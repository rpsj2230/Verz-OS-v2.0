"""The application's login against a real server: bound by row-level security, and unable to reach
the owner from inside a request transaction.

`SET LOCAL ROLE brain_app` binds each transaction, and `RESET ROLE` undoes it back to the login.
So the property that matters is the login's, and it is measured here on a real PostgreSQL rather
than on a fake, because a fake would answer whatever the test told it. See
`brain.session.A_REQUEST_TRANSACTION_CAN_RESET_ITS_ROLE_TO_THE_LOGIN`.

The login is a role of this file's own, `LOGIN NOSUPERUSER NOBYPASSRLS` and a member of
`brain_app`, dropped afterwards: roles are cluster-wide, and changing `brain_app` itself would
reach every other test sharing the server. Every test skips without `DATABASE_URL`, and CI always
sets it.

Task ids: M31.4.2
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from brain.session import (
    BYPASSES_ROW_SECURITY,
    check_login_row_security,
    check_row_security,
    make_application_sessions,
)
from tests.fixtures.scratch_postgres import admin_url, drop, engine, fresh, run, sql

DATABASE = "brain_database_login"
LOGIN = "brain_login_probe"


def as_login(url: str, user: str, password: str) -> str:
    """`url` with its user and password replaced, host, port and database kept."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"{quote(user)}:{quote(password)}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))


@pytest.fixture(scope="module")
def urls() -> Iterator[tuple[str, str]]:
    """The owner's URL and the application login's, over one scratch database."""
    owner = fresh(DATABASE)
    password = secrets.token_urlsafe(24)
    sql(owner, f'DROP ROLE IF EXISTS "{LOGIN}"')
    sql(owner, f"CREATE ROLE \"{LOGIN}\" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'")
    sql(owner, f'GRANT brain_app TO "{LOGIN}"')
    try:
        yield owner, as_login(owner, LOGIN, password)
    finally:
        drop(DATABASE)
        sql(admin_url(), f'DROP ROLE IF EXISTS "{LOGIN}"')


#: Whether the URL's own login could read past a policy: the case the owner's sibling test needs.
LOGIN_BYPASSES = "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = session_user"


def owner_bypasses(owner: str) -> bool:
    [(bypasses,)] = sql(owner, LOGIN_BYPASSES)
    return bool(bypasses)


async def a_request_can_become_the_owner(built: AsyncEngine) -> bool:
    """Whether a statement inside a request transaction can shed `brain_app` and read past RLS.

    `RESET ROLE` is the statement an injected query would use: it needs no privilege and returns
    the transaction to the login."""
    sessions = make_application_sessions(built)
    try:
        async with sessions() as session:
            await session.execute(text("RESET ROLE"))
            return bool((await session.execute(BYPASSES_ROW_SECURITY)).scalar_one())
    finally:
        await built.dispose()


def test_the_application_login_is_bound_by_row_level_security(urls: tuple[str, str]) -> None:
    """`database_login` on `/health/ready` is ready for the login the install should use.

    Delete this and `check_login_row_security` could ask `current_user`, which is `brain_app`
    inside every request transaction whatever the login, and report every owner login ready."""
    _, login = urls

    assert run(lambda: check_login_row_security(engine(login))) is True
    assert run(lambda: check_row_security(make_application_sessions(engine(login)))) is True


def test_a_request_transaction_on_the_application_login_cannot_run_as_the_owner(
    urls: tuple[str, str],
) -> None:
    """The test the leaf asks for: it fails if a request transaction can run as the owner.

    Delete this and a login granted the owner role, or made BYPASSRLS, passes every unit test,
    because each of those fakes the database."""
    owner, login = urls
    owner_name = urlsplit(owner).username or ""

    assert run(lambda: a_request_can_become_the_owner(engine(login))) is False

    async def set_role_to_owner() -> None:
        built = engine(login)
        try:
            async with make_application_sessions(built)() as session:
                await session.execute(text(f'SET ROLE "{owner_name}"'))
        finally:
            await built.dispose()

    with pytest.raises(Exception, match="permission denied"):
        run(set_role_to_owner)


def test_the_owner_login_is_named_not_ready_and_can_shed_the_role(urls: tuple[str, str]) -> None:
    """The sibling that proves the two checks above can fail: on the owner's login, a request
    transaction reaches the owner with one statement and `database_login` says so.

    Delete this and both checks above are satisfied by a function that answers False always."""
    owner, _ = urls
    if not owner_bypasses(owner):
        pytest.skip(
            "this server's DATABASE_URL login is not a superuser, so there is no owner to shed to"
        )

    assert run(lambda: check_login_row_security(engine(owner))) is False
    assert run(lambda: a_request_can_become_the_owner(engine(owner))) is True
