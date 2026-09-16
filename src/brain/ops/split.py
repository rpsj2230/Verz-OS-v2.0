"""Two hosts: the application on one, and the database and the object store on the other.

`brain.ops.scaling` names the move and its trigger, RAM pressure or a resilience requirement.
This module is the move itself, as three overlay files and the checks that keep them honest,
and the claim it has to support is the second leaf's: **the split needs no application
change**. Every service reads where its database is from a connection string in its
environment, so moving the database to another host is a change to those strings and to what
the data host publishes, and to nothing the image contains.

**One set of overlays for both hosts, and a service list per host.** The obvious shape is two
standalone files, one per host. It was rejected because the application's service block would
then exist twice, and the base file's copy is edited often: every setting the application gains
would have to be copied into a file most installs never read, and the copy that drifts is the
one nobody is looking at. So the profile's own files are composed on both hosts, the overlays
change only connection strings and published ports, and which services start is the argument
to `docker compose up`, computed by `host_services`. A pooler's published port is therefore
declared on the application host too, where it is never bound, because the pooler is not
started there. See `THE_OVERLAY_CHANGES_ADDRESSES_AND_NOTHING_THE_IMAGE_READS`.

**Rejected: disabling the other host's services with compose profiles.** It would let a plain
`docker compose up -d` start the right set, which is the attraction. It needs every dependency
across the boundary marked `required: false`, whose behaviour for a service switched off by a
profile has changed between compose releases, or the `!reset` merge tag, which no parser this
repository's tests use can read. An explicit service list works on every compose release and
fails loudly when forgotten: started on the application host with no list, the poolers try to
bind the data host's private address, which is not on that machine, and compose refuses.

**Every published port is bound to one private address, and the variable holding it is
required.** A port published without an address is published on every interface, and Docker
inserts its rule ahead of the host firewall, so `ufw deny` would not stop it: see
`docs/install/network.md`. A variable spelled `${NAME}` that nobody set becomes exactly that
unbound publication. So the address is `${BRAIN_DATA_HOST_ADDRESS:?...}` on every entry, and
`published_port_gaps` refuses any other form; see
`A_PORT_WITH_NO_ADDRESS_IS_PUBLISHED_ON_EVERY_INTERFACE`.
`address_refusals` is what an operator runs against the value itself, because compose can say
that a variable is set and cannot say whether it is private.

**The database itself is never published, only its poolers.** A connection from the application
host is a connection the application's pooler already bounds, and the database's own port
admits the superuser from anywhere its address is reachable. See
`THE_DATA_HOST_PUBLISHES_POOLERS_AND_NEVER_THE_DATABASE`.

**What is not split: the `full` profile.** The trace ledger's two services connect straight to
`db` and to the object store by service name, and no overlay here rewrites them.
`split_gaps("full")` names both rather than this paragraph asserting it, so the day an overlay
covers them the finding disappears and a test says so.

What has not happened: nobody has run these overlays. The merge rules they depend on, a
service's `environment` merged by key and its `ports` appended, are compose's documented rules
and have not been observed here, and the rehearsal that would observe them is written in
`docs/install/scaling.md`.

Task ids: M36.1.4.1, M36.1.4.2
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from brain.deployment.requirements import files_for
from brain.ops.compose import ComposeFiles

#: The variable naming the data host's private address, read on both hosts from one value.
ADDRESS_VARIABLE: Final = "BRAIN_DATA_HOST_ADDRESS"

#: How every overlay spells that address, so an unset variable refuses rather than binds widely.
ADDRESS: Final = (
    "${" + ADDRESS_VARIABLE + ":?set " + ADDRESS_VARIABLE + " to the data host private address}"
)

#: The overlay every split composes.
BASE_OVERLAY: Final = "docker-compose.split.yml"

#: The overlay for the two workers and their pooler, composed where the workers are.
WORKERS_OVERLAY: Final = "docker-compose.split.workers.yml"

#: The overlay for the object store, composed where the object store is.
OBJECT_STORE_OVERLAY: Final = "docker-compose.split.objectstore.yml"

#: Each overlay against the compose file whose presence decides it.
OVERLAY_CONDITIONS: Final[Mapping[str, str | None]] = {
    BASE_OVERLAY: None,
    WORKERS_OVERLAY: "docker-compose.worker.yml",
    OBJECT_STORE_OVERLAY: "docker-compose.objectstore.yml",
}

#: What the data host runs. Everything else in a profile is the application host's.
DATA_TIER: Final[frozenset[str]] = frozenset(
    {"db", "pgbouncer", "pgbouncer-session", "seaweedfs", "seaweedfs-init"}
)

#: The one port each published data-tier service opens on the private address: host, container.
PUBLISHED: Final[Mapping[str, tuple[int, int]]] = {
    "pgbouncer": (6432, 5432),
    "pgbouncer-session": (6433, 5432),
    "seaweedfs": (8333, 8333),
}

#: The keys an overlay may set on a service, by tier. Anything else is an application change.
APPLICATION_KEYS: Final[frozenset[str]] = frozenset({"environment"})
DATA_KEYS: Final[frozenset[str]] = frozenset({"ports"})

HOSTS: Final[tuple[str, ...]] = ("application", "data")

THE_OVERLAY_CHANGES_ADDRESSES_AND_NOTHING_THE_IMAGE_READS: Final = (
    "An overlay here may set a connection string in an application-host service's environment "
    "and a published port on a data-host service, and nothing else. An image, a command, a "
    "healthcheck or any other setting changed for the split is a change to how the application "
    "runs, and the leaf this answers is that the split needs none."
)

A_PORT_WITH_NO_ADDRESS_IS_PUBLISHED_ON_EVERY_INTERFACE: Final = (
    "A published port with no address binds every interface, including the public one, and "
    "Docker's own rule is consulted before the host firewall, so a deny rule does not stop it. "
    "Every published entry names the required address variable, so an unset variable refuses "
    "to start instead of publishing the database's pooler to the internet."
)

THE_DATA_HOST_PUBLISHES_POOLERS_AND_NEVER_THE_DATABASE: Final = (
    "The application host reaches the database through the poolers, which bound what it may "
    "hold. The database's own port admits the superuser, and publishing it would put that "
    "login one network hop from anything that can reach the private address."
)

THE_LINK_BETWEEN_THE_HOSTS_IS_NOT_ENCRYPTED_BY_THIS_PRODUCT: Final = (
    "Neither pooler nor the object store is given a certificate, so what crosses between the "
    "hosts is only as private as the network carrying it. The address has to be one on an "
    "encrypted private network such as a WireGuard interface, and a provider's private network "
    "that other customers share is not one."
)

#: `${NAME:?message}` at the start of a ports entry, capturing the name.
_REQUIRED_ADDRESS: Final = re.compile(r"\A\$\{([A-Z][A-Z0-9_]*):\?[^}]+\}:(\d+):(\d+)\Z")

#: A service name used as a host in a connection string or an endpoint.
_HOST_IN_VALUE: Final = re.compile(r"(?:@|://)([a-z][a-z0-9-]*)(?::|/|$)")


def overlays_for(files: Sequence[str]) -> tuple[str, ...]:
    """The split overlays a profile composing these files needs, in `-f` order."""
    return tuple(
        name
        for name, condition in OVERLAY_CONDITIONS.items()
        if condition is None or condition in files
    )


def _services(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    block = document.get("services") or {}
    return {str(name): body for name, body in block.items() if isinstance(body, Mapping)}


def _environment(body: Mapping[str, Any]) -> dict[str, str]:
    environment = body.get("environment") or {}
    if isinstance(environment, Mapping):
        return {str(key): str(value) for key, value in environment.items()}
    found: dict[str, str] = {}
    for entry in environment:
        key, _, value = str(entry).partition("=")
        found[key] = value
    return found


def profile_services(files: ComposeFiles) -> tuple[str, ...]:
    """Every service these files describe or name, sorted."""
    return tuple(sorted({name for document in files.values() for name in _services(document)}))


def host_services(files: ComposeFiles, host: str) -> tuple[str, ...]:
    """The services one host starts, as the argument list to `docker compose up`."""
    if host not in HOSTS:
        msg = f"no host named {host!r}; the split has {list(HOSTS)}"
        raise ValueError(msg)
    every = profile_services(files)
    if host == "data":
        return tuple(one for one in every if one in DATA_TIER)
    return tuple(one for one in every if one not in DATA_TIER)


def published_port_gaps(overlays: ComposeFiles) -> tuple[str, ...]:
    """Every published port that is not one data-tier pooler or store on the required address."""
    findings: list[str] = []
    for name in overlays:
        for service, body in _services(overlays[name]).items():
            entries = [str(one) for one in body.get("ports") or ()]
            if not entries:
                continue
            if service not in PUBLISHED:
                findings.append(
                    f"{name}: {service!r} publishes {entries}. "
                    + (
                        THE_DATA_HOST_PUBLISHES_POOLERS_AND_NEVER_THE_DATABASE
                        if service in DATA_TIER
                        else "Only the data host publishes, and only its poolers and store."
                    )
                )
                continue
            if len(entries) != 1:
                findings.append(f"{name}: {service!r} publishes {len(entries)} ports, not one")
                continue
            matched = _REQUIRED_ADDRESS.match(entries[0])
            if matched is None or matched.group(1) != ADDRESS_VARIABLE:
                findings.append(
                    f"{name}: {service!r} publishes {entries[0]!r}. "
                    f"{A_PORT_WITH_NO_ADDRESS_IS_PUBLISHED_ON_EVERY_INTERFACE}"
                )
                continue
            wanted = PUBLISHED[service]
            if (int(matched.group(2)), int(matched.group(3))) != wanted:
                findings.append(
                    f"{name}: {service!r} publishes {matched.group(2)}:{matched.group(3)} and "
                    f"the split expects {wanted[0]}:{wanted[1]}"
                )
    return tuple(findings)


def application_change_gaps(overlays: ComposeFiles) -> tuple[str, ...]:
    """Every setting an overlay changes that is not an address. The M36.1.4.2 property."""
    findings: list[str] = []
    for name in overlays:
        document = overlays[name]
        extra_top = sorted(set(document) - {"services"})
        if extra_top:
            findings.append(f"{name} declares {extra_top} beside its services")
        for service, body in _services(document).items():
            allowed = DATA_KEYS if service in DATA_TIER else APPLICATION_KEYS
            changed = sorted(set(body) - allowed)
            if changed:
                findings.append(
                    f"{name}: {service!r} changes {changed}. "
                    f"{THE_OVERLAY_CHANGES_ADDRESSES_AND_NOTHING_THE_IMAGE_READS}"
                )
    return tuple(findings)


def _merged_environment(files: ComposeFiles, overlays: ComposeFiles) -> dict[str, dict[str, str]]:
    """Each service's environment after the overlays, merged by key as compose merges it."""
    merged: dict[str, dict[str, str]] = {}
    for documents in (files, overlays):
        for name in documents:
            for service, body in _services(documents[name]).items():
                merged.setdefault(service, {}).update(_environment(body))
    return merged


def split_gaps(files: ComposeFiles, overlays: ComposeFiles) -> tuple[str, ...]:
    """Every way this profile, split by these overlays, would still not work across two hosts.

    Three questions. Does an application-host service still name a data-host service, which
    resolves on nothing once the two are on different machines. Does a rewritten address point
    at the port that belongs to the service it used to name, so a queue does not land on the
    transaction pooler. And are the overlays the ones the profile needs, no more and no fewer.
    """
    findings: list[str] = []
    wanted = overlays_for(tuple(files))
    if tuple(overlays) != wanted:
        findings.append(
            f"the profile needs the overlays {list(wanted)} and was given {list(overlays)}"
        )

    before = _merged_environment(files, {})
    after = _merged_environment(files, overlays)
    application = set(host_services(files, "application"))
    for service in sorted(application):
        for key, value in sorted(after.get(service, {}).items()):
            named = {one for one in _HOST_IN_VALUE.findall(value) if one in DATA_TIER}
            if named:
                findings.append(
                    f"{service!r} {key} still names {sorted(named)}, which is on the data host "
                    "and resolves on nothing from the application host"
                )
                continue
            original = before.get(service, {}).get(key, "")
            was = {one for one in _HOST_IN_VALUE.findall(original) if one in DATA_TIER}
            if not was or original == value:
                continue
            if ADDRESS not in value:
                findings.append(f"{service!r} {key} moved somewhere other than {ADDRESS_VARIABLE}")
                continue
            target = next(iter(was))
            port = PUBLISHED.get(target, (0, 0))[0]
            tail = value.split(ADDRESS, 1)[1]
            if not tail.startswith(f":{port}"):
                findings.append(
                    f"{service!r} {key} used to reach {target!r} and now reaches port "
                    f"{tail.split('/', 1)[0].lstrip(':')!s} on the data host, which is not "
                    f"{target!r}'s {port}"
                )
            elif urlsplit(original).path != urlsplit(value.replace(ADDRESS, "host")).path:
                findings.append(f"{service!r} {key} changed database as well as host")
    return (*findings, *published_port_gaps(overlays), *application_change_gaps(overlays))


def address_refusals(address: str) -> tuple[str, ...]:
    """Why this value cannot be the data host's address, or nothing when it can.

    Accepts an IPv4 address that is not globally routable and is a real unicast address of a
    host: a private range, a WireGuard or tailnet address. Refuses IPv6, which a ports entry
    needs in brackets; the unspecified address, which is every interface; loopback, which the
    other host cannot reach; link-local and multicast; a public address; and anything that is
    not an address at all, including a hostname, because compose binds a published port to an
    address and never resolves a name for it.
    """
    try:
        parsed = ipaddress.ip_address(address.strip())
    except ValueError:
        return (f"{address!r} is not an IP address; a published port binds to an address",)
    if parsed.version == 6:
        return (
            f"{address} is an IPv6 address, and a ports entry needs one in brackets, which the "
            "overlays do not add; use the IPv4 address the private link gives this host",
        )
    if parsed.is_unspecified:
        return (
            f"{address} is every interface. "
            f"{A_PORT_WITH_NO_ADDRESS_IS_PUBLISHED_ON_EVERY_INTERFACE}",
        )
    if parsed.is_loopback:
        return (f"{address} is loopback, which the application host cannot reach",)
    if parsed.is_link_local or parsed.is_multicast:
        return (f"{address} is not an address one host gives another",)
    if parsed.is_global:
        return (
            f"{address} is a public address, so the poolers would answer the internet. "
            f"{THE_LINK_BETWEEN_THE_HOSTS_IS_NOT_ENCRYPTED_BY_THIS_PRODUCT}",
        )
    return ()


def main(argv: Sequence[str] | None = None) -> int:
    """`--check-address <address>`, or `--services <profile> <host>` read from `--in <dir>`.

    `--in` is the directory holding the profile's compose files, which is the install's own
    directory on a server and defaults to the current one. It is an argument rather than a
    setting because it describes where the command is being run, not the install.
    """
    parser = argparse.ArgumentParser(prog="python -m brain.ops.split")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-address", metavar="ADDRESS")
    group.add_argument("--services", nargs=2, metavar=("PROFILE", "HOST"))
    parser.add_argument("--in", dest="directory", default=".", metavar="DIR")
    arguments = parser.parse_args(argv)
    if arguments.check_address is not None:
        refusals = address_refusals(arguments.check_address)
        for line in refusals:
            print(line)
        if not refusals:
            print(f"{arguments.check_address} can be {ADDRESS_VARIABLE}")
        return 1 if refusals else 0
    profile, host = arguments.services
    import yaml

    directory = Path(arguments.directory)
    files = {
        name: yaml.safe_load((directory / name).read_text(encoding="utf-8")) or {}
        for name in files_for(profile)
    }
    print(" ".join(host_services(files, host)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
