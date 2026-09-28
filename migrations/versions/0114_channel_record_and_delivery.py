"""Each channel is its own record on the install, and every delivery in or out is recorded.

**`ops.channel`: one row per channel (M10.6.3).** On or off, the tenant identifiers the channel
needs, and the vault slot its secret is kept in, which a check derives from the channel so a row
cannot point at another credential. `brain.tables.channel` argues the columns. **SELECT, INSERT
and UPDATE, and no DELETE**: a channel is switched off, never removed, so a delivery row always
names a channel the install can still say something about. `USING (true)` on each, because the one
reader and writer is `brain.channel_routes`, behind the channel authority.

**`ops.channel_delivery`: one row per delivery, and none of its content (M10.6.1).** Channel,
direction, outcome, a reason from a closed list and the vendor's status. **SELECT and INSERT, and no
UPDATE or DELETE**, for `0093`'s reason: what happened to a delivery is a fact once it is written,
and a later attempt is its own row.

**Every change to a channel's record is written to the audit ledger, from the database.** A
trigger on `ops.channel` appends a `setting` entry under `setting:channel.<channel>`, with the
actor the row's own `updated_by` names and the reach and trace the route set on the transaction
(`brain.tables.audit.attributed_to`), exactly as `0059`'s trigger records a row of `ops.setting`:
`set` when the tenant was written, `switched_on` or `switched_off` when the switch moved, and
nothing for a save that changed neither. The details are the change word alone, never the tenant
and never anything of the secret, whose replacement is recorded under `credential` by `0054`'s
trigger on `ops.credential_write`. `setting` rather than a new member: the action list and the
subject grammar are superseded by whichever migration lands last, and a channel's switch is a
switch, which `brain.audit.record.SettingChange` already has the words for. See
`brain.audit.record.AuditRecorder.setting`, which the trigger is held to.

**The append is `0003`'s, one more copy of that block**, for the reason `0047` gives against
editing a function every grant in production goes through.

**The downgrade** drops the trigger, its function and both tables, which forgets every channel's
record (each channel then refuses to receive or send, which is the behaviour before this release:
nothing received) and every delivery row. The ledger keeps every entry already appended. Nothing
else refers to either table.

Task ids: M10.6.1, M10.6.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0114"
# The head of origin/main when this was written (028fe36c); 0114 is the number the Wave 2 plan
# holds for the channel pipeline, re-pointed at landing if another lands first.
down_revision = "0108"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.channel", "ops.channel_delivery")

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.channel` by `tests/unit/test_channel_pipeline.py`.
CHANNELS = (
    "channel IN ('api', 'console', 'email', 'lark', 'scheduler', 'slack', 'teams', 'telegram', "
    "'webhook', 'whatsapp', 'widget')"
)
SLOT_IS_DERIVED = "secret_path = 'providers/channel_' || channel"
BORROWED_BY_THE_APPLICATION = "secret_role = 'application'"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
DIRECTIONS = "direction IN ('inbound', 'outbound')"
OUTCOME_FITS_DIRECTION = (
    "(direction = 'inbound' AND outcome IN ('accepted', 'redelivered', 'refused')) OR "
    "(direction = 'outbound' AND outcome IN ('refused', 'sent', 'unknown'))"
)
REASONS = (
    "reason IS NULL OR reason IN ('bad_signature', 'cannot_carry', 'incomplete', "
    "'no_secret', 'not_answerable', 'not_configured', 'reach_changed', 'switched_off', "
    "'too_large', 'unreadable', 'unsafe_address', 'vault_unavailable', 'vendor_refused', "
    "'vendor_unavailable')"
)
REASON_WHEN_NOT_DELIVERED = "(outcome IN ('refused', 'unknown')) = (reason IS NOT NULL)"
VENDOR_STATUS = "vendor_status IS NULL OR vendor_status BETWEEN 100 AND 599"
CHANNEL_CHARS = 16
SECRET_PATH_CHARS = 34
WORD_CHARS = 24
PRINCIPAL_ID_CHARS = 128

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON ops.channel TO brain_app",
    "GRANT SELECT, INSERT ON ops.channel_delivery TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.channel ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY channel_readable ON ops.channel
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY channel_configurable ON ops.channel
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY channel_switchable ON ops.channel
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.channel_delivery ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY channel_delivery_readable ON ops.channel_delivery
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY channel_delivery_appendable ON ops.channel_delivery
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: The words the trigger appends: `brain.audit.record.SettingChange`'s, less `retired`, because a
#: channel is switched off and never retired.
CHANNEL_TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_channel_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'setting:channel.' || NEW.channel;
    v_changes text[] := ARRAY[]::text[];
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' OR OLD.tenant IS DISTINCT FROM NEW.tenant THEN
        v_changes := v_changes || 'set'::text;
    END IF;
    IF TG_OP = 'INSERT' OR OLD.enabled IS DISTINCT FROM NEW.enabled THEN
        IF NEW.enabled THEN
            v_changes := v_changes || 'switched_on'::text;
        ELSE
            v_changes := v_changes || 'switched_off'::text;
        END IF;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);
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
            v_seq, v_at, NEW.updated_by, 'setting', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, NEW.updated_by, 'setting', v_subject,
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
    RETURN NULL;
END;
$$
"""

CHANNEL_TRIGGER = """
CREATE TRIGGER channel_is_audited
    AFTER INSERT OR UPDATE ON ops.channel
    FOR EACH ROW EXECUTE FUNCTION ops.record_channel_change()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert "UPDATE" not in GRANTS[1]

    op.create_table(
        "channel",
        sa.Column("channel", sa.String(CHANNEL_CHARS), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tenant", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("secret_path", sa.String(SECRET_PATH_CHARS), nullable=False),
        sa.Column("secret_role", sa.String(32), nullable=False),
        sa.Column("updated_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint("jsonb_typeof(tenant) = 'object'", name="tenant_is_an_object"),
        sa.CheckConstraint(SLOT_IS_DERIVED, name="secret_path_is_derived"),
        sa.CheckConstraint(BORROWED_BY_THE_APPLICATION, name="secret_role"),
        sa.CheckConstraint(f"updated_by ~ '{IDENTIFIER}'", name="updated_by_shape"),
        sa.PrimaryKeyConstraint("channel"),
        schema="ops",
    )
    op.create_table(
        "channel_delivery",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(CHANNEL_CHARS), nullable=False),
        sa.Column("direction", sa.String(WORD_CHARS), nullable=False),
        sa.Column("outcome", sa.String(WORD_CHARS), nullable=False),
        sa.Column("reason", sa.String(WORD_CHARS), nullable=True),
        sa.Column("vendor_status", sa.SmallInteger(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint(DIRECTIONS, name="direction"),
        sa.CheckConstraint(OUTCOME_FITS_DIRECTION, name="outcome_fits_direction"),
        sa.CheckConstraint(REASONS, name="reason_known"),
        sa.CheckConstraint(REASON_WHEN_NOT_DELIVERED, name="reason_when_not_delivered"),
        sa.CheckConstraint(VENDOR_STATUS, name="vendor_status"),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index(
        "ix_channel_delivery_channel_recorded_at",
        "channel_delivery",
        ["channel", "recorded_at"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    op.execute(CHANNEL_TRIGGER_FUNCTION)
    op.execute(CHANNEL_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER channel_is_audited ON ops.channel")
    op.execute("DROP FUNCTION ops.record_channel_change()")
    # The index, the policies and the grants go with the tables.
    op.drop_table("channel_delivery", schema="ops")
    op.drop_table("channel", schema="ops")
