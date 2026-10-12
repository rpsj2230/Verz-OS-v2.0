"""The install check for an agent's manifest taken out and brought back, passing on PostgreSQL at
head, leaving nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.28
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_manifest"
MANIFEST = "a_manifest_leaves_without_company_details_and_returns_as_a_draft"


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """The check and the leaf it closes. Delete this and the check can lose M27.15.28, or gain a
    leaf it does not prove, with the routes unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {MANIFEST: ("M27.15.28",)}
    assert checks_in(MODULE) == [MANIFEST]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_manifest") as url:
        yield url


@pytest.fixture(autouse=True)
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[MANIFEST]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no agent, draft or ledger entry.
    Delete this and a check that commits a draft reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {MANIFEST: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_export_that_keeps_the_address_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An export that redacts nothing. Delete this and M27.15.28 closes on an export that carries
    a company's address out of the install, which is the leak the leaf exists to stop."""
    from brain import agent_builder_routes as routes

    monkeypatch.setattr(routes, "SHAPED", frozenset())
    assert "kept a company's address" in _failed(install)


@pytest.mark.needs_db
def test_an_import_that_publishes_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An import that does not run the leak scan. Delete this and M27.15.28 closes on a document
    brought in from elsewhere with its company details unflagged."""
    from brain import agent_builder_routes as routes

    monkeypatch.setattr(routes, "scan", lambda document: type("R", (), {"items": ()})())
    outcome, reason = run_module(install, MODULE)[MANIFEST]
    assert outcome == FAILED, reason
