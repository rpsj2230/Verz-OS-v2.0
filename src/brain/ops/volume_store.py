"""How much each person asked lately against their own week, counted from the request ledger.

`brain.ops.limits.assess_volume` scores one principal's volume against their own baseline and
decides nothing, and until 2026-09-28 nothing handed it a volume: no statement anywhere counted
anybody's questions per person, so M23.2.1's detector was a function with no input. This is
the input, one statement over `obs.request_telemetry`, and the Limits screen is where its
answer is read (`brain.console.installation.unusual_now`).

**People's traffic only.** The statement counts the classes `brain.ops.limits.HUMAN_TRAFFIC`
names, which is `counts_towards_metrics` over every class, because a nightly report running
under somebody's name is not that person asking and would make them the most unusual person in
the company every night. That is M23.2.3's exclusion, applied where the count is taken rather
than after it, so no count that includes a machine exists to be shown by mistake.

**One statement, grouped by the database, and two figures per person.** The recent period and
the week before it are counted in the same pass with a filter on each aggregate, so the two
figures cannot come from two different reads that a request landing between them made
disagree. `limits.VOLUME_OBSERVED_PERIOD` and `limits.VOLUME_BASELINE_PERIODS` are the policy;
this module owns no number.

**The counts are inputs and never output.** `PrincipalVolume` goes to `assess_volume` and what
leaves for a screen is the band. A person's question count beside their name is a report about
their day, which `brain.ops.lane_share.THIS_MODULE_HAS_NOWHERE_TO_PUT_A_PERSON` refuses for a
reason that applies here with more force, since this one is per person by construction.

Rejected: counting in Valkey beside the windows. The windows hold a minute and a day at most,
and a baseline is a week; keeping a week of hits per person in the store the entitlement cache
answers from would be the largest thing in it, to duplicate a ledger that already exists.

Task ids: M23.2.1, M23.2.3
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.limits import (
    HUMAN_TRAFFIC,
    VOLUME_BASELINE_PERIODS,
    VOLUME_OBSERVED_PERIOD,
    VolumeAssessment,
    assess_volume,
    baseline_from,
)
from brain.tables.telemetry import RequestTelemetryRow


@dataclass(frozen=True)
class PrincipalVolume:
    """What one person asked in the recent period and in the week before it."""

    principal: str
    observed: int
    prior: int

    def assessed(self) -> VolumeAssessment:
        """`limits.assess_volume` against this person's own week. Decides nothing."""
        return assess_volume(observed=self.observed, baseline=baseline_from(self.prior))


def volumes_at(now: datetime) -> Select[tuple[str, int, int]]:
    """Each person's recent count and the count of the week before, in one grouped pass.

    The recent period is `[now - period, now)` and the baseline the `VOLUME_BASELINE_PERIODS`
    periods before it, half-open like every window in this repository, so a request exactly on
    the split is counted once and in the recent period.
    """
    split = now - VOLUME_OBSERVED_PERIOD
    start = split - VOLUME_OBSERVED_PERIOD * VOLUME_BASELINE_PERIODS
    received = RequestTelemetryRow.received_at
    return (
        select(
            RequestTelemetryRow.principal,
            func.count().filter(received >= split).label("observed"),
            func.count().filter(received < split).label("prior"),
        )
        .where(
            received >= start,
            received < now,
            RequestTelemetryRow.traffic_class.in_(sorted(str(one) for one in HUMAN_TRAFFIC)),
        )
        .group_by(RequestTelemetryRow.principal)
    )


async def principal_volumes(session: AsyncSession, *, now: datetime) -> tuple[PrincipalVolume, ...]:
    """Every person who asked anything in the last eight periods, with both counts."""
    found = await session.execute(volumes_at(now))
    return tuple(
        PrincipalVolume(principal=str(principal), observed=int(observed), prior=int(prior))
        for principal, observed, prior in found.all()
    )


@dataclass(frozen=True)
class StoredVolumes:
    """`principal_volumes` on a session of its own, in the shape the Limits route reads."""

    sessions: async_sessionmaker[AsyncSession]

    async def __call__(self, now: datetime) -> Sequence[PrincipalVolume]:
        async with self.sessions() as session:
            return await principal_volumes(session, now=now)
