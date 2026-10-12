"""The install check for the handover Settings describes, passing on PostgreSQL at head, leaving
nothing, and failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.13.7
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_console_handover"
HANDOVER = "settings_describes_the_handover_before_anyone_runs_it"


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """The check and the leaf it closes. Delete this and the check can lose M27.13.7, or gain a
    leaf it does not prove, with the screen unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {HANDOVER: ("M27.13.7",)}
    assert checks_in(MODULE) == [HANDOVER]


def test_the_authority_the_check_holds_is_the_routes_own() -> None:
    """The authority the check's administrator holds, held against the Settings route's. Delete
    this and a renamed authority fails the check on every install with nothing wrong."""
    from brain.ops.acceptance_checks_console_handover import CHANGES_SETTINGS
    from brain.settings_routes import INSTALL_SETTING_AUTHORITY

    assert INSTALL_SETTING_AUTHORITY.value == CHANGES_SETTINGS


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_console_handover") as url:
        yield url


def _failed(url: str) -> str:
    outcome, reason = run_module(url, MODULE)[HANDOVER]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and leaves no person, grant or ledger entry.
    Delete this and a check that commits, or one that cannot pass on a real schema, reaches the
    owner's server first."""
    before = counts(install)
    assert run_module(install, MODULE) == {HANDOVER: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_handover_that_leaves_out_a_store_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A preview missing the last store. Delete this and M27.13.7 closes on a screen that tells
    a person leaving that less of the install goes than does."""
    from brain.ops.handover_run import preview_steps as real

    def short(*, realm: str) -> tuple[object, ...]:
        steps = real(realm=realm)
        stores = [one for one in steps if one.what.__class__.__name__ == "Store"]
        return tuple(one for one in steps if one is not stores[-1])

    monkeypatch.setattr("brain.settings_routes.preview_steps", short)
    assert "every store" in _failed(install)


@pytest.mark.needs_db
def test_a_settings_screen_open_to_anybody_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority ignored. Delete this and the plan for leaving could be shown to a person with
    no authority over the install and M27.13.7 would still close."""
    from brain import settings_routes

    monkeypatch.setattr(settings_routes, "may_configure", lambda *args, **kwargs: True)
    assert "without the authority" in _failed(install)
