"""The install check for archiving a document, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.40
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_archive"
ARCHIVE = "a_document_is_archived_and_nothing_answers_from_it_afterwards"


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """The check and the leaf it closes. Delete this and the check can lose M27.15.40, or gain a
    leaf it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {ARCHIVE: ("M27.15.40",)}
    assert checks_in(MODULE) == [ARCHIVE]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_archive") as url:
        yield url


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no document, passage, person,
    grant or ledger entry. Delete this and a check that commits, or one that cannot pass on a real
    schema, reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {ARCHIVE: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_archive_that_moves_nothing_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive press changing nothing. Delete this and M27.15.40 closes on a page whose Archive
    button does nothing, which is a withdrawn document still answering."""
    from brain.knowledge import lifecycle_store

    async def nothing(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(lifecycle_store, "record_archive", nothing)
    outcome, reason = run_module(install, MODULE)[ARCHIVE]
    assert outcome == FAILED
    assert "still among the live items" in reason


@pytest.mark.needs_db
def test_an_archive_open_to_a_plain_reader_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority rule answering yes to everybody. Delete this and the refusal half of the check
    can be dropped, after which a route that archives for a reader still closes the leaf."""
    from brain.knowledge.lifecycle import Authority

    monkeypatch.setattr(Authority, "may_act", lambda self, item: True)
    outcome, reason = run_module(install, MODULE)[ARCHIVE]
    assert outcome == FAILED
    assert "neither stewards nor administers" in reason
