"""The knowledge inventory, taken from the Knowledge screen, against a real database.

Every test builds a database migrated to head and presses the route over HTTP as the application
role, signed in with grants the grant table holds, as `tests/unit/test_knowledge_documents_db.py`
does for the list. What each proves is where the owner would see it: the file holds the documents
the list would show that reader and no others, states each one's level and department, carries
nothing a document says and nothing the badge withholds, and is recorded on the Exports log with
its ledger entry before it is handed over.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector.

Task ids: M25.3.3
"""

from __future__ import annotations

import csv
import hashlib
import io
from typing import Any

import httpx
import pytest

from brain import knowledge_export_routes as routes
from brain.knowledge_export_routes import (
    COLUMNS,
    KNOWLEDGE_EXPORT_PATH,
    NOT_ANSWERABLE,
    inventory,
)
from brain.knowledge_lifecycle_routes import DocumentView
from tests.fixtures.console_http import headers
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_knowledge_documents_db import (
    ADMIN_NAME,
    FINANCE_POLICY,
    WEB_UPLOADER,
    company,
    pressed,
)
from tests.unit.test_knowledge_lifecycle_db import (
    FINANCE_READER,
    V1,
    WEB_ADMIN,
    WEB_READER,
    api,
    upload,
    verify,
)

pytestmark = pytest.mark.needs_db

BODY = {"reason": "regulatory_request", "reason_reference": "AUDIT-2026-Q3"}

#: Somebody signed in who holds no knowledge grant at all.
NOBODY = "u_none"


def rows_in(response: httpx.Response) -> list[dict[str, str]]:
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.json()["document"])))


async def taken(
    client: httpx.AsyncClient, who: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    return await client.post(api(KNOWLEDGE_EXPORT_PATH), json=body or BODY, headers=headers(who))


def test_the_inventory_holds_the_documents_the_list_shows_that_reader_and_states_their_scope() -> (
    None
):
    """**The inventory on a server.** Web's administrator adds and verifies a web document. A web
    reader's file holds it and finance's company-wide policy, each with its level and department
    and who that reaches in words, and holds no word of the document's text. A finance reader's file
    holds the policy and not the web document, with no line about what it left out.

    Delete this and the inventory can name a document the list withholds, drop a level on the way
    out, or carry the text that the passage policy would have redacted."""
    with company("brain_ke_scope") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            await verify(client, WEB_ADMIN, first["item_id"])
            return {
                "item": first["item_id"],
                "web": await taken(client, WEB_READER),
                "finance": await taken(client, FINANCE_READER),
            }

        said = pressed(url, presses)

    web = {one["Document id"]: one for one in rows_in(said["web"])}
    assert set(web) == {said["item"], FINANCE_POLICY}
    assert web[said["item"]]["Level"] == "department"
    assert web[said["item"]]["Department"] == "web"
    assert web[said["item"]]["Who may read it"] == "people in web"
    assert web[FINANCE_POLICY]["Level"] == "company"
    assert web[FINANCE_POLICY]["Who may read it"] == "everyone in the company"
    assert web[said["item"]]["Steward"] == ADMIN_NAME
    assert "TEALOLD" not in said["web"].json()["document"]
    finance = rows_in(said["finance"])
    assert [one["Document id"] for one in finance] == [FINANCE_POLICY]
    assert list(finance[0]) == list(COLUMNS)
    assert said["item"] not in said["finance"].text


def test_a_document_the_load_admitted_and_the_reader_may_not_see_is_not_in_the_file() -> None:
    """An uploader who may add in web and read nothing is loaded finance's company-wide policy by
    the database's policy, and `may_see` refuses it. Delete this and the file is the one place a
    document the list withholds can be learned of, because the load admitted it."""
    with company("brain_ke_may_see") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            return {
                "item": first["item_id"],
                "uploader": await taken(client, WEB_UPLOADER),
                "reader": await taken(client, WEB_READER),
            }

        said = pressed(url, presses)

    assert {one["Document id"] for one in rows_in(said["uploader"])} == {said["item"]}
    assert FINANCE_POLICY in {one["Document id"] for one in rows_in(said["reader"])}


def test_a_verifier_the_badge_withholds_is_not_named_in_the_file() -> None:
    """The administrator who verified a document is named to the administrator and not to a reader
    the badge does not name them to. Delete this and the file is a second way to learn who vouched
    for a document, which the badge withholds behind its own capability."""
    with company("brain_ke_verifier") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            await verify(client, WEB_ADMIN, first["item_id"])
            return {
                "item": first["item_id"],
                "admin": await taken(client, WEB_ADMIN),
                "reader": await taken(client, WEB_READER),
            }

        said = pressed(url, presses)

    seen_by_reader = {one["Document id"]: one for one in rows_in(said["reader"])}[said["item"]]
    seen_by_admin = {one["Document id"]: one for one in rows_in(said["admin"])}[said["item"]]
    assert seen_by_reader["Verified by"] == ""
    assert seen_by_admin["Verified by"] == ADMIN_NAME


def test_the_inventory_is_recorded_with_its_ledger_entry_and_matches_the_file_handed_over() -> None:
    """One row on the Exports log under the exporter, a readable export with the count and the
    digest of the exact bytes, and the `publish` entry `0053`'s trigger writes. Delete this and an
    inventory can leave the building with no record that it did, or a record of some other file."""
    with company("brain_ke_recorded") as url:

        async def presses(client: httpx.AsyncClient) -> Any:
            await upload(client, WEB_ADMIN, V1)
            return await taken(client, WEB_READER)

        answer = pressed(url, presses)
        body = answer.json()
        recorded = sql(
            url,
            "SELECT data_set, requested_by, reason, reason_reference, form, entries, "
            "document_digest, first_seq, verified FROM ops.data_export",
        )
        entries = sql(
            url,
            "SELECT action, subject FROM obs.audit_entry WHERE subject = %s",
            f"artifact:{body['export']['export_id']}",
        )

    assert len(recorded) == 1
    data_set, who, reason, reference, form, count, digest, first, verified = recorded[0]
    assert (data_set, who, reason, reference) == (
        "knowledge",
        WEB_READER,
        "regulatory_request",
        "AUDIT-2026-Q3",
    )
    assert (form, first, verified) == ("readable", None, None)
    assert count == len(rows_in(answer))
    assert digest == hashlib.sha256(body["document"].encode("utf-8")).hexdigest()
    assert body["filename"] == f"knowledge-{body['export']['export_id']}.csv"
    assert [one[0] for one in entries] == ["publish"]


def test_a_reader_with_no_knowledge_authority_is_refused_in_the_words_of_an_unknown_route() -> None:
    """Refused before anything is read or recorded, and the sentence names no document. Delete this
    and somebody who may read nothing can take a file and a record for it."""
    with company("brain_ke_refused") as url:

        async def presses(client: httpx.AsyncClient) -> httpx.Response:
            return await taken(client, NOBODY)

        answer = pressed(url, presses)
        recorded = sql(url, "SELECT count(*) FROM ops.data_export")

    assert answer.status_code == 404
    assert answer.json()["message"] == "I could not find that."
    assert NOT_ANSWERABLE not in answer.text
    assert recorded[0][0] == 0


def test_a_reference_with_a_space_or_an_unknown_reason_is_refused_by_its_shape() -> None:
    """The reason is a closed word and the reference a token. Delete this and a person's name can
    be written into the record of an export as its reference."""
    with company("brain_ke_shape") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, httpx.Response]:
            return {
                "spaced": await taken(client, WEB_READER, {**BODY, "reason_reference": "Jane Doe"}),
                "unknown": await taken(client, WEB_READER, {**BODY, "reason": "curiosity"}),
            }

        said = pressed(url, presses)
        recorded = sql(url, "SELECT count(*) FROM ops.data_export")

    assert said["spaced"].status_code == said["unknown"].status_code == 422
    assert recorded[0][0] == 0


# ------------------------------------------------------------------ the file, row by row
def a_row(**given: Any) -> DocumentView:
    """One document as the Knowledge list sends it, with only what the test is about changed."""
    fields: dict[str, Any] = {
        "item_id": "upload.one",
        "title": "Site handover",
        "kind": "sop",
        "kind_label": "SOP",
        "level": "department",
        "department": "web",
        "steward_id": "u_steward",
        "state": "published",
        "verification": "verified",
        "steward_name": "Aisha Web",
    }
    return DocumentView(**{**fields, **given})


def test_each_level_is_stated_in_words_and_a_personal_document_never_carries_its_stewards_id() -> (
    None
):
    """The three levels each reach somebody different, and the file says which in words. Delete this
    and a level can be written as the wrong audience, or a personal document can carry the id of the
    person it belongs to."""
    rows = [
        a_row(item_id="a", level="company", department=None),
        a_row(item_id="b", level="department", department="finance"),
        a_row(item_id="c", level="personal", department=None),
    ]

    said = {one["Document id"]: one for one in csv.DictReader(io.StringIO(inventory(rows)))}

    assert said["a"]["Who may read it"] == "everyone in the company"
    assert said["b"]["Who may read it"] == "people in finance"
    assert said["c"]["Who may read it"] == "its steward only"
    assert "u_steward" not in inventory(rows)


def test_a_title_a_spreadsheet_would_run_is_written_as_text() -> None:
    """Delete this and a document titled =HYPERLINK(1) runs as a formula in the auditor's copy."""
    document = inventory([a_row(title="=HYPERLINK(1)", steward_name="@someone")])

    assert "'=HYPERLINK(1)" in document
    assert "'@someone" in document


def test_a_scope_that_would_not_survive_the_export_stops_it_before_anything_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The comparison runs on the rows about to be written. Delete this and the route can drop the
    scope check, which the function's own tests would never notice."""
    from brain.ops.export import ExportError

    with company("brain_ke_scope_check") as url:

        async def presses(client: httpx.AsyncClient) -> httpx.Response:
            await upload(client, WEB_ADMIN, V1)
            return await taken(client, WEB_READER)

        def refuse(items: object) -> None:
            raise ExportError("flattened")

        monkeypatch.setattr(routes, "knowledge_inventory", refuse)
        answer = pressed(url, presses)
        recorded = sql(url, "SELECT count(*) FROM ops.data_export")

    assert answer.status_code == 500
    assert "document" not in answer.text
    assert recorded[0][0] == 0


def test_a_record_that_fails_hands_over_no_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """`THE_ROW_AND_THE_DOCUMENT_COMMIT_TOGETHER`, for the inventory. Delete this and an inventory
    can leave the building while its record failed."""

    class Failing:
        async def record_report(self, **given: object) -> object:
            raise RuntimeError("the insert failed")

    with company("brain_ke_record_fails") as url:

        async def presses(client: httpx.AsyncClient) -> httpx.Response:
            await upload(client, WEB_ADMIN, V1)
            return await taken(client, WEB_READER)

        monkeypatch.setattr(routes, "report_records_of", lambda request: Failing())
        answer = pressed(url, presses)

    assert answer.status_code == 500
    assert "document" not in answer.text


def test_a_list_that_loaded_its_most_documents_says_the_inventory_may_not_hold_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fact about the load and never a count. Delete this and a reader is handed a partial
    inventory believing it complete."""
    with company("brain_ke_full") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, httpx.Response]:
            await upload(client, WEB_ADMIN, V1)
            full = await taken(client, WEB_READER)
            return {"full": full}

        monkeypatch.setattr(routes, "MAX_ITEMS", 1)
        said = pressed(url, presses)

    assert routes.THE_LIST_LOADED_ITS_MOST_DOCUMENTS in said["full"].json()["told"]
