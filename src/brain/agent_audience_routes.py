"""Who an agent is offered to beside its level: read, add and withdraw, from its Profile.

`brain.agents.audience_store` and `agent.audience_extra` have held the departments and people an
agent is offered to since `0223`, and `brain.agents.model.visible_to` has read them since then, but
the only thing that wrote one was an install check. The Profile said "Not a list of people" and
offered a level it could not change. This is the route behind that card (M27.11.13).

**A reader is told who an agent is offered to only if they answer for it.** The level, the
department and the steward are the availability block's and are sent to anybody who may see the
agent. The departments and the named people beside the level are sent to the agent's steward and
to a holder of the lifecycle authority over its row, and to nobody else, whose answer carries
neither list nor a word saying one exists. A reader who is named is told that already by the
availability block (`reader_is_included`), which is the one fact they need. Rejected: sending the
names to every reader of the agent, which tells a colleague that somebody they have never met was
offered a department's agent. See
`ONLY_THOSE_WHO_ANSWER_FOR_AN_AGENT_ARE_TOLD_WHO_IT_IS_OFFERED_TO`.

**Changing it is the authority that switches an agent off, and the switch ships off.** An offer
widens who is shown an agent and starts it for them, which is less than switching it on for
somebody and more than a steward alone should decide, so it asks
`brain.agents.lifecycle.AGENT_LIFECYCLE_CAPABILITY` over the agent's row exactly as the channels
and the learning pause do, and a missing agent, a hidden one and one outside the caller's authority
are the one 404 the lifecycle answers. The owner has not answered needs-rupash 201 question 1 (one
choice, or several), so the add and withdraw routes are behind the `agent_audience_extras` switch,
which ships off, and the read is not: what is stored is always shown. See
`brain.ops.features_declared.agent_audience_extras`.

**An offer is discovery and never reach, and a personal agent takes none.** The row only makes the
agent appear for a person and start for them, and `brain.agents.model.audience_scope`, which is the
only predicate a run is narrowed by, does not read it. A personal agent is found by its owner and by
nobody else (M39.10.3), so an offer on one is refused whatever the switch says, and a company agent
already names everybody, which `AgentAudience` itself refuses. See
`AN_OFFER_IS_DISCOVERY_AND_A_PERSONAL_AGENT_TAKES_NONE`.

**A department is checked against the ones the install has and a person is not.** A department
named in an offer has to be one of the registry's live departments, because a typed word that is
nobody's department is an offer to nobody that looks like one. A person is not checked, for the
reason `brain.tables.audience_extra` gives: answering that a principal does not exist tells the
asker which ids do. Both are one word with no spaces in it.

**Added by one person, withdrawn by one person, and the row stays.** The history is the table's:
`added_by`, `added_at`, `removed_by` and `removed_at`, written in the caller's name under the row
level policies of `0223`. There is no ledger entry for an offer, because the ledger's triggers are
per table and `0223` created none for this one; the table is itself the dated record of who offered
what to whom, and a trigger is a migration this leaf does not need.

Task ids: M27.11.13
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Final, Literal, Protocol, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import _actionable, _not_changed, holds
from brain.agent_routes import _require_session_factory, _visible_record
from brain.agents.audience_store import Extras, add_extra, extras_of, remove_extra
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.core.errors import Failed
from brain.knowledge.visibility import Visibility
from brain.knowledge_routes import live_departments
from brain.ops.features import is_on
from brain.ops.features_declared.agent_audience_extras import AGENT_AUDIENCE_EXTRAS
from brain.routing_routes import sessions_of
from brain.tables.audience_extra import ExtraKind

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the names beside the level go to the people who answer for the agent only.
ONLY_THOSE_WHO_ANSWER_FOR_AN_AGENT_ARE_TOLD_WHO_IT_IS_OFFERED_TO: Final = (
    "The departments and people an agent is offered to beside its level are told to its steward "
    "and to a holder of the lifecycle authority over its row. Anybody else is told the level, the "
    "department and the steward, and whether they themselves are included, and nothing that says "
    "other people were named."
)

#: Why an offer on a personal agent is refused, and why the sentence is the one it is.
AN_OFFER_IS_DISCOVERY_AND_A_PERSONAL_AGENT_TAKES_NONE: Final = (
    "An offer widens who is shown an agent and starts it for them, and a personal agent is shown "
    "to its owner and to nobody else. So an offer on one is refused whatever the switch says, "
    "and a company agent, which already names everybody, takes none either."
)

#: What a caller who may act is told, one sentence for each refusal.
NOT_SWITCHED_ON: Final = (
    "Nothing was changed: offering an agent to more departments and people is not switched on "
    "for this company yet."
)
A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER: Final = (
    "Nothing was changed: a personal agent is found only by the person it belongs to."
)
A_COMPANY_AGENT_IS_FOUND_BY_EVERYBODY: Final = (
    "Nothing was changed: a company agent is already found by everybody."
)
NOT_A_DEPARTMENT_HERE: Final = "Nothing was changed: that is not a department on this install."
TOO_MANY_OFFERS: Final = "Nothing was changed: this agent is offered to as many as it may be."
NOTHING_TO_WITHDRAW: Final = "Nothing was changed: it was not offered to that one."

#: What the card says a withdrawal and an offer are, once, so the words are the route's.
AN_OFFER_ONLY_MAKES_IT_FOUND: Final = (
    "An offer only makes the agent appear and start for them. It gives nobody access to anything "
    "they could not already reach."
)

#: Words an act's refusal carries as `outcome`, as the other writes in this family do.
REFUSED: Final = "refused"

#: The most departments and people one agent may be offered to, so a card stays a list a person
#: reads and the roster's one read stays a bounded one.
MAX_OFFERS: Final = 100

# ------------------------------------------------------------------------ the figures
AUDIENCE_PATH: Final = "/agents/{agent_id}/audience"
ADDITIONS_PATH: Final = "/agents/{agent_id}/audience/additions"
REMOVALS_PATH: Final = "/agents/{agent_id}/audience/removals"


# ------------------------------------------------------------------------------ the views
class AudienceAsked(BaseModel):
    """One department or one person, by the word the install knows them by."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["department", "person"]
    value: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S+$")]


class AudienceView(BaseModel):
    """Who an agent is offered to beside its level, as this reader may be told it.

    `departments` and `people` are empty, and `names_shown` false, for a reader who does not
    answer for the agent, and nothing else in the body varies with what was stored, so such a
    reader cannot tell an agent offered to nobody from one offered to a hundred.
    `department_choices` is sent only to a reader who may change the offers, and `refusal` only
    to one who answers for the agent, saying why they may not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    level: str
    department: str | None = None
    owner_id: str
    names_shown: bool
    departments: list[str] = []
    people: list[str] = []
    may_change: bool
    refusal: str | None = None
    department_choices: list[str] = []
    #: What an offer is and is not, said once by the route.
    words: str = AN_OFFER_ONLY_MAKES_IT_FOUND


# ------------------------------------------------------------------------------ the store
class AudienceExtras(Protocol):
    """The offers one agent holds, and the two writes, in a form a test can hold in memory."""

    async def of(self, agent_id: str) -> Extras: ...

    async def add(self, *, agent_id: str, kind: ExtraKind, value: str, by: str) -> None: ...

    async def remove(self, *, agent_id: str, kind: ExtraKind, value: str, by: str) -> bool: ...


class StoredAudienceExtras:
    """`AudienceExtras` over `agent.audience_extra`, each write in the caller's own name."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def of(self, agent_id: str) -> Extras:
        async with self._sessions() as session:
            return (await extras_of(session)).get(agent_id, Extras())

    async def add(self, *, agent_id: str, kind: ExtraKind, value: str, by: str) -> None:
        async with self._sessions() as session, session.begin():
            await add_extra(session, agent_id=agent_id, kind=kind, value=value, by=by)

    async def remove(self, *, agent_id: str, kind: ExtraKind, value: str, by: str) -> bool:
        async with self._sessions() as session, session.begin():
            return await remove_extra(session, agent_id=agent_id, kind=kind, value=value, by=by)


def audience_extras_of(request: Request) -> AudienceExtras:
    """`app.state.audience_extras` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "audience_extras", None)
    if found is not None:
        # A cast at the seam a test fills: whatever is put on `app.state` is held to this
        # protocol by the tests that put it there, and a runtime check would add nothing.
        return cast(AudienceExtras, found)
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAudienceExtras(factory)


async def extras_are_on(request: Request) -> bool:
    """Whether the offers may be changed on this install. Off until somebody turns it on.

    `app.state.agent_audience_extras_on` wins when something put a boolean there, as every other
    switch read here does, so a test can say it without a database.
    """
    found = getattr(request.app.state, "agent_audience_extras_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        return False
    async with factory() as session:
        return await is_on(session, AGENT_AUDIENCE_EXTRAS)


# ------------------------------------------------------------------------- the decisions
def why_not_changeable(record: AgentRecord, *, switched_on: bool) -> str | None:
    """Why this agent's offers may not be changed, or None when they may.

    The level first, because it is a fact about the agent and no switch repairs it. See
    `AN_OFFER_IS_DISCOVERY_AND_A_PERSONAL_AGENT_TAKES_NONE`.
    """
    level = record.audience.level
    if level is Visibility.PERSONAL:
        return A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER
    if level is Visibility.COMPANY:
        return A_COMPANY_AGENT_IS_FOUND_BY_EVERYBODY
    if not switched_on:
        return NOT_SWITCHED_ON
    return None


def answers_for(record: AgentRecord, asked: Asking) -> bool:
    """Whether this reader is the agent's steward or holds the lifecycle authority over its row."""
    return record.audience.owner_id == asked.caller.principal.id or holds(
        AGENT_LIFECYCLE_CAPABILITY, record, asked
    )


def audience_view(
    record: AgentRecord,
    extras: Extras,
    asked: Asking,
    *,
    switched_on: bool,
    departments: Sequence[str],
) -> AudienceView:
    """What this reader is told.

    See `ONLY_THOSE_WHO_ANSWER_FOR_AN_AGENT_ARE_TOLD_WHO_IT_IS_OFFERED_TO`.

    `extras` and `departments` are read only for a reader they may be told to, so for anybody
    else they arrive empty and the body is the same whatever was stored.
    """
    answering = answers_for(record, asked)
    acts = holds(AGENT_LIFECYCLE_CAPABILITY, record, asked)
    refusal = why_not_changeable(record, switched_on=switched_on)
    may_change = acts and refusal is None
    return AudienceView(
        agent_id=record.agent_id,
        level=record.audience.level.value,
        department=record.audience.department or None,
        owner_id=record.audience.owner_id,
        names_shown=answering,
        departments=list(extras.departments) if answering else [],
        people=list(extras.people) if answering else [],
        may_change=may_change,
        refusal=refusal if acts else None,
        department_choices=sorted(departments) if may_change else [],
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])

_TOLD: Final = {**COMMON_RESPONSES}


async def _departments(request: Request) -> tuple[str, ...]:
    """Every live department's slug, which is what an offer to a department may name."""
    return await live_departments(_require_session_factory(request))


async def _present(request: Request, record: AgentRecord, asked: Asking) -> AudienceView:
    """The view of one agent for this reader, reading only what this reader may be told."""
    switched_on = await extras_are_on(request)
    extras = (
        await audience_extras_of(request).of(record.agent_id)
        if answers_for(record, asked)
        else Extras()
    )
    may_change = holds(AGENT_LIFECYCLE_CAPABILITY, record, asked) and (
        why_not_changeable(record, switched_on=switched_on) is None
    )
    choices = await _departments(request) if may_change else ()
    return audience_view(record, extras, asked, switched_on=switched_on, departments=choices)


@router.get(AUDIENCE_PATH, response_model=AudienceView, responses=COMMON_RESPONSES)
async def agent_audience(request: Request, agent_id: str, asked: Asked) -> AudienceView:
    """Who one agent is offered to beside its level, or the answer a missing agent gets."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    return await _present(request, record, asked)


async def _changeable(
    request: Request, agent_id: str, asked: Asking
) -> tuple[AgentRecord, JSONResponse | None]:
    """The agent, for a caller who may change its offers, and the refusal when the change is not
    one that may be made, in the caller's own sentence."""
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    refusal = why_not_changeable(found.record, switched_on=await extras_are_on(request))
    if refusal is not None:
        return found.record, _not_changed(REFUSED, refusal)
    return found.record, None


@router.post(ADDITIONS_PATH, response_model=AudienceView, responses=_TOLD)
async def offer_agent(
    request: Request, agent_id: str, body: AudienceAsked, asked: Asked
) -> AudienceView | JSONResponse:
    """Offer one agent to one more department or person, in the caller's name.

    Adding what is already offered is the same answer as adding it, so a second press is not a
    second row. A caller who may act and may not do this is told why in one sentence, and writes
    nothing.
    """
    record, refusal = await _changeable(request, agent_id, asked)
    if refusal is not None:
        return refusal
    if body.kind == ExtraKind.DEPARTMENT.value and body.value not in await _departments(request):
        return _not_changed(REFUSED, NOT_A_DEPARTMENT_HERE)
    store = audience_extras_of(request)
    held = await store.of(record.agent_id)
    if len(held.departments) + len(held.people) >= MAX_OFFERS:
        return _not_changed(REFUSED, TOO_MANY_OFFERS)
    await store.add(
        agent_id=record.agent_id,
        kind=ExtraKind(body.kind),
        value=body.value,
        by=asked.caller.principal.id,
    )
    log.info(
        "agent offered",
        agent=record.agent_id,
        kind=body.kind,
        principal=asked.caller.principal.id,
    )
    return await _present(request, record, asked)


@router.post(REMOVALS_PATH, response_model=AudienceView, responses=_TOLD)
async def withdraw_agent(
    request: Request, agent_id: str, body: AudienceAsked, asked: Asked
) -> AudienceView | JSONResponse:
    """Withdraw an agent from one department or person, in the caller's name. The row stays."""
    record, refusal = await _changeable(request, agent_id, asked)
    if refusal is not None:
        return refusal
    done = await audience_extras_of(request).remove(
        agent_id=record.agent_id,
        kind=ExtraKind(body.kind),
        value=body.value,
        by=asked.caller.principal.id,
    )
    if not done:
        return _not_changed(REFUSED, NOTHING_TO_WITHDRAW)
    log.info(
        "agent withdrawn",
        agent=record.agent_id,
        kind=body.kind,
        principal=asked.caller.principal.id,
    )
    return await _present(request, record, asked)
