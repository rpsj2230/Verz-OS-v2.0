"""The one place a part is loaded, used, measured and ended.

**One part is resident at a time, one request is served at a time, and an idle part's process is
ended.** `brain.ops.model_server` is where the design is argued; this is the machinery, and each
rule is something a caller of it can see without reading a model's code.

A request for the part that is loaded goes straight to it. A request for another part ends the one
that is loaded, asks the host whether the new one fits (`admit`), starts it and serves. A request
that arrives while one is being served waits for the lock, up to `QUEUE_WAIT_SECONDS`, and is
answered busy beyond that, which the application reads as an outage and retries from its queue. A
part idle for `idle_seconds` is ended by `reap`, which the gateway calls every few seconds, and the
container then holds what the supervisor holds and nothing else.

**Every refusal the supervisor makes is a 503 or a 404, never a 4xx the application would read as
its own fault.** A request the application sent correctly and the server could not serve now is an
outage and not a malformed request: a 400 would make the application stop sending it, and the
document would never be read. `brain.connectors.throttle.classify` reads 5xx as unavailable and
the queue re-drives it, which is the only reading under which nothing is lost.

**The memory report is added here and is never the reason for a failure.** A measured request gets a
`memory` block in its answer; one that could not be measured gets none, and the answer is returned
as it was.

**What is rejected.** A thread pool of parts, which is more than one resident. A cache of loaded
parts evicted by size, which is a policy for deciding which one to keep and the whole point of this
design is that nothing is kept. And an `asyncio` server, because every part is a blocking library
call in another process and the only concurrency that matters is the lock.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO, Final, Protocol, cast

from inference_server.admit import admit, mem_available_mib
from inference_server.config import ServerConfig
from inference_server.framing import FrameError, read_frame, write_frame
from inference_server.meter import REPORT_KEY, Meter, report

#: How long a request waits for the part that is serving another one before it is told to come back.
QUEUE_WAIT_SECONDS: Final = 20.0

#: How long a part may take to answer one request before its process is ended, in seconds. A model
#: load and a large document are both inside it; a part that is past it is wedged, not busy, and the
#: cost of killing a working one is a request the application retries.
REQUEST_SECONDS: Final = 900.0

#: How long a part may take to say it has loaded.
LOAD_SECONDS: Final = 300.0

#: The ceiling on one frame back from a part. An answer is blocks or vectors, not a document.
ANSWER_CEILING: Final = 256 * 1024 * 1024


class PartFailed(Exception):  # noqa: N818 - reads as an event, as `PartFailed` is raised and caught
    """A part's process would not start, died, or sent something that is not an answer."""


@dataclass(frozen=True)
class Reply:
    """What the gateway sends back: a status and the body as bytes."""

    status: int
    body: bytes


def _json(status: int, body: dict[str, object]) -> Reply:
    return Reply(status, json.dumps(body, separators=(",", ":")).encode("utf-8"))


class PartProcess(Protocol):
    """One part's process, as the supervisor uses it: faked in tests, a subprocess in the image."""

    def start(self) -> str:
        """Load the part and answer with the model's name and revision, or raise `PartFailed`."""

    def call(self, body: bytes) -> bytes:
        """Send one request and read the one answer, or raise `PartFailed`."""

    def stop(self) -> None:
        """End the process and wait for it. Safe to call twice."""


class SubprocessPart:
    """A part run as `python -m inference_server.worker <part>`, spoken to over its pipes."""

    def __init__(
        self, part: str, *, env: dict[str, str] | None = None, argv: list[str] | None = None
    ) -> None:
        self._part = part
        self._env = env
        #: Fixed by this program, never taken from a request. A parameter so a test can run a
        #: stand-in that speaks the same frames and be sure a process really ends.
        self._argv = argv
        self._process: subprocess.Popen[bytes] | None = None

    def _binary(self, stream: object) -> BinaryIO:
        return cast(BinaryIO, stream)

    def _kill_after(self, seconds: float) -> threading.Timer:
        timer = threading.Timer(seconds, self.stop)
        timer.daemon = True
        timer.start()
        return timer

    def start(self) -> str:
        argv = self._argv or [sys.executable, "-m", "inference_server.worker", self._part]
        # A fixed argv built from a part name this program validated against its own list.
        # In a session of its own, so that everything the part starts (the general reader's JVM,
        # a recogniser's child) is in the process group this program ends, and ending the part
        # leaves nothing of it holding memory.
        self._process = subprocess.Popen(  # noqa: S603
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=self._env,
            start_new_session=True,
        )
        timer = self._kill_after(LOAD_SECONDS)
        try:
            frame = read_frame(self._binary(self._process.stdout), ceiling=ANSWER_CEILING)
        except (FrameError, OSError) as error:
            self.stop()
            msg = f"the {self._part} part's process ended before it said it had loaded"
            raise PartFailed(msg) from error
        finally:
            timer.cancel()
        if frame is None:
            self.stop()
            msg = f"the {self._part} part's process ended before it said it had loaded"
            raise PartFailed(msg)
        try:
            hello = json.loads(frame)
            label = str(hello["model"])
        except (ValueError, KeyError, TypeError) as error:
            self.stop()
            msg = f"the {self._part} part said something that is not that it had loaded"
            raise PartFailed(msg) from error
        return label

    def call(self, body: bytes) -> bytes:
        process = self._process
        if process is None or process.poll() is not None:
            msg = f"the {self._part} part's process is not running"
            raise PartFailed(msg)
        timer = self._kill_after(REQUEST_SECONDS)
        try:
            write_frame(self._binary(process.stdin), body)
            answer = read_frame(self._binary(process.stdout), ceiling=ANSWER_CEILING)
        except (FrameError, OSError, ValueError) as error:
            self.stop()
            msg = f"the {self._part} part's process ended while it worked"
            raise PartFailed(msg) from error
        finally:
            timer.cancel()
        if answer is None:
            self.stop()
            msg = f"the {self._part} part's process ended while it worked"
            raise PartFailed(msg)
        return answer

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        for stream in (process.stdin, process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        if process.poll() is None:
            self._signal_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._signal_group(process, signal.SIGKILL)
                process.wait()
        # Whatever the part started and did not wait for: a part that ended by itself leaves its
        # children in the group, and they are the memory this call exists to give back.
        self._signal_group(process, signal.SIGKILL)

    @staticmethod
    def _signal_group(process: subprocess.Popen[bytes], sent: int) -> None:
        """Send a signal to the part's whole process group, which `start` made its own."""
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, sent)


class Supervisor:
    """Holds the one part that is loaded and the lock that serves one request at a time."""

    def __init__(
        self,
        config: ServerConfig,
        *,
        spawn: Callable[[str], PartProcess] | None = None,
        clock: Callable[[], float] = time.monotonic,
        available: Callable[[], int | None] = mem_available_mib,
        meter: Callable[[], Meter] = Meter,
    ) -> None:
        self._config = config
        self._spawn = spawn or (lambda part: SubprocessPart(part))
        self._clock = clock
        self._available = available
        self._meter = meter
        self._lock = threading.Lock()
        self._loaded: str | None = None
        self._process: PartProcess | None = None
        self._label = ""
        self._last_used = 0.0

    @property
    def loaded(self) -> str | None:
        """The part that is in memory now, or None when only the supervisor is."""
        return self._loaded

    def _unload(self) -> None:
        process, self._process, self._loaded, self._label = self._process, None, None, ""
        if process is not None:
            process.stop()

    def _load(self, part: str) -> Reply | None:
        """Make this part the loaded one, or answer with why it cannot be."""
        if self._loaded == part and self._process is not None:
            return None
        self._unload()
        decision = admit(
            part,
            need_mib=self._config.needs_mib[part],
            available_mib=self._available(),
        )
        if not decision.admitted:
            return _json(503, {"refusal": decision.words})
        process = self._spawn(part)
        try:
            label = process.start()
        except PartFailed as error:
            process.stop()
            return _json(503, {"refusal": str(error)})
        self._process, self._loaded, self._label = process, part, label
        return None

    def handle(self, part: str, body: bytes) -> Reply:
        """Serve one request for this part, loading it first when it is not the loaded one."""
        if part not in self._config.parts:
            return _json(404, {"refusal": f"the {part} part is not run by this install"})
        if not self._lock.acquire(timeout=QUEUE_WAIT_SECONDS):
            return _json(503, {"refusal": "the server is busy with another request"})
        try:
            refused = self._load(part)
            if refused is not None:
                return refused
            process = self._process
            if process is None:  # pragma: no cover - `_load` binds it whenever it returns None
                return _json(503, {"refusal": f"the {part} part is not loaded"})
            meter = self._meter()
            meter.start()
            try:
                answer = process.call(body)
            except PartFailed as error:
                meter.stop()
                self._unload()
                return _json(503, {"refusal": str(error)})
            measured = meter.stop()
            self._last_used = self._clock()
            return self._finished(answer, len(body), measured)
        finally:
            self._lock.release()

    def _finished(self, answer: bytes, request_bytes: int, measured: object) -> Reply:
        """The part's envelope as a reply, with the memory block added when there is one."""
        try:
            envelope = json.loads(answer)
            status = int(envelope["status"])
            payload = dict(envelope["answer"])
            items = int(envelope.get("items", 0))
        except (ValueError, KeyError, TypeError):
            unreadable = f"the {self._loaded} part sent an answer nobody can read"
            return _json(503, {"refusal": unreadable})
        block = report(
            model=self._label,
            items=items,
            request_bytes=request_bytes,
            measured=measured,  # type: ignore[arg-type]
            duration_ms=getattr(measured, "duration_ms", 0),
        )
        if block is not None and status == 200:
            payload[REPORT_KEY] = block
        return _json(status, payload)

    def reap(self) -> str | None:
        """End the loaded part if it has been idle for the whole of `idle_seconds`, and say which.

        Never ends one that is serving: the lock is tried without waiting and a request holds it for
        as long as it is working.
        """
        if not self._lock.acquire(blocking=False):
            return None
        try:
            ended = self._loaded
            if ended is None or self._clock() - self._last_used < self._config.idle_seconds:
                return None
            self._unload()
            return ended
        finally:
            self._lock.release()

    def close(self) -> None:
        """End whatever is loaded. Called when the container is told to stop."""
        with self._lock:
            self._unload()
