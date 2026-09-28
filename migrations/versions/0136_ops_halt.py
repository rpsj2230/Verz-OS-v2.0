"""A halt and its resume are rows, so a stop survives the restart that usually follows it.

`brain.ops.halt` argues that a stop held in a process is undone by the deploy that follows it, and
that `Halt` is a value meant to be written down and read back. This is where it is written down.
The store, the three routes and admission reading the persisted state are the package after this
one; until they land, nothing writes a row here and admission reads the halts it is handed.

**Insert-only, one row per act.** A halt row and a resume row are two facts; updating a halt row
to say it ended would overwrite who stopped the system with who restarted it. The current state is
the latest row per scope and target, which `ix_ops_halt_scope_target_at` serves. SELECT and INSERT
for the application, and no UPDATE or DELETE, so the absence of either grant is the rule.

**No effects column.** `Halt.effects` defaults to both effects and every halt the console declares
is `stop_everything`'s, so a row reads back as both, which is the direction that fails closed. A
narrower halt is a column and a migration on the day something declares one.

**The ledger entry is written by a trigger on the row**, for `0054`'s reason, with `0003`'s append
block as `0105` writes it. The entry names the act and the scope and never the target, which may be
a person's id, nor the reason, which is prose an administrator typed. The audit grammar is widened
by one action, `halt`, and one subject kind, `halt`, over `0105`'s action list and `0104`'s subject
grammar, which are the ones in the database.

**The downgrade** drops the trigger, its function and the table, and puts both lists back `NOT
VALID`, for `0026`'s reason: an entry already recorded stays.

Drafted on 2026-09-17 as 0090 over 0083 and never run; landed on 2026-09-28 as 0136 over 0121,
with the grammar lists rebuilt from today's, since the draft's would have dropped the four actions
and the subject kind added after 0083.

It is the table M27.12.4 needs and claims nothing: that leaf closes when the Stop control
halts an install and the halt is seen to survive a restart.

Task ids: none

Revision ID: 0136
Revises: 0121
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0136"
# The newest migration on origin/main when this landed. 0118 to 0135 are held by Wave 2
# packages still in flight; whichever lands after this re-points at it.
down_revision = "0121"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.halt",)

APP_ROLE = "brain_app"

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0105`'s.
WIDENED_ACTIONS = (
    "action IN ('agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'compose_change', 'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', "
    "'grant', 'halt', 'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', "
    "'principal_state', 'publish', 'record_read', 'retention', 'revoke', 'routing', "
    "'session_end', 'setting', 'sign_in', 'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'compose_change', 'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', "
    "'grant', 'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', "
    "'principal_state', 'publish', 'record_read', 'retention', 'revoke', 'routing', "
    "'session_end', 'setting', 'sign_in', 'skill', 'vault_access', 'webhook')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0104`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|breach|connector|credential|department|entity|erasure|grant"
    "|halt|leash|legal_hold|memory|principal|retention|routing|scope|session|setting|skill"
    "|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|breach|connector|credential|department|entity|erasure|grant"
    "|leash|legal_hold|memory|principal|retention|routing|scope|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0105`'s action list and `0104`'s subject grammar.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

#: Copied for `0009`'s reason and held equal to `brain.tables.halt` and `brain.ops.halt` by
#: `tests/unit/test_halt_table.py`.
ACT_CHARS = 8
SCOPE_CHARS = 16
TARGET_CHARS = 128
PRINCIPAL_ID_CHARS = 128
ROLE_CHARS = 64
MINIMUM_REASON = 12
ACTS = "act IN ('halt', 'resume')"
SCOPES = "scope IN ('agent', 'connector', 'department', 'everything', 'person')"

POLICIES: tuple[str, ...] = (
    "ALTER TABLE ops.halt ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY halt_readable ON ops.halt
        FOR SELECT TO brain_app
        USING (true)
    """,
    # The actor is the session's principal, so a row cannot say somebody else stopped the system.
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
    -- The append, as 0003, 0050, 0093, 0095b and 0105 write it. See the module docstring.
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


def _create_halt() -> None:
    op.create_table(
        "halt",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("act", sa.String(ACT_CHARS), nullable=False),
        sa.Column("scope", sa.String(SCOPE_CHARS), nullable=False),
        sa.Column("target", sa.String(TARGET_CHARS), nullable=False, server_default=""),
        sa.Column("actor_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("actor_role", sa.String(ROLE_CHARS), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(ACTS, name="act"),
        sa.CheckConstraint(SCOPES, name="scope"),
        sa.CheckConstraint(
            "(scope = 'everything') = (target = '')", name="everything_names_no_target"
        ),
        sa.CheckConstraint(
            f"char_length(btrim(reason)) >= {MINIMUM_REASON}", name="reason_says_something"
        ),
        schema="ops",
    )
    op.create_index("ix_ops_halt_scope_target_at", "halt", ["scope", "target", "at"], schema="ops")


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in s and "DELETE" not in s for s in GRANTS)

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")

    _create_halt()
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
