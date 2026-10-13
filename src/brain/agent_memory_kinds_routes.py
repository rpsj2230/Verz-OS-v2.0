"""Which kinds of memory an agent may read and write, read and set over HTTP (M39.7.1).

The owner decided on needs item 180 (2026-10-12, option B) that an agent is configured with which of
five kinds of memory it may read and write, and that a run cannot read a kind its configuration
leaves out. `brain.agents.memory_kinds` holds the five and why, `AgentRecord.memory_kinds` holds the
setting, and `brain.gate.turn_context.assemble` is where it is enforced; this is the screen's half:
what is set now, and the one write that changes it.

**The authority is the channels'**, for the same reason: the agent's steward and a holder of the
lifecycle authority over its row, and nobody else, and anybody else is answered as an agent that
does not exist. A kind switched off narrows what a run is shown and never what a caller may reach,
so it asks nothing of the caller's own reach, and switching one on is no wider than it was when the
agent was made, which had all five. See
`brain.agent_lifecycle_routes.A_STEWARD_OR_AN_ADMINISTRATOR_SWITCHES_AN_AGENT_S_CHANNELS`.

**The page sends the kinds it drew, and a row that moved since is a 409 and nothing is written.**
The write is a compare and set on the array the decision was read from, `0225`'s trigger appends
one `compose_change` entry for each kind added or taken, and the reason code the entry carries is
`memory_kinds_set`.

Task ids: M39.7.1
"""

from __future__ import annotations

from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import (
    IT_MOVED,
    MOVED,
    _no_agent_here,
    _not_changed,
    _trace_id,
    lifecycles_of,
    may_change_channels,
    visible,
)
from brain.agents.memory_kinds import ALL_KINDS, MemoryKind, memory_kinds_of
from brain.agents.model import AgentRecord, remembering
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.errors import Failed
from brain.ops.attachment_store import REASON_SETTING
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to

log = structlog.get_logger()

MEMORY_KINDS_PATH: Final = "/agents/{agent_id}/memory-kinds"

#: The reason the ledger entry for a kind switched on or off carries.
REASON_CODE: Final = "memory_kinds_set"

#: What each kind is called on the page, and what it is.
KIND_WORDS: Final[dict[str, tuple[str, str]]] = {
    MemoryKind.CONVERSATION.value: (
        "This conversation",
        "What was asked earlier in the thread and what the person said for this conversation only.",
    ),
    MemoryKind.TASK.value: ("The task", "The skills and instructions the agent was given for it."),
    MemoryKind.PROJECT.value: (
        "The project",
        "What is current about the client project asked about.",
    ),
    MemoryKind.PERSON.value: (
        "The person",
        "What the person asking said about themselves and may still recall.",
    ),
    MemoryKind.OWN.value: ("Its own", "What the agent itself remembers across conversations."),
}

#: Why a kind switched off is not a deletion.
A_KIND_LEFT_OUT_IS_NOT_READ_AND_NOT_DELETED: Final = (
    "Leaving a kind of memory out stops a run from being shown it. It deletes nothing: what was "
    "remembered stays where it is, and switching the kind on again shows it again, so an agent's "
    "owner can try an agent without one kind and change their mind. A person's own right to have "
    "what the agent remembered about them deleted is unchanged by any of this."
)


class KindChoiceView(BaseModel):
    """One kind a page draws as a box: its name, its words, and whether it is on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    hint: str
    on: bool


class MemoryKindsView(BaseModel):
    """What an agent's memory is set up as, and whether this reader may change it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    kinds: list[KindChoiceView]
    may_change: bool
    note: str = A_KIND_LEFT_OUT_IS_NOT_READ_AND_NOT_DELETED


class MemoryKindsAsked(BaseModel):
    """The kinds an agent should be set up with, and the kinds the page drew."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kinds: list[str] = Field(max_length=len(ALL_KINDS))
    expected: list[str] = Field(max_length=len(ALL_KINDS))

    @field_validator("kinds", "expected")
    @classmethod
    def _known(cls, value: list[str]) -> list[str]:
        return list(memory_kinds_of(value))


def view_of(record: AgentRecord, *, may_change: bool) -> MemoryKindsView:
    """The agent's memory as a page draws it: every kind, each on or off."""
    return MemoryKindsView(
        agent_id=record.agent_id,
        kinds=[
            KindChoiceView(
                name=name,
                label=KIND_WORDS[name][0],
                hint=KIND_WORDS[name][1],
                on=name in record.memory_kinds,
            )
            for name in ALL_KINDS
        ],
        may_change=may_change,
    )


class StoredMemoryKinds:
    """The one write: an agent's memory kinds, if they still hold what the decision read."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def change(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        """A compare and set, as `StoredAgentLifecycles.change_channels`. `0225`'s trigger appends
        one `compose_change` entry for each kind added or taken, attributed by the three settings
        and carrying `REASON_CODE`."""
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor_id, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            await session.execute(
                text("SELECT set_config(:name, :value, true)"),
                {"name": REASON_SETTING, "value": REASON_CODE},
            )
            written = (
                await session.execute(
                    update(AgentRow)
                    .where(
                        AgentRow.id == before.agent_id,
                        AgentRow.memory_kinds == list(before.memory_kinds),
                    )
                    .values(memory_kinds=list(after.memory_kinds))
                    .returning(AgentRow.id)
                )
            ).scalar_one_or_none()
        return written is not None


def stored_kinds_of(request: Request) -> StoredMemoryKinds:
    """`app.state.memory_kinds` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "memory_kinds", None)
    if isinstance(found, StoredMemoryKinds):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredMemoryKinds(factory)


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(MEMORY_KINDS_PATH, response_model=MemoryKindsView, responses=COMMON_RESPONSES)
async def agent_memory_kinds(request: Request, agent_id: str, asked: Asked) -> MemoryKindsView:
    """What the agent's memory is set up as, to anybody its audience covers."""
    found = await lifecycles_of(request).agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    return view_of(found.record, may_change=may_change_channels(found.record, asked))


@router.post(
    MEMORY_KINDS_PATH,
    response_model=MemoryKindsView,
    responses={**COMMON_RESPONSES, 409: {"description": "Nothing was changed, and why."}},
)
async def set_agent_memory_kinds(
    request: Request, agent_id: str, body: MemoryKindsAsked, asked: Asked
) -> JSONResponse:
    """Set which kinds of memory the agent may read and write, for its steward or an administrator.

    The page sends the kinds it drew; a row that moved since is a 409 and nothing is written.
    """
    found = await lifecycles_of(request).agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    if not may_change_channels(found.record, asked):
        raise _no_agent_here(asked, "scope")
    before = found.record
    if tuple(body.expected) != before.memory_kinds:
        return _not_changed(MOVED, IT_MOVED)
    after = remembering(before, body.kinds)
    if after.memory_kinds != before.memory_kinds and not await stored_kinds_of(request).change(
        before,
        after,
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    ):
        return _not_changed(MOVED, IT_MOVED)
    log.info("agent memory kinds set", agent=agent_id, principal=asked.caller.principal.id)
    return JSONResponse(
        status_code=200, content=view_of(after, may_change=True).model_dump(mode="json")
    )
