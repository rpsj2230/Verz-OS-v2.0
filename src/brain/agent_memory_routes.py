"""One agent's memory and learning, as its page's Memory section reads them, and the owner's edit.

`brain.console.reach_view` decided how an agent's memory reads, a fortnight before any route asked:
readable text or nothing (`readable`), curated apart from extracted (`split_memory`), a history
with a diff per step and the trigger that caused it (`revisions`), and what the agent learnt kept
apart from what it keeps about people. `brain.console.govern_estate.learning_estate` decided the
three learning tiers, and `brain.ops.memory_store.StoredMemoryRecords` writes an edit and a
delete. The only place any of it reached was the company's Memory and Learning screens, estate
wide and never for one agent. This module is the agent's own view, and it decides nothing those
modules had not.

**What the agent learnt is read at `E_run(reader, agent)`; what it keeps about the reader is read
at the reader's own reach.** The first is `reach_view.run_reach`, the console's one route into the
intersection, because the Memory section showing what the agent knows rather than what this
reader may be told would be the one place the lens stopped applying. The second is the reader's
own reach, at `brain.memory.turn.recall_place`, because narrowing a person's own memory by the
agent's ceiling would hide it from its own subject for a reason that has nothing to do with them.
A memory about the reader appears in both lists when both admit it: assigning it to one makes the
other incomplete, and the reader cannot tell which. See `reach_view.SeparateMemoryView`.

**The agent's steward edits and deletes its memory, and a person deletes or corrects memory about
themselves** (`docs/requirements/register.json` ARC-B-070, FEAT-7.4). Both only on a memory the
list already shows them; anything else is the answer a memory that does not exist gets. A delete
is `StoredMemoryRecords.undo`, which is `brain.memory.review.delete`'s mark: the memory stays on the
record and stops being recalled, and `0061`'s trigger ledgers it. An edit is `StoredMemoryRecords.
edit`: a new memory naming the one it replaces and a supersession, and nothing rewritten in place.
See `THE_STEWARD_AND_THE_PERSON_IT_IS_ABOUT_MAY_CHANGE_A_MEMORY`.

**The tiers are the Learning screen's, for this agent alone.** `learning_estate` over this one
record: tier one newest first with the undo offered where `may_undo` admits the reader (the undo
itself is the Learning screen's own route), tier two with its evidence and whether the rule may be
promoted, tier three routed to the department queue with the key back to this agent and withheld
on the narrower basis. Which tiers are active is `reach_view.active_tiers` over every tier, because
nothing on an install switches a tier off for one agent yet; tier three is never active, since a
gated change waits for a person.

Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.4, M39.4.1.5
Task ids: M39.4.2.1, M39.4.2.2, M39.4.2.3, M39.4.2.4
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from brain.agent_routes import (
    _no_agent_here,
    _require_session_factory,
    _visible_record,
)
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.console.govern_estate import learning_estate, may_undo, spans_departments
from brain.console.reach_view import (
    LearningState,
    MemoryText,
    Revision,
    TierTwoRow,
    active_tiers,
    revisions,
    run_reach,
    split_memory,
)
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.core.entitlement import EntitlementSet
from brain.estate_routes import (
    MAX_LEARNINGS_CONSIDERED,
    StoredLearnings,
    learnings_stored,
    memory_records_of,
    stored_memory,
    undone_view,
)
from brain.memory.digest import Learning
from brain.memory.formation import Formation
from brain.memory.promotion import LearnedRule, PromotionState
from brain.memory.promotion_store import StoredLearnedRules
from brain.memory.signals import Signal
from brain.memory.tiers import Occurrence, Tier, independent
from brain.memory.turn import MEMORY_ID_DIGEST_CHARS, MEMORY_ID_PREFIX, recall_place
from brain.ops.memory_store import inferred_named, stated_named
from brain.promotion_routes import may_promote_where
from brain.tables.learning import MEMORY_ID_CHARS
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Who may change one agent's memory from its page, and why those two.
THE_STEWARD_AND_THE_PERSON_IT_IS_ABOUT_MAY_CHANGE_A_MEMORY: Final = (
    "An agent's memory is changed by the person who answers for the agent, and a memory about a "
    "person may be deleted or corrected by that person. Each may change only a memory the "
    "Memory section already shows them, and anybody else is told which of the two may."
)

#: The sentence a reader shown a memory they may not change is told.
CHANGING_A_MEMORY_NEEDS_THE_STEWARD_OR_ITS_SUBJECT: Final = (
    "Changing this memory needs the agent's steward, or the person the memory is about."
)

# ------------------------------------------------------------------------ the figures
MEMORY_PATH: Final = "/agents/{agent_id}/memory"
DELETE_PATH: Final = "/agents/{agent_id}/memory/{memory_id}/deletion"
EDIT_PATH: Final = "/agents/{agent_id}/memory/{memory_id}/edit"

#: The longest statement an edit may write, which is what a turn may form.
MAX_STATEMENT_CHARS: Final = 500

MemoryId = Annotated[
    str, Path(min_length=1, max_length=MEMORY_ID_CHARS, pattern=r"^[A-Za-z0-9_.@-]+$")
]


# ------------------------------------------------------------------------------ the views
class MemoryItemView(BaseModel):
    """One memory in its own words, with whether this reader may change it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    statement: str
    confidence: float
    formed_at: datetime
    #: Stated by a person, or inferred from how they asked (`Provenance`'s two words).
    provenance: str
    #: Whether the memory is about the reader.
    about_you: bool
    #: Whether this reader may edit and delete it here.
    changeable: bool


class MemoryRevisionView(BaseModel):
    """One step in the history, as `reach_view.Revision` built it (M39.4.1.3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    replaced_id: str | None
    at: datetime
    diff: list[str]
    trigger: str | None
    correction: str | None


class TierOneItemView(BaseModel):
    """One automatic change, and whether this reader is offered its undo (M39.4.2.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    change: str
    control_writes: str
    learned_at: datetime
    in_effect: bool
    undo_offered: bool


class TierTwoItemView(BaseModel):
    """One proposed rule, its evidence kinds, and whether it may be promoted (M39.4.2.3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    change: str
    evidence: list[str]
    promote_ready: bool
    learned_at: datetime
    #: Where its learned rule stands, `held`, `awaiting_second` or `promoted`, or null for a
    #: learning that holds no rule (M39.4.2.3).
    state: str | None = None
    #: How many separate conversations would have used it, shown only to whoever may promote it.
    agreeing: int | None = None
    #: Whether this reader may press Promote on it now. See `brain.promotion_routes`.
    promote_offered: bool = False


class TierThreeItemView(BaseModel):
    """Where one gated change waits for a person, and the key back to this agent (M39.4.2.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    department: str
    back_to: str


class AgentMemoryView(BaseModel):
    """What one agent remembers, as this reader may read it, and how it learns.

    `curated` and `extracted` are what the agent learnt at the reader's run reach; `about_you`
    is what it keeps about the reader, at their own reach. No field is a count of anything left
    out. `tier_three` is null on the narrower basis, and never an empty list standing in for it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    curated: list[MemoryItemView]
    extracted: list[MemoryItemView]
    about_you: list[MemoryItemView]
    history: list[MemoryRevisionView]
    #: The tiers this agent learns at now, lowest first (M39.4.2.1).
    active_tiers: list[int]
    tier_one: list[TierOneItemView]
    tier_two: list[TierTwoItemView]
    tier_three: list[TierThreeItemView] | None = None


class MemoryChangedView(BaseModel):
    """What one delete or edit wrote, or that nothing was, and the domain's reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    took_effect: bool
    #: The replacement's id, for an edit that took effect.
    replaced_by: str | None = None
    told: str


class EditAsked(BaseModel):
    """What the memory should say instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


# ------------------------------------------------------------------------- the decisions
def item_view(text: MemoryText, *, reader_id: str, steward: bool) -> MemoryItemView:
    """One admitted memory, with who may change it. See the reason above."""
    about_you = text.seen.formation.principal_id == reader_id
    return MemoryItemView(
        memory_id=text.memory_id,
        statement=text.statement,
        confidence=text.seen.confidence,
        formed_at=text.seen.formation.formed_at,
        provenance=text.provenance.value,
        about_you=about_you,
        changeable=steward or about_you,
    )


def tier_two_view(
    row: TierTwoRow,
    learned: LearnedRule | None,
    seen: Sequence[Occurrence],
    reader: EntitlementSet,
    now: datetime,
) -> TierTwoItemView:
    """One tier-two row, with its learned rule's standing and the press for whoever may make it."""
    offered = (
        learned is not None
        and learned.state is not PromotionState.PROMOTED
        and may_promote_where(reader, learned.department, now)
    )
    return TierTwoItemView(
        memory_id=row.memory_id,
        change=row.change.value,
        evidence=[signal.value for signal in row.evidence],
        promote_ready=row.promote_ready,
        learned_at=row.learned_at,
        state=None if learned is None else learned.state.value,
        agreeing=independent(seen, now=now) if offered else None,
        promote_offered=offered,
    )


def revision_view(one: Revision) -> MemoryRevisionView:
    return MemoryRevisionView(
        memory_id=one.memory_id,
        replaced_id=one.replaced_id,
        at=one.at,
        diff=list(one.diff),
        trigger=None if one.trigger is None else one.trigger.value,
        correction=None if one.correction is None else one.correction.value,
    )


def memory_view(
    record: AgentRecord,
    stored: StoredLearnings,
    entries: Sequence[tuple[Learning, str]],
    *,
    reader: EntitlementSet,
    department: str | None,
    now: datetime,
    learned: Mapping[str, LearnedRule] | None = None,
    occurrences: Mapping[str, Sequence[Occurrence]] | None = None,
) -> AgentMemoryView:
    """The agent's memory, its history and its tiers, for this reader. See the module docstring.

    `learned` and `occurrences` are each tier-two learning's held rule and the conversations
    counted for it (M39.4.2.3), so a row is ready on counted agreement and offers Promote to a
    reader who may press it where the rule would answer.

    `department` is the reader's primary department, which `recall_place` adds to the place
    their own memory is recalled at, so a reader whose grants are scoped to it recalls their own.
    """
    marks = stored.corrections.supersessions
    demoted = stored.corrections.demotions
    reader_id = reader.principal_id
    steward = record.audience.owner_id == reader_id
    run = run_reach(reader, record)
    typed = list(entries)
    learnt = split_memory(typed, run, now=now, supersessions=marks, demotions=demoted)
    mine = split_memory(
        [one for one in typed if one[0].formation.principal_id == reader_id],
        reader,
        now=now,
        where=recall_place(reader_id, department),
        supersessions=marks,
        demotions=demoted,
    )
    history = revisions(typed, run, now=now, supersessions=marks, demotions=demoted)
    review = learning_estate(
        basis=spans_departments(reader, now),
        records=(record,),
        learnings=stored.learnings,
        caller=reader,
        now=now,
        supersessions=marks,
        demotions=demoted,
        occurrences=occurrences,
    )
    by_id = {one.memory_id: one for one in stored.learnings}
    rules = learned or {}
    counted = occurrences or {}
    tiers = active_tiers(LearningState(agent_id=record.agent_id, declared=frozenset(Tier)))
    return AgentMemoryView(
        agent_id=record.agent_id,
        curated=[item_view(one, reader_id=reader_id, steward=steward) for one in learnt.curated],
        extracted=[
            item_view(one, reader_id=reader_id, steward=steward) for one in learnt.extracted
        ],
        about_you=[
            item_view(one, reader_id=reader_id, steward=steward)
            for one in (*mine.curated, *mine.extracted)
        ],
        history=[revision_view(one) for one in history],
        active_tiers=[int(one) for one in tiers],
        tier_one=[
            TierOneItemView(
                memory_id=one.memory_id,
                change=one.change.value,
                control_writes=one.control_writes.value,
                learned_at=one.learned_at,
                in_effect=one.in_effect,
                undo_offered=one.in_effect and may_undo(reader, by_id[one.memory_id], now),
            )
            for one in review.tier_one
        ],
        tier_two=[
            tier_two_view(
                one, rules.get(one.memory_id), counted.get(one.memory_id, ()), reader, now
            )
            for one in review.tier_two
        ],
        tier_three=None
        if review.tier_three is None
        else [
            TierThreeItemView(
                memory_id=one.memory_id, department=one.department, back_to=one.back_to
            )
            for one in review.tier_three
        ],
    )


async def agent_entries(
    session: AsyncSession, record: AgentRecord
) -> tuple[StoredLearnings, list[tuple[Learning, str]]]:
    """The agent's learnings, the corrections naming them, and each with its statement.

    `learnings_stored` is the Learning screen's load, asked for this one agent; the statements
    are read from both memory tables by the learnings' ids, as that load reads the formations.
    """
    stored = await learnings_stored(session, (record,), MAX_LEARNINGS_CONSIDERED)
    ids = [one.memory_id for one in stored.learnings]
    if not ids:
        return stored, []
    rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [
        *(await session.execute(stated_named(ids))).scalars().all(),
        *(await session.execute(inferred_named(ids))).scalars().all(),
    ]
    statements = {
        found[0].memory_id: found[1] for found in (stored_memory(row) for row in rows) if found
    }
    return stored, [
        (one, statements[one.memory_id]) for one in stored.learnings if one.memory_id in statements
    ]


def may_read_memory(asked: Asking) -> bool:
    """The Memory tab's own read, which is what the strip shows the section by."""
    return permitted(tab(Tab.MEMORY).read, asked.reach, asked.now)


def replacement_for(learning: Learning, statement: str, *, at: datetime) -> Learning:
    """The memory an edit writes: this one's formation and agent, formed now, naming this one.

    Its id is derived from what it replaces and what it says, never minted, in the shape a turn's
    memories take (`brain.memory.turn.memory_id`), so the same edit sent twice proposes one id.
    """
    source = f"{learning.memory_id}\n{statement.strip()}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    formation: Formation = replace(learning.formation, formed_at=at)
    return replace(
        learning,
        memory_id=f"{MEMORY_ID_PREFIX}{digest[:MEMORY_ID_DIGEST_CHARS]}",
        formation=formation,
        replaced_id=learning.memory_id,
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(MEMORY_PATH, response_model=AgentMemoryView, responses=COMMON_RESPONSES)
async def agent_memory(request: Request, agent_id: str, asked: Asked) -> AgentMemoryView:
    """One agent's memory and learning, or the answer a missing agent gets.

    A reader without the Memory tab's read is answered as an agent that does not exist, so the
    address is never a way to learn whether an agent remembers anything.
    """
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_memory(asked):
            log.info("agent memory not answerable", principal=asked.caller.principal.id)
            raise _no_agent_here()
        stored, entries = await agent_entries(session, record)
    learned, occurrences = await learned_rules_of(factory, stored.learnings)
    return memory_view(
        record,
        stored,
        entries,
        reader=asked.reach,
        department=asked.caller.principal.primary_department,
        now=asked.now,
        learned=learned,
        occurrences=occurrences,
    )


async def learned_rules_of(
    factory: Any, learnings: Sequence[Learning]
) -> tuple[Mapping[str, LearnedRule], Mapping[str, Sequence[Occurrence]]]:
    """Each tier-two learning's held rule and its counted conversations (M39.4.2.3)."""
    store = StoredLearnedRules(factory)
    twos = [one.memory_id for one in learnings if one.proposal.tier is Tier.PROMOTED]
    found = {}
    for memory_id in twos:
        held = await store.learned(memory_id)
        if held is not None:
            found[memory_id] = held
    return found, await store.occurrences(tuple(found))


async def _shown(
    request: Request, agent_id: str, memory_id: str, asked: Asking
) -> tuple[AgentRecord, Learning, AgentMemoryView]:
    """The memory, if this reader's Memory section shows it, or the missing agent's answer."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_memory(asked):
            raise _no_agent_here()
        stored, entries = await agent_entries(session, record)
    view = memory_view(
        record,
        stored,
        entries,
        reader=asked.reach,
        department=asked.caller.principal.primary_department,
        now=asked.now,
    )
    found = next((one for one in stored.learnings if one.memory_id == memory_id), None)
    if found is None or changeable(view, memory_id) is None:
        log.info("agent memory change not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return record, found, view


def changeable(view: AgentMemoryView, memory_id: str) -> bool | None:
    """Whether this reader may change a memory their view shows, or None when it shows none.

    None is the answer a memory that does not exist gets; False is a memory they are shown and
    may not change. See `THE_STEWARD_AND_THE_PERSON_IT_IS_ABOUT_MAY_CHANGE_A_MEMORY`.
    """
    shown = [
        one
        for one in (*view.curated, *view.extracted, *view.about_you)
        if one.memory_id == memory_id
    ]
    if not shown:
        return None
    return any(one.changeable for one in shown)


def _refused() -> JSONResponse:
    return JSONResponse(
        status_code=403, content={"message": CHANGING_A_MEMORY_NEEDS_THE_STEWARD_OR_ITS_SUBJECT}
    )


@router.post(DELETE_PATH, response_model=MemoryChangedView, responses=COMMON_RESPONSES)
async def delete_agent_memory(
    request: Request, agent_id: str, memory_id: MemoryId, asked: Asked
) -> JSONResponse | MemoryChangedView:
    """Delete one memory: the mark that stops it being recalled. See the module docstring."""
    _, found, view = await _shown(request, agent_id, memory_id, asked)
    if not changeable(view, memory_id):
        return _refused()
    records = memory_records_of(request)
    if records is None:
        raise _no_agent_here()
    decided = await records.undo(
        found,
        actor=asked.caller.principal.id,
        trace_id=trace_of_request(),
        ent_hash=asked.reach.ent_hash(),
    )
    told = undone_view(decided)
    return MemoryChangedView(memory_id=memory_id, took_effect=told.took_effect, told=told.told)


@router.post(EDIT_PATH, response_model=MemoryChangedView, responses=COMMON_RESPONSES)
async def edit_agent_memory(
    request: Request, agent_id: str, memory_id: MemoryId, body: EditAsked, asked: Asked
) -> JSONResponse | MemoryChangedView:
    """Correct what one memory says: a new memory naming it, and a mark. See the docstring."""
    _, found, view = await _shown(request, agent_id, memory_id, asked)
    if not changeable(view, memory_id):
        return _refused()
    records = memory_records_of(request)
    if records is None:
        raise _no_agent_here()
    statement = body.statement.strip()
    replacement = replacement_for(found, statement, at=asked.now)
    decided = await records.edit(
        found,
        replacement,
        statement,
        prompted_by=Signal.REJECTED,
        actor=asked.caller.principal.id,
        trace_id=trace_of_request(),
        ent_hash=asked.reach.ent_hash(),
    )
    return MemoryChangedView(
        memory_id=memory_id,
        took_effect=decided.replacement is not None,
        replaced_by=None if decided.replacement is None else decided.replacement.memory_id,
        told=decided.reason,
    )
