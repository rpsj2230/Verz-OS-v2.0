"""Six governance listings held to what each may show, and to what it must never show.

Every test hands over real records and real grants and asks what comes back. Nothing here
appoints anybody to a role, because no function in the module can read an appointment.

Six leaves are claimed and each is a disclosure decision rather than a page. A scope row is
shown whole or is absent, because blanking the predicate leaves the slug and the slug is the
predicate in words, and a department filter offers only the names the reader's own scope
admits (M27.3.2). A staff source sits nowhere, so a department-scoped grant reaches none of
them, and the row carries what the source may assert and never how many people it returned
(M27.3.5). Three different things wait on a human and each is filtered by its own authority,
and a kind the reader may decide none of has no heading (M27.3.7). Holding what an export
contained does not show that it happened, holding the Exports screen's grant does, and a
person named in an export reads that row (M27.3.9). An erasure request reaches its subject and
a scoped admin, a retention report is handed whole or withheld because there is nothing on it
to narrow, and nothing implements the eraser that would drain the queue (M27.3.10). The audit
filter has no list of actors and cannot grow one, its subject kinds are the reader's own reach
and its actions are the whole vocabulary (M27.3.18).

Real `EntitlementSet`s, a real `ScopeRecord`, a real `Roster`, a real `SuspendedAction` built
through the real `Action` and its real digest, a real `SubjectGrant`, a real
`PromotionProposal`, a real `ExportAudit` and a real `RetentionReport` built by
`enforcement_report`. A fixture that built its own shape would be a fixture the guard under
test cannot reach, which is the defect that has produced almost every surviving mutation here.

Task ids: M27.3.2, M27.3.5, M27.3.7, M27.3.9
Task ids: M27.3.10, M27.3.18
"""

from __future__ import annotations

import re
from dataclasses import fields, make_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.audit.ledger import SUBJECT_KINDS, AuditAction
from brain.audit.view import CAPABILITY_BY_KIND
from brain.console import govern_surfaces as surfaces_module
from brain.console.govern import NOWHERE, Placed
from brain.console.govern_surfaces import (
    AUDIT_SCREEN,
    EXPORT_LOG_SCREEN,
    NAMES_THAT_WOULD_BE_AN_ACTOR_LIST,
    NAMES_THAT_WOULD_BE_THE_ROSTER,
    RETENTION_SCREEN,
    SCOPES_SCREEN,
    SURFACE_COUNT,
    SURFACE_SCREENS,
    ApprovalSection,
    AuditFilterOptions,
    DeletionRow,
    GovernSurfaceError,
    StaffSourceRow,
    Waiting,
    approval_sections,
    audit_filter_options,
    audit_grant_gaps,
    audit_kinds,
    deletion_rows,
    departments_offered,
    drain_gaps,
    erasure_request,
    export_log,
    may_approve_promotion,
    retention_view,
    scope_rows,
    source_warnings,
    staff_source_rows,
    surface_gaps,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS, screen
from brain.core.department import ScopeRecord, department_scope
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import Action, ApprovalState, SuspendedAction, render_artefact
from brain.identity.packs import SubjectGrant
from brain.identity.staff_source import Asserts, Roster, StaffRecord
from brain.identity.teams import principal_subject
from brain.knowledge.visibility import PROMOTION_CAPABILITY, PromotionProposal, Visibility
from brain.ops.erasure import deletion_order
from brain.ops.export import ExportAudit, ExportReason
from brain.ops.retention import Store, StoreCensus, enforcement_report

#: A fixed moment, so an expiry test cannot pass because the machine's clock happened to sit
#: on the convenient side of a boundary. Everything below is built relative to it.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

#: Two departments, so a scoped reader has somewhere to be refused.
MAINTENANCE = "maintenance"
FINANCE = "finance"

#: The `Task ids:` lines of the module under test, read rather than restated. See the count
#: test at the end of the file.
TASK_LINE_RE = re.compile(r"^\s*Task ids:\s*(.+)$", re.M)
TASK_ID_RE = re.compile(r"\bM\d+(?:\.\d+){2,4}\b")


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
    scope: Scope | None = None,
    principal_id: str = "u_reader",
) -> EntitlementSet:
    """A reader holding these capabilities in one scope, plus the plane grants named.

    Built here rather than taken from a fixture so a test can hold one capability at one scope
    and another at a different one, which is what most of the narrowing tests below vary.
    """
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def holding_at(
    pairs: tuple[tuple[str, Scope], ...],
    *,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
    principal_id: str = "u_reader",
) -> EntitlementSet:
    """A reader holding each capability at its own scope.

    The fixture the narrowing arguments actually need: an admin whose authority is company-wide
    and whose capability over the rows is one department, or the reverse. A single-scope
    builder cannot express either, and a guard that separates the two is unreachable without it.
    """
    grants = [Grant(capability=Capability(value=one), scope=where) for one, where in pairs]
    grants += [Grant(capability=plane_capability(one), scope=Scope(clauses=())) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def scope_capability() -> str:
    """The Scopes screen's own requirement, read off the registry rather than spelled here.

    Spelled once in `test_the_pinned_screen_keys_name_the_screens_this_module_reads` and read
    from the registry everywhere else, so repointing `SCOPES_SCREEN` fails one test with a
    readable message instead of quietly changing what every narrowing test is about.
    """
    return screen(SCOPES_SCREEN).read.requires.value


def audit_capability() -> str:
    """The Activity screen's own requirement, on the same terms."""
    return screen(AUDIT_SCREEN).read.requires.value


def in_department(name: str) -> Scope:
    """A scope naming one department, which the rows below either match or do not."""
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=name),))


def a_scope_record(slug: str, department: str) -> ScopeRecord:
    """One real scope record, through `ScopeRecord`'s own validators."""
    return ScopeRecord(
        slug=slug,
        scope=department_scope(department),
        is_department=True,
        label=f"Everything belonging to {department}",
    )


def a_roster(source: str, *, complete: bool, asserts: frozenset[Asserts]) -> Roster:
    """One real roster, with people on it, so a row that leaked a count could leak one."""
    return Roster(
        source=source,
        people=(
            StaffRecord(
                work_address="one@example.invalid",
                display_name="One Person",
                department=MAINTENANCE,
            ),
            StaffRecord(
                work_address="two@example.invalid",
                display_name="Two Person",
                department=FINANCE,
            ),
        ),
        complete=complete,
        asserts=asserts,
    )


def a_suspension(ident: str, capability: str, *, department: str) -> SuspendedAction:
    """One real suspension, built through the real `Action` and its real digest.

    Produced the way `brain.gate.leash.suspend` produces one rather than stubbed, so a test
    cannot be satisfied by a `SuspendedAction` the gate would never have written.
    """
    action = Action(
        agent_id="agent_test",
        tool=ToolDefinition(
            name="ticket.update_status",
            description="a tool a test built so that a suspension has something real behind it",
            entity="ticket",
            required_capability=capability,
            side_effect=SideEffect.WRITE,
        ),
        target="ticket",
        touched_fields=("status",),
        row={"department": department},
        args={"status": "closed"},
    )
    return SuspendedAction(
        id=ident,
        trace_id="trace_test",
        action=action,
        principal_id="u_asker",
        ent_hash="e" * 32,
        artefact=render_artefact(action),
        action_digest=action.digest(),
        raised_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        state=ApprovalState.PENDING,
    )


def a_proposed_grant(capability: str, *, department: str) -> SubjectGrant:
    """One real grant proposal, through `SubjectGrant`'s own validators."""
    return SubjectGrant(
        subject=principal_subject("u_1"),
        capability=Capability(value=capability),
        scope=department_scope(department),
        granted_by="u_reader",
        reason="written for this test",
        granted_at=NOW - timedelta(days=1),
    )


def a_promotion(proposer_id: str = "u_author") -> PromotionProposal:
    """One real widening proposal, through `PromotionProposal`'s own validators."""
    return PromotionProposal(
        item_id="doc_1",
        from_level=Visibility.DEPARTMENT,
        to_level=Visibility.COMPANY,
        proposer_id=proposer_id,
        owner_id="u_steward",
        review_by=NOW + timedelta(days=90),
        reason="the handbook belongs to everybody",
    )


def an_export(
    export_id: str,
    *,
    subjects: tuple[str, ...] = ("u_1",),
    all_subjects: bool = False,
) -> ExportAudit:
    """One real export row, through `ExportAudit`'s own validators."""
    return ExportAudit(
        export_id=export_id,
        at=NOW - timedelta(hours=1),
        requested_by="u_investigator",
        reason=ExportReason.INTERNAL_INVESTIGATION,
        reason_reference="matter-4471",
        stores=(Store.ATTACHMENT,),
        subjects=subjects,
        all_subjects=all_subjects,
        items=12,
    )


# ------------------------------------------------------- scopes and departments (M27.3.2)
def test_a_scope_a_readers_grant_does_not_contain_is_absent_rather_than_blanked() -> None:
    """Delete this and the Scopes screen becomes the People screen's shape, which is wrong
    here: blanking the predicate leaves `finance_shared`, and the slug is the department named
    in a friendlier font. The absence is what makes a scope out of reach indistinguishable
    from a scope nobody wrote.

    The two records differ only in the department their predicate names, and the reader holds
    the Scopes screen's capability in exactly one of the two, so the department is the only
    thing that can decide the answer."""
    reader = holding(scope_capability(), scope=in_department(MAINTENANCE))
    records = (a_scope_record("maintenance", MAINTENANCE), a_scope_record("finance", FINANCE))

    shown = scope_rows(records, reader, NOW)

    assert tuple(one.slug for one in shown) == ("maintenance",)
    assert shown[0].scope == department_scope(MAINTENANCE)


def test_a_company_wide_reader_of_scopes_is_shown_every_record_with_its_predicate() -> None:
    """The positive half. Delete it and `scope_rows` is satisfied by a function returning
    nothing, which passes every refusal test above and shows an administrator an empty Scopes
    screen while the grant they hold reaches all of it."""
    reader = holding(scope_capability())
    records = (a_scope_record("maintenance", MAINTENANCE), a_scope_record("finance", FINANCE))

    shown = scope_rows(records, reader, NOW)

    assert shown == records


def test_a_scope_wider_than_the_readers_own_grant_is_absent() -> None:
    """Delete this and containment can be replaced by "the reader holds the capability at
    all", which shows a department admin the unrestricted scope: the one record that reaches
    the whole company, listed on the screen whose whole subject is who reaches what.

    The unrestricted record is the interesting direction, because the narrower one in the test
    above proves only that something was filtered."""
    reader = holding(scope_capability(), scope=in_department(MAINTENANCE))
    company_wide = ScopeRecord(slug="everything", scope=Scope.unrestricted(), label="all rows")

    assert scope_rows((company_wide,), reader, NOW) == ()


def test_a_department_filter_offers_only_the_names_the_readers_own_scope_admits() -> None:
    """Delete this and the dropdown is populated from the department registry, which is the
    inventory `brain.core.department.plan_cross_department` refuses to produce, arriving on the
    screen whose rows were carefully scoped.

    Both names are offered to the function, so the filtering is what is under test rather than
    what the caller happened to pass."""
    reader = holding(scope_capability(), scope=in_department(MAINTENANCE))

    assert departments_offered((MAINTENANCE, FINANCE), reader, NOW) == (MAINTENANCE,)


def test_a_reader_holding_nothing_over_scopes_is_offered_no_departments() -> None:
    """Delete this and an absent grant can fall through to the unrestricted scope, which is
    the mistake `brain.core.department.compose` refuses in its own words: no scopes arriving
    from a failed lookup must never mean everything."""
    assert departments_offered((MAINTENANCE, FINANCE), holding("read:role"), NOW) == ()


def test_a_company_wide_reader_is_offered_every_department_named() -> None:
    """The positive half of the filter. Delete it and `departments_offered` is satisfied by a
    function returning nothing, and a super administrator's dropdown is empty."""
    assert departments_offered((MAINTENANCE, FINANCE), holding(scope_capability()), NOW) == (
        MAINTENANCE,
        FINANCE,
    )


# ----------------------------------------------------------------- staff sources (M27.3.5)
def test_a_department_scoped_grant_over_staff_sources_reaches_no_source() -> None:
    """Delete this and somebody makes the screen useful for a department admin by placing a
    source in a department, and the check that would have decided is this one. A roster is one
    list for the whole company and the department is a column inside it; there is no such
    thing as the sources feeding one department.

    The two readers differ only in the scope their `read:staff_source` grant carries."""
    rosters = (a_roster("spreadsheet", complete=False, asserts=frozenset({Asserts.EXISTENCE})),)
    scoped = holding("read:staff_source", scope=in_department(MAINTENANCE))
    company_wide = holding("read:staff_source")

    assert staff_source_rows(rosters, scoped, NOW) == ()
    assert tuple(one.source for one in staff_source_rows(rosters, company_wide, NOW)) == (
        "spreadsheet",
    )


def test_a_source_row_says_what_the_source_may_assert_and_never_what_it_returned() -> None:
    """Delete this and `asserts` is built from the rows the roster happened to contain, which
    reads identically on a screen and is a different fact: a spreadsheet whose rows all carry
    a department still asserts existence alone, and a row built from the people would say it
    asserts departments.

    Asserted against the roster's own declared trust rather than against a list written here,
    so the claim is that the row carries the source's decision."""
    trusted = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE})
    rosters = (a_roster("spreadsheet", complete=False, asserts=frozenset({Asserts.EXISTENCE})),)
    both = (*rosters, a_roster("lark", complete=True, asserts=trusted))

    rows = staff_source_rows(both, holding("read:staff_source"), NOW)

    assert tuple(one.source for one in rows) == ("lark", "spreadsheet")
    assert rows[0].asserts == tuple(sorted(one.value for one in trusted))
    assert rows[0].complete is True
    assert rows[1].asserts == (Asserts.EXISTENCE.value,)
    assert rows[1].complete is False


def test_a_staff_source_row_has_nowhere_to_carry_the_people_it_returned() -> None:
    """Delete this and somebody adds a headcount column, which is a fact about the company on
    a screen about where a list is read from, and two of them side by side are the people one
    source has and the other does not.

    Asserted on the field names of the type rather than on one built row, because a row built
    from a two-person roster would pass a test that only looked at values."""
    names = {one.name for one in fields(StaffSourceRow)}

    assert not names & NAMES_THAT_WOULD_BE_THE_ROSTER
    assert names == {"source", "asserts", "complete", "last_run_at"}


def test_the_last_run_time_is_carried_when_something_recorded_one() -> None:
    """The positive half of the row. Delete it and `last_run_at` can be hard-wired to None,
    which reads on the screen as a source that has never run and is the state an operator
    would chase."""
    rosters = (a_roster("lark", complete=True, asserts=frozenset({Asserts.EXISTENCE})),)

    rows = staff_source_rows(
        rosters, holding("read:staff_source"), NOW, last_run={"lark": NOW - timedelta(hours=2)}
    )

    assert rows[0].last_run_at == NOW - timedelta(hours=2)


def test_the_warning_about_two_role_authorities_comes_from_the_module_that_decides() -> None:
    """Delete this and a copy of the three findings ends up here, and the console's copy is
    the one an administrator reads, so it is the one that would look authoritative while
    disagreeing with the sync that actually runs."""
    trusted = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE})
    warnings = source_warnings(
        (
            a_roster("lark", complete=True, asserts=trusted),
            a_roster("ldap", complete=True, asserts=trusted),
        )
    )

    assert any("trusted to assert roles" in one for one in warnings)


# --------------------------------------------------------------- approvals queue (M27.3.7)
def test_each_kind_of_waiting_thing_is_filtered_by_its_own_authority() -> None:
    """Delete this and the queue is filtered by the Approvals screen's own capability, which
    offers an approver decisions they could not make and hides ones they could. That is the
    failure the role filter would have produced, arriving through the arrangement of the
    screen rather than through the filter.

    The reader holds the capability the suspended action requires and does not hold
    `approve:grant`, so the two sections can only differ by their own authority."""
    reader = holding_at(
        (
            ("write:ticket.status", in_department(MAINTENANCE)),
            ("read:capability", in_department(MAINTENANCE)),
        )
    )

    sections = approval_sections(
        reader,
        NOW,
        suspensions=(a_suspension("s_1", "write:ticket.status", department=MAINTENANCE),),
        grants=(a_proposed_grant("read:capability", department=MAINTENANCE),),
    )

    assert tuple(one.kind for one in sections) == (Waiting.ACTION,)


def test_an_approver_holding_the_grant_authority_sees_the_grant_section() -> None:
    """The positive half. Delete it and `approval_sections` is satisfied by a function that
    returns the action section and nothing else, which passes the test above for the wrong
    reason and leaves the grants queue permanently empty.

    The only difference from the test above is that this reader also holds `approve:grant`."""
    reader = holding_at(
        (
            ("approve:grant", in_department(MAINTENANCE)),
            ("read:capability", in_department(MAINTENANCE)),
        )
    )

    sections = approval_sections(
        reader,
        NOW,
        grants=(a_proposed_grant("read:capability", department=MAINTENANCE),),
    )

    assert tuple(one.kind for one in sections) == (Waiting.GRANT,)
    assert len(sections[0].items) == 1


def test_a_grant_proposal_outside_the_admins_own_scope_is_not_offered() -> None:
    """Delete this and containment is dropped from the grants section, and an admin whose
    authority is one department is offered a grant written over another. The row and the
    authority differ in exactly one thing here, the department the grant is written over."""
    reader = holding_at(
        (
            ("approve:grant", in_department(MAINTENANCE)),
            ("read:capability", in_department(MAINTENANCE)),
        )
    )

    sections = approval_sections(
        reader,
        NOW,
        grants=(a_proposed_grant("read:capability", department=FINANCE),),
    )

    assert sections == ()


def test_a_kind_this_approver_may_decide_none_of_has_no_section() -> None:
    """Delete this and a heading reading Grants appears above an empty list, which tells the
    reader that grants are waiting they may not see. That is the subtraction disclosure
    spelled out rather than counted, and it is the shape a renderer produces by iterating the
    three kinds."""
    reader = holding("read:capability")

    assert (
        approval_sections(
            reader, NOW, grants=(a_proposed_grant("read:capability", department=MAINTENANCE),)
        )
        == ()
    )


def test_a_section_refuses_to_be_built_with_nothing_in_it() -> None:
    """Delete this and a caller assembling sections by hand goes around the rule, which is
    `brain.console.govern.Certification`'s argument about where a refusal belongs: a rule kept
    only by the function that usually builds the object is a rule a hand-built object escapes."""
    with pytest.raises(GovernSurfaceError, match="nothing under it"):
        ApprovalSection(kind=Waiting.GRANT, items=())


def test_a_proposer_may_not_approve_their_own_widening() -> None:
    """Delete this and the promotion section offers an author their own proposal, which is the
    gate defeated with every record looking correct: there is a proposal, there is an
    approval, and they are the same person twice.

    Asked through `brain.knowledge.visibility.approve_promotion` rather than by restating its
    checks, so a fourth refusal added there is honoured here."""
    reader = holding(PROMOTION_CAPABILITY.value, principal_id="u_author")

    assert may_approve_promotion(a_promotion("u_author"), "u_author", reader, NOW) is False
    assert may_approve_promotion(a_promotion("u_other"), "u_author", reader, NOW) is True


def test_a_reader_without_the_promotion_capability_decides_no_widening() -> None:
    """Delete this and the promotion section is filtered by the Approvals screen's capability,
    which is a different grant from the one `approve_promotion` requires, so the screen would
    offer a control the submit path refuses."""
    reader = holding("approve:action", principal_id="u_approver")

    assert may_approve_promotion(a_promotion(), "u_approver", reader, NOW) is False


def test_a_blank_approver_decides_no_widening() -> None:
    """Delete this and `approver_id` can default to something the promotion gate accepts,
    which would approve on behalf of a person who was never asked. `approve_promotion`
    compares the name against the entitlement's own principal and an unstated approver is not
    the entitlement's owner."""
    reader = holding(PROMOTION_CAPABILITY.value, principal_id="u_approver")

    sections = approval_sections(reader, NOW, promotions=(a_promotion(),))

    assert sections == ()


def test_the_three_sections_come_back_in_the_screens_own_order() -> None:
    """Delete this and the order becomes whatever a dict iterated, and an approver reading the
    queue twice in a morning sees two different pages. The order is the one the Approvals
    screen's purpose sentence names: an action above its rung, a grant, a promotion."""
    reader = holding_at(
        (
            ("write:ticket.status", Scope(clauses=())),
            ("approve:grant", Scope(clauses=())),
            ("read:capability", Scope(clauses=())),
            (PROMOTION_CAPABILITY.value, Scope(clauses=())),
        ),
        principal_id="u_approver",
    )

    sections = approval_sections(
        reader,
        NOW,
        approver_id="u_approver",
        suspensions=(a_suspension("s_1", "write:ticket.status", department=MAINTENANCE),),
        grants=(a_proposed_grant("read:capability", department=MAINTENANCE),),
        promotions=(a_promotion(),),
    )

    assert tuple(one.kind for one in sections) == (Waiting.ACTION, Waiting.GRANT, Waiting.PROMOTION)


# ------------------------------------------------------------------------ exports (M27.3.9)
def test_holding_what_an_export_contained_does_not_show_that_it_happened() -> None:
    """**The edit this leaf exists to refuse.** Delete this and the log follows the data,
    written by whoever thinks that whoever could have taken an export may read that one was
    taken. That hands the log to everybody holding a wide read capability, who are the people
    the log exists to watch.

    The reader holds every capability the export could have needed and does not hold
    `read:export`, so the capability is the only thing that can decide."""
    reader = holding("read:client.*", "read:grant", principal_id="u_watcher")
    entries = (Placed(record=an_export("x_1"), where={"department": MAINTENANCE}),)

    assert export_log(entries, reader, NOW) == ()


def test_the_exports_screens_grant_shows_the_log_without_any_grant_over_what_left() -> None:
    """The other direction, and the positive half. Delete it and `export_log` is satisfied by
    a function returning nothing, and an auditor holding exactly the right grant reads an
    empty page.

    This reader holds `read:export` and nothing else at all, which is what an auditor's grant
    set looks like."""
    reader = holding(screen(EXPORT_LOG_SCREEN).read.requires.value, principal_id="u_auditor")
    row = an_export("x_1")
    entries = (Placed(record=row, where={"department": MAINTENANCE}),)

    assert export_log(entries, reader, NOW) == (row,)


def test_an_export_row_outside_the_readers_scope_is_absent() -> None:
    """Delete this and the exports screen shows a department admin every export in the
    company. The two rows differ only in the department they sit in."""
    reader = holding(
        screen(EXPORT_LOG_SCREEN).read.requires.value, scope=in_department(MAINTENANCE)
    )
    mine = an_export("x_1")
    theirs = an_export("x_2")
    entries = (
        Placed(record=mine, where={"department": MAINTENANCE}),
        Placed(record=theirs, where={"department": FINANCE}),
    )

    assert export_log(entries, reader, NOW) == (mine,)


def test_a_person_named_in_an_export_reads_that_row_whatever_they_hold() -> None:
    """Delete this and the one person with the strongest claim to the row cannot see it. An
    export naming somebody says their data was collected, under which reason and against which
    written authorisation, and that is what a subject access request asks for.

    The reader holds nothing at all, so the subject branch is the only way in."""
    reader = EntitlementSet(principal_id="u_1", grants=())
    row = an_export("x_1", subjects=("u_1", "u_2"))

    assert export_log((Placed(record=row, where={}),), reader, NOW) == (row,)


def test_an_export_covering_everybody_reaches_nobody_through_the_subject_branch() -> None:
    """Delete this and an export of the whole company reaches every employee's screen, because
    everybody is a subject of it. The log would then become a company-wide read through the
    branch that exists to serve one person.

    The two rows differ only in whether the export named a shortlist."""
    reader = EntitlementSet(principal_id="u_1", grants=())
    everybody = an_export("x_1", subjects=(), all_subjects=True)
    shortlist = an_export("x_2", subjects=("u_1",))
    entries = (Placed(record=everybody, where={}), Placed(record=shortlist, where={}))

    assert export_log(entries, reader, NOW) == (shortlist,)


def test_a_row_that_covers_everybody_and_names_a_shortlist_admits_nobody_by_name() -> None:
    """**The guard the test above cannot reach, and the reason it exists.**
    `brain.ops.export.BulkExportRequest` refuses an export that both covers everybody and
    names a shortlist, in its own words because the shortlist would read as the scope and it
    is not. `ExportAudit` does not refuse the same pair, so a row loaded from a table, written
    by an older version of the code or hand-built by a test can carry both, and then a
    shortlist that is not the scope would admit the people on it by name while the export
    reached everybody.

    Delete this and the `all_subjects` half of that check is unreachable, because every row
    built through `bulk_export` has an empty shortlist when it covers everybody, and a
    mutation removing the check would survive.

    The two rows differ only in `all_subjects`, and the reader is named on both."""
    reader = EntitlementSet(principal_id="u_1", grants=())
    malformed = an_export("x_1", subjects=("u_1",), all_subjects=True)
    shortlist = an_export("x_2", subjects=("u_1",))
    entries = (Placed(record=malformed, where={}), Placed(record=shortlist, where={}))

    assert export_log(entries, reader, NOW) == (shortlist,)


# ------------------------------------------------------- retention and erasure (M27.3.10)
def test_an_erasure_request_reaches_its_own_subject() -> None:
    """Delete this and a person cannot follow up the request they made, which is a right
    nobody can exercise. The reader holds nothing, so the subject branch is the only way in."""
    reader = EntitlementSet(principal_id="u_1", grants=())
    row = erasure_request("u_1", NOW - timedelta(days=2))

    assert deletion_rows((Placed(record=row, where={}),), reader, NOW) == (row,)


def test_an_erasure_request_outside_the_readers_scope_is_absent() -> None:
    """Delete this and whoever can open the Retention screen reads the list of everybody who
    has asked to be erased, which is usually a list of endings: a dispute, a departure, a
    complaint. The two rows differ only in the department their subject sits in."""
    reader = holding(
        screen(RETENTION_SCREEN).read.requires.value,
        scope=in_department(MAINTENANCE),
        principal_id="u_admin",
    )
    mine = erasure_request("u_1", NOW - timedelta(days=2))
    theirs = erasure_request("u_2", NOW - timedelta(days=1))
    entries = (
        Placed(record=mine, where={"department": MAINTENANCE}),
        Placed(record=theirs, where={"department": FINANCE}),
    )

    assert deletion_rows(entries, reader, NOW) == (mine,)


def test_a_deletion_row_takes_its_store_order_from_the_module_that_owns_it() -> None:
    """Delete this and the order is written out here, and the copy is the one that gets a
    store added to it late. Purging a derived copy before its source leaves a deleted person
    answerable from cache with every log line saying the deletion succeeded.

    Asserted against `brain.ops.erasure.deletion_order` rather than against a list in this
    file, which would be the same copy the rule refuses."""
    row = erasure_request("u_1", NOW)

    assert row.stores == deletion_order()
    assert row.completed_at is None


def test_a_deletion_row_has_nowhere_to_promise_a_deletion_date() -> None:
    """Delete this and a `due_at` column appears, which is a statement about a future nothing
    in this repository brings about, on the one screen somebody opens to check that deletion
    happens."""
    names = {one.name for one in fields(DeletionRow)}

    assert names == {"subject_id", "requested_at", "stores", "completed_at"}


def test_an_erasure_request_naming_nobody_is_refused() -> None:
    """Delete this and a queue entry belonging to nobody is loadable, and nobody can be told
    what happened to a request that names no one."""
    with pytest.raises(GovernSurfaceError, match="naming no subject"):
        erasure_request("  ", NOW)


def test_an_erasure_request_with_a_naive_time_is_refused() -> None:
    """Delete this and a naive request time compares wrongly against an aware completion time,
    by however many hours the host happens to sit from UTC, and neither direction announces
    itself."""
    with pytest.raises(GovernSurfaceError, match="naive request time"):
        erasure_request("u_1", datetime(2027, 5, 4, 10, 0))


def test_a_retention_report_is_handed_whole_to_a_company_wide_reader() -> None:
    """The positive half, and the shape of the decision: there is nothing on a
    `RetentionReport` to narrow, so it is the report or nothing. Delete this and
    `retention_view` is satisfied by a function returning None, and the screen is empty for
    the one person it was built for.

    Built by the real `enforcement_report`, so the object under test is the one the operator
    would actually be handed."""
    report = enforcement_report(
        now=NOW, census=[StoreCensus(store=Store.ATTACHMENT, beyond_horizon=3)]
    )
    reader = holding(screen(RETENTION_SCREEN).read.requires.value)

    assert retention_view(report, reader, NOW) is report


def test_a_department_scoped_reader_is_given_no_retention_report_at_all() -> None:
    """Delete this and somebody narrows the report to a department, which means inventing
    per-subject rows to narrow, and inventing them is a second implementation of what is kept
    where. The two readers differ only in the scope their grant carries."""
    report = enforcement_report(now=NOW, census=[])
    reader = holding(screen(RETENTION_SCREEN).read.requires.value, scope=in_department(MAINTENANCE))

    assert retention_view(report, reader, NOW) is None


def test_nothing_implements_the_eraser_or_the_sweeper_that_would_drain_the_queue() -> None:
    """**The finding, and it is most of this leaf.** Delete this and the queue renders as
    though something drains it, in the one screen somebody opens to check that deletion
    happens. `brain.ops.erasure.StoreEraser` and `brain.ops.retention.StoreSweeper` are
    protocols and both modules say the executor is not built.

    The deployment call passes nothing because there is nothing to pass; handing in a stub for
    one leaves the other finding, which is what makes the two separable rather than one
    sentence about the state of the world."""
    both = drain_gaps()

    assert len(both) == 2
    assert any("StoreEraser" in one for one in both)
    assert any("StoreSweeper" in one for one in both)

    only_the_sweeper = drain_gaps(eraser=object())

    assert len(only_the_sweeper) == 1
    assert "StoreSweeper" in only_the_sweeper[0]
    assert drain_gaps(eraser=object(), sweeper=object()) == ()


# -------------------------------------------------------------------------- audit (M27.3.18)
def test_the_audit_filter_offers_no_list_of_actors_and_cannot_grow_one() -> None:
    """**The decision this leaf turns on.** Delete this and a screen populates the actor
    dropdown from the ledger, which is a directory of everybody who has ever acted, or from
    the page, which is a directory of everybody on it. `brain.audit.view.AuditFilter` refuses
    an actor filter that is not an identifier and has no opinion about where the reference
    came from.

    Asserted on the field names of the type rather than on one built value, because a value
    with an empty actor list would pass a test that only looked at contents."""
    names = {one.name for one in fields(AuditFilterOptions)}

    assert not names & NAMES_THAT_WOULD_BE_AN_ACTOR_LIST
    assert names == {"actions", "subject_kinds"}


def test_the_subject_kinds_offered_are_the_ones_this_reader_holds_a_capability_over() -> None:
    """Delete this and the dropdown offers every kind, which is a filter that returns an empty
    page for a reason the reader cannot see, and that is the shape somebody reads as a bug in
    the ledger.

    The reader holds one kind capability and the assertion is against
    `brain.audit.view.CAPABILITY_BY_KIND`, so a new subject kind moves both sides together
    only if the mapping and the narrowing agree."""
    one_kind = sorted(CAPABILITY_BY_KIND)[0]
    reader = holding(audit_capability(), CAPABILITY_BY_KIND[one_kind].value)

    options = audit_filter_options(reader, NOW)

    assert options.subject_kinds == (one_kind,)
    assert audit_kinds(reader, NOW) == (one_kind,)


def test_a_wildcard_audit_grant_offers_every_subject_kind() -> None:
    """The positive half. Delete it and the narrowing is satisfied by a function returning
    nothing, and an auditor holding `read:audit.*` is offered no filter at all.

    `Capability.covers` expands the trailing star, which is what makes one grant reach every
    kind, and this is the test that says the surface honours it."""
    reader = holding("read:audit.*")

    assert audit_kinds(reader, NOW) == tuple(sorted(SUBJECT_KINDS))


def test_the_actions_offered_are_the_whole_vocabulary_and_never_the_readers_own() -> None:
    """Delete this and the actions are narrowed to the reader, which is their own entitlement
    under a heading reading everything that is recorded: it discloses nothing and tells them
    the ledger records less than it does.

    Asserted against `AuditAction` itself rather than a list here, so a new member is offered
    without anybody remembering to add it."""
    options = audit_filter_options(holding(audit_capability()), NOW)

    assert options.actions == tuple(sorted(AuditAction, key=lambda one: one.value))


def test_a_grant_of_read_audit_alone_is_reported_as_a_page_with_no_entries() -> None:
    """Delete this and a grant somebody stopped writing halfway ships as a working screen.
    `Capability.covers` does not expand an entity-level grant, so `read:audit` covers neither
    `read:audit.principal` nor any other kind, and the page shows the reader their own entries
    and nothing else.

    Reported rather than repaired, because repairing it would mean this module deciding
    somebody reaches more than their grants say."""
    findings = audit_grant_gaps(holding(audit_capability()), NOW)

    assert len(findings) == 1
    assert "read:audit" in findings[0]


def test_a_reader_who_holds_a_kind_capability_is_not_reported() -> None:
    """The positive half. Delete it and the finding fires for every auditor, which is a
    diagnostic nobody reads after the first week. The two readers differ only in whether they
    hold one kind capability."""
    complete = holding(audit_capability(), CAPABILITY_BY_KIND[sorted(CAPABILITY_BY_KIND)[0]].value)

    assert audit_grant_gaps(complete, NOW) == ()


def test_somebody_who_cannot_open_the_audit_screen_is_not_reported() -> None:
    """Delete this and the finding fires for everybody in the company who holds no audit grant
    at all, which is most people, and the diagnostic becomes a headcount."""
    assert audit_grant_gaps(holding("read:grant"), NOW) == ()


# ------------------------------------------------------------------------- the diagnostic
def test_the_deployment_check_is_clean_for_the_module_as_it_stands() -> None:
    """Delete this and `surface_gaps` can be broken by an edit to the module it checks without
    anything failing, which is the state a diagnostic spends most of its life in."""
    assert surface_gaps() == ()


def test_the_diagnostic_names_a_screen_key_the_registry_does_not_have() -> None:
    """Delete this and a surface can point at a screen nobody registered, so whatever
    capability it asks for is a grant no administrator reviews.

    Handed a constructed key rather than relying on the module's own, because a check that can
    only run against the healthy tree has nothing to report and every mutation in it
    survives."""
    findings = surface_gaps(keys=("scopes", "a_screen_nobody_registered"))

    assert len(findings) == 1
    assert "a_screen_nobody_registered" in findings[0]


def test_the_diagnostic_names_a_source_row_that_would_carry_the_roster() -> None:
    """Delete this and a headcount column is added to the staff sources screen by somebody
    making it more useful, and two of them side by side are a set difference nobody granted."""
    leaky = make_dataclass("LeakySourceRow", [("source", str), ("headcount", int)])

    findings = surface_gaps(keys=(), rows=(), source_row=leaky)

    assert any("headcount" in one for one in findings)


def test_the_diagnostic_names_an_options_type_that_would_offer_actors() -> None:
    """Delete this and the actor dropdown arrives as one field on a dataclass, added by
    somebody who found the typed filter unusable, and the screen becomes a directory."""
    leaky = make_dataclass("LeakyOptions", [("actions", tuple), ("actors", tuple)])

    findings = surface_gaps(keys=(), rows=(), options_type=leaky)

    assert any("actors" in one for one in findings)


def test_the_diagnostic_names_a_row_that_would_count_what_it_hid() -> None:
    """Delete this and a hidden count arrives on one of these four row types, which is the
    disclosure by subtraction the whole design refuses.

    Reused from `brain.ops.jobs.hidden_count_fields` rather than restated, so the list of
    names is the one the rest of the system watches."""
    leaky = make_dataclass("LeakyRow", [("subject_id", str), ("hidden_count", int)])

    findings = surface_gaps(keys=(), rows=(leaky,))

    assert any("hidden_count" in one for one in findings)


def test_the_diagnostic_names_an_export_row_that_would_carry_a_reference() -> None:
    """Delete this and an export row grows a field that travels into this log, and the check
    that would have caught it is `brain.ops.export.withheld_names_on`, which is reused here
    rather than restated because the words are that module's."""
    leaky = make_dataclass("LeakyExport", [("export_id", str), ("lock_count", int)])

    findings = surface_gaps(keys=(), rows=(), export_row=leaky)

    assert any("lock_count" in one for one in findings)


def test_every_screen_this_module_reads_is_a_govern_screen_in_the_registry() -> None:
    """Delete this and a surface here can read a screen from another group, which would put a
    governance decision behind an operational capability. Asserted against `SCREENS` rather
    than against a list in this file, because the two lists agreeing is the property."""
    govern_keys = {one.key for one in SCREENS if one.group.value == "govern"}

    assert set(SURFACE_SCREENS) <= govern_keys
    assert len(set(SURFACE_SCREENS)) == len(SURFACE_SCREENS)


def test_the_surface_count_is_the_number_of_leaves_the_module_claims() -> None:
    """Delete this and `SURFACE_COUNT` becomes a number that agrees with itself. It is pinned
    against the module's own `Task ids:` lines, which is the record the traceability sweep
    reads, so the constant cannot drift from the claim.

    Read out of the source rather than imported, because importing the module's own tuple and
    comparing its length against a constant derived from it is the comparison
    `CLAUDE.md` names: both sides move together."""
    source = Path(str(surfaces_module.__file__)).read_text(encoding="utf-8")
    claimed = {one for line in TASK_LINE_RE.findall(source) for one in TASK_ID_RE.findall(line)}

    assert len(claimed) == SURFACE_COUNT
    assert all(one.startswith("M27.3.") for one in claimed)


def test_no_surface_here_places_a_record_where_a_scoped_grant_would_reach_it() -> None:
    """The `NOWHERE` contract, asserted rather than assumed. Delete this and somebody changes
    `NOWHERE` to a row carrying a department, and every company-wide surface in this module
    quietly becomes reachable by a department-scoped grant.

    Asserted through `Scope.matches` on the real object, because the claim is about what a
    scoped predicate does with an empty row rather than about the value being empty."""
    assert in_department(MAINTENANCE).matches(dict(NOWHERE)) is False
    assert Scope(clauses=()).matches(dict(NOWHERE)) is True


def test_the_pinned_screen_keys_name_the_screens_this_module_reads() -> None:
    """Delete this and a screen key here can be repointed at another screen, and every
    narrowing below would start asking for a different capability while still passing, because
    each of them reads the requirement off whatever key the constant holds.

    Each pair is asserted against the capability string as written, which is outside both the
    constant and the registry entry, so moving either one fails."""
    assert screen(SCOPES_SCREEN).read.requires.value == "read:scope"
    assert screen(EXPORT_LOG_SCREEN).read.requires.value == "read:export"
    assert screen(RETENTION_SCREEN).read.requires.value == "read:retention_policy"
    assert screen(AUDIT_SCREEN).read.requires.value == "read:audit"
