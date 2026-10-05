"""The script sandbox's contract and the client that asks it, against a recorded sandbox.

Nothing here starts a process or opens a socket: the sandbox is an `httpx.MockTransport` that
answers as the contract says the runner will. What is held is this side of the conversation: the
address only where the sandbox is switched on, the bytes checked before anything is sent, the
request in the agreed shape with the smaller of each limit, and every answer, refusal and silence
read into a run or a sentence.

Task ids: M12.2.9, M12.4.11
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from brain.ops.sandbox import (
    RUN_PATH,
    SANDBOX_MEMORY_MIB,
    SANDBOX_PORT,
    SANDBOX_SERVICE,
    AnswerStatus,
    RefusalCode,
    RunAnswer,
    RunLimits,
    RunRequest,
    SandboxContractError,
    SandboxHealth,
    refusal_of,
    sandbox_address,
)
from brain.ops.sandbox_client import (
    THE_SANDBOX_DID_NOT_ANSWER,
    SandboxRunner,
    status_of,
)
from brain.tools.run_skill import (
    SCRIPT_CHANGED_SINCE_APPROVAL,
    RunStatus,
    SandboxSpec,
    ScriptLeash,
    SkillScriptError,
)
from brain.tools.skills import script_sha256_of

SCRIPT = "scripts/check.py"
BYTES = b"print('renewal due')\n"
DIGEST = "a" * 64


def spec(**changes: Any) -> SandboxSpec:
    fields: dict[str, Any] = {
        "skill": "hosting_expiry",
        "digest": DIGEST,
        "script": SCRIPT,
        "arguments": ("--month", "10"),
        "environment": {"LANG": "C.UTF-8"},
        "leash": ScriptLeash(wall_clock_seconds=20, memory_mib=256, output_bytes=1024),
        "script_sha256": ((SCRIPT, script_sha256_of(BYTES)),),
    }
    fields.update(changes)
    return SandboxSpec(**fields)


class Sandbox:
    """A recorded sandbox: keeps every request and answers with what it was told to."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.seen: list[dict[str, Any]] = []
        self.status = status
        self.body = body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        self.seen.append(sent)
        body = self.body
        if body is None:
            body = RunAnswer(
                run_id=sent["run_id"],
                status=AnswerStatus.COMPLETED,
                exit_code=0,
                output="renewal due\n",
                elapsed_seconds=0.2,
            ).to_json()
        return httpx.Response(self.status, json=body)


def runner(sandbox: Sandbox, files: dict[str, bytes] | None = None) -> SandboxRunner:
    client = httpx.Client(transport=httpx.MockTransport(sandbox))
    stored = {SCRIPT: BYTES} if files is None else files
    return SandboxRunner("http://script-sandbox:3100/", client, lambda digest: stored)


# ------------------------------------------------------------------------ the contract
def test_the_sandbox_has_an_address_only_where_the_install_switched_it_on() -> None:
    """No switch, no address, whatever is configured; switched on, the configured address or the
    product's own service by name. Delete this and an install that never chose a sandbox could be
    sent scripts to run at an address somebody typed."""
    assert sandbox_address("http://elsewhere:1", frozenset()) is None
    assert sandbox_address("", {SANDBOX_SERVICE}) == f"http://{SANDBOX_SERVICE}:{SANDBOX_PORT}"
    assert sandbox_address(" http://own:9 ", {SANDBOX_SERVICE}) == "http://own:9"


def test_a_request_crosses_the_wire_and_back_unchanged() -> None:
    """The runner reads exactly what the client writes, bytes included. Delete this and the two
    sides of the contract can drift with each one's own tests green."""
    sent = RunRequest(
        run_id="r1",
        skill="s",
        digest=DIGEST,
        script=SCRIPT,
        files={SCRIPT: BYTES},
        sha256={SCRIPT: script_sha256_of(BYTES)},
        arguments=("a",),
        environment={"TZ": "UTC"},
        limits=RunLimits(10, 64, 100),
    )
    assert RunRequest.from_json(json.loads(json.dumps(sent.to_json()))) == sent


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"run_id": "r", "status": "completed", "exit_code": 0, "output": "x"},
        {"run_id": "r", "status": "unknown", "exit_code": 0, "output": "", "elapsed_seconds": 1},
        {
            "run_id": "r",
            "status": "completed",
            "exit_code": True,
            "output": "",
            "elapsed_seconds": 1,
        },
        {"run_id": "r", "status": "completed", "exit_code": 0, "output": "", "elapsed_seconds": -1},
    ],
)
def test_an_answer_in_any_other_shape_is_not_read(body: object) -> None:
    """Not an object, no elapsed time, a status the contract lacks, a boolean exit code, a
    negative time: each is refused rather than read. Delete this and a broken runner's body
    becomes a run somebody believes."""
    with pytest.raises(SandboxContractError):
        RunAnswer.from_json(body)


def test_a_refusal_is_a_code_and_nothing_else() -> None:
    """`{"refused": code}` with a known code is read; a code the contract lacks, or anything beside
    it, is not. Delete this and a refusal can carry an echo of the request into a log."""
    assert refusal_of({"refused": "digest_mismatch"}) is RefusalCode.DIGEST_MISMATCH
    for body in ({"refused": "nope"}, {"refused": "busy", "detail": "x"}, ["busy"]):
        with pytest.raises(SandboxContractError):
            refusal_of(body)


def test_a_sandbox_is_isolated_only_under_gvisor_with_no_network() -> None:
    """The health answer the install check reads. Delete this and a sandbox under the host's own
    kernel, or with a network, passes as isolated."""
    assert SandboxHealth.from_json({"runtime": "runsc", "network": "none"}).is_isolated
    assert not SandboxHealth.from_json({"runtime": "runc", "network": "none"}).is_isolated
    assert not SandboxHealth.from_json({"runtime": "runsc", "network": "bridge"}).is_isolated


# ------------------------------------------------------------------------ the client
def test_a_run_sends_the_approved_bytes_and_the_smaller_limits_and_reads_the_answer() -> None:
    """The positive run: the request carries the script's bytes and the approved hash, the argv,
    the environment and the smaller of each leash and sandbox ceiling, and the answer comes back
    as this product's outcome. Delete this and a runner that sends nothing or reads nothing passes
    every refusal test below."""
    sandbox = Sandbox()
    outcome = runner(sandbox).run(spec(leash=ScriptLeash(memory_mib=SANDBOX_MEMORY_MIB)))
    (sent,) = sandbox.seen
    assert base64.b64decode(sent["files"][SCRIPT]) == BYTES
    assert sent["sha256"] == {SCRIPT: script_sha256_of(BYTES)}
    assert sent["arguments"] == ["--month", "10"]
    assert sent["limits"]["memory_mib"] == SANDBOX_MEMORY_MIB
    assert (outcome.status, outcome.exit_code, outcome.output) == (
        RunStatus.COMPLETED,
        0,
        "renewal due\n",
    )


def test_bytes_changed_after_approval_are_refused_before_the_sandbox_is_asked() -> None:
    """M12.4.11's "refused before it runs": a stored script whose bytes no longer hash to the
    approved value is refused and the sandbox sees no request. Delete this and an edited script
    reaches the sandbox, which is the second check standing alone."""
    sandbox = Sandbox()
    with pytest.raises(SkillScriptError) as refused:
        runner(sandbox, files={SCRIPT: BYTES + b"#"}).run(spec())
    assert str(refused.value) == SCRIPT_CHANGED_SINCE_APPROVAL
    assert sandbox.seen == []


def test_a_refusal_says_its_code_and_a_silence_says_the_sandbox_did_not_answer() -> None:
    """A 4xx is the contract's code in a sentence; a 5xx, an unreadable body and an answer for
    another run are one sentence, and nothing is retried. Delete this and a refusal or an outage
    is read as a run, or retried into running a script twice."""
    refused = Sandbox(status=409, body={"refused": "digest_mismatch"})
    with pytest.raises(SkillScriptError, match="digest_mismatch"):
        runner(refused).run(spec())
    for broken in (
        Sandbox(status=500, body={"error": "x"}),
        Sandbox(status=200, body={"nonsense": True}),
        Sandbox(
            status=200,
            body={
                "run_id": "another",
                "status": "completed",
                "exit_code": 0,
                "output": "",
                "elapsed_seconds": 0.1,
            },
        ),
    ):
        with pytest.raises(SkillScriptError) as silent:
            runner(broken).run(spec())
        assert str(silent.value) == THE_SANDBOX_DID_NOT_ANSWER
        assert len(broken.seen) == 1


def test_a_script_no_interpreter_runs_is_refused_before_anything_is_sent() -> None:
    """Only the extensions the sandbox has an interpreter for are sent. Delete this and a script
    the sandbox will refuse costs a round trip and a slot."""
    sandbox = Sandbox()
    with pytest.raises(SkillScriptError, match="no other kind"):
        runner(sandbox).run(spec(script="scripts/check.rb"))
    assert sandbox.seen == []


def test_a_memory_ceiling_is_a_kill_and_a_non_zero_exit_is_a_failure() -> None:
    """The sandbox's statuses in this product's words. Delete this and a script stopped for its
    memory reads as one that failed on its own, or a failing script as one that completed."""

    def answered(status: AnswerStatus, code: int) -> RunStatus:
        return status_of(RunAnswer("r", status, code, "", 0.1))

    assert answered(AnswerStatus.COMPLETED, 0) is RunStatus.COMPLETED
    assert answered(AnswerStatus.COMPLETED, 2) is RunStatus.FAILED
    assert answered(AnswerStatus.TIMED_OUT, -9) is RunStatus.TIMED_OUT
    assert answered(AnswerStatus.MEMORY_EXCEEDED, -9) is RunStatus.KILLED
    assert answered(AnswerStatus.FAILED, 1) is RunStatus.FAILED
    assert RUN_PATH == "/run"


def test_the_kind_the_reach_and_standard_input_cross_the_wire_and_an_unknown_kind_is_refused() -> (
    None
):
    """The three additions for connector code: a run names its kind, carries its reach (empty for
    a connector, at the service's reach), and hands standard input as base64. A request naming no
    kind or an unknown one is not read. Delete this and connector code can be sent as a skill, or
    its input dropped on the way."""
    from brain.ops.sandbox import A_CONNECTOR_RUN_IS_AT_THE_SERVICE_S_REACH, RunKind

    sent = RunRequest(
        run_id="r1",
        skill="xero_adapter",
        digest=DIGEST,
        script="adapter.py",
        files={"adapter.py": BYTES},
        sha256={"adapter.py": script_sha256_of(BYTES)},
        stdin=b'{"rows": []}',
        kind=RunKind.CONNECTOR,
    )
    wire = json.loads(json.dumps(sent.to_json()))
    assert wire["kind"] == "connector" and wire["reach"] == ""
    assert RunRequest.from_json(wire) == sent
    assert "stdin" not in RunRequest(**{**sent.__dict__, "stdin": b""}).to_json()
    for broken in ({**wire, "kind": "script"}, {k: v for k, v in wire.items() if k != "kind"}):
        with pytest.raises(SandboxContractError):
            RunRequest.from_json(broken)
    assert "service's reach" in A_CONNECTOR_RUN_IS_AT_THE_SERVICE_S_REACH


def test_a_request_over_either_bound_is_refused_before_it_is_sent_and_never_cut() -> None:
    """Files or standard input over their bound make `too_large` true, and the client refuses it
    without asking the sandbox; at the bound it is sent whole. Delete this and an oversized input
    is cut, and a connector reads half an answer as all of it."""
    from brain.ops.sandbox import SANDBOX_FILES_BYTES, SANDBOX_STDIN_BYTES

    def asking(stdin: bytes, files: dict[str, bytes]) -> RunRequest:
        return RunRequest(
            run_id="r", skill="s", digest=DIGEST, script=SCRIPT, files=files, sha256={}, stdin=stdin
        )

    assert not asking(b"x" * SANDBOX_STDIN_BYTES, {SCRIPT: BYTES}).too_large()
    assert asking(b"x" * (SANDBOX_STDIN_BYTES + 1), {SCRIPT: BYTES}).too_large()
    assert asking(b"", {SCRIPT: b"x" * (SANDBOX_FILES_BYTES + 1)}).too_large()
    sandbox = Sandbox()
    huge = {f"scripts/{i}.py": b"x" * (64 * 1024) for i in range(17)}
    files = {SCRIPT: BYTES, **huge}
    approved = tuple(sorted((path, script_sha256_of(content)) for path, content in files.items()))
    with pytest.raises(SkillScriptError, match="too_large"):
        runner(sandbox, files=files).run(spec(script_sha256=approved))
    assert sandbox.seen == []
