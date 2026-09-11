"""The usage screen: four breakdowns of one row set, and what none of them may say.

Two things are asserted here and they pull against each other. A usage report has to be
useful enough that somebody can see who is consuming what, and it must not become a directory
of the people, agents and departments the reader holds no grant over.

The tests that matter most are not about a single table. A breakdown whose total is the sum of
its own lines discloses nothing, and every one here passes that on its own. The disclosure
this screen could carry is between two tables: four correct breakdowns of what a reader takes
to be one row set, where one of them was filtered differently, and the gap between two totals
is a count of what they may not see. `test_two_axes_of_one_admitted_set_carry_the_same_totals`
and `test_withholding_an_axis_changes_no_figure_on_the_axes_that_remain` are the pair that
holds that shut, and neither would be missed by a reviewer reading one table at a time.

Task ids: M27.4.2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from brain.console.screens import screen
from brain.console.spend_view import USAGE_AUTHORITY
from brain.console.usage_view import (
    AGENT_VOCABULARY,
    AXIS_DISCLOSURE,
    THE_FILTER,
    Admitted,
    Axis,
    UsageLine,
    UsageReport,
    UsageRow,
    UsageViewError,
    admit,
    axes_for,
    breakdowns,
    may_break_down_by,
    usage_by,
    usage_gaps,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.ops.spend import NO_AGENT

#: Pinned well away from any plausible wall clock. Nothing here is about the present, and a
#: fixture with today's date in it is a test that reports a defect on a schedule nobody chose.
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
ALREADY_OVER = datetime(2019, 1, 1, tzinfo=UTC)

USAGE = Capability(value="read:usage")
AGENTS = Capability(value="read:agent")

SUPPORT = "support"
FINANCE = "finance"


def a_row(
    *,
    department: str = SUPPORT,
    principal: str = "u_asker",
    model: str = "big",
    agent: str | None = "a_helper",
    tokens_in: int = 100,
    tokens_out: int = 20,
    machine: bool = False,
    at: datetime = NOW,
) -> UsageRow:
    """One completed run, through `UsageRow`'s own validators."""
    return UsageRow(
        principal_id=principal,
        principal_kind=PrincipalKind.SERVICE if machine else PrincipalKind.HUMAN,
        traffic=TrafficClass.AUTOMATION if machine else TrafficClass.HUMAN_INTERACTIVE,
        department=department,
        model=model,
        agent_id=agent,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        at=at,
    )


def a_reader(
    *departments: str,
    agents: bool = False,
    principal: str = "u_reader",
    not_after: datetime | None = None,
) -> EntitlementSet:
    """Somebody holding the usage grant over some departments, and perhaps the agent grant."""
    grants = [Grant(capability=USAGE, scope=Scope.department(one)) for one in departments]
    if agents:
        grants.append(Grant(capability=AGENTS, scope=Scope.unrestricted()))
    return EntitlementSet(principal_id=principal, grants=tuple(grants), not_after=not_after)


def everybody(*, agents: bool = False) -> EntitlementSet:
    """Somebody holding the usage grant company wide."""
    grants = [Grant(capability=USAGE, scope=Scope.unrestricted())]
    if agents:
        grants.append(Grant(capability=AGENTS, scope=Scope.unrestricted()))
    return EntitlementSet(principal_id="u_admin", grants=tuple(grants))


# ---------------------------------------------------------------------- the axes themselves
def test_the_axes_are_exactly_the_four_the_leaf_names_in_the_order_it_names_them() -> None:
    """Deleted, a fifth axis could be added with no decision about what it discloses.

    The literals are written here rather than read off the enum deliberately: comparing the
    enum against itself would be green for every set of members it could hold, which is the
    failure `CLAUDE.md` records catching three authors in one afternoon.
    """
    assert [one.value for one in Axis] == ["person", "department", "model", "agent"]


def test_the_agent_axis_is_read_behind_the_agents_screens_own_capability() -> None:
    """Deleted, the agent axis could drift onto a capability nobody grants, or onto the row
    grant, and either way the decision that a reader may learn which agents exist would be
    made here rather than where the Agents screen already makes it."""
    assert screen("agents").read.requires == AGENT_VOCABULARY
    assert AGENT_VOCABULARY.value == "read:agent"


def test_the_other_three_axes_are_read_behind_the_usage_screens_own_capability() -> None:
    """Deleted, the three axes computed over the reader's own rows could quietly acquire a
    grant of their own, which would be a second answer to a question `spend_view` already
    answers about the same rows."""
    assert USAGE_AUTHORITY.value == "read:usage"
    assert AXIS_DISCLOSURE[Axis.PERSON] == USAGE_AUTHORITY
    assert AXIS_DISCLOSURE[Axis.DEPARTMENT] == USAGE_AUTHORITY
    assert AXIS_DISCLOSURE[Axis.MODEL] == USAGE_AUTHORITY
    assert AXIS_DISCLOSURE[Axis.AGENT] != USAGE_AUTHORITY


def test_a_usage_grant_alone_offers_three_axes_and_not_the_agent_one() -> None:
    """Deleted, the agent axis could be offered on the row grant, which would name agents to
    a reader who cannot open the screen that lists them."""
    reader = a_reader(SUPPORT)
    assert axes_for(reader, now=NOW) == (Axis.PERSON, Axis.DEPARTMENT, Axis.MODEL)
    assert not may_break_down_by(Axis.AGENT, reader, now=NOW)


def test_the_agent_grant_adds_the_agent_axis_and_nothing_else() -> None:
    """The positive case for the refusal above. Deleted, a function that offered no axis at
    all would satisfy every test about withholding one."""
    reader = a_reader(SUPPORT, agents=True)
    assert axes_for(reader, now=NOW) == tuple(Axis)
    assert may_break_down_by(Axis.AGENT, reader, now=NOW)


def test_an_expired_reader_may_break_usage_down_by_nothing() -> None:
    """Deleted, `now` could stop being threaded into the grant check and a lapsed reader
    would keep every axis until somebody restarted the process."""
    lapsed = a_reader(SUPPORT, agents=True, not_after=ALREADY_OVER)
    assert axes_for(lapsed, now=NOW) == ()
    assert admit([a_row()], lapsed, now=NOW).rows == ()


# ------------------------------------------------------------------------- which rows at all
def test_a_row_from_a_department_the_reader_may_not_read_is_absent_from_every_axis() -> None:
    """Deleted, the model axis in particular would name a model used only by a department
    this reader holds nothing over, which is a fact about somebody else's work arriving
    through the one axis whose keys look harmless."""
    rows = [
        a_row(department=SUPPORT, model="big", principal="u_one", agent="a_one"),
        a_row(department=FINANCE, model="ledger", principal="u_two", agent="a_two"),
    ]
    admitted = admit(rows, a_reader(SUPPORT, agents=True), now=NOW)
    keys = {
        one.axis: {line.key for line in one.lines}
        for one in breakdowns(admitted, a_reader(SUPPORT, agents=True), now=NOW)
    }
    assert keys[Axis.DEPARTMENT] == {SUPPORT}
    assert keys[Axis.PERSON] == {"u_one"}
    assert keys[Axis.MODEL] == {"big"}
    assert keys[Axis.AGENT] == {"a_one"}


def test_a_department_the_reader_may_read_is_reported_in_full() -> None:
    """The sibling of every refusal above. Deleted, a filter that admitted nothing would pass
    all of them, and an empty screen looks exactly like a careful one."""
    rows = [
        a_row(department=SUPPORT, principal="u_one", tokens_in=100, tokens_out=20),
        a_row(department=SUPPORT, principal="u_two", tokens_in=7, tokens_out=3),
    ]
    report = usage_by(admit(rows, everybody(), now=NOW), Axis.PERSON, everybody(), now=NOW)
    assert report is not None
    assert report.total_runs == 2
    assert report.total_tokens_in == 107
    assert report.total_tokens_out == 23
    assert {line.key for line in report.lines} == {"u_one", "u_two"}


def test_a_reader_holding_nothing_is_admitted_to_nothing_rather_than_refused() -> None:
    """Deleted, an empty answer could become a refusal, and a refusal naming the capability
    would tell somebody a usage report exists."""
    nobody = EntitlementSet(principal_id="u_stranger")
    assert admit([a_row()], nobody, now=NOW).rows == ()
    assert axes_for(nobody, now=NOW) == ()
    assert breakdowns(admit([a_row()], nobody, now=NOW), nobody, now=NOW) == ()


def test_a_readers_own_run_outside_their_grant_is_still_absent() -> None:
    """Deleted, somebody would add the exception `spend_view.told_about` makes for a person's
    own allowance, and a row admitted because it is the reader's own carries a department,
    which then appears as a key on the department table for somebody with no grant over it."""
    mine = a_row(department=FINANCE, principal="u_reader")
    reader = a_reader(SUPPORT)
    assert admit([mine], reader, now=NOW).rows == ()
    report = usage_by(admit([mine], reader, now=NOW), Axis.DEPARTMENT, reader, now=NOW)
    assert report is not None
    assert report.lines == ()


# -------------------------------------------------------------------------- machine traffic
def test_automation_is_absent_from_a_usage_report_unless_it_is_asked_for() -> None:
    """Deleted, a nightly job would be the most active user in the company on a screen read
    to find out what people are doing."""
    rows = [a_row(principal="u_person"), a_row(principal="svc_sync", machine=True)]
    admitted = admit(rows, everybody(), now=NOW)
    assert [one.principal_id for one in admitted.rows] == ["u_person"]
    assert admitted.machine_included is False


def test_automation_is_reported_when_it_is_asked_for() -> None:
    """The positive case. Deleted, an admit that dropped every machine row whatever it was
    asked would pass the test above, and the question of what the automations actually
    consumed would have no answer at all."""
    rows = [a_row(principal="u_person"), a_row(principal="svc_sync", machine=True)]
    admitted = admit(rows, everybody(), now=NOW, include_machine=True)
    assert {one.principal_id for one in admitted.rows} == {"u_person", "svc_sync"}
    assert admitted.machine_included is True


def test_a_row_set_that_says_it_excludes_automation_cannot_hold_a_machine_row() -> None:
    """Deleted, a hand-assembled row set could carry automation under a qualifier saying it
    does not, and every report built from it would print that qualifier."""
    with pytest.raises(UsageViewError, match="excludes automation"):
        Admitted(
            reader_id="u_reader",
            rows=(a_row(principal="svc_sync", machine=True),),
            machine_included=False,
        )


# ------------------------------------------------- the disclosure between two tables
def test_two_axes_of_one_admitted_set_carry_the_same_totals() -> None:
    """The property the whole module is shaped around. Deleted, one axis could be filtered
    differently from another and the gap between their totals would be a count of what the
    reader may not see, with every line on both tables correct and nothing saying so."""
    rows = [
        a_row(principal="u_one", model="big", agent="a_one", tokens_in=100, tokens_out=20),
        a_row(principal="u_two", model="small", agent=None, tokens_in=7, tokens_out=3),
        a_row(principal="u_one", model="small", agent="a_two", tokens_in=40, tokens_out=60),
    ]
    reader = everybody(agents=True)
    reports = breakdowns(admit(rows, reader, now=NOW), reader, now=NOW)
    assert [one.axis for one in reports] == list(Axis)
    totals = {(one.total_runs, one.total_tokens_in, one.total_tokens_out) for one in reports}
    assert totals == {(3, 147, 83)}


def test_withholding_an_axis_changes_no_figure_on_the_axes_that_remain() -> None:
    """Deleted, an axis could be withheld by narrowing the rows rather than by dropping the
    table, and the reader without the agent grant would see smaller department figures than
    the reader with it. Two colleagues comparing screens would then read the difference as
    the usage of the agents one of them may not be told about."""
    rows = [
        a_row(principal="u_one", agent="a_one", tokens_in=100, tokens_out=20),
        a_row(principal="u_two", agent="a_private", tokens_in=7, tokens_out=3),
    ]
    wider = a_reader(SUPPORT, agents=True, principal="u_wide")
    narrower = a_reader(SUPPORT, principal="u_narrow")

    from_wider = {one.axis: one for one in breakdowns(admit(rows, wider, now=NOW), wider, now=NOW)}
    from_narrower = {
        one.axis: one for one in breakdowns(admit(rows, narrower, now=NOW), narrower, now=NOW)
    }

    assert set(from_wider) == set(Axis)
    assert set(from_narrower) == {Axis.PERSON, Axis.DEPARTMENT, Axis.MODEL}
    for axis, report in from_narrower.items():
        assert report == from_wider[axis]


def test_the_entitlement_offers_an_axis_and_never_narrows_the_rows_under_it() -> None:
    """Deleted, `usage_by` could filter the rows a second time by the entitlement handed to
    it, and the screen's tables would then disagree with each other depending on which reach
    each was rendered at.

    One person, two entitlement sets: the reach the rows were admitted at, and a narrower one
    built afterwards. The grouping is over what `admit` already decided.
    """
    rows = [
        a_row(department=SUPPORT, principal="u_one"),
        a_row(department=FINANCE, principal="u_two"),
    ]
    admitted = admit(rows, everybody(), now=NOW)
    narrowed_since = a_reader(SUPPORT, principal="u_admin")
    report = usage_by(admitted, Axis.DEPARTMENT, narrowed_since, now=NOW)
    assert report is not None
    assert {line.key for line in report.lines} == {SUPPORT, FINANCE}


def test_a_row_set_admitted_for_one_reader_cannot_be_grouped_for_another() -> None:
    """Deleted, the filtering and the grouping could come apart: a table computed at one
    person's reach would be rendered under another person's name, with every line on it
    arithmetically correct and nothing on the screen saying whose rows they are."""
    admitted = admit([a_row(department=FINANCE)], everybody(), now=NOW)
    somebody_else = a_reader(SUPPORT, principal="u_reader")
    with pytest.raises(UsageViewError, match="under another person's name"):
        usage_by(admitted, Axis.DEPARTMENT, somebody_else, now=NOW)
    with pytest.raises(UsageViewError, match="under another person's name"):
        breakdowns(admitted, somebody_else, now=NOW)


def test_an_axis_a_reader_may_not_have_is_absent_rather_than_empty_or_refused() -> None:
    """Deleted, a withheld axis could come back as an empty report, which says there was no
    usage, or as a raised error, which says there is an axis. Absence says neither."""
    reader = a_reader(SUPPORT)
    admitted = admit([a_row()], reader, now=NOW)
    assert usage_by(admitted, Axis.AGENT, reader, now=NOW) is None
    assert [one.axis for one in breakdowns(admitted, reader, now=NOW)] == [
        Axis.PERSON,
        Axis.DEPARTMENT,
        Axis.MODEL,
    ]


def test_a_report_cannot_state_a_total_over_rows_it_did_not_show() -> None:
    """Deleted, a report could be built with a company figure beside a filtered breakdown,
    which hands over the hidden usage in one subtraction with every line correctly scoped."""
    lines = (UsageLine(key=SUPPORT, runs=1, tokens_in=10, tokens_out=2),)
    with pytest.raises(UsageViewError, match="rows this reader was not shown"):
        UsageReport(
            axis=Axis.DEPARTMENT,
            lines=lines,
            machine_included=False,
            total_runs=9,
            total_tokens_in=10,
            total_tokens_out=2,
        )


def test_a_report_whose_totals_are_its_own_lines_is_accepted() -> None:
    """The sibling of the refusal above. Deleted, a constructor that refused every report
    would satisfy it, and no report would exist to be read."""
    lines = (UsageLine(key=SUPPORT, runs=1, tokens_in=10, tokens_out=2),)
    report = UsageReport(
        axis=Axis.DEPARTMENT,
        lines=lines,
        machine_included=False,
        total_runs=1,
        total_tokens_in=10,
        total_tokens_out=2,
    )
    assert report.total_tokens == 12


# ------------------------------------------------------------------------------- the buckets
def test_a_run_through_no_agent_is_bucketed_rather_than_dropped() -> None:
    """Deleted, the agent table would total to less than the other three, and the difference
    would be the usage of every run nobody attached an agent to."""
    rows = [
        a_row(agent="a_one", tokens_in=10, tokens_out=1),
        a_row(agent=None, tokens_in=5, tokens_out=1),
    ]
    reader = everybody(agents=True)
    report = usage_by(admit(rows, reader, now=NOW), Axis.AGENT, reader, now=NOW)
    assert report is not None
    assert {line.key for line in report.lines} == {"a_one", NO_AGENT}
    assert report.total_tokens_in == 15


def test_each_axis_buckets_by_its_own_field() -> None:
    """Deleted, one axis could group by another's field and the table would read correctly
    while answering a different question, which is exactly the failure nobody notices on a
    screen with four tables that all reconcile."""
    rows = [a_row(principal="u_one", department=SUPPORT, model="big", agent="a_one")]
    reader = everybody(agents=True)
    admitted = admit(rows, reader, now=NOW)
    keys = {}
    for axis in Axis:
        report = usage_by(admitted, axis, reader, now=NOW)
        assert report is not None
        keys[axis] = [line.key for line in report.lines]
    assert keys == {
        Axis.PERSON: ["u_one"],
        Axis.DEPARTMENT: [SUPPORT],
        Axis.MODEL: ["big"],
        Axis.AGENT: ["a_one"],
    }


def test_lines_are_ordered_by_tokens_largest_first_with_the_key_as_the_tie_break() -> None:
    """Deleted, two readings of one report could disagree about the order of two equal
    figures, and the largest consumer could sit anywhere on the table."""
    rows = [
        a_row(principal="u_small", tokens_in=1, tokens_out=1),
        a_row(principal="u_large", tokens_in=0, tokens_out=100),
        a_row(principal="b_tied", tokens_in=1, tokens_out=1),
    ]
    report = usage_by(admit(rows, everybody(), now=NOW), Axis.PERSON, everybody(), now=NOW)
    assert report is not None
    assert [line.key for line in report.lines] == ["u_large", "b_tied", "u_small"]


def test_tokens_in_and_tokens_out_are_reported_apart() -> None:
    """Deleted, the two could be summed into one figure, which reconciles against no invoice
    anybody will receive because every provider prices them differently."""
    rows = [a_row(tokens_in=90, tokens_out=10)]
    report = usage_by(admit(rows, everybody(), now=NOW), Axis.PERSON, everybody(), now=NOW)
    assert report is not None
    assert (report.total_tokens_in, report.total_tokens_out) == (90, 10)
    assert report.lines[0].tokens_in == 90
    assert report.lines[0].tokens_out == 10


def test_questions_asked_are_counted_per_bucket() -> None:
    """Deleted, the leaf's first figure would be missing: it asks for questions asked as well
    as tokens, and a thousand cheap questions and one long task are the same token count and
    a very different week."""
    rows = [a_row(principal="u_one") for _ in range(3)] + [a_row(principal="u_two")]
    report = usage_by(admit(rows, everybody(), now=NOW), Axis.PERSON, everybody(), now=NOW)
    assert report is not None
    assert {line.key: line.runs for line in report.lines} == {"u_one": 3, "u_two": 1}
    assert report.total_runs == 4


# ------------------------------------------------------------------------- the row's shape
def test_a_row_with_no_principal_department_or_model_cannot_be_built() -> None:
    """Deleted, a row with a blank department would be matched against nobody's scope and
    would be absent from every reader's report with nothing saying why."""
    with pytest.raises(UsageViewError, match="to group by"):
        a_row(principal=" ")
    with pytest.raises(UsageViewError, match="to group by"):
        a_row(department="")
    with pytest.raises(UsageViewError, match="to group by"):
        a_row(model="  ")


def test_a_row_with_a_blank_agent_id_cannot_be_built() -> None:
    """Deleted, a whitespace agent id would open a bucket nobody can name beside the
    no-agent bucket, and the agent table would carry two rows meaning the same thing."""
    with pytest.raises(UsageViewError, match="no-agent bucket"):
        a_row(agent="   ")


def test_a_negative_token_count_cannot_be_built() -> None:
    """Deleted, a figure derived from something withheld could be summed into a total nobody
    can reconcile, and the subtraction that produced it would be invisible."""
    with pytest.raises(UsageViewError, match="tokens are counts"):
        a_row(tokens_in=-1)
    with pytest.raises(UsageViewError, match="tokens are counts"):
        a_row(tokens_out=-1)


def test_a_naive_instant_cannot_be_built() -> None:
    """Deleted, a row would land in the wrong period at either end of a day and a usage
    report would move rows between months depending on who rendered it."""
    with pytest.raises(UsageViewError, match="naive instant"):
        a_row(at=NOW.replace(tzinfo=None))


def test_machine_is_derived_rather_than_declared() -> None:
    """Deleted, a caller could set the flag directly and there would be two answers to
    whether a run was somebody's, with the wrong one deciding a report."""
    assert a_row(machine=True).machine is True
    assert a_row(machine=False).machine is False
    human_on_a_schedule = UsageRow(
        principal_id="u_person",
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.AUTOMATION,
        department=SUPPORT,
        model="big",
        agent_id=None,
        tokens_in=1,
        tokens_out=1,
        at=NOW,
    )
    assert human_on_a_schedule.machine is True


# ------------------------------------------------------------------------------- the gaps
def test_this_module_reports_no_gaps_about_itself() -> None:
    """Deleted, every check below would still fire on an injected surface and none of them
    would ever be pointed at the real one."""
    assert usage_gaps() == ()


def test_a_function_that_could_look_a_department_up_is_reported() -> None:
    """Deleted, a reporting path could acquire a directory and answer for itself which
    department somebody is in, which is the join that stopped this leaf being claimed."""

    def report_for(directory: object) -> None:
        """A surface that could ask which department somebody is in."""

    found = usage_gaps(functions=[report_for])
    assert any("directory" in one for one in found)


def test_a_function_that_could_be_narrowed_to_an_area_it_was_asked_for_is_reported() -> None:
    """Deleted, a reader could name the department they wanted rather than being given the
    one their grant derives, which is the shape `scoped_authority` refuses for the same
    reason."""

    def report_for(department: str) -> None:
        """A surface that takes the area to report on."""

    assert any("department" in one for one in usage_gaps(functions=[report_for]))


def test_a_function_other_than_the_filter_taking_rows_is_reported() -> None:
    """Deleted, a second row set could reach a function that must not filter, and two tables
    on one screen would have been computed over two different reaches."""

    def group_by(rows: object) -> None:
        """A surface that could be handed rows the filter never saw."""

    assert any("rows" in one for one in usage_gaps(functions=[group_by]))


def test_the_filter_is_the_one_function_allowed_to_take_rows() -> None:
    """The sibling of the check above, and the reason it is a named exemption rather than an
    identity test. Deleted, the exemption could be repointed at a grouping function and the
    check would go quiet about the one function it exists to watch."""
    assert THE_FILTER == "admit"

    def admit(rows: object) -> None:
        """A stand-in carrying the exempt name."""

    assert not any("rows" in one for one in usage_gaps(functions=[admit]))


@dataclass(frozen=True)
class Tempting:
    """A shape somebody would add for a good reason, carrying two figures nobody may have."""

    key: str
    withheld: int
    of_total: int


def test_a_value_carrying_a_count_of_what_was_hidden_is_reported() -> None:
    """Deleted, a report could grow a residual bucket or a company denominator, which is the
    subtraction disclosure with a label on it."""
    found = usage_gaps(models=[Tempting])
    assert any("withheld" in one for one in found)
    assert any("of_total" in one for one in found)


def test_a_report_total_is_not_treated_as_a_count_of_what_was_hidden() -> None:
    """The other half of the check above. Deleted, the forbidden names could grow to include
    the word total, and the one figure this module argues is safe would be refused while the
    denominators that are not safe went unnamed."""
    assert usage_gaps(models=[UsageReport]) == ()


def test_an_axis_with_no_grant_behind_it_is_reported() -> None:
    """Deleted, an axis added without a decision about what it discloses would be silently
    withheld from everybody, and the silence would read as a decision."""
    partial = {Axis.PERSON: USAGE_AUTHORITY}
    found = usage_gaps(disclosure=partial)
    assert any("agent axis has no declared disclosure" in one for one in found)
    assert any("model axis has no declared disclosure" in one for one in found)


def test_the_agent_axis_pointing_at_another_screens_capability_is_reported() -> None:
    """Deleted, the axis could be repointed at the row grant and the check comparing it
    against the Agents screen would have nothing to say, so a usage table would name agents
    to a reader who cannot open the screen that lists them."""
    repointed = dict(AXIS_DISCLOSURE) | {Axis.AGENT: USAGE_AUTHORITY}
    found = usage_gaps(disclosure=repointed)
    assert any("cannot open the screen that lists them" in one for one in found)
