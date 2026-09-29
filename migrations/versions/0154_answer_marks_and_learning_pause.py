"""A helpful or unhelpful mark on an answer, and a switch that pauses what an agent's runs teach.

Two rows the learning loop needed and nothing kept. `brain.tables.learning_signal` holds the
argument for each column.

**`mem.mark`**: one row per mark a person puts on one of their own answers, naming the answer by
the trace it ran under, whether it helped, who marked it and when. **No free text and no answer**:
a mark is a pointer at the trace and one bit, for `brain.ops.feedback`'s reason about a box beside
an answer being where the answer gets pasted. A later mark by the same person on the same answer
is a new row, and the latest is theirs; nothing is updated.

**`agent.learning_pause`**: one row per time somebody paused or resumed what one agent's runs may
teach, with who, when and why. Where an agent stands is read off its latest row, and an agent with
no row learns as it always has. A pause only ever stops formation, so a row here can narrow what is
learned and never widen it.

**SELECT and INSERT only, written in the session's own name**, `0149`'s shape: a mark names its
marker and a pause its setter as `app.principal_id`, and a row naming anybody else is refused.
Nothing is updated to say what happened, so neither table needs a ledger trigger to be its own
history: the rows are the record, with their author and their instant, and nothing may delete one.

**Each row is stamped with `statement_timestamp()`, not `now()`.** The latest row is the one that
counts, and `now()` is when the transaction began, so a pause and a resume written in one
transaction would tie and either could be read as the latest; the statement's own instant orders
them as they were written, which is
`brain.ops.memory_store.A_REVISION_IS_STAMPED_WHEN_IT_IS_DECIDED`.

**The downgrade drops both tables.** A mark changes nothing by itself, and a pause dropped leaves
every agent learning as it did before the pause, which is the state an install downgraded past this
migration is in anyway.

Task ids: M16.7.4, M16.7.13, M16.6.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0154"
down_revision = "0150"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. Neither points
#: at anything: a mark names a trace and a pause an agent by value, so each outlives what it names.
TABLES: tuple[str, ...] = (
    "mem.mark",
    "agent.learning_pause",
)

APP_ROLE = "brain_app"

#: Widths copied for the reason `0009` gives about reading live code from a migration, and held
#: equal to `brain.tables.learning_signal` by `tests/unit/test_learning_signal.py`.
TRACE_ID_CHARS = 64
PRINCIPAL_ID_CHARS = 128
AGENT_ID_CHARS = 60
REASON_CHARS = 400

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE mem.mark ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.learning_pause ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY mark_readable ON mem.mark
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY mark_made_in_the_sessions_name ON mem.mark
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
    """
    CREATE POLICY learning_pause_readable ON agent.learning_pause
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY learning_pause_set_in_the_sessions_name ON agent.learning_pause
        FOR INSERT TO brain_app
        WITH CHECK (set_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a new mark and a resume are new rows.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON mem.mark TO brain_app",
    "GRANT SELECT, INSERT ON agent.learning_pause TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "mark",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column(
            "marked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="trace_present"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        schema="mem",
    )
    op.create_index("ix_mem_mark_trace_id", "mark", ["trace_id"], schema="mem")
    op.create_table(
        "learning_pause",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=False),
        sa.Column("set_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        sa.CheckConstraint("length(btrim(set_by)) > 0", name="set_by_present"),
        schema="agent",
    )
    op.create_index(
        "ix_agent_learning_pause_agent_id_at",
        "learning_pause",
        ["agent_id", "at"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the tables.
    op.drop_table("learning_pause", schema="agent")
    op.drop_table("mark", schema="mem")
