"""The publication-reach check: registered, passing on a real schema, and able to fail (M20.5.1).

Each break puts back one of the doors the leaf closes: the agent publication that asked only for the
capability in any scope, the promotion approval that did the same, the queue that offered a company
request to a department's administrator, the queue that showed one department another's request, and
the skill library that a department's administrator could decide about.

Task ids: M20.5.1
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

MODULE = "brain.ops.acceptance_checks_publication_reach"
NAME = "a_department_admin_decides_only_for_their_department"


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


def test_the_reach_check_is_listed_with_the_leaf_it_proves() -> None:
    """The one check this module registers, naming M20.5.1 alone and found by the suite, with a
    sentence that fits the Install page. Delete this and the check can drop out of its module or
    close a leaf it does not prove."""
    assert checks_in(MODULE) == [NAME]
    assert MODULE in check_modules()
    assert mine()[NAME].leaves == ("M20.5.1",)
    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS


def test_every_reason_the_reach_check_can_give_is_a_named_literal_that_fits_the_page() -> None:
    """Each failure sentence is a module constant that fits the result's column. Delete this and a
    reason can be cut off on the page, or built from a row the check read."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_publication_reach as module

    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CheckFailedError":
            [argument] = node.args
            assert isinstance(argument, ast.Name)
            reasons.append(getattr(module, argument.id))
    assert len(reasons) == 10
    assert len(set(reasons)) == 10
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


@pytest.mark.needs_db
def test_on_a_real_database_the_company_waits_for_a_super_admin_and_nothing_is_kept() -> None:
    """**The check as the worker runs it.** It passes, and the agents, people and requests it made
    are gone. Delete this and publishing at a reach can stop being decided by the right person on
    an install with nothing saying so, or the check can leave an agent on the owner's install."""
    with at_head("brain_acceptance_publication_reach") as url:
        before = counts(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _as_before_the_agent_door(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.agent_lifecycle_routes as routes
    import brain.agents.lifecycle as lifecycle

    # The route asks the console's question first and the domain's second, so both are put back.
    monkeypatch.setattr(routes, "may_publish", lambda reach, now: True)
    monkeypatch.setattr(lifecycle, "holds_for_level", lambda *a, **k: True)


def _as_before_the_promotion_door(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.knowledge.visibility as visibility

    real = visibility.holds_for_level

    def only_for_a_department(
        entitlement: Any, capability: Any, level: Any, now: Any, **rest: Any
    ) -> bool:
        if level is visibility.Visibility.COMPANY:
            return entitlement.scope_for(capability, now) is not None
        return real(entitlement, capability, level, now, **rest)

    monkeypatch.setattr(visibility, "holds_for_level", only_for_a_department)


def _as_before_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.console.global_surfaces as surfaces

    monkeypatch.setattr(surfaces, "may_approve_publication", lambda placed, reach, now: True)


def _as_before_the_skill_library(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.console.skill_library as library

    monkeypatch.setattr(library, "may_review", lambda reach, now: True)


BREAKS: dict[str, tuple[Any, str]] = {
    "agent_door": (_as_before_the_agent_door, "AN_AGENT_WAS_PUBLISHED_ALONE"),
    "promotion_door": (_as_before_the_promotion_door, "A_DEPARTMENT_ADMIN_APPROVED_THE_COMPANY"),
    "queue": (_as_before_the_queue, "THE_QUEUE_OFFERED_THE_COMPANY"),
    "skill_library": (_as_before_the_skill_library, "A_DEPARTMENT_ADMIN_REVIEWED_A_SKILL"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_reach_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each putting one door back as it was: the agent's publication, the knowledge
    promotion, the publication queue and the skill library, each admitting a department's
    administrator to a decision at a wider reach. Each fails with its own sentence. Delete this and
    the check can pass with a door left open."""
    import brain.ops.acceptance_checks_publication_reach as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_publication_reach_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, getattr(module, reason))
