"""The correction check: registered, passing on a real schema, and able to fail.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_templates import run_checks

MODULE = "brain.ops.acceptance_checks_corrections"
NAMED = "a_correction_is_held_grouped_and_decided_as_a_new_version"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_correction_check_is_listed() -> None:
    """The one check this module registers. Delete this and it can drop out of the page."""
    assert checks_in(MODULE) == [NAMED]
    assert MODULE in check_modules()


@pytest.mark.needs_db
def test_on_a_real_database_the_correction_check_passes_and_leaves_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** Delete this and a
    correction can stop reaching its steward with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_corrections") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAMED: (PASSED, "")}
    assert after == before


def _nothing_proposed(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.thread_routes as routes

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(routes, "propose", nothing)


def _ungrouped(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.knowledge.candidate_store as store
    from brain.knowledge.candidates import group_key as real

    counter = iter(range(1, 1_000))
    # Letters, not digits: the words' key reads letters alone, so a digit would group again.
    monkeypatch.setattr(
        store, "group_key", lambda item, words: real(item, f"{words} {'z' * next(counter)}")
    )


def _proposer_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.knowledge.candidate_store as store

    monkeypatch.setattr(store, "may_decide", lambda candidate, item, by: by.may_act(item))


def _no_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.candidate_routes as routes

    monkeypatch.setattr(routes, "audience", lambda place: "")


def _not_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    import brain.knowledge.candidate_store as store

    async def nowhere(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(store, "write_version", nowhere)


BREAKS: dict[str, tuple[Any, str]] = {
    "nothing_proposed": (_nothing_proposed, "NOT_HELD"),
    "ungrouped": (_ungrouped, "NOT_GROUPED"),
    "proposer_decides": (_proposer_decides, "SHOWN_TO_ITS_PROPOSER"),
    "no_audience": (_no_audience, "NO_AUDIENCE"),
    "not_applied": (_not_applied, "NOT_APPLIED"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_correction_check_fails_where_the_product_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: nothing proposed,
    the same fix not grouped, a proposer let decide, the audience not shown, and an approval that
    writes no version. Delete this and the check can pass with any of those gone."""
    import brain.ops.acceptance_checks_corrections as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    with at_head(f"brain_acceptance_corrections_{broken}") as url:
        outcome = run_checks(url, (mine()[NAMED],))
    assert outcome[NAMED] == (FAILED, getattr(module, reason))


@pytest.mark.needs_db
def test_the_database_refuses_a_proposer_s_decision_when_the_python_rule_is_let_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The second wall.** With `may_decide` letting anybody who may add a version decide inside
    `decide`, the administrator whose correction the candidate holds is still refused, by
    `0198`'s update policy alone, and the check passes.

    Delete this and the database's half of the four-eyes rule, which
    `NOBODY_WHOSE_CORRECTION_IT_HOLDS_MAY_APPROVE_IT` says is there, is reached by no test: every
    other test stops a proposer in Python first."""
    import contextvars

    import brain.knowledge.candidate_store as store

    deciding = contextvars.ContextVar("deciding", default=False)
    from brain.knowledge.candidates import may_decide as real_rule

    real_decide = store.decide

    def rule(candidate: Any, item: Any, by: Any) -> bool:
        return bool(by.may_act(item)) if deciding.get() else real_rule(candidate, item, by)

    async def decide(*args: Any, **kwargs: Any) -> Any:
        # Reset on the way out: an awaited coroutine shares its caller's context, so a flag left
        # set would let the next read through and the check would fail on the wrong wall.
        token = deciding.set(True)
        try:
            return await real_decide(*args, **kwargs)
        finally:
            deciding.reset(token)

    monkeypatch.setattr(store, "may_decide", rule)
    monkeypatch.setattr(store, "decide", decide)
    import brain.candidate_routes as routes

    monkeypatch.setattr(routes, "decide", decide)
    with at_head("brain_acceptance_corrections_second_wall") as url:
        outcome = run_checks(url, (mine()[NAMED],))
    assert outcome == {NAMED: (PASSED, "")}
