"""A skill described in conversation, drafted by the model, and added the way an import is.

`brain.tools.skill_draft` decides what a model's reply may become; this is the one route that asks
a model for it (M12.4.14). It is a module of its own, and not part of `brain.skill_routes`, because
`brain.ops.runtime_scan` holds the list of modules that call a model, and the Skills screen's
router is not on it and should not be: a router that decides who may assign a skill is one that
must never be a place a model is asked.

**It adds a skill through `brain.skill_routes._added`, the one door every way in goes through**,
so a draft is refused for another spelling of a held name and for bytes already held, is written
undecided by the person who asked, and reaches the ledger as an import does.

Task ids: M12.4.14
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_routes import _tool_registry
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.skill_library import LibrarySkill, added, drafted_package, may_add
from brain.core.lane import Lane
from brain.models.disclosure import DataCategory
from brain.models.driver import ProviderUnavailable
from brain.models.metering import Meter
from brain.models.routing import NoCompliantRoute, Tier
from brain.ops.features import SKILL_DRAFTING, is_on
from brain.skill_routes import (
    LibrarySkillView,
    _added,
    _not_answerable,
    _refused_because,
    _require_sessions,
    _trace_id,
)
from brain.tools.skill_draft import DESCRIPTION_CHARS as DRAFT_DESCRIPTION_CHARS
from brain.tools.skill_draft import REPLY_TOKENS as DRAFT_REPLY_TOKENS
from brain.tools.skill_draft import SkillDraftError, draft_messages
from brain.tools.skill_draft import read_reply as read_draft_reply

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["skills"])

#: Where a person describes a skill to be drafted (M12.4.14).
DRAFTS_PATH: Final = "/skills/drafts"

#: What a person is told when nothing can draft.
NO_MODEL_TO_DRAFT: Final = (
    "No model is set up on this install yet, so there is nothing to draft the skill. Nothing was "
    "added; you can still paste or upload the skill."
)
NO_ANSWER_TO_DRAFT: Final = (
    "The model could not be reached just now, so nothing was drafted and nothing was added. Try "
    "again in a moment."
)
THE_DRAFTING_SWITCH_IS_OFF: Final = (
    "Drafting a skill from a description is switched off on this install. An administrator can "
    "switch it on from the Features screen; nothing was added."
)

#: What the page says beside a draft, whatever the draft says.
A_DRAFT_WAITS_FOR_A_SECOND_PERSON: Final = (
    "This draft is in the library waiting for review, and no agent can read it until a second "
    "person has approved it, as with any skill added from a file."
)


class SkillDescribed(BaseModel):
    """What the person wants the skill to do, in their own words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(min_length=1, max_length=DRAFT_DESCRIPTION_CHARS)


class DraftFindingView(BaseModel):
    """One thing the draft named that this install does not have, left out and said so."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    what: str
    message: str


class SkillDraftView(BaseModel):
    """The skill as the library now holds it, and what was left out of what the model wrote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill: LibrarySkillView
    findings: list[DraftFindingView]
    note: str = A_DRAFT_WAITS_FOR_A_SECOND_PERSON


async def _departments_held(request: Request) -> tuple[str, ...]:
    """The department names this install holds, for the draft to choose its needs from."""
    from sqlalchemy import select

    from brain.tables.gate import DepartmentRow

    async with _require_sessions(request)() as session:
        found = await session.execute(
            select(DepartmentRow.slug).where(DepartmentRow.deleted_at.is_(None))
        )
        return tuple(sorted(str(one) for one in found.scalars().all()))


@router.post(
    DRAFTS_PATH,
    status_code=201,
    response_model=SkillDraftView,
    responses=COMMON_RESPONSES,
)
async def draft_skill(request: Request, body: SkillDescribed, asked: Asked) -> JSONResponse:
    """Draft a skill from a description, and add it undecided, exactly as an import is (M12.4.14).

    The authority is asked first, as an import's is, so a caller who may not add skills learns
    nothing about whether drafting is on. Then the switch, then the description, then the model:
    nothing is spent on a request that would be refused. What the model wrote is read as untrusted
    input (`brain.tools.skill_draft.read_reply`), a tool or department this install does not hold
    is left out and said, and the result goes through `_added`, the one door every way in goes
    through, so it is refused for another spelling of a held name and for bytes already held.
    See `brain.tools.skill_draft.A_DRAFTED_SKILL_IS_AN_IMPORT_AND_NOTHING_MORE_TRUSTED`.
    """
    # Imported here, as `brain.api_routes` imports this module: the co-author's own reading of the
    # executor and its recording of what a call cost, which a skill draft is held to as well.
    from brain.agent_coauthor_routes import _spent, calls_of

    if not may_add(asked.reach, asked.now):
        log.info("skill not draftable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        if not await is_on(session, SKILL_DRAFTING):
            raise _refused_because(THE_DRAFTING_SWITCH_IS_OFF)
    registry = _tool_registry(request)
    tools = [] if registry is None else [(one.name, one.description) for one in registry]
    departments = await _departments_held(request)
    try:
        messages = draft_messages(body.description, tools=tools, departments=departments)
    except SkillDraftError as refused:
        raise _refused_because(str(refused)) from None
    calls = calls_of(request)
    if calls is None:
        raise _refused_because(NO_MODEL_TO_DRAFT)
    meter = Meter()
    try:
        response = await calls.complete(
            messages,
            tier=Tier.MAIN,
            lane=Lane.ANSWER,
            meter=meter,
            trace_id=_trace_id(),
            max_output_tokens=DRAFT_REPLY_TOKENS,
            categories=(DataCategory.AGENT_DRAFT,),
        )
    except (ProviderUnavailable, NoCompliantRoute):
        await _spent(request, asked, meter, answered=False, completed_at=datetime.now(UTC))
        raise _refused_because(NO_ANSWER_TO_DRAFT) from None
    await _spent(request, asked, meter, answered=True, completed_at=datetime.now(UTC))
    try:
        draft = read_draft_reply(
            response.text,
            tools=[name for name, _ in tools],
            departments=departments,
        )
    except SkillDraftError as refused:
        raise _refused_because(str(refused)) from None

    def making(held: Sequence[LibrarySkill]) -> LibrarySkill:
        return added(drafted_package(draft, held), by=asked.caller.principal.id, at=asked.now)

    answered = await _added(request, asked, making, ())
    view = SkillDraftView(
        skill=LibrarySkillView.model_validate_json(bytes(answered.body)),
        findings=[DraftFindingView(what=one.what, message=one.message) for one in draft.findings],
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))
