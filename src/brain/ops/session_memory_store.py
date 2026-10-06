"""Session memory: what a person said for one conversation, held for that conversation alone
(M16.1.1), formed and read without telling anybody (M16.3.1).

`brain.memory.formation` decided where it lives and for how long, `session_key` and
`session_expiry`, and nothing kept one: `brain.ops.memory_store.kept_of` drops a session row on
sight and no turn formed any. This is the store, and it owns the Valkey client and no policy, the
split `brain.ops.limits` and `brain.ops.limit_store` keep. What counts as something said for this
conversation is `brain.memory.turn.session_statements`'s decision.

**One person's one conversation, and nobody else's.** The key is `session_key(thread, person)`,
so two people who reach one thread id reach two keys, and a thread id somebody guessed reaches only
the guesser's own, empty one. Nothing here lists keys, matches a pattern or reads a key it did not
build from the person asking. See
`A_SESSION_MEMORY_IS_ONE_PERSONS_ONE_CONVERSATION_AND_GOES_WITH_IT`.

**It goes with the conversation.** It is read only through `SessionRecollection`, which the answer
route binds after it has found the conversation as the asker's own and live, so a conversation
retired has no session memory any reader can reach from the moment it goes, and its bytes expire
with the conversation's idle lifetime, `SESSION_IDLE_SECONDS`, moved forward by every write. **An
erasure request deletes them**: the erasure drain deletes the key of every conversation the person
had, as part of their memories (`brain.ops.erasure_store.SessionMemoryEraser`). Valkey is the only
place it is kept: no table, no log line and no trace carries a statement.

**Silent, which is tier zero.** A session statement is `Change.SESSION_CONTEXT`, `Tier.SESSION`:
it is in no digest (`brain.memory.digest.DIGEST_TIERS` stops above it), no review and no notice,
and it changes nothing anybody else is shown.

**A failure is no session memory and an answer.** Valkey is a cache here as everywhere: an outage
reads as nothing remembered, and a failed write is logged by kind and forgotten, so a person is
never refused an answer because their conversation's notes could not be kept.

Rejected: a table beside `mem.persistent`. It would outlive the conversation by design, need an
erasure declaration and a retention sweep to be made to forget, and be one join away from a list of
what everybody said in every conversation.

Rejected: a delete command on this store's client, for the reason `brain.cache.ValkeyClient`
gives about its own. A conversation retired is unreachable through the read gate. An erasure
request is a promise that the person's data is gone, so the erasure drain alone holds a client that
deletes, and deletes only the keys it names from the person's conversation ids
(`brain.ops.erasure_store.SessionMemoryEraser`).

Task ids: M16.1.1, M16.3.1
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import structlog

from brain.cache import OUTAGES, AsyncValkeyClient
from brain.memory.formation import (
    MAX_SESSION_STATEMENTS,
    SESSION_IDLE_SECONDS,
    session_expiry,
    session_key,
)
from brain.memory.turn import MAX_STATEMENT_CHARS, key_of

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: The rule the coordinator set for this store, and why it holds by construction.
A_SESSION_MEMORY_IS_ONE_PERSONS_ONE_CONVERSATION_AND_GOES_WITH_IT: Final = (
    "Session memory is kept in Valkey only, under a key naming one person and one conversation, "
    "so it is never shared between people: two people on one thread id have two keys, and "
    "nothing here lists or matches keys. It is read only once the conversation has been found "
    "as the asker's own and live, so a retired conversation takes its session memory with it "
    "from every reader at once and the bytes expire with its idle lifetime, and an erasure "
    "request deletes the key of every conversation the person had. No table, log or trace "
    "holds a statement."
)

#: Why a failure is an empty memory.
A_SESSION_MEMORY_THAT_CANNOT_BE_READ_IS_EMPTY: Final = (
    "Valkey is a cache. A read that fails is nothing remembered and a write that fails is "
    "logged by its kind and dropped, so an outage costs a conversation its notes and never "
    "costs a person their answer."
)


def _decoded(raw: bytes | None) -> tuple[str, ...]:
    """The statements a stored value holds, or none for anything that is not a list of strings."""
    if raw is None:
        return ()
    try:
        found = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(found, list):
        return ()
    return tuple(
        one for one in found if isinstance(one, str) and 0 < len(one) <= MAX_STATEMENT_CHARS
    )


def merged(held: Sequence[str], said: Sequence[str]) -> tuple[str, ...]:
    """What the conversation holds once these are added: each statement once, newest kept.

    A statement said again moves to the end rather than being held twice, and past
    `MAX_SESSION_STATEMENTS` the oldest go first.
    """
    fresh = {key_of(one) for one in said}
    kept = [one for one in held if key_of(one) not in fresh]
    return tuple([*kept, *said][-MAX_SESSION_STATEMENTS:])


def ttl_from(now: datetime, *, last_spoken_at: datetime) -> int:
    """Seconds until the conversation's notes expire, never less than one.

    `session_expiry` decides when; this only turns it into what `setex` takes.
    """
    return max(1, int((session_expiry(last_spoken_at) - now).total_seconds()))


class StoredSessions:
    """Session memory over one Valkey client. Owns the client and decides nothing."""

    def __init__(self, client: AsyncValkeyClient) -> None:
        self._client = client

    async def recalled(self, thread_id: str, principal_id: str) -> tuple[str, ...]:
        """This person's notes for this conversation, oldest first. Empty on any failure."""
        try:
            raw = await self._client.get(session_key(thread_id, principal_id))
        except OUTAGES as exc:
            log.warning("session_memory.unread", error=type(exc).__name__)
            return ()
        return _decoded(raw)

    async def remember(
        self, thread_id: str, principal_id: str, said: Sequence[str], *, now: datetime
    ) -> None:
        """Add what was said for this conversation, and move its expiry to a full idle lifetime.

        Nothing is written when nothing was said, so a turn without a session statement does not
        keep an empty conversation alive.
        """
        if not said:
            return
        key = session_key(thread_id, principal_id)
        try:
            held = _decoded(await self._client.get(key))
            value = json.dumps(list(merged(held, said))).encode("utf-8")
            await self._client.setex(key, ttl_from(now, last_spoken_at=now), value)
        except OUTAGES as exc:
            log.warning("session_memory.unkept", error=type(exc).__name__)


@dataclass(frozen=True)
class SessionRecollection:
    """`brain.gate.turn_context.Recollection` over one person's one live conversation.

    Built by the answer route only after it found the conversation as the asker's own and live.
    See `A_SESSION_MEMORY_IS_ONE_PERSONS_ONE_CONVERSATION_AND_GOES_WITH_IT`.
    """

    store: StoredSessions
    thread_id: str
    principal_id: str

    async def hints(self) -> tuple[str, ...]:
        return await self.store.recalled(self.thread_id, self.principal_id)


#: The idle lifetime, re-read here so the expiry argument has its figure beside it.
IDLE_SECONDS: Final = SESSION_IDLE_SECONDS
