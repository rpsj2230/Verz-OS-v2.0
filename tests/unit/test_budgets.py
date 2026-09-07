"""Budgets, held to the two things that make a shared budget survive contact with people.

The first is that a ceiling has a history: what it is now is uninteresting compared with what
it was on the day of the overspend, and a row that can be edited in place cannot answer that.
The second is that a department's share is its own. Implicit overflow is the feature everybody
asks for in month one, and it makes the shared budget invisible again.

Almost every constant here is asserted against something outside itself: another module's
figure, a second constant it must relate to, or the property that makes the number right. A
test comparing a constant with the constant it imported is green for every value that constant
could hold, which is the defect this repository keeps finding.

Task ids: M21.1.1, M21.1.2, M21.1.3, M21.1.4, M21.1.5
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.budgets import (
    ALLOWANCE_GENEROSITY,
    DAILY_BURST,
    DAYS_IN_BUDGET_MONTH,
    LEVEL_BREADTH,
    USER_FAIR_SHARE,
    Allowance,
    BudgetError,
    BudgetHistory,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
    DepartmentShare,
    Transfer,
    admits,
    agent_ceilings,
    allocate,
    apply_transfers,
    company_budget,
    level_gaps,
    narrowed_by_agent,
    tightest,
    user_allowances,
)
from brain.ops.limits import PRINCIPAL_FAIR_SHARE

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=1)


def company(ceiling: int = 1_000_000, fractions: tuple[float, ...] = (0.75, 0.9)) -> BudgetRow:
    return company_budget(
        company_id="verz",
        ceiling_minor=ceiling,
        author="rupash",
        effective_from=NOW,
        alert_fractions=fractions,
    )


def department(subject: str = "web", ceiling: int = 400_000) -> BudgetRow:
    return BudgetRow(
        level=BudgetLevel.DEPARTMENT,
        subject=subject,
        period=BudgetPeriod.MONTH,
        ceiling_minor=ceiling,
        version=1,
        author="rupash",
        effective_from=NOW,
    )


# ------------------------------------------------------------------ versioned audited rows
def test_a_budget_row_is_superseded_at_the_next_version_and_never_edited_in_place() -> None:
    """**The shape M21.1.5 asks for.** A ceiling that is overwritten cannot answer the only
    question anybody asks after an overspend, which is what the ceiling was at the time.

    Three halves, because the obvious ways round the rule are all cheap. The row is frozen, so
    assignment fails. `superseded_by` bumps the version, so two versions cannot claim to be
    the same one. And it refuses an effective time that is not strictly later, so a history
    cannot contain two rows nobody can order.

    Delete this and a ceiling becomes an integer somebody edits, the audit trail moves to
    whoever remembers to write one, and the version column is decoration."""
    row = department()

    with pytest.raises(dataclasses.FrozenInstanceError):
        row.ceiling_minor = 999  # type: ignore[misc]

    later = row.superseded_by(ceiling_minor=500_000, author="priya", effective_from=LATER)
    assert later.version == row.version + 1
    assert later.author == "priya"
    assert row.ceiling_minor == 400_000, "the original row was mutated"

    with pytest.raises(BudgetError, match="strictly after"):
        row.superseded_by(ceiling_minor=1, author="priya", effective_from=NOW)


def test_a_history_before_its_first_row_has_no_row_in_force_rather_than_the_first_one() -> None:
    """None is not an unlimited budget and it is not the earliest row either.

    Returning the earliest row for an instant before it took effect back-dates a ceiling
    nobody had agreed to yet, which is how last quarter's spend gets judged against this
    quarter's number and comes out fine.

    The positive half is asserted beside it: at and after each row's instant, the right row is
    in force, so a function that simply returned None would not pass.

    Delete this and `in_force_at` grows a sensible-looking fallback, and every historic report
    silently uses today's ceiling."""
    first = department(ceiling=400_000)
    second = first.superseded_by(ceiling_minor=500_000, author="priya", effective_from=LATER)
    history = BudgetHistory(rows=(first, second))

    assert history.in_force_at(NOW - timedelta(seconds=1)) is None
    assert history.in_force_at(NOW) is first
    assert history.in_force_at(LATER - timedelta(seconds=1)) is first
    assert history.in_force_at(LATER) is second


def test_a_history_refuses_rows_it_cannot_order() -> None:
    """A history is only evidence if it can be read in one order.

    Three ways it stops being orderable: a repeated version, an effective time that does not
    move forwards, and two subjects in one history. All three read as tidy configuration and
    all three make "the row in force" a question about list order.

    Delete this and a loader that sorts by the wrong column produces a history that answers
    differently depending on how it was read out of the store."""
    first = department()
    same_version = dataclasses.replace(first, effective_from=LATER)
    assert same_version.version == first.version

    with pytest.raises(BudgetError, match="versions only go forwards"):
        BudgetHistory(rows=(first, same_version))

    backwards = dataclasses.replace(first, version=2, effective_from=NOW - timedelta(days=1))
    with pytest.raises(BudgetError, match="cannot be ordered"):
        BudgetHistory(rows=(first, backwards))

    other = department(subject="finance").superseded_by(
        ceiling_minor=10, author="rupash", effective_from=LATER
    )
    with pytest.raises(BudgetError, match="a history holds one ceiling"):
        BudgetHistory(rows=(first, other))

    with pytest.raises(BudgetError, match="not a budget"):
        BudgetHistory(rows=())


def test_a_budget_row_needs_an_author_a_subject_and_an_aware_instant() -> None:
    """An audited row is three fields, and each one goes missing in a different plausible way.

    An unattributed row is not an audited row. An unkeyed row counts everybody. A naive
    instant compares wrongly against an aware one, which is `memory.tiers.Occurrence`'s rule
    and the same failure: a comparison that raises at the boundary of a month.

    Delete this and a seeding script writes rows with an empty author because that is what the
    dataclass default would have been."""
    for broken, expected in (
        ({"author": ""}, "no author"),
        ({"subject": ""}, "needs a subject"),
        ({"effective_from": datetime(2026, 9, 1, 9, 0)}, "naive instant"),
    ):
        with pytest.raises(BudgetError, match=expected):
            dataclasses.replace(department(), **broken)


def test_a_budget_of_zero_is_a_suspension_rather_than_a_funded_budget() -> None:
    """Zero is how somebody switches a principal off by editing a number, and in the console
    it reads as a funded budget. The same argument `limits.Limit` makes about a limit of zero.

    The positive sibling matters here: a ceiling of one unit is accepted, so this is a floor
    rather than a function that refuses everything small.

    Delete this and suspending a department becomes a budget edit with no announcement, no
    author on the suspension itself and nothing in the console that reads as switched off."""
    with pytest.raises(BudgetError, match="suspension wearing a budget's clothes"):
        department(ceiling=0)
    with pytest.raises(BudgetError, match="minimum is 1"):
        department(ceiling=-5)

    assert department(ceiling=1).ceiling_minor == 1


# --------------------------------------------------------------- company ceiling and alerts
def test_an_alert_fires_strictly_before_the_refusal_and_never_at_it() -> None:
    """**M21.1.1's two halves are a hard ceiling and thresholds that warn before it.**

    A fraction at or above 1.0 fires at the instant of the refusal, which tells nobody
    anything they were not about to be told, while looking in the console exactly like an
    early warning that works. So it is refused at construction.

    The behaviour is asserted the other way round as well: at three quarters of the ceiling
    the alert has fired and the budget still admits, which is what "before" means and what a
    threshold equal to the ceiling could not do.

    Delete this and the alert fractions become presentation, somebody sets one to 1.0 because
    it seems tidier, and the first warning anybody gets is the refusal."""
    with pytest.raises(BudgetError, match="outside"):
        company(fractions=(0.75, 1.0))
    with pytest.raises(BudgetError, match="strictly increasing"):
        company(fractions=(0.9, 0.75))

    row = company(ceiling=1_000, fractions=(0.75, 0.9))
    assert row.alerts_crossed(740) == ()
    assert row.alerts_crossed(750) == (0.75,)
    assert row.alerts_crossed(900) == (0.75, 0.9)
    assert admits((Allowance(row=row, spent_minor=900),), 50), (
        "an alert fired and the ceiling refused at the same moment"
    )


# ------------------------------------------------------- departments, shares and transfers
def test_department_shares_cannot_total_more_than_the_company_ceiling() -> None:
    """Above one, the departments together may spend more than the company ceiling. That is
    implicit overflow written into the allocation rather than at the point of spending, and it
    is harder to see there, because every individual row looks reasonable and the total is
    nowhere on the page.

    The positive case is asserted beside it: shares that total under one allocate, and each
    department gets the floor of its share, so the parts never exceed the whole.

    Delete this and an eight-department allocation drifts to 1.15 one department at a time,
    and nothing reports it until the month the company budget binds."""
    with pytest.raises(BudgetError, match="implicit overflow"):
        allocate(
            company(),
            (DepartmentShare("web", 0.6), DepartmentShare("finance", 0.6)),
            author="rupash",
            effective_from=NOW,
        )

    rows = allocate(
        company(ceiling=1_000_000),
        (DepartmentShare("web", 0.5), DepartmentShare("finance", 0.3)),
        author="rupash",
        effective_from=NOW,
    )
    assert [row.ceiling_minor for row in rows] == [500_000, 300_000]
    assert sum(row.ceiling_minor for row in rows) < 1_000_000, "the parts exceeded the whole"
    assert all(row.version == 1 and row.author == "rupash" for row in rows)


def test_a_department_cannot_borrow_from_another_departments_headroom() -> None:
    """**The property M21.1.2's "explicit transfer only" means.**

    Web is exhausted; finance and the company have plenty. The request is refused, and adding
    finance's untouched allowance to the very same sequence changes nothing. That is what
    makes the absence of implicit overflow testable rather than a claim in a docstring: there
    is no arrangement of allowances in which one department's spare budget relieves another's.

    The positive sibling is the third assertion: with room of its own, web is admitted, so
    this is not a conjunction that refuses everything.

    Delete this and `admits` becomes an `any` during a refactor, which reads as more generous
    and means the first department to spend spends everybody's."""
    web = Allowance(row=department("web", 100), spent_minor=100)
    finance = Allowance(row=department("finance", 1_000_000), spent_minor=0)
    company_room = Allowance(row=company(1_000_000), spent_minor=0)

    assert not admits((company_room, web), 50)
    assert not admits((company_room, web, finance), 50), (
        "another department's headroom relieved this one"
    )
    assert admits((company_room, Allowance(row=department("web", 100)), finance), 50)


def test_a_transfer_moves_a_ceiling_and_never_creates_one() -> None:
    """Conservation is what makes this a transfer rather than a raise. The obvious slip is to
    credit the destination and forget the debit, which reads as generosity in review and is an
    overspend in the ledger.

    Both sides come back at the next version with the author and the reason on them, which is
    the audited half: the question asked three months later is never how much, it is who
    agreed and why.

    Delete this and `apply_transfers` can quietly become `raise_ceiling` with a second
    department named in a string nobody parses."""
    rows = allocate(
        company(1_000_000),
        (DepartmentShare("web", 0.5), DepartmentShare("finance", 0.3)),
        author="rupash",
        effective_from=NOW,
    )
    before = sum(row.ceiling_minor for row in rows)

    moved = apply_transfers(
        rows,
        (
            Transfer(
                from_department="finance",
                to_department="web",
                amount_minor=50_000,
                author="rupash",
                at=LATER,
                reason="the Q4 migration lands in web",
            ),
        ),
    )
    by_name = {row.subject: row for row in moved}

    assert sum(row.ceiling_minor for row in moved) == before, "a transfer created budget"
    assert by_name["web"].ceiling_minor == 550_000
    assert by_name["finance"].ceiling_minor == 250_000
    for row in moved:
        assert row.version == 2
        assert row.author == "rupash"
        assert "Q4 migration" in row.reason


def test_a_transfer_names_both_sides_an_author_and_a_reason() -> None:
    """A transfer to itself is an edit to a ceiling wearing a transfer's paperwork, and it is
    the shape somebody reaches for when they want a raise and know a transfer is the only
    sanctioned path. The other three refusals are the paperwork itself.

    Delete this and `Transfer` becomes a way of writing any ceiling anybody likes, with the
    audit trail saying a department transferred to itself for no stated reason."""
    valid = {
        "from_department": "finance",
        "to_department": "web",
        "amount_minor": 10,
        "author": "rupash",
        "at": LATER,
        "reason": "agreed at the September budget review",
    }
    assert Transfer(**valid).amount_minor == 10  # type: ignore[arg-type]

    for broken, expected in (
        ({"to_department": "finance"}, "cannot transfer to itself"),
        ({"amount_minor": 0}, "moves nothing"),
        ({"author": ""}, "no author"),
        ({"reason": ""}, "no reason"),
    ):
        with pytest.raises(BudgetError, match=expected):
            Transfer(**{**valid, **broken})  # type: ignore[arg-type]


def test_a_transfer_cannot_drain_a_department_to_nothing_or_invent_one() -> None:
    """Draining a department to zero suspends it, and a suspension has an author, an
    announcement and a different form. A department with no row at all cannot receive a
    transfer either: a transfer moves budget between two funded departments and is not a way
    of creating one out of another's.

    Delete this and a transfer becomes the undocumented way to switch a department off, and
    the console still shows it as funded at zero."""
    rows = allocate(
        company(1_000_000),
        (DepartmentShare("web", 0.5), DepartmentShare("finance", 0.3)),
        author="rupash",
        effective_from=NOW,
    )
    drain = Transfer(
        from_department="finance",
        to_department="web",
        amount_minor=300_000,
        author="rupash",
        at=LATER,
        reason="everything",
    )
    with pytest.raises(BudgetError, match="that suspends it"):
        apply_transfers(rows, (drain,))

    unknown = Transfer(
        from_department="finance",
        to_department="legal",
        amount_minor=10,
        author="rupash",
        at=LATER,
        reason="a department that has no row",
    )
    with pytest.raises(BudgetError, match="has no budget row"):
        apply_transfers(rows, (unknown,))


# --------------------------------------------------------------- a person's two allowances
def test_one_person_cannot_hold_their_whole_departments_budget() -> None:
    """**The fair-share cap of M21.1.3.** Checked at three headcounts, including one, because
    a department of one is where the even split stops binding and only the cap is left. A
    department's budget also funds its agents and its automations, so even a sole member must
    not be able to take all of it.

    The cap is asserted against the department ceiling rather than against `USER_FAIR_SHARE`
    multiplied out by the test, which would be the arithmetic under test restated.

    Delete this and the cap becomes a comment, and the first person to run a backfill takes
    the department's month."""
    dept = department(ceiling=400_000)
    for headcount in (1, 10, 100):
        _daily, monthly = user_allowances(
            dept,
            principal_id="p_alice",
            headcount=headcount,
            author="rupash",
            effective_from=NOW,
        )
        assert monthly.ceiling_minor * 2 < dept.ceiling_minor, (
            f"at a headcount of {headcount} one person holds most of the department"
        )


def test_both_of_a_persons_allowances_bind_and_neither_subsumes_the_other() -> None:
    """The daily allowance catches a loop today and the monthly one catches the steady
    overspend that no single day looks wrong for.

    Two properties make that true and both are asserted from behaviour rather than from the
    constants. A day is strictly less than a month, or the daily figure is decoration. And a
    person spending the daily allowance every day of the month overruns the monthly one, or
    the monthly figure is decoration.

    Delete this and somebody derives the daily allowance as a thirtieth of the monthly one,
    which is tidy, refuses every ordinary busy day, and makes the monthly ceiling
    unreachable."""
    dept = department(ceiling=400_000)
    daily, monthly = user_allowances(
        dept, principal_id="p_alice", headcount=10, author="rupash", effective_from=NOW
    )

    assert daily.period is BudgetPeriod.DAY
    assert monthly.period is BudgetPeriod.MONTH
    assert daily.ceiling_minor < monthly.ceiling_minor
    assert daily.ceiling_minor * DAYS_IN_BUDGET_MONTH > monthly.ceiling_minor, (
        "spending every day at the daily cap stays inside the month, so the month never binds"
    )


def test_a_persons_money_share_is_the_same_fraction_as_their_share_of_a_connector() -> None:
    """`USER_FAIR_SHARE` is a quarter for the reason `limits.PRINCIPAL_FAIR_SHARE` is: it
    takes four heavy callers to exhaust a pool rather than one, and one person's backfill
    leaves three quarters for everybody's questions.

    Anchored on the other module's figure rather than on itself, which is the whole point of
    the assertion: a test reading `USER_FAIR_SHARE == 0.25` from the module it imported it
    from is green for every value it could hold. Diverging the two is allowed and needs an
    argument written next to it, which is what editing this test is.

    The remaining bounds are the properties that make the other two figures right rather than
    their values: a generosity at or below one is an even split, a burst at or below one
    refuses an ordinary busy day, and a burst at or above the month lets a loop spend the
    month before lunch.

    Delete this and every one of the four figures can be moved to anything at all with the
    suite green."""
    assert USER_FAIR_SHARE == PRINCIPAL_FAIR_SHARE
    assert 0.0 < USER_FAIR_SHARE < 1.0
    assert ALLOWANCE_GENEROSITY > 1.0
    assert 1.0 < DAILY_BURST < DAYS_IN_BUDGET_MONTH


def test_an_allowance_cannot_be_derived_from_a_budget_that_cannot_be_shared() -> None:
    """A department funded with three units has no fair share to give: a quarter of it rounds
    to nothing, so any allowance at all would be the whole department's budget. Refused rather
    than clamped to one unit, because a clamp hands one person the department and reports it
    as a fair share.

    The other two refusals are the ones that make the arithmetic mean something: a period that
    is not a month, and a department with nobody in it.

    Delete this and the fair-share cap silently stops applying at the bottom of the range,
    which is exactly where a new department starts."""
    with pytest.raises(BudgetError, match="cannot be shared"):
        user_allowances(
            department(ceiling=3),
            principal_id="p_alice",
            headcount=1,
            author="rupash",
            effective_from=NOW,
        )
    with pytest.raises(BudgetError, match="pretending the periods are the same"):
        user_allowances(
            dataclasses.replace(department(), period=BudgetPeriod.DAY),
            principal_id="p_alice",
            headcount=1,
            author="rupash",
            effective_from=NOW,
        )
    with pytest.raises(BudgetError, match="nobody to give an allowance to"):
        user_allowances(
            department(),
            principal_id="p_alice",
            headcount=0,
            author="rupash",
            effective_from=NOW,
        )


# ------------------------------------------------------------------------ agent ceilings
def test_an_agent_run_ceiling_above_its_day_ceiling_is_refused() -> None:
    """A run ceiling above the day ceiling can never bind, because the day ceiling stops the
    run first. A configured number that cannot have an effect is the kind of setting somebody
    later reads as protection they do not have.

    The positive sibling is asserted first: equal ceilings are accepted, which is the honest
    case of an agent allowed exactly one full run a day.

    Delete this and the console offers two fields where only one of them ever does
    anything."""
    per_run, per_day = agent_ceilings(
        agent_id="a_reporter",
        per_run_minor=500,
        per_day_minor=500,
        author="rupash",
        effective_from=NOW,
    )
    assert per_run.period is BudgetPeriod.RUN
    assert per_day.period is BudgetPeriod.DAY

    with pytest.raises(BudgetError, match="protection nobody has"):
        agent_ceilings(
            agent_id="a_reporter",
            per_run_minor=600,
            per_day_minor=500,
            author="rupash",
            effective_from=NOW,
        )


def test_an_agent_ceiling_narrows_its_caller_and_can_never_widen_them() -> None:
    """An agent is a lens, never a principal, and in the money dimension that means its
    ceilings are added to the caller's rather than substituted for them.

    Asserted as the property rather than as the implementation: for a generous agent and a
    mean one, adding the agent's allowances never admits something the caller alone would have
    refused. A substitution would pass every test that only tried the mean agent.

    Delete this and `narrowed_by_agent` becomes "use the agent's ceilings", which is the
    money spelling of an agent being a way round its caller's permissions."""
    caller = (Allowance(row=department("web", 1_000), spent_minor=980),)
    generous = (
        Allowance(
            row=agent_ceilings(
                agent_id="a",
                per_run_minor=100_000,
                per_day_minor=100_000,
                author="rupash",
                effective_from=NOW,
            )[0]
        ),
    )
    mean = (
        Allowance(
            row=agent_ceilings(
                agent_id="a",
                per_run_minor=5,
                per_day_minor=5,
                author="rupash",
                effective_from=NOW,
            )[0]
        ),
    )

    assert admits(caller, 20)
    assert admits(narrowed_by_agent(caller, generous), 20)
    assert not admits(narrowed_by_agent(caller, mean), 20)
    assert not admits(narrowed_by_agent(caller, generous), 21), (
        "the agent's ceiling replaced the caller's instead of narrowing it"
    )


# --------------------------------------------------------------------- naming what bound
def test_the_wider_of_two_equally_exhausted_budgets_is_the_one_named() -> None:
    """Raising somebody's own allowance while their department's is exhausted changes nothing,
    and a person sent to their department head who is then refused again has been sent to the
    wrong place twice.

    The non-tied case is asserted beside it, because a tie-break that also decided the
    ordinary case would report the company budget every time somebody ran out of anything: the
    tightest allowance is the one that bound, whatever level it sits at.

    Delete this and the tie is broken by whichever order the allowances were assembled in,
    which is a detail of the call site."""
    exhausted_company = Allowance(row=company(1_000), spent_minor=1_000)
    exhausted_user = Allowance(
        row=BudgetRow(
            level=BudgetLevel.USER,
            subject="p_alice",
            period=BudgetPeriod.MONTH,
            ceiling_minor=1_000,
            version=1,
            author="rupash",
            effective_from=NOW,
        ),
        spent_minor=1_000,
    )
    tie = tightest((exhausted_user, exhausted_company), 10)
    assert tie is not None
    assert tie.row.level is BudgetLevel.COMPANY

    roomy_company = Allowance(row=company(1_000_000), spent_minor=0)
    bound = tightest((exhausted_user, roomy_company), 10)
    assert bound is not None
    assert bound.row.level is BudgetLevel.USER


def test_every_budget_level_has_a_breadth_and_no_two_share_one() -> None:
    """`LEVEL_BREADTH` is what breaks the tie above, and a level missing from it raises at the
    moment two budgets are equally exhausted, which is the worst moment for a lookup to fail
    and one no test that never produced a tie would reach.

    Checked against `set(BudgetLevel)` in both directions rather than by counting, so that a
    level added without a breadth and a breadth left behind by a deleted level both fail.

    Delete this and a fifth budget level ships with a `KeyError` waiting in the refusal
    path."""
    assert level_gaps() == ()
    assert set(LEVEL_BREADTH) == set(BudgetLevel)
    assert len(set(LEVEL_BREADTH.values())) == len(BudgetLevel)


def test_an_empty_allowance_list_is_unlimited_by_configuration_rather_than_refused() -> None:
    """The positive case for the conjunction. A caller with no budget rows is a fresh install,
    and `limits.check` gives the same answer to an empty limit list: nothing governs this.

    It matters that this is stated in a test rather than left as a property of `all`, because
    the alternative reading, which is that no rows means no money, would take a working system
    down on the day somebody renamed a config key.

    Delete this and a defensive edit turns the empty case into a refusal, and every
    unconfigured install refuses every question with a budget message."""
    assert admits((), 10_000_000)
    assert tightest((), 10_000_000) is None
