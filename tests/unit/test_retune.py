"""Retuning a budget threshold from a measured distribution, and refusing to without one.

Every distribution here is synthetic and deliberately so. What is being tested is the
machinery, and the one thing that must not happen is a default in `brain.ops.budgets` moving
because of a number generated in a test file.

Task ids: M37.5.3.3
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from brain.ops.budgets import DAILY_BURST, DAYS_IN_BUDGET_MONTH, DEFAULT_ALERT_FRACTIONS
from brain.ops.retune import (
    ALERTS_WORTH_READING,
    DAYS_A_BURST_CAP_MUST_ADMIT,
    MEASUREMENT_WINDOW_DAYS,
    SAMPLES_IN_THE_TAIL,
    Distribution,
    Proposal,
    RetuneError,
    proposal_gaps,
    retune_alert_fraction,
    retune_daily_burst,
    samples_needed,
    variance,
)

MODULE = Path(__file__).resolve().parents[2] / "src" / "brain" / "ops" / "retune.py"


def _flat(reading: int, count: int, *, over_days: int | None = None) -> Distribution:
    """A distribution of identical readings, which makes every percentile predictable."""
    return Distribution(readings=(reading,) * count, over_days=over_days or count)


def _ramp(count: int, *, over_days: int | None = None) -> Distribution:
    """Readings from 1 to `count`, so the percentile at p is p of the way up."""
    return Distribution(readings=tuple(range(1, count + 1)), over_days=over_days or count)


# --------------------------------------------------------------------- how much evidence
def test_the_readings_a_percentile_needs_grow_with_the_percentile() -> None:
    """Delete this and a ninety-ninth percentile over twenty readings passes as a percentile.

    It is the largest of the twenty, because there is nothing above it, and at the point of
    use it is indistinguishable from a real answer: a number, in range, with a sample count
    beside it. The relation is asserted rather than the values, so the property survives
    `SAMPLES_IN_THE_TAIL` being tuned.
    """
    assert samples_needed(0.99) > samples_needed(0.90) > samples_needed(0.80)
    assert samples_needed(0.90) * (1 - 0.90) >= SAMPLES_IN_THE_TAIL


def test_a_month_of_daily_readings_places_the_eightieth_percentile_and_not_the_ninetyninth() -> (
    None
):
    """Delete this and `SAMPLES_IN_THE_TAIL` can be tuned until every question is answerable.

    Both halves of the sentence in the constant's own comment, asserted against
    `MEASUREMENT_WINDOW_DAYS` rather than against the constant itself. Raising the tail size
    breaks the first half and lowering it breaks the second, which is what makes this a check
    on the number rather than a restatement of it.
    """
    assert samples_needed(0.80) <= MEASUREMENT_WINDOW_DAYS
    assert samples_needed(0.99) > MEASUREMENT_WINDOW_DAYS


def test_the_count_it_asks_for_actually_puts_several_readings_above_the_percentile() -> None:
    """Delete this and `SAMPLES_IN_THE_TAIL` can be dropped to one with nothing failing.

    A tail of one makes the percentile the largest reading, which is exactly what the
    constant exists to prevent, and the bracketing test above passes for that value: five
    readings still fit inside a month and a hundred still do not. The property is what the
    number is for, so the property is what is asserted: at the count this asks for, the part
    of the distribution above the percentile has more than one reading in it.
    """
    for at in (0.8, 0.9, 0.99):
        readings = _ramp(samples_needed(at))
        above = sum(1 for one in readings.readings if one > readings.percentile(at))
        assert above > 1, f"the {at:.0%} percentile of {samples_needed(at)} readings has a tail"


def test_a_cap_that_refuses_work_fires_more_rarely_than_a_warning_that_mentions_it() -> None:
    """Delete this and the two target percentiles can be brought together.

    They are two constants that must differ and nothing else compares them, which is the
    shape that passes every test in a file while being wrong. A warning is a sentence
    somebody reads; a burst cap refuses a person's work. If the day you are warned is the day
    you are refused, the warning has bought nothing and the cap has become the warning.
    """
    assert DAYS_A_BURST_CAP_MUST_ADMIT > 1.0 - ALERTS_WORTH_READING


def test_a_percentile_at_the_edges_is_refused() -> None:
    """Delete this and a caller can ask for the minimum or the maximum and be given a sample
    count for it, which is a different question wearing this one's clothes."""
    for at in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(RetuneError, match="percentile"):
            samples_needed(at)


def test_a_tail_of_nothing_is_refused() -> None:
    """Delete this and `samples_needed` can be made to return the count at which the
    percentile is the largest reading, which is the thing it exists to refuse."""
    with pytest.raises(RetuneError, match="largest reading"):
        samples_needed(0.9, 0)


# ------------------------------------------------------------------------ the evidence
def test_a_distribution_with_no_readings_is_refused() -> None:
    """Delete this and an assumption with a type on it passes as a measurement."""
    with pytest.raises(RetuneError, match="no readings"):
        Distribution(readings=(), over_days=30)


def test_a_negative_reading_is_refused() -> None:
    """Delete this and a sign error upstream becomes a threshold.

    Zero is kept: a quiet day is evidence, and dropping it would make the distribution the
    distribution of busy days, which is the one thing a burst cap must not be tuned against.
    """
    with pytest.raises(RetuneError, match="is not a spend"):
        Distribution(readings=(1, -1), over_days=2)
    assert Distribution(readings=(0, 1), over_days=2).total_minor == 1


def test_a_window_of_no_days_is_refused() -> None:
    """Delete this and a comparison against a monthly projection can be made without knowing
    how much of a month it is looking at."""
    with pytest.raises(RetuneError, match="not a window"):
        Distribution(readings=(1,), over_days=0)


def test_the_window_length_is_carried_rather_than_counted() -> None:
    """Delete this and a weekly series looks like four days of spending.

    Four readings over thirty days is a month sampled weekly, and collapsing the two would
    make `is_long_enough` false for a measurement that covers the whole period.
    """
    weekly = Distribution(readings=(1, 2, 3, 4), over_days=30)
    assert weekly.is_long_enough
    assert not Distribution(readings=(1, 2, 3, 4), over_days=4).is_long_enough


def test_the_percentile_is_a_reading_that_actually_happened() -> None:
    """Delete this and a threshold is placed at a number no period ever cost.

    Nearest rank rather than interpolation. Every figure here is money spent on some period,
    so an interpolated percentile is a value nothing in the evidence sits either side of.
    """
    ramp = _ramp(100)
    assert ramp.percentile(0.9) == 90
    assert ramp.percentile(0.5) == 50
    assert ramp.percentile(0.01) == 1
    assert _flat(7, 10).percentile(0.9) == 7


def test_a_percentile_at_the_edges_of_a_distribution_is_refused() -> None:
    """Delete this and a caller gets the minimum or the maximum labelled as a percentile."""
    for at in (0.0, 1.0):
        with pytest.raises(RetuneError, match="minimum or the maximum"):
            _ramp(10).percentile(at)


def test_the_share_above_a_figure_is_strict() -> None:
    """Delete this and a proposal reports itself as firing more often than it does.

    A budget alert crosses when spend *exceeds* the fraction, which is the comparison
    `brain.ops.budgets.BudgetRow.alerts_crossed` makes, so a threshold placed exactly at an
    observed reading has not fired on it.
    """
    assert _flat(10, 4).share_above(10) == 0.0
    assert _flat(10, 4).share_above(9) == 1.0
    assert _ramp(10).share_above(5) == 0.5


# --------------------------------------------------- measured against the projection
def test_the_variance_is_a_ratio_over_the_totals() -> None:
    """Delete this and a hundred quiet days outvote the week the work happened.

    A mean of per-period ratios weights a day that cost a penny equally with the day a
    backfill ran, which is the same failure `brain.ops.spend.correct` avoids in the same way.
    """
    measured = Distribution(readings=(100, 100, 800), over_days=30)
    result = variance(projected_minor=500, measured=measured)
    assert result.measured_minor == 1000
    assert result.ratio == 2.0
    assert result.long_enough


def test_a_short_window_produces_a_variance_that_says_it_is_short() -> None:
    """Delete this and a fortnight's spending is compared against a monthly projection with
    nothing attached saying so.

    The caveat is on the value rather than in a paragraph, because the number is what gets
    quoted and a caveat somewhere else does not travel with it.
    """
    short = variance(projected_minor=500, measured=Distribution(readings=(100,), over_days=9))
    assert not short.long_enough
    assert "indication rather than a comparison" in short.because
    long = variance(
        projected_minor=500,
        measured=Distribution(readings=(100,), over_days=MEASUREMENT_WINDOW_DAYS),
    )
    assert long.long_enough
    assert "indication rather than a comparison" not in long.because


def test_a_projection_of_nothing_is_refused() -> None:
    """Delete this and a divide by zero becomes a variance of infinity in a report."""
    with pytest.raises(RetuneError, match="no ratio to an actual"):
        variance(projected_minor=0, measured=_flat(1, 1))


# ------------------------------------------------------------- retuning a warning fraction
def test_the_first_alert_fraction_is_placed_where_it_fires_at_the_target_rate() -> None:
    """Delete this and the warning fraction is tuned against the ceiling, which cannot see
    the failure that actually happens.

    An alert fraction fails on a real estate by firing on most periods and being ignored, and
    the ceiling is the same number whatever the spending looks like. A ramp from 1 to 100
    against a ceiling of 100 puts the ninetieth percentile at 90, so the proposal is 0.9.
    """
    proposal = retune_alert_fraction(measured=_ramp(100), ceiling_minor=100)
    assert proposal.is_supported
    assert proposal.proposed == pytest.approx(0.9)
    assert proposal.at_percentile == pytest.approx(1.0 - ALERTS_WORTH_READING)
    assert proposal.current == DEFAULT_ALERT_FRACTIONS[0]


def test_the_reason_says_how_often_the_current_fraction_fires() -> None:
    """Delete this and the proposal is a number with no argument attached.

    The figure that makes the case is not the proposal, it is the rate the current threshold
    fires at: 0.75 of the ceiling firing on a quarter of periods is the sentence somebody
    acts on.
    """
    proposal = retune_alert_fraction(measured=_ramp(100), ceiling_minor=100)
    assert "fires on 25% of periods" in proposal.because
    assert "Not applied" in proposal.because


def test_a_proposal_above_the_ceiling_is_returned_rather_than_clamped() -> None:
    """Delete this and the most useful answer this function gives is hidden.

    A ninetieth percentile above the ceiling means no warning fraction can be placed
    usefully, because the ordinary state of the estate is already over budget. Clamping it to
    1.0 would report that as a threshold somebody could set.
    """
    proposal = retune_alert_fraction(measured=_flat(500, 60), ceiling_minor=100)
    assert proposal.proposed is not None
    assert proposal.proposed > 1.0


def test_too_few_readings_produce_a_refusal_naming_the_count_needed() -> None:
    """Delete this and a threshold is placed from the largest of a handful of readings.

    The refusal has to carry the number, because whoever is deciding whether to keep
    collecting needs to know how much longer, and an approximate answer there is worse than
    none.
    """
    proposal = retune_alert_fraction(measured=_ramp(5), ceiling_minor=100)
    assert not proposal.is_supported
    assert proposal.proposed is None
    assert str(samples_needed(1.0 - ALERTS_WORTH_READING)) in proposal.because


def test_a_ceiling_of_nothing_and_a_budget_with_no_fractions_are_refused() -> None:
    """Delete this and the retune answers questions that have no subject."""
    with pytest.raises(RetuneError, match="no fractions"):
        retune_alert_fraction(measured=_ramp(100), ceiling_minor=0)
    with pytest.raises(RetuneError, match="no first fraction"):
        retune_alert_fraction(measured=_ramp(100), ceiling_minor=100, current=())


# ---------------------------------------------------------------- retuning the daily burst
def test_a_month_of_daily_totals_cannot_retune_the_burst_cap() -> None:
    """Delete this and the finding disappears into a number.

    This is the result rather than a limitation of the module. A cap meant to catch a loop
    has to sit above essentially every real day, which is a ninety-ninth percentile, which
    needs five hundred readings. Thirty days of daily totals is thirty readings, so a month
    of production does not move this constant and the honest answer says how much would.
    """
    month = _ramp(MEASUREMENT_WINDOW_DAYS)
    proposal = retune_daily_burst(measured=month, monthly_allowance_minor=3000)
    assert not proposal.is_supported
    assert str(samples_needed(DAYS_A_BURST_CAP_MUST_ADMIT)) in proposal.because
    assert proposal.current == DAILY_BURST


def test_enough_readings_produce_a_multiple_of_an_even_day() -> None:
    """Delete this and the refusal above is satisfied by a function that refuses everything.

    Every refusal test needs a sibling proving the thing still works. Five hundred readings
    all at twice an even day propose a multiple of two.
    """
    even_day = 3000 / DAYS_IN_BUDGET_MONTH
    readings = _flat(int(even_day * 2), samples_needed(DAYS_A_BURST_CAP_MUST_ADMIT))
    proposal = retune_daily_burst(measured=readings, monthly_allowance_minor=3000)
    assert proposal.is_supported
    assert proposal.proposed == pytest.approx(2.0)


def test_an_allowance_or_a_month_of_nothing_is_refused() -> None:
    """Delete this and a divide by zero becomes a burst multiple."""
    plenty = _flat(1, samples_needed(DAYS_A_BURST_CAP_MUST_ADMIT))
    with pytest.raises(RetuneError, match="no daily share"):
        retune_daily_burst(measured=plenty, monthly_allowance_minor=0)
    with pytest.raises(RetuneError, match="no even day"):
        retune_daily_burst(measured=plenty, monthly_allowance_minor=3000, days_in_month=0)


# ------------------------------------------------------------------------- the proposals
def test_a_proposal_that_names_no_setting_is_reported() -> None:
    """Delete this and a number in a report gets applied to the nearest constant with a
    similar name, and there are two alert fractions."""
    nameless = Proposal(
        setting=" ",
        current=0.75,
        proposed=0.9,
        at_percentile=0.9,
        readings=100,
        because="because",
    )
    assert any("names no setting" in one for one in proposal_gaps((nameless,)))


def test_a_proposal_agreeing_with_the_assumption_is_said_out_loud() -> None:
    """Delete this and the most useful result this module can produce reads as nothing having
    happened.

    "The measurement agrees with the assumption" is a real answer and it is the one that
    looks identical to a run that found nothing.
    """
    agreeing = Proposal(
        setting="brain.ops.budgets.DAILY_BURST",
        current=4.0,
        proposed=4.0,
        at_percentile=0.99,
        readings=500,
        because="because",
    )
    assert any("agreeing with the assumption" in one for one in proposal_gaps((agreeing,)))
    moved = Proposal(
        setting="brain.ops.budgets.DAILY_BURST",
        current=4.0,
        proposed=2.0,
        at_percentile=0.99,
        readings=500,
        because="because",
    )
    assert proposal_gaps((moved,)) == ()


def test_nothing_in_this_module_produces_a_budget_row() -> None:
    """Delete this and a proposal becomes something somebody wires straight into a budget.

    Structural rather than a promise: the module is parsed and every annotated return type is
    read. A function here returning a `BudgetRow` would be this module writing the ceilings
    it exists to argue about, and the diff would read as a tuning.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    returns = [
        ast.unparse(node.returns)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.returns is not None
    ]
    assert returns, "the module has annotated functions to check"
    assert not any("BudgetRow" in one for one in returns)


def test_this_module_imports_the_budget_constants_and_nothing_that_writes_one() -> None:
    """Delete this and the constants can be imported alongside something that persists them.

    The constants are here to be compared against. `company_budget`, `allocate` and
    `user_allowances` all build rows, and importing any of them would put the act of applying
    a proposal one line away from the function that produces it.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "brain.ops.budgets"
        for alias in node.names
    }
    assert imported == {"DAILY_BURST", "DAYS_IN_BUDGET_MONTH", "DEFAULT_ALERT_FRACTIONS"}
