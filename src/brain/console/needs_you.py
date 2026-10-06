"""The landing screen's two strips: is the install healthy, and what is waiting on this reader.

`docs/admin-console-architecture.md` Part 2.3 A1 draws the Dashboard as a health strip
(readiness, halts in force, budget stops, the worker) and "Needs you", one line per queue the
reader can open with the number of items in it. `brain.console.operate` already holds the rule
for a landing figure, **honest counting**: a figure only to a reader who could open the screen
that counts it, counted over the rows that screen would show them, and never a second figure
for one screen. This module is that rule applied to the queues, which are Govern screens and
so have no `Panel` in `brain.console.operate.PANELS` for `tile` to take.

**A queue's figure is the length of the list its own screen would show this reader, and
nothing else.** Each route narrows with the function its queue's screen already uses
(`brain.console.role_surfaces.pending_for`, `brain.govern_people_routes.reviewable`,
`brain.console.elevation.may_decide`, `brain.console.govern_estate.skill_queue`,
`brain.knowledge.lifecycle.Authority.may_act`) and hands the narrowed rows' count here. There is
no parameter carrying a total, which is
`brain.console.operate.A_TOTAL_THAT_ARRIVES_AS_AN_ARGUMENT_WAS_COUNTED_SOMEWHERE_ELSE`.

**A queue the reader may not act on is absent, not nought.** A line reading "Access review 0"
to somebody who may not open access review says the queue exists and is theirs to watch; the
menu already declines to say either. `needs_you` drops a `None` and keeps no record that it
did. See `A_QUEUE_THE_READER_MAY_NOT_OPEN_IS_ABSENT_AND_NEVER_NOUGHT`.

**One figure per queue.** Two lines for one queue are a subtraction whatever their labels,
which is `brain.console.operate.A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION`, and
`needs_you` refuses the pair rather than rendering both.

**Three queues the design names have nothing to count, and each says so in words.** A
tier-three learning change is routed and never decided, so nothing waits on anybody; a widened
publish waiting for a second approver has domain code in `brain.builder.publish` and no store;
and a sign-in refused for having no binding is logged without its subject, so nothing lists
one. The health strip's budget stops are the same: `brain.ops.budget_stop` decides one and
nothing stores one. Each is served as `Unrecorded` with its sentence, never as a queue of nought
or a strip reading "no stops", which is the reassuring answer nobody measured.

**Halts are read from `ops.halt` (0136), the latest act per scope and target, and shown through
`brain.console.operate.stopped_for`.** A halt on everything is shown to everybody it stops and a
narrower one only through the halt screen's own grant, which is that function's rule and not a
second one here. A row that does not construct, like a store that cannot be read, makes the state
unknown rather than empty, for
`brain.ops.halt.IF_WE_CANNOT_TELL_WHETHER_WE_ARE_HALTED_WE_ARE_HALTED`: a strip reading "nothing
stopped" while admission refuses everything is the worst sentence it could print. The reason and
who declared it are not carried: `brain.ops.halt.Halt.reason` is never shown to somebody the halt
refuses, and the landing screen is read by exactly those people.

Scope: domain logic. Nothing here opens a connection or reads a clock.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.console.entity_stats import Unrecorded
from brain.console.operate import A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION

# ------------------------------------------------------------------ written-down reasons
#: Why a queue the reader may not act on is left out rather than shown empty.
A_QUEUE_THE_READER_MAY_NOT_OPEN_IS_ABSENT_AND_NEVER_NOUGHT: Final = (
    "A queue line reading nought to somebody who may not open the queue tells them the queue "
    "exists and that its contents are being kept from them, which is a count in words. So a "
    "queue the reader may not act on is absent from Needs you, exactly as its screen is absent "
    "from their menu, and a queue they may act on shows the length of the list its own screen "
    "would show them."
)


class NeedsYouError(Exception):
    """A queue figure that would say more than the queue's own screen does."""


class Queue(enum.StrEnum):
    """The queues Needs you names, in the order the design lists them."""

    APPROVALS = "approvals"
    ACCESS_REVIEW = "access_review"
    ELEVATION = "elevation"
    SKILL_REVIEWS = "skill_reviews"
    TIER_THREE_LEARNING = "tier_three_learning"
    PUBLISH_APPROVALS = "publish_approvals"
    UNBOUND_SIGN_INS = "unbound_sign_ins"
    KNOWLEDGE_PAST_REVIEW = "knowledge_past_review"


#: The console page each queue opens, so the line is a link to the list it counted.
OPENS: Final = MappingProxyType(
    {
        Queue.APPROVALS: "/approvals",
        Queue.ACCESS_REVIEW: "/access_review",
        Queue.ELEVATION: "/elevation",
        Queue.SKILL_REVIEWS: "/skills",
        Queue.TIER_THREE_LEARNING: "/learning",
        Queue.PUBLISH_APPROVALS: "/agents",
        Queue.UNBOUND_SIGN_INS: "/sign-in-links",
        Queue.KNOWLEDGE_PAST_REVIEW: "/library",
    }
)

#: The queues nothing on an install can count yet, and why. Product sentences, no values.
UNCOUNTED_QUEUES: Final[tuple[Unrecorded, ...]] = (
    Unrecorded(
        figure=Queue.TIER_THREE_LEARNING.value,
        why=(
            "a tier-three learning change is routed to the people it names and nothing records a "
            "decision on one, so nothing waits on anybody to count"
        ),
    ),
    Unrecorded(
        figure=Queue.PUBLISH_APPROVALS.value,
        why=(
            "a widened publish needs a second approver and nothing stores a publish waiting for "
            "one yet, so there is no queue to count"
        ),
    ),
    Unrecorded(
        figure=Queue.UNBOUND_SIGN_INS.value,
        why=(
            "a sign-in refused because the account is bound to nobody is logged without who it "
            "was, deliberately, so nothing lists the people waiting to be bound"
        ),
    ),
)

#: The health strip's figures nothing on an install records yet, and why.
UNRECORDED_HEALTH: Final[tuple[Unrecorded, ...]] = (
    Unrecorded(
        figure="budget_stops",
        why=(
            "nothing records a budget stop in force yet: ceilings are stored and nothing writes "
            "the stop reached on the way to one, so there is no stop to count"
        ),
    ),
)


@dataclass(frozen=True)
class Waiting:
    """One queue and how many items in it this reader may act on.

    `at_least` says the list was read to its bound, so the figure is at least this. There is
    no field for the queue's size beyond the reader's reach, and none can be added without the
    test that reads these field names failing.
    """

    queue: Queue
    waiting: int
    at_least: bool = False

    def __post_init__(self) -> None:
        if self.waiting < 0:
            msg = f"{self.queue.value} reports {self.waiting} items, which is not a count"
            raise NeedsYouError(msg)

    @property
    def opens(self) -> str:
        return OPENS[self.queue]


def waiting(queue: Queue, shown: Iterable[object], *, at_least: bool = False) -> Waiting:
    """A queue's figure: how many of the rows its own screen would show this reader.

    Takes the rows rather than a number, so the count is of what was narrowed and there is no
    argument a precomputed total could arrive through.
    """
    return Waiting(queue=queue, waiting=sum(1 for _ in shown), at_least=at_least)


def needs_you(found: Iterable[Waiting | None]) -> tuple[Waiting, ...]:
    """The queues this reader may act on, in the register's order, one figure each.

    `None` is a queue the reader may not open, and it is dropped without a trace. See
    `A_QUEUE_THE_READER_MAY_NOT_OPEN_IS_ABSENT_AND_NEVER_NOUGHT`. A second figure for one queue
    is refused, for `A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION`.
    """
    kept = [one for one in found if one is not None]
    seen: set[Queue] = set()
    for one in kept:
        if one.queue in seen:
            msg = (
                f"{one.queue.value} lends Needs you two figures. "
                f"{A_SECOND_FIGURE_FOR_ONE_SCREEN_IS_A_SUBTRACTION}"
            )
            raise NeedsYouError(msg)
        seen.add(one.queue)
    order = {queue: index for index, queue in enumerate(Queue)}
    return tuple(sorted(kept, key=lambda one: order[one.queue]))


def worker_last_seen(runs: Iterable[tuple[datetime, datetime | None]]) -> datetime | None:
    """When the worker was last seen doing anything, from the scheduled runs this reader may see.

    The worker's own heartbeat is a file in its container, which the web process cannot read,
    and the queue driver's worker table is refused to the application role. What the database
    does hold is each scheduled run's start and finish, written by the worker and by nothing
    else, so the newest of those is the latest evidence it was alive.
    """
    instants = [moment for started, finished in runs for moment in (started, finished)]
    return max((one for one in instants if one is not None), default=None)
