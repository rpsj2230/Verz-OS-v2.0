"""A company's first week, held to what it would do to the second company.

Every property here is about a decision onboarding makes on the client's behalf, and the test
of each is the same one the rest of this repository applies: would the line still be right on
a server belonging to a company nobody here has met. So no test asserts a vendor, a
department name or a figure that came from one deployment, and the ones that assert an
ordering assert it against a constructed set where the wrong answer is available.

Task ids: M34.1.1.1 M34.1.1.2 M34.1.1.3 M34.1.2.1 M34.1.2.2 M34.1.2.3 M34.2.1.1
Task ids: M34.2.2.3 M34.3.1.1 M34.3.1.2
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.adoption import (
    COVERAGE_MESSAGE,
    NEED_FOR,
    NEED_MESSAGE,
    QUESTION_SHAPES,
    STARTER_QUESTIONS,
    WEEK_ONE_TARGET,
    Action,
    AdoptionError,
    ChannelSurface,
    CitedItem,
    ConnectorOffer,
    Coverage,
    Need,
    ScopeCoverage,
    Sentence,
    SourceKind,
    StarterQuestion,
    Unanswered,
    connector_demand,
    correction_gaps,
    coverage_gaps,
    coverage_report,
    first_connector,
    posture_gaps,
    privacy_posture,
    shopping_list,
    starter_questions,
    verification_targets,
    visibility_summary,
)
from brain.locale import MESSAGES

SYNCED = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)

#: Three departments, three sources, one in each of the three coverage states.
ROWS = (
    ScopeCoverage(
        department="alpha",
        source="records-a",
        connected=True,
        records=812,
        last_sync=SYNCED,
        entities=(("deals", 400), ("contacts", 312), ("notes", 100)),
    ),
    ScopeCoverage(
        department="beta", source="records-b", connected=True, records=0, last_sync=SYNCED
    ),
    ScopeCoverage(department="gamma", source="records-c", connected=False),
)
EVERYWHERE = frozenset({"alpha", "beta", "gamma"})


# --- choosing the first source --------------------------------------------------------------


def test_the_first_connector_is_one_that_can_answer_before_anybody_uploads_a_file() -> None:
    """A document source answers nothing until somebody has chosen, uploaded, parsed and
    embedded a file, which is a week of work done by the person who is least convinced. The
    ordering is asserted against a set where the document source would win on every other
    criterion, so a function that ignored the kind would pick it.

    Delete this and week one becomes a week of uploading, which is the failure this
    ordering exists to prevent."""
    offers = (
        ConnectorOffer("files", SourceKind.DOCUMENTS, ("a", "b", "c"), True),
        ConnectorOffer("rows", SourceKind.RECORDS, ("a",), True),
    )

    assert first_connector(offers).name == "rows"


def test_a_source_nobody_can_open_loses_to_one_they_can() -> None:
    """The first answer is either evidence or theatre, and the difference is whether the
    person watching can open the system it came from and see the same figure. Checkability
    is ordered above reach for that reason, and the assertion is against a set where the
    unverifiable source reaches more departments.

    Delete this and the first demonstration is a number nobody in the room can confirm."""
    offers = (
        ConnectorOffer("opaque", SourceKind.RECORDS, ("a", "b", "c"), False),
        ConnectorOffer("open", SourceKind.RECORDS, ("a",), True),
    )

    assert first_connector(offers).name == "open"


def test_between_two_equal_sources_the_one_reaching_more_people_is_first() -> None:
    """Reach breaks the tie because the first connector should put the system in front of the
    most people who could ask it something, and the name breaks the tie after that so two
    runs of the same install agree.

    Delete this and the choice becomes whichever offer happened to be listed first."""
    offers = (
        ConnectorOffer("narrow", SourceKind.RECORDS, ("a",), True),
        ConnectorOffer("wide", SourceKind.RECORDS, ("a", "b"), True),
        ConnectorOffer("also-wide", SourceKind.RECORDS, ("a", "b"), True),
    )

    assert first_connector(offers).name == "also-wide"


def test_an_install_with_nothing_but_documents_is_a_conversation_and_not_a_default() -> None:
    """Falling back to a document source would produce a first week spent uploading with
    nothing said about it. A refusal makes it a decision somebody takes deliberately, which
    is the only honest handling of a client whose systems hold no records.

    The two refusals have to say different things, and that is the second half of the test.
    Offering nothing and offering only documents are different situations for whoever is
    reading the message: one is an install nobody has told about their systems and the other
    is a conversation about what week one will cost. A single refusal would tell the first
    of them that every source they offered holds documents, when they offered none.

    Delete this and the refusal becomes a silent fallback to the slowest possible start, or
    a message that is false for the empty case."""
    with pytest.raises(AdoptionError) as nothing:
        first_connector(())
    with pytest.raises(AdoptionError) as documents:
        first_connector((ConnectorOffer("files", SourceKind.DOCUMENTS, ("a",), True),))

    assert "document" not in str(nothing.value)
    assert "document" in str(documents.value)


def test_an_offer_with_no_name_or_no_department_cannot_be_considered() -> None:
    """A source reaching no department answers nobody, so connecting it is work with no
    result, and an offer with no name cannot be reported either way.

    Delete this and an empty offer can win the ordering by having nothing to sort on."""
    assert ConnectorOffer("rows", SourceKind.RECORDS, ("a",), True).departments == ("a",)
    with pytest.raises(AdoptionError):
        ConnectorOffer(" ", SourceKind.RECORDS, ("a",), True)
    with pytest.raises(AdoptionError):
        ConnectorOffer("rows", SourceKind.RECORDS, (), True)


# --- coverage, and the three states ---------------------------------------------------------


def test_a_source_nobody_connected_and_a_source_that_found_nothing_are_different_states() -> None:
    """Rendering both as zero tells a department the system looked and found nothing when it
    never looked, and the two need different actions from different people: one is a
    connector somebody authorises, the other is data somebody enters.

    Delete this and every coverage view sends both questions to the wrong person."""
    states = {one.department: one.state for one in ROWS}

    assert states == {
        "alpha": Coverage.CONNECTED,
        "beta": Coverage.CONNECTED_NO_RECORDS,
        "gamma": Coverage.NOT_CONNECTED,
    }
    assert len(set(Coverage)) == 3


def test_every_coverage_state_is_a_value_with_a_message_and_never_a_colour() -> None:
    """A status returned as a tone hands the renderer a colour and no meaning, so the only
    accessible rendering left is one that guesses back what the colour was supposed to say.
    Each state carries a catalogue key, which has already been proved to exist in every
    language this install offers.

    Delete this and a fourth state ships with no way to say it in words."""
    assert set(COVERAGE_MESSAGE) == set(Coverage)
    assert all(key in MESSAGES for key in COVERAGE_MESSAGE.values())
    assert len(set(COVERAGE_MESSAGE.values())) == len(Coverage)


def test_a_coverage_row_cannot_describe_two_states_at_once() -> None:
    """Four ways a row would be internally wrong, and the fourth is the one that ages badly: a
    count with no sync time is a figure nobody can date, so it goes on looking current for
    ever. A disconnected source carrying a count is a row that was written by two code paths.

    Delete these and a coverage screen can report a stale count as a live one."""
    assert ScopeCoverage("a", "s", connected=False).records is None

    with pytest.raises(AdoptionError):
        ScopeCoverage(" ", "s", connected=False)
    with pytest.raises(AdoptionError):
        ScopeCoverage("a", " ", connected=False)
    with pytest.raises(AdoptionError):
        ScopeCoverage("a", "s", connected=False, records=4, last_sync=SYNCED)
    with pytest.raises(AdoptionError):
        ScopeCoverage("a", "s", connected=True, records=-1, last_sync=SYNCED)
    with pytest.raises(AdoptionError):
        ScopeCoverage("a", "s", connected=True, records=4)
    with pytest.raises(AdoptionError):
        ScopeCoverage("a", "s", connected=True, records=4, last_sync=SYNCED, entities=(("x", 0),))


def test_a_coverage_report_says_nothing_about_a_scope_the_reader_cannot_reach() -> None:
    """The reach arrives narrowed and this filters to it. Both halves matter: the rows inside
    are all present, so a champion is not shown a thinner picture than they are entitled to,
    and no row outside appears in any form.

    Delete this and the first onboarding screen is where the entitlement rule stops
    applying, which is the screen most likely to be shown to a room."""
    narrow = coverage_report(ROWS, frozenset({"alpha"}))

    assert [one.department for one in narrow] == ["alpha"]
    assert len(coverage_report(ROWS, EVERYWHERE)) == len(ROWS)


def test_a_coverage_report_carries_no_total_a_reader_could_subtract_from() -> None:
    """The disclosure this repository refuses is the one that arrives by subtraction:
    "showing 3 of 12" tells a reader there are nine departments they were not shown. The
    result is a plain sequence with no denominator anywhere on it, so a caller wanting one
    would have to count what it did not pass in.

    Delete this and a summary line grows a total on the first commit that adds a heading."""
    narrow = coverage_report(ROWS, frozenset({"alpha"}))

    assert isinstance(narrow, tuple)
    assert not hasattr(narrow, "total")
    assert coverage_gaps([f"{one.department}: {one.state.value}" for one in narrow]) == ()


def test_a_rendered_percentage_or_a_how_many_of_how_many_is_refused() -> None:
    """The two shapes a progress figure arrives in. Both are counts of what the reader was not
    shown, and both read as helpful, which is why the check is on the rendered line rather
    than on the rows: the rows carry no total and whatever writes the sentence is where the
    disclosure is made.

    Delete this and the coverage screen grows a progress bar, which is both a leak and the
    wrong measurement."""
    findings = coverage_gaps(
        [
            "showing 3 of 12 departments",
            "coverage 45 % complete",
            "alpha: connected",
            "of the sources you can reach, all are connected",
        ]
    )

    assert len(findings) == 2


# --- the first questions ----------------------------------------------------------------------


def test_the_starter_questions_are_built_from_what_actually_indexed() -> None:
    """Generated from the entities that came back with rows, most populated first, and never
    from a list written in the module. A canned question works on the data it was written
    against and returns nothing for the first client whose records are shaped differently, in
    the week that decides whether anybody comes back.

    Delete this and the first three questions become three that happen to suit one client."""
    questions = starter_questions(ROWS, "alpha", checkable=frozenset({"records-a"}))

    assert [one.entity for one in questions] == ["deals", "contacts", "notes"]
    assert [one.shape for one in questions] == list(QUESTION_SHAPES)
    assert len(QUESTION_SHAPES) == STARTER_QUESTIONS


def test_a_department_with_less_indexed_than_asked_for_gets_fewer_and_not_padding() -> None:
    """Padding the list to three is how a question about nothing gets built in, and what the
    room learns from it is that the system cannot answer questions.

    Delete this and a thin first sync produces questions with no data behind them."""
    thin = (
        ScopeCoverage(
            department="alpha",
            source="records-a",
            connected=True,
            records=5,
            last_sync=SYNCED,
            entities=(("deals", 5),),
        ),
    )
    questions = starter_questions(thin, "alpha", checkable=frozenset({"records-a"}))

    assert len(questions) == 1
    with pytest.raises(AdoptionError):
        starter_questions(ROWS, "alpha", checkable=frozenset({"records-a"}), wanted=0)


def test_a_question_is_only_offered_when_its_answer_can_be_checked_somewhere_else() -> None:
    """Two enforcements of one rule, and the pair is deliberate: an unverifiable source
    contributes nothing before anything is built, and a question with nowhere to check it
    cannot be constructed even by a caller that skipped the first check.

    Delete either and the first answer becomes theatre, which is a demonstration the client
    has no way to disbelieve or to believe."""
    assert starter_questions(ROWS, "alpha", checkable=frozenset()) == ()
    assert starter_questions(ROWS, "delta", checkable=frozenset({"records-a"})) == ()

    with pytest.raises(AdoptionError):
        StarterQuestion(department="a", entity="deals", shape="starter.how_many", check_in=" ")
    with pytest.raises(AdoptionError):
        StarterQuestion(department="a", entity=" ", shape="starter.how_many", check_in="records-a")


def test_a_starter_question_renders_in_every_language_the_install_offers() -> None:
    """The shape is a catalogue key, so the first thing a company is shown is translated like
    everything else. A question built as an English sentence here would be the one string
    nobody thought of, on the screen most likely to be shown to a room.

    Delete this and week one is English-only on an install that offers two languages."""
    assert all(one in MESSAGES for one in QUESTION_SHAPES)
    with pytest.raises(AdoptionError):
        StarterQuestion(
            department="a", entity="deals", shape="How many deals?", check_in="records-a"
        )


# --- the shopping list ------------------------------------------------------------------------


def test_the_next_actions_are_ordered_by_what_people_asked_for_and_did_not_get() -> None:
    """The only ordering that is about the company rather than about the product. A list
    ordered by how much of this system is switched on would put the connector nobody wants
    above the one a department has asked for eleven times.

    Delete this and the shopping list becomes a checklist in whatever order the rows
    arrived, which is the order the connectors were written in."""
    ordered = shopping_list(ROWS, EVERYWHERE, {("beta", "records-b"): 11})

    assert [one.department for one in ordered] == ["beta", "gamma"]
    assert [one.department for one in shopping_list(ROWS, EVERYWHERE)] == ["beta", "gamma"]


def test_a_connected_scope_produces_no_action_and_the_two_unfinished_ones_differ() -> None:
    """Three states and two of them are work, and the two are not the same work: an
    unconnected source needs somebody to authorise it and an empty one needs somebody to find
    out why. A single "not done" state would send both to the same person, and one of them
    would be the wrong person.

    Asserted on the need rather than on a sentence, because two sentences that interpolate
    their own department name differ from each other however the branch behind them is
    written, which is a comparison that passes without measuring anything.

    Delete this and the two failures become one kind of work that neither owner can act on."""
    needs = {one.department: one.need for one in shopping_list(ROWS, EVERYWHERE)}

    assert needs == {
        "beta": Need.FIND_OUT_WHY_IT_IS_EMPTY,
        "gamma": Need.AUTHORISE_THE_SOURCE,
    }
    assert shopping_list(ROWS, frozenset({"alpha"})) == ()


def test_every_unfinished_state_maps_to_a_need_and_the_finished_one_maps_to_none() -> None:
    """The table is what makes the branch unnecessary, so the property it carries has to be
    asserted where the table is: every state that is work has exactly one kind of work, no
    two states share one, and the finished state has none.

    Delete this and a fourth coverage state can be added with nothing to do about it, or the
    two needs can collapse into one."""
    assert set(NEED_FOR) == set(Coverage) - {Coverage.CONNECTED}
    assert len(set(NEED_FOR.values())) == len(NEED_FOR) == len(Need)
    assert set(NEED_MESSAGE) == set(Need)
    assert all(key in MESSAGES for key in NEED_MESSAGE.values())


def test_an_action_about_no_department_or_no_source_cannot_be_built() -> None:
    """An action nobody owns is a line on a list that stays there, because the person who
    would have done it cannot tell that it is theirs.

    Delete this and a blank row can reach the champion's list."""
    assert Action("a", "s", Need.AUTHORISE_THE_SOURCE).need is Need.AUTHORISE_THE_SOURCE
    with pytest.raises(AdoptionError):
        Action(" ", "s", Need.AUTHORISE_THE_SOURCE)
    with pytest.raises(AdoptionError):
        Action("a", " ", Need.AUTHORISE_THE_SOURCE)


# --- the verification ritual -------------------------------------------------------------------


def test_the_documents_a_lead_verifies_first_are_the_ones_answers_already_quote() -> None:
    """The obvious five are the five most recently uploaded, which are the five the lead has
    already read. The five worth an hour are the ones answers are built from, because those
    are the passages a wrong document is being quoted through.

    Delete this and week one is spent verifying documents nothing cites, which changes no
    answer at all."""
    items = [
        CitedItem("quiet", "alpha", 0, verified=False),
        CitedItem("loud", "alpha", 40, verified=False),
        CitedItem("middling", "alpha", 9, verified=False),
        CitedItem("done", "alpha", 99, verified=True),
        CitedItem("elsewhere", "beta", 99, verified=False),
    ]
    chosen = verification_targets(items, "alpha")

    assert [one.item_id for one in chosen] == ["loud", "middling"]


def test_the_week_one_target_is_small_enough_that_somebody_with_a_job_finishes_it() -> None:
    """A target of twenty is a target that is missed, and a ritual missed in week one teaches
    that targets here are decoration. Asserted by handing in more candidates than the target
    and counting what comes back, so the figure cannot be moved in either direction without
    this failing.

    Delete this and the target becomes a number nobody has to defend."""
    many = [CitedItem(f"item-{one}", "alpha", 100 - one, verified=False) for one in range(20)]

    assert len(verification_targets(many, "alpha")) == WEEK_ONE_TARGET
    assert 2 <= WEEK_ONE_TARGET <= 10
    assert len(verification_targets(many, "alpha", target=2)) == 2
    with pytest.raises(AdoptionError):
        verification_targets(many, "alpha", target=0)


def test_a_negative_citation_count_is_refused_because_it_would_sort_to_the_bottom() -> None:
    """A count that cannot happen sorts silently rather than failing, and the item disappears
    off the end of a list somebody is relying on to be complete.

    Delete this and a bad row removes a document from every queue without an error."""
    assert CitedItem("a", "alpha", 0, verified=False).citations == 0
    with pytest.raises(AdoptionError):
        CitedItem("a", "alpha", -1, verified=False)


# --- correcting an answer ----------------------------------------------------------------------


def test_every_channel_that_delivers_an_answer_can_also_take_a_correction() -> None:
    """A correction path that exists only in the console is a path for the people who use the
    console, which is not who reads most answers. Somebody who would have to open a different
    application to report a wrong answer does not report it, and the wrong document stays
    cited for everybody.

    Delete this and a channel ships delivering answers with the feedback affordance as a
    second commit nobody writes."""
    findings = correction_gaps(
        [ChannelSurface("chat", corrects=False), ChannelSurface("console", corrects=True)]
    )

    assert len(findings) == 1
    assert findings[0].startswith("chat:")
    assert correction_gaps([ChannelSurface("console", corrects=True)]) == ()


# --- the connector roadmap ---------------------------------------------------------------------


def test_an_unanswered_question_is_recorded_without_the_question() -> None:
    """What somebody asked and did not get is a statement of what they were trying to find
    out, and storing it puts that under the permissions of whoever reads the roadmap rather
    than of whoever asked. The absence is structural: there is no field to put it in.

    Delete this and the most useful artefact in this module becomes a search history."""
    row = Unanswered("alpha", "records-c")

    assert set(vars(row)) == {"department", "missing_source"}
    with pytest.raises(AdoptionError):
        Unanswered(" ", "records-c")
    with pytest.raises(AdoptionError):
        Unanswered("alpha", " ")


def test_demand_is_counted_per_department_and_only_inside_the_readers_reach() -> None:
    """Keyed by the pair because "sales wanted this eleven times" is an argument a champion
    can take to the person who owns that system and "eleven times somewhere" is not. Rows
    outside the reach are not counted at all rather than counted anonymously, because a total
    including them is a number the reader can subtract their own figures from.

    Delete this and the roadmap becomes a way to measure another department's questions."""
    rows = [
        Unanswered("alpha", "records-c"),
        Unanswered("alpha", "records-c"),
        Unanswered("alpha", "records-d"),
        Unanswered("beta", "records-c"),
    ]
    counted = connector_demand(rows, frozenset({"alpha"}))

    assert counted == {("alpha", "records-c"): 2, ("alpha", "records-d"): 1}
    assert connector_demand(rows, frozenset()) == {}


# --- what the staff are told --------------------------------------------------------------------


def test_the_plain_language_summary_names_what_you_can_reach_and_never_what_you_cannot() -> None:
    """The explanation people ask for is a list of what the system holds and what they may
    have of it, and the second half is the whole disclosure. What is safe is the reader's own
    reach and the rule governing the rest, stated as a rule: nothing outside is listed, and
    finding nothing is never evidence of a refusal.

    Delete this and the friendliest page in the product becomes the map nobody was given."""
    summary = visibility_summary(["beta", "alpha"])

    assert [one.key for one in summary] == ["visibility.can_reach", "visibility.rule"]
    assert all(one.key in MESSAGES for one in summary)
    assert summary[0].fills == {"departments": "alpha, beta"}
    assert summary[1].fills == {}


def test_a_sentence_whose_placeholders_are_not_filled_cannot_be_built() -> None:
    """Too few fills renders a sentence with a value silently missing or raises inside the
    renderer at the moment somebody switches language; too many is a value somebody meant to
    show and did not. Both are checked against the catalogue rather than against a list
    written here, so a translator adding a placeholder in one language is caught.

    Delete this and the plain-language page is where a half-rendered sentence appears."""
    assert Sentence("visibility.rule", {}).fills == {}

    with pytest.raises(AdoptionError):
        Sentence("visibility.can_reach", {})
    with pytest.raises(AdoptionError):
        Sentence("visibility.rule", {"departments": "alpha"})
    with pytest.raises(AdoptionError):
        Sentence("not a message", {})


def test_a_person_who_can_reach_nothing_is_shown_no_summary_at_all() -> None:
    """An empty summary would tell somebody there is something to reach and that it is not
    theirs, which is the existence disclosure the summary exists to avoid making.

    Delete this and the page renders "you can ask about" followed by nothing."""
    with pytest.raises(AdoptionError):
        visibility_summary([])


def test_the_privacy_posture_changes_when_the_configuration_that_makes_it_true_changes() -> None:
    """A page saying that questions never leave the client's network is a sentence somebody
    typed, and it stays on the screen after an administrator switches to a hosted provider.
    Read off the configuration it cannot say that, and this asserts the change rather than
    the wording: two configurations, two different statements.

    Delete this and the privacy page becomes prose that is true on the day it is written."""
    inside = privacy_posture({})
    outside = privacy_posture(
        {"INSTALL_MODEL_PROFILE": "hosted", "INSTALL_BROKERED_DIRECTORY": "google"}
    )

    assert inside != outside
    assert inside[0] == "posture.model_local"
    assert outside[0] == "posture.model_hosted"
    assert inside[1] == "posture.directory_own"
    assert outside[1] == "posture.directory_brokered"
    assert inside[2] == outside[2] == "posture.entitled"


def test_every_posture_statement_is_in_the_catalogue_and_therefore_translated() -> None:
    """The gate for the real posture and the refusal for a statement nobody wrote. A posture
    key that existed in one language and was announced anyway would pass the catalogue's own
    check by being absent from it.

    Delete this and the privacy page is the one page that is English everywhere."""
    assert posture_gaps(privacy_posture({})) == ()
    assert posture_gaps(privacy_posture({"INSTALL_MODEL_PROFILE": "hosted"})) == ()
    assert len(posture_gaps(["posture.entitled", "a sentence somebody typed"])) == 1
