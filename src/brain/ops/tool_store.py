"""The tool catalogue and its switches in the database, for the Tools screen and for every call.

`brain.tools.registry` holds the rules: which tools may exist, and that a switched-off tool is
refused at every call. This is the half with a connection, on the split `brain.ops.limits` keeps
from `brain.ops.limit_store`, so the rule can be tested at the boundary that matters without a
socket and the statements here can be tested without a rule.

**`SessionSwitchSource` is asked at every call to a governed registry's tools**, one statement per
call over `agent.tool_switch` joined to the caller's department in `auth.principal`. Per call and
not cached, because the owner's sentence is that after a switch "every call to it ... is refused",
and a copy refreshed on a timer is a window in which a switched-off tool still runs; a process
that holds a stale copy also cannot be told apart from one holding a fresh one. The statement is
a primary-key-sized read on a partial unique index, beside a tool call that reads rows anyway.

**A call nobody can place in a department meets every stop on the tool.** `stop_for` is handed
None when the handler was called with no reach, and the only safe reading of "we cannot tell
whose call this is" is that any department's stop might be theirs. See
`A_CALL_NOBODY_CAN_PLACE_MEETS_EVERY_STOP`.

**The catalogue row is written from the registry, and only from it.** `record_definition` is an
upsert of what the frozen registry says about one tool, called in the transaction that switches it
(the switch's foreign key needs the row) and by the application at start for every tool it
registered. Nothing else writes the table, so a row can never describe a tool differently from the
registration that produced it.

Task ids: M12.1.1, M12.4.3
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Select, Update, func, or_, select, update
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from brain.tables.identity import PrincipalRow
from brain.tables.tool_definition import ToolDefinitionRow, ToolSwitchRow
from brain.tools.registry import RegisteredTool, Switch, ToolRegistry

#: Why a call with no reach is refused by a department's stop.
A_CALL_NOBODY_CAN_PLACE_MEETS_EVERY_STOP: Final = (
    "A department's stop refuses the calls of that department's people, and a call handed no "
    "reach cannot be placed in any department. Treating it as nobody's would let it through "
    "every department's stop, which is the one reading under which a stop can be walked around "
    "by calling the handler differently, so it meets every stop on the tool instead."
)


@dataclass(frozen=True)
class LiveStop:
    """One live stop with the note it was switched off with, for the Tools screen."""

    switch: Switch
    off_reason: str | None


@dataclass(frozen=True)
class RecordedTool:
    """One tool the catalogue table holds, as the Tools screen draws a tool no longer registered."""

    name: str
    source: str
    entity: str
    description: str
    required_capability: str
    side_effect: str
    sensitive: bool
    sensitive_effect: str | None
    result_contract: str
    identity_mode: str


_STOP_COLUMNS: Final = (
    ToolSwitchRow.id,
    ToolSwitchRow.tool_name,
    ToolSwitchRow.department,
    ToolSwitchRow.switched_off_by,
    ToolSwitchRow.created_at,
    ToolSwitchRow.off_reason,
)


def _switch(row: Any) -> Switch:
    return Switch(
        switch_id=str(row[0]),
        tool=str(row[1]),
        department=None if row[2] is None else str(row[2]),
        switched_off_by=str(row[3]),
        switched_off_at=row[4],
    )


def widest(stops: Iterable[Switch]) -> Switch | None:
    """The stop a refusal names: the install's before any department's, then the oldest."""
    ordered = sorted(
        stops, key=lambda one: (one.department is not None, one.switched_off_at, one.switch_id)
    )
    return ordered[0] if ordered else None


# ----------------------------------------------------------------------- at every call
def stops_for_call(tool: str, principal_id: str | None) -> Select[Any]:
    """The live stops that refuse this call: the install's, and the caller's department's.

    The department is the caller's `primary_department`, which is the value a department
    administrator's grant is written against (`brain.gate.roster`'s reading of a person's
    department until membership is read). See `A_CALL_NOBODY_CAN_PLACE_MEETS_EVERY_STOP` for None.
    """
    live = select(*_STOP_COLUMNS).where(
        ToolSwitchRow.tool_name == tool, ToolSwitchRow.deleted_at.is_(None)
    )
    if principal_id is None:
        return live
    department = (
        select(PrincipalRow.primary_department)
        .where(PrincipalRow.id == principal_id)
        .scalar_subquery()
    )
    return live.where(
        or_(ToolSwitchRow.department.is_(None), ToolSwitchRow.department == department)
    )


class SessionSwitchSource:
    """`brain.tools.registry.SwitchSource` over `agent.tool_switch`, asked at every call."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def stop_for(self, tool: str, principal_id: str | None) -> Switch | None:
        async with self.sessions() as session:
            rows = (await session.execute(stops_for_call(tool, principal_id))).all()
        return widest(_switch(row) for row in rows)


# ------------------------------------------------------------------- the Tools screen
def live_stops_statement() -> Select[Any]:
    return select(*_STOP_COLUMNS).where(ToolSwitchRow.deleted_at.is_(None))


async def live_stops(session: AsyncSession) -> tuple[LiveStop, ...]:
    """Every live stop on the install. The route decides which of them a reader is shown."""
    rows = (await session.execute(live_stops_statement())).all()
    return tuple(
        LiveStop(switch=_switch(row), off_reason=None if row[5] is None else str(row[5]))
        for row in rows
    )


def recorded_statement() -> Select[Any]:
    return select(
        ToolDefinitionRow.name,
        ToolDefinitionRow.source,
        ToolDefinitionRow.entity,
        ToolDefinitionRow.description,
        ToolDefinitionRow.required_capability,
        ToolDefinitionRow.side_effect,
        ToolDefinitionRow.sensitive,
        ToolDefinitionRow.sensitive_effect,
        ToolDefinitionRow.result_contract,
        ToolDefinitionRow.identity_mode,
    ).order_by(ToolDefinitionRow.name)


async def recorded_tools(session: AsyncSession) -> tuple[RecordedTool, ...]:
    """Every tool the catalogue table holds, registered on this process or not."""
    rows = (await session.execute(recorded_statement())).all()
    return tuple(
        RecordedTool(
            name=str(row[0]),
            source=str(row[1]),
            entity=str(row[2]),
            description=str(row[3]),
            required_capability=str(row[4]),
            side_effect=str(row[5]),
            sensitive=bool(row[6]),
            sensitive_effect=None if row[7] is None else str(row[7]),
            result_contract=str(row[8]),
            identity_mode=str(row[9]),
        )
        for row in rows
    )


def departments_statement() -> Select[Any]:
    """The departments somebody live is in: the only values a department stop can refuse."""
    return (
        select(PrincipalRow.primary_department)
        .where(PrincipalRow.deleted_at.is_(None), PrincipalRow.primary_department.is_not(None))
        .distinct()
        .order_by(PrincipalRow.primary_department)
    )


async def departments_in_use(session: AsyncSession) -> tuple[str, ...]:
    rows = (await session.execute(departments_statement())).all()
    return tuple(str(row[0]) for row in rows)


# ------------------------------------------------------------------------- the writes
def definition_values(tool: RegisteredTool) -> dict[str, object]:
    """What the catalogue row says about one registered tool, read off the registration."""
    definition = tool.definition
    return {
        "name": definition.name,
        "source": tool.source,
        "entity": definition.entity,
        "description": definition.description,
        "required_capability": tool.capability.value,
        "side_effect": definition.side_effect.value,
        "sensitive": definition.declares_sensitive_effect(),
        "sensitive_effect": None if tool.sensitive_effect is None else tool.sensitive_effect.value,
        "result_contract": tool.result_contract.value,
        "identity_mode": definition.identity_mode.value,
    }


def record_definition_statement(tool: RegisteredTool) -> Insert:
    """The upsert: insert the row, or bring an existing one in line with the registration."""
    values = definition_values(tool)
    statement = insert(ToolDefinitionRow).values(**values)
    changed = {key: statement.excluded[key] for key in values if key != "name"}
    return statement.on_conflict_do_update(
        index_elements=[ToolDefinitionRow.name], set_={**changed, "updated_at": func.now()}
    )


async def record_definition(session: AsyncSession, tool: RegisteredTool) -> None:
    await session.execute(record_definition_statement(tool))


async def record_catalogue(
    sessions: async_sessionmaker[AsyncSession], registry: ToolRegistry
) -> int:
    """Write every registered tool's row, in one transaction, and say how many.

    Called by the application at start, after the registry is frozen. A failure here is the
    caller's to log and survive: the Tools screen reads the registry itself, and the one write
    that needs the row, a switch, records it in its own transaction first.
    """
    async with sessions() as session:
        for name in registry.names():
            await record_definition(session, registry.get(name))
        await session.commit()
    return len(registry)


def _at(department: str | None) -> Any:
    return (
        ToolSwitchRow.department.is_(None)
        if department is None
        else ToolSwitchRow.department == department
    )


def switch_off_statement(
    tool: str, department: str | None, *, by: str, reason: str | None
) -> ReturningInsert[tuple[uuid.UUID]]:
    """One stop, or nothing where the same stop is already live (the partial unique index)."""
    return (
        insert(ToolSwitchRow)
        .values(tool_name=tool, department=department, switched_off_by=by, off_reason=reason)
        .on_conflict_do_nothing()
        .returning(ToolSwitchRow.id)
    )


def switch_on_statement(tool: str, department: str | None, *, by: str, reason: str) -> Update:
    """Retire the live stop at this place, stamped at the statement's own instant.

    `statement_timestamp()`, the one value `0117`'s update policy admits, for the reason
    `tests/invariants/test_soft_delete_invariants.py` reads every `deleted_at` write for.
    """
    return (
        update(ToolSwitchRow)
        .where(
            ToolSwitchRow.tool_name == tool,
            _at(department),
            ToolSwitchRow.deleted_at.is_(None),
        )
        .values(
            deleted_at=func.statement_timestamp(),
            updated_at=func.now(),
            switched_on_by=by,
            on_reason=reason,
        )
        .returning(ToolSwitchRow.id)
    )


async def switch_off(
    session: AsyncSession, tool: str, department: str | None, *, by: str, reason: str | None
) -> bool:
    """Write the stop. False when the same stop was already live, which changes nothing."""
    written = await session.execute(switch_off_statement(tool, department, by=by, reason=reason))
    return bool(written.all())


async def switch_on(
    session: AsyncSession, tool: str, department: str | None, *, by: str, reason: str
) -> bool:
    """Retire the stop. False when there was none at this place, which changes nothing."""
    retired = await session.execute(switch_on_statement(tool, department, by=by, reason=reason))
    return bool(retired.all())


def stop_at(stops: Iterable[LiveStop], tool: str, department: str | None) -> LiveStop | None:
    """The live stop on this tool at this place, or None."""
    return next(
        (one for one in stops if one.switch.tool == tool and one.switch.department == department),
        None,
    )
