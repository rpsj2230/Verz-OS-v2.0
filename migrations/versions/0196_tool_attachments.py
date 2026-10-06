"""A tool or a connector is attached to an agent, or detached, and each reaches the ledger.

`brain.console.agent_tabs` decided that an attach is checked when it happens and that every add and
remove reaches the ledger with who, when and why; an agent's tools were its manifest's
`allowed_tools`, sealed in its install, so nothing could move one. `brain.tables.attachment` holds
the argument for each column and `brain.ops.attachment_store` is the one writer.

**`agent.tool_attachment`**: one row per press on a tool, naming the tool and which way. **SELECT
and INSERT only, written in the session's own name**, `0149`'s shape. Each row appends one
`compose_change` entry about the agent, in the same transaction, with the part, the reference, the
direction and the reason code, which is `AuditRecorder.compose_change`'s own shape (`0022` added the
action).

**A connector is never a row here, and its check says so.** A connector attached to an agent is a
name in `agent.agent.connectors`, which `0186` added and `brain.agents.binding.bound_capabilities`
compiles into the agent's ceiling; a press on one writes that column. A row here for a connector
would be a second store of the same fact, so `part` admits `tool` alone.

**A connector moved on the agent row reaches the ledger through the agent row's own trigger.**
`agent.record_agent_change` as `0190` leaves it (`0137`'s, with the channels branch) records the
lifecycle, the audience and the channels and, by `0137`'s own words, nothing that edits the
ceiling. It is replaced here with one more movement: on an update that
changes `connectors`, one `compose_change` entry per connector added or taken away, in the same
shape a tool press writes, with the part `connector`. Whoever writes the column is recorded, the
console's press and a builder publish and a statement at a prompt alike, which is the reason `0054`
gives for a trigger rather than a route appending. The reason code is the transaction's
`brain.reason_code` when the writer set one, and `agent_row_changed` when it did not, so a
statement nobody explained is still recorded and says so. Rejected: a second trigger on the row
for the column, which `0105` did for the steward, because the change is to what the agent may
reach and the agent's own trigger is where a reader of the ledger's `agent` subjects looks.

**The function is `0190`'s, built the way `0190` builds it, and changed in two places**: the
connectors' two declarations before the body and their branch before it returns. It is not a copy:
`0190` reads `0137`'s text and adds its branch, and this reads `0190` and adds its own, so neither
the channels branch nor anything `0137` argues can be lost between the two. Rejected: copying the
eighty lines of PL/pgSQL, which is what this migration did when `0137` was the last definition, and
which would have undone `0190`'s channels branch on any install applying both.

**The downgrade restores `0190`'s function exactly** (`AS_SHIPPED_BEFORE`, held equal to it by
`tests/unit/test_attachment_store.py`) and drops the table, its function and its trigger. The ledger
entries stay.

Written as 0160 over 0158 in #257, and replayed as 0196 over 0186, the head of main once #395
landed; whoever lands it later re-points `down_revision` and nothing else.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0196"
down_revision = "0195"
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
#: A connector is the agent row's own list, never a row here. Held equal to
#: `brain.tables.attachment.TOOL_ROWS_ONLY`.
PARTS = "part = 'tool'"
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

#: The append the trigger makes, copied from `0149`, which copied `0139`, `0121`, `0056` and `0003`.
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


def _channels_audit() -> ModuleType:
    """`0190`, read from beside this file, as `0190` reads `0137`."""
    path = Path(__file__).with_name("0190_agent_channels_audited.py")
    spec = importlib.util.spec_from_file_location("m0190_agent_channels_audited", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def as_0190_leaves_it() -> str:
    """`agent.record_agent_change` as `0190` leaves it: `0137`'s text with the channels branch.

    Built the way `0190` builds it, from `0137`'s text through `0190`'s own `replaced`, rather than
    copied, so the function this replaces and the one its downgrade puts back are `0190`'s by
    construction and cannot drift from it.
    """
    channels = _channels_audit()
    return str(channels.replaced(channels._lifecycle_audit().AGENT_TRIGGER_FUNCTION))


#: The function as `0190` leaves it, which the downgrade puts back.
AS_SHIPPED_BEFORE = as_0190_leaves_it()

#: The setting a writer names its reason in, and the code a write that named none is recorded with.
#: Held equal to `brain.ops.attachment_store` by `tests/unit/test_attachment_store.py`.
REASON_SETTING = "brain.reason_code"
UNEXPLAINED = "agent_row_changed"

#: The word beside an actor nobody named, as `0137` writes it. Held equal to
#: `brain.audit.record.INFERRED_ACTOR` by `tests/unit/test_attachment_store.py`.
INFERRED = "inferred"

#: The declarations the connectors branch needs, added to the function's own.
CONNECTOR_DECLARATIONS = """    v_connector text;
    v_direction text;
"""

#: One `compose_change` entry per connector added to or taken from the agent's list, in the shape a
#: tool press writes. Placed after every entry the function already appends, so an update moving the
#: lifecycle, the audience, the channels and the connectors writes them in that order.
CONNECTOR_BRANCH = (
    """    IF TG_OP = 'UPDATE' AND OLD.connectors IS DISTINCT FROM NEW.connectors THEN
        FOR v_connector, v_direction IN
            SELECT one, 'attached' FROM unnest(NEW.connectors) AS one
             WHERE NOT one = ANY(OLD.connectors)
            UNION ALL
            SELECT one, 'detached' FROM unnest(OLD.connectors) AS one
             WHERE NOT one = ANY(NEW.connectors)
            ORDER BY 2, 1
        LOOP
            v_details := jsonb_build_object(
                'part', 'connector',
                'reference', v_connector,
                'direction', v_direction,
                'reason_code', COALESCE(
                    NULLIF(current_setting('__REASON_SETTING__', true), ''), '__UNEXPLAINED__'
                )
            );
            IF v_inferred THEN
                v_details := v_details || jsonb_build_object('actor', '__INFERRED__');
            END IF;
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
                v_seq, v_at, v_actor, 'compose_change', v_subject, v_ent_hash,
                v_trace, v_details, v_prev
            );

            MERGE INTO obs.audit_entry AS t
            USING (SELECT v_seq AS seq) AS s
               ON t.seq = s.seq
            WHEN NOT MATCHED THEN
                INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                        details, prev_hash, entry_hash)
                VALUES (v_seq, v_at, v_actor, 'compose_change', v_subject,
                        v_ent_hash, v_trace, v_details, v_prev, v_entry);

            GET DIAGNOSTICS v_written = ROW_COUNT;
            IF v_written <> 1 THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'the ledger already holds seq ' || v_seq
                              || '; the audit entry was not appended',
                    ERRCODE = 'restrict_violation',
                    HINT = 'an append that is discarded silently is the failure this refuses';
            END IF;
        END LOOP;
    END IF;
""".replace("__REASON_SETTING__", REASON_SETTING)
    .replace("__UNEXPLAINED__", UNEXPLAINED)
    .replace("__INFERRED__", INFERRED)
)

#: Where each addition goes: the declarations before the body begins, the branch before it returns.
BEGINS = "BEGIN\n"
RETURNS = "    RETURN NULL;\nEND;"


def with_connectors(function: str) -> str:
    """`0190`'s function with the connectors branch, and nothing else changed."""
    assert function.count(BEGINS) == 1, "0190's function no longer has one BEGIN to declare before"
    assert function.count(RETURNS) == 1, "0190's function no longer has one RETURN to branch before"
    return function.replace(BEGINS, CONNECTOR_DECLARATIONS + BEGINS, 1).replace(
        RETURNS, CONNECTOR_BRANCH + RETURNS, 1
    )


#: `0190`'s function with one movement more: a connector added to or taken from the agent's list is
#: one `compose_change` entry each.
AGENT_TRIGGER_FUNCTION = with_connectors(AS_SHIPPED_BEFORE)

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
    op.execute(AGENT_TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(AS_SHIPPED_BEFORE)
    op.execute("DROP TRIGGER tool_attachment_is_audited ON agent.tool_attachment")
    op.execute("DROP FUNCTION agent.record_tool_attachment()")
    op.drop_table("tool_attachment", schema="agent")
