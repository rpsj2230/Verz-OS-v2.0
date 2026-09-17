"""The application database's memory settings, per profile, held to the sizing that pays for them.

M0.3.6 asks for `shared_buffers`, `work_mem` and `autovacuum_work_mem` set explicitly per
profile. The compose files already carried a `command:` with most of them, and nothing read it:
the one test on it searched each file's text for the word, so a setting inside a comment passed,
and `autovacuum_work_mem` was on two files and missing from the third without anything noticing.

**Why `autovacuum_work_mem` is the one that matters most on a shared host.** Unset it is `-1`,
which means "use `maintenance_work_mem`", and autovacuum runs up to `autovacuum_max_workers`
(three by default) at once. So the unset value is three times `maintenance_work_mem` of memory
nobody chose, arriving at whatever hour autovacuum picks. See
`AN_UNSET_AUTOVACUUM_WORK_MEM_IS_THREE_TIMES_MAINTENANCE`.

**The figures are one row per profile, and the rows are equal today on purpose.** `lite`,
`standard` and `full` all run the database service described in `docker-compose.yml` (lite's
file is held equal to it by `tests/unit/test_repo_shape.py`), so they run one 2048 MiB container,
and three different sets of figures for one container would be two of them wrong. The table is
still per profile because the day a profile gets its own database body is the day its row has to
change, and `settings_gaps` is asked per profile so that it fails for that profile alone.

**The sum is checked against the sizing, not only the spelling.** `brain.ops.connections` owns
the database's memory limit, `shared_buffers`, `work_mem` and the connection demand its clients
declare. What the settings here can cost at once, `shared_buffers + demand * work_mem +
maintenance_work_mem + autovacuum_max_workers * autovacuum_work_mem`, has to fit in that limit.
The declared demand rather than `max_connections`, for the reason
`connections.THE_POOLER_IS_WHAT_MAKES_THE_CEILING_SAFE` gives: the ceiling is a refusal
threshold that the poolers keep anything from reaching.

Rejected: generating the compose `command:` from this table. A stored compose (Coolify's) is a
copy with no repository beside it, so the file has to carry literal values and this module can
only check them.

Task ids: M0.3.6
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from brain.ops.connections import database, demand_on
from brain.ops.wiring import PROFILES

#: The service the application's database runs as in every profile.
DATABASE_SERVICE: Final = "db"

#: What PostgreSQL runs at once by default, and nothing in this deployment raises it.
AUTOVACUUM_MAX_WORKERS: Final = 3

#: The settings M0.3.6 names, plus the one `autovacuum_work_mem` falls back to when unset.
EXPLICIT_SETTINGS: Final[tuple[str, ...]] = (
    "shared_buffers",
    "work_mem",
    "maintenance_work_mem",
    "autovacuum_work_mem",
)

#: Why the autovacuum figure is set even though a default exists.
AN_UNSET_AUTOVACUUM_WORK_MEM_IS_THREE_TIMES_MAINTENANCE: Final = (
    "autovacuum_work_mem defaults to -1, which means maintenance_work_mem, and autovacuum runs "
    "up to autovacuum_max_workers of them at once. Left unset on a 2048 MiB container with "
    "maintenance_work_mem=256MB that is 768 MiB nobody chose, at an hour nobody chose, beside a "
    "neighbour's production. Set, it is a figure the sum below counts."
)

_SETTING = re.compile(r"-c\s+([a-z_]+)=(\S+)")


@dataclass(frozen=True)
class PostgresSettings:
    """The memory settings of one database container, in MiB."""

    shared_buffers_mib: int
    work_mem_mib: int
    maintenance_work_mem_mib: int
    autovacuum_work_mem_mib: int

    def __post_init__(self) -> None:
        for name, value in self.as_arguments().items():
            if not value.endswith("MB") or int(value[:-2]) < 1:
                msg = f"{name} is {value}; every memory setting here is a positive MiB figure"
                raise ValueError(msg)

    def as_arguments(self) -> dict[str, str]:
        """Each setting as the compose `command:` spells it."""
        return {
            "shared_buffers": f"{self.shared_buffers_mib}MB",
            "work_mem": f"{self.work_mem_mib}MB",
            "maintenance_work_mem": f"{self.maintenance_work_mem_mib}MB",
            "autovacuum_work_mem": f"{self.autovacuum_work_mem_mib}MB",
        }

    def worst_case_mib(self, connections: int) -> int:
        """What these settings can hold at once with `connections` backends each sorting."""
        return (
            self.shared_buffers_mib
            + connections * self.work_mem_mib
            + self.maintenance_work_mem_mib
            + AUTOVACUUM_MAX_WORKERS * self.autovacuum_work_mem_mib
        )


_ONE_CONTAINER = PostgresSettings(
    shared_buffers_mib=512,
    work_mem_mib=16,
    maintenance_work_mem_mib=256,
    autovacuum_work_mem_mib=128,
)

#: The figures each profile's database runs with. Equal today; see the module docstring.
SETTINGS_FOR: Final[Mapping[str, PostgresSettings]] = MappingProxyType(
    {"lite": _ONE_CONTAINER, "standard": _ONE_CONTAINER, "full": _ONE_CONTAINER}
)


def command_settings(command: object) -> dict[str, str]:
    """Every `-c name=value` on a compose `command:`, in either the string or the list form."""
    if isinstance(command, list):
        text = " ".join(str(one) for one in command)
    elif isinstance(command, str):
        text = command
    else:
        return {}
    return dict(_SETTING.findall(text))


def _database_body(files: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The one described body of the database service across a profile's files."""
    for name in sorted(files):
        body = (files[name].get("services") or {}).get(DATABASE_SERVICE)
        if isinstance(body, Mapping) and body:
            return body
    return None


def settings_gaps(profile: str, files: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    """Every way this profile's database command disagrees with its row or its sizing.

    `files` is the profile's compose documents, already parsed; see
    `brain.deployment.requirements.COMPOSE_FILES_FOR`.
    """
    if profile not in PROFILES:
        msg = f"{profile!r} is not a profile; the profiles are {PROFILES}"
        raise KeyError(msg)
    body = _database_body(files)
    if body is None:
        return (f"profile {profile!r} describes no {DATABASE_SERVICE!r} service",)

    wanted = SETTINGS_FOR[profile]
    stated = command_settings(body.get("command"))
    findings: list[str] = []
    for name, value in wanted.as_arguments().items():
        if name not in stated:
            findings.append(
                f"profile {profile!r} leaves {name} to PostgreSQL's default; it is sized at {value}"
            )
        elif stated[name] != value:
            findings.append(f"profile {profile!r} sets {name}={stated[name]} and is sized {value}")

    sizing = database(DATABASE_SERVICE)
    limit = str(
        ((body.get("deploy") or {}).get("resources") or {}).get("limits", {}).get("memory", "")
    )
    if limit != f"{sizing.memory_mib}M":
        findings.append(
            f"profile {profile!r} limits {DATABASE_SERVICE!r} to {limit or 'nothing'} and "
            f"brain.ops.connections sizes it at {sizing.memory_mib}M, so the sum below is "
            "checked against a container this profile does not run"
        )
    if (wanted.shared_buffers_mib, wanted.work_mem_mib) != (
        sizing.shared_buffers_mib,
        sizing.work_mem_mib,
    ):
        findings.append(
            f"profile {profile!r} is sized shared_buffers={wanted.shared_buffers_mib}MB "
            f"work_mem={wanted.work_mem_mib}MB and brain.ops.connections budgets "
            f"{sizing.shared_buffers_mib}MB and {sizing.work_mem_mib}MB"
        )
    worst = wanted.worst_case_mib(demand_on(DATABASE_SERVICE))
    if worst > sizing.memory_mib:
        findings.append(
            f"profile {profile!r} can hold {worst} MiB at once against a "
            f"{sizing.memory_mib} MiB container. "
            f"{AN_UNSET_AUTOVACUUM_WORK_MEM_IS_THREE_TIMES_MAINTENANCE}"
        )
    return tuple(findings)
