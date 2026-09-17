"""A halt and its resume are rows, so a stop survives the restart that usually follows it.

DRAFT, never run against a database. See the commit message for what is left.

**Insert-only, one row per act.** A halt row and a resume row are two facts; updating a halt row
to say it ended would overwrite who stopped the system with who restarted it. The current state is
the latest row per scope and target, read by the store that follows.

**The ledger entry is written by a trigger on the row**, for `0054`'s reason, with `0059`'s append
block, and the audit grammar is widened as `0059` widens it: one action, `halt`, one subject kind,
`halt`.

Task ids: none (draft; M27.12.4 is not yet proved)

Revision ID: 0090
Revises: 0083
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0090"
down_revision = "0083"
branch_labels = None
depends_on = None

TABLES: tuple[str, ...] = ("ops.halt",)

APP_ROLE = "brain_app"

WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'halt', "
    "'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', "
    "'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', "
    "'skill', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|erasure|grant|halt|leash|legal_hold"
    "|memory|principal|retention|routing|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|erasure|grant|leash|legal_hold"
    "|memory|principal|retention|routing|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)

MINIMUM_REASON = 12

CHECKS: tuple[tuple[str, str], ...] = (
    ("act", "act IN ('halt', 'resume')"),
    ("scope", "scope IN ('everything', 'department', 'agent', 'connector', 'person')"),
    ("everything_names_no_target", "(scope = 'everything') = (target = '')"),
    ("reason_says_something", f"char_length(btrim(reason)) >= {MINIMUM_REASON}"),
)

POLICIES: tuple[str, ...] = (
    "ALTER TABLE ops.halt ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY halt_readable ON ops.halt
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY halt_written_by_the_session ON ops.halt
        FOR INSERT TO brain_app
        WITH CHECK (actor_id = current_setting('app.principal_id', true))
    """,
)

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.halt TO brain_app",)

TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_halt() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'halt:' || NEW.id;
    v_details jsonb := jsonb_build_object('act', NEW.act, 'scope', NEW.scope);
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(
        NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32)
    );
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, NEW.actor_id, 'halt', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.actor_id, 'halt', v_subject,
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

TRIGGER = """
CREATE TRIGGER halt_is_audited
    AFTER INSERT ON ops.halt
    FOR EACH ROW EXECUTE FUNCTION ops.record_halt()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in s and "DELETE" not in s for s in GRANTS)

    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")

    op.create_table(
        "halt",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("act", sa.String(8), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("target", sa.String(128), nullable=False, server_default=""),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="ops",
    )
    for name, condition in CHECKS:
        op.create_check_constraint(name, "halt", condition, schema="ops")
    op.create_index("ix_ops_halt_scope_target_at", "halt", ["scope", "target", "at"], schema="ops")
    for statement in POLICIES:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER halt_is_audited ON ops.halt")
    op.execute("DROP FUNCTION ops.record_halt()")
    op.drop_table("halt", schema="ops")
    # The entries already written stay; the narrower grammar governs only what is written next.
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs", postgresql_not_valid=True
    )
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
