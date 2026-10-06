"""The document plane's retrieval and embedding caches, through a row source that records.

Over `brain.knowledge.document_tools` with the caches `brain.cache` builds on a running install
replaced by a dictionary, so what is asked of the row source on a hit and on a miss can be read
back. The stand-in source cannot evaluate SQL, so what a statement admits is asserted on the
compiled statement, as `tests/unit/test_document_tools.py` does.

Task ids: M6.2.3, M6.2.4
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.scope import Scope
from brain.gate.caches import CachedEmbedding, CachedRetrieval
from brain.knowledge.document_tools import (
    A_CACHED_RETRIEVAL_IS_RE_READ_UNDER_THE_CALLERS_REACH,
    PASSAGE_COLUMNS,
    DocumentSearch,
    KnowledgePassage,
    QuestionEmbedder,
    searcher,
)
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import KNOWLEDGE_READ, Reach, lexical_legs, reach_predicate
from tests.unit.test_document_tools import (
    A_REVISION,
    NOW,
    POSTGRES,
    UPDATED,
    Embedding,
    Recording,
    body,
    holding,
    rendered,
    settle,
)


@dataclass
class Kept[T]:
    """A cache as a dictionary, remembering what it was asked to keep and for how long."""

    held: dict[str, T] = field(default_factory=dict)
    lifetimes: dict[str, int] = field(default_factory=dict)

    def get(self, key: str) -> T | None:
        return self.held.get(key)

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self.held[key] = value
        self.lifetimes[key] = ttl_seconds


class Corpus(Recording):
    """`Recording`, also answering the corpus query with `passages` seen and one change time."""

    def __init__(self, *, passages: int = 1, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.passages = passages

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        if query.columns == ("policy_epoch", "passages", "changed"):
            self.asked.append(query)
            return [{"policy_epoch": 3, "passages": self.passages, "changed": UPDATED}]
        return await super().rows(query)

    def rankings(self) -> list[RowQuery]:
        return [one for one in self.asked if one.columns == ("chunk_id", "relevance")]

    def bodies_asked(self) -> list[RowQuery]:
        return [one for one in self.asked if one.columns == PASSAGE_COLUMNS]


LEAVE = body("c_leave_1", "doc_leave", 0, "Leave is booked a week ahead.")


def asked(
    source: Corpus,
    kept: Kept[CachedRetrieval],
    entitlement: EntitlementSet,
    question: str = "leave",
    *,
    limit: int = 5,
) -> TypedResult[KnowledgePassage]:
    handler = searcher(source, None, kept)
    request = DocumentSearch(question=question, limit=limit)
    return settle(handler(request, entitlement=entitlement, now=NOW))


def legs(question: str = "leave") -> int:
    return len(lexical_legs(question))


# ------------------------------------------------------------------ the retrieval (M6.2.3)
def test_a_search_asked_again_is_ranked_once_and_its_bodies_read_both_times() -> None:
    """**What the cache is for, and what it must not save.** The second asking skips the ranking
    legs and still asks for the bodies, and hands back the same passages. Delete this and the
    cache can be wired so that it saves nothing, or so that it saves the read it must not."""
    source = Corpus(ranked=[("c_leave_1",)] * legs(), bodies=(LEAVE,))
    kept: Kept[CachedRetrieval] = Kept()

    first = asked(source, kept, holding(KNOWLEDGE_READ.value))
    second = asked(source, kept, holding(KNOWLEDGE_READ.value))

    assert [one.id for one in first.records] == [one.id for one in second.records] == ["c_leave_1"]
    assert len(source.rankings()) == legs()
    assert len(source.bodies_asked()) == 2
    assert [one.chunk_ids for one in kept.held.values()] == [("c_leave_1",)]


def test_a_cached_list_is_re_read_under_the_callers_reach_and_only_that_read_is_handed_back() -> (
    None
):
    """**The property that matters most.** On a hit the bodies are fetched by the statement that
    carries the caller's reach and the settings the second wall reads, and what is handed back is
    what that read returned now, not what the list named: a passage the caller has since lost is
    gone, even though the cached list still names it. Delete this and a cached list of references
    becomes a way to read a passage after the reach that found it was taken away."""
    web = holding(KNOWLEDGE_READ.value, scope=Scope.department("web"))
    reach = Reach(principal_id="u_reader", departments=("web",))
    source = Corpus(ranked=[("c_leave_1",)] * legs(), bodies=(LEAVE,))
    kept: Kept[CachedRetrieval] = Kept()
    asked(source, kept, web)

    # The re-read now admits nothing: the reach no longer covers the passage.
    source.bodies = ()
    later = asked(source, kept, web)

    hit = source.bodies_asked()[-1]
    assert later.records == ()
    assert len(source.rankings()) == legs()
    assert str(reach_predicate(reach).compile(dialect=POSTGRES)) in str(
        hit.statement.compile(dialect=POSTGRES)
    )
    assert rendered(hit.settings) == rendered(source.bodies_asked()[0].settings), (
        A_CACHED_RETRIEVAL_IS_RE_READ_UNDER_THE_CALLERS_REACH
    )


def test_two_people_asking_the_same_words_do_not_share_a_list() -> None:
    """The retrieval key carries who is asking, because a person's own drafts are in their reach
    and nobody else's. Delete this and one person's ranking, drafts included, is reused for
    another's question."""
    source = Corpus(ranked=[("c_leave_1",)] * (2 * legs()), bodies=(LEAVE,))
    kept: Kept[CachedRetrieval] = Kept()
    other = EntitlementSet(principal_id="u_other", grants=holding(KNOWLEDGE_READ.value).grants)

    asked(source, kept, holding(KNOWLEDGE_READ.value))
    asked(source, kept, other)

    assert len(kept.held) == 2
    assert len(source.rankings()) == 2 * legs()


def test_a_change_to_the_corpus_the_caller_sees_is_a_new_key() -> None:
    """An upload adds a passage to the reach's count, so the next asking ranks again rather than
    reusing a list that cannot name what was just added. Delete this and somebody who uploads a
    document cannot find it until the cache forgets the question."""
    source = Corpus(ranked=[("c_leave_1",)] * (2 * legs()), bodies=(LEAVE,))
    kept: Kept[CachedRetrieval] = Kept()

    asked(source, kept, holding(KNOWLEDGE_READ.value))
    source.passages += 1
    asked(source, kept, holding(KNOWLEDGE_READ.value))

    assert len(kept.held) == 2
    assert len(source.rankings()) == 2 * legs()


def test_the_number_of_passages_asked_for_is_part_of_the_key() -> None:
    """732399b5's narrowing: a list ranked for one passage is not the first of a list ranked for
    five, once fusion has cut both. Delete this and a question asking for more passages is handed
    the shorter list somebody else asked for."""
    source = Corpus(ranked=[("c_leave_1",)] * (2 * legs()), bodies=(LEAVE,))
    kept: Kept[CachedRetrieval] = Kept()

    asked(source, kept, holding(KNOWLEDGE_READ.value), limit=1)
    asked(source, kept, holding(KNOWLEDGE_READ.value), limit=5)

    assert len(kept.held) == 2


def test_an_expired_caller_is_neither_kept_nor_served() -> None:
    """`CallerKey.of` refuses a caller past their time bound, so nothing is kept for them and
    the search runs as it would with no cache. Delete this and a contractor's list outlives their
    contract under a key that matches exactly."""
    expired = EntitlementSet(
        principal_id="u_reader",
        grants=holding(KNOWLEDGE_READ.value).grants,
        not_after=UPDATED,
    )
    source = Corpus(ranked=[("c_leave_1",)] * legs(), bodies=(LEAVE,))
    kept: Kept[CachedRetrieval] = Kept()

    asked(source, kept, expired)

    assert kept.held == {}


# ------------------------------------------------------------------ the embedding (M6.2.4)
def test_a_question_asked_twice_is_embedded_once() -> None:
    """The second asking of the same words is served the kept vector, and the service is asked
    once. Delete this and the embedding cache can be built and never read."""
    service = Embedding()
    kept: Kept[CachedEmbedding] = Kept()
    embedder = QuestionEmbedder(service=service, revision=A_REVISION, cache=kept)

    first = settle(embedder.vector("how is leave booked"))
    second = settle(embedder.vector("how is leave booked"))

    assert first == second
    assert len(service.asked) == 1
    [entry] = kept.held.values()
    assert entry.model == first.model.identity


def test_a_vector_kept_for_other_weights_is_never_read() -> None:
    """The model is in the key, so a revision change embeds afresh rather than reading a vector
    from a space the corpus is no longer in. Delete this and an upgrade of the weights mixes two
    spaces in one search with nothing saying so."""
    service = Embedding()
    kept: Kept[CachedEmbedding] = Kept()

    settle(QuestionEmbedder(service=service, revision=A_REVISION, cache=kept).vector("leave"))
    settle(QuestionEmbedder(service=service, revision="v2.0.0", cache=kept).vector("leave"))

    assert len(service.asked) == 2
    assert len(kept.held) == 2


def test_with_no_cache_every_asking_is_embedded() -> None:
    """The sibling: an install with no cache configured embeds as it always did. Delete this and
    a process with no cache can be made to fail rather than to embed."""
    service = Embedding()
    embedder = QuestionEmbedder(service=service, revision=A_REVISION)

    settle(embedder.vector("leave"))
    settle(embedder.vector("leave"))

    assert len(service.asked) == 2
