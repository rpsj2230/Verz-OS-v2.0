"""The three places a person reads memory back, and what each one refuses to show.

A per-agent tab, a department view and a tier-three queue. All three are listings of things
the system learnt, and a listing is where the rule everything else keeps gets broken by
accident, because a page of rows wants a total at the top of it and a total beside a filtered
list is the number of things the reader may not see.

**A listing is entitled like every other disclosure, through the same intersection.** The
per-agent tab is the one that makes this concrete: a tab listing everything an agent has ever
learnt would show a caller memories formed from other people's conversations, which is exactly
the failure `brain.memory.formation` exists to prevent, arriving through a surface rather than
through recall. So the tab computes `E_run(caller, agent) = E(caller) intersect agent_ceiling`
by calling `EntitlementSet.intersect`, the same method `gate.leash.decide` and
`ops.automation.flow_reach` call, and hands the result to `formation.may_recall`. No second
definition of narrower is written here. See `A_LISTING_IS_ENTITLED_LIKE_ANY_OTHER_DISCLOSURE`.

The intersection is computed inside `agent_memory` rather than taken as an already-narrowed
parameter, which is the argument `gate.leash.decide` makes and it holds here for the same
reason: a signature taking one entitlement set would work exactly as well until somebody
passed the caller's own reach and nothing noticed the agent's ceiling had stopped applying.

**The department view is not a wider lens on individuals.** A department head may see what the
system has learnt *about the department*. That is not the same as what it learnt from each of
their reports' conversations, and the difference is a performance review assembled out of a
memory tab. The two cannot be separated by looking at a memory's text, and this module does
not look at text at all, so the honest line is drawn on the change kind: the view shows only
what `tiers.CHANGES_WHAT_ANYBODY_MAY_SEE` covers, which is the set of learnings that are about
the organisation rather than about somebody's way of asking questions.

What that leaves out is stated plainly rather than hidden. Preferences, retrieval boosts and
demotions, entity links, negative signals, fast-path rules and procedural shortcuts are all
absent from the department view even when they were formed inside that department, because
each of them is a fact about how one person's conversations went. The cost is real: the view
is thin, and it overlaps almost entirely with the tier-three queue, since every change in
`CHANGES_WHAT_ANYBODY_MAY_SEE` is gated. That overlap is the honest consequence of refusing to
widen rather than a bug in the split. See `A_DEPARTMENT_VIEW_IS_NOT_A_WIDER_LENS_ON_ITS_MEMBERS`.

Rejected: a department view built from the department's members, unioning what each of them
learnt and relying on the head holding a broad enough grant to see it. It is what somebody
asks for, it is one join, and it is a surface whose whole purpose is to show one person what
the system inferred from their colleagues' conversations.

**The queue lists and cannot decide.** `tiers.THIS_MODULE_HAS_NOWHERE_TO_APPROVE` says a gated
change is approved by a surface that does not exist, and this is not that surface. There is no
`approve` here, no `apply`, no `grant`, and `QueueItem` deliberately carries no control field
at all, where `MemoryItem` carries one: a delete button drawn on a gated proposal is a person
deciding a scope widening by pressing something that says delete.

**The budget alarm is raised on what this reader can see, and that is a privacy decision
before it is an ergonomic one.** An alarm computed on the true queue and shown beside three
visible rows tells the reader there are at least a dozen more, which is the subtraction the
whole system refuses. So the alarm reads the filtered list. The cost is that a queue spread
thinly across departments raises nobody's alarm, and the answer to that is an operator whose
reach covers the estate, not a number leaked to everybody else. See
`THE_ALARM_IS_RAISED_ON_WHAT_THE_READER_CAN_SEE`.

Rejected: putting the queue length on the alarm. It is the obvious field, it is what an
operator asks for, and on a filtered queue it is a count of hidden items whenever the filter
did anything.

**Nothing here writes, applies or approves.** `delete` returns the correction `digest.undo`
builds and stores nothing, the views build values, and `now` is a parameter everywhere.

Task ids: M16.5.2, M16.5.3, M16.5.4
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from datetime import datetime

from brain.core.entitlement import EntitlementSet
from brain.core.scope import Scope
from brain.memory.correction import Demotion, Supersession
from brain.memory.digest import (
    COUNTING_FIELD_NAMES,
    Learning,
    MemoryItem,
    Undo,
    memory_item,
    undo,
)
from brain.memory.formation import may_recall
from brain.memory.signals import Signal
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Change, Tier

# ------------------------------------------------------------------ written-down reasons
#: Why a listing goes through the entitlement model rather than around it.
A_LISTING_IS_ENTITLED_LIKE_ANY_OTHER_DISCLOSURE = (
    "A memory tab listing everything an agent has learnt would show a caller memories formed "
    "from other people's conversations, which is the exact failure `brain.memory.formation` "
    "exists to prevent, arriving through a page of rows instead of through an answer. So a "
    "listing takes the caller's reach, narrows it by the agent's ceiling using "
    "`EntitlementSet.intersect`, and asks `formation.may_recall` about every row. That is the "
    "same composition `gate.leash.decide` and `ops.automation.flow_reach` use and there is no "
    "second definition of narrower anywhere in this module: a second one is a second place "
    "for the central invariant to be wrong, and the permissive copy wins the day they differ."
)

#: Why the department view shows the organisation and not the people in it.
A_DEPARTMENT_VIEW_IS_NOT_A_WIDER_LENS_ON_ITS_MEMBERS = (
    "A department head may see what the system has learnt about the department. What it "
    "learnt from each of their reports' conversations is a different thing, and a view that "
    "unioned the second is a performance review assembled out of a memory tab: preferences "
    "and corrections are small statements that somebody's answers went badly, and gathered "
    "under a manager's name they read as a statement about the person. The two cannot be "
    "told apart by reading a memory, and nothing here reads one, so the line is drawn on the "
    "change kind: the view shows only what `tiers.CHANGES_WHAT_ANYBODY_MAY_SEE` covers, "
    "which is the set of learnings that are about the organisation. Everything else is left "
    "out, including learnings formed inside that department, and the view is thin as a "
    "result. Thin and correct is the trade; widening it quietly is not available."
)

#: Why the control in a memory tab says delete and writes a mark.
DELETE_IS_THE_SAME_MARK_THE_DIGEST_UNDO_WRITES = (
    "The control a person sees as delete is implemented as `digest.undo`, which writes a "
    "supersession or a demotion and removes nothing. One implementation and two names, "
    "because two implementations of a mark is two things that can disagree about what a "
    "delete means, and the one that ends up meaning delete is the one written in a hurry by "
    "somebody who read the button rather than the module. `brain.memory.correction` gives "
    "the reason in full: a deleted memory cannot explain itself, and a mark is undoable "
    "where a delete is not."
)

#: Why the queue can list a gated change and can do nothing else with it.
THE_QUEUE_LISTS_AND_CANNOT_DECIDE = (
    "`tiers.propose` returns a proposal and there is no `apply`; a `Proposal` carries no "
    "approver, no decision and no timestamp, so approving a gated change is a surface that "
    "does not exist rather than a field somebody adds. This is not that surface. There is no "
    "callable here whose name could be read as approving, applying, granting or widening, "
    "and `QueueItem` carries no control field where `MemoryItem` carries one, because a "
    "delete button drawn beside a scope widening is a person deciding it by pressing "
    "something that says delete."
)

#: Why the alarm is computed on the rows this reader can see.
THE_ALARM_IS_RAISED_ON_WHAT_THE_READER_CAN_SEE = (
    "An alarm computed on the whole queue and shown beside three visible rows tells the "
    "reader there are at least a dozen more, which is a count of hidden items arrived at by "
    "subtraction and is the one thing no surface here may say. So the alarm reads the "
    "filtered list, and it carries no number at all: whether it is raised, and a sentence. "
    "The cost is that a queue spread thinly across departments raises nobody's alarm, and "
    "the answer to that is somebody whose reach covers the estate looking at it, not a "
    "figure leaked to everybody whose reach does not."
)

# ------------------------------------------------------------------------- the department
#: The scope field a department is named in. One spelling, for the reason
#: `formation.clause_place` exists: a field spelled two ways in two call sites produces two
#: memories about the same department that do not match each other. `Scope.department` builds
#: the grant side of the same pairing.
DEPARTMENT_FIELD = "department"

#: What a department view may show.
#:
#: Deliberately the same object as `tiers.CHANGES_WHAT_ANYBODY_MAY_SEE` rather than a copy of
#: its members. A copy would drift, and the direction it drifts is always wider, because the
#: pressure on this view is always "why can I not see what my team's assistant learnt". What
#: is checked instead of the equality is the behaviour: a test puts a preference formed
#: inside the department in front of the head and proves it does not appear.
DEPARTMENT_CHANGES: frozenset[Change] = CHANGES_WHAT_ANYBODY_MAY_SEE

# ---------------------------------------------------------------------------- the alarm
#: How long one gated change takes a person to review properly.
#:
#: Four minutes. A tier-three proposal is a change to who may see what, so reviewing one
#: means reading what it would widen, working out who that reaches and deciding: it is not a
#: row somebody skims. Four is the figure this whole alarm rests on and it is deliberately
#: the one a reader can argue with.
REVIEW_MINUTES_PER_ITEM = 4

#: How long one sitting of review is.
#:
#: An hour. Not a measure of anybody's attention span: an hour is what somebody blocks out
#: for a queue before it stops being a task and becomes a project, and a queue that cannot be
#: emptied in the slot people actually give it is a queue that is never emptied.
REVIEW_SITTING_MINUTES = 60


#: The queue length above which the alarm fires.
#:
#: **Anchored outside itself, which is the whole point of the figure.** What makes a review
#: queue worth an alarm is not that it reached some round number; it is that it has grown
#: past what a person can work through in one sitting, because a queue longer than that is a
#: queue that is not being worked through, and a tier-three queue that is not being worked
#: through is a set of access decisions nobody is making. So this is one sitting divided by
#: one item: sixty minutes over four. Written as a literal rather than as that division, so
#: that a test can check the derivation against the two figures it comes from instead of
#: recomputing it and comparing the answer with itself.
QUEUE_ALARM_AT = 15


@dataclass(frozen=True)
class QueueItem:
    """One gated change waiting for a person, as one reader may see it.

    The same row as `MemoryItem` minus the control, and the absence is the design. A gated
    change has not been applied, so there is nothing to delete; and a control on this row
    would be a person deciding a scope widening by pressing a button that says something
    else. See `THE_QUEUE_LISTS_AND_CANNOT_DECIDE`.
    """

    memory_id: str
    change: Change
    #: Always `Tier.GATED` on a queued item. Carried rather than assumed, so a renderer
    #: showing several surfaces does not have to know which list it was handed.
    tier: Tier
    subject: str
    evidence: tuple[Signal, ...]
    confidence: float
    scope: Scope
    learned_at: datetime


@dataclass(frozen=True)
class QueueAlarm:
    """Whether the queue has grown past one sitting, and a sentence saying so.

    No number of any kind, and that is deliberate twice over: the length of a filtered queue
    beside an alarm computed on the true one is a subtraction, and a sentence with a figure
    in it is the first thing that gets forwarded out of context.
    """

    raised: bool
    reason: str


@dataclass(frozen=True)
class ReviewQueue:
    """The gated changes one reader may see, oldest first, and the alarm on them."""

    reader_id: str
    items: tuple[QueueItem, ...]
    alarm: QueueAlarm


@dataclass(frozen=True)
class AgentMemoryView:
    """What one agent learnt, as far as this caller's own reach admits.

    Carries who is reading and which agent, and no statement of any kind about what was left
    out: the difference between this list and the agent's own is the set of memories formed
    from other people's conversations, and its size is not the reader's to know.
    """

    reader_id: str
    agent_id: str
    items: tuple[MemoryItem, ...]


@dataclass(frozen=True)
class DepartmentMemoryView:
    """What the system learnt about one department, for somebody who reaches it."""

    reader_id: str
    department: str
    items: tuple[MemoryItem, ...]


def _queue_item(item: MemoryItem) -> QueueItem:
    """The same row with the control taken off, for the queue.

    Built from `MemoryItem` rather than assembled separately, so the two rows cannot drift in
    what they say about a learning; what differs between them is only the control, which is
    the difference the queue exists to make.
    """
    return QueueItem(
        memory_id=item.memory_id,
        change=item.change,
        tier=item.tier,
        subject=item.subject,
        evidence=item.evidence,
        confidence=item.confidence,
        scope=item.scope,
        learned_at=item.learned_at,
    )


def _visible(
    learnings: Sequence[Learning],
    reader: EntitlementSet,
    *,
    now: datetime,
    where: dict[str, object] | None = None,
) -> list[MemoryItem]:
    """Every learning this reader may be shown, as rows. Says nothing about the rest.

    The one place any of the three views decides reach, so that a view added later cannot
    forget to. `may_recall` is what actually decides; this loop only carries the answer.
    """
    rows: list[MemoryItem] = []
    for learning in learnings:
        seen = may_recall(
            learning.formation,
            reader,
            now=now,
            where=where,
            formed_confidence=learning.formed_confidence,
        )
        if seen is not None:
            rows.append(memory_item(learning, seen))
    return rows


def _most_confident_first(rows: Sequence[MemoryItem]) -> tuple[MemoryItem, ...]:
    """Rows in the order a person browsing wants: what the system is surest of, first.

    Ties break on the time and then the id, so a page that is reloaded looks the same. A
    listing whose order moves between two readings is one nobody can work through, which is
    the same reason `correction.newest_first` fixes its ties.
    """
    return tuple(sorted(rows, key=lambda one: (-one.confidence, one.learned_at, one.memory_id)))


def agent_memory(
    *,
    now: datetime,
    caller: EntitlementSet,
    agent_ceiling: EntitlementSet,
    agent_id: str,
    learnings: Sequence[Learning],
) -> AgentMemoryView:
    """What one agent learnt, listed at the caller's own reach (M16.5.2).

    The reach is `E_run(caller, agent) = E(caller) intersect agent_ceiling`, computed here by
    calling `EntitlementSet.intersect`. An agent is a lens and never a principal, so a tab
    showing what the agent knows rather than what this caller may be told would be the one
    place in the system where the lens stopped applying.

    Filtered to this agent's own learnings. A learning formed with no agent running belongs
    to no tab, which is an absence rather than a refusal: it is not hidden from anybody, it
    is simply not part of what this agent learnt.

    Returns the rows and nothing else. No total, no "and more", and no signal anywhere that
    anything was left out, because the difference between what a caller sees here and what
    exists is the set of memories formed from other people's conversations.
    """
    run = caller.intersect(agent_ceiling)
    mine = [one for one in learnings if one.agent_id == agent_id]
    return AgentMemoryView(
        reader_id=caller.principal_id,
        agent_id=agent_id,
        items=_most_confident_first(_visible(mine, run, now=now)),
    )


def department_memory(
    *,
    now: datetime,
    caller: EntitlementSet,
    department: str,
    learnings: Sequence[Learning],
) -> DepartmentMemoryView:
    """What the system learnt about one department (M16.5.3).

    About the department, not from the people in it. The filter is the change kind: only
    `DEPARTMENT_CHANGES`, which is `tiers.CHANGES_WHAT_ANYBODY_MAY_SEE`, reaches this view.
    Everything a member's conversations produced about how they like an answer shaped is
    left out, including when it was formed inside this department, and
    `A_DEPARTMENT_VIEW_IS_NOT_A_WIDER_LENS_ON_ITS_MEMBERS` is why.

    The department is then a place rather than a filter on the writer: `may_recall` is asked
    whether the caller reaches each memory *in this department*, which is `Scope.matches`
    against `{"department": name}` and is the same predicate `audit.view` evaluates against
    a ledger row. Asking whose conversation formed it would be the other view, the one this
    one refuses to be.

    No count, in this view as in the others: a department head told "twelve of forty" has
    been told there are twenty-eight learnings about their own department they may not read.
    """
    if not department:
        msg = "a department view needs a department; an unnamed one is every department"
        raise ValueError(msg)
    about_the_department = [one for one in learnings if one.proposal.change in DEPARTMENT_CHANGES]
    where: dict[str, object] = {DEPARTMENT_FIELD: department}
    return DepartmentMemoryView(
        reader_id=caller.principal_id,
        department=department,
        items=_most_confident_first(_visible(about_the_department, caller, now=now, where=where)),
    )


def queue_alarm(items: Sequence[QueueItem], *, alarm_at: int = QUEUE_ALARM_AT) -> QueueAlarm:
    """Whether this queue has grown past what a person works through in one sitting.

    Takes the rows a reader may see, never the true queue. An alarm raised on somebody else's
    rows is a statement about how many of them there are, which is the count this surface
    exists without. See `THE_ALARM_IS_RAISED_ON_WHAT_THE_READER_CAN_SEE`.

    Strictly greater, so a queue that is exactly one sitting long is a queue somebody can
    still clear this afternoon and is not worth waking anybody about.

    The sentence carries no figure. A number in an alarm is the part that survives being
    forwarded, and a queue length forwarded out of this context is a count of pending access
    decisions with nothing saying whose reach it was measured at.
    """
    if len(items) > alarm_at:
        return QueueAlarm(
            raised=True,
            reason=(
                "more gated changes are waiting than a person works through in one sitting, "
                "so the queue is not being worked through and access decisions are not being "
                "made rather than being made slowly"
            ),
        )
    return QueueAlarm(
        raised=False,
        reason="the gated changes waiting are within one sitting of review",
    )


def review_queue(
    *,
    now: datetime,
    caller: EntitlementSet,
    learnings: Sequence[Learning],
    alarm_at: int = QUEUE_ALARM_AT,
) -> ReviewQueue:
    """The tier-three changes waiting for a person, and the alarm on them (M16.5.4).

    Gated only. A tier-one or tier-two learning has already taken effect or is waiting on
    agreement rather than on a person, and putting either in this queue would bury the
    decisions that need somebody under the ones that do not.

    Oldest first, which is the opposite of the digest and for the opposite reason: a queue is
    worked from the top and abandoned partway down, so newest-first starves the item that has
    been waiting longest, which is the one whose delay is already the problem.

    The alarm is computed on the rows that survive the entitlement filter, never on the input.

    Lists and decides nothing. There is no approval anywhere in this module and a `QueueItem`
    has no control on it. See `THE_QUEUE_LISTS_AND_CANNOT_DECIDE`.
    """
    gated = [one for one in learnings if one.proposal.tier is Tier.GATED]
    rows = _visible(gated, caller, now=now)
    items = tuple(
        _queue_item(one) for one in sorted(rows, key=lambda one: (one.learned_at, one.memory_id))
    )
    return ReviewQueue(
        reader_id=caller.principal_id,
        items=items,
        alarm=queue_alarm(items, alarm_at=alarm_at),
    )


def delete(
    learning: Learning,
    *,
    at: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> Undo:
    """The delete control on a memory tab (M16.5.2). It writes a mark.

    Literally `digest.undo`, renamed for the surface that calls it, because two
    implementations of a mark is two things that can disagree about what a delete means. The
    person sees delete; the system writes a supersession restoring what this learning
    replaced, or a demotion if it replaced nothing; the memory stays on the record and stops
    being recalled. See `DELETE_IS_THE_SAME_MARK_THE_DIGEST_UNDO_WRITES`.

    Idempotent for the same reason and by the same check: pressing it twice, or pressing it
    after something else has superseded the same memory, does nothing and says so.
    """
    return undo(learning, at=at, supersessions=supersessions, demotions=demotions)


def review_gaps() -> tuple[str, ...]:
    """Everything about this module that would show a reader something it must not.

    Four checks. The first is the one worth having: it walks this module's own public names
    for anything that could approve a gated change, because the pressure to add one arrives
    the first time somebody sits in front of the queue and cannot act on it.
    """
    gaps: list[str] = []

    deciding = ("approve", "apply", "grant", "widen", "allow", "permit")
    for name, value in sorted(globals().items()):
        if name.startswith("_") or not callable(value):
            continue
        if any(word in name.lower() for word in deciding):
            gaps.append(
                f"{name} could be read as deciding a gated change, and this module lists "
                "rather than decides: approval is a surface that does not exist"
            )

    if not DEPARTMENT_CHANGES <= CHANGES_WHAT_ANYBODY_MAY_SEE:
        for extra in sorted(one.value for one in DEPARTMENT_CHANGES - CHANGES_WHAT_ANYBODY_MAY_SEE):
            gaps.append(
                f"{extra} is in the department view and does not change who may see what, so "
                "the view has widened into what the system learnt from individuals"
            )

    if QUEUE_ALARM_AT * REVIEW_MINUTES_PER_ITEM > REVIEW_SITTING_MINUTES or (
        (QUEUE_ALARM_AT + 1) * REVIEW_MINUTES_PER_ITEM <= REVIEW_SITTING_MINUTES
    ):
        gaps.append(
            "the alarm no longer fires at one sitting of review: it is set above or below "
            "the number of items that fit in the time a person gives the queue, so it says "
            "nothing about whether the queue is being worked through"
        )

    for model in (QueueItem, QueueAlarm, ReviewQueue, AgentMemoryView, DepartmentMemoryView):
        for one in fields(model):
            if one.name in COUNTING_FIELD_NAMES:
                gaps.append(
                    f"{model.__name__} carries {one.name}, which beside a filtered listing "
                    "is the number of things the reader may not see"
                )

    return tuple(gaps)
