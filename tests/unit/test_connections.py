"""The connection budget, held to the outage that produced it.

On 2026-09-07 Keycloak opened every connection its database would give it and held all thirty
idle. The next connection was refused and the next connection was an administrator trying to
diagnose it. Every test here is about one of the three ways that happens: a client with no
bound, a server whose clients can outnumber its slots, and an application connecting as the
superuser so the administrator's reserve reserves nothing.

The declarations are checked against the compose files they describe rather than trusted,
because a budget that has drifted from what is deployed is worse than none: it is a number
somebody will believe.

Six clients are declared and four of them arrived on 2026-09-09, before any of the four had
ever been started. Each of those four bounds is asserted against something outside the
declaration that carries it: a `connection_limit` on a URL, a variable in a container's
environment, and the pool `brain.session.make_worker_engine` keeps. A test comparing a bound
against the constant it is written from would pass for every value that constant could hold,
which is the trap `CLAUDE.md` records three authors falling into in one afternoon.

Task ids: none
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from brain.ops.connections import (
    A_DIRECT_CLIENT_IS_THE_ONE_THE_POOLER_DOES_NOT_BOUND,
    POSTGRES_RESERVED_CONNECTIONS,
    THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE,
    WORKER_CHECKPOINTER_CONNECTIONS,
    Client,
    Database,
    ceiling_costs,
    client_named,
    clients_of,
    connection_breaches,
    database,
    demand_on,
    direct_database_in,
    headroom_on,
    undeclared_clients,
)

REPO = Path(__file__).resolve().parents[2]


def compose(name: str) -> dict[str, Any]:
    return yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}


def every_connection_string() -> dict[str, list[str]]:
    """Every compose service against the environment values it carries, over every file.

    All of them rather than the deployed ones, because a compose file that is not composed
    today is exactly the thing this is watching: the trace ledger and the two workers are
    written, sized and unstarted, and the moment somebody starts one the pool it opens is
    real. Read with `yaml.safe_load` rather than grepped, so a connection string inside a
    comment is not a client.
    """
    services: dict[str, list[str]] = {}
    for path in sorted(REPO.glob("docker-compose*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, body in (raw.get("services") or {}).items():
            environment = body.get("environment") or {}
            values = environment.values() if isinstance(environment, dict) else environment
            services.setdefault(name, []).extend(str(one) for one in values)
    return services


def connection_limit_on(url: str) -> int:
    """Prisma's pool maximum, read off a connection string the way Prisma reads it.

    A query parameter rather than an environment variable, because that is the only place
    Prisma takes one. Parsed rather than matched with a substring, so a limit written into the
    password or into a comment is not a limit.
    """
    values = parse_qs(urlsplit(url).query).get("connection_limit", [])
    assert len(values) == 1, f"no single connection_limit on {url!r}: {values}"
    return int(values[0])


def pool_max_declared_by(name: str, service: str) -> int:
    """`BRAIN_WORKER_POOL_MAX` out of one worker's compose file."""
    environment = compose(name)["services"][service]["environment"]
    assert "BRAIN_WORKER_POOL_MAX" in environment, f"{service} declares no connection bound"
    return int(environment["BRAIN_WORKER_POOL_MAX"])


def worker_engine_pool() -> dict[str, int]:
    """What `brain.session.make_worker_engine` passes to `create_async_engine`, from its source.

    Read out of the source rather than off a constructed engine, and that is a deliberate
    choice rather than laziness: `pool_size` is available on the pool object and `max_overflow`
    is not, so an engine-based version would reach into a private attribute and would break on
    a SQLAlchemy release rather than on a change to this repository. This is the technique
    `tests/invariants/test_single_implementation.py` uses for the same reason.

    Fails loudly when the call stops naming both as literals, because the day somebody moves
    them into a variable is the day this stops watching the number it exists to watch.
    """
    tree = ast.parse((REPO / "src" / "brain" / "session.py").read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "make_worker_engine"):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            for keyword in call.keywords:
                if keyword.arg not in {"pool_size", "max_overflow"}:
                    continue
                assert isinstance(keyword.value, ast.Constant), keyword.arg
                assert isinstance(keyword.arg, str)
                assert isinstance(keyword.value.value, int)
                found[keyword.arg] = keyword.value.value
    assert set(found) == {"pool_size", "max_overflow"}, (
        f"make_worker_engine no longer passes both as literals: {found}"
    )
    return found


def setting(command: list[str], key: str) -> str:
    """One `-c key=value` out of a Postgres command line, or a failure naming what is missing.

    Read out of the compose rather than restated here, so the budget is checked against the
    deployment instead of against itself.
    """
    for one in command:
        if one.startswith(f"{key}="):
            return one.split("=", 1)[1]
    pytest.fail(f"{key} is not set on the command line: {command}")


# --- the outage, as three properties -------------------------------------------------------


def test_no_client_can_open_more_connections_than_its_server_admits() -> None:
    """**The outage, in one line.** Keycloak's pool defaulted to 100 against a server admitting
    30, so it took every slot and held them idle. The service stayed healthy for the one person
    signed in and nothing else could connect at all.

    Asserted per database rather than in aggregate, because connections are not fungible
    across servers and a total that balances can still hide one saturated database.

    Delete this and a client's pool and a server's ceiling drift apart again, and the symptom
    is an administrator who cannot connect to the database that is refusing connections."""
    for one in (database("db"), database("keycloak-db")):
        assert demand_on(one.name) <= one.admissible(), (
            f"{one.name} admits {one.admissible()} and its clients want {demand_on(one.name)}"
        )


def test_every_database_keeps_a_connection_free_for_whoever_has_to_diagnose_it() -> None:
    """Headroom is the thing that was zero. A budget that balances exactly is a budget with no
    room for a backup, a migration, a second replica or a person, and the connection nobody
    opens until something is wrong is the one that must always be available.

    Delete this and a pool sized to exactly fill its server passes the test above and
    reproduces the incident.

    Positive as well as negative: the headroom is a real number and this prints it in the
    failure, so somebody adding a client can see what they have to spend."""
    for one in (database("db"), database("keycloak-db")):
        assert headroom_on(one.name) > 0, f"{one.name} has {headroom_on(one.name)} spare"


def test_a_client_that_declares_no_pool_maximum_cannot_be_constructed() -> None:
    """An unbounded client's steady state is its server's ceiling, whatever the load, because
    a `max_connections` figure is a refusal threshold and not a budget.

    Refused at construction rather than reported by the diagnostic, so the declaration cannot
    exist in a state the budget would have to describe.

    Delete this and `pool_max=0` reads as "no limit configured yet" and behaves as "all of
    them, for ever"."""
    with pytest.raises(ValueError, match="unbounded client runs at its server's ceiling"):
        Client(name="something", database="db", pool_max=0, why="because")


def test_a_client_whose_number_came_from_nowhere_cannot_be_constructed() -> None:
    """**The field four rows arrived with on 2026-09-09 and the reason it is required.** Each
    of those four numbers has a different source: one is read off a compose file, one off an
    engine in this repository, one off a decision in `docs/needs-rupash.md`, and one is a
    judgement about a driver nobody has installed. A reader cannot tell those apart from the
    figures, and a bound nobody can check is a bound nobody will argue with.

    Refused at construction rather than reported, matching the pool maximum above: the
    declaration cannot exist in a state the budget would have to describe.

    Delete this and `why=""` becomes the shape of every row added in a hurry, which is the
    same silence an undeclared client arrives through."""
    with pytest.raises(ValueError, match="provenance is nowhere"):
        Client(name="something", database="db", pool_max=5, why="   ")


def test_two_replicas_of_one_client_are_counted_twice() -> None:
    """The arithmetic everybody gets wrong the first time they scale something horizontally: a
    pool is per process, so two copies of a service hold two pools.

    Delete this and the budget is correct until the day somebody adds a replica, which is
    exactly the day it is needed."""
    one = Client(name="scaled", database="db", pool_max=10, replicas=3, why="a test")

    assert one.demand() == 30


def test_an_application_connecting_as_the_superuser_is_reported() -> None:
    """Postgres holds `superuser_reserved_connections` back so an administrator can always get
    in, and it reserves them *from ordinary roles*. An application connecting as the superuser
    draws on the reserve like everything else, which is why on 2026-09-07 there was no way to
    query the database that was refusing queries rather than merely a slow one.

    Reported rather than refused at construction, because it is true of Keycloak today and a
    constructor that refused it would make the real deployment undescribable.

    Delete this and the one remaining compromise in this budget stops being visible, and the
    next person reads the reserve as protection it does not provide."""
    found = connection_breaches()

    assert any("as its superuser" in one for one in found), found
    assert any("reserve nothing" in one for one in found), found


def test_the_only_breach_is_the_one_that_is_known_and_written_down() -> None:
    """The budget holds apart from a single recorded compromise, and this pins the set so a
    second one cannot arrive unnoticed.

    Asserted as an exact count rather than as "not empty", because a check that tolerates one
    finding tolerates two the day somebody adds one, and the whole value of this module is
    that the number is watched.

    Delete this and saturation can return while the superuser finding masks it."""
    found = connection_breaches()

    assert len(found) == 1, found


# --- the declarations agree with what is deployed -------------------------------------------


def test_the_keycloak_pool_and_its_server_agree_with_the_compose_file() -> None:
    """A budget that has drifted from the deployment is worse than none: it is a number
    somebody will believe. Both halves are read out of `docker-compose.keycloak.yml`.

    Delete this and the module can say fifteen while the compose says a hundred, and the test
    above passes on a fiction."""
    services = compose("docker-compose.keycloak.yml")["services"]

    declared = database("keycloak-db")
    assert int(setting(services["keycloak-db"]["command"], "max_connections")) == (
        declared.max_connections
    )
    assert setting(services["keycloak-db"]["command"], "work_mem") == (f"{declared.work_mem_mib}MB")
    assert setting(services["keycloak-db"]["command"], "shared_buffers") == (
        f"{declared.shared_buffers_mib}MB"
    )

    pool = services["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"]
    assert int(pool) == clients_of("keycloak-db")[0].pool_max


def test_the_pooler_size_agrees_with_the_compose_file() -> None:
    """The application's side of the same check. `DEFAULT_POOL_SIZE` is what actually bounds
    connections to the application's database, and it is the reason that database's declared
    ceiling is affordable.

    Delete this and the budget's most load-bearing figure is a number in a docstring."""
    services = compose("docker-compose.yml")["services"]

    declared = clients_of("db")[0]
    assert int(services["pgbouncer"]["environment"]["DEFAULT_POOL_SIZE"]) == declared.pool_max


def test_the_two_langfuse_pools_are_the_limit_their_own_connection_strings_carry() -> None:
    """**Both of the four numbers that a compose file can be asked about directly.** Prisma
    takes its pool maximum as `connection_limit` on the URL and nowhere else, so the budget's
    figure and the deployed figure are two copies of one number in two files, and the whole
    value of this module is that something compares them.

    Asserted per service rather than as a total, because two fives and a ten add up the same
    way and only one of those is the deployment.

    Delete this and the budget can say five while the URL says nothing at all, which is
    Prisma's default: a pool sized from the host's core count, on a database whose ceiling
    costs more memory than its container has."""
    services = compose("docker-compose.langfuse.yml")["services"]

    for name in ("langfuse-web", "langfuse-worker"):
        declared = client_named(name)
        assert declared is not None, f"{name} has no Client row"
        assert connection_limit_on(services[name]["environment"]["DATABASE_URL"]) == (
            declared.pool_max
        ), name


def test_the_two_worker_pools_are_the_bound_their_own_containers_declare() -> None:
    """The other two, and they are declared in an environment variable rather than on the URL
    because a worker's bound covers two pools rather than one: the checkpointer engine's and
    the queue driver's.

    `BRAIN_WORKER_POOL_MAX` is the container's copy and the `Client` row is the budget's, and
    `brain.ops.worker.pool_declaration_gaps` refuses a container where the two disagree. This
    is the same comparison made from the other end, so that a compose file edited without the
    budget fails here rather than only on a host with a queue driver installed.

    Delete this and the deployed bound drifts from the one every headroom figure in this
    module is computed from."""
    for file, service in (
        ("docker-compose.worker.yml", "brain-worker"),
        ("docker-compose.parse-worker.yml", "brain-parse-worker"),
    ):
        declared = client_named(service)
        assert declared is not None, f"{service} has no Client row"
        assert pool_max_declared_by(file, service) == declared.pool_max, service


def test_the_general_workers_bound_is_the_parse_workers_plus_what_its_engine_keeps() -> None:
    """**Where the fifteen comes from, asserted against the two things it is made of rather
    than against itself.** Ten is measured: `brain.session.make_worker_engine` keeps a pool of
    five plus five overflow for the checkpointer, which goes straight to the database because a
    saver prepares statements server-side. Five is the queue connection, and the parse worker
    is exactly that five and nothing else, because it configures no checkpointer at all.

    **Which half of this carries weight is worth being exact about.** The relation between the
    two rows is an identity while both are built from the same two constants, so it holds for
    every value they could take and it is not what makes the fifteen right. What makes it right
    is the line above it, which compares the ten against `brain/session.py` and would fail if
    that engine were resized; and the test above, which compares both rows against the numbers
    their containers actually carry, which is what stops the constants moving together
    unnoticed. What the relation itself pins is the shape: the difference between the two
    workers is exactly one checkpointer pool, so raising one row without the other fails here.

    Delete this and the ten stops being measured. `make_worker_engine` can be given a larger
    pool with nothing here noticing, and the budget goes on reporting spare connections that
    the worker is already holding."""
    engine = worker_engine_pool()
    general = client_named("brain-worker")
    parse = client_named("brain-parse-worker")

    assert general is not None and parse is not None
    assert engine["pool_size"] + engine["max_overflow"] == WORKER_CHECKPOINTER_CONNECTIONS
    assert general.pool_max == parse.pool_max + WORKER_CHECKPOINTER_CONNECTIONS
    # The parse worker's half is a queue connection and nothing else, which is only true while
    # that container configures no checkpointer. Asserted against its compose file, because the
    # day somebody gives it one is the day its five is an understatement.
    parse_environment = compose("docker-compose.parse-worker.yml")["services"][
        "brain-parse-worker"
    ]["environment"]
    assert "BRAIN_CHECKPOINTER_URL" not in parse_environment


def test_every_declared_database_has_a_client_and_every_client_a_database() -> None:
    """Both directions. A database nothing declares a client for is either dead or has an
    undeclared client, and an undeclared client is precisely what saturated Keycloak's.

    Delete this and a client can be added to a compose file and left out of the budget, which
    is the state this module was written to end."""
    for name in ("db", "keycloak-db"):
        assert clients_of(name), f"{name} has no declared client"

    from brain.ops.connections import CLIENTS

    for client in CLIENTS:
        assert database(client.database), client.name


# --- the ceiling that is affordable only because of the pooler ------------------------------


def test_the_application_ceiling_is_affordable_only_because_of_the_pooler() -> None:
    """**The relationship worth naming rather than fixing.** The application's database
    declares 100 connections at 16 MiB of `work_mem` inside a 2048 MiB container, so its
    declared ceiling costs 2112 MiB at worst and could not be honoured if anything reached it.

    Nothing does, because every client of it is bounded: PgBouncer at twenty and the four
    services that go round it at thirty between them. That makes the pooler load-bearing rather
    than an optimisation, and it makes each of those four bounds load-bearing in the same way.
    This is the test that says so, and its second line is where the four declarations of
    2026-09-09 are spent: it was 512 + 20 * 16 = 832 MiB against 2048 and it is now 1312, so
    the margin this database is safe by has fallen from 1216 MiB to 736.

    Reported by `ceiling_costs` and deliberately not by `connection_breaches`, because a check
    that is red the day it lands is a check somebody switches off.

    Delete this and removing the pooler looks like a simplification, and so does adding a fifth
    direct client with a pool chosen to be generous."""
    one = database("db")

    assert one.ceiling_cost_mib() > one.memory_mib
    assert demand_on("db") * one.work_mem_mib + one.shared_buffers_mib <= one.memory_mib

    reported = ceiling_costs()
    assert any("db" in line for line in reported), reported
    assert "load-bearing" in THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE


def test_keycloaks_ceiling_is_affordable_on_its_own() -> None:
    """The contrast, and the reason the two databases are configured differently. Keycloak's
    server can honour its own declared ceiling inside its container, so it needs no pooler and
    a bounded client is enough.

    Delete this and somebody raising `max_connections` there has nothing telling them the
    memory has to move with it."""
    one = database("keycloak-db")

    assert one.ceiling_cost_mib() <= one.memory_mib
    assert not any(one.name in line for line in ceiling_costs())


# --- the clients nobody declared ------------------------------------------------------------


def test_every_service_that_goes_round_the_pooler_is_declared_by_the_budget() -> None:
    """**The direction the outage came from, checked over the deployment rather than over the
    declaration.** `connection_breaches` asks whether a database's declared clients can
    outnumber its slots, and it cannot ask anything at all about a client nobody declared.
    Keycloak's was undeclared and unbounded, and that is the whole incident.

    Four services hold a connection string that reaches `db` with no pooler in the way, and
    until 2026-09-09 none of them had a `Client`. Every one bypasses PgBouncer for a good
    reason, which is what makes them the case that matters: the queue needs LISTEN and the
    checkpointer needs server-side prepared statements, so the services that most need
    budgeting are exactly the ones the pooler is not bounding.

    The answer is pinned as the exact set rather than as a count, in the shape
    `test_the_only_breach_is_the_one_that_is_known_and_written_down` uses, and the set is
    empty. That is the strongest form it can take: the next service pointed straight at one of
    these databases fails here rather than becoming a fifth finding in a list whose number
    nobody re-derives.

    Delete this and a service can be pointed straight at the application's database in a
    compose file and left out of the budget for ever, which is the state this module was
    written to end."""
    found = undeclared_clients(every_connection_string())

    assert found == (), found
    # Empty because they are declared, not because nothing reaches `db` directly. Both halves
    # are asserted, because a check that had stopped reading the compose files would produce
    # exactly the same empty tuple.
    assert {one.name for one in clients_of("db")} == {
        "pgbouncer",
        "brain-worker",
        "brain-parse-worker",
        "langfuse-web",
        "langfuse-worker",
    }
    direct = {
        service
        for service, urls in every_connection_string().items()
        if any(direct_database_in(url) for url in urls)
    }
    assert direct == {
        "brain-worker",
        "brain-parse-worker",
        "keycloak",
        "langfuse-web",
        "langfuse-worker",
    }, direct
    assert "PgBouncer" in A_DIRECT_CLIENT_IS_THE_ONE_THE_POOLER_DOES_NOT_BOUND


def test_a_service_that_goes_round_the_pooler_with_no_client_row_is_still_reported() -> None:
    """The positive case for a check whose real answer is now empty, and without it that check
    could `return ()` unconditionally with every other test here green.

    Asked with a service name no compose file uses, so it is testing the rule rather than the
    deployment: any service holding a direct connection string that `CLIENTS` does not name is
    a pool outside the budget, and the finding says what the budget's spare figure does not
    know about.

    Delete this and the empty set above stops being evidence of anything."""
    found = undeclared_clients({"a-new-service": ["postgresql+psycopg://brain:pw@db:5432/brain"]})

    assert len(found) == 1, found
    assert "'a-new-service'" in found[0] and "'db'" in found[0]
    assert f"{headroom_on('db')} spare" in found[0]


def test_a_caller_behind_the_pooler_is_not_counted_a_second_time() -> None:
    """The positive case, and it is load-bearing rather than symmetry. A check that reported
    every service holding any database URL would name the application itself, whose whole
    connection story is that it goes through PgBouncer, and a budget that refused the correct
    deployment is a budget somebody deletes.

    Both halves: a caller behind the pooler is not a direct client, and a client that *is*
    declared is not reported although it connects directly.

    Delete this and `direct_database_in` can start returning a database for every URL, which
    turns this check into noise on the day it would otherwise have said something.

    Asserted against `direct_database_in` on the application's own strings rather than against
    the findings, because the findings are empty now that the four direct clients are declared,
    and an absence from an empty tuple is evidence of nothing."""
    services = every_connection_string()

    assert "app" in services, sorted(services)
    assert not [url for url in services["app"] if direct_database_in(url)], (
        "the application reaches its database through PgBouncer"
    )
    assert any("pgbouncer" in url for url in services["app"]), (
        "an application holding no database URL at all would pass the line above"
    )

    # Keycloak is the half that says the skip is doing work rather than never being reached.
    # It holds `KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak`, so it is a direct
    # client of a database this budget declares, and it is absent from the findings only
    # because `CLIENTS` names it. Both facts are asserted, because the first spelling of this
    # asserted the second alone and passed while the skip was removed entirely.
    assert direct_database_in("jdbc:postgresql://keycloak-db:5432/keycloak") == "keycloak-db"
    assert any(one.name == "keycloak" for one in clients_of("keycloak-db"))
    assert undeclared_clients({"keycloak": services["keycloak"]}) == (), (
        "Keycloak is declared, and declared is the point"
    )
    assert undeclared_clients({"not-keycloak": services["keycloak"]}), (
        "the same strings under an undeclared name have to be reported, or the line above "
        "passes for a check that reads nothing"
    )

    assert direct_database_in("postgresql+psycopg://brain:pw@pgbouncer:5432/brain") is None
    assert direct_database_in("postgresql+psycopg://brain:pw@db:5432/brain") == "db"


def test_a_value_that_is_not_a_connection_string_is_not_a_client() -> None:
    """A compose environment block holds queue URLs, cache URLs, public addresses, secrets
    with substitution markers in them and plain words. Every one of them is handed to this
    check, so anything it cannot read has to come back as nothing rather than as a finding or
    an exception.

    `automation-db` is the sharp case and it is a real one: Activepieces keeps its own
    Postgres, on its own internal network, and this budget has never declared it. A hostname
    nobody declared is somebody else's server, and reporting it would be this module claiming
    a database it cannot see the settings of.

    Delete this and a Redis URL beside a Postgres one turns into an undeclared client, and
    the pinned set above starts failing for reasons that are not about connections."""
    assert direct_database_in("redis://langfuse-cache:6379/0") is None
    assert direct_database_in("automation-db") is None
    assert direct_database_in("") is None
    assert direct_database_in("http://[::1:80/") is None
    # As a URL rather than as a bare hostname, which is the assertion with teeth. A bare word
    # has no host for `urlsplit` to find and returns None down a different branch, so the
    # first spelling of this passed while a mutation admitting `automation-db` survived.
    assert direct_database_in("postgresql://activepieces:pw@automation-db:5432/activepieces") is (
        None
    )

    reported = {line.split("'")[1] for line in undeclared_clients(every_connection_string())}
    assert "activepieces" not in reported, "its store is not one of ours to budget"


def test_a_neighbours_database_is_declared_for_the_arithmetic_and_never_reported_as_ours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Database.ours` exists so the host's arithmetic can be honest about servers this system
    does not own, and no such row exists today, so the clause reading it is asserted against a
    declaration built here rather than against the live one. That is the same technique
    `test_wiring.py` uses for the trace-ledger membership and for the same reason: a branch
    that no real data reaches is a branch that has never been shown to work.

    The point of the clause is what it stops: reporting a neighbour's Postgres as an
    undeclared client of ours would ask somebody to add a `Client` row for a pool this system
    has no say over, and the first honest answer to that request is a number invented for
    somebody else's server.

    Delete this and `and one.ours` can be dropped as dead code, which it is until the day the
    first neighbour row is added, and on that day the check starts naming containers nobody
    here can size."""
    theirs = Database(
        name="someone-elses",
        max_connections=50,
        shared_buffers_mib=64,
        work_mem_mib=4,
        memory_mib=512,
        ours=False,
    )
    monkeypatch.setattr("brain.ops.connections.DATABASES", (database("db"), theirs))

    assert direct_database_in("postgresql://u:p@someone-elses:5432/x") is None
    assert direct_database_in("postgresql://u:p@db:5432/brain") == "db"
    assert undeclared_clients({"a-service": ["postgresql://u:p@someone-elses:5432/x"]}) == ()


def test_a_database_that_reserves_everything_cannot_be_constructed() -> None:
    """A reserve as large as the ceiling leaves nothing for the application, which is the same
    outage from the other end.

    Delete this and a typo in the reserve produces a database that refuses its own
    application and reports itself healthy."""
    with pytest.raises(ValueError, match="leaving nothing for the application"):
        Database(
            name="silly",
            max_connections=3,
            shared_buffers_mib=16,
            work_mem_mib=4,
            memory_mib=256,
            reserved=3,
        )


def test_the_reserve_is_the_servers_own_default_and_not_a_number_chosen_here() -> None:
    """The arithmetic has to match the server's or the budget describes a different machine.
    Three is `superuser_reserved_connections`, whose default has not changed in the lifetime
    of the setting.

    Delete this and the reserve drifts, and every headroom figure in this module is wrong by
    the difference."""
    assert POSTGRES_RESERVED_CONNECTIONS == 3
    assert database("keycloak-db").reserved == POSTGRES_RESERVED_CONNECTIONS
    assert database("keycloak-db").admissible() == 30 - POSTGRES_RESERVED_CONNECTIONS
