"""The desktop install check: what it names, that it is never a pass, and that it fails for each
way the product's description of a desktop run could be weakened.

The second half of the check (asking the install's launcher to make a desktop sandbox) is not
written, because the launcher makes none, so the check ends as not run on every install. These
tests hold that: the sentence it ends on, that the first half still fails on a product defect
before that sentence is reached, and that the first half is not skipped.

Task ids: M19.8.1
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from brain.browsing import desktop_app
from brain.ops import acceptance_checks_desktop as module
from brain.ops.acceptance import CheckFailedError, CheckNotRunError, registered
from tests.unit.test_acceptance import checks_in

MODULE = "brain.ops.acceptance_checks_desktop"
NAME = "a_desktop_application_runs_in_a_sandbox_with_no_way_out"


class Rolled:
    """A harness stand-in: the check reads its run and nothing else."""

    run = "r1"


def run_it() -> None:
    asyncio.run(module.a_desktop_application_runs_in_a_sandbox_with_no_way_out(Rolled()))  # type: ignore[arg-type]


def test_the_check_names_the_desktop_leaf_and_sits_in_this_packages_range() -> None:
    """Delete this and the check can lose its leaf with the page showing the same row, or sit
    outside the keys this package was given, where it would collide with another package's."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M19.8.1",))]
    assert checks_in(MODULE) == [NAME]
    assert 2300 <= module.CHECK_ORDER <= 2399


def test_a_product_that_describes_its_desktop_soundly_still_ends_as_not_run() -> None:
    """The first half passes on any machine, so it can never be what closes the leaf. Delete this
    and an install that has never started a desktop passes."""
    with pytest.raises(CheckNotRunError) as stopped:
        run_it()

    assert stopped.value.reason == module.A_DESKTOP_THAT_WAS_NEVER_STARTED_HAS_NOT_PASSED


def test_a_sandbox_built_with_a_way_out_fails_the_check_before_it_can_be_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first half is a real check. Delete this and it could be skipped, and the check would
    say not run over a product that was broken."""
    real = desktop_app.desktop_sandbox_for

    def routable(run_id: str, **kw: Any) -> Any:
        built = real(run_id, **kw)
        return type(built)(
            run_id=built.run_id,
            network={**built.network, "Internal": False},
            runner=built.runner,
            command=built.command,
        )

    monkeypatch.setattr(desktop_app, "desktop_sandbox_for", routable)

    with pytest.raises(CheckFailedError):
        run_it()


def test_a_gap_check_that_finds_nothing_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The planted weaknesses must each be found. Delete this and a gap check that was emptied
    passes every sandbox the check plants."""
    monkeypatch.setattr(desktop_app, "desktop_gaps", lambda box, app: ())

    with pytest.raises(CheckFailedError) as failed:
        run_it()

    assert "given a way out passed" in failed.value.reason


def test_a_declaration_that_accepts_a_shell_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a command pattern that admits any path passes the check."""
    import re

    monkeypatch.setattr(desktop_app, "COMMAND_RE", re.compile(r"^/.*$"))

    with pytest.raises(CheckFailedError) as failed:
        run_it()

    assert "could reach another place" in failed.value.reason


def test_a_role_table_that_stopped_translating_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and widgets read as another vocabulary than the enforcer's pass."""
    monkeypatch.setattr(desktop_app, "ROLE_NAMES", {})

    with pytest.raises(CheckFailedError) as failed:
        run_it()

    assert "tree the enforcer reads" in failed.value.reason


def test_two_runs_given_one_name_fail_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a sandbox builder that ignores the run id passes, which puts two runs on one
    network."""
    real = desktop_app.desktop_sandbox_for

    def same(run_id: str, **kw: Any) -> Any:
        return real("fixed", **kw)

    monkeypatch.setattr(desktop_app, "desktop_sandbox_for", same)

    with pytest.raises(CheckFailedError) as failed:
        run_it()

    assert "one network or one container name" in failed.value.reason


def test_an_application_allowed_a_second_origin_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a target that admits a website beside its application passes."""
    from brain.browsing.targets import Target

    def wider(self: desktop_app.DesktopApp) -> Target:
        return Target(
            name=self.name,
            origins=frozenset({self.origin, "https://example.com"}),
            surfaces=self.windows,
        )

    monkeypatch.setattr(desktop_app.DesktopApp, "target", wider)

    with pytest.raises(CheckFailedError) as failed:
        run_it()

    assert "origin other than its own" in failed.value.reason
