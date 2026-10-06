"""The install acceptance check for a file attached to a conversation, read by the registered tool.

One check, over the product's own pieces inside the check's transaction (M12.3.6). Two people of
acceptance_a who both read knowledge. The first adds a document at their own level through the
upload route's sequence, which makes it a document only they may read, and attaches it to a new
thread of theirs through `POST /threads/attachments`'s own function, called as the threads check
calls the thread routes. The tool is the one `brain.tools.startup.build_registry` registers on this
install, called as the gate calls it.

**What is checked.**
- Read by the tool as the person who attached it, the file's passages come back, word for word.
- Read as the other person, the same reference answers nothing, and the route refuses to attach it
  to a thread of theirs with the same 404 as a document that does not exist.
- Read as the first person, a second document of theirs that is not attached answers nothing,
  even when an answer in the same thread drew on it, so the tool reads attachments and is not a
  second way to read any document.

**No model is run.** The leaf is about the tool and the reach it is read at, which is what an agent
is handed; that the answer lane tells a selected agent what is attached is its second half, and
comes with the attach control on Ask.

Task ids: M12.3.6
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from brain.core.entitlement import EntitlementSet
    from brain.core.envelope import TypedResult
    from brain.knowledge.document_tools import KnowledgePassage

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 245

A, _ = RESERVED_DEPARTMENTS


@check(
    leaves=("M12.3.6",),
    sentence=(
        "A document one person adds at their own level and attaches to their thread is read by "
        "the registered attachment tool at their reach, word for word; read as a colleague it "
        "answers nothing and cannot be attached by them, and an unattached document of the "
        "first person's answers nothing either."
    ),
)
async def an_attached_file_is_read_at_its_owner_s_reach_and_by_nobody_else(
    h: Harness,
) -> None:
    from brain.chat.attachments import READ_ATTACHMENT, AttachmentRead
    from brain.core.errors import Absent
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.acceptance_threads import _asking, _request, _web
    from brain.thread_routes import AttachAsked, attach_to_my_thread
    from brain.tools.startup import build_registry

    await h.found_departments()
    owner, colleague = h.principal(A, "attacher"), h.principal(A, "colleague")
    await h.person(owner, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(colleague, department=A, grants=_in(A, *KNOWLEDGE_READS))

    async def personal(word: str) -> str:
        read = await _upload(
            h,
            owner,
            filename="Acceptance attachment.md",
            declared=MediaType.MARKDOWN.value,
            body=a_markdown_document("Acceptance attachment", f"This file says {word}."),
            level=Visibility.PERSONAL,
        )
        if isinstance(read, ParseFailure):
            raise CheckFailedError("a well-formed Markdown document could not be added")
        return str(read.item.item_id)

    word, other = h.word(), h.word()
    attached, unattached = await personal(word), await personal(other)
    app = await _web(h)
    kept = await attach_to_my_thread(
        _request(app), await _asking(h, owner), AttachAsked(attachment_id=attached)
    )
    if kept.attachment_id != attached or not kept.thread_id:
        raise CheckFailedError("a document its owner may read was not attached to their thread")

    records = SessionRowSource(h.sessions)
    tool = build_registry(source=h.settings.tool_source, records=records).get(READ_ATTACHMENT)
    owning, other_one = await h.reach(owner), await h.reach(colleague)

    # The registry keeps a handler as an untyped callable; this is the one it registered.
    handler = cast("Callable[..., Awaitable[TypedResult[KnowledgePassage]]]", tool.handler)

    async def read_as(reach: EntitlementSet, document: str) -> str:
        result = await handler(AttachmentRead(attachment_id=document), entitlement=reach, now=h.now)
        return " ".join(one.document for one in result.records)

    # An answer in the same thread that drew on the unattached document, which cites it and does
    # not attach it.
    from brain.chat.thread_store import Exchange, StoredThreads
    from brain.chat.turns import RecordRef
    from brain.gate.context import Channel
    from brain.knowledge.search import KNOWLEDGE_READ

    await StoredThreads(h.sessions).record(
        owner,
        thread_id=kept.thread_id,
        channel=Channel.CONSOLE,
        exchange=Exchange(
            question="What does my other file say?",
            answer="It says what it says.",
            refs=(RecordRef(entity="knowledge", record_id=unattached, required=KNOWLEDGE_READ),),
        ),
        now=h.now,
    )

    if word not in await read_as(owning, attached):
        raise CheckFailedError("the attached file was not read at its owner's reach")
    if await read_as(other_one, attached):
        raise CheckFailedError("a file somebody else attached was read by a colleague")
    try:
        await attach_to_my_thread(
            _request(app), await _asking(h, colleague), AttachAsked(attachment_id=attached)
        )
    except Absent:
        pass
    else:
        raise CheckFailedError("a colleague attached another person's own document to a thread")
    if await read_as(owning, unattached):
        raise CheckFailedError("the attachment tool read a document nobody attached")
