"""The runner a skill's script is handed to: bytes checked against the approval, then the sandbox.

`brain.tools.run_skill.SkillScriptTool` requires a `ScriptRunner` and has no default, because six of
the ten things a sandbox must deny are a container's to enforce. This is the runner, and it is a
client: the container is the script sandbox an install switches on (`brain.ops.sandbox`), and this
module only asks it, over the contract that module holds.

**Nothing is sent until the bytes are the approved ones.** The scripts are read by the skill's
digest, every file's sha256 is recomputed and compared with the hashes the approval covers
(`run_skill.verify_script_bytes`), and only then is the run posted. A script edited in the store
after its approval is refused here, before the sandbox is asked anything, which is M12.4.11's
"refused before it runs". The sandbox checks again on its side.

**What comes back is a report, and the leash is still applied to it.** The answer is read through
`brain.ops.sandbox.RunAnswer`, which refuses any other shape, and then
`run_skill.accept_outcome` measures the output and the time against the spec's leash whatever the
sandbox said, for `run_skill.THE_CEILING_APPLIES_TO_WHAT_CAME_BACK`.

**A refusal or a silence is a sentence a model may read and nothing more.** A 4xx is one of the
contract's codes; a 5xx, an unreadable body or no answer is "the sandbox did not answer", and
nothing is retried, because a script that did something before the connection dropped would be run
twice.

Task ids: M12.2.9, M12.4.11
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Final

import httpx
import structlog

from brain.ops.sandbox import (
    INTERPRETERS,
    RUN_PATH,
    SANDBOX_MEMORY_MIB,
    SANDBOX_OUTPUT_BYTES,
    SANDBOX_WALL_CLOCK_SECONDS,
    AnswerStatus,
    RefusalCode,
    RunAnswer,
    RunLimits,
    RunRequest,
    SandboxContractError,
    refusal_of,
)
from brain.tools.run_skill import (
    RunOutcome,
    RunStatus,
    SandboxSpec,
    SkillScriptError,
    verify_script_bytes,
)

log = structlog.get_logger(__name__)

#: Said when the sandbox gave no answer this side can read.
THE_SANDBOX_DID_NOT_ANSWER: Final = "the script sandbox did not answer, so the script was not run"

#: Said for a refusal, with its code, which carries nothing from the request.
THE_SANDBOX_REFUSED: Final = "the script sandbox refused to run it ({code})"

#: Said for a script whose extension the sandbox has no interpreter for, before anything is sent.
NO_INTERPRETER: Final = "the sandbox runs scripts ending in {suffixes} and no other kind"

#: Slack on the HTTP timeout past the script's own deadline, for the answer to travel back.
ANSWER_SLACK_SECONDS: Final = 10.0

#: Reads a stored skill's scripts by its digest: path to bytes. `StoredSkills.script_bytes`.
ScriptBytes = Callable[[str], Mapping[str, bytes]]


def status_of(answer: RunAnswer) -> RunStatus:
    """The sandbox's status in this product's words. A memory ceiling is a kill from outside."""
    if answer.status is AnswerStatus.COMPLETED:
        return RunStatus.COMPLETED if answer.exit_code == 0 else RunStatus.FAILED
    if answer.status is AnswerStatus.TIMED_OUT:
        return RunStatus.TIMED_OUT
    if answer.status is AnswerStatus.MEMORY_EXCEEDED:
        return RunStatus.KILLED
    return RunStatus.FAILED


class SandboxRunner:
    """`brain.tools.run_skill.ScriptRunner` over the install's script sandbox."""

    def __init__(self, address: str, client: httpx.Client, scripts: ScriptBytes) -> None:
        self._url = f"{address.rstrip('/')}{RUN_PATH}"
        self._client = client
        self._scripts = scripts

    def run(self, spec: SandboxSpec) -> RunOutcome:
        """Check the bytes, ask the sandbox once, and read its answer. See the module docstring."""
        suffix = "." + spec.script.rsplit(".", 1)[-1] if "." in spec.script else ""
        if suffix not in INTERPRETERS:
            raise SkillScriptError(NO_INTERPRETER.format(suffixes=sorted(INTERPRETERS)))
        files = dict(self._scripts(spec.digest))
        verify_script_bytes(spec, files)
        request = RunRequest(
            run_id=str(uuid.uuid4()),
            skill=spec.skill,
            digest=spec.digest,
            script=spec.script,
            files=files,
            sha256=dict(spec.script_sha256),
            arguments=spec.arguments,
            environment=dict(spec.environment),
            reach=spec.reach_hash,
            limits=RunLimits(
                wall_clock_seconds=min(spec.leash.wall_clock_seconds, SANDBOX_WALL_CLOCK_SECONDS),
                memory_mib=min(spec.leash.memory_mib, SANDBOX_MEMORY_MIB),
                output_bytes=min(spec.leash.output_bytes, SANDBOX_OUTPUT_BYTES),
            ),
        )
        if request.too_large():
            raise SkillScriptError(THE_SANDBOX_REFUSED.format(code=RefusalCode.TOO_LARGE.value))
        try:
            response = self._client.post(
                self._url,
                json=request.to_json(),
                timeout=request.limits.wall_clock_seconds + ANSWER_SLACK_SECONDS,
            )
        except httpx.HTTPError as exc:
            log.warning("sandbox.unanswered", skill=spec.skill, error=type(exc).__name__)
            raise SkillScriptError(THE_SANDBOX_DID_NOT_ANSWER) from None
        refused = response.is_client_error
        try:
            if refused:
                code = refusal_of(response.json())
            elif response.status_code == httpx.codes.OK:
                answer = RunAnswer.from_json(response.json())
            else:
                raise SandboxContractError("status")
        except (SandboxContractError, ValueError) as exc:
            log.warning("sandbox.unreadable", skill=spec.skill, error=type(exc).__name__)
            raise SkillScriptError(THE_SANDBOX_DID_NOT_ANSWER) from None
        if refused:
            log.info("sandbox.refused", skill=spec.skill, code=code.value)
            raise SkillScriptError(THE_SANDBOX_REFUSED.format(code=code.value))
        if answer.run_id != request.run_id:
            log.warning("sandbox.other_run", skill=spec.skill)
            raise SkillScriptError(THE_SANDBOX_DID_NOT_ANSWER)
        return RunOutcome(
            run_id=answer.run_id,
            status=status_of(answer),
            exit_code=answer.exit_code,
            output=answer.output,
            elapsed_seconds=answer.elapsed_seconds,
        )


__all__ = [
    "NO_INTERPRETER",
    "THE_SANDBOX_DID_NOT_ANSWER",
    "THE_SANDBOX_REFUSED",
    "RefusalCode",
    "SandboxRunner",
    "status_of",
]
