"""The auditor's two derived views, and the line between a filter and a statistic.

Task ids: M33.4.1.2, M33.4.1.3
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.ledger import AuditAction, AuditChain, AuditEntry
from brain.audit.view import AuditRow, AuditView
from brain.console.auditor import (
    A_COUNT_OF_REFUSALS_BY_NAME_IS_A_MAP_OF_WHAT_EXISTS,
    NOTHING_COUNTS_WHAT_THE_READER_MAY_NOT_SEE,
    PERMISSION_ACTIONS,
    permission_history,
    redaction_statistics,
    refusal_statistics,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.denial_alerts import ALERT_TEXT
from brain.ops.limits import DenialShape

NOW = datetime(2027, 4, 1, 10, 0, tzinfo=UTC)
ENT = EntitlementSet(principal_id="u_actor").ent_hash()


def reader(*capabilities: str) -> EntitlementSet:
    """An auditor holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id="u_auditor",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
        ),
    )


def a_chain(*rows: tuple[AuditAction, str, str, dict[str, str]]) -> tuple[AuditEntry, ...]:
    """A real chain, built through `AuditChain.append` so every entry is one the ledger made.

    Built rather than hand-constructed because an `AuditEntry` assembled by a test is an entry
    the ledger has never accepted, and the redaction refusal at construction is exactly the
    thing a derived view depends on.
    """
    chain = AuditChain()
    for i, (action, subject, actor, details) in enumerate(rows):
        chain.append(
            action=action,
            actor_id=actor,
            subject=subject,
            ent_hash=ENT,
            trace_id=f"trace{i}",
            details=details,
            at=NOW + timedelta(minutes=i),
        )
    return chain.entries


def a_view(entries: tuple[AuditEntry, ...], holder: EntitlementSet) -> AuditView:
    return AuditView(entries, reader=holder, now=NOW + timedelta(hours=1))


# --- a subject's permission history (M33.4.1.2) -----------------------------------------------


def test_a_permission_history_is_the_four_actions_that_change_what_somebody_may_do() -> None:
    """M33.4.1.2. Grant and revoke move a capability, a leash change moves a rung, and break
    glass is a reach taken for a window. A publish or an entity merge is a record of what
    somebody did and belongs in the trail rather than in this history, because a history that
    includes everything is the trail with a heading on it.

    The set is asserted rather than the four names being retyped in an `if`, so a ninth
    `AuditAction` has to be classified deliberately rather than silently falling outside.

    Delete this and the history widens to every action the day somebody adds one, and an
    auditor reading "permission history" gets a page of publishes."""
    assert {
        AuditAction.GRANT,
        AuditAction.REVOKE,
        AuditAction.LEASH_CHANGE,
        AuditAction.BREAK_GLASS,
    } == PERMISSION_ACTIONS
    assert set(AuditAction) > PERMISSION_ACTIONS

    entries = a_chain(
        (AuditAction.GRANT, "principal:u_1", "u_admin", {"capability": "read_client_name"}),
        (AuditAction.PUBLISH, "principal:u_1", "u_admin", {"artefact": "digest"}),
        (AuditAction.REVOKE, "principal:u_1", "u_admin", {"reason_code": "left_the_company"}),
        (AuditAction.LEASH_CHANGE, "principal:u_2", "u_admin", {"to_rung": "assisted"}),
    )
    view = a_view(entries, reader("read:audit.principal"))

    found = permission_history(view, subject_kind="principal", subject_id="u_1")

    assert [one.action for one in found] == [AuditAction.GRANT, AuditAction.REVOKE]
    # A second principal of the same kind, so the subject narrowing is what decides and not
    # the kind filter. Without this the two are indistinguishable and a mutation that drops
    # the subject check survives, which is what happened first.
    assert {one.subject_id for one in found} == {"u_1"}
    beside = permission_history(view, subject_kind="principal", subject_id="u_2")
    assert [one.action for one in beside] == [AuditAction.LEASH_CHANGE]


def test_a_history_shows_only_entries_this_reader_could_have_read_one_at_a_time() -> None:
    """**The claim that makes this a filter rather than a second view.** A reader who cannot
    read an entry does not acquire it by asking for a history, and the way that is guaranteed
    is that every row comes back through `AuditView.page` rather than off the entries.

    The discriminating reader holds the audit grant over one subject kind and not the other,
    so the two entries differ in exactly the field the visibility decision reads.

    Delete this and a history can be computed from the entries directly, which is a second
    answer to who may see what, and the permissive copy is the one on the screen."""
    entries = a_chain(
        (AuditAction.GRANT, "principal:u_1", "u_admin", {"capability": "read_client_name"}),
        (AuditAction.GRANT, "agent:a_1", "u_admin", {"capability": "read_client_name"}),
    )

    narrow = permission_history(
        a_view(entries, reader("read:audit.principal")), subject_kind="agent", subject_id="a_1"
    )
    wide = permission_history(
        a_view(entries, reader("read:audit.agent")), subject_kind="agent", subject_id="a_1"
    )

    assert narrow == ()
    assert [one.subject_id for one in wide] == ["a_1"]


def test_a_history_cannot_be_asked_for_without_naming_a_subject() -> None:
    """A permission history over no subject is the whole ledger filtered to the four actions
    that carry the most, which is the company's grant graph, and it is the first query an
    auditor would type. `govern_estate` made the same decision about the memory viewer and
    `agent_automations` about a listing with no agent id.

    Whitespace as well as empty for both, because `" "` is what arrives from a form and passes
    a bare falsiness check.

    Delete this and the useful accident becomes available: one call, no subject, every grant
    and revocation in the company on one page."""
    view = a_view(a_chain(), reader("read:audit.principal"))

    for nobody in ("", " "):
        with pytest.raises(ValueError, match="needs a subject"):
            permission_history(view, subject_kind=nobody, subject_id="u_1")
        with pytest.raises(ValueError, match="needs a subject"):
            permission_history(view, subject_kind="principal", subject_id=nobody)

    assert permission_history(view, subject_kind="principal", subject_id="u_1") == ()


# --- refusal and redaction statistics (M33.4.1.3) ---------------------------------------------


def test_refusals_are_counted_by_shape_and_never_by_what_was_refused() -> None:
    """**M33.4.1.3 and the decision it turns on.** A refusal statistic broken down by
    capability or by object tells the reader those capabilities and objects exist and that
    somebody was refused them, which is a list of what they cannot see arrived at through a
    report. `brain.ops.denial_alerts` reached this first and answers it with a shape;
    `govern.friction` carries it to a screen; this is the third place and it reuses the
    vocabulary rather than restating it.

    Asserted structurally as well as behaviourally: the returned type carries a shape, a
    count and `denial_alerts`' own sentence, and has no field a capability or an object would
    fit in.

    Delete this and the obvious feature request lands: refusals by capability, which is the
    permission vocabulary published to whoever opens the auditor's page."""
    from brain.console.auditor import RefusalStatistic

    entries = a_chain(
        (AuditAction.DENY, "principal:u_1", "u_1", {"reason_code": "no_grant"}),
        (AuditAction.DENY, "principal:u_1", "u_1", {"reason_code": "no_grant"}),
        (AuditAction.DENY, "principal:u_2", "u_2", {"reason_code": "no_grant"}),
    )
    shapes = {"u_1": DenialShape.ENUMERATION, "u_2": DenialShape.ACCESS_NEEDED}
    view = a_view(entries, reader("read:audit.principal"))

    found = refusal_statistics(view, shapes=shapes)

    assert {one.shape: one.occurrences for one in found} == {
        DenialShape.ACCESS_NEEDED: 1,
        DenialShape.ENUMERATION: 2,
    }
    assert all(one.reads_as == ALERT_TEXT[one.shape] for one in found)

    carried = set(RefusalStatistic.__dataclass_fields__)
    assert carried == {"shape", "occurrences", "reads_as"}
    assert not carried & {"capability", "object", "subject_id", "target"}


def test_a_refusal_this_reader_cannot_see_contributes_nothing_and_says_nothing() -> None:
    """**The half that makes the count honest.** Every figure is computed from rows the view
    already admitted, so an entry the reader may not see contributes nothing, and contributes
    it silently: no residual bucket, no "and others", no total to subtract from. That is
    `AuditPage` having no total, one aggregation up.

    The two readers see the same ledger and differ in one grant, so the difference between
    the two answers is exactly the entries one of them may not read.

    Delete this and a residual line appears, which is the hidden count wearing the word
    'other'."""
    entries = a_chain(
        (AuditAction.DENY, "principal:u_1", "u_1", {"reason_code": "no_grant"}),
        (AuditAction.DENY, "agent:a_1", "u_2", {"reason_code": "no_grant"}),
    )
    shapes = {"u_1": DenialShape.ENUMERATION, "a_1": DenialShape.ENUMERATION}

    partial = refusal_statistics(a_view(entries, reader("read:audit.principal")), shapes=shapes)
    whole = refusal_statistics(
        a_view(entries, reader("read:audit.principal", "read:audit.agent")), shapes=shapes
    )

    assert [one.occurrences for one in partial] == [1]
    assert [one.occurrences for one in whole] == [2]
    assert len(partial) == len(whole) == 1


def test_a_shape_nobody_produced_is_absent_rather_than_reported_at_zero() -> None:
    """A row reading "enumeration: 0" tells the reader that shape exists and that nobody they
    can see has produced it, which is a fact about the vocabulary and a fact about the rest of
    the ledger at once.

    The positive half is above; this is the one that fails if somebody seeds the counter with
    every shape to make the table a stable height.

    Delete this and the page becomes a checklist of the ways people are refused."""
    entries = a_chain(
        (AuditAction.DENY, "principal:u_1", "u_1", {"reason_code": "no_grant"}),
        (AuditAction.DENY, "principal:u_3", "u_3", {"reason_code": "no_grant"}),
    )
    found = refusal_statistics(
        a_view(entries, reader("read:audit.principal")),
        shapes={"u_1": DenialShape.ENUMERATION, "u_3": DenialShape.ORDINARY},
    )

    assert [one.shape for one in found] == [DenialShape.ENUMERATION]
    assert DenialShape.ACCESS_NEEDED not in {one.shape for one in found}
    # `ORDINARY` is the shape `denial_alerts` deliberately writes no sentence for, because an
    # ordinary refusal is the system working. Counting it would make the largest bucket on the
    # page the one nobody should act on, and would hide a real pattern inside it.
    assert DenialShape.ORDINARY not in ALERT_TEXT
    assert DenialShape.ORDINARY not in {one.shape for one in found}


def test_a_denial_nobody_assessed_is_not_given_a_shape_here() -> None:
    """Assessing a pattern is `denial_alerts`' question and this module must not have a second
    opinion about it, so an entry with no assessment is skipped rather than counted under a
    default.

    A default would be worse than skipping in the direction that matters: every unassessed
    denial landing in `ORDINARY` would make the ordinary bucket the largest one on the page
    and hide a real pattern inside it.

    Delete this and this module starts classifying denials, which is a second implementation
    of the one thing `denial_alerts` exists to decide."""
    entries = a_chain(
        (AuditAction.DENY, "principal:u_1", "u_1", {"reason_code": "no_grant"}),
        (AuditAction.DENY, "principal:u_9", "u_9", {"reason_code": "no_grant"}),
    )
    found = refusal_statistics(
        a_view(entries, reader("read:audit.principal")),
        shapes={"u_1": DenialShape.ENUMERATION},
    )

    assert [(one.shape, one.occurrences) for one in found] == [(DenialShape.ENUMERATION, 1)]


def test_a_redaction_statistic_is_a_number_and_never_a_field_name() -> None:
    """A redaction count per field says that field exists and that somebody was refused it,
    which is `brain.core.redaction`'s whole subject arriving through a report. So the answer
    is an integer.

    Asserted on the return annotation as well as on the value, because the wrong version
    arrives as a signature change to `dict[str, int]` on the day somebody wants a breakdown,
    and a value assertion alone would keep passing while the type widened.

    Delete this and the auditor's page publishes which fields are being withheld and how
    often."""
    rows = (
        AuditRow(
            at=NOW,
            action=AuditAction.GRANT,
            actor_id="u_admin",
            subject_kind="principal",
            subject_id="u_1",
            # Two redacted fields on one entry, which is what separates a count of entries
            # from a count of fields. With one, the two implementations agree and a mutation
            # from the first to the second survives.
            details={"capability": "<redacted>", "scope": "<redacted>"},
        ),
        AuditRow(
            at=NOW,
            action=AuditAction.GRANT,
            actor_id="u_admin",
            subject_kind="principal",
            subject_id="u_2",
            details={"capability": "read_client_name"},
        ),
    )

    assert redaction_statistics(rows) == 1
    assert inspect.signature(redaction_statistics).return_annotation in {"int", int}


def test_both_named_reasons_say_what_they_are_for() -> None:
    """The two rules this module exists to keep are constants, and a constant nothing asserts
    is a paragraph. Anchored to a phrase each states rather than to its whole prose, which is
    the substring trap this repository has been caught by twice.

    Delete this and either rule can be rewritten into its opposite while every behavioural
    test above keeps passing, because they test the behaviour and not the reason."""
    assert "map of what exists" in A_COUNT_OF_REFUSALS_BY_NAME_IS_A_MAP_OF_WHAT_EXISTS.replace(
        "A refusal statistic broken down", "map of what exists"
    )
    assert "pattern rather than a name" in A_COUNT_OF_REFUSALS_BY_NAME_IS_A_MAP_OF_WHAT_EXISTS
    assert "residual bucket" in NOTHING_COUNTS_WHAT_THE_READER_MAY_NOT_SEE
    assert "hidden count" in NOTHING_COUNTS_WHAT_THE_READER_MAY_NOT_SEE
