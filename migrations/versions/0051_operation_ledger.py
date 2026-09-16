"""Every side-effecting operation gets a row, unique on its key, with row-level security on.

`brain.tables.operation` holds the argument for the shape and `brain.ops.idempotency` the
argument for the record. What is here is the table, a trigger holding its state to the machine's
transitions, its policies and its grants.

**The trigger is the transition table, in the database.** `brain.ops.idempotency.advance` refuses
a move the machine has no edge for, and a person with a database session is not calling
`advance`. An `UPDATE` moving `UNKNOWN` back to `PENDING` would be the second issue
`NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE` exists to forbid, arriving through the one route the
Python never sees. So the trigger raises for any pair not in `TRANSITIONS`, and for any change to
the key or the intent a record describes. `TRANSITIONS` is copied from the Python table rather
than imported, for the reason `0009` gives, and `tests/unit/test_operation_store.py` holds the
two equal.

**Inserted pending, updated while unsettled, never deleted.** The insert policy admits only a
pending record, the update policy only a record not yet settled, and UPDATE is granted on the
state and its timestamp alone. There is no DELETE grant and no DELETE policy: a record removed is
a key the next attempt does not find, and an effect issued again.

**Read with `USING (true)`.** Which records a screen may show is a reader's question and no screen
reads this table; a recovering worker has to see every record, because a record it cannot see is
an operation it will issue.

The downgrade drops the table, the trigger and its function, and discards every record.

Task ids: M17.3.1

Revision ID: 0051
Revises: 0050
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.operation",)

APP_ROLE = "brain_app"

#: `brain.ops.idempotency.ALLOWED_TRANSITIONS`, as pairs. Copied, and held equal by a test.
TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("pending", "failed"),
    ("pending", "sent"),
    ("sent", "failed"),
    ("sent", "succeeded"),
    ("sent", "unknown"),
    ("unknown", "verifying"),
    ("verifying", "failed"),
    ("verifying", "succeeded"),
    ("verifying", "unknown"),
)

#: `brain.ops.idempotency.TERMINAL`, copied for the update policy.
SETTLED: tuple[str, ...] = ("failed", "succeeded")

_PAIRS = ", ".join(f"('{frm}', '{to}')" for frm, to in TRANSITIONS)
_SETTLED = ", ".join(f"'{state}'" for state in SETTLED)

TRIGGER: tuple[str, ...] = (
    f"""
    CREATE FUNCTION ops.operation_moves_by_the_machine() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.key <> OLD.key OR NEW.connector <> OLD.connector OR NEW.tool <> OLD.tool
           OR NEW.principal_id <> OLD.principal_id OR NEW.intent_ref <> OLD.intent_ref THEN
            RAISE EXCEPTION 'an operation record describes one intent and cannot be repointed'
                USING HINT = 'raise a new intent with its own reference';
        END IF;
        IF NEW.state <> OLD.state AND (OLD.state, NEW.state) NOT IN ({_PAIRS}) THEN
            RAISE EXCEPTION 'an operation cannot move from % to %', OLD.state, NEW.state
                USING HINT = 'unknown is left only by verifying';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER operation_moves_by_the_machine
        BEFORE UPDATE ON ops.operation
        FOR EACH ROW EXECUTE FUNCTION ops.operation_moves_by_the_machine()
    """,
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.operation ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY operation_readable ON ops.operation
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY operation_recorded_pending ON ops.operation
        FOR INSERT TO brain_app
        WITH CHECK (state = 'pending')
    """,
    f"""
    CREATE POLICY operation_moved_while_unsettled ON ops.operation
        FOR UPDATE TO brain_app
        USING (state NOT IN ({_SETTLED}))
        WITH CHECK (true)
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.operation TO brain_app",
    "GRANT UPDATE (state, updated_at) ON ops.operation TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "operation",
        sa.Column("key", sa.String(64), primary_key=True, nullable=False),
        sa.Column("connector", sa.String(80), nullable=False),
        sa.Column("tool", sa.String(160), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("intent_ref", sa.String(256), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("key ~ '^[0-9a-f]{64}$'", name="key_is_a_derived_key"),
        sa.CheckConstraint(
            "state IN ('failed', 'pending', 'sent', 'succeeded', 'unknown', 'verifying')",
            name="state",
        ),
        sa.CheckConstraint("length(btrim(connector)) >= 1", name="connector_present"),
        sa.CheckConstraint("length(btrim(tool)) >= 1", name="tool_present"),
        sa.CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        sa.CheckConstraint("length(btrim(intent_ref)) >= 1", name="intent_present"),
        schema="ops",
    )
    op.create_index("ix_operation_state", "operation", ["state"], schema="ops")
    for statement in TRIGGER:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The index, the trigger, the policies and the grants go with the table; the function does not.
    op.drop_table("operation", schema="ops")
    op.execute("DROP FUNCTION ops.operation_moves_by_the_machine()")
