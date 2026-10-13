"""An agent is set up with which of five kinds of memory it may read and write.

The owner decided on needs item 180 (2026-10-12, option B) that memory is told apart in five kinds,
as the task for it says: the conversation, the task, the project, the person and the agent's own,
and that an agent is configured with the kinds it may read and write (M39.7.1). `agent.agent` gains
`memory_kinds`, and a run cannot read a kind its configuration leaves out
(`brain.gate.turn_context.assemble`).

**One column, all five by default.** Every agent that exists keeps what it remembers the day this
lands; the setting only ever removes. A check holds the array inside the five names and nothing
else, so a kind nobody declared is refused by the database and not left for the next reader to
meet. An empty array is legal and is an agent that remembers nothing.

**A change reaches the ledger from the row, the way a connector does.** `0196`'s trigger function
writes one `compose_change` entry for each connector added to or taken from an agent's list; this
replaces it with the same function and a second branch of the same shape for the memory kinds, so a
kind switched on or off is one entry naming who, when, which kind and the direction, attributed
exactly as every other agent change is. The branch is `0196`'s own text with the column and the part
changed, read from that migration rather than copied beside it, so the append, the attribution and
the order of the existing branches cannot drift from what `0196` argues.

**The downgrade** puts `0196`'s function back and drops the column. A kind somebody left out is then
read again by every agent, which is the state an install downgraded past this is in anyway.

Task ids: M39.7.1

Revision ID: 0225
Revises: 0224
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic import op

revision = "0225"
down_revision = "0224"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`.
TABLES: tuple[str, ...] = ()

#: The five kinds on the day this ran, sorted, written out as data because a migration says what it
#: did on the day it ran. Held equal to `brain.agents.memory_kinds.MemoryKind` by a test.
KINDS: tuple[str, ...] = ("conversation", "own", "person", "project", "task")

#: The widest kind is seven characters. Held equal to `brain.tables.agent.MEMORY_KIND_CHARS`.
KIND_CHARS = 16

#: The default: every kind.
ALL_KINDS_DEFAULT = "'{" + ",".join(KINDS) + "}'"

#: `memory_kinds` holds only the five names. `<@` is array containment, as in `0014`'s
#: `required_tools <@ allowed_tools`, and the right side is cast so both sides are one type.
KNOWN = "memory_kinds <@ ARRAY[" + ", ".join(f"'{one}'" for one in KINDS) + "]::character varying[]"

#: The place `0196` ends its function and so where the new branch goes.
RETURNS = "    RETURN NULL;\nEND;"


def _earlier(name: str) -> ModuleType:
    """A migration beside this one, read live for the reason `0190` gives."""
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(f"m_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def memory_branch(connectors_branch: str) -> str:
    """`0196`'s connectors branch, over the memory kinds: the column and the part changed."""
    assert "OLD.connectors IS DISTINCT FROM NEW.connectors" in connectors_branch
    return (
        connectors_branch.replace("OLD.connectors", "OLD.memory_kinds")
        .replace("NEW.connectors", "NEW.memory_kinds")
        .replace("'part', 'connector'", "'part', 'memory'")
    )


def replaced(function: str, branch: str) -> str:
    """`0196`'s function with the memory branch before it returns, and nothing else changed."""
    assert function.count(RETURNS) == 1, "0196's function no longer has one RETURN to branch before"
    return function.replace(RETURNS, branch + RETURNS, 1)


def function_with_memory() -> str:
    tools = _earlier("0196_tool_attachments.py")
    return replaced(tools.AGENT_TRIGGER_FUNCTION, memory_branch(tools.CONNECTOR_BRANCH)).replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
    )


def upgrade() -> None:
    op.add_column(
        "agent",
        sa.Column(
            "memory_kinds",
            sa.ARRAY(sa.String(KIND_CHARS)),
            nullable=False,
            server_default=sa.text(ALL_KINDS_DEFAULT),
        ),
        schema="agent",
    )
    op.create_check_constraint("memory_kinds_known", "agent", KNOWN, schema="agent")
    op.execute(function_with_memory())


def downgrade() -> None:
    tools = _earlier("0196_tool_attachments.py")
    op.execute(
        tools.AGENT_TRIGGER_FUNCTION.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    )
    op.drop_constraint("memory_kinds_known", "agent", schema="agent", type_="check")
    op.drop_column("agent", "memory_kinds", schema="agent")
