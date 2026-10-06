"""The Super Admin's company pages over HTTP: the estate, all activity and the company's spend,
each narrowed by `brain.console.global_surfaces` and refused with the one 404.

Driven through the real application with signed-in people and a stub where the pool is, so every
statement a route makes is answered by a function here or fails the test. The ledger is the audit
route tests' own in-memory `Ledger`, whose rows are real `AuditChain` entries, so the activity
page is decided by `brain.audit.view.AuditView` exactly as on an install. The one statement this
router writes, `spend_between`, is then run against a real PostgreSQL with rows either side of its
window; that half skips without `DATABASE_URL`, and CI always sets it.

**Every refusal has a sibling proving the permitted case is answered**, which is CLAUDE.md's rule
about a guard tested only by its refusals.

Task ids: M33.1.1.1, M33.1.1.2, M33.1.1.3
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql.selectable import Select

from brain import company_routes
from brain.api import API_PREFIX
from brain.audit.view import AuditFilter
from brain.company_routes import (
    ACTIVITY_PATH,
    CONSUMPTION_PATH,
    ESTATE_PATH,
    MAX_SPEND_ROWS,
    CompanyActivityPage,
    ConsumptionView,
    DepartmentSpendView,
    EstateRowView,
    EstateView,
    spend_between,
)
from brain.console.global_surfaces import ESTATE_SCREEN, EstateKind
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.knowledge.visibility import Visibility
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.tables.agent import AgentRow
from brain.tables.skill import SkillRow
from brain.tables.spend import SpendActualRow
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.scratch_postgres import engine, modelled, run
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_audit_routes import PLAN, Ledger, Names, chain_of, stored

ESTATE = f"{API_PREFIX}{ESTATE_PATH}"
ACTIVITY = f"{API_PREFIX}{ACTIVITY_PATH}"
CONSUMPTION = f"{API_PREFIX}{CONSUMPTION_PATH}"
AUDIT = f"{API_PREFIX}/audit"

FINANCE = "finance"
DEPT = Visibility.DEPARTMENT
MAINTENANCE = "maintenance"
EVERYWHERE = Scope.unrestricted()
PLANES = tuple(Grant(capability=plane_capability(one), scope=EVERYWHERE) for one in Plane)

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
BEGAN = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def read(key: str) -> Capability:
    return screen(key).read.requires


def everywhere(*capabilities: Capability | str) -> tuple[Grant, ...]:
    return tuple(
        Grant(
            capability=one if isinstance(one, Capability) else Capability(value=one),
            scope=EVERYWHERE,
        )
        for one in capabilities
    )


def in_maintenance(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.department(MAINTENANCE)) for one in capabilities)


#: `u_admin` reads all four estate screens, the ledger, the budget, the people and the scopes over
#: everything. `u_narrow` reads the agents, the budget and the scopes in maintenance alone, and the
#: whole ledger, but not the People screen, so a department lens names nobody to them.
#: `u_wide` reads the knowledge library and nothing else of the estate. `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        *PLANES,
        *everywhere(
            *(read(ESTATE_SCREEN[kind]) for kind in EstateKind),
            read("audit"),
            "read:audit.*",
            read("budget"),
            read("people"),
            read("scopes"),
        ),
    ),
    "u_narrow": (
        *PLANES,
        *in_maintenance(read("agents"), read("budget"), read("scopes")),
        *everywhere(read("audit"), "read:audit.*"),
    ),
    "u_wide": (*PLANES, *everywhere(read("library"))),
    "u_none": (),
}


# ------------------------------------------------------------------------- the stub


def names_of(statement: Any) -> list[str]:
    if not isinstance(statement, Select):
        return []
    return [str(one["name"]) for one in statement.column_descriptions]


def archived(row: AgentRow) -> AgentRow:
    row.archived_at = BEGAN
    return row


def skill(name: str, owner: str) -> SkillRow:
    return SkillRow(digest=f"{name}-digest", name=name, version="1.0.0", submitted_by=owner)


#: The estate the stub holds: two agents in two departments and an archived third, a skill, a
#: finance document and a live connector.
AGENTS = (
    agent_row(
        "a_finance",
        level=DEPT,
        department=FINANCE,
        owner_id="u_theirs",
        display_name="Finance desk",
    ),
    agent_row(
        "a_maint", level=DEPT, department=MAINTENANCE, owner_id="u_mine", display_name="Maint desk"
    ),
    archived(agent_row("a_gone", level=DEPT, department=MAINTENANCE, owner_id="u_mine")),
)
SKILLS = (Row((skill("summarise", "u_mine"), None)),)
DOCUMENTS = (Row(("k_ledger_policy", "u_theirs", "department", FINANCE, None)),)
CONNECTIONS = (Row(("xero", {}, "d" * 64, "u_mine", BEGAN, None)),)

#: The directory: two people in finance and one in maintenance.
PEOPLE = (
    Row(("u_admin", "Admin", FINANCE, "staff", None)),
    Row(("u_narrow", "Narrow", FINANCE, "staff", None)),
    Row(("u_elsewhere", "Elsewhere", MAINTENANCE, "staff", None)),
)
DEPARTMENTS = (Row((FINANCE, "Finance")), Row((MAINTENANCE, "Maintenance")))


def a_cost(department: str, cost_minor: int, at: datetime) -> SpendActualRow:
    return SpendActualRow(
        principal_id="u_admin",
        principal_kind=PrincipalKind.HUMAN.value,
        traffic=TrafficClass.HUMAN_INTERACTIVE.value,
        department=department,
        agent_id="a_finance",
        model="a-model",
        lane=Lane.ANSWER.value,
        cost_minor=cost_minor,
        at=at,
        trace_id="t-cost-1",
    )


def costs() -> list[SpendActualRow]:
    """Three runs this week and one six weeks ago, which the window must leave out."""
    now = datetime.now(UTC)
    return [
        a_cost(FINANCE, 500, now - timedelta(days=1)),
        a_cost(MAINTENANCE, 200, now - timedelta(days=2)),
        a_cost(MAINTENANCE, 100, now - timedelta(days=3)),
        a_cost(FINANCE, 9_000, now - timedelta(days=42)),
    ]


def answerer(spend: list[SpendActualRow]) -> Callable[[Any], Result | None]:
    def answer(statement: Any) -> Result | None:
        columns = names_of(statement)
        if columns == ["AgentRow"]:
            return Result(AGENTS)
        if columns == ["SkillRow", "SkillReviewRow"]:
            return Result(SKILLS)
        if columns == ["item_id", "owner_id", "visibility", "department", "kind"]:
            return Result(DOCUMENTS)
        if columns[:1] == ["connector"] and "connected_by" in columns:
            return Result(CONNECTIONS)
        if columns == ["id", "display_name", "primary_department", "employment", "disabled_at"]:
            return Result(PEOPLE)
        if columns == ["slug", "name"]:
            return Result(DEPARTMENTS)
        if columns == ["SpendActualRow"]:
            return Result(spend)
        return None

    return answer


@contextmanager
def serving(
    monkeypatch: pytest.MonkeyPatch, spend: list[SpendActualRow] | None = None
) -> Iterator[tuple[TestClient, Stub, Ledger]]:
    monkeypatch.setattr(company_routes, "money_and_clock", lambda: ("SGD", "UTC"))
    ledger = Ledger(rows=[stored(one) for one in chain_of(PLAN)])
    with console_client(GRANTS, routers=(company_routes.router,)) as (client, stub):
        app: Any = client.app
        app.state.audit_ledger = ledger
        app.state.people_names = Names()
        stub.answerers.append(answerer(costs() if spend is None else spend))
        yield client, stub, ledger


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Stub, Ledger]]:
    with serving(monkeypatch) as both:
        yield both


def estate_of(client: TestClient, pid: str, **params: str) -> EstateView:
    response = client.get(ESTATE, params=params, headers=headers(pid))
    assert response.status_code == 200, response.text
    return EstateView.model_validate(response.json())


def activity_of(client: TestClient, pid: str, **params: str) -> CompanyActivityPage:
    response = client.get(ACTIVITY, params=params, headers=headers(pid))
    assert response.status_code == 200, response.text
    return CompanyActivityPage.model_validate(response.json())


def consumption_of(client: TestClient, pid: str) -> ConsumptionView:
    response = get(client, pid, CONSUMPTION)
    assert response.status_code == 200, response.text
    return ConsumptionView.model_validate(response.json())


def refusal(body: Mapping[str, Any]) -> dict[str, Any]:
    found = dict(body)
    assert "trace_id" in found
    found["trace_id"] = "<per request>"
    return found


def ids(view: EstateView) -> list[tuple[str, str]]:
    return [(one.kind.value, one.item_id) for one in view.items]


def actors(page: CompanyActivityPage) -> list[str]:
    return [one.actor_id for one in page.items]


# -------------------------------------------------------------------------- the estate


def test_a_reader_of_all_four_screens_is_shown_every_kind_by_the_words_it_is_known_by(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """The positive case: every live agent, the skill, the document and the connector, each
    labelled as a person knows it, an archived agent left out, and a document labelled by its
    reference rather than its title. Delete this and the estate can refuse everything and pass
    every test about what it must not show."""
    client, _stub, _ledger = served
    view = estate_of(client, "u_admin")

    assert ids(view) == [
        ("agent", "a_finance"),
        ("agent", "a_maint"),
        ("skill", "summarise-digest"),
        ("knowledge", "k_ledger_policy"),
        ("connector", "xero"),
    ]
    assert [one.label for one in view.items] == [
        "Finance desk",
        "Maint desk",
        "summarise 1.0.0",
        "k_ledger_policy",
        "xero",
    ]
    assert view.kinds == list(EstateKind)


def test_a_reader_who_may_open_none_of_the_four_screens_gets_the_one_404_before_any_read(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """The estate opens on any of its four screens and is refused on none of them, with the
    body the Audit screen refuses the same caller with. Delete this and a caller with no grant
    is shown an empty estate, which is a different answer from a refused screen, or the tables
    are read for somebody who will be refused."""
    client, stub, _ledger = served
    refused = get(client, "u_none", ESTATE)
    audit = get(client, "u_none", AUDIT)

    assert refused.status_code == audit.status_code == 404
    assert refusal(refused.json()) == refusal(audit.json())
    assert stub.statements == []


def test_a_reader_of_one_screen_is_shown_that_kind_and_opens_the_estate_on_it(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """A reader holding the library and nothing else is shown the document and no agent, skill
    or connector. Delete this and the gate can ask for the agents screen alone, refusing a
    library reader the estate the leaf says they may filter."""
    client, _stub, _ledger = served

    assert ids(estate_of(client, "u_wide")) == [("knowledge", "k_ledger_policy")]


def test_a_department_lens_narrows_within_what_the_reader_sees_and_never_beyond_it(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """A reader over everything narrowed to finance sees the finance agent and document and
    nothing else. A reader of maintenance alone asking for finance is answered exactly as
    asking for a department that does not exist. Delete this and the lens can run before the
    visibility check, and the estate answers which departments own anything."""
    client, _stub, _ledger = served

    finance = estate_of(client, "u_admin", department=FINANCE)
    unseen = estate_of(client, "u_narrow", department=FINANCE)
    invented = estate_of(client, "u_narrow", department="nobody_here")
    own = estate_of(client, "u_narrow", department=MAINTENANCE)

    assert ids(finance) == [("agent", "a_finance"), ("knowledge", "k_ledger_policy")]
    assert unseen == invented
    assert unseen.items == []
    assert ids(own) == [("agent", "a_maint")]


def test_a_person_lens_and_a_kind_narrow_to_what_they_name(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """The other two narrowings, proved to work rather than to be accepted. Delete this and a
    person or a kind filter can be ignored and the whole estate returned under it."""
    client, _stub, _ledger = served

    mine = estate_of(client, "u_admin", person="u_mine")
    skills = estate_of(client, "u_admin", kind="skill")

    assert ids(mine) == [("agent", "a_maint"), ("skill", "summarise-digest"), ("connector", "xero")]
    assert ids(skills) == [("skill", "summarise-digest")]


def test_the_estate_filters_offer_only_what_the_rows_already_said(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """The departments offered are those of the rows the reader may see, as their Scopes grant
    admits them, and the people are those rows' owners, whatever the lens. Delete this and the
    dropdown can be read from a table and name every department to a reader of one."""
    client, _stub, _ledger = served

    wide = estate_of(client, "u_admin", department=FINANCE)
    narrow = estate_of(client, "u_narrow")

    assert wide.departments == [FINANCE, MAINTENANCE]
    assert wide.people == ["u_mine", "u_theirs"]
    assert set(wide.names) == {"u_mine", "u_theirs"}
    assert narrow.departments == [MAINTENANCE]
    assert narrow.people == ["u_mine"]
    # u_wide sees the finance document and holds no Scopes grant, so no department is offered.
    assert estate_of(client, "u_wide").departments == []


def test_an_estate_row_carries_neither_its_department_nor_its_owner() -> None:
    """A department and an owner together are a predicate with a name in front of it. Delete
    this and a field for either can join the row, which the library screen refuses for its own
    rows."""
    assert set(EstateRowView.model_fields) == {"kind", "item_id", "label"}


# ------------------------------------------------------------------------- the activity


def test_a_reader_of_the_audit_screen_reads_all_activity_newest_first(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """The positive case: every entry the reader may see, newest first, with the actors on the
    page offered and the directory's departments as their Scopes grant admits them. Delete this
    and the page can return nothing and pass every narrowing test."""
    client, _stub, _ledger = served
    page = activity_of(client, "u_admin")

    assert actors(page) == [one[1] for one in reversed(PLAN)]
    assert page.actors == ["u_admin", "u_narrow", "u_elsewhere"]
    assert page.departments == [FINANCE, MAINTENANCE]
    assert page.next_cursor is None
    # u_narrow's Scopes grant names maintenance alone, so finance is not offered to them.
    assert activity_of(client, "u_narrow").departments == [MAINTENANCE]


def test_a_reader_without_the_audit_screen_is_refused_with_the_one_404_before_the_ledger(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """Delete this and the ledger is read for a caller who will be refused, or a caller with no
    audit grant is shown an empty page rather than the refusal a missing screen gets."""
    client, _stub, ledger = served
    refused = get(client, "u_wide", ACTIVITY)
    audit = get(client, "u_wide", AUDIT)

    assert refused.status_code == audit.status_code == 404
    assert refusal(refused.json()) == refusal(audit.json())
    assert ledger.calls == []


def test_a_department_lens_is_that_departments_people_and_a_person_lens_is_that_person(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """Finance is u_admin and u_narrow in the directory, so its activity is theirs and not
    u_elsewhere's; maintenance is u_elsewhere's alone; a person lens is that person's entries,
    and a person named beside a department they are not in is an empty page. Delete this and a
    department lens can be ignored and the whole ledger shown under a department's name."""
    client, _stub, _ledger = served

    finance = activity_of(client, "u_admin", department=FINANCE)
    maintenance = activity_of(client, "u_admin", department=MAINTENANCE)
    one_person = activity_of(client, "u_admin", person="u_narrow")
    outside = activity_of(client, "u_admin", department=MAINTENANCE, person="u_narrow")

    assert set(actors(finance)) == {"u_admin", "u_narrow"}
    assert len(finance.items) == 5
    assert actors(maintenance) == ["u_elsewhere"]
    assert actors(one_person) == ["u_narrow"]
    assert outside.items == []


def test_a_department_the_reader_may_name_nobody_in_answers_as_one_with_nobody_in_it(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """u_narrow reads the whole ledger and may not open the People screen, so asking for
    finance must not tell them who sits there by returning those people's entries. It answers
    exactly as a department that does not exist, without reading the ledger, and the same reader
    with no lens still reads everything. Delete this and the department lens becomes a way to
    learn where a colleague sits from a screen that was told not to say."""
    client, _stub, ledger = served

    finance = activity_of(client, "u_narrow", department=FINANCE)
    invented = activity_of(client, "u_narrow", department="nobody_here")
    calls_before = list(ledger.calls)
    everything = activity_of(client, "u_narrow")

    assert finance == invented
    assert finance.items == []
    assert calls_before == []
    assert len(everything.items) == len(PLAN)


def test_a_search_and_an_order_narrow_and_walk_within_the_lens(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """A search over finance's activity is asked of the rows the lens left, and an order walks
    them the other way. Delete this and the search can be asked of the whole ledger, or the
    order ignored, and the page still looks narrowed."""
    client, _stub, _ledger = served

    searched = activity_of(client, "u_admin", department=FINANCE, q="u_wide")
    oldest = activity_of(client, "u_admin", department=FINANCE, order="oldest")
    newest = activity_of(client, "u_admin", department=FINANCE)

    assert [(one.action, one.subject_id) for one in searched.items] == [
        ("sign_in", "u_wide"),
        ("grant", "u_wide"),
    ]
    assert [one.action for one in oldest.items] == [one.action for one in reversed(newest.items)]
    assert (oldest.order, newest.order) == ("oldest", "newest")


def test_a_department_lens_loads_only_that_departments_people_from_the_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The statement is narrowed to the lens's actors so a department's page does not read the
    whole ledger to find a few entries; `company_activity` decides again over what arrives, so
    this is a cost and never a permission. Delete this and the narrowing can fall out of the
    statement with every other test green, and a busy install reads every entry for every page."""
    asked: list[frozenset[str]] = []

    class Recording(Ledger):
        async def window(self, criteria: AuditFilter, **kwargs: Any) -> Any:
            asked.append(criteria.actors)
            return await super().window(criteria, **kwargs)

    with serving(monkeypatch) as (client, _stub, ledger):
        app: Any = client.app
        app.state.audit_ledger = Recording(rows=ledger.rows)
        activity_of(client, "u_admin", department=FINANCE)
        activity_of(client, "u_admin")

    assert asked == [frozenset({"u_admin", "u_narrow"}), frozenset()]


def test_a_forged_cursor_is_a_malformed_parameter_before_any_read(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """Delete this and a forged cursor reaches the ledger as a 500."""
    client, _stub, ledger = served
    forged = client.get(ACTIVITY, params={"cursor": "not-a-cursor"}, headers=headers("u_admin"))

    assert forged.status_code == 422
    assert ledger.calls == []


# ----------------------------------------------------------------------- the consumption


def test_a_reader_of_the_budget_over_everything_is_shown_the_company_total_by_department(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """The positive case: the three runs in the window, totalled and divided by department, and
    the run six weeks ago left out by the surface's own window. Delete this and the figure can be
    withheld from everybody and pass every test about withholding it."""
    client, _stub, _ledger = served
    view = consumption_of(client, "u_admin")

    assert (view.withheld, view.spend_minor, view.incomplete) == (False, 800, False)
    assert view.by_department == [
        DepartmentSpendView(department=FINANCE, spend_minor=500),
        DepartmentSpendView(department=MAINTENANCE, spend_minor=300),
    ]
    assert view.currency == "SGD"
    assert view.ceiling_set is False


def test_a_reader_whose_budget_grant_is_narrower_is_told_the_figure_is_withheld(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """A budget grant over maintenance opens the screen and is the narrower basis, so the
    company figure is withheld rather than narrowed: no total, no line. Delete this and a
    department's own spend can appear under a heading reading company consumption."""
    client, _stub, _ledger = served
    view = consumption_of(client, "u_narrow")

    assert (view.withheld, view.spend_minor, view.by_department) == (True, None, [])


def test_a_reader_without_the_budget_screen_is_refused_with_the_one_404(
    served: tuple[TestClient, Stub, Ledger],
) -> None:
    """Delete this and a reader with no budget grant is answered that the figure is withheld,
    which is a different answer from a screen that is not there."""
    client, stub, _ledger = served
    refused = get(client, "u_wide", CONSUMPTION)
    audit = get(client, "u_wide", AUDIT)

    assert refused.status_code == 404
    assert refusal(refused.json()) == refusal(audit.json())
    assert not [one for one in stub.statements if names_of(one) == ["SpendActualRow"]]


def test_a_load_that_came_back_full_is_said_beside_the_figure_and_never_without_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full load makes the company total short, which its reader must be told; told to a
    reader whose figure is withheld, it is a measure of everybody else's activity. Delete this
    and either the figure is quietly short or the flag leaks past the withholding."""
    monkeypatch.setattr(company_routes, "MAX_SPEND_ROWS", 4)
    with serving(monkeypatch) as (client, _stub, _ledger):
        wide = consumption_of(client, "u_admin")
        narrow = consumption_of(client, "u_narrow")

    assert (wide.withheld, wide.incomplete) == (False, True)
    assert (narrow.withheld, narrow.incomplete) == (True, False)


def test_nothing_on_any_answer_could_carry_a_count() -> None:
    """Delete this and a total of what was withheld can join one of these pages, which on
    listings narrowed per reader is the subtraction CLAUDE.md forbids."""
    for model in (EstateView, EstateRowView, CompanyActivityPage, ConsumptionView):
        assert not set(model.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, model


def test_the_spend_load_is_bounded_well_above_a_months_runs_for_a_small_company() -> None:
    """Held against the agent page's own bound: the company figure reads at least as many rows
    as one agent's headline does. Delete this and the bound can drop to a figure that makes
    every company total short on an ordinary month."""
    from brain.agent_routes import MAX_HEADLINE_ROWS

    assert MAX_SPEND_ROWS >= MAX_HEADLINE_ROWS


# --------------------------------------------------------------------- the database half


def test_the_spend_statement_reads_exactly_the_window_newest_first_against_postgres() -> None:
    """Rows either side of the window prove the WHERE clause and the order on a real database,
    rather than a description of them. Delete this and the window can be dropped from the
    statement, which `company_consumption` would still correct, at the cost of reading every
    run the install has ever made on every request."""
    since = BEGAN
    until = BEGAN + timedelta(days=30)
    rows = [
        a_cost(FINANCE, 1, BEGAN - timedelta(seconds=1)),
        a_cost(FINANCE, 2, BEGAN),
        a_cost(MAINTENANCE, 3, BEGAN + timedelta(days=10)),
        a_cost(FINANCE, 4, until),
        a_cost(FINANCE, 5, until + timedelta(seconds=1)),
    ]
    with modelled("brain_company_routes", ["ops.spend_actual"]) as url:
        built = engine(url)
        sessions = async_sessionmaker(built, expire_on_commit=False)

        async def scenario() -> list[int]:
            async with sessions() as session, session.begin():
                session.add_all(rows)
            async with sessions() as session:
                found = (await session.execute(spend_between(since, until, 10))).scalars().all()
                bounded = (await session.execute(spend_between(since, until, 2))).scalars().all()
            await built.dispose()
            return [one.cost_minor for one in found] + [-1] + [one.cost_minor for one in bounded]

        assert run(scenario) == [4, 3, 2, -1, 4, 3]
