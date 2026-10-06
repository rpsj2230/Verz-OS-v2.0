"""A department head's budget against pace and their department's coverage, over HTTP.

Driven through the real application with signed-in people and a stub where the pool is, then the
same two routes against a real PostgreSQL, where the lead table, the budget versions, the cost rows
and `know.item`'s policy answer instead of the stub. The database half skips without
`DATABASE_URL` or pgvector, and CI has both.

The readers, by the people the token machinery knows: `u_wide` leads maintenance and reads its
budget and its knowledge; `u_narrow` leads finance and holds neither read; `u_admin` reads every
department's budget and knowledge and leads nothing; `u_none` holds nothing.

**Every refusal has a sibling proving the permitted case is answered.**

Task ids: M33.2.1.3, M33.2.1.4
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import TextClause, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.selectable import Select

from brain import console_overview_figures_routes as figures_routes
from brain import department_view_routes as routes
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.screens import screen
from brain.console_overview_figures_routes import COST_HAS_NO_PRICE
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.department_view_routes import (
    A_HEAD_IS_WHOEVER_LEADS_IT_AND_EVERYBODY_ELSE_IS_ONE_ANSWER,
    COVERAGE_LOAD_WAS_FULL,
    COVERAGE_PATH,
    DEPARTMENT_ITEMS,
    PACE_PATH,
    DepartmentCoverageView,
    DepartmentPaceView,
    PaceView,
    headed_by,
    period_bounds,
)
from brain.knowledge.search import KNOWLEDGE_READ
from brain.ops.budgets import BudgetPeriod
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.tables.budget import BudgetVersionRow
from tests.fixtures.console_http import Stub, console_client, gate_wiring, get
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_console_overview_figures_routes import (
    INSTALL_CURRENCY,
    a_price,
    settings_with,
)

PACE = f"{API_PREFIX}{PACE_PATH}"
COVERAGE = f"{API_PREFIX}{COVERAGE_PATH}"

MAINTENANCE = "maintenance"
FINANCE = "finance"

BUDGET_READ = screen("budget").read.requires
EVERYWHERE = Scope.unrestricted()

#: Far outside any plausible wall clock, for CLAUDE.md's reason: no ceiling here is about today.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect


def in_(department: str) -> Scope:
    return Scope.department(department)


GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_wide": (
        Grant(capability=BUDGET_READ, scope=in_(MAINTENANCE)),
        Grant(capability=KNOWLEDGE_READ, scope=in_(MAINTENANCE)),
    ),
    "u_narrow": (),
    "u_admin": (
        Grant(capability=BUDGET_READ, scope=EVERYWHERE),
        Grant(capability=KNOWLEDGE_READ, scope=EVERYWHERE),
    ),
    "u_none": (),
}

#: Who leads what, as `gate.department_lead` would answer.
LEADS: Mapping[str, tuple[str, ...]] = {"u_wide": (MAINTENANCE,), "u_narrow": (FINANCE,)}

#: What the stub sums a department's cost to, as PostgreSQL sends a sum of a bigint.
SPENT = Decimal(2500)


def a_ceiling(department: str, period: BudgetPeriod, ceiling: int) -> BudgetVersionRow:
    return BudgetVersionRow(
        level="department",
        subject=department,
        period=period.value,
        ceiling_minor=ceiling,
        version=1,
        author="u_admin",
        effective_from=LONG_AGO,
        reason="",
        alert_fractions=[],
    )


#: A daily and a monthly ceiling on each department.
CEILINGS: tuple[BudgetVersionRow, ...] = (
    a_ceiling(MAINTENANCE, BudgetPeriod.DAY, 5000),
    a_ceiling(MAINTENANCE, BudgetPeriod.MONTH, 10000),
    a_ceiling(FINANCE, BudgetPeriod.MONTH, 10000),
)


def column_names(statement: Any) -> list[str]:
    if not isinstance(statement, Select):
        return []
    return [str(one["name"]) for one in statement.column_descriptions]


def params_of(statement: Any) -> dict[str, Any]:
    return dict(statement.compile(dialect=DIALECT).params)


class MappingResult(Result):
    """A result read by `.mappings()`, as `lifecycle_store.stored_item` reads one."""

    def mappings(self) -> list[Any]:
        return self.all()


def an_item(
    item_id: str,
    *,
    verified_days_ago: int | None,
    state: str = "published",
    owner: str = "u_author",
    department: str = MAINTENANCE,
) -> dict[str, Any]:
    verified = (
        None if verified_days_ago is None else datetime.now(UTC) - timedelta(days=verified_days_ago)
    )
    return {
        "item_id": item_id,
        "title": f"title of {item_id}",
        "owner_id": owner,
        "visibility": "department",
        "department": department,
        "state": state,
        "kind": None,
        "verified_by": None if verified is None else "u_steward",
        "verified_at": verified,
        "review_by": None,
        "supersedes": None,
        "created_at": LONG_AGO,
    }


#: One item in each freshness band on the document horizon, and somebody else's draft, which no
#: reader but its owner may count.
ITEMS: tuple[dict[str, Any], ...] = (
    an_item("k_live", verified_days_ago=1),
    an_item("k_ageing", verified_days_ago=200),
    an_item("k_stale", verified_days_ago=400),
    an_item("k_never", verified_days_ago=None),
    an_item("k_draft", verified_days_ago=None, state="draft"),
)


class Answers:
    """The lead table, the budget versions, the cost sum and `know.item`, as the stub's answers."""

    def __init__(
        self,
        ceilings: Sequence[BudgetVersionRow] = CEILINGS,
        items: Sequence[dict[str, Any]] = ITEMS,
    ) -> None:
        self.ceilings = tuple(ceilings)
        self.items = tuple(items)

    def answer(self, statement: Any) -> Result | None:
        names = column_names(statement)
        if names == ["principal_id", "slug"]:
            bound = set(params_of(statement).values())
            return Result(
                [Row((pid, slug)) for pid, slugs in LEADS.items() if pid in bound for slug in slugs]
            )
        if names == ["department_spent_minor"]:
            return Result([Row((SPENT,))])
        if isinstance(statement, Select) and statement.column_descriptions[0]["entity"] is (
            BudgetVersionRow
        ):
            asked = params_of(statement)
            return Result(
                [
                    one
                    for one in self.ceilings
                    if one.subject in asked.values() and one.period in asked.values()
                ]
            )
        if isinstance(statement, TextClause) and statement.text == DEPARTMENT_ITEMS:
            department = statement.compile().params["department"]
            limit = statement.compile().params["limit"]
            found = [one for one in self.items if one["department"] == department]
            return MappingResult(found[:limit])
        return None


@contextmanager
def serving(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ceilings: Sequence[BudgetVersionRow] = CEILINGS,
    priced: bool = True,
) -> Iterator[tuple[TestClient, Stub]]:
    monkeypatch.setattr(figures_routes, "install_currency", lambda: INSTALL_CURRENCY)
    prices = (("anthropic", "a-model", a_price()),) if priced else ()
    with console_client(GRANTS, routers=(routes.router,)) as (client, stub):
        stub.answerers.append(Answers(ceilings).answer)
        stub.answerers.append(settings_with(*prices).answer)
        yield client, stub


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Stub]]:
    with serving(monkeypatch) as both:
        yield both


def pace_of(client: TestClient, pid: str, department: str = MAINTENANCE) -> DepartmentPaceView:
    response = get(client, pid, f"{PACE}?department={department}")
    assert response.status_code == 200, response.text
    return DepartmentPaceView.model_validate(response.json())


def coverage_of(
    client: TestClient, pid: str, department: str = MAINTENANCE
) -> DepartmentCoverageView:
    response = get(client, pid, f"{COVERAGE}?department={department}")
    assert response.status_code == 200, response.text
    return DepartmentCoverageView.model_validate(response.json())


def refusal(client: TestClient, pid: str, path: str) -> dict[str, Any]:
    response = get(client, pid, path)
    assert response.status_code == 404, response.text
    body = dict(response.json())
    body["trace_id"] = "<per request>"
    return body


def budget_statements(stub: Stub) -> list[Any]:
    return [
        one
        for one in stub.statements
        if isinstance(one, Select) and one.column_descriptions[0]["entity"] is BudgetVersionRow
    ]


def spent_statements(stub: Stub) -> list[Any]:
    return [one for one in stub.statements if column_names(one) == ["department_spent_minor"]]


def item_statements(stub: Stub) -> list[Any]:
    return [
        one
        for one in stub.statements
        if isinstance(one, TextClause) and one.text == DEPARTMENT_ITEMS
    ]


# ------------------------------------------------------------------------------- the pace


def test_the_head_of_a_department_is_told_each_ceiling_against_the_part_of_its_period_gone(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for every refusal below: the daily and the monthly ceiling, each as
    `department_pace` computes it, spend over ceiling against time gone over the period. Delete
    this and each refusal is satisfied by a route that answers nobody."""
    client, _ = served
    body = pace_of(client, "u_wide")

    assert body.department == MAINTENANCE
    assert body.not_recorded == []
    day, month = body.paces
    assert (day.period, month.period) == ("day", "month")
    assert (day.spent_fraction, month.spent_fraction) == (0.5, 0.25)
    for one in (day, month):
        assert 0.0 <= one.elapsed_fraction <= 1.0
        assert one.ahead is (one.spent_fraction > one.elapsed_fraction)
        assert one.started_at < one.ends_at
    assert month.ends_at.day == 1
    assert day.ends_at - day.started_at == timedelta(days=1)


def test_spend_is_summed_for_the_department_from_the_start_of_each_period(
    served: tuple[TestClient, Stub],
) -> None:
    """The statement, not the arithmetic: each period's sum names the department and starts where
    the period does, which is what makes the fraction a pace rather than a lifetime total. Delete
    this and a month's pace could be computed over the department's whole history."""
    client, stub = served
    body = pace_of(client, "u_wide")

    day_sum, month_sum = spent_statements(stub)
    for statement, pace in zip((day_sum, month_sum), body.paces, strict=True):
        bound = params_of(statement)
        assert MAINTENANCE in bound.values()
        assert pace.started_at in bound.values()


def test_somebody_who_leads_no_such_department_is_refused_with_the_one_404(
    served: tuple[TestClient, Stub],
) -> None:
    """**A department nobody here leads, one somebody else leads, one that does not exist and a
    reader who reads every budget but leads nothing are one answer**, and no ceiling is read for
    any of them. Delete this and the page answers whoever can type a department's name.
    """
    client, stub = served
    answers = [
        refusal(client, "u_admin", f"{PACE}?department={MAINTENANCE}"),
        refusal(client, "u_none", f"{PACE}?department={MAINTENANCE}"),
        refusal(client, "u_wide", f"{PACE}?department={FINANCE}"),
        refusal(client, "u_wide", f"{PACE}?department=nowhere"),
    ]

    assert all(one == answers[0] for one in answers)
    assert MAINTENANCE not in str(answers[0]) and FINANCE not in str(answers[0])
    assert budget_statements(stub) == []
    assert "gate.department_lead" in A_HEAD_IS_WHOEVER_LEADS_IT_AND_EVERYBODY_ELSE_IS_ONE_ANSWER


def test_a_head_who_may_not_read_the_budget_is_refused_whether_or_not_a_ceiling_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The pace is withheld exactly where `department_pace` withholds it.** `u_narrow` leads
    finance and holds no budget read: with a ceiling set the function returns `None` and the
    route refuses, and with none the same question is asked directly, so the head is not told
    their department has no budget. The sibling is the head who may read it, told the empty
    list. Delete this and a head without the grant learns whether a ceiling exists."""
    with serving(monkeypatch) as (client, _):
        with_ceiling = refusal(client, "u_narrow", f"{PACE}?department={FINANCE}")
    with serving(monkeypatch, ceilings=()) as (client, _):
        without = refusal(client, "u_narrow", f"{PACE}?department={FINANCE}")
        allowed = pace_of(client, "u_wide")

    assert with_ceiling == without
    assert (allowed.paces, allowed.not_recorded) == ([], [])


def test_a_pace_over_spend_nothing_could_record_is_the_sentence_and_never_two_fractions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On an install where no model is priced in its currency the recorder writes no cost, so a
    sum would say the department spent nothing. The head is given the sentence and no fraction,
    no sum is sent, and the reach is still decided first. Delete this and every department on an
    unpriced install reads as comfortably under budget."""
    with serving(monkeypatch, priced=False) as (client, stub):
        body = pace_of(client, "u_wide")
        refused = get(client, "u_narrow", f"{PACE}?department={FINANCE}")

    assert body.paces == []
    assert body.not_recorded == [COST_HAS_NO_PRICE]
    assert spent_statements(stub) == []
    assert refused.status_code == 404


def test_a_department_pace_carries_two_fractions_and_no_amount() -> None:
    """Only what `department_pace` returns is sent: the ceiling and the sum are the Budget
    screen's, read behind its own grant, and no field is a count of anything withheld. Delete this
    and an amount can be added beside the fractions without anybody deciding it."""
    assert set(PaceView.model_fields) == {
        "period",
        "started_at",
        "ends_at",
        "spent_fraction",
        "elapsed_fraction",
        "ahead",
    }
    names = set(DepartmentPaceView.model_fields) | set(PaceView.model_fields)
    assert names.isdisjoint(NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT)


def test_a_period_runs_from_its_first_instant_to_the_first_instant_of_the_next() -> None:
    """The bounds the elapsed fraction is taken over, at the ends of a month and a year. Delete
    this and the last day of December paces against a period that ends in January of the year
    before."""
    late = datetime(2019, 12, 31, 23, 30, tzinfo=UTC)
    assert period_bounds(BudgetPeriod.MONTH, late) == (
        datetime(2019, 12, 1, tzinfo=UTC),
        datetime(2020, 1, 1, tzinfo=UTC),
    )
    assert period_bounds(BudgetPeriod.DAY, late) == (
        datetime(2019, 12, 31, tzinfo=UTC),
        datetime(2020, 1, 1, tzinfo=UTC),
    )
    february = datetime(2020, 2, 29, 12, tzinfo=UTC)
    assert period_bounds(BudgetPeriod.MONTH, february)[1] == datetime(2020, 3, 1, tzinfo=UTC)


def test_who_leads_is_the_audit_reach_rewrites_answer_narrowed_to_the_reader() -> None:
    """`headed_by` is `head_audit_store.leads` with the reader added, so a lead stood down, a
    department retired and a head the roster marks as having left are no head here either. Read
    off the compiled statement. Delete this and the page could be answered from a second
    definition of a head that disagrees with the Activity screen's."""
    compiled = str(headed_by("u_wide").compile(dialect=DIALECT))
    assert "department_lead.ended_at IS NULL" in compiled
    assert "department.deleted_at IS NULL" in compiled
    assert "department_lead.principal_id NOT IN" in compiled
    assert "department_lead.principal_id = " in compiled
    assert "u_wide" in params_of(headed_by("u_wide")).values()


# --------------------------------------------------------------------------- the coverage


def test_the_head_is_told_their_departments_coverage_band_by_band(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case: one area, the department, with an item in each band on the document
    horizon, and somebody else's draft not counted. The read is told who is asking first, so
    `know.item`'s policy narrows on the same person. Delete this and the refusals below are
    satisfied by a route that shows nothing."""
    client, stub = served
    body = coverage_of(client, "u_wide")

    assert body.unread == ""
    (area,) = body.areas
    assert (area.area, area.items) == (MAINTENANCE, 4)
    assert area.by_freshness == {"live": 1, "ageing": 1, "stale": 1, "unstated": 1}
    assert ("app.principal_id", "u_wide") in stub.attributions
    assert ("app.departments", MAINTENANCE) in stub.attributions
    (statement,) = item_statements(stub)
    assert statement.compile().params["department"] == MAINTENANCE


def test_coverage_refuses_everybody_but_the_head_with_the_one_404(
    served: tuple[TestClient, Stub],
) -> None:
    """The coverage's refusals, identical to the pace's and to each other, with no document read
    for any of them. Delete this and the coverage of any department is a query parameter away."""
    client, stub = served
    answers = [
        refusal(client, "u_admin", f"{COVERAGE}?department={MAINTENANCE}"),
        refusal(client, "u_none", f"{COVERAGE}?department={MAINTENANCE}"),
        refusal(client, "u_wide", f"{COVERAGE}?department={FINANCE}"),
        refusal(client, "u_wide", f"{COVERAGE}?department=nowhere"),
        refusal(client, "u_wide", f"{PACE}?department=nowhere"),
    ]

    assert all(one == answers[0] for one in answers)
    assert item_statements(stub) == []


def test_a_head_without_a_read_of_the_knowledge_plane_is_shown_no_area_and_nothing_is_read(
    served: tuple[TestClient, Stub],
) -> None:
    """A head whose grants reach none of the knowledge plane is shown no row rather than a row of
    zeroes, and the table is not read for them. Delete this and a head with no read is told how
    many documents their department holds."""
    client, stub = served
    body = coverage_of(client, "u_narrow", FINANCE)

    assert (body.areas, body.unread) == ([], "")
    assert item_statements(stub) == []


def test_a_coverage_load_that_came_back_full_is_withheld_rather_than_drawn_short(
    monkeypatch: pytest.MonkeyPatch, served: tuple[TestClient, Stub]
) -> None:
    """See `A_COVERAGE_LOAD_THAT_CAME_BACK_FULL_IS_WITHHELD`. With the bound at the size of the
    load, the rows are not drawn and the sentence says why; one above it, they are. Delete this
    and a department past the bound reads as holding exactly the bound."""
    client, _ = served
    monkeypatch.setattr(routes, "MAX_ITEMS_COUNTED", len(ITEMS))
    full = coverage_of(client, "u_wide")
    monkeypatch.setattr(routes, "MAX_ITEMS_COUNTED", len(ITEMS) + 1)
    whole = coverage_of(client, "u_wide")

    assert (full.areas, full.unread) == ([], COVERAGE_LOAD_WAS_FULL)
    assert [one.items for one in whole.areas] == [4]


def test_coverage_carries_no_total_share_or_count_of_what_was_withheld() -> None:
    """Read off the models. Delete this and a total of the corpus could be added beside the
    reader's own count, and the subtraction is the hidden count."""
    names = set(DepartmentCoverageView.model_fields) | set(routes.CoverageAreaView.model_fields)
    assert names == {"department", "areas", "unread", "area", "items", "by_freshness"}
    assert names.isdisjoint(NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT)


# ----------------------------------------------------------------- against PostgreSQL

DATABASE = "brain_test_department_view_routes"


@pytest.fixture(scope="module")
def company() -> Iterator[str]:
    """Every migration to head; maintenance led by `u_wide` and finance by `u_narrow`; a monthly
    ceiling on maintenance; cost charged to maintenance this month and last, and to finance; and
    `know.item` rows in maintenance, in finance and company-wide. Skips without pgvector."""
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import sql

    with retirable(DATABASE) as url:
        if not has_pgvector(url):
            pytest.skip("the lead, budget and item tables need the whole chain and pgvector")
        for slug, head in ((MAINTENANCE, "u_wide"), (FINANCE, "u_narrow")):
            sql(
                url,
                "INSERT INTO gate.scope (slug, predicate) VALUES (%s, %s)",
                slug,
                json.dumps({"department": slug}),
            )
            sql(
                url,
                "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
                " VALUES ('c_1', %s, %s, %s)",
                slug,
                slug.title(),
                slug,
            )
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name)"
                " VALUES (%s, 'human', 'staff', %s)",
                head,
                f"Person {head}",
            )
            sql(
                url,
                "INSERT INTO gate.department_lead (department_id, principal_id, appointed_by)"
                " SELECT id, %s, 'u_admin' FROM gate.department WHERE slug = %s",
                head,
                slug,
            )
        sql(
            url,
            "INSERT INTO ops.budget_version (level, subject, period, ceiling_minor, version,"
            " author, effective_from) VALUES ('department', %s, 'month', 10000, 1, 'u_admin', %s)",
            MAINTENANCE,
            LONG_AGO,
        )
        began, _ = period_bounds(BudgetPeriod.MONTH, datetime.now(UTC))
        for department, at, cost, trace in (
            (MAINTENANCE, began, 2000, "c-a"),
            (MAINTENANCE, began, 500, "c-b"),
            (MAINTENANCE, began - timedelta(days=3), 99999, "c-c"),
            (FINANCE, began, 7777, "c-d"),
            # Dated after the request, so only the window's upper bound leaves it out.
            (MAINTENANCE, datetime.now(UTC) + timedelta(hours=1), 4444, "c-e"),
        ):
            sql(
                url,
                "INSERT INTO ops.spend_actual (principal_id, principal_kind, traffic, department,"
                " model, lane, cost_minor, at, trace_id)"
                " VALUES ('u_wide', 'human', 'human_interactive', %s, 'a-model', 'fast', %s, %s,"
                " %s)",
                department,
                cost,
                at,
                trace,
            )
        now = datetime.now(UTC)
        filed: tuple[tuple[str, str | None, str, datetime | None], ...] = (
            ("k_live", MAINTENANCE, "department", now - timedelta(days=1)),
            ("k_stale", MAINTENANCE, "department", now - timedelta(days=400)),
            ("k_never", MAINTENANCE, "department", None),
            ("k_finance", FINANCE, "department", now - timedelta(days=1)),
            ("k_company", None, "company", now - timedelta(days=1)),
        )
        for item_id, place, visibility, verified in filed:
            sql(
                url,
                "INSERT INTO know.item (item_id, title, owner_id, visibility, department, state,"
                " verified_by, verified_at) VALUES (%s, %s, 'u_author', %s, %s, 'published', %s,"
                " %s)",
                item_id,
                f"title of {item_id}",
                visibility,
                place,
                None if verified is None else "u_steward",
                verified,
            )
        yield url


@contextmanager
def against(url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The application over the scratch database, as the application role, so every policy
    applies. Cost is taken as recorded: whether it is, is the stub half's question."""
    from brain.session import make_session_factory
    from tests.unit.test_automation_owner_store import app_engine

    async def recorded(_: object) -> tuple[str, None]:
        return INSTALL_CURRENCY, None

    monkeypatch.setattr(routes, "cost_recorded_in", recorded)
    engine = app_engine(url)
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = make_session_factory(engine)
        yield client


def test_against_the_database_the_head_is_paced_on_this_periods_cost_to_their_department(
    company: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lead table decides the head, the ceiling in force is read, and the sum is this month's
    cost charged to maintenance and nothing else: 2500 of 10000, with last month's, finance's and
    a row dated after the request left out by the server. The other department's head is
    refused. Delete this and the WHERE clauses are proved only by the words the stub compiles."""
    with against(company, monkeypatch) as client:
        body = pace_of(client, "u_wide")
        refused = get(client, "u_narrow", f"{PACE}?department={FINANCE}")
        stranger = get(client, "u_admin", f"{PACE}?department={MAINTENANCE}")

    (month,) = body.paces
    assert (month.period, month.spent_fraction) == ("month", 0.25)
    assert (refused.status_code, stranger.status_code) == (404, 404)


def test_against_the_database_coverage_is_read_through_the_item_policy_at_the_heads_reach(
    company: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`know.item`'s policy admits a department's items only to a transaction told that
    department, so the three maintenance items are counted only because the route told the
    database who was asking; finance's item and the company item are not in the department's
    row. Delete this and a route that forgot the settings would read nothing and show an empty
    department."""
    with against(company, monkeypatch) as client:
        body = coverage_of(client, "u_wide")

    (area,) = body.areas
    assert (area.area, area.items) == (MAINTENANCE, 3)
    assert area.by_freshness == {"live": 1, "ageing": 0, "stale": 1, "unstated": 1}
