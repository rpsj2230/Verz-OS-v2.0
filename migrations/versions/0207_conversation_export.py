"""A person's export of their own conversation is recorded as an export, as every other one is.

`brain.member_activity.export_my_history` builds a person's own conversation as an export and the
`ExportAudit` row recording them taking it, filed as a subject access request in their own name, and
nothing wrote that row: no route called it. `brain.thread_routes` now does, and the row lands in
`ops.data_export` beside the audit trail and access certification exports, so `0053`'s trigger
appends the same `publish` entry naming the data set, and the Exports log lists it.

**`ops.data_export` may record a conversation.** `0146`'s `data_set` list held two members;
`conversation_history` joins it, recorded as a readable export (no window, no verdict) by `0082`'s
constraints, with the sha256 of the exact bytes the person received and how many turns left.

**The downgrade** puts `0146`'s list back `NOT VALID`, for
`brain.ops.migration_policy.A_DOWNGRADE_NARROWS_WHAT_IS_WRITTEN_NEXT_AND_NOT_WHAT_WAS_WRITTEN_BEFORE`,
so a conversation export already recorded stays and no new one is accepted.

Task ids: M33.3.1.3

Revision ID: 0207
Revises: 0187
"""

from __future__ import annotations

from alembic import op

revision = "0207"
# The head of main on the day. Re-pointed at whichever migration is the head when it lands:
# nothing here depends on anything after 0146.
down_revision = "0187"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: `brain.tables.data_export.ExportDataSet`, sorted as `one_of` sorts, after and before.
WIDENED_DATA_SETS = "data_set IN ('access_certification', 'audit_trail', 'conversation_history')"
NARROWER_DATA_SETS = "data_set IN ('access_certification', 'audit_trail')"

#: What this migration replaces: `0146`'s data set list.
SUPERSEDES: dict[str, str] = {NARROWER_DATA_SETS: WIDENED_DATA_SETS}


def upgrade() -> None:
    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint("data_set", "data_export", WIDENED_DATA_SETS, schema="ops")


def downgrade() -> None:
    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint(
        "data_set", "data_export", NARROWER_DATA_SETS, schema="ops", postgresql_not_valid=True
    )
