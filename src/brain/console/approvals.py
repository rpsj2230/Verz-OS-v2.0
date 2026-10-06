"""What an approver is shown, what they may do about it, and what reaches the ledger.

`brain.console.role_surfaces.pending_for` decides which suspensions an approver is offered and
`brain.gate.leash.SuspendedAction` holds the state machine. Neither says what the person sees
or what happens when they decide, and those are the two halves here.

**What will happen is rendered at the approver's own reach, and the tool call is not shown at
all (M33.8.1, needs-rupash 14).** A tool call is a capability name and a row of arguments. The
capability is a fact about the permission model, which `brain.console.auditor` argues at length
must not leak through a report, and the arguments are the client's own data, arriving on a screen
whose reader was chosen for their authority over an action rather than their reach over that data.
So the card carries `brain.gate.approval_request.render_request` of the action at the approver's
entitlements, under the field policy of the action's entity (`request_policy`): an argument they
may read shows its value and every other one is locked. Until 2026-10-06 the card carried
`SuspendedAction.artefact`, the requester's rendering with every value in it, on the argument that
an approval of a re-rendered artefact is an approval of something nobody read; the action digest
is what binds an approval to one action, and the requester's rendering is what item 14 forbids.
`Card` has no field a tool call could arrive in, and `card_gaps` reports one if a later edit adds
it. See `AN_APPROVER_READS_WHAT_WILL_HAPPEN_AND_NOT_HOW`.

**Four verdicts, three states, and the asymmetry is the point.** `brain.audit.record`'s
`ApprovalVerdict` argues it: a state says whether the stored action may run and a verdict says
what the person did. Rejecting and taking the work over both leave the action unrun, so they
are one state and two verdicts, and an estate where half the approvals are taken over is an
estate whose agents are configured wrongly, which is invisible if both land as rejected.

**An amendment closes the original and this module will not build the replacement.** Producing
an amended action from an approver's edit is exactly where an approver could amend something
into a thing they could not have asked for themselves, and the check that would stop it is the
gate's rather than a screen's. So `decide` records the amendment against a digest that already
exists and closes the original, and the replacement goes through the ordinary suspension path
with its own reach check. See `AN_AMENDMENT_A_SCREEN_BUILDS_IS_AN_ACTION_NOBODY_ENTITLED`.

**Every verdict writes exactly one entry and the write is the caller's recorder.** Nothing here
opens a ledger; `AuditRecorder` is passed in, on the split the rest of this package keeps. A
decision that changed the suspension and failed to record would be the one case worth
preventing, so the entry is written first and the updated suspension is derived from it: if
the ledger refuses, nothing has been decided.

Rejected: a `decided_reason` field on `SuspendedAction`. The state machine already carries who
and when, and a reason on the row would be the second copy of something the ledger holds, with
the row's retention rather than the ledger's. `brain.ops.queue.Job` makes the same refusal
about the same shape.

Rejected: offering the approver a count of what they were not shown. `pending_for` returns one
value for the reason `A_QUEUE_THAT_COUNTS_WHAT_IT_WITHHELD_IS_A_CENSUS_OF_OTHER_DEPARTMENTS`
gives, and a card view that said "and four others" would put the count back one screen along.

Task ids: M33.6.1.2, M33.6.1.3, M40.6.1.2, M33.8.1
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Final

from brain.audit.ledger import AuditEntry
from brain.audit.record import ApprovalVerdict, AuditRecorder
from brain.console.role_surfaces import pending_for
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import ToolDefinition
from brain.core.field_policy import FieldPolicy
from brain.gate.approval_request import (
    RenderedRequest,
    RequestRefusedError,
    render_request,
    render_terms,
)
from brain.gate.leash import Action, SuspendedAction
from brain.knowledge.promotion import is_promotion


class ApprovalError(Exception):
    """A decision was asked for that the approver may not take, or that says nothing."""


# ------------------------------------------------------------------ written-down reasons
#: Why the card carries the artefact and never the call that produced it.
AN_APPROVER_READS_WHAT_WILL_HAPPEN_AND_NOT_HOW: Final = (
    "A tool call is a capability name and a row of arguments. The capability is a fact about "
    "the permission model, which a report must not leak, and the arguments are the client's "
    "own data arriving on a screen whose reader was chosen for their authority over an "
    "action rather than their reach over that data. What an approver needs is what will "
    "happen, rendered at their own reach, with every argument they could not look up locked."
)


#: Why an amended action is not built here.
AN_AMENDMENT_A_SCREEN_BUILDS_IS_AN_ACTION_NOBODY_ENTITLED: Final = (
    "Producing an amended action from an approver's edit is where an approver amends "
    "something into a thing they could not have asked for themselves, and the check that "
    "stops that is the gate's rather than a screen's. So an amendment here records a digest "
    "that already exists and closes the original, and the replacement goes through the "
    "ordinary suspension path with its own reach check."
)

#: Why an approval carries no reason and the other three do.
A_REASON_EVERY_VERDICT_CARRIES_IS_A_FIELD_NOBODY_READS: Final = (
    "Rejecting, taking over and amending are each somebody deciding the thing should not run "
    "as asked, and the next person needs to know why. Requiring a reason on an approval "
    "collects the same word forever, and a field that always says the same thing is one "
    "nobody reads on the row where it mattered. brain.audit.record.AuditRecorder.approval "
    "holds the rule; this module does not restate it and lets that refusal through."
)

#: Why a person's own request is approved or rejected and never taken over.
ONLY_AN_AGENT_S_WORK_IS_TAKEN_OVER: Final = (
    "Taking over says the approver will do by hand what an agent prepared, and it counts against "
    "that agent's rung on that target. A promotion is a person asking for their own document to "
    "reach further, prepared by nobody, so there is no agent whose work is taken over and no rung "
    "to lower: it is approved or rejected, and the card says whether the third choice is offered."
)

#: The names a tool call would arrive under if somebody added it to the card later. Read from
#: the shapes it would come from rather than invented here, so a rename moves both.
CALL_SHAPED: Final[frozenset[str]] = frozenset(
    {
        "action",
        "arguments",
        "args",
        "capability",
        "required_capability",
        "row",
        "params",
        "parameters",
        "tool",
        "payload",
    }
)


@dataclass(frozen=True)
class Card:
    """One approval as its approver sees it (M33.6.1.2).

    `request` is the action rendered at the approver's own reach by
    `brain.gate.approval_request.render_request`, never the requester's artefact. Everything else
    is what a person needs to decide: which suspension this is, when it lapses, and whose reach it
    would run under, which is the fact that makes "approve" mean something different from "do it".

    There is no field a tool call could arrive in, and `card_gaps` says so mechanically.
    """

    suspension_id: str
    request: RenderedRequest
    runs_as: str
    raised_at: datetime
    expires_at: datetime
    #: Whether the approver is offered taking the work over: an agent's prepared action, never a
    #: person's own request. False unless `card` says otherwise. See
    #: `ONLY_AN_AGENT_S_WORK_IS_TAKEN_OVER`.
    may_take_over: bool = False
    #: Why approving this sends nothing, in the grant's own words, or empty when it would run
    #: (M11.7.3): a connector write this install has not allowed. Never a tool call's detail.
    unsent_because: str = ""


def card_gaps(shape: type = Card) -> tuple[str, ...]:
    """Fields on a card a tool call could arrive in (M33.6.1.2).

    Asked of the class rather than of a reviewer, in the same shape
    `brain.console.agent_output.artifact_gaps` asks it about an artifact carrying its own
    bytes. The failure this guards against is somebody making the card more useful.

    The class is a parameter and that is not generality for its own sake. Asked only about
    `Card`, which has no such field, this function returns nothing whether it is working or
    not, and a mutation proved it: replacing the condition with `False` changed no answer, and
    so did deleting a name from the list it searches. A check nothing can reach is the defect
    this repository keeps finding, and the fix is the same one `brain.ops.controls.runbook_gaps`
    made on the same day, which is to let a test hand it something that ought to fail.
    """
    return tuple(
        f"{shape.__name__}.{one.name} is named like a tool call, and an approver reads what "
        f"will happen rather than how. {AN_APPROVER_READS_WHAT_WILL_HAPPEN_AND_NOT_HOW}"
        for one in fields(shape)
        if one.name in CALL_SHAPED
    )


def terms_not_data() -> tuple[ToolDefinition, ...]:
    """The product's own tools whose arguments are the terms of the decision, shown whole.

    A closed set a test holds, matched on the whole definition rather than the name, so a tool of
    anybody else's that borrowed one of these names is rendered under its entity's classification
    like every other. See `brain.gate.approval_request.AN_ACTION_S_OWN_TERMS_ARE_NOT_DATA`.
    """
    from brain.browsing.sessions import ACT_ON_SURFACE
    from brain.knowledge.promotion import PROMOTION_TOOL

    return (PROMOTION_TOOL, ACT_ON_SURFACE)


def request_policy(action: Action) -> FieldPolicy:
    """The field policy an approver's view of `action` is rendered under.

    Its entity's classification, its own source's first. An entity nothing classifies is the
    empty policy, under which every argument is locked.
    """
    from brain.tools.startup import classification_for

    found = classification_for(action.tool.entity, source=action.tool.source or None)
    return found.policy() if found is not None else FieldPolicy(rules=())


def request_for(
    suspension: SuspendedAction, reader: EntitlementSet, now: datetime
) -> RenderedRequest:
    """What `reader` is shown of one held action, on every surface an approval is drawn on.

    The product's own terms for one of `terms_not_data`, and otherwise the action rendered at the
    reader's reach under `request_policy`. **The one function on any approver's surface that reads
    `SuspendedAction.artefact`, and only for the product's own tools**, which a test holds by
    reading the source. See `brain.gate.approval_request.AN_ACTION_S_OWN_TERMS_ARE_NOT_DATA`.
    """
    action = suspension.action
    if action.tool in terms_not_data():
        return render_terms(suspension.artefact, reader)
    return render_request(action, reader, request_policy(action), now)


def card(
    suspension: SuspendedAction,
    entitlement: EntitlementSet,
    now: datetime,
    *,
    unsent_because: str = "",
) -> Card | None:
    """What this approver is shown for this suspension, or `None`.

    `None` for a suspension this approver is not offered, and it is the same `None` for one
    that is out of reach, one that has already been decided and one that has lapsed. Those
    are three different reasons and a card view must not distinguish them: an approver who
    could tell "not yours" from "already decided" learns that the suspension exists.

    Decided through `pending_for` rather than by asking the two questions again, so a screen
    and its queue cannot disagree about what may be decided.

    `may_take_over` is true for an agent's prepared action and false for a promotion; see
    `ONLY_AN_AGENT_S_WORK_IS_TAKEN_OVER`.
    """
    if not pending_for(entitlement, [suspension], now):
        return None
    try:
        request = request_for(suspension, entitlement, now)
    except RequestRefusedError as refused:
        raise ApprovalError(str(refused)) from refused
    return Card(
        suspension_id=suspension.id,
        request=request,
        runs_as=suspension.principal_id,
        raised_at=suspension.raised_at,
        expires_at=suspension.expires_at,
        may_take_over=not is_promotion(suspension),
        unsent_because=unsent_because,
    )


@dataclass(frozen=True)
class Decided:
    """A decision that was taken: the suspension as it now stands, and the entry recording it.

    Both, because a caller needs the row to store and the entry to chain, and returning only
    the suspension would leave the recording to a second call that can be forgotten.
    """

    suspension: SuspendedAction
    entry: AuditEntry


#: Verdicts that leave the agent's action unrun. Three of the four, which is why there are
#: three states and not four: `brain.audit.record.ApprovalVerdict` argues the asymmetry.
DOES_NOT_RUN: Final[frozenset[ApprovalVerdict]] = frozenset(
    {ApprovalVerdict.REJECTED, ApprovalVerdict.TAKEN_OVER, ApprovalVerdict.AMENDED}
)


def decide(
    suspension: SuspendedAction,
    entitlement: EntitlementSet,
    recorder: AuditRecorder,
    *,
    verdict: ApprovalVerdict,
    now: datetime,
    reason_code: str = "",
    amended_digest: str = "",
) -> Decided:
    """Approve, reject, take over or amend, and record it (M33.6.1.3, M40.6.1.2).

    Refuses a suspension this approver is not offered, using `pending_for` rather than
    repeating its two questions: an approver who may not see it may not decide it, and a
    screen that asked differently from the queue would eventually disagree with it.

    An amendment needs a digest that is not the original's. An amendment recorded against the
    same digest is an approval wearing another word, and it would read in the ledger as a
    change that was never made. The other three verdicts refuse one: a digest on a rejection
    describes an action the rejection did not produce.

    The entry is written before the suspension is moved. If the ledger refuses, nothing has
    been decided, which is the right way round: a decision that took effect and was not
    recorded is the one case worth preventing.

    The reason code is not validated here. `AuditRecorder.approval` holds that rule, including
    the asymmetry that an approval carries none, and a second copy would be a second place for
    it to be subtly different. See `A_REASON_EVERY_VERDICT_CARRIES_IS_A_FIELD_NOBODY_READS`.
    """
    if not pending_for(entitlement, [suspension], now):
        msg = (
            f"suspension {suspension.id!r} is not this approver's to decide; it is out of "
            "reach, already decided or lapsed, and which of those is not said here"
        )
        raise ApprovalError(msg)
    if verdict is ApprovalVerdict.AMENDED:
        if not amended_digest:
            msg = "an amendment records the digest of what was substituted, and none was given"
            raise ApprovalError(msg)
        if amended_digest == suspension.action_digest:
            msg = (
                "the amended digest is the original's, so nothing was amended and this is an "
                "approval wearing another word"
            )
            raise ApprovalError(msg)
    elif amended_digest:
        msg = (
            f"a {verdict.value} verdict carries no amended digest; it describes an action "
            "this decision did not produce"
        )
        raise ApprovalError(msg)
    entry = recorder.approval(
        suspension_id=suspension.id,
        verdict=verdict,
        digest=amended_digest or suspension.action_digest,
        reason_code=reason_code,
    )
    moved = (
        suspension.rejected_by(entitlement.principal_id, now)
        if verdict in DOES_NOT_RUN
        else suspension.approved_by(entitlement.principal_id, now)
    )
    return Decided(suspension=moved, entry=entry)
