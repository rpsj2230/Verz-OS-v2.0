"""One request and one answer between the supervisor and a part, as length-prefixed frames.

**Frames over a pipe and not a port or a socket**, because the part is the supervisor's own child
and nothing else may speak to it. A listening port inside the container would be a second way in to
a process holding a client's document, reachable by anything else that shares the network
namespace; a pipe has one reader and one writer and goes away with the process. Eight bytes of
big-endian length and then that many bytes, so a body of any size and any content passes untouched
and a half-written frame is told from a whole one by the length alone.

**The ceiling is checked on the way in.** A frame longer than the one the install set is refused
before it is read, so a part that wrote a length it did not mean cannot make the supervisor allocate
for it, which is the same refusal the gateway makes of a request's `Content-Length`.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import struct
from typing import BinaryIO, Final

#: The width of the length that precedes every frame.
HEADER_BYTES: Final = 8

_HEADER: Final = struct.Struct(">Q")


class FrameError(Exception):
    """A frame that is cut short, or longer than the ceiling allows."""


def write_frame(stream: BinaryIO, body: bytes) -> None:
    """Write one frame and flush it, so the reader is not left waiting on a buffer."""
    stream.write(_HEADER.pack(len(body)))
    stream.write(body)
    stream.flush()


def _read_exactly(stream: BinaryIO, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            msg = f"the stream ended with {remaining} of {count} bytes still due"
            raise FrameError(msg)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO, *, ceiling: int) -> bytes | None:
    """The next frame, or None when the stream ended cleanly between two of them.

    A stream that ends inside a header or a body is not clean and raises: the far end died with
    something half said, and the caller must not treat a fragment as an answer.
    """
    first = stream.read(1)
    if not first:
        return None
    (length,) = _HEADER.unpack(first + _read_exactly(stream, HEADER_BYTES - 1))
    if length > ceiling:
        msg = f"a frame of {length} bytes is over the ceiling of {ceiling}"
        raise FrameError(msg)
    return _read_exactly(stream, length)
