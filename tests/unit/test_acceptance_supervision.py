"""The install checks for a pin's thirty-day review and the Leash screen's date, each passing on
PostgreSQL at head and each failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M13.5.18, M13.8.13
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_supervision"
REVIEW = "the_chasers_pin_is_reviewed_at_thirty_days_and_never_lapses"
SCREEN = "the_leash_screen_shows_when_a_pin_ends_and_when_it_has_come"


def test_the_module_declares_a_check_for_each_leaf_it_proves() -> None:
    """Two checks, each closing its own leaf. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REVIEW, ("M13.5.18",)),
        (SCREEN, ("M13.8.13",)),
    ]
    assert checks_in(MODULE) == [REVIEW, SCREEN]


def test_a_pin_is_thirty_days_in_the_check_and_in_the_product_alike() -> None:
    """The check writes thirty days out and the product's review period is held to the same
    figure written in the check. Delete this and the check's thirty can stop being the product's."""
    from brain.agents.supervision import SHADOW_REVIEW_PERIOD
    from brain.ops import acceptance_checks_supervision as module

    assert module.THIRTY_DAYS == SHADOW_REVIEW_PERIOD
    assert module.PINNED_THIRTY_ONE_DAYS_AGO > module.THIRTY_DAYS
    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_supervision") as url:
        yield url


def run_supervision(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_supervision(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_both_supervision_checks_pass_on_an_install_and_leave_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and nothing a check wrote is left: no agent,
    pin, template version or switch. Delete this and a check that can never pass on a real schema,
    or one that leaves a pin behind, reaches the owner's server."""
    before = counts(install)
    outcomes = run_supervision(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_pass_that_releases_a_pin_because_a_date_passed_fails_the_review_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review answering eligible for every due pin. Delete this and M13.5.18 closes on a pin
    that lapses because a date went by."""
    from brain.ops import supervision_review
    from brain.tables.leash import PinOutcome

    real = supervision_review.answer_review

    def released(state: Any, *, now: Any) -> Any:
        found = real(state, now=now)
        if isinstance(found, supervision_review.Answer):
            return replace(found, outcome=PinOutcome.ELIGIBLE)
        return found

    monkeypatch.setattr(supervision_review, "answer_review", released)
    assert "not extended" in _failed(install, REVIEW)


@pytest.mark.needs_db
def test_a_pass_that_writes_with_its_switch_off_fails_the_review_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as on whatever it says. Delete this and M13.5.18 closes on a review that
    acts before the owner has seen what it would do."""
    from brain.ops.supervision_review import StoredReviews

    async def on(self: Any) -> bool:
        return True

    monkeypatch.setattr(StoredReviews, "switched_on", on)
    assert "switch was off" in _failed(install, REVIEW)


@pytest.mark.needs_db
def test_a_leash_screen_that_shows_no_pin_fails_the_screen_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pin dropped from the screen's answer. Delete this and M13.8.13 closes on a screen that
    never says when a pin ends."""
    from brain import agent_leash_routes

    monkeypatch.setattr(agent_leash_routes, "supervision_view", lambda state, now: None)
    assert "showed no pin" in _failed(install, SCREEN)


@pytest.mark.needs_db
def test_a_leash_screen_open_to_a_reader_without_the_settings_tab_fails_the_screen_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Settings tab's read given to every reader. Delete this and M13.8.13 closes on a leash
    shown to somebody who may not open the agent's settings."""
    from brain import agent_leash_routes

    monkeypatch.setattr(agent_leash_routes, "may_read_settings", lambda asked: True)
    assert "without the Settings tab" in _failed(install, SCREEN)
