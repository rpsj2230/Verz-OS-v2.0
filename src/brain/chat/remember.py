"""What an answered question leaves in its asker's thread: the words shown, and what they stood on.

`brain.chat.thread_store` writes rows and `brain.chat.threads` reads them back at the reach held
at the time. Between the two sits one decision, taken here: what an answer drew on, as references
a later reader can be re-checked against. An answer is the words the person was shown, exactly as
a text channel shows them, and its references are the records and passages its citations name,
each with the capability that was needed to read it.

**A reference carries the field's own capability, never only the record's.** A cited field is
read under its column's rule, so an answer quoting a cost was shown to somebody holding the cost
grant, and shown again only to somebody who still does. Recording the table's capability instead
would show the cost again after the column grant was revoked and the table grant kept. A field no
policy classifies is recorded under a column capability named for it, which nobody is granted
unless somebody writes that rule, so such an answer is not shown again, failing closed. See
`A_CITED_FIELD_IS_RE_CHECKED_UNDER_ITS_OWN_RULE`.

**A cited passage is re-checked under the document's text capability**, which is what reading a
passage needs (`brain.gate.model_lane.PASSAGE_POLICY`), and is recorded by its chunk, which is what
a follow-up in the same thread re-reads under the reach held then (M9.2.3).

**What is not recorded, and why.** A referred question: see `brain.chat.thread_store`. A window's
refusal: nothing was answered. A cache hit: recorded with its words and with references the reader
refuses, so the question stays in the thread and the answer is never shown again; see
`brain.chat.thread_store.AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_NEVER_SHOWN_AGAIN`. An abstention
drew on nothing and is recorded with no references.

Task ids: M9.1.1, M9.1.2, M9.2.3
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from brain.chat.thread_store import Exchange, StoredThreads
from brain.chat.turns import RecordRef
from brain.core.entitlement import Capability
from brain.core.field_policy import FieldPolicy
from brain.gate.answer import Answered
from brain.gate.context import Channel
from brain.gate.model_lane import PASSAGE_POLICY
from brain.gate.provenance import DOCUMENT_KIND, RECORD_KIND
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY

#: The passage policy, keyed as the answer route keys an entity's.
PASSAGES: Final[Mapping[str, FieldPolicy]] = {KNOWLEDGE_ENTITY: PASSAGE_POLICY}

#: Why a cited field keeps its own capability on the reference.
A_CITED_FIELD_IS_RE_CHECKED_UNDER_ITS_OWN_RULE: Final = (
    "An answer quoting a field was shown to somebody holding that field's grant, so it is shown "
    "again only to somebody who still does. The record's capability alone would re-show a cost "
    "after the cost grant was revoked and the table grant kept. A field no rule classifies is "
    "recorded under a column capability nobody is granted, so its answer is not shown again."
)


def refs_of(
    answered: Answered, policies: Mapping[str, FieldPolicy]
) -> tuple[RecordRef, ...] | None:
    """What an answer drew on, or None when it was not recorded. See the module docstring."""
    if answered.from_cache:
        return None
    if answered.provenance is None:
        return ()
    found: dict[tuple[str, str, str], RecordRef] = {}
    for evidence in answered.provenance.evidence:
        view = evidence.view()
        kind = view.get("kind", "")
        if kind == RECORD_KIND:
            entity, record_id, field = view["entity"], view["record_id"], view["field"]
            required = _field_capability(entity, field, policies)
        elif kind == DOCUMENT_KIND:
            # The passage cited, by its chunk, which is what a follow-up re-reads (M9.2.3).
            entity, record_id = KNOWLEDGE_ENTITY, chunk_of(view)
            required = _field_capability(KNOWLEDGE_ENTITY, "document", PASSAGES)
        else:
            # A citation of a shape this build does not write. Unknown sources: not shown again.
            return None
        one = RecordRef(entity=entity, record_id=record_id, required=required)
        found.setdefault((one.entity, one.record_id, one.required.value), one)
    return tuple(found.values())


def chunk_of(view: Mapping[str, str]) -> str:
    """The chunk a document citation's anchor names, or the document when it names none."""
    anchor = view.get("anchor", "")
    first = anchor.split("&", 1)[0]
    chunk = first.removeprefix("chunk=") if first.startswith("chunk=") else ""
    return chunk or view["document_id"]


def _field_capability(entity: str, field: str, policies: Mapping[str, FieldPolicy]) -> Capability:
    """The capability a field is read under, from the policy classifying its entity."""
    policy = policies.get(entity)
    rule = None if policy is None else policy.rule_for(entity, field)
    if rule is not None:
        return rule.required_capability
    return Capability(value=f"read:{entity}.{field}")


def exchange_of(
    question: str, answered: Answered, policies: Mapping[str, FieldPolicy]
) -> Exchange | None:
    """The exchange an answered question leaves in its thread, or None when it leaves none."""
    if answered.referred:
        return None
    # Read lazily: `brain.chat_answer` imports the answer route, which imports this module.
    from brain.chat_answer import chat_text

    return Exchange(
        question=question,
        answer=chat_text(answered),
        refs=refs_of(answered, policies),
        escalated=answered.escalated,
    )


async def remember(
    threads: StoredThreads | None,
    *,
    principal_id: str,
    thread_id: str | None,
    channel: Channel,
    question: str,
    answered: Answered,
    policies: Mapping[str, FieldPolicy],
    now: datetime,
    trace_id: str | None = None,
) -> str | None:
    """Write this exchange to the person's thread, and say which thread; None when none was.

    `trace_id` is the request it was answered on, which the learning signals the exchange is
    evidence of name (M16.2.8).
    """
    if threads is None:
        return None
    exchange = exchange_of(question, answered, policies)
    if exchange is None:
        return None
    return await threads.record(
        principal_id,
        thread_id=thread_id,
        channel=channel,
        exchange=exchange,
        now=now,
        trace_id=trace_id,
    )


def threads_of(state: Any) -> StoredThreads | None:
    """The thread store over this process's database, or None on a process with none."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessions = getattr(state, "db_sessions", None)
    return StoredThreads(sessions) if isinstance(sessions, async_sessionmaker) else None
