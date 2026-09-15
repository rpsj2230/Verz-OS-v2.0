"""A suspended action gets a table an approver reads through row-level security and decides once.

`brain.tables.suspension` holds the argument for the shape. What is here is the table, a view of
the capabilities pending suspensions require, the policies and the grants.

**The read policy narrows on two of `card`'s three questions and leaves the third to it.**
`brain.console.approvals.card` shows a suspension when it is open, when the approver holds the
action's capability, and when the scope they hold it in matches the action's row. The first two
are here: a pending row, whose `required_capability` is in `app.approvable`. The third is not,
because a scope is not a column: it can be unrestricted, it can expire, and a predicate written
here would be a second and different statement of who may approve, which `0041` refuses for the
same reader. So the database never hands an approver a suspension whose capability they do not
hold, and `card` still decides every row the database does hand over.

**`app.approvable` is computed by `EntitlementSet.holds`, never by SQL.** `Capability.covers`
expands a trailing `.*` and an expired principal holds nothing, and restating either in a policy
would be the second implementation CLAUDE.md forbids. So `gate.suspension_capability` lists the
distinct capabilities pending suspensions require, the store asks the reader's reach which of
those it holds, and writes the answer with `set_config(..., true)`. The view shows capability
names and nothing else: no id, no row, no count, and it reaches the application process and never
a person. A setting that is unset or empty admits nothing.

**The principal a suspension runs as reads their own, whatever its state.** A resume is asked by
the run that raised it, after somebody else decided it, and it has to read an approved row that
the approver's clause no longer admits. It is that principal's own action.

**And whoever decided one reads the row they decided.** Not as a courtesy: PostgreSQL holds the
row an UPDATE writes to the SELECT policy as well, so a decided row that its decider could not
read would be refused by the very statement recording the decision. It discloses nothing, since
they wrote it, and `card` still refuses to show a decided suspension to anybody.

**Inserted only as its own principal, pending and undecided.** A request cannot raise a
suspension in somebody else's name, which would put their reach on a card they never raised.

**Decided once, by name.** The update policy admits only a pending row the session may approve,
and checks that the new state is decided and names the session's principal. A decided row is no
longer admitted by that `USING`, so it cannot be decided again, and UPDATE is granted on the
decision columns alone, so the action and its digest cannot be edited by the application role.

**No DELETE.** Nothing for the fast lane role.

The downgrade drops the view and the table and discards every suspension.

Task ids: M35.3.1.1, M33.6.1.3

Revision ID: 0042
Revises: 0041
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.suspension",)

APP_ROLE = "brain_app"

#: `brain.gate.leash.IDENTIFIER` and `brain.gate.leash.DIGEST`, copied rather than imported for
#: the reason `0009` gives: a migration describes the database it built, and one that read live
#: code would stop doing so the day that code changed.
IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"
STATE_IN = "state IN ('approved', 'pending', 'rejected')"
#: `brain.gate.leash.MAX_APPROVAL_WINDOW`, in hours.
MAX_WINDOW_HOURS = 24

#: The setting the store writes: the capabilities, of those pending, that the reader holds.
APPROVABLE = "string_to_array(current_setting('app.approvable', true), ',')"
PRINCIPAL = "current_setting('app.principal_id', true)"

VIEW = """
    CREATE VIEW gate.suspension_capability AS
        SELECT DISTINCT required_capability
        FROM gate.suspension
        WHERE state = 'pending'
"""

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.suspension ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY suspension_readable ON gate.suspension
        FOR SELECT TO brain_app
        USING (
            principal_id = {PRINCIPAL}
            OR decided_by = {PRINCIPAL}
            OR (state = 'pending' AND required_capability = ANY ({APPROVABLE}))
        )
    """,
    f"""
    CREATE POLICY suspension_raised_by_its_principal ON gate.suspension
        FOR INSERT TO brain_app
        WITH CHECK (
            principal_id = {PRINCIPAL} AND state = 'pending' AND decided_by IS NULL
        )
    """,
    f"""
    CREATE POLICY suspension_decided_once_by_the_session ON gate.suspension
        FOR UPDATE TO brain_app
        USING (state = 'pending' AND required_capability = ANY ({APPROVABLE}))
        WITH CHECK (state <> 'pending' AND decided_by = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON gate.suspension TO brain_app",
    "GRANT UPDATE (state, decided_by, decided_at, updated_at) ON gate.suspension TO brain_app",
    "GRANT SELECT ON gate.suspension_capability TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "suspension",
        sa.Column("id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("required_capability", sa.String(200), nullable=False),
        sa.Column("action", postgresql.JSONB(), nullable=False),
        sa.Column("ent_hash", sa.String(128), nullable=False),
        sa.Column("artefact", sa.String(8000), nullable=False),
        sa.Column("action_digest", sa.String(64), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), server_default="pending", nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"id ~ '{IDENTIFIER_PATTERN}'", name="id_is_an_identifier"),
        sa.CheckConstraint(f"trace_id ~ '{IDENTIFIER_PATTERN}'", name="trace_id_is_an_identifier"),
        sa.CheckConstraint(
            f"principal_id ~ '{IDENTIFIER_PATTERN}'", name="principal_id_is_an_identifier"
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER_PATTERN}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(
            "length(btrim(required_capability)) > 0", name="an_action_requires_something"
        ),
        sa.CheckConstraint("length(btrim(ent_hash)) > 0", name="a_reach_was_recorded"),
        sa.CheckConstraint("length(artefact) > 0", name="something_was_shown"),
        sa.CheckConstraint(f"action_digest ~ '{DIGEST_PATTERN}'", name="action_digest_shape"),
        sa.CheckConstraint(STATE_IN, name="state"),
        sa.CheckConstraint("expires_at > raised_at", name="a_window_ends_after_it_opens"),
        sa.CheckConstraint(
            f"expires_at - raised_at <= interval '{MAX_WINDOW_HOURS} hours'",
            name="a_window_is_bounded",
        ),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (state = 'pending')",
            name="only_a_decided_suspension_names_its_decider",
        ),
        schema="gate",
    )
    op.create_index(
        "ix_suspension_pending_capability",
        "suspension",
        ["required_capability"],
        schema="gate",
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.execute(VIEW)
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the table; the view has to go first.
    op.execute("DROP VIEW gate.suspension_capability")
    op.drop_table("suspension", schema="gate")
