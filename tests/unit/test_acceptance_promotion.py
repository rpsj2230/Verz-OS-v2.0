"""The learned rule promotion check: registered, passing on a real schema, and able to fail.

Task ids: M39.4.2.3
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_promotion"
NAMED = "a_learned_rule_is_promoted_once_conversations_agree"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_promotion_check_is_listed() -> None:
    """The one check this module registers. Delete this and it can drop out of the page."""
    assert checks_in(MODULE) == [NAMED]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_promotion_check_passes_and_leaves_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and a learned
    rule can stop being counted, pressed or applied with nothing on an install saying so."""
    with at_head("brain_acceptance_promotion") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAMED: (PASSED, "")}
    assert after == before


def _nothing_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.memory.promotion_store as store

    async def nothing(*args: Any, **kwargs: Any) -> tuple[str, ...]:
        return ()

    monkeypatch.setattr(store.StoredLearnedRules, "count_occurrence", nothing)


def _always_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.promotion_routes as routes

    monkeypatch.setattr(routes, "may_promote", lambda *args, **kwargs: True)


def _anybody_presses(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.promotion_routes as routes

    monkeypatch.setattr(routes, "may_promote_where", lambda *args, **kwargs: True)


def _never_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.memory.promotion_store as store
    from brain.memory.promotion import Pressed, PromotionState

    def held(learned: Any, *, by: str, ready: bool, two: bool) -> Pressed:
        return Pressed(PromotionState.AWAITING_SECOND, True, by, None, "")

    monkeypatch.setattr(store, "press", held)


def _one_person_for_money(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.promotion_routes as routes

    monkeypatch.setattr(routes, "needs_two", lambda **kwargs: False)


BREAKS: dict[str, tuple[Any, str]] = {
    "nothing_counted": (_nothing_counted, "NOT_COUNTED"),
    "always_ready": (_always_ready, "PROMOTED_UNREADY"),
    "anybody_presses": (_anybody_presses, "PRESSED_ELSEWHERE"),
    "never_applied": (_never_applied, "NOT_APPLIED"),
    "one_person_for_money": (_one_person_for_money, "ONE_PERSON_FOR_MONEY"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_promotion_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: nothing counted, a
    press admitted before agreement, a press admitted anywhere, a promotion that applies nothing,
    and a confidential rule taking one person. Delete this and the check can pass with any of
    those gone."""
    import brain.ops.acceptance_checks_promotion as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_promotion_{broken}") as url:
        outcome = run_checks(url, (mine()[NAMED],))
    assert outcome[NAMED] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_the_database_refuses_a_proposers_press_when_the_python_rule_lets_it_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The second wall.** With `promotion.press` letting the proposer through, `0206`'s check
    refuses the proposer's promotion and the press is answered as refused, so the check passes.

    Delete this and `NOBODY_PROMOTES_WHAT_THEY_PROPOSED`'s database half is reached by no test."""
    import brain.memory.promotion_store as store
    from brain.memory.promotion import press as real

    def blind(learned: Any, *, by: str, ready: bool, two: bool) -> Any:
        from dataclasses import replace

        return real(replace(learned, proposed_by=None), by=by, ready=ready, two=two)

    monkeypatch.setattr(store, "press", blind)
    with at_head("brain_acceptance_promotion_second_wall") as url:
        outcome = run_checks(url, (mine()[NAMED],))
    assert outcome == {NAMED: (PASSED, "")}
