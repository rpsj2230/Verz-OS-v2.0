"""My workspace over HTTP: what a person has asked, kept and been given, for a reader who
administers nothing.

`docs/screens.html` SCREEN 12 is a member's own page: the agents they can call, the knowledge
they own, what the system learnt about them, their budget, and what they can ask about. The
decisions behind every card already exist and none of them could be reached from a browser.
`brain.member.shell` registers the page as the member screen `home`, `brain.console.own_things`
and `brain.member_activity` narrow each figure to one person, and `brain.console.govern_estate.
subject_memory` decides which memories a reader may read back. This route loads, calls those,
and projects what comes back.

**Whether the page opens is `brain.console.reads.permitted` over the member screen's own read.**
`brain.member.shell.MemberScreen` refuses at construction any capability a governance screen
is gated on, so the grant that opens this page opens no administrative screen, and a person
holding every administrative grant and not the member one is refused here like anybody else.
That is the "administers nothing" half of M27.7.28 as a property rather than a menu. See
`THE_MEMBER_GRANT_OPENS_THIS_AND_NOTHING_ELSE`.

**Every figure is the caller's own and the principal is never a parameter.** There is no query
parameter naming a person, so there is no request that asks this route about somebody else: the
principal is the one the token resolved. The loads are narrowed to that principal in SQL, which
bounds what leaves the database, and the functions that decide what a row means narrow again by
`brain.console.own_things.is_own`: `my_agents` and `personal_budget` inside themselves, the
knowledge rows here, and `subject_memory` by the formation's principal.

**Asked.** The questions this person asked this month, counted from `ops.question_asked`, which
the answer lane writes. A count of one's own questions discloses nothing about anybody else.
Corrections are not counted, because nothing records one: `brain.member_activity.
activity_this_month` counts them from chat turns, and no store writes a turn.

**Kept.** The knowledge items this person stewards, from `know.item`, with how widely each
reaches; and the memories formed from their own conversations that they may still read back,
through `subject_memory`, which asks `may_recall` about them as they are now. A memory formed
while they held a grant since revoked is absent here, which is
`brain.member_activity.OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS`.

**Forget and edit, since 2026-09-29** (M16.4.2). `POST /me/memory/forget` and `/me/memory/edit`
act on one memory formed from this person's own words, decided by `brain.console.own_things`
and written through `brain.ops.memory_store.StoredMemoryRecords`, the store the Learning screen's
undo writes through: a forget is a mark and an edit is a replacement and a supersession, so nothing
is deleted and the next recall reads the change. Until then this card said nothing stored a
correction, which stopped being true when `mem.correction` landed and the sentence did not move.
See `A_PERSON_FORGETS_AND_EDITS_WHAT_WAS_FORMED_FROM_THEIR_OWN_WORDS`.

**Given.** The agents this person can call, each with where it runs at their own run's reach
and how often they used it, which is `brain.member_activity.my_agents`; their own ceilings and
what has gone against each, which is `personal_budget`; and what they can ask about, which is
`brain.member.shell.disclosure_line` read off their grants.

**A spend load that comes back full shows no budget.** A ceiling beside an undercounted spend
reads as headroom somebody does not have, which is
`brain.console.own_things.A_CEILING_WITH_NO_WINDOW_REPORTS_FULL_HEADROOM` arriving through a
bound. So the budget is withheld with a sentence rather than shown short. See
`A_SPEND_LOAD_THAT_CAME_BACK_FULL_UNDERSTATES_WHAT_WAS_SPENT`.

**What nothing records is said on the page.** Corrections, an undo, which accounts are connected,
and when an item was verified or how often it was used: each has a sentence, so a card with
nothing under it is never read as nothing having happened.

**What has never run.** No PostgreSQL here, so the loads have not been executed against one. What
is tested is the statements they compile to, every refusal and its order, and each decision
reached through the real application.

Task ids: M27.7.28, M16.4.2
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Row, Select, String, column, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    actual_of,
    declared_channels,
    every_agent,
    product_field_policy,
    record_of,
    viewer_of,
)
from brain.api import API_PREFIX, COMMON_RESPONSES, bound_trace_id
from brain.api_routes import Asked
from brain.console.govern_estate import subject_memory
from brain.console.own_things import OwnThingsError, delete_own_memory, edit_own_memory, is_own
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.estate_routes import (
    MAX_MEMORIES_CONSIDERED,
    RememberedAbout,
    learning_of,
    memory_records_of,
    remembered_about,
)
from brain.knowledge.search import PRINCIPAL_SETTING
from brain.locale import currency_or_unset
from brain.member.shell import disclosure_line, member_screen
from brain.member_activity import my_agents, personal_budget
from brain.memory.digest import Learning
from brain.memory.signals import Signal
from brain.memory.turn import MAX_STATEMENT_CHARS, MEMORY_ID_DIGEST_CHARS, MEMORY_ID_PREFIX
from brain.ops.budget_store import in_force
from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.memory_store import MemoryRecords
from brain.ops.replica_store import ConsoleReads
from brain.routing_routes import sessions_of
from brain.tables.adoption import QuestionAskedRow
from brain.tables.agent import AgentRow
from brain.tables.learning import MEMORY_ID_CHARS
from brain.tables.spend import SpendActualRow

log = structlog.get_logger()

#: The member screen this route serves.
MEMBER_HOME: Final = "home"

#: How far back "used" is counted on the agents card. SCREEN 12's column is "Used 30d".
USED_OVER: Final = timedelta(days=30)

#: How many of this person's own knowledge items one load reads.
MAX_OWN_ITEMS: Final = 200

#: How many of this person's own completed runs one load reads. A resource bound, and a load
#: that reaches it withholds the budget rather than showing it short.
MAX_OWN_RUNS: Final = 5000

# ------------------------------------------------------------------ written-down reasons
#: Why the page is gated on the member grant and nothing else.
THE_MEMBER_GRANT_OPENS_THIS_AND_NOTHING_ELSE: Final = (
    "This page is the member screen home, and brain.member.shell refuses a member screen whose "
    "capability gates any governance screen. So what opens it is a grant that opens no "
    "administrative surface, a person who administers nothing reaches it with that grant alone, "
    "and holding every administrative grant without it opens nothing here."
)

#: Why a budget over a truncated spend load is withheld.
A_SPEND_LOAD_THAT_CAME_BACK_FULL_UNDERSTATES_WHAT_WAS_SPENT: Final = (
    "A ceiling shown beside the spend a bounded load happened to read is a ceiling with more "
    "headroom than the person has, on the page they check before starting something expensive. "
    "When the load comes back full the budget is not shown, and a sentence says why."
)

#: What the budget card says when the spend load came back full.
MORE_SPEND_THAN_THIS_PAGE_READS: Final = (
    "You have more runs this month than this page reads at once, so it cannot say how much of "
    "your budget is left without understating what you have spent. Your department administrator "
    "can read the full figure."
)

#: What the questions figure does not include.
CORRECTIONS_ARE_NOT_RECORDED: Final = (
    "Corrections are not counted: nothing on this install records when you told it an answer was "
    "wrong."
)

#: What the learned card says beside its controls.
FORGET_AND_EDIT_SAY: Final = (
    "Forget stops a memory being used at once and keeps the record of it; if it replaced an "
    "earlier one, the earlier one is used again. Edit keeps what you write instead, in the same "
    "place, and the old words stay in its history."
)

#: Why a person may forget or edit a memory of theirs and nobody else's, here.
A_PERSON_FORGETS_AND_EDITS_WHAT_WAS_FORMED_FROM_THEIR_OWN_WORDS: Final = (
    "Who a memory is about is who was asking when it formed, and this page offers forget and edit "
    "on those memories alone, decided by brain.console.own_things, which is the ownership the "
    "page reads its list by. A memory of somebody else's is refused in the words a memory that "
    "does not exist is refused in. Forget writes a mark and edit writes a replacement and a mark, "
    "through the store the Learning screen's undo writes through, so nothing is ever deleted and "
    "the next recall, the next answer and the Memory screen all read the change at once."
)

#: What the connected accounts card says.
ACCOUNTS_ARE_NOT_READ_HERE: Final = (
    "Below are the sources you may connect your own account with, and whether you have. "
    "Connecting one never widens what you can see: it adds a source that is already yours, read "
    "only for your own questions."
)

#: What the knowledge card does not show.
VERIFICATION_AND_USE_ARE_NOT_RECORDED: Final = (
    "When each item was last verified and how often it was used are not shown: nothing on this "
    "install counts how often an item is drawn on."
)


# ------------------------------------------------------------------------ the shapes
class MineAskedView(BaseModel):
    """How many questions this person asked since the start of this month."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    since: datetime
    questions: int
    corrections: str


class MineAgentView(BaseModel):
    """One agent this person can call: who provides it, where it runs, how often they used it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    #: `provided` by a department or the company, or `personal`.
    provision: str
    channels: list[str]
    uses: int


class MineCeilingView(BaseModel):
    """One of this person's own ceilings and what has gone against it, in minor units."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    ceiling_minor: int
    spent_minor: int
    headroom_minor: int
    #: The ISO 4217 code the minor units are in, `XXX` when the install chose none. See
    #: `brain.report_routes.A_FIGURE_SAYS_ITS_CURRENCY_AND_ITS_CLOCK`.
    currency: str
    alerts_crossed: list[float]


class MineItemView(BaseModel):
    """One knowledge item this person stewards, and how widely it reaches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    level: str
    department: str | None


class MineLearnedView(BaseModel):
    """One memory formed from this person's conversations that they may still read back."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    statement: str
    #: True for something stated, false for something the system inferred.
    stated: bool
    confidence: float
    formed_at: datetime


class MineMemoryAsked(BaseModel):
    """Which of this person's memories to forget: its id and nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str = Field(min_length=1, max_length=MEMORY_ID_CHARS, pattern=r"^\S+$")


class MineMemoryEdited(BaseModel):
    """Which of this person's memories to edit, and what it should say instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str = Field(min_length=1, max_length=MEMORY_ID_CHARS, pattern=r"^\S+$")
    statement: str = Field(min_length=1, max_length=MAX_STATEMENT_CHARS)


class MineMemoryChangedView(BaseModel):
    """What a forget or an edit did: whether it took effect, the store's sentence, and the id of
    the memory an edit wrote in its place."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    took_effect: bool
    told: str
    replacement_id: str | None = None


class MineWorkspaceView(BaseModel):
    """SCREEN 12, for the person asking. Every figure on it is theirs.

    `budget` is None exactly when `budget_unread` says why; an empty list is a person with no
    ceilings of their own, which is a real answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    asked: MineAskedView
    agents: list[MineAgentView]
    agents_used_since: datetime
    budget: list[MineCeilingView] | None
    budget_unread: str
    knowledge: list[MineItemView]
    knowledge_truncated: bool
    knowledge_not_shown: str
    learned: list[MineLearnedView]
    learned_undo: str
    can_ask_about: str
    accounts: str
    staleness: StalenessBanner | None = None


# ---------------------------------------------------------------- the statements
def month_start(now: datetime) -> datetime:
    """The first instant of this calendar month, in the zone `now` carries."""
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def day_start(now: datetime) -> datetime:
    """The first instant of this calendar day, in the zone `now` carries."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def questions_asked(principal_id: str, since: datetime, until: datetime) -> Select[tuple[int]]:
    """How many questions this person asked in `[since, until]`."""
    return (
        select(func.count())
        .select_from(QuestionAskedRow)
        .where(
            QuestionAskedRow.principal_id == principal_id,
            QuestionAskedRow.at >= since,
            QuestionAskedRow.at <= until,
        )
    )


def runs_by(principal_id: str, since: datetime, limit: int) -> Select[tuple[SpendActualRow]]:
    """This person's own completed runs since an instant, newest first, bounded."""
    return (
        select(SpendActualRow)
        .where(SpendActualRow.principal_id == principal_id, SpendActualRow.at >= since)
        .order_by(SpendActualRow.at.desc())
        .limit(limit)
    )


def items_stewarded(limit: int) -> Select[tuple[str, str, str, str | None]]:
    """The retrievable knowledge items this person stewards, in reference order, bounded.

    **Read through `know.items_stewarded_by_the_session`, with the session told who is present.**
    `know.item`'s policy is the corpus's reach and admits a personal item or a draft only to a
    session naming its owner, and this load named nobody, so a person's own personal items and
    drafts were absent from what they keep. `0069`'s function returns the rows whose owner is the
    principal `principal_setting` names, and `is_own` is still asked of each. See
    `WHAT_A_PERSON_STEWARDS_IS_READ_AS_THEM`.
    """
    items = func.know.items_stewarded_by_the_session(limit).table_valued(
        column("item_id", String),
        column("owner_id", String),
        column("visibility", String),
        column("department", String),
        name="item",
    )
    return select(items.c.item_id, items.c.owner_id, items.c.visibility, items.c.department)


def principal_setting(principal_id: str) -> Select[tuple[str]]:
    """The statement that tells this transaction who is present, for the stewardship read."""
    return select(func.set_config(PRINCIPAL_SETTING, principal_id, True))


#: Why the stewardship read names the person to the database first.
WHAT_A_PERSON_STEWARDS_IS_READ_AS_THEM: Final = (
    "know.item's row-level security admits a personal item or a draft only to a session naming "
    "its owner, and My workspace named nobody, so the list of what a person keeps left out their "
    "own personal items and drafts. The load sets app.principal_id to the person asking, in the "
    "same transaction, and reads through know.items_stewarded_by_the_session, which returns the "
    "rows that principal owns and no title."
)


# ------------------------------------------------------------------------ the wiring
def _console_reads(request: Request) -> ConsoleReads:
    """Where the page is read from, or a process-level fault. `brain.estate_routes`' shape."""
    found = getattr(request.app.state, "console_reads", None)
    if isinstance(found, ConsoleReads):
        return found
    factory: async_sessionmaker[AsyncSession] | None = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return ConsoleReads(factory)


def _not_answerable() -> Absent:
    """The refusal this page makes. Names the page and never the reader or a row."""
    return Absent("your workspace is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["member"])


@router.get("/me/workspace", response_model=MineWorkspaceView, responses=COMMON_RESPONSES)
async def workspace(request: Request, asked: Asked) -> MineWorkspaceView:
    """What the person asking has asked, kept and been given.

    The member screen's question first and the database second, so a caller who may not open
    the page is refused identically on an install with a database and on one without.
    """
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("workspace not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()

    me = asked.caller.principal.id
    now = asked.now
    this_month = month_start(now)
    used_since = now - USED_OVER
    runs_since = min(this_month, used_since)

    async def load(
        session: AsyncSession,
    ) -> tuple[
        int,
        list[SpendActualRow],
        list[AgentRow],
        list[Row[tuple[str, str, str, str | None]]],
        RememberedAbout,
        list[BudgetRow],
    ]:
        questions = int((await session.execute(questions_asked(me, this_month, now))).scalar_one())
        runs = list((await session.execute(runs_by(me, runs_since, MAX_OWN_RUNS))).scalars().all())
        agents = list((await session.execute(every_agent())).scalars().all())
        await session.execute(principal_setting(me))
        items = list((await session.execute(items_stewarded(MAX_OWN_ITEMS + 1))).all())
        remembered = await remembered_about(session, me, MAX_MEMORIES_CONSIDERED)
        ceilings: list[BudgetRow] = []
        for period in (BudgetPeriod.DAY, BudgetPeriod.MONTH):
            found = await in_force(session, (BudgetLevel.USER, me, period), now)
            if found is not None:
                ceilings.append(found)
        return questions, runs, agents, items, remembered, ceilings

    served = await _console_reads(request).read(load, now=now)
    questions, runs, agent_rows, item_rows, stored, ceilings = served.value

    actuals = [one for one in (actual_of(row) for row in runs) if one is not None]
    records = [one for one in (record_of(row) for row in agent_rows) if one is not None]
    agents = my_agents(
        records,
        actuals,
        principal_id=me,
        viewer=viewer_of(asked),
        reach=asked.reach,
        capabilities=declared_channels(),
        policy=product_field_policy(),
        since=used_since,
        until=now,
        now=now,
    )

    code = currency_or_unset()
    budget: list[MineCeilingView] | None = None
    budget_unread = MORE_SPEND_THAN_THIS_PAGE_READS
    if len(runs) < MAX_OWN_RUNS:
        budget_unread = ""
        budget = [
            MineCeilingView(
                period=one.period.value,
                ceiling_minor=one.ceiling_minor,
                spent_minor=one.spent_minor,
                headroom_minor=one.headroom_minor,
                currency=code,
                alerts_crossed=list(one.alerts_crossed),
            )
            for one in personal_budget(
                ceilings,
                actuals,
                principal_id=me,
                windows={
                    BudgetPeriod.DAY: (day_start(now), now),
                    BudgetPeriod.MONTH: (this_month, now),
                },
            )
        ]

    owned = [row for row in item_rows[:MAX_OWN_ITEMS] if is_own(me, row.owner_id)]

    remembered = subject_memory(
        subject_id=me,
        entries=stored.entries,
        reader=asked.reach,
        now=now,
        supersessions=stored.corrections.supersessions,
        demotions=stored.corrections.demotions,
    )

    return MineWorkspaceView(
        principal_id=me,
        display_name=asked.caller.principal.display_name,
        asked=MineAskedView(
            since=this_month, questions=questions, corrections=CORRECTIONS_ARE_NOT_RECORDED
        ),
        agents=[
            MineAgentView(
                agent_id=one.agent_id,
                provision=one.provision.value,
                channels=[str(channel) for channel in one.channels],
                uses=one.uses,
            )
            for one in agents
        ],
        agents_used_since=used_since,
        budget=budget,
        budget_unread=budget_unread,
        knowledge=[
            MineItemView(item_id=row.item_id, level=row.visibility, department=row.department)
            for row in owned
        ],
        knowledge_truncated=len(item_rows) > MAX_OWN_ITEMS,
        knowledge_not_shown=VERIFICATION_AND_USE_ARE_NOT_RECORDED,
        learned=[
            *(
                MineLearnedView(
                    memory_id=one.memory_id,
                    statement=one.statement,
                    stated=True,
                    confidence=one.seen.confidence,
                    formed_at=one.seen.formation.formed_at,
                )
                for one in remembered.memory.curated
            ),
            *(
                MineLearnedView(
                    memory_id=one.memory_id,
                    statement=one.statement,
                    stated=False,
                    confidence=one.seen.confidence,
                    formed_at=one.seen.formation.formed_at,
                )
                for one in remembered.memory.extracted
            ),
        ],
        learned_undo=FORGET_AND_EDIT_SAY,
        can_ask_about=disclosure_line(asked.reach, now),
        accounts=ACCOUNTS_ARE_NOT_READ_HERE,
        staleness=served.banner,
    )


# ------------------------------------------------------------ forgetting and editing
def replacement_for(
    learning: Learning, *, principal_id: str, statement: str, at: datetime
) -> Learning:
    """The memory an edit writes in place of `learning`: what it says is new, and nothing else.

    Everything `brain.memory.review.replacement_gaps` holds equal is copied, and it is formed now,
    because a person restating a thing is a new statement of it. Its id is derived from the memory
    it replaces, the person, the words and the instant, and never minted.
    """
    source = f"{principal_id}\n{learning.memory_id}\n{statement}\n{at.isoformat()}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return Learning(
        memory_id=f"{MEMORY_ID_PREFIX}{digest[:MEMORY_ID_DIGEST_CHARS]}",
        proposal=learning.proposal,
        formation=replace(learning.formation, formed_at=at),
        formed_confidence=learning.formed_confidence,
        replaced_id=learning.memory_id,
        agent_id=learning.agent_id,
    )


async def stored_learning(
    sessions: async_sessionmaker[AsyncSession], memory_id: str
) -> Learning | None:
    """The memory asked about, as the domain's `Learning`, or None when there is no such memory.

    Whose it is is not asked here: `brain.console.own_things.delete_own_memory` and
    `edit_own_memory` ask it, so ownership is decided in one place rather than in two that could
    disagree, and a memory of somebody else's is refused by them in the words a missing one is.
    """
    async with sessions() as session:
        return await learning_of(session, memory_id)


async def forgotten(
    sessions: async_sessionmaker[AsyncSession],
    records: MemoryRecords,
    *,
    principal_id: str,
    memory_id: str,
    ent_hash: str,
    trace_id: str,
    now: datetime,
) -> MineMemoryChangedView | None:
    """Forget one of this person's memories, or None when it is not theirs or not there.

    `brain.console.own_things.delete_own_memory` decides it is theirs and what a forget is, and the
    store writes it under the lock the Learning screen's undo takes. The body of
    `forget_my_memory`, and what the install's acceptance check calls.
    """
    found = await stored_learning(sessions, memory_id)
    if found is None:
        return None
    try:
        delete_own_memory(found, principal_id=principal_id, at=now)
    except OwnThingsError:
        return None
    decided = await records.undo(found, actor=principal_id, trace_id=trace_id, ent_hash=ent_hash)
    return MineMemoryChangedView(
        memory_id=found.memory_id, took_effect=decided.took_effect, told=decided.reason
    )


async def edited(
    sessions: async_sessionmaker[AsyncSession],
    records: MemoryRecords,
    *,
    principal_id: str,
    memory_id: str,
    statement: str,
    ent_hash: str,
    trace_id: str,
    now: datetime,
) -> MineMemoryChangedView | None:
    """Edit what one of this person's memories says, or None when it is not theirs or not there.

    `brain.console.own_things.edit_own_memory` decides it is theirs and that the replacement changes
    the words and nothing else, and the store writes the replacement, its learning record and the
    supersession in one transaction. The body of `edit_my_memory`.
    """
    said = statement.strip()
    found = None if not said else await stored_learning(sessions, memory_id)
    if found is None:
        return None
    replacement = replacement_for(found, principal_id=principal_id, statement=said, at=now)
    try:
        edit_own_memory(found, replacement, principal_id=principal_id, at=now)
    except (OwnThingsError, ValueError):
        return None
    decided = await records.edit(
        found,
        replacement,
        said,
        prompted_by=Signal.REJECTED,
        actor=principal_id,
        trace_id=trace_id,
        ent_hash=ent_hash,
    )
    return MineMemoryChangedView(
        memory_id=found.memory_id,
        took_effect=decided.replacement is not None,
        told=decided.reason,
        replacement_id=None if decided.replacement is None else decided.replacement.memory_id,
    )


def _stores(
    request: Request, asked: Asked
) -> tuple[async_sessionmaker[AsyncSession], MemoryRecords]:
    """The member grant first, then this process's sessions and memory store, or a fault."""
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own memory not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    sessions = sessions_of(request)
    records = memory_records_of(request)
    if sessions is None or records is None:
        raise Failed("no database on this process")
    return sessions, records


@router.post("/me/memory/forget", response_model=MineMemoryChangedView, responses=COMMON_RESPONSES)
async def forget_my_memory(
    request: Request, body: MineMemoryAsked, asked: Asked
) -> MineMemoryChangedView:
    """Forget one memory formed from this person's own words, and say what was written.

    See `A_PERSON_FORGETS_AND_EDITS_WHAT_WAS_FORMED_FROM_THEIR_OWN_WORDS`. Somebody else's memory
    and one that does not exist are the one 404. A second forget is answered 200 with
    `took_effect` false and the store's sentence.
    """
    sessions, records = _stores(request, asked)
    done = await forgotten(
        sessions,
        records,
        principal_id=asked.caller.principal.id,
        memory_id=body.memory_id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=bound_trace_id(request),
        now=asked.now,
    )
    if done is None:
        log.info("own memory not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    log.info("own memory forgotten", principal=asked.caller.principal.id, took=done.took_effect)
    return done


@router.post("/me/memory/edit", response_model=MineMemoryChangedView, responses=COMMON_RESPONSES)
async def edit_my_memory(
    request: Request, body: MineMemoryEdited, asked: Asked
) -> MineMemoryChangedView:
    """Edit what one memory formed from this person's own words says, and say what was written.

    The old memory stays on the record, marked as replaced, and its words are in the history.
    Somebody else's memory, one that does not exist and a statement of white space are the one 404.
    """
    sessions, records = _stores(request, asked)
    done = await edited(
        sessions,
        records,
        principal_id=asked.caller.principal.id,
        memory_id=body.memory_id,
        statement=body.statement,
        ent_hash=asked.reach.ent_hash(),
        trace_id=bound_trace_id(request),
        now=asked.now,
    )
    if done is None:
        log.info("own memory not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    log.info("own memory edited", principal=asked.caller.principal.id, took=done.took_effect)
    return done
