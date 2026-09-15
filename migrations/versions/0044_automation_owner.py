"""An automation gets a table naming its owner, read through row-level security by id or by owner.

`brain.tables.automation` holds the argument for the shape, and `brain.ops.automation_owner` the
argument for item 56 of `docs/needs-rupash.md`. What is here is the table, its policies and its
grants.

**Read by the automation that is calling, or by its owner.** A call arrives with a credential
naming one automation, and the route tells the transaction which one with `app.automation_id`
before it reads anything, so the database hands over that row and no other: a credential for one
automation cannot be used to read another's ceiling by a query that forgot its WHERE clause. The
owner reads their own through `app.principal_id`, which is what a screen listing a person's
automations will need. A setting that is unset admits nothing.

**Registered only in the session's own name.** An insert names the session's principal as owner,
so nobody registers an automation that runs as somebody else. Whether the session may register
one at all is the application's decision, and there is no screen for it yet.

**Adopted only in the session's own name, and only the row named.** The update policy admits the
row `app.automation_id` names and checks that the new owner is the session's principal. Whether
the automation is awaiting an owner is not a column and cannot be a predicate here: it is the
owner's standing in `auth.principal`, derived by `brain.ops.automation_owner.standing_of` when it
is asked, and the store asks it under a row lock before it writes. UPDATE is granted on the owner
and the timestamp alone, so the credential, the tools and the ceiling cannot be edited by the
application role.

**No DELETE.** Retiring an automation is not built, and a role that could delete this row could
remove the record of who an automation ran as.

The downgrade drops the table and discards every registration, and with them every automation's
credential.

Task ids: none

Revision ID: 0044
Revises: 0043
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.automation_owner",)

APP_ROLE = "brain_app"

#: `brain.ops.automation_owner.AUTOMATION_ID`, `brain.ops.automation_owner.DIGEST` and
#: `brain.gate.leash.IDENTIFIER`, copied rather than imported for the reason `0009` gives: a
#: migration describes the database it built, and one that read live code would stop doing so
#: the day that code changed.
AUTOMATION_ID_PATTERN = "^[A-Za-z0-9_-]{1,128}$"
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"

AUTOMATION = "current_setting('app.automation_id', true)"
PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.automation_owner ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY automation_owner_readable ON gate.automation_owner
        FOR SELECT TO brain_app
        USING (automation_id = {AUTOMATION} OR owner_principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY automation_owner_registered_in_the_sessions_name ON gate.automation_owner
        FOR INSERT TO brain_app
        WITH CHECK (owner_principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY automation_owner_adopted_in_the_sessions_name ON gate.automation_owner
        FOR UPDATE TO brain_app
        USING (automation_id = {AUTOMATION})
        WITH CHECK (automation_id = {AUTOMATION} AND owner_principal_id = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON gate.automation_owner TO brain_app",
    "GRANT UPDATE (owner_principal_id, updated_at) ON gate.automation_owner TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "automation_owner",
        sa.Column("automation_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("owner_principal_id", sa.String(128), nullable=False),
        sa.Column("credential_digest", sa.String(64), nullable=False),
        sa.Column("declared_tools", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("ceiling", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"automation_id ~ '{AUTOMATION_ID_PATTERN}'", name="automation_id_shape"
        ),
        sa.CheckConstraint(
            f"owner_principal_id ~ '{IDENTIFIER_PATTERN}'",
            name="owner_principal_id_is_an_identifier",
        ),
        sa.CheckConstraint(
            "owner_principal_id <> automation_id", name="an_automation_is_not_its_owner"
        ),
        sa.CheckConstraint(
            f"credential_digest ~ '{DIGEST_PATTERN}'", name="credential_digest_shape"
        ),
        sa.CheckConstraint("cardinality(declared_tools) > 0", name="a_tool_is_declared"),
        sa.CheckConstraint("jsonb_typeof(ceiling) = 'array'", name="a_ceiling_is_a_list_of_grants"),
        schema="gate",
    )
    op.create_index(
        "ix_automation_owner_owner_principal_id",
        "automation_owner",
        ["owner_principal_id"],
        schema="gate",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the table.
    op.drop_table("automation_owner", schema="gate")
