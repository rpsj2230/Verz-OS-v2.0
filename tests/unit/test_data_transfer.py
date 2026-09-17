"""What can be imported and exported, who may take the audit trail export, and what it produces.

No server. Ledger windows are built with `brain.audit.ledger.AuditChain`, which is the chain the
export verifies, and the visibility of every entry is `brain.audit.view.AuditView`'s. Two proofs
matter most here. That `reads_the_whole_ledger` implies the view shows every entry the ledger could
hold, because that implication is what lets the chain be chosen before anything is read. And the
byte identity of a readable export: a window holding an entry its exporter may not read renders
exactly as the same window where that entry was never written.

Every date is in 2019, far from any wall clock, because nothing here is about the present.

Task ids: M27.8.16, M27.9.4
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.export import render_export, verify_document
from brain.audit.ledger import SUBJECT_KINDS, AuditAction, AuditChain, AuditEntry
from brain.audit.readable_export import (
    READABLE_FORMAT,
    WHAT_THIS_DOCUMENT_CARRIES,
    verify_readable_document,
)
from brain.audit.reads import READ_LOG_CAPABILITY
from brain.audit.view import CAPABILITY_BY_KIND, AuditRow, AuditView
from brain.console.reads import plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.identity.first_administrator import GRANTED_AT_APPOINTMENT
from brain.ops import data_transfer
from brain.ops.data_transfer import (
    AUDIT_TRAIL_READ,
    CATALOGUE,
    EMPTY_WINDOW,
    EXPORT_AUTHORITY,
    FORM_TOLD,
    NOT_A_CHAIN,
    NOTHING_YOU_MAY_READ,
    TOO_LARGE_WINDOW,
    TOO_MANY_YOU_MAY_READ,
    AuditExportRefusedError,
    Direction,
    everything_is_visible,
    form_for,
    kept_by,
    may_export,
    may_take_audit_export,
    produce_audit_export,
    reads_the_whole_ledger,
    request_problems,
)
from brain.ops.export import ExportReason
from brain.tables.data_export import ExportDataSet, ExportForm

LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
WHOLE = Scope.unrestricted()
FINANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

#: The window every export here is taken over, and the instant it is taken at.
SINCE = LONG_AGO
UNTIL = LONG_AGO + timedelta(days=1)
TAKEN_AT = LONG_AGO + timedelta(days=2)


def reach(
    *capabilities: Capability, scope: Scope = WHOLE, pid: str = "u_exporter"
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=tuple(Grant(capability=one, scope=scope) for one in capabilities),
    )


#: Every capability the whole ledger takes to read.
LEDGER: tuple[Capability, ...] = (*CAPABILITY_BY_KIND.values(), READ_LOG_CAPABILITY)
#: What the audit trail's own screen takes to open: its read, and the plane that read is shown at.
SCREEN: tuple[Capability, ...] = (
    AUDIT_TRAIL_READ.requires,
    plane_capability(AUDIT_TRAIL_READ.plane),
)
#: A whole-ledger exporter, who takes the chain.
EXPORTER = reach(EXPORT_AUTHORITY, *SCREEN, *LEDGER)
#: An exporter who may read the audit entries about principals and nothing else.
PARTIAL = reach(EXPORT_AUTHORITY, *SCREEN, CAPABILITY_BY_KIND["principal"])


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


#: One entry as a test writes it: action, subject and the second of the window it happens in.
Written = tuple[AuditAction, str, int]


def ledger(*written: Written) -> tuple[AuditEntry, ...]:
    """These entries appended in order to a fresh chain, each at its second of the window."""
    chain = AuditChain()
    for action, subject, second in written:
        chain.append(
            action=action,
            actor_id="u_admin",
            subject=subject,
            ent_hash="a" * 32,
            trace_id="trace1",
            at=SINCE + timedelta(seconds=second),
            details={"capability": "read:client.name"},
        )
    return chain.entries


#: Readable by `PARTIAL`: principal subjects. Two share an instant, so their order is tested.
SEEN_FIRST: Written = (AuditAction.GRANT, "principal:u_wei", 10)
SEEN_TOGETHER_A: Written = (AuditAction.REVOKE, "principal:u_ana", 20)
SEEN_TOGETHER_B: Written = (AuditAction.GRANT, "principal:u_bo", 20)
SEEN_LAST: Written = (AuditAction.SIGN_IN, "principal:u_cy", 30)

#: Not readable by `PARTIAL`: another kind, and a read-log entry whose subject is a principal.
HIDDEN_AGENT: Written = (AuditAction.LEASH_CHANGE, "agent:helper", 5)
HIDDEN_READ: Written = (AuditAction.RECORD_READ, "principal:u_wei", 15)
HIDDEN_SAME_INSTANT: Written = (AuditAction.GRANT, "grant:g1", 20)
HIDDEN_AFTER: Written = (AuditAction.GRANT, "connector:lark", 40)


def taken(entries: tuple[AuditEntry, ...], reader: EntitlementSet) -> data_transfer.Produced:
    return produce_audit_export(
        entries,
        reader=reader,
        reason=ExportReason.REGULATORY_REQUEST,
        trace_id="trace1",
        at=TAKEN_AT,
        since=SINCE,
        until=UNTIL,
    )


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


def test_every_form_has_its_own_sentence_for_the_screen() -> None:
    """The listing tells a reader what their export will be. Delete this and a form added to
    `ExportForm` reaches the listing as a `KeyError`, or both forms share the chain's promise that
    the document can be checked without this system."""
    assert set(FORM_TOLD) == set(ExportForm)
    assert len(set(FORM_TOLD.values())) == len(ExportForm)


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


def test_taking_an_export_needs_the_export_capability_and_what_the_audit_trail_itself_needs() -> (
    None
):
    """`admin:export` over everything and the audit screen's read with its plane, and nothing about
    how much of the ledger the reader may see. Delete this and `and` becomes `or`, so `admin:export`
    alone copies the audit trail out, or the whole-ledger rule comes back and the first
    administrator of every install is refused again."""
    now = LONG_AGO
    assert may_take_audit_export(EXPORTER, now)
    assert may_take_audit_export(PARTIAL, now)
    assert may_take_audit_export(reach(EXPORT_AUTHORITY, *SCREEN), now)
    assert not may_take_audit_export(reach(*SCREEN, *LEDGER), now)
    assert not may_take_audit_export(reach(EXPORT_AUTHORITY), now)
    assert not may_take_audit_export(reach(EXPORT_AUTHORITY, *LEDGER), now)
    for missing in SCREEN:
        held = (one for one in SCREEN if one != missing)
        assert not may_take_audit_export(reach(EXPORT_AUTHORITY, *held, *LEDGER), now)
    assert not may_export(reach(EXPORT_AUTHORITY, scope=FINANCE), now)
    assert EXPORT_AUTHORITY.value.startswith("admin:")


def test_the_first_administrator_may_take_an_export_and_takes_the_entries_they_may_read() -> None:
    """M27.9.4 from the appointment's own list rather than from a constant here. Delete this and the
    appointment can drop the audit screen's read, or gain the whole ledger, with nothing noticing
    that the first administrator's export changed shape or vanished."""
    first = reach(*(Capability(value=one) for one in GRANTED_AT_APPOINTMENT), pid="u_first")
    assert may_take_audit_export(first, LONG_AGO)
    assert form_for(first, LONG_AGO) is ExportForm.READABLE


def test_the_form_is_the_chain_exactly_for_a_reader_of_the_whole_ledger() -> None:
    """Decided from grants: every audit kind and the read log over everything is the chain, and one
    fewer, or one held over a department, is the readable form. Delete this and a partial reader is
    handed the chain, which the view then refuses, or a whole-ledger reader loses the chain."""
    now = LONG_AGO
    assert form_for(EXPORTER, now) is ExportForm.CHAIN
    for missing in LEDGER:
        fewer = reach(EXPORT_AUTHORITY, *SCREEN, *(one for one in LEDGER if one != missing))
        assert form_for(fewer, now) is ExportForm.READABLE
    assert form_for(PARTIAL, now) is ExportForm.READABLE


def test_a_whole_ledger_reader_is_shown_every_entry_the_ledger_could_hold() -> None:
    """The implication the chain rests on: whatever `reads_the_whole_ledger` admits, `AuditView`
    shows every entry of every subject kind and the read log. If it did not, a chain would be chosen
    for somebody the view then withholds from. Delete this and a new subject kind, or a new rule in
    the view, makes the form decision promise a chain the view will not give."""
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


def test_the_store_keeps_every_entry_of_a_chain_and_only_the_readable_entries_otherwise() -> None:
    """What `StoredExports` counts towards the ceiling. Delete this and the store can keep raw rows
    for a readable export, so the ceiling counts entries the exporter may not read, or keep only
    readable rows for a chain, which leaves a gap the chain then refuses."""
    entries = ledger(HIDDEN_AGENT, SEEN_FIRST, HIDDEN_READ, SEEN_LAST)
    assert kept_by(ExportForm.CHAIN, PARTIAL, TAKEN_AT)(entries) == entries
    assert kept_by(ExportForm.READABLE, PARTIAL, TAKEN_AT)(entries) == (entries[1], entries[3])
    assert kept_by(ExportForm.READABLE, EXPORTER, TAKEN_AT)(entries) == entries


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


# ------------------------------------------------------------------ the chain


def produce(entries: tuple[AuditEntry, ...]) -> data_transfer.Produced:
    return taken(entries, EXPORTER)


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
    assert (produced.form, produced.verified) == (ExportForm.CHAIN, True)
    manifest = json.loads(produced.document.splitlines()[0])
    assert manifest["exported_by"] == "u_exporter"
    assert manifest["reason_code"] == ExportReason.REGULATORY_REQUEST.value


def test_a_whole_ledger_readers_export_is_the_chain_exactly_as_the_audit_export_renders_it() -> (
    None
):
    """Unchanged by M27.9.4, down to the byte: every entry with its sequence number and both
    digests, the window's start hash, and the recipe. Compared with `brain.audit.export` called
    directly, so a readable rendering, a reordering or a dropped field is a difference. Delete this
    and the auditor's verifiable export can quietly become the readable form."""
    entries = ledger(HIDDEN_AGENT, SEEN_FIRST, HIDDEN_READ, SEEN_TOGETHER_A, SEEN_LAST)[1:]
    produced = produce(entries)
    direct = render_export(
        AuditChain(entries, start_hash=entries[0].prev_hash),
        exported_by="u_exporter",
        trace_id="trace1",
        reason_code=ExportReason.REGULATORY_REQUEST.value,
        at=TAKEN_AT,
    )
    assert produced.document == direct
    lines = [json.loads(one) for one in produced.document.splitlines()[1:]]
    assert [one["seq"] for one in lines] == [one.seq for one in entries]
    assert [one["entry_hash"] for one in lines] == [one.entry_hash for one in entries]


def test_a_window_taken_from_the_middle_of_the_ledger_still_verifies() -> None:
    """A window starts at its first entry's parent rather than at genesis. Delete this and every
    export but the first reads as a tampered ledger."""
    entries = every_kind_of_entry()
    produced = produce(entries[3:])
    assert produced.verified is True
    assert produced.first_seq == entries[3].seq


def test_an_empty_a_broken_and_an_oversized_chain_are_refused_in_words(
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


def test_the_chain_asks_the_view_once_more_before_it_renders_anything() -> None:
    """`form_for` makes a partial reader's chain impossible to reach through `produce_audit_export`,
    so the chain's own check is driven directly. Delete this and the chain path renders every entry
    it is handed, trusting a decision taken somewhere else."""
    with pytest.raises(PermissionError):
        data_transfer._produce_chain(
            every_kind_of_entry(),
            reader=PARTIAL,
            reason=ExportReason.REGULATORY_REQUEST,
            trace_id="trace1",
            at=TAKEN_AT,
        )


# ------------------------------------------------------------ the readable form


def test_a_readable_export_of_a_window_with_entries_withheld_is_byte_identical_to_one_without() -> (
    None
):
    """The property M27.9.4 is written for. A window holding entries the exporter may not read, one
    before everything, one between, one at the same instant as two readable entries and one after,
    renders exactly as the window where none of them was written: every byte of the document, its
    digest, and every value the record keeps. Hidden entries shift every readable entry's sequence
    number and digest, which the first assertion shows, so a document carrying either differs. The
    clock and trace are fixed and the document carries no export id, so nothing differs
    legitimately. Delete this and a readable export can count what it withheld, by position or by
    digest, and a verdict or a sequence range can reach its record."""
    withheld = ledger(
        HIDDEN_AGENT,
        SEEN_FIRST,
        HIDDEN_READ,
        SEEN_TOGETHER_A,
        HIDDEN_SAME_INSTANT,
        SEEN_TOGETHER_B,
        SEEN_LAST,
        HIDDEN_AFTER,
    )
    never_written = ledger(SEEN_FIRST, SEEN_TOGETHER_A, SEEN_TOGETHER_B, SEEN_LAST)
    assert [one.entry_hash for one in withheld if one.subject == "principal:u_cy"] != [
        one.entry_hash for one in never_written if one.subject == "principal:u_cy"
    ]
    with_them = taken(withheld, PARTIAL)
    without_them = taken(never_written, PARTIAL)
    assert with_them.document == without_them.document
    assert (with_them.digest, with_them.entries, with_them.form) == (
        without_them.digest,
        without_them.entries,
        ExportForm.READABLE,
    )
    assert (with_them.first_seq, with_them.last_seq, with_them.verified) == (None, None, None)


def test_an_entry_the_exporter_may_read_is_in_the_document_as_the_audit_trail_shows_it() -> None:
    """The positive sibling of byte identity: a document of nothing would satisfy it. Every readable
    entry is a line, each line is the view's own row and nothing more, the manifest says what the
    document carries, and it verifies against itself. An entry about the exporter is present
    without any audit kind, which is the view's rule and not a copy of it. Delete this and the
    readable form can drop what it should carry, or carry a chain field beside it."""
    entries = ledger(
        HIDDEN_AGENT, SEEN_FIRST, (AuditAction.GRANT, "principal:u_exporter", 12), SEEN_LAST
    )
    produced = taken(entries, reach(EXPORT_AUTHORITY, *SCREEN))
    manifest, *lines = [json.loads(one) for one in produced.document.splitlines()]
    assert [(one["action"], one["subject_kind"], one["subject_id"]) for one in lines] == [
        ("grant", "principal", "u_exporter")
    ]
    everybody = taken(entries, PARTIAL)
    manifest, *lines = [json.loads(one) for one in everybody.document.splitlines()]
    shown = AuditView(entries, reader=PARTIAL, now=TAKEN_AT).page().rows
    assert lines == [
        {**row.model_dump(mode="json"), "at": row.at.astimezone(UTC).isoformat()} for row in shown
    ]
    assert all(set(one) == set(AuditRow.model_fields) for one in lines)
    assert manifest["format"] == READABLE_FORMAT
    assert manifest["carries"] == WHAT_THIS_DOCUMENT_CARRIES
    assert (manifest["entry_count"], everybody.entries) == (3, 3)
    assert {"first_seq", "last_seq", "start_hash", "head"}.isdisjoint(manifest)
    assert verify_readable_document(everybody.document) == (
        True,
        "manifest matches the entry block",
    )
    assert everybody.digest == hashlib.sha256(everybody.document.encode("utf-8")).hexdigest()


def test_the_rows_are_in_time_order_whatever_order_the_entries_arrive_in() -> None:
    """The document's order is the rows' own, instant first and then the row's line. Delete this
    and the order follows whatever handed the entries over, so two exports of one window differ."""
    entries = ledger(SEEN_LAST, SEEN_TOGETHER_B, SEEN_FIRST, SEEN_TOGETHER_A)
    arranged = taken(entries, PARTIAL).document
    assert taken(tuple(reversed(entries)), PARTIAL).document == arranged
    assert taken(tuple(entries[one] for one in (2, 0, 3, 1)), PARTIAL).document == arranged
    instants = [json.loads(one)["at"] for one in arranged.splitlines()[1:]]
    assert instants == sorted(instants)


def test_the_empty_refusal_does_not_move_when_an_entry_the_exporter_may_not_read_is_added() -> None:
    """A window of nothing and a window of only withheld entries are refused in one sentence, and
    one readable entry beside them is served. Delete this and a refusal saying "nothing was
    recorded" for one window and something else for the other tells the exporter what they could
    not see."""
    for window in ((), ledger(HIDDEN_AGENT), ledger(HIDDEN_AGENT, HIDDEN_READ, HIDDEN_AFTER)):
        with pytest.raises(AuditExportRefusedError) as refused:
            taken(window, PARTIAL)
        assert str(refused.value) == NOTHING_YOU_MAY_READ
    assert taken(ledger(HIDDEN_AGENT, SEEN_FIRST), PARTIAL).entries == 1


def test_the_ceiling_does_not_move_when_entries_the_exporter_may_not_read_are_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At a ceiling of two, two readable entries are served however many withheld entries surround
    them, and three are refused whether or not any are withheld. Delete this and the ceiling counts
    rows, so a reader who may read two is told the window holds more than they could see."""
    monkeypatch.setattr(data_transfer, "MAX_EXPORT_ENTRIES", 2)
    two = taken(ledger(HIDDEN_AGENT, SEEN_FIRST, HIDDEN_READ, SEEN_LAST, HIDDEN_AFTER), PARTIAL)
    assert two.entries == 2
    assert two.document == taken(ledger(SEEN_FIRST, SEEN_LAST), PARTIAL).document
    for window in (
        ledger(SEEN_FIRST, SEEN_TOGETHER_A, SEEN_LAST),
        ledger(HIDDEN_AGENT, SEEN_FIRST, SEEN_TOGETHER_A, HIDDEN_READ, SEEN_LAST),
    ):
        with pytest.raises(AuditExportRefusedError) as refused:
            taken(window, PARTIAL)
        assert str(refused.value) == TOO_MANY_YOU_MAY_READ
