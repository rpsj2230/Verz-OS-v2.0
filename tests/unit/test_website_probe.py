"""The website check's transport, against a TLS server on the loopback, and its registration.

Nothing here reaches a host: the server is started by the test on 127.0.0.1 and answers as a name
ending in `.invalid`, which no resolver answers, so a prober that looked the name up again could
not have connected at all. Then the check is followed end to end through `follow` with this prober,
and the registry is shown to carry it only where the application handed it one.

Task ids: M12.4.4
"""

from __future__ import annotations

import asyncio
import http.server
import socket
import ssl
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from brain.ops.website_probe import USER_AGENT, HttpsProber
from brain.tools.fetch import Fetchable
from brain.tools.website_check import (
    WEBSITE_CHECK_TOOL,
    ProbeFailure,
    WebsiteCheckTool,
)
from tests.fixtures.tls_certificate import certificate

#: A name no resolver answers. See the module docstring.
NAME = "site.brain-test.invalid"

#: Where the fixture's certificate runs out, and where the expired one ran out.
FIXTURE_EXPIRY = datetime(3000, 1, 1, tzinfo=UTC)
EXPIRED_AT = datetime(2019, 6, 1, tzinfo=UTC)


@dataclass
class Answer:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Server:
    port: int
    trusted: ssl.SSLContext
    seen: list[tuple[str, str, dict[str, str]]]
    answer: Answer


def expired_certificate(directory: Path, name: str) -> tuple[Path, Path]:
    """A certificate for `name` that ran out on `EXPIRED_AT`, and its key, as PEM."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    made = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2018, 1, 1, tzinfo=UTC))
        .not_valid_after(EXPIRED_AT)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert, private = directory / "expired.pem", directory / "expired.key"
    cert.write_bytes(made.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert, private


def serve(cert: Path, key: Path) -> tuple[http.server.ThreadingHTTPServer, Server]:
    seen: list[tuple[str, str, dict[str, str]]] = []
    answer = Answer()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(("GET", self.path, dict(self.headers.items())))
            self.send_response(answer.status)
            for header, value in answer.headers.items():
                self.send_header(header, value)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"hello")

        def log_message(self, *args: Any) -> None:
            return None

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)
    httpd.socket = serving.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    trusted = ssl.create_default_context(cafile=str(cert))
    return httpd, Server(int(httpd.server_address[1]), trusted, seen, answer)


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Server]:
    """An HTTPS server on the loopback interface answering GETs as `NAME`."""
    httpd, running = serve(*certificate(tmp_path, NAME))
    try:
        yield running
    finally:
        httpd.shutdown()
        httpd.server_close()


def target(port: int, path: str = "/") -> Fetchable:
    return Fetchable(url=f"https://{NAME}:{port}{path}", host=NAME, address="127.0.0.1")


def probed(prober: HttpsProber, where: Fetchable, timeout: float = 5.0) -> Any:
    return asyncio.run(prober.probe(where, timeout_seconds=timeout))


# ------------------------------------------------------------------------ one hop
def test_a_hop_goes_to_the_checked_address_as_the_name_and_reads_its_certificate(
    server: Server,
) -> None:
    """**The connection goes to the address, and TLS and HTTP speak as the name**, and the
    certificate's expiry comes back with the status. Delete this and a prober that connects by
    name reopens DNS rebinding under every website check, or one that reads no certificate
    answers the question an expiring site most needs answered with nothing."""
    answer = probed(HttpsProber(context=server.trusted), target(server.port, "/a?b=1"))
    assert (answer.status, answer.failure) == (200, None)
    assert answer.certificate_not_after == FIXTURE_EXPIRY
    assert answer.elapsed_seconds >= 0
    ((method, path, headers),) = server.seen
    assert (method, path) == ("GET", "/a?b=1")
    assert headers["Host"] == f"{NAME}:{server.port}"
    assert headers["User-Agent"] == USER_AGENT


def test_a_redirect_is_reported_and_not_followed(server: Server) -> None:
    """The chain is where every hop is checked, so a prober that followed a redirect itself would
    contact an address nobody checked. Delete this and that can happen with the check green."""
    server.answer.status = 301
    server.answer.headers["Location"] = "https://elsewhere.invalid/"
    answer = probed(HttpsProber(context=server.trusted), target(server.port))
    assert (answer.status, answer.location) == (301, "https://elsewhere.invalid/")
    assert len(server.seen) == 1


def test_a_certificate_for_another_name_is_a_tls_failure_with_its_expiry(
    server: Server, tmp_path: Path
) -> None:
    """A handshake that fails verification is `ProbeFailure.TLS`, nothing is requested, and the
    certificate's date is still read. Delete this and a certificate for another name is trusted,
    or reported with no date to say what is wrong."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    other, _ = certificate(elsewhere, "other.brain-test.invalid")
    distrusting = ssl.create_default_context(cafile=str(other))
    answer = probed(HttpsProber(context=distrusting), target(server.port))
    assert answer.failure is ProbeFailure.TLS
    assert answer.status is None
    assert answer.certificate_not_after == FIXTURE_EXPIRY
    assert server.seen == []


def test_an_expired_certificate_is_a_tls_failure_dated_when_it_ran_out(tmp_path: Path) -> None:
    """The commonest reason a site fails a check, reported with the day it ran out. Delete this
    and an expired certificate reads as an unexplained failure."""
    cert, key = expired_certificate(tmp_path, NAME)
    httpd, running = serve(cert, key)
    try:
        answer = probed(HttpsProber(context=running.trusted), target(running.port))
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert answer.failure is ProbeFailure.TLS
    assert answer.certificate_not_after == EXPIRED_AT
    assert running.seen == []


def test_nothing_listening_is_a_connection_failure() -> None:
    """A refused connection is `CONNECTION`, not a timeout and not an exception. Delete this and a
    site that is down raises out of the tool instead of being reported down."""
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        port = spare.getsockname()[1]
    answer = probed(HttpsProber(), target(port))
    assert answer.failure is ProbeFailure.CONNECTION


def test_a_site_that_never_answers_is_a_timeout() -> None:
    """A server that accepts and says nothing is `TIMEOUT` at the deadline. Delete this and a
    hanging site holds the check for ever or is reported as refusing connections."""
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        answer = probed(HttpsProber(), target(silent.getsockname()[1]), timeout=0.3)
    assert answer.failure is ProbeFailure.TIMEOUT


# ------------------------------------------------------------------------ registered
def test_the_registry_carries_the_check_only_where_a_prober_was_handed_to_it() -> None:
    """`build_registry` registers the check with the prober the application hands it, and none
    without one. Delete this and the check can drop out of the catalogue on every install, which
    is where it was for its first month, or appear on one with no transport."""
    from brain.ops.webhook_delivery import SystemResolver
    from brain.tools.startup import build_registry

    tool = WebsiteCheckTool(resolver=SystemResolver(), prober=HttpsProber())
    with_check = build_registry(source="brain_demo", website=tool)
    without = build_registry(source="brain_demo")
    assert WEBSITE_CHECK_TOOL in with_check.names()
    assert WEBSITE_CHECK_TOOL not in without.names()


def test_the_application_hands_the_registry_a_website_check_over_https() -> None:
    """The lifespan builds the registry with an `HttpsProber` over the system resolver. Read off
    the call in `brain.app`'s source, because the lifespan needs a database to run. Delete this
    and the application can stop passing one with every other test here green."""
    import ast
    import inspect

    import brain.app as app

    tree = ast.parse(inspect.getsource(app))
    calls = {
        ast.unparse(node.func): node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "build_registry"
    }
    keywords = {one.arg: ast.unparse(one.value) for one in calls["build_registry"].keywords}
    assert keywords["website"] == "website"
    built = [
        ast.unparse(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and [ast.unparse(one) for one in node.targets] == ["website"]
    ]
    assert built == ["WebsiteCheckTool(resolver=SystemResolver(), prober=HttpsProber())"]
