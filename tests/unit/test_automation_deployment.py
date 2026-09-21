"""The automation sandbox as deployed, held to the boundary `brain.ops.automation` declares.

That module opens by saying the canvas runs flows a client's own staff assemble, so the code
inside it is written by somebody outside this repository and is treated as hostile: no
database URL, no vault token, no provider key, and an egress allowlist rather than an open
network. It then says plainly that the container has a memory budget and no compose service.

This is that boundary as a deployment, and these tests are what stop the two drifting. A
boundary that exists only as a Python constant is a boundary nothing enforces, which is the
same gap that left `ToolRegistry` unbuilt until yesterday and the retention policy untold to
any store until this morning.

**The network is the load-bearing part.** The allowlist matters, and an allowlist checked
inside the sandbox is one the sandbox can edit. What makes it hold is that `automation` is an
internal network with no route out, so the proxy is the only way through rather than the
polite way through.

Task ids: M32.6.1.1
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.automation import EGRESS_ALLOWLIST
from brain.ops.wiring import COMPONENTS

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.automation.yml"
APP_COMPOSE = REPO / "docker-compose.yml"

#: The network carrying the application and the canvas and nothing else. Named in both
#: compose files, which is why it is written once here: a test that spelled it twice would
#: pass while the two files named different networks.
TOOL_API = "tool-api"
EGRESS_CONF = REPO / "ops" / "automation" / "egress.conf"

#: `acl <name> dstdomain <host>` with no leading dot. The absence of the dot is the point and
#: is asserted separately, so this captures the host as written rather than normalising it.
DSTDOMAIN_RE = re.compile(r"^acl\s+\S+\s+dstdomain\s+(\S+)\s*$", re.MULTILINE)


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return loaded


def _service(name: str) -> dict[str, Any]:
    service: dict[str, Any] = _compose()["services"][name]
    return service


def _app_compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(APP_COMPOSE.read_text(encoding="utf-8"))
    return loaded


def _on(compose: dict[str, Any], network: str) -> set[str]:
    """Every service in one compose file that joins the named network."""
    return {
        name
        for name, service in compose["services"].items()
        if network in (service.get("networks") or [])
    }


# --------------------------------------------------------------- the allowlist is deployed
def test_the_proxy_allows_exactly_the_hosts_the_policy_names() -> None:
    """Two copies of five hostnames, safe only while something compares them.

    Both directions. A host in the config and not in the policy is a route nobody reviewed;
    a host in the policy and not in the config is a source the canvas cannot reach, which
    presents as a flow that mysteriously fails rather than as a missing line.

    Delete this and the proxy config becomes the real allowlist while `automation.py` keeps
    describing a different one."""
    configured = set(DSTDOMAIN_RE.findall(EGRESS_CONF.read_text(encoding="utf-8")))

    assert configured == set(EGRESS_ALLOWLIST)


def test_no_allowlisted_host_is_written_as_a_suffix() -> None:
    """**The bug `brain.ops.automation` spends a paragraph on, in the one place it can
    actually happen.**

    Squid's leading-dot form matches every subdomain. `.xero.com` therefore admits any host
    under it, and the module's own argument is that a suffix check admits
    `notapi.lark.com` because that string genuinely ends with `api.lark.com`. The Python
    side matches exactly; this asserts the deployment does too.

    Delete this and one convenient dot reopens the hole the constant was written to close."""
    configured = DSTDOMAIN_RE.findall(EGRESS_CONF.read_text(encoding="utf-8"))

    suffixed = [host for host in configured if host.startswith(".")]
    assert not suffixed, f"these are written as suffixes and match every subdomain: {suffixed}"


def test_the_proxy_denies_by_default() -> None:
    """An allowlist under a permissive default is decoration. `http_access deny all` has to
    be the last word, because Squid takes the first rule that matches and a later allow would
    never be reached to be noticed as wrong."""
    lines = [
        line.strip()
        for line in EGRESS_CONF.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("http_access")
    ]

    assert lines[-1] == "http_access deny all"


# --------------------------------------------------------------- the network is the boundary
def test_the_canvas_sits_on_an_internal_network_with_no_route_out() -> None:
    """**The line that makes the allowlist enforceable rather than advisory.**

    If the canvas could reach the internet directly, the proxy would be a convention: a flow
    that unsets `HTTP_PROXY` would simply go around it. On an internal network there is
    nowhere to go around to, so the proxy is the only route rather than the preferred one.

    Delete this and `internal: true` can be dropped to fix some unrelated connectivity
    problem, and every remaining test here still passes.

    **The canvas is on two networks now and neither reaches out.** `tool-api` was added on
    2026-09-06 and it is the application's, which joins no outward network either, so the
    proxy is still the only route to anything that is not on this host. The assertion is
    therefore that every network the canvas sits on is one of the two known ones rather than
    that it sits on exactly one, and the membership of `tool-api` is established by
    `test_the_route_to_the_application_carries_the_application_and_nothing_else`."""
    compose = _compose()

    assert compose["networks"]["automation"]["internal"] is True
    assert set(_service("activepieces")["networks"]) == {"automation", TOOL_API}
    assert "egress" not in _service("activepieces")["networks"], (
        "the canvas is on the outward network, so the proxy is no longer the only route"
    )


def test_only_the_proxy_touches_a_network_that_reaches_out() -> None:
    """One service on both sides, and it is the one whose whole job is deciding what crosses.
    A second would be a second route, and the allowlist only constrains this one."""
    compose = _compose()
    outward = [
        name
        for name, service in compose["services"].items()
        if "egress" in (service.get("networks") or [])
    ]

    assert outward == ["automation-egress"]


def test_the_canvas_is_not_on_the_application_stack_at_all() -> None:
    """Being on the application's network would let a flow reach `db:5432` and `cache:6379`
    by hostname, and the absence of credentials would then be the only thing between an
    assembled flow and the database.

    Two defences are better than one, and the network is the one that still holds when
    somebody adds an environment variable in a hurry.

    **`tool-api` is admitted here and is not a hole in that**, which the sibling below is
    what actually establishes. This test says the canvas is on no network of ours except
    that one; the next says that one carries the application alone."""
    for name, service in _compose()["services"].items():
        networks = service.get("networks") or []
        assert "default" not in networks, f"{name} joins the default network"
        assert set(networks) <= {"automation", "egress", TOOL_API}, f"{name} reaches {networks}"


def test_the_route_to_the_application_carries_the_application_and_nothing_else() -> None:
    """**The whole of what makes the canvas reaching us safe.**

    Item 30 of `docs/needs-rupash.md` chose a shared network over the public hostname, and a
    shared network is only as narrow as its membership: every container on one resolves every
    other by hostname, so the property being bought is not "there is a network" but "there is
    nothing else on it". Add `db` to it and an assembled flow can open `db:5432`, and every
    other test in this file still passes.

    Read from both compose files, because the membership is decided in two places and each
    file alone looks correct. The application's file could put `cache` on it and the sandbox
    would never know.

    Delete this and the network stops being a boundary and becomes a name, which is exactly
    the failure the file docstring warns about when it says being on the application's
    network would leave credentials as the only defence."""
    ours = _on(_app_compose(), TOOL_API)
    theirs = _on(_compose(), TOOL_API)

    assert ours == {"app"}, f"the application stack puts {sorted(ours)} on {TOOL_API}"
    assert theirs == {"activepieces"}, f"the sandbox puts {sorted(theirs)} on {TOOL_API}"


def test_the_application_keeps_its_own_network_while_joining_the_shared_one() -> None:
    """Naming any network on a service stops Compose adding the default one, so listing
    `tool-api` alone would cut the application off from its own database and cache.

    That failure is loud, which is the only reason it is a test rather than a comment: it
    would be found by the first deploy. It is here because the fix is one word and the
    symptom is an application that cannot reach PostgreSQL, which reads like a database
    problem and sends somebody to the wrong file.

    Delete this and `default` can be tidied out of a list where it looks redundant."""
    app = _app_compose()["services"]["app"]

    # `pii` is the personal data analyser's internal network, joined since 2026-09-21; see
    # `docker-compose.presidio.yml`.
    assert set(app["networks"]) == {"default", TOOL_API, "pii"}


def test_the_shared_network_is_declared_identically_internal_and_never_external() -> None:
    """Two compose files describing one network is two chances to describe it differently:
    an `internal: true` on one side and not the other, or two `name:` values, and the
    symptom is a canvas that cannot reach the application for a reason neither file shows.

    **Until 2026-09-15 the sandbox marked it `external`, and that was wrong.** `full` composes
    this file after `docker-compose.yml` into one project, Compose merges a top-level network
    with the later file winning, so the merged network was external and nothing created it.
    Compose also refuses any attribute but `name` beside `external`, so it could not have
    carried `internal: true` either. Both files now declare the same body.

    **And internal, because a network with a gateway is a route out.** The canvas on a
    non-internal `tool-api` could reach the internet past the egress proxy, and a flow using
    Node's `fetch` would, because `fetch` ignores `HTTP_PROXY`.

    Delete this and either side can drop `internal: true` or reintroduce `external`, and the
    canvas regains a second route out or `full` stops starting on a clean host."""
    app_network = _app_compose()["networks"][TOOL_API]
    sandbox_network = _compose()["networks"][TOOL_API]

    assert "external" not in sandbox_network, "the sandbox turns the merged network external"
    assert app_network == sandbox_network, (
        f"the application declares {app_network} and the sandbox {sandbox_network}; merged in "
        "one project the later file wins and the result is neither"
    )
    assert app_network["internal"] is True, f"{TOOL_API} has a gateway, so it is a route out"


# --------------------------------------------------------------- no credentials of ours
def test_no_service_is_handed_a_credential_belonging_to_the_application() -> None:
    """The canvas keeps its own store and is given nothing of ours. This checks the file for
    the application's own variable names rather than for the word "password", because the
    sandbox legitimately has a password: its own.

    Delete this and `POSTGRES_PASSWORD` gets interpolated here by somebody wiring the two
    together, which is one line, and one line is how a sandbox stops being one."""
    text = COMPOSE.read_text(encoding="utf-8")

    for forbidden in (
        "${POSTGRES_PASSWORD}",
        "${APP_ROLE_PASSWORD}",
        "${BRAIN_DATABASE_URL}",
        "${DATABASE_URL}",
        "${VALKEY_URL}",
        "${LANGFUSE_S3_SECRET_ACCESS_KEY}",
    ):
        assert forbidden not in text, f"the sandbox is handed {forbidden}"


def test_the_canvas_points_at_its_own_database_and_not_ours() -> None:
    """`automation-db` is on the internal network and exists only for this. The application's
    `db` service is on another network entirely and is not named here."""
    environment = _service("activepieces")["environment"]

    assert environment["AP_POSTGRES_HOST"] == "automation-db"
    assert environment["AP_POSTGRES_DATABASE"] == "activepieces"


def test_every_outbound_request_is_pointed_at_the_proxy() -> None:
    """Set in the deployment rather than left to whoever writes a flow. The internal network
    means unsetting these reaches nothing rather than reaching everything, so this is the
    belt and the network is the braces."""
    environment = _service("activepieces")["environment"]

    assert environment["HTTP_PROXY"] == "http://automation-egress:3128"
    assert environment["HTTPS_PROXY"] == "http://automation-egress:3128"


def test_the_proxy_the_canvas_is_pointed_at_is_on_an_internal_network_they_share() -> None:
    """With `tool-api` internal as well, the proxy is the canvas's only route to anything off
    this host, so it has to be reachable. Read from the proxy address itself rather than from
    a service name spelt again here.

    Delete this and the proxy can be moved to `egress` alone, and every flow that calls an
    allowlisted source fails with a name that does not resolve, which reads as the source
    being down."""
    environment = _service("activepieces")["environment"]
    host = str(environment["HTTPS_PROXY"]).split("://", 1)[1].split(":", 1)[0]
    compose = _compose()
    shared = set(_service("activepieces")["networks"]) & set(_service(host)["networks"])

    assert shared, f"the canvas shares no network with its proxy {host}"
    assert all(compose["networks"][one].get("internal") is True for one in shared)


def test_the_application_on_the_tool_network_is_exempt_from_the_proxy() -> None:
    """**The canvas reaches the application directly, and a client that honours the proxy
    variables would not.** The framework's HTTP client is axios, which reads `HTTP_PROXY` and
    `NO_PROXY`; a tool call to `app:8000` without `app` in `NO_PROXY` goes to the proxy, which
    refuses it because the application is not an allowlisted host, and the step fails.

    Every member of `tool-api` other than the canvas is read from the application's compose
    file, so a second service added there has to be exempted here too.

    Delete this and `app` can be dropped from `NO_PROXY` as tidying, and every piece step that
    uses the framework's client stops reaching the gate."""
    exempt = set(str(_service("activepieces")["environment"]["NO_PROXY"]).split(","))
    on_the_route = _on(_app_compose(), TOOL_API)

    assert on_the_route, f"nothing of ours is on {TOOL_API}, so there is nothing to exempt"
    assert on_the_route <= exempt, f"{sorted(on_the_route - exempt)} would be sent to the proxy"


# --------------------------------------------------------------- sizing
def test_the_canvas_is_sized_to_the_component_it_is_budgeted_as() -> None:
    """`brain.ops.wiring` decides what `activepieces` may take and every profile's arithmetic
    is computed from it. More here is memory no budget accounted for."""
    declared = {c.name: c.memory_mib for c in COMPONENTS}
    limit = _service("activepieces")["deploy"]["resources"]["limits"]["memory"]

    assert int(str(limit).rstrip("M")) == declared["activepieces"]


@pytest.mark.parametrize("service", ["activepieces", "automation-egress", "automation-db"])
def test_every_service_in_the_sandbox_carries_a_memory_limit(service: str) -> None:
    """The rule the whole host depends on. An unlimited container is a neighbour's outage,
    and this file adds three of them at once."""
    limits = _service(service)["deploy"]["resources"]["limits"]

    assert "memory" in limits


def test_nothing_here_is_published_to_the_host() -> None:
    """`expose` publishes to the compose network; `ports` publishes to the world. A canvas
    reachable from the host is one reachable from anywhere the host is, and this one runs
    code somebody outside this repository wrote."""
    for name, service in _compose()["services"].items():
        assert "ports" not in service, f"{name} publishes a port to the host"
