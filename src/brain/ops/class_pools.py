"""Three connection pools, one per workload class, and the rule for when a process uses them.

`brain.ops.admission` has said since M22.2.1 that the database is shared by three classes and
how its slots should be split between them (`POOL_SHARE`, `pools_for`), and until this module
nothing built a pool from that split. Every process reached PostgreSQL through the one
transaction-mode PgBouncer at twenty server connections, so a connector sync holding fifteen of
them for a minute was fifteen connections a person's question could not have. **The class
ceilings decide how much work a class may start; only separate pools decide whether the work it
started can hold a connection the request path needs**, which is the sentence `ClassPools`
already carries and nothing honoured.

**The pools are a second PgBouncer the release starts, never a change to the first.** The first
one is in the compose file Coolify keeps its own copy of, and its image writes its configuration
from environment variables as one wildcard database with one pool size, so per-class pools need a
hand-written configuration and a release can change neither. So the class pooler is an overlay
(`brain.ops.overlays`), started beside the application by `ops/deploy/overlays/apply.sh` on every
deploy, with its configuration written by `class-pools.prepare.sh` from `render_ini` here. It is
the only overlay that is always on: class isolation is how the product behaves, not a service an
administrator chooses. It is still costed, and a server with no room for it is told so in words.
Rejected: a hand edit of the stored compose file (true on one server, absent from the next
company's), and three poolers (three containers and three healthchecks for what one
configuration file says).

**Nothing depends on it running.** A process uses its class's pooler only when the deploy step's
stored observation for this release says the pooler is running and healthy, and otherwise stays
on the pooler it already had. See
`A_PROCESS_USES_ITS_CLASS_POOLER_ONLY_WHEN_THIS_RELEASE_SAW_IT_RUNNING`. That is read again every
minute, because the step writes it after the application is already serving: a decision taken
once at start would never see a pooler started after it, and a pooler that stops is a minute of
failed requests rather than an outage.

**The class URL is derived from the URL a process already has, and no variable names it**, the
way `brain.ops.queue.queue_url_for` derives the queue's: the class pooler's service name as the
host, the class's database name, the login kept. Only a connection through the transaction
pooler moves (`ONLY_A_CONNECTION_THROUGH_THE_TRANSACTION_POOLER_MOVES`), so the queue's LISTEN,
the checkpointer's prepared statements and the session-level locks stay on `pgbouncer-session`,
and a URL straight to the database stays where it is.

**The three pools split the existing pooler's twenty and are not given twenty each.** Traffic
moves from the old pooler to these, so the old one's server connections fall idle and
`server_idle_timeout` closes them. `brain.ops.connections` counts the two poolers as one budget
for that reason, and says what that leaves uncovered:
`TWO_POOLERS_FOR_ONE_TRAFFIC_ARE_ONE_BUDGET`.

**A pool is bounded per database across logins**, because
PgBouncer's `pool_size` is per login and database pair: the application as `brain_app` and the
schedule as the owner would otherwise hold twice a class's share. See
`A_CLASS_SHARE_IS_BOUNDED_ACROSS_LOGINS`.

What only an install proves: that PgBouncer reads this configuration, that the application and
the worker reach the pooler by name over the database's network, and that a batch transaction
holding its share leaves an interactive one running at once. The install check
`brain.ops.acceptance_checks_class_pools` asks exactly that of the running pooler; the tests here
parse what is rendered and hold every figure against the files it has to agree with.

Task ids: M22.2.2
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

import structlog
from sqlalchemy.engine import make_url

from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.ops.admission import ClassPools, WorkloadClass, pools_for, workload_class_for
from brain.ops.overlays import OBSERVED_KEY, seen_in
from brain.ops.queue import POOLER_HOSTNAMES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

log = structlog.get_logger(__name__)

#: The class pooler's service name in `ops/deploy/overlays/class-pools.yml`, and the host every
#: class URL names. A test holds the two equal.
CLASS_POOLER: Final = "pgbouncer-classes"

#: The port it listens on, inside the server's network only (`expose`, never `ports`).
CLASS_POOLER_PORT: Final = 5432

#: The server connections the existing pooler is given, `DEFAULT_POOL_SIZE` in
#: `docker-compose.yml`, and the slots `pools_for` splits. A test holds it equal to that file and
#: to the `pgbouncer` row of `brain.ops.connections`, so the split cannot drift from the pool it
#: is a split of.
POOLER_SLOTS: Final = 20

#: Each class's share of those slots, from the one function that decides it.
POOLS: Final[ClassPools] = pools_for(POOLER_SLOTS)

#: The database the class pooler's entries point at, as the application's database is named on
#: the server's network. The same `DB_HOST` the existing pooler is given, held equal by test.
DATABASE_SERVICE: Final = "db"
DATABASE_PORT: Final = 5432

#: The client connections the class pooler accepts, the existing pooler's figure. The clients are
#: the same processes, moved, so a smaller figure would refuse what the old one admitted.
MAX_CLIENT_CONN: Final = 200

#: The name a client gives for each class. A pooler database entry rather than a real database:
#: each points at the application's one database with its own pool.
CLASS_DATABASE: Final[Mapping[WorkloadClass, str]] = MappingProxyType(
    {one: f"brain_{one.value}" for one in WorkloadClass}
)

#: The lookup the existing poolers run for a login the userlist does not hold, as PgBouncer reads
#: it. The same query, so `brain_app` is admitted here exactly as it is there and a role that
#: could read past row-level security never is. Held equal to `docker-compose.yml` by test.
AUTH_QUERY: Final = (
    "SELECT rolname, CASE WHEN rolvaliduntil < now() THEN NULL ELSE rolpassword END "
    "FROM pg_authid WHERE rolname = $1 AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls"
)

#: The lane a queued job runs in, whatever enqueued it.
QUEUED_LANE: Final = Lane.TASK

#: Why a queued job is classed through `workload_class_for` with the task lane.
A_QUEUED_JOB_IS_TASK_LANE_WORK: Final = (
    "A job taken off the queue has nobody watching it finish: whoever enqueued it was answered "
    "when it was enqueued. That is the task lane's definition, so a queued job is classed by "
    "admission.workload_class_for over its own traffic class and the task lane, which can only "
    "lower a class and never promotes a job onto the request path's pool."
)

#: Why a process does not simply use the class pooler.
A_PROCESS_USES_ITS_CLASS_POOLER_ONLY_WHEN_THIS_RELEASE_SAW_IT_RUNNING: Final = (
    "The class pooler is started by the deploy step after the application is serving, can be "
    "refused for want of memory, and can fail to start. A process that assumed it would lose "
    "its database on every one of those. So a process uses its class's pooler only while the "
    "step's stored observation for the release this process is running says that pooler is "
    "running and healthy, reads that again every minute, and otherwise stays on the pooler it "
    "already had, which every install runs. A report from another release is no report: it "
    "describes containers this release may not have."
)

#: Why only a connection through the transaction pooler is moved.
ONLY_A_CONNECTION_THROUGH_THE_TRANSACTION_POOLER_MOVES: Final = (
    "The class pools are transaction pools. A connection that needs session state, the queue's "
    "LISTEN, the checkpointer's prepared statements or a session-level advisory lock, goes to "
    "pgbouncer-session for that reason and must stay there, and a connection straight to the "
    "database belongs to something that chose to go round every pooler. So a URL is moved only "
    "when its host is a transaction pooler, and every other URL is returned as it came."
)

#: Why each entry carries `max_db_connections` as well as `pool_size`.
A_CLASS_SHARE_IS_BOUNDED_ACROSS_LOGINS: Final = (
    "PgBouncer's pool_size is per pair of database and login, and two logins use these pools: "
    "the application as brain_app and the schedule as the owner. With pool_size alone a class "
    "could hold its share once per login, twice what was split. max_db_connections on the entry "
    "bounds the class across every login, so the three entries together never hold more than "
    "the slots they were split from."
)

#: How often a process reads the observation again. Once a minute is the cadence every other
#: re-read in the application keeps (`brain.ops.install_settings.HOLD_EVERY`).
FOLLOW_EVERY: Final = timedelta(minutes=1)

#: Characters a password cannot carry into the pooler's userlist or the step's environment file.
_UNCARRIABLE: Final = re.compile(r"['\"\\\r\n]")

#: What a login name may be before it is written into the configuration.
_LOGIN: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ClassPoolError(Exception):
    """A configuration that cannot be written as asked, said in words the deploy journal shows."""


# --------------------------------------------------------------------- the URL a class uses
def class_url_of(url: str, workload: WorkloadClass) -> str | None:
    """`url` moved to `workload`'s pool, or None when it is not a URL that moves.

    The login, the password, the driver and the query are kept; the host becomes the class
    pooler and the database its class's entry. See
    `ONLY_A_CONNECTION_THROUGH_THE_TRANSACTION_POOLER_MOVES`.
    """
    text = url.strip()
    if not text:
        return None
    try:
        parsed = make_url(text)
    except Exception:
        # A URL nothing can parse is not moved: the engine will refuse it where it is, in the
        # words it already has for that.
        return None
    if (parsed.host or "").lower() not in POOLER_HOSTNAMES:
        return None
    moved = parsed.set(host=CLASS_POOLER, port=CLASS_POOLER_PORT, database=CLASS_DATABASE[workload])
    return moved.render_as_string(hide_password=False)


def routed_url(url: str, workload: WorkloadClass, *, running: bool) -> str:
    """The URL a process in `workload` connects with: its class's while the pooler runs.

    See `A_PROCESS_USES_ITS_CLASS_POOLER_ONLY_WHEN_THIS_RELEASE_SAW_IT_RUNNING`.
    """
    if not running:
        return url
    return class_url_of(url, workload) or url


def queued_class(traffic: TrafficClass) -> WorkloadClass:
    """The class a queued job's connections are in. See `A_QUEUED_JOB_IS_TASK_LANE_WORK`."""
    return workload_class_for(traffic, QUEUED_LANE)


# ------------------------------------------------------------ whether the pooler is running
def runs_here(observed: object, *, commit: str) -> bool:
    """Whether a stored observation says the class pooler runs, healthy, on release `commit`."""
    seen = seen_in(observed, commit=commit)
    if seen is None:
        return False
    one = seen.get(CLASS_POOLER)
    return one is not None and (one.state, one.health) == ("running", "healthy")


async def observed_running(sessions: async_sessionmaker[AsyncSession], *, commit: str) -> bool:
    """`runs_here` over the stored row, read through `sessions`; False when it cannot be read.

    Never raises. A database that does not answer is a reason to stay on the pooler every install
    runs, and a process that moved to the class pooler and then cannot read through it is moved
    back by exactly this False.
    """
    from brain.ops.setting_store import read_namespace

    try:
        async with sessions() as session:
            held = await read_namespace(session, OBSERVED_KEY.split(".", 1)[0])
    except Exception as error:
        log.warning("class_pools.unread", error=type(error).__name__)
        return False
    row = held.get(OBSERVED_KEY)
    return row is not None and runs_here(row.value, commit=commit)


@dataclass
class Routing:
    """What one process last read about its class pooler, shared by everything in it that connects.

    Starts not running, which is the pooler every install has. Only `refresh` changes it.
    """

    commit: str
    running: bool = False

    def url(self, url: str, workload: WorkloadClass) -> str:
        """`routed_url` with what this process last read."""
        return routed_url(url, workload, running=self.running)

    async def refresh(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        reader: Callable[..., Awaitable[bool]] = observed_running,
    ) -> bool:
        """Read the observation again and hold the answer."""
        self.running = await reader(sessions, commit=self.commit)
        return self.running


class Follower:
    """A session factory that moves onto its class's pooler and back as the observation changes.

    The factory is the one every caller already holds, reconfigured in place, so nothing that was
    handed it has to be told: a session opened after a move connects through the new engine, and
    one already open finishes on the engine it began on. The engines are `NullPool`, so the old
    one holds nothing once its sessions close.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        url: str,
        workload: WorkloadClass,
        make_engine: Callable[[str], AsyncEngine] | None = None,
    ) -> None:
        from brain.session import make_app_engine

        self._sessions = sessions
        self._url = url
        self._workload = workload
        self._make = make_engine or make_app_engine
        self._home = sessions.kw.get("bind")
        self.moved: AsyncEngine | None = None

    async def follow(self, running: bool) -> bool:
        """Move to the class pooler when it runs and home when it does not; True while moved."""
        target = routed_url(self._url, self._workload, running=running)
        if target != self._url and self.moved is None:
            self.moved = self._make(target)
            self._sessions.configure(bind=self.moved)
            log.info("class_pools.moved", workload=self._workload.value, pooler=CLASS_POOLER)
        elif target == self._url and self.moved is not None:
            await self.close()
            log.info("class_pools.home", workload=self._workload.value)
        return self.moved is not None

    async def close(self) -> None:
        """Back to the engine the factory was built with, and the moved one disposed."""
        if self.moved is None:
            return
        self._sessions.configure(bind=self._home)
        moved, self.moved = self.moved, None
        await moved.dispose()


async def keep_following(
    sessions: async_sessionmaker[AsyncSession],
    *,
    url: str,
    workload: WorkloadClass,
    commit: str,
    every: timedelta = FOLLOW_EVERY,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    rounds: int | None = None,
    reader: Callable[..., Awaitable[bool]] = observed_running,
    make_engine: Callable[[str], AsyncEngine] | None = None,
) -> None:
    """A process's sessions following its class pooler, read now and then every `every`.

    Reads first rather than waiting, so a process restarted on a release whose pooler already
    runs moves at once. Leaves the factory on its own engine when cancelled. `rounds`, `reader`
    and `make_engine` are for a test.
    """
    routing = Routing(commit=commit)
    follower = Follower(sessions, url=url, workload=workload, make_engine=make_engine)
    done = 0
    try:
        while rounds is None or done < rounds:
            await follower.follow(await routing.refresh(sessions, reader=reader))
            done += 1
            if rounds is not None and done >= rounds:
                break
            await sleep(every.total_seconds())
    finally:
        await follower.close()


# ------------------------------------------------------------------- what the pooler reads
def render_ini(*, database: str, auth_user: str, pools: ClassPools = POOLS) -> str:
    """The class pooler's whole configuration: one entry per class, transaction mode.

    `database` is the application's database as the server names it and `auth_user` the owner
    login the userlist holds, which runs `AUTH_QUERY` for every other login. Neither is a secret,
    and nothing here is handed one: the password reaches the pooler through the step's
    environment file and the image's own userlist. See `A_CLASS_SHARE_IS_BOUNDED_ACROSS_LOGINS`
    for why each entry carries two sizes.
    """
    for name, value in (("database", database), ("auth_user", auth_user)):
        if not _LOGIN.match(value):
            msg = f"{value!r} is not a {name} the class pooler's configuration can name"
            raise ClassPoolError(msg)
    if "%" in AUTH_QUERY:
        # PgBouncer reads no interpolation, but a percent sign in a configuration this file is
        # copied beside is the next person's format string. Kept out, as the image's is.
        msg = "the lookup query carries a percent sign"
        raise ClassPoolError(msg)
    entries = [
        f"{CLASS_DATABASE[one]} = host={DATABASE_SERVICE} port={DATABASE_PORT} "
        f"dbname={database} auth_user={auth_user} "
        f"pool_size={pools.slots_for(one)} max_db_connections={pools.slots_for(one)}"
        for one in WorkloadClass
    ]
    settings = {
        # Every address inside its own container, which `expose` and the networks it is on bound;
        # PgBouncer's `*` for that.
        "listen_addr": "*",
        "listen_port": str(CLASS_POOLER_PORT),
        "unix_socket_dir": "",
        "auth_type": "scram-sha-256",
        "auth_file": "/etc/pgbouncer/userlist.txt",
        "auth_query": AUTH_QUERY,
        "pool_mode": "transaction",
        "max_client_conn": str(MAX_CLIENT_CONN),
        "ignore_startup_parameters": "extra_float_digits",
        # A client waiting for its class's pool is told so after thirty seconds rather than
        # PgBouncer's two minutes, as the session pooler's are.
        "query_wait_timeout": "30",
    }
    return (
        ";; Written by the release (brain.ops.class_pools.render_ini) on every deploy.\n"
        ";; An edit here is replaced by the next one.\n"
        "[databases]\n"
        + "".join(f"{one}\n" for one in entries)
        + "\n[pgbouncer]\n"
        + "".join(f"{key} = {value}\n" for key, value in settings.items())
    )


def owner_login_lines(url: str) -> str:
    """The owner login as two lines of the step's environment file, single-quoted.

    The image writes the userlist from `DB_USER` and `DB_PASSWORD`, which the compose file reads
    from these two lines. Refuses, in words naming no value, a password a userlist or an
    environment file cannot carry: the class pools are then not prepared and every process stays
    on the pooler it has.
    """
    try:
        parsed = make_url(url.strip())
    except Exception as error:
        msg = "the owner's connection string could not be read"
        raise ClassPoolError(msg) from error
    user = parsed.username or ""
    password = parsed.password or ""
    if not _LOGIN.match(user):
        msg = "the owner's connection string names no login the class pooler can be given"
        raise ClassPoolError(msg)
    if not password or _UNCARRIABLE.search(str(password)):
        msg = (
            "the owner's password is empty or holds a quote, a backslash or a line break, which "
            "the pooler's userlist cannot carry"
        )
        raise ClassPoolError(msg)
    return f"BRAIN_CLASS_POOL_OWNER='{user}'\nBRAIN_CLASS_POOL_OWNER_PASSWORD='{password}'\n"


# ------------------------------------------------------------------------------ the command
def main(argv: Sequence[str] | None = None) -> int:
    """`ini --database NAME` or `owner-login`, run by the preparation inside the application.

    Both read the owner login through `Settings.owner_database_url`, the one reader of it. A
    refusal exits 1 with a `SAY` line naming no value, and the preparation then fails, which
    leaves the class pooler out of that deploy and every process where it was.
    """
    from brain.settings import Settings

    args = list(sys.argv[1:] if argv is None else argv)
    try:
        owner = Settings().owner_database_url()
        if not owner:
            msg = "neither BRAIN_MIGRATION_DATABASE_URL nor DATABASE_URL is set"
            raise ClassPoolError(msg)
        if args == ["owner-login"]:
            sys.stdout.write(owner_login_lines(owner))
            return 0
        if len(args) == 3 and args[:2] == ["ini", "--database"]:
            user = make_url(owner).username or ""
            sys.stdout.write(render_ini(database=args[2], auth_user=user))
            return 0
    except ClassPoolError as error:
        print(f"SAY the class pools are not prepared: {error}")
        return 1
    print(
        "usage: python -m brain.ops.class_pools ini --database NAME\n"
        "       python -m brain.ops.class_pools owner-login",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
