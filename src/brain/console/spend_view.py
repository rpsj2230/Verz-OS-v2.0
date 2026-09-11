"""What it cost, read by somebody who may not see all of it.

`brain.ops.spend` does the accounting: it holds `Actual`, the five dimensions a run is counted
against, and `spend_by`, which groups them. None of that knows who is looking. This is the
screen, and the screen is where the reach applies.

**A spend report is a count of things that exist, and that is the whole difficulty.** A
breakdown by person is a list of people; by agent, a list of agents; by department, a list of
departments. Every one of those is a directory to a reader who did not have it, so the rows
are filtered before they are grouped, not after: `visible` drops every row whose department
this reader's usage grant does not admit, and `spend_by` then groups what is left. Grouping
first and filtering the buckets afterwards would produce the same rows and a different total,
which is the bug this ordering exists to make impossible.

**A total is the disclosure, not the rows.** `Report.total_minor` is the sum of the lines the
reader is looking at and nothing else. A report that showed the company total beside a filtered
breakdown would hand over the hidden spend by subtraction, in one step, with every individual
figure correctly redacted. That is
`brain.audit.view.AuditPage`'s rule about page totals one aggregation up, and it is why there
is no `include_total` parameter anywhere here. See
`A_TOTAL_OVER_ROWS_THE_READER_MAY_NOT_SEE_IS_A_SUBTRACTION`.

**Machine traffic is excluded by default and the report says so.** `spend_by` takes the flag
and declines to have an opinion, which is right for the accounting layer; the opinion belongs
here. A spend report is read to understand what people are doing, and automated traffic is
both the larger figure and nobody's behaviour, so a report that silently included it would put
a nightly sync at the top of the list of expensive users. Excluded, and `Report.machine_included`
is on the object rather than in a caption, so a renderer cannot show the figure without the
qualifier. See `MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO`.

**A cost per answer is a distribution and the mean is the least useful number in it.** Question
costs are long-tailed: most are cheap, a few retrieve half a library, and the mean sits below
almost every expensive one. A budget set from a mean is a budget set from a figure nothing
costs. So `cost_per_answer` returns quantiles, and it returns each one only when there are
enough rows for it to be a rank rather than the largest row wearing a percentile's name. The
minimum is derived from the quantile rather than chosen: `ceil(1 / (1 - q))`, which is two rows
for a median, ten for a ninetieth and a hundred for a ninety-ninth. See
`A_PERCENTILE_NEEDS_ENOUGH_ROWS_TO_BE_A_RANK`.

**Pace is a comparison of two fractions and a per-run budget has neither.** A run does not
roll, so there is no elapsed fraction of it and a percentage would be a share of a window that
does not exist. `pace` refuses it rather than returning something a dashboard would draw. See
`A_PER_RUN_BUDGET_HAS_NO_PACE`.

**M21.3.4 is claimed for agents and not for question shapes, and the reason is a decision
somebody else already made correctly.** `spend.Actual` carries no question and no record id,
because a cost ledger with the question in it is a second copy of the business activity with
its own retention. So the dearest agents are here and the dearest question shapes cannot be:
answering that needs a shape on the ledger that is structural rather than content, and the
obvious one is whether the run fanned out and how many tools it called. Neither is on `Actual`
today. See `A_COST_LEDGER_HAS_NO_QUESTION_IN_IT`.

What was rejected. A `department` parameter, so a reader could narrow the report themselves:
`brain.console.screens.A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS` is the same refusal
about the same shape, and the argument carries here unchanged. That citation named
`scoped_authority.THE_AREAS_ARE_DERIVED_AND_NEVER_ASKED_FOR` until 2026-09-11 and no such
constant has ever existed anywhere in this repository. It was found by an agent writing
`usage_view.py`, which copied the name before checking it; a citation nobody can follow is a
rejected design whose argument has quietly gone missing, and the reader who goes looking
concludes the refusal was never really made. A row count beside each line,
which is a count of runs and therefore of activity the reader may not have. And a residual
bucket for rows out of reach, which is the hidden count with a label on it.

**A budget refusal that names a budget the reader could not have read is a disclosure wearing
an error message.** This is the half of the owner's hard stop that is easy to get wrong while
looking helpful. `brain.ops.spend.Refusal` names which budget bound, and M21.2.6 argues for
that: it is the caller's own budget, and a refusal saying only "no" sends a person to a help
desk that cannot help them. That argument holds for a person's own allowance and stops holding
one level up. "Your department's monthly budget is used up" tells somebody who cannot read
their department's spend that the department has a budget, that it is monthly, and that it is
gone, which is three facts they did not have and a running total they can watch across two
refusals. So `told_about` asks the same question `visible` asks about a row, through the same
`may_read_spend`, and a reader outside that reach gets a sentence naming no level, no period,
no subject and no instant. See
`A_BUDGET_REFUSAL_NAMING_A_BUDGET_THE_READER_CANNOT_READ_IS_A_DISCLOSURE`.

**What a stop may say out loud is that questions are paused, and `brain.ops.halt` is why.**
That module argues that a halt is not a permission decision, so it may say so: refusing
somebody in silence sends them to a support channel to report a bug that is not one. The same
carries here as long as the sentence names no budget. The line is between the *fact* of a
budget stop, which discloses nothing about what exists or who may see it, and *which* budget
stopped, which is somebody's spend.

**A budget refusal and a permission refusal must not look alike to an operator either**, and
that is the thing the recommendation against a hard stop was worried about made visible rather
than left silent. `budget_stops` puts every budget currently refusing on the screen at the
reader's own reach, and `brain.ops.admission.OPERATOR_ACTION` already separates the two at the
log: QUOTA says raise this allowance or leave it deliberately, PERMISSION says the model is
working. An operator who cannot tell the two apart goes to look at grants while a department
sits stopped. See `A_STOPPED_DEPARTMENT_MUST_NOT_READ_AS_A_PERMISSION_PROBLEM`.

**The cost review is the one section here that reads two modules and it has to.** A variance
without the correction beside it is a number somebody is asked to worry about with nothing to
do; a corrected estimator without the variance is a factor with no evidence next to it.
`cost_review` renders the pair, and it carries `long_enough` on the object rather than in a
caption for the same reason `Report.machine_included` is on the object: a renderer cannot show
a corrected factor without the qualifier that says how much of a month it was measured over.

That section is also why `brain.ops.retune` is imported by anything at all.
`brain.ops.controls` records `spend_correction` as a control, and until this screen existed
the estimator correction was called from a module nothing imported, which
`chains_worth_checking` reports as a caller as unreached as the control itself.

Task ids: M21.3.1, M21.3.2, M21.3.3, M21.3.5, M21.3.6
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.budget_stop import Stop
from brain.ops.budgets import Allowance, BudgetLevel, BudgetPeriod
from brain.ops.retune import Distribution as SpendWindow
from brain.ops.retune import Variance, post_launch_correction, variance
from brain.ops.spend import Actual, Correction, Dimension, Observation, Refusal, Rung, spend_by


class SpendViewError(Exception):
    """Raised when a spend report would state something the rows cannot support."""


# ------------------------------------------------------------------ written-down reasons
#: Why no report here carries a figure computed over rows it did not show.
A_TOTAL_OVER_ROWS_THE_READER_MAY_NOT_SEE_IS_A_SUBTRACTION: Final = (
    "A company total printed beside a breakdown the reader's grant narrowed hands over the "
    "hidden spend in one subtraction, with every individual figure correctly redacted. So a "
    "total here is the sum of the lines on the screen and there is no parameter that asks "
    "for another one."
)

#: Why the default excludes automated traffic, and why the flag is on the object.
MACHINE_TRAFFIC_IS_EXCLUDED_BY_DEFAULT_AND_THE_REPORT_SAYS_SO: Final = (
    "A spend report is read to understand what people are doing, and automated traffic is "
    "both the larger figure and nobody's behaviour: included silently, a nightly sync is the "
    "most expensive user in the company. It is excluded by default and the flag rides on the "
    "report rather than in a caption, so a renderer cannot show the figure without the "
    "qualifier that makes it mean something."
)

#: Why a quantile is withheld rather than computed from too few rows.
A_PERCENTILE_NEEDS_ENOUGH_ROWS_TO_BE_A_RANK: Final = (
    "A ninety-ninth percentile over eleven rows is the largest row wearing a percentile's "
    "name, and it is read as a typical worst case rather than as the single expensive "
    "question it actually is. The minimum sample is derived from the quantile and not "
    "chosen: a rank at q needs ceil(1 / (1 - q)) rows before it can sit anywhere but the "
    "top. Below that the quantile is absent, which a reader notices, rather than "
    "approximate, which they do not."
)

#: Why the mean is present and never on its own.
A_MEAN_OVER_A_LONG_TAIL_IS_A_FIGURE_NOTHING_COSTS: Final = (
    "Question costs are long-tailed, so the mean sits below almost every expensive question "
    "and above almost every cheap one. A budget set from it is set from a figure nothing "
    "costs. It is carried because it reconciles against a total and for no other reason, and "
    "a Distribution cannot be constructed without the count that says how much to trust it."
)

#: Why a per-run budget has no pace.
A_PER_RUN_BUDGET_HAS_NO_PACE: Final = (
    "Pace is spend so far against time so far, and a per-run budget does not roll: waiting "
    "does not refill it, so there is no elapsed fraction and a percentage would be a share "
    "of a window that does not exist. Refused rather than returned as zero, because a "
    "dashboard draws a zero."
)

#: Why the dearest question shapes are not answered here.
A_COST_LEDGER_HAS_NO_QUESTION_IN_IT: Final = (
    "brain.ops.spend.Actual deliberately carries no question, no answer and no record id, "
    "because a cost ledger holding them is a second copy of the business activity with its "
    "own retention. So the dearest agents can be reported and the dearest question shapes "
    "cannot, and the fix is a structural shape on the ledger rather than the question: "
    "whether the run fanned out, and how many tools it called."
)


#: Why a refusal names the budget to one reader and nothing at all to another.
A_BUDGET_REFUSAL_NAMING_A_BUDGET_THE_READER_CANNOT_READ_IS_A_DISCLOSURE: Final = (
    "M21.2.6 asks a refusal to name which budget was hit, and it is right about a person's "
    "own allowance: it is theirs, and a refusal saying only no sends them to a help desk that "
    "cannot help them. One level up the same sentence is a disclosure. Your department's "
    "monthly budget is used up tells somebody who cannot read that department's spend that it "
    "has a budget, that the budget is monthly, and that it is gone, and a second refusal a "
    "fortnight later says whether anything was raised in between. So the budget is named to a "
    "reader whose usage grant already admits that department's rows, and to nobody else, and "
    "the withheld form carries no level, no period, no subject and no end instant."
)

#: Why a stopped department must not read like a permission problem, to either reader.
A_STOPPED_DEPARTMENT_MUST_NOT_READ_AS_A_PERMISSION_PROBLEM: Final = (
    "A hard stop at a budget is an outage the system causes itself, which is the argument "
    "that was made against it and lost. What that argument bought instead is that the outage "
    "is never silent: an operator can see every budget currently refusing, at their own "
    "reach, on the screen that owns budgets, and brain.ops.admission.OPERATOR_ACTION gives "
    "QUOTA and PERMISSION different sentences about what to do. An operator who cannot tell "
    "the two apart spends the afternoon reading grants while a department sits stopped, and "
    "the person who was refused is told to raise a ticket about their access."
)

#: Why the review shows the variance and the corrected factor together.
A_VARIANCE_WITH_NO_CORRECTION_BESIDE_IT_IS_A_WORRY_WITH_NO_ACTION: Final = (
    "Spending twice the projection is a fact somebody can act on only next to what the "
    "estimator now says, and a corrected factor on its own is a number with no evidence "
    "beside it. Shown apart, the first reads as an alarm nobody can answer and the second as "
    "a change nobody asked for. The screen carries both or neither, and it carries whether "
    "the window was long enough on the object rather than in a caption, so a renderer cannot "
    "show the factor without the qualifier."
)

# ---------------------------------------------------------------- who may read what (M21.3.1)
#: The capability a usage report is read behind, taken from the screen that shows it rather
#: than written here, so the screen registry stays the single statement of what a screen needs.
USAGE_AUTHORITY: Final[Capability] = screen("usage").read.requires

#: The place field a spend row is admitted by. `Actual` carries a department and no other
#: place, so this is the whole of the row form. See `brain.console.govern._in_reach` and
#: `brain.ops.feedback` for the same pair of calls against the same key.
PLACE_FIELD: Final = "department"


def may_read_spend(
    department: str, entitlement: EntitlementSet, *, now: datetime | None = None
) -> bool:
    """Whether this reader's usage grant admits that department's spend.

    `EntitlementSet.scope_for` then `Scope.matches`, which is the pair every other row-level
    decision in this package makes. It is one function here rather than the same two lines in
    four places, because the answer now decides more than which rows a report shows: it also
    decides whether a refusal may name the budget that stopped somebody. Two copies of it
    would drift on the afternoon somebody widens the report, and the copy that drifts would be
    the one deciding what an error message is allowed to say.

    A reader holding nothing is admitted to nothing, and finds that out as an empty answer
    rather than as a refusal, because a refusal that named the capability would tell them a
    usage report exists.
    """
    scope = entitlement.scope_for(USAGE_AUTHORITY, now)
    if scope is None:
        return False
    return scope.matches({PLACE_FIELD: department})


def visible(
    actuals: Sequence[Actual], entitlement: EntitlementSet, *, now: datetime | None = None
) -> tuple[Actual, ...]:
    """The accounting rows this reader's usage grant admits, in the order given.

    One question per row, through `may_read_spend`, which is the single statement of that
    question in this module.
    """
    return tuple(one for one in actuals if may_read_spend(one.department, entitlement, now=now))


@dataclass(frozen=True)
class Line:
    """One bucket of a breakdown: what it is called and what it cost."""

    key: str
    cost_minor: int


@dataclass(frozen=True)
class Report:
    """A spend breakdown in one dimension, at one reader's reach.

    `total_minor` is the sum of `lines` and is asserted to be. It is on the object rather than
    left to the renderer because a renderer that adds them up itself will one day be handed a
    truncated list, and the figure it prints will then be the one nobody can reconcile.
    """

    dimension: Dimension
    lines: tuple[Line, ...]
    machine_included: bool
    total_minor: int

    def __post_init__(self) -> None:
        if self.total_minor != sum(one.cost_minor for one in self.lines):
            msg = (
                "the total does not equal the lines shown. "
                f"{A_TOTAL_OVER_ROWS_THE_READER_MAY_NOT_SEE_IS_A_SUBTRACTION}"
            )
            raise SpendViewError(msg)


def spend_report(
    actuals: Sequence[Actual],
    entitlement: EntitlementSet,
    dimension: Dimension,
    *,
    now: datetime | None = None,
    include_machine: bool = False,
) -> Report:
    """Spend in one dimension, over the rows this reader may see (M21.3.1, M21.3.2).

    Filtered and then grouped, in that order. Grouping first and dropping buckets afterwards
    gives the same lines and a different total, and the total is the half that leaks.

    Lines are ordered by cost, dearest first, with the key as the tie-break so two runs of the
    same report do not disagree about the order of two equal figures.
    """
    rows = visible(actuals, entitlement, now=now)
    totals = spend_by(rows, dimension, include_machine=include_machine)
    lines = tuple(
        Line(key=key, cost_minor=cost)
        for key, cost in sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    )
    return Report(
        dimension=dimension,
        lines=lines,
        machine_included=include_machine,
        total_minor=sum(one.cost_minor for one in lines),
    )


def dearest(report: Report, limit: int) -> tuple[Line, ...]:
    """The most expensive lines of a report, dearest first (M21.3.4, agents only).

    A slice of what the reader is already looking at, so it discloses nothing the report did
    not. It carries no rank number and no "of N", for the same reason the report carries no
    total over rows it did not show.

    A limit of nothing or less is refused rather than returning everything, because a caller
    computing the limit from a page size and getting zero wants to know.
    """
    if limit < 1:
        msg = f"a list of the {limit} dearest lines is not a list"
        raise SpendViewError(msg)
    return report.lines[:limit]


# --------------------------------------------------------------- cost per answer (M21.3.3)
#: The quantiles reported, ascending. Three rather than a full curve: a median, a
#: ninetieth for what a bad day looks like, and a ninety-ninth for what a budget has to
#: survive. Each carries its own minimum sample, so adding one here does not weaken the rest.
QUANTILES: Final[tuple[float, ...]] = (0.5, 0.9, 0.99)


def minimum_rows(quantile: float) -> int:
    """How many observations a quantile needs before it can be a rank rather than the maximum.

    `ceil(1 / (1 - q))`. Below that the nearest-rank index lands on the last observation, so
    the figure is the largest row with a percentile's name on it; at exactly that many it is
    the first sample size at which it can differ from the maximum, and every larger sample
    separates the two further. Derived rather than chosen, for the reason
    `A_PERCENTILE_NEEDS_ENOUGH_ROWS_TO_BE_A_RANK` gives.

    In exact arithmetic, because `1 / (1 - 0.9)` is 10.000000000000002 in binary floating
    point and `ceil` of that is eleven. A ninetieth percentile withheld from a sample of ten
    is the sort of wrong that looks like a deliberate conservatism and is a rounding error.
    """
    if not 0.0 < quantile < 1.0:
        msg = f"{quantile} is not a quantile; 0 and 1 are the minimum and the maximum"
        raise SpendViewError(msg)
    return math.ceil(1 / (1 - Fraction(str(quantile))))


@dataclass(frozen=True)
class Distribution:
    """What a set of answers cost: how many, the mean, and the quantiles the sample supports.

    The count is required and comes first, because the mean is only readable next to it. See
    `A_MEAN_OVER_A_LONG_TAIL_IS_A_FIGURE_NOTHING_COSTS`.

    A quantile the sample cannot support is absent from `quantiles` rather than present and
    approximate. A reader notices an absent figure; they do not notice an unreliable one.
    """

    count: int
    mean_minor: float
    quantiles: Mapping[float, int]

    def __post_init__(self) -> None:
        if self.count < 1:
            msg = "a distribution over no observations is not a distribution"
            raise SpendViewError(msg)
        for quantile in self.quantiles:
            if self.count < minimum_rows(quantile):
                msg = (
                    f"the {quantile} quantile is stated over {self.count} row(s) and needs "
                    f"{minimum_rows(quantile)}. {A_PERCENTILE_NEEDS_ENOUGH_ROWS_TO_BE_A_RANK}"
                )
                raise SpendViewError(msg)


def distribution(costs: Sequence[int], *, quantiles: Sequence[float] = QUANTILES) -> Distribution:
    """The distribution of a set of costs, with only the quantiles the sample supports.

    Nearest-rank, which needs no interpolation and therefore reports a figure some answer
    actually cost. An interpolated percentile is a number between two real ones, and on a
    long-tailed set the gap between the two is the whole of the interesting part.
    """
    if not costs:
        msg = "a distribution over no observations is not a distribution"
        raise SpendViewError(msg)
    ordered = sorted(costs)
    count = len(ordered)
    found: dict[float, int] = {}
    for quantile in quantiles:
        if count < minimum_rows(quantile):
            continue
        rank = math.ceil(Fraction(str(quantile)) * count)
        found[quantile] = ordered[rank - 1]
    return Distribution(
        count=count,
        mean_minor=sum(ordered) / count,
        quantiles=MappingProxyType(found),
    )


def cost_per_answer(
    actuals: Sequence[Actual],
    entitlement: EntitlementSet,
    *,
    now: datetime | None = None,
    include_machine: bool = False,
) -> Distribution:
    """What one answer costs, over the rows this reader may see (M21.3.3).

    One observation per accounting row, because a row is one completed run and a run is one
    answer. Machine traffic excluded by default like every other report here: a distribution
    with a nightly sync in it describes the sync.
    """
    rows = [
        one.cost_minor
        for one in visible(actuals, entitlement, now=now)
        if include_machine or not one.machine
    ]
    return distribution(rows)


# ------------------------------------------------------------ budget against pace (M21.3.5)
@dataclass(frozen=True)
class Pace:
    """How much of a budget has gone against how much of its period has.

    Two fractions rather than one number, because the ratio alone loses the size of what it is
    a ratio of: a department a fifth of the way through the month having spent a quarter of
    its budget is the same ratio as one nine tenths through having spent a shade over, and
    only one of them is worth a message.
    """

    spent_fraction: float
    elapsed_fraction: float

    @property
    def ahead(self) -> bool:
        """Whether spend is running faster than time. The comparison the screen is read for.

        Strictly faster. A quarter of the money a quarter of the way through the month is the
        arrangement a budget is meant to produce, and flagging it is how a screen teaches
        people to ignore it.
        """
        return self.spent_fraction > self.elapsed_fraction


def pace(allowance: Allowance, *, started_at: datetime, ends_at: datetime, now: datetime) -> Pace:
    """Budget consumption against the elapsed period (M21.3.5).

    Refuses a per-run budget, which has no period to be part-way through. Refuses a period
    that ends before it starts, and an instant outside it: a pace computed from a `now` after
    the period closed reports a fraction above one, which a dashboard draws as an overspend
    that already ended.

    There is deliberately no guard here against a ceiling of zero. `brain.ops.budgets.BudgetRow`
    refuses one in its own constructor, calling it a suspension wearing a budget's clothes, so
    an `Allowance` carrying one cannot be built and a check for it here would be a guard no
    test could reach. That is the defect this repository keeps finding in dataclass validators
    and it is not worth adding on purpose.
    """
    if allowance.row.period is BudgetPeriod.RUN:
        msg = f"a per-run budget has no pace. {A_PER_RUN_BUDGET_HAS_NO_PACE}"
        raise SpendViewError(msg)
    if ends_at <= started_at:
        msg = "a period that ends when or before it starts has no elapsed fraction"
        raise SpendViewError(msg)
    if not started_at <= now <= ends_at:
        msg = (
            f"{now.isoformat()} is outside the period it is being paced against, so the "
            "fraction would be below nothing or above everything"
        )
        raise SpendViewError(msg)
    return Pace(
        spent_fraction=allowance.spent_minor / allowance.row.ceiling_minor,
        elapsed_fraction=(now - started_at).total_seconds()
        / (ends_at - started_at).total_seconds(),
    )


# ------------------------------------------- refusals and degradations, with cause (M21.3.6)
@dataclass(frozen=True)
class Setback:
    """One request that did not run as asked, and why.

    Assembled by the caller from a `brain.ops.spend.Preflight` and the department the request
    came from, because a `Preflight` carries no place and a report has to be filtered by one.
    Carries no figure and no subject, which is `spend.Refusal`'s own shape and its reasons
    carry here unchanged.

    A refusal happens at exactly one rung, and the constructor holds the two together: a
    `REFUSE` row with no refusal has lost which budget bound, and a refusal at a lower rung
    describes a request that ran and was refused.
    """

    department: str
    at: datetime
    rung: Rung
    refusal: Refusal | None

    def __post_init__(self) -> None:
        if not self.department.strip():
            msg = "a setback with no department cannot be shown to anybody at a reach"
            raise SpendViewError(msg)
        if (self.rung is Rung.REFUSE) != (self.refusal is not None):
            msg = (
                f"a setback at the {self.rung.name} rung "
                f"{'carries' if self.refusal else 'carries no'} refusal, and a refusal "
                "happens at the refuse rung and nowhere else"
            )
            raise SpendViewError(msg)

    @property
    def cause(self) -> str:
        """Which budget bound, or which sacrifice was made. Never a figure and never a person."""
        return self.refusal.budget if self.refusal is not None else self.rung.name.lower()


@dataclass(frozen=True)
class Friction:
    """Refusals and degradations the reader may see, counted by what caused them.

    Two maps rather than a list of rows, because the question a screen asks here is whether
    something is repeatedly hitting a boundary, and the answer to that is a pattern.
    `brain.console.auditor` reached the same shape from the audit side.

    No total beyond these counts, and no residual bucket for rows out of reach.
    """

    by_rung: Mapping[Rung, int]
    by_cause: Mapping[str, int]


def friction(
    setbacks: Sequence[Setback], entitlement: EntitlementSet, *, now: datetime | None = None
) -> Friction:
    """Every refusal and degradation this reader may see, with its cause (M21.3.6).

    Filtered by the same grant and the same place field as the spend report, so a reader
    cannot learn from the friction screen that a department exists which the usage screen
    declined to mention.

    A cause is the budget that bound or the sacrifice that was made. Both are the reader's own
    department's, both come from closed vocabularies, and neither names a person, an amount or
    a capability. See `brain.ops.spend.A_REFUSAL_CARRIES_NO_FIGURE`.
    """
    rungs: dict[Rung, int] = {}
    causes: dict[str, int] = {}
    for one in setbacks:
        if not may_read_spend(one.department, entitlement, now=now):
            continue
        rungs[one.rung] = rungs.get(one.rung, 0) + 1
        causes[one.cause] = causes.get(one.cause, 0) + 1
    return Friction(by_rung=MappingProxyType(rungs), by_cause=MappingProxyType(causes))


# --------------------------------------- a budget that is refusing until the period rolls
#: What somebody outside a budget's reach is told when it has stopped them.
#:
#: Names no level, no period, no subject, no figure and no end instant, so two refusals a
#: fortnight apart are the same sentence and subtract into nothing. It does say that questions
#: are paused and that this is not about their access, which is `brain.ops.halt`'s argument
#: about a halt applied to a stop: refusing somebody in silence sends them to a support channel
#: to report a bug that is not one, and the fact of a pause discloses nothing about what exists
#: or who may see it.
NOTHING_TO_NAME: Final = (
    "Questions are paused because a budget is used up. Nothing about your access has changed."
)


@dataclass(frozen=True)
class StopRow:
    """One budget stop, at the place it is reported.

    Assembled by the caller from a `brain.ops.budget_stop.Stop` and the department the stop is
    reported at, exactly as `Setback` is assembled from a `Preflight` and a department, and for
    the same reason: a stop carries a budget's own subject, which is a department only at one
    of four levels, and a report has to be filtered by a place at all four.
    """

    stop: Stop
    department: str

    def __post_init__(self) -> None:
        if not self.department.strip():
            msg = "a stop with no department cannot be shown to anybody at a reach"
            raise SpendViewError(msg)


@dataclass(frozen=True)
class Told:
    """What one asker is told about the stop refusing them. Two shapes, and one names nothing.

    `until` is present only on the shape that names the budget, so the withheld form has
    nothing for a renderer to show: a date is itself a disclosure, because a boundary tomorrow
    and a boundary on the first say whether the exhausted ceiling was daily or monthly.

    The constructor holds the two together, so a withheld notice cannot be built carrying a
    specific sentence and a specific one cannot be built without its instant.
    """

    message: str
    until: datetime | None

    def __post_init__(self) -> None:
        if (self.until is None) != (self.message == NOTHING_TO_NAME):
            msg = (
                "this refusal names a budget and no instant, or an instant and no budget. "
                f"{A_BUDGET_REFUSAL_NAMING_A_BUDGET_THE_READER_CANNOT_READ_IS_A_DISCLOSURE}"
            )
            raise SpendViewError(msg)

    @property
    def names_the_budget(self) -> bool:
        """Whether this reader was told which budget stopped them."""
        return self.until is not None


def told_about(row: StopRow, entitlement: EntitlementSet, *, now: datetime | None = None) -> Told:
    """What this asker may be told about the budget stop refusing them (M21.3.6).

    Two readers and one rule. Somebody whose usage grant already admits that department's rows
    is told which budget bound and when it ends, in `brain.ops.spend.Refusal`'s own words
    rather than a second wording. Everybody else is told that questions are paused and nothing
    else at all. See `A_BUDGET_REFUSAL_NAMING_A_BUDGET_THE_READER_CANNOT_READ_IS_A_DISCLOSURE`.

    **A person's own allowance is always theirs to be told about**, whatever they may read of
    a department's spend, and that is what keeps M21.2.6 working for the case it was written
    for. Their own ceiling is a fact about them; the department's is a fact about everybody
    else's spending as well.
    """
    if _their_own(row.stop, entitlement) or may_read_spend(row.department, entitlement, now=now):
        return Told(
            message=Refusal(level=row.stop.level, period=row.stop.period).message,
            until=row.stop.until,
        )
    return Told(message=NOTHING_TO_NAME, until=None)


def _their_own(stop: Stop, entitlement: EntitlementSet) -> bool:
    """Whether this stop is on the reader's own personal allowance and nobody else's."""
    return stop.level is BudgetLevel.USER and stop.subject == entitlement.principal_id


def budget_stops(
    rows: Sequence[StopRow],
    entitlement: EntitlementSet,
    *,
    at: datetime,
    now: datetime | None = None,
) -> tuple[StopRow, ...]:
    """Every budget currently refusing that this reader may see, in the order given (M21.3.6).

    The operator's half of the owner's decision, and the reason it is built at all. A hard stop
    is an outage the system causes itself, so somebody has to be able to look at one screen and
    see that questions are being refused for money rather than for permission. See
    `A_STOPPED_DEPARTMENT_MUST_NOT_READ_AS_A_PERMISSION_PROBLEM`.

    Filtered by the same grant and the same place field as the spend report, so a reader cannot
    learn from the stop board that a department exists which the usage screen declined to
    mention. A stop whose period has rolled is absent, because `Stop.in_force_at` is what
    decides that and nothing here keeps a second opinion about when a window closes.

    No count of what was dropped and no residual bucket, for the reason `Report` carries no
    total over rows it did not show.
    """
    return tuple(
        one
        for one in rows
        if one.stop.in_force_at(at) and may_read_spend(one.department, entitlement, now=now)
    )


# ------------------------------------------------- the cost review after launch (M37.5.3)
@dataclass(frozen=True)
class CostReview:
    """What the first window actually cost, against what was projected, and what follows.

    `long_enough` is repeated from the variance rather than left to be read off it, because
    the correction below is the figure a renderer will show large and the qualifier belongs on
    the same object. See `A_VARIANCE_WITH_NO_CORRECTION_BESIDE_IT_IS_A_WORRY_WITH_NO_ACTION`.
    """

    variance: Variance
    correction: Correction
    long_enough: bool


def cost_review(
    *,
    projected_minor: int,
    measured: SpendWindow,
    prior: Correction,
    observations: Sequence[Observation],
) -> CostReview:
    """The pair a person reads thirty days after launch.

    Both halves come from `brain.ops.retune`, which owns the window rule, rather than being
    recomputed here: this module decides what a reader may see and the arithmetic belongs
    where the argument for it is. `post_launch_correction` returns the prior unchanged with a
    reason when the window is short, so a review rendered in the first fortnight shows a
    variance, an uncorrected factor and a sentence saying why, which is the honest version of
    that screen rather than an empty one.
    """
    measured_variance = variance(projected_minor=projected_minor, measured=measured)
    return CostReview(
        variance=measured_variance,
        correction=post_launch_correction(prior, observations, measured),
        long_enough=measured_variance.long_enough,
    )
