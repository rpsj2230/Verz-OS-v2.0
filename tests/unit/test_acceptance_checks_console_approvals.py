"""The install check for an approval naming its agent, passing on PostgreSQL at head, leaving
nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.30, M27.11.15
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_approvals"
APPROVALS = "an_approval_names_its_agent_and_each_agent_lists_only_its_own"


def test_the_module_declares_the_leaves_its_check_proves() -> None:
    """The check and the leaves it closes. Delete this and the check can lose M27.15.30, or gain a
    leaf it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        APPROVALS: ("M27.15.30", "M27.11.15")
    }
    assert checks_in(MODULE) == [APPROVALS]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_approvals") as url:
        yield url


@pytest.fixture(autouse=True)
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[APPROVALS]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no suspension, person or ledger
    entry. Delete this and a check that commits a held action reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {APPROVALS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_card_that_forgets_its_agent_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card built without the agent. Delete this and M27.15.30 closes on cards that name nobody,
    so an agent's page has nothing to list."""
    from brain.console import approvals

    real = approvals.card

    def nameless(*args: object, **kwargs: object) -> object:
        made = real(*args, **kwargs)  # type: ignore[arg-type]
        return None if made is None else dataclasses.replace(made, agent_id="")

    monkeypatch.setattr("brain.approval_routes.card", nameless)
    assert "did not name the agent" in _failed(install)
