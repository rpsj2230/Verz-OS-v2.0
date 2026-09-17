"""The Import and export screen over HTTP: who may export, in what order, and what is handed over.

Driven through the real application with the gate from `tests/unit/test_webhook_routes.py`. The
store is `Exports`, an in-memory `brain.ops.data_export_store.ExportRecords` that keeps what the
route's `keep` keeps of its window and runs the route's own `produce` over it, as the database
store does, so the document a test reads is the one the route rendered. The database half, the
record and its ledger entry, is `tests/unit/test_data_export_store.py`.

The six people are the fake directory's six subjects, given grants that matter here: nothing; the
whole ledger and the audit screen without `admin:export`; `admin:export` alone; `admin:export` and
the whole ledger without the audit screen; everything, who takes the chain; and `admin:export` with
the audit screen and the principal entries only, who takes the entries they may read.

Task ids: M27.8.16, M27.9.4
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.export import verify_document
from brain.audit.ledger import AuditEntry
from brain.audit.readable_export import verify_readable_document
from brain.audit.view import CAPABILITY_BY_KIND
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.data_transfer_routes import DATA_TRANSFER_PATH, EXPORTS_PATH
from brain.ops.data_export_store import TakenExport
from brain.ops.data_transfer import (
    A_READABLE_EXPORT_CARRIES_WHAT_YOU_MAY_READ,
    AN_AUDIT_EXPORT_CAN_BE_CHECKED_WITHOUT_THIS_SYSTEM,
    EMPTY_WINDOW,
    EXPORT_AUTHORITY,
    NOTHING_YOU_MAY_READ,
    Produced,
    may_export,
)
from brain.ops.export import ExportReason
from brain.tables.data_export import ExportDataSet, ExportForm
from tests.unit.test_audit_routes import Ledger
from tests.unit.test_data_transfer import (
    HIDDEN_AFTER,
    HIDDEN_AGENT,
    HIDDEN_READ,
    HIDDEN_SAME_INSTANT,
    LEDGER,
    LONG_AGO,
    SCREEN,
    SEEN_FIRST,
    SEEN_LAST,
    SEEN_TOGETHER_A,
    SEEN_TOGETHER_B,
    SINCE,
    UNTIL,
    every_kind_of_entry,
    ledger,
)
from tests.unit.test_webhook_routes import NoDatabase, headers, wiring

LISTING = f"{API_PREFIX}{DATA_TRANSFER_PATH}"
TAKE = f"{API_PREFIX}{EXPORTS_PATH}"
AUDIT = f"{API_PREFIX}/audit"
WHOLE = Scope.unrestricted()


def held(*capabilities: object) -> tuple[Grant, ...]:
    return tuple(Grant.model_validate({"capability": one, "scope": WHOLE}) for one in capabilities)


GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_narrow": held(*SCREEN, *LEDGER),
    "u_wide": held(EXPORT_AUTHORITY),
    "u_prefix": held(EXPORT_AUTHORITY, *LEDGER),
    "u_admin": held(EXPORT_AUTHORITY, *SCREEN, *LEDGER),
    "u_elsewhere": held(EXPORT_AUTHORITY, *SCREEN, CAPABILITY_BY_KIND["principal"]),
}


class Exports:
    """`ExportRecords` in memory: keeps what `keep` keeps, runs `produce`, records what it saw."""

    def __init__(self, window: Sequence[AuditEntry]) -> None:
        self.window = tuple(window)
        self.asked: list[str] = []
        self.forms: list[ExportForm] = []
        self.taken: list[TakenExport] = []

    async def take_audit_export(
        self,
        *,
        since: datetime,
        until: datetime,
        limit: int,
        form: ExportForm,
        keep: Callable[[Sequence[AuditEntry]], Sequence[AuditEntry]],
        actor: str,
        ent_hash: str,
        trace_id: str,
        reason: ExportReason,
        reason_reference: str,
        at: datetime,
        produce: Callable[[Sequence[AuditEntry]], Produced],
    ) -> tuple[TakenExport, Produced]:
        self.asked.append("take")
        self.forms.append(form)
        produced = produce(tuple(keep(self.window))[: limit + 1])
        taken = TakenExport(
            export_id="11111111-1111-4111-8111-111111111111",
            data_set=ExportDataSet.AUDIT_TRAIL,
            requested_by=actor,
            reason=reason,
            reason_reference=reason_reference,
            produced_at=at,
            form=produced.form,
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
        "since": SINCE.isoformat(),
        "until": UNTIL.isoformat(),
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


@pytest.mark.parametrize("pid", ["u_none", "u_narrow", "u_wide", "u_prefix"])
def test_an_export_is_refused_in_one_sentence_before_it_is_judged_or_anything_is_read(
    app: FastAPI, client: TestClient, pid: str
) -> None:
    """Nothing held; the whole ledger and the audit screen without `admin:export`; `admin:export`
    alone; and `admin:export` with the whole ledger but not the audit screen. One body each, and the
    store never asked, including for a malformed request. The positive siblings are the exports
    below. Delete this and a holder of `admin:export` learns from a 422 or an empty window what the
    ledger holds, or takes a copy of an audit trail whose screen is closed to them."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    for body in (request(), request(reason="nope", reason_reference="")):
        refused = take(client, pid, body)
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    assert store.asked == []


def test_a_password_only_session_holding_everything_cannot_export(
    app: FastAPI, client: TestClient
) -> None:
    """`admin:` is withheld without a second factor. Delete this and the export capability can be
    respelled `read:` to reach it from a password."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    assert take(client, "u_admin", request(), claims={"amr": ["pwd"]}).status_code == 404
    assert store.asked == []


def test_the_export_is_offered_to_exactly_the_holders_of_the_export_grant_the_audit_trail_opens_for(
    app: FastAPI, client: TestClient
) -> None:
    """Who may export is decided by asking the audit trail's own route rather than by a list here:
    for every person, the listing offers the export exactly when `GET /audit` answers them and they
    hold `admin:export`. Delete this and the export's second half can drift from the screen's, which
    is how it came to ask for the whole ledger while the screen asked for its own read."""
    app.state.export_records = Exports(())
    app.state.audit_ledger = Ledger()
    offered: dict[str, bool] = {}
    for pid, grants in GRANTS.items():
        opens = client.get(AUDIT, headers=headers(pid)).status_code == 200
        exporter = may_export(EntitlementSet(principal_id=pid, grants=grants), LONG_AGO)
        listed = client.get(LISTING, headers=headers(pid)).json()
        assert listed["exportable"] is (opens and exporter), pid
        offered[pid] = listed["exportable"]
    assert offered == {
        "u_none": False,
        "u_narrow": False,
        "u_wide": False,
        "u_prefix": False,
        "u_admin": True,
        "u_elsewhere": True,
    }


# -------------------------------------------------------------------- the listing


def test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own(
    app: FastAPI, client: TestClient
) -> None:
    """A reader who may not export is told so and the store is not asked; one who may sees the
    exports they took, asked for by their own id, and the form their export takes in words. Delete
    this and the listing becomes a second export log behind a different decision from the Exports
    screen's, or promises a partial reader a chain they will not receive."""
    store = Exports(every_kind_of_entry())
    app.state.export_records = store
    refused = client.get(LISTING, headers=headers("u_wide")).json()
    assert (refused["exportable"], refused["exports"], refused["form"], refused["form_told"]) == (
        False,
        [],
        None,
        None,
    )
    assert store.asked == []
    assert take(client, "u_admin", request()).status_code == 200
    listed = client.get(LISTING, headers=headers("u_admin")).json()
    assert listed["exportable"] is True
    assert (listed["form"], listed["form_told"]) == (
        "chain",
        AN_AUDIT_EXPORT_CAN_BE_CHECKED_WITHOUT_THIS_SYSTEM,
    )
    assert [one["reason_reference"] for one in listed["exports"]] == ["MATTER-2019/004"]
    assert store.asked[-1] == "taken_by:u_admin"
    assert [one["key"] for one in listed["catalogue"] if one["runs"]] == ["audit_trail"]
    assert listed["reasons"] == [one.value for one in ExportReason]
    partial = client.get(LISTING, headers=headers("u_elsewhere")).json()
    assert (partial["exportable"], partial["form"], partial["form_told"]) == (
        True,
        "readable",
        A_READABLE_EXPORT_CARRIES_WHAT_YOU_MAY_READ,
    )


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
    assert (record["form"], record["verified"]) == ("chain", True)
    assert store.taken[0].requested_by == "u_admin"
    assert store.forms == [ExportForm.CHAIN]
    assert body["filename"] == f"audit_trail-{record['first_seq']}-{record['last_seq']}.jsonl"
    assert "u_admin" not in body["filename"]


def test_a_partial_reader_is_handed_the_entries_they_may_read_with_no_window_and_no_verdict(
    app: FastAPI, client: TestClient
) -> None:
    """M27.9.4 through the route. The store is asked for the readable form and keeps what the view
    shows; the document is the readable one and carries the two principal entries and nothing of
    the others; the record and the filename name no sequence number. Delete this and the route can
    hand a partial reader the chain's refusal, or a record whose range counts what was withheld."""
    store = Exports(ledger(HIDDEN_AGENT, SEEN_FIRST, HIDDEN_READ, SEEN_LAST, HIDDEN_AFTER))
    app.state.export_records = store
    answered = take(client, "u_elsewhere", request())
    assert answered.status_code == 200
    body = answered.json()
    assert store.forms == [ExportForm.READABLE]
    assert verify_readable_document(body["document"]) == (True, "manifest matches the entry block")
    lines = [json.loads(one) for one in body["document"].splitlines()[1:]]
    assert [(one["subject_kind"], one["subject_id"]) for one in lines] == [
        ("principal", "u_wei"),
        ("principal", "u_cy"),
    ]
    record = body["export"]
    assert (record["form"], record["first_seq"], record["last_seq"], record["verified"]) == (
        "readable",
        None,
        None,
        None,
    )
    assert record["entries"] == 2
    assert body["filename"] == f"audit_trail-{record['export_id']}.jsonl"


def test_a_readable_export_through_the_route_is_the_same_with_or_without_entries_withheld(
    app: FastAPI, client: TestClient
) -> None:
    """Byte identity end to end, less the two values each request legitimately makes its own: the
    instant it was taken, which is the request's clock, and its trace id, which the middleware mints
    per request. Everything else, the window, the count, the digest of the entry lines and every
    line, is equal. Delete this and the route can pass the store a window of raw rows, or name the
    window by what it found, while the pure property still holds."""

    def exported(window: tuple[AuditEntry, ...]) -> tuple[dict[str, Any], list[str], int]:
        app.state.export_records = Exports(window)
        body = take(client, "u_elsewhere", request()).json()
        manifest, *lines = body["document"].splitlines()
        stated = json.loads(manifest)
        del stated["exported_at"], stated["trace_id"]
        return stated, lines, body["export"]["entries"]

    withheld = exported(
        ledger(
            HIDDEN_AGENT,
            SEEN_FIRST,
            HIDDEN_READ,
            SEEN_TOGETHER_A,
            HIDDEN_SAME_INSTANT,
            SEEN_TOGETHER_B,
            SEEN_LAST,
            HIDDEN_AFTER,
        )
    )
    never_written = exported(ledger(SEEN_FIRST, SEEN_TOGETHER_A, SEEN_TOGETHER_B, SEEN_LAST))
    assert withheld == never_written
    assert datetime.fromisoformat(withheld[0]["since"]) == SINCE


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
    """Refused with the sentence, as a field the person changes. For a partial reader a window of
    only withheld entries is refused in the same words as a window of nothing. Delete this and an
    empty window answers a 500, or a document of nothing is recorded as an export, or the two
    windows are told apart."""
    for pid, window, said in (
        ("u_admin", (), EMPTY_WINDOW),
        ("u_elsewhere", (), NOTHING_YOU_MAY_READ),
        ("u_elsewhere", ledger(HIDDEN_AGENT, HIDDEN_READ), NOTHING_YOU_MAY_READ),
    ):
        store = Exports(window)
        app.state.export_records = store
        refused = take(client, pid, request())
        assert refused.status_code == 422
        assert refused.json()["problems"] == [
            {"field": "window", "code": "window_refused", "message": said}
        ]
        assert store.taken == []
