"""The knowledge library, the learning review and the memory viewer over HTTP, and what each
one's store cannot yet tell it.

`brain.console.govern_estate` decides three Govern screens the design draws: SCREEN 7 of
`docs/screens.html` is Knowledge, SCREEN 8 is Learning, and the memory card inside SCREEN 13
is the change history a person's memory carries. `library_rows` and `departments_represented`
decide what a reader may know exists and how the rows may be grouped, `learning_review` keeps
the three tiers apart and withholds tier three on the narrower basis, and `subject_memory`
decides which memories about one person a reader may read and which revisions they may diff.
None of the three could be reached from a browser. This module is the read they sit behind,
and nothing in it decides who may see anything: every route asks
`brain.console.reads.permitted` whether its screen opens, loads, hands the rows to the
function that owns the decision, and projects what comes back. See
`brain.govern_routes.THE_SCREEN_DECIDES_NOTHING_AND_THE_CONSOLE_MODULE_DECIDES_EVERYTHING`.

**All three stores are empty on every install today, and the routes are written for the day
they are not.** `brain.knowledge.item_store.put_item` says in its own docstring that nothing
calls it outside the tests. Nothing writes `mem.persistent` or `mem.adaptive` either, and
nothing stores a learning's tier, the change it proposed or what it replaced. So the library
and the viewer read real tables through real decisions and answer nothing, and the review has
no table to read at all. Each response says which of its facts has no source rather than
drawing an empty table that reads as a company with no knowledge, no learning and no memory.

**The library shows two facts per item, because the decision admits two.** `LibraryRow` is an
item's reference and its visibility level, and `brain.console.govern_estate.
A_VISIBILITY_PREDICATE_NAMES_A_DEPARTMENT_AND_AN_OWNER` is why the department and the owner are
not on it: they are the two halves of the predicate. The screen is registered on the existence
plane, so the title and the verification are not on it either. SCREEN 7 draws eight columns and
this answers two; `only_existence_and_reach_are_shown` is that fact on the response. See
`A_LIBRARY_ROW_SAYS_AN_ITEM_EXISTS_AND_HOW_WIDELY_IT_REACHES`.

**Freshness and use are not measured here, and the reason is the row rather than a choice.**
SCREEN 7's Fresh figure and its coverage bars are `brain.console.operate.coverage`, which
takes whole `KnowledgeItem`s, and a `KnowledgeItem` refuses to construct without its text.
`know.item` holds no text on purpose: its own docstring says a second copy of the corpus
outside the reach predicate is the thing it refuses to be. Never retrieved and Used 30d need a
count of retrievals per document, and nothing records one. See
`FRESHNESS_NEEDS_A_WHOLE_DOCUMENT_AND_THE_ROW_HOLDS_NONE`.

**The library is not filtered on the server, because a filter makes `truncated` an oracle.**
A department filter answering "the load came back full" tells a reader who cannot see finance
that finance holds at least a page of documents. The load is the whole retrievable table,
bounded, and the page narrows what it already holds. See
`A_FILTER_ON_THE_SERVER_TURNS_A_TRUNCATION_FLAG_INTO_A_COUNT`.

**The learning review is empty by construction, and tier-one undo is not a route.** Undoing a
tier-one learning is `brain.memory.digest.undo`, which returns a `Supersession` or a `Demotion`
for whoever owns the correction table, and there is no correction table. There is also nothing
that recalls from memory at request time, so a written correction would change no answer.
A route that accepted an undo would answer 200 for a write that reaches neither a row nor a
behaviour, which is `docs/admin-console.md`'s "a control that renders but reaches nothing is
worse than no control at all". See
`AN_UNDO_WITH_NO_CORRECTION_STORE_REACHES_NEITHER_A_ROW_NOR_A_BEHAVIOUR`.

**The memory viewer is asked about one person and says nothing about how much there is.** A
subject is required, which is `brain.console.govern_estate.
A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE`. What this adds is the bound: the
load is keyed by a name the caller typed, so a flag saying it came back full would say a
person has at least that many memories, readable or not. See
`A_TRUNCATION_FLAG_ON_A_LOOKUP_BY_PERSON_COUNTS_WHAT_IS_REMEMBERED_ABOUT_THEM`.

**Memory is a Govern screen and not a tab inside an agent, although SCREEN 13 draws it in
one.** The design places a memory card on one agent's page and has no company-level memory
screen. `brain.console.screens` registers `memory` under Govern, and the decision it serves,
`subject_memory`, is keyed by the person a memory is about. Neither memory table records the
agent that was running, so a per-agent tab would have nothing to select on.

**Whether a screen opens is `permitted` and it is asked before anything else.** The Library
screen is the existence plane, Learning and Memory are the content plane, and a hand-written
`reach.holds` would answer an existence-only reader a content screen. The question comes before
a session is reached for, so a caller with no grant cannot tell an instance with a database from
one without.

**Nothing here computes a reach.** There is no `.intersect(` in this module.
`brain.console.workspace.intersections_in` is run over this source by its test.

**What has never run.** This repository has no PostgreSQL, so neither load has been executed
against one. What is tested is the statement each compiles to, every refusal and the order it
happens in, and each decision reached through the real application.

Task ids: M27.7.20, M27.7.21, M27.7.22
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, Placed
from brain.console.govern_estate import (
    LibraryItem,
    departments_represented,
    learning_review,
    library_rows,
    spans_departments,
    subject_memory,
)
from brain.console.reach_view import (
    MemoryText,
    MemoryViewError,
    Revision,
    TierOneRow,
    TierThreeRouting,
    TierTwoRow,
    provenance_of,
)
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import Basis
from brain.core.entitlement import Capability
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.knowledge.item import RETRIEVABLE_STATES
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.memory.correction import Demotion, Supersession
from brain.memory.formation import Formation, MemoryKind
from brain.memory.tiers import BLAST_RADIUS, Tier
from brain.ops.replica_store import ConsoleReads
from brain.routing_routes import sessions_of
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.memory import PRINCIPAL_ID_CHARS, AdaptiveMemoryRow, PersistentMemoryRow

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why a library row is two facts when the design draws eight columns.
A_LIBRARY_ROW_SAYS_AN_ITEM_EXISTS_AND_HOW_WIDELY_IT_REACHES: Final = (
    "SCREEN 7 of docs/screens.html lists Item, Dept, Type, Visible to, Owner, Verified, Review "
    "due and Used 30d. brain.console.govern_estate.LibraryRow carries the item's reference and "
    "its visibility level, and nothing else: the department and the owner are the two halves of "
    "the visibility predicate, which that module refuses to put on a row, and the Library screen "
    "is registered on the existence plane, which says a document is there and never what it "
    "says or who vouched for it. A route adding the title or the owner would be a second answer "
    "to what this screen may show, so the response says which facts are withheld instead."
)

#: Why the freshness and use figures on SCREEN 7 have no source here.
FRESHNESS_NEEDS_A_WHOLE_DOCUMENT_AND_THE_ROW_HOLDS_NONE: Final = (
    "brain.console.operate.coverage decides freshness per department and takes whole "
    "KnowledgeItem values, and KnowledgeItem refuses to construct without its text. know.item "
    "stores no text, deliberately, so the decision has no input that could be built from the "
    "table without inventing the corpus. Never retrieved and Used 30d need a count of "
    "retrievals per document and nothing records one. The response says both are unmeasured "
    "rather than drawing a figure of zero, which would read as a library nobody uses."
)

#: Why the library has no department, level or search parameter.
A_FILTER_ON_THE_SERVER_TURNS_A_TRUNCATION_FLAG_INTO_A_COUNT: Final = (
    "truncated says the load came back full. Over the whole table that is a fact about the "
    "install. Over a load narrowed by a department the caller typed, it says that department "
    "holds at least a page of documents, which a reader who cannot see that department learns "
    "without being shown a row. So the load is never narrowed by a parameter, and the page "
    "filters and sorts the rows it already holds, saying that is what it did."
)

#: Why the learning review answers three empty tiers and a flag.
NOTHING_STORES_A_LEARNING_SO_THE_REVIEW_HAS_NOTHING_TO_NARROW: Final = (
    "brain.memory.digest.Learning is a proposal, a formation, evidence and what it replaced, "
    "and no table in this repository stores one: mem.persistent and mem.adaptive hold the "
    "formation and the statement and record no change kind, no tier and no agent. So "
    "learning_review is asked over nothing, the tiers come back empty, and the response carries "
    "learnings_are_not_recorded so the page says an empty review is an absence of a store and "
    "not a system that has learnt nothing."
)

#: Why there is no undo route.
AN_UNDO_WITH_NO_CORRECTION_STORE_REACHES_NEITHER_A_ROW_NOR_A_BEHAVIOUR: Final = (
    "brain.memory.digest.undo returns a Supersession or a Demotion for whoever owns the table, "
    "and nothing owns one: no migration creates a correction table. Nothing recalls from memory "
    "while answering a question either, so a correction written somewhere would change no "
    "answer. A route accepting an undo would answer success for a write that reaches no row and "
    "no behaviour, and docs/admin-console.md says a control that cannot be proved end to end is "
    "not shipped as working. undo_is_not_writable says so on the response."
)

#: Why the memory viewer carries no truncation flag.
A_TRUNCATION_FLAG_ON_A_LOOKUP_BY_PERSON_COUNTS_WHAT_IS_REMEMBERED_ABOUT_THEM: Final = (
    "The memory load is keyed by a person the caller named. A flag saying the load came back "
    "full would say that person has at least that many memories, including ones this reader "
    "may not recall, which is a count of hidden items arrived at by a boolean. So the bound is "
    "stated as a constant on every response, identical for every person and every reader, and "
    "nothing on the response varies with how many rows the load found."
)


# ----------------------------------------------------------------- the screens

#: The screens these routes answer, as `brain.console.screens` keys them. Keys rather than
#: capabilities spelled out, so nothing here can drift from the registry.
LIBRARY_SCREEN: Final = "library"
LEARNING_SCREEN: Final = "learning"
MEMORY_SCREEN: Final = "memory"


# ------------------------------------------------------------------ the bounds

#: The most knowledge items one library answer is assembled from. A resource bound and not a
#: permission one: `library_rows` narrows what came back, and `truncated` says the load was full.
MAX_ITEMS_CONSIDERED: Final = 2000

#: What a caller gets when they do not say.
DEFAULT_ITEMS_CONSIDERED: Final = 500

#: The most memories of each kind one viewer answer is assembled from, newest first. Sent on
#: every response as a constant; see
#: `A_TRUNCATION_FLAG_ON_A_LOOKUP_BY_PERSON_COUNTS_WHAT_IS_REMEMBERED_ABOUT_THEM`.
MAX_MEMORIES_CONSIDERED: Final = 200

#: What a stated memory was worth when it was formed. `mem.persistent` has no confidence column
#: and `brain.memory.digest.Learning.formed_confidence` defaults to certain for the same kind
#: of memory, so a row read back is handed to recall on the terms it was written on.
STATED_CONFIDENCE: Final = 1.0


# ------------------------------------------------------------------- the shapes


class LibraryRowView(BaseModel):
    """One item on the library: that it exists, and how widely it reaches.

    `brain.console.govern_estate.LibraryRow`, copied field by field, and no third field. See
    `A_LIBRARY_ROW_SAYS_AN_ITEM_EXISTS_AND_HOW_WIDELY_IT_REACHES`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    level: Visibility


class LibraryPage(Page[LibraryRowView]):
    """Every retrievable item this reader may know exists, and how the rows may be grouped.

    `total` is inherited and never populated: the rows are narrowed per caller, so a count
    would be the subtraction the disclosure rule forbids.
    """

    #: The load came back full. Never how much more there is.
    truncated: bool = False
    #: `departments_represented`' answer: the departments the rows may be grouped by, or null
    #: when this reader may not be shown a grouping. Null is not "no departments".
    departments: tuple[str, ...] | None = None
    staleness: StalenessBanner | None = None
    #: Title, owner, department, type and verification are not on a row. See
    #: `A_LIBRARY_ROW_SAYS_AN_ITEM_EXISTS_AND_HOW_WIDELY_IT_REACHES`.
    only_existence_and_reach_are_shown: bool = True
    #: Nothing here can say how fresh an item is or how often it is used. See
    #: `FRESHNESS_NEEDS_A_WHOLE_DOCUMENT_AND_THE_ROW_HOLDS_NONE`.
    freshness_and_use_are_not_measured: bool = True


class TierOneView(BaseModel):
    """One automatic change, as `brain.console.reach_view.TierOneRow` carries it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    change: str
    #: What undoing it would write, which is a mark and never a removal.
    control_writes: str
    learned_at: datetime


class TierTwoView(BaseModel):
    """One proposed rule, its evidence kinds and whether it may be promoted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    change: str
    evidence: tuple[str, ...]
    promote_ready: bool
    learned_at: datetime


class TierThreeView(BaseModel):
    """Where one gated change was routed, and the key back to its agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    department: str
    back_to: str


class TierRuleView(BaseModel):
    """One tier and every kind of change that needs it, from `brain.memory.tiers.BLAST_RADIUS`.

    A constant of the product, identical on every install and for every reader, which is why
    it may be shown to anybody who opens the screen. It is the one part of SCREEN 8 that is
    true today whatever has been recorded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: int
    changes: tuple[str, ...]


class LearningReviewView(BaseModel):
    """The three tiers, kept apart, with tier three absent on the narrower basis.

    `tier_three` null means this reader may not be shown where gated changes were routed, and
    is never an empty list standing in for it: see `brain.console.govern_estate.
    TIER_THREE_IS_THE_ONLY_LEARNING_ROW_THAT_NAMES_A_DEPARTMENT`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    basis: Basis
    #: The instant the review was assembled at, so the page can say what "the last seven days"
    #: means without reading a clock of its own.
    as_of: datetime
    tier_one: tuple[TierOneView, ...]
    tier_two: tuple[TierTwoView, ...]
    tier_three: tuple[TierThreeView, ...] | None
    tiers: tuple[TierRuleView, ...]
    #: See `NOTHING_STORES_A_LEARNING_SO_THE_REVIEW_HAS_NOTHING_TO_NARROW`.
    learnings_are_not_recorded: bool = True
    #: See `AN_UNDO_WITH_NO_CORRECTION_STORE_REACHES_NEITHER_A_ROW_NOR_A_BEHAVIOUR`.
    undo_is_not_writable: bool = True


class MemoryTextView(BaseModel):
    """One memory in its own words, as `brain.console.reach_view.MemoryText` admitted it.

    The confidence is the recollection's, after decay, and the instant is the formation's. The
    scope the reader reaches it at is not carried: it is a predicate, and the memory card in
    SCREEN 13 draws none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    statement: str
    confidence: float
    formed_at: datetime


class RevisionView(BaseModel):
    """One step in the history, as `brain.console.reach_view.Revision` built it.

    `diff` is empty when the reader was not admitted to both sides, and nothing here says which
    side, for that type's reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    replaced_id: str | None
    at: datetime
    diff: tuple[str, ...]
    trigger: str | None
    correction: str | None


class SubjectMemoryView(BaseModel):
    """What this reader may read of what is remembered about one person, and its history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_id: str
    curated: tuple[MemoryTextView, ...]
    extracted: tuple[MemoryTextView, ...]
    history: tuple[RevisionView, ...]
    #: How many memories of each kind the load reads at most. A constant, never a measurement.
    considered_per_kind: int = MAX_MEMORIES_CONSIDERED
    staleness: StalenessBanner | None = None
    #: Nothing stores a supersession, a demotion or what a memory replaced, so no revision here
    #: carries a diff or a trigger yet.
    corrections_are_not_recorded: bool = True
    #: There is no route that edits or deletes a memory from this screen. See the module
    #: docstring on the undo, whose store is the same missing table.
    edit_is_not_writable: bool = True


# ---------------------------------------------------------------- the statements


def retrievable_items(limit: int) -> Select[tuple[KnowledgeItemRow]]:
    """Every item the system can draw on, in reference order, at most `limit` of them.

    `RETRIEVABLE_STATES` rather than every row, because the screen is "every document the
    system can draw on" in `brain.console.screens`' own words, and a superseded or archived item
    listed at its old level would say it still reaches that audience. A load narrowing and not a
    permission one: nothing a reader holds changes it. Ordered, so two readings of an unchanged
    table are the same page and the rows that fall off a full load are always the same ones.
    """
    return (
        select(KnowledgeItemRow)
        .where(KnowledgeItemRow.state.in_(sorted(one.value for one in RETRIEVABLE_STATES)))
        .order_by(KnowledgeItemRow.item_id)
        .limit(limit)
    )


def stated_about(subject_id: str, limit: int) -> Select[tuple[PersistentMemoryRow]]:
    """What people stated, formed while `subject_id` was asking, newest first."""
    return (
        select(PersistentMemoryRow)
        .where(PersistentMemoryRow.principal_id == subject_id)
        .order_by(PersistentMemoryRow.formed_at.desc(), PersistentMemoryRow.id)
        .limit(limit)
    )


def inferred_about(subject_id: str, limit: int) -> Select[tuple[AdaptiveMemoryRow]]:
    """What the system inferred, formed while `subject_id` was asking, newest first."""
    return (
        select(AdaptiveMemoryRow)
        .where(AdaptiveMemoryRow.principal_id == subject_id)
        .order_by(AdaptiveMemoryRow.formed_at.desc(), AdaptiveMemoryRow.id)
        .limit(limit)
    )


# ------------------------------------------------------------------ rows to records


def placed_item(row: KnowledgeItemRow) -> Placed[LibraryItem]:
    """One stored item, as the pair `library_rows` narrows.

    `where` is the department the item sits in, which is the place question that function
    asks, and the empty mapping when the row names none. That fails closed: `Clause.matches`
    refuses a field the row does not have, so an item with no department is known to exist
    only by a reader whose grant is company-wide, which is `brain.console.govern.NOWHERE`'s own
    argument.

    No refusal to catch. `know.item`'s constraints admit only the three visibility words, a
    non-empty owner and a department slug, and the column widths are `KnowledgeVisibility`'s,
    so every stored row constructs.
    """
    visibility = KnowledgeVisibility(
        level=Visibility(row.visibility),
        owner_id=row.owner_id,
        department=row.department or "",
    )
    return Placed(
        record=LibraryItem(item_id=row.item_id, visibility=visibility),
        where={"department": row.department} if row.department else NOWHERE,
    )


@dataclass(frozen=True)
class StoredMemory:
    """One memory row, as `brain.console.reach_view.Remembered` reads it.

    Not a `Learning`, because a row records no proposal. See `Remembered`. `replaced_id` is
    always `None`: no column records what a memory replaced.
    """

    memory_id: str
    formation: Formation
    formed_confidence: float
    replaced_id: str | None = None


def stored_memory(
    row: PersistentMemoryRow | AdaptiveMemoryRow,
) -> tuple[StoredMemory, str] | None:
    """One row and its statement, or `None` when the row does not describe a memory a viewer
    can show.

    Three refusals and one answer. A kind no `MemoryKind` names, a session kind, which
    `provenance_of` refuses because a session memory lives in neither table, and a formation
    whose capability tags or scope the types refuse. `mem.*.kind` has no check constraint and a
    tag column is only bounded by width, so each of these can be on disk. The row is skipped and
    logged, and the response says nothing about it: a note that a row was skipped is a count of
    what the reader was not shown, which is `brain.govern_routes.
    A_ROW_THE_TYPE_REFUSES_IS_A_ROW_AND_NOT_THE_END_OF_THE_SCREEN`.
    """
    try:
        kind = MemoryKind(row.kind)
        provenance_of(kind)
        formation = Formation(
            principal_id=row.principal_id,
            capabilities=tuple(Capability(value=one) for one in row.capability_tags),
            scope=Scope.model_validate(row.scope),
            ent_hash=row.ent_hash,
            formed_at=row.formed_at,
            kind=kind,
        )
    except (ValueError, MemoryViewError) as exc:
        log.warning("memory row does not construct", memory=row.id, error=type(exc).__name__)
        return None
    confidence = row.formed_confidence if isinstance(row, AdaptiveMemoryRow) else STATED_CONFIDENCE
    return (
        StoredMemory(memory_id=row.id, formation=formation, formed_confidence=confidence),
        row.statement,
    )


# ---------------------------------------------------------------- what is recorded


@dataclass(frozen=True)
class RecordedLearning:
    """The per-agent tier rows `learning_review` gathers, and the agents a reader may see.

    Four fields shaped exactly as that function's parameters, so the day a store exists the
    change is `recorded_learnings` and nothing that calls it.
    """

    visible: tuple[str, ...]
    tier_one: Mapping[str, Sequence[TierOneRow]]
    tier_two: Mapping[str, Sequence[TierTwoRow]]
    tier_three: Mapping[str, Sequence[TierThreeRouting]]


def recorded_learnings() -> RecordedLearning:
    """What this install records about learning, which is nothing.

    A function rather than empty literals at the call site, for `brain.skill_routes.submitted`'s
    reason: the absence has a place to be argued and a name to search for. **No agent roster is
    loaded**, because nothing recorded is keyed by an agent; the day a store exists, `visible` is
    `brain.agents.model.visible_agent_ids` over the roster, as `brain.skill_routes` assembles it,
    and the three mappings are `brain.console.reach_view.tier_one_rows`, `tier_two_rows` and
    `tier_three_routing` per agent. See
    `NOTHING_STORES_A_LEARNING_SO_THE_REVIEW_HAS_NOTHING_TO_NARROW`.
    """
    return RecordedLearning(
        visible=(),
        tier_one=MappingProxyType({}),
        tier_two=MappingProxyType({}),
        tier_three=MappingProxyType({}),
    )


def recorded_corrections() -> tuple[tuple[Supersession, ...], tuple[Demotion, ...]]:
    """Every supersession and demotion this install records, which is none.

    No migration creates a table for either. `brain.memory.correction` defines both and
    `brain.memory.digest.undo` and `brain.memory.review.edit` build them, and every one of those
    returns its correction for somebody else to write.
    """
    return (), ()


def tier_rules() -> tuple[TierRuleView, ...]:
    """Every tier, lowest first, with the changes `BLAST_RADIUS` puts at it, in its own order.

    Read off the map rather than written out, so a change moved between tiers moves on this
    screen in the same commit. A tier with no change is still listed: tier zero has one today,
    and a tier with none is still a rung of the vocabulary somebody reads the page to learn.
    """
    return tuple(
        TierRuleView(
            tier=int(tier),
            changes=tuple(change.value for change, needs in BLAST_RADIUS.items() if needs is tier),
        )
        for tier in Tier
    )


# ---------------------------------------------------------------- the projections


def memory_text_view(text: MemoryText) -> MemoryTextView:
    """One admitted memory, copied field by field."""
    return MemoryTextView(
        memory_id=text.memory_id,
        statement=text.statement,
        confidence=text.seen.confidence,
        formed_at=text.seen.formation.formed_at,
    )


def revision_view(one: Revision) -> RevisionView:
    """One revision, copied field by field, with the two vocabularies sent as their words."""
    return RevisionView(
        memory_id=one.memory_id,
        replaced_id=one.replaced_id,
        at=one.at,
        diff=one.diff,
        trigger=None if one.trigger is None else one.trigger.value,
        correction=None if one.correction is None else one.correction.value,
    )


# ------------------------------------------------------------------- the wiring


def _require_console_reads(request: Request) -> ConsoleReads:
    """Where a page is read from: `app.state.console_reads`, or the primary, or a fault.

    `brain.govern_routes`' construction. A `Failed` when there is no pool at all, on
    `brain.routing_routes`' argument: an instance with no database is broken rather than empty,
    and only a caller who already holds the screen's grant reaches this line.
    """
    found = getattr(request.app.state, "console_reads", None)
    if isinstance(found, ConsoleReads):
        return found
    factory: async_sessionmaker[AsyncSession] | None = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return ConsoleReads(factory)


def _not_answerable(what: str) -> Absent:
    """The refusal each screen here makes. Names the screen and never the row or the caller.

    The screen names are the console's own menu, identical in every install, so naming one
    discloses nothing about this company. `brain.govern_routes._not_answerable`'s shape.
    """
    return Absent(f"the {what} screen is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/library", response_model=LibraryPage, responses=COMMON_RESPONSES)
async def library(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_ITEMS_CONSIDERED)] = DEFAULT_ITEMS_CONSIDERED,
) -> LibraryPage:
    """Every retrievable item this reader may know exists, with how widely each reaches.

    The screen's question first and the database second. Then one load, `library_rows` for the
    rows and `departments_represented` for the grouping at `spans_departments`' basis, both over
    the same placed items, so the grouping can never name a department none of the rows sits in.

    `truncated` is the load having come back full, computed against what was loaded rather than
    against what `library_rows` returned, because the second would be a count of what the
    decision withheld spelled as a boolean. No parameter narrows the load; see
    `A_FILTER_ON_THE_SERVER_TURNS_A_TRUNCATION_FLAG_INTO_A_COUNT`.
    """
    if not permitted(screen(LIBRARY_SCREEN).read, asked.reach, asked.now):
        log.info("library screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(LIBRARY_SCREEN)

    reads = _require_console_reads(request)

    async def load(session: AsyncSession) -> list[KnowledgeItemRow]:
        return list((await session.execute(retrievable_items(limit))).scalars().all())

    served = await reads.read(load, now=asked.now)
    rows = served.value
    items = [placed_item(row) for row in rows]
    basis = spans_departments(asked.reach, asked.now)

    return LibraryPage(
        items=[
            LibraryRowView(item_id=one.item_id, level=one.level)
            for one in library_rows(items, asked.reach, asked.now)
        ],
        next_cursor=None,
        truncated=len(rows) >= limit,
        departments=departments_represented(items, asked.reach, basis=basis, now=asked.now),
        staleness=served.banner,
    )


@router.get("/govern/learning", response_model=LearningReviewView, responses=COMMON_RESPONSES)
async def learning(asked: Asked) -> LearningReviewView:
    """The three tiers across the estate, kept apart, and the vocabulary that sorts them.

    No database, because nothing stores a learning; see `recorded_learnings`. The basis is
    `spans_departments`' answer for this reader and `learning_review` uses it to decide whether
    tier three is shown, so the one per-reader decision on this screen is made today and is the
    same decision the day rows exist.
    """
    if not permitted(screen(LEARNING_SCREEN).read, asked.reach, asked.now):
        log.info("learning screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(LEARNING_SCREEN)

    recorded = recorded_learnings()
    review = learning_review(
        basis=spans_departments(asked.reach, asked.now),
        visible=recorded.visible,
        tier_one=recorded.tier_one,
        tier_two=recorded.tier_two,
        tier_three=recorded.tier_three,
    )
    return LearningReviewView(
        basis=review.basis,
        as_of=asked.now,
        tier_one=tuple(
            TierOneView(
                memory_id=one.memory_id,
                change=one.change.value,
                control_writes=one.control_writes.value,
                learned_at=one.learned_at,
            )
            for one in review.tier_one
        ),
        tier_two=tuple(
            TierTwoView(
                memory_id=one.memory_id,
                change=one.change.value,
                evidence=tuple(signal.value for signal in one.evidence),
                promote_ready=one.promote_ready,
                learned_at=one.learned_at,
            )
            for one in review.tier_two
        ),
        tier_three=None
        if review.tier_three is None
        else tuple(
            TierThreeView(memory_id=one.memory_id, department=one.department, back_to=one.back_to)
            for one in review.tier_three
        ),
        tiers=tier_rules(),
    )


@router.get("/govern/memory", response_model=SubjectMemoryView, responses=COMMON_RESPONSES)
async def memory(
    request: Request,
    asked: Asked,
    subject: Annotated[str, Query(min_length=1, max_length=PRINCIPAL_ID_CHARS, pattern=r"^\S+$")],
) -> SubjectMemoryView:
    """What this reader may read of what is remembered about one person, and its history.

    The screen's question first and the database second. Two loads, both keyed by the subject
    and bounded newest first, then `subject_memory`, which asks `may_recall` about every row
    for this reader and decides every diff from two admissions.

    A person nobody remembers anything about and a person whose every memory this reader may
    not recall produce the same response, byte for byte, because nothing on it varies with the
    rows the load found. See
    `A_TRUNCATION_FLAG_ON_A_LOOKUP_BY_PERSON_COUNTS_WHAT_IS_REMEMBERED_ABOUT_THEM`.

    The pattern refuses a subject made of white space before `subject_memory` is reached, so
    that function's refusal of a blank subject is a 422 naming the parameter rather than a 500.
    """
    if not permitted(screen(MEMORY_SCREEN).read, asked.reach, asked.now):
        log.info("memory screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(MEMORY_SCREEN)

    reads = _require_console_reads(request)

    async def load(
        session: AsyncSession,
    ) -> tuple[list[PersistentMemoryRow], list[AdaptiveMemoryRow]]:
        stated = (await session.execute(stated_about(subject, MAX_MEMORIES_CONSIDERED))).scalars()
        inferred = (
            await session.execute(inferred_about(subject, MAX_MEMORIES_CONSIDERED))
        ).scalars()
        return list(stated.all()), list(inferred.all())

    served = await reads.read(load, now=asked.now)
    stated, inferred = served.value
    rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [*stated, *inferred]
    entries = [found for found in (stored_memory(row) for row in rows) if found is not None]
    supersessions, demotions = recorded_corrections()
    remembered = subject_memory(
        subject_id=subject,
        entries=entries,
        reader=asked.reach,
        now=asked.now,
        supersessions=supersessions,
        demotions=demotions,
    )
    return SubjectMemoryView(
        subject_id=remembered.subject_id,
        curated=tuple(memory_text_view(one) for one in remembered.memory.curated),
        extracted=tuple(memory_text_view(one) for one in remembered.memory.extracted),
        history=tuple(revision_view(one) for one in remembered.history),
        staleness=served.banner,
    )
