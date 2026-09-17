"""The webhook outbox: subscribers, events and deliveries, with row-level security on all three.

`brain.ops.outbox` decides what an event may carry, how a request is signed and what one
attempt's outcome does to a delivery. It has said since it was written that the table was not
in this repository. This is the table, and `brain.ops.outbox_store` is the worker that drains
it. `brain.tables.outbox` holds the argument for the shape; what is here is the DDL and the
three policies that make the shape hold for the application role.

**Three policy shapes, one per table, and each is the table's rule in the database.**

- `ops.outbox_event` takes SELECT and INSERT and nothing else. An event is the key a
  subscriber deduplicates on, so it is written once. PostgreSQL denies what no policy admits,
  so the absent UPDATE and DELETE policies are the refusal.
- `ops.outbox_delivery` takes an INSERT only in its first state, and an UPDATE only on a row
  that is still pending. A delivered or exhausted row is history, and the policy reads the
  row before the change, so the application cannot move one back.
- `ops.webhook_subscriber` takes an UPDATE only on a row that is still active, which is what
  makes deactivation one way. There is no DELETE policy and no DELETE grant: a delivery names
  its subscriber by foreign key, and the record of what was sent where outlives the
  subscription.

**`USING (true)` on the reads is not an absence of a permission check**, for the reason `0025`
gives about `ops.control_run`. Who may see a subscriber is a console question decided against
the reader's live entitlements by `brain.console.subscribers`, and none of these rows carries a
field a predicate here could read.

**The claim index is partial.** `ix_outbox_delivery_due` covers pending rows only, because the
worker's claim never asks about a settled one and the history of settled rows only grows.

**The downgrade is real and drops all three**, in the reverse of the order they were built,
because the delivery table points at both of the others. Nothing outside this migration refers
to any of them. Downgrading discards every undelivered event, which is the state before this
migration existed, and it is said here because a downgrade on a live install is the moment
somebody would want to know.

**It also widens `ops.control_run`'s name constraint, and that belongs here.** The worker
that drains the outbox is registered in `brain.ops.controls` as `outbox_dispatch`, a
control nothing calls yet, and the constraint on `ops.control_run.name` is generated from
that registry. Without the widening the model and the migration chain disagree, and the
first recorded run of the dispatcher would be refused by the database. The downgrade
narrows it again `NOT VALID`, for the reason `0026` gives: a run record is history, so a run of
`outbox_dispatch` already recorded stays and no new one is accepted.

Task ids: M17.5.1, M17.5.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

#: The tables this migration creates, in the order it creates them. Read by
#: `tests/unit/test_tables.py` so the package tuple is the migrations end to end.
TABLES: tuple[str, ...] = ("ops.webhook_subscriber", "ops.outbox_event", "ops.outbox_delivery")

APP_ROLE = "brain_app"

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON ops.webhook_subscriber TO brain_app",
    "GRANT SELECT, INSERT ON ops.outbox_event TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON ops.outbox_delivery TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.webhook_subscriber ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY webhook_subscriber_readable ON ops.webhook_subscriber
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY webhook_subscriber_registrable ON ops.webhook_subscriber
        FOR INSERT TO brain_app
        WITH CHECK (deactivated_at IS NULL)
    """,
    # The only change a subscriber takes is being switched off, and only once.
    """
    CREATE POLICY webhook_subscriber_deactivatable ON ops.webhook_subscriber
        FOR UPDATE TO brain_app
        USING (deactivated_at IS NULL)
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.outbox_event ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY outbox_event_readable ON ops.outbox_event
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY outbox_event_appendable ON ops.outbox_event
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.outbox_delivery ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY outbox_delivery_readable ON ops.outbox_delivery
        FOR SELECT TO brain_app
        USING (true)
    """,
    # A delivery is written with its event, before anybody has attempted it.
    """
    CREATE POLICY outbox_delivery_schedulable ON ops.outbox_delivery
        FOR INSERT TO brain_app
        WITH CHECK (state = 'pending' AND attempts = 0)
    """,
    # Moved only while pending. A settled delivery is history.
    """
    CREATE POLICY outbox_delivery_movable ON ops.outbox_delivery
        FOR UPDATE TO brain_app
        USING (state = 'pending')
        WITH CHECK (true)
    """,
)


#: The control-run name constraint, widened for `outbox_dispatch`. Alphabetical, matching how
#: `brain.tables.identity.one_of` sorts, so the model and the migration compare equal as text.
WITH_OUTBOX_DISPATCH = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction')"
)
WITHOUT_OUTBOX_DISPATCH = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'knowledge_reverification', 'model_health_probes', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction')"
)

#: What this migration replaces: `0025`'s list, which is the one in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_OUTBOX_DISPATCH: WITH_OUTBOX_DISPATCH}

#: Drops the control-run name constraint by whichever name it has. `0025` passed a name that
#: was already prefixed, so a database built by it holds `ck_control_run_ck_control_run_control_
#: run_name` while the model declares `ck_control_run_control_run_name`, and a named drop of
#: either would be wrong on one of the two. Matched on its suffix and dropped by the name found.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'ops.control_run'::regclass
           AND c.contype = 'c'
           AND right(c.conname, 16) = 'control_run_name'
    LOOP
        EXECUTE 'ALTER TABLE ops.control_run DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Check constraints take their bare names. Alembic applies `NAMING_CONVENTION["ck"]` on top
    # of whatever is passed, so a name written out in full arrives doubled, and one of these
    # was long enough to be truncated at sixty-three characters as well. `0026` records the
    # same trap on the drop side, and `tests/unit/test_outbox_store.py` compares what this
    # builds with what the models declare, which is how it was found here.
    op.create_table(
        "webhook_subscriber",
        sa.Column("subscriber_id", sa.String(128), primary_key=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("secret_path", sa.String(200), nullable=False),
        sa.Column("secret_role", sa.String(32), nullable=False),
        sa.Column("kinds", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(subscriber_id)) >= 1",
            name="subscriber_id_present",
        ),
        sa.CheckConstraint(
            "length(btrim(endpoint)) BETWEEN 1 AND 2048",
            name="endpoint_present",
        ),
        sa.CheckConstraint(
            "secret_role IN ('application', 'browser_runner', 'worker')",
            name="secret_role",
        ),
        sa.CheckConstraint("cardinality(kinds) >= 1", name="takes_something"),
        sa.CheckConstraint(
            "kinds <@ ARRAY['approval.requested', 'automation.run_finished', "
            "'connector.health_changed', 'operation.settled']::text[]",
            name="kinds_known",
        ),
        sa.CheckConstraint("length(btrim(created_by)) >= 1", name="created_by_present"),
        schema="ops",
    )
    op.create_table(
        "outbox_event",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(128), nullable=False),
        sa.Column("record_id", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("length(btrim(event_id)) >= 1", name="event_id_present"),
        sa.CheckConstraint(
            "kind IN ('approval.requested', 'automation.run_finished', "
            "'connector.health_changed', 'operation.settled')",
            name="kind",
        ),
        sa.CheckConstraint("length(btrim(record_id)) >= 1", name="record_id_present"),
        sa.CheckConstraint("jsonb_typeof(attributes) = 'object'", name="attributes_object"),
        schema="ops",
    )
    op.create_table(
        "outbox_delivery",
        sa.Column(
            "event_id",
            sa.String(128),
            sa.ForeignKey(
                "ops.outbox_event.event_id", name="fk_outbox_delivery_event_id_outbox_event"
            ),
            primary_key=True,
        ),
        sa.Column(
            "subscriber_id",
            sa.String(128),
            sa.ForeignKey(
                "ops.webhook_subscriber.subscriber_id",
                name="fk_outbox_delivery_subscriber_id_webhook_subscriber",
            ),
            primary_key=True,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("state", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "due_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("attempts BETWEEN 0 AND 8", name="attempts_within_the_cap"),
        sa.CheckConstraint("state IN ('delivered', 'exhausted', 'pending')", name="state"),
        sa.CheckConstraint(
            "attempts = 0 OR last_attempt_at IS NOT NULL",
            name="an_attempt_has_an_instant",
        ),
        sa.CheckConstraint(
            "last_reason IS NULL OR length(last_reason) <= 2000",
            name="reason_is_a_sentence",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_outbox_delivery_due",
        "outbox_delivery",
        ["due_at"],
        schema="ops",
        postgresql_where=sa.text("state = 'pending'"),
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_OUTBOX_DISPATCH, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_OUTBOX_DISPATCH,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.drop_index("ix_outbox_delivery_due", table_name="outbox_delivery", schema="ops")
    op.drop_table("outbox_delivery", schema="ops")
    op.drop_table("outbox_event", schema="ops")
    op.drop_table("webhook_subscriber", schema="ops")
