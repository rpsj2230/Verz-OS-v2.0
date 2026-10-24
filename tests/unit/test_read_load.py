"""What the console asks of a process: reads in flight, the busiest minute, and report durations.

Task ids: M36.1.2.4, M36.1.3.3
"""

from __future__ import annotations

import pytest

from brain.ops import read_load
from brain.ops.read_load import (
    MINIMUM_REPORTS_FOR_A_P95,
    PEAK_MINUTES,
    REPORT_WINDOW,
    ReadLoad,
    is_console_read,
    is_report,
    nearest_rank,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_only_a_get_beneath_the_api_is_a_console_read() -> None:
    """An answer is a POST, a stream is a POST, a probe sits outside the API, and a report is a GET
    beneath the report prefix. Delete this and an answer counts against the console's headroom, or
    the health probe does."""
    assert is_console_read("GET", "/api/v1/agents")
    assert not is_console_read("POST", "/api/v1/ask")
    assert not is_console_read("GET", "/healthz")
    assert not is_console_read("GET", "/api/v10/x")
    assert is_report("/api/v1/report/spend") and not is_report("/api/v1/agents")


def test_the_busiest_minute_is_what_is_kept_and_not_the_last_count() -> None:
    """Three reads in flight together, then all finished, still read three. Delete this and the
    reading is the instant's count, which is nought whenever anybody looks."""
    clock = Clock()
    load = ReadLoad(clock)
    started = [load.begin("GET", "/api/v1/agents") for _ in range(3)]
    for one in started:
        load.finish(one)
    assert load.reading().peak_reads_in_flight == 3
    load.finish(None)
    assert load.reading().peak_reads_in_flight == 3


def test_a_reading_older_than_the_hour_is_forgotten() -> None:
    """A busy minute stops counting an hour later. Delete this and a problem fixed last week reads
    as a current one."""
    clock = Clock()
    load = ReadLoad(clock)
    load.finish(load.begin("GET", "/api/v1/agents"))
    clock.now += 60 * PEAK_MINUTES
    assert load.reading().peak_reads_in_flight is None
    clock.now -= 60
    assert load.reading().peak_reads_in_flight == 1


def test_an_answer_is_not_counted() -> None:
    """A POST begins nothing and finishes nothing. Delete this and the answer path is its own
    console load."""
    load = ReadLoad(Clock())
    assert load.begin("POST", "/api/v1/ask") is None
    assert load.reading().peak_reads_in_flight is None


def test_a_percentile_is_not_read_from_a_handful_of_reports() -> None:
    """Nineteen reports give no 95th percentile and twenty give the nearest rank. Delete this and a
    p95 over three requests is the slowest of them."""
    clock = Clock()
    load = ReadLoad(clock)
    for number in range(MINIMUM_REPORTS_FOR_A_P95 - 1):
        begun = load.begin("GET", "/api/v1/report/spend")
        clock.now += 0.1 * (number + 1)
        load.finish(begun)
    assert load.reading().report_p95_ms is None
    assert load.reading().reports_seen == MINIMUM_REPORTS_FOR_A_P95 - 1
    begun = load.begin("GET", "/api/v1/report/spend")
    clock.now += 2.0
    load.finish(begun)
    assert load.reading().report_p95_ms == pytest.approx(1900.0, rel=0.01)


def test_a_report_that_was_refused_is_not_a_duration() -> None:
    """A refusal in a millisecond would pull the percentile down. Delete this and a flood of
    unsigned requests makes the reports look fast."""
    load = ReadLoad(Clock())
    for _ in range(50):
        load.finish(load.begin("GET", "/api/v1/report/spend"), answered=False)
    assert load.reading().reports_seen == 0


def test_the_window_keeps_only_the_newest_reports() -> None:
    """Delete this and the window grows without bound, or keeps the oldest."""
    clock = Clock()
    load = ReadLoad(clock)
    for number in range(REPORT_WINDOW + 10):
        begun = load.begin("GET", "/api/v1/report/spend")
        clock.now += 0.001 if number < 10 else 5.0
        load.finish(begun)
    reading = load.reading()
    assert reading.reports_seen == REPORT_WINDOW
    assert reading.report_p95_ms == pytest.approx(5000.0, rel=0.01)


def test_nearest_rank_is_never_interpolated() -> None:
    """Delete this and a percentile is a figure no request took."""
    assert nearest_rank([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert nearest_rank([10.0], 0.95) == 10.0


def test_a_check_can_swap_the_counter_and_the_process_gets_its_own_back() -> None:
    """Delete this and a check's readings stay behind in the worker."""
    own = read_load.current()
    swapped = ReadLoad(Clock())
    with read_load.observing(swapped) as inside:
        assert read_load.current() is inside is swapped
    assert read_load.current() is own


def test_the_applications_trace_middleware_counts_a_report_it_answered() -> None:
    """A signed-out GET of a report is counted in flight and is not a duration, because it was
    refused; an unknown path is not a report. Delete this and the middleware counts nothing, so the
    Capacity screen says 'not measured' for ever."""
    from fastapi.testclient import TestClient

    from brain.app import Settings, create_app

    app = create_app(Settings(env="development"))
    swapped = ReadLoad()
    with read_load.observing(swapped), TestClient(app) as client:
        client.get("/api/v1/report/spend")
        client.post("/api/v1/ask")
    seen = swapped.reading()
    assert seen.peak_reads_in_flight == 1
    assert seen.reports_seen == 0


def test_a_busy_instant_inside_a_minute_is_not_overwritten_by_a_quieter_one_after_it() -> None:
    """Three together, two finish, one more starts: the minute's most is three and not the two it
    ends at. Delete this and the peak is whatever the latest start saw."""
    load = ReadLoad(Clock())
    three = [load.begin("GET", "/api/v1/agents") for _ in range(3)]
    load.finish(three[0])
    load.finish(three[1])
    load.begin("GET", "/api/v1/agents")
    assert load.reading().peak_reads_in_flight == 3
