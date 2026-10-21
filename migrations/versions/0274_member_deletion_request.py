"""A person's request that their data be deleted, kept until the retention owner acts on it.

`brain.member_activity.request_deletion` and `route` were built and tested with no caller, and the
reason is the shape of the queue they would have to land in. **`ops.erasure_request` is carried out
by the worker on its next run "without anybody being asked again"**
(`brain.erasure_routes.ERASING`),
so filing a person's own click there would be an erase and not a request: it would be the silent
deletion the leaf (M40.4.2.3) says it must not be, with no legal-hold read at the moment of the ask
and no retention owner in the loop. So a person's ask is its own record, and the existing erasure
filing, which needs `admin:erasure` over everything, is the act that acts on it.

**`ops.deletion_request`, one row for each ask.** The person (a value, never a reference, so a row
outlives the person's directory row), when they asked, and, once the retention owner has filed the
erasure, who did and which erasure it became. A row with no `decided_at` is waiting. **A partial
unique index allows one waiting row for a person**, so asking twice is one ask and the second answer
is the first row; once it is decided a later ask is a new row.

**What the row does not hold**: no reason, no scope and no list of what was reached. The reach of a
deletion is `brain.ops.erasure`'s answer at the time it runs and a row copying it would be a second
statement of it, correct on the day it was written. The reason a person gives, if they give one, is
for the retention owner and belongs in the matter reference they file under, not in a table that is
read by the person's own page.

**Read by the application with `USING (true)`**, as `0230`'s `agent.agent_request` is: who may be
told is the route's decision (the person reads their own; `admin:erasure` over everything reads the
waiting ones), and a policy that tried to know about `admin:erasure` would be a second copy of it.
**Written as the person**: an insert is held to the person the session names and to a row not yet
decided. **Decided as the retention owner**: an update may only set the three decision columns,
once, and `decided_by` must be the session's principal. Never DELETE: a request that was filed is
the record that the person asked, and `brain.ops.erasure_store` reports these rows kept when the
person is erased, which is what lets a certificate say the request existed.

**No ledger trigger.** The act with a consequence is the erasure, which the ledger already records
(`0060`); a person asking is not a change to what the system holds. The row is insert-only apart
from the decision and is itself the record.

**The downgrade** drops the table. A waiting request is then lost, which is stated and not hidden
because there is nothing else the downgrade could do with it; no erasure that was filed from one is
undone, because that is the erasure queue's.

Task ids: M40.4.2.3

Revision ID: 0274
Revises: 0273
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0274"
# Follows 0272, the head of main when this was re-cut. The coordinator re-points it if another
# migration lands first, as every migration landed in a train is.
down_revision = "0273"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.deletion_request",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.member_deletion`.
PRINCIPAL_ID_CHARS = 128
ERASURE_REQUEST_ID_CHARS = 128

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.deletion_request ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY deletion_request_readable ON ops.deletion_request
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY deletion_request_made_by_the_person ON ops.deletion_request
        FOR INSERT TO brain_app
        WITH CHECK (subject_id = {PRINCIPAL} AND decided_at IS NULL)
    """,
    f"""
    CREATE POLICY deletion_request_decided_once_by_the_retention_owner ON ops.deletion_request
        FOR UPDATE TO brain_app
        USING (decided_at IS NULL)
        WITH CHECK (decided_at IS NOT NULL AND decided_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and UPDATE of the three decision columns alone. Never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.deletion_request TO brain_app",
    "GRANT UPDATE (decided_by, decided_at, erasure_request_id) ON ops.deletion_request"
    " TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.create_table(
        "deletion_request",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subject_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erasure_request_id", sa.String(ERASURE_REQUEST_ID_CHARS), nullable=True),
        sa.CheckConstraint("length(btrim(subject_id)) > 0", name="subject_present"),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)"
            " AND (decided_at IS NULL) = (erasure_request_id IS NULL)",
            name="decided_whole_or_not_at_all",
        ),
        schema="ops",
    )
    op.create_index(
        "uq_deletion_request_one_waiting",
        "deletion_request",
        ["subject_id"],
        unique=True,
        schema="ops",
        postgresql_where=sa.text("decided_at IS NULL"),
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The index, the policies and the grants go with the table.
    op.drop_table("deletion_request", schema="ops")
