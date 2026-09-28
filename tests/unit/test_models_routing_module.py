"""The Models and routing module's rebuild: retiring and moving a step, a provider's figures, its
last test, the providers list, the routing export, and the registry on the ledger.

Four layers, each where it is cheapest to be sure. The decisions (`placements`,
`levels_left_empty`, `overlaid`) are driven directly. The routes are driven through the real
application over the stub sessions `tests.unit.test_routing_routes` and
`tests.unit.test_provider_routes` already build, so a refusal and the statements a write makes are
inspected without a server. And the two things only PostgreSQL can say, that a move and a
retirement leave the rows, roles and ledger entries they claim and that `0140`'s trigger records a
registry row, run against a database built through the migrations that ship, as the application
role. **Those skip without a server**, which CI provides.

Task ids: M27.15.38, M5.3.3, M5.6.4, M27.16.1
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder, ProviderRegistryChange, RoutingChange
from brain.console.agent_profile import RUN_SPEND_IS_RECORDED
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.models.routing import Tier
from brain.ops.matrix_gate import (
    ALREADY_THERE,
    GateError,
    Placement,
    RungEdit,
    RungMove,
    RungRetirement,
    level_left_empty,
    levels_left_empty,
    overlaid,
    placements,
)
from brain.ops.setting_store import SettingState
from brain.provider_routes import (
    CHECK_NAMESPACE,
    COST_IS_NOT_SPLIT_BY_PROVIDER,
    FAILED_OUTCOMES,
    NO_COST_RECORDED,
    NO_STEP_NO_CALLS,
    NOT_SENT_OUTCOME,
    CheckView,
    check_value,
    checks_from,
    stats_view,
)
from brain.routing_routes import MATRIX_READ, MATRIX_WRITE
from brain.tables.identity import one_of
from brain.tables.model_registry import ChangeKind
from brain.tables.routing import ATTEMPT_OUTCOMES
from tests.fixtures.console_http import headers
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import sql
from tests.unit import test_routing_routes as routing
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_credential_writes import entries
from tests.unit.test_model_calls import rung
from tests.unit.test_provider_routes import PROVIDERS, Estate, call
from tests.unit.test_provider_routes import client as client  # the fixture, by its name
from tests.unit.test_provider_routes import estate as estate  # the fixture, by its name
from tests.unit.test_routing_routes import executed as executed  # the fixture, by its name
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0140_provider_registry_audit_and_rung_moves.py"
AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
EVERYWHERE = Scope.unrestricted()


def placed(*rows: tuple[str, Tier, int]) -> list[tuple[str, Tier, int]]:
    return list(rows)


# ------------------------------------------------------------------ retiring and moving a step


def test_a_retirement_takes_its_rung_off_the_copy_and_nothing_else() -> None:
    """The copy the gate tries for a retirement. Delete this and a trial could leave the retired
    rung in the ladder it judges, or take a neighbour out with it."""
    rungs = (rung("anthropic"), rung("moonshot", position=1), rung("openai", tier=Tier.HEAVY))

    trial = overlaid(rungs, RungRetirement(rung_id="main-1"), new_rung_id="unused")

    assert trial == (rungs[0], rungs[2])
    with pytest.raises(GateError):
        overlaid(rungs, RungRetirement(rung_id="main-9"), new_rung_id="unused")


def test_a_move_to_the_end_rewrites_the_moved_rung_alone_above_every_live_position() -> None:
    """Delete this and a move to the end could renumber rungs it never passed, each a retirement
    and an addition on the ledger that nothing happened to."""
    live = placed(("a", Tier.MAIN, 0), ("b", Tier.MAIN, 1), ("c", Tier.MAIN, 2))

    assert placements(live, RungMove(rung_id="a", tier=Tier.MAIN, step=3)) == (Placement("a", 3),)
    # A step past the end is the end.
    assert placements(live, RungMove(rung_id="a", tier=Tier.MAIN, step=9)) == (Placement("a", 3),)


def test_a_move_into_a_full_run_rewrites_it_and_the_rungs_after_at_fresh_positions() -> None:
    """The unique index is checked row by row, so a move never reuses a live position: the moved
    rung and the rungs after it take positions above every live one, in their new order. Delete
    this and a move collides with `uq_routing_rung_tier_position_live` halfway through."""
    live = placed(("a", Tier.MAIN, 0), ("b", Tier.MAIN, 1), ("c", Tier.MAIN, 2))

    to_top = placements(live, RungMove(rung_id="c", tier=Tier.MAIN, step=1))
    to_middle = placements(live, RungMove(rung_id="a", tier=Tier.MAIN, step=2))

    assert to_top == (Placement("c", 3), Placement("a", 4), Placement("b", 5))
    assert to_middle == (Placement("a", 3), Placement("c", 4))
    for moved in (to_top, to_middle):
        taken = {position for _, _, position in live}
        assert not taken & {one.position for one in moved}


def test_a_move_into_a_gap_takes_the_free_position_and_rewrites_nothing_else() -> None:
    """A retirement leaves a gap, and a move into it needs no renumbering. Delete this and every
    move after a retirement rewrites the whole level."""
    live = placed(("a", Tier.MAIN, 0), ("c", Tier.MAIN, 5), ("d", Tier.MAIN, 6))

    assert placements(live, RungMove(rung_id="d", tier=Tier.MAIN, step=2)) == (Placement("d", 4),)


def test_a_move_to_another_level_is_numbered_there_and_a_move_in_place_is_refused() -> None:
    """Delete this and a rung moved to another level could be placed by its old level's numbers,
    or a move that changes nothing could be sent through the gate and recorded as a change."""
    live = placed(("a", Tier.MAIN, 0), ("b", Tier.MAIN, 1), ("h", Tier.HEAVY, 0))

    assert placements(live, RungMove(rung_id="b", tier=Tier.HEAVY, step=1)) == (
        Placement("b", 1),
        Placement("h", 2),
    )
    with pytest.raises(GateError, match=ALREADY_THERE):
        placements(live, RungMove(rung_id="b", tier=Tier.MAIN, step=2))
    with pytest.raises(GateError):
        placements(live, RungMove(rung_id="b", tier=Tier.MAIN, step=0))


def test_the_copy_a_move_is_tried_on_walks_the_new_order() -> None:
    """The trial ladder is the ladder the move produces. Delete this and the gate could judge the
    old order and pass a move whose new order answers nothing."""
    rungs = (rung("anthropic"), rung("moonshot", position=1), rung("openai", position=2))

    trial = overlaid(rungs, RungMove(rung_id="main-2", tier=Tier.MAIN, step=1), new_rung_id="x")

    order = [one.provider for one in sorted(trial, key=lambda one: one.position)]
    assert order == ["openai", "anthropic", "moonshot"]


def test_a_change_that_would_empty_a_level_names_it_and_one_that_would_not_does_not() -> None:
    """The held reason names the level in the owner's word. Delete this and retiring a level's
    last step reaches the gate, whose golden questions may never ask that level."""
    live = placed(("a", Tier.MAIN, 0), ("b", Tier.MAIN, 1), ("s", Tier.SMALL, 0))

    assert levels_left_empty(live, RungRetirement(rung_id="s")) == (Tier.SMALL,)
    assert levels_left_empty(live, RungMove(rung_id="s", tier=Tier.MAIN, step=1)) == (Tier.SMALL,)
    assert levels_left_empty(live, RungRetirement(rung_id="a")) == ()
    assert levels_left_empty(live, RungMove(rung_id="a", tier=Tier.MAIN, step=2)) == ()
    assert levels_left_empty(live, RungEdit("s", 1, 1.0, 1, enabled=False)) == ()
    assert "Simple level with no step" in level_left_empty(Tier.SMALL)


def test_the_change_kinds_are_the_ones_0140_admits() -> None:
    """Delete this and a retirement or a move is refused by the database as a change of no kind."""
    module = migration_module(MIGRATION)
    assert one_of("kind", ChangeKind) == module.WIDENED_KINDS
    assert {"retire", "move"} <= {one.value for one in ChangeKind}


# ---------------------------------------------------------- the routes, over the stub session


@pytest.fixture
def matrix(executed: routing.Executed) -> Iterator[TestClient]:
    """`tests.unit.test_routing_routes`' application over its stub session and scripted gate."""
    app = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = routing._wiring()
        app.state.db_sessions = async_sessionmaker(class_=routing.StubSession)
        app.state.console_reads = None
        app.state.matrix_gate = routing.GATE
        routing.GATE.verdict = routing.PASSING
        routing.GATE.asked.clear()
        yield c


def post(c: TestClient, pid: str, path: str, body: object = None) -> Response:
    response: Response = c.post(path, headers=headers(pid), json=body)
    return response


def rung_path(row: Any, act: str) -> str:
    return f"{API_PREFIX}/routing/rungs/{row.id}/{act}"


def test_retiring_or_moving_needs_the_write_over_everything_and_is_refused_as_absent(
    matrix: TestClient, executed: routing.Executed
) -> None:
    """A reader of the matrix, a writer scoped elsewhere and a rung that is not there all get the
    one refusal. Delete this and a department-scoped editor could retire a step every department's
    questions walk, or learn which ids exist from the difference."""
    row = executed.rows[0]
    missing = f"{API_PREFIX}/routing/rungs/{uuid.uuid4()}/retire"
    answers = [
        post(matrix, "u_narrow", rung_path(row, "retire")).status_code,
        post(matrix, "u_narrow", rung_path(row, "move"), {"tier": "main", "step": 2}).status_code,
    ]
    executed.rows = ()
    answers.append(post(matrix, "u_admin", missing).status_code)

    assert answers == [404, 404, 404]
    assert routing.GATE.asked == []
    assert executed.changes == []


def test_a_retirement_that_would_empty_a_level_is_held_with_its_reason_and_the_gate_not_asked(
    matrix: TestClient, executed: routing.Executed
) -> None:
    """Delete this and retiring a level's last step reaches the gate, and the ledger can end up
    with a level nothing answers."""
    only = routing.rung(position=0, tier="small")
    executed.rows = (only,)

    answer = post(matrix, "u_admin", rung_path(only, "retire"))

    assert answer.status_code == 200
    body = answer.json()
    assert (body["kind"], body["status"]) == ("retire", "held")
    assert body["reasons"] == [level_left_empty(Tier.SMALL)]
    assert routing.GATE.asked == []
    assert not any(getattr(one, "is_update", False) for one in executed.statements)


def test_a_passed_retirement_retires_the_row_and_derives_the_levels_roles_again(
    matrix: TestClient, executed: routing.Executed
) -> None:
    """The row is retired rather than deleted, and the level's live rungs are written with their
    own role so the trigger derives each again. Delete this and the step after a retired primary
    reads as a failover until somebody saves it."""
    first = executed.rows[0]

    answer = post(matrix, "u_admin", rung_path(first, "retire"))

    assert answer.status_code == 200
    assert (answer.json()["kind"], answer.json()["status"]) == ("retire", "applied")
    assert routing.GATE.asked == [RungRetirement(rung_id=str(first.id))]
    updates = [str(one) for one in executed.statements if getattr(one, "is_update", False)]
    assert any("deleted_at=statement_timestamp()" in one for one in updates)
    assert any("SET role=ops.routing_rung.role" in one for one in updates)
    assert executed.changes[-1].rung_id == first.id


def test_a_move_to_the_step_a_rung_holds_is_a_422_naming_the_step_and_nothing_is_asked(
    matrix: TestClient, executed: routing.Executed
) -> None:
    """Delete this and a move that changes nothing runs the golden questions and records a change
    nobody made."""
    first = executed.rows[0]

    answer = post(matrix, "u_admin", rung_path(first, "move"), {"tier": "main", "step": 1})

    assert answer.status_code == 422
    assert "step" in json.dumps(answer.json())
    assert routing.GATE.asked == []
    assert executed.changes == []


def test_a_passed_move_retires_the_rows_it_rewrites_and_inserts_them_at_their_new_places(
    matrix: TestClient, executed: routing.Executed
) -> None:
    """A move is a retirement and an insertion in one transaction, never an UPDATE of a position.
    Delete this and a move could be written as the UPDATE the unique index refuses halfway."""
    first, second = executed.rows

    answer = post(matrix, "u_admin", rung_path(second, "move"), {"tier": "main", "step": 1})

    assert answer.status_code == 200
    assert (answer.json()["kind"], answer.json()["status"]) == ("move", "applied")
    assert routing.GATE.asked == [RungMove(rung_id=str(second.id), tier=Tier.MAIN, step=1)]
    inserts = [one for one in executed.statements if getattr(one, "is_insert", False)]
    rung_inserts = [one for one in inserts if one.table.fullname == "ops.routing_rung"]
    assert [one.compile().params["position"] for one in rung_inserts] == [2, 3]
    assert [one.compile().params["deployment_id"] for one in rung_inserts] == [
        second.deployment_id,
        first.deployment_id,
    ]
    updates = [str(one) for one in executed.statements if getattr(one, "is_update", False)]
    assert not any("SET position" in one for one in updates)
    assert executed.committed == 1


# --------------------------------------------------------------- the providers, over the stub


def test_the_providers_list_searches_filters_and_pages_and_the_steps_stay_whole(
    client: TestClient, estate: Estate
) -> None:
    """The list contract on the providers alone. Delete this and the console's search box sends a
    `q` the route ignores, which is a control that does nothing."""
    found = call(client, "GET", "u_narrow", f"{PROVIDERS}?q=moon").json()
    off = call(client, "GET", "u_narrow", f"{PROVIDERS}?filter=switched_on:false").json()
    first = call(client, "GET", "u_narrow", f"{PROVIDERS}?limit=1").json()

    assert [one["provider"] for one in found["providers"]] == ["moonshot"]
    assert len(found["rungs"]) == len(estate.rungs)
    assert off["providers"] == []
    assert len(first["providers"]) == 1 and first["next_cursor"]
    whole = call(client, "GET", "u_narrow", PROVIDERS).json()
    assert [one["listed"] for one in whole["providers"]] == list(range(len(whole["providers"])))
    assert "total" not in whole


def test_a_test_is_remembered_as_the_providers_last_and_listed_without_its_reply(
    client: TestClient, estate: Estate
) -> None:
    """Delete this and the list can go on saying "not tested" after a test, or keep the reply."""
    before = call(client, "GET", "u_narrow", PROVIDERS).json()
    checked = call(client, "POST", "u_admin", f"{PROVIDERS}/anthropic/check")
    after = call(client, "GET", "u_narrow", PROVIDERS).json()

    assert checked.status_code == 200
    assert all(one["last_check"] is None for one in before["providers"])
    kept, by = estate.settings[f"{CHECK_NAMESPACE}.anthropic"]
    assert by == "u_admin" and kept == check_value(CheckView(**checked.json()))
    last = {one["provider"]: one["last_check"] for one in after["providers"]}
    assert last["anthropic"]["answered"] is True
    assert last["anthropic"]["model"] == "anthropic-model"
    assert "REPLY-CANARY" not in json.dumps(after)
    assert f"{CHECK_NAMESPACE}.anthropic" not in {one["provider"] for one in after["providers"]}


def test_a_last_test_this_release_cannot_read_is_no_test() -> None:
    """Delete this and a row written by hand as a string, or by a later release in another shape,
    takes the providers read down."""
    state = SettingState(
        key="provider_check.openai", value_type="json", value="yes", updated_by="u", updated_at=AT
    )
    good = SettingState(
        key="provider_check.moonshot",
        value_type="json",
        value={"answered": False, "outcome": "timeout", "model": None},
        updated_by="u",
        updated_at=AT,
    )

    found = checks_from({"openai": state, "moonshot": good})

    assert list(found) == ["moonshot"]
    assert (found["moonshot"].answered, found["moonshot"].outcome, found["moonshot"].at) == (
        False,
        "timeout",
        AT,
    )


def test_a_provider_no_step_names_has_no_calls_recorded_and_the_cost_is_never_nought(
    client: TestClient,
) -> None:
    """A figure nothing records is null and named, never zero. Delete this and the dashboard can
    say a provider nobody routes to had no failures, which is a measurement nobody made."""
    answer = call(client, "GET", "u_narrow", f"{PROVIDERS}/deepseek/stats")
    missing = call(client, "GET", "u_narrow", f"{PROVIDERS}/nobody/stats")
    refused = call(client, "GET", "u_none", f"{PROVIDERS}/deepseek/stats")

    assert answer.status_code == 200
    body = answer.json()
    assert (body["calls"], body["failures"], body["cost_minor"]) == (None, None, None)
    assert {one["figure"]: one["why"] for one in body["unrecorded"]} == {
        "calls": NO_STEP_NO_CALLS,
        "failures": NO_STEP_NO_CALLS,
        "model_cost": COST_IS_NOT_SPLIT_BY_PROVIDER if RUN_SPEND_IS_RECORDED else NO_COST_RECORDED,
    }
    assert missing.status_code == refused.status_code == 404
    unlabelled = [
        {k: v for k, v in one.json().items() if "trace" not in k} for one in (missing, refused)
    ]
    assert unlabelled[0] == unlabelled[1]


def test_a_counted_provider_carries_its_numbers_and_only_the_cost_is_unrecorded() -> None:
    """The positive half. Delete this and `stats_view` could drop a count it was handed."""
    view = stats_view("anthropic", counted=(12, 3), cost_recorded=False)
    recorded = stats_view("anthropic", counted=(12, 3), cost_recorded=True)

    assert (view.calls, view.failures, view.cost_minor) == (12, 3, None)
    assert [(one.figure, one.why) for one in view.unrecorded] == [("model_cost", NO_COST_RECORDED)]
    assert recorded.cost_minor is None
    assert [(one.figure, one.why) for one in recorded.unrecorded] == [
        ("model_cost", COST_IS_NOT_SPLIT_BY_PROVIDER)
    ]


def test_the_failures_are_attempt_outcomes_and_exclude_an_answer_and_an_unsent_call() -> None:
    """Held against the column's own vocabulary. Delete this and a renamed outcome silently stops
    counting as a failure, or `ok` starts to."""
    assert set(ATTEMPT_OUTCOMES) >= FAILED_OUTCOMES | {NOT_SENT_OUTCOME}
    assert {"ok", "refused", NOT_SENT_OUTCOME}.isdisjoint(FAILED_OUTCOMES)
    assert set(ATTEMPT_OUTCOMES) - FAILED_OUTCOMES == {"ok", "refused", NOT_SENT_OUTCOME}


KEYISH = re.compile(r"key|credential|secret|vault|token", re.IGNORECASE)


def _keys(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for name, inner in value.items():
            yield str(name)
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def test_the_routing_export_numbers_each_levels_steps_from_one_and_carries_nothing_about_keys(
    client: TestClient, estate: Estate
) -> None:
    """M27.15.38. Delete this and the export can grow a `key_held` or a vault slot the day
    somebody copies the providers view into it, and a copy handed to a supplier says how the
    install authenticates."""
    answer = call(client, "GET", "u_narrow", f"{API_PREFIX}/routing/export")
    refused = call(client, "GET", "u_none", f"{API_PREFIX}/routing/export")

    assert answer.status_code == 200 and refused.status_code == 404
    body = answer.json()
    assert body["filename"].endswith(".json")
    assert [(one["tier"], one["step"], one["provider"]) for one in body["steps"]] == [
        ("main", 1, "anthropic"),
        ("main", 2, "moonshot"),
        ("heavy", 1, "openai"),
    ]
    assert [name for name in _keys(body) if KEYISH.search(name)] == []


# ------------------------------------------------------------------- the registry on the ledger


def recorder(actor: str = "u_admin") -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id=actor, ent_hash="0" * 32, trace_id="t", clock=lambda: AT
    )


def test_the_registry_trigger_writes_the_recorders_words_on_the_providers_subject() -> None:
    """Delete this and `0140`'s trigger can drift from `AuditRecorder.setting`: a word the enum
    lacks, a subject other than the provider's switch's, or the terms themselves in the ledger."""
    module = migration_module(MIGRATION)
    body = " ".join(module.TRIGGER_FUNCTION.split())
    written = re.findall(r"v_changes := v_changes \|\| '(\w+)'::text;", body)

    assert sorted(written) == sorted(one.value for one in ProviderRegistryChange)
    assert "v_subject text := 'setting:provider.' || NEW.slug;" in body
    excluded = re.search(r"ARRAY\[([^\]]+)\]\s*\)", body)
    assert excluded is not None
    assert excluded.group(1).replace("'", "").split(", ") == list(
        module.REGISTRY_COLUMNS_NOT_RECORDED
    )
    assert "retention_terms)" not in body and "NEW.training_terms" not in body
    entry = recorder().setting(
        key="provider.openai",
        change=ProviderRegistryChange.CHANGED,
        fields=("training_terms", "retention_terms"),
    )
    assert (entry.subject, dict(entry.details)) == (
        "setting:provider.openai",
        {"change": "changed", "fields": "retention_terms,training_terms"},
    )
    with pytest.raises(ValueError):
        recorder().setting(
            key="provider.openai", change=ProviderRegistryChange.RETIRED, fields=("x",)
        )
    with pytest.raises(ValueError):
        recorder().setting(key="provider.openai", change=ProviderRegistryChange.CHANGED)


def as_application(url: str, *statements: str) -> None:
    """Each statement in its own transaction as the application role, so the policies apply,
    attributed as `brain.attribution` attributes a route's write."""
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('brain.actor_id', 'u_admin', false)")
        for statement in statements:
            conn.execute(statement.encode())


def test_a_retiring_rung_keeps_its_role_and_the_downgrade_puts_0097s_function_back() -> None:
    """Delete this and a move's retirements can go back to re-deriving each other's roles, which
    ledgers a role change nobody made, or the downgrade can leave the guarded function behind."""
    module = migration_module(MIGRATION)
    before = migration_module(VERSIONS / "0097_model_registry_and_matrix_gate.py").ROLE_FUNCTION
    guard = "IF NEW.deleted_at IS NOT NULL THEN RETURN NEW; END IF;"

    assert guard in " ".join(module.ROLE_FUNCTION.split())
    assert " ".join(module.ROLE_FUNCTION.split()).replace(guard + " ", "") == " ".join(
        module.ROLE_FUNCTION_BEFORE.split()
    )
    assert " ".join(module.ROLE_FUNCTION_BEFORE.split()) == " ".join(
        before.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION").split()
    )


def _server(database: str) -> Iterator[str]:
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("this server has no pgvector, so the migrations cannot reach 0140")
        yield url


def test_a_registry_row_registered_changed_and_retired_leaves_three_entries_no_terms() -> None:
    """M5.6.4's ledger half, as the application role with the route's attribution. A save that
    changes nothing appends nothing. Delete this and a terms edit is logged and never ledgered,
    which is where it stood before `0140`. **Skips without a server.**"""
    database = "brain_test_registry_audit"
    for url in _server(database):
        change = (
            "UPDATE ops.model_provider SET retention_terms = 'Zero retention of prompts', "
            "updated_by = 'u_admin' WHERE slug = 'openai' AND deleted_at IS NULL"
        )
        as_application(
            url,
            "INSERT INTO ops.model_provider (slug, kind, label, updated_by) "
            "VALUES ('openai', 'builtin', 'OpenAI', 'u_admin')",
            change,
            change,
            "UPDATE ops.model_provider SET deleted_at = statement_timestamp() "
            "WHERE slug = 'openai' AND deleted_at IS NULL",
        )
        found = [one for one in entries(url) if one.subject == "setting:provider.openai"]
        chain = entries(url)

    assert [(one.actor_id, one.action.value, dict(one.details)) for one in found] == [
        (
            "u_admin",
            "setting",
            dict(
                recorder()
                .setting(key="provider.openai", change=ProviderRegistryChange.REGISTERED)
                .details
            ),
        ),
        (
            "u_admin",
            "setting",
            dict(
                recorder()
                .setting(
                    key="provider.openai",
                    change=ProviderRegistryChange.CHANGED,
                    fields=("retention_terms",),
                )
                .details
            ),
        ),
        (
            "u_admin",
            "setting",
            dict(
                recorder()
                .setting(key="provider.openai", change=ProviderRegistryChange.RETIRED)
                .details
            ),
        ),
    ]
    assert "Zero retention" not in json.dumps([dict(one.details) for one in chain])
    assert AuditChain(chain).verify() is None


ROUTING_GRANTS = {
    "u_admin": (
        Grant(capability=MATRIX_READ, scope=EVERYWHERE),
        Grant(capability=MATRIX_WRITE, scope=EVERYWHERE),
    ),
}

INSERT_RUNG = (
    "INSERT INTO ops.routing_rung (id, tier, scope, position, role, deployment_id, provider, "
    "model, attempts, timeout_seconds, max_concurrency) VALUES "
    "(%s, %s, '{\"clauses\": []}', %s, 'primary', %s, %s, 'm', 1, 10, 2)"
)


def test_a_move_and_a_retirement_leave_the_rows_roles_records_and_entries_they_claim() -> None:
    """M27.15.38 against PostgreSQL, pressed over HTTP as the application role.

    The third step of Medium is moved to the top: all three are retired and inserted again in the
    new order at fresh positions, the attempt on the old row keeps it, and the ledger says three
    retired and three added. The new primary is then retired, and the level's next step becomes
    its primary by the trigger. Retiring Simple's only step is held and changes nothing. Delete
    this and a move can pass every stub test and collide with the unique index, or leave the roles
    wrong, on the first install that uses it. **Skips without a server.**"""
    ids = {name: str(uuid.uuid4()) for name in ("a", "b", "c", "s")}
    for url in _server("brain_test_routing_moves"):
        for name, tier, position, provider in (
            ("a", "main", 0, "anthropic"),
            ("b", "main", 1, "anthropic"),
            ("c", "main", 2, "moonshot"),
            ("s", "small", 0, "anthropic"),
        ):
            sql(url, INSERT_RUNG, ids[name], tier, position, f"{provider}-{name}", provider)
        sql(
            url,
            "INSERT INTO ops.model_attempt (trace_id, rung_id, sequence, started_at, finished_at, "
            "outcome) VALUES ('t-1', %s, 0, now(), now(), 'ok')",
            ids["c"],
        )

        async def presses(client: httpx.AsyncClient) -> list[dict[str, Any]]:
            base = f"{API_PREFIX}/routing/rungs"
            moved = await client.post(
                f"{base}/{ids['c']}/move",
                json={"tier": "main", "step": 1},
                headers=headers("u_admin"),
            )
            new_primary = moved.json()["rung_id"]
            retired = await client.post(f"{base}/{new_primary}/retire", headers=headers("u_admin"))
            held = await client.post(f"{base}/{ids['s']}/retire", headers=headers("u_admin"))
            return [moved.json(), retired.json(), held.json()]

        moved, retired, held = pressed(url, ROUTING_GRANTS, presses)
        live = sql(
            url,
            "SELECT deployment_id, role, position FROM ops.routing_rung "
            "WHERE tier = 'main' AND deleted_at IS NULL ORDER BY position",
        )
        [(evidence,)] = sql(
            url,
            "SELECT r.deleted_at IS NOT NULL FROM ops.model_attempt a "
            "JOIN ops.routing_rung r ON r.id = a.rung_id",
        )
        still_small = sql(
            url,
            "SELECT count(*) FROM ops.routing_rung WHERE id = %s AND deleted_at IS NULL",
            ids["s"],
        )
        kinds = sql(url, "SELECT kind, status FROM ops.routing_change ORDER BY decided_at, kind")
        routing_entries = [
            dict(one.details) for one in entries(url) if one.action.value == "routing"
        ]
        chain = entries(url)

    assert (moved["kind"], moved["status"]) == ("move", "applied")
    assert (retired["kind"], retired["status"]) == ("retire", "applied")
    assert (held["status"], held["reasons"]) == ("held", [level_left_empty(Tier.SMALL)])
    assert [(one[0], one[1]) for one in live] == [
        ("anthropic-a", "primary"),
        ("anthropic-b", "same_provider_failover"),
    ]
    assert evidence is True
    assert still_small == [(1,)]
    assert sorted(kinds) == [("move", "applied"), ("retire", "applied"), ("retire", "held")]
    after_seed = routing_entries[4:]
    assert [one["change"] for one in after_seed[:6]] == ["retired"] * 3 + ["added"] * 3
    assert {"change": RoutingChange.RETIRED.value} in after_seed[6:]
    assert AuditChain(chain).verify() is None
