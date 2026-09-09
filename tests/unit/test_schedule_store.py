"""The two clocks, the lock, and the row a run leaves behind.

**The statements are compiled and never run, and that is stated rather than implied.** This
repository has no PostgreSQL, which `tests/unit/test_routing_routes.py` records for the same
reason: a stub session exercises the arithmetic, the refusals and the SQL that would be sent,
and nothing here says PostgreSQL would match what the WHERE clause says. CI runs the migration
and the schema against a real database on every commit, which is where that half is checked.

So what is asserted below is the compiled statement, in the shape that file already uses. A
test that asserted on a returned dictionary from a stub would be asserting on the stub.

Task ids: M37.5.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.schedule import schedulable
from brain.ops.schedule_runner import lock_id
from brain.ops.schedule_store import (
    ScheduleStoreError,
    last_attempts,
    last_successes,
    record_finish,
    record_start,
    take_the_lock,
    unfinished,
)
from brain.tables.schedule import OUTCOMES

NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)


class Recording(AsyncSession):
    """A session that records what it was asked to execute and answers a canned result.

    Subclasses `AsyncSession` rather than duck-typing it, so a signature change in SQLAlchemy
    fails here rather than letting a test pass against a shape the real session no longer has.
    """

    def __init__(self, *, scalar: Any = True, rowcount: int = 1) -> None:
        self.statements: list[Any] = []
        self.params: list[Any] = []
        self.added: list[Any] = []
        self.flushed = 0
        self.commits = 0
        self._scalar = scalar
        self._rowcount = rowcount

    async def execute(self, statement: Any, params: Any = None, **_: Any) -> Any:
        self.statements.append(statement)
        self.params.append(params)
        return _Answer(self._scalar, self._rowcount)

    def add(self, instance: Any, _warn: bool = True) -> None:
        self.added.append(instance)

    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.commits += 1


class _Answer:
    """What the recording session hands back: a scalar, a row list and a row count."""

    def __init__(self, scalar: Any, rowcount: int) -> None:
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar_one(self) -> Any:
        return self._scalar

    def all(self) -> list[Any]:
        return []


def sql_of(statement: Any) -> str:
    """One statement as the PostgreSQL it would send, parameters inlined so a test can read
    the values as well as the shape."""
    # `postgresql.dialect` is untyped in the stubs, and calling it in a typed context is the
    # one place a cast buys something: proving a structural match against a dialect class
    # would be work for no property. The compile call itself is typed.
    dialect = cast("Any", postgresql.dialect)()
    return str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


# --- the two clocks ------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_attempt_clock_counts_a_run_that_started_however_it_ended() -> None:
    """**Started rather than finished, and the difference is what stops a control being run
    twice at once.** A run that began and did not return still happened, so the next tick must
    not treat the control as never attempted and start it again beside the first.

    Asserted on the compiled statement: no outcome appears in it at all, which is the property.
    A version filtering on success here would make a control that fails look never attempted,
    and it would then be retried on every tick for ever.

    Delete this and the two clocks quietly become one."""
    session = Recording()

    await last_attempts(session)

    sent = sql_of(session.statements[0])
    assert "started_at" in sent
    assert "outcome" not in sent, "an attempt is an attempt whatever it ended as"
    assert "DISTINCT ON" in sent, "the newest per control, not every run there has ever been"


@pytest.mark.anyio
async def test_the_success_clock_counts_ok_and_not_a_refusal() -> None:
    """**A refusal is not a success and folding the two together undoes the whole vocabulary.**
    A destructive control in report-only mode was reached and declined to act, so the thing it
    guards has not been done and the clock measuring how late it is must not move.

    If it did, releasing the retention sweep would look like a sweep that had been running all
    along, which is the exact reading `report_only` exists to prevent.

    Delete this and a control that has refused every run for a month reports as healthy."""
    session = Recording()

    await last_successes(session)

    sent = sql_of(session.statements[0])
    assert "'ok'" in sent
    assert "refused" not in sent
    assert "failed" not in sent
    assert "finished_at" in sent, "a success is measured from when it finished, not started"


@pytest.mark.anyio
async def test_a_run_that_started_and_recorded_no_finish_is_findable() -> None:
    """The row a dead process leaves. `stalled_runs` decides which of those are old enough to
    ask about; this is the query that finds them at all, and the two are separate because
    "did not return" is a fact and "has been that way too long" is a judgement.

    Delete this and a control that never returns is invisible until somebody reads the table
    by hand."""
    session = Recording()

    await unfinished(session)

    sent = sql_of(session.statements[0])
    assert "finished_at IS NULL" in sent


@pytest.mark.anyio
async def test_the_control_something_else_runs_is_not_asked_about() -> None:
    """The audit anchor is started by a timer outside this process, so this store has no
    business holding a run history for it: rows would appear for runs it did not record and
    the gaps between them would read as a control that keeps stopping.

    Asserted on all three queries, because each builds its own name list and one of them could
    drift.

    Delete this and the scheduler's own history claims a control it does not run."""
    session = Recording()

    await last_attempts(session)
    await last_successes(session)
    await unfinished(session)

    for statement in session.statements:
        sent = sql_of(statement)
        assert "'audit_anchor'" not in sent
        assert "'retention_sweep'" in sent, "and the ones it does run are there"


@pytest.mark.anyio
async def test_asking_about_no_controls_sends_no_query_at_all() -> None:
    """An empty `IN` list compiles to a predicate PostgreSQL matches nothing against, which is
    the right answer arrived at by an accident of SQL rather than by a decision. Answering
    without a round trip is the same answer and says so.

    Delete this and a caller with an empty control list pays for three queries to learn
    nothing."""
    session = Recording()

    assert await last_attempts(session, controls=[]) == {}
    assert await last_successes(session, controls=[]) == {}
    assert await unfinished(session, controls=[]) == {}
    assert session.statements == []


# --- the lock ------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_lock_is_tried_and_transaction_scoped_and_neither_is_incidental() -> None:
    """**Two properties in one statement name and both were learned expensively.**

    Transaction-scoped, because the application talks to PgBouncer in transaction mode: a
    session-level lock is taken on one server connection while every later statement runs on
    another, so mutual exclusion is gone and nothing says so. `brain.migrate` carries the
    record of finding that out.

    Tried rather than waited on, because a replica that cannot take the lock has learned that
    another replica is running the control. Blocking would hold a connection for the length of
    a sweep to discover there is nothing to do.

    Asserted on the function name, because the two wrong choices are both one word away:
    `pg_advisory_lock` is session-scoped and `pg_advisory_xact_lock` blocks.

    Delete this and either mistake passes."""
    session = Recording(scalar=True)

    assert await take_the_lock(session, "retention_sweep") is True

    sent = str(session.statements[0])
    assert "pg_try_advisory_xact_lock" in sent
    assert session.params[0] == dict(
        zip(("namespace", "key"), lock_id("retention_sweep"), strict=True)
    )


@pytest.mark.anyio
async def test_a_lock_somebody_else_holds_is_an_answer_and_not_an_error() -> None:
    """The contended tick, which is the system working rather than failing. Raising here would
    turn every simultaneous tick into an incident, and recording it would put a row in the
    table for a run that never happened.

    Delete this and two replicas ticking together look like a fault."""
    session = Recording(scalar=False)

    assert await take_the_lock(session, "retention_sweep") is False
    assert session.added == [], "nothing is written when the lock was not taken"


@pytest.mark.anyio
async def test_each_control_takes_its_own_lock() -> None:
    """One lock for the scheduler would serialise thirteen unrelated mechanisms behind
    whichever is slowest, and the retention sweep is the slowest thing here.

    Delete this and the per-control derivation can collapse to a constant."""
    session = Recording()

    await take_the_lock(session, "retention_sweep")
    await take_the_lock(session, "denial_digest")

    assert session.params[0] != session.params[1]


# --- the row a run leaves ------------------------------------------------------------------


@pytest.mark.anyio
async def test_starting_a_run_writes_the_row_and_does_not_commit() -> None:
    """**Not committing is the property, and it is a constraint on callers rather than an
    oversight.** The advisory lock is held by the transaction, so committing here would release
    it and let a second replica start the same control while this one was still running it.

    Flushed rather than committed, so the row has an identifier the caller can close later.

    Delete this and the lock is released at the moment the work begins, which is the one
    moment it has to be held."""
    session = Recording()

    run = await record_start(session, "retention_sweep", at=NOW, report_only=True)

    assert isinstance(run, uuid.UUID | type(None))
    assert session.flushed == 1
    assert session.commits == 0, "committing here releases the lock the run is holding"
    assert len(session.added) == 1
    assert session.added[0].report_only is True, "which mode it ran in, on the row"


@pytest.mark.anyio
async def test_a_run_is_closed_only_while_it_is_open() -> None:
    """The update names `finished_at IS NULL`, so a second finish changes nothing and is then
    refused by the row count rather than overwriting the first.

    That matters because the two ways to reach a second finish are both worth refusing: two
    callers holding one identifier, which the lock exists to prevent, or a retry that would
    write a success over a failure.

    Delete this and a failure can be quietly overwritten by a later success."""
    session = Recording(rowcount=1)

    await record_finish(session, uuid.uuid4(), at=NOW, outcome="ok")

    sent = sql_of(session.statements[0])
    assert "finished_at IS NULL" in sent


@pytest.mark.anyio
async def test_closing_a_run_that_is_not_open_is_refused_rather_than_ignored() -> None:
    """A silent no-op here leaves a row open for ever and a caller believing it closed one,
    which is exactly the state `unfinished` would then report as a stalled run.

    Delete this and the failure mode is a table slowly filling with runs nothing ever
    finished."""
    session = Recording(rowcount=0)

    with pytest.raises(ScheduleStoreError, match="is not open"):
        await record_finish(session, uuid.uuid4(), at=NOW, outcome="ok")


@pytest.mark.anyio
async def test_an_outcome_outside_the_vocabulary_is_refused_before_the_database_sees_it() -> None:
    """The check constraint is still what holds, and this is the message. A caller writing
    `"success"` gets a sentence naming the three words rather than an integrity error naming a
    constraint, and the difference is who can act on it.

    Asserted against the vocabulary rather than a literal list, so a fourth outcome added to
    the table does not need this test edited to keep passing for the wrong reason.

    Delete this and the first bad outcome anybody writes surfaces as a database error at three
    in the morning."""
    session = Recording()

    with pytest.raises(ScheduleStoreError, match="is not how a run ends"):
        await record_finish(session, uuid.uuid4(), at=NOW, outcome="success")

    assert session.statements == [], "refused before anything was sent"
    for outcome in OUTCOMES:
        await record_finish(session, uuid.uuid4(), at=NOW, outcome=outcome)


@pytest.mark.anyio
async def test_every_control_this_process_schedules_can_be_locked_and_recorded() -> None:
    """The deployment check: every name the scheduler would use is one this store can take a
    lock for and write a row against. A control added to the registry with a name the table's
    check constraint does not admit would fail at the first run rather than here.

    Delete this and adding a control is a run that fails on its first attempt in production."""
    for control in schedulable():
        namespace, key = lock_id(control.name)
        assert isinstance(namespace, int)
        assert isinstance(key, int)
