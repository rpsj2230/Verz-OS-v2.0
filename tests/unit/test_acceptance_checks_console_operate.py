"""The install checks for the Operate screens, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.14, M27.12.4, M27.2.8, M27.2.6, M27.12.3, M27.15.37
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_operate"
STOP = "the_stop_control_is_drawn_for_its_holders_and_a_stop_is_kept"
RUNS = "running_and_waiting_work_is_listed_by_state_to_its_readers"
AUTOMATION = "an_automation_is_started_changed_paused_and_removed"
ADOPTED = "an_ownerless_automation_is_adopted_and_runs_as_the_adopter"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The two checks and the leaves each closes. Delete this and a check can lose a leaf, or
    gain one it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        STOP: ("M27.15.14", "M27.12.4", "M27.2.8"),
        RUNS: ("M27.2.6",),
        AUTOMATION: ("M27.12.3",),
        ADOPTED: ("M27.15.37",),
    }
    assert checks_in(MODULE) == [STOP, RUNS, AUTOMATION, ADOPTED]


def test_the_figures_the_check_restates_are_the_menus_own() -> None:
    """The two words the check holds the header's control to are the ones the route answers.
    Delete this and a renamed word fails the check on every install with nothing wrong."""
    from brain.navigation_routes import STOP_DEPARTMENTS, STOP_EVERYTHING
    from brain.ops.acceptance_checks_console_operate import STOPS_EVERYTHING, STOPS_ITS_DEPARTMENTS

    assert (STOPS_EVERYTHING, STOPS_ITS_DEPARTMENTS) == (STOP_EVERYTHING, STOP_DEPARTMENTS)


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_operate") as url:
        yield url


def _failed(url: str, name: str) -> str:
    outcome, reason = run_module(url, MODULE)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**Both checks as the worker runs them.** They pass and no person, grant, ledger entry or halt
    is left behind, so the install is never stopped by its own proof. Delete this and a check that
    commits a stop, or one that cannot pass on a real schema, reaches the owner's server first."""
    from tests.fixtures.scratch_postgres import sql

    before = counts(install)
    halts = int(sql(install, "SELECT count(*) FROM ops.halt")[0][0])
    assert run_module(install, MODULE) == {
        STOP: (PASSED, ""),
        RUNS: (PASSED, ""),
        AUTOMATION: (PASSED, ""),
        ADOPTED: (PASSED, ""),
    }
    assert counts(install) == before
    assert int(sql(install, "SELECT count(*) FROM ops.halt")[0][0]) == halts


@pytest.mark.needs_db
def test_a_stop_control_drawn_for_everybody_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The header's control decided as present for every reader. Delete this and M27.15.14 closes
    on a header offering Stop to a person who may stop nothing."""
    from brain import navigation_routes

    real = navigation_routes.stop_offered
    monkeypatch.setattr(
        navigation_routes, "stop_offered", lambda *a, **k: real(*a, **k) or "departments"
    )
    assert "stop nothing" in _failed(install, STOP)


@pytest.mark.needs_db
def test_a_stop_that_is_not_listed_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Stop screen answering no halts. Delete this and M27.2.8 closes on a screen that does
    not say what is stopped."""
    from brain import halt_routes

    monkeypatch.setattr(halt_routes, "stopped_for", lambda *a, **k: ())
    assert "list what had just been stopped" in _failed(install, STOP)


@pytest.mark.needs_db
def test_running_work_shown_to_a_person_with_no_grant_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live runs reading every run as the reader's. Delete this and M27.2.6 closes on a screen that
    shows running work to anybody."""
    from brain.console import operate

    monkeypatch.setattr(operate, "may_watch_unattended", lambda *a, **k: True)
    assert "queue" in _failed(install, RUNS) or "neither" in _failed(install, RUNS)


@pytest.mark.needs_db
def test_an_automation_offered_for_adoption_while_its_owner_is_here_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adoption offered whatever the owner's state. Delete this and M27.15.37 closes on a screen
    that lets an administrator take over an automation whose owner is still here."""
    from brain import automations_routes

    monkeypatch.setattr(automations_routes, "may_adopt", lambda *a, **k: True)
    assert "owner here" in _failed(install, ADOPTED)


@pytest.mark.needs_db
def test_a_change_made_over_a_stale_screen_that_is_kept_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A change whose confirmation is no longer the automation's own accepted. Delete this and
    M27.12.3 closes on a screen where two administrators overwrite one another unseen."""
    from brain import automations_routes

    monkeypatch.setattr(automations_routes, "shown", lambda *a, **k: "0" * 64)
    assert "moved" in _failed(install, AUTOMATION) or "start" in _failed(install, AUTOMATION)
