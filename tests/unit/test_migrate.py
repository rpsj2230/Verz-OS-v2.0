"""Startup migrations and the advisory lock that makes them safe with replicas.

Task ids: M0.3.2
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from brain import migrate
from brain.app import Settings, create_app
from brain.db import normalise_database_url
from tests.fixtures.scratch_postgres import database_url, drop, fresh, pointed_at, sql

REPO = Path(__file__).resolve().parents[2]
HANDED = "postgresql+psycopg://brain@db:5432/handed"
PREFIXED = "postgresql+psycopg://brain@db:5432/prefixed"
PLAIN = "postgresql+psycopg://brain@db:5432/plain"


def test_the_lock_id_is_a_fixed_constant() -> None:
    """Every replica must ask for the same lock. Deriving it from anything that varies -
    a hostname, a pid, the database name - would let two replicas each take a different
    lock and migrate at the same time, which is the exact failure the lock prevents."""
    assert isinstance(migrate.MIGRATION_LOCK_ID, int)
    assert migrate.MIGRATION_LOCK_ID == 8_274_419_003


def test_alembic_config_points_at_the_repository() -> None:
    cfg = migrate._alembic_config("postgresql+psycopg://u:p@h/d")
    assert Path(cfg.get_main_option("script_location") or "").name == "migrations"
    assert cfg.get_main_option("sqlalchemy.url") == "postgresql+psycopg://u:p@h/d"


def test_percent_in_a_password_is_escaped_for_configparser() -> None:
    """alembic.ini is read by configparser, which treats % as interpolation. A password
    containing one would raise rather than connect."""
    cfg = migrate._alembic_config("postgresql+psycopg://u:pa%%ss@h/d")
    assert "%%" in (cfg.get_main_option("sqlalchemy.url") or "")


def test_the_migration_template_asks_for_task_ids_and_both_directions() -> None:
    """`make revision` writes every new migration from `migrations/script.py.mako`, so the
    template is where a migration's house rules either start or do not. It carries a
    `Task ids:` line so a migration claims its leaves the way a module does, it renders both an
    upgrade and a downgrade, and it tells the author that a downgrade which cannot be written
    raises rather than passes, because a `pass` downgrade reports success on the way back and
    leaves the schema where it was.

    Read line by line and matched on whole lines, so a phrase inside the template's own prose
    cannot stand in for the function it describes.

    Delete this and the template can lose any of those, and the next migration written from it
    has no line on which to say which leaf it serves."""
    template = (Path(__file__).resolve().parents[2] / "migrations" / "script.py.mako").read_text(
        encoding="utf-8"
    )
    lines = [line.rstrip() for line in template.splitlines()]

    assert any(line.startswith("Task ids:") for line in lines)
    assert "def upgrade() -> None:" in lines
    assert "def downgrade() -> None:" in lines
    assert "revision = ${repr(up_revision)}" in lines
    assert "down_revision = ${repr(down_revision)}" in lines
    assert "NotImplementedError" in template


# ------------------------------------------------------------------ startup
def test_startup_skips_migrations_when_no_database_is_configured() -> None:
    """The documents and the status page serve without a database, so a missing
    DATABASE_URL must not stop the app booting."""
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app) as c:
        assert c.get("/health/ready").status_code == 200
        assert "migrations" not in c.get("/health/ready").json()["checks"]


def test_a_failed_migration_leaves_the_app_unready_rather_than_crashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unready is visible on /health/ready and keeps the traceback. A crash would put the
    container in a restart loop and discard the reason on every cycle."""

    def boom(_url: str) -> list[str]:
        msg = "deliberate"
        raise RuntimeError(msg)

    monkeypatch.setattr("brain.app.run_migrations", boom)
    app = create_app(Settings(env="development", database_url="postgresql://u:p@h/d"))
    with TestClient(app) as c:
        r = c.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["checks"]["migrations"] is False


def test_migrations_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """An operator who applies migrations by hand sets this and the app does not try."""
    called = False

    def spy(_url: str) -> list[str]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("brain.app.run_migrations", spy)
    app = create_app(
        Settings(env="development", database_url="postgresql://u:p@h/d", run_migrations=False)
    )
    with TestClient(app):
        pass
    assert not called


def test_a_successful_migration_is_recorded_separately_from_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migrations and reachability are two checks, not one.

    A database that accepted the migration and is now unreachable is a different failure
    from one that rejected it, and readiness has to be able to say which.
    """
    monkeypatch.setattr("brain.app.run_migrations", lambda _url: ["0001"])
    app = create_app(Settings(env="development", database_url="postgresql://u:p@127.0.0.1:1/d"))
    with TestClient(app) as c:
        checks = c.get("/health/ready").json()["checks"]
        assert checks["migrations"] is True
        # the host is deliberately unreachable, so this is the honest answer
        assert checks["database"] is False


def test_an_unreachable_database_fails_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check runs a statement rather than only opening a connection: PgBouncer will
    accept a connection it cannot fulfil, so connecting proves the pooler is alive and
    nothing about the database behind it."""
    monkeypatch.setattr("brain.app.run_migrations", lambda _url: [])
    app = create_app(Settings(env="development", database_url="postgresql://u:p@127.0.0.1:1/d"))
    with TestClient(app) as c:
        r = c.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"


# ------------------------------------------------------------- regression
def test_the_plain_database_url_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression, found by the CI stack job on 2026-09-04.

    Settings carries env_prefix="BRAIN_", so `database_url` looked only at
    BRAIN_DATABASE_URL. Compose, alembic, and every operator on earth write
    DATABASE_URL. The deployed app therefore found nothing, skipped migrations, and
    reported healthy against an empty schema - and nothing failed, because an app with no
    database is perfectly able to serve documents.
    """
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    assert Settings().database_url == "postgresql://u:p@h/d"


def test_the_prefixed_name_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both are accepted; the explicit one takes precedence so a host-wide DATABASE_URL
    cannot quietly override a deliberate per-app setting."""
    monkeypatch.setenv("BRAIN_DATABASE_URL", "postgresql://deliberate@h/d")
    monkeypatch.setenv("DATABASE_URL", "postgresql://ambient@h/d")
    assert Settings().database_url == "postgresql://deliberate@h/d"


def test_a_missing_database_outside_development_is_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence was the actual failure. Outside development, no database means unready."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    app = create_app(Settings(env="staging", database_url=""))
    with TestClient(app) as c:
        r = c.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["checks"]["database_configured"] is False


def test_development_without_a_database_stays_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the docs locally with no Postgres is a normal thing to do."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app) as c:
        assert c.get("/health/ready").status_code == 200


# ----------------------------------------------- the lock has to survive a transaction pooler
def test_the_migration_lock_is_transaction_scoped_not_session_scoped() -> None:
    """A session-level lock is held by a *server* connection, and the application talks to
    PgBouncer in transaction mode, where consecutive statements from one client can land on
    different server connections. The lock was taken on one and every later statement ran
    somewhere else, so mutual exclusion was gone and nothing said so: two replicas both ran
    the upgrade, both issued CREATE TABLE alembic_version, and the loser died on a unique
    violation against a system index while the app failed to start.

    Asserted by reading the source because the failure only appears with a real pooler and
    two replicas, which is not a thing a unit test can stand up.
    """
    source = (Path(__file__).resolve().parents[2] / "src" / "brain" / "migrate.py").read_text(
        encoding="utf-8"
    )
    assert "pg_advisory_xact_lock" in source
    assert "SELECT pg_advisory_lock(" not in source


def test_the_migration_runs_on_the_connection_that_holds_the_lock() -> None:
    """A transaction-scoped lock only guards work inside its own transaction. Left to
    itself alembic opens a second connection, and through the pooler that is a different
    server connection again, so the migration would run outside the lock it just took."""
    source = (Path(__file__).resolve().parents[2] / "src" / "brain" / "migrate.py").read_text(
        encoding="utf-8"
    )
    assert 'attributes["connection"]' in source

    env = (Path(__file__).resolve().parents[2] / "migrations" / "env.py").read_text(
        encoding="utf-8"
    )
    assert 'config.attributes.get("connection")' in env


def test_nothing_unlocks_by_hand() -> None:
    """A transaction-scoped lock releases itself. An explicit unlock would be a path that
    can be forgotten, and a crashed replica would leave the lock held forever."""
    source = (Path(__file__).resolve().parents[2] / "src" / "brain" / "migrate.py").read_text(
        encoding="utf-8"
    )
    assert "pg_advisory_unlock" not in source


# ------------------------------------------------ which address the Alembic environment migrates
def _bare_config(url: str | None = None) -> Config:
    """An Alembic config pointed at the migrations, with no ini file.

    No ini file because `env.py` calls `logging.config.fileConfig` on one, and that disables
    every logger already created in this process, which is every other test's logging. What is
    under test is the address `env.py` settles on, and `alembic.ini` names no address.
    """
    config = Config()
    config.set_main_option("script_location", str(REPO / "migrations"))
    if url is not None:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _run_env_offline(config: Config) -> str:
    """Execute `migrations/env.py` for the first revision as SQL, and return the address it set.

    Offline mode runs `env.py` to completion without connecting to anything, so the address it
    resolves is observable on the config it wrote back to, with no database present."""
    config.output_buffer = io.StringIO()
    command.upgrade(config, "base:0001", sql=True)
    return config.get_main_option("sqlalchemy.url") or ""


def _no_database_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)


def test_the_address_on_the_config_beats_both_variable_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What `run_migrations` hands over is what is migrated, whatever the process says.

    Delete this and `alembic_url` can prefer a variable, which on a host with a stale one
    migrates a database the application is not connected to."""
    monkeypatch.setenv("BRAIN_DATABASE_URL", PREFIXED)
    monkeypatch.setenv("DATABASE_URL", PLAIN)

    assert migrate.alembic_url(HANDED) == HANDED


def test_with_nothing_on_the_config_the_address_is_the_one_settings_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bare `alembic` command hands over nothing, so the setting answers, with the prefixed
    name winning exactly as it does for the application; and either name alone is enough.

    Delete this and the command line can grow its own reading of the two names again."""
    monkeypatch.setenv("BRAIN_DATABASE_URL", PREFIXED)
    monkeypatch.setenv("DATABASE_URL", PLAIN)
    assert migrate.alembic_url(None) == normalise_database_url(Settings().database_url)
    assert migrate.alembic_url("") == PREFIXED

    monkeypatch.delenv("BRAIN_DATABASE_URL")
    assert migrate.alembic_url(None) == PLAIN


def test_with_no_address_anywhere_the_refusal_names_both_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the message can go back to naming `DATABASE_URL` alone, which sends an
    operator who set the prefixed name to look for a variable they believe they already set."""
    _no_database_names(monkeypatch)

    with pytest.raises(RuntimeError, match="BRAIN_DATABASE_URL nor DATABASE_URL"):
        migrate.alembic_url(None)


def test_a_percent_in_a_password_survives_the_trip_through_the_config() -> None:
    """`_alembic_config` doubles a `%` for configparser and `get_main_option` undoes it, so the
    address `alembic_url` is handed is the one that was given.

    Delete this and a password containing `%` can reach the driver doubled, which fails as an
    authentication error that reads like a wrong password."""
    given = "postgresql+psycopg://brain:pa%25ss@db:5432/brain"
    config = migrate._alembic_config(given)

    assert migrate.alembic_url(config.get_main_option("sqlalchemy.url")) == given


def test_the_alembic_environment_keeps_the_address_it_was_handed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`env.py` itself, executed: a config carrying an address comes back carrying the same one
    with both variables set to another.

    Delete this and `env.py` can stop calling `alembic_url` and read `DATABASE_URL` again, which
    every test of `alembic_url` above would survive."""
    monkeypatch.setenv("BRAIN_DATABASE_URL", PREFIXED)
    monkeypatch.setenv("DATABASE_URL", PLAIN)

    assert _run_env_offline(_bare_config(HANDED)) == HANDED
    # A `%` in a password, which `env.py` has to double again when it writes the address back.
    escaped = "postgresql+psycopg://brain:pa%25ss@db:5432/handed"
    assert _run_env_offline(_bare_config(escaped)) == escaped


def test_the_alembic_environment_runs_on_the_prefixed_name_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host naming the database only as `BRAIN_DATABASE_URL` gets a migration rather than
    `DATABASE_URL is not set`, and a config with no address and no variable is refused.

    Delete this and the application's own migration step can raise inside `env.py` on such a
    host again, with readiness reporting migrations failed and nothing wrong with the setting."""
    _no_database_names(monkeypatch)
    with pytest.raises(RuntimeError, match="BRAIN_DATABASE_URL nor DATABASE_URL"):
        _run_env_offline(_bare_config())

    monkeypatch.setenv("BRAIN_DATABASE_URL", PREFIXED)
    assert _run_env_offline(_bare_config()) == PREFIXED


def test_a_database_named_only_by_the_prefixed_variable_is_the_one_alembic_writes_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same claim against a real server: with only `BRAIN_DATABASE_URL` set and nothing on
    the config, `alembic stamp` lands its revision in that database. Skips with no server.

    Delete this and the offline test above is the only evidence, and offline mode never opens
    the connection whose address is the whole question."""
    server = database_url()
    if server is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    name = "brain_test_alembic_prefixed_only"
    scratch = fresh(name)
    try:
        with monkeypatch.context() as scoped:
            scoped.delenv("DATABASE_URL", raising=False)
            scoped.setenv("BRAIN_DATABASE_URL", pointed_at(server, name))
            command.stamp(_bare_config(), "0024")
        assert sql(scratch, "SELECT version_num FROM alembic_version") == [("0024",)]
    finally:
        drop(name)
