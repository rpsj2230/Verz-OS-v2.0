"""The control schedule the worker ticks: what runs, what is recorded, and what is left alone.

This is where M25.1.5, M36.1.3.2 and M34.2.1.3 stop being "a runner exists" and become "a
schedule starts them": a tick against a real `ops.control_run` starts the retention sweep, the
re-verification nag and the spend report refresh once, records each, leaves every control with
nothing to run unrecorded, skips a control another replica holds, and records a runner that
raises as a failed run while the next control still runs. The runners are replaced by a
recording stand-in for those, because what is under test is the loop.

One test does not replace the runner. The re-verification nag is started through the real
`start_control` against a database holding the grant tables, the outbox and `know.item`, so the
tick is shown to reach an owner's nag end to end rather than a stand-in's sentence.

The clock is 2999, for the reason CLAUDE.md records.

Task ids: M34.2.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from brain.knowledge.item import KnowledgeItem
from brain.knowledge.parse_budget import PARSE_WORKER_COMPONENT
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops import schedule_runner, worker
from brain.ops.queue import SlotClass
from brain.ops.schedule import schedulable
from brain.ops.schedule_runner import RUNNERS, lock_id
from brain.ops.worker import (
    DEFAULT_WORKER_COMPONENT,
    EXIT_MISCONFIGURED,
    ControlTick,
    Ticked,
    run_schedule,
    schedule_url,
    schedules_here,
    serve,
    tick_controls,
)
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.knowledge_items import (
    a_person,
    a_reader,
    knowledge_items,
    nags,
    put,
)
from tests.fixtures.scratch_postgres import (
    RETENTION_TABLES,
    SCHEDULE_CONTROL_TABLES,
    add_modelled,
    drop,
    fresh,
    migrate,
    run,
    sql,
    with_every_control_name,
)

NOW = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
FINISHED = NOW + timedelta(seconds=7)

#: The runners that can start, read off the table the worker dispatches from.
WIRED = [one.name for one in RUNNERS if one.run is not None]

#: What each wired control is started with on a fresh install, in the order the tick starts them.
STARTED = [
    ("retention_sweep", True),
    ("canary_run", False),
    ("knowledge_reverification", False),
    ("outbox_dispatch", False),
    ("spend_report_refresh", False),
    ("erasure_queue", False),
]


@contextmanager
def control_runs(database: str) -> Iterator[str]:
    """A database holding `ops.control_run` with the name constraint `0037` leaves, the
    retention tables `0049` builds, which the tick reads the sweep's release from, and
    `ops.setting`, which it reads a person's pauses and run requests from."""
    url = fresh(database)
    try:
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", "0036")
        migrate(database, "upgrade", "0037")
        with_every_control_name(url)
        add_modelled(url, (*RETENTION_TABLES, *SCHEDULE_CONTROL_TABLES))
        yield url
    finally:
        drop(database)


class Starts:
    """Stands in for `start_control`, recording each start and raising for the names asked."""

    def __init__(self, *, raising: frozenset[str] = frozenset()) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.raising = raising

    def __call__(self, name: str, *, now: datetime, report_only: bool, database_url: str) -> str:
        self.calls.append((name, report_only))
        if name in self.raising:
            msg = f"{name} broke on purpose"
            raise RuntimeError(msg)
        return f"{name} ran"


def tick(url: str, *, at: datetime) -> tuple[ControlTick, ...]:
    async def once() -> tuple[ControlTick, ...]:
        engine = make_app_engine(url)
        try:
            return await tick_controls(
                make_session_factory(engine),
                now=at,
                database_url=url,
                clock=lambda: at + (FINISHED - NOW),
            )
        finally:
            await engine.dispose()

    return run(once)


def recorded(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT name, outcome, report_only, detail, started_at, finished_at "
        "FROM ops.control_run ORDER BY started_at, name",
    )


@pytest.fixture
def starts(monkeypatch: pytest.MonkeyPatch) -> Starts:
    fake = Starts()
    monkeypatch.setattr(worker, "start_control", fake)
    return fake


# ------------------------------------------------------------------- without a server
def test_the_wired_runners_are_the_six_the_schedule_is_meant_to_start() -> None:
    """Asserted against the names, so a runner wired or unwired later moves this on purpose.

    The webhook dispatch, the erasure queue and the permission canaries joined on 2026-09-17.

    Delete this and every assertion below that names the six could be satisfied by a table
    that had quietly lost one of them."""
    assert WIRED == [
        "retention_sweep",
        "canary_run",
        "knowledge_reverification",
        "outbox_dispatch",
        "spend_report_refresh",
        "erasure_queue",
    ]


def test_only_the_general_worker_ticks_the_schedule_and_it_needs_the_applications_url() -> None:
    """The general worker schedules and the parse worker does not; an unset or blank URL is
    None, and a set one is read as given.

    Delete this and a parse container could spend a parse's memory on a retention sweep, or a
    general worker with no URL could start draining its queue and schedule nothing."""
    assert schedules_here(DEFAULT_WORKER_COMPONENT) is True
    assert schedules_here("brain-parse-worker") is False
    assert schedule_url({}) is None
    assert schedule_url({"DATABASE_URL": "   "}) is None
    assert schedule_url({"DATABASE_URL": " postgresql://app@pooler/brain "}) == (
        "postgresql://app@pooler/brain"
    )


def test_the_worker_finds_the_applications_database_under_the_name_the_application_prefers() -> (
    None
):
    """The worker reads the address through `Settings`, so a host that names it only as
    `BRAIN_DATABASE_URL` schedules, and a host naming both gives the worker the one the
    application connects to.

    Delete this and the worker can go back to reading `DATABASE_URL` for itself, which is what it
    did until 2026-09-15: a general worker on such a host refuses to schedule while the
    application beside it is healthy, or schedules against the stale one of the two."""
    from brain.settings import settings_from

    prefixed = {"BRAIN_DATABASE_URL": "postgresql://app@pooler/brain"}
    assert schedule_url(prefixed) == "postgresql://app@pooler/brain"

    both = {
        "BRAIN_DATABASE_URL": "postgresql://app@pooler/current",
        "DATABASE_URL": "postgresql://app@pooler/stale",
    }
    assert schedule_url(both) == settings_from(both).database_url
    assert schedule_url(both) == "postgresql://app@pooler/current"


def test_a_general_worker_with_no_application_url_refuses_before_it_opens_anything(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The general worker with no `DATABASE_URL` is refused with the schedule's own sentence;
    given one, it gets past that refusal to the next thing missing; and the parse worker, which
    does not schedule, is never told about the schedule at all.

    Delete this and a general worker with no application URL could start, drain its queue and
    schedule nothing, which is every control in the estate stopped with nothing saying so."""
    refused = worker.run(
        {}, worker_component=DEFAULT_WORKER_COMPONENT, slot_class=SlotClass.STANDARD
    )
    assert refused == EXIT_MISCONFIGURED
    assert "ticks the control schedule and DATABASE_URL is not set" in capsys.readouterr().err

    given = {"DATABASE_URL": "postgresql://app@pooler/brain"}
    assert (
        worker.run(given, worker_component=DEFAULT_WORKER_COMPONENT, slot_class=SlotClass.STANDARD)
        == EXIT_MISCONFIGURED
    )
    assert "ticks the control schedule" not in capsys.readouterr().err

    assert (
        worker.run({}, worker_component=PARSE_WORKER_COMPONENT, slot_class=SlotClass.STANDARD)
        == EXIT_MISCONFIGURED
    )
    assert "ticks the control schedule" not in capsys.readouterr().err


def test_a_tick_that_raises_is_reported_and_the_next_tick_still_happens(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first tick raises, the second returns; both happen, the first is printed with its
    reason, and the loop only stops when it is cancelled.

    Delete this and one unreachable database at start-up would stop the schedule for the life of
    the container, with the queue beside it still reporting healthy."""
    ticks: list[datetime] = []

    async def flaky(*_: object, now: datetime, **__: object) -> tuple[ControlTick, ...]:
        ticks.append(now)
        if len(ticks) == 1:
            msg = "no route to the pooler"
            raise OSError(msg)
        return (ControlTick("retention_sweep", Ticked.FAILED, "RuntimeError: broke"),)

    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(worker, "tick_controls", flaky)
    with pytest.raises(asyncio.CancelledError):
        run(lambda: run_schedule(None, database_url="unused", clock=lambda: NOW, sleep=sleep))  # type: ignore[arg-type]

    printed = capsys.readouterr().err
    assert len(ticks) == 2
    assert "could not tick" in printed and "OSError: no route to the pooler" in printed
    assert "control retention_sweep failed: RuntimeError: broke" in printed
    assert all(0.0 <= one <= 30.0 for one in sleeps)


def test_the_schedule_runs_beside_the_shards_and_stops_when_they_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a URL the schedule starts and is cancelled once the shards return; without one the
    shards run alone and nothing is scheduled.

    Delete this and a worker told to stop could leave a tick half written, or a parse worker could
    tick the schedule because nothing checked which container it was."""
    events: list[str] = []

    async def shards(*_: object, **__: object) -> None:
        await asyncio.sleep(0)
        events.append("shards")

    async def schedule(*_: object, **__: object) -> None:
        events.append("schedule started")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            events.append("schedule cancelled")
            raise

    monkeypatch.setattr(worker, "run_shards", shards)
    monkeypatch.setattr(worker, "run_schedule", schedule)

    run(lambda: serve(object(), (), beat=lambda: None, database_url=None))
    assert events == ["shards"]

    events.clear()
    run(
        lambda: serve(
            object(), (), beat=lambda: None, database_url="postgresql://nobody@127.0.0.1:1/none"
        )
    )
    assert events == ["schedule started", "shards", "schedule cancelled"]


# ------------------------------------------------------------------------ with a server
def test_a_due_control_is_started_once_and_its_run_is_recorded(starts: Starts) -> None:
    """Every wired control is owed on a fresh install and each starts exactly once: the sweep in
    report-only mode, recorded as refused, and the canaries, the nag and the refresh recorded as
    ok, each with the runner's sentence and the finish taken from the clock. Every other
    schedulable control is reported as having nothing to run and leaves no row.

    Delete this and the loop could start a control twice in one tick, record it under the wrong
    outcome, or write rows for controls that cannot run."""
    with control_runs("brain_worker_schedule_due") as url:
        found = tick(url, at=NOW)

        assert starts.calls == STARTED
        assert [(one.name, one.outcome, one.report_only, one.detail) for one in _rows(url)] == [
            ("canary_run", "ok", False, "canary_run ran"),
            ("erasure_queue", "ok", False, "erasure_queue ran"),
            ("knowledge_reverification", "ok", False, "knowledge_reverification ran"),
            ("outbox_dispatch", "ok", False, "outbox_dispatch ran"),
            ("retention_sweep", "refused", True, "retention_sweep ran"),
            ("spend_report_refresh", "ok", False, "spend_report_refresh ran"),
        ]
        assert {row[4] for row in recorded(url)} == {NOW}
        assert {row[5] for row in recorded(url)} == {FINISHED}
        by_name = {one.name: one.ticked for one in found}
        assert by_name["retention_sweep"] is Ticked.REFUSED
        assert by_name["canary_run"] is Ticked.RAN
        assert by_name["knowledge_reverification"] is Ticked.RAN
        assert by_name["spend_report_refresh"] is Ticked.RAN
        assert by_name["outbox_dispatch"] is Ticked.RAN
        unwired = {one.name for one in schedulable()} - set(WIRED)
        assert {name for name, ticked in by_name.items() if ticked is Ticked.NOTHING_TO_RUN} == (
            unwired
        )


def test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report(starts: Starts) -> None:
    """A release recorded after a report: the tick starts the sweep acting and records it as ok.
    Withdrawn, the next due tick starts it reporting again.

    Delete this and the tick could go on passing no release to `due_now`, which is the state the
    sweep was in from 0037 until 0049: scheduled, and forbidden to act for ever."""
    with control_runs("brain_worker_schedule_released") as url:
        report = sql(
            url,
            "INSERT INTO ops.retention_report (at, report_only, complete, stores, holds, findings) "
            "VALUES (%s, true, false, '[]', '[]', '[]') RETURNING id",
            NOW - timedelta(days=2),
        )[0][0]
        sql(
            url,
            "INSERT INTO ops.retention_release (after_report, released_at, released_by) "
            "VALUES (%s, %s, 'u_admin')",
            report,
            NOW - timedelta(days=1),
        )
        tick(url, at=NOW)
        sql(
            url,
            "UPDATE ops.retention_release SET withdrawn_at = %s, withdrawn_by = 'u_admin'",
            NOW + timedelta(hours=1),
        )
        tick(url, at=NOW + timedelta(days=1, minutes=1))

    sweeps = [call for call in starts.calls if call[0] == "retention_sweep"]
    assert sweeps == [("retention_sweep", False), ("retention_sweep", True)]


def test_nothing_that_is_not_due_runs_and_it_runs_again_once_its_cadence_has_passed(
    starts: Starts,
) -> None:
    """A second tick thirty seconds later starts nothing and records nothing; a tick a day and a
    minute after the first starts every wired control again. Thirty seconds rather than a minute
    since the webhook dispatch, whose cadence is a minute, joined the schedule.

    Delete this and the loop could restart every wired control on every thirty-second tick, which
    is a retention sweep two thousand eight hundred and eighty times a day."""
    with control_runs("brain_worker_schedule_cadence") as url:
        tick(url, at=NOW)
        later = tick(url, at=NOW + timedelta(seconds=30))

        assert starts.calls == STARTED
        assert len(recorded(url)) == 6
        assert not any(one.name in WIRED for one in later)

        tick(url, at=NOW + timedelta(days=1, minutes=1))
        assert len(starts.calls) == 12
        assert len(recorded(url)) == 12


def test_a_control_whose_lock_another_replica_holds_is_not_started_and_the_rest_are(
    starts: Starts,
) -> None:
    """Another connection holds the refresh's advisory lock in an open transaction: the refresh is
    reported as locked elsewhere, is not started and leaves no row, and the others still run.

    Delete this and two replicas ticking together could both start one control, which for the
    sweep is two deletions of one window."""
    with control_runs("brain_worker_schedule_locked") as url:
        with psycopg.connect(url) as other:
            other.execute("SELECT pg_advisory_xact_lock(%s, %s)", lock_id("spend_report_refresh"))
            found = tick(url, at=NOW)
            other.rollback()

        assert starts.calls == [*STARTED[:4], STARTED[5]]
        assert [row[0] for row in recorded(url)] == [
            "canary_run",
            "erasure_queue",
            "knowledge_reverification",
            "outbox_dispatch",
            "retention_sweep",
        ]
        assert {one.name: one.ticked for one in found}["spend_report_refresh"] is (
            Ticked.LOCKED_ELSEWHERE
        )


def test_a_runner_that_raises_is_recorded_as_failed_with_its_reason_and_the_next_one_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sweep's runner raises: its run is finished as failed with the exception's type and
    message, and the ones declared after it still start and are recorded as ok.

    Delete this and one broken control would either vanish from the record or stop every control
    declared after it."""
    fake = Starts(raising=frozenset({"retention_sweep"}))
    monkeypatch.setattr(worker, "start_control", fake)
    with control_runs("brain_worker_schedule_failed") as url:
        found = tick(url, at=NOW)

        assert fake.calls == STARTED
        assert [(one.name, one.outcome, one.detail) for one in _rows(url)] == [
            ("canary_run", "ok", "canary_run ran"),
            ("erasure_queue", "ok", "erasure_queue ran"),
            ("knowledge_reverification", "ok", "knowledge_reverification ran"),
            ("outbox_dispatch", "ok", "outbox_dispatch ran"),
            ("retention_sweep", "failed", "RuntimeError: retention_sweep broke on purpose"),
            ("spend_report_refresh", "ok", "spend_report_refresh ran"),
        ]
        assert {one.name: one.ticked for one in found}["retention_sweep"] is Ticked.FAILED


def test_the_tick_records_the_re_verification_nag_through_the_real_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The leaf, end to end.** One tick of the worker's schedule starts
    `knowledge_reverification` through the real `start_control`, which reads a lapsed item out
    of `know.item`, resolves its owner's grants, records the owner's nag in the outbox and
    commits, and the tick records the run as ok with the store's sentence. The other wired
    controls are stood in for, because they need tables this database does not hold.

    Delete this and every other test of the nag could pass with nothing on a schedule reaching
    it, which is the state this control was in for as long as it had no row."""
    real = schedule_runner.start_control
    others = Starts()

    def started(name: str, *, now: datetime, report_only: bool, database_url: str) -> str:
        if name == "knowledge_reverification":
            return real(name, now=now, report_only=report_only, database_url=database_url)
        return others(name, now=now, report_only=report_only, database_url=database_url)

    monkeypatch.setattr(worker, "start_control", started)
    lapsed = NOW - timedelta(days=1)
    item = KnowledgeItem(
        item_id="kb.renewals",
        content="What the document says.",
        title="Renewal pricing",
        visibility=KnowledgeVisibility.of_department("web", owner_id="u_owner"),
        owner_id="u_owner",
    ).verified(by="u_verifier", at=lapsed - timedelta(days=365), review_by=lapsed)

    with knowledge_items("brain_kr_worker_tick") as url:
        # The tick reads the sweep's release since 0049, which this chain stops short of, and a
        # person's pauses from `ops.setting`, which is created only when missing.
        add_modelled(url, (*RETENTION_TABLES, *SCHEDULE_CONTROL_TABLES))
        with_every_control_name(url)
        a_person(url, "u_owner")
        a_reader(url, "u_owner", "web")
        put(url, item)

        found = tick(url, at=NOW)
        runs = {row[0]: (row[1], row[3]) for row in recorded(url)}
        recorded_nags = nags(url)

    assert {one.name: one.ticked for one in found}["knowledge_reverification"] is Ticked.RAN
    outcome, detail = runs["knowledge_reverification"]
    assert outcome == "ok"
    assert detail.startswith(f"knowledge re-verification at {NOW.isoformat()}: ")
    assert "a nag was recorded: yes;" in detail
    assert recorded_nags == [
        ("kb.renewals", {"route": "owner", "recipient": "u_owner", "review_by": lapsed.isoformat()})
    ]
    assert others.calls == [
        ("retention_sweep", True),
        ("canary_run", False),
        ("outbox_dispatch", False),
        ("spend_report_refresh", False),
        ("erasure_queue", False),
    ]
    # The registry's entry point is what the schedule starts, so the control cannot measure as
    # running through its decision functions while the store they need goes uncalled.
    from brain.ops.controls import control

    assert control("knowledge_reverification").entry_point == (
        "brain.knowledge.item_store:run_reverification_now"
    )


class _Row:
    def __init__(self, row: tuple[Any, ...]) -> None:
        self.name, self.outcome, self.report_only, self.detail = row[:4]


def _rows(url: str) -> list[_Row]:
    return [_Row(row) for row in recorded(url)]
