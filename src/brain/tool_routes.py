"""The Tools screen over HTTP: every tool, what it needs and what it does, and the switch.

`brain.tools.registry` decides which tools may exist and refuses a call to a switched-off one;
`brain.ops.tool_store` reads and writes the catalogue and the stops. This module is who may see
and throw a switch, and what the screen is told.

**One authority, `admin:tool`, and its scope is the whole of the department rule.** Held over
everything, it opens the screen and switches a tool off or back on for the install or for any
department somebody is in. Held within a department, it opens the same screen and stops or
restarts a tool for that department's people and nobody else's: `may_stop` is
`brain.console.govern._in_reach` at `{"department": d}`, the narrowing every console surface
uses, and `may_switch_install` is the same question at `NOWHERE`, which only an unrestricted
grant admits. There is no role parameter anywhere, for `brain.console.screens`' reason: a role
implies no capability, Super Admin included. See
`A_DEPARTMENT_STOPS_ITS_OWN_PEOPLE_AND_NOBODY_ELSE`.

**A department's reader is shown the install's switches and their own department's stops, and
never another department's.** A stop on another department is a fact about how somebody else's
work is governed, and the list of departments with stops is the filter-list disclosure
`brain.console.screens` names. The install's switch is shown to everybody who may open the
screen, because it governs their people's calls as much as anybody's.

**The catalogue is the registry this process built, and the table fills in what it no longer
builds.** A tool a release stopped registering keeps its catalogue row, and is listed as no
longer offered, so a stop on it is never a row the screen cannot draw. What each tool is said to
need and do is read off the registration through the same functions the gate uses:
`effect_class` for read, write or irreversible, and `leash_ceiling` for the highest rung a
leash entry on it keeps (M12.1.3).

**Stopping needs no reason and starting again needs one**, `brain.ops.halt`'s asymmetry and its
figure. Every change is a `setting` entry appended by `0117`'s trigger in the transaction that
writes it, and the route sets who, at what reach and for which request first, so the entry
names the request as well as the person.

Task ids: M12.1.1, M12.1.3, M12.1.4, M12.3.8, M12.4.3
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.agent_profile import rung_key
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.errors import Absent, Failed
from brain.core.scope import Op
from brain.ops.halt import MINIMUM_REASON
from brain.ops.tool_store import (
    LiveStop,
    RecordedTool,
    departments_in_use,
    live_stops,
    record_definition,
    recorded_tools,
    stop_at,
    switch_off,
    switch_on,
)
from brain.routing_routes import sessions_of
from brain.tables.audit import attributed_to
from brain.tools.registry import (
    ResultContract,
    SensitiveEffect,
    ToolRegistry,
    effect_class,
    leash_ceiling,
)

log = structlog.get_logger()

#: Opens the Tools screen and throws a switch: over everything for the install, within a
#: department for that department.
TOOL_AUTHORITY: Final = Capability(value="admin:tool")

#: The screen's name in a refusal. The console's own menu word, identical on every install.
TOOLS_SCREEN: Final = "tools"

#: Where the screen lives under the API prefix.
TOOLS_PATH: Final = "/tools"

#: Why a department's administrator can stop a tool only for their own department's people.
A_DEPARTMENT_STOPS_ITS_OWN_PEOPLE_AND_NOBODY_ELSE: Final = (
    "A department stop refuses the calls of that department's people, whoever or whatever makes "
    "them for them: an agent, a workflow, an automation. Who may write one is the scope of the "
    "writer's admin:tool grant, asked at the department the stop names, so a department "
    "administrator stops their own department and a stop anywhere else is refused before "
    "anything is read. The install's switch needs the grant over everything, and no department "
    "stop can lift it, because a stop is the only thing a switch can write."
)


def may_open(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds the authority anywhere, which is what opens the screen."""
    return reach.scope_for(TOOL_AUTHORITY, now) is not None


def may_switch_install(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may switch a tool off or on for the whole install."""
    return _in_reach(reach, TOOL_AUTHORITY, NOWHERE, now)


def may_stop(reach: EntitlementSet, department: str, now: datetime) -> bool:
    """Whether this reach may stop or restart a tool for this department's people."""
    return _in_reach(reach, TOOL_AUTHORITY, {"department": department}, now)


def departments_named(reach: EntitlementSet, now: datetime) -> tuple[str, ...]:
    """The departments this reader's own grant names, which is where a department admin acts."""
    scope = reach.scope_for(TOOL_AUTHORITY, now)
    if scope is None:
        return ()
    named: set[str] = set()
    for clause in scope.clauses:
        if clause.field != "department":
            continue
        if clause.op is Op.EQ and isinstance(clause.value, str):
            named.add(clause.value)
        if clause.op is Op.IN and isinstance(clause.value, tuple):
            named.update(clause.value)
    return tuple(sorted(one for one in named if may_stop(reach, one, now)))


def offered_departments(
    reach: EntitlementSet, in_use: Iterable[str], now: datetime
) -> tuple[str, ...]:
    """The departments this reader may stop a tool for: somebody's department, within reach.

    Intersected against the reader's reach and returning no count of what it dropped, which is
    `brain.console.screens.offerable`'s rule for any list a filter is drawn from.
    """
    candidates = {*in_use, *departments_named(reach, now)}
    return tuple(sorted(one for one in candidates if may_stop(reach, one, now)))


# ------------------------------------------------------------------------- the shapes
class ToolStopView(BaseModel):
    """One stop on one tool. `department` is null for the install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str | None
    switched_off_by: str
    switched_off_at: datetime
    #: The note it was switched off with, when there was one. Shown to administrators only.
    reason: str | None


class CatalogueToolView(BaseModel):
    """One tool: what it needs, what it does, and where it is stopped for this reader."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source: str
    description: str
    entity: str
    #: The capability a caller must hold for the tool to be offered at all (M12.1.2).
    capability: str
    #: `read`, `write` or `irreversible`: see `brain.tools.registry.EffectClass`.
    effect: str
    side_effect: str
    #: Which of the owner's sensitive effects the tool named, or null (M12.3.8).
    sensitive_effect: str | None
    #: `typed` or `opaque` (M12.1.4).
    result_contract: str
    identity_mode: str
    #: The highest rung a leash entry on this tool keeps (M12.1.3).
    leash_at_most: str
    #: Whether this process registers the tool, as against a row a release left behind.
    registered: bool
    off_for_install: ToolStopView | None
    #: The department stops this reader may see: their own department's, or every one.
    stopped_for: list[ToolStopView]


class ToolsPage(BaseModel):
    """Every tool, and what this reader may switch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tools: list[CatalogueToolView]
    may_switch_install: bool
    #: The departments this reader may stop a tool for.
    departments: list[str]
    #: The shortest reason starting a tool again takes.
    reason_to_switch_on: int = MINIMUM_REASON
    #: A switch can refuse a call and cannot allow one. See `A_SWITCH_ONLY_EVER_NARROWS`.
    a_switch_only_narrows: bool = True
    #: The person asking is told what any refusal tells them, and never which switch.
    the_asker_is_never_told: bool = True
    #: Every switch that changes anything is an entry in the audit trail.
    every_change_is_in_the_audit_trail: bool = True


class ToolSwitchAsked(BaseModel):
    """Switch one tool off or back on, for the install or for one department."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool
    department: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=2000)


class ToolSwitchAnswer(BaseModel):
    """The tool as it now stands, and whether this request changed anything."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: CatalogueToolView
    changed: bool


# ------------------------------------------------------------------------ the drawing
def _definition_of(recorded: RecordedTool) -> ToolDefinition:
    """A recorded row as the definition it was written from, so one function reads both."""
    return ToolDefinition(
        name=recorded.name,
        description=recorded.description,
        entity=recorded.entity,
        required_capability=recorded.required_capability,
        side_effect=SideEffect(recorded.side_effect),
        identity_mode=IdentityMode(recorded.identity_mode),
        sensitive=recorded.sensitive,
    )


def _stop_view(stop: LiveStop) -> ToolStopView:
    return ToolStopView(
        department=stop.switch.department,
        switched_off_by=stop.switch.switched_off_by,
        switched_off_at=stop.switch.switched_off_at,
        reason=stop.off_reason,
    )


def _stops_shown(
    name: str, stops: Sequence[LiveStop], reach: EntitlementSet, now: datetime
) -> tuple[ToolStopView | None, list[ToolStopView]]:
    """The install's stop on this tool, and the department stops this reader may see."""
    install = stop_at(stops, name, None)
    departments = [
        _stop_view(one)
        for one in stops
        if one.switch.tool == name
        and one.switch.department is not None
        and may_stop(reach, one.switch.department, now)
    ]
    departments.sort(key=lambda one: one.department or "")
    return (None if install is None else _stop_view(install)), departments


def tool_view(
    definition: ToolDefinition,
    *,
    capability: str,
    sensitive_effect: SensitiveEffect | str | None,
    result_contract: ResultContract | str,
    registered: bool,
    stops: Sequence[LiveStop],
    reach: EntitlementSet,
    now: datetime,
) -> CatalogueToolView:
    """One tool as the screen draws it, read through the functions the gate itself uses."""
    install, departments = _stops_shown(definition.name, stops, reach, now)
    return CatalogueToolView(
        name=definition.name,
        source=definition.name.split(".", 1)[0],
        description=definition.description,
        entity=definition.entity,
        capability=capability,
        effect=effect_class(definition).value,
        side_effect=definition.side_effect.value,
        sensitive_effect=None if sensitive_effect is None else str(sensitive_effect),
        result_contract=str(result_contract),
        identity_mode=definition.identity_mode.value,
        leash_at_most=rung_key(leash_ceiling(definition)),
        registered=registered,
        off_for_install=install,
        stopped_for=departments,
    )


def tool_views(
    registry: ToolRegistry,
    recorded: Sequence[RecordedTool],
    stops: Sequence[LiveStop],
    reach: EntitlementSet,
    now: datetime,
) -> list[CatalogueToolView]:
    """Every registered tool, then every recorded one this process no longer registers."""
    views = [
        tool_view(
            registry.get(name).definition,
            capability=registry.get(name).capability.value,
            sensitive_effect=registry.get(name).sensitive_effect,
            result_contract=registry.get(name).result_contract,
            registered=True,
            stops=stops,
            reach=reach,
            now=now,
        )
        for name in registry.names()
    ]
    views.extend(
        tool_view(
            _definition_of(one),
            capability=one.required_capability,
            sensitive_effect=one.sensitive_effect,
            result_contract=one.result_contract,
            registered=False,
            stops=stops,
            reach=reach,
            now=now,
        )
        for one in recorded
        if not registry.has(one.name)
    )
    return sorted(views, key=lambda one: one.name)


def tools_page(
    registry: ToolRegistry,
    recorded: Sequence[RecordedTool],
    stops: Sequence[LiveStop],
    in_use: Sequence[str],
    reach: EntitlementSet,
    now: datetime,
) -> ToolsPage:
    return ToolsPage(
        tools=tool_views(registry, recorded, stops, reach, now),
        may_switch_install=may_switch_install(reach, now),
        departments=list(offered_departments(reach, in_use, now)),
    )


# ------------------------------------------------------------------------- the wiring
def registry_of(request: Request) -> ToolRegistry:
    """The registry this process built, or an empty frozen one where none was built."""
    found = getattr(request.app.state, "tools", None)
    return found if isinstance(found, ToolRegistry) else ToolRegistry().freeze()


def _trace_id() -> str:
    """The request's trace, for the ledger entry `0117`'s trigger appends beside the switch."""
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable() -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {TOOLS_SCREEN} screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what to fix."""
    message = f"that tool was not switched: {reason}"
    return Absent(message, public_message=message)


def _place_refusal(reach: EntitlementSet, department: str | None, now: datetime) -> Absent | None:
    """Why this reader may not switch at this place, in words naming only their own reach."""
    if department is None and not may_switch_install(reach, now):
        return _refused_because(
            "switching a tool for the whole install needs the authority over everything; "
            "stop it for your own department instead"
        )
    if department is not None and not may_stop(reach, department, now):
        return _refused_because("you may stop or restart a tool for your own department only")
    return None


def _reasons(asked: ToolSwitchAsked) -> tuple[str | None, str | None]:
    """The reason to start a tool again, required, and the note to stop it with, optional.

    The first is set exactly when the tool is being started again, so the write below branches on
    which of the two it holds rather than on `on` and a reason separately.
    """
    reason = (asked.reason or "").strip() or None
    if not asked.on:
        return None, reason
    if reason is None or len(reason) < MINIMUM_REASON:
        raise _refused_because(
            f"switching a tool back on takes a reason of at least {MINIMUM_REASON} characters, "
            "because starting something somebody stopped is the decision that needs one"
        )
    return reason, None


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get(TOOLS_PATH, response_model=ToolsPage, responses=COMMON_RESPONSES)
async def tools(request: Request, asked: Asked) -> ToolsPage:
    """Every tool, what it needs and does, and the stops this reader may see."""
    if not may_open(asked.reach, asked.now):
        log.info("tools screen not answerable")
        raise _not_answerable()
    registry = registry_of(request)
    factory = sessions_of(request)
    if factory is None:
        return tools_page(registry, (), (), (), asked.reach, asked.now)
    async with factory() as session:
        stops = await live_stops(session)
        recorded = await recorded_tools(session)
        in_use = await departments_in_use(session)
    return tools_page(registry, recorded, stops, in_use, asked.reach, asked.now)


@router.post(
    f"{TOOLS_PATH}/{{name}}/switch", response_model=ToolSwitchAnswer, responses=COMMON_RESPONSES
)
async def switch_tool(
    request: Request, name: str, body: ToolSwitchAsked, asked: Asked
) -> ToolSwitchAnswer:
    """Switch one tool off or back on, for the install or one department, and say what now holds.

    The authority first, then the tool, then the place, then the reason, then the write, and the
    order is the property: a caller without the authority learns nothing about which tools exist,
    and a caller with it is told what to fix before anything is written.
    """
    if not may_open(asked.reach, asked.now):
        log.info("tool switch refused")
        raise _not_answerable()
    registry = registry_of(request)
    if not registry.has(name):
        raise _refused_because(f"{name!r} is not a tool this install registers")
    department = None if body.department is None else (body.department.strip() or None)
    if body.department is not None and department is None:
        raise _refused_because("a department stop names the department")
    refusal = _place_refusal(asked.reach, department, asked.now)
    if refusal is not None:
        raise refusal
    on_reason, off_reason = _reasons(body)

    async with _require_sessions(request)() as session:
        in_use = await departments_in_use(session)
        if department is not None and department not in offered_departments(
            asked.reach, in_use, asked.now
        ):
            raise _refused_because(
                "nobody on this install is in that department, so a stop there would stop nobody"
            )
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        ):
            await session.execute(statement)
        # The catalogue row first: the stop's foreign key needs it, and it is written from the
        # registration, so the row says what the gate will apply.
        await record_definition(session, registry.get(name))
        if on_reason is not None:
            changed = await switch_on(
                session, name, department, by=asked.caller.principal.id, reason=on_reason
            )
        else:
            changed = await switch_off(
                session, name, department, by=asked.caller.principal.id, reason=off_reason
            )
        stops = await live_stops(session)
        await session.commit()
    log.info(
        "tool switched",
        tool=name,
        control="install" if department is None else "department",
        outcome="on" if body.on else "off",
    )
    registered = registry.get(name)
    return ToolSwitchAnswer(
        tool=tool_view(
            registered.definition,
            capability=registered.capability.value,
            sensitive_effect=registered.sensitive_effect,
            result_contract=registered.result_contract,
            registered=True,
            stops=stops,
            reach=asked.reach,
            now=asked.now,
        ),
        changed=changed,
    )
