"""The handover pack, over HTTP: the service level statement, the subprocessors, who owns what and
when the review is.

`brain.launch` has decided since it was written what a handover must say and refuses a handover
that cannot be said truthfully: a recovery promise the schedule cannot meet or no rehearsal has
verified, a list of model providers that is empty or names one no slot declares, a responsibility
with no named owner, a review booked too late. Nothing called it, so a client was handed a
sentence about recovery by a person typing it. This is the call site, and it is deliberately only
a call site.

**The statement is produced or refused, and the refusal is shown in `launch`'s words.** The route
reads the backup bucket the Recovery screen reads, hands `launch.service_level` the copies and the
rehearsals it found, and returns either the statement or the one sentence naming which promise
does not hold. It never rounds a refusal into a statement. A process that cannot read the bucket
says that, and does not ask `service_level` about copies it did not look for: **a statement over
no observation would be a promise signed on an absence** (`brain.install_routes.
AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`).

**The subprocessors are the providers whose key this process holds**, for the reason
`launch.A_SUBPROCESSOR_LIST_NAMES_WHO_MAY_PROCESS_AND_NOT_WHO_HAS` gives: a list built from what
has been called would be shorter than what a question may reach.

**The learning note is the sentence and two counts, both zero here.** Nothing re-derives a foreign
memory yet, so the note says the new system starts without the old one's accumulated learning and
that nothing was carried, which is true and is what the handover must say
(`brain.migration.learning.THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING`).

**One authority, held over everything**, `admin:install_setting`, to read and to write. Writing is
also behind the `handover_pack` switch, which ships off. The two writes refuse in `launch`'s own
sentences (an owner with no way to reach them, a review the day of launch or past the window), and
what is stored is read back through the same constructors.

**Not claimed:** the per-screen runbooks (M37.4.3.1, decided) and the incident playbook
(M37.4.3.2, decided) are `brain.launch.screen_runbook_gaps` and `playbook_gaps`, and are handed
over beside this pack and not drawn from it. No page draws this route yet.

Task ids: M30.5.4, M30.6.6, M37.4.2.4, M37.4.3.3, M37.4.3.5, M37.2.4.4
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import structlog
from fastapi import APIRouter, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.install_routes import (
    THE_BACKUP_BUCKET_DID_NOT_ANSWER,
    backup_objects_of,
    settings_of,
)
from brain.launch import (
    LaunchError,
    Owner,
    Responsibility,
    owner_gaps,
    review_gaps,
    service_level,
    subprocessors,
)
from brain.migration.learning import learning_note
from brain.ops import handover_store
from brain.ops.backup_manifest import read_drills, read_manifests
from brain.ops.features import is_on
from brain.ops.features_declared.handover_pack import HANDOVER_PACK
from brain.ops.model_service import held_providers
from brain.ops.storage import StoreUnansweredError
from brain.routing_routes import sessions_of
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: Reads and writes the handover. Held over everything or not at all.
HANDOVER_AUTHORITY = Capability(value="admin:install_setting")

#: Said when the bucket was not read, in place of a statement over no observation.
NO_STATEMENT_WITHOUT_THE_COPIES = (
    "the service level statement was not asked of the copies, because this process does not read "
    "the backup bucket, so no promise about recovery is made on an absence"
)


class ServiceLevelView(BaseModel):
    """The statement, as `launch.ServiceLevel` states it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str
    rpo_seconds: int
    rto_seconds: int
    measured_rto_seconds: float
    measured_at: AwareDatetime
    because: str


class SubprocessorView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    purpose: str


class OwnerView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    responsibility: str
    name: str
    contact: str


class ReviewView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    launched_on: date
    review_booked_for: date


class LearningView(BaseModel):
    """The sentence the handover must carry, and what was carried across, which is nothing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sentence: str
    derived: int
    files_read: int


class HandoverView(BaseModel):
    """The pack as far as it can be said, and everything that stops it being complete."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Exactly one of the statement and the sentence for why there is none.
    service_level: ServiceLevelView | None
    service_level_refused: str
    #: Exactly one of the list and the sentence for why there is none.
    subprocessors: list[SubprocessorView] | None
    subprocessors_refused: str
    owners: list[OwnerView]
    owner_gaps: list[str]
    review: ReviewView | None
    review_gaps: list[str]
    learning: LearningView
    unreadable: list[str]
    #: True when every part is present: nothing is outstanding.
    ready: bool
    #: Whether the two writes are switched on for this install.
    can_record: bool


class OwnerAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    responsibility: Responsibility
    name: str = Field(min_length=1, max_length=200)
    contact: str = Field(min_length=1, max_length=300)


class OwnersAsked(BaseModel):
    """The whole list, replacing the earlier one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owners: list[OwnerAsked] = Field(max_length=30)


class ReviewAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    launched_on: date
    review_booked_for: date


def may_hand_over(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds the install authority over everything."""
    return _in_reach(reach, HANDOVER_AUTHORITY, NOWHERE, now)


def _not_answerable() -> Absent:
    return Absent("the handover is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    message = f"that was not saved: {reason}"
    return Absent(message, public_message=message)


router = APIRouter(prefix=API_PREFIX, tags=["install"])


async def _page(request: Request, asked: Asked) -> HandoverView:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    try:
        async with factory() as session:
            held = await handover_store.recorded(session)
            switched_on = await is_on(session, HANDOVER_PACK)
    except SQLAlchemyError as error:
        log.warning("handover not read", error=type(error).__name__)
        raise Failed("the handover could not be read") from error

    level: ServiceLevelView | None = None
    level_refused = ""
    objects = backup_objects_of(request)
    if objects is None:
        level_refused = NO_STATEMENT_WITHOUT_THE_COPIES
    else:
        try:
            listing = await asyncio.to_thread(lambda: tuple(objects()))
        except StoreUnansweredError as error:
            log.warning("backup bucket did not answer", error=str(error))
            level_refused = THE_BACKUP_BUCKET_DID_NOT_ANSWER
        else:
            backups, _ = read_manifests(listing)
            verifications, _ = read_drills(listing)
            try:
                made = service_level(
                    settings_of(request).profile,
                    verifications=verifications,
                    backups=backups,
                    now=asked.now,
                )
            except LaunchError as refused:
                level_refused = str(refused)
            else:
                level = ServiceLevelView(
                    profile=made.profile,
                    rpo_seconds=made.rpo_seconds,
                    rto_seconds=made.rto_seconds,
                    measured_rto_seconds=made.measured_rto_seconds,
                    measured_at=made.measured_at,
                    because=made.because,
                )

    named: list[SubprocessorView] | None = None
    named_refused = ""
    try:
        named = [
            SubprocessorView(provider=one.slug, purpose=one.purpose)
            for one in subprocessors(held_providers())
        ]
    except LaunchError as refused:
        named_refused = str(refused)

    owner_findings = list(owner_gaps(held.owners))
    review_findings = (
        ["no review is booked, and a review that has to be arranged later is arranged later"]
        if held.review is None
        else list(
            review_gaps(
                launched_on=held.review.launched_on,
                review_booked_for=held.review.review_booked_for,
            )
        )
    )
    note = learning_note([], [])
    return HandoverView(
        service_level=level,
        service_level_refused=level_refused,
        subprocessors=named,
        subprocessors_refused=named_refused,
        owners=[
            OwnerView(responsibility=one.responsibility.value, name=one.name, contact=one.contact)
            for one in held.owners
        ],
        owner_gaps=owner_findings,
        review=(
            None
            if held.review is None
            else ReviewView(
                launched_on=held.review.launched_on,
                review_booked_for=held.review.review_booked_for,
            )
        ),
        review_gaps=review_findings,
        learning=LearningView(
            sentence=note.sentence, derived=note.derived, files_read=note.files_read
        ),
        unreadable=list(held.unreadable),
        # An unreadable stored value is also a missing owner or review, so it needs no clause here.
        ready=(
            level is not None and named is not None and not owner_findings and not review_findings
        ),
        can_record=switched_on,
    )


@router.get("/handover", response_model=HandoverView, responses=COMMON_RESPONSES)
async def handover(request: Request, asked: Asked) -> HandoverView:
    """The pack as far as it can be said now, and everything that stops it being complete."""
    if not may_hand_over(asked.reach, asked.now):
        raise _not_answerable()
    return await _page(request, asked)


@router.put("/handover/owners", response_model=HandoverView, responses=COMMON_RESPONSES)
async def save_owners(request: Request, body: OwnersAsked, asked: Asked) -> HandoverView:
    """Name who owns knowledge, grants and connectors. The list replaces the earlier one."""
    if not may_hand_over(asked.reach, asked.now):
        raise _not_answerable()
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    try:
        owners = tuple(
            Owner(responsibility=one.responsibility, name=one.name, contact=one.contact)
            for one in body.owners
        )
    except LaunchError as refused:
        raise _refused_because(str(refused)) from None
    async with factory() as session:
        if not await is_on(session, HANDOVER_PACK):
            raise _refused_because(
                "recording the handover is switched off for this install; switch it on from "
                "Features"
            )
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=str(structlog.contextvars.get_contextvars().get("trace_id", "")),
        ):
            await session.execute(statement)
        await handover_store.save_owners(session, owners, by=asked.caller.principal.id)
        await session.commit()
    log.info("handover owners recorded", principal=asked.caller.principal.id)
    return await _page(request, asked)


@router.put("/handover/review", response_model=HandoverView, responses=COMMON_RESPONSES)
async def book_review(request: Request, body: ReviewAsked, asked: Asked) -> HandoverView:
    """Book the review. Refused when it is the day of launch, before it, or past thirty days."""
    if not may_hand_over(asked.reach, asked.now):
        raise _not_answerable()
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    findings = review_gaps(launched_on=body.launched_on, review_booked_for=body.review_booked_for)
    if findings:
        raise _refused_because("; ".join(findings))
    async with factory() as session:
        if not await is_on(session, HANDOVER_PACK):
            raise _refused_because(
                "recording the handover is switched off for this install; switch it on from "
                "Features"
            )
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=str(structlog.contextvars.get_contextvars().get("trace_id", "")),
        ):
            await session.execute(statement)
        await handover_store.save_review(
            session,
            handover_store.Review(
                launched_on=body.launched_on, review_booked_for=body.review_booked_for
            ),
            by=asked.caller.principal.id,
        )
        await session.commit()
    log.info("handover review booked", principal=asked.caller.principal.id)
    return await _page(request, asked)
