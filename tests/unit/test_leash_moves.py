"""How an agent's rungs move after it is installed, held to the rules `reach_view` wrote.

Real `Leash`es, real `ActionRecord`s and `ShadowReview`s, and the real `may_raise` and
`breaker_trips`, so a rung that moves here moves on the product's own rules. Dates are pinned far
from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.

Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.leash_moves import (
    A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS,
    BREAKER_METRIC,
    RAISING_WAITS_FOR_THE_REVIEW,
    THE_EVIDENCE_DOES_NOT_MEET_THE_BAR,
    THE_PROPOSER_CANNOT_CONFIRM,
    LeashMove,
    LeashMoveError,
    Record,
    breaker_for,
    effective_leash,
    held_while_supervised,
    history,
    lowering,
    raising,
    record_since,
    rung_of,
    takeover_demotions,
)
from brain.agents.supervision import ShadowReview
from brain.audit.record import ApprovalVerdict
from brain.console.reach_view import (
    MINIMUM_AGREEMENT_RATE,
    MINIMUM_CLEAN_RUNS,
    PromotionEvidence,
)
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.abstain import TAKEOVER_DEMOTION_THRESHOLD, TAKEOVER_WINDOW, AutonomyBreaker
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ActionRecord, Leash, LeashEntry, Route
from brain.tables.leash import MoveKind, PinOutcome

AGENT = "quoting"
AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
EVERYWHERE = Scope.unrestricted()
SALES = Scope.department("sales")

LEASH = Leash(
    entries=(
        LeashEntry(
            agent_id=AGENT, target="quote.send", scope=EVERYWHERE, rung=AutonomyTier.ASSISTED
        ),
        LeashEntry(agent_id=AGENT, target="quote.send", scope=SALES, rung=AutonomyTier.SHADOW),
        LeashEntry(
            agent_id="other", target="quote.send", scope=EVERYWHERE, rung=AutonomyTier.AUTONOMOUS
        ),
    )
)


def digest(n: int) -> str:
    return hashlib.sha256(str(n).encode()).hexdigest()


def action(
    n: int, *, target: str = "quote.send", at: datetime = AT, route: Route = Route.SIMULATE
) -> ActionRecord:
    return ActionRecord(
        trace_id=f"t{n}",
        agent_id=AGENT,
        tool_name=target,
        target=target,
        principal_id="p_asker",
        ent_hash="0" * 32,
        action_digest=digest(n),
        route=route,
        tier=AutonomyTier.SHADOW,
        at=at + timedelta(minutes=n),
    )


def verdict(n: int, what: ApprovalVerdict = ApprovalVerdict.APPROVED) -> ShadowReview:
    return ShadowReview(
        agent_id=AGENT,
        action_digest=digest(n),
        verdict=what,
        reviewer_id="p_steward",
        at=AT + timedelta(days=1, minutes=n),
    )


def lowered_to(to: AutonomyTier, *, at: datetime = AT) -> LeashMove:
    """The everywhere entry lowered by a department administrator."""
    return lowering(
        LEASH, agent_id=AGENT, target="quote.send", scope=EVERYWHERE, to=to, by="p_admin", at=at
    )


def press(
    to: AutonomyTier,
    record: Record,
    *,
    effect: SideEffect = SideEffect.WRITE,
    by: str = "p_admin",
    pending: LeashMove | None = None,
    supervision: PinOutcome | None = None,
) -> LeashMove:
    """A press to raise the everywhere entry, as the move route makes one."""
    return raising(
        LEASH,
        agent_id=AGENT,
        target="quote.send",
        scope=EVERYWHERE,
        to=to,
        by=by,
        at=AT,
        effect=effect,
        record=record,
        pending=pending,
        supervision=supervision,
    )


def test_a_move_replaces_its_own_entry_and_leaves_every_other_entry_alone() -> None:
    """**M39.3.2.1.** Lowering one agent's everywhere entry changes that entry and nothing else: the
    narrower sales entry and another agent's entry keep their rungs, so the strictest of
    overlapping entries still wins in sales. A key the install never named is added. Delete this
    and a move either lands as a second entry, which a raise could never beat, or rewrites a
    neighbour."""
    down = lowered_to(AutonomyTier.SHADOW)
    after = effective_leash(LEASH, [down])

    assert rung_of(after, AGENT, "quote.send", EVERYWHERE) is AutonomyTier.SHADOW
    assert rung_of(after, AGENT, "quote.send", SALES) is AutonomyTier.SHADOW
    assert rung_of(after, "other", "quote.send", EVERYWHERE) is AutonomyTier.AUTONOMOUS
    assert len(after.entries) == len(LEASH.entries)
    unknown = LeashMove(
        agent_id=AGENT,
        target="invoice.pay",
        scope=EVERYWHERE,
        was=AutonomyTier.ASSISTED,
        became=AutonomyTier.SHADOW,
        kind=MoveKind.LOWERED,
        at=AT,
        changed_by="p_admin",
    )
    added = effective_leash(LEASH, [unknown])
    assert rung_of(added, AGENT, "invoice.pay", EVERYWHERE) is AutonomyTier.SHADOW
    assert added.rung_for(AGENT, "quote.send", {"department": "sales"}) is AutonomyTier.SHADOW


def test_the_newest_move_for_a_key_wins_and_a_proposal_moves_nothing() -> None:
    """Delete this and the rung a key stands at depends on the order rows were read, or a proposal
    waiting for its second person raises the rung on its own."""
    first = lowered_to(AutonomyTier.SHADOW)
    later = LeashMove(
        agent_id=AGENT,
        target="quote.send",
        scope=EVERYWHERE,
        was=AutonomyTier.SHADOW,
        became=AutonomyTier.ASSISTED,
        kind=MoveKind.RAISED,
        at=AT + timedelta(hours=1),
        changed_by="p_admin",
        promotion=raised_evidence(),
    )
    proposal = LeashMove(
        agent_id=AGENT,
        target="quote.send",
        scope=EVERYWHERE,
        was=AutonomyTier.ASSISTED,
        became=AutonomyTier.AUTONOMOUS,
        kind=MoveKind.PROPOSED,
        at=AT + timedelta(hours=2),
        changed_by="p_admin",
        irreversible=True,
        promotion=raised_evidence(),
    )

    assert (
        rung_of(effective_leash(LEASH, [later, first]), AGENT, "quote.send", EVERYWHERE)
        is AutonomyTier.ASSISTED
    )
    assert (
        rung_of(effective_leash(LEASH, [first, later, proposal]), AGENT, "quote.send", EVERYWHERE)
        is AutonomyTier.ASSISTED
    )
    assert [one.kind for one in history([proposal, later, first])] == [
        MoveKind.LOWERED,
        MoveKind.RAISED,
        MoveKind.PROPOSED,
    ]


def raised_evidence() -> PromotionEvidence:
    return PromotionEvidence(
        clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, approver_id="p_admin"
    )


def test_a_rise_is_counted_from_what_people_said_since_the_key_last_moved() -> None:
    """**M39.3.2.2.** Clean runs are the unbroken run of accepted verdicts back from the newest, the
    agreement is the share accepted, and neither counts an action before the key last moved, another
    target's, or one nobody judged. Delete this and a rise can be earned on another target's record
    or on a history the last demotion should have wiped."""
    actions = [action(n) for n in range(12)] + [action(99, target="invoice.pay")]
    verdicts = (
        [verdict(0, ApprovalVerdict.AMENDED)] + [verdict(n) for n in range(1, 11)] + [verdict(99)]
    )

    everything = record_since(AGENT, "quote.send", actions=actions, verdicts=verdicts, since=None)
    later = record_since(
        AGENT, "quote.send", actions=actions, verdicts=verdicts, since=AT + timedelta(minutes=5)
    )

    assert everything == Record(clean_runs=10, agreement_rate=10 / 11, reviewed=11)
    assert later == Record(clean_runs=6, agreement_rate=1.0, reviewed=6)
    assert record_since(AGENT, "quote.send", actions=actions, verdicts=[], since=None) == Record(
        0, 0.0, 0
    )


def test_a_rise_needs_the_bar_and_a_named_approver_and_a_lowering_needs_nothing() -> None:
    """**M39.3.2.2.** Below the bar a rise is refused in words naming no figure; at the bar it is a
    raise naming the person who pressed; a lowering asks for no evidence at all, and a press that
    does not move in its own direction is refused. Delete this and a rung rises on a thin record, or
    lowering one in an incident needs paperwork."""
    thin = Record(
        clean_runs=MINIMUM_CLEAN_RUNS - 1, agreement_rate=1.0, reviewed=MINIMUM_CLEAN_RUNS - 1
    )
    good = Record(clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=MINIMUM_AGREEMENT_RATE, reviewed=12)
    with pytest.raises(LeashMoveError, match="does not yet meet the bar") as refused:
        press(AutonomyTier.AUTONOMOUS, thin)
    assert str(refused.value) == THE_EVIDENCE_DOES_NOT_MEET_THE_BAR
    up = press(AutonomyTier.AUTONOMOUS, good)
    assert (up.kind, up.was, up.became) == (
        MoveKind.RAISED,
        AutonomyTier.ASSISTED,
        AutonomyTier.AUTONOMOUS,
    )
    assert up.promotion is not None and up.promotion.approver_id == "p_admin"
    down = lowered_to(AutonomyTier.SHADOW)
    assert (down.kind, down.promotion) == (MoveKind.LOWERED, None)
    with pytest.raises(LeashMoveError):
        lowered_to(AutonomyTier.AUTONOMOUS)
    with pytest.raises(LeashMoveError):
        press(AutonomyTier.ASSISTED, good)


def test_a_money_rise_is_a_proposal_then_a_second_persons_raise_naming_both() -> None:
    """**M39.3.2.4.** Across a money boundary the first press is a proposal that moves nothing, the
    proposer's own second press is refused, and another person's press is the raise naming both.
    Delete this and one person can move an agent that spends money onto its own."""
    good = Record(clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, reviewed=10)
    proposal = press(AutonomyTier.AUTONOMOUS, good, effect=SideEffect.MONEY, by="p_first")
    assert (proposal.kind, proposal.irreversible) == (MoveKind.PROPOSED, True)
    assert (
        rung_of(effective_leash(LEASH, [proposal]), AGENT, "quote.send", EVERYWHERE)
        is AutonomyTier.ASSISTED
    )
    with pytest.raises(LeashMoveError) as own:
        press(
            AutonomyTier.AUTONOMOUS, good, effect=SideEffect.MONEY, by="p_first", pending=proposal
        )
    assert str(own.value) == THE_PROPOSER_CANNOT_CONFIRM
    raised = press(
        AutonomyTier.AUTONOMOUS, good, effect=SideEffect.MONEY, by="p_second", pending=proposal
    )
    assert raised.kind is MoveKind.RAISED
    assert raised.promotion is not None
    assert (raised.promotion.approver_id, raised.promotion.second_approver_id) == (
        "p_first",
        "p_second",
    )
    with pytest.raises(LeashMoveError):
        LeashMove(
            agent_id=AGENT,
            target="quote.send",
            scope=EVERYWHERE,
            was=AutonomyTier.ASSISTED,
            became=AutonomyTier.AUTONOMOUS,
            kind=MoveKind.RAISED,
            at=AT,
            changed_by="p_first",
            irreversible=True,
            promotion=proposal.promotion,
        )


def test_the_breaker_trips_below_the_bar_names_its_metric_and_not_at_the_bottom() -> None:
    """**M39.3.2.3.** Above the bottom rung, agreement below the bar trips with the metric, its
    figure and the threshold; at the bar it holds; at the bottom or with nothing judged it never
    trips. Delete this and a rung that fell cannot say why, or one is demoted on no evidence."""
    below = Record(clean_runs=0, agreement_rate=0.5, reviewed=2)
    at_bar = Record(clean_runs=9, agreement_rate=MINIMUM_AGREEMENT_RATE, reviewed=10)

    trip = breaker_for(AutonomyTier.AUTONOMOUS, below, at=AT)
    assert trip is not None
    assert (trip.metric, trip.measured, trip.threshold) == (
        BREAKER_METRIC,
        0.5,
        MINIMUM_AGREEMENT_RATE,
    )
    assert breaker_for(AutonomyTier.AUTONOMOUS, at_bar, at=AT) is None
    assert breaker_for(AutonomyTier.SHADOW, below, at=AT) is None
    assert breaker_for(AutonomyTier.ASSISTED, Record(0, 0.0, 0), at=AT) is None


def test_a_supervised_agent_is_held_down_and_cannot_rise_until_its_review_found_it_ready() -> None:
    """**M39.8.2.** Pinned or extended, every one of this agent's rungs is held at the bottom and a
    rise is refused; eligible, the configured rungs stand and a rise is judged on its evidence.
    Another agent is never held. Delete this and a date passing ends supervision, or one pin holds
    the estate."""
    good = Record(clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, reviewed=10)
    for outcome in (PinOutcome.PINNED, PinOutcome.EXTENDED):
        held = held_while_supervised(LEASH, AGENT, outcome)
        assert rung_of(held, AGENT, "quote.send", EVERYWHERE) is AutonomyTier.SHADOW
        assert rung_of(held, "other", "quote.send", EVERYWHERE) is AutonomyTier.AUTONOMOUS
        with pytest.raises(LeashMoveError) as waits:
            raising(
                LEASH,
                agent_id=AGENT,
                target="quote.send",
                scope=EVERYWHERE,
                to=AutonomyTier.AUTONOMOUS,
                by="p_admin",
                at=AT,
                effect=SideEffect.WRITE,
                record=good,
                pending=None,
                supervision=outcome,
            )
        assert str(waits.value) == RAISING_WAITS_FOR_THE_REVIEW
    assert held_while_supervised(LEASH, AGENT, PinOutcome.ELIGIBLE) == LEASH
    assert held_while_supervised(LEASH, AGENT, None) == LEASH
    assert (
        raising(
            LEASH,
            agent_id=AGENT,
            target="quote.send",
            scope=EVERYWHERE,
            to=AutonomyTier.AUTONOMOUS,
            by="p_admin",
            at=AT,
            effect=SideEffect.WRITE,
            record=good,
            pending=None,
            supervision=PinOutcome.ELIGIBLE,
        ).kind
        is MoveKind.RAISED
    )


# ------------------------------------------------------------------ the takeover breaker
def standing(*instants: datetime, target: str = "quote.send") -> AutonomyBreaker:
    """The breaker for the agent on one target, holding these takeover instants."""
    return AutonomyBreaker(agent_id=AGENT, target=target, takeovers=tuple(sorted(instants)))


def test_a_raised_rung_is_held_lower_while_people_keep_taking_its_work_over() -> None:
    """**The lower rung binds**, by `leash_moves`' reason constant. A rung raised to Autonomous on
    its record, on a target people took the work of over three times this week, is held a step
    lower and shown so, with the earliest instant the takeovers inside the week hold it down and
    how many there are, one older than the week counted by neither; the gate's own leash with the
    gate's own breaker agrees. Once the takeovers leave the week the raise binds and no demotion
    is shown. Delete this and a raise made while the breaker is open reads as having taken effect,
    or a demotion is drawn after the week that caused it is over."""
    good = Record(clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=MINIMUM_AGREEMENT_RATE, reviewed=12)
    raised = effective_leash(LEASH, [press(AutonomyTier.AUTONOMOUS, good)])
    now = AT + timedelta(days=2)
    instants = [AT + timedelta(hours=n) for n in (1, 2, 3, 4)]
    aged_out = now - TAKEOVER_WINDOW - timedelta(hours=1)
    held = {"quote.send": standing(aged_out, *instants)}

    (demotion,) = takeover_demotions(raised, AGENT, held, now)

    assert (demotion.target, demotion.was, demotion.became) == (
        "quote.send",
        AutonomyTier.AUTONOMOUS,
        AutonomyTier.ASSISTED,
    )
    assert demotion.at == instants[TAKEOVER_DEMOTION_THRESHOLD - 1]
    assert demotion.takeovers == len(instants)
    gate = held["quote.send"].rung(raised.rung_for(AGENT, "quote.send", {}), now)
    assert gate is demotion.became
    later = instants[-1] + TAKEOVER_WINDOW + timedelta(minutes=1)
    assert takeover_demotions(raised, AGENT, held, later) == ()
    assert (
        "lower of the two" in A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS
    )


def test_no_demotion_is_shown_below_the_threshold_at_the_bottom_or_for_another_agent() -> None:
    """Two takeovers in the week lower nothing; a target already at Shadow has nowhere lower to go;
    another agent's entry on the same target is not this agent's; and a standing filed under the
    wrong target is refused rather than drawn. Delete this and the history shows a demotion the
    gate never applies, or one agent's takeovers lower another's rung on the page."""
    now = AT + timedelta(days=1)
    few = [AT + timedelta(hours=n) for n in range(TAKEOVER_DEMOTION_THRESHOLD - 1)]
    many = [AT + timedelta(hours=n) for n in range(TAKEOVER_DEMOTION_THRESHOLD)]
    bottom = effective_leash(LEASH, [lowered_to(AutonomyTier.SHADOW)])

    assert takeover_demotions(LEASH, AGENT, {"quote.send": standing(*few)}, now) == ()
    assert takeover_demotions(bottom, AGENT, {"quote.send": standing(*many)}, now) == ()
    assert takeover_demotions(LEASH, AGENT, {}, now) == ()
    (one,) = takeover_demotions(LEASH, AGENT, {"quote.send": standing(*many)}, now)
    assert (one.was, one.became) == (AutonomyTier.ASSISTED, AutonomyTier.SHADOW)
    other = Leash(entries=tuple(e for e in LEASH.entries if e.agent_id == "other"))
    assert takeover_demotions(other, AGENT, {"quote.send": standing(*many)}, now) == ()
    with pytest.raises(ValueError, match="filed under"):
        takeover_demotions(LEASH, AGENT, {"quote.send": standing(*many, target="x.y")}, now)
