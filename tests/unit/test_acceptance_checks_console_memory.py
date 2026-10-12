"""The install check for the Memory screen's history, passing on PostgreSQL at head, leaving
nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.7.22
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_memory"
HISTORY = "memory_history_shows_an_edit_and_hides_what_is_not_recallable"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The check and the leaf it closes. Delete this and the check can lose M27.7.22, or gain a
    leaf it does not prove, with the screen unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {HISTORY: ("M27.7.22",)}
    assert checks_in(MODULE) == [HISTORY]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_memory") as url:
        yield url


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[HISTORY]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no memory, person or ledger entry.
    Delete this and a check that commits, or one that cannot pass on a real schema, reaches the
    owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {HISTORY: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_viewer_whose_history_leaves_out_an_edit_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A history that forgets the steps. Delete this and M27.7.22 closes on a viewer that shows the
    current words and no change history, which is the half of the leaf nothing else watches."""
    from brain.console.govern_estate import subject_memory as real

    def forgetting(**kwargs: Any) -> Any:
        return dataclasses.replace(real(**kwargs), history=())

    monkeypatch.setattr("brain.estate_routes.subject_memory", forgetting)
    assert "history did not show the edit" in _failed(install)


@pytest.mark.needs_db
def test_a_viewer_that_answers_a_person_without_the_screen_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen's read ignored. Delete this and a person with no Memory screen could be answered
    and M27.7.22 would still close."""
    from brain import estate_routes

    monkeypatch.setattr(estate_routes, "permitted", lambda *args, **kwargs: True)
    assert "without the Memory screen" in _failed(install)
