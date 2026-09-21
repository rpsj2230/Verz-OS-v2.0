"""Service accounts and their keys get tables, and a partner's standing grants stop counting.

Two changes, both about who may act with no standing authority of their own.

**`auth.service_account` and `auth.api_key`.** `brain.tables.service_account` argues both. An
account is not a principal, so `gate.capability_grant`'s foreign key refuses a grant naming it and
its reach can only be its owner's narrowed by its ceiling (M1.1.7, M1.8.2). A key is a digest, and
there is no column for its secret. Both are retired rather than removed, under the policies every
retirable table carries since `0045`: a live row is readable, a row retired in this statement is
readable for the rest of it, and nothing retired is found afterwards.

**`gate.held_grants` stops counting a partner's standing grants** (M1.2.4). `brain.identity.roles.
standing_entitlement` has always said a partner holds nothing whatever the grant table says, and the
resolver every request goes through never read employment, so a partner with rows in the table held
them. What a partner may hold is a break-glass window: a grant or an assignment with a lapse no more
than `BREAK_GLASS_MAX` after it was written, which is exactly what an approved elevation writes
(`brain.gate.elevation_store`). Every other row a partner has is kept, shown and inert. See
`A_PARTNER_HOLDS_ONLY_A_WINDOW`. The function keeps its signature and its columns, so
`gate.resolve_entitlements` and `gate.entitlements_with_lapse`, which both read it, change their
answer for a partner and for nobody else.

Rejected: refusing the write, with a trigger on the grant tables. It leaves the rows a partner
already has (staff who became a partner, a migration, a mistake) counting, which is the state the
type calls the reason for ignoring the table rather than trusting it.

The downgrade drops both tables and puts back `0048`'s body word for word.

Task ids: M1.1.7, M1.2.4, M1.8.2

Revision ID: 0095
Revises: 0093
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0095"
# The head of origin/main when this was written.
down_revision = "0096"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("auth.service_account", "auth.api_key")

APP_ROLE = "brain_app"

#: Copied for the reason `0009` gives about reading live code from a migration, and held equal to
#: `brain.tables.service_account` by `tests/unit/test_service_accounts.py`.
CLIENT_ID_PATTERN = r"^svc_[a-z0-9][a-z0-9_]{1,62}$"
HANDLE_PATTERN = r"^[A-Za-z0-9_-]{6,32}$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"

#: `brain.identity.roles.BREAK_GLASS_MAX`, as SQL, written into both halves of the function below.
#: Held equal to the constant, and to the function's text, by the same test.
BREAK_GLASS_WINDOW = "interval '4 hours'"

#: Why a partner's row counts only when it is a window.
A_PARTNER_HOLDS_ONLY_A_WINDOW: Final = (
    "A partner has no standing entitlement. A row counts for them only when it lapses no more "
    "than the break-glass maximum after it was written, which is what an approved elevation is; "
    "any other row they hold is kept and confers nothing."
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON auth.service_account TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON auth.api_key TO brain_app",
)

#: `0045`'s shape for a retirable table, per table.
RLS: tuple[str, ...] = (
    "ALTER TABLE auth.service_account ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY service_account_live ON auth.service_account
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY service_account_insertable ON auth.service_account
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY service_account_updatable ON auth.service_account
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "ALTER TABLE auth.api_key ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY api_key_live ON auth.api_key
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY api_key_insertable ON auth.api_key
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY api_key_updatable ON auth.api_key
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)

# `0048`'s rows, with the partner's window. The casts are `0048`'s, for its reason.
HELD_GRANTS_WITH_PARTNER_WINDOW = """
CREATE OR REPLACE FUNCTION gate.held_grants(p_principal_id text, p_now timestamptz)
RETURNS TABLE (capability text, scope jsonb, not_after timestamptz)
LANGUAGE sql
STABLE
AS $$
    SELECT g.capability::text, g.scope, g.not_after
    FROM gate.capability_grant g
    JOIN auth.principal pr ON pr.id = g.principal_id
    WHERE g.principal_id = p_principal_id
      AND g.deleted_at IS NULL
      AND (g.not_after IS NULL OR g.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (g.not_after IS NOT NULL AND g.not_after <= g.created_at + interval '4 hours')
      )
    UNION ALL
    SELECT member.capability::text, a.scope, a.not_after
    FROM gate.capability_pack_assignment a
    JOIN gate.capability_pack k
      ON k.id = a.pack_id
     AND k.deleted_at IS NULL
    JOIN auth.principal pr ON pr.id = a.principal_id
    CROSS JOIN LATERAL unnest(k.capabilities) AS member(capability)
    WHERE a.principal_id = p_principal_id
      AND a.deleted_at IS NULL
      AND (a.not_after IS NULL OR a.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (a.not_after IS NOT NULL AND a.not_after <= a.created_at + interval '4 hours')
      )
$$
"""

# `0048`'s body, restated for the downgrade for the reason `0048` gives.
HELD_GRANTS_AS_0048_WROTE_IT = """
CREATE OR REPLACE FUNCTION gate.held_grants(p_principal_id text, p_now timestamptz)
RETURNS TABLE (capability text, scope jsonb, not_after timestamptz)
LANGUAGE sql
STABLE
AS $$
    SELECT g.capability::text, g.scope, g.not_after
    FROM gate.capability_grant g
    JOIN auth.principal pr ON pr.id = g.principal_id
    WHERE g.principal_id = p_principal_id
      AND g.deleted_at IS NULL
      AND (g.not_after IS NULL OR g.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
    UNION ALL
    SELECT member.capability::text, a.scope, a.not_after
    FROM gate.capability_pack_assignment a
    JOIN gate.capability_pack k
      ON k.id = a.pack_id
     AND k.deleted_at IS NULL
    JOIN auth.principal pr ON pr.id = a.principal_id
    CROSS JOIN LATERAL unnest(k.capabilities) AS member(capability)
    WHERE a.principal_id = p_principal_id
      AND a.deleted_at IS NULL
      AND (a.not_after IS NULL OR a.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "service_account",
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("owner_principal_id", sa.String(128), nullable=False),
        sa.Column("ceiling", postgresql.ARRAY(sa.String(200)), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(200), server_default=sa.text("''"), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"client_id ~ '{CLIENT_ID_PATTERN}'", name="client_id_shape"),
        sa.CheckConstraint("cardinality(ceiling) > 0", name="ceiling_declared"),
        sa.CheckConstraint("client_id <> owner_principal_id", name="not_its_own_owner"),
        sa.CheckConstraint(
            "subject IS NULL OR length(btrim(subject)) > 0", name="subject_present_or_null"
        ),
        sa.ForeignKeyConstraint(["owner_principal_id"], ["auth.principal.id"]),
        sa.PrimaryKeyConstraint("client_id"),
        schema="auth",
    )
    op.create_index(
        "ix_auth_service_account_owner_principal_id",
        "service_account",
        ["owner_principal_id"],
        schema="auth",
    )
    op.create_index(
        "ix_auth_service_account_deleted_at", "service_account", ["deleted_at"], schema="auth"
    )
    op.create_index(
        "uq_service_account_live_subject",
        "service_account",
        ["subject"],
        unique=True,
        schema="auth",
        postgresql_where=sa.text("deleted_at IS NULL AND subject IS NOT NULL"),
    )
    op.create_table(
        "api_key",
        sa.Column("handle", sa.String(32), nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(200), server_default=sa.text("''"), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"handle ~ '{HANDLE_PATTERN}'", name="handle_shape"),
        sa.CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_is_a_digest"),
        sa.CheckConstraint("not_after > issued_at", name="lapses_after_issue"),
        sa.ForeignKeyConstraint(["client_id"], ["auth.service_account.client_id"]),
        sa.PrimaryKeyConstraint("handle"),
        schema="auth",
    )
    op.create_index("ix_auth_api_key_client_id", "api_key", ["client_id"], schema="auth")
    op.create_index("ix_auth_api_key_deleted_at", "api_key", ["deleted_at"], schema="auth")
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    op.execute(HELD_GRANTS_WITH_PARTNER_WINDOW)


def downgrade() -> None:
    op.execute(HELD_GRANTS_AS_0048_WROTE_IT)
    # The policies, the grants and the indexes go with the tables.
    op.drop_table("api_key", schema="auth")
    op.drop_table("service_account", schema="auth")
