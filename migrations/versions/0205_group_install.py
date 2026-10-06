"""The conversations the bot is in, and an agent installed into one of them, on the ledger.

`brain.console.agent_tabs` decided what a group install is and refused one on a surface that does
not declare `Feature.GROUP_INSTALL`; `brain.tables.group_install` holds the argument for each column.

**`ops.channel_room`: what the vendor said.** A row per conversation the bot was added to, written
when the vendor's event arrives and closed when the bot is removed. SELECT, INSERT and UPDATE for the
application, which writes it from a verified event and from nothing a person sends. Not ledgered,
because the bot being in a conversation changes nobody's access.

**`agent.group_install`: who installed which agent where.** SELECT and INSERT, and UPDATE of the two
removal columns alone, so an install is never rewritten into a different one: a move is a removal
and an install. The insert policy admits only an install in the session's own name and the update
policy only a removal in it. **Its trigger writes `AuditRecorder.compose_change`'s entry** for an
install and for a removal, in the same transaction, with the part `group`, the room's reference and
the direction, by the person named on the row. The append is `0003`'s block once more, for the
reason `0047` gives against editing a function every grant goes through.

**The downgrade drops both.** An install's entries stay on the ledger.

Task ids: M39.2.4.4

Revision ID: 0205
Revises: 0207
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0205"
down_revision = "0204"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. A room points at nothing; an install at nothing either: the
#: agent and the people are values.
TABLES: tuple[str, ...] = ("ops.channel_room", "agent.group_install")

APP_ROLE = "brain_app"
PRINCIPAL = "current_setting('app.principal_id', true)"

#: Copied for `0009`'s reason and held equal to `brain.tables.group_install` by
#: `tests/unit/test_group_install.py`.
AGENT_ID_CHARS = 128
CHANNEL_CHARS = 16
ROOM_REF_CHARS = 128
ROOM_NAME_CHARS = 200
PRINCIPAL_ID_CHARS = 128
ROOM_REF_PATTERN = r"^[A-Za-z0-9_.@-]{1,128}$"
CHANNELS = (
    "channel IN ('api', 'console', 'email', 'lark', 'scheduler', 'slack', 'teams', 'telegram', "
    "'webhook', 'whatsapp', 'widget')"
)
#: The part a group install is recorded under in a `compose_change` entry, and the reason code.
PART = "group"
REASON = "group_install"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.channel_room ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY channel_room_readable ON ops.channel_room
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY channel_room_noted ON ops.channel_room
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY channel_room_moved ON ops.channel_room
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
    "ALTER TABLE agent.group_install ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY group_install_readable ON agent.group_install
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY group_install_made_in_the_sessions_name ON agent.group_install
        FOR INSERT TO brain_app
        WITH CHECK (installed_by = {PRINCIPAL} AND removed_at IS NULL)
    """,
    f"""
    CREATE POLICY group_install_removed_in_the_sessions_name ON agent.group_install
        FOR UPDATE TO brain_app
        USING (removed_at IS NULL)
        WITH CHECK (removed_by = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON ops.channel_room TO brain_app",
    "GRANT SELECT, INSERT ON agent.group_install TO brain_app",
    "GRANT UPDATE (removed_by, removed_at) ON agent.group_install TO brain_app",
)

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
            v_seq, v_at, v_actor, 'compose_change', 'agent:' || NEW.agent_id, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, 'compose_change', 'agent:' || NEW.agent_id,
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

#: One `compose_change` entry per install and per removal, by the person the row names.
INSTALL_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_group_install() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_details jsonb;
    v_actor text;
    v_direction text;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_actor := NEW.installed_by;
        v_direction := 'attached';
    ELSIF OLD.removed_at IS NULL AND NEW.removed_at IS NOT NULL THEN
        v_actor := NEW.removed_by;
        v_direction := 'detached';
    ELSE
        RETURN NULL;
    END IF;
    v_details := jsonb_build_object(
        'part', '"""
    + PART
    + """',
        'reference', NEW.room_ref,
        'direction', v_direction,
        'reason_code', '"""
    + REASON
    + """'
    );"""
    + _APPEND
    + """    RETURN NULL;
END;
$$
"""
)

INSTALL_TRIGGER = """
CREATE TRIGGER group_install_is_audited
    AFTER INSERT OR UPDATE ON agent.group_install
    FOR EACH ROW EXECUTE FUNCTION agent.record_group_install()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.create_table(
        "channel_room",
        sa.Column("channel", sa.String(CHANNEL_CHARS), nullable=False),
        sa.Column("room_ref", sa.String(ROOM_REF_CHARS), nullable=False),
        sa.Column("name", sa.String(ROOM_NAME_CHARS), server_default=sa.text("''"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("channel", "room_ref"),
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint(f"room_ref ~ '{ROOM_REF_PATTERN}'", name="room_ref_shape"),
        schema="ops",
    )
    op.create_table(
        "group_install",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("channel", sa.String(CHANNEL_CHARS), nullable=False),
        sa.Column("room_ref", sa.String(ROOM_REF_CHARS), nullable=False),
        sa.Column("installed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("removed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint(f"room_ref ~ '{ROOM_REF_PATTERN}'", name="room_ref_shape"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="names_an_agent"),
        sa.CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_names_who_and_when"
        ),
        schema="agent",
    )
    op.create_index(
        "uq_group_install_one_agent_per_room",
        "group_install",
        ["channel", "room_ref"],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index("ix_group_install_agent_id", "group_install", ["agent_id"], schema="agent")
    for statement in RLS + GRANTS:
        op.execute(statement)
    op.execute(INSTALL_TRIGGER_FUNCTION)
    op.execute(INSTALL_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent.group_install")
    op.execute("DROP FUNCTION IF EXISTS agent.record_group_install()")
    op.execute("DROP TABLE IF EXISTS ops.channel_room")
