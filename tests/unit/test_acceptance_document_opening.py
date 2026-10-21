"""The install check for opening another department's document, passing on PostgreSQL and failing
when the route stops writing the entry or starts writing one for every opening.

The pure half holds the module's shape. The database half runs the check as the worker would, over
a database at head, and then runs it again with the route's rule broken in each direction, because a
check shown only passing is satisfied by one that cannot fail.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_document_opening"
CHECK = "opening_another_departments_document_leaves_an_entry"


def test_the_module_declares_one_check_naming_the_one_leaf() -> None:
    """Delete this and the check can name another leaf too, so its failure holds a leaf it does not
    prove, or drop the leaf from the Install page without a test going red."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {CHECK: ("M27.15.1",)}
    assert checks_in(MODULE) == [CHECK]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """A database at head, as the application leaves it. Nothing is furnished for this check."""
    with at_head("brain_acceptance_document_opening") as url:
        yield url


def run_check(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    [one] = results
    return one.outcome, one.reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """The route as it ships: one entry for the reader across the line, none inside the department,
    none for a refusal. Delete this and the check is never shown to pass against a database."""
    assert run_check(install) == (PASSED, "")


@pytest.mark.needs_db
def test_the_check_fails_when_the_route_writes_nothing(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route stops treating any department as another's, so no opening leaves an entry. Delete
    this and a route that quietly stopped writing the entry leaves the check green."""
    monkeypatch.setattr(
        "brain.knowledge_lifecycle_routes.is_another_departments", lambda *_a: False
    )
    outcome, reason = run_check(install)
    assert outcome == FAILED
    assert "exactly one entry" in reason


@pytest.mark.needs_db
def test_the_check_fails_when_the_route_writes_one_for_every_opening(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route writes an entry whoever opens, which is the log of every read the declared set
    exists to prevent. Delete this and the check is satisfied by a route that over-writes."""
    monkeypatch.setattr("brain.knowledge_lifecycle_routes.is_another_departments", lambda *_a: True)
    outcome, reason = run_check(install)
    assert outcome == FAILED
    assert "inside the department" in reason
