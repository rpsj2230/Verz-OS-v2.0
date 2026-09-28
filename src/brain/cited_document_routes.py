"""The document a citation links to, read at the reader's own reach (M8.1.2).

A document citation on the Ask screen names a document and a passage in it, and a citation nobody
can follow is a citation nobody checks, which `brain.gate.provenance` says in its first paragraph.
Until 2026-09-28 there was nowhere to follow one to: the Knowledge library lists items and says in
`console/src/App.tsx` that "an item has no page of its own", and no route returned a document's
words to a person. This is that route, and it is deliberately the smallest one: the passages of
one document, in reading order, at the reach the answer was computed at.

**It reads through the registered `knowledge.read_document` handler and the model lane's passage
policy, and through nothing else.** The handler puts the reader's reach inside the statement and
runs it under the row-level security `0009` put on `know.chunk`; the redactor then walks what came
back with `brain.gate.model_lane.PASSAGE_POLICY` at the same reach. Those are the two walls the
answer went through, so a passage the reader could have been cited is a passage they can open here,
and nothing else is. Rejected: reading `know.chunk` from this module, which would be a third
statement over the document plane with its own opinion of the reach. See
`A_CITED_DOCUMENT_IS_READ_THROUGH_THE_WALLS_THE_ANSWER_WENT_THROUGH`.

**A document the reader may not read and one that does not exist are one 404.** The handler returns
nothing for either, and the route answers both with the sentence an unknown record gets. A refusal
here would tell somebody typing references which documents exist; see `brain.core.errors`.

**The passage cited is found by the page, not by this route.** The citation's anchor names a chunk
and travels as the address's fragment, which is never sent to a server, so the reference to the
passage a person followed is not in any request log. The route returns the document's passages up
to `brain.knowledge.document_tools.MAX_PASSAGES`, says when it stopped there, and the page marks the
passage whose chunk the fragment names.

Task ids: M8.1.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final, cast

import structlog
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.envelope import TypedResult
from brain.core.errors import Absent, BrainError, Failed
from brain.core.redaction import ID_KEYS, redact
from brain.gate.model_lane import PASSAGE_POLICY
from brain.knowledge.document_tools import (
    MAX_PASSAGES,
    READ_DOCUMENT,
    DocumentRead,
    KnowledgePassage,
)
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

#: Why the page reads through the handler and the policy the answer did.
A_CITED_DOCUMENT_IS_READ_THROUGH_THE_WALLS_THE_ANSWER_WENT_THROUGH: Final = (
    "A citation is followed by the person it was shown to, so the document is read at their "
    "reach through the same handler and redacted by the same policy the answer's passages were. "
    "A passage they could have been cited is one they can open, and a passage withheld from the "
    "answer is withheld here, because the two reads are one read made twice."
)

#: The path, under the API prefix. A reference fits `ITEM_ID_PATTERN`, which the path refuses
#: otherwise before anything is looked up, identically for every reference.
CITED_DOCUMENT_PATH: Final = "/knowledge/documents/{document_id}"


class CitedPassage(BaseModel):
    """One passage as the reader may read it: where it is, and its words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    section: str = ""
    text: str
    #: When the stored copy was last written, where the reader may read it; empty otherwise.
    updated_at: str = ""


class CitedDocument(BaseModel):
    """One document's passages in reading order, at the reader's reach."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    #: The title, where the reader may read it; empty otherwise, and the page says the reference.
    title: str = ""
    passages: tuple[CitedPassage, ...]
    #: The read stopped at `MAX_PASSAGES`. Never how many more there are.
    truncated: bool = False


def _not_found(document_id: str) -> Absent:
    """One refusal for a document withheld and a document that does not exist."""
    return Absent(f"document {document_id!r} is not answerable for this caller")


def passages_of(document_id: str, records: tuple[dict[str, Any], ...]) -> CitedDocument | None:
    """The document as the reader may read it, or None when no passage with words survived.

    Built from the post-redaction records and from nothing else, so a title or a date the
    reader may not read is absent rather than blank, and a passage whose words were withheld
    is not listed.
    """
    mine = [record for record in records if record.get("document_id") == document_id]
    passages = tuple(
        CitedPassage(
            chunk_id=str(next(record[key] for key in ID_KEYS if key in record)),
            section=str(record.get("section") or ""),
            text=str(record["document"]),
            updated_at=str(record.get("updated_at") or ""),
        )
        for record in mine
        if record.get("document")
    )
    if not passages:
        return None
    titles = [str(record["title"]) for record in mine if record.get("title")]
    return CitedDocument(
        document_id=document_id, title=titles[0] if titles else "", passages=passages
    )


router = APIRouter(prefix=API_PREFIX, tags=["gate"])


@router.get(CITED_DOCUMENT_PATH, response_model=CitedDocument, responses=COMMON_RESPONSES)
async def cited_document(
    request: Request,
    document_id: Annotated[str, Path(pattern=ITEM_ID_PATTERN, max_length=128)],
    asked: Asked,
) -> CitedDocument:
    """One document's passages, at this caller's reach, for the page a citation links to."""
    registry = getattr(request.app.state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        # A process-level fault, identical for every caller and document.
        raise Failed("no tool registry on this process")
    if not registry.has(READ_DOCUMENT):
        # No document plane on this process, which is the same for every document and caller.
        raise _not_found(document_id)
    # A cast at the registry's boundary, for `brain.api_routes.passage_search_for`'s reason.
    handler = cast(
        Callable[..., Awaitable[TypedResult[KnowledgePassage]]],
        registry.get(READ_DOCUMENT).handler,
    )
    try:
        found = await handler(
            DocumentRead(document_id=document_id, limit=MAX_PASSAGES),
            entitlement=asked.reach,
            now=asked.now,
        )
        redacted = redact(found, entitlement=asked.reach, policy=PASSAGE_POLICY, now=asked.now)
    except BrainError:
        raise
    except Exception as exc:
        # Whatever a driver raises becomes a fault with no connection string in it.
        raise Failed(f"reading a cited document: {type(exc).__name__}") from exc
    document = passages_of(document_id, redacted.payload.records)
    if document is None:
        log.info("cited_document.not_answerable")
        raise _not_found(document_id)
    return document.model_copy(update={"truncated": redacted.payload.truncated})
