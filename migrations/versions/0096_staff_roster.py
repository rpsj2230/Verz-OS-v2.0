"""The staff roster the scheduled sync applies, and one row for each of its runs.

`brain.tables.staff` argues the shape: members kept by the digest of their work address and never
the address, a leaver marked rather than deleted, and one appended row per scheduled attempt. What
is here is the two tables, their checks, row-level security and the grants.

**`USING (true)` on the reads, for `0068`'s reason.** Who may be told what the roster holds is the
Staff sources screen's question, asked against the reader's own grants in
`brain.console.staff_source_view`; a predicate here would be a second and different answer to it.

**SELECT, INSERT and UPDATE on the members, SELECT and INSERT on the runs, and no DELETE on
either.** A member who left is marked, because the mark is what lists their agents for a new
owner, and a run is appended once, because "the credential was refused six nights running" is only
true while the six rows are kept. The worker writes as the database owner, as `0068` records for
`ops.connector_sync`, and the application role holds the same writes so a worker configured with
that login is not refused.

**No trigger into the ledger.** A roster row is a fact a source asserted, not a permission change:
nothing here grants, and the credential write that makes a run possible is already a `credential`
entry through `ops.credential_write`.

The downgrade drops both tables; their policies and grants go with them.

Task ids: M1.6.12, M1.8.6, M1.8.9

Revision ID: 0096
Revises: 0093
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0096"
down_revision = "0093"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("auth.staff_member", "auth.staff_sync_run")

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.staff` by `tests/unit/test_tables.py`'s model-versus-migration check.
SOURCE_CHARS = 32
SOURCE_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"
IDENTITY_HASH_PATTERN = "^[0-9a-f]{64}$"
DISPLAY_NAME_CHARS = 200
DEPARTMENT_CHARS = 120
STABLE_ID_CHARS = 200
DETAIL_CHARS = 500

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON auth.staff_member TO brain_app",
    "GRANT SELECT, INSERT ON auth.staff_sync_run TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE auth.staff_member ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY staff_member_readable ON auth.staff_member
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY staff_member_insertable ON auth.staff_member
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY staff_member_updatable ON auth.staff_member
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
    "ALTER TABLE auth.staff_sync_run ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY staff_sync_run_readable ON auth.staff_sync_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY staff_sync_run_appendable ON auth.staff_sync_run
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "staff_member",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(SOURCE_CHARS), nullable=False),
        sa.Column("address_hash", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(DISPLAY_NAME_CHARS), nullable=False),
        sa.Column("department", sa.String(DEPARTMENT_CHARS), nullable=True),
        sa.Column("stable_id", sa.String(STABLE_ID_CHARS), nullable=True),
        sa.Column("first_listed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_listed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_because", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"source ~ '{SOURCE_PATTERN}'", name="source_shape"),
        sa.CheckConstraint(f"address_hash ~ '{IDENTITY_HASH_PATTERN}'", name="address_is_a_digest"),
        sa.CheckConstraint("length(btrim(display_name)) > 0", name="display_name_present"),
        sa.CheckConstraint(
            "left_because IS NULL OR left_because IN "
            "('absent_from_complete_roster', 'source_says_left')",
            name="left_because",
        ),
        sa.CheckConstraint(
            "(left_at IS NULL) = (left_because IS NULL)",
            name="left_at_and_left_because_together",
        ),
        sa.CheckConstraint("last_listed_at >= first_listed_at", name="listed_in_order"),
        sa.UniqueConstraint("source", "address_hash"),
        schema="auth",
    )
    op.create_index("ix_staff_member_left_at", "staff_member", ["left_at"], schema="auth")

    op.create_table(
        "staff_sync_run",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(SOURCE_CHARS), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("added", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("marked_left", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("renamed", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("withheld", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.CheckConstraint(f"source ~ '{SOURCE_PATTERN}'", name="source_shape"),
        sa.CheckConstraint(
            "outcome IN ('applied', 'credential_refused', 'misconfigured', 'no_credential', "
            "'not_schedulable', 'unchanged', 'unreachable')",
            name="outcome",
        ),
        sa.CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        sa.CheckConstraint(
            f"length(btrim(detail)) > 0 AND length(detail) <= {DETAIL_CHARS}",
            name="detail_is_a_sentence",
        ),
        sa.CheckConstraint(
            "outcome IN ('applied', 'unchanged') OR (cardinality(added) = 0 "
            "AND cardinality(marked_left) = 0 AND cardinality(renamed) = 0)",
            name="only_an_applied_run_changes_anybody",
        ),
        schema="auth",
    )
    op.create_index(
        "ix_staff_sync_run_source_finished",
        "staff_sync_run",
        ["source", "finished_at"],
        schema="auth",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The indexes, the policies and the grants go with the tables.
    op.drop_table("staff_sync_run", schema="auth")
    op.drop_table("staff_member", schema="auth")
