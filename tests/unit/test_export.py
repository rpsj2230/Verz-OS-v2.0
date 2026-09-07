"""Export, held to the three things that leave a guard behind.

An export is the one act in this system that produces something read outside it. Everything
else is decided per question and re-decided on the next one; an export is a file, and the
file has no gate in front of it. So each test below is one way the file could carry
something the answer that produced it would not have.

The turns are real `brain.chat.turns.Turn` objects with real `RecordRef` and `LockedField`
values on them, not stubs, because the property being asserted is that two specific members
of that class do not survive the export, and a stub written here would have whatever members
this file gave it. The knowledge items are real `KnowledgeItem` objects for the same reason:
the scope compared is `brain.core.scope.Scope`, built by the knowledge layer.

Task ids: M25.3.1, M25.3.2, M25.3.3
"""

from __future__ import annotations

import inspect
from dataclasses import MISSING, dataclass, fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.chat.turns import RecordRef, Turn, TurnKind
from brain.core.entitlement import Capability
from brain.core.redaction import LockedField
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.ops.export import (
    BulkExport,
    BulkExportRequest,
    ConversationExport,
    ExportAudit,
    ExportedKnowledge,
    ExportedTurn,
    ExportError,
    ExportReason,
    bulk_export,
    conversation_export,
    export_gaps,
    knowledge_export,
    withheld_names_on,
)
from brain.ops.retention import Store

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)


def _turn(text: str, *, minutes: int = 0, locked: bool = False, refs: bool = False) -> Turn:
    """A real turn, optionally carrying the two members an export must not pass on."""
    return Turn(
        kind=TurnKind.QUESTION,
        at=NOW + timedelta(minutes=minutes),
        principal_id="p_ada",
        text=text,
        refs=(
            (
                RecordRef(
                    entity="client",
                    record_id="c_snm",
                    required=Capability(value="read:client"),
                ),
            )
            if refs
            else ()
        ),
        locked=(
            (LockedField(entity="client", record_id="c_snm", field="contract_value"),)
            if locked
            else ()
        ),
    )


def _item(level: Visibility, *, item_id: str = "k_1") -> KnowledgeItem:
    """A real knowledge item at one of the three visibility levels."""
    visibility = {
        Visibility.PERSONAL: KnowledgeVisibility.personal("p_ada"),
        Visibility.DEPARTMENT: KnowledgeVisibility.of_department("finance", owner_id="p_ada"),
        Visibility.COMPANY: KnowledgeVisibility.company(owner_id="p_ada"),
    }[level]
    return KnowledgeItem(
        item_id=item_id,
        content="the renewal process runs quarterly",
        title="Renewals",
        visibility=visibility,
        owner_id="p_ada",
        state=KnowledgeState.DRAFT,
    )


# ------------------------------------------------ M25.3.1  conversation export per user
def test_a_conversation_export_carries_the_text_in_the_order_it_was_said() -> None:
    """The positive case, and without it every assertion below is satisfied by a function
    that exports nothing.

    Order is asserted as well as content: a transcript whose turns were re-sorted by an
    export is no longer a record of what was said, which is the only reason to keep one.

    Delete this and `conversation_export` can be reduced to returning an empty tuple with
    every privacy assertion in this file still green."""
    export = conversation_export(
        subject_id="p_ada",
        conversation_id="conv_1",
        at=NOW,
        turns=[_turn("first"), _turn("second", minutes=1), _turn("third", minutes=2)],
    )

    assert [one.text for one in export.turns] == ["first", "second", "third"]
    assert [one.at for one in export.turns] == sorted(one.at for one in export.turns)
    assert export.turns[0].principal_id == "p_ada"
    assert export.turns[0].kind is TurnKind.QUESTION


def test_a_conversation_export_drops_a_record_reference_because_it_is_never_re_checked() -> None:
    """`RecordRef` exists so that a reference cannot outlive the grant that justified it: it
    is re-checked on every later turn and yields nothing once the grant is gone.

    An export is the artefact that is never checked again. Carrying the references into one
    turns a structure designed to expire into a permanent list of which records an answer
    touched, readable by whoever ends up with the file.

    Asserted on the record id as well as on the field name, because a mapping that flattened
    the refs into a string would satisfy a field-name check and still carry `c_snm`.

    Delete this and refs are added back for a console feature, and the export becomes a
    durable copy of a permission decision made once."""
    source = _turn("what is the contract value", refs=True)
    assert source.refs, "the fixture must actually carry a reference"

    export = conversation_export(
        subject_id="p_ada", conversation_id="conv_1", at=NOW, turns=[source]
    )

    assert "refs" not in {f.name for f in fields(ExportedTurn)}
    rendered = repr(export)
    assert "c_snm" not in rendered
    assert "read:client" not in rendered


def test_a_conversation_export_cannot_say_how_much_was_withheld() -> None:
    """**The architecture's hardest rule, at the place it leaks most easily.**

    `Turn.locked` is the fields withheld from records a turn showed, and `ShownAnswer` has a
    `lock_count`. Either of those in an export tells the reader there are things they were
    not shown, which is the DENIED and ABSENT distinction handed over in writing.

    Both halves are checked: the model has no attribute to hold a count, and a turn that
    actually carries a lock exports with no trace of it.

    Delete this and `locked` is carried through for a viewer that renders the padlock icons,
    and the export starts counting refusals out loud."""
    source = _turn("what is the contract value", locked=True)
    assert source.locked, "the fixture must actually carry a lock"

    export = conversation_export(
        subject_id="p_ada", conversation_id="conv_1", at=NOW, turns=[source]
    )

    names = {f.name for f in fields(ExportedTurn)} | {f.name for f in fields(ConversationExport)}
    for forbidden in ("locked", "lock_count", "redacted", "withheld", "hidden", "omitted"):
        assert forbidden not in names, f"an export can carry {forbidden}"
    assert "contract_value" not in repr(export)
    assert export_gaps() == ()


def test_a_conversation_export_carries_no_ordinal_that_would_count_the_gaps() -> None:
    """The version of the rule above that gets past review.

    Nobody ships a lock count. An ordinal looks like metadata: turns numbered 1, 2, 5 and 6
    have told the reader that two things sit between the second and the third, which is the
    same disclosure arrived at by subtraction.

    Delete this and `ordinal: int` is added so a viewer can deep-link to a message, and the
    export starts counting the missing ones."""
    names = {f.name for f in fields(ExportedTurn)}

    assert names == {"kind", "at", "principal_id", "text"}
    for forbidden in ("ordinal", "sequence", "position", "turn_number", "message_index", "id"):
        assert forbidden not in names, f"an exported turn carries {forbidden}"


def test_the_withheld_scan_reports_a_model_that_grew_a_lock_count() -> None:
    """The negative sibling of the two rules above, run against a fabricated model.

    `withheld_names_on` is split out of `export_gaps` so it can be pointed at something other
    than the models it guards: a scan only ever run against code known to be clean has never
    produced a finding, and nobody knows whether it can.

    Delete this and the whole withheld-name check is a function that has only ever returned
    an empty tuple."""

    @dataclass(frozen=True)
    class Chatty:
        text: str
        lock_count: int
        refs: tuple[str, ...]

    assert withheld_names_on(Chatty) == ("lock_count", "refs")
    assert withheld_names_on(ExportedTurn) == ()

    findings = export_gaps(models=[Chatty])
    assert any("carries lock_count" in one for one in findings)
    assert any("carries refs" in one for one in findings)


def test_a_conversation_export_belonging_to_nobody_is_refused() -> None:
    """An export with no subject and no conversation is a file nobody can file, and it is
    also a file nobody can find again when the person asks what was sent to them.

    Delete this and an assembly bug produces anonymous transcripts."""
    with pytest.raises(ExportError, match="belongs to nobody"):
        ConversationExport(subject_id="", conversation_id="conv_1", at=NOW, turns=())

    kept = ConversationExport(subject_id="p_ada", conversation_id="conv_1", at=NOW, turns=())
    assert kept.turns == ()


def test_conversation_export_has_no_parameter_for_the_turns_it_may_not_show() -> None:
    """The structural half of "it cannot report what it was never given".

    A function that receives the withheld turns can be made to count them, by accident or by
    a well-meaning change. This one receives only what the caller may see.

    Delete this and `hidden: Sequence[Turn] = ()` is added for a "some messages omitted"
    banner, which is the banner the whole rule exists to prevent."""
    taken = set(inspect.signature(conversation_export).parameters)

    assert taken == {"subject_id", "conversation_id", "at", "turns"}


# ------------------------------------------------------ M25.3.2  bulk export for eDiscovery
def test_a_bulk_export_cannot_be_requested_without_a_reason_and_a_reference() -> None:
    """**The reason is structural, not validated.**

    Validation catches an empty string and does nothing about the call that never had a
    reason argument at all. A frozen request with no default for either field means there is
    no shape of this call that omits one, so the check happens at construction and the type
    checker sees it too.

    Delete this and `reason: str = ""` appears for the benefit of an internal caller, and
    the eDiscovery export becomes something anybody can take silently."""
    required = {
        f.name
        for f in fields(BulkExportRequest)
        if f.default is MISSING and f.default_factory is MISSING
    }

    assert {"reason", "reason_reference"} <= required
    with pytest.raises(TypeError):
        BulkExportRequest(  # type: ignore[call-arg]
            requested_by="p_ops", stores=frozenset({Store.CONVERSATION})
        )
    with pytest.raises(ExportError, match="written authorisation"):
        BulkExportRequest(
            requested_by="p_ops",
            reason=ExportReason.LEGAL_DISCOVERY,
            reason_reference="   ",
            stores=frozenset({Store.CONVERSATION}),
            subjects=frozenset({"p_ada"}),
        )


def test_a_bulk_export_naming_no_subject_means_everybody_by_accident_and_is_refused() -> None:
    """The same failure `brain.audit.ledger.LegalHold` refuses in its own constructor: the
    other reading of "nothing named" is "everything", and it is the largest possible version
    of this mistake.

    The positive sibling proves `all_subjects` still works, so this is a check on the
    ambiguity rather than a constructor that refuses breadth.

    Delete this and an export request with an empty subject set collects the whole company
    and nothing about the request says it meant to."""
    with pytest.raises(ExportError, match="everybody by accident"):
        BulkExportRequest(
            requested_by="p_ops",
            reason=ExportReason.LEGAL_DISCOVERY,
            reason_reference="matter-77",
            stores=frozenset({Store.CONVERSATION}),
        )

    wide = BulkExportRequest(
        requested_by="p_ops",
        reason=ExportReason.LEGAL_DISCOVERY,
        reason_reference="matter-77",
        stores=frozenset({Store.CONVERSATION}),
        all_subjects=True,
    )
    assert wide.all_subjects


def test_a_bulk_export_cannot_both_cover_everybody_and_name_a_shortlist() -> None:
    """Two scopes on one request, and the shortlist is the one a reader believes.

    Delete this and a request carrying both is collected against whichever field the
    executor happened to read."""
    with pytest.raises(ExportError, match="shortlist"):
        BulkExportRequest(
            requested_by="p_ops",
            reason=ExportReason.REGULATORY_REQUEST,
            reason_reference="matter-77",
            stores=frozenset({Store.CONVERSATION}),
            subjects=frozenset({"p_ada"}),
            all_subjects=True,
        )


def test_a_bulk_export_returns_its_audit_row_and_there_is_no_way_to_take_one_without() -> None:
    """**An export is the widest permission act in the system and the row is not optional.**

    Written as a separate call the row is a line somebody forgets, wraps in a condition, or
    disables in the environment the nightly job runs in. As a required member of the returned
    object there is no path that produces one and not the other.

    Both halves are asserted: the row comes back populated, and there is no parameter on the
    function that could turn it off.

    Delete this and `audit: ExportAudit | None = None` is a one-line change that makes every
    other test here pass."""
    request = BulkExportRequest(
        requested_by="p_ops",
        reason=ExportReason.LEGAL_DISCOVERY,
        reason_reference="matter-77",
        stores=frozenset({Store.CONVERSATION, Store.MEMORY}),
        subjects=frozenset({"p_ada", "p_ben"}),
    )

    taken = bulk_export(
        request=request,
        export_id="exp_1",
        at=NOW,
        counts={Store.CONVERSATION: 40, Store.MEMORY: 2},
    )

    audit_field = next(f for f in fields(BulkExport) if f.name == "audit")
    assert "None" not in str(audit_field.type)
    for forbidden in ("audit", "skip_audit", "no_audit", "quiet", "silent", "dry_run"):
        assert forbidden not in inspect.signature(bulk_export).parameters

    assert isinstance(taken.audit, ExportAudit)
    assert taken.audit.items == 42
    assert taken.items == 42
    assert taken.audit.subjects == ("p_ada", "p_ben")


def test_the_audit_row_names_the_reason_and_the_reference_and_no_content() -> None:
    """The row has to answer "why was this taken and on whose authority" a year later.

    The reason is a closed picklist for the same reason `LawfulBasis` is: a free-text reason
    on an export record is where the name of the person being investigated ends up. The
    reference points at the written authorisation and is never the authorisation itself.

    Delete this and the row degrades into a timestamp and a count, which answers nothing."""
    request = BulkExportRequest(
        requested_by="p_ops",
        reason=ExportReason.INTERNAL_INVESTIGATION,
        reason_reference="hr-2026-014",
        stores=frozenset({Store.CONVERSATION}),
        subjects=frozenset({"p_ada"}),
    )

    line = bulk_export(
        request=request, export_id="exp_1", at=NOW, counts={Store.CONVERSATION: 3}
    ).audit.line()

    assert "internal_investigation" in line
    assert "hr-2026-014" in line
    assert "p_ops" in line
    assert "conversation" in line


def test_a_bulk_export_refuses_a_count_from_a_store_it_does_not_cover() -> None:
    """The manifest and the collection have to be the same document, because the manifest is
    what somebody later checks the collection against.

    Dropping the stray count silently would produce an export whose manifest is quietly
    smaller than what was actually taken, which is the shape of an over-collection nobody
    can see.

    Delete this and a request scoped to conversations comes back holding memories, and the
    manifest says it did not."""
    request = BulkExportRequest(
        requested_by="p_ops",
        reason=ExportReason.LEGAL_DISCOVERY,
        reason_reference="matter-77",
        stores=frozenset({Store.CONVERSATION}),
        subjects=frozenset({"p_ada"}),
    )

    with pytest.raises(ExportError, match="does not cover"):
        bulk_export(
            request=request,
            export_id="exp_1",
            at=NOW,
            counts={Store.CONVERSATION: 3, Store.MEMORY: 1},
        )

    kept = bulk_export(request=request, export_id="exp_1", at=NOW, counts={Store.CONVERSATION: 3})
    assert [one.store for one in kept.manifest] == [Store.CONVERSATION]


def test_a_bulk_export_with_no_id_is_refused() -> None:
    """A row nobody can cite records nothing, and the id is what a later question about the
    export is asked with.

    Delete this and two exports taken the same afternoon are indistinguishable in the log."""
    request = BulkExportRequest(
        requested_by="p_ops",
        reason=ExportReason.LEGAL_DISCOVERY,
        reason_reference="matter-77",
        stores=frozenset({Store.MEMORY}),
        subjects=frozenset({"p_ada"}),
    )

    with pytest.raises(ExportError, match="needs an id"):
        bulk_export(request=request, export_id="", at=NOW, counts={})


# ------------------------------------------------------------- M25.3.3  knowledge export
def test_a_knowledge_export_carries_the_same_scope_predicate_the_item_had() -> None:
    """**An export that flattens scope is a permission laundering machine.**

    Data leaves scoped to one department and comes back, or is quoted, as an unscoped
    document. Nothing was granted and nothing was revoked; the restriction was left behind in
    a format with nowhere to put it.

    The comparison is on `brain.core.scope.Scope`, which the knowledge layer builds, rather
    than on the visibility level alone: a department scope and a personal scope with the same
    level and different owners are different predicates, and only the predicate decides who
    reaches the item.

    All three levels are checked, because the failure would be introduced by a mapping that
    is right for the common case and wrong for one of the others.

    Delete this and `visibility=KnowledgeVisibility.company()` in the mapping function makes
    every departmental item company-wide on its way out."""
    items = [
        _item(Visibility.PERSONAL, item_id="k_1"),
        _item(Visibility.DEPARTMENT, item_id="k_2"),
        _item(Visibility.COMPANY, item_id="k_3"),
    ]

    exported = knowledge_export(items)

    assert len(exported) == 3
    for source, out in zip(items, exported, strict=True):
        assert out.visibility == source.visibility
        assert out.scope == source.scope
        assert out.item_id == source.item_id
        assert out.content == source.content


def test_an_exported_knowledge_item_cannot_be_built_without_a_visibility() -> None:
    """The structural half. The scope travels with the item or the item does not travel, and
    that is enforced by there being no shape of the model without one.

    Delete this and a default of company visibility is added so a test fixture is shorter,
    and every item built that way leaves the system unscoped."""
    names = {f.name for f in fields(ExportedKnowledge)}

    assert "visibility" in names
    with pytest.raises(TypeError):
        ExportedKnowledge(  # type: ignore[call-arg]
            item_id="k_1",
            title="Renewals",
            content="body",
            owner_id="p_ada",
            state=KnowledgeState.DRAFT,
        )


def test_a_knowledge_export_of_nothing_is_empty_rather_than_an_error() -> None:
    """The positive sibling for the empty case, which is a real case: a caller whose scope
    matched no items should get an empty export rather than a refusal that reads as a fault.

    Delete this and an export for somebody with no knowledge raises, and whoever is watching
    reads it as the export being broken."""
    assert knowledge_export([]) == ()


def test_the_export_module_reports_no_gaps_of_its_own() -> None:
    """The positive case for `export_gaps`, and the sibling of the fabricated-model negative
    above.

    A gap check tested only by being made to fail is satisfied by a function that reports
    everything, which is as useless as one that reports nothing.

    Delete this and `export_gaps` can be made to return a finding unconditionally with every
    negative test in this file still passing."""
    assert export_gaps() == ()
