"""Why the `full` profile is eight compose files and not one, computed from the files.

`docker-compose.lite.yml` is the `lite` profile as a file an operator can point at, and M0.4.2
asks for the same thing for `full`. **That file is not written, and this module is the reason
in a form that stops being true the moment somebody fixes it.** Four things stand between the
eight files a `full` install composes today and the one file the leaf asks for. Every one of
them is a fact about the product rather than about a particular server, and every one is
computed here rather than argued in a paragraph that nothing recomputes.

**The reason is not the memory arithmetic, and saying so matters because that was the previous
answer.** `brain.ops.wiring.budget_breaches("full")` reports the profile wanting 8320 MiB of
wave 2 against 1720 MiB spare, on the one machine this repository has been measured against.
That is a fact about that machine. This repository is the product and every company installs
it on their own server, so "it does not fit the development host" is not a reason to refuse to
describe the profile: a client with a larger machine runs `full`, and that is what the profile
is for. What such a file owes its reader is the size of host it needs, and `host_mib_for`
computes it rather than leaving it to be guessed.

**What does stop the file being written, in the order a reader meets them.**

A component of the profile has no service anywhere. `components_with_no_service` names it, and
the aggregate cannot be complete while a container in the budget has no declaration to copy.
Writing one would mean choosing an image, a port and a readiness probe for a container nobody
here has run, which is the one thing a file whose whole purpose is to be the profile must not
do.

One service is declared twice, with different bodies. `docker-compose.langfuse.yml` names
`seaweedfs` deliberately, so that a project composing it beside the object store gets one
container rather than two, and its copy is missing the S3 configuration the object store's
copy mounts. Compose settles that by argument order, so which of the two runs depends on the
order of the `-f` flags. See `TWO_DECLARATIONS_OF_ONE_SERVICE_ARE_SETTLED_BY_ARGUMENT_ORDER`.
An aggregate file has to choose one, and choosing is a decision about the object store.

Four services take something they need at startup from a bind mount beside the compose file,
and an aggregate is precisely the form that gets deployed as a stored copy with no repository
beside it. See `A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE`, which is the same trap
`docker-compose.keycloak.yml` already works around for the realm by shipping it inside the
image and writing it into a named volume.

Two services connect to a database that nothing creates. `databases_nothing_creates` reads it
out of the connection strings rather than out of a note, which is the direction
`brain.ops.connections.undeclared_clients` reads in and for the same reason: a deployment that
was never started is described by what it declares, and nothing else.

**Reported rather than raised, and deliberately not a gate.** Every finding is true on
arrival. `brain.ops.sweeps` records at length that a check which is red the day it lands is a
check somebody switches off, so what pins these is a test asserting the exact set, in the
shape `test_connections.py` uses for the four undeclared clients. A fifth relative bind mount
fails a test; it does not fail a deploy that was already failing for four other reasons.

Rejected: writing the aggregate anyway, with the four defects carried into it. The precedent
was there, because `docker-compose.langfuse.yml` and `docker-compose.inference.yml` are both
written for hosts and images that do not exist and say so. The difference is what the file
would be for. Those two are one component each, argued in one place, and their absence of a
host is a sentence in a header. An aggregate is a second copy of eight files whose only
purpose is to be deployable in one piece, so a copy that cannot come up is a maintenance
obligation paid for nothing, and the obligation is permanent: every edit to any of the eight
then has to be copied across or a test goes red.

Rejected: reading the compose files here. Every function takes documents somebody else parsed,
which is the split `brain.ops.connections` keeps and for the same reason. A check that had to
find and open files could not be asked about a file that does not exist yet, and the test
suite is where `yaml.safe_load` belongs so that what is checked is the deployment rather than
a second copy of it kept in Python.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import urlsplit

from brain.ops.wiring import HOST_RESERVE_MIB, assert_known_profile, components_for

#: One compose document, as `yaml.safe_load` returns it.
#:
#: `Any` rather than a TypedDict, and that is a boundary rather than laziness: the shape is
#: whatever the file holds, including the shapes a half-finished edit leaves behind, and a
#: type that promised otherwise would be a promise this module cannot keep about a file it
#: does not own.
ComposeDoc = Mapping[str, Any]

#: Filename against the document parsed from it. Filenames rather than paths, because this
#: module never opens one and a path would suggest it might.
ComposeFiles = Mapping[str, ComposeDoc]

#: Why a mount that reads `./ops/...` is nothing at all once the file is stored elsewhere.
A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE: Final = (
    "A relative bind mount is resolved against the directory the compose file is read from. "
    "The deployment path this system actually uses stores its own copy of the file and runs "
    "it with no repository beside it, so `./ops/whatever` names a path that does not exist. "
    "Docker does not refuse: it creates an empty directory there and starts the container, "
    "so the service comes up healthy with none of the configuration the mount was carrying. "
    "Three of the four here are silent in the worst direction, because what they carry is a "
    "memory ceiling, an egress allowlist and a set of object-store credentials, and a "
    "container missing any of those looks exactly like one that has them. The fourth is a "
    "script named as an entrypoint, so that one at least exits. The answer is the one "
    "`docker-compose.keycloak.yml` already uses for the realm: the file arrives inside the "
    "image and a one-shot container writes it into a named volume."
)

#: Why two declarations of one service are worse than two services.
TWO_DECLARATIONS_OF_ONE_SERVICE_ARE_SETTLED_BY_ARGUMENT_ORDER: Final = (
    "Compose merges every `-f` file into one project, so a service declared in two of them is "
    "one container built from both declarations, with the later file winning wherever the two "
    "disagree. Nothing reports the overlap. That makes the running configuration a property "
    "of the order somebody typed the flags in, which is not a property anybody reviews, and "
    "the failure is invisible in both files because each is correct on its own."
)

#: The compose files a `full` install composes, in the order an operator would name them.
#:
#: A declaration, and it is checked from the other side rather than trusted:
#: `components_with_no_service` asks whether every component of the profile has a service
#: somewhere in this set, so a component added without a file is a finding rather than a
#: silence. `docker-compose.lite.yml` is deliberately absent because it is the same four
#: services as the baseline, and `docker-compose.staging.yml` because it is a different
#: deployment of those four rather than a member of this one.
FULL_PROFILE_FILES: Final = (
    "docker-compose.yml",
    "docker-compose.worker.yml",
    "docker-compose.parse-worker.yml",
    "docker-compose.objectstore.yml",
    "docker-compose.keycloak.yml",
    "docker-compose.langfuse.yml",
    "docker-compose.inference.yml",
    "docker-compose.automation.yml",
)

#: The file whose services are the baseline `brain.ops.wiring.PRODUCTION_BASELINE_MIB`
#: already accounts for. Everything outside it is expected to be a budgeted component, and
#: `unbudgeted_services` is what reports the ones that are not.
BASELINE_FILE: Final = "docker-compose.yml"

#: The four reasons, with the figures the functions below produce.
#:
#: Written out because the next person to ask "why is there no full compose file" will read a
#: sentence rather than run a function, and a sentence with numbers in it goes stale silently.
#: `tests/unit/test_compose.py` compares every figure here against what the files say, in the
#: shape `wiring.A_SET_THAT_DOES_NOT_FIT_ALONE_NEVER_FITS_BESIDE_ANYTHING` is held to.
THE_FULL_PROFILE_IS_NOT_ONE_FILE_YET: Final = (
    "The full profile is 19 containers across 8 compose files, reserving 12096 MiB, and it "
    "needs a host with 12864 MiB to spare once the component that has no service is deployed "
    "too. Four things stop it being written as one file: presidio-analyzer is budgeted and "
    "has no service anywhere, seaweedfs is declared twice with different bodies, 4 services "
    "take something they need at startup from a bind mount that a stored compose resolves to "
    "nothing, and 2 services connect to a database that nothing in these files creates."
)


class ComposeError(Exception):
    """Raised when a compose document cannot be costed or read as one."""


def declared_services(files: ComposeFiles) -> dict[str, tuple[str, ...]]:
    """Every service name against the files declaring it, in filename order.

    The union rather than a per-file view, because everything this module asks is a question
    about the set: a service is declared twice, a component has no service anywhere, a
    connection string names a server declared in a different file from the one holding it.
    """
    found: dict[str, list[str]] = {}
    for name in sorted(files):
        for service in _services_in(files[name]):
            found.setdefault(service, []).append(name)
    return {service: tuple(where) for service, where in found.items()}


def services_declared_differently(files: ComposeFiles) -> tuple[str, ...]:
    """Services declared in more than one file whose declarations disagree.

    Two identical declarations are not reported, and that is the useful half rather than a
    softening: naming one service in two files is how the object store is shared between the
    trace ledger and the profile that also runs it on its own, which is deliberate and
    documented. What is not safe is the two copies drifting, because the winner is then
    decided by the order of the `-f` flags. See
    `TWO_DECLARATIONS_OF_ONE_SERVICE_ARE_SETTLED_BY_ARGUMENT_ORDER`.
    """
    found: list[str] = []
    for service, where in sorted(declared_services(files).items()):
        if len(where) < 2:
            continue
        first = _services_in(files[where[0]])[service]
        for other_file in where[1:]:
            other = _services_in(files[other_file])[service]
            if other == first:
                continue
            found.append(
                f"{service!r} is declared in {where[0]!r} and {other_file!r} and the two "
                f"disagree about {_keys_that_differ(first, other)}; compose settles that by "
                "the order of the -f flags, so the configuration that runs is not a property "
                "of either file"
            )
    return tuple(found)


def relative_bind_mounts(files: ComposeFiles) -> tuple[str, ...]:
    """Every mount whose source is a path beside the compose file rather than a named volume.

    Reported per service rather than per path, because the thing an operator has to act on is
    a container that will come up without its configuration. See
    `A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE`.
    """
    found: list[str] = []
    for name in sorted(files):
        for service, body in sorted(_services_in(files[name]).items()):
            for source in _mount_sources(body):
                if source.startswith((".", "~")):
                    found.append(
                        f"{name}: {service!r} mounts {source!r} from beside the compose file, "
                        "so a deployment that stores its own copy starts the container with "
                        "an empty directory there and no error anywhere"
                    )
    return tuple(found)


def components_with_no_service(profile: str, files: ComposeFiles) -> tuple[str, ...]:
    """Components this profile budgets that no file in this set declares a service for.

    The check that says a profile cannot yet be one file. A component here is memory the
    budget has already spent and a container nobody can start, and the two together are worse
    than either: the arithmetic says the profile is larger than anything deployable proves.
    """
    assert_known_profile(profile)
    declared = set(declared_services(files))
    return tuple(
        f"{one.name!r} is budgeted at {one.memory_mib} MiB in profile {profile!r} and no "
        "compose file declares a service by that name, so it is spent and undeployable"
        for one in components_for(profile)
        if one.name not in declared
    )


def unbudgeted_services(profile: str, files: ComposeFiles) -> tuple[str, ...]:
    """Containers this set deploys that neither the baseline nor a component accounts for.

    The other direction of the same question, and the one the profile arithmetic cannot ask.
    `wave_two_mib` sums components, so a container that is real memory on the host and is not
    a component is invisible to every figure in `brain.ops.wiring`. Four of them are one-shot
    helpers and sidecars that arrived with the files they help, which is exactly how memory
    stops being counted: nobody adds a component for a container that only runs for a second,
    and the sidecar beside it inherits the silence.
    """
    assert_known_profile(profile)
    budgeted = {one.name for one in components_for(profile)}
    baseline = set(_services_in(files[BASELINE_FILE])) if BASELINE_FILE in files else set()
    return tuple(
        f"{service!r} is deployed by {where[0]!r} at {_service_mib(files, service)} MiB and is "
        f"neither a component of profile {profile!r} nor part of the deployed baseline, so no "
        "figure in the budget includes it"
        for service, where in sorted(declared_services(files).items())
        if service not in budgeted and service not in baseline
    )


def databases_nothing_creates(files: ComposeFiles) -> tuple[str, ...]:
    """Services holding a connection string for a database no server in this set creates.

    Read out of the deployment rather than out of a note, for the reason
    `brain.ops.connections.undeclared_clients` reads that way: a stack that has never been
    started is described by what it declares and by nothing else, and the failure this catches
    has no symptom until the day it is started, when it is a container that cannot connect and
    a message about a database that was never anybody's job to create.

    Only servers this set declares are checked. A hostname nobody here declares is somebody
    else's server, and what databases it holds is not visible from a compose file.
    """
    creates = _databases_created(files)
    found: set[str] = set()
    for name in sorted(files):
        for service, body in sorted(_services_in(files[name]).items()):
            for value in _environment(body).values():
                target = _postgres_target(value)
                if target is None:
                    continue
                host, database = target
                if host not in creates or database == creates[host]:
                    continue
                found.add(
                    f"{service!r} connects to database {database!r} on {host!r}, and {host!r} "
                    f"creates only {creates[host]!r}; nothing in these files creates the "
                    "other one, so the service cannot start on a fresh install"
                )
    return tuple(sorted(found))


def deployment_mib(files: ComposeFiles) -> int:
    """What this set of compose files reserves on a host, counting one container once.

    Refuses a service with no memory limit rather than costing it at nothing, which is the
    same refusal `wiring.set_cost_mib` makes about a name nobody budgeted and for the same
    reason: the failure is in the affordable direction. Eighteen of nineteen services costed
    is a profile that looks like it fits by the size of the one that was skipped.

    A service declared twice is costed at the larger of its declarations, because the larger
    is what the host has to honour if that is the declaration the flag order selects.
    """
    return sum(_service_mib(files, service) for service in declared_services(files))


def undeployed_mib(profile: str, files: ComposeFiles) -> int:
    """What this profile budgets for components that have no service in this set."""
    assert_known_profile(profile)
    declared = set(declared_services(files))
    return sum(one.memory_mib for one in components_for(profile) if one.name not in declared)


def unbudgeted_mib(profile: str, files: ComposeFiles) -> int:
    """What this set deploys that neither the baseline nor a component of this profile counts.

    The figure `unbudgeted_services` names one container at a time, kept as a number as well
    because the only way to see that the budget and the deployment describe the same host is
    to add both gaps to both sides and find the totals equal.
    """
    assert_known_profile(profile)
    budgeted = {one.name for one in components_for(profile)}
    baseline = set(_services_in(files[BASELINE_FILE])) if BASELINE_FILE in files else set()
    return sum(
        _service_mib(files, service)
        for service in declared_services(files)
        if service not in budgeted and service not in baseline
    )


def host_mib_for(profile: str, files: ComposeFiles) -> int:
    """The memory a host needs spare to run this profile, with nothing else of ours on it.

    What the files reserve, plus what the profile budgets for the component that has no
    service yet, plus what `brain.ops.wiring` keeps back for the kernel and the session an
    operator needs in order to fix whatever went wrong.

    This is the figure a `docker-compose.full.yml` would owe its reader, and it is the one the
    per-profile budget cannot give: `budget_breaches` answers whether wave 2 fits inside a cap
    measured on one machine, which is a question about that machine. This answers what machine
    the profile needs, which is a question about the product.
    """
    return deployment_mib(files) + undeployed_mib(profile, files) + HOST_RESERVE_MIB


def _services_in(document: ComposeDoc) -> dict[str, Any]:
    """The services block, or an empty one for a document that has none."""
    services = document.get("services") or {}
    if not isinstance(services, Mapping):
        msg = f"a compose document has a services block that is not a mapping: {type(services)}"
        raise ComposeError(msg)
    return {str(name): body for name, body in services.items()}


def _keys_that_differ(first: Any, other: Any) -> list[str]:
    """Which top-level keys two declarations of one service disagree about."""
    if not isinstance(first, Mapping) or not isinstance(other, Mapping):
        return ["the whole declaration"]
    return sorted(str(key) for key in set(first) | set(other) if first.get(key) != other.get(key))


def _mount_sources(body: Any) -> tuple[str, ...]:
    """The source half of every volume entry, in both the short and the long spelling."""
    if not isinstance(body, Mapping):
        return ()
    sources: list[str] = []
    for entry in body.get("volumes") or ():
        if isinstance(entry, Mapping):
            sources.append(str(entry.get("source", "")))
        else:
            sources.append(str(entry).split(":", 1)[0])
    return tuple(sources)


def _environment(body: Any) -> dict[str, str]:
    """A service's environment, from either the mapping or the `KEY=value` list spelling."""
    if not isinstance(body, Mapping):
        return {}
    environment = body.get("environment") or {}
    if isinstance(environment, Mapping):
        return {str(key): str(value) for key, value in environment.items()}
    values: dict[str, str] = {}
    for entry in environment:
        key, _, value = str(entry).partition("=")
        values[key] = value
    return values


def _databases_created(files: ComposeFiles) -> dict[str, str]:
    """Every service that initialises a PostgreSQL database, against the one it creates.

    `POSTGRES_DB` is the official image's own variable and it creates exactly one database on
    an empty data directory. That is the whole of what a compose file creates, which is why a
    second database on the same server is nobody's job until somebody notices.
    """
    created: dict[str, str] = {}
    for name in sorted(files):
        for service, body in _services_in(files[name]).items():
            database = _environment(body).get("POSTGRES_DB")
            if database:
                created[service] = database
    return created


def _postgres_target(url: str) -> tuple[str, str] | None:
    """The host and database a PostgreSQL connection string names, or None for anything else.

    The `jdbc:` prefix is stripped for the reason `brain.ops.connections.direct_database_in`
    strips it: `urlsplit` reads it as the scheme and everything after it as an opaque path, so
    a JDBC URL otherwise has no hostname at all and the check silently sees nothing.
    """
    text = url.strip()
    if text.lower().startswith("jdbc:"):
        text = text[len("jdbc:") :]
    try:
        parts = urlsplit(text)
    except ValueError:
        # A value this cannot parse is not a connection string. A compose environment holds
        # passwords with substitution markers in them, and a check that raised on one would be
        # a check nobody runs.
        return None
    if not parts.scheme.lower().startswith("postgres"):
        return None
    host = parts.hostname
    database = parts.path.lstrip("/")
    if not host or not database:
        return None
    return host, database


def _service_mib(files: ComposeFiles, service: str) -> int:
    """The memory limit on one service, refusing a service that declares none."""
    limits: list[int] = []
    for name in declared_services(files).get(service, ()):
        body = _services_in(files[name])[service]
        limits.append(_limit_mib(body, where=f"{name}: {service}"))
    if not limits:
        msg = f"no compose file in this set declares {service!r}"
        raise ComposeError(msg)
    return max(limits)


def _limit_mib(body: Any, *, where: str) -> int:
    """`deploy.resources.limits.memory` in MiB, refusing a service that does not set one."""
    value = None
    if isinstance(body, Mapping):
        value = body.get("deploy", {}).get("resources", {}).get("limits", {}).get("memory")
    if value is None:
        msg = (
            f"{where} declares no memory limit, so costing this set would understate it by "
            "however large that container turns out to be"
        )
        raise ComposeError(msg)
    text = str(value).strip().upper()
    if text.endswith("G"):
        return int(float(text[:-1]) * 1024)
    return int(float(text.rstrip("M")))
