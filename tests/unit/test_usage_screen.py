"""The usage screen's reader decision: who asked, from where, and what is said about the rest.

Every property here is about one of two failures. The first is two tables on one screen that
subtract into a count of questions the reader may not see, so the person table and the
department table are held to one total for readers of every reach, including a reader whose own
question sits outside their grant. The second is a figure that looks measured and is not, so the
measures no ledger fills are held to the ledger's own record of what it leaves empty, and the
day that record changes a test here says the screen has nowhere to show the figure.

Dates are 2019, far from any wall clock, because nothing here is about the present.

Task ids: M27.7.14
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import pytest

from brain.adoption import AdoptionError, Asked, DepartmentAdoption
from brain.console import usage_view
from brain.console.screens import screen
from brain.console.usage_screen import (
    AUTOMATION_IS_COUNTED,
    MEASURED_BY,
    NO_SINGLE_MODEL,
    READ_BEHIND,
    SCREEN_KEY,
    SHOWN_WHEN_MEASURED,
    Measure,
    PersonLine,
    UsageScreen,
    UsageScreenError,
    not_measured,
    person_lines,
    token_rows,
    usage_for_reader,
    usage_screen_gaps,
)
from brain.console.usage_view import Axis
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.ops.spend import NO_AGENT
from brain.ops.telemetry import (
    FILLED_BY_A_MODEL_CALL,
    REQUEST_FIELDS,
    UNFILLABLE_TODAY,
    MeteredRequest,
)

#: The grants, written out rather than read from the modules under test, so a capability moved
#: in one place is a failing comparison rather than a constant agreeing with itself.
USAGE = Capability(value="read:usage")
AGENTS = Capability(value="read:agent")

NOW = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)
START = NOW - timedelta(days=7)
DIRECTORY = ("finance", "support", "web")


def asked(
    trace: str,
    *,
    person: str = "u_asker",
    department: str = "support",
    machine: bool = False,
    at: datetime = NOW - timedelta(hours=1),
) -> Asked:
    """One recorded question, through `Asked`'s own checks."""
    return Asked(
        trace_id=trace,
        principal_id=person,
        principal_kind=PrincipalKind.SERVICE if machine else PrincipalKind.HUMAN,
        channel=Channel.CONSOLE,
        department=department,
        at=at,
    )


def reader(
    department: str | None = None, *, agents: bool = False, usage: bool = True
) -> EntitlementSet:
    """A reader holding the usage grant over one department, or the company when None."""
    grants: list[Grant] = []
    if usage:
        scope = Scope.unrestricted() if department is None else Scope.department(department)
        grants.append(Grant(capability=USAGE, scope=scope))
    if agents:
        grants.append(Grant(capability=AGENTS, scope=Scope.unrestricted()))
    return EntitlementSet(principal_id="u_reader", grants=tuple(grants))


def questions() -> tuple[Asked, ...]:
    """Three people across two departments, and one schedule that must count nowhere."""
    return (
        asked("t1", person="u_ana", department="support"),
        asked("t2", person="u_ana", department="support"),
        asked("t3", person="u_ben", department="support"),
        asked("t4", person="u_cai", department="web"),
        asked("t5", person="u_job", department="web", machine=True),
    )


def screen_for(entitlement: EntitlementSet, rows: tuple[Asked, ...] | None = None) -> UsageScreen:
    return usage_for_reader(
        questions() if rows is None else rows,
        DIRECTORY,
        entitlement,
        start=START,
        end=NOW,
        now=NOW,
    )


# ------------------------------------------------------------------------ what is shown
def test_a_company_wide_reader_sees_every_question_by_department_and_by_person() -> None:
    """The positive case, which every narrowing test below would pass by showing nothing.

    What breaks if this is deleted: a screen that offered every reader empty tables would pass
    the rest of this file, because an empty table is what a reader holding nothing is shown.
    """
    shown = screen_for(reader())

    assert shown.departments == (
        DepartmentAdoption("finance", 0, 0),
        DepartmentAdoption("support", 3, 2),
        DepartmentAdoption("web", 1, 1),
    )
    assert shown.people == (
        PersonLine("u_ana", 2),
        PersonLine("u_ben", 1),
        PersonLine("u_cai", 1),
    )
    assert shown.questions == 4


def test_a_department_scoped_reader_sees_only_that_departments_questions_on_both_tables() -> None:
    """A person from another department is absent from the person table, not only its line.

    What breaks if this is deleted: the person table grouped over every question while the
    department table is narrowed, and a department admin reads the names of the people asking in
    every other department.
    """
    shown = screen_for(reader("support"))

    assert shown.departments == (DepartmentAdoption("support", 3, 2),)
    assert shown.people == (PersonLine("u_ana", 2), PersonLine("u_ben", 1))
    assert shown.questions == 3


@pytest.mark.parametrize("department", [None, "support", "web", "finance", "nowhere"])
def test_the_person_and_department_tables_always_total_the_questions_above_them(
    department: str | None,
) -> None:
    """For every reach, the two tables subtract into nothing.

    What breaks if this is deleted: the one disclosure no single table shows, which is a
    difference between two correct totals, stops being checked for the reaches where it would
    appear.
    """
    shown = screen_for(reader(department))

    assert shown.departments is not None and shown.people is not None
    assert sum(one.questions for one in shown.departments) == shown.questions
    assert sum(one.questions for one in shown.people) == shown.questions


def test_a_reader_holding_no_usage_grant_is_offered_no_table_no_total_and_no_sentence() -> None:
    """Absent rather than empty: nothing is offered, including what is not measured.

    What breaks if this is deleted: a reader with no usage grant shown a total of zero, which
    is a figure about the company and a false one, or told that tokens are not measured on a
    screen they may not open.
    """
    shown = screen_for(reader(usage=False))

    assert shown.departments is None
    assert shown.people is None
    assert shown.questions is None
    assert shown.not_measured == ()


def test_an_axis_withheld_on_its_own_leaves_the_other_table_and_its_total_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two axes are decided separately, so the screen must survive them coming apart.

    Today the person and the department axes share one grant, so they are offered together.
    Here the person axis is moved behind the agent grant, and a reader holding only the usage
    grant must still be shown the department table with a total that is its own sum, and no
    person table at all.

    What breaks if this is deleted: the screen treats the axes as offered only together, and
    the day `usage_view.AXIS_DISCLOSURE` gives the person axis a grant of its own, every reader
    without it is answered with a fault instead of the department table they may read.
    """
    monkeypatch.setattr(
        usage_view,
        "AXIS_DISCLOSURE",
        MappingProxyType({**usage_view.AXIS_DISCLOSURE, Axis.PERSON: AGENTS}),
    )

    shown = screen_for(reader())

    assert shown.people is None
    assert shown.departments is not None
    assert shown.questions == 4
    assert sum(one.questions for one in shown.departments) == 4


def test_a_reader_whose_departments_asked_nothing_sees_zero_lines_rather_than_no_screen() -> None:
    """A quiet department is a line of zeros and an empty person table, not an absent screen.

    What breaks if this is deleted: a department nobody asked in disappears from its admin's
    screen, which reads as a refusal of their own department.
    """
    shown = screen_for(reader("finance"))

    assert shown.departments == (DepartmentAdoption("finance", 0, 0),)
    assert shown.people == ()
    assert shown.questions == 0


def test_automated_questions_are_counted_on_neither_table() -> None:
    """A schedule is not a person and is not a department's asking.

    What breaks if this is deleted: a nightly job listed as the busiest person in a department,
    and the flag the route copies onto the response saying automation is not counted becomes
    false.
    """
    shown = screen_for(reader("web"))

    assert shown.people == (PersonLine("u_cai", 1),)
    assert shown.questions == 1
    assert AUTOMATION_IS_COUNTED is False


def test_the_readers_own_question_from_outside_their_grant_is_on_neither_table() -> None:
    """No self-exception, for the reason the multi-axis usage report gives.

    What breaks if this is deleted: a reader's own question admitted because it is theirs puts
    its department on the department table for somebody holding no grant over it.
    """
    rows = (*questions(), asked("t9", person="u_reader", department="web"))

    shown = screen_for(reader("support"), rows)

    assert all(one.person != "u_reader" for one in shown.people or ())
    assert [one.department for one in shown.departments or ()] == ["support"]


def test_people_are_listed_most_questions_first_and_then_by_name() -> None:
    """Two readings of one window agree about the order of two equal figures.

    What breaks if this is deleted: a person table whose order moves between loads, which reads
    on a paged screen as people appearing and disappearing.
    """
    rows = (
        asked("t1", person="u_zed"),
        asked("t2", person="u_amy"),
        asked("t3", person="u_mid"),
        asked("t4", person="u_mid"),
    )

    assert [one.person for one in person_lines(rows)] == ["u_mid", "u_amy", "u_zed"]


def test_a_malformed_window_is_refused_for_a_reader_offered_nothing_too() -> None:
    """The questions are chosen before any axis is decided, so a refused reader does the work.

    What breaks if this is deleted: a reader holding no grant is the one reader whose request
    over an empty window succeeds, which tells them the decision was taken before the read.
    """
    with pytest.raises(AdoptionError, match="holds no instant"):
        usage_for_reader(questions(), DIRECTORY, reader(usage=False), start=NOW, end=NOW, now=NOW)


# ------------------------------------------------------------------ what is not measured
def test_nothing_the_screen_is_asked_for_is_named_as_unmeasured_now_a_model_call_is_metered() -> (
    None
):
    """The ledger fills tokens, the model and the agent, so no reader is told any is missing.

    What breaks if this is deleted: the screen goes on saying tokens are not measured beside the
    token tables that measure them.
    """
    assert not_measured(reader(agents=True), now=NOW) == ()


def test_a_measure_the_ledger_cannot_fill_is_named_only_to_a_reader_who_may_have_its_axis() -> None:
    """A withheld axis is not mentioned as unmeasured either.

    What breaks if this is deleted: a reader who may not learn which agents exist is told that
    which agent answered is not recorded, which still says there is an agent axis.
    """
    unfilled = MappingProxyType({**UNFILLABLE_TODAY, **FILLED_BY_A_MODEL_CALL})

    assert not_measured(reader(), now=NOW, unfillable=unfilled) == (Measure.TOKENS, Measure.MODEL)
    assert not_measured(reader(agents=True), now=NOW, unfillable=unfilled) == (
        Measure.TOKENS,
        Measure.MODEL,
        Measure.AGENT,
    )


def test_a_measure_the_ledger_fills_is_no_longer_named() -> None:
    """The sentence follows the ledger rather than this module.

    What breaks if this is deleted: the screen goes on saying a measure is missing on the day a
    model call fills it, because the list was typed rather than read.
    """
    filled = MappingProxyType(
        {k: v for k, v in FILLED_BY_A_MODEL_CALL.items() if k not in ("tokens_in", "tokens_out")}
    )

    assert not_measured(reader(), now=NOW, unfillable=filled) == (Measure.MODEL,)


def test_every_measure_is_read_from_fields_a_model_call_fills_on_the_ledger() -> None:
    """Held against the telemetry module's lists, not against this module's own.

    What breaks if this is deleted: `MEASURED_BY` pointing at a field the ledger does not have, or
    at one nothing fills, so a measure is drawn as a table of nothing.
    """
    for measure in Measure:
        for field in MEASURED_BY[measure]:
            assert field in REQUEST_FIELDS
            assert field in FILLED_BY_A_MODEL_CALL
            assert field not in UNFILLABLE_TODAY
    assert READ_BEHIND == {
        Measure.TOKENS: Axis.DEPARTMENT,
        Measure.MODEL: Axis.MODEL,
        Measure.AGENT: Axis.AGENT,
    }
    assert frozenset(Measure) == SHOWN_WHEN_MEASURED


# ---------------------------------------------------------------------------- the tokens
def used(
    trace: str, *, person: str = "u_ana", model: str | None = "claude-sonnet-5", tokens: int = 10
) -> MeteredRequest:
    return MeteredRequest(
        trace_id=trace,
        principal=person,
        model=model,
        agent_version=None,
        tokens_in=tokens,
        tokens_out=tokens // 10,
    )


def tokens_by(shown: UsageScreen) -> dict[str, dict[str, tuple[int, int, int]]]:
    return {
        report.axis.value: {
            line.key: (line.runs, line.tokens_in, line.tokens_out) for line in report.lines
        }
        for report in shown.tokens
    }


def test_tokens_are_shown_by_person_department_and_model_for_the_questions_that_called_one() -> (
    None
):
    """The positive case: two of Ana's questions and Cai's called a model, Ben's did not.

    What breaks if this is deleted: a screen that never draws a token table passes every narrowing
    test below, because an absent table is what a narrowed reader is shown.
    """
    shown = usage_for_reader(
        questions(),
        DIRECTORY,
        reader(),
        start=START,
        end=NOW,
        now=NOW,
        metered=(used("t1", tokens=100), used("t2", tokens=50), used("t4", person="u_cai")),
    )

    assert tokens_by(shown) == {
        "person": {"u_ana": (2, 150, 15), "u_cai": (1, 10, 1)},
        "department": {"support": (2, 150, 15), "web": (1, 10, 1)},
        "model": {"claude-sonnet-5": (3, 160, 16)},
    }
    assert {report.total_tokens_in for report in shown.tokens} == {160}


def test_a_ledger_row_whose_question_this_reader_is_not_shown_contributes_nothing() -> None:
    """Joined to the chosen questions, never filtered on its own: a support reader is not shown
    web's tokens, a schedule's tokens, a ledger row naming another person under the same trace, or
    a model call that was not a question at all.

    What breaks if this is deleted: the token tables are a second answer to which requests this
    reader may know about, and the difference between the two is a count of what one withheld.
    """
    shown = usage_for_reader(
        questions(),
        DIRECTORY,
        reader("support"),
        start=START,
        end=NOW,
        now=NOW,
        metered=(
            used("t1", tokens=100),
            used("t4", person="u_cai", tokens=900),
            used("t5", person="u_job", tokens=900),
            used("t1", person="u_intruder", tokens=900),
            used("check-trace", person="u_admin", tokens=900),
        ),
    )

    assert tokens_by(shown) == {
        "person": {"u_ana": (1, 100, 10)},
        "department": {"support": (1, 100, 10)},
        "model": {"claude-sonnet-5": (1, 100, 10)},
    }


def test_a_request_answered_by_no_single_model_is_grouped_under_its_own_key() -> None:
    """Delete this and a request whose calls disagreed is dropped from the model table, which then
    totals less than the other three."""
    rows = token_rows((asked("t1", person="u_ana"),), (used("t1", model=None),))

    assert [one.model for one in rows] == [NO_SINGLE_MODEL]


def test_the_agent_table_is_shown_only_to_a_reader_who_may_know_agents_exist() -> None:
    """Delete this and a reader without the Agents screen's grant is told which agents answered."""
    metered = (used("t1"),)
    plain = usage_for_reader(
        questions(), DIRECTORY, reader(), start=START, end=NOW, now=NOW, metered=metered
    )
    agents = usage_for_reader(
        questions(), DIRECTORY, reader(agents=True), start=START, end=NOW, now=NOW, metered=metered
    )

    assert [one.axis for one in plain.tokens] == [Axis.PERSON, Axis.DEPARTMENT, Axis.MODEL]
    assert [one.axis for one in agents.tokens] == list(Axis)
    assert tokens_by(agents)["agent"] == {NO_AGENT: (1, 10, 1)}


def test_a_reader_holding_no_usage_grant_is_shown_no_token_table() -> None:
    """Delete this and the token tables are the one part of the screen a grantless reader sees."""
    shown = usage_for_reader(
        questions(),
        DIRECTORY,
        reader(usage=False),
        start=START,
        end=NOW,
        now=NOW,
        metered=(used("t1"),),
    )

    assert shown.tokens == ()


# ---------------------------------------------------------------------------- the shapes
def test_a_screen_whose_department_lines_do_not_total_its_questions_cannot_be_built() -> None:
    """The department table and the total disagreeing is a figure about unseen questions.

    What breaks if this is deleted: a total computed somewhere else travels beside lines it
    does not describe, and the difference is the count the screen exists not to show.
    """
    with pytest.raises(UsageScreenError, match="department lines sum to 1"):
        UsageScreen(
            start=START,
            end=NOW,
            departments=(DepartmentAdoption("support", 1, 1),),
            people=(PersonLine("u_ana", 2),),
            questions=2,
            not_measured=(),
        )


def test_a_screen_whose_person_lines_do_not_total_its_questions_cannot_be_built() -> None:
    """The same property on the other table.

    What breaks if this is deleted: a person table filtered differently from the department
    table, which is the subtraction this screen is built around.
    """
    with pytest.raises(UsageScreenError, match="person lines sum to 1"):
        UsageScreen(
            start=START,
            end=NOW,
            departments=(DepartmentAdoption("support", 2, 1),),
            people=(PersonLine("u_ana", 1),),
            questions=2,
            not_measured=(),
        )


def test_a_screen_whose_tables_total_its_questions_is_accepted() -> None:
    """The sibling of the two refusals above.

    What breaks if this is deleted: a constructor that refused every screen would pass both.
    """
    built = UsageScreen(
        start=START,
        end=NOW,
        departments=(DepartmentAdoption("support", 2, 1), DepartmentAdoption("web", 0, 0)),
        people=(PersonLine("u_ana", 2),),
        questions=2,
        not_measured=(Measure.TOKENS,),
    )

    assert built.questions == 2


def test_a_total_with_no_table_under_it_cannot_be_built() -> None:
    """A figure nobody can reconcile.

    What breaks if this is deleted: a reader offered no axis is shown the company's question
    count on its own.
    """
    with pytest.raises(UsageScreenError, match="figure with nothing under it"):
        UsageScreen(
            start=START, end=NOW, departments=None, people=None, questions=4, not_measured=()
        )


def test_tables_with_no_total_cannot_be_built() -> None:
    """The other half of the same pairing.

    What breaks if this is deleted: tables whose total a renderer adds up itself, which is the
    renderer that will one day be handed a list it did not draw all of.
    """
    with pytest.raises(UsageScreenError, match="no total"):
        UsageScreen(
            start=START, end=NOW, departments=(), people=None, questions=None, not_measured=()
        )


@pytest.mark.parametrize(("person", "count"), [("", 1), ("   ", 1), ("u_ana", 0), ("u_ana", -1)])
def test_a_person_line_with_no_person_or_no_questions_cannot_be_built(
    person: str, count: int
) -> None:
    """A line exists only for somebody who asked.

    What breaks if this is deleted: a person listed with no questions, whose name can only have
    come from a directory the usage grant does not open.
    """
    with pytest.raises(UsageScreenError):
        PersonLine(person=person, questions=count)


def test_the_screen_is_the_registrys_usage_screen_read_behind_the_usage_grant() -> None:
    """The key and the grant, compared with values written out here.

    What breaks if this is deleted: the module declares another screen's key, so the sweep that
    counts reads with no screen reports the wrong module as served.
    """
    assert SCREEN_KEY == "usage"
    assert screen(SCREEN_KEY).read.requires == USAGE


# ------------------------------------------------------------------------------- the gaps
def test_this_screen_reports_no_gaps_about_itself() -> None:
    """Green today, so every gap below is a change somebody made.

    What breaks if this is deleted: the checks below prove the diagnostic can find something
    and nothing proves this module is clean.
    """
    assert usage_screen_gaps() == ()


def test_a_measure_the_ledger_now_fills_is_reported_as_a_screen_with_nowhere_to_show_it() -> None:
    """The failure that would otherwise arrive as a sentence quietly disappearing.

    What breaks if this is deleted: the ledger fills a measure, the screen stops saying it is not
    measured, and nothing says the screen never learnt to show it.
    """
    found = usage_screen_gaps(shown=SHOWN_WHEN_MEASURED - {Measure.MODEL})

    assert len(found) == 1
    assert "model is measured and this screen has nowhere to show it" in found[0]


def test_a_measure_read_from_a_field_the_ledger_does_not_have_is_reported() -> None:
    """A not-measured sentence about a field that does not exist.

    What breaks if this is deleted: a renamed ledger field leaves this screen naming a measure
    for ever, because the old name is in no list of filled fields.
    """
    moved = {**MEASURED_BY, Measure.MODEL: ("model_name",)}

    found = usage_screen_gaps(
        unfillable={**UNFILLABLE_TODAY, **FILLED_BY_A_MODEL_CALL, "model_name": "x"},
        measured_by=moved,
    )

    assert found == (
        "model is read from model_name, which the request ledger does not have, so saying it is "
        "not measured is a claim about nothing",
    )


def test_a_measure_with_no_field_or_no_axis_is_reported() -> None:
    """A fourth measure added to the enum and to nothing else.

    What breaks if this is deleted: a measure nobody decided a source or a grant for, which the
    screen would then name to everybody or to nobody.
    """
    no_field: dict[Measure, tuple[str, ...]] = {
        k: v for k, v in MEASURED_BY.items() if k is not Measure.AGENT
    }
    no_axis: dict[Measure, Axis] = {k: v for k, v in READ_BEHIND.items() if k is not Measure.TOKENS}

    assert len(usage_screen_gaps(measured_by=no_field)) == 1
    assert len(usage_screen_gaps(read_behind=no_axis)) == 1
