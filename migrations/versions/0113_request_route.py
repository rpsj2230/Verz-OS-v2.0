"""The request row records the whole routing decision: why the lane, and where the model call went.

**`obs.request_telemetry` gains three nullable columns** (M3.6.3). `lane_basis` is the rule of
`brain.gate.classify.classify_lane` that chose `routed_lane`, which 0100 wrote without its reason.
`routed_tier` and `tier_basis` are the tier `brain.models.calls.ModelCalls.complete` classified the
request's model call into and the step of `classify_tier` that settled it, noted on the request's
meter as it was decided. Until now the executor's decision was dropped once walked, so a row said
which model answered and never where the request was sent or why.

**Names with checks, never sentences.** Each decision carries a sentence as well, and the ledger
holds names only, so the codes are what is written and each check is its enum's member list, held
equal to the model's by `tests/unit/test_tables.py`. Nullable, because every row written before
this migration has none, and so does every request the front half or the executor did not decide
for. Adding a nullable column rewrites nothing and every existing row satisfies each check.

**No new table**, so no row-level security to enable: the grants and policies 0039 put on the
ledger cover the new columns as they cover the rest.

**The downgrade** drops the three columns, each check with its column, and narrows nothing else.

Task ids: M3.6.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0113"
# The head of origin/main when this was written (2519150). Nothing after 0100 alters
# `obs.request_telemetry`.
down_revision = "0108"
branch_labels = None
depends_on = None

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.telemetry` by `tests/unit/test_tables.py`.
LANE_BASIS = (
    "lane_basis IS NULL OR lane_basis IN "
    "('default', 'exact_intent', 'fast_refused', 'long_question', 'requested', 'task_phrase')"
)
ROUTED_TIER = "routed_tier IS NULL OR routed_tier IN ('heavy', 'main', 'none', 'small')"
TIER_BASIS = (
    "tier_basis IS NULL OR tier_basis IN "
    "('context', 'default', 'fast_lane', 'pinned', 'residency_floor', 'task_lane', 'tool_floor')"
)

#: The widths, each holding its enum's longest member, held to the model by the same test.
BASIS_CHARS = 16
TIER_CHARS = 8

#: Every column this adds, in the order it adds them; the downgrade drops them in reverse.
COLUMNS: tuple[str, ...] = ("lane_basis", "routed_tier", "tier_basis")


def upgrade() -> None:
    # Each check travels with the column it reads, under the naming convention; see `0093`.
    op.add_column(
        "request_telemetry",
        sa.Column(
            "lane_basis",
            sa.String(BASIS_CHARS),
            sa.CheckConstraint(LANE_BASIS, name="lane_basis"),
            nullable=True,
        ),
        schema="obs",
    )
    op.add_column(
        "request_telemetry",
        sa.Column(
            "routed_tier",
            sa.String(TIER_CHARS),
            sa.CheckConstraint(ROUTED_TIER, name="routed_tier"),
            nullable=True,
        ),
        schema="obs",
    )
    op.add_column(
        "request_telemetry",
        sa.Column(
            "tier_basis",
            sa.String(BASIS_CHARS),
            sa.CheckConstraint(TIER_BASIS, name="tier_basis"),
            nullable=True,
        ),
        schema="obs",
    )


def downgrade() -> None:
    # Each column's check goes with it.
    for column in reversed(COLUMNS):
        op.drop_column("request_telemetry", column, schema="obs")
