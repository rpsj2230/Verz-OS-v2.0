"""What the console is asking of this process: reads in flight, and how long a report takes.

`brain.ops.scaling` declared the two triggers that wait on a measurement (a read replica when
console reads take connections the answer path is sized to need, materialised reports when a report
is slower than a person waiting should be made to wait) and the Capacity screen served both as "not
measured", because nothing on an install counted a console read or timed a report. This is the
counter, and it decides nothing: `scaling.replica_is_due` and `scaling.report_is_due` are the
decisions, called with what this holds.

**It is this process's own view, and it says so.** An install runs several web processes and each
holds its own window, so a reading is what the process that answered the Capacity screen has seen
since it started, and the screen's sentence names that. The cheaper-looking design is a table the
processes write and the screen sums, and it was rejected: a write per console read to measure
console reads is the load being measured, and a number two seconds stale from a table is no better
for a trigger a person weighs once a quarter than a number from the process in front of them. A
reading too thin to support a percentile is not a reading (`MINIMUM_REPORTS_FOR_A_P95`), for the
reason a load run's is not: a p95 over three requests is the slowest of them.

**What counts is a GET under the API.** A console read is a GET beneath `/api/v1`; an answer is a
POST and a stream is a POST, so neither is counted here, and the health probes sit outside the API.
A report is a GET beneath `/api/v1/report/`. Nothing is recorded about who asked or what: a count,
and a duration against the route group, never a path, a query or a person.

**Peak in flight is kept per minute for an hour.** The trigger compares a count with the headroom
the interactive pool has once the answer path has its peak, so the figure that matters is the most
reads that were in flight together, and a mean would sit far below it. The hour is a window long
enough to include a busy minute and short enough that a fixed problem stops reading as a current
one.

Task ids: M36.1.2.4, M36.1.3.3
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

#: Where the API lives, restated so this module imports nothing from the web layer.
API_PREFIX: Final = "/api/v1"

#: A report is a GET beneath this.
REPORT_PREFIX: Final = f"{API_PREFIX}/report/"

#: How many report durations the window keeps.
REPORT_WINDOW: Final = 500

#: The fewest reports a 95th percentile may be read from. See the module docstring.
MINIMUM_REPORTS_FOR_A_P95: Final = 20

#: How long the peak in flight is remembered, in one-minute buckets.
PEAK_MINUTES: Final = 60


@dataclass(frozen=True)
class Reading:
    """What this process has seen, with the counts that say how much that is."""

    #: The most console reads in flight together in the last hour, or None where none was seen.
    peak_reads_in_flight: int | None
    #: The 95th percentile of report durations in milliseconds, or None where too few were seen.
    report_p95_ms: float | None
    #: How many report durations the window holds, so a thin reading is visibly thin.
    reports_seen: int


@dataclass(frozen=True)
class Begun:
    """A request that has started and is counted until `finish`."""

    report: bool
    started: float


def is_console_read(method: str, path: str) -> bool:
    """Whether this request is a console read: a GET beneath the API."""
    return method == "GET" and path.startswith(f"{API_PREFIX}/")


def is_report(path: str) -> bool:
    """Whether this path is a report screen's read."""
    return path.startswith(REPORT_PREFIX)


def nearest_rank(samples: list[float], fraction: float) -> float:
    """Nearest-rank percentile, never interpolated. The sample must not be empty."""
    ordered = sorted(samples)
    return ordered[max(1, math.ceil(fraction * len(ordered))) - 1]


class ReadLoad:
    """A process's count of console reads in flight and window of report durations."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._in_flight = 0
        #: `(minute, most in flight during it)`, oldest first, at most `PEAK_MINUTES` long.
        self._peaks: deque[tuple[int, int]] = deque()
        self._reports: deque[float] = deque(maxlen=REPORT_WINDOW)

    def begin(self, method: str, path: str) -> Begun | None:
        """Count a request as started if it is a console read, and say how to finish it."""
        if not is_console_read(method, path):
            return None
        now = self._clock()
        with self._lock:
            self._in_flight += 1
            minute = int(now // 60)
            if self._peaks and self._peaks[-1][0] == minute:
                latest = self._peaks[-1]
                self._peaks[-1] = (minute, max(latest[1], self._in_flight))
            else:
                self._peaks.append((minute, self._in_flight))
                while len(self._peaks) > PEAK_MINUTES:
                    self._peaks.popleft()
        return Begun(report=is_report(path), started=now)

    def finish(self, begun: Begun | None, *, answered: bool = True) -> None:
        """Stop counting a request `begin` counted, and keep a report's duration if it was answered.

        A refusal or a failure is not a report taking its time: a request turned away at the door
        in a millisecond would pull the percentile down, and one that failed slowly would push it
        up, so only a report that was answered is a duration.
        """
        if begun is None:
            return
        took = self._clock() - begun.started
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            if begun.report and answered:
                self._reports.append(took * 1000.0)

    def reading(self) -> Reading:
        """What the window holds now."""
        now_minute = int(self._clock() // 60)
        with self._lock:
            recent = [most for minute, most in self._peaks if now_minute - minute < PEAK_MINUTES]
            reports = list(self._reports)
        return Reading(
            peak_reads_in_flight=max(recent) if recent else None,
            report_p95_ms=(
                nearest_rank(reports, 0.95) if len(reports) >= MINIMUM_REPORTS_FOR_A_P95 else None
            ),
            reports_seen=len(reports),
        )


#: This process's own. Replaced for the length of a check by `observing`.
_CURRENT = ReadLoad()


def current() -> ReadLoad:
    """The counter this process is using."""
    return _CURRENT


@contextmanager
def observing(load: ReadLoad) -> Iterator[ReadLoad]:
    """Use this counter for the length of the block, then put the process's own back.

    How an install check, which runs in the worker where no console read has been counted, shows
    the Capacity screen a reading without leaving anything behind in the process.
    """
    global _CURRENT
    before = _CURRENT
    _CURRENT = load
    try:
        yield load
    finally:
        _CURRENT = before
