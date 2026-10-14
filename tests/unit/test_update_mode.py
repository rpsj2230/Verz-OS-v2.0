"""How an install updates: `INSTALL_UPDATE_MODE`, its two words, and what each changes.

Found on the owner's staging install on 2026-10-14: its auto-deploy follows the newest image on
purpose, and the install check for "one published image at a named release" failed it on every
run. The product is wrong, not the install: whether an install follows every release is a
fact the install has to be able to say, and until it could, the check had two bad choices, a
failure on a server doing what its owner asked or a pass on a client's production pinned to
`latest` by accident. These tests hold the setting, its default, its screen and the two places
that read it, the Updates screen's words and the install checks (the latter in
`test_acceptance_checks_install_template.py`).

Task ids: M42.1.3, M42.1.4, M42.3.9
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.console.configuration import (
    EDITABLE_SETTINGS,
    LABELS,
    READ_BY,
    SECTION_OF,
    SECTION_TITLES,
    Section,
    setting_problem,
)
from brain.console.installation import install_facts
from brain.console.version_view import (
    ANSWERS,
    FOLLOWS_EVERY_RELEASE,
    Running,
    Standing,
    VersionError,
    panel,
    running_release,
)
from brain.deployment.update_mode import (
    AN_INSTALL_THAT_FOLLOWS_EVERY_RELEASE_IS_NEVER_BEHIND_BY_CHOICE,
    NOTHING_PINS_THIS_INSTALL_AND_THE_BUILT_COMMIT_SAYS_WHAT_RUNS,
    THIS_INSTALL_FOLLOWS_EVERY_RELEASE_BY_CHOICE,
    UPDATE_MODE_SETTING,
    UpdateMode,
    follows_every_release,
    update_mode,
    update_mode_problem,
)
from brain.install import BY_NAME
from brain.ops.install_from_empty import Revision

#: Far outside any plausible wall clock, because nothing here is about the present.
NOW = datetime(2999, 1, 1, tzinfo=UTC)

IMAGE = "registry.invalid/brain"
COMMIT = "a" * 40

CONTINUOUS = {UPDATE_MODE_SETTING: "continuous"}


def mode(written: str) -> UpdateMode:
    return update_mode({UPDATE_MODE_SETTING: written}, {})


# --- the setting and its default --------------------------------------------------------


def test_an_install_that_says_nothing_stays_on_a_release() -> None:
    """The declared default is `release`, which is what a client's production wants, and an
    install that never set anything reads as it. Asked against the declaration rather than a
    constant of the module under test.

    Delete this and the default can become `continuous`, and every client install would follow
    whatever was pushed last until somebody noticed."""
    assert BY_NAME[UPDATE_MODE_SETTING].default == "release"
    assert update_mode({}, {}) is UpdateMode.RELEASE
    assert follows_every_release({}, {}) is False


def test_the_two_words_are_read_and_continuous_is_the_only_one_that_follows() -> None:
    """The positive case: `continuous` is read, in any case and with stray spaces, and `release`
    is read as itself. Delete this and a function that always answers `release` passes every
    refusal below."""
    assert mode("release") is UpdateMode.RELEASE
    assert mode("continuous") is UpdateMode.CONTINUOUS
    assert mode("  Continuous ") is UpdateMode.CONTINUOUS
    assert follows_every_release(CONTINUOUS, {}) is True
    assert {one.value for one in UpdateMode} == {"release", "continuous"}


@pytest.mark.parametrize("written", ["", "latest", "follow", "continuously", "true", "always"])
def test_a_word_that_is_not_the_choice_reads_as_release(written: str) -> None:
    """A typo in the environment file must not become permission to run whatever was pushed last.
    Delete this and an unrecognised word is read as the loose answer, which is the direction that
    hides a client's production running `latest` by accident."""
    assert mode(written) is UpdateMode.RELEASE


def test_the_saved_value_outranks_the_environment_file() -> None:
    """A mode saved on Install, Settings wins over the environment file's line, as every
    installation value does through `value_of`. Delete this and the screen's change is silently
    overridden by whatever the template left behind."""
    assert update_mode(CONTINUOUS, {UPDATE_MODE_SETTING: "release"}) is UpdateMode.RELEASE
    assert update_mode({UPDATE_MODE_SETTING: "release"}, CONTINUOUS) is UpdateMode.CONTINUOUS


def test_a_value_other_than_the_two_words_is_refused_before_it_is_saved_in_a_plain_sentence() -> (
    None
):
    """The refusal names both words and what each is for, and the two words are admitted. Delete
    this and the screen can save a word nothing reads, which then reads as `release` with the
    person who typed it believing they had chosen something."""
    assert update_mode_problem("release") == ""
    assert update_mode_problem("continuous") == ""
    sentence = update_mode_problem("forever")
    assert "release" in sentence and "continuous" in sentence
    assert sentence.endswith(".")
    assert update_mode_problem("") != ""


# --- the screen that changes it ---------------------------------------------------------


def test_the_setting_is_changed_on_install_settings_with_its_own_section_and_label() -> None:
    """It is editable, drawn in a section of its own, labelled in words, and read by the module
    that decides it. Delete this and the owner has no screen on which to say how this install
    updates, which is the whole of what this setting is for."""
    assert UPDATE_MODE_SETTING in EDITABLE_SETTINGS
    assert SECTION_OF[UPDATE_MODE_SETTING] is Section.UPDATES
    assert SECTION_TITLES[Section.UPDATES]
    assert LABELS[UPDATE_MODE_SETTING]
    assert READ_BY[UPDATE_MODE_SETTING] == ("brain.deployment.update_mode",)


def test_the_screen_judges_the_value_by_the_modules_own_rule() -> None:
    """`setting_problem` accepts the two words and refuses anything else with that rule's own
    sentence, and an empty value gets the generic one. Delete this and the screen's check is not
    this setting's rule, so a word the module refuses can still be saved."""
    assert setting_problem(UPDATE_MODE_SETTING, "continuous") == ""
    assert setting_problem(UPDATE_MODE_SETTING, "release") == ""
    assert setting_problem(UPDATE_MODE_SETTING, "forever") == update_mode_problem("forever")
    assert setting_problem(UPDATE_MODE_SETTING, "  ").startswith("Type a value")


# --- what the Updates screen says -------------------------------------------------------


def test_an_install_on_latest_that_follows_every_release_is_told_it_is_a_choice() -> None:
    """On `latest` in continuous mode no release is named, the reason is the choice rather than a
    missing pin, and the pinned-image fact no longer says nobody decided anything. Delete this and
    a staging server's screen goes on telling it to pin a release it chose not to pin."""
    running = running_release(
        pinned_image=f"{IMAGE}:latest", built_commit=COMMIT, follows_every_release=True
    )

    assert running.tag == ""
    assert running.follows_every_release is True
    assert running.cannot_say == THIS_INSTALL_FOLLOWS_EVERY_RELEASE_BY_CHOICE
    pinned = next(one for one in running.facts if one.name == "pinned image")
    assert "follow every release" in pinned.because
    assert "nobody having decided" not in pinned.because
    assert running.commit == COMMIT


def test_an_install_on_latest_that_never_chose_it_is_still_told_it_is_unpinned() -> None:
    """The default is unchanged: `latest` with no choice is an install with no pin, in the
    words it always had. Delete this and the strict answer can be lost with the loose one
    looking fine, which is the failure the check exists to find."""
    running = running_release(pinned_image=f"{IMAGE}:latest", built_commit=COMMIT)

    assert running.tag == ""
    assert running.follows_every_release is False
    assert "pins no release" in running.cannot_say
    pinned = next(one for one in running.facts if one.name == "pinned image")
    assert "nobody having decided" in pinned.because


def test_continuous_mode_changes_nothing_for_an_install_pinned_to_a_tag_or_told_nothing() -> None:
    """A tag is read as a tag in either mode, and an install that was handed no image reference
    at all is not described as having chosen anything: the choice is about an image that names no
    release, and no image is a deployment that told this application nothing.

    Delete this and continuous mode can hide a missing `APP_IMAGE`, which is a stored compose file
    that predates the line."""
    pinned = running_release(pinned_image=f"{IMAGE}:v1.2.3", follows_every_release=True)
    assert pinned.tag == "v1.2.3"
    assert pinned.follows_every_release is False

    nothing = running_release(marker="v1.2.3", follows_every_release=True)
    assert nothing.tag == ""
    assert nothing.follows_every_release is False
    assert nothing.cannot_say != THIS_INSTALL_FOLLOWS_EVERY_RELEASE_BY_CHOICE


def test_a_running_release_cannot_both_be_named_and_be_the_choice_not_to_name_one() -> None:
    """The two together are refused when it is built, as a caveat beside a version is. Delete this
    and a renderer can be handed a version number and told the install names none."""
    running = running_release(pinned_image=f"{IMAGE}:v1.2.3")
    with pytest.raises(VersionError):
        Running(tag="v1.2.3", facts=running.facts, commit=COMMIT, follows_every_release=True)


def test_the_panel_for_an_install_that_follows_every_release_does_not_tell_it_to_pin_one() -> None:
    """The finding is still that no release is known, so the standing is the same one, and the
    sentences differ: the instruction for a missing pin is to run the update script with a tag,
    which on this install would undo the choice. Delete this and the Updates screen contradicts
    the setting beside it.

    The ordinary answer is asserted too, so an answer that always reads the choice cannot pass."""
    chosen = running_release(
        pinned_image=f"{IMAGE}:latest", built_commit=COMMIT, follows_every_release=True
    )
    shown = panel(chosen, None, now=NOW)

    assert shown.standing is Standing.UNKNOWN_RUNNING
    assert shown.answer == FOLLOWS_EVERY_RELEASE
    assert shown.answer.says == AN_INSTALL_THAT_FOLLOWS_EVERY_RELEASE_IS_NEVER_BEHIND_BY_CHOICE
    assert shown.answer.what_to_do == NOTHING_PINS_THIS_INSTALL_AND_THE_BUILT_COMMIT_SAYS_WHAT_RUNS
    assert shown.answer.what_to_do.startswith("Nothing to pin")
    assert shown.answer != ANSWERS[Standing.UNKNOWN_RUNNING]

    unchosen = running_release(pinned_image=f"{IMAGE}:latest", built_commit=COMMIT)
    assert panel(unchosen, None, now=NOW).answer == ANSWERS[Standing.UNKNOWN_RUNNING]


def test_there_is_still_one_answer_for_every_standing_and_no_tenth_one() -> None:
    """The choice is a different instruction for an existing standing, not a new standing, so the
    Updates screen keeps the nine ways it can be drawn that the install check holds it to. Delete
    this and a tenth way to be drawn wrongly can be added with no answer written for it."""
    assert set(ANSWERS) == set(Standing)
    assert len(Standing) == 9


def test_the_installation_screen_names_the_choice_where_it_would_name_a_missing_pin() -> None:
    """The Install screen's release fact reads the same answer as the Updates screen, through the
    same `running_release`, so the two cannot say different things about one install. Delete this
    and Install says nothing selects a release while Updates says that is the choice.

    The environment is handed in, as `install_facts` takes it, and nothing here reads the
    process's own."""
    ordinary = install_facts(
        profile="lite",
        manifest=None,
        revisions=(Revision(name="a", revision="0001", down_revision=None),),
        pinned_image=f"{IMAGE}:latest",
        env={},
    )
    chosen = install_facts(
        profile="lite",
        manifest=None,
        revisions=(Revision(name="a", revision="0001", down_revision=None),),
        pinned_image=f"{IMAGE}:latest",
        env=CONTINUOUS,
    )

    assert next(one for one in ordinary if one.name == "release").because != (
        THIS_INSTALL_FOLLOWS_EVERY_RELEASE_BY_CHOICE
    )
    assert (
        next(one for one in chosen if one.name == "release").because
        == THIS_INSTALL_FOLLOWS_EVERY_RELEASE_BY_CHOICE
    )
