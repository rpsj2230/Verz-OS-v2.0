"""An access request can be marked handled by its owner, and a certification report is an export.

**`gate.access_request` gains `handled_at` and `handled_by`** (needs-rupash gap (a)). A request was
insert-and-read only, so a steward's list grew for ever with every request they had already dealt
with, and nothing said which. The owner marks one handled, once; both columns are set together or
neither, and `handled_by` must be the request's own owner, so nobody records another person's
request as dealt with. **UPDATE is granted on those two columns only**, and the policy admits an
update only to a row not yet handled, so a mark cannot be moved, cleared or put on twice, and the
rest of the row stays exactly as it was asked.

Not on the ledger, for the reason `0101` gives about the request itself: a request changes nothing
anybody holds, and marking it handled changes nothing either. The decision is a grant written on
the People or Roles screens, which is recorded there. The row keeps who marked it and when.

**`ops.data_export` may record an access certification report** (M27.15.21). `0053`'s `data_set`
list held one member; `access_certification` joins it, recorded as a readable export (no window,
no verdict) by `0082`'s constraints, and `0053`'s trigger appends its `publish` entry exactly as
for an audit trail export, naming the data set under `fields`.

**The downgrade** drops the two columns with their grant and policy, which loses the marks and
keeps every request, and puts `0053`'s list back `NOT VALID`, for
`brain.ops.migration_policy.A_DOWNGRADE_NARROWS_WHAT_IS_WRITTEN_NEXT_AND_NOT_WHAT_WAS_WRITTEN_BEFORE`,
so a report already recorded stays and no new one is accepted.

Task ids: M4.3.4, M27.15.21, M27.16.1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0146"
# The head of origin/main when this was written; re-pointed when it lands.
down_revision = "0149"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`.
TABLES: tuple[str, ...] = ()

#: `brain.tables.identity.PRINCIPAL_ID_CHARS`, copied for the reason `0009` gives.
PRINCIPAL_ID_CHARS = 128

#: Both or neither, and only the request's own owner.
HANDLED_WHOLE = "(handled_at IS NULL) = (handled_by IS NULL)"
HANDLED_BY_ITS_OWNER = "handled_by IS NULL OR handled_by = owner_id"

GRANTS: tuple[str, ...] = (
    "GRANT UPDATE (handled_at, handled_by) ON gate.access_request TO brain_app",
)
REVOKES: tuple[str, ...] = (
    "REVOKE UPDATE (handled_at, handled_by) ON gate.access_request FROM brain_app",
)

POLICIES: tuple[str, ...] = (
    """
    CREATE POLICY access_request_handled_once ON gate.access_request
        FOR UPDATE TO brain_app
        USING (handled_at IS NULL)
        WITH CHECK (handled_at IS NOT NULL AND handled_by = owner_id)
    """,
)

#: `brain.tables.data_export.ExportDataSet`, sorted as `one_of` sorts, after and before.
WIDENED_DATA_SETS = "data_set IN ('access_certification', 'audit_trail')"
NARROWER_DATA_SETS = "data_set IN ('audit_trail')"

#: What this migration replaces: `0053`'s data set list.
SUPERSEDES: dict[str, str] = {NARROWER_DATA_SETS: WIDENED_DATA_SETS}


def upgrade() -> None:
    op.add_column(
        "access_request",
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        schema="gate",
    )
    op.add_column(
        "access_request",
        sa.Column("handled_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        schema="gate",
    )
    op.create_check_constraint("handled_whole", "access_request", HANDLED_WHOLE, schema="gate")
    op.create_check_constraint(
        "handled_by_its_owner", "access_request", HANDLED_BY_ITS_OWNER, schema="gate"
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in POLICIES:
        op.execute(statement)

    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint("data_set", "data_export", WIDENED_DATA_SETS, schema="ops")


def downgrade() -> None:
    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint(
        "data_set", "data_export", NARROWER_DATA_SETS, schema="ops", postgresql_not_valid=True
    )

    op.execute("DROP POLICY access_request_handled_once ON gate.access_request")
    for statement in REVOKES:
        op.execute(statement)
    op.drop_constraint("handled_by_its_owner", "access_request", schema="gate", type_="check")
    op.drop_constraint("handled_whole", "access_request", schema="gate", type_="check")
    op.drop_column("access_request", "handled_by", schema="gate")
    op.drop_column("access_request", "handled_at", schema="gate")
