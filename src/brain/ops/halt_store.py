"""`ops.halt` read and written in one place, and the one question every piece of work asks of it.

`brain.ops.halt` is the domain: what a halt is, what it covers, what a resume must carry and that a
state nobody could read is halted. `0136` gave it a table that outlives a process. Until this module
nothing wrote that table and nothing that starts work read it, so a halt could be declared on
nothing and would have refused nothing, which is the fifth lie that module names.

**One reader, one decider.** `read_state` is the only function that selects from `ops.halt`, and
`refusal_in` is the only function a path that starts work asks whether it may. The answer route
(web and every chat channel, through `brain.api_routes.answered_for`), the automation runner, the
connector sync and the live reads an answer makes each call one of them and none of them looks at a
row. A second reader is a second place to forget that unknown means halted, which is the mistake
that would be made in the one path nobody tested during an incident, and
`tests/unit/test_halt_store.py` reads the source to keep it to one. See
`ONE_READER_AND_ONE_DECIDER`.

**A configured database that cannot be read is halted; no database configured is not.** The
first is `brain.ops.halt.IF_WE_CANNOT_TELL_WHETHER_WE_ARE_HALTED_WE_ARE_HALTED`, the point. The
second is a process built with no `DATABASE_URL`: there is no table a halt could have been written
to, so "nothing is halted" is a fact about it rather than a guess, and failing it closed would
refuse every question on every process that was never meant to hold anything. The distinction is
`sessions is None`, which `brain.app.lifespan` sets only when no URL is configured, never when one
is configured and failing. See `NO_DATABASE_CONFIGURED_MEANS_NOTHING_COULD_HAVE_BEEN_HALTED`.

**Nothing is held in memory.** Every call reads the table, so a halt survives a restart because a
restart changes nothing this module keeps. A cached state would be faster and would be a halt that
a deploy undoes, which is that module's second lie.

**Who may stop what is the grant's scope matched against the halt, as a row.** A halt on one
department is written as a row naming that department, so a grant scoped to it matches and a grant
scoped to another does not; a halt on everything names no department, so only a grant with no
department in its scope may write one. See `A_SCOPED_STOP_STOPS_ONLY_WHAT_ITS_SCOPE_NAMES`. The
agent axis is refused here until something that starts an agent's work asks it, rather than stored
as a halt that refuses nothing (M13.7.3 is that work).

Task ids: M27.15.10, M27.15.15, M27.15.16, M27.15.2
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
import structlog
from sqlalchemy import Executable, Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.record import HaltAct
from brain.core.entitlement import EntitlementSet
from brain.ops.halt import (
    ENFORCED_AXES,
    HALT_CAPABILITY,
    NOTHING_HALTED,
    Halt,
    HaltError,
    HaltScope,
    HaltState,
    Resume,
    in_force,
)
from brain.tables.halt import HaltRow

log = structlog.get_logger()

#: Why there is one reader and one decider.
ONE_READER_AND_ONE_DECIDER: Final = (
    "Every path that starts work asks refusal_in, and only read_state selects from ops.halt. A "
    "second reader is a second place to forget that a state nobody could read is halted, and it "
    "would be forgotten in the path nobody exercised until the incident that needed it."
)

#: Why a process with no database is not halted, and a failing one is.
NO_DATABASE_CONFIGURED_MEANS_NOTHING_COULD_HAVE_BEEN_HALTED: Final = (
    "A process built with no database URL has no table a halt could have been written to, so "
    "nothing is halted there, as a fact rather than a guess. A process with a database it cannot "
    "read does not know whether somebody stopped it, and is halted until it does."
)

#: Why a scoped stop cannot stop everything, or somebody else's department.
A_SCOPED_STOP_STOPS_ONLY_WHAT_ITS_SCOPE_NAMES: Final = (
    "The stop capability is matched against the halt as a row: a department halt carries the "
    "department it names, a halt on everything carries none. A grant scoped to one department "
    "therefore matches a halt on that department and nothing wider, and a department administrator "
    "pressing stop stops their department and nobody else's work."
)

#: The reason a stop is stored with when the person stopping gave none. See the rule below.
STOPPED_FROM_THE_CONSOLE: Final = "Stopped from the console Stop control"

#: Why a stop needs no words and a resume does.
A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES: Final = (
    "Stopping is one press. When the person stopping gives no reason it is stored with the fixed "
    "sentence STOPPED_FROM_THE_CONSOLE, beside who pressed it and when, which the row already "
    "holds. Resuming is refused without a reason the person wrote, because whoever reads it next "
    "needs to know whether the cause was fixed."
)

#: What the actor's authority is written as, in `actor_role`.
INSTALL_ADMINISTRATOR: Final = "install administrator"
SCOPED_ADMINISTRATOR: Final = "scoped administrator"

_SET_PRINCIPAL: Final = sa.text("SELECT set_config('app.principal_id', :principal, true)")


class HaltRefusedError(Exception):
    """A stop or a resume this reader may not make, or one that would not work."""


@dataclass(frozen=True)
class Work:
    """One piece of work about to start, on the axes a halt can name. Empty means not known."""

    person: str = ""
    department: str = ""
    connector: str = ""


#: One row of `ops.halt` as the state reading needs it: scope, target, act, actor, reason, instant.
HaltActRow = tuple[str, str, str, str, str, datetime]


def halt_state(latest: Iterable[HaltActRow]) -> HaltState:
    """The halts in force, from the latest act per scope and target, or unknown.

    A latest act of `halt` is in force and a latest act of `resume` lifted it. A row that does not
    construct makes the whole state unknown rather than dropping that one halt: a halt the reader
    is not told of is the one that is refusing their work.
    """
    halts: list[Halt] = []
    for scope, target, act, actor, reason, at in latest:
        if act != HaltAct.HALT.value:
            continue
        try:
            halts.append(
                Halt(scope=HaltScope(scope), target=target, declared_by=actor, at=at, reason=reason)
            )
        except (HaltError, ValueError):
            return HaltState.unknown()
    return in_force(halts)


def latest_halt_acts() -> Select[tuple[str, str, str, str, str, datetime]]:
    """The latest act per scope and target in `ops.halt`, which is what is in force.

    `DISTINCT ON (scope, target)` over `ix_ops_halt_scope_target_at`, one row per thing ever
    stopped, so the read is the size of the stop history's distinct targets, not of its rows.
    """
    return (
        select(
            HaltRow.scope,
            HaltRow.target,
            HaltRow.act,
            HaltRow.actor_id,
            HaltRow.reason,
            HaltRow.at,
        )
        .order_by(HaltRow.scope, HaltRow.target, HaltRow.at.desc())
        .distinct(HaltRow.scope, HaltRow.target)
    )


async def read_state(sessions: async_sessionmaker[AsyncSession] | None) -> HaltState:
    """The halts in force; nothing halted with no database; unknown when one cannot be read."""
    if sessions is None:
        return NOTHING_HALTED
    try:
        async with sessions() as session:
            rows = (await session.execute(latest_halt_acts())).all()
    except SQLAlchemyError as failed:
        log.warning("halt state unreadable", error=type(failed).__name__)
        return HaltState.unknown()
    return halt_state(tuple(row) for row in rows)


def refusal_in(state: HaltState, work: Work) -> str:
    """What to tell the person whose work this is, or empty when it may start.

    `HaltState.refusal`, which names the scope and never the reason or who declared it, and which
    has its own sentence for a state nobody could read.
    """
    return state.refusal(person=work.person, department=work.department, connector=work.connector)


async def refusal_for(sessions: async_sessionmaker[AsyncSession] | None, work: Work) -> str:
    """`refusal_in` over a fresh read, for a path that starts one piece of work."""
    return refusal_in(await read_state(sessions), work)


def halt_row(scope: HaltScope, target: str) -> dict[str, str]:
    """A halt as the stop grant's scope is matched against it. See the rule above."""
    row = {"scope": scope.value, "target": target}
    if scope is HaltScope.DEPARTMENT:
        row["department"] = target
    return row


def may_act(
    reader: EntitlementSet, scope: HaltScope, target: str, now: datetime | None = None
) -> bool:
    """Whether this reader may stop or resume this scope and target."""
    where = reader.scope_for(HALT_CAPABILITY, now)
    return where is not None and where.matches(halt_row(scope, target))


def _authority(reader: EntitlementSet, now: datetime) -> str:
    where = reader.scope_for(HALT_CAPABILITY, now)
    return (
        INSTALL_ADMINISTRATOR
        if where is not None and where.is_unrestricted()
        else SCOPED_ADMINISTRATOR
    )


async def _write(
    sessions: async_sessionmaker[AsyncSession],
    *,
    act: HaltAct,
    scope: HaltScope,
    target: str,
    actor: str,
    role: str,
    reason: str,
    at: datetime,
    attributed: Sequence[Executable],
) -> str:
    async with sessions() as session, session.begin():
        await session.execute(_SET_PRINCIPAL, {"principal": actor})
        # Who, at what reach, in which request, for `0136`'s trigger to write into the ledger
        # entry. See `brain.attribution`.
        for statement in attributed:
            await session.execute(statement)
        written = await session.execute(
            sa.insert(HaltRow)
            .values(
                act=act.value,
                scope=scope.value,
                target=target,
                actor_id=actor,
                actor_role=role,
                reason=reason,
                at=at,
            )
            .returning(HaltRow.id)
        )
        return str(written.scalar_one())


async def stop(
    sessions: async_sessionmaker[AsyncSession],
    reader: EntitlementSet,
    *,
    scope: HaltScope,
    target: str,
    reason: str,
    now: datetime,
    attributed: Sequence[Executable] = (),
) -> Halt:
    """Stop one scope and target, as this reader, at once. Refused rather than stored as inert."""
    if scope not in ENFORCED_AXES:
        msg = f"nothing that starts work asks the {scope.value} axis yet, so it cannot be stopped"
        raise HaltRefusedError(msg)
    if not may_act(reader, scope, target, now):
        msg = "this reader may not stop that"
        raise HaltRefusedError(msg)
    try:
        halt = Halt(
            scope=scope,
            target=target.strip(),
            declared_by=reader.principal_id,
            at=now,
            reason=reason.strip() or STOPPED_FROM_THE_CONSOLE,
        )
    except HaltError as refused:
        raise HaltRefusedError(str(refused)) from refused
    await _write(
        sessions,
        act=HaltAct.HALT,
        scope=halt.scope,
        target=halt.target,
        actor=halt.declared_by,
        role=_authority(reader, now),
        reason=halt.reason,
        at=now,
        attributed=attributed,
    )
    return halt


async def resume(
    sessions: async_sessionmaker[AsyncSession],
    reader: EntitlementSet,
    *,
    scope: HaltScope,
    target: str,
    reason: str,
    now: datetime,
    attributed: Sequence[Executable] = (),
) -> Resume:
    """Lift the halt in force on this scope and target, with a written reason, naming whose it was.

    Refused when the state cannot be read, since there is then no halt that can be named, and
    when nothing is in force there, since a resume that lifts nothing would be a row saying
    somebody restarted a system nobody had stopped.
    """
    if not may_act(reader, scope, target, now):
        msg = "this reader may not resume that"
        raise HaltRefusedError(msg)
    state = await read_state(sessions)
    if not state.known:
        msg = "the halts in force cannot be read, so there is no halt to name in a resume"
        raise HaltRefusedError(msg)
    named = target.strip()
    found = [one for one in state.halts if (one.scope, one.target) == (scope, named)]
    if not found:
        msg = "nothing is stopped there"
        raise HaltRefusedError(msg)
    try:
        lifted = Resume(halt=found[0], by=reader.principal_id, at=now, reason=reason.strip())
    except HaltError as refused:
        raise HaltRefusedError(str(refused)) from refused
    await _write(
        sessions,
        act=HaltAct.RESUME,
        scope=scope,
        target=named,
        actor=reader.principal_id,
        role=_authority(reader, now),
        reason=lifted.reason,
        at=now,
        attributed=attributed,
    )
    return lifted
