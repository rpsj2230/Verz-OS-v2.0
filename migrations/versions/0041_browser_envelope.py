"""A sealed browser envelope gets a table the approval queue reads and only its asker writes.

`brain.tables.browsing` holds the argument for the shape: the permitted parts of an envelope and
their digest, and the approval's state, window, decider and time, with the verdict's reason in
the ledger. What is here is the table, its three policies and its grants.

**`USING (true)` on the read, for the reason `0038` gives, and the reader is again one whose
reach is decided in Python.** An approver is offered an envelope by
`brain.console.role_surfaces.pending_for`, which asks their live `EntitlementSet` for the write
capability in a scope matching the target. A scope is not a column: it can be unrestricted, it
can expire, and a predicate written here would be a second and different statement of who may
approve. The row holds no goal text and nothing read from a page, only which surfaces, verbs,
counts and origins a run was permitted and who asked, which is what the card shows.

**An envelope is inserted only as its own asker.** The insert policy checks `asked_by` against
`app.principal_id`, so a request cannot seal an envelope in somebody else's name, which would put
their reach on a card they never raised.

**A decision moves a pending row and names the session's principal as the decider.** The update
policy admits only a pending row and checks `decided_by` against `app.principal_id`, so the name
on a decision is the name of whoever made the connection, and a decided row cannot be decided
again. UPDATE is granted on the decision columns alone, so what was sealed cannot be edited by
the application role at all; a superuser who edits it anyway leaves a row whose digest no longer
matches, and `brain.browsing.envelope_store` refuses it on read.

**No DELETE.** A sealed envelope is the record of what a run was permitted. Nothing for the fast
lane role.

The downgrade drops the table and discards every sealed envelope.

Task ids: M19.2.3

Revision ID: 0041
Revises: 0040
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.browser_envelope",)

APP_ROLE = "brain_app"

#: `brain.gate.leash.IDENTIFIER`, `brain.browsing.targets.NAME_RE` and `brain.gate.leash.DIGEST`,
#: copied rather than imported for the reason `0009` gives: a migration describes the database it
#: built, and one that read live code would stop doing so the day that code changed.
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
SLUG_PATTERN = "^[a-z][a-z0-9_]*$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"
STATE_IN = "approval_state IN ('approved', 'pending', 'rejected')"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.browser_envelope ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY browser_envelope_readable ON agent.browser_envelope
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY browser_envelope_sealed_by_its_asker ON agent.browser_envelope
        FOR INSERT TO brain_app
        WITH CHECK (asked_by = current_setting('app.principal_id', true))
    """,
    """
    CREATE POLICY browser_envelope_decided_by_the_session ON agent.browser_envelope
        FOR UPDATE TO brain_app
        USING (approval_state = 'pending')
        WITH CHECK (decided_by = current_setting('app.principal_id', true))
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.browser_envelope TO brain_app",
    "GRANT UPDATE (approval_state, decided_by, decided_at, updated_at) "
    "ON agent.browser_envelope TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "browser_envelope",
        sa.Column("run_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("asked_by", sa.String(128), nullable=False),
        sa.Column("envelope_digest", sa.String(64), nullable=False),
        sa.Column("sealed", postgresql.JSONB(), nullable=False),
        sa.Column("approval_state", sa.String(16), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"run_id ~ '{IDENTIFIER_PATTERN}'", name="run_id_is_an_identifier"),
        sa.CheckConstraint(f"target ~ '{SLUG_PATTERN}'", name="target_is_a_slug"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="an_agent_runs_it"),
        sa.CheckConstraint("length(btrim(asked_by)) > 0", name="somebody_asked"),
        sa.CheckConstraint(f"envelope_digest ~ '{DIGEST_PATTERN}'", name="envelope_digest_shape"),
        sa.CheckConstraint(STATE_IN, name="approval_state"),
        sa.CheckConstraint(
            "(approval_state IS NULL) = (raised_at IS NULL) "
            "AND (raised_at IS NULL) = (expires_at IS NULL)",
            name="an_approval_is_raised_with_a_window",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > raised_at", name="a_window_ends_after_it_opens"
        ),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (approval_state IS NULL OR approval_state = 'pending')",
            name="only_a_decided_approval_names_its_decider",
        ),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the table.
    op.drop_table("browser_envelope", schema="agent")
