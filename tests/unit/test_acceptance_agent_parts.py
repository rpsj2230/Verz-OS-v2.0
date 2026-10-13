"""The agent-parts check: registered, passing on a real schema, and able to fail.

Run as the worker would, then against the product broken where it proves: a part dropped from the
list, a persona that can be attached, and a page that does not show the tool.

Task ids: M39.1.1.1
"""

from __future__ import annotations

import asyncio
import enum
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_agent_parts"
NAME = "an_agent_is_composed_of_twelve_parts_with_tools_and_workflows"


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


def test_the_agent_parts_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M39.1.1.1",)


@pytest.mark.needs_db
def test_on_a_real_database_the_twelve_parts_hold_and_nothing_is_left() -> None:
    """**The check as the worker runs it.** Delete this and a part of an agent can go missing from
    the enum, or the page stop showing a tool an agent carries, with nothing on an install saying
    so."""
    with at_head("brain_acceptance_agent_parts") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _loses_the_workflows_part(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.console.workspace as workspace

    class Fewer(enum.StrEnum):
        PERSONA = "persona"

    monkeypatch.setattr(workspace, "Part", Fewer)


def _lets_a_persona_be_attached(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.console.workspace as workspace

    monkeypatch.setattr(workspace, "PINNED_PARTS", frozenset(workspace.Part))


def _hides_the_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_routes as routes

    monkeypatch.setattr(routes, "profile_view", lambda *_args, **_kwargs: None)


BREAKS: dict[str, tuple[Any, str]] = {
    "loses_a_part": (_loses_the_workflows_part, "NOT_TWELVE"),
    "attaches_a_persona": (_lets_a_persona_be_attached, "A_PERSONA_WAS_ATTACHED"),
    "hides_the_tools": (_hides_the_tools, "THE_TOOL_WAS_NOT_SHOWN"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_agent_parts_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found. Delete this and the check can pass over a part
    quietly dropped, a second persona accepted, or a tool the page does not show."""
    import brain.ops.acceptance_checks_agent_parts as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_agent_parts_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
