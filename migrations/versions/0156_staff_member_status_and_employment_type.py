"""A roster row says where somebody stands and what kind of employment they have.

The owner, 2026-09-29: "there are some people who are suspended or outsourced people who are in our
list. So, when listing the people, it should show the status, and those suspended or outsourced
should not be able to access the Brain" (needs-rupash 115). A roster row held `left_at` and nothing
else about standing, and nothing about employment type at all, so neither could be shown or acted on.

**`status`**, one of `brain.identity.staff_source.EmploymentStatus`: active, suspended, left, not
activated. Not null with a default of `active`, so the release still running during a deploy, which
names no such column, inserts a row this accepts, and every row already held reads as active until
the next run reads its source again.

**`employment_type`**, one of `EmploymentType`, or null where the source records none. Nullable,
because the rows already held were written by a run that read no type, and there is no honest value
to backfill.

**The checks travel with the columns**, under the naming convention, as `0115` adds its own: a
constraint declared on a column this migration adds narrows nothing the previous release could
write.

**The downgrade** drops both columns, which loses what the last run read; the next run reads it again.

Task ids: M1.6.13, M1.6.14

Revision ID: 0156
Revises: 0155
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

SCHEMA = "auth"
TABLE = "staff_member"

#: `brain.tables.staff`'s lists, copied for `0009`'s reason about reading live code from a
#: migration and held equal to them by a test.
EMPLOYMENT_STATUSES: tuple[str, ...] = ("active", "left", "not_activated", "suspended")
EMPLOYMENT_TYPES: tuple[str, ...] = (
    "consultant",
    "contractor",
    "intern",
    "labour_dispatch",
    "other",
    "outsourced",
    "regular",
)
EMPLOYMENT_CHARS = 24


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{one}'" for one in sorted(values)))


STATUS_CHECK = _one_of("status", EMPLOYMENT_STATUSES)
TYPE_CHECK = f"employment_type IS NULL OR {_one_of('employment_type', EMPLOYMENT_TYPES)}"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "status",
            sa.String(EMPLOYMENT_CHARS),
            sa.CheckConstraint(STATUS_CHECK, name="status"),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column(
            "employment_type",
            sa.String(EMPLOYMENT_CHARS),
            sa.CheckConstraint(TYPE_CHECK, name="employment_type"),
            nullable=True,
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "employment_type", schema=SCHEMA)
    op.drop_column(TABLE, "status", schema=SCHEMA)
