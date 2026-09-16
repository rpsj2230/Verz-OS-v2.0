"""What a run is created in, read off the Engine bodies, and the proxy rule that is its route out.

No container is started here and none can be: Docker and gVisor are not on this machine. What is
tested is every decision the bodies make, each against a planted body that breaks it, and the
proxy's rule against flows shaped the way mitmproxy hands them over.

Task ids: M19.1.1, M19.1.5, M19.1.6, M19.3.5, M19.6.4
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from brain.browsing import egress_addon
from brain.browsing.egress_addon import Egress, admits, parse_allowlist, same_site
from brain.browsing.sandbox import (
    ADDON_VARIABLE,
    CONTAINER_TMP,
    EGRESS_ALIAS,
    EGRESS_CAPS,
    MIB,
    PROXY_ADDRESS,
    RUNNER_CAPS,
    RUNTIME,
    Caps,
    RunSandbox,
    SandboxError,
    addon_script,
    addon_source,
    allowlist_in,
    runner_image_for,
    sandbox_for,
    sandbox_gaps,
)
from brain.ops.admission import Resource, seed_budgets

ORIGIN = "https://books.example"
LOGIN = "https://login.books.example"
APP_IMAGE = "registry.example/brain:1.4.2"


def sandbox(run_id: str = "run-1") -> RunSandbox:
    return sandbox_for(run_id, origins=frozenset({ORIGIN, LOGIN}), app_image=APP_IMAGE)


def broken(change: str) -> RunSandbox:
    """The real sandbox with one decision undone, so each gap test changes exactly one thing."""
    built = sandbox()
    network = copy.deepcopy(built.network)
    runner = copy.deepcopy(built.runner.body)
    egress = copy.deepcopy(built.egress.body)
    host = runner["HostConfig"]
    match change:
        case "runtime":
            host["Runtime"] = "runc"
        case "egress runtime":
            egress["HostConfig"]["Runtime"] = "runc"
        case "writable root":
            host["ReadonlyRootfs"] = False
        case "network with a gateway":
            network["Internal"] = False
        case "host network":
            host["NetworkMode"] = "host"
        case "a bind mount":
            host["Binds"] = ["/:/host"]
        case "a volume":
            runner["Volumes"] = {"/data": {}}
        case "capabilities kept":
            host["CapDrop"] = []
        case "privileged":
            host["Privileged"] = True
        case "memory uncapped":
            host["Memory"] = 0
        case "swap past the cap":
            host["MemorySwap"] = -1
        case "a second writable mount":
            host["Tmpfs"] = {**host["Tmpfs"], "/opt": "rw,size=64m"}
        case "a published port":
            host["PortBindings"] = {"9222/tcp": [{"HostPort": "9222"}]}
        case "a second network for the runner":
            runner["NetworkingConfig"] = {"EndpointsConfig": {"brain-browser-egress": {}}}
        case "the proxy variables dropped":
            runner["Env"] = [one for one in runner["Env"] if "PROXY" not in one]
        case "a credential in the environment":
            runner["Env"] = [*runner["Env"], "VAULT_TOKEN=x"]
        case "a wider allowlist":
            wider = addon_script((ORIGIN, LOGIN, "https://elsewhere.example"))
            egress["Env"] = [f"{ADDON_VARIABLE}={wider}"]
        case "a list built some other way":
            other = f"{addon_source()}\naddons = [Egress(parse_allowlist(open('list').read()))]\n"
            egress["Env"] = [f"{ADDON_VARIABLE}={other}"]
        case "kept after exit":
            host["AutoRemove"] = False
        case _:  # pragma: no cover - a test naming a change nobody wrote
            raise AssertionError(change)
    return RunSandbox(
        run_id=built.run_id,
        network=network,
        egress=type(built.egress)(name=built.egress.name, body=egress),
        runner=type(built.runner)(name=built.runner.name, body=runner),
        origins=built.origins,
    )


# ------------------------------------------------------------------ the bodies
def test_the_sandbox_the_product_builds_has_no_gap() -> None:
    """The positive case, and the claim itself. Delete this and `sandbox_for` can drift into a body
    `sandbox_gaps` refuses, so every launch is refused and nothing says why until a run is tried."""
    assert sandbox_gaps(sandbox()) == ()


@pytest.mark.parametrize(
    "change",
    [
        "runtime",
        "egress runtime",
        "writable root",
        "network with a gateway",
        "host network",
        "a bind mount",
        "a volume",
        "capabilities kept",
        "privileged",
        "memory uncapped",
        "swap past the cap",
        "a second writable mount",
        "a published port",
        "a second network for the runner",
        "the proxy variables dropped",
        "a credential in the environment",
        "a wider allowlist",
        "a list built some other way",
        "kept after exit",
    ],
)
def test_every_way_out_of_the_sandbox_is_a_gap(change: str) -> None:
    """Each body change here gives a compromised page something: the host kernel, a route out, a
    place to leave a file, a way past the memory cap, or a reach beyond the run's origins.

    Delete this and `sandbox_gaps` can be narrowed to the checks the real body happens to pass,
    which is a launcher that would send any body at all."""
    assert sandbox_gaps(broken(change)) != ()


def test_both_containers_run_under_gvisor_with_nothing_writable_but_memory() -> None:
    """M19.1.1 and M19.1.5 stated on the bodies rather than through the gap function, so a gap
    function that agreed with a wrong body would still be caught here.

    Delete this and the two properties are asserted only through the check that is meant to hold
    them, which proves the check and the builder agree and nothing about either."""
    built = sandbox()
    for container, caps in ((built.runner, RUNNER_CAPS), (built.egress, EGRESS_CAPS)):
        host = container.body["HostConfig"]
        assert host["Runtime"] == "runsc"
        assert host["ReadonlyRootfs"] is True
        assert set(host["Tmpfs"]) == {path for path, _ in caps.tmpfs}
        assert host["AutoRemove"] is True
        assert "Binds" not in host
        assert "Mounts" not in host
        assert host["Memory"] == host["MemorySwap"] == caps.memory_mib * MIB


def test_a_run_is_created_on_its_own_network_that_nothing_else_shares() -> None:
    """M19.1.6. Two runs never share a network, a proxy or a name.

    Delete this and names can be derived from something other than the run id, and two runs'
    runners land on one network where one page can reach the other run's browser."""
    first, second = sandbox("run-1"), sandbox("run-2")

    assert first.network["Internal"] is True
    assert first.network_name != second.network_name
    assert first.runner.body["HostConfig"]["NetworkMode"] == first.network_name
    assert {first.runner.name, first.egress.name}.isdisjoint(
        {second.runner.name, second.egress.name}
    )
    endpoints = first.egress.body["NetworkingConfig"]["EndpointsConfig"]
    assert endpoints == {first.network_name: {"Aliases": [EGRESS_ALIAS]}}
    assert f"http://{EGRESS_ALIAS}:8080" == PROXY_ADDRESS


def test_the_proxy_is_handed_exactly_the_runs_origins_and_the_rule_in_this_repository() -> None:
    """M19.3.5's configuration half. Delete this and the proxy can be started with a list the
    envelope did not seal, or with a copy of the rule that has drifted from the tested one."""
    env = dict(one.split("=", 1) for one in sandbox().egress.body["Env"])
    script = env[ADDON_VARIABLE]

    assert set(env) == {ADDON_VARIABLE}
    assert script.startswith(addon_source())
    assert allowlist_in(script) == parse_allowlist(json.dumps([ORIGIN, LOGIN]))


def test_a_run_id_that_cannot_name_a_container_unchanged_is_refused() -> None:
    """Delete this and ids are rewritten into names, so `Run/1` and `run-1` share containers."""
    for bad in ("Run-1", "run/1", "", "-run"):
        with pytest.raises(SandboxError, match="cannot name a container"):
            sandbox_for(bad, origins=frozenset({ORIGIN}), app_image=APP_IMAGE)


def test_a_run_with_no_origin_is_refused() -> None:
    """Delete this and a proxy with an empty list starts, refuses everything, and the run fails for
    a reason that looks like the target being down."""
    with pytest.raises(SandboxError, match="allows no origin"):
        sandbox_for("run-1", origins=frozenset(), app_image=APP_IMAGE)


def test_the_runner_image_is_the_application_release_with_a_suffix_and_never_a_guess() -> None:
    """One variable selects every container of the product. Delete this and the runner can be
    named by a second variable, which is the drift item 51 closed for the application."""
    assert runner_image_for(APP_IMAGE) == "registry.example/brain:1.4.2-browser"
    assert runner_image_for("localhost:5000/brain:7") == "localhost:5000/brain:7-browser"
    for bad in ("registry.example/brain", "brain@sha256:" + "a" * 64, "localhost:5000/brain"):
        with pytest.raises(SandboxError, match="carries no tag"):
            runner_image_for(bad)


# ------------------------------------------------------------------ the caps
def test_writable_memory_and_the_browsers_floor_must_fit_under_the_cap() -> None:
    """M19.1.5 and M19.6.4 together: tmpfs is charged to the memory cgroup.

    Delete this and a runner can be given a tmpfs as large as its cap, and a page that fills its
    download directory has the browser killed mid-write instead of seeing a full disk."""
    with pytest.raises(SandboxError, match="does not fit"):
        Caps(
            memory_mib=1024,
            millicpus=1000,
            pids=64,
            tmpfs=((CONTAINER_TMP, 512),),
            shm_mib=64,
            floor_mib=512,
        )
    fits = Caps(
        memory_mib=1024,
        millicpus=1000,
        pids=64,
        tmpfs=((CONTAINER_TMP, 448),),
        shm_mib=64,
        floor_mib=512,
    )
    assert fits.writable_mib() + fits.floor_mib == fits.memory_mib


@pytest.mark.parametrize("name", ["memory_mib", "millicpus", "pids", "shm_mib", "floor_mib"])
def test_a_cap_of_zero_is_refused(name: str) -> None:
    """Zero is how "unlimited" is spelled in a body. Delete this and a cap can be switched off by
    editing a number."""
    values: dict[str, Any] = {
        "memory_mib": 1024,
        "millicpus": 100,
        "pids": 10,
        "tmpfs": (),
        "shm_mib": 1,
        "floor_mib": 1,
    }
    values[name] = 0
    with pytest.raises(SandboxError, match="no cap at all"):
        Caps(**values)


def test_the_caps_for_every_budgeted_session_fit_what_the_budget_reason_describes() -> None:
    """The per-session caps are held against two things outside themselves: the global browser
    budget in `brain.ops.admission`, whose reason says a session is hundreds of megabytes on a box
    of twelve gigabytes, and the architecture's sizing table, which gives the browser 8 GB of a
    32 GB machine at most, a quarter. Every admitted session at once, with its proxy, fits in a
    quarter of the box the budget was written for.

    Delete this and the runner cap can be raised to several gigabytes with the budget still
    admitting two sessions, and the host the budget was measured on runs out of memory."""
    (budget,) = [one for one in seed_budgets() if one.resource is Resource.BROWSER_SESSIONS]
    per_session = RUNNER_CAPS.memory_mib + EGRESS_CAPS.memory_mib

    assert "hundreds of megabytes" in budget.reason
    assert per_session * budget.limit <= 12 * 1024 // 4
    assert RUNNER_CAPS.memory_mib < 2048


# ------------------------------------------------------------------ the proxy's rule
@dataclass
class Request:
    scheme: str = "https"
    host: str = "books.example"
    port: int = 443
    host_header: str | None = "books.example"


@dataclass
class Flow:
    request: Request = field(default_factory=Request)
    killed: bool = False

    def kill(self) -> None:
        self.killed = True


ALLOWED = parse_allowlist(json.dumps([ORIGIN, "http://plain.example:8080"]))


def test_an_allowed_origin_passes_through_the_tunnel_and_inside_it() -> None:
    """The positive case. Delete this and a proxy that kills everything satisfies every refusal."""
    proxy = Egress(ALLOWED)
    connect, inside = Flow(Request(host_header=None)), Flow()

    proxy.http_connect(connect)
    proxy.requestheaders(inside)
    plain = Flow(
        Request(scheme="http", host="plain.example", port=8080, host_header="plain.example:8080")
    )
    proxy.requestheaders(plain)

    assert not connect.killed
    assert not inside.killed
    assert not plain.killed


@pytest.mark.parametrize(
    "request_",
    [
        Request(host="books.example.evil.test", host_header=None),
        Request(host="evil.books.example", host_header=None),
        Request(port=8443, host_header=None),
        Request(scheme="http", port=443, host_header=None),
        Request(host="login.books.example", host_header=None),
    ],
    ids=["a suffix", "a subdomain", "another port", "another scheme", "another host"],
)
def test_a_request_to_anything_but_an_exact_origin_is_killed(request_: Request) -> None:
    """Delete this and the rule can become a suffix or a domain match, which is how a look-alike
    host is reached from a browser holding a real session.

    No Host header on any of these, so the origin rule alone decides. With one, the header check
    refuses the subdomain as well, and a suffix match survived mutation behind it on 2026-09-16."""
    flow = Flow(request_)

    Egress(ALLOWED).requestheaders(flow)

    assert flow.killed


def test_a_tunnel_to_a_host_that_is_not_allowed_is_never_opened() -> None:
    """Delete this and the tunnel opens and only the requests inside it are checked, which leaves
    every protocol mitmproxy cannot read inside an open tunnel to anywhere."""
    flow = Flow(Request(host="elsewhere.example", host_header=None))

    Egress(ALLOWED).http_connect(flow)

    assert flow.killed


def test_a_request_naming_another_site_in_its_host_header_is_killed() -> None:
    """Domain fronting. The tunnel is to an allowed host and the Host header asks the shared front
    end for another site. Delete this and the tunnel check alone admits it."""
    flow = Flow(Request(host_header="elsewhere.example"))

    Egress(ALLOWED).requestheaders(flow)

    assert flow.killed
    assert same_site("books.example:443", "books.example", 443, "https")
    assert not same_site("books.example:444", "books.example", 443, "https")


def test_traffic_that_is_not_http_is_killed() -> None:
    """Delete this and raw TCP, UDP or DNS through the proxy has no origin checked at all."""
    proxy = Egress(ALLOWED)
    flows = [Flow(), Flow(), Flow()]

    proxy.tcp_start(flows[0])
    proxy.udp_start(flows[1])
    proxy.dns_request(flows[2])

    assert all(one.killed for one in flows)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json",
        json.dumps({"origin": ORIGIN}),
        json.dumps([ORIGIN, "ftp://files.example"]),
        json.dumps([ORIGIN, "https://books.example/path"]),
        json.dumps([ORIGIN, 42]),
        json.dumps([ORIGIN, "https://books.example:99999"]),
    ],
    ids=["unset", "empty", "not JSON", "not a list", "a scheme", "a path", "not text", "a port"],
)
def test_an_allowlist_with_any_unreadable_part_admits_nothing(raw: str | None) -> None:
    """Fail closed, all or nothing. Delete this and one mistyped origin either opens the proxy to
    everything or leaves a partly read list in force that every log reports as the list."""
    allowlist = parse_allowlist(raw)

    assert allowlist == frozenset()
    assert not admits(allowlist, "https", "books.example", 443)


def test_an_origin_with_no_port_is_its_schemes_default_port() -> None:
    """Delete this and `https://books.example` admits nothing, because a tunnel always names 443."""
    assert parse_allowlist(json.dumps([ORIGIN])) == frozenset({("https", "books.example", 443)})
    assert admits(
        parse_allowlist(json.dumps(["HTTPS://Books.Example"])), "https", "books.example", 443
    )


def test_the_script_a_proxy_loads_builds_its_addon_with_exactly_the_runs_origins() -> None:
    """Run as mitmproxy would load it, with nothing in its environment. Delete this and the one
    appended line can be written so that it parses as the gap check expects and builds something
    else, or fails to load, and a proxy that loads no addon forwards everything.

    Its own namespace, because the script is the whole program the proxy runs."""
    namespace: dict[str, object] = {}
    exec(compile(addon_script((ORIGIN, LOGIN)), "egress_addon.py", "exec"), namespace)  # noqa: S102

    addons = namespace["addons"]
    assert isinstance(addons, list)
    (addon,) = addons
    assert type(addon).__name__ == egress_addon.Egress.__name__
    assert addon.allowlist == parse_allowlist(json.dumps([ORIGIN, LOGIN]))
    assert RUNTIME == "runsc"
