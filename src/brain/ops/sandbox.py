"""The script sandbox's contract: where it answers, what it is asked, and what it may say back.

One sandbox serves three things: a skill's scripts (M12.2.9), the code sandbox (M12.4.5) and the
custom-code transport (M11.1.5). It is an optional service an install switches on
(`INSTALL_SERVICES`), run under gVisor on a network of its own, each script in an empty network
namespace. Two modules talk across it: `brain.ops.sandbox_client` asks, and
`brain.ops.sandbox_runner` answers inside the service. **This module is the agreement between
them and does no I/O**, so neither side can drift from the other without a test failing, and the
runner never imports a client.

**The address has one reader, and no switch means no sandbox.** `sandbox_address` returns None
unless the install switched the service on, and then the configured address or the product's own
service by name. No profile deploys it, so a profile is not asked. A caller with None stores no
script and runs none: see `brain.console.skill_library.THIS_INSTALL_RUNS_NO_SANDBOX`.

**Both sides check the bytes.** The client recomputes each script's sha256 against the approval
before it sends (`brain.tools.run_skill.verify_script_bytes`), and the runner recomputes it again
before it executes, refusing with `digest_mismatch`. Rejected: either check alone. The client's
proves the bytes are the approved ones; the runner's proves they arrived intact, and a runner
that trusted a hash it was sent would be checking the request against itself.

**The sandbox's own ceilings win.** It applies the smaller of what it is asked and its own
ceiling for each limit, so a client asking for more is given less rather than refused, and the
client applies its own leash to what comes back whatever the sandbox says. The memory ceiling is
256 MiB, which is what fits beside the analyser and the trace store on a small server; it is a
named constant because the owner may move it.

**A refusal is a code and nothing else.** The body of a 4xx is `{"refused": code}` with no
sentence and no echo of the request, so a refusal can never carry a script's output, a path or an
argument into a log. A 5xx or no answer is "the sandbox did not answer", and nothing is retried.

Task ids: M12.2.9, M12.4.11
"""

from __future__ import annotations

import base64
import enum
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

#: The service's name in the overlay and its port, which the deploy side's compose file is held
#: to by a test.
SANDBOX_SERVICE: Final = "script-sandbox"
SANDBOX_PORT: Final = 3100

#: The `brain.settings.Settings` field an install sets to send runs somewhere other than the
#: product's own service.
SANDBOX_ADDRESS_SETTING: Final = "sandbox_url"

#: The paths the runner answers on.
RUN_PATH: Final = "/run"
HEALTH_PATH: Final = "/health"

#: The sandbox's own ceilings. It applies the smaller of these and what it is asked.
SANDBOX_WALL_CLOCK_SECONDS: Final = 60
SANDBOX_MEMORY_MIB: Final = 256
SANDBOX_OUTPUT_BYTES: Final = 64 * 1024
#: The most bytes every file of one run may total, decoded.
SANDBOX_FILES_BYTES: Final = 1024 * 1024

#: The interpreter the sandbox runs a script with, chosen by its extension and by nothing else.
INTERPRETERS: Final[Mapping[str, str]] = {".py": "python3", ".sh": "/bin/sh"}

#: The runtime a healthy sandbox reports, read from its own kernel, and the network it has.
GVISOR_RUNTIME: Final = "runsc"
NO_NETWORK: Final = "none"


def sandbox_address(configured: str, switched: Collection[str]) -> str | None:
    """Where this install runs scripts, or None when it has not switched the sandbox on.

    `switched` is `brain.ops.overlays.components_switched_on(switched_on_here())`. The configured
    value wins when there is one; otherwise the product's own service by name, which resolves on
    the sandbox's network and nowhere else.
    """
    if SANDBOX_SERVICE not in switched:
        return None
    return configured.strip() or f"http://{SANDBOX_SERVICE}:{SANDBOX_PORT}"


class RefusalCode(enum.StrEnum):
    """Why the sandbox did not run something. Closed, and the whole of a refusal's body."""

    #: A file's bytes do not hash to the sha256 it was sent with.
    DIGEST_MISMATCH = "digest_mismatch"
    #: The script to run is not among the files sent.
    SCRIPT_NOT_DECLARED = "script_not_declared"
    #: The script's extension names no interpreter in `INTERPRETERS`.
    INTERPRETER_NOT_ALLOWED = "interpreter_not_allowed"
    #: The files total more than `SANDBOX_FILES_BYTES`.
    TOO_LARGE = "too_large"
    #: Every slot is in use; a 429 with Retry-After.
    BUSY = "busy"
    #: A body that does not parse, or a path that is absolute or climbs out.
    BAD_REQUEST = "bad_request"


class AnswerStatus(enum.StrEnum):
    """How a run the sandbox accepted ended, in the sandbox's words."""

    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    MEMORY_EXCEEDED = "memory_exceeded"
    FAILED = "failed"


class SandboxContractError(ValueError):
    """A body on either side that is not the shape this module agrees, so none of it is read."""


@dataclass(frozen=True)
class RunLimits:
    wall_clock_seconds: int
    memory_mib: int
    output_bytes: int


@dataclass(frozen=True)
class RunRequest:
    """What the client sends to `RUN_PATH`. Files travel as bytes here and base64 on the wire."""

    run_id: str
    skill: str
    digest: str
    script: str
    files: Mapping[str, bytes]
    sha256: Mapping[str, str]
    arguments: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    limits: RunLimits = field(
        default_factory=lambda: RunLimits(
            SANDBOX_WALL_CLOCK_SECONDS, SANDBOX_MEMORY_MIB, SANDBOX_OUTPUT_BYTES
        )
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "skill": self.skill,
            "digest": self.digest,
            "script": self.script,
            "files": {
                path: base64.b64encode(content).decode("ascii")
                for path, content in sorted(self.files.items())
            },
            "sha256": dict(sorted(self.sha256.items())),
            "arguments": list(self.arguments),
            "environment": dict(sorted(self.environment.items())),
            "limits": {
                "wall_clock_seconds": self.limits.wall_clock_seconds,
                "memory_mib": self.limits.memory_mib,
                "output_bytes": self.limits.output_bytes,
            },
        }

    @classmethod
    def from_json(cls, body: object) -> RunRequest:
        """The request a runner was sent, or `SandboxContractError`: the runner says bad_request."""
        if not isinstance(body, Mapping):
            raise SandboxContractError("a run request is a JSON object")
        try:
            files = {str(k): base64.b64decode(v, validate=True) for k, v in body["files"].items()}
            limits = body["limits"]
            return cls(
                run_id=_text(body["run_id"]),
                skill=_text(body["skill"]),
                digest=_text(body["digest"]),
                script=_text(body["script"]),
                files=files,
                sha256={str(k): _text(v) for k, v in body["sha256"].items()},
                arguments=tuple(_text(one) for one in body["arguments"]),
                environment={str(k): _text(v) for k, v in body["environment"].items()},
                limits=RunLimits(
                    wall_clock_seconds=_whole(limits["wall_clock_seconds"]),
                    memory_mib=_whole(limits["memory_mib"]),
                    output_bytes=_whole(limits["output_bytes"]),
                ),
            )
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise SandboxContractError(type(exc).__name__) from None


@dataclass(frozen=True)
class RunAnswer:
    """What the runner sends back for a run it accepted."""

    run_id: str
    status: AnswerStatus
    exit_code: int
    output: str
    elapsed_seconds: float
    truncated: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "output": self.output,
            "elapsed_seconds": self.elapsed_seconds,
            "truncated": self.truncated,
        }

    @classmethod
    def from_json(cls, body: object) -> RunAnswer:
        if not isinstance(body, Mapping):
            raise SandboxContractError("a run answer is a JSON object")
        try:
            elapsed = body["elapsed_seconds"]
            if isinstance(elapsed, bool) or not isinstance(elapsed, int | float) or elapsed < 0:
                raise ValueError("elapsed_seconds")
            truncated = body.get("truncated", False)
            if not isinstance(truncated, bool):
                raise TypeError("truncated")
            return cls(
                run_id=_text(body["run_id"]),
                status=AnswerStatus(body["status"]),
                exit_code=_integer(body["exit_code"]),
                output=_text(body["output"]),
                elapsed_seconds=float(elapsed),
                truncated=truncated,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SandboxContractError(type(exc).__name__) from None


def refusal_of(body: object) -> RefusalCode:
    """The code a 4xx body carries, or `SandboxContractError` for any other shape."""
    if not isinstance(body, Mapping) or set(body) != {"refused"}:
        raise SandboxContractError("a refusal is exactly {'refused': code}")
    try:
        return RefusalCode(body["refused"])
    except ValueError:
        raise SandboxContractError("a refusal names a code this contract does not have") from None


@dataclass(frozen=True)
class SandboxHealth:
    """What `HEALTH_PATH` says: the runtime read from the sandbox's own kernel, and its network."""

    runtime: str
    network: str

    @property
    def is_isolated(self) -> bool:
        return self.runtime == GVISOR_RUNTIME and self.network == NO_NETWORK

    @classmethod
    def from_json(cls, body: object) -> SandboxHealth:
        if not isinstance(body, Mapping):
            raise SandboxContractError("a health answer is a JSON object")
        try:
            return cls(runtime=_text(body["runtime"]), network=_text(body["network"]))
        except (KeyError, TypeError) as exc:
            raise SandboxContractError(type(exc).__name__) from None


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("text")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("integer")
    return value


def _whole(value: object) -> int:
    number = _integer(value)
    if number < 1:
        raise ValueError("limit")
    return number
