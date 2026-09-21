"""The retention report over HTTP, and the four writes that decide whether the sweep may act.

`brain.ops.retention_store` writes a report on every run and reads the holds and the release
the sweep acts on. Until this module nothing outside the process could read a report, place a
hold, or release the sweep, so the sweep reported for ever and a hold could only be written with
a database password. This is the half that makes them reachable, and it decides nothing the
store or the console decides.

**Whether the report may be shown is `brain.console.govern_surfaces.retention_view`, whole or
withheld.** The Retention screen's own question is asked first, before the database, with
`brain.console.reads.permitted`, on the ordering argument `brain.govern_routes` makes: a caller
who may not open the screen is refused identically whether or not this process has a pool. A
caller who may open it and whose grant is not company-wide is answered **no report**, which is
exactly what an install that has never run a sweep answers, because a report is counts over the
whole estate and a department reader shown it would learn how much is held about people outside
their reach. See `A_READER_WHO_MAY_NOT_SEE_THE_ESTATE_IS_ANSWERED_AS_A_FRESH_INSTALL`.

**Every write needs its authority over everything.** `admin:retention` releases and withdraws
the sweep and `admin:legal_hold` places and lifts a hold, each held unrestricted, because both
decide about every store at once and a hold scoped to a department cannot be expressed by the
sweep that honours it. Both are checked with `brain.console.govern._in_reach` at
`brain.console.govern.NOWHERE`, which only a company-wide grant admits, rather than by a scope
comparison written here. **Releasing also needs the report**: the caller must be somebody
`retention_view` would show the report to, because a release is the record that a person read
it. See `A_RELEASE_BY_SOMEBODY_WHO_COULD_NOT_READ_THE_REPORT_APPROVED_NOTHING`.

**One refusal for a caller without authority, and a named one for a caller with it.** A caller
who may not write is told nothing, in the shape every govern write takes. A caller who holds
the authority and names a report that is no longer the newest is told so, because they already
see the whole estate and the only thing the reason discloses is what they need to fix.

**Nothing is deleted through here, and there is no route that could.** A hold is lifted by
being marked, a release is withdrawn by being marked, and a report is never touched: the
console's own client has no DELETE verb, for the reason it gives.

Task ids: M25.1.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.audit.ledger import FIELD_NAME, IDENTIFIER, LegalHold
from brain.console.govern import NOWHERE, _in_reach
from brain.console.govern_surfaces import RETENTION_SCREEN, retention_view
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.retention import DataClass, RetentionReport
from brain.ops.retention_store import (
    ReleaseRefusedError,
    RetentionStoreError,
    StoredReport,
    latest_report,
    lift_hold,
    place_hold,
    release_sweep,
    released_controls,
    withdraw_release,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a department reader of the Retention screen is answered as an install with no report.
A_READER_WHO_MAY_NOT_SEE_THE_ESTATE_IS_ANSWERED_AS_A_FRESH_INSTALL: Final = (
    "retention_view withholds the report from everybody whose grant is not company-wide, and the "
    "two ways of withholding it are a refusal and an absence. A refusal tells a department reader "
    "that a report exists and that it is about more than they may see; an absence tells them "
    "what an install that has never swept tells everybody. So the answer is no report, and "
    "nothing on the response distinguishes the two."
)

#: Why releasing needs the report as well as the authority.
A_RELEASE_BY_SOMEBODY_WHO_COULD_NOT_READ_THE_REPORT_APPROVED_NOTHING: Final = (
    "brain.ops.schedule keeps the sweep reporting until a person who read its report releases "
    "it. A caller holding admin:retention and not the Retention screen's read has never been "
    "shown a report, so a release from them is a deletion nobody who read anything approved, "
    "recorded as though somebody had."
)

# ------------------------------------------------------------------------ authorities
#: Releases and withdraws the retention sweep. Held over everything or not at all.
RETENTION_AUTHORITY: Final = Capability(value="admin:retention")

#: Places and lifts a legal hold. Held over everything or not at all.
LEGAL_HOLD_AUTHORITY: Final = Capability(value="admin:legal_hold")

#: How many subjects or actors one hold may name. A resource bound on a request body, not a
#: permission: a hold over more people than this is a company-wide hold, which is one flag.
MAX_HELD_NAMES: Final = 500


def may_release(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may release or withdraw the sweep: the authority, over everything."""
    return _in_reach(reach, RETENTION_AUTHORITY, NOWHERE, now)


def may_hold(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may place or lift a legal hold: the authority, over everything."""
    return _in_reach(reach, LEGAL_HOLD_AUTHORITY, NOWHERE, now)


# ------------------------------------------------------------------------ the shapes
class ClassCount(BaseModel):
    """One data class and how many items of it something happened to."""

    model_config = ConfigDict(frozen=True)

    data_class: DataClass
    count: int


class StoreLine(BaseModel):
    """One store's line of a report. Counts and reasons, and never a subject."""

    model_config = ConfigDict(frozen=True)

    store: str
    data_class: DataClass
    lifetime: str
    days: int | None
    reached: bool
    beyond_horizon: int
    held: int
    due: int
    removed: int
    queued: int
    queued_because: str
    unreached_because: str
    oldest_days: int | None


class CitedHoldView(BaseModel):
    """A hold a run was under, by identifier and reason code."""

    model_config = ConfigDict(frozen=True)

    hold_id: str
    reason_code: str
    company_wide: bool


class ReportView(BaseModel):
    """One run's report, as the store wrote it and `retention_view` allowed it."""

    model_config = ConfigDict(frozen=True)

    report_id: uuid.UUID
    at: datetime
    report_only: bool
    complete: bool
    failure: str | None
    #: Whether a release is live now, so the reader knows whether the next run will act.
    released: bool
    removed: int
    removed_by_class: list[ClassCount]
    held_by_class: list[ClassCount]
    queued_by_class: list[ClassCount]
    stores: list[StoreLine]
    holds: list[CitedHoldView]
    findings: list[str]


class RetentionAnswer(BaseModel):
    """The Retention screen's report half. `report` is None for no report and for withheld."""

    model_config = ConfigDict(frozen=True)

    report: ReportView | None


class ReleaseBody(BaseModel):
    """Release the sweep after reading the report named."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    after_report: uuid.UUID


class Released(BaseModel):
    model_config = ConfigDict(frozen=True)

    release_id: uuid.UUID
    after_report: uuid.UUID
    released_at: datetime


class Withdrawn(BaseModel):
    model_config = ConfigDict(frozen=True)

    withdrawn_at: datetime


class HoldBody(BaseModel):
    """A hold to place. The instant is the request's, never the body's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hold_id: str = Field(pattern=IDENTIFIER)
    reason_code: str = Field(pattern=FIELD_NAME, max_length=80)
    subjects: list[Annotated[str, Field(pattern=IDENTIFIER)]] = Field(
        default_factory=list, max_length=MAX_HELD_NAMES
    )
    actors: list[Annotated[str, Field(pattern=IDENTIFIER)]] = Field(
        default_factory=list, max_length=MAX_HELD_NAMES
    )
    all_subjects: bool = False


class HoldPlaced(BaseModel):
    model_config = ConfigDict(frozen=True)

    hold_id: str
    placed_at: datetime


class LiftBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hold_id: str = Field(pattern=IDENTIFIER)


class HoldLifted(BaseModel):
    model_config = ConfigDict(frozen=True)

    hold_id: str
    lifted_at: datetime


def report_view(stored: StoredReport, report: RetentionReport, *, released: bool) -> ReportView:
    """The response for one report, copied field by field from what the store and view gave."""

    def counts(pairs: tuple[tuple[DataClass, int], ...]) -> list[ClassCount]:
        return [ClassCount(data_class=data_class, count=count) for data_class, count in pairs]

    return ReportView(
        report_id=stored.id,
        at=report.at,
        report_only=report.report_only,
        complete=report.complete,
        failure=stored.failure,
        released=released,
        removed=report.removed,
        removed_by_class=counts(report.removed_by_class()),
        held_by_class=counts(report.held_by_class()),
        queued_by_class=counts(report.queued_by_class()),
        stores=[
            StoreLine(
                store=one.store.value,
                data_class=one.data_class,
                lifetime=one.lifetime.value,
                days=one.days,
                reached=one.reached,
                beyond_horizon=one.beyond_horizon,
                held=one.held,
                due=one.due,
                removed=one.removed,
                queued=one.queued,
                queued_because=one.queued_because,
                unreached_because=one.unreached_because,
                oldest_days=one.oldest_days,
            )
            for one in report.swept
        ],
        holds=[
            CitedHoldView(
                hold_id=hold.hold_id, reason_code=hold.reason_code, company_wide=hold.company_wide
            )
            for hold in report.holds
        ],
        findings=list(report.findings),
    )


# ------------------------------------------------------------------------ the wiring
def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory, or a process-level fault, on `brain.govern_routes`' argument."""
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable() -> Absent:
    """The refusal the Retention screen makes to a caller who may not open it."""
    return Absent(f"the {RETENTION_SCREEN} screen is not answerable for this caller")


def _not_writable() -> Absent:
    """The one refusal every write here makes to a caller without the authority."""
    return Absent("that retention change is not writable by this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what they need to fix."""
    message = f"that retention change was not made: {reason}"
    return Absent(message, public_message=message)


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/retention", response_model=RetentionAnswer, responses=COMMON_RESPONSES)
async def retention_report(request: Request, asked: Asked) -> RetentionAnswer:
    """The newest retention report, whole, or no report.

    The screen's question before the database; then the newest report; then `retention_view`,
    which answers the report or None. See
    `A_READER_WHO_MAY_NOT_SEE_THE_ESTATE_IS_ANSWERED_AS_A_FRESH_INSTALL`.

    The store is read before the view decides, for the reason `brain.report_routes` gives: a
    route that skipped the read for a reader it expected to withhold from would answer that
    reader faster, and the difference would be readable from outside.
    """
    if not permitted(screen(RETENTION_SCREEN).read, asked.reach, asked.now):
        log.info("retention screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()

    async with _require_sessions(request)() as session:
        stored = await latest_report(session)
        released = bool(await released_controls(session, now=asked.now))

    if stored is None:
        return RetentionAnswer(report=None)
    shown = retention_view(stored.report, asked.reach, asked.now)
    if shown is None:
        return RetentionAnswer(report=None)
    return RetentionAnswer(report=report_view(stored, shown, released=released))


@router.post("/govern/retention/release", response_model=Released, responses=COMMON_RESPONSES)
async def release(request: Request, body: ReleaseBody, asked: Asked) -> Released:
    """Release the sweep after the report named, so its next run removes what may go.

    Both questions before the database: the authority over everything, and that this caller is
    somebody the report would be shown to. See
    `A_RELEASE_BY_SOMEBODY_WHO_COULD_NOT_READ_THE_REPORT_APPROVED_NOTHING`. Whether the report
    named may be released after is `brain.ops.retention_store.release_refusal`.
    """
    if not may_release(asked.reach, asked.now) or not permitted(
        screen(RETENTION_SCREEN).read, asked.reach, asked.now
    ):
        log.info("retention release not writable", principal=asked.caller.principal.id)
        raise _not_writable()

    async with _require_sessions(request)() as session:
        # Who, at what reach, in which request, for the entry the release's trigger writes.
        await attribute(session, asked)
        stored = await latest_report(session)
        if stored is None or retention_view(stored.report, asked.reach, asked.now) is None:
            await session.rollback()
            log.info(
                "retention release with no readable report", principal=asked.caller.principal.id
            )
            raise _not_writable()
        try:
            made = await release_sweep(
                session, after_report=body.after_report, by=asked.caller.principal.id, at=asked.now
            )
        except ReleaseRefusedError as refused:
            await session.rollback()
            raise _refused_because(refused.reason.value) from None
        except IntegrityError:
            await session.rollback()
            raise _refused_because("already_released") from None
        await session.commit()
    return Released(release_id=made, after_report=body.after_report, released_at=asked.now)


@router.post("/govern/retention/withdrawal", response_model=Withdrawn, responses=COMMON_RESPONSES)
async def withdraw(request: Request, asked: Asked) -> Withdrawn:
    """Put the sweep back to reporting. Needs the authority and not the report."""
    if not may_release(asked.reach, asked.now):
        log.info("retention withdrawal not writable", principal=asked.caller.principal.id)
        raise _not_writable()

    async with _require_sessions(request)() as session:
        await attribute(session, asked)
        withdrawn = await withdraw_release(session, by=asked.caller.principal.id, at=asked.now)
        if not withdrawn:
            await session.rollback()
            raise _refused_because("not_released")
        await session.commit()
    return Withdrawn(withdrawn_at=asked.now)


@router.post("/govern/legal-holds", response_model=HoldPlaced, responses=COMMON_RESPONSES)
async def hold(request: Request, body: HoldBody, asked: Asked) -> HoldPlaced:
    """Place a legal hold from this instant. The sweep's next run honours it."""
    if not may_hold(asked.reach, asked.now):
        log.info("legal hold not writable", principal=asked.caller.principal.id)
        raise _not_writable()
    try:
        placed = LegalHold(
            id=body.hold_id,
            reason_code=body.reason_code,
            subjects=frozenset(body.subjects),
            actors=frozenset(body.actors),
            all_subjects=body.all_subjects,
            placed_at=asked.now,
        )
    except ValidationError:
        raise _refused_because("names_nothing") from None

    async with _require_sessions(request)() as session:
        await attribute(session, asked)
        try:
            await place_hold(session, placed, by=asked.caller.principal.id)
        except (IntegrityError, RetentionStoreError):
            await session.rollback()
            raise _refused_because("not_placed") from None
        await session.commit()
    return HoldPlaced(hold_id=placed.id, placed_at=asked.now)


@router.post("/govern/legal-holds/lift", response_model=HoldLifted, responses=COMMON_RESPONSES)
async def lift(request: Request, body: LiftBody, asked: Asked) -> HoldLifted:
    """Mark a hold lifted from this instant. The row stays."""
    if not may_hold(asked.reach, asked.now):
        log.info("legal hold lift not writable", principal=asked.caller.principal.id)
        raise _not_writable()

    async with _require_sessions(request)() as session:
        await attribute(session, asked)
        lifted = await lift_hold(session, body.hold_id, by=asked.caller.principal.id, at=asked.now)
        if not lifted:
            await session.rollback()
            raise _refused_because("not_a_live_hold")
        await session.commit()
    return HoldLifted(hold_id=body.hold_id, lifted_at=asked.now)
