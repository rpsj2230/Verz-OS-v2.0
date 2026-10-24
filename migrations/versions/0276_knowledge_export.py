"""The inventory of the documents a reader may see is recorded as an export, as every other is.

`brain.ops.export.knowledge_export` kept each item's scope with it, was tested, and had no caller:
`brain.ops.data_transfer.CATALOGUE` said the knowledge export could not run. Needs-rupash 108,
decided on 2026-09-29, says to build it. `brain.knowledge_export_routes` now does, from the Knowledge
screen, and the row lands in `ops.data_export` beside the audit trail, access certification and
conversation exports, so `0053`'s trigger appends the same `publish` entry naming the data set and
the Exports log lists it.

**`ops.data_export` may record a knowledge inventory.** `0207`'s `data_set` list held three members;
`knowledge` joins it, recorded as a readable export (no window, no verdict) by `0082`'s
constraints, with the sha256 of the exact bytes the reader received and how many documents left.

**The downgrade** puts `0207`'s list back `NOT VALID`, for
`brain.ops.migration_policy.A_DOWNGRADE_NARROWS_WHAT_IS_WRITTEN_NEXT_AND_NOT_WHAT_WAS_WRITTEN_BEFORE`,
so an inventory already recorded stays and no new one is accepted.

Task ids: M25.3.3

Revision ID: 0276
Revises: 0275
"""

from __future__ import annotations

from alembic import op

revision = "0276"
# The head of main on the day. Re-pointed at whichever migration is the head when it lands:
# nothing here depends on anything after 0207.
down_revision = "0275"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: `brain.tables.data_export.ExportDataSet`, sorted as `one_of` sorts, after and before.
WIDENED_DATA_SETS = (
    "data_set IN ('access_certification', 'audit_trail', 'conversation_history', 'knowledge')"
)
NARROWER_DATA_SETS = "data_set IN ('access_certification', 'audit_trail', 'conversation_history')"

#: What this migration replaces: `0207`'s data set list.
SUPERSEDES: dict[str, str] = {NARROWER_DATA_SETS: WIDENED_DATA_SETS}


def upgrade() -> None:
    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint("data_set", "data_export", WIDENED_DATA_SETS, schema="ops")


def downgrade() -> None:
    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint(
        "data_set", "data_export", NARROWER_DATA_SETS, schema="ops", postgresql_not_valid=True
    )
