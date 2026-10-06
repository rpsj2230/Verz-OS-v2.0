"""A file a person attached to their own conversation, and the one tool an agent reads it with.

M12.3.6 asks that an agent read a file a person attached to the conversation, through a registered
tool, at that person's reach, and never a file somebody else attached. Every part of that but the
attaching already existed. An upload at a person's own level (`brain.knowledge_routes.upload`) is a
document only they may read, and `knowledge.read_document` reads one document at its caller's
reach. What nothing did was tie a document to a conversation, or give an agent a tool that reads
the files of the conversation it is answering in and nothing else.

**An attachment is a reference on the conversation, not a copy.** `StoredThreads.attach` writes a
system note into the person's own thread whose one reference is the document, under
`ATTACHMENT_ENTITY` and the capability that reads documents, so it is re-checked on every later
turn like every other reference (`brain.chat.turns.RecordRef`). The file is the knowledge item the
upload made, kept and governed where every document is. No table is added, because
`chat.message.refs` already holds identifiers and never values.

**The tool reads an attachment only of the caller's own conversations, and only at their reach.**
`chat.read_attachment` asks, as the caller, whether any conversation of theirs names the document
as an attachment, then reads it through `knowledge.read_document`'s own reader at the same reach.
Two walls, each enough alone: the chat tables' row-level security shows a person their own
conversations only, so a file somebody else attached is named by nothing the caller can see; and a
file uploaded at its owner's own level is a document only its owner reaches. An attachment the
caller cannot read is answered exactly as one that does not exist. See
`AN_AGENT_READS_ONLY_WHAT_ITS_CALLER_ATTACHED_AND_ONLY_AT_THEIR_REACH`.

**It is bound wherever an agent reads documents.** Its entity is the document plane's, so a
template that declares `knowledge.read` binds it beside `knowledge.read_document`
(`brain.agents.install.bind_tool`): an agent trusted to read documents reads the ones its asker
attached, under the same capability and the same leash target. Rejected: an entity of its own,
which would leave every existing agent unable to read an attachment until each template was
edited, and would put the same read under two supervision targets.

Task ids: M12.3.6
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import TextClause

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.knowledge.document_tools import (
    KNOWLEDGE_ENTITY,
    MAX_PASSAGES,
    DocumentRead,
    KnowledgePassage,
    reach_through,
    reader,
)
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.rows import RowQuery, RowSource
from brain.knowledge.search import KNOWLEDGE_READ, session_settings
from brain.tables.chat import ConversationRow, MessageRole, MessageRow

#: Why the tool reads only the caller's own attachments, at their reach.
AN_AGENT_READS_ONLY_WHAT_ITS_CALLER_ATTACHED_AND_ONLY_AT_THEIR_REACH: Final = (
    "A file attached to a conversation is the person's, given to answer their question. An agent "
    "answering them reads it at their reach, through the reader every document goes through, and "
    "only when a conversation of theirs names it; a file somebody else attached is named by "
    "nothing they can see and is answered as one that does not exist."
)

#: What an attachment's reference is called: the document plane's own entity.
ATTACHMENT_ENTITY: Final = KNOWLEDGE_ENTITY

#: The system note an attachment is kept as. The words carry no name and no content; the
#: reference beside it is the document.
ATTACHED: Final = "A file was attached to this conversation."

#: The tool's registered name.
READ_ATTACHMENT: Final = "chat.read_attachment"

READ_ATTACHMENT_DESCRIPTION: Final = (
    "Read the passages of one file the person you are answering attached to their conversation, "
    "by its reference, in reading order"
)


class AttachmentRead(BaseModel):
    """One attached file, by the reference the conversation holds for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attachment_id: str = Field(pattern=ITEM_ID_PATTERN)
    limit: int = Field(default=MAX_PASSAGES, ge=1, le=MAX_PASSAGES)


def attached_reference(attachment_id: str) -> list[dict[str, str]]:
    """The reference list an attachment's note holds, in `refs_as_json`'s shape."""
    return [
        {
            "entity": ATTACHMENT_ENTITY,
            "record_id": attachment_id,
            "required": KNOWLEDGE_READ.value,
        }
    ]


def attached_query(
    attachment_id: str, *, principal_id: str, settings: tuple[TextClause, ...]
) -> RowQuery:
    """Whether any conversation of this person's names this document as an attachment.

    Filtered by the person as well as by the row-level security the settings raise, so a
    connection that set nothing still finds nothing of anybody else's.
    """
    statement = (
        sa.select(MessageRow.id.label("message_id"))
        .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
        .where(
            ConversationRow.principal_id == principal_id,
            MessageRow.role == MessageRole.SYSTEM.value,
            MessageRow.body == ATTACHED,
            MessageRow.refs.contains([{"entity": ATTACHMENT_ENTITY, "record_id": attachment_id}]),
        )
        .limit(1)
    )
    return RowQuery(
        entity=ATTACHMENT_ENTITY,
        source="chat",
        columns=("message_id",),
        statement=statement,
        certainly_empty=False,
        settings=settings,
    )


def attachment_reader(
    records: RowSource,
) -> Callable[..., Awaitable[TypedResult[KnowledgePassage]]]:
    """The handler for `chat.read_attachment`, bound to where conversations and chunks are read.

    See `AN_AGENT_READS_ONLY_WHAT_ITS_CALLER_ATTACHED_AND_ONLY_AT_THEIR_REACH`.
    """
    read_document = reader(records)

    async def read(
        request: AttachmentRead,
        *,
        entitlement: EntitlementSet,
        now: datetime | None = None,
    ) -> TypedResult[KnowledgePassage]:
        reach = await reach_through(records, entitlement, now)
        nothing = TypedResult[KnowledgePassage](records=(), source=KNOWLEDGE_ENTITY)
        if reach is None:
            return nothing
        named = await records.rows(
            attached_query(
                request.attachment_id,
                principal_id=entitlement.principal_id,
                settings=session_settings(reach),
            )
        )
        if not named:
            return nothing
        return await read_document(
            DocumentRead(document_id=request.attachment_id, limit=request.limit),
            entitlement=entitlement,
            now=now,
        )

    return read


def attachment_definition() -> ToolDefinition:
    """What the registry describes for `chat.read_attachment`."""
    return ToolDefinition(
        name=READ_ATTACHMENT,
        description=READ_ATTACHMENT_DESCRIPTION,
        entity=ATTACHMENT_ENTITY,
        args_schema=AttachmentRead.model_json_schema(),
        required_capability=KNOWLEDGE_READ.value,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.SERVICE,
    )
