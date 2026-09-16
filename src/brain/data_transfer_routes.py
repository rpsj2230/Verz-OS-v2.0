"""The Import and export screen over HTTP: what can move, and taking an audit trail export.

`brain.ops.data_transfer` holds the catalogue and every decision about an export;
`brain.ops.data_export_store` holds the transaction. This module asks them in order and decides
nothing either already decides.

**The listing is shown to anybody signed in to the console, and the records on it are the
reader's own.** The catalogue is the product's, identical on every install, and says nothing about
any company's data. `exportable` says whether this reader may take an audit trail export, which is
a fact about the reader. `exports` lists the exports this reader took and nobody else's, and is
read only for a reader who may take one: who else has taken exports is the Exports screen's
question, behind its own grant, and answering it here as well would be one set of rows behind two
decisions. See `YOUR_OWN_EXPORTS_AND_NOBODY_ELSES`.

**Taking an export is refused in one sentence before anything is judged or read**, unless the
reader holds `admin:export` and may read every entry the ledger could hold; see
`brain.ops.data_transfer.A_WHOLE_LEDGER_READER_IS_ASKED_BEFORE_THE_LEDGER_IS`. Then every problem
with the request is answered at once as a 422, of which an empty, oversized or broken window is
one, because a window is a field the person changes. A 200 carries the record and the document,
and only after the record has committed.

**The document travels in the response body, once.** It is line-delimited JSON of at most
`MAX_EXPORT_ENTRIES` lines and the console saves it as a file; nothing keeps it on the server. The
record keeps its digest, so the file can be matched to this export later.

Task ids: M27.8.16
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.audit.ledger import AuditEntry
from brain.core.errors import Absent, Failed
from brain.ops.data_export_store import ExportRecords, StoredExports, TakenExport
from brain.ops.data_transfer import (
    AN_EXPORT_IS_A_COPY_THAT_LEAVES_EVERY_GUARD_BEHIND,
    CATALOGUE,
    MAX_EXPORT_ENTRIES,
    THE_DOCUMENT_IS_HANDED_OVER_ONCE,
    AuditExportRefusedError,
    Direction,
    ExportField,
    ExportProblem,
    Produced,
    may_take_audit_export,
    produce_audit_export,
    request_problems,
)
from brain.ops.export import ExportReason
from brain.routing_routes import sessions_of
from brain.tables.data_export import ExportDataSet

log = structlog.get_logger()

#: Why the listing carries only the reader's own exports.
YOUR_OWN_EXPORTS_AND_NOBODY_ELSES: Final = (
    "The exports listed here are the ones you took. Who else has taken an export is shown on the "
    "Exports screen to whoever may read that log, and showing it here too would put one set of "
    "records behind two different decisions about who may see them."
)

#: What a success says.
EXPORT_TAKEN: Final = (
    "The export was recorded in the audit trail under your name and is being saved to your "
    "computer. It is not kept on the server."
)

#: Where the screen is read, and the one write beneath it.
DATA_TRANSFER_PATH: Final = "/data-transfer"
EXPORTS_PATH: Final = f"{DATA_TRANSFER_PATH}/exports"

#: How many of the reader's own exports the listing reads.
OWN_EXPORTS_SHOWN: Final = 20

# ------------------------------------------------------------------------ the shapes


class DataSetView(BaseModel):
    """One thing the code knows how to move, and whether this install can move it now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    direction: Direction
    carries: str
    runs: bool
    told: str


class ExportRecordView(BaseModel):
    """One export's record. Never the document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    export_id: str
    data_set: ExportDataSet
    reason: ExportReason
    reason_reference: str
    produced_at: datetime
    first_seq: int | None
    last_seq: int | None
    entries: int
    verified: bool
    document_digest: str


class DataTransferView(BaseModel):
    """The Import and export screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    catalogue: list[DataSetView]
    reasons: list[ExportReason]
    exportable: bool
    exports: list[ExportRecordView]
    export_told: str
    document_told: str
    own_exports_told: str
    max_entries: int


class ExportAsked(BaseModel):
    """An export request. The reason is a closed word; the reference is judged in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_set: str
    reason: str
    reason_reference: str
    since: datetime
    until: datetime


class ExportTakenView(BaseModel):
    """The record of the export just taken, and the document itself, once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    export: ExportRecordView
    filename: str
    document: str
    told: str


class ExportProblemView(BaseModel):
    """One thing wrong with an export request: the field, a stable code, and what to do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: ExportField
    code: str
    message: str


class ExportProblemsView(BaseModel):
    """Everything wrong with an export request. Nothing was read or recorded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: list[ExportProblemView]


# ------------------------------------------------------------------------- the wiring


def export_records_of(request: Request) -> ExportRecords:
    """What `app.state.export_records` holds, or the database, or one process fault."""
    found = getattr(request.app.state, "export_records", None)
    if isinstance(found, ExportRecords):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredExports(sessions)


def _trace_id() -> str:
    found = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    # The manifest's trace id has the ledger's grammar and may not be empty; a request the
    # middleware did not see has none, and is named for what it is.
    return found or "untraced"


def record_view(taken: TakenExport) -> ExportRecordView:
    return ExportRecordView(
        export_id=taken.export_id,
        data_set=taken.data_set,
        reason=taken.reason,
        reason_reference=taken.reason_reference,
        produced_at=taken.produced_at,
        first_seq=taken.first_seq,
        last_seq=taken.last_seq,
        entries=taken.entries,
        verified=taken.verified,
        document_digest=taken.document_digest,
    )


def filename_for(taken: TakenExport) -> str:
    """The name the console saves the document under: the data set and the window, no person."""
    return f"{taken.data_set.value}-{taken.first_seq}-{taken.last_seq}.jsonl"


def _problems(found: tuple[ExportProblem, ...]) -> JSONResponse:
    told = ExportProblemsView(
        problems=[
            ExportProblemView(field=one.field, code=one.code, message=one.message) for one in found
        ]
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _not_answerable() -> Absent:
    return Absent("an export is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["data-transfer"])


@router.get(DATA_TRANSFER_PATH, response_model=DataTransferView, responses=COMMON_RESPONSES)
async def data_transfer(request: Request, asked: Asked) -> DataTransferView:
    """What can be imported and exported, whether this reader may export, and their own exports."""
    exportable = may_take_audit_export(asked.reach, asked.now)
    exports: list[ExportRecordView] = []
    if exportable:
        taken = await export_records_of(request).taken_by(
            asked.reach.principal_id, limit=OWN_EXPORTS_SHOWN
        )
        exports = [record_view(one) for one in taken]
    return DataTransferView(
        catalogue=[
            DataSetView(
                key=one.key,
                label=one.label,
                direction=one.direction,
                carries=one.carries,
                runs=one.runs,
                told=one.told,
            )
            for one in CATALOGUE
        ],
        reasons=list(ExportReason),
        exportable=exportable,
        exports=exports,
        export_told=AN_EXPORT_IS_A_COPY_THAT_LEAVES_EVERY_GUARD_BEHIND,
        document_told=THE_DOCUMENT_IS_HANDED_OVER_ONCE,
        own_exports_told=YOUR_OWN_EXPORTS_AND_NOBODY_ELSES,
        max_entries=MAX_EXPORT_ENTRIES,
    )


_WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": ExportProblemsView, "description": "What is wrong with the request."},
}


@router.post(EXPORTS_PATH, response_model=ExportTakenView, responses=_WRITE_RESPONSES)
async def take_export(request: Request, body: ExportAsked, asked: Asked) -> JSONResponse:
    """Take an audit trail export: record it in the audit trail, then hand the document over."""
    if not may_take_audit_export(asked.reach, asked.now):
        log.info("export not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = request_problems(
        data_set=body.data_set,
        reason=body.reason,
        reason_reference=body.reason_reference,
        since=body.since,
        until=body.until,
    )
    if found:
        return _problems(found)
    reason = ExportReason(body.reason)
    trace_id = _trace_id()

    def produce(entries: Sequence[AuditEntry]) -> Produced:
        return produce_audit_export(
            entries,
            reader=asked.reach,
            reason=reason,
            trace_id=trace_id,
            at=asked.now,
        )

    try:
        taken, produced = await export_records_of(request).take_audit_export(
            since=body.since,
            until=body.until,
            limit=MAX_EXPORT_ENTRIES,
            actor=asked.reach.principal_id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_id,
            reason=reason,
            reason_reference=body.reason_reference,
            at=asked.now,
            produce=produce,
        )
    except AuditExportRefusedError as refused:
        return _problems((ExportProblem(ExportField.WINDOW, "window_refused", str(refused)),))
    except PermissionError as withheld:
        raise _not_answerable() from withheld
    log.info(
        "export taken",
        principal=asked.reach.principal_id,
        export_id=taken.export_id,
        data_set=taken.data_set.value,
        entries=taken.entries,
    )
    answered = ExportTakenView(
        export=record_view(taken),
        filename=filename_for(taken),
        document=produced.document,
        told=EXPORT_TAKEN,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
