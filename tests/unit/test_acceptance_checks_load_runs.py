"""The install check for the peak runs listed beside the service levels, passing on PostgreSQL at
head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M36.2.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_load_runs import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_load_runs"
CHECK = "a_kept_peak_run_is_listed_beside_the_service_levels"


def test_the_module_names_its_leaf_in_one_check() -> None:
    """One check, one leaf. Delete this and the leaf can move to a check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CHECK, ("M36.2.4.3",))]
    assert checks_in(MODULE) == [CHECK]
    assert 2145 < CHECK_ORDER < 2150


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_load_runs") as url:
        yield url


def run_module(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings_from({"BRAIN_DATABASE_URL": url}),
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes and nothing is left. Delete this and a check
    that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {CHECK: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_listing_that_shows_runs_to_a_department_reader_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service levels reader decision removed. Delete this and a department head is shown when
    the install was load tested and how it did."""
    from brain import load_run_routes

    monkeypatch.setattr(load_run_routes, "may_read_service_levels", lambda *a, **k: True)
    outcome, reason = run_module(install)[CHECK]
    assert outcome == FAILED and "one department" in reason


@pytest.mark.needs_db
def test_a_listing_that_pairs_a_lane_with_the_wrong_objective_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The objective lookup answering every lane with the same figure. Delete this and a run's
    figures can sit beside an objective that is not the lane's."""
    from brain import load_run_routes
    from brain.core.lane import Lane
    from brain.ops.reliability import lane_objective

    monkeypatch.setattr(
        load_run_routes,
        "lane_objective",
        lambda lane, *a: lane_objective(Lane("fast")),
    )
    outcome, reason = run_module(install)[CHECK]
    assert outcome == FAILED and "objective" in reason
