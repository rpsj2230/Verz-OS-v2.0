"""What this container was started with, read once and checked.

The application decides the figures (`brain.ops.model_server.environment`) and the compose file
hands them over as environment variables; this reads them. Nothing here has a default of its own
that the application does not also have, because a default spelled in two programs is a default
that disagrees with itself the first time one of them is edited: the compose file carries the
defaults, and a variable that is missing is a container started by somebody who did not use it,
which is refused rather than guessed.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The parts, spelled as `brain.ops.model_server.Part`'s values.
PARTS: Final = ("layout", "ocr", "tika", "embedding", "entities")

#: The environment variable names, spelled as `brain.ops.model_server.environment` writes them.
PARTS_VARIABLE: Final = "INFERENCE_PARTS"
IDLE_VARIABLE: Final = "INFERENCE_IDLE_SECONDS"
MEMORY_VARIABLE: Final = "INFERENCE_MEMORY_MIB"
UPLOAD_VARIABLE: Final = "INFERENCE_UPLOAD_MB"
CEILING_VARIABLE: Final = "INFERENCE_MAX_REQUEST_BYTES"
AT_ONCE_VARIABLE: Final = "INFERENCE_REQUESTS_AT_ONCE"
MODEL_DIR_VARIABLE: Final = "INFERENCE_MODEL_DIR"
EMBEDDING_MODEL_VARIABLE: Final = "INFERENCE_EMBEDDING_MODEL"
EMBEDDING_FILE_VARIABLE: Final = "INFERENCE_EMBEDDING_FILE"
THREADS_VARIABLE: Final = "OMP_NUM_THREADS"


def need_variable(part: str) -> str:
    """The variable holding what a part cannot give back, in MiB: `INFERENCE_NEED_EMBEDDING_MIB`."""
    return f"INFERENCE_NEED_{part.upper()}_MIB"


class ConfigError(Exception):
    """The container was started with something this program cannot run on, with the sentence."""


@dataclass(frozen=True)
class ServerConfig:
    """What the supervisor runs under. Frozen, and every figure checked on the way in."""

    parts: tuple[str, ...]
    idle_seconds: int
    memory_mib: int
    upload_mb: int
    max_request_bytes: int
    requests_at_once: int
    model_dir: Path
    embedding_model: str
    embedding_file: str
    threads: int
    #: What each chosen part cannot give back while it works, in MiB, for the admission check.
    needs_mib: Mapping[str, int]
    port: int = 8080


def _whole(env: Mapping[str, str], name: str, *, least: int = 1) -> int:
    text = (env.get(name) or "").strip()
    if not text:
        msg = f"{name} is not set; the compose file hands it over and nobody else does"
        raise ConfigError(msg)
    try:
        value = int(text)
    except ValueError:
        msg = f"{name} is {text!r}, which is not a whole number"
        raise ConfigError(msg) from None
    if value < least:
        msg = f"{name} is {value}, which is under the least it may be, {least}"
        raise ConfigError(msg)
    return value


def from_environment(env: Mapping[str, str]) -> ServerConfig:
    """The configuration this container was started with, or the first reason it cannot run."""
    names = [one.strip().casefold() for one in (env.get(PARTS_VARIABLE) or "").split(",")]
    chosen = tuple(one for one in names if one)
    if not chosen:
        msg = f"{PARTS_VARIABLE} names no part, so the server would hold memory and do nothing"
        raise ConfigError(msg)
    unknown = [one for one in chosen if one not in PARTS]
    if unknown:
        msg = f"{PARTS_VARIABLE} names {unknown}, which this server does not have; it has {PARTS}"
        raise ConfigError(msg)
    if len(set(chosen)) != len(chosen):
        msg = f"{PARTS_VARIABLE} names a part twice"
        raise ConfigError(msg)
    needs = {one: _whole(env, need_variable(one)) for one in chosen}
    return ServerConfig(
        parts=chosen,
        idle_seconds=_whole(env, IDLE_VARIABLE, least=1),
        memory_mib=_whole(env, MEMORY_VARIABLE),
        upload_mb=_whole(env, UPLOAD_VARIABLE),
        max_request_bytes=_whole(env, CEILING_VARIABLE),
        requests_at_once=_whole(env, AT_ONCE_VARIABLE),
        model_dir=Path((env.get(MODEL_DIR_VARIABLE) or "/models").strip()),
        embedding_model=(env.get(EMBEDDING_MODEL_VARIABLE) or "").strip(),
        embedding_file=(env.get(EMBEDDING_FILE_VARIABLE) or "").strip(),
        threads=max(1, int((env.get(THREADS_VARIABLE) or "1").strip() or "1")),
        needs_mib=needs,
    )
