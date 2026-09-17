"""The application's warnings and errors get a table the Logs screen reads, row-level security on.

`brain.tables.application_log` holds the argument for the columns, `brain.ops.log_capture` for what
a row may carry, and `brain.ops.log_store` for how rows arrive and leave. What is here is the DDL,
the policies and the grant.

**SELECT, INSERT and DELETE, and never UPDATE.** A log row is a fact about a moment and is never
edited. It leaves by age through the retention sweep, which `brain.ops.retention_store` removes only
from a table the application role may delete from, and by volume through the store's ceiling, so
DELETE is granted where most tables in this schema withhold it. The absent UPDATE grant is the
refusal of an edit, since PostgreSQL denies what no grant admits.

**`USING (true)` is not an absence of a permission check.** Who may read the log is a console
question, decided against the reader's live grants by `brain.log_routes.may_read_application_log`
before any statement is built, which is `0052`'s and `0053`'s shape for a table the console
narrows. Nothing on a row names a person, so there is no row a policy could admit to one reader and
refuse to another.

**Chained to 0062 and dependent on nothing any earlier migration builds**, so a change landing
between the two re-chains `down_revision` and nothing else.

**The downgrade drops the table**, and every kept warning with it. The container's standard output
is unaffected either way.

Task ids: M27.8.14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("obs.application_log",)

APP_ROLE = "brain_app"

#: Widths and bounds copied for the reason `0009` gives about reading live code from a migration:
#: `brain.ops.log_capture.MAX_EVENT_CHARS` and `MAX_ORIGIN_CHARS`, and
#: `brain.tables.application_log`'s `TRACE_ID_CHARS`, `ERROR_TYPE_CHARS` and `MAX_FIELDS_BYTES`.
EVENT_CHARS = 160
ORIGIN_CHARS = 200
TRACE_ID_CHARS = 64
ERROR_TYPE_CHARS = 80
MAX_FIELDS_BYTES = 4096

#: `brain.ops.log_capture.LogLevel`, sorted as `one_of` sorts.
LEVEL_IN = "level IN ('critical', 'error', 'info', 'warning')"

RLS: tuple[str, ...] = (
    "ALTER TABLE obs.application_log ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY application_log_visible ON obs.application_log
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: SELECT, INSERT and DELETE, and never UPDATE. See the module docstring.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT, DELETE ON obs.application_log TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "application_log",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("event", sa.String(EVENT_CHARS), nullable=True),
        sa.Column("origin", sa.String(ORIGIN_CHARS), nullable=True),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=True),
        sa.Column("error_type", sa.String(ERROR_TYPE_CHARS), nullable=True),
        sa.Column("repeats", sa.Integer(), nullable=False),
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(LEVEL_IN, name="level"),
        sa.CheckConstraint("repeats >= 1", name="repeats_positive"),
        sa.CheckConstraint("last_at >= at", name="last_not_before_first"),
        sa.CheckConstraint("jsonb_typeof(fields) = 'object'", name="fields_object"),
        sa.CheckConstraint(
            f"octet_length(fields::text) <= {MAX_FIELDS_BYTES}", name="fields_bounded"
        ),
        schema="obs",
    )
    op.create_index("ix_application_log_at", "application_log", ["at", "id"], schema="obs")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policy, the grant and the index go with the table.
    op.drop_table("application_log", schema="obs")
