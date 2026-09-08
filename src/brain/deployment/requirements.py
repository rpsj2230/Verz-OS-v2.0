"""What size of server each profile needs, computed from the deployment rather than guessed.

M42.2.1 asks for a recommended specification per profile "with the memory and connection
arithmetic already measured", and the reason that phrase is in the leaf is that both sums
already exist here and neither was ever assembled into an answer anybody could act on.
`brain.ops.compose.host_mib_for` costs a set of compose files and adds what the profile
budgets for a component that has no service yet. `brain.ops.connections` holds the two
PostgreSQL servers, their ceilings and what every declared client may hold open. **This module
adds no arithmetic to either. It selects the files a profile composes and reports both sums
against that selection**, which is the step that was missing and the only one that can be
wrong in a way a client notices.

**Two of the four figures are measured and two are ratios, and the difference is stated rather
than implied.** Memory comes out of the compose files and the connection figures out of the
connection budget; both change when the deployment changes. Cores and disk are derived from
the deployment by a stated ratio, because nothing here has ever been measured under load and a
figure invented to look precise is worse than a figure that says what it is. `ServerSpec.notes`
prints the provenance beside every number for exactly that reason.

**The file list per profile is a declaration and it is checked from the other side.** The
tempting alternative is to derive it: take the profile's components, find the file declaring
each. That cannot work, because `docker-compose.lite.yml` and `docker-compose.yml` declare the
same four services, so a derivation picks up both and every service is then declared twice with
which one runs decided by the order of the `-f` flags. So the list is written down, and
`brain.ops.compose.components_with_no_service` asked about that list is what refuses a profile
whose file set cannot start it. Asked today it names `presidio-analyzer` for `standard` and for
`full`, which is the first of the four reasons there is no aggregate compose file.

**The port requirement is the one that surprises a reader.** No service in any compose file in
this repository declares `ports:`, only `expose:`, so a fresh server that has run the install
to completion is answering on nothing at all from outside its own docker network. That is
correct for every service except the console, and it means the reverse proxy is a requirement
of the install rather than an optional extra, and no compose file declares one.

Rejected: taking a profile name and reading the files itself. Every function here takes
documents somebody else parsed, which is the split `brain.ops.compose` keeps: a check that
had to open files could not be asked about a profile whose files nobody has written, and the
test suite is where `yaml.safe_load` belongs so that what is checked is the deployment rather
than a second copy of it kept in Python.

Task ids: M42.2.1, M42.2.2
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil
from types import MappingProxyType
from typing import Any, Final

from brain.ops.compose import (
    FULL_PROFILE_FILES,
    ComposeFiles,
    declared_services,
    host_mib_for,
)
from brain.ops.connections import (
    DATABASES,
    POSTGRES_RESERVED_CONNECTIONS,
    demand_on,
    headroom_on,
)
from brain.ops.wiring import PROFILES, assert_known_profile

#: Why the memory limits in every compose file are a requirement on the runtime and not a
#: property of the file.
#:
#: Every service in this repository writes its ceiling under `deploy.resources.limits.memory`,
#: which is the Compose specification's spelling and is honoured by `docker compose` v2 outside
#: swarm. The v1 Python `docker-compose` **ignores that whole block without a warning**, so an
#: install on a host with the old tool starts every container unlimited, `docker stats` shows
#: no ceiling anywhere, and the first runaway query takes the box with it. On a client's own
#: server that is their outage; on a shared one it is somebody else's. It is the single
#: requirement here whose absence produces no error message at any point.
LIMITS_ARE_IGNORED_WITHOUT_COMPOSE_V2: Final = (
    "Every memory ceiling in this deployment is written under deploy.resources.limits, and "
    "the v1 docker-compose tool ignores that block silently. An install on the old tool comes "
    "up healthy with every container unlimited and nothing anywhere says so, which turns the "
    "whole of brain.ops.wiring into a document about a deployment that is not running."
)

#: Why the install needs something in front of it that no compose file declares.
NOTHING_IN_THIS_DEPLOYMENT_PUBLISHES_A_PORT: Final = (
    "Every service uses `expose` and none uses `ports`, so after a complete install the "
    "console is reachable from other containers and from nowhere else. That is right for the "
    "database, the cache and the pooler, and it means the reverse proxy holding the "
    "certificate is part of the install rather than an optional extra. No compose file in "
    "this repository declares one, so it is a requirement on the server and not on the stack."
)

#: The compose files each profile composes, in the order an operator names them.
#:
#: `full` is `brain.ops.compose.FULL_PROFILE_FILES` rather than a copy of it: that tuple is
#: already the declaration, already checked from the other side, and a second list here would
#: be a second answer to which files a full install runs.
COMPOSE_FILES_FOR: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        # One file, and it is the only profile that is one file today. Lite is the whole
        # stack minus the worker, which is what production runs.
        "lite": ("docker-compose.lite.yml",),
        "standard": (
            "docker-compose.yml",
            "docker-compose.worker.yml",
            "docker-compose.parse-worker.yml",
            "docker-compose.objectstore.yml",
            "docker-compose.keycloak.yml",
            "docker-compose.inference.yml",
        ),
        "full": FULL_PROFILE_FILES,
    }
)

#: How much memory one core is expected to serve. A ratio rather than a measurement, and the
#: figure is the one the database dominates: `db` alone is 2048 MiB and a core that is also
#: running the application beside it is a core the query waits behind.
MIB_PER_CPU: Final = 2048

#: How many containers one core is expected to serve. The second term exists because the
#: memory ratio alone under-counts a profile made of many small containers: `full` is nineteen
#: containers, four of which are one-shot helpers and sidecars that nothing budgets at all.
CONTAINERS_PER_CPU: Final = 4

#: Disk for one container image and its layers, in GiB. A ratio, and a generous one, because
#: the inference server's image is the largest thing this system pulls and nothing here has
#: measured it.
IMAGE_GIB: Final = 2

#: Disk for everything that is not an image: the database, the object store, the parsed
#: originals, and the room a restore needs to sit beside what it is replacing.
DATA_GIB: Final = 20

#: `-c max_connections=100` inside a compose `command:`, which is where this deployment sets it.
MAX_CONNECTIONS = re.compile(r"-c\s+max_connections=(\d+)")


class RequirementError(Exception):
    """Raised when a requirement or a specification is described in a way nobody can act on."""


@dataclass(frozen=True)
class Requirement:
    """One thing a server must already have before the installer is run.

    `why` is required and is not a comment. It is what somebody reads when the requirement is
    inconvenient, and a requirement whose reason nobody wrote down is one that gets waived by
    the person under the most time pressure. `Component.ready_when` is required for the same
    reason and `brain.install.Setting.meaning` for the same reason again.
    """

    #: What is needed, named as somebody would search for it.
    what: str
    #: The smallest version or value that works, or an empty string when there is no version.
    minimum: str
    #: What breaks without it, in a sentence.
    why: str

    def __post_init__(self) -> None:
        if not self.what.strip():
            msg = "a requirement with no name cannot be checked for on a server"
            raise RequirementError(msg)
        if not self.why.strip():
            msg = (
                f"{self.what} does not say what breaks without it, and a requirement with no "
                "reason is one somebody waives on the day it is inconvenient"
            )
            raise RequirementError(msg)


#: Operating system, runtime and packages. Ports are computed rather than listed: see
#: `published_ports` and `NOTHING_IN_THIS_DEPLOYMENT_PUBLISHES_A_PORT`.
RUNTIME_REQUIREMENTS: Final[tuple[Requirement, ...]] = (
    Requirement(
        what="a 64-bit Linux with cgroup v2",
        minimum="",
        why=(
            "every container image this deployment pulls is linux/amd64 or linux/arm64, and "
            "the memory ceilings are enforced by the kernel rather than by docker"
        ),
    ),
    Requirement(
        what="Docker Engine",
        minimum="24.0",
        why=(
            "the compose files use the Compose specification's `deploy` block, healthcheck "
            "`start_period` and `depends_on` conditions, and an older engine starts the "
            "dependent container before its dependency is ready"
        ),
    ),
    Requirement(
        what="Docker Compose v2, as the `docker compose` subcommand",
        minimum="2.10",
        why=LIMITS_ARE_IGNORED_WITHOUT_COMPOSE_V2,
    ),
    Requirement(
        what="curl and tar",
        minimum="",
        why=(
            "the installer fetches one release archive and unpacks it. It does not clone a "
            "repository, because a build that fetches a second repository is the shape "
            "brain.ops.independence.duplication_gaps refuses"
        ),
    ),
    Requirement(
        what="openssl",
        minimum="",
        why=(
            "every password and key is minted on this server during the install, and a "
            "generator that is not a CSPRNG is a credential somebody can reproduce"
        ),
    ),
    Requirement(
        what="a reverse proxy terminating TLS on 443",
        minimum="",
        why=NOTHING_IN_THIS_DEPLOYMENT_PUBLISHES_A_PORT,
    ),
)


@dataclass(frozen=True)
class ServerSpec:
    """The server one profile needs, with the provenance of every figure on it.

    Frozen and validated, because this is the number somebody buys a machine against and a
    zero anywhere in it reads as "no requirement" rather than as a bug in whatever produced it.
    """

    profile: str
    #: What the compose files reserve, plus the profile's undeployed components, plus the
    #: host reserve. Computed by `brain.ops.compose.host_mib_for`.
    memory_mib: int
    #: Containers this profile's files declare, counting one service once.
    containers: int
    #: Derived from the two ratios above.
    cpus: int
    #: Derived from the image count and `DATA_GIB`.
    disk_gib: int

    def __post_init__(self) -> None:
        assert_known_profile(self.profile)
        if self.memory_mib < 1:
            msg = f"{self.profile} reserves no memory, which is a costing that did not happen"
            raise RequirementError(msg)
        if self.containers < 1:
            msg = f"{self.profile} declares no containers, so nothing would start"
            raise RequirementError(msg)
        if self.cpus < 1:
            msg = f"{self.profile} needs no cores, which no server can be bought against"
            raise RequirementError(msg)
        if self.disk_gib < 1:
            msg = f"{self.profile} needs no disk, and the images alone are gigabytes"
            raise RequirementError(msg)

    def notes(self) -> str:
        """The specification as a person reads it, with where each figure came from.

        The provenance is the point. A reader handed "8 cores" cannot tell a measurement from
        a ratio, and the two deserve different amounts of trust when the machine turns out to
        be too small.
        """
        return "\n".join(
            (
                f"profile: {self.profile}",
                f"memory: {self.memory_mib} MiB    (measured: the sum of every compose "
                "memory limit, plus what this profile budgets for a component that has no "
                "service, plus the host reserve)",
                f"cores: {self.cpus}    (a ratio: one per {MIB_PER_CPU} MiB and one per "
                f"{CONTAINERS_PER_CPU} containers, whichever is larger)",
                f"disk: {self.disk_gib} GiB    (a ratio: {IMAGE_GIB} GiB per image plus "
                f"{DATA_GIB} GiB for data and a restore)",
                f"containers: {self.containers}",
            )
        )


def files_for(profile: str) -> tuple[str, ...]:
    """The compose files this profile composes, refusing a profile nobody declared."""
    assert_known_profile(profile)
    return COMPOSE_FILES_FOR[profile]


def images_in(files: ComposeFiles) -> tuple[str, ...]:
    """Every distinct image reference in this set, in sorted order.

    Distinct rather than one per service, because `seaweedfs` and `seaweedfs-init` are the
    same image and a disk figure that counted it twice would be describing a pull that does
    not happen.
    """
    found = {
        str(body["image"])
        for name in files
        for body in _bodies(files[name])
        if isinstance(body, Mapping) and body.get("image")
    }
    return tuple(sorted(found))


def published_ports(files: ComposeFiles) -> tuple[str, ...]:
    """Every host port this set publishes, as `service: entry`.

    Empty today for every profile, which is the finding rather than the absence of one. See
    `NOTHING_IN_THIS_DEPLOYMENT_PUBLISHES_A_PORT`.
    """
    found: list[str] = []
    for name in sorted(files):
        for service, body in sorted(_services(files[name]).items()):
            if not isinstance(body, Mapping):
                continue
            for entry in body.get("ports") or ():
                found.append(f"{service}: {entry}")
    return tuple(found)


def exposed_ports(files: ComposeFiles) -> dict[str, tuple[str, ...]]:
    """Every port each service opens on the compose network, by service name."""
    found: dict[str, tuple[str, ...]] = {}
    for name in sorted(files):
        for service, body in sorted(_services(files[name]).items()):
            if not isinstance(body, Mapping):
                continue
            entries = tuple(str(one) for one in body.get("expose") or ())
            if entries:
                found[service] = entries
    return found


def spec_for(profile: str, files: ComposeFiles) -> ServerSpec:
    """The server this profile needs, from these compose documents.

    The memory figure is `brain.ops.compose.host_mib_for` unchanged, which is deliberate: that
    function is what a `docker-compose.full.yml` would owe its reader, and a specification
    that recomputed it would be a second answer to the one question the compose module already
    settles.
    """
    assert_known_profile(profile)
    memory_mib = host_mib_for(profile, files)
    containers = len(declared_services(files))
    cpus = max(ceil(memory_mib / MIB_PER_CPU), ceil(containers / CONTAINERS_PER_CPU))
    disk_gib = len(images_in(files)) * IMAGE_GIB + DATA_GIB
    return ServerSpec(
        profile=profile,
        memory_mib=memory_mib,
        containers=containers,
        cpus=cpus,
        disk_gib=disk_gib,
    )


def connection_arithmetic(files: ComposeFiles) -> tuple[str, ...]:
    """What every PostgreSQL this set deploys admits, and what is already spoken for.

    Read out of `brain.ops.connections`, which owns the budget, and selected by what this file
    set actually declares. A profile that deploys no Keycloak has no keycloak-db line, and a
    specification listing one would be describing a different install.

    The server ceiling is checked against the compose `command:` as well as against the
    declaration, because the two are separate copies of one number and the whole value of the
    budget is that it stops matching when somebody edits the file.
    """
    deployed = set(declared_services(files))
    lines: list[str] = []
    for one in DATABASES:
        if one.name not in deployed:
            continue
        stated = _max_connections_in(files, one.name)
        drift = (
            ""
            if stated is None or stated == one.max_connections
            else f" (the compose command says {stated}, and the budget says "
            f"{one.max_connections}; one of them is describing a different server)"
        )
        lines.append(
            f"{one.name}: {one.max_connections} connections, {POSTGRES_RESERVED_CONNECTIONS} "
            f"reserved for administrators, {demand_on(one.name)} claimed by declared clients, "
            f"{headroom_on(one.name)} spare{drift}"
        )
    return tuple(lines)


def _max_connections_in(files: ComposeFiles, service: str) -> int | None:
    """`max_connections` from a service's compose `command:`, or None when it sets none."""
    for name in sorted(files):
        body = _services(files[name]).get(service)
        if not isinstance(body, Mapping):
            continue
        command = body.get("command")
        # The positive branch rather than a `continue` on None, so that refusing it stops the
        # command being read at all and a test says so. Spelled as `is None` it was equivalent
        # to reading `str(None)`, which matches nothing, so nothing could ever observe it.
        if isinstance(command, str | list):
            text = " ".join(str(one) for one in command) if isinstance(command, list) else command
            match = MAX_CONNECTIONS.search(text)
            if match:
                return int(match.group(1))
    return None


def _services(document: Mapping[str, Any]) -> dict[str, Any]:
    """The services block of one document, or an empty one.

    A local accessor rather than a shared helper: `brain.ops.compose` keeps its own private
    one and refuses a services block that is not a mapping, which is a rule about costing a
    deployment. This is a lookup, and importing a private name to save four lines would tie a
    module that reads to a module that decides.
    """
    services = document.get("services")
    return dict(services) if isinstance(services, Mapping) else {}


def _bodies(document: Mapping[str, Any]) -> tuple[Any, ...]:
    """Every service body in one document, in declaration order."""
    return tuple(_services(document).values())


def profiles_by_size(files_by_profile: Mapping[str, ComposeFiles]) -> tuple[ServerSpec, ...]:
    """A specification for each profile given, smallest server first.

    Sorted rather than left in declaration order, because the question a reader arrives with
    is "what fits on the machine I have", and an answer they have to sort themselves is one
    they sort by the name of the profile.
    """
    specs = [
        spec_for(profile, files_by_profile[profile])
        for profile in PROFILES
        if profile in files_by_profile
    ]
    return tuple(sorted(specs, key=lambda one: one.memory_mib))
