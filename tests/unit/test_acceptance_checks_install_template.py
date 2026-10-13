"""The client deployment template's install checks: passing at head, and failing with the template
broken the way it would plausibly break.

The checks that need no database are run directly with a stand-in harness that holds only what they
read; the Updates screen's check signs a reserved person in and runs against PostgreSQL at head,
and skips where `DATABASE_URL` is unset.

Task ids: M42.1.2, M42.1.3, M42.1.4, M42.2.3, M42.2.8, M42.3.1, M42.3.6
Task ids: M42.3.9, M42.5.1, M42.5.2, M42.5.15, M42.3.3, M42.1.1, M42.3.2
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
    }
    assert checks_in(MODULE) == [STEPS, SECRETS, GUIDES, PIN, UPDATE, SCREEN, HEAD, VARIABLES]


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
