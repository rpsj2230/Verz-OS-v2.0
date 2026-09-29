"""The two recovery sweeps: what each moves, what each refuses to move, and what a person is shown.

The first half is the decision's sweep over stand-ins, where every verdict can be set up at once.
The second half is each sweep over what it runs against on an install: the driver's own tables,
installed by `install_queue` on a scratch PostgreSQL, and `ops.operation` as `0051` builds it.
Those skip without `DATABASE_URL`, as every `needs_db` test does, and CI always sets it.

Task ids: M23.3.1
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.knowledge.embed_queue import EMBED_TASK, REEMBED_TASK, embed_job, rebuild_job
from brain.knowledge.embedding import EmbeddingModel, RebuildCursor, RebuildPlan
from brain.knowledge.ingest_queue import INGEST_TASK, ingest_job
from brain.knowledge.search import EMBEDDING_DIMENSIONS
from brain.operation_routes import INTERRUPTED_PATH, interrupted_before
from brain.ops.idempotency import (
    IllegalTransitionError,
    Intent,
    Operation,
    OperationState,
    advance,
    operation_for,
)
from brain.ops.queue import MAX_REDRIVES, InFlight, Redrive, queue_app, tasks_of_ours
from brain.ops.recovery_run import (
    A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING,
    NAMED_IN_A_REPORT,
    NO_READ_BACK,
    NOT_YET_SWEPT,
    READ_BACK_ABSENT,
    READ_BACK_FOUND,
    READ_BACK_UNANSWERED,
    REDRIVE_BY_TASK,
    ReadBack,
    redrive_for,
    resume_side_effects,
    standing_of,
    sweep_queue,
)
from brain.ops.schedule_runner import queue_redrive, side_effect_resume
from brain.ops.worker import CONTROL_TASK, control_job, register_tasks
from brain.tables.operation import OperationRow
from tests.fixtures.console_http import console_client, get
from tests.fixtures.setting_rows import Result

#: A clock nobody's wall clock will reach, so nothing here goes off on a date. See CLAUDE.md.
NOW = datetime(2999, 1, 1, 12, tzinfo=UTC)
STALE = NOW - timedelta(minutes=10)
FRESH = NOW - timedelta(seconds=5)

DIRECT = "postgresql://brain@db:5432/brain"


def a_job(
    job_id: str,
    task: str,
    *,
    heartbeat: datetime = STALE,
    redrives: int = 0,
) -> InFlight:
    return InFlight(
        job_id=job_id,
        task=task,
        worker_id="w1",
        heartbeat_at=heartbeat,
        redrives=redrives,
        redrive=redrive_for(task),
    )


class Queue:
    """`QueueRows` over two lists, keeping every move it was asked to make."""

    def __init__(
        self,
        running: tuple[InFlight, ...] = (),
        failed: tuple[InFlight, ...] = (),
        *,
        moved_on: frozenset[str] = frozenset(),
    ) -> None:
        self._running = running
        self._failed = failed
        self.moved_on = moved_on
        self.moves: list[tuple[str, str]] = []

    async def running(self) -> tuple[InFlight, ...]:
        return self._running

    async def failed(self) -> tuple[InFlight, ...]:
        return self._failed

    async def run_again(self, job_id: str, now: datetime) -> bool:
        self.moves.append(("run_again", job_id))
        return job_id not in self.moved_on

    async def set_aside(self, job_id: str) -> bool:
        self.moves.append(("set_aside", job_id))
        return job_id not in self.moved_on


def swept(queue: Queue) -> Any:
    from tests.fixtures.scratch_postgres import run

    return run(lambda: sweep_queue(queue, now=NOW))


# ------------------------------------------------------------------------ the queue half
def test_an_orphaned_job_its_task_declares_safe_is_put_back_on_its_queue() -> None:
    """**The leaf's first half.** A worker died under an embedding batch, and the batch runs again.

    Delete this and the sweep could decide every orphan and move none, which is a scheduled
    control reporting a clean run while the work it exists for stays in running for ever."""
    queue = Queue(running=(a_job("11", EMBED_TASK),))

    sweep = swept(queue)

    assert queue.moves == [("run_again", "11")]
    assert sweep.ran_again == ("11",) and sweep.set_aside == ()


def test_an_orphaned_job_nobody_declared_safe_is_set_aside_and_never_run_again() -> None:
    """A control run whose worker died may have half-swept something, so a person decides.

    Delete this and a job whose second run is a second real act could be put back by the sweep
    written to prevent exactly that. The sibling above is the proof it still re-drives."""
    queue = Queue(running=(a_job("12", CONTROL_TASK), a_job("13", "brain.nobody.declared")))

    sweep = swept(queue)

    assert queue.moves == [("set_aside", "12"), ("set_aside", "13")]
    assert sweep.ran_again == ()


def test_a_job_whose_worker_is_still_heartbeating_is_left_alone() -> None:
    """Delete this and a sweep could put a live job back while its worker is still running it,
    which is the duplicate the re-drive safety exists to make harmless and never to cause."""
    queue = Queue(running=(a_job("14", EMBED_TASK, heartbeat=FRESH),))

    sweep = swept(queue)

    assert queue.moves == []
    assert "1 left as they were" in sweep.summary()


def test_a_job_put_back_as_often_as_the_cap_allows_is_set_aside_rather_than_run_again() -> None:
    """A batch that kills every worker it lands on is a poison pill, whatever its task declares.

    Delete this and one bad batch keeps a worker dying once a minute for ever."""
    queue = Queue(running=(a_job("15", EMBED_TASK, redrives=MAX_REDRIVES),))

    swept(queue)

    assert queue.moves == [("set_aside", "15")]


def test_a_failed_job_of_a_safe_task_under_the_cap_is_run_again() -> None:
    """**The leaf's word "retryable".** An upload whose store was down fails its job, and the job
    is put back rather than left failed with the upload never added.

    Delete this and a transient failure of a safe task is permanent, because no task is
    registered with a retry of the driver's."""
    queue = Queue(failed=(a_job("21", INGEST_TASK, redrives=1),))

    sweep = swept(queue)

    assert queue.moves == [("run_again", "21")]
    assert sweep.ran_again == ("21",)


def test_a_failed_job_the_decision_does_not_run_again_is_left_failed_and_never_set_aside() -> None:
    """Failed is already where a job that needs a person rests, and the driver refuses to finish a
    job that is not running. Delete this and every failed control run is finished again every
    minute, each attempt refused by the driver and counted as a move."""
    queue = Queue(
        failed=(a_job("22", CONTROL_TASK), a_job("23", EMBED_TASK, redrives=MAX_REDRIVES))
    )

    sweep = swept(queue)

    assert queue.moves == []
    assert "2 job(s) looked at: 0 re-driven, 0 set aside" in sweep.summary()


def test_a_job_that_moved_on_by_itself_is_counted_as_such_and_not_as_moved() -> None:
    """The driver refused the move because the row had already left the state it was read in.

    Delete this and a race lost between the read and the move is reported as a job re-driven or
    set aside, and the report a person reads says the sweep did something it did not."""
    queue = Queue(
        running=(a_job("31", EMBED_TASK), a_job("32", CONTROL_TASK)),
        moved_on=frozenset({"31", "32"}),
    )

    sweep = swept(queue)

    assert sweep.moved_on == ("31", "32")
    assert sweep.ran_again == () and sweep.set_aside == ()
    assert "2 had moved on by themselves" in sweep.summary()


def test_the_report_names_each_job_set_aside_by_id_and_task_and_says_how_many_more() -> None:
    """The queue's rows are refused to the application, so the report is the only place a person
    reads which job waits for them. Delete this and the report can say three were set aside and
    leave a person to find them in a table no screen shows."""
    many = tuple(a_job(str(100 + n), CONTROL_TASK) for n in range(NAMED_IN_A_REPORT + 2))
    report = swept(Queue(running=many)).summary()

    assert f"job 100 ({CONTROL_TASK})" in report
    assert f"job {100 + NAMED_IN_A_REPORT - 1} ({CONTROL_TASK})" in report
    assert f"job {100 + NAMED_IN_A_REPORT} " not in report
    assert report.endswith(" and 2 more")


def test_every_task_a_worker_registers_declares_what_running_twice_does() -> None:
    """And none is registered with a retry of the driver's, which is what makes the driver's own
    record of each put-back a count of re-drives rather than of retries.

    Delete this and a task added to the worker is unsafe by default and silently never re-driven,
    or a task given a driver retry has its retries counted against its re-drive cap."""
    app = queue_app(DIRECT, pool_max=5)
    register_tasks(app, database_url=DIRECT)
    ours = tasks_of_ours(app.tasks)

    assert set(ours) <= set(REDRIVE_BY_TASK)
    assert {CONTROL_TASK, EMBED_TASK, INGEST_TASK} <= set(ours)
    assert all(app.tasks[name].retry_strategy is None for name in ours)


def test_what_each_task_declares_here_is_what_its_own_job_builder_declares() -> None:
    """Delete this and the table here could call a task safe that its builder calls unsafe, and
    the sweep would run twice a job whose author said it must not be."""
    model = EmbeddingModel(name="m", revision="r1", dimensions=EMBEDDING_DIMENSIONS)
    other = EmbeddingModel(name="m", revision="r2", dimensions=EMBEDDING_DIMENSIONS)
    rebuilt = rebuild_job(
        plan=RebuildPlan(to_model=other, from_identity=model.identity),
        cursor=RebuildCursor(model=other, after_chunk_id="k.0001", chunks=2, batches=1),
    )
    assert rebuilt is not None
    built = (
        control_job("retention_sweep"),
        embed_job(document_id="d1", first_ordinal=0, last_ordinal=1, model=model, owner_id="u1"),
        rebuilt,
        ingest_job("t1"),
    )

    assert {one.task: one.redrive for one in built} == dict(REDRIVE_BY_TASK)
    assert CONTROL_TASK == "brain.controls.run"
    assert REEMBED_TASK in REDRIVE_BY_TASK


def test_a_task_nobody_declared_is_unsafe_and_a_declared_one_is_as_declared() -> None:
    """Delete this and the default could become safe, and an undeclared task would run twice."""
    assert redrive_for("brain.nobody.declared") is Redrive.UNSAFE
    assert redrive_for(EMBED_TASK) is Redrive.SAFE


# -------------------------------------------------------------------- the side-effect half
def an_operation(n: int, connector: str, state: OperationState) -> Operation:
    made = operation_for(
        Intent(principal_id="u_asker", intent_ref=f"turn_{n}"),
        connector=connector,
        tool=f"{connector}.send",
        arguments={"to": "somewhere"},
    )
    return dataclasses.replace(made, state=state)


class Records:
    """`OperationRecords` over a dictionary, moved only along the machine's edges."""

    def __init__(self, *held: tuple[Operation, datetime]) -> None:
        self.held = {one.key: (one, at) for one, at in held}
        self.moves: list[tuple[str, OperationState]] = []

    async def unsettled(self, before: datetime) -> tuple[Operation, ...]:
        states = {OperationState.SENT, OperationState.UNKNOWN, OperationState.VERIFYING}
        return tuple(one for one, at in self.held.values() if one.state in states and at < before)

    async def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        advance(frm, to)
        one, _ = self.held[key]
        if one.state is not frm:
            raise IllegalTransitionError(f"{key} was not {frm}")
        moved = dataclasses.replace(one, state=to)
        self.held[key] = (moved, NOW)
        self.moves.append((key, to))
        return moved

    def state_of(self, key: str) -> OperationState:
        return self.held[key][0].state


def resumed(records: Records, read_backs: Mapping[str, ReadBack]) -> Any:
    from tests.fixtures.scratch_postgres import run

    return run(lambda: resume_side_effects(records, now=NOW, read_backs=read_backs))


def test_a_side_effect_no_connector_can_answer_for_is_left_unknown_for_a_person() -> None:
    """**The leaf's second half, as it is on every install today.** A message whose delivery was
    never confirmed moves to unknown and waits for a person; nothing issues it again.

    Delete this and an interrupted operation could stay `SENT`, which reads as in flight, or be
    settled by a guess, and either way nobody is asked before a second real act."""
    sent = an_operation(1, "chat", OperationState.SENT)
    records = Records((sent, STALE))

    sweep = resumed(records, {})

    assert records.moves == [(sent.key, OperationState.UNKNOWN)]
    assert [one.learnt for one in sweep.settled] == [NO_READ_BACK]
    assert "1 waiting for a person" in sweep.summary()


def test_a_side_effect_is_read_back_only_after_its_record_says_it_is_being_verified() -> None:
    """And settled on what the source said: found is succeeded, absent is failed.

    Delete this and a read-back could be asked before the write-ahead, so a sweep that died
    mid-question leaves a record nobody can tell from one never asked."""
    found = an_operation(2, "ledger_a", OperationState.SENT)
    gone = an_operation(3, "ledger_b", OperationState.UNKNOWN)
    records = Records((found, STALE), (gone, STALE))
    seen: list[tuple[str, OperationState]] = []

    def asking(answer: str) -> Callable[[Operation], object]:
        def read_back(one: Operation) -> object:
            seen.append((one.key, records.state_of(one.key)))
            return answer

        return read_back

    sweep = resumed(records, {"ledger_a": asking("found"), "ledger_b": asking("absent")})

    assert seen == [(found.key, OperationState.VERIFYING), (gone.key, OperationState.VERIFYING)]
    assert records.state_of(found.key) is OperationState.SUCCEEDED
    assert records.state_of(gone.key) is OperationState.FAILED
    assert [one.learnt for one in sweep.settled] == [READ_BACK_FOUND, READ_BACK_ABSENT]


def test_a_read_back_that_raises_or_answers_rubbish_leaves_the_record_unknown() -> None:
    """Both have shown nothing about the source. Delete this and a connector answering `True`,
    or timing out, could settle a record, or leave it stuck in verifying where no list shows it
    as waiting for anybody."""
    rubbish = an_operation(4, "ledger_a", OperationState.SENT)
    broken = an_operation(5, "ledger_b", OperationState.SENT)
    unsure = an_operation(6, "ledger_c", OperationState.SENT)
    records = Records((rubbish, STALE), (broken, STALE), (unsure, STALE))

    def raises(_: Operation) -> object:
        raise TimeoutError

    sweep = resumed(
        records,
        {"ledger_a": lambda _: True, "ledger_b": raises, "ledger_c": lambda _: "inconclusive"},
    )

    assert [records.state_of(one.key) for one in (rubbish, broken, unsure)] == [
        OperationState.UNKNOWN
    ] * 3
    assert [one.learnt for one in sweep.settled] == [READ_BACK_UNANSWERED] * 3


def test_a_record_younger_than_a_live_worker_could_hold_it_is_not_read() -> None:
    """Delete this and the sweep races a live worker that is about to confirm its own call."""
    young = an_operation(7, "ledger_a", OperationState.SENT)
    records = Records((young, FRESH))

    sweep = resumed(records, {"ledger_a": lambda _: "found"})

    assert sweep.settled == () and records.moves == []


def test_what_a_person_is_told_follows_the_state_and_the_connector() -> None:
    """Delete this and a record the sweep has not reached yet reads as one it gave up on."""
    assert standing_of(an_operation(8, "chat", OperationState.UNKNOWN)) == NO_READ_BACK
    assert standing_of(an_operation(9, "chat", OperationState.SENT)) == NOT_YET_SWEPT
    asked = an_operation(10, "ledger_a", OperationState.UNKNOWN)
    assert standing_of(asked, {"ledger_a": lambda _: "found"}) == READ_BACK_UNANSWERED


# ------------------------------------------------------------------------ the runners
def test_both_sweeps_in_report_only_mode_move_nothing_and_open_nothing() -> None:
    """A URL that points nowhere is enough, because neither runner opens anything when told to
    report. Delete this and a runner could ignore the mode it was given."""
    nowhere = "postgresql://nobody@127.0.0.1:9/none"

    assert queue_redrive(NOW, True, nowhere).endswith(
        A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING
    )
    assert side_effect_resume(NOW, True, nowhere).endswith(
        A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING
    )


def test_the_queue_sweep_on_a_process_with_no_queue_says_so_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a worker started without its queue address fails the control every minute
    with a connection error nobody can act on, instead of saying what is missing."""
    monkeypatch.delenv("QUEUE_URL", raising=False)

    said = queue_redrive(NOW, False, "postgresql://nobody@127.0.0.1:9/none")

    assert said.startswith("no job was moved: QUEUE_URL is not set")


# ------------------------------------------------------------------------ the list
QUEUE_READ = screen("queue").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
GRANTS = {
    "u_wide": (
        Grant(capability=QUEUE_READ, scope=Scope.unrestricted()),
        Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
    ),
    "u_elsewhere": (
        Grant(capability=QUEUE_READ, scope=Scope.department("finance")),
        Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
    ),
    "u_none": (),
}


def a_row(n: int, state: OperationState, at: datetime) -> OperationRow:
    one = an_operation(n, "chat", state)
    return OperationRow(
        key=one.key,
        connector=one.connector,
        tool=one.tool,
        principal_id=one.principal_id,
        intent_ref=one.intent_ref,
        state=one.state.value,
        updated_at=at,
    )


@pytest.fixture
def listed() -> Iterator[tuple[Any, Any]]:
    with console_client(GRANTS) as (client, stub):
        rows = [a_row(1, OperationState.UNKNOWN, STALE), a_row(2, OperationState.SENT, STALE)]
        stub.answerers.append(
            lambda statement: Result(rows) if "ops.operation" in str(statement) else None
        )
        yield client, stub


def test_the_list_shows_a_reader_of_the_whole_queue_each_interrupted_action(
    listed: tuple[Any, Any],
) -> None:
    """With what the sweep learnt, and without who issued it or what for.

    Delete this and a record left unknown waits for a person who is never shown it."""
    client, _ = listed

    response = get(client, "u_wide", f"{API_PREFIX}{INTERRUPTED_PATH}")

    assert response.status_code == 200
    shown = response.json()["operations"]
    assert [(one["state"], one["standing"]) for one in shown] == [
        ("unknown", NO_READ_BACK),
        ("sent", NOT_YET_SWEPT),
    ]
    assert all(
        set(one) == {"key", "connector", "tool", "state", "since", "standing"} for one in shown
    )


def test_a_reader_who_may_not_see_the_sweep_is_answered_as_an_install_with_nothing_waiting(
    listed: tuple[Any, Any],
) -> None:
    """And the database is not asked. A department's reader of the queue is such a reader: the
    list is the whole install's.

    Delete this and the list could answer a reader outside the sweep's read with the install's
    interrupted actions, or with a refusal that says there is something to refuse."""
    client, stub = listed

    answers = [
        get(client, pid, f"{API_PREFIX}{INTERRUPTED_PATH}") for pid in ("u_none", "u_elsewhere")
    ]

    assert [one.status_code for one in answers] == [200, 200]
    assert [one.json()["operations"] for one in answers] == [[], []]
    assert not any("ops.operation" in str(one) for one in stub.statements)


def test_only_records_past_the_sweeps_grace_are_asked_for() -> None:
    """Delete this and the list puts an ordinary call a live worker is about to confirm in front
    of a person as though it had been interrupted."""
    assert interrupted_before(NOW) < NOW - timedelta(seconds=30)
    assert interrupted_before(NOW, timedelta(minutes=5)) == NOW - timedelta(minutes=5)


# ------------------------------------------------------------ against what an install runs
@pytest.mark.needs_db
def test_the_driver_queue_puts_back_the_safe_sets_aside_the_rest_and_counts_its_own_moves() -> None:
    """**The leaf against the driver's own tables.** A scratch database with the queue installed
    by `install_queue`, holding one job of every kind the sweep decides, swept through
    `DriverQueue` exactly as the worker's schedule sweeps it.

    Delete this and every test above could pass over stand-ins while the driver refused each move,
    counted re-drives from a column that counts something else, or read a failed job's live
    worker as a heartbeat."""
    import psycopg

    from brain.ops.queue import DriverQueue, install_queue
    from tests.fixtures.scratch_postgres import drop, fresh, run, sql

    database = "brain_recovery_queue"
    url = fresh(database)
    try:
        install_queue(url, pool_max=5)
        # The driver's triggers name its tables unqualified, as the driver's own connection sees
        # them through its search path, so these writes are made on a connection that sees the same.
        with psycopg.connect(url, autocommit=True, options="-c search_path=ops") as conn:

            def one(statement: str, *params: object) -> int:
                row = conn.execute(statement, params or None).fetchone()
                assert row is not None
                return int(row[0])

            dead = one(
                "INSERT INTO procrastinate_workers (last_heartbeat) "
                "VALUES (now() - interval '10 minutes') RETURNING id"
            )
            live = one("INSERT INTO procrastinate_workers DEFAULT VALUES RETURNING id")

            def job(task: str, *, failed: bool, worker: int) -> int:
                made = one(
                    "INSERT INTO procrastinate_jobs (queue_name, task_name, args) "
                    "VALUES ('recovery_check', %s, '{}') RETURNING id",
                    task,
                )
                conn.execute(
                    "UPDATE procrastinate_jobs SET status = 'doing', worker_id = %s WHERE id = %s",
                    (worker, made),
                )
                if failed:
                    conn.execute(
                        "UPDATE procrastinate_jobs SET status = 'failed' WHERE id = %s", (made,)
                    )
                return made

            orphan_safe = job(EMBED_TASK, failed=False, worker=dead)
            orphan_unsafe = job(CONTROL_TASK, failed=False, worker=dead)
            running = job(EMBED_TASK, failed=False, worker=live)
            failed_safe = job(INGEST_TASK, failed=True, worker=live)
            failed_unsafe = job(CONTROL_TASK, failed=True, worker=live)
            capped = job(INGEST_TASK, failed=True, worker=live)
            for _ in range(MAX_REDRIVES):
                conn.execute(
                    "INSERT INTO procrastinate_events (job_id, type) VALUES (%s, 'retried')",
                    (capped,),
                )

        async def sweep_and_race() -> tuple[Any, bool, bool]:
            app = queue_app(url, pool_max=2)
            async with app.open_async():
                queue = DriverQueue(app, REDRIVE_BY_TASK)
                done = await sweep_queue(queue, now=datetime.now(tz=UTC))
                again = await queue.run_again(str(orphan_safe), datetime.now(tz=UTC))
                aside = await queue.set_aside(str(failed_unsafe))
            return done, again, aside

        sweep, put_back_twice, set_aside_twice = run(sweep_and_race)
        status = dict(sql(url, "SELECT id, status::text FROM ops.procrastinate_jobs"))
        redrives = dict(
            sql(
                url,
                "SELECT job_id, count(*) FROM ops.procrastinate_events "
                "WHERE type IN ('deferred_for_retry', 'retried') GROUP BY job_id",
            )
        )
    finally:
        drop(database)

    assert status == {
        orphan_safe: "todo",
        orphan_unsafe: "failed",
        running: "doing",
        failed_safe: "todo",
        failed_unsafe: "failed",
        capped: "failed",
    }
    assert redrives == {orphan_safe: 1, failed_safe: 1, capped: MAX_REDRIVES}
    assert set(sweep.ran_again) == {str(orphan_safe), str(failed_safe)}
    assert sweep.set_aside == (str(orphan_unsafe),)
    assert (put_back_twice, set_aside_twice) == (False, False)


@pytest.mark.needs_db
def test_the_stored_operations_are_read_back_settled_and_listed_in_postgresql() -> None:
    """**The leaf against `ops.operation`.** Records claimed and won through the production ledger,
    left behind by a worker that stopped, swept through `StoredOperations` as the schedule sweeps
    them: the one a connector can answer for is settled, the one it cannot is left unknown and is
    what the list shows, read as the application's own role.

    Delete this and the conditional moves and the trigger `0051` installs could disagree with the
    stand-in above, and only the install would find out."""
    import psycopg

    from brain.ops.operation_store import PostgresOperationLedger
    from brain.ops.recovery_run import StoredOperations
    from brain.session import make_application_sessions, make_session_factory
    from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, run, sql

    database = "brain_recovery_operations"
    url = fresh(database)
    try:
        migrate(database, "stamp", "0050")
        migrate(database, "upgrade", "0051")
        answered = an_operation(11, "ledger_a", OperationState.PENDING)
        silent = an_operation(12, "chat", OperationState.PENDING)
        young = an_operation(13, "ledger_a", OperationState.PENDING)
        with psycopg.connect(url, autocommit=True) as conn:
            ledger = PostgresOperationLedger(conn)
            for one in (answered, silent, young):
                ledger.claim(one)
                ledger.win(one.key)
        sql(
            url,
            "UPDATE ops.operation SET updated_at = now() - interval '10 minutes' "
            "WHERE key = ANY(%s)",
            [answered.key, silent.key],
        )

        async def swept_and_listed() -> tuple[Any, Any]:
            owner = engine(url)
            try:
                now = datetime.now(tz=UTC)
                done = await resume_side_effects(
                    StoredOperations(make_session_factory(owner)),
                    now=now,
                    read_backs={"ledger_a": lambda _: "found"},
                )
                waiting = await StoredOperations(make_application_sessions(owner)).waiting(
                    interrupted_before(now)
                )
            finally:
                await owner.dispose()
            return done, waiting

        sweep, waiting = run(swept_and_listed)
        states = dict(sql(url, "SELECT key, state FROM ops.operation"))
    finally:
        drop(database)

    assert states == {answered.key: "succeeded", silent.key: "unknown", young.key: "sent"}
    assert {one.operation.key: one.learnt for one in sweep.settled} == {
        answered.key: READ_BACK_FOUND,
        silent.key: NO_READ_BACK,
    }
    assert [one.operation.key for one in waiting] == [silent.key]
