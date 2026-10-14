"""The HTTP face of the model server, on an internal network, with one job: hand a body to a part.

**Five routes, one per part, and a readiness route.** The application posts to the path of the part
it wants and gets that part's answer, with a `memory` block added by the supervisor. The paths are
spelled here and in `brain.ops.model_server_client` and held equal by test, because a path spelled
differently on each side is a 404, which the application classifies as its own fault and does not
retry.

**The body is bounded before it is read.** `Content-Length` is required and is compared with the
ceiling the install set, and a request over it is refused with a 413 without a byte of the body
being read, so the ceiling is a cap on what this process allocates and not a message sent after the
allocation. A request with no length is refused with a 411 for the same reason: a body of unknown
size is a body of any size.

**Nothing here looks inside a body.** It is bytes to the part and bytes back. Whether a document is
what it says is the part's, and whether somebody may read it was decided before it was sent. That is
what lets this program have no connection to the application's database and no copy of its rules.

**The reaper runs here and not in the supervisor** because it is the one thing that needs a thread
of its own for the life of the process, and the supervisor is a plain object a test builds without
starting anything.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final

from inference_server.admit import mem_available_mib
from inference_server.config import ServerConfig
from inference_server.meter import read_sample
from inference_server.parts import readiness_gaps
from inference_server.parts.embedding import recorded_revision
from inference_server.supervisor import Supervisor

#: Which part answers each path. Spelled as `brain.ops.model_server_client.PATH_OF_PART`.
ROUTES: Final[dict[str, str]] = {
    "/embed": "embedding",
    "/parse": "layout",
    "/ocr": "ocr",
    "/extract": "tika",
    "/entities": "entities",
}

#: The readiness route, and the route that says what the container holds now.
READY_PATH: Final = "/ready"
MEMORY_PATH: Final = "/memory"

#: How often the reaper looks for an idle part, in seconds.
REAP_EVERY_SECONDS: Final = 5.0


def ready_body(config: ServerConfig, supervisor: Supervisor) -> tuple[int, dict[str, object]]:
    """Readiness: every chosen part has what it needs on disk. Never loads a part to find out."""
    gaps = readiness_gaps(config)
    body: dict[str, object] = {
        "ready": not gaps,
        "parts": list(config.parts),
        "loaded": supervisor.loaded,
        "gaps": list(gaps),
        # The weights each part holds, as the revision the application records beside a vector
        # (`INSTALL_EMBEDDING_REVISION`). Read from the fetch's record and never computed here, so
        # the health check stays free; None until the weights have been fetched.
        "revisions": revisions_of(config),
    }
    return (200 if not gaps else 503), body


def revisions_of(config: ServerConfig) -> dict[str, str | None]:
    """The revision of every chosen part that has one: today the embedding part's weights."""
    if "embedding" not in config.parts or not config.embedding_file:
        return {}
    return {"embedding": recorded_revision(config.model_dir, config.embedding_file)}


def memory_body() -> dict[str, object]:
    """What the container holds and what the host could give, for a person asking from a shell."""
    sample = read_sample()
    return {
        "anon_mib": None if sample is None else -(-sample.anon // (1024 * 1024)),
        "cache_mib": None if sample is None else -(-sample.file // (1024 * 1024)),
        "host_available_mib": mem_available_mib(),
    }


def make_handler(config: ServerConfig, supervisor: Supervisor) -> type[BaseHTTPRequestHandler]:
    """A request handler bound to this configuration and this supervisor."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # No access log: a request line is a path and a length, and nothing here is worth the
            # noise. A refusal is logged by the supervisor's reply, which the application records.
            return

        def _send(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if status == 503:
                self.send_header("Retry-After", "30")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, body: dict[str, object]) -> None:
            self._send(status, json.dumps(body, separators=(",", ":")).encode("utf-8"))

        def do_GET(self) -> None:
            if self.path == READY_PATH:
                status, body = ready_body(config, supervisor)
                self._json(status, body)
            elif self.path == MEMORY_PATH:
                self._json(200, memory_body())
            else:
                self._json(404, {"refusal": "there is nothing at that path"})

        def do_POST(self) -> None:
            part = ROUTES.get(self.path)
            if part is None:
                self._json(404, {"refusal": "there is nothing at that path"})
                return
            declared = self.headers.get("Content-Length")
            if declared is None or not declared.isdigit():
                self._json(411, {"refusal": "a request states how long its body is"})
                return
            length = int(declared)
            if length > config.max_request_bytes:
                # Not read: the connection is closed after the answer, so the unread body does not
                # become the start of the next request.
                self.close_connection = True
                self._json(413, {"refusal": "that request is larger than this server accepts"})
                return
            body = self.rfile.read(length)
            reply = supervisor.handle(part, body)
            self._send(reply.status, reply.body)

    return Handler


def serve(config: ServerConfig, supervisor: Supervisor) -> ThreadingHTTPServer:
    """A server on the configured port, its reaper running. The caller calls `serve_forever`."""
    server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(config, supervisor))  # noqa: S104
    server.daemon_threads = True
    stop = threading.Event()

    def reap() -> None:
        while not stop.wait(REAP_EVERY_SECONDS):
            supervisor.reap()

    threading.Thread(target=reap, name="reaper", daemon=True).start()
    original = server.server_close

    def close() -> None:
        stop.set()
        supervisor.close()
        original()

    server.server_close = close  # type: ignore[method-assign]
    return server
