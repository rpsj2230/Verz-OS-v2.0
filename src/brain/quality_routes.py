"""Quality from the console: flagging a bad answer, turning the flag into a regression case, a day's
annotation queue and what a person says of it, and the candidates a failed case opened.

`brain.ops.feedback` and `brain.ops.sampling` decided all of this and had no store and no route
(each said so in its own docstring); `brain.ops.quality_store` is the store over `0222` and this is
the door. It adds no rule of its own about what may be flagged or captured: `feedback.may_flag`,
`feedback.capture` and `sampling.draw` are called, and their refusals are the answers here.

**Every refusal is one answer.** A reader who may not flag in a department, a flag that is not
there, one whose trace has aged out and a request outside the day's sample are each the same
`Absent`, so the route does not say which door was shut. See
`brain.ops.feedback.A_LEAD_MAY_ONLY_FLAG_INSIDE_THE_DEPARTMENT_THEY_ALREADY_REACH`.

**Two grants beyond a department's flag.** Reading the sample and annotating it, and deciding a
candidate, are the whole installation's: a day's sample is drawn from every request, and a candidate
is evidence about an agent across departments. Each asks its capability held unrestricted.

**A candidate is decided here and applied nowhere.** `decide` writes a `TierDecision` row at tier
three and no route, function or column takes a candidate to an agent's configuration. See
`brain.ops.quality_store.A_FAILED_CASE_OPENS_A_CANDIDATE_AND_NEVER_CHANGES_THE_AGENT`.

No console page draws any of it yet; the routes are listed in the console audit as called by no
screen.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M34.2.2.2
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.ops.feedback import FeedbackError, FlagReason, capture, flag_answer, may_flag, plane_of
from brain.ops.quality_store import (
    DecisionError,
    annotate,
    candidates,
    decide,
    file_flag,
    flags,
    keep_case,
    sample_for,
)
from brain.ops.sampling import HumanAnnotation, SamplingError
from brain.routing_routes import sessions_of
from brain.tables.quality import ItemKind, TierDecisionWord

log = structlog.get_logger()

#: Where each door is.
FLAGS_PATH: Final = "/quality/flags"
CASE_PATH: Final = "/quality/flags/{flag_id}/case"
SAMPLE_PATH: Final = "/quality/sample"
ANNOTATIONS_PATH: Final = "/quality/annotations"
CANDIDATES_PATH: Final = "/quality/candidates"
CANDIDATE_DECISION_PATH: Final = "/quality/candidates/{candidate_id}/decision"

#: What deciding a candidate needs, held over the whole installation.
DECIDES_CANDIDATES: Final = Capability(value="approve:evaluation_candidate")

#: The screen whose read lists flags and candidates.
QUALITY_SCREEN: Final = "quality"

#: Said when a process has no database.
NOTHING_KEPT_HERE: Final = "this process has no database to keep a quality finding in"


# ------------------------------------------------------------------------ the shapes
class FlagAsked(BaseModel):
    """A lead's flag: which answer, in which department, and why. No text from the answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_ref: str = Field(min_length=1, max_length=64)
    question_id: str = Field(min_length=1, max_length=64)
    department: str = Field(min_length=1, max_length=60)
    reason: FlagReason


class FlagView(BaseModel):
    """A flag as listed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    trace_ref: str
    question_id: str
    department: str
    reason: str
    #: The half of the system the reason sends somebody to: `retrieval` for wrong sources or stale
    #: material, `reasoning` for a wrong or incomplete answer over the right material, `permission`
    #: for a refusal either way (M34.2.2.2). Derived from the reason by `plane_of` and never filed.
    plane: str
    flagged_at: datetime
    captured: bool


class FlagsView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[FlagView]


class CaseAsked(BaseModel):
    """What a captured case needs beyond the flag: the asker's own words, the shape of their reach,
    and names. Field names and a fixture, never a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    held: list[str] = Field(default_factory=list, max_length=200)
    answering_fields: list[str] = Field(default_factory=list, max_length=100)
    locked_fields: list[str] = Field(default_factory=list, max_length=100)
    mocked_from: str = Field(min_length=1, max_length=64)


class CaseView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    flag_id: str
    expectation: str


class SampleView(BaseModel):
    """One day's queue: the day, the published seed and the ids. No count, no fraction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: date
    seed: str
    request_ids: list[str]


class AnnotationAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    day: date
    request_id: str = Field(min_length=1, max_length=64)
    sound: bool
    fault: FlagReason | None = None


class AnnotationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    sound: bool


class CandidateView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    agent_id: str
    source: str
    case_ref: str
    standing: str


class CandidatesView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[CandidateView]


class CandidateDecisionAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: TierDecisionWord


class CandidateDecisionView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    decision: str
    #: What a decision does to the agent: nothing, said once so a page cannot imply otherwise.
    changes_the_agent: bool = False


# ------------------------------------------------------------------------ the wiring
router = APIRouter(prefix=API_PREFIX, tags=["quality"])


def _not_answerable() -> Absent:
    """The one refusal every door here gives."""
    return Absent("that quality finding is not answerable for this caller")


def _factory(request: Request) -> async_sessionmaker[AsyncSession]:
    found = sessions_of(request)
    if found is None:
        raise Failed(NOTHING_KEPT_HERE)
    return found


def _company_wide(reach: EntitlementSet, capability: Capability, now: datetime) -> bool:
    scope = reach.scope_for(capability, now)
    return scope is not None and scope.is_unrestricted()


def _reads(asked: Asked) -> bool:
    return permitted(screen(QUALITY_SCREEN).read, asked.reach, asked.now)


# ------------------------------------------------------------------------- the doors
@router.post(FLAGS_PATH, response_model=FlagView, responses=COMMON_RESPONSES, status_code=201)
async def flag_an_answer(request: Request, asked: Asked, body: FlagAsked) -> FlagView:
    """A department lead says an answer was wrong. Refused for a department they do not reach."""
    try:
        one = flag_answer(
            trace_ref=body.trace_ref,
            question_id=body.question_id,
            department=body.department,
            flagger=asked.reach,
            reason=body.reason,
            now=asked.now,
        )
    except FeedbackError:
        log.info("flag refused", principal=asked.caller.principal.id)
        raise _not_answerable() from None
    async with _factory(request)() as session:
        identifier = await file_flag(session, one)
        await session.commit()
    return FlagView(
        id=str(identifier),
        trace_ref=one.trace_ref,
        question_id=one.question_id,
        department=one.department,
        reason=one.reason.value,
        plane=plane_of(one.reason).value,
        flagged_at=one.at,
        captured=False,
    )


@router.get(FLAGS_PATH, response_model=FlagsView, responses=COMMON_RESPONSES)
async def listed_flags(request: Request, asked: Asked) -> FlagsView:
    """Flags in departments this reader may flag in, or every one for a reader of the screen
    across the whole installation. A flag outside both is absent, and nothing counts it."""
    if not _reads(asked):
        raise _not_answerable()
    async with _factory(request)() as session:
        found = await flags(session)
    return FlagsView(
        items=[
            FlagView(
                id=str(one.id),
                trace_ref=one.flag.trace_ref,
                question_id=one.flag.question_id,
                department=one.flag.department,
                reason=one.flag.reason.value,
                plane=plane_of(one.flag.reason).value,
                flagged_at=one.flag.at,
                captured=one.captured,
            )
            for one in found
            if may_flag(one.flag.department, asked.reach, now=asked.now) is not None
        ]
    )


@router.post(CASE_PATH, response_model=CaseView, responses=COMMON_RESPONSES, status_code=201)
async def turn_a_flag_into_a_case(
    request: Request, flag_id: uuid.UUID, asked: Asked, body: CaseAsked
) -> CaseView:
    """One click: the flag becomes a permanent regression case that carries no value."""
    async with _factory(request)() as session:
        found = next((one for one in await flags(session) if one.id == flag_id), None)
        if found is None or may_flag(found.flag.department, asked.reach, now=asked.now) is None:
            raise _not_answerable()
        try:
            held = EntitlementSet(
                principal_id="captured_asker",
                grants=tuple(
                    Grant(capability=Capability(value=one), scope=Scope.unrestricted())
                    for one in body.held
                ),
            )
            case = capture(
                found.flag,
                question=body.question,
                asked_with=held,
                answering_fields=body.answering_fields,
                locked_fields=body.locked_fields,
                mocked_from=body.mocked_from,
                now=asked.now,
            )
        except (FeedbackError, ValueError):
            raise _not_answerable() from None
        identifier = await keep_case(session, flag_id, case, by=asked.caller.principal.id)
        await session.commit()
    return CaseView(id=str(identifier), flag_id=str(flag_id), expectation=case.expectation.value)


@router.get(SAMPLE_PATH, response_model=SampleView, responses=COMMON_RESPONSES)
async def annotation_queue(request: Request, asked: Asked, day: date) -> SampleView:
    """One day's annotation queue, drawn reproducibly from the requests read that day."""
    from brain.ops.feedback import FLAG_CAPABILITY

    if not _company_wide(asked.reach, FLAG_CAPABILITY, asked.now):
        raise _not_answerable()
    async with _factory(request)() as session:
        drawn = await sample_for(session, day)
    return SampleView(day=drawn.day, seed=drawn.seed, request_ids=list(drawn.request_ids))


@router.post(
    ANNOTATIONS_PATH, response_model=AnnotationView, responses=COMMON_RESPONSES, status_code=201
)
async def annotate_an_answer(
    request: Request, asked: Asked, body: AnnotationAsked
) -> AnnotationView:
    """A person's judgement of one answer from the day's sample, in their own name."""
    from brain.ops.feedback import FLAG_CAPABILITY

    if not _company_wide(asked.reach, FLAG_CAPABILITY, asked.now):
        raise _not_answerable()
    try:
        one = HumanAnnotation(
            request_id=body.request_id,
            annotator=asked.caller.principal.id,
            sound=body.sound,
            fault=body.fault,
        )
    except SamplingError:
        raise _not_answerable() from None
    async with _factory(request)() as session:
        kept = await annotate(session, one, day=body.day)
        await session.commit()
    if not kept:
        raise _not_answerable()
    return AnnotationView(request_id=one.request_id, sound=one.sound)


@router.get(CANDIDATES_PATH, response_model=CandidatesView, responses=COMMON_RESPONSES)
async def listed_candidates(request: Request, asked: Asked) -> CandidatesView:
    """The failed cases opened against agents, each with where it stands."""
    if not _reads(asked) or not _company_wide(asked.reach, DECIDES_CANDIDATES, asked.now):
        raise _not_answerable()
    async with _factory(request)() as session:
        found = await candidates(session)
    return CandidatesView(
        items=[
            CandidateView(
                id=str(one.id),
                agent_id=one.agent_id,
                source=one.source.value,
                case_ref=one.case_ref,
                standing=one.standing,
            )
            for one in found
        ]
    )


@router.post(
    CANDIDATE_DECISION_PATH, response_model=CandidateDecisionView, responses=COMMON_RESPONSES
)
async def decide_a_candidate(
    request: Request, candidate_id: uuid.UUID, asked: Asked, body: CandidateDecisionAsked
) -> CandidateDecisionView:
    """Approve or decline a candidate, recording who. Neither changes the agent."""
    if not _company_wide(asked.reach, DECIDES_CANDIDATES, asked.now):
        raise _not_answerable()
    async with _factory(request)() as session:
        found = [one for one in await candidates(session) if one.id == candidate_id]
        if not found or found[0].standing != "pending":
            raise _not_answerable()
        try:
            await decide(
                session,
                kind=ItemKind.CANDIDATE,
                ref=str(candidate_id),
                tier=3,
                decision=body.decision,
                decided_by=asked.caller.principal.id,
                at=asked.now,
            )
        except DecisionError:
            raise _not_answerable() from None
        await session.commit()
    return CandidateDecisionView(candidate_id=str(candidate_id), decision=body.decision.value)
