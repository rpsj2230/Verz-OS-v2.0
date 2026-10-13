"""The install can measure how long approvals wait, through a view that carries two times and no person.

`gate.suspension` is read by a person only for the approvals they raised or decided, or may approve
while pending (`0042`), so nothing the application serves could say how long approvals wait across
the install, and the deferral of push notifications for approvals (M35.3.2.2) had a trigger no
figure could ever fire. This adds **one view, `gate.approval_wait`, of `raised_at` and `decided_at`
for every decided approval and nothing else**: no id, no person, no agent, no capability and no
verdict. The application reads it in aggregate and shows one duration, never a count, which is the
rule the other views in this schema keep (`gate.suspension_capability` shows capability names and
nothing else). The view's owner is the table's owner, so it is read whole whoever asks, which is
the point and the whole of what it discloses; the grant is SELECT to the application role alone.

Rejected: a second, wider policy on `gate.suspension` for administrators. It would let a person with
the Install screen read other people's approvals row by row, which is the disclosure this view
exists to avoid. Rejected too: a column added to `ops.control_run`'s detail by a worker sweep, which
keeps a stale figure and needs a control nobody has asked for.

The downgrade drops the view.

Task ids: M35.4.5, M35.3.2.2

Revision ID: 0230
Revises: 0225
"""

from __future__ import annotations

from alembic import op

revision = "0230"
down_revision = "0225"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`.
TABLES: tuple[str, ...] = ()

VIEW = """
    CREATE VIEW gate.approval_wait AS
        SELECT raised_at, decided_at
        FROM gate.suspension
        WHERE decided_at IS NOT NULL
"""

GRANTS: tuple[str, ...] = ("GRANT SELECT ON gate.approval_wait TO brain_app",)


def upgrade() -> None:
    assert all("brain_app" in statement for statement in GRANTS)
    op.execute(VIEW)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW gate.approval_wait")
