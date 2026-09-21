"""Running migrations at startup, safely, with more than one replica.

Migrations used to run as a separate one-shot container. That worked, but it exits when
it succeeds, and Coolify has no way to be told a container is *meant* to stop, so a
successful migration displayed as a red "Exited" next to three healthy services, forever.
A status anyone has to remember is fine is a status that will eventually be believed.

So migrations now run during application startup, before readiness passes. The obvious
objection is the race: two replicas starting together would both try to migrate. That is
handled by a PostgreSQL advisory lock rather than by hoping. The first replica takes the
lock and migrates; the others block until it finishes, then find nothing to do. The lock
is held on a session and released automatically if that process dies, so a replica killed
mid-migration does not wedge the deployment.

The trade-off, stated because it is real: a failed migration now fails startup, so the
application refuses to serve rather than serving against a schema it does not match. That
is the behaviour we want, the alternative is answering questions from a half-migrated
database, but it does mean a bad migration takes the app down rather than just failing a
job. The invariant suite and the CI stack test exist to catch that before it deploys.

Task ids: M0.3.2, M31.1.1.2
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from brain.db import normalise_database_url
from brain.settings import Settings

log = structlog.get_logger()

#: Why the Alembic environment believes the address on its config before any setting.
THE_ADDRESS_HANDED_TO_ALEMBIC_IS_THE_ONE_MIGRATED: Final = (
    "run_migrations puts the application's database address on the Alembic config, and "
    "migrations/env.py used to overwrite it with DATABASE_URL read from the process. On a host "
    "naming the database only as BRAIN_DATABASE_URL the application's own migration step raised; "
    "on a host naming both, the application connected to one database and migrated the other. "
    "The address a caller hands over is the one migrated, and the setting is only the fallback "
    "for the bare alembic command, which hands over nothing."
)


def alembic_url(configured: str | None) -> str:
    """The address `migrations/env.py` connects to, in SQLAlchemy's form.

    `configured` is `sqlalchemy.url` as the Alembic config reports it, which `_alembic_config`
    set and `get_main_option` has already unescaped. When nothing set it, which is the bare
    `alembic upgrade head` command because `alembic.ini` deliberately names no database, the
    address is `Settings.database_url`, so the command line and the application agree about
    which of the two variable names wins. See `THE_ADDRESS_HANDED_TO_ALEMBIC_IS_THE_ONE_MIGRATED`.

    Here rather than in `env.py`, because `env.py` is executed by Alembic and cannot be imported
    by a test, and the precedence is the part worth holding to a test.
    """
    settings = Settings()
    # The owner's login first, as the lifespan does, so the bare command can migrate an install
    # whose `DATABASE_URL` names `brain_app`.
    url = (configured or "").strip() or settings.owner_database_url()
    if not url:
        msg = (
            "no database to migrate: the Alembic config names none, and neither "
            "BRAIN_DATABASE_URL nor DATABASE_URL is set"
        )
        raise RuntimeError(msg)
    return normalise_database_url(url)


REPO = Path(__file__).resolve().parents[2]

#: Any constant works; it only has to be the same in every replica. Chosen once and never
#: changed, because changing it would let an old and a new replica migrate concurrently.
MIGRATION_LOCK_ID = 8_274_419_003


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def pending_revisions(url: str) -> list[str]:
    """Revisions the database has not applied yet. Empty means up to date."""
    cfg = _alembic_config(url)
    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(url, poolclass=None)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    head = script.get_current_head()
    if current == head:
        return []
    return [rev.revision for rev in script.iterate_revisions(head, current) if rev.revision]


def run_migrations(database_url: str) -> list[str]:
    """Bring the database to head. Returns the revisions applied, newest first.

    Safe to call from every replica simultaneously.
    """
    url = normalise_database_url(database_url)
    pending = pending_revisions(url)
    if not pending:
        log.info("migrations up to date")
        return []

    log.info("migrations pending", count=len(pending), revisions=pending)
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            # `pg_advisory_xact_lock`, not `pg_advisory_lock`, and the difference is the
            # whole reason this function exists in the shape it does.
            #
            # A session-level lock is held by a *server* connection. The application talks
            # to PgBouncer in transaction mode, where consecutive statements from one
            # client can land on different server connections, so the lock was taken on
            # one connection and every later statement ran somewhere else. Mutual
            # exclusion was gone and nothing said so: two replicas both ran `upgrade`,
            # both issued `CREATE TABLE alembic_version`, and the loser died with a
            # unique-violation on a system index while the app failed to start.
            #
            # A transaction-scoped lock is held for one transaction, and a transaction is
            # the one thing a transaction pooler will not split across server connections.
            # It also cannot leak: there is no unlock to forget and no path where a
            # crashed replica leaves the lock held.
            #
            # Blocking, not try-lock: a replica that loses the race must wait for the
            # winner rather than start serving against an unmigrated schema.
            conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": MIGRATION_LOCK_ID})

            # Re-check inside the lock. The replica that waited will usually find the work
            # already done, and running `upgrade` regardless would be harmless but would
            # log a migration that did not happen.
            still_pending = pending_revisions(url)
            if not still_pending:
                log.info("migrations applied by another replica")
                conn.rollback()
                return []

            # Alembic runs on *this* connection, inside *this* transaction, which is what
            # puts the migration under the lock. Left to itself it would open a second
            # connection, and through the pooler that is a different server connection
            # again, which is the bug this whole block exists to close.
            cfg = _alembic_config(url)
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            conn.commit()
            log.info("migrations applied", revisions=still_pending)
            return still_pending
    finally:
        engine.dispose()
