"""The company's monthly budget over HTTP against PostgreSQL: set twice, two versions, two entries.

The refusals (a department's budget administrator, a stranger) are held in
`tests/unit/test_company_routes.py` over a stub pool; this is the half that needs a database. The
company's budget administrator sets the ceiling through the route as the application role, sets it
again, and the table holds version one and version two, each ledgered under the company and naming
who set it, with the request's own trace.

Task ids: M33.1.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import httpx
import pytest

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.company_routes import COMPANY_BUDGET_AUTHORITY, COMPANY_BUDGET_PATH, router
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries

EVERYWHERE = Scope.unrestricted()

#: `u_admin` reads the budget screen and holds the budget authority over everything.
GRANTS = {
    "u_admin": (
        Grant(capability=COMPANY_BUDGET_AUTHORITY, scope=EVERYWHERE),
        Grant(capability=screen("budget").read.requires, scope=EVERYWHERE),
        *(Grant(capability=plane_capability(one), scope=EVERYWHERE) for one in Plane),
    ),
}

BODY = {"ceiling_minor": 1_000_000, "reason": "The company's month."}


@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_company_budget_{uuid.uuid4().hex[:8]}") as url:
        yield url


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The route over this database as the application role. No lifespan runs."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def test_setting_the_companys_budget_twice_writes_two_versions_and_two_ledger_entries(
    database: str,
) -> None:
    """M33.1.1.3's budget on PostgreSQL as the application role: the budget administrator over
    everything sets the company's monthly ceiling and sets it again; the table holds version one
    and version two, the consumption read after them carries the ceiling now in force, and each
    version is ledgered naming who set it. Delete this and the route can answer 200 over a write
    the table or its trigger refuses, or a ceiling can be written that no read ever shows."""

    async def twice(client: httpx.AsyncClient) -> list[Any]:
        path = f"{API_PREFIX}{COMPANY_BUDGET_PATH}"
        first = await client.put(path, json=BODY, headers=headers("u_admin"))
        second = await client.put(
            path, json={**BODY, "ceiling_minor": 2_000_000}, headers=headers("u_admin")
        )
        shown = await client.get(f"{API_PREFIX}/company/consumption", headers=headers("u_admin"))
        return [first, second, shown]

    first, second, shown = pressed(database, twice)
    assert (first.status_code, second.status_code) == (200, 200), first.text
    assert (first.json()["version"], second.json()["version"]) == (1, 2)
    stored = sql(
        database,
        "SELECT version, ceiling_minor, author FROM ops.budget_version"
        " WHERE level = 'company' AND period = 'month' ORDER BY version",
    )
    assert [tuple(one) for one in stored] == [(1, 1_000_000, "u_admin"), (2, 2_000_000, "u_admin")]
    assert shown.status_code == 200, shown.text
    assert (shown.json()["ceiling_set"], shown.json()["ceiling_minor"]) == (True, 2_000_000)
    ledgered = [
        one for one in entries(database, "setting") if one.subject == "setting:budget.company"
    ]
    assert [(one.actor_id, one.details["budget_period"]) for one in ledgered] == [
        ("u_admin", "month"),
        ("u_admin", "month"),
    ]
    assert all(not one.trace_id.startswith("tx.") for one in ledgered)


def test_a_budget_set_from_the_console_warns_where_the_owner_asked_and_keeps_its_warnings(
    database: str,
) -> None:
    """The first version of the company's budget carries the warnings at seventy and ninety per
    cent that the owner's requirement names, a second version with none given keeps them, and one
    that names its own replaces them. Delete this and the budget the console writes has warning
    fractions nothing ever sets, which is how the thresholds were stored and fired by nothing."""

    async def three(client: httpx.AsyncClient) -> list[Any]:
        path = f"{API_PREFIX}{COMPANY_BUDGET_PATH}"
        first = await client.put(path, json=BODY, headers=headers("u_admin"))
        second = await client.put(
            path, json={**BODY, "ceiling_minor": 2_000_000}, headers=headers("u_admin")
        )
        third = await client.put(
            path,
            json={**BODY, "ceiling_minor": 3_000_000, "alert_fractions": [0.5, 0.8]},
            headers=headers("u_admin"),
        )
        return [first, second, third]

    first, second, third = pressed(database, three)
    assert [one.json()["alert_fractions"] for one in (first, second, third)] == [
        [0.7, 0.9],
        [0.7, 0.9],
        [0.5, 0.8],
    ]
    stored = sql(
        database,
        "SELECT version, alert_fractions FROM ops.budget_version"
        " WHERE level = 'company' AND period = 'month' ORDER BY version",
    )
    assert [(one[0], [float(x) for x in one[1]]) for one in stored] == [
        (1, [0.7, 0.9]),
        (2, [0.7, 0.9]),
        (3, [0.5, 0.8]),
    ]


def test_warning_fractions_that_do_not_rise_or_reach_the_ceiling_are_refused(
    database: str,
) -> None:
    """A fraction at the ceiling, one that does not rise and one past it are each a 422 and write
    nothing. Delete this and a warning that fires at the instant of the refusal, which tells nobody
    anything, can be stored as if it were an early one."""

    async def bad(client: httpx.AsyncClient) -> list[Any]:
        path = f"{API_PREFIX}{COMPANY_BUDGET_PATH}"
        return [
            await client.put(
                path, json={**BODY, "alert_fractions": fractions}, headers=headers("u_admin")
            )
            for fractions in ([1.0], [0.9, 0.5], [0.5, 1.2], [0.0, 0.5], [0.1] * 6)
        ]

    assert [one.status_code for one in pressed(database, bad)] == [422] * 5
    assert sql(database, "SELECT count(*) FROM ops.budget_version")[0][0] == 0
