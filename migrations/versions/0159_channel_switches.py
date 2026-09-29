"""An agent answers only on the channels switched on for it, and the web page is switched on for
every agent that already existed.

An agent answers only on the channels an administrator switched on for it, never on every channel
by default (`docs/requirements/register.json` OWN-7, ARC-A-171, OWN-56). Nothing stored a switch,
so every stored agent answered wherever it could be addressed. `brain.tables.channel_switch` holds
the argument for each column and `brain.ops.channel_switch_store` is the one writer after this.

**`agent.channel_switch`**: one row per press, the newest per agent and channel deciding.
**SELECT and INSERT only, written in the session's own name**, `0149`'s shape. Each row appends one
`compose_change` entry about the agent (part `channels`, the channel, on or off, and the reason),
`AuditRecorder.compose_change`'s shape.

**Nothing that answers today stops answering, and that is `0159b`'s half.** The rows switching on
every channel an existing agent could be reached on are data, and `brain.ops.migration_policy`
keeps a schema change and a data change in separate migrations, so this one builds the table, its
trigger and the act column, and `0159b`, which follows it, writes them.

**A publish that waits for a second person carries the web choice on its request.** One column on
`agent.manifest_act`, `on_the_web`, true for every act taken before it, because every agent made
then answered on the page. Without it the author's untick would be lost between the request and
the approval that makes the agent, and the approver's publish would switch the page on regardless.

**The downgrade drops the table, the function, the trigger and the column**, and the ledger entries
stay.

Written over 0160, the newest migration on the branch it stacks on; whoever lands it re-points
`down_revision` to main's head then and nothing else.

Task ids: M39.2.4.1, M39.2.4.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0159"
down_revision = "0160"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.channel_switch",)

APP_ROLE = "brain_app"

#: Widths and vocabularies copied for the reason `0009` gives, and held equal to
#: `brain.tables.channel_switch` by `tests/unit/test_channel_switch_store.py`.
AGENT_ID_CHARS = 128
CHANNEL_CHARS = 32
TRACE_ID_CHARS = 128
REASON_CHARS = 64
PRINCIPAL_ID_CHARS = 128
ENT_HASH_PATTERN = r"^[0-9a-f]{32}$"
REASON_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
CHANNELS = (
    "channel IN ('api', 'console', 'email', 'lark', 'scheduler', 'slack', 'teams', 'telegram', "
    "'webhook', 'whatsapp', 'widget')"
)

#: `0149`'s CREATE TABLE for the acts as it would read today, for the comparison with the model.
#: Held to the ALTER the upgrade emits by `tests/unit/test_channel_switch_store.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, CONSTRAINT pk_manifest_act PRIMARY KEY": (
        "at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, "
        "on_the_web BOOLEAN DEFAULT true NOT NULL, CONSTRAINT pk_manifest_act PRIMARY KEY"
    ),
}

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.channel_switch ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY channel_switch_readable ON agent.channel_switch
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY channel_switch_made_in_the_sessions_name ON agent.channel_switch
        FOR INSERT TO brain_app
        WITH CHECK (changed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a switch is a new row.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.channel_switch TO brain_app",)

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

#: One `compose_change` entry about the agent per switch, in `AuditRecorder.compose_change`'s shape.
SWITCH_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_channel_switch() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    v_details := jsonb_build_object(
        'part', 'channels',
        'reference', NEW.channel,
        'direction', CASE WHEN NEW.switched_on THEN 'attached' ELSE 'detached' END,
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

SWITCH_TRIGGER = """
    CREATE TRIGGER channel_switch_is_audited
        AFTER INSERT ON agent.channel_switch
        FOR EACH ROW EXECUTE FUNCTION agent.record_channel_switch()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "channel_switch",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("channel", sa.String(CHANNEL_CHARS), nullable=False),
        sa.Column("switched_on", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint(f"reason_code ~ '{REASON_PATTERN}'", name="reason_is_a_code"),
        sa.CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        schema="agent",
    )
    op.create_index(
        "ix_channel_switch_agent_changed",
        "channel_switch",
        ["agent_id", "changed_at"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(SWITCH_TRIGGER_FUNCTION)
    op.execute(SWITCH_TRIGGER)
    op.add_column(
        "manifest_act",
        sa.Column("on_the_web", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema="agent",
    )


def downgrade() -> None:
    op.drop_column("manifest_act", "on_the_web", schema="agent")
    op.execute("DROP TRIGGER channel_switch_is_audited ON agent.channel_switch")
    op.execute("DROP FUNCTION agent.record_channel_switch()")
    op.drop_table("channel_switch", schema="agent")
