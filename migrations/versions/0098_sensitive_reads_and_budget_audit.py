"""A sensitive read reaches the ledger, and so does every budget version.

Two changes to what the ledger is told, both schema only.

**`ops.sensitive_read`: one row per read of a personnel record or a shown salary (M24.3.2).**
`brain.ops.sensitive_read_store.SensitiveReadRecorder` writes a row from the one place a request
finishes, and the row's insert trigger appends a `record_read` entry, as
`brain.audit.record.AuditRecorder.record_read` builds one: the actor is the reader, the subject the
person the record is about (`principal:<id>`) or, for a record that names nobody, the record
itself (`entity:<id>`), and the details the record's kind and the agent when there was one, never
a field that was shown. `brain.tables.sensitive_read` argues the columns. **The entry's reach
digest and trace are the row's own**, which the recorder takes from the finished request, so the
entry never carries `0003`'s placeholder for a write that set no session setting.

**`ops.budget_version`: every version appends a `setting` entry (M24.3.7).** `brain.tables.budget`
recorded the missing entry as a gap, "the identical gap `0004` records for `ops.setting`", and
`0059` closed that one; this closes the budget's. No new action and no new subject kind, for the
reason `brain.tables.audit.GRANT_SUBJECT_KIND` gives against widening a closed vocabulary to make
one trigger read better, and because a new kind is a new question for Needs Rupash item 48's
list of what a department head reads. A ceiling is filed under whose money it counts: a person's
under `principal:`, an agent's under `agent:`, a department's under `department:`, and the
company's under `setting:budget.company`. The actor is the row's `author`, the details are the
level and the period, **never the figure**, which stays on the row. A subject the ledger's grammar
refuses rolls the budget write back, which is `0003`'s refusal of an append discarded silently, in
the direction that keeps the chain whole.

**SELECT and INSERT on the new table, and no UPDATE or DELETE**, for `0093`'s reason: nothing
edits what was read. `USING (true)` on the read, because the only readers are the ledger's own
screens, which decide per entry.

**The append is `0003`'s, one more copy of the block `0054` carries**, for the reason `0047` gives
against editing a function every grant in production goes through.

**The downgrade** drops both triggers and their functions and the table, which discards every
read row (the ledger keeps its entries). Nothing here widens a check constraint, so nothing goes
back `NOT VALID`.

Task ids: M24.3.2, M24.3.7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0098"
# The newest head on origin/main when this was written: 0101 (access_request).
down_revision = "0101"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.sensitive_read",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.sensitive_read` and `brain.audit.ledger` by tests.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
TRACE_ID = r"^[A-Za-z0-9_.-]{1,64}$"
ENT_HASH = r"^[0-9a-f]{32}$"
RECORD_KIND_PATTERN = r"^[a-z][a-z0-9_]*$"
AGENT_PATTERN = r"^[a-z][a-z0-9_]*$"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.sensitive_read TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.sensitive_read ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY sensitive_read_readable ON ops.sensitive_read
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY sensitive_read_appendable ON ops.sensitive_read
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def _append(action: str) -> str:
    """`0054`'s append for one action, reading the actor, subject, details, digest and trace from
    variables the function sets before it."""
    return (
        """
        PERFORM pg_advisory_xact_lock(8274419004);
        SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
        SELECT COALESCE(
            (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
            repeat('0', 64)
        ) INTO v_prev;
        v_entry := obs.audit_entry_hash(
            v_seq, v_at, v_actor, '"""
        + action
        + """', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, '"""
        + action
        + """', v_subject,
                    v_ent_hash, v_trace, v_details, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
"""
    )


_DECLARE = """
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_written integer;
"""

#: One `record_read` entry per read row. The details are the recorder's, key for key.
SENSITIVE_READ_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_sensitive_read() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text := NEW.reader_id;
    v_subject text := CASE
        WHEN NEW.subject_principal IS NOT NULL THEN 'principal:' || NEW.subject_principal
        ELSE 'entity:' || NEW.record_id
    END;
    v_details jsonb := jsonb_build_object('record_kind', NEW.record_kind);
    v_ent_hash text := NEW.ent_hash;
    v_trace text := NEW.trace_id;"""
    + _DECLARE
    + """BEGIN
    IF NEW.agent_id IS NOT NULL THEN
        v_details := v_details || jsonb_build_object('agent', NEW.agent_id);
    END IF;"""
    + _append("record_read")
    + """    RETURN NULL;
END;
$$
"""
)

SENSITIVE_READ_TRIGGER = """
    CREATE TRIGGER sensitive_read_is_audited
        AFTER INSERT ON ops.sensitive_read
        FOR EACH ROW EXECUTE FUNCTION ops.record_sensitive_read()
"""

#: One `setting` entry per budget version, filed under whose money the ceiling counts.
BUDGET_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_budget_version() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text := NEW.author;
    v_subject text := CASE NEW.level
        WHEN 'user' THEN 'principal:' || NEW.subject
        WHEN 'agent' THEN 'agent:' || NEW.subject
        WHEN 'department' THEN 'department:' || NEW.subject
        ELSE 'setting:budget.company'
    END;
    v_details jsonb := jsonb_build_object(
        'budget_level', NEW.level,
        'budget_period', NEW.period
    );
    v_ent_hash text := COALESCE(
        NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32)
    );
    v_trace text := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );"""
    + _DECLARE
    + """BEGIN"""
    + _append("setting")
    + """    RETURN NULL;
END;
$$
"""
)

BUDGET_TRIGGER = """
    CREATE TRIGGER budget_version_is_audited
        AFTER INSERT ON ops.budget_version
        FOR EACH ROW EXECUTE FUNCTION ops.record_budget_version()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "sensitive_read",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("reader_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("record_kind", sa.String(64), nullable=False),
        sa.Column("subject_principal", sa.String(128), nullable=True),
        sa.Column("record_id", sa.String(128), nullable=True),
        sa.Column("ent_hash", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.CheckConstraint(f"reader_id ~ '{IDENTIFIER}'", name="reader_id_shape"),
        sa.CheckConstraint(f"agent_id IS NULL OR agent_id ~ '{AGENT_PATTERN}'", name="agent_shape"),
        sa.CheckConstraint(f"record_kind ~ '{RECORD_KIND_PATTERN}'", name="record_kind_shape"),
        sa.CheckConstraint(
            f"subject_principal IS NULL OR subject_principal ~ '{IDENTIFIER}'",
            name="subject_principal_shape",
        ),
        sa.CheckConstraint(
            f"record_id IS NULL OR record_id ~ '{IDENTIFIER}'", name="record_id_shape"
        ),
        sa.CheckConstraint(
            "(subject_principal IS NULL) <> (record_id IS NULL)", name="one_subject"
        ),
        sa.CheckConstraint(f"ent_hash ~ '{ENT_HASH}'", name="ent_hash_shape"),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        schema="ops",
    )
    op.create_index("ix_sensitive_read_at", "sensitive_read", ["at"], schema="ops")
    op.create_index(
        "ix_sensitive_read_subject_principal",
        "sensitive_read",
        ["subject_principal"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    op.execute(SENSITIVE_READ_TRIGGER_FUNCTION)
    op.execute(SENSITIVE_READ_TRIGGER)
    op.execute(BUDGET_TRIGGER_FUNCTION)
    op.execute(BUDGET_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER budget_version_is_audited ON ops.budget_version")
    op.execute("DROP FUNCTION ops.record_budget_version()")
    op.execute("DROP TRIGGER sensitive_read_is_audited ON ops.sensitive_read")
    op.execute("DROP FUNCTION ops.record_sensitive_read()")
    # The indexes, the policies and the grants go with the table.
    op.drop_table("sensitive_read", schema="ops")
