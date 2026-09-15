"""The approvals waiting on a caller over HTTP, and the one route that decides one.

`brain.console.approvals.card` decides what an approver is shown for one suspension,
`brain.console.role_surfaces.pending_for` decides which suspensions they are offered, and
`brain.console.approvals.decide` decides what a verdict does and writes the ledger entry. None of
the three had a route, so the console had no approvals page to put on a phone and nothing could
decide one. This module adds no rule of its own about who may see or decide an approval, or what a
card carries.

**Who may see an approval is `card` and nothing else.** A card is built for a suspension that
is open and inside the caller's reach, through `pending_for`, and `None` otherwise. The queue,
the single card and the decision all ask it, so a card listed is a card that opens, and a card
that opens is a card that can be decided. The entitlement handed to it is `Asking.reach`, the
admitted set, and never one assembled here.

**An approval this caller may not decide and one that does not exist are one 404 with one
body, whether it is read or decided.** `card` returns the same `None` for a suspension out of
reach, one already decided and one that has lapsed, and says why that matters: an approver who
could tell "not yours" from "already decided" learns the suspension exists. `_no_approval_here`
carries that to the edge of the process, where an address bar is a loop and a caller trying ids
would otherwise enumerate the company's pending actions. A decision is the same loop with a POST
in it. See `AN_APPROVAL_YOU_MAY_NOT_DECIDE_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER`.

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

**A decision is written once because the row is held while it is taken.** `decide_once` locks
the stored suspension, asks `card` whether this reach may see it, hands it to `decide`, which
writes the ledger entry before the state moves, and records the moved suspension against the
pending row. The lock is the store's, so a second request for the same suspension waits and then
finds it decided, which `card` answers with the same `None` as every other reason. There is no
second approval mechanism here and no second statement of who may approve: `decide` is the one
already written and tested. See `A_DECISION_IS_TAKEN_ON_A_HELD_ROW_AND_WRITTEN_ONCE`.

**Two verdicts are offered, and the body refuses a mismatched reason before the store is
asked.** Approving and rejecting are what a phone needs. Taking over needs somewhere for the
person to do the work and amending needs a replacement raised through the gate, and neither
exists; see `TAKING_OVER_AND_AMENDING_WAIT_FOR_WHAT_THEY_HAND_OVER_TO`. A rejection names one
of `RejectionReason`, because `brain.audit.record.redact_details` stores prose as the marker
and the why would be lost. `AuditRecorder.approval` still holds the rule that a rejection needs
a reason and an approval has none. `DecisionAsked` refuses the same two shapes one frame earlier,
so the refusal is the same for every id rather than arriving only for one the caller may see,
and a test holds the two to agree.

**Where suspensions come from is read off `app.state.suspensions`,** in the shape
`brain.api_routes.wiring_of` reads the gate. Either a `SuspensionStore`, which reads at the
caller's reach so row-level security has something to narrow on and which can hold a row to
decide it, or a bare `SuspensionSource`, which can be read and not decided. A process with
neither gets the one fault `_require_source` raises, the same for everybody and every id, and a
process that cannot keep a decision refuses every decision alike. Nothing constructs a store in
production today, because it needs a ledger writer that survives a restart and none exists; see
`brain.app.suspension_store_for`.

Rejected: reading every suspension and finding one by id for the single card. It would work,
and it would make the single card as expensive as the queue, so the protocol asks for one
suspension by its id.

Rejected: a `read:approval` or `approve:*` capability on these routes. Being offered an approval
is `pending_for`'s question and holding the action's own capability in the action's own scope is
its answer; a second gate would be a second answer, and the two would disagree about the same
approver on the same day.

Task ids: M35.3.1.2, M35.3.1.1
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Final, Protocol, Self, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked
from brain.audit.record import ApprovalVerdict, AuditRecorder, LedgerWriter
from brain.console.approvals import ApprovalError, Card, Decided, card, decide
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.gate.leash import SuspendedAction

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why every refusal about one approval is one answer.
AN_APPROVAL_YOU_MAY_NOT_DECIDE_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER: Final = (
    "card returns one None for a suspension out of reach, already decided or lapsed, and an "
    "id nothing holds is a fourth reason for the same None. A route that answered any of "
    "them differently, on a read or on a decision, would let a caller trying ids learn which "
    "pending actions exist, so all four raise the one refusal, with one status and one body."
)

#: Why the queue's bound is applied to the cards and not to the store's rows.
APPROVALS_ARE_FILTERED_BEFORE_THEY_ARE_BOUNDED: Final = (
    "A queue bounded before the reach filter comes back short whenever the filter did "
    "anything, and a short page under a bound says there were approvals the reader was not "
    "shown. So every open suspension is asked about, the cards that survive are ordered and "
    "then bounded, and truncated says there are more this reader may decide, never how many "
    "they may not."
)

#: Why a decision is taken while the row is held.
A_DECISION_IS_TAKEN_ON_A_HELD_ROW_AND_WRITTEN_ONCE: Final = (
    "Two approvers on two phones can press approve on one card in the same second. Read, "
    "decide and write as three separate steps and both find it pending, both write a ledger "
    "entry and one of the two row writes wins. So the row is locked before card is asked, the "
    "entry is written while it is held, and the write names the pending row at the decided "
    "digest. The second request waits, finds the suspension decided, and gets the answer an "
    "invented id gets."
)

#: Why only approving and rejecting are offered.
TAKING_OVER_AND_AMENDING_WAIT_FOR_WHAT_THEY_HAND_OVER_TO: Final = (
    "Taking over says a person is doing the work instead, and there is nowhere yet to hand "
    "the work to. Amending closes the original against the digest of a replacement raised "
    "through the gate, and nothing raises one from an approver's edit. A verdict recorded "
    "with nothing behind it would be a ledger entry describing something that did not happen."
)


# ------------------------------------------------------------------------ the bounds

#: The most cards one queue answer carries. A resource bound and not a permission one: it is
#: applied after the reach filter, so raising it discloses nothing.
MAX_QUEUE_CARDS: Final = 200


# ----------------------------------------------------------------- the vocabulary


class DecidableVerdict(enum.StrEnum):
    """The verdicts this route offers. Two of `ApprovalVerdict`'s four, under its own values.

    See `TAKING_OVER_AND_AMENDING_WAIT_FOR_WHAT_THEY_HAND_OVER_TO`.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class RejectionReason(enum.StrEnum):
    """Why an approver rejected an action, as a code the ledger keeps.

    A closed list rather than free text: `brain.audit.record.redact_details` admits a field-name
    token and stores a sentence as the marker, so a typed reason would be recorded as nothing.
    Written for any company rather than for one, and each says what the next person should look
    at rather than who was at fault.
    """

    NOT_WHAT_WAS_ASKED = "not_what_was_asked"
    WRONG_TARGET = "wrong_target"
    NO_LONGER_NEEDED = "no_longer_needed"
    NEEDS_MORE_DETAIL = "needs_more_detail"


# ------------------------------------------------------------------------ the source


@runtime_checkable
class SuspensionSource(Protocol):
    """Where suspensions are read from, at whatever reach the source was built for."""

    async def open_suspensions(self) -> Sequence[SuspendedAction]:
        """Every suspension that may still be pending. `card` decides which are shown."""
        ...

    async def suspension(self, suspension_id: str) -> SuspendedAction | None:
        """One suspension by its id, whatever its state, or None."""
        ...


class HeldSuspensions(Protocol):
    """One transaction's hold on stored suspensions, for the length of one decision."""

    async def lock(self, suspension_id: str) -> SuspendedAction | None:
        """The suspension, held until the transaction ends, or None."""
        ...

    async def record(self, decided: SuspendedAction) -> bool:
        """Write a decided suspension over its pending row. True when exactly that happened."""
        ...


@runtime_checkable
class SuspensionStore(Protocol):
    """A store that reads at a reach and can hold a row while it is decided.

    `brain.gate.suspension_store.StoredSuspensions` implements it over `gate.suspension`.
    """

    @property
    def ledger(self) -> LedgerWriter:
        """Where a decision's entry is written."""
        ...

    def reading_as(self, reach: EntitlementSet, now: datetime) -> SuspensionSource:
        """The store as this reach may read it."""
        ...

    def holding(
        self, reach: EntitlementSet, now: datetime
    ) -> AbstractAsyncContextManager[HeldSuspensions]:
        """One transaction at this reach, committed when it ends and rolled back on a raise."""
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


class DecisionAsked(BaseModel):
    """What an approver decided: a verdict, and a reason when it is a rejection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: DecidableVerdict
    reason_code: RejectionReason | None = None

    @model_validator(mode="after")
    def _a_rejection_says_why_and_an_approval_does_not(self) -> Self:
        # The rule is `AuditRecorder.approval`'s. It is refused here as well so the refusal
        # arrives before the store is asked, identically for every id. See the module note.
        if self.verdict is DecidableVerdict.REJECTED and self.reason_code is None:
            msg = "a rejection names its reason"
            raise ValueError(msg)
        if self.verdict is DecidableVerdict.APPROVED and self.reason_code is not None:
            msg = "an approval carries no reason"
            raise ValueError(msg)
        return self


class ApprovalDecisionView(BaseModel):
    """The decision that was taken, which is what the approver asked for and nothing more."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suspension_id: str
    verdict: DecidableVerdict


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


async def decide_once(
    held: HeldSuspensions,
    suspension_id: str,
    reach: EntitlementSet,
    recorder: AuditRecorder,
    *,
    asked: DecisionAsked,
    now: datetime,
) -> Decided | None:
    """Decide one held suspension and write the decision, or None when this reach may not.

    None for every reason there is no card, which `card` already makes one reason. See
    `A_DECISION_IS_TAKEN_ON_A_HELD_ROW_AND_WRITTEN_ONCE` for the order. A row that the store
    locked and then would not write is a process fault, raised so the transaction rolls back.
    """
    found = await held.lock(suspension_id)
    if found is None or shown_card(found, reach, now) is None:
        return None
    decided = decide(
        found,
        reach,
        recorder,
        verdict=ApprovalVerdict(asked.verdict.value),
        now=now,
        reason_code=asked.reason_code.value if asked.reason_code is not None else "",
    )
    if not await held.record(decided.suspension):
        msg = f"suspension {suspension_id!r} was held and its decision was not written"
        raise Failed(msg)
    return decided


# ------------------------------------------------------------------------- the wiring


def suspensions_of(request: Request) -> SuspensionStore | SuspensionSource | None:
    """The suspension store or source this process was built with, or None.

    `getattr` and an `isinstance`, in the shape `brain.api_routes.wiring_of` uses and for its
    reason: a process built without one is a value to read, not an `AttributeError` that
    reaches a caller as a 500 reading like a bug.
    """
    found = getattr(request.app.state, "suspensions", None)
    return found if isinstance(found, SuspensionStore | SuspensionSource) else None


def _require_source(request: Request, reach: EntitlementSet, now: datetime) -> SuspensionSource:
    """What this reach reads, or a process-level fault identical for every caller and every id.

    A `Failed` rather than an empty queue, because an empty queue is a claim that nothing is
    waiting on this person, and a process with no store has no evidence for that claim.
    """
    found = suspensions_of(request)
    if isinstance(found, SuspensionStore):
        return found.reading_as(reach, now)
    if found is None:
        raise Failed("no suspension store on this process")
    return found


def _require_store(request: Request) -> SuspensionStore:
    """A store that can keep a decision, or one fault for every caller and every id."""
    found = suspensions_of(request)
    if not isinstance(found, SuspensionStore):
        raise Failed("no suspension store that keeps a decision on this process")
    return found


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
    source = _require_source(request, asked.reach, asked.now)
    return queue(await source.open_suspensions(), asked.reach, asked.now)


@router.get(
    "/approvals/{suspension_id}", response_model=ApprovalCardView, responses=COMMON_RESPONSES
)
async def approval(request: Request, suspension_id: str, asked: Asked) -> ApprovalCardView:
    """One approval's card, or the answer an approval that does not exist gets."""
    source = _require_source(request, asked.reach, asked.now)
    found = await source.suspension(suspension_id)
    shown = shown_card(found, asked.reach, asked.now) if found is not None else None
    if shown is None:
        log.info("approval not answerable", principal=asked.caller.principal.id)
        raise _no_approval_here()
    return card_view(shown)


@router.post(
    "/approvals/{suspension_id}/decision",
    response_model=ApprovalDecisionView,
    responses=COMMON_RESPONSES,
)
async def decide_approval(
    request: Request, suspension_id: str, asked: Asked, decision: DecisionAsked
) -> ApprovalDecisionView:
    """Approve or reject one approval, once, or the answer an approval that does not exist gets."""
    store = _require_store(request)
    # The id the trace middleware vouched for or minted, read from the log context for the
    # reason `brain.api_routes.answer` gives: the header is what the caller proposed.
    trace_id = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    now = asked.now
    recorder = AuditRecorder(
        store.ledger,
        actor_id=asked.reach.principal_id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_id,
        clock=lambda: now,
    )
    try:
        async with store.holding(asked.reach, now) as held:
            decided = await decide_once(
                held, suspension_id, asked.reach, recorder, asked=decision, now=now
            )
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives: whatever a driver raises would
        # otherwise reach the response as a body that is not `ErrorBody`.
        raise Failed(f"deciding: {type(exc).__name__}") from exc
    if decided is None:
        log.info("approval not decidable", principal=asked.caller.principal.id)
        raise _no_approval_here()
    return ApprovalDecisionView(suspension_id=decided.suspension.id, verdict=decision.verdict)
