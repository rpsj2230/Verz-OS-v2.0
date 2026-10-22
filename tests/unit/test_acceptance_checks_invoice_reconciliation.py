"""The install check for metered spend against a provider's invoice, passing on PostgreSQL at head
and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M21.4.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.ops.acceptance_checks_invoice_reconciliation import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_invoice_reconciliation"
CHECK = "metered_spend_is_held_against_a_providers_invoice"


def test_the_module_names_its_leaf_in_one_check() -> None:
    """One check, one leaf. Delete this and the leaf can move to a check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CHECK, ("M21.4.1",))]
    assert checks_in(MODULE) == [CHECK]
    assert 2140 < CHECK_ORDER < 2150


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_invoice") as url:
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


@pytest.fixture
def currency(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install names its currency, which the process reads from its environment."""
    monkeypatch.setenv("INSTALL_CURRENCY", "SGD")


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str, currency: None) -> None:
    """**The module as the worker runs it.** It passes and nothing is left. Delete this and a check
    that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {CHECK: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_install_with_no_currency_says_it_was_not_run(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a currency there is nothing to compare in, and the check says so rather than pass.
    Delete this and an install that never set its currency shows a green row for a comparison
    that never ran."""
    monkeypatch.delenv("INSTALL_CURRENCY", raising=False)
    outcome, reason = run_module(install)[CHECK]
    assert outcome == NOT_RUN and "currency" in reason


@pytest.mark.needs_db
def test_a_route_that_counts_a_request_outside_the_window_fails_the_check(
    install: str, currency: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window dropped from the read. Delete this and an invoice for May is held against
    spend from the months before it."""
    from brain.ops import spend_store

    original = spend_store.costs_by_model_between

    async def whole_ledger(session: object, since: object, until: object) -> object:
        from datetime import UTC, datetime, timedelta

        return await original(session, datetime.now(UTC) - timedelta(days=3650), until)  # type: ignore[arg-type]

    from brain import spend_detail_routes

    monkeypatch.setattr(spend_detail_routes, "costs_by_model_between", whole_ledger)
    outcome, reason = run_module(install)[CHECK]
    assert outcome == FAILED
    assert "a month before" in reason


@pytest.mark.needs_db
def test_a_route_that_shows_providers_to_a_department_reader_fails_the_check(
    install: str, currency: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The company-wide grant requirement removed. Delete this and a department head is shown what
    a provider charged for everybody."""
    from brain import spend_detail_routes

    monkeypatch.setattr(spend_detail_routes, "may_read_unplaced", lambda *args, **kwargs: True)
    outcome, reason = run_module(install)[CHECK]
    assert outcome == FAILED
    assert "provider's total" in reason
