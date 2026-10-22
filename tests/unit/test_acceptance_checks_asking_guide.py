"""The asking guide install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M34.3.1.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_asking_guide"
GUIDE = "staff_are_served_the_asking_guide_with_their_own_examples"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check closing M34.3.1.3, placed after the adoption check it borrows its setup from.
    Delete this and the check can lose its leaf with the page showing the same row."""
    from brain.ops import acceptance_checks_adoption as adoption
    from brain.ops import acceptance_checks_asking_guide as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(GUIDE, ("M34.3.1.3",))]
    assert checks_in(MODULE) == [GUIDE]
    assert module.CHECK_ORDER > adoption.CHECK_ORDER
    assert module.SOURCE == adoption.SOURCE


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_asking_guide") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    outcome, reason = run(url)[GUIDE]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_guide_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that leaves a connection, ships."""
    before = counts(install)
    assert run(install) == {GUIDE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_guide_that_offers_every_reader_the_same_question_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The examples no longer follow the reader's reach, so a person who may not read tickets is
    offered a question about them. Delete this and M34.3.1.3 closes on a guide that teaches staff
    to ask about records they cannot reach."""
    from brain import welcome_routes

    async def the_same_for_all(request: Any, asked: Any) -> Any:
        one = welcome_routes.StarterFromDataView(
            question="How many ticket are there?", check_in="Freshdesk"
        )
        return welcome_routes.WelcomeFromDataView(questions=[one])

    monkeypatch.setattr(welcome_routes, "welcome_from_data", the_same_for_all)
    assert "records they may not read" in _failed(install)


@pytest.mark.needs_db
def test_a_guide_that_serves_nothing_for_a_member_who_may_read_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: the member is always shown the sentence for nothing indexed. Delete
    this and a guide that never shows any example satisfies the check that only looks for leaks."""
    from brain import welcome_routes

    async def nothing(request: Any, asked: Any) -> Any:
        return welcome_routes.WelcomeFromDataView(questions=[])

    monkeypatch.setattr(welcome_routes, "welcome_from_data", nothing)
    assert "not served a question about the records they read" in _failed(install)


@pytest.mark.needs_db
def test_a_guide_that_keeps_the_shipped_pages_working_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker from the shipped page left in what is served. Delete this and M34.3.1.3 closes on a
    page that shows staff the demo company's tables or this repository's tests."""
    from brain.ops import guide_docs

    real = guide_docs.served_asking_guide

    def leaking(page: str, *, examples: Any) -> str:
        return real(page, examples=examples) + "\n<!-- checked: examples from operations -->\n"

    monkeypatch.setattr(guide_docs, "served_asking_guide", leaking)
    assert "own working" in _failed(install)


@pytest.mark.needs_db
def test_a_guide_that_ignores_the_switch_for_questions_built_from_data_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as always on. Delete this and M34.3.1.3 closes on a guide that offers
    questions built from an install's data before the install has chosen to."""
    from brain import welcome_routes

    async def always(request: Any) -> bool:
        return True

    monkeypatch.setattr(welcome_routes, "starter_from_data_is_on", always)
    assert "while their switch was off" in _failed(install)
