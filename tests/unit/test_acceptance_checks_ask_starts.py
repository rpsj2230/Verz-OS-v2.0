"""The Ask starts install checks, passing on PostgreSQL at head and failing when broken.

The database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.7.5, M40.7.2, M40.7.8
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import checks_in, counts
from tests.unit.test_acceptance_skill_runs import at_head_laddered, run_checks

MODULE = "brain.ops.acceptance_checks_ask_starts"
ROUTING = "a_task_with_no_agent_goes_to_the_agent_it_matches"
TRYING = "a_member_tries_an_approved_skill_for_one_question"
STARTERS = "an_agent_opened_offers_the_examples_of_its_skills"


def test_the_module_declares_its_leaves_and_sits_in_its_range() -> None:
    """One check for each of the three leaves. Delete this and a check can lose its leaf with the
    page showing the same row."""
    from brain.ops import acceptance_checks_ask_starts as module

    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        ROUTING: ("M40.7.5",),
        TRYING: ("M40.7.2",),
        STARTERS: ("M40.7.8",),
    }
    assert sorted(checks_in(MODULE)) == sorted([ROUTING, TRYING, STARTERS])
    assert module.CHECK_ORDER == 1960


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head_laddered("brain_acceptance_ask_starts") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hosted profile, so the stand-in may be asked; no provider's key is needed for it."""
    monkeypatch.setenv("INSTALL_MODEL_PROFILE", "hosted")


def run(url: str, only: str | None = None) -> dict[str, tuple[str, str]]:
    chosen = [one for one in registered((MODULE,)) if only is None or one.name == only]
    return run_checks(url, chosen)


def _failed(url: str, which: str) -> str:
    [(outcome, reason)] = run(url, which).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_ask_start_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: all three pass and nothing is left behind. Delete this and
    a check that cannot pass on a real schema, or one that commits a row, ships."""
    before = counts(install)
    assert run(install) == {ROUTING: (PASSED, ""), TRYING: (PASSED, ""), STARTERS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_selector_that_ignores_what_agents_are_for_fails_the_routing_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The profiles dropped on the way to the selector. Delete this and M40.7.5 closes on a task
    that is always answered by the default."""
    from brain import api_routes

    async def nothing(state: object, roster: object, *, named: bool) -> dict[str, str]:
        return {}

    monkeypatch.setattr(api_routes, "task_profiles", nothing)
    assert "purpose it matches" in _failed(install, ROUTING)


@pytest.mark.needs_db
def test_a_try_that_pins_without_asking_the_switch_fails_the_trying_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trying that ignores its switch. Delete this and M40.7.2 closes on a feature that cannot be
    turned off."""
    from brain import api_routes

    async def always(state: object) -> bool:
        return True

    monkeypatch.setattr(api_routes, "trying_a_skill_is_on", always)
    assert "switched off" in _failed(install, TRYING)


@pytest.mark.needs_db
def test_starters_that_ignore_the_runs_reach_fail_the_starters_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every example offered to whoever opens the agent. Delete this and M40.7.8 closes on a
    route that tells a person who may not run an agent what to ask it."""
    from brain import member_starter_routes

    monkeypatch.setattr(
        member_starter_routes,
        "runnable_agent_ids",
        lambda records, viewer: frozenset(r.agent_id for r in records),
    )
    monkeypatch.setattr(member_starter_routes, "visible_to", lambda audience, viewer: True)
    assert "may not run an agent" in _failed(install, STARTERS)
