"""The cost-hold check: registered, passing on a real schema, and able to fail (M20.5.2).

The breaks put back, one at a time, the four ways the hold goes wrong: never holding, holding while
its switch is off, holding an agent that is within its ceiling, and a publish record that carries no
cost.

Task ids: M20.5.2
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    PASSED,
    REASON_CHARS,
    SENTENCE_CHARS,
    Check,
    check_modules,
    registered,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_publish_cost"
NAME = "a_costly_publish_waits_for_a_colleague_in_the_department"


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


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_cost_hold_check_is_listed_with_the_leaf_it_proves() -> None:
    """The one check this module registers, naming M20.5.2 alone and found by the suite, with a
    sentence that fits the Install page. Delete this and the check can drop out of its module or
    close a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M20.5.2",)
    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS


def test_every_reason_the_cost_hold_check_can_give_is_a_named_literal_that_fits_the_page() -> None:
    """Each failure sentence is a module constant that fits the result's column. Delete this and a
    reason can be cut off on the page, or built from a row the check read."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_publish_cost as module

    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CheckFailedError":
            [argument] = node.args
            assert isinstance(argument, ast.Name)
            reasons.append(getattr(module, argument.id))
    assert len(reasons) == 9
    assert len(set(reasons)) == 9
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


@pytest.mark.needs_db
def test_on_a_real_database_a_costly_publish_waits_for_a_colleague_and_nothing_is_kept() -> None:
    """**The check as the worker runs it.** It passes, and the agents, people, budget versions and
    the switch it wrote are gone. Delete this and the hold can stop working on an install with
    nothing saying so, or the check can leave a ceiling on the owner's department."""
    with at_head("brain_acceptance_publish_cost") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _never_held(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    monkeypatch.setattr(routes, "cost_hold", lambda manifest, **kept: None)


def _held_while_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes

    async def on(sessions: Any) -> bool:
        return True

    monkeypatch.setattr(routes, "cost_hold_is_on", on)


def _held_within_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.run_cost import cost_hold

    def always(manifest: Any, *, department: str | None, ceiling_minor: int | None) -> Any:
        return cost_hold(
            manifest, department=department, ceiling_minor=1 if ceiling_minor else None
        )

    monkeypatch.setattr(routes, "cost_hold", always)


def _held_without_a_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_builder_routes as routes
    from brain.builder.run_cost import cost_hold

    def zero(manifest: Any, *, department: str | None, ceiling_minor: int | None) -> Any:
        return cost_hold(
            manifest,
            department=department,
            ceiling_minor=0 if ceiling_minor is None else ceiling_minor,
        )

    monkeypatch.setattr(routes, "cost_hold", zero)


def _no_cost_on_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.builder.publish as publish

    monkeypatch.setattr(publish, "cost_of_document", lambda document: None)


BREAKS: dict[str, tuple[Any, str]] = {
    "never_held": (_never_held, "NOT_HELD"),
    "held_while_off": (_held_while_off, "HELD_WHILE_OFF"),
    "held_within_the_ceiling": (_held_within_the_ceiling, "HELD_WITHIN_THE_CEILING"),
    "held_without_a_ceiling": (_held_without_a_ceiling, "HELD_WITH_NO_CEILING"),
    "no_cost_on_the_record": (_no_cost_on_the_record, "NO_COST_ON_THE_RECORD"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_cost_hold_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Five breaks: a hold that never fires, one that fires with its switch off, one that fires on
    an agent within its ceiling, one that fires where no ceiling was set, and a record without a
    cost. Each fails with its own sentence.
    Delete this and the check can pass with the hold gone or applied to everything."""
    import brain.ops.acceptance_checks_publish_cost as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_publish_cost_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
