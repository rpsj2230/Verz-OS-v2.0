"""The memory-kinds check: registered, passing on a real schema, and able to fail.

Run as the worker would, then against the product broken where it proves: a colleague who may change
what an agent remembers, a setting the run does not obey, and a kind put back that is not shown.

Task ids: M39.7.1
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

MODULE = "brain.ops.acceptance_checks_agent_memory_kinds"
NAME = "an_agent_leaves_out_a_kind_of_memory_and_no_run_is_shown_it"


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


def test_the_memory_kinds_check_is_listed_with_the_leaf_it_proves() -> None:
    """Delete this and the check can drop out of the module, or claim a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M39.7.1",)


@pytest.mark.needs_db
def test_on_a_real_database_a_kind_left_out_is_kept_and_obeyed_and_nothing_is_left() -> None:
    """**The check as the worker runs it**, over a schema carrying `0228`. Delete this and the
    column, the route and the assembler can stop agreeing with nothing on an install saying so."""
    with at_head("brain_acceptance_memory_kinds") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _anybody_may_change_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_memory_kinds_routes as routes

    monkeypatch.setattr(routes, "may_change_channels", lambda _record, _asked: True)


def _the_run_ignores_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.gate.turn_context as context

    real = context.assemble

    async def ignoring(*args: Any, **kwargs: Any) -> Any:
        kwargs["kinds"] = None
        return await real(*args, **kwargs)

    monkeypatch.setattr(context, "assemble", ignoring)


BREAKS: dict[str, tuple[Any, str]] = {
    "anybody_may_change_it": (_anybody_may_change_it, "A_COLLEAGUE_CHANGED_IT"),
    "run_ignores_it": (_the_run_ignores_the_setting, "READ_WHAT_WAS_LEFT_OUT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_memory_kinds_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Each way the product can be wrong is found. Delete this and the check can pass over a kind
    anybody may switch, or a setting no run obeys."""
    import brain.ops.acceptance_checks_agent_memory_kinds as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_memory_kinds_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
