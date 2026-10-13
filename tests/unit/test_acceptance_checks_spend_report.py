"""The install checks for the cost ledger, the Spend report and budget versions, each passing on
PostgreSQL at head and each failing with the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: both checks
pass and leave nothing. Then each is shown failing: a report that counts machine traffic by
default, one that shows a department's spend to a reader of another, a view that is not rebuilt
from the ledger, and a budget append that writes no ledger entry.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M21.1.5, M21.2.3, M21.3.1, M21.3.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_spend_report import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_spend_report"
REPORT = "a_run_is_recorded_and_the_report_shows_it_in_every_dimension"
VERSIONS = "every_budget_version_is_a_row_and_a_ledger_entry"


def test_the_module_names_each_leaf_in_one_check() -> None:
    """Two checks, each closing its own leaves. Delete this and a leaf can move to a check that
    never looked at it, with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REPORT, ("M21.2.3", "M21.3.1", "M21.3.2")),
        (VERSIONS, ("M21.1.5",)),
    ]
    assert checks_in(MODULE) == [REPORT, VERSIONS]
    assert 2100 <= CHECK_ORDER <= 2199


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_spend_report") as url:
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
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing a check wrote is left: no cost
    row, no rebuilt view, no budget version. Delete this and a check that can never pass on a
    real schema, or one that leaves a budget behind, reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
def test_machine_traffic_counted_by_default_fails_the_report_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report counting machine traffic whatever it was asked. Delete this and M21.3.2 closes
    on a report that prices a nightly sync as questions."""
    from brain import report_routes
    from brain.console.spend_report_view import spend_report_from_view as real

    def always_machine(*args: Any, **kwargs: Any) -> Any:
        kwargs["include_machine"] = True
        return real(*args, **kwargs)

    monkeypatch.setattr(report_routes, "spend_report_from_view", always_machine)
    assert "machine" in _failed(install, REPORT)


@pytest.mark.needs_db
def test_a_report_open_to_every_department_fails_the_report_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report's per-department admission removed. Delete this and M21.3.1 closes on a report
    that tells a department head what another department spent."""
    from brain import report_routes
    from brain.console import spend_report_view

    monkeypatch.setattr(spend_report_view, "may_read_spend", lambda *a, **k: True)
    assert report_routes is not None
    assert "another" in _failed(install, REPORT)


@pytest.mark.needs_db
def test_a_budget_version_with_no_ledger_entry_fails_the_versions_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The budget store writing its row without the attribution the ledger trigger needs is not
    reproducible here; what is, is the ledger being asked for an entry the store did not make.
    Delete this and M21.1.5 closes on a version nothing recorded."""
    from brain.ops import budget_store

    async def no_row(*args: Any, **kwargs: Any) -> Any:
        from brain.ops.budgets import BudgetHistory

        return BudgetHistory(rows=())

    monkeypatch.setattr(budget_store, "append", no_row)
    assert _failed(install, VERSIONS)
