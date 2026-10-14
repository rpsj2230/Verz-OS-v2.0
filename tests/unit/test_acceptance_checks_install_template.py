"""The client deployment template's install checks: passing at head, and failing with the template
broken the way it would plausibly break.

The checks that need no database are run directly with a stand-in harness that holds only what they
read; the Updates screen's check signs a reserved person in and runs against PostgreSQL at head,
and skips where `DATABASE_URL` is unset.

Task ids: M42.1.2, M42.1.3, M42.1.4, M42.2.3, M42.2.8, M42.3.1, M42.3.6
Task ids: M42.3.9, M42.5.1, M42.5.2, M42.5.15, M42.3.3, M42.1.1, M42.3.2, M42.3.8
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.deployment.installer import PLAN
from brain.ops.acceptance import (
    FAILED,
    PASSED,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from tests.fixtures.console_proof import run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_install_template"
STEPS = "the_installer_steps_say_when_done_and_what_to_do_on_failure"
SECRETS = "every_secret_the_install_holds_was_minted_here_and_none_repeats"
GUIDES = "the_install_guides_are_held_to_the_installer_and_the_checklist"
PIN = "the_install_runs_one_published_image_at_a_named_release"
UPDATE = "the_update_refuses_latest_and_the_rollback_reads_the_previous"
SCREEN = "the_updates_screen_names_the_version_and_whether_newer_exists"
HEAD = "the_database_is_at_the_head_the_migrate_command_brings_it_to"
VARIABLES = "the_variables_template_is_blank_and_the_repository_is_checked"
NOTES = "the_release_this_install_runs_says_what_changed_and_how_urgent"

IMAGE = "ghcr.io/rpsj2230/verz-brain-v2.0"


def body(name: str) -> Any:
    return next(one.run for one in registered((MODULE,)) if one.name == name)


def ran(name: str, *, app_image: str = "") -> None:
    asyncio.run(body(name)(SimpleNamespace(settings=SimpleNamespace(app_image=app_image))))


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        STEPS: ("M42.3.1", "M42.5.1", "M42.5.15"),
        SECRETS: ("M42.1.2", "M42.5.2"),
        GUIDES: ("M42.2.3", "M42.2.8"),
        PIN: ("M42.1.3", "M42.1.4"),
        UPDATE: ("M42.3.6",),
        SCREEN: ("M42.3.9",),
        HEAD: ("M42.3.3",),
        VARIABLES: ("M42.1.1", "M42.3.2"),
        NOTES: ("M42.3.8",),
    }
    assert checks_in(MODULE) == [
        STEPS,
        SECRETS,
        GUIDES,
        PIN,
        UPDATE,
        SCREEN,
        HEAD,
        VARIABLES,
        NOTES,
    ]


def test_the_installer_and_the_update_checks_pass_on_the_plan_this_release_carries() -> None:
    """The positive half: the plan at head satisfies every claim. Delete this and a refusal
    test below is satisfied by a check that refuses everything."""
    ran(STEPS)
    ran(UPDATE)


def test_the_variables_check_passes_at_head_and_fails_when_the_template_ships_a_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The template and the repository check at head pass; a template that ships a password
    fails. Delete this and M42.3.2 closes on a generator that stopped blanking credentials."""
    ran(VARIABLES)
    from brain.deployment import variables

    real = variables.template_for

    def shipping(install: str, *, also: Any = None) -> str:
        return real(install, also=also).replace(
            "POSTGRES_PASSWORD=", "POSTGRES_PASSWORD=hunter2hunter2"
        )

    monkeypatch.setattr(variables, "template_for", shipping)
    with pytest.raises(CheckFailedError, match="ships a value"):
        ran(VARIABLES)


def test_the_guides_check_passes_on_the_guides_this_release_carries() -> None:
    """The guides at head agree with the installer's plan and the registries. Delete this and
    the guides check is only ever shown refusing."""
    ran(GUIDES)


def test_a_secrets_check_passes_over_generated_values_and_refuses_a_repeated_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct long values pass; one value doing for two credentials fails. Delete this and a
    check that cannot see a shared secret passes on every install."""
    generated = {"BRAIN_SETUP_SECRET": "a" * 40, "APP_ROLE_PASSWORD": "b" * 40}
    monkeypatch.setattr("brain.settings.process_environment", lambda: generated)
    ran(SECRETS)
    generated["APP_ROLE_PASSWORD"] = generated["BRAIN_SETUP_SECRET"]
    with pytest.raises(CheckFailedError, match="shared"):
        ran(SECRETS)


def test_the_secrets_check_passes_a_token_of_the_length_the_vault_issues_and_still_refuses_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Found on a staging install: the vault's own token, about twenty-six characters, failed the
    check as short enough to be guessed, on every run, with nothing the install could do. The
    check reads what the application reads, so this also proves the token is among those names.
    A short password beside it and a vault token sharing its value with another setting each
    still fail, and a failure still names no value. (A worker's token is the same name inside the
    worker's container, so two vault tokens sharing a value is held on the function's own tests.)

    Delete this and the staging fault can return with the unit tests of the function green, since
    only this drives the check itself over the names the application reads."""
    vault = "s." + "a1B2c3D4" * 3
    held = {
        "BRAIN_SETUP_SECRET": "a" * 40,
        "APP_ROLE_PASSWORD": "b" * 40,
        "BRAIN_VAULT_TOKEN": vault,
    }
    monkeypatch.setattr("brain.settings.process_environment", lambda: held)
    ran(SECRETS)

    held["APP_ROLE_PASSWORD"] = vault
    with pytest.raises(CheckFailedError, match="shared"):
        ran(SECRETS)

    held["APP_ROLE_PASSWORD"] = "b" * 40
    ran(SECRETS)

    held["BRAIN_SETUP_SECRET"] = "zq7zq7"
    with pytest.raises(CheckFailedError) as raised:
        ran(SECRETS)
    assert vault not in str(raised.value)
    assert "zq7zq7" not in str(raised.value)


def test_a_step_that_writes_and_cannot_say_it_is_done_fails_the_steps_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step that repeats on a second run fails the check. The step class refuses to be built so,
    so the plan is handed one made past its constructor. Delete this and M42.3.1 closes on a
    check that never looks at the steps."""
    from brain.ops import acceptance_checks_install_template as module

    first, *rest = PLAN
    broken = dataclasses.replace(rest[1])
    object.__setattr__(broken, "already_done", "")
    assert broken.changes
    monkeypatch.setattr(module, "PLAN", (first, broken, *rest[2:]))
    with pytest.raises(CheckFailedError, match="already done"):
        ran(STEPS)


def test_an_update_script_that_admits_latest_fails_the_update_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first step of the update is run in a shell. Delete this and a refusal that never
    refuses closes M42.3.6."""
    from brain.deployment import release

    real = release.update_plan

    def admitting(plan: Any = PLAN) -> Any:
        first, *rest = real(plan)
        return (dataclasses.replace(first, run="true"), *rest)

    monkeypatch.setattr(release, "update_plan", admitting)
    with pytest.raises(CheckFailedError, match="admitted latest"):
        ran(UPDATE)


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        (f"{IMAGE}:v1.2.3", None),
        (f"{IMAGE}:latest", CheckFailedError),
        (IMAGE, CheckFailedError),
        ("ghcr.io/somebody/else:v1.2.3", CheckFailedError),
        (f"{IMAGE}:0123abc", CheckNotRunError),
        ("", CheckNotRunError),
    ],
)
def test_the_pin_check_names_what_each_image_is(
    image: str, expected: type[Exception] | None
) -> None:
    """A release tag passes, latest or no tag or another repository fails, a build tag or no
    reference is not run. Delete this and the pin check is only ever shown one of its answers."""
    if expected is None:
        ran(PIN, app_image=image)
    else:
        with pytest.raises(expected):
            ran(PIN, app_image=image)


@pytest.mark.parametrize("image", [f"{IMAGE}:latest", IMAGE, f"{IMAGE}:v1.2.3", ""])
def test_an_install_that_follows_every_release_is_recorded_as_not_run_whatever_it_runs(
    image: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found on a staging install: its auto-deploy follows the newest image on purpose, and the
    check failed it on every run. When the install says it follows every release, the check is
    not run, with the sentence saying why, and is never passed: even a pinned tag is not a pass,
    because the install is not being held to one.

    Delete this and the staging install is red again, or the check is quietly changed to pass
    where it is not run, which shows a tick beside a pin nobody confirmed."""
    from brain.ops.acceptance_checks_install_template import FOLLOWS_EVERY_RELEASE_BY_CHOICE

    monkeypatch.setenv("INSTALL_UPDATE_MODE", "continuous")
    with pytest.raises(CheckNotRunError) as raised:
        ran(PIN, app_image=image)
    assert str(raised.value) == FOLLOWS_EVERY_RELEASE_BY_CHOICE
    assert "follow every release" in str(raised.value)


@pytest.mark.parametrize("mode", ["release", "", "Continuously", "latest", "follow"])
def test_an_install_that_has_not_chosen_to_follow_every_release_is_still_held_to_a_tag(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default install, one set to release, and one whose environment file holds a word that
    is not the choice all keep the refusal: latest fails, and a release tag passes. A typo must
    not become permission to run whatever was pushed last.

    Delete this and the refusal can be switched off by anything, or by nothing, and the page goes
    green on an install running latest by accident, which is the fault the check exists for."""
    monkeypatch.setenv("INSTALL_UPDATE_MODE", mode)
    with pytest.raises(CheckFailedError, match="latest or to no tag"):
        ran(PIN, app_image=f"{IMAGE}:latest")
    ran(PIN, app_image=f"{IMAGE}:v1.2.3")


class _NoSessions:
    """A session factory that opens nothing, for a check that is told the switch is on."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


def _notes_run(app_image: str) -> None:
    harness = SimpleNamespace(
        settings=SimpleNamespace(
            app_image=app_image, release_check=True, release_feed_url="https://feed.invalid/x"
        ),
        sessions=_NoSessions,
    )
    asyncio.run(body(NOTES)(harness))


def test_the_release_notes_check_says_an_install_that_follows_every_release_has_no_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where the image names no release, an install set to follow every release is told that is
    the reason, and one that is not is told its image is a build, as before. Neither fetches
    anything. Delete this and a staging install's notes check says it should be re-pinned, which
    is the instruction to undo the choice it made.

    Both sentences are the check module's own literals, compared against the raised text."""
    from brain.ops import acceptance_checks_install_template as module

    with pytest.raises(CheckNotRunError) as release:
        _notes_run(f"{IMAGE}:latest")
    assert str(release.value) == module.PINNED_TO_A_BUILD

    monkeypatch.setenv("INSTALL_UPDATE_MODE", "continuous")
    with pytest.raises(CheckNotRunError) as continuous:
        _notes_run(f"{IMAGE}:latest")
    assert str(continuous.value) == module.FOLLOWING_EVERY_RELEASE_NAMES_NO_RELEASE_TO_READ_NOTES_OF


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_install_template") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_the_updates_screen_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The Updates screen as an administrator opens it, through the install's own gate. Delete
    this and M42.3.9 closes on a screen no check opened."""
    from tests.fixtures.console_proof import counts

    before = counts(install)
    results = run_module(install, MODULE)
    assert results[SCREEN] == (PASSED, "")
    assert results[HEAD] == (PASSED, "")
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_database_behind_the_head_fails_the_head_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database one revision behind would apply a migration if the command ran. Delete this and
    M42.3.3 closes on a check that never compares the two."""
    from alembic.script import ScriptDirectory

    monkeypatch.setattr(ScriptDirectory, "get_current_head", lambda self: "0000")
    outcome, reason = run_module(install, MODULE)[HEAD]
    assert outcome == FAILED, reason
    assert "head" in reason


def test_the_guides_are_found_where_the_application_serves_them() -> None:
    """The guides check reads the directory the application serves, so the two cannot disagree.
    Delete this and the check can read one folder while the page serves another."""
    from brain.docs_routes import DOCS
    from brain.ops.acceptance_checks_install_template import _guides

    assert _guides() == DOCS / "install"
    assert isinstance(DOCS, Path)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("body", "listed", "expected"),
    [
        (
            "## What changed\n- x\n## Does this change your database\nNo.\n## How urgent this is\n",
            True,
            "passed",
        ),
        ("## What changed\n- x\n", True, "failed"),
        ("", False, "not run"),
    ],
)
def test_the_notes_check_reads_the_running_releases_notes_from_the_list(
    install: str,
    issuer: None,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    listed: bool,
    expected: str,
) -> None:
    """A release whose notes carry the three headings passes, one that says only what changed
    fails, and one the list does not carry is not run. Delete this and M42.3.8 closes on notes
    nobody read, or fails on an install the list says nothing about."""
    import json

    from brain.console import version_view
    from brain.deployment import release_feed
    from brain.ops import features

    monkeypatch.setattr(version_view, "image_tag", lambda reference: "v1.2.3")
    monkeypatch.setattr(
        features, "switched_on_in", lambda states, one=(): {features.RELEASE_CHECK.name}
    )
    entry = {"tag_name": "v1.2.3" if listed else "v0.0.1", "body": body}
    monkeypatch.setattr(release_feed, "https_fetch", lambda url: json.dumps([entry]).encode())
    outcome, reason = run_module(install, MODULE)[NOTES]
    assert outcome == expected, reason
