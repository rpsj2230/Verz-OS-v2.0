"""The spend screens: what a reader may see of what it cost, and what no report may say.

Two things are being tested here and they pull in opposite directions. A spend report has to be
useful enough that somebody can act on it, and it must not become a directory of the people,
agents and departments the reader has no grant over. Every refusal below is one of those two
holding the other in place.

The quantile tests are the other half. `cost_per_answer` reports figures that were actually
paid and withholds the ones its sample cannot support, and both halves are asserted: a
percentile that is silently the maximum is worse than an absent one, because it is read as a
typical bad case rather than as the single expensive question it is.

Task ids: M21.3.1, M21.3.2, M21.3.3, M21.3.5, M21.3.6
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from brain.console.screens import screen
from brain.console.spend_view import (
    QUANTILES,
    CostReview,
    Distribution,
    Friction,
    Line,
    Report,
    Setback,
    SpendViewError,
    cost_per_answer,
    cost_review,
    dearest,
    distribution,
    friction,
    minimum_rows,
    pace,
    spend_report,
    visible,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.ops.budgets import (
    Allowance,
    BudgetError,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
)
from brain.ops.retune import MEASUREMENT_WINDOW_DAYS
from brain.ops.retune import Distribution as SpendWindow
from brain.ops.spend import (
    NO_CORRECTION,
    Actual,
    Dimension,
    Observation,
    Refusal,
    Rung,
    total_minor,
)

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
USAGE = Capability(value="read:usage")

MAINTENANCE = "maintenance"
FINANCE = "finance"


def a_run(
    *,
    department: str,
    cost: int,
    principal: str = "u_asker",
    agent: str | None = "a_helper",
    model: str = "big",
    lane: Lane = Lane.ANSWER,
    machine: bool = False,
    at: datetime = NOW,
) -> Actual:
    """One completed run, through `Actual`'s own validators."""
    return Actual(
        principal_id=principal,
        principal_kind=PrincipalKind.SERVICE if machine else PrincipalKind.HUMAN,
        traffic=TrafficClass.AUTOMATION if machine else TrafficClass.HUMAN_INTERACTIVE,
        department=department,
        agent_id=agent,
        model=model,
        lane=lane,
        cost_minor=cost,
        at=at,
    )


def a_reader(*departments: str) -> EntitlementSet:
    """Somebody holding the usage grant over one department, or over none at all."""
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(Grant(capability=USAGE, scope=Scope.department(one)) for one in departments),
    )


def everybody() -> EntitlementSet:
    """Somebody holding the usage grant company wide."""
    return EntitlementSet(
        principal_id="u_admin",
        grants=(Grant(capability=USAGE, scope=Scope.unrestricted()),),
    )


def a_budget(*, ceiling: int, period: BudgetPeriod, spent: int) -> Allowance:
    """One department budget with spend against it, through the real constructors."""
    return Allowance(
        row=BudgetRow(
            level=BudgetLevel.DEPARTMENT,
            subject=MAINTENANCE,
            period=period,
            ceiling_minor=ceiling,
            version=1,
            author="u_admin",
            effective_from=NOW - timedelta(days=40),
            reason="a figure written for this test",
        ),
        spent_minor=spent,
    )


# --- who may see what (M21.3.1) ----------------------------------------------------------


def test_a_reader_sees_the_departments_their_usage_grant_admits_and_no_others() -> None:
    """M21.3.1. A breakdown by department is a list of departments, so it is filtered by the
    reader's own grant before anything is grouped.

    Two departments either side of the boundary, so the difference between the two answers is
    the reader's scope and nothing else.

    Delete this and the usage screen is a directory of every department in the company behind
    a grant over one of them."""
    runs = [a_run(department=MAINTENANCE, cost=100), a_run(department=FINANCE, cost=900)]

    mine = spend_report(runs, a_reader(MAINTENANCE), Dimension.DEPARTMENT, now=NOW)

    assert [one.key for one in mine.lines] == [MAINTENANCE]
    assert mine.total_minor == 100


def test_the_total_is_the_sum_of_the_lines_shown_and_never_the_company_figure() -> None:
    """**The rows are not the disclosure; the total is.** A company figure printed beside a
    filtered breakdown hands over the hidden spend in one subtraction, with every individual
    line correctly redacted.

    Asserted against `brain.ops.spend.total_minor` over everything, which is the figure that
    must not appear, rather than only against the sum of the lines: a report that carried the
    company total would still satisfy an assertion that the lines add up to something.

    Delete this and the usage screen tells a department head exactly what every other
    department spent."""
    runs = [a_run(department=MAINTENANCE, cost=100), a_run(department=FINANCE, cost=900)]

    mine = spend_report(runs, a_reader(MAINTENANCE), Dimension.DEPARTMENT, now=NOW)

    assert mine.total_minor == sum(one.cost_minor for one in mine.lines)
    assert mine.total_minor != total_minor(runs)


def test_a_report_whose_total_disagrees_with_its_lines_cannot_be_constructed() -> None:
    """The guard on the guard. `spend_report` computes the total from the lines it built, and
    a later edit that computed it from the unfiltered rows would be one character of
    difference and invisible in review.

    Refused in the constructor so no other producer of a `Report` can get it wrong either.

    Delete this and the invariant lives only in the one function that happens to hold it."""
    with pytest.raises(SpendViewError, match="does not equal the lines shown"):
        Report(
            dimension=Dimension.DEPARTMENT,
            lines=(Line(key=MAINTENANCE, cost_minor=100),),
            machine_included=False,
            total_minor=1_000,
        )


def test_rows_are_filtered_before_they_are_grouped_and_not_after() -> None:
    """The ordering, tested where the two orders actually differ.

    One person spends in both departments. Filtering first gives their maintenance spend;
    grouping first and then dropping buckets the reader cannot see keeps the whole person,
    finance included, because the bucket is keyed on the person and not the place.

    That is not a hypothetical rewrite: grouping first is the cheaper implementation and it
    produces the same list of names, which is why it would survive review.

    Delete this and a department head reads a colleague's company-wide spend on their own
    department's page."""
    runs = [
        a_run(department=MAINTENANCE, cost=100, principal="u_both"),
        a_run(department=FINANCE, cost=900, principal="u_both"),
    ]

    mine = spend_report(runs, a_reader(MAINTENANCE), Dimension.PRINCIPAL, now=NOW)

    assert [(one.key, one.cost_minor) for one in mine.lines] == [("u_both", 100)]


def test_a_reader_holding_no_usage_grant_gets_nothing_and_is_told_nothing() -> None:
    """Empty rather than a refusal, because a refusal naming the capability would tell
    somebody a usage report exists to be refused.

    Both halves asserted: `visible` returns nothing, and the report built from it has no
    lines and a total of nothing rather than a total over everything.

    Delete this and the absence of a grant becomes an oracle for the presence of a screen."""
    runs = [a_run(department=MAINTENANCE, cost=100)]
    nobody = a_reader()

    assert visible(runs, nobody, now=NOW) == ()

    empty = spend_report(runs, nobody, Dimension.DEPARTMENT, now=NOW)

    assert empty.lines == ()
    assert empty.total_minor == 0


def test_the_lines_are_ordered_dearest_first_with_the_key_as_the_tie_break() -> None:
    """A report read to find what is expensive is read from the top. The tie-break is not
    decoration: two equal figures in an arbitrary order make two runs of the same report
    disagree, and somebody then reconciles a difference that is not there.

    Delete this and the ordering is whatever the grouping dictionary happened to produce."""
    runs = [
        a_run(department=MAINTENANCE, cost=100, model="b"),
        a_run(department=MAINTENANCE, cost=300, model="c"),
        a_run(department=MAINTENANCE, cost=100, model="a"),
    ]

    lines = spend_report(runs, everybody(), Dimension.MODEL, now=NOW).lines

    assert [(one.key, one.cost_minor) for one in lines] == [("c", 300), ("a", 100), ("b", 100)]


def test_the_usage_capability_is_the_screens_own_and_not_one_invented_here() -> None:
    """A capability invented for this module would be a second grant over the same rows, and
    an administrator reviewing the console's screens would never meet it.

    Anchored to the literal as well as to the screen, so the pair is not compared against
    itself: repointing the constant at the screen's requirement and repointing the screen
    together would otherwise pass.

    Delete this and the usage report is read behind a grant nobody reviews."""
    from brain.console.spend_view import USAGE_AUTHORITY

    assert USAGE_AUTHORITY.value == "read:usage"
    assert screen("usage").read.requires == USAGE_AUTHORITY


def test_there_is_no_parameter_that_widens_the_report() -> None:
    """Asserted on the signature, because the wrong version arrives as a parameter rather than
    as a changed calculation: a `department` argument so a reader can narrow their own page,
    or an `include_total` so a renderer can show the company figure.

    Behaviour alone would keep passing on the day either lands.

    Delete this and the report grows the parameter, and the filtering above becomes advisory."""
    taken = inspect.signature(spend_report).parameters

    assert "department" not in taken
    assert "include_total" not in taken
    assert "entitlement" in taken
    assert "include_machine" in taken


# --- machine traffic (M21.3.2) -----------------------------------------------------------


def test_machine_traffic_is_excluded_by_default_and_the_report_carries_which() -> None:
    """M21.3.2. Included silently, a nightly sync is the most expensive user in the company.

    The flag is asserted on the report as well as the figure, because a caption in a template
    is a caption somebody removes while the number stays.

    Delete this and the two figures are indistinguishable on the screen."""
    runs = [
        a_run(department=MAINTENANCE, cost=100, principal="u_person"),
        a_run(department=MAINTENANCE, cost=900, principal="p_sync", machine=True),
    ]

    people = spend_report(runs, everybody(), Dimension.PRINCIPAL, now=NOW)
    everything = spend_report(runs, everybody(), Dimension.PRINCIPAL, now=NOW, include_machine=True)

    assert people.total_minor == 100
    assert people.machine_included is False
    assert everything.total_minor == 1_000
    assert everything.machine_included is True


# --- cost per answer (M21.3.3) -----------------------------------------------------------


def test_the_minimum_sample_for_a_quantile_is_derived_from_the_quantile() -> None:
    """M21.3.3. Two rows for a median, ten for a ninetieth, a hundred for a ninety-ninth.

    The literals are written here rather than computed from the same expression the module
    uses, so a change to the derivation fails rather than moving both sides together.

    Delete this and the minimum becomes a number somebody picked, and the first thing that
    happens to a picked number is that it gets lowered to make a screen show something."""
    assert minimum_rows(0.5) == 2
    assert minimum_rows(0.9) == 10
    assert minimum_rows(0.99) == 100

    for impossible in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(SpendViewError, match="is not a quantile"):
            minimum_rows(impossible)


def test_a_quantile_is_absent_until_the_sample_can_rank_it() -> None:
    """A ninety-ninth percentile over ten rows is the largest row wearing a percentile's name,
    and it is read as a typical bad case.

    Ten rows and then a hundred, so a function that always returned every quantile and one
    that never returned any both fail.

    Delete this and a screen shows a p99 computed from eleven questions."""
    ten = distribution([1] * 9 + [10_000])
    hundred = distribution([1] * 99 + [10_000])

    assert set(ten.quantiles) == {0.5, 0.9}
    assert set(hundred.quantiles) == set(QUANTILES)


def test_a_distribution_cannot_be_constructed_stating_a_quantile_its_count_cannot_support() -> None:
    """Refused in the constructor rather than only in the producer, so a second producer, or a
    test fixture, cannot assemble the thing the producer refuses to compute.

    Delete this and the rule lives in one function instead of in the type."""
    with pytest.raises(SpendViewError, match="needs 100"):
        Distribution(count=5, mean_minor=1.0, quantiles={0.99: 10_000})


def test_a_distribution_over_no_observations_is_refused_by_both_doors() -> None:
    """No answers is not a cost of zero, and a mean over nothing is a division nobody wants to
    see the result of.

    Both the function and the constructor, because they are two ways in.

    Delete this and an empty period renders as a free one."""
    with pytest.raises(SpendViewError, match="not a distribution"):
        distribution([])
    with pytest.raises(SpendViewError, match="not a distribution"):
        Distribution(count=0, mean_minor=0.0, quantiles={})


def test_every_quantile_reported_is_a_cost_something_actually_paid() -> None:
    """Nearest-rank rather than interpolated. An interpolated percentile is a number between
    two real ones, and on a long-tailed set the gap between those two is the interesting part.

    Delete this and the screen reports figures no question ever cost."""
    costs = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]

    found = distribution(costs)

    assert set(found.quantiles.values()) <= set(costs)
    assert found.count == len(costs)


def test_the_mean_sits_between_the_median_and_the_tail_and_describes_neither() -> None:
    """The argument M21.3.3 is making, stated as a test. Ninety cheap questions and ten
    expensive ones: the median is a cheap question, the ninety-ninth percentile is an
    expensive one, and the mean is a thousand times the first and a tenth of the second.

    A budget set from that mean refuses most of the expensive questions it was sized for and
    tells nobody why. A budget set from the ninety-ninth admits them.

    Delete this and `cost_per_answer` can quietly become a mean with extra fields."""
    found = distribution([1] * 90 + [10_000] * 10)

    assert found.quantiles[0.5] == 1
    assert found.quantiles[0.99] == 10_000
    assert found.quantiles[0.5] < found.mean_minor < found.quantiles[0.99]


def test_cost_per_answer_is_one_observation_per_run_at_the_readers_reach() -> None:
    """One accounting row is one completed run is one answer. Machine rows excluded by
    default, like every other report here, because a distribution with a nightly sync in it
    describes the sync.

    Delete this and the distribution is computed over rows the reader may not see, which is
    the total leak wearing a percentile."""
    runs = [
        a_run(department=MAINTENANCE, cost=10),
        a_run(department=MAINTENANCE, cost=30),
        a_run(department=FINANCE, cost=5_000),
        a_run(department=MAINTENANCE, cost=9_999, machine=True),
    ]

    mine = cost_per_answer(runs, a_reader(MAINTENANCE), now=NOW)

    assert mine.count == 2
    assert mine.quantiles[0.5] == 10


# --- budget against pace (M21.3.5) -------------------------------------------------------


def test_a_per_run_budget_has_no_pace() -> None:
    """M21.3.5. A run does not roll, so there is no elapsed fraction of it and a percentage
    would be a share of a window that does not exist.

    Refused rather than returned as zero, because a dashboard draws a zero and a reader reads
    it as a budget nothing has been spent against.

    Delete this and the per-run ceiling appears on the pace screen at nought per cent all
    month."""
    with pytest.raises(SpendViewError, match="no pace"):
        pace(
            a_budget(ceiling=1_000, period=BudgetPeriod.RUN, spent=500),
            started_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=1),
            now=NOW,
        )


def test_spending_faster_than_time_is_ahead_and_both_fractions_are_carried() -> None:
    """The positive case, and the reason there are two numbers rather than one. A fifth of the
    way through the month having spent a quarter is the same ratio as nine tenths through
    having spent a shade over, and only one of them is worth a message.

    Delete this and the screen shows a ratio with nothing to read it against."""
    month = a_budget(ceiling=1_000, period=BudgetPeriod.MONTH, spent=250)
    started = datetime(2026, 3, 1, tzinfo=UTC)
    ends = datetime(2026, 3, 31, tzinfo=UTC)

    ahead = pace(month, started_at=started, ends_at=ends, now=datetime(2026, 3, 7, tzinfo=UTC))
    behind = pace(month, started_at=started, ends_at=ends, now=datetime(2026, 3, 28, tzinfo=UTC))

    assert ahead.spent_fraction == 0.25
    assert ahead.ahead is True
    assert behind.spent_fraction == 0.25
    assert behind.ahead is False


def test_a_budget_exactly_on_pace_is_not_ahead_of_it() -> None:
    """The boundary, which a mutation found and nothing else was watching: `>=` in place of
    `>` passed every other test in this file.

    A quarter of the money a quarter of the way through the month is the arrangement a budget
    is meant to produce, and reporting it as running fast is how a screen teaches people to
    ignore it. `ahead` means faster than time, and equal is not faster.

    A quarter is used because it is exact in binary floating point, so this asserts the
    comparison rather than the arithmetic that fed it.

    Delete this and the pace screen flags every department that is spending precisely as
    planned."""
    month = a_budget(ceiling=1_000, period=BudgetPeriod.MONTH, spent=250)
    started = datetime(2026, 3, 1, tzinfo=UTC)
    ends = datetime(2026, 3, 31, tzinfo=UTC)
    quarter_way = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    level = pace(month, started_at=started, ends_at=ends, now=quarter_way)

    assert level.spent_fraction == 0.25
    assert level.elapsed_fraction == 0.25
    assert level.ahead is False


def test_a_pace_needs_an_instant_inside_the_period_it_paces() -> None:
    """A `now` past the end reports an elapsed fraction above one, which a dashboard draws as
    an overspend that already finished. A `now` before the start reports a negative one.

    Both ends, because a guard written for one of them passes a test that only asks about the
    other.

    Delete this and last month's budget renders as this month's emergency."""
    month = a_budget(ceiling=1_000, period=BudgetPeriod.MONTH, spent=250)
    started = datetime(2026, 3, 1, tzinfo=UTC)
    ends = datetime(2026, 3, 31, tzinfo=UTC)

    for outside in (datetime(2026, 2, 28, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)):
        with pytest.raises(SpendViewError, match="outside the period"):
            pace(month, started_at=started, ends_at=ends, now=outside)


def test_a_period_with_no_length_has_no_pace_and_a_budget_of_nothing_cannot_exist() -> None:
    """Two divisions by zero. Only one of them needs a guard here.

    A period of no length makes every instant fully elapsed, and nothing upstream refuses it,
    so `pace` does. A ceiling of nothing would make every budget fully spent, and
    `brain.ops.budgets.BudgetRow` already refuses it in its own constructor: a second check
    here would be a guard no test could reach, which is the defect this repository keeps
    finding rather than a belt beside a brace.

    The second half is asserted as the upstream refusal rather than dropped, so the day
    somebody relaxes `BudgetRow` this test says where the hole now is.

    Delete this and the pace screen divides by a zero one of its two inputs can hold."""
    started = datetime(2026, 3, 1, tzinfo=UTC)

    with pytest.raises(SpendViewError, match="no elapsed fraction"):
        pace(
            a_budget(ceiling=1_000, period=BudgetPeriod.MONTH, spent=1),
            started_at=started,
            ends_at=started,
            now=started,
        )
    with pytest.raises(BudgetError, match="ceiling of"):
        a_budget(ceiling=0, period=BudgetPeriod.MONTH, spent=0)


# --- refusals and degradations (M21.3.6) -------------------------------------------------


def test_a_refusal_belongs_to_the_refuse_rung_and_to_no_other() -> None:
    """M21.3.6. A `REFUSE` row with no refusal has lost which budget bound, which is the one
    fact the row exists to carry. A refusal at a lower rung describes a request that ran and
    was refused, which did not happen.

    Both directions, because a guard written for one passes a test that only asks the other.

    Delete this and the friction screen counts causes from rows that do not have one."""
    bound = Refusal(level=BudgetLevel.DEPARTMENT, period=BudgetPeriod.MONTH)

    with pytest.raises(SpendViewError, match="refuse rung and nowhere else"):
        Setback(department=MAINTENANCE, at=NOW, rung=Rung.REFUSE, refusal=None)
    with pytest.raises(SpendViewError, match="refuse rung and nowhere else"):
        Setback(department=MAINTENANCE, at=NOW, rung=Rung.QUEUE, refusal=bound)

    assert Setback(department=MAINTENANCE, at=NOW, rung=Rung.REFUSE, refusal=bound).cause
    assert Setback(department=MAINTENANCE, at=NOW, rung=Rung.QUEUE, refusal=None).cause == "queue"


def test_a_setback_with_no_department_cannot_be_shown_at_a_reach() -> None:
    """The place is what the report filters on, so a row without one is a row that is either
    shown to everybody or to nobody, and which of those it is depends on the filter's
    implementation rather than on a decision.

    Whitespace as well as empty, because `" "` passes a bare falsiness check.

    Delete this and a row with no department decides its own audience."""
    for nowhere in ("", " "):
        with pytest.raises(SpendViewError, match="no department"):
            Setback(department=nowhere, at=NOW, rung=Rung.QUEUE, refusal=None)


def test_friction_counts_only_what_the_reader_may_see_and_leaves_no_residual() -> None:
    """A count of refusals in a department the reader has no grant over is a count of activity
    they do not have. No residual bucket, no "and others", and no total to subtract from,
    which is `brain.console.auditor`'s rule reached from the spend side.

    Three rows, one of them in finance, so a function counting everything and one counting
    nothing both fail.

    Delete this and the friction screen tells a department head how busy finance was."""
    bound = Refusal(level=BudgetLevel.DEPARTMENT, period=BudgetPeriod.MONTH)
    rows = [
        Setback(department=MAINTENANCE, at=NOW, rung=Rung.QUEUE, refusal=None),
        Setback(department=MAINTENANCE, at=NOW, rung=Rung.REFUSE, refusal=bound),
        Setback(department=FINANCE, at=NOW, rung=Rung.REFUSE, refusal=bound),
    ]

    mine = friction(rows, a_reader(MAINTENANCE), now=NOW)

    assert mine.by_rung == {Rung.QUEUE: 1, Rung.REFUSE: 1}
    assert sum(mine.by_cause.values()) == 2
    assert friction(rows, everybody(), now=NOW).by_rung == {Rung.QUEUE: 1, Rung.REFUSE: 2}


def test_a_reader_with_no_grant_sees_an_empty_friction_report_rather_than_a_refusal() -> None:
    """Same reason as the empty spend report: a refusal naming the capability would say the
    screen exists.

    Delete this and holding no grant is distinguishable from having nothing to see."""
    rows = [Setback(department=MAINTENANCE, at=NOW, rung=Rung.QUEUE, refusal=None)]

    empty = friction(rows, a_reader(), now=NOW)

    assert empty == Friction(by_rung={}, by_cause={})


def test_a_cause_names_the_budget_or_the_sacrifice_and_never_a_figure() -> None:
    """`spend.Refusal` carries no amount and no subject by construction, and the cause here is
    read off it rather than assembled. The degradation case is the rung's own name, which is a
    closed vocabulary of four.

    Asserted by looking for digits, because the failure this prevents is a cause string
    interpolating a headroom into an otherwise correct sentence.

    Delete this and the friction screen becomes the place the remaining budget leaks out."""
    bound = Refusal(level=BudgetLevel.DEPARTMENT, period=BudgetPeriod.MONTH)
    refused = Setback(department=MAINTENANCE, at=NOW, rung=Rung.REFUSE, refusal=bound)
    degraded = Setback(department=MAINTENANCE, at=NOW, rung=Rung.CHEAPER_TIER, refusal=None)

    assert refused.cause == bound.budget
    assert degraded.cause == "cheaper_tier"
    for one in (refused, degraded):
        assert not any(character.isdigit() for character in one.cause)


# --- the dearest lines (M21.3.4, agents only) --------------------------------------------


def test_the_dearest_lines_are_a_slice_of_what_the_report_already_showed() -> None:
    """A top list over rows the reader is already looking at discloses nothing new, which is
    the whole reason it takes a `Report` rather than the accounting rows.

    No rank number and no "of N" on the result, for the same reason the report carries no
    total over rows it did not show.

    Delete this and the expensive-agents panel is computed from the unfiltered ledger."""
    runs = [
        a_run(department=MAINTENANCE, cost=10, agent="a_cheap"),
        a_run(department=MAINTENANCE, cost=500, agent="a_dear"),
        a_run(department=FINANCE, cost=9_000, agent="a_someone_elses"),
    ]

    mine = spend_report(runs, a_reader(MAINTENANCE), Dimension.AGENT, now=NOW)

    assert [one.key for one in dearest(mine, 2)] == ["a_dear", "a_cheap"]
    assert [one.key for one in dearest(mine, 1)] == ["a_dear"]


def test_a_list_of_the_dearest_nothing_is_refused() -> None:
    """A caller computing the limit from a page size and getting zero wants to know, rather
    than getting an empty panel that reads as no spend.

    Delete this and a paging bug renders as a quiet month."""
    empty = spend_report([], everybody(), Dimension.AGENT, now=NOW)

    for none_at_all in (0, -1):
        with pytest.raises(SpendViewError, match="is not a list"):
            dearest(empty, none_at_all)


# ------------------------------------------- the cost review after launch (M37.5.3)
def _dear_runs(count: int) -> tuple[Observation, ...]:
    return tuple(Observation(estimated_minor=100, actual_minor=200) for _ in range(count))


def test_the_cost_review_shows_the_variance_and_the_corrected_factor_together() -> None:
    """**A variance with no correction beside it is a worry with no action.** Spending twice
    the projection is something a person can act on only next to what the estimator now says,
    and a corrected factor on its own is a number with no evidence beside it.

    Delete this and the screen can show one of them, and whichever it shows is the half that
    reads as either an alarm nobody can answer or a change nobody asked for."""
    review = cost_review(
        projected_minor=500,
        measured=SpendWindow(readings=(1000,), over_days=MEASUREMENT_WINDOW_DAYS),
        prior=NO_CORRECTION,
        observations=_dear_runs(60),
    )

    assert isinstance(review, CostReview)
    assert review.variance.ratio == 2.0
    assert review.correction.factor > NO_CORRECTION.factor
    assert review.long_enough is True


def test_a_review_inside_the_first_month_shows_a_variance_and_an_uncorrected_factor() -> None:
    """The honest version of that screen in the first fortnight rather than an empty one: a
    variance, the prior unchanged, and a sentence saying how much of a month was measured.

    `long_enough` is on the object rather than in a caption, which is the same argument
    `Report.machine_included` makes: a renderer cannot show the factor without the qualifier.

    Delete this and the obvious tightening is to refuse a short window, and the cost review is
    switched off for the month it is most worth reading."""
    review = cost_review(
        projected_minor=500,
        measured=SpendWindow(readings=(1000,), over_days=3),
        prior=NO_CORRECTION,
        observations=_dear_runs(60),
    )

    assert review.long_enough is False
    assert review.variance.ratio == 2.0
    assert review.correction.factor == NO_CORRECTION.factor
    assert str(MEASUREMENT_WINDOW_DAYS) in review.correction.reason


def test_the_review_says_it_is_short_on_the_object_and_not_only_in_the_variance() -> None:
    """The qualifier is repeated onto the review rather than left to be read off the variance,
    because the correction is the figure a renderer shows large and the two would otherwise sit
    on different objects.

    Compared against the variance's own answer rather than against a literal, so the two can
    never disagree.

    Delete this and `long_enough` can drift from the variance it came from."""
    for days in (1, MEASUREMENT_WINDOW_DAYS):
        review = cost_review(
            projected_minor=500,
            measured=SpendWindow(readings=(1000,), over_days=days),
            prior=NO_CORRECTION,
            observations=_dear_runs(60),
        )

        assert review.long_enough is review.variance.long_enough
