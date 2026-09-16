"""The Import and export screen over HTTP: who may export, in what order, and what is handed over.

Driven through the real application with the gate from `tests/unit/test_webhook_routes.py`. The
store is `Exports`, an in-memory `brain.ops.data_export_store.ExportRecords` that runs the route's
own `produce` over a window built with `AuditChain`, so the document a test reads is the one the
route rendered. The database half, the record and its ledger entry, is
`tests/unit/test_data_export_store.py`.

Task ids: M27.8.16
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.export import verify_document
from brain.audit.ledger import AuditEntry
from brain.core.entitlement import Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.data_transfer_routes import DATA_TRANSFER_PATH, EXPORTS_PATH
from brain.ops.data_export_store import TakenExport
from brain.ops.data_transfer import EMPTY_WINDOW, EXPORT_AUTHORITY, Produced
from brain.ops.export import ExportReason
from brain.tables.data_export import ExportDataSet
from tests.unit.test_data_transfer import LEDGER, LONG_AGO, every_kind_of_entry
from tests.unit.test_webhook_routes import NoDatabase, headers, wiring

LISTING = f"{API_PREFIX}{DATA_TRANSFER_PATH}"
TAKE = f"{API_PREFIX}{EXPORTS_PATH}"
WHOLE = Scope.unrestricted()

GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_narrow": tuple(Grant(capability=one, scope=WHOLE) for one in LEDGER),
    "u_wide": (Grant(capability=EXPORT_AUTHORITY, scope=WHOLE),),
    "u_prefix": (),
    "u_admin": (
        Grant(capability=EXPORT_AUTHORITY, scope=WHOLE),
        *(Grant(capability=one, scope=WHOLE) for one in LEDGER),
    ),
    "u_elsewhere": (),
}


class Exports:
    """`ExportRecords` in memory: runs `produce` over its window, and records what it was asked."""

    def __init__(self, window: Sequence[AuditEntry]) -> None:
        self.window = tuple(window)
        self.asked: list[str] = []
        self.taken: list[TakenExport] = []

    async def take_audit_export(
        self,
        *,
        since: datetime,
        until: datetime,
        limit: int,
        actor: str,
        ent_hash: str,
        trace_id: str,
        reason: ExportReason,
        reason_reference: str,
        at: datetime,
        produce: Callable[[Sequence[AuditEntry]], Produced],
    ) -> tuple[TakenExport, Produced]:
        self.asked.append("take")
        produced = produce(self.window)
        taken = TakenExport(
            export_id="11111111-1111-4111-8111-111111111111",
            data_set=ExportDataSet.AUDIT_TRAIL,
            requested_by=actor,
            reason=reason,
            reason_reference=reason_reference,
            produced_at=at,
            first_seq=produced.first_seq,
            last_seq=produced.last_seq,
            entries=produced.entries,
            verified=produced.verified,
            document_digest=produced.digest,
        )
        self.taken.append(taken)
        return taken, produced

    async def taken_by(self, principal_id: str, *, limit: int) -> tuple[TakenExport, ...]:
        self.asked.append(f"taken_by:{principal_id}")
        return tuple(one for one in self.taken if one.requested_by == principal_id)


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring(GRANTS)
        app.state.db_sessions = NoDatabase()
        yield c


def request(**changed: object) -> dict[str, object]:
    body: dict[str, object] = {
        "data_set": ExportDataSet.AUDIT_TRAIL.value,
        "reason": ExportReason.REGULATORY_REQUEST.value,
        "reason_reference": "MATTER-2019/004",
        "since": LONG_AGO.isoformat(),
        "until": (LONG_AGO + timedelta(days=1)).isoformat(),
    }
    body.update(changed)
    return body


def take(c: TestClient, pid: str, body: object, **kw: Any) -> Any:
    return c.post(TAKE, headers=headers(pid, **kw), json=body)


def without_trace(response: Any) -> dict[str, Any]:
    found = dict(response.json())
    found.pop("trace_id", None)
    return found


# ---------------------------------------------------------------------- who may


@pytest.mark.parametrize("pid", ["u_none", "u_narrow", "u_wide"])
def test_an_export_is_refused_in_one_sentence_before_it_is_judged_or_anything_is_read(
    app: FastAPI, client: TestClient, pid: str
) -> None:
    """Nothing held, the whole ledger without `admin:export`, and `admin:export` without the whole
    ledger: one body each, and the store never asked, including for a malformed request. The
    positive sibling is the export below. Delete this and a holder of `admin:export` alone learns
    from a 422 or an empty window what the ledger holds."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    for body in (request(), request(reason="nope", reason_reference="")):
        refused = take(client, pid, body)
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    assert store.asked == []


def test_a_password_only_session_holding_both_cannot_export(
    app: FastAPI, client: TestClient
) -> None:
    """`admin:` is withheld without a second factor. Delete this and the export capability can be
    respelled `read:` to reach it from a password."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    assert take(client, "u_admin", request(), claims={"amr": ["pwd"]}).status_code == 404
    assert store.asked == []


# -------------------------------------------------------------------- the listing


def test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own(
    app: FastAPI, client: TestClient
) -> None:
    """A reader who may not export is told so and the store is not asked; one who may sees the
    exports they took, asked for by their own id. Delete this and the listing becomes a second
    export log behind a different decision from the Exports screen's."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    refused = client.get(LISTING, headers=headers("u_wide")).json()
    assert (refused["exportable"], refused["exports"]) == (False, [])
    assert store.asked == []
    assert take(client, "u_admin", request()).status_code == 200
    listed = client.get(LISTING, headers=headers("u_admin")).json()
    assert listed["exportable"] is True
    assert [one["reason_reference"] for one in listed["exports"]] == ["MATTER-2019/004"]
    assert store.asked[-1] == "taken_by:u_admin"
    assert [one["key"] for one in listed["catalogue"] if one["runs"]] == ["audit_trail"]
    assert listed["reasons"] == [one.value for one in ExportReason]


# ---------------------------------------------------------------------- the write


def test_an_export_hands_over_the_rendered_document_and_its_record_after_the_store_returns(
    app: FastAPI, client: TestClient
) -> None:
    """The document verifies, the record's digest is its sha256, the actor is the person asking and
    the filename names the window and no person. Delete this and a route that hands over a document
    the store never recorded, or records a digest of something else, passes."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    answered = take(client, "u_admin", request())
    assert answered.status_code == 200
    body = answered.json()
    document = body["document"]
    assert verify_document(document)[0] is True
    record = body["export"]
    assert record["document_digest"] == hashlib.sha256(document.encode("utf-8")).hexdigest()
    assert store.taken[0].requested_by == "u_admin"
    assert body["filename"] == f"audit_trail-{record['first_seq']}-{record['last_seq']}.jsonl"
    assert "u_admin" not in body["filename"]


def test_a_request_with_problems_is_told_all_of_them_and_nothing_is_read(
    app: FastAPI, client: TestClient
) -> None:
    """Delete this and a reference carrying a person's name reaches the store and the ledger."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    refused = take(
        client,
        "u_admin",
        request(data_set="knowledge", reason="because", reason_reference="Wei Ling"),
    )
    assert refused.status_code == 422
    assert [(p["field"], p["code"]) for p in refused.json()["problems"]] == [
        ("data_set", "not_available"),
        ("reason", "unknown"),
        ("reason_reference", "not_a_reference"),
    ]
    assert store.asked == []


def test_an_empty_window_is_a_problem_on_the_window(app: FastAPI, client: TestClient) -> None:
    """Refused with the sentence, as a field the person changes. Delete this and an empty window
    answers a 500, or worse, a document of nothing recorded as an export."""
    store = Exports(())
    app.state.export_records = store
    refused = take(client, "u_admin", request())
    assert refused.status_code == 422
    assert refused.json()["problems"] == [
        {"field": "window", "code": "window_refused", "message": EMPTY_WINDOW}
    ]
    assert store.taken == []
