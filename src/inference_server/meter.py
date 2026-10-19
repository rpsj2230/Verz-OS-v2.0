"""What the container held at its peak while it served a request, split by what can be given back.

The model server is sized from judgements until it reports its own peak, and this is how it does.
**Two figures and never their sum**, because they are two different promises. Anonymous memory is
the heap, the stacks and the arenas: nothing can take it back, and it is what the host has to have
spare. Cache is file-backed pages, the memory-mapped weights among them: the kernel charges them to
the container that read them and takes them back under pressure before it kills anything. A single
"resident" figure would blur them, and the blurred figure is the one that makes a host look full
when it holds gigabytes it would hand over. See `brain.ops.model_server.CACHE_IS_COUNTED_AS_CACHE`.

**Read from the container's own cgroup, so the children count.** A part runs as a child process and
Tika as a JVM beside it; a peak taken from the supervisor's own process would report the cost of an
HTTP server. The cgroup is the one thing every process of the container is charged to and the one
the kernel kills by, so it is the figure that has to be under the limit. Version 2 and version 1 are
both read because a client's host is whichever it is; neither present (a developer's machine, a
test) is no measurement, and the report says so by carrying no figures and not by carrying zeros.

**Sampled, not exact, and it says so.** A thread reads the cgroup every `INTERVAL_SECONDS` and keeps
the largest. A spike shorter than the interval is missed, so the figure is a floor on the true peak,
which is the safe direction for a number a limit is tuned up from and the unsafe one for a number it
is tuned down from; `brain.ops.model_server.suggested_limit_mib` adds a margin for that reason and
is never applied by itself.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The key an answer carries its report under, and the keys of it. Spelled as
#: `brain.ops.model_server_peaks.REPORT_KEY` and `REPORT_FIELDS`, which a test holds equal.
REPORT_KEY: Final = "memory"
REPORT_FIELDS: Final[tuple[str, ...]] = (
    "model",
    "items",
    "request_bytes",
    "duration_ms",
    "anon_peak_mib",
    "cache_peak_mib",
    "cgroup_limit_mib",
)

#: How often the cgroup is read while a request is served, in seconds.
INTERVAL_SECONDS: Final = 0.05

_MIB: Final = 1024 * 1024
_CGROUP: Final = Path("/sys/fs/cgroup")


@dataclass(frozen=True)
class Sample:
    """The cgroup at one instant, in bytes. `limit` is None when the kernel says there is none."""

    anon: int
    file: int
    limit: int | None


def _stat(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for line in text.splitlines():
        name, _, value = line.partition(" ")
        if value.strip().isdigit():
            found[name] = int(value)
    return found


def read_sample(root: Path = _CGROUP) -> Sample | None:
    """The container's memory now, from the cgroup it is in, or None where there is none to read.

    Version 2 first (`memory.stat` has `anon`, `file` and `shmem`), then version 1 (`rss`, `cache`
    and `shmem` under `memory/`). Shared memory is counted as anonymous: it is charged as cache
    and the kernel cannot reclaim it without swap, which this container does not have.
    """
    try:
        stat = _stat((root / "memory.stat").read_text(encoding="utf-8"))
        if "anon" in stat:
            limit_text = (root / "memory.max").read_text(encoding="utf-8").strip()
            limit = int(limit_text) if limit_text.isdigit() else None
            shared = stat.get("shmem", 0)
            return Sample(
                anon=stat["anon"] + shared, file=max(stat.get("file", 0) - shared, 0), limit=limit
            )
    except (OSError, ValueError):
        pass
    try:
        stat = _stat((root / "memory" / "memory.stat").read_text(encoding="utf-8"))
        if "rss" in stat:
            raw = int((root / "memory" / "memory.limit_in_bytes").read_text(encoding="utf-8"))
            shared = stat.get("shmem", 0)
            # Version 1 reports "no limit" as a number near 2**63, which is not a limit anybody set.
            limit = raw if raw < 1 << 60 else None
            return Sample(
                anon=stat["rss"] + shared, file=max(stat.get("cache", 0) - shared, 0), limit=limit
            )
    except (OSError, ValueError):
        pass
    return None


@dataclass(frozen=True)
class Measurement:
    """The largest anonymous and cache figures seen while a request was served, in MiB."""

    anon_peak_mib: int
    cache_peak_mib: int
    cgroup_limit_mib: int | None
    duration_ms: int


def _mib(value: int) -> int:
    return -(-value // _MIB)


class Meter:
    """Samples the cgroup in the background for as long as a request is being served.

    The reader and the clock are parameters for the reason `brain.models.routing.CircuitBreaker`
    takes `now`: a meter whose peak can only be seen by running a real container is a meter nobody
    tests the arithmetic of.
    """

    def __init__(
        self,
        read: Callable[[], Sample | None] = read_sample,
        *,
        interval: float = INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read = read
        self._interval = interval
        self._clock = clock
        self._anon = 0
        self._file = 0
        self._limit: int | None = None
        self._seen = False
        self._started = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _take(self) -> None:
        sample = self._read()
        if sample is None:
            return
        self._seen = True
        self._anon = max(self._anon, sample.anon)
        self._file = max(self._file, sample.file)
        self._limit = sample.limit

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._take()

    def start(self) -> None:
        """Take the first sample now and keep sampling until `stop`."""
        self._started = self._clock()
        self._take()
        self._thread = threading.Thread(target=self._run, name="memory-meter", daemon=True)
        self._thread.start()

    def stop(self) -> Measurement | None:
        """Take a last sample, end the thread, and answer with the peak, or None if unreadable."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._take()
        duration = int((self._clock() - self._started) * 1000)
        if not self._seen:
            return None
        return Measurement(
            anon_peak_mib=_mib(self._anon),
            cache_peak_mib=_mib(self._file),
            cgroup_limit_mib=None if self._limit is None else _mib(self._limit),
            duration_ms=max(duration, 0),
        )


def report(
    *, model: str, items: int, request_bytes: int, measured: Measurement | None, duration_ms: int
) -> dict[str, object] | None:
    """The block an answer carries, or None when nothing could be measured.

    None rather than a block of zeros: a zero is a measurement, and a recorded zero would pull a
    suggested limit down on the strength of a machine that could not be read.
    """
    if measured is None:
        return None
    return {
        "model": model,
        "items": items,
        "request_bytes": request_bytes,
        "duration_ms": duration_ms,
        "anon_peak_mib": measured.anon_peak_mib,
        "cache_peak_mib": measured.cache_peak_mib,
        "cgroup_limit_mib": measured.cgroup_limit_mib,
    }
