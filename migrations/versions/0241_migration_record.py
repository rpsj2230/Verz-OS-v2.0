"""The documents a migration from another system is run on, kept: `ops.migration_record`.

`brain.migration` holds three registers as modules of refusals (what the old system holds and what
happens to each of it, the comparison period with the criteria agreed before it began, and the
cutover record), and none of them had anywhere to be kept. This is the table (M37.1.1.1 and its
neighbours); `brain.tables.migration_record` holds the argument for each column.

**A version per row, appended and never edited.** Each save is a new row of one kind and the
newest is current. A migration register is the thing somebody is asked to account for months
later, and a row overwritten in place answers with the last edit. `0032`'s `ops.plugin_version`
and `0031`'s `ops.budget_version` have the same shape for the same reason.

**SELECT and INSERT only, written in the session's own name**, `0217`'s shape: the insert policy
admits a row whose `recorded_by` is the session's principal, and no UPDATE or DELETE is granted.
**No ledger entry of its own**: a version is its own record of who and when, and a save changes
nobody's access and no configuration. What is recorded about a person leaving the old system is
what the document says, and the cutover's own gate, not the ledger, is what refuses a completed
cutover while an act with a security consequence is unrecorded.

The downgrade drops the table. The documents it held are lost, which is the state before this.

Task ids: M37.1.1.1

Revision ID: 0241
Revises: 0225
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0241"
# The plan's number after 0225. The coordinator re-points it at whichever migration is the head
# when the train is assembled.
down_revision = "0225"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: a person is a value, so a version
#: outlives the person who saved it.
TABLES: tuple[str, ...] = ("ops.migration_record",)

APP_ROLE = "brain_app"

#: Held equal to `brain.tables.migration_record`.
KIND_CHARS = 16
PRINCIPAL_ID_CHARS = 128

#: `brain.tables.migration_record.RecordKind`, on the day this ran.
KINDS: tuple[str, ...] = ("cutover", "parallel", "register")

PRINCIPAL = "current_setting('app.principal_id', true)"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.migration_record ENABLE ROW LEVEL SECURITY",
    # Read by the screen for whoever may see a migration; who may is decided where it is shown.
    """
    CREATE POLICY migration_record_readable ON ops.migration_record
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY migration_record_written_in_the_sessions_name ON ops.migration_record
        FOR INSERT TO brain_app
        WITH CHECK (recorded_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.migration_record TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "migration_record",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("recorded_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(_one_of("kind", KINDS), name="kind"),
        sa.CheckConstraint("jsonb_typeof(body) = 'object'", name="body_object"),
        sa.CheckConstraint("length(btrim(recorded_by)) > 0", name="a_person_recorded"),
        schema="ops",
    )
    op.create_index(
        "ix_migration_record_newest_of_a_kind",
        "migration_record",
        ["kind", "recorded_at"],
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("migration_record", schema="ops")
