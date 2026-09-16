"""What one browser run runs in: two containers and a network, made for it and then destroyed.

The architecture calls the runner untrusted, and this module is what that word costs. A runner is a
browser executing somebody else's JavaScript while holding a session on a client's system. The
design assumes it is compromised on its first page and asks what it can then reach, keep or leave
behind. Everything here is a Docker Engine API body, built from a run id, the run's origins and the
application image, and `sandbox_gaps` re-reads those bodies before `brain.browsing.launcher` sends
any of them, so a body with a hole in it is refused before a container exists.

**One run, one set, never reused (M19.1.1).** Each run gets a network, an egress proxy and a runner,
all named from the run id and labelled with it, created when the run starts and removed when it
ends. The rejected shape was a pool of long-lived runners restarted between runs: a restarted
container is the same container, and whatever a page managed to leave in it, a cache, a service
worker, a profile, a file, is there for the next company's session. Nothing here has a volume, so
there is nowhere for a run to leave anything that outlives its container.

**The kernel a page reaches is gVisor's, not the host's (M19.1.1).** Both containers run under the
`runsc` runtime, which answers system calls in a user-space kernel. A browser exploit that escapes
Chromium's own sandbox then escapes into gVisor, which is a second, independent boundary, rather
than into the host kernel every other service shares. It needs no `/dev/kvm`, which is why it is
the default the architecture chose for hosts that are not ours.

**The only writable storage is memory, sized under the memory cap (M19.1.5).** The root filesystem
is read-only, the browser's home, its temporary directory and its shared memory are tmpfs, and
tmpfs pages are charged to the container's memory cgroup. So `Caps` refuses a set of tmpfs sizes
that, full, would leave less than the browser's floor under the cap: a page that fills a download
directory should hit a full disk, not kill the browser mid-write with the OOM killer and leave the
run's last action unknown. When the container is removed the memory is freed and there is nothing
to delete.

**A network per run, with no gateway, and one other member (M19.1.6, M19.3.5).** The run's network
is `internal`, so Docker gives it no route out. The egress proxy is the only other container on it,
and it alone also joins `brain-browser-egress`, which has a route out and has inter-container
traffic switched off, so two runs' proxies cannot reach each other and no runner can reach
anything but its own proxy. The proxy is given the run's origins at creation and runs
`brain.browsing.egress_addon`, which refuses everything else. A runner that ignores its proxy
variables reaches nothing, rather than reaching everything.

**Caps on memory, processes and CPU per session (M19.6.4).** Memory with swap equal to it, so a
runner cannot page its way past the cap; a process limit, because Chromium forks per site and a
page can make it fork more; and a CPU quota, so one page spinning cannot starve the host. The
figures are judgements, not measurements, and each says so beside it.

**What this does not decide, and why.** Whether Chromium's own sandbox can run under gVisor is not
known on this machine, so the runner image starts it without and relies on gVisor, which
`ops/browser/REHEARSAL.md` asks to be checked first. Whether the Docker host has `runsc` installed
is a property of a server, and a body naming a runtime the daemon does not have is refused by the
daemon at creation, which is the loud outcome. None of these bodies has been sent to a daemon.

Task ids: M19.1.1, M19.1.5, M19.1.6, M19.3.5, M19.6.4
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from brain.browsing.egress_addon import Egress, parse_allowlist

#: The runtime every container here runs under. gVisor's OCI runtime, by the name Docker registers.
RUNTIME: Final = "runsc"

#: The label naming the run a container or network belongs to. The launcher sweeps by it.
RUN_LABEL: Final = "brain.browser.run"

#: The label naming what a container is for within its run.
ROLE_LABEL: Final = "brain.browser.role"

#: The one network with a route out, shared by every run's proxy and by nothing else.
EGRESS_NETWORK: Final = "brain-browser-egress"

#: The published proxy image, pinned. Unverified against a registry on this machine: see REHEARSAL.
EGRESS_IMAGE: Final = "mitmproxy/mitmproxy:11.1.3"

#: The name the runner reaches its proxy by, on the run's own network, and the port it listens on.
EGRESS_ALIAS: Final = "egress"
EGRESS_PORT: Final = 8080
PROXY_ADDRESS: Final = f"http://{EGRESS_ALIAS}:{EGRESS_PORT}"

#: What the runner image is called beside the application image it is built with.
RUNNER_TAG_SUFFIX: Final = "-browser"

#: The user the runner runs as, which the Playwright base image creates.
RUNNER_USER: Final = "pwuser"

#: The file in the runner image that opens the browser and calls `brain.browsing.runner.drive`.
RUNNER_ENTRY: Final = "/opt/brain-runner/playwright_browser.py"

#: The user the proxy runs as, which the mitmproxy image creates.
EGRESS_USER: Final = "mitmproxy"

#: A run id, as it may appear in a container name. Refused rather than rewritten, so two run ids
#: can never be folded onto one name.
RUN_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")

#: The environment variable the addon's source reaches the proxy container in.
ADDON_VARIABLE: Final = "BRAIN_EGRESS_ADDON"

#: Mebibytes to bytes.
MIB: Final = 1024 * 1024

#: The temporary directory inside a container, which is a tmpfs of that container's own and never
#: the host's temporary directory.
CONTAINER_TMP: Final = "/tmp"  # noqa: S108

#: Why a pool of restarted runners was rejected.
A_RESTARTED_CONTAINER_IS_THE_SAME_CONTAINER: Final = (
    "Restarting a runner between runs keeps its container, and a container keeps whatever a page "
    "could write into it: a profile, a cache, a service worker, a file in a directory somebody "
    "forgot was writable. The next run, possibly for somebody else, starts on top of it. A run "
    "gets containers made for it, from a read-only image, and they are removed when it ends."
)

#: Why tmpfs sizes are held under the memory cap.
TMPFS_IS_MEMORY: Final = (
    "tmpfs pages are charged to the container's memory cgroup. A tmpfs sized at or near the cap "
    "lets a page fill it and have the kernel kill the browser mid-action, which leaves the last "
    "write unknown. Sized under the cap with room for the browser, a full tmpfs is a full disk."
)


class SandboxError(Exception):
    """A sandbox was asked for in terms that cannot be made safe."""


@dataclass(frozen=True)
class Caps:
    """The ceilings on one container, and the floor its own process needs under them."""

    memory_mib: int
    millicpus: int
    pids: int
    #: Mount point to size in MiB, for every tmpfs the container gets.
    tmpfs: tuple[tuple[str, int], ...]
    shm_mib: int
    #: What the process itself needs with every tmpfs full. A judgement, stated beside each use.
    floor_mib: int

    def __post_init__(self) -> None:
        for name in ("memory_mib", "millicpus", "pids", "shm_mib", "floor_mib"):
            if getattr(self, name) < 1:
                msg = f"a container cap {name} of {getattr(self, name)} is no cap at all"
                raise SandboxError(msg)
        if any(size < 1 for _, size in self.tmpfs):
            msg = "a tmpfs of no size is a mount that refuses every write"
            raise SandboxError(msg)
        if self.writable_mib() + self.floor_mib > self.memory_mib:
            msg = (
                f"{self.writable_mib()} MiB of tmpfs and shared memory plus a {self.floor_mib} MiB "
                f"floor does not fit under {self.memory_mib} MiB. {TMPFS_IS_MEMORY}"
            )
            raise SandboxError(msg)

    def writable_mib(self) -> int:
        """Everything a full container holds in memory that is not its process."""
        return sum(size for _, size in self.tmpfs) + self.shm_mib


#: One browser session. 768 MiB is the floor judged for Chromium with one page and its renderer,
#: not measured: nothing here has run Chromium under gVisor. One CPU and 512 processes are
#: judgements in the same register. The total is held by test against the architecture's own
#: sizing, which gives browsers a quarter of the machine at most, applied to the twelve gigabytes
#: the global budget of two sessions in `brain.ops.admission` was written for.
RUNNER_CAPS: Final = Caps(
    memory_mib=1280,
    millicpus=1000,
    pids=512,
    tmpfs=((CONTAINER_TMP, 64), (f"/home/{RUNNER_USER}", 192)),
    shm_mib=128,
    floor_mib=768,
)

#: One run's proxy. A floor of 96 MiB for mitmproxy holding one browser's connections, judged.
EGRESS_CAPS: Final = Caps(
    memory_mib=256,
    millicpus=250,
    pids=64,
    tmpfs=((CONTAINER_TMP, 16), (f"/home/{EGRESS_USER}", 16)),
    shm_mib=16,
    floor_mib=96,
)


@dataclass(frozen=True)
class Container:
    """One container to create: its name and the body the Engine API is sent."""

    name: str
    body: dict[str, Any]


@dataclass(frozen=True)
class RunSandbox:
    """Everything one run is created in, in the order it is created."""

    run_id: str
    network: dict[str, Any]
    egress: Container
    runner: Container
    origins: tuple[str, ...]

    @property
    def network_name(self) -> str:
        return str(self.network["Name"])


def runner_image_for(app_image: str) -> str:
    """The runner image built with this release of the application, found by its tag.

    One variable selects every container of the product, and this is how the runner obeys it: the
    runner is published as the application's tag with `-browser` on the end. A digest reference
    has no tag to extend and an untagged reference names whatever was pushed last, so both refuse.
    """
    last = app_image.rsplit("/", 1)[-1]
    if "@" in app_image or ":" not in last or not last.rsplit(":", 1)[1]:
        msg = (
            f"the application image {app_image!r} carries no tag, so there is no release to find "
            "the runner image beside"
        )
        raise SandboxError(msg)
    return f"{app_image}{RUNNER_TAG_SUFFIX}"


def network_body(run_id: str) -> dict[str, Any]:
    """The run's own network. Internal, so Docker gives it no gateway."""
    return {
        "Name": f"brain-browser-{run_id}",
        "Driver": "bridge",
        "Internal": True,
        "Attachable": False,
        "Labels": {RUN_LABEL: run_id},
    }


def egress_network_body() -> dict[str, Any]:
    """The shared network with a route out, with inter-container traffic switched off."""
    return {
        "Name": EGRESS_NETWORK,
        "Driver": "bridge",
        "Internal": False,
        "Attachable": False,
        "Labels": {RUN_LABEL: "egress"},
        "Options": {"com.docker.network.bridge.enable_icc": "false"},
    }


def _host_config(caps: Caps, network: str) -> dict[str, Any]:
    """The isolation both containers share, from their caps and the run's network."""
    return {
        "Runtime": RUNTIME,
        "NetworkMode": network,
        "ReadonlyRootfs": True,
        "Tmpfs": {path: f"rw,noexec,nosuid,nodev,size={size}m" for path, size in caps.tmpfs},
        "ShmSize": caps.shm_mib * MIB,
        "Memory": caps.memory_mib * MIB,
        "MemorySwap": caps.memory_mib * MIB,
        "NanoCpus": caps.millicpus * 1_000_000,
        "PidsLimit": caps.pids,
        "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges"],
        "Privileged": False,
        "AutoRemove": True,
        "IpcMode": "private",
        "Init": True,
    }


def addon_source() -> str:
    """The proxy's rule as this repository holds it, before a run's origins are added."""
    return (Path(__file__).with_name("egress_addon.py")).read_text(encoding="utf-8")


def addon_script(origins: tuple[str, ...]) -> str:
    """The program one run's proxy loads: the rule, and the one line that gives it the origins.

    The origins are a Python literal of a JSON list, so they are fixed when the proxy loads the
    file and there is nowhere at run time they are read from.
    """
    line = f"addons = [{Egress.__name__}(parse_allowlist({json.dumps(list(origins))!r}))]"
    return f"{addon_source()}\n\n{line}\n"


def allowlist_in(script: str) -> frozenset[tuple[str, str, int]]:
    """The origins a proxy script constructs its addon with, read off the source, not run.

    Empty unless the script ends by assigning exactly one `Egress` built from one string literal,
    so a script that builds its list any other way is refused by the gap check rather than trusted.
    """
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return frozenset()
    assigned = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(one, ast.Name) and one.id == "addons" for one in node.targets)
    ]
    if len(assigned) != 1 or tree.body[-1] is not assigned[0]:
        return frozenset()
    value = assigned[0].value
    if not isinstance(value, ast.List) or len(value.elts) != 1:
        return frozenset()
    call = value.elts[0]
    if not (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == Egress.__name__
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Call)
        and isinstance(call.args[0].func, ast.Name)
        and call.args[0].func.id == parse_allowlist.__name__
        and len(call.args[0].args) == 1
        and isinstance(call.args[0].args[0], ast.Constant)
        and isinstance(call.args[0].args[0].value, str)
    ):
        return frozenset()
    return parse_allowlist(call.args[0].args[0].value)


def sandbox_for(run_id: str, *, origins: frozenset[str], app_image: str) -> RunSandbox:
    """The network, proxy and runner for one run, built and not yet created."""
    if not RUN_ID_RE.match(run_id):
        msg = f"run id {run_id!r} cannot name a container without being rewritten"
        raise SandboxError(msg)
    if not origins:
        msg = f"run {run_id!r} allows no origin, so its proxy would refuse every request"
        raise SandboxError(msg)
    network = network_body(run_id)
    name = str(network["Name"])
    listed = tuple(sorted(origins))
    script = (
        f'printf "%s" "${ADDON_VARIABLE}" > /tmp/egress_addon.py && exec mitmdump '
        f"--listen-port {EGRESS_PORT} --set connection_strategy=lazy -s /tmp/egress_addon.py"
    )
    egress = Container(
        name=f"{name}-egress",
        body={
            "Image": EGRESS_IMAGE,
            "User": EGRESS_USER,
            "Entrypoint": ["sh", "-c"],
            "Cmd": [script],
            "Env": [f"{ADDON_VARIABLE}={addon_script(listed)}"],
            "Labels": {RUN_LABEL: run_id, ROLE_LABEL: "egress"},
            "HostConfig": _host_config(EGRESS_CAPS, name),
            "NetworkingConfig": {"EndpointsConfig": {name: {"Aliases": [EGRESS_ALIAS]}}},
        },
    )
    runner = Container(
        name=f"{name}-runner",
        body={
            "Image": runner_image_for(app_image),
            "User": RUNNER_USER,
            "Entrypoint": ["python"],
            "Cmd": [RUNNER_ENTRY],
            "Env": [
                f"HTTPS_PROXY={PROXY_ADDRESS}",
                f"HTTP_PROXY={PROXY_ADDRESS}",
                "NO_PROXY=",
                f"HOME=/home/{RUNNER_USER}",
                "PYTHONUNBUFFERED=1",
            ],
            "Labels": {RUN_LABEL: run_id, ROLE_LABEL: "runner"},
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": False,
            "OpenStdin": True,
            "StdinOnce": True,
            "Tty": False,
            "HostConfig": _host_config(RUNNER_CAPS, name),
        },
    )
    return RunSandbox(run_id=run_id, network=network, egress=egress, runner=runner, origins=listed)


#: Host configuration keys that would give a container something beyond its own tmpfs and network.
FORBIDDEN_HOST_KEYS: Final = (
    "Binds",
    "Mounts",
    "VolumesFrom",
    "Devices",
    "PortBindings",
    "PublishAllPorts",
    "CapAdd",
    "PidMode",
    "UsernsMode",
    "CgroupParent",
    "ExtraHosts",
    "Links",
)

#: Environment names that would hand a runner something it must not hold.
SECRET_SHAPED_ENV: Final = ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL", "DATABASE", "VAULT")


def sandbox_gaps(sandbox: RunSandbox) -> tuple[str, ...]:
    """Every way these bodies would let a run reach, keep or leave something. Empty when sound."""
    gaps: list[str] = []
    network = sandbox.network
    name = sandbox.network_name
    if network.get("Internal") is not True:
        gaps.append(f"network {name} is not internal, so the runner has a route out")
    if network.get("Labels", {}).get(RUN_LABEL) != sandbox.run_id:
        gaps.append(f"network {name} is not labelled with its run, so no sweep would find it")
    for role, container, caps in (
        ("egress", sandbox.egress, EGRESS_CAPS),
        ("runner", sandbox.runner, RUNNER_CAPS),
    ):
        gaps.extend(_container_gaps(role, container, caps, name, sandbox.run_id))
    runner_env = sandbox.runner.body.get("Env", [])
    if f"HTTPS_PROXY={PROXY_ADDRESS}" not in runner_env:
        gaps.append("the runner is not pointed at its proxy")
    for entry in runner_env:
        variable = str(entry).split("=", 1)[0].upper()
        if any(shape in variable for shape in SECRET_SHAPED_ENV):
            gaps.append(f"the runner's environment carries {variable}, which it must never hold")
    if sandbox.runner.body.get("NetworkingConfig"):
        gaps.append("the runner joins a network beyond its run's own")
    endpoints = sandbox.egress.body.get("NetworkingConfig", {}).get("EndpointsConfig", {})
    if set(endpoints) != {name}:
        gaps.append("the proxy is created on a network other than its run's")
    allowed = allowlist_in(_env_value(sandbox.egress.body, ADDON_VARIABLE) or "")
    expected = parse_allowlist(json.dumps(list(sandbox.origins)))
    if not expected or allowed != expected:
        gaps.append("the proxy's allowlist is not exactly the run's origins")
    return tuple(gaps)


def _container_gaps(
    role: str, container: Container, caps: Caps, network: str, run_id: str
) -> list[str]:
    host = container.body.get("HostConfig", {})
    gaps: list[str] = []
    if host.get("Runtime") != RUNTIME:
        gaps.append(f"the {role} does not run under {RUNTIME}, so a page reaches the host kernel")
    if host.get("ReadonlyRootfs") is not True:
        gaps.append(f"the {role}'s root filesystem is writable, so a run can leave something")
    if host.get("NetworkMode") != network:
        gaps.append(f"the {role} is not on its run's network")
    if host.get("Privileged") is not False:
        gaps.append(f"the {role} is privileged")
    if host.get("CapDrop") != ["ALL"]:
        gaps.append(f"the {role} keeps Linux capabilities")
    if "no-new-privileges" not in host.get("SecurityOpt", []):
        gaps.append(f"the {role} can gain privileges through a setuid binary")
    if host.get("AutoRemove") is not True:
        gaps.append(f"the {role} survives its own exit")
    for key in FORBIDDEN_HOST_KEYS:
        if host.get(key):
            gaps.append(f"the {role} is given {key}, which reaches beyond its own container")
    memory = caps.memory_mib * MIB
    if host.get("Memory") != memory or host.get("MemorySwap") != memory:
        gaps.append(f"the {role}'s memory is not capped at {caps.memory_mib} MiB without swap")
    if not host.get("NanoCpus") or not host.get("PidsLimit"):
        gaps.append(f"the {role} has no CPU or process cap")
    tmpfs = host.get("Tmpfs", {})
    if set(tmpfs) != {path for path, _ in caps.tmpfs}:
        gaps.append(f"the {role}'s writable mounts are not exactly its declared tmpfs")
    if container.body.get("Volumes"):
        gaps.append(f"the {role} declares a volume, which outlives the container")
    if container.body.get("Labels", {}).get(RUN_LABEL) != run_id:
        gaps.append(f"the {role} is not labelled with its run")
    return gaps


def _env_value(body: dict[str, Any], variable: str) -> str | None:
    for entry in body.get("Env", []):
        name, _, value = str(entry).partition("=")
        if name == variable:
            return value
    return None
