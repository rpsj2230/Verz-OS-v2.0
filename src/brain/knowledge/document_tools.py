"""The document plane as two tools, so an agent built to read knowledge has something to call.

`brain.knowledge.search` decides what a caller may retrieve and `brain.knowledge.assembly`
arranges what came back, and until 2026-09-14 nothing registered either as a tool. Ten
templates in `brain.agents.catalogue` name `knowledge.read` or `knowledge.search` on their
leash, and `brain.tools.startup.build_registry` registered row tools only, so every one of them
was an agent with no tool to reach for, which `brain.gate.invoke.invoke` refuses to start.

**Two tools, because the catalogue wrote two verbs.** `knowledge.search_documents` answers a
question with passages, fused by `hybrid`; `knowledge.read_document` hands back one document's
passages in reading order. `brain.agents.install.bind_tool` binds a declaration by entity and
verb, so `knowledge.search` binds the first and `knowledge.read` the second, and a single tool
carrying both would put two supervision targets on one name.

**Every statement carries the reach, and the reach is `reach_for`'s.** Nothing here decides what
a caller may see. The caller's `Reach` comes from `brain.knowledge.search.reach_for` and every
chunk statement is built with `reach_predicate` in its WHERE clause, including the second one
that fetches the bodies of what the lexical leg ranked, so a body the caller may not read is
never fetched to be dropped. See `THE_DOCUMENT_PLANE_IS_READ_THROUGH_ITS_OWN_REACH`.

**The tools read through the application's `RowSource`, because it is the only database handle
the registry has.** `build_registry` is handed a row source or nothing, and a tool that is
present and cannot answer is worse than an absent one, so these are registered through the
same door as the row tools and exactly when they are. `RowSource` is "whatever runs a
statement and hands back mappings keyed by the labels", and a chunk statement is a statement.

**Every chunk statement carries the settings the second wall reads.** The second wall on
`know.chunk` is the row-level security policy in 0009, which reads `app.principal_id` and
`app.departments`. Until 2026-09-14 `brain.knowledge.row_store.SessionRowSource` ran one
statement per session and no settings, so on a real database the policy saw neither and
admitted company-visible chunks only: a person asking through these tools reached the company's
documents and not their own department's or their own. It failed closed, and it made "answering
with knowledge" false for everything that was not company-wide. Now each chunk statement is a
`RowQuery` carrying `brain.knowledge.search.session_settings` for the same `Reach` its
`reach_predicate` was built from, and the source runs them in the statement's transaction. One
`Reach` builds both walls, so they cannot be built for two different callers. See
`THE_SECOND_WALL_IS_RAISED_BY_EVERY_CHUNK_STATEMENT`.

**The iterative scan settings are not carried, because nothing here reads the vector index.**
`brain.knowledge.search.iterative_scan_statements` tunes how the HNSW index is walked under a
filter, and only `vector_query` walks it. These tools fuse the lexical legs with an empty vector
leg, because this process has no embedding of the question to search with, so carrying them
would set two index parameters on statements that never touch the index. The day a vector leg is
added here, its statement carries both, and a test fails first to say so. See
`NO_STATEMENT_HERE_WALKS_THE_VECTOR_INDEX`.

**The departments are read from `gate.department`, on each call.** `reach_for` needs the
registry of departments, because a grant with no department clause reaches every department
and the second wall takes names rather than a wildcard. `gate.department`'s policy is
`deleted_at IS NULL` alone, so this read needs no session settings. Read per call rather than
at start-up, so a department added this morning is reachable this morning.

**The definitions name no source.** `ToolDefinition.source` is the system a record came from,
and `brain.api_routes.row_readers` reads a set source as a row tool to hand the answer lane.
The document plane is the product's own and not a system anybody installed, so the field is
left empty and the lane never mistakes a knowledge tool for a reader of rows. See
`A_KNOWLEDGE_TOOL_NAMES_NO_SOURCE`.

Two designs were rejected.

*One knowledge tool per department, or per source.* The plane is not per anything: a chunk
carries its own visibility, and the reach predicate is what narrows. A tool per department
would be a second place that decides which department a caller reaches.

*A second protocol beside `RowSource` for chunk statements, handed to `build_registry`.* It
would have raised the second wall without touching the row plane, and it would register the
knowledge tools only on processes handed it, so an install with a database and rows would carry
row tools and no document tools while every knowledge template badged itself incomplete for a
reason nobody could find. A query that carries its own settings raises the same wall through the
door that already exists.

*Settings run by the handler, through a session it opens itself.* The handler holds a
`RowSource` and not a session, and the only way to share a transaction with a statement the
source runs is to be run by the source.

Task ids: M15.2.6, M15.3.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import TextClause
from sqlalchemy.sql import Select

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.assembly import RetrievedChunk, by_chunk, by_document
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.rows import RowQuery, RowSource
from brain.knowledge.search import (
    CANDIDATE_DEPTH,
    CHUNK,
    KNOWLEDGE_READ,
    RETRIEVABLE_STATE_VALUES,
    Reach,
    cjk_lexical_query,
    hybrid,
    lexical_legs,
    lexical_query,
    reach_for,
    reach_predicate,
    session_settings,
)
from brain.tables.gate import DepartmentRow

# ------------------------------------------------------------------ written-down reasons

#: Why nothing in this module decides what a caller may retrieve.
THE_DOCUMENT_PLANE_IS_READ_THROUGH_ITS_OWN_REACH: Final = (
    "What a caller may retrieve is decided by brain.knowledge.search.reach_for and applied by "
    "reach_predicate inside every statement, the statement fetching bodies included. A tool "
    "that filtered what came back, or fetched bodies by reference alone because the ranking "
    "query had already applied the reach, would be a second decision about the same question, "
    "and the second one is the one that drifts."
)

#: Why every chunk statement carries session settings. See the module docstring.
THE_SECOND_WALL_IS_RAISED_BY_EVERY_CHUNK_STATEMENT: Final = (
    "know.chunk's row-level security reads app.principal_id and app.departments, which "
    "set_config writes for one transaction. A chunk statement with no settings is admitted "
    "company-visible chunks only, so a person's own department's documents and their own "
    "never come back, and nothing raises to say so. Every chunk statement therefore carries "
    "session_settings for the Reach its reach_predicate was built from, and the row source "
    "runs them in the statement's own transaction."
)

#: Why the iterative scan settings are not carried. See the module docstring.
NO_STATEMENT_HERE_WALKS_THE_VECTOR_INDEX: Final = (
    "iterative_scan_statements tunes how the HNSW index is walked under a filter, and only a "
    "vector leg walks it. These tools fuse the lexical legs with an empty vector leg, so the "
    "settings would tune an index no statement here reads. A vector leg added here carries "
    "them with its statement."
)

#: Why the definitions leave `source` empty.
A_KNOWLEDGE_TOOL_NAMES_NO_SOURCE: Final = (
    "ToolDefinition.source names the system a record came from, and "
    "brain.api_routes.row_readers treats a definition with a source as a row reader for the "
    "answer lane. The document plane is the product's own rather than a system somebody "
    "installed, so the field is empty and the lane never hands a question to a knowledge tool "
    "as though it were a table of rows."
)

# ------------------------------------------------------------------ the vocabulary

#: The entity both tools return, and the noun every knowledge capability is written about:
#: `read:knowledge` reaches the plane, `read:knowledge.document` and its siblings the fields.
KNOWLEDGE_ENTITY: Final = "knowledge"

#: The first segment of both names. The registry reads it as `RegisteredTool.source`; it names
#: the plane rather than a system, for the reason `A_KNOWLEDGE_TOOL_NAMES_NO_SOURCE` gives.
KNOWLEDGE_TOOL_PREFIX: Final = "knowledge"

#: What `knowledge.search` binds to.
SEARCH_DOCUMENTS: Final = f"{KNOWLEDGE_TOOL_PREFIX}.search_documents"

#: What `knowledge.read` binds to.
READ_DOCUMENT: Final = f"{KNOWLEDGE_TOOL_PREFIX}.read_document"

SEARCH_DESCRIPTION: Final = (
    "Search the company's documents for the passages that answer a question, from the "
    "documents this caller may already read"
)
READ_DESCRIPTION: Final = (
    "Read the passages of one document by its reference, in reading order, when this caller "
    "may already read that document"
)

#: How long a question may be. A question is a sentence, and the lexical leg binds it whole.
QUESTION_CHARS: Final = 1000

#: How many passages a call returns unless it asks for fewer. Bounded by `CANDIDATE_DEPTH`,
#: which a test holds: a page longer than one leg's candidates is a page the fusion cannot fill.
DEFAULT_PASSAGES: Final = 10
MAX_PASSAGES: Final = 50

#: The standing narrowing both tools apply, in the type the registry's SERVICE rule reads.
#:
#: Not compiled from here. `reach_predicate` carries the same condition inside every chunk
#: statement, and a test holds the values equal to `RETRIEVABLE_STATE_VALUES`, so the scope a
#: reader of the registry sees is one the statements actually apply rather than the
#: unrestricted scope that rule exists to refuse.
KNOWLEDGE_PIN: Final = Scope(
    clauses=(Clause(field="state", op=Op.IN, value=RETRIEVABLE_STATE_VALUES),)
)

#: The columns a passage is built from, labelled as `know.chunk` names them.
PASSAGE_COLUMNS: Final[tuple[str, ...]] = (
    "chunk_id",
    "document_id",
    "ordinal",
    "body",
    "title",
    "section",
    "updated_at",
)

#: The query builder for each lexical leg `lexical_legs` can name. A leg added there and not
#: here is a `KeyError` on the first question in that script, which a test asks.
LEXICAL_LEG_QUERIES: Final[Mapping[str, Callable[..., Select[Any]]]] = MappingProxyType(
    {"tsv": lexical_query, "tsv_cjk": cjk_lexical_query}
)


# ------------------------------------------------------------------ what a model may ask
class DocumentSearch(BaseModel):
    """A question, and how many passages to hand back. The question is bound, never spliced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(min_length=1, max_length=QUESTION_CHARS)
    limit: int = Field(default=DEFAULT_PASSAGES, ge=1, le=MAX_PASSAGES)


class DocumentRead(BaseModel):
    """One document, by the reference a passage from `knowledge.search_documents` carried."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(pattern=ITEM_ID_PATTERN)
    limit: int = Field(default=MAX_PASSAGES, ge=1, le=MAX_PASSAGES)


# ------------------------------------------------------------------ what comes back
class KnowledgePassage(Entity):
    """One passage, tagged so the redactor can walk it.

    The field names are the ones the catalogue's and the starter pack's capabilities already
    name, `read:knowledge.document`, `.title`, `.section` and `.updated_at`, so the passage
    body is `document`. `document_id` is carried so a passage can be cited and its document
    read, which is what `knowledge.read_document` takes.
    """

    document_id: str
    title: str = ""
    section: str = ""
    document: str
    updated_at: str = ""


# ------------------------------------------------------------------ the statements
def _query(
    entity: str,
    columns: tuple[str, ...],
    statement: Select[Any],
    empty: bool,
    *,
    settings: tuple[TextClause, ...],
) -> RowQuery:
    """A row query on the document plane. `settings` has no default, so every statement
    written here says whether the second wall reads anything, rather than inheriting nothing."""
    return RowQuery(
        entity=entity,
        source=KNOWLEDGE_TOOL_PREFIX,
        columns=columns,
        statement=statement,
        certainly_empty=empty,
        settings=settings,
    )


def departments_query() -> RowQuery:
    """Every live department's slug, which is the registry `reach_for` intersects a grant with.

    No settings: `gate.department`'s policy is `deleted_at IS NULL` alone, and this runs before
    there is a `Reach` to build any from.
    """
    statement = (
        sa.select(DepartmentRow.slug.label("slug"))
        .where(DepartmentRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug)
    )
    return _query("department", ("slug",), statement, empty=False, settings=())


def search_queries(question: str, *, reach: Reach) -> tuple[RowQuery, ...]:
    """A ranked statement per lexical leg the question needs, in the order `lexical_legs` gives."""
    return tuple(
        _query(
            KNOWLEDGE_ENTITY,
            ("chunk_id", "relevance"),
            LEXICAL_LEG_QUERIES[leg](question, reach=reach, depth=CANDIDATE_DEPTH),
            empty=False,
            settings=session_settings(reach),
        )
        for leg in lexical_legs(question)
    )


def _passage_select() -> Select[Any]:
    return sa.select(*(CHUNK.c[name].label(name) for name in PASSAGE_COLUMNS))


def passages_query(chunk_ids: Sequence[str], *, reach: Reach) -> RowQuery:
    """The bodies of the passages a ranking returned, under the reach again.

    The reach is applied a second time on purpose. The ranking and the bodies are two
    statements, and a body fetched by reference alone would trust that the reference came from
    a statement carrying this caller's reach, which is a property of the caller of this
    function rather than of the query. See `THE_DOCUMENT_PLANE_IS_READ_THROUGH_ITS_OWN_REACH`.

    Certainly empty when there are no references, so the handler does not ask.
    """
    statement = (
        _passage_select()
        .where(sa.and_(reach_predicate(reach), CHUNK.c.chunk_id.in_(list(chunk_ids))))
        .order_by(CHUNK.c.chunk_id)
    )
    return _query(
        KNOWLEDGE_ENTITY,
        PASSAGE_COLUMNS,
        statement,
        empty=not chunk_ids,
        settings=session_settings(reach),
    )


def document_query(document_id: str, *, reach: Reach, limit: int) -> RowQuery:
    """One document's passages in reading order, under the reach."""
    statement = (
        _passage_select()
        .where(sa.and_(reach_predicate(reach), CHUNK.c.document_id == document_id))
        .order_by(CHUNK.c.ordinal, CHUNK.c.chunk_id)
        .limit(limit)
    )
    return _query(
        KNOWLEDGE_ENTITY, PASSAGE_COLUMNS, statement, empty=False, settings=session_settings(reach)
    )


# ------------------------------------------------------------------ the handlers
async def reach_through(
    records: RowSource, entitlement: EntitlementSet, now: datetime | None
) -> Reach | None:
    """The caller's reach, computed by `reach_for` against the live department registry."""
    departments = [str(row["slug"]) for row in await records.rows(departments_query())]
    return reach_for(entitlement, departments=departments, now=now)


def _passages(
    order: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> tuple[KnowledgePassage, ...]:
    """Passages in document order, through `by_chunk` and `by_document`.

    The order decides membership and the rows only supply text, which is `by_chunk`'s own
    property: a row the order did not name is never returned.
    """
    fetched = {str(row["chunk_id"]): row for row in rows}
    chunks = {
        ref: RetrievedChunk(
            chunk_id=ref,
            document_id=str(row["document_id"]),
            ordinal=int(row["ordinal"]),
            text=str(row["body"]),
            title=str(row["title"]),
            section=str(row["section"]),
        )
        for ref, row in fetched.items()
    }
    return tuple(
        KnowledgePassage(
            entity=KNOWLEDGE_ENTITY,
            id=passage.chunk_id,
            document_id=passage.document_id,
            title=passage.title,
            section=passage.section,
            document=passage.text,
            updated_at=fetched[passage.chunk_id]["updated_at"].isoformat(),
        )
        for found in by_document(by_chunk(order, chunks))
        for passage in found.passages
    )


def _result(
    passages: tuple[KnowledgePassage, ...], now: datetime | None, *, truncated: bool
) -> TypedResult[KnowledgePassage]:
    return TypedResult(
        records=passages,
        source=KNOWLEDGE_TOOL_PREFIX,
        # No clock is read here, for the reason `brain.knowledge.rows.read_rows` gives.
        fetched_at=now.isoformat() if now is not None else "",
        truncated=truncated,
    )


def searcher(records: RowSource) -> Callable[..., Awaitable[TypedResult[KnowledgePassage]]]:
    """The handler for `knowledge.search_documents`, bound to where the chunks are read.

    A closure, as `RowTool.reader` is, so the signature a registry inspects carries only what a
    model may pass.
    """

    async def search(
        request: DocumentSearch,
        *,
        entitlement: EntitlementSet,
        now: datetime | None = None,
    ) -> TypedResult[KnowledgePassage]:
        reach = await reach_through(records, entitlement, now)
        if reach is None:
            return _result((), now, truncated=False)
        legs = [
            await records.rows(query) for query in search_queries(request.question, reach=reach)
        ]
        # One ranking from the legs in the order they arrived, each passage once: a chunk that
        # matches in two scripts is one passage, and `Ranking` refuses it listed twice.
        lexical = tuple(dict.fromkeys(str(row["chunk_id"]) for rows in legs for row in rows))
        page = [one.ref for one in hybrid(lexical=lexical, vector=(), limit=request.limit)]
        bodies = passages_query(page, reach=reach)
        rows = () if bodies.certainly_empty else await records.rows(bodies)
        return _result(_passages(page, rows), now, truncated=len(page) == request.limit)

    return search


def reader(records: RowSource) -> Callable[..., Awaitable[TypedResult[KnowledgePassage]]]:
    """The handler for `knowledge.read_document`, bound to where the chunks are read."""

    async def read(
        request: DocumentRead,
        *,
        entitlement: EntitlementSet,
        now: datetime | None = None,
    ) -> TypedResult[KnowledgePassage]:
        reach = await reach_through(records, entitlement, now)
        if reach is None:
            return _result((), now, truncated=False)
        query = document_query(request.document_id, reach=reach, limit=request.limit)
        rows = await records.rows(query)
        order = [str(row["chunk_id"]) for row in rows]
        return _result(_passages(order, rows), now, truncated=len(rows) == request.limit)

    return read


# ------------------------------------------------------------------ the definitions
def search_definition() -> ToolDefinition:
    """What the catalogue describes for `knowledge.search_documents`."""
    return ToolDefinition(
        name=SEARCH_DOCUMENTS,
        description=SEARCH_DESCRIPTION,
        entity=KNOWLEDGE_ENTITY,
        args_schema=DocumentSearch.model_json_schema(),
        required_capability=KNOWLEDGE_READ.value,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.SERVICE,
    )


def read_definition() -> ToolDefinition:
    """What the catalogue describes for `knowledge.read_document`."""
    return ToolDefinition(
        name=READ_DOCUMENT,
        description=READ_DESCRIPTION,
        entity=KNOWLEDGE_ENTITY,
        args_schema=DocumentRead.model_json_schema(),
        required_capability=KNOWLEDGE_READ.value,
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.SERVICE,
    )


def knowledge_tools(
    records: RowSource,
) -> tuple[tuple[ToolDefinition, Callable[..., Awaitable[TypedResult[KnowledgePassage]]]], ...]:
    """Both tools, each with its handler bound to `records`, for `build_registry` to register."""
    return ((search_definition(), searcher(records)), (read_definition(), reader(records)))
