"""A person proposed for a role, kept until somebody else decides it.

One table, `gate.role_nomination`. `brain.tables.role_nomination` holds the argument for each
column: the nominee as a value rather than a key, the scope by name and resolved at confirmation,
and a decision written once by a third person.

**SELECT, INSERT and UPDATE, and the UPDATE is a decision.** A person nominates in their own name:
the insert policy admits only a row whose `nominated_by` is the session's principal and that is
not yet decided. A confirmer or a decliner decides in theirs: the update policy admits only an
undecided row and only a `decided_by` that is the session's principal, so nobody decides in
another person's name and nothing reopens a decided nomination. No DELETE.

**No ledger entry of its own.** A confirmation writes a `gate.role_grant` in the same transaction,
and `0102`'s trigger puts that grant on the ledger with the confirmer as the actor. A nomination
nobody acted on changes nobody's access, which is what the ledger records.

**The downgrade drops it.** A pending nomination is a proposal and is made again; a confirmed one
left its role grant, which stays.

Task ids: M33.1.2.3

Revision ID: 0208
Revises: 0189
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0208"
down_revision = "0189"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at a role grant, which is never deleted.
TABLES: tuple[str, ...] = ("gate.role_nomination",)

APP_ROLE = "brain_app"
FAST_ROLE = "brain_fastlane"
PRINCIPAL = "current_setting('app.principal_id', true)"

#: Copied for `0009`'s reason and held equal to `brain.tables.role_nomination` by
#: `tests/unit/test_role_nominations.py`.
PRINCIPAL_ID_CHARS = 128
ROLE_CHARS = 32
SCOPE_SLUG_CHARS = 60
OUTCOME_CHARS = 16
REASON_CHARS = 500
ROLES = (
    "role IN ('approver', 'auditor', 'connector_admin', 'department_admin', 'member', "
    "'super_admin')"
)
SCOPED = "role IN ('approver', 'department_admin')"
OUTCOMES = "outcome IN ('confirmed', 'declined')"

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.role_nomination ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY role_nomination_readable ON gate.role_nomination
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY role_nomination_made_in_the_sessions_name ON gate.role_nomination
        FOR INSERT TO brain_app
        WITH CHECK (nominated_by = {PRINCIPAL} AND outcome IS NULL)
    """,
    f"""
    CREATE POLICY role_nomination_decided_in_the_sessions_name ON gate.role_nomination
        FOR UPDATE TO brain_app
        USING (outcome IS NULL)
        WITH CHECK (decided_by = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON gate.role_nomination TO brain_app",
    "GRANT UPDATE (outcome, decided_by, decided_at, grant_id) ON gate.role_nomination TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert all(FAST_ROLE not in statement for statement in GRANTS + RLS)
    op.create_table(
        "role_nomination",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("role", sa.String(ROLE_CHARS), nullable=False),
        sa.Column("scope_slug", sa.String(SCOPE_SLUG_CHARS), nullable=True),
        sa.Column("nominated_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(OUTCOME_CHARS), nullable=True),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grant_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(ROLES, name="role"),
        sa.CheckConstraint(
            f"({SCOPED}) = (scope_slug IS NOT NULL)", name="scope_exactly_when_required"
        ),
        sa.CheckConstraint(
            f"length(btrim(reason)) > 0 AND length(reason) <= {REASON_CHARS}",
            name="reason_present",
        ),
        sa.CheckConstraint("nominated_by <> principal_id", name="not_self_nominated"),
        sa.CheckConstraint(f"outcome IS NULL OR {OUTCOMES}", name="outcome"),
        sa.CheckConstraint(
            "(outcome IS NULL) = (decided_by IS NULL) AND (outcome IS NULL) = (decided_at IS NULL)",
            name="decided_once_and_whole",
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR (decided_by <> principal_id AND decided_by <> nominated_by)",
            name="decided_by_a_third_person",
        ),
        sa.CheckConstraint(
            "(outcome IS NOT DISTINCT FROM 'confirmed') = (grant_id IS NOT NULL)",
            name="a_grant_exactly_when_confirmed",
        ),
        sa.ForeignKeyConstraint(["grant_id"], ["gate.role_grant.id"], ondelete="RESTRICT"),
        schema="gate",
    )
    op.create_index(
        "ix_gate_role_nomination_created_at", "role_nomination", ["created_at"], schema="gate"
    )
    for statement in RLS + GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gate.role_nomination")
