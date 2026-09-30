"""A skill says where an unanswered question goes, and the handoff is kept until it expires.

M8.3 asks that escalation be an authored step in a skill rather than a model's judgement, that the
person picking it up is told who asked, what, what was tried and what is needed, and that every
escalation has a timeout. `brain.gate.abstain` holds that domain, and nothing stored or sent any of
it. This migration is the two places it lands.

**`agent.skill` gains three nullable columns**: the queue a skill escalates to, the sentence saying
what would unblock its question, and the hours a person has. Null together on every skill that
declares none, so every row written before this reads back as the skill it was and its digest is
unchanged; each constraint binds only a column added here, for
`brain.deployment.compatibility`'s reason about the release still running during a deploy.

**`gate.escalation` is one row per question handed to a person.** It holds the handoff exactly as
`brain.gate.abstain.Handoff` shapes it: the asker, their question in their own words, what was tried
as step names, what the skill's author said is needed, and the trace to quote. It never holds a
passage, a record, a field or the abstention's reason, and it has no column any of them could go in:
the person picking it up may hold less than the asker, and a refusal and an absence are one outcome
to the asker, so they are one outcome here too. See
`brain.ops.escalation_store.A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE`.

Who reads a row is the database's decision. The asker reads theirs, the person it was routed to
reads it, and while nobody was named for its queue when it arrived, whoever is named now reads it,
which is `0104`'s rule for a sensitive referral applied to a queue (`escalation_route.<queue>` in
`ops.setting`, a JSON object whose `person` is the named principal). The asker's own session files
it and records how its delivery went, and nothing else: UPDATE is granted on the two delivery
columns alone. The worker's sweep marks it expired as its own login, which is how the knowledge
review sweep reads past a policy, and no application session can set `expired_at`.

No ledger entry. The row is the record, held where only the asker and the named person may read it;
a ledger entry would copy who asked about what into the one store every holder of the audit reading
grant reads.

**`ops.control_run` admits `escalation_expiry`**, the worker control that marks an escalation
expired once its deadline passes (M8.3.4).

**The downgrade** drops the table, the columns and restores `0133`'s control names, and refuses when
a control run named `escalation_expiry` is kept, for the reason `0133` gives about its own.

Revises `0156`, the head of main when this was written.

Task ids: M8.3.1, M8.3.2, M8.3.4

Revision ID: 0168
Revises: 0156
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0168"
# The head of origin/main when this was written; re-pointed when it lands.
down_revision = "0156"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.escalation",)

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to the models by `tests/unit/test_escalation_store.py`.
ESCALATION_QUEUE_PATTERN = r"^[a-z][a-z0-9_]{0,59}$"
ESCALATION_QUEUE_CHARS = 60
ESCALATION_NEEDS_CHARS = 300
MAX_ESCALATION_HOURS = 72
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
SKILL_NAME_CHARS = 80
AGENT_ID_CHARS = 128
MAX_QUESTION_CHARS = 4000
TRACE_CHARS = 128

#: The three checks the skill's columns carry, as (name, predicate), in the order they are added.
SKILL_CHECKS: tuple[tuple[str, str], ...] = (
    ("escalate_to_shape", f"escalate_to IS NULL OR escalate_to ~ '{ESCALATION_QUEUE_PATTERN}'"),
    (
        "an_escalation_says_what_it_needs",
        "(escalate_to IS NULL) = (escalation_needs IS NULL)"
        " AND (escalation_needs IS NULL OR length(btrim(escalation_needs)) > 0)",
    ),
    (
        "escalate_within_hours",
        "escalate_within IS NULL OR (escalate_to IS NOT NULL"
        f" AND escalate_within BETWEEN 1 AND {MAX_ESCALATION_HOURS})",
    ),
)

#: `0056`'s CREATE TABLE for `agent.skill`, as `0121` left it, brought up to what this leaves
#: behind, for the comparison with the model. Held to the ALTERs the upgrade emits by
#: `tests/unit/test_escalation_store.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "edited_from VARCHAR(64), CONSTRAINT pk_skill PRIMARY KEY (digest),": (
        f"edited_from VARCHAR(64), escalate_to VARCHAR({ESCALATION_QUEUE_CHARS}), "
        f"escalation_needs VARCHAR({ESCALATION_NEEDS_CHARS}), escalate_within SMALLINT, "
        "CONSTRAINT pk_skill PRIMARY KEY (digest),"
    ),
    "CONSTRAINT fk_skill_edited_from_skill FOREIGN KEY(edited_from) "
    "REFERENCES agent.skill (digest) )": (
        "".join(f"CONSTRAINT ck_skill_{name} CHECK ({check}), " for name, check in SKILL_CHECKS)
        + "CONSTRAINT fk_skill_edited_from_skill FOREIGN KEY(edited_from) "
        "REFERENCES agent.skill (digest) )"
    ),
}

#: `brain.gate.abstain.EscalationTrigger`'s values, and the delivery outcomes a row may record.
TRIGGERS = "trigger IN ('abstention', 'approval required', 'authored step')"
DELIVERIES = "delivery IS NULL OR delivery IN ('not_sent', 'refused', 'sent', 'unknown')"

PRINCIPAL = "current_setting('app.principal_id', true)"

#: Whether a row is readable by this session: the asker's, routed to them, or routed to nobody and
#: they are named for its queue now.
VISIBLE_ESCALATION = """(
            asker_id = current_setting('app.principal_id', true)
            OR routed_to = current_setting('app.principal_id', true)
            OR (
                routed_to IS NULL
                AND EXISTS (
                    SELECT 1 FROM ops.setting s
                     WHERE s.key = 'escalation_route.' || queue
                       AND s.deleted_at IS NULL
                       AND s.value ->> 'person' = current_setting('app.principal_id', true)
                )
            )
        )"""

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.escalation ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY escalation_read_by_its_people ON gate.escalation
        FOR SELECT TO brain_app
        USING {VISIBLE_ESCALATION}
    """,
    f"""
    CREATE POLICY escalation_filed_by_the_asker ON gate.escalation
        FOR INSERT TO brain_app
        WITH CHECK (asker_id = {PRINCIPAL} AND delivered_at IS NULL AND expired_at IS NULL)
    """,
    f"""
    CREATE POLICY escalation_delivery_recorded_by_the_asker ON gate.escalation
        FOR UPDATE TO brain_app
        USING (asker_id = {PRINCIPAL} AND delivered_at IS NULL)
        WITH CHECK (asker_id = {PRINCIPAL} AND expired_at IS NULL)
    """,
)

#: SELECT and INSERT, and UPDATE of the two delivery columns alone. Never DELETE: a handoff is a
#: record, and never `expired_at`, which is the worker's.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON gate.escalation TO brain_app",
    "GRANT UPDATE (delivered_at, delivery) ON gate.escalation TO brain_app",
)

#: The control-run names, with and without `escalation_expiry`. The second is `0133`'s.
WITH_ESCALATION_EXPIRY = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'escalation_expiry', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh', 'vault_audit_ship', "
    "'vault_token_renewal')"
)
WITHOUT_ESCALATION_EXPIRY = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)

#: What this migration replaces: `0133`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_ESCALATION_EXPIRY: WITH_ESCALATION_EXPIRY}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0133` copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname
          FROM pg_constraint c
         WHERE c.conrelid = 'ops.control_run'::regclass
           AND c.contype = 'c'
           AND right(c.conname, 16) = 'control_run_name'
    LOOP
        EXECUTE 'ALTER TABLE ops.control_run DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""

#: The downgrade's refusal, for a run of the control it would stop admitting.
REFUSE_A_KEPT_RUN = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ops.control_run WHERE name = 'escalation_expiry') THEN
        RAISE EXCEPTION 'escalation_expiry has runs recorded; a downgrade would orphan them';
    END IF;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # The skill's escalation. Bare constraint names: alembic applies the naming convention.
    op.add_column(
        "skill", sa.Column("escalate_to", sa.String(ESCALATION_QUEUE_CHARS)), schema="agent"
    )
    op.add_column(
        "skill", sa.Column("escalation_needs", sa.String(ESCALATION_NEEDS_CHARS)), schema="agent"
    )
    op.add_column("skill", sa.Column("escalate_within", sa.SmallInteger()), schema="agent")
    for name, check in SKILL_CHECKS:
        op.create_check_constraint(name, "skill", check, schema="agent")

    op.create_table(
        "escalation",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("queue", sa.String(ESCALATION_QUEUE_CHARS), nullable=False),
        sa.Column("skill_name", sa.String(SKILL_NAME_CHARS), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("asker_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("tried", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("needed", sa.String(ESCALATION_NEEDS_CHARS), nullable=False),
        sa.Column("trace_ref", sa.String(TRACE_CHARS), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("routed_to", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery", sa.String(16), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(TRIGGERS, name="trigger"),
        sa.CheckConstraint(f"queue ~ '{ESCALATION_QUEUE_PATTERN}'", name="queue_shape"),
        sa.CheckConstraint(f"asker_id ~ '{IDENTIFIER}'", name="asker_id_shape"),
        sa.CheckConstraint(
            f"routed_to IS NULL OR routed_to ~ '{IDENTIFIER}'", name="routed_to_shape"
        ),
        sa.CheckConstraint(
            f"length(btrim(question)) > 0 AND length(question) <= {MAX_QUESTION_CHARS}",
            name="question_present",
        ),
        sa.CheckConstraint("jsonb_typeof(tried) = 'array'", name="tried_is_a_list"),
        sa.CheckConstraint("length(btrim(needed)) > 0", name="needed_present"),
        sa.CheckConstraint("expires_at > raised_at", name="expires_after_it_is_raised"),
        sa.CheckConstraint(DELIVERIES, name="delivery"),
        sa.CheckConstraint(
            "(delivered_at IS NULL) = (delivery IS NULL)", name="a_delivery_says_how_it_went"
        ),
        sa.CheckConstraint(
            "expired_at IS NULL OR expired_at >= expires_at", name="expired_once_it_was_due"
        ),
        schema="gate",
    )
    op.create_index("ix_escalation_asker", "escalation", ["asker_id", "raised_at"], schema="gate")
    op.create_index(
        "ix_escalation_routed_to", "escalation", ["routed_to", "raised_at"], schema="gate"
    )
    op.create_index(
        "ix_escalation_open",
        "escalation",
        ["expires_at"],
        schema="gate",
        postgresql_where=sa.text("expired_at IS NULL"),
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)

    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_ESCALATION_EXPIRY, schema="ops"
    )


def downgrade() -> None:
    op.execute(REFUSE_A_KEPT_RUN)
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_ESCALATION_EXPIRY,
        schema="ops",
        postgresql_not_valid=True,
    )
    # The indexes and the policies go with the table.
    op.drop_table("escalation", schema="gate")
    for name, _ in reversed(SKILL_CHECKS):
        # Bare, as created: alembic applies the naming convention to a drop as well.
        op.drop_constraint(name, "skill", schema="agent", type_="check")
    for column in ("escalate_within", "escalation_needs", "escalate_to"):
        op.drop_column("skill", column, schema="agent")
