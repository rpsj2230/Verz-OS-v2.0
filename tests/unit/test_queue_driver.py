"""The queue driver as configured: what it is told, what it is bounded by, and what installs it.

Every test here is about a queue that works and is wrong. A worker judged against a staleness
it is not keeping, a pool that opens more than the budget says, a driver whose tables arrive
readable by every role: none of those raises, none appears in a metric, and each is discovered
by the mechanism it was meant to make unnecessary.

The tests that need a server are marked `needs_db` and perform the deploy step. That is not a
side effect to apologise for: `install_queue` is what an operator runs before the first
`docker compose up` of the worker, it is idempotent, and running it against a database leaves
that database in the state a deploy would.

Task ids: M32.4.1.1
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import replace
from typing import Any, cast

import pytest

from brain.gate.context import TrafficClass
from brain.ops.connections import WORKER_QUEUE_CONNECTIONS
from brain.ops.queue import (
    CONCURRENCY,
    DRIVER_SCHEMA,
    DRIVER_TABLE_PREFIX,
    FALLBACK_POLL_SECONDS,
    HEARTBEAT_SECONDS,
    STALE_AFTER_HEARTBEATS,
    QueueError,
    Shard,
    driver_default_disagreements,
    driver_default_options,
    driver_option_gaps,
    driver_options,
    install_queue,
    queue_name_for,
    queue_pool_gaps,
    run_shards,
    stale_after,
    tasks_of_ours,
    unattributable_tables,
    worker_shards,
)

APP_URL = "postgresql+psycopg://brain:pw@pgbouncer:5432/brain"
DIRECT_URL = "postgresql+psycopg://brain:pw@db:5432/brain"

#: How long a stubbed driver worker pretends to be working.
#:
#: **Five seconds rather than an hour, and the difference cost a mutation run.** The first
#: version slept for an hour, which is what a real worker does, and a mutation that removed the
#: refusal in `run_shards` then produced a test that hung instead of a test that failed. The
#: harness has no per-test timeout and waits on pytest, so one row's mutation stopped the whole
#: table rather than filling in. A stub's job is to be observable and then get out of the way.
STUB_WORKER_SECONDS = 5.0

SHARD = Shard(
    queue=queue_name_for(TrafficClass.SYSTEM),
    traffic_class=TrafficClass.SYSTEM,
    concurrency=1,
)


# --------------------------------------------------- what the driver is told
def test_the_driver_is_given_this_modules_figures_and_never_its_own_defaults() -> None:
    """The translation from a shard into the driver's worker options, and the positive half of
    every disagreement test below. A check tested only by what it refuses is satisfied by one
    that refuses everything, and this surface exists to hand the driver three numbers that are
    argued elsewhere in `brain.ops.queue` rather than to have an opinion of its own.

    Delete this and `driver_options` can stop passing one of them, which is invisible: the
    driver falls back to a default and the worker runs."""
    options = driver_options(SHARD)

    assert driver_option_gaps(options) == ()
    assert options.queues == (SHARD.queue,)
    assert options.concurrency == SHARD.concurrency
    assert options.fetch_job_polling_interval == FALLBACK_POLL_SECONDS
    assert options.update_heartbeat_interval == HEARTBEAT_SECONDS
    assert options.stalled_worker_timeout == stale_after().total_seconds()
    assert options.listen_notify is True


def test_the_drivers_own_grace_period_is_shorter_than_ours_and_is_reported_by_name() -> None:
    """**The finding this whole surface exists for, and it is not a tuning difference.** The
    driver prunes a worker row whose heartbeat is older than its own default, our staleness is
    `HEARTBEAT_SECONDS` times `STALE_AFTER_HEARTBEATS`, and the driver's job row references the
    worker row `ON DELETE SET NULL`. Its stalled-job query reports every running job whose
    worker is null whatever staleness it is asked about, so pruning early hands live jobs to a
    sweep that was asked about a longer window. `STALE_AFTER_HEARTBEATS` is four rather than one
    exactly so that a worker paused by memory pressure on this shared host is not treated as
    dead, and the driver's default removes that grace period without contradicting a word of
    the argument for it.

    Read off the driver's own signature rather than compared against a number written here, so
    a default it changes in a release arrives as a different answer instead of as silence.

    Delete this and the two figures can drift apart in either direction with the queue working
    perfectly throughout, and what is lost is the grace period, which only shows up as work
    being run twice."""
    defaults = driver_default_options(SHARD)
    gaps = driver_option_gaps(defaults)

    assert defaults.stalled_worker_timeout < stale_after().total_seconds()
    assert any("prunes a worker after" in gap for gap in gaps), gaps
    assert any("heartbeat is written every" in gap for gap in gaps), gaps
    assert driver_default_disagreements(SHARD) == gaps


def test_a_shard_told_to_poll_rather_than_listen_is_reported() -> None:
    """Listening is why the queue does not go behind the transaction pooler at all, so a worker
    with it switched off has chosen the degraded mode the pooler produces by accident: its whole
    latency becomes the fallback poll, permanently, and nothing anywhere says so.

    Delete this and `listen_notify` can be turned off to work around a connection problem, which
    is the one edit that makes the pooler refusal pointless."""
    gaps = driver_option_gaps(replace(driver_options(SHARD), listen_notify=False))

    assert any("listening switched off" in gap for gap in gaps), gaps


def test_a_shard_that_drains_no_queue_at_all_is_reported() -> None:
    """The driver reads an empty queue list as "every queue", which is the routing defect the
    slot classes exist to close: the container sized for cheap work fetches the expensive job.
    `Shard` cannot be built that way, so this is the check on the translation rather than on the
    shard.

    Delete this and an empty tuple reaching the driver is a container draining everything."""
    gaps = driver_option_gaps(replace(driver_options(SHARD), queues=()))

    assert any("names no queue" in gap for gap in gaps), gaps


def test_a_shard_allocated_no_slots_at_all_is_reported() -> None:
    """A worker that fetches nothing still holds a connection and still reports itself up, which
    is the sentence `Shard` refuses on and this repeats at the driver's door. The two are not one
    check: a shard is built from an allocation and these options are built from a shard, and a
    translation that dropped the concurrency would produce the driver's default of one.

    Delete this and a zero allocation silently becomes one slot."""
    gaps = driver_option_gaps(replace(driver_options(SHARD), concurrency=0))

    assert any("fetches nothing" in gap for gap in gaps), gaps


# --------------------------------------------------- the connection bound
def test_every_shard_holds_a_connection_so_the_shard_count_is_a_floor_on_the_pool() -> None:
    """**The arithmetic nothing did, and it is uncomfortable rather than wrong.** Listening is a
    connection-bound operation and each worker process opens its own, so the shards are spoken
    for before any work is fetched and what is left is shared by every fetch, heartbeat and
    completion in the container. psycopg's pool makes an exhausted pool a wait rather than an
    error, so the symptom of getting this wrong is latency and never a failure.

    Delete this and the next traffic class with an allocation takes the general worker to four
    listeners against five connections, and the one after that does not fit at all."""
    shards = worker_shards(CONCURRENCY)

    assert queue_pool_gaps(WORKER_QUEUE_CONNECTIONS, shards) == ()
    assert len(shards) < WORKER_QUEUE_CONNECTIONS

    crowded = queue_pool_gaps(len(shards), shards)

    assert any("each hold a connection to listen on" in gap for gap in crowded), crowded


def test_a_queue_bounded_at_nothing_is_a_worker_that_cannot_fetch() -> None:
    """Not a smaller pool. A bound of zero or less is a container that holds no connection,
    fetches nothing and reports itself up, which is the state every refusal in this module is
    about.

    Delete this and a mis-derived share of a declared bound reaches the driver as a pool size."""
    assert any("cannot fetch anything" in gap for gap in queue_pool_gaps(0, (SHARD,)))
    assert queue_pool_gaps(5, ()) == ()


# --------------------------------------------------- what installs it
def test_the_installer_refuses_a_pooler_connection_before_it_opens_one() -> None:
    """The refusal has to be at this door as well as at the worker's. A queue installed
    correctly on a connection nothing will ever listen on is the worst outcome available: the
    tables are right, the row-level security is on, the deploy reports success, and the only
    symptom is a queue whose latency is the fallback poll for ever.

    Delete this and the install step is the one path that never asks."""
    with pytest.raises(QueueError, match="transaction pooler"):
        install_queue(APP_URL, pool_max=5)


def test_the_installer_refuses_a_schema_the_security_sweep_does_not_enumerate() -> None:
    """`sweep_rls` reads `brain.db.SCHEMAS` and looks nowhere else, so the driver's tables in an
    undeclared schema are not merely undeclared, they are outside the reach of the only check
    that would report them having no row-level security.

    Delete this and the queue can be installed into `public`, which is where the driver puts it
    by default and which that sweep does not look in at all."""
    with pytest.raises(QueueError, match="sweep_rls"):
        install_queue(DIRECT_URL, pool_max=5, schema="public")


def test_the_installer_refuses_an_unbounded_pool_rather_than_choosing_one() -> None:
    """The same rule the running worker is held to, at the door that runs first. An installer
    that defaulted its own pool would be a client of that database nobody budgeted, which is
    `A_DIRECT_CLIENT_IS_THE_ONE_THE_POOLER_DOES_NOT_BOUND` in the one process an operator runs
    by hand and watches.

    Delete this and the install opens what it likes."""
    with pytest.raises(QueueError, match="bounded at 0 connections"):
        install_queue(DIRECT_URL, pool_max=0)


def test_the_drivers_own_housekeeping_task_is_not_counted_as_one_of_ours() -> None:
    """**Written because the guard that needed it could not fire, and only running the process
    showed that.** `brain.ops.worker` prints an advisory when nothing this system registered can
    be run, which is the state today; it asked the driver's registry, and the driver registers a
    job-pruning task of its own on every app it builds, under two names. So the count was never
    zero, the advisory was never printed, and every test of the surrounding code was green.

    A prefix rather than a substring, and the asymmetry matters: excluding any name containing
    "builtin" would hide a task of ours called `report.builtin_summary`, and that failure is the
    flattering one, where the process reports nothing registered while something is.

    Delete this and the filter can go back to matching the registry, and the sentence about what
    is still missing stops being printed on the day it is most true."""
    registered = (
        "procrastinate.builtin_tasks.remove_old_jobs",
        "builtin:procrastinate.builtin_tasks.remove_old_jobs",
        "answer.compose",
        "report.builtin_summary",
    )

    assert tasks_of_ours(registered) == ("answer.compose", "report.builtin_summary")
    assert tasks_of_ours(()) == ()


def test_the_driver_registers_a_task_of_its_own_so_an_empty_registry_never_happens() -> None:
    """The measured fact the filter above exists for, read off a real app rather than asserted.
    A test that only exercised the filter would pass against a driver that registers nothing,
    which is the version of the world in which the original guard was correct.

    Delete this and the filter looks like defensive tidying rather than a fact about the driver,
    and the next person removes it."""
    from brain.ops.queue import queue_app

    app = queue_app(DIRECT_URL, pool_max=5)

    assert app.tasks, "the driver registered nothing, so the filter below is about nothing"
    assert tasks_of_ours(app.tasks) == ()


def test_a_table_that_appeared_and_is_not_the_drivers_stops_the_install() -> None:
    """The driver renaming its tables is the fork this module has argued about twice in prose
    and could not detect. The security step is built from what the catalogue gained, so a table
    it cannot attribute to the driver is a table it has no basis to secure, and filtering
    silently would leave exactly that table unsecured in a schema the sweep enumerates.

    A refusal rather than a filter, and the message names both ways it happens: the driver
    renaming its tables, and something else writing into the schema while the install ran.

    Delete this and a driver upgrade that renames a table installs a queue with one table
    nothing protects, and the sweep that would say so is the one whose remedy this step is."""
    assert unattributable_tables([f"{DRIVER_TABLE_PREFIX}jobs"]) == ()
    assert unattributable_tables([]) == ()
    assert unattributable_tables(["celery_taskmeta", f"{DRIVER_TABLE_PREFIX}events"]) == (
        "celery_taskmeta",
    )


# --------------------------------------------------- the process layout
class _RecordingApp:
    """An app that records how each worker was started and then waits to be cancelled.

    A stub rather than a real driver, because what is under test is the translation and not the
    driver: the figures `run_shards` passes are the whole of what this module decides, and a
    test against a live queue would prove the driver works and say nothing about which numbers
    it was given.
    """

    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.opened = 0

    def open_async(self) -> Any:
        app = self

        class _Open:
            async def __aenter__(self) -> None:
                app.opened += 1

            async def __aexit__(self, *exc: object) -> None:
                return None

        return _Open()

    async def run_worker_async(self, **kwargs: Any) -> None:
        self.started.append(kwargs)
        # Bounded, and the bound is the point. A stub that waited for ever turns any mutation
        # that gets past a refusal in `run_shards` into a test that hangs rather than one that
        # fails, and a hanging test is a mutation run nobody gets a table out of: the harness
        # has no per-test timeout and waits on pytest. Long enough that `_drive` always sees
        # every worker start, short enough that a mutation costs seconds.
        await asyncio.sleep(STUB_WORKER_SECONDS)

    @property
    def tasks(self) -> dict[str, Any]:
        return {}


def _as_app(app: _RecordingApp) -> Any:
    """The stub where the driver's own app is expected.

    A cast at the boundary rather than a subclass of the driver's type. `run_shards` uses two
    of its methods, and a subclass would inherit a constructor that wants a connector, which
    means opening a pool in order to test the arithmetic of not opening one.
    """
    return cast(Any, app)


def _drive(shards: tuple[Shard, ...]) -> tuple[_RecordingApp, list[int]]:
    """Start the shards, let them register, then cancel the way a shutdown does."""
    beats: list[int] = []

    async def go() -> _RecordingApp:
        app = _RecordingApp()
        running = asyncio.create_task(
            run_shards(_as_app(app), shards, beat=lambda: beats.append(1))
        )
        for _ in range(200):
            await asyncio.sleep(0.01)
            if len(app.started) == len(shards) and beats:
                break
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running
        return app

    return asyncio.run(go()), beats


def test_one_driver_worker_is_started_per_shard_on_the_queue_that_shard_drains() -> None:
    """Per-class concurrency is a process layout rather than a setting, because the driver takes
    one concurrency and a list of queues. This is that translation actually happening: three
    allocations become three workers, each on its own queue, at its own concurrency.

    Delete this and one worker on every queue at one concurrency passes every other test here,
    and a backfill's thousand automation jobs occupy every slot while the reply somebody is
    waiting for sits behind them."""
    shards = worker_shards(CONCURRENCY)
    app, beats = _drive(shards)

    assert app.opened == 1
    assert [call["queues"] for call in app.started] == [[s.queue] for s in shards]
    assert [call["concurrency"] for call in app.started] == [s.concurrency for s in shards]
    assert beats, "the heartbeat the readiness check reads was never written"


def test_no_shard_installs_the_drivers_own_signal_handlers() -> None:
    """**A defect avoided rather than a preference.** The driver installs its handlers per
    worker and saves what it displaced; three workers on one loop means the third saves the
    second's, and a SIGTERM stops one of the three. The other two are killed mid-job after the
    runtime's grace period, on every ordinary deploy, which is the re-drive machinery being
    exercised by the deployment rather than by a crash.

    Delete this and the flag can be dropped in an edit that reads as removing a workaround, and
    the symptom is jobs quarantined after deploys."""
    app, _ = _drive(worker_shards(CONCURRENCY))

    assert app.started
    assert all(call["install_signal_handlers"] is False for call in app.started)


def test_every_shard_is_started_on_this_modules_figures() -> None:
    """The other end of `driver_options`: the figures are not merely computed, they reach the
    driver. `CLAUDE.md` states the rule this is written for, which is that a producer and a
    consumer either side of a value need a test each, or the two tests are both about the
    producer.

    Delete this and `run_shards` can build the options and start the workers without them,
    which is exactly what the driver's defaults are for."""
    app, _ = _drive(worker_shards(CONCURRENCY))

    for call in app.started:
        assert call["fetch_job_polling_interval"] == FALLBACK_POLL_SECONDS
        assert call["update_heartbeat_interval"] == HEARTBEAT_SECONDS
        assert call["stalled_worker_timeout"] == HEARTBEAT_SECONDS * STALE_AFTER_HEARTBEATS
        assert call["listen_notify"] is True


def test_a_worker_with_no_shard_at_all_refuses_rather_than_waiting() -> None:
    """An allocation of zero everywhere produces no shards, and a process that opened a pool
    and started nothing would hold a connection, drain nothing and report itself up, which is
    the shape every refusal in this module is about.

    Delete this and a compose file with four zeroes in it deploys a container that looks
    healthy for ever."""
    with pytest.raises(QueueError, match="no shard to run"):
        asyncio.run(run_shards(_as_app(_RecordingApp()), ()))


def test_the_shards_are_refused_if_they_would_be_started_on_the_wrong_figures() -> None:
    """The gate between `driver_option_gaps` and the thing that starts workers. The check exists
    and would be a check nobody runs if the run path did not ask it, which is this repository's
    most common defect.

    Delete this and the options can be wrong at the one moment they matter, with every option
    test above still green."""
    wrong = Shard(
        queue=queue_name_for(TrafficClass.SYSTEM),
        traffic_class=TrafficClass.SYSTEM,
        concurrency=1,
    )
    with pytest.raises(QueueError, match="figures this module did not choose"):
        asyncio.run(
            run_shards(
                _as_app(_RecordingApp()), (wrong,), beat=None, options=driver_default_options
            )
        )


# --------------------------------------------------- what only a server can say
def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL") or None


@pytest.mark.needs_db
def test_the_install_creates_the_drivers_tables_and_leaves_none_of_them_readable() -> None:
    """**The only test that can establish what the deploy plan claims.** Every other test here
    is about figures; this is about a catalogue. The driver's tables are not in
    `migrations/versions` and cannot be, so the rule that every new table enables row-level
    security is kept by a deploy step, and a deploy step is a promise until something reads the
    catalogue back.

    Three facts, and the third is the one a flag cannot give you. The tables appear; every one
    of them reports `relrowsecurity`; and none of them carries a policy, because a policy of
    `USING (true)` would read as thoroughness and grant everything straight back, leaving a
    green sweep over a table nothing protects.

    Run twice, because the driver's own schema command is a create and raises on its second
    run: a deploy step that fails on redeploy fails at the moment an operator can least afford
    to read it.

    **Row-level security is switched off first wherever it is already on**, which is what makes
    this a test rather than an observation. Against a database the install has already touched,
    a run that enabled nothing at all would leave the flags exactly as this expects to find
    them, so the assertion would pass for a step that did not run. Turning them off is the only
    way to ask whether this run turns them back on.

    Delete this and the install is verified by the absence of an exception, which is the same
    evidence a step that did nothing would produce."""
    import psycopg

    from brain.db import libpq_url

    url = _database_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no catalogue to read; CI always sets it")

    with psycopg.connect(libpq_url(url), autocommit=True) as conn:
        for (existing,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tablename LIKE %s",
            (DRIVER_SCHEMA, f"{DRIVER_TABLE_PREFIX}%"),
        ).fetchall():
            conn.execute(f"ALTER TABLE {DRIVER_SCHEMA}.{existing} DISABLE ROW LEVEL SECURITY")

    first = install_queue(url, pool_max=WORKER_QUEUE_CONNECTIONS)
    second = install_queue(url, pool_max=WORKER_QUEUE_CONNECTIONS)

    assert any("row-level security is on" in line for line in first)
    assert any("already present" in line for line in second)

    with psycopg.connect(libpq_url(url), autocommit=True) as conn:
        rows = conn.execute(
            "SELECT c.relname, c.relrowsecurity, "
            "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = 'r' AND c.relname LIKE %s",
            (DRIVER_SCHEMA, f"{DRIVER_TABLE_PREFIX}%"),
        ).fetchall()

    assert rows, "the driver's command created no table in the schema the sweep enumerates"
    for name, secured, policies in rows:
        assert secured is True, f"{name} has row-level security off"
        assert policies == 0, (
            f"{name} carries {policies} policy, which grants back what the flag denied"
        )
