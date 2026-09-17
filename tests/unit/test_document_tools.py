"""The document plane's two tools, driven through a row source that records what it is asked.

**No database, and the stand-in cannot evaluate SQL, so the two halves are asserted apart.**
What a statement will admit is asserted on the compiled statement: every chunk statement
carries `reach_predicate` for the caller's reach, and the bodies are asked for by exactly the
references the ranking returned. What the handler does with what comes back is asserted by
handing it rows, including rows it did not ask for, because a handler that trusted its row
source would pass every test that only ever handed it the right ones.

Task ids: M15.2.6, M15.3.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.visitors import iterate

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.errors import Degraded
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.document_tools import (
    DEFAULT_PASSAGES,
    KNOWLEDGE_ENTITY,
    KNOWLEDGE_PIN,
    LEXICAL_LEG_QUERIES,
    MAX_PASSAGES,
    ONLY_THE_VECTOR_LEG_WALKS_THE_INDEX_AND_IT_CARRIES_THE_SCAN_SETTINGS,
    PASSAGE_COLUMNS,
    DocumentRead,
    DocumentSearch,
    KnowledgePassage,
    QuestionEmbedder,
    departments_query,
    passages_query,
    reach_through,
    reader,
    searcher,
)
from brain.knowledge.embed_policy import (
    COLUMN_DIMENSIONS,
    QUESTION_UNIT_ID,
    EmbeddingUnavailable,
    served_embedding_model,
)
from brain.knowledge.embed_queue import Embedded, EmbeddingBatch
from brain.knowledge.embedding import EmbeddedVector
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import (
    CANDIDATE_DEPTH,
    CHUNK,
    EMBEDDING_DIMENSIONS,
    KNOWLEDGE_READ,
    RETRIEVABLE_STATE_VALUES,
    Reach,
    iterative_scan_statements,
    lexical_legs,
    reach_predicate,
    session_settings,
    vector_query,
)
from brain.tables.gate import DepartmentRow

#: `postgresql.dialect()` is untyped, so the dialect is taken from an engine, as
#: `tests/unit/test_search.py` takes it.
POSTGRES = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far from any wall clock, because nothing here is about the present.
NOW = datetime(2019, 1, 1, 9, 0, tzinfo=UTC)
UPDATED = datetime(2019, 1, 1, 8, 0, tzinfo=UTC)

DEPARTMENTS = ("finance", "web")


class Recording:
    """A row source that answers by what it was asked for and remembers every statement.

    The department registry for the departments query, the next ranking for a lexical leg, the
    nearest chunks for the vector leg, and every body it holds for anything else, whatever that
    statement asked for.
    """

    def __init__(
        self,
        *,
        ranked: Sequence[Sequence[str]] = (),
        bodies: Sequence[Mapping[str, Any]] = (),
        nearest: Sequence[str] = (),
    ) -> None:
        self.ranked = [tuple(leg) for leg in ranked]
        self.bodies = tuple(bodies)
        self.nearest = tuple(nearest)
        self.asked: list[RowQuery] = []

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.asked.append(query)
        if query.entity == "department":
            return [{"slug": slug} for slug in DEPARTMENTS]
        if query.columns == ("chunk_id", "relevance"):
            leg = self.ranked.pop(0) if self.ranked else ()
            return [{"chunk_id": ref, "relevance": 1.0} for ref in leg]
        if query.columns == ("chunk_id", "distance"):
            return [{"chunk_id": ref, "distance": 0.1} for ref in self.nearest]
        return list(self.bodies)

    def chunk_statements(self) -> list[RowQuery]:
        return [query for query in self.asked if query.entity == KNOWLEDGE_ENTITY]


def body(chunk_id: str, document_id: str, ordinal: int, text: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "ordinal": ordinal,
        "body": text,
        "title": f"title of {document_id}",
        "section": "",
        "updated_at": UPDATED,
    }


def holding(*capabilities: str, scope: Scope | None = None) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=Capability(value=value), scope=scope or Scope.unrestricted())
            for value in capabilities
        ),
    )


READER = holding(KNOWLEDGE_READ.value)
NO_PLANE = holding("read:price_list")


def search(
    source: Recording, question: str, entitlement: EntitlementSet, limit: int = DEFAULT_PASSAGES
) -> TypedResult[KnowledgePassage]:
    handler = searcher(source)
    return settle(
        handler(DocumentSearch(question=question, limit=limit), entitlement=entitlement, now=NOW)
    )


def settle[T](pending: Awaitable[T]) -> T:
    """Run one handler to completion. The handlers are typed as awaitables, as
    `RowTool.reader`'s are, and `asyncio.run` takes a coroutine."""

    async def wait() -> T:
        return await pending

    return asyncio.run(wait())


def compiled(query: RowQuery) -> str:
    return str(query.statement.compile(dialect=POSTGRES))


# ------------------------------------------------------------------ what a search returns
def test_a_search_hands_back_the_ranked_passages_grouped_by_the_document_they_came_from() -> None:
    """**The positive case every refusal below needs beside it.** The ranking is handed back
    through `hybrid`, `by_chunk` and `by_document`: documents in the order of their best
    passage, passages inside a document in reading order, and each passage carrying its body as
    `document` and its document's reference so it can be cited and read.

    Delete this and a handler that returned nothing passes every refusal in this file."""
    source = Recording(
        ranked=[("c_rota_2", "c_leave_1", "c_rota_1")],
        bodies=(
            body("c_rota_1", "doc_rota", 0, "Escalations go to the on-call engineer."),
            body("c_rota_2", "doc_rota", 1, "Public holidays follow the rota."),
            body("c_leave_1", "doc_leave", 0, "Leave is booked two weeks ahead."),
        ),
    )

    found = search(source, "who is on call", READER)

    assert [one.id for one in found.records] == ["c_rota_1", "c_rota_2", "c_leave_1"]
    first = found.records[0]
    assert (first.entity, first.document_id, first.document, first.updated_at) == (
        KNOWLEDGE_ENTITY,
        "doc_rota",
        "Escalations go to the on-call engineer.",
        UPDATED.isoformat(),
    )
    assert first.title == "title of doc_rota"
    assert found.fetched_at == NOW.isoformat()
    assert found.truncated is False


def test_a_body_the_ranking_did_not_name_is_never_handed_back() -> None:
    """The ranking decides membership and the rows only supply text. A row source handing back
    more than it was asked for, a cache or a query that lost its WHERE clause, must widen
    nothing.

    Delete this and the handler can build passages from whatever rows arrive, and the salary
    note rides back beside the leave policy."""
    source = Recording(
        ranked=[("c_leave_1",)],
        bodies=(
            body("c_leave_1", "doc_leave", 0, "Leave is booked two weeks ahead."),
            body("c_salary_1", "doc_salary", 0, "The band review settled."),
        ),
    )

    assert [one.id for one in search(source, "leave", READER).records] == ["c_leave_1"]


def test_a_page_that_filled_its_limit_says_it_may_have_been_cut_short() -> None:
    """Delete this and a page that stopped at its limit reads as the whole answer, which is the
    difference between "there are two" and "here are two"."""
    ranked = ("c_a_1", "c_b_1", "c_c_1")
    bodies = [body(ref, f"doc_{ref[2]}", 0, f"passage {ref}") for ref in ranked]

    short = search(Recording(ranked=[ranked], bodies=bodies), "passage", READER, limit=2)
    whole = search(Recording(ranked=[ranked], bodies=bodies), "passage", READER, limit=10)

    assert [one.id for one in short.records] == ["c_a_1", "c_b_1"]
    assert short.truncated is True
    assert whole.truncated is False


def test_a_passage_matched_in_two_scripts_is_one_passage() -> None:
    """A question in two scripts is asked of both lexical legs, and a chunk holding both scripts
    comes back from each. `Ranking` refuses a reference listed twice, so without the legs being
    joined first the question would fail rather than answer.

    Delete this and every mixed-script question that matches a mixed-script document fails."""
    source = Recording(
        ranked=[("c_sla_1",), ("c_sla_1", "c_sla_2")],
        bodies=(
            body("c_sla_1", "doc_a", 0, "SLA 条款 one"),
            body("c_sla_2", "doc_b", 0, "条款 two"),
        ),
    )

    found = search(source, "SLA 条款", READER)

    assert len(source.asked) == 1 + len(lexical_legs("SLA 条款")) + 1
    assert [one.id for one in found.records] == ["c_sla_1", "c_sla_2"]


def test_every_leg_a_question_can_need_has_a_statement() -> None:
    """`lexical_legs` names a leg by the column it searches, and a leg with no statement here is
    a `KeyError` on the first question in that script.

    Delete this and a third script added to `lexical_legs` fails in production on its first
    question rather than here."""
    for question in ("annual leave", "年假", "SLA 条款"):
        assert set(lexical_legs(question)) <= set(LEXICAL_LEG_QUERIES), question

    source = Recording(ranked=[()])
    search(source, "年假", READER)
    assert ["tsv_cjk" in compiled(query) for query in source.chunk_statements()] == [True]


# ------------------------------------------------------------------ the reach, inside
def test_every_chunk_statement_carries_the_callers_reach() -> None:
    """**The property the module rests on.** The ranking legs, the bodies of what they ranked,
    and a document read are each built with `reach_predicate` for this caller's reach, so a body
    the caller may not read is never fetched to be dropped. Asserted on the compiled SQL of the
    whole predicate rather than on one column name that a comment could supply.

    Delete this and the bodies can be fetched by reference alone, on the reasoning that the
    ranking already applied the reach, which is a second decision about the same question."""
    reach = Reach(principal_id="u_reader", departments=DEPARTMENTS)
    predicate = str(reach_predicate(reach).compile(dialect=POSTGRES))
    source = Recording(
        ranked=[("c_leave_1",)], bodies=(body("c_leave_1", "doc_leave", 0, "Leave."),)
    )

    search(source, "leave", READER)
    settle(reader(source)(DocumentRead(document_id="doc_leave"), entitlement=READER, now=NOW))

    statements = source.chunk_statements()
    assert len(statements) == len(lexical_legs("leave")) + 2
    for query in statements:
        assert predicate in compiled(query), compiled(query)


def rendered(settings: Sequence[Any]) -> list[tuple[str, dict[str, Any]]]:
    """Settings as the text and the bound values they compile to, so two tuples built separately
    compare by what they would run rather than by object identity."""
    out = []
    for one in settings:
        statement = one.compile(dialect=POSTGRES)
        out.append((str(statement), dict(statement.params)))
    return out


def test_every_chunk_statement_carries_the_settings_the_second_wall_reads() -> None:
    """**What makes a department's documents reachable on a real database.** `know.chunk`'s
    row-level security reads `app.principal_id` and `app.departments`, and a statement run with
    neither set is admitted company-visible chunks only. So every chunk statement, the ranking
    legs, the bodies and a document read, carries `session_settings` for the caller's reach.

    Asked of a caller reaching one department, so the settings are held to that reach rather
    than to any reach: `app.departments` is `web` and nothing wider.

    Delete this and a chunk statement can go out with no settings, which every test with a
    stand-in source passes and which on PostgreSQL hands a department nothing of its own."""
    web = holding(KNOWLEDGE_READ.value, scope=Scope.department("web"))
    expected = rendered(session_settings(Reach(principal_id="u_reader", departments=("web",))))
    source = Recording(
        ranked=[("c_leave_1",)], bodies=(body("c_leave_1", "doc_leave", 0, "Leave."),)
    )

    settle(searcher(source)(DocumentSearch(question="leave"), entitlement=web, now=NOW))
    settle(reader(source)(DocumentRead(document_id="doc_leave"), entitlement=web, now=NOW))

    statements = source.chunk_statements()
    assert len(statements) == len(lexical_legs("leave")) + 2
    for query in statements:
        assert rendered(query.settings) == expected, compiled(query)
    assert dict(expected[1][1])["value"] == "web"


def test_the_department_registry_is_read_with_no_settings() -> None:
    """The registry is read before there is a reach to build settings from, and
    `gate.department`'s policy reads none.

    Delete this and the registry read can be handed settings from a reach computed some other
    way, which would be a reach decided before `reach_for` was asked."""
    assert departments_query().settings == ()


def walks(statement: Any) -> bool:
    """Whether a statement's expression tree reaches the embedding column itself."""
    return any(element is CHUNK.c.embedding for element in iterate(statement))


def test_an_install_that_embeds_no_questions_walks_no_vector_index() -> None:
    """**With no embedder there is no vector leg**, which is every install that has not
    declared its embedding weights, and none of its statements reads the embedding. Asserted by
    walking each statement's expression tree for the embedding column itself, with a positive
    sibling built from `vector_query`, so the walk is known to find the column when it is there.

    Delete this and a vector statement can be sent by an install with no vectors in it, which
    also breaks `test_document_second_wall.py`, whose table has no embedding column because no
    statement of these tools reads one there."""
    reach = Reach(principal_id="u_reader", departments=DEPARTMENTS)
    source = Recording(
        ranked=[("c_leave_1",)], bodies=(body("c_leave_1", "doc_leave", 0, "Leave."),)
    )
    search(source, "leave", READER)
    settle(reader(source)(DocumentRead(document_id="doc_leave"), entitlement=READER, now=NOW))

    width = EMBEDDING_DIMENSIONS
    assert walks(vector_query([0.0] * width, reach=reach, model=f"m@1:{width}"))
    assert source.chunk_statements()
    assert not any(walks(query.statement) for query in source.chunk_statements())


# ------------------------------------------------------------------ a question's vector
A_REVISION = "v1.0.0"


def unit_vector(hot: int) -> tuple[float, ...]:
    """A normalised vector pointing along one axis, which the client's check accepts."""
    values = [0.0] * COLUMN_DIMENSIONS
    values[hot] = 1.0
    return tuple(values)


@dataclass
class Embedding:
    """An `EmbeddingService` answering a question with one vector, or failing as a server does."""

    down: bool = False
    asked: list[EmbeddingBatch] = field(default_factory=list)

    def embed(self, batch: EmbeddingBatch) -> tuple[Embedded, ...]:
        self.asked.append(batch)
        if self.down:
            msg = "the inference server did not answer"
            raise EmbeddingUnavailable(msg)
        vector = EmbeddedVector(model=batch.model, values=unit_vector(0))
        return (Embedded(chunk_id=QUESTION_UNIT_ID, vector=vector),)


def search_embedding(
    source: Recording, question: str, entitlement: EntitlementSet, service: Embedding
) -> TypedResult[KnowledgePassage]:
    handler = searcher(source, QuestionEmbedder(service=service, revision=A_REVISION))
    return settle(handler(DocumentSearch(question=question), entitlement=entitlement, now=NOW))


def test_a_passage_only_the_vector_leg_found_is_handed_back() -> None:
    """**The vector leg reaches the answer.** A question that shares no word with a passage and
    is near it in meaning comes back with it, which is the whole of what embedding a question is
    for, and the question is sent to the service under the model passages are written with.

    Delete this and the vector leg can be run and its ranking thrown away, which leaves every
    other test here green and an install that embeds questions answering from text search."""
    service = Embedding()
    source = Recording(
        ranked=[()],
        nearest=("c_leave_1",),
        bodies=(body("c_leave_1", "doc_leave", 0, "Annual leave is 25 days."),),
    )

    result = search_embedding(source, "holiday allowance", READER, service)

    assert [passage.id for passage in result.records] == ["c_leave_1"]
    [batch] = service.asked
    assert batch.model.identity == served_embedding_model(revision=A_REVISION).identity


def test_the_vector_leg_carries_the_callers_reach_and_both_sets_of_settings() -> None:
    """**The asker's reach is inside the vector query, and the scan settings travel with it and
    with nothing else.** The one statement that walks the embedding carries `reach_predicate`
    for this caller's reach, the caller's session settings and then the iterative scan
    settings, in that order; no other statement carries the scan settings.

    Asked of a caller reaching one department, so the predicate and `app.departments` are held
    to that reach rather than to any reach.

    Delete this and the nearest neighbours can be taken from the whole corpus and filtered
    afterwards, or taken under a narrow reach without iterative scan, and either hands a narrow
    caller fewer passages than they may read with nothing saying why."""
    web = holding(KNOWLEDGE_READ.value, scope=Scope.department("web"))
    reach = Reach(principal_id="u_reader", departments=("web",))
    predicate = str(reach_predicate(reach).compile(dialect=POSTGRES))
    source = Recording(
        ranked=[("c_leave_1",)],
        nearest=("c_leave_1",),
        bodies=(body("c_leave_1", "doc_leave", 0, "Leave."),),
    )

    search_embedding(source, "leave", web, Embedding())

    walking = [query for query in source.chunk_statements() if walks(query.statement)]
    [vector] = walking
    assert predicate in compiled(vector)
    assert rendered(vector.settings) == rendered(
        (*session_settings(reach), *iterative_scan_statements())
    )
    scan = rendered(iterative_scan_statements())
    for query in source.chunk_statements():
        if query is not vector:
            assert not any(one in scan for one in rendered(query.settings)), compiled(query)
    assert "vector" in ONLY_THE_VECTOR_LEG_WALKS_THE_INDEX_AND_IT_CARRIES_THE_SCAN_SETTINGS


def test_a_question_the_server_could_not_embed_is_a_degraded_answer_and_reads_no_chunk() -> None:
    """**An outage on the query leg is declared, not absorbed.** The handler raises `Degraded`
    before any chunk statement is sent, so no passages from text search alone are handed back
    reading like a full answer.

    Delete this and the handler can swallow the failure and answer from the lexical legs, which
    is the silent degradation `embed_policy.OUTAGE_POLICY` says the query leg never has."""
    source = Recording(ranked=[("c_leave_1",)], bodies=(body("c_leave_1", "doc_leave", 0, "L."),))

    with pytest.raises(Degraded):
        search_embedding(source, "leave", READER, Embedding(down=True))
    assert source.chunk_statements() == []


def test_a_caller_with_no_read_of_the_plane_sends_nothing_to_be_embedded() -> None:
    """A question from somebody who reaches no document is not sent anywhere: there is nothing
    it could be compared with that they may read.

    Delete this and the embedding can move ahead of the reach, which posts every question from
    every caller to the server, including the ones who are about to be handed nothing."""
    service = Embedding()

    result = search_embedding(Recording(), "leave", NO_PLANE, service)

    assert result.records == ()
    assert service.asked == []


def test_the_bodies_are_asked_for_by_exactly_the_references_the_ranking_returned() -> None:
    """Delete this and the bodies statement can lose its reference list and ask for every chunk
    the caller reaches, which is a page of the whole plane handed to a filter in Python."""
    page = ["c_rota_2", "c_leave_1"]
    query = passages_query(page, reach=Reach(principal_id="u_reader", departments=DEPARTMENTS))

    params = query.statement.compile(dialect=POSTGRES).params

    assert page in params.values()
    assert query.columns == PASSAGE_COLUMNS
    assert query.certainly_empty is False


def test_a_document_is_read_in_reading_order_by_its_own_reference() -> None:
    """`by_document` puts a document's passages in ordinal order whatever order the rows arrive
    in, and the statement asks for that one document.

    Delete this and a document read can hand back another document's passages, or its own in
    the order an index happened to return them."""
    source = Recording(
        bodies=(
            body("c_rota_3", "doc_rota", 2, "third"),
            body("c_rota_1", "doc_rota", 0, "first"),
            body("c_rota_2", "doc_rota", 1, "second"),
        )
    )

    found = settle(
        reader(source)(DocumentRead(document_id="doc_rota", limit=3), entitlement=READER, now=NOW)
    )

    assert [one.document for one in found.records] == ["first", "second", "third"]
    assert found.truncated is True
    (statement,) = source.chunk_statements()
    assert "doc_rota" in statement.statement.compile(dialect=POSTGRES).params.values()


def test_the_reach_is_the_departments_the_registry_holds_that_the_grant_admits() -> None:
    """`reach_for` intersects a grant with the department registry, which is read from the row
    source. An unrestricted grant reaches every department there is and a departmental one
    reaches its own.

    Delete this and the handler can pass an empty registry, and every department's documents
    become unreachable for everybody while company documents go on answering."""
    source = Recording()

    wide = settle(reach_through(source, READER, NOW))
    web = settle(
        reach_through(source, holding(KNOWLEDGE_READ.value, scope=Scope.department("web")), NOW)
    )

    assert wide == Reach(principal_id="u_reader", departments=DEPARTMENTS)
    assert web == Reach(principal_id="u_reader", departments=("web",))


def test_a_caller_with_no_read_of_the_plane_is_handed_nothing_and_no_chunk_is_read() -> None:
    """The refusal, asked of both tools and without a clock, and with rows ready that a handler
    ignoring the reach would hand back. No chunk statement runs at all for somebody `reach_for`
    answers None for.

    Delete this and a handler can build a reach of its own when `reach_for` has none, which is
    the plane opened to whoever reaches the tool."""
    rows = (body("c_leave_1", "doc_leave", 0, "Leave."),)
    searching = Recording(ranked=[("c_leave_1",)], bodies=rows)
    reading = Recording(bodies=rows)

    searched = settle(searcher(searching)(DocumentSearch(question="leave"), entitlement=NO_PLANE))
    read = settle(reader(reading)(DocumentRead(document_id="doc_leave"), entitlement=NO_PLANE))

    assert searched.records == ()
    assert read.records == ()
    assert searched.fetched_at == ""
    assert searching.chunk_statements() == []
    assert reading.chunk_statements() == []


def test_a_question_nothing_matches_reads_no_bodies() -> None:
    """A ranking with nothing in it has no bodies to fetch, and the handler does not ask, as
    `brain.knowledge.rows.read_rows` does not run a statement that cannot return a row.

    Delete this and every question with no match spends a round trip to be told nothing."""
    source = Recording(ranked=[()], bodies=(body("c_leave_1", "doc_leave", 0, "Leave."),))

    found = search(source, "nothing like it", READER)

    assert found.records == ()
    assert [query.columns for query in source.chunk_statements()] == [("chunk_id", "relevance")]


# ------------------------------------------------------------------ the declarations
def test_the_scope_the_registry_reads_is_the_condition_every_statement_applies() -> None:
    """`assert_service_tool_is_scoped` refuses an unrestricted scope on a SERVICE tool. The pin
    satisfies it with the retrievable states, held here to `brain.knowledge.search`'s own
    constant, which is what `reach_predicate` conjoins inside every statement above.

    Delete this and the pin can drift into a scope nothing applies."""
    assert KNOWLEDGE_PIN.clauses == (
        Clause(field="state", op=Op.IN, value=RETRIEVABLE_STATE_VALUES),
    )
    assert not KNOWLEDGE_PIN.is_unrestricted()


def test_a_page_is_never_longer_than_one_legs_candidates() -> None:
    """Each leg returns `CANDIDATE_DEPTH` candidates before fusion, so a page longer than that
    is a page fusion can never fill, and it would report itself complete when it was cut.

    Delete this and the limit can be raised past what a leg returns."""
    assert DEFAULT_PASSAGES <= MAX_PASSAGES <= CANDIDATE_DEPTH


def test_the_department_registry_is_read_for_live_departments_only() -> None:
    """`reach_for` intersects a grant with the registry it is handed, so a retired department
    in it is one a grant with no department clause still reaches, and a name the second wall
    is told to admit after the department was removed. The policy on `gate.department` hides
    retired rows from the application's role; this holds the statement to the same condition
    itself, so a session the policy does not name reads the same registry.

    Asserted on the column's own compiled `IS NULL` test rather than on text a comment could
    supply.

    Delete this and the departments query can read retired departments back into every reach."""
    live = str(DepartmentRow.deleted_at.is_(None).compile(dialect=POSTGRES))

    assert live in compiled(departments_query())
