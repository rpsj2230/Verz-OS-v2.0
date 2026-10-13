"""The agent-oversight check: registered, passing on a real schema, and able to fail.

Run as the worker would, then against the product broken where it proves: a steward told nothing, a
colleague told of other people's use, and a conversation told with its words.

Task ids: M39.11.1, M39.11.2
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

MODULE = "brain.ops.acceptance_checks_agent_oversight"
NAME = "an_agents_steward_is_told_that_others_conversations_happened"


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


def test_the_oversight_check_is_listed_with_the_leaves_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M39.11.1", "M39.11.2")


@pytest.mark.needs_db
def test_on_a_real_database_a_steward_is_told_and_a_colleague_is_not_and_nothing_is_left() -> None:
    """**The check as the worker runs it**, over a schema carrying `0227`'s policy. Delete this and
    the policy, the route and the page can stop agreeing with nothing on an install saying so."""
    with at_head("brain_acceptance_agent_oversight") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _tells_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_conversation_routes as routes

    monkeypatch.setattr(routes, "oversees", lambda _record, _asked: False)


def _tells_everybody(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_conversation_routes as routes

    monkeypatch.setattr(routes, "oversees", lambda _record, _asked: True)


BREAKS: dict[str, tuple[Any, str]] = {
    "tells_nobody": (_tells_nobody, "STEWARD_NOT_TOLD"),
    "tells_everybody": (_tells_everybody, "A_COLLEAGUE_WAS_TOLD"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_oversight_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found. Delete this and the check can pass over a
    steward told nothing or a colleague told who used an agent they do not look after."""
    import brain.ops.acceptance_checks_agent_oversight as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_agent_oversight_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
