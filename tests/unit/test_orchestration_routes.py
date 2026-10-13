"""The plan-weighing routes: refused before the database to anybody without the authority, refused
while the switch is off, a plan that is not one refused in the graph's own words, results checked
and merged with a stated gap, and a kept decision rebuilt through the record that refuses an
untrue one.

The stub holds `ops.setting` in memory and answers the one read of `ops.fanout_gate`; the write is
proved against PostgreSQL by `brain.ops.acceptance_checks_orchestration_rehearsal`.

Task ids: M18.1.3, M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.4.1, M18.4.2, M18.4.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.ops import fanout_gate_store
from brain.ops.acceptance_checks_orchestration_rehearsal import _chain_plan, _split_plan
from brain.ops.features import ORCHESTRATION_REHEARSAL
from brain.orchestration.fanout import FanOutError
from brain.orchestration_routes import REHEARSAL_AUTHORITY, RehearsalAsked, merged_of
from brain.routers import ROUTERS
from brain.tables.fanout_gate import FanoutGateRow
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import Result, SettingRows

PATH = f"{API_PREFIX}/orchestration/rehearsals"
EVERYWHERE = Scope.unrestricted()

GRANTS = {
    "u_admin": (Grant(capability=REHEARSAL_AUTHORITY, scope=EVERYWHERE),),
    "u_narrow": (Grant(capability=REHEARSAL_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


def stored(**overrides: Any) -> SimpleNamespace:
    """A row of `ops.fanout_gate` as the read returns one: the split plan's decision."""
    row: dict[str, Any] = {
        "run_id": "rehearsal-1",
        "decided_at": datetime(2019, 1, 1, tzinfo=UTC),
        "decided_by": "u_admin",
        "branches": 4,
        "depth": 0,
        "cost_multiplier": 1.0,
        "speedup": 4.0,
        "largest_share": 0.25,
        "evaluated": [
            "enough_branches",
            "within_run_concurrency",
            "within_depth",
            "cost_multiplier_bounded",
            "speedup_worth_it",
            "no_branch_dominates",
        ],
        "failed": [],
        "verdict": "parallel",
    }
    row.update(overrides)
    return SimpleNamespace(**row)


class Gates:
    """The one read of `ops.fanout_gate`, answering the rows a test holds."""

    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        if statement.column_descriptions[0].get("entity") is not FanoutGateRow:
            return None
        return Result(self.rows)


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def gates() -> Gates:
    return Gates()


@pytest.fixture
def served(settings: SettingRows, gates: Gates) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, gates.answer])
        yield client, stub


def test_the_router_is_mounted_by_the_application() -> None:
    """Delete this and the routes can be written, tested and never served."""
    assert any(
        getattr(one, "path", "") == PATH.removeprefix("")
        for router in ROUTERS
        for one in router.routes
    )


# -------------------------------------------------------------------------- the authority
@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_a_caller_without_the_authority_over_everything_is_refused_before_the_database(
    pid: str, method: str
) -> None:
    """The same refusal with a database and without one, naming no capability, and no statement
    reaches a store.

    Delete this and a department-scoped holder weighs plans for the whole install, or a caller
    with nothing learns whether this process has a pool."""

    def call(client: TestClient) -> Any:
        return get(client, pid, PATH) if method == "GET" else post(client, pid, PATH, _split_plan())

    with console_client(GRANTS, database=False) as (client, _):
        without = call(client)
    with console_client(GRANTS) as (client, stub):
        with_pool = call(client)
    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert REHEARSAL_AUTHORITY.value not in with_pool.json()["message"]
    assert stub.statements == []


def test_a_password_only_sign_in_holding_the_authority_is_refused(
    served: tuple[TestClient, Stub],
) -> None:
    """`brain.gate.admission` withholds `admin:` from a session with no second factor.

    Delete this and a stolen password alone weighs plans and writes a row."""
    client, stub = served
    assert post(client, "u_admin", PATH, _split_plan(), strong=False).status_code == 404
    assert stub.statements == []


# --------------------------------------------------------------------------- the list
def test_the_list_draws_the_decisions_kept_and_says_whether_weighing_is_on(
    served: tuple[TestClient, Stub], gates: Gates, settings: SettingRows
) -> None:
    """A kept row comes back as the record it was, with who asked.

    Delete this and the page can draw a decision that is not the one stored."""
    gates.rows.append(stored())
    settings.hold(ORCHESTRATION_REHEARSAL.key, True, value_type="boolean")
    client, _ = served
    body = get(client, "u_admin", PATH).json()
    assert body["rehearsal_is_on"] is True
    [one] = body["decisions"]
    assert (one["verdict"], one["branches"], one["decided_by"], one["failed"]) == (
        "parallel",
        4,
        "u_admin",
        [],
    )
    assert len(one["evaluated"]) == 6


def test_a_stored_row_that_says_parallel_after_a_failure_does_not_come_back(
    served: tuple[TestClient, Stub],
) -> None:
    """Rebuilt through `GateRecord`, which refuses a split that names a failure.

    Delete this and a row the table somehow admitted is drawn as something the gate never said."""
    with pytest.raises(FanOutError):
        fanout_gate_store.record_of(stored(failed=["enough_branches"]))  # type: ignore[arg-type]
    with pytest.raises(FanOutError):
        fanout_gate_store.record_of(stored(evaluated=["enough_branches"]))  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- the switch
def test_a_plan_is_not_weighed_while_the_switch_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a feature that ships off is on for every install the day it arrives."""
    client, stub = served
    refused = post(client, "u_admin", PATH, _split_plan())
    assert refused.status_code == 404
    assert "switched off" in refused.json()["message"]
    assert stub.commits == 0
    assert settings.writes == []


# ---------------------------------------------------------------- a plan that is not one
@pytest.fixture
def switched_on(settings: SettingRows) -> None:
    settings.hold(ORCHESTRATION_REHEARSAL.key, True, value_type="boolean")


def test_a_dependency_on_a_subtask_the_plan_lacks_is_refused_in_the_graphs_words(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """Delete this and the gate decides over a plan smaller than the one that would run."""
    client, stub = served
    plan = _chain_plan()
    plan["subtasks"][1]["depends_on"] = ["ghost"]
    plan["coupling"] = [
        {"before": "ghost", "after": "second", "tokens": 1},
        {"before": "second", "after": "third", "tokens": 1},
    ]
    refused = post(client, "u_admin", PATH, plan)
    assert refused.status_code == 404
    assert "ghost" in refused.json()["message"]
    assert stub.commits == 0


def test_a_dependency_with_no_measured_coupling_is_refused(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """An unweighted edge would pass every condition. Delete this and a plan with an edge nobody
    priced is weighed as though the edge were free."""
    client, _ = served
    plan = _chain_plan()
    plan["coupling"] = []
    refused = post(client, "u_admin", PATH, plan)
    assert refused.status_code == 404
    assert "coupling" in refused.json()["message"]


def test_a_cycle_is_refused(served: tuple[TestClient, Stub], switched_on: None) -> None:
    """Delete this and a plan that can never start is weighed."""
    client, _ = served
    plan = _chain_plan()
    plan["subtasks"][0]["depends_on"] = ["third"]
    plan["coupling"].append({"before": "third", "after": "first", "tokens": 1})
    assert post(client, "u_admin", PATH, plan).status_code == 404


def test_a_plan_cannot_carry_its_own_weights(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """A subtask body naming a token figure is refused as an unknown field, so a rehearsal cannot
    be made to pass the gate with the number that makes it pass.

    Delete this and the estimator is optional."""
    client, _ = served
    plan = _split_plan()
    plan["subtasks"][0]["tokens"] = 1
    assert post(client, "u_admin", PATH, plan).status_code == 422


def test_a_subtask_promising_prose_is_refused(
    served: tuple[TestClient, Stub], switched_on: None
) -> None:
    """The six kinds are the whole vocabulary: there is no kind for a paragraph.

    Delete this and a contract can promise free text."""
    client, _ = served
    plan = _split_plan()
    plan["subtasks"][0]["output"] = [{"name": "summary", "kind": "prose"}]
    assert post(client, "u_admin", PATH, plan).status_code == 422


# ----------------------------------------------------------------------------- the merge
def _asked(**more: Any) -> RehearsalAsked:
    return RehearsalAsked.model_validate(_split_plan(**more))


def _contracts() -> Any:
    from brain.orchestration_routes import contracts_of

    return contracts_of(_asked())


def _returned(name: str, count: object, minor: int) -> dict[str, Any]:
    return {
        "subtask_id": name,
        "values": {"ref": f"ref_{name}", "count": count},
        "minor": minor,
        "seconds": 2.0,
    }


def test_a_result_that_breaks_its_contract_is_a_stated_gap_and_never_a_merge_input() -> None:
    """Delete this and M18.1.3 and M18.4.3 are claims about types with no route behind them."""
    body = _asked(
        returned=[
            _returned("part_a", 3, 4),
            _returned("part_b", 3, 5),
            _returned("part_c", 3, 6),
            _returned("part_d", "three", 7),
        ]
    )
    answer = merged_of("run", body, _contracts())
    assert sorted(answer.values) == ["part_a", "part_b", "part_c"]
    assert not answer.is_complete
    assert "part_d" in answer.notice(disclosable=frozenset({"part_d"}))
    assert answer.total_minor == 22


def test_a_subtask_nothing_was_handed_in_for_is_a_gap_with_no_cost_line() -> None:
    """Delete this and a subtask that never returned is charged for, or silently absent."""
    body = _asked(returned=[_returned("part_a", 3, 4)])
    answer = merged_of("run", body, _contracts())
    assert [one.subtask_id for one in answer.reports] == ["part_a"]
    assert {one.subtask_id for one in answer.gaps} == {"part_b", "part_c", "part_d"}


def test_a_run_of_four_that_all_kept_their_promise_is_complete_and_says_nothing() -> None:
    """The positive half. Delete this and a merge that reports every run incomplete is satisfied by
    the tests above."""
    body = _asked(returned=[_returned(f"part_{n}", 3, 4) for n in "abcd"])
    answer = merged_of("run", body, _contracts())
    assert answer.is_complete
    assert answer.notice(disclosable=frozenset(answer.values)) == ""
    assert answer.total_minor == 16


def test_a_result_for_a_subtask_the_plan_does_not_hold_is_refused() -> None:
    """Delete this and a result for nothing is merged under a name nobody planned."""
    body = _asked(returned=[_returned("part_z", 3, 1)])
    with pytest.raises(Absent):
        merged_of("run", body, _contracts())


def test_a_timestamp_arrives_as_text_and_is_read_as_one() -> None:
    """A timestamp field is ISO text in JSON, and a naive one is still refused.

    Delete this and the timestamp kind can never be satisfied over HTTP."""
    plan = _split_plan()
    for one in plan["subtasks"]:
        one["output"] = [{"name": "at", "kind": "timestamp"}]
    handed = [
        {"subtask_id": f"part_{n}", "values": {"at": "2019-03-04T09:00:00+00:00"}, "minor": 1}
        for n in "abcd"
    ]
    handed[3]["values"] = {"at": "2019-03-04T09:00:00"}
    body = RehearsalAsked.model_validate({**plan, "returned": handed})
    from brain.orchestration_routes import contracts_of

    answer = merged_of("run", body, contracts_of(body))
    assert sorted(answer.values) == ["part_a", "part_b", "part_c"]
    assert {one.subtask_id for one in answer.gaps} == {"part_d"}


def test_the_authority_is_a_capability_the_first_administrator_holds() -> None:
    """Delete this and the screen needs a grant nobody on a fresh install has."""
    from brain.identity.first_administrator import ADMINISTRATION

    assert isinstance(REHEARSAL_AUTHORITY, Capability)
    assert REHEARSAL_AUTHORITY.value in ADMINISTRATION
