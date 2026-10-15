"""The agent slice check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would. Then it is run
against the product broken where it proves: an artifact read that ignores the agent named, a
learning read that does, a memory read that does, and a memory read that answers for an agent the
reader may not see.

Task ids: M27.15.34
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_agent_slice"
NAME = "an_estate_read_cut_to_an_agent_is_its_slice_and_hides_the_rest"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def test_the_agent_slice_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M27.15.34",)


@pytest.mark.needs_db
def test_on_a_real_database_each_read_is_cut_to_an_agent_and_nothing_is_left() -> None:
    """**The check as the worker runs it.** Delete this and a filter that is accepted and ignored,
    or one that answers for an agent the reader cannot see, reaches an install with nothing
    saying so."""
    with at_head("brain_acceptance_agent_slice") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _artifacts_ignore_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.artifact_routes as routes

    monkeypatch.setattr(routes, "artifacts_of_agent", lambda shown, _agent: tuple(shown))


def _learning_ignores_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.estate_routes as routes

    monkeypatch.setattr(routes, "records_of_agent", lambda visible, _agent: tuple(visible))


def _memory_ignores_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.estate_routes as routes

    monkeypatch.setattr(
        routes,
        "subject_memory_of_agent",
        lambda remembered, _agent, *, formed_by, visible_agents: remembered,
    )


def _memory_answers_for_an_agent_the_reader_may_not_see(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.estate_routes as routes
    from brain.console.govern_estate import subject_memory_of_agent as original

    def every_agent_is_visible(
        remembered: Any, agent: Any, *, formed_by: Any, visible_agents: Any
    ) -> Any:
        return original(
            remembered, agent, formed_by=formed_by, visible_agents=set(formed_by.values())
        )

    monkeypatch.setattr(routes, "subject_memory_of_agent", every_agent_is_visible)


BREAKS: dict[str, tuple[Any, str]] = {
    "artifacts_ignore_the_agent": (_artifacts_ignore_the_agent, "ARTIFACTS_NOT_CUT"),
    "learning_ignores_the_agent": (_learning_ignores_the_agent, "LEARNING_NOT_CUT"),
    "memory_ignores_the_agent": (_memory_ignores_the_agent, "MEMORY_NOT_CUT"),
    "memory_answers_for_a_hidden_agent": (
        _memory_answers_for_an_agent_the_reader_may_not_see,
        "HIDDEN_AGENT_TOLD_APART",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_agent_slice_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found, in its own words. Delete this and the check
    can pass over a filter nothing reads, which is the control `docs/admin-console.md` calls worse
    than none."""
    import brain.ops.acceptance_checks_agent_slice as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_agent_slice_{broken}"[:60]) as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
