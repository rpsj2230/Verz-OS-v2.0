"""An agent's channels switched by its steward or an administrator reach the ledger.

`0189` gave `agent.agent` its channels (M13.7.4) and `brain.agent_lifecycle_routes` now switches
them for an agent's steward or an administrator over its row. `0137`'s trigger records an agent's
lifecycle and audience and nothing else, so a channel switched on or off would have stopped at the
row: who made an agent answerable on WhatsApp, and when, would have had a last answer and no
history. This replaces that trigger's function with the same function and one more branch:
`channels_changed`, when the stored list moves, attributed exactly as every other agent change is.

**The function is `0137`'s own text, read from that migration and changed in one place**, rather
than a copy of eighty lines of PL/pgSQL beside it, so the append, the attribution and the order of
the existing branches cannot drift from what `0137` argues. The new branch sits after the audience
branch, so an update moving both writes them in that order.

**The details are the change and nothing else**, `0137`'s rule: the row holds the channels now and
the entry says who changed them and when. Naming the channels in the entry would put a second copy
of a configuration value in the chain for every switch.

The downgrade puts `0137`'s function back, after which a switch reaches the row and not the ledger,
which is the state an install downgraded past this migration is in anyway.

Task ids: M13.7.4

Revision ID: 0190
Revises: 0189
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`.
TABLES: tuple[str, ...] = ()

#: The change word, `brain.audit.record.AgentChange.CHANNELS_CHANGED`, copied for the reason `0009`
#: gives about reading live code from a migration, and held equal by a test.
CHANNELS_CHANGED = "channels_changed"

#: Where the new branch goes: just before the actor of an update is decided, after every branch
#: `0137` writes.
BEFORE = "        v_actor := COALESCE(v_supplied, session_user::text);"

BRANCH = f"""        IF OLD.channels IS DISTINCT FROM NEW.channels THEN
            v_changes := v_changes || '{CHANNELS_CHANGED}'::text;
        END IF;
"""


def _lifecycle_audit() -> ModuleType:
    """`0137`, read from beside this file."""
    path = Path(__file__).with_name("0137_agent_lifecycle_audit.py")
    spec = importlib.util.spec_from_file_location("m0137_agent_lifecycle_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replaced(function: str) -> str:
    """`0137`'s function, replaceable, and with the channels branch before the actor is decided."""
    assert function.count(BEFORE) == 1, "0137's function no longer has the line the branch follows"
    return function.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1).replace(
        BEFORE, BRANCH + BEFORE, 1
    )


def upgrade() -> None:
    op.execute(replaced(_lifecycle_audit().AGENT_TRIGGER_FUNCTION))


def downgrade() -> None:
    original = _lifecycle_audit().AGENT_TRIGGER_FUNCTION
    op.execute(original.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
