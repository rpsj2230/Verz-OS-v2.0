"""A question's retrieval reaches the learning signal's record, and nothing else of it does.

The pure half of `brain.knowledge.retrieval_log`: a search notes only into a request that collects,
the record counts the passages the person was shown and the corroborated ones among them alone, and
the passage search notes which of its retrievers ran and which passages two of them agreed on. The
searcher is driven through `tests/unit/test_document_tools.py`'s recording row source, so the
statements are the real ones and only the database is stood in.

Task ids: M15.3.4
"""

from __future__ import annotations

import asyncio

import pytest

from brain.knowledge import retrieval_log
from brain.knowledge.quality import QualityError, RetrievalEvent
from brain.knowledge.retrieval_log import Searched, collected, event_for, note
from brain.knowledge.search import LEXICAL_RETRIEVER, VECTOR_RETRIEVER
from tests.unit.test_document_tools import (
    READER,
    Embedding,
    Recording,
    body,
    search,
    search_embedding,
)

SEARCHED = Searched(
    retrievers=(VECTOR_RETRIEVER, LEXICAL_RETRIEVER),
    corroborated=frozenset({"c_2", "c_9"}),
    latency_ms=12,
)


def test_the_record_counts_what_was_shown_and_the_corroboration_among_it_alone() -> None:
    """Three passages shown, one of them corroborated; a corroborated passage the person was not
    shown counts for nothing; the retrievers are sorted; the last search of a request is the one
    recorded. Delete this and a passage the redactor dropped can be counted, which is a count of
    something the person was not shown."""
    earlier = Searched(retrievers=(LEXICAL_RETRIEVER,), corroborated=frozenset(), latency_ms=1)
    event = event_for([earlier, SEARCHED], ["c_1", "c_2", "c_3", "c_2"])

    assert event == RetrievalEvent(
        retrievers=(LEXICAL_RETRIEVER, VECTOR_RETRIEVER),
        returned=3,
        corroborated=1,
        latency_ms=12,
    )
    assert event_for([], ["c_1"]) is None
    assert event_for([SEARCHED], []) == RetrievalEvent(
        retrievers=(LEXICAL_RETRIEVER, VECTOR_RETRIEVER), returned=0, latency_ms=12
    )


def test_a_search_notes_only_into_a_request_that_collects() -> None:
    """`ONLY_A_RETRIEVAL_SOMEBODY_COULD_FOLLOW_IS_LOGGED`: noted outside `collected`, a search
    lands nowhere; inside, it lands in that block's list and in no other. Delete this and a check's
    or a chat's search is logged as a retrieval nobody used."""
    note(SEARCHED)
    with collected() as outer:
        note(SEARCHED)
        with collected() as inner:
            note(SEARCHED)
        note(SEARCHED)
    note(SEARCHED)

    assert (len(outer), len(inner)) == (2, 1)


def test_the_record_refuses_a_retriever_outside_its_grammar() -> None:
    """The record's own validation still stands behind `event_for`, the positive case above
    beside it. Delete this and a name that would split on the separator could be stored."""
    with pytest.raises(QualityError):
        event_for([Searched(retrievers=("Lexical",), corroborated=frozenset(), latency_ms=0)], [])


def test_the_passage_search_notes_the_retrievers_that_ran_and_what_two_agreed_on() -> None:
    """Text search alone notes the lexical retriever; with an embedder the vector retriever too,
    and the passage both legs found is the corroborated one. Delete this and the signal's
    corroboration is always nought, or names a retriever that did not run."""
    passages = (
        body("c_leave_1", "doc_leave", 0, "Annual leave is 25 days."),
        body("c_leave_2", "doc_leave", 1, "Carry over up to five days."),
    )
    with collected() as lexical_only:
        search(Recording(ranked=[("c_leave_1", "c_leave_2")], bodies=passages), "leave", READER)
    with collected() as both:
        search_embedding(
            Recording(ranked=[("c_leave_1", "c_leave_2")], nearest=("c_leave_1",), bodies=passages),
            "leave",
            READER,
            Embedding(),
        )

    [plain] = lexical_only
    assert (plain.retrievers, plain.corroborated) == ((LEXICAL_RETRIEVER,), frozenset())
    [hybrid] = both
    assert hybrid.retrievers == (LEXICAL_RETRIEVER, VECTOR_RETRIEVER)
    assert hybrid.corroborated == frozenset({"c_leave_1"})
    assert event_for(both, ["c_leave_1", "c_leave_2"]) == RetrievalEvent(
        retrievers=(LEXICAL_RETRIEVER, VECTOR_RETRIEVER),
        returned=2,
        corroborated=1,
        latency_ms=hybrid.latency_ms,
    )


def test_latency_is_whole_milliseconds_and_never_negative() -> None:
    """`elapsed_ms` from `started`. Delete this and a clock read the wrong way round stores a
    negative duration the record refuses, failing the answer's logging."""
    since = retrieval_log.started()
    assert retrieval_log.elapsed_ms(since) >= 0
    assert retrieval_log.elapsed_ms(since + 3600) == 0


def test_the_collector_is_the_requests_own_across_tasks() -> None:
    """Two requests collecting at once each see their own searches, because the collector is a
    context variable and each task runs in a copy of the context. Delete this and one person's
    retrieval can be recorded against another's answer."""

    async def one_request(n: int) -> int:
        with collected() as mine:
            for _ in range(n):
                note(SEARCHED)
                await asyncio.sleep(0)
        return len(mine)

    async def both() -> list[int]:
        return list(await asyncio.gather(one_request(1), one_request(3)))

    assert asyncio.run(both()) == [1, 3]


def test_a_cited_passage_carries_its_place_in_the_list_the_person_was_shown() -> None:
    """`trace_of` places each cited passage by where it sat in the payload, so a passage that could
    not be cited as a document leaves a gap rather than shifting the ones after it, and the
    evidence view sends the place as text. Delete this and a followed citation's place is its
    place among citations, which is a different list from the one the retrieval was logged over."""
    from datetime import UTC, datetime

    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.redaction import ChannelPayload
    from brain.core.scope import Scope
    from brain.gate.model_lane import trace_of
    from brain.gate.provenance import SEED_HORIZONS, document_evidence

    payload = ChannelPayload(
        records=(
            {"entity": "knowledge", "id": "c_a_1", "document_id": "doc_a"},
            {"entity": "knowledge", "id": "c_b_1"},
            {"entity": "knowledge", "id": "c_c_1", "document_id": "doc_c"},
        )
    )
    reach = EntitlementSet(
        principal_id="u_reader",
        grants=(Grant(capability=Capability(value="read:knowledge"), scope=Scope()),),
    )
    trace = trace_of(payload, reach=reach)

    assert [(one.document_id, one.position) for one in trace.passages] == [
        ("doc_a", 1),
        ("doc_c", 3),
    ]
    views = document_evidence(
        trace, horizon=SEED_HORIZONS.documents, now=datetime(2019, 1, 1, tzinfo=UTC)
    )
    assert [one.view()["position"] for one in views] == ["1", "3"]
