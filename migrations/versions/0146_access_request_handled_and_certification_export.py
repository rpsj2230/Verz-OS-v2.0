"""An access request is marked handled by its owner, and a certification report is an export.

**`gate.access_request_handled` holds one row per request its owner has dealt with** (needs-rupash
gap (a)). A request was insert-and-read only, so a steward's list grew for ever with every request
they had already dealt with, and nothing said which. The owner marks one handled by inserting a row
keyed by the request, so a second mark is a conflict, and the insert policy admits it only when
`handled_by` is the owner of the request it names. SELECT and INSERT only: a mark cannot be moved
or cleared, and the request row itself is never updated.

Rejected: `handled_at` and `handled_by` on `gate.access_request`, with a column grant and an update
policy. It gave the application an UPDATE on a table `0101` built insert only, and a new policy and
check on a table the release before already writes, which `brain.deployment.compatibility` refuses
as a narrowing during a rolling deploy.

Not on the ledger, for the reason `0101` gives about the request itself: a request changes nothing
anybody holds, and marking it handled changes nothing either. The decision is a grant written on
the People or Roles screens, which is recorded there. The row keeps who marked it and when.

**`ops.data_export` may record an access certification report** (M27.15.21). `0053`'s `data_set`
list held one member; `access_certification` joins it, recorded as a readable export (no window,
no verdict) by `0082`'s constraints, and `0053`'s trigger appends its `publish` entry exactly as
for an audit trail export, naming the data set under `fields`.

**The downgrade** drops the handled table, which loses the marks and keeps every request, and puts
`0053`'s list back `NOT VALID`, for
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

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.access_request_handled",)

APP_ROLE = "brain_app"

#: `brain.tables.identity.PRINCIPAL_ID_CHARS`, copied for the reason `0009` gives.
PRINCIPAL_ID_CHARS = 128

#: SELECT and INSERT. Never UPDATE and never DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON gate.access_request_handled TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.access_request_handled ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY access_request_handled_readable ON gate.access_request_handled
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY access_request_handled_by_its_owner ON gate.access_request_handled
        FOR INSERT TO brain_app
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM gate.access_request r
                WHERE r.id = request_id AND r.owner_id = handled_by
            )
        )
    """,
)

#: `brain.tables.data_export.ExportDataSet`, sorted as `one_of` sorts, after and before.
WIDENED_DATA_SETS = "data_set IN ('access_certification', 'audit_trail')"
NARROWER_DATA_SETS = "data_set IN ('audit_trail')"

#: What this migration replaces: `0053`'s data set list.
SUPERSEDES: dict[str, str] = {NARROWER_DATA_SETS: WIDENED_DATA_SETS}


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "access_request_handled",
        sa.Column("request_id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("handled_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "handled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["request_id"], ["gate.access_request.id"], ondelete="RESTRICT"),
        schema="gate",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)

    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint("data_set", "data_export", WIDENED_DATA_SETS, schema="ops")


def downgrade() -> None:
    op.drop_constraint("data_set", "data_export", schema="ops", type_="check")
    op.create_check_constraint(
        "data_set", "data_export", NARROWER_DATA_SETS, schema="ops", postgresql_not_valid=True
    )

    # The policies and the grant go with the table.
    op.drop_table("access_request_handled", schema="gate")
