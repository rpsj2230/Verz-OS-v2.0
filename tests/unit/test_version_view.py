"""The version panel held to the rule that "up to date" and "cannot tell" must not look alike.

Three things are being pinned here and they fail in three different ways.

**Which release is running.** An install holds a marker file, an image pin and a built commit,
and the first two can disagree from the day it was installed. Every test about `running_release`
asks the same question: does the panel name a release it cannot stand behind. It must not, and
the case that matters is the ordinary one, an install that has never run the update script and
therefore pins nothing at all.

**Whether anything newer exists.** Nothing in this repository asks anywhere outside the
install, so the common answer is that nobody has said, and that answer must be distinguishable
from being current. The reassuring answer is the only one with refusals on it, and three tests
try to build a panel claiming it without the things that make it true.

**The ordering.** `v1.9.0` sorts after `v1.10.0` as text, and every wrong answer a loose
comparison gives is wrong towards reassurance. One test is that comparison, written so it
records the string ordering it exists to refuse.

The instants below are in 2099 deliberately. Nothing here is about the present, and a fixture
carrying a date near the wall clock is a test that reports a defect on a schedule nobody chose;
`tests/unit/test_scope_and_capability.py` says the same thing about 2019 and 2999.

Task ids: M42.3.9
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.console.installation import Fact, Source
from brain.console.version_view import (
    ANSWERS,
    COMMIT_FACT,
    MARKER_FACT,
    PINNED_FACT,
    SETTLED,
    TELLING_GOES_OFF_AFTER_DAYS,
    THE_APPLICATION_SERVICE,
    WHAT_A_RELEASE_CHECK_WOULD_SEND,
    Answer,
    Panel,
    Running,
    Standing,
    Told,
    VersionError,
    facts_the_container_cannot_read,
    image_tag,
    panel,
    release_check_cost,
    running_release,
    standing_of,
)
from brain.console.workspace import intersections_in
from brain.deployment.installer import INSTALL_HOME
from brain.deployment.release import NOT_PLAIN_ENGLISH, compose_documents
from brain.ops.recovery import DRILL_INTERVAL_DAYS
from brain.ops.reliability import BASELINE_COMPONENTS

#: Far outside any wall clock, because nothing in this module is about the present.
NOW = datetime(2099, 6, 1, 12, 0, tzinfo=UTC)

#: A whole image reference, of the shape the update script writes into the environment file.
PINNED = "ghcr.io/example/brain:v1.4.0"

SOURCE = Path("src/brain/console/version_view.py")


def on(tag: str) -> Running:
    """An install whose marker and pin agree on one release, which is the settled case."""
    return running_release(
        marker=tag, pinned_image=f"ghcr.io/example/brain:{tag}", built_commit="724cf3f"
    )


def said(tag: str, *, days_ago: int = 0) -> Told:
    """Somebody having named `tag` as the newest release, `days_ago` before `NOW`."""
    return Told(tag=tag, at=NOW - timedelta(days=days_ago), by="the administrator")


def named(one: Running, name: str) -> Fact:
    """The one statement with this name, so a test asserts on the object and not on a string."""
    return next(fact for fact in one.facts if fact.name == name)


# --------------------------------------------------------------- which release is running
def test_an_install_that_pins_no_image_names_no_release_however_confident_its_marker_is():
    """**This is the ordinary install and it is the one a version screen gets wrong.** A fresh
    install writes the marker and writes nothing that selects an image, so every container
    falls back to the compose default, which ends in `latest`. A panel reporting the marker's
    tag as the running version would therefore be right about a file and wrong about the
    containers on every install that has never been updated, which is every install today.

    Delete this and the panel becomes the confident version number this whole module exists to
    refuse, and it becomes it silently: the value shown is a real tag read from a real file."""
    one = running_release(marker="v1.4.0", built_commit="724cf3f")

    assert one.tag == ""
    assert "pins no release" in one.cannot_say
    assert named(one, MARKER_FACT).value == "v1.4.0"
    assert named(one, PINNED_FACT).source is Source.UNKNOWN


def test_a_marker_and_a_pin_that_disagree_produce_no_version_and_name_them_both():
    """The two statements answer different questions, so one of them is not more right than
    the other and picking either is a screen that lies quietly. This is the state an update
    that failed between unpacking and pinning leaves behind, which is the moment somebody is
    most likely to be reading the panel.

    Delete this and the panel picks the marker, which is the record of what was downloaded,
    and reports it as the version somebody is running."""
    one = running_release(marker="v1.5.0", pinned_image=PINNED, built_commit="724cf3f")

    assert one.tag == ""
    assert "v1.5.0" in one.cannot_say
    assert "v1.4.0" in one.cannot_say


def test_a_marker_and_a_pin_that_agree_are_the_release_this_install_is_on():
    """The positive case, without which every test above is satisfied by a function that
    refuses to name any release at all. Two statements that agree are the strongest answer
    this panel can give and it has to give it.

    Delete this and a panel that never names a version passes the whole file."""
    one = running_release(marker="v1.4.0", pinned_image=PINNED, built_commit="724cf3f")

    assert one.tag == "v1.4.0"
    assert one.cannot_say == ""


def test_a_pin_with_no_marker_is_the_release_the_containers_were_told_to_run():
    """An install whose marker was lost still has a pin, and the pin is what selects every
    container, so it names the release on its own. This is the second positive case and it is
    the direction the module trusts: the pin describes what is running, the marker describes
    what was downloaded.

    Delete this and a panel that only ever answers when both statements are present passes,
    and an install missing one file reports nothing at all."""
    one = running_release(pinned_image=PINNED, built_commit="724cf3f")

    assert one.tag == "v1.4.0"


def test_an_install_that_reports_neither_statement_says_so_rather_than_reporting_no_pin():
    """Two different silences, and collapsing them sends somebody to fix the wrong thing.
    Nothing having been handed to the screen is a wiring problem; an install with a marker and
    no pin is a real install that is genuinely unpinned and is fixed by running the update
    script once.

    Delete this and both arrive as the unpinned sentence, and an operator goes to run an
    update against an install whose panel simply was not given anything."""
    one = running_release(built_commit="724cf3f")

    assert one.tag == ""
    assert "pins no release" not in one.cannot_say
    assert "no statement about a version has been read" in one.cannot_say


def test_the_commit_is_measured_and_is_never_the_release_the_panel_names():
    """The commit is the only statement this process can measure and it is the wrong answer:
    a client cannot look one up in a list of releases, ask for its notes, or hand it to the
    update script. An install that reports a commit and nothing else still names no release.

    Delete this and the obvious repair to an empty version field is to fall back to the
    commit, which is a field that answers a question nobody asked in the reassuring
    direction."""
    one = running_release(built_commit="724cf3f")

    assert named(one, COMMIT_FACT).source is Source.MEASURED
    assert named(one, COMMIT_FACT).value == "724cf3f"
    assert one.tag == ""


def test_every_reading_carries_a_statement_for_all_three_places_that_can_say():
    """An absent statement is a row the reader has to see rather than one to leave out: a
    panel with two rows and a panel with three rows and one of them unknown are read very
    differently, and only the second says what is missing.

    Delete this and a reading assembled from one input renders as a complete panel."""
    one = running_release()

    assert tuple(fact.name for fact in one.facts) == (MARKER_FACT, PINNED_FACT, COMMIT_FACT)
    assert all(fact.source is Source.UNKNOWN for fact in one.facts)
    assert all(fact.because.strip() for fact in one.facts)


def test_a_reading_cannot_carry_both_a_version_and_a_reason_not_to_name_one():
    """A caveat beside a version number is read as a version number. The constructor refuses
    the pair rather than leaving a renderer to decide which of the two wins, because the
    renderer that decides wrongly is the one nobody reviews.

    Delete this and a future edit can hand back both, and the panel shows the tag."""
    with pytest.raises(VersionError, match="caveat beside a version number"):
        Running(tag="v1.4.0", facts=running_release().facts, cannot_say="and also this")


def test_a_reading_assembled_from_no_statements_at_all_is_refused():
    """A reading with an empty statement list renders as a panel with a version and no rows
    under it, which is the confident answer with its evidence removed. `running_release`
    always supplies three, so this guard is only reachable by a caller assembling one, and a
    caller assembling one is exactly who has dropped the evidence.

    Delete this and the check is the sort that gets removed as unreachable, which is this
    repository's most common defect and the reason the guard audit exists."""
    with pytest.raises(VersionError, match="read from nothing"):
        Running(tag="v1.4.0", facts=())


def test_a_reading_that_names_no_release_has_to_say_why():
    """Unknown on its own sends the reader looking for a setting that would not have helped,
    which is the rule `brain.console.installation.Fact` applies to an unknown value one screen
    over.

    Delete this and an empty version field can ship with nothing beside it."""
    with pytest.raises(VersionError, match="nothing says why"):
        Running(tag="", facts=running_release().facts)


def test_a_registry_port_is_not_read_as_the_release_this_install_is_running():
    """`rsplit(":", 1)` on a whole image reference returns the port of the registry when the
    registry has one, so the panel would report `5000` as the release. Nobody here deploys
    against a registry on a port, which is exactly why it would ship.

    Delete this and the tag reader is simplified to the one-line version on the first tidy."""
    assert image_tag("localhost:5000/example/brain:v1.4.0") == "v1.4.0"
    assert image_tag("localhost:5000/example/brain") == ""


# ------------------------------------------------------- whether anything newer exists
def test_nobody_having_said_anything_is_not_the_same_answer_as_being_up_to_date():
    """The common state of every install of this product is that nothing has ever told it
    which release is newest, because nothing here asks. That state must be its own answer and
    it must not be one a tick can be drawn beside.

    Delete this and the absence of a telling collapses into the reassuring answer, which is
    the exact field somebody checks before deciding not to worry."""
    where = standing_of(on("v1.4.0"), None, now=NOW)

    assert where is Standing.NOBODY_HAS_SAID
    assert where not in SETTLED


def test_a_telling_stops_being_reassuring_the_moment_the_window_closes():
    """The boundary is the only interesting instant and it cannot be reached through a
    function that reads the process clock, which is why the window and the moment are both
    parameters. Exactly at the window the answer still stands; a second past it does not.

    Delete this and an off-by-one in the comparison goes unnoticed in the direction that
    keeps saying "current" for ever."""
    running = on("v1.4.0")
    window = timedelta(days=TELLING_GOES_OFF_AFTER_DAYS)

    at_the_edge = Told(tag="v1.4.0", at=NOW - window, by="the administrator")
    past_it = Told(tag="v1.4.0", at=NOW - window - timedelta(seconds=1), by="the administrator")

    assert standing_of(running, at_the_edge, now=NOW) is Standing.CURRENT
    assert standing_of(running, past_it, now=NOW) is Standing.STALE
    assert Standing.STALE not in SETTLED


def test_a_release_published_long_ago_is_still_one_this_install_is_behind():
    """Staleness only takes the value out of the reassuring answer. A newer release named a
    year ago is still a newer release, and folding age into that verdict would turn the one
    answer that asks somebody to act into one that asks them to look again.

    Delete this and the obvious symmetry ("old answers are unreliable") gets applied to every
    verdict, and an install nine months behind reports that nobody has looked recently."""
    where = standing_of(on("v1.4.0"), said("v1.5.0", days_ago=400), now=NOW)

    assert where is Standing.BEHIND


def test_a_release_newer_than_the_one_recorded_is_not_reported_as_behind():
    """Somebody updates and does not update the recorded answer, which is the ordinary case
    rather than the odd one. Folded into "behind", the panel would send them to install a
    release older than the one they are running.

    Delete this and the comparison is simplified to "different means behind", which is wrong
    in a direction that costs somebody a rollback."""
    where = standing_of(on("v1.6.0"), said("v1.5.0"), now=NOW)

    assert where is Standing.AHEAD
    assert where not in SETTLED


def test_ten_is_later_than_nine_rather_than_earlier_as_text_would_have_it():
    """**This is the comparison the module exists to get right.** As text, `v1.9.0` sorts
    after `v1.10.0`, so a string comparison reports an install nine releases behind as being
    ahead of the newest one. The assertion on the string ordering is here so the next reader
    can see what is being refused rather than take it on trust.

    Delete this and the ordering is replaced by the obvious one-liner, and the failure is
    silent and reassuring."""
    assert "v1.9.0" > "v1.10.0"

    assert standing_of(on("v1.9.0"), said("v1.10.0"), now=NOW) is Standing.BEHIND
    assert standing_of(on("v1.10.0"), said("v1.9.0"), now=NOW) is Standing.AHEAD


def test_a_shorter_tag_is_ordered_against_a_longer_one_the_way_a_person_reads_them():
    """`v1.4` and `v1.4.1` are one release apart and a comparison of unequal tuples would
    order them by length or refuse them. Padding is what makes the ordinary release series
    comparable at all.

    Delete this and a project that drops the patch number from its first tag has an
    uncomparable pair on day one."""
    assert standing_of(on("v1.4"), said("v1.4.1"), now=NOW) is Standing.BEHIND
    assert standing_of(on("v2"), said("v1.9.9"), now=NOW) is Standing.AHEAD


def test_two_tags_that_cannot_be_ordered_are_reported_as_differing_rather_than_equal():
    """Anything outside the one declared shape is not ordered at all, and the answer says so.
    The two spellings of one number are the interesting half: they pad to the same tuple and
    are still two tags, which a registry holds as two things, so calling them one release is a
    guess in the reassuring direction.

    Delete this and an unparseable pair falls through to whatever the last branch returns,
    which is the branch a reader assumes is the safe one."""
    assert standing_of(on("v1.4.0"), said("2099.06-hotfix"), now=NOW) is Standing.DIFFERS
    assert standing_of(on("v1.4"), said("v1.4.0"), now=NOW) is Standing.DIFFERS
    assert Standing.DIFFERS not in SETTLED


def test_an_unknown_running_release_is_answered_before_anything_about_a_newer_one():
    """A comparison against an install nobody identified is a comparison against nothing, and
    it would come out as "behind" or "differs" and read as a fact about this server. The order
    of the questions is the argument.

    Delete this and an unpinned install with a recorded newest release reports a verdict about
    a version it never established."""
    unpinned = running_release(marker="v1.4.0", built_commit="724cf3f")

    assert standing_of(unpinned, said("v1.5.0"), now=NOW) is Standing.UNKNOWN_RUNNING


def test_a_telling_from_after_the_moment_being_asked_about_is_refused():
    """Two clocks that disagree would make an answer's age read as fresher than it is, and
    freshness is the whole of what separates the reassuring answer from the stale one. A
    negative age would also be less than any window, so it would pass every check silently.

    Delete this and a server whose clock is behind the recorder's reports "current" for ever."""
    with pytest.raises(VersionError, match="clocks disagree"):
        standing_of(on("v1.4.0"), said("v1.4.0", days_ago=-1), now=NOW)


def test_a_window_that_cannot_close_is_refused_rather_than_making_every_answer_reassuring():
    """A negative window is one no answer can ever be older than, so every telling stays
    current for ever and the panel becomes the tick with nothing behind it by arithmetic
    rather than by omission. It is the only value of this parameter that is silently
    catastrophic, which is why it is the one refused.

    Delete this and a caller passing a window computed by subtraction gets a permanently
    reassuring panel and no error anywhere."""
    with pytest.raises(VersionError, match="cannot go off after"):
        standing_of(on("v1.4.0"), said("v1.4.0"), now=NOW, goes_off_after_days=-1)


def test_a_naive_moment_is_refused_rather_than_compared_at_this_machines_offset():
    """The same rule `brain.ops.recovery.drill_due` keeps. A naive instant compared against an
    aware one is a silent offset, and the offset moves the answer across the window.

    Delete this and a caller passing a naive clock gets an answer that is wrong by hours and
    looks exactly like one that is right."""
    with pytest.raises(VersionError, match="naive now"):
        standing_of(on("v1.4.0"), said("v1.4.0"), now=NOW.replace(tzinfo=None))


# ------------------------------------------------------------------ the reassuring answer
def test_the_only_reassuring_answer_is_the_one_with_every_condition_behind_it():
    """`SETTLED` is asserted as a property of what `standing_of` produces rather than as a
    list written here: a member is in it only when the install named a release, somebody said
    what the newest one is, and they said it inside the window. Every other way of arriving is
    checked to land outside it.

    Delete this and a later member added to the enum can be drawn with a tick beside it
    because nothing says which of them may be."""
    running = on("v1.4.0")
    settled = {
        standing_of(running, said("v1.4.0"), now=NOW),
    }
    unsettled = {
        standing_of(running, None, now=NOW),
        standing_of(running, said("v1.5.0"), now=NOW),
        standing_of(running, said("v1.3.0"), now=NOW),
        standing_of(running, said("hotfix"), now=NOW),
        standing_of(running, said("v1.4.0", days_ago=TELLING_GOES_OFF_AFTER_DAYS + 1), now=NOW),
        standing_of(running_release(marker="v1.4.0"), said("v1.5.0"), now=NOW),
    }

    assert settled == set(SETTLED)
    assert unsettled.isdisjoint(SETTLED)
    assert settled | unsettled == set(Standing)


def test_a_panel_cannot_claim_the_reassuring_answer_without_a_running_release():
    """The refusal is on the panel as well as in the function that computes the verdict,
    because a panel is a value anybody can construct and the reassuring one is the value worth
    forging by accident.

    Delete this and a caller assembling a panel by hand can put a tick on an install whose
    version nothing established."""
    with pytest.raises(VersionError, match="which release is running"):
        Panel(
            running=running_release(built_commit="724cf3f"),
            told=said("v1.4.0"),
            standing=Standing.CURRENT,
            told_days_ago=0,
        )


def test_a_panel_cannot_claim_the_reassuring_answer_with_nobody_having_said_anything():
    """This is the tick with nothing behind it, in its purest form: an install that knows what
    it is running, has never been told what is newest, and is drawn as up to date.

    Delete this and the one field somebody checks before deciding not to worry can be filled
    from an install that has never compared itself against anything."""
    with pytest.raises(VersionError, match="nobody has said"):
        Panel(running=on("v1.4.0"), told=None, standing=Standing.CURRENT)


def test_a_panel_cannot_claim_the_reassuring_answer_against_an_answer_that_has_gone_off():
    """A release published since the recorded answer would look identical to this, which is
    the whole reason the window exists.

    Delete this and a panel assembled with a stale telling and a hand-written verdict shows a
    tick, and the age beside it is the only thing saying otherwise."""
    with pytest.raises(VersionError, match="days ago"):
        Panel(
            running=on("v1.4.0"),
            told=said("v1.4.0", days_ago=TELLING_GOES_OFF_AFTER_DAYS + 1),
            standing=Standing.CURRENT,
            told_days_ago=TELLING_GOES_OFF_AFTER_DAYS + 1,
        )


def test_the_panel_a_current_install_gets_is_the_reassuring_one():
    """The positive case for the three refusals above, without which they are satisfied by a
    panel that refuses every reassurance. An install on the newest recorded release, recorded
    today, is entitled to the settled answer.

    Delete this and a `Panel` that raises on every construction passes this file."""
    built = panel(on("v1.4.0"), said("v1.4.0"), now=NOW)

    assert built.standing in SETTLED
    assert built.told_days_ago == 0
    assert built.answer is ANSWERS[Standing.CURRENT]


def test_the_age_of_an_answer_is_rounded_down_rather_than_up():
    """The rounding has a direction and it is the opposite of everything else here. An answer
    recorded twenty-three hours before the window closes has not gone off, and rounding up
    would refuse to reassure somebody who has just looked, which is the failure that teaches
    people to ignore the panel.

    Delete this and the arithmetic is replaced by a ceiling on the first tidy, and the window
    quietly becomes a day shorter than the constant says."""
    almost = Told(tag="v1.4.0", at=NOW - timedelta(hours=23), by="the administrator")

    assert panel(on("v1.4.0"), almost, now=NOW).told_days_ago == 0


# --------------------------------------------------------------------- what a client reads
def test_every_standing_has_both_of_the_sentences_a_client_reads():
    """A member added to the enum without an answer would raise a `KeyError` at the moment
    somebody opened the screen, on an install in whichever state nobody thought about.

    Delete this and the eighth standing ships with no words at all."""
    assert set(ANSWERS) == set(Standing)
    assert all(one.says.strip() and one.what_to_do.strip() for one in ANSWERS.values())


def test_a_state_with_no_instruction_beside_it_is_refused():
    """The state and the instruction are two different things, and a state on its own is a
    word three people read three ways: "stale" tells nobody whether to act today. The same
    pair `brain.deployment.release.Level` keeps apart for the same reason.

    Delete this and a member added later can ship with the state written and the instruction
    left blank, and the blank is invisible on a screen."""
    with pytest.raises(VersionError, match="no what_to_do"):
        Answer(says="something happened", what_to_do="  ")
    with pytest.raises(VersionError, match="no says"):
        Answer(says="", what_to_do="do this")


def test_no_sentence_a_client_reads_names_something_only_this_repository_has():
    """Held against `brain.deployment.release.NOT_PLAIN_ENGLISH` rather than a second rule of
    this module's own, because it is the same requirement in the same words: a client's IT
    team has no source tree, no module names and no task ids, and a sentence naming one reads
    as coverage while being unusable.

    Delete this and the next edit to these sentences explains a state by naming the function
    that produces it."""
    for one in ANSWERS.values():
        for sentence in (one.says, one.what_to_do):
            assert NOT_PLAIN_ENGLISH.search(sentence) is None, sentence


def test_a_recorded_answer_says_who_gave_it_and_when():
    """An answer about whether a client is patched is worth what its source is worth, and the
    two plausible sources are an administrator who looked this morning and a value typed once
    during setup. Both refusals are here because a renderer showing a tag without a source
    invites the second to be read as the first.

    Delete this and a telling can be recorded with nobody behind it, and the panel's whole
    provenance argument disappears without any test failing."""
    with pytest.raises(VersionError, match="nobody named"):
        Told(tag="v1.5.0", at=NOW, by="   ")
    with pytest.raises(VersionError, match="naive instant"):
        Told(tag="v1.5.0", at=NOW.replace(tzinfo=None), by="the administrator")
    with pytest.raises(VersionError, match="names no release"):
        Told(tag="  ", at=NOW, by="the administrator")


def test_the_tag_that_is_not_a_release_cannot_be_recorded_as_the_newest_one():
    """`latest` is what the update script refuses in both directions, and recording it here
    would give this install a target it can never be on: the comparison would report
    "differs" for ever while the recorded answer looked like a real one.

    Delete this and an administrator copying the compose default into this field produces a
    panel that is permanently and inexplicably unsettled."""
    with pytest.raises(VersionError, match="is not a release"):
        Told(tag="latest", at=NOW, by="the administrator")


def test_the_window_an_answer_goes_off_after_is_the_one_a_drill_is_re_proven_on():
    """**A constant asserted against itself is green for every value it could hold**, so this
    compares it against the module it is taken from. Both figures answer one question, which
    is how long a system may go on repeating a reassurance nobody has re-proven, and the drill
    interval is itself bounded from above by the backup retention window rather than picked.

    Delete this and the window can be raised to ninety days with nothing failing, and the
    reassuring answer outlives every release that could have been published inside it."""
    assert TELLING_GOES_OFF_AFTER_DAYS == DRILL_INTERVAL_DAYS
    assert TELLING_GOES_OFF_AFTER_DAYS > 0


# ------------------------------------------------------------------------ the diagnostics
def test_neither_host_statement_can_be_read_from_inside_the_application_container():
    """**This is the finding rather than a passing check.** The marker and the image pin are
    the two statements the panel most needs, and today no compose file mounts anything from
    the install directory into the application service and the image variable is in no
    environment entry of it. So the panel is built and its inputs have no route into the
    process that would draw it, which is worth a red line on a screen rather than a sentence
    in a commit message.

    Delete this and the day somebody wires one of the two, nothing records that the other is
    still missing, and a half-wired panel reads as a working one."""
    found = facts_the_container_cannot_read(compose_documents())

    assert len(found) == 2
    assert any(INSTALL_HOME in one and "unpacked" in one for one in found)
    assert any("APP_IMAGE" in one for one in found)


def test_mounting_the_install_directory_into_the_application_answers_the_first_finding():
    """The positive case, and without it the check above is satisfied by a function that
    reports both findings unconditionally, which is exactly what a hand-written list would
    do. The check is read out of the compose documents, so wiring it changes the answer.

    Delete this and the diagnostic can become a constant tuple and nothing notices."""
    wired = {
        "docker-compose.yml": {
            "services": {
                THE_APPLICATION_SERVICE: {"volumes": [f"{INSTALL_HOME}/RELEASE:/app/RELEASE:ro"]}
            }
        }
    }
    found = facts_the_container_cannot_read(wired)

    assert not any("unpacked" in one for one in found)
    assert any("APP_IMAGE" in one for one in found)


def test_the_image_variable_in_the_application_environment_answers_the_second_finding():
    """The other positive case, and it covers both spellings of a compose environment block,
    because the mapping form and the `KEY=value` list form are both legal and a reader of one
    of them reports a wiring that exists as missing.

    Delete this and the environment reader can lose the list form, which is the form the
    generated files happen not to use today."""
    as_mapping = {
        "a.yml": {"services": {THE_APPLICATION_SERVICE: {"environment": {"APP_IMAGE": "x"}}}}
    }
    as_list = {"b.yml": {"services": {THE_APPLICATION_SERVICE: {"environment": ["APP_IMAGE=x"]}}}}

    assert not any("APP_IMAGE" in one for one in facts_the_container_cannot_read(as_mapping))
    assert not any("APP_IMAGE" in one for one in facts_the_container_cannot_read(as_list))


def test_the_application_service_is_one_this_deployment_actually_declares():
    """The findings above are per service, so a renamed service would turn the check into one
    that reports the same two things for ever while the wiring it asks for sat in front of it.
    Asserted against the baseline component register rather than against a second copy of the
    name.

    Delete this and the check survives a rename by continuing to be right about a service that
    no longer exists."""
    assert THE_APPLICATION_SERVICE in BASELINE_COMPONENTS
    assert THE_APPLICATION_SERVICE in compose_documents()["docker-compose.yml"]["services"]


def test_the_cost_of_asking_a_vendor_is_recorded_as_a_check_rather_than_a_sentence():
    """The decision not to phone home is the kind that gets re-litigated by whoever next finds
    the panel unhelpful, and a sentence in a commit message is not where that argument
    survives. One finding per item, so the day somebody designs a check the list is what they
    have to answer rather than a paragraph they can skim.

    Delete this and the reason there is no automatic check becomes folklore."""
    found = release_check_cost()

    assert len(found) == len(WHAT_A_RELEASE_CHECK_WOULD_SEND) == 5
    assert all(
        one.startswith("an install that asks whether a newer release exists") for one in found
    )


# ------------------------------------------------------------------- module properties
def test_nothing_in_this_module_reaches_the_network_or_reads_a_clock():
    """**This is the phone-home decision as a check on the module itself.** Every claim in the
    docstring about what does not leave a client's network is worth exactly as much as this
    test: an import of an HTTP client, a socket or a subprocess here would be the check being
    built by whoever found the panel unhelpful, in the module that argues against it. `now` is
    a parameter for the same reason, so a call to the process clock is refused too.

    Delete this and the module's central argument becomes prose, and the first person to add
    "just a quick fetch" passes every other test in this file."""
    reaching = {"httpx", "urllib", "socket", "subprocess", "requests", "asyncio"}
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported: list[str] = []
    clocks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(one.name for one in node.names)
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
        called = node.func if isinstance(node, ast.Call) else None
        if isinstance(called, ast.Attribute) and called.attr in {"now", "utcnow", "today"}:
            clocks.append(called.attr)

    assert [one for one in imported if one.split(".")[0] in reaching] == []
    assert clocks == []


def test_nothing_in_this_module_intersects_two_entitlement_sets():
    """The same rule `tests/unit/test_installation.py` keeps for the screen next door. This
    panel is about the deployment rather than about anybody's data, so it filters nothing, and
    a copy of the platform's central rule landing here would be the one nobody reviews because
    an install screen looks like plumbing.

    Delete this and a fourth implementation of the reach rule can arrive on a screen whose
    rows are not about people at all."""
    assert intersections_in(SOURCE.read_text(encoding="utf-8")) == ()
