"""Where the staff list comes from, held to the one thing a staff list must never do.

A roster source answers "who works here". A sign-in source answers "prove you are that
person". Google, Microsoft and Lark can be both, which is why the two get conflated, and every
test here is about a consequence of keeping them apart: a spreadsheet may list people and may
not appoint them, a source that half answered may add and may never remove, and no source of
any trust may hand out a capability.

The last section is about which of those sources a client's install reads, which is a question
this repository cannot answer and must not guess at: it is the master every client's system is
made from, so the source is a value somebody sets and the tests here are about what happens
when they set it wrongly. An unrecognised name, a source pointed nowhere and a roster of
nobody all have the same tempting non-answer, which is to carry on with what was returned, and
what was returned in every one of the three is an empty company.

Real `Role`s and real `DirectoryAssertion`s throughout. A stand-in for either would test this
module against a fixture rather than against the two objects reconciliation actually consumes,
and the agreement is the whole point: `brain.identity.directory.reconcile` is two set
differences, so an assertion that is not equal to yesterday's identical one is a deletion and
an insertion in the audit ledger.

Environments are passed as plain mappings rather than through `monkeypatch`, because
`brain.install.value_of` takes one for exactly that reason and a test that set a real
environment variable would be testing this process rather than an install.

Task ids: M1.6.1, M1.6.2, M1.6.3, M1.6.7, M1.6.9, M1.6.10
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from brain.identity.directory import DirectoryAssertion
from brain.identity.roles import Role
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    LEAST_TRUST,
    SELECTABLE,
    SELECTABLE_BY_NAME,
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    Asserts,
    GroupRule,
    Roster,
    SelectableSource,
    StaffRecord,
    StaffSource,
    StaffSourceError,
    assertions_from,
    departments_from,
    roster_from,
    selectable_names,
    selected_source,
    source_gaps,
    trust_for,
)
from brain.install import BY_NAME


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


def test_a_staff_source_has_no_way_to_authenticate_anybody() -> None:
    """**The axis this module exists to keep separate, asserted structurally.** A roster is a
    list read on a schedule; a sign-in source is a live protocol that proves somebody is who
    they say. Google, Microsoft and Lark can be both, which is why the two get conflated, and
    designing for that makes the spreadsheet case impossible: there is nothing to
    authenticate against.

    So `StaffSource` has exactly one method, and it answers a question about a list. A second
    one taking a credential is how the collapse arrives, and it would arrive looking like a
    convenience: the Workspace connector has the tokens already, so why not ask it.

    Asserted over the protocol's own members rather than over a name, because a method called
    `verify` or `check` or `bind` is the same failure whatever it is called, and asserted by
    absence of a credential-shaped parameter anywhere in the module's public functions for the
    same reason.

    Delete this and sign-in moves out of Keycloak one convenient method at a time, and the
    first installation to notice is one whose staff list is a spreadsheet."""
    import inspect

    from brain.identity import staff_source

    declared = {
        name
        for name, value in vars(StaffSource).items()
        if not name.startswith("_") and callable(value)
    }
    assert declared == {"roster"}
    assert inspect.signature(StaffSource.roster).parameters.keys() == {"self"}

    secrets = ("password", "secret", "token", "credential", "authenticate")
    for name, value in vars(staff_source).items():
        if name.startswith("_") or not inspect.isfunction(value):
            continue
        parameters = " ".join(inspect.signature(value).parameters).casefold()
        assert not any(one in parameters for one in secrets), f"{name} takes {parameters}"


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


# --- which of them this install reads ------------------------------------------------------


class Fixed:
    """A staff source that answers with a roster somebody wrote, and opens nothing.

    A class rather than a lambda because `StaffSource` is a protocol with one method, and
    satisfying it structurally is what proves `roster_from` needs nothing else from a source.
    """

    def __init__(self, answer: Roster) -> None:
        self.answer = answer

    def roster(self) -> Roster:
        return self.answer


def env(source: str, *, location: str = "somewhere") -> dict[str, str]:
    """One install's answers to the two settings that decide where its staff list is."""
    return {STAFF_SOURCE_SETTING: source, STAFF_SOURCE_LOCATION_SETTING: location}


def test_a_staff_source_name_nothing_here_recognises_is_refused_with_the_names_that_work() -> None:
    """**The rule that keeps this a template.** A misspelled or invented source must not fall
    back to a default, because the install that would meet that default is the one whose
    operator mistyped, and the symptom is a company's people read out of somewhere nobody
    chose. There is no default source for the same reason: whichever was written first would
    become every later client's.

    The message is asserted to carry every name, rather than to be non-empty, because a
    refusal that does not say what would have worked leaves somebody guessing at a spelling on
    a server they have just built.

    Delete this and `INSTALL_STAFF_SOURCE` accepts anything, resolves to whatever the lookup
    happens to return for a missing key, and the first evidence is a roster from the wrong
    system."""
    with pytest.raises(StaffSourceError) as refused:
        selected_source(env("google-workspace"))

    for name in selectable_names():
        assert name in str(refused.value), name


def test_an_install_that_has_chosen_nothing_reads_no_staff_list_rather_than_one_of_them() -> None:
    """The default is the absence of a source, not one of them picked on the client's behalf.
    Asserted through `brain.install`'s own declaration rather than against the word `none`, so
    the two cannot be changed apart: a default that named a real source would make one
    company's arrangement every company's, which is the whole of item 39's first half.

    Delete this and the default can quietly become a working source, and every install that
    has not chosen starts syncing from it."""
    declared = BY_NAME[STAFF_SOURCE_SETTING].default

    assert selected_source({}) is SELECTABLE_BY_NAME[declared]
    assert not SELECTABLE_BY_NAME[declared].reads_a_list


def test_a_source_short_of_two_settings_is_refused_naming_both_of_them() -> None:
    """**A mutation found that the plural half of that refusal was unreachable.**

    Every source declared today needs at most one setting, so a version naming only the first
    missing one survived. The case is not impossible, it was unbuildable: `selected_source`
    read the module's own tuple and no test could hand it a source needing two. It takes the
    set as a parameter now, defaulting to the real one.

    Both at once rather than the first, because an operator fixing a configuration wants the
    list rather than two runs of one error each.

    Delete this and adding a source that needs an address and a credential silently reports
    half of what is missing."""
    # Two guards had to be respected to construct this at all, and both are right.
    # `SelectableSource` refuses a name the trust table has no entry for, because a source
    # with no declared trust silently gets the least of it. And it refuses a `needs` entry
    # `brain.install` does not declare, because a setting with nowhere to be set refuses on
    # every install. So the name is a real one and both settings are declared ones. The
    # second is another optional setting rather than a staff one, because no staff source
    # needs two today: what is under test is the sentence, not a source this product has. It
    # has to be optional, because a required setting raises from `value_of` before
    # `unsupplied` can report it, which is a fourth guard in the same direction.
    needs_two = SelectableSource(
        name="google_workspace",
        meaning="a source that needs an address and something else that is declared",
        needs=(STAFF_SOURCE_LOCATION_SETTING, "INSTALL_BROKERED_DIRECTORY"),
    )

    with pytest.raises(StaffSourceError) as caught:
        selected_source({STAFF_SOURCE_SETTING: "google_workspace"}, sources=[needs_two])

    assert STAFF_SOURCE_LOCATION_SETTING in str(caught.value)
    assert "INSTALL_BROKERED_DIRECTORY" in str(caught.value)
    assert "are unset" in str(caught.value), "two of them, so the sentence is plural"


def test_a_source_name_with_space_around_it_is_the_name() -> None:
    """An operator pasting a value into an environment file brings whatever was around it, and
    a name refused for a trailing space is a refusal whose message reads as though the name is
    wrong. The name is not wrong.

    **The trimming happens in `brain.install.value_of` and not here, and a mutation is what
    established that.** This module trimmed the value a second time, and removing that changed
    nothing any test could see, because the one reader of an installation setting already
    strips what it returns. The second trim is gone rather than tested around: a guard that
    cannot fire is this repository's most common defect, and one on the boundary between two
    modules reads as belt and braces while being neither.

    So what this pins is the property rather than the line: an install that pasted a padded
    value gets the source it named, wherever the trimming is done."""
    padded = selected_source(
        {STAFF_SOURCE_SETTING: "  google_workspace  ", STAFF_SOURCE_LOCATION_SETTING: "a-domain"}
    )

    assert padded.name == "google_workspace"


def test_a_chosen_source_that_was_never_pointed_anywhere_is_refused_naming_the_setting() -> None:
    """**The empty-roster failure caught one layer earlier.** A directory with no address and
    a sheet with no identifier both answer, and both answer with nobody, which is exactly what
    a company where everybody left looks like to a sync that reads a source's answer as the
    membership.

    The setting is named in the message, because "not configured" on somebody else's server is
    a sentence they cannot act on and a variable name is one they can.

    Delete this and choosing a source is enough to start a sync that reads nothing, and the
    first dry run proposes removing every person in the company."""
    with pytest.raises(StaffSourceError) as refused:
        selected_source({STAFF_SOURCE_SETTING: "ldap"})

    assert STAFF_SOURCE_LOCATION_SETTING in str(refused.value)


def test_a_chosen_source_with_everything_it_needs_is_returned() -> None:
    """The positive sibling of the two refusals above, without which both are satisfied by a
    function that refuses every configuration.

    Delete this and the selection can start refusing every install, and the only symptom is
    that nobody's staff list ever syncs."""
    assert selected_source(env("ldap")).name == "ldap"
    assert selected_source(env("spreadsheet")).name == "spreadsheet"


def test_a_source_that_needs_nothing_is_not_held_up_by_an_unset_location() -> None:
    """A hand-kept spreadsheet is uploaded, so the file is its own answer to where the list is
    and there is nothing to point at. A requirement applied to every source alike would make
    the one source that needs no configuration impossible to configure.

    Delete this and `needs` becomes decoration: every source demands every setting, and the
    refusal above stops being about this source and starts being about all of them."""
    assert selected_source({STAFF_SOURCE_SETTING: "spreadsheet"}).name == "spreadsheet"


def test_the_selection_carries_no_trust_of_its_own() -> None:
    """**Item 39's second half, asserted structurally.** The staff list lists people and roles
    are set in the console, so there must be no field here through which choosing a source
    also decides what it may assert. `trust_for` is that answer and a second one reachable
    from an environment file would let a shared spreadsheet name a Super Admin.

    Asserted over the field names rather than over a type, because a field called `asserts`,
    `trust` or `may` is the same failure whatever it is annotated as.

    Delete this and the day somebody adds a trust field to the selection is the day an install
    file can appoint people."""
    assert {one.name for one in fields(SelectableSource)} == {
        "name",
        "meaning",
        "needs",
        "reads_a_list",
    }


def test_the_two_staff_lists_anybody_with_the_link_can_edit_may_not_appoint_anybody() -> None:
    """**The evidence for item 39's second answer, taken from the trust table rather than
    from prose.** Both of the sources a client is most likely to pick are editable by whoever
    holds the link, so one edit to one cell would be an appointment with its history in a
    document nobody reviews.

    Asserted by the absence of `ROLE` and `DEPARTMENT` rather than against `LEAST_TRUST`,
    because comparing the answer with a constant imported from the module under test compares
    that constant with itself and stays green for every value it could hold.

    Delete this and the default trust for a spreadsheet can be raised without a word, and the
    console stops being where roles are decided."""
    for name in ("spreadsheet", "google_sheet"):
        assert name in SELECTABLE_BY_NAME, name
        assert Asserts.EXISTENCE in trust_for(name), name
        assert Asserts.ROLE not in trust_for(name), name
        assert Asserts.DEPARTMENT not in trust_for(name), name


def test_a_selectable_source_the_trust_table_does_not_know_is_refused_at_construction() -> None:
    """A source offered to an install whose name the trust table has never heard of falls to
    existence alone with nothing anywhere saying so, which is the silent demotion
    `staff_adapters` argues about at length. Offering it is worse than parsing it, because the
    install that picks it believes it has chosen a directory.

    Delete this and a source can be added to the menu with a hyphen in its name, and every
    install that picks it stops conferring departments and roles for no visible reason."""
    with pytest.raises(ValueError, match="trust table has no entry"):
        SelectableSource(name="google-workspace", meaning="a near miss")


def test_a_selectable_source_needing_a_setting_nobody_declared_can_never_be_chosen() -> None:
    """`needs` names installation settings so a refusal can name a variable somebody can set.
    A name `brain.install` does not declare is one `value_of` refuses outright, so that source
    would refuse on every install for ever with no way to satisfy it.

    Delete this and a typo in a requirement makes a source permanently unselectable, and the
    error a client sees is about an undeclared setting rather than about their choice."""
    with pytest.raises(ValueError, match=r"brain\.install does not declare"):
        SelectableSource(name="ldap", meaning="a directory", needs=("INSTALL_NOT_A_SETTING",))


def test_a_source_that_reads_no_list_cannot_require_a_setting() -> None:
    """`none` is the absence of a staff list, so a setting it required would be one an install
    could never satisfy its way out of needing: there is nothing to point anywhere.

    Delete this and the option meaning "read nothing" can be given a requirement, and an
    install that has chosen no staff source is refused for not configuring one."""
    with pytest.raises(ValueError, match="reads no list"):
        SelectableSource(
            name="none",
            meaning="no list",
            needs=(STAFF_SOURCE_LOCATION_SETTING,),
            reads_a_list=False,
        )


def test_a_selectable_source_with_no_name_or_no_meaning_is_refused() -> None:
    """The name is what an install sets and what a refusal lists; the meaning is what a setup
    screen shows the person choosing. A source missing either is one somebody picks blind.

    Delete this and a blank row can be added to the menu, and the refusal for an unknown name
    lists an empty string among the answers that would have worked."""
    with pytest.raises(ValueError, match="not a staff source somebody could choose"):
        SelectableSource(name="  ", meaning="a source with no name")

    with pytest.raises(ValueError, match="not a staff source somebody could choose"):
        SelectableSource(name="ldap", meaning="   ")


def test_every_source_on_the_menu_is_one_the_trust_table_has_assessed() -> None:
    """The construction guard above, asked of the real menu rather than of an example. The two
    are different tests: one proves the rule refuses, this proves the shipped list obeys it.

    Delete this and the guard can be satisfied by a menu nobody checked it against."""
    for one in SELECTABLE:
        assert one.reads_a_list == (one.name in DEFAULT_TRUST), one.name


# --- what a chosen source is allowed to hand back ------------------------------------------


def test_a_roster_of_nobody_is_refused_before_anything_can_read_it_as_everybody_leaving() -> None:
    """**The dangerous shape this whole section exists for.** `staff_sync.dry_run` reads what
    a source returns as the membership, so a complete roster with nobody in it is a diff
    proposing that every person in the company be removed, and it is indistinguishable from a
    company that really did empty. A source pointed at the wrong place and a credential that
    was never supplied both produce exactly this.

    Refused where the answer arrives, while the source that produced it is still in hand,
    rather than reported by `source_gaps`, which says nothing about an empty roster on purpose.

    Delete this and a directory outage becomes a mass revocation that the audit ledger records
    as deliberate."""
    chosen = SELECTABLE_BY_NAME["ldap"]

    with pytest.raises(StaffSourceError, match="answered with nobody"):
        roster_from(Fixed(roster("ldap")), chosen)


def test_a_roster_claiming_more_than_its_source_is_trusted_with_is_refused() -> None:
    """**Item 39's second answer at the seam the install reaches.** Choosing where a staff
    list lives is not appointing anybody from it, so a roster arriving through the install's
    own choice may not say more than that source's declared trust allows. Without this, a
    spreadsheet reaching this seam with role trust would confer roles from a document anybody
    with the link can edit.

    `trust_for` is called rather than restated, so this adds no second answer to what a source
    may assert; it compares the roster against the one answer there is.

    Delete this and the trust table becomes advisory at the one point an install can reach."""
    appointing = Roster(
        source="google_sheet",
        people=(person("one@example.com", groups=("admins",)),),
        complete=True,
        asserts=frozenset({Asserts.EXISTENCE, Asserts.ROLE}),
    )

    with pytest.raises(StaffSourceError, match="more than that source is trusted with"):
        roster_from(Fixed(appointing), SELECTABLE_BY_NAME["google_sheet"])


def test_a_roster_claiming_less_than_its_source_is_trusted_with_is_read() -> None:
    """The other direction, and it has to keep working: an installation whose Workspace groups
    are edited by a helpdesk may lower that source's trust, and a check that refused a
    narrowing would make the cautious configuration the one that fails.

    Delete this and the widening check above grows into a demand that every roster match its
    default exactly, and lowering a source's trust becomes impossible."""
    cautious = Roster(
        source="google_workspace",
        people=(person("one@example.com"),),
        complete=True,
        asserts=frozenset({Asserts.EXISTENCE}),
    )

    assert roster_from(Fixed(cautious), SELECTABLE_BY_NAME["google_workspace"]) is cautious


def test_a_roster_from_a_source_other_than_the_one_chosen_is_refused() -> None:
    """Reconciliation compares a source's rows against that same source's previous rows, so an
    install configured for one source and handed another would have the two deleting each
    other's assertions on every run, additively and for ever.

    Delete this and a connector wired to the wrong adapter reconciles against a stranger's
    rows, and every sync is a revocation followed by a grant."""
    with pytest.raises(StaffSourceError, match="was handed a roster from"):
        roster_from(
            Fixed(roster("google_sheet", person("one@example.com"))),
            SELECTABLE_BY_NAME["spreadsheet"],
        )


def test_a_source_that_reads_no_list_has_no_roster_to_be_asked_for() -> None:
    """An install with no staff source provisions people in the console, so there is nothing
    to read. Answering with an empty roster instead would be the same mass revocation the
    empty-roster refusal exists to stop, arriving by the one route that looks legitimate.

    Delete this and the safest configuration, having chosen no source at all, becomes the one
    that proposes removing everybody."""
    with pytest.raises(StaffSourceError, match="reads no staff list"):
        roster_from(
            Fixed(roster("spreadsheet", person("one@example.com"))),
            SELECTABLE_BY_NAME["none"],
        )


def test_a_populated_roster_from_the_chosen_source_is_handed_back_unchanged() -> None:
    """The positive case for `roster_from`, without which every refusal above is satisfied by
    a function that refuses everything.

    Identity rather than equality, because a seam that rebuilt the roster would be a second
    place its fields are decided, and the one that drifts is the copy nobody reads.

    Delete this and the seam can start refusing every roster, and the only symptom is a sync
    that never runs."""
    answered = roster("spreadsheet", person("one@example.com"), complete=False)

    assert roster_from(Fixed(answered), SELECTABLE_BY_NAME["spreadsheet"]) is answered
