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
`brain.member_activity.OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS`. No undo control:
nothing stores a correction, so an undo would reach neither a row nor a behaviour, which is
`brain.estate_routes.AN_UNDO_WITH_NO_CORRECTION_STORE_REACHES_NEITHER_A_ROW_NOR_A_BEHAVIOUR`.

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

Task ids: M27.7.28
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    actual_of,
    declared_channels,
    every_agent,
    product_field_policy,
    record_of,
    viewer_of,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern_estate import subject_memory
from brain.console.own_things import is_own
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.estate_routes import MAX_MEMORIES_CONSIDERED, RememberedAbout, remembered_about
from brain.knowledge.item import RETRIEVABLE_STATES
from brain.member.shell import disclosure_line, member_screen
from brain.member_activity import my_agents, personal_budget
from brain.ops.budget_store import in_force
from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.replica_store import ConsoleReads
from brain.routing_routes import sessions_of
from brain.tables.adoption import QuestionAskedRow
from brain.tables.agent import AgentRow
from brain.tables.knowledge import KnowledgeItemRow
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

#: Why the learned card has no undo control.
UNDO_IS_NOT_RECORDED: Final = (
    "Nothing here can be undone from this page yet: nothing on this install stores an undo, so a "
    "button would change neither what is kept nor any answer you are given."
)

#: What the connected accounts card says.
ACCOUNTS_ARE_NOT_READ_HERE: Final = (
    "Which of your own accounts are connected is not read by this page. Connecting one never "
    "widens what you can see: it adds a source that is already yours, on your own access."
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


def items_stewarded_by(principal_id: str, limit: int) -> Select[tuple[KnowledgeItemRow]]:
    """The retrievable knowledge items this person stewards, in reference order, bounded."""
    return (
        select(KnowledgeItemRow)
        .where(
            KnowledgeItemRow.owner_id == principal_id,
            KnowledgeItemRow.state.in_(sorted(one.value for one in RETRIEVABLE_STATES)),
        )
        .order_by(KnowledgeItemRow.item_id)
        .limit(limit)
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
        list[KnowledgeItemRow],
        RememberedAbout,
        list[BudgetRow],
    ]:
        questions = int((await session.execute(questions_asked(me, this_month, now))).scalar_one())
        runs = list((await session.execute(runs_by(me, runs_since, MAX_OWN_RUNS))).scalars().all())
        agents = list((await session.execute(every_agent())).scalars().all())
        items = list(
            (await session.execute(items_stewarded_by(me, MAX_OWN_ITEMS + 1))).scalars().all()
        )
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
        learned_undo=UNDO_IS_NOT_RECORDED,
        can_ask_about=disclosure_line(asked.reach, now),
        accounts=ACCOUNTS_ARE_NOT_READ_HERE,
        staleness=served.banner,
    )
