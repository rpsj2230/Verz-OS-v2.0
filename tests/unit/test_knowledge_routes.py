"""Adding a document from the console over HTTP: what is offered, what is added, what is refused.

Driven through the real application with signed-in people holding chosen grants. The department
registry is answered by the stub session; the store step, `brain.knowledge_routes.store_upload`,
is replaced by one that keeps what it was handed, because what it does against a database is
`tests/unit/test_knowledge_upload_db.py`'s. Everything before it, the door, the scan, the parse,
the kind and the placement, runs for real over files built in memory.

Task ids: M7.1.1, M7.6.3, M7.2.5, M7.4.3, M7.6.1
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain import knowledge_routes
from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.knowledge.chunk_store import ChunkStoreError
from brain.knowledge.ingest import CAUSE_TEXT, ParseCause
from brain.knowledge.kinds import KIND_LABELS, uploadable_kinds
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge.text_path import STRUCTURAL_CHECK
from brain.knowledge.uploads import ReadUpload
from brain.knowledge_routes import (
    FOUND_BY_TEXT,
    NAME_HEADER,
    UPLOAD_OPTIONS_PATH,
    UPLOADS_PATH,
)
from brain.ops.queue import Job
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.documents import LINE, a_locked_pdf, a_pdf, a_word_document
from tests.fixtures.setting_rows import Result

OPTIONS = f"{API_PREFIX}{UPLOAD_OPTIONS_PATH}"
UPLOADS = f"{API_PREFIX}{UPLOADS_PATH}"
EVERYWHERE = Scope.unrestricted()
REGISTRY = ["finance", "web"]


def _grant(capability: Capability, scope: Scope = EVERYWHERE) -> Grant:
    return Grant(capability=capability, scope=scope)


#: `u_admin` adds anywhere and reads nothing, as a first administrator does. `u_narrow` adds in
#: web and reads it. `u_wide` reads everything and adds nowhere. The names are the signed-in
#: people `tests.unit.test_api_routes` mints tokens for.
GRANTS = {
    "u_admin": (_grant(KNOWLEDGE_UPLOAD),),
    "u_narrow": (
        _grant(KNOWLEDGE_UPLOAD, Scope.department("web")),
        _grant(KNOWLEDGE_READ, Scope.department("web")),
    ),
    "u_wide": (_grant(KNOWLEDGE_READ),),
}

MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALCHECK list before leaving."]).encode()


class Kept:
    """The store step, keeping what it was handed and answering as an install with no vectors."""

    def __init__(self) -> None:
        self.stored: list[ReadUpload] = []
        self.fail: Exception | None = None

    async def __call__(
        self, request: Any, read: ReadUpload, *, now: Any
    ) -> tuple[Job | None, bool]:
        if self.fail is not None:
            raise self.fail
        self.stored.append(read)
        return None, False


def registry(statement: Any) -> Result | None:
    """The live department registry, for the one select that reads it."""
    if isinstance(statement, Select):
        names = {getattr(one, "name", "") for one in statement.get_final_froms()}
        if "department" in names:
            return Result(REGISTRY)
    return None


@pytest.fixture
def kept(monkeypatch: pytest.MonkeyPatch) -> Kept:
    store = Kept()
    monkeypatch.setattr(knowledge_routes, "store_upload", store)
    return store


@pytest.fixture
def served(kept: Kept) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(registry)
        yield client, stub


def upload(
    client: TestClient,
    pid: str,
    body: bytes,
    *,
    name: str = "Site handover.md",
    media_type: str = "text/markdown",
    kind: str = "sop",
    level: str = "department",
    department: str = "web",
    strong: bool = True,
) -> Any:
    sent = {**headers(pid, strong=strong), "content-type": media_type}
    if name:
        sent[NAME_HEADER] = quote(name)
    return client.post(
        UPLOADS,
        content=body,
        headers=sent,
        params={"kind": kind, "level": level, "department": department},
    )


def problem(response: Any) -> str:
    """The reason a 422 gives, which is its message and its one problem's, the same words."""
    assert response.status_code == 422, response.text
    body = response.json()
    (one,) = body["problems"]
    assert body["message"] == one["message"]
    assert body["trace_id"]
    return str(one["message"])


# ------------------------------------------------------------------ what is offered
def test_an_administrator_is_offered_every_uploadable_kind_and_every_department(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for the options. Delete this and each refusal below is satisfied by a
    route that offers nothing, which is the Knowledge page with no upload for anybody."""
    client, _ = served
    response = get(client, "u_admin", OPTIONS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kinds"] == [
        {"value": one.value, "label": KIND_LABELS[one]} for one in uploadable_kinds()
    ]
    assert body["departments"] == REGISTRY
    assert body["personal"] is False
    assert {one["media_type"] for one in body["types"]} == {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    assert body["found_by"] == FOUND_BY_TEXT
    assert body["checked_by"] == STRUCTURAL_CHECK


def test_a_department_administrator_is_offered_their_own_department_and_their_own_level(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the options list the whole registry to somebody who may add to one
    department, which is the org chart handed to whoever can open the page."""
    client, _ = served
    body = get(client, "u_narrow", OPTIONS).json()
    assert (body["departments"], body["personal"]) == (["web"], True)


def test_somebody_who_may_add_nothing_is_answered_as_absent(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a reader is offered an upload the route will refuse, or is told why not.
    A session with no second factor is the same answer, because administration needs one."""
    client, _ = served
    assert get(client, "u_wide", OPTIONS).status_code == 404
    assert get(client, "u_admin", OPTIONS, strong=False).status_code == 404


# ------------------------------------------------------------------ what is added
def test_a_markdown_file_is_added_to_a_department_as_its_uploader(
    served: tuple[TestClient, Stub], kept: Kept
) -> None:
    """M7.6.3's route. Delete this and every refusal below is satisfied by a route that adds
    nothing, which is the page this module was written to replace."""
    client, _ = served
    response = upload(client, "u_admin", MARKDOWN)

    assert response.status_code == 201, response.text
    body = response.json()
    (read,) = kept.stored
    assert body == {
        "item_id": read.item.item_id,
        "title": "Site handover",
        "kind": "sop",
        "level": "department",
        "department": "web",
        "passages": len(read.blocks),
        "found_by": FOUND_BY_TEXT,
    }
    assert read.item.owner_id == "u_admin"
    assert "TEALCHECK" in read.item.content


def test_a_word_document_and_a_pdf_are_added(served: tuple[TestClient, Stub], kept: Kept) -> None:
    """The other two formats the owner names. Delete this and only text reaches the corpus."""
    client, _ = served
    word = upload(
        client,
        "u_admin",
        a_word_document(paragraphs=["Sign the TEALCHECK list."]),
        name="handover.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="policy",
    )
    pdf = upload(
        client,
        "u_admin",
        a_pdf("Sign the TEALCHECK list."),
        name="handover.pdf",
        media_type="application/pdf",
        kind="faq",
    )
    assert (word.status_code, pdf.status_code) == (201, 201), (word.text, pdf.text)
    assert [one.item.kind.value for one in kept.stored if one.item.kind] == ["policy", "faq"]


# ------------------------------------------------------------------ what is refused
def test_a_department_nobody_may_add_to_and_one_that_does_not_exist_are_one_answer(
    served: tuple[TestClient, Stub], kept: Kept
) -> None:
    """DENIED and ABSENT are one answer. Delete this and the refusal says which departments
    exist, a probe anybody holding the capability anywhere could sit and run."""
    client, _ = served
    denied = upload(client, "u_narrow", MARKDOWN, department="finance")
    absent = upload(client, "u_narrow", MARKDOWN, department="nowhere")

    assert denied.status_code == absent.status_code == 404
    assert denied.json()["message"] == absent.json()["message"]
    assert kept.stored == []


def test_company_wide_is_refused_with_the_reason(
    served: tuple[TestClient, Stub], kept: Kept
) -> None:
    """Uploading never widens scope (M7.4.3). Delete this and a query parameter publishes a
    document to the whole company."""
    client, _ = served
    assert "promotion" in problem(upload(client, "u_admin", MARKDOWN, level="company"))
    assert kept.stored == []


def test_a_locked_pdf_is_refused_naming_the_cause_and_the_remedy(
    served: tuple[TestClient, Stub], kept: Kept
) -> None:
    """M7.2.5 on the page. Delete this and the uploader is told only that something failed, and
    sends the identical file again."""
    client, _ = served
    response = upload(
        client,
        "u_admin",
        a_locked_pdf("Sign the list."),
        name="locked.pdf",
        media_type="application/pdf",
    )
    assert CAUSE_TEXT[ParseCause.ENCRYPTED] in problem(response)
    assert response.json()["problems"][0]["code"] == ParseCause.ENCRYPTED.value
    assert kept.stored == []


def test_a_pricing_note_holding_a_table_is_refused(
    served: tuple[TestClient, Stub], kept: Kept
) -> None:
    """Delete this and a price table reaches the corpus as text inside a note (M7.6.1)."""
    client, _ = served
    table = LINE.join(["| Service | Price |", "| Audit | 900 |"]).encode()
    assert "price list" in problem(upload(client, "u_admin", table, kind="pricing_note"))
    assert kept.stored == []


def test_an_approved_solution_is_refused(served: tuple[TestClient, Stub], kept: Kept) -> None:
    """Delete this and an upload carries the approved-solution label with no approval behind it."""
    client, _ = served
    assert "approv" in problem(upload(client, "u_admin", MARKDOWN, kind="approved_solution"))


def test_an_image_is_refused_before_it_is_read(served: tuple[TestClient, Stub], kept: Kept) -> None:
    """Delete this and a type this path cannot read is read whole to be refused."""
    client, _ = served
    response = upload(client, "u_admin", b"x" * 64, name="scan.png", media_type="image/png")
    assert "not read from the console" in problem(response)


def test_an_upload_with_no_name_is_refused(served: tuple[TestClient, Stub], kept: Kept) -> None:
    """Delete this and a nameless file is added that no refusal or library row can name."""
    client, _ = served
    assert "filename" in problem(upload(client, "u_admin", MARKDOWN, name=""))


def test_a_document_the_store_refuses_is_reported_and_not_added(
    served: tuple[TestClient, Stub], kept: Kept
) -> None:
    """Delete this and a store refusal reaches the uploader as a fault with no words."""
    client, _ = served
    kept.fail = ChunkStoreError("the store refused it")
    assert problem(upload(client, "u_admin", MARKDOWN)) == "the store refused it"
