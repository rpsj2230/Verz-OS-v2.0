"""The workers' session-mode pooler, held to the budget rows it enforces (M0.3.5).

Every refusal below is built from the real compose files with exactly one thing changed, so a
test that passes is a statement about the deployment and not about a fixture somebody wrote to
agree with the check.

Task ids: M0.3.5
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.requirements import files_for
from brain.ops.connections import client_named
from brain.ops.queue import POOLER_HOSTNAMES
from brain.ops.session_pool import (
    A_SESSION_POOL_SMALLER_THAN_ITS_CLIENTS_IS_A_LISTEN_THAT_WAITS,
    A_WORKER_ROUTED_ROUND_THE_SESSION_POOLER_IS_OUTSIDE_ITS_CEILING,
    MAX_QUERY_WAIT_SECONDS,
    SESSION_POOL_CLIENTS,
    SESSION_POOLER,
    SESSION_POOLER_FILE,
    declared_demand,
    session_pool_gaps,
)
from brain.ops.wiring import component

REPO = Path(__file__).resolve().parents[2]
WORKER = "docker-compose.worker.yml"
PARSE_WORKER = "docker-compose.parse-worker.yml"


def profile(name: str) -> dict[str, Any]:
    """The compose files a profile composes, parsed, as fresh copies a test may edit."""
    return {
        one: yaml.safe_load((REPO / one).read_text(encoding="utf-8")) for one in files_for(name)
    }


def pooler_environment(files: dict[str, Any]) -> dict[str, Any]:
    environment: dict[str, Any] = files[SESSION_POOLER_FILE]["services"][SESSION_POOLER][
        "environment"
    ]
    return environment


# ======================================================================= the real files
@pytest.mark.parametrize("name", ["standard", "full"])
def test_every_profile_that_runs_the_workers_runs_the_session_pooler_as_the_budget_says(
    name: str,
) -> None:
    """The positive case, over the files each profile actually composes. Delete this and every
    refusal below can pass against a check that refuses everything, including the deployment."""
    files = profile(name)

    assert SESSION_POOLER in files[SESSION_POOLER_FILE]["services"]
    assert session_pool_gaps(files) == ()


def test_a_profile_with_no_worker_needs_no_session_pooler() -> None:
    """`lite` runs no worker, so there is nothing for the pooler to serve and no finding to make.
    Delete this and the check can start demanding a pooler on the profile production runs."""
    files = profile("lite")

    assert not any(SESSION_POOLER in (doc.get("services") or {}) for doc in files.values())
    assert session_pool_gaps(files) == ()


def test_the_ceiling_is_what_the_two_workers_containers_declare_and_not_a_copy_of_itself() -> None:
    """The figure is asserted against something outside `brain.ops.session_pool`: the
    `BRAIN_WORKER_POOL_MAX` each worker container is actually given, and the pooler's own
    compose entry. Delete this and the ceiling and the rows can move together to any value, with
    the check comparing a sum against the same sum."""
    files = profile("standard")
    given = sum(
        int(files[name]["services"][service]["environment"]["BRAIN_WORKER_POOL_MAX"])
        for name, service in ((WORKER, "brain-worker"), (PARSE_WORKER, "brain-parse-worker"))
    )
    environment = pooler_environment(files)

    assert declared_demand() == given == 20
    assert int(environment["MAX_DB_CONNECTIONS"]) == given
    assert int(environment["DEFAULT_POOL_SIZE"]) == given
    assert int(environment["MAX_CLIENT_CONN"]) > given
    assert environment["POOL_MODE"] == "session"
    assert {one for one in SESSION_POOL_CLIENTS if client_named(one) is None} == set()


def test_the_pooler_is_budgeted_at_the_memory_its_container_is_given() -> None:
    """Two copies of 64 MiB, one in the wiring and one in the compose file. Delete this and the
    container can be raised without the host requirement moving."""
    body = profile("standard")[SESSION_POOLER_FILE]["services"][SESSION_POOLER]

    assert body["deploy"]["resources"]["limits"]["memory"] == (
        f"{component(SESSION_POOLER).memory_mib}M"
    )


def test_the_session_pooler_is_never_one_the_transaction_rule_refuses() -> None:
    """`POOLER_HOSTNAMES` refuses a queue URL by host. Delete this and the session pooler's name
    can be added to that set, after which every worker refuses to start on a correct URL."""
    assert SESSION_POOLER not in POOLER_HOSTNAMES


# ========================================================================= the refusals
def test_a_session_pooler_in_transaction_mode_is_refused() -> None:
    """The failure with no error anywhere: a LISTEN behind transaction pooling stops being
    notified and the queue reads as empty. Delete this and one word in the compose file undoes
    the whole reason the service exists."""
    files = profile("standard")
    pooler_environment(files)["POOL_MODE"] = "transaction"

    assert any("POOL_MODE=transaction" in one for one in session_pool_gaps(files))


@pytest.mark.parametrize("ceiling", ["19", "21"])
def test_a_ceiling_that_is_not_the_workers_declared_demand_is_refused(ceiling: str) -> None:
    """Both directions. Below the rows, a worker waits for a backend another is holding; above
    them, the database's budget counts less than the pooler admits. Delete this and either can
    ship."""
    files = profile("standard")
    pooler_environment(files)["MAX_DB_CONNECTIONS"] = ceiling

    found = session_pool_gaps(files)
    assert any(f"admits {ceiling} server connections" in one for one in found), found


def test_a_pooler_with_no_ceiling_is_refused() -> None:
    """Without `MAX_DB_CONNECTIONS` the pooler counts nothing, and a session pooler that counts
    nothing is a hop with no purpose. Delete this and the one setting it exists for can go."""
    files = profile("standard")
    del pooler_environment(files)["MAX_DB_CONNECTIONS"]

    assert any("sets no MAX_DB_CONNECTIONS" in one for one in session_pool_gaps(files))


def test_a_pool_smaller_than_the_declared_demand_is_refused() -> None:
    """The silent wait. Delete this and the pool can be halved with the ceiling left alone."""
    files = profile("standard")
    pooler_environment(files)["DEFAULT_POOL_SIZE"] = "10"

    found = session_pool_gaps(files)
    assert any(
        "keeps a pool of 10" in one
        and A_SESSION_POOL_SMALLER_THAN_ITS_CLIENTS_IS_A_LISTEN_THAT_WAITS in one
        for one in found
    ), found


def test_a_client_limit_below_the_pool_is_refused() -> None:
    """With every worker connected, the healthcheck is the next client, and a limit at or below
    the pool marks a working pooler unhealthy. Delete this and that ships as a restart loop."""
    files = profile("standard")
    pooler_environment(files)["MAX_CLIENT_CONN"] = "19"

    assert any("accepts 19 clients" in one for one in session_pool_gaps(files))


@pytest.mark.parametrize("wait", [None, "0", str(MAX_QUERY_WAIT_SECONDS + 1)])
def test_a_client_beyond_the_ceiling_must_fail_within_the_bound(wait: str | None) -> None:
    """A worker past its budget should fail where somebody reads it. Delete this and PgBouncer's
    default of two minutes returns, which from outside looks like an idle queue."""
    files = profile("standard")
    environment = pooler_environment(files)
    if wait is None:
        del environment["QUERY_WAIT_TIMEOUT"]
    else:
        environment["QUERY_WAIT_TIMEOUT"] = wait

    assert any("QUERY_WAIT_TIMEOUT" in one for one in session_pool_gaps(files))


def test_a_worker_sent_straight_to_the_database_is_refused() -> None:
    """It works, and that is why it is checked: it is outside the ceiling. Delete this and the
    old direct URL can come back in one edit with nothing else noticing."""
    files = profile("standard")
    environment = files[PARSE_WORKER]["services"]["brain-parse-worker"]["environment"]
    environment["QUEUE_URL"] = "postgresql+psycopg://brain:pw@db:5432/brain"

    found = session_pool_gaps(files)
    assert any(
        "'brain-parse-worker' sends QUEUE_URL to 'db'" in one
        and A_WORKER_ROUTED_ROUND_THE_SESSION_POOLER_IS_OUTSIDE_ITS_CEILING in one
        for one in found
    ), found


def test_a_checkpointer_sent_through_the_transaction_pooler_is_refused() -> None:
    """The prepared-statement half of the rule, on the other setting. Delete this and only the
    queue URL is ever checked."""
    files = profile("standard")
    environment = files[WORKER]["services"]["brain-worker"]["environment"]
    environment["BRAIN_CHECKPOINTER_URL"] = "postgresql+psycopg://brain:pw@pgbouncer:5432/brain"

    found = session_pool_gaps(files)
    assert any("BRAIN_CHECKPOINTER_URL through the transaction pooler" in one for one in found)


def test_workers_with_no_session_pooler_in_the_set_are_refused() -> None:
    """Composing a worker file without the file that declares the pooler. Delete this and the
    check reports nothing about the case where there is nothing to check."""
    files = profile("standard")
    del files[SESSION_POOLER_FILE]["services"][SESSION_POOLER]

    found = session_pool_gaps(files)
    assert len(found) == 1 and f"no {SESSION_POOLER!r} service" in found[0], found


def test_a_pooler_on_profiles_the_budget_does_not_give_it_is_refused() -> None:
    """Held to the wiring, so the host requirement and the deployment describe one set. Delete
    this and the pooler can start on a profile nothing costs it on."""
    files = profile("standard")
    files[SESSION_POOLER_FILE]["services"][SESSION_POOLER]["profiles"] = ["full"]

    assert any("runs on profiles ['full']" in one for one in session_pool_gaps(files))


def test_a_pooler_pointed_at_a_database_the_budget_does_not_declare_is_refused() -> None:
    """The workers' rows count against `db`. Delete this and the pooler can be pointed somewhere
    else while the budget goes on counting connections that no longer land there."""
    files = profile("standard")
    pooler_environment(files)["DB_HOST"] = "elsewhere"

    assert any("reaches 'elsewhere'" in one for one in session_pool_gaps(files))


def test_the_files_are_not_edited_by_the_check() -> None:
    """The check takes documents a caller parsed, and a caller reuses them. Delete this and a
    merge that wrote into the caller's copy would pass every other test here."""
    files = profile("full")
    before = copy.deepcopy(files)

    session_pool_gaps(files)

    assert files == before
