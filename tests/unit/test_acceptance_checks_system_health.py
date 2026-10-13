"""The install check for System health, passing on PostgreSQL at head and failing with the product
broken the way it would plausibly break.

The database half runs the check as the worker would and shows it failing with the guarantee
rule broken (a control behind still held), the whole-installation rule removed, and the worker read
from nothing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.13.2, M27.15.54
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_system_health"
CHECK = "system_health_shows_a_guarantee_held_only_while_its_control_runs"


def test_the_module_declares_its_one_check_for_its_two_leaves() -> None:
    """Delete this and the check can lose a leaf with the Install page showing the same rows, and
    the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CHECK, ("M27.13.2", "M27.15.54"))
    ]
    assert checks_in(MODULE) == [CHECK]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_system_health") as url:
        yield url


def run_check(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    [only] = results
    return only.outcome, only.reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and no run record is left. Delete this and a
    check that can never pass on a real schema, or that leaves a run behind for the worker's
    schedule to read as done, reaches the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    before = (counts(install), sql(install, "SELECT count(*) FROM ops.control_run"))
    assert run_check(install) == (PASSED, "")
    assert (counts(install), sql(install, "SELECT count(*) FROM ops.control_run")) == before


@pytest.mark.needs_db
def test_a_control_that_is_behind_but_shown_as_held_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The register read as never overdue. Delete this and M27.15.54 closes on a screen that shows
    every protection in force whatever the scheduler recorded."""
    from brain import system_health_routes
    from brain.ops import guarantee_state

    monkeypatch.setattr(guarantee_state, "overdue", lambda **kwargs: ())
    monkeypatch.setattr(system_health_routes, "guarantees", guarantee_state.guarantees)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "shown as held" in reason


@pytest.mark.needs_db
def test_a_department_reader_shown_the_screen_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole-installation rule removed. Delete this and M27.13.2 closes on a screen that tells a
    department's reader about the vault and the worker."""
    from brain import system_health_routes

    monkeypatch.setattr(system_health_routes, "held_across_the_install", lambda *args: True)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "one department" in reason
