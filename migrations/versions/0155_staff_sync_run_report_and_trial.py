"""A staff sync says what it read, and a trial read is a run of its own.

Found on the owner's install on 2026-09-29: a Lark staff sync added 123 people, placed every one of
them in no department, and its run row said only "Read the staff list from lark and applied it."
The reason was a missing scope (`brain.identity.staff_adapters.LARK_DEPARTMENT_NAME_SCOPE`), and
nothing the product showed could have told anybody. Two changes to `auth.staff_sync_run`, which
`0096` built.

**`report`, the sentences `brain.identity.staff_adapters.ReadReport.words` says**: how many
departments the walk read and how many had a name, how many people were read and placed, a count
for each reason somebody was left unplaced, and what to change at the source. Counts and constant
sentences, never a name: the column is shown on the Staff sources screen and in the job history.
A column rather than more words in `detail`, whose check holds it to 500 characters, because the
longest report a Lark read can make is longer than that and the part a truncation would cut is the
sentence saying which scope to add. **Not null with a default of the empty array**, so the release
still running during a deploy, which names no such column, inserts a row this accepts; the
compatibility gate reads that as a not-null column with a default and passes it.

**`outcome` gains `tried`**: a read somebody asked for from the Staff sources screen, made by the
worker with the kept credential, which computes the plan the nightly run would and writes no
member. None of the seven outcomes says that. `applied` and `unchanged` are what `last_applied` is
read from, so a trial recorded as either would make the next nightly run a second run of a source
that was never applied, and the first-run rule that keeps it from removing anybody would not hold.
The failure outcomes are what a trial that failed is recorded as, because they are true of it.
Widened as
`0142` widens `ops.connector_sync.outcome`: the new list holds the old one, which the compatibility
gate orders, and `SUPERSEDES` names the old text for `tests/unit/test_tables.py`.
`only_an_applied_run_changes_anybody` already holds a trial to naming nobody.

**The downgrade** puts the seven-word list back `NOT VALID`, for `0026`'s reason, and drops the
column, which loses the reports: a real loss and the only reversal a column addition has.

Task ids: M1.6.11, M1.6.12, M27.7.2

Revision ID: 0155
Revises: 0150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0155"
# The newest migration on origin/main when this was merged with it. A branch landing a newer one
# first moves this line to it.
down_revision = "0150"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

SCHEMA = "auth"
TABLE = "staff_sync_run"
COLUMN = "report"

#: The bare constraint name; alembic applies the naming convention, for `0026`'s reason.
CONSTRAINT = "outcome"

#: `0096`'s list, and the list this release writes. Copied for `0009`'s reason about reading live
#: code from a migration, and held equal to `brain.tables.staff.RUN_OUTCOMES` by a test.
NARROWER_OUTCOMES = (
    "outcome IN ('applied', 'credential_refused', 'misconfigured', 'no_credential', "
    "'not_schedulable', 'unchanged', 'unreachable')"
)
WIDENED_OUTCOMES = (
    "outcome IN ('applied', 'credential_refused', 'misconfigured', 'no_credential', "
    "'not_schedulable', 'tried', 'unchanged', 'unreachable')"
)

#: What this migration replaces, for `tests/unit/test_tables.py`'s `as_amended`.
SUPERSEDES: dict[str, str] = {NARROWER_OUTCOMES: WIDENED_OUTCOMES}

#: `0096`'s CREATE TABLE as it reads once this column is added, for the model comparison.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "withheld TEXT[] NOT NULL, CONSTRAINT pk_staff_sync_run PRIMARY KEY (id),": (
        "withheld TEXT[] NOT NULL, report TEXT[] DEFAULT '{}' NOT NULL, "
        "CONSTRAINT pk_staff_sync_run PRIMARY KEY (id),"
    ),
}


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, WIDENED_OUTCOMES, schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT, TABLE, NARROWER_OUTCOMES, schema=SCHEMA, postgresql_not_valid=True
    )
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
