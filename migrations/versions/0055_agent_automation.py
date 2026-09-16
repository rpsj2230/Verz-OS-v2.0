"""An automation installed onto an agent gets a row, and the row reaches the ledger from the
database.

`brain.console.automation_gallery` installs one of the product's automation templates onto an agent
in one confirmed step, and `brain.tables.agent_automation` argues why the automation and its
scheduled job registry entry are one row. What is here is the table, its policies, its grants and
the trigger that records an install.

**Read and written only in the session's own name.** An automation installed from the gallery runs
as whoever installed it, which is
`brain.console.automation_gallery.AN_INSTALLED_AUTOMATION_RUNS_AS_WHOEVER_INSTALLED_IT`, so the
insert policy admits a row whose principal and installer are both the session's principal, the way
`0044` admits a registration only in the session's own name. The select policy admits the session's
own rows, which is everything the gallery reads: whether this person has already installed a
template on this agent. A listing of an agent's automations for somebody holding the queue screen's
grant is `brain.console.agent_automations.automations_for`'s question, it has no route, and the
migration that gives it one widens this policy with it. A setting that is unset admits nothing.

**SELECT and INSERT, and no UPDATE or DELETE.** Pausing, resuming and removing are decided in
`brain.console.agent_automations` and no route performs them, so a role that could edit this row
would be an edit nothing in the application makes, and one that could delete it would remove the
record of what ran in a person's name.

**One install per agent, template and person**, as a unique constraint, for
`INSTALLING_TWICE_IS_ANSWERED_WITH_THE_FIRST`. The store inserts with `ON CONFLICT DO NOTHING`, and
PostgreSQL fires no row trigger for a row it did not insert, so a second install appends nothing
to the ledger either.

**The ledger entry is `compose_change` about the agent, and no new member was added.** An
automation taken on by an agent is something attached to that agent, which is the event
`COMPOSE_CHANGE` exists for: M39.1.1.3 asks for every attachment added to or removed from an agent
to reach the ledger with who, when and why, and "what has this agent been given to do" is the query
it serves. The part is `automation`, the reference is the automation's id, the direction is
`attached` and the reason code is `template_install`, which are exactly the four details
`brain.audit.record.AuditRecorder.compose_change` writes, and a test holds the two to one answer. A
member of its own was rejected: it would split what was attached to one agent across two actions,
and it would supersede the action list another change in flight is also superseding. The subject
kind `agent` already exists, so neither the action list nor the subject grammar is touched here.

**The append is `0003`'s, a copy beside the others**, for the reason `0047` gives against editing a
function every grant in production goes through. The actor is the row's own `installed_by`; the
reach's digest and the trace come from the settings the store sets in the same transaction.

The downgrade drops the trigger, its function and the table, and with the table every installed
automation. The ledger entries stay, because nothing may delete one.

Task ids: M39.6.1.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.automation",)

APP_ROLE = "brain_app"

#: Copied for the reason `0009` gives about reading live code from a migration, and held equal to
#: `brain.ops.automation_owner.AUTOMATION_ID`, `brain.audit.ledger.IDENTIFIER`,
#: `brain.console.automation_gallery.TEMPLATE_ID` and the widths in
#: `brain.tables.agent_automation` by `tests/unit/test_agent_automation_store.py`.
AUTOMATION_ID_PATTERN = "^[A-Za-z0-9_-]{1,128}$"
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
TEMPLATE_ID_PATTERN = "^[a-z][a-z0-9_]{2,63}$"
MINIMUM_OUTCOME_NAME = 12
MINIMUM_GUARDS = 12

#: The two constant details the trigger writes, as `AuditRecorder.compose_change` spells them.
#: Written out literally in the function below as well, so the SQL is not assembled from strings;
#: a test holds the two equal.
PART = "automation"
REASON_CODE = "template_install"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.automation ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY automation_readable_by_its_principal ON agent.automation
        FOR SELECT TO brain_app
        USING (runs_as_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY automation_installed_in_the_sessions_name ON agent.automation
        FOR INSERT TO brain_app
        WITH CHECK (runs_as_id = {PRINCIPAL} AND installed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.automation TO brain_app",)

AUTOMATION_INSTALL_TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_automation_install() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object(
        'part', 'automation', 'reference', NEW.automation_id,
        'direction', 'attached', 'reason_code', 'template_install'
    );
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    -- The append, as 0003's gate.record_entitlement_change and 0054's
    -- ops.record_credential_write write it.
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
        v_seq, v_at, NEW.installed_by, 'compose_change', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.installed_by, 'compose_change', v_subject,
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

AUTOMATION_INSTALL_TRIGGER = """
CREATE TRIGGER automation_install_is_audited
    AFTER INSERT ON agent.automation
    FOR EACH ROW EXECUTE FUNCTION agent.record_automation_install()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "automation",
        sa.Column("automation_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("runs_as_id", sa.String(128), nullable=False),
        sa.Column("task", sa.String(80), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guards", sa.Text(), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("installed_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"automation_id ~ '{AUTOMATION_ID_PATTERN}'", name="automation_id_shape"
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER_PATTERN}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(
            f"runs_as_id ~ '{IDENTIFIER_PATTERN}'", name="runs_as_id_is_an_identifier"
        ),
        sa.CheckConstraint(
            f"installed_by ~ '{IDENTIFIER_PATTERN}'", name="installed_by_is_an_identifier"
        ),
        sa.CheckConstraint(
            "runs_as_id <> agent_id AND runs_as_id <> ('agent:' || agent_id)",
            name="an_automation_does_not_run_as_its_agent",
        ),
        sa.CheckConstraint(
            f"left(name, 2) = 'I ' AND length(btrim(name)) >= {MINIMUM_OUTCOME_NAME}",
            name="name_is_an_outcome",
        ),
        sa.CheckConstraint("length(btrim(task)) > 0", name="task_present"),
        sa.CheckConstraint(
            f"length(btrim(guards)) >= {MINIMUM_GUARDS}", name="guards_says_what_breaks"
        ),
        sa.CheckConstraint(f"template_id ~ '{TEMPLATE_ID_PATTERN}'", name="template_id_shape"),
        sa.CheckConstraint("template_version >= 1", name="template_version_from_one"),
        sa.UniqueConstraint(
            "agent_id",
            "template_id",
            "runs_as_id",
            name="one_install_per_agent_template_and_person",
        ),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(AUTOMATION_INSTALL_TRIGGER_FUNCTION)
    op.execute(AUTOMATION_INSTALL_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER automation_install_is_audited ON agent.automation")
    op.execute("DROP FUNCTION agent.record_automation_install()")
    # The policies and the grants go with the table.
    op.drop_table("automation", schema="agent")
