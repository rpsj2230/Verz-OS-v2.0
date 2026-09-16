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
    Department,
    Member,
    Organisation,
    Team,
    organisation,
    organisation_gaps,
)
from brain.console.reads import Plane, plane_capability
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
