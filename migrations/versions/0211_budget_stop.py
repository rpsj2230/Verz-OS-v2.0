"""Every budget that was used up, and whether the install stopped it or only said it would have.

`ops.budget_stop`, one row per ceiling per period that ran out. `brain.ops.budget_stop` decided on
2026-09-15 what follows a budget being used up (the owner's warning, then a stop until the next
period) and nothing could record either, so ceilings were stored and never enforced. This is the
record. `brain.tables.budget_stop` holds the argument for each column.

**One row per ceiling per period, and per whether it was enforced.** The unique key is the
ceiling's key, the instant its period ends and `enforced`, so the first request that finds a budget
used up opens the row and every later one finds it there. `enforced` is false while
`budget_enforcement` is switched off: the row then says the install would have stopped, which is
the evidence the owner decides the switch on. Switching it on during a period opens the enforced
row beside the one that was only said.

**Ids and the ceiling's key, and nothing a request said.** The principal and the trace of the
request that found the budget used up, and who the warning was addressed to, as principal ids.
No question, no figure and no amount: how much was spent is the spend ledger's, behind the Spend
screen's own grant.

**SELECT and INSERT only, written in the session's own name**, `0188`'s shape. A stop ends when
its period does, so nothing updates a row, and nothing may delete one: the rows are their own
history and need no ledger trigger.

The downgrade drops the table. A budget that stopped being enforced was always one the ceiling
rows still describe.

Task ids: M27.12.5, M27.7.15

Revision ID: 0211
Revises: 0189
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0211"
# main's head at the time of writing. Re-pointed at whichever migration is the head when it lands.
down_revision = "0189"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the ceiling, the principal and the
#: recipients are values, so a stop's row outlives a ceiling's next version and a person leaving.
TABLES: tuple[str, ...] = ("ops.budget_stop",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.budget_stop`, which takes them from the tables they name.
SUBJECT_CHARS = 128
PRINCIPAL_ID_CHARS = 128
TRACE_ID_CHARS = 64
VOCABULARY_CHARS = 16

#: `BudgetLevel`, the periods that roll (`brain.ops.budget_stop.WINDOWS`) and `Addressing`, on the
#: day this ran.
LEVELS: tuple[str, ...] = ("agent", "company", "department", "user")
PERIODS: tuple[str, ...] = ("day", "month")
ADDRESSING: tuple[str, ...] = ("escalated", "own_admin", "unaddressed")

PRINCIPAL = "current_setting('app.principal_id', true)"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.budget_stop ENABLE ROW LEVEL SECURITY",
    # Read by the request path for whoever is asking, and by the Spend screen for its reader, so
    # who may be told of a stop is decided where it is shown rather than here.
    """
    CREATE POLICY budget_stop_readable ON ops.budget_stop
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY budget_stop_written_in_the_sessions_name ON ops.budget_stop
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.budget_stop TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "budget_stop",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("level", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("subject", sa.String(SUBJECT_CHARS), nullable=False),
        sa.Column("period", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enforced", sa.Boolean(), nullable=False),
        sa.Column("addressing", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column(
            "addressed_to",
            sa.ARRAY(sa.String(PRINCIPAL_ID_CHARS)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_one_of("level", LEVELS), name="level"),
        sa.CheckConstraint(_one_of("period", PERIODS), name="period"),
        sa.CheckConstraint(_one_of("addressing", ADDRESSING), name="addressing"),
        sa.CheckConstraint("length(btrim(subject)) > 0", name="subject_present"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="trace_present"),
        sa.CheckConstraint("until > since", name="ends_after_it_starts"),
        sa.CheckConstraint(
            "(addressing = 'unaddressed') = (cardinality(addressed_to) = 0)",
            name="addressed_to_somebody_or_said_to_nobody",
        ),
        sa.UniqueConstraint(
            "level", "subject", "period", "until", "enforced", name="one_stop_per_period"
        ),
        schema="ops",
    )
    op.create_index("ix_ops_budget_stop_until", "budget_stop", ["until"], schema="ops")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("budget_stop", schema="ops")
