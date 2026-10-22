"""The member accounts install checks, passing on PostgreSQL at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.5.1.3, M40.5.1.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("where", "sentence"),
    [
        ("brain.connector_routes.my_accounts", "DB_LIST"),
        ("brain.govern_routes.retire_grant", "DB_RETIRE_GRANT"),
        ("brain.ops.acceptance_checks_member_accounts._held_in", "DB_SEARCH_SETTINGS"),
        ("brain.ops.acceptance_checks_member_accounts._held_in", "DB_SEARCH_RECENT"),
    ],
)
def test_a_step_the_database_refuses_is_named_by_the_step_and_quotes_nothing(
    install: str,
    issuer: None,
    monkeypatch: pytest.MonkeyPatch,
    where: str,
    sentence: str,
) -> None:
    """The install stopped this check on an OperationalError and the page could only say the type.
    A refused step must now fail with the sentence naming it. Delete this and a database error on
    an install is again a type name, and the next run cannot say which statement it was."""
    import importlib

    from sqlalchemy.exc import OperationalError

    from brain.ops import acceptance_checks_member_accounts as module

    module_name, _, attribute = where.rpartition(".")
    target = importlib.import_module(module_name)

    def refuses(*args: Any, **kwargs: Any) -> Any:
        raise OperationalError("statement", {}, Exception("a value that must not be quoted"))

    async def refuses_later(*args: Any, **kwargs: Any) -> Any:
        # The search is two statements' worth of calls: the tables without a time column, then the
        # ones read by theirs. Refuse only the one this case is about, and answer the other.
        settings_only = all(
            module.WHERE_A_TOKEN_COULD_BE_LEFT[one] is None for one in kwargs["tables"]
        )
        if settings_only == (sentence == "DB_SEARCH_SETTINGS"):
            raise OperationalError("statement", {}, Exception("a value that must not be quoted"))
        return ()

    monkeypatch.setattr(target, attribute, refuses_later if attribute == "_held_in" else refuses)
    reason = _failed(install, DISCONNECT)
    assert reason == getattr(module, sentence)
    assert "must not be quoted" not in reason


@pytest.mark.needs_db
def test_the_search_for_a_left_behind_token_finds_it_in_the_tables_it_looks_in(
    install: str,
) -> None:
    """The bounded search against a real database: a token planted in `ops.setting` is found and
    one planted nowhere is not. Delete this and the search can look nowhere and pass for ever."""
    import asyncio

    from sqlalchemy import text

    from brain.db import normalise_database_url
    from brain.ops.acceptance_checks_member_accounts import (
        WHERE_A_TOKEN_COULD_BE_LEFT,
        _held_in,
    )
    from brain.session import make_app_engine
    from tests.fixtures.scratch_postgres import sql

    planted = "CANARY-TOKEN-8f3a1c-left-behind"
    sql(
        install,
        "INSERT INTO ops.setting (key, value_type, value, description, updated_by) "
        "VALUES ('canary.left', 'string', to_jsonb(%s::text), 'a canary', 'test')",
        planted,
    )

    hexed = "CANARY-TOKEN-hex-7c2e"
    sql(
        install,
        "INSERT INTO ops.setting (key, value_type, value, description, updated_by) "
        "VALUES ('canary.hex', 'string', to_jsonb(%s::text), 'a canary', 'test')",
        hexed.encode("utf-8").hex(),
    )

    everything = tuple(WHERE_A_TOKEN_COULD_BE_LEFT)
    long_ago = datetime(2019, 1, 1, tzinfo=UTC)

    async def look(needle: str, *, since: datetime = long_ago) -> tuple[str, ...]:
        engine = make_app_engine(normalise_database_url(install))
        try:
            async with engine.connect() as connection:
                harness: Any = type("H", (), {"connection": connection})()
                found = await _held_in(harness, needle, since=since, tables=everything)
                await connection.execute(text("SELECT 1"))
                return found
        finally:
            await engine.dispose()

    try:
        assert asyncio.run(look(planted)) == ("ops.setting",)
        assert asyncio.run(look(hexed)) == ("ops.setting",)
        assert asyncio.run(look("CANARY-TOKEN-never-written")) == ()
    finally:
        sql(install, "DELETE FROM ops.setting WHERE key LIKE 'canary.%'")


@pytest.mark.needs_db
def test_the_search_reads_a_table_with_a_time_column_only_from_the_start_of_the_window(
    install: str,
) -> None:
    """A token in a connection row is found from a window that includes the row and not from one
    that starts after it. Delete this and the bound can be dropped, which puts a cast of the
    whole ledger back on an install with a year of rows, or tightened past the run so a token it
    left is never looked for, and the search passes either way."""
    import asyncio

    from sqlalchemy import text

    from brain.db import normalise_database_url
    from brain.ops.acceptance_checks_member_accounts import _held_in
    from brain.session import make_app_engine
    from tests.fixtures.scratch_postgres import sql

    planted = "CANARY-CONNECTION-5d9b2e-left-behind"
    written = datetime(2999, 6, 1, tzinfo=UTC)
    sql(
        install,
        "INSERT INTO ops.connector_connection "
        "(connector, settings, digest, connected_by, connected_at) "
        "VALUES ('canary_source', jsonb_build_object('note', %s::text), %s, 'test', %s)",
        planted,
        "0" * 64,
        written,
    )

    async def look(since: datetime) -> tuple[str, ...]:
        engine = make_app_engine(normalise_database_url(install))
        try:
            async with engine.connect() as connection:
                harness: Any = type("H", (), {"connection": connection})()
                found = await _held_in(
                    harness, planted, since=since, tables=("ops.connector_connection",)
                )
                await connection.execute(text("SELECT 1"))
                return found
        finally:
            await engine.dispose()

    try:
        assert asyncio.run(look(written - timedelta(hours=1))) == ("ops.connector_connection",)
        assert asyncio.run(look(written + timedelta(hours=1))) == ()
    finally:
        sql(install, "DELETE FROM ops.connector_connection WHERE connector = 'canary_source'")


@pytest.mark.needs_db
def test_a_token_found_in_a_table_a_disconnect_writes_to_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The search finding something is a failure, in words that name no table's contents. Delete
    this and a token a disconnect left behind passes the check."""
    from brain.ops import acceptance_checks_member_accounts as module

    async def finds(h: Any, needle: str, **kwargs: Any) -> tuple[str, ...]:
        return ("ops.setting",)

    monkeypatch.setattr(module, "_held_in", finds)
    assert "was found in a table" in _failed(install, DISCONNECT)
