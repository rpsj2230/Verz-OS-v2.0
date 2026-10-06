"""A file attached to a person's own conversation, and the tool an agent reads it with (M12.3.6).

The first half runs anywhere: the reference an attachment is kept as reads back through the
threads loader as a reference and never as an unreadable list, the tool is declared on the
document plane under the capability that reads documents, and a template's `knowledge.read`
binds it beside `knowledge.read_document`. The second builds PostgreSQL to head and attaches
through the thread store as the application role: one note per document per thread, and an id
that is not the person's opens a thread of their own.

Task ids: M12.3.6
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from brain.agents.install import bind_tool
from brain.chat.attachments import (
    ATTACHED,
    ATTACHMENT_ENTITY,
    READ_ATTACHMENT,
    attached_reference,
    attachment_definition,
)
from brain.chat.thread_store import StoredThreads
from brain.chat.threads import refs_from_json
from brain.core.envelope import SideEffect
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, READ_DOCUMENT
from brain.knowledge.search import KNOWLEDGE_READ
from tests.unit.test_acceptance import at_head

#: Far outside any plausible wall clock. See CLAUDE.md on a fixture with a date in it.
NOW = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
DOCUMENT = "doc_0123456789abcdef"


def test_an_attachment_is_kept_as_a_reference_the_thread_reads_back() -> None:
    """The note's one reference is the document, under the document plane's entity and the
    capability that reads documents, and the threads loader reads it as a reference. Delete this
    and an attachment can be stored in a shape the loader calls unreadable, which hides the whole
    thread's history after the first attachment."""
    (ref,) = refs_from_json(attached_reference(DOCUMENT)) or ()

    assert (ref.entity, ref.record_id, ref.required) == (
        KNOWLEDGE_ENTITY,
        DOCUMENT,
        KNOWLEDGE_READ,
    )
    assert ATTACHMENT_ENTITY == KNOWLEDGE_ENTITY


def test_the_tool_reads_on_the_document_plane_and_changes_nothing() -> None:
    """Declared with the capability every document read needs and no side effect. Delete this and
    the tool can be declared under a capability nobody holds, or as an effect a leash holds for a
    person, and an agent can never read what its asker attached."""
    definition = attachment_definition()

    assert definition.name == READ_ATTACHMENT
    assert definition.entity == KNOWLEDGE_ENTITY
    assert definition.required_capability == KNOWLEDGE_READ.value
    assert definition.side_effect is SideEffect.NONE


def test_an_agent_that_reads_documents_is_bound_to_read_attachments_too() -> None:
    """A template declaring `knowledge.read` binds the attachment tool beside the document reader,
    so every agent trusted to read documents reads what its asker attached. Delete this and an
    entity of its own can return, leaving every existing agent unable to read an attachment."""
    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import build_registry

    registry = build_registry(source="demo", records=SessionRowSource(None))  # type: ignore[arg-type]

    assert set(bind_tool("knowledge.read", registry).bound) == {READ_DOCUMENT, READ_ATTACHMENT}


@pytest.mark.needs_db
def test_a_document_is_attached_once_to_the_person_s_own_thread_or_a_new_one() -> None:
    """Attached twice to one thread, one note is kept; attached naming a thread that is not the
    person's, a thread of their own is opened rather than the other's being written to. Delete
    this and a retried attach fills a thread with notes, or an id typed into a request writes into
    somebody else's history."""
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_suspension_store import app_engine

    with at_head("brain_chat_attachments") as url:

        async def work() -> tuple[str, str, str]:
            # The application role, so row-level security decides whose thread an id is.
            engine = app_engine(url)
            try:
                store = StoredThreads(make_session_factory(engine))
                first = await store.attach("u_one", thread_id=None, attachment_id=DOCUMENT, now=NOW)
                again = await store.attach(
                    "u_one", thread_id=first, attachment_id=DOCUMENT, now=NOW
                )
                other = await store.attach(
                    "u_two", thread_id=first, attachment_id=DOCUMENT, now=NOW
                )
                return first, again, other
            finally:
                await engine.dispose()

        first, again, other = asyncio.run(work())
        notes = sql(
            url,
            "SELECT c.principal_id, m.conversation_id::text FROM chat.message m "
            "JOIN chat.conversation c ON c.id = m.conversation_id WHERE m.body = %s "
            "ORDER BY c.principal_id",
            ATTACHED,
        )

    assert first == again != other
    assert notes == [("u_one", first), ("u_two", other)]


def test_the_question_asks_for_the_caller_s_own_attachment_notes_alone() -> None:
    """**Structure, not text nearby.** The compiled statement selects from the caller's own
    conversations by principal, only system notes whose words are the attachment note, and only a
    note whose references contain this document. Row-level security already hides another
    person's conversations from a source that runs as the application role; the principal is in
    the statement as well so a source that set nothing still finds nothing of anybody else's.
    Delete this and the question can widen to any conversation, or to an answer that merely cited
    the document."""
    from sqlalchemy.dialects import postgresql

    from brain.chat.attachments import attached_query

    query = attached_query(DOCUMENT, principal_id="u_one", settings=())
    compiled = query.statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    where = str(query.statement.whereclause)
    values = {one for one in compiled.params.values() if isinstance(one, str)}

    assert "chat.conversation.principal_id = " in where
    assert "chat.message.role = " in where
    assert "chat.message.body = " in where
    assert "chat.message.refs @> " in where
    assert {"u_one", "system", ATTACHED} <= values


def test_a_caller_who_reads_no_knowledge_is_answered_with_nothing_and_asks_nothing() -> None:
    """Without the read that documents need there is no reach, and the tool answers nothing before
    any conversation or document is asked about. Delete this and a caller holding nothing has a
    question built for them from a reach that does not exist."""
    from brain.chat.attachments import AttachmentRead, attachment_reader
    from brain.core.entitlement import EntitlementSet
    from brain.core.envelope import TypedResult
    from brain.knowledge.document_tools import KnowledgePassage

    asked: list[str] = []

    class Rows:
        async def rows(self, query: object) -> list[dict[str, str]]:
            asked.append(getattr(query, "entity", ""))
            return [{"slug": "sales"}] if getattr(query, "entity", "") == "department" else []

    read = attachment_reader(Rows())

    async def ask() -> TypedResult[KnowledgePassage]:
        return await read(
            AttachmentRead(attachment_id=DOCUMENT),
            entitlement=EntitlementSet(principal_id="u_nobody", grants=()),
            now=NOW,
        )

    found = asyncio.run(ask())

    assert found.records == ()
    assert asked == ["department"]
