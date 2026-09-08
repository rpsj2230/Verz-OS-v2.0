"""Moving a threshold from an assumption to a measurement, and refusing to move one without.

`brain.ops.budgets` holds four numbers that were reasoned about and never measured:
`DEFAULT_ALERT_FRACTIONS` at three quarters and nine tenths, `ALLOWANCE_GENEROSITY` at three
times an even split, `DAILY_BURST` at four ordinary days, and `USER_FAIR_SHARE` at a quarter.
Every one of them has an argument beside it and none of them has a distribution behind it.
`brain.ops.spend.correct` closes the same loop for the *estimator* and stops there; this is
the other half, which is the thresholds the estimate is judged against.

**Nothing here is applied to any default, and that is the deliverable rather than a caveat.**
There are no thirty days of actuals in this repository and there is no company running it. A
number retuned against imagined data is worse than the assumption it replaced, because the
assumption is visibly an assumption and the retuned figure carries the authority of having
been measured. So every function here returns a `Proposal`, which is a value with a
justification on it and nothing that writes anything, and the constants in `brain.ops.budgets`
are imported to be compared against rather than to be moved. See
`A_THRESHOLD_RETUNED_AGAINST_IMAGINED_DATA_IS_WORSE_THAN_THE_ASSUMPTION`.

**How many observations a percentile needs is derived from the percentile, not chosen.** This
is the part that decides whether a retune is honest, and it is where the arithmetic actually
bites. A ninety-ninth percentile over twenty samples is the maximum with extra steps: there
is no observation above it, so the answer is one unusual day rather than a property of the
distribution. `samples_needed` is `SAMPLES_IN_THE_TAIL / (1 - percentile)`, so the tail being
reasoned about has several observations in it, and asking for the ninety-ninth percentile
therefore asks for five hundred readings. **A thirty-day window cannot support that**, which
is a real finding rather than a limitation of this module: `MEASUREMENT_WINDOW_DAYS` of daily
totals is thirty numbers, and thirty numbers can retune a threshold at the eightieth
percentile and cannot retune one at the ninety-ninth. `retune_daily_burst` says so instead of
answering.

**A warning threshold is retuned against how often it would fire, not against the ceiling.**
An alert fraction is not a safety limit, it is a thing a person reads, and the failure of
`DEFAULT_ALERT_FRACTIONS` on a real estate is not that it is unsafe but that it fires on most
periods and is ignored by the end of the second month. So the target is a rate:
`ALERTS_WORTH_READING` says what share of periods may cross the first fraction, and the
proposal is the fraction that produces it in the measured distribution. See
`AN_ALERT_FRACTION_IS_TUNED_AGAINST_HOW_OFTEN_IT_FIRES`.

**A cap that exists to catch a loop is tuned above the ordinary, not at it.** `DAILY_BURST`
is not there to ration a busy day; `brain.ops.budgets` says so beside the constant, and the
monthly ceiling is what actually binds. So the target percentile is high on purpose and the
proposal admits essentially every real day, which is the opposite of how a fair-share figure
would be tuned and is why the two are separate functions rather than one with a parameter.

Rejected: returning a corrected constant. A function returning a number is a function
somebody assigns to the constant, and the diff reads as a tuning rather than as a change of
regime. A `Proposal` carries what it was, what it would be, at what percentile, over how many
readings, and why, and none of that survives being flattened to a float.

Rejected: taking the observations from a store. The same split every policy module here
keeps: `brain.ops.limits` holds the window algorithm and no connection. A retune that read
its own actuals could not be tested against the distribution that matters, which is the one
with too few readings in the tail.

Rejected: folding this into `brain.ops.spend`. That module corrects the estimate and this
moves the threshold the estimate is judged against, and they fail in opposite directions: an
estimator that drifts low waves work through, and a threshold that drifts low refuses it. One
module for both would be one place where a single blend constant governed both directions.

Scope: domain logic. Nothing here reads a clock, opens a connection or stores anything, and
there is no function that returns a `brain.ops.budgets.BudgetRow`: a proposal cannot be
mistaken for a budget by anybody wiring this up in a hurry.

Task ids: M37.5.3.3
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from brain.ops.budgets import DAILY_BURST, DAYS_IN_BUDGET_MONTH, DEFAULT_ALERT_FRACTIONS

# ------------------------------------------------------------------ written-down reasons
#: Why every function here returns a proposal and none of them changes a default.
A_THRESHOLD_RETUNED_AGAINST_IMAGINED_DATA_IS_WORSE_THAN_THE_ASSUMPTION: Final = (
    "An assumption is visibly an assumption: the constant carries a paragraph saying what it "
    "was reasoned from, and the next reader knows to distrust it. A figure retuned against a "
    "distribution somebody invented carries the authority of a measurement and nothing "
    "distinguishes it from one, so the next reader stops asking. There are no thirty days of "
    "actuals in this repository and no company running it, so nothing here may move a "
    "default: a proposal is a value with its evidence attached and no way to apply itself."
)

#: Why a warning threshold is tuned against its firing rate rather than against the ceiling.
AN_ALERT_FRACTION_IS_TUNED_AGAINST_HOW_OFTEN_IT_FIRES: Final = (
    "brain.ops.budgets.AN_ALERT_IS_NOT_A_CEILING already says what an alert fraction is not. "
    "What it is, is a sentence a person reads, so the way it fails on a real estate is not "
    "that it admits too much but that it fires on most periods and stops being read by the "
    "end of the second month. Tuning it against the ceiling cannot see that failure at all, "
    "because the ceiling is the same number whatever the spending looks like. Tuning it "
    "against the observed rate can, and the number it produces is the fraction at which the "
    "warning still means something unusual happened."
)

#: Why the number of readings needed is computed from the percentile.
A_PERCENTILE_OVER_TOO_FEW_READINGS_IS_THE_MAXIMUM_WEARING_A_NUMBER: Final = (
    "Ask for the ninety-ninth percentile of twenty readings and you get the largest of the "
    "twenty, because there is nothing above it to interpolate towards. The answer is one "
    "unusual day rather than a property of the distribution, and it is indistinguishable "
    "from a real answer at the point of use: it is a number, in range, with a sample count "
    "beside it. So the sample count needed is derived from the tail being asked about rather "
    "than being one figure for every question, and a request that cannot be supported is "
    "refused with the count it would have needed."
)


class RetuneError(Exception):
    """A distribution was described in a shape no percentile can be taken of.

    Outside `brain.core.errors` for the reason `brain.ops.jobs.JobsError` gives about itself:
    nobody asking a question ever sees one of these.
    """


# ------------------------------------------------------------------------- the evidence
#: How long a window has to be before it is worth comparing against a projection.
#:
#: Thirty days, which is `brain.ops.budgets.DAYS_IN_BUDGET_MONTH` rather than a month, and
#: taking it from there rather than writing 30 is what keeps the comparison aligned with the
#: period the ceilings are actually written over. A shorter window compares a fortnight's
#: spending against a monthly projection and the ratio is arithmetic about nothing.
MEASUREMENT_WINDOW_DAYS: Final[int] = DAYS_IN_BUDGET_MONTH

#: How many readings a percentile's tail must contain before the percentile means anything.
#:
#: Five. One would make the percentile the maximum, which is the failure being avoided; the
#: figure has to be small enough that a threshold at the eightieth percentile is answerable
#: from a month of daily readings, and large enough that the tail is not a single event.
#: Asserted against that property rather than against itself: a month of daily readings
#: supports the eightieth percentile and does not support the ninety-ninth, and both halves
#: of that sentence break if this number moves far.
SAMPLES_IN_THE_TAIL: Final[int] = 5

#: What share of periods may cross the first warning fraction before it stops being read.
#:
#: One in ten. Above it the warning is the ordinary state of a busy estate and people learn
#: to close it; far below it the first thing somebody sees is the ceiling itself, which is
#: the warning having bought nothing.
#:
#: What this costs is worth reading before anybody plans around it. A rate of one in ten is a
#: ninetieth percentile, which `samples_needed` puts at over fifty readings, and a reading is
#: one budget period. On a daily budget that is two months of running. **On a monthly budget
#: it is over four years**, so the first alert fraction of a monthly ceiling is not something
#: a first year of production retunes, and `retune_alert_fraction` says so rather than
#: answering from twelve readings.
ALERTS_WORTH_READING: Final[float] = 0.10

#: The share of real days a daily cap must admit. A cap on the day a report is due is a cap
#: that refuses work rather than catching a loop, which is the failure
#: `brain.ops.budgets.DAILY_BURST` names in its own comment.
DAYS_A_BURST_CAP_MUST_ADMIT: Final[float] = 0.99


def samples_needed(percentile: float, in_the_tail: int = SAMPLES_IN_THE_TAIL) -> int:
    """How many readings a percentile needs before it is a percentile.

    `in_the_tail / (1 - percentile)`, rounded up, which is the count at which the part of the
    distribution above the percentile holds `in_the_tail` observations. See
    `A_PERCENTILE_OVER_TOO_FEW_READINGS_IS_THE_MAXIMUM_WEARING_A_NUMBER`.

    Both arguments are parameters rather than the constants beside them, following
    `brain.ops.queue.concurrency_gaps`: a function that could only be run against one value
    cannot be shown to give a different answer for another, and the whole content of this one
    is that the answer moves a great deal with the percentile.
    """
    if not 0.0 < percentile < 1.0:
        msg = (
            f"a percentile of {percentile} is not inside the distribution; 0 and 1 are the "
            "minimum and the maximum, and neither needs a sample count to be believed"
        )
        raise RetuneError(msg)
    if in_the_tail < 1:
        msg = (
            f"{in_the_tail} observation(s) in the tail makes the percentile the largest "
            "reading, which is the thing this function exists to refuse"
        )
        raise RetuneError(msg)
    return math.ceil(in_the_tail / (1.0 - percentile))


@dataclass(frozen=True)
class Distribution:
    """What actually happened, in minor units, one reading per period.

    Readings rather than a mean and a spread, because every question here is about a tail and
    a tail is exactly what a summary loses. The shape a caller has after a month is a list of
    daily totals, so that is the shape this takes.

    `over_days` is carried alongside rather than derived from the length, and the two are
    allowed to differ: a month of readings taken weekly is four readings over thirty days,
    and collapsing them would make a weekly series look like four days of spending.
    """

    #: One period's spend, in minor units. Zero is a real reading: a quiet day is evidence.
    readings: tuple[int, ...]
    #: How many days these readings span. Used to say whether the window is long enough.
    over_days: int

    def __post_init__(self) -> None:
        if not self.readings:
            msg = "a distribution with no readings in it is an assumption with a type on it"
            raise RetuneError(msg)
        for reading in self.readings:
            if reading < 0:
                msg = f"a reading of {reading} minor units is not a spend"
                raise RetuneError(msg)
        if self.over_days < 1:
            msg = (
                f"{self.over_days} day(s) is not a window; a comparison against a monthly "
                "projection needs to know how much of a month it is looking at"
            )
            raise RetuneError(msg)

    @property
    def total_minor(self) -> int:
        return sum(self.readings)

    @property
    def is_long_enough(self) -> bool:
        """Whether this window reaches the period the ceilings are written over."""
        return self.over_days >= MEASUREMENT_WINDOW_DAYS

    def percentile(self, at: float) -> int:
        """The reading at this percentile, by nearest rank.

        Nearest rank rather than interpolation, and the choice is deliberate rather than
        simpler. Every figure here is money that was actually spent on some period, so an
        interpolated percentile is a number no period ever cost, and a threshold placed at it
        is a threshold nothing in the evidence sits either side of. The rank is
        `ceil(at * n)`, which puts the hundredth percentile at the largest reading and the
        smallest positive percentile at the smallest.

        Refuses 0 and 1 for the reason `samples_needed` does: those are the minimum and the
        maximum, they need no evidence, and a caller asking for them is asking a different
        question from the one this answers.
        """
        if not 0.0 < at < 1.0:
            msg = (
                f"a percentile of {at} is the minimum or the maximum of these readings "
                "rather than a percentile of them"
            )
            raise RetuneError(msg)
        ordered = sorted(self.readings)
        rank = max(1, math.ceil(at * len(ordered)))
        return ordered[rank - 1]

    def share_above(self, minor: int) -> float:
        """What fraction of readings are strictly above this figure.

        Strictly, so a threshold placed exactly at an observed reading is not counted as
        having fired on it. A budget alert crosses when spend exceeds the fraction, which is
        the same comparison `brain.ops.budgets.BudgetRow.alerts_crossed` makes, and a share
        computed the other way would report a proposal as firing more often than it does.
        """
        return sum(1 for reading in self.readings if reading > minor) / len(self.readings)


# ------------------------------------------------- measured against the projection (M37.5.3.1)
@dataclass(frozen=True)
class Variance:
    """What was projected, what happened, and whether the window is long enough to say.

    `long_enough` is on the value rather than being left to the reader, because a variance
    over nine days is a number in exactly the same format as a variance over thirty and is
    not the same claim. The one that gets quoted in a meeting is whichever one is to hand.
    """

    projected_minor: int
    measured_minor: int
    over_days: int
    #: Measured over projected. Above one is spending more than was projected.
    ratio: float
    long_enough: bool
    because: str


def variance(*, projected_minor: int, measured: Distribution) -> Variance:
    """Measured spend against the projection over this window (M37.5.3.1).

    A ratio over the totals rather than a mean of per-period ratios, which is the same choice
    `brain.ops.spend.correct` makes and for the same reason: the periods that matter to a
    budget are the few large ones, and a mean of ratios lets a hundred quiet days outvote the
    week the work actually happened.

    A window shorter than the period the ceilings are written over produces a variance and
    says so rather than refusing. Refusing would hide the only reading anybody has in the
    first fortnight of an installation, and the honest handling of a partial window is to
    hand it over with the caveat attached to it rather than in a paragraph somewhere else.
    """
    if projected_minor < 1:
        msg = (
            f"a projection of {projected_minor} has no ratio to an actual; nothing was "
            "projected, so nothing can be over or under it"
        )
        raise RetuneError(msg)
    ratio = measured.total_minor / projected_minor
    long_enough = measured.is_long_enough
    return Variance(
        projected_minor=projected_minor,
        measured_minor=measured.total_minor,
        over_days=measured.over_days,
        ratio=ratio,
        long_enough=long_enough,
        because=(
            f"{measured.total_minor} spent against {projected_minor} projected, over "
            f"{measured.over_days} day(s)"
            + (
                ""
                if long_enough
                else f", which is short of the {MEASUREMENT_WINDOW_DAYS} day(s) the ceilings "
                "are written over, so this is an indication rather than a comparison"
            )
        ),
    )


# ------------------------------------------------------------- retuned thresholds (M37.5.3.3)
@dataclass(frozen=True)
class Proposal:
    """What a threshold is, what the evidence says it should be, and why.

    There is deliberately nothing on this that applies it. No method, no flag and no field
    naming a destination: it is a sentence with numbers in it, addressed to whoever owns the
    budget. See `A_THRESHOLD_RETUNED_AGAINST_IMAGINED_DATA_IS_WORSE_THAN_THE_ASSUMPTION`.

    `proposed` is None when the readings cannot support one, and that is the ordinary case
    rather than an error. `because` then says how many readings it would have taken, so the
    answer to "why has this not been retuned" is a number rather than a shrug.
    """

    #: The constant this is about, named so a reader can find it.
    setting: str
    current: float
    #: What the evidence supports, or None when it supports nothing.
    proposed: float | None
    at_percentile: float
    readings: int
    because: str

    @property
    def is_supported(self) -> bool:
        return self.proposed is not None


def _unsupported(
    *, setting: str, current: float, at: float, readings: int, in_the_tail: int
) -> Proposal:
    """The proposal for a measurement that cannot place this percentile.

    One place rather than three, because the sentence is the same each time and the number in
    it is the thing that must not be got wrong: a reader deciding whether to keep collecting
    needs to know how much longer, and an approximate answer there is worse than none.
    """
    needed = samples_needed(at, in_the_tail)
    return Proposal(
        setting=setting,
        current=current,
        proposed=None,
        at_percentile=at,
        readings=readings,
        because=(
            f"{readings} reading(s) cannot place the {at:.0%} percentile: it would be the "
            f"largest of them rather than a property of the distribution. "
            f"{needed} are needed. "
            f"{A_PERCENTILE_OVER_TOO_FEW_READINGS_IS_THE_MAXIMUM_WEARING_A_NUMBER}"
        ),
    )


def retune_alert_fraction(
    *,
    measured: Distribution,
    ceiling_minor: int,
    current: tuple[float, ...] = DEFAULT_ALERT_FRACTIONS,
    fires_on: float = ALERTS_WORTH_READING,
    in_the_tail: int = SAMPLES_IN_THE_TAIL,
) -> Proposal:
    """Where the first warning fraction would sit if it fired as often as it should
    (M37.5.3.3).

    The percentile is `1 - fires_on`, so a target of one period in ten places the fraction at
    the ninetieth percentile of what periods actually cost. See
    `AN_ALERT_FRACTION_IS_TUNED_AGAINST_HOW_OFTEN_IT_FIRES`.

    The first fraction rather than all of them, and that is a limit worth stating rather than
    an omission. The second fraction is a different question: it is the one that means the
    ceiling is close, so it is tuned against how much warning somebody needs to act rather
    than against a firing rate, and nothing measured here says how long acting takes.

    A proposal above 1.0 is returned rather than clamped, and it is the most useful answer
    this function gives: it means the ninetieth percentile of real spending is already over
    the ceiling, so no warning fraction can be placed usefully and the ceiling is the thing
    that is wrong.
    """
    if ceiling_minor < 1:
        msg = "a ceiling of nothing has no fractions of it"
        raise RetuneError(msg)
    if not current:
        msg = "a budget with no alert fractions on it has no first fraction to retune"
        raise RetuneError(msg)
    at = 1.0 - fires_on
    first = current[0]
    if len(measured.readings) < samples_needed(at, in_the_tail):
        return _unsupported(
            setting="brain.ops.budgets.DEFAULT_ALERT_FRACTIONS[0]",
            current=first,
            at=at,
            readings=len(measured.readings),
            in_the_tail=in_the_tail,
        )
    at_percentile = measured.percentile(at)
    proposed = at_percentile / ceiling_minor
    fired_at_current = measured.share_above(math.floor(first * ceiling_minor))
    return Proposal(
        setting="brain.ops.budgets.DEFAULT_ALERT_FRACTIONS[0]",
        current=first,
        proposed=proposed,
        at_percentile=at,
        readings=len(measured.readings),
        because=(
            f"{first:.0%} of the ceiling fires on {fired_at_current:.0%} of periods in this "
            f"measurement, against a target of {fires_on:.0%}. The {at:.0%} percentile of "
            f"what periods actually cost is {at_percentile}, which is {proposed:.0%} of the "
            "ceiling. Not applied: "
            f"{A_THRESHOLD_RETUNED_AGAINST_IMAGINED_DATA_IS_WORSE_THAN_THE_ASSUMPTION}"
        ),
    )


def retune_daily_burst(
    *,
    measured: Distribution,
    monthly_allowance_minor: int,
    current: float = DAILY_BURST,
    admits: float = DAYS_A_BURST_CAP_MUST_ADMIT,
    in_the_tail: int = SAMPLES_IN_THE_TAIL,
    days_in_month: int = DAYS_IN_BUDGET_MONTH,
) -> Proposal:
    """The burst multiple that would have admitted this share of real days (M37.5.3.3).

    `brain.ops.budgets.DAILY_BURST` is a multiple of an even thirtieth of the monthly
    allowance, so the proposal is the observed day at the target percentile divided by that
    even day. The multiple rather than an amount, because the multiple is what the constant
    holds and a proposal expressed in another unit is one somebody converts by hand.

    **This is the function that usually refuses, and the refusal is the finding.** A cap
    meant to catch a loop has to sit above essentially every real day, which is a percentile
    of ninety-nine, which needs five hundred readings. Thirty days of daily totals is thirty
    readings. So a month of production does not retune this constant and the honest answer is
    the number of readings it would take, not a figure derived from the largest of thirty.
    """
    if monthly_allowance_minor < 1:
        msg = "an allowance of nothing has no daily share of it"
        raise RetuneError(msg)
    if days_in_month < 1:
        msg = f"a month of {days_in_month} day(s) has no even day in it"
        raise RetuneError(msg)
    setting = "brain.ops.budgets.DAILY_BURST"
    if len(measured.readings) < samples_needed(admits, in_the_tail):
        return _unsupported(
            setting=setting,
            current=current,
            at=admits,
            readings=len(measured.readings),
            in_the_tail=in_the_tail,
        )
    even_day = monthly_allowance_minor / days_in_month
    at_percentile = measured.percentile(admits)
    proposed = at_percentile / even_day
    return Proposal(
        setting=setting,
        current=current,
        proposed=proposed,
        at_percentile=admits,
        readings=len(measured.readings),
        because=(
            f"admitting {admits:.0%} of measured days needs {at_percentile} minor units, "
            f"which is {proposed:.1f} times an even day of {even_day:.1f}. The current "
            f"multiple is {current:.1f}. Not applied: "
            f"{A_THRESHOLD_RETUNED_AGAINST_IMAGINED_DATA_IS_WORSE_THAN_THE_ASSUMPTION}"
        ),
    )


def proposal_gaps(proposals: Sequence[Proposal]) -> tuple[str, ...]:
    """Every way a set of proposals would mislead whoever reads them.

    Two findings, and neither is about the arithmetic.

    A proposal that does not name the constant it is about is a number in a report that
    somebody applies to the nearest constant with a similar name, and the two alert fractions
    are exactly that hazard.

    A supported proposal identical to the current value is worth saying out loud rather than
    dropping: "the measurement agrees with the assumption" is the most useful result this
    module can produce and it is the one that looks like nothing happened.
    """
    findings: list[str] = []
    findings.extend(
        f"a proposal at the {one.at_percentile:.0%} percentile names no setting, so nothing "
        "says which constant it is about"
        for one in proposals
        if not one.setting.strip()
    )
    findings.extend(
        f"{one.setting} is proposed at its current value of {one.current}, which is the "
        "measurement agreeing with the assumption and reads in a list as no result at all"
        for one in proposals
        if one.proposed is not None and one.proposed == one.current
    )
    return tuple(findings)
