"""The install check for the leash on an agent's page, passing on PostgreSQL at head, leaving
nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.12.8, M27.3.12
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_leash"
LEASH = "a_rung_falls_at_once_and_rises_only_on_proof_and_a_second_person"


def test_the_module_declares_the_leaves_its_check_proves() -> None:
    """The check and the leaves it closes. Delete this and a check can lose a leaf, or gain one it
    does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        LEASH: ("M27.12.8", "M27.3.12")
    }
    assert checks_in(MODULE) == [LEASH]


def test_the_authority_and_the_evidence_the_check_holds_are_the_products_own() -> None:
    """The authority the check's holders hold, and the number of actions it judges, held against
    the route's own and the bar's. Delete this and a renamed authority, or a raised bar, fails the
    check on every install with nothing wrong."""
    from brain.agent_leash_routes import LEASH_AUTHORITY
    from brain.console.reach_view import MINIMUM_CLEAN_RUNS
    from brain.ops.acceptance_checks_console_leash import JUDGED, MOVES_A_RUNG

    assert LEASH_AUTHORITY.value == MOVES_A_RUNG
    assert JUDGED > MINIMUM_CLEAN_RUNS


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_leash") as url:
        yield url


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[LEASH]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no person, grant, ledger entry,
    leash move or judged action. Delete this and a check that commits, or one that cannot pass on
    a real schema, reaches the owner's server first."""
    from tests.fixtures.scratch_postgres import sql

    tables = ("agent.leash_change", "agent.supervised_action", "agent.action_verdict")
    before = counts(install)
    held = [int(sql(install, f"SELECT count(*) FROM {one}")[0][0]) for one in tables]  # noqa: S608
    assert run_module(install, MODULE) == {LEASH: (PASSED, "")}
    assert counts(install) == before
    assert held == [int(sql(install, f"SELECT count(*) FROM {one}")[0][0]) for one in tables]  # noqa: S608


@pytest.mark.needs_db
def test_a_rise_with_no_second_person_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A confirmation by whoever proposed it accepted. Delete this and M27.12.8 closes on a leash
    one person can loosen alone across a boundary that cannot be undone."""
    from brain.agents import leash_moves

    real = leash_moves.raising

    def alone(*args: object, **kwargs: object) -> object:
        kwargs["pending"] = None
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("brain.agent_leash_routes.raising", alone)
    assert "proposed a rise" in _failed(install)
