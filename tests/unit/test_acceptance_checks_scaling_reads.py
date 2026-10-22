"""The install checks for the ledger's partitions, the console read replica's routing and the spend
report's refresh, each passing on PostgreSQL at head and each failing with the product broken.

The database half runs the module as the worker would, against a database at head: the partition
check says it did not run until the worker's maintenance has made the months (it is run here as the
worker runs it), then all three pass and leave nothing. Then each is shown failing: a ledger missing
a month, a decision read from the replica, a replica read carrying no banner, and a stale report
that says it is live.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M36.1.1.1, M36.1.2.2, M36.1.3.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_scaling_reads import CHECK_ORDER, THE_MONTHS_ARE_NOT_MADE_YET
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_scaling_reads"
PARTITIONS = "the_ledger_has_a_partition_for_this_month_and_each_one_ahead"
REPLICA = "a_console_read_goes_to_the_replica_and_a_decision_never_does"
AGE = "the_spend_report_is_rebuilt_daily_and_says_how_old_it_is"


def test_the_module_names_each_leaf_in_one_check() -> None:
    """Three checks, each closing its own leaf. Delete this and a leaf can move to a check that
    never looked at it, with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (PARTITIONS, ("M36.1.1.1",)),
        (REPLICA, ("M36.1.2.2", "M36.1.2.3")),
        (AGE, ("M36.1.3.2",)),
    ]
    assert checks_in(MODULE) == [PARTITIONS, REPLICA, AGE]
    assert 2100 <= CHECK_ORDER <= 2199
    assert len(THE_MONTHS_ARE_NOT_MADE_YET) <= REASON_CHARS


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_scaling_reads") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


def _the_worker_makes_the_months(url: str) -> None:
    """The retention run's own maintenance, as the worker runs it, committed on the scratch
    database."""
    import psycopg

    from brain.db import libpq_conninfo
    from brain.ops.ledger_partitions import maintain

    with psycopg.connect(libpq_conninfo(url), prepare_threshold=None) as conn:
        maintain(conn, now=datetime.now(UTC), report_only=False)


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Before the worker has made the months the partition
    check says in words that it did not run, and after it all three pass and nothing is left.
    Delete this and a check that can never pass on a real schema, or one that fails an install
    that has not had its first daily run, reaches the owner's server."""
    first = run_module(install)
    assert first[PARTITIONS][0] in (NOT_RUN, PASSED)
    _the_worker_makes_the_months(install)
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_ledger_missing_a_month_fails_the_partition_check(install: str) -> None:
    """The next month's partition detached. Delete this and M36.1.1.1 closes on a ledger that has
    nowhere to put next month's rows but its default."""
    from brain.ops.ledger_partitions import Month
    from tests.fixtures.scratch_postgres import sql

    _the_worker_makes_the_months(install)
    ahead_name = Month.of(datetime.now(UTC)).following().name
    sql(install, "ALTER TABLE obs.request_telemetry DETACH PARTITION obs." + ahead_name)
    try:
        assert "partition" in _failed(install, PARTITIONS)
    finally:
        sql(install, "DROP TABLE IF EXISTS obs." + ahead_name)
        _the_worker_makes_the_months(install)


@pytest.mark.needs_db
def test_a_server_that_reports_itself_a_replica_fails_the_replica_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real lag measurement made to say the install's own server replays another's log. Delete
    this and M36.1.2.3 closes on a measurement nothing here ever asked the real server for."""
    from datetime import timedelta

    from brain.console.read_replica import LagReading
    from brain.ops import replica_store

    async def replica(_session: Any) -> LagReading:
        return LagReading(in_recovery=True, replay_age=timedelta(seconds=3), caught_up=False)

    monkeypatch.setattr(replica_store, "measure_lag", replica)
    assert "reported a replica" in _failed(install, REPLICA)


@pytest.mark.needs_db
def test_a_decision_read_from_the_replica_or_a_banner_left_off_fails_the_replica_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routing sending every read to the replica, then dropping the banner. Delete this and
    M36.1.2.2 closes on a router that lets a decision read a copy or hides how old the copy is."""
    from brain.console import read_replica
    from brain.ops import replica_store

    real = read_replica.route_read

    def always_replica(purpose: Any, measurement: Any, *, now: Any) -> Any:
        return read_replica.ConsoleRoute(
            target=read_replica.Target.REPLICA, why=read_replica.Why.CURRENT
        )

    with monkeypatch.context() as patched:
        patched.setattr(replica_store, "route_read", always_replica)
        assert "decides" in _failed(install, REPLICA)

    def unbannered(purpose: Any, measurement: Any, *, now: Any) -> Any:
        routed = real(purpose, measurement, now=now)
        return read_replica.ConsoleRoute(target=routed.target, why=read_replica.Why.CURRENT)

    monkeypatch.setattr(replica_store, "route_read", unbannered)
    assert "how far" in _failed(install, REPLICA)


@pytest.mark.needs_db
def test_a_report_that_always_says_live_fails_the_age_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report grading every age as live. Delete this and M36.1.3.2 closes on a report that
    cannot say it has gone stale."""
    from brain.console import spend_report_view
    from brain.gate.provenance import Freshness, StatedFreshness

    def live(*args: Any, **kwargs: Any) -> Any:
        return StatedFreshness(state=Freshness.LIVE)

    monkeypatch.setattr(spend_report_view, "freshness_of", live)
    assert "stale" in _failed(install, AGE)
