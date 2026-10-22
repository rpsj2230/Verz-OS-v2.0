"""The install checks for a department's budget and allowances, passing on PostgreSQL at head and
failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M21.1.2, M21.1.3, M21.1.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_department_budgets import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_department_budgets"
SHARING = "department_shares_and_transfers_are_versions_and_nothing_else"
ALLOWANCES = "a_departments_people_are_given_capped_allowances"


def test_the_module_names_its_leaves_in_two_checks_inside_its_range() -> None:
    """Two checks, each naming its leaves, in a range of their own. Delete this and a leaf can move
    to a check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (SHARING, ("M21.1.2", "M21.1.1")),
        (ALLOWANCES, ("M21.1.3",)),
    ]
    assert checks_in(MODULE) == [SHARING, ALLOWANCES]
    assert 2150 < CHECK_ORDER < 2160


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_department_budgets") as url:
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
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing is left behind. Delete this and
    a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {SHARING: (PASSED, ""), ALLOWANCES: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_allocation_that_ignores_what_the_other_departments_hold_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The partial-allocation rule removed from the planner. Delete this and shares that together
    hold more than the company's budget are accepted whenever a request names half the
    departments."""
    from brain import department_budget_routes as routes

    original = routes.plan_allocation

    def unchecked(company: Any, shares: Any, held: Any, **kwargs: Any) -> Any:
        # Only the departments the request names are counted, which is what a planner that did not
        # add up the departments it leaves out would have let through.
        named = {one.department for one in shares}
        return original(company, shares, {k: v for k, v in held.items() if k in named}, **kwargs)

    monkeypatch.setattr(routes, "plan_allocation", unchecked)
    outcome, reason = run_module(install)[SHARING]
    assert outcome == FAILED
    assert "more than the company" in reason


@pytest.mark.needs_db
def test_a_route_that_ignores_the_authority_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority over everything dropped from the allocation. Delete this and the head of one
    department can set the shares of all of them."""
    from brain import department_budget_routes as routes

    monkeypatch.setattr(routes, "_may_move_company_money", lambda *args: True)
    outcome, reason = run_module(install)[SHARING]
    assert outcome == FAILED
    assert "administrator of one department" in reason


@pytest.mark.needs_db
def test_allowances_that_are_not_capped_fail_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fair-share cap lifted from the derivation. Delete this and one person can be given the
    whole of a department's month."""
    from brain.ops import budgets

    monkeypatch.setattr(budgets, "USER_FAIR_SHARE", 1.0)
    monkeypatch.setattr(budgets, "ALLOWANCE_GENEROSITY", 1000.0)
    outcome, reason = run_module(install)[ALLOWANCES]
    assert outcome == FAILED
    assert "quarter" in reason
