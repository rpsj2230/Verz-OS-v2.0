"""The script sandbox's two processes: a front that answers, and an executor with no network.

`brain.ops.sandbox` is the contract and `brain.ops.sandbox_client` the side that asks. This is the
side that answers, inside `docker-compose.sandbox.yml`'s two containers, both under gVisor with a
read-only root. It imports the contract's shapes and the standard library and nothing else of this
product, so what runs beside a stranger's script is a few hundred lines anybody can read.

**Two processes, because a script must have no network and the sandbox must answer on one.** The
front listens on the sandbox's internal network, checks a request against the contract and writes
it into a job directory on a volume the two share. The executor, in a container with no network
interface but loopback, takes the job, runs the script, and writes the answer back beside it. The
script therefore runs where there is nothing to connect to, by construction of its container rather
than by a rule a process beside it enforces. See `A_SCRIPT_RUNS_WHERE_THERE_IS_NO_NETWORK`.

**Every check is made twice, and the second one is the executor's.** The front refuses a request
whose bytes do not hash to what they were sent with, whose script is not among its files, whose
interpreter is not allowed, or whose files or standard input are too large (refused whole, never
cut), with the contract's codes and nothing else. The executor checks the same again before it
runs anything, because a job volume is a place a request could be written by something other
than the front, and an executor that trusted the front's say-so would be running whatever
appeared there.

**The limits are the kernel's, set on the script's own process.** Wall clock by a timer that kills
the script's process group; memory by `RLIMIT_AS`; everything it writes, its output included, by
`RLIMIT_FSIZE` on a memory-backed scratch directory; open files and processes by their own limits.
Each is the smaller of what the request asked and the contract's ceiling. Rejected: watching the
script from outside and killing it when it looks too big, which is a race the script can win by
allocating faster than the watcher looks.

**What it says about itself is read, not declared.** `/health` reports the runtime and network the
executor read from its own kernel on its last heartbeat: gVisor names itself in the kernel's log
and in the version it reports, and a container with no network has no interface but loopback. A
front whose executor has not reported recently is not healthy. See `isolation`.

Task ids: M12.4.5, M12.2.9, M11.1.5
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Final

from brain.ops.sandbox import (
    GVISOR_RUNTIME,
    HEALTH_PATH,
    INTERPRETERS,
    NO_NETWORK,
    RUN_PATH,
    SANDBOX_FILES_BYTES,
    SANDBOX_MEMORY_MIB,
    SANDBOX_OUTPUT_BYTES,
    SANDBOX_PORT,
    SANDBOX_STDIN_BYTES,
    SANDBOX_WALL_CLOCK_SECONDS,
    AnswerStatus,
    RefusalCode,
    RunAnswer,
    RunLimits,
    RunRequest,
    SandboxContractError,
)

# ------------------------------------------------------------------ written-down reasons
#: Why the script's container has no network rather than the script's process having none.
A_SCRIPT_RUNS_WHERE_THERE_IS_NO_NETWORK: Final = (
    "The executor's container is started with no network, so a script has no interface but "
    "loopback and nothing to resolve or connect to. Removing the network around each script from "
    "inside a container that has one would need a capability inside the sandbox and would make the "
    "isolation a property of code running beside the script; a container with no network makes it "
    "a property of the container."
)

# ------------------------------------------------------------------------- the figures
#: The suffixes a job directory moves through: written, waiting, taken, answered.
WRITING: Final = ".writing"
READY: Final = ".ready"
TAKEN: Final = ".taken"
DONE: Final = ".done"

#: The executor's report of itself, and how often it writes it.
HEARTBEAT: Final = ".executor.json"
HEARTBEAT_EVERY_SECONDS: Final = 5.0

#: How old a report may be before the front says it is not healthy: six missed heartbeats.
HEARTBEAT_STALE_SECONDS: Final = 30.0

#: How often the executor looks for a job, and the front for its answer.
POLL_SECONDS: Final = 0.05

#: How long past a run's own wall clock the front waits for its answer before it says it did not
#: answer: the executor's start-up of the interpreter and its writes, on a busy host.
ANSWER_GRACE_SECONDS: Final = 15.0

#: The largest body the front reads: the files' and standard input's ceilings in base64, which is
#: four thirds of them, and room for the rest of the request.
MAX_BODY_BYTES: Final = (SANDBOX_FILES_BYTES + SANDBOX_STDIN_BYTES) * 4 // 3 + 64 * 1024

#: The environment a script may be given, and only these.
ALLOWED_ENVIRONMENT: Final = frozenset({"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR"})

#: What a script may write in all, its output included: the scratch directory's own size.
WRITE_LIMIT_BYTES: Final = 16 * 1024 * 1024

#: Open files and processes a script may hold.
FILE_LIMIT: Final = 64
PROCESS_LIMIT: Final = 32

#: How a run id may be spelled, because it names a directory.
RUN_ID_CHARS: Final = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
RUN_ID_MAX: Final = 80

#: What gVisor's kernel says about itself, in the log it keeps and the version it reports.
GVISOR_LOG_MARK: Final = "gVisor"
GVISOR_VERSION_MARK: Final = "Sun Jan 10 15:06:54 PST 2016"

#: What a script that ran out of memory leaves in its output, by interpreter.
OUT_OF_MEMORY_MARKS: Final = ("MemoryError", "Cannot allocate memory", "out of memory")


# --------------------------------------------------------------------- checking a request
def limits_of(request: RunRequest) -> RunLimits:
    """The limits a run gets: what it asked for, never past the contract's ceilings."""
    return clamped(request.limits)


def clamped(limits: RunLimits) -> RunLimits:
    """The smaller of each limit asked for and the contract's ceiling."""
    return RunLimits(
        wall_clock_seconds=min(limits.wall_clock_seconds, SANDBOX_WALL_CLOCK_SECONDS),
        memory_mib=min(limits.memory_mib, SANDBOX_MEMORY_MIB),
        output_bytes=min(limits.output_bytes, SANDBOX_OUTPUT_BYTES),
    )


def _safe_path(path: str) -> bool:
    """A relative path that stays where it is put: no root, no climbing, no empty part."""
    if not path or "\\" in path or "\x00" in path:
        return False
    pure = PurePosixPath(path)
    return not pure.is_absolute() and all(part not in ("", ".", "..") for part in pure.parts)


def refusal_for(request: RunRequest) -> RefusalCode | None:
    """Why the contract refuses this request, or None when it may run. Made on both sides."""
    if not set(request.run_id) <= RUN_ID_CHARS or not 0 < len(request.run_id) <= RUN_ID_MAX:
        return RefusalCode.BAD_REQUEST
    if not all(_safe_path(path) for path in request.files):
        return RefusalCode.BAD_REQUEST
    if not set(request.environment) <= ALLOWED_ENVIRONMENT:
        return RefusalCode.BAD_REQUEST
    if request.too_large():
        return RefusalCode.TOO_LARGE
    if request.script not in request.files:
        return RefusalCode.SCRIPT_NOT_DECLARED
    if PurePosixPath(request.script).suffix not in INTERPRETERS:
        return RefusalCode.INTERPRETER_NOT_ALLOWED
    if set(request.sha256) != set(request.files) or any(
        hashlib.sha256(content).hexdigest() != request.sha256[path]
        for path, content in request.files.items()
    ):
        return RefusalCode.DIGEST_MISMATCH
    return None


# ---------------------------------------------------------------------- what it runs on
def isolation(
    *,
    version: Callable[[], str] | None = None,
    kernel_log: Callable[[], str] | None = None,
    interfaces: Callable[[], Sequence[str]] | None = None,
) -> tuple[str, str]:
    """The runtime and the network this process runs on, as its own kernel tells it.

    The runtime is `GVISOR_RUNTIME` when gVisor names itself in the kernel's log or in the version
    it reports, and "other" otherwise; the network is `NO_NETWORK` when there is no interface but
    loopback. Each reader is a parameter so a test can be a kernel; on the server they read
    `/proc/version`, the kernel's log and `/proc/net/dev`.
    """
    seen_version = (version or _proc_version)()
    seen_log = (kernel_log or _kernel_log)()
    names = set((interfaces or _interfaces)())
    runtime = (
        GVISOR_RUNTIME
        if GVISOR_LOG_MARK in seen_log or GVISOR_VERSION_MARK in seen_version
        else "other"
    )
    network = NO_NETWORK if names <= {"lo"} else "present"
    return runtime, network


def _proc_version() -> str:
    try:
        return Path("/proc/version").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _kernel_log() -> str:
    found = shutil.which("dmesg")
    if found is None:
        return ""
    try:
        return subprocess.run(  # noqa: S603 - a fixed program, no argument from a request
            [found], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _interfaces() -> list[str]:
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
    except OSError:
        return []
    return [line.split(":", 1)[0].strip() for line in lines if ":" in line]


# ----------------------------------------------------------------------- running a script
@dataclass(frozen=True)
class Ran:
    """What one script did, before it is an answer."""

    status: AnswerStatus
    exit_code: int
    output: bytes
    truncated: bool
    elapsed_seconds: float


def _limit_child(limits: RunLimits) -> Callable[[], None]:
    """The limits set on the script's own process just before it starts."""
    memory = limits.memory_mib * 1024 * 1024

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_FSIZE, (WRITE_LIMIT_BYTES, WRITE_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_NOFILE, (FILE_LIMIT, FILE_LIMIT))
        resource.setrlimit(resource.RLIMIT_NPROC, (PROCESS_LIMIT, PROCESS_LIMIT))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        cpu = limits.wall_clock_seconds + 1
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        # A write past the limit fails with an error the script sees, rather than killing it.
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)

    return apply


def command_for(request: RunRequest) -> list[str]:
    """The script's argv: its interpreter, the script, its arguments. No shell parses any of it."""
    suffix = PurePosixPath(request.script).suffix
    interpreter = shutil.which(INTERPRETERS[suffix]) or INTERPRETERS[suffix]
    isolated = ["-I"] if suffix == ".py" else []
    return [interpreter, *isolated, request.script, *request.arguments]


def run_script(
    request: RunRequest,
    place: Path,
    *,
    clock: Callable[[], float] = time.monotonic,
    limiter: Callable[[RunLimits], Callable[[], None]] | None = None,
) -> Ran:
    """Write the request's files under `place`, run its script there, and say what happened.

    `limiter` is `_limit_child` on the server. A parameter only because a development machine
    that is not Linux refuses an address-space limit, so a test there hands one without it and
    the memory test runs on Linux alone.
    """
    limit = (limiter or _limit_child)(limits_of(request))
    limits = clamped(request.limits)
    for path, content in request.files.items():
        target = place / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(place), "TMPDIR": str(place)}
    environment.update(request.environment)
    output_path = place.parent / f"{place.name}.output"
    input_path = place.parent / f"{place.name}.input"
    input_path.write_bytes(request.stdin)
    started = clock()
    with output_path.open("wb") as written, input_path.open("rb") as given:
        child = subprocess.Popen(  # noqa: S603 - argv from command_for, never a shell
            command_for(request),
            cwd=place,
            env=environment,
            stdin=given,
            stdout=written,
            stderr=subprocess.STDOUT,
            preexec_fn=limit,
            start_new_session=True,
        )
        timed_out = False
        try:
            code = child.wait(timeout=limits.wall_clock_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait()
    elapsed = clock() - started
    with output_path.open("rb") as read:
        output = read.read(limits.output_bytes + 1)
    output_path.unlink(missing_ok=True)
    input_path.unlink(missing_ok=True)
    truncated = len(output) > limits.output_bytes
    output = output[: limits.output_bytes]
    if timed_out:
        status = AnswerStatus.TIMED_OUT
    elif code == -signal.SIGKILL or any(mark.encode() in output for mark in OUT_OF_MEMORY_MARKS):
        status = AnswerStatus.MEMORY_EXCEEDED
    elif code == 0:
        status = AnswerStatus.COMPLETED
    else:
        status = AnswerStatus.FAILED
    return Ran(
        status=status,
        exit_code=code,
        output=output,
        truncated=truncated,
        elapsed_seconds=round(elapsed, 3),
    )


def answer_of(request: RunRequest, ran: Ran) -> RunAnswer:
    """The contract's answer for a run."""
    return RunAnswer(
        run_id=request.run_id,
        status=ran.status,
        exit_code=ran.exit_code,
        output=ran.output.decode("utf-8", errors="replace"),
        elapsed_seconds=ran.elapsed_seconds,
        truncated=ran.truncated,
    )


# --------------------------------------------------------------------------- the executor
def _write_json(path: Path, body: Mapping[str, Any]) -> None:
    """Write a file whole or not at all: a reader never sees half of one."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(body), encoding="utf-8")
    partial.replace(path)


def heartbeat(jobs: Path, *, now: float) -> None:
    """Write what the executor runs on, and when it said so."""
    runtime, network = isolation()
    _write_json(jobs / HEARTBEAT, {"runtime": runtime, "network": network, "at": now})


def take_one(jobs: Path, work: Path) -> bool:
    """Run the oldest waiting job, if there is one, and say whether there was."""
    waiting = sorted(jobs.glob(f"*{READY}"), key=lambda one: one.stat().st_mtime)
    if not waiting:
        return False
    ready = waiting[0]
    taken = ready.with_name(ready.name.removesuffix(READY) + TAKEN)
    try:
        ready.rename(taken)
    except OSError:
        return True
    try:
        request = RunRequest.from_json(json.loads((taken / "request.json").read_text("utf-8")))
    except (OSError, ValueError, SandboxContractError):
        _write_json(taken / "answer.json", {"refused": RefusalCode.BAD_REQUEST.value})
    else:
        refused = refusal_for(request)
        if refused is not None:
            _write_json(taken / "answer.json", {"refused": refused.value})
        else:
            place = work / request.run_id
            shutil.rmtree(place, ignore_errors=True)
            place.mkdir(parents=True)
            try:
                _write_json(
                    taken / "answer.json", answer_of(request, run_script(request, place)).to_json()
                )
            finally:
                shutil.rmtree(place, ignore_errors=True)
    taken.rename(taken.with_name(taken.name.removesuffix(TAKEN) + DONE))
    return True


def executor(jobs: Path, work: Path, *, stop: threading.Event | None = None) -> None:
    """Take jobs one at a time, and say what this process runs on every few seconds."""
    last = 0.0
    while stop is None or not stop.is_set():
        now = time.time()
        if now - last >= HEARTBEAT_EVERY_SECONDS:
            heartbeat(jobs, now=now)
            last = now
        if not take_one(jobs, work):
            time.sleep(POLL_SECONDS)


def reported(jobs: Path, *, now: float) -> tuple[str, str] | None:
    """The executor's last report of itself, or None when it is missing or stale."""
    try:
        body = json.loads((jobs / HEARTBEAT).read_text(encoding="utf-8"))
        runtime, network, at = str(body["runtime"]), str(body["network"]), float(body["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if now - at > HEARTBEAT_STALE_SECONDS:
        return None
    return runtime, network


# ------------------------------------------------------------------------------ the front
class Front:
    """Checks a request, hands it to the executor and waits for its answer. One run at a time."""

    def __init__(self, jobs: Path, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.jobs = jobs
        self.clock = clock
        self._one = threading.Lock()

    def run(self, raw: bytes) -> tuple[int, dict[str, Any]]:
        """The status and body for one `RUN_PATH` request."""
        if len(raw) > MAX_BODY_BYTES:
            return 413, {"refused": RefusalCode.TOO_LARGE.value}
        try:
            request = RunRequest.from_json(json.loads(raw))
        except (ValueError, SandboxContractError):
            return 400, {"refused": RefusalCode.BAD_REQUEST.value}
        refused = refusal_for(request)
        if refused is not None:
            return (413 if refused is RefusalCode.TOO_LARGE else 422), {"refused": refused.value}
        if not self._one.acquire(blocking=False):
            return 429, {"refused": RefusalCode.BUSY.value}
        try:
            return self._hand_over(request, raw)
        finally:
            self._one.release()

    def _hand_over(self, request: RunRequest, raw: bytes) -> tuple[int, dict[str, Any]]:
        writing = self.jobs / f"{request.run_id}{WRITING}"
        done = self.jobs / f"{request.run_id}{DONE}"
        for stale in (writing, done, self.jobs / f"{request.run_id}{READY}"):
            shutil.rmtree(stale, ignore_errors=True)
        writing.mkdir()
        (writing / "request.json").write_bytes(raw)
        writing.rename(self.jobs / f"{request.run_id}{READY}")
        deadline = self.clock() + clamped(request.limits).wall_clock_seconds + ANSWER_GRACE_SECONDS
        while self.clock() < deadline:
            if done.exists():
                try:
                    body = json.loads((done / "answer.json").read_text(encoding="utf-8"))
                finally:
                    shutil.rmtree(done, ignore_errors=True)
                return (422 if "refused" in body else 200), body
            time.sleep(POLL_SECONDS)
        return 504, {}

    def health(self) -> tuple[int, dict[str, Any]]:
        """The executor's own report, or not healthy when it has not reported recently."""
        seen = reported(self.jobs, now=time.time())
        if seen is None:
            return 503, {}
        return 200, {"runtime": seen[0], "network": seen[1]}


def _handler(front: Front) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: Mapping[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if status == 429:
                self.send_header("Retry-After", "5")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path != HEALTH_PATH:
                self._send(404, {})
                return
            self._send(*front.health())

        def do_POST(self) -> None:
            if self.path != RUN_PATH:
                self._send(404, {})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send(413, {"refused": RefusalCode.TOO_LARGE.value})
                return
            self._send(*front.run(self.rfile.read(length)))

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base's name
            # A request line names a path and nothing a script carries; even so, nothing is logged
            # from a request, so no part of one ever reaches a log.
            return

    return Handler


def main(argv: Sequence[str] | None = None) -> int:
    """`front JOBS`, `executor JOBS WORK` or `alive JOBS`: what the compose file runs.

    The directories are arguments rather than the environment, because a process here reads no
    setting: everything it is told is in its command line, which the compose file states.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "front":
        front = Front(Path(args[1]))
        server = ThreadingHTTPServer(("0.0.0.0", SANDBOX_PORT), _handler(front))  # noqa: S104 - the internal network is the boundary
        server.serve_forever()
        return 0
    if len(args) == 3 and args[0] == "executor":
        executor(Path(args[1]), Path(args[2]))
        return 0
    if len(args) == 2 and args[0] == "alive":
        return 0 if reported(Path(args[1]), now=time.time()) is not None else 1
    print(
        "usage: python -m brain.ops.sandbox_runner front JOBS | executor JOBS WORK | alive JOBS",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
