"""The envelopes waiting on one person, what each will do, and what happens if nobody answers.

An envelope is a `brain.gate.leash.SuspendedAction`: an action an agent was about to take,
stopped, with everything a resume will need to re-check. This module is the member's side of
that queue, and it adds three things the gate deliberately does not have.

**What will happen, stated before the fact, at the approver's own reach (M33.8.1).** The
envelope shows `brain.console.approvals.request_for` of the stored action at the entitlements of
the person it waits on, the same function the Approvals screen and the Lark card use, so an
argument they could not look up is locked. Until 2026-10-06 it carried `SuspendedAction.artefact`
and refused anything else, which is the requester's rendering with every value in it, and
needs-rupash item 14 forbids exactly that. The stored action is what is rendered, so an edited
action renders as edited and its digest no longer matches the approval.

**A plain sentence for what the effect is.** `SideEffect` has five members and the difference
between `write` and `send` is the difference between a record changing and a message leaving
the building. `EFFECT_SENTENCES` is exhaustive over the enumeration and a test holds it to
that, so a sixth member is a failing test rather than an envelope with a blank line where the
consequence should be.

**A stated default of doing nothing, which is what already happens.** M40.6.1.3 asks for the
expiry to have a default and for it to be nothing. The pleasing thing here is that there was
nothing to build: `brain.gate.leash.resume` checks `is_expired` before anything else and
returns a refusal without ever calling the executor, so the default is nothing by
construction. What was missing is somebody being told, which is `DEFAULT_ON_EXPIRY` and
`Lapse`. **The test for this drives `resume` with a recording executor and asserts it was
never called**, because a constant saying nothing happens is worth nothing next to the thing
that would have run.

**One answer, whichever surface it arrives from.** M40.6.1.4 asks for the same approval to be
reachable from a chat channel and from the web without a double action, and there are two
halves to that. The idempotence is `SuspendedAction`'s: a decision returns a new artefact and
`_decided` refuses one that is not open, so a second press produces an error rather than a
second approval. `answer_once` turns that into the two answers a surface actually needs: the
same person answering the same way twice is the second surface catching up and comes back as
`already`, while a different answer or a different person is refused with what really
happened. The refusal is not idempotence being unhelpful, it is the only honest answer when
two people pressed different buttons.

The other half is that both surfaces run this function. `answer_once` takes the channel and
asks `brain.gate.admission.verbs_for_channel` whether it may carry an approve, which is the
same check the gate makes and refuses on WhatsApp, email, Slack, Telegram, Teams and the
widget. A web-only version of this with the channel check "somewhere in the API layer" is how
a Lark button ends up being a weaker way in than the console.

**M40.6.1.2 is not claimed and cannot be built here.** It asks for approve, reject and amend
to be written to the ledger, and there is no ledger action for an approval decision:
`brain.audit.ledger.AuditAction` has eight members, is closed on purpose, and is pinned by
`tests/invariants/test_audit_invariants.py` along with `brain.audit.record.ACTION_BY_METHOD`.
Recording a decision under `GRANT` is refused by that member's own argument, that "what did
this person gain, and when" must stay answerable from one action. So the leaf needs a ninth
member, a method on `AuditRecorder`, an edit to the invariant that pins the pair, and a
migration, because `brain.tables.audit` renders a CHECK constraint from the enumeration.
That is the same shape `COMPOSE_CHANGE` was added in on 2026-09-08 and it is a decision with
a migration behind it rather than something to slip into a member surface.

**Amend was designed and not built, for the same reason plus one of its own.** Amending an
envelope cannot be an edit: `action_digest` binds an approval to the exact action it was
granted for, and `resume` refuses `ARTEFACT_ALTERED` when the two disagree, correctly. So an
amendment is a rejection of the original and a new action put back through `decide` and
`suspend`, which re-runs every check against the amended arguments rather than carrying an
approval across to something nobody read. Written down here rather than half-built, because
the half that would fit today is the rejection, and a control labelled amend that only
rejects is worse than no control.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock.

Task ids: M40.6.1.1, M40.6.1.3, M40.6.1.4
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.console.approvals import request_for
from brain.console.role_surfaces import pending_for
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import SideEffect
from brain.gate.admission import verbs_for_channel
from brain.gate.approval_request import RenderedRequest
from brain.gate.context import Channel
from brain.gate.leash import ApprovalState, SuspendedAction

# ------------------------------------------------------------------ written-down reasons
#: Why the envelope shows the action at its reader's reach and never the stored artefact.
AN_ENVELOPE_SHOWS_WHAT_ITS_READER_MAY_SEE: Final = (
    "The person an approval waits on was chosen for their authority over the action, not for "
    "their reach over the data it carries. The stored artefact is the requester's rendering, with "
    "every value the requester could see, so the envelope renders the stored action at the "
    "reader's own reach and locks what they could not look up."
)

#: Why nothing happening is the default and why it still has to be said.
AN_UNANSWERED_APPROVAL_DOES_NOTHING_AND_SOMEBODY_HAS_TO_BE_TOLD_THAT: Final = (
    "brain.gate.leash.resume checks is_expired first and returns before the executor is "
    "reached, so an envelope nobody answers has already done nothing. What was missing is "
    "the person knowing that in advance: an approval request with a deadline and no stated "
    "consequence reads as a threat, and somebody under time pressure approves it to make it "
    "go away. The sentence is on the envelope before the answer, not in the lapse notice."
)

#: Why a second answer from another surface is not a second decision.
THE_SECOND_SURFACE_IS_CATCHING_UP_AND_IS_NOT_A_SECOND_APPROVAL: Final = (
    "The same envelope is reachable from a chat channel and from the web, so the same person "
    "answering it twice is ordinary: they pressed the button on their phone and then opened "
    "the page. That is the decision already made, reported as already rather than refused, "
    "and it applies nothing a second time. A different answer, or a different person, is "
    "refused with what actually happened, because two people pressing different buttons is "
    "not something idempotence can smooth over."
)

#: Why the channel check lives in the same function both surfaces call.
ONE_ANSWERING_FUNCTION_OR_THE_WEAKER_SURFACE_IS_THE_WAY_IN: Final = (
    "brain.gate.admission decides which channels may carry an approve and refuses most of "
    "them. If the web surface checks that and the chat surface trusts its own webhook, the "
    "chat surface is a weaker way in to the same decision, which is the shape the channel "
    "ceilings exist to prevent. Both call answer_once and answer_once asks "
    "verbs_for_channel, so there is one place the rule can be wrong and it is the place "
    "everything goes through."
)


class MemberApprovalError(Exception):
    """An envelope was answered by somebody, or from somewhere, that may not.

    Outside `brain.core.errors` for `brain.console.own_things.OwnThingsError`'s reason: those
    five outcomes describe an answer given to somebody who asked a question, and this is a
    refusal to operate a control on a personal screen.
    """


# -------------------------------------------------------------------- what will happen
#: What each side effect means, in words somebody who does not work here can act on.
#:
#: Exhaustive over `SideEffect` and a test asserts it, so a sixth member is a failing test
#: rather than an envelope with nothing where the consequence should be. A mapping rather than
#: a method on the enumeration, because `brain.core.envelope` is the tool contract and a
#: member-facing sentence does not belong in it.
EFFECT_SENTENCES: Final[Mapping[SideEffect, str]] = MappingProxyType(
    {
        SideEffect.NONE: "Nothing changes outside the Brain.",
        SideEffect.DRAFT: "A draft is prepared for somebody to look at. Nothing is sent.",
        SideEffect.WRITE: "A record is changed in another system.",
        SideEffect.SEND: "A message leaves the building.",
        SideEffect.MONEY: "Money moves.",
    }
)

#: What happens to an envelope nobody answers (M40.6.1.3). Shown before the answer.
DEFAULT_ON_EXPIRY: Final = (
    "If you do not answer by the time shown, nothing happens. The action is not taken and "
    "nobody has to undo anything. Whoever needs it can raise it again."
)


def effect_sentence(effect: SideEffect) -> str:
    """The plain sentence for one side effect (M40.6.1.1).

    A lookup that raises on a missing member rather than returning a fallback, because a
    fallback would put an envelope with no stated consequence in front of somebody, which is
    the one thing this leaf asks not to happen. The test that pins the mapping to the
    enumeration is what stops that ever being reached.
    """
    return EFFECT_SENTENCES[effect]


@dataclass(frozen=True)
class Envelope:
    """One approval waiting on this person, with the consequence stated (M40.6.1.1).

    Everything on it is read off the suspension and nothing is recomputed. The three refusals
    below are the three ways a surface could show somebody an envelope that is not the one
    they will be deciding.
    """

    suspension: SuspendedAction
    #: The stored action at the reader's reach. See `AN_ENVELOPE_SHOWS_WHAT_ITS_READER_MAY_SEE`.
    what_will_happen: RenderedRequest
    #: What the effect means, in words.
    effect: str
    #: The stated consequence of not answering, which is nothing.
    if_nothing_happens: str = DEFAULT_ON_EXPIRY

    def __post_init__(self) -> None:
        if self.effect != effect_sentence(self.suspension.action.tool.side_effect):
            msg = (
                f"this envelope describes the effect as {self.effect!r} and the action's "
                f"effect is {self.suspension.action.tool.side_effect.value!r}, so the "
                "consequence on the screen is not the consequence of the action"
            )
            raise ValueError(msg)
        if not self.if_nothing_happens.strip():
            told = AN_UNANSWERED_APPROVAL_DOES_NOTHING_AND_SOMEBODY_HAS_TO_BE_TOLD_THAT
            msg = (
                "an envelope with a deadline and no stated consequence of missing it reads "
                f"as a threat. {told}"
            )
            raise ValueError(msg)

    @property
    def expires_at(self) -> datetime:
        """When this stops being answerable. Read off the suspension, never stored twice."""
        return self.suspension.expires_at


def envelope_for(suspension: SuspendedAction, reader: EntitlementSet, now: datetime) -> Envelope:
    """One suspension as `reader` sees it (M40.6.1.1, M33.8.1).

    The only constructor anything should use. Building an `Envelope` by hand is possible and
    is checked by its own validators; this is the path that cannot get the derived values
    wrong in the first place. See `AN_ENVELOPE_SHOWS_WHAT_ITS_READER_MAY_SEE`.
    """
    return Envelope(
        suspension=suspension,
        what_will_happen=request_for(suspension, reader, now),
        effect=effect_sentence(suspension.action.tool.side_effect),
    )


def awaiting(
    entitlement: EntitlementSet,
    suspensions: Sequence[SuspendedAction],
    now: datetime,
) -> tuple[Envelope, ...]:
    """The envelopes this person may decide (M40.6.1.1), and no count of the rest.

    `brain.console.role_surfaces.pending_for` is the filter, called rather than rewritten. It
    narrows by what the approver holds and by whether their scope matches the target's own
    row, which is the rule that an approver may not wave through what they could not do
    themselves, and it returns one value with no count of what it withheld.

    A member queue that filtered by the Approver role instead would be wrong in both
    directions at once: somebody holding the role and not the capability would be offered
    decisions they cannot make, and somebody holding the capability and not the role would
    not see their own.

    Order follows `suspensions`, which is `pending_for`'s own decision.
    """
    return tuple(
        envelope_for(one, entitlement, now) for one in pending_for(entitlement, suspensions, now)
    )


# ------------------------------------------------------------------- nobody answered
@dataclass(frozen=True)
class Lapse:
    """An envelope that expired unanswered, and what that did, which is nothing (M40.6.1.3).

    Carries the suspension id rather than the suspension, because a lapse notice is delivered
    and a delivered object carrying the artefact would put the action's argument values into
    whatever channel it went out on. `brain.gate.leash.ActionRecord` makes the same split
    between the artefact and the half that is retained.
    """

    suspension_id: str
    expired_at: datetime
    what_happened: str = DEFAULT_ON_EXPIRY

    def __post_init__(self) -> None:
        if not self.suspension_id.strip():
            msg = "a lapse naming no envelope tells the reader that something expired"
            raise ValueError(msg)


def lapsed(
    entitlement: EntitlementSet,
    suspensions: Sequence[SuspendedAction],
    now: datetime,
) -> tuple[Lapse, ...]:
    """What in this person's own queue expired with nobody answering (M40.6.1.3).

    **Narrowed by the same predicate the queue uses, asked at the moment each was raised.**
    `pending_for` answers "may this person decide this now", and by definition it says no to
    everything here, because these have expired. So each is offered to it at its own
    `raised_at`, when it was open, which reuses the whole of `_may_approve` rather than
    reimplementing the capability-and-scope check for a second surface.

    The entitlement is the one this person holds now and not the one they held then, which is
    the conservative direction: somebody whose access was removed stops seeing what lapsed in
    their old department, and somebody who has just been given access sees a little history
    they could have decided. The alternative needs an entitlement as at a past moment, which
    nothing in this repository can produce.

    **Only an unanswered envelope lapses, and there is deliberately no clause here saying
    so.** One was written and a mutation proved it dead: `pending_for` calls
    `SuspendedAction.is_open`, which reads the state as it stands now rather than as it stood
    at the moment it is asked about, so a decided envelope is already refused by the
    narrowing above however early that moment is. A second `state is PENDING` beside it reads
    as the guard that keeps a rejected envelope out of a lapse notice and could never fire,
    which is `brain.connectors.manifest.ProjectedEntity`'s recorded case of two enforcement
    points that are really one. The property is still asserted by a test, because it must
    hold however it is enforced.
    """
    return tuple(
        Lapse(suspension_id=one.id, expired_at=one.expires_at)
        for one in suspensions
        if one.is_expired(now) and pending_for(entitlement, (one,), one.raised_at)
    )


# ------------------------------------------------------------------- answering, once
#: The two answers a member surface offers. Amend is absent; see the module docstring.
#:
#: Not an enumeration of its own but the states themselves, because a second vocabulary
#: mapping onto `ApprovalState` is a second place the two can disagree about what approve
#: means, and the mapping would have exactly two entries.
ANSWERS: Final[frozenset[ApprovalState]] = frozenset(
    {ApprovalState.APPROVED, ApprovalState.REJECTED}
)


@dataclass(frozen=True)
class Decided:
    """An envelope after somebody answered it (M40.6.1.4).

    `already` is the whole reason this type exists rather than a bare `SuspendedAction`. A
    surface that cannot tell an answer from a repeat shows "approved" twice, or shows an
    error to somebody who did nothing wrong, and the second is what a Lark button and an open
    browser tab produce between them every time.
    """

    suspension: SuspendedAction
    #: True when this answer had already been given, by this person, this way.
    already: bool


def answer_once(
    suspension: SuspendedAction,
    *,
    answer: ApprovalState,
    who: str,
    channel: Channel,
    at: datetime,
) -> Decided:
    """Answer one envelope from either surface, once (M40.6.1.4).

    Four refusals and one repeat, in an order that is not arbitrary.

    The answer itself is checked first, because `ApprovalState` has a third member and
    `PENDING` is not an answer. Then the channel, because a surface that may not carry an
    approve may not carry one whatever the state of the envelope is, and answering that
    question after looking at the envelope would tell an unauthorised channel whether it
    exists. Then the state, so that the second surface catching up is recognised before
    expiry is considered: somebody who answered at noon and opens the page at midnight
    answered, and telling them it expired would be false. Then expiry, and only then the
    decision.

    See `THE_SECOND_SURFACE_IS_CATCHING_UP_AND_IS_NOT_A_SECOND_APPROVAL` and
    `ONE_ANSWERING_FUNCTION_OR_THE_WEAKER_SURFACE_IS_THE_WAY_IN`.
    """
    if answer not in ANSWERS:
        msg = f"{answer.value!r} is not an answer; an envelope is approved or rejected"
        raise MemberApprovalError(msg)
    if "approve" not in verbs_for_channel(channel):
        msg = (
            f"an approval cannot be answered from {channel.value}. "
            f"{ONE_ANSWERING_FUNCTION_OR_THE_WEAKER_SURFACE_IS_THE_WAY_IN}"
        )
        raise MemberApprovalError(msg)
    if suspension.state is not ApprovalState.PENDING:
        if suspension.state is answer and suspension.decided_by == who:
            return Decided(suspension=suspension, already=True)
        msg = (
            f"this envelope was already {suspension.state.value} and cannot be "
            f"{answer.value} now. {THE_SECOND_SURFACE_IS_CATCHING_UP_AND_IS_NOT_A_SECOND_APPROVAL}"
        )
        raise MemberApprovalError(msg)
    if suspension.is_expired(at):
        msg = f"this envelope expired at {suspension.expires_at.isoformat()}. {DEFAULT_ON_EXPIRY}"
        raise MemberApprovalError(msg)

    if answer is ApprovalState.APPROVED:
        return Decided(suspension=suspension.approved_by(who, at), already=False)
    return Decided(suspension=suspension.rejected_by(who, at), already=False)


def approvals_gaps(
    envelopes: Sequence[Envelope] = (),
    sentences: Mapping[SideEffect, str] = EFFECT_SENTENCES,
) -> tuple[str, ...]:
    """Everything that would put an envelope in front of somebody it does not describe.

    Takes its inputs for `brain.console.own_things.own_gaps`' reason: a diagnostic exercised
    only against objects a constructor already refused has nothing to report, and every check
    below is about an `Envelope` that arrived some other way, which is what a row loaded from
    a table is.

    `sentences` is defaulted rather than read off the module for the same reason, and it took
    no argument first. That version could not be shown to fire: `EFFECT_SENTENCES` is
    complete, so the loop below was a guard no test could reach, which is the exact shape
    CLAUDE.md records as the source of almost every surviving mutation here.
    """
    gaps: list[str] = []

    gaps.extend(
        f"no sentence for the {effect.value} side effect, so an envelope for one would be "
        "shown with nothing where the consequence should be"
        for effect in SideEffect
        if effect not in sentences
    )

    for one in envelopes:
        if not one.if_nothing_happens.strip():
            gaps.append(
                f"envelope {one.suspension.id} states no consequence for not answering. "
                f"{AN_UNANSWERED_APPROVAL_DOES_NOTHING_AND_SOMEBODY_HAS_TO_BE_TOLD_THAT}"
            )

    return tuple(gaps)
