"""Where the staff list comes from, held to the one thing a staff list must never do.

A roster source answers "who works here". A sign-in source answers "prove you are that
person". Google, Microsoft and Lark can be both, which is why the two get conflated, and every
test here is about a consequence of keeping them apart: a spreadsheet may list people and may
not appoint them, a source that half answered may add and may never remove, and no source of
any trust may hand out a capability.

Real `Role`s and real `DirectoryAssertion`s throughout. A stand-in for either would test this
module against a fixture rather than against the two objects reconciliation actually consumes,
and the agreement is the whole point: `brain.identity.directory.reconcile` is two set
differences, so an assertion that is not equal to yesterday's identical one is a deletion and
an insertion in the audit ledger.

Task ids: none
"""

from __future__ import annotations

import pytest

from brain.identity.directory import DirectoryAssertion
from brain.identity.roles import Role
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    LEAST_TRUST,
    Asserts,
    GroupRule,
    Roster,
    StaffRecord,
    StaffSourceError,
    assertions_from,
    departments_from,
    source_gaps,
    trust_for,
)


def person(
    address: str,
    *,
    name: str = "A Person",
    department: str = "",
    groups: tuple[str, ...] = (),
    active: bool = True,
) -> StaffRecord:
    return StaffRecord(
        work_address=address,
        display_name=name,
        department=department,
        groups=groups,
        active=active,
    )


def roster(
    source: str,
    *people: StaffRecord,
    complete: bool = True,
    asserts: frozenset[Asserts] | None = None,
) -> Roster:
    return Roster(
        source=source,
        people=people,
        complete=complete,
        asserts=LEAST_TRUST if asserts is None else asserts,
    )


# --- a source may not say more than it is trusted to say -----------------------------------


def test_a_source_wired_to_role_rules_it_may_not_assert_is_refused() -> None:
    """**The decision this module exists for.** A Google Sheet anybody in the company can edit
    is a fine answer to who works here and a catastrophic answer to who is a Super Admin: one
    edit to a cell and somebody has appointed themselves, with the edit history in a document
    nobody reviews.

    Refused rather than filtered, and refused when the sync is wired rather than on the night
    it runs, because a rule that is quietly ignored looks exactly like a rule that is working.

    Delete this and the trust levels become documentation: a spreadsheet keeps its role rules,
    the rules keep resolving, and the audit ledger records a promotion nobody made."""
    sheet = roster("google_sheet", person("someone@example.com", groups=("admins",)))

    with pytest.raises(StaffSourceError, match="must not be wired to any"):
        assertions_from(
            sheet,
            [GroupRule(source_group="admins", role=Role.SUPER_ADMIN)],
            principal_for={"someone@example.com": "p_someone"},
        )


def test_a_source_trusted_with_roles_produces_the_assertions_its_groups_support() -> None:
    """The positive case, without which the refusal above is satisfied by a function that
    refuses everything.

    Asserted as the whole `DirectoryAssertion` rather than as a count, because the three
    fields are the primary key of `auth.directory_role_grant` and an assertion carrying the
    wrong `source_group` reconciles as a different row.

    Delete this and the trust check can start refusing every source and nothing says so."""
    workspace = roster(
        "google_workspace",
        person("lead@example.com", groups=("approvers",)),
        asserts=DEFAULT_TRUST["google_workspace"],
    )

    found = assertions_from(
        workspace,
        [GroupRule(source_group="approvers", role=Role.APPROVER)],
        principal_for={"lead@example.com": "p_lead"},
    )

    assert found == (
        DirectoryAssertion(principal_id="p_lead", role=Role.APPROVER, source_group="approvers"),
    )


def test_a_source_with_no_role_rules_at_all_is_not_refused_for_its_trust() -> None:
    """The refusal is about rules that would be ignored, not about the trust in the abstract.
    A spreadsheet wired to no role rules is a correctly configured spreadsheet, and raising on
    it would make the safe configuration the one that fails.

    Delete this and the guard grows into a refusal of the ordinary case, which is how a check
    ends up switched off."""
    sheet = roster("google_sheet", person("someone@example.com", groups=("admins",)))

    assert assertions_from(sheet, [], principal_for={"someone@example.com": "p_someone"}) == ()


def test_an_unknown_source_is_trusted_with_existence_and_nothing_else() -> None:
    """A client naming their own export script should not have to add a line to this file, and
    the safe answer for a source nobody has assessed is that it may list people. `trust_for`
    returning a permissive default for an unrecognised name is the one shape that would make
    every check above bypassable by choosing a source string nobody wrote down.

    Asserted against `Asserts.ROLE` and `Asserts.DEPARTMENT` by absence rather than against
    `LEAST_TRUST` alone, because comparing the answer to a constant imported from the same
    module compares that constant against itself and stays green for any value it holds.

    Delete this and an unknown source can be handed role rules."""
    found = trust_for("somebodys_own_csv_script")

    assert Asserts.EXISTENCE in found
    assert Asserts.ROLE not in found
    assert Asserts.DEPARTMENT not in found


def test_configuration_overrides_the_default_in_both_directions() -> None:
    """The defaults are a starting point, not a fixed rule: an installation whose sheet is
    locked to two people may raise it, and one whose Workspace groups are edited by a helpdesk
    may lower it. Both directions, because a `configured` argument that could only widen would
    make the cautious installation impossible.

    `configured is not None` rather than a truthiness test, and this is what pins that: an
    empty frozenset is a real configuration meaning "this source may say nothing", and under a
    truthiness test it would silently fall through to the permissive default.

    Delete this and lowering a source's trust to nothing raises it to the default instead."""
    assert trust_for("google_sheet", frozenset({Asserts.EXISTENCE, Asserts.ROLE})) == frozenset(
        {Asserts.EXISTENCE, Asserts.ROLE}
    )
    assert trust_for("google_workspace", frozenset()) == frozenset()


def test_no_trust_level_anywhere_can_confer_a_capability() -> None:
    """**The rule with no member for it, which is the point rather than an omission.** A group
    maps to a `Role` and to nothing else, because a capability in a directory moves "who can
    see the margin on this client" out of this system and into one nobody here reviews.

    Checked over the enum and over every configured default, so a fourth member added to
    either fails here rather than in the first installation that uses it.

    Delete this and `Asserts.CAPABILITY` can be added, and the module's argument for why it
    cannot exist survives only in prose."""
    assert set(Asserts) == {Asserts.EXISTENCE, Asserts.DEPARTMENT, Asserts.ROLE}

    for source, granted in DEFAULT_TRUST.items():
        assert granted <= set(Asserts), source

    assert not any("capab" in one.value for one in Asserts)


# --- absence is not deletion ---------------------------------------------------------------


def test_a_roster_that_did_not_promise_completeness_may_not_remove_anybody() -> None:
    """An export that timed out, a filter somebody narrowed and a paging bug all produce the
    same thing: a shorter list. Treating absence as departure turns any of them into a mass
    revocation that reads, in the audit ledger, exactly like a deliberate one.

    Delete this and the day a directory API pages badly is the day everybody loses their
    roles, and the ledger says the system did it on purpose."""
    partial = roster("lark", person("one@example.com"), complete=False)
    whole = roster("lark", person("one@example.com"), complete=True)

    assert not partial.may_remove()
    assert whole.may_remove()


def test_an_incomplete_roster_is_reported_as_a_gap_and_an_empty_one_is_not() -> None:
    """The pair that keeps the diagnostic honest. An incomplete run with people in it is a
    real limitation somebody should see; an empty roster is a source that returned nothing at
    all, which is either a company with no staff or a failure, and reporting "nobody may be
    removed" about it says nothing useful.

    Delete this and either the warning stops appearing when it matters or it appears on every
    empty run until nobody reads it."""
    with_people = source_gaps([roster("lark", person("one@example.com"), complete=False)])
    empty = source_gaps([roster("lark", complete=False)])

    assert any("may be removed" in one for one in with_people), with_people
    assert not any("may be removed" in one for one in empty), empty


def test_a_person_listed_twice_by_one_source_is_refused_at_construction() -> None:
    """Two rows for one person make every set difference ambiguous, and reconciliation is
    nothing but set differences. Refused at construction rather than reported later, so a
    roster cannot exist in the state that would make `reconcile` wrong.

    Case-folded, because a directory that exports one address in two capitalisations is a
    directory, not a hypothetical.

    Delete this and one duplicated row decides whether somebody keeps a role."""
    with pytest.raises(ValueError, match="more than once"):
        Roster(
            source="lark",
            people=(person("one@example.com"), person("ONE@example.com")),
            complete=True,
        )


def test_a_roster_with_no_source_name_cannot_be_constructed() -> None:
    """Reconciliation compares a source's rows against that same source's previous rows, so a
    roster with no name has nothing to be compared against and its rows would be attributed to
    whichever nameless run went before.

    Delete this and two unnamed sources reconcile against each other, and each one deletes the
    other's assertions on every run."""
    with pytest.raises(ValueError, match="cannot be reconciled"):
        Roster(source="   ", people=(), complete=True)


def test_a_record_without_a_usable_work_address_or_a_name_is_refused() -> None:
    """The work address is the only join between a roster entry and the person who signs in,
    and the display name is the only thing a screen can call them. A record missing either is
    a row that will be silently skipped somewhere further down, at a point where the source of
    the problem is no longer visible.

    Delete this and a blank cell in a spreadsheet becomes a principal nothing can match."""
    with pytest.raises(ValueError, match="not a work address"):
        person("no-at-sign")

    with pytest.raises(ValueError, match="no display name"):
        StaffRecord(work_address="one@example.com", display_name="  ")


# --- what the roster is allowed to produce -------------------------------------------------


def test_a_person_the_source_says_has_left_asserts_nothing() -> None:
    """`active=False` is the source saying this person has left, which is a different fact from
    their being absent entirely and is the one case where a source may take something away
    without promising a complete list.

    Delete this and a departure recorded in the directory keeps its roles until somebody
    deletes the row, which on a partial roster is never."""
    workspace = roster(
        "google_workspace",
        person("gone@example.com", groups=("approvers",), active=False),
        asserts=DEFAULT_TRUST["google_workspace"],
    )

    assert (
        assertions_from(
            workspace,
            [GroupRule(source_group="approvers", role=Role.APPROVER)],
            principal_for={"gone@example.com": "p_gone"},
        )
        == ()
    )


def test_an_address_with_no_principal_is_skipped_rather_than_provisioned() -> None:
    """Creating a principal is provisioning, which carries decisions about entitlements,
    departments and a sign-in identity that this function has no business making. It belongs to
    `brain.identity.lifecycle.provision`.

    The sibling assertion matters as much: the person who *does* have a principal is still
    produced, so the skip is a skip and not an abandoned run.

    Delete this and a roster read becomes a provisioning path, and every misspelled address in
    a spreadsheet creates an account."""
    workspace = roster(
        "google_workspace",
        person("known@example.com", groups=("approvers",)),
        person("stranger@example.com", groups=("approvers",)),
        asserts=DEFAULT_TRUST["google_workspace"],
    )

    found = assertions_from(
        workspace,
        [GroupRule(source_group="approvers", role=Role.APPROVER)],
        principal_for={"known@example.com": "p_known"},
    )

    assert [one.principal_id for one in found] == ["p_known"]


def test_two_groups_conferring_one_role_produce_two_assertions() -> None:
    """`source_group` is part of the identity rather than a detail hanging off it. Collapsing
    these into one row would make leaving either group remove the role, when the person is
    still in the other.

    Delete this and somebody removed from one of two groups loses a role they still hold."""
    workspace = roster(
        "google_workspace",
        person("both@example.com", groups=("approvers", "finance-approvers")),
        asserts=DEFAULT_TRUST["google_workspace"],
    )

    found = assertions_from(
        workspace,
        [
            GroupRule(source_group="approvers", role=Role.APPROVER),
            GroupRule(source_group="finance-approvers", role=Role.APPROVER),
        ],
        principal_for={"both@example.com": "p_both"},
    )

    assert {one.source_group for one in found} == {"approvers", "finance-approvers"}
    assert len(set(found)) == 2


def test_the_same_roster_read_twice_produces_equal_assertions() -> None:
    """Reconciliation is set arithmetic over frozen values, so a re-sync that produced
    unequal-but-identical assertions would propose deleting yesterday's row and inserting
    today's, which reads in the audit ledger exactly like somebody's role being removed and
    restored.

    Ordering is asserted too, because a caller that diffs two runs as sequences would see
    churn that the set arithmetic does not.

    Delete this and an unstable order or an unhashable field turns every sync into a
    revocation followed by a grant."""
    workspace = roster(
        "google_workspace",
        person("b@example.com", groups=("approvers",)),
        person("a@example.com", groups=("auditors",)),
        asserts=DEFAULT_TRUST["google_workspace"],
    )
    rules = [
        GroupRule(source_group="approvers", role=Role.APPROVER),
        GroupRule(source_group="auditors", role=Role.AUDITOR),
    ]
    principals = {"a@example.com": "p_a", "b@example.com": "p_b"}

    first = assertions_from(workspace, rules, principal_for=principals)
    second = assertions_from(workspace, rules, principal_for=principals)

    assert first == second
    assert [one.principal_id for one in first] == ["p_a", "p_b"]


def test_departments_come_back_empty_from_a_source_not_trusted_to_place_people() -> None:
    """A department is the scope a person's grants are bounded by, so a spreadsheet that could
    set it could widen somebody's reach by editing a cell.

    Empty rather than partial, because a partial map is one a caller would have to know to
    distrust, and the caller that knew would not have asked.

    Delete this and the department column of a shared spreadsheet decides what its editors can
    see."""
    sheet = roster("google_sheet", person("one@example.com", department="finance"))
    workspace = roster(
        "google_workspace",
        person("one@example.com", department="finance"),
        asserts=DEFAULT_TRUST["google_workspace"],
    )

    assert departments_from(sheet) == {}
    assert departments_from(workspace) == {"one@example.com": "finance"}


def test_a_person_with_no_department_is_absent_from_the_map_rather_than_placed_nowhere() -> None:
    """An empty string is not a department. Carrying one into the map would give the caller a
    key whose value bounds nothing, and a scope built from it would be a scope named "".

    Delete this and a blank cell becomes a department that no grant can ever match, and the
    person sees nothing with no error anywhere saying why."""
    workspace = roster(
        "google_workspace",
        person("placed@example.com", department="finance"),
        person("unplaced@example.com"),
        asserts=DEFAULT_TRUST["google_workspace"],
    )

    assert departments_from(workspace) == {"placed@example.com": "finance"}


# --- the diagnostic ------------------------------------------------------------------------


def test_two_sources_both_trusted_with_roles_are_reported() -> None:
    """The check nobody thinks of. Each source reconciles its own rows and neither can see the
    other's, so a person removed from a group in one keeps the role while the other still
    asserts it. That is the additive rule working as designed, and it is rarely what somebody
    configuring a second source expects.

    Reported rather than refused, because a company migrating from Workspace to Entra runs
    both for a month and a refusal would make the migration impossible.

    Delete this and a revocation performed in the directory silently does nothing."""
    both = source_gaps(
        [
            roster("google_workspace", asserts=DEFAULT_TRUST["google_workspace"]),
            roster("microsoft_entra", asserts=DEFAULT_TRUST["microsoft_entra"]),
        ]
    )

    assert any("trusted to assert roles" in one for one in both), both


def test_one_source_trusted_with_roles_is_not_reported() -> None:
    """The sibling. A diagnostic that fires on the ordinary single-source installation is a
    diagnostic somebody switches off, and then it is not there on the day a second source
    arrives.

    Delete this and the check can grow into a warning about every configuration."""
    one = source_gaps([roster("google_workspace", asserts=DEFAULT_TRUST["google_workspace"])])

    assert not any("trusted to assert roles" in line for line in one), one


def test_a_source_not_trusted_to_say_who_exists_is_reported() -> None:
    """Existence is the one thing every roster source is for, so a source configured without
    it is a source that has been wired for nothing. Worth saying out loud rather than leaving
    somebody to wonder why their sync produces no people.

    Delete this and `trust_for(name, frozenset())` is a silently useless configuration."""
    found = source_gaps([roster("odd", person("one@example.com"), asserts=frozenset())])

    assert any("who exists" in one for one in found), found


def test_a_correctly_configured_pair_of_sources_reports_nothing() -> None:
    """The positive case for the whole diagnostic. Without it, `source_gaps` returning a
    finding for every possible input would pass every test above.

    Delete this and the diagnostic can become unconditional, at which point its output means
    nothing."""
    clean = source_gaps(
        [
            roster(
                "google_workspace",
                person("one@example.com"),
                asserts=DEFAULT_TRUST["google_workspace"],
            ),
            roster("google_sheet", person("two@example.com"), asserts=LEAST_TRUST),
        ]
    )

    assert clean == ()
