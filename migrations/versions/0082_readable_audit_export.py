"""An export of the audit entries a reader may read can be recorded, without a window or a verdict.

`0053` built `ops.data_export` for one shape of export: a contiguous run of the chain, whose record
names its first and last sequence numbers and says whether it verified. Two of its constraints hold
that shape, `a_window_names_both_ends_or_neither` and `the_window_is_contiguous`, and both are right
about a chain. An export of the entries one reader may read (`brain.audit.readable_export`) is not
a chain, and neither constraint can record it truthfully: with a sequence range beside its count,
the range less the count is how many entries were withheld from that reader, on a record shown back
to them and on the Exports log; without one, `a_window_names_both_ends_or_neither` refuses any count
above zero. See `brain.tables.data_export.A_READABLE_EXPORT_NAMES_NO_WINDOW`.

**A form column, and the window constraints say they describe the chain.** `form` is `chain` or
`readable`, and a row written before this migration is a chain, which is the server default: every
existing row already satisfies the chain's constraints, so nothing is rewritten and no statement
here changes data. The two constraints are dropped and recreated with `form <> 'chain' OR` in
front of what they said, so a chain is held exactly as before and a non-contiguous chain is still
refused. Two constraints are added for the new form: a readable export names no sequence number,
and only a chain carries a verdict, which is why `verified` stops being NOT NULL. A readable record
with `verified = false` would read as a tampered ledger.

Rejected: a second table for readable exports. The Exports log, the reader's own listing and the
ledger trigger all read one table, and two would mean two queries behind one decision about who may
be told that an export happened, with the trigger copied a sixth time.

Rejected: recording a readable export with the raw window's range and count, or with zero entries.
Either makes the record describe something other than what left, and the record is the only thing
that matches a copy found later to the person who took it.

**Nothing about access changes.** No table, no policy, no grant. `0053`'s SELECT and INSERT for
`brain_app` are table grants and cover the new column; its `USING (true)` policy is unchanged for
the reason `0053` gives. The trigger that appends the ledger entry reads no column this touches.

**The downgrade refuses on an install that has taken a readable export**, and that is the right
restriction: `0053`'s constraints cannot hold such a record, and a downgrade that deleted it would
be the one migration here that removes the record of something leaving the building. The old
constraints are recreated `NOT VALID`, for
`brain.ops.migration_policy.A_DOWNGRADE_NARROWS_WHAT_IS_WRITTEN_NEXT_AND_NOT_WHAT_WAS_WRITTEN_BEFORE`,
so they hold every write after the downgrade and judge no row already written. What meets a
readable record is `verified` becoming NOT NULL again, because such a record has no verdict, so the
downgrade fails there and, the DDL being one transaction, changes nothing.

Task ids: M27.9.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0082"
down_revision = "0069"
branch_labels = None
depends_on = None

#: `brain.tables.data_export.FORM_CHARS`, copied for the reason `0009` gives about live code.
FORM_CHARS = 16

#: `brain.tables.data_export.ExportForm`, sorted as `one_of` sorts.
FORM_IN = "form IN ('chain', 'readable')"

#: `0053`'s two window constraints, as it wrote them. The downgrade puts these back.
BOTH_ENDS_OR_NEITHER = (
    "(first_seq IS NULL) = (last_seq IS NULL) AND (first_seq IS NULL) = (entries = 0)"
)
CONTIGUOUS = "first_seq IS NULL OR last_seq - first_seq + 1 = entries"

#: The same two, held to the chain.
A_CHAINS_BOTH_ENDS_OR_NEITHER = (
    "form <> 'chain' OR ((first_seq IS NULL) = (last_seq IS NULL) AND (first_seq IS NULL) = "
    "(entries = 0))"
)
A_CHAIN_IS_CONTIGUOUS = "form <> 'chain' OR first_seq IS NULL OR last_seq - first_seq + 1 = entries"

#: What a readable export is held to.
READABLE_NAMES_NO_WINDOW = "form <> 'readable' OR (first_seq IS NULL AND last_seq IS NULL)"
ONLY_A_CHAIN_HAS_A_VERDICT = "(form = 'chain') = (verified IS NOT NULL)"

#: Constraint names without the prefix; alembic applies `brain.db.NAMING_CONVENTION`. See `0030`.
WINDOW_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("a_window_names_both_ends_or_neither", BOTH_ENDS_OR_NEITHER, A_CHAINS_BOTH_ENDS_OR_NEITHER),
    ("the_window_is_contiguous", CONTIGUOUS, A_CHAIN_IS_CONTIGUOUS),
)
READABLE_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("form", FORM_IN),
    ("a_readable_export_names_no_window", READABLE_NAMES_NO_WINDOW),
    ("only_a_chain_says_whether_it_verified", ONLY_A_CHAIN_HAS_A_VERDICT),
)


def upgrade() -> None:
    op.add_column(
        "data_export",
        sa.Column("form", sa.String(FORM_CHARS), server_default="chain", nullable=False),
        schema="ops",
    )
    op.alter_column(
        "data_export", "verified", existing_type=sa.Boolean(), nullable=True, schema="ops"
    )
    for name, _before, after in WINDOW_CONSTRAINTS:
        op.drop_constraint(name, "data_export", schema="ops", type_="check")
        op.create_check_constraint(name, "data_export", after, schema="ops")
    for name, condition in READABLE_CONSTRAINTS:
        op.create_check_constraint(name, "data_export", condition, schema="ops")


def downgrade() -> None:
    for name, _condition in reversed(READABLE_CONSTRAINTS):
        op.drop_constraint(name, "data_export", schema="ops", type_="check")
    for name, before, _after in reversed(WINDOW_CONSTRAINTS):
        op.drop_constraint(name, "data_export", schema="ops", type_="check")
        op.create_check_constraint(
            name, "data_export", before, schema="ops", postgresql_not_valid=True
        )
    op.alter_column(
        "data_export", "verified", existing_type=sa.Boolean(), nullable=False, schema="ops"
    )
    op.drop_column("data_export", "form", schema="ops")
