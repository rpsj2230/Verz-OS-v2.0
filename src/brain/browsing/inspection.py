"""What the daemon says a run was created as, set against what the launcher asked for.

`brain.browsing.sandbox.sandbox_gaps` reads the bodies the launcher is about to send, and a body is
a request. Everything the product claims about isolation (gVisor, a root filesystem nothing can
write, a network with no gateway, a proxy that is the only member with a route out) is a claim about
what the **daemon** made of that request, and the two differ whenever a daemon ignores a field it
does not know, applies a default the body did not mention, or has a runtime registered under another
name. This module reads the daemon's own description of the three things one run is made of and
holds it to the same expectations, so a launcher whose request was perfect and whose result was not
is a finding and not a pass.

**It is the same expectations, written once more, and that is deliberate.** `sandbox_gaps` checks
the request and this checks the answer; both are built from the constants `sandbox` declares
(`RUNTIME`, `RUNNER_CAPS`, `EGRESS_CAPS`, `EGRESS_NETWORK`), so a change to a cap moves both. What
they do not share is the parsing: a body is the product's own dictionary and an inspection is
Docker's, with its own spelling (`Tmpfs` is a mapping of path to options, a mount is a list of
typed entries, a network is a mapping of names to endpoints), and reading it is where a wrong
assumption would sit.

**An answer that cannot be read is a gap, never a pass.** A missing field is `unknown` and not the
safe value, because the daemon omitting `ReadonlyRootfs` is not the daemon saying the root is
read-only. Every field is looked up and none is defaulted to what the product wanted.

**Nothing here names a container, an image or a path of a company's.** The messages are fixed
sentences about roles, so a rehearsal's report can be served on a public page without carrying what
it read.

Rejected: trusting the launcher's own record of what it created. It is the party that made the
request, and a record of a request is the thing this exists not to take for an answer.

Task ids: M19.1.1, M19.1.5, M19.1.6, M19.3.5, M19.6.4
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from brain.browsing.sandbox import (
    EGRESS_CAPS,
    EGRESS_NETWORK,
    MIB,
    RUN_LABEL,
    RUNNER_CAPS,
    RUNTIME,
    Caps,
    Container,
    RunSandbox,
)

#: The mount type a tmpfs is reported as. Anything else is something the run could keep or reach.
TMPFS_MOUNT: Final = "tmpfs"

#: Why an unreadable field is a finding.
A_FIELD_THE_DAEMON_OMITTED_IS_NOT_THE_SAFE_VALUE: Final = (
    "A daemon that leaves out ReadonlyRootfs has not said the root filesystem is read-only, and "
    "one that leaves out the runtime has not said it is gVisor. Each field is read as it came, "
    "and one that did not come is a gap."
)


@dataclass(frozen=True)
class ContainerFacts:
    """One container as the daemon described it, reduced to what isolation depends on.

    Every field is the daemon's answer. `None` in a field that has one means the daemon did not give
    it, which `observed_gaps` reports and never reads as the safe value.
    """

    runtime: str | None
    read_only: bool | None
    privileged: bool | None
    cap_drop: tuple[str, ...] | None
    memory: int | None
    swap: int | None
    nano_cpus: int | None
    pids: int | None
    #: Where the container can write, which is every tmpfs and nothing else.
    writable: tuple[str, ...]
    #: Every mount that is not a tmpfs, as its type. A bind or a volume is something that outlives
    #: the container or reaches the host.
    reaches: tuple[str, ...]
    #: Every network the container is on, by name.
    networks: tuple[str, ...]
    run: str | None


@dataclass(frozen=True)
class NetworkFacts:
    """One network as the daemon described it."""

    name: str
    internal: bool | None
    run: str | None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def container_facts(raw: Mapping[str, Any]) -> ContainerFacts:
    """A `GET /containers/{id}/json` answer as the facts isolation depends on."""
    host = raw.get("HostConfig")
    host = host if isinstance(host, Mapping) else {}
    config = raw.get("Config")
    config = config if isinstance(config, Mapping) else {}
    labels = config.get("Labels")
    labels = labels if isinstance(labels, Mapping) else {}
    drop = host.get("CapDrop")
    mounts = raw.get("Mounts")
    tmpfs = host.get("Tmpfs")
    binds = host.get("Binds")
    settings = raw.get("NetworkSettings")
    networks = settings.get("Networks") if isinstance(settings, Mapping) else None
    typed = [
        str(one.get("Type", "unknown"))
        for one in (mounts if isinstance(mounts, list) else [])
        if isinstance(one, Mapping) and one.get("Type") != TMPFS_MOUNT
    ]
    runtime = host.get("Runtime")
    run = labels.get(RUN_LABEL)
    return ContainerFacts(
        runtime=runtime if isinstance(runtime, str) else None,
        read_only=_flag(host.get("ReadonlyRootfs")),
        privileged=_flag(host.get("Privileged")),
        cap_drop=(
            tuple(sorted(str(one).upper() for one in drop)) if isinstance(drop, list) else None
        ),
        memory=_int(host.get("Memory")),
        swap=_int(host.get("MemorySwap")),
        nano_cpus=_int(host.get("NanoCpus")),
        pids=_int(host.get("PidsLimit")),
        writable=tuple(sorted(tmpfs)) if isinstance(tmpfs, Mapping) else (),
        reaches=tuple(
            sorted([*typed, *(["bind"] * len(binds) if isinstance(binds, list) else [])])
        ),
        networks=tuple(sorted(networks)) if isinstance(networks, Mapping) else (),
        run=run if isinstance(run, str) else None,
    )


def network_facts(raw: Mapping[str, Any]) -> NetworkFacts:
    """A `GET /networks/{id}` answer as the facts isolation depends on."""
    labels = raw.get("Labels")
    labels = labels if isinstance(labels, Mapping) else {}
    run = labels.get(RUN_LABEL)
    return NetworkFacts(
        name=str(raw.get("Name", "")),
        internal=_flag(raw.get("Internal")),
        run=run if isinstance(run, str) else None,
    )


def observed_gaps(
    run_id: str, *, network: NetworkFacts, runner: ContainerFacts, egress: ContainerFacts
) -> tuple[str, ...]:
    """Every way what the daemon made of a run is weaker than the product said it would be.

    Empty when the daemon's own account of the network, the runner and the proxy matches the
    isolation the product describes. The runner is on its run's network and no other; the proxy is
    on that network and on the one shared network with a route out; neither can write anywhere but
    memory.
    """
    gaps: list[str] = []
    if network.internal is not True:
        gaps.append("the run's network is not internal, so its runner has a route out")
    if network.run != run_id:
        gaps.append("the run's network does not carry the run's label, so no sweep would find it")
    for role, facts, caps in (("runner", runner, RUNNER_CAPS), ("proxy", egress, EGRESS_CAPS)):
        gaps.extend(_container_gaps(role, facts, caps, run_id))
    if set(runner.networks) != {network.name}:
        gaps.append("the runner is on a network other than its run's, or on none")
    if set(egress.networks) != {network.name, EGRESS_NETWORK}:
        gaps.append("the proxy is not on exactly its run's network and the shared egress network")
    return tuple(gaps)


def _container_gaps(role: str, facts: ContainerFacts, caps: Caps, run_id: str) -> list[str]:
    gaps: list[str] = []
    if facts.runtime != RUNTIME:
        gaps.append(f"the {role} is not running under {RUNTIME}, so a page reaches the host kernel")
    if facts.read_only is not True:
        gaps.append(f"the {role}'s root filesystem is not read-only")
    if facts.privileged is not False:
        gaps.append(f"the {role} is privileged or its privilege was not reported")
    if facts.cap_drop != ("ALL",):
        gaps.append(f"the {role} keeps Linux capabilities or its capabilities were not reported")
    memory = caps.memory_mib * MIB
    if facts.memory != memory or facts.swap != memory:
        gaps.append(f"the {role}'s memory is not capped at {caps.memory_mib} MiB without swap")
    if facts.nano_cpus != caps.millicpus * 1_000_000:
        gaps.append(f"the {role}'s processor cap is not the one the product sets")
    if facts.pids != caps.pids:
        gaps.append(f"the {role}'s process cap is not the one the product sets")
    if set(facts.writable) != {path for path, _ in caps.tmpfs}:
        gaps.append(f"the {role} can write somewhere other than its own tmpfs")
    if facts.reaches:
        gaps.append(f"the {role} has a bind or a volume, which outlives it or reaches the host")
    if facts.run != run_id:
        gaps.append(f"the {role} does not carry the run's label, so no sweep would find it")
    return gaps


def faithful_description(
    box: RunSandbox, *, runner_networks: tuple[str, ...] | None = None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The network, runner and proxy descriptions a daemon that did exactly as asked would give.

    In Docker's own spelling, built from the bodies of a `RunSandbox`. It is what the install
    check measures the parse and the comparison against before it asks a real daemon, so a
    comparison that never finds a gap, or a parse that cannot read the spelling, is found on every
    install and not only on one with a daemon. It is a model of the daemon and never a source of
    facts about it: nothing reads it as an answer.
    """

    def container(made: Container, networks: tuple[str, ...]) -> dict[str, Any]:
        host = made.body["HostConfig"]
        return {
            "Name": f"/{made.name}",
            "Config": {"Labels": dict(made.body["Labels"])},
            "HostConfig": {
                key: host.get(key)
                for key in (
                    "Runtime",
                    "ReadonlyRootfs",
                    "Privileged",
                    "CapDrop",
                    "Memory",
                    "MemorySwap",
                    "NanoCpus",
                    "PidsLimit",
                    "Tmpfs",
                    "Binds",
                )
            },
            "Mounts": [{"Type": TMPFS_MOUNT, "Destination": path} for path in host["Tmpfs"]],
            "NetworkSettings": {"Networks": {name: {} for name in networks}},
        }

    named = box.network_name
    network = {
        "Name": named,
        "Internal": box.network["Internal"],
        "Labels": dict(box.network["Labels"]),
    }
    return (
        network,
        container(box.runner, (named,) if runner_networks is None else runner_networks),
        container(box.egress, (named, EGRESS_NETWORK)),
    )
