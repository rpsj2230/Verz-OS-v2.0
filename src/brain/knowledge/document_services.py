"""Which readers of the model server this install has, asked in one place.

A document is sent to a part of the model server only when three things hold, and this is where
they are asked together so no caller can ask two of them: the server is one of the optional
services this install runs (`INSTALL_SERVICES`), the feature that lets the product send it work is
on (`brain.ops.features_declared.model_server.MODEL_SERVER`), and the install chose a part that
reads a document (`INSTALL_MODEL_PARTS`).

**Off means exactly what it meant before the model server existed.** With any of the three missing
the answer is no readers, the route for every type is empty, and a file is read by the reader in
this process. Nothing here raises for a setting it cannot read: a worker that refused to start over
a part named wrongly would stop the queue, and the setting is refused where it is saved.

**The door asks for the parts and the job asks for the readers**, because the door decides what a
person may upload and must not build a client to do it, while the job builds one for the life of the
worker (its breaker is state) and builds the readers over it.

Task ids: M7.2.1, M7.2.3, M7.2.4
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.model_server_parsers import Caller, DocumentServices, services_for
from brain.ops.inference import is_switched_on
from brain.ops.model_server import DOCUMENT_PARTS, ModelServerError, Part, read_config
from brain.ops.model_server_client import Reply
from brain.ops.model_server_store import model_server_is_on


class _NobodyToAsk:
    """A caller for a decision that sends nothing: the door asks what is readable, not to read."""

    def ask(self, part: Part, request: object) -> Reply:
        msg = "a question about which types are readable sends no document"
        raise RuntimeError(msg)


#: What the door passes to `services_for`: a type is readable if a reader is chosen for it, and
#: that is asked without a server.
_NO_SERVER: Final[Caller] = _NobodyToAsk()


async def document_parts(
    sessions: async_sessionmaker[AsyncSession] | None, env: Mapping[str, str] | None = None
) -> frozenset[Part]:
    """The parts that read a document which this install runs and may send work to, or none.

    None for a process with no database (the switch cannot be asked, and so is off).
    """
    if sessions is None or not is_switched_on(env):
        return frozenset()
    if not await model_server_is_on(sessions):
        return frozenset()
    try:
        chosen = read_config(env).parts
    except ModelServerError:
        return frozenset()
    return frozenset(part for part in chosen if part in DOCUMENT_PARTS)


def door_services(parts: frozenset[Part]) -> DocumentServices | None:
    """The readers a door decides with: which types are readable, and nothing it could send to."""
    return services_for(parts, _NO_SERVER) if parts else None


async def document_services(
    sessions: async_sessionmaker[AsyncSession],
    server: Callable[[], Caller],
    env: Mapping[str, str] | None = None,
) -> DocumentServices | None:
    """The readers for this install over the server `server()` gives, or None when it has none.

    `server` is a function so that the client is made only when there is a reader to send to: an
    install that runs no document part builds nothing, and one that does keeps the one it built.
    """
    parts = await document_parts(sessions, env)
    if not parts:
        return None
    return services_for(parts, server())
