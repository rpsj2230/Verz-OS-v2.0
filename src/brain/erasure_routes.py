"""What the Retention and erasure screen needs beside the report: who may act, what each act does,
the export log, and the queue of erasure requests with the one write that files one.

`brain.retention_routes` serves the newest retention report and the four writes that decide
whether the sweep acts: release, withdrawal, placing a hold and lifting one. This is the rest of
the screen. It decides nothing `brain.retention_routes` decides, and nothing
`brain.ops.erasure_store` decides about carrying a request out.

**Who may act is a function per authority, called and never restated.** `may_release` and
`may_hold` are `brain.retention_routes`', and `may_erase` is this module's, the same shape: the
authority held over everything, which is the only form a write that reaches every store accepts.
The flags decide whether a control is drawn, and the write route decides again whatever this said.
See `A_FLAG_THAT_DRAWS_A_BUTTON_IS_NOT_THE_DECISION_TO_ACCEPT_ONE`.

**Filing a request needs `admin:erasure` over everything and the screen.** An erasure reaches every
store at once and the queue carries it out without asking anybody again, so a department's grant of
the authority is not one, for the reason a hold scoped to one department is not a hold. The screen
is required as well because the person filing has to be able to read the queue the request lands
in; a request filed by somebody who cannot see what it did is a deletion nobody followed up. See
`A_REQUEST_FILED_BY_SOMEBODY_WHO_CANNOT_READ_THE_QUEUE_IS_FOLLOWED_UP_BY_NOBODY`.

**What each act does is written here, in the words a confirmation shows.** `docs/admin-console.md`
requires a destructive action to say what will happen and to what, and filing an erasure is the
most destructive act the console offers: `ERASING` is the sentence, and it says what is removed,
what is retired and still stored, what is kept and what is not reached, because every one of those
is true today and a confirmation that left one out would be the one read as a promise.

**The queue is `brain.console.govern_surfaces.deletion_rows`, and every request sits nowhere.** Two
ways in: the reader is the person the request is about, or a grant of the Retention screen's
capability admits where the request sits. A request is placed at `brain.console.govern.NOWHERE`,
which only a company-wide grant admits, and not at the person's department, because the erasure
retires the person's own row, so a placement read off it would move the request out of its
department's reach part-way through, and a department admin would watch requests vanish. See
`A_REQUEST_SITS_NOWHERE_BECAUSE_THE_ERASURE_RETIRES_WHERE_IT_WOULD_SIT`.

**The export log is `brain.console.govern_surfaces.export_log`, over `ops.data_export`.** Every row
an export left is read back and each is handed to that function, which admits it under the Exports
screen's own capability in a scope that reaches it. An audit trail window covers everybody, so it
sits nowhere and is read by a company-wide grant of `read:export` and by nobody else. A reader who
may open the Retention screen and holds no such grant is told so by a flag, rather than shown an
empty table that reads as nothing having left the building.

**The screen's question is asked first**, with `brain.console.reads.permitted`, before any
authority and before the database, so a caller who may not open the screen learns nothing.

Task ids: M27.7.24
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.audit.ledger import IDENTIFIER
from brain.console.govern import NOWHERE, Placed, _in_reach
from brain.console.govern_surfaces import (
    EXPORT_LOG_SCREEN,
    RETENTION_SCREEN,
    DeletionRow,
    deletion_rows,
    erasure_request,
    export_log,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.data_export_store import ExportLog, StoredExports, TakenExport
from brain.ops.erasure_store import (
    ErasureRecord,
    ErasureRecords,
    ErasureRefusedError,
    StoredErasures,
)
from brain.ops.export import ExportAudit
from brain.ops.retention import HORIZONS, Horizon, Store
from brain.retention_routes import may_hold, may_release
from brain.routing_routes import sessions_of
from brain.tables.data_export import REFERENCE_PATTERN

log = structlog.get_logger()

#: The screen this route serves beside the report. Bound to the registry.
THE_SCREEN: Final = RETENTION_SCREEN

#: How many requests and exports the screen is shown, newest first.
QUEUE_SHOWN: Final = 100
EXPORTS_SHOWN: Final = 100

# ------------------------------------------------------------------ written-down reasons
#: Why the flags are the authorities' functions and the route still decides.
A_FLAG_THAT_DRAWS_A_BUTTON_IS_NOT_THE_DECISION_TO_ACCEPT_ONE: Final = (
    "may_release, may_hold and may_erase decide whether a control is drawn, and the write route "
    "asks the same functions again when it is pressed. A copy of any rule here would be correct "
    "the day it was written and would drift, and the drift would be a button for somebody the "
    "route refuses or no button for somebody it accepts."
)

#: Why filing needs the screen as well as the authority.
A_REQUEST_FILED_BY_SOMEBODY_WHO_CANNOT_READ_THE_QUEUE_IS_FOLLOWED_UP_BY_NOBODY: Final = (
    "The queue says what each erasure removed, retired, kept and could not reach, and an erasure "
    "is incomplete on every install today. A caller holding admin:erasure and not the Retention "
    "screen could file one and never read what it did, so nobody who asked for the deletion would "
    "ever see that it did not reach the recordings."
)

#: Why a request is placed nowhere rather than at the person's department.
A_REQUEST_SITS_NOWHERE_BECAUSE_THE_ERASURE_RETIRES_WHERE_IT_WOULD_SIT: Final = (
    "The only place a request could be placed is the department on the person's own row, and the "
    "erasure retires that row. A placement read off it would move the request out of its "
    "department's reach the moment the queue ran, so a department admin would watch requests "
    "disappear as they were carried out. Placed nowhere, a request is read by a company-wide grant "
    "and by the person it is about, and by nobody whose view of it changes as it runs."
)

# ------------------------------------------------------------ what each act does, in words
#: What releasing the sweep does, as a confirmation shows it beside the report's counts.
RELEASING: Final = (
    "Releasing lets the sweep act. From its next run it removes what is past its window in every "
    "store it reaches, keeps everything a legal hold covers, and leaves alone what it queued for "
    "the rule that removes it and every store it could not reach. The counts are from the report "
    "you read; anything that passes its window before the next run is removed as well. "
    "Withdrawing the release puts the sweep back to reporting, and nothing already removed comes "
    "back."
)

#: What withdrawing the release does.
WITHDRAWING: Final = (
    "Withdrawing puts the sweep back to reporting. Its next run removes nothing and writes a "
    "report of what it would have removed. Nothing it removed while released is brought back."
)

#: What placing a hold does.
HOLDING: Final = (
    "A legal hold stops the sweep removing anything about the people it names, or anything they "
    "did, from the moment it is placed until it is lifted, including what is written after it is "
    "placed. A store that cannot tell which of its rows a hold covers is not swept at all while "
    "the hold stands. The hold is recorded with your name, and it is lifted rather than ever "
    "deleted."
)

#: What lifting a hold does.
LIFTING: Final = (
    "Lifting a hold lets the sweep remove what the hold was keeping, on the sweep's next released "
    "run, once each item is past its window. The hold stays on record with who placed it, who "
    "lifted it and when."
)

#: What filing an erasure request does. Every clause is true today; see the module docstring.
ERASING: Final = (
    "The request is recorded with your name and carried out on the queue's next run, which comes "
    "round every quarter of an hour, without anybody being asked again. If a legal hold covers the "
    "person when it runs, nothing is touched "
    "and the request is finished as held. Otherwise every store in the database is worked through: "
    "rows the application may delete are removed, rows in tables that keep their trail are "
    "retired, which makes them unreadable to everybody and leaves them stored, and rows in tables "
    "that neither delete nor retire are kept and counted. Recordings, attachments, the answer "
    "cache and the retrieval index are not reached, and a backup taken before the request holds "
    "everything until it rotates out. The person's account and sign-in are retired with the rest. "
    "Nothing retired or removed can be brought back from this screen."
)

#: What the export log lists, and what it cannot.
EXPORTS_ARE_LISTED: Final = (
    "Every export taken from this install is listed with who took it, why, when, what window of "
    "the audit trail it covered and the digest of the document handed over. Only exports taken "
    "through the console are recorded; a copy made some other way leaves no row."
)

#: What the queue lists, and what it cannot.
ERASURES_ARE_LISTED: Final = (
    "Each request is listed with who filed it and when, and once it has run, how it finished and "
    "what each store did. A request finished as incomplete names the stores it could not reach and "
    "the rows it kept, and those still hold data about the person."
)

#: What a reader who may open the screen and may not read exports is told instead of a table.
EXPORT_LOG_NOT_YOURS: Final = (
    "Reading the export log needs the exports read over the whole company, because an audit trail "
    "export covers everybody."
)


# ------------------------------------------------------------------------ authorities
#: Files a request to erase somebody's data. Held over everything or not at all.
ERASURE_AUTHORITY: Final = Capability(value="admin:erasure")


def may_erase(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may file an erasure request: the authority, over everything."""
    return _in_reach(reach, ERASURE_AUTHORITY, NOWHERE, now)


def may_read_exports(reach: EntitlementSet, now: datetime) -> bool:
    """Whether an audit trail export, which sits nowhere, is one this reader may be told about."""
    return _in_reach(reach, screen(EXPORT_LOG_SCREEN).read.requires, NOWHERE, now)


# ------------------------------------------------------------------------ the shapes
class KeptView(BaseModel):
    """How long one class of thing is kept, and why that answer. `brain.ops.retention.Horizon`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_class: str
    lifetime: str
    #: Set exactly when the lifetime is a fixed window.
    days: int | None
    because: str


class RetentionControlsView(BaseModel):
    """Which controls this reader may be shown, what each does, and what the two lists hold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    may_release: bool
    may_hold: bool
    may_erase: bool
    may_read_exports: bool
    releasing: str
    withdrawing: str
    holding: str
    lifting: str
    erasing: str
    exports: str
    erasures: str
    exports_not_yours: str
    kept: list[KeptView]


class StoreErasedView(BaseModel):
    """What a finished request did in one store. Counts and a sentence, never a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: str
    disposition: str
    reached: bool
    removed: int
    retired: int
    kept: int
    because: str


class ErasureRequestView(BaseModel):
    """One request in the queue, and how it finished where it has."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    subject_id: str
    reason_reference: str
    requested_by: str
    requested_at: datetime
    finished_at: datetime | None
    #: `erased`, `held` or `incomplete`, or None while it waits.
    outcome: str | None
    stores: list[StoreErasedView]
    holds: list[str]


class ErasureQueueView(BaseModel):
    """The requests this reader may be shown, newest first. No count of the rest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests: list[ErasureRequestView]


class ErasureBody(BaseModel):
    """A request to file. The person by reference, and the matter it arrived under."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_id: str = Field(pattern=IDENTIFIER)
    reason_reference: str = Field(pattern=REFERENCE_PATTERN)


class ErasureFiled(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    subject_id: str
    requested_at: datetime


class ExportLogEntryView(BaseModel):
    """One export as `ops.data_export` recorded it. Never the document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    export_id: str
    data_set: str
    requested_by: str
    reason: str
    reason_reference: str
    produced_at: datetime
    #: `chain` or `readable`. A readable export has no sequence range and no verdict; see
    #: `brain.tables.data_export.A_READABLE_EXPORT_NAMES_NO_WINDOW`.
    form: str
    first_seq: int | None
    last_seq: int | None
    entries: int
    verified: bool | None
    document_digest: str


class ExportLogView(BaseModel):
    """The exports this reader may be told about, newest first. No count of the rest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exports: list[ExportLogEntryView]


def kept_view(one: Horizon) -> KeptView:
    """One horizon, copied field by field."""
    return KeptView(
        data_class=one.data_class.value,
        lifetime=one.lifetime.value,
        days=one.days,
        because=one.because,
    )


def request_view(record: ErasureRecord) -> ErasureRequestView:
    """One request, copied field by field from what the store read."""
    return ErasureRequestView(
        request_id=record.request_id,
        subject_id=record.subject_id,
        reason_reference=record.reason_reference,
        requested_by=record.requested_by,
        requested_at=record.requested_at,
        finished_at=record.finished_at,
        outcome=None if record.outcome is None else record.outcome.value,
        stores=[
            StoreErasedView(
                store=str(one["store"]),
                disposition=str(one["disposition"]),
                reached=bool(one["reached"]),
                removed=int(one["removed"]),
                retired=int(one["retired"]),
                kept=int(one["kept"]),
                because=str(one["because"]),
            )
            for one in record.stores
        ],
        holds=list(record.holds),
    )


def queued(record: ErasureRecord) -> Placed[DeletionRow]:
    """A request as the queue's surface decides over it: the row, placed nowhere.

    See `A_REQUEST_SITS_NOWHERE_BECAUSE_THE_ERASURE_RETIRES_WHERE_IT_WOULD_SIT`.
    """
    row = replace(
        erasure_request(record.subject_id, record.requested_at), completed_at=record.finished_at
    )
    return Placed(record=row, where=NOWHERE)


def logged(taken: TakenExport) -> Placed[ExportAudit]:
    """An audit trail export as the export log decides over it: everybody's, placed nowhere."""
    return Placed(
        record=ExportAudit(
            export_id=taken.export_id,
            at=taken.produced_at,
            requested_by=taken.requested_by,
            reason=taken.reason,
            reason_reference=taken.reason_reference,
            stores=(Store.AUDIT,),
            subjects=(),
            all_subjects=True,
            items=taken.entries,
        ),
        where=NOWHERE,
    )


def export_view(taken: TakenExport) -> ExportLogEntryView:
    return ExportLogEntryView(
        export_id=taken.export_id,
        data_set=taken.data_set.value,
        requested_by=taken.requested_by,
        reason=taken.reason.value,
        reason_reference=taken.reason_reference,
        produced_at=taken.produced_at,
        form=taken.form.value,
        first_seq=taken.first_seq,
        last_seq=taken.last_seq,
        entries=taken.entries,
        verified=taken.verified,
        document_digest=taken.document_digest,
    )


# ------------------------------------------------------------------------ the wiring
def erasure_records_of(request: Request) -> ErasureRecords:
    """What `app.state.erasure_records` holds, or the database, or one process fault."""
    found = getattr(request.app.state, "erasure_records", None)
    if isinstance(found, ErasureRecords):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredErasures(sessions)


def export_log_of(request: Request) -> ExportLog:
    """What `app.state.export_log` holds, or the database, or one process fault."""
    found = getattr(request.app.state, "export_log", None)
    if isinstance(found, ExportLog):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredExports(sessions)


def _trace_id() -> str:
    found = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    # The ledger's trace grammar admits no empty value, and a request the middleware did not see
    # has none, so it is named for what it is.
    return found or "untraced"


def _not_answerable() -> Absent:
    """The refusal the Retention screen makes, in `brain.retention_routes`' own words."""
    return Absent(f"the {THE_SCREEN} screen is not answerable for this caller")


def _not_writable() -> Absent:
    """The one refusal filing makes to a caller without the authority or the screen."""
    return Absent("that erasure request is not writable by this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what they need to fix."""
    message = f"that erasure request was not filed: {reason}"
    return Absent(message, public_message=message)


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get(
    "/govern/retention/controls", response_model=RetentionControlsView, responses=COMMON_RESPONSES
)
async def retention_controls(asked: Asked) -> RetentionControlsView:
    """Who may act on the Retention screen, what each act does, and what the two lists hold.

    The screen first, then each authority, each asked of its own function. No database: every
    answer here is a decision about the reader or a declaration.
    """
    if not permitted(screen(THE_SCREEN).read, asked.reach, asked.now):
        log.info("retention controls not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return RetentionControlsView(
        may_release=may_release(asked.reach, asked.now),
        may_hold=may_hold(asked.reach, asked.now),
        may_erase=may_erase(asked.reach, asked.now),
        may_read_exports=may_read_exports(asked.reach, asked.now),
        releasing=RELEASING,
        withdrawing=WITHDRAWING,
        holding=HOLDING,
        lifting=LIFTING,
        erasing=ERASING,
        exports=EXPORTS_ARE_LISTED,
        erasures=ERASURES_ARE_LISTED,
        exports_not_yours=EXPORT_LOG_NOT_YOURS,
        kept=[kept_view(one) for one in HORIZONS],
    )


@router.get("/govern/erasures", response_model=ErasureQueueView, responses=COMMON_RESPONSES)
async def erasure_queue(request: Request, asked: Asked) -> ErasureQueueView:
    """The erasure requests this reader may be shown, newest first.

    The screen's question before the database, then every newest request read, then
    `deletion_rows`, which keeps the ones this reader may see. Kept by identity rather than by
    equality, because two requests about one person filed at one instant are two rows that
    compare equal, and a filter by equality would show both when one was admitted.
    """
    if not permitted(screen(THE_SCREEN).read, asked.reach, asked.now):
        log.info("erasure queue not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    records = await erasure_records_of(request).requests(limit=QUEUE_SHOWN)
    placed = [(record, queued(record)) for record in records]
    shown = {id(row) for row in deletion_rows([one for _, one in placed], asked.reach, asked.now)}
    return ErasureQueueView(
        requests=[request_view(record) for record, one in placed if id(one.record) in shown]
    )


@router.post("/govern/erasures", response_model=ErasureFiled, responses=COMMON_RESPONSES)
async def file_erasure(request: Request, body: ErasureBody, asked: Asked) -> ErasureFiled:
    """File a request to erase one person's data. The worker's queue carries it out.

    Both questions before the database: the authority over everything, and the screen the queue
    is read on. See
    `A_REQUEST_FILED_BY_SOMEBODY_WHO_CANNOT_READ_THE_QUEUE_IS_FOLLOWED_UP_BY_NOBODY`. The instant
    is the request's and never the body's.
    """
    if not may_erase(asked.reach, asked.now) or not permitted(
        screen(THE_SCREEN).read, asked.reach, asked.now
    ):
        log.info("erasure request not writable", principal=asked.caller.principal.id)
        raise _not_writable()
    try:
        filed = await erasure_records_of(request).file(
            subject_id=body.subject_id,
            reason_reference=body.reason_reference,
            actor=asked.reach.principal_id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
            at=asked.now,
        )
    except ErasureRefusedError as refused:
        raise _refused_because(refused.reason) from None
    return ErasureFiled(
        request_id=filed.request_id, subject_id=filed.subject_id, requested_at=filed.requested_at
    )


@router.get("/govern/retention/exports", response_model=ExportLogView, responses=COMMON_RESPONSES)
async def exports_taken(request: Request, asked: Asked) -> ExportLogView:
    """The exports this reader may be told were taken, newest first.

    The screen's question before the database, then every newest export read, then `export_log`,
    which keeps the ones this reader may be told about, matched back by export id.
    """
    if not permitted(screen(THE_SCREEN).read, asked.reach, asked.now):
        log.info("export log not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    taken = await export_log_of(request).recent(limit=EXPORTS_SHOWN)
    admitted = {
        one.export_id for one in export_log([logged(one) for one in taken], asked.reach, asked.now)
    }
    return ExportLogView(exports=[export_view(one) for one in taken if one.export_id in admitted])
