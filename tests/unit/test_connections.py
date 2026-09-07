"""The connection budget, held to the outage that produced it.

On 2026-09-07 Keycloak opened every connection its database would give it and held all thirty
idle. The next connection was refused and the next connection was an administrator trying to
diagnose it. Every test here is about one of the three ways that happens: a client with no
bound, a server whose clients can outnumber its slots, and an application connecting as the
superuser so the administrator's reserve reserves nothing.

The declarations are checked against the compose files they describe rather than trusted,
because a budget that has drifted from what is deployed is worse than none: it is a number
somebody will believe.

Task ids: none
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.connections import (
    POSTGRES_RESERVED_CONNECTIONS,
    THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE,
    Client,
    Database,
    ceiling_costs,
    clients_of,
    connection_breaches,
    database,
    demand_on,
    headroom_on,
)

REPO = Path(__file__).resolve().parents[2]


def compose(name: str) -> dict[str, Any]:
    return yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}


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
        Client(name="something", database="db", pool_max=0)


def test_two_replicas_of_one_client_are_counted_twice() -> None:
    """The arithmetic everybody gets wrong the first time they scale something horizontally: a
    pool is per process, so two copies of a service hold two pools.

    Delete this and the budget is correct until the day somebody adds a replica, which is
    exactly the day it is needed."""
    one = Client(name="scaled", database="db", pool_max=10, replicas=3)

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

    Nothing does, because PgBouncer bounds real server connections to twenty. That makes the
    pooler load-bearing rather than an optimisation, and this is the test that says so: point
    a second client straight at that database and the ceiling stops being theoretical.

    Reported by `ceiling_costs` and deliberately not by `connection_breaches`, because a check
    that is red the day it lands is a check somebody switches off.

    Delete this and removing the pooler looks like a simplification."""
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
