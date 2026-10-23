"""The queue install check: a job put on the install's own queue is fetched and run by a worker, the
check says in words where it cannot be asked, and it fails where the queue is broken.

The pure half holds the check to its leaf, its page order and the property that makes its probe
safe: the class it uses is allocated no slots. The database half installs the queue the way the
worker does on its first start, runs the check as the worker runs the suite, and breaks the queue
one property at a time. Every database test ends by counting what the queue holds, because the
probe is committed on the queue's own connection and only its name finds it again.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M17.1.2
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    REASON_CHARS,
    Check,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_queue"
RUNS = "a_job_put_on_the_install_s_queue_is_fetched_and_run_by_a_worker"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_its_leaf_and_stands_in_its_range() -> None:
    """Delete this and the check can close a leaf it does not exercise, or sit on the page's order
    key of another module."""
    from brain.ops import acceptance_checks_queue as module

    assert {name: one.leaves for name, one in mine().items()} == {RUNS: ("M17.1.2",)}
    assert checks_in(MODULE) == [RUNS]
    assert 2060 < module.CHECK_ORDER < 2070


def test_every_sentence_the_check_says_fits_a_stored_reason() -> None:
    """A reason is stored whole, up to a limit. Delete this and one of the check's sentences is cut
    short on the Install page, which is the page a person reads to find out what is wrong."""
    from brain.ops import acceptance_checks_queue as module

    sentences = [
        value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, str) and name != "PROBE_QUEUE"
        if name != "CHECK_ORDER"
    ]
    assert len(sentences) >= 9
    assert all(len(one) <= REASON_CHARS for one in sentences)


def test_the_class_the_probe_uses_is_allocated_no_slots_and_names_the_queue_the_check_expects() -> (
    None
):
    """**The property that makes the probe safe.** A worker of the install fetches the queues of the
    classes allocated slots, and a probe it fetched would be failed for want of a registered task.
    `human_interactive` is allocated none, and the check's own word for its queue is the class's
    word, not the function that derives it. Delete this and the probe moves to a class the install
    drains, or the check compares the derived queue with itself."""
    from brain.ops.acceptance_checks_queue import PROBE_QUEUE
    from brain.ops.queue import CONCURRENCY, PROBE_TRAFFIC_CLASS, queue_name_for, worker_shards

    assert CONCURRENCY[PROBE_TRAFFIC_CLASS] == 0
    assert PROBE_QUEUE == PROBE_TRAFFIC_CLASS.value == queue_name_for(PROBE_TRAFFIC_CLASS)
    assert PROBE_QUEUE not in {shard.queue for shard in worker_shards()}


def test_a_probe_task_must_carry_the_probe_prefix_or_nothing_is_enqueued() -> None:
    """The prefix is how what a check made is found and removed. Delete this and a probe can be
    given any name, including a real task's, and the clean-up by prefix leaves it behind or removes
    something that was not the check's."""
    from brain.ops.queue import QueueError, run_probe_job

    async def run(**_: Any) -> None:
        return None

    with pytest.raises(QueueError):
        asyncio.run(
            run_probe_job(
                "postgresql://unused.invalid/none",
                task="knowledge.ingest",
                run=run,
                args={},
                at=_now(),
            )
        )


def test_with_no_queue_connection_named_the_check_says_it_was_not_run() -> None:
    """A process that names no database for the queue cannot be asked about it. Delete this and a
    process with nothing to ask records a pass, or raises something a page cannot show."""
    from brain.ops import acceptance_checks_queue as module

    harness = SimpleNamespace(settings=settings_from({}), removes=lambda _: None)
    with pytest.raises(CheckNotRunError) as stopped:
        asyncio.run(module.probe_a_job(harness, fails=False))  # type: ignore[arg-type]
    assert stopped.value.reason == module.NO_QUEUE_CONNECTION_IS_NAMED


class _Harness:
    """What `probe_a_job` reads of a harness: settings, a run, a word and a place for an undoing."""

    run = "r1"

    def __init__(self, url: str = "postgresql://owner@db.invalid:5432/brain") -> None:
        self.settings = settings_from({"BRAIN_DATABASE_URL": url})
        self.undone: list[Any] = []

    def word(self) -> str:
        return "W"

    def removes(self, undo: Any) -> None:
        self.undone.append(undo)


def _probe_that(
    *,
    waiting: str = "todo",
    after: str = "succeeded",
    queue: str = "human_interactive",
    words: tuple[str, ...] = ("W",),
    raises: Exception | None = None,
) -> Any:
    """A runner that hands the task the words given and answers with the states given."""
    from brain.ops import queue as queue_module

    async def probe(url: str, *, task: str, run: Any, args: Any, at: Any, **_: Any) -> Any:
        if raises is not None:
            raise raises
        for word in words:
            try:
                await run(word=word)
            except RuntimeError:
                continue
        return queue_module.ProbedJob(
            job_id=1, queue=queue, status_waiting=waiting, status_after=after, kept_aside=False
        )

    return probe


def _stubbed(
    monkeypatch: pytest.MonkeyPatch,
    probe: Any,
    *,
    tables: bool | Exception = True,
    forget: Exception | None = None,
) -> None:
    from brain.ops import queue

    async def there(url: str) -> bool:
        if isinstance(tables, Exception):
            raise tables
        return tables

    async def forgot(url: str) -> None:
        if forget is not None:
            raise forget

    monkeypatch.setattr(queue, "probe_tables_are_there", there)
    monkeypatch.setattr(queue, "forget_probe_jobs", forgot)
    monkeypatch.setattr(queue, "run_probe_job", probe)


def _outcome(harness: _Harness, *, fails: bool = False) -> tuple[str, str]:
    from brain.ops import acceptance_checks_queue as module

    try:
        asyncio.run(module.probe_a_job(harness, fails=fails))  # type: ignore[arg-type]
    except CheckFailedError as stopped:
        return FAILED, stopped.reason
    except CheckNotRunError as stopped:
        return NOT_RUN, stopped.reason
    return PASSED, ""


def test_each_way_the_queue_cannot_be_asked_says_its_own_sentence_and_makes_no_undoing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The three ways in, and what each leaves.** A queue that refuses the connection is not run,
    one that does not answer is failed, a missing one is not run, and none of the three has
    registered an undoing for a probe it never made. Delete this and the refusal and the silence
    read the same on the Install page, or an undoing is registered for rows that do not exist."""
    from brain.ops import acceptance_checks_queue as module
    from brain.ops.queue import QueueError

    for tables, expected in (
        (QueueError("refused"), (NOT_RUN, module.THE_QUEUE_REFUSES_THIS_PROCESS_S_CONNECTION)),
        (OSError("down"), (FAILED, module.THE_QUEUE_DID_NOT_ANSWER)),
        (False, (NOT_RUN, module.NO_QUEUE_IS_INSTALLED_HERE)),
    ):
        harness = _Harness()
        _stubbed(monkeypatch, _probe_that(), tables=tables)
        assert _outcome(harness) == expected
        assert harness.undone == []


def test_a_queue_that_cannot_clear_the_last_run_s_leftovers_fails_but_leaves_an_undoing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The undoing is registered once the queue is known to be there, before the first thing is
    written. Delete this and a failure while clearing leaves nothing registered to clean up, or the
    check goes on to write over rows it could not clear."""
    from brain.ops import acceptance_checks_queue as module

    harness = _Harness()
    _stubbed(monkeypatch, _probe_that(), forget=OSError("down"))
    assert _outcome(harness) == (FAILED, module.THE_QUEUE_DID_NOT_ANSWER)
    assert len(harness.undone) == 1


def test_each_way_the_probe_can_go_wrong_says_its_own_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**One sentence per thing the queue can do wrong**, each produced by a runner answering what
    the real one would: a worker that runs out of time, a queue that refuses the job, a connection
    lost, a job that was not waiting or was on another queue, one nothing ran, one another worker
    took, a task run twice or with other words, and a state the queue never recorded. Delete this
    and two of these read the same, or one passes."""
    from brain.ops import acceptance_checks_queue as module
    from brain.ops.queue import QueueError

    cases: list[tuple[dict[str, Any], bool, tuple[str, str]]] = [
        ({"raises": TimeoutError()}, False, (FAILED, module.THE_WORKER_DID_NOT_FINISH)),
        ({"raises": QueueError("no")}, False, (FAILED, module.THE_QUEUE_REFUSED_THE_JOB)),
        ({"raises": OSError("down")}, False, (FAILED, module.THE_QUEUE_DID_NOT_ANSWER)),
        ({"waiting": "doing"}, False, (FAILED, module.THE_JOB_WAS_NOT_WAITING)),
        ({"queue": "elsewhere"}, False, (FAILED, module.THE_JOB_WAS_ON_ANOTHER_QUEUE)),
        (
            {"words": (), "after": "todo"},
            False,
            (FAILED, module.THE_WORKER_DID_NOT_RUN_THE_JOB),
        ),
        (
            {"words": (), "after": "failed"},
            False,
            (NOT_RUN, module.SOMETHING_ELSE_FETCHED_THE_PROBE),
        ),
        ({"words": ("X",)}, False, (FAILED, module.THE_JOB_RAN_WITH_OTHER_ARGUMENTS)),
        ({"words": ("W", "W")}, False, (FAILED, module.THE_JOB_RAN_WITH_OTHER_ARGUMENTS)),
        ({"after": "failed"}, False, (FAILED, module.THE_QUEUE_DID_NOT_RECORD_THE_RUN)),
        ({"after": "succeeded"}, True, (FAILED, module.A_FAILED_JOB_WAS_NOT_RECORDED_FAILED)),
    ]
    for kwargs, fails, expected in cases:
        _stubbed(monkeypatch, _probe_that(**kwargs))
        assert _outcome(_Harness(), fails=fails) == expected, kwargs


def test_a_job_that_ran_once_and_was_recorded_passes_whether_it_succeeded_or_was_to_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive sibling of the table above. Delete this and the table is satisfied by a check
    that refuses everything."""
    _stubbed(monkeypatch, _probe_that())
    assert _outcome(_Harness()) == (PASSED, "")
    _stubbed(monkeypatch, _probe_that(after="failed"))
    assert _outcome(_Harness(), fails=True) == (PASSED, "")


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


# ---------------------------------------------------------------------------- with a server
def run_checks(url: str, which: dict[str, Check] | None = None) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                tuple((which or mine()).values()),
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def queued(url: str) -> None:
    """The queue's tables, made the way the worker makes them on its first start."""
    from brain.ops.queue import install_queue

    install_queue(url, pool_max=3)


def held_by_the_queue(url: str) -> tuple[int, int, int]:
    """The probe's rows: jobs, events and set-aside rows, all of the queue's own connection."""
    from tests.fixtures.scratch_postgres import sql

    return (
        int(sql(url, "SELECT count(*) FROM ops.procrastinate_jobs")[0][0]),
        int(sql(url, "SELECT count(*) FROM ops.procrastinate_events")[0][0]),
        int(sql(url, "SELECT count(*) FROM ops.dead_letter")[0][0]),
    )


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_before_the_worker_has_made_the_queue_the_check_says_it_was_not_run() -> None:
    """The state of a database no worker has started on. Delete this and a missing queue records a
    pass, or fails an install that is only new."""
    from brain.ops.acceptance_checks_queue import NO_QUEUE_IS_INSTALLED_HERE

    with at_head("brain_acceptance_queue_absent") as url:
        assert run_checks(url) == {RUNS: (NOT_RUN, NO_QUEUE_IS_INSTALLED_HERE)}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_job_put_on_the_queue_is_run_once_and_nothing_is_left_behind() -> None:
    """**The positive case, against a real queue.** The check passes, the install's tables hold
    what they held, and the queue holds no job, event or set-aside row of the probe afterwards.
    Delete this and the check can be satisfied by a queue that fetches nothing, or leave a job
    behind on a client's install every time it runs."""
    with at_head("brain_acceptance_queue") as url:
        queued(url)
        before, queue_before = counts(url), held_by_the_queue(url)
        first = run_checks(url)
        second = run_checks(url)
        after, queue_after = counts(url), held_by_the_queue(url)

    assert first == {RUNS: (PASSED, "")}
    assert second == {RUNS: (PASSED, "")}
    assert after == before
    assert queue_before == queue_after == (0, 0, 0)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_rows_a_killed_run_left_are_removed_by_name_before_the_next() -> None:
    """A process killed between enqueueing and cleaning up leaves a probe job. Delete this and the
    leftovers of an interrupted run accumulate on the install, one for every kill."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_queue_left") as url:
        queued(url)
        sql(
            url,
            "INSERT INTO ops.procrastinate_jobs (queue_name, task_name, status, args)"
            " VALUES ('human_interactive', 'acceptance.probe.killed', 'failed', '{}'::jsonb)",
        )
        sql(
            url,
            "INSERT INTO ops.dead_letter (job_id, task, principal_id, traffic_class, reason,"
            " attempts, set_aside_at) VALUES ('900', 'acceptance.probe.killed', 'system',"
            " 'human_interactive', 'attempts_exhausted', 1, now())",
        )
        assert run_checks(url) == {RUNS: (PASSED, "")}
        assert held_by_the_queue(url) == (0, 0, 0)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_job_on_a_queue_the_class_does_not_derive_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The queue's name function returning another word: the job is enqueued, fetched and run
    consistently on the wrong queue. Delete this and the check passes a queue that routes by a
    name nobody chose."""
    from brain.ops import acceptance_checks_queue as module
    from brain.ops import queue

    monkeypatch.setattr(
        queue, "queue_name_for", lambda traffic_class, slot=queue.SlotClass.STANDARD: "elsewhere"
    )
    with at_head("brain_acceptance_queue_wrong") as url:
        queued(url)
        outcome = run_checks(url)
        left = held_by_the_queue(url)
    assert outcome == {RUNS: (FAILED, module.THE_JOB_WAS_ON_ANOTHER_QUEUE)}
    assert left == (0, 0, 0)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_worker_that_drains_another_queue_fails_the_check_and_the_probe_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker's figures naming a queue the job is not on: the job is left waiting. Delete this
    and the check passes a worker that fetches nothing, and a waiting job is left on the install
    after a failed run."""
    from dataclasses import replace

    from brain.ops import acceptance_checks_queue as module
    from brain.ops import queue

    real = queue.driver_options
    monkeypatch.setattr(
        queue, "driver_options", lambda shard: replace(real(shard), queues=("not_the_probe_queue",))
    )
    with at_head("brain_acceptance_queue_idle") as url:
        queued(url)
        outcome = run_checks(url)
        left = held_by_the_queue(url)
    assert outcome == {RUNS: (FAILED, module.THE_WORKER_DID_NOT_RUN_THE_JOB)}
    assert left == (0, 0, 0)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_queue_that_does_not_record_the_run_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The state read after the worker stops saying the job is still running. Delete this and the
    check passes a job that ran and was never recorded as done, which is a job run again."""
    from brain.ops import acceptance_checks_queue as module
    from brain.ops import queue

    real = queue._status_of
    calls: list[int] = []

    async def status(app: Any, job_id: int) -> str:
        calls.append(job_id)
        return await real(app, job_id) if len(calls) == 1 else "doing"

    monkeypatch.setattr(queue, "_status_of", status)
    with at_head("brain_acceptance_queue_unrecorded") as url:
        queued(url)
        outcome = run_checks(url)
    assert outcome == {RUNS: (FAILED, module.THE_QUEUE_DID_NOT_RECORD_THE_RUN)}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_job_another_worker_took_is_not_run_rather_than_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator who allocated slots to the probe's queue has a worker that fetches the job and
    fails it for want of the task. Delete this and that install is told its queue is broken when the
    check could not see its own worker."""
    from brain.ops import acceptance_checks_queue as module
    from brain.ops import queue

    async def taken(url: str, **_: Any) -> Any:
        return queue.ProbedJob(
            job_id=1,
            queue="human_interactive",
            status_waiting="todo",
            status_after="failed",
            kept_aside=False,
        )

    monkeypatch.setattr(queue, "run_probe_job", taken)
    with at_head("brain_acceptance_queue_taken") as url:
        queued(url)
        outcome = run_checks(url)
    assert outcome == {RUNS: (NOT_RUN, module.SOMETHING_ELSE_FETCHED_THE_PROBE)}


@pytest.mark.needs_db
def test_only_a_job_that_ended_failed_is_set_aside_and_the_set_aside_row_is_the_drivers() -> None:
    """**The probe against a real queue, below the check.** A task that returns is recorded
    succeeded and, given a reason to set it aside, is not; a task that raises is recorded failed
    and is, and the row holds the driver's own task, class and attempts, written by the call the
    recovery sweep makes. Delete this and a job that worked can be written into the dead-letter
    table by a reason that was meant for failures, or a failed one can be set aside with figures
    the caller supplied."""
    from brain.ops.queue import PROBE_TASK_PREFIX, forget_probe_jobs, run_probe_job
    from tests.fixtures.scratch_postgres import sql

    async def works(*, word: str) -> str:
        return word

    async def breaks(*, word: str) -> str:
        msg = "the probe task was asked to fail"
        raise RuntimeError(msg)

    async def both(url: str) -> tuple[Any, Any]:
        kept = await run_probe_job(
            url,
            task=f"{PROBE_TASK_PREFIX}ok",
            run=works,
            args={"word": "w"},
            at=_now(),
            set_aside_reason="attempts_exhausted",
        )
        failed = await run_probe_job(
            url,
            task=f"{PROBE_TASK_PREFIX}bad",
            run=breaks,
            args={"word": "w"},
            at=_now(),
            set_aside_reason="attempts_exhausted",
        )
        return kept, failed

    with at_head("brain_acceptance_queue_below") as url:
        queued(url)
        try:
            worked, failed = asyncio.run(both(url))
            rows = sql(
                url, "SELECT task, principal_id, traffic_class, attempts FROM ops.dead_letter"
            )
        finally:
            asyncio.run(forget_probe_jobs(url))
        left = held_by_the_queue(url)
    assert (worked.status_after, worked.kept_aside) == ("succeeded", False)
    assert (failed.status_after, failed.kept_aside) == ("failed", True)
    assert rows == [(f"{PROBE_TASK_PREFIX}bad", "system", "human_interactive", 1)]
    assert left == (0, 0, 0)
