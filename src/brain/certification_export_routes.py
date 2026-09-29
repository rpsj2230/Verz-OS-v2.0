"""The access certification report, exported from the Access review screen (M27.15.21).

The owner asked for the people list, the department structure and "an access certification report"
to each export from the console, "carrying only rows the exporter may read and no count of the
rest". The review screen already answers who may decide which holding, row by row
(`brain.govern_people_routes.reviewable`), so the report is that screen's rows and nothing else:
every grant and pack this reviewer could have written, who holds it, who granted it and why, when it
lapses, and its last review, one line each.

**The report is the review's own rows, so it cannot show more than the screen.** The route asks the
screen's read first, loads the holdings the screen loads, keeps each only when `reviewable` would
list it, and writes those. A holding the reviewer may not decide is absent from the file exactly as
it is absent from the page, and the file carries no line saying how many were left out.

**Recorded before it is handed over.** The document is built, its sha256 taken, and
`ops.data_export` written as a readable export under the exporter with the reason and reference
they gave (`brain.ops.data_export_store.ReportRecords`); `0053`'s trigger appends the `publish`
entry in the same commit. Only then is the document returned, for the reason
`brain.ops.data_export_store.THE_ROW_AND_THE_DOCUMENT_COMMIT_TOGETHER` gives. A failure before
the commit returns nothing and records nothing.

**People by name.** The holder's name is on the row; who granted it and who last decided it are read
by `brain.people_names` for exactly the ids on the rows written. A cell that begins with a formula
character is prefixed, because a value from the database is data and never a formula.

Rejected: building the report in the browser from the rows on screen. That is the kit's export of
what is drawn, which a person already has, and it leaves no record that the report left the
building, which is what an auditor asks of a certification.

Task ids: M27.15.21
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Failed
from brain.data_transfer_routes import ExportTakenView, record_view
from brain.govern_people_routes import (
    ACCESS_REVIEW_SCREEN,
    MAX_ROWS,
    ReviewRowView,
    _not_answerable,
    _trace_id,
    review_row,
    review_store_of,
    reviewable,
)
from brain.ops.data_export_store import ReportRecords, StoredExports
from brain.ops.export import ExportReason
from brain.people_names import names_for
from brain.routing_routes import sessions_of
from brain.tables.data_export import REFERENCE_PATTERN, ExportDataSet

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["govern"])

CERTIFICATION_EXPORT_PATH: Final = "/govern/access-review/export"

#: What a success says.
REPORT_TAKEN: Final = (
    "The certification report was recorded on the Exports log under your name and is being saved "
    "to your computer. It is not kept on the server."
)

#: Said as well when the review loaded its most rows, which is a fact about the load, not a count.
THE_REVIEW_LOADED_ITS_MOST_ROWS: Final = (
    " The review read the most grants one load reads, so the report may not hold every grant you "
    "may review."
)

#: The report's columns, in order.
COLUMNS: Final = (
    "Person",
    "Department",
    "Holds",
    "Kind",
    "Capabilities",
    "Scope",
    "Granted by",
    "Granted at",
    "Why it was granted",
    "Lapses",
    "Last review",
    "Reviewed by",
    "Reviewed at",
)

#: A spreadsheet opens a cell starting with one of these as a formula.
FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")


class CertificationAsked(BaseModel):
    """Why the report is leaving, as a closed word, and the ticket or matter it is for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: ExportReason
    reason_reference: Annotated[
        str, StringConstraints(strip_whitespace=True, pattern=REFERENCE_PATTERN, max_length=64)
    ]


def report_records_of(request: Request) -> ReportRecords:
    """`app.state.report_records` when something put one there, the database otherwise."""
    found = getattr(request.app.state, "report_records", None)
    if isinstance(found, ReportRecords):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredExports(sessions)


def _cell(value: str) -> str:
    return f"'{value}" if value.startswith(FORMULA_START) else value


def scope_words(scope: Mapping[str, Any]) -> str:
    """A scope's clauses as the console spells them, joined; everything for an empty scope."""
    clauses = scope.get("clauses") or ()
    words = [
        f"{one.get('field', '')} {one.get('op', '')} {one.get('value', '')}".strip()
        for one in clauses
        if isinstance(one, Mapping)
    ]
    return "; ".join(words) if words else "everything"


def report(rows: Sequence[ReviewRowView], people: Mapping[str, str]) -> str:
    """The rows as CSV, one line each, with a header line and nothing about any other row."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        holds = row.capabilities[0] if row.pack is None and row.capabilities else f"{row.pack} pack"
        writer.writerow(
            [
                _cell(one)
                for one in (
                    row.display_name or people.get(row.principal_id, ""),
                    row.department or "",
                    holds,
                    row.kind.value,
                    ", ".join(row.capabilities),
                    scope_words(row.scope),
                    people.get(row.granted_by, ""),
                    row.granted_at.isoformat(),
                    row.reason,
                    "" if row.lapses_at is None else row.lapses_at.isoformat(),
                    "never" if row.last_decision is None else row.last_decision.value,
                    "" if row.last_decided_by is None else people.get(row.last_decided_by, ""),
                    "" if row.last_decided_at is None else row.last_decided_at.isoformat(),
                )
            ]
        )
    return out.getvalue()


@router.post(CERTIFICATION_EXPORT_PATH, response_model=ExportTakenView, responses=COMMON_RESPONSES)
async def export_certification(
    request: Request, body: CertificationAsked, asked: Asked
) -> JSONResponse:
    """The review's rows as a report: recorded on the Exports log, then handed over once."""
    if not permitted(screen(ACCESS_REVIEW_SCREEN).read, asked.reach, asked.now):
        log.info("certification export not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("access review")
    holdings, decided, full = await review_store_of(request).holdings(limit=MAX_ROWS)
    rows: list[ReviewRowView] = []
    for holding in holdings:
        grants = reviewable(holding, asked.reach, asked.now)
        if grants is not None:
            rows.append(review_row(holding, grants, decided.get(holding.row.id)))
    people = await names_for(
        request,
        {one.principal_id for one in rows}
        | {one.granted_by for one in rows}
        | {one.last_decided_by for one in rows if one.last_decided_by is not None},
    )
    document = report(rows, people)
    taken = await report_records_of(request).record_report(
        data_set=ExportDataSet.ACCESS_CERTIFICATION,
        actor=asked.reach.principal_id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id() or "untraced",
        reason=body.reason,
        reason_reference=body.reason_reference,
        at=asked.now,
        entries=len(rows),
        document_digest=hashlib.sha256(document.encode("utf-8")).hexdigest(),
    )
    log.info("certification report taken", principal=asked.reach.principal_id, entries=len(rows))
    answered = ExportTakenView(
        export=record_view(taken),
        filename=f"{taken.data_set.value}-{taken.export_id}.csv",
        document=document,
        told=REPORT_TAKEN + (THE_REVIEW_LOADED_ITS_MOST_ROWS if full else ""),
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
