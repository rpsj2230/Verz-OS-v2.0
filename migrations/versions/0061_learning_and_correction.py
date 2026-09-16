"""What a learning proposed and replaced gets a row, and so does every correction, which is audited.

`brain.tables.learning` argues the shape of both records. What is here is the two tables, their
policies, their grants, the ledger member and subject kind a correction is recorded under, and the
trigger that records it.

**Read by the application and added to, and nothing else.** SELECT and INSERT on both, no UPDATE and
no DELETE, and the policies admit any row the constraints admit. A correction is reversed by a later
correction the other way, which `brain.memory.correction.superseded_ids` reads as the pair's latest
word, so nothing the application does to undo an undo needs to touch a row already written. `USING
(true)` on the reads is not an absence of a permission check, for the reason `0030` gives: whether a
reader may be told a learning or a correction exists is `brain.memory.formation.may_recall`'s
question, asked against the memory's own capability tags by every route that reads these rows.

**The tier is held to the change by the table.** `change_needs_its_tier` pairs every change with
the tier `brain.memory.tiers.BLAST_RADIUS` gives it, so a row claiming a scope widening applies by
itself is refused whoever writes it. Copied as SQL for the reason `0009` gives, and held equal to
the model by `tests/unit/test_memory_store.py`.

**The ledger gains a member, `memory`, and a subject kind, `memory`**, which
`brain.audit.ledger.AuditAction` argues. The action list and the subject grammar are superseded
again, replacing `0060`'s, which are the two in the database.

**The trigger fires on a correction's insert and on nothing else**, with the actor read off the
row's own `recorded_by`, as `0057`'s reads `connected_by`. The details are the kind of correction
alone: never a statement, which neither table holds, and never the memory that replaced the one
marked, which the row keeps. A learning's insert is not audited; `brain.tables.learning` says why.

**The append is `0003`'s, and this is one more copy of that block**, beside `0047`'s to `0060`'s,
for the reason `0047` gives against editing a function every grant in production goes through. Same
advisory lock, same sequence and parent read, same `obs.audit_entry_hash`, same refusal of a
discarded MERGE.

**The downgrade can fail, which is correct**, for `0026`'s reason: narrowing the action list and
the subject grammar is refused once any entry records a correction, and an audit entry cannot be
deleted to make room. It drops both tables with it, and with them every correction, which is the
state before this migration: recall then reads no corrections, as it did.

Task ids: M27.7.21, M27.7.22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("mem.learning", "mem.correction")

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.learning`, `brain.agents.model.AGENT_ID_CHARS`,
#: `brain.audit.ledger.IDENTIFIER` and `brain.tables.identity.PRINCIPAL_ID_CHARS` by
#: `tests/unit/test_memory_store.py`.
MEMORY_ID_CHARS = 26
CHANGE_CHARS = 32
SIGNAL_CHARS = 32
SUBJECT_CHARS = 200
CORRECTION_CHARS = 16
AGENT_ID_CHARS = 60
PRINCIPAL_ID_CHARS = 128
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"

#: `brain.tables.learning`'s generated predicates, as they rendered on 2026-09-17.
CHANGES = (
    "change IN ('capability_addition', 'company_knowledge', 'entity_link', 'fast_path_rule', "
    "'leash_increase', 'money_boundary_merge', 'negative_signal', 'preference', "
    "'procedural_shortcut', 'retrieval_boost', 'retrieval_demotion', 'scope_widening', "
    "'session_context')"
)
CHANGE_NEEDS_ITS_TIER = (
    "(change = 'session_context' AND tier = 0) OR (change = 'preference' AND tier = 1) OR "
    "(change = 'retrieval_boost' AND tier = 1) OR (change = 'retrieval_demotion' AND tier = 1) OR "
    "(change = 'entity_link' AND tier = 1) OR (change = 'negative_signal' AND tier = 1) OR "
    "(change = 'fast_path_rule' AND tier = 2) OR (change = 'procedural_shortcut' AND tier = 2) OR "
    "(change = 'scope_widening' AND tier = 3) OR (change = 'company_knowledge' AND tier = 3) OR "
    "(change = 'leash_increase' AND tier = 3) OR (change = 'money_boundary_merge' AND tier = 3) OR "
    "(change = 'capability_addition' AND tier = 3)"
)
EVIDENCE_IS_SIGNALS = (
    "evidence <@ ARRAY['contradicted', 'copied', 'escalated', 'reasked', 'rejected', 'reopened', "
    "'taken_over']::varchar[]"
)
CORRECTIONS = "correction IN ('demoted', 'superseded')"
PROMPTED_BY = (
    "prompted_by IS NULL OR prompted_by IN ('contradicted', 'copied', 'escalated', 'reasked', "
    "'rejected', 'reopened', 'taken_over')"
)
A_CORRECTION_HAS_ITS_KINDS_SHAPE = (
    "(correction = 'superseded' AND by_id IS NOT NULL AND prompted_by IS NOT NULL "
    "AND field IS NULL AND by_id <> memory_id) OR (correction = 'demoted' AND by_id IS NULL "
    "AND prompted_by IS NULL AND field IS NOT NULL AND length(btrim(field)) > 0)"
)

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0060`'s.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'publish', 'record_read', 'retention', 'revoke', "
    "'routing', 'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'publish', 'record_read', 'retention', 'revoke', 'routing', "
    "'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0060`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|erasure|grant|leash|legal_hold"
    "|memory|principal|retention|routing|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|erasure|grant|leash|legal_hold"
    "|principal|retention|routing|session|setting|skill|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0060`'s action list and `0060`'s subject grammar.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

RLS: tuple[str, ...] = (
    "ALTER TABLE mem.learning ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mem.correction ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY learning_readable ON mem.learning
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY learning_recorded ON mem.learning
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY correction_readable ON mem.correction
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY correction_recorded ON mem.correction
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON mem.learning TO brain_app",
    "GRANT SELECT, INSERT ON mem.correction TO brain_app",
)

#: A correction, with the actor its own column names and its kind in the details.
CORRECTION_TRIGGER_FUNCTION = """
CREATE FUNCTION mem.record_correction() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'memory:' || NEW.memory_id;
    v_details jsonb := jsonb_build_object('change', NEW.correction);
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    -- The append, as 0003's gate.record_entitlement_change and every trigger since write it.
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
        v_seq, v_at, NEW.recorded_by, 'memory', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.recorded_by, 'memory', v_subject,
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

CORRECTION_TRIGGER = """
CREATE TRIGGER correction_is_audited
    AFTER INSERT ON mem.correction
    FOR EACH ROW EXECUTE FUNCTION mem.record_correction()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "learning",
        sa.Column("memory_id", sa.String(MEMORY_ID_CHARS), primary_key=True, nullable=False),
        sa.Column("change", sa.String(CHANGE_CHARS), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("subject", sa.String(SUBJECT_CHARS), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=True),
        sa.Column("replaced_id", sa.String(MEMORY_ID_CHARS), nullable=True),
        sa.Column(
            "evidence",
            postgresql.ARRAY(sa.String(SIGNAL_CHARS)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"memory_id ~ '{IDENTIFIER}'", name="memory_id_shape"),
        sa.CheckConstraint(CHANGES, name="change"),
        sa.CheckConstraint(CHANGE_NEEDS_ITS_TIER, name="change_needs_its_tier"),
        sa.CheckConstraint("length(btrim(subject)) > 0", name="subject_present"),
        sa.CheckConstraint(
            "agent_id IS NULL OR length(btrim(agent_id)) > 0", name="agent_id_present_when_named"
        ),
        sa.CheckConstraint(
            "replaced_id IS NULL OR replaced_id <> memory_id", name="not_its_own_replacement"
        ),
        sa.CheckConstraint(EVIDENCE_IS_SIGNALS, name="evidence_is_signals"),
        schema="mem",
    )
    op.create_index("ix_learning_agent_id", "learning", ["agent_id"], schema="mem")
    op.create_table(
        "correction",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("memory_id", sa.String(MEMORY_ID_CHARS), nullable=False),
        sa.Column("correction", sa.String(CORRECTION_CHARS), nullable=False),
        sa.Column("by_id", sa.String(MEMORY_ID_CHARS), nullable=True),
        sa.Column("prompted_by", sa.String(SIGNAL_CHARS), nullable=True),
        sa.Column("field", sa.String(SUBJECT_CHARS), nullable=True),
        sa.Column("recorded_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"memory_id ~ '{IDENTIFIER}'", name="memory_id_shape"),
        sa.CheckConstraint(CORRECTIONS, name="correction"),
        sa.CheckConstraint(PROMPTED_BY, name="prompted_by"),
        sa.CheckConstraint(
            A_CORRECTION_HAS_ITS_KINDS_SHAPE, name="a_correction_has_its_kinds_shape"
        ),
        sa.CheckConstraint(f"recorded_by ~ '{IDENTIFIER}'", name="recorded_by_shape"),
        schema="mem",
    )
    op.create_index("ix_correction_memory_id", "correction", ["memory_id"], schema="mem")
    op.create_index("ix_correction_by_id", "correction", ["by_id"], schema="mem")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")
    op.execute(CORRECTION_TRIGGER_FUNCTION)
    op.execute(CORRECTION_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER correction_is_audited ON mem.correction")
    op.execute("DROP FUNCTION mem.record_correction()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", NARROWER_ACTIONS, schema="obs")
    # The policies and the grants go with the tables.
    op.drop_index("ix_correction_by_id", "correction", schema="mem")
    op.drop_index("ix_correction_memory_id", "correction", schema="mem")
    op.drop_table("correction", schema="mem")
    op.drop_index("ix_learning_agent_id", "learning", schema="mem")
    op.drop_table("learning", schema="mem")
