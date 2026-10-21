"""The member accounts install checks, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.5.1.3, M40.5.1.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_accounts"
DISCONNECT = "a_member_disconnects_their_account_and_the_vendor_is_told_first"
INHERITED = "a_departments_connection_is_inherited_and_not_detachable"


def test_the_module_declares_its_leaves_and_sits_where_it_was_placed() -> None:
    """One check per leaf, each closing only its own, at the order this module was given. Delete
    this and a check can lose its leaf with the page showing the same row, or share a position."""
    from brain.ops import acceptance_checks_member_accounts as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (DISCONNECT, ("M40.5.1.3",)),
        (INHERITED, ("M40.5.1.4",)),
    ]
    assert checks_in(MODULE) == [DISCONNECT, INHERITED]
    assert module.CHECK_ORDER == 2780


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_accounts") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str) -> dict[str, tuple[str, str]]:
    return run_check(url, list(registered((MODULE,))))


def _failed(url: str, which: str) -> str:
    outcome, reason = run(url)[which]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_the_account_checks_pass_on_an_install_and_leave_nothing(
    install: str, issuer: None
) -> None:
    """The module as the worker runs it: both pass and nothing is left behind. Delete this and a
    check that cannot pass on a real schema, or one that commits a connection, ships."""
    before = counts(install)
    assert run(install) == {DISCONNECT: (PASSED, ""), INHERITED: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_revoker_that_removes_the_token_before_asking_the_vendor_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The order reversed: the slot goes, then the vendor is asked. Delete this and M40.5.1.3
    closes on a disconnect that leaves nothing to retry with when the vendor refuses."""
    from brain.ops.person_token_revoker import VaultTokenRevoker

    original = VaultTokenRevoker.revoke

    def removes_first(self: VaultTokenRevoker, token_ref: str, *, at: datetime) -> bool:
        self._remover.remove_static_kv(token_ref)
        return original(self, token_ref, at=at)

    monkeypatch.setattr(VaultTokenRevoker, "revoke", removes_first)

    assert _failed(install, DISCONNECT)


@pytest.mark.needs_db
def test_a_disconnect_that_ignores_a_failed_revocation_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`disconnect` replaced by a function that never refuses. Delete this and M40.5.1.3 closes on
    a page that reports a disconnection the vendor refused."""
    from brain import member_accounts_routes
    from brain.member.connections import Disconnection

    def never_refuses(connection: Any, *, revoker: Any, at: datetime) -> Disconnection:
        revoker.revoke(connection.token_ref, at=at)
        return Disconnection(
            principal_id=connection.principal_id, source=connection.source, revoked_at=at
        )

    monkeypatch.setattr(member_accounts_routes, "disconnect", never_refuses)

    assert "refused" in _failed(install, DISCONNECT) or "still" in _failed(install, DISCONNECT)


@pytest.mark.needs_db
def test_a_listing_that_offers_a_control_on_a_departments_connection_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every department connection marked disconnectable. Delete this and M40.5.1.4 closes on a
    page that offers to detach what the person did not attach."""
    from brain import connector_routes
    from brain.connector_routes import MyAccountView

    real = connector_routes.MyAccountView

    def offers(**fields: Any) -> MyAccountView:
        return real(**{**fields, "disconnectable": True})

    monkeypatch.setattr(connector_routes, "MyAccountView", offers)

    assert "inherited" in _failed(install, INHERITED)


@pytest.mark.needs_db
def test_a_listing_that_leaves_the_departments_connection_out_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inherited list emptied. Delete this and M40.5.1.4 closes on a list of what the system
    reaches for a person that leaves the department's out."""
    from brain import connector_routes

    async def nothing(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(connector_routes, "department_provided", nothing)

    assert "inherited" in _failed(install, INHERITED)
