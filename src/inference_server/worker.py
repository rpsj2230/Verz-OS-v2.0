"""`python -m inference_server.worker <part>`: one part's process, which lives while it is wanted.

The supervisor starts this, reads a first frame saying the part has loaded, and then sends it one
request at a time as frames on its standard input and reads one answer back on its standard output.
When the supervisor ends the process the part's memory goes back to the kernel, which is the whole
reason it is a process and not an object.

**Standard output belongs to the protocol and nothing else may write to it.** A library that prints
a progress bar or a licence line to it would corrupt a frame, and the supervisor would read the text
as a length. So the real stream is taken at the start and `sys.stdout` is pointed at standard error
before any part's library is imported, and a part that prints writes to the log.

**What a part's backend is.** A module `inference_server.parts.<name>` with `load(config)` returning
an object with `label` (the model's name and revision, which the application records beside every
vector) and `handle(body) -> Answer`. A request the backend can say something true about (this file
is encrypted, this page is blank) is an `Answer` with status 200 and a refusal in its payload,
because that is a fact about the document and the application's decoder is built to read it. An
exception is not that: it is this process failing, which the supervisor reports as an outage and the
application retries, and the text of it is never sent, because an exception message from a parser
quotes the file.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass
from typing import BinaryIO, Final, Protocol

from inference_server.config import ServerConfig, from_environment
from inference_server.framing import FrameError, read_frame, write_frame
from inference_server.parts import NEEDS

#: The ceiling on a frame the supervisor sends: the same one the gateway enforced on the way in.
_FALLBACK_CEILING: Final = 1 << 31


@dataclass(frozen=True)
class Answer:
    """What a backend says about one request. `items` counts the chunks, pages or documents done."""

    status: int
    payload: dict[str, object]
    items: int = 0


class Backend(Protocol):
    """What `inference_server.parts.<name>.load` returns."""

    label: str

    def handle(self, body: bytes) -> Answer: ...


def load_backend(part: str, config: ServerConfig) -> Backend:
    """The backend for this part, imported only now so a part not chosen costs nothing."""
    needs = NEEDS[part]
    module = importlib.import_module(f"inference_server.parts.{needs.module}")
    backend: Backend = module.load(config)
    return backend


def serve(part: str, config: ServerConfig, stdin: BinaryIO, stdout: BinaryIO) -> int:
    """Load, say so, and answer frames until the supervisor closes the pipe."""
    backend = load_backend(part, config)
    write_frame(stdout, json.dumps({"ready": True, "model": backend.label}).encode("utf-8"))
    ceiling = max(config.max_request_bytes, 1) * 2
    while True:
        try:
            body = read_frame(stdin, ceiling=ceiling)
        except FrameError:
            return 1
        if body is None:
            return 0
        try:
            answer = backend.handle(body)
            envelope = {"status": answer.status, "answer": answer.payload, "items": answer.items}
        except Exception as error:
            # The type and nothing else: a parser's message quotes the file it was reading.
            print(f"the {part} part failed: {type(error).__name__}", file=sys.stderr)
            envelope = {
                "status": 503,
                "answer": {"refusal": f"the {part} part failed on that request"},
                "items": 0,
            }
        write_frame(stdout, json.dumps(envelope, separators=(",", ":")).encode("utf-8"))


def main(argv: list[str]) -> int:
    """Entry point. The protocol stream is taken before anything else can write to it."""
    if len(argv) != 2 or argv[1] not in NEEDS:
        print(f"usage: python -m inference_server.worker <{'|'.join(NEEDS)}>", file=sys.stderr)
        return 64
    protocol_out = os.fdopen(os.dup(1), "wb")
    # Descriptor 1 is pointed at standard error as well as the Python-level stream, because a C
    # library (llama.cpp prints while it loads) writes to the descriptor, not to `sys.stdout`.
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    config = from_environment(os.environ)
    return serve(argv[1], config, sys.stdin.buffer, protocol_out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
