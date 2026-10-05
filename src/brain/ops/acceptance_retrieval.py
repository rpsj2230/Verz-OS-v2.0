"""Install acceptance checks for retrieval: what each reader's search and row tools return, and why.

The retrieval modules were built with a claim each, and every claim was proved over a fake source or
a Python model of the SQL: `brain.knowledge.search.top_within_reach` says in its own docstring that
it is the property written without a server. These checks run the product's own statements on the
install's own PostgreSQL, as reserved people in the reserved departments, inside the check's
rolled-back transaction, and read what comes back: the typed row tool, the text leg and its
weights, the vector leg through the install's HNSW index, the fusion of the two, the assembly of a
document's passages, the database's own wall under the query, and one composite of three people
reaching four places.

**The vector leg is proved with vectors a check writes, and no embedding model is asked.** A
default install declares no embedding revision (`INSTALL_EMBEDDING_REVISION` is `unset`), so no
chunk on it has a vector and no inference server answers. What M15.2.2 to M15.2.5 claim is about
the index, the scan settings, the scope predicate and the fusion, not about the model, so each check
writes vectors of its own onto its own chunks through the product's own
`brain.knowledge.chunk_store.embedding_update`, under a model identity named for the run, and asks
with a vector of its own through the product's `QuestionEmbedder` over a stand-in service. Every
other chunk on the install carries another identity or none, and `vector_query` conjoins the
identity, so nothing real is ever compared. See
`A_CHECK_S_VECTORS_ARE_ITS_OWN_AND_NAMED_FOR_ITS_RUN`.

**The index walk is forced, because on a small corpus the planner rightly scans instead.** The
narrow-scope failure M15.2.4 exists to prevent happens only when the HNSW index is walked: a
sequential scan filters every row and is exact. A new install has a handful of chunks, so the
planner scans, and a check that let it would pass whether or not iterative scan was on. So the
vector reads here run the product's statement with its own settings and two more, the sequential
scan and the sort switched off, in the read's own savepoint, which ends with it. That found the
vector leg's ORDER BY carrying a tie-breaker the index cannot serve, so no install had ever walked
it; `brain.knowledge.search.vector_query` now orders by the distance alone. See
`THE_INDEX_IS_WALKED_BECAUSE_THAT_IS_WHERE_THE_LEAK_IS`.

**The crowd is in the other department.** Sixty passages in acceptance_b sit closer to the
question than the three in acceptance_a, more than `CANDIDATE_DEPTH` and more than the index's
default walk, so a reader in acceptance_a is answered from their own three only if the predicate is
inside the walk and the walk keeps going past the crowd.

**What is left out, and why.** M15.3.3 (deduplication across planes) has no answer to act on: the
fast lane reads rows and the model step reads passages, and no answer today draws on both. M15.3.4
(retrieval logging) has no store. M15.3.1 (reranking) has no reranker to evaluate. None of those
has a check here, and none is claimed.

Task ids: M38.5.1
"""

from __future__ import annotations

import math
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, select, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.knowledge.embedding import EmbeddingModel
    from brain.knowledge.rows import RowQuery

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 150

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the vectors a check searches are its own.
A_CHECK_S_VECTORS_ARE_ITS_OWN_AND_NAMED_FOR_ITS_RUN: Final = (
    "No embedding model answers on a default install, and what the vector leg's leaves claim is "
    "about the index, the scan settings, the scope predicate and the fusion. So a check writes "
    "vectors onto its own chunks through the product's own update, under a model identity named "
    "for its run, and the vector query conjoins that identity, so no chunk of the install's own "
    "is compared with anything a check wrote."
)

#: Why the vector reads switch the sequential scan off.
THE_INDEX_IS_WALKED_BECAUSE_THAT_IS_WHERE_THE_LEAK_IS: Final = (
    "A narrow reader loses results only when the HNSW index is walked and the walk stops before it "
    "reaches their passages; a sequential scan filters every row and is exact. On a small corpus "
    "the planner scans, so a check that let it would pass with iterative scan off. The vector "
    "reads run the product's statement with its settings and with the sequential scan and the "
    "sort switched off, in the read's own savepoint, which ends with the read, so the index walk "
    "is the only plan that orders the statement."
)

#: Why the second wall is asked with the reader settings written empty.
A_CHECK_CLEARS_THE_READER_SETTINGS_IT_DID_NOT_SET: Final = (
    "The chunk table's policy reads two transaction settings, and a request starts with neither. "
    "A check is one transaction, and a service that committed earlier in it released a savepoint "
    "still holding the settings it set, so asking with no reach would ask as whoever uploaded "
    "last. The check writes both settings empty, which is what a request that set none reads."
)

#: Why a placed vector's direction away from the question is drawn at random.
A_PLACED_VECTOR_LEANS_A_RANDOM_WAY: Final = (
    "An HNSW graph built over vectors that all sit at one distance from each other, as vectors "
    "leaning on separate axes do, links so few of them that most cannot be reached from the "
    "entry point at all, measured at thirty-six of a hundred and twenty-six. Embeddings are not "
    "shaped like that. A placed vector keeps its stated cosine with the question and leans the "
    "rest of the way in a direction drawn from a seeded generator, so the graph is one a real "
    "corpus would build and every passage in it can be reached."
)

#: Why a placed vector is drawn from the run as well as from its position.
A_PLACED_VECTOR_IS_THE_RUN_S_OWN: Final = (
    "A check's rows are rolled back and their index entries stay until a vacuum. pgvector keeps "
    "equal vectors in one HNSW element, ten heap entries to an element, so a check that placed "
    "the same vectors on every run stacked each run's dead copies onto the last run's: from the "
    "eleventh run on one database the narrow reader's own passages were no longer reached "
    "(measured 2026-10-05, ten runs passing and the next two failing; one CI run in about eight "
    "failed this check on its second pass). So the direction a vector leans is drawn from the run "
    "and its position together, and no two runs place the same point."
)

# ------------------------------------------------------------------------ the figures
#: What a vector read adds to the product's own settings, in its own savepoint: no sequential
#: scan and no sort, so the only plan that gives the statement its order is the HNSW index walk.
#: See `THE_INDEX_IS_WALKED_BECAUSE_THAT_IS_WHERE_THE_LEAK_IS`.
WALK_THE_INDEX: Final = (
    text("SET LOCAL enable_seqscan = off"),
    text("SET LOCAL enable_sort = off"),
)

#: How many passages crowd acceptance_b, closer to the question than acceptance_a's own. More
#: than `CANDIDATE_DEPTH` and more than pgvector's default `hnsw.ef_search` of forty.
CROWD: Final = 60

#: How many passages of acceptance_a's own each vector check places.
OWN: Final = 3

#: How close acceptance_b's crowd sits to the question, and acceptance_a's own passages.
CROWD_SIMILARITY: Final = 0.95
OWN_SIMILARITY: Final = 0.9

#: The two settings the chunk table's policy reads, emptied. A request's transaction starts with
#: neither set; a check's does not, because an upload earlier in it released a savepoint holding
#: the uploader's, so "no reach" is written rather than assumed. See
#: `A_CHECK_CLEARS_THE_READER_SETTINGS_IT_DID_NOT_SET`.
NO_REACH: Final = (
    text("SELECT set_config('app.principal_id', '', true)"),
    text("SELECT set_config('app.departments', '', true)"),
)

#: How many characters each section of a many-passage document runs to: under a chunk's size
#: and over its minimum, so each section is a passage of its own.
SECTION_CHARS: Final = 900


# --------------------------------------------------------------------------- documents
def _markdown(sections: Sequence[str]) -> bytes:
    """A Markdown document of one heading and paragraph per section, each its own passage."""
    lines: list[str] = []
    for n, words in enumerate(sections, start=1):
        filler = " ".join(["The acceptance check wrote this sentence to fill the section."] * 20)
        lines.extend((f"# Section {n}", "", f"{words} {filler}"[:SECTION_CHARS], ""))
    return "\n".join(lines).encode("utf-8")


async def _added(
    h: Harness,
    uploader: str,
    sections: Sequence[str],
    *,
    filename: str = "Acceptance.md",
    department: str = A,
    level: Any = None,
) -> str:
    """A document placed by `uploader` through the upload route's own sequence: its item id."""
    from brain.knowledge.ingest import MediaType, ParseFailure

    read = await _upload(
        h,
        uploader,
        filename=filename,
        declared=MediaType.MARKDOWN.value,
        body=_markdown(sections),
        department=department,
        level=level,
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed Markdown document could not be added")
    return str(read.item.item_id)


def _found_documents(found: Any) -> list[str]:
    """The documents a search returned, in the order their passages came back, each once."""
    return list(dict.fromkeys(one.document_id for one in found.records))


# ----------------------------------------------------------------------------- vectors
def _unit(dimensions: int, weights: dict[int, float]) -> tuple[float, ...]:
    """A unit vector of `dimensions` with the given weights on the given axes."""
    norm = math.sqrt(sum(value * value for value in weights.values()))
    values = [0.0] * dimensions
    for axis, value in weights.items():
        values[axis] = value / norm
    return tuple(values)


def _at(similarity: float, seed: int, dimensions: int, *, run: str) -> tuple[float, ...]:
    """A unit vector whose cosine with the question's axis is `similarity`, the rest of it a
    direction drawn from `run` and `seed`. See `A_PLACED_VECTOR_LEANS_A_RANDOM_WAY` and
    `A_PLACED_VECTOR_IS_THE_RUN_S_OWN`."""
    # A seeded generator on purpose: one run places the same vectors, and nothing here is a
    # secret or a key, which is the case the rule below is about.
    draw = random.Random(f"{run}:{seed}")  # noqa: S311
    rest = [draw.gauss(0.0, 1.0) for _ in range(dimensions - 1)]
    length = math.sqrt(sum(one * one for one in rest))
    side = math.sqrt(1 - similarity * similarity)
    return (similarity, *(one / length * side for one in rest))


def _model(h: Harness) -> EmbeddingModel:
    """The identity a check's vectors are written under: the served model, a revision of the run.

    See `A_CHECK_S_VECTORS_ARE_ITS_OWN_AND_NAMED_FOR_ITS_RUN`.
    """
    from brain.knowledge.embed_policy import served_embedding_model

    return served_embedding_model(revision=f"acceptance-{h.run}")


def _dimensions() -> int:
    from brain.knowledge.search import EMBEDDING_DIMENSIONS

    if EMBEDDING_DIMENSIONS < CROWD + OWN + 2:
        raise CheckNotRunError(
            "this install's vector column is too narrow to place the crowd on axes of its own"
        )
    return EMBEDDING_DIMENSIONS


async def _embedded(
    h: Harness,
    owner: str,
    document_id: str,
    vector: Callable[[int], tuple[float, ...]],
) -> dict[str, str]:
    """Write `vector(n)` onto the `n`th passage of a document, as its owner: each passage's words,
    by its id.

    `brain.knowledge.chunk_store.embedding_update` under the owner's own reach, as the worker's
    embedding job writes one, with the run's model identity beside every vector.
    """
    from brain.knowledge.chunk_store import embedding_update, reach_of
    from brain.knowledge.embed_queue import EmbeddingWrite
    from brain.knowledge.embedding import EmbeddedVector
    from brain.knowledge.search import CHUNK, session_settings

    model = _model(h)
    async with h.sessions() as session:
        reach = await reach_of(session, owner, now=h.now)
        if reach is None:
            raise CheckFailedError("the uploader of a document reached none of it to embed")
        for setting in session_settings(reach):
            await session.execute(setting)
        rows = (
            await session.execute(
                select(CHUNK.c.chunk_id, CHUNK.c.updated_at, CHUNK.c.body)
                .where(CHUNK.c.document_id == document_id)
                .order_by(CHUNK.c.ordinal)
            )
        ).all()
        for n, (chunk_id, updated_at, _) in enumerate(rows):
            write = EmbeddingWrite(
                chunk_id=str(chunk_id),
                vector=EmbeddedVector(model=model, values=vector(n)),
            )
            done = await session.execute(embedding_update(write, reach=reach, read_at=updated_at))
            if getattr(done, "rowcount", 0) != 1:
                raise CheckFailedError("a passage's vector was not written by the embedding update")
        await session.commit()
    return {str(one[0]): str(one[2]) for one in rows}


def _walked(query: RowQuery) -> RowQuery:
    """The product's statement with its settings and the index walk forced. See
    `THE_INDEX_IS_WALKED_BECAUSE_THAT_IS_WHERE_THE_LEAK_IS`."""
    return replace(query, settings=(*query.settings, *WALK_THE_INDEX))


async def _nearest(h: Harness, reader: str, vector: tuple[float, ...]) -> list[str]:
    """The vector leg for `reader`, as `document_tools.searcher` builds it, walking the index."""
    from brain.knowledge.document_tools import reach_through, vector_search_query
    from brain.knowledge.embedding import EmbeddedVector
    from brain.knowledge.row_store import SessionRowSource

    records = SessionRowSource(h.sessions)
    reach = await reach_through(records, await h.reach(reader), h.now)
    if reach is None:
        return []
    query = vector_search_query(EmbeddedVector(model=_model(h), values=vector), reach=reach)
    return [str(row["chunk_id"]) for row in await records.rows(_walked(query))]


async def _plan(h: Harness, query: RowQuery) -> dict[str, Any]:
    """`EXPLAIN (FORMAT JSON)` of a compiled statement, after its settings, as the application.

    The statement is compiled for this connection's driver and sent with its parameters bound,
    so the plan is the one the statement gets when it runs.
    """
    import json

    async with h.sessions() as session:
        for setting in query.settings:
            await session.execute(setting)
        connection = await session.connection()
        # Expanding parameters, a department list among them, are rendered into the text here, as
        # the driver would render them at execution.
        compiled = query.statement.compile(
            dialect=connection.dialect, compile_kwargs={"render_postcompile": True}
        )
        result = await connection.exec_driver_sql(
            f"EXPLAIN (FORMAT JSON) {compiled}", dict(compiled.params)
        )
        raw = result.scalar_one()
    planned = json.loads(raw) if isinstance(raw, str) else raw
    return dict(planned[0]["Plan"])


def _nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Every node of a plan, parents first."""
    found = [plan]
    for child in plan.get("Plans", []):
        found.extend(_nodes(child))
    return found


# ------------------------------------------------ 1. a typed tool (M15.1.1, M15.1.2, M15.1.4)
@check(
    leaves=("M15.1.1", "M15.1.2", "M15.1.4"),
    sentence=(
        "The install's typed price list tool, asked by a seller in acceptance_a, returns that "
        "department's rows with only the columns they hold, a finance reader there gets cost and "
        "margin too, a seller in acceptance_b only theirs, and each is shown those rows through "
        "the redactor every door uses; the statement binds every value, and its plan filters on "
        "the department in the scan of the records itself."
    ),
)
async def a_typed_row_tool_reads_only_the_callers_rows_and_columns(h: Harness) -> None:
    """**Read through the redactor as well as from the tool**, because that is what a person is
    shown. Until 2026-09-29 this read the tool's records and stopped, and every reader here holds
    grants scoped to one department, so the redactor judged each field's scope against a record
    that did not carry `department` and withheld the lot: every door that redacts answered these
    readers with nothing while this check passed. See
    `brain.knowledge.rows.A_RECORD_CARRIES_WHAT_ITS_READERS_SCOPES_TEST`.
    """
    from brain.api_routes import field_policies
    from brain.core.redaction import require_typed_result, serialise_for_channel
    from brain.knowledge.columns import PRICE_LIST
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.rows import RowRequest, RowTool, compile_row_query
    from brain.tables.projection import ProjectedRecordRow
    from brain.tools.startup import build_registry

    await h.found_departments()
    source = h.settings.tool_source
    tool = RowTool(source=source, classification=PRICE_LIST, description="The price list.")
    registry = build_registry(source=source, records=SessionRowSource(h.sessions))
    if not registry.has(tool.name):
        raise CheckFailedError("this install registers no typed tool for its price list")
    seen = ("read:price_list", "read:price_list.name", "read:price_list.sell_price")
    held = ("read:price_list.cost", "read:price_list.margin")
    seller, finance, outsider = (
        h.principal(A, "seller"),
        h.principal(A, "finance"),
        h.principal(B, "seller"),
    )
    await h.person(seller, department=A, grants=_in(A, *seen))
    await h.person(finance, department=A, grants=_in(A, *seen, *held))
    await h.person(outsider, department=B, grants=_in(B, *seen))
    names = {A: (h.word(), h.word()), B: (h.word(),)}
    for department, listed in names.items():
        for n, name in enumerate(listed):
            await h.execute(
                *h.attributed(),
                insert(ProjectedRecordRow).values(
                    source=source,
                    entity=PRICE_LIST.entity,
                    source_id=f"acceptance-{h.run}-{department}-{n}",
                    last_seen_at=h.now,
                    fields={
                        "department": department,
                        "sku": f"ACC-{n}",
                        "name": name,
                        "sell_price": "120.00",
                        "cost": "70.00",
                        "margin": "50.00",
                    },
                ),
            )
    # A cast at the registry's boundary, for `brain.api_routes.passage_search_for`'s reason.
    handler = cast("Callable[..., Awaitable[Any]]", registry.get(tool.name).handler)
    policy = field_policies(registry)[PRICE_LIST.entity]

    async def read(who: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        reach = await h.reach(who)
        found = await handler(RowRequest(), entitlement=reach, now=h.now)
        shown = serialise_for_channel(
            require_typed_result(found), entitlement=reach, policy=policy, now=h.now
        )
        return [one.model_dump() for one in found.records], list(shown.records)

    for who, department, columns in (
        (seller, A, {"name", "sell_price"}),
        (finance, A, {"name", "sell_price", "cost", "margin"}),
        (outsider, B, {"name", "sell_price"}),
    ):
        records, shown = await read(who)
        if {str(one.get("name")) for one in records} != set(names[department]):
            raise CheckFailedError("a reader's typed tool returned rows outside their department")
        # The department is carried for the redactor to judge the reader's scope by, and is
        # the one key beyond the projection a record may hold.
        if any(set(one) - {"entity", "id", "department"} != columns for one in records):
            raise CheckFailedError("a reader's typed tool returned columns other than they hold")
        if {str(one.get("name")) for one in shown} != set(names[department]):
            raise CheckFailedError("the redactor did not show a reader their own department's rows")
        if any(set(one) - {"entity", "id"} != columns for one in shown):
            raise CheckFailedError("the redactor showed a reader columns other than they hold")

    query = compile_row_query(tool, RowRequest(), entitlement=await h.reach(seller), now=h.now)
    if A in str(query.statement.compile()) or {"cost", "margin"} & set(query.columns):
        raise CheckFailedError("the statement spliced a value in or selected a withheld column")
    scans = [one for one in _nodes(await _plan(h, query)) if one.get("Relation Name") == "record"]
    if not scans or not all(
        A in f"{one.get('Filter', '')} {one.get('Index Cond', '')}" for one in scans
    ):
        raise CheckFailedError("the plan did not filter on the department in the records' scan")


# ---------------------------------------------------------------- 2. the weights (M15.2.1)
@check(
    leaves=("M15.2.1",),
    sentence=(
        "Two documents in acceptance_a hold one word, one in its title and one in passing in its "
        "text: a member's text search returns both from the install's weighted full-text index, "
        "the document the word titles first."
    ),
)
async def a_word_in_a_title_outranks_a_word_in_passing(h: Harness) -> None:
    await h.found_departments()
    library, reader = h.principal(A, "library"), h.principal(A, "member")
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(reader, department=A, grants=_in(A, *KNOWLEDGE_READS))
    word = h.word()
    titled = await _added(h, library, ["Nothing here names it."], filename=f"{word}.md")
    passing = await _added(h, library, [f"This text mentions {word} once in passing."])
    found, _ = await _found(h, reader, word)
    if _found_documents(found) != [titled, passing]:
        raise CheckFailedError("a word a document is titled by did not outrank a word in passing")


# ------------------------------------------------------------- 3. the assembly (M15.3.2)
@check(
    leaves=("M15.3.2",),
    sentence=(
        "A document in acceptance_a with three passages naming one word, the last naming it most, "
        "comes back from a member's search as one document, its passages together and in the "
        "order the document has them, beside another document that names the word."
    ),
)
async def a_documents_passages_come_back_together_in_reading_order(h: Harness) -> None:
    await h.found_departments()
    library, reader = h.principal(A, "library"), h.principal(A, "member")
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(reader, department=A, grants=_in(A, *KNOWLEDGE_READS))
    word = h.word()
    long = await _added(h, library, [word, f"{word} {word}", " ".join([word] * 5)])
    other = await _added(h, library, [" ".join([word] * 3)])
    found, _ = await _found(h, reader, word)
    order = [str(one.document_id) for one in found.records]
    mine = [str(one.id) for one in found.records if one.document_id == long]
    if set(order) != {long, other} or len(mine) != OWN:
        raise CheckFailedError("a search did not return every passage of the documents it matched")
    first = order.index(long)
    if order[first : first + OWN] != [long] * OWN or mine != sorted(mine):
        raise CheckFailedError("a document's passages did not come back together in reading order")


# ------------------------- 4. a narrow reader and the index (M15.2.2, M15.2.3, M15.2.4, M15.2.6)
@check(
    leaves=("M15.2.2", "M15.2.3", "M15.2.4", "M15.2.6"),
    sentence=(
        "Sixty passages in acceptance_b sit nearer a question, and hold its word more strongly, "
        "than three in acceptance_a: walking the install's HNSW index with its scan settings, and "
        "in the text leg, a member of acceptance_a is given all three of their own and none of the "
        "crowd, and a member of acceptance_b is given the crowd."
    ),
)
async def a_narrow_reader_is_given_their_own_passages_past_a_nearer_crowd(h: Harness) -> None:
    from brain.knowledge.search import CANDIDATE_DEPTH, EMBEDDING_DIMENSIONS, VECTOR_INDEX

    dimensions = _dimensions()
    await h.found_departments()
    library_a, library_b = h.principal(A, "library"), h.principal(B, "library")
    reader_a, reader_b = h.principal(A, "member"), h.principal(B, "member")
    await h.person(library_a, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(library_b, department=B, grants=_in(B, "admin:knowledge"))
    await h.person(reader_a, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(reader_b, department=B, grants=_in(B, *KNOWLEDGE_READS))

    column = (
        await h.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute"
                " WHERE attrelid = 'know.chunk'::regclass AND attname = 'embedding'"
            )
        )
    ).scalar_one()
    index = (
        await h.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'know'"
                " AND tablename = 'chunk' AND indexname = :name"
            ).bindparams(name=VECTOR_INDEX.name)
        )
    ).scalar_one_or_none()
    if column != f"vector({EMBEDDING_DIMENSIONS})" or index is None or "hnsw" not in index:
        raise CheckFailedError("the vector column or its HNSW index is not the width declared")

    word = h.word()
    own = await _added(h, library_a, [word] * OWN)
    crowd = await _added(
        h, library_b, [" ".join([word] * 4)] * CROWD, filename=f"{word}.md", department=B
    )
    own_words = await _embedded(
        h, library_a, own, lambda n: _at(OWN_SIMILARITY, n, dimensions, run=h.run)
    )
    own_ids = set(own_words)
    crowd_ids = set(
        await _embedded(
            h,
            library_b,
            crowd,
            lambda n: _at(CROWD_SIMILARITY, len(own_ids) + n, dimensions, run=h.run),
        )
    )
    if len(own_ids) < OWN or len(crowd_ids) < CROWD or len(own_ids) > CANDIDATE_DEPTH:
        raise CheckFailedError("the documents did not come apart into the passages written")

    question = _unit(dimensions, {0: 1.0})
    if set(await _nearest(h, reader_a, question)) != own_ids:
        raise CheckFailedError(
            "a narrow reader walking the index was not given every passage of their own"
        )
    theirs = set(await _nearest(h, reader_b, question))
    if not theirs or not theirs <= crowd_ids:
        raise CheckFailedError("a reader in acceptance_b was not given the crowd alone")
    found, _ = await _found(h, reader_a, word)
    worded = {one for one, words in own_words.items() if word in words}
    if not worded or {str(one.id) for one in found.records} != worded:
        raise CheckFailedError("a narrow reader's text search lost their passages to the crowd")

    from brain.knowledge.document_tools import reach_through, vector_search_query
    from brain.knowledge.embedding import EmbeddedVector
    from brain.knowledge.row_store import SessionRowSource

    reach = await reach_through(SessionRowSource(h.sessions), await h.reach(reader_a), h.now)
    if reach is None:
        raise CheckFailedError("a reader of acceptance_a's documents reached none of them")
    walk = _walked(
        vector_search_query(EmbeddedVector(model=_model(h), values=question), reach=reach)
    )
    if not any(one.get("Index Name") == VECTOR_INDEX.name for one in _nodes(await _plan(h, walk))):
        raise CheckFailedError("the vector leg did not walk the install's HNSW index")


# ------------------------------------------------------------------ 5. the fusion (M15.2.5)
@dataclass(frozen=True)
class _Service:
    """An embedding service answering one question with one vector, in the process."""

    model: EmbeddingModel
    values: tuple[float, ...]

    def embed(self, batch: Any) -> Sequence[Any]:
        from brain.knowledge.embed_queue import Embedded
        from brain.knowledge.embedding import EmbeddedVector

        return [
            Embedded(
                chunk_id=unit.chunk_id, vector=EmbeddedVector(model=self.model, values=self.values)
            )
            for unit in batch.units
        ]


@check(
    leaves=("M15.2.5",),
    sentence=(
        "Of two documents in acceptance_a, one holds the question's word and sits far from its "
        "vector, the other holds no word of it and sits on its vector: a member's hybrid search "
        "returns both, fused by rank, the one both legs found first."
    ),
)
async def hybrid_search_returns_what_each_leg_finds_fused_by_rank(h: Harness) -> None:
    from brain.knowledge.document_tools import DocumentSearch, QuestionEmbedder, searcher
    from brain.knowledge.row_store import SessionRowSource

    dimensions = _dimensions()
    await h.found_departments()
    library, reader = h.principal(A, "library"), h.principal(A, "member")
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(reader, department=A, grants=_in(A, *KNOWLEDGE_READS))
    word = h.word()
    worded = await _added(h, library, [f"This passage names {word}."])
    near = await _added(h, library, ["This passage names nothing the question says."])
    await _embedded(h, library, worded, lambda n: _at(0.3, 2, dimensions, run=h.run))
    await _embedded(h, library, near, lambda n: _at(0.99, 3, dimensions, run=h.run))
    question = _unit(dimensions, {0: 1.0})
    embedder = QuestionEmbedder(
        service=_Service(model=_model(h), values=question), revision=f"acceptance-{h.run}"
    )
    found = await searcher(SessionRowSource(h.sessions), embedder)(
        DocumentSearch(question=word), entitlement=await h.reach(reader), now=h.now
    )
    if _found_documents(found)[:2] != [worded, near]:
        raise CheckFailedError("a hybrid search did not fuse what each leg found by rank")


# ------------------------------------------------------------ 6. the second wall (M15.2.7)
@check(
    leaves=("M15.2.7",),
    sentence=(
        "Asked for acceptance_a's document by its reference with no reach predicate in the "
        "statement, the install's database returns its passages under acceptance_a's reach and "
        "nothing under acceptance_b's or under no reach at all."
    ),
)
async def the_database_withholds_passages_the_statement_did_not_filter(h: Harness) -> None:
    from brain.knowledge.search import CHUNK, session_settings
    from brain.knowledge.search import reach_for as reach_of_departments

    await h.found_departments()
    library, reader_a, reader_b = (
        h.principal(A, "library"),
        h.principal(A, "member"),
        h.principal(B, "member"),
    )
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(reader_a, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(reader_b, department=B, grants=_in(B, *KNOWLEDGE_READS))
    document = await _added(h, library, [h.word()])

    async def unfiltered(settings: Sequence[Any]) -> list[str]:
        async with h.sessions() as session:
            for setting in settings:
                await session.execute(setting)
            rows = await session.execute(
                select(CHUNK.c.chunk_id).where(CHUNK.c.document_id == document)
            )
            return [str(one) for one in rows.scalars().all()]

    def settings_for(reach: EntitlementSet) -> tuple[Any, ...]:
        held = reach_of_departments(reach, departments=[A, B], now=h.now)
        if held is None:
            raise CheckFailedError("a reader holding the knowledge read reached no department")
        return session_settings(held)

    if not await unfiltered(settings_for(await h.reach(reader_a))):
        raise CheckFailedError("the database withheld a passage from its own department's reader")
    if await unfiltered(settings_for(await h.reach(reader_b))) or await unfiltered(NO_REACH):
        raise CheckFailedError("the database returned a passage the statement did not filter")


# --------------------------------------------------------- 7. three people's reach (M15.4.3)
@check(
    leaves=("M15.4.3",),
    sentence=(
        "A member and a department admin of acceptance_a and a super admin search the same words "
        "over each one's personal document, acceptance_a's, acceptance_b's and a company-wide one, "
        "and read an uploaded table: each is given every item their scope covers, only the columns "
        "they may read, and what a search for nothing gives for the rest."
    ),
)
async def three_readers_get_everything_in_their_scope_and_nothing_else(
    h: Harness,
) -> None:
    from brain.knowledge.visibility import PROMOTION_CAPABILITY, Visibility
    from brain.ops.acceptance_checks_chat import uploaded
    from brain.ops.acceptance_checks_lifecycle import (
        REVIEW_AHEAD,
        _approve,
        _as,
        _propose,
        _verify,
    )

    await h.found_departments()
    member, head, owner = (
        h.principal(A, "member"),
        h.principal(A, "head"),
        h.principal(A, "owner"),
    )
    approver, library_b = h.principal(A, "approver"), h.principal(B, "library")
    table = await uploaded(h)
    reads = (*KNOWLEDGE_READS, "admin:knowledge")
    everywhere = tuple((one, Scope.unrestricted()) for one in reads)
    await h.person(member, department=A, grants=(*_in(A, *reads), *table.reads(A, held=False)))
    await h.person(
        head,
        department=A,
        grants=(*_in(A, *reads, PROMOTION_CAPABILITY.value), *table.reads(A, held=True)),
    )
    await h.person(
        owner,
        department=A,
        grants=(
            *everywhere,
            (f"read:{table.entity}", Scope.unrestricted()),
            (f"read:{table.entity}.{table.held_column}", Scope.unrestricted()),
        ),
    )
    await h.person(approver, department=A, grants=_in(A, PROMOTION_CAPABILITY.value))
    await h.person(library_b, department=B, grants=_in(B, "admin:knowledge"))

    words = {one: h.word() for one in ("mine", "heads", "a", "b", "company")}
    placed = {
        "mine": await _added(h, member, [words["mine"]], level=Visibility.PERSONAL),
        "heads": await _added(h, head, [words["heads"]], level=Visibility.PERSONAL),
        "a": await _added(h, head, [words["a"]]),
        "b": await _added(h, library_b, [words["b"]], department=B),
        "company": await _added(h, head, [words["company"]]),
    }
    asking, approving = await _as(h, head), await _as(h, approver)
    if await _verify(h, asking, placed["company"], review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("a department admin could not verify their own document")
    card = await _propose(h, asking, placed["company"])
    if card is None or not await _approve(h, approving, card):
        raise CheckFailedError("a verified document could not be made company-wide")

    expected = {
        member: {"mine", "a", "company"},
        head: {"heads", "a", "company"},
        owner: {"a", "b", "company"},
    }
    for who, reaches in expected.items():
        nothing, _ = await _found(h, who, h.word())
        for place, word in words.items():
            found, kept = await _found(h, who, word)
            if place in reaches:
                if _found_documents(found) != [placed[place]] or not any(
                    word in str(one.get("document", "")) for one in kept
                ):
                    raise CheckFailedError("a reader was not given an item their scope covers")
            elif (found.records, found.truncated, found.source) != (
                nothing.records,
                nothing.truncated,
                nothing.source,
            ):
                raise CheckFailedError(
                    "a reader was given, or told of, an item outside their scope"
                )

    await _table_columns(h, table, {member: False, head: True, owner: True})


async def _table_columns(h: Harness, table: Any, held: dict[str, bool]) -> None:
    """Each reader's read of the uploaded table: its one row, with the held column only if held."""
    from brain.knowledge.classified_rows import TABLES_SOURCE
    from brain.knowledge.rows import RowRequest
    from brain.ops.acceptance_checks_tables import _Application
    from brain.ops.classification_store import classified_lane_of

    lane = await classified_lane_of(_Application(h.sessions))
    reader = lane.readers.get((TABLES_SOURCE, table.entity))
    if reader is None:
        raise CheckFailedError("the uploaded table had no reader on Ask's lane")
    for who, holds in held.items():
        found = await reader(RowRequest(), entitlement=await h.reach(who), now=h.now)
        rows = [one.model_dump() for one in found.records]
        if len(rows) != 1 or str(rows[0].get(table.open_column)) != table.seen:
            raise CheckFailedError("a reader of the uploaded table was not given its row")
        if (table.held_column in rows[0]) is not holds:
            raise CheckFailedError("a reader was given a column other than the ones they may read")
