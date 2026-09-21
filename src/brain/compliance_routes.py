"""The Compliance screen over HTTP: sensitive-topic routing, the processing register, breach cases.

Three owner sentences had modules and no screen (docs/tracker-audit-2026-09-17.md): a sensitive
question routed to the named person for its topic (M24.2.2), a data processing record per
connector (M24.2.3), and a PDPA breach assessment with the correct clock (M24.2.4). The decisions
are `brain.audit.compliance`'s and `brain.ops.processing_register`'s; the rows are
`brain.ops.sensitive_referral_store`'s and `brain.ops.breach_store`'s. This module asks them in
order and adds no second opinion.

**One authority for every read and write under `/govern/compliance`: `admin:compliance` held over
everything.** `brain.settings_routes`' shape and its argument: a breach case, a topic's named
person and the register are the whole company's, there is no department's version of any of
them, and a `read:` capability for pages whose only readers act on them would be one the first
administrator, who holds every `admin:` capability, could not open. Being `admin:`, it is withheld
from a password-only session and from every channel but the console by `brain.gate.admission`.
A caller without it is refused in one way on every route, before any store is asked.

**The named person's own list is `/me/referrals`, and it needs no capability.** A referral is read
by the person it was routed to, and the database decides that (`0104`'s policy), so a route that
also asked for a grant would stop the person the owner named from ever seeing what was sent to
them. What anybody else gets from it is their own empty list.

**The tally is suppressed, never a count of hidden items.** A data protection officer sees whether
the control ran this month through `InterceptionTally.report`, which releases nothing below a
cohort and no breakdown that a total could complete.

Task ids: M24.2.2, M24.2.3, M24.2.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.audit.compliance import (
    REFERRAL_TEXT,
    Awareness,
    AwarenessBasis,
    AwarenessSource,
    ExceptionGround,
    SensitiveTopic,
)
from brain.audit.ledger import IDENTIFIER
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.breach_store import (
    CLOSING_NEEDS_A_MADE_ASSESSMENT,
    Actor,
    BreachCases,
    BreachRecord,
    BreachRefusedError,
    StoredBreachCases,
    closable,
)
from brain.ops.connector_store import ConnectorRecords, StoredConnections
from brain.ops.processing_register import (
    THE_COUNTS_ARE_WHAT_WAS_READ,
    RegisterRow,
    register_rows,
)
from brain.ops.read_counts_store import ReadCountSource, StoredReadCounts
from brain.ops.sensitive_referral_store import (
    NamedPerson,
    NamingRefusedError,
    Referral,
    SensitiveReferrals,
    StoredSensitiveReferrals,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: The authority every route under `/govern/compliance` asks, over everything.
COMPLIANCE_AUTHORITY: Final = Capability(value="admin:compliance")

TOPICS_PATH: Final = "/govern/compliance/topics"
REGISTER_PATH: Final = "/govern/compliance/register"
BREACHES_PATH: Final = "/govern/compliance/breaches"
MY_REFERRALS_PATH: Final = "/me/referrals"

#: What each topic is called on the screen. Product text, identical on every install.
TOPIC_LABELS: Final[dict[SensitiveTopic, str]] = {
    SensitiveTopic.HR_PERSONAL: "HR matters",
    SensitiveTopic.GRIEVANCE: "Grievances",
    SensitiveTopic.HARASSMENT: "Harassment and bullying",
    SensitiveTopic.WHISTLEBLOWING: "Whistleblowing",
    SensitiveTopic.SALARY: "Salary",
    SensitiveTopic.MEDICAL: "Medical",
    SensitiveTopic.LEGAL: "Legal matters",
}

#: What the topics section says about itself.
ROUTING_IS_BESIDE_THE_CONVERSATION: Final = (
    "A question on one of these topics is not answered by any agent. The asker is told the same "
    "sentence whatever the topic, and a note that they asked, without what they wrote, goes to "
    "the person named for the topic, who reads it under Referred to me. A topic with nobody "
    "named keeps its notes for whoever is named next."
)


def may_govern_compliance(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `admin:compliance` over everything."""
    return _in_reach(reach, COMPLIANCE_AUTHORITY, NOWHERE, now)


def _refused() -> Absent:
    return Absent("the compliance screen is not answerable for this caller")


def _because(reason: str) -> Absent:
    message = f"that was not recorded: {reason}"
    return Absent(message, public_message=message)


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", "")) or "untraced"


def _actor(asked: Asking) -> Actor:
    return Actor(
        principal_id=asked.reach.principal_id, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id()
    )


def _required_sessions(request: Request) -> Any:
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return sessions


def referrals_of(request: Request) -> SensitiveReferrals:
    found = getattr(request.app.state, "sensitive_referrals", None)
    if isinstance(found, SensitiveReferrals):
        return found
    return StoredSensitiveReferrals(_required_sessions(request))


def breaches_of(request: Request) -> BreachCases:
    found = getattr(request.app.state, "breach_cases", None)
    if isinstance(found, BreachCases):
        return found
    return StoredBreachCases(_required_sessions(request))


def connections_of(request: Request) -> ConnectorRecords:
    found = getattr(request.app.state, "connector_records", None)
    if isinstance(found, ConnectorRecords):
        return found
    return StoredConnections(_required_sessions(request))


def read_counts_of(request: Request) -> ReadCountSource:
    found = getattr(request.app.state, "read_counts", None)
    if isinstance(found, ReadCountSource):
        return found
    return StoredReadCounts(_required_sessions(request))


# ------------------------------------------------------------------------ the shapes
class NamedView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    named_by: str
    named_at: datetime


class TopicView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str
    label: str
    named: NamedView | None


class TallyView(BaseModel):
    """`TallyReport`, copied field by field. `total` and `by_topic` are None when suppressed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    total: int | None
    by_topic: dict[str, int] | None
    suppressed: bool


class TopicsView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    topics: list[TopicView]
    tally: TallyView
    referral: str
    routing: str


class NameBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(pattern=IDENTIFIER)


class ReferralView(BaseModel):
    """One referral as its reader sees it: who asked, when and about which topic. Nothing said."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    referral_id: str
    topic: str
    label: str
    asked_by: str
    asked_at: datetime
    handled_at: datetime | None
    handled_by: str | None


class ReferralsView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    referrals: list[ReferralView]


class RegisterEntityView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str
    tier: str
    fields: list[str]
    classes: list[str]


class RegisterRowView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    label: str
    connected_by: str
    connected_at: datetime
    transport: str | None
    version: str | None
    entities: list[RegisterEntityView]
    categories: list[str]
    write_capable: bool
    records_read: int | None
    documents_read: int | None
    last_read_at: datetime | None
    problem: str


class RegisterView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    connectors: list[RegisterRowView]
    counts: str


class ObligationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    basis: str
    due_before: datetime | None
    satisfied: bool
    overdue: bool
    satisfied_late: bool
    out_of_order: bool


class BreachView(BaseModel):
    """One case: its clock, its steps and what is wrong with it. Never what happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    became_aware_at: datetime
    clock_starts_at: datetime
    awareness_basis: str
    awareness_source: str
    recorded_by: str
    evidence_reference: str
    assessed_at: datetime | None
    significant_harm: bool | None
    affected_count: int | None
    outcome: str | None
    commission_notified_at: datetime | None
    individuals_notified_at: datetime | None
    exception_ground: str | None
    closed_at: datetime | None
    closed_by: str | None
    obligations: list[ObligationView]
    findings: list[str]
    closable: bool


class BreachesView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: list[BreachView]
    closing: str


class OpenBody(BaseModel):
    """What opening a case needs: when there was reason to believe, how that is known, and where
    the evidence is. No description, for `brain.tables.compliance`'s reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    became_aware_at: datetime
    basis: AwarenessBasis
    source: AwarenessSource
    evidence_reference: str = Field(pattern=IDENTIFIER)
    earliest_possible_at: datetime | None = None


class AssessBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    significant_harm: bool
    rationale_reference: str = Field(pattern=IDENTIFIER)
    #: None means not yet established, never zero.
    affected_count: int | None = Field(default=None, ge=0)


class NotifiedBody(BaseModel):
    """When the notification was made, which may be before it is recorded. Defaults to now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime | None = None


class ExceptionBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ground: ExceptionGround
    rationale_reference: str = Field(pattern=IDENTIFIER)


def named_view(one: NamedPerson | None) -> NamedView | None:
    if one is None:
        return None
    return NamedView(principal_id=one.principal_id, named_by=one.named_by, named_at=one.named_at)


def referral_view(one: Referral) -> ReferralView:
    return ReferralView(
        referral_id=one.referral_id,
        topic=one.topic.value,
        label=TOPIC_LABELS[one.topic],
        asked_by=one.asked_by,
        asked_at=one.asked_at,
        handled_at=one.handled_at,
        handled_by=one.handled_by,
    )


def register_view(row: RegisterRow) -> RegisterRowView:
    return RegisterRowView(
        connector=row.connector,
        label=row.label,
        connected_by=row.connected_by,
        connected_at=row.connected_at,
        transport=row.transport,
        version=row.version,
        entities=[
            RegisterEntityView(
                entity=e.entity, tier=e.tier.value, fields=list(e.fields), classes=list(e.classes)
            )
            for e in row.entities
        ],
        categories=list(row.categories),
        write_capable=row.write_capable,
        records_read=None if row.counts is None else row.counts.records,
        documents_read=None if row.counts is None else row.counts.documents,
        last_read_at=None if row.counts is None else row.counts.finished_at,
        problem=row.problem,
    )


def breach_view(record: BreachRecord, now: datetime) -> BreachView:
    case = record.case
    made = case.assessment
    return BreachView(
        case_id=case.case_id,
        became_aware_at=case.awareness.became_aware_at,
        clock_starts_at=case.awareness.clock_starts_at,
        awareness_basis=case.awareness.basis.value,
        awareness_source=case.awareness.source.value,
        recorded_by=case.awareness.recorded_by,
        evidence_reference=case.awareness.evidence_reference,
        assessed_at=None if made is None else made.assessed_at,
        significant_harm=None if made is None else made.harm.significant_harm,
        affected_count=None if made is None else made.affected_count,
        outcome=None if made is None else made.outcome.value,
        commission_notified_at=case.commission_notified_at,
        individuals_notified_at=case.individuals_notified_at,
        exception_ground=(
            None if case.individuals_exception is None else case.individuals_exception.ground.value
        ),
        closed_at=record.closed_at,
        closed_by=record.closed_by,
        obligations=[
            ObligationView(
                kind=o.kind.value,
                basis=o.basis.value,
                due_before=o.due_before,
                satisfied=o.satisfied,
                overdue=o.overdue,
                satisfied_late=o.satisfied_late,
                out_of_order=o.out_of_order,
            )
            for o in case.outstanding(now)
        ],
        findings=list(case.findings(now)),
        closable=record.closed_at is None and closable(record),
    )


router = APIRouter(prefix=API_PREFIX, tags=["compliance"])


def _govern(asked: Asking) -> None:
    if not may_govern_compliance(asked.reach, asked.now):
        log.info("compliance not answerable", principal=asked.caller.principal.id)
        raise _refused()


# ------------------------------------------------------------ sensitive topics (M24.2.2)
@router.get(TOPICS_PATH, response_model=TopicsView, responses=COMMON_RESPONSES)
async def topics(request: Request, asked: Asked) -> TopicsView:
    """Every topic, who it is routed to, and this month's suppressed tally."""
    _govern(asked)
    store = referrals_of(request)
    named = await store.named()
    report = (await store.tally(asked.now.strftime("%Y-%m"))).report()
    return TopicsView(
        topics=[
            TopicView(topic=t.value, label=TOPIC_LABELS[t], named=named_view(named.get(t)))
            for t in SensitiveTopic
        ],
        tally=TallyView(
            period=report.period,
            total=report.total,
            by_topic=(
                None
                if report.by_topic is None
                else {topic.value: n for topic, n in report.by_topic.items()}
            ),
            suppressed=report.suppressed,
        ),
        referral=REFERRAL_TEXT,
        routing=ROUTING_IS_BESIDE_THE_CONVERSATION,
    )


@router.put(TOPICS_PATH + "/{topic}", response_model=NamedView, responses=COMMON_RESPONSES)
async def name_person(request: Request, topic: str, body: NameBody, asked: Asked) -> NamedView:
    """Name the person a topic is routed to. `0059`'s trigger records the change, not the value."""
    _govern(asked)
    chosen = next((t for t in SensitiveTopic if t.value == topic), None)
    if chosen is None:
        raise _refused()
    try:
        named = await referrals_of(request).name(
            chosen,
            body.principal_id,
            by=asked.reach.principal_id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        )
    except NamingRefusedError:
        raise _because("the person named is not somebody active on this install") from None
    return NamedView(
        principal_id=named.principal_id, named_by=named.named_by, named_at=named.named_at
    )


@router.get(MY_REFERRALS_PATH, response_model=ReferralsView, responses=COMMON_RESPONSES)
async def my_referrals(request: Request, asked: Asked) -> ReferralsView:
    """The referrals routed to this caller, newest first. The database decides which."""
    found = await referrals_of(request).mine(asked.reach.principal_id)
    return ReferralsView(referrals=[referral_view(one) for one in found])


@router.post(
    MY_REFERRALS_PATH + "/{referral_id}/handled",
    response_model=ReferralsView,
    responses=COMMON_RESPONSES,
)
async def handled(request: Request, referral_id: uuid.UUID, asked: Asked) -> ReferralsView:
    """Mark one referral handled. One refusal for one that is not this caller's or is done."""
    store = referrals_of(request)
    done = await store.handle(
        str(referral_id),
        by=asked.reach.principal_id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
        at=asked.now,
    )
    if not done:
        raise Absent("that referral is not open for this caller")
    found = await store.mine(asked.reach.principal_id)
    return ReferralsView(referrals=[referral_view(one) for one in found])


# ----------------------------------------------------------- processing register (M24.2.3)
@router.get(REGISTER_PATH, response_model=RegisterView, responses=COMMON_RESPONSES)
async def register(request: Request, asked: Asked) -> RegisterView:
    """Every connected source: what it reads, its categories, and what its last run read."""
    _govern(asked)
    connections = await connections_of(request).connected()
    counts = await read_counts_of(request).counts() if connections else {}
    return RegisterView(
        connectors=[register_view(row) for row in register_rows(connections, counts)],
        counts=THE_COUNTS_ARE_WHAT_WAS_READ,
    )


# ---------------------------------------------------------------- breach cases (M24.2.4)
@router.get(BREACHES_PATH, response_model=BreachesView, responses=COMMON_RESPONSES)
async def breaches(request: Request, asked: Asked) -> BreachesView:
    """Every case, newest awareness first, with its clock as at now."""
    _govern(asked)
    found = await breaches_of(request).cases()
    return BreachesView(
        cases=[breach_view(one, asked.now) for one in found],
        closing=CLOSING_NEEDS_A_MADE_ASSESSMENT,
    )


@router.post(BREACHES_PATH, response_model=BreachView, responses=COMMON_RESPONSES)
async def open_breach(request: Request, body: OpenBody, asked: Asked) -> BreachView:
    """Open a case from an awareness stated in full. The recorder is the caller; now is the
    instant it was recorded, and never a time the body could choose."""
    _govern(asked)
    try:
        awareness = Awareness(
            became_aware_at=body.became_aware_at,
            basis=body.basis,
            source=body.source,
            earliest_possible_at=body.earliest_possible_at,
            recorded_at=asked.now,
            recorded_by=asked.reach.principal_id,
            evidence_reference=body.evidence_reference,
        )
    except ValueError as wrong:
        raise _because(str(wrong).splitlines()[-1]) from None
    opened = await breaches_of(request).open(awareness, actor=_actor(asked))
    return breach_view(opened, asked.now)


async def _move(
    request: Request, case_id: uuid.UUID, changes: dict[str, Any], asked: Asking
) -> BreachView:
    try:
        moved = await breaches_of(request).move(str(case_id), changes, actor=_actor(asked))
    except BreachRefusedError as refused:
        raise _because(refused.reason) from None
    except ValueError as wrong:
        raise _because(str(wrong).splitlines()[-1]) from None
    return breach_view(moved, asked.now)


@router.post(
    BREACHES_PATH + "/{case_id}/assessment", response_model=BreachView, responses=COMMON_RESPONSES
)
async def assess(
    request: Request, case_id: uuid.UUID, body: AssessBody, asked: Asked
) -> BreachView:
    """Record the assessment: the caller's harm judgement, where it is written, and the count."""
    _govern(asked)
    return await _move(
        request,
        case_id,
        {
            "assessed_at": asked.now,
            "significant_harm": body.significant_harm,
            "harm_decided_by": asked.reach.principal_id,
            "harm_rationale_reference": body.rationale_reference,
            "affected_count": body.affected_count,
        },
        asked,
    )


def _when(body: NotifiedBody, asked: Asking) -> datetime:
    at = body.at or asked.now
    if at.tzinfo is None or at > asked.now:
        raise _because("a notification is recorded at a time with a zone, and not in the future")
    return at


@router.post(
    BREACHES_PATH + "/{case_id}/commission", response_model=BreachView, responses=COMMON_RESPONSES
)
async def commission_notified(
    request: Request, case_id: uuid.UUID, body: NotifiedBody, asked: Asked
) -> BreachView:
    """Record that the Commission was notified, and when."""
    _govern(asked)
    return await _move(request, case_id, {"commission_notified_at": _when(body, asked)}, asked)


@router.post(
    BREACHES_PATH + "/{case_id}/individuals", response_model=BreachView, responses=COMMON_RESPONSES
)
async def individuals_notified(
    request: Request, case_id: uuid.UUID, body: NotifiedBody, asked: Asked
) -> BreachView:
    """Record that the affected individuals were notified, and when."""
    _govern(asked)
    return await _move(request, case_id, {"individuals_notified_at": _when(body, asked)}, asked)


@router.post(
    BREACHES_PATH + "/{case_id}/exception", response_model=BreachView, responses=COMMON_RESPONSES
)
async def individuals_excused(
    request: Request, case_id: uuid.UUID, body: ExceptionBody, asked: Asked
) -> BreachView:
    """Record the decision not to notify the individuals, its ground and where it is reasoned."""
    _govern(asked)
    return await _move(
        request,
        case_id,
        {
            "exception_ground": body.ground.value,
            "exception_decided_by": asked.reach.principal_id,
            "exception_decided_at": asked.now,
            "exception_rationale_reference": body.rationale_reference,
        },
        asked,
    )


@router.post(
    BREACHES_PATH + "/{case_id}/close", response_model=BreachView, responses=COMMON_RESPONSES
)
async def close_breach(request: Request, case_id: uuid.UUID, asked: Asked) -> BreachView:
    """Close a case whose assessment has been made. See `CLOSING_NEEDS_A_MADE_ASSESSMENT`."""
    _govern(asked)
    return await _move(
        request, case_id, {"closed_at": asked.now, "closed_by": asked.reach.principal_id}, asked
    )
