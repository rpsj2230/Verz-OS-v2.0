"""The install acceptance checks for the console pages around an agent, each through its own route.

Every check here calls the route function the page calls, as the reader the page serves: the
workspace route behind an agent's header, its connector strip and its channels; the capability
route behind the Profile's connector rows; the About route; the Prompts screen's three routes; one
source's page on the Connectors screen; a skill's figures on the Skills screen; and the roster the
People screen's Overview narrows to one steward. Each is handed an application holding the
install's own sessions and tool registry and nothing else, and a caller built from a reserved
principal's reach as the console admits it, so what the check reads is what the page would draw.

**A route, and not the functions under it, because the owner's rule for a console leaf is that the
page works on his install.** A page test in CI proves the page draws what it is sent; it says
nothing about whether the route sends it on this install's schema, with this install's grants. The
cheaper design, calling `connector_strip` or `about_flow` on values the check builds, was rejected
for the reason CLAUDE.md gives about a test that builds the value the function under test
produces: it would prove the consumer and call it the producer. See
`A_CONSOLE_LEAF_IS_PROVED_THROUGH_ITS_ROUTE`.

**Every row a check writes is in its rolled-back transaction, in acceptance_a or acceptance_b, for
an agent or a skill named for the run.** The one write that looks like more is a connection of a
shipped source for the Profile's projected fields and inherited health: it is written through
`StoredConnections.connect`, with no key kept anywhere, only when that source has no live
connection on the install, and it is rolled back with everything else. A source this install has
connected already is left alone and the check says it was not run, rather than reading the
install's real connection. See `A_CONNECTION_THE_INSTALL_HOLDS_IS_NEVER_BORROWED`.

**Nothing here asserts a figure the route computed against the same function computing it.** The
strip's overflow is held to the rows the route sent, the projected fields to grants the check gave,
the layout of each channel to the features its adapter declares, and a skill's runs to the rows the
check wrote, so a mutation of the producer moves one side and not the other.

Task ids: M27.11.11, M39.1.2.3, M39.2.1.1, M39.2.1.3, M39.2.1.5, M39.2.4.3, M27.11.16, M27.8.9
Task ids: M27.15.58, M27.15.9, M27.15.5
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_run import SET_UP_REACH, Harness
from brain.ops.acceptance_workspace import (
    _everywhere,
    _planes,
    _spend,
    installed_agent,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.tools.registry import ToolRegistry

#: Where this module's checks stand on the Install page: after the agent page's own module.
#: See `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 300

A, B = RESERVED_DEPARTMENTS

A_CONSOLE_LEAF_IS_PROVED_THROUGH_ITS_ROUTE: Final = (
    "Each check calls the route function its page calls, with the install's sessions and tool "
    "registry and a reserved reader's reach as the console admits it; a check over the functions "
    "under the route would prove the page's consumer and never what this install sends it."
)

A_CONNECTION_THE_INSTALL_HOLDS_IS_NEVER_BORROWED: Final = (
    "The check connects a shipped source only when the install has no live connection of it, "
    "keeps no key, and rolls the connection back; a source the install has connected is not "
    "read, and the check is not run rather than run over somebody's real connection."
)

#: The sources the projections check may connect, with settings their forms accept and that name
#: nothing real. A random tenant and portal each run, so no two runs describe the same account.
CONNECTABLE_HERE: Final = ("xero", "hubspot")

#: The instructions the Prompts check gives an agent, and gives back.
LOCAL_INSTRUCTIONS: Final = "Answers an install acceptance check, as edited on the Prompts screen."


# ------------------------------------------------------------------------ the console
def _console(h: Harness, registry: ToolRegistry | None = None) -> FastAPI:
    """The state the agent pages' routes read, over the check's transaction: sessions, settings
    and the install's own tool registry."""
    from fastapi import FastAPI

    from brain.ops.acceptance_checks_tools import _install_registry

    app = FastAPI()
    app.state.settings = h.settings
    app.state.db_sessions = h.sessions
    app.state.tools = registry if registry is not None else _install_registry(h)
    return app


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "GET"})


async def _asking(h: Harness, principal_id: str, *, strong: bool = False) -> Any:
    """What the routes read of a signed-in person: the principal, the reach as the console admits
    it, and the check's instant. `strong` is a session that passed the second factor, which the
    console asks of anybody exercising an administrative authority."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    assurance = Assurance.STRONG if strong else Assurance.AUTHENTICATED
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, assurance)
    # A cast at the routes' boundary: they read these three, and a `Caller` is minted only from
    # a verified token.
    return cast(
        Any,
        SimpleNamespace(caller=SimpleNamespace(principal=person), reach=reach, now=h.now),
    )


def _readers(*extra: str) -> tuple[tuple[str, Scope], ...]:
    """An agent page reader's grants: the Settings tab's read, every plane, and `extra`."""
    return _everywhere("read:agent", *_planes(), *extra)


def _entities_by_source(registry: ToolRegistry) -> dict[str, list[str]]:
    """Every source the registry reads rows from, with the entities its tools read, by name."""
    found: dict[str, list[str]] = {}
    for one in sorted(registry.definitions(), key=lambda d: d.name):
        if one.source and one.entity:
            found.setdefault(one.source, []).append(one.entity)
    return dict(sorted(found.items()))


# ------------------------------------------- 1. the header, and the views behind it
@check(
    leaves=("M27.11.11", "M39.1.2.3"),
    sentence=(
        "An agent's page is answered in one workspace answer that carries its header, with when "
        "it was created, its pinned skill and its spend over the period, and both the Dashboard's "
        "headline and the Profile, so moving between the views asks for nothing again."
    ),
)
async def the_agent_page_header_and_its_views_come_in_one_answer(h: Harness) -> None:
    from brain.agent_routes import agent_workspace
    from brain.tables.spend import SpendActualRow

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_readers("read:skill", "read:budget"))
    digest = hashlib.sha256(f"{h.word()} body".encode()).hexdigest()
    agent_id = await installed_agent(h, steward, skills=(("acceptance-header-skill", digest),))
    async with h.sessions() as session:
        await session.execute(
            insert(SpendActualRow),
            [_spend(agent_id, steward, 250, h.now - timedelta(hours=1), f"{h.trace_id}-s0")],
        )
        await session.commit()

    answer = await agent_workspace(_request(_console(h)), agent_id, await _asking(h, steward))
    # M27.11.11: the header's three facts, each from what this install holds.
    if answer.agent.created_at is None:
        raise CheckFailedError("the agent's header did not say when the agent was created")
    if [one.name for one in answer.skills] != ["acceptance-header-skill"]:
        raise CheckFailedError("the agent's header could not count the skill it is pinned to")
    if answer.headline is None or answer.headline.spend_minor != 250:
        raise CheckFailedError("the agent's header did not carry its spend over the period")
    # M39.1.2.3: the Dashboard's figures and the Profile in the same answer.
    if answer.profile is None:
        raise CheckFailedError("the workspace answer left out the Profile a settings reader opens")


# ------------------------------------------------------- 2. the connector strip
@check(
    leaves=("M39.2.1.1",),
    sentence=(
        "An agent naming every source this install reads shows its reader a row of the first few "
        "and a count of the rest, both over the sources that reader may be told of: a reader who "
        "may not read one source is shown a shorter row and a smaller count, and never its name."
    ),
)
async def an_agents_connector_strip_counts_only_what_its_reader_may_see(h: Harness) -> None:
    from brain.agent_routes import agent_workspace
    from brain.ops.acceptance_checks_tools import _install_registry

    await h.found_departments()
    registry = _install_registry(h)
    sources = _entities_by_source(registry)
    if len(sources) < 3:
        raise CheckFailedError("this install's registry reads rows from fewer than three sources")
    names = list(sources)
    withheld = names[-1]
    every = [f"read:{entity}" for entities in sources.values() for entity in entities]
    fewer = [f"read:{entity}" for name in names[:-1] for entity in sources[name]]
    wide, narrow = h.principal(A, "wide"), h.principal(A, "narrow")
    await h.person(wide, department=A, grants=_readers(*every))
    await h.person(narrow, department=A, grants=_readers(*fewer))
    agent_id = await installed_agent(h, wide, connectors=names)
    app = _console(h, registry)

    for reader, expected in ((wide, names), (narrow, names[:-1])):
        strip = (
            await agent_workspace(_request(app), agent_id, await _asking(h, reader))
        ).connectors
        rows = [one.source for one in strip.rows]
        shown = [one.source for one in strip.shown]
        if rows != expected:
            raise CheckFailedError(
                "the strip's rows were not the sources its reader may be told of"
            )
        if not shown or shown != rows[: len(shown)]:
            raise CheckFailedError("the strip's icons were not the head of its own rows")
        if strip.overflow != len(rows) - len(shown):
            raise CheckFailedError("the strip's count was not the rows left off the end of it")
        if reader == wide and not strip.overflow:
            raise CheckFailedError("the strip drew every source and counted none off the end")
        if reader == narrow and withheld in rows + shown:
            raise CheckFailedError("a source the reader may not be told of was named on the strip")


# ------------------------------------- 3. projected fields, and the source's own health
async def _connected_here(h: Harness) -> tuple[str, Any]:
    """A shipped source connected for the check alone, and its manifest. See
    `A_CONNECTION_THE_INSTALL_HOLDS_IS_NEVER_BORROWED`."""
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live

    for name in CONNECTABLE_HERE:
        if (await h.execute(live(name))).scalar_one_or_none() is not None:
            continue
        settings = (
            {"tenant_id": str(uuid.uuid4())}
            if name == "xero"
            else {"portal_id": str(10_000_000 + secrets.randbelow(89_999_999))}
        )
        manifest = manifest_for(name, settings)

        async def no_key() -> Any:
            return h.now

        await StoredConnections(h.sessions).connect(
            connector=name,
            settings=settings,
            digest=manifest_digest(manifest),
            actor=h.actor,
            trace_id=h.trace_id,
            ent_hash=SET_UP_REACH,
            keep_key=no_key,
        )
        return name, manifest
    raise CheckNotRunError(
        "every source this check can connect for itself is already connected on this install, "
        "and the check does not read a real connection"
    )


@check(
    leaves=("M39.2.1.3", "M39.2.1.5"),
    sentence=(
        "A connected source an agent may read shows on the agent's Profile the fields a run of it "
        "by this reader would return, which a field the agent's ceiling withholds is not among "
        "though the reader holds it, and the health the source's last attempt left, degraded."
    ),
)
async def an_agents_connector_shows_its_run_fields_and_its_health(h: Harness) -> None:
    from brain.agent_capability_routes import agent_capabilities
    from brain.connectors.contract import HealthState
    from brain.ops.acceptance_checks_tools import _install_registry
    from brain.ops.connector_store import live
    from brain.ops.connector_sync import Attempt, SyncOutcome
    from brain.ops.connector_sync_store import attempt_row

    await h.found_departments()
    name, manifest = await _connected_here(h)
    registry = _install_registry(h)
    entity = manifest.projections[0]
    first, second = (one.name for one in entity.fields[:2])
    tool = next(
        (
            one.name
            for one in registry.definitions()
            if one.source == name and one.entity == entity.entity
        ),
        None,
    )
    if tool is None:
        raise CheckFailedError("the install's registry has no tool reading the source it projects")
    finished = h.now - timedelta(minutes=5)
    connection_id = (await h.execute(live(name))).scalar_one()
    await h.execute(
        attempt_row(
            connection_id,
            Attempt(
                connector=name,
                started_at=finished - timedelta(minutes=1),
                finished_at=finished,
                outcome=SyncOutcome.FAILED,
                health=HealthState.DEGRADED,
                records=0,
                consecutive_failures=1,
                next_attempt_at=h.now + timedelta(hours=1),
                detail="An install acceptance check recorded this attempt as degraded.",
            ),
        )
    )
    held = (f"read:{entity.entity}", f"read:{entity.entity}.{first}")
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=_readers(*held, f"read:{entity.entity}.{second}"))
    agent_id = await installed_agent(
        h, reader, connectors=(name,), capabilities=held, allowed_tools=(tool,)
    )

    answer = await agent_capabilities(
        _request(_console(h, registry)), agent_id, await _asking(h, reader)
    )
    rows = [one for one in answer.connectors if one.source == name]
    if len(rows) != 1 or rows[0].presence != "attached":
        raise CheckFailedError("the source the agent may read was not on its Profile, attached")
    row = rows[0]
    # M39.2.1.3: the fields at E_run(caller, agent), not at the caller's reach alone.
    if f"{entity.entity}.{first}" not in row.projects:
        raise CheckFailedError("a field both the reader and the agent may read was not shown")
    if f"{entity.entity}.{second}" in row.projects:
        raise CheckFailedError("a field the agent's ceiling withholds was shown as projected")
    # M39.2.1.5: the health the source's own page shows, copied and never derived.
    if row.health != HealthState.DEGRADED.value or row.checked_at != finished:
        raise CheckFailedError("the source's degraded health did not reach the agent's Profile")


# ----------------------------------------------------- 4. a layout for each channel
@check(
    leaves=("M39.2.4.3",),
    sentence=(
        "Every surface an agent is offered on carries a layout chosen from what its adapter "
        "declares: cards where it can draw them, files beside a body where it can only attach, "
        "and plain text otherwise, with more than one layout among the surfaces this release ships."
    ),
)
async def each_channel_an_agent_is_offered_on_carries_its_own_layout(h: Harness) -> None:
    from brain.agent_routes import agent_workspace, declared_channels
    from brain.channels.adapter import Feature

    await h.found_departments()
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=_readers())
    agent_id = await installed_agent(h, reader)
    answer = await agent_workspace(_request(_console(h)), agent_id, await _asking(h, reader))
    declared = {one.channel.value: one for one in declared_channels()}

    if not answer.channels:
        raise CheckFailedError("an agent with no sensitive ceiling was offered on no surface")
    for one in answer.channels:
        surface = declared.get(one.channel)
        if surface is None:
            raise CheckFailedError("an agent was offered on a surface no adapter declares")
        expected = (
            "card"
            if surface.supports(Feature.CARDS)
            else "attachment"
            if surface.supports(Feature.ATTACHMENTS)
            else "plain"
        )
        if one.profile != expected:
            raise CheckFailedError("a surface's layout was not the one its adapter can carry")
    if len({one.profile for one in answer.channels}) < 2:
        raise CheckFailedError("every surface was given one layout whatever it can carry")


# ---------------------------------------------------------------- 5. the About flow
@check(
    leaves=("M27.11.16",),
    sentence=(
        "An agent's About is answered to anybody who may see the agent: a flow from what starts "
        "it to what it produces and what it will never do, naming its read tool and its rows to a "
        "reader of its settings, and to a reader of nothing else, no tool and no ceiling at all."
    ),
)
async def an_agents_about_flow_is_derived_from_its_setup(h: Harness) -> None:
    from brain.agent_about_routes import agent_about
    from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_SOURCE, LOCAL_TOOL

    await h.found_departments()
    steward, member = h.principal(A, "steward"), h.principal(A, "member")
    await h.person(steward, department=A, grants=_readers(LOCAL_READ))
    await h.person(member, department=A)
    agent_id = await installed_agent(
        h,
        steward,
        connectors=(LOCAL_SOURCE,),
        capabilities=(LOCAL_READ,),
        allowed_tools=(LOCAL_TOOL,),
    )
    app = _console(h)

    told = await agent_about(_request(app), agent_id, await _asking(h, steward))
    steps = [one.step for one in told.steps]
    if not steps or steps[0] != "starts" or steps[-1] != "result" or "reads" not in steps:
        raise CheckFailedError("the About flow did not run from what starts it to what it produces")
    lines = [line for step in told.steps for line in step.lines]
    if not any(one.kind == "read_tool" and one.tool == LOCAL_TOOL for one in lines):
        raise CheckFailedError("the About flow did not name the read tool the ceiling allows")
    if not any(one.kind == "rows" for one in lines):
        raise CheckFailedError("the About flow did not say which rows the agent reads")
    if not any(one.kind == "no_action" for one in lines):
        raise CheckFailedError("an agent with only a read tool was described as acting")
    if not any(one.every_agent for one in told.never) or len(told.never) < 2:
        raise CheckFailedError("the About flow did not say what this agent will never do")

    plain = await agent_about(_request(app), agent_id, await _asking(h, member))
    if not plain.steps:
        raise CheckFailedError("a reader who may see the agent was given no About flow")
    seen = [line for step in plain.steps for line in step.lines]
    if any(one.tool or one.kind == "rows" for one in seen):
        raise CheckFailedError("a reader of no settings was told the agent's tools or its rows")
    if [one.every_agent for one in plain.never] != [True]:
        raise CheckFailedError("a reader of no settings was told the agent's own ceiling")


# ------------------------------------------------------------- 6. the Prompts screen
@check(
    leaves=("M27.8.9",),
    sentence=(
        "An administrator holding the instructions authority sees an agent's instructions on the "
        "Prompts screen, is refused an edit while the feature is off, replaces them while it is "
        "on with the change recorded against the template, and gives them back; a reader without "
        "the authority is refused."
    ),
)
async def an_agents_instructions_are_edited_and_given_back(h: Harness) -> None:
    import structlog

    from brain.agents.template import TemplateError
    from brain.core.errors import Absent
    from brain.ops.acceptance_workspace import TEMPLATE_PERSONA
    from brain.ops.features import PROMPT_EDITING, switch
    from brain.prompt_routes import (
        INSTRUCTIONS_AUTHORITY,
        SWITCHED_OFF,
        InstructionsEdit,
        InstructionsGiveBack,
        edit_instructions,
        give_back_instructions,
        prompts,
    )
    from brain.tables.audit import attributed_to

    await h.found_departments()
    admin, reader = h.principal(A, "admin"), h.principal(A, "reader")
    await h.person(admin, department=A, grants=_readers(INSTRUCTIONS_AUTHORITY.value))
    await h.person(reader, department=A, grants=_readers())
    agent_id = await installed_agent(h, admin)
    app = _console(h)

    async def switched(on: bool) -> None:
        async with h.sessions() as session:
            for statement in attributed_to(
                actor_id=admin, ent_hash=SET_UP_REACH, trace_id=h.trace_id
            ):
                await session.execute(statement)
            await switch(session, PROMPT_EDITING, on=on, by=admin)
            await session.commit()

    async def shown() -> Any:
        page = await prompts(_request(app), await _asking(h, admin, strong=True))
        found = [one for one in page.agents if one.agent_id == agent_id]
        if len(found) != 1:
            raise CheckFailedError("the Prompts screen did not list the agent to its administrator")
        return found[0]

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await switched(False)
        before = await shown()
        if before.instructions != TEMPLATE_PERSONA or before.overridden or before.editable:
            raise CheckFailedError("the Prompts screen did not show the template's instructions")
        edit = InstructionsEdit(
            instructions=LOCAL_INSTRUCTIONS, expected_hash=before.effective_hash or ""
        )
        try:
            await edit_instructions(
                _request(app), agent_id, edit, await _asking(h, admin, strong=True)
            )
        except Absent as refused:
            if SWITCHED_OFF not in str(refused):
                raise CheckFailedError(
                    "an edit while the feature is off was refused unexplained"
                ) from None
        else:
            raise CheckFailedError("an agent's instructions were edited with the feature off")

        await switched(True)
        try:
            await edit_instructions(
                _request(app), agent_id, edit, await _asking(h, reader, strong=True)
            )
        except Absent:
            pass
        else:
            raise CheckFailedError("a reader without the authority edited an agent's instructions")
        try:
            edited = await edit_instructions(
                _request(app), agent_id, edit, await _asking(h, admin, strong=True)
            )
        except (Absent, TemplateError):
            raise CheckFailedError("the administrator could not edit the instructions") from None
        after = await shown()
        if (after.instructions, after.overridden, after.set_by) != (
            LOCAL_INSTRUCTIONS,
            True,
            admin,
        ):
            raise CheckFailedError("an edit was not in force and recorded against its template")
        if after.template_instructions != TEMPLATE_PERSONA:
            raise CheckFailedError("an edit replaced the template's own instructions")

        back = InstructionsGiveBack(expected_hash=edited.effective_hash or "")
        await give_back_instructions(
            _request(app), agent_id, back, await _asking(h, admin, strong=True)
        )
        given = await shown()
        if given.instructions != TEMPLATE_PERSONA or given.overridden:
            raise CheckFailedError("instructions given back were not the template's again")


# ---------------------------------------------------------- 7. one source's page
@check(
    leaves=("M27.15.58",),
    sentence=(
        "A shipped source's page lists an agent whose manifest names it and a skill whose tool it "
        "provides to a reader who may see both, and lists neither to a reader in another "
        "department who may read the Connectors screen but not that agent or the skill library."
    ),
)
async def a_source_page_lists_the_agents_and_skills_that_use_it(h: Harness) -> None:
    from brain.connector_routes import connector_source
    from brain.connectors.declaration import shipped
    from brain.console.skill_library import added, read_package
    from brain.ops.acceptance_checks_skills import _named, _skill_md, _store
    from brain.ops.acceptance_checks_tools import _install_registry

    await h.found_departments()
    registry = _install_registry(h)
    offered = sorted(
        (one.source, one.name)
        for one in registry.definitions()
        if one.source in shipped() and one.entity
    )
    if not offered:
        raise CheckFailedError("this install's registry has no tool from a shipped source")
    source, tool = offered[0]
    steward, outsider = h.principal(A, "steward"), h.principal(B, "outsider")
    await h.person(steward, department=A, grants=_readers("read:connector", "read:skill"))
    await h.person(outsider, department=B, grants=_everywhere("read:connector", *_planes()))
    agent_id = await installed_agent(h, steward, connectors=(source,))
    skill = _named(h, "uses_source")
    made = added(
        read_package("SKILL.md", _skill_md(skill, extra=(f"tools: [{tool}]",))),
        by=steward,
        at=h.now,
    )
    await _store(h, made, await h.reach(steward))
    app = _console(h, registry)

    page = await connector_source(_request(app), source, await _asking(h, steward))
    if agent_id not in {one.agent_id for one in page.agents}:
        raise CheckFailedError("the source's page did not list an agent whose manifest names it")
    if skill not in {one.name for one in page.skills}:
        raise CheckFailedError("the source's page did not list a skill whose tool it provides")
    elsewhere = await connector_source(_request(app), source, await _asking(h, outsider))
    if agent_id in {one.agent_id for one in elsewhere.agents}:
        raise CheckFailedError("an agent its reader may not see was listed on a source's page")
    if skill in {one.name for one in elsewhere.skills}:
        raise CheckFailedError("a skill was listed to a reader the library is not listed to")


# ---------------------------------------------------------- 8. a skill's runs
@check(
    leaves=("M27.15.9",),
    sentence=(
        "A skill pinned to one agent and invoked three times, twice by a member and once by an "
        "administrator, shows the administrator who reads usage three runs and the member two, "
        "counted from the invocations and never from the one agent it is assigned to."
    ),
)
async def a_skills_runs_are_counted_from_invocations_its_reader_may_see(h: Harness) -> None:
    from brain.console.skill_library import added, decided, read_package
    from brain.console_stats_routes import skill_stats
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _assign,
        _named,
        _screen,
        _skill_md,
        _store,
    )
    from brain.ops.skill_store import StoredSkills
    from brain.tables.skill_invocation import SkillInvocationRow

    await h.found_departments()
    admin = await _administrator(h, "skills")
    await h.grant(admin, "read:usage", Scope.unrestricted())
    member = h.principal(A, "member")
    await h.person(member, department=A, grants=_everywhere(*_screen()))
    reach = await h.reach(admin)
    name = _named(h, "counted")
    made = added(
        read_package(
            "SKILL.md", _skill_md(name, description="Use when a skill's runs are counted")
        ),
        by=admin,
        at=h.now,
    )
    await _store(h, made, reach)
    if not await StoredSkills(h.sessions).decide(
        decided(made, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an administrator could not approve a skill they imported")
    agent_id = await _an_agent(h, admin)
    await _assign(h, made.digest, agent_id, reach)
    async with h.sessions() as session:
        await session.execute(
            insert(SkillInvocationRow),
            [
                {
                    "agent_id": agent_id,
                    "skill_name": name,
                    "digest": made.digest,
                    "principal_id": who,
                    "trace_id": f"{h.trace_id}-k{n}",
                    "used_at": h.now - timedelta(hours=n + 1),
                }
                for n, who in enumerate((admin, member, member))
            ],
        )
        await session.commit()
    app = _console(h)

    for reader, runs in ((admin, 3), (member, 2)):
        figures = await skill_stats(_request(app), name, await _asking(h, reader))
        if figures.agents_pinned != 1:
            raise CheckFailedError("the skill's figures did not name the one agent pinned to it")
        if max(one.runs for one in figures.periods) != runs:
            raise CheckFailedError("a skill's runs were not the invocations its reader may count")


# ---------------------------------------------- 9. the agents a person stewards
@check(
    leaves=("M27.15.5",),
    sentence=(
        "A person's Overview lists the agents they steward, from the roster filtered to them, to "
        "a reader who may see those agents, and lists none to a reader in another department, so "
        "a leaver's agents are visible to the people who can take them on."
    ),
)
async def a_persons_overview_lists_the_agents_they_steward(h: Harness) -> None:
    from brain.agent_routes import agents
    from brain.api_routes import FILTER_SEPARATOR
    from brain.listing import ListAsked

    await h.found_departments()
    steward, other = h.principal(A, "steward"), h.principal(A, "other")
    colleague, outsider = h.principal(A, "colleague"), h.principal(B, "outsider")
    for one, where in ((steward, A), (other, A), (colleague, A), (outsider, B)):
        await h.person(one, department=where)
    stewarded = await installed_agent(h, steward)
    elsewhere = await installed_agent(h, other, suffix="_other")
    app = _console(h)
    filtered = ListAsked(filters=(f"owner_id{FILTER_SEPARATOR}{steward}",))

    listed = await agents(_request(app), await _asking(h, colleague), filtered)
    ids = [one.agent_id for one in listed.items]
    if stewarded not in ids:
        raise CheckFailedError("a person's Overview did not list the agent they steward")
    if elsewhere in ids:
        raise CheckFailedError("a person's Overview listed an agent somebody else stewards")
    hidden = await agents(_request(app), await _asking(h, outsider), filtered)
    if stewarded in [one.agent_id for one in hidden.items]:
        raise CheckFailedError("an agent was listed to a reader its audience does not cover")
