"""An installed automation runs: its runs, its schedule changes and their ledger entries, and a
place on the worker's schedule.

`brain.ops.automation_run` decides a run and `brain.tables.automation_run` argues the two tables.
What is here is the tables, their policies and grants, the trigger that records a schedule change,
the widening of `agent.automation`'s own policies that starting and stopping one needs, and the name
the worker's schedule records its runs under.

**`agent.automation_run` is written only by the worker.** The worker drains due automations on the
database owner's connection, as `brain.ops.erasure_store` does, so the application role holds SELECT
and nothing else, and no request the console serves can record a run. Read with `USING (true)`, for
the reason `0053` gives: who may see a run is `brain.console.agent_automations.history`, decided
against the reader's live grants.

**`agent.automation_schedule` is inserted in the session's own name.** The insert policy admits a
row whose `changed_by` is the session's principal, the way `0055` admits an install, so a start or a
stop cannot be recorded in somebody else's name. SELECT and INSERT, and no UPDATE or DELETE: a
schedule change is reversed by the next one, and the row that says why an automation stopped is the
one a person reads before starting it again.

**The ledger entry is `compose_change` about the agent, and no member was added.** `0055` records an
install as the automation attached to the agent with reason `template_install`; a start is the same
attachment put on the schedule and a stop or a pause is its detachment, with the row's reason as the
reason code. A member of its own was rejected for `0055`'s reason, and because another change in
flight is widening the action list: a second widening written against the same predecessor is a
supersession one of the two would silently undo.

**`agent.automation` becomes readable by the application and its next run updatable.** `0055` said
the migration that gives an agent's automations a listing widens the select policy with it, and this
is that migration: `brain.automation_schedule_routes` lists them through `automations_for`, which
decides who may see which. The update is a column grant on `next_run_at` and `updated_at` alone, and
its policy refuses a session with no principal set, so an unattributed change writes nothing.

**`automation_run` joins the control-run names**, replacing `0066`'s list, for the reason `0060`
gives.

The downgrade drops the trigger, its function and both tables, restores `0055`'s policies and
grants and `0066`'s names. The names come back `NOT VALID`: a run already recorded under
`automation_run` is kept and not re-checked, because a run that happened is not deleted to make a
constraint fit, and only a run written after the downgrade is refused. Re-checking the old rows
would make the downgrade fail on every install that has run an automation. The ledger entries stay,
because nothing may delete one.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.automation_run", "agent.automation_schedule")

APP_ROLE = "brain_app"

#: Copied for the reason `0009` gives about reading live code from a migration, and held equal to
#: `brain.tables.automation_run` by `tests/unit/test_automation_run_store.py`.
AUTOMATION_ID_PATTERN = "^[A-Za-z0-9_-]{1,128}$"
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
RUN_ID_PATTERN = "^run_[0-9a-f]{32}$"
ENT_HASH_PATTERN = "^[0-9a-f]{32}$"
OUTCOME_IN = "outcome IN ('failed', 'refused', 'succeeded')"
REASON_IN = (
    "reason IN ('agent_unavailable', 'failed_repeatedly', 'owner_gone', 'owner_lost_reach', "
    "'stopped', 'task_unbuilt')"
)
SCHEDULE_REASON_IN = (
    "reason IN ('agent_unavailable', 'failed_repeatedly', 'owner_gone', 'owner_lost_reach', "
    "'started', 'stopped', 'task_unbuilt')"
)

#: The control-run names, with and without `automation_run`. The second is `0066`'s.
WITH_AUTOMATION_RUN = (
    "name IN ('audit_anchor', 'automation_run', 'backup_exposure', 'canary_run', "
    "'denial_digest', 'directory_sync', 'erasure_queue', 'knowledge_reverification', "
    "'model_health_probes', 'outbox_dispatch', 'queue_redrive', 'resolution_calibration', "
    "'restore_drill', 'retention_sweep', 'side_effect_resume', 'spend_correction', "
    "'spend_report_refresh', 'vault_token_renewal')"
)
WITHOUT_AUTOMATION_RUN = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'erasure_queue', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh', "
    "'vault_token_renewal')"
)

#: What this migration replaces: `0066`'s control names, the one list in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_AUTOMATION_RUN: WITH_AUTOMATION_RUN}

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.automation_run ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY automation_run_readable ON agent.automation_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    "ALTER TABLE agent.automation_schedule ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY automation_schedule_readable ON agent.automation_schedule
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY automation_schedule_changed_in_the_sessions_name ON agent.automation_schedule
        FOR INSERT TO brain_app
        WITH CHECK (changed_by = {PRINCIPAL})
    """,
)

#: `0055`'s select policy, replaced, and the update policy starting and stopping needs.
AUTOMATION_POLICIES: tuple[str, ...] = (
    "DROP POLICY automation_readable_by_its_principal ON agent.automation",
    """
    CREATE POLICY automation_readable ON agent.automation
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY automation_rescheduled_by_somebody ON agent.automation
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (COALESCE({PRINCIPAL}, '') <> '')
    """,
)

#: `0055`'s select policy, as the downgrade puts it back.
AUTOMATION_POLICIES_BEFORE: tuple[str, ...] = (
    "DROP POLICY automation_rescheduled_by_somebody ON agent.automation",
    "DROP POLICY automation_readable ON agent.automation",
    f"""
    CREATE POLICY automation_readable_by_its_principal ON agent.automation
        FOR SELECT TO brain_app
        USING (runs_as_id = {PRINCIPAL})
    """,
)

#: SELECT on the runs, SELECT and INSERT on the schedule, and the two columns a start or a stop
#: moves. Never DELETE anywhere, and never UPDATE on a run or a schedule row.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT ON agent.automation_run TO brain_app",
    "GRANT SELECT, INSERT ON agent.automation_schedule TO brain_app",
    "GRANT UPDATE (next_run_at, updated_at) ON agent.automation TO brain_app",
)

REVOKES: tuple[str, ...] = (
    "REVOKE UPDATE (next_run_at, updated_at) ON agent.automation FROM brain_app",
)

SCHEDULE_TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_automation_schedule() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object(
        'part', 'automation', 'reference', NEW.automation_id,
        'direction', CASE WHEN NEW.next_run_at IS NULL THEN 'detached' ELSE 'attached' END,
        'reason_code', NEW.reason
    );
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    -- The append, as 0003's gate.record_entitlement_change and 0055's
    -- agent.record_automation_install write it.
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

SCHEDULE_TRIGGER = """
CREATE TRIGGER automation_schedule_is_audited
    AFTER INSERT ON agent.automation_schedule
    FOR EACH ROW EXECUTE FUNCTION agent.record_automation_schedule()
"""

#: Drops the control-run name constraint by whichever name it has. See `0060`, which copies `0030`.
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

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "automation_run",
        sa.Column("run_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("automation_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("ent_hash", sa.String(32), nullable=True),
        sa.Column(
            "result",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.CheckConstraint(f"run_id ~ '{RUN_ID_PATTERN}'", name="run_id_shape"),
        sa.CheckConstraint(
            f"automation_id ~ '{AUTOMATION_ID_PATTERN}'", name="automation_id_shape"
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER_PATTERN}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(
            f"principal_id ~ '{IDENTIFIER_PATTERN}'", name="principal_id_is_an_identifier"
        ),
        sa.CheckConstraint(OUTCOME_IN, name="outcome"),
        sa.CheckConstraint(
            "(outcome = 'refused') = (reason IS NOT NULL)", name="a_reason_exactly_when_refused"
        ),
        sa.CheckConstraint(f"reason IS NULL OR {REASON_IN}", name="reason"),
        sa.CheckConstraint(
            "cardinality(result) = 0 OR outcome = 'succeeded'",
            name="a_result_only_from_a_success",
        ),
        sa.CheckConstraint(f"ent_hash IS NULL OR ent_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash"),
        sa.CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        schema="agent",
    )
    op.create_index(
        "ix_automation_run_automation_finished",
        "automation_run",
        ["automation_id", "finished_at"],
        schema="agent",
    )
    op.create_table(
        "automation_schedule",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("automation_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("changed_by", sa.String(128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"automation_id ~ '{AUTOMATION_ID_PATTERN}'", name="automation_id_shape"
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER_PATTERN}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(
            f"changed_by ~ '{IDENTIFIER_PATTERN}'", name="changed_by_is_an_identifier"
        ),
        sa.CheckConstraint(SCHEDULE_REASON_IN, name="reason"),
        sa.CheckConstraint(
            "(reason = 'started') = (next_run_at IS NOT NULL)",
            name="a_start_has_a_next_run_and_nothing_else_does",
        ),
        schema="agent",
    )
    op.create_index(
        "ix_automation_schedule_automation_at",
        "automation_schedule",
        ["automation_id", "at"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in AUTOMATION_POLICIES:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(SCHEDULE_TRIGGER_FUNCTION)
    op.execute(SCHEDULE_TRIGGER)
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint("control_run_name", "control_run", WITH_AUTOMATION_RUN, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_AUTOMATION_RUN,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.execute("DROP TRIGGER automation_schedule_is_audited ON agent.automation_schedule")
    op.execute("DROP FUNCTION agent.record_automation_schedule()")
    for statement in REVOKES:
        op.execute(statement)
    for statement in AUTOMATION_POLICIES_BEFORE:
        op.execute(statement)
    op.drop_index(
        "ix_automation_schedule_automation_at", table_name="automation_schedule", schema="agent"
    )
    op.drop_table("automation_schedule", schema="agent")
    op.drop_index(
        "ix_automation_run_automation_finished", table_name="automation_run", schema="agent"
    )
    # The policies and the grants go with the tables.
    op.drop_table("automation_run", schema="agent")
