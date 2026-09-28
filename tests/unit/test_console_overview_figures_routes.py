"""The landing screen's figure row over HTTP: who may read it, whose requests and whose cost it
counts, and that a cost nothing could have written is named rather than served as nought.

Driven through the real application with signed-in people and a stub where the pool is, and then
the two statements themselves against a real PostgreSQL, where rows of two people inside and
outside the window prove the WHERE clauses rather than a description of them. The database half
skips without `DATABASE_URL`, and CI always sets it.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql.selectable import Select

from brain import console_overview_figures_routes as figures_routes
from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import Basis
from brain.console_overview_figures_routes import (
    COST_HAS_NO_PRICE,
    COST_IS_NOT_RECORDED,
    FIGURES_PATH,
    OverviewFiguresView,
    request_cost,
    request_outcomes,
)
from brain.core.entitlement import Capability, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.locale import LocaleError
from brain.models.pricing import Price, stored_of
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.price_store import price_key
from brain.ops.spend import Actual
from brain.ops.spend_store import record as record_cost
from brain.ops.telemetry import RequestStatus, RequestTelemetry
from brain.tables.config import SettingType
from tests.fixtures.console_http import Stub, console_client, get
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, run
from tests.fixtures.setting_rows import Result, Row, SettingRows
from tests.unit.test_telemetry_store import LATER, a_row, write_as_app

FIGURES = f"{API_PREFIX}{FIGURES_PATH}"
EVERYWHERE = Scope.unrestricted()
PLANES = tuple(Grant(capability=plane_capability(one), scope=EVERYWHERE) for one in Plane)


def read(key: str) -> Capability:
    return screen(key).read.requires


#: `u_wide` opens the overview and reads the Usage and Budget screens over everything, so they
#: are counted everybody's requests and everybody's cost. `u_elsewhere` reads Usage and not
#: Budget, so they are counted everybody's requests and only their own cost. `u_narrow` opens the
#: overview only, so both are their own. `u_none` holds nothing, so the figures are not theirs.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_wide": (
        *PLANES,
        *(Grant(capability=read(key), scope=EVERYWHERE) for key in ("overview", "usage", "budget")),
    ),
    "u_elsewhere": (
        *PLANES,
        *(Grant(capability=read(key), scope=EVERYWHERE) for key in ("overview", "usage")),
    ),
    "u_narrow": (*PLANES, Grant(capability=read("overview"), scope=EVERYWHERE)),
    "u_none": (),
}

#: The currency the install counts in, for every test here. Patched where the route reads it.
INSTALL_CURRENCY = "SGD"

#: What the stub sums the week's cost to, as PostgreSQL sends a sum of a bigint: a numeric.
WEEK_COST = Decimal(128450)


def a_price(currency: str = INSTALL_CURRENCY) -> Price:
    return Price(input_minor=Decimal(300), output_minor=Decimal(1500), currency=currency)


def is_outcomes(statement: Any) -> bool:
    """Whether a statement is `request_outcomes`': a status and a count, grouped."""
    if not isinstance(statement, Select):
        return False
    return [one["name"] for one in statement.column_descriptions] == ["status", "count"]


def is_cost(statement: Any) -> bool:
    """Whether a statement is `request_cost`': one sum, named for the field it becomes."""
    if not isinstance(statement, Select):
        return False
    return [one["name"] for one in statement.column_descriptions] == ["cost_minor"]


class Outcomes:
    """Answers `request_outcomes` with fixed counts, including a status the page never shows,
    and `request_cost` with `cost`."""

    def __init__(self, cost: Decimal = WEEK_COST) -> None:
        self.cost = cost

    def answer(self, statement: Any) -> Result | None:
        if is_cost(statement):
            return Result([Row((self.cost,))])
        if not is_outcomes(statement):
            return None
        return Result(
            [
                Row((RequestStatus.ANSWERED.value, 41)),
                Row((RequestStatus.NOTHING_RETURNED.value, 6)),
                Row((RequestStatus.FAILED.value, 2)),
            ]
        )


def settings_with(*prices: tuple[str, str, Price]) -> SettingRows:
    """`ops.setting` holding these prices as the price store keeps them, one row per provider."""
    rows = SettingRows()
    by_provider: dict[str, dict[str, Any]] = {}
    for provider, model, price in prices:
        by_provider.setdefault(provider, {})[model] = stored_of(price)
    for provider, models in by_provider.items():
        rows.hold(price_key(provider), models, value_type=SettingType.JSON.value)
    return rows


@contextmanager
def serving(
    monkeypatch: pytest.MonkeyPatch,
    *prices: tuple[str, str, Price],
    cost: Decimal = WEEK_COST,
) -> Iterator[tuple[TestClient, Stub]]:
    """The application, an install counting in `INSTALL_CURRENCY`, and these prices set."""
    monkeypatch.setattr(figures_routes, "install_currency", lambda: INSTALL_CURRENCY)
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(Outcomes(cost).answer)
        stub.answerers.append(settings_with(*prices).answer)
        yield client, stub


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Stub]]:
    with serving(monkeypatch, ("anthropic", "a-model", a_price())) as both:
        yield both


def figures_of(client: TestClient, pid: str) -> OverviewFiguresView:
    response = get(client, pid, FIGURES)
    assert response.status_code == 200, response.text
    return OverviewFiguresView.model_validate(response.json())


def outcome_statements(stub: Stub) -> list[Select[Any]]:
    return [one for one in stub.statements if is_outcomes(one)]


def cost_statements(stub: Stub) -> list[Select[Any]]:
    return [one for one in stub.statements if is_cost(one)]


def test_a_reader_of_the_usage_screen_is_counted_everybodys_requests_by_how_they_ended(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case: answered and nothing returned are the database's counts, a failed
    request is in neither, and the statement carries no person. Delete this and the figure row
    could draw the wrong status, or everybody's figures could be narrowed to nobody's."""
    client, stub = served
    body = figures_of(client, "u_wide")

    assert (body.basis, body.answered, body.nothing_returned) == (Basis.EVERYONE.value, 41, 6)
    assert body.range == "7d"
    assert body.until - body.since == timedelta(days=7)
    (statement,) = outcome_statements(stub)
    assert "u_wide" not in statement.compile().params.values()


def test_a_reader_without_the_usage_screen_is_counted_their_own_requests_in_the_statement(
    served: tuple[TestClient, Stub],
) -> None:
    """The narrowing: a reader who could not open Usage is told whose figures these are, and
    the statement itself names them, so nobody else's request is counted for them. Delete this
    and a landing screen could show a colleague's activity to anybody who may open it."""
    client, stub = served
    body = figures_of(client, "u_narrow")

    assert body.basis == Basis.OWN.value
    (statement,) = outcome_statements(stub)
    assert "u_narrow" in statement.compile().params.values()


def test_a_reader_who_may_not_open_the_overview_is_refused_before_anything_is_read(
    served: tuple[TestClient, Stub],
) -> None:
    """The refusal, and its order: a 404 with no statement sent. Delete this and a reader with
    no grant could learn how many requests the company made last week."""
    client, stub = served
    response = get(client, "u_none", FIGURES)

    assert response.status_code == 404
    assert outcome_statements(stub) == []


def test_a_reader_of_the_budget_screen_is_told_everybodys_cost_in_the_installs_currency(
    served: tuple[TestClient, Stub],
) -> None:
    """The positive case for cost, which replaces the tripwire that stood here while nothing wrote
    one: the week's sum is served in whole minor units of the install's currency, on the Budget
    screen's basis, with no person in the statement and no sentence saying it is not recorded.
    Delete this and the figure row could go back to naming cost as not recorded on an install that
    records it, or send a sum in no currency."""
    client, stub = served
    body = figures_of(client, "u_wide")

    assert (body.cost_basis, body.cost_minor, body.currency) == (
        Basis.EVERYONE.value,
        int(WEEK_COST),
        INSTALL_CURRENCY,
    )
    assert body.not_recorded == []
    (statement,) = cost_statements(stub)
    assert "u_wide" not in statement.compile().params.values()


def test_a_reader_without_the_budget_screen_is_summed_their_own_cost_in_the_statement(
    served: tuple[TestClient, Stub],
) -> None:
    """The narrowing, and the no-hidden-total rule for money: a reader who may read everybody's
    usage but not everybody's spend is counted everybody's requests and summed only their own
    cost, told so apart, and no statement summing anybody else's is sent for them. The same holds
    for a reader of neither screen. Delete this and the landing screen is a way to read the
    company's spend without the Budget screen's grant."""
    client, stub = served
    usage_only = figures_of(client, "u_elsewhere")
    narrow = figures_of(client, "u_narrow")

    assert (usage_only.basis, usage_only.cost_basis) == (Basis.EVERYONE.value, Basis.OWN.value)
    assert (narrow.basis, narrow.cost_basis) == (Basis.OWN.value, Basis.OWN.value)
    first, second = cost_statements(stub)
    assert "u_elsewhere" in first.compile().params.values()
    assert "u_narrow" in second.compile().params.values()


def test_a_week_with_no_cost_is_nought_once_a_model_has_a_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nought is served when it was measured: recording is on, a model is priced in the install's
    currency, and the reader's rows sum to nothing. Delete this and the no-price rule below could be
    widened to every empty week, so a quiet install would read as unrecorded for ever."""
    with serving(monkeypatch, ("anthropic", "a-model", a_price()), cost=Decimal(0)) as (
        client,
        _,
    ):
        body = figures_of(client, "u_narrow")

    assert (body.cost_minor, body.currency, body.not_recorded) == (0, INSTALL_CURRENCY, [])


@pytest.mark.parametrize(
    "prices",
    [(), (("anthropic", "a-model", a_price("EUR")),)],
    ids=["no price at all", "a price only in another currency"],
)
def test_an_install_with_no_model_priced_in_its_currency_is_told_cost_is_not_recorded(
    monkeypatch: pytest.MonkeyPatch, prices: tuple[tuple[str, str, Price], ...]
) -> None:
    """The recorder writes no cost for a call to an unpriced model, so on an install where no model
    has a price in its currency a sum would be nought for a company that has spent money. The
    figure is null, its currency with it, the sentence says why, and nothing is summed. Delete this
    and the Overview draws 0.00 on every install that has not set a price."""
    with serving(monkeypatch, *prices) as (client, stub):
        body = figures_of(client, "u_wide")

    assert (body.cost_minor, body.currency) == (None, None)
    assert body.not_recorded == [COST_HAS_NO_PRICE]
    assert cost_statements(stub) == []


def test_a_currency_that_does_not_resolve_is_one_no_price_is_in(
    monkeypatch: pytest.MonkeyPatch, served: tuple[TestClient, Stub]
) -> None:
    """A misspelled install currency cannot be the one a price was set in, so the figure is not
    recorded rather than a refusal that takes the request counts with it. Delete this and a typo in
    a setting blanks the landing screen's figure row."""

    def unresolved() -> str:
        raise LocaleError("not a currency")

    monkeypatch.setattr(figures_routes, "install_currency", unresolved)
    client, stub = served
    body = figures_of(client, "u_wide")

    assert (body.answered, body.cost_minor, body.not_recorded) == (41, None, [COST_HAS_NO_PRICE])
    assert cost_statements(stub) == []


def test_while_nothing_records_a_requests_cost_it_is_named_and_never_summed(
    monkeypatch: pytest.MonkeyPatch, served: tuple[TestClient, Stub]
) -> None:
    """The flag the agent pages read still governs this route: on a release where nothing writes a
    cost, cost travels as its sentence, no price is read and nothing is summed. Delete this and the
    route could serve a sum over a table nothing fills the day recording is switched off."""
    monkeypatch.setattr(figures_routes, "RUN_SPEND_IS_RECORDED", False)
    client, stub = served
    body = figures_of(client, "u_wide")

    assert (body.cost_minor, body.currency) == (None, None)
    assert body.not_recorded == [COST_IS_NOT_RECORDED]
    assert cost_statements(stub) == []
    assert COST_IS_NOT_RECORDED.figure == COST_HAS_NO_PRICE.figure == "cost"
    assert COST_IS_NOT_RECORDED.why != COST_HAS_NO_PRICE.why


def test_no_field_on_the_answer_is_a_count_of_what_was_withheld() -> None:
    """Read off the model rather than trusted to a reviewer. Delete this and a field named like
    a total could be added beside a figure that was narrowed to the reader."""
    names = set(OverviewFiguresView.model_fields)
    assert names.isdisjoint(NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT)
    assert {"cost_minor", "currency", "cost_basis"} <= names


# --- the statement against a real server ----------------------------------------------------


DATABASE = "brain_test_overview_figures"


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """`0034` and `0043` for the cost table, `0039`, `0100` and `0113` for the ledger.

    Each run for real after a stamp of its predecessor, because neither table points at anything
    the stamped migrations build, and `0001` needs pgvector, which the scratch server may not have.
    """
    scratch = fresh(DATABASE)
    try:
        migrate(DATABASE, "stamp", "0033")
        migrate(DATABASE, "upgrade", "0034")
        migrate(DATABASE, "stamp", "0038")
        migrate(DATABASE, "upgrade", "0039")
        migrate(DATABASE, "stamp", "0042")
        migrate(DATABASE, "upgrade", "0043")
        migrate(DATABASE, "stamp", "0097")
        migrate(DATABASE, "upgrade", "0100")
        migrate(DATABASE, "stamp", "0108")
        migrate(DATABASE, "upgrade", "0113")
        yield scratch
    finally:
        drop(DATABASE)


def telemetry(principal: str, at: datetime, status: RequestStatus, trace: str) -> RequestTelemetry:
    return dataclasses.replace(a_row(trace, at=at, status=status), principal=principal)


def counted(database: str, *, basis: Basis, caller: str) -> dict[str, int]:
    since, until = LATER - timedelta(days=7), LATER

    async def go() -> dict[str, int]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                rows = await session.execute(
                    request_outcomes(since, until, basis=basis, caller_id=caller)
                )
                return {str(status): int(count) for status, count in rows.all()}
        finally:
            await bound.dispose()

    return run(go)


def test_the_statement_counts_the_window_and_on_the_narrower_basis_only_the_caller(
    database: str,
) -> None:
    """Rows of two people, inside and outside the week, read back as the application role.
    Delete this and the WHERE clause is proved only by the words the stub test compiles, never by
    a server honouring them."""
    inside = LATER - timedelta(days=1)
    before = LATER - timedelta(days=8)
    write_as_app(
        database,
        telemetry("u_one", inside, RequestStatus.ANSWERED, "t-a"),
        telemetry("u_one", inside, RequestStatus.ANSWERED, "t-b"),
        telemetry("u_one", inside, RequestStatus.NOTHING_RETURNED, "t-c"),
        telemetry("u_two", inside, RequestStatus.ANSWERED, "t-d"),
        telemetry("u_one", before, RequestStatus.ANSWERED, "t-e"),
    )

    assert counted(database, basis=Basis.EVERYONE, caller="u_one") == {
        RequestStatus.ANSWERED.value: 3,
        RequestStatus.NOTHING_RETURNED.value: 1,
    }
    assert counted(database, basis=Basis.OWN, caller="u_one") == {
        RequestStatus.ANSWERED.value: 2,
        RequestStatus.NOTHING_RETURNED.value: 1,
    }
    assert counted(database, basis=Basis.OWN, caller="u_three") == {}


def cost(principal: str, at: datetime, minor: int, trace: str) -> Actual:
    return Actual(
        principal_id=principal,
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        department="support",
        agent_id=None,
        model="a-model",
        lane=Lane.FAST,
        cost_minor=minor,
        at=at,
        trace_id=trace,
    )


def paid_as_app(database: str, *costs: Actual) -> None:
    async def go() -> None:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                for one in costs:
                    await record_cost(session, one)
                await session.commit()
        finally:
            await bound.dispose()

    run(go)


def summed(database: str, *, basis: Basis, caller: str) -> int:
    since, until = LATER - timedelta(days=7), LATER

    async def go() -> int:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                rows = await session.execute(
                    request_cost(since, until, basis=basis, caller_id=caller)
                )
                ((total,),) = rows.all()
                return int(total)
        finally:
            await bound.dispose()

    return run(go)


def test_the_cost_statement_sums_the_window_and_on_the_narrower_basis_only_the_caller(
    database: str,
) -> None:
    """Costs of two people, inside and outside the week, summed back as the application role, and
    a caller with no cost summed to nought rather than to nothing. Delete this and the cost's
    WHERE clause is proved only by the words the stub test compiles, and a sum over no rows could
    come back null, which the route would refuse rather than serve as the nought it is."""
    inside = LATER - timedelta(days=1)
    before = LATER - timedelta(days=8)
    paid_as_app(
        database,
        cost("u_one", inside, 250, "c-a"),
        cost("u_one", LATER, 100, "c-b"),
        cost("u_two", inside, 4000, "c-c"),
        cost("u_one", before, 99999, "c-d"),
    )

    assert summed(database, basis=Basis.EVERYONE, caller="u_one") == 4350
    assert summed(database, basis=Basis.OWN, caller="u_one") == 350
    assert summed(database, basis=Basis.OWN, caller="u_three") == 0
