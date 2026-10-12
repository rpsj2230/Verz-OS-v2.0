"""The company-budget install check: registered, passing on PostgreSQL, able to fail.

The pure half holds the module to its leaf and its place in the run. The database half builds
PostgreSQL to head once, runs the check as the worker would, and then breaks the product one part at
a time (a route that lets a department's administrator set the company's budget, one that shows the
ceiling to a reader whose total is withheld) and shows the check failing with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M33.1.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_company_budget"
NAME = "the_company_budget_is_set_and_read_beside_the_spend"

WRITTEN = (
    "ops.budget_version",
    "ops.spend_actual",
    "auth.principal",
    "gate.capability_grant",
    "gate.department",
    "obs.audit_entry",
)


def test_the_module_declares_one_check_naming_the_leaf_it_proves() -> None:
    """One check, one leaf. Delete this and the check can lose its leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M33.1.1.3",))]
    assert checks_in(MODULE) == [NAME]
    from brain.ops import acceptance_checks_company_budget as module

    assert 880 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_company_budget") as url:
        yield url


def run_mine(url: str) -> dict[str, tuple[str, str]]:
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


def held(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and nothing it wrote is left. Delete this and
    a check that can never pass on a real schema, or one that commits, reaches the owner's
    server."""
    before = held(install)
    assert run_mine(install) == {NAME: (PASSED, "")}
    assert held(install) == before


@pytest.mark.needs_db
def test_a_route_that_lets_a_departments_administrator_set_the_companys_budget_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority asked over every scope as if it were held over everything. Delete this and the
    check closes M33.1.1.3 on an install where a department's budget administrator sets the
    company's."""
    from brain import company_routes

    monkeypatch.setattr(company_routes, "within_reach", lambda *_args, **_kw: True)
    outcome, reason = run_mine(install)[NAME]
    assert outcome == FAILED
    assert "budget administrator over one department set" in reason


@pytest.mark.needs_db
def test_a_ceiling_sent_to_a_reader_whose_total_is_withheld_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A consumption that is shown to a reader it should be withheld from, so the ceiling beside it
    goes too. Delete this and the check closes M33.1.1.3 on a read that sends the company's
    ceiling to a reader who should be shown nothing."""
    from brain import company_routes
    from brain.console.global_surfaces import CompanyConsumption

    original = company_routes.company_consumption

    def leaky(*args: Any, **kwargs: Any) -> Any:
        return original(*args, **kwargs) or CompanyConsumption(spend_minor=0, by_department=())

    monkeypatch.setattr(company_routes, "company_consumption", leaky)
    outcome, reason = run_mine(install)[NAME]
    assert outcome == FAILED
    assert "withheld was shown the company's ceiling" in reason
