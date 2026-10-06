"""The script sandbox's front and executor, run in this process over real directories.

The isolation itself, gVisor and a container with no network, is the server's and is proved by the
install check (`brain.ops.acceptance_checks_services`). What is proved here is everything the two
processes decide: what they refuse, the limits they set on a script, what they say about the kernel
they read, and the hand-over between them through the job directory.

A development machine that is not Linux refuses an address-space limit, so the tests that run a
script hand `run_script` a limiter without one, and the memory limit is tested on Linux alone, which
is what CI runs.

Task ids: M12.4.5, M12.2.9, M11.1.5
"""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from brain.ops import sandbox_runner as runner
from brain.ops.sandbox import (
    GVISOR_RUNTIME,
    NO_NETWORK,
    SANDBOX_FILES_BYTES,
    SANDBOX_MEMORY_MIB,
    SANDBOX_OUTPUT_BYTES,
    SANDBOX_WALL_CLOCK_SECONDS,
    AnswerStatus,
    RefusalCode,
    RunAnswer,
    RunLimits,
    RunRequest,
)

LINUX = sys.platform.startswith("linux")


def without_address_space(limits: RunLimits) -> Callable[[], None]:
    """`_limit_child` less the one limit a non-Linux machine refuses."""

    def apply() -> None:
        cpu = limits.wall_clock_seconds + 1
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (runner.WRITE_LIMIT_BYTES,) * 2)

    return apply


def a_request(
    code: str = "print('hello')",
    *,
    name: str = "job.py",
    wall: int = 5,
    memory: int = 128,
    output: int = 4096,
    arguments: tuple[str, ...] = (),
    environment: dict[str, str] | None = None,
    run_id: str = "run-1",
) -> RunRequest:
    body = code.encode()
    return RunRequest(
        run_id=run_id,
        skill="a-skill",
        digest="d",
        script=name,
        files={name: body},
        sha256={name: hashlib.sha256(body).hexdigest()},
        arguments=arguments,
        environment=environment or {},
        limits=RunLimits(wall_clock_seconds=wall, memory_mib=memory, output_bytes=output),
    )


def ran(request: RunRequest, tmp_path: Path) -> runner.Ran:
    limiter = None if LINUX else without_address_space
    return runner.run_script(request, tmp_path / "place", limiter=limiter)


# ------------------------------------------------------------------------ what is refused
def test_a_request_the_contract_allows_is_not_refused() -> None:
    """The positive case for every refusal below. Delete this and a check that refuses everything
    passes them all."""
    assert runner.refusal_for(a_request()) is None
    assert runner.refusal_for(a_request("echo hi", name="tools/run.sh")) is None


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"files": {"/etc/passwd": b"x"}, "script": "/etc/passwd"}, RefusalCode.BAD_REQUEST),
        ({"files": {"../out.py": b"x"}, "script": "../out.py"}, RefusalCode.BAD_REQUEST),
        ({"run_id": "a/b"}, RefusalCode.BAD_REQUEST),
        ({"run_id": ""}, RefusalCode.BAD_REQUEST),
        ({"environment": {"AWS_SECRET": "x"}}, RefusalCode.BAD_REQUEST),
        ({"script": "other.py"}, RefusalCode.SCRIPT_NOT_DECLARED),
        ({"files": {"job.rb": b"x"}, "script": "job.rb"}, RefusalCode.INTERPRETER_NOT_ALLOWED),
        ({"sha256": {"job.py": "0" * 64}}, RefusalCode.DIGEST_MISMATCH),
        ({"sha256": {}}, RefusalCode.DIGEST_MISMATCH),
    ],
    ids=[
        "absolute path",
        "climbing path",
        "run id names a directory",
        "empty run id",
        "environment outside the allowlist",
        "script not among the files",
        "interpreter not allowed",
        "bytes do not hash to what was sent",
        "a file with no hash",
    ],
)
def test_each_way_a_request_breaks_the_contract_is_refused_with_its_own_code(
    change: dict[str, object], code: RefusalCode
) -> None:
    """Made by the front and again by the executor. Delete this and a script whose bytes changed
    after approval runs, or one writes outside its directory."""
    import dataclasses

    request = a_request()
    files = change.get("files")
    if isinstance(files, dict) and "sha256" not in change:
        change = {
            **change,
            "sha256": {path: hashlib.sha256(body).hexdigest() for path, body in files.items()},
        }
    assert runner.refusal_for(dataclasses.replace(request, **change)) is code  # type: ignore[arg-type]


def test_files_past_the_ceiling_are_too_large_and_at_it_are_not() -> None:
    """At the boundary, both sides. Delete this and the ceiling can move by a byte either way."""
    at = b"x" * SANDBOX_FILES_BYTES
    over = at + b"x"
    for body, refused in ((at, None), (over, RefusalCode.TOO_LARGE)):
        request = RunRequest(
            run_id="r",
            skill="s",
            digest="d",
            script="job.py",
            files={"job.py": body},
            sha256={"job.py": hashlib.sha256(body).hexdigest()},
        )
        assert runner.refusal_for(request) is refused


def test_a_run_gets_the_smaller_of_each_limit_asked_and_the_ceiling() -> None:
    """The sandbox's ceilings win, and a smaller ask is kept. Delete this and a client asking for
    an hour gets an hour."""
    over = RunLimits(10_000, 10_000, 10_000_000)
    under = RunLimits(1, 1, 1)
    assert runner.clamped(over) == RunLimits(
        SANDBOX_WALL_CLOCK_SECONDS, SANDBOX_MEMORY_MIB, SANDBOX_OUTPUT_BYTES
    )
    assert runner.clamped(under) == under


# --------------------------------------------------------------------- running a script
def test_a_script_runs_in_its_own_directory_and_its_output_comes_back(tmp_path: Path) -> None:
    """Delete this and a runner that runs nothing passes every limit test below."""
    done = ran(a_request("import os\nprint('hello', os.getcwd().endswith('place'))"), tmp_path)
    assert done.status is AnswerStatus.COMPLETED
    assert done.exit_code == 0
    assert done.output == b"hello True\n"
    assert not done.truncated


def test_arguments_are_passed_as_they_are_and_never_to_a_shell(tmp_path: Path) -> None:
    """argv, never a command line. Delete this and an argument holding `$(...)` runs it."""
    tricky = "$(echo pwned); rm -rf /"
    done = ran(a_request('printf "%s" "$1"', name="job.sh", arguments=(tricky,)), tmp_path)
    assert done.output == tricky.encode()


def test_a_script_is_given_only_the_allowed_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing of the executor's own environment reaches a script. Delete this and a variable the
    executor happened to hold is one print statement away from a stranger's output."""
    monkeypatch.setenv("SOMETHING_PRIVATE", "should-not-be-seen")
    code = "import json, os\nprint(json.dumps(sorted(os.environ)))"
    done = ran(a_request(code, environment={"LANG": "C.UTF-8"}), tmp_path)
    assert done.status is AnswerStatus.COMPLETED, done.output
    named = set(json.loads(done.output.decode()))
    # What an interpreter adds to its own environment as it starts, on Linux and on macOS.
    its_own = {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
    assert "SOMETHING_PRIVATE" not in named
    assert named - its_own <= runner.ALLOWED_ENVIRONMENT
    assert "LANG" in named


def test_a_script_past_its_time_is_stopped_and_said_to_have_timed_out(tmp_path: Path) -> None:
    """Delete this and a script that sleeps holds the one executor for ever."""
    started = time.monotonic()
    done = ran(a_request("import time\ntime.sleep(30)", wall=1), tmp_path)
    assert done.status is AnswerStatus.TIMED_OUT
    assert time.monotonic() - started < 10


def test_a_script_that_exits_badly_has_failed_and_says_with_what(tmp_path: Path) -> None:
    """Delete this and a failed script reads as one that completed."""
    done = ran(a_request("import sys\nsys.exit(3)"), tmp_path)
    assert done.status is AnswerStatus.FAILED
    assert done.exit_code == 3


def test_output_past_its_limit_is_cut_at_the_limit_and_says_so(tmp_path: Path) -> None:
    """Delete this and a script printing a gigabyte sends a gigabyte back to a model."""
    done = ran(a_request("print('x' * 10000)", output=100), tmp_path)
    assert done.output == b"x" * 100
    assert done.truncated


@pytest.mark.skipif(not LINUX, reason="only Linux enforces an address-space limit")
def test_a_script_past_its_memory_is_stopped_and_said_to_have_run_out(tmp_path: Path) -> None:
    """The limit is the kernel's, on the script's own process. Delete this and a script that
    allocates without bound takes the executor's memory, which is the server's."""
    done = ran(
        a_request("block = bytearray(512 * 1024 * 1024)\nprint(len(block))", memory=64), tmp_path
    )
    assert done.status is AnswerStatus.MEMORY_EXCEEDED, done.output


# ------------------------------------------------------------------- what it runs on
@pytest.mark.parametrize(
    ("version", "log", "interfaces", "expected"),
    [
        (
            "Linux version 4.4.0 #1 SMP Sun Jan 10 15:06:54 PST 2016",
            "",
            ["lo"],
            (GVISOR_RUNTIME, NO_NETWORK),
        ),
        (
            "Linux version 6.8.0",
            "[    0.000000] Starting gVisor...",
            ["lo"],
            (GVISOR_RUNTIME, NO_NETWORK),
        ),
        ("Linux version 6.8.0", "", ["lo"], ("other", NO_NETWORK)),
        (
            "Linux version 6.8.0",
            "[ 0.0] Starting gVisor...",
            ["lo", "eth0"],
            (GVISOR_RUNTIME, "present"),
        ),
    ],
    ids=["gVisor by its version", "gVisor by its log", "another kernel", "an interface"],
)
def test_what_the_sandbox_says_it_runs_on_is_what_its_kernel_says(
    version: str, log: str, interfaces: list[str], expected: tuple[str, str]
) -> None:
    """Read, never declared. Delete this and a sandbox started under docker's own runtime, or with
    a network, reports itself isolated."""
    assert (
        runner.isolation(
            version=lambda: version, kernel_log=lambda: log, interfaces=lambda: interfaces
        )
        == expected
    )


# ------------------------------------------------------------------- the two processes
@pytest.fixture
def jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path]]:
    """A job directory and a work directory, with the executor's limits the machine accepts."""
    if not LINUX:
        monkeypatch.setattr(runner, "_limit_child", without_address_space)
    monkeypatch.setattr(runner, "isolation", lambda: (GVISOR_RUNTIME, NO_NETWORK))
    shared, work = tmp_path / "jobs", tmp_path / "work"
    shared.mkdir()
    work.mkdir()
    yield shared, work


def test_the_executor_answers_a_job_and_marks_it_done(jobs: tuple[Path, Path]) -> None:
    """Delete this and a job the front hands over is never answered."""
    shared, work = jobs
    ready = shared / f"run-1{runner.READY}"
    ready.mkdir()
    (ready / "request.json").write_text(json.dumps(a_request().to_json()), encoding="utf-8")

    assert runner.take_one(shared, work) is True
    answer = json.loads((shared / f"run-1{runner.DONE}" / "answer.json").read_text("utf-8"))
    assert RunAnswer.from_json(answer).status is AnswerStatus.COMPLETED
    assert runner.take_one(shared, work) is False
    assert list(work.iterdir()) == []


@pytest.mark.parametrize(
    ("body", "refused"),
    [
        ("not json", RefusalCode.BAD_REQUEST),
        ("tampered", RefusalCode.DIGEST_MISMATCH),
    ],
)
def test_the_executor_checks_a_job_again_whoever_wrote_it(
    jobs: tuple[Path, Path], body: str, refused: RefusalCode
) -> None:
    """A job written by something other than the front is refused by the executor's own check.
    Delete this and anything that can write to the job volume runs what it likes."""
    shared, work = jobs
    ready = shared / f"run-1{runner.READY}"
    ready.mkdir()
    if body == "tampered":
        sent = a_request().to_json()
        sent["sha256"] = {"job.py": "0" * 64}
        text = json.dumps(sent)
    else:
        text = body
    (ready / "request.json").write_text(text, encoding="utf-8")

    runner.take_one(shared, work)
    answer = json.loads((shared / f"run-1{runner.DONE}" / "answer.json").read_text("utf-8"))
    assert answer == {"refused": refused.value}


def test_health_is_the_executor_s_own_recent_report_and_nothing_else(
    jobs: tuple[Path, Path],
) -> None:
    """No report, or a stale one, is not healthy. Delete this and a front whose executor died
    reports a sandbox that can run nothing."""
    shared, _ = jobs
    front = runner.Front(shared)
    assert front.health() == (503, {})
    runner.heartbeat(shared, now=time.time())
    assert front.health() == (200, {"runtime": GVISOR_RUNTIME, "network": NO_NETWORK})
    runner.heartbeat(shared, now=time.time() - runner.HEARTBEAT_STALE_SECONDS - 1)
    assert front.health() == (503, {})


def test_the_front_hands_a_run_to_the_executor_and_returns_its_answer(
    jobs: tuple[Path, Path],
) -> None:
    """End to end across the job directory. Delete this and the two halves can each pass alone and
    never meet."""
    shared, work = jobs
    stop = threading.Event()
    worker = threading.Thread(target=runner.executor, args=(shared, work), kwargs={"stop": stop})
    worker.start()
    try:
        status, body = runner.Front(shared).run(json.dumps(a_request().to_json()).encode())
    finally:
        stop.set()
        worker.join(timeout=10)
    assert status == 200
    answer = RunAnswer.from_json(body)
    assert (answer.run_id, answer.status, answer.output) == (
        "run-1",
        AnswerStatus.COMPLETED,
        "hello\n",
    )


@pytest.mark.parametrize(
    ("raw", "status", "refused"),
    [
        (b"not json", 400, RefusalCode.BAD_REQUEST),
        (b"x" * (runner.MAX_BODY_BYTES + 1), 413, RefusalCode.TOO_LARGE),
    ],
)
def test_the_front_refuses_a_body_it_cannot_read_with_a_code_and_nothing_else(
    jobs: tuple[Path, Path], raw: bytes, status: int, refused: RefusalCode
) -> None:
    """The body of a refusal is exactly `{"refused": code}`. Delete this and a refusal can echo
    the request into a log."""
    shared, _ = jobs
    assert runner.Front(shared).run(raw) == (status, {"refused": refused.value})


def test_a_contract_refusal_is_made_before_anything_is_handed_over(jobs: tuple[Path, Path]) -> None:
    """Delete this and the front writes a job the executor will only refuse."""
    shared, _ = jobs
    sent = a_request().to_json()
    sent["script"] = "other.py"
    status, body = runner.Front(shared).run(json.dumps(sent).encode())
    assert (status, body) == (422, {"refused": RefusalCode.SCRIPT_NOT_DECLARED.value})
    assert list(shared.iterdir()) == []


def test_a_second_run_while_one_is_running_is_told_the_sandbox_is_busy(
    jobs: tuple[Path, Path],
) -> None:
    """One run at a time, and the second is told so rather than queued. Delete this and two runs
    share an executor sized for one."""
    shared, _ = jobs
    front = runner.Front(shared)
    assert front._one.acquire()
    try:
        assert front.run(json.dumps(a_request().to_json()).encode()) == (
            429,
            {"refused": RefusalCode.BUSY.value},
        )
    finally:
        front._one.release()


def test_a_run_nobody_answers_is_said_to_have_had_no_answer(
    jobs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No executor, no answer: a 5xx, which the client reads as "the sandbox did not answer".
    Delete this and a front with no executor waits for ever."""
    shared, _ = jobs
    monkeypatch.setattr(runner, "ANSWER_GRACE_SECONDS", 0.2)
    assert runner.Front(shared).run(json.dumps(a_request(wall=1).to_json()).encode()) == (504, {})


def test_the_command_line_names_the_directories_and_nothing_else_is_read() -> None:
    """Delete this and the processes start reading settings from an environment the compose file
    does not state."""
    assert runner.main([]) == 64
    assert runner.main(["front"]) == 64
    assert runner.main(["alive", "/nonexistent-jobs"]) == 1


# ------------------------------------------------------------------------ standard input
def test_standard_input_reaches_the_script_whole(tmp_path: Path) -> None:
    """The bounded input channel, past the argument limit a model's answer would otherwise meet.
    Delete this and the channel is declared and never delivered."""
    import dataclasses

    given = ("line " * 4000).encode()
    request = dataclasses.replace(
        a_request("import sys\nprint(len(sys.stdin.buffer.read()))"), stdin=given
    )
    done = ran(request, tmp_path)
    assert done.status is AnswerStatus.COMPLETED, done.output
    assert done.output == f"{len(given)}\n".encode()


def test_standard_input_past_its_bound_is_refused_whole_and_never_cut() -> None:
    """At the boundary, both sides, by the contract's own test of both bounds. Delete this and an
    over-long input is cut, and a script reads half an answer as a whole one."""
    import dataclasses

    from brain.ops.sandbox import SANDBOX_STDIN_BYTES

    at = dataclasses.replace(a_request(), stdin=b"x" * SANDBOX_STDIN_BYTES)
    over = dataclasses.replace(a_request(), stdin=b"x" * (SANDBOX_STDIN_BYTES + 1))
    assert runner.refusal_for(at) is None
    assert runner.refusal_for(over) is RefusalCode.TOO_LARGE


def test_an_unknown_run_kind_is_a_request_the_front_cannot_read(jobs: tuple[Path, Path]) -> None:
    """Connector code is named as itself, and a kind nobody declared is not run as either. Delete
    this and a third kind arrives unexamined."""
    shared, _ = jobs
    sent = a_request().to_json()
    sent["kind"] = "plugin"
    assert runner.Front(shared).run(json.dumps(sent).encode()) == (
        400,
        {"refused": RefusalCode.BAD_REQUEST.value},
    )
