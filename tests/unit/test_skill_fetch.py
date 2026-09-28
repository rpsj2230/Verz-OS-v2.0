"""The transport a skill import runs over, against a TLS server on the loopback interface.

Nothing here reaches a host: the server is started by the test on 127.0.0.1 and answers as a name
ending in `.invalid`, which no resolver answers, so a transport that looked the name up again could
not have connected at all. That is the property `brain.ops.skill_fetch` exists for.

Task ids: M12.2.2, M12.2.3
"""

from __future__ import annotations

import http.server
import ssl
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from brain.ops.skill_fetch import USER_AGENT, HttpsFetcher, SystemResolver
from brain.ops.webhook_delivery import SystemResolver as DeliveryResolver
from brain.tools.fetch import FetchedBytes, Fetcher
from brain.tools.skills import SkillError
from tests.fixtures.tls_certificate import certificate

#: A name no resolver answers. See the module docstring.
NAME = "skills.brain-test.invalid"


@dataclass
class Answer:
    status: int = 200
    body: bytes = b"---\nname: x\n---\n"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Server:
    port: int
    trusted: ssl.SSLContext
    seen: list[tuple[str, dict[str, str]]]
    answer: Answer


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Server]:
    """An HTTPS server on the loopback interface answering GETs as `NAME`."""
    cert, key = certificate(tmp_path, NAME)
    seen: list[tuple[str, dict[str, str]]] = []
    answer = Answer()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append((self.path, dict(self.headers.items())))
            self.send_response(answer.status)
            for header, value in answer.headers.items():
                self.send_header(header, value)
            self.send_header("Content-Length", str(len(answer.body)))
            self.end_headers()
            self.wfile.write(answer.body)

        def log_message(self, *args: Any) -> None:
            return None

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)
    httpd.socket = serving.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield Server(
            int(httpd.server_address[1]),
            ssl.create_default_context(cafile=str(cert)),
            seen,
            answer,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()


def url(server: Server, path: str = "/o/r/main/SKILL.md") -> str:
    return f"https://{NAME}:{server.port}{path}"


def test_a_get_goes_to_the_checked_address_speaking_as_the_name(server: Server) -> None:
    """**The connection goes to the address, and TLS and HTTP speak as the name.** Delete this and
    a transport that connects by name reopens DNS rebinding under every skill import."""
    got = HttpsFetcher(context=server.trusted).get_once(
        url(server, "/o/r/main/SKILL.md?x=1"), address="127.0.0.1", max_bytes=1000
    )

    assert got == FetchedBytes(
        body=server.answer.body, final_url=url(server, "/o/r/main/SKILL.md?x=1")
    )
    ((path, headers),) = server.seen
    assert path == "/o/r/main/SKILL.md?x=1"
    assert headers["Host"] == f"{NAME}:{server.port}"
    assert headers["User-Agent"] == USER_AGENT


def test_a_redirect_is_handed_back_as_a_whole_address_and_not_followed(server: Server) -> None:
    """Delete this and the transport follows a redirect itself, so the host list and the range rule
    are applied to the first address only; or a relative `Location` reaches the rule as a path."""
    server.answer.status = 302
    server.answer.headers = {"Location": "/moved/SKILL.md"}

    got = HttpsFetcher(context=server.trusted).get_once(
        url(server), address="127.0.0.1", max_bytes=1000
    )

    assert got == url(server, "/moved/SKILL.md")
    assert len(server.seen) == 1


def test_a_status_that_is_not_an_answer_is_a_refusal_naming_the_status_and_not_the_body(
    server: Server,
) -> None:
    """Delete this and a 404 page is parsed as a skill, or the far side's error text reaches the
    person importing as though this install had written it."""
    server.answer.status = 404
    server.answer.body = b"secret internal detail"

    with pytest.raises(SkillError, match="answered 404") as refused:
        HttpsFetcher(context=server.trusted).get_once(
            url(server), address="127.0.0.1", max_bytes=1000
        )
    assert "secret" not in str(refused.value)


def test_a_body_is_read_to_one_byte_past_the_ceiling_and_no_further(server: Server) -> None:
    """The fetch refuses anything longer than its ceiling by counting, so the transport hands back
    one byte more than it and stops. Delete this and a host sending gigabytes is read in full."""
    server.answer.body = b"x" * 5000

    got = HttpsFetcher(context=server.trusted).get_once(
        url(server), address="127.0.0.1", max_bytes=10
    )

    assert isinstance(got, FetchedBytes)
    assert len(got.body) == 11


def test_a_certificate_for_another_name_is_a_refusal_and_not_an_exception(
    server: Server, tmp_path: Path
) -> None:
    """Delete this and an address answering for a different name is trusted, or the refusal is a
    traceback that stops the request with a 500."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    other, _ = certificate(elsewhere, "other.brain-test.invalid")
    distrusting = ssl.create_default_context(cafile=str(other))

    with pytest.raises(SkillError, match="could not be reached"):
        HttpsFetcher(context=distrusting, timeout_seconds=5).get_once(
            url(server), address="127.0.0.1", max_bytes=1000
        )
    assert server.seen == []


def test_the_transport_and_the_resolver_are_the_ones_the_fetch_rule_expects() -> None:
    """The route hands these to `brain.tools.fetch`; the resolver is the delivery worker's, reused.
    Delete this and a second resolver with its own idea of which answers count can arrive here."""
    assert isinstance(HttpsFetcher(), Fetcher)
    assert SystemResolver is DeliveryResolver
