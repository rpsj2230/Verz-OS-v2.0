"""The deployment acceptance checks: registered, passing in a worker's own environment, and able to
fail.

The worker's environment here is the one `docker-compose.worker.yml` gives the general worker, read
from that file with its two substitutions filled in, so the checks are asked about the container
the product ships rather than about a dictionary written for the test. The layout and the scrub
need no database and run without one; the connection budget and the trace store run against
PostgreSQL at head. Each check is then broken the way it would break in practice and fails with
its own sentence, and a process that is not a worker is told so by the three that read one.

Task ids: M32.4.1.4, M32.7.3, M32.1.2.1, M32.1.2.2, M32.1.2.5, M32.2.2.4
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from structlog.testing import capture_logs

from brain.ops import acceptance_checks_deployment as deployment
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_deployment"

LEAVES = {
    "the_worker_serves_each_traffic_class_from_its_own_slots": ("M32.4.1.4",),
    "every_database_client_is_bounded_within_the_install_s_ceiling": ("M32.7.3",),
    "a_run_s_trace_is_stored_masked_and_read_only_after_its_row": (
        "M32.1.2.1",
        "M32.1.2.2",
        "M32.1.2.5",
    ),
    "the_scrub_meets_its_budget_on_this_install_s_processor": ("M32.2.2.4",),
}

#: The checks that read the worker they run in.
READ_THE_WORKER = (
    "the_worker_serves_each_traffic_class_from_its_own_slots",
    "every_database_client_is_bounded_within_the_install_s_ceiling",
    "the_scrub_meets_its_budget_on_this_install_s_processor",
)

LAYOUT = "the_worker_serves_each_traffic_class_from_its_own_slots"
SCRUB = "the_scrub_meets_its_budget_on_this_install_s_processor"

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

#: A password that is only ever a placeholder in a connection string the test never opens.
PLACEHOLDER = "not-a-password"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def worker_environment() -> dict[str, str]:
    """The general worker's environment as `docker-compose.worker.yml` declares it."""
    compose = yaml.safe_load((ROOT / "docker-compose.worker.yml").read_text(encoding="utf-8"))
    declared = compose["services"]["brain-worker"]["environment"]
    filled: dict[str, str] = {}
    for name, value in declared.items():
        text = str(value).replace("${POSTGRES_PASSWORD}", PLACEHOLDER)
        # `${NAME:-default}` is the compose default, which is what an unset variable becomes.
        filled[name] = re.sub(r"\$\{[A-Z_]+:-([^}]*)\}", r"\1", text)
    return filled


@pytest.fixture
def in_a_worker(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The worker's environment on this process, all but the application's own connection.

    `DATABASE_URL` is left as the test run has it, because it is also where the database tests'
    scratch server is found, and the worker's value names a pooler this machine does not have.
    """
    env = {name: value for name, value in worker_environment().items() if name != "DATABASE_URL"}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return env


@pytest.fixture
def not_in_a_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUEUE_URL", raising=False)


def ticking(milliseconds: float) -> Any:
    """A clock that moves `milliseconds` each time it is read, so a timing is the same on every
    machine: a scrub timed with it costs exactly that per sample, whatever the scrub did."""
    now = [0.0]

    def read() -> float:
        now[0] += milliseconds / 1000.0
        return now[0]

    return read


@pytest.fixture
def steady(monkeypatch: pytest.MonkeyPatch) -> None:
    """One millisecond a sample over sixteen kibibytes, well inside the budget on any machine."""
    monkeypatch.setattr(deployment, "SCRUB_CLOCK", ticking(1.0))


def without_a_database() -> Harness:
    # The layout and the scrub read nothing: each is handed a harness with no connection on purpose.
    return Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]


def ran(name: str) -> tuple[str, str]:
    """One check's outcome and reason with no database, as the run records them."""
    try:
        asyncio.run(mine()[name].run(without_a_database()))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


# ------------------------------------------------------------------------ without a server
def test_the_deployment_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names the leaves it proves, in order, and each is a leaf of the work breakdown.
    Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    assert list(mine()) == list(LEAVES)
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


@pytest.mark.usefixtures("not_in_a_worker")
@pytest.mark.parametrize("name", READ_THE_WORKER)
def test_a_process_that_is_not_a_worker_is_told_so_rather_than_judged(name: str) -> None:
    """`NOT_IN_A_WORKER`: a process holding no queue address records the three worker checks as
    not run, before it reads a table. Delete this and the application's own run of the suite could
    pass a layout nobody started, or fail over a pool it never declared."""
    assert ran(name) == (NOT_RUN, deployment.NOT_IN_A_WORKER)


@pytest.mark.usefixtures("in_a_worker", "steady")
@pytest.mark.parametrize("name", (LAYOUT, SCRUB))
def test_in_the_worker_s_own_environment_the_layout_and_the_scrub_pass(name: str) -> None:
    """The general worker as the product ships it: its start-up checks refuse nothing, it drains
    human_async, automation and system each at its declared concurrency within 384 MiB, and a scrub
    timed inside its budget passes. The clock is steady so the answer does not depend on how busy
    the machine running the suite is; the install's own processor is what the check times. Delete
    this and a check that cannot pass on the shipped container reaches the owner's server first."""
    assert ran(name) == (PASSED, "")


@pytest.mark.usefixtures("steady")
def test_the_scrub_s_figure_goes_to_the_log_with_nothing_from_the_environment(
    in_a_worker: dict[str, str],
) -> None:
    """`THE_SCRUB_IS_TIMED_WHERE_IT_WILL_RUN`: the rate is logged, because a result names no value,
    and the line carries the figure, the budget and the sample and nothing the environment holds.
    Delete this and the measurement could be taken and thrown away, or the log could start
    carrying the worker's connection strings."""
    with capture_logs() as logged:
        assert ran(SCRUB) == (PASSED, "")
    [line] = [one for one in logged if one["event"] == "acceptance.scrub_measured"]
    assert 0 < line["ms_per_kib"] <= line["budget_ms_per_kib"]
    assert line["chars"] >= deployment.SCRUB_SAMPLE_CHARS
    assert line["samples"] == deployment.SCRUB_SAMPLES
    said = json.dumps(line, default=str)
    assert PLACEHOLDER not in said and "postgresql" not in said


@pytest.mark.usefixtures("in_a_worker")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("pool", "the worker's own start-up checks would refuse the container the suite runs in"),
        ("guard", "a worker missing one traffic class's allocation would have started"),
        ("layout", "a traffic class runs at a concurrency its container did not declare"),
    ],
)
def test_the_layout_check_fails_where_the_worker_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each the way it happens: a container whose declared bound disagrees with the
    budget, a start-up check that refuses nothing, and a plan whose shards do not run at what the
    container declared. Each fails with its own sentence. Delete this and the check is satisfied
    by any worker that started, which is every worker that is running."""
    from brain.ops import worker
    from brain.ops.queue import Shard

    if broken == "pool":
        monkeypatch.setenv(worker.POOL_MAX_ENV, "14")
    elif broken == "guard":
        monkeypatch.setattr(worker, "preflight", lambda env: ())
    else:
        real = worker.plan_for

        def doubled(allocation: Any, **kwargs: Any) -> Any:
            plan = real(allocation, **kwargs)
            return worker.WorkerPlan(
                shards=tuple(
                    Shard(
                        queue=one.queue,
                        traffic_class=one.traffic_class,
                        concurrency=one.concurrency * 2,
                        slot_class=one.slot_class,
                    )
                    for one in plan.shards
                ),
                memory_mib=plan.memory_mib,
            )

        monkeypatch.setattr(worker, "plan_for", doubled)
    assert ran(LAYOUT) == (FAILED, reason)


@pytest.mark.usefixtures("in_a_worker")
def test_the_scrub_check_fails_when_the_scrub_is_slower_than_its_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scrub timed at fifty milliseconds over sixteen kibibytes is three per kibibyte against a
    budget of two, and the check fails with its sentence. Delete this and a check that passes for
    every timing would be read as a measurement."""
    monkeypatch.setattr(deployment, "SCRUB_CLOCK", ticking(50.0))
    assert ran(SCRUB) == (
        FAILED,
        "the scrub cost more per kibibyte on this install's processor than its budget allows",
    )


# --------------------------------------------------------------------------- with a server
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def trace_rows(url: str) -> tuple[int, int]:
    from tests.fixtures.scratch_postgres import sql

    steps = int(sql(url, "SELECT count(*) FROM obs.trace_step")[0][0])
    reads = int(sql(url, "SELECT count(*) FROM obs.trace_read")[0][0])
    return steps, reads


@pytest.mark.needs_db
@pytest.mark.usefixtures("in_a_worker", "steady")
def test_on_a_real_database_every_check_passes_and_leaves_nothing_behind() -> None:
    """**The four as the worker runs them, against PostgreSQL at head.** Each passes, and every
    table a check writes to, the trace step and the trace read among them, holds what it held
    before. Delete this and a check that cannot pass on the real schema, or one that commits a
    trace to a client's install, reaches the owner's server first."""
    with at_head("brain_acceptance_deployment") as url:
        before = (counts(url), trace_rows(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), trace_rows(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("in_a_worker")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        (
            "ceiling",
            "the install's database admits a different number of connections from the one its "
            "budget is computed against",
        ),
        ("full", "the declared clients of the install's database leave it no room"),
        (
            "crowded",
            "more connections are open on the install's database than its declared clients may "
            "hold",
        ),
        ("guard", "a worker declaring no connection bound would have started"),
        ("undeclared", "the worker running the suite does not declare its budgeted bound"),
    ],
)
def test_the_connection_check_fails_where_the_budget_does_not_hold(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks: a budget declaring a ceiling the database does not have, clients declared to
    fill it, clients declared to hold fewer connections than the check's own, a declaration check
    that refuses nothing, and a worker whose environment declares no bound. Each fails with its
    own sentence; the third also shows the count of open connections is read, since the check's
    own connection is one of them. Delete this and the check is satisfied by any database and any
    worker."""
    from dataclasses import replace

    from brain.ops import connections, worker

    if broken == "ceiling":
        wrong = replace(connections.database("db"), max_connections=97)
        monkeypatch.setattr(connections, "database", lambda name: wrong)
    elif broken == "full":
        monkeypatch.setattr(connections, "headroom_on", lambda name: 0)
    elif broken == "crowded":
        monkeypatch.setattr(connections, "demand_on", lambda name: 0)
    elif broken == "guard":
        monkeypatch.setattr(worker, "pool_declaration_gaps", lambda env, worker_component: ())
    else:
        monkeypatch.delenv(worker.POOL_MAX_ENV)
    check = mine()["every_database_client_is_bounded_within_the_install_s_ceiling"]
    with at_head("brain_acceptance_deployment") as url:
        assert run_checks(url, (check,)) == {check.name: (FAILED, reason)}


@pytest.mark.needs_db
def test_the_trace_check_fails_when_a_trace_is_stored_unmasked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorder's mask switched off: the step's payload is the record's text, which the
    table's own check refuses, so nothing is stored and the check says the graph is missing.
    Delete this and a check that passes whatever the recorder did would be read as proof that
    traces are masked."""
    from brain.ops import trace_store
    from brain.ops.tracing import Span

    def unmasked(span: Span) -> Span:
        return span

    monkeypatch.setattr(trace_store, "mask", unmasked)
    check = mine()["a_run_s_trace_is_stored_masked_and_read_only_after_its_row"]
    with at_head("brain_acceptance_deployment") as url:
        assert run_checks(url, (check,)) == {
            check.name: (FAILED, "a run's trace graph was not stored under its trace")
        }
