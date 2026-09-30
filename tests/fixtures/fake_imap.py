"""A mailbox small enough to read, speaking enough IMAP for `imaplib` to read and mark mail in it.

`brain.channels.mailbox.ImapMailbox` is held to what a server on the other end of a real connection
sees: that it signed in with the password configured, over TLS from the first byte, read only the
unseen mail, never set a flag by reading, marked what it handled seen, and never deleted, moved or
expunged anything. A mock of `imaplib` would agree with whatever the reader called; this answers
the protocol, over a socket, on the loopback interface.

Enough and no more: CAPABILITY, LOGIN, SELECT, UID SEARCH UNSEEN, UID FETCH (BODY.PEEK[]),
UID STORE +FLAGS (\\Seen), and LOGOUT. Every command is kept, so a test can say none deleted.

Task ids: none
"""

from __future__ import annotations

import socketserver
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.fixtures.tls_certificate import certificate

LOOPBACK = "127.0.0.1"


@dataclass
class Held:
    """One message in the mailbox: its UID, its exact bytes and its flags."""

    uid: int
    raw: bytes
    flags: set[str] = field(default_factory=set)


@dataclass
class Mailbox:
    """What the stand-in holds and everything it was asked."""

    port: int
    trusted: ssl.SSLContext
    user: str
    password: str
    messages: list[Held] = field(default_factory=list)
    #: Every command, its tag taken off, in order.
    commands: list[str] = field(default_factory=list)

    def add(self, raw: bytes, *, seen: bool = False) -> int:
        uid = len(self.messages) + 1
        self.messages.append(Held(uid=uid, raw=raw, flags={"\\Seen"} if seen else set()))
        return uid

    def seen(self) -> list[int]:
        return [one.uid for one in self.messages if "\\Seen" in one.flags]


class _Handler(socketserver.StreamRequestHandler):
    mailbox: Mailbox
    serving: ssl.SSLContext

    def setup(self) -> None:
        self.request = self.serving.wrap_socket(self.request, server_side=True)
        super().setup()

    def _say(self, line: str) -> None:
        self.wfile.write(line.encode("utf-8") + b"\r\n")
        self.wfile.flush()

    def handle(self) -> None:
        box = self.mailbox
        self._say("* OK stand-in IMAP ready")
        signed_in = False
        while True:
            line = self.rfile.readline()
            if not line:
                return
            tag, _, rest = line.decode("utf-8").rstrip("\r\n").partition(" ")
            command = rest.split(" ")[0].upper()
            box.commands.append(rest)
            if command == "CAPABILITY":
                self._say("* CAPABILITY IMAP4rev1 AUTH=PLAIN")
                self._say(f"{tag} OK done")
            elif command == "LOGIN":
                words = rest.split(" ")
                given = [one.strip('"') for one in words[1:3]]
                if given == [box.user, box.password]:
                    signed_in = True
                    self._say(f"{tag} OK signed in")
                else:
                    self._say(f"{tag} NO [AUTHENTICATIONFAILED] refused")
            elif not signed_in and command != "LOGOUT":
                self._say(f"{tag} BAD sign in first")
            elif command == "SELECT":
                self._say(f"* {len(box.messages)} EXISTS")
                self._say(f"{tag} OK [READ-WRITE] selected")
            elif rest.upper().startswith("UID SEARCH UNSEEN"):
                unseen = " ".join(str(one.uid) for one in box.messages if "\\Seen" not in one.flags)
                self._say(f"* SEARCH {unseen}".rstrip())
                self._say(f"{tag} OK searched")
            elif rest.upper().startswith("UID FETCH"):
                uid = int(rest.split(" ")[2])
                held = next(one for one in box.messages if one.uid == uid)
                self.wfile.write(
                    f"* {uid} FETCH (UID {uid} BODY[] {{{len(held.raw)}}}\r\n".encode()
                    + held.raw
                    + b")\r\n"
                )
                self._say(f"{tag} OK fetched")
            elif rest.upper().startswith("UID STORE"):
                ids = [int(one) for one in rest.split(" ")[2].split(",")]
                for one in box.messages:
                    if one.uid in ids:
                        one.flags.add("\\Seen")
                        self._say(f"* {one.uid} FETCH (UID {one.uid} FLAGS (\\Seen))")
                self._say(f"{tag} OK stored")
            elif command == "LOGOUT":
                self._say("* BYE")
                self._say(f"{tag} OK bye")
                return
            else:
                self._say(f"{tag} BAD not implemented")


@contextmanager
def fake_imap(directory: Path, *, user: str, password: str) -> Iterator[Mailbox]:
    """A mailbox on the loopback interface, TLS from the first byte, for the block."""
    cert, key = certificate(directory, LOOPBACK)
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)
    trusted = ssl.create_default_context(cafile=str(cert))

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    handler: Any = type("Handler", (_Handler,), {"serving": serving})
    server = Server((LOOPBACK, 0), handler)
    box = Mailbox(port=int(server.server_address[1]), trusted=trusted, user=user, password=password)
    handler.mailbox = box
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield box
    finally:
        server.shutdown()
        server.server_close()
