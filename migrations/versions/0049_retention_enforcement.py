"""Legal holds, retention reports and the sweep's release get tables, with row-level security on.

`brain.tables.retention` holds the argument for the three shapes and `brain.ops.retention_store`
the argument for what reads and writes them. What is here is the tables, their policies and their
grants. They exist because the scheduled retention sweep has run since 0037 in report-only mode
with no holds, for the reason `brain.ops.schedule_runner.NOTHING_RECORDS_A_LEGAL_HOLD_YET` gave:
nothing recorded either a hold or a release.

**Read with `USING (true)`, for the reason `0034` gives.** Who may be shown a retention report is
`brain.console.govern_surfaces.retention_view`'s decision, which withholds it from everybody
without a company-wide grant; a predicate here would be a second copy of that rule. The sweep
reads every hold, because a hold it cannot see is a hold that does not hold.

**A hold is lifted and a release withdrawn by an update that can happen once.** The update
policies admit only a row not yet lifted or withdrawn and check that the new row is, and UPDATE is
granted on the two lifting columns alone, so the application role cannot edit what a hold covers
or which report a release came after. The read policies are unconditional, so the new row passes
the read check PostgreSQL applies to an update, which `0045` measured the hard way.

**No DELETE on any of the three.** A hold that could be deleted is a hold whose existence can be
denied afterwards; a report that could be deleted is a sweep that removed rows and left no record
of it; a release that could be deleted is a deletion nobody approved.

**One live release, by a partial unique index**, because a second live release would make
withdrawing one a withdrawal that changes nothing.

The downgrade drops all three and discards every hold, report and release.

Task ids: M25.1.5

Revision ID: 0049
Revises: 0048
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("obs.legal_hold", "ops.retention_report", "ops.retention_release")

APP_ROLE = "brain_app"

#: `brain.audit.ledger.IDENTIFIER` and `brain.tables.retention.REASON_CODE_PATTERN`, copied rather
#: than imported for the reason `0009` gives: a migration describes the database it built.
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
FIELD_NAME_PATTERN = "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$"

RLS: tuple[str, ...] = (
    "ALTER TABLE obs.legal_hold ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY legal_hold_readable ON obs.legal_hold
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY legal_hold_placed_unlifted ON obs.legal_hold
        FOR INSERT TO brain_app
        WITH CHECK (released_at IS NULL)
    """,
    """
    CREATE POLICY legal_hold_lifted_once ON obs.legal_hold
        FOR UPDATE TO brain_app
        USING (released_at IS NULL)
        WITH CHECK (released_at IS NOT NULL)
    """,
    "ALTER TABLE ops.retention_report ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY retention_report_readable ON ops.retention_report
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY retention_report_appendable ON ops.retention_report
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.retention_release ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY retention_release_readable ON ops.retention_release
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY retention_release_made_live ON ops.retention_release
        FOR INSERT TO brain_app
        WITH CHECK (withdrawn_at IS NULL)
    """,
    """
    CREATE POLICY retention_release_withdrawn_once ON ops.retention_release
        FOR UPDATE TO brain_app
        USING (withdrawn_at IS NULL)
        WITH CHECK (withdrawn_at IS NOT NULL)
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON obs.legal_hold TO brain_app",
    "GRANT UPDATE (released_at, released_by) ON obs.legal_hold TO brain_app",
    "GRANT SELECT, INSERT ON ops.retention_report TO brain_app",
    "GRANT SELECT, INSERT ON ops.retention_release TO brain_app",
    "GRANT UPDATE (withdrawn_at, withdrawn_by) ON ops.retention_release TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "legal_hold",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column(
            "subjects",
            postgresql.ARRAY(sa.String(128)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "actors",
            postgresql.ARRAY(sa.String(128)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("all_subjects", sa.Boolean(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("placed_by", sa.String(128), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", sa.String(128), nullable=True),
        sa.CheckConstraint(f"id ~ '{IDENTIFIER_PATTERN}'", name="id_is_an_identifier"),
        sa.CheckConstraint(f"reason_code ~ '{FIELD_NAME_PATTERN}'", name="reason_is_a_code"),
        sa.CheckConstraint(
            f"placed_by ~ '{IDENTIFIER_PATTERN}'", name="placed_by_is_an_identifier"
        ),
        sa.CheckConstraint(
            "all_subjects OR cardinality(subjects) > 0 OR cardinality(actors) > 0",
            name="names_something",
        ),
        sa.CheckConstraint(
            "(released_at IS NULL AND released_by IS NULL) OR "
            "(released_at IS NOT NULL AND released_by IS NOT NULL)",
            name="lifted_by_somebody",
        ),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= placed_at",
            name="lifted_after_it_was_placed",
        ),
        schema="obs",
    )
    op.create_index("ix_legal_hold_placed_at", "legal_hold", ["placed_at"], schema="obs")

    op.create_table(
        "retention_report",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_only", sa.Boolean(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("stores", postgresql.JSONB(), nullable=False),
        sa.Column("holds", postgresql.JSONB(), nullable=False),
        sa.Column("findings", postgresql.JSONB(), nullable=False),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.CheckConstraint("jsonb_typeof(stores) = 'array'", name="stores_list"),
        sa.CheckConstraint("jsonb_typeof(holds) = 'array'", name="holds_list"),
        sa.CheckConstraint("jsonb_typeof(findings) = 'array'", name="findings_list"),
        sa.CheckConstraint(
            "failure IS NULL OR length(failure) BETWEEN 1 AND 2000",
            name="failure_is_a_sentence",
        ),
        schema="ops",
    )
    op.create_index("ix_retention_report_at", "retention_report", ["at"], schema="ops")

    op.create_table(
        "retention_release",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "after_report",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("ops.retention_report.id"),
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_by", sa.String(128), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.String(128), nullable=True),
        sa.CheckConstraint(f"released_by ~ '{IDENTIFIER_PATTERN}'", name="by_is_an_identifier"),
        sa.CheckConstraint(
            "(withdrawn_at IS NULL AND withdrawn_by IS NULL) OR "
            "(withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL)",
            name="withdrawn_by_somebody",
        ),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= released_at",
            name="withdrawn_after_it_was_released",
        ),
        schema="ops",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_retention_release_live ON ops.retention_release "
        "((withdrawn_at IS NULL)) WHERE withdrawn_at IS NULL"
    )

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The indexes, policies and grants go with the tables. The release points at a report, so
    # it goes first.
    op.drop_table("retention_release", schema="ops")
    op.drop_table("retention_report", schema="ops")
    op.drop_table("legal_hold", schema="obs")
