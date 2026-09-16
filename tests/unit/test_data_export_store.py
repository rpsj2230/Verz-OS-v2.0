"""The export store against a real database: an audit trail export leaves its record and its
ledger entry, or nothing.

The window is real ledger entries, appended by `0003`'s grant trigger when grants are written, and
the export is rendered by `brain.ops.data_transfer.produce_audit_export` over what the store read.
The proof is the three places `docs/admin-console.md` names: the `ops.data_export` row, the
`publish` entry `0053`'s trigger appends under `artifact:<export_id>`, and the behaviour, which is
that the record's digest is the digest of the document handed over. A render that fails leaves no
row and no entry.

It needs the full migration chain, which a server with pgvector builds, and skips without one; CI
has one.

Task ids: M27.8.16
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.audit.ledger import AuditEntry
from brain.ops.data_export_store import StoredExports
from brain.ops.data_transfer import Produced, produce_audit_export
from brain.ops.export import ExportReason
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_data_transfer import EXPORTER
from tests.unit.test_webhook_store import through_head


def with_store[T](url: str, work: Callable[[StoredExports], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredExports(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def seed_ledger(url: str) -> None:
    """Two grants, whose trigger appends two ledger entries."""
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES ('u_holder', 'human', 'staff', 'Holder', 'web')",
    )
    for capability in ("read:client.name", "read:invoice.total"):
        sql(
            url,
            "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
            " reason) VALUES ('u_holder', %s, '{\"clauses\": []}', 'u_seed', 'needed')",
            capability,
        )


def producing(at: datetime) -> Callable[[Sequence[AuditEntry]], Produced]:
    def produce(entries: Sequence[AuditEntry]) -> Produced:
        return produce_audit_export(
            entries,
            reader=EXPORTER,
            reason=ExportReason.REGULATORY_REQUEST,
            trace_id="trace-export",
            at=at,
        )

    return produce


def test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it() -> None:
    """M27.8.16's proof. Delete this and an export can hand over a document with no record, or a
    record with no ledger entry, while the route tests stay green."""
    with through_head("brain_data_export") as url:
        seed_ledger(url)
        now = datetime.now(UTC)

        async def take(store: StoredExports) -> Any:
            return await store.take_audit_export(
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
                limit=1000,
                actor="u_exporter",
                ent_hash="c" * 32,
                trace_id="trace-export",
                reason=ExportReason.REGULATORY_REQUEST,
                reason_reference="MATTER-1",
                at=now,
                produce=producing(now),
            )

        taken, produced = with_store(url, take)
        assert produced.entries >= 2 and produced.verified is True
        assert taken.document_digest == hashlib.sha256(produced.document.encode()).hexdigest()
        [(requested_by, entries, digest)] = sql(
            url, "SELECT requested_by, entries, document_digest FROM ops.data_export"
        )
        assert (requested_by, entries, digest) == (
            "u_exporter",
            produced.entries,
            taken.document_digest,
        )
        [(actor, details, ent_hash, trace)] = sql(
            url,
            "SELECT actor_id, details, ent_hash, trace_id FROM obs.audit_entry"
            " WHERE action = 'publish' AND subject = %s",
            f"artifact:{taken.export_id}",
        )
        assert (actor, details, ent_hash, trace) == (
            "u_exporter",
            {"fields": "audit_trail"},
            "c" * 32,
            "trace-export",
        )

        async def mine(store: StoredExports) -> Any:
            return await store.taken_by("u_exporter", limit=5)

        assert [one.export_id for one in with_store(url, mine)] == [taken.export_id]


def test_an_export_that_fails_to_render_leaves_no_record_and_no_entry() -> None:
    """Delete this and a failure after the insert commits a record of an export nobody received."""
    with through_head("brain_data_export_failed") as url:
        seed_ledger(url)
        now = datetime.now(UTC)

        def fails(entries: Sequence[AuditEntry]) -> Produced:
            raise RuntimeError("the render failed")

        async def take(store: StoredExports) -> Any:
            return await store.take_audit_export(
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
                limit=1000,
                actor="u_exporter",
                ent_hash="c" * 32,
                trace_id="trace-export",
                reason=ExportReason.REGULATORY_REQUEST,
                reason_reference="MATTER-1",
                at=now,
                produce=fails,
            )

        with pytest.raises(RuntimeError):
            with_store(url, take)
        assert sql(url, "SELECT count(*) FROM ops.data_export") == [(0,)]
        assert sql(url, "SELECT count(*) FROM obs.audit_entry WHERE action = 'publish'") == [(0,)]
