"""A service level reading per lane, against the objectives it is measured against.

The figures compared against are `brain.ops.reliability`'s, and the tests here read them from
there rather than restating them, except where a figure has to be checked against something
outside itself: the sample a ninety-fifth percentile needs is twenty, which is arithmetic about
nearest rank rather than a declaration anywhere in this repository.

The store query that feeds this, and the whole path from the route, are in
`tests/unit/test_telemetry_store.py`.

M30.5.3 is not claimed; see `brain.ops.service_levels` for why.

Task ids: M30.5.2
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.lane import Lane
from brain.ops.reliability import (
    FAST_P95_MS,
    LANE_OBJECTIVES,
    SUCCESSFUL_REQUEST_RATE,
    lane_objective,
)
from brain.ops.service_levels import (
    A_LANE_WITH_NO_REQUESTS_IN_THE_WINDOW_IS_UNMEASURED_RATHER_THAN_MET,
    A_READING_WITH_NO_SCREEN_HAS_NO_READER_DECISION,
    LaneReading,
    Observation,
    ServiceLevelError,
    against_target,
)
from brain.ops.telemetry import RequestStatus, request_telemetry_of
from tests.unit.test_answer_lane import ACME, SEES_NAME_ONLY, Rows, ents
from tests.unit.test_request_finish import Kept, lane

#: Far outside any plausible wall clock. Nothing here is about the present.
START = datetime(2999, 6, 1, tzinfo=UTC)
END = START + timedelta(days=30)
INSIDE = START + timedelta(days=1)

#: How many observations a nearest-rank ninety-fifth percentile needs before it can be anything
#: but the largest: ceil(1 / (1 - 0.95)). Written as the arithmetic, not imported.
RANK_NEEDS = 20


def seen(
    lane_: Lane = Lane.FAST,
    status: RequestStatus = RequestStatus.ANSWERED,
    duration_ms: float = 10.0,
    at: datetime = INSIDE,
) -> Observation:
    return Observation(lane=lane_, status=status, duration_ms=duration_ms, received_at=at)


def reading(observations: list[Observation], which: Lane = Lane.FAST) -> LaneReading:
    levels = against_target(observations, start=START, end=END)
    (found,) = [one for one in levels.lanes if one.objective.lane is which]
    return found


def test_a_lane_inside_its_objective_reads_met_with_its_figures() -> None:
    """Twenty fast requests from one millisecond to twenty: the ninety-fifth percentile by nearest
    rank is the nineteenth, every one succeeded, and nothing is short.

    Delete this and a reading that reports every lane short passes every refusal test here."""
    found = reading([seen(duration_ms=float(one)) for one in range(1, 21)])

    assert found.requests == 20
    assert found.p95_ms == 19.0
    assert found.success_rate == 1.0
    assert found.shortfalls == ()
    assert found.met


def test_a_lane_over_its_latency_and_under_its_success_rate_reads_both_shortfalls() -> None:
    """Measured figures handed to `attainment`, which is the one comparison: a percentile above
    the target and a success rate below it are two sentences, naming the measured figures.

    Delete this and the reading can hand `attainment` nothing, and every lane is short for want
    of a measurement it had."""
    slow = [seen(duration_ms=float(FAST_P95_MS + 100)) for _ in range(19)]
    slow.append(seen(status=RequestStatus.FAILED, duration_ms=float(FAST_P95_MS + 100)))

    found = reading(slow)

    assert found.p95_ms == float(FAST_P95_MS + 100)
    assert found.success_rate == 0.95
    assert found.success_rate < SUCCESSFUL_REQUEST_RATE
    assert len(found.shortfalls) == 2
    assert any(f"{FAST_P95_MS + 100}ms" in one for one in found.shortfalls)
    assert any("0.9500" in one for one in found.shortfalls)


def test_a_lane_nothing_was_asked_through_is_present_and_unmeasured_rather_than_met() -> None:
    """See `A_LANE_WITH_NO_REQUESTS_IN_THE_WINDOW_IS_UNMEASURED_RATHER_THAN_MET`. No traffic
    anywhere: every declared lane is on the reading, with no figures and a shortfall.

    Delete this and an empty window reads green, which is what a stopped ingest looks like."""
    levels = against_target([], start=START, end=END)

    assert [one.objective.lane for one in levels.lanes] == [one.lane for one in LANE_OBJECTIVES]
    for one in levels.lanes:
        assert (one.requests, one.p95_ms, one.success_rate) == (0, None, None)
        assert len(one.shortfalls) == 1
        assert "unmeasured rather than met" in one.shortfalls[0]
    assert A_LANE_WITH_NO_REQUESTS_IN_THE_WINDOW_IS_UNMEASURED_RATHER_THAN_MET


def test_a_percentile_is_withheld_below_the_sample_a_rank_needs_and_taken_at_it() -> None:
    """Nineteen requests have no ninety-fifth percentile that is not the slowest request, so the
    latency objective is unmeasured and says how many it needs; twenty have one. The success rate
    is measured either way.

    Delete this and a lane with three requests reports its slowest as its percentile, and a
    single slow request turns a quiet lane's objective red."""
    nineteen = reading([seen() for _ in range(RANK_NEEDS - 1)])
    twenty = reading([seen() for _ in range(RANK_NEEDS)])

    assert nineteen.p95_ms is None
    assert nineteen.success_rate == 1.0
    assert any(f"needs {RANK_NEEDS}" in one for one in nineteen.shortfalls)
    assert any("nothing measures one" in one for one in nineteen.shortfalls)
    assert twenty.p95_ms == 10.0
    assert twenty.shortfalls == ()


def test_the_task_lane_takes_no_percentile_and_is_not_short_for_want_of_one() -> None:
    """The task lane promises no percentile, so none is taken even over enough requests, and its
    reading is met on the success rate alone.

    Delete this and the task lane's argued absence of a latency target is measured anyway, and
    a nine-minute task reads as a breach."""
    found = reading([seen(Lane.TASK, duration_ms=540_000.0) for _ in range(25)], Lane.TASK)

    assert lane_objective(Lane.TASK).p95_ms is None
    assert found.p95_ms is None
    assert found.shortfalls == ()


def test_a_withheld_request_and_an_absent_one_read_identically_and_a_fault_does_not() -> None:
    """See `A_WITHHELD_REQUEST_AND_AN_ABSENT_ONE_ARE_ONE_OBSERVATION`, through the real lane. One
    person asks about a record whose answer field they may not read, and about one that does not
    exist; built into observations through the ledger's own mapping, the two windows read the
    same. A fault in place of either is the positive sibling, and it reads differently.

    Delete this and the reading can grow a figure per status, from which a reader subtracts the
    number of things somebody was refused."""

    def observed(rows: Rows) -> Observation:
        kept = Kept()
        lane(reach=ents(*SEES_NAME_ONLY), rows=rows, recorders=(kept,))
        telemetry = request_telemetry_of(kept.seen[0])
        return seen(telemetry.lane, telemetry.status, telemetry.duration_ms)

    withheld, absent = observed(Rows(ACME)), observed(Rows())
    fault = seen(status=RequestStatus.FAILED, duration_ms=withheld.duration_ms)

    assert reading([withheld] * RANK_NEEDS) == reading([absent] * RANK_NEEDS)
    assert reading([withheld] * RANK_NEEDS).met
    assert reading([fault] * RANK_NEEDS) != reading([withheld] * RANK_NEEDS)


def test_a_reading_holds_no_count_of_any_status() -> None:
    """Five fields on a lane's reading and no sixth, asserted against a list written here: the
    objective, the number of requests, the percentile, the success rate and the shortfalls. A
    count per status, or of refusals, has nowhere to go.

    Delete this and a `nothing_returned` field is one helpful edit away."""
    assert {one.name for one in fields(LaneReading)} == {
        "objective",
        "requests",
        "p95_ms",
        "success_rate",
        "shortfalls",
    }
    assert {one.name for one in fields(Observation)} == {
        "lane",
        "status",
        "duration_ms",
        "received_at",
    }


def test_the_window_holds_its_start_and_not_its_end() -> None:
    """`[start, end)`, which is the store query's own window. A request at the end is the next
    window's and a request at the start is this one's.

    Delete this and a request at midnight is measured in both windows or in neither."""
    found = reading(
        [
            seen(at=START - timedelta(microseconds=1)),
            seen(at=START),
            seen(at=END - timedelta(microseconds=1)),
            seen(at=END),
        ]
    )

    assert found.requests == 2


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (START.replace(tzinfo=None), END),
        (START, END.replace(tzinfo=None)),
        (START, START),
        (END, START),
    ],
)
def test_a_window_with_no_timezone_or_no_time_in_it_is_refused(
    start: datetime, end: datetime
) -> None:
    """A naive window cannot be compared with the ledger's instants, and a window of no time or
    negative time holds nothing to measure. The positive sibling is every other test here.

    Delete this and an empty window reads as a lane with no traffic, and a naive one raises a
    comparison error from somewhere less helpful."""
    with pytest.raises(ServiceLevelError):
        against_target([], start=start, end=end)


def test_a_request_on_an_undeclared_lane_is_refused_inside_the_window_and_not_outside() -> None:
    """A client's own objectives can omit a lane. A request on that lane inside the window would
    be measured against nothing and silently left out, so the reading refuses; one outside the
    window is not being measured and is not a reason to refuse.

    Delete this and a client who declares no task objective sees a reading that quietly drops
    every task."""
    without_task = [one for one in LANE_OBJECTIVES if one.lane is not Lane.TASK]

    with pytest.raises(ServiceLevelError, match="task"):
        against_target([seen(Lane.TASK)], start=START, end=END, objectives=without_task)
    outside = against_target(
        [seen(Lane.TASK, at=END)], start=START, end=END, objectives=without_task
    )
    assert [one.objective.lane for one in outside.lanes] == [Lane.FAST, Lane.ANSWER]


def test_objectives_declaring_one_lane_twice_are_refused() -> None:
    """Two objectives for one lane make the reading depend on which is read first. The positive
    sibling is the declared set, which every other test here reads.

    Delete this and a client's duplicated line silently measures the lane against the laxer
    figure."""
    doubled = [*LANE_OBJECTIVES, lane_objective(Lane.FAST)]

    with pytest.raises(ServiceLevelError, match="fast"):
        against_target([], start=START, end=END, objectives=doubled)


def test_the_reading_names_its_window_and_why_it_has_no_reader_check() -> None:
    """The window a reading covers travels with it, so a renderer cannot show the figures without
    the period they are over. And the absence of a reader decision is stated where the screen's
    author will look.

    Delete this and a reading can be rendered with no period, which is a percentile of nothing
    in particular."""
    levels = against_target([seen()], start=START, end=END)

    assert (levels.start, levels.end) == (START, END)
    assert "No screen" in A_READING_WITH_NO_SCREEN_HAS_NO_READER_DECISION
