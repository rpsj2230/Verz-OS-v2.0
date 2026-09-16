"""The one process that may start a runner, and the one channel between a run and the system.

`brain.browsing.sandbox` says what a run is created in. This module creates it, relays the run's
line protocol, and removes it. It is its own service, `browser-launcher` in
`docker-compose.browser.yml`, because it is the only thing in the product that holds the Docker
socket, and whatever holds the Docker socket can do anything on the host.

**So it holds nothing else, and it accepts almost nothing.** No database address, no vault token, no
provider key, no route out: it sits on one internal network shared with the worker. What it accepts
is one line, a `brain.browsing.wire` start message, and it builds every Engine body itself from that
message through `sandbox_for`, then refuses to send any body `sandbox_gaps` finds a hole in. A
compromised worker can ask it to start a sandbox for a set of origins. It cannot ask it for a
container with a volume, a privileged flag, the host network or another runtime, because there is
no field in the request to put one in. The rejected alternatives were handing the worker the socket,
which puts root on the host one parser away from model output, and a generic socket proxy filtering
API paths, which admits `POST /containers/create` with any body at all.

**A run id is launched once in a launcher's life, and spent before anything is created.** A launch
that fails half way still spends its id, so a retry is a new run with a new envelope, which is the
rule `brain.browsing.runner` states from the other side: a run is never resumed.

**Teardown attempts every removal, whatever failed before it.** The runner, then the proxy, then the
network, each attempted even when an earlier one raised, and the failures reported together. A
teardown that stopped at its first error would leave a network or a proxy with a route out behind,
labelled and orphaned. At start the launcher removes everything carrying the run label, because a
launcher that died mid-run left exactly that.

**The channel is the container's standard input and output, and nothing else.** The launcher
attaches to the runner before starting it, so no line is lost, and relays lines in both directions
with the same bound `brain.browsing.wire` applies. There is no network path from a runner to the
launcher or the worker: a compromised page reaches the proxy, and the proxy reaches the run's
origins.

**Ready means the daemon answers and has gVisor.** `--check` asks the daemon for its runtimes and
fails unless `runsc` is registered, so a host where gVisor was never installed shows an unhealthy
launcher rather than a healthy one whose every run is refused at creation.

Not built, and stated: the worker side of the channel, which would compile an envelope, open a
connection here, send the start line, resolve credentials at the action boundary, and record the
transcript through `brain.browsing.recording`. Nothing in the repository calls this service yet.
None of the socket code below has run against a Docker daemon; the decisions it makes are tested and
the plumbing is the rehearsal in `ops/browser/REHEARSAL.md`.

Task ids: M19.1.1, M19.1.5, M19.1.6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

import httpx

from brain.browsing.sandbox import (
    EGRESS_NETWORK,
    RUN_LABEL,
    RUNTIME,
    RunSandbox,
    egress_network_body,
    sandbox_for,
    sandbox_gaps,
)
from brain.browsing.wire import MAX_LINE_BYTES, Kind, WireError, decode

#: Where the launcher listens on its internal network. Fixed, because it is a service name and a
#: port inside the product, not a value that differs between installs.
LISTEN_PORT: Final = 7300

#: The compose file that deploys the launcher, composed after a profile's own files.
OVERLAY: Final = "docker-compose.browser.yml"

#: The compose file a profile must already compose for the overlay to have a worker to join.
WORKER_FILE: Final = "docker-compose.worker.yml"


def overlays_for(files: Sequence[str]) -> tuple[str, ...]:
    """The browser overlay for a profile that runs the worker, and nothing for one that does not.

    Lite has no worker, and the overlay adds a network to the worker, so composed onto lite it
    would declare a service with no image. Decided by the file name, as `brain.ops.tunnel` decides
    its own overlays.
    """
    return (OVERLAY,) if WORKER_FILE in files else ()


#: The Docker socket as it is mounted into the launcher.
DOCKER_SOCKET: Final = "/var/run/docker.sock"

#: The Engine API version every request names, so a daemon upgrade cannot change a body's meaning.
API_VERSION: Final = "v1.44"

#: Why the launcher and not the worker holds the socket.
WHOEVER_HOLDS_THE_SOCKET_HOLDS_THE_HOST: Final = (
    "The Docker socket creates containers with any mount, any network and any privilege, so the "
    "process holding it is root on the host in all but name. The worker parses model output and "
    "resolves credentials; the launcher parses one start line and builds every body itself. Only "
    "the second is small enough to hold the socket."
)

#: Why every removal is attempted.
A_TEARDOWN_THAT_STOPS_AT_ITS_FIRST_ERROR_LEAVES_A_ROUTE_OUT: Final = (
    "The proxy is the member of a run with a route out. A teardown that raised on the runner and "
    "stopped would leave the proxy running with the run's allowlist and nobody using it, and the "
    "network with it. So each removal is attempted and the failures are reported together."
)


class LauncherError(Exception):
    """A run could not be started, relayed or removed as asked."""


class EngineError(Exception):
    """The Docker daemon refused or could not be reached."""


class Engine(Protocol):
    """The Docker Engine API calls a launcher makes, and no others."""

    def create_network(self, body: Mapping[str, Any]) -> str:
        """Create a network and return its id."""
        ...

    def create_container(self, name: str, body: Mapping[str, Any]) -> str:
        """Create a container, not started, and return its id."""
        ...

    def connect(self, network: str, container: str) -> None:
        """Join a created container to a second network."""
        ...

    def start(self, container: str) -> None:
        """Start a created container."""
        ...

    def remove_container(self, container: str) -> None:
        """Stop and remove a container. A container that is already gone is not an error."""
        ...

    def remove_network(self, network: str) -> None:
        """Remove a network. A network that is already gone is not an error."""
        ...

    def labelled(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Every container and every network carrying the run label, as ids."""
        ...

    def runtimes(self) -> tuple[str, ...]:
        """The OCI runtimes the daemon has registered."""
        ...


@dataclass(frozen=True)
class Launched:
    """What was created for one run, by id, in the order it must be removed."""

    run_id: str
    network: str = ""
    egress: str = ""
    runner: str = ""


@dataclass
class Launcher:
    """Creates and removes runs. Holds the set of run ids it has spent."""

    engine: Engine
    app_image: str
    spent: set[str] = field(default_factory=set)

    def launch(self, run_id: str, origins: frozenset[str]) -> Launched:
        """Create the network and proxy, start the proxy, and create the runner unstarted.

        The runner is left for the caller to start once it has attached, so its first line is not
        lost. Anything created before a failure is removed before the failure is raised.
        """
        if run_id in self.spent:
            msg = f"run {run_id!r} was launched once already, and a run is never launched twice"
            raise LauncherError(msg)
        sandbox = sandbox_for(run_id, origins=origins, app_image=self.app_image)
        refused(sandbox)
        self.spent.add(run_id)
        created = Launched(run_id=run_id)
        try:
            created = Launched(run_id, network=self.engine.create_network(sandbox.network))
            egress = self.engine.create_container(sandbox.egress.name, sandbox.egress.body)
            created = Launched(run_id, network=created.network, egress=egress)
            self.engine.connect(EGRESS_NETWORK, egress)
            self.engine.start(egress)
            runner = self.engine.create_container(sandbox.runner.name, sandbox.runner.body)
            return Launched(run_id, network=created.network, egress=egress, runner=runner)
        except BaseException:
            self.tear_down(created)
            raise

    def tear_down(self, launched: Launched) -> None:
        """Remove the runner, the proxy and the network, attempting each whatever came before."""
        failures: list[str] = []
        for container in (launched.runner, launched.egress):
            if container:
                try:
                    self.engine.remove_container(container)
                except EngineError as exc:
                    failures.append(f"container {container}: {exc}")
        if launched.network:
            try:
                self.engine.remove_network(launched.network)
            except EngineError as exc:
                failures.append(f"network {launched.network}: {exc}")
        if failures:
            msg = f"run {launched.run_id!r} was not wholly removed: {'; '.join(failures)}"
            raise LauncherError(msg)

    def sweep(self) -> int:
        """Remove every labelled container and then every labelled network. Returns how many.

        The shared egress network is labelled too and is left alone, because every future run's
        proxy joins it and removing it between runs would only make the next launch create it.
        """
        containers, networks = self.engine.labelled()
        for container in containers:
            self.engine.remove_container(container)
        removed = len(containers)
        for network in networks:
            if network == EGRESS_NETWORK:
                continue
            self.engine.remove_network(network)
            removed += 1
        return removed


def refused(sandbox: RunSandbox) -> None:
    """Raise if the bodies for a run have any gap. Called before anything is created."""
    gaps = sandbox_gaps(sandbox)
    if gaps:
        msg = f"run {sandbox.run_id!r} was not launched: {'; '.join(gaps)}"
        raise LauncherError(msg)


def runtime_gaps(runtimes: Sequence[str]) -> tuple[str, ...]:
    """Why a daemon cannot run a sandbox. Empty when gVisor is registered."""
    if RUNTIME in runtimes:
        return ()
    return (
        f"the Docker daemon has no {RUNTIME} runtime, so every run would be refused at creation; "
        "install gVisor and register it with the daemon",
    )


def start_request(line: bytes) -> tuple[str, frozenset[str]]:
    """The run id and origins from the one line a launcher accepts, or a refusal."""
    try:
        message = decode(line)
    except WireError as exc:
        raise LauncherError(str(exc)) from exc
    if message.kind is not Kind.START:
        msg = f"a launcher accepts a start message and was sent {message.kind.value}"
        raise LauncherError(msg)
    run_id = message.fields["run_id"]
    origins = message.fields["origins"]
    if not isinstance(run_id, str) or not isinstance(origins, list):
        msg = "a start message names its run or its origins in a shape that cannot be read"
        raise LauncherError(msg)
    if not all(isinstance(one, str) for one in origins):
        msg = "a start message lists an origin that is not text"
        raise LauncherError(msg)
    return run_id, frozenset(origins)


# ------------------------------------------------------------------ the attached stream
def attach_request(container: str) -> bytes:
    """The HTTP request that turns a socket into the container's standard input and output."""
    return (
        f"POST /{API_VERSION}/containers/{container}/attach?stream=1&stdin=1&stdout=1&stderr=0 "
        "HTTP/1.1\r\nHost: docker\r\nUpgrade: tcp\r\nConnection: Upgrade\r\n"
        "Content-Length: 0\r\n\r\n"
    ).encode("ascii")


#: Docker's multiplexed stream: one byte of stream, three of padding, four of length.
FRAME_HEADER: Final = struct.Struct(">BxxxL")
STDOUT: Final = 1


@dataclass
class Demultiplexer:
    """Standard output out of Docker's multiplexed attach stream, in the order it arrived."""

    pending: bytes = b""

    def feed(self, data: bytes) -> bytes:
        """Everything on standard output that `data` completes. Other streams are discarded."""
        self.pending += data
        out = b""
        while len(self.pending) >= FRAME_HEADER.size:
            stream, size = FRAME_HEADER.unpack_from(self.pending)
            end = FRAME_HEADER.size + size
            if len(self.pending) < end:
                break
            if stream == STDOUT:
                out += self.pending[FRAME_HEADER.size : end]
            self.pending = self.pending[end:]
        return out


@dataclass
class Lines:
    """Complete lines out of a byte stream, refusing one longer than a line may be."""

    pending: bytes = b""

    def feed(self, data: bytes) -> list[bytes]:
        self.pending += data
        lines: list[bytes] = []
        while (cut := self.pending.find(b"\n")) >= 0:
            lines.append(self.pending[: cut + 1])
            self.pending = self.pending[cut + 1 :]
        if len(self.pending) > MAX_LINE_BYTES or any(len(one) > MAX_LINE_BYTES for one in lines):
            msg = "a runner sent a line longer than a line may be"
            raise LauncherError(msg)
        return lines


# ------------------------------------------------------------------ the Docker adapter
class DockerEngine:
    """`Engine` over the Docker socket. Nothing here has been run against a daemon."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    @classmethod
    def over(cls, socket: str = DOCKER_SOCKET) -> DockerEngine:
        transport = httpx.HTTPTransport(uds=socket)
        return cls(httpx.Client(transport=transport, base_url="http://localhost", timeout=60.0))

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.client.request(method, f"/{API_VERSION}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise EngineError(str(exc)) from exc
        if response.status_code >= 400 and response.status_code != 404:
            raise EngineError(f"{method} {path} answered {response.status_code}")
        return response

    def create_network(self, body: Mapping[str, Any]) -> str:
        response = self._request("POST", "/networks/create", json=dict(body))
        return _id_of(response)

    def create_container(self, name: str, body: Mapping[str, Any]) -> str:
        response = self._request(
            "POST", "/containers/create", params={"name": name}, json=dict(body)
        )
        return _id_of(response)

    def connect(self, network: str, container: str) -> None:
        response = self._request(
            "POST", f"/networks/{network}/connect", json={"Container": container}
        )
        _present(response, f"network {network} or container {container}")

    def start(self, container: str) -> None:
        response = self._request("POST", f"/containers/{container}/start")
        _present(response, f"container {container}")

    def remove_container(self, container: str) -> None:
        self._request("DELETE", f"/containers/{container}", params={"force": "true"})

    def remove_network(self, network: str) -> None:
        self._request("DELETE", f"/networks/{network}")

    def labelled(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        filters = json.dumps({"label": [RUN_LABEL]})
        containers = self._request(
            "GET", "/containers/json", params={"all": "1", "filters": filters}
        )
        networks = self._request("GET", "/networks", params={"filters": filters})
        return (
            tuple(str(one["Id"]) for one in containers.json()),
            tuple(str(one["Name"]) for one in networks.json()),
        )

    def runtimes(self) -> tuple[str, ...]:
        info = self._request("GET", "/info").json()
        return tuple(sorted(info.get("Runtimes", {})))

    def ensure_egress_network(self) -> None:
        """Create the shared egress network if this daemon does not have it yet."""
        found = self._request("GET", f"/networks/{EGRESS_NETWORK}")
        if found.status_code == 404:
            self.create_network(egress_network_body())


def _id_of(response: httpx.Response) -> str:
    if response.status_code == 404:
        msg = "the daemon answered 404 to a create, so the image or network it names is missing"
        raise EngineError(msg)
    created = response.json().get("Id")
    if not isinstance(created, str) or not created:
        msg = "the daemon created something and did not say what"
        raise EngineError(msg)
    return created


def _present(response: httpx.Response, what: str) -> None:
    if response.status_code == 404:
        msg = f"{what} is not there"
        raise EngineError(msg)


# ------------------------------------------------------------------ the service
async def _attach(socket: str, container: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_unix_connection(socket)
    writer.write(attach_request(container))
    await writer.drain()
    status = await reader.readline()
    if b" 101 " not in status and b" 200 " not in status:
        msg = f"the daemon refused to attach to {container}"
        raise EngineError(msg)
    while (await reader.readline()) not in (b"\r\n", b""):
        pass
    return reader, writer


async def _relay(
    client: tuple[asyncio.StreamReader, asyncio.StreamWriter],
    runner: tuple[asyncio.StreamReader, asyncio.StreamWriter],
) -> None:
    async def upstream() -> None:
        try:
            while line := await client[0].readuntil(b"\n"):
                runner[1].write(line)
                await runner[1].drain()
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            return

    async def downstream() -> None:
        frames, lines = Demultiplexer(), Lines()
        while chunk := await runner[0].read(65536):
            for line in lines.feed(frames.feed(chunk)):
                client[1].write(line)
                await client[1].drain()

    tasks = [asyncio.create_task(upstream()), asyncio.create_task(downstream())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()


def serve(launcher: Launcher, *, socket: str, engine: DockerEngine) -> None:
    """Listen on the control network, one run per connection, for as long as the process lives."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        launched: Launched | None = None
        try:
            first = await reader.readuntil(b"\n")
            run_id, origins = start_request(first)
            launched = await asyncio.to_thread(launcher.launch, run_id, origins)
            attached = await _attach(socket, launched.runner)
            await asyncio.to_thread(engine.start, launched.runner)
            attached[1].write(first)
            await attached[1].drain()
            await _relay((reader, writer), attached)
        except (LauncherError, EngineError, asyncio.LimitOverrunError, asyncio.IncompleteReadError):
            pass
        finally:
            if launched is not None:
                await asyncio.to_thread(launcher.tear_down, launched)
            writer.close()

    async def run() -> None:
        server = await asyncio.start_server(
            handle,
            # Every interface of a container whose only network is the internal control network.
            host="0.0.0.0",  # noqa: S104
            port=LISTEN_PORT,
            limit=MAX_LINE_BYTES + 1,
        )
        async with server:
            await server.serve_forever()

    asyncio.run(run())


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.browsing.launcher --app-image IMAGE [--check]`."""
    parser = argparse.ArgumentParser(prog="brain.browsing.launcher")
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    engine = DockerEngine.over()
    gaps = runtime_gaps(engine.runtimes())
    if arguments.check or gaps:
        for gap in gaps:
            print(gap)
        return 1 if gaps else 0
    launcher = Launcher(engine=engine, app_image=arguments.app_image)
    engine.ensure_egress_network()
    launcher.sweep()
    serve(launcher, socket=DOCKER_SOCKET, engine=engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
