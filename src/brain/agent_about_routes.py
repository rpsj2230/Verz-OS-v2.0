"""One agent's About tab over HTTP: how the agent works, as a flow derived for one reader.

`brain.console.agent_about` writes the flow from the agent's setup and nothing else. This module
decides what each reader hands it, and adds no rule about who may see an agent or what they may
read about one: the audience is `brain.agent_routes`' check, the configuration travels with the
Settings tab as it does on the workspace, and the automations are the Automations tab's.

**A sibling of the workspace rather than more of it, for two reasons measured on 2026-09-17.**
The flow's first step names the agent's running automations, and those are stored by
`brain.ops.automation_run_store` and wired by `brain.automation_schedule_routes`, both of which
import `brain.agent_routes`, so the workspace module cannot read them without a cycle; an import
inside the handler would hide the cycle rather than remove it. And the workspace is read by all
three of the page's tabs, while the automations read is the About tab's alone, so on the
workspace it would be paid by every Dashboard and Profile for a step they never draw.
`docs/admin-console-architecture.md` 4.1a gives the About tab its own address,
`/agents/{id}/about`, and this is the route behind it. See
`THE_ABOUT_FLOW_IS_ITS_OWN_ROUTE_BECAUSE_ITS_AUTOMATIONS_ARE_DOWNSTREAM_OF_THE_WORKSPACE`.

**The same audience check, in the same order, and the same one 404.** `_visible_record` is the
workspace's own, so an agent this caller may not see and an agent that does not exist are one
answer here too, and nothing about a hidden agent is read: the install after the audience, and
the automations after both and only for a reader of the Automations tab.

**Each input is narrowed exactly as the block it comes from is narrowed on the workspace.** The
channels are `brain.agent_routes.offered_surfaces` at `E_run(caller, agent)`; the sources are
`reader_connector_rows`, at the sources `reachable_sources` lets this reader be told about; the
setup is handed in only where `may_read_settings` holds; the automations only where
`may_open_gallery` holds, filtered by `brain.console.agent_automations.automations_for`. A reader
therefore reads nothing in the flow that the workspace and the Automations tab would not already
show them. See `THE_FLOW_IS_NARROWED_BLOCK_BY_BLOCK_AS_THE_WORKSPACE_IS`.

**No overview.** `identity.overview`, the paragraph a person writes for this tab, is not a
manifest path. Adding one changes the digest every stored template is signed over and reaches a
model through `brain.builder.coauthor`, so it was measured on 2026-09-17 and left for a package
of its own; the tab has the summary and the derived flow until then.

It serves the About tab of M27.11.16, and claims no leaf: that leaf closes when the page exists.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_routes import (
    Install,
    _require_session_factory,
    _tool_registry,
    _visible_record,
    install_for,
    install_of,
    leash_of,
    may_read_settings,
    offered_surfaces,
    reader_connector_rows,
    registered_tools,
)
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_schedule_routes import schedules_of
from brain.console.agent_about import AboutFlow, Offered, Scheduled, Setup, about_flow
from brain.console.agent_automations import automations_for
from brain.console.agent_profile import rung_key
from brain.console.agent_tabs import rendering_profile
from brain.console.automation_gallery import may_open_gallery, template_by_id
from brain.tools.registry import ToolRegistry

#: The address, under `API_PREFIX`.
ABOUT_PATH: Final = "/agents/{agent_id}/about"

#: Why the flow is not a block of the workspace.
THE_ABOUT_FLOW_IS_ITS_OWN_ROUTE_BECAUSE_ITS_AUTOMATIONS_ARE_DOWNSTREAM_OF_THE_WORKSPACE: Final = (
    "The flow names the agent's running automations, which are stored and wired by modules that "
    "import brain.agent_routes, so the workspace cannot read them without a cycle. And the "
    "workspace is read by every tab of the agent page while the automations are drawn only on "
    "About, so the read belongs to the route behind the About tab's own address."
)

#: Why the flow's inputs are the workspace's blocks, each at its own gate.
THE_FLOW_IS_NARROWED_BLOCK_BY_BLOCK_AS_THE_WORKSPACE_IS: Final = (
    "The flow is sentences about the channels, the sources, the configuration and the "
    "automations, so each is narrowed where it is narrowed on the workspace and the Automations "
    "tab: channels at the run's reach, sources at the sources the reader may be told about, "
    "configuration with the Settings tab, automations with the Automations tab and the reader's "
    "own visibility of each. The flow cannot say more than those blocks already show."
)


# ------------------------------------------------------------------------ the shapes
class FlowLineView(BaseModel):
    """One line of the flow, as `brain.console.agent_about.FlowLine` carries it.

    `rungs` are the leash's words for a rung, lowest first. `leash_entry` is whether a leash row
    names the action's target, so the page links it to that row or to the leash card.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    text: str
    channels: list[str] = []
    automation_id: str | None = None
    source: str | None = None
    tool: str | None = None
    effect: str | None = None
    rungs: list[str] = []
    leash_entry: bool | None = None


class FlowStepView(BaseModel):
    """One step with something in it. Numbered from one without a gap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    step: str
    title: str
    lines: list[FlowLineView]


class NeverView(BaseModel):
    """One thing the agent will never do, and whether it is true of every agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    every_agent: bool


class AboutView(BaseModel):
    """One agent's About tab for this reader. No field here counts what a step left out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    #: `identity.summary` of the effective manifest, as the workspace header sends it.
    summary: str | None = None
    steps: list[FlowStepView]
    never: list[NeverView]


# ------------------------------------------------------------------------ the decisions
def flow_view(agent_id: str, summary: str | None, flow: AboutFlow) -> AboutView:
    """The flow under the wire's names, value for value."""
    return AboutView(
        agent_id=agent_id,
        summary=summary,
        steps=[
            FlowStepView(
                number=step.number,
                step=step.step.value,
                title=step.title,
                lines=[
                    FlowLineView(
                        kind=line.kind.value,
                        text=line.text,
                        channels=[one.value for one in line.channels],
                        automation_id=line.automation_id,
                        source=line.source,
                        tool=line.tool,
                        effect=None if line.effect is None else line.effect.value,
                        rungs=[rung_key(one) for one in line.rungs],
                        leash_entry=line.leash_entry,
                    )
                    for line in step.lines
                ],
            )
            for step in flow.steps
        ],
        never=[NeverView(text=one.text, every_agent=one.every_agent) for one in flow.never],
    )


def about(
    record: AgentRecord,
    install: Install | None,
    asked: Asking,
    *,
    registry: ToolRegistry | None = None,
    automations: Sequence[Scheduled] | None = None,
) -> AboutView:
    """One admitted agent's About tab at this reader's reach.

    Takes a record the audience has already admitted, as `brain.agent_routes.workspace` does, and
    the automations already narrowed by `scheduled_for`. See
    `THE_FLOW_IS_NARROWED_BLOCK_BY_BLOCK_AS_THE_WORKSPACE_IS` for each of the other three inputs.
    """
    setup = (
        Setup(
            agent_id=record.agent_id,
            authority=record.authority,
            registered=registered_tools(record, registry),
            leash=leash_of(install, registry),
        )
        if may_read_settings(asked)
        else None
    )
    flow = about_flow(
        channels=[
            Offered(channel=one.channel, profile=rendering_profile(one))
            for one in offered_surfaces(record, asked)
        ],
        automations=automations,
        sources=reader_connector_rows(install, record, registry, asked),
        setup=setup,
    )
    summary = (install.summary or None) if install is not None else None
    return flow_view(record.agent_id, summary, flow)


async def scheduled_for(
    request: Request, agent_id: str, asked: Asking
) -> tuple[Scheduled, ...] | None:
    """This agent's automations this reader may see, or None for a reader of no Automations tab.

    None rather than an empty tuple, because the flow says "nothing starts it" only to a reader
    who could have been told about an automation. The listing and the filter are the Automations
    tab's own, and an automation whose template is gone is left out, as that tab leaves it out.
    """
    if not may_open_gallery(asked.reach, asked.now):
        return None
    every = await schedules_of(request).listed(agent_id)
    seen = {
        one.automation_id
        for one in automations_for(
            agent_id, [one.automation for one in every], asked.reach, asked.now
        )
    }
    found: list[Scheduled] = []
    for listed in every:
        template = template_by_id(listed.template_id)
        if listed.automation.automation_id not in seen or template is None:
            continue
        found.append(
            Scheduled(
                automation_id=listed.automation.automation_id,
                name=listed.automation.name,
                schedule=template.cadence.words(),
                running=listed.automation.next_run_at is not None,
            )
        )
    return tuple(found)


# ------------------------------------------------------------------------- the wiring
router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(ABOUT_PATH, response_model=AboutView, responses=COMMON_RESPONSES)
async def agent_about(request: Request, agent_id: str, asked: Asked) -> AboutView:
    """One agent's About tab, or the answer an agent that does not exist gets.

    The audience first, then the install, then the automations, so nothing about an agent this
    caller may not see is read on their behalf.
    """
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        pair = (await session.execute(install_for(agent_id))).one_or_none()
    install = install_of(pair[0], pair[1], record) if pair is not None else None
    automations = await scheduled_for(request, agent_id, asked)
    return about(
        record,
        install,
        asked,
        registry=_tool_registry(request),
        automations=automations,
    )
