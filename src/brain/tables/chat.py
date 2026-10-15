"""Conversations and the messages in them.

**A transcript is a record of what was shown, and never a source the system answers from.**
That single sentence is the whole design, and the two halves pull in opposite directions.

The person who asked already saw the answer, so keeping it and letting them read it back
takes nothing from anybody: deleting their history when a grant is revoked would be
theatre, since they read it at the time. But a *follow-up* must not draw on it, because by
then the grant may be gone and a model told "the client is Acme" does not stop to ask
whether it still may know that. `brain.chat.turns.context_for` is the enforcement of the
second half; this module is the storage that makes the first half safe.

**A conversation belongs to exactly one principal, and there is no column that could make it
belong to two.** No `team_id`, no `department`, no `shared_with`. That is the M9.1.3 rule -
"conversation search restricted to the asker" - written as a schema rather than as a WHERE
clause somebody has to remember. A shared transcript is one person's answers, produced at
their reach, readable by somebody with a different reach; the two people never see the same
system, so the sharing is a leak with a friendly name on it.

**Thread continuity is per conversation, not per channel (M9.1.2).** A question asked in the
console and followed up in Lark is one thread, so `channel` lives on the message and not on
the conversation. Putting it on the conversation would make continuing elsewhere a new
thread, and a person would lose their own context by switching app - or, worse, somebody
would add a lookup that stitches threads together by principal and time, which is a join
that guesses.

**A message stores what was shown and the identifiers behind it.** `refs` is jsonb holding
entity and record ids only, never values: it is what `RecordRef` carries, and the reason is
the same. A copy of a record still reads perfectly after the grant behind it is revoked; an
identifier yields nothing when it is re-checked.

**What is deliberately absent.** No embedding column, and that is not an oversight to fix
later. Making transcripts searchable by similarity means one person's phrasing of a question
pulls up another person's conversation in a nearest-neighbour scan, and a vector index does
not carry a principal. If conversation search across people is ever wanted, it is a feature
with its own permission model, not a column added here.

**An answer records the scope it was computed at and the agent that gave it (`0124`).** The
scope is `EntitlementSet.ent_hash`, the fingerprint the answer cache and the ledger already key
on, so it identifies a reach and discloses none of it. It sits on the message and never on the
conversation, because a scope on the conversation is the shared-transcript column refused
above. A question carries neither, and the table refuses one that does.

**A correction is a row of its own, `chat.correction`, and never an edit of the answer.** One
per answer, keyed to the message it corrects and restricted through the conversation like a
message is. It holds the kind of wrong, the agent and the scope copied off the answer, and the
identifiers the answer drew on: the shape of the disagreement and never what the right answer
is. See `brain.chat.turns.Correction`.

Task ids: M9.1.1, M9.1.2, M9.1.3, M9.1.4, M9.2.4
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.audit.ledger import ENT_HASH
from brain.chat.turns import CorrectionKind
from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.tables.audit import ENT_HASH_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Long enough for a real title and short enough that it is a title. Titles are generated
#: from the first question, so this is a truncation point rather than a limit somebody hits.
TITLE_CHARS = 200

#: A channel name, as `brain.gate.context.Channel` spells it. Stored as text rather than as
#: a foreign key to an enum table: the set is closed in code, and a table would let a
#: channel exist in the database that no code path can produce.
CHANNEL_CHARS = 32


class MessageRole(enum.StrEnum):
    """Who said it. Closed, and the members are not interchangeable.

    `SYSTEM` is separate from `ASSISTANT` because a system note - "this conversation was
    exported", "an approval expired" - is not something the assistant said, and folding the
    two would make the transcript claim the assistant said things nobody wrote.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


#: An entitlement hash, or nothing. The ledger's grammar, so the two columns hold one kind of value.
ENT_HASH_OR_NOTHING = f"ent_hash = '' OR ent_hash ~ '{ENT_HASH}'"

#: A question is the person's own words and was computed at no reach and by no agent.
ONLY_AN_ANSWER_HAS_A_SCOPE = (
    f"role = '{MessageRole.ASSISTANT.value}' OR (agent_id = '' AND ent_hash = '')"
)


class ConversationRow(TimestampMixin, SoftDeleteMixin, Base):
    """`chat.conversation`. One thread, owned by one person (M9.1.1).

    `principal_id` is the owner and it is not nullable. A conversation with no owner is a
    conversation no row-level security policy can restrict, which is the one shape this
    table must not be able to hold.

    Not a foreign key to `auth.principal`, for the reason `CapabilityGrantRow.granted_by`
    gives: a transcript has to outlive the account that produced it, or an offboarding
    deletes the record of what was asked - which is exactly the record somebody wants after
    an offboarding.
    """

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint(_present("principal_id"), name="owned"),
        # Live rows only. A retired conversation keeps its title; the index exists so a
        # person's conversation list is a single index scan on the one column every query
        # here filters by.
        Index(
            "ix_conversation_owner_live",
            "principal_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "chat"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    #: The one person this belongs to. There is no second column that could widen it, and
    #: `tests/unit/test_chat_tables.py` fails on one being added.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    #: Generated from the first question, so a list of conversations reads as a list of
    #: questions. Nullable: a conversation exists from the moment it is opened, and the
    #: title arrives with the first message.
    title: Mapped[str | None] = mapped_column(String(TITLE_CHARS), nullable=True)


class MessageRow(TimestampMixin, Base):
    """`chat.message`. One turn, in whichever channel it happened in (M9.1.2).

    No soft delete, unlike almost everything else here. A message that can be hidden makes
    the transcript a thing somebody can edit the meaning of by removal, and a transcript
    that can be edited is not worth keeping. A conversation is retired as a whole or not at
    all.
    """

    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint(one_of("role", MessageRole), name="role"),
        CheckConstraint(_present("channel"), name="channel_present"),
        # `refs` holds identifiers and never values. A check cannot prove that, so it
        # asserts the shape it can: an array, so a caller cannot put a record object in it
        # and have it read as a reference list later.
        CheckConstraint("jsonb_typeof(refs) = 'array'", name="refs_is_an_array"),
        CheckConstraint(ENT_HASH_OR_NOTHING, name="ent_hash_shape"),
        CheckConstraint(ONLY_AN_ANSWER_HAS_A_SCOPE, name="only_an_answer_has_a_scope"),
        Index("ix_message_conversation", "conversation_id", "created_at"),
        {"schema": "chat"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    #: Cascades on delete, and this is the one foreign key here. A message without its
    #: conversation is a fragment nothing can restrict: the owner is on the conversation, so
    #: an orphaned message is a row row-level security cannot reason about.
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat.conversation.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Where this turn happened. On the message rather than the conversation, so a thread
    #: continued in another app is the same thread.
    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)

    #: What was said or shown. For an assistant turn this is the rendered answer, locks
    #: included, exactly as the asker saw it - the transcript is a record of what was shown.
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    #: Entity and record identifiers the answer drew on. Never values. See the module
    #: docstring, and `brain.chat.turns.RecordRef`, which is the same rule in the type.
    refs: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    #: Which agent answered, or empty. What a correction copies, so "which agent is corrected
    #: most" is read off the answer rather than off whatever the person said (`0124`).
    agent_id: Mapped[str] = mapped_column(
        String(AGENT_ID_CHARS), nullable=False, server_default=""
    )

    #: The scope the answer was computed at, as `EntitlementSet.ent_hash`, or empty for a
    #: question. A fingerprint: it identifies a reach and names nothing in it (`0124`).
    ent_hash: Mapped[str] = mapped_column(String(ENT_HASH_CHARS), nullable=False, server_default="")


class CorrectionRow(Base):
    """`chat.correction`. A person saying one answer was wrong (M9.2.4, `0124`).

    No owner column, for the reason `MessageRow` has none: the owner is on the conversation,
    and a second copy of "whose is this" is a second answer the day the two disagree. The
    policy restricts through the conversation, and the store checks the message is an answer
    in that same conversation before it writes.

    One per answer. A second press is the same statement again, and the signal counts answers
    that were wrong rather than how often somebody said so.

    No `updated_at` and no soft delete: SELECT and INSERT only, so a correction is a record of
    what was said and cannot be edited into a different one.
    """

    __tablename__ = "correction"
    __table_args__ = (
        CheckConstraint(one_of("kind", CorrectionKind), name="kind"),
        CheckConstraint("jsonb_typeof(refs) = 'array'", name="refs_is_an_array"),
        CheckConstraint(ENT_HASH_OR_NOTHING, name="ent_hash_shape"),
        UniqueConstraint("message_id"),
        Index("ix_correction_conversation", "conversation_id", "created_at"),
        {"schema": "chat"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat.conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The answer corrected. Cascades with it, which nothing does, since nothing deletes one.
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat.message.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Copied off the answer by `brain.chat.turns.record_correction`, never supplied.
    agent_id: Mapped[str] = mapped_column(
        String(AGENT_ID_CHARS), nullable=False, server_default=""
    )
    #: The scope the corrected answer was computed at, copied off it.
    ent_hash: Mapped[str] = mapped_column(String(ENT_HASH_CHARS), nullable=False, server_default="")
    #: What the corrected answer drew on, so a reviewer can look at the same records.
    refs: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
