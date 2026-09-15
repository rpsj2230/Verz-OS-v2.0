"""Create, migrate and seed a database, as three commands a client's IT team runs by name.

The pieces existed and none of them was a script anybody on a client's server could be told to
run. `brain.migrate.run_migrations` runs at application startup and has no command of its own;
`brain.seed` is a command and refuses an unmigrated database with a traceback rather than a
sentence; and nothing created the database at all, because on a standard install the database
container's image creates one. That is true until somebody points an install at a server they
already run, which is the first thing a client with a database team asks to do.

**Three commands and no fourth that runs them all, and the missing one is the argument.**
`create` and `migrate` build a database and are part of every install. `seed` loads a
fictitious company and belongs on a demonstration or a staging server only, so a `build` that
ran all three would be one argument away from writing a demo into a live install, and a `build`
that ran two would be a second name for a sequence of two commands. See
`SEEDING_IS_NOT_PART_OF_BUILDING_A_DATABASE`.

**Every one of them can be run twice, and each says which run it was.** An install is re-run
after a failure part of the way through, by somebody who does not know how far the first run
got. `create` on a database that exists says so and writes nothing, `migrate` at head applies
nothing, and a second `seed` over its own demo writes nothing, which `brain.seed` already
decides. See `A_COMMAND_THAT_CAN_BE_RUN_TWICE_WILL_BE`.

**Each refuses the state it cannot act on, in order, and names the command that fixes it.**
`migrate` against a database the server does not have is told to run `create`; `seed` against
a schema behind the migrations is told to run `migrate`; `seed` against a database holding rows
it does not own is refused by `brain.seed.looks_like_production`, unchanged, and this command
offers no `--force`. The flag stays on `python -m brain.seed`, where its own refusal text says
what it is. See `brain.seed.A_REFUSAL_WHOSE_ONLY_REMEDY_IS_FORCE_TEACHES_FORCE`.

**A full disk is reported by name, and only because each of these writes in one
transaction.** `migrate` runs the whole chain in one transaction under the advisory lock and
`seed` loads the demo in one, so when PostgreSQL refuses a write for want of space nothing the
command wrote survives it, and `DiskFullError` can say so. `create` issues one statement. That
is the condition `brain.ops.reliability.A_FULL_DISK_REFUSES_THE_WRITE_RATHER_THAN_HALF_WRITING_IT`
puts on raising it, and the exit status is its own so a wrapper can tell it from a refusal.

**The database is the same in every profile, and the one that differs is not this module's.**
`lite`, `standard` and `full` run one application database with one schema, and the demo is
the same rows in all three. `full` also runs the trace ledger, which needs a second database
and a login of its own, and the installer creates both in its step "create the databases the
compose files do not". Repeating that here would be a second place the trace ledger's login is
created. See `EVERY_PROFILE_BUILDS_THE_SAME_APPLICATION_DATABASE`.

Rejected: a shell script per command under `ops/`. Every rule above is a decision about a
PostgreSQL condition, and in shell each one is a string match on psql's output, untestable
without a server and wrong in the locale where the message is translated. These run where the
application does, as `python -m brain.deployment.database`, and the install guide gives the
`docker compose exec` form.

Rejected: reading the database name out of the URL with a split on "/". A URL whose path holds
a query string or an encoded character would produce a name the server does not have, and
`create` would make it. The name is parsed, and anything that is not an ordinary lowercase
identifier is refused rather than quoted, because this is a name typed into an environment file
and a name that needs quoting is almost always a typing mistake.

Task ids: M42.3.3, M30.4.5
"""

from __future__ import annotations

import enum
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol
from urllib.parse import unquote, urlsplit, urlunsplit

from sqlalchemy import create_engine, text

from brain import seed as seeding
from brain.db import normalise_database_url
from brain.migrate import pending_revisions, run_migrations
from brain.ops.reliability import DiskFullError, is_disk_full
from brain.settings import Settings, settings_from

# ------------------------------------------------------------------ written-down reasons
#: Why there is no command that runs all three.
SEEDING_IS_NOT_PART_OF_BUILDING_A_DATABASE: Final = (
    "create and migrate are what every install runs; seed writes a fictitious company's "
    "people, clients and contract values, which on a live install sit beside the real ones "
    "looking exactly like them. A command that ran all three would put that one argument away "
    "from every production database, and the guard in the seed would be the only thing between "
    "them. So the demo is a separate command a person has to name."
)

#: Why each command says whether it did anything.
A_COMMAND_THAT_CAN_BE_RUN_TWICE_WILL_BE: Final = (
    "An install that failed part of the way is re-run by somebody who cannot see how far it "
    "got. A command that fails the second time turns a finished step into an apparent fault, "
    "and one that repeats its work turns it into a real one. So each command answers the "
    "second run with nothing written and a sentence saying so."
)

#: Why this module creates the application database and not the trace ledger's.
EVERY_PROFILE_BUILDS_THE_SAME_APPLICATION_DATABASE: Final = (
    "Every profile runs one application database with the same schema and the same demo. Only "
    "full adds the trace ledger, whose database and login the installer creates in its own "
    "step, guarded by existence checks. A second creator of that login here would be a second "
    "place its password is set, and the two would disagree the first time one was changed."
)

# ------------------------------------------------------------------------ the vocabulary
#: The commands, in the order an install runs them.
COMMANDS: Final[tuple[str, ...]] = ("create", "migrate", "seed")

#: The database every PostgreSQL server has, which `create` connects to in order to make
#: another one. A database cannot be created from a connection to itself.
MAINTENANCE_DATABASE: Final = "postgres"

#: A database name these commands will create or connect to. Lowercase, because an unquoted
#: name is folded to lowercase by the server, and a name that only works quoted is one the
#: next tool that connects will not find.
DATABASE_NAME: Final = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

#: Exit statuses. A full disk has its own, so whatever runs these can tell "free space and run
#: it again" from "something about this database has to change first".
EXIT_DONE: Final = 0
EXIT_REFUSED: Final = 1
EXIT_USAGE: Final = 2
EXIT_DISK_FULL: Final = 3

USAGE: Final = (
    "usage: python -m brain.deployment.database create | migrate | seed\n"
    "reads DATABASE_URL; see docs/install/operations.md"
)


class DatabaseScriptError(Exception):
    """Raised when a command refuses the state it found, with the command that fixes it."""


class Executor(Protocol):
    """The part of a connection `ensure_database` uses, so the decision is testable alone."""

    def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


# ---------------------------------------------------------------------- which database
@dataclass(frozen=True)
class Target:
    """The database a URL names, and the URL of the server's maintenance database beside it."""

    name: str
    server_url: str


def target_of(url: str) -> Target:
    """The database `url` names, refused unless it is an ordinary lowercase identifier."""
    parts = urlsplit(url.strip())
    name = unquote(parts.path.lstrip("/"))
    if not name:
        msg = (
            "DATABASE_URL names no database, so there is nothing to create or migrate. It ends "
            "in the database's name, for example /brain"
        )
        raise DatabaseScriptError(msg)
    if not DATABASE_NAME.match(name):
        msg = (
            f"the database name {name!r} is not an ordinary lowercase identifier, so it would "
            "have to be quoted everywhere it is used. Use lowercase letters, digits and "
            "underscores"
        )
        raise DatabaseScriptError(msg)
    server = urlunsplit(parts._replace(path=f"/{MAINTENANCE_DATABASE}"))
    return Target(name=name, server_url=server)


class Created(enum.StrEnum):
    """What `create` did, so the second run is distinguishable from the first."""

    CREATED = "created"
    ALREADY_THERE = "already there"


def ensure_database(conn: Executor, name: str) -> Created:
    """Create `name` on this server unless it exists. The decision, apart from the connection.

    The name is checked again here rather than trusted from `target_of`, because it is
    interpolated: `CREATE DATABASE` takes no bind parameter for its name.
    """
    if not DATABASE_NAME.match(name):
        msg = f"the database name {name!r} is not an ordinary lowercase identifier"
        raise DatabaseScriptError(msg)
    if ensure_exists_query(conn, name):
        return Created.ALREADY_THERE
    conn.execute(text(f'CREATE DATABASE "{name}"'))
    return Created.CREATED


# ------------------------------------------------------------------------ the commands
def create(url: str) -> Created:
    """Create the database DATABASE_URL names, on the server it names, unless it exists."""
    target = target_of(url)
    engine = create_engine(
        normalise_database_url(target.server_url), isolation_level="AUTOCOMMIT", poolclass=None
    )
    try:
        with engine.connect() as conn:
            return ensure_database(conn, target.name)
    except Exception as error:
        if is_disk_full(error):
            raise DiskFullError("creating the database") from error
        raise
    finally:
        engine.dispose()


def database_exists(url: str) -> bool:
    """Whether the server DATABASE_URL names has the database it names, asked of the server.

    **Asked before connecting, because the failure to connect does not say why.** The first
    version translated PostgreSQL's condition 3D000 out of the error, with a test that built
    that error from psycopg's own class and passed. Run against a real server on 2026-09-15 it
    never fired: a connection refused for a missing database arrives as psycopg's
    `OperationalError` with no SQLSTATE on it at all, and the only place the reason appears is
    the server's message, in the server's language. So the maintenance database is asked, which
    is the question `create` already asks.
    """
    target = target_of(url)
    engine = create_engine(normalise_database_url(target.server_url), poolclass=None)
    try:
        with engine.connect() as conn:
            return ensure_exists_query(conn, target.name)
    finally:
        engine.dispose()


def ensure_exists_query(conn: Executor, name: str) -> bool:
    """The existence question on a connection somebody else opened."""
    return bool(
        conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        ).first()
    )


def _refuse_if_missing(url: str) -> None:
    """The refusal for a database the server does not have, naming the command that makes it."""
    if not database_exists(url):
        msg = (
            f"the server has no database called {target_of(url).name}. Run create first; it "
            "makes the database DATABASE_URL names and does nothing if it already exists"
        )
        raise DatabaseScriptError(msg)


def migrate(url: str) -> list[str]:
    """Bring the database to the newest schema. Returns what was applied; empty means none."""
    _refuse_if_missing(url)
    try:
        return run_migrations(url)
    except Exception as error:
        if is_disk_full(error):
            raise DiskFullError("the migration") from error
        raise


def seed(url: str) -> int:
    """Load the demo company, on a migrated database holding nothing of anybody else's.

    Returns `brain.seed.seed`'s own status, which is zero for a load and for a second run over
    the demo, and one for its refusal, whose reasons it prints itself.
    """
    _refuse_if_missing(url)
    behind = pending_revisions(normalise_database_url(url))
    if behind:
        msg = (
            f"the database is {len(behind)} migration(s) behind this release, so the demo has "
            "tables to write into that do not exist yet. Run migrate first"
        )
        raise DatabaseScriptError(msg)
    try:
        return seeding.seed(url)
    except Exception as error:
        if is_disk_full(error):
            raise DiskFullError("loading the demo") from error
        raise


# ------------------------------------------------------------------------- the command line
def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """Run one command against DATABASE_URL, and exit with a status a wrapper can act on."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in COMMANDS:
        print(USAGE, file=sys.stderr)
        return EXIT_USAGE
    # Through `Settings`, so this script and the application agree about which of the two
    # names wins when both are set. It preferred the plain one until 2026-09-15.
    settings = Settings() if env is None else settings_from(env)
    url = settings.database_url.strip()
    if not url:
        print("DATABASE_URL is not set, so there is no database to act on", file=sys.stderr)
        return EXIT_USAGE

    command = args[0]
    try:
        if command == "create":
            done = create(url)
            name = target_of(url).name
            if done is Created.CREATED:
                print(f"created the database {name}")
            else:
                print(f"the database {name} already exists; nothing was written")
            return EXIT_DONE
        if command == "migrate":
            applied = migrate(url)
            if applied:
                print(f"applied {len(applied)} migration(s); the schema is at this release")
            else:
                print("the schema is already at this release; nothing was applied")
            return EXIT_DONE
        return seed(url)
    except DiskFullError as full:
        print(f"DISK FULL: {full}", file=sys.stderr)
        return EXIT_DISK_FULL
    except DatabaseScriptError as refused:
        print(f"REFUSED: {refused}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
