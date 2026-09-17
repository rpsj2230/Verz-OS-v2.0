"""An installed automation runs on a real database: claimed, run as its owner, recorded, paused.

`tests/unit/test_automation_run.py` holds the decisions over values. This file holds what
`migrations/versions/0067_automation_run.py` builds and what `brain.ops.automation_run_store` writes
through it: the first half reads the migration as the SQL it renders and needs no server; the second
builds a database through the migrations that ship and drives the worker's own tick and the
console's own store. **It skips when there is no server**, and CI always has one.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from sqlalchemy.schema import CreateTable

from brain.audit.ledger import IDENTIFIER
from brain.console.agent_automations import Automation, pause, resume
from brain.console.automation_gallery import BUILT_IN
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.db import metadata
from brain.ops import automation_run_store as store
from brain.ops.automation_owner import AUTOMATION_ID
from brain.ops.automation_run import (
    RUNNER_ACTOR,
    PausedBecause,
    RunOutcome,
    next_run_after,
    run_id,
)
from brain.ops.automation_run_store import (
    StoredAutomationSchedules,
    run_automations,
)
from brain.ops.controls import CONTROLS
from brain.session import make_session_factory
from brain.tables import automation_run as table
from brain.tables.identity import one_of
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import add_modelled, engine, migrate, run, sql
from tests.unit.test_agent_automation_store import compiled
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_entitlement_store import a_grant, a_principal, revoke
from tests.unit.test_tables import VERSIONS, as_amended, migration_module, rendered, squash

MIGRATION = VERSIONS / "0067_automation_run.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)

OWNER = "u_owner"
AGENT = "quote_helper"
QUESTIONS = next(one for one in BUILT_IN if one.task == "automation.unanswered_questions")


# ------------------------------------------------------------------ without a server
def test_the_migration_builds_both_tables_exactly_as_the_models_declare_them() -> None:
    """Rendered DDL against rendered DDL. Delete this and a width, a default or a check could differ
    between what the worker writes against and what the database refuses."""
    emitted = as_amended(rendered("upgrade", MIGRATION))
    for qualified in migration_module(MIGRATION).TABLES:
        expected = squash(str(CreateTable(metadata.tables[qualified]).compile(dialect=_dialect())))
        assert expected in emitted, qualified


def _dialect() -> Any:
    from tests.unit.test_tables import DIALECT

    return DIALECT


def test_the_migration_widens_the_control_names_to_exactly_the_registry() -> None:
    """Delete this and the first run the schedule records under `automation_run` is refused by the
    database, or a name the registry dropped stays admitted."""
    module = migration_module(MIGRATION)
    assert squash(module.WITH_AUTOMATION_RUN) == squash(
        one_of("name", tuple(one.name for one in CONTROLS))
    )
    assert module.SUPERSEDES == {module.WITHOUT_AUTOMATION_RUN: module.WITH_AUTOMATION_RUN}
    assert squash(module.WITHOUT_AUTOMATION_RUN) == squash(
        migration_module(VERSIONS / "0066_vault_token_renewal.py").WIDENED_NAMES
    )


def test_the_migration_grants_the_application_a_read_of_runs_and_a_move_of_the_next_run_only() -> (
    None
):
    """No write of a run, no update or delete of a schedule row, and on the automation an update of
    two columns under a policy refusing a session with no principal.

    Delete this and a request the console serves could record a run, rewrite why an automation
    stopped, or edit an automation's name or principal."""
    emitted = squash(rendered("upgrade", MIGRATION))
    assert "GRANT SELECT ON agent.automation_run TO brain_app" in emitted
    assert "GRANT SELECT, INSERT ON agent.automation_schedule TO brain_app" in emitted
    assert "GRANT UPDATE (next_run_at, updated_at) ON agent.automation TO brain_app" in emitted
    assert "DELETE" not in " ".join(migration_module(MIGRATION).GRANTS)
    assert "WITH CHECK (COALESCE(current_setting('app.principal_id', true), '') <> '')" in emitted
    assert "WITH CHECK (changed_by = current_setting('app.principal_id', true))" in emitted
    assert "DROP POLICY automation_readable_by_its_principal ON agent.automation" in emitted


def test_the_migrations_copied_grammars_are_the_live_ones() -> None:
    """Delete this and a run id or an automation id the worker writes could be refused by a pattern
    copied wrongly into the migration."""
    module = migration_module(MIGRATION)
    assert module.AUTOMATION_ID_PATTERN == AUTOMATION_ID
    assert module.IDENTIFIER_PATTERN == IDENTIFIER
    assert module.RUN_ID_PATTERN == table.RUN_ID_PATTERN
    assert module.ENT_HASH_PATTERN == table.ENT_HASH_PATTERN
    assert squash(module.OUTCOME_IN) == squash(one_of("outcome", table.RUN_OUTCOMES))
    assert squash(module.REASON_IN) == squash(one_of("reason", table.PAUSE_REASONS))
    assert squash(module.SCHEDULE_REASON_IN) == squash(one_of("reason", table.SCHEDULE_REASONS))
    assert "'part', 'automation'" in module.SCHEDULE_TRIGGER_FUNCTION


def test_the_console_moves_a_next_run_only_where_it_is_still_the_one_shown() -> None:
    """`IS NOT DISTINCT FROM`, so a start from no next run matches and a stale one does not.

    Delete this and a start written with `=` would never match a paused automation, or a change
    with no condition would overwrite a run that arrived first."""
    one = Automation(
        automation_id="auto_one",
        agent_id=AGENT,
        name=QUESTIONS.name,
        runs_as=_person(OWNER),
        task=QUESTIONS.task,
    )
    change = resume(one, next_run_at=NOW, guards=QUESTIONS.guards)
    said = compiled(store.moving(change))
    assert "agent.automation.next_run_at IS NOT DISTINCT FROM" in said
    assert "agent.automation.automation_id = " in said
    assert "RETURNING agent.automation.automation_id" in said


# ------------------------------------------------------------------ with a server
def _person(pid: str) -> Principal:
    return Principal(
        id=pid, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=f"Person {pid}"
    )


@contextmanager
def through_0067(database: str) -> Iterator[str]:
    """A database with `0067` applied and the tables a run reads.

    Without pgvector `retirable` stops at `0048`, which built the principals, the grants, the
    resolver and the ledger. `0049` and `0055` are run for real, as
    `tests/unit/test_agent_automation_store.py` runs them; the agent table, the control runs and the
    outbox are built from the models, because what the run reads of them is its columns and no
    policy; then `0064`, `0066` and `0067` run for real."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0055")
            add_modelled(
                url,
                (
                    "agent.agent",
                    "ops.control_run",
                    "ops.webhook_subscriber",
                    "ops.outbox_event",
                    "ops.outbox_delivery",
                ),
            )
            migrate(database, "stamp", "0063")
            migrate(database, "upgrade", "0067")
        yield url


def seeded(url: str, *, capabilities: tuple[str, ...] = ("read:question",)) -> None:
    """An owner holding `capabilities`, an agent admitting the question read, an automation of
    theirs due at `NOW`, and two unanswered questions in the week before it."""
    a_principal(url, OWNER)
    for one in capabilities:
        a_grant(url, OWNER, one)
    sql(
        url,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by) VALUES (%s, 'Quote helper', 'Answers briefly.', 'main', 'company',"
        " 'u_steward', NULL, '{\"clauses\": []}', %s, '{}', '{}', 'none', 'u_builder')",
        AGENT,
        ["read:question"],
    )
    sql(
        url,
        "INSERT INTO agent.automation (automation_id, agent_id, name, runs_as_id, task,"
        " next_run_at, guards, template_id, template_version, installed_by)"
        " VALUES ('auto_one', %s, %s, %s, %s, %s, %s, %s, 1, %s)",
        AGENT,
        QUESTIONS.name,
        OWNER,
        QUESTIONS.task,
        NOW - timedelta(minutes=1),
        QUESTIONS.guards,
        QUESTIONS.template_id,
        OWNER,
    )
    for trace, department in (("trace-a", "web"), ("trace-b", "web")):
        sql(
            url,
            "INSERT INTO ops.question_gap (trace_id, department, source, at) VALUES (%s, %s,"
            " 'crm', %s)",
            trace,
            department,
            NOW - timedelta(days=2),
        )


def tick(url: str, at: datetime = NOW) -> store.AutomationTick:
    async def go() -> store.AutomationTick:
        built = engine(url)
        try:
            return await run_automations(make_session_factory(built), now=at)
        finally:
            await built.dispose()

    return run(go)


def runs(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT run_id, principal_id, outcome, reason, result, ent_hash FROM agent.automation_run"
        " ORDER BY finished_at, run_id",
    )


def next_run(url: str) -> datetime | None:
    [(at,)] = sql(url, "SELECT next_run_at FROM agent.automation WHERE automation_id = 'auto_one'")
    return at  # type: ignore[no-any-return]


def schedule_rows(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT reason, changed_by, next_run_at FROM agent.automation_schedule ORDER BY at, id",
    )


def ledger_details(url: str) -> list[tuple[str, dict[str, Any]]]:
    rows = sql(url, "SELECT actor_id, details FROM obs.audit_entry ORDER BY seq")
    return [
        (actor, details if isinstance(details, dict) else json.loads(details))
        for actor, details in rows
    ]


def test_a_due_automation_runs_as_its_owner_and_writes_its_run_its_event_and_its_next_slot() -> (
    None
):
    """The positive case every refusal below is measured against. One run, as the owner, at a
    reach whose digest is kept, with the lines the owner may read; one outbox event naming it; and
    the next run at the cadence's next instant after the run. A second tick at the same instant
    finds nothing due.

    Delete this and every refusal test passes against a runner that runs nothing."""
    with through_0067("brain_automation_run_ok") as url:
        seeded(url)
        first = tick(url)
        second = tick(url)
        [(ran_id, principal, outcome, reason, result, ent_hash)] = runs(url)
        events = sql(url, "SELECT event_id, kind, record_id FROM ops.outbox_event")
        scheduled = next_run(url)

    assert (first.succeeded, first.failed, first.refused, first.paused) == (1, 0, 0, 0)
    assert second.summary() == "no automation was due"
    assert ran_id == run_id("auto_one", NOW - timedelta(minutes=1))
    assert (principal, outcome, reason) == (OWNER, "succeeded", None)
    assert result == ["2 asked in web that a source you are not told of would have answered"]
    assert re.fullmatch(table.ENT_HASH_PATTERN, ent_hash)
    assert events == [(ran_id, "automation.run_finished", ran_id)]
    assert scheduled == next_run_after(QUESTIONS.cadence, NOW)


def test_an_owner_who_lost_the_grant_runs_nothing_and_it_pauses_with_a_ledger_entry() -> None:
    """The grant deleted before the tick: a refused run with no result and no reach, no next run,
    a schedule row saying why by the runner, and a `compose_change` entry detaching the automation
    with that reason.

    Delete this and a revoked owner's automation would go on running at their old reach, or stop
    with nothing anywhere saying why."""
    with through_0067("brain_automation_run_revoked") as url:
        seeded(url)
        revoke(url, OWNER, "read:question")
        done = tick(url)
        [(_, _, outcome, reason, result, ent_hash)] = runs(url)
        scheduled = next_run(url)
        rows = schedule_rows(url)
        entries = ledger_details(url)

    assert (done.refused, done.paused) == (1, 1)
    assert (outcome, reason, result, ent_hash) == (
        "refused",
        PausedBecause.OWNER_LOST_REACH.value,
        [],
        None,
    )
    assert scheduled is None
    assert rows == [(PausedBecause.OWNER_LOST_REACH.value, RUNNER_ACTOR, None)]
    assert entries[-1] == (
        RUNNER_ACTOR,
        {
            "part": "automation",
            "reference": "auto_one",
            "direction": "detached",
            "reason_code": PausedBecause.OWNER_LOST_REACH.value,
        },
    )


def test_an_owner_who_has_gone_runs_nothing_whatever_their_grants_say() -> None:
    """The owner disabled with the grant still on file. Delete this and a leaver's automation would
    run for as long as nobody deleted their grants."""
    with through_0067("brain_automation_run_gone") as url:
        seeded(url)
        sql(
            url,
            "UPDATE auth.principal SET disabled_at = %s WHERE id = %s",
            NOW - timedelta(days=1),
            OWNER,
        )
        tick(url)
        [(_, _, outcome, reason, _, _)] = runs(url)

    assert (outcome, reason) == ("refused", PausedBecause.OWNER_GONE.value)


def test_a_task_that_raises_is_scheduled_again_once_and_paused_at_the_second_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first failure keeps the automation on its cadence; the run at that next slot fails too
    and pauses it, and nothing of either exception is kept.

    Delete this and a broken task would fail on every slot for ever, or pause on its first blip."""

    async def broken(*_: object, **__: object) -> tuple[str, ...]:
        msg = "the read quoted somebody's data"
        raise RuntimeError(msg)

    monkeypatch.setattr(store, "perform", broken)
    with through_0067("brain_automation_run_failing") as url:
        seeded(url)
        first = tick(url)
        again = next_run(url)
        assert again is not None
        second = tick(url, again)
        outcomes = runs(url)
        scheduled = next_run(url)
        rows = schedule_rows(url)

    assert (first.failed, first.paused) == (1, 0)
    assert (second.failed, second.paused) == (1, 1)
    assert [(one[2], one[4]) for one in outcomes] == [("failed", []), ("failed", [])]
    assert scheduled is None
    assert rows == [(PausedBecause.FAILED_REPEATEDLY.value, RUNNER_ACTOR, None)]
    assert "somebody's data" not in repr(outcomes)


def test_a_start_after_a_failure_pause_counts_failures_afresh() -> None:
    """A person starts the automation again after it paused; its next failure does not pause it at
    once, because the failures before the start are not the same run of trouble.

    Delete this and a restarted automation would pause on its first blip after every restart."""
    with through_0067("brain_automation_run_restart") as url:
        seeded(url)
        for at in (NOW - timedelta(hours=2), NOW - timedelta(hours=1)):
            sql(
                url,
                "INSERT INTO agent.automation_run (run_id, automation_id, agent_id, principal_id,"
                " due_at, started_at, finished_at, outcome) VALUES (%s, 'auto_one', %s, %s, %s, %s,"
                " %s, 'failed')",
                run_id("auto_one", at),
                AGENT,
                OWNER,
                at,
                at,
                at,
            )
        sql(
            url,
            "INSERT INTO agent.automation_schedule (automation_id, agent_id, next_run_at, reason,"
            " changed_by, at) VALUES ('auto_one', %s, %s, 'started', 'u_admin', %s)",
            AGENT,
            NOW - timedelta(minutes=1),
            NOW - timedelta(minutes=30),
        )

        async def failing(*_: object, **__: object) -> tuple[str, ...]:
            raise RuntimeError

        original = store.perform
        store.perform = failing
        try:
            done = tick(url)
        finally:
            store.perform = original

    assert (done.failed, done.paused) == (1, 0)


def test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who() -> None:
    """A start by an approver and a stop by the owner, through the store the routes use and as the
    role they use: each moves the next run, writes a schedule row in its actor's name and appends a
    `compose_change` entry by that actor. A second start from the same stale state writes nothing.

    Delete this and a start could reach the database unattributed, or twice."""
    with through_0067("brain_automation_run_console") as url:
        seeded(url)
        sql(url, "UPDATE agent.automation SET next_run_at = NULL")
        one = Automation(
            automation_id="auto_one",
            agent_id=AGENT,
            name=QUESTIONS.name,
            runs_as=_person(OWNER),
            task=QUESTIONS.task,
        )
        becomes = next_run_after(QUESTIONS.cadence, NOW)
        started = resume(one, next_run_at=becomes, guards=QUESTIONS.guards)

        async def go() -> tuple[bool, bool, bool, tuple[store.Listed, ...]]:
            built = app_engine(url)
            try:
                schedules = StoredAutomationSchedules(make_session_factory(built))
                first = await schedules.change(
                    started,
                    reason="started",
                    actor="u_admin",
                    ent_hash="0" * 32,
                    trace_id="t-1",
                    at=NOW,
                )
                twice = await schedules.change(
                    started,
                    reason="started",
                    actor="u_admin",
                    ent_hash="0" * 32,
                    trace_id="t-2",
                    at=NOW,
                )
                assert started.after is not None
                stopped = await schedules.change(
                    pause(started.after, guards=QUESTIONS.guards),
                    reason="stopped",
                    actor=OWNER,
                    ent_hash="0" * 32,
                    trace_id="t-3",
                    at=NOW + timedelta(seconds=1),
                )
                return first, twice, stopped, await schedules.listed(AGENT)
            finally:
                await built.dispose()

        first, twice, stopped, listed = run(go)
        rows = schedule_rows(url)
        entries = ledger_details(url)[-2:]

    assert (first, twice, stopped) == (True, False, True)
    assert [(one[0], one[1]) for one in rows] == [("started", "u_admin"), ("stopped", OWNER)]
    assert [
        (actor, details["direction"], details["reason_code"]) for actor, details in entries
    ] == [
        ("u_admin", "attached", "started"),
        (OWNER, "detached", "stopped"),
    ]
    [shown] = listed
    assert shown.automation.paused and shown.stopped_because == "stopped"


def test_the_application_role_cannot_record_a_run_or_move_a_next_run_unattributed() -> None:
    """Measured as the role. No insert of a run; an update of the next run refused with no
    principal set and admitted with one; no update of any other column; no schedule row in somebody
    else's name. The positive case is the console test above.

    Delete this and a request the console serves could write what the worker alone may write."""
    with through_0067("brain_automation_run_policies") as url:
        seeded(url)
        with as_app(url) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO agent.automation_run (run_id, automation_id, agent_id, principal_id,"
                " due_at, started_at, finished_at, outcome) VALUES (%s, 'auto_one', 'a', 'b',"
                " now(), now(), now(), 'succeeded')",
                (run_id("auto_one", NOW),),
            )
        with as_app(url) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE agent.automation SET next_run_at = NULL")
        with as_app(url, ("app.principal_id", "u_admin")) as conn:
            moved = conn.execute("UPDATE agent.automation SET next_run_at = NULL").rowcount
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE agent.automation SET runs_as_id = 'u_admin'")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO agent.automation_schedule (automation_id, agent_id, reason,"
                    " changed_by, at) VALUES ('auto_one', 'quote_helper', 'stopped', 'u_other',"
                    " now())"
                )

    assert moved == 1


def test_the_runner_writes_under_the_owner_connection_it_is_started_on() -> None:
    """The runner's tick through `run_automations_now`'s own engine, at the instant handed in.

    Delete this and the worker's entry point could build its engine from somewhere other than the
    URL the schedule hands it."""
    with through_0067("brain_automation_run_entry") as url:
        seeded(url)
        from brain.db import normalise_database_url
        from brain.ops.worker import _loop_factory

        said = store.run_automations_now(
            normalise_database_url(url), now=NOW, loop_factory=_loop_factory()
        )
        [(_, _, outcome, _, _, _)] = runs(url)

    assert said == "1 ran, 0 failed, 0 refused; 0 paused"
    assert outcome == RunOutcome.SUCCEEDED.value
