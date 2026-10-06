"""Budgets and rate limits as rows: the knobs, their bounds, what is in force, and the routes.

The domain half holds every knob against the figure it sets, read from the module that owns that
figure rather than from `brain.ops.tuning` itself, so a default that drifted from the budget or
window it sets is caught. The holding half shows a held value reaching the three readers the
request path and the Rate limits screen use, and a value outside the bounds never reaching them.
The route half drives the real application with `ops.setting` held in memory: who may read and
who may change, a refusal that writes nothing, and a save that writes the row as the person and is
in force on the next request.

Task ids: M22.1.2, M22.4.1
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.ops import admission, limits, tuning
from brain.ops.admission import Resource
from brain.ops.limits import LimitScope, declared_windows, limit_for, request_limits
from brain.settings_routes import INSTALL_SETTING_AUTHORITY
from brain.tables.config import SettingType
from brain.tuning_routes import TUNING_PATH
from tests.fixtures.console_http import Stub, console_client, get, headers
from tests.fixtures.setting_rows import SettingRows

SCREEN = f"{API_PREFIX}{TUNING_PATH}"

GRANTS = {
    "u_admin": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.unrestricted()),),
    # A reader of the Rate limits screen: its capability, and a console plane admitting it.
    "u_wide": (
        Grant(capability=Capability(value="read:rate_limit"), scope=Scope.unrestricted()),
        Grant(capability=plane_capability(Plane.CONTENT), scope=Scope.unrestricted()),
    ),
    "u_narrow": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


@pytest.fixture(autouse=True)
def nothing_held() -> Iterator[None]:
    """Every test starts with nothing held and leaves what was held before it."""
    before = tuning.hold({})
    yield
    tuning.hold(before)


# ------------------------------------------------------------------------ the knobs
def test_every_budget_row_the_product_seeds_has_exactly_one_knob_with_the_seed_as_its_default() -> (
    None
):
    """Held against `seed_budgets`, the module that owns the figures. Delete this and a budget can
    be added with no knob, so it can never be changed without a release, or a knob's default can
    drift from the budget it sets and the screen shows a figure admission does not use."""
    seeds = admission.seed_budgets()
    for seed in seeds:
        knob = tuning.budget_knob(seed.resource, seed.key)
        assert knob is not None, seed.budget_key
        assert knob.default == seed.limit
    budget_knobs = tuning.knobs_of(tuning.KnobKind.BUDGET)
    assert len(budget_knobs) == len(seeds)


def test_every_request_window_knob_defaults_to_the_limits_module_s_own_figure() -> None:
    """Held against `brain.ops.limits`' constants. Delete this and a knob's default could say
    thirty while the product's window is twenty, and nothing saved would still change the figure."""
    expected = {
        LimitScope.PRINCIPAL: limits.DEFAULT_PRINCIPAL_PER_MINUTE,
        LimitScope.CHANNEL: limits.DEFAULT_CHANNEL_PER_MINUTE,
        LimitScope.AGENT: limits.DEFAULT_AGENT_PER_MINUTE,
    }
    rates = {one.scope: one.default for one in tuning.knobs_of(tuning.KnobKind.RATE)}
    assert rates == expected


def test_a_source_budget_is_never_allowed_past_what_the_source_s_own_ceiling_supports() -> None:
    """Little's law over each verified source's documented ceiling at the five-second timeout.
    Delete this and a bound could admit more calls in flight than the vendor serves, which buys
    nothing but refusals from the source."""
    for name in ("lark_base", "xero"):
        ceiling = limits.connector_ceiling(name)
        assert ceiling is not None
        per_second = ceiling.per_minute / 60.0
        knob = tuning.budget_knob(Resource.SOURCE_CALLS, name)
        assert knob is not None
        assert knob.highest <= int(per_second * 5.0) + 1


def test_a_knob_whose_default_is_outside_its_bounds_or_admits_zero_is_refused() -> None:
    """Delete this and a knob can be declared whose own default the save route would refuse, or
    one that lets a person switch a door off while it reads as configured."""
    with pytest.raises(ValueError, match="outside its own bounds"):
        tuning.Knob("x", tuning.KnobKind.BUDGET, "x", "u", 9, 1, 8, "", Resource.MODEL_CALLS)
    with pytest.raises(ValueError, match="below one"):
        tuning.Knob("x", tuning.KnobKind.BUDGET, "x", "u", 1, 0, 8, "", Resource.MODEL_CALLS)
    with pytest.raises(ValueError, match="names a resource"):
        tuning.Knob("x", tuning.KnobKind.BUDGET, "x", "u", 1, 1, 8, "")
    with pytest.raises(ValueError, match="names a window"):
        tuning.Knob("x", tuning.KnobKind.RATE, "x", "u", 1, 1, 8, "")
    assert tuning.Knob("x", tuning.KnobKind.RATE, "x", "u", 1, 1, 8, "", scope=LimitScope.AGENT)


def test_a_value_is_refused_outside_its_bounds_or_when_it_is_not_a_whole_number() -> None:
    """The route's only judgement. Delete this and a zero window, a fraction, a string or an
    unknown knob can be saved; the sibling assertion is that a value at either bound is taken."""
    knob = tuning.KNOB_BY_NAME["person_per_minute"]
    assert tuning.problem(knob.name, knob.lowest) == ""
    assert tuning.problem(knob.name, knob.highest) == ""
    assert f"between {knob.lowest:,} and {knob.highest:,}" in tuning.problem(knob.name, 0)
    assert tuning.problem(knob.name, knob.highest + 1).startswith(knob.label)
    assert tuning.problem(knob.name, 2.5) == f"{knob.label} is a whole number."
    assert tuning.problem(knob.name, True) == f"{knob.label} is a whole number."
    assert tuning.problem(knob.name, "30") == f"{knob.label} is a whole number."
    assert tuning.problem("no_such_knob", 5) == tuning.NOT_A_KNOB


# ------------------------------------------------------------------------ in force
def test_a_held_window_is_what_the_request_path_the_screen_and_the_live_windows_all_count() -> None:
    """The three readers ask one function, so one saved value moves all three. Delete this and the
    request could count against a saved twelve while the screen lists thirty, or the live window
    be judged against a limit the request never used."""
    tuning.hold({"person_per_minute": 12, "channel_per_minute": 300, "agent_per_minute": 20})
    counted = request_limits(principal_id="u_one", channel="api", agent_id="a_one")
    assert [one.limit for one in counted] == [12, 300, 20]
    judged = limit_for(counted[0].key)
    assert judged is not None and judged.limit == 12
    declared = {one.applies_to: one.limit for one in declared_windows({})}
    assert declared["each person"] == 12
    assert declared["each channel"] == 300
    assert declared["each agent"] == 20


def test_an_explicit_allowance_still_outranks_what_is_held() -> None:
    """A caller that names its allowance, as the acceptance checks do, is counted at it. Delete
    this and a check filling a window of two is judged against thirty and never refused."""
    tuning.hold({"person_per_minute": 12})
    assert request_limits(principal_id="u", channel="c", principal_per_minute=2)[0].limit == 2


def test_nothing_held_and_a_held_value_outside_the_bounds_both_read_as_the_product_s_figure() -> (
    None
):
    """`A_SAVED_VALUE_OUTSIDE_THE_BOUNDS_IS_NOT_USED`. Delete this and a row saved under a wider
    bound in an older release holds the install outside what the product now admits."""
    assert request_limits(principal_id="u", channel="c")[0].limit == 30
    tuning.hold({"person_per_minute": 100_000, "document_jobs": 0})
    assert request_limits(principal_id="u", channel="c")[0].limit == 30
    rows = {one.budget_key: one for one in tuning.configured_budgets()}
    assert rows[(Resource.DOCUMENT_JOBS, "")].limit == 4
    assert rows[(Resource.DOCUMENT_JOBS, "")].source == "seed"


def test_a_saved_budget_is_laid_over_its_seed_row_and_says_it_was_saved() -> None:
    """What admission reads. Delete this and a saved budget can be dropped on the way to the
    queued upload's decision, with the screen showing the new figure."""
    saved = {"document_jobs": 2, "source_calls_xero": 3}
    rows = {one.budget_key: one for one in tuning.configured_budgets(saved)}
    assert rows[(Resource.DOCUMENT_JOBS, "")].limit == 2
    assert rows[(Resource.DOCUMENT_JOBS, "")].source == "saved"
    assert rows[(Resource.SOURCE_CALLS, "xero")].limit == 3
    assert rows[(Resource.MODEL_CALLS, "")].source == "seed"
    assert len(rows) == len(admission.seed_budgets())


def test_holding_drops_a_name_that_is_not_a_knob_and_returns_what_it_replaced() -> None:
    """Delete this and a stray row under the namespace becomes configuration nothing declares, or
    a test that holds a value cannot put the process back."""
    assert tuning.hold({"person_per_minute": 12, "not_a_knob": 3}) == {}
    assert dict(tuning.held()) == {"person_per_minute": 12}
    assert dict(tuning.hold({})) == {"person_per_minute": 12}


def test_the_intake_route_decides_from_the_configured_budgets_and_not_the_seed() -> None:
    """The call site, read as structure: the argument `admit_ingestion` is handed. Delete this and
    the route can go back to `seed_budgets()`, and a saved budget changes the screen and nothing
    the queue decides."""
    import ast
    import inspect

    import brain.knowledge_intake_routes as intake

    tree = ast.parse(inspect.getsource(intake))
    handed = [
        ast.unparse(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "admit_ingestion"
        for keyword in node.keywords
        if keyword.arg == "budgets"
    ]
    assert handed == ["configured_budgets()"]


# ------------------------------------------------------------------------ the routes
@pytest.fixture
def rows() -> SettingRows:
    return SettingRows()


@pytest.fixture
def served(rows: SettingRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(rows.answer)
        yield client, stub


def put(client: TestClient, pid: str, name: str, value: Any) -> Any:
    return client.put(f"{SCREEN}/{name}", json={"value": value}, headers=headers(pid))


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
def test_a_caller_who_may_neither_read_the_screen_nor_change_settings_is_refused_before_a_read(
    pid: str,
) -> None:
    """One refusal for the read and the write, with and without a database, and nothing sent to
    the database. Delete this and a department's administrator sees or sets the whole install's
    windows."""
    for database in (True, False):
        with console_client(GRANTS, database=database) as (client, stub):
            assert get(client, pid, SCREEN).status_code == 404
            assert put(client, pid, "person_per_minute", 12).status_code == 404
            assert stub.statements == []


def test_a_reader_of_the_screen_sees_every_knob_and_may_not_change_one(
    served: tuple[TestClient, Stub],
) -> None:
    """The read is the screen's and the write the Settings authority's. Delete this and the
    console draws a control for somebody the write refuses, or refuses them the figures."""
    client, stub = served
    body = get(client, "u_wide", SCREEN).json()
    assert body["may_change"] is False
    assert [one["name"] for one in body["knobs"]] == [
        one.name for one in tuning.KNOBS if one.kind in tuning.LIMIT_KINDS
    ]
    assert put(client, "u_wide", "person_per_minute", 12).status_code == 404
    assert stub.statements == []


def test_saving_a_window_writes_its_row_as_the_person_and_the_next_request_counts_against_it(
    served: tuple[TestClient, Stub], rows: SettingRows
) -> None:
    """The whole path: the row under the namespace, typed as a whole number and written by the
    person, held by this process, and in force on the request path and the screen. Delete this
    and a save can land in the table and change nothing until a restart."""
    client, _ = served
    answer = put(client, "u_admin", "person_per_minute", 12)
    assert answer.status_code == 200
    assert rows.writes == [
        {
            "key": "tuning.person_per_minute",
            "value_type": SettingType.INTEGER.value,
            "value": 12,
            "updated_by": "u_admin",
        }
    ]
    knob = next(one for one in answer.json()["knobs"] if one["name"] == "person_per_minute")
    assert (knob["value"], knob["saved"], knob["default"]) == (12, True, 30)
    assert answer.json()["may_change"] is True
    assert request_limits(principal_id="u_one", channel="api")[0].limit == 12


def test_a_value_outside_the_bounds_is_refused_in_words_and_nothing_is_written(
    served: tuple[TestClient, Stub], rows: SettingRows
) -> None:
    """Delete this and a person can save a window of zero, which refuses everybody while the
    screen reads as configured, or a string the reload then cannot read."""
    client, stub = served
    refused = put(client, "u_admin", "person_per_minute", 0)
    assert refused.status_code == 422
    assert "between 5 and 120" in refused.json()["message"]
    assert put(client, "u_admin", "person_per_minute", "12").status_code == 422
    assert put(client, "u_admin", "not_a_knob", 12).status_code == 422
    assert rows.writes == []
    assert not [one for one in stub.statements if "INSERT" in str(one).upper()]


# ------------------------------------------------------------------------ the reload
@pytest.mark.needs_db
def test_every_reload_of_saved_settings_holds_the_saved_limits_and_names_a_changed_one() -> None:
    """**The path a change takes to every process, against PostgreSQL at head.** A saved window is
    held by the application's start-up reload, and the worker's per-tick reload names it when it
    changes, as the application role reads it. Delete this and a limit saved on the screen reaches
    the process that saved it and no other until somebody restarts the install."""
    import asyncio

    from brain.db import normalise_database_url
    from brain.ops.install_settings import refresh, refresh_changed
    from brain.session import make_app_engine, make_session_factory
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head

    def saved(amount: int) -> None:
        sql(
            url,
            "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
            " VALUES ('tuning.person_per_minute', 'integer', to_jsonb(%s::int), 'a window',"
            " 'u_admin') ON CONFLICT (key) WHERE deleted_at IS NULL"
            " DO UPDATE SET value = excluded.value",
            amount,
        )

    async def reloads() -> tuple[dict[str, int], tuple[str, ...], tuple[str, ...]]:
        engine = make_app_engine(normalise_database_url(url))
        try:
            sessions = make_session_factory(engine)
            await refresh(sessions)
            first = dict(tuning.held())
            unchanged = await refresh_changed(sessions)
            saved(14)
            changed = await refresh_changed(sessions)
            return first, unchanged, changed
        finally:
            await engine.dispose()

    with at_head("brain_tuning_reload") as url:
        saved(12)
        first, unchanged, changed = asyncio.run(reloads())

    assert first == {"person_per_minute": 12}
    assert "tuning.person_per_minute" not in unchanged
    assert "tuning.person_per_minute" in changed
    assert tuning.value("person_per_minute") == 14
