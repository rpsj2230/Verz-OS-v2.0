"""The install checks for an agent's recent runs and a person's own page, passing on PostgreSQL at
head, leaving nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.27, M27.15.18
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_lists"
RECENT = "an_agents_recent_runs_are_the_ones_its_reader_is_counted_over"
PERSON = "a_persons_page_lists_what_they_own_and_what_the_ledger_says"
STOPPED = "adoption_counts_who_stopped_asking_in_the_readers_departments"
FIGURES = "landing_figures_follow_the_period_and_department_a_reader_reads"


def test_the_module_declares_the_leaf_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the pages unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        RECENT: ("M27.15.27",),
        PERSON: ("M27.15.18",),
        STOPPED: ("M27.7.17",),
        FIGURES: ("M27.15.17",),
    }
    assert checks_in(MODULE) == [RECENT, PERSON, STOPPED, FIGURES]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_lists") as url:
        yield url


@pytest.fixture(autouse=True)
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def _failed(url: str, name: str) -> str:
    outcome, reason = run_module(url, MODULE)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The checks as the worker runs them.** Each passes and leaves no agent, request, spend or
    ledger entry. Delete this and a check that commits what it wrote reaches the owner's server
    first."""
    before = counts(install)
    assert run_module(install, MODULE) == {
        RECENT: (PASSED, ""),
        PERSON: (PASSED, ""),
        STOPPED: (PASSED, ""),
        FIGURES: (PASSED, ""),
    }
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_list_that_forgets_the_runs_fails_the_recent_runs_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Dashboard whose list is always empty. Delete this and M27.15.27 closes on the note it
    replaced."""
    monkeypatch.setattr("brain.console_stats_routes.recent_runs", lambda runs, names: [])
    assert "newest first" in _failed(install, RECENT)


@pytest.mark.needs_db
def test_a_list_that_names_somebody_elses_run_fails_the_recent_runs_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A member's list built from everybody's runs. Delete this and M27.15.27 closes on a list that
    tells a member who else asked the agent."""
    from brain.console.workspace import Basis

    monkeypatch.setattr(
        "brain.console_stats_routes.usage_basis", lambda reach, now=None: Basis.EVERYONE
    )
    assert "somebody else made" in _failed(install, RECENT)


@pytest.mark.needs_db
def test_an_adoption_that_never_looks_back_fails_the_stopped_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A figure that is always nought. Delete this and M27.7.17 closes on a page that cannot say
    who has stopped, which is the half of the leaf nothing else watches."""
    monkeypatch.setattr("brain.report_routes.stopped_for_reader", lambda *args, **kwargs: {})
    assert "stopped asking" in _failed(install, STOPPED)


@pytest.mark.needs_db
def test_figures_that_ignore_the_department_fail_the_figures_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A department filter that narrows nothing. Delete this and M27.15.17 closes on a landing
    screen whose department figures are the company's."""
    from brain import console_overview_figures_routes as routes

    real = routes.request_outcomes
    monkeypatch.setattr(
        routes,
        "request_outcomes",
        lambda since, until, **kwargs: real(since, until, **{**kwargs, "department": None}),
    )
    assert "did not count its people's questions" in _failed(install, FIGURES)
