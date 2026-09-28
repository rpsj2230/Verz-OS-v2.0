"""The console's landing screen over HTTP: a health strip, and what is waiting on this reader.

`docs/admin-console-architecture.md` Part 2.3 A1 names `GET /api/v1/console/overview` as the
route to build: a health strip (readiness, halts in force, budget stops, the worker) and "Needs
you", each queue the reader can open with the number of items they may see in it.
`brain.console.needs_you` holds the rules; this module asks each queue's own screen and store,
in the order its own route asks them, and adds no decision about any of them.

**The screen's read first, and nothing is read for a reader without it.** The Overview screen is
registered at `read:overview`, and `brain.console.reads.permitted` is asked before any store,
so a caller without it is refused identically on an install with a database and on one without.

**Each queue is asked exactly as its own screen asks, and counted over what that screen would
list.** Approvals: the Approvals screen's read, then `brain.approval_routes.shown_card` over the
open suspensions at the reader's reach. Access review: that screen's read, then
`brain.govern_people_routes.reviewable` over the holdings, counting those with no decision yet.
Elevation: whether the reader may authorise at all, then `brain.console.elevation.may_decide` over
the pending requests. Skill reviews: `brain.console.skill_library.may_review`, then
`brain.console.govern_estate.skill_queue`. Knowledge past review: the Library screen's read, then
`brain.knowledge.lifecycle.Authority.may_act` over the live documents whose review date has
passed. A queue the reader may not act on is absent, never nought; see
`brain.console.needs_you.A_QUEUE_THE_READER_MAY_NOT_OPEN_IS_ABSENT_AND_NEVER_NOUGHT`. A queue whose
store was read to its bound says `at_least`, so its figure is at least what is shown; the bound
is the one the queue's own screen reads with, so the two agree about where the list stops.

**A queue the reader may act on and this process cannot read is named, not dropped.** Each gate
is asked before its store, so a store's fault reaches only a reader the queue is for, and the
queue is then served in `uncounted` with `A_QUEUE_THAT_COULD_NOT_BE_READ_IS_NAMED`. Dropping it
would read as nothing waiting, which is the reassuring answer nobody measured.

**The health strip says what is measured and names what is not.** Readiness is `/health/ready`'s
own computation, which is public, so it is shown to every reader of this screen. The worker is
the newest scheduled run this reader may see (`brain.jobs_routes.may_see_job`), because the
heartbeat file is in another container and the queue driver's tables are refused to the
application. Halts and budget stops have no store, and are served as `unrecorded` with the
sentence rather than as "none".

Rejected: routing the queues through `brain.console.operate.tile`. `tile` takes a `Panel`, and
the twelve panels are the Operate and Report screens; the queues are Govern screens, and a
panel invented for each would be a second register of them. The rule `tile` enforces, a figure
counted over the rows its screen would show and no second figure per screen, is
`brain.console.needs_you.needs_you`'s, and the tests hold both halves.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.approval_routes import (
    APPROVALS_ARE_NOT_KEPT_ON_THIS_PROCESS,
    SuspensionStore,
    shown_card,
    suspensions_of,
)
from brain.console.elevation import ELEVATION_CONTROL, ElevationState, may_decide, state_of
from brain.console.entity_stats import Unrecorded
from brain.console.govern_estate import skill_queue
from brain.console.needs_you import (
    UNCOUNTED_QUEUES,
    UNRECORDED_HEALTH,
    Queue,
    Waiting,
    needs_you,
    waiting,
    worker_last_seen,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.sign_in_links import may_see_links
from brain.console.skill_library import may_review
from brain.core.errors import Absent, Failed
from brain.govern_people_routes import (
    ACCESS_REVIEW_SCREEN,
    MAX_ROWS,
    elevation_records_of,
    elevation_request,
    review_store_of,
    reviewable,
)
from brain.jobs_routes import last_run_of_each_control, may_see_job
from brain.knowledge.lifecycle_store import MAX_ITEMS, live_items
from brain.knowledge_lifecycle_routes import authority_of, in_transaction
from brain.ops.skill_store import MAX_LIBRARY
from brain.readiness import ReadinessPart, parts_of
from brain.routing_routes import sessions_of
from brain.skill_routes import library_of, submitted

log = structlog.get_logger()

OVERVIEW_PATH: Final = "/console/overview"

#: The registered screen this route is. Read off the registry, never spelled as a capability.
OVERVIEW_SCREEN: Final = "overview"
APPROVALS_SCREEN: Final = "approvals"
LIBRARY_SCREEN: Final = "library"
LEARNING_SCREEN: Final = "learning"
AGENTS_SCREEN: Final = "agents"


# ------------------------------------------------------------------------------ the views
class UnrecordedFigureView(BaseModel):
    """A figure or queue the landing screen names that nothing on this install records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    figure: str
    why: str


class HealthView(BaseModel):
    """Whether the install can answer, and when the worker was last seen doing anything.

    `status` and `parts` are `/health/ready`'s own. `worker_last_seen` is null when no
    scheduled run this reader may see has ever started, which is also what a reader who may
    see none is answered.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    parts: list[ReadinessPart]
    worker_last_seen: datetime | None
    unrecorded: list[UnrecordedFigureView]


class QueueView(BaseModel):
    """One queue this reader may act on and how many items in it they may act on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    queue: str
    waiting: int
    at_least: bool
    opens: str


class OverviewView(BaseModel):
    """The landing screen for one reader: the health strip and Needs you.

    `needs_you` holds only queues the reader may act on. `uncounted` names the queues the
    design lists that nothing on an install can count yet, for a reader of each one's screen.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    health: HealthView
    needs_you: list[QueueView]
    uncounted: list[UnrecordedFigureView]


def _unrecorded(rows: tuple[Unrecorded, ...] | list[Unrecorded]) -> list[UnrecordedFigureView]:
    return [UnrecordedFigureView(figure=one.figure, why=one.why) for one in rows]


#: Why a queue whose store this process cannot read is named rather than left out.
A_QUEUE_THAT_COULD_NOT_BE_READ_IS_NAMED: Final = (
    "this queue is yours to act on and it could not be read on this process just now, so it is "
    "named rather than counted: leaving it out would read as nothing waiting"
)


def _not_answerable() -> Absent:
    """The one refusal this route makes. It names the screen, never a capability or a queue."""
    return Absent(f"the {OVERVIEW_SCREEN} screen is not answerable for this caller")


# ---------------------------------------------------------------------------- the strips
async def readiness(request: Request) -> tuple[str, list[ReadinessPart]]:
    """`/health/ready`'s status and parts, computed as that route computes them.

    A process whose lifespan did not run has no readings and no checks, and is reported with
    every headline part not configured, which is what `parts_of` says of an empty mapping.
    """
    state = request.app.state
    readings = getattr(state, "readings", None)
    checks_held = getattr(state, "ready", None)
    if readings is not None and checks_held is not None:
        await readings.refresh(checks_held)
    checks: dict[str, bool] = dict(checks_held or {})
    reported: dict[str, bool] = dict(getattr(state, "reported", {}) or {})
    ok = all(checks.values()) if checks else True
    return ("ok" if ok else "degraded"), parts_of(checks, reported)


async def worker_seen(request: Request, asked: Asking) -> datetime | None:
    """The newest start or finish of a scheduled run this reader may see, or None."""
    factory = sessions_of(request)
    if factory is None:
        return None
    async with factory() as session:
        rows = (await session.execute(last_run_of_each_control())).all()
    return worker_last_seen(
        (started, finished)
        for name, started, finished, *_ in (row._tuple() for row in rows)
        if may_see_job(str(name), asked.reach, asked.now)
    )


# ---------------------------------------------------------------------------- the queues
async def approvals_waiting(request: Request, asked: Asking) -> Waiting | Unrecorded | None:
    """The approvals this reader could decide, or None when they may not open the screen."""
    if not permitted(screen(APPROVALS_SCREEN).read, asked.reach, asked.now):
        return None
    found = suspensions_of(request)
    if found is None:
        return Unrecorded(figure=Queue.APPROVALS.value, why=APPROVALS_ARE_NOT_KEPT_ON_THIS_PROCESS)
    source = (
        found.reading_as(asked.reach, asked.now) if isinstance(found, SuspensionStore) else found
    )
    suspensions = await source.open_suspensions()
    return waiting(
        Queue.APPROVALS,
        (one for one in suspensions if shown_card(one, asked.reach, asked.now) is not None),
    )


async def access_review_waiting(request: Request, asked: Asking) -> Waiting | None:
    """Holdings this reviewer may decide that have no decision yet, or None without the screen."""
    if not permitted(screen(ACCESS_REVIEW_SCREEN).read, asked.reach, asked.now):
        return None
    holdings, decided, full = await review_store_of(request).holdings(limit=MAX_ROWS)
    return waiting(
        Queue.ACCESS_REVIEW,
        (
            one
            for one in holdings
            if reviewable(one, asked.reach, asked.now) is not None and one.row.id not in decided
        ),
        at_least=full,
    )


async def elevation_waiting(request: Request, asked: Asking) -> Waiting | None:
    """Pending requests this reader may decide, or None when they may authorise nothing."""
    if asked.reach.scope_for(ELEVATION_CONTROL, asked.now) is None:
        return None
    stored, full = await elevation_records_of(request).requests(limit=MAX_ROWS)
    return waiting(
        Queue.ELEVATION,
        (
            one
            for one in stored
            if state_of(
                decision=one.decision,
                lapses_at=one.lapses_at,
                grant_live=one.grant_live,
                now=asked.now,
            )
            is ElevationState.PENDING
            and may_decide(asked.reach, elevation_request(one), asked.now)
        ),
        at_least=full,
    )


async def skill_reviews_waiting(request: Request, asked: Asking) -> Waiting | None:
    """Skills waiting for a reviewer this reader may review, or None when they may review none."""
    if not may_review(asked.reach, asked.now):
        return None
    library = await library_of(request).library(MAX_LIBRARY)
    narrowed = skill_queue(submitted(library, asked.now), asked.reach, asked.now)
    return waiting(Queue.SKILL_REVIEWS, narrowed.entries, at_least=len(library) >= MAX_LIBRARY)


async def knowledge_past_review_waiting(request: Request, asked: Asking) -> Waiting | None:
    """Live documents past their review date that this reader may act on, or None."""
    if not permitted(screen(LIBRARY_SCREEN).read, asked.reach, asked.now):
        return None
    authority = await authority_of(request, asked)
    items = await in_transaction(
        request, asked, authority, lambda session: live_items(session, limit=MAX_ITEMS)
    )
    return waiting(
        Queue.KNOWLEDGE_PAST_REVIEW,
        (
            one
            for one in items
            if one.review_by is not None and one.review_by <= asked.now and authority.may_act(one)
        ),
        at_least=len(items) >= MAX_ITEMS,
    )


def uncounted_for(asked: Asking) -> list[Unrecorded]:
    """The queues nothing counts yet, each for a reader who could open the screen it lives on."""
    opens = {
        Queue.TIER_THREE_LEARNING.value: permitted(
            screen(LEARNING_SCREEN).read, asked.reach, asked.now
        ),
        Queue.PUBLISH_APPROVALS.value: permitted(
            screen(AGENTS_SCREEN).read, asked.reach, asked.now
        ),
        Queue.UNBOUND_SIGN_INS.value: may_see_links(asked.reach, asked.now),
    }
    return [one for one in UNCOUNTED_QUEUES if opens.get(one.figure, False)]


#: Each counted queue and the function that asks its screen and its store, in register order.
QUEUE_READERS: Final[
    tuple[tuple[Queue, Callable[[Request, Asking], Awaitable[Waiting | Unrecorded | None]]], ...]
] = (
    (Queue.APPROVALS, approvals_waiting),
    (Queue.ACCESS_REVIEW, access_review_waiting),
    (Queue.ELEVATION, elevation_waiting),
    (Queue.SKILL_REVIEWS, skill_reviews_waiting),
    (Queue.KNOWLEDGE_PAST_REVIEW, knowledge_past_review_waiting),
)


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(OVERVIEW_PATH, response_model=OverviewView, responses=COMMON_RESPONSES)
async def overview(request: Request, asked: Asked) -> OverviewView:
    """The health strip and Needs you, for this reader."""
    if not permitted(screen(OVERVIEW_SCREEN).read, asked.reach, asked.now):
        log.info("overview not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    status, parts = await readiness(request)
    uncounted = uncounted_for(asked)
    found: list[Waiting | None] = []
    for queue, ask in QUEUE_READERS:
        try:
            answer = await ask(request, asked)
        except Failed:
            # Only a reader the queue is for reaches its store. See the module docstring.
            log.warning("overview queue unreadable", queue=queue.value)
            uncounted.append(
                Unrecorded(figure=queue.value, why=A_QUEUE_THAT_COULD_NOT_BE_READ_IS_NAMED)
            )
            continue
        if isinstance(answer, Unrecorded):
            uncounted.append(answer)
        else:
            found.append(answer)
    shown = needs_you(found)
    return OverviewView(
        as_of=asked.now,
        health=HealthView(
            status=status,
            parts=parts,
            worker_last_seen=await worker_seen(request, asked),
            unrecorded=_unrecorded(UNRECORDED_HEALTH),
        ),
        needs_you=[
            QueueView(
                queue=one.queue.value, waiting=one.waiting, at_least=one.at_least, opens=one.opens
            )
            for one in shown
        ],
        uncounted=_unrecorded(uncounted),
    )
