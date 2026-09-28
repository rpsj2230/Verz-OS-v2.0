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

**The downgrade** drops both tables, which forgets every channel's record (each channel then
refuses to receive or send, which is the behaviour before this release: nothing received) and every
delivery row. Nothing else refers to either table.

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


def downgrade() -> None:
    # The index, the policies and the grants go with the tables.
    op.drop_table("channel_delivery", schema="ops")
    op.drop_table("channel", schema="ops")
