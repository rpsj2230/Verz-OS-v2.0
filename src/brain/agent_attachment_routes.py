"""Attaching a tool or a connector to an agent from its page, and detaching one.

`brain.agents.attachments` decides what an agent carries and whether a press may be made, and
`brain.ops.attachment_store` keeps each press with its ledger entry; this is the route between the
page and them, and it decides only who may press.

**Tools are the tool administrator's over the agent's department**, or over everything for an agent
no department owns (`agent_workspace_routes.place_of`), because what an agent may call is part of
its ceiling and a department's ceiling is its administrator's (`docs/requirements/register.json`
ARC-B-064). **Connectors are the agent's steward's or the connector administrator's over its
department**: which sources an agent reads is the question its steward answers for, and the
person's own reach is still asked of everything a connector would open, so a steward cannot hand
the agent a source they could not read. Anybody else is told which role would let them, and never
whether the press would have been allowed. See
`ATTACHING_IS_THE_DEPARTMENT_S_TOOL_OR_CONNECTOR_ROLE`.

**A connector press writes the agent's own connector list and nothing else**, which is what
`brain.agents.binding.bound_capabilities` compiles into its ceiling; there is no second store of
it. See `brain.agents.attachments.A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`.

**What may be attached is listed from the registry at the agent's ceiling and the reader's reach**,
so the list never names a tool the reader could not attach, and a tool outside either is refused in
the sentence a tool that does not exist gets.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    _no_agent_here,
    _require_session_factory,
    _tool_registry,
    _visible_record,
    may_read_settings,
)
from brain.agent_workspace_routes import place_of
from brain.agents.attachments import (
    AttachmentError,
    attachable,
    connector_attachable,
    connectors_after_attach,
    connectors_after_detach,
    connectors_of,
    narrowed,
    to_attach,
    to_detach,
)
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.console.scoped_authority import within_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.attachment_store import AgentMovedError, StoredAttachments, changes_in
from brain.tables.attachment import AttachmentPart

log = structlog.get_logger()

ATTACHING_IS_THE_DEPARTMENT_S_TOOL_OR_CONNECTOR_ROLE: Final = (
    "What an agent may call is part of its ceiling, and a department's ceiling is its "
    "administrator's: a tool is attached or detached by whoever holds the tool authority over the "
    "agent's department, a connector by the agent's steward or the connector authority over it. "
    "Anybody else is told which role, and never whether the press would have been allowed."
)

CHANGING_TOOLS_NEEDS_THE_TOOL_ROLE: Final = (
    "Attaching or detaching this agent's tools needs the tool role for its department."
)
CHANGING_CONNECTORS_NEEDS_THE_CONNECTOR_ROLE: Final = (
    "Attaching or detaching this agent's connectors needs its steward or the connector role for "
    "its department."
)
THE_AGENT_MOVED: Final = (
    "This agent changed a moment ago, or has been archived, so nothing was changed. Look again "
    "before pressing once more."
)

TOOL_AUTHORITY: Final = Capability(value="admin:tool")
CONNECTOR_AUTHORITY: Final = Capability(value="admin:connector")

#: The reason code a press from the page is recorded with.
FROM_THE_AGENT_PAGE: Final = "changed_on_the_agent_page"

ATTACHMENTS_PATH: Final = "/agents/{agent_id}/attachments"


def may_press(
    part: AttachmentPart, reach: EntitlementSet, record: AgentRecord, now: datetime
) -> bool:
    """Whether this reach may attach or detach this kind of thing on this agent."""
    if part is AttachmentPart.TOOL:
        return within_reach(reach, TOOL_AUTHORITY, place_of(record), now)
    return reach.principal_id == record.audience.owner_id or within_reach(
        reach, CONNECTOR_AUTHORITY, place_of(record), now
    )


def shipped_connectors() -> frozenset[str]:
    """The connector names this release ships, which are the only ones an agent can name."""
    from brain.connectors.declaration import shipped

    return frozenset(shipped())


class AttachableView(BaseModel):
    """One thing the reader could attach, by name, with its source and what it does."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    source: str
    description: str


class AttachmentsView(BaseModel):
    """What the reader could attach, and whether they may attach or detach at all."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    #: The tools the agent carries now that this process registers, by name.
    carried: list[AttachableView]
    #: The connectors the agent names, which its ceiling is compiled with.
    carried_connectors: list[str]
    tools: list[AttachableView]
    #: The connectors this reader could attach: each opens something the agent may read, all of
    #: which the reader reaches.
    connectors: list[str]
    may_change_tools: bool
    may_change_connectors: bool


class PressAsked(BaseModel):
    """One press: attach or detach a tool or a connector."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    part: Literal["tool", "connector"]
    reference: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    attached: bool


class PressedView(BaseModel):
    """What a press moved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    reference: str
    attached: bool
    tools: list[str]
    #: For a connector press, the agent's connector list as it now stands.
    connectors: list[str] = []


def _refused(message: str, status: int = 409) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message})


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(ATTACHMENTS_PATH, response_model=AttachmentsView, responses=COMMON_RESPONSES)
async def agent_attachments(request: Request, agent_id: str, asked: Asked) -> AttachmentsView:
    """What this reader could attach to this agent, behind the Settings read (M39.8.6)."""
    factory = _require_session_factory(request)
    registry = _tool_registry(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_settings(asked):
            raise _no_agent_here()
        record = narrowed(record, await changes_in(session, (agent_id,)))
    carried = record.authority.allowed_tools
    registered = () if registry is None else registry.definitions()
    open_tools = [
        one
        for one in registered
        if one.name not in carried and attachable(one, record, asked.reach, asked.now)
    ]
    held = [one for one in registered if one.name in carried]
    return AttachmentsView(
        agent_id=agent_id,
        carried=[
            AttachableView(name=one.name, source=one.source, description=one.description)
            for one in sorted(held, key=lambda tool: tool.name)
        ],
        carried_connectors=list(connectors_of(record)),
        tools=[
            AttachableView(name=one.name, source=one.source, description=one.description)
            for one in sorted(open_tools, key=lambda tool: tool.name)
        ],
        connectors=sorted(
            one
            for one in shipped_connectors()
            if one not in connectors_of(record)
            and connector_attachable(one, record, asked.reach, asked.now)
        ),
        may_change_tools=may_press(AttachmentPart.TOOL, asked.reach, record, asked.now),
        may_change_connectors=may_press(AttachmentPart.CONNECTOR, asked.reach, record, asked.now),
    )


@router.post(ATTACHMENTS_PATH, response_model=PressedView, responses=COMMON_RESPONSES)
async def press_attachment(
    request: Request, agent_id: str, body: PressAsked, asked: Asked
) -> JSONResponse | PressedView:
    """Attach or detach one tool or one connector's tools, checked now (M39.2.1.2, M39.8.6)."""
    factory = _require_session_factory(request)
    registry = _tool_registry(request)
    part = AttachmentPart(body.part)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_settings(asked):
            raise _no_agent_here()
        record = narrowed(record, await changes_in(session, (agent_id,)))
    if not may_press(part, asked.reach, record, asked.now):
        told = (
            CHANGING_TOOLS_NEEDS_THE_TOOL_ROLE
            if part is AttachmentPart.TOOL
            else CHANGING_CONNECTORS_NEEDS_THE_CONNECTOR_ROLE
        )
        return _refused(told, 403)
    if part is AttachmentPart.CONNECTOR:
        return await _press_connector(factory, record, body, asked)
    registered = () if registry is None else registry.definitions()
    carried = record.authority.allowed_tools
    try:
        tools = (
            to_attach(
                body.reference,
                record=record,
                carried=carried,
                registered=registered,
                by=asked.reach,
                now=asked.now,
            )
            if body.attached
            else to_detach(body.reference, record=record, carried=carried)
        )
    except AttachmentError as refused:
        return _refused(str(refused))
    await StoredAttachments(factory).press(
        agent_id=agent_id,
        part=part,
        reference=body.reference,
        attached=body.attached,
        tools=tools,
        by=asked.caller.principal.id,
        reason_code=FROM_THE_AGENT_PAGE,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
        at=asked.now,
    )
    return PressedView(
        part=part.value, reference=body.reference, attached=body.attached, tools=list(tools)
    )


async def _press_connector(
    factory: async_sessionmaker[AsyncSession], record: AgentRecord, body: PressAsked, asked: Asking
) -> JSONResponse | PressedView:
    """Write the agent's connector list with one added or taken away (M39.8.6)."""
    try:
        becomes = (
            connectors_after_attach(
                body.reference,
                record=record,
                by=asked.reach,
                now=asked.now,
            )
            if body.attached
            else connectors_after_detach(body.reference, record=record)
        )
    except AttachmentError as refused:
        return _refused(str(refused))
    try:
        await StoredAttachments(factory).bind_connectors(
            agent_id=record.agent_id,
            was=connectors_of(record),
            becomes=becomes,
            by=asked.caller.principal.id,
            reason_code=FROM_THE_AGENT_PAGE,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_of_request(),
        )
    except AgentMovedError:
        return _refused(THE_AGENT_MOVED)
    return PressedView(
        part=AttachmentPart.CONNECTOR.value,
        reference=body.reference,
        attached=body.attached,
        tools=[],
        connectors=list(becomes),
    )
