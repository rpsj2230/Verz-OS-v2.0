"""The general reader: Apache Tika's server, a JVM, asked for the text of a file and nothing else.

**Never run against the real server.** Nothing in this repository has downloaded Tika or run a
JVM, so the command line it is started with, the readiness probe and the status codes it answers
with are written from its documentation and have not been observed. The mapping of a status to a
refusal and the splitting of the text into blocks are the program's own and are tested against a
stand-in HTTP server speaking the same two requests.

**Text only, and no metadata.** Tika can return a document's metadata beside its text (a title,
an author, the program that made it), and that is attacker-chosen prose in a field a naive pipeline
concatenates near a prompt (the application's `parse_layout` module argues it under
`METADATA_IS_ATTACKER_CHOSEN_TEXT_IN_A_FIELD_NOBODY_READS_AS_ONE`). So this asks for `text/plain`
from `/tika` and never for `/rmeta`, and the answer has no key anything but blocks could be read
from.

**The JVM lives and dies with this process.** It is started when the part loads and it shares this
process's process group, which the supervisor ends as a whole, so ending the part ends the JVM and
its memory goes back to the kernel. A JVM that dies on its own ends this process too (exit status
70), because a part that is up and answering nothing is the failure the container's readiness
exists to prevent, and the supervisor starts a fresh one for the next request.

**What it cannot say.** Tika answers 422 for a file it could not process without saying whether
that is a password or damage, so a refusal from here is `unsupported` and never `encrypted`: a
word that is true, where `encrypted` would send somebody to remove a password that may not be
there. Blocks are the paragraphs of the text, all prose; a table in a Word file arrives as the
lines of its cells, which is the quality change `brain.knowledge.parse_paths` records as the
fallback path.

Task ids: M7.2.3
"""

from __future__ import annotations

import http.client
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

from inference_server.config import ServerConfig
from inference_server.parts.documents import (
    BadRequest,
    Draft,
    bad_request,
    blocks_answer,
    laid_out,
    read_document,
    refusal,
)
from inference_server.worker import Answer

LABEL: Final = "tika"

#: Where the jar sits under the models volume.
JAR: Final = ("tika", "tika-server.jar")

#: The JVM's heap ceiling in MiB. Spelled as the 384 in `brain.ops.model_server.SIZING` for this
#: part, whose other 128 is what the heap ceiling does not cover; a test holds the two equal.
HEAP_MIB: Final = 384

#: How long a JVM may take to say it is ready, and how long one document may take.
READY_SECONDS: Final = 120.0
REQUEST_SECONDS: Final = 600.0

#: The exit status of a part whose JVM has gone, which the supervisor reads as the part ending.
JVM_GONE: Final = 70

#: Tika's statuses for a file it will not read. 415 is a type it has no parser for and 422 a file it
#: could not process.
UNSUPPORTED_STATUSES: Final = frozenset({415, 422})

_PARAGRAPH_BREAK: Final = re.compile(r"\n\s*\n")

#: What one request to the server is: a body, a media type, and the status and body that come back.
Send = Callable[[bytes, str], tuple[int, bytes]]


def paragraphs(text: str) -> list[str]:
    """The text as paragraphs, split where a blank line says one ends."""
    return [part for part in _PARAGRAPH_BREAK.split(text) if part.strip()]


class TikaBackend:
    """`Backend`: asks a running Tika server for a file's text and lays it out as blocks."""

    def __init__(
        self, send: Send, alive: Callable[[], bool] = lambda: True, label: str = LABEL
    ) -> None:
        self._send = send
        self._alive = alive
        self.label = label

    def handle(self, body: bytes) -> Answer:
        try:
            document = read_document(body)
        except BadRequest as error:
            return bad_request(error)
        if not self._alive():
            raise SystemExit(JVM_GONE)
        try:
            status, text = self._send(document.content, document.media_type)
        except OSError:
            if not self._alive():
                raise SystemExit(JVM_GONE) from None
            raise
        if status in UNSUPPORTED_STATUSES:
            return refusal("unsupported", "text")
        if status != 200:
            msg = f"the general reader answered {status}"
            raise RuntimeError(msg)
        drafts = [Draft(text=part) for part in paragraphs(text.decode("utf-8", errors="replace"))]
        return blocks_answer(laid_out(drafts))


def free_port() -> int:
    """A port nothing on this host is listening on, for a server that listens only on loopback."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def sender(port: int) -> Send:
    """The request to a Tika server on this host: the file in, plain text out, no metadata."""

    def send(content: bytes, media_type: str) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=REQUEST_SECONDS)
        try:
            connection.request(
                "PUT",
                "/tika",
                body=content,
                headers={"Accept": "text/plain", "Content-Type": media_type},
            )
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    return send


def wait_until_ready(port: int, process: subprocess.Popen[bytes]) -> None:
    """Block until the server answers its version, or raise saying it did not."""
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            msg = "the general reader's JVM ended before it was ready"
            raise RuntimeError(msg)
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
            try:
                connection.request("GET", "/version")
                if connection.getresponse().status == 200:
                    return
            finally:
                connection.close()
        except OSError:
            pass
        time.sleep(0.5)
    process.terminate()
    msg = "the general reader's JVM was not ready in time"
    raise RuntimeError(msg)


def load(config: ServerConfig) -> TikaBackend:
    """Start the JVM from the weights volume and wait for it, then answer through it."""
    jar = Path(config.model_dir, *JAR)
    java = shutil.which("java")
    if java is None:
        msg = "the general reader needs java, which is not on this image's path"
        raise RuntimeError(msg)
    port = free_port()
    # A fixed argv: the program, the heap ceiling and a jar on the read-only volume. Nothing from a
    # request reaches it. `-noFork` keeps the server a single process, so the heap ceiling above is
    # the whole of its memory rather than one of two.
    process = subprocess.Popen(  # noqa: S603
        [
            java,
            f"-Xmx{HEAP_MIB}m",
            "-jar",
            str(jar),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-noFork",
        ],
        stdout=sys.stderr,
        stderr=sys.stderr,
    )
    wait_until_ready(port, process)
    return TikaBackend(sender(port), alive=lambda: process.poll() is None)
