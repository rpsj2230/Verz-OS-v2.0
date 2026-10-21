"""The coverage install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M34.1.1.1, M34.1.1.2, M34.1.1.3, M34.1.2.1, M34.1.2.2, M34.1.2.3
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_adoption"
COVERAGE = "a_department_is_told_what_is_connected_for_it_alone"
LEAVES = ("M34.1.1.1", "M34.1.1.2", "M34.1.1.3", "M34.1.2.1", "M34.1.2.2", "M34.1.2.3")


def test_the_module_declares_its_leaves_and_sits_in_its_range() -> None:
    """One check closing the coverage leaves, placed on the Install page. Delete this and the check
    can lose a leaf with the page showing the same row, or share a key with another."""
    from brain.ops import acceptance_checks_adoption as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(COVERAGE, LEAVES)]
    assert checks_in(MODULE) == [COVERAGE]
    assert module.CHECK_ORDER == 2700


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_adoption") as url:
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
def test_the_coverage_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind, the connection, the
    attempt and the index rows included. Delete this and a check that cannot pass on a real schema,
    or one that commits a connection, ships."""
    before = counts(install)
    assert run(install) == {COVERAGE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_statement_that_shows_every_department_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reach replaced by every department. Delete this and the leaves close on a coverage
    statement that tells a department lead about departments they may not read."""
    from brain.console import adoption_coverage

    monkeypatch.setattr(
        adoption_coverage,
        "reachable_departments",
        lambda departments, entitlement, *, now: frozenset(departments),
    )
    assert "may not read usage" in _failed(install)


@pytest.mark.needs_db
def test_a_statement_that_names_a_source_the_reader_may_not_be_told_of_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every connection treated as one the reader may name. Delete this and the leaves close on a
    coverage line that tells a department lead what the company runs."""
    from brain.console import adoption_coverage

    monkeypatch.setattr(
        adoption_coverage,
        "admitted_connections",
        lambda connections, entitlement, now=None: tuple(connections),
    )
    assert "dropped or named" in _failed(install)


@pytest.mark.needs_db
def test_questions_about_records_the_person_cannot_read_fail_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person's reach on a kind of record not asked. Delete this and the leaves close on Ask
    suggesting a kind of record the person cannot reach."""
    from brain.console import adoption_coverage

    def anything(entity: str, entitlement: Any, now: Any, place: Any) -> bool:
        return True

    monkeypatch.setattr(adoption_coverage, "_may_ask_about", anything)
    assert "records they may not read" in _failed(install)
