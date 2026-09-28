"""Making a binding single-use, and taking one away again.

`brain.gate.ingress` already has the hard parts of binding a chat identity to a person: the
nonce is minted inside an authenticated session and carried outward to the channel, never
sent to an address that asked to be bound; it is compared in constant time; and it is pinned
to the channel it was minted for, so the weakest channel cannot become the way in to every
other one.

Two things were missing, and both are in the leaf's own words: **single use**, and
**unbinding and rebinding**.

**A nonce that is merely valid is not single-use, and the difference is the whole attack.**
`bind` checks that the value matches, has not expired and is on the right channel, and every
one of those is still true the second time it is presented. The nonce travels *through the
chat channel* by design, so it is visible to anything that can read the message: a second
device signed into the same account, a workspace administrator, a backup, a bot with history
access. Whoever reads it inside the ten-minute window can present it from their own account
and bind themselves to somebody else's principal, and the real person's binding still works,
so nothing looks wrong from either side. Ten minutes of exposure is the cost of the outward
direction, which is right; single use is what bounds it to one.

Consumption is therefore a **test-and-set that must be atomic**, not a read followed by a
write. Two presentations racing on a check-then-mark both see an unconsumed nonce and both
bind. `NonceLedger.consume` returns whether *this* caller was the one that consumed it, so
the atomicity lives in the implementation where the storage engine can provide it, and this
module cannot express the racy version: there is no `was_consumed` to read.

**One live binding per principal per channel.** A person has one Lark account. Allowing two
means an old account, which is the one plausibly compromised or belonging to a replaced
device, keeps working forever while the new one also works, so nobody notices. Rebinding
therefore revokes the previous binding on that channel and says so in the result. The cost is
real and accepted: somebody with two legitimate accounts on one channel can bind only the
latest.

**One channel identity never binds to two principals.** This is refused rather than resolved,
because the two readings are "somebody is taking over an account" and "somebody made a
mistake", and there is no evidence here that tells them apart. Resolving it either way
silently picks one.

**Unbinding is deletion, not a flag.** Entitlements in this system are additive only and
nothing subtracts at read time; a revoked-flag on a binding row would be exactly the
subtractive state that `subtractive_state` refuses across the identity package. The record
that a binding existed lives in the audit ledger, which is where a record that must survive
belongs.

**Minting requires a live sign-in, and that is the "outward-only" property having teeth
rather than a docstring.** `ingress.mint_nonce` takes a principal id as a string and says the
caller is responsible for that being an authenticated one. That is a true statement and it is
not a guard: anything that can reach it can mint a nonce naming somebody else's principal,
present it from its own chat account, and be bound to them. The whole direction of this flow
exists to stop that, and it rested on a caller being careful.

`mint_for_session` takes a `Session` instead, and reads the principal off it. There is no
argument to pass the wrong principal in, which is the only form of this rule that survives a
future caller who has not read the docstring.

**A nonce is also re-checked against the session at bind time.** A nonce lives ten minutes.
Somebody who signs in, requests a code and then signs out has ended the sign-in that
authorised the binding, and the code should stop working at that moment rather than at the
end of its ten minutes. The registry's not-before floor is what makes logout mean anything at
all here, and it is the thing that survives a restart or a second replica.

**The stored flow, since CH2: a code is kept, sent to the bot, and redeemed there.** Everything
above was written with the nonce in hand at both ends, and on an install the two ends are a
browser and a chat message minutes apart. `mint_code` keeps the code's digest in
`auth.binding_code` beside the person and the sign-in it was shown in; `code_in` says whether a
private message from a sender bound to nobody is a code, which `brain.channels.inbound.reply_for`
asks through `brain.ops.binding_store.StoredBinder`; `redeem` spends it in one statement, asks
`auth.session` whether that sign-in is still open, and hands the fresh binding and `settle` to the
store, which writes it and retires the one it replaces in one transaction under a lock on the
person and the channel. `0118`'s trigger records both in the audit ledger.

**The row is found by a digest of what was presented, so a wrong value cannot burn a code.**
`code_digest` is over the channel and the presented value alone, so the store finds a row only
for a value that is the code, and "validate, then consume" holds by construction: there is no
row a wrong value could spend. `nonce_digest` is kept for `NonceLedger`, whose callers hold the
nonce and know whose it is; the store cannot, because the whole point is that the message does
not say.

**One answer for every code that does not bind.** A code nobody minted, one already used, one
past its ten minutes, one minted for another channel, one whose sign-in has ended and one for an
account already somebody else's all return None, and the chat answers every one of them with
`brain.channels.inbound.CODE_REFUSED_TOLD`, whatever the reason. See
`EVERY_CODE_THAT_DOES_NOT_BIND_IS_ONE_ANSWER`. The reason is logged by its shape for an operator,
never with the code or the identity.

Task ids: M10.3.1, M10.3.2, M10.3.4
"""

from __future__ import annotations

import enum
import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

import structlog

from brain.gate.context import Channel
from brain.gate.ingress import (
    NONCE_BYTES,
    NONCE_TTL,
    Binding,
    BindingNonce,
    BindingRefusedError,
    ChannelEvent,
    bind,
    mint_nonce,
)
from brain.identity.sessions import Session, SessionRegistry

log = structlog.get_logger()

#: Derived from `ingress.NONCE_TTL` rather than restated, so the two cannot drift. A
#: consumption record shorter than the nonce's own life would let a replay through in the gap
#: between the record being pruned and the nonce expiring.
NONCE_TTL_SECONDS: Final = NONCE_TTL.total_seconds()

#: How long a consumption record must outlive the nonce it records. Zero would be enough in
#: principle, because an expired nonce is refused by `bind` anyway, but the two clocks are
#: not the same clock: the ledger's pruning runs on the storage side. Slack means a record is
#: never pruned while the nonce it guards could still pass its own expiry check.
CONSUMPTION_SLACK: Final = 60


class NonceLedger(Protocol):
    """Records that a nonce has been used, and answers whether this caller was first.

    **There is deliberately no `was_consumed` here.** A protocol with a read and a separate
    write is a protocol whose only correct use is a transaction the caller has to remember,
    and whose racy use type-checks perfectly. `consume` returning a bool means the storage
    engine performs the test and the set together, and a caller cannot spell the version with
    a gap in the middle.

    Implementations: a unique insert whose duplicate-key failure means false, or `SET NX` on
    a key with a TTL. Both are one round trip and both are atomic without a transaction.
    """

    def consume(self, nonce_digest: str, *, now: datetime, ttl_seconds: int) -> bool: ...


def nonce_digest(nonce: BindingNonce) -> str:
    """What the ledger stores instead of the nonce.

    A digest rather than the value, because the ledger is a table of live credentials
    otherwise: anything that can read it during the ten-minute window can present what it
    finds. Salted by principal and channel so the same nonce value, if two mints ever
    collided, is two records rather than one that consumes both.
    """
    parts = (nonce.principal_id, nonce.channel.value, nonce.value)
    blob = "".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionNonce:
    """A nonce, and the sign-in that authorised it.

    The pair travels together because the second half is checked twice: once when the nonce
    is minted, and again when it is presented. A nonce carrying no session would be a nonce
    that outlives the sign-in it came from, and ten minutes is long enough for somebody to
    request a code and then sign out.
    """

    nonce: BindingNonce
    session_id: str


def mint_for_session(
    session: Session,
    channel: Channel,
    *,
    now: datetime,
) -> SessionNonce:
    """Mint a binding code inside a live sign-in, for the person who is signed in.

    **The principal is read off the session and is not a parameter.** `ingress.mint_nonce`
    takes it as a string and documents that the caller must have authenticated them; this
    takes the session and leaves no argument to pass somebody else's id into. A rule enforced
    by a docstring is a rule that holds until the second caller.

    What that stops is the whole point of the outward direction: mint a nonce naming a
    colleague, present it from your own chat account, and their messages now resolve to you.

    **An expired session mints nothing.** Checked with `Session.is_live`, so idle expiry and
    the absolute ceiling are the ones `brain.identity.sessions` already decided rather than a
    second opinion here.
    """
    if not session.is_live(now):
        msg = (
            "this sign-in has expired, so there is no authenticated session to mint in. "
            "The code is carried outward from a live session on purpose: minting outside one "
            "is minting on behalf of somebody who is not there."
        )
        raise BindingRefusedError(msg)
    return SessionNonce(
        nonce=mint_nonce(session.principal_id, channel, now),
        session_id=session.session_id,
    )


def assert_session_still_authorises(
    minted: SessionNonce,
    *,
    now: datetime,
    registry: SessionRegistry,
) -> None:
    """Refuse a code whose sign-in has since ended.

    A nonce lives ten minutes, which is long enough to request a code and then sign out, and
    signing out has to mean the code stops working at that moment rather than at the end of
    its own clock. Otherwise "log me out everywhere" leaves a credential outstanding that
    binds a chat account afterwards.

    Two questions, and the second is the one that survives a restart. `registry.get` finds the
    session if this process knows about it; the not-before floor answers even when it does
    not, because a floor is one timestamp per principal and it is raised by every logout,
    including one that arrived at a different replica. Checking only the first would make this
    guard depend on which process happened to serve the request.
    """
    session = registry.get(minted.session_id)
    if session is None or not session.is_live(now):
        msg = "the sign-in that produced this code has ended"
        raise BindingRefusedError(msg)

    floor = registry.not_before_for(minted.nonce.principal_id)
    if floor is not None and minted.nonce.minted_at < floor:
        msg = (
            "this code was minted before the last sign-out for that person, so the sign-in "
            "that authorised it has been revoked"
        )
        raise BindingRefusedError(msg)


@dataclass(frozen=True)
class BindingOutcome:
    """A completed binding, and what it displaced.

    `revoked` is the binding this one replaced on the same channel, or None. Returned rather
    than quietly dropped because somebody has to write it to the audit ledger, and a
    revocation nobody recorded is a revocation nobody can explain later.
    """

    binding: Binding
    revoked: Binding | None = None


def bind_once(
    nonce: BindingNonce,
    presented: str,
    event: ChannelEvent,
    *,
    now: datetime,
    ledger: NonceLedger,
    existing: Iterable[Binding] = (),
) -> BindingOutcome:
    """Bind, exactly once, and refuse every way this could bind the wrong person.

    **The nonce is consumed after `bind` has validated it, not before.** Consuming first
    would let anybody who can send a message on that channel burn a nonce they cannot use, by
    presenting a wrong value: the real person's next attempt would then fail for a reason
    nobody can see, and the only remedy is minting another, which is the same denial one
    message later. Validate, then consume, then take effect.

    The order after that matters too: the identity check comes before the channel-conflict
    check, because binding one identity to two people is an account takeover and binding a
    second identity for one person is ordinary.
    """
    # Raises BindingRefusedError on a bad value, an expired nonce, or the wrong channel.
    fresh = bind(nonce, presented, event, now)

    ttl_seconds = int(NONCE_TTL_SECONDS) + CONSUMPTION_SLACK
    if not ledger.consume(nonce_digest(nonce), now=now, ttl_seconds=ttl_seconds):
        msg = (
            "this nonce has already been used. It travels through the channel, so anything "
            "that can read the message can present it; one use is what bounds that to the "
            "person it was minted for."
        )
        raise BindingRefusedError(msg)

    return settle(fresh, existing)


def settle(fresh: Binding, existing: Iterable[Binding]) -> BindingOutcome:
    """What a validated binding does to the bindings already live: refused, or what it replaces.

    Split out of `bind_once` so the stored flow asks the same two questions in the same order:
    the store hands this the live rows it read under its lock, and writes what comes back.
    """
    live = tuple(existing)
    taken = _bound_to_somebody_else(fresh, live)
    if taken is not None:
        msg = (
            f"this identity is already bound to {taken.principal_id}. Refused rather than "
            "resolved: an identity moving between people is either a takeover or a mistake, "
            "and nothing here can tell those apart."
        )
        raise BindingRefusedError(msg)

    return BindingOutcome(binding=fresh, revoked=_same_channel_binding(fresh, live))


def _bound_to_somebody_else(fresh: Binding, live: Iterable[Binding]) -> Binding | None:
    """An existing binding for this identity that belongs to a different principal.

    **The channel comparison here is redundant and `_same_channel_binding`'s is not**, which
    is worth stating because the two predicates look identical. `ingress.identity_hash` is
    salted by channel, so two hashes are equal only when the channels already are; matching on
    the hash has therefore matched the channel. Removing it changes nothing, and a mutation
    proved that rather than an argument.

    It is load-bearing three lines further down because that predicate matches on the
    principal and on hashes being *different*, which is true across channels all day: without
    it, adding Lark revokes the person's email binding.

    Kept because the redundancy rests on a property of another module. If `identity_hash` ever
    stopped salting by channel, this would silently become the only thing standing between a
    binding on a weak channel and one on a strong channel, which is the exact failure that
    docstring says the salt exists to prevent. There is a test pinning that premise.
    """
    for other in live:
        if (
            other.channel is fresh.channel
            and other.identity_hash == fresh.identity_hash
            and other.principal_id != fresh.principal_id
        ):
            return other
    return None


def _same_channel_binding(fresh: Binding, live: Iterable[Binding]) -> Binding | None:
    """This principal's previous binding on this channel, which the new one replaces."""
    for other in live:
        if (
            other.channel is fresh.channel
            and other.principal_id == fresh.principal_id
            and other.identity_hash != fresh.identity_hash
        ):
            return other
    return None


def unbind(
    principal_id: str,
    channel: Channel,
    live: Iterable[Binding],
) -> tuple[Binding, ...]:
    """The bindings to delete so this person no longer reaches us on this channel.

    Returns what to delete rather than a flag to set. A revoked binding that stays in the
    table is subtractive state, and every read afterwards has to remember to exclude it;
    forget once and a revoked channel is answering again. The audit ledger is where the fact
    that it existed survives.

    Returns every match rather than the first, so a table that has somehow accumulated two
    for one person is cleaned rather than half-cleaned.
    """
    return tuple(b for b in live if b.channel is channel and b.principal_id == principal_id)


def apply_unbind(
    principal_id: str,
    channel: Channel,
    live: Mapping[str, Binding],
) -> dict[str, Binding]:
    """What the binding table looks like afterwards. Keyed by identity hash, as `resolve` is.

    A pure function over the map so the caller can diff it, and so this is testable without a
    database. Nothing here writes.
    """
    doomed = {b.identity_hash for b in unbind(principal_id, channel, live.values())}
    return {k: v for k, v in live.items() if k not in doomed}


def would_replay(nonce: BindingNonce, consumed: Iterable[str]) -> bool:
    """Whether this nonce has already been recorded as used, for a console to show.

    Read-only and advisory. `bind_once` does not call it: the decision has to be the atomic
    consume, and a check here followed by a consume there is the race this module exists to
    remove. It is here so a console can say "that code has been used" without inventing its
    own idea of what used means.
    """
    return nonce_digest(nonce) in set(consumed)


# ------------------------------------------------------------------ the stored flow (CH2)

#: Why every code that does not bind gets one answer.
EVERY_CODE_THAT_DOES_NOT_BIND_IS_ONE_ANSWER: Final = (
    "A code nobody minted, one already used, one past its ten minutes, one whose sign-in has "
    "ended and one for an account that is somebody else's all come back as one refusal, which the "
    "chat answers with one sentence. Saying which would tell whoever holds the handset that a "
    "code existed, that somebody used it, or that this account is bound to a person, and each of "
    "those is a fact about somebody else."
)

#: Why only the newest code for a channel works.
A_NEWER_CODE_ENDS_THE_OLDER_ONE: Final = (
    "Minting a code for a channel shortens the life of every unused code the same person holds "
    "for it to now, so the code on the screen is the only one that binds. A person who asks twice "
    "has one code in circulation rather than two, and a code shown on a screen somebody walked "
    "away from stops working the moment they ask for another."
)

#: The length of a code as `ingress.mint_nonce` makes one: `token_urlsafe(NONCE_BYTES)` is the
#: unpadded base64 of that many bytes, four characters for every three, rounded up.
CODE_CHARS: Final = -(-NONCE_BYTES * 4 // 3)

#: A whole message that is one code: the URL-safe alphabet, exactly `CODE_CHARS` long.
_CODE_RE: Final = re.compile(rf"[A-Za-z0-9_-]{{{CODE_CHARS}}}")


def code_in(text: str) -> str | None:
    """The code this message is, or None. A message that is one code and nothing else.

    Only the whole message, stripped, and never a code found inside a sentence: a question that
    happens to contain twenty-two letters and digits in a row is a question, and reading codes
    out of prose would spend somebody's code on a sentence that quoted it.
    """
    candidate = text.strip()
    return candidate if _CODE_RE.fullmatch(candidate) else None


def code_digest(channel: Channel, presented: str) -> str:
    """What `auth.binding_code` keeps, and finds a row by: the channel and the value, digested.

    Over what was presented and nothing else, because the store has to find the row from the
    message alone, which does not say whose code it is. Salted by the channel, so a code minted
    for one channel is not found when it is sent on another. Length-prefixed for the usual reason.
    """
    parts = (channel.value, presented)
    blob = "".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClaimedCode:
    """A code the store has just spent, and what it was minted for. Returned once, to one caller."""

    principal_id: str
    session_id: str
    minted_at: datetime
    channel: Channel


class BindingCodes(Protocol):
    """Where codes are kept. `brain.ops.binding_store.StoredCodes` over `auth.binding_code`.

    `claim` is the test-and-set `NonceLedger.consume` is, for the reason given there: there is no
    way to ask whether a code is spent without spending it, so the racy check cannot be written.
    """

    async def keep(self, minted: SessionNonce, *, digest: str, expires_at: datetime) -> None:
        """Keep one code's digest, and end every unused code this person holds for its channel."""
        ...

    async def claim(self, digest: str, *, now: datetime) -> ClaimedCode | None:
        """Spend the unused, unexpired code with this digest and say whose it was, or None."""
        ...


class SignIns(Protocol):
    """Whether a sign-in is still open. `brain.ops.binding_store.StoredSignIns`, `auth.session`."""

    async def still_open(self, session_id: str, principal_id: str, *, now: datetime) -> bool:
        """True when this session is this person's, not ended and not past its ceiling."""
        ...


@dataclass(frozen=True)
class BoundPerson:
    """One person bound on a channel, as an administrator's list shows them. No identity."""

    principal_id: str
    display_name: str
    bound_at: datetime


class BindingTable(Protocol):
    """Where chat bindings are kept. `brain.ops.binding_store.StoredBindings`.

    Decides nothing. `bind` is handed `settle` and calls it with the live rows it read under its
    lock, so the decision is this module's and the transaction is the store's.
    """

    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        """The live binding for this identity digest on this channel, or None."""
        ...

    async def for_principal(self, principal_id: str) -> tuple[Binding, ...]:
        """This person's live chat bindings, in channel order."""
        ...

    async def on_channel(
        self, channel: Channel, *, limit: int
    ) -> tuple[tuple[BoundPerson, ...], bool]:
        """Who is bound on this channel, by name, and whether the load came back full."""
        ...

    async def bind(
        self,
        fresh: Binding,
        *,
        decide: Callable[[tuple[Binding, ...]], BindingOutcome],
        trace_id: str,
    ) -> BindingOutcome | None:
        """Write `decide`'s outcome in one transaction, or None when a race left nothing to write.

        `BindingRefusedError` from `decide` propagates and nothing is written.
        """
        ...

    async def unbind(
        self, principal_id: str, channel: Channel, *, actor: str, ent_hash: str, trace_id: str
    ) -> tuple[Binding, ...]:
        """Retire this person's bindings on this channel, attributed, and return them."""
        ...


class Refused(enum.StrEnum):
    """Why a code did not bind, for an operator's log and never for the sender."""

    UNKNOWN_USED_OR_EXPIRED = "unknown_used_or_expired"
    SIGNED_OUT = "signed_out"
    REFUSED = "refused"
    RACED = "raced"


async def mint_code(
    session: Session,
    channel: Channel,
    *,
    now: datetime,
    codes: BindingCodes,
) -> SessionNonce:
    """Mint a code in this live sign-in and keep its digest; the value is returned once, to show.

    `mint_for_session` decides, so the principal comes off the session and an expired session
    mints nothing. The value is never kept: `keep` is handed its digest. See
    `A_NEWER_CODE_ENDS_THE_OLDER_ONE` for what keeping it does to an older code.
    """
    if channel is Channel.CONSOLE:
        msg = "the console is where a code is shown, not a chat a code binds"
        raise BindingRefusedError(msg)
    minted = mint_for_session(session, channel, now=now)
    await codes.keep(
        minted,
        digest=code_digest(channel, minted.nonce.value),
        expires_at=minted.nonce.minted_at + NONCE_TTL,
    )
    return minted


async def redeem(
    event: ChannelEvent,
    presented: str,
    *,
    now: datetime,
    codes: BindingCodes,
    sign_ins: SignIns,
    table: BindingTable,
    trace_id: str,
) -> BindingOutcome | None:
    """Bind this message's sender with the code they presented, or None for every way it cannot.

    `presented` is `code_in`'s answer about the message; only a sender bound to nobody, in a
    conversation they alone read, is asked, and the caller has asked both. Spends the code first,
    which cannot burn somebody else's (see the module docstring), then asks whether the sign-in
    that minted it is still open, then `bind` validates the value, its age and its channel, and
    the store writes `settle`'s outcome under its lock. See
    `EVERY_CODE_THAT_DOES_NOT_BIND_IS_ONE_ANSWER` for why every None is one.
    """
    claimed = await codes.claim(code_digest(event.channel, presented), now=now)
    if claimed is None:
        _refused(event, Refused.UNKNOWN_USED_OR_EXPIRED)
        return None
    if not await sign_ins.still_open(claimed.session_id, claimed.principal_id, now=now):
        _refused(event, Refused.SIGNED_OUT)
        return None
    nonce = BindingNonce(
        value=presented,
        principal_id=claimed.principal_id,
        minted_at=claimed.minted_at,
        channel=claimed.channel,
    )
    try:
        fresh = bind(nonce, presented, event, now)
        outcome = await table.bind(
            fresh, decide=lambda live: settle(fresh, live), trace_id=trace_id
        )
    except BindingRefusedError:
        _refused(event, Refused.REFUSED)
        return None
    if outcome is None:
        _refused(event, Refused.RACED)
        return None
    log.info(
        "channel.bound",
        channel=event.channel.value,
        principal=outcome.binding.principal_id,
        replaced=outcome.revoked is not None,
    )
    return outcome


def _refused(event: ChannelEvent, why: Refused) -> None:
    """Log a code that did not bind by its shape. The caller answers None, the one answer."""
    log.info("channel.code_refused", channel=event.channel.value, reason=why.value)
