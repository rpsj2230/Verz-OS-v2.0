"""An installed automation is paused, resumed, rescheduled, removed and adopted as change rows, each
reaching the ledger from the database.

`brain.console.automations` decides each change and `brain.tables.automation_change` argues the
table. What is here is the table, its policies and grants, and the trigger that records a change.

**SELECT and INSERT, and no UPDATE or DELETE.** A change is reversed by the next one, and the row
that says an automation was removed, or whose it became, is the one a person reads before deciding
anything else about it. Read with `USING (true)`, for the reason `0067` gives about the schedule
rows: who may see a change is `brain.console.agent_automations.may_see`, decided against the
reader's live grants.

**Inserted only in the session's own name.** The insert policy admits a row whose `changed_by` is
the session's principal, and the table's own constraint makes an adoption's new owner that same
principal, so an automation cannot be handed to somebody else and cannot be changed unattributed.

**The ledger entry is `compose_change` about the agent**, as `0055` records an install and `0067` a
start or a stop: the part is `automation`, the reference its id, the direction `attached` when the
change leaves a next run and `detached` when it leaves none, and the reason code the change's kind.
No action member was added, for `0067`'s reason.

**`agent.automation` is not widened.** The next run a pause, a resume or a schedule change moves is
the column `0067` already lets the application update, and nothing else on the install row changes:
a new cadence or a new owner is a row here, folded over the install when it is read.

The downgrade drops the trigger, its function and the table. The ledger entries stay, because
nothing may delete one; an automation that was removed or adopted reads as its install again, which
is why the downgrade is the release's and not a person's.

Task ids: M27.12.3, M27.15.37, M39.6.1.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0145"
down_revision = "0142"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.automation_change",)

APP_ROLE = "brain_app"

#: Copied for the reason `0009` gives about reading live code from a migration, and held equal to
#: `brain.tables.automation_change` by `tests/unit/test_automation_change_store.py`.
AUTOMATION_ID_PATTERN = "^[A-Za-z0-9_-]{1,128}$"
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
KIND_IN = "kind IN ('adopted', 'paused', 'removed', 'rescheduled', 'resumed')"
EVERY_IN = "every IN ('day', 'week', 'weekday')"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.automation_change ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY automation_change_readable ON agent.automation_change
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY automation_change_in_the_sessions_name ON agent.automation_change
        FOR INSERT TO brain_app
        WITH CHECK (changed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT. Never UPDATE and never DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.automation_change TO brain_app",)

CHANGE_TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_automation_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object(
        'part', 'automation', 'reference', NEW.automation_id,
        'direction', CASE WHEN NEW.next_run_at IS NULL THEN 'detached' ELSE 'attached' END,
        'reason_code', NEW.kind
    );
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    -- The append, as 0067's agent.record_automation_schedule writes it.
    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, NEW.changed_by, 'compose_change', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.changed_by, 'compose_change', v_subject,
                v_ent_hash, v_trace, v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
    RETURN NULL;
END;
$$
"""

CHANGE_TRIGGER = """
CREATE TRIGGER automation_change_is_audited
    AFTER INSERT ON agent.automation_change
    FOR EACH ROW EXECUTE FUNCTION agent.record_automation_change()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "automation_change",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("automation_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("every", sa.String(8), nullable=True),
        sa.Column("weekday", sa.SmallInteger(), nullable=True),
        sa.Column("hour_utc", sa.SmallInteger(), nullable=True),
        sa.Column("runs_as_id", sa.String(128), nullable=True),
        sa.Column("changed_by", sa.String(128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"automation_id ~ '{AUTOMATION_ID_PATTERN}'", name="automation_id_shape"
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER_PATTERN}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(
            f"changed_by ~ '{IDENTIFIER_PATTERN}'", name="changed_by_is_an_identifier"
        ),
        sa.CheckConstraint(KIND_IN, name="kind"),
        sa.CheckConstraint(f"every IS NULL OR {EVERY_IN}", name="every"),
        sa.CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6", name="weekday_is_a_day"),
        sa.CheckConstraint("hour_utc IS NULL OR hour_utc BETWEEN 0 AND 23", name="hour_is_an_hour"),
        sa.CheckConstraint(
            "(kind = 'rescheduled') = (every IS NOT NULL AND hour_utc IS NOT NULL)",
            name="a_cadence_exactly_when_rescheduled",
        ),
        sa.CheckConstraint(
            "(every IS NOT DISTINCT FROM 'week') = (weekday IS NOT NULL)",
            name="a_day_exactly_when_weekly",
        ),
        sa.CheckConstraint(
            "(kind = 'adopted') = (runs_as_id IS NOT NULL)",
            name="an_owner_exactly_when_adopted",
        ),
        sa.CheckConstraint(
            "runs_as_id IS NULL OR (runs_as_id = changed_by AND runs_as_id <> agent_id"
            " AND runs_as_id <> ('agent:' || agent_id))",
            name="an_adoption_is_in_the_adopters_own_name",
        ),
        sa.CheckConstraint(
            "kind NOT IN ('paused', 'removed', 'adopted') OR next_run_at IS NULL",
            name="a_stop_leaves_no_next_run",
        ),
        sa.CheckConstraint(
            "kind <> 'resumed' OR next_run_at IS NOT NULL",
            name="a_resume_leaves_a_next_run",
        ),
        schema="agent",
    )
    op.create_index(
        "ix_automation_change_automation_at",
        "automation_change",
        ["automation_id", "at"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(CHANGE_TRIGGER_FUNCTION)
    op.execute(CHANGE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER automation_change_is_audited ON agent.automation_change")
    op.execute("DROP FUNCTION agent.record_automation_change()")
    op.drop_index(
        "ix_automation_change_automation_at", table_name="automation_change", schema="agent"
    )
    # The policies and the grant go with the table.
    op.drop_table("automation_change", schema="agent")
