"""Starting and removing a run against an engine that records what it was asked, and the stream.

The Docker daemon is not on this machine. The launcher's decisions are tested against a fake
`Engine` that can be told to fail at any call, and the adapter's requests against httpx's mock
transport, which checks their shape and not that a daemon would accept them.

Task ids: M19.1.1, M19.1.5, M19.1.6
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from brain.browsing.launcher import (
    API_VERSION,
    FRAME_HEADER,
    Demultiplexer,
    DockerEngine,
    EngineError,
    Launched,
    Launcher,
    LauncherError,
    Lines,
    attach_request,
    runtime_gaps,
    start_request,
)
from brain.browsing.sandbox import EGRESS_NETWORK, RUN_LABEL
from brain.browsing.wire import MAX_LINE_BYTES, Kind, encode

ORIGIN = "https://books.example"
APP_IMAGE = "registry.example/brain:1.4.2"


@dataclass
class FakeEngine:
    fail_on: str = ""
    calls: list[tuple[str, str]] = field(default_factory=list)
    leftovers: tuple[tuple[str, ...], tuple[str, ...]] = ((), ())

    def _called(self, name: str, subject: str) -> str:
        self.calls.append((name, subject))
        if name == self.fail_on:
            msg = f"{name} failed"
            raise EngineError(msg)
        return f"id-{subject}"

    def create_network(self, body: Mapping[str, Any]) -> str:
        return self._called("create_network", str(body["Name"]))

    def create_container(self, name: str, body: Mapping[str, Any]) -> str:
        return self._called("create_container", name)

    def connect(self, network: str, container: str) -> None:
        self._called("connect", f"{network}<-{container}")

    def start(self, container: str) -> None:
        self._called("start", container)

    def remove_container(self, container: str) -> None:
        self._called("remove_container", container)

    def remove_network(self, network: str) -> None:
        self._called("remove_network", network)

    def labelled(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return self.leftovers

    def runtimes(self) -> tuple[str, ...]:
        return ("runc", "runsc")


def launcher(engine: FakeEngine) -> Launcher:
    return Launcher(engine=engine, app_image=APP_IMAGE)


def test_a_run_is_created_network_first_proxy_started_and_runner_left_unstarted() -> None:
    """The positive case, in order. The proxy is on the route out before the runner exists, and the
    runner is not started, so the caller can attach before its first line.

    Delete this and the runner can be started before it is attached, losing its first lines, or
    before its proxy is up, so its first navigation fails as though the target were down."""
    engine = FakeEngine()

    launched = launcher(engine).launch("run-1", frozenset({ORIGIN}))

    assert [name for name, _ in engine.calls] == [
        "create_network",
        "create_container",
        "connect",
        "start",
        "create_container",
    ]
    assert engine.calls[2] == ("connect", f"{EGRESS_NETWORK}<-id-brain-browser-run-1-egress")
    assert launched == Launched(
        "run-1",
        network="id-brain-browser-run-1",
        egress="id-brain-browser-run-1-egress",
        runner="id-brain-browser-run-1-runner",
    )


@pytest.mark.parametrize("failing", ["create_container", "connect", "start"])
def test_a_launch_that_fails_half_way_removes_everything_it_created(failing: str) -> None:
    """Delete this and a failed launch leaves a proxy with a route out, or a network, behind."""
    engine = FakeEngine(fail_on=failing)

    with pytest.raises(EngineError):
        launcher(engine).launch("run-1", frozenset({ORIGIN}))

    removed = {subject for name, subject in engine.calls if name.startswith("remove")}
    assert "id-brain-browser-run-1" in removed
    if failing != "create_container":
        assert "id-brain-browser-run-1-egress" in removed


def test_a_run_id_is_spent_by_its_first_launch_even_when_that_launch_failed() -> None:
    """**Never reused.** Delete this and a failed run can be retried under its old id, onto names
    and an envelope that belong to an attempt that already happened."""
    engine = FakeEngine(fail_on="start")
    starter = launcher(engine)
    with pytest.raises(EngineError):
        starter.launch("run-1", frozenset({ORIGIN}))
    engine.fail_on = ""

    with pytest.raises(LauncherError, match="never launched twice"):
        starter.launch("run-1", frozenset({ORIGIN}))
    assert starter.launch("run-2", frozenset({ORIGIN})).runner


def test_a_sandbox_with_a_gap_is_refused_before_the_engine_is_asked_anything() -> None:
    """Delete this and a body the gap check refuses reaches the daemon anyway."""
    engine = FakeEngine()

    with pytest.raises(LauncherError, match="not launched"):
        Launcher(engine=engine, app_image=APP_IMAGE).launch(
            "run-1", frozenset({"https://books.example/not-an-origin"})
        )

    assert engine.calls == []


def test_teardown_attempts_every_removal_whatever_failed_first() -> None:
    """Delete this and a teardown that fails on the runner leaves the proxy and its route out."""
    engine = FakeEngine(fail_on="remove_container")

    with pytest.raises(LauncherError, match="not wholly removed"):
        launcher(engine).tear_down(
            Launched("run-1", network="net", egress="egress", runner="runner")
        )

    assert engine.calls == [
        ("remove_container", "runner"),
        ("remove_container", "egress"),
        ("remove_network", "net"),
    ]


def test_a_teardown_that_succeeds_removes_runner_then_proxy_then_network() -> None:
    """The positive case for teardown. Delete this and one that removes nothing passes above."""
    engine = FakeEngine()

    launcher(engine).tear_down(Launched("run-1", network="net", egress="egress", runner="runner"))

    assert engine.calls == [
        ("remove_container", "runner"),
        ("remove_container", "egress"),
        ("remove_network", "net"),
    ]


def test_a_sweep_removes_what_a_dead_launcher_left_and_keeps_the_shared_egress_network() -> None:
    """Delete this and a launcher that restarts mid-run leaves that run's proxy running for ever."""
    engine = FakeEngine(leftovers=(("c1", "c2"), ("brain-browser-run-9", EGRESS_NETWORK)))

    removed = launcher(engine).sweep()

    assert removed == 3
    assert ("remove_network", EGRESS_NETWORK) not in engine.calls
    assert ("remove_network", "brain-browser-run-9") in engine.calls


def test_a_daemon_without_gvisor_is_not_ready() -> None:
    """Delete this and a launcher on a host with no gVisor reports healthy and refuses every run."""
    assert runtime_gaps(("runc",)) != ()
    assert runtime_gaps(("runc", "runsc")) == ()


# ------------------------------------------------------------------ what it accepts
def test_the_launcher_accepts_only_a_start_message() -> None:
    """Delete this and a stop or an act can be the first line, and a run starts from nothing."""
    with pytest.raises(LauncherError, match="accepts a start message"):
        start_request(encode(Kind.STOP))
    with pytest.raises(LauncherError):
        start_request(b"not json\n")


def test_a_start_message_yields_the_run_and_its_origins_and_nothing_else() -> None:
    """The positive case. Delete this and a launcher refusing every start passes the test above."""
    line = encode(
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

    assert start_request(line) == ("run-1", frozenset({ORIGIN}))


# ------------------------------------------------------------------ the stream
def test_only_standard_output_survives_the_multiplexed_stream_whatever_the_chunking() -> None:
    """Delete this and standard error, which a crashing browser fills, is relayed as protocol lines,
    or a frame split across two reads is dropped."""
    stream = (
        FRAME_HEADER.pack(1, 6)
        + b"hello\n"
        + FRAME_HEADER.pack(2, 5)
        + b"oops\n"
        + FRAME_HEADER.pack(1, 3)
        + b"ok\n"
    )
    for size in (1, 3, 7, len(stream)):
        frames = Demultiplexer()
        out = b"".join(frames.feed(stream[at : at + size]) for at in range(0, len(stream), size))
        assert out == b"hello\nok\n"


def test_lines_are_split_whole_and_an_endless_line_is_refused() -> None:
    """Delete this and a runner that never sends a newline fills the launcher's memory."""
    lines = Lines()
    assert lines.feed(b"one\ntw") == [b"one\n"]
    assert lines.feed(b"o\n") == [b"two\n"]
    with pytest.raises(LauncherError, match="longer than a line may be"):
        Lines().feed(b"x" * (MAX_LINE_BYTES + 1))


def test_the_attach_request_asks_for_input_and_output_and_not_error() -> None:
    """Delete this and the attach can include standard error, or omit standard input, which is a
    run that can never be sent its first instruction."""
    request = attach_request("abc").decode("ascii")

    assert request.startswith(f"POST /{API_VERSION}/containers/abc/attach?")
    assert "stdin=1" in request
    assert "stdout=1" in request
    assert "stderr=0" in request
    assert "Upgrade: tcp" in request


# ------------------------------------------------------------------ the adapter
def test_the_docker_adapter_sends_the_sandbox_body_it_was_given_to_the_versioned_api() -> None:
    """Delete this and the adapter can rewrite a body on the way out, or drop the API version, and
    the gap check upstream is checking a body that is not the one sent."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "created"})

    engine = DockerEngine(
        httpx.Client(transport=httpx.MockTransport(answer), base_url="http://docker")
    )
    body = {"Image": "x", "HostConfig": {"Runtime": "runsc"}}

    assert engine.create_container("brain-browser-run-1-runner", body) == "created"
    (request,) = seen
    assert request.url.path == f"/{API_VERSION}/containers/create"
    assert request.url.params["name"] == "brain-browser-run-1-runner"
    assert json.loads(request.content) == body


def test_the_docker_adapter_treats_a_refusal_as_an_error_and_an_absence_on_removal_as_done() -> (
    None
):
    """Delete this and a 409 on create reads as success, or a second removal of a gone container
    fails a teardown that has nothing left to remove."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(404)
        return httpx.Response(409, json={"message": "conflict"})

    engine = DockerEngine(
        httpx.Client(transport=httpx.MockTransport(answer), base_url="http://docker")
    )

    with pytest.raises(EngineError):
        engine.create_network({"Name": "brain-browser-run-1"})
    engine.remove_container("gone")
    engine.remove_network("gone")


def test_the_docker_adapter_finds_leftovers_by_the_run_label() -> None:
    """Delete this and a sweep can list every container on the host and remove them all."""
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/containers/json"):
            return httpx.Response(200, json=[{"Id": "c1"}])
        return httpx.Response(200, json=[{"Name": "brain-browser-run-1"}])

    engine = DockerEngine(
        httpx.Client(transport=httpx.MockTransport(answer), base_url="http://docker")
    )

    assert engine.labelled() == (("c1",), ("brain-browser-run-1",))
    assert all(json.loads(one.url.params["filters"]) == {"label": [RUN_LABEL]} for one in seen)
