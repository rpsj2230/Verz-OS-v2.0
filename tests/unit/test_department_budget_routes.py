"""A department's budget over HTTP: its share, a transfer, its per-run ceiling and its people's
allowances.

The pure half is the three planners and the line filter, which decide every figure and every
refusal; the stub half drives the real application with signed-in people and holds the refusals,
none of which reads a row; the database half runs the whole path as the application role against
PostgreSQL and reads the versions and the ledger back.

Task ids: M21.1.1, M21.1.2, M21.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.company_routes import COMPANY_ALERT_FRACTIONS, COMPANY_BUDGET_PATH
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.department_budget_routes import (
    A_RUN_CEILING_ABOVE_THE_MONTH_CAN_NEVER_BIND,
    ALLOWANCES_PATH,
    DEPARTMENT_ALERT_FRACTIONS,
    DEPARTMENT_BUDGETS_PATH,
    MOVING_COMPANY_MONEY_NEEDS_THE_BUDGET_ROLE,
    RUN_CEILING_PATH,
    SETTING_A_DEPARTMENT_BUDGET_NEEDS_THE_BUDGET_ROLE,
    TRANSFER_PATH,
    lines_of,
    plan_allocation,
    plan_allowances,
    plan_transfer,
    router,
)
from brain.ops.budgets import (
    BudgetError,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
    DepartmentShare,
    company_budget,
)
from brain.session import make_session_factory
from tests.fixtures.console_http import Stub, console_client, gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

#: Dated far from any wall clock, so no fixture here can go off: see the repository's rule on
#: fixtures that carry a date.
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
LATER = LONG_AGO + timedelta(days=1)
AUTHORITY = Capability(value="admin:budget")


def company(ceiling: int = 1_000_000) -> BudgetRow:
    return company_budget(
        company_id="c_1", ceiling_minor=ceiling, author="u_root", effective_from=LONG_AGO
    )


def shares(**by_department: float) -> list[DepartmentShare]:
    return [DepartmentShare(department=name, share=one) for name, one in by_department.items()]


def held_by(rows: tuple[BudgetRow, ...]) -> dict[str, BudgetRow]:
    return {one.subject: one for one in rows}


# ------------------------------------------------------------------------ the pure half
def test_a_departments_budget_warns_at_seventy_and_ninety_per_cent() -> None:
    """The owner's requirement for the company's budget names seventy and ninety per cent, and a
    department it is shared with warns at the same two. The figure is asserted as a literal and not
    against the constant, which would compare it with itself. Delete this and the console writes
    budgets that warn where the code once guessed and not where the owner asked."""
    assert COMPANY_ALERT_FRACTIONS == (0.7, 0.9)
    assert DEPARTMENT_ALERT_FRACTIONS == (0.7, 0.9)


def test_a_first_allocation_gives_each_department_a_version_one_row_that_warns() -> None:
    """The rows an allocation appends are version one, shared out by the fractions, signed by the
    author with the reason, and carry the warning fractions that `allocate`'s own rows do not.
    Delete this and a department's budget never warns as it is consumed."""
    rows = plan_allocation(
        company(),
        shares(web=0.4, finance=0.3),
        {},
        author="u_admin",
        reason="the year's split",
        now=LATER,
    )
    made = held_by(rows)
    assert {name: (one.ceiling_minor, one.version) for name, one in made.items()} == {
        "web": (400_000, 1),
        "finance": (300_000, 1),
    }
    assert all(one.alert_fractions == (0.7, 0.9) for one in rows)
    assert all(one.author == "u_admin" and "the year's split" in one.reason for one in rows)
    assert all(
        one.level is BudgetLevel.DEPARTMENT and one.period is BudgetPeriod.MONTH for one in rows
    )


def test_allocating_again_supersedes_what_a_department_holds_and_keeps_its_warnings() -> None:
    """A department that already has a budget gets the next version, not a second version one, and
    a row written before warnings existed gains them. Delete this and a second allocation is the
    history the table refuses to order, or the old row's silence carries on."""
    first = plan_allocation(
        company(), shares(web=0.4), {}, author="u_admin", reason="first", now=LATER
    )
    silent = BudgetRow(
        level=BudgetLevel.DEPARTMENT,
        subject="web",
        period=BudgetPeriod.MONTH,
        ceiling_minor=first[0].ceiling_minor,
        version=1,
        author="u_old",
        effective_from=LONG_AGO,
    )
    again = plan_allocation(
        company(),
        shares(web=0.5),
        {"web": silent},
        author="u_admin",
        reason="second",
        now=LATER,
    )
    assert [(one.version, one.ceiling_minor) for one in again] == [(2, 500_000)]
    assert again[0].alert_fractions == (0.7, 0.9)


def test_an_allocation_beside_departments_it_does_not_name_cannot_exceed_the_company() -> None:
    """Finance keeps its sixty per cent when the request names only web, so web at fifty per cent
    would leave the departments holding one and a tenth of the company. It is refused, and the same
    request at forty per cent is accepted. Delete this and two half-requests are the overflow that
    one whole request cannot be."""
    finance = plan_allocation(
        company(), shares(finance=0.6), {}, author="u_admin", reason="x", now=LATER
    )
    held = held_by(finance)
    with pytest.raises(BudgetError):
        plan_allocation(company(), shares(web=0.5), held, author="u_admin", reason="x", now=LATER)
    fits = plan_allocation(
        company(), shares(web=0.4), held, author="u_admin", reason="x", now=LATER
    )
    assert fits[0].ceiling_minor == 400_000


def test_shares_adding_up_to_more_than_one_are_refused_by_the_budget_itself() -> None:
    """`allocate`'s own rule still holds through the planner. Delete this and the planner's added
    check is the only one standing, which a later edit can remove with nothing noticing."""
    with pytest.raises(BudgetError):
        plan_allocation(
            company(), shares(web=0.7, finance=0.6), {}, author="u_admin", reason="x", now=LATER
        )


def test_a_transfer_conserves_the_total_and_names_both_sides() -> None:
    """Both rows come back as the next version, the amount leaves one and arrives at the other, and
    the sum is the same. Delete this and a transfer that credits and forgets to debit reads as
    generosity and is an overspend."""
    rows = held_by(
        plan_allocation(
            company(), shares(web=0.4, finance=0.3), {}, author="u_admin", reason="x", now=LATER
        )
    )
    source, destination = plan_transfer(
        rows["web"],
        rows["finance"],
        amount_minor=50_000,
        author="u_admin",
        reason="a launch",
        now=LATER + timedelta(days=1),
    )
    assert (source.subject, source.ceiling_minor, source.version) == ("web", 350_000, 2)
    assert (destination.subject, destination.ceiling_minor, destination.version) == (
        "finance",
        350_000,
        2,
    )
    assert source.ceiling_minor + destination.ceiling_minor == 700_000
    assert "a launch" in source.reason and "u_admin" in source.reason


def test_a_transfer_cannot_take_a_department_to_nothing() -> None:
    """Moving all of a department's budget suspends it, which is a different change. Delete this
    and a transfer is the way to switch a department off without anyone saying so."""
    rows = held_by(
        plan_allocation(
            company(), shares(web=0.4, finance=0.3), {}, author="u_admin", reason="x", now=LATER
        )
    )
    with pytest.raises(BudgetError):
        plan_transfer(
            rows["web"],
            rows["finance"],
            amount_minor=400_000,
            author="u_admin",
            reason="all of it",
            now=LATER + timedelta(days=1),
        )


def test_everyone_in_a_department_gets_the_same_capped_pair_and_asking_again_writes_nothing() -> (
    None
):
    """Each member gets a daily and a monthly row; the pair is the fair-share one for the
    department's budget and headcount; asked a second time with nothing changed no row is written.
    Delete this and an allowance route either gives people different figures for being in the same
    room, or writes a new version on every click."""
    department = held_by(
        plan_allocation(company(), shares(web=0.4), {}, author="u_admin", reason="x", now=LATER)
    )["web"]
    people = ["u_a", "u_b", "u_c", "u_d", "u_e"]
    rows, figures = plan_allowances(
        department, people, {}, author="u_admin", reason="the month's", now=LATER
    )
    assert len(rows) == 2 * len(people)
    monthly = {one.ceiling_minor for one in rows if one.period is BudgetPeriod.MONTH}
    assert monthly == {figures[1]}
    assert figures[1] <= department.ceiling_minor // 4
    held = {(one.subject, one.period): one for one in rows}
    again, _ = plan_allowances(
        department,
        people,
        held,
        author="u_admin",
        reason="the month's",
        now=LATER + timedelta(days=1),
    )
    assert again == ()


def test_a_changed_department_budget_gives_the_next_version_of_an_allowance() -> None:
    """A person who already holds an allowance and whose figure changes gets the next version of
    that row. Delete this and the second asking appends a second version one."""
    first = held_by(
        plan_allocation(company(), shares(web=0.2), {}, author="u_admin", reason="x", now=LATER)
    )["web"]
    people = ["u_a", "u_b"]
    rows, _ = plan_allowances(first, people, {}, author="u_admin", reason="x", now=LATER)
    held = {(one.subject, one.period): one for one in rows}
    bigger = held_by(
        plan_allocation(
            company(),
            shares(web=0.4),
            {"web": first},
            author="u_admin",
            reason="x",
            now=LATER + timedelta(days=1),
        )
    )["web"]
    later, _ = plan_allowances(
        bigger, people, held, author="u_admin", reason="x", now=LATER + timedelta(days=2)
    )
    assert len(later) == 4
    assert {one.version for one in later} == {2}


def reach(*grants: Grant) -> EntitlementSet:
    return EntitlementSet(principal_id="u_x", grants=grants)


def test_a_reader_is_shown_the_lines_of_the_departments_they_hold_the_authority_over() -> None:
    """The department head sees their own line, the administrator over everything sees all, and a
    reader with no authority sees none, which is also what an install with no budgets shows. Delete
    this and a list of departments becomes a list of which departments have a budget."""
    monthly = held_by(
        plan_allocation(
            company(), shares(web=0.4, finance=0.3), {}, author="u_admin", reason="x", now=LATER
        )
    )
    now = LATER + timedelta(days=1)
    head = reach(Grant(capability=AUTHORITY, scope=Scope.department("web")))
    everything = reach(Grant(capability=AUTHORITY, scope=Scope.unrestricted()))
    assert [one.department for one in lines_of(monthly, {}, head, now)] == ["web"]
    assert [one.department for one in lines_of(monthly, {}, everything, now)] == ["finance", "web"]
    assert lines_of(monthly, {}, reach(), now) == []


# ---------------------------------------------------------------------- the refusals, stubbed
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        Grant(capability=AUTHORITY, scope=Scope.unrestricted()),
        Grant(capability=screen("budget").read.requires, scope=Scope.unrestricted()),
        *(Grant(capability=plane_capability(one), scope=Scope.unrestricted()) for one in Plane),
    ),
    "u_prefix": (Grant(capability=AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


@pytest.fixture
def served() -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        yield client, stub


def send(client: TestClient, method: str, path: str, pid: str, body: Mapping[str, Any]) -> Any:
    return client.request(method, f"{API_PREFIX}{path}", json=dict(body), headers=headers(pid))


ALLOCATION = {"shares": [{"department": "web", "share": 0.4}], "reason": "the year"}
TRANSFER = {
    "from_department": "web",
    "to_department": "finance",
    "amount_minor": 1000,
    "reason": "a launch",
}
RUN = {"ceiling_minor": 500, "reason": "per run"}
ALLOWANCES = {"reason": "the month"}


def test_moving_company_money_needs_the_authority_over_everything_and_reads_nothing(
    served: tuple[TestClient, Stub],
) -> None:
    """A department's own administrator and a stranger are refused an allocation and a transfer
    with the sentence naming the role, before any row is read. Delete this and the head of one
    department can set the shares of all of them."""
    client, stub = served
    for pid in ("u_prefix", "u_none"):
        for method, path, body in (
            ("PUT", DEPARTMENT_BUDGETS_PATH, ALLOCATION),
            ("POST", TRANSFER_PATH, TRANSFER),
        ):
            refused = send(client, method, path, pid, body)
            assert refused.status_code == 403
            assert refused.json()["message"] == MOVING_COMPANY_MONEY_NEEDS_THE_BUDGET_ROLE
    assert stub.statements == []


def test_another_departments_ceiling_is_refused_in_the_words_a_stranger_gets(
    served: tuple[TestClient, Stub],
) -> None:
    """An administrator of web asking for finance's per-run ceiling or allowances is told what
    somebody with no authority at all is told, and nothing is read, so the answer does not say which
    departments exist. Delete this and the refusal tells a caller whether a department is real."""
    client, stub = served
    for pid, department in (
        ("u_prefix", "finance"),
        ("u_none", "web"),
        ("u_prefix", "no_such_one"),
    ):
        for method, path, body in (
            ("PUT", RUN_CEILING_PATH, RUN),
            ("POST", ALLOWANCES_PATH, ALLOWANCES),
        ):
            refused = send(client, method, path.format(department=department), pid, body)
            assert refused.status_code == 403
            assert refused.json()["message"] == SETTING_A_DEPARTMENT_BUDGET_NEEDS_THE_BUDGET_ROLE
    assert stub.statements == []


def test_a_malformed_share_or_a_repeated_department_is_refused_before_anything_is_read(
    served: tuple[TestClient, Stub],
) -> None:
    """A share of nothing, one above one, a department twice and an empty list are each a 422 and
    read nothing. Delete this and a malformed allocation reaches the planner."""
    client, stub = served
    bad = (
        {"shares": [{"department": "web", "share": 0}], "reason": "x"},
        {"shares": [{"department": "web", "share": 1.5}], "reason": "x"},
        {
            "shares": [
                {"department": "web", "share": 0.2},
                {"department": "web", "share": 0.2},
            ],
            "reason": "x",
        },
        {"shares": [], "reason": "x"},
    )
    for body in bad:
        assert send(client, "PUT", DEPARTMENT_BUDGETS_PATH, "u_admin", body).status_code == 422
    assert stub.statements == []


# ------------------------------------------------------------------------- the database
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_department_budget_{uuid.uuid4().hex[:8]}") as url:
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The routes over this database as the application role. No lifespan runs."""
    from brain.company_routes import router as company_router

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.include_router(company_router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def seed(url: str) -> None:
    for slug in ("web", "finance"):
        sql(
            url,
            "INSERT INTO gate.scope (slug, predicate) VALUES (%s, %s)",
            slug,
            f'{{"department": "{slug}"}}',
        )
        sql(
            url,
            "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
            " VALUES ('c_1', %s, %s, %s)",
            slug,
            slug.title(),
            slug,
        )
    for pid, department, disabled in (
        ("u_a", "web", False),
        ("u_b", "web", False),
        ("u_c", "web", False),
        ("u_gone", "web", True),
        ("u_fin", "finance", False),
    ):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department,"
            " disabled_at) VALUES (%s, 'human', 'staff', %s, %s,"
            " CASE WHEN %s THEN now() ELSE NULL END)",
            pid,
            f"Person {pid}",
            department,
            disabled,
        )


def test_a_department_is_funded_moved_ceilinged_and_given_allowances_on_the_database(
    database: str,
) -> None:
    """**The whole path on PostgreSQL as the application role.** The company's budget is set; the
    administrator over everything shares it between two departments, which are then listed to them
    and to a head of one; a transfer moves money and leaves the total; the head of web sets web's
    per-run ceiling and gives its live people allowances, the disabled member getting none; asking
    for allowances again writes nothing; and every version is in the table and in the ledger. Delete
    this and each route can answer 200 over a write the table or its trigger refuses."""
    seed(database)

    async def scenario(client: httpx.AsyncClient) -> dict[str, Any]:
        out: dict[str, Any] = {}
        base = API_PREFIX
        out["company"] = await client.put(
            f"{base}{COMPANY_BUDGET_PATH}",
            json={"ceiling_minor": 1_000_000, "reason": "the month"},
            headers=headers("u_admin"),
        )
        out["allocated"] = await client.put(
            f"{base}{DEPARTMENT_BUDGETS_PATH}",
            json={
                "shares": [
                    {"department": "web", "share": 0.4},
                    {"department": "finance", "share": 0.3},
                ],
                "reason": "the split",
            },
            headers=headers("u_admin"),
        )
        out["over"] = await client.put(
            f"{base}{DEPARTMENT_BUDGETS_PATH}",
            json={"shares": [{"department": "web", "share": 0.9}], "reason": "too much"},
            headers=headers("u_admin"),
        )
        out["unknown"] = await client.put(
            f"{base}{DEPARTMENT_BUDGETS_PATH}",
            json={"shares": [{"department": "nowhere", "share": 0.1}], "reason": "x"},
            headers=headers("u_admin"),
        )
        out["transferred"] = await client.post(
            f"{base}{TRANSFER_PATH}",
            json={**TRANSFER, "amount_minor": 50_000},
            headers=headers("u_admin"),
        )
        out["emptied"] = await client.post(
            f"{base}{TRANSFER_PATH}",
            json={**TRANSFER, "amount_minor": 350_000},
            headers=headers("u_admin"),
        )
        out["run"] = await client.put(
            f"{base}{RUN_CEILING_PATH.format(department='web')}",
            json={"ceiling_minor": 20_000, "reason": "per run"},
            headers=headers("u_prefix"),
        )
        out["run_over"] = await client.put(
            f"{base}{RUN_CEILING_PATH.format(department='web')}",
            json={"ceiling_minor": 9_000_000, "reason": "too much"},
            headers=headers("u_prefix"),
        )
        out["allowances"] = await client.post(
            f"{base}{ALLOWANCES_PATH.format(department='web')}",
            json=ALLOWANCES,
            headers=headers("u_prefix"),
        )
        out["again"] = await client.post(
            f"{base}{ALLOWANCES_PATH.format(department='web')}",
            json=ALLOWANCES,
            headers=headers("u_prefix"),
        )
        out["head_list"] = await client.get(
            f"{base}{DEPARTMENT_BUDGETS_PATH}", headers=headers("u_prefix")
        )
        out["all_list"] = await client.get(
            f"{base}{DEPARTMENT_BUDGETS_PATH}", headers=headers("u_admin")
        )
        out["none_list"] = await client.get(
            f"{base}{DEPARTMENT_BUDGETS_PATH}", headers=headers("u_none")
        )
        return out

    seen = pressed(database, scenario)
    for name in ("company", "allocated", "transferred", "run", "allowances", "again"):
        assert seen[name].status_code == 200, (name, seen[name].text)
    assert seen["over"].status_code == 422
    assert seen["unknown"].status_code == 422
    assert seen["emptied"].status_code == 422
    assert seen["run_over"].status_code == 422
    assert seen["run_over"].json()["message"] == A_RUN_CEILING_ABOVE_THE_MONTH_CAN_NEVER_BIND

    stored = {
        (one[0], one[1]): (one[2], one[3])
        for one in sql(
            database,
            "SELECT subject, period, version, ceiling_minor FROM ops.budget_version"
            " WHERE level = 'department' AND version = (SELECT max(version) FROM"
            " ops.budget_version b WHERE b.level = ops.budget_version.level AND b.subject ="
            " ops.budget_version.subject AND b.period = ops.budget_version.period)",
        )
    }
    assert stored[("web", "month")] == (2, 350_000)
    assert stored[("finance", "month")] == (2, 350_000)
    assert stored[("web", "run")] == (1, 20_000)

    people = seen["allowances"].json()["people"]
    assert people == 3
    users = sql(
        database,
        "SELECT subject, period, version FROM ops.budget_version WHERE level = 'user'"
        " ORDER BY subject, period",
    )
    assert {one[0] for one in users} == {"u_a", "u_b", "u_c"}
    assert all(one[2] == 1 for one in users) and len(users) == 6
    assert seen["again"].json()["people"] == 3

    head = seen["head_list"].json()
    assert [one["department"] for one in head["lines"]] == ["web"]
    assert head["may_allocate"] is False and head["unallocated_minor"] is None
    everything = seen["all_list"].json()
    assert [one["department"] for one in everything["lines"]] == ["finance", "web"]
    assert everything["unallocated_minor"] == 300_000
    assert seen["none_list"].json()["lines"] == []

    ledgered = entries(database, "setting")
    departments = [one for one in ledgered if one.subject.startswith("department:")]
    persons = [one for one in ledgered if one.subject.startswith("principal:")]
    assert sorted((one.subject, one.actor_id) for one in departments) == [
        ("department:finance", "u_admin"),
        ("department:finance", "u_admin"),
        ("department:web", "u_admin"),
        ("department:web", "u_admin"),
        ("department:web", "u_prefix"),
    ]
    assert {one.actor_id for one in persons} == {"u_prefix"} and len(persons) == 6
    assert all(not one.trace_id.startswith("tx.") for one in departments + persons)
