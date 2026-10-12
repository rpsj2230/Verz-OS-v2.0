"""The install checks for the people screens, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.15.25
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_people"
SESSIONS = "every_session_of_a_person_ends_and_a_wrong_unlink_is_undone"


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {SESSIONS: ("M27.15.25",)}
    assert checks_in(MODULE) == [SESSIONS]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_people") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_the_checks_pass_on_an_install_and_leave_nothing(install: str, issuer: None) -> None:
    """**The checks as the worker runs them.** They pass and leave no person, grant, binding,
    session or ledger entry. Delete this and a check that commits, or one that cannot pass on a
    real schema, reaches the owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {SESSIONS: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_request_that_ends_only_the_first_session_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ending several sessions that ends one. Delete this and M27.15.25 closes on a screen that
    leaves a person signed in on another device after an administrator ended them."""
    from brain import session_routes

    async def first_only(items: list[str], act: object) -> list[tuple[str, object]]:
        first, *rest = items
        return [(first, await act(first)), *[(one, None) for one in rest]]  # type: ignore[operator]

    monkeypatch.setattr(session_routes, "each_of", first_only)
    outcome, reason = run_module(install, MODULE)[SESSIONS]
    assert outcome == FAILED, reason
    assert "every session" in reason
