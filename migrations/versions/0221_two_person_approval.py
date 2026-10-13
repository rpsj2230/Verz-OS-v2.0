"""A suspended action with a sensitive effect can need two different people, and the database holds it.

`gate.suspension` held one decision, and the person who asked could make it. This adds the second
person without a new table: three columns on the row, four checks and one policy.

**`two_person`, set when the action is raised.** `brain.gate.suspension_store.put_suspension` sets
it from the feature switch and the tool's declared effect, so what needs two people is fixed at the
moment the approval is asked for and a switch turned later cannot make an old one need fewer.
Existing rows and every row written by code that does not know of the column hold false, which is
what the previous release's behaviour is.

**`endorsed_by` and `endorsed_at`: the first approver.** A first approval of a `two_person` row does
not decide it. It writes these two columns and leaves the row pending, and a different person then
decides it, which is the existing update and the existing ledger entry. The ledger holds the second
person's decision as it always did; the first is on the row.

**The checks are the rule, and the route is the message.** Five, in the words of the leaf:

- the endorsement is a person and an instant together, or neither (two checks, one each way);
- only a `two_person` row is endorsed;
- whoever asked (`principal_id`, whose reach the action would run under) never endorses it;
- a `two_person` row is approved only by somebody who is neither the one who endorsed it nor the one
  who asked, and only once it has been endorsed.

Every one binds only a row the previous release cannot write (`two_person` false is the default), so
none narrows what it wrote.

**The update policy is `0042`'s, plus one.** A row that is `two_person`, pending and not yet
endorsed may be endorsed by a session that may approve it, in its own name. The column grant is the
two columns and nothing else. The decision's policy is untouched.

Task ids: M13.7.7

Revision ID: 0221
Revises: 0220
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0221"
# The plan's number, after 0220. Re-pointed at whichever migration is the head when it lands.
down_revision = "0220"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. This migration adds columns and no table.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"
ID_CHARS = 128

#: `0042`'s settings, copied for the reason `0009` gives.
APPROVABLE = "string_to_array(current_setting('app.approvable', true), ',')"
PRINCIPAL = "current_setting('app.principal_id', true)"

CHECKS: tuple[tuple[str, str], ...] = (
    ("an_endorsement_names_its_instant", "endorsed_by IS NULL OR endorsed_at IS NOT NULL"),
    ("an_endorsement_instant_names_its_person", "endorsed_at IS NULL OR endorsed_by IS NOT NULL"),
    ("only_a_two_person_row_is_endorsed", "endorsed_by IS NULL OR two_person"),
    ("the_asker_does_not_endorse", "endorsed_by IS NULL OR endorsed_by <> principal_id"),
    (
        "a_two_person_row_is_approved_by_two_others",
        "NOT two_person OR state <> 'approved' OR "
        "(endorsed_by IS NOT NULL AND decided_by <> endorsed_by AND decided_by <> principal_id)",
    ),
)

POLICY = f"""
    CREATE POLICY suspension_endorsed_once_by_the_session ON gate.suspension
        FOR UPDATE TO brain_app
        USING (
            state = 'pending' AND two_person AND endorsed_by IS NULL
            AND required_capability = ANY ({APPROVABLE})
        )
        WITH CHECK (state = 'pending' AND endorsed_by = {PRINCIPAL})
"""

GRANTS: tuple[str, ...] = (
    "GRANT UPDATE (endorsed_by, endorsed_at) ON gate.suspension TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.add_column(
        "suspension",
        sa.Column("two_person", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="gate",
    )
    op.add_column(
        "suspension", sa.Column("endorsed_by", sa.String(ID_CHARS), nullable=True), schema="gate"
    )
    op.add_column(
        "suspension",
        sa.Column("endorsed_at", sa.DateTime(timezone=True), nullable=True),
        schema="gate",
    )
    for name, condition in CHECKS:
        op.create_check_constraint(name, "suspension", condition, schema="gate")
    op.execute(POLICY)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY suspension_endorsed_once_by_the_session ON gate.suspension")
    for name, _ in reversed(CHECKS):
        op.drop_constraint(name, "suspension", schema="gate", type_="check")
    # The column grant goes with the columns.
    op.drop_column("suspension", "endorsed_at", schema="gate")
    op.drop_column("suspension", "endorsed_by", schema="gate")
    op.drop_column("suspension", "two_person", schema="gate")
