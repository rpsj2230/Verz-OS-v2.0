"""A tool or a connector is attached to an agent, or detached, and each reaches the ledger.

`brain.console.agent_tabs` decided that an attach is checked when it happens and that every add and
remove reaches the ledger with who, when and why; an agent's tools were its manifest's
`allowed_tools`, sealed in its install, so nothing could move one. `brain.tables.attachment` holds
the argument for each column and `brain.ops.attachment_store` is the one writer.

**`agent.tool_attachment`**: one row per press, naming what was pressed on (a tool, or a connector's
every tool) and the tool names it moved. **SELECT and INSERT only, written in the session's own
name**, `0149`'s shape.

**Each row appends one `compose_change` entry about the agent**, in the same transaction, with the
part, the reference, the direction and the reason code, which is `AuditRecorder.compose_change`'s
own shape (`0022` added the action). Never the tool list beyond the reference: the row holds it.

**The downgrade drops the table, the function and the trigger**, and the ledger entries stay.

Written over 0158, the newest migration on the branch it stacks on; whoever lands it re-points
`down_revision` to main's head then and nothing else.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0160"
down_revision = "0158"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.tool_attachment",)

APP_ROLE = "brain_app"

#: Widths and vocabularies copied for the reason `0009` gives, and held equal to
#: `brain.tables.attachment` by `tests/unit/test_attachment_store.py`.
AGENT_ID_CHARS = 128
REFERENCE_CHARS = 80
PART_CHARS = 16
TRACE_ID_CHARS = 128
REASON_CHARS = 64
PRINCIPAL_ID_CHARS = 128
ENT_HASH_PATTERN = r"^[0-9a-f]{32}$"
REASON_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
PARTS = "part IN ('connector', 'tool')"
A_TOOL_MOVES_ITSELF = "part <> 'tool' OR tools = ARRAY[reference]::text[]"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.tool_attachment ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY tool_attachment_readable ON agent.tool_attachment
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY tool_attachment_made_in_the_sessions_name ON agent.tool_attachment
        FOR INSERT TO brain_app
        WITH CHECK (changed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: an attach and a detach are new rows.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.tool_attachment TO brain_app",)

#: The append the trigger makes, copied from `0158`, which copied `0149`, `0139`, `0121`, `0056`
#: and `0003`.
_APPEND = """
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
            v_seq, v_at, {actor}, '{action}', {subject}, v_ent_hash,
            v_trace, {details}, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, {actor}, '{action}', {subject},
                    v_ent_hash, v_trace, {details}, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
"""

_DECLARE = """
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

#: One `compose_change` entry about the agent per press, in `AuditRecorder.compose_change`'s shape.
ATTACHMENT_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_tool_attachment() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    v_details := jsonb_build_object(
        'part', NEW.part,
        'reference', NEW.reference,
        'direction', CASE WHEN NEW.attached THEN 'attached' ELSE 'detached' END,
        'reason_code', NEW.reason_code
    );"""
    + _APPEND.format(
        actor="NEW.changed_by",
        action="compose_change",
        subject="'agent:' || NEW.agent_id",
        details="v_details",
    )
    + """    RETURN NULL;
END;
$$
"""
)

ATTACHMENT_TRIGGER = """
    CREATE TRIGGER tool_attachment_is_audited
        AFTER INSERT ON agent.tool_attachment
        FOR EACH ROW EXECUTE FUNCTION agent.record_tool_attachment()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "tool_attachment",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("part", sa.String(PART_CHARS), nullable=False),
        sa.Column("reference", sa.String(REFERENCE_CHARS), nullable=False),
        sa.Column("attached", sa.Boolean(), nullable=False),
        sa.Column("tools", ARRAY(sa.Text()), nullable=False),
        sa.Column("changed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason_code", sa.String(REASON_CHARS), nullable=False),
        sa.Column("entitlement_hash", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(PARTS, name="part"),
        sa.CheckConstraint("length(btrim(reference)) > 0", name="names_what"),
        sa.CheckConstraint("cardinality(tools) > 0", name="moves_a_tool"),
        sa.CheckConstraint(A_TOOL_MOVES_ITSELF, name="a_tool_moves_itself"),
        sa.CheckConstraint(f"reason_code ~ '{REASON_PATTERN}'", name="reason_is_a_code"),
        sa.CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        schema="agent",
    )
    op.create_index(
        "ix_tool_attachment_agent_changed",
        "tool_attachment",
        ["agent_id", "changed_at"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(ATTACHMENT_TRIGGER_FUNCTION)
    op.execute(ATTACHMENT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER tool_attachment_is_audited ON agent.tool_attachment")
    op.execute("DROP FUNCTION agent.record_tool_attachment()")
    op.drop_table("tool_attachment", schema="agent")
