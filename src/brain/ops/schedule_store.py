"""Where a control's run history lives, and the lock that stops two replicas running one.

`brain.ops.schedule` decides what is owed and holds no connection, deliberately, for the
reason `brain.ops.limits` gives about the same split: the case that is always wrong is the
boundary, and a boundary cannot be tested through a module that opens a socket.
`brain.ops.schedule_runner` holds the arithmetic that sits between them. This is the half that
talks to PostgreSQL, and it re-decides nothing: it reads the two clocks, takes a lock, writes
a row when a run starts and finishes it when the run returns.

**Nothing here decides whether a control may run.** `owed` and `due_now` answer that, from
values this module produced. A store that also decided would be a second implementation of a
rule with a written argument, and the copy that drifts is the one holding the connection.

**`pg_advisory_xact_lock`, tried rather than waited on, and both halves matter.**
Transaction-scoped because the application talks to PgBouncer in transaction mode, where
consecutive statements from one client land on different server connections: a session-level
lock is taken on one and every later statement runs somewhere else, so mutual exclusion is
gone and nothing says so. `brain.migrate`'s comment is the record of learning that the
expensive way. Tried rather than waited on because a replica that cannot take a control's lock
has learned that another replica is running it, and waiting would hold a connection for the
length of a sweep to discover there is nothing to do.

**The lock is held for the whole run and released by the transaction ending.** That is the
property worth stating, because it is what makes a process that dies mid-run safe: the
transaction is rolled back by the server, the lock goes, and the row it wrote keeps its
`started_at` with no `finished_at`, which is what `stalled_runs` reads. A lock released before
the work finished would let a second replica start the same sweep while the first was still
in it.

**A run that fails is recorded as having failed rather than not recorded.** The temptation is
to write the row only on success, which produces a table of things that worked and no evidence
of anything that did not. `A_CONTROL_THAT_FAILS_EVERY_RUN_LOOKS_LIKE_ONE_THAT_RUNS` in
`brain.tables.schedule` is the argument, and the two clocks in `schedule_runner` are what it
buys: dueness from the last attempt so a broken control is not retried every tick, lateness
from the last success so it does not report as healthy.

Rejected: one query returning both clocks as a pair per control. It reads as an optimisation
and it produces a row per control whichever clock is missing, so "never attempted" and "never
succeeded" arrive as nulls a caller has to tell apart by position. Two maps, each holding only
the controls that have the thing being asked about, is the shape `brain.ops.schedule.owed`
already takes: absent means never.

Rejected: recording the run before the lock is taken. A contended tick would leave a row for a
run that never happened, and "this control has thousands of attempts and no successes" would
then mean two different things.

Scope: SQL and nothing else. No clock is read here and no cadence is known here; every instant
is a parameter, for the reason the whole of `brain.ops.recovery` takes its observations that
way.

Task ids: M37.5.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.controls import Control
from brain.ops.schedule import schedulable
from brain.ops.schedule_runner import lock_id
from brain.tables.schedule import OUTCOMES, ControlRunRow

#: Why a failed run is written down rather than left out.
A_TABLE_OF_RUNS_THAT_WORKED_IS_NOT_A_HISTORY: Final = (
    "Writing the row only when a control succeeds produces a table of things that worked and "
    "no evidence of anything that did not, so a mechanism failing every hour for a week is "
    "indistinguishable from one nobody has run. The row is written when the run starts and "
    "finished when it returns, whichever way it returned."
)

#: Why the lock is tried rather than waited on.
A_REPLICA_THAT_CANNOT_TAKE_THE_LOCK_HAS_LEARNED_SOMETHING: Final = (
    "Two replicas tick together and both find a control owed. The one that cannot take the "
    "lock now knows the other is running it, which is the system working. Waiting would hold "
    "a connection for the length of a sweep to discover there is nothing to do, and treating "
    "it as an error would record an attempt that never happened."
)


class ScheduleStoreError(Exception):
    """Raised when a run record is asked for in a way the table cannot answer."""


async def last_attempts(
    session: AsyncSession, *, controls: Sequence[Control] | None = None
) -> dict[str, datetime]:
    """When each control was last started, for the controls that have ever been started.

    A control absent from the answer has never been attempted, which `brain.ops.schedule.owed`
    reads as a first run: owed now and not late. Absent rather than a null, so a caller cannot
    accidentally treat "never" as an old date.

    Started rather than finished, and the difference is the point: a run that began and did
    not return still happened, and counting it as an attempt is what stops the next tick
    starting the same control again while the first is in it. The lock stops that too; this
    stops it staying started for ever if the lock is somehow not held.
    """
    names = [one.name for one in schedulable(controls)]
    if not names:
        return {}
    rows = await session.execute(
        select(ControlRunRow.name, ControlRunRow.started_at)
        .where(ControlRunRow.name.in_(names))
        .order_by(ControlRunRow.name, ControlRunRow.started_at.desc())
        .distinct(ControlRunRow.name)
    )
    return {row.name: row.started_at for row in rows.all()}


async def last_successes(
    session: AsyncSession, *, controls: Sequence[Control] | None = None
) -> dict[str, datetime]:
    """When each control last finished successfully, for the ones that ever have.

    `ok` only. A refusal is not a success: a destructive control in report-only mode was
    reached and declined to act, so the thing it guards has not been done and the clock that
    measures how late it is must not move. That is the distinction `OUTCOMES` exists to make
    and folding `refused` in here would undo it.
    """
    names = [one.name for one in schedulable(controls)]
    if not names:
        return {}
    rows = await session.execute(
        select(ControlRunRow.name, ControlRunRow.finished_at)
        .where(ControlRunRow.name.in_(names), ControlRunRow.outcome == "ok")
        .order_by(ControlRunRow.name, ControlRunRow.finished_at.desc())
        .distinct(ControlRunRow.name)
    )
    return {row.name: row.finished_at for row in rows.all() if row.finished_at is not None}


async def unfinished(
    session: AsyncSession, *, controls: Sequence[Control] | None = None
) -> dict[str, datetime]:
    """The newest run of each control that started and recorded no finish.

    Feeds `brain.ops.schedule_runner.stalled_runs`, which decides which of them are old enough
    to be worth asking about. The two are separate because "did not return" is a fact this
    table holds and "has been that way too long" is a judgement with a threshold in it.
    """
    names = [one.name for one in schedulable(controls)]
    if not names:
        return {}
    rows = await session.execute(
        select(ControlRunRow.name, ControlRunRow.started_at)
        .where(ControlRunRow.name.in_(names), ControlRunRow.finished_at.is_(None))
        .order_by(ControlRunRow.name, ControlRunRow.started_at.desc())
        .distinct(ControlRunRow.name)
    )
    return {row.name: row.started_at for row in rows.all()}


async def take_the_lock(session: AsyncSession, name: str) -> bool:
    """Try to take this control's lock. True when it was taken, False when somebody holds it.

    `pg_try_advisory_xact_lock`, so it answers rather than blocks. See
    `A_REPLICA_THAT_CANNOT_TAKE_THE_LOCK_HAS_LEARNED_SOMETHING`.

    The lock lives for the transaction and is released when it ends, however it ends. A caller
    that takes it and then commits has released it, so the run has to happen inside the same
    transaction as the acquisition. That is a real constraint on callers and it is stated here
    rather than left to be discovered: it is why `record_start` does not commit.
    """
    namespace, key = lock_id(name)
    answer = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:namespace, :key)"),
        {"namespace": namespace, "key": key},
    )
    return bool(answer.scalar_one())


async def record_start(
    session: AsyncSession, name: str, *, at: datetime, report_only: bool
) -> uuid.UUID:
    """Write the row that says this control started, and answer with its identifier.

    Does not commit, and that is deliberate rather than an omission. The advisory lock is held
    by the transaction, so committing here would release it and let a second replica start the
    same control while this one was running it. The caller commits once, after the run.

    `report_only` is written now rather than inferred later, because the same control produces
    a refusal for two different reasons over its life and a reader six months on cannot
    reconstruct which mode it was in.
    """
    row = ControlRunRow(name=name, started_at=at, report_only=report_only)
    session.add(row)
    await session.flush()
    return row.id


async def record_finish(
    session: AsyncSession,
    run: uuid.UUID,
    *,
    at: datetime,
    outcome: str,
    detail: str = "",
) -> None:
    """Close the row this run opened, with what it ended as.

    Refuses an outcome outside the vocabulary before the database does, so the message names
    the vocabulary rather than the constraint. The check constraint is still there and is
    still the thing that holds: this is the message, not the rule.

    Refuses to close a row that is already closed. A second finish is either two callers
    holding one run identifier, which the lock is supposed to prevent, or a retry that would
    overwrite a failure with a success, and both are worth a refusal rather than an update.
    """
    if outcome not in OUTCOMES:
        msg = f"{outcome!r} is not how a run ends; the outcomes are {list(OUTCOMES)}"
        raise ScheduleStoreError(msg)
    # `CursorResult` rather than `Result`, which is what an UPDATE returns and is the only
    # one carrying `rowcount`. Cast rather than ignored, at a library boundary where proving
    # the structural match buys nothing: the statement is an update, so the result is a cursor.
    changed = cast(
        "CursorResult[Any]",
        await session.execute(
            update(ControlRunRow)
            .where(ControlRunRow.id == run, ControlRunRow.finished_at.is_(None))
            .values(finished_at=at, outcome=outcome, detail=detail or None)
        ),
    )
    if changed.rowcount != 1:
        msg = (
            f"run {run} is not open, so this is either a second finish for one run or a "
            "finish for a run that was never started. The lock exists to make the first "
            "impossible, so either way something is holding an identifier it should not"
        )
        raise ScheduleStoreError(msg)


async def clocks(
    session: AsyncSession, *, controls: Sequence[Control] | None = None
) -> tuple[Mapping[str, datetime], Mapping[str, datetime]]:
    """Both clocks in one call, in the order `due_now` takes them.

    A convenience over the two queries above rather than a third query, so there is no version
    of this that could answer differently from them. Callers that want one clock ask for one.
    """
    return (
        await last_attempts(session, controls=controls),
        await last_successes(session, controls=controls),
    )
