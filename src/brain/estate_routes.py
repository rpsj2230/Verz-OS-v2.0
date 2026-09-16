"""The knowledge library, the learning review and the memory viewer over HTTP, what each one's
store can tell it, and the one write among them.

`brain.console.govern_estate` decides three Govern screens the design draws: SCREEN 7 of
`docs/screens.html` is Knowledge, SCREEN 8 is Learning, and the memory card inside SCREEN 13
is the change history a person's memory carries. `library_rows` and `departments_represented`
decide what a reader may know exists and how the rows may be grouped, `learning_estate` keeps
the three tiers apart over what is stored and withholds tier three on the narrower basis, and
`subject_memory` decides which memories about one person a reader may read and which revisions
they may diff. This module is the read they sit behind and the undo beside the review, and
nothing in it decides who may see anything: every route asks `brain.console.reads.permitted`
whether its screen opens, loads, hands the rows to the function that owns the decision, and
projects what comes back. See
`brain.govern_routes.THE_SCREEN_DECIDES_NOTHING_AND_THE_CONSOLE_MODULE_DECIDES_EVERYTHING`.

**Since 2026-09-17 the learning review and the memory viewer read stored learnings and
corrections.** `mem.learning` holds what a learning proposed, which agent ran and what it
replaced, and `mem.correction` holds every supersession and demotion, both from `0061`. The
review reads the learnings of the agents a caller may see and the corrections naming them; the
viewer reads a person's memories, what each replaced and the corrections naming them. Nothing
yet forms a memory from a conversation on a running install, so on most installs both still
answer empty, and neither says so with a flag any more: an empty review over a store that exists
is an install where nothing has been learnt, which is now a fact the tables establish.

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

**Undoing a tier-one learning is a confirmed, audited write.** `POST /govern/learning/undo`
names one memory. The caller must open the Learning screen and hold `admin:learning` somewhere,
before anything is loaded; then the learning must be one the review would show them, at the
reach their run of its agent has, and `brain.console.govern_estate.may_undo` must admit the place
its memory was formed. Every refusal is the one 404. The store decides and writes under a lock,
`0061`'s trigger appends the ledger entry, and the next recall reads the correction: the memory
viewer, a person's own memory tab and `brain.memory.recall.recall` all leave the undone memory
out. The console confirms first, in the sentence `undo_says` serves. See
`AN_UNDO_REACHES_A_ROW_A_LEDGER_ENTRY_AND_WHAT_IS_RECALLED`.

**The memory viewer is asked about one person and says nothing about how much there is.** A
subject is required, which is `brain.console.govern_estate.
A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE`. What this adds is the bound: the
load is keyed by a name the caller typed, so a flag saying it came back full would say a
person has at least that many memories, readable or not. See
`A_TRUNCATION_FLAG_ON_A_LOOKUP_BY_PERSON_COUNTS_WHAT_IS_REMEMBERED_ABOUT_THEM`. The review's
bound is stated the same way and for the same reason: a flag over the learnings of the agents a
caller may see counts learnings they may not recall.

**Memory is a Govern screen and not a tab inside an agent, although SCREEN 13 draws it in
one.** The design places a memory card on one agent's page and has no company-level memory
screen. `brain.console.screens` registers `memory` under Govern, and the decision it serves,
`subject_memory`, is keyed by the person a memory is about.

**Whether a screen opens is `permitted` and it is asked before anything else.** The Library
screen is the existence plane, Learning and Memory are the content plane, and a hand-written
`reach.holds` would answer an existence-only reader a content screen. The question comes before
a session is reached for, so a caller with no grant cannot tell an instance with a database from
one without.

**Nothing here computes a reach.** There is no `.intersect(` in this module.
`brain.console.workspace.intersections_in` is run over this source by its test.

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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import every_agent, one_agent, record_of, viewer_of
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, Asking
from brain.console.govern import NOWHERE, Placed
from brain.console.govern_estate import (
    UNDO_AUTHORITY,
    LibraryItem,
    departments_represented,
    learning_estate,
    learnings_in_view,
    library_rows,
    may_undo,
    spans_departments,
    subject_memory,
)
from brain.console.reach_view import (
    MemoryText,
    MemoryViewError,
    Revision,
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
from brain.memory.correction import Correction, Supersession
from brain.memory.digest import Learning, Undo
from brain.memory.formation import Formation, MemoryKind
from brain.memory.signals import Signal
from brain.memory.tiers import BLAST_RADIUS, Change, Proposal, Tier, TierError
from brain.ops.memory_store import (
    Corrections,
    MemoryRecords,
    StoredMemoryRecords,
    corrections_naming,
    corrections_of,
    inferred_named,
    learnings_named,
    learnings_of_agents,
    stated_named,
)
from brain.ops.replica_store import ConsoleReads
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.learning import MEMORY_ID_CHARS, LearningRow
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

#: Why an undo is followed to the row, the ledger and recall rather than to the row alone.
AN_UNDO_REACHES_A_ROW_A_LEDGER_ENTRY_AND_WHAT_IS_RECALLED: Final = (
    "docs/admin-console.md says a control that renders but reaches nothing is worse than no "
    "control. An undo reaches three places: brain.ops.memory_store writes the correction under a "
    "lock, 0061's trigger appends a memory entry to the ledger naming who undid it, and "
    "brain.memory.recall reads the correction, so the memory viewer and a person's own memory tab "
    "stop listing the undone memory and list the one it replaced, if any. A second undo of the "
    "same learning writes nothing and says so."
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

#: Where the undo is posted, under the learning screen's own path.
UNDO_PATH: Final = "/govern/learning/undo"


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

#: The most agents one review is assembled over, in id order, before their audience is asked.
MAX_AGENTS_CONSIDERED: Final = 500

#: The most learnings one review is assembled from, most recently recorded first. Sent on every
#: response as a constant, for the viewer's reason.
MAX_LEARNINGS_CONSIDERED: Final = 500

#: What a stated memory was worth when it was formed. `mem.persistent` has no confidence column
#: and `brain.memory.digest.Learning.formed_confidence` defaults to certain for the same kind
#: of memory, so a row read back is handed to recall on the terms it was written on.
STATED_CONFIDENCE: Final = 1.0

#: What the confirmation says an undo will do, by what it would write. Served, so the console
#: shows the API's sentence rather than a copy of it.
UNDO_SAYS: Final[Mapping[Correction, str]] = MappingProxyType(
    {
        Correction.SUPERSEDED: (
            "The memory this learning replaced is put back and this one is marked, so the system "
            "recalls the earlier memory again and stops recalling this one. Nothing is deleted: "
            "both stay on the record, the Memory screen shows the change, and the audit trail "
            "records that you undid it."
        ),
        Correction.DEMOTED: (
            "This learning's memory is marked, so the system stops recalling it. Nothing is "
            "deleted: it stays on the record, the Memory screen shows the change, and the audit "
            "trail records that you undid it."
        ),
    }
)


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
    """One automatic change, as `brain.console.reach_view.TierOneRow` carries it, and whether
    this reader is offered its undo."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    change: str
    #: What undoing it would write, which is a mark and never a removal.
    control_writes: str
    learned_at: datetime
    #: False once a correction marked it. `TierOneRow.in_effect`.
    in_effect: bool
    #: Whether this reader may undo it now: in effect, and `may_undo` admits them. A reader who
    #: may see the row and not undo it is shown the row without the control.
    undo_offered: bool


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
    it may be shown to anybody who opens the screen.
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
    #: How many learnings the load reads at most. A constant, never a measurement.
    considered: int = MAX_LEARNINGS_CONSIDERED
    #: What the confirmation says an undo will do, keyed by `control_writes`. See `UNDO_SAYS`.
    undo_says: dict[str, str]
    staleness: StalenessBanner | None = None


class UndoAsked(BaseModel):
    """Which tier-one learning to undo. Its memory's id and nothing else.

    No reason and no correction kind: what an undo writes is `brain.memory.digest.undo`'s to
    decide from whether the learning replaced a memory, and a caller choosing would be a caller
    able to demote a memory whose undo should have restored the one before it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str = Field(min_length=1, max_length=MEMORY_ID_CHARS, pattern=r"^[A-Za-z0-9_.@-]+$")


class LearningUndoneView(BaseModel):
    """What one undo did: the correction it wrote and when, or nothing, and the domain's reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    #: False when the memory was already marked, which is the ordinary outcome of a second click.
    took_effect: bool
    #: What was written, as `Correction`'s word, or null when nothing was.
    correction: str | None
    at: datetime | None
    told: str


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
    #: There is no route that edits a memory from this screen. `brain.ops.memory_store` writes an
    #: edit, and the control belongs on a person's own memory tab, which has no route yet.
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


def bounded_agents(limit: int) -> Select[tuple[AgentRow]]:
    """Every stored agent, bounded. Filtered by audience afterwards, by the one predicate."""
    return every_agent().limit(limit)


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

    Not a `Learning`, because a memory row records no proposal; `recorded_learning` builds one
    when `mem.learning` holds it. `replaced_id` is the learning record's, and `None` for a
    memory nothing records as having replaced another.
    """

    memory_id: str
    formation: Formation
    formed_confidence: float
    replaced_id: str | None = None


def stored_memory(
    row: PersistentMemoryRow | AdaptiveMemoryRow,
    learning: LearningRow | None = None,
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

    `learning` is this memory's record in `mem.learning`, when there is one, and it is where
    what the memory replaced is read from.
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
    replaced = learning.replaced_id if learning is not None else None
    return (
        StoredMemory(
            memory_id=row.id,
            formation=formation,
            formed_confidence=confidence,
            replaced_id=replaced,
        ),
        row.statement,
    )


def recorded_learning(row: LearningRow, memory: StoredMemory) -> Learning | None:
    """One stored learning as the domain's `Learning`, or `None` when the domain refuses it.

    `Proposal` refuses a tier the change does not need and `Learning` refuses a confidence of
    zero or a memory that replaced itself. `0061`'s constraints refuse the first and third, and
    an inferred memory can be stored at zero, so each is possible on disk; the row is skipped and
    logged, for `stored_memory`'s reason.
    """
    try:
        return Learning(
            memory_id=memory.memory_id,
            proposal=Proposal(change=Change(row.change), tier=Tier(row.tier), subject=row.subject),
            formation=memory.formation,
            evidence=frozenset(Signal(one) for one in row.evidence),
            formed_confidence=memory.formed_confidence,
            replaced_id=row.replaced_id,
            agent_id=row.agent_id,
        )
    except (ValueError, TierError) as exc:
        log.warning(
            "learning row does not construct", memory=row.memory_id, error=type(exc).__name__
        )
        return None


# ---------------------------------------------------------------- the loads


@dataclass(frozen=True)
class RememberedAbout:
    """One person's memories, each with its statement and what it replaced, and the corrections
    naming any of them."""

    entries: tuple[tuple[StoredMemory, str], ...]
    corrections: Corrections


async def remembered_about(session: AsyncSession, subject_id: str, limit: int) -> RememberedAbout:
    """What is stored about one person, for the memory viewer and a person's own memory tab.

    Four statements in the session the caller holds: both memory tables keyed by the subject and
    bounded newest first, the learning records of exactly the memories found, and the corrections
    naming them. The last two are asked only when a memory was found, so a person nobody remembers
    anything about costs two statements.
    """
    stated = (await session.execute(stated_about(subject_id, limit))).scalars().all()
    inferred = (await session.execute(inferred_about(subject_id, limit))).scalars().all()
    rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [*stated, *inferred]
    ids = [row.id for row in rows]
    if not ids:
        return RememberedAbout(entries=(), corrections=Corrections((), ()))
    records = {
        one.memory_id: one for one in (await session.execute(learnings_named(ids))).scalars().all()
    }
    marks = (await session.execute(corrections_naming(ids))).scalars().all()
    entries = tuple(
        found for found in (stored_memory(row, records.get(row.id)) for row in rows) if found
    )
    return RememberedAbout(entries=entries, corrections=corrections_of(marks))


@dataclass(frozen=True)
class StoredLearnings:
    """The agents a review was assembled over, their learnings, and the corrections naming them."""

    records: tuple[AgentRecord, ...]
    learnings: tuple[Learning, ...]
    corrections: Corrections


async def learnings_stored(
    session: AsyncSession, visible: Sequence[AgentRecord], limit: int
) -> StoredLearnings:
    """The learnings formed while these agents ran, with their memories and corrections.

    `visible` has already been narrowed to the caller's audience, so nothing is loaded about an
    agent the caller may not see. The memories are read by id from both tables, because a learning
    record does not say which table its memory is in, and a learning whose memory is in neither is
    skipped: there is no formation to decide recall from.
    """
    if not visible:
        return StoredLearnings(records=(), learnings=(), corrections=Corrections((), ()))
    rows = (
        (await session.execute(learnings_of_agents([one.agent_id for one in visible], limit)))
        .scalars()
        .all()
    )
    ids = [one.memory_id for one in rows]
    if not ids:
        return StoredLearnings(
            records=tuple(visible), learnings=(), corrections=Corrections((), ())
        )
    stated = (await session.execute(stated_named(ids))).scalars().all()
    inferred = (await session.execute(inferred_named(ids))).scalars().all()
    marks = (await session.execute(corrections_naming(ids))).scalars().all()
    memory_rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [*stated, *inferred]
    memories = {
        found[0].memory_id: found[0]
        for found in (stored_memory(row) for row in memory_rows)
        if found is not None
    }
    learnings = tuple(
        learning
        for learning in (
            recorded_learning(row, memories[row.memory_id])
            for row in rows
            if row.memory_id in memories
        )
        if learning is not None
    )
    return StoredLearnings(
        records=tuple(visible), learnings=learnings, corrections=corrections_of(marks)
    )


def visible_records(records: Sequence[AgentRecord], asked: Asking) -> tuple[AgentRecord, ...]:
    """The agents this caller's audience covers, in id order.

    `brain.agents.model.visible_agent_ids` is the answer and `brain.agent_routes.viewer_of`
    builds the viewer, so who may see an agent is decided once, by the module that owns it.
    """
    visible = visible_agent_ids(records, viewer_of(asked))
    return tuple(sorted((one for one in records if one.agent_id in visible), key=_agent_id))


def _agent_id(record: AgentRecord) -> str:
    return record.agent_id


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


def undone_view(decided: Undo) -> LearningUndoneView:
    """What one undo did, from the correction the store wrote or its absence."""
    correction = decided.correction
    if correction is None:
        return LearningUndoneView(
            memory_id=decided.memory_id,
            took_effect=False,
            correction=None,
            at=None,
            told=decided.reason,
        )
    return LearningUndoneView(
        memory_id=decided.memory_id,
        took_effect=True,
        correction=(
            Correction.SUPERSEDED if isinstance(correction, Supersession) else Correction.DEMOTED
        ).value,
        at=correction.at,
        told=decided.reason,
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


def memory_records_of(request: Request) -> MemoryRecords | None:
    """What `app.state.memory_records` holds, or the database's store, or None without one."""
    found = getattr(request.app.state, "memory_records", None)
    if isinstance(found, MemoryRecords):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredMemoryRecords(sessions)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.connector_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


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
async def learning(request: Request, asked: Asked) -> LearningReviewView:
    """The three tiers across the agents this reader may see, kept apart, and what undo would do.

    The screen's question first and the database second. The agents are loaded bounded and
    narrowed to the caller's audience before anything about them is read; their learnings, the
    memories those were formed as and the corrections naming them are loaded next; and
    `learning_estate` decides every row, including which learnings the caller may be told of at
    the reach their run of each agent has. Whether a row's undo is offered is `may_undo`, asked per
    row of the learning the row is about.
    """
    if not permitted(screen(LEARNING_SCREEN).read, asked.reach, asked.now):
        log.info("learning screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(LEARNING_SCREEN)

    reads = _require_console_reads(request)

    async def load(session: AsyncSession) -> StoredLearnings:
        agent_rows = (await session.execute(bounded_agents(MAX_AGENTS_CONSIDERED))).scalars().all()
        records = [one for one in (record_of(row) for row in agent_rows) if one is not None]
        return await learnings_stored(
            session, visible_records(records, asked), MAX_LEARNINGS_CONSIDERED
        )

    served = await reads.read(load, now=asked.now)
    stored = served.value
    review = learning_estate(
        basis=spans_departments(asked.reach, asked.now),
        records=stored.records,
        learnings=stored.learnings,
        caller=asked.reach,
        now=asked.now,
        supersessions=stored.corrections.supersessions,
        demotions=stored.corrections.demotions,
    )
    by_id = {one.memory_id: one for one in stored.learnings}
    return LearningReviewView(
        basis=review.basis,
        as_of=asked.now,
        tier_one=tuple(
            TierOneView(
                memory_id=one.memory_id,
                change=one.change.value,
                control_writes=one.control_writes.value,
                learned_at=one.learned_at,
                in_effect=one.in_effect,
                undo_offered=one.in_effect
                and may_undo(asked.reach, by_id[one.memory_id], asked.now),
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
        undo_says={correction.value: said for correction, said in UNDO_SAYS.items()},
        staleness=served.banner,
    )


@router.post(UNDO_PATH, response_model=LearningUndoneView, responses=COMMON_RESPONSES)
async def undo_learning(request: Request, body: UndoAsked, asked: Asked) -> LearningUndoneView:
    """Undo one tier-one learning, as the person asking, and say what was written.

    **Four questions, every refusal the one 404, and the order is the property.** Whether the caller
    may open the Learning screen and holds `UNDO_AUTHORITY` anywhere, before a session is reached
    for, so a caller who may not undo anything cannot tell an instance with a database from one
    without, or a memory that exists from one that does not. Then the learning, its memory and its
    agent are read from the primary, and the learning must be one `learnings_in_view` shows this
    caller: a visible agent's, recalled at the caller's run of it. Then `may_undo`, which is tier
    one and the authority in a scope admitting where the memory was formed. Only then the store,
    which decides and writes under a lock. See
    `AN_UNDO_REACHES_A_ROW_A_LEDGER_ENTRY_AND_WHAT_IS_RECALLED`.

    A second undo is answered 200 with `took_effect` false and the domain's sentence, because the
    person did nothing wrong and there is nothing for them to fix.
    """
    if not permitted(screen(LEARNING_SCREEN).read, asked.reach, asked.now) or not asked.reach.holds(
        UNDO_AUTHORITY, asked.now
    ):
        log.info("undo not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(LEARNING_SCREEN)
    factory = sessions_of(request)
    records = memory_records_of(request)
    if factory is None or records is None:
        raise Failed("no database on this process")

    async with factory() as session:
        row = (await session.execute(learnings_named((body.memory_id,)))).scalars().first()
        agent_row = (
            None
            if row is None or row.agent_id is None
            else (await session.execute(one_agent(row.agent_id))).scalars().first()
        )
        stated = (await session.execute(stated_named((body.memory_id,)))).scalars().all()
        inferred = (await session.execute(inferred_named((body.memory_id,)))).scalars().all()

    record = None if agent_row is None else record_of(agent_row)
    memory_rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [*stated, *inferred]
    memories = [found for found in (stored_memory(one) for one in memory_rows) if found]
    found = None if row is None or not memories else recorded_learning(row, memories[0][0])
    visible = () if record is None else visible_records((record,), asked)
    shown = learnings_in_view(
        records=visible,
        learnings=() if found is None else (found,),
        caller=asked.reach,
        now=asked.now,
    )
    if (
        found is None
        or found.memory_id not in {one.memory_id for theirs in shown.values() for one in theirs}
        or not may_undo(asked.reach, found, asked.now)
    ):
        log.info("undo not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(LEARNING_SCREEN)

    decided = await records.undo(
        found,
        actor=asked.reach.principal_id,
        trace_id=_trace_id(),
        ent_hash=asked.reach.ent_hash(),
    )
    log.info(
        "learning undo answered",
        principal=asked.reach.principal_id,
        took_effect=decided.took_effect,
    )
    return undone_view(decided)


@router.get("/govern/memory", response_model=SubjectMemoryView, responses=COMMON_RESPONSES)
async def memory(
    request: Request,
    asked: Asked,
    subject: Annotated[str, Query(min_length=1, max_length=PRINCIPAL_ID_CHARS, pattern=r"^\S+$")],
) -> SubjectMemoryView:
    """What this reader may read of what is remembered about one person, and its history.

    The screen's question first and the database second. One load, `remembered_about`, keyed by
    the subject and bounded newest first, with what each memory replaced and the corrections
    naming them; then `subject_memory`, which asks `may_recall` about every row for this reader,
    leaves out what a correction marked and decides every diff from two admissions.

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

    async def load(session: AsyncSession) -> RememberedAbout:
        return await remembered_about(session, subject, MAX_MEMORIES_CONSIDERED)

    served = await reads.read(load, now=asked.now)
    stored = served.value
    remembered = subject_memory(
        subject_id=subject,
        entries=stored.entries,
        reader=asked.reach,
        now=asked.now,
        supersessions=stored.corrections.supersessions,
        demotions=stored.corrections.demotions,
    )
    return SubjectMemoryView(
        subject_id=remembered.subject_id,
        curated=tuple(memory_text_view(one) for one in remembered.memory.curated),
        extracted=tuple(memory_text_view(one) for one in remembered.memory.extracted),
        history=tuple(revision_view(one) for one in remembered.history),
        staleness=served.banner,
    )
