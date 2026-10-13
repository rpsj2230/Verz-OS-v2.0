"""The install check for an agent's per-run and per-day ceilings, passing on PostgreSQL at head and
failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M21.1.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_agent_ceilings import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_agent_ceilings"
CEILINGS = "an_agents_run_and_day_ceilings_are_set_together_as_versions"


def test_the_module_names_its_leaf_in_one_check_inside_its_range() -> None:
    """One check, one leaf, in the assigned order range. Delete this and the leaf can move to a
    check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CEILINGS, ("M21.1.4",))]
    assert checks_in(MODULE) == [CEILINGS]
    assert 2100 <= CHECK_ORDER <= 2199


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_agent_ceilings") as url:
        yield url


def run_module(url: str) -> dict[str, tuple[str, str]]:
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
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes and nothing is left. Delete this and a
    check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {CEILINGS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_route_that_ignores_the_authority_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority question removed from the ceilings route. Delete this and M21.1.4 closes on a
    route any reader of an agent can use to set what it may spend."""
    from brain import agent_workspace_routes

    monkeypatch.setattr(agent_workspace_routes, "may_set_budget", lambda *args: True)
    [(outcome, reason)] = run_module(install).values()
    assert outcome == FAILED
    assert "without the budget role" in reason or "set an agent" in reason


@pytest.mark.needs_db
def test_a_run_ceiling_above_the_day_s_accepted_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pair's own refusal removed. Delete this and a run ceiling that can never bind reads as
    protection the agent has."""
    from brain import agent_workspace_routes
    from brain.ops.budgets import BudgetRow

    def unrefused(*args: Any, **kwargs: Any) -> tuple[BudgetRow, BudgetRow]:
        from brain.ops.budgets import BudgetLevel, BudgetPeriod

        def row(period: BudgetPeriod, amount: int) -> BudgetRow:
            return BudgetRow(
                level=BudgetLevel.AGENT,
                subject=kwargs["agent_id"],
                period=period,
                ceiling_minor=amount,
                version=1,
                author=kwargs["author"],
                effective_from=kwargs["now"],
                reason="x",
            )

        return row(BudgetPeriod.RUN, kwargs["per_run_minor"]), row(
            BudgetPeriod.DAY, kwargs["per_day_minor"]
        )

    monkeypatch.setattr(agent_workspace_routes, "next_ceilings", unrefused)
    [(outcome, _)] = run_module(install).values()
    assert outcome == FAILED
