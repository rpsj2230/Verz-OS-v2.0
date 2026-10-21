"""A person asking for their data to be deleted, and the retention owner seeing who has asked.

`brain.member_activity.request_deletion` and `route` were built to be the member's side of an
erasure and nothing called them. Three routes now do.

**An ask is a record, and the erasure is still filed by someone with the authority.** The erasure
queue (`brain.erasure_routes`) is carried out by the worker with nobody asked again, and it retires
the person's account and sign-in, so a member's click filed straight into it would be a silent
deletion with no read of a legal hold and no one deciding. `POST /me/deletion-request` therefore
keeps a row (`ops.deletion_request`, `0273`) and shows the person what a deletion reaches. `GET
/govern/erasure-requests` lists the asks that wait, for the holder of `admin:erasure` over
everything who also reads the Retention screen, and **filing the erasure through `POST
/govern/erasures` closes the ask** (`brain.erasure_routes.file_erasure`). Rejected: filing straight
into the queue as the person, which is the cheaper design and the one that makes a mis-click an
irreversible erasure; the open question of whether an install wants that is the owner's, and this is
what holds under either answer.

**The four lists are `brain.member_activity.route`'s, and none is written out here.** What a
deletion
reaches, what only time removes (the backups), what is kept on purpose, and the order, each with the
sentence `brain.ops.retention.STORES` gives for the store. A store added to the system without a
disposition cannot fall out of this page, because `route` refuses to build without it.

**A switch gates the ask and nothing else.** `member_deletion_requests` is asked before a new ask
is taken. The reading of one's own, and the administrator's list, are never behind it, so turning it
off leaves an ask already made readable and actionable. See
`brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.

**DENIED and ABSENT are one answer.** A caller who may not open the member page, a switch that is
off for an ask, and an administrator without the authority are each the page's one refusal. No count
of asks is returned beyond the rows shown, and the list names no person but by the reference the
erasure form takes, for the reason `brain.erasure_routes` gives: a name for somebody being erased is
the one value that screen should not add.

Task ids: M40.4.2.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent
from brain.erasure_routes import THE_SCREEN, may_erase
from brain.erasure_routes import deletion_requests_of as deletion_requests_of
from brain.member.shell import member_screen
from brain.member_activity import DeletionRoute, MemberError, request_deletion, route
from brain.mine_routes import MEMBER_HOME
from brain.ops.features import is_on
from brain.ops.features_declared.member_deletion_requests import MEMBER_DELETION_REQUESTS
from brain.ops.retention import STORES, Store
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

#: How many waiting asks the Retention screen is shown, oldest first.
WAITING_SHOWN: Final = 100

# ------------------------------------------------------------------ written-down reasons
#: What a person is told before they ask.
ASKING_DELETES_NOTHING: Final = (
    "Asking does not delete anything. Your request goes to whoever holds the erasure authority, "
    "who checks whether anything the company must keep covers you and then files the erasure. The "
    "lists below say what a deletion reaches, what it leaves for time to remove, and what is kept "
    "on purpose."
)

#: What a person is told while their ask waits.
YOUR_ASK_IS_WAITING: Final = (
    "Your request is waiting for an administrator to act on it. Nothing has been deleted yet."
)

#: What a person is told once an administrator has filed the erasure.
YOUR_ASK_WAS_FILED: Final = (
    "An administrator has filed the erasure. It is carried out on the queue's next run, and a "
    "legal hold that covers you stops it."
)


def _not_answerable() -> Absent:
    return Absent("your deletion request is not answerable for this caller")


def _guard(asked: Asked) -> None:
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own deletion request not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


async def deletion_requests_are_on(request: Request) -> bool:
    """Whether a person may make a new ask. Off until turned on; never asked before a reading."""
    found = getattr(request.app.state, "member_deletion_requests_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        return False
    async with factory() as session:
        return await is_on(session, MEMBER_DELETION_REQUESTS)


class MemberDeletionStoreLineView(BaseModel):
    """One store, and what a reader of a subject access request would call it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: str
    holds: str


class MemberDeletionRouteView(BaseModel):
    """Where an ask goes and what a deletion would not reach: the four lists of `route`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order: list[MemberDeletionStoreLineView]
    reaches: list[MemberDeletionStoreLineView]
    rotates_out: list[MemberDeletionStoreLineView]
    retained: list[MemberDeletionStoreLineView]


class MyDeletionView(BaseModel):
    """The person's own ask, if they made one, and what a deletion would do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Whether the page offers the ask: the switch is on and none is waiting.
    may_ask: bool
    asked_at: datetime | None
    #: `none`, `waiting` or `filed`.
    state: str
    told: str
    route: MemberDeletionRouteView


class MemberDeletionWaitingAskView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    subject_id: str
    requested_at: datetime


class MemberDeletionWaitingAsksView(BaseModel):
    """The asks waiting for the retention owner, oldest first. No count of anything else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests: list[MemberDeletionWaitingAskView]
    told: str


#: What the Retention screen says above the waiting asks.
WAITING_ASKS_TOLD: Final = (
    "These people asked, from their own page, for their data to be deleted. Nothing is deleted by "
    "asking. File the erasure with the form above, naming the person and the matter it arrived "
    "under; filing it closes their ask."
)


def _lines(stores: tuple[Store, ...]) -> list[MemberDeletionStoreLineView]:
    facts = {one.store: one.holds for one in STORES}
    return [MemberDeletionStoreLineView(store=one.value, holds=facts[one]) for one in stores]


def route_view(one: DeletionRoute) -> MemberDeletionRouteView:
    """`member_activity.route`'s answer as the four lists a person reads."""
    return MemberDeletionRouteView(
        order=_lines(one.order),
        reaches=_lines(one.reaches),
        rotates_out=_lines(one.rotates_out),
        retained=_lines(one.retained),
    )


async def _view(request: Request, asked: Asked, *, on: bool) -> MyDeletionView:
    me = asked.caller.principal.id
    factory = sessions_of(request)
    latest = None if factory is None else await deletion_requests_of(request).latest(me)
    try:
        shown = route(request_deletion(subject_id=me, at=asked.now))
    except MemberError:
        log.warning("deletion route would not build", principal=me)
        raise _not_answerable() from None
    if latest is None:
        state, told, when = "none", ASKING_DELETES_NOTHING, None
    elif latest.waiting:
        state, told, when = "waiting", YOUR_ASK_IS_WAITING, latest.requested_at
    else:
        state, told, when = "filed", YOUR_ASK_WAS_FILED, latest.requested_at
    return MyDeletionView(
        may_ask=on and state != "waiting",
        asked_at=when,
        state=state,
        told=told,
        route=route_view(shown),
    )


@router.get("/me/deletion-request", response_model=MyDeletionView, responses=COMMON_RESPONSES)
async def my_deletion_request(request: Request, asked: Asked) -> MyDeletionView:
    """What a deletion would do to this person's data, and their own ask if they made one."""
    _guard(asked)
    return await _view(request, asked, on=await deletion_requests_are_on(request))


@router.post("/me/deletion-request", response_model=MyDeletionView, responses=COMMON_RESPONSES)
async def ask_for_my_data_to_be_deleted(request: Request, asked: Asked) -> MyDeletionView:
    """Take this person's ask. Records it and deletes nothing; a second ask is the first.

    The switch first, then the record. Off is the page's one refusal.
    """
    _guard(asked)
    if not await deletion_requests_are_on(request):
        log.info("own deletion request switched off", principal=asked.caller.principal.id)
        raise _not_answerable()
    me = asked.caller.principal.id
    try:
        made = request_deletion(subject_id=me, at=asked.now)
    except MemberError:
        raise _not_answerable() from None
    await deletion_requests_of(request).ask(made.subject_id, at=made.requested_at)
    log.info("own deletion requested", principal=me)
    return await _view(request, asked, on=True)


@router.get(
    "/govern/erasure-requests",
    response_model=MemberDeletionWaitingAsksView,
    responses=COMMON_RESPONSES,
)
async def waiting_asks(request: Request, asked: Asked) -> MemberDeletionWaitingAsksView:
    """The asks waiting for the retention owner. The authority over everything and the screen."""
    if not may_erase(asked.reach, asked.now) or not permitted(
        screen(THE_SCREEN).read, asked.reach, asked.now
    ):
        log.info("waiting deletion asks not answerable", principal=asked.caller.principal.id)
        raise Absent(f"the {THE_SCREEN} screen is not answerable for this caller")
    waiting = await deletion_requests_of(request).waiting(limit=WAITING_SHOWN)
    return MemberDeletionWaitingAsksView(
        requests=[
            MemberDeletionWaitingAskView(
                request_id=one.request_id, subject_id=one.subject_id, requested_at=one.requested_at
            )
            for one in waiting
        ],
        told=WAITING_ASKS_TOLD,
    )
