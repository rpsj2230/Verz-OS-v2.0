"""A mail relay small enough to read, speaking enough SMTP for `smtplib` to send a message to it.

`brain.ops.mail.SmtpTransport` is held to what a relay on the other end of a real connection
receives: whether the connection was upgraded to TLS before the password was sent, whether the
password was the one configured, and what arrived. A mock of `smtplib` would agree with whatever
the transport called; this answers the protocol, over a socket, on the loopback interface.

Enough and no more: EHLO, STARTTLS, AUTH PLAIN, MAIL, RCPT, DATA, RSET and QUIT, TLS from the first
byte when asked, a switch to stop offering STARTTLS, and a switch to refuse every recipient. Each
line the client sent is kept, so a test can say a password was never sent in the clear.

Task ids: none
"""

from __future__ import annotations

import base64
import socket
import socketserver
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.fixtures.tls_certificate import certificate

#: The address the relay listens on and the name its certificate carries.
LOOPBACK = "127.0.0.1"


@dataclass
class Delivered:
    """One message the relay accepted."""

    mail_from: str
    rcpt_to: list[str]
    data: bytes
    authenticated_as: str | None


@dataclass
class Relay:
    """What the relay is configured to do, and everything it saw."""

    port: int
    trusted: ssl.SSLContext
    username: str | None = None
    password: str | None = None
    implicit_tls: bool = False
    offer_starttls: bool = True
    refuse_recipients: bool = False
    delivered: list[Delivered] = field(default_factory=list)
    #: Every command line, with whether the connection was encrypted when it arrived.
    lines: list[tuple[bool, str]] = field(default_factory=list)


class _Handler(socketserver.StreamRequestHandler):
    relay: Relay
    serving: ssl.SSLContext

    def _say(self, stream: Any, line: str) -> None:
        stream.write(f"{line}\r\n".encode())
        stream.flush()

    def handle(self) -> None:
        relay = self.relay
        conn: socket.socket = self.request
        secure = False
        if relay.implicit_tls:
            conn = self.serving.wrap_socket(conn, server_side=True)
            secure = True
        stream = conn.makefile("rwb")
        self._say(stream, "220 relay.test ESMTP")
        authenticated: str | None = None
        mail_from = ""
        rcpt: list[str] = []
        while True:
            raw = stream.readline()
            if not raw:
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            relay.lines.append((secure, line))
            upper = line.upper()
            if upper.startswith(("EHLO", "HELO")):
                offers = ["250-relay.test"]
                if not secure and relay.offer_starttls:
                    offers.append("250-STARTTLS")
                if secure:
                    offers.append("250-AUTH PLAIN")
                offers.append("250 8BITMIME")
                for one in offers:
                    self._say(stream, one)
            elif upper == "STARTTLS" and not secure and relay.offer_starttls:
                self._say(stream, "220 go ahead")
                stream.close()
                conn = self.serving.wrap_socket(conn, server_side=True)
                stream = conn.makefile("rwb")
                secure = True
            elif upper.startswith("AUTH PLAIN"):
                given = line.split(" ", 2)[2] if line.count(" ") >= 2 else ""
                if not given:
                    self._say(stream, "334 ")
                    given = stream.readline().decode().strip()
                parts = base64.b64decode(given).split(b"\0")
                user, password = parts[1].decode(), parts[2].decode()
                if secure and user == relay.username and password == relay.password:
                    authenticated = user
                    self._say(stream, "235 authenticated")
                else:
                    self._say(stream, "535 authentication failed")
            elif upper.startswith("MAIL FROM:"):
                if relay.username is not None and authenticated is None:
                    self._say(stream, "530 authentication required")
                    continue
                mail_from = line[10:].strip().strip("<>").split(" ")[0].strip("<>")
                rcpt = []
                self._say(stream, "250 ok")
            elif upper.startswith("RCPT TO:"):
                if relay.refuse_recipients:
                    self._say(stream, "550 no such mailbox")
                    continue
                rcpt.append(line[8:].strip().strip("<>"))
                self._say(stream, "250 ok")
            elif upper == "DATA":
                self._say(stream, "354 go ahead")
                data = bytearray()
                while True:
                    chunk = stream.readline()
                    if not chunk or chunk == b".\r\n":
                        break
                    data.extend(chunk)
                relay.delivered.append(Delivered(mail_from, list(rcpt), bytes(data), authenticated))
                self._say(stream, "250 queued")
            elif upper == "RSET":
                self._say(stream, "250 ok")
            elif upper == "QUIT":
                self._say(stream, "221 bye")
                return
            else:
                self._say(stream, "502 not implemented")


@contextmanager
def fake_relay(directory: Path, **configured: Any) -> Iterator[Relay]:
    """A relay on the loopback interface, with a certificate for its address, for the block."""
    cert, key = certificate(directory, LOOPBACK)
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)
    trusted = ssl.create_default_context(cafile=str(cert))

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    handler = type("Handler", (_Handler,), {"serving": serving})
    server = Server((LOOPBACK, 0), handler)
    relay = Relay(port=int(server.server_address[1]), trusted=trusted, **configured)
    handler.relay = relay  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield relay
    finally:
        server.shutdown()
        server.server_close()
