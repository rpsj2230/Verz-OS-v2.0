"""A skill names the departments whose knowledge it needs, and the library keeps them.

M12.3.3 asks that a skill declare the knowledge it needs and that giving it to an agent whose
knowledge scope does not cover the need be refused, saying what is missing. A skill's file had no
place to say it (`brain.tools.skills.Skill.knowledge`), and a stored skill had nowhere to keep it.

**`agent.skill` gains one column.** `knowledge` is a JSON list of department slugs, `NOT NULL` with
an empty list as its default, so every row written before this reads back as the skill it was, its
digest is unchanged (an empty list is left out of the digest), and the release still running during
a deploy inserts without naming the column and is given the default. The check binds only the
column added here, for `brain.deployment.compatibility`'s reason. Nothing else about the table, its
policies or its triggers changes: the application role may insert a row and never update it, so a
need is written once with the bytes it was approved against.

**The downgrade** drops the check and the column. A skill that declared a need loses the
declaration, and its digest then no longer matches the key it was stored under, so it reads as
moved and is not executable, which is the safe way for a downgrade to leave it.

Revises `0213`, the head of main once the Knowledge counts migration lands.

Task ids: M12.3.3

Revision ID: 0214
Revises: 0213
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0214"
# The head of origin/main when this was written; re-pointed when it lands.
down_revision = "0213"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The one check the column carries, as (name, predicate).
KNOWLEDGE_CHECK: tuple[str, str] = ("knowledge_is_a_list", "jsonb_typeof(knowledge) = 'array'")

#: `0056`'s and `0168`'s CREATE TABLE for `agent.skill`, brought up to what this leaves behind, for
#: the comparison with the model. Held to the ALTER the upgrade emits by
#: `tests/unit/test_skill_knowledge.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "escalate_within SMALLINT, CONSTRAINT pk_skill PRIMARY KEY (digest),": (
        "escalate_within SMALLINT, knowledge JSONB DEFAULT '[]'::jsonb NOT NULL, "
        "CONSTRAINT pk_skill PRIMARY KEY (digest),"
    ),
    "CONSTRAINT ck_skill_tools_are_a_list CHECK (jsonb_typeof(tools) = 'array'),": (
        "CONSTRAINT ck_skill_tools_are_a_list CHECK (jsonb_typeof(tools) = 'array'), "
        f"CONSTRAINT ck_skill_{KNOWLEDGE_CHECK[0]} CHECK ({KNOWLEDGE_CHECK[1]}),"
    ),
}


def upgrade() -> None:
    op.add_column(
        "skill",
        sa.Column(
            "knowledge",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="agent",
    )
    # Bare constraint name: alembic applies the naming convention.
    op.create_check_constraint(KNOWLEDGE_CHECK[0], "skill", KNOWLEDGE_CHECK[1], schema="agent")


def downgrade() -> None:
    op.drop_constraint(KNOWLEDGE_CHECK[0], "skill", schema="agent", type_="check")
    op.drop_column("skill", "knowledge", schema="agent")
