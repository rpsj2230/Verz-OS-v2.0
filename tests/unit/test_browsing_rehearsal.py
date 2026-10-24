"""A rehearsal makes a run's sandbox, asks the daemon what it made, removes it, and starts nothing.

The daemon is not on this machine. These tests use an engine that behaves like one: it keeps the
bodies it was sent and describes them back in Docker's own spelling, and each test then changes one
thing the way a real daemon could (a runtime it does not have, a field it leaves out, a bind it was
not asked for) and requires the rehearsal to say so. What is not shown here is that Docker's real
answer has these shapes; `ops/browser/REHEARSAL.md` and the install check are where that is read.

Task ids: M19.1.1, M19.1.5, M19.1.6, M19.3.5, M19.6.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from brain.browsing import launcher as launcher_module
from brain.browsing.inspection import (
    container_facts,
    network_facts,
    observed_gaps,
)
from brain.browsing.launcher import (
    EngineError,
    Launcher,
    LauncherError,
    rehearsal_request,
    start_request,
)
from brain.browsing.sandbox import EGRESS_NETWORK, RUN_LABEL
from brain.browsing.wire import Kind, decode, encode

ORIGIN = "https://books.example"
APP_IMAGE = "registry.example/brain:1.4.2"

Edit = Callable[[dict[str, Any]], None]


@dataclass
class Daemon:
    """An engine that remembers what it made and describes it the way Docker would."""

    networks: dict[str, dict[str, Any]] = field(default_factory=dict)
    containers: dict[str, dict[str, Any]] = field(default_factory=dict)
    joined: dict[str, list[str]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    #: Edits applied to what the daemon says about a container, by the end of its name.
    edit_container: dict[str, Edit] = field(default_factory=dict)
    edit_network: Edit | None = None
    fail_inspect: bool = False
    fail_removal: bool = False
    leftovers: tuple[tuple[str, ...], tuple[str, ...]] = ((), ())

    def create_network(self, body: Mapping[str, Any]) -> str:
        self.calls.append("create_network")
        self.networks[str(body["Name"])] = dict(body)
        return str(body["Name"])

    def create_container(self, name: str, body: Mapping[str, Any]) -> str:
        self.calls.append(f"create_container:{name}")
        self.containers[name] = dict(body)
        mode = str(body["HostConfig"]["NetworkMode"])
        self.joined[name] = [mode]
        return name

    def connect(self, network: str, container: str) -> None:
        self.calls.append("connect")
        self.joined[container].append(network)

    def start(self, container: str) -> None:
        self.calls.append(f"start:{container}")

    def remove_container(self, container: str) -> None:
        self.calls.append(f"remove_container:{container}")
        if self.fail_removal:
            msg = "refused"
            raise EngineError(msg)
        self.containers.pop(container, None)

    def remove_network(self, network: str) -> None:
        self.calls.append(f"remove_network:{network}")
        self.networks.pop(network, None)

    def labelled(self, run_id: str | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return self.leftovers

    def runtimes(self) -> tuple[str, ...]:
        return ("runc", "runsc")

    def inspect_container(self, container: str) -> Mapping[str, Any]:
        if self.fail_inspect:
            msg = "no answer"
            raise EngineError(msg)
        body = self.containers[container]
        host = body["HostConfig"]
        described: dict[str, Any] = {
            "Name": f"/{container}",
            "Config": {"Labels": dict(body["Labels"])},
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
            "Mounts": [{"Type": "tmpfs", "Destination": path} for path in host["Tmpfs"]],
            "NetworkSettings": {"Networks": {name: {} for name in self.joined[container]}},
        }
        for suffix, edit in self.edit_container.items():
            if container.endswith(suffix):
                edit(described)
        return described

    def inspect_network(self, network: str) -> Mapping[str, Any]:
        body = self.networks[network]
        described: dict[str, Any] = {
            "Name": body["Name"],
            "Internal": body["Internal"],
            "Labels": dict(body["Labels"]),
        }
        if self.edit_network is not None:
            self.edit_network(described)
        return described


def rehearsal(daemon: Daemon, run_id: str = "rehearsal-1"):  # type: ignore[no-untyped-def]
    return Launcher(engine=daemon, app_image=APP_IMAGE).rehearse(run_id, frozenset({ORIGIN}))


# ------------------------------------------------------------ a daemon that does as it is told
def test_a_rehearsal_of_a_faithful_daemon_finds_nothing_and_starts_no_browser() -> None:
    """The positive case. The proxy is started, because the route out is part of what is being
    described, and the runner never is, so no page is opened and nothing leaves the host.

    Delete this and a rehearsal that reports a gap for every daemon, or one that starts the runner
    on the owner's server whenever the checks run, passes every test below."""
    daemon = Daemon()

    found = rehearsal(daemon)

    assert found.gaps == ()
    assert found.runtime == "runsc"
    assert found.left_behind == 0
    assert "start:brain-browser-rehearsal-1-egress" in daemon.calls
    assert not any(call.startswith("start:") and call.endswith("-runner") for call in daemon.calls)


def test_a_rehearsal_removes_what_it_made_whether_or_not_it_found_anything() -> None:
    """Delete this and each rehearsal leaves a proxy with a route out and a network on the owner's
    server, once per acceptance run."""
    daemon = Daemon()

    rehearsal(daemon)

    assert daemon.containers == {} and daemon.networks == {}
    assert "remove_container:brain-browser-rehearsal-1-runner" in daemon.calls
    assert "remove_container:brain-browser-rehearsal-1-egress" in daemon.calls


# ------------------------------------------------------------------ a daemon that did not
def test_a_daemon_that_ran_the_runner_under_another_runtime_is_a_finding() -> None:
    """The body asked for runsc and the daemon says runc. Delete this and a host where gVisor was
    registered under another name passes, with every page reaching the host kernel."""
    daemon = Daemon(
        edit_container={"-runner": lambda raw: raw["HostConfig"].update(Runtime="runc")}
    )

    found = rehearsal(daemon)

    assert any("runner is not running under runsc" in gap for gap in found.gaps)
    assert found.runtime == "runc"


def test_a_field_the_daemon_left_out_is_a_finding_and_not_the_safe_value() -> None:
    """Delete this and a daemon that does not report a read-only root is read as having one."""

    def forget(raw: dict[str, Any]) -> None:
        del raw["HostConfig"]["ReadonlyRootfs"]

    found = rehearsal(Daemon(edit_container={"-runner": forget}))

    assert any("runner's root filesystem is not read-only" in gap for gap in found.gaps)


@pytest.mark.parametrize(
    ("edit", "words"),
    [
        (lambda raw: raw["HostConfig"].update(Privileged=True), "privileged"),
        (lambda raw: raw["HostConfig"].update(CapDrop=[]), "capabilities"),
        (lambda raw: raw["HostConfig"].update(Memory=0), "memory"),
        (lambda raw: raw["HostConfig"].update(MemorySwap=2 * 1024**3), "memory"),
        (lambda raw: raw["HostConfig"].update(NanoCpus=0), "processor"),
        (lambda raw: raw["HostConfig"].update(PidsLimit=-1), "process cap"),
        (lambda raw: raw["HostConfig"].update(Tmpfs={"/tmp": "rw"}), "somewhere other"),  # noqa: S108
        (lambda raw: raw["HostConfig"].update(Binds=["/home/staff:/profile"]), "bind or a volume"),
        (lambda raw: raw["Mounts"].append({"Type": "volume", "Destination": "/p"}), "bind or a v"),
        (lambda raw: raw["Config"]["Labels"].clear(), "carry the run's label"),
    ],
)
def test_each_way_a_runner_could_be_weaker_than_asked_is_named(edit: Edit, words: str) -> None:
    """One edit at a time, each on the runner. Delete this and a daemon that applied a default for a
    cap, kept a capability or mounted a profile passes."""
    found = rehearsal(Daemon(edit_container={"-runner": edit}))

    assert any(words in gap for gap in found.gaps), found.gaps


def test_the_proxy_is_held_to_the_same_expectations_as_the_runner() -> None:
    """Delete this and only the runner is described, so a proxy with a writable root passes."""
    daemon = Daemon(
        edit_container={"-egress": lambda raw: raw["HostConfig"].update(ReadonlyRootfs=False)}
    )

    found = rehearsal(daemon)

    assert any("proxy's root filesystem" in gap for gap in found.gaps)


def test_a_network_the_daemon_made_routable_is_a_finding() -> None:
    """Delete this and a daemon that ignored `Internal` gives the runner a gateway."""
    found = rehearsal(Daemon(edit_network=lambda raw: raw.update(Internal=False)))

    assert any("not internal" in gap for gap in found.gaps)


def test_a_runner_on_a_second_network_is_a_finding() -> None:
    """The runner's only route is its run's network. Delete this and a runner given the shared
    egress network, which has a route out, passes."""
    daemon = Daemon()
    original = daemon.create_container

    def create(name: str, body: Mapping[str, Any]) -> str:
        made = original(name, body)
        if name.endswith("-runner"):
            daemon.joined[name].append(EGRESS_NETWORK)
        return made

    daemon.create_container = create  # type: ignore[method-assign]

    found = rehearsal(daemon)

    assert any("runner is on a network other than its run's" in gap for gap in found.gaps)


def test_a_proxy_that_is_not_on_the_shared_egress_network_is_a_finding() -> None:
    """The proxy is the one member with a route out. Delete this and a proxy that cannot reach the
    network, or one on a third, passes."""
    daemon = Daemon()
    original = daemon.connect

    def connect(network: str, container: str) -> None:
        original("brain-browser-somewhere-else", container)

    daemon.connect = connect  # type: ignore[method-assign]

    found = rehearsal(daemon)

    assert any("proxy is not on exactly" in gap for gap in found.gaps)


def test_a_removal_that_failed_is_a_finding_and_every_removal_was_still_attempted() -> None:
    """Delete this and a daemon that refuses to remove the proxy is reported clean."""
    daemon = Daemon(fail_removal=True)

    found = rehearsal(daemon)

    assert any("not wholly removed" in gap for gap in found.gaps)
    assert "remove_network:brain-browser-rehearsal-1" in daemon.calls


def test_a_daemon_that_cannot_describe_what_it_made_is_a_finding_and_is_cleaned_up() -> None:
    """Delete this and a daemon that answers creates and not inspects is read as a clean one, or
    leaves the rehearsal's containers behind."""
    daemon = Daemon(fail_inspect=True)

    found = rehearsal(daemon)

    assert found.gaps == ("the daemon could not describe what it created",)
    assert daemon.containers == {}


def test_what_is_still_labelled_with_the_run_is_counted_and_the_shared_network_is_not() -> None:
    """Delete this and a removal that quietly did nothing is reported as nothing left, or the
    shared egress network, which is meant to stay, is counted as a leak every time."""
    leaking = Daemon(leftovers=(("c1",), ("brain-browser-rehearsal-1", EGRESS_NETWORK)))
    clean = Daemon(leftovers=((), (EGRESS_NETWORK,)))

    assert rehearsal(leaking).left_behind == 2
    assert rehearsal(clean).left_behind == 0


def test_a_request_the_sandbox_refuses_is_refused_and_nothing_is_created() -> None:
    """Delete this and a rehearsal can be asked for a sandbox the launcher would never make."""
    daemon = Daemon()

    with pytest.raises(LauncherError):
        Launcher(engine=daemon, app_image=APP_IMAGE).rehearse(
            "rehearsal-1", frozenset({"https://books.example/not-an-origin"})
        )

    assert daemon.calls == []


# ------------------------------------------------------------ the facts, as Docker spells them
def test_the_facts_are_read_from_the_spelling_docker_uses() -> None:
    """Delete this and the parse is only ever exercised on dictionaries this file built to match
    it, so the shape Docker really uses is never what is read."""
    raw = {
        "Config": {"Labels": {RUN_LABEL: "run-1"}},
        "HostConfig": {
            "Runtime": "runsc",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["all"],
            "Memory": 5,
            "MemorySwap": 5,
            "NanoCpus": 7,
            "PidsLimit": 9,
            "Tmpfs": {"/tmp": "rw,size=64m", "/home/x": "rw"},  # noqa: S108
            "Binds": ["/a:/b"],
        },
        "Mounts": [{"Type": "tmpfs"}, {"Type": "bind"}],
        "NetworkSettings": {"Networks": {"b": {}, "a": {}}},
    }

    facts = container_facts(raw)

    assert facts.runtime == "runsc" and facts.read_only is True and facts.privileged is False
    assert facts.cap_drop == ("ALL",)
    assert (facts.memory, facts.swap, facts.nano_cpus, facts.pids) == (5, 5, 7, 9)
    assert facts.writable == ("/home/x", "/tmp")  # noqa: S108
    assert facts.reaches == ("bind", "bind")
    assert facts.networks == ("a", "b")
    assert facts.run == "run-1"


def test_a_description_with_nothing_in_it_yields_no_safe_values() -> None:
    """Delete this and an empty answer is read as a container that has every protection."""
    facts = container_facts({})

    assert facts.runtime is None and facts.read_only is None and facts.privileged is None
    assert facts.cap_drop is None and facts.memory is None and facts.pids is None
    assert facts.writable == () and facts.networks == () and facts.run is None
    assert network_facts({}).internal is None


def test_a_boolean_is_not_a_number_in_a_daemons_answer() -> None:
    """Delete this and `Memory: true` is read as a cap of one byte that matches nothing, or worse
    `PidsLimit: true` as a limit of one."""
    facts = container_facts({"HostConfig": {"Memory": True, "PidsLimit": True}})

    assert facts.memory is None and facts.pids is None


def test_observed_gaps_is_empty_for_the_facts_the_product_describes() -> None:
    """The positive case for the comparison on its own: Delete this and a comparison that reports
    something for every input passes the rehearsal tests, which only look for the words."""
    daemon = Daemon()
    box = Launcher(engine=daemon, app_image=APP_IMAGE)
    launched = box.launch("rehearsal-2", frozenset({ORIGIN}))

    gaps = observed_gaps(
        "rehearsal-2",
        network=network_facts(daemon.inspect_network(launched.network)),
        runner=container_facts(daemon.inspect_container(launched.runner)),
        egress=container_facts(daemon.inspect_container(launched.egress)),
    )

    assert gaps == ()


# ------------------------------------------------------------------ the line
def test_a_rehearse_line_is_not_a_start_line_and_the_other_way_round() -> None:
    """Delete this and a start line can be read as a rehearsal (so a real run is described and not
    run), or a rehearsal as a start (so it opens a browser)."""
    rehearse = encode(Kind.REHEARSE, run_id="rehearsal-1", origins=[ORIGIN])
    start = encode(
        Kind.START,
        run_id="run-1",
        asked_by="alex",
        digest="d",
        approved=False,
        origins=[ORIGIN],
        steps=[],
        budget=[],
        tiers=[],
        unattended=[],
        surfaces={},
    )

    assert rehearsal_request(rehearse) == ("rehearsal-1", frozenset({ORIGIN}))
    assert rehearsal_request(start) is None
    assert rehearsal_request(b"not json\n") is None
    with pytest.raises(LauncherError, match="accepts a start message"):
        start_request(rehearse)


class _Writer:
    def __init__(self) -> None:
        self.lines: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.lines.append(data)

    async def drain(self) -> None:
        return None


def _answer(daemon: Daemon, run_id: str = "rehearsal-1") -> dict[str, Any]:
    writer = _Writer()
    asyncio.run(
        launcher_module._rehearsed(
            Launcher(engine=daemon, app_image=APP_IMAGE),
            writer,  # type: ignore[arg-type]
            run_id,
            frozenset({ORIGIN}),
        )
    )
    (line,) = writer.lines
    message = decode(line)
    assert message.kind is Kind.REHEARSED
    return dict(message.fields)


def test_the_answer_to_a_rehearsal_is_one_rehearsed_line_naming_the_run() -> None:
    """Delete this and the worker cannot tell which run an answer is for, or reads a clean daemon
    as one with gaps."""
    answer = _answer(Daemon())

    assert answer == {
        "run_id": "rehearsal-1",
        "runtime": "runsc",
        "gaps": [],
        "left_behind": 0,
        "virtualisation": "no_gvisor",
    }


def test_a_request_the_sandbox_refuses_is_answered_with_its_sentence_and_not_with_silence() -> None:
    """Delete this and a refused rehearsal closes the connection, which the other side reads as a
    launcher that is not there and reports as the runtime being absent."""
    writer = _Writer()
    asyncio.run(
        launcher_module._rehearsed(
            Launcher(engine=Daemon(), app_image=APP_IMAGE),
            writer,  # type: ignore[arg-type]
            "Rehearsal With Capitals",
            frozenset({ORIGIN}),
        )
    )

    message = decode(writer.lines[0])
    assert message.kind is Kind.REHEARSED
    assert message.fields["gaps"] and message.fields["runtime"] == ""


def test_a_network_without_the_runs_label_is_a_finding() -> None:
    """The sweep finds a leftover by its label. Delete this and a network the daemon made without
    one passes, and a dead launcher's network is never removed."""
    found = rehearsal(Daemon(edit_network=lambda raw: raw["Labels"].clear()))

    assert any("network does not carry the run's label" in gap for gap in found.gaps)


def test_a_string_is_not_a_flag_in_a_daemons_answer() -> None:
    """Delete this and `ReadonlyRootfs: "false"`, which is a string and is truthy, is read as a
    read-only root."""
    facts = container_facts({"HostConfig": {"ReadonlyRootfs": "true", "Privileged": "false"}})

    assert facts.read_only is None and facts.privileged is None
    assert network_facts({"Internal": "true"}).internal is None


def test_the_answer_names_what_the_launcher_read_of_the_host() -> None:
    """The state the launcher was started with is the one it answers, for a refusal as well as a
    clean rehearsal. Delete this and the install check reads a state the launcher never read."""
    writer = _Writer()
    asyncio.run(
        launcher_module._rehearsed(
            Launcher(engine=Daemon(), app_image=APP_IMAGE, virtualisation="kvm_in_use"),
            writer,  # type: ignore[arg-type]
            "rehearsal-1",
            frozenset({ORIGIN}),
        )
    )
    (line,) = writer.lines

    assert decode(line).fields["virtualisation"] == "kvm_in_use"
