"""A recorded cost can name the request it paid for, by trace id, with row-level security unchanged.

`docs/needs-rupash.md` item 59 was answered Option B: link each spend row to its trace and read
the question's shape from the trace ledger, rather than copying fan-out or tool count onto the
spend row. `brain.tables.spend` holds the argument for the column; what is here is the column
and the index the join reads.

**Nullable, with no check constraint, and this is the first half of a two-release change.** A
deploy runs the new schema against the previous release's code for the length of the swap, and
that release's INSERT names no trace id. A NOT NULL column with no default refuses that insert,
and a check constraint added to a table that already exists narrows what it accepts, so
`brain.deployment.compatibility` reports both as breaking. It was written that way first and the
gate refused it, correctly. Nothing has ever written a cost, so in fact nothing would have
broken, and that is exactly the argument the compatibility module refuses to take from a file:
it has no per-migration escape hatch, and its answer to a column that must become required is
the two-release change. See `REQUIRED_IN_A_LATER_RELEASE`.

**Required where a cost is made, meanwhile.** `brain.ops.spend.Actual` refuses a cost without a
trace id in the audit ledger's grammar, and `brain.ops.spend_store` writes only an `Actual`, so
every row this release writes carries one. A row with none can only come from a writer that
went round `Actual`, and `brain.ops.spend_store.actual_from` refuses to read it back rather than
report a cost under a trace nobody recorded.

**Nothing about row-level security changes, and nothing needs to.** The policies `0034` created
are table policies, and a column added to the table is governed by them without a statement
here. The grant is `SELECT, INSERT ON ops.spend_actual`, which covers every column. The read
stays `USING (true)` for the reason `0034` gives, and `0035`'s argument that the materialised
view is no wider than its table is untouched, because the view selects named columns and this
one is not among them.

The downgrade drops the column and its index, and discards every trace link recorded since.

Task ids: M21.3.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. This one
#: adds a column and no table.
TABLES: tuple[str, ...] = ()

#: The width of a trace id, as `brain.tables.adoption.TRACE_ID_CHARS` and `brain.db` size it.
TRACE_ID_CHARS = 64

#: What the second release of this change does, said where the next migration author looks.
REQUIRED_IN_A_LATER_RELEASE = (
    "Once no release that writes a cost without a trace id can still be serving, a later "
    "migration sets ops.spend_actual.trace_id NOT NULL and adds a check that it is not blank. "
    "Done here, both are refused by brain.deployment.compatibility, because the release "
    "before this one inserts without the column."
)


def upgrade() -> None:
    op.add_column(
        "spend_actual",
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=True),
        schema="ops",
    )
    op.create_index("ix_spend_actual_trace_id", "spend_actual", ["trace_id"], schema="ops")


def downgrade() -> None:
    # The index goes with the column.
    op.drop_column("spend_actual", "trace_id", schema="ops")
