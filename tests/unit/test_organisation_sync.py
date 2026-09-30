"""What the directory sync would change about teams and leads, and the four rules that narrow it.

`brain.identity.organisation_sync.organisation_plan` against rosters built here and holdings passed
in. Every rule is a narrowing, so each test pairs the narrowed case with the one it narrows, for
CLAUDE.md's rule about a guard tested only by its refusals. Applying a plan against PostgreSQL is
`tests/unit/test_organisation_store.py`.

Task ids: M27.7.4
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from brain.console.organisation import founded
from brain.core.department import SLUG_PATTERN
from brain.identity.organisation_sync import (
    SLUG_CHARS,
    HeldLead,
    HeldMembership,
    Placement,
    department_slug,
    departments_to_found,
    organisation_plan,
    sync_actor,
)
from brain.identity.staff_source import (
    Asserts,
    Roster,
    StaffRecord,
    leads_from,
    teams_from,
)
from brain.identity.starter_pack_sync import registered_by_name
from brain.tables.organisation import SYNC_ACTOR_PREFIX

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

TRUSTED = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT})
KNOWN = {"wei@example.test": "u_wei", "new@example.test": "u_new", "gone@example.test": "u_gone"}
TEAMS = frozenset({"web.design", "web.projects"})
DEPARTMENTS = frozenset({"web", "finance"})
SYNC = sync_actor("lark")


def roster(
    *people: StaffRecord, complete: bool = True, asserts: frozenset[Asserts] = TRUSTED
) -> Roster:
    return Roster(source="lark", people=people, complete=complete, asserts=asserts)


def wei(*teams: str, active: bool = True) -> StaffRecord:
    return StaffRecord("wei@example.test", "Wei", department="web", teams=teams, active=active)


def test_a_trusted_source_places_people_in_registered_teams_and_appoints_its_lead() -> None:
    """The positive case. Delete this and every narrowing below is satisfied by a plan that never
    proposes anything, and the sync's half of M27.7.4 writes nothing on any install."""
    plan = organisation_plan(
        roster(
            wei("design", "pods"),
            StaffRecord("new@example.test", "New", department="web", leads=True),
            StaffRecord("stranger@example.test", "Stranger", department="web", teams=("design",)),
        ),
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        last_applied=None,
    )

    assert plan.to_join == (Placement(where="web.design", principal_id="u_wei"),)
    assert plan.to_appoint == (Placement(where="web", principal_id="u_new"),)
    assert plan.unregistered == ("web.pods",)
    assert plan.safe_to_apply and not plan.changes_nothing
    assert plan.actor == SYNC == f"{SYNC_ACTOR_PREFIX}lark"


def test_a_source_not_trusted_with_departments_proposes_nothing_and_says_why() -> None:
    """Delete this and a shared sheet anybody can edit places people in teams and names leads,
    which is the directory a department's access is reviewed against."""
    plan = organisation_plan(
        roster(wei("design"), asserts=frozenset({Asserts.EXISTENCE})),
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        last_applied=LONG_AGO,
    )

    assert plan.changes_nothing
    assert plan.refusals != () and not plan.safe_to_apply
    assert teams_from(roster(wei("design"), asserts=frozenset({Asserts.EXISTENCE}))) == {}


def test_the_sync_ends_only_the_placements_it_made() -> None:
    """`THE_SYNC_ENDS_ONLY_THE_PLACEMENTS_IT_MADE`. Delete this and a placement an administrator
    made in the console, which the source does not mention, is taken away on the next run."""
    held = (
        HeldMembership(team="web.design", principal_id="u_wei", added_by=SYNC),
        HeldMembership(team="web.projects", principal_id="u_wei", added_by="u_admin"),
    )

    plan = organisation_plan(
        roster(wei()),
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        memberships=held,
        last_applied=LONG_AGO,
    )

    assert plan.to_leave == (held[0],)


def test_absence_ends_nothing_on_an_incomplete_or_first_run_and_a_departure_ends_it_anyway() -> (
    None
):
    """Delete this and an export that half answered, or a first run aimed at the wrong place, takes
    everybody out of their teams; or somebody the source says has left stays in theirs."""
    held = (
        HeldMembership(team="web.design", principal_id="u_gone", added_by=SYNC),
        HeldMembership(team="web.design", principal_id="u_wei", added_by=SYNC),
    )
    gone = StaffRecord("gone@example.test", "Gone", department="web", active=False)

    def plan_for(*, complete: bool, last: datetime | None) -> tuple[HeldMembership, ...]:
        return organisation_plan(
            roster(wei(), gone, complete=complete),
            known=KNOWN,
            teams=TEAMS,
            departments=DEPARTMENTS,
            memberships=held,
            last_applied=last,
        ).to_leave

    assert plan_for(complete=True, last=LONG_AGO) == held
    assert plan_for(complete=False, last=LONG_AGO) == (held[0],)
    assert plan_for(complete=True, last=None) == (held[0],)


def test_a_lead_changes_hands_only_when_the_sync_appointed_the_one_it_replaces() -> None:
    """Delete this and the sync replaces a lead an administrator appointed, or never replaces the
    one it appointed itself, or stands a lead down on a roster that did not promise completeness."""
    new_leads = roster(wei(), StaffRecord("new@example.test", "New", department="web", leads=True))
    by_sync = HeldLead(department="web", principal_id="u_wei", appointed_by=SYNC)
    by_hand = HeldLead(department="web", principal_id="u_wei", appointed_by="u_admin")

    replaced = organisation_plan(
        new_leads,
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        leads=(by_sync,),
        last_applied=None,
    )
    kept = organisation_plan(
        new_leads,
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        leads=(by_hand,),
        last_applied=None,
    )
    unnamed = [
        organisation_plan(
            roster(wei(), complete=complete),
            known=KNOWN,
            teams=TEAMS,
            departments=DEPARTMENTS,
            leads=(by_sync,),
            last_applied=LONG_AGO,
        ).to_stand_down
        for complete in (True, False)
    ]

    assert (replaced.to_stand_down, replaced.to_appoint) == (
        (by_sync,),
        (Placement(where="web", principal_id="u_new"),),
    )
    assert (kept.to_stand_down, kept.to_appoint) == ((), ())
    assert kept.withheld != ()
    assert unnamed == [(by_sync,), ()]


def test_a_department_two_people_claim_to_lead_gets_neither_and_an_unregistered_one_is_named() -> (
    None
):
    """Delete this and whichever row came first leads a department two rows both claim, or a
    department nobody registered is appointed a lead the page can never show."""
    plan = organisation_plan(
        roster(
            StaffRecord("wei@example.test", "Wei", department="web", leads=True),
            StaffRecord("new@example.test", "New", department="web", leads=True),
            StaffRecord("gone@example.test", "Gone", department="sales", leads=True),
        ),
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        leads=(HeldLead(department="web", principal_id="u_wei", appointed_by=SYNC),),
        last_applied=LONG_AGO,
    )

    assert plan.to_appoint == () and plan.to_stand_down == ()
    assert plan.contested == ("web",)
    assert plan.unregistered == ("sales",)


def test_teams_and_leads_are_read_from_active_people_in_their_own_department() -> None:
    """`teams_from` and `leads_from`. Delete this and a team slug is read against the wrong
    department, a leaver is placed, or a person placed in a team with no department is accepted."""
    people = roster(
        wei("design"),
        StaffRecord(
            "gone@example.test", "Gone", department="finance", teams=("payroll",), active=False
        ),
        StaffRecord("new@example.test", "New", department="finance", leads=True),
    )

    assert teams_from(people) == {"wei@example.test": ("web.design",)}
    assert leads_from(people) == {"finance": ("new@example.test",)}
    try:
        StaffRecord("x@example.test", "X", teams=("design",))
    except ValueError:
        pass
    else:
        raise AssertionError("a team with no department was accepted")


# ------------------------------------------------------------ a source's spelling of a department
def test_a_department_the_source_spells_its_own_way_is_matched_to_the_registered_one() -> None:
    """Lark says `Web Development`, the install's slug is `web`, registered under that name: the
    team and the lead are the registered department's. Delete this and a department whose name
    has a space in it places nobody, which is what the plan did until 2026-09-29."""
    people = (
        StaffRecord("wei@example.test", "Wei", department="Web Development", teams=("design",)),
        StaffRecord("new@example.test", "New", department="web  development", leads=True),
    )
    matched = organisation_plan(
        roster(*people),
        known=KNOWN,
        teams=TEAMS,
        departments=DEPARTMENTS,
        last_applied=None,
        slug_of=registered_by_name({"web": "Web Development", "finance": "Finance"}),
    )
    spelled = organisation_plan(
        roster(*people), known=KNOWN, teams=TEAMS, departments=DEPARTMENTS, last_applied=None
    )

    assert matched.to_join == (Placement(where="web.design", principal_id="u_wei"),)
    assert matched.to_appoint == (Placement(where="web", principal_id="u_new"),)
    assert matched.unregistered == ()
    assert spelled.to_join == ()
    assert set(spelled.unregistered) == {"Web Development.design", "web  development"}


def test_a_name_becomes_a_slug_of_its_words_and_a_name_with_none_a_digest() -> None:
    """Held against slugs written out here rather than against the function. Delete this and a
    Chinese department name, or one starting with a year, becomes a slug the type refuses and the
    founding fails for the whole press."""
    assert department_slug("Web Development") == "web_development"
    assert department_slug("R&D  / Labs") == "r_d_labs"
    assert department_slug("2024 Interns") == "department_2024_interns"
    chinese = department_slug("设计部")
    assert chinese.startswith("department_") and len(chinese) == len("department_") + 8
    assert department_slug("设计部") == chinese
    assert department_slug("设计部") != department_slug("市场部")
    assert len(department_slug("A very long department name " * 5)) <= SLUG_CHARS
    # One letter matches the slug grammar and is refused by the department type, which wants two.
    assert department_slug("x").startswith("department_")
    for name in ("Web Development", "R&D", "2024 Interns", "设计部", "x"):
        assert re.fullmatch(SLUG_PATTERN, department_slug(name)), name
        founded(department_slug(name), name)


def test_what_is_offered_leaves_out_every_registered_name_and_numbers_a_taken_slug() -> None:
    """A name a registered department answers to is not offered again, two spellings of one name
    are one department, and a slug already taken is numbered. Delete this and a second press
    founds `Finance` twice, or two departments get one slug and the second press fails."""
    registered = {"finance": "Finance", "web": "Web"}
    named = departments_to_found(
        ["Finance", "FINANCE", "Web Dev", "web  dev", "Web!", "Design", " "],
        registered,
        registered_by_name(registered),
    )

    # `Web!` is not how the registered `web` is spelled, so it is offered, and numbered because
    # its slug is taken; `Finance` and `FINANCE` are one name a registered department answers to.
    assert [(one.name, one.slug) for one in named.to_found] == [
        ("Design", "design"),
        ("Web Dev", "web_dev"),
        ("Web!", "web_2"),
    ]
    assert named.registered == ("FINANCE",)
    numbered = departments_to_found(["Web-Dev", "Web Dev"], {"web_dev": "Web development team"}, {})
    assert [one.slug for one in numbered.to_found] == ["web_dev_2", "web_dev_3"]
