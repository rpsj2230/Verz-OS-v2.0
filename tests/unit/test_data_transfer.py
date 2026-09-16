"""What can be imported and exported, who may take the audit trail export, and what it produces.

No server. Ledger windows are built with `brain.audit.ledger.AuditChain`, which is the chain the
export verifies, and the visibility of every entry is `brain.audit.view.AuditView`'s. The one test
that matters most here is the proof that `reads_the_whole_ledger` implies the view shows every
entry the ledger could hold, because that implication is what lets the route ask before it reads.

Task ids: M27.8.16
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.export import verify_document
from brain.audit.ledger import SUBJECT_KINDS, AuditAction, AuditChain, AuditEntry
from brain.audit.reads import READ_LOG_CAPABILITY
from brain.audit.view import CAPABILITY_BY_KIND
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.ops import data_transfer
from brain.ops.data_transfer import (
    CATALOGUE,
    EMPTY_WINDOW,
    EXPORT_AUTHORITY,
    NOT_A_CHAIN,
    TOO_LARGE_WINDOW,
    AuditExportRefusedError,
    Direction,
    everything_is_visible,
    may_export,
    may_take_audit_export,
    produce_audit_export,
    reads_the_whole_ledger,
    request_problems,
)
from brain.ops.export import ExportReason
from brain.tables.data_export import ExportDataSet

LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
WHOLE = Scope.unrestricted()
FINANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))


def reach(
    *capabilities: Capability, scope: Scope = WHOLE, pid: str = "u_exporter"
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=tuple(Grant(capability=one, scope=scope) for one in capabilities),
    )


#: Every capability the whole ledger takes to read, and the export's own.
LEDGER: tuple[Capability, ...] = (*CAPABILITY_BY_KIND.values(), READ_LOG_CAPABILITY)
EXPORTER = reach(EXPORT_AUTHORITY, *LEDGER)


def every_kind_of_entry(start: int = 0) -> tuple[AuditEntry, ...]:
    """One entry per subject kind and one read-log entry, none of them about the exporter."""
    chain = AuditChain()
    moment = LONG_AGO + timedelta(minutes=start)
    for index, kind in enumerate(sorted(SUBJECT_KINDS)):
        chain.append(
            action=AuditAction.GRANT,
            actor_id="u_someone",
            subject=f"{kind}:thing{index}",
            ent_hash="0" * 32,
            trace_id="trace1",
            at=moment + timedelta(seconds=index),
        )
    chain.append(
        action=AuditAction.RECORD_READ,
        actor_id="u_someone",
        subject="principal:u_other",
        ent_hash="0" * 32,
        trace_id="trace1",
        at=moment + timedelta(minutes=1),
    )
    return chain.entries


# ------------------------------------------------------------------- the catalogue


def test_the_data_sets_that_run_are_exactly_the_ones_an_export_row_can_record() -> None:
    """A data set offered as runnable with no member in `ExportDataSet` is a button whose record the
    table refuses, and a member with no runnable entry is a constraint nothing uses. Delete this and
    the catalogue and the table drift apart, found on the first export."""
    runs = {one.key for one in CATALOGUE if one.runs}
    assert runs == {one.value for one in ExportDataSet}
    assert all(one.direction is Direction.EXPORT for one in CATALOGUE if one.runs)


def test_every_data_set_that_cannot_run_says_why_and_imports_are_listed_too() -> None:
    """The owner's standard: where the mechanism is missing, the screen says so in words. Delete
    this and a row with an empty sentence reads as an option somebody forgot to enable."""
    assert {one.direction for one in CATALOGUE} == set(Direction)
    assert len({one.key for one in CATALOGUE}) == len(CATALOGUE)
    for one in CATALOGUE:
        assert one.told.strip() and one.carries.strip() and one.label.strip()


# ------------------------------------------------------------------ who may export


def test_the_whole_ledger_reach_is_every_audit_kind_and_the_read_log_each_over_everything() -> None:
    """Missing any one capability, or holding one over a department, is not the whole ledger. The
    positive sibling is the full set. Delete this and the read log's own noun is dropped from the
    check, which `brain.audit.reads` says no audit wildcard reaches."""
    now = LONG_AGO
    assert reads_the_whole_ledger(reach(*LEDGER), now)
    for missing in LEDGER:
        assert not reads_the_whole_ledger(reach(*(one for one in LEDGER if one != missing)), now)
    narrow = EntitlementSet(
        principal_id="u_exporter",
        grants=(
            *(Grant(capability=one, scope=WHOLE) for one in LEDGER[1:]),
            Grant(capability=LEDGER[0], scope=FINANCE),
        ),
    )
    assert not reads_the_whole_ledger(narrow, now)


def test_taking_an_export_needs_both_the_export_capability_and_the_whole_ledger() -> None:
    """Either alone is refused. Delete this and `and` becomes `or`, and an administrator holding
    `admin:export` and nothing else copies the audit trail out."""
    now = LONG_AGO
    assert may_take_audit_export(EXPORTER, now)
    assert not may_take_audit_export(reach(*LEDGER), now)
    assert not may_take_audit_export(reach(EXPORT_AUTHORITY), now)
    assert not may_export(reach(EXPORT_AUTHORITY, scope=FINANCE), now)
    assert EXPORT_AUTHORITY.value.startswith("admin:")


def test_a_whole_ledger_reader_is_shown_every_entry_the_ledger_could_hold() -> None:
    """The implication the route rests on: whatever `reads_the_whole_ledger` admits, `AuditView`
    shows every entry of every subject kind and the read log. If it did not, a refusal after
    loading would say what a window held. Delete this and a new subject kind, or a new rule in the
    view, makes the pre-check admit a reader the view then withholds from."""
    entries = every_kind_of_entry()
    assert {one.subject.partition(":")[0] for one in entries} == set(SUBJECT_KINDS)
    assert everything_is_visible(entries, reach(*LEDGER), LONG_AGO)


def test_a_reader_missing_one_kind_is_not_shown_everything() -> None:
    """The negative of the above, so `everything_is_visible` cannot answer true for everybody.
    Delete this and the view's decision is asked and ignored."""
    entries = every_kind_of_entry()
    without_agents = reach(*(one for one in LEDGER if one != CAPABILITY_BY_KIND["agent"]))
    assert not everything_is_visible(entries, without_agents, LONG_AGO)
    without_reads = reach(*(one for one in LEDGER if one != READ_LOG_CAPABILITY))
    assert not everything_is_visible(entries, without_reads, LONG_AGO)


def test_everything_visible_counts_across_more_than_one_page_of_the_view() -> None:
    """A window longer than a page is walked to its end. Delete this and a check that reads one page
    answers false for every real export."""
    chain = AuditChain()
    for index in range(250):
        chain.append(
            action=AuditAction.GRANT,
            actor_id="u_someone",
            subject=f"principal:p{index}",
            ent_hash="0" * 32,
            trace_id="trace1",
            at=LONG_AGO + timedelta(seconds=index),
        )
    assert everything_is_visible(chain.entries, reach(*LEDGER), LONG_AGO)


# ------------------------------------------------------------------ the request


def test_a_request_wrong_in_every_field_is_told_every_problem() -> None:
    """Delete this and the reference, the one field a name could be written into, is judged only
    when nothing else is wrong."""
    found = request_problems(
        data_set="knowledge",
        reason="because",
        reason_reference="Wei Ling Tan",
        since=LONG_AGO,
        until=LONG_AGO,
    )
    assert [(one.field.value, one.code) for one in found] == [
        ("data_set", "not_available"),
        ("reason", "unknown"),
        ("reason_reference", "not_a_reference"),
        ("window", "backwards"),
    ]
    naive = request_problems(
        data_set="audit_trail",
        reason="legal_discovery",
        reason_reference="REQ-1",
        since=LONG_AGO.replace(tzinfo=None),
        until=LONG_AGO,
    )
    assert [(one.field.value, one.code) for one in naive] == [("window", "no_timezone")]


def test_a_well_formed_request_has_no_problems() -> None:
    """The sibling every refusal above needs."""
    assert (
        request_problems(
            data_set=ExportDataSet.AUDIT_TRAIL.value,
            reason=ExportReason.REGULATORY_REQUEST.value,
            reason_reference="MATTER-2019/004#2",
            since=LONG_AGO,
            until=LONG_AGO + timedelta(days=1),
        )
        == ()
    )


# ------------------------------------------------------------------ the document


def produce(entries: tuple[AuditEntry, ...]) -> data_transfer.Produced:
    return produce_audit_export(
        entries,
        reader=EXPORTER,
        reason=ExportReason.REGULATORY_REQUEST,
        trace_id="trace1",
        at=LONG_AGO + timedelta(days=1),
    )


def test_a_window_is_rendered_verified_and_described_by_what_a_recipient_can_check() -> None:
    """The document verifies against its own manifest, its digest is the sha256 of exactly those
    bytes, and the window is the entries' own sequence numbers. Delete this and a record can carry a
    digest of something other than the file handed over."""
    entries = every_kind_of_entry()
    produced = produce(entries)
    assert verify_document(produced.document) == (True, "manifest matches the entry block")
    assert produced.digest == hashlib.sha256(produced.document.encode("utf-8")).hexdigest()
    assert (produced.first_seq, produced.last_seq, produced.entries) == (
        entries[0].seq,
        entries[-1].seq,
        len(entries),
    )
    assert produced.verified is True
    manifest = json.loads(produced.document.splitlines()[0])
    assert manifest["exported_by"] == "u_exporter"
    assert manifest["reason_code"] == ExportReason.REGULATORY_REQUEST.value


def test_a_window_taken_from_the_middle_of_the_ledger_still_verifies() -> None:
    """A window starts at its first entry's parent rather than at genesis. Delete this and every
    export but the first reads as a tampered ledger."""
    entries = every_kind_of_entry()
    produced = produce(entries[3:])
    assert produced.verified is True
    assert produced.first_seq == entries[3].seq


def test_an_empty_a_broken_and_an_oversized_window_are_refused_in_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each with the sentence a person acts on. Delete this and an empty window produces a document
    of nothing, recorded in the ledger as an export."""
    entries = every_kind_of_entry()
    with pytest.raises(AuditExportRefusedError, match=EMPTY_WINDOW):
        produce(())
    with pytest.raises(AuditExportRefusedError, match="do not follow"):
        produce((entries[0], entries[2]))
    assert "do not follow" in NOT_A_CHAIN
    monkeypatch.setattr(data_transfer, "MAX_EXPORT_ENTRIES", 2)
    with pytest.raises(AuditExportRefusedError) as large:
        produce(entries[:3])
    assert str(large.value) == TOO_LARGE_WINDOW
    assert produce(entries[:2]).entries == 2


def test_entries_the_view_would_not_show_the_reader_are_never_rendered() -> None:
    """The route asks first and this is the view deciding once more. Delete this and a caller that
    forgot the pre-check renders entries the reader may not see."""
    entries = every_kind_of_entry()
    with pytest.raises(PermissionError):
        produce_audit_export(
            entries,
            reader=reach(EXPORT_AUTHORITY),
            reason=ExportReason.REGULATORY_REQUEST,
            trace_id="trace1",
            at=LONG_AGO,
        )
