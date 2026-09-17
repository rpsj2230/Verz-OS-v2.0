"""The database create, migrate and seed commands, against fakes and against a real server.

The decisions are tested without a server, by handing each command the error a real server
would raise, built from psycopg's own classes: a full disk is `DiskFull`, wrapped in SQLAlchemy's
error exactly as it arrives on a client's install. A missing database is not tested that way, and
the reason is a measurement: the first version did, passed, and never fired against a real
server, because a connection refused for a missing database carries no condition code. See
`brain.deployment.database.database_exists`. The second half runs the commands against
whatever `DATABASE_URL` points at, in a database of this file's own, and skips when nothing is
set. CI always sets it.

**One live test needs `vector` and says so rather than failing.** Migrating to head needs
pgvector, which CI's database image carries and a development machine's PostgreSQL often does
not. That test skips with the reason when the extension is unavailable, so a green run on a
machine without it has not measured a migration, and the skip line is what says so.

Task ids: M42.3.3, M30.4.5
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg.errors
import pytest
from sqlalchemy.exc import OperationalError

from brain import seed as seeding
from brain.deployment import database
from brain.deployment.database import (
    COMMANDS,
    EXIT_DISK_FULL,
    EXIT_DONE,
    EXIT_REFUSED,
    EXIT_USAGE,
    MAINTENANCE_DATABASE,
    Created,
    DatabaseScriptError,
    ensure_database,
    target_of,
)
from brain.ops.reliability import DiskFullError

URL = "postgresql://brain:secret@db:5432/brain"


def _wrapped(driver_error: BaseException) -> OperationalError:
    """What a command catches from a real server: SQLAlchemy's error around the driver's."""
    return OperationalError("SELECT 1", {}, driver_error)


def _recording(into: list[str], answer: Any) -> Any:
    """A stand-in that records the URL it was called with and returns `answer`."""

    def go(url: str) -> Any:
        into.append(url)
        return answer

    return go


def _raises(error: BaseException) -> Any:
    def go(*_args: object, **_kwargs: object) -> Any:
        raise error

    return go


class _Rows:
    def __init__(self, row: object) -> None:
        self.row = row

    def first(self) -> object:
        return self.row


class _Server:
    """A connection that answers the existence question and records what it was asked."""

    def __init__(self, *, exists: bool) -> None:
        self.exists = exists
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: object = None, /) -> _Rows:
        self.statements.append(str(statement))
        return _Rows((1,) if self.exists else None)


# ------------------------------------------------------------------------ which database
def test_the_database_is_read_from_the_url_and_created_from_the_servers_own() -> None:
    """`create` cannot run `CREATE DATABASE brain` from a connection to `brain`, so it connects
    to the maintenance database on the same server with the same credentials.

    Delete this and the server URL can keep the target's name, and `create` fails on every
    fresh server with the error it exists to prevent."""
    found = target_of(URL)

    assert found.name == "brain"
    parts = urlsplit(found.server_url)
    assert parts.path == f"/{MAINTENANCE_DATABASE}"
    assert (parts.username, parts.password, parts.hostname, parts.port) == (
        "brain",
        "secret",
        "db",
        5432,
    )


def test_a_url_naming_no_database_is_refused() -> None:
    """Delete this and a URL ending at the port reads as a database with an empty name, which
    the server answers with an error about syntax rather than about the environment file."""
    with pytest.raises(DatabaseScriptError, match="names no database"):
        target_of("postgresql://brain:secret@db:5432")


def test_a_database_name_that_would_need_quoting_is_refused_rather_than_quoted() -> None:
    """The name is interpolated into `CREATE DATABASE`, which takes no bind parameter for it.

    Delete this and a name carrying a quote reaches the statement, and a name in capitals is
    created as one that every tool connecting without quotes will not find."""
    for name in ('brain"; DROP DATABASE postgres; --', "Brain", "1brain", "brain-app"):
        with pytest.raises(DatabaseScriptError, match="not an ordinary lowercase identifier"):
            target_of(f"postgresql://brain@db:5432/{name}")
        with pytest.raises(DatabaseScriptError, match="not an ordinary lowercase identifier"):
            ensure_database(_Server(exists=False), name)


# ------------------------------------------------------------------------------- create
def test_create_makes_a_database_the_server_does_not_have() -> None:
    """Delete this and `ensure_database` can return without creating anything, and every test
    of the second run below still passes."""
    server = _Server(exists=False)

    assert ensure_database(server, "brain") is Created.CREATED
    assert server.statements[-1] == 'CREATE DATABASE "brain"'


def test_create_writes_nothing_when_the_database_already_exists() -> None:
    """**The second run.** An install re-run after a failure reaches this step again, and a
    `CREATE DATABASE` against an existing database is an error that stops the re-run at a step
    that had succeeded.

    Delete this and `create` can issue the statement unconditionally."""
    server = _Server(exists=True)

    assert ensure_database(server, "brain") is Created.ALREADY_THERE
    assert not any(one.startswith("CREATE") for one in server.statements)


def test_create_reports_a_full_disk_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and a full disk while creating the database leaves the command's traceback
    as the only report."""
    monkeypatch.setattr(database, "ensure_database", _raises(_wrapped(psycopg.errors.DiskFull())))
    monkeypatch.setattr(database, "create_engine", lambda *_a, **_k: _FakeEngine())

    with pytest.raises(DiskFullError, match="creating the database"):
        database.create(URL)


class _FakeEngine:
    def connect(self) -> Any:
        from contextlib import nullcontext

        return nullcontext(_Server(exists=False))

    def dispose(self) -> None:
        return None


# ------------------------------------------------------------------------------ migrate
def test_migrate_on_a_database_the_server_lacks_says_to_run_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order an install runs these in is the whole content of the refusal, and nothing is
    migrated before it is given.

    Delete this and the command answers a missing database with psycopg's connection error,
    which carries no condition code and says nothing about which command makes the database."""
    ran: list[str] = []
    monkeypatch.setattr(database, "database_exists", lambda url: False)
    monkeypatch.setattr(database, "run_migrations", _recording(ran, []))

    with pytest.raises(DatabaseScriptError, match="Run create first"):
        database.migrate(URL)
    assert ran == []


def test_migrate_reports_a_full_disk_as_a_full_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """**M30.4.5 on a real write path.** The migration runs in one transaction, so a refusal for
    space leaves nothing applied and the named error is true.

    Delete this and the translation can go, and an operator reads a SQLAlchemy traceback in
    which the words disk and full appear only in the server's message, if the locale is
    English."""
    monkeypatch.setattr(database, "database_exists", lambda url: True)
    full = psycopg.errors.DiskFull("could not extend file")
    monkeypatch.setattr(database, "run_migrations", _raises(_wrapped(full)))

    with pytest.raises(DiskFullError, match="the migration stopped because the disk is full"):
        database.migrate(URL)


def test_migrate_lets_every_other_failure_through_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling of the two translations. A command that turned every error into one of its
    own sentences would tell somebody with a wrong password to free disk space.

    Delete this and both translations can be widened to catch everything."""
    monkeypatch.setattr(database, "database_exists", lambda url: True)
    wrong = _wrapped(psycopg.errors.InvalidPassword("password authentication failed"))
    monkeypatch.setattr(database, "run_migrations", _raises(wrong))

    with pytest.raises(OperationalError) as caught:
        database.migrate(URL)
    assert caught.value is wrong


def test_migrate_returns_what_was_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and the command can succeed without running the migrations at all."""
    monkeypatch.setattr(database, "database_exists", lambda url: True)
    monkeypatch.setattr(database, "run_migrations", lambda url: ["0031", "0030"])

    assert database.migrate(URL) == ["0031", "0030"]


# --------------------------------------------------------------------------------- seed
def test_seed_on_a_schema_behind_the_migrations_says_to_run_migrate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the demo is loaded into tables that do not exist, and the person reads
    `relation "auth.principal" does not exist` as a broken release."""
    monkeypatch.setattr(database, "database_exists", lambda url: True)
    called: list[str] = []
    monkeypatch.setattr(database, "pending_revisions", lambda url: ["0002", "0001"])
    monkeypatch.setattr(seeding, "seed", _recording(called, 0))

    with pytest.raises(DatabaseScriptError, match=r"2 migration\(s\) behind.*Run migrate first"):
        database.seed(URL)
    assert called == []


def test_seed_on_a_migrated_database_hands_over_to_the_guarded_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive half, and the reason it hands over rather than loading itself: the refusal
    of a database holding somebody else's rows lives in `brain.seed` and is not repeated here.

    Delete this and the command can refuse every database, which passes the test above."""
    monkeypatch.setattr(database, "database_exists", lambda url: True)
    called: list[str] = []
    monkeypatch.setattr(database, "pending_revisions", lambda url: [])
    monkeypatch.setattr(seeding, "seed", _recording(called, 1))

    assert database.seed(URL) == 1
    assert called == [URL]


def test_seed_on_a_production_install_is_refused_before_the_database_is_asked_anything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """M38.1.4.4. An install whose `BRAIN_ENV` is `production` never receives the demo, and the
    refusal comes before the row guard, which waves an empty production database through.

    Delete this and the command a client's runbook names can write a fictitious company into a
    live install on the morning it was set up."""
    called: list[str] = []
    monkeypatch.setattr(database, "seed", _recording(called, 0))

    env = {"DATABASE_URL": URL, "BRAIN_ENV": "production"}
    assert database.main(["seed"], env=env) == EXIT_REFUSED
    assert called == []
    assert "BRAIN_ENV=staging" in capsys.readouterr().err


def test_seed_on_a_staging_install_goes_on_to_the_guarded_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive half: staging is where seed data belongs. Delete this and the environment
    check can refuse every install, which passes the test above."""
    called: list[str] = []
    monkeypatch.setattr(database, "seed", _recording(called, 0))

    assert database.main(["seed"], env={"DATABASE_URL": URL, "BRAIN_ENV": "staging"}) == 0
    assert called == [URL]


def test_seed_offers_no_way_past_the_guard() -> None:
    """**No `--force` on the install command.** The flag exists on `python -m brain.seed`, whose
    refusal names the remedies before it names the flag.

    Delete this and a flag can be threaded through, and the command a client's runbook names
    becomes one argument away from writing a demo into a live install."""
    assert database.main(["seed", "--force"], env={"DATABASE_URL": URL}) == EXIT_USAGE


def test_seed_on_a_database_the_server_lacks_says_to_run_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the seed's first question, how far behind the schema is, raises psycopg's
    connection error instead of the order to run the commands in."""
    monkeypatch.setattr(database, "database_exists", lambda url: False)
    monkeypatch.setattr(database, "pending_revisions", _raises(AssertionError("asked anyway")))

    with pytest.raises(DatabaseScriptError, match="Run create first"):
        database.seed(URL)


def test_seed_reports_a_full_disk_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The demo loads in one transaction, so the refusal is true when it says nothing was kept.

    Delete this and a full disk half way through the load is a traceback."""
    monkeypatch.setattr(database, "database_exists", lambda url: True)
    monkeypatch.setattr(database, "pending_revisions", lambda url: [])
    monkeypatch.setattr(seeding, "seed", _raises(_wrapped(psycopg.errors.DiskFull("no space"))))

    with pytest.raises(DiskFullError, match="loading the demo"):
        database.seed(URL)


# ------------------------------------------------------------------------ the command line
def test_the_command_line_reads_the_environment_it_is_handed_and_not_the_machines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handed environment is the whole environment: the machine's own database names do not
    answer for one the caller left out, and the prefixed name the application prefers is read.

    Delete this and `main` can build `Settings()` from the process instead of the mapping, which
    passes every other test here on a machine with no database configured and is wrong on any
    machine with one."""
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("BRAIN_DATABASE_URL", URL)
    assert database.main(["migrate"], env={}) == EXIT_USAGE

    monkeypatch.setattr(database, "migrate", lambda url: [])
    assert database.main(["migrate"], env={"BRAIN_DATABASE_URL": URL}) == EXIT_DONE


def test_the_command_line_acts_as_the_owner_when_the_install_names_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create, migrate and seed are the owner's work. Delete this and an install whose
    `DATABASE_URL` names `brain_app` runs them as a login that cannot create a schema."""
    owner = "postgresql://owner:pw@db:5432/brain"
    seen: list[str] = []

    def migrated(url: str) -> list[str]:
        seen.append(url)
        return []

    monkeypatch.setattr(database, "migrate", migrated)

    env = {"DATABASE_URL": URL, "BRAIN_MIGRATION_DATABASE_URL": owner}
    assert database.main(["migrate"], env=env) == EXIT_DONE
    assert database.main(["migrate"], env={"DATABASE_URL": URL}) == EXIT_DONE
    assert seen == [owner, URL]


def test_the_command_line_answers_each_outcome_with_its_own_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A full disk, a refusal, bad usage and success are four statuses, so whatever runs these
    can tell "free space and run it again" from "change something first".

    Delete this and the statuses can collapse into one non-zero exit."""
    env = {"DATABASE_URL": URL}

    assert database.main([], env=env) == EXIT_USAGE
    assert database.main(["drop"], env=env) == EXIT_USAGE
    assert database.main(["migrate"], env={}) == EXIT_USAGE

    monkeypatch.setattr(database, "migrate", _raises(DiskFullError("the migration")))
    assert database.main(["migrate"], env=env) == EXIT_DISK_FULL
    assert "DISK FULL: the migration" in capsys.readouterr().err

    monkeypatch.setattr(database, "migrate", _raises(DatabaseScriptError("Run create first")))
    assert database.main(["migrate"], env=env) == EXIT_REFUSED
    assert "REFUSED: Run create first" in capsys.readouterr().err

    monkeypatch.setattr(database, "migrate", lambda url: [])
    assert database.main(["migrate"], env=env) == EXIT_DONE
    assert "nothing was applied" in capsys.readouterr().out

    monkeypatch.setattr(database, "migrate", lambda url: ["0002"])
    assert database.main(["migrate"], env=env) == EXIT_DONE
    assert "applied 1 migration(s)" in capsys.readouterr().out


def test_the_command_line_says_which_run_of_create_it_was(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and the second run of create can print the first run's sentence, which tells
    somebody re-running a failed install that a database was just made."""
    env = {"DATABASE_URL": URL}

    monkeypatch.setattr(database, "create", lambda url: Created.CREATED)
    assert database.main(["create"], env=env) == EXIT_DONE
    assert capsys.readouterr().out.strip() == "created the database brain"

    monkeypatch.setattr(database, "create", lambda url: Created.ALREADY_THERE)
    assert database.main(["create"], env=env) == EXIT_DONE
    assert "already exists; nothing was written" in capsys.readouterr().out


def test_the_commands_are_the_three_the_leaf_names_in_the_order_an_install_runs_them() -> None:
    """Delete this and a fourth command running all three can be added, which is the command
    `SEEDING_IS_NOT_PART_OF_BUILDING_A_DATABASE` argues against."""
    assert COMMANDS == ("create", "migrate", "seed")


# ------------------------------------------------------------------- against a real server
#: A database of this file's own, created and dropped here, so nothing else reads it.
SCRATCH = "brain_database_scripts_check"


def _server_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL") or None


def _pointed_at(url: str, name: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


def _drop(url: str, name: str) -> None:
    from brain.db import libpq_url

    with psycopg.connect(libpq_url(_pointed_at(url, MAINTENANCE_DATABASE)), autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def scratch() -> Iterator[str]:
    """The URL of a database that does not exist yet, on the server `DATABASE_URL` names."""
    url = _server_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    _drop(url, SCRATCH)
    yield _pointed_at(url, SCRATCH)
    _drop(url, SCRATCH)


def test_on_a_real_server_create_makes_the_database_once_and_then_reports_it(scratch: str) -> None:
    """**Measured, not mocked.** The existence query and the statement run against PostgreSQL,
    which is the only place `CREATE DATABASE` inside a transaction is refused.

    Delete this and `create` can be correct against the fake and fail on every server, because
    the fake does not know the statement cannot run in a transaction block."""
    assert database.create(scratch) is Created.CREATED
    assert database.create(scratch) is Created.ALREADY_THERE


def test_on_a_real_server_the_later_commands_refuse_until_the_earlier_ones_have_run(
    scratch: str,
) -> None:
    """The refusals, from the conditions the server really raises rather than ones built here.

    Delete this and the translation can match a condition the server never sends."""
    with pytest.raises(DatabaseScriptError, match="Run create first"):
        database.migrate(scratch)
    with pytest.raises(DatabaseScriptError, match="Run create first"):
        database.seed(scratch)

    database.create(scratch)
    with pytest.raises(DatabaseScriptError, match="Run migrate first"):
        database.seed(scratch)


def _has_vector(url: str) -> bool:
    from brain.db import libpq_url

    with psycopg.connect(libpq_url(url)) as conn:
        row = conn.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'").fetchone()
    return row is not None


def test_on_a_real_server_the_three_commands_build_a_database_and_run_twice_safely(
    scratch: str,
) -> None:
    """**The leaf end to end.** Create, migrate to head, seed the demo, and every command a
    second time: nothing is created twice, no migration is applied twice, and the second seed
    writes nothing and succeeds.

    Skipped where the server has no `vector`, because the first migration installs it, and the
    skip says so rather than the test passing on less.

    Delete this and the three commands are tested only against their own fakes."""
    maintenance = _pointed_at(scratch, MAINTENANCE_DATABASE)
    if not _has_vector(maintenance):
        pytest.skip("this server has no pgvector, so no migration can reach head here; CI's has")

    assert database.create(scratch) is Created.CREATED
    assert database.migrate(scratch)
    assert database.migrate(scratch) == []
    assert database.seed(scratch) == 0
    assert database.seed(scratch) == 0
    assert database.create(scratch) is Created.ALREADY_THERE
