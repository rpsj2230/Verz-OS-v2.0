"""`0097`: the provider registry, the gate's tables, the pin, the refused outcome, the role trigger.

Most of what is here is a property of the DDL the migration emits, rendered offline. The role
trigger is also run on a scratch PostgreSQL, because what a trigger derives is a behaviour of a
server: CI has one and a development machine skips it.

Task ids: M5.3.2, M5.6.2, M5.6.4, M5.7.2, M5.7.3, M5.4.1
"""

from __future__ import annotations

import io
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations

from brain.db import metadata
from brain.models.evidence import OUTCOMES
from brain.ops.migration_policy import check_file
from brain.tables.routing import ATTEMPT_OUTCOMES
from tests.fixtures.amended_tables import ADDED_LATER
from tests.fixtures.scratch_postgres import modelled, sql
from tests.unit.test_tables import migration_module, squash

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/0097_model_registry_and_matrix_gate.py"
)


def module() -> ModuleType:
    return migration_module(MIGRATION)


def rendered(direction: str) -> str:
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer, "target_metadata": metadata},
    )
    with Operations.context(context):
        getattr(module(), direction)()
    return squash(buffer.getvalue())


def test_the_migration_satisfies_the_migration_policy() -> None:
    """No rename written as a drop, no not-null column without a default, no data. Delete this and
    the added columns can arrive not null with no default and fail on a populated install."""
    assert check_file(MIGRATION) == []


def test_every_new_table_has_row_level_security_and_no_delete_grant() -> None:
    """Every new table enables row-level security in the migration that creates it, and none is
    granted DELETE. Delete this and a table ships readable by any role, or deletable by the app."""
    upgrade = rendered("upgrade")
    for table in module().TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in upgrade
        assert f"GRANT SELECT, INSERT, UPDATE ON {table} TO brain_app" in upgrade
    assert "DELETE ON" not in upgrade


def test_the_role_trigger_is_created_and_the_downgrade_removes_it() -> None:
    """M5.3.2: the role is derived by a trigger rather than typed. Delete this and the trigger can
    be defined in a constant that `upgrade` never runs."""
    upgrade = rendered("upgrade")
    downgrade = rendered("downgrade")

    assert "CREATE FUNCTION ops.routing_rung_role()" in upgrade
    assert squash(module().ROLE_TRIGGER) in upgrade
    assert "DROP TRIGGER routing_rung_role_is_derived ON ops.routing_rung" in downgrade
    assert "DROP FUNCTION ops.routing_rung_role()" in downgrade


def test_refused_joins_the_outcomes_the_attempt_table_and_the_health_layer_both_know() -> None:
    """M5.4.1: the column, the migration and `brain.models.evidence` agree on `refused`, and the
    downgrade narrows it NOT VALID so an attempt already recorded refused stays.

    Delete this and a refused attempt is written by the executor and refused by the database."""
    assert "refused" in ATTEMPT_OUTCOMES
    assert set(ATTEMPT_OUTCOMES) == set(OUTCOMES)
    assert squash(module().WITH_REFUSED) in rendered("upgrade")
    assert "NOT VALID" in rendered("downgrade")


def test_the_columns_added_to_existing_tables_are_exactly_the_ones_the_fixture_excuses() -> None:
    """`tests.fixtures.amended_tables.ADDED_LATER` lets the creating migrations' comparisons ignore
    these columns; this holds it to what `0097` adds and nothing else.

    Delete this and the fixture can excuse a column no migration adds."""
    upgrade = rendered("upgrade")
    assert "ALTER TABLE ops.model_attempt ADD COLUMN data_categories JSONB" in upgrade
    assert "ALTER TABLE agent.agent ADD COLUMN model_pin_provider VARCHAR(60)" in upgrade
    assert "ALTER TABLE agent.agent ADD COLUMN model_pin_model VARCHAR(120)" in upgrade
    assert dict(ADDED_LATER) == {
        "ops.model_attempt": ("data_categories",),
        "agent.agent": ("model_pin_provider", "model_pin_model"),
    }


def test_the_role_trigger_derives_the_role_whatever_the_writer_typed() -> None:
    """M5.3.2 on a real server: a rung written with the wrong role gets the derived one.

    The second rung of a tier is typed `primary`; the trigger makes it a same-provider failover,
    and a third from another provider a cross-provider one. Delete this and the trigger can exist
    and derive nothing."""
    with modelled("brain_rung_role_trigger", ("ops.routing_rung",)) as url:
        sql(url, module().ROLE_FUNCTION)
        sql(url, module().ROLE_TRIGGER)
        insert = (
            "INSERT INTO ops.routing_rung (tier, scope, position, role, deployment_id, provider, "
            "model, attempts, timeout_seconds, max_concurrency) VALUES "
            "('main', '{\"clauses\": []}', %s, 'primary', %s, %s, 'm', 1, 10, 2)"
        )
        sql(url, insert, 0, "a-0", "anthropic")
        sql(url, insert, 1, "a-1", "anthropic")
        sql(url, insert, 2, "m-2", "moonshot")

        roles = sql(url, "SELECT position, role FROM ops.routing_rung ORDER BY position")

    assert roles == [
        (0, "primary"),
        (1, "same_provider_failover"),
        (2, "cross_provider_failover"),
    ]
