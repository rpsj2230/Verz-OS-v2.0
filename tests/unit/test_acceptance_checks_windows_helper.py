"""The install checks for the Windows install helper, each passing on
PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M42.6.6
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_windows_helper import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_windows_helper"
COMMAND = "the_windows_helper_runs_the_documented_command_and_is_guided"
FILES = "the_shipped_helper_asks_five_questions_and_starts_only_itself"


def test_the_module_names_the_leaf_on_both_checks_inside_its_range() -> None:
    """Both checks name the leaf and sit where assigned. Delete this and a check can drop the leaf
    it was written for, or the module can slip out of its place on the Install page."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (COMMAND, ("M42.6.6",)),
        (FILES, ("M42.6.6",)),
    ]
    assert checks_in(MODULE) == [COMMAND, FILES]
    assert CHECK_ORDER == 1815


@pytest.fixture(autouse=True)
def issuer_of_this_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install values a console sign-in needs, set as the whole-suite run sets them."""
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_windows_helper") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url, **INSTALL})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_both_checks_pass_from_a_clone_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it, from a clone where the helper's files are present.** Both
    pass and nothing is written. Delete this and a check that can never pass reaches the owner's
    server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


# ---------------------------------------------------------------------- the first check broken
@pytest.mark.needs_db
def test_a_helper_that_builds_another_command_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run line changed in the helper and not in the guide. Delete this and M42.6.6 closes on
    a helper that is a second install path nobody reading the guide would recognise."""
    from brain.deployment import windows_helper

    monkeypatch.setattr(windows_helper, "RUN_LINE", windows_helper.RUN_LINE + " --quick")
    assert "install guide's" in _failed(install, COMMAND)


@pytest.mark.needs_db
def test_a_command_with_a_flag_the_installer_dropped_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installer no longer declaring a flag the helper passes. Delete this and M42.6.6 closes
    on a helper whose command the installer refuses as an unknown option."""
    from brain.deployment import install_script

    kept = tuple(one for one in install_script.FLAGS if one[0] != "--console-address")
    monkeypatch.setattr(install_script, "FLAGS", kept)
    assert "flag" in _failed(install, COMMAND)


@pytest.mark.needs_db
def test_a_file_the_guide_does_not_name_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher renamed and the guide not. Delete this and M42.6.6 closes on a guide that tells
    a person to double-click a file the release no longer carries."""
    from brain.deployment import windows_helper

    monkeypatch.setattr(
        windows_helper, "HELPER_LAUNCHER_PATH", "ops/install/windows/install-elsewhere.cmd"
    )
    assert "launcher" in _failed(install, COMMAND)


@pytest.mark.needs_db
def test_a_size_the_guide_does_not_name_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A size added to the installer and not the guide. Delete this and M42.6.6 closes on a guide
    that leaves a person choosing between sizes it never described."""
    from brain.ops import wiring

    monkeypatch.setattr(wiring, "PROFILES", (*wiring.PROFILES, "enormous"))
    assert "size" in _failed(install, COMMAND)


# --------------------------------------------------------------------- the second check broken
def _shipped_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, script: str = "", launcher: str = ""
) -> None:
    """The helper's two files copied out of the clone, edited, and read from there by the check."""
    from brain.deployment.release import REPO
    from brain.deployment.windows_helper import HELPER_LAUNCHER_PATH, HELPER_SCRIPT_PATH
    from brain.ops import acceptance_checks_windows_helper as module

    for relative, edit in ((HELPER_SCRIPT_PATH, script), (HELPER_LAUNCHER_PATH, launcher)):
        text = (REPO / relative).read_text(encoding="ascii")
        old, _, new = edit.partition("=>")
        (tmp_path / Path(relative).name).write_bytes(
            (text.replace(old, new) if old else text).encode()
        )
    monkeypatch.setattr(module, "_repository_file", lambda relative: tmp_path / Path(relative).name)


@pytest.mark.needs_db
def test_the_copy_the_edits_start_from_passes_the_files_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The unedited copy. Delete this and every refusal below is satisfied by a copy that was
    broken before it was edited, which is a guard tested only by its refusals."""
    _shipped_copy(tmp_path, monkeypatch)
    assert run_module(install, FILES)[FILES] == (PASSED, "")


@pytest.mark.needs_db
def test_a_script_that_asks_another_question_fails_the_files_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The release page question renamed. Delete this and M42.6.6 closes on a helper that no
    longer asks what its guide says it asks."""
    _shipped_copy(tmp_path, monkeypatch, script="'   Release page'=>'   Something else'")
    assert "five questions" in _failed(install, FILES)


@pytest.mark.needs_db
def test_a_launcher_that_runs_a_second_command_fails_the_files_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second line in the launcher. Delete this and M42.6.6 closes on a file a person
    double-clicks that does more than start the script beside it."""
    _shipped_copy(tmp_path, monkeypatch, launcher="@echo off=>@echo off\necho hello")
    assert "launcher" in _failed(install, FILES)


@pytest.mark.needs_db
def test_a_helper_with_a_character_a_console_mangles_fails_the_files_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A typographic quote in the script. Delete this and M42.6.6 closes on a script that prints
    nonsense on the screen of the person it was written for."""
    _shipped_copy(tmp_path, monkeypatch, script="Address=>Address" + chr(0x2019))
    assert "mangle" in _failed(install, FILES)


@pytest.mark.needs_db
def test_a_worker_without_the_files_is_told_so_and_not_passed(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The files absent from the image. Delete this and an image without them reports the helper
    as proved, which is the one thing it cannot know."""
    from brain.ops import acceptance_checks_windows_helper as module

    monkeypatch.setattr(module, "_repository_file", lambda relative: tmp_path / "missing")
    [(outcome, reason)] = run_module(install, FILES).values()
    assert outcome == "not run"
    assert reason == module.NO_HELPER_FILES_HERE


@pytest.mark.needs_db
def test_a_command_naming_the_release_by_another_variable_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installer reading its release from a different variable. Delete this and M42.6.6 closes
    on a helper that hands the installer a release address it never looks at."""
    from brain.deployment import install_script

    monkeypatch.setattr(install_script, "RELEASE_URL_VARIABLE", "SOME_OTHER_VARIABLE")
    assert "variable" in _failed(install, COMMAND)


@pytest.mark.needs_db
def test_a_file_the_archive_does_not_carry_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper dropped from the release's include list. Delete this and M42.6.6 closes on a
    helper that is in the repository and on no release page."""
    from brain.deployment import release

    monkeypatch.setattr(release, "included_by", lambda path: "")
    assert "archive" in _failed(install, COMMAND)


@pytest.mark.needs_db
def test_a_script_that_stops_saying_five_fails_the_files_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The script's own promise changed. Delete this and M42.6.6 closes on a helper that tells a
    person to expect a different number of questions than it asks."""
    _shipped_copy(tmp_path, monkeypatch, script="five questions=>seven questions")
    assert "tell the person" in _failed(install, FILES)


@pytest.mark.needs_db
def test_a_script_offering_another_set_of_sizes_fails_the_files_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A size dropped from the helper's list. Delete this and M42.6.6 closes on a helper that
    cannot choose a size the installer offers."""
    _shipped_copy(tmp_path, monkeypatch, script="'lite', 'standard', 'full'=>'lite', 'full'")
    assert "sizes" in _failed(install, FILES)


@pytest.mark.needs_db
def test_an_install_guide_without_the_command_fails_the_command_check(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The one command's heading gone from the guide. Delete this and M42.6.6 closes on a helper
    held to a command the guide no longer shows."""
    from brain import docs_routes

    folder = tmp_path / "install"
    folder.mkdir()
    for source in (docs_routes.DOCS / "install").glob("*.md"):
        text = source.read_text(encoding="utf-8")
        (folder / source.name).write_text(
            text.replace("## Run this one command", "## Run these commands"), encoding="utf-8"
        )
    monkeypatch.setattr(docs_routes, "DOCS", tmp_path)
    assert "no longer has" in _failed(install, COMMAND)


@pytest.mark.needs_db
def test_an_image_without_the_guides_is_told_so_and_not_passed(
    install: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The guides absent from the image. Delete this and an image without them reports the helper's
    command as held to a guide nobody could read."""
    from brain import docs_routes
    from brain.ops import acceptance_checks_windows_helper as module

    monkeypatch.setattr(docs_routes, "DOCS", tmp_path)
    [(outcome, reason)] = run_module(install, COMMAND).values()
    assert outcome == "not run"
    assert reason == module.NO_GUIDES_HERE
