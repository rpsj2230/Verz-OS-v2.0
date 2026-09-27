"""The export store against a real database: an audit trail export leaves its record and its
ledger entry, or nothing, and a readable export is read, limited and recorded by what its exporter
may read.

The chain's window is real ledger entries, appended by `0003`'s grant trigger when grants are
written, and the export is rendered by `brain.ops.data_transfer.produce_audit_export` over what the
store read. The proof is the three places `docs/admin-console.md` names: the `ops.data_export` row,
the `publish` entry `0053`'s trigger appends under `artifact:<export_id>`, and the behaviour, which
is that the record's digest is the digest of the document handed over. A render that fails leaves
no row and no entry.

The readable export's window is written into `obs.audit_entry` from `AuditChain`, so its sequence
numbers and digests are a real chain with entries its exporter may not read between the ones they
may, and `0082`'s constraints are asked directly with statements a person could type.

`through_0082` builds the chain on any server. With pgvector, which CI has, `retirable` runs every
migration to head. Without it `retirable` stops at `0048`; `0049` is run, then the migrations that
build what `0053` needs and nothing else built, each after a stamp of its predecessor: `0025`
because `0030` widens its constraint, `0030` for the webhook subscriber `0053` points at, `0053`
itself, and `0082` after a stamp of the revision it names.

Task ids: M27.8.16, M27.9.4
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.audit.ledger import AuditAction, AuditEntry
from brain.ops import data_export_store
from brain.ops.data_export_store import AN_ENTRY_THAT_DOES_NOT_READ, StoredExports, entries_of
from brain.ops.data_transfer import (
    AuditExportRefusedError,
    Produced,
    kept_by,
    produce_audit_export,
)
from brain.ops.export import ExportReason
from brain.session import make_session_factory
from brain.tables.data_export import ExportForm
from tests.fixtures.retirable import has_pgvector, predecessor, retirable, revision_of
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_audit_routes import stored
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_data_transfer import (
    EXPORTER,
    PARTIAL,
    SINCE,
    TAKEN_AT,
    UNTIL,
    Written,
    ledger,
    taken,
)

READABLE_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0082_readable_audit_export.py"
)

#: A window for the store, in the actions and subject kinds every chain `through_0082` builds
#: admits: without pgvector the chain is stamped past the migrations that widened both lists.
#: Readable by `PARTIAL` are the principal entries, two of them at one instant.
SEEN: tuple[Written, ...] = (
    (AuditAction.GRANT, "principal:u_wei", 10),
    (AuditAction.REVOKE, "principal:u_ana", 20),
    (AuditAction.GRANT, "principal:u_bo", 20),
    (AuditAction.REVOKE, "principal:u_cy", 30),
)
#: The whole window: withheld entries before, between, beside and after the readable ones.
WINDOW: tuple[Written, ...] = (
    (AuditAction.LEASH_CHANGE, "agent:helper", 5),
    SEEN[0],
    (AuditAction.GRANT, "grant:g1", 15),
    SEEN[1],
    (AuditAction.REVOKE, "grant:g2", 20),
    SEEN[2],
    SEEN[3],
    (AuditAction.DENY, "connector:lark", 40),
)


@contextmanager
def through_0082(database: str) -> Iterator[str]:
    """A database with `0053` and `0082` applied. See the module docstring."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            for before, revision in (("0024", "0025"), ("0029", "0030"), ("0052", "0053")):
                migrate(database, "stamp", before)
                migrate(database, "upgrade", revision)
            migrate(database, "stamp", predecessor(READABLE_MIGRATION))
            migrate(database, "upgrade", revision_of(READABLE_MIGRATION))
        yield url


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


def write_ledger(url: str, entries: Sequence[AuditEntry]) -> None:
    """These entries into `obs.audit_entry` as they are, sequence numbers and digests included."""
    for one in entries:
        sql(
            url,
            "INSERT INTO obs.audit_entry (seq, at, actor_id, action, subject, ent_hash, trace_id,"
            " details, prev_hash, entry_hash)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
            one.seq,
            one.at,
            one.actor_id,
            one.action.value,
            one.subject,
            one.ent_hash,
            one.trace_id,
            '{"capability": "read:client.name"}',
            one.prev_hash,
            one.entry_hash,
        )


def producing(at: datetime) -> Callable[[Sequence[AuditEntry]], Produced]:
    def produce(entries: Sequence[AuditEntry]) -> Produced:
        return produce_audit_export(
            entries,
            reader=EXPORTER,
            reason=ExportReason.REGULATORY_REQUEST,
            trace_id="trace-export",
            at=at,
            since=at - timedelta(days=1),
            until=at + timedelta(days=1),
        )

    return produce


def test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it() -> None:
    """M27.8.16's proof. Delete this and an export can hand over a document with no record, or a
    record with no ledger entry, while the route tests stay green."""
    with through_0082("brain_data_export") as url:
        seed_ledger(url)
        now = datetime.now(UTC)

        async def take(store: StoredExports) -> Any:
            return await store.take_audit_export(
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
                limit=1000,
                form=ExportForm.CHAIN,
                keep=kept_by(ExportForm.CHAIN, EXPORTER, now),
                actor="u_exporter",
                ent_hash="c" * 32,
                trace_id="trace-export",
                reason=ExportReason.REGULATORY_REQUEST,
                reason_reference="MATTER-1",
                at=now,
                produce=producing(now),
            )

        taken_export, produced = with_store(url, take)
        assert produced.entries >= 2 and produced.verified is True
        assert (
            taken_export.document_digest == hashlib.sha256(produced.document.encode()).hexdigest()
        )
        [(requested_by, entries, digest, form)] = sql(
            url, "SELECT requested_by, entries, document_digest, form FROM ops.data_export"
        )
        assert (requested_by, entries, digest, form) == (
            "u_exporter",
            produced.entries,
            taken_export.document_digest,
            "chain",
        )
        [(actor, details, ent_hash, trace)] = sql(
            url,
            "SELECT actor_id, details, ent_hash, trace_id FROM obs.audit_entry"
            " WHERE action = 'publish' AND subject = %s",
            f"artifact:{taken_export.export_id}",
        )
        assert (actor, details, ent_hash, trace) == (
            "u_exporter",
            {"fields": "audit_trail"},
            "c" * 32,
            "trace-export",
        )

        async def mine(store: StoredExports) -> Any:
            return await store.taken_by("u_exporter", limit=5)

        assert [one.export_id for one in with_store(url, mine)] == [taken_export.export_id]


def test_an_export_that_fails_to_render_leaves_no_record_and_no_entry() -> None:
    """Delete this and a failure after the insert commits a record of an export nobody received."""
    with through_0082("brain_data_export_failed") as url:
        seed_ledger(url)
        now = datetime.now(UTC)

        def fails(entries: Sequence[AuditEntry]) -> Produced:
            raise RuntimeError("the render failed")

        async def take(store: StoredExports) -> Any:
            return await store.take_audit_export(
                since=now - timedelta(days=1),
                until=now + timedelta(days=1),
                limit=1000,
                form=ExportForm.CHAIN,
                keep=kept_by(ExportForm.CHAIN, EXPORTER, now),
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


# ------------------------------------------------------------ the readable form


#: A readable export's record as a statement at the server would write it, less what varies.
INSERT_RECORD = (
    "INSERT INTO ops.data_export (data_set, requested_by, reason, reason_reference, form,"
    " first_seq, last_seq, entries, verified, document_digest) VALUES ('audit_trail', 'u_exporter',"
    " 'regulatory_request', 'MATTER-1', %s, %s, %s, %s, %s, %s)"
)


def refused_by(url: str, *values: object) -> str | None:
    """The constraint that refuses this record, or None when the table takes it."""
    import psycopg

    try:
        sql(url, INSERT_RECORD, *values, "d" * 64)
    except psycopg.errors.CheckViolation as refused:
        return refused.diag.constraint_name
    return None


def test_the_table_records_a_readable_export_with_no_window_and_still_refuses_a_broken_chain() -> (
    None
):
    """`0082`'s constraints, asked with statements a person could type. A readable record with a
    count, no sequence range and no verdict is taken, and so is a contiguous chain, with the form
    defaulted for an insert that names none. A chain whose range does not match its count, a chain
    with a count and no range, a readable record naming a range, and a verdict on the wrong form
    are refused, each by the constraint that says so. Delete this and the migration can loosen the
    chain's constraints for everybody, or record a readable export with the range that counts what
    it withheld."""
    with through_0082("brain_data_export_forms") as url:
        assert refused_by(url, "readable", None, None, 3, None) is None
        assert refused_by(url, "chain", 10, 12, 3, True) is None
        sql(
            url,
            "INSERT INTO ops.data_export (data_set, requested_by, reason, reason_reference,"
            " first_seq, last_seq, entries, verified, document_digest) VALUES ('audit_trail',"
            " 'u_exporter', 'regulatory_request', 'MATTER-2', 20, 21, 2, false, %s)",
            "e" * 64,
        )
        assert sql(url, "SELECT form, verified FROM ops.data_export ORDER BY entries, form") == [
            ("chain", False),
            ("chain", True),
            ("readable", None),
        ]
        assert refused_by(url, "chain", 10, 15, 3, True) == (
            "ck_data_export_the_window_is_contiguous"
        )
        assert refused_by(url, "chain", None, None, 3, True) == (
            "ck_data_export_a_window_names_both_ends_or_neither"
        )
        assert refused_by(url, "readable", 10, 15, 3, None) == (
            "ck_data_export_a_readable_export_names_no_window"
        )
        assert refused_by(url, "readable", None, None, 3, False) == (
            "ck_data_export_only_a_chain_says_whether_it_verified"
        )
        assert refused_by(url, "chain", 10, 12, 3, None) == (
            "ck_data_export_only_a_chain_says_whether_it_verified"
        )
        assert refused_by(url, "sample", None, None, 3, None) == "ck_data_export_form"


def test_a_readable_export_through_the_store_is_the_document_of_the_ledger_without_what_it_withheld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end over a real chain. The ledger holds entries the exporter may not read before,
    between, beside and after the ones they may, and is read one row per statement, so the store
    has to keep reading past rows it drops. What it hands over is byte for byte the document of a
    ledger where those entries were never written, and its record has a count, no range and no
    verdict. Delete this and the store can stop at a chunk of withheld rows, hand the producer raw
    rows, or record the range that counts what was withheld."""
    monkeypatch.setattr(data_export_store, "READ_CHUNK", 1)
    with through_0082("brain_data_export_readable") as url:
        write_ledger(
            url,
            ledger(*WINDOW),
        )
        expected = taken(ledger(*SEEN), PARTIAL)

        async def take(store: StoredExports) -> Any:
            return await store.take_audit_export(
                since=SINCE,
                until=UNTIL,
                limit=1000,
                form=ExportForm.READABLE,
                keep=kept_by(ExportForm.READABLE, PARTIAL, TAKEN_AT),
                actor="u_exporter",
                ent_hash="c" * 32,
                trace_id="trace1",
                reason=ExportReason.REGULATORY_REQUEST,
                reason_reference="MATTER-1",
                at=TAKEN_AT,
                produce=lambda entries: taken(tuple(entries), PARTIAL),
            )

        taken_export, produced = with_store(url, take)
        assert produced.document == expected.document
        assert sql(
            url, "SELECT form, first_seq, last_seq, entries, verified FROM ops.data_export"
        ) == [("readable", None, None, 4, None)]
        assert (taken_export.form, taken_export.first_seq, taken_export.verified) == (
            ExportForm.READABLE,
            None,
            None,
        )


def test_the_store_stops_at_one_more_readable_entry_than_the_ceiling_however_many_rows_it_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At a ceiling of two the producer is handed exactly three readable entries, read one row at a
    time through a ledger where withheld rows outnumber them, and at a ceiling of ten it is handed
    all four. Delete this and the store can count rows towards the ceiling, so a reader who may
    read two is refused for the rows around them, or read on past the ceiling without end."""
    monkeypatch.setattr(data_export_store, "READ_CHUNK", 1)
    with through_0082("brain_data_export_ceiling") as url:
        write_ledger(
            url,
            ledger(*WINDOW),
        )
        handed: list[list[str]] = []

        def produce(entries: Sequence[AuditEntry]) -> Produced:
            handed.append([one.subject for one in entries])
            return taken(tuple(entries), PARTIAL)

        def take(limit: int) -> Callable[[StoredExports], Awaitable[Any]]:
            async def go(store: StoredExports) -> Any:
                return await store.take_audit_export(
                    since=SINCE,
                    until=UNTIL,
                    limit=limit,
                    form=ExportForm.READABLE,
                    keep=kept_by(ExportForm.READABLE, PARTIAL, TAKEN_AT),
                    actor="u_exporter",
                    ent_hash="c" * 32,
                    trace_id="trace1",
                    reason=ExportReason.REGULATORY_REQUEST,
                    reason_reference="MATTER-1",
                    at=TAKEN_AT,
                    produce=produce,
                )

            return go

        with_store(url, take(2))
        with_store(url, take(10))
        assert handed == [
            ["principal:u_wei", "principal:u_ana", "principal:u_bo"],
            ["principal:u_wei", "principal:u_ana", "principal:u_bo", "principal:u_cy"],
        ]


def test_a_row_that_does_not_construct_refuses_a_chain_and_is_dropped_from_a_readable_export() -> (
    None
):
    """A chain with a row left out is not the chain, so it is refused in words; a readable export
    drops the row as the audit screen does, because a refusal would say it exists. Delete this and
    a chain silently loses an entry at the edge of its window, or a readable export tells its
    exporter about a row the view would never have shown them."""
    rows = [stored(one) for one in ledger(SEEN[0], SEEN[3])]
    rows[0].action = "invented"
    assert [one.subject for one in entries_of(rows, ExportForm.READABLE)] == ["principal:u_cy"]
    with pytest.raises(AuditExportRefusedError, match=AN_ENTRY_THAT_DOES_NOT_READ):
        entries_of(rows, ExportForm.CHAIN)
    whole = [stored(one) for one in ledger(SEEN[0], SEEN[3])]
    assert len(entries_of(whole, ExportForm.CHAIN)) == 2
