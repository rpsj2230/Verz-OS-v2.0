"""The thread states install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.7.6
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_thread_states"
STATES = "each_recent_conversation_says_where_its_run_has_got_to"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check closing M40.7.6, inside the range the member packages were given. Delete this
    and the check can lose its leaf with the page showing the same row, or share a key."""
    from brain.ops import acceptance_checks_thread_states as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(STATES, ("M40.7.6",))]
    assert checks_in(MODULE) == [STATES]
    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_thread_states") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    [(outcome, reason)] = run(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_thread_states_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a row, ships."""
    before = counts(install)
    assert run(install) == {STATES: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_switch_that_is_not_asked_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch answered yes whatever the install says. Delete this and M40.7.6 closes on a list
    that reads three more tables on an install that never turned it on."""
    from brain import thread_routes

    async def always(_sessions: Any) -> bool:
        return True

    monkeypatch.setattr(thread_routes, "thread_states_are_on", always)
    assert "while the switch was off" in _failed(install)


@pytest.mark.needs_db
def test_a_rule_that_ignores_a_held_action_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state decided from the answer's own run state alone. Delete this and M40.7.6 closes on
    a list that calls a run done while it waits for a colleague."""
    from brain import thread_routes
    from brain.member_task_state import RunFacts, TaskState
    from brain.tables.chat import RunState

    def ignoring(facts: RunFacts) -> TaskState:
        return TaskState.FAILED if facts.run_state is RunState.FAILED else TaskState.DONE

    monkeypatch.setattr(thread_routes, "state_of", ignoring)
    assert "waiting" in _failed(install)


@pytest.mark.needs_db
def test_a_store_that_reads_anybody_s_approval_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store asked for suspensions by request alone, naming nobody. Delete this and M40.7.6
    closes on a list that takes its state from a colleague's approval on the same request."""
    from sqlalchemy import select as real_select

    from brain.tables.suspension import SuspensionRow

    def select(*columns: Any) -> Any:
        chosen = real_select(*columns)
        if columns and columns[0] is SuspensionRow.trace_id:
            original = chosen.where

            def where(*clauses: Any) -> Any:
                kept = [one for one in clauses if "principal_id" not in str(one)]
                return original(*kept)

            chosen.where = where  # type: ignore[method-assign]
        return chosen

    monkeypatch.setattr("brain.ops.task_state_store.select", select)
    assert "another person's approval" in _failed(install)
