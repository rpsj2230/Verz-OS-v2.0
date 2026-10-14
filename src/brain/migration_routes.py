"""Running a migration from another system, kept and checked: the register, the comparison period
and the cutover, over HTTP.

`brain.migration` is a package of refusals nothing called: a register of what the old system holds
and what happens to each of it (`inventory`), a comparison period whose criteria were agreed before
it began (`parallel`), and a cutover that cannot be reported complete while an act with a security
consequence is unrecorded (`decommission`). Until this module each was a value that ended with the
process. This keeps them (`ops.migration_record`, `0241`), reads them back through the package's own
constructors, and says what is outstanding.

**The route is the package's refusals with a database under them, and nothing more.** A body is
built into `Catalogue`, `Period` or `Decommission` and refused in the words the package gives
(an item decided by omission, a threshold agreed after the period began, an archive taken before the
system was read-only); what is stored has passed them once and reading it back passes them again,
because a row is also something that arrives by being loaded. The findings are computed on read and
never stored, so they cannot be stale.

**A save is a version, and a save after a completed cutover is not a completed cutover.** Each PUT
appends a new version and the newest is current. `reported_complete` is written only by
`POST /migration/cutover/complete`, which builds `CompletedCutover` and so cannot succeed while a
gated act is unrecorded; a later edit to the record writes a version without it, because a cutover
reported complete and then changed is a cutover nobody has reported. Rejected: letting the body
carry `reported_by`, which is the one way to forge a completion by naming oneself.

**What this does not do is touch the old system.** Nothing here reaches it, exports from it or
revokes anything of its: a revocation is recorded as asked and as confirmed by a person, and an act
is recorded as done by a person, because nothing here can check either
(`decommission.AN_ACT_NOBODY_RECORDED_IS_AN_ACT_NOBODY_DID`). The exporter is a plugin that does not
exist, so the register's catalogue is typed in or pasted by whoever surveyed the old system, and the
comparison log holds the question and the verdict and never either answer.

**One authority, held over everything**, `admin:install_setting`: a migration is the install's own
business and has no department. Reading is the authority; writing is also behind the
`migration_workspace` switch, which ships off, so a fresh install holds no migration record.

**Not claimed:** the exporter and the re-parse (M37.1.2), the old system's side of the comparison
(M37.1.3.1), the skill and memory conversions (M37.2), and the whole-migration rehearsal (M37.7.6).

Task ids: M37.1.1.1, M37.1.1.2, M37.1.1.3, M37.1.3.2, M37.1.3.3
Task ids: M37.1.4.1, M37.1.4.2, M37.1.4.3, M37.1.4.4, M37.7.5
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.migration import decommission as cutover_module
from brain.migration import inventory, parallel
from brain.migration.inventory import MigrationError
from brain.ops import migration_record_store
from brain.ops.features import MIGRATION_WORKSPACE, is_on
from brain.routing_routes import sessions_of
from brain.tables.migration_record import RecordKind

log = structlog.get_logger()

#: Reads the migration records and writes them. Held over everything or not at all.
MIGRATION_AUTHORITY: Final = Capability(value="admin:install_setting")

#: How many of anything one document may hold. A migration past these is a project of its own.
MOST_ITEMS: Final = 2000
MOST_COMPARISONS: Final = 5000
MOST_ACTS: Final = 200

Name = Annotated[str, Field(min_length=1, max_length=240)]
Short = Annotated[str, Field(min_length=1, max_length=120)]


def may_run_a_migration(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read and write the migration records: the authority, over
    everything."""
    return _in_reach(reach, MIGRATION_AUTHORITY, NOWHERE, now)


# ----------------------------------------------------------------- what is written: the register
class ItemAsked(BaseModel):
    """One thing the old system holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: Short
    holding: Literal["knowledge", "prompt", "tool", "conversation"]
    name: Name
    permissions: list[Short] = Field(default_factory=list, max_length=64)


class ItemDecisionAsked(BaseModel):
    """What happens to one item, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: Short
    disposition: Literal["migrate", "rebuild", "retire"]
    because: Name


class MappingAsked(BaseModel):
    """What one old permission becomes here, and the argument for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    old: Short
    capabilities: list[Short] = Field(default_factory=list, max_length=32)
    because: Name


class RegisterAsked(BaseModel):
    """The register: what was surveyed, what was found, what is decided and what is mapped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surveyed: list[Literal["knowledge", "prompt", "tool", "conversation"]]
    items: list[ItemAsked] = Field(default_factory=list, max_length=MOST_ITEMS)
    decisions: list[ItemDecisionAsked] = Field(default_factory=list, max_length=MOST_ITEMS)
    mappings: list[MappingAsked] = Field(default_factory=list, max_length=MOST_ITEMS)


# ---------------------------------------------------------------- what is written: the period
class CriterionAsked(BaseModel):
    """One threshold, when it was agreed and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measure: Literal["questions asked", "days running", "unreviewed disagreements"]
    direction: Literal["at least", "at most"]
    threshold: Annotated[int, Field(ge=0, le=1_000_000)]
    agreed_at: AwareDatetime
    because: Name


class ComparisonAsked(BaseModel):
    """One question put to both systems and the verdict. Neither answer is held."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: Name
    asked_at: AwareDatetime
    verdict: Literal["agreed", "differed", "only one answered"]
    reviewed_by: Annotated[str, Field(max_length=128)] = ""


class ParallelAsked(BaseModel):
    """The comparison period, its criteria and the log."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    started_at: AwareDatetime
    ends_at: AwareDatetime
    criteria: list[CriterionAsked] = Field(default_factory=list, max_length=16)
    comparisons: list[ComparisonAsked] = Field(default_factory=list, max_length=MOST_COMPARISONS)


# ------------------------------------------------------------------ what is written: the cutover
class RevocationAsked(BaseModel):
    """One grant the old system held and how far its withdrawal got."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: Short
    requested_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None


class JobAsked(BaseModel):
    """One job on the old system, when it was disabled and what was seen afterwards."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Short
    disabled_at: AwareDatetime | None = None
    watched_until: AwareDatetime | None = None
    last_run_at: AwareDatetime | None = None


class BackupAsked(BaseModel):
    """The last copy taken of the old system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backup_id: Short
    taken_at: AwareDatetime
    verified: bool = False


class ActAsked(BaseModel):
    """One act off the delivery checklist, and who says it happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    leaf: Short
    performed_at: AwareDatetime
    recorded_by: Short


class CutoverAsked(BaseModel):
    """The cutover record. It cannot say it was reported complete: only the route that refuses it
    while an act is unrecorded can."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cut_over_at: AwareDatetime
    read_only_at: AwareDatetime | None = None
    archived_at: AwareDatetime | None = None
    revocations: list[RevocationAsked] = Field(default_factory=list, max_length=MOST_ITEMS)
    jobs: list[JobAsked] = Field(default_factory=list, max_length=MOST_ITEMS)
    final_backup: BackupAsked | None = None
    acts: list[ActAsked] = Field(default_factory=list, max_length=MOST_ACTS)


# ------------------------------------------------------------------------------ what is shown
class WhoAndWhen(BaseModel):
    """Who saved the current version and when. Null before anybody has."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    by: str
    at: datetime


class MigrationRegisterView(BaseModel):
    """The register as saved and what is outstanding in it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    saved: WhoAndWhen | None
    document: RegisterAsked | None
    #: True only when every item is decided and every permission mapped, and nothing contradicts.
    agreed: bool
    #: Everything outstanding, worst first, or empty.
    gaps: list[str]


class ParallelView(BaseModel):
    """The comparison period as saved, what it measured and what stands between it and a cutover."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    saved: WhoAndWhen | None
    document: ParallelAsked | None
    may_cut_over: bool
    gaps: list[str]
    #: The questions the two systems answered differently, in the order asked.
    disagreements: list[str]
    #: Those nobody has read yet.
    unreviewed: list[str]
    #: The questions only one system answered, which are neither agreement nor disagreement.
    only_one_answered: list[str]


class CutoverView(BaseModel):
    """The cutover as saved, everything still true of the old system, and whether it may be
    reported complete."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    saved: WhoAndWhen | None
    document: CutoverAsked | None
    #: Everything still true of a system somebody believes is switched off.
    gaps: list[str]
    #: The acts with a security consequence nobody has recorded doing, by task id.
    acts_outstanding: list[str]
    may_report_complete: bool
    #: Who reported it complete and when, or null. Only the route that builds `CompletedCutover`
    #: writes it.
    reported_complete: WhoAndWhen | None


class WorkspacePage(BaseModel):
    """The three documents and whether saving is switched on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inventory: MigrationRegisterView
    parallel: ParallelView
    cutover: CutoverView
    workspace_is_on: bool
    #: True while nothing here reaches the old system. A field, so the sentence leaves the page in
    #: the commit that makes it false.
    nothing_reaches_the_old_system: bool = True


# -------------------------------------------------------------------------- the machinery
def _not_answerable() -> Absent:
    return Absent("the migration screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    message = f"that was not saved: {reason}"
    return Absent(message, public_message=message)


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _who(saved: migration_record_store.Saved | None) -> WhoAndWhen | None:
    return None if saved is None else WhoAndWhen(by=saved.by, at=saved.at)


def _refusal(refused: Exception) -> Absent:
    """A refusal in the package's own words, or a summary of where a body did not read."""
    if isinstance(refused, ValidationError):
        found = "; ".join(
            f"{'.'.join(str(part) for part in one['loc']) or 'the document'}: {one['msg']}"
            for one in refused.errors(include_input=False)
        )
        return _refused_because(f"the document does not read: {found}")
    return _refused_because(str(refused))


def register_of(
    body: RegisterAsked,
) -> tuple[
    inventory.Catalogue, tuple[inventory.Decision, ...], tuple[inventory.PermissionMapping, ...]
]:
    """The package's own objects for a register body, refused in the package's words."""
    try:
        catalogue = inventory.Catalogue(
            surveyed=frozenset(inventory.Holding(one) for one in body.surveyed),
            items=tuple(
                inventory.Item(
                    item_id=one.item_id,
                    holding=inventory.Holding(one.holding),
                    name=one.name,
                    permissions=tuple(one.permissions),
                )
                for one in body.items
            ),
        )
        decisions = tuple(
            inventory.Decision(
                item_id=one.item_id,
                disposition=inventory.Disposition(one.disposition),
                because=one.because,
            )
            for one in body.decisions
        )
        mappings = tuple(
            inventory.PermissionMapping(
                old=one.old,
                capabilities=tuple(Capability(value=c) for c in one.capabilities),
                because=one.because,
            )
            for one in body.mappings
        )
    except (MigrationError, ValueError) as refused:
        raise _refusal(refused) from None
    return catalogue, decisions, mappings


def period_of(
    body: ParallelAsked, now: datetime
) -> tuple[parallel.Period, tuple[parallel.Comparison, ...]]:
    """The package's own period and log for a body. A criterion cannot be agreed in the future."""
    try:
        late = [one.measure for one in body.criteria if one.agreed_at > now]
        if late:
            msg = (
                f"the {late[0]} threshold is dated after this save, and an agreement cannot be "
                "agreed ahead of the day it was written down"
            )
            raise parallel.ParallelError(msg)
        period = parallel.Period(
            started_at=body.started_at,
            ends_at=body.ends_at,
            criteria=tuple(
                parallel.Criterion(
                    measure=parallel.Measure(one.measure),
                    direction=parallel.Direction(one.direction),
                    threshold=one.threshold,
                    agreed_at=one.agreed_at,
                    because=one.because,
                )
                for one in body.criteria
            ),
        )
        log_ = tuple(
            parallel.Comparison(
                question=one.question,
                asked_at=one.asked_at,
                verdict=parallel.Verdict(one.verdict),
                reviewed_by=one.reviewed_by,
            )
            for one in body.comparisons
        )
    except (MigrationError, ValueError) as refused:
        raise _refusal(refused) from None
    return period, log_


def decommission_of(body: CutoverAsked) -> cutover_module.Decommission:
    """The package's own cutover record for a body, refused in the package's words."""
    try:
        return cutover_module.Decommission(
            cut_over_at=body.cut_over_at,
            read_only_at=body.read_only_at,
            archived_at=body.archived_at,
            revocations=tuple(
                cutover_module.Revocation(
                    connector=one.connector,
                    requested_at=one.requested_at,
                    verified_at=one.verified_at,
                )
                for one in body.revocations
            ),
            jobs=tuple(
                cutover_module.ScheduledJob(
                    name=one.name,
                    disabled_at=one.disabled_at,
                    watched_until=one.watched_until,
                    last_run_at=one.last_run_at,
                )
                for one in body.jobs
            ),
            final_backup=(
                None
                if body.final_backup is None
                else cutover_module.FinalBackup(
                    backup_id=body.final_backup.backup_id,
                    taken_at=body.final_backup.taken_at,
                    verified=body.final_backup.verified,
                )
            ),
            acts=tuple(
                cutover_module.ActRecord(
                    leaf=one.leaf, performed_at=one.performed_at, recorded_by=one.recorded_by
                )
                for one in body.acts
            ),
        )
    except (MigrationError, ValueError) as refused:
        raise _refusal(refused) from None


def register_view(saved: migration_record_store.Saved | None) -> MigrationRegisterView:
    if saved is None:
        return MigrationRegisterView(saved=None, document=None, agreed=False, gaps=[])
    document = RegisterAsked.model_validate(saved.body)
    catalogue, decisions, mappings = register_of(document)
    gaps = inventory.catalogue_gaps(catalogue, decisions, mappings)
    return MigrationRegisterView(
        saved=_who(saved), document=document, agreed=not gaps, gaps=list(gaps)
    )


def parallel_view(saved: migration_record_store.Saved | None, now: datetime) -> ParallelView:
    if saved is None:
        return ParallelView(
            saved=None,
            document=None,
            may_cut_over=False,
            gaps=[],
            disagreements=[],
            unreviewed=[],
            only_one_answered=[],
        )
    document = ParallelAsked.model_validate(saved.body)
    period, log_ = _period_as_stored(document)
    gaps = parallel.cutover_gaps(period, log_, now=now)
    return ParallelView(
        saved=_who(saved),
        document=document,
        may_cut_over=parallel.may_cut_over(period, log_, now=now),
        gaps=list(gaps),
        disagreements=[one.question for one in parallel.disagreements(log_)],
        unreviewed=[one.question for one in parallel.unreviewed(log_)],
        only_one_answered=[one.question for one in parallel.unanswered(log_)],
    )


def _period_as_stored(
    document: ParallelAsked,
) -> tuple[parallel.Period, tuple[parallel.Comparison, ...]]:
    """A stored period read back through the package's constructors, which are the ones that
    refuse a threshold agreed after the period began. A stored criterion may not be dated after
    the save it came from, which the route checked at the time."""
    far = datetime.max.replace(tzinfo=document.started_at.tzinfo)
    return period_of(document, far)


def cutover_view(saved: migration_record_store.Saved | None) -> CutoverView:
    if saved is None:
        return CutoverView(
            saved=None,
            document=None,
            gaps=[],
            acts_outstanding=[],
            may_report_complete=False,
            reported_complete=None,
        )
    body = dict(saved.body)
    reported = body.pop("reported_complete", None)
    document = CutoverAsked.model_validate(body)
    record = decommission_of(document)
    return CutoverView(
        saved=_who(saved),
        document=document,
        gaps=list(cutover_module.decommission_gaps(record)),
        acts_outstanding=list(cutover_module.security_acts_outstanding(record)),
        may_report_complete=cutover_module.may_report_complete(record),
        reported_complete=(
            None
            if not isinstance(reported, dict)
            else WhoAndWhen(by=str(reported["by"]), at=datetime.fromisoformat(str(reported["at"])))
        ),
    )


async def _page(session: AsyncSession, now: datetime) -> WorkspacePage:
    return WorkspacePage(
        inventory=register_view(await migration_record_store.newest(session, RecordKind.REGISTER)),
        parallel=parallel_view(
            await migration_record_store.newest(session, RecordKind.PARALLEL), now
        ),
        cutover=cutover_view(await migration_record_store.newest(session, RecordKind.CUTOVER)),
        workspace_is_on=await is_on(session, MIGRATION_WORKSPACE),
    )


async def _switched_on(session: AsyncSession) -> None:
    if not await is_on(session, MIGRATION_WORKSPACE):
        raise _refused_because(
            "keeping a migration is switched off for this install; switch it on from Features"
        )


router = APIRouter(prefix=API_PREFIX, tags=["migration"])


@router.get("/migration", response_model=WorkspacePage, responses=COMMON_RESPONSES)
async def workspace(request: Request, asked: Asked) -> WorkspacePage:
    """The register, the comparison period and the cutover, as saved, with what is outstanding."""
    if not may_run_a_migration(asked.reach, asked.now):
        log.info("migration screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        return await _page(session, asked.now)


@router.put("/migration/register", response_model=MigrationRegisterView, responses=COMMON_RESPONSES)
async def save_register(
    request: Request, body: RegisterAsked, asked: Asked
) -> MigrationRegisterView:
    """Save a version of the register: what the old system holds, what happens to each of it and
    what its permissions become. The gaps are computed from what was saved and not stored."""
    if not may_run_a_migration(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        register_of(body)
        await migration_record_store.save(
            session, RecordKind.REGISTER, body.model_dump(mode="json"), by=asked.caller.principal.id
        )
        saved = await migration_record_store.newest(session, RecordKind.REGISTER)
        await session.commit()
    log.info("migration register saved", principal=asked.caller.principal.id)
    return register_view(saved)


@router.put("/migration/parallel", response_model=ParallelView, responses=COMMON_RESPONSES)
async def save_parallel(request: Request, body: ParallelAsked, asked: Asked) -> ParallelView:
    """Save a version of the comparison period. A threshold agreed after the period began, or
    dated after this save, is refused."""
    if not may_run_a_migration(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        period_of(body, asked.now)
        await migration_record_store.save(
            session, RecordKind.PARALLEL, body.model_dump(mode="json"), by=asked.caller.principal.id
        )
        saved = await migration_record_store.newest(session, RecordKind.PARALLEL)
        await session.commit()
    log.info("migration period saved", principal=asked.caller.principal.id)
    return parallel_view(saved, asked.now)


@router.put("/migration/cutover", response_model=CutoverView, responses=COMMON_RESPONSES)
async def save_cutover(request: Request, body: CutoverAsked, asked: Asked) -> CutoverView:
    """Save a version of the cutover record. It carries no completion: a version saved after one was
    reported is a cutover that has not been reported."""
    if not may_run_a_migration(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        decommission_of(body)
        await migration_record_store.save(
            session, RecordKind.CUTOVER, body.model_dump(mode="json"), by=asked.caller.principal.id
        )
        saved = await migration_record_store.newest(session, RecordKind.CUTOVER)
        await session.commit()
    log.info("migration cutover saved", principal=asked.caller.principal.id)
    return cutover_view(saved)


@router.post("/migration/cutover/complete", response_model=CutoverView, responses=COMMON_RESPONSES)
async def report_cutover_complete(request: Request, asked: Asked) -> CutoverView:
    """Report the saved cutover complete, or say which unrecorded act stops it.

    `CompletedCutover` is built from the saved record and the caller's own name, and cannot be built
    while an act with a security consequence is unrecorded, so the refusal is the package's own and
    names each act.
    """
    if not may_run_a_migration(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        saved = await migration_record_store.newest(session, RecordKind.CUTOVER)
        if saved is None:
            raise _refused_because("no cutover has been saved, so there is nothing to report")
        body = dict(saved.body)
        body.pop("reported_complete", None)
        record = decommission_of(CutoverAsked.model_validate(body))
        try:
            cutover_module.CompletedCutover(record=record, reported_by=asked.caller.principal.id)
        except MigrationError as refused:
            raise _refused_because(str(refused)) from None
        body["reported_complete"] = {
            "by": asked.caller.principal.id,
            "at": asked.now.isoformat(),
        }
        await migration_record_store.save(
            session, RecordKind.CUTOVER, body, by=asked.caller.principal.id
        )
        latest = await migration_record_store.newest(session, RecordKind.CUTOVER)
        await session.commit()
    log.info("migration cutover reported complete", principal=asked.caller.principal.id)
    return cutover_view(latest)
