"""Who may open how many database connections, and what happens when nobody decides.

`brain.ops.wiring` governs memory across components: every container declares a limit, the
profile's total is checked against a measured headroom, and a test fails when the sum does not
fit. Connections had no such module, and on 2026-09-07 that cost an outage of exactly the kind
the memory budget exists to prevent.

**What happened, measured rather than reconstructed.** Keycloak's database was configured with
`max_connections=30`. Keycloak's own pool defaults to 100 and nothing capped it, so it opened
every connection the server would give it and held all thirty idle. The next connection was
refused, and the next connection was an administrator trying to find out why:

    FATAL: sorry, too many clients already

The service looked healthy throughout. It was healthy, for one signed-in person. What was gone
was every spare connection, so a backup, a second replica, a migration or a diagnosis would
all have failed, and the failure would have pointed at the database rather than at the setting
that caused it.

**The general shape, which is the reason this module exists rather than a one-line cap.** A
`max_connections` figure is not a budget. It is a refusal threshold, and a refusal threshold
with no client-side bound underneath it is a system that always runs at the threshold. A
budget requires two declarations that must agree: what the server will admit, and what its
clients may ask for. Neither is useful alone, and this repository had the first one five times
over and the second one nowhere.

**Three things this checks, and each is a real failure that has a name.**

Saturation: the clients of one database can, between them, open more than it admits. That is
today's outage, and it locks out administration first because administration is the connection
nobody opens until something is wrong.

Unbounded clients: a client with no declared pool maximum, which is the Keycloak default and
is how saturation arrives without anybody choosing it.

Superuser clients: Postgres keeps `superuser_reserved_connections` back so an administrator can
always get in. That mechanism only works if the application is *not* the superuser. Keycloak
connects as the owner of its own cluster, so its pool consumed the reserved slots too, which is
why there was no way in at all rather than a slow way in.

**One relationship deliberately not a breach, because naming it is worth more.** A database's
declared ceiling has a memory cost: worst case, `shared_buffers + max_connections * work_mem`.
For the application's database that is 512 + 100 * 16 = 2112 MiB against a 2048 MiB container,
so the declared ceiling could not be honoured if it were ever reached. It is safe, and it is
safe entirely because PgBouncer bounds real connections to twenty. That makes the pooler
load-bearing rather than an optimisation, and `THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE` says
so where somebody proposing to remove it will read it. Raising the alarm instead would produce
a check that is red on arrival, and `brain.ops.sweeps` records why those get switched off.

**The budget could not see a client until somebody wrote it down, and for four of them
nobody had.** `CLIENTS` is a declaration, so a service pointed straight at a database in a
compose file is invisible here until a row is added by hand, which is the same silence the
outage above arrived through: Keycloak's pool was undeclared and unbounded and the budget had
nothing to say about it. `undeclared_clients` closes the loop from the other side, over the
compose files rather than over this list, and until 2026-09-09 it named four:
`langfuse-web` and `langfuse-worker` hold `DATABASE_URL` at `db:5432` with no
`connection_limit` anywhere on it, and `brain-worker` and `brain-parse-worker` hold `QUEUE_URL`
and `BRAIN_CHECKPOINTER_URL` there. Every one of them bypasses PgBouncer deliberately and for
a good reason, which is exactly what makes them the case that matters: see
`A_DIRECT_CLIENT_IS_THE_ONE_THE_POOLER_DOES_NOT_BOUND`.

**They are declared now, and the arithmetic moved with them.** `docs/needs-rupash.md` item 41
records the decision of 2026-09-09 and the provenance of every figure, and `Client.why`
carries that sentence on the row itself rather than in a comment beside it, because a comment
is not something a test or a screen can read back. Five each for Langfuse's two, which Prisma
takes as `connection_limit` on the URL; fifteen for `brain-worker`, of which ten is measured
rather than chosen; five for `brain-parse-worker`, which configures no checkpointer at all.
`db` admitted 97 against a declared demand of 20 and now stands at 50, so the spare figure
this module reports has fallen from 77 to 47 and is at last a figure about the host rather
than about the four services missing from it.

**Declaring a number is not the same as the number being true, and the half nobody can
measure is the queue driver's.** Ten of `brain-worker`'s fifteen is
`brain.session.make_worker_engine`, which keeps a pool of five plus five overflow and is in
the code today. The other five is a judgement about a driver nobody has installed, and a
judgement about a pool understates rather than overstates, because the failure nobody writes
down is the one they have not met yet. `brain.ops.worker` refuses to start a container that
has a driver and no declared bound, for that reason and in those words; see
`AN_UNDECLARED_POOL_IS_A_GUESS_AND_A_GUESS_UNDERSTATES` there.

`undeclared_clients` stays out of `connection_breaches` now that it answers nothing, and the
reason has changed with it. It was kept out because it was true on arrival and a check that
is red the day it lands is a check somebody switches off. What keeps it out today is scope:
it has to be handed the deployment, and `connection_breaches` reads declarations and nothing
else. `test_connections.py` pins its answer as the empty set rather than as a count, so the
next service pointed straight at `db` fails a test instead of joining a list.

Scope: declarations and arithmetic. Nothing here opens a connection or reads a server, and it
reads no file either: `undeclared_clients` takes connection strings somebody else parsed out
of the YAML. That is the same split `brain.ops.limits` keeps and for the same reason: a budget
that had to connect to something could not be checked before deploying the thing it is a
budget for.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

#: Why a client that has not declared a pool maximum is refused rather than defaulted.
AN_UNBOUNDED_CLIENT_ALWAYS_RUNS_AT_THE_SERVERS_CEILING: Final = (
    "A max_connections figure is a refusal threshold, not a budget. A client with no bound "
    "of its own opens connections until the server refuses, so the steady state of an "
    "unbounded client is the ceiling, permanently, whatever the load. Keycloak's pool "
    "defaults to 100 against a server admitting 30, and it held all thirty idle within "
    "minutes of first boot. A default here would reproduce that: the whole point is that "
    "somebody has to choose the number."
)

#: Why an application must not connect as the database superuser.
RESERVED_CONNECTIONS_ONLY_RESERVE_FROM_SOMEBODY_ELSE: Final = (
    "Postgres holds superuser_reserved_connections back so an administrator can always get "
    "in when the pool is exhausted. It reserves them from ordinary roles, so an application "
    "connecting as the superuser draws on the reserve like everything else and the mechanism "
    "protects nobody. That is the difference between an incident where the fix is slow and "
    "one where the diagnosis is impossible: on 2026-09-07 Keycloak connected as the owner of "
    "its own cluster and there was no way to query the database that was refusing queries."
)

#: Why the application's database is safe today and would not be without the pooler.
THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE: Final = (
    "The application's database declares max_connections=100 and work_mem=16MB inside a 2048 "
    "MiB container. Worst case that is 512 + 100 * 16 = 2112 MiB, which is more than the "
    "container has, so the declared ceiling could not be honoured if anything ever reached "
    "it. Nothing does, because every client of it is bounded: PgBouncer holds two hundred "
    "callers to twenty server connections, the four services that go round it are bounded at "
    "thirty between them, and the worst case behind all fifty is 1312 MiB. The pooler is "
    "therefore load-bearing rather than an optimisation, and so is every bound beside it: "
    "removing the pooler, or adding a fifth direct client with no bound of its own, turns a "
    "configuration nobody has questioned into an out-of-memory kill under load."
)

#: Why a service that goes round the pooler is the one this budget has to be told about.
A_DIRECT_CLIENT_IS_THE_ONE_THE_POOLER_DOES_NOT_BOUND: Final = (
    "A caller behind PgBouncer is already counted, because two hundred of them are twenty "
    "server connections and PgBouncer is the client this budget declares. A service pointed "
    "straight at the database is not counted by anything: it holds its own pool, that pool "
    "is the only thing bounding it, and if nobody sized it then the server's ceiling is what "
    "bounds it instead. Every direct connection in this repository is deliberate and well "
    "argued, which is the point rather than a mitigation. The queue needs LISTEN and the "
    "checkpointer needs server-side prepared statements, and both of those are the reason a "
    "pooler cannot serve them, so the services that most need to be in this budget are "
    "precisely the ones the pooler is not protecting. THE_POOLER_IS_WHAT_MAKES_THE_CEILING_"
    "SAFE is the other half of the same sentence: the application's declared ceiling costs "
    "more memory than its container has, and it is affordable only while real connections "
    "stay far below it."
)

#: What Postgres holds back for administrators, by default.
#:
#: Not a number chosen here. It is `superuser_reserved_connections`, whose default has been 3
#: for as long as the setting has existed, and the arithmetic below has to match the server's
#: own or the budget describes a different machine.
POSTGRES_RESERVED_CONNECTIONS: Final = 3

#: What a worker's checkpointer engine keeps open, measured rather than chosen.
#:
#: `brain.session.make_worker_engine` is created with `pool_size=5` and `max_overflow=5`, so
#: ten is the most one worker process can hold for saved graph state. It is written here as
#: arithmetic rather than folded into the fifteen below, because the two halves of that figure
#: have completely different standing: this one is in the code and can be read off it, and a
#: test does exactly that. Change the engine and this row is wrong; nothing else would say so.
WORKER_CHECKPOINTER_CONNECTIONS: Final = 10

#: What one worker's queue connection is budgeted at, for both worker containers.
#:
#: The same number in both because it is the same decision: a queue connection is a LISTEN
#: and the fetches that follow it, and it does not scale with slots the way the checkpointer
#: does. It is the half of `brain-worker`'s bound that is a judgement rather than a
#: measurement, because no queue driver is installed and nothing can be read off one. See
#: `brain.ops.worker.AN_UNDECLARED_POOL_IS_A_GUESS_AND_A_GUESS_UNDERSTATES` for what happens
#: on the day a driver arrives and this number turns out to be smaller than the truth.
WORKER_QUEUE_CONNECTIONS: Final = 5


@dataclass(frozen=True)
class Database:
    """One PostgreSQL server, and what it will admit before it starts refusing.

    Carries its memory tuning as well as its connection ceiling because the two are one
    question: `shared_buffers + max_connections * work_mem` is what the ceiling costs if it is
    ever reached, and a ceiling the container cannot afford is a promise the kernel breaks.
    """

    name: str
    max_connections: int
    shared_buffers_mib: int
    work_mem_mib: int
    #: The container's memory limit, which must agree with `wiring.Component.memory_mib`.
    memory_mib: int
    #: Whether this system owns it. A neighbour's database is declared so the arithmetic is
    #: honest about the host, and excluded from anything this system could be asked to fix.
    ours: bool = True
    reserved: int = POSTGRES_RESERVED_CONNECTIONS

    def __post_init__(self) -> None:
        if self.max_connections < 1:
            msg = f"{self.name!r} admits no connections, which is not a database"
            raise ValueError(msg)
        if self.reserved >= self.max_connections:
            msg = (
                f"{self.name!r} reserves {self.reserved} of {self.max_connections} "
                "connections, leaving nothing for the application"
            )
            raise ValueError(msg)

    def admissible(self) -> int:
        """Connections available to applications, after the administrator's reserve."""
        return self.max_connections - self.reserved

    def ceiling_cost_mib(self) -> int:
        """What the declared ceiling would cost in memory if every connection were busy.

        `work_mem` is per sort or hash operation rather than per connection, so this is a
        floor on the worst case rather than the worst case itself. It is the figure worth
        checking anyway: a ceiling that fails this one fails the real one sooner.
        """
        return self.shared_buffers_mib + self.max_connections * self.work_mem_mib


@dataclass(frozen=True)
class Client:
    """One process that opens connections to one database, and how many it may open.

    `pool_max` is per replica and `replicas` multiplies it, because two copies of a service
    each holding a full pool is the arithmetic everybody gets wrong the first time they scale
    something horizontally.

    `why` is required and it is the field this class gained on 2026-09-09, when four rows were
    added at once and each of the four numbers had a different source: one read off a compose
    file, one off an engine in this repository, one off a decision recorded in
    `docs/needs-rupash.md`, and one a judgement about software nobody has installed. Written as
    comments those distinctions survive exactly as long as the next person reading in a hurry.
    """

    name: str
    database: str
    pool_max: int
    #: Where this number came from, in one sentence a reader can check. Not a description of
    #: the client: the provenance of the figure, because a bound with no provenance is a bound
    #: nobody will challenge, and the one that caused the outage was a vendor default nobody
    #: had chosen at all.
    why: str
    replicas: int = 1
    #: True when this client connects as the owner or superuser of its database. See
    #: `RESERVED_CONNECTIONS_ONLY_RESERVE_FROM_SOMEBODY_ELSE`.
    connects_as_superuser: bool = False

    def __post_init__(self) -> None:
        if self.pool_max < 1:
            msg = (
                f"{self.name!r} declares no pool maximum; an unbounded client runs at its "
                "server's ceiling for ever, which is how a database with spare capacity on "
                "paper has none in practice"
            )
            raise ValueError(msg)
        if self.replicas < 1:
            msg = f"{self.name!r} declares {self.replicas} replicas"
            raise ValueError(msg)
        if not self.why.strip():
            msg = (
                f"{self.name!r} declares a pool of {self.pool_max} and no reason for it; a "
                "connection bound whose provenance is nowhere is one nobody can check and "
                "nobody will argue with, which is how a number stays wrong"
            )
            raise ValueError(msg)

    def demand(self) -> int:
        """Connections this client can hold open across all of its replicas."""
        return self.pool_max * self.replicas


#: Every PostgreSQL on the deployment host, measured on 2026-09-07 rather than declared from
#: the compose files, because two of them belong to other projects and one of ours had drifted.
DATABASES: Final[tuple[Database, ...]] = (
    Database(
        # The application's own. Fronted by PgBouncer in transaction mode, which is what
        # makes the ceiling affordable: see THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE.
        name="db",
        max_connections=100,
        shared_buffers_mib=512,
        work_mem_mib=16,
        memory_mib=2048,
    ),
    Database(
        # Keycloak's. `work_mem` was never set here and 4 MiB is the server default, which is
        # the figure the arithmetic has to use: an unset setting is still a setting, and
        # writing it down is how the budget stops depending on somebody remembering.
        name="keycloak-db",
        max_connections=30,
        shared_buffers_mib=64,
        work_mem_mib=4,
        memory_mib=256,
    ),
)


#: Everything that opens a connection to one of the databases above.
#:
#: Six rows, of which four were added on 2026-09-09 and none of the four is deployed yet. That
#: is the point rather than a caveat: a bound chosen before a service starts is a decision, and
#: the same bound chosen after it starts is an incident review. See `Client.why` on each.
CLIENTS: Final[tuple[Client, ...]] = (
    Client(
        name="pgbouncer",
        database="db",
        pool_max=20,
        why=(
            "DEFAULT_POOL_SIZE in docker-compose.yml, held equal to it by test. Transaction "
            "mode is what makes it enough: twenty server connections serve two hundred "
            "callers, which is also why nothing behind the pooler is declared here as well"
        ),
    ),
    Client(
        name="keycloak",
        database="keycloak-db",
        pool_max=15,
        why=(
            "KC_DB_POOL_MAX_SIZE in docker-compose.keycloak.yml, held equal to it by test. "
            "Before 2026-09-07 it was unset, which meant Keycloak's own default of 100 "
            "against a server admitting 30, and that is the outage this module exists for"
        ),
        connects_as_superuser=True,
    ),
    Client(
        name="langfuse-web",
        database="db",
        pool_max=5,
        why=(
            "A trace interface rather than anything on the request path, so five serves a "
            "browser. Prisma takes it as connection_limit on DATABASE_URL in "
            "docker-compose.langfuse.yml, and without it Prisma sizes the pool from the "
            "host's core count, which is a number about the machine and not about the work"
        ),
    ),
    Client(
        name="langfuse-worker",
        database="db",
        pool_max=5,
        why=(
            "Batched ingestion with one writer, so five is the batch in flight and room "
            "beside it. Prisma takes it as connection_limit on DATABASE_URL in "
            "docker-compose.langfuse.yml, the same way the interface above does"
        ),
    ),
    Client(
        name="brain-worker",
        database="db",
        pool_max=WORKER_CHECKPOINTER_CONNECTIONS + WORKER_QUEUE_CONNECTIONS,
        why=(
            "Ten of it is measured: brain.session.make_worker_engine keeps a pool of five "
            "plus five overflow for the checkpointer, which goes straight to the database "
            "because a saver prepares statements server-side. Five more for the queue "
            "connection, which is a judgement rather than a measurement while no driver is "
            "installed. BRAIN_WORKER_POOL_MAX in docker-compose.worker.yml carries the total "
            "to the container, and brain.ops.worker refuses to start one that has a driver "
            "and no such declaration"
        ),
    ),
    Client(
        name="brain-parse-worker",
        database="db",
        pool_max=WORKER_QUEUE_CONNECTIONS,
        why=(
            "A queue connection and nothing else: this container sets no "
            "BRAIN_CHECKPOINTER_URL, because a parse is not a graph, so it has none of the "
            "ten the general worker's checkpointer keeps. BRAIN_WORKER_POOL_MAX in "
            "docker-compose.parse-worker.yml carries it to the container"
        ),
    ),
)


def database(name: str) -> Database:
    """One declared database, by name, refusing an unknown one rather than answering None."""
    for one in DATABASES:
        if one.name == name:
            return one
    msg = f"no database named {name!r}; known: {[one.name for one in DATABASES]}"
    raise KeyError(msg)


def clients_of(name: str) -> tuple[Client, ...]:
    """Every declared client of one database."""
    return tuple(one for one in CLIENTS if one.database == name)


def client_named(name: str) -> Client | None:
    """One declared client by name, or None when this budget has never heard of it.

    None rather than the refusal `database` makes about an unknown name, and the asymmetry is
    deliberate. A database nobody declared cannot be budgeted at all, so asking about one is a
    mistake worth raising on. A client nobody declared is the ordinary case for anything behind
    the pooler and for any container a future deployment adds, and a caller checking whether a
    container's environment agrees with this budget has to be able to ask about a container
    that is not in it.
    """
    for one in CLIENTS:
        if one.name == name:
            return one
    return None


def demand_on(name: str) -> int:
    """Connections every client of this database can hold open at once."""
    return sum(one.demand() for one in clients_of(name))


def headroom_on(name: str) -> int:
    """Connections left for anything undeclared: a backup, a migration, a diagnosis.

    The figure that was zero during the outage. It is reported rather than merely checked,
    because "how much room is there" is the question somebody asks before adding a client and
    the answer should not require reading two compose files.
    """
    return database(name).admissible() - demand_on(name)


def connection_breaches() -> tuple[str, ...]:
    """Every way the declared connection budget does not hold, in words an operator can act on.

    Returns rather than raises, and returns all of them, for the reason
    `brain.ops.wiring.budget_breaches` gives: a check that stops at the first problem is three
    deploys' worth of learning delivered one sentence at a time.
    """
    found: list[str] = []

    for one in DATABASES:
        if not one.ours:
            continue
        wanted = demand_on(one.name)
        spare = one.admissible() - wanted
        if wanted > one.admissible():
            found.append(
                f"{one.name!r} admits {one.admissible()} connections after its reserve and "
                f"its clients can open {wanted}; the excess is refused, and the first thing "
                "refused is whoever is trying to find out why"
            )
        elif spare == 0:
            found.append(
                f"{one.name!r} has no spare connection at all: its clients can open exactly "
                f"the {one.admissible()} it admits, so a backup, a migration or a diagnosis "
                "has nowhere to connect from"
            )

        if not clients_of(one.name):
            found.append(
                f"{one.name!r} has no declared client, so either nothing uses it or "
                "something does and this budget cannot see it"
            )

    for client in CLIENTS:
        if client.connects_as_superuser:
            found.append(
                f"{client.name!r} connects to {client.database!r} as its superuser, so the "
                f"{database(client.database).reserved} connections Postgres holds back for "
                "administrators are drawn from the same pool and reserve nothing"
            )

    return tuple(found)


def ceiling_costs() -> tuple[str, ...]:
    """Databases whose declared ceiling their container could not afford if it were reached.

    Separate from `connection_breaches` and deliberately not part of it. The application's
    database is in this list today and is not in danger, because PgBouncer bounds real
    connections far below the ceiling. Folding the two together would make the breach check
    red on arrival, and `brain.ops.sweeps` records at length why a gate that is red the day it
    lands is a gate somebody switches off.

    What this is for is the day a second client is pointed straight at that database. Then the
    ceiling stops being theoretical and this sentence is already written.
    """
    return tuple(
        f"{one.name!r} declares {one.max_connections} connections costing at worst "
        f"{one.ceiling_cost_mib()} MiB against a {one.memory_mib} MiB container; it is "
        f"affordable only because its clients are bounded to {demand_on(one.name)}"
        for one in DATABASES
        if one.ours and one.ceiling_cost_mib() > one.memory_mib
    )


def direct_database_in(url: str) -> str | None:
    """The database this connection string reaches without a pooler in the way, or None.

    None for a pooler, and that is the useful half rather than an omission: a caller behind
    PgBouncer is already in this budget as PgBouncer, whose whole purpose is that many callers
    become twenty server connections. Counting the caller as well would budget the same
    connections twice and would refuse a deployment that is correct.

    None for anything that is not one of *our* declared databases too, including a neighbour's
    server declared here only so the arithmetic about the host is honest, and a Redis URL that
    happens to sit in the same environment block. A hostname this module has never heard of is
    somebody else's server and there is nothing here that could budget it.

    **The `jdbc:` prefix is stripped and that is not tidiness.** `urlsplit` reads `jdbc:` as
    the scheme and everything after it as an opaque path, so a JDBC URL has no hostname at
    all and `KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak` came back as nothing.
    Keycloak happens to be declared, so this reported the right answer for the wrong reason,
    which is the shape `brain.ops.sweeps` keeps finding: a check that is green because it
    never looked. The next JVM service pointed at one of these databases would have been
    invisible.
    """
    text = url.strip()
    if text.lower().startswith("jdbc:"):
        text = text[len("jdbc:") :]
    try:
        host = urlsplit(text).hostname
    except ValueError:
        # A connection string this cannot parse is reported as nothing rather than raised on.
        # A compose environment holds passwords with substitution markers in them, and a
        # budget that refused to run because one of them was unusual would be a budget nobody
        # runs.
        return None
    if host is None:
        return None
    return host if any(one.name == host and one.ours for one in DATABASES) else None


def undeclared_clients(connections: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """Every service holding a direct connection string that `CLIENTS` does not budget.

    The check that reads the deployment rather than the declaration, which is the direction
    the outage came from. `connection_breaches` asks whether the declared clients of a
    database can outnumber its slots; it cannot ask about a client nobody declared, and an
    undeclared client is what saturated Keycloak's database. See
    `A_DIRECT_CLIENT_IS_THE_ONE_THE_POOLER_DOES_NOT_BOUND`.

    Takes a service name against the connection strings it holds, parsed by the caller, for
    the reason the module docstring gives about scope. The test suite reads them out of the
    compose files with `yaml.safe_load`, so what is checked is the deployment rather than a
    second copy of it kept here.

    Deliberately not part of `connection_breaches`, and the reason changed on 2026-09-09 when
    the four services it used to name were declared. It was kept out because it was true on
    arrival, and `brain.ops.sweeps` records at length how a gate that is red the day it lands
    comes to be switched off. It stays out now for scope: this function has to be handed the
    deployment, and `connection_breaches` reads declarations and opens nothing. What pins the
    answer is a test asserting the exact set, which is empty today, so the next service pointed
    straight at a database fails a test rather than joining a list nobody reads.
    """
    budgeted = {(one.name, one.database) for one in CLIENTS}
    found: list[str] = []
    for service in sorted(connections):
        for name in sorted({d for url in connections[service] if (d := direct_database_in(url))}):
            if (service, name) in budgeted:
                continue
            found.append(
                f"{service!r} connects straight to {name!r} and no Client declares it, so "
                f"whatever pool it opens is outside this budget. {name!r} reports "
                f"{headroom_on(name)} spare connections and that figure does not know about it"
            )
    return tuple(found)
