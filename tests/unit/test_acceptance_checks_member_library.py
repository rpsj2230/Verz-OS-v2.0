"""The member library install check, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.3.1.2
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_library"
CYCLE = "a_member_adds_a_document_with_a_review_cycle_and_retires_it"


def test_the_module_declares_its_leaf_and_sits_in_its_range() -> None:
    """One check closing M40.3.1.2 inside the range the member package was given. Delete this and
    the check can lose its leaf with the page showing the same row."""
    from brain.ops import acceptance_checks_member_library as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CYCLE, ("M40.3.1.2",))]
    assert checks_in(MODULE) == [CYCLE]
    assert 1900 <= module.CHECK_ORDER <= 1999


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_library") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str) -> str:
    outcome, reason = run(url)[CYCLE]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_library_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: it passes and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a document, ships."""
    before = counts(install)
    assert run(install) == {CYCLE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_upload_that_drops_the_review_cycle_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The date asked for at upload is not set on the item. Delete this and M40.3.1.2 closes on an
    upload that accepts a review cycle and leaves the document outside the sweep."""
    from brain.knowledge import uploads

    monkeypatch.setattr(uploads, "with_review_by", lambda read, review_by: read)
    assert "cycle they asked for" in _failed(install)


@pytest.mark.needs_db
def test_an_upload_that_stores_a_different_date_from_the_cycle_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cycle is stored a day late. Delete this and M40.3.1.2 closes on an upload that keeps
    some date and not the one the member asked for."""
    from datetime import timedelta

    from brain.knowledge import uploads

    real = uploads.with_review_by

    def a_day_late(read: Any, review_by: Any) -> Any:
        return real(read, review_by + timedelta(days=1))

    monkeypatch.setattr(uploads, "with_review_by", a_day_late)
    assert "other than the cycle asked for" in _failed(install)


@pytest.mark.needs_db
def test_a_colleague_who_can_retire_a_departments_document_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority stops deciding who may act, so any reader of the department may withdraw a
    document the member added to it. Delete this and M40.3.1.2 closes on a retire that is open to
    anybody who can read the document."""
    from brain.knowledge.lifecycle import Authority

    def anybody(self: Any, *args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(Authority, "may_act", anybody)
    assert "only reads a department" in _failed(install)


@pytest.mark.needs_db
def test_a_retire_that_leaves_the_document_listed_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: the member's retire answers and writes nothing. Delete this and a
    retire that does nothing satisfies the checks that only look for who may not."""
    from brain import knowledge_lifecycle_routes as routes

    async def nothing(session: Any, item: Any) -> None:
        return None

    monkeypatch.setattr(routes, "record_archive", nothing)
    assert "still on its member's list" in _failed(install)


@pytest.mark.needs_db
def test_a_retire_that_fails_for_a_departments_document_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database refuses the withdrawal of the document added to the department, which the
    route reports as a refusal and not as an absence. Delete this and M40.3.1.2 closes on a member
    whose retire of a shared document is answered and does nothing."""
    from brain.knowledge.lifecycle_store import LifecycleStoreError, record_archive
    from brain.knowledge.visibility import Visibility

    async def refuses_shared(session: Any, item: Any) -> None:
        if item.visibility.level is Visibility.DEPARTMENT:
            raise LifecycleStoreError("refused")
        await record_archive(session, item)

    monkeypatch.setattr("brain.knowledge_lifecycle_routes.record_archive", refuses_shared)
    assert "retire the department's document" in _failed(install)
