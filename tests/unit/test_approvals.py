"""The approval card and the four verdicts, and what each of them writes down.

Two properties carry this file. An approver reads what will happen and never how, so the card
has no field a tool call could arrive in and a test asks the class rather than a reviewer. And
a decision that took effect without being recorded is the one outcome worth preventing, so the
entry is written before the suspension moves and a refusing ledger leaves nothing decided.

The suspensions here are built the way `brain.gate.leash.suspend` builds them, through a real
`Action` with its real digest and artefact. A test that built its own would be a test of a
shape the gate never writes.

Task ids: M33.6.1.2, M33.6.1.3, M40.6.1.2
"""

from __future__ import annotations

from dataclasses import fields, make_dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import ApprovalVerdict, AuditRecorder
from brain.console.approvals import (
    CALL_SHAPED,
    ApprovalError,
    Card,
    card,
    card_gaps,
    decide,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import Action, ApprovalState, SuspendedAction, render_artefact

NOW = datetime(2027, 3, 1, 9, 0, tzinfo=UTC)
MAINTENANCE = "maintenance"
WRITE_STATUS = "write:ticket.status"


def an_action(*, row: dict[str, str] | None = None, status: str = "closed") -> Action:
    """One real action, so the digest and the artefact are the gate's own."""
    return Action(
        agent_id="agent_test",
        tool=ToolDefinition(
            name="ticket.update_status",
            description="a tool a test built so that a suspension has something real behind it",
            entity="ticket",
            required_capability=WRITE_STATUS,
            side_effect=SideEffect.WRITE,
        ),
        target="ticket",
        touched_fields=("status",),
        row=row if row is not None else {"department": MAINTENANCE},
        args={"status": status},
    )


def a_suspension(
    ident: str = "sus_1",
    *,
    action: Action | None = None,
    raised_at: datetime = NOW,
    window: timedelta = timedelta(hours=4),
    state: ApprovalState = ApprovalState.PENDING,
) -> SuspendedAction:
    """One suspension, built the way `suspend` builds one."""
    built = action if action is not None else an_action()
    return SuspendedAction(
        id=ident,
        trace_id="trace_test",
        action=built,
        principal_id="u_asker",
        ent_hash="e" * 32,
        artefact=render_artefact(built),
        action_digest=built.digest(),
        raised_at=raised_at,
        expires_at=raised_at + window,
        state=state,
    )


def an_approver(department: str = MAINTENANCE, principal: str = "u_approver") -> EntitlementSet:
    """Somebody holding the action's own capability in one department."""
    return EntitlementSet(
        principal_id=principal,
        grants=(
            Grant(
                capability=Capability(value=WRITE_STATUS),
                scope=Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),)),
            ),
        ),
    )


def a_recorder() -> AuditRecorder:
    """A recorder over a real chain, so an entry that is written is one the ledger accepted."""
    return AuditRecorder(
        AuditChain(),
        actor_id="u_approver",
        ent_hash="e" * 32,
        trace_id="trace_test",
        clock=lambda: NOW,
    )


# --- what the approver is shown (M33.6.1.2) ----------------------------------------------


def test_the_card_shows_the_artefact_exactly_as_it_was_rendered() -> None:
    """M33.6.1.2. `SuspendedAction` keeps what the person was shown with the argument beside
    it: an approval of a re-rendered artefact is an approval of something nobody read. This
    is that carried through to the card.

    Compared against the suspension's own field rather than against a string written here, so
    a card that re-rendered from the action would fail even if the renderer agreed today.

    Delete this and the card becomes a fresh render, and the day the renderer changes every
    approval in flight is for something else."""
    suspension = a_suspension()

    shown = card(suspension, an_approver(), NOW)

    assert shown is not None
    assert shown.artefact == suspension.artefact
    assert shown.suspension_id == suspension.id
    assert shown.runs_as == suspension.principal_id


def test_the_card_has_no_field_a_tool_call_could_arrive_in() -> None:
    """The other half of M33.6.1.2, asked of the class rather than of a reviewer. A tool call
    is a capability name and a row of arguments: the capability is a fact about the permission
    model and the arguments are the client's own data, on a screen whose reader was chosen for
    their authority over an action rather than their reach over that data.

    Both directions: the finder reports nothing today, and the names it looks for are real
    enough that at least one of them is what the `Action` actually calls its arguments.

    Delete this and the card grows an `args` field the first time somebody wants to see what
    is being changed, which is a reasonable thing to want and the wrong place to get it."""
    assert card_gaps() == ()
    assert {one.name for one in fields(Card)} & CALL_SHAPED == set()
    assert set(Action.model_fields) & CALL_SHAPED != set()

    # And the finder finds one when there is one. Without this the assertion above is true of
    # a function that looks at nothing, which a mutation proved it was: `card_gaps` took no
    # argument, `Card` has no call-shaped field, and both the condition and the list it
    # searches could be emptied with every test still passing.
    fake = make_dataclass("Fake", [("suspension_id", str), ("args", dict)])
    found = card_gaps(fake)

    assert len(found) == 1
    assert "Fake.args" in found[0]


def test_a_card_with_nothing_on_it_cannot_be_constructed() -> None:
    """An approver pressing approve on an empty card has approved whatever it was. The
    suspension model already requires a non-empty artefact, so this is the second door: a
    `Card` assembled by anything other than `card` cannot be blank either.

    Whitespace as well as empty, because a renderer that produced nothing produces spaces
    rather than an empty string.

    Delete this and a card built by a future caller renders as an empty box with two buttons
    under it."""
    for nothing in ("", " ", "\n"):
        with pytest.raises(ApprovalError, match="nothing on it"):
            Card(
                suspension_id="sus_1",
                artefact=nothing,
                runs_as="u_asker",
                raised_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )


def test_out_of_reach_already_decided_and_lapsed_are_one_answer() -> None:
    """Three different reasons and one `None`. An approver who could tell "not yours" from
    "already decided" has learned that the suspension exists, which is the queue's own
    disclosure rule arriving one screen along.

    All three, plus the positive case, so a function returning `None` for everything fails.

    Delete this and the card view becomes an oracle for suspensions in other departments."""
    elsewhere = a_suspension(action=an_action(row={"department": "finance"}))
    decided = a_suspension(state=ApprovalState.APPROVED)
    lapsed = a_suspension(raised_at=NOW - timedelta(days=1))
    approver = an_approver()

    assert card(elsewhere, approver, NOW) is None
    assert card(decided, approver, NOW) is None
    assert card(lapsed, approver, NOW) is None
    assert card(a_suspension(), approver, NOW) is not None


# --- deciding (M33.6.1.3, M40.6.1.2) ------------------------------------------------------


def test_every_verdict_writes_one_entry_naming_the_suspension() -> None:
    """M40.6.1.2 asks that each decision reach the ledger. All four, because a function that
    recorded three of them would pass a test that checked one.

    The subject is the suspension rather than the target: recording against the target would
    put approvals and the writes they authorised under one subject, and "who approved this"
    becomes a search through everything that ever happened to that row.

    Delete this and a verdict lands in the row and nowhere else, and the question an auditor
    asks, which is what this approver has been waving through, has no answer."""
    approver = an_approver()
    for verdict, reason, amended in (
        (ApprovalVerdict.APPROVED, "", ""),
        (ApprovalVerdict.REJECTED, "wrong_ticket", ""),
        (ApprovalVerdict.TAKEN_OVER, "did_it_myself", ""),
        (ApprovalVerdict.AMENDED, "narrowed_the_change", "a" * 64),
    ):
        result = decide(
            a_suspension(),
            approver,
            a_recorder(),
            verdict=verdict,
            now=NOW,
            reason_code=reason,
            amended_digest=amended,
        )

        assert result.entry.action is AuditAction.APPROVAL
        assert result.entry.subject == "leash:sus_1"
        assert result.entry.details["verdict"] == verdict.value


def test_approving_leaves_the_action_runnable_and_the_other_three_do_not() -> None:
    """M33.6.1.3, and the asymmetry `ApprovalVerdict` argues: four verdicts, three states.
    Taking over is not a rejection with a nicer name, and it is not an approval either,
    because the agent's action must not run.

    All four in one test, because the property is about the partition rather than about any
    one of them.

    Delete this and a take-over approves the action it was meant to replace."""
    approver = an_approver()
    outcomes = {}
    for verdict, reason, amended in (
        (ApprovalVerdict.APPROVED, "", ""),
        (ApprovalVerdict.REJECTED, "wrong_ticket", ""),
        (ApprovalVerdict.TAKEN_OVER, "did_it_myself", ""),
        (ApprovalVerdict.AMENDED, "narrowed_the_change", "a" * 64),
    ):
        result = decide(
            a_suspension(),
            approver,
            a_recorder(),
            verdict=verdict,
            now=NOW,
            reason_code=reason,
            amended_digest=amended,
        )
        outcomes[verdict] = result.suspension.state

    assert outcomes[ApprovalVerdict.APPROVED] is ApprovalState.APPROVED
    assert outcomes[ApprovalVerdict.REJECTED] is ApprovalState.REJECTED
    assert outcomes[ApprovalVerdict.TAKEN_OVER] is ApprovalState.REJECTED
    assert outcomes[ApprovalVerdict.AMENDED] is ApprovalState.REJECTED


def test_a_suspension_this_approver_is_not_offered_cannot_be_decided() -> None:
    """The queue and the decision ask the same question, through `pending_for`, so a screen
    and its queue cannot disagree about what may be decided.

    Three ways to be undecidable and the message names none of them, for the same reason the
    card returns one `None`.

    Delete this and an approver who can guess a suspension id can decide it."""
    approver = an_approver()
    for unavailable in (
        a_suspension(action=an_action(row={"department": "finance"})),
        a_suspension(state=ApprovalState.APPROVED),
        a_suspension(raised_at=NOW - timedelta(days=1)),
    ):
        with pytest.raises(ApprovalError, match="not this approver's to decide"):
            decide(
                unavailable,
                approver,
                a_recorder(),
                verdict=ApprovalVerdict.APPROVED,
                now=NOW,
            )


def test_an_amendment_needs_a_digest_that_is_not_the_originals() -> None:
    """An amendment recorded against the original's digest is an approval wearing another
    word, and it reads in the ledger as a change that was never made.

    Both failures, because a check for the missing case passes a test that only makes the
    identical one.

    Delete this and "amended" becomes a label anybody can put on an unchanged action."""
    suspension = a_suspension()
    approver = an_approver()

    with pytest.raises(ApprovalError, match="records the digest"):
        decide(
            suspension,
            approver,
            a_recorder(),
            verdict=ApprovalVerdict.AMENDED,
            now=NOW,
            reason_code="narrowed_the_change",
        )
    with pytest.raises(ApprovalError, match="nothing was amended"):
        decide(
            suspension,
            approver,
            a_recorder(),
            verdict=ApprovalVerdict.AMENDED,
            now=NOW,
            reason_code="narrowed_the_change",
            amended_digest=suspension.action_digest,
        )


def test_the_other_three_verdicts_refuse_an_amended_digest() -> None:
    """A digest on a rejection describes an action the rejection did not produce, and a
    reader finding one there would be right to think something was substituted.

    Delete this and a caller can attach any digest to any verdict, and the ledger's record of
    what was substituted stops meaning anything."""
    approver = an_approver()

    with pytest.raises(ApprovalError, match="carries no amended digest"):
        decide(
            a_suspension(),
            approver,
            a_recorder(),
            verdict=ApprovalVerdict.REJECTED,
            now=NOW,
            reason_code="wrong_ticket",
            amended_digest="b" * 64,
        )


def test_the_entry_records_the_amended_digest_and_not_the_original() -> None:
    """The difference between the two digests is what makes an amendment auditable: two
    entries naming one suspension with two digests are a record of what was asked for and
    what was allowed.

    Delete this and an amendment records the thing it replaced."""
    suspension = a_suspension()
    substituted = "c" * 64

    result = decide(
        suspension,
        an_approver(),
        a_recorder(),
        verdict=ApprovalVerdict.AMENDED,
        now=NOW,
        reason_code="narrowed_the_change",
        amended_digest=substituted,
    )

    assert result.entry.details["action_digest"] == substituted
    assert result.entry.details["action_digest"] != suspension.action_digest


def test_a_decision_recorded_against_something_that_is_not_a_digest_is_refused() -> None:
    """A decision recorded against no digest cannot be compared with the action that ran, so
    an action edited between the approval and the run would agree with its own approval
    forever. That is the failure `SuspendedAction` stores its digest to prevent, arriving
    through the ledger instead.

    Found by a mutation: every other test here passes a well-formed digest, so the check had
    never once run.

    The amendment path is used because it is the one that takes a digest from a caller. The
    other three take the suspension's own, which the model has already validated.

    Delete this and the ledger accepts an approval recorded against the word "yes"."""
    with pytest.raises(ValueError, match="not an action digest"):
        decide(
            a_suspension(),
            an_approver(),
            a_recorder(),
            verdict=ApprovalVerdict.AMENDED,
            now=NOW,
            reason_code="narrowed_the_change",
            amended_digest="not-a-digest",
        )


def test_a_rejection_without_a_reason_is_refused_and_an_approval_with_one_is_too() -> None:
    """The rule is `AuditRecorder.approval`'s and this module lets the refusal through rather
    than copying it. Asserted here because the behaviour is what a caller of this surface
    meets, and a second copy of the rule would be a second place for it to differ.

    Both directions, because the asymmetry is the decision: a rejection somebody has to act
    on needs a why, and an approval that demanded one would collect the same word forever.

    Delete this and the reason field silently becomes optional everywhere, which is the state
    it would have reached by accident."""
    approver = an_approver()

    with pytest.raises(ValueError, match="needs a reason code"):
        decide(a_suspension(), approver, a_recorder(), verdict=ApprovalVerdict.REJECTED, now=NOW)
    with pytest.raises(ValueError, match="carries no reason code"):
        decide(
            a_suspension(),
            approver,
            a_recorder(),
            verdict=ApprovalVerdict.APPROVED,
            now=NOW,
            reason_code="looked_fine",
        )


def test_a_refusing_ledger_leaves_the_suspension_undecided() -> None:
    """The entry is written before the suspension moves, and this is why. A decision that took
    effect and was not recorded is the one outcome worth preventing, and the ordering is the
    whole of the mechanism.

    Provoked through the recorder's own refusal rather than a stub that raises, so this
    asserts the real order of two real calls.

    Delete this and the suspension can be approved by a call whose ledger write failed, and
    the row and the trail disagree forever."""
    suspension = a_suspension()

    with pytest.raises(ValueError):
        decide(
            suspension,
            an_approver(),
            a_recorder(),
            verdict=ApprovalVerdict.REJECTED,
            now=NOW,
            reason_code="not a code",
        )

    assert suspension.state is ApprovalState.PENDING
    assert suspension.decided_by == ""
