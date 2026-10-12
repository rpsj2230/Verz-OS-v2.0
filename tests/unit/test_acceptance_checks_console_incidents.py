"""The install check for the Incidents screen, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.2.7
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_incidents"
INCIDENT = "a_refused_source_is_an_incident_naming_what_it_blocks"


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """The check and the leaf it closes. Delete this and a check can lose its leaf, or gain one it
    does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {INCIDENT: ("M27.2.7",)}
    assert checks_in(MODULE) == [INCIDENT]


def test_the_authority_the_check_holds_is_the_routes_own() -> None:
    """The authority the check's administrator holds, held against the Connectors screen's. Delete
    this and a renamed authority fails the check on every install with nothing wrong."""
    from brain.connectors.registry import INSTALL_AUTHORITY
    from brain.ops.acceptance_checks_console_incidents import CONNECTS_SOURCES

    assert INSTALL_AUTHORITY.value == CONNECTS_SOURCES


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_incidents") as url:
        yield url


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no person, grant, connection or
    ledger entry. Delete this and a check that commits, or one that cannot pass on a real schema,
    reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {INCIDENT: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_incident_screen_that_lists_nothing_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A screen that finds no source degraded. Delete this and M27.2.7 closes on a screen that
    tells an administrator all is well while a source refuses every read."""
    from brain import incident_routes

    monkeypatch.setattr(incident_routes, "incidents", lambda named, shown: ())
    outcome, reason = run_module(install, MODULE)[INCIDENT]
    assert outcome == FAILED, reason
