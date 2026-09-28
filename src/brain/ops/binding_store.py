"""Where a chat binding, its one-time code and the sign-in behind it are kept, deciding nothing.

`brain.channels.binding` decides everything about a binding: that a code is minted only inside a
live sign-in, that a code binds once, that an identity already somebody else's is refused, that a
rebind retires the account it replaces. It could not be run on an install, because it had nowhere
to keep a code between the browser and the chat, and nowhere to keep the binding it produced:
`brain.channels.inbound.NoBindingsYet` answered every sender as bound to nobody. This module is
both places, and it takes every decision as a callable or leaves it to the database's own checks,
for `brain.ops.limit_store`'s reason: a rule cannot be tested for the case that is always wrong
through a module that opens a connection.

**A binding is a row of `auth.principal_identity`, the table `0002` built for exactly this.** One
live row per channel identity, keyed by `brain.gate.ingress.identity_hash` and never by the
identity, and retired by `deleted_at` rather than removed, which is `0045`'s policy: a retired
row is hidden from every read, so nothing afterwards has to remember to exclude it, and the
record that it existed is `0118`'s `channel_binding` entry in the ledger. **The console channel's
rows are sign-in links and are never touched here**: `brain.identity.sign_in_binding` owns them,
and every statement below either names a chat channel or excludes the console. See
`THE_SIGN_IN_CHANNEL_IS_NOT_A_CHAT`.

**A bind is one transaction under a lock on the person and the channel.** The live rows for the
identity and for the person on the channel are read under `pg_advisory_xact_lock`, handed to the
caller's `decide`, and what it returns is written: the replaced row retired and the new one
inserted, or nothing. Two rebinds of one person racing each other are serialised by the lock; two
people racing for one identity are serialised by the partial unique index, and the loser's insert
writes nothing, which rolls back its retirement too. See `A_BIND_READS_AND_WRITES_UNDER_ONE_LOCK`.

**Every write is attributed in its own transaction, before it.** `brain.tables.audit.attributed_to`
sets the actor, the reach digest and the trace for `0118`'s trigger. A bind is attributed to the
person being bound, because the code they minted in their own sign-in is their authorisation and
nobody else's; an unbind to whoever pressed the control, the person or an administrator.

**A code is spent by one statement.** `claim` is an `UPDATE ... WHERE used_at IS NULL AND
expires_at > now RETURNING`, so of two presentations of one code exactly one gets a row back, and
`0118`'s update policy admits no spent row, so nothing the application role can say brings it
back. `keep` shortens every unused code the person holds for the channel to now before it inserts
the new one, which is `brain.channels.binding.A_NEWER_CODE_ENDS_THE_OLDER_ONE`.

Task ids: M10.3.1, M10.3.2, M10.3.4
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.channels.binding import (
    BindingOutcome,
    BoundPerson,
    ClaimedCode,
    SessionNonce,
    code_in,
    redeem,
    unbind,
)
from brain.channels.inbound import Redeemed
from brain.gate.context import Channel
from brain.gate.ingress import Binding, BindingRefusedError, ChannelEvent
from brain.tables.audit import attributed_to
from brain.tables.binding_code import BindingCodeRow
from brain.tables.identity import PrincipalIdentityRow, PrincipalRow, SessionRow

# ------------------------------------------------------------------ written-down reasons

#: Why no statement here reads or writes a console row.
THE_SIGN_IN_CHANNEL_IS_NOT_A_CHAT: Final = (
    "The console channel's rows in auth.principal_identity are sign-in links, which account at "
    "the identity provider signs in as which person, and brain.identity.sign_in_binding owns them "
    "under its own rules and its own audit action. A chat binding store that could retire one "
    "would be a second way to take somebody's sign-in away, recorded under the wrong action."
)

#: Why a bind reads and writes under one lock.
A_BIND_READS_AND_WRITES_UNDER_ONE_LOCK: Final = (
    "Which binding a new one replaces is decided from the rows live at that moment, so the read "
    "and the write are one transaction under a lock on the person and the channel. Read, decide "
    "and write in three transactions and two new accounts bound at once each see the old one, "
    "each retire it, and both stay live, which is the second account nobody notices."
)

#: The prefix of the advisory lock key a bind and an unbind take, so no other lock collides.
LOCK_PREFIX: Final = "channel_binding"


def _refuse_console(channel: Channel) -> None:
    if channel is Channel.CONSOLE:
        msg = f"the console channel is a sign-in link. {THE_SIGN_IN_CHANNEL_IS_NOT_A_CHAT}"
        raise BindingRefusedError(msg)


def _binding_of(row: Any) -> Binding:
    return Binding(
        channel=Channel(row.channel),
        identity_hash=row.identity_hash,
        principal_id=row.principal_id,
        bound_at=row.bound_at,
    )


async def _lock(session: AsyncSession, principal_id: str, channel: Channel) -> None:
    """The lock a bind and an unbind for this person on this channel both take."""
    key = f"{LOCK_PREFIX}:{principal_id}:{channel.value}"
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})


class _RacedError(Exception):
    """The new row lost to another binding of the same identity; rolls the transaction back."""


# ------------------------------------------------------------------------ the codes


@dataclass(frozen=True)
class StoredCodes:
    """`auth.binding_code`, as the application role. `brain.channels.binding.BindingCodes`."""

    sessions: async_sessionmaker[AsyncSession]

    async def keep(self, minted: SessionNonce, *, digest: str, expires_at: datetime) -> None:
        nonce = minted.nonce
        _refuse_console(nonce.channel)
        now = nonce.minted_at
        older = (
            update(BindingCodeRow)
            .where(
                BindingCodeRow.principal_id == nonce.principal_id,
                BindingCodeRow.channel == nonce.channel.value,
                BindingCodeRow.used_at.is_(None),
                BindingCodeRow.expires_at > now,
            )
            .values(expires_at=func.greatest(BindingCodeRow.minted_at, now))
        )
        fresh = insert(BindingCodeRow).values(
            code_digest=digest,
            channel=nonce.channel.value,
            principal_id=nonce.principal_id,
            session_id=minted.session_id,
            minted_at=now,
            expires_at=expires_at,
        )
        async with self.sessions() as session, session.begin():
            await session.execute(older)
            await session.execute(fresh)

    async def claim(self, digest: str, *, now: datetime) -> ClaimedCode | None:
        spend = (
            update(BindingCodeRow)
            .where(
                BindingCodeRow.code_digest == digest,
                BindingCodeRow.used_at.is_(None),
                BindingCodeRow.expires_at > now,
            )
            .values(used_at=func.greatest(BindingCodeRow.minted_at, now))
            .returning(
                BindingCodeRow.principal_id,
                BindingCodeRow.session_id,
                BindingCodeRow.minted_at,
                BindingCodeRow.channel,
            )
        )
        async with self.sessions() as session, session.begin():
            row = (await session.execute(spend)).one_or_none()
        if row is None:
            return None
        principal_id, session_id, minted_at, channel = row
        return ClaimedCode(
            principal_id=principal_id,
            session_id=session_id,
            minted_at=minted_at,
            channel=Channel(channel),
        )


@dataclass(frozen=True)
class StoredSignIns:
    """`auth.session`, read. `brain.channels.binding.SignIns`."""

    sessions: async_sessionmaker[AsyncSession]

    async def still_open(self, session_id: str, principal_id: str, *, now: datetime) -> bool:
        query = select(SessionRow.id).where(
            SessionRow.id == session_id,
            SessionRow.principal_id == principal_id,
            SessionRow.ended_at.is_(None),
            SessionRow.expires_at > now,
        )
        async with self.sessions() as session, session.begin():
            return (await session.execute(query)).first() is not None


# ------------------------------------------------------------------------ the bindings

_LIVE_CHAT: Final = (
    PrincipalIdentityRow.deleted_at.is_(None),
    PrincipalIdentityRow.channel != Channel.CONSOLE.value,
)

_COLUMNS: Final = (
    PrincipalIdentityRow.channel,
    PrincipalIdentityRow.identity_hash,
    PrincipalIdentityRow.principal_id,
    PrincipalIdentityRow.bound_at,
)


@dataclass(frozen=True)
class StoredBindings:
    """`auth.principal_identity`'s chat rows. `brain.channels.binding.BindingTable`, and
    `brain.channels.inbound.ChannelBindings`, which is its first method."""

    sessions: async_sessionmaker[AsyncSession]

    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        if channel is Channel.CONSOLE:
            return None
        query = select(*_COLUMNS).where(
            *_LIVE_CHAT,
            PrincipalIdentityRow.channel == channel.value,
            PrincipalIdentityRow.identity_hash == digest,
        )
        async with self.sessions() as session, session.begin():
            row = (await session.execute(query)).first()
        return None if row is None else _binding_of(row)

    async def for_principal(self, principal_id: str) -> tuple[Binding, ...]:
        query = (
            select(*_COLUMNS)
            .where(*_LIVE_CHAT, PrincipalIdentityRow.principal_id == principal_id)
            .order_by(PrincipalIdentityRow.channel, PrincipalIdentityRow.bound_at)
        )
        async with self.sessions() as session, session.begin():
            rows = (await session.execute(query)).all()
        return tuple(_binding_of(row) for row in rows)

    async def on_channel(
        self, channel: Channel, *, limit: int
    ) -> tuple[tuple[BoundPerson, ...], bool]:
        if channel is Channel.CONSOLE:
            return (), False
        query = (
            select(
                PrincipalIdentityRow.principal_id,
                PrincipalRow.display_name,
                PrincipalIdentityRow.bound_at,
            )
            .join(PrincipalRow, PrincipalRow.id == PrincipalIdentityRow.principal_id)
            .where(*_LIVE_CHAT, PrincipalIdentityRow.channel == channel.value)
            .order_by(PrincipalRow.display_name, PrincipalIdentityRow.principal_id)
            .limit(limit)
        )
        async with self.sessions() as session, session.begin():
            rows = (await session.execute(query)).all()
        people = tuple(
            BoundPerson(principal_id=principal_id, display_name=name, bound_at=bound_at)
            for principal_id, name, bound_at in rows
        )
        return people, len(rows) >= limit

    async def bind(
        self,
        fresh: Binding,
        *,
        decide: Callable[[tuple[Binding, ...]], BindingOutcome],
        trace_id: str,
    ) -> BindingOutcome | None:
        _refuse_console(fresh.channel)
        live = select(*_COLUMNS).where(
            *_LIVE_CHAT,
            PrincipalIdentityRow.channel == fresh.channel.value,
            or_(
                PrincipalIdentityRow.identity_hash == fresh.identity_hash,
                PrincipalIdentityRow.principal_id == fresh.principal_id,
            ),
        )
        try:
            async with self.sessions() as session, session.begin():
                for statement in attributed_to(
                    actor_id=fresh.principal_id, ent_hash="", trace_id=trace_id
                ):
                    await session.execute(statement)
                await _lock(session, fresh.principal_id, fresh.channel)
                rows = (await session.execute(live)).all()
                # Raises BindingRefusedError, which rolls back and propagates: nothing written.
                outcome = decide(tuple(_binding_of(row) for row in rows))
                if outcome.revoked is not None:
                    await session.execute(_retire(outcome.revoked))
                written = await session.execute(_insert_once(outcome.binding))
                if written.first() is None:
                    raise _RacedError
        except _RacedError:
            return None
        return outcome

    async def unbind(
        self, principal_id: str, channel: Channel, *, actor: str, ent_hash: str, trace_id: str
    ) -> tuple[Binding, ...]:
        _refuse_console(channel)
        live = select(*_COLUMNS).where(
            *_LIVE_CHAT,
            PrincipalIdentityRow.channel == channel.value,
            PrincipalIdentityRow.principal_id == principal_id,
        )
        async with self.sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            await _lock(session, principal_id, channel)
            rows = (await session.execute(live)).all()
            doomed = unbind(principal_id, channel, (_binding_of(row) for row in rows))
            for one in doomed:
                await session.execute(_retire(one))
        return doomed


def _retire(binding: Binding) -> Any:
    """Retire one live chat binding, stamped by the statement, for `0045`'s policy."""
    return (
        update(PrincipalIdentityRow)
        .where(
            *_LIVE_CHAT,
            PrincipalIdentityRow.channel == binding.channel.value,
            PrincipalIdentityRow.identity_hash == binding.identity_hash,
            PrincipalIdentityRow.principal_id == binding.principal_id,
        )
        .values(deleted_at=func.statement_timestamp(), updated_at=func.now())
    )


def _insert_once(binding: Binding) -> Any:
    """Insert one live binding, or nothing when the identity is live for somebody already."""
    return (
        upsert(PrincipalIdentityRow)
        .values(
            channel=binding.channel.value,
            identity_hash=binding.identity_hash,
            principal_id=binding.principal_id,
            bound_at=binding.bound_at,
        )
        .on_conflict_do_nothing(
            index_elements=["channel", "identity_hash"],
            index_where=PrincipalIdentityRow.deleted_at.is_(None),
        )
        .returning(PrincipalIdentityRow.id)
    )


@dataclass(frozen=True)
class StoredBinder:
    """`brain.channels.inbound.ChatBinder` over the three stores, for one request's trace.

    Says whether the message is a code by `brain.channels.binding.code_in`, the one place a code's
    shape is known, and answers every code that did not bind as `REFUSED`, whatever the reason,
    for `brain.channels.binding.EVERY_CODE_THAT_DOES_NOT_BIND_IS_ONE_ANSWER`.
    """

    sessions: async_sessionmaker[AsyncSession]
    trace_id: str

    async def redeem(self, event: ChannelEvent, text: str, *, now: datetime) -> Redeemed:
        presented = code_in(text)
        if presented is None:
            return Redeemed.NOT_A_CODE
        outcome = await redeem(
            event,
            presented,
            now=now,
            codes=StoredCodes(self.sessions),
            sign_ins=StoredSignIns(self.sessions),
            table=StoredBindings(self.sessions),
            trace_id=self.trace_id,
        )
        return Redeemed.REFUSED if outcome is None else Redeemed.BOUND
