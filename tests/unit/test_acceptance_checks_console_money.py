"""The install check for the console's money figures, passing on PostgreSQL at head, leaving
nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.33
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_money"
MONEY = "an_unrecorded_cost_is_not_nought_and_a_cost_names_its_currency"


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """The check and the leaf it closes. Delete this and the check can lose M27.15.33, or gain a
    leaf it does not prove, with the screens unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {MONEY: ("M27.15.33",)}
    assert checks_in(MODULE) == [MONEY]


def test_the_currency_the_check_moves_prices_to_is_never_the_installs() -> None:
    """The check repoints every price to a currency that is not the install's. Delete this and a
    currency list that grows to hold the install's own makes the 'unpriced' half price it."""
    from brain.ops.acceptance_checks_console_money import OTHER_CURRENCIES

    assert len(set(OTHER_CURRENCIES)) >= 2


@pytest.fixture(autouse=True)
def a_currency_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install's currency, which a cost is recorded in and without which the check says it was
    not run. Delete this and every test below reads the empty state and proves nothing."""
    monkeypatch.setenv("INSTALL_CURRENCY", "USD")


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_money") as url:
        yield url


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[MONEY]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no price, spend or ledger entry.
    Delete this and a check that commits the prices it repoints reaches the owner's server
    first."""
    before = counts(install)
    outcome = run_module(install, MODULE)[MONEY]
    assert outcome[0] == PASSED, outcome
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_cost_that_is_nought_when_nothing_is_priced_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent's stats that sum an empty table. Delete this and M27.15.33 closes on a cost of
    nought served as a measurement, the figure the leaf exists to refuse."""
    from brain import console_stats_routes

    async def always_priced(session: object) -> tuple[str, None]:
        return "XXX", None

    monkeypatch.setattr(console_stats_routes, "cost_recorded_in", always_priced)
    assert "agent's stats served a cost" in _failed(install)
