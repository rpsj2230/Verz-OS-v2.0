"""The text path's decisions: where an upload is placed, what it is called, and what it becomes.

`tests/unit/test_text_path.py` holds the scanner and the parser, and
`tests/unit/test_knowledge_routes.py` the HTTP half. What is here is `brain.knowledge.uploads`'
own share of M7.6.3 and M7.4.3: a placement that never widens, a name that is never the filename,
and the item a received file becomes.

Task ids: M7.4.3, M7.6.3, M7.6.1, M7.1.1
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.chunk_store import store_reach
from brain.knowledge.ingest import IngestRefused, MediaType, ParseCause, ParseFailure, admit_upload
from brain.knowledge.item import ITEM_ID_PATTERN, KnowledgeState
from brain.knowledge.kinds import KindError, KnowledgeKind
from brain.knowledge.scanning import ScanReport
from brain.knowledge.search import (
    KNOWLEDGE_READ,
    KNOWLEDGE_UPLOAD,
    TITLE_CHARS,
    Reach,
    reach_for,
)
from brain.knowledge.text_path import joined
from brain.knowledge.uploads import (
    UPLOAD_ID_PREFIX,
    ReadUpload,
    ReceivedUpload,
    UploadNotOffered,
    placement_for_upload,
    read_arriving,
    read_for_text_path,
    text_path_type,
    upload_item_id,
    upload_title,
)
from brain.knowledge.visibility import KnowledgeVisibility, Visibility, VisibilityError
from tests.fixtures.documents import LINE, a_pdf, a_word_document

OWNER = "u_uploader"
WEB = KnowledgeVisibility.of_department("web", owner_id=OWNER)
MAY_ADD_TO_WEB = Reach(principal_id=OWNER, departments=("web",))

MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALCHECK list before leaving."]).encode()


def place(
    level: Visibility,
    *,
    department: str = "",
    may_add: Reach | None = MAY_ADD_TO_WEB,
    reads_knowledge: bool = True,
) -> KnowledgeVisibility:
    return placement_for_upload(
        level,
        department=department,
        owner_id=OWNER,
        may_add=may_add,
        reads_knowledge=reads_knowledge,
    )


def received(
    content: bytes, media_type: MediaType, filename: str = "Site handover.md"
) -> ReceivedUpload:
    upload = admit_upload(filename=filename, declared_type=media_type.value, content=content)
    return ReceivedUpload(upload=upload, body=content)


class NeverScans:
    """A scanner a test proves was never reached."""

    def scan(self, content: bytes) -> ScanReport:
        raise AssertionError("the scanner was reached")


# ------------------------------------------------------------------ placement (M7.4.3)
def test_an_upload_is_placed_in_a_department_its_uploader_may_add_to() -> None:
    """The positive case. Delete this and every refusal below is satisfied by a placement that
    refuses everything, which is an install where nobody can add a document."""
    assert place(Visibility.DEPARTMENT, department="web") == WEB


def test_a_department_the_uploader_may_not_add_to_is_refused_as_not_offered() -> None:
    """Delete this and an uploader holding the capability over one department places documents
    in another, which is the upload widening the uploader's own reach."""
    with pytest.raises(UploadNotOffered):
        place(Visibility.DEPARTMENT, department="finance")


def test_nobody_may_add_without_the_capability_or_with_somebody_elses() -> None:
    """Delete this and an uploader with no upload grant, or a reach built for another person,
    places a document; the second is the handler with the wrong variable in scope."""
    with pytest.raises(UploadNotOffered):
        place(Visibility.DEPARTMENT, department="web", may_add=None)
    with pytest.raises(UploadNotOffered):
        place(
            Visibility.DEPARTMENT,
            department="web",
            may_add=Reach(principal_id="u_somebody_else", departments=("web",)),
        )


def test_an_upload_is_never_placed_company_wide_whatever_the_uploader_holds() -> None:
    """Uploading never widens scope. Delete this and a form field publishes a document to the
    whole company with no approver and no review date."""
    everywhere = Reach(principal_id=OWNER, departments=("web", "finance"))
    with pytest.raises(VisibilityError):
        place(Visibility.COMPANY, may_add=everywhere)


def test_a_personal_upload_needs_a_read_of_the_knowledge_layer() -> None:
    """Delete this and an administrator who reads no knowledge adds a personal document nobody,
    themselves included, could ever be answered from."""
    assert place(Visibility.PERSONAL) == KnowledgeVisibility.personal(OWNER)
    with pytest.raises(VisibilityError):
        place(Visibility.PERSONAL, reads_knowledge=False)


# ------------------------------------------------------------------ the name
def test_an_uploads_id_is_a_digest_of_what_it_is_and_where_it_went_and_never_its_name() -> None:
    """Delete this and the id can carry the filename into citations and the ledger, or the same
    file placed in two departments becomes one item moved between them."""
    first = received(MARKDOWN, MediaType.MARKDOWN, filename="Acme redundancy plan.md").upload
    again = received(MARKDOWN, MediaType.MARKDOWN, filename="another name.md").upload
    elsewhere = KnowledgeVisibility.of_department("sales", owner_id=OWNER)

    item_id = upload_item_id(first, WEB, OWNER)
    assert item_id == upload_item_id(again, WEB, OWNER)
    assert item_id != upload_item_id(first, elsewhere, OWNER)
    assert item_id != upload_item_id(first, WEB, "u_other")
    assert item_id.startswith(UPLOAD_ID_PREFIX)
    assert "Acme" not in item_id
    assert re.match(ITEM_ID_PATTERN, item_id)
    assert re.match(ITEM_ID_PATTERN, f"{item_id}.9999")


def test_an_uploads_title_is_its_filename_without_the_extension() -> None:
    """Delete this and the library and every citation read "Site handover.md"."""
    assert upload_title("Site handover.md") == "Site handover"
    assert upload_title("notes") == "notes"
    assert upload_title(".md") == ".md"
    assert len(upload_title("x" * 400 + ".pdf")) == TITLE_CHARS


# ------------------------------------------------------------------ the item (M7.6.3)
def test_a_markdown_upload_becomes_a_published_item_of_its_kind_at_its_place() -> None:
    """The positive path, end to end without a server. Delete this and each refusal below is
    satisfied by a path that makes no item."""
    read = read_for_text_path(
        received(MARKDOWN, MediaType.MARKDOWN),
        kind=KnowledgeKind.SOP,
        placement=WEB,
        owner_id=OWNER,
    )
    assert isinstance(read, ReadUpload)
    item = read.item
    assert (item.kind, item.state, item.visibility, item.owner_id) == (
        KnowledgeKind.SOP,
        KnowledgeState.PUBLISHED,
        WEB,
        OWNER,
    )
    assert item.title == "Site handover"
    assert item.content == joined(read.blocks)
    assert "TEALCHECK" in item.content


def test_a_word_upload_becomes_an_item_whose_table_is_a_table_block() -> None:
    """Delete this and a Word document's table is written as prose and cut across chunks."""
    document = a_word_document(paragraphs=["Notes."], table=[["Step", "Who"], ["Sign", "Lead"]])
    read = read_for_text_path(
        received(document, MediaType.DOCX, filename="handover.docx"),
        kind=KnowledgeKind.SOP,
        placement=WEB,
        owner_id=OWNER,
    )
    assert isinstance(read, ReadUpload)
    assert "| Sign | Lead |" in read.item.content


def test_an_approved_solution_is_refused_before_the_file_is_scanned() -> None:
    """Delete this and the file is scanned and parsed for a kind no upload may carry."""
    with pytest.raises(KindError):
        read_for_text_path(
            received(MARKDOWN, MediaType.MARKDOWN),
            kind=KnowledgeKind.APPROVED_SOLUTION,
            placement=WEB,
            owner_id=OWNER,
            scanner=NeverScans(),
        )


def test_a_pricing_note_holding_a_table_or_uploaded_as_a_pdf_is_refused() -> None:
    """M7.6.1's last clause, over real files. Delete this and a price table reaches the corpus
    as text inside a note."""
    with_table = a_word_document(paragraphs=["Q3."], table=[["Service", "Price"], ["Audit", "900"]])
    with pytest.raises(KindError):
        read_for_text_path(
            received(with_table, MediaType.DOCX, filename="prices.docx"),
            kind=KnowledgeKind.PRICING_NOTE,
            placement=WEB,
            owner_id=OWNER,
        )
    with pytest.raises(KindError):
        read_for_text_path(
            received(a_pdf("Prices move each quarter."), MediaType.PDF, filename="prices.pdf"),
            kind=KnowledgeKind.PRICING_NOTE,
            placement=WEB,
            owner_id=OWNER,
        )
    plain = read_for_text_path(
        received(b"Prices move each quarter; ask finance.", MediaType.PLAIN, filename="n.txt"),
        kind=KnowledgeKind.PRICING_NOTE,
        placement=WEB,
        owner_id=OWNER,
    )
    assert isinstance(plain, ReadUpload)


def test_a_type_outside_the_text_path_is_a_named_failure_and_is_never_scanned() -> None:
    """Delete this and a CSV reaches the scanner and the parser on this path."""
    outcome = read_for_text_path(
        received(b"a,b" + LINE.encode() + b"1,2", MediaType.CSV, filename="rows.csv"),
        kind=KnowledgeKind.SOP,
        placement=WEB,
        owner_id=OWNER,
        scanner=NeverScans(),
    )
    assert isinstance(outcome, ParseFailure)
    assert outcome.cause is ParseCause.UNSUPPORTED


def test_the_declared_type_is_refused_before_a_byte_when_this_path_cannot_read_it() -> None:
    """Delete this and a fifty megabyte image is read in full only to be refused."""
    assert text_path_type("text/markdown") is MediaType.MARKDOWN
    with pytest.raises(IngestRefused):
        text_path_type("image/png")
    with pytest.raises(IngestRefused):
        text_path_type("application/x-shell")


# ------------------------------------------------------------------ the body arriving
async def _arriving(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def test_a_body_is_refused_while_it_is_still_arriving_over_http() -> None:
    """The door's second check, over an asynchronous stream. Delete this and a request that
    declares nothing and sends gigabytes is held whole before anything refuses it."""
    assert asyncio.run(read_arriving(_arriving(b"ab", b"cd"), ceiling=4)) == b"abcd"
    with pytest.raises(IngestRefused):
        asyncio.run(read_arriving(_arriving(b"ab", b"cd", b"e"), ceiling=4))


# ------------------------------------------------------------------ the store's reach
NOW = datetime(2999, 1, 1, tzinfo=UTC)
REGISTRY = ("finance", "sales", "web")


def holding(*grants: tuple[str, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id=OWNER,
        grants=tuple(Grant(capability=Capability(value=one), scope=scope) for one, scope in grants),
    )


def test_an_administrator_who_reads_nothing_writes_where_they_may_add() -> None:
    """The store's half of an administrator adding a document to a department they do not read.
    Delete this and the store judges the owner by their read alone, so the document is refused at
    the door, or written and never readable back by the embedding job that runs as its owner."""
    reach = store_reach(
        holding((KNOWLEDGE_UPLOAD.value, Scope.department("web"))), departments=REGISTRY, now=NOW
    )
    assert reach == Reach(principal_id=OWNER, departments=("web",))


def test_the_store_reach_is_the_read_and_the_add_together_and_nothing_for_neither() -> None:
    """Delete this and the union can drop one half, or a person holding neither is handed a reach
    of no departments, which still writes a personal row nobody asked for."""
    both = holding(
        (KNOWLEDGE_READ.value, Scope.department("sales")),
        (KNOWLEDGE_UPLOAD.value, Scope.department("web")),
    )
    assert store_reach(both, departments=REGISTRY, now=NOW) == Reach(
        principal_id=OWNER, departments=("sales", "web")
    )
    assert store_reach(holding(), departments=REGISTRY, now=NOW) is None


def test_the_search_a_person_asks_through_still_reads_with_the_read_alone() -> None:
    """The other half of the store's union, and the reason it is the store's alone. Delete this
    and an administrator's add grant can become a read of every department they may add to."""
    adder = holding((KNOWLEDGE_UPLOAD.value, Scope.unrestricted()))
    assert reach_for(adder, departments=REGISTRY, now=NOW) is None
