"""Departments, teams and who belongs to each: which a reader is shown, and that nothing is counted.

Every narrowing here is somebody else's decision composed, so each test holds one of the three
halves apart: the department headings are the Scopes screen's, the people are the People screen's,
and a team rides on its department. Grants are spelled out rather than read off the registry, for
`tests/unit/test_govern_routes.py`' reason: read off it, a repointed screen would move both sides.

Task ids: M27.7.4
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.console.organisation import (
    ORGANISATION_ROWS,
    ORGANISING_AUTHORITY,
    Department,
    Lead,
    Member,
    Membership,
    Organisation,
    Team,
    may_appoint,
    may_organise,
    may_place,
    organisation,
    organisation_gaps,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 1, tzinfo=UTC)

WHOLE = Scope.unrestricted()
WEB = Scope.department("web")

DEPARTMENTS = (Department(slug="finance", name="Finance"), Department(slug="web", name="Web"))
TEAMS = (
    Team(department="web", slug="projects", name="Projects"),
    Team(department="web", slug="design", name="Design"),
    Team(department="finance", slug="payroll", name="Payroll"),
)
MEMBERS = (
    Member(principal_id="u_2", display_name="Wei Ling", department="web", disabled=False),
    Member(principal_id="u_1", display_name="Aaron", department="web", disabled=True),
    Member(principal_id="u_3", display_name="Grace", department="finance", disabled=False),
    Member(principal_id="u_4", display_name="Nobody placed", department=None, disabled=False),
    Member(principal_id="u_5", display_name="Typo", department="webb", disabled=False),
)


def grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


def reader(*grants: Grant) -> EntitlementSet:
    return EntitlementSet(principal_id="u_reader", grants=grants)


CONFIGURATION = grant(plane_capability(Plane.CONFIGURATION).value)

#: Both screens, company-wide.
EVERYTHING = reader(grant("read:scope"), grant("read:grant"), CONFIGURATION)
#: Both screens, in web only.
WEB_ONLY = reader(grant("read:scope", WEB), grant("read:grant", WEB), CONFIGURATION)
#: The departments and nobody in them.
HEADINGS_ONLY = reader(grant("read:scope"), CONFIGURATION)


def shown(entitlement: EntitlementSet) -> Organisation:
    return organisation(DEPARTMENTS, TEAMS, MEMBERS, entitlement, NOW)


def test_a_company_wide_reader_sees_every_department_its_teams_and_its_people() -> None:
    """M27.7.4, the positive case every narrowing below needs. Delete this and each of them is
    satisfied by a function that returns nothing at all; and the order of people and teams can
    vary between two readings of an unchanged directory."""
    page = shown(EVERYTHING)

    assert [line.slug for line in page.departments] == ["finance", "web"]
    web = page.departments[1]
    assert web.name == "Web"
    assert [team.slug for team in web.teams] == ["design", "projects"]
    assert [one.principal_id for one in web.members] == ["u_1", "u_2"]
    assert web.members[0].disabled is True
    assert [one.principal_id for one in page.departments[0].members] == ["u_3"]


def test_a_department_reader_sees_their_department_and_no_other_name_anywhere_on_the_page() -> None:
    """The Scopes screen's decision over the headings and the People screen's over the rows.
    Delete this and a web admin is handed finance's heading, its teams and its people, which is
    the org chart `govern_surfaces.departments_offered` exists not to hand over; or a person in no
    department, or in one nobody registered, reaches a reader whose grant names a department."""
    page = shown(WEB_ONLY)

    assert [line.slug for line in page.departments] == ["web"]
    assert [team.slug for team in page.departments[0].teams] == ["design", "projects"]
    assert [one.principal_id for one in page.departments[0].members] == ["u_1", "u_2"]
    assert page.unplaced == ()


def test_people_need_the_people_screens_read_on_the_console_plane_and_headings_do_not() -> None:
    """`may_name_people` is `permitted`, the capability and the plane together. Delete this and a
    reader of the Scopes screen alone is handed a directory of people, or one holding the People
    read with only the existence plane is, which a bare `scope_for` check lets through; and the
    headings would vanish for a reader who may see departments and not people."""
    headings = shown(HEADINGS_ONLY)
    existence_only = shown(
        reader(
            grant("read:scope"),
            grant("read:grant"),
            grant(plane_capability(Plane.EXISTENCE).value),
        )
    )

    assert [line.slug for line in headings.departments] == ["finance", "web"]
    assert all(line.members == () for line in headings.departments)
    assert headings.unplaced == ()
    assert [line.slug for line in existence_only.departments] == ["finance", "web"]
    assert all(line.members == () for line in existence_only.departments)
    assert existence_only.unplaced == ()


def test_somebody_in_no_department_or_an_unregistered_one_reaches_only_a_company_wide_reader() -> (
    None
):
    """`govern.NOWHERE` fails closed. Delete this and a person whose row names no department, or a
    department nobody registered, disappears from the one page an administrator opens to find
    them; or appears under a heading, which would put an unregistered name on the page."""
    page = shown(EVERYTHING)

    assert [(one.principal_id, one.department) for one in page.unplaced] == [
        ("u_4", None),
        ("u_5", "webb"),
    ]
    assert all(
        one.principal_id not in {"u_4", "u_5"} for line in page.departments for one in line.members
    )


def test_a_person_whose_department_is_registered_and_not_offered_is_nowhere_on_the_page() -> None:
    """A reader may hold the People read wider than the Scopes read. Delete this and a finance
    person is listed among the unplaced for a web-scoped department reader with a wide People
    grant, with `finance` beside their name: the heading withheld and the name printed anyway."""
    page = organisation(
        DEPARTMENTS,
        TEAMS,
        MEMBERS,
        reader(grant("read:scope", WEB), grant("read:grant"), CONFIGURATION),
        NOW,
    )

    assert [line.slug for line in page.departments] == ["web"]
    assert all(one.department != "finance" for one in page.unplaced)


def test_no_row_on_the_page_can_carry_a_count() -> None:
    """Delete this and a `headcount` field added to a department line passes review, which is the
    subtraction CLAUDE.md names: every list here is narrowed to the reader."""
    assert organisation_gaps() == ()

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Counted:
        hidden_count: int

    assert organisation_gaps(rows=(*ORGANISATION_ROWS, Counted)) != ()


# ---------------------------------------------------------------- members, leads, writes

MEMBERSHIPS = (
    Membership(department="web", team="design", principal_id="u_2"),
    Membership(department="web", team="design", principal_id="u_3"),
    Membership(department="web", team="projects", principal_id="u_9"),
)
LEADS = (Lead(department="web", principal_id="u_3"), Lead(department="finance", principal_id="u_3"))


def placed_page(entitlement: EntitlementSet) -> Organisation:
    return organisation(
        DEPARTMENTS, TEAMS, MEMBERS, entitlement, NOW, memberships=MEMBERSHIPS, leads=LEADS
    )


def test_a_teams_members_and_a_lead_are_listed_for_a_reader_who_may_name_them() -> None:
    """M27.7.4, who belongs to each. Delete this and a team lists nobody when its members are
    recorded, a membership naming somebody no row carries puts an id on the page, or a lead is
    dropped for the reader who may see them."""
    page = placed_page(EVERYTHING)
    web = page.departments[1]

    assert [(team.slug, [one.principal_id for one in team.members]) for team in web.teams] == [
        ("design", ["u_3", "u_2"]),
        ("projects", []),
    ]
    assert web.lead is not None and web.lead.principal_id == "u_3"
    assert page.departments[0].lead is not None


def test_a_member_or_lead_the_reader_may_not_name_reads_as_nobody() -> None:
    """The People screen's decision wherever a person appears. Delete this and a web reader sees
    Grace from finance in web's design team, or as web's lead, which names somebody the People
    screen withholds from them; and the page would differ between a withheld person and none."""
    web = placed_page(WEB_ONLY).departments[0]
    headings = placed_page(HEADINGS_ONLY).departments[1]

    assert [one.principal_id for one in web.teams[0].members] == ["u_2"]
    assert web.lead is None
    assert headings.teams[0].members == () and headings.lead is None


def test_organising_takes_the_grant_authority_over_the_department_and_the_person() -> None:
    """`may_organise`, both rows. Delete this and a web organiser places somebody from finance, one
    holding the authority only in finance places anybody in web, or somebody in no department is
    placed by anybody short of company-wide."""
    web_organiser = reader(grant("approve:grant", WEB))
    everywhere = reader(grant("approve:grant"))
    wei, grace, nobody = MEMBERS[0], MEMBERS[2], MEMBERS[3]

    assert may_organise(web_organiser, department="web", person=wei, now=NOW) is True
    assert may_organise(web_organiser, department="web", person=grace, now=NOW) is False
    assert may_organise(web_organiser, department="finance", person=wei, now=NOW) is False
    assert may_organise(web_organiser, department="web", person=nobody, now=NOW) is False
    assert may_organise(everywhere, department="web", person=nobody, now=NOW) is True
    assert may_organise(reader(grant("read:grant")), department="web", person=wei) is False
    assert screen("access_review").read.requires == ORGANISING_AUTHORITY


def test_nobody_places_a_disabled_person_or_appoints_themselves() -> None:
    """`may_place` and `may_appoint`. Delete this and a disabled account is listed as somebody at
    work, or somebody chooses who reviews their own access; and the positive half proves neither
    refuses everybody."""
    everywhere = EntitlementSet(principal_id="u_2", grants=(grant("approve:grant"),))
    aaron, wei = MEMBERS[1], MEMBERS[0]
    other = Member(principal_id="u_7", display_name="Seven", department="web", disabled=False)

    assert may_place(everywhere, department="web", person=aaron, now=NOW) is False
    assert may_place(everywhere, department="web", person=wei, now=NOW) is True
    assert may_appoint(everywhere, department="web", person=wei, now=NOW) is False
    assert may_appoint(everywhere, department="web", person=other, now=NOW) is True
    assert may_appoint(everywhere, department="web", person=aaron, now=NOW) is False
