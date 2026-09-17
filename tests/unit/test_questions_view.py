"""The questions screen's reader decision: the gaps an install can name, and to whom.

Three properties carry the file. Nothing connected is identical for everybody, so any holder of the
screen's grant is told it and a reader without the grant is answered as a connected install is. A
recorded gap is shown by department through the screen's own grant, with its source named only
where the Connectors screen would name it, and nothing counts what was left out. And the sentences
the page quotes are the lane's own objects, with "I could not find that" the one sentence a refusal
and an absence share, which is why it is never counted as a gap.

Task ids: M27.7.18
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.console.operate import GAP_REASONS
from brain.console.questions_view import (
    GAP_COLUMNS,
    OUTCOME_COLUMNS,
    QUESTION_AUTHORITY,
    SCREEN_KEY,
    UNANSWERED_QUESTIONS_ARE_RECORDED,
    GapLine,
    QuestionsScreen,
    gap_lines,
    may_be_told_what_is_connected,
    questions_for_reader,
    questions_gaps,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.abstain import AbstentionReason
from brain.ops.question_gap_store import Gap
from brain.tables.adoption import QuestionAskedRow
from brain.tables.question_gap import QuestionGapRow
from brain.tables.telemetry import RequestTelemetryRow

#: The grants, written out rather than read from the modules under test.
QUESTIONS = Capability(value="read:question")
CONNECTORS = Capability(value="read:connector")

NOW = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)

#: The two sentences, as an asker reads them. Literals, so a change of wording in the lane is a
#: failing comparison here rather than a constant agreeing with itself.
NOTHING_CONNECTED = "Nothing I can reach is connected to that yet, so I have not guessed."
NOTHING_FOUND = "I could not find that."


def reader(
    scope: Scope | None, *, expired: bool = False, connectors: Scope | None = None
) -> EntitlementSet:
    """A reader holding the questions grant in `scope`, or holding nothing when it is None, and
    the connectors grant in `connectors` when one is given."""
    grants = () if scope is None else (Grant(capability=QUESTIONS, scope=scope),)
    if connectors is not None:
        grants = (*grants, Grant(capability=CONNECTORS, scope=connectors))
    return EntitlementSet(
        principal_id="u_reader",
        grants=grants,
        not_after=datetime(2019, 1, 1, tzinfo=UTC) if expired else None,
    )


def a_gap(trace: str, department: str, source: str) -> Gap:
    return Gap(trace_id=trace, department=department, source=source, at=NOW)


#: Five questions no connected source covered: three in support, two of them needing xero, and
#: two in finance needing hubspot and xero.
GAPS = (
    a_gap("t1", "support", "xero"),
    a_gap("t2", "support", "xero"),
    a_gap("t3", "support", "hubspot"),
    a_gap("t4", "finance", "hubspot"),
    a_gap("t5", "finance", "xero"),
)

#: A connectors grant narrowed to one source, as `brain.console.connector_trust` spells the field.
XERO_ONLY = Scope.model_validate({"clauses": [{"field": "connector", "op": "eq", "value": "xero"}]})


def test_a_company_wide_reader_on_an_install_with_nothing_connected_is_told_so() -> None:
    """The positive case, which every refusal below would pass by telling nobody anything.

    What breaks if this is deleted: a screen that never said nothing was connected would pass
    every test here, and an administrator whose staff all receive that sentence is never told.
    """
    shown = questions_for_reader(
        connected=False, gaps=(), entitlement=reader(Scope.unrestricted()), now=NOW
    )

    assert shown.nothing_connected is True


def test_a_department_scoped_reader_is_told_the_same_thing() -> None:
    """The gap has no department's version and every asker is told it, so scope does not narrow.

    What breaks if this is deleted: a department admin whose people are all being answered with
    nothing connected is shown a screen saying nothing about it.
    """
    shown = questions_for_reader(
        connected=False, gaps=(), entitlement=reader(Scope.department("support")), now=NOW
    )

    assert shown.nothing_connected is True


@pytest.mark.parametrize("scope", [Scope.unrestricted(), Scope.department("support")])
def test_an_install_with_a_source_connected_names_no_gap(scope: Scope) -> None:
    """Connected is not a gap, for any reader.

    What breaks if this is deleted: the screen says nothing is connected on an install that is
    answering questions, which sends an administrator to connect a source they already have.
    """
    shown = questions_for_reader(connected=True, gaps=(), entitlement=reader(scope), now=NOW)

    assert shown.nothing_connected is False


def test_a_reader_without_the_grant_is_answered_as_a_connected_install_is() -> None:
    """DENIED and ABSENT: the refused object equals the object with nothing to say.

    What breaks if this is deleted: a reader holding nothing learns from the response whether
    the install has anything connected, from a screen they may not open.
    """
    refused = questions_for_reader(connected=False, gaps=GAPS, entitlement=reader(None), now=NOW)
    connected = questions_for_reader(connected=True, gaps=GAPS, entitlement=reader(None), now=NOW)
    told_connected = questions_for_reader(
        connected=True, gaps=(), entitlement=reader(Scope.unrestricted()), now=NOW
    )

    assert refused == connected == told_connected


def test_an_expired_reader_may_not_be_told() -> None:
    """The instant is passed through, so an expired grant holds nothing.

    What breaks if this is deleted: the decision reads the process clock or no clock at all,
    and a lapsed contractor goes on being told what the install has connected.
    """
    assert may_be_told_what_is_connected(reader(Scope.unrestricted()), now=NOW) is True
    assert (
        may_be_told_what_is_connected(reader(Scope.unrestricted(), expired=True), now=NOW) is False
    )


def test_the_grant_is_judged_at_the_requests_instant_and_not_the_process_clock() -> None:
    """A grant lapsing after the request's instant and before today's clock still holds.

    The lapse is 2020, after `NOW` and before any wall clock this runs under, so the two
    instants give opposite answers and only the one the request carries is right.

    What breaks if this is deleted: `now` stops being passed to `scope_for`, the process clock
    is used instead, and the expired-reader test above still passes, because a grant that
    lapsed in 2019 is lapsed by either clock.
    """
    lapses_later = EntitlementSet(
        principal_id="u_reader",
        grants=(Grant(capability=QUESTIONS, scope=Scope.unrestricted()),),
        not_after=datetime(2020, 1, 1, tzinfo=UTC),
    )

    assert may_be_told_what_is_connected(lapses_later, now=NOW) is True


def test_the_sentences_carried_are_the_ones_an_asker_receives() -> None:
    """Quoted from the lane, and the not-found sentence is the one a refusal shares.

    What breaks if this is deleted: the page quotes a sentence askers never see, or a copy that
    drifted the afternoon somebody reworded one of the two.
    """
    shown = questions_for_reader(connected=False, gaps=(), entitlement=reader(None), now=NOW)

    assert shown == QuestionsScreen(
        nothing_connected=False,
        answered_when_nothing_connected=NOTHING_CONNECTED,
        answered_when_nothing_found=NOTHING_FOUND,
        gaps=(),
    )


def test_the_screen_is_the_registrys_questions_screen_read_behind_its_own_grant() -> None:
    """The key and the grant, compared with values written out here.

    What breaks if this is deleted: the module declares another screen, so the sweep counting
    reads with no screen reports the wrong module as served, or reads another screen's grant.
    """
    assert SCREEN_KEY == "questions"
    assert QUESTION_AUTHORITY == QUESTIONS


def test_nothing_records_every_unanswered_question_and_a_gap_holds_three_facts() -> None:
    """The constant the route copies, held to the two ledgers it describes, and the gap ledger
    held to a department, a source and an instant under its trace.

    What breaks if this is deleted: the page goes on saying only gaps are recorded after a ledger
    has started to record how every question ended, or a gap starts to carry who asked.
    """
    assert UNANSWERED_QUESTIONS_ARE_RECORDED is False
    for table in (QuestionAskedRow, RequestTelemetryRow):
        assert not set(table.__table__.columns.keys()) & OUTCOME_COLUMNS
    assert set(QuestionGapRow.__table__.columns.keys()) == {
        "trace_id",
        "department",
        "source",
        "at",
    }
    assert set(GAP_COLUMNS) == {"trace_id", "department", "source", "at"}


# ------------------------------------------------------------------------------ the lines
def test_a_company_wide_reader_of_both_screens_is_shown_every_line_by_source_most_asked_first() -> (
    None
):
    """The positive case for every narrowing below.

    What breaks if this is deleted: a screen that shows nobody a gap passes every refusal here.
    """
    shown = gap_lines(GAPS, reader(Scope.unrestricted(), connectors=Scope.unrestricted()), now=NOW)

    assert shown == (
        GapLine(department="support", source="xero", asked=2),
        GapLine(department="finance", source="hubspot", asked=1),
        GapLine(department="finance", source="xero", asked=1),
        GapLine(department="support", source="hubspot", asked=1),
    )


def test_a_department_scoped_reader_is_shown_that_department_and_no_trace_of_another() -> None:
    """The lines are the department's own, whole, and nothing on the answer counts finance.

    What breaks if this is deleted: a support admin reads how often finance asked for a source.
    """
    shown = gap_lines(
        GAPS, reader(Scope.department("support"), connectors=Scope.unrestricted()), now=NOW
    )

    assert shown == (
        GapLine(department="support", source="xero", asked=2),
        GapLine(department="support", source="hubspot", asked=1),
    )
    assert (
        gap_lines(
            GAPS[:3], reader(Scope.department("support"), connectors=Scope.unrestricted()), now=NOW
        )
        == shown
    )


def test_a_source_the_reader_may_not_be_told_is_merged_into_its_department_unnamed() -> None:
    """No connectors grant names no source; a grant narrowed to xero names xero and merges the
    rest, and the department's total is the same either way.

    What breaks if this is deleted: a reader who may not open the Connectors screen reads which
    systems the company runs off this one, or the merge drops the questions it cannot name.
    """
    unnamed = gap_lines(GAPS, reader(Scope.department("support")), now=NOW)
    one_named = gap_lines(GAPS, reader(Scope.department("support"), connectors=XERO_ONLY), now=NOW)

    assert unnamed == (GapLine(department="support", source=None, asked=3),)
    assert one_named == (
        GapLine(department="support", source="xero", asked=2),
        GapLine(department="support", source=None, asked=1),
    )


@pytest.mark.parametrize(
    "entitlement",
    [
        reader(None, connectors=Scope.unrestricted()),
        reader(Scope.unrestricted(), expired=True, connectors=Scope.unrestricted()),
        reader(Scope.department("hr"), connectors=Scope.unrestricted()),
    ],
    ids=["no_grant", "expired", "another_department"],
)
def test_a_reader_who_may_see_no_line_is_answered_as_an_install_with_no_gap(
    entitlement: EntitlementSet,
) -> None:
    """DENIED and ABSENT: no line, and the screen equal to one read over an empty ledger.

    What breaks if this is deleted: a reader whose grant reaches none of the departments learns
    that questions went unanswered somewhere.
    """
    assert gap_lines(GAPS, entitlement, now=NOW) == ()
    assert questions_for_reader(
        connected=True, gaps=GAPS, entitlement=entitlement, now=NOW
    ) == questions_for_reader(connected=True, gaps=(), entitlement=entitlement, now=NOW)


# ------------------------------------------------------------------------------- the gaps
def test_this_screen_reports_no_gaps_about_itself() -> None:
    """Green today, so every gap below is a change somebody made.

    What breaks if this is deleted: the checks below prove the diagnostic can find something
    and nothing proves this module is clean.
    """
    assert frozenset({AbstentionReason.NOTHING_CONNECTED}) == GAP_REASONS
    assert questions_gaps() == ()


@pytest.mark.parametrize(
    "reasons",
    [
        frozenset({AbstentionReason.NOTHING_CONNECTED, AbstentionReason.NOTHING_RETRIEVED}),
        frozenset(),
    ],
    ids=["a_refusal_counted_as_a_gap", "nothing_connected_no_longer_a_gap"],
)
def test_the_console_counting_other_gaps_than_this_screen_shows_is_reported(
    reasons: frozenset[AbstentionReason],
) -> None:
    """The console's gap decision and this screen moving apart, in either direction.

    What breaks if this is deleted: somebody adds nothing retrieved to the gap reasons, which
    counts refusals as holes, and this screen goes on quietly showing only one kind of gap.
    """
    found = questions_gaps(gap_reasons=reasons)

    assert len(found) == 1
    assert "this screen shows only nothing connected" in found[0]


def test_a_gap_ledger_that_starts_holding_more_than_a_department_and_a_source_is_reported() -> None:
    """The day a gap carries who asked or what they typed.

    What breaks if this is deleted: a principal column is added to `ops.question_gap` and the
    screen goes on calling it a roadmap rather than a search history.
    """
    found = questions_gaps(gap_columns=("trace_id", "department", "source", "at", "principal_id"))

    assert found == (
        "the gap ledger now has a column named principal_id, beyond a department, a source and "
        "an instant, so a gap may carry who asked or what they typed",
    )


def test_a_ledger_that_starts_recording_how_a_question_ended_is_reported() -> None:
    """The day the not-recorded sentence stops being true.

    What breaks if this is deleted: a reason column is added to the question ledger and the
    screen keeps telling administrators that nothing records one.
    """
    found = questions_gaps(ledger_columns=(("trace_id", "reason"), ("status",)))

    assert found == (
        "a question ledger now has a column named reason, so something may record how a "
        "question ended and this screen still says nothing does",
    )
