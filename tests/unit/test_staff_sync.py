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

Task ids: M1.6.12
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

from brain.identity import staff_sync
from brain.identity.directory import DirectoryAssertion, reconcile
from brain.identity.roles import Role
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    Asserts,
    GroupRule,
    Roster,
    StaffRecord,
    assertions_from,
    source_gaps,
)
from brain.identity.staff_sync import SYNC_INTERVAL, DryRun, dry_run, due_at, is_due

YESTERDAY = datetime(2026, 9, 6, 2, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)


def person(address: str, *, groups: tuple[str, ...] = (), active: bool = True) -> StaffRecord:
    return StaffRecord(
        work_address=address, display_name=f"Person at {address}", groups=groups, active=active
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
    session to it, and the pure half of the split is gone."""
    allowed = {"__future__", "collections", "dataclasses", "datetime", "typing", "brain"}
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
