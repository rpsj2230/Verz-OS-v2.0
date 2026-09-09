"""The comparison period: what it measures, and what it is not allowed to decide."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.migration.parallel import (
    A_PARALLEL_RUN_NOBODY_ENDED_IS_NOT_A_PERIOD,
    Comparison,
    Criterion,
    Direction,
    Measure,
    ParallelError,
    Period,
    Verdict,
    cutover_gaps,
    disagreements,
    may_cut_over,
    measured,
    unanswered,
    unmet,
    unreviewed,
)

#: Far outside any plausible wall clock, for the reason CLAUDE.md gives: a fixture with a date
#: near today is a clock, and this file is not about the present.
AGREED_ON = datetime(2030, 1, 1, tzinfo=UTC)
STARTED = datetime(2030, 2, 1, tzinfo=UTC)
ENDS = datetime(2030, 3, 1, tzinfo=UTC)
DURING = datetime(2030, 2, 15, tzinfo=UTC)


def a_criterion(
    measure: Measure = Measure.QUESTIONS_ASKED,
    direction: Direction = Direction.AT_LEAST,
    threshold: int = 20,
    agreed_at: datetime = AGREED_ON,
) -> Criterion:
    return Criterion(
        measure=measure,
        direction=direction,
        threshold=threshold,
        agreed_at=agreed_at,
        because="twenty is the acceptance set the pilot department wrote",
    )


def all_three(
    questions: int = 20, days: int = 7, unreviewed_at_most: int = 0
) -> tuple[Criterion, ...]:
    return (
        a_criterion(Measure.QUESTIONS_ASKED, Direction.AT_LEAST, questions),
        a_criterion(Measure.DAYS_RUNNING, Direction.AT_LEAST, days),
        a_criterion(Measure.UNREVIEWED_DISAGREEMENTS, Direction.AT_MOST, unreviewed_at_most),
    )


def a_period(criteria: tuple[Criterion, ...] | None = None) -> Period:
    return Period(
        started_at=STARTED, ends_at=ENDS, criteria=all_three() if criteria is None else criteria
    )


def asked(
    question: str = "how many hours are left on this project",
    verdict: Verdict = Verdict.AGREED,
    reviewed_by: str = "",
    day: int = 2,
) -> Comparison:
    return Comparison(
        question=question,
        asked_at=STARTED + timedelta(days=day),
        verdict=verdict,
        reviewed_by=reviewed_by,
    )


def a_log(
    agreed: int = 20, differed: int = 0, only_one: int = 0, reviewed: int = 0
) -> tuple[Comparison, ...]:
    entries = [asked(f"agreed {i}") for i in range(agreed)]
    entries.extend(
        asked(
            f"differed {i}",
            Verdict.DIFFERED,
            reviewed_by="u_priya" if i < reviewed else "",
        )
        for i in range(differed)
    )
    entries.extend(asked(f"unanswered {i}", Verdict.ONLY_ONE_ANSWERED) for i in range(only_one))
    return tuple(entries)


# ------------------------------------------------------- the criteria come first (M37.1.3.3)
def test_a_criterion_agreed_after_the_period_started_is_refused() -> None:
    """**M37.1.3.3 says the criteria are agreed in writing before the period starts, and this
    is what makes that checkable by somebody who was not in the room.**

    Whoever writes a threshold in week two has seen week one, and the threshold that gets
    written is the one the result already clears. That is what anybody does with the number in
    front of them, which is why it is a refusal here rather than a line in a runbook.

    Delete this and the timestamps become decoration, and a cutover is justified by criteria
    fitted to the period they were meant to judge."""
    late = a_criterion(agreed_at=STARTED + timedelta(days=3))

    with pytest.raises(ParallelError, match="after the period started"):
        Period(started_at=STARTED, ends_at=ENDS, criteria=(late,))


def test_a_criterion_agreed_at_the_very_instant_the_period_started_is_refused() -> None:
    """The boundary, and it is refused rather than allowed. Nothing is agreed in writing at the
    same instant a period opens; equality there is a default timestamp, which is exactly the
    case the rule is about.

    Delete this and the comparison can be written as a strict `>`, and every criterion stamped
    with the period's own start time passes."""
    with pytest.raises(ParallelError, match="after the period started"):
        Period(started_at=STARTED, ends_at=ENDS, criteria=(a_criterion(agreed_at=STARTED),))


def test_a_period_that_ends_before_it_starts_is_refused() -> None:
    """Two systems answering the same questions costs twice and confuses everybody who asks
    one of them, so it is a period with an end rather than an arrangement.

    Delete this and a period with the dates the wrong way round reports zero days running for
    ever, which clears no duration criterion and looks like the period never began."""
    with pytest.raises(ParallelError) as raised:
        Period(started_at=ENDS, ends_at=STARTED, criteria=())

    assert A_PARALLEL_RUN_NOBODY_ENDED_IS_NOT_A_PERIOD in str(raised.value)


def test_a_criterion_with_a_negative_threshold_is_refused() -> None:
    """Counted things are not negative, and an at-most criterion of minus one can never be met,
    so it reports as a permanently unmet criterion rather than as the typing error it is.

    Delete this and a cutover is blocked for ever by a threshold nobody can reach."""
    with pytest.raises(ParallelError, match="cannot be counted to -1"):
        a_criterion(threshold=-1)


def test_a_criterion_with_no_stated_reason_is_refused() -> None:
    """A threshold agreed in writing with no argument behind it is a number in a document, and
    the argument is what somebody re-reads when the result is close.

    Delete this and the reason column fills itself in from a template."""
    with pytest.raises(ParallelError, match="for no stated reason"):
        Criterion(
            measure=Measure.QUESTIONS_ASKED,
            direction=Direction.AT_LEAST,
            threshold=20,
            agreed_at=AGREED_ON,
            because="   ",
        )


def test_a_period_whose_criteria_were_all_agreed_first_is_accepted() -> None:
    """The positive case for every refusal above.

    Delete this and `Period` can be tightened until no period is constructible."""
    period = a_period()

    assert len(period.criteria) == len(Measure)
    assert period.started_at == STARTED


# ------------------------------------------------------------- the log (M37.1.3.1, M37.1.3.2)
def test_a_comparison_with_no_question_is_refused() -> None:
    """A row nobody can go and look at is a row that cannot be reviewed, and review is the
    measure that says whether the comparison was done rather than merely run.

    Delete this and the blank branch is unreachable."""
    with pytest.raises(ParallelError, match="records no question"):
        asked(question="  ")


def test_marking_an_agreement_as_reviewed_is_refused() -> None:
    """Review is what happens to a disagreement. A reviewer's name against an agreement is a
    bulk update, and it inflates nothing visible: `unreviewed` would still be right, and the
    log would claim somebody read a pair of answers that never differed.

    Delete this and "mark all reviewed" becomes a way to clear the one measure that says
    whether anybody looked."""
    with pytest.raises(ParallelError, match="review is what happens to a disagreement"):
        asked(verdict=Verdict.AGREED, reviewed_by="u_priya")


def test_a_disagreement_is_returned_as_the_entries_and_not_as_a_count() -> None:
    """**M37.1.3.2 asks for disagreements to be surfaced.** A count sends somebody to argue
    about a percentage; the entries send them to read three answers, which is what the period
    is for.

    Delete this and the log's only output is a number, and the questions the two systems
    answered differently are never read by anybody."""
    log = a_log(agreed=2, differed=2)

    found = disagreements(log)

    assert [one.question for one in found] == ["differed 0", "differed 1"]
    assert all(one.verdict is Verdict.DIFFERED for one in found)


def test_a_question_only_one_system_answered_is_neither_agreement_nor_disagreement() -> None:
    """**The third verdict, and the reason there are three.** Folded into agreement, an old
    system that has quietly stopped answering produces a perfect score and the cutover is
    decided by an outage. Folded into disagreement, the same outage reads as the new system
    being wrong about everything.

    Delete this and the log can go back to two verdicts, and whichever fold is chosen decides
    a cutover on something nobody measured."""
    log = a_log(agreed=3, differed=1, only_one=2)

    assert len(unanswered(log)) == 2
    assert len(disagreements(log)) == 1
    assert measured(Measure.QUESTIONS_ASKED, log, period=a_period(), now=DURING) == 4


def test_an_unreviewed_disagreement_is_a_disagreement_nobody_has_read() -> None:
    """The measure that separates a comparison period from a parallel run.

    Delete this and a period can end with every disagreement unread and still report that it
    ran for a month with twenty questions."""
    log = a_log(agreed=1, differed=3, reviewed=1)

    assert [one.question for one in unreviewed(log)] == ["differed 1", "differed 2"]


def test_days_running_is_measured_to_now_rather_than_to_the_agreed_end() -> None:
    """The question a duration criterion asks is how long it has actually run, not how long it
    was agreed to run for.

    Delete this and every period clears its duration criterion on the day it opens, because
    the agreed span is written down in advance and the measurement would read that."""
    period = a_period()

    assert measured(Measure.DAYS_RUNNING, (), period=period, now=STARTED + timedelta(days=9)) == 9
    assert measured(Measure.DAYS_RUNNING, (), period=period, now=STARTED) == 0


# ------------------------------------------------------------------------ the cutover
def test_a_measure_nobody_agreed_a_threshold_for_is_reported_first() -> None:
    """**A cutover agreed on the question count alone is agreed without reference to whether
    anybody read the disagreements**, and that is the measure that says the comparison was
    done rather than merely run. It is a gap in the agreement, not a criterion that passes by
    being absent, and it is reported before the results because it says the results are not
    the whole answer.

    Delete this and a period with one criterion reports a clean cutover."""
    period = a_period((a_criterion(Measure.QUESTIONS_ASKED, Direction.AT_LEAST, 1),))

    findings = cutover_gaps(period, a_log(agreed=5), now=DURING)

    assert findings == (
        "days running: nothing was agreed about it before the period started",
        "unreviewed disagreements: nothing was agreed about it before the period started",
    )


def test_a_criterion_that_is_not_met_says_what_it_stands_at_and_what_was_agreed() -> None:
    """Both numbers, because a finding that gives only one of them sends the reader back to
    two documents to work out how far off it is.

    Delete this and the finding becomes "not met", which nobody can act on."""
    period = a_period(all_three(questions=20, days=7, unreviewed_at_most=0))

    findings = unmet(period, a_log(agreed=5, differed=2), now=STARTED + timedelta(days=2))

    assert findings == (
        "questions asked: 7, and the agreed criterion is at least 20",
        "days running: 2, and the agreed criterion is at least 7",
        "unreviewed disagreements: 2, and the agreed criterion is at most 0",
    )


def test_a_period_running_past_its_agreed_end_is_its_own_finding() -> None:
    """**Not the same finding as an unmet criterion.** An unmet criterion is a real answer and
    the period is doing its job. This one says nobody looked, and two systems are answering
    the same questions indefinitely at twice the cost.

    Delete this and a parallel run that everybody forgot about reports as a period whose
    criteria are all met."""
    period = a_period()
    log = a_log(agreed=30, differed=1, reviewed=1)

    findings = cutover_gaps(period, log, now=ENDS + timedelta(days=10))

    assert len(findings) == 1
    assert findings[0].startswith("the agreed period ended at")


def test_a_period_that_met_every_criterion_may_cut_over() -> None:
    """The positive case for the whole module, and it is the one that proves the refusals are
    not unconditional.

    Delete this and every guard here can be strengthened until no migration ever cuts over."""
    period = a_period()
    log = a_log(agreed=30, differed=2, reviewed=2)

    assert cutover_gaps(period, log, now=STARTED + timedelta(days=10)) == ()
    assert may_cut_over(period, log, now=STARTED + timedelta(days=10)) is True


def test_a_period_may_cut_over_with_disagreements_everybody_has_read() -> None:
    """**Deliberately not "no disagreements".** Two systems will differ, and a period that ends
    with the differences read and decided about is a period that did its job. Refusing to cut
    over until they agree on everything is refusing to cut over.

    Delete this and the obvious tightening is to require zero disagreements, which makes the
    comparison period a way of never migrating."""
    period = a_period()
    log = a_log(agreed=25, differed=6, reviewed=6)

    assert may_cut_over(period, log, now=STARTED + timedelta(days=10)) is True
    assert len(disagreements(log)) == 6


def test_a_period_with_an_unread_disagreement_may_not_cut_over() -> None:
    """The other side of the same rule, and the reason the review measure exists.

    Delete this and a cutover proceeds with disagreements in the log that nobody opened."""
    period = a_period()
    log = a_log(agreed=25, differed=6, reviewed=5)

    assert may_cut_over(period, log, now=STARTED + timedelta(days=10)) is False
