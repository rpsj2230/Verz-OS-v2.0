"""The approvals waiting on a caller, over HTTP, and why this router decides nothing.

`brain.console.approvals.card` decides what an approver is shown for one suspension and
`brain.console.role_surfaces.pending_for` decides which suspensions they are offered. Neither
had a route, so the console had no approvals page to put on a phone. This module is the read
half, and it adds no rule of its own about who may see an approval or what a card carries.

**Who may see an approval is `card` and nothing else.** A card is built for a suspension that
is open and inside the caller's reach, through `pending_for`, and `None` otherwise. The queue
and the single card both ask it, so a card listed is a card that opens and a card that opens is
a card listed. The entitlement handed to it is `Asking.reach`, the admitted set, and never one
assembled here.

**An approval this caller may not decide and one that does not exist are one 404 with one
body.** `card` returns the same `None` for a suspension out of reach, one already decided and
one that has lapsed, and says why that matters: an approver who could tell "not yours" from
"already decided" learns the suspension exists. `_no_approval_here` carries that to the edge
of the process, where an address bar is a loop and a caller trying ids would otherwise
enumerate the company's pending actions. See
`AN_APPROVAL_YOU_MAY_NOT_DECIDE_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER`.

**The queue is a listing, and a listing is where a total leaks.** `ApprovalQueue` never sets
the `total` it inherits, an approval outside the caller's reach is absent rather than drawn
greyed out, and the bound is applied after the filter, for the reason
`brain.agent_routes.A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED` gives about the roster. The
order is soonest to lapse first, which is the order a person on a phone needs and says nothing
about anything they were not shown. See `APPROVALS_ARE_FILTERED_BEFORE_THEY_ARE_BOUNDED`.

**The card on the wire is `Card`, field for field.** `ApprovalCardView` has exactly the five
fields `Card` has, so the tool call `brain.console.approvals.AN_APPROVER_READS_WHAT_WILL_
HAPPEN_AND_NOT_HOW` keeps off the card cannot come back one layer out, in a serialiser.

**A suspension that does not make a card is absent for everybody.** `Card` refuses an artefact
that is only whitespace, which `SuspendedAction` admits because its bound is a length. Raising
that as a 500 would take the queue down for every approver over one row and, on the single
card, tell an id that exists from one that does not. It is logged and absent, as
`brain.agent_routes.A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY` argues for agents.

**Deciding is not wired, and nothing here pretends it is.** There is no POST. Nothing in this
repository stores a `SuspendedAction`: no table, no migration and no store behind
`SuspensionSource`, so a decided suspension would have nowhere to be written, and the
idempotence `brain.member.approvals.answer_once` relies on is a stored state rather than a
returned one. A decide route over a source that cannot persist would record a verdict in the
ledger and then lose it, which lets the same approval be decided again on the next request.
See `NOTHING_STORES_A_SUSPENSION_SO_NOTHING_IS_DECIDED_HERE`.

**And the read has no store behind it in production either, which is stated rather than
hidden.** `SuspensionSource` is the protocol a store will implement, read off
`app.state.suspensions` in the shape `brain.api_routes.wiring_of` reads the gate. Nothing
constructs one today, so every caller gets the one process fault `_require_source` raises,
which is the same answer for everybody and every id. An empty queue would be the wrong answer:
it is a fact somebody believes, namely that nothing is waiting on them.

Rejected: reading every suspension and finding one by id for the single card. It would work,
and it would make the single card as expensive as the queue on the day there is a store, so
the protocol asks for one suspension by its id.

Rejected: a `read:approval` capability on either route. Being offered an approval is
`pending_for`'s question and holding the action's own capability in the action's own scope is
its answer; a second gate would be a second answer, and the two would disagree about the same
approver on the same day.

Task ids: M35.3.1.2
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked
from brain.console.approvals import ApprovalError, Card, card
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.gate.leash import SuspendedAction

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why the single card refuses alike for every reason there is no card.
AN_APPROVAL_YOU_MAY_NOT_DECIDE_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER: Final = (
    "card returns one None for a suspension out of reach, already decided or lapsed, and an "
    "id nothing holds is a fourth reason for the same None. A route that answered any of "
    "them differently would let a caller trying ids learn which pending actions exist, so "
    "all four raise the one refusal, with one status and one body."
)

#: Why the queue's bound is applied to the cards and not to the store's rows.
APPROVALS_ARE_FILTERED_BEFORE_THEY_ARE_BOUNDED: Final = (
    "A queue bounded before the reach filter comes back short whenever the filter did "
    "anything, and a short page under a bound says there were approvals the reader was not "
    "shown. So every open suspension is asked about, the cards that survive are ordered and "
    "then bounded, and truncated says there are more this reader may decide, never how many "
    "they may not."
)

#: Why there is no decide route on this router.
NOTHING_STORES_A_SUSPENSION_SO_NOTHING_IS_DECIDED_HERE: Final = (
    "decide returns the suspension as it now stands and the entry recording it, and both "
    "have to be kept. Nothing in this repository stores a suspension, so a decided one would "
    "be recorded in the ledger and then lost, and the next request would find it still open "
    "and let it be decided again. A decide route is written the day a store exists, not "
    "before it, and until then this router serves GET and nothing else."
)


# ------------------------------------------------------------------------ the bounds

#: The most cards one queue answer carries. A resource bound and not a permission one: it is
#: applied after the reach filter, so raising it discloses nothing.
MAX_QUEUE_CARDS: Final = 200


# ------------------------------------------------------------------------ the source


@runtime_checkable
class SuspensionSource(Protocol):
    """Where suspensions are read from. Nothing implements this yet; see the module note."""

    async def open_suspensions(self) -> Sequence[SuspendedAction]:
        """Every suspension that may still be pending. `card` decides which are shown."""
        ...

    async def suspension(self, suspension_id: str) -> SuspendedAction | None:
        """One suspension by its id, whatever its state, or None."""
        ...


# ------------------------------------------------------------------------ the shapes


class ApprovalCardView(BaseModel):
    """One approval as its approver sees it: `brain.console.approvals.Card`, field for field.

    No field a tool call could arrive in, because `Card` has none, and a test holds the two
    sets of names equal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    suspension_id: str
    artefact: str
    runs_as: str
    raised_at: datetime
    expires_at: datetime


class ApprovalQueue(Page[ApprovalCardView]):
    """Every approval this caller may decide, soonest to lapse first.

    `total` is inherited and never populated, and `next_cursor` is always null: the queue is
    bounded by `MAX_QUEUE_CARDS` rather than paged. See
    `APPROVALS_ARE_FILTERED_BEFORE_THEY_ARE_BOUNDED`.
    """

    #: There are more approvals this caller may decide than this answer carries. Never how many.
    truncated: bool = False


# ------------------------------------------------------------------ the decisions


def card_view(shown: Card) -> ApprovalCardView:
    """One card under the wire names, which are `Card`'s own."""
    return ApprovalCardView(
        suspension_id=shown.suspension_id,
        artefact=shown.artefact,
        runs_as=shown.runs_as,
        raised_at=shown.raised_at,
        expires_at=shown.expires_at,
    )


def shown_card(suspension: SuspendedAction, reach: EntitlementSet, now: datetime) -> Card | None:
    """The card this reach is shown for one suspension, or None, including when none can be built.

    A suspension whose artefact is only whitespace is refused by `Card` itself, and that
    refusal is absence here rather than a status. See the module note.
    """
    try:
        return card(suspension, reach, now)
    except ApprovalError:
        log.warning("suspension does not make a card", suspension=suspension.id)
        return None


def queue(
    suspensions: Sequence[SuspendedAction], reach: EntitlementSet, now: datetime
) -> ApprovalQueue:
    """The cards this reach may decide, soonest to lapse first, bounded after filtering."""
    cards = sorted(
        (
            shown
            for shown in (shown_card(one, reach, now) for one in suspensions)
            if shown is not None
        ),
        key=lambda shown: (shown.expires_at, shown.suspension_id),
    )
    return ApprovalQueue(
        items=[card_view(shown) for shown in cards[:MAX_QUEUE_CARDS]],
        next_cursor=None,
        truncated=len(cards) > MAX_QUEUE_CARDS,
    )


# ------------------------------------------------------------------------- the wiring


def suspensions_of(request: Request) -> SuspensionSource | None:
    """The suspension source this process was built with, or None.

    `getattr` and an `isinstance`, in the shape `brain.api_routes.wiring_of` uses and for its
    reason: a process built without one is a value to read, not an `AttributeError` that
    reaches a caller as a 500 reading like a bug.
    """
    found = getattr(request.app.state, "suspensions", None)
    return found if isinstance(found, SuspensionSource) else None


def _require_source(request: Request) -> SuspensionSource:
    """The source, or a process-level fault identical for every caller and every id.

    A `Failed` rather than an empty queue, because an empty queue is a claim that nothing is
    waiting on this person, and a process with no store has no evidence for that claim.
    """
    source = suspensions_of(request)
    if source is None:
        raise Failed("no suspension store on this process")
    return source


def _no_approval_here() -> Absent:
    """The one refusal this router makes about an approval.

    See `AN_APPROVAL_YOU_MAY_NOT_DECIDE_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER`.
    `brain.app.handle_brain_error` sends `Absent.public_message`; this string reaches a log.
    """
    return Absent("no approval is answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["approvals"])


@router.get("/approvals", response_model=ApprovalQueue, responses=COMMON_RESPONSES)
async def approvals(request: Request, asked: Asked) -> ApprovalQueue:
    """Every approval this caller may decide, at their admitted reach."""
    source = _require_source(request)
    return queue(await source.open_suspensions(), asked.reach, asked.now)


@router.get(
    "/approvals/{suspension_id}", response_model=ApprovalCardView, responses=COMMON_RESPONSES
)
async def approval(request: Request, suspension_id: str, asked: Asked) -> ApprovalCardView:
    """One approval's card, or the answer an approval that does not exist gets."""
    source = _require_source(request)
    found = await source.suspension(suspension_id)
    shown = shown_card(found, asked.reach, asked.now) if found is not None else None
    if shown is None:
        log.info("approval not answerable", principal=asked.caller.principal.id)
        raise _no_approval_here()
    return card_view(shown)
