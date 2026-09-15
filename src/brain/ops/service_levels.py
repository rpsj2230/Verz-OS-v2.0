"""Each lane's measured attainment against its objective, over a window, as a read model.

`brain.ops.reliability` declares what each lane promises (`LANE_OBJECTIVES`) and compares one
observation against one promise (`attainment`). Until the metadata ledger had a table and a
duration, nothing could supply the observation, so every latency objective was reported unmet
for want of a measurement. This module folds the ledger's rows into one reading per lane and
hands each to that comparison. It adds no second comparison and no second percentile.

**One reading per declared lane, always, including a lane with no traffic.** A lane nothing was
asked through in the window is present with no figures and a shortfall saying so, rather than
absent. An absent row reads as a lane nobody promised anything about, and a figure of 100% over
no requests is what a stopped ingest looks like. See
`A_LANE_WITH_NO_REQUESTS_IN_THE_WINDOW_IS_UNMEASURED_RATHER_THAN_MET`.

**A percentile is withheld below the sample it needs to be a rank.** Nearest rank at 0.95 over
nineteen requests is the slowest request with a percentile's name on it.
`brain.console.spend_view.minimum_rows` derives the floor and `brain.connectors.throttle.
percentile_ms` takes the rank, both imported, so there is one rule about how many observations
a quantile needs and one about how it is taken. Below the floor the latency objective is
reported unmeasured, through `attainment`, which already says so for a missing observation.

**A withheld request and an absent one are one observation.** `Observation` holds a lane, a
status, a duration and an instant, and the status is the ledger's coarse one, so the two cannot
be separated here by anything a reader could be shown: both are `NOTHING_RETURNED`, and both are
in `SUCCESS_STATUSES` for the reason `reliability` gives. There is no count of any status in a
reading, only the number of requests and the success rate, and neither is a count of anything
hidden. See `A_WITHHELD_REQUEST_AND_AN_ABSENT_ONE_ARE_ONE_OBSERVATION`.

**What is not built, and why M30.5.3 is not claimed.** The leaf is a dashboard. There is no
screen for it in `brain.console.screens`, so no capability decides who may read a reading and
nothing renders one. A reading carries no principal, no department and no trace, so what it
discloses is how the install is performing, which is less than any row it was built from; but
who may be shown that is a screen's decision, and writing a capability here for a screen that
does not exist would be a permission waiting for a caller. See
`A_READING_WITH_NO_SCREEN_HAS_NO_READER_DECISION`.

Scope: pure. `brain.ops.telemetry_store.service_levels_between` is the store query feeding it.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.connectors.throttle import percentile_ms
from brain.console.spend_view import minimum_rows
from brain.core.lane import Lane
from brain.ops.reliability import (
    LANE_OBJECTIVES,
    LaneObjective,
    ReliabilityError,
    attainment,
    success_rate,
)
from brain.ops.telemetry import RequestStatus

# ----------------------------------------------------------------- written-down reasons
#: Why an empty lane is a row with a shortfall rather than a missing row or a green one.
A_LANE_WITH_NO_REQUESTS_IN_THE_WINDOW_IS_UNMEASURED_RATHER_THAN_MET: Final = (
    "A lane with no traffic has no success rate and no percentile. Rendering it green reports "
    "the absence of a measurement as compliance, and leaving it out makes it indistinguishable "
    "from a lane nothing promised anything about. So it is present, with no figures, and says "
    "it was not measured."
)

#: Why the read model cannot separate a refusal from an absence.
A_WITHHELD_REQUEST_AND_AN_ABSENT_ONE_ARE_ONE_OBSERVATION: Final = (
    "An observation carries the ledger's status, and the ledger records a withheld record and "
    "an absent one as NOTHING_RETURNED because the lane's status is decided without reading "
    "why it abstained. Both count as the system having done its job. A reading holds the "
    "number of requests and the share that succeeded and no count of any one status, so there "
    "is no figure on it from which the number of refusals could be read or subtracted."
)

#: Why the read model has no reader check of its own.
A_READING_WITH_NO_SCREEN_HAS_NO_READER_DECISION: Final = (
    "Who may see how the install is performing is decided per screen, by the capability the "
    "screen registry declares for it. No screen shows service levels yet, so there is no "
    "capability to check, and inventing one here would be a grant nobody can be given through "
    "the console and a rule the screen, when it is written, would have to agree with."
)

#: The percentile every lane objective is stated at.
P95: Final = 0.95


class ServiceLevelError(ReliabilityError):
    """Raised when a reading is asked for over no window or against objectives that overlap."""


@dataclass(frozen=True)
class Observation:
    """One finished request as a service level reading needs it, and nothing more."""

    lane: Lane
    status: RequestStatus
    duration_ms: float
    received_at: datetime


@dataclass(frozen=True)
class LaneReading:
    """One lane's measured figures over a window, beside the objective they are measured against.

    `p95_ms` is None when the lane promises no percentile, when there were no requests, or when
    there were too few for a rank. `success_rate` is None only when there were no requests.
    `shortfalls` is every way the lane misses its objective, one sentence each, and is empty
    exactly when it meets it.
    """

    objective: LaneObjective
    requests: int
    p95_ms: float | None
    success_rate: float | None
    shortfalls: tuple[str, ...]

    @property
    def met(self) -> bool:
        return not self.shortfalls


@dataclass(frozen=True)
class ServiceLevels:
    """Every declared lane's reading over `[start, end)`, in the objectives' declared order."""

    start: datetime
    end: datetime
    lanes: tuple[LaneReading, ...]


def _window(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        msg = (
            "a service level window with no timezone cannot be compared with the ledger's instants"
        )
        raise ServiceLevelError(msg)
    if end <= start:
        msg = f"a service level window from {start} to {end} holds no time at all"
        raise ServiceLevelError(msg)


def _declared(objectives: Sequence[LaneObjective] | None) -> tuple[LaneObjective, ...]:
    declared = LANE_OBJECTIVES if objectives is None else tuple(objectives)
    lanes = [one.lane for one in declared]
    twice = sorted({lane.value for lane in lanes if lanes.count(lane) > 1})
    if twice:
        msg = (
            f"{twice} declared more than once, so a reading would depend on which objective "
            "was read first"
        )
        raise ServiceLevelError(msg)
    return declared


def reading_for(objective: LaneObjective, observations: Sequence[Observation]) -> LaneReading:
    """One lane's reading from the observations already known to be in its window and lane."""
    lane = objective.lane.value
    if not observations:
        return LaneReading(
            objective=objective,
            requests=0,
            p95_ms=None,
            success_rate=None,
            shortfalls=(
                f"nothing was asked through the {lane} lane in this window, so its objective "
                "is unmeasured rather than met",
            ),
        )
    count = len(observations)
    rate = success_rate([one.status for one in observations])
    p95: float | None = None
    too_few: tuple[str, ...] = ()
    if objective.p95_ms is not None:
        needed = minimum_rows(P95)
        if count >= needed:
            p95 = percentile_ms([one.duration_ms for one in observations], P95)
        else:
            too_few = (
                f"the {lane} lane has {count} request(s) in this window and a 95th percentile "
                f"needs {needed} to be a rank rather than the slowest request",
            )
    return LaneReading(
        objective=objective,
        requests=count,
        p95_ms=p95,
        success_rate=rate,
        shortfalls=(
            *too_few,
            *attainment(objective, observed_p95_ms=p95, observed_success_rate=rate),
        ),
    )


def against_target(
    observations: Sequence[Observation],
    *,
    start: datetime,
    end: datetime,
    objectives: Sequence[LaneObjective] | None = None,
) -> ServiceLevels:
    """Every declared lane's attainment over `[start, end)` (M30.5.3, not claimed).

    Refuses an observation on a lane no objective declares rather than dropping it: a request
    measured against nothing is a request the reading silently leaves out, and the lane it was
    on is then the one whose figures look best.
    """
    _window(start, end)
    declared = _declared(objectives)
    promised = {one.lane for one in declared}
    inside = [one for one in observations if start <= one.received_at < end]
    unpromised = sorted({one.lane.value for one in inside if one.lane not in promised})
    if unpromised:
        msg = f"requests on {unpromised} are in the window and no objective declares that lane"
        raise ServiceLevelError(msg)
    return ServiceLevels(
        start=start,
        end=end,
        lanes=tuple(
            reading_for(objective, [one for one in inside if one.lane is objective.lane])
            for objective in declared
        ),
    )
