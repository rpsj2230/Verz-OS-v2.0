"""An answer in a thread names the agent that gave it, the request it answered and how it ended.

`chat.message` held what was said and what an answer drew on, and nothing about who answered or
whether the run finished. So an agent's page could not list the conversations it took part in,
`brain.chat.turns.Turn.agent_id` was always empty when read back from a table, and a run that failed
left nothing at all in the asker's thread. `brain.tables.chat.MessageRow` argues the three columns
and `brain.tables.chat.RunState` the vocabulary.

**Three nullable columns on answers only.** Every answer written before this recorded no agent and
no run, and a default would be a value nobody measured; three checks keep all three off a question
and off a system note, because a run state there would say a run happened where none did. Each is
written `<column> IS NULL OR ...`, so a row the previous release writes during a rolling deploy,
which never sets these columns, is never refused.

**An index on the agent and the time**, so an agent's conversations are found without reading every
message on the install. Row-level security still decides whose conversations those are: a message is
reachable only through its conversation, which is its owner's (`0005`).

**The downgrade drops the index, the checks and the columns**, and what they held goes with them.

Written over 0150, main's newest migration when this was written; whoever lands it re-points
`down_revision` to main's head then and nothing else.

Task ids: M39.8.9

Revision ID: 0161
Revises: 0150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0161"
down_revision = "0150"
branch_labels = None
depends_on = None

#: Widths and the vocabulary copied for the reason `0009` gives, and held equal to
#: `brain.tables.chat` by `tests/unit/test_thread_runs.py`.
AGENT_ID_CHARS = 60
TRACE_ID_CHARS = 64
RUN_STATE_CHARS = 16
#: `brain.tables.chat.RUN_CHECKS`, each `<column> IS NULL OR ...`, so no row the previous release
#: writes is refused by one: it never sets these columns.
RUN_CHECKS: dict[str, str] = {
    "run_state_on_an_answer": (
        "run_state IS NULL OR (role = 'assistant' AND "
        "run_state IN ('abstained', 'answered', 'degraded', 'failed'))"
    ),
    "agent_on_an_answer": "agent_id IS NULL OR role = 'assistant'",
    "trace_on_an_answer": "trace_id IS NULL OR role = 'assistant'",
}

#: `0005`'s CREATE TABLE for messages as it would read today, for the comparison with the model.
#: Held to the ALTERs the upgrade emits by `tests/unit/test_thread_runs.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "refs JSONB DEFAULT '[]'::jsonb NOT NULL, created_at": (
        "refs JSONB DEFAULT '[]'::jsonb NOT NULL, "
        f"agent_id VARCHAR({AGENT_ID_CHARS}), trace_id VARCHAR({TRACE_ID_CHARS}), "
        f"run_state VARCHAR({RUN_STATE_CHARS}), created_at"
    ),
    "CONSTRAINT ck_message_refs_is_an_array CHECK (jsonb_typeof(refs) = 'array'),": (
        "CONSTRAINT ck_message_refs_is_an_array CHECK (jsonb_typeof(refs) = 'array'), "
        + "".join(
            f"CONSTRAINT ck_message_{name} CHECK ({condition}), "
            for name, condition in RUN_CHECKS.items()
        ).rstrip(" ")
    ),
}


def upgrade() -> None:
    op.add_column(
        "message", sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=True), schema="chat"
    )
    op.add_column(
        "message", sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=True), schema="chat"
    )
    op.add_column(
        "message",
        sa.Column("run_state", sa.String(RUN_STATE_CHARS), nullable=True),
        schema="chat",
    )
    op.create_check_constraint(
        "run_state_on_an_answer", "message", RUN_CHECKS["run_state_on_an_answer"], schema="chat"
    )
    op.create_check_constraint(
        "agent_on_an_answer", "message", RUN_CHECKS["agent_on_an_answer"], schema="chat"
    )
    op.create_check_constraint(
        "trace_on_an_answer", "message", RUN_CHECKS["trace_on_an_answer"], schema="chat"
    )
    op.create_index("ix_message_agent", "message", ["agent_id", "created_at"], schema="chat")


def downgrade() -> None:
    op.drop_index("ix_message_agent", table_name="message", schema="chat")
    op.drop_constraint("trace_on_an_answer", "message", type_="check", schema="chat")
    op.drop_constraint("agent_on_an_answer", "message", type_="check", schema="chat")
    op.drop_constraint("run_state_on_an_answer", "message", type_="check", schema="chat")
    op.drop_column("message", "run_state", schema="chat")
    op.drop_column("message", "trace_id", schema="chat")
    op.drop_column("message", "agent_id", schema="chat")
