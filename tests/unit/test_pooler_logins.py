"""Which logins the bundled pooler admits, read from the compose files that ship.

The application has to connect as `brain_app`, the NOBYPASSRLS login `0001` creates, and only
migrations as the owner. PgBouncer is the only door to the database, so it has to admit that
login. The image writes one userlist entry, the owner's, and a database entry carrying
`auth_user=<owner>`; a login not in the userlist is then looked up with `auth_query`, run as the
owner. Left to PgBouncer's default query, that lookup admits every login role, superusers
included, and the behaviour changes with the image. So the query is pinned in every pooler and
refuses any role that could read past row security: such a login can only be the one written
into the userlist on purpose.

**What is not measured here.** Docker is not installed where this was written, so no pooler was
started: that `v1.24.1-p1`'s entrypoint writes `auth_user=` rather than `user=` was read from
its published source, and a bump of the image has to re-read it (the pin is held below). The
query itself is run against PostgreSQL in CI by the last test.

Task ids: M31.4.2
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]

#: Every compose file that declares a pooler, including the worker's session pooler, so one
#: rule holds for all of them and a new pooler is caught by the image test below.
FILES: Final = (
    "docker-compose.yml",
    "docker-compose.lite.yml",
    "docker-compose.staging.yml",
    "docker-compose.worker.yml",
    # The generated merge of the full profile carries both poolers its sources ship.
    "docker-compose.full.yml",
)

#: The image whose entrypoint was read. Its database entry says `auth_user=${DB_USER}`, which
#: is what makes the lookup run as the owner and the server login be the client's own.
POOLER_IMAGE: Final = "edoburu/pgbouncer:v1.24.1-p1"

#: The query as PgBouncer receives it, after Compose turns `$$1` into `$1`.
AUTH_QUERY: Final = (
    "SELECT rolname, CASE WHEN rolvaliduntil < now() THEN NULL ELSE rolpassword END "
    "FROM pg_authid WHERE rolname = $1 AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls"
)

OWNER: Final = "brain"


def _services(name: str) -> dict[str, Any]:
    parsed = yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
    services: dict[str, Any] = parsed.get("services") or {}
    return services


def _poolers() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (name, service, body)
        for name in FILES
        for service, body in _services(name).items()
        if "pgbouncer" in str(body.get("image", ""))
    ]


def test_every_file_that_ships_a_pooler_is_read() -> None:
    """A pooler in a file this list does not name would admit logins by the default query."""
    shipping = [
        path.name
        for path in sorted(REPO.glob("docker-compose*.yml"))
        if any("pgbouncer" in str(b.get("image", "")) for b in _services(path.name).values())
    ]
    assert sorted(shipping) == sorted(FILES)


@pytest.mark.parametrize(("name", "service", "body"), _poolers())
def test_every_pooler_admits_brain_app_by_the_pinned_query_only(
    name: str, service: str, body: dict[str, Any]
) -> None:
    env = body["environment"]
    assert body["image"] == POOLER_IMAGE, f"{name}:{service}: re-read the new entrypoint"
    # The owner is the userlist entry and so the lookup's auth_user.
    assert env["DB_USER"] == OWNER
    assert env["AUTH_TYPE"] == "scram-sha-256"
    assert env["AUTH_QUERY"].replace("$$", "$") == AUTH_QUERY, f"{name}:{service}"


def test_the_query_refuses_every_role_that_reads_past_row_security() -> None:
    assert "NOT rolsuper" in AUTH_QUERY
    assert "NOT rolbypassrls" in AUTH_QUERY
    assert "rolcanlogin" in AUTH_QUERY
    # The entrypoint pastes the value into a printf format string, where % would be read.
    assert "%" not in AUTH_QUERY


@pytest.mark.parametrize(
    ("name", "variable"),
    [
        ("docker-compose.yml", "${BRAIN_DATABASE_URL:-}"),
        ("docker-compose.lite.yml", "${BRAIN_DATABASE_URL:-}"),
        ("docker-compose.staging.yml", "${STAGING_APP_DATABASE_URL:-}"),
    ],
)
def test_the_application_login_can_be_switched_without_editing_the_file(
    name: str, variable: str
) -> None:
    """`BRAIN_DATABASE_URL` wins over `DATABASE_URL` and a blank one is ignored, so the owner's
    URL stays the default and naming brain_app is one variable, not an edit to a stored file."""
    env = _services(name)["app"]["environment"]
    assert env["BRAIN_DATABASE_URL"] == variable
    assert "@pgbouncer:5432/" in env["DATABASE_URL"]
    if name == "docker-compose.staging.yml":
        assert env["BRAIN_MIGRATION_DATABASE_URL"] == "${STAGING_MIGRATION_DATABASE_URL:-}"


@pytest.mark.needs_db
def test_the_shipped_query_returns_brain_app_shaped_logins_and_no_superuser() -> None:
    """Runs the query the compose file carries against a real server: a NOBYPASSRLS login with a
    password comes back with its SCRAM secret, a superuser and a BYPASSRLS login come back empty."""
    url = os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    import psycopg

    from brain.db import libpq_url

    libpq = libpq_url(url)
    query = _services("docker-compose.yml")["pgbouncer"]["environment"]["AUTH_QUERY"]
    query = query.replace("$$", "$").replace("$1", "%s")
    suffix = secrets.token_hex(4)
    roles = {
        f"pool_app_{suffix}": "LOGIN NOSUPERUSER NOBYPASSRLS",
        f"pool_super_{suffix}": "LOGIN SUPERUSER",
        f"pool_bypass_{suffix}": "LOGIN NOSUPERUSER BYPASSRLS",
    }
    with psycopg.connect(libpq, autocommit=True) as conn:
        try:
            for role, attributes in roles.items():
                conn.execute(f"CREATE ROLE {role} {attributes} PASSWORD 'pw-{suffix}'")
            found = {role: conn.execute(query, (role,)).fetchall() for role in roles}
        finally:
            for role in roles:
                conn.execute(f"DROP ROLE IF EXISTS {role}")
    app_rows = found[f"pool_app_{suffix}"]
    assert len(app_rows) == 1 and str(app_rows[0][1]).startswith("SCRAM-SHA-256$")
    assert found[f"pool_super_{suffix}"] == []
    assert found[f"pool_bypass_{suffix}"] == []
