"""Localisation and accessibility, held to the reader nobody in this repository is.

Every test here is about a decision the domain layer makes on somebody's behalf: which
language they read, which way round a date is, whether they can see the colour a status was
rendered in, and whether a screen reader is told an answer arrived. The properties are
written against the mechanism rather than against today's two locales, because the second
client's language is the one that finds out whether the mechanism was real.

Task ids: M35.1.1.1 M35.1.1.2 M35.1.1.3 M35.1.2.2 M35.2.1.1 M35.2.1.2
Task ids: M35.2.2.3 M35.2.2.4 M35.3.2.2
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from brain.install import BY_NAME, Belongs, value_of
from brain.locale import (
    AMBIGUOUS_ORDERS,
    BY_TAG,
    DEFERRALS,
    DETECTION_FLOOR,
    MESSAGES,
    MINIMUM_CONTRAST,
    MINIMUM_NON_TEXT_CONTRAST,
    PUSH_FOR_APPROVALS,
    PUSH_IS_DUE_ABOVE_HOURS,
    REASSURANCE_AFTER_SECONDS,
    RIGHT_TO_LEFT,
    SECTION_SHARE,
    SHIPPED,
    SHIPPED_TAGS,
    TOKENS_CSS,
    Announcement,
    DateOrder,
    Deferral,
    DetectedLanguage,
    Direction,
    FieldError,
    FormField,
    LocaleError,
    LocaleRules,
    Piece,
    Politeness,
    Script,
    Theme,
    Trigger,
    accent_gaps,
    accent_window,
    announcements,
    catalogue_gaps,
    contrast_gaps,
    contrast_ratio,
    currency,
    default_locale,
    detect,
    enabled_locales,
    form_gaps,
    format_date,
    format_money,
    format_number,
    format_timestamp,
    is_right_to_left,
    lexical_blind_to,
    lexical_tokens,
    locale_facts,
    presentation_gaps,
    rules_for,
    script_counts,
    script_of,
    text,
    theme_palettes,
    time_zone,
    triggered,
)

REPO = Path(__file__).resolve().parents[2]

#: A locale nothing ships, so a test can prove a rule is read from the table rather than
#: written into the function it is read by.
INVENTED = LocaleRules(
    tag="qq-Latn",
    endonym="Qqish",
    direction=Direction.LTR,
    date_order=DateOrder.DMY,
    date_marks=(".", ".", "."),
    decimal_point=",",
    group_separator=" ",
    group_size=4,
)


def a_locale(
    *,
    tag: str = "qq",
    endonym: str = "Qqish",
    decimal_point: str = ".",
    group_separator: str = ",",
    group_size: int = 3,
) -> LocaleRules:
    """A locale nothing ships, built with one field deliberately wrong at a time.

    A helper rather than six full constructions, because written out in full the difference
    between them is the thing that is hard to see, and the difference is the whole content
    of the test below.
    """
    return LocaleRules(
        tag=tag,
        endonym=endonym,
        direction=Direction.LTR,
        date_order=DateOrder.YMD,
        date_marks=("-", "-", ""),
        decimal_point=decimal_point,
        group_separator=group_separator,
        group_size=group_size,
    )


# --- the locale is configuration and what a locale means is not -----------------------------


def test_the_offered_languages_are_a_setting_and_not_a_constant() -> None:
    """The whole of M35's client independence in one assertion: which languages an install
    offers is read through the one reader, so a company nobody here has met sets it in their
    own environment file rather than finding this repository's answer compiled in.

    Delete this and a language list becomes a constant, which is the same defect as a
    company name in a default and is caught by nothing else."""
    declared = BY_NAME["INSTALL_LOCALES"]

    assert declared.belongs is Belongs.LOCALE
    assert value_of("INSTALL_LOCALES", {"INSTALL_LOCALES": "zh-Hans"}) == "zh-Hans"
    assert [one.tag for one in enabled_locales({"INSTALL_LOCALES": "zh-Hans"})] == ["zh-Hans"]


def test_the_default_locale_list_offers_every_catalogue_this_product_ships() -> None:
    """The default is asserted against `SHIPPED` rather than against the string `"en,zh-Hans"`,
    which is the difference between a test and a restatement: shipping a third catalogue and
    forgetting to offer it fails here, and a translation nobody is offered is a translation
    nobody reads.

    Delete this and the default silently stops naming a language the product can render."""
    assert BY_NAME["INSTALL_LOCALES"].default == ",".join(SHIPPED_TAGS)
    assert [one.tag for one in enabled_locales({})] == list(SHIPPED_TAGS)


def test_the_first_offered_locale_is_what_somebody_with_no_preference_reads() -> None:
    """First rather than English. The install that most needs a different default is the one
    where English is the second language, and a constant here would make every person on it
    change the same setting on their first morning.

    Delete this and `default_locale` can return a fixed tag while both tests above pass."""
    assert default_locale({"INSTALL_LOCALES": "zh-Hans,en"}).tag == "zh-Hans"
    assert default_locale({"INSTALL_LOCALES": "en,zh-Hans"}).tag == "en"


def test_an_install_offering_no_language_is_refused_rather_than_defaulted() -> None:
    """An empty setting and an unset one are different, and the empty one has to fail: a
    console offering no language is unusable, and falling back to English would make an
    obvious misconfiguration invisible on the one install where it matters.

    Delete this and `INSTALL_LOCALES=` starts an English-only system with nothing said."""
    with pytest.raises(LocaleError):
        enabled_locales({"INSTALL_LOCALES": "  ,  "})
    assert enabled_locales({"INSTALL_LOCALES": " en "})[0].tag == "en"


def test_the_same_locale_asked_for_twice_is_offered_once() -> None:
    """A switcher listing English twice is a switcher somebody reads as two different
    settings, and the duplicate arrives from an environment file somebody edited by hand.

    Delete this and `INSTALL_LOCALES=en,en` renders a list with a repeated entry."""
    assert [one.tag for one in enabled_locales({"INSTALL_LOCALES": "en,en,zh-Hans"})] == [
        "en",
        "zh-Hans",
    ]


def test_a_locale_with_no_catalogue_is_refused_and_not_rendered_in_english() -> None:
    """Falling back would mean a screen asking for French renders in English with nothing
    reporting it, which is the same silent half-translation `catalogue_gaps` exists to stop,
    one layer down.

    Delete this and an unshipped tag becomes a quiet English console."""
    with pytest.raises(LocaleError):
        rules_for("fr")
    assert rules_for("EN").tag == "en"


# --- dates, figures and money ---------------------------------------------------------------


def test_no_shipped_locale_writes_a_date_in_an_order_that_can_be_read_two_ways() -> None:
    """08/09/2026 is two different days depending on where the reader learnt to read, and a
    system whose answers cite dated documents cannot ship a rendering with that property.

    Delete this and a day-first order can be added to a shipped locale, and the ambiguity is
    invisible on eleven days out of twelve."""
    assert {DateOrder.DMY, DateOrder.MDY} == AMBIGUOUS_ORDERS
    assert all(one.date_order not in AMBIGUOUS_ORDERS for one in SHIPPED)


def test_the_date_order_is_read_from_the_locale_and_not_written_into_the_formatter() -> None:
    """Handing in a locale nothing ships is the only way to prove the ordering comes from the
    table: both shipped locales are year-first, so a formatter that ignored the table would
    pass every test written against them.

    Delete this and `format_date` can hardcode the order and stay green."""
    assert format_date(date(2026, 9, 8), rules_for("en")) == "2026-09-08"
    assert format_date(date(2026, 9, 8), rules_for("zh-Hans")) == "2026年09月08日"
    assert format_date(date(2026, 9, 8), INVENTED) == "08.09.2026."


def test_a_timestamp_with_no_zone_is_refused_rather_than_assumed_to_be_utc() -> None:
    """A naive datetime converted as though it were UTC renders correctly for readers in one
    zone and wrongly for everybody else, on some days of the year and not others, which is
    the failure nobody reports because it looks like a mistake somebody else made.

    Delete this and a naive value renders a date that is out by a day near midnight."""
    with pytest.raises(LocaleError):
        format_timestamp(datetime(2026, 9, 8, 23, 30), rules_for("en"), time_zone({}))
    aware = datetime(2026, 9, 8, 23, 30, tzinfo=UTC)
    assert format_timestamp(aware, rules_for("en"), time_zone({})) == "2026-09-08 23:30"


def test_a_timestamp_is_rendered_in_the_zone_this_install_configured() -> None:
    """The zone is client configuration, and a rendering that ignored it would show every
    colleague the implementer's own zone. Asserted by rendering one moment in two zones and
    getting two different days.

    Delete this and `INSTALL_TIME_ZONE` becomes a setting nothing reads."""
    aware = datetime(2026, 9, 8, 23, 30, tzinfo=UTC)
    east = time_zone({"INSTALL_TIME_ZONE": "Asia/Singapore"})

    assert format_timestamp(aware, rules_for("en"), east) == "2026-09-09 07:30"
    assert format_timestamp(aware, rules_for("en"), time_zone({})) == "2026-09-08 23:30"


def test_a_zone_this_machine_cannot_resolve_fails_where_it_was_set() -> None:
    """A misspelled zone that silently fell back would render every timestamp wrongly for a
    year, and the fallback would be the implementer's zone.

    Delete this and `INSTALL_TIME_ZONE=Asia/Singapor` starts and renders UTC."""
    with pytest.raises(LocaleError):
        time_zone({"INSTALL_TIME_ZONE": "Nowhere/Nowhere"})
    assert str(time_zone({})) == "UTC"


def test_a_figure_is_grouped_and_pointed_the_way_the_locale_writes_it() -> None:
    """Both shipped locales group in threes with a comma, so an invented locale is again the
    only proof the separators are read rather than assumed. Negative and fractional values
    are here because the sign and the fraction are separate branches.

    Delete this and a comma and a full stop can be written into the formatter."""
    assert format_number(Decimal("-1234567.50"), rules_for("en")) == "-1,234,567.50"
    assert format_number(Decimal("1234567.5"), INVENTED) == "123 4567,5"
    assert format_number(Decimal("999"), rules_for("en")) == "999"


def test_a_figure_keeps_exactly_the_precision_it_arrived_with() -> None:
    """Rounding here would be this module inventing precision the source system did not
    state, and a figure that gains or loses a place on the way to a screen is one somebody
    reconciles against and fails to.

    Delete this and two decimal places can be imposed on a whole-unit currency."""
    assert format_money(Decimal("1234"), rules_for("en"), "JPY") == "1,234 JPY"
    assert format_money(Decimal("1234.500"), rules_for("en"), "SGD") == "1,234.500 SGD"


def test_money_carries_a_currency_code_and_never_a_symbol() -> None:
    """A symbol is at least ten currencies and a code is one. A figure carrying a symbol has
    told the reader something they can act on and nothing they can check.

    Delete this and a dollar sign can be prepended, which is correct in one country."""
    rendered = format_money(Decimal("1234.50"), rules_for("en"), "SGD")

    assert rendered.endswith(" SGD")
    assert not any(one in rendered for one in "$£€¥")


def test_an_unconfigured_install_shows_a_currency_that_is_visibly_unset() -> None:
    """XXX is the ISO 4217 code meaning no currency. An install that has not chosen one shows
    something obviously wrong rather than a figure that reads correctly in the wrong money,
    which is the version somebody acts on.

    Delete this and the default becomes whichever currency the implementer was near."""
    assert currency({}) == "XXX"
    assert currency({"INSTALL_CURRENCY": "sgd"}) == "SGD"
    with pytest.raises(LocaleError):
        currency({"INSTALL_CURRENCY": "dollars"})
    with pytest.raises(LocaleError):
        format_money(Decimal("1"), rules_for("en"), "dollars")


# --- the catalogue --------------------------------------------------------------------------


def test_every_message_exists_in_every_language_this_install_offers() -> None:
    """The gate, run against the real catalogue, and it is meant to stay at zero. A key added
    in English alone renders as an exception or as English under a Chinese label, and the
    only person who would notice is the one who cannot read the other half.

    Delete this and the catalogue drifts on the first commit that adds a key."""
    assert catalogue_gaps() == ()
    assert set(SHIPPED_TAGS) <= set(MESSAGES["answer.complete"])


def test_a_missing_a_blank_or_a_differently_filled_message_is_reported() -> None:
    """Three shapes and the third is the one a reviewer misses: a translation that dropped
    `{example}` renders a sentence with the value silently gone, and one that renamed it
    raises inside the renderer at the moment somebody switches language.

    Delete this and `catalogue_gaps` can return an empty tuple for every input."""
    built = {
        "a.missing": {"en": "here"},
        "a.blank": {"en": "here", "zh-Hans": "   "},
        "a.renamed": {"en": "say {name}", "zh-Hans": "say {other}"},
        "a.fine": {"en": "say {name}", "zh-Hans": "shuo {name}"},
    }
    findings = catalogue_gaps(built, ("en", "zh-Hans"))

    assert len(findings) == 3
    assert any("a.missing" in one for one in findings)
    assert any("a.blank" in one for one in findings)
    assert any("a.renamed" in one for one in findings)
    assert not any("a.fine" in one for one in findings)


def test_asking_for_a_message_that_has_no_translation_refuses_rather_than_falling_back() -> None:
    """A fallback means the catalogue is never finished, because nothing anywhere reports the
    gap. The strictness is only affordable because the test above runs in the suite, and the
    two are a pair.

    Delete this and `text` can quietly answer in English for every language."""
    assert text("answer.complete", rules_for("zh-Hans")) == MESSAGES["answer.complete"]["zh-Hans"]
    with pytest.raises(LocaleError):
        text("not.a.key", rules_for("en"))
    with pytest.raises(LocaleError):
        text("answer.complete", INVENTED)


def test_a_locale_that_could_not_be_read_or_could_not_render_a_figure_is_refused() -> None:
    """Six constructions, each a way a locale would be wrong rather than unusual: a tag that
    is not one, no endonym so a switcher can only name it in another language, a decimal
    point written as whitespace, no group separator at all, one character doing both
    separator jobs, and grouping that separates every digit. The endonym and the decimal
    point are refused for a space as well as for an empty string, because a space is what an
    empty field becomes when somebody fills it in to get past a check.

    A space *is* accepted as a group separator, and the last assertion is why: French writes
    1 234 567, so refusing it would be this repository deciding that a real locale is a typo.

    Delete these and a locale can be added that renders figures incorrectly."""
    assert a_locale().language == "qq"
    assert a_locale(group_separator=" ").group_separator == " "

    with pytest.raises(LocaleError):
        a_locale(tag="not a tag")
    with pytest.raises(LocaleError):
        a_locale(endonym="")
    with pytest.raises(LocaleError):
        a_locale(endonym=" ")
    with pytest.raises(LocaleError):
        a_locale(decimal_point=" ")
    with pytest.raises(LocaleError):
        a_locale(group_separator="")
    with pytest.raises(LocaleError):
        a_locale(group_separator=".")
    with pytest.raises(LocaleError):
        a_locale(group_size=1)


# --- what language a document is in ---------------------------------------------------------


def test_a_document_holding_two_languages_is_indexed_under_both_and_not_its_majority() -> None:
    """A contract whose body is English and whose schedule is Chinese is mostly English, and
    labelling it English is how the schedule stops being retrievable in the language it is
    written in. Nothing reports that: the document is found by English queries and the
    Chinese ones return nothing, which reads as the schedule not existing.

    Delete this and `detect` can return the dominant language alone."""
    mixed = detect("本合同的正文为中文 and the schedule below is written in English for the team")

    assert mixed.tag == "en"
    assert set(mixed.languages) == {"en", "zh-Hans"}
    assert mixed.mixed

    single = detect("This paragraph is entirely English and is long enough to be counted")
    assert single.languages == ("en",)
    assert not single.mixed


def test_a_language_below_the_section_share_is_a_word_and_not_a_section() -> None:
    """The share is what separates a product name in an English page from an appendix
    somebody will search for in its own language. Asserted from both sides so the figure
    cannot move in either direction unnoticed.

    Delete this and `SECTION_SHARE` can be set to anything, including zero."""
    assert Decimal("0.01") < SECTION_SHARE < Decimal("0.4")
    sprinkled = detect("This is an English sentence long enough to count and it mentions 合同")
    assert sprinkled.languages == ("en",)

    substantial = detect("English body text here plus 本附件全部以中文书写并且相当长")
    assert set(substantial.languages) == {"en", "zh-Hans"}


def test_a_text_too_short_to_be_evidence_is_recorded_as_unknown_and_not_as_english() -> None:
    """A detector that always returns a language turns "we could not tell" into "English",
    which is a claim nothing later can distinguish from a measurement. A row saying unknown
    can be improved; one saying English will not be looked at again.

    Delete this and every two-word document in the corpus is labelled English."""
    assert DETECTION_FLOOR > 1
    assert detect("a" * (DETECTION_FLOOR - 1)).tag is None
    assert detect("a" * DETECTION_FLOOR).tag == "en"
    assert detect("1234567890 !!! ??? ,,,").tag is None


def test_a_document_in_a_script_with_no_catalogue_is_unknown_rather_than_guessed() -> None:
    """The detector distinguishes the two scripts this product ships catalogues for and has
    no opinion about the rest, which is honest and is the state the record has to be able to
    hold: a Greek document is not English, and neither is one whose only Latin characters are
    a page number.

    Delete this and a document in a third script is labelled with whichever of the two
    happened to have a character in it, which is a wrong fact rather than a missing one."""
    greek = detect("Ω" * (DETECTION_FLOOR * 2))
    assert greek.tag is None
    assert greek.languages == ()

    mostly_greek = detect("Ω" * 100 + "page")
    assert mostly_greek.tag is None
    assert detect("Ω" * 10 + "this is an english sentence that is long enough").tag == "en"


def test_a_detection_record_cannot_say_it_found_nothing_and_indexed_something() -> None:
    """The two fields have to agree or a consumer reading one gets a different answer from a
    consumer reading the other, and the disagreement is invisible until a document is
    retrievable in a language nothing detected.

    Delete this and a row can carry a tag that is not in its own language list."""
    assert DetectedLanguage(tag="en", languages=("en",), counts={Script.LATIN: 30}).mixed is False
    with pytest.raises(LocaleError):
        DetectedLanguage(tag=None, languages=("en",), counts={})
    with pytest.raises(LocaleError):
        DetectedLanguage(tag="en", languages=(), counts={})
    with pytest.raises(LocaleError):
        DetectedLanguage(tag="en", languages=("zh-Hans", "en"), counts={})


def test_a_character_that_says_nothing_about_language_is_counted_as_nothing() -> None:
    """Digits, punctuation and spaces are shared by every language, and counting them would
    make a page of figures look like whichever script its handful of words happened to be in.

    Delete this and an invoice full of numbers is detected as whatever its footer is in."""
    assert script_of("A") is Script.LATIN
    assert script_of("合") is Script.HAN
    assert script_of("Ω") is Script.OTHER
    assert script_of("7") is None
    assert script_of(" ") is None
    assert script_counts("ab 12 合") == {Script.LATIN: 2, Script.HAN: 1}


# --- lexical tokens for a script the parser cannot segment ----------------------------------


def test_a_run_of_han_characters_becomes_overlapping_bigrams_and_not_one_token() -> None:
    """PostgreSQL's default parser has no Chinese dictionary, so a phrase is one token and a
    query for a term inside it matches nothing. The symptom is a Chinese query returning
    fewer rows rather than an error, which is why nothing catches it.

    Delete this and the tokeniser can return the phrase whole and look correct."""
    assert lexical_tokens("服务级别协议") == ("服务", "务级", "级别", "别协", "协议")
    assert "级别" in lexical_tokens("服务级别协议")
    assert lexical_tokens("合") == ("合",)


def test_latin_words_are_kept_whole_and_separated_at_a_space() -> None:
    """The bigram treatment is for the script that needs it and for nothing else. A tokeniser
    that ran the Latin characters together would make "hello world" one token and would be
    caught by no Chinese test at all.

    Delete this and every English phrase collapses into a single unsearchable token."""
    assert lexical_tokens("Hello world 2026") == ("hello", "world", "2026")
    assert lexical_tokens("SLA 服务级别 ok") == ("sla", "服务", "务级", "级别", "ok")
    assert lexical_tokens("") == ()


def test_a_text_the_lexical_index_cannot_segment_says_so_rather_than_returning_nothing() -> None:
    """A caller combining lexical and vector results has to know the lexical half contributed
    nothing. Without that, an empty lexical result reads as evidence that nothing matched,
    which is the silent degradation this leaf is about.

    Delete this and a Chinese query looks like an English query that found nothing."""
    assert lexical_blind_to("服务级别")
    assert not lexical_blind_to("SLA agreement")
    assert not lexical_blind_to("one 合 character only")


# --- right to left, and push, deferred with a stated trigger --------------------------------


def test_every_deferral_names_a_trigger_something_can_answer() -> None:
    """A trigger of "when clients ask for it" is one nobody can evaluate, and a deferral with one is
    an abandonment with better manners. A `Trigger` member is a question this system can be
    asked, which is what makes the deferral reviewable rather than permanent.

    Delete this and a deferral can be added with prose where its trigger should be."""
    assert set(DEFERRALS) == {RIGHT_TO_LEFT, PUSH_FOR_APPROVALS}
    assert all(isinstance(one.trigger, Trigger) for one in DEFERRALS)
    assert {one.trigger for one in DEFERRALS} == set(Trigger)


def test_a_deferral_with_no_subject_or_no_reason_is_refused() -> None:
    """A deferral is a record that somebody decided, and one with a blank reason is the word
    "later" in a dataclass. Whitespace counts as blank because a space is what an empty field
    becomes when somebody fills it in to get past a check.

    Delete this and `DEFERRALS` can grow an entry that explains nothing."""
    assert Deferral(what="a", trigger=Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR, reason="b").what
    with pytest.raises(LocaleError):
        Deferral(what=" ", trigger=Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR, reason="b")
    with pytest.raises(LocaleError):
        Deferral(what="a", trigger=Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR, reason=" ")


def test_no_shipped_locale_runs_right_to_left_and_asking_for_one_names_the_deferral() -> None:
    """The model can express a right-to-left locale and the layout has never rendered one, so
    the honest state is a refusal that says which deferral it is rather than a console that
    silently runs the wrong way or an unknown-tag error that explains nothing.

    Delete this and an Arabic tag either fails opaquely or ships a mirrored layout nobody
    in this repository could read to find out it was wrong."""
    assert all(one.direction is Direction.LTR for one in SHIPPED)
    assert is_right_to_left("ar") and is_right_to_left("uz-Arab") and not is_right_to_left("en")

    with pytest.raises(LocaleError) as refusal:
        rules_for("he")
    assert RIGHT_TO_LEFT.reason in str(refusal.value)


def test_asking_for_a_right_to_left_locale_is_what_makes_that_work_due() -> None:
    """The trigger has to fire off something observable, and the observable is the setting.
    An install that asks for Hebrew has the requirement; one that does not has a deferral
    with a reason, and the difference is readable from the configuration alone.

    Delete this and the trigger becomes a sentence nothing evaluates."""
    assert locale_facts({})[Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR] is False
    asked = locale_facts({"INSTALL_LOCALES": "en,he"})

    assert asked[Trigger.A_RIGHT_TO_LEFT_LOCALE_IS_ASKED_FOR] is True
    assert triggered(asked) == (RIGHT_TO_LEFT,)
    assert triggered(locale_facts({})) == ()


def test_a_trigger_nobody_supplied_a_fact_for_is_not_reported_as_fired() -> None:
    """The two facts come from different places: one is configuration and one is a
    measurement somebody else takes. A caller holding one should still get an answer about
    it rather than being made to invent the other, and an absent fact must not read as true.

    Delete this and a caller that knows nothing about approval latency is told push is due."""
    assert triggered({}) == ()
    assert triggered({Trigger.APPROVALS_WAIT_LONGER_THAN_THE_STATED_HOURS: True}) == (
        PUSH_FOR_APPROVALS,
    )


def test_the_push_threshold_is_shorter_than_a_working_day_and_longer_than_an_hour() -> None:
    """A threshold of an hour fires on a busy afternoon and one of a day never fires, because
    by then somebody has complained. The figure is bounded rather than asserted against
    itself, so moving it out of the band that makes it a signal fails here.

    Delete this and the threshold can be set to a number that can never be reached."""
    assert 1 < PUSH_IS_DUE_ABOVE_HOURS < 8
    assert str(PUSH_IS_DUE_ABOVE_HOURS) in PUSH_FOR_APPROVALS.reason


# --- what a screen reader is told -----------------------------------------------------------


def test_no_fragment_of_an_arriving_answer_is_ever_announced() -> None:
    """An aria-live region is announced on every mutation, so a token stream is read letter by
    letter and restarted on each token. No politeness setting fixes it: the fragments have to
    carry no announcement at all, and only the domain layer knows when the answer is done.

    Delete this and a screen reader user cannot hear a single complete answer."""
    said = announcements([(Piece.FRAGMENT, 0.1), (Piece.STEP, 0.2), (Piece.CITATION, 0.3)])

    assert said == ()


def test_a_finished_answer_is_announced_exactly_once_and_politely() -> None:
    """Once, because a second announcement of the same event is the letter-by-letter problem
    with a longer interval. Politely, because the reader asked for this and is waiting for
    it, and an assertive interruption for an expected event teaches somebody to switch the
    region off.

    Delete this and completion is announced on every subsequent frame or not at all."""
    said = announcements(
        [(Piece.FRAGMENT, 0.1), (Piece.DONE, 1.0), (Piece.FRAGMENT, 1.1), (Piece.DONE, 1.2)]
    )

    assert said == (Announcement(key="answer.complete", politeness=Politeness.POLITE),)


def test_a_long_silence_gets_one_reassurance_and_a_short_one_gets_none() -> None:
    """A reader who cannot see tokens arrive has nothing between the question and the answer,
    and after twenty seconds the reasonable conclusion is that the page is broken. A fast
    answer says one thing rather than two, which is why the reassurance is suppressed.

    Delete this and either every answer says "still working" or none ever does."""
    slow = announcements([(Piece.FRAGMENT, 0.1), (Piece.DONE, float(REASSURANCE_AFTER_SECONDS))])
    fast = announcements([(Piece.FRAGMENT, 0.1), (Piece.DONE, 1.0)])

    assert [one.key for one in slow] == ["answer.working", "answer.complete"]
    assert [one.key for one in fast] == ["answer.complete"]


def test_a_failure_interrupts_and_a_completion_does_not() -> None:
    """A failure is the one event the reader is not waiting for and the one where continuing
    to wait is wrong, so it is the only assertive announcement in the module.

    Delete this and a failed answer is announced politely behind whatever is being read, or
    an ordinary completion interrupts."""
    failed = announcements([(Piece.FRAGMENT, 0.1), (Piece.ERROR, 2.0)])
    slow_failure = announcements([(Piece.ERROR, float(REASSURANCE_AFTER_SECONDS) + 1)])

    assert failed == (Announcement(key="answer.failed", politeness=Politeness.ASSERTIVE),)
    assert [one.key for one in slow_failure] == ["answer.working", "answer.failed"]


def test_the_reassurance_never_fires_more_often_than_the_transport_calls_silence() -> None:
    """Anchored against `brain.gate.streaming.HEARTBEAT_SECONDS` rather than against itself.
    The transport already decided that ten seconds of quiet needs a keep-alive, and a
    reassurance firing more often than that would be announcing that the connection is open.

    Delete this and the threshold can be dropped to a second and every test above still
    passes, because each supplies its own timings."""
    from brain.gate.streaming import HEARTBEAT_SECONDS

    assert REASSURANCE_AFTER_SECONDS >= 2 * HEARTBEAT_SECONDS


def test_an_announcement_that_is_not_in_the_catalogue_cannot_be_built() -> None:
    """An announcement built as English prose in the domain layer is a sentence that never
    reaches `catalogue_gaps` and is read to a Chinese-speaking colleague in English.

    Delete this and a screen reader announcement becomes the one string nobody translates."""
    assert Announcement(key="answer.complete", politeness=Politeness.POLITE).key in MESSAGES
    with pytest.raises(LocaleError):
        Announcement(key="an English sentence", politeness=Politeness.POLITE)


def test_a_reassurance_threshold_of_nothing_is_refused() -> None:
    """Zero announces silence before there is any, which is the letter-by-letter failure
    arriving through the parameter rather than through the design.

    Delete this and a caller passing 0 makes every answer announce twice."""
    with pytest.raises(LocaleError):
        announcements([(Piece.DONE, 1.0)], quiet_after=0)
    assert announcements([(Piece.DONE, 1.0)], quiet_after=1) != ()


# --- forms, labels and error association ----------------------------------------------------


def test_a_form_field_carries_a_label_key_so_labelling_and_translating_are_one_job() -> None:
    """A renderer given a key cannot draw the field without a label, and the key has already
    been proved to exist in every language. A label supplied as a string would be an English
    label everywhere and a renderer could omit it entirely.

    Delete this and an unlabelled input is a valid form field."""
    field = FormField(
        name="department",
        label_key="field.department.label",
        errors={"required": "field.department.required"},
    )

    assert form_gaps([field]) == ()
    with pytest.raises(LocaleError):
        FormField(name=" ", label_key="field.department.label", errors={})
    with pytest.raises(LocaleError):
        FormField(name="department", label_key=" ", errors={})


def test_an_error_that_names_no_field_on_this_form_cannot_be_associated_with_an_input() -> None:
    """An error arriving as a sentence, or naming a field the form does not have, can only be
    read out at the top of the page, where a screen reader announces it with nothing saying
    which input to go back to.

    Delete this and error association becomes something a renderer is trusted to do."""
    field = FormField(
        name="department",
        label_key="field.department.label",
        errors={"required": "field.department.required"},
    )
    findings = form_gaps([field], [FieldError(field="nowhere", key="field.department.required")])

    assert len(findings) == 1
    assert form_gaps([field], [FieldError("department", "field.department.required")]) == ()


def test_a_field_or_an_error_naming_a_message_nobody_wrote_is_reported() -> None:
    """Three separate ways a form becomes English-only or unreadable: a label key nobody
    translated, an error key nobody translated, and a field that can be rejected with nothing
    to say about it.

    Delete this and `form_gaps` can return an empty tuple for every input."""
    findings = form_gaps(
        [
            FormField(name="a", label_key="not.a.key", errors={"x": "also.not.a.key"}),
            FormField(name="b", label_key="field.department.label", errors={}),
        ],
        [FieldError(field="a", key="third.missing.key")],
    )

    assert len(findings) == 4


# --- contrast, in both themes ---------------------------------------------------------------


def test_a_token_after_a_dark_block_belongs_to_the_light_palette_again(tmp_path: Path) -> None:
    """The parser tracks nesting, and nothing in the real stylesheet proves it does: its dark
    blocks are last, so a parser that never closed one would still file every light token
    correctly. A constructed sheet with a light declaration *after* the dark block is the
    only shape where forgetting to close makes a difference, and forgetting is silent, because
    the wrong answer is a populated palette rather than an empty one.

    The stray closing brace is the second half. A sheet with one is malformed, and the parser
    has to carry on rather than raise on an empty stack, because a stylesheet this cannot read
    would take the contrast check out with it.

    Delete this and the brace handling can be removed and every other test here still
    passes."""
    sheet = tmp_path / "tokens.css"
    sheet.write_text(
        "}\n"
        ":root { --bg: #ffffff; }\n"
        "@media (prefers-color-scheme: dark) { :root { --bg: #000000; } }\n"
        ":root { --fg: #111111; }\n",
        encoding="utf-8",
        newline="\n",
    )
    palettes = theme_palettes(sheet)

    assert palettes[Theme.LIGHT] == {"bg": "#ffffff", "fg": "#111111"}
    assert palettes[Theme.DARK] == {"bg": "#000000"}


def test_the_console_palette_is_read_from_the_stylesheet_and_not_restated_here() -> None:
    """A copy of the palette in Python agrees with the stylesheet on the day it is written
    and never again, and the failure is silent: the check keeps passing about colours nobody
    renders. Both themes come back populated, which is what the comment-stripping is for.

    Delete this and the parser can return an empty light palette while `contrast_gaps`
    reports missing tokens rather than a parse that went wrong."""
    palettes = theme_palettes(REPO / TOKENS_CSS)

    assert palettes[Theme.LIGHT]["bg"] != palettes[Theme.DARK]["bg"]
    assert len(palettes[Theme.LIGHT]) > 10
    assert len(palettes[Theme.DARK]) == len(palettes[Theme.LIGHT])


def test_every_pair_a_reader_has_to_read_clears_the_text_contrast_floor_in_both_themes() -> None:
    """The gate, run against the real stylesheet. A palette is designed in one theme, usually
    the light one, and the dark values are checked by somebody looking at them rather than
    measuring them; the pair that fails is a muted grey on a dark surface, for the reader who
    most needs it to pass.

    Delete this and a theme change ships an unreadable console."""
    assert contrast_gaps(theme_palettes(REPO / TOKENS_CSS)) == ()


def test_a_faint_pair_and_a_renamed_token_are_both_reported() -> None:
    """Both directions, because a check that skipped a missing token would go green by
    measuring nothing, which is how a renaming quietly removes a rule.

    Delete this and `contrast_gaps` can return an empty tuple for every palette."""
    faint = {
        Theme.LIGHT: {"text": "#cccccc", "bg": "#ffffff"},
        Theme.DARK: {"text": "#ffffff", "bg": "#000000"},
    }
    findings = contrast_gaps(faint, (("text", "bg"), ("gone", "bg")))

    assert len(findings) == 3
    assert contrast_gaps(faint, (("text", "bg"),))[0].startswith("light:")


def test_the_contrast_ratio_is_the_same_whichever_way_round_the_colours_arrive() -> None:
    """A pair that passed one way and failed the other would be a check whose result depended
    on which token somebody wrote first.

    Delete this and the ratio can be computed as foreground over background and go below one
    for light text."""
    assert contrast_ratio("#000000", "#ffffff") == contrast_ratio("#ffffff", "#000000")
    assert round(contrast_ratio("#000000", "#ffffff")) == 21
    assert contrast_ratio("#fff", "#ffffff") == 1
    with pytest.raises(LocaleError):
        contrast_ratio("#12", "#ffffff")


def test_no_single_client_colour_can_clear_the_text_floor_on_both_grounds() -> None:
    """Measured rather than asserted, and it is why the accent is held to the non-text floor.
    At 4.5 to 1 the band a colour must sit in to stand off the light ground ends below the
    band for the dark one, so the requirement is not strict, it is unsatisfiable. At 3 to 1
    the bands overlap and the configured default sits inside.

    Delete this and the accent floor becomes a number somebody chose, and raising it to 4.5
    would make the check red on every install and therefore switched off."""
    palettes = theme_palettes(REPO / TOKENS_CSS)
    strict_floor, strict_ceiling = accent_window(palettes, MINIMUM_CONTRAST)
    open_floor, open_ceiling = accent_window(palettes, MINIMUM_NON_TEXT_CONTRAST)

    assert strict_floor > strict_ceiling
    assert open_floor < open_ceiling
    assert MINIMUM_NON_TEXT_CONTRAST < MINIMUM_CONTRAST


def test_a_ground_that_admits_a_lighter_and_a_darker_accent_is_refused_not_narrowed() -> None:
    """Narrowing to one of two bands would return a window tighter than the truth and report
    perfectly usable colours as failures. A mid grey at a low ratio is the case, and it is
    refused rather than guessed at.

    Delete this and `accent_window` silently answers a question it cannot answer."""
    grey = {Theme.LIGHT: {"bg": "#808080"}, Theme.DARK: {"bg": "#808080"}}
    with pytest.raises(LocaleError):
        accent_window(grey, Decimal("1.5"))
    assert accent_window({Theme.LIGHT: {}, Theme.DARK: {}}, MINIMUM_CONTRAST) == (
        Decimal(0),
        Decimal(1),
    )


def test_the_accent_a_client_configures_is_checked_against_both_grounds() -> None:
    """The accent arrives on install day from somebody holding a brand guideline and no
    contrast meter, on a light screen, for a console that also has a dark theme. It is the
    one contrast value that cannot be settled in this repository and the one most likely to
    fail.

    Delete this and a client's brand colour disappears into the dark theme with nothing
    saying so."""
    palettes = theme_palettes(REPO / TOKENS_CSS)

    assert accent_gaps(value_of("INSTALL_ACCENT_COLOUR", {}), palettes) == ()
    assert len(accent_gaps("#101418", palettes)) == 1
    assert len(accent_gaps("#f7f8fa", palettes)) == 1
    assert accent_gaps("#101418", {Theme.LIGHT: {}, Theme.DARK: {}}) != ()


def test_this_installs_presentation_is_correct_before_anybody_opens_it() -> None:
    """The three checks in one call, run against the real tree and the neutral configuration,
    so a sweep or a console screen asks one question. Zero on arrival is the point: a check
    that is red the day it lands is a check somebody switches off.

    Delete this and the catalogue, the palette and the accent are each checked alone and
    nothing checks that a default install is readable."""
    assert presentation_gaps(REPO, {}) == ()


#: Full-width stop, comma, question mark and exclamation mark, by code point.
#:
#: Written as code points rather than as the characters, because ruff's ambiguous-character
#: rule is exactly what refuses them and a test containing them would fail the gate it is
#: about. Ideographs are fine and the catalogue is full of them; it is the punctuation that
#: is confusable with ASCII.
FULL_WIDTH_TERMINATORS = (chr(0x3002), chr(0xFF0C), chr(0xFF1F), chr(0xFF01))


def test_a_message_never_ends_in_a_full_width_terminator() -> None:
    """Not a style rule. Full-width punctuation is what ruff's ambiguous-character check
    refuses in this repository, and a translation pasted from a document carries it in
    silently, so the commit that adds one fails lint with nothing explaining why.

    Delete this and the next translated string breaks the lint gate for a reason nobody
    finds, because the message is about a character that looks like a full stop."""
    for key, entries in MESSAGES.items():
        for tag, value in entries.items():
            assert not value.endswith(FULL_WIDTH_TERMINATORS), f"{key}/{tag}"


def test_every_shipped_locale_is_reachable_by_tag_and_by_index() -> None:
    """`BY_TAG` and `SHIPPED_TAGS` are both derived from `SHIPPED`, and the derivation is what
    makes adding a locale a one-line change rather than three that can disagree.

    Delete this and a locale can be shipped that `rules_for` cannot find."""
    assert set(BY_TAG) == {one.tag.lower() for one in SHIPPED}
    assert tuple(one.tag for one in SHIPPED) == SHIPPED_TAGS
    assert all(rules_for(one) in SHIPPED for one in SHIPPED_TAGS)
