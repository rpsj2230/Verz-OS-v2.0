"""The request row records what the gate's front half decided, and a redelivered message is refused.

Two schema changes, both for the gate's front half.

**`obs.request_telemetry` gains four nullable columns** (M3.4.2, M3.6.3): `risk_score`, the
injection score of the question (0 to 100); `routed_lane`, the lane `classify_lane` chose;
`selection_stage` and `selected_agent`, which stage of `select_agent` chose which agent. Written by
`brain.ops.telemetry.request_telemetry_of` from `brain.gate.finish.FrontRecord`, which is built from
the decisions themselves, so the row carries the route that was taken rather than one re-derived.
Nullable because every row written before this migration, and every request that does not pass
through the front half, has none. Adding a nullable column rewrites nothing, and the checks are
satisfied by every existing row, which holds NULL in all four.

**`gate.channel_event` is new** (M3.2.2): the dedupe key `brain.gate.ingress.ChannelEvent` has
always had, as a primary key on `(channel, external_id)`, so a redelivered message is refused by
the unique index. No sender and no text, for the reason `brain.tables.channel_event` gives.
**SELECT and INSERT, and no UPDATE or DELETE**: a claim is never edited, and the insert's
`RETURNING` needs the read. **`USING (true)`**: the only reader is that insert.

**The downgrade** drops the table, which forgets every claim (a message redelivered afterwards is
answered again, which is the behaviour before this release), and the four columns with their checks.
No check is re-created, so nothing is narrowed on rows already written.

Task ids: M3.2.2, M3.4.2, M3.6.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0100"
# The head of origin/main when this was written (e6fde3a). Nothing after 0039 alters
# `obs.request_telemetry`, and nothing builds a table in `gate` that this one names.
down_revision = "0097"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.channel_event",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.telemetry` and `brain.tables.channel_event` by `tests/unit/test_tables.py`.
RISK_SCORE_RANGE = "risk_score IS NULL OR risk_score BETWEEN 0 AND 100"
ROUTED_LANE = "routed_lane IS NULL OR routed_lane IN ('answer', 'fast', 'task')"
SELECTION_STAGE = (
    "selection_stage IS NULL OR "
    "selection_stage IN ('addressed', 'binding', 'classifier', 'default', 'rule')"
)
CHANNELS = (
    "channel IN ('api', 'console', 'email', 'lark', 'scheduler', 'slack', 'teams', 'telegram', "
    "'webhook', 'whatsapp', 'widget')"
)
NAME_CHARS = 120
EXTERNAL_ID_CHARS = 255

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON gate.channel_event TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.channel_event ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY channel_event_readable ON gate.channel_event
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY channel_event_claimable ON gate.channel_event
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Each check travels with the column it reads, under the naming convention; see `0093`.
    op.add_column(
        "request_telemetry",
        sa.Column(
            "risk_score",
            sa.SmallInteger(),
            sa.CheckConstraint(RISK_SCORE_RANGE, name="risk_score_range"),
            nullable=True,
        ),
        schema="obs",
    )
    op.add_column(
        "request_telemetry",
        sa.Column(
            "routed_lane",
            sa.String(8),
            sa.CheckConstraint(ROUTED_LANE, name="routed_lane"),
            nullable=True,
        ),
        schema="obs",
    )
    op.add_column(
        "request_telemetry",
        sa.Column(
            "selection_stage",
            sa.String(16),
            sa.CheckConstraint(SELECTION_STAGE, name="selection_stage"),
            nullable=True,
        ),
        schema="obs",
    )
    op.add_column(
        "request_telemetry",
        sa.Column("selected_agent", sa.String(NAME_CHARS), nullable=True),
        schema="obs",
    )

    op.create_table(
        "channel_event",
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(EXTERNAL_ID_CHARS), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(CHANNELS, name="channel"),
        sa.CheckConstraint("length(btrim(external_id)) >= 1", name="external_id_present"),
        sa.PrimaryKeyConstraint("channel", "external_id"),
        schema="gate",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("channel_event", schema="gate")
    # Each column's check goes with it.
    for column in ("selected_agent", "selection_stage", "routed_lane", "risk_score"):
        op.drop_column("request_telemetry", column, schema="obs")
