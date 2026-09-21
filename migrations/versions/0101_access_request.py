"""A request for access is stored and addressed to the person who can decide it.

**`gate.access_request` is new** (M4.3.4, M2.2.4): one row per request, naming a locked field on
an entity or a department an answer said was out of reach, the question in the asker's words, the
capability that would answer it and the owner it is addressed to. `brain.tables.access_request`
argues the shape. The owner reads their own requests on the console's Access requests screen,
which is how a request is delivered; the asker is told one constant sentence whatever happened.

**SELECT and INSERT, and no UPDATE or DELETE**: a request is a record that it was made, and the
decision is a grant written elsewhere. **`USING (true)`**: the one reader is
`brain.ops.access_request_store.addressed_to`, which selects by the caller's own principal id, and
the one writer is the route that composed the notice.

**The downgrade** drops the table and every request in it, which is the state before this release:
nothing was stored. No check is re-created, so nothing is narrowed on rows already written.

Task ids: M4.3.4, M2.2.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0101"
# The head of origin/main when this was written.
down_revision = "0100"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.access_request",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.access_request` by `tests/unit/test_tables.py`.
PRINCIPAL_ID_CHARS = 128
NAME_CHARS = 120
SLUG_CHARS = 60
QUESTION_CHARS = 2000
CAPABILITY_CHARS = 200
NAME_PATTERN = "^[a-z][a-z0-9_]*$"
CAPABILITY_PATTERN = r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*|\.\*)*$"
ONE_SUBJECT = (
    "(entity IS NOT NULL AND field IS NOT NULL AND department IS NULL) OR "
    "(entity IS NULL AND field IS NULL AND department IS NOT NULL)"
)

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON gate.access_request TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.access_request ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY access_request_readable ON gate.access_request
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY access_request_recordable ON gate.access_request
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "access_request",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("asker_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("owner_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("entity", sa.String(NAME_CHARS), nullable=True),
        sa.Column("field", sa.String(NAME_CHARS), nullable=True),
        sa.Column("department", sa.String(SLUG_CHARS), nullable=True),
        sa.Column("question", sa.String(QUESTION_CHARS), nullable=False),
        sa.Column("requested_capability", sa.String(CAPABILITY_CHARS), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(ONE_SUBJECT, name="one_subject"),
        sa.CheckConstraint(f"entity IS NULL OR entity ~ '{NAME_PATTERN}'", name="entity_name"),
        sa.CheckConstraint(f"field IS NULL OR field ~ '{NAME_PATTERN}'", name="field_name"),
        sa.CheckConstraint(
            f"department IS NULL OR department ~ '{NAME_PATTERN}'", name="department_name"
        ),
        sa.CheckConstraint("length(btrim(question)) >= 1", name="question_present"),
        sa.CheckConstraint(
            f"requested_capability ~ '{CAPABILITY_PATTERN}'", name="requested_capability_grammar"
        ),
        schema="gate",
    )
    op.create_index(
        "ix_gate_access_request_owner_id", "access_request", ["owner_id"], schema="gate"
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The index, the policies and the grant go with the table.
    op.drop_table("access_request", schema="gate")
