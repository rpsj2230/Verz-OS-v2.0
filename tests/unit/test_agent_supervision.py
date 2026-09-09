"""A shadow pin that is reviewed, and never one that runs out.

The property under test is one sentence: **a shadow pin never expires on a timer**. Thirty
days is when the question is asked, and the answer is a measurement of how much the agent was
understood to have got right, computed from records the gate and the ledger already produce.
Below the threshold the period extends; at or above it a person may propose a rung rise.

Four failures are what these tests exist to catch, and every one of them is quiet.

**The pin lapsing.** An agent that becomes autonomous over somebody's accounts receivable
because a date passed. `test_a_due_review_on_an_unmeasured_agent_extends_the_pin_rather_than_
lifting_it` is the direct one, and the structural test on the record's own fields is the one
that stops an expiry being added back as a column beside the review date.

**The threshold being a number nobody can check.** `SHADOW_EXIT_CONFIDENCE` is asserted
against `brain.console.reach_view.MINIMUM_AGREEMENT_RATE`, which is a different module's
figure for the same bar, and against hand-computed fractions that name no constant at all:
twenty-seven of thirty clears nine tenths and twenty-six of thirty does not. CLAUDE.md records
three authors in one afternoon writing a test that compared a constant with itself and was
green for every value it could hold, and the fractions are what stop this being a fourth.

**A confidence over three runs.** `MINIMUM_REVIEWED_ACTIONS` is asserted as the property that
makes it right rather than as a number: it is the smallest denominator at which an agent can
be wrong once and still clear the bar.

**An unmeasured agent reading as a perfect one.** `Confidence.share` refuses rather than
answering zero or one, and the review of an agent nobody looked at extends the period.

**Dates are pinned in 2999 and 2019 deliberately**, as `tests/unit/test_scope_and_capability.py`
pins its own. Nothing here is about the present: every comparison is between a pin, a review
and an action, so a fixture anchored near today would be a clock that goes off on a schedule
nobody chose, which is what `test_memory_formation.py` did on the day after it was written.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents import supervision
from brain.agents.supervision import (
    HELD_AT_WHILE_SUPERVISED,
    MINIMUM_REVIEWED_ACTIONS,
    SHADOW_EXIT_CONFIDENCE,
    SHADOW_REVIEW_PERIOD,
    VERDICTS_THAT_SHOW_UNDERSTANDING,
    Confidence,
    ShadowDecision,
    ShadowOutcome,
    ShadowPin,
    ShadowReview,
    SupervisionError,
    extended,
    measure,
    pin,
    review,
    supervised_leash,
)
from brain.audit.record import ApprovalVerdict
from brain.console.reach_view import MINIMUM_AGREEMENT_RATE, MINIMUM_CLEAN_RUNS
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ActionRecord, Leash, LeashEntry, Route

# Far outside any plausible wall clock, so no fixture here is a clock. See the module
# docstring: 2019 is before every pin in this file and 2999 is after every real one.
PINNED_AT = datetime(2999, 1, 1, tzinfo=UTC)
DUE_AT = PINNED_AT + SHADOW_REVIEW_PERIOD
BEFORE_DUE = DUE_AT - timedelta(days=1)
AFTER_DUE = DUE_AT + timedelta(days=1)
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)

CHASER = "renewal_chaser"
OTHER_AGENT = "support_triage"
REVIEWER = "u_head_of_finance"
ACTED_AT = PINNED_AT + timedelta(days=2)
LOOKED_AT = PINNED_AT + timedelta(days=3)


def _digest(n: int) -> str:
    """A distinct action digest per index, in the ledger's own grammar."""
    return f"{n:064x}"


def _acted(n: int, *, agent_id: str = CHASER, at: datetime = ACTED_AT) -> ActionRecord:
    """One simulated action, as `govern` records it on the shadow route."""
    return ActionRecord(
        trace_id="t_0001",
        agent_id=agent_id,
        tool_name="invoice.draft_reminder",
        target="invoice.draft",
        principal_id="u_caller",
        ent_hash="e_0001",
        action_digest=_digest(n),
        route=Route.SIMULATE,
        tier=AutonomyTier.SHADOW,
        at=at,
    )


def _looked(
    n: int,
    verdict: ApprovalVerdict = ApprovalVerdict.APPROVED,
    *,
    agent_id: str = CHASER,
    at: datetime = LOOKED_AT,
) -> ShadowReview:
    """One person's verdict on the action `_acted(n)` produced."""
    return ShadowReview(
        agent_id=agent_id,
        action_digest=_digest(n),
        verdict=verdict,
        reviewer_id=REVIEWER,
        at=at,
    )


def _window(
    understood: int, amended: int, *, unreviewed: int = 0
) -> tuple[
    list[ActionRecord],
    list[ShadowReview],
]:
    """A window of simulated actions and the verdicts somebody gave them."""
    total = understood + amended + unreviewed
    records = [_acted(n) for n in range(total)]
    reviews = [_looked(n) for n in range(understood)]
    reviews += [
        _looked(n, ApprovalVerdict.AMENDED) for n in range(understood, understood + amended)
    ]
    return records, reviews


def _pinned() -> ShadowPin:
    return pin(CHASER, now=PINNED_AT)


# --------------------------------------------------------------- the pin cannot run out


def test_a_pin_carries_no_field_and_no_outcome_that_could_mean_supervision_ended() -> None:
    """Delete this and reading two arrives as a column.

    The whole item is that a pin is reviewed rather than expiring, and the way that gets
    undone is not somebody arguing for an expiry: it is an `expires_at` added beside
    `review_due_at` because a console wanted to show one, after which the next reader treats
    the review date as advisory. The guarantee is that there is no field to hold one and no
    outcome to spell one with, and this is what asserts it against the real objects.
    """
    ending = ("expire", "expiry", "lapse", "until", "autonom", "promot", "release", "lift")
    assert set(ShadowPin.model_fields) == {"agent_id", "pinned_at", "review_due_at"}
    for name in ShadowPin.model_fields:
        assert not any(word in name.lower() for word in ending), name
    for member in ShadowOutcome:
        assert not any(word in member.value for word in ending), member
    assert set(ShadowOutcome) == {
        ShadowOutcome.NOT_YET_DUE,
        ShadowOutcome.EXTENDED,
        ShadowOutcome.ELIGIBLE,
    }


def test_a_due_review_on_an_unmeasured_agent_extends_the_pin_rather_than_lifting_it() -> None:
    """Delete this and the pin becomes a timer.

    This is the failure the owner's decision is written against: nobody reviewed anything,
    the thirty days ran out, and the agent starts acting unwatched. The review has to come
    back extended, with a review date one full period past the day it was asked, and the
    evidence window has to still start where it started.
    """
    records = [_acted(n) for n in range(40)]
    decision = review(_pinned(), simulated=records, reviews=[], now=AFTER_DUE)

    assert decision.outcome is ShadowOutcome.EXTENDED
    assert decision.stays_supervised
    assert decision.pin.review_due_at == AFTER_DUE + SHADOW_REVIEW_PERIOD
    assert decision.pin.pinned_at == PINNED_AT
    assert decision.confidence.reviewed == 0
    assert decision.confidence.simulated == 40


def test_a_review_that_is_not_due_yet_decides_nothing_however_good_the_figure_is() -> None:
    """Delete this and thirty days becomes a suggestion.

    An agent that is perfect on day three is not eligible on day three. The period is the
    owner's and a share that could end it early would make the date meaningless in the other
    direction. The confidence is still computed, because a progress screen needs it every day.
    """
    records, reviews = _window(understood=12, amended=0)
    decision = review(_pinned(), simulated=records, reviews=reviews, now=BEFORE_DUE)

    assert decision.outcome is ShadowOutcome.NOT_YET_DUE
    assert decision.stays_supervised
    assert decision.pin == _pinned()
    assert decision.confidence.share == 1.0


def test_the_review_is_due_at_the_instant_it_is_due_and_not_a_moment_later() -> None:
    """Delete this and a review scheduled for exactly its own due date reports as early.

    The boundary is inclusive because the due date is the day the review happens, not the day
    after it, and a strict comparison makes a scheduler that fires on the date do nothing.
    """
    assert _pinned().is_due(DUE_AT) is True
    assert _pinned().is_due(DUE_AT - timedelta(seconds=1)) is False


def test_a_late_review_extends_from_the_review_and_not_from_the_date_it_was_due() -> None:
    """Delete this and a backlog can walk an agent through several reviews in an afternoon.

    Measured from the old due date, a review run forty days late produces a pin that is
    already due again, so the next call reviews the same evidence and extends again. Measured
    from the review, a late review delays the next one, which keeps the agent supervised.
    """
    very_late = DUE_AT + timedelta(days=40)
    moved = extended(_pinned(), now=very_late)

    assert moved.review_due_at == very_late + SHADOW_REVIEW_PERIOD
    assert moved.is_due(very_late) is False
    assert moved.pinned_at == PINNED_AT


def test_a_pin_whose_review_is_due_before_the_period_it_reviews_began_is_refused() -> None:
    """Delete this and a pin can be written that is due the moment it exists.

    Such a pin answers on an empty window and extends on the first call, which looks exactly
    like the system working and has thrown the thirty days away.
    """
    with pytest.raises(ValueError, match="empty window"):
        ShadowPin(agent_id=CHASER, pinned_at=PINNED_AT, review_due_at=PINNED_AT)


def test_a_naive_timestamp_is_refused_on_a_pin_and_on_a_review() -> None:
    """Delete this and an hour's drift decides whether evidence counts.

    Every comparison here is a naive-or-aware one across a window boundary, so a naive
    timestamp is not a rounding error: it is the difference between a review counting and not.
    """
    with pytest.raises(ValueError, match="timezone-aware"):
        ShadowPin(
            agent_id=CHASER,
            pinned_at=datetime(2999, 1, 1),
            review_due_at=DUE_AT,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        ShadowReview(
            agent_id=CHASER,
            action_digest=_digest(1),
            verdict=ApprovalVerdict.APPROVED,
            reviewer_id=REVIEWER,
            at=datetime(2999, 1, 4),
        )


# ------------------------------------------------------------------ ninety percent of what


def test_the_bar_for_ending_supervision_is_the_bar_a_rung_rise_already_has_to_clear() -> None:
    """Delete this and there are two different ninety percents that can drift apart.

    `brain.console.reach_view.MINIMUM_AGREEMENT_RATE` is the share a promotion's evidence has
    to show before `may_raise` will admit it. If this module's threshold moved away from it,
    a review could report an agent eligible for a promotion the console would then refuse, or
    worse, admit one the console's own bar would have stopped. Both constants are asserted
    here rather than either being asserted against itself, which is the mistake CLAUDE.md
    records three authors making in one afternoon.
    """
    assert SHADOW_EXIT_CONFIDENCE == MINIMUM_AGREEMENT_RATE
    assert MINIMUM_REVIEWED_ACTIONS == MINIMUM_CLEAN_RUNS
    assert timedelta(days=30) == SHADOW_REVIEW_PERIOD


def test_twenty_seven_of_thirty_clears_the_bar_and_twenty_six_of_thirty_does_not() -> None:
    """Delete this and the threshold can hold any value with its other tests still green.

    Every figure here is a literal fraction and none of them is the constant, so the pair of
    assertions is false for every threshold except the owner's. Twenty-seven of thirty is
    nine tenths exactly, which is the boundary, and the boundary is inclusive because at or
    above is what he decided.
    """
    assert Confidence(understood=27, reviewed=30, simulated=30).meets_the_bar() is True
    assert Confidence(understood=26, reviewed=30, simulated=30).meets_the_bar() is False
    assert Confidence(understood=9, reviewed=10, simulated=10).meets_the_bar() is True
    assert Confidence(understood=89, reviewed=99, simulated=99).meets_the_bar() is False


def test_the_minimum_denominator_is_the_smallest_one_that_survives_a_single_mistake() -> None:
    """Delete this and the floor becomes a number somebody liked.

    The floor is not a taste. At the floor an agent must be able to be wrong once and still
    clear the threshold, and one step below it a single mistake must be disqualifying: below
    that point the figure stops measuring the agent and starts measuring its luck. Asserted as
    that property, so moving either the floor or the threshold without the other fails here.
    """
    at_the_floor = Confidence(
        understood=MINIMUM_REVIEWED_ACTIONS - 1,
        reviewed=MINIMUM_REVIEWED_ACTIONS,
        simulated=MINIMUM_REVIEWED_ACTIONS,
    )
    one_below = Confidence(
        understood=MINIMUM_REVIEWED_ACTIONS - 2,
        reviewed=MINIMUM_REVIEWED_ACTIONS - 1,
        simulated=MINIMUM_REVIEWED_ACTIONS - 1,
    )
    assert at_the_floor.share >= SHADOW_EXIT_CONFIDENCE
    assert one_below.share < SHADOW_EXIT_CONFIDENCE


def test_a_perfect_share_over_too_few_actions_is_not_a_confidence() -> None:
    """Delete this and three of three promotes an agent.

    A hundred percent over three runs is the case the denominator floor exists for, and it is
    the one that looks best on a screen. Both the measurement and the review have to refuse it.
    """
    tiny = Confidence(understood=3, reviewed=3, simulated=3)
    assert tiny.share == 1.0
    assert tiny.is_measured is False
    assert tiny.meets_the_bar() is False

    records, reviews = _window(understood=3, amended=0)
    decision = review(_pinned(), simulated=records, reviews=reviews, now=AFTER_DUE)
    assert decision.outcome is ShadowOutcome.EXTENDED


def test_an_agent_nobody_reviewed_has_no_share_at_all_rather_than_none_or_all_of_one() -> None:
    """Delete this and the absence of a measurement acquires a value.

    Zero and one are both numbers somebody chose. Zero reads as fail-closed and is a claim
    that the agent was measured and was wrong every time, which is a figure a reviewer can
    argue with about an agent nobody watched. The refusal is what keeps unmeasured a third
    state instead of a low score.
    """
    unmeasured = Confidence(understood=0, reviewed=0, simulated=12)
    assert unmeasured.is_measured is False
    assert unmeasured.meets_the_bar() is False
    with pytest.raises(SupervisionError, match="no share to report"):
        _ = unmeasured.share


def test_a_confidence_cannot_be_built_from_counts_that_contradict_each_other() -> None:
    """Delete this and a share above one, or a denominator larger than what happened, is
    storable.

    The second is the one that matters: more reviewed than simulated means verdicts were
    counted against actions the agent never took, and the denominator is then whatever
    somebody filed rather than what the agent did.
    """
    with pytest.raises(SupervisionError, match="share above one"):
        Confidence(understood=11, reviewed=10, simulated=10)
    with pytest.raises(SupervisionError, match="never took"):
        Confidence(understood=5, reviewed=10, simulated=5)
    with pytest.raises(SupervisionError, match="negative"):
        Confidence(understood=-1, reviewed=10, simulated=10)


# ---------------------------------------------------- where the numbers actually come from


def test_the_measurement_counts_the_simulated_actions_a_person_gave_a_verdict_on() -> None:
    """Delete this and every refusal below is satisfied by a function that measures nothing.

    This is the positive case: a window of thirty simulated actions, twenty-seven approved,
    three amended, and ten nobody looked at. The denominator is what was reviewed, the
    population is what happened, and both come off the records rather than from a caller.
    """
    records, reviews = _window(understood=27, amended=3, unreviewed=10)
    measured = measure(_pinned(), simulated=records, reviews=reviews)

    assert measured.understood == 27
    assert measured.reviewed == 30
    assert measured.simulated == 40
    assert measured.share == 0.9


def test_only_an_approval_counts_as_the_agent_having_understood() -> None:
    """Delete this and an amendment reads as a success.

    An amended action is one a person had to change, a taken-over action is one a person did
    instead, and a rejected one should not have happened. None of the three is understanding.
    The other three members are named rather than derived, so a fifth verdict added to the
    ledger's vocabulary fails here and has to be dispositioned by somebody.
    """
    assert {ApprovalVerdict.APPROVED} == VERDICTS_THAT_SHOW_UNDERSTANDING
    assert set(ApprovalVerdict) - VERDICTS_THAT_SHOW_UNDERSTANDING == {
        ApprovalVerdict.REJECTED,
        ApprovalVerdict.TAKEN_OVER,
        ApprovalVerdict.AMENDED,
    }

    records = [_acted(n) for n in range(30)]
    reviews = [_looked(n, ApprovalVerdict.AMENDED) for n in range(30)]
    assert measure(_pinned(), simulated=records, reviews=reviews).understood == 0


def test_one_action_simulated_many_times_is_one_action() -> None:
    """Delete this and a retry loop inflates both halves of the fraction.

    An agent that simulated the same action twelve times has simulated one action. Counting
    the records rather than the distinct digests would make the population, and any share
    drawn from it, move with how often a loop happened to run.
    """
    records = [_acted(1) for _ in range(12)]
    reviews = [_looked(1)]
    measured = measure(_pinned(), simulated=records, reviews=reviews)

    assert measured.simulated == 1
    assert measured.reviewed == 1


def test_an_action_that_was_really_executed_is_not_evidence_about_a_shadow_period() -> None:
    """Delete this and a promoted agent's real work counts towards the review of its pin.

    The filter is on the route rather than on the tier because the route is what happened to
    the call. A verdict naming an executed action is then outside the population, and the
    refusal below is what the caller gets.
    """
    executed = _acted(1).model_copy(update={"route": Route.EXECUTE})
    with pytest.raises(SupervisionError, match="did not simulate"):
        measure(_pinned(), simulated=[executed], reviews=[_looked(1)])


def test_a_verdict_about_an_action_the_agent_never_simulated_is_refused() -> None:
    """Delete this and the denominator becomes whatever somebody filed.

    Refused rather than dropped, because a dropped row moves the denominator silently, and
    the same defect then reads as an agent that simply ran fewer times.
    """
    with pytest.raises(SupervisionError, match="did not simulate"):
        measure(_pinned(), simulated=[_acted(1)], reviews=[_looked(2)])


def test_a_review_dated_before_the_action_it_judges_is_refused() -> None:
    """Delete this and a row nobody produced can be counted as a person looking.

    A verdict recorded before its action is not evidence of anybody reviewing anything, and
    it lands in the numerator as readily as a real one.
    """
    too_early = _looked(1, at=ACTED_AT - timedelta(hours=1))
    with pytest.raises(SupervisionError, match="dated before the action"):
        measure(_pinned(), simulated=[_acted(1)], reviews=[too_early])


def test_two_people_disagreeing_about_one_action_is_refused_rather_than_resolved() -> None:
    """Delete this and whoever reviews last decides the share.

    Taking the later verdict is the obvious rule and it hands one reviewer the power to move
    the figure by filing again. A repeat of the same verdict is not a disagreement and stays
    admissible, because a retry after a timeout must not fail.
    """
    records = [_acted(1)]
    with pytest.raises(SupervisionError, match="contradiction in the record"):
        measure(
            _pinned(),
            simulated=records,
            reviews=[_looked(1), _looked(1, ApprovalVerdict.REJECTED)],
        )
    repeated = measure(_pinned(), simulated=records, reviews=[_looked(1), _looked(1)])
    assert repeated.reviewed == 1


def test_another_agents_actions_and_verdicts_are_not_this_agents_evidence() -> None:
    """Delete this and one agent's record can carry another out of supervision.

    Dropped rather than refused: a caller handing over everything the ledger holds is the
    normal case, and refusing it would push the filtering onto callers, which is the one step
    that must not be theirs.
    """
    records = [_acted(n) for n in range(12)] + [_acted(n, agent_id=OTHER_AGENT) for n in range(12)]
    reviews = [_looked(n, agent_id=OTHER_AGENT) for n in range(12)]
    measured = measure(_pinned(), simulated=records, reviews=reviews)

    assert measured.simulated == 12
    assert measured.reviewed == 0


def test_a_review_from_before_this_pin_is_not_evidence_about_it() -> None:
    """Delete this and a demoted agent walks straight back out on its old record.

    An agent that was promoted, went wrong and fell to the bottom rung is pinned again. The
    reviews that carried it out the first time are still in the ledger, and counting them
    would answer the review its own failure caused with the evidence that preceded the
    failure. A new pin is a new window and the old evidence is outside it.
    """
    old_records = [_acted(n, at=LONG_AGO) for n in range(30)]
    old_reviews = [_looked(n, at=LONG_AGO + timedelta(days=1)) for n in range(30)]
    repinned = pin(CHASER, now=PINNED_AT)

    decision = review(repinned, simulated=old_records, reviews=old_reviews, now=AFTER_DUE)

    assert decision.confidence.reviewed == 0
    assert decision.confidence.simulated == 0
    assert decision.outcome is ShadowOutcome.EXTENDED


# ---------------------------------------------------------------- the review, end to end


def test_a_short_confidence_extends_the_period_instead_of_ending_it() -> None:
    """Delete this and an agent that was understood twenty-six times in thirty is promoted.

    Twenty-six of thirty is short of nine tenths, so the answer to the thirty-day question is
    more time rather than a rung rise, and the pin comes back with a later review date and the
    same window start.
    """
    records, reviews = _window(understood=26, amended=4)
    decision = review(_pinned(), simulated=records, reviews=reviews, now=AFTER_DUE)

    assert decision.outcome is ShadowOutcome.EXTENDED
    assert decision.confidence.reviewed == 30
    assert decision.pin.review_due_at == AFTER_DUE + SHADOW_REVIEW_PERIOD
    assert decision.pin.pinned_at == PINNED_AT


def test_confidence_at_the_threshold_makes_a_promotion_possible_and_moves_no_date() -> None:
    """Delete this and every refusal above is satisfied by a review that never says yes.

    A guard tested only by its refusals is satisfied by a function that refuses everything.
    Twenty-seven of thirty on a due review has to come back eligible, and the pin must not be
    extended: the question was answered.
    """
    records, reviews = _window(understood=27, amended=3)
    decision = review(_pinned(), simulated=records, reviews=reviews, now=AFTER_DUE)

    assert decision.outcome is ShadowOutcome.ELIGIBLE
    assert decision.stays_supervised is False
    assert decision.pin == _pinned()
    assert decision.confidence.share == 0.9


def test_a_confidence_falls_when_the_agent_starts_getting_things_wrong() -> None:
    """Delete this and a share can be latched at its best reading.

    The agent that qualified and then started being amended is the case that matters. Nothing
    stores a figure or a qualified flag, so the same pin reviewed again on worse evidence
    comes back extended, and the same call that said eligible says extended.
    """
    good_records, good_reviews = _window(understood=27, amended=3)
    first = review(_pinned(), simulated=good_records, reviews=good_reviews, now=AFTER_DUE)
    assert first.outcome is ShadowOutcome.ELIGIBLE

    later_records = good_records + [_acted(n) for n in range(30, 40)]
    later_reviews = good_reviews + [_looked(n, ApprovalVerdict.AMENDED) for n in range(30, 40)]
    second = review(first.pin, simulated=later_records, reviews=later_reviews, now=AFTER_DUE)

    assert second.confidence.share < first.confidence.share
    assert second.outcome is ShadowOutcome.EXTENDED


# ------------------------------------------------------- nothing here raises a rung


def test_the_rung_a_supervised_agent_is_held_at_is_the_bottom_of_the_ladder() -> None:
    """Delete this and the held rung can be repointed at a tier that acts.

    Asserted against the ladder rather than against the literal zero, so a rung added below
    SHADOW moves this with it rather than leaving a constant naming the second-lowest.
    """
    assert min(AutonomyTier) == HELD_AT_WHILE_SUPERVISED


def test_a_supervised_leash_narrows_this_agent_and_leaves_every_other_agent_alone() -> None:
    """Delete this and one unanswered review can stop an estate, or fail to stop anything.

    Two properties in one place because they are one edit apart. A rung is held down for the
    agent under review, and another agent's rung is untouched: holding the whole table down
    on one agent's review is the blast radius that gets a control switched off.
    """
    entries = (
        LeashEntry(
            agent_id=CHASER, target="invoice.draft", scope=Scope(), rung=AutonomyTier.AUTONOMOUS
        ),
        LeashEntry(
            agent_id=OTHER_AGENT,
            target="ticket.read",
            scope=Scope(),
            rung=AutonomyTier.AUTONOMOUS,
        ),
    )
    held = supervised_leash(Leash(entries=entries), _extended_decision())

    assert held.rung_for(CHASER, "invoice.draft", {}) is AutonomyTier.SHADOW
    assert held.rung_for(OTHER_AGENT, "ticket.read", {}) is AutonomyTier.AUTONOMOUS


def test_an_eligible_review_raises_no_rung_and_leaves_the_agent_simulating() -> None:
    """Delete this and eligibility becomes the promotion.

    Every template in `brain.agents.catalogue` declares SHADOW on every target it names. An
    eligible review over that leash has to leave it saying SHADOW, because ending supervision
    is a person editing a rung through `may_raise` with a named approver, and for money a
    second one. If this ever returns anything above the bottom rung, the owner's decision has
    been undone by the function that implements it.
    """
    entries = (
        LeashEntry(
            agent_id=CHASER, target="invoice.draft", scope=Scope(), rung=AutonomyTier.SHADOW
        ),
    )
    leash = Leash(entries=entries)

    after_eligible = supervised_leash(leash, _eligible_decision())
    assert after_eligible.rung_for(CHASER, "invoice.draft", {}) is AutonomyTier.SHADOW

    after_extended = supervised_leash(leash, _extended_decision())
    assert after_extended.rung_for(CHASER, "invoice.draft", {}) is AutonomyTier.SHADOW


def test_no_function_in_this_module_hands_back_an_autonomy_tier() -> None:
    """Delete this and a helper that returns a rung can be added beside the ones that cannot.

    The module's whole claim is that it narrows and never raises. A function returning an
    `AutonomyTier` is the shape that breaks it, because a caller assigns what it is given, so
    the absence is asserted over the real annotations rather than promised in a docstring.
    """
    for name, obj in vars(supervision).items():
        if not inspect.isfunction(obj) or obj.__module__ != supervision.__name__:
            continue
        returns = inspect.signature(obj).return_annotation
        assert returns is not AutonomyTier, name
        assert "AutonomyTier" not in str(returns), name


def _eligible_decision() -> ShadowDecision:
    return ShadowDecision(
        outcome=ShadowOutcome.ELIGIBLE,
        confidence=Confidence(understood=27, reviewed=30, simulated=30),
        pin=_pinned(),
        asked_at=AFTER_DUE,
    )


def _extended_decision() -> ShadowDecision:
    return ShadowDecision(
        outcome=ShadowOutcome.EXTENDED,
        confidence=Confidence(understood=0, reviewed=0, simulated=0),
        pin=_pinned(),
        asked_at=AFTER_DUE,
    )
