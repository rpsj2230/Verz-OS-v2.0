"""A department's console: who is given it, what it offers, and the proof that it shows less.

M27.7.29 is "the same screens at department scope, proved by a department-scoped person opening
them and seeing less, with no screen whose subject is the installation offered at all". Three
halves, and this file holds each:

**Who is given it.** `brain.console.department_console.console_for` over grants alone, with the
plane's scope asked beside the capability's, and the menu failing closed for a reader who holds
nothing across the install. Driven through the real application as well, because a decision no
route serves is the state this leaf started in.

**What it offers.** SCREEN 2's entries, narrowed by `brain.console.screens.for_department`, with
no Install screen in the declaration, in the answer or in the function that narrows it.

**Seeing less.** A department-scoped reader opens every screen the department console offers,
through the decision the route behind that screen hands its rows and its reach to, with rows
placed in two departments. The rows are built in memory because this repository has no
PostgreSQL; what is proved is each screen's own narrowing, which is where a department's rows
are chosen, and every route's own tests already hold that the route calls it.

**These tests do not depend on the change to `brain.console.reads.permitted` that makes a plane
grant count only over its own scope.** Every fixture here holds the plane grants in the same scope
as the capability grants, so `permitted` answers the same under either reading, and the one test
that separates the two scopes asks `console_for`, which reads both scopes itself.

Task ids: M27.7.29
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.adoption import Asked
from brain.agent_routes import roster
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    visible_agent_ids,
)
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.connector_trust import trust_rows
from brain.console.department_console import (
    DEPARTMENT_NAVIGATION,
    ConsoleKind,
    ConsoleNavigation,
    Entry,
    console_for,
    departments_held,
)
from brain.console.govern import people
from brain.console.govern_estate import learning_review, library_rows, spans_departments
from brain.console.operate import unattended_running
from brain.console.questions_view import questions_for_reader
from brain.console.reach_view import TierThreeRouting
from brain.console.reads import Plane, permitted, plane_capability
from brain.console.screens import SCREENS, Group, for_department, screen
from brain.console.usage_screen import usage_for_reader
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.knowledge.visibility import Visibility
from brain.navigation_routes import NavigationView
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_connector_trust import a_registered
from tests.unit.test_govern import placed_grant
from tests.unit.test_govern_estate import a_library_item

REPO = Path(__file__).resolve().parents[2]

#: Pinned far from any wall clock, for `CLAUDE.md`'s reason about a fixture with a date in it.
NOW = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)

MAINTENANCE = "maintenance"
FINANCE = "finance"
IN_MAINTENANCE = Scope.department(MAINTENANCE)
WHOLE = Scope.unrestricted()

#: What a run or a connector is placed in, which is no department at all.
NO_DEPARTMENT = "(no department)"

NAVIGATION_PATH = f"{API_PREFIX}/console/navigation"

#: When the grants on the People screen were written, before `NOW` so each is a holding.
GRANTED_AT = NOW - timedelta(days=30)


def every_screen(
    scope: Scope, *, planes: Scope | None = None, pid: str = "u_reader"
) -> EntitlementSet:
    """Every registered screen's capability and all three console planes, in one scope each.

    The shape of a department admin who was given the whole console for one department, and of a
    company administrator when the scope is unrestricted. `planes` defaults to the same scope,
    which is what keeps these tests independent of how `permitted` compares the two.
    """
    capabilities = sorted({one.read.requires.value for one in SCREENS})
    grants = [Grant(capability=Capability(value=one), scope=scope) for one in capabilities]
    grants += [
        Grant(capability=plane_capability(one), scope=planes if planes is not None else scope)
        for one in Plane
    ]
    return EntitlementSet(principal_id=pid, grants=tuple(grants))


def holding(*capabilities: str, scope: Scope, planes: Scope | None = None) -> EntitlementSet:
    """These capabilities in one scope, and all three planes in `planes` or the same scope."""
    grants = [Grant(capability=Capability(value=one), scope=scope) for one in capabilities]
    grants += [
        Grant(capability=plane_capability(one), scope=planes if planes is not None else scope)
        for one in Plane
    ]
    return EntitlementSet(principal_id="u_reader", grants=tuple(grants))


def entry_keys(navigation: ConsoleNavigation) -> list[str]:
    return [one.key for section in navigation.sections for one in section.entries]


# ----------------------------------------------------------------------------- who is given it


def test_a_reader_holding_every_screen_in_one_department_is_given_that_departments_console() -> (
    None
):
    """The positive case the whole leaf is for. Delete this and `console_for` can return the
    company console to everybody, which is every refusal below satisfied by a function that
    never offers a department anything."""
    decided = console_for(every_screen(IN_MAINTENANCE), NOW)

    assert decided.kind is ConsoleKind.DEPARTMENT
    assert decided.departments == (MAINTENANCE,)
    assert [one.heading for one in decided.sections] == ["Operate", "Govern", "Report"]
    assert [[one.label for one in section.entries] for section in decided.sections] == [
        ["Department", "Live runs", "Connectors"],
        ["People and grants", "Agents and leashes", "Knowledge", "Skills", "Learning"],
        ["Gaps", "Usage"],
    ]


def test_a_reader_holding_one_screen_across_the_install_is_given_the_company_console() -> None:
    """One unrestricted screen is enough, and the company console carries no menu and names no
    department, because its menu is the shell's own and identical for everybody given it.

    Built without a second grant of the same capability, because `EntitlementSet.scope_for`
    intersects the scopes of every grant covering one capability: holding `read:release` in
    maintenance and across the install is holding it in maintenance, and is a department's.

    Delete this and a company administrator whose other grants happen to be scoped is sent a
    department's console with every screen about the install missing from it."""
    scoped = every_screen(IN_MAINTENANCE, planes=WHOLE)
    plus_one = EntitlementSet(
        principal_id="u_reader",
        grants=(
            *(one for one in scoped.grants if one.capability.value != "read:release"),
            Grant(capability=Capability(value="read:release"), scope=WHOLE),
        ),
    )
    twice = EntitlementSet(
        principal_id="u_reader",
        grants=(*scoped.grants, Grant(capability=Capability(value="read:release"), scope=WHOLE)),
    )

    assert console_for(plus_one, NOW) == ConsoleNavigation(kind=ConsoleKind.COMPANY)
    assert console_for(every_screen(WHOLE), NOW) == ConsoleNavigation(kind=ConsoleKind.COMPANY)
    assert console_for(twice, NOW).kind is ConsoleKind.DEPARTMENT


def test_a_screen_held_everywhere_with_its_plane_held_in_one_department_is_a_departments() -> None:
    """The plane half. `read:grant` over everything with the configuration plane in one department
    reads configuration only there, so the reader is a department's. The sibling with the plane
    unrestricted is the company's.

    Delete this and `held_across_the_install` can ask the capability's scope alone, which gives
    the company console, and every install screen in it, to a reader whose console grant was
    written for one department."""
    narrow_plane = holding("read:grant", scope=WHOLE, planes=IN_MAINTENANCE)
    wide_plane = holding("read:grant", scope=WHOLE, planes=WHOLE)

    assert console_for(narrow_plane, NOW).kind is ConsoleKind.DEPARTMENT
    assert console_for(narrow_plane, NOW).departments == (MAINTENANCE,)
    assert console_for(wide_plane, NOW).kind is ConsoleKind.COMPANY


def test_only_a_plane_that_admits_the_screen_can_make_it_the_installs() -> None:
    """The existence plane held across the install admits no configuration screen. `read:grant`
    over everything, the existence plane over everything and the configuration plane in one
    department is a department's reader of People and grants.

    Delete this and the planes asked can be every plane held rather than the ones that admit the
    screen, and an existence grant across the install, which is an auditor's shape, turns a
    department's configuration grant into the company console."""
    reader = EntitlementSet(
        principal_id="u_reader",
        grants=(
            Grant(capability=Capability(value="read:grant"), scope=WHOLE),
            Grant(capability=plane_capability(Plane.EXISTENCE), scope=WHOLE),
            Grant(capability=plane_capability(Plane.CONFIGURATION), scope=IN_MAINTENANCE),
        ),
    )

    decided = console_for(reader, NOW)
    assert decided.kind is ConsoleKind.DEPARTMENT
    assert decided.departments == (MAINTENANCE,)
    assert entry_keys(decided) == ["people"]


def test_a_reader_holding_nothing_is_given_an_empty_department_console_not_the_companys() -> None:
    """The menu fails closed. A reader who holds no screen gets a department console with no
    section and no department named, never the company console.

    Delete this and the default can become the company console, which offers every screen about
    this server to somebody the API has not said may see any."""
    nobody = EntitlementSet(principal_id="u_reader", grants=())

    assert console_for(nobody, NOW) == ConsoleNavigation(kind=ConsoleKind.DEPARTMENT)


def test_a_section_with_nothing_offered_in_it_is_dropped_rather_than_shown_empty() -> None:
    """`read:usage` in one department reaches Usage and Service levels, and Service levels is
    withheld from a department, so the menu is one Report heading with one entry.

    Delete this and a heading can be left with nothing under it, which tells the reader there are
    screens there they may not open, the count of hidden things written as a word."""
    decided = console_for(holding("read:usage", scope=IN_MAINTENANCE), NOW)

    assert [one.heading for one in decided.sections] == ["Report"]
    assert entry_keys(decided) == ["usage"]


def test_the_departments_named_are_read_off_the_readers_own_grants() -> None:
    """A department clause's value is named, both values of an IN clause are, and a clause on some
    other field names nothing. The plane's scope counts as well as the capability's.

    Delete this and the department list can be read from somewhere other than the reader's grants,
    and the one list that names departments on the console names departments the reader holds
    nothing in."""
    two = Scope(clauses=(Clause(field="department", op=Op.IN, value=(FINANCE, MAINTENANCE)),))
    by_prefix = Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="main"),))
    by_client = Scope(clauses=(Clause(field="client_id", op=Op.EQ, value="447"),))
    people_screen = [screen("people")]

    assert departments_held(people_screen, holding("read:grant", scope=two), NOW) == (
        FINANCE,
        MAINTENANCE,
    )
    assert departments_held(people_screen, holding("read:grant", scope=by_client), NOW) == ()
    assert departments_held(people_screen, holding("read:grant", scope=by_prefix), NOW) == ()
    assert departments_held(
        people_screen, holding("read:grant", scope=WHOLE, planes=IN_MAINTENANCE), NOW
    ) == (MAINTENANCE,)
    assert departments_held(people_screen, EntitlementSet(principal_id="u", grants=()), NOW) == ()


def test_the_navigation_has_three_fields_and_none_of_them_counts_anything() -> None:
    """Delete this and a `withheld` or a `total` can be added beside the sections, and the menu
    publishes how much of the console the reader was not given."""
    assert [one.name for one in fields(ConsoleNavigation)] == ["kind", "departments", "sections"]
    assert set(NavigationView.model_fields) == {"console", "departments", "sections"}


# ------------------------------------------------------------------------------ what it offers


def test_no_screen_whose_subject_is_the_installation_is_offered_to_a_department() -> None:
    """The last clause of M27.7.29, held three ways that must agree: the declaration names no
    Install screen, an entry naming one cannot be built, and `for_department` drops the group for
    a reader holding every Install capability in their department.

    Delete this and an Install screen can be added to the department's menu, or `for_department`
    can offer the group again, with the served menu still looking right because the declaration
    happens not to name it."""
    install = {one.key for one in SCREENS if one.group is Group.INSTALL}
    assert install == {"install", "updates", "recovery", "limits", "connections"}

    declared = {one.key for section in DEPARTMENT_NAVIGATION for one in section.entries}
    assert not declared & install

    with pytest.raises(ValueError, match="subject is the installation"):
        Entry(label="This install", key="install", to="/install")

    reader = every_screen(IN_MAINTENANCE)
    assert not {one.key for one in for_department(reader, NOW)} & install
    assert not set(entry_keys(console_for(reader, NOW))) & install


def test_every_entry_opens_an_address_the_console_routes() -> None:
    """Each entry's address is a path in `console/src/App.tsx`. Read from the route table rather
    than typed, so an entry cannot point at a page nobody routes.

    Delete this and the department's menu can link to the console's own not-found page, which
    reads to a department admin as a screen that exists and refuses them."""
    table = (REPO / "console" / "src" / "App.tsx").read_text(encoding="utf-8")
    routed = set(re.findall(r'path:\s*"([^"]*)"', table))

    for section in DEPARTMENT_NAVIGATION:
        for entry in section.entries:
            assert entry.to.lstrip("/") in routed, entry.to


# --------------------------------------------------------------------------- over the wire

NAVIGATION_GRANTS: dict[str, EntitlementSet] = {
    "u_narrow": every_screen(IN_MAINTENANCE, pid="u_narrow"),
    "u_wide": every_screen(WHOLE, pid="u_wide"),
    "u_none": EntitlementSet(principal_id="u_none", grants=()),
}


class NavigationStore:
    """A `brain.gate.resolve.EntitlementStore` over `NAVIGATION_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return NAVIGATION_GRANTS[principal_id]


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The real application, so the route is proved mounted as well as correct."""
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer="https://id.verz.example/realms/brain",
                audience="brain-api",
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=NavigationStore(),
            cache=NoCache(),
        )
        yield c


def ask(c: TestClient, pid: str) -> Response:
    token = token_for(pid, claims={"amr": ["otp"]})
    response: Response = c.get(NAVIGATION_PATH, headers={"authorization": f"Bearer {token}"})
    return response


def test_the_route_answers_each_reader_the_console_their_grants_give_them(
    client: TestClient,
) -> None:
    """A department-scoped reader is answered their department's console, and the body names no
    Install screen and no address about the server anywhere in it. An install-wide reader is
    answered the company console with nothing else. A reader holding nothing is answered, not
    refused.

    Delete this and the decision can be correct and unserved, which is the state
    `brain.console.screens.navigation` was in when this leaf was written."""
    narrow = ask(client, "u_narrow")
    wide = ask(client, "u_wide")
    none = ask(client, "u_none")

    assert narrow.status_code == 200
    body = narrow.json()
    assert body["console"] == "department"
    assert body["departments"] == [MAINTENANCE]
    served = [one["key"] for section in body["sections"] for one in section["entries"]]
    assert served == [
        "overview",
        "runs",
        "connectors",
        "people",
        "agents",
        "library",
        "skills",
        "learning",
        "questions",
        "usage",
    ]
    for word in ("install", "updates", "recovery", "limits", "connections", "storage", "features"):
        assert f'"/{word}"' not in narrow.text

    assert wide.json() == {"console": "company", "departments": [], "sections": []}
    assert none.status_code == 200
    assert none.json() == {"console": "department", "departments": [], "sections": []}


# ---------------------------------------------------------------------------- seeing less


def maintenance_reader() -> EntitlementSet:
    return every_screen(IN_MAINTENANCE, pid="u_maintenance")


def company_reader() -> EntitlementSet:
    return every_screen(WHOLE, pid="u_company")


def open_people(reader: EntitlementSet) -> frozenset[str]:
    """People and grants: the department each subject shown sits in."""
    sits = {"principal:u_m": MAINTENANCE, "principal:u_f": FINANCE}
    holdings = [
        placed_grant(
            "read:client", department=MAINTENANCE, subject_id="u_m", granted_at=GRANTED_AT
        ),
        placed_grant("read:client", department=FINANCE, subject_id="u_f", granted_at=GRANTED_AT),
    ]
    return frozenset(sits[one.subject] for one in people(holdings, reader, NOW))


def open_library(reader: EntitlementSet) -> frozenset[str]:
    """Knowledge: the department each item shown sits in."""
    sits = {"k_m": MAINTENANCE, "k_f": FINANCE}
    items = [
        a_library_item("k_m", department=MAINTENANCE),
        a_library_item("k_f", department=FINANCE),
    ]
    return frozenset(sits[one.item_id] for one in library_rows(items, reader, NOW))


def _question(trace: str, *, person: str, department: str) -> Asked:
    return Asked(
        trace_id=trace,
        principal_id=person,
        principal_kind=PrincipalKind.HUMAN,
        channel=Channel.CONSOLE,
        department=department,
        at=NOW - timedelta(hours=1),
    )


def open_usage(reader: EntitlementSet) -> frozenset[str]:
    """Usage, and the Department page's usage card: the departments on the table, and the
    department of every person on the other table."""
    sits = {"u_m": MAINTENANCE, "u_f": FINANCE}
    asked = (
        _question("t1", person="u_m", department=MAINTENANCE),
        _question("t2", person="u_f", department=FINANCE),
    )
    shown = usage_for_reader(
        asked,
        (FINANCE, MAINTENANCE),
        reader,
        start=NOW - timedelta(days=7),
        end=NOW,
        now=NOW,
    )
    seen = {one.department for one in shown.departments or ()}
    seen |= {sits[one.person] for one in shown.people or ()}
    return frozenset(seen)


def open_runs(reader: EntitlementSet) -> frozenset[str]:
    """Live runs: a scheduled control belongs to no department, so any row is placed nowhere."""
    started = [("retention_sweep", NOW - timedelta(minutes=3), False)]
    return frozenset(NO_DEPARTMENT for _ in unattended_running(started, (), reader, NOW))


def open_connectors(reader: EntitlementSet) -> frozenset[str]:
    """Connectors: a source is placed by its own name and never in a department."""
    return frozenset(NO_DEPARTMENT for _ in trust_rows([a_registered("laravel")], reader, now=NOW))


def open_learning(reader: EntitlementSet) -> frozenset[str]:
    """Learning: the departments the tier-three routings shown name."""
    desk = "desk"
    review = learning_review(
        basis=spans_departments(reader, NOW),
        visible={desk},
        tier_one={},
        tier_two={},
        tier_three={
            desk: (
                TierThreeRouting(
                    memory_id="m_m", department=MAINTENANCE, back_to="agent:desk/learning"
                ),
                TierThreeRouting(
                    memory_id="m_f", department=FINANCE, back_to="agent:desk/learning"
                ),
            )
        },
    )
    return frozenset(one.department for one in review.tier_three or ())


def _agents() -> tuple[AgentRecord, ...]:
    def one(agent_id: str, department: str) -> AgentRecord:
        return AgentRecord(
            agent_id=agent_id,
            display_name=agent_id,
            persona="Answers in the house voice.",
            audience=AgentAudience(
                level=Visibility.DEPARTMENT, owner_id="u_steward", department=department
            ),
            authority=AgentAuthority(),
            created_by="u_steward",
        )

    return (one("maintenance_desk", MAINTENANCE), one("finance_desk", FINANCE))


def open_agents(viewer: AgentViewer, reader: EntitlementSet) -> frozenset[str]:
    """Agents and leashes: the department each agent on the roster belongs to."""
    page = roster(_agents(), viewer, ceilings=permitted(screen("agents").read, reader, NOW))
    return frozenset(one.department or NO_DEPARTMENT for one in page.items)


def open_skills(viewer: AgentViewer, reader: EntitlementSet) -> frozenset[str]:
    """Skills: the skills listed are the pins of the agents this viewer may see, so the departments
    are those agents'. The screen's own grant is asked first, as the route asks it."""
    if not permitted(screen("skills").read, reader, NOW):
        return frozenset()
    records = _agents()
    visible = visible_agent_ids(records, viewer)
    return frozenset(one.audience.department for one in records if one.agent_id in visible)


def open_questions(reader: EntitlementSet) -> frozenset[str]:
    """Gaps: whether every question is answered with nothing connected, which is one fact about
    the install, the same for every department, and names no department on the screen."""
    shown = questions_for_reader(connected=False, entitlement=reader, now=NOW)
    return frozenset(
        str(getattr(shown, one.name)) for one in fields(shown) if one.name == "department"
    )


MAINTENANCE_PERSON = AgentViewer(principal_id="u_maintenance", departments=frozenset({MAINTENANCE}))
FINANCE_PERSON = AgentViewer(principal_id="u_finance", departments=frozenset({FINANCE}))

#: How each screen the department console offers is opened, and by whom the positive half is
#: seen. Agents and Skills are decided by audience rather than by grant, so their other reader is
#: a person in the other department rather than a company administrator, which is
#: `brain.agent_routes.AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES`.
OPENERS: dict[
    str,
    tuple[Callable[[EntitlementSet], frozenset[str]], Callable[[EntitlementSet], frozenset[str]]],
] = {
    "overview": (open_usage, open_usage),
    "runs": (open_runs, open_runs),
    "connectors": (open_connectors, open_connectors),
    "people": (open_people, open_people),
    "agents": (
        lambda reader: open_agents(MAINTENANCE_PERSON, reader),
        lambda reader: open_agents(FINANCE_PERSON, reader),
    ),
    "library": (open_library, open_library),
    "skills": (
        lambda reader: open_skills(MAINTENANCE_PERSON, reader),
        lambda reader: open_skills(FINANCE_PERSON, reader),
    ),
    "learning": (open_learning, open_learning),
    "questions": (open_questions, open_questions),
    "usage": (open_usage, open_usage),
}

#: The one screen whose only fact is the same for every department, so seeing less is not
#: possible on it and the proof is that it names no department at all.
THE_SAME_FOR_EVERY_DEPARTMENT = frozenset({"questions"})


def test_every_screen_the_department_console_offers_has_a_way_to_open_it_here() -> None:
    """Read off the declaration, so an entry added to the department's menu is a screen this file
    has to open. Delete this and the proof below covers the screens somebody remembered."""
    assert set(OPENERS) == {one.key for section in DEPARTMENT_NAVIGATION for one in section.entries}


@pytest.mark.parametrize("key", sorted(OPENERS))
def test_a_department_scoped_person_opening_a_shared_screen_sees_only_their_department(
    key: str,
) -> None:
    """**The proof M27.7.29 asks for.** The same rows, placed in two departments or in none, opened
    by a person who holds every screen in maintenance and by one who sees the other half. The
    maintenance reader is shown nothing placed in another department and nothing placed nowhere,
    and the other reader is shown something the maintenance reader was not, so this is not
    passing because the screen shows nobody anything. The Department page is its usage card.

    Delete this and a screen in the department's console can show a department admin every
    department's rows, with every menu test still green, because the menu was never the part
    that chose the rows."""
    mine, other = OPENERS[key]
    reader = maintenance_reader()

    assert key in {one.key for one in for_department(reader, NOW)}
    seen = mine(reader)
    assert seen <= {MAINTENANCE}, (key, seen)

    elsewhere = other(company_reader())
    if key in THE_SAME_FOR_EVERY_DEPARTMENT:
        assert seen == elsewhere == frozenset()
        return
    assert elsewhere - seen, (key, elsewhere, seen)


def test_the_proof_would_notice_a_screen_that_showed_a_department_admin_everything() -> None:
    """The proof's own positive control: opened by a company administrator, the People screen
    shows both departments, which is exactly what the assertion above refuses. Delete this and
    the opener could be broken in a way that shows nobody anything, and the proof above would be
    satisfied by it."""
    assert open_people(company_reader()) == {MAINTENANCE, FINANCE}
    assert open_usage(company_reader()) == {MAINTENANCE, FINANCE}
    assert open_library(company_reader()) == {MAINTENANCE, FINANCE}
