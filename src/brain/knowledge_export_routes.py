"""The knowledge inventory, exported from the Knowledge screen, each document with who may read it.

`brain.ops.export.knowledge_export` kept each item's scope with it, was tested, and had no
caller; `brain.ops.data_transfer.CATALOGUE` said the knowledge export could not run. Needs-rupash
108 decided to build it (2026-09-29). This is the route that takes it, from the screen whose rows
it holds, and it is shaped on `brain.certification_export_routes` for the same reasons.

**What leaves is the inventory and never a document's text.** The owner's decision names the
inventory. A document's text is read through the passage policy and a sensitive read leaves its
own entry (`brain.knowledge_lifecycle_routes.version_text`), and a file taken out of the system can
carry neither, so putting text in an export would be the one way to read a document without either.
Each line says what the Knowledge list says: the title, its id, the kind, the state, the level and
department that decide who may read it, the steward, when it was added, how it was last verified
and by whom where the reader may be told, when it is next due for review and what it replaces.

**The inventory is the screen's own rows, so it cannot show more than the screen.** The route
loads what `GET /knowledge/documents` loads, keeps a document only when `Authority.may_see` admits
it, builds each row with `document_view` (which withholds a verifier the badge does not name to this
reader) and writes those. A document the reader may not see is absent from the file exactly as it is
absent from the list, and the file carries no line saying how many were left out. A reader who
holds no knowledge authority at all is refused before anything is read, in the sentence an unknown
route gets.

**The scope is carried, and checked on the way out.** `brain.ops.export.knowledge_inventory` holds
the same comparison `knowledge_export` makes: the scope derived from the exported visibility is
compared with the one the source derives, and a document that would leave with a different one
stops the export. The file states the level and the department, which is the whole of a document's
scope, and says in words who that reaches; a personal document says "its steward only" and never
carries the steward's id. Rejected: the scope as JSON in a cell. The two columns above are the
scope and rebuild it exactly, and a predicate in a spreadsheet cell invites an edit that reads as
valid.

**Recorded before it is handed over**, as the certification report is: the document is built, its
sha256 taken, and `ops.data_export` written as a readable export under the exporter with the reason
and reference they gave; `0053`'s trigger appends the `publish` entry in the same commit, and only
then is the document returned. A failure before the commit returns nothing and records nothing.

**A cell that begins with a formula character is prefixed**, because a title is a person's words
and never a formula.

Task ids: M25.3.3
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.certification_export_routes import FORMULA_START, report_records_of
from brain.core.errors import Absent
from brain.data_transfer_routes import ExportTakenView, record_view
from brain.knowledge.lifecycle import StoredItem
from brain.knowledge.lifecycle_store import MAX_ITEMS, documents, names_of
from brain.knowledge.visibility import Visibility
from brain.knowledge_lifecycle_routes import (
    DocumentView,
    authority_of,
    document_view,
    in_transaction,
    people_named_on,
)
from brain.ops.export import ExportReason, knowledge_inventory
from brain.tables.data_export import REFERENCE_PATTERN, ExportDataSet

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])

KNOWLEDGE_EXPORT_PATH: Final = "/knowledge/inventory"

#: What a success says.
INVENTORY_TAKEN: Final = (
    "The knowledge inventory was recorded on the Exports log under your name and is being saved "
    "to your computer. It is not kept on the server, and it holds no document's text."
)

#: Said as well when the list loaded its most documents, which is a fact about the load and not a
#: count of anything.
THE_LIST_LOADED_ITS_MOST_DOCUMENTS: Final = (
    " The list read the most documents one load reads, so the inventory may not hold every "
    "document you may see."
)

#: The refusal, which names the screen and nothing of the caller. An unknown route's sentence.
NOT_ANSWERABLE: Final = "the knowledge screen is not answerable for this caller"

#: What a document's level means for who may read it, in the words the file carries.
WHO_MAY_READ: Final = {
    Visibility.COMPANY: "everyone in the company",
    Visibility.DEPARTMENT: "people in {department}",
    Visibility.PERSONAL: "its steward only",
}

#: The inventory's columns, in order. The level and the department are the scope.
COLUMNS: Final = (
    "Document",
    "Document id",
    "Kind",
    "State",
    "Level",
    "Department",
    "Who may read it",
    "Steward",
    "Added",
    "Verification",
    "Verified by",
    "Verified at",
    "Review due",
    "Replaces",
)

A_DOCUMENT_LEAVES_WITH_ITS_SCOPE_AND_WITHOUT_ITS_TEXT: Final = (
    "The inventory states each document's level and department, which are its whole scope, and "
    "says in words who that reaches. It carries no document's text, because text read outside the "
    "system leaves behind the redaction and the sensitive-read record every reading in it makes."
)


class KnowledgeAsked(BaseModel):
    """Why the inventory is leaving, as a closed word, and the ticket or matter it is for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: ExportReason
    reason_reference: Annotated[
        str, StringConstraints(strip_whitespace=True, pattern=REFERENCE_PATTERN, max_length=64)
    ]


def _cell(value: str) -> str:
    return f"'{value}" if value.startswith(FORMULA_START) else value


def _when(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def who_may_read(row: DocumentView) -> str:
    """In words, who this document's level and department reach."""
    level = Visibility(row.level)
    return WHO_MAY_READ[level].format(department=row.department or "its department")


def inventory(rows: Sequence[DocumentView]) -> str:
    """The rows as CSV, one line each, with a header line and nothing about any other document."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                _cell(one)
                for one in (
                    row.title,
                    row.item_id,
                    row.kind_label,
                    row.state,
                    row.level,
                    row.department or "",
                    who_may_read(row),
                    row.steward_name or "",
                    _when(row.added_at),
                    row.verification,
                    row.verified_by_name or "",
                    _when(row.verified_at),
                    _when(row.review_by),
                    row.supersedes or "",
                )
            ]
        )
    return out.getvalue()


def kept_with_scope(items: Sequence[StoredItem]) -> None:
    """Stop the export when any of these would leave with a scope other than its own.

    The comparison of `brain.ops.export.knowledge_inventory`, asked of the rows about to be
    written, so an edit that flattens a level in this module's row building is refused here and
    not found in a file somebody else is reading.
    """
    knowledge_inventory(items)


@router.post(KNOWLEDGE_EXPORT_PATH, response_model=ExportTakenView, responses=COMMON_RESPONSES)
async def export_knowledge(request: Request, body: KnowledgeAsked, asked: Asked) -> JSONResponse:
    """The Knowledge list's rows as an inventory: recorded on the Exports log, then handed over."""
    authority = await authority_of(request, asked)
    if authority.reads is None and authority.adds is None:
        log.info("knowledge export not answerable", principal=asked.caller.principal.id)
        raise Absent(NOT_ANSWERABLE)

    async def load(session: AsyncSession) -> tuple[tuple[StoredItem, ...], bool, dict[str, str]]:
        found, full = await documents(session, limit=MAX_ITEMS)
        return found, full, await names_of(session, people_named_on(found))

    found, full, names = await in_transaction(request, asked, authority, load)
    seen = [one for one in found if authority.may_see(one)]
    kept_with_scope(seen)
    rows = [
        document_view(one, authority=authority, reader=asked.reach, now=asked.now, names=names)
        for one in seen
    ]
    document = inventory(rows)
    taken = await report_records_of(request).record_report(
        data_set=ExportDataSet.KNOWLEDGE,
        actor=asked.reach.principal_id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request() or "untraced",
        reason=body.reason,
        reason_reference=body.reason_reference,
        at=asked.now,
        entries=len(rows),
        document_digest=hashlib.sha256(document.encode("utf-8")).hexdigest(),
    )
    log.info("knowledge inventory taken", principal=asked.reach.principal_id, entries=len(rows))
    answered = ExportTakenView(
        export=record_view(taken),
        filename=f"{taken.data_set.value}-{taken.export_id}.csv",
        document=document,
        told=INVENTORY_TAKEN + (THE_LIST_LOADED_ITS_MOST_DOCUMENTS if full else ""),
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
