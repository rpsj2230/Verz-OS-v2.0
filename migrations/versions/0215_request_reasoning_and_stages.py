"""The request row records what a model spent reasoning and where the request's time went.

**`obs.request_telemetry` gains two nullable columns** (M27.15.6). `reasoning_tokens` is the part
of `tokens_out` a reasoning model spent thinking, as the provider counted it. It is **a part of
the output count and never an addition to it**: providers that report it count it inside the
completion tokens, so a usage screen that summed the two would double-count. It is kept as its own
column because a reasoning model's cost is mostly the part nobody reads, and one output figure
cannot tell a long answer from a long think. `stage_ms` is the milliseconds the request spent in
each gate step it entered, keyed by the step's lower-case name (`record`, `identify`, `entitle`,
and so on), from the recorder's own clock. A step the request never entered is absent from the
object rather than zero in it.

**A check on the shape, none on the keys.** The column must be a JSON object when it is present.
The keys are `brain.gate.context.GateStep`'s names and the model refuses any other before a row is
built (`brain.ops.telemetry.RequestTelemetry`); repeating the list in a constraint would be a
second copy that has to be changed whenever the gate gains a step, and a step the check did not yet
know would refuse the whole row and lose the request's record with it.

Nullable, because every row written before this migration has neither, and so does every request
whose recorder had no clock or that called no model. Adding a nullable column rewrites nothing.

**No new table**, so no row-level security to enable: the grants and policies 0039 put on the
ledger cover the new columns as they cover the rest. The table is partitioned and a column added
to the parent reaches every partition.

**The downgrade** drops both columns, each check with its column.

Task ids: M27.15.6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0215"
# Linked into the chain by the coordinator's migration train (0213, 0214, then this).
down_revision = "0214"
branch_labels = None
depends_on = None

#: Held equal to `brain.tables.telemetry` by `tests/unit/test_tables.py`.
STAGE_MS_OBJECT = "stage_ms IS NULL OR jsonb_typeof(stage_ms) = 'object'"
REASONING_NOT_NEGATIVE = "reasoning_tokens IS NULL OR reasoning_tokens >= 0"


def upgrade() -> None:
    # Each check travels with the column it reads, under the naming convention; see `0093`.
    op.add_column(
        "request_telemetry",
        sa.Column(
            "reasoning_tokens",
            sa.Integer(),
            sa.CheckConstraint(REASONING_NOT_NEGATIVE, name="reasoning_tokens_not_negative"),
            nullable=True,
        ),
        schema="obs",
    )
    op.add_column(
        "request_telemetry",
        sa.Column(
            "stage_ms",
            postgresql.JSONB(),
            sa.CheckConstraint(STAGE_MS_OBJECT, name="stage_ms_object"),
            nullable=True,
        ),
        schema="obs",
    )


def downgrade() -> None:
    op.drop_column("request_telemetry", "stage_ms", schema="obs")
    op.drop_column("request_telemetry", "reasoning_tokens", schema="obs")
