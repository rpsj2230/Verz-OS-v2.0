"""Where an item's review date is read from, and who is asked when it arrives.

`brain.knowledge.item.due_for_reverification` decides which items are due and
`brain.knowledge.verification.open_reverification_tasks` which of them a run opens tasks for.
Both take items somebody else holds and store nothing. This is the somebody: it reads the due
items out of `know.item`, reads what was already asked out of the outbox, asks whether each
owner can still reach what they would be asked about, and records the nag.

**The owner is asked only if the owner can still reach the item when the nag is recorded.**
`owner_id` never moves and a department does, so the steward named on an item can be somebody
who has since left its department, lost their read of the knowledge plane or left the company.
A nag names a document, and naming one to a person the gate would refuse it to undoes the
refusal. So the owner's reach is resolved from their grants as they stand, through
`gate.resolve_entitlements` and `brain.knowledge.search.reach_for`, and judged by
`Reach.admits`, the Python half of the predicate `know.chunk`'s policy enforces. Nothing here
compares a department by hand and nothing here intersects a scope. See
`A_NAG_GOES_ONLY_TO_AN_OWNER_WHO_CAN_STILL_REACH_THE_ITEM`.

**An owner who cannot is told nothing, and the item goes where it lives.** A published
department item goes to its department and a published company item to the company, and neither
route names the owner. A draft or a personal item goes nowhere, because nobody but its owner may
learn it exists: it is held, left out of the log, and due again on the next run. See
`A_NAG_THE_OWNER_CANNOT_RECEIVE_GOES_WHERE_THE_ITEM_LIVES` and
`WHAT_ONLY_THE_OWNER_MAY_REACH_IS_HELD_RATHER_THAN_ROUTED`.

**DENIED and ABSENT stay one answer.** An owner who was never a principal, one who was disabled,
one with no read of the plane and one whose grant moved to another department all come back as
no reach and take the same route, and nothing records which it was. The run's summary is three
booleans and no count.

**The log is the outbox.** A nag is an outbox event whose id is derived from the item and the
review date it fell due on, so the row that records the nag and the row that stops it being
recorded twice are one row, and its primary key refuses a second. Rejected: a table of opened
reviews beside it. It would be a second record of one event, and the two could disagree in the
one direction that matters, a log row committed with no nag, which is an item nobody is ever
asked about again. See `THE_LOG_IS_THE_NAGS_ALREADY_RECORDED`.

**The event carries no title, and that is the outbox's rule rather than a choice made here.**
`brain.ops.outbox.AN_EVENT_CARRIES_IDS_AND_NEVER_CONTENT`. Its kind is `APPROVAL_REQUESTED` on
the entity `knowledge_item`, because a re-verification is an owner being asked to vouch for a
document again, which is what that kind says. Rejected: a kind of its own, which would widen a
closed enum and two check constraints to state a fact the existing kind already states.

**Nothing sends a nag yet.** See `NOTHING_SENDS_A_NAG_YET`, which the run's summary carries so
that nobody reading a successful control run takes it for an owner having been told.

Rejected: reading items through the model as the application role. `know.item`'s policy is the
corpus's reach and the sweep has no principal, so it would see company items only and record a
successful run over none of the rest. `know.items_for_review` is the one read past the policy,
and `0040` argues it.

Task ids: M34.2.1.3
"""

from __future__ import annotations

import asyncio
import enum
import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Final, assert_never

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.core.entitlement import EntitlementSet
from brain.knowledge.item import (
    RETRIEVABLE_STATES,
    KnowledgeError,
    KnowledgeItem,
    KnowledgeState,
    ReverificationTask,
)
from brain.knowledge.search import Reach, SearchError, reach_for
from brain.knowledge.verification import (
    DEFAULT_LEAD_TIME,
    ReverificationLog,
    ReviewKey,
    key_for,
    open_reverification_tasks,
)
from brain.knowledge.visibility import Visibility
from brain.ops.outbox import EventKind, OutboxEvent
from brain.ops.outbox_store import record_event, subscribers
from brain.session import make_app_engine, make_session_factory
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.outbox import OutboxEventRow

# ------------------------------------------------------------------ written-down reasons
#: Why the owner's reach is asked before the owner is asked anything.
A_NAG_GOES_ONLY_TO_AN_OWNER_WHO_CAN_STILL_REACH_THE_ITEM: Final = (
    "An item's owner never moves and its department does, so the steward on file can be "
    "somebody who has left the department, lost their read of the knowledge plane or left the "
    "company. A nag names a document, and naming one to a person the gate would refuse it to "
    "undoes the refusal. So the owner's reach is resolved from their grants when the nag is "
    "recorded and judged by the predicate the corpus's own policy enforces, and an owner it "
    "does not admit is not asked."
)

#: Where the nag goes instead.
A_NAG_THE_OWNER_CANNOT_RECEIVE_GOES_WHERE_THE_ITEM_LIVES: Final = (
    "A published department item whose owner cannot reach it goes to its department, and a "
    "published company item to the company, and neither route names the owner. Somebody still "
    "has to look again, and the people an item already reaches are the only ones who can be "
    "asked about it without being told something new. Who administers that department is not "
    "resolved here, because a department admin's scope lives in the reviewed rule that maps "
    "the directory group and not on a row."
)

#: What goes nowhere, and why that is not a lost task.
WHAT_ONLY_THE_OWNER_MAY_REACH_IS_HELD_RATHER_THAN_ROUTED: Final = (
    "A draft is its owner's alone whatever its visibility says, and a personal item is reached "
    "by nobody else, so routing either anywhere tells a second person it exists. It is held "
    "instead: nothing is recorded, it stays due, and it is asked about on the first run at "
    "which its owner can reach it again. The run says that something was held as a boolean, "
    "and never which or how many."
)

#: Why there is no table of opened reviews.
THE_LOG_IS_THE_NAGS_ALREADY_RECORDED: Final = (
    "A nag is an outbox event whose id is derived from the item and the review date it fell "
    "due on, so recording the nag and recording that it was sent are one insert and the "
    "primary key refuses a second. A separate log would be a second record of one event, and "
    "a log row committed without its nag is an item nobody is asked about again, with every "
    "run after it reporting that there was nothing to do."
)

#: Why a grant `reach_for` refuses is read as no reach rather than as a failed run.
A_GRANT_THE_DOCUMENT_PLANE_CANNOT_READ_REACHES_NOTHING_HERE: Final = (
    "brain.knowledge.search.reach_for refuses a knowledge grant whose scope is not a "
    "department membership, because a list of department names cannot represent it without "
    "loss. The sweep reads that refusal as no reach at all. It is the safe direction, since the "
    "owner is then not asked and the item goes where it lives, and one oddly written grant "
    "must not stop every other owner being asked."
)

#: What does not happen yet, carried in every run's summary.
NOTHING_SENDS_A_NAG_YET: Final = (
    "Nothing sends a nag yet. Each is recorded as an outbox event, with a delivery for every "
    "subscriber that takes approval requests, and nothing drains the outbox: outbox_dispatch has "
    "no caller and no sender is implemented. No channel composes the sentence an owner would "
    "read, so no owner has been told anything by this, and whatever sends one has to ask the "
    "owner's reach again when it does."
)

#: Why a personal item's owner and its row's owner must be one person.
A_PERSONAL_ITEM_HAS_ONE_OWNER_AND_ONE_COLUMN_SAYS_WHO: Final = (
    "The row has one owner column and the policy reads it both as the steward and as the only "
    "person a personal item reaches. A personal item whose visibility names somebody other than "
    "its steward would be stored reachable by the steward and not by the person it was written "
    "for, so it is refused before it is written rather than stored as a different item."
)

# ------------------------------------------------------------------ the shapes
#: The entity every nag names, in the grammar `brain.core.envelope.OBJECT_NAME_PATTERN` admits.
NAG_ENTITY: Final = "knowledge_item"

#: The kind every nag is recorded as. See the module docstring for why it is not a new one.
NAG_KIND: Final = EventKind.APPROVAL_REQUESTED

#: What a nag's event id begins with, so a subscriber can tell one from another approval request.
NAG_ID_PREFIX: Final = "reverification."

#: How much of the digest names a nag. Forty hex characters is 160 bits, which no two review
#: keys share by accident, and with the prefix it is well inside the outbox's identifier limit
#: for an item id of any length the grammar admits.
NAG_DIGEST_CHARS: Final = 40

#: The attribute a nag's review date travels under, and is read back from for the log.
REVIEW_BY_ATTRIBUTE: Final = "review_by"

#: The attribute naming how a nag was routed, and the two naming who it is addressed to.
ROUTE_ATTRIBUTE: Final = "route"
RECIPIENT_ATTRIBUTE: Final = "recipient"
DEPARTMENT_ATTRIBUTE: Final = "department"

#: How the store reads the items whose date has arrived. See `0040` for why it is a function.
ITEMS_FOR_REVIEW_SQL: Final = (
    "SELECT item_id, owner_id, title, state, visibility, department, review_by "
    "FROM know.items_for_review(:by)"
)

#: How the store reads an owner's grants as they stand. `0003`'s resolver, granted to the app.
RESOLVE_SQL: Final = "SELECT gate.resolve_entitlements(:principal_id, :now)"


class Route(enum.StrEnum):
    """Where one due item's nag goes."""

    #: To the owner, who can still reach the item.
    OWNER = "owner"
    #: To the department a published department item lives in, naming no owner.
    DEPARTMENT = "department"
    #: To the company, for a published company item, naming no owner.
    COMPANY = "company"
    #: Nowhere this run. See `WHAT_ONLY_THE_OWNER_MAY_REACH_IS_HELD_RATHER_THAN_ROUTED`.
    HELD = "held"


@dataclass(frozen=True)
class ItemUnderReview:
    """One due item as `know.items_for_review` returns it: stewardship without the text.

    Satisfies `brain.knowledge.item.UnderReview`, so the sweep's decision is the one that module
    and `brain.knowledge.verification` already make, over rows rather than models.
    """

    item_id: str
    owner_id: str
    title: str
    state: KnowledgeState
    visibility: Visibility
    department: str
    review_by: datetime | None

    @property
    def is_retrievable(self) -> bool:
        return self.state in RETRIEVABLE_STATES

    def reach_row(self) -> dict[str, object]:
        """The item in the shape `Reach.admits` evaluates, which is a `know.chunk` row's."""
        return {
            "deleted_at": None,
            "state": self.state.value,
            "owner_id": self.owner_id,
            "visibility": self.visibility.value,
            "department": self.department or None,
        }


@dataclass(frozen=True)
class NagRun:
    """What one run did, as three booleans. See the module docstring on counts."""

    recorded: bool = False
    held: bool = False
    more_waiting: bool = False

    def summary(self, now: datetime) -> str:
        """The run's sentence for `ops.control_run.detail`. No title, no owner and no number."""
        return (
            f"knowledge re-verification at {now.isoformat()}: "
            f"a nag was recorded: {_said(self.recorded)}; "
            f"an item only its owner may reach was held: {_said(self.held)}; "
            f"more were due than one run asks about: {_said(self.more_waiting)}. "
            f"{NOTHING_SENDS_A_NAG_YET}"
        )


def _said(flag: bool) -> str:
    return "yes" if flag else "no"


# ------------------------------------------------------------------ decisions, no connection
def row_values(item: KnowledgeItem) -> dict[str, object]:
    """The columns an item is stored as, refusing the one item one owner column cannot hold.

    See `A_PERSONAL_ITEM_HAS_ONE_OWNER_AND_ONE_COLUMN_SAYS_WHO`.
    """
    if item.visibility.level is Visibility.PERSONAL and item.visibility.owner_id != item.owner_id:
        msg = (
            f"{item.item_id!r} is personal to {item.visibility.owner_id!r} and stewarded by "
            f"{item.owner_id!r}. {A_PERSONAL_ITEM_HAS_ONE_OWNER_AND_ONE_COLUMN_SAYS_WHO}"
        )
        raise KnowledgeError(msg)
    return {
        "item_id": item.item_id,
        "title": item.title,
        "owner_id": item.owner_id,
        "visibility": item.visibility.level.value,
        "department": item.visibility.department or None,
        "state": item.state.value,
        "verified_by": item.verified_by or None,
        "verified_at": item.verified_at,
        "review_by": item.review_by,
        "supersedes": item.supersedes or None,
    }


def reach_from(
    entitlement: EntitlementSet, *, departments: Sequence[str], now: datetime
) -> Reach | None:
    """The owner's reach over the document plane, or None when they reach none of it.

    `reach_for`, with its refusal read as no reach. See
    `A_GRANT_THE_DOCUMENT_PLANE_CANNOT_READ_REACHES_NOTHING_HERE`.
    """
    try:
        return reach_for(entitlement, departments=departments, now=now)
    except SearchError:
        return None


def route_for(item: ItemUnderReview, owner_reach: Reach | None) -> Route:
    """Where this item's nag goes, given what its owner reaches now.

    See `A_NAG_GOES_ONLY_TO_AN_OWNER_WHO_CAN_STILL_REACH_THE_ITEM`,
    `A_NAG_THE_OWNER_CANNOT_RECEIVE_GOES_WHERE_THE_ITEM_LIVES` and
    `WHAT_ONLY_THE_OWNER_MAY_REACH_IS_HELD_RATHER_THAN_ROUTED`.

    A reach belonging to somebody else is refused rather than judged. It would route one
    person's item to its owner on the strength of another person's grants, and the caller that
    did it has the wrong variable in scope.
    """
    if owner_reach is not None and owner_reach.principal_id != item.owner_id:
        msg = (
            f"a reach for {owner_reach.principal_id!r} was offered to route an item stewarded "
            f"by {item.owner_id!r}; whether an owner may be asked is their own reach's question"
        )
        raise KnowledgeError(msg)
    if owner_reach is not None and owner_reach.admits(item.reach_row()):
        return Route.OWNER
    if item.state is not KnowledgeState.PUBLISHED:
        return Route.HELD
    match item.visibility:
        case Visibility.DEPARTMENT:
            return Route.DEPARTMENT
        case Visibility.COMPANY:
            return Route.COMPANY
        case Visibility.PERSONAL:
            return Route.HELD
    assert_never(item.visibility)


def nag_instant(moment: datetime) -> str:
    """A review date as the log spells it: UTC, so two offsets for one instant are one key."""
    return moment.astimezone(UTC).isoformat()


def nag_event_id(key: ReviewKey) -> str:
    """The event id a nag for this item and review date is recorded under, derived and never drawn.

    See `THE_LOG_IS_THE_NAGS_ALREADY_RECORDED`.
    """
    item_id, review_by = key
    digest = hashlib.sha256(f"{item_id}\n{nag_instant(review_by)}".encode()).hexdigest()
    return NAG_ID_PREFIX + digest[:NAG_DIGEST_CHARS]


def nag_event(
    task: ReverificationTask, route: Route, *, department: str, now: datetime
) -> OutboxEvent:
    """The outbox event recording one nag. Identifiers only, and the owner only when asked.

    A held route has no event, and asking for one is refused: an event for it would be the
    second person told the item exists.
    """
    attributes: dict[str, str | int] = {
        ROUTE_ATTRIBUTE: route.value,
        REVIEW_BY_ATTRIBUTE: nag_instant(task.review_by),
    }
    match route:
        case Route.OWNER:
            attributes[RECIPIENT_ATTRIBUTE] = task.owner_id
        case Route.DEPARTMENT:
            attributes[DEPARTMENT_ATTRIBUTE] = department
        case Route.COMPANY:
            pass
        case Route.HELD:
            msg = f"{WHAT_ONLY_THE_OWNER_MAY_REACH_IS_HELD_RATHER_THAN_ROUTED}"
            raise KnowledgeError(msg)
    return OutboxEvent(
        event_id=nag_event_id(key_for(task)),
        kind=NAG_KIND,
        entity=NAG_ENTITY,
        record_id=task.item_id,
        occurred_at=now,
        attributes=MappingProxyType(attributes),
    )


# ------------------------------------------------------------------ the store
async def put_item(session: AsyncSession, item: KnowledgeItem) -> None:
    """Write an item, or replace what is on file for its id. Does not commit.

    Nothing in this repository calls it outside the tests yet: ingestion writes no chunk and no
    item, and verifying a document records nothing. It is here so the row has one writer when
    one is built, and so the sweep's tests write rows through the same checks a writer would.
    """
    values = row_values(item)
    statement = insert(KnowledgeItemRow).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[KnowledgeItemRow.item_id],
            set_={
                **{name: statement.excluded[name] for name in values if name != "item_id"},
                "updated_at": func.now(),
            },
        )
    )


async def items_for_review(session: AsyncSession, *, by: datetime) -> tuple[ItemUnderReview, ...]:
    """Retrievable items whose review date is at or before `by`, oldest date first."""
    rows = await session.execute(text(ITEMS_FOR_REVIEW_SQL), {"by": by})
    return tuple(
        ItemUnderReview(
            item_id=row.item_id,
            owner_id=row.owner_id,
            title=row.title,
            state=KnowledgeState(row.state),
            visibility=Visibility(row.visibility),
            department=row.department or "",
            review_by=row.review_by,
        )
        for row in rows
    )


async def opened_reviews(session: AsyncSession, item_ids: Iterable[str]) -> ReverificationLog:
    """The nags already recorded for these items, as the log `open_reverification_tasks` takes."""
    rows = await session.execute(
        select(OutboxEventRow.record_id, OutboxEventRow.attributes, OutboxEventRow.occurred_at)
        .where(OutboxEventRow.kind == NAG_KIND.value)
        .where(OutboxEventRow.entity == NAG_ENTITY)
        .where(OutboxEventRow.record_id.in_(sorted(set(item_ids))))
    )
    opened = {
        (row.record_id, datetime.fromisoformat(str(row.attributes[REVIEW_BY_ATTRIBUTE]))): (
            row.occurred_at
        )
        for row in rows
    }
    return ReverificationLog(opened=MappingProxyType(opened))


async def owner_reach(
    session: AsyncSession, owner_id: str, *, department: str, now: datetime
) -> Reach | None:
    """What this owner reaches of one item's place now, from their grants as they stand.

    **The registry `reach_for` is handed is the item's own department and nothing else.** The
    question is whether this grant admits this one department, and `reach_for` answers it for
    exactly the names it is given. Rejected: every live row of `gate.department`, which
    `brain.knowledge.document_tools` reads because it builds a query over all of them. Here it
    would add a read that answers nothing, and a department missing from the registry, retired
    or never recorded, would make every owner in it unreachable and send every nag there to a
    department. A company or personal item has no department, so none is passed.
    """
    resolved = await session.execute(text(RESOLVE_SQL), {"principal_id": owner_id, "now": now})
    entitlement = EntitlementSet.model_validate(resolved.scalar_one())
    places = (department,) if department else ()
    return reach_from(entitlement, departments=places, now=now)


async def run_reverification(
    session: AsyncSession, *, now: datetime, lead_time: timedelta = DEFAULT_LEAD_TIME
) -> NagRun:
    """One pass: read what is due, open what the log has not, route each, record the routed.

    Does not commit. The events and their deliveries are written in the caller's transaction,
    which is the one the schedule's lock lives in.
    """
    items = await items_for_review(session, by=now + lead_time)
    log = await opened_reviews(session, (one.item_id for one in items))
    run = open_reverification_tasks(items, now=now, log=log, lead_time=lead_time)
    by_id = {one.item_id: one for one in items}
    takers = await subscribers(session)
    recorded = False
    held = False
    for task in run.tasks:
        item = by_id[task.item_id]
        reach = await owner_reach(session, task.owner_id, department=item.department, now=now)
        route = route_for(item, reach)
        if route is Route.HELD:
            held = True
            continue
        event = nag_event(task, route, department=item.department, now=now)
        await record_event(session, event, takers)
        recorded = True
    return NagRun(recorded=recorded, held=held, more_waiting=run.more_waiting)


def run_reverification_now(
    database_url: str,
    *,
    now: datetime,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> NagRun:
    """`run_reverification`, from a thread with no event loop of its own, committed.

    The shape `brain.ops.spend_store.refresh_spend_daily_now` takes and for its reasons: the
    worker's schedule runs a control off its event loop, the engine is the application's, and
    which loop psycopg accepts is decided in `brain.ops.worker`.
    """

    async def once() -> NagRun:
        engine = make_app_engine(database_url)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                return await run_reverification(session, now=now)
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory)
