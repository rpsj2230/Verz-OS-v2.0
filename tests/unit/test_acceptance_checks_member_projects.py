"""The member project install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.7.7
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_projects"
PROJECT = "a_member_asks_inside_a_project_and_it_reads_what_they_may_read"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check closing M40.7.7, inside the range the member packages were given. Delete this and
    the check can lose its leaf with the page showing the same row, or share a key with another."""
    from brain.ops import acceptance_checks_member_projects as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(PROJECT, ("M40.7.7",))]
    assert checks_in(MODULE) == [PROJECT]
    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_projects") as url:
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
def test_the_project_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a project, ships."""
    before = counts(install)
    assert run(install) == {PROJECT: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_switch_that_is_not_asked_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch answered yes whatever the install says. Delete this and M40.7.7 closes on
    routes that make projects on an install that never turned them on."""
    from brain import project_routes

    async def always(_sessions: Any) -> bool:
        return True

    monkeypatch.setattr(project_routes, "projects_are_on", always)
    assert "switch was off" in _failed(install)


@pytest.mark.needs_db
def test_listing_a_document_without_asking_whether_it_can_be_read_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reader at the person's reach replaced by one that finds a passage in anything. Delete
    this and M40.7.7 closes on a project that lists documents its owner may not read."""
    from brain import project_routes

    class Found:
        records = ("a passage",)

    def anything(_records: Any) -> Any:
        async def read(*_args: Any, **_kwargs: Any) -> Found:
            return Found()

        return read

    monkeypatch.setattr(project_routes, "reader", anything)
    assert "could not read" in _failed(install)


@pytest.mark.needs_db
def test_a_project_file_read_at_somebody_elses_reach_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The document tool handed the first reach it was ever given, whoever asks. Delete this and
    M40.7.7 closes on a reader that has stopped deciding at the reach of the run."""
    from brain import project_context

    real = project_context.project_file_handler
    first: list[Any] = []

    def sticky(registry: Any) -> Any:
        read = real(registry)
        assert read is not None

        async def reading(document_id: str, *, entitlement: Any, now: Any = None) -> Any:
            first.append(entitlement)
            return await read(document_id, entitlement=first[0], now=now)

        return reading

    monkeypatch.setattr(project_context, "project_file_handler", sticky)
    assert "someone who could not read it" in _failed(install)
