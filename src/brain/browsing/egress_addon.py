"""The rule the per-run egress proxy applies: this run's origins, exactly, and nothing else.

Every runner container sits on a network of its own with no gateway, and the only other member of
that network is one mitmproxy container started for the same run (`brain.browsing.sandbox`). So
this file is not an allowlist beside a route out. It is the route out, and the allowlist is the
whole of what it does.

**It runs inside mitmproxy and imports nothing from this repository.** The proxy container is the
published mitmproxy image, and `brain.browsing.sandbox` hands it this file's source and the run's
origins at creation, so the rule a run is held to is readable here, tested here, and cannot be
changed by editing a configuration file on a server. The flows it is handed are typed below as the
two attributes and one method it uses, which is all the coupling to mitmproxy there is.

**The allowlist is read once, when the proxy starts, and an unreadable one refuses everything.**
`brain.browsing.sandbox.addon_script` appends one line to this file's source, constructing the
addon with the run's origins as a literal, so the list is part of the program the proxy loads and
is parsed once when it loads. Nothing is read from the environment or a file at run time, which is
also the rule `tests/invariants/test_configuration_is_read_in_one_place.py` holds for every module
under `src`. There is no reload: M19.3.1's argument about the enforcer holds for the proxy,
because a list that can be refreshed mid-run is a list whose source the run can try to reach. A
missing, malformed or partly malformed list is the empty set, and the empty set admits nothing.
A proxy that fails open because somebody mistyped one origin is the proxy failing at the one job.

**An origin is a scheme, a host and a port, compared exactly.** No suffix, no registrable domain,
no wildcard, for the reason `brain.browsing.targets.Target.allows_origin` gives at length: a
suffix match is how `bank.example.evil.test` is admitted for `bank.example`.

**The Host header is checked against the tunnel it arrived through.** mitmproxy intercepts TLS, so
each request inside a `CONNECT` is seen, and a request whose Host names a different site from the
tunnel's is refused. Without that, a page on an allowed host that shares a front end with another
site can ask the front end for the other site by header, and the tunnel check alone would admit it.

**Anything that is not HTTP is refused.** Raw TCP, UDP and DNS through the proxy have no origin to
check, and nothing a browser run is for needs them.

Not enforced here, and stated: an allowed hostname whose DNS answers with an address on this host's
private networks is connected to. The proxy's own network has a gateway, and an allowlist entry
whose owner points its name at a private address would reach whatever listens there. Refusing
non-global peer addresses needs a hook on the server connection this has not been verified against.

Task ids: M19.3.5
"""

from __future__ import annotations

import json
from typing import Final, Protocol
from urllib.parse import urlsplit

#: The only schemes an origin may have, with the port each implies.
DEFAULT_PORTS: Final = {"https": 443, "http": 80}

#: One origin as the proxy compares it.
Origin = tuple[str, str, int]

#: Why an unreadable list refuses everything rather than nothing.
A_PROXY_THAT_FAILS_OPEN_HAS_FAILED_AT_ITS_ONLY_JOB: Final = (
    "The proxy is the only route out of a runner's network. A list it could not read, read as no "
    "restriction, turns a typo in one origin into a browser that can reach the whole internet, and "
    "nothing about the run would look different. An unreadable list is the empty list."
)


class ProxiedRequest(Protocol):
    """The parts of a mitmproxy request this rule reads."""

    scheme: str
    host: str
    port: int
    host_header: str | None


class ProxiedFlow(Protocol):
    """The parts of a mitmproxy flow this rule uses: its request, and the way to refuse it."""

    @property
    def request(self) -> ProxiedRequest:
        """The request the flow carries, read and never replaced here."""
        ...

    def kill(self) -> None:
        """Refuse the flow: nothing is sent upstream and the client's connection is closed."""
        ...


class AnyFlow(Protocol):
    """A flow with no request to read: TCP, UDP or DNS. Refused whatever it carries."""

    def kill(self) -> None:
        """Refuse the flow."""
        ...


def parse_allowlist(raw: str | None) -> frozenset[Origin]:
    """The origins in a JSON list, or the empty set if any part of it is unreadable.

    All or nothing. Dropping the one bad entry and keeping the rest would be kinder and would mean
    a list nobody checked is partly in force, which reads in every log as a list that is in force.
    """
    if not raw:
        return frozenset()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return frozenset()
    if not isinstance(values, list):
        return frozenset()
    found: set[Origin] = set()
    for value in values:
        origin = _origin(value)
        if origin is None:
            return frozenset()
        found.add(origin)
    return frozenset(found)


def _origin(value: object) -> Origin | None:
    """One serialised origin as a comparable triple, or None for anything that is not one."""
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = parts.hostname
    if scheme not in DEFAULT_PORTS or not host:
        return None
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        return None
    return (scheme, host.lower(), DEFAULT_PORTS[scheme] if port is None else port)


def admits(allowlist: frozenset[Origin], scheme: str, host: str, port: int) -> bool:
    """Exact membership of one scheme, host and port. Never a suffix, never a wildcard."""
    return (scheme.lower(), host.lower(), port) in allowlist


def same_site(header: str, host: str, port: int, scheme: str) -> bool:
    """Whether a Host header names the host and port of the connection it arrived on."""
    try:
        parts = urlsplit(f"//{header}")
        named_port = parts.port
    except ValueError:
        return False
    named = parts.hostname
    if not named:
        return False
    expected = DEFAULT_PORTS.get(scheme.lower(), port) if named_port is None else named_port
    return named.lower() == host.lower() and expected == port


class Egress:
    """The mitmproxy addon. One instance, holding one frozen allowlist, for the proxy's life."""

    def __init__(self, allowlist: frozenset[Origin]) -> None:
        self.allowlist = allowlist

    def http_connect(self, flow: ProxiedFlow) -> None:
        """A tunnel is only ever opened to an allowed HTTPS origin."""
        request = flow.request
        if not admits(self.allowlist, "https", request.host, request.port):
            flow.kill()

    def requestheaders(self, flow: ProxiedFlow) -> None:
        """Every request, inside a tunnel or not: its origin, and its Host against its tunnel."""
        request = flow.request
        if not admits(self.allowlist, request.scheme, request.host, request.port):
            flow.kill()
            return
        header = request.host_header
        if header is not None and not same_site(header, request.host, request.port, request.scheme):
            flow.kill()

    def tcp_start(self, flow: AnyFlow) -> None:
        flow.kill()

    def udp_start(self, flow: AnyFlow) -> None:
        flow.kill()

    def dns_request(self, flow: AnyFlow) -> None:
        flow.kill()
