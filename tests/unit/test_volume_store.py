"""Each person's recent questions against their own week, counted from the request ledger.

`brain.ops.limits.assess_volume` is tested in `test_limits.py`. What is here is the input it had
never had: the statement over `obs.request_telemetry` (compiled, and run for real where CI has
a server) and the assessment each person's two counts produce.

The database half skips without `DATABASE_URL`, and CI always sets it.

Task ids: M23.2.1, M23.2.3
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.gate.context import TrafficClass
from brain.ops.limits import (
    HUMAN_TRAFFIC,
    VOLUME_BASELINE_PERIODS,
    VOLUME_OBSERVED_PERIOD,
    VolumeBand,
)
from brain.ops.telemetry import RequestTelemetry
from brain.ops.volume_store import PrincipalVolume, principal_volumes, volumes_at
from tests.fixtures.scratch_postgres import engine, run
from tests.unit.test_telemetry_store import a_row, built, write_as_app

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far from any wall clock, for `CLAUDE.md`'s reason about fixtures that are clocks.
NOW = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)


def test_the_statement_counts_both_periods_in_one_pass_over_peoples_traffic() -> None:
    """One grouped statement with a filter on each count, over the classes
    `limits.HUMAN_TRAFFIC` names, bounded by the week before the split and the split itself.

    Delete this and the two figures can come from two reads, or machine traffic can be counted
    as a person's."""
    compiled = volumes_at(NOW).compile(dialect=DIALECT)
    sql = str(compiled)

    assert sql.count("FILTER (WHERE") == 2
    assert "GROUP BY obs.request_telemetry.principal" in sql
    assert "obs.request_telemetry.traffic_class IN" in sql
    classes = [value for value in compiled.params.values() if isinstance(value, list)]
    assert classes == [sorted(str(one) for one in HUMAN_TRAFFIC)]
    split = NOW - VOLUME_OBSERVED_PERIOD
    start = split - VOLUME_OBSERVED_PERIOD * VOLUME_BASELINE_PERIODS
    dates = sorted(value for value in compiled.params.values() if isinstance(value, datetime))
    assert dates == [start, split, split, NOW]


def test_a_person_is_judged_against_their_own_week_and_not_the_companys() -> None:
    """Sixty questions today against four a day is extreme; sixty against sixty is not. The
    baseline is the week divided by its periods, so the finance director who always asks sixty
    is never listed.

    Delete this and the baseline can become the whole week's total, which makes everybody
    ordinary."""
    spike = PrincipalVolume("p_sales", observed=60, prior=4 * VOLUME_BASELINE_PERIODS)
    steady = PrincipalVolume("p_finance", observed=60, prior=60 * VOLUME_BASELINE_PERIODS)

    assert spike.assessed().band is VolumeBand.EXTREME
    assert steady.assessed().band is VolumeBand.ORDINARY


# ------------------------------------------------------------------ against the table
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with built("brain_test_m2321_volume") as url:
        yield url


def at(when: datetime, principal: str, traffic: TrafficClass, trace: str) -> RequestTelemetry:
    row = a_row(trace, at=when)
    return replace(row, principal=principal, ingress=replace(row.ingress, traffic_class=traffic))


def test_the_ledger_is_counted_per_person_and_a_schedule_is_nobody(database: str) -> None:
    """Run for real: two of one person's questions today and seven over the week before, one
    of another's, and a scheduled request under the first person's name that counts for
    nobody.

    Delete this and the statement's filters are asserted only as text."""
    today = NOW - timedelta(hours=1)
    last_week = NOW - timedelta(days=3)
    rows = [
        at(today, "u_one", TrafficClass.HUMAN_INTERACTIVE, "t1"),
        at(today, "u_one", TrafficClass.HUMAN_ASYNC, "t2"),
        *(at(last_week, "u_one", TrafficClass.HUMAN_INTERACTIVE, f"w{n}") for n in range(7)),
        at(today, "u_two", TrafficClass.HUMAN_INTERACTIVE, "t3"),
        at(today, "u_one", TrafficClass.AUTOMATION, "t4"),
        at(NOW - timedelta(days=30), "u_one", TrafficClass.HUMAN_INTERACTIVE, "old"),
    ]
    write_as_app(database, *rows)

    async def go() -> tuple[PrincipalVolume, ...]:
        bound = engine(database)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET ROLE brain_app"))
                return await principal_volumes(session, now=NOW)
        finally:
            await bound.dispose()

    found = {one.principal: one for one in run(go)}

    assert found["u_one"] == PrincipalVolume("u_one", observed=2, prior=7)
    assert found["u_two"] == PrincipalVolume("u_two", observed=1, prior=0)
