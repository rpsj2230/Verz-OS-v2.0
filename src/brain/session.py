"""Engines and sessions.

Two engines, deliberately, and the reason is PgBouncer.

**The application engine runs through PgBouncer in transaction mode**, which hands a
different backend connection to every transaction. That is what makes a hundred
application connections survivable on a database configured for twenty, but it breaks
server-side prepared statements, because the statement is prepared on one backend and
executed on another. psycopg raises `InvalidSqlStatementName` or, worse, silently reuses a
plan built for different parameters. So `prepare_threshold=None` is not a tuning knob
here; without it the application works in development, where there is no PgBouncer, and
fails in production under load.

**The worker engine bypasses the pooler**, or uses session mode. `LISTEN`/`NOTIFY` binds
to a backend connection and transaction pooling moves it; a listener behind a transaction
pooler simply stops receiving notifications, with no error anywhere.

**The application's sessions run every transaction as `brain_app`, whoever logged in.** `0001`
creates that role NOBYPASSRLS so that row-level security binds the application, and nothing
made the application use it: `make_app_engine` sets no role, and every compose file's
`DATABASE_URL` names `brain`, the `POSTGRES_USER` the database container creates, which is a
superuser. So every policy the migrations wrote was decoration on a deployed process, which is
exactly what `0001`'s docstring says it exists to prevent. The login cannot simply become
`brain_app` either: the same URL runs the migrations inside the lifespan, and those create
extensions and roles. See `THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS`.

Task ids: M0.3.4, M31.2.1.2, M31.2.1.3, M31.2.1.4
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import structlog
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.pool import NullPool

from brain.db import normalise_database_url

log = structlog.get_logger()

#: The role `0001` creates NOSUPERUSER NOBYPASSRLS, and the one row-level security binds.
APPLICATION_ROLE: Final = "brain_app"

#: Written out, so there is no interpolation near a statement. A test holds it to the role.
SET_APPLICATION_ROLE: Final = "SET LOCAL ROLE brain_app"

#: Whether the role this transaction runs as could read past a policy. False is the ready answer.
BYPASSES_ROW_SECURITY: Final = text(
    "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
)

#: Why the role is set per transaction, and not on the login or the connection.
THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS: Final = (
    "The login a deployment gives the application is the database superuser, because the same "
    "URL runs the migrations and those create extensions and roles, and a superuser reads past "
    "every row-level security policy. So each transaction the application's sessions begin "
    "starts with SET LOCAL ROLE brain_app. LOCAL, because the application talks to PgBouncer "
    "in transaction mode: a session-level SET ROLE stays on the server connection it ran on, "
    "which is handed to another client after the transaction, while this client's next "
    "transaction lands on a connection where it was never set and runs as the superuser. A "
    "role set inside the transaction ends with it, on whichever connection that was. Rejected: "
    "refusing to start when the login bypasses row security, which refuses every install as "
    "they are deployed today; and a role on the connection string, which PgBouncer does not "
    "carry to the server connection."
)


def _async_url(url: str) -> str:
    """psycopg 3 speaks both sync and async; SQLAlchemy needs the async dialect named."""
    return normalise_database_url(url)


def make_app_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """The engine every request uses. Assumes PgBouncer in transaction mode.

    `poolclass=NullPool` because PgBouncer *is* the pool. Stacking SQLAlchemy's pool on
    top of it means two pools with different ideas about connection lifetime, and the
    symptom is connections that look idle to one and busy to the other.
    """
    return create_async_engine(
        _async_url(url),
        echo=echo,
        poolclass=NullPool,
        connect_args={
            # Not optional behind a transaction pooler. See the module docstring: a
            # prepared statement created on one backend and executed on another is the
            # bug that only appears in production.
            "prepare_threshold": None,
        },
    )


def make_worker_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """The engine for background work, connecting directly rather than through a pooler.

    Keeps a real pool, because a worker holds long-lived connections for LISTEN/NOTIFY
    and re-establishing one per transaction would drop notifications between them.

    **M0.3.5 asked for a PgBouncer session-mode pool here and this is not one.** Every
    pooler in every compose file is `POOL_MODE: transaction`, and transaction pooling
    cannot carry LISTEN: the connection a notification arrives on is handed to somebody
    else between statements. The worker therefore connects straight to Postgres, which is
    what LISTEN needs and is a defensible answer to the same problem.

    It is a different answer, so the leaf is not claimed. The cost is that these
    connections are outside PgBouncer's bound and are held by this pool instead:
    `pool_size` plus `max_overflow` below, per worker process. That figure is the one
    `docs/needs-rupash.md` item 41 needs, and it is why two of the four services named
    there are already bounded in code and merely undeclared.
    """
    return create_async_engine(
        _async_url(url),
        echo=echo,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        expire_on_commit=False,  # objects stay usable after commit, inside one request
        autoflush=False,  # flush where it is meant to happen, not implicitly mid-read
    )


class ApplicationRoleSession(Session):
    """A session whose every transaction runs as `APPLICATION_ROLE`. See the listener below."""


@event.listens_for(ApplicationRoleSession, "after_begin")
def _as_application_role(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """The first statement of every transaction, before anything the caller sends.

    `after_begin` fires once per connection a session transaction takes, which is before the
    caller's first statement reaches it, so there is no statement in any transaction these
    sessions run that ran as the login.
    See `THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS`.
    """
    del session, transaction
    connection.exec_driver_sql(SET_APPLICATION_ROLE)


def make_application_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`make_session_factory`, with every transaction run as `APPLICATION_ROLE`.

    What `brain.app.lifespan` serves requests through. A separate function rather than a change
    to `make_session_factory`, because the worker and the schedule runner build sessions over
    the same URL for work that is not a request and has not been measured as the application
    role; switching them in passing would be a change nobody decided.
    """
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
        sync_session_class=ApplicationRoleSession,
    )


async def check_row_security(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Readiness: a transaction from these sessions runs as a role row-level security binds.

    Asked through the sessions rather than the engine, so it is the question about what requests
    run as and not about the login. False for a role that bypasses the policies, and False for a
    transaction that could not be run at all, which is a missing `brain_app` or a login not
    allowed to become it. The log line names the exception class and never its message, which
    carries the connection string.
    """
    try:
        async with sessions() as session:
            bypasses = (await session.execute(BYPASSES_ROW_SECURITY)).scalar_one()
    except Exception as exc:
        log.warning("row security unverified", error=type(exc).__name__)
        return False
    if bypasses:
        log.error("the application's transactions read past row-level security")
        return False
    return True


@asynccontextmanager
async def request_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One session per request, rolled back on any exception.

    Committing is the caller's job. A context manager that commits on the way out turns
    every unhandled path into a write, which is precisely wrong for a system whose default
    should be reading.
    """
    session = factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_reachable(engine: AsyncEngine) -> bool:
    """Readiness. A trivial query, not a connection test.

    Opening a connection proves the pooler is alive; PgBouncer will happily accept a
    connection it cannot fulfil. Running a statement proves there is a database behind it.
    """
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("database unreachable", error=str(exc)[:200])
        return False
    return True


async def dispose(engine: AsyncEngine | None) -> None:
    if engine is not None:
        await engine.dispose()


def engine_kwargs_for_profile(profile: str) -> dict[str, Any]:
    """Sizing per deployment profile, kept in one place rather than in a compose file.

    The numbers are deliberately modest. The target box runs about thirty containers on
    twelve gigabytes, and a connection pool sized for a machine we do not have is how a
    shared host falls over.
    """
    return {
        "lite": {"pool_size": 5, "max_overflow": 5},
        "standard": {"pool_size": 10, "max_overflow": 10},
        "full": {"pool_size": 20, "max_overflow": 20},
    }.get(profile, {"pool_size": 5, "max_overflow": 5})
