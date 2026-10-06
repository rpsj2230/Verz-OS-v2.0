"""A stored document's lifecycle against a real PostgreSQL, through the application's own routes.

Every test here builds a database migrated to head, so `0120`'s tables, policies, triggers and
functions are the ones that ship, and presses the routes over HTTP as the application role, signed
in with chosen grants that the grant table holds as well. What each proves is the owner's sentence
for one package, seen where he would see it: a newer version supersedes the older, which stays
readable in history while answers use the newer; a promotion waits on the Approvals screen and is
applied when a Super Admin approves it; a review that fell due opens a task for its steward; a
solution becomes knowledge only when a named person approves it; a steward is handed over and told.
Every change is in the ledger, and a document a reader may not see is answered as absent.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is, and without pgvector, which the
chain to head needs; CI has both.

Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app, suspension_store_for
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.scope import Scope
from brain.knowledge.document_tools import DocumentSearch, KnowledgePassage, searcher
from brain.knowledge.item_store import run_reverification_now
from brain.knowledge.lifecycle import STEWARD_REFUSED
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge.visibility import PROMOTION_CAPABILITY
from brain.knowledge_lifecycle_routes import router as lifecycle_router
from brain.knowledge_routes import NAME_HEADER
from brain.ops.worker import _loop_factory
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.documents import LINE
from tests.fixtures.knowledge_items import a_person
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import admin_url, modelled, run, secured, shape, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_embedding_path_db import through

pytestmark = pytest.mark.needs_db

COMPANY = "c_knowledge_lifecycle"
#: The people `tests.unit.test_api_routes` mints tokens for, in the parts this file gives them.
WEB_ADMIN = "u_admin"
WEB_READER = "u_narrow"
FINANCE_READER = "u_elsewhere"
SUPER = "u_wide"
TABLES: tuple[str, ...] = ("know.steward_task", "know.solution")

#: The field grants a passage is read under, as a pack assignment grants them.
PASSAGE_FIELDS: tuple[str, ...] = (
    "read:knowledge.document",
    "read:knowledge.title",
    "read:knowledge.section",
    "read:knowledge.updated_at",
)


def _in(department: str, *capabilities: str) -> tuple[Grant, ...]:
    return tuple(
        Grant(capability=Capability(value=one), scope=Scope.department(department))
        for one in capabilities
    )


#: What each person holds, in the grant table and in the sign-in's admitted reach alike.
GRANTS: dict[str, tuple[Grant, ...]] = {
    WEB_ADMIN: _in("web", KNOWLEDGE_UPLOAD.value, KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    WEB_READER: _in("web", KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    FINANCE_READER: _in("finance", KNOWLEDGE_READ.value, *PASSAGE_FIELDS),
    SUPER: (Grant(capability=PROMOTION_CAPABILITY, scope=Scope.unrestricted()),),
}

V1 = LINE.join(["# Site handover", "", "Sign the TEALOLD list before leaving."]).encode()
V2 = LINE.join(["# Site handover", "", "Sign the TEALNEW list and lock the door."]).encode()
LATER = datetime.now(tz=UTC) + timedelta(days=180)


@contextmanager
def company(name: str) -> Iterator[str]:
    """A database at head holding four people, their grants and two departments."""
    if not has_pgvector(admin_url()):
        pytest.skip("the chain to head needs pgvector, which CI's server has")
    with retirable(name) as url:
        for department in ("web", "finance"):
            sql(
                url,
                "INSERT INTO gate.department (company_id, slug, name, scope_slug) "
                "VALUES (%s, %s, %s, %s)",
                COMPANY,
                department,
                department.title(),
                department,
            )
        for person, grants in GRANTS.items():
            a_person(url, person)
            for grant in grants:
                sql(
                    url,
                    "INSERT INTO gate.capability_grant "
                    "(principal_id, capability, scope, granted_by, reason) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    person,
                    grant.capability.value,
                    json.dumps(grant.scope.model_dump(mode="json")),
                    "u_seed",
                    "loaded by the test fixture",
                )
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes, with the lifecycle's included, as the application role."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(lifecycle_router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.suspensions = suspension_store_for(app.state.db_sessions)
            app.state.console_reads = None
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def api(path: str) -> str:
    return f"{API_PREFIX}{path}"


def file_headers(who: str) -> dict[str, str]:
    return {
        **headers(who),
        "content-type": "text/markdown",
        NAME_HEADER: quote("Site handover.md"),
    }


async def upload(client: httpx.AsyncClient, who: str, body: bytes) -> dict[str, Any]:
    added = await client.post(
        api("/knowledge/uploads"),
        params={"kind": "sop", "level": "department", "department": "web"},
        content=body,
        headers=file_headers(who),
    )
    assert added.status_code == 201, added.text
    return dict(added.json())


async def verify(client: httpx.AsyncClient, who: str, item_id: str) -> httpx.Response:
    return await client.post(
        api(f"/knowledge/items/{item_id}/verification"),
        json={"review_by": LATER.isoformat()},
        headers=headers(who),
    )


def searched(url: str, who: str, word: str) -> TypedResult[KnowledgePassage]:
    reader = EntitlementSet(principal_id=who, grants=GRANTS[who])

    async def work(sessions: async_sessionmaker[AsyncSession]) -> TypedResult[KnowledgePassage]:
        return await searcher(SessionRowSource(sessions))(
            DocumentSearch(question=word), entitlement=reader
        )

    return through(url, work)


def ledger(url: str, subject_prefix: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (row[0], row[1])
        for row in sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry WHERE subject LIKE %s ORDER BY seq",
            f"{subject_prefix}%",
        )
    ]


def without_trace(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "trace_id"}


# ------------------------------------------------------------------ a new version (M7.4.5)
def test_a_newer_version_supersedes_the_older_which_stays_readable_and_answers_use_the_newer() -> (
    None
):
    """**M7.4.5 on a server, through the routes.** Web's administrator adds a document, verifies it
    and adds a newer version. The older is `superseded` with its passages, the newer names it, a
    text search finds the newer's words and not the older's, the history lists both to a web
    reader, and the older's text is still read from it. A finance reader is told the document is
    absent in the words an invented id gets, and so is a web reader asking to verify it. Every
    write is in the ledger naming the administrator and the columns that changed.

    Delete this and supersession can be written in Python and refused by the policy it runs
    under, which 0046 recorded for chunks and nothing had fixed, with every stand-in green."""
    with company("brain_k2_supersede") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            verified = await verify(client, WEB_ADMIN, first["item_id"])
            second = await client.post(
                api(f"/knowledge/items/{first['item_id']}/versions"),
                params={"review_by": LATER.isoformat()},
                content=V2,
                headers=file_headers(WEB_ADMIN),
            )
            newer = second.json()["item_id"]
            return {
                "first": first,
                "verified": verified,
                "second": second,
                "again": await client.post(
                    api(f"/knowledge/items/{first['item_id']}/versions"),
                    params={"review_by": LATER.isoformat()},
                    content=V2,
                    headers=file_headers(WEB_ADMIN),
                ),
                "history": await client.get(
                    api(f"/knowledge/items/{newer}"), headers=headers(WEB_READER)
                ),
                "older_text": await client.get(
                    api(f"/knowledge/items/{first['item_id']}/passages"),
                    headers=headers(WEB_READER),
                ),
                "finance": await client.get(
                    api(f"/knowledge/items/{newer}"), headers=headers(FINANCE_READER)
                ),
                "invented": await client.get(
                    api("/knowledge/items/upload.nothing_here"), headers=headers(FINANCE_READER)
                ),
                "reader_verifies": await verify(client, WEB_READER, newer),
                "invented_verify": await verify(client, WEB_READER, "upload.nothing_here"),
            }

        said = pressed(url, presses)
        older, newer = said["first"]["item_id"], said["second"].json()["item_id"]
        states = dict(sql(url, "SELECT item_id, state FROM know.item"))
        supersedes = sql(url, "SELECT supersedes FROM know.item WHERE item_id = %s", newer)
        chunk_states = set(
            sql(url, "SELECT DISTINCT state FROM know.chunk WHERE document_id = %s", older)
        )
        old_words = searched(url, WEB_READER, "TEALOLD")
        new_words = searched(url, WEB_READER, "TEALNEW")
        entries = ledger(url, "setting:knowledge_item.")

    assert said["verified"].status_code == 200
    assert said["second"].status_code == 201, said["second"].text
    assert said["second"].json()["supersedes"] == older
    assert states == {older: "superseded", newer: "published"}
    assert supersedes == [(older,)]
    assert chunk_states == {("superseded",)}
    assert old_words.records == ()
    assert new_words.records and all(one.document_id == newer for one in new_words.records)
    assert said["again"].status_code == 404
    history = said["history"].json()
    assert [(one["item_id"], one["state"]) for one in history["versions"]] == [
        (older, "superseded"),
        (newer, "published"),
    ]
    assert all(one["readable"] for one in history["versions"])
    assert said["older_text"].status_code == 200
    assert any("TEALOLD" in one["text"] for one in said["older_text"].json()["passages"])
    for refused, invented in (("finance", "invented"), ("reader_verifies", "invented_verify")):
        assert said[refused].status_code == said[invented].status_code == 404
        assert without_trace(said[refused].json()) == without_trace(said[invented].json())
    changed = [details.get("changed", "") for actor, details in entries if actor == WEB_ADMIN]
    assert "review_by,verified_at,verified_by" in changed
    assert "state" in changed and "supersedes" in changed


# ------------------------------------------------------------------ promotion (M7.4.4)
def test_a_promotion_waits_on_the_approvals_screen_and_is_applied_when_a_super_admin_approves() -> (
    None
):
    """**M7.4.4 on a server.** The steward asks for their verified document to be company-wide.
    The card is on the Super Admin's Approvals screen and on nobody else's; approving it through
    that screen's own route makes the document and its passages company-wide in the same
    transaction, a finance reader's search then finds it, the steward is told, and the ledger holds
    the approval and the widening, both naming the Super Admin.

    Delete this and a promotion can be raised to a queue nobody reads, or approved with nothing
    widening, and the Approvals screen would still look right."""
    with company("brain_k2_promotion") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V2)
            item = first["item_id"]
            unverified = await client.post(
                api(f"/knowledge/items/{item}/promotion"),
                json={"review_by": LATER.isoformat(), "reason": "every team quotes it"},
                headers=headers(WEB_ADMIN),
            )
            await verify(client, WEB_ADMIN, item)
            asked = await client.post(
                api(f"/knowledge/items/{item}/promotion"),
                json={"review_by": LATER.isoformat(), "reason": "every team quotes it"},
                headers=headers(WEB_ADMIN),
            )
            twice = await client.post(
                api(f"/knowledge/items/{item}/promotion"),
                json={"review_by": LATER.isoformat(), "reason": "every team quotes it"},
                headers=headers(WEB_ADMIN),
            )
            card = asked.json()["suspension_id"]
            reader_queue = await client.get(api("/approvals"), headers=headers(WEB_READER))
            queue = await client.get(api("/approvals"), headers=headers(SUPER))
            decided = await client.post(
                api(f"/approvals/{card}/decision"),
                json={"verdict": "approved"},
                headers=headers(SUPER),
            )
            return {
                "item": item,
                "unverified": unverified,
                "asked": asked,
                "twice": twice,
                "reader_queue": reader_queue,
                "queue": queue,
                "decided": decided,
                "tasks": await client.get(api("/knowledge/tasks"), headers=headers(WEB_ADMIN)),
                "looked_after": await client.get(
                    api("/knowledge/items"), headers=headers(WEB_ADMIN)
                ),
            }

        said = pressed(url, presses)
        item = said["item"]
        placed = sql(url, "SELECT visibility, department FROM know.item WHERE item_id = %s", item)
        chunks = set(
            sql(url, "SELECT DISTINCT visibility FROM know.chunk WHERE document_id = %s", item)
        )
        found = searched(url, FINANCE_READER, "TEALNEW")
        approvals = ledger(url, "leash:")
        widened = [
            (actor, details)
            for actor, details in ledger(url, "setting:knowledge_item.")
            if details.get("level") == "company"
        ]

    assert said["unverified"].status_code == 422
    assert said["asked"].status_code == 201, said["asked"].text
    assert said["twice"].status_code == 409
    assert said["reader_queue"].json()["items"] == []
    cards = said["queue"].json()["items"]
    assert [one["suspension_id"] for one in cards] == [said["asked"].json()["suspension_id"]]
    assert "Document: Site handover" in cards[0]["request"]
    assert "TEALNEW" not in cards[0]["request"]
    assert said["decided"].status_code == 200, said["decided"].text
    assert placed == [("company", "web")]
    assert chunks == {("company",)}
    assert found.records and found.records[0].document_id == item
    assert [(actor, details["verdict"]) for actor, details in approvals] == [(SUPER, "approved")]
    assert [actor for actor, _ in widened] == [SUPER]
    assert "visibility" in widened[0][1]["changed"]
    says = [one["says"] for one in said["tasks"].json()["items"]]
    assert any("approved for the whole company" in one for one in says)
    promoted = [one for one in said["looked_after"].json()["items"] if one["item_id"] == item]
    assert promoted[0]["promotion"]["status"] == "approved"


def test_a_promotion_approved_by_its_own_asker_or_after_the_document_moved_is_not_applied() -> None:
    """The trigger's two refusals, pressed at the row as a decision would write it. Delete this and
    a Super Admin who asked can approve their own card, or an approval collected before the document
    was narrowed widens it anyway, with the card reading approved."""
    with company("brain_k2_promotion_refused") as url:

        async def presses(client: httpx.AsyncClient) -> tuple[str, str]:
            first = await upload(client, WEB_ADMIN, V2)
            await verify(client, WEB_ADMIN, first["item_id"])
            asked = await client.post(
                api(f"/knowledge/items/{first['item_id']}/promotion"),
                json={"review_by": LATER.isoformat(), "reason": "wanted by all"},
                headers=headers(WEB_ADMIN),
            )
            return first["item_id"], asked.json()["suspension_id"]

        item, card = pressed(url, presses)
        decide = (
            "UPDATE gate.suspension SET state = 'approved', decided_by = %s, "
            "decided_at = now(), verdict = 'approved' WHERE id = %s"
        )
        with pytest.raises(psycopg.errors.CheckViolation, match="somebody other than"):
            sql(url, decide, WEB_ADMIN, card)
        sql(url, "UPDATE know.item SET owner_id = %s WHERE item_id = %s", WEB_READER, item)
        with pytest.raises(psycopg.errors.CheckViolation, match="moved"):
            sql(url, decide, SUPER, card)
        state = sql(url, "SELECT state FROM gate.suspension WHERE id = %s", card)
        placed = sql(url, "SELECT visibility FROM know.item WHERE item_id = %s", item)

    assert state == [("pending",)]
    assert placed == [("department",)]


def test_approving_a_promotion_whose_document_was_superseded_is_refused_in_words_not_a_fault() -> (
    None
):
    """**Found on the owner's install on 2026-09-29, through the Approvals screen's own route and
    `0120`'s own trigger.** The steward asks for their document to be company-wide, then adds a
    newer version of it, so the document the card names is superseded. The Super Admin's approval
    is refused by the database, and the route answers that the request no longer applies rather
    than a 500; the card is closed as rejected under the Super Admin's name with the reason no
    approver chooses, the document stays in its department, and pressing again is the invented
    id's answer. Delete this and the translation of the trigger's refusal can drift from the words
    the trigger says, and every such card is a fault on the screen again."""
    from brain.approval_routes import A_REQUEST_THAT_NO_LONGER_APPLIES

    with company("brain_k2_promotion_moved") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            item = first["item_id"]
            await verify(client, WEB_ADMIN, item)
            asked = await client.post(
                api(f"/knowledge/items/{item}/promotion"),
                json={"review_by": LATER.isoformat(), "reason": "every team quotes it"},
                headers=headers(WEB_ADMIN),
            )
            newer = await client.post(
                api(f"/knowledge/items/{item}/versions"),
                params={"review_by": LATER.isoformat()},
                content=V2,
                headers=file_headers(WEB_ADMIN),
            )
            card = asked.json()["suspension_id"]

            async def approve() -> httpx.Response:
                return await client.post(
                    api(f"/approvals/{card}/decision"),
                    json={"verdict": "approved"},
                    headers=headers(SUPER),
                )

            return {
                "item": item,
                "card": card,
                "asked": asked,
                "newer": newer,
                "decided": await approve(),
                "again": await approve(),
                "invented": await client.post(
                    api("/approvals/promotion.nothing_here/decision"),
                    json={"verdict": "approved"},
                    headers=headers(SUPER),
                ),
            }

        said = pressed(url, presses)
        row = sql(
            url,
            "SELECT state, decided_by, verdict, reason_code FROM gate.suspension WHERE id = %s",
            said["card"],
        )
        placed = sql(
            url, "SELECT state, visibility FROM know.item WHERE item_id = %s", said["item"]
        )
        approvals = ledger(url, "leash:")

    assert said["asked"].status_code == 201, said["asked"].text
    assert said["newer"].status_code == 201, said["newer"].text
    assert said["decided"].status_code == 404, said["decided"].text
    assert said["decided"].json()["message"] == A_REQUEST_THAT_NO_LONGER_APPLIES
    assert row == [("rejected", SUPER, "rejected", "no_longer_applies")]
    assert placed == [("superseded", "department")]
    assert [
        (actor, details["verdict"], details.get("reason_code")) for actor, details in approvals
    ] == [(SUPER, "rejected", "no_longer_applies")]
    assert said["again"].status_code == said["invented"].status_code == 404
    assert without_trace(said["again"].json()) == without_trace(said["invented"].json())


# ------------------------------------------------------------------ re-verification (M7.4.6)
def test_a_document_due_for_review_opens_a_task_for_its_steward_which_verifying_closes() -> None:
    """**M7.4.6 on a server.** A verified document's review date passes; the scheduled sweep runs
    and records its nag; the nag opens a task on the steward's Knowledge page naming the document
    and the date, and on nobody else's. Verifying it again with a new date closes the task, and a
    second sweep opens nothing.

    Delete this and the sweep records a nag that no person is ever shown, which is what the owner
    saw on his install: a scheduled job, and nobody asked."""
    with company("brain_k2_reverify") as url:

        async def add(client: httpx.AsyncClient) -> str:
            first = await upload(client, WEB_ADMIN, V1)
            await verify(client, WEB_ADMIN, first["item_id"])
            return str(first["item_id"])

        item = pressed(url, add)
        sql(
            url,
            "UPDATE know.item SET verified_at = now() - interval '400 days', "
            "review_by = now() - interval '1 day' WHERE item_id = %s",
            item,
        )
        run_reverification_now(url, now=datetime.now(tz=UTC), loop_factory=_loop_factory())

        async def look(client: httpx.AsyncClient) -> dict[str, httpx.Response]:
            before = await client.get(api("/knowledge/tasks"), headers=headers(WEB_ADMIN))
            others = await client.get(api("/knowledge/tasks"), headers=headers(WEB_READER))
            dismissed = await client.post(
                api(f"/knowledge/tasks/{before.json()['items'][0]['task_id']}/done"),
                headers=headers(WEB_ADMIN),
            )
            verified = await verify(client, WEB_ADMIN, item)
            after = await client.get(api("/knowledge/tasks"), headers=headers(WEB_ADMIN))
            return {
                "before": before,
                "others": others,
                "dismissed": dismissed,
                "verified": verified,
                "after": after,
            }

        said = pressed(url, look)
        second = run_reverification_now(url, now=datetime.now(tz=UTC), loop_factory=_loop_factory())
        rows = sql(url, "SELECT kind, principal_id, done_at IS NOT NULL FROM know.steward_task")

    tasks = said["before"].json()["items"]
    assert [(one["kind"], one["item_id"], one["closable"]) for one in tasks] == [
        ("reverify", item, False)
    ]
    assert tasks[0]["says"].startswith("Site handover was due for review on ")
    assert said["others"].json()["items"] == []
    assert said["dismissed"].status_code == 404
    assert said["verified"].status_code == 200
    assert said["after"].json()["items"] == []
    assert rows == [("reverify", WEB_ADMIN, True)]
    assert second.recorded is False


# ------------------------------------------------------------------ solutions (M7.6.2)
def test_a_captured_solution_becomes_knowledge_only_when_somebody_else_approves_it() -> None:
    """**M7.6.2 on a server.** A web reader captures a solution from a conversation. It answers
    nothing while it waits; web's administrator sees it waiting and a finance reader does not; its
    capturer cannot decide it. Approved, it is a published, verified document of the
    approved-solution kind, stewarded and verified by the approver at that moment, found by text
    search, and the solution records who decided and when. The capturer is told, and the capture
    and the approval are in the ledger naming each person.

    Delete this and a solution can become company knowledge on its capturer's word, or be approved
    into a document nobody's search reaches."""
    with company("brain_k2_solution") as url:
        body = {
            "problem": "Checkout fails after the plugin update",
            "answer": "Clear the TEALFIX object cache, then retry.",
            "department": "web",
            "conversation_ref": "conv.42",
        }

        async def capture(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                api("/knowledge/solutions"), json=body, headers=headers(WEB_READER)
            )

        captured = pressed(url, capture)
        solution = captured.json()["solution_id"]
        waiting_before = searched(url, WEB_READER, "TEALFIX")

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            return {
                "captured": captured,
                "waiting_before": waiting_before,
                "admin_sees": await client.get(
                    api("/knowledge/solutions"), headers=headers(WEB_ADMIN)
                ),
                "finance_sees": await client.get(
                    api("/knowledge/solutions"), headers=headers(FINANCE_READER)
                ),
                "own": await client.post(
                    api(f"/knowledge/solutions/{solution}/decision"),
                    json={"verdict": "approved", "review_by": LATER.isoformat()},
                    headers=headers(WEB_READER),
                ),
                "approved": await client.post(
                    api(f"/knowledge/solutions/{solution}/decision"),
                    json={"verdict": "approved", "review_by": LATER.isoformat()},
                    headers=headers(WEB_ADMIN),
                ),
                "told": await client.get(api("/knowledge/tasks"), headers=headers(WEB_READER)),
            }

        said = pressed(url, presses)
        item = sql(
            url,
            "SELECT kind, state, owner_id, verified_by, department, visibility "
            "FROM know.item WHERE item_id = %s",
            solution,
        )
        row = sql(
            url,
            "SELECT state, decided_by, item_id FROM know.solution WHERE solution_id = %s",
            solution,
        )
        found = searched(url, WEB_READER, "TEALFIX")
        entries = ledger(url, "setting:knowledge_solution.")

    assert said["captured"].status_code == 201, said["captured"].text
    assert said["waiting_before"].records == ()
    assert [one["solution_id"] for one in said["admin_sees"].json()["waiting"]] == [solution]
    assert said["finance_sees"].json() == {"waiting": [], "yours": [], "departments": ["finance"]}
    assert said["own"].status_code == 404
    assert said["approved"].status_code == 200, said["approved"].text
    assert item == [("approved_solution", "published", WEB_ADMIN, WEB_ADMIN, "web", "department")]
    assert row == [("approved", WEB_ADMIN, solution)]
    assert found.records and found.records[0].document_id == solution
    assert [(actor, details["change"]) for actor, details in entries] == [
        (WEB_READER, "captured"),
        (WEB_ADMIN, "approved"),
    ]
    assert any(
        "was approved and is now company knowledge" in one["says"]
        for one in said["told"].json()["items"]
    )


# ------------------------------------------------------------------ stewards (M7.7.2)
def test_a_steward_is_handed_over_to_somebody_who_reaches_it_and_is_told() -> None:
    """**M7.7.2's per-document half on a server.** Web's administrator hands a document to a web
    reader: the document and its passages name the new steward, the new steward has a task saying
    so, which only they can mark read, and the ledger records the change of steward. Handing it to
    a finance reader, and to a person who does not exist, is refused in one sentence.

    Delete this and a steward can be named who can never be asked, or named with nobody told."""
    with company("brain_k2_steward") as url:

        async def presses(client: httpx.AsyncClient) -> dict[str, Any]:
            first = await upload(client, WEB_ADMIN, V1)
            item = first["item_id"]

            async def hand(to: str) -> httpx.Response:
                return await client.post(
                    api(f"/knowledge/items/{item}/steward"),
                    json={"steward_id": to},
                    headers=headers(WEB_ADMIN),
                )

            finance = await hand(FINANCE_READER)
            nobody = await hand("u_nobody_at_all")
            reader = await hand(WEB_READER)
            told = await client.get(api("/knowledge/tasks"), headers=headers(WEB_READER))
            task = told.json()["items"][0]["task_id"]
            by_somebody_else = await client.post(
                api(f"/knowledge/tasks/{task}/done"), headers=headers(WEB_ADMIN)
            )
            read = await client.post(
                api(f"/knowledge/tasks/{task}/done"), headers=headers(WEB_READER)
            )
            return {
                "item": item,
                "finance": finance,
                "nobody": nobody,
                "reader": reader,
                "told": told,
                "by_somebody_else": by_somebody_else,
                "read": read,
            }

        said = pressed(url, presses)
        item = said["item"]
        owners = set(
            sql(url, "SELECT DISTINCT owner_id FROM know.chunk WHERE document_id = %s", item)
        )
        steward = sql(url, "SELECT owner_id FROM know.item WHERE item_id = %s", item)
        changed = [details.get("changed") for _, details in ledger(url, "setting:knowledge_item.")]

    assert said["finance"].status_code == said["nobody"].status_code == 422
    assert said["finance"].json()["message"] == said["nobody"].json()["message"] == STEWARD_REFUSED
    assert said["reader"].status_code == 200, said["reader"].text
    assert said["reader"].json()["steward_id"] == WEB_READER
    assert steward == [(WEB_READER,)]
    assert owners == {(WEB_READER,)}
    assert [one["kind"] for one in said["told"].json()["items"]] == ["steward_named"]
    assert said["by_somebody_else"].status_code == 404
    assert said["read"].status_code == 200
    assert said["read"].json()["items"] == []
    assert "owner_id" in changed


# ------------------------------------------------------------------ the tables
def test_the_tables_are_what_the_models_declare_and_the_application_opens_no_task() -> None:
    """Every constraint, index and column of both tables, compared between `0120` and the models;
    row-level security on both; the application role holds no insert on the task table and reads
    another person's tasks as none. Delete this and the migration and the model can disagree, or a
    route could open a task nobody's trigger vouched for."""
    with (
        company("brain_k2_tables") as url,
        modelled("brain_k2_tables_modelled", TABLES) as from_models,
    ):
        assert shape(url, TABLES) == shape(from_models, TABLES)
        assert secured(url, TABLES) == dict.fromkeys(TABLES, True)
        sql(
            url,
            "INSERT INTO know.steward_task (task_id, principal_id, kind, item_id, opened_at) "
            "VALUES ('steward.x', %s, 'steward_named', 'upload.x', now())",
            WEB_READER,
        )
        with psycopg.connect(url) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config('app.principal_id', %s, true)", (FINANCE_READER,))
            others = conn.execute("SELECT count(*) FROM know.steward_task").fetchone()
            conn.execute("SELECT set_config('app.principal_id', %s, true)", (WEB_READER,))
            own = conn.execute("SELECT count(*) FROM know.steward_task").fetchone()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO know.steward_task (task_id, principal_id, kind, item_id, "
                    "opened_at) VALUES ('steward.y', %s, 'steward_named', 'upload.y', now())",
                    (WEB_READER,),
                )

    assert others == (0,)
    assert own == (1,)
