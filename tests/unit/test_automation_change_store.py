"""Pausing, resuming, rescheduling, removing and adopting an automation on a real database, and what
the runner then does on its next tick.

`tests/unit/test_automations.py` holds the decisions over values. This file holds what
`migrations/versions/0145_automation_change.py` builds and what `brain.ops.automation_run_store.
StoredAutomationSchedules.apply` writes through it, as the application role the routes use, and
then drives the worker's own tick: the first half reads the migration as SQL and needs no server,
the second **skips when there is no server**, and CI always has one.

Task ids: M27.12.3, M27.15.37, M39.6.1.5
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

import psycopg
import pytest
from sqlalchemy.schema import CreateTable

from brain.audit.ledger import IDENTIFIER
from brain.console.agent_automations import Automation, resume
from brain.console.automation_gallery import Cadence, Every
from brain.console.automations import Change, ChangeKind, shown
from brain.db import metadata
from brain.ops.automation_owner import AUTOMATION_ID
from brain.ops.automation_run import PausedBecause, next_run_after
from brain.ops.automation_run_store import StoredAutomationSchedules
from brain.session import make_session_factory
from brain.tables import automation_change as table
from brain.tables.identity import one_of
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_automation_run_store import (
    AGENT,
    NOW,
    OWNER,
    QUESTIONS,
    _person,
    ledger_details,
    next_run,
    runs,
    seeded,
    tick,
)
from tests.unit.test_entitlement_store import a_grant, a_principal
from tests.unit.test_tables import DIALECT, VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0145_automation_change.py"
ADOPTER = "u_adopter"
APPROVER = "u_admin"
MONDAYS = Cadence(every=Every.WEEK, hour_utc=7, weekday=0)


# ------------------------------------------------------------------ without a server
def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Rendered DDL against rendered DDL. Delete this and a constraint the model states could be
    missing from the database the console writes to."""
    emitted = squash(rendered("upgrade", MIGRATION))
    expected = squash(
        str(CreateTable(metadata.tables["agent.automation_change"]).compile(dialect=DIALECT))
    )
    assert expected in emitted


def test_the_migrations_copied_grammars_are_the_live_ones() -> None:
    """Delete this and a kind or a cadence the domain writes could be refused by a list copied
    wrongly into the migration."""
    module = migration_module(MIGRATION)
    assert module.AUTOMATION_ID_PATTERN == AUTOMATION_ID
    assert module.IDENTIFIER_PATTERN == IDENTIFIER
    assert squash(module.KIND_IN) == squash(one_of("kind", table.CHANGE_KINDS))
    assert squash(module.EVERY_IN) == squash(one_of("every", table.EVERY))


def test_the_application_may_read_and_insert_changes_in_its_own_name_and_nothing_else() -> None:
    """SELECT and INSERT, an insert policy pinned to the session's principal, and a trigger.

    Delete this and a request could rewrite or delete why an automation stopped, or record a
    change in somebody else's name."""
    module = migration_module(MIGRATION)
    emitted = squash(rendered("upgrade", MIGRATION))
    assert module.GRANTS == ("GRANT SELECT, INSERT ON agent.automation_change TO brain_app",)
    assert "WITH CHECK (changed_by = current_setting('app.principal_id', true))" in emitted
    assert "AFTER INSERT ON agent.automation_change" in emitted
    assert "'reason_code', NEW.kind" in squash(module.CHANGE_TRIGGER_FUNCTION)


# ------------------------------------------------------------------ with a server
@contextmanager
def at_head(database: str) -> Iterator[str]:
    """Every migration applied. `retirable` stops at `0048` without pgvector, which predates the
    table, so this skips there; CI's image has it."""
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the change table needs every migration, and those need pgvector")
        yield url


def the_automation(next_run_at: datetime | None, owner: str = OWNER) -> Automation:
    return Automation(
        automation_id="auto_one",
        agent_id=AGENT,
        name=QUESTIONS.name,
        runs_as=_person(owner),
        task=QUESTIONS.task,
        next_run_at=next_run_at,
    )


def apply(
    url: str,
    change: Change,
    *,
    next_run_at: datetime | None,
    owner: str = OWNER,
    cadence: Cadence = QUESTIONS.cadence,
) -> bool:
    """One change through the store the routes use, as the role they use, confirmed over the
    automation as it is described here."""
    expect = shown(the_automation(next_run_at, owner), cadence=cadence, removed=False)

    async def go() -> bool:
        built = app_engine(url)
        try:
            store = StoredAutomationSchedules(make_session_factory(built))
            return await store.apply(
                "auto_one", change, expect=expect, ent_hash="0" * 32, trace_id="t-1"
            )
        finally:
            await built.dispose()

    return run(go)


def changes(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT kind, changed_by, runs_as_id, next_run_at FROM agent.automation_change"
        " ORDER BY at, id",
    )


def test_a_paused_automation_does_not_run_on_the_next_tick_and_the_ledger_says_who() -> None:
    """Paused by its owner while due: no next run, one change row, a `compose_change` entry
    detaching it in the owner's name, and a tick at the same instant finds nothing to run.

    Delete this and a pause could be written while the runner went on running it."""
    with at_head("brain_automation_change_pause") as url:
        seeded(url)
        due = NOW - timedelta(minutes=1)
        written = apply(
            url, Change(kind=ChangeKind.PAUSED, at=NOW, changed_by=OWNER), next_run_at=due
        )
        done = tick(url)
        found = runs(url)
        scheduled = next_run(url)
        rows = changes(url)
        entry = ledger_details(url)[-1]

    assert written
    assert done.summary() == "no automation was due"
    assert found == []
    assert scheduled is None
    assert rows == [("paused", OWNER, None, None)]
    assert entry == (
        OWNER,
        {
            "part": "automation",
            "reference": "auto_one",
            "direction": "detached",
            "reason_code": "paused",
        },
    )


def test_a_change_confirmed_over_what_has_since_moved_writes_nothing() -> None:
    """Confirmed as paused while it is due: the store folds the row again under its lock and
    refuses. Delete this and a change confirmed an hour ago could land on an automation somebody
    else has changed since."""
    with at_head("brain_automation_change_stale") as url:
        seeded(url)
        written = apply(
            url, Change(kind=ChangeKind.PAUSED, at=NOW, changed_by=OWNER), next_run_at=None
        )
        rows = changes(url)
        scheduled = next_run(url)

    assert not written
    assert rows == []
    assert scheduled == NOW - timedelta(minutes=1)


def test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter() -> None:
    """The owner leaves: the next tick refuses the run and pauses it with the reason. It waits.
    Adopted, it stays paused and names the adopter; resumed by somebody else, the next tick runs it
    at the adopter's reach and records the run in the adopter's name.

    Delete this and a leaver's automation could run as nobody, or an adopted one could go on
    running as the person who left."""
    with at_head("brain_automation_change_adopt") as url:
        seeded(url)
        a_principal(url, ADOPTER)
        a_grant(url, ADOPTER, "read:question")
        sql(url, "UPDATE auth.principal SET disabled_at = %s WHERE id = %s", NOW, OWNER)
        stopped = tick(url)
        waiting = next_run(url)
        adopted = apply(
            url,
            Change(kind=ChangeKind.ADOPTED, at=NOW, changed_by=ADOPTER, runs_as_id=ADOPTER),
            next_run_at=None,
        )
        becomes = next_run_after(QUESTIONS.cadence, NOW)
        resumed = apply(
            url,
            Change(
                kind=ChangeKind.RESUMED,
                at=NOW + timedelta(seconds=1),
                changed_by=APPROVER,
                next_run_at=becomes,
            ),
            next_run_at=None,
            owner=ADOPTER,
        )
        ran = tick(url, becomes)
        found = runs(url)
        rows = changes(url)
        entries = ledger_details(url)[-2:]

    assert (stopped.refused, stopped.paused) == (1, 1)
    assert waiting is None
    assert (adopted, resumed) == (True, True)
    assert [(one[1], one[2], one[3]) for one in found] == [
        (OWNER, "refused", PausedBecause.OWNER_GONE.value),
        (ADOPTER, "succeeded", None),
    ]
    assert ran.succeeded == 1
    assert rows == [("adopted", ADOPTER, ADOPTER, None), ("resumed", APPROVER, None, becomes)]
    assert [(one[0], one[1]["direction"], one[1]["reason_code"]) for one in entries] == [
        (ADOPTER, "detached", "adopted"),
        (APPROVER, "attached", "resumed"),
    ]


def test_a_removed_automation_never_runs_again_and_cannot_be_started_from_its_agent() -> None:
    """Removed, then its next run set again behind the application's back: the runner still skips
    it, and a start from the agent's page writes nothing.

    Delete this and a removal would be one start away from running again."""
    with at_head("brain_automation_change_remove") as url:
        seeded(url)
        due = NOW - timedelta(minutes=1)
        removed = apply(
            url, Change(kind=ChangeKind.REMOVED, at=NOW, changed_by=OWNER), next_run_at=due
        )
        sql(url, "UPDATE agent.automation SET next_run_at = %s", due)
        done = tick(url)

        async def start() -> bool:
            built = app_engine(url)
            try:
                store = StoredAutomationSchedules(make_session_factory(built))
                change = resume(the_automation(due), next_run_at=NOW, guards=QUESTIONS.guards)
                return await store.change(
                    change,
                    reason="started",
                    actor=APPROVER,
                    ent_hash="0" * 32,
                    trace_id="t-2",
                    at=NOW,
                )
            finally:
                await built.dispose()

        started = run(start)
        entry = ledger_details(url)[-1]

    assert removed
    assert (entry[0], entry[1]["direction"], entry[1]["reason_code"]) == (
        OWNER,
        "detached",
        "removed",
    )
    assert done.summary() == "no automation was due"
    assert not started


def test_a_schedule_change_moves_the_next_run_and_the_runner_keeps_to_the_new_cadence() -> None:
    """Rescheduled to Mondays while running: the next run is the new cadence's next instant, and the
    run at it schedules the Monday after.

    Delete this and a schedule change would be recorded and ignored by the only thing that reads
    it."""
    with at_head("brain_automation_change_reschedule") as url:
        seeded(url)
        due = NOW - timedelta(minutes=1)
        monday = next_run_after(MONDAYS, NOW)
        written = apply(
            url,
            Change(
                kind=ChangeKind.RESCHEDULED,
                at=NOW,
                changed_by=APPROVER,
                cadence=MONDAYS,
                next_run_at=monday,
            ),
            next_run_at=due,
        )
        moved = next_run(url)
        entry = ledger_details(url)[-1]
        tick(url, monday)
        following = next_run(url)

    assert written
    assert (entry[0], entry[1]["direction"], entry[1]["reason_code"]) == (
        APPROVER,
        "attached",
        "rescheduled",
    )
    assert moved == monday
    assert following == next_run_after(MONDAYS, monday)


def test_the_application_cannot_record_a_change_for_somebody_else() -> None:
    """Measured as the role: a change in another person's name is refused by the policy, and an
    adoption naming somebody other than the adopter by the table. The positive case is every test
    above.

    Delete this and an automation could be handed to somebody who never agreed to lend it their
    reach."""
    with at_head("brain_automation_change_policies") as url:
        seeded(url)
        insert = (
            "INSERT INTO agent.automation_change (automation_id, agent_id, kind, runs_as_id,"
            " changed_by, at) VALUES ('auto_one', %s, %s, %s, %s, now())"
        )
        with (
            as_app(url, ("app.principal_id", APPROVER)) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(insert, (AGENT, "paused", None, "u_other"))
        with (
            as_app(url, ("app.principal_id", APPROVER)) as conn,
            pytest.raises(psycopg.errors.CheckViolation),
        ):
            conn.execute(insert, (AGENT, "adopted", "u_other", APPROVER))
        with (
            as_app(url, ("app.principal_id", APPROVER)) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute("DELETE FROM agent.automation_change")
