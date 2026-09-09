"""The scheduled roster read, held to the rule that the diff is the whole product.

Nobody watches a scheduled job. So what this module produces is the list of who would be
added and who would be removed, built from the inputs the real run uses, writing nothing. Two
things are being tested: that the diff is right, and that every rule which stops a removal
stops it for a stated reason rather than by an accident of arithmetic.

Three separate rules can empty the removal list and they are not the same rule. The source
did not promise completeness; nobody has ever seen what this source returns; and neither of
those touches a person the source explicitly says has left. Each has a test and each has a
sibling proving the other side, because a suppression tested only by its refusals is
satisfied by a function that removes nobody, ever.

The second half of the file is the department head's audit reach, which is the same module's
other product and a different kind of thing: a set of grants written against the people in a
department, because an audit entry carries no department to write them against. The tests
that matter most there are the two that go through a real `AuditView`, because the failure
this answers is a page that is empty for every reader it exists for while every fixture that
uses a company-wide grant passes over the top of it.

Task ids: M1.6.12, M33.2.1.2
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.audit.ledger import SUBJECT_KINDS, AuditAction, AuditChain, AuditEntry
from brain.audit.view import CAPABILITY_BY_KIND, AuditView
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.core.scope_sql import PredicateRefusedError, assert_conjunctive
from brain.identity import staff_sync
from brain.identity.directory import DirectoryAssertion, reconcile
from brain.identity.packs import SubjectGrant, subtractive_state
from brain.identity.roles import Role
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    Asserts,
    GroupRule,
    Roster,
    StaffRecord,
    StaffSourceError,
    assertions_from,
    source_gaps,
)
from brain.identity.staff_sync import (
    AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE,
    AUDIT_KIND_DECISIONS,
    AUDIT_PAGE_CAPABILITY,
    GRANT_LIFETIME,
    HEAD_AUDIT_SUBJECT_KINDS,
    ROSTER_PREFIX,
    SYNC_INTERVAL,
    AuditKindDecision,
    DryRun,
    audit_reach_for_head,
    dry_run,
    due_at,
    is_due,
    renewed,
)
from brain.identity.teams import PrincipalSubject

YESTERDAY = datetime(2026, 9, 6, 2, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)

#: Deliberately far outside any plausible wall clock, on the rule
#: `tests/unit/test_scope_and_capability.py` states: what is tested here is not about the
#: present, and a fixture that can expire is a test that reports a defect on a schedule
#: nobody chose.
READ_AT = datetime(2999, 1, 1, 3, 0, tzinfo=UTC)


def person(
    address: str,
    *,
    groups: tuple[str, ...] = (),
    active: bool = True,
    department: str = "",
) -> StaffRecord:
    return StaffRecord(
        work_address=address,
        display_name=f"Person at {address}",
        groups=groups,
        active=active,
        department=department,
    )


def roster(*people: StaffRecord, complete: bool = True) -> Roster:
    return Roster(
        source="google_workspace",
        people=people,
        complete=complete,
        asserts=DEFAULT_TRUST["google_workspace"],
    )


def sheet(*people: StaffRecord, complete: bool = False) -> Roster:
    return Roster(source="google_sheet", people=people, complete=complete)


# --- the diff ---------------------------------------------------------------------------


def test_a_dry_run_names_who_would_be_added_and_who_would_be_removed() -> None:
    """**The product of the whole module.** An operator wiring a source up wants to know
    whether the run they are about to schedule does what they think, and the only answer that
    settles it is the two lists with the people in them.

    Named rather than counted, in both directions. "Two people would be removed" cannot be
    checked against what the operator expects, and the question a dry run exists to answer is
    exactly whether the two are the two they had in mind.

    Delete this and the dry run can report the wrong people while its counts stay plausible."""
    found = dry_run(
        roster(person("here@example.com"), person("joined@example.com")),
        known={"here@example.com": "p_here", "gone@example.com": "p_gone"},
        last_applied=YESTERDAY,
    )

    assert [one.work_address for one in found.would_add] == ["joined@example.com"]
    assert found.would_remove == ("gone@example.com",)
    assert found.absent == ("gone@example.com",)
    assert found.withheld == ()


def test_a_roster_that_did_not_promise_completeness_removes_nobody_and_says_why() -> None:
    """Absence is not deletion, and an export that timed out, a filter somebody narrowed and a
    paging bug all produce a shorter list. The reason is carried in words rather than left as
    an empty list, because an empty removal list with no explanation reads as a source that
    agrees with the system.

    The sibling is the whole test. Without it a dry run that removed nobody under any
    circumstances would pass, and every source in the system would silently lose the ability
    to retire anybody.

    Delete this and the day a directory pages badly is the day everybody it missed is
    deprovisioned, on a run nobody watched."""
    partial = dry_run(
        sheet(person("here@example.com")),
        known={"here@example.com": "p_here", "unmentioned@example.com": "p_unmentioned"},
        last_applied=YESTERDAY,
    )
    whole = dry_run(
        roster(person("here@example.com")),
        known={"here@example.com": "p_here", "unmentioned@example.com": "p_unmentioned"},
        last_applied=YESTERDAY,
    )

    assert partial.would_remove == ()
    assert any("complete list" in one for one in partial.withheld), partial.withheld
    assert whole.would_remove == ("unmentioned@example.com",)


def test_a_dry_run_shows_who_is_absent_even_when_it_may_not_remove_them() -> None:
    """Who is missing is the fact that tells an operator whether the source is pointed at the
    right place, and it is exactly the fact a suppressed removal list throws away. A source
    aimed at one organisational unit and a source that is working correctly produce the same
    empty removal list and very different absences.

    Delete this and the failure a first run exists to catch is invisible on the first run."""
    found = dry_run(
        sheet(person("here@example.com")),
        known={"here@example.com": "p_here", "elsewhere@example.com": "p_elsewhere"},
        last_applied=None,
    )

    assert found.would_remove == ()
    assert found.absent == ("elsewhere@example.com",)


def test_a_sources_first_run_removes_nobody_however_complete_it_promised_to_be() -> None:
    """**Completeness is a promise about the source's answer and not about the question.** A
    Workspace connector aimed at one organisational unit, a Sheets range covering one office
    and a directory search rooted a level too deep are each complete, correct, and wrong about
    the company, and every one proposes removing everybody outside its scope on the first run.
    Nothing distinguishes that from a company that really did shrink, because there is no
    previous run to notice it against.

    The sibling is the second run, which is the one that may remove, because by then somebody
    has had a dry run to read.

    Delete this and the most dangerous run a source ever performs is the one nobody has seen
    the output of."""
    first = dry_run(
        roster(person("here@example.com")),
        known={"here@example.com": "p_here", "outside@example.com": "p_outside"},
        last_applied=None,
    )
    second = dry_run(
        roster(person("here@example.com")),
        known={"here@example.com": "p_here", "outside@example.com": "p_outside"},
        last_applied=YESTERDAY,
    )

    assert first.would_remove == ()
    assert any("never been applied" in one for one in first.withheld), first.withheld
    assert second.would_remove == ("outside@example.com",)


def test_the_removals_proposed_are_always_among_the_absences_found() -> None:
    """The property that makes every suppression rule safe to add: they narrow and they cannot
    widen. A dry run able to name somebody the caller did not show it is a dry run proposing
    to delete a row nobody read first, which is `reconcile`'s argument for being two set
    differences and is the same argument here.

    Asserted across every combination of the two suppressions rather than for one input, so a
    rule added later inherits the property rather than needing its own test.

    Delete this and a fourth rule can be added that computes its own removal list."""
    known = {"here@example.com": "p_here", "elsewhere@example.com": "p_elsewhere"}
    for complete in (True, False):
        for applied in (None, YESTERDAY):
            found = dry_run(
                Roster(
                    source="google_workspace",
                    people=(person("here@example.com"),),
                    complete=complete,
                    asserts=DEFAULT_TRUST["google_workspace"],
                ),
                known=known,
                last_applied=applied,
            )
            assert set(found.would_remove) <= set(found.absent), (complete, applied)
            assert set(found.absent) <= set(known), (complete, applied)


def test_a_person_the_source_says_has_left_is_reported_even_on_an_incomplete_first_run() -> None:
    """The one removal that survives both suppressions, because it is the source stating a
    fact rather than failing to mention one. A spreadsheet installation has no other way to
    retire anybody at all, so folding this in with the absences would leave it unable to.

    Reported separately rather than mixed into `would_remove`, because they are different
    actions: one is a person the source says has gone and the other is a person the source did
    not mention.

    Delete this and the only removal a spreadsheet can make is the one it cannot make."""
    found = dry_run(
        sheet(person("here@example.com"), person("left@example.com", active=False)),
        known={"here@example.com": "p_here", "left@example.com": "p_left"},
        last_applied=None,
    )

    assert found.would_deactivate == ("left@example.com",)
    assert found.would_remove == ()
    assert [one.work_address for one in found.would_add] == []


def test_somebody_the_source_says_has_left_is_not_proposed_as_an_addition() -> None:
    """A person marked as departed who is not in the system yet is not somebody to provision.
    Adding them would create an account for a leaver, which is the one direction of this
    mistake that is a security finding rather than an inconvenience.

    Delete this and a spreadsheet's leaver column creates accounts."""
    found = dry_run(
        sheet(person("never.joined@example.com", active=False)),
        known={},
        last_applied=YESTERDAY,
    )

    assert found.would_add == ()
    assert found.would_deactivate == ()


# --- what a dry run does with a configuration that is wrong ---------------------------------


def test_a_dry_run_reports_a_source_wired_to_rules_it_may_not_assert_rather_than_raising() -> None:
    """**A dry run is run against a configuration that might be wrong.** `assertions_from`
    refuses a source wired to role rules it is not trusted to assert, on purpose and at
    configuration time, and configuration time is precisely when somebody is looking at a dry
    run. Letting that exception escape would make the one tool for finding the
    misconfiguration the one tool that cannot survive it.

    The refusal is not softened: nothing may be applied, and `safe_to_apply` says so. The
    sibling proves a correctly wired source still produces its grants, without which a dry run
    that refused everything would pass.

    Delete this and the operator wiring a Google Sheet to a Super Admin rule sees a stack
    trace instead of the sentence explaining why it will not work."""
    refused = dry_run(
        sheet(person("someone@example.com", groups=("admins",))),
        known={"someone@example.com": "p_someone"},
        last_applied=YESTERDAY,
        rules=[GroupRule(source_group="admins", role=Role.SUPER_ADMIN)],
    )
    allowed = dry_run(
        roster(person("lead@example.com", groups=("approvers",))),
        known={"lead@example.com": "p_lead"},
        last_applied=YESTERDAY,
        rules=[GroupRule(source_group="approvers", role=Role.APPROVER)],
    )

    assert any("must not be wired to any" in one for one in refused.refusals), refused.refusals
    assert not refused.safe_to_apply
    assert refused.role_grants_to_add == ()

    assert allowed.refusals == ()
    assert allowed.safe_to_apply
    assert allowed.role_grants_to_add == (
        DirectoryAssertion(principal_id="p_lead", role=Role.APPROVER, source_group="approvers"),
    )


def test_a_role_a_roster_no_longer_supports_is_removed_only_when_a_person_would_be() -> None:
    """A role removed on the strength of an incomplete roster is the same mistake as a person
    removed on the strength of one, a table along. `reconcile` computes both differences and
    this discards the deletions under exactly the conditions that discard a removal, rather
    than computing the additions separately: a second set difference here would be a second
    answer to what a sync proposes.

    Both directions, because suppressing every deletion would make a directory unable to
    retire a role at all, which is the failure `directory.reconcile` exists to prevent.

    Delete this and a paging bug revokes every role in the company while the people survive."""
    held = (
        DirectoryAssertion(principal_id="p_lead", role=Role.APPROVER, source_group="approvers"),
    )
    partial = dry_run(
        Roster(
            source="google_workspace",
            people=(person("lead@example.com"),),
            complete=False,
            asserts=DEFAULT_TRUST["google_workspace"],
        ),
        known={"lead@example.com": "p_lead"},
        last_applied=YESTERDAY,
        rules=[GroupRule(source_group="approvers", role=Role.APPROVER)],
        held=held,
    )
    whole = dry_run(
        roster(person("lead@example.com")),
        known={"lead@example.com": "p_lead"},
        last_applied=YESTERDAY,
        rules=[GroupRule(source_group="approvers", role=Role.APPROVER)],
        held=held,
    )

    assert partial.role_grants_to_remove == ()
    assert whole.role_grants_to_remove == held


def test_a_role_the_roster_still_supports_is_in_neither_list() -> None:
    """The unchanged case, which is the common one by far. A sync that proposed deleting
    yesterday's row and inserting today's identical one would read in the audit ledger exactly
    like somebody's role being removed and restored.

    Delete this and every scheduled run is a revocation followed by a grant, for everybody."""
    held = (
        DirectoryAssertion(principal_id="p_lead", role=Role.APPROVER, source_group="approvers"),
    )
    found = dry_run(
        roster(person("lead@example.com", groups=("approvers",))),
        known={"lead@example.com": "p_lead"},
        last_applied=YESTERDAY,
        rules=[GroupRule(source_group="approvers", role=Role.APPROVER)],
        held=held,
    )

    assert found.role_grants_to_add == ()
    assert found.role_grants_to_remove == ()
    assert found.changes_nothing


def test_the_grants_a_dry_run_shows_are_the_rows_reconcile_would_be_handed() -> None:
    """The reuse claim, checked rather than asserted in a docstring. A dry run assembled from
    its own arithmetic is a rehearsal of a different performance, and the difference would only
    show up on the night.

    Delete this and the dry run can drift from the applying step, which is the one failure a
    dry run cannot warn anybody about."""
    people = roster(
        person("lead@example.com", groups=("approvers",)),
        person("aud@example.com", groups=("auditors",)),
    )
    known = {"lead@example.com": "p_lead", "aud@example.com": "p_aud"}
    rules = [
        GroupRule(source_group="approvers", role=Role.APPROVER),
        GroupRule(source_group="auditors", role=Role.AUDITOR),
    ]
    held = (DirectoryAssertion(principal_id="p_aud", role=Role.AUDITOR, source_group="auditors"),)

    found = dry_run(people, known=known, last_applied=YESTERDAY, rules=rules, held=held)
    directly = reconcile(assertions_from(people, rules, principal_for=known), held)

    assert set(found.role_grants_to_add) == set(directly.to_insert)
    assert set(found.role_grants_to_remove) == set(directly.to_delete)


def test_the_gaps_a_dry_run_reports_are_the_sources_own_and_not_a_second_opinion() -> None:
    """`source_gaps` is the diagnostic and this hands it through unchanged. A dry run with its
    own opinion about what is wrong with a source is a second implementation of a rule, and
    the two would drift in the direction of whichever one somebody edited.

    Delete this and the sync grows a private idea of what a misconfigured source looks like."""
    people = sheet(person("someone@example.com"))
    found = dry_run(people, known={}, last_applied=YESTERDAY)

    assert found.gaps == source_gaps([people])
    assert found.gaps, "the fixture no longer produces a gap, so this compared two empties"


def test_a_run_that_would_change_nothing_says_so_and_one_that_would_does_not() -> None:
    """A scheduled job that writes an audit entry per run whether or not anything changed
    buries the runs that did. `Reconciliation.is_empty` exists for the same reason and this is
    the same question one layer up, over people as well as over grants.

    Delete this and every quiet night looks like a night something happened."""
    quiet = dry_run(
        roster(person("here@example.com")),
        known={"here@example.com": "p_here"},
        last_applied=YESTERDAY,
    )
    busy = dry_run(
        roster(person("here@example.com"), person("new@example.com")),
        known={"here@example.com": "p_here"},
        last_applied=YESTERDAY,
    )

    assert quiet.changes_nothing
    assert not busy.changes_nothing


def test_a_dry_run_has_nowhere_to_write_and_nothing_to_write_with() -> None:
    """**The claim in the module's first line, made structural.** A dry run that could reach a
    database is a dry run somebody will eventually let write, and the argument for the split
    is that the deciding half stays testable without one.

    Read off the imports rather than off the signature, because the way a connection arrives
    is as a module-level session rather than as an argument. `sqlalchemy` and `psycopg` are
    absent, and so is everything else that is not the standard library or this package.

    Delete this and the first caller who wants the dry run to record its own run adds a
    session to it, and the pure half of the split is gone.

    `types` is on the list for `MappingProxyType`, which is how `AUDIT_KIND_DECISIONS` is
    published so nobody can edit the eight decisions in process. The list is an allowlist and
    not "the standard library", so a module arriving on it is a line in this test rather than
    a name that quietly passes, and that is the property worth keeping: `sqlalchemy` and
    `psycopg` are absent because everything is absent until somebody writes it down."""
    allowed = {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "types",
        "typing",
        "brain",
    }
    source = Path(staff_sync.__file__).read_text(encoding="utf-8")

    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(one.name.split(".")[0] for one in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported, "nothing was read, so this examined no imports at all"
    assert imported <= allowed, sorted(imported - allowed)
    assert isinstance(
        dry_run(roster(person("one@example.com")), known={}, last_applied=None), DryRun
    )


# --- the schedule -------------------------------------------------------------------------


def test_a_source_that_has_never_been_applied_is_due_now() -> None:
    """None rather than a time, because a source that has never been read has no interval to
    count from, and answering with the current time would make the answer depend on when the
    question was asked.

    Delete this and a newly wired source waits an interval before its first read, which is a
    day in which nobody can tell whether it works."""
    assert due_at(None) is None
    assert is_due(None, NOW)


def test_a_source_read_inside_its_interval_is_not_due_and_one_read_before_it_is() -> None:
    """The pair. A schedule that always answers due is a busy loop and one that never answers
    due is a sync that silently stopped, and only both assertions together rule out either.

    The boundary is inclusive, because a run due at exactly the interval is due: excluding it
    makes every run drift later by however long the previous one took.

    Delete this and the interval is decoration."""
    read_just_now = NOW - timedelta(minutes=1)

    assert not is_due(read_just_now, NOW)
    assert is_due(NOW - SYNC_INTERVAL - timedelta(seconds=1), NOW)
    assert is_due(NOW - SYNC_INTERVAL, NOW)
    assert due_at(read_just_now) == read_just_now + SYNC_INTERVAL


def test_somebody_who_joins_is_picked_up_within_a_day_of_the_last_run() -> None:
    """**The constant asserted against the thing that makes it right, not against itself.**
    The interval bounds how long a joiner waits, which is the visible failure of a longer one;
    a leaver keeping access does not depend on it at all, because sign-in is Keycloak's and an
    account disabled in the directory cannot sign in whatever this roster last said.

    So the property is that a day is enough, and the bound is one-sided: shortening the
    interval keeps this true and lengthening it does not.

    Delete this and the interval can be raised to a week by somebody reducing API calls, and
    a new starter waits a week for access with nothing anywhere saying why."""
    joined_at = NOW
    a_day = timedelta(days=1)

    assert a_day >= SYNC_INTERVAL
    assert is_due(joined_at, joined_at + a_day)


def test_the_schedule_has_nowhere_to_record_a_dry_run() -> None:
    """A dry run changes nothing, so recording one as a run would push the next real sync out
    by a full interval every time somebody looked at the diff. The failure would be a sync
    that stops happening on the day somebody starts watching it, which is as close to
    undiagnosable as this system gets.

    Asserted on the signatures: `is_due` takes the last time a sync was applied, and `dry_run`
    hands back nothing that could be stored as one.

    Delete this and a console page that shows a dry run quietly becomes a console page that
    suppresses the sync."""
    assert set(inspect.signature(is_due).parameters) == {"last_applied", "now", "every"}
    assert set(inspect.signature(due_at).parameters) == {"last_applied", "every"}

    produced = dry_run(roster(person("one@example.com")), known={}, last_applied=YESTERDAY)
    carried = fields(produced)
    assert carried, "no fields were read, so this examined nothing"
    assert not any(isinstance(getattr(produced, one.name), datetime) for one in carried), (
        "a dry run now carries a time, which is a time somebody will store as a run"
    )


def test_a_dry_run_of_a_source_trusted_with_nothing_still_produces_the_people() -> None:
    """The positive case for the whole file. Every rule above is a refusal or a narrowing, and
    a set of narrowings is satisfied by a dry run that proposes nothing whatever it is given.

    A least-trusted source is the hardest case for that: it may not assert a department or a
    role, and it must still be able to say who exists, which is the one thing every roster
    source is for.

    Delete this and a dry run that returned an empty answer for every input would pass every
    other test here."""
    found = dry_run(
        sheet(person("one@example.com"), person("two@example.com")),
        known={"one@example.com": "p_one"},
        last_applied=YESTERDAY,
    )

    assert [one.work_address for one in found.would_add] == ["two@example.com"]
    assert Asserts.ROLE not in DEFAULT_TRUST["google_sheet"]
    assert not found.changes_nothing
    assert found.safe_to_apply


# --- a department head's audit reach --------------------------------------------------------
#: What the roster says, with one person in another department so every narrowing has
#: something it has to leave out.
MAINTENANCE = (
    person("priya@example.com", department="Maintenance"),
    person("wei@example.com", department="Maintenance"),
    person("sam@example.com", department="Web"),
)

KNOWN = {
    "priya@example.com": "u_priya",
    "wei@example.com": "u_wei",
    "sam@example.com": "u_sam",
}

ENT = "a" * 32


def reach(
    *people: StaffRecord,
    complete: bool = True,
    asserts: frozenset[Asserts] | None = None,
    held: tuple[SubjectGrant, ...] = (),
    department: str = "Maintenance",
    read_at: datetime = READ_AT,
) -> staff_sync.HeadAuditReach:
    source = Roster(
        source="google_workspace",
        people=people or MAINTENANCE,
        complete=complete,
        asserts=DEFAULT_TRUST["google_workspace"] if asserts is None else asserts,
    )
    return audit_reach_for_head(
        source,
        department=department,
        head_id="u_head",
        known=KNOWN,
        read_at=read_at,
        held=held,
    )


def entitlement_of(grants: tuple[SubjectGrant, ...]) -> EntitlementSet:
    """The head's reach, built through `SubjectGrant.as_grant` rather than around it."""
    return EntitlementSet(principal_id="u_head", grants=tuple(one.as_grant() for one in grants))


def ledger_of(*actors: str) -> tuple[AuditEntry, ...]:
    """One grant entry per actor named, each about somebody who is not the reader."""
    chain = AuditChain()
    return tuple(
        chain.append(
            at=READ_AT,
            actor_id=actor,
            action=AuditAction.GRANT,
            subject=f"principal:u_subject{index}",
            ent_hash=ENT,
            trace_id="t1",
            details={"capability": "read:client.name"},
        )
        for index, actor in enumerate(actors)
    )


def test_a_department_scoped_audit_grant_matches_no_entry_at_all() -> None:
    """**The finding this section answers, kept as a measurement rather than a memory.** An
    audit entry records what happened, what kind of thing it happened to, which thing and who
    did it, and no department, so a clause over `department` admits nothing: a missing field
    must never satisfy a predicate. Nine entries by three actors, and a reader holding every
    audit capability scoped to their own department sees nought of them.

    The second half is the same reader with the same capabilities scoped to two named actors,
    seeing six rows and those two actors only, which is both the confirmation that the ledger
    is not simply unreadable and the shape of the fix.

    Delete this and the module's argument for why a department scope cannot be used becomes a
    claim nobody re-runs, and the obvious simplification, scoping these grants to the
    department like every other grant in the system, comes back with every test green and
    every head's activity page empty."""
    entries = ledger_of(*(("u_priya", "u_wei", "u_sam") * 3))
    assert len(entries) == 9

    by_department = EntitlementSet(
        principal_id="u_head",
        grants=tuple(
            Grant(capability=one, scope=Scope.department("maintenance"))
            for one in CAPABILITY_BY_KIND.values()
        ),
    )
    assert AuditView(entries, reader=by_department, now=READ_AT).page(limit=200).rows == ()

    seen = AuditView(entries, reader=entitlement_of(reach().to_insert), now=READ_AT).page(limit=200)
    assert len(seen.rows) == 6
    assert sorted({row.actor_id for row in seen.rows}) == ["u_priya", "u_wei"]


def test_a_head_reads_their_own_peoples_entries_and_nobody_elses() -> None:
    """The whole point, asserted through a real `AuditView` rather than against the scope.

    This is what pins `ACTOR_FIELD` to the field name `brain.audit.view._scope_row` actually
    projects. That name is private, so nothing importable connects the two, and the failure if
    they ever disagree is not an exception: it is a head's page rendering empty, which is
    exactly the failure item 48 records and is invisible to anybody not looking for it.

    Delete this and the grants can be written against a field the view does not project, and
    every other test here still passes, because they all read the scope rather than the rows
    it admits."""
    entries = ledger_of("u_priya", "u_sam", "u_wei")
    view = AuditView(entries, reader=entitlement_of(reach().to_insert), now=READ_AT)

    assert [row.actor_id for row in view.page().rows] == ["u_priya", "u_wei"]


def test_a_heads_grants_carry_the_people_and_no_department_clause() -> None:
    """A permission that names the people it covers is what item 48 chose it for: it can be
    read on a screen against the org chart. A department clause on the same row would be a
    scope that reads as correct and admits nothing.

    Delete this and a later change can add a department clause beside the actor one, which by
    conjunction matches nothing at all, with the actor clause still sitting there looking
    right."""
    for one in reach().to_insert:
        assert [clause.field for clause in one.scope.clauses] == ["actor_id"]
        assert [clause.op for clause in one.scope.clauses] == [Op.IN]
        assert [clause.value for clause in one.scope.clauses] == [("u_priya", "u_wei")]


def test_every_one_of_the_eight_audit_subject_kinds_has_been_decided_about() -> None:
    """The eight are `brain.audit.ledger.SUBJECT_KINDS`, and the decision list is compared
    with that rather than with a copy of itself, so a ninth kind added to the ledger leaves
    this red until somebody says whether a head reads it.

    Delete this and a new subject kind arrives with no decision, and which side it lands on is
    whatever the derived tuple happens to do, which is out."""
    assert set(AUDIT_KIND_DECISIONS) == SUBJECT_KINDS
    assert all(one.because.strip() for one in AUDIT_KIND_DECISIONS.values())


def test_a_head_holds_the_three_governance_kinds_and_none_of_the_other_five() -> None:
    """**The answer to the question item 48 called the better one.** The list is written out
    here rather than derived from the module, because a test that asks the module what it
    decided and then agrees with it has tested nothing.

    In: `principal`, where every grant and revocation lands; `agent`, where a leash change and
    a composition change land; `leash`, where an approval lands. Out: `grant`, which nothing
    writes; `entity` and `artifact`, whose ids are governed by a scope over the object that an
    actor-scoped audit grant never consults; `connector`, which is estate configuration a head
    cannot touch; and `session`, which is break-glass and would amount to a standing presence
    record over fifteen named people.

    Delete this and the set can be widened one kind at a time by whoever finds a page thin,
    and the widening is invisible because every other test here is about the shape of a grant
    rather than about which grants exist."""
    left_out = sorted(one for one, decision in AUDIT_KIND_DECISIONS.items() if not decision.covered)

    assert HEAD_AUDIT_SUBJECT_KINDS == ("agent", "leash", "principal")
    assert left_out == ["artifact", "connector", "entity", "grant", "session"]


def test_the_page_capability_and_the_kind_capabilities_are_written_together() -> None:
    """`Capability.covers` expands only a trailing `.*`, so `read:audit` and
    `read:audit.principal` are disjoint. A head given only the kinds has rows and no menu
    entry; a head given only the page has a screen showing them their own entries and nothing
    else, which is correct and reads as broken.

    Delete this and one of the two halves can be dropped as redundant, and the symptom is a
    screen that either cannot be found or is empty, neither of which points at a grant."""
    held = {one.capability.value for one in reach().to_insert}

    assert held == {
        AUDIT_PAGE_CAPABILITY.value,
        "read:audit.agent",
        "read:audit.leash",
        "read:audit.principal",
    }
    assert not AUDIT_PAGE_CAPABILITY.covers(CAPABILITY_BY_KIND["principal"])
    assert not CAPABILITY_BY_KIND["principal"].covers(AUDIT_PAGE_CAPABILITY)


def test_a_transfer_rewrites_the_reach_to_name_the_membership_that_is_left() -> None:
    """**The rewrite, which is the half of Option A that keeps the list true.** Somebody moves
    out of the department, and the run proposes deleting the four grants naming the old set
    and writing four naming the new one. Both halves, and the deletion is what makes it a
    revocation: there is no deny list anywhere, so the only way a head stops reading somebody
    is that the row saying they may is gone.

    Delete this and a sync that only ever inserts passes, and a head goes on reading somebody
    who transferred out of their department for as long as the old grant sits there."""
    before = reach().to_insert
    assert len(before) == 4

    after = reach(
        person("priya@example.com", department="Maintenance"),
        person("wei@example.com", department="Web"),
        held=before,
    )

    assert {one.capability.value for one in after.to_delete} == {
        one.capability.value for one in before
    }
    assert [clause.value for one in after.to_insert for clause in one.scope.clauses] == [
        ("u_priya",)
    ] * 4
    assert after.unchanged == ()
    assert not after.changes_nothing
    assert after.safe_to_apply


def test_a_run_over_an_unchanged_department_proposes_nothing_and_keeps_the_rows() -> None:
    """The sibling of the rewrite, and the reason `unchanged` exists at all. A head whose
    department did not change must not have four grants deleted and four written every night:
    in the ledger that is a revocation followed by a grant, once per head per run, and the
    runs that meant something are then unfindable.

    **The rows held are written at an earlier reading than the one being run**, which is the
    only version of this that tests anything. Both sides built at one instant agree on every
    field including the lapse, so a comparison that keys on the lapse as well as on the reach
    still reports no change, and a mutation adding `not_after` to the key survived exactly
    that fixture. Yesterday's rows against today's run is what the sync actually does.

    Delete this and the obvious implementation, delete everything and write the current set,
    passes the rewrite test above and fills the audit trail with churn."""
    yesterday = reach(read_at=READ_AT - SYNC_INTERVAL).to_insert
    again = reach(held=yesterday)

    assert {one.not_after for one in yesterday} != {one.not_after for one in reach().to_insert}
    assert again.changes_nothing
    assert again.to_insert == ()
    assert again.to_delete == ()
    assert len(again.unchanged) == 4


def test_a_kind_taken_out_of_the_decision_list_is_deleted_from_whoever_holds_it() -> None:
    """`to_delete` is computed against every audit capability this sync could ever have
    written, never against the ones it writes today. So narrowing the decision list takes the
    grant away from heads who already hold it rather than only changing what new heads get.

    A policy change that applies to nobody it was written about is the failure, and it is a
    quiet one: the decision would look taken, the list would read correctly, and every head
    granted before it would keep the reach.

    Delete this and removing a kind becomes a change to the future only."""
    stale = SubjectGrant(
        subject=PrincipalSubject(principal_id="u_head"),
        capability=CAPABILITY_BY_KIND["entity"],
        scope=reach().to_insert[0].scope,
        granted_by=f"{ROSTER_PREFIX}google_workspace",
        reason="heads Maintenance, whose people this roster names",
        granted_at=READ_AT,
    )

    assert "read:audit.entity" in AUDIT_CAPABILITIES_A_SYNC_MAY_WRITE
    assert "entity" not in HEAD_AUDIT_SUBJECT_KINDS
    assert reach(held=(stale,)).to_delete == (stale,)


def test_a_department_is_matched_however_the_directory_capitalised_it() -> None:
    """A department slug is lowercase and a department field in a directory is whatever
    somebody typed into it, so the comparison casefolds both sides. Without it a head of
    `maintenance` reads nothing at all from a roster that says `Maintenance`, which is the
    empty page this whole section exists to stop, arriving through a different door.

    Delete this and the surface works in every test fixture and is empty against the one
    directory anybody actually wires up."""
    found = reach(
        person("priya@example.com", department="MAINTENANCE"),
        person("wei@example.com", department="maintenance"),
        department="Maintenance",
    )

    assert found.members == ("u_priya", "u_wei")


def test_somebody_the_roster_lists_and_this_system_does_not_hold_contributes_nothing() -> None:
    """A roster names people by work address and this system holds principals, and the two
    disagree for as long as it takes somebody to provision a new starter. Their address maps
    to no principal, so there is nothing to put in a scope.

    Not reported here either: `dry_run.would_add` is where an unknown person is named, and a
    second answer to who is missing would be two lists to keep in step.

    Delete this and the lookup can go straight into the mapping, and a scheduled sync raises
    a KeyError on the day somebody joins."""
    found = reach(
        person("priya@example.com", department="Maintenance"),
        person("brandnew@example.com", department="Maintenance"),
    )

    assert found.members == ("u_priya",)


def test_another_heads_audit_grants_are_never_touched() -> None:
    """The held rows are filtered to this head's own before anything is compared, so a run for
    one department cannot reach the grants of another department's head. Every one of these
    rows looks alike apart from its subject and its member list, which is exactly why the
    subject has to be checked first.

    **Two rows, and both assertions are needed.** A grant naming another head's own people
    falls outside this run's wanted set, so without the filter it is proposed for deletion; a
    grant that happens to name the same people falls inside it, so without the filter it is
    reported as unchanged and the caller renews somebody else's row. A mutation removing the
    filter survived a version of this test that carried only the second row and only asserted
    the first thing.

    Delete this and a nightly sync over eight departments deletes seven heads' grants and
    writes one, and the symptom is seven people whose activity page went empty overnight."""
    theirs = SubjectGrant(
        subject=PrincipalSubject(principal_id="u_other_head"),
        capability=CAPABILITY_BY_KIND["principal"],
        scope=Scope(clauses=(Clause(field="actor_id", op=Op.IN, value=("u_sam",)),)),
        granted_by=f"{ROSTER_PREFIX}google_workspace",
        reason="heads Web, whose people this roster names",
        granted_at=READ_AT,
    )
    overlapping = SubjectGrant(
        subject=PrincipalSubject(principal_id="u_other_head"),
        capability=CAPABILITY_BY_KIND["agent"],
        scope=reach().to_insert[0].scope,
        granted_by=f"{ROSTER_PREFIX}google_workspace",
        reason="heads Web, whose people this roster names",
        granted_at=READ_AT,
    )
    found = reach(held=(theirs, overlapping))

    assert found.to_delete == ()
    assert found.unchanged == ()


def test_a_grant_a_person_wrote_by_hand_is_never_proposed_for_deletion() -> None:
    """The sync deletes only rows carrying `ROSTER_PREFIX` in `granted_by`.
    `brain.identity.directory` buys the same property with a second table and calls a filter
    on a column the weaker form, correctly; this is the strongest available while these rows
    share a table with every other capability grant.

    Delete this and the first refactor that simplifies the held-row filter starts deleting
    audit grants somebody appointed by hand, silently, and the symptom is a person quietly
    holding less than they should."""
    by_hand = SubjectGrant(
        subject=PrincipalSubject(principal_id="u_head"),
        capability=CAPABILITY_BY_KIND["session"],
        scope=Scope.department("maintenance"),
        granted_by="u_super_admin",
        reason="appointed during the incident review",
        granted_at=READ_AT,
    )

    assert reach(held=(by_hand,)).to_delete == ()


def test_a_source_not_trusted_to_place_people_names_none_of_them() -> None:
    """Every other suppression in this module is against a list that is too short, which fails
    closed. This one is against a list that is wrong: a department field nobody reviewed puts
    somebody else's people into a head's reach, which widens.

    So it produces no member list at all rather than a list marked unsafe, because a list that
    exists is a list somebody writes a screen against.

    Delete this and a spreadsheet anybody with the link can edit decides whose activity a
    department head may read."""
    refused = reach(asserts=frozenset({Asserts.EXISTENCE}))

    assert refused.members == ()
    assert refused.to_insert == ()
    assert refused.to_delete == ()
    assert not refused.safe_to_apply
    assert any("not trusted" in one for one in refused.refusals)


def test_a_half_answered_roster_reports_the_members_and_rewrites_nothing() -> None:
    """An export that timed out looks exactly like a department that halved. The direction is
    safe, because a shorter list narrows, and the visibility is not: the head's page shows
    fewer people, and DENIED being indistinguishable from ABSENT is what stops them noticing.

    The members are still reported, unlike the refusal above, because here the source can
    answer the question and may simply not have finished; that list is the diagnostic an
    operator reads. Two refusals, two different remains, and this asserts both.

    Delete this and a paging bug halves every head's reach overnight with nothing said."""
    refused = reach(complete=False, held=reach().to_insert)

    assert refused.members == ("u_priya", "u_wei")
    assert refused.to_insert == ()
    assert refused.to_delete == ()
    assert not refused.safe_to_apply
    assert any("complete" in one for one in refused.refusals)


def test_a_department_the_roster_places_nobody_in_produces_no_grant() -> None:
    """An `IN` clause with an empty member list is refused by `assert_conjunctive` before a
    `SubjectGrant` can hold one, so the alternative to returning nothing is an exception out
    of the middle of a scheduled job. Nothing is also the correct answer: a head of a
    department the roster places nobody in reads nothing, exactly as they would if no grant
    existed.

    The refusal is asserted here rather than assumed, because it is the reason this branch is
    a return rather than an oversight.

    Delete this and an empty department either raises inside the sync or, if somebody fixes
    that by dropping the clause, produces a grant with no clauses at all, which is
    unrestricted."""
    with pytest.raises(PredicateRefusedError, match="empty member list"):
        assert_conjunctive(Scope(clauses=(Clause(field="actor_id", op=Op.IN, value=()),)))

    empty = reach(person("sam@example.com", department="Web"))
    assert empty.members == ()
    assert empty.to_insert == ()
    assert empty.safe_to_apply


def test_a_person_the_source_says_has_left_is_not_in_the_reach() -> None:
    """Item 48's own wording is that the grant is rewritten when somebody joins or leaves. The
    alternative keeps a head reading a departed person's trail for as long as the row sits
    there, which is retention arriving through a permission rather than through a policy.

    Their entries do not go anywhere: the ledger keeps them and whoever holds the wider audit
    grant reads them.

    Delete this and a leaver stays in every head's reach until somebody notices the name."""
    found = reach(
        person("priya@example.com", department="Maintenance"),
        person("wei@example.com", department="Maintenance", active=False),
    )

    assert found.members == ("u_priya",)


def test_a_reach_lapses_within_two_reads_of_the_roster_behind_it() -> None:
    """The bound on the staleness cost. With no expiry a sync that stops leaves a head reading
    whatever membership it stopped at, for ever, and nothing about the page says so. Two
    intervals rather than one, so a single missed run is survivable and two close the reach.

    Asserted against `SYNC_INTERVAL` rather than against a literal number of days, because
    that relationship is what makes the figure right: change the interval and this moves with
    it.

    Delete this and the lifetime can be set to anything, including None, and the failure is a
    reach that outlives the roster reading nobody is doing any more."""
    assert GRANT_LIFETIME == 2 * SYNC_INTERVAL
    assert GRANT_LIFETIME > SYNC_INTERVAL

    for one in reach().to_insert:
        assert one.not_after == READ_AT + GRANT_LIFETIME
        assert one.is_active(READ_AT + SYNC_INTERVAL)
        assert not one.is_active(READ_AT + GRANT_LIFETIME)


def test_renewing_moves_the_lapse_and_never_the_appointment() -> None:
    """`granted_at` stays where it was, which is
    `brain.identity.directory.directory_role_grants`' argument about its own timestamp: a
    grant stamped with the current time reads, in every review afterwards, as though the
    appointment were made this morning. Nothing else moves either, because a function that
    could change the capability or the scope while claiming to renew would be a widening with
    a reassuring name.

    Delete this and the nightly touch on an unchanged row rewrites when the head was given
    this, and an access review can no longer tell a standing reach from a new one."""
    original = reach().to_insert[0]
    later = renewed(original, read_at=READ_AT + SYNC_INTERVAL)

    assert later.granted_at == original.granted_at
    assert later.capability == original.capability
    assert later.scope == original.scope
    assert later.granted_by == original.granted_by
    assert later.not_after == READ_AT + SYNC_INTERVAL + GRANT_LIFETIME


def test_a_source_name_too_long_to_record_as_a_grantor_is_refused_before_the_insert() -> None:
    """The same refusal `brain.identity.directory.directory_role_grants` makes about an
    issuer, for the same reason: a grantor string longer than the column fails at the INSERT,
    which is after the decision has been taken and inside a transaction.

    Delete this and a long source name turns a scheduled sync into a failing transaction with
    a database error in the log rather than a sentence naming the source."""
    with pytest.raises(StaffSourceError, match="too long to record as a grantor"):
        audit_reach_for_head(
            Roster(
                source="s" * 130,
                people=MAINTENANCE,
                complete=True,
                asserts=DEFAULT_TRUST["google_workspace"],
            ),
            department="Maintenance",
            head_id="u_head",
            known=KNOWN,
            read_at=READ_AT,
        )


def test_a_reach_over_no_department_or_no_head_is_refused() -> None:
    """Both are the mistake `brain.console.scoped_authority.department_coverage` refuses in
    its own words: over no department this is the company's ledger, and for no head it is a
    grant addressed to nobody.

    Delete this and a caller passing an empty string writes a grant to the principal named by
    the empty string, which resolves for whoever happens to hold that id."""
    with pytest.raises(ValueError, match="needs a department"):
        reach(department="  ")
    with pytest.raises(ValueError, match="needs the head"):
        audit_reach_for_head(
            roster(*MAINTENANCE),
            department="Maintenance",
            head_id=" ",
            known=KNOWN,
            read_at=READ_AT,
        )


def test_a_decision_about_a_kind_the_ledger_does_not_have_is_refused() -> None:
    """A decision about `read:audit.everything` decides nothing, and it would sit in the list
    looking like an answer. The check is against `SUBJECT_KINDS` rather than against a copy,
    so it moves when the ledger's vocabulary does.

    Delete this and a misspelled kind is a decision nobody made, while the kind it was meant
    to be about stays undecided and the list looks complete."""
    with pytest.raises(ValueError, match="is not an audit subject kind"):
        AuditKindDecision(kind="everything", covered=True, because="because it looks useful")


def test_a_decision_with_no_argument_behind_it_is_refused() -> None:
    """The rule `brain.identity.lifecycle.Step` keeps about its own reasons: a decision nobody
    can explain is one that gets reversed the first time it is inconvenient, and by then what
    it was protecting is gone. This list is what item 48 asked for precisely because it is a
    list somebody can read, and a blank line in it reads as an answer.

    Delete this and the eight arguments can be emptied one at a time by whoever is in a hurry,
    leaving a mapping that still passes the completeness check above."""
    with pytest.raises(ValueError, match="carries no argument"):
        AuditKindDecision(kind="session", covered=True, because="   ")


def test_nothing_in_this_module_subtracts_at_resolve_time() -> None:
    """M1.4.2 applied here, because this module now produces grants. `staff_sync` is not in
    `IDENTITY_MODULES`, which is a tuple in another file, so this is where the sweep reaches
    it.

    Delete this and the first person who wants a head's reach to leave one person out adds a
    field for it, and from that moment resolution has an order and no grant can be read on its
    own again."""
    assert subtractive_state(staff_sync) == []
