"""An answer records the scope it was computed at and the agent that gave it, and a correction is kept.

`0005` built the conversation and its messages and nothing wrote them. Wave 2 files every
exchange from the web and from a chat (M9.1.1, M9.1.2) and lets a person say an answer was wrong
(M9.2.4), and `brain.tables.chat` holds the argument for each column; this is how they arrive.

**Two columns on `chat.message`, each with a default and each checked.** `agent_id`, the agent
that answered, and `ent_hash`, the scope the answer was computed at as
`EntitlementSet.ent_hash`. Both default to the empty string, which is what every row written
before this migration is: a question, or an answer nobody recorded a scope for. The checks
refuse a hash that is not one and refuse either on a question. Neither is added to the
conversation, because a scope there is the shared-transcript column `0005` refuses.

**`chat.correction`, one row per corrected answer.** Keyed to the conversation and the message,
both cascading, with the kind of wrong from `brain.chat.turns.CorrectionKind`, the agent and the
scope copied off the answer, and the identifiers the answer drew on. No owner column: the policy
restricts through the conversation, as `chat.message`'s does, so there is one answer to "whose is
this". SELECT and INSERT only, so a correction is never edited into a different one and never
removed except with the conversation it belongs to.

**The downgrade** drops the table and the two columns, losing what they held, which is the only
reversal a column addition has. The previous release reads neither.

Task ids: M9.1.1, M9.2.4

Revision ID: 0124
Revises: 0120
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0124"
# The newest migration on origin/main when this was written.
down_revision = "0120"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("chat.correction",)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a
#: migration, and held equal to `brain.tables.chat` by `tests/unit/test_conversation_store.py`.
AGENT_ID_CHARS = 60
ENT_HASH_CHARS = 32
ENT_HASH = r"^[0-9a-f]{32}$"
KIND_IN = "kind IN ('misread_question', 'missing', 'stale', 'wrong_fact')"
ENT_HASH_OR_NOTHING = f"ent_hash = '' OR ent_hash ~ '{ENT_HASH}'"
ONLY_AN_ANSWER_HAS_A_SCOPE = "role = 'assistant' OR (agent_id = '' AND ent_hash = '')"

#: The checks the two new message columns carry, as (name, predicate).
MESSAGE_CHECKS: tuple[tuple[str, str], ...] = (
    ("ent_hash_shape", ENT_HASH_OR_NOTHING),
    ("only_an_answer_has_a_scope", ONLY_AN_ANSWER_HAS_A_SCOPE),
)

RLS: tuple[str, ...] = (
    "ALTER TABLE chat.correction ENABLE ROW LEVEL SECURITY",
    # Through the conversation, as `0005` restricts a message, and live conversations only: a
    # retired conversation's corrections go with it.
    """
    CREATE POLICY correction_through_conversation ON chat.correction
        FOR SELECT TO brain_app
        USING (
            EXISTS (
                SELECT 1 FROM chat.conversation c
                WHERE c.id = chat.correction.conversation_id
                  AND c.deleted_at IS NULL
                  AND c.principal_id = current_setting('app.principal_id', true)
            )
        )
    """,
    """
    CREATE POLICY correction_insertable ON chat.correction
        FOR INSERT TO brain_app
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM chat.conversation c
                WHERE c.id = chat.correction.conversation_id
                  AND c.deleted_at IS NULL
                  AND c.principal_id = current_setting('app.principal_id', true)
            )
        )
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a correction is a record of what was said.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON chat.correction TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)

    op.add_column(
        "message",
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False, server_default=""),
        schema="chat",
    )
    op.add_column(
        "message",
        sa.Column("ent_hash", sa.String(ENT_HASH_CHARS), nullable=False, server_default=""),
        schema="chat",
    )
    for name, predicate in MESSAGE_CHECKS:
        op.create_check_constraint(name, "message", predicate, schema="chat")

    op.create_table(
        "correction",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False, server_default=""),
        sa.Column("ent_hash", sa.String(ENT_HASH_CHARS), nullable=False, server_default=""),
        sa.Column(
            "refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["chat.conversation.id"],
            name="fk_correction_conversation_id_conversation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat.message.id"],
            name="fk_correction_message_id_message",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("message_id", name="uq_correction_message_id"),
        sa.CheckConstraint(KIND_IN, name="kind"),
        sa.CheckConstraint("jsonb_typeof(refs) = 'array'", name="refs_is_an_array"),
        sa.CheckConstraint(ENT_HASH_OR_NOTHING, name="ent_hash_shape"),
        schema="chat",
    )
    op.create_index(
        "ix_correction_conversation",
        "correction",
        ["conversation_id", "created_at"],
        schema="chat",
    )

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies, index and grant belong to the table and go with it.
    for qualified in reversed(TABLES):
        schema, _, name = qualified.partition(".")
        op.drop_table(name, schema=schema)
    # The bare names, which the naming convention prefixes as it did when they were created.
    for name, _ in reversed(MESSAGE_CHECKS):
        op.drop_constraint(name, "message", schema="chat", type_="check")
    op.drop_column("message", "ent_hash", schema="chat")
    op.drop_column("message", "agent_id", schema="chat")
