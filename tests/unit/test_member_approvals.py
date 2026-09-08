"""What a member is asked to approve, what happens if they say nothing, and answering once.

Three claims and the middle one is the reason this file exists.

**What will happen, before the fact** (M40.6.1.1). The envelope carries the artefact stored
on the suspension, verbatim, and refuses to carry anything else. The temptation is to call
`render_artefact` again for the member surface, which agrees with itself in every test and
disagrees with the approval the moment a stored action has been edited, which is the exact
case `action_digest` exists to catch. The test constructs that disagreement.

**A stated default of doing nothing** (M40.6.1.3), and **the test drives `brain.gate.leash.
resume` with a recording executor and asserts it was never called**. A constant saying
nothing happens is worth nothing next to the thing that would have run, and the whole content
of this leaf is that the thing does not run.

**One answer from either surface** (M40.6.1.4). The same person answering the same way twice
is the second surface catching up and comes back as `already`; a different answer, or a
different person, is refused with what really happened. And both surfaces run the one
function that asks `brain.gate.admission.verbs_for_channel`, so a chat channel is not a
weaker way in to the same decision than the console.

Real `Action`s, a real `ToolDefinition`, real `SuspendedAction`s through `brain.gate.leash.
suspend`, and a real `EntitlementSet`. Nothing here builds a suspension by hand, because the
window rules and the digest are the machinery the surface sits on and a hand-built one would
be testing this file's idea of a suspension.

Task ids: M40.6.1.1, M40.6.1.3, M40.6.1.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import (
    Action,
    ApprovalState,
    Leash,
    LeashEntry,
    ResumeRefusal,
    SuspendedAction,
    decide,
    resume,
    suspend,
)
from brain.member.approvals import (
    DEFAULT_ON_EXPIRY,
    EFFECT_SENTENCES,
    Envelope,
    Lapse,
    MemberApprovalError,
    answer_once,
    approvals_gaps,
    awaiting,
    effect_sentence,
    envelope_for,
    lapsed,
)

NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)
CLEAN = RiskAssessment(score=0, matched=())

ME = "u_me"
THEM = "u_them"
AGENT = "ag_support"
TARGET = "ticket.update_status"


# ------------------------------------------------------------------------- fixtures
class Ticket(Entity):
    status: str = ""


UPDATE_STATUS = ToolDefinition(
    name="ticket.update_status",
    description="Set the status of a support ticket",
    entity="ticket",
    required_capability="write:ticket.status",
    side_effect=SideEffect.WRITE,
    identity_mode=IdentityMode.DELEGATED,
)

POLICY = FieldPolicy(
    rules=(FieldRule.of("ticket", "status", "read:ticket.status", Classification.INTERNAL),)
)


def entitlement(*values: str, principal_id: str = ME, scope: Scope | None = None) -> EntitlementSet:
    where = scope if scope is not None else Scope.unrestricted()
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=Capability(value=one), scope=where) for one in values),
    )


CALLER = entitlement("write:ticket.status", "read:ticket.status")
CEILING = entitlement("write:ticket.status", "read:ticket.status", principal_id=AGENT)

#: An approver holding the capability the action needs, which is what `pending_for` filters on.
APPROVER = entitlement("write:ticket.status", principal_id="u_approver")

#: An approver holding it only in another department, so the scope half of the filter bites.
ELSEWHERE = entitlement(
    "write:ticket.status",
    principal_id="u_finance",
    scope=Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),)),
)


def action(*, args: dict[str, str] | None = None) -> Action:
    return Action(
        agent_id=AGENT,
        tool=UPDATE_STATUS,
        target=TARGET,
        touched_fields=("status",),
        row={"department": "maintenance"},
        args=args if args is not None else {"status": "closed"},
    )


def leash_at(rung: AutonomyTier) -> Leash:
    return Leash(
        entries=(
            LeashEntry(
                agent_id=AGENT,
                target=TARGET,
                scope=Scope.unrestricted(),
                rung=rung,
            ),
        )
    )


def suspension(
    *,
    subject: Action | None = None,
    now: datetime = NOW,
    window: timedelta = timedelta(hours=4),
    suspension_id: str = "sus_1",
) -> SuspendedAction:
    """A real suspension, through the gate's own `decide` and `suspend`."""
    here = subject if subject is not None else action()
    decision = decide(
        here,
        caller=CALLER,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=leash_at(AutonomyTier.ASSISTED),
        assessment=CLEAN,
        now=now,
    )
    return suspend(
        here,
        decision,
        principal_id=ME,
        trace_id="tr_1",
        now=now,
        window=window,
        suspension_id=suspension_id,
    )


class Executor:
    """A recording executor, so "nothing happens" can be asserted on the thing that would."""

    def __init__(self) -> None:
        self.ran: list[Action] = []

    def __call__(self, subject: Action) -> TypedResult[Ticket]:
        self.ran.append(subject)
        return TypedResult[Ticket](
            records=(Ticket(entity="ticket", id="t_9", status="closed"),), source="ticket_store"
        )


# ------------------------------------------- M40.6.1.1 what will happen, stated before
def test_an_envelope_shows_the_artefact_that_was_stored_and_never_a_new_one() -> None:
    """**The claim `brain.gate.leash` makes about its own artefact, kept on this surface.** An
    approval of a re-rendered artefact is an approval of something nobody read.

    Delete this and the member surface can call `render_artefact` again, which agrees with
    itself in every test and disagrees with the approval the moment a stored action has been
    edited."""
    waiting = suspension()

    envelope = envelope_for(waiting)

    assert envelope.what_will_happen == waiting.artefact
    assert "status: closed" in envelope.what_will_happen
    assert envelope.expires_at == waiting.expires_at


def test_an_envelope_showing_anything_but_the_stored_artefact_is_refused() -> None:
    """The guard, reached by constructing the disagreement rather than by trusting the
    constructor above never to produce it. A row loaded from a table has been through no
    constructor of ours.

    Delete this and `Envelope` can be built from a re-rendered string with nothing failing."""
    waiting = suspension()

    with pytest.raises(ValueError, match="other than the artefact"):
        Envelope(
            suspension=waiting,
            what_will_happen=waiting.artefact + " (tidied up)",
            effect=effect_sentence(SideEffect.WRITE),
        )


def test_an_envelope_describing_the_wrong_effect_is_refused() -> None:
    """The consequence on the screen has to be the consequence of the action. An envelope
    that said "nothing changes" over an action that sends a message is the worst possible
    thing to put in front of somebody who is about to press approve.

    Delete this and the two can drift apart, and nothing reads the side effect again."""
    waiting = suspension()

    with pytest.raises(ValueError, match="not the consequence of the action"):
        Envelope(
            suspension=waiting,
            what_will_happen=waiting.artefact,
            effect=effect_sentence(SideEffect.NONE),
        )


def test_an_envelope_with_no_stated_consequence_of_not_answering_is_refused() -> None:
    """A space rather than only an empty string, because a template that renders nothing
    produces whitespace and `" "` passes a bare falsiness check.

    An approval request with a deadline and no stated consequence reads as a threat, and
    somebody under time pressure approves it to make it go away.

    Delete this and the deadline can appear on its own."""
    waiting = suspension()

    with pytest.raises(ValueError, match="reads as a threat"):
        Envelope(
            suspension=waiting,
            what_will_happen=waiting.artefact,
            effect=effect_sentence(SideEffect.WRITE),
            if_nothing_happens=" ",
        )


def test_every_side_effect_has_a_sentence_somebody_can_act_on() -> None:
    """Exhaustive over the enumeration rather than over the mapping, so a sixth member is a
    failing test rather than an envelope with a blank line where the consequence should be.

    The pair that matters is `write` and `send`: a record changing and a message leaving the
    building are different decisions, and an envelope that blurred them would be asking for
    an approval of the wrong thing.

    Delete this and a new side effect ships with no member-facing words at all."""
    assert set(EFFECT_SENTENCES) == set(SideEffect)
    assert all(EFFECT_SENTENCES[one].strip() for one in SideEffect)
    assert EFFECT_SENTENCES[SideEffect.WRITE] != EFFECT_SENTENCES[SideEffect.SEND]
    assert approvals_gaps() == ()


def test_the_queue_holds_what_this_approver_may_decide_and_nothing_else() -> None:
    """`brain.console.role_surfaces.pending_for` is the filter, called rather than rewritten,
    so the member queue and the console queue cannot disagree about who may decide what. The
    approver in another department holds the same capability and a narrower scope, and the
    scope half is what leaves them out.

    Delete this and the member surface acquires its own idea of who may approve, which is
    where the role would creep back in."""
    waiting = suspension()

    mine = awaiting(APPROVER, (waiting,), NOW)
    theirs = awaiting(ELSEWHERE, (waiting,), NOW)

    assert [one.suspension.id for one in mine] == ["sus_1"]
    assert theirs == ()
    assert mine[0].if_nothing_happens == DEFAULT_ON_EXPIRY


def test_the_queue_returns_no_count_of_what_it_withheld() -> None:
    """One value, for the reason every listing in this system returns one: a count of what
    was withheld is a census of the other departments' work.

    Delete this and a helpful "and 3 more you cannot see" arrives on a member page."""
    waiting = suspension()

    assert isinstance(awaiting(ELSEWHERE, (waiting,), NOW), tuple)
    assert awaiting(ELSEWHERE, (waiting,), NOW) == ()


# --------------------------------------------- M40.6.1.3 nobody answered, nothing happens
def test_an_unanswered_approval_does_not_run_when_it_expires() -> None:
    """**The leaf, asserted on the thing that would have run.** A constant saying nothing
    happens proves nothing; a recording executor that was never called does.

    The suspension is approved first, so this is the strongest case: an approval that was
    granted and then sat past its window still executes nothing.

    Delete this and the stated default becomes a promise with no mechanism, and the mechanism
    is the only part anybody depends on."""
    executor = Executor()
    approved = suspension().approved_by("u_approver", NOW + timedelta(minutes=1))
    later = NOW + timedelta(hours=5)

    outcome = resume(
        approved,
        caller=CALLER,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=leash_at(AutonomyTier.ASSISTED),
        assessment=CLEAN,
        trace_id="tr_1",
        now=later,
        execute=executor,
    )

    assert outcome.resumed is False
    assert outcome.refusal is ResumeRefusal.EXPIRED
    assert executor.ran == []


def test_an_approved_envelope_inside_its_window_does_run() -> None:
    """The positive half, without which the test above is satisfied by a `resume` that never
    executes anything, and the expiry would be proving nothing at all.

    Delete this and "nothing happens on expiry" is indistinguishable from "nothing ever
    happens"."""
    executor = Executor()
    approved = suspension().approved_by("u_approver", NOW + timedelta(minutes=1))

    outcome = resume(
        approved,
        caller=CALLER,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=leash_at(AutonomyTier.ASSISTED),
        assessment=CLEAN,
        trace_id="tr_1",
        now=NOW + timedelta(minutes=2),
        execute=executor,
    )

    assert outcome.resumed is True
    assert len(executor.ran) == 1


def test_what_lapsed_is_narrowed_by_the_same_predicate_the_queue_uses() -> None:
    """The lapse list is the queue's list one moment later, so it is narrowed by asking
    `pending_for` at the moment each envelope was raised, when it was open. A second
    capability-and-scope check written here would be a second answer to who may see an
    envelope, on the surface where nobody would look for it.

    Delete this and the lapse notice tells somebody about work in a department they cannot
    see."""
    waiting = suspension()
    later = NOW + timedelta(hours=5)

    mine = lapsed(APPROVER, (waiting,), later)
    theirs = lapsed(ELSEWHERE, (waiting,), later)

    assert [one.suspension_id for one in mine] == ["sus_1"]
    assert mine[0].what_happened == DEFAULT_ON_EXPIRY
    assert mine[0].expired_at == waiting.expires_at
    assert theirs == ()


def test_an_envelope_still_inside_its_window_has_not_lapsed() -> None:
    """The positive half of the expiry filter. Without it, `lapsed` reporting everything
    would pass every assertion above.

    Delete this and a member is told an envelope lapsed while it is still on their queue."""
    waiting = suspension()

    assert lapsed(APPROVER, (waiting,), NOW + timedelta(minutes=1)) == ()
    assert awaiting(APPROVER, (waiting,), NOW + timedelta(minutes=1)) != ()


def test_an_envelope_that_was_answered_and_then_expired_is_not_reported_as_lapsed() -> None:
    """Reporting it would tell somebody nothing happened when a decision is exactly what did,
    and a rejection is a decision worth remembering.

    **This asserts the property and no longer names the clause that enforced it.** `lapsed`
    carried an explicit `state is PENDING` test, and a mutation showed it dead: `pending_for`
    reaches `SuspendedAction.is_open`, which reads the state as it stands rather than as it
    stood, so a decided envelope is already refused by the narrowing. The clause is gone and
    this test stays, because the property must hold however it is enforced.

    Delete this and every decided envelope reappears as a lapse the moment its window
    passes."""
    rejected = suspension().rejected_by("u_approver", NOW + timedelta(minutes=1))
    later = NOW + timedelta(hours=5)

    assert lapsed(APPROVER, (rejected,), later) == ()
    assert rejected.state is ApprovalState.REJECTED


def test_a_lapse_naming_no_envelope_is_refused() -> None:
    """A space as well as an empty string. A lapse notice with no id tells the reader that
    something expired and gives them no way to find out what, which is a notification whose
    only content is anxiety.

    Delete this and a delivery path can render a blank notice."""
    with pytest.raises(ValueError, match="naming no envelope"):
        Lapse(suspension_id=" ", expired_at=NOW)


def test_a_lapse_carries_no_artefact() -> None:
    """A lapse is delivered, and the artefact carries the action's argument values, so a
    lapse carrying it would put those values into whatever channel it went out on.
    `brain.gate.leash.ActionRecord` makes the same split.

    Delete this and the notice quotes what somebody was about to do to a customer record."""
    named = set(Lapse(suspension_id="sus_1", expired_at=NOW).__dict__)

    assert named == {"suspension_id", "expired_at", "what_happened"}


# --------------------------------------------------- M40.6.1.4 one answer, either surface
def test_answering_the_same_way_twice_from_two_surfaces_is_one_approval() -> None:
    """**The leaf.** They pressed the button on their phone and then opened the page. The
    second answer reports `already` and applies nothing, rather than erroring at somebody who
    did nothing wrong or recording a second decision.

    The decided artefact is returned unchanged on the repeat, so the page shows who decided
    it and when, which is the same information both surfaces had.

    Delete this and a Lark button and an open browser tab produce an error between them every
    time."""
    waiting = suspension()

    first = answer_once(
        waiting,
        answer=ApprovalState.APPROVED,
        who="u_approver",
        channel=Channel.LARK,
        at=NOW + timedelta(minutes=1),
    )
    second = answer_once(
        first.suspension,
        answer=ApprovalState.APPROVED,
        who="u_approver",
        channel=Channel.CONSOLE,
        at=NOW + timedelta(minutes=2),
    )

    assert first.already is False
    assert first.suspension.state is ApprovalState.APPROVED
    assert first.suspension.decided_by == "u_approver"
    assert second.already is True
    assert second.suspension is first.suspension
    assert second.suspension.decided_at == NOW + timedelta(minutes=1)


def test_a_different_answer_to_a_decided_envelope_is_refused_with_what_happened() -> None:
    """Idempotence cannot smooth over two people pressing different buttons, and the honest
    answer names the decision that stands.

    Delete this and the second press quietly overwrites the first, or quietly does nothing
    while reporting success."""
    approved = answer_once(
        suspension(),
        answer=ApprovalState.APPROVED,
        who="u_approver",
        channel=Channel.CONSOLE,
        at=NOW + timedelta(minutes=1),
    ).suspension

    with pytest.raises(MemberApprovalError, match="already approved"):
        answer_once(
            approved,
            answer=ApprovalState.REJECTED,
            who="u_approver",
            channel=Channel.CONSOLE,
            at=NOW + timedelta(minutes=2),
        )


def test_somebody_elses_answer_is_not_this_persons_repeat() -> None:
    """The `already` path is the same person catching up on another surface, not anybody
    agreeing with a decision already made. Without the identity comparison, a second approver
    pressing approve would be told their action succeeded when it did nothing.

    Delete this and two approvers both believe they made the decision."""
    approved = answer_once(
        suspension(),
        answer=ApprovalState.APPROVED,
        who="u_approver",
        channel=Channel.CONSOLE,
        at=NOW + timedelta(minutes=1),
    ).suspension

    with pytest.raises(MemberApprovalError, match="already approved"):
        answer_once(
            approved,
            answer=ApprovalState.APPROVED,
            who="u_second",
            channel=Channel.CONSOLE,
            at=NOW + timedelta(minutes=2),
        )


def test_an_envelope_cannot_be_answered_from_a_channel_that_may_not_approve() -> None:
    """**Both surfaces run this function, so there is one place the channel rule can be
    wrong.** A web surface that checks it and a chat surface that trusts its own webhook make
    the chat surface a weaker way in to the same decision.

    WhatsApp is the case worth naming: a message is not a signature, which is
    `brain.gate.admission`'s own words.

    Delete this and an envelope is answerable from whichever channel delivered it."""
    waiting = suspension()

    with pytest.raises(MemberApprovalError, match="cannot be answered from whatsapp"):
        answer_once(
            waiting,
            answer=ApprovalState.APPROVED,
            who="u_approver",
            channel=Channel.WHATSAPP,
            at=NOW + timedelta(minutes=1),
        )


def test_the_channel_is_checked_before_the_state_of_the_envelope_is_read() -> None:
    """Ordering, and it is a disclosure decision rather than tidiness: answering the state
    question first would tell an unauthorised channel whether the envelope exists and what
    was done with it.

    Delete this and a channel that may not approve learns the state of every envelope it is
    handed."""
    decided = suspension().approved_by("u_approver", NOW + timedelta(minutes=1))

    with pytest.raises(MemberApprovalError, match="cannot be answered from whatsapp"):
        answer_once(
            decided,
            answer=ApprovalState.APPROVED,
            who="u_approver",
            channel=Channel.WHATSAPP,
            at=NOW + timedelta(minutes=2),
        )


def test_pending_is_not_an_answer() -> None:
    """`ApprovalState` has three members and only two of them are answers. Without this a
    caller passing the state it read off the envelope would set it back to pending, which is
    an undo nobody designed.

    Delete this and an envelope can be answered into the state it was already in, from any
    surface, with no record that anything happened."""
    with pytest.raises(MemberApprovalError, match="is not an answer"):
        answer_once(
            suspension(),
            answer=ApprovalState.PENDING,
            who="u_approver",
            channel=Channel.CONSOLE,
            at=NOW + timedelta(minutes=1),
        )


def test_an_expired_envelope_cannot_be_answered_and_says_what_happened_instead() -> None:
    """The refusal carries the stated default, because somebody who has just tried to approve
    something is exactly the person who needs to know that nothing was done.

    Delete this and the deadline is enforced with a message that reads like a system error."""
    waiting = suspension()

    with pytest.raises(MemberApprovalError, match="expired at"):
        answer_once(
            waiting,
            answer=ApprovalState.APPROVED,
            who="u_approver",
            channel=Channel.CONSOLE,
            at=NOW + timedelta(hours=5),
        )


def test_an_envelope_can_be_rejected_as_well_as_approved() -> None:
    """The other answer, and the positive half of the state machine. A surface tested only on
    approve is one where reject can be wired to the same call.

    Delete this and rejecting could approve."""
    rejected = answer_once(
        suspension(),
        answer=ApprovalState.REJECTED,
        who="u_approver",
        channel=Channel.LARK,
        at=NOW + timedelta(minutes=1),
    )

    assert rejected.already is False
    assert rejected.suspension.state is ApprovalState.REJECTED
    assert rejected.suspension.decided_by == "u_approver"


def test_answering_leaves_the_original_envelope_untouched() -> None:
    """`SuspendedAction` copies rather than mutates, so what was shown and what was decided
    are two records. A member surface that returned the same object would let a decision
    reach back into the queue somebody else is still reading.

    Delete this and the two records become one overwritten one."""
    waiting = suspension()

    answered = answer_once(
        waiting,
        answer=ApprovalState.APPROVED,
        who="u_approver",
        channel=Channel.CONSOLE,
        at=NOW + timedelta(minutes=1),
    )

    assert waiting.state is ApprovalState.PENDING
    assert answered.suspension is not waiting


def test_the_diagnostic_reports_an_envelope_that_shows_the_wrong_thing() -> None:
    """`approvals_gaps` exercised against an envelope that arrived some other way, which is
    what a row loaded from a table is and the only state it has anything to say about.

    Built through `object.__setattr__` on a frozen dataclass, because the constructor refuses
    exactly this and the diagnostic exists for the objects that did not go through it.

    Delete this and the diagnostic only ever runs on inputs a constructor already vetted,
    where switching off its checks changes nothing observable."""
    envelope = envelope_for(suspension())
    object.__setattr__(envelope, "what_will_happen", "something else entirely")
    object.__setattr__(envelope, "if_nothing_happens", " ")

    found = approvals_gaps((envelope,))

    assert any("other than the stored" in one for one in found)
    assert any("states no consequence" in one for one in found)


def test_the_diagnostic_is_quiet_about_an_envelope_the_constructor_built() -> None:
    """The positive half, without which the diagnostic above is satisfied by one that reports
    everything and the deployment check becomes noise.

    Delete this and `approvals_gaps` can complain about correct envelopes."""
    assert approvals_gaps((envelope_for(suspension()),)) == ()


def test_the_diagnostic_reports_a_side_effect_with_no_sentence_behind_it() -> None:
    """**The test for the test, and it changed the function.** `approvals_gaps` read
    `EFFECT_SENTENCES` off the module first, and that mapping is complete, so the loop could
    never report anything and switching it off changed nothing any test could see.

    An incomplete mapping is handed in instead. The finding names the member with nothing
    behind it, which is the diagnostic a sixth side effect should produce on the day somebody
    adds one and forgets the words.

    Delete this and the exhaustiveness check goes back to being unreachable."""
    short: dict[SideEffect, str] = {
        one: EFFECT_SENTENCES[one] for one in SideEffect if one is not SideEffect.MONEY
    }

    found = approvals_gaps((), short)

    assert any("no sentence for the money side effect" in one for one in found)
    assert approvals_gaps((), EFFECT_SENTENCES) == ()


def test_the_stated_default_actually_says_that_nothing_happens() -> None:
    """The copy, asserted against its content rather than against itself. Every other test
    here compares a lapse's `what_happened` to the imported constant, which moves with it and
    is green for whatever the constant says.

    The two things the leaf requires are that nothing happens and that the action is not
    taken, and a member reads both before they answer.

    Delete this and the default can be reworded into "the action proceeds" with every other
    test in this file still passing."""
    assert "nothing happens" in DEFAULT_ON_EXPIRY
    assert "not taken" in DEFAULT_ON_EXPIRY
    assert "raise it again" in DEFAULT_ON_EXPIRY
