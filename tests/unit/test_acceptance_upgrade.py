"""The agent upgrade acceptance check: registered, passing on a real schema, and able to fail.

Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_upgrade"
UPGRADE = "a_newer_version_is_reviewed_and_never_raises_a_rung"
LEAVES = ("M13.4.2", "M13.4.3", "M13.4.4", "M13.4.5")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_upgrade_check_is_listed_and_names_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of its module, or close a leaf it does not exercise,
    with the Install page simply listing one row fewer."""
    assert checks_in(MODULE) == [UPGRADE]
    assert MODULE in check_modules()
    assert mine()[UPGRADE].leaves == LEAVES


@pytest.mark.needs_db
def test_on_a_real_database_the_upgrade_check_passes_and_leaves_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and an agent
    could stop being upgradable on the owner's install with nothing there saying so."""
    with at_head("brain_acceptance_upgrade") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {UPGRADE: (PASSED, "")}
    assert after == before


def broken_and_run(monkeypatch: pytest.MonkeyPatch, label: str, setup: Any) -> Any:
    setup(monkeypatch)
    with at_head(f"brain_acceptance_upgrade_{label}") as url:
        return run_checks(url, tuple(mine().values()))[UPGRADE]


def _raises_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_upgrade_routes as routes
    import brain.agents.upgrade as domain

    monkeypatch.setattr(domain, "rungs_an_upgrade_would_raise", lambda reviewed: ())
    monkeypatch.setattr(routes, "rungs_an_upgrade_would_raise", lambda reviewed: ())


def _declines_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.agent_upgrade_routes import StoredAgentUpgrades

    async def forgets(self: Any, made: Any, **rest: Any) -> bool:
        return False

    monkeypatch.setattr(StoredAgentUpgrades, "decline", forgets)


def _accepts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.agent_upgrade_routes import StoredAgentUpgrades

    async def writes_nothing(self: Any, upgraded: Any, **rest: Any) -> bool:
        return True

    monkeypatch.setattr(StoredAgentUpgrades, "accept", writes_nothing)


def _anybody_holds_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_upgrade_routes as routes

    monkeypatch.setattr(routes, "holds", lambda capability, record, asked: True)
    monkeypatch.setattr(routes, "visible", lambda record, asked: True)


def _a_review_with_no_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_upgrade_routes as routes
    import brain.agents.upgrade as domain

    kept = domain.review

    def no_conflicts(*args: Any, **kwargs: Any) -> Any:
        import dataclasses

        return dataclasses.replace(kept(*args, **kwargs), conflicts=())

    monkeypatch.setattr(domain, "review", no_conflicts)
    monkeypatch.setattr(routes, "review", no_conflicts)


BREAKS: dict[str, tuple[Any, str]] = {
    "raises_a_rung": (_raises_nothing, "RUNG_NOT_SAID"),
    "forgets_a_decline": (_declines_nothing, "NO_DECLINE"),
    "accepts_nothing": (_accepts_nothing, "NOT_MOVED"),
    "told_to_anybody": (_anybody_holds_it, "OUTSIDER_TOLD"),
    "no_conflicts_shown": (_a_review_with_no_conflicts, "NOT_A_CONFLICT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_upgrade_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: a version holding a
    higher rung than the agent is on that the review does not refuse (M13.4.4), a decline that is
    not kept (M13.4.5), an acceptance that moves nothing (M13.4.4), a review shown to a reader of
    another department (M13.4.2) and a claimed path that is not shown as a conflict (M13.4.3).
    Delete this and the check can pass with any of them gone."""
    import brain.ops.acceptance_checks_upgrade as module

    setup, reason = BREAKS[broken]
    assert broken_and_run(monkeypatch, broken, setup) == (FAILED, getattr(module, reason))
