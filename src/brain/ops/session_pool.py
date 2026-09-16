"""The workers' session-mode pooler, held to the connection budget it exists to enforce.

The queue needs LISTEN and the checkpointer needs server-side prepared statements, and a
pooler in transaction mode carries neither: a notification arrives on a backend that has been
handed to somebody else, and a statement prepared on one backend is executed on another. So
until 2026-09-16 both workers went straight to `db`, and `brain.session.make_worker_engine`
said in its own docstring that M0.3.5 had asked for a session-mode pooler and this was not one.

**What a session pooler buys is not pooling.** In session mode PgBouncer gives each client one
server connection for as long as the client stays connected, so twenty client connections are
twenty server connections. The application's pooler turns two hundred callers into twenty, and
this one turns twenty into twenty. What it adds is a ceiling counted somewhere other than the
process that declares it. `BRAIN_WORKER_POOL_MAX` is what each worker hands its own driver, and
`docker-compose.worker.yml` lists the one case that bound does not cover: a driver that opens a
connection outside its pool. A second replica of a worker is the other, and it is the ordinary
way to double a declared figure without editing it. `MAX_DB_CONNECTIONS` on the session pooler
counts both workers together, at a process neither of them runs, so either case waits at the
pooler instead of spending the database's ceiling. See
`THE_SESSION_POOLER_IS_A_CEILING_AND_NOT_A_POOL`.

**Every figure on the service is derived from `brain.ops.connections`, and `session_pool_gaps`
refuses one that is not.** The ceiling is the sum of the two workers' declared rows, because
those rows are what the database's budget already counts: `connections.demand_on("db")` stays
correct only while what the pooler admits equals what the rows declare. A ceiling above that is
spare capacity the budget cannot see; a pool below it is the failure with no error at all. See
`A_SESSION_POOL_SMALLER_THAN_ITS_CLIENTS_IS_A_LISTEN_THAT_WAITS`.

**Checked here rather than folded into `brain.ops.connections`.** That module reads connection
strings and declarations and nothing else, and the session pooler reaches `db` through
`DB_HOST`, which is not a connection string, so `undeclared_clients` cannot see it and never
will. Teaching it one image's environment variables would put a vendor's spelling into the
module every other budget reads. This module is the one place that knows the pooler's spelling,
and it states the relation to the budget as a check a test runs over the real compose files.

Rejected: a second database entry on the application's `pgbouncer` with `pool_mode=session`.
The image writes its configuration from environment variables as one wildcard database with
one mode, so a per-database mode needs a hand-written configuration file. That is a bind mount,
which a stored compose resolves to an empty directory (see
`brain.ops.compose.A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE`), or it is a change to the
pooler every request on every install already goes through, for the benefit of a container
only two profiles run. A 64 MiB container is neither.

Rejected: leaving the workers direct. It is correct for LISTEN and it is what shipped until
this module, and the argument against it is only the ceiling above. That argument is enough,
because the one outage this repository has had in its connection budget came from a client
whose bound was its own configuration and nothing else.

What has not happened: the session pooler has never been started. Nothing here has seen a
LISTEN delivered through it or a checkpointer prepare survive it. PgBouncer's documentation says
both work in session mode, and that is where this module's premise comes from.

Task ids: M0.3.5
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import urlsplit

from brain.ops.compose import ComposeFiles
from brain.ops.connections import client_named, database
from brain.ops.queue import POOLER_HOSTNAMES
from brain.ops.wiring import component

#: The service, by the name the workers' connection strings use.
SESSION_POOLER: Final = "pgbouncer-session"

#: The compose file that describes it. Every other file names it without a body.
SESSION_POOLER_FILE: Final = "docker-compose.worker.yml"

#: The services whose connections go through it, which are the budget rows its ceiling sums.
SESSION_POOL_CLIENTS: Final[tuple[str, ...]] = ("brain-worker", "brain-parse-worker")

#: The environment variables on a worker that must reach Postgres through a session.
SESSION_URL_SETTINGS: Final[tuple[str, ...]] = ("QUEUE_URL", "BRAIN_CHECKPOINTER_URL")

#: PgBouncer's spelling of the mode, as the image reads it.
SESSION_MODE: Final = "session"

#: What a client beyond the ceiling waits before PgBouncer refuses it, at most, in seconds.
#:
#: PgBouncer's own default is 120. A worker waiting two minutes for a connection it will never
#: get looks, from outside, exactly like a worker with nothing to do. Thirty is long enough to
#: ride out a restart of the other worker and short enough that a scaled-out worker fails in a
#: log somebody reads the same minute.
MAX_QUERY_WAIT_SECONDS: Final = 30

#: Why the pooler exists at all, given that it pools nothing away.
THE_SESSION_POOLER_IS_A_CEILING_AND_NOT_A_POOL: Final = (
    "In session mode one client connection is one server connection for as long as the client "
    "stays connected, so this pooler saves the database nothing. It is a count kept outside "
    "the workers: BRAIN_WORKER_POOL_MAX bounds what each worker hands its own driver, and a "
    "driver opening a connection outside that pool, or a second replica of a worker, spends "
    "past it without editing it. MAX_DB_CONNECTIONS on the session pooler is where both of "
    "those wait instead of spending the database's ceiling."
)

#: Why the pool cannot be smaller than the demand it serves.
A_SESSION_POOL_SMALLER_THAN_ITS_CLIENTS_IS_A_LISTEN_THAT_WAITS: Final = (
    "A session holds its server connection until the client disconnects, and a queue worker's "
    "LISTEN connection never disconnects. A pool smaller than the declared demand therefore "
    "leaves a worker whose connection is accepted by the pooler and never given a backend: no "
    "error, no notification, and a queue that reads as empty. The ceiling may not be below the "
    "declared rows for the same reason, and may not be above them because the database's "
    "budget counts the rows and would not see the difference."
)

#: Why the workers' session URLs are checked by host rather than by the absence of a pooler.
A_WORKER_ROUTED_ROUND_THE_SESSION_POOLER_IS_OUTSIDE_ITS_CEILING: Final = (
    "The ceiling only counts connections that reach it. A worker whose queue or checkpointer URL "
    "names db directly still works, which is what makes it the mistake to check for: it is "
    "outside the one count this pooler exists to keep, and nothing else would notice."
)


def _services(files: ComposeFiles) -> dict[str, Mapping[str, Any]]:
    """Every described service across the files, later files adding keys to earlier ones.

    A shallow merge by top-level key, which is all this module reads: the environment, the
    profiles and the mode are each read whole from whichever file gives them.
    """
    merged: dict[str, dict[str, Any]] = {}
    for name in files:
        block = files[name].get("services") or {}
        for service, body in block.items():
            if isinstance(body, Mapping):
                merged.setdefault(str(service), {}).update(body)
    return dict(merged)


def _environment(body: Mapping[str, Any]) -> dict[str, str]:
    """A service's environment, from either the mapping or the `KEY=value` list spelling."""
    environment = body.get("environment") or {}
    if isinstance(environment, Mapping):
        return {str(key): str(value) for key, value in environment.items()}
    found: dict[str, str] = {}
    for entry in environment:
        key, _, value = str(entry).partition("=")
        found[key] = value
    return found


def _whole(value: str | None) -> int | None:
    """A setting as a whole number, or None when it is absent or not one."""
    if value is None or not value.strip().isdigit():
        return None
    return int(value)


def declared_demand() -> int:
    """What the two workers' budget rows say they may hold against the database, together."""
    total = 0
    for name in SESSION_POOL_CLIENTS:
        row = client_named(name)
        if row is None:
            msg = f"{name!r} has no row in brain.ops.connections, so its demand is unknown"
            raise KeyError(msg)
        total += row.demand()
    return total


def session_pool_gaps(files: ComposeFiles) -> tuple[str, ...]:
    """Every way these compose documents disagree with the session pooler's reason to exist.

    Returns all of them, in words that name the setting. Empty for a set that does not run the
    workers at all, which is `lite`: a profile with no worker has nothing for the pooler to
    serve, and a finding about it would be a finding about nothing.
    """
    services = _services(files)
    workers = [name for name in SESSION_POOL_CLIENTS if name in services]
    if not workers:
        return ()

    findings: list[str] = []
    pooler = services.get(SESSION_POOLER)
    if pooler is None:
        return (
            f"{', '.join(workers)} run with no {SESSION_POOLER!r} service in this set, so a "
            "LISTEN has either no session pooler to reach or the transaction pooler to lose "
            "its notifications in",
        )

    environment = _environment(pooler)
    mode = environment.get("POOL_MODE", "")
    if mode != SESSION_MODE:
        findings.append(
            f"{SESSION_POOLER!r} runs POOL_MODE={mode or 'unset'!s}; in transaction mode a "
            "LISTEN is moved to another backend between statements and stops being notified, "
            "with no error anywhere"
        )

    target = environment.get("DB_HOST", "")
    try:
        database(target)
    except KeyError:
        findings.append(
            f"{SESSION_POOLER!r} reaches {target or 'nothing'!r}, which brain.ops.connections "
            "does not declare, so the workers' rows count connections against a database this "
            "pooler does not reach"
        )

    demand = declared_demand()
    ceiling = _whole(environment.get("MAX_DB_CONNECTIONS"))
    pool = _whole(environment.get("DEFAULT_POOL_SIZE"))
    clients = _whole(environment.get("MAX_CLIENT_CONN"))
    wait = _whole(environment.get("QUERY_WAIT_TIMEOUT"))

    if ceiling is None:
        findings.append(
            f"{SESSION_POOLER!r} sets no MAX_DB_CONNECTIONS, so it counts nothing. "
            f"{THE_SESSION_POOLER_IS_A_CEILING_AND_NOT_A_POOL}"
        )
    elif ceiling != demand:
        findings.append(
            f"{SESSION_POOLER!r} admits {ceiling} server connections and the workers' rows "
            f"declare {demand}. {A_SESSION_POOL_SMALLER_THAN_ITS_CLIENTS_IS_A_LISTEN_THAT_WAITS}"
        )
    if pool is None or pool < demand:
        findings.append(
            f"{SESSION_POOLER!r} keeps a pool of {pool} against a declared demand of {demand}. "
            f"{A_SESSION_POOL_SMALLER_THAN_ITS_CLIENTS_IS_A_LISTEN_THAT_WAITS}"
        )
    if clients is None or pool is None or clients < pool:
        findings.append(
            f"{SESSION_POOLER!r} accepts {clients} clients against a pool of {pool}, so the "
            "healthcheck and a one-off queue install are refused while the workers are connected"
        )
    if wait is None or wait < 1 or wait > MAX_QUERY_WAIT_SECONDS:
        findings.append(
            f"{SESSION_POOLER!r} makes a client beyond its ceiling wait {wait} seconds; set "
            f"QUERY_WAIT_TIMEOUT between 1 and {MAX_QUERY_WAIT_SECONDS} so a worker past its "
            "budget fails where somebody reads it rather than idling as if the queue were empty"
        )

    wanted = sorted(component(SESSION_POOLER).profiles)
    profiles = sorted(str(one) for one in pooler.get("profiles") or ())
    if profiles != wanted:
        findings.append(
            f"{SESSION_POOLER!r} runs on profiles {profiles} and brain.ops.wiring budgets it on "
            f"{wanted}"
        )

    for worker in workers:
        worker_environment = _environment(services[worker])
        for setting in SESSION_URL_SETTINGS:
            url = worker_environment.get(setting)
            if url is None:
                continue
            host = (urlsplit(url).hostname or "").lower()
            if host in POOLER_HOSTNAMES:
                findings.append(
                    f"{worker!r} sends {setting} through the transaction pooler {host!r}; "
                    "LISTEN and a server-side prepare both need a session"
                )
            elif host != SESSION_POOLER:
                findings.append(
                    f"{worker!r} sends {setting} to {host or 'nothing'!r} rather than "
                    f"{SESSION_POOLER!r}. "
                    f"{A_WORKER_ROUTED_ROUND_THE_SESSION_POOLER_IS_OUTSIDE_ITS_CEILING}"
                )
    return tuple(findings)
