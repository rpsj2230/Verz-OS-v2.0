"""What a budget does when it is used up: who is told, and how long nothing runs.

The owner chose a warning followed by a hard stop until the next period, over a
recommendation to refuse only the expensive lanes. A hard stop is an outage the system causes
itself, so the tests here are weighted towards the two ways it could become one nobody
intended: a stop whose end instant is wrong or absent, and a stop opened without anybody who
could relieve it being told.

Every date below is in 2032 and 2033, far outside any plausible wall clock, because none of
this is about the present. `CLAUDE.md` records why a fixture with a date in it is a clock: one
that expires reports a defect on a schedule nobody chose. The calendar arithmetic needs real
months, so a leap year and the year after it are both walked.

The zone is `Asia/Singapore` where a zone is incidental and `America/Santiago` where it is
not: Santiago changes its clocks at local midnight, which is the one case where flooring an
aware instant and flooring a wall clock give different answers.

Task ids: none
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from brain.ops import budget_stop as budget_stop_module
from brain.ops.admission import OPERATOR_ACTION, RefusalKind
from brain.ops.budget_stop import (
    BUDGET_AUTHORITY,
    DOES_NOT_ROLL,
    WINDOWS,
    Addressing,
    BudgetStopError,
    Consequence,
    Notice,
    Stop,
    Window,
    boundary_gaps,
    consequence_of,
    in_force,
    next_period_start,
    stopped,
    warn,
    wider_than,
)
from brain.ops.budgets import (
    LEVEL_BREADTH,
    Allowance,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
)
from brain.ops.spend import BUDGET_PHRASE, Refusal

EAST = ZoneInfo("Asia/Singapore")
#: The same zone the instants below are written in, as a `ZoneInfo` rather than as
#: `datetime.UTC`, because a boundary is floored in an installation's configured zone and
#: `brain.locale.time_zone` returns one of these.
UTC_ZONE = ZoneInfo("UTC")
#: A zone whose clocks change at local midnight, which is where wall-clock flooring earns
#: itself. Chile moves at 24:00 local, so the day of the change has no 00:00.
MIDNIGHT_SHIFTER = ZoneInfo("America/Santiago")

#: Deliberately far outside any wall clock this will run against. See the module docstring.
NOW = datetime(2032, 3, 10, 12, 0, tzinfo=UTC)

MAINTENANCE = "maintenance"
FINANCE = "finance"
ADMIN = "u_dept_admin"
OWNER = "u_company_owner"


def a_row(
    *,
    level: BudgetLevel = BudgetLevel.DEPARTMENT,
    subject: str = MAINTENANCE,
    period: BudgetPeriod = BudgetPeriod.MONTH,
    ceiling: int = 10_000,
) -> BudgetRow:
    """One ceiling, through `BudgetRow`'s own validators."""
    return BudgetRow(
        level=level,
        subject=subject,
        period=period,
        ceiling_minor=ceiling,
        version=1,
        author="u_admin",
        effective_from=NOW - timedelta(days=400),
        reason="a figure written for this test",
    )


def spent_out(**kwargs: object) -> Allowance:
    """A ceiling with all of it spent, which is what `tightest` hands `consequence_of`."""
    row = a_row(**kwargs)  # type: ignore[arg-type]
    return Allowance(row=row, spent_minor=row.ceiling_minor)


# --- the period boundary is data, and it comes from the row's own period ---------------------


def test_a_monthly_stop_ends_at_local_midnight_on_the_first_of_the_next_month() -> None:
    """The boundary somebody means by "until the next period", walked over every month of a
    leap year and the year after it, so February and the thirty-one day months are both in the
    answer rather than in a comment.

    The zone is east of UTC, so a boundary computed in UTC would land eight hours late and this
    fails with a visible offset rather than with an off-by-one nobody can read.

    Delete this and the month stride can become thirty days, which is right for four months of
    the year and puts the boundary in the middle of the previous month for the rest."""
    for year in (2032, 2033):
        for month in range(1, 13):
            inside = datetime(year, month, 17, 9, 30, tzinfo=EAST)
            expected_year = year + 1 if month == 12 else year
            expected_month = 1 if month == 12 else month + 1

            found = next_period_start(BudgetPeriod.MONTH, inside, zone=EAST)

            assert found == datetime(expected_year, expected_month, 1, tzinfo=EAST), (year, month)


def test_a_daily_stop_ends_at_the_next_local_midnight_and_never_before_it_started() -> None:
    """The other rolling period, and the property that matters for both: the answer is strictly
    after the instant it was asked about, and it is the first boundary after it rather than the
    one it is standing on.

    An instant exactly on a boundary is the discriminating case. Midnight belongs to the day
    that is starting, so the stop opened at midnight ends twenty-four hours later and not
    immediately, which a flooring that returned the current window's start would get wrong.

    Delete this and `next_period_start` can return the start of the window it was given, and
    every stop ends at the instant it opens."""
    midday = datetime(2032, 6, 14, 12, 0, tzinfo=EAST)
    midnight = datetime(2032, 6, 14, 0, 0, tzinfo=EAST)

    assert next_period_start(BudgetPeriod.DAY, midday, zone=EAST) == datetime(
        2032, 6, 15, tzinfo=EAST
    )
    assert next_period_start(BudgetPeriod.DAY, midnight, zone=EAST) == datetime(
        2032, 6, 15, tzinfo=EAST
    )

    for hour in range(24):
        at = datetime(2032, 6, 14, hour, 31, tzinfo=EAST)
        assert next_period_start(BudgetPeriod.DAY, at, zone=EAST) > at, hour


def test_the_boundary_is_read_in_the_installs_zone_and_not_in_the_requests() -> None:
    """The zone is a company setting and the instant is whatever the request carried. A monthly
    budget on a company east of UTC rolls at their midnight, so a request made at 20:00 UTC on
    the last day of the month is already in the next month for them.

    The same instant is passed twice with two zones and the answers differ, which is what makes
    this a test of the zone rather than of the instant.

    Delete this and the boundary is computed in whatever zone the caller's clock happened to be
    in, and a month ends at eight in the morning for half the company."""
    at = datetime(2032, 3, 31, 20, 0, tzinfo=UTC)

    assert next_period_start(BudgetPeriod.MONTH, at, zone=EAST) == datetime(2032, 5, 1, tzinfo=EAST)
    assert next_period_start(BudgetPeriod.MONTH, at, zone=UTC_ZONE) == datetime(
        2032, 4, 1, tzinfo=UTC
    )


def test_a_period_containing_a_clock_change_still_ends_at_local_midnight() -> None:
    """Wall-clock arithmetic rather than a count of seconds, which is the whole reason
    `_start_of` strips the zone before flooring. Santiago moves its clocks at local midnight, so
    a stop opened before the change and ending after it must still end at the local midnight
    somebody would read off a wall, not twenty-three or twenty-five hours later.

    Asserted on the local date and the local hour rather than on the UTC offset, because the
    offset is exactly what changes and pinning it would pin the bug.

    Delete this and the boundary can be computed by adding a `timedelta` to an aware instant,
    and twice a year a daily budget ends at one in the morning."""
    before = datetime(2032, 9, 4, 18, 0, tzinfo=MIDNIGHT_SHIFTER)

    found = next_period_start(BudgetPeriod.DAY, before, zone=MIDNIGHT_SHIFTER)
    local = found.astimezone(MIDNIGHT_SHIFTER)

    assert (local.year, local.month, local.day) == (2032, 9, 5)
    assert local.hour == 0
    assert found > before


def test_a_per_run_ceiling_has_no_next_period_and_is_refused_rather_than_guessed() -> None:
    """**The sharpest rule in the module.** Waiting does not refill a per-run ceiling, so a stop
    until the next period would never end and a cost control would become a permanent outage.
    Both doors are shut: the boundary refuses to compute one and the value refuses to hold one.

    The rolling periods are asserted in the same breath, so this is not passing because
    `next_period_start` refuses everything.

    Delete this and a per-run agent ceiling stops its department for ever, with nothing in the
    system able to end it."""
    with pytest.raises(BudgetStopError, match="has no next period"):
        next_period_start(BudgetPeriod.RUN, NOW, zone=EAST)

    with pytest.raises(BudgetStopError, match="cannot be stopped until the next period"):
        Stop(
            level=BudgetLevel.AGENT,
            subject="a_reporter",
            period=BudgetPeriod.RUN,
            since=NOW,
            until=NOW + timedelta(days=1),
        )

    for period in (BudgetPeriod.DAY, BudgetPeriod.MONTH):
        assert next_period_start(period, NOW, zone=EAST) > NOW


def test_a_naive_instant_has_no_zone_to_be_floored_in_and_is_refused() -> None:
    """A naive instant compares wrongly against every aware one in the system, and the failure
    it causes here is a boundary computed as though the request had been made in UTC.

    The aware sibling is asserted, so this is not passing because the function refuses
    everything.

    Delete this and a caller passing `datetime.now()` without a zone gets a boundary that is
    right on a server in London and wrong everywhere else."""
    with pytest.raises(BudgetStopError, match="no zone to be floored in"):
        next_period_start(BudgetPeriod.DAY, datetime(2032, 3, 10, 12, 0), zone=EAST)

    assert next_period_start(BudgetPeriod.DAY, NOW, zone=EAST) > NOW


def test_every_budget_period_either_rolls_or_is_declared_not_to() -> None:
    """The gap this exists to make loud: a rolling period added to `BudgetPeriod` and forgotten
    in `WINDOWS` is indistinguishable at runtime from a per-run ceiling, so budgets at it would
    never stop anybody and nothing would say so.

    The two tables are asserted to be disjoint and to cover the enum, and the diagnostic is
    asserted quiet on the module as it stands.

    Delete this and a fourth period ships with no boundary, and the ceiling it belongs to
    enforces itself one request at a time for ever."""
    assert set(WINDOWS) | DOES_NOT_ROLL == set(BudgetPeriod)
    assert set(WINDOWS) & DOES_NOT_ROLL == set()
    assert boundary_gaps() == ()


def test_boundary_gaps_reports_a_period_that_neither_rolls_nor_says_it_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The diagnostic, watched. The real tables cover the enum, so the branch cannot fire on the
    module as it stands and would be a check nobody could exercise. Emptying one table is how it
    becomes watchable, which is the technique `test_screens` uses on its own registry checks.

    Both findings are provoked, because they are opposite mistakes: a period nothing decided
    about, and one declared both ways.

    Delete this and the check goes back to being a branch nothing can reach."""
    monkeypatch.setattr(budget_stop_module, "DOES_NOT_ROLL", frozenset())

    gaps = budget_stop_module.boundary_gaps()

    assert [one for one in gaps if one.startswith("run has no window")], gaps

    monkeypatch.setattr(budget_stop_module, "DOES_NOT_ROLL", frozenset(BudgetPeriod))

    both = budget_stop_module.boundary_gaps()

    assert [one for one in both if "both rolls and does not" in one], both


def test_a_window_that_could_not_reach_the_next_one_cannot_be_declared() -> None:
    """A stride that lands inside the window it started in makes the next period begin at the
    same instant as this one, so every stop ends before it begins and the ceiling stops nothing.
    A start day past the twenty-eighth does not exist in February, so the boundary would move or
    fail depending on the month.

    The real rows are constructed in the same pass, so this is not passing because `Window`
    refuses everything.

    Delete this and a month's stride can be set to zero during a refactor, and the stop that
    reads as a month is over the moment it is written."""
    with pytest.raises(BudgetStopError, match="lands in the window it started in"):
        Window(starts_on_day=None, stride=timedelta(0))

    with pytest.raises(BudgetStopError, match="does not exist in every month"):
        Window(starts_on_day=31, stride=timedelta(days=32))

    assert WINDOWS[BudgetPeriod.MONTH].starts_on_day == 1
    assert WINDOWS[BudgetPeriod.DAY].starts_on_day is None


# --- the stop refuses until then, and ends by the clock ---------------------------------------


def test_a_stop_refuses_from_the_instant_it_opened_until_the_period_rolls_and_not_after() -> None:
    """Half open at the top, so the first request of the new period is served rather than being
    the one that discovers the boundary was inclusive. Refusing at the instant of the boundary
    would push every stop one request into the period it was supposed to end at.

    Four instants: before it opened, at the instant it opened, inside it, and at the boundary.
    The one before is the discriminating case, because a stop that returned True for everything
    would pass the other three.

    Delete this and the comparison can become `<=` at both ends, and a monthly stop refuses the
    first question of every new month."""
    until = next_period_start(BudgetPeriod.MONTH, NOW, zone=EAST)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        since=NOW,
        until=until,
    )

    assert stop.in_force_at(NOW - timedelta(seconds=1)) is False
    assert stop.in_force_at(NOW) is True
    assert stop.in_force_at(NOW + timedelta(days=5)) is True
    assert stop.in_force_at(until) is False


def test_a_stop_that_ends_when_or_before_it_began_cannot_be_constructed() -> None:
    """A stop with no duration refuses nothing and reads on a screen exactly like one that
    refuses everything, which is the worst pair of properties a row can have: an operator
    looking at the budget screen sees a department stopped and the department sees no stop.

    The valid stop is built in the same test, so this is not passing because the constructor
    refuses everything.

    Delete this and a boundary computed one period too early ships as a stop that does
    nothing."""
    for until in (NOW, NOW - timedelta(hours=1)):
        with pytest.raises(BudgetStopError, match="refuses nothing"):
            Stop(
                level=BudgetLevel.DEPARTMENT,
                subject=MAINTENANCE,
                period=BudgetPeriod.DAY,
                since=NOW,
                until=until,
            )

    assert Stop(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.DAY,
        since=NOW,
        until=NOW + timedelta(seconds=1),
    ).in_force_at(NOW)


def test_a_stop_naming_no_subject_and_a_stop_on_a_naive_clock_are_both_refused() -> None:
    """A stop with no subject refuses either everybody or nobody and there is no way to tell
    which was meant, which is `budgets.BudgetRow`'s argument about an unkeyed ceiling. A naive
    instant compares wrongly against the aware instant every request carries, so the stop would
    be in force or not depending on the server's zone.

    Delete this and a stop assembled from a partly-filled form is a stop that refuses the
    company."""
    with pytest.raises(BudgetStopError, match="naming no subject"):
        Stop(
            level=BudgetLevel.DEPARTMENT,
            subject="   ",
            period=BudgetPeriod.DAY,
            since=NOW,
            until=NOW + timedelta(days=1),
        )

    with pytest.raises(BudgetStopError, match="naive instant"):
        Stop(
            level=BudgetLevel.DEPARTMENT,
            subject=MAINTENANCE,
            period=BudgetPeriod.DAY,
            since=datetime(2032, 3, 10, 12, 0),
            until=NOW + timedelta(days=1),
        )


def test_a_stop_has_no_way_to_be_lifted_early_and_no_field_an_extension_could_live_on() -> None:
    """The absence that keeps a budget stop honest in the opposite direction from a halt's. A
    budget stop is an arithmetic consequence and must end when the ceiling refills; a halt is a
    person's decision and must not end on its own. Unifying them would break whichever was made
    to follow the other.

    Asserted on the fields and on the methods, because the two ways this goes wrong are a
    `lifted_at` column added for an administrator and a `resume` added beside `halt`'s.

    Delete this and a stop grows an override, and the way to raise a budget becomes an act with
    no author, no version and no history."""
    names = {one.name for one in dataclass_fields(Stop)}

    assert names == {"level", "subject", "period", "since", "until"}
    for forbidden in ("lifted_at", "lifted_by", "extended_to", "override", "enabled"):
        assert forbidden not in names, forbidden
    for forbidden in ("resume", "lift", "clear", "extend"):
        assert not hasattr(Stop, forbidden), forbidden


def test_the_operator_record_says_quota_and_names_when_it_ends() -> None:
    """**Half of "the two must not look alike to an operator".** A budget stop and a permission
    refusal have different remedies, and `admission.OPERATOR_ACTION` is where that difference is
    already written down: QUOTA says raise this allowance or leave it deliberately, PERMISSION
    says the model is working and to do nothing.

    The end instant is what separates a stop from one refused request at the same kind: a reader
    can tell a single refusal from a department that will be refused for the rest of the month.

    Delete this and a budget stop is logged as a permission refusal, and the operator reading it
    goes to look at grants."""
    until = next_period_start(BudgetPeriod.MONTH, NOW, zone=EAST)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        since=NOW,
        until=until,
    )

    record = stop.log_record()

    assert record["refusal_kind"] == str(RefusalKind.QUOTA)
    assert record["operator_action"] == OPERATOR_ACTION[RefusalKind.QUOTA]
    assert record["operator_action"] != OPERATOR_ACTION[RefusalKind.PERMISSION]
    assert until.isoformat() in record["detail"]
    assert MAINTENANCE not in record["detail"]
    assert MAINTENANCE not in record["subject"]


def test_a_stop_refuses_the_request_its_own_ceiling_is_judged_against_and_no_other() -> None:
    """Matched on the ceiling's key rather than on a level and a subject compared by hand, so a
    stop on a department's monthly budget cannot refuse a request judged against that
    department's daily one, and a stop on one department cannot refuse another's.

    The positive case is first and is the discriminating one: a matcher that returned None for
    everything would pass all three negatives.

    Delete this and `stopped` can match on the subject alone, and stopping a department for the
    month stops every daily budget in it as well."""
    monthly = spent_out(period=BudgetPeriod.MONTH)
    daily = spent_out(period=BudgetPeriod.DAY)
    elsewhere = spent_out(subject=FINANCE)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        since=NOW,
        until=NOW + timedelta(days=20),
    )

    assert stopped([monthly], [stop], at=NOW) is stop
    assert stopped([daily], [stop], at=NOW) is None
    assert stopped([elsewhere], [stop], at=NOW) is None
    assert stopped([], [stop], at=NOW) is None


def test_a_stop_whose_period_has_rolled_refuses_nothing_and_nobody_has_to_clear_it() -> None:
    """The property that stops this becoming the expiring halt the module argues against from
    the other side. Nothing clears a stop and nothing has to: it is absent from the answer the
    instant its window closes, so a row left in a table cannot outlive the ceiling it came from.

    The in-force sibling is asserted, so this is not passing because `stopped` returns None for
    everything.

    Delete this and a stop needs somebody to delete it, and the first month nobody does is a
    department refused for two."""
    ceiling = spent_out(period=BudgetPeriod.MONTH)
    until = NOW + timedelta(days=20)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        since=NOW,
        until=until,
    )

    assert stopped([ceiling], [stop], at=NOW + timedelta(days=19)) is stop
    assert stopped([ceiling], [stop], at=until) is None
    assert in_force([stop], at=until) == ()
    assert in_force([stop], at=NOW) == (stop,)


def test_the_widest_of_several_stops_is_the_one_a_request_is_refused_by() -> None:
    """Relieving a person's allowance while their department is stopped changes nothing, and
    somebody sent to their department head who is then refused again by the company's budget has
    been sent to the wrong place twice. That is `budgets.THE_WIDEST_OF_TWO_EXHAUSTED_BUDGETS_IS_
    THE_ONE_NAMED` read from the other end, and the breadth table is the same one.

    The stops are passed narrowest first so a function returning the first match would fail, and
    the ordering is pinned against `LEVEL_BREADTH` rather than against a list written here.

    Delete this and which budget a stopped person is told about depends on the order a store
    returned the rows in."""
    company = Stop(
        level=BudgetLevel.COMPANY,
        subject="c_this",
        period=BudgetPeriod.MONTH,
        since=NOW,
        until=NOW + timedelta(days=20),
    )
    department = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        since=NOW,
        until=NOW + timedelta(days=20),
    )
    allowances = [
        spent_out(level=BudgetLevel.COMPANY, subject="c_this"),
        spent_out(level=BudgetLevel.DEPARTMENT, subject=MAINTENANCE),
    ]

    assert stopped(allowances, [department, company], at=NOW) is company
    assert in_force([department, company], at=NOW) == (company, department)
    assert LEVEL_BREADTH[BudgetLevel.COMPANY] < LEVEL_BREADTH[BudgetLevel.DEPARTMENT]


# --- somebody is told first, and the order is a shape ------------------------------------------


def test_somebody_who_holds_the_authority_twice_is_warned_once_and_the_order_is_kept() -> None:
    """**A mutation found that nothing watched the deduplication.**

    A directory resolves to a list, and one person can reach the same budget by two routes:
    a department admin who is also a company admin, or two grants for one principal. Warning
    them twice is not a disclosure and it is the difference between a notice somebody reads
    and a notice somebody filters.

    `dict.fromkeys` rather than a set, and that half is the reason this test asserts the order
    as well as the membership. A set makes the recipient list depend on hash ordering, so the
    same estate produces a different notice on two runs and neither is wrong, which is the
    kind of difference that makes a person doubt the whole message.

    Delete this and the deduplication can be dropped for a plain tuple, which passes every
    test that only checks who was reached."""
    notice = warn(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        at=NOW,
        admins=[ADMIN, OWNER, ADMIN],
        above=[],
    )

    assert notice.to == (ADMIN, OWNER)
    assert notice.addressing is Addressing.OWN_ADMIN


def test_the_warning_goes_to_whoever_holds_the_authority_over_that_budget() -> None:
    """The ordinary case, and the one every other case here is a departure from. The recipients
    arrive already resolved, so what is tested is what this module does with them rather than a
    directory nobody has.

    The capability is pinned to a value written here rather than compared against itself, which
    is the trap `CLAUDE.md` records three authors falling into in one afternoon.

    Delete this and `warn` can address the notice to the person who was refused, which passes
    every test that only checks a notice was produced."""
    notice = warn(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        at=NOW,
        admins=[ADMIN],
        above=[OWNER],
    )

    assert notice.to == (ADMIN,)
    assert notice.addressing is Addressing.OWN_ADMIN
    assert notice.unaddressed is False
    assert BUDGET_AUTHORITY.value == "admin:budget"
    assert BUDGET_AUTHORITY.verb == "admin"


def test_a_department_with_no_admin_escalates_one_level_rather_than_going_unwarned() -> None:
    """**Refusing to warn is not the same as not warning.** A department with no admin is the
    ordinary state of a young install. Raising would mean the ceiling does not enforce itself;
    returning nothing would mean it does and nobody hears. The warning goes one level wider and
    the notice says that is what happened.

    One hop and not a chain: the escalated notice names the people above and nothing walks
    further, so a console reading `ESCALATED` knows the level it was meant for is unstaffed.

    Delete this and a budget in an unadministered department stops the department silently, and
    the first anybody hears is a person saying their questions stopped working."""
    notice = warn(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        at=NOW,
        admins=[],
        above=[OWNER],
    )

    assert notice.to == (OWNER,)
    assert notice.addressing is Addressing.ESCALATED
    assert notice.unaddressed is False


def test_a_warning_nobody_holds_the_authority_for_is_recorded_rather_than_lost() -> None:
    """The third state, and it is a finding rather than a silence: nobody holds the authority
    over this budget or over the one above it. The notice exists, it says it reached nobody, and
    a console can count them.

    The refusal beside it is the shape rule: an unaddressed notice with recipients on it, or an
    addressed one with none, would read as a warning having been delivered.

    Delete this and an empty directory produces a notice indistinguishable from a delivered
    one."""
    notice = warn(
        level=BudgetLevel.COMPANY,
        subject="c_this",
        period=BudgetPeriod.MONTH,
        at=NOW,
        admins=[],
        above=[],
    )

    assert notice.to == ()
    assert notice.addressing is Addressing.UNADDRESSED
    assert notice.unaddressed is True

    with pytest.raises(BudgetStopError, match="unaddressed warning reached nobody"):
        Notice(
            level=BudgetLevel.COMPANY,
            subject="c_this",
            period=BudgetPeriod.MONTH,
            at=NOW,
            to=(OWNER,),
            addressing=Addressing.UNADDRESSED,
        )


def test_the_level_a_warning_escalates_to_is_derived_from_the_breadth_table() -> None:
    """Derived rather than written out again, so the escalation and the tie-break between two
    exhausted budgets cannot disagree about which of two levels is wider. The company's is the
    widest and escalates nowhere, which is why an unaddressed company warning is the loudest
    thing this module produces.

    Every level is walked, so a fifth added to `BudgetLevel` has an answer here rather than a
    `KeyError` at the moment somebody is being refused.

    Delete this and the escalation grows its own ordering, and the day somebody reorders
    `BudgetLevel` the two disagree in the direction where a warning goes nowhere."""
    assert wider_than(BudgetLevel.COMPANY) is None
    assert wider_than(BudgetLevel.DEPARTMENT) is BudgetLevel.COMPANY
    assert wider_than(BudgetLevel.USER) is BudgetLevel.DEPARTMENT
    assert wider_than(BudgetLevel.AGENT) is BudgetLevel.USER

    for level in BudgetLevel:
        above = wider_than(level)
        if above is not None:
            assert LEVEL_BREADTH[above] < LEVEL_BREADTH[level], level


def test_a_notice_names_the_budget_in_spends_words_and_carries_no_figure() -> None:
    """The recipient is being told which ceiling to raise, so the budget is named; nothing else
    about it is. A remaining figure on a warning is the number a person forwards, and two
    warnings a fortnight apart subtract into everybody else's spending, which is
    `spend.A_REFUSAL_CARRIES_NO_FIGURE` about the same disclosure at the other end.

    The wording comes from `spend.BUDGET_PHRASE` rather than from a second table here, asserted
    by building the phrase from `Refusal` and comparing.

    Delete this and the notice grows its own phrasing, and the two disagree about what a
    department's monthly budget is called."""
    notice = warn(
        level=BudgetLevel.DEPARTMENT,
        subject=MAINTENANCE,
        period=BudgetPeriod.MONTH,
        at=NOW,
        admins=[ADMIN],
        above=[],
    )

    assert notice.budget == Refusal(level=BudgetLevel.DEPARTMENT, period=BudgetPeriod.MONTH).budget
    assert BUDGET_PHRASE[BudgetLevel.DEPARTMENT].format(period="monthly") == notice.budget

    names = {one.name for one in dataclass_fields(Notice)}

    for forbidden in ("headroom_minor", "spent_minor", "ceiling_minor", "remaining", "overspend"):
        assert forbidden not in names, forbidden


def test_a_warning_and_a_stop_come_back_together_and_the_warning_comes_first() -> None:
    """**Both, in the order the owner asked for.** The order is a shape rather than a comment:
    `Consequence` carries both, neither is optional, and it refuses a warning raised after the
    stop it is supposed to precede.

    The mismatch check is the other half. A warning about one department paired with a stop on
    another would tell the wrong person and refuse the wrong people, and both halves would look
    correct in isolation.

    Delete this and the order is kept by whoever wired the call site up, and the second call
    site opens a stop with no warning."""
    outcome = consequence_of(
        spent_out(),
        at=NOW,
        zone=EAST,
        admins=[ADMIN],
        above=[OWNER],
    )

    assert outcome is not None
    assert outcome.notice.to == (ADMIN,)
    assert outcome.notice.at <= outcome.stop.since
    assert outcome.stop.until == next_period_start(BudgetPeriod.MONTH, NOW, zone=EAST)

    with pytest.raises(BudgetStopError, match="in the other order"):
        Consequence(
            notice=warn(
                level=BudgetLevel.DEPARTMENT,
                subject=MAINTENANCE,
                period=BudgetPeriod.MONTH,
                at=NOW + timedelta(hours=1),
                admins=[ADMIN],
                above=[],
            ),
            stop=outcome.stop,
        )

    with pytest.raises(BudgetStopError, match="not the one refusing"):
        Consequence(
            notice=warn(
                level=BudgetLevel.DEPARTMENT,
                subject=FINANCE,
                period=BudgetPeriod.MONTH,
                at=NOW,
                admins=[ADMIN],
                above=[],
            ),
            stop=outcome.stop,
        )


def test_a_warning_that_reached_nobody_still_stops_the_budget() -> None:
    """A ceiling that stopped enforcing itself when the directory was incomplete would be a
    budget any misconfiguration switches off, and the misconfiguration that switches it off is
    an empty admin list, which is what a new department looks like.

    The notice records that nobody was told, so the outage is visible rather than being
    inferred from the absence of a message.

    Delete this and the way to spend past a budget is to have no department admin."""
    outcome = consequence_of(spent_out(), at=NOW, zone=EAST, admins=[], above=[])

    assert outcome is not None
    assert outcome.notice.unaddressed is True
    assert outcome.stop.in_force_at(NOW) is True


def test_a_per_run_ceiling_warns_nobody_and_stops_nothing() -> None:
    """The consequence of the boundary rule, at the entry point. A per-run ceiling refuses the
    request that reached it and exhausts nothing, so there is nobody to warn and nothing to
    stop, and `consequence_of` says so by returning nothing rather than by raising.

    The rolling sibling is asserted in the same test, so this is not passing because
    `consequence_of` returns None for everything.

    Delete this and an agent's per-run ceiling opens a stop with no end, which is the outage
    this whole module is written to avoid."""
    per_run = Allowance(
        row=a_row(level=BudgetLevel.AGENT, subject="a_reporter", period=BudgetPeriod.RUN),
        spent_minor=10_000,
    )

    assert consequence_of(per_run, at=NOW, zone=EAST, admins=[ADMIN], above=[]) is None
    assert consequence_of(spent_out(), at=NOW, zone=EAST, admins=[ADMIN], above=[]) is not None
