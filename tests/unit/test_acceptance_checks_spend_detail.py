"""The install checks for what an answer costs, the dearest shapes and the stops in force, each
passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M21.3.3, M21.3.4, M21.3.6
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_spend_detail import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_spend_detail"
COST = "what_one_answer_costs_is_a_distribution_not_a_mean"
SHAPES = "dearest_question_shapes_are_ranked_from_their_own_requests"
STOPS = "every_budget_stop_in_force_is_listed_to_those_who_may_be_told"


def test_the_module_names_each_leaf_in_one_check_inside_its_range() -> None:
    """Three checks, each closing its own leaf, in the assigned order range. Delete this and a
    leaf can move to a check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (COST, ("M21.3.3",)),
        (SHAPES, ("M21.3.4",)),
        (STOPS, ("M21.3.6",)),
    ]
    assert checks_in(MODULE) == [COST, SHAPES, STOPS]
    assert 2100 <= CHECK_ORDER <= 2199


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_spend_detail") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
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
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and nothing a check wrote is left: no
    cost row, no request row, no stop. Delete this and a check that can never pass on a real
    schema, or one that leaves a stop behind refusing real questions, reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_median_that_is_a_mean_or_a_quantile_the_sample_cannot_hold_fails_the_cost_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The distribution stated with its quantiles shifted by one rank. Delete this and M21.3.3
    closes on a figure that is not the nearest-rank answer anybody paid."""
    from brain.console import spend_view

    real = spend_view.distribution

    def off_by_one(costs: Any, *, quantiles: Any = spend_view.QUANTILES) -> Any:
        return real([one + 1 for one in costs], quantiles=quantiles)

    monkeypatch.setattr(spend_view, "distribution", off_by_one)
    assert _failed(install, COST)


@pytest.mark.needs_db
def test_an_unrecorded_shape_guessed_into_a_known_one_fails_the_shapes_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cost with no recorded shape filed under the dearest shape. Delete this and M21.3.4
    closes on a ranking that says what an unknown cost bought."""
    from brain.console.spend_view import shape_report as real
    from brain.core.lane import Lane
    from brain.ops.telemetry import QuestionShape

    def guess(actuals: Any, shapes: Any, entitlement: Any, **kwargs: Any) -> Any:
        everything = QuestionShape(Lane.TASK, 3)
        return real(
            actuals,
            dict.fromkeys(((one.trace_id, one.principal_id) for one in actuals), everything),
            entitlement,
            **kwargs,
        )

    monkeypatch.setattr("brain.ops.spend_store.shape_report", guess)
    assert _failed(install, SHAPES)


@pytest.mark.needs_db
def test_a_stop_shown_to_a_reader_of_another_department_fails_the_stops_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop board's department filter removed. Delete this and M21.3.6 closes on a board that
    tells a department's reader another department's budget has stopped."""
    from brain import spend_detail_routes

    monkeypatch.setattr(spend_detail_routes, "budget_stops", lambda rows, *a, **k: tuple(rows))
    assert "another department" in _failed(install, STOPS)
