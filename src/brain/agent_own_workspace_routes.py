"""A person's own Google account on their personal agent, read and attached over HTTP (M39.10.4).

`brain.agents.own_workspace` holds the decision and why it is shaped as it is; this is the page's
route to it, and the one write: the agent's own connector list with the account added or taken out.

**Only the owner of a personal agent is answered at all.** A colleague, an administrator who holds
every authority there is and a person naming an agent that was never made are one `404`, and so is
a read of a team agent, which has no such card. A press on a team agent a reader can see is the one
refusal in a sentence that is not about the reader's own standing: a team agent never carries one
person's own account, and saying so reveals nothing the page does not already show. What else is
refused in a sentence is only what the owner can mend: a switch that is off, an account nobody has
given them access to.

**The switch gates attaching and never detaching.** `personal_agent_own_workspace` ships off. An
account already attached stays attached when it goes off, and its owner can still take it off.

**Whether the person has connected their own account is told to them and decides nothing.**
Attaching before connecting is allowed: the agent reads nothing until the person has consented at
Google from My workspace, and a person who attaches first is told, on the card, that the other half
is theirs to do. What is refused is an account the person may not connect at all (they hold no read
of Google Workspace in the connection's department, or the company has not connected it), because
nothing would ever be read from it and a card that said "attached" would be a lie.

**The write is the agent's connector list and nothing else**, written by
`brain.ops.attachment_store.StoredAttachments.bind_connectors` in the owner's own name: a compare
and set on the list the decision was read from, one ledger entry for the connector added or taken,
naming the owner and carrying `own_workspace_attached` or `own_workspace_detached`.

Task ids: M39.10.4
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import _no_agent_here, _trace_id, lifecycles_of, visible
from brain.agents.attachments import connectors_of
from brain.agents.own_workspace import (
    ATTACHED_REASON,
    CONNECTOR,
    DETACHED_REASON,
    THE_AGENT_MOVED,
    after_attach,
    after_detach,
    attach_refusal,
    detach_refusal,
    is_attached,
    is_personal,
    owns,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.connector_routes import _connected_for, _personal_sources
from brain.core.errors import Failed
from brain.credential_routes import credentials_of
from brain.ops.attachment_store import AgentMovedError, StoredAttachments
from brain.ops.features import is_on
from brain.ops.features_declared.personal_agent_own_workspace import PERSONAL_AGENT_OWN_WORKSPACE
from brain.routing_routes import sessions_of

log = structlog.get_logger()

OWN_WORKSPACE_PATH: Final = "/agents/{agent_id}/own-workspace"

#: What the card says under its buttons, whatever else is true.
WHAT_IT_READS: Final = (
    "The agent reads your own mail, calendar and documents, with your own consent at Google, for "
    "you alone, when you ask it something. Nothing is copied into the Brain. Nobody else can ask "
    "it for them, and you connect or disconnect your account from My workspace."
)


class OwnWorkspaceView(BaseModel):
    """Whether the owner's own Google account is on this agent, and whether they may attach it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    attached: bool
    #: Whether pressing attach would be accepted now: the switch is on and the account is one this
    #: person may connect. Their own standing, which tells nothing about anybody else.
    may_attach: bool
    #: Whether they have connected their own account at Google; null when that could not be asked.
    account_connected: bool | None = None
    note: str = WHAT_IT_READS


class OwnWorkspaceAsked(BaseModel):
    """Attach the account, or take it off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attached: bool


@runtime_checkable
class OwnWorkspaceStore(Protocol):
    """What the write needs of the agent table. `StoredOwnWorkspace` implements it."""

    async def bind(
        self,
        *,
        agent_id: str,
        was: tuple[str, ...],
        becomes: tuple[str, ...],
        by: str,
        reason_code: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool: ...


class StoredOwnWorkspace:
    """The one write, over `StoredAttachments`. False when the agent moved since it was read."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._attachments = StoredAttachments(sessions)

    async def bind(
        self,
        *,
        agent_id: str,
        was: tuple[str, ...],
        becomes: tuple[str, ...],
        by: str,
        reason_code: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        try:
            await self._attachments.bind_connectors(
                agent_id=agent_id,
                was=was,
                becomes=becomes,
                by=by,
                reason_code=reason_code,
                ent_hash=ent_hash,
                trace_id=trace_id,
            )
        except AgentMovedError:
            return False
        return True


def store_of(request: Request) -> OwnWorkspaceStore:
    """`app.state.own_workspace` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "own_workspace", None)
    if isinstance(found, OwnWorkspaceStore):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredOwnWorkspace(factory)


async def own_workspace_is_on(sessions: async_sessionmaker[AsyncSession] | None) -> bool:
    """Whether `personal_agent_own_workspace` is switched on now. Off with no database or no row."""
    if sessions is None:
        return False
    async with sessions() as session:
        return await is_on(session, PERSONAL_AGENT_OWN_WORKSPACE)


async def _offered(request: Request, asked: Asking) -> bool:
    """Whether Google Workspace is connected and this person may connect their own account."""
    sources = await _personal_sources(request, asked.reach, asked.now)
    return any(declared.name == CONNECTOR for declared, _ in sources)


def _refused(message: str) -> JSONResponse:
    return JSONResponse(status_code=409, content={"message": message})


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(OWN_WORKSPACE_PATH, response_model=OwnWorkspaceView, responses=COMMON_RESPONSES)
async def agent_own_workspace(request: Request, agent_id: str, asked: Asked) -> OwnWorkspaceView:
    """Whether the owner's own Google account is on their personal agent. Anybody else: the 404."""
    found = await lifecycles_of(request).agent(agent_id)
    if (
        found is None
        or not visible(found.record, asked)
        or not owns(found.record, asked.caller.principal.id)
    ):
        raise _no_agent_here(asked, "own workspace")
    record = found.record
    offered = await _offered(request, asked)
    switched_on = await own_workspace_is_on(sessions_of(request))
    held = _connected_for(credentials_of(request), CONNECTOR, asked.caller.principal.id)
    return OwnWorkspaceView(
        agent_id=agent_id,
        attached=is_attached(record),
        may_attach=attach_refusal(record, offered=offered, switched_on=switched_on) is None,
        account_connected=held if offered else None,
    )


@router.post(OWN_WORKSPACE_PATH, response_model=OwnWorkspaceView, responses=COMMON_RESPONSES)
async def attach_own_workspace(
    request: Request, agent_id: str, body: OwnWorkspaceAsked, asked: Asked
) -> JSONResponse:
    """Attach the owner's own Google account to their personal agent, or take it off.

    Decided from the agent as it stands and written as a compare and set on its connector list, so
    a page that went stale is told so and nothing is written.
    """
    found = await lifecycles_of(request).agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "own workspace")
    record = found.record
    # A team agent a reader can see is told the rule it was asked to break; a personal agent is the
    # owner's alone, so anybody else is answered as for an agent that was never made.
    if is_personal(record) and not owns(record, asked.caller.principal.id):
        raise _no_agent_here(asked, "own workspace")
    offered = await _offered(request, asked)
    switched_on = await own_workspace_is_on(sessions_of(request))
    if body.attached:
        refusal = attach_refusal(record, offered=offered, switched_on=switched_on)
        becomes, reason = after_attach(record), ATTACHED_REASON
    else:
        refusal = detach_refusal(record)
        becomes, reason = after_detach(record), DETACHED_REASON
    if refusal is not None:
        return _refused(refusal)
    written = await store_of(request).bind(
        agent_id=agent_id,
        was=connectors_of(record),
        becomes=becomes,
        by=asked.caller.principal.id,
        reason_code=reason,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if not written:
        return _refused(THE_AGENT_MOVED)
    log.info("own workspace changed on an agent", agent=agent_id, attached=body.attached)
    held = _connected_for(credentials_of(request), CONNECTOR, asked.caller.principal.id)
    answered = OwnWorkspaceView(
        agent_id=agent_id,
        attached=body.attached,
        may_attach=not body.attached and offered and switched_on,
        account_connected=held if offered else None,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
