"""Binding a chat account with a one-time code, taking it away again, and the Channels screen.

Driven through the real application where a route exists, with the token machinery of
`tests/unit/test_api_routes.py` and the channel pipeline's own stand-ins from
`tests/unit/test_channel_pipeline.py`, over codes, sign-ins and bindings kept in memory; the pure
halves are called directly. The migration is held to the model without a server, and the stores
and `0118`'s trigger run against PostgreSQL at the foot, which **skip without a server**.

Every refusal has a permitted sibling, and every refusal a sender or a reader could see is held
to the answer given for something that does not exist.

Task ids: M10.3.1, M10.3.2, M10.3.4, M10.1.2, M10.1.3, M10.1.4
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

from brain import binding_routes, channel_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import AuditRecorder, ChannelBindingChange
from brain.channels.adapter import adapter_for
from brain.channels.binding import (
    CODE_CHARS,
    EVERY_CODE_THAT_DOES_NOT_BIND_IS_ONE_ANSWER,
    BindingOutcome,
    BoundPerson,
    ClaimedCode,
    SessionNonce,
    code_digest,
    code_in,
    mint_code,
    redeem,
    settle,
    unbind,
)
from brain.channels.inbound import CODE_REFUSED_TOLD, LINKED_TOLD, Inbound, Redeemed
from brain.channels.outbound import Outgoing
from brain.console.channel_health import (
    A_STRANGERS_REFUSED_REQUEST_SAYS_NOTHING_ABOUT_THE_CHANNEL,
    FAULTS,
    ChannelHealthState,
    channel_health,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.ingress import (
    NONCE_TTL,
    UNRECOGNISED_PROMPT,
    Binding,
    BindingRefusedError,
    ChannelEvent,
    identity_hash,
    mint_nonce,
)
from brain.identity.bearer import TokenAuthority
from brain.identity.sessions import Session
from brain.identity.sign_in_binding import own_scope
from brain.member.connections import MemberConnectionError, my_channels
from brain.ops.binding_store import StoredBindings, StoredCodes, StoredSignIns
from brain.ops.channel_store import ChannelRecord, DeliveryEntry, DeliveryView
from brain.ops.credentials import Credentials
from brain.ops.idempotency import Intent
from brain.tables import binding_code as binding_code_table
from brain.tables.binding_code import BindingCodeRow
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause
from brain.tables.identity import one_of
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_channel_pipeline import (
    Directory,
    World,
    body_of,
    fresh_record,
    grant,
    post_event,
    signed,
)
from tests.unit.test_credential_writes import entries
from tests.unit.test_tables import DIALECT, checks, migration_module, rendered, squash, table

MIGRATION_0118 = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0118_channel_binding_codes.py"
)

#: Far outside any plausible wall clock, for the pure halves, which compare nothing with now.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
ALICE = "u_alice"
BOB = "u_bob"
TRACE = "trace-binding-1"

MEMBER = Capability(value="read:member.*")

# ------------------------------------------------------------------------ the stand-ins


def _session(principal: str = ALICE, *, sid: str = "sess-1", opened: datetime = NOW) -> Session:
    return Session(
        session_id=sid,
        principal_id=principal,
        issuer="https://id.example/realms/brain",
        subject="1f2e3d4c-0000-4000-8000-000000000001",
        opened_at=opened,
        expires_at=opened + timedelta(minutes=30),
        absolute_expiry=opened + timedelta(hours=10),
    )


def chat(
    identity: str, text: str, *, channel: Channel = Channel.LARK, at: datetime = NOW
) -> ChannelEvent:
    return ChannelEvent(
        channel=channel,
        channel_identity=identity,
        external_id=f"m-{identity}-{text[:6]}",
        text=text,
        received_at=at,
    )


@dataclass
class Row:
    principal_id: str
    session_id: str
    channel: Channel
    minted_at: datetime
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class MemoryCodes:
    """`BindingCodes` over a dictionary, keeping exactly what `auth.binding_code` keeps."""

    rows: dict[str, Row] = field(default_factory=dict)

    async def keep(self, minted: SessionNonce, *, digest: str, expires_at: datetime) -> None:
        nonce = minted.nonce
        for row in self.rows.values():
            if (
                row.principal_id == nonce.principal_id
                and row.channel is nonce.channel
                and row.used_at is None
                and row.expires_at > nonce.minted_at
            ):
                row.expires_at = max(row.minted_at, nonce.minted_at)
        self.rows[digest] = Row(
            principal_id=nonce.principal_id,
            session_id=minted.session_id,
            channel=nonce.channel,
            minted_at=nonce.minted_at,
            expires_at=expires_at,
        )

    async def claim(self, digest: str, *, now: datetime) -> ClaimedCode | None:
        row = self.rows.get(digest)
        if row is None or row.used_at is not None or row.expires_at <= now:
            return None
        row.used_at = max(row.minted_at, now)
        return ClaimedCode(
            principal_id=row.principal_id,
            session_id=row.session_id,
            minted_at=row.minted_at,
            channel=row.channel,
        )


@dataclass
class MemorySignIns:
    """`SignIns` over the set of sessions still open, as `(session id, principal)`."""

    open: set[tuple[str, str]] = field(default_factory=set)

    async def still_open(self, session_id: str, principal_id: str, *, now: datetime) -> bool:
        return (session_id, principal_id) in self.open


@dataclass
class MemoryTable:
    """`BindingTable` over a list of live bindings, recording each change as the trigger would."""

    live: list[Binding] = field(default_factory=list)
    #: `(change, principal, channel, actor)` for every row bound or retired, in order.
    changes: list[tuple[str, str, str, str]] = field(default_factory=list)

    async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
        return next(
            (b for b in self.live if b.channel is channel and b.identity_hash == digest), None
        )

    async def for_principal(self, principal_id: str) -> tuple[Binding, ...]:
        return tuple(b for b in self.live if b.principal_id == principal_id)

    async def on_channel(
        self, channel: Channel, *, limit: int
    ) -> tuple[tuple[BoundPerson, ...], bool]:
        people = tuple(
            BoundPerson(
                principal_id=b.principal_id, display_name=b.principal_id, bound_at=b.bound_at
            )
            for b in sorted(self.live, key=lambda b: b.principal_id)
            if b.channel is channel
        )
        return people[:limit], len(people) >= limit

    async def bind(
        self,
        fresh: Binding,
        *,
        decide: Callable[[tuple[Binding, ...]], BindingOutcome],
        trace_id: str,
    ) -> BindingOutcome | None:
        rows = tuple(
            b
            for b in self.live
            if b.channel is fresh.channel
            and (b.identity_hash == fresh.identity_hash or b.principal_id == fresh.principal_id)
        )
        outcome = decide(rows)
        if any(
            b.channel is fresh.channel and b.identity_hash == fresh.identity_hash for b in self.live
        ):
            return None
        if outcome.revoked is not None:
            self.live.remove(outcome.revoked)
            self.changes.append(
                ("unbound", fresh.principal_id, fresh.channel.value, fresh.principal_id)
            )
        self.live.append(outcome.binding)
        self.changes.append(("bound", fresh.principal_id, fresh.channel.value, fresh.principal_id))
        return outcome

    async def unbind(
        self, principal_id: str, channel: Channel, *, actor: str, ent_hash: str, trace_id: str
    ) -> tuple[Binding, ...]:
        doomed = unbind(principal_id, channel, self.live)
        for one in doomed:
            self.live.remove(one)
            self.changes.append(("unbound", principal_id, channel.value, actor))
        return doomed


@dataclass
class Binder:
    codes: MemoryCodes = field(default_factory=MemoryCodes)
    sign_ins: MemorySignIns = field(default_factory=lambda: MemorySignIns({("sess-1", ALICE)}))
    table: MemoryTable = field(default_factory=MemoryTable)

    async def mint(self, principal: str = ALICE, channel: Channel = Channel.LARK) -> str:
        minted = await mint_code(_session(principal), channel, now=NOW, codes=self.codes)
        return minted.nonce.value

    async def redeem(self, event: ChannelEvent, *, now: datetime = NOW) -> BindingOutcome | None:
        presented = code_in(event.text)
        if presented is None:
            return None
        return await redeem(
            event,
            presented,
            now=now,
            codes=self.codes,
            sign_ins=self.sign_ins,
            table=self.table,
            trace_id=TRACE,
        )


# ======================================================================== codes (M10.3.1)


def test_a_code_is_one_whole_message_and_never_a_word_inside_a_sentence() -> None:
    """`code_in` reads a message that is a code and nothing else, and its length is measured
    against what `ingress.mint_nonce` actually makes rather than restated.

    Delete this and a question quoting a code spends it, or the pattern drifts from the minted
    shape and no code ever binds."""
    for _ in range(50):
        value = mint_nonce(ALICE, Channel.LARK, NOW).value
        assert len(value) == CODE_CHARS
        assert code_in(value) == value
        assert code_in(f"  {value}\n") == value
        assert code_in(f"my code is {value}") is None
    assert code_in("what is left on the retainer?") is None
    assert code_in("") is None
    assert code_in("a" * (CODE_CHARS + 1)) is None


def test_the_digest_kept_is_the_channels_and_the_codes_and_never_the_code() -> None:
    """A code is kept as sixty-four hex characters, salted by its channel, so a code sent on the
    wrong channel finds no row and a reader of the table finds nothing to present.

    Delete this and the table becomes a list of live credentials, or one channel's code binds on
    another."""
    value = mint_nonce(ALICE, Channel.LARK, NOW).value
    lark = code_digest(Channel.LARK, value)
    assert len(lark) == 64 and all(c in "0123456789abcdef" for c in lark)
    assert value not in lark
    assert code_digest(Channel.WEBHOOK, value) != lark
    assert code_digest(Channel.LARK, value) == lark


def test_a_code_is_minted_in_a_live_sign_in_for_the_person_signed_in_and_kept_as_a_digest() -> None:
    """**M10.3.1.** The principal comes off the session, the store is handed the digest and the
    ten-minute expiry, and the value is never kept. An expired sign-in and the console mint
    nothing.

    Delete this and a code can be minted for somebody who is not there, or kept in the clear."""
    binder = Binder()
    value = run(lambda: binder.mint())
    kept = binder.codes.rows[code_digest(Channel.LARK, value)]
    assert (kept.principal_id, kept.session_id, kept.channel) == (ALICE, "sess-1", Channel.LARK)
    assert kept.expires_at - kept.minted_at == NONCE_TTL
    assert value not in repr(binder.codes.rows)
    stale = _session(opened=NOW - timedelta(hours=11))
    with pytest.raises(BindingRefusedError, match="expired"):
        run(lambda: mint_code(stale, Channel.LARK, now=NOW, codes=binder.codes))
    with pytest.raises(BindingRefusedError, match="console"):
        run(lambda: mint_code(_session(), Channel.CONSOLE, now=NOW, codes=binder.codes))
    assert len(binder.codes.rows) == 1


# ======================================================================== redeeming (M10.3.2)


def test_a_code_sent_from_a_chat_binds_that_account_to_the_person_who_minted_it() -> None:
    """The permitted case every refusal below is measured against. Delete this and a redeemer
    that refuses everything passes every refusal test."""
    binder = Binder()
    value = run(lambda: binder.mint())
    outcome = run(lambda: binder.redeem(chat("ou_alice_phone", value)))
    assert isinstance(outcome, BindingOutcome)
    assert outcome.binding.principal_id == ALICE
    assert outcome.binding.identity_hash == identity_hash(Channel.LARK, "ou_alice_phone")
    assert outcome.revoked is None
    assert binder.table.changes == [("bound", ALICE, "lark", ALICE)]


def test_a_code_binds_once_and_a_second_account_presenting_it_is_refused() -> None:
    """**Single use (M10.3.2).** The code travels through the chat, so a second device or anybody
    with the history can read it; presented again it binds nothing.

    Delete this and the ten-minute window becomes unlimited uses."""
    binder = Binder()
    value = run(lambda: binder.mint())
    assert run(lambda: binder.redeem(chat("ou_alice_phone", value))) is not None
    assert run(lambda: binder.redeem(chat("ou_mallory", value))) is None
    assert [b.identity_hash for b in binder.table.live] == [
        identity_hash(Channel.LARK, "ou_alice_phone")
    ]


def test_a_wrong_value_burns_nobodys_code() -> None:
    """The row is found by the digest of what was presented, so a stranger guessing spends
    nothing, and the real code still binds afterwards.

    Delete this and anybody who can message the bot can switch binding off for everyone."""
    binder = Binder()
    value = run(lambda: binder.mint())
    wrong = ("A" if value[0] != "A" else "B") + value[1:]
    assert run(lambda: binder.redeem(chat("ou_stranger", wrong))) is None
    assert run(lambda: binder.redeem(chat("ou_alice_phone", value))) is not None


def test_a_code_past_its_ten_minutes_binds_nothing() -> None:
    """**Expiry (M10.3.2).** Delete this and a code photographed off a screen works for ever."""
    binder = Binder()
    value = run(lambda: binder.mint())
    late = NOW + NONCE_TTL + timedelta(seconds=1)
    assert run(lambda: binder.redeem(chat("ou_alice_phone", value, at=late), now=late)) is None
    assert binder.table.live == []


def test_a_code_whose_sign_in_has_ended_binds_nothing() -> None:
    """Signing out, or an administrator ending the session, stops the code at that moment.

    Delete this and "sign me out everywhere" leaves a credential that binds a chat afterwards."""
    binder = Binder()
    value = run(lambda: binder.mint())
    binder.sign_ins.open.clear()
    assert run(lambda: binder.redeem(chat("ou_alice_phone", value))) is None
    assert binder.table.live == []


def test_a_code_minted_for_one_channel_binds_nothing_on_another() -> None:
    """Delete this and the weakest channel becomes the way in to every other one."""
    binder = Binder()
    value = run(lambda: binder.mint(channel=Channel.LARK))
    event = chat("person-42", value, channel=Channel.WEBHOOK)
    assert run(lambda: binder.redeem(event)) is None
    assert run(lambda: binder.redeem(chat("ou_alice_phone", value))) is not None


def test_an_account_already_bound_to_somebody_else_is_refused_and_nothing_is_written() -> None:
    """Refused rather than resolved: an account moving between people is a takeover or a
    mistake. Delete this and a colleague's code quietly moves your chat account to them."""
    binder = Binder()
    binder.table.live.append(
        Binding(
            channel=Channel.LARK,
            identity_hash=identity_hash(Channel.LARK, "ou_shared"),
            principal_id=BOB,
            bound_at=NOW,
        )
    )
    value = run(lambda: binder.mint())
    assert run(lambda: binder.redeem(chat("ou_shared", value))) is None
    assert [b.principal_id for b in binder.table.live] == [BOB]
    assert binder.table.changes == []


def test_every_code_that_does_not_bind_is_one_answer_whatever_the_reason() -> None:
    """**DENIED and ABSENT indistinguishable.** Not a code, unknown, used, expired, signed out and
    somebody else's account all come back None, which the chat answers with one prompt.

    Delete this and the redeemer can grow a second return value saying why, and the sender is
    told which of those facts about somebody else is true."""
    binder = Binder()
    used = run(lambda: binder.mint())
    run(lambda: binder.redeem(chat("ou_alice_phone", used)))
    unknown = mint_nonce(ALICE, Channel.LARK, NOW).value
    outcomes = [
        run(lambda: binder.redeem(chat("ou_x", "hello there"))),
        run(lambda: binder.redeem(chat("ou_x", unknown))),
        run(lambda: binder.redeem(chat("ou_x", used))),
    ]
    assert outcomes == [None, None, None]
    assert "somebody else" in EVERY_CODE_THAT_DOES_NOT_BIND_IS_ONE_ANSWER


# ============================================================ rebinding and unbinding (M10.3.4)


def test_binding_a_new_account_retires_the_old_one_on_that_channel_and_no_other() -> None:
    """**Device change.** A new phone binds and the old account stops being answered, and a
    binding on another channel is untouched. Both changes are recorded.

    Delete this and the old account, the one plausibly lost, keeps working beside the new one."""
    binder = Binder()
    old = Binding(
        channel=Channel.LARK,
        identity_hash=identity_hash(Channel.LARK, "ou_old_phone"),
        principal_id=ALICE,
        bound_at=NOW - timedelta(days=30),
    )
    other = Binding(
        channel=Channel.WEBHOOK,
        identity_hash=identity_hash(Channel.WEBHOOK, "person-42"),
        principal_id=ALICE,
        bound_at=NOW - timedelta(days=30),
    )
    binder.table.live.extend([old, other])
    value = run(lambda: binder.mint())
    outcome = run(lambda: binder.redeem(chat("ou_new_phone", value)))
    assert outcome is not None and outcome.revoked == old
    assert set(binder.table.live) == {other, outcome.binding}
    assert binder.table.changes == [
        ("unbound", ALICE, "lark", ALICE),
        ("bound", ALICE, "lark", ALICE),
    ]


def test_minting_a_newer_code_ends_the_older_one() -> None:
    """`A_NEWER_CODE_ENDS_THE_OLDER_ONE`. Delete this and every code a person ever asked for is
    live for its full ten minutes."""
    binder = Binder()
    first = run(lambda: binder.mint())
    second = run(lambda: binder.mint())
    assert run(lambda: binder.redeem(chat("ou_a", first))) is None
    assert run(lambda: binder.redeem(chat("ou_a", second))) is not None


def test_settle_is_the_single_use_modules_own_decision() -> None:
    """The stored flow and `bind_once` ask one function the same two questions.

    Delete this and the two paths can come to disagree about a takeover."""
    fresh = Binding(
        channel=Channel.LARK,
        identity_hash=identity_hash(Channel.LARK, "ou_a"),
        principal_id=ALICE,
        bound_at=NOW,
    )
    taken = Binding(
        channel=Channel.LARK, identity_hash=fresh.identity_hash, principal_id=BOB, bound_at=NOW
    )
    with pytest.raises(BindingRefusedError, match="already bound"):
        settle(fresh, [taken])
    assert settle(fresh, []) == BindingOutcome(binding=fresh)


# ======================================================================== the person's page


def test_a_persons_channels_are_the_ones_on_and_the_ones_they_are_bound_on() -> None:
    """A binding on a channel since switched off is still listed, with no code offered; the
    console is never a chat; somebody else's binding on this page is refused.

    Delete this and a binding that will answer again the day the channel is switched back on is
    hidden from the one person who would remove it."""
    mine = Binding(
        channel=Channel.SLACK,
        identity_hash=identity_hash(Channel.SLACK, "U1"),
        principal_id=ALICE,
        bound_at=NOW,
    )
    rows = my_channels(ALICE, [mine], [Channel.WEBHOOK, Channel.CONSOLE])
    assert [(r.channel, r.bound_at, r.may_bind) for r in rows] == [
        (Channel.SLACK, NOW, False),
        (Channel.WEBHOOK, None, True),
    ]
    theirs = Binding(
        channel=Channel.SLACK, identity_hash=mine.identity_hash, principal_id=BOB, bound_at=NOW
    )
    with pytest.raises(MemberConnectionError, match="wrong person"):
        my_channels(ALICE, [theirs], [])


# ======================================================================== health (M10.1.4)


def view(
    direction: Direction,
    outcome: DeliveryOutcome,
    reason: RefusedBecause | None = None,
    *,
    minute: int,
) -> DeliveryView:
    return DeliveryView(
        entry=DeliveryEntry(Channel.WEBHOOK, direction, outcome, reason),
        recorded_at=NOW + timedelta(minutes=minute),
    )


def test_health_is_read_from_the_record_then_the_newest_delivery_that_says_anything() -> None:
    """Not set up, switched off, quiet, working and failing, each from the deliveries a channel
    really recorded, and a stranger's refused request deciding nothing.

    Delete this and anybody posting junk to the events address turns the screen red, or a
    vendor refusing every reply reads as working."""
    sent = view(Direction.OUTBOUND, DeliveryOutcome.SENT, minute=1)
    junk = view(Direction.INBOUND, DeliveryOutcome.REFUSED, RefusedBecause.BAD_SIGNATURE, minute=2)
    refused = view(
        Direction.OUTBOUND, DeliveryOutcome.REFUSED, RefusedBecause.VENDOR_REFUSED, minute=3
    )
    received = view(Direction.INBOUND, DeliveryOutcome.ACCEPTED, minute=4)
    on, off = fresh_record(), fresh_record(enabled=False)
    assert channel_health(None, [sent]).health is ChannelHealthState.NOT_SET_UP
    assert channel_health(off, [sent]).health is ChannelHealthState.SWITCHED_OFF
    assert channel_health(on, []).health is ChannelHealthState.QUIET
    assert channel_health(on, [junk]).health is ChannelHealthState.QUIET
    assert channel_health(on, [junk, sent]).health is ChannelHealthState.WORKING
    failing = channel_health(on, [sent, junk, refused])
    assert failing.health is ChannelHealthState.FAILING
    assert failing.last_fault == refused
    assert failing.last_sent_at == sent.recorded_at
    recovered = channel_health(on, [refused, received, sent, junk])
    assert recovered.health is ChannelHealthState.WORKING
    assert recovered.last_received_at == received.recorded_at
    assert RefusedBecause.BAD_SIGNATURE not in FAULTS
    assert "junk" in A_STRANGERS_REFUSED_REQUEST_SAYS_NOTHING_ABOUT_THE_CHANNEL


def test_a_bound_sender_nobody_answered_is_a_fault() -> None:
    """Delete this and a channel on which every bound person hears nothing reads as working."""
    unanswered = view(
        Direction.OUTBOUND, DeliveryOutcome.REFUSED, RefusedBecause.NOT_ANSWERABLE, minute=5
    )
    received = view(Direction.INBOUND, DeliveryOutcome.ACCEPTED, minute=4)
    assert (
        channel_health(fresh_record(), [received, unanswered]).health is ChannelHealthState.FAILING
    )


# ======================================================================== through the routes

#: `u_admin` holds the channel authority over everything and a member grant; `u_narrow` a member
#: grant alone; `u_none` nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (grant(Scope.unrestricted()), Grant(capability=MEMBER, scope=own_scope("u_admin"))),
    "u_narrow": (Grant(capability=MEMBER, scope=own_scope("u_narrow")),),
    "u_none": (),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


@dataclass
class MemoryBinder:
    """`ChatBinder` over the memory stores, as `brain.ops.binding_store.StoredBinder` is."""

    binder: Binder

    async def redeem(self, event: ChannelEvent, text: str, *, now: datetime) -> Redeemed:
        if code_in(text) is None:
            return Redeemed.NOT_A_CODE
        bound = await self.binder.redeem(event, now=now)
        return Redeemed.REFUSED if bound is None else Redeemed.BOUND


@dataclass
class Place:
    world: World = field(default_factory=World)
    binder: Binder = field(
        default_factory=lambda: Binder(
            sign_ins=MemorySignIns({("sess-1", "u_narrow"), ("sess-1", "u_admin")})
        )
    )


@pytest.fixture
def place() -> Place:
    return Place()


@pytest.fixture
def client(place: Place) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
    app.include_router(binding_routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        world = place.world
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = world.secrets
        app.state.channel_transport = world.transport
        app.state.operation_ledger = world.ledger
        app.state.credentials = Credentials(world.vault)
        app.state.channel_bindings = place.binder.table
        app.state.channel_binder = MemoryBinder(place.binder)
        app.state.binding_table = place.binder.table
        app.state.binding_codes = place.binder.codes
        yield c


def as_(pid: str, **claims: object) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp'], **claims})}"}


def from_sender(sender: str, text: str, ident: str) -> dict[str, str]:
    return {"id": ident, "sender": sender, "text": text, "conversation": f"conv-{sender}"}


def test_a_person_mints_a_code_in_my_workspace_sends_it_and_is_answered_as_themself(
    client: TestClient, place: Place
) -> None:
    """**The install flow, end to end.** A member asks for a code for the webhook channel, which is
    switched on; it is answered once, marked not to be stored; sent as a message from their chat
    account it is answered with the bound reply, and their next message reaches the answerer as
    them. Their page then shows the channel bound.

    Delete this and every half is tested and the whole never ran."""
    place.world.records.kept[Channel.WEBHOOK] = fresh_record()
    listed = client.get(API_PREFIX + "/me/channels", headers=as_("u_narrow"))
    assert listed.status_code == 200
    assert listed.json()["channels"] == [
        {"channel": "webhook", "bound": False, "bound_at": None, "may_bind": True}
    ]
    minted = client.post(API_PREFIX + "/me/channels/webhook/code", headers=as_("u_narrow"))
    assert minted.status_code == 200
    assert minted.headers["cache-control"] == "no-store"
    code = minted.json()["code"]
    assert code_in(code) == code

    raw, sent = signed(from_sender("person-42", code, "m-code"))
    assert post_event(client, raw, sent).json() == {"status": "accepted", "reply": "sent"}
    assert place.world.transport.texts() == [LINKED_TOLD]
    assert [(b.principal_id, b.channel) for b in place.binder.table.live] == [
        ("u_narrow", Channel.WEBHOOK)
    ]

    class Answerer:
        async def answer(
            self,
            inbound: Inbound,
            *,
            binding: Binding,
            record: ChannelRecord,
            reply_to: str,
            now: datetime,
        ) -> tuple[Outgoing, ...]:
            return (
                Outgoing(
                    channel=Channel.WEBHOOK,
                    to=reply_to,
                    intent=Intent(principal_id=binding.principal_id, intent_ref="answer.1"),
                    text=f"answered as {binding.principal_id}",
                ),
            )

    client.app.state.channel_answerer = Answerer()  # type: ignore[attr-defined]
    raw, sent = signed(from_sender("person-42", "what is left on the retainer?", "m-next"))
    post_event(client, raw, sent)
    assert place.world.transport.texts()[-1] == "answered as u_narrow"
    after = client.get(API_PREFIX + "/me/channels", headers=as_("u_narrow")).json()["channels"]
    assert [(one["channel"], one["bound"]) for one in after] == [("webhook", True)]


def test_a_used_an_unknown_and_a_wrong_code_are_one_answer_and_bind_nobody(
    client: TestClient, place: Place
) -> None:
    """**DENIED and ABSENT indistinguishable, in the chat.** The code used once, presented again
    from another account; a code nobody minted; the real code with one character changed: three
    identical replies, and nobody bound. A message that is no code at all is prompted to bind.

    Delete this and the reply to a reused code tells its sender that somebody bound with it."""
    place.world.records.kept[Channel.WEBHOOK] = fresh_record()
    code = client.post(API_PREFIX + "/me/channels/webhook/code", headers=as_("u_narrow")).json()[
        "code"
    ]
    raw, sent = signed(from_sender("person-42", code, "m-1"))
    post_event(client, raw, sent)
    unknown = mint_nonce("u_x", Channel.WEBHOOK, NOW).value
    wrong = ("A" if code[0] != "A" else "B") + code[1:]
    for n, text in enumerate((code, unknown, wrong, "hello")):
        raw, sent = signed(from_sender(f"person-{n + 90}", text, f"m-x{n}"))
        assert post_event(client, raw, sent).json() == {"status": "accepted", "reply": "sent"}
    assert place.world.transport.texts() == [
        LINKED_TOLD,
        CODE_REFUSED_TOLD,
        CODE_REFUSED_TOLD,
        CODE_REFUSED_TOLD,
        UNRECOGNISED_PROMPT,
    ]
    assert [b.principal_id for b in place.binder.table.live] == ["u_narrow"]


def test_a_code_is_refused_off_a_switched_on_channel_without_a_member_grant_or_a_sign_in(
    client: TestClient, place: Place
) -> None:
    """A channel switched off, one never set up, a name that is no channel, a reader holding no
    member grant, and a token belonging to no sign-in are one answer, and none mints a code.

    Delete this and a service account mints codes, or the route says which channels exist."""
    place.world.records.kept[Channel.WEBHOOK] = fresh_record(enabled=False)
    refusals = [
        client.post(API_PREFIX + "/me/channels/webhook/code", headers=as_("u_narrow")),
        client.post(API_PREFIX + "/me/channels/lark/code", headers=as_("u_narrow")),
        client.post(API_PREFIX + "/me/channels/carrier-pigeon/code", headers=as_("u_narrow")),
        client.post(API_PREFIX + "/me/channels/console/code", headers=as_("u_narrow")),
    ]
    place.world.records.kept[Channel.WEBHOOK] = fresh_record()
    refusals += [
        client.post(API_PREFIX + "/me/channels/webhook/code", headers=as_("u_none")),
        client.post(API_PREFIX + "/me/channels/webhook/code", headers=as_("u_narrow", sid="")),
    ]
    assert {one.status_code for one in refusals} == {404}
    assert len({json.dumps(body_of(one)) for one in refusals}) == 1
    assert place.binder.codes.rows == {}
    assert (
        client.post(API_PREFIX + "/me/channels/webhook/code", headers=as_("u_narrow")).status_code
        == 200
    )


def test_a_person_unbinds_their_own_chat_and_it_is_recorded_as_theirs(
    client: TestClient, place: Place
) -> None:
    """**M10.3.4 for the person.** Their binding is retired, with them as the actor, and a second
    press finds nothing and says so as an absence. Delete this and a lost phone keeps being
    answered as its owner until an administrator notices."""
    place.world.records.kept[Channel.WEBHOOK] = fresh_record()
    place.binder.table.live.append(
        Binding(
            channel=Channel.WEBHOOK,
            identity_hash=identity_hash(Channel.WEBHOOK, "person-42"),
            principal_id="u_narrow",
            bound_at=NOW,
        )
    )
    gone = client.post(API_PREFIX + "/me/channels/webhook/unbind", headers=as_("u_narrow"))
    assert gone.status_code == 200
    assert gone.json()["channels"] == [
        {"channel": "webhook", "bound": False, "bound_at": None, "may_bind": True}
    ]
    assert place.binder.table.changes == [("unbound", "u_narrow", "webhook", "u_narrow")]
    again = client.post(API_PREFIX + "/me/channels/webhook/unbind", headers=as_("u_narrow"))
    assert again.status_code == 404


def test_an_administrator_lists_who_is_bound_and_unbinds_one_and_a_stranger_is_told_nothing(
    client: TestClient, place: Place
) -> None:
    """**M10.3.4 for the administrator.** The channel's authority lists the bound people by name
    and unbinds one, recorded as the administrator's act; a reader without it, and one asking about
    a channel that does not exist, get one absence and change nothing.

    Delete this and anybody signed in can see who has a chat account bound, or unbind them."""
    place.world.records.kept[Channel.WEBHOOK] = fresh_record()
    for pid, who in (("u_narrow", "person-42"), ("u_other", "person-43")):
        place.binder.table.live.append(
            Binding(
                channel=Channel.WEBHOOK,
                identity_hash=identity_hash(Channel.WEBHOOK, who),
                principal_id=pid,
                bound_at=NOW,
            )
        )
    listed = client.get(API_PREFIX + "/channels/webhook/bindings", headers=as_("u_admin"))
    assert [one["principal_id"] for one in listed.json()["items"]] == ["u_narrow", "u_other"]
    assert "person-42" not in listed.text

    refused = [
        client.get(API_PREFIX + "/channels/webhook/bindings", headers=as_("u_narrow")),
        client.post(
            API_PREFIX + "/channels/webhook/bindings/unbind",
            headers=as_("u_narrow"),
            json={"principal_id": "u_other"},
        ),
        client.get(API_PREFIX + "/channels/carrier-pigeon/bindings", headers=as_("u_admin")),
        client.post(
            API_PREFIX + "/channels/webhook/bindings/unbind",
            headers=as_("u_admin"),
            json={"principal_id": "u_nobody"},
        ),
    ]
    assert {one.status_code for one in refused} == {404}
    assert len({json.dumps(body_of(one)) for one in refused}) == 1
    assert len(place.binder.table.live) == 2

    done = client.post(
        API_PREFIX + "/channels/webhook/bindings/unbind",
        headers=as_("u_admin"),
        json={"principal_id": "u_other"},
    )
    assert done.json()["principal_id"] == "u_other"
    after = client.get(API_PREFIX + "/channels/webhook/bindings", headers=as_("u_admin")).json()
    assert [one["principal_id"] for one in after["items"]] == ["u_narrow"]
    searched = client.get(
        API_PREFIX + "/channels/webhook/bindings", headers=as_("u_admin"), params={"q": "narrow"}
    ).json()
    assert [one["principal_id"] for one in searched["items"]] == ["u_narrow"]
    assert place.binder.table.changes == [("unbound", "u_other", "webhook", "u_admin")]


def test_the_channels_screen_shows_what_each_channel_declares_and_how_it_is_doing(
    client: TestClient, place: Place
) -> None:
    """**M10.1.2, M10.1.3 and M10.1.4 on the screen.** Features and the most sensitive class are
    the adapter's own declaration, read from the adapter rather than restated, and health is its
    deliveries'. A reader without the authority is told nothing.

    Delete this and the screen can claim a channel carries what its adapter refuses."""
    place.world.records.kept[Channel.WEBHOOK] = fresh_record()
    place.world.deliveries.entries.append(
        DeliveryEntry(Channel.WEBHOOK, Direction.OUTBOUND, DeliveryOutcome.SENT, vendor_status=200)
    )
    found = client.get(API_PREFIX + "/channels/webhook/health", headers=as_("u_admin")).json()
    declared = adapter_for(Channel.WEBHOOK).capabilities()
    assert found["features"] == sorted(one.value for one in declared.features)
    assert found["max_classification"] == declared.max_classification.value
    assert found["can_carry_label"] is declared.can_carry_label
    assert (found["receives"], found["health"], found["last_fault"]) == (True, "working", None)
    slack = client.get(API_PREFIX + "/channels/slack/health", headers=as_("u_admin")).json()
    assert (slack["receives"], slack["health"]) == (False, "not_set_up")
    declared_slack = adapter_for(Channel.SLACK).capabilities().max_classification
    assert slack["max_classification"] == declared_slack
    refused = client.get(API_PREFIX + "/channels/webhook/health", headers=as_("u_narrow"))
    nothing = client.get(API_PREFIX + "/channels/carrier-pigeon/health", headers=as_("u_admin"))
    assert refused.status_code == nothing.status_code == 404
    assert body_of(refused) == body_of(nothing)


# ======================================================================== the migration


def migration() -> ModuleType:
    return migration_module(MIGRATION_0118)


def test_0118_builds_the_code_table_exactly_as_the_model_declares_it_and_secures_it() -> None:
    """**Every new table enables row-level security**, grants no DELETE, and admits no update of
    a spent code. Delete this and the model and the migration can disagree, or a later edit can
    let the application bring a spent code back."""
    up = squash(rendered("upgrade", MIGRATION_0118))
    expected = squash(str(CreateTable(table("auth.binding_code")).compile(dialect=DIALECT)))
    assert expected in up
    for index in table("auth.binding_code").indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in up
    assert "ALTER TABLE auth.binding_code ENABLE ROW LEVEL SECURITY" in up
    m = migration()
    assert m.GRANTS == ("GRANT SELECT, INSERT, UPDATE ON auth.binding_code TO brain_app",)
    assert "FOR DELETE" not in up
    assert (
        "CREATE POLICY binding_code_spendable ON auth.binding_code FOR UPDATE TO brain_app "
        "USING (used_at IS NULL) WITH CHECK (true)"
    ) in up
    assert one_of("channel", Channel) == m.CHANNELS
    assert checks("auth.binding_code")["ck_binding_code_channel"] == m.CHANNELS
    assert m.CODE_DIGEST_CHARS == binding_code_table.CODE_DIGEST_CHARS == 64
    down = squash(rendered("downgrade", MIGRATION_0118))
    assert "DROP TABLE auth.binding_code" in down
    assert "DROP TRIGGER principal_identity_records_channel_binding" in down


def test_0118_widens_the_ledger_to_the_new_action_and_names_the_list_it_replaces() -> None:
    """The action list is the enum's, with `channel_binding` in it, and the list replaced is the
    one `0105` left. Delete this and a trigger writes an action the database refuses."""
    m = migration()
    assert one_of("action", AuditAction) == m.WIDENED_ACTIONS
    assert "'channel_binding'" not in m.NARROWER_ACTIONS
    previous = migration_module(MIGRATION_0118.parent / "0105_agent_owner_audit.py")
    assert m.NARROWER_ACTIONS == previous.WIDENED_ACTIONS
    assert m.SUPERSEDES == {m.NARROWER_ACTIONS: m.WIDENED_ACTIONS}


def test_the_trigger_writes_the_recorders_words_and_leaves_the_console_to_sign_in() -> None:
    """The trigger's details are `AuditRecorder.channel_binding`'s, its subject the person, and
    it returns before writing anything for a console row, which `0047` records.

    Delete this and the trigger and the recorder drift, or a sign-in link is recorded twice."""
    entry = AuditChain().append(
        action=AuditAction.CHANNEL_BINDING,
        actor_id=ALICE,
        subject="principal:" + ALICE,
        ent_hash="0" * 32,
        trace_id=TRACE,
        at=NOW,
        details={"change": "bound", "channel": "lark"},
    )
    recorded = AuditRecorder(
        AuditChain(), actor_id=ALICE, ent_hash="0" * 32, trace_id=TRACE, clock=lambda: NOW
    )
    mine = recorded.channel_binding(
        principal_id=ALICE, channel="lark", change=ChannelBindingChange.BOUND
    )
    assert (mine.subject, dict(mine.details)) == (entry.subject, dict(entry.details))
    body = migration().BINDING_TRIGGER_FUNCTION
    assert "IF NEW.channel = 'console' THEN\n        RETURN NULL;" in body
    assert "jsonb_build_object('change', v_change, 'channel', NEW.channel)" in body
    assert {one.value for one in ChannelBindingChange} == {"bound", "unbound"}


# ======================================================================== against a server


@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    """Every migration that ships, through `0118`, which a server with pgvector builds."""
    with retirable("brain_test_channel_binding") as url:
        if not has_pgvector(url):
            pytest.skip("the migrations to 0118 need pgvector, which CI's server has")
        yield url


def _people(url: str) -> None:
    sql(url, "TRUNCATE auth.binding_code")
    for pid in (ALICE, BOB, "u_admin"):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name) "
            "VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
            pid,
            pid,
        )
    sql(
        url,
        "INSERT INTO auth.session (id, principal_id, channel, assurance, started_at, expires_at) "
        "VALUES ('sess-db', %s, 'console', 2, now() - interval '1 minute', "
        "now() + interval '1 hour') "
        "ON CONFLICT (id) DO NOTHING",
        ALICE,
    )


def test_a_code_is_kept_spent_once_and_never_brought_back_by_the_application(
    migrated: str,
) -> None:
    """**Single use against a server, as the application role.** A code is kept as its digest;
    claimed twice, the second finds nothing; a newer code ends the older; and the application
    role's own update cannot unspend a code, because the policy admits no spent row.

    Delete this and single use is only ever faked, and the first race is on an install."""
    _people(migrated)
    now = datetime.now(UTC)

    async def through() -> tuple[Any, ...]:
        db = app_engine(migrated)
        sessions = async_sessionmaker(db, expire_on_commit=False)
        codes = StoredCodes(sessions)
        live = _session(ALICE, sid="sess-db", opened=now)
        first = await mint_code(live, Channel.LARK, now=now, codes=codes)
        second = await mint_code(live, Channel.LARK, now=now + timedelta(seconds=1), codes=codes)
        later = now + timedelta(seconds=2)
        stale = await codes.claim(code_digest(Channel.LARK, first.nonce.value), now=later)
        claimed = await codes.claim(code_digest(Channel.LARK, second.nonce.value), now=later)
        again = await codes.claim(code_digest(Channel.LARK, second.nonce.value), now=later)
        signed_in = await StoredSignIns(sessions).still_open("sess-db", ALICE, now=later)
        somebody_else = await StoredSignIns(sessions).still_open("sess-db", BOB, now=later)
        async with db.begin() as conn:
            from sqlalchemy import text

            unspent = await conn.execute(
                text("UPDATE auth.binding_code SET used_at = NULL WHERE used_at IS NOT NULL")
            )
        await db.dispose()
        return first, second, stale, claimed, again, signed_in, somebody_else, unspent.rowcount

    first, second, stale, claimed, again, signed_in, somebody_else, unspent = run(through)
    assert stale is None and again is None
    assert claimed == ClaimedCode(
        principal_id=ALICE,
        session_id="sess-db",
        minted_at=second.nonce.minted_at,
        channel=Channel.LARK,
    )
    assert (signed_in, somebody_else, unspent) == (True, False, 0)
    stored = sql(migrated, "SELECT code_digest FROM auth.binding_code")
    assert {row[0] for row in stored} == {
        code_digest(Channel.LARK, first.nonce.value),
        code_digest(Channel.LARK, second.nonce.value),
    }
    assert first.nonce.value not in repr(stored)


def test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies(
    migrated: str,
) -> None:
    """**Every bind and unbind is in the audit ledger (M10.3.4), against a server.** A bind is
    `bound` as the person; a rebind is `unbound` then `bound`; an administrator's unbind is
    `unbound` as the administrator; the console is refused; an account already somebody else's
    writes nothing. Every entry names the person and the channel and never the account, and the
    chain verifies.

    Delete this and the trigger is only ever read, and the first time it runs is on an install."""
    _people(migrated)
    before = len(entries(migrated))

    def fresh(pid: str, who: str) -> Binding:
        return Binding(
            channel=Channel.LARK,
            identity_hash=identity_hash(Channel.LARK, who),
            principal_id=pid,
            bound_at=NOW,
        )

    async def through() -> tuple[Any, ...]:
        db = app_engine(migrated)
        stored = StoredBindings(async_sessionmaker(db, expire_on_commit=False))
        old = fresh(ALICE, "ou_old")
        new = fresh(ALICE, "ou_new")
        first = await stored.bind(old, decide=lambda live: settle(old, live), trace_id=TRACE)
        second = await stored.bind(new, decide=lambda live: settle(new, live), trace_id=TRACE)
        taken = fresh(BOB, "ou_new")
        with pytest.raises(BindingRefusedError):
            await stored.bind(taken, decide=lambda live: settle(taken, live), trace_id=TRACE)
        with pytest.raises(BindingRefusedError):
            await stored.unbind(
                ALICE, Channel.CONSOLE, actor="u_admin", ent_hash="1f" * 16, trace_id=TRACE
            )
        found = await stored.binding_for(Channel.LARK, identity_hash(Channel.LARK, "ou_new"))
        gone = await stored.binding_for(Channel.LARK, identity_hash(Channel.LARK, "ou_old"))
        listed = await stored.on_channel(Channel.LARK, limit=10)
        retired = await stored.unbind(
            ALICE, Channel.LARK, actor="u_admin", ent_hash="1f" * 16, trace_id=TRACE
        )
        after = await stored.for_principal(ALICE)
        await db.dispose()
        return first, second, found, gone, listed, retired, after

    first, second, found, gone, listed, retired, after = run(through)
    assert first is not None and first.revoked is None
    assert second is not None and second.revoked is not None
    assert found is not None and found.principal_id == ALICE and gone is None
    assert [(one.principal_id, one.display_name) for one in listed[0]] == [(ALICE, ALICE)]
    assert [one.identity_hash for one in retired] == [identity_hash(Channel.LARK, "ou_new")]
    assert after == ()
    chain = entries(migrated)
    mine = chain[before:]
    assert [(one.action, one.actor_id, one.subject, dict(one.details)) for one in mine] == [
        (
            AuditAction.CHANNEL_BINDING,
            ALICE,
            "principal:" + ALICE,
            {"change": "bound", "channel": "lark"},
        ),
        (
            AuditAction.CHANNEL_BINDING,
            ALICE,
            "principal:" + ALICE,
            {"change": "unbound", "channel": "lark"},
        ),
        (
            AuditAction.CHANNEL_BINDING,
            ALICE,
            "principal:" + ALICE,
            {"change": "bound", "channel": "lark"},
        ),
        (
            AuditAction.CHANNEL_BINDING,
            "u_admin",
            "principal:" + ALICE,
            {"change": "unbound", "channel": "lark"},
        ),
    ]
    assert {one.trace_id for one in mine} == {TRACE}
    assert "ou_new" not in repr(mine)
    assert AuditChain(chain).verify() is None


def test_a_chat_binding_nobody_named_is_recorded_as_unattributed_in_both_directions(
    migrated: str,
) -> None:
    """A bind and an unbind written by statements naming no actor are both recorded, as
    `unattributed`, and neither is refused: other writers of a non-console row exist, and an entry
    saying a binding appeared that nobody claimed is what an audit looks for.

    Delete this and a binding written at a prompt leaves no entry, or the trigger starts refusing
    every writer that is not the binding store."""
    _people(migrated)
    digest = identity_hash(Channel.SLACK, "U-prompt")
    before = len(entries(migrated))
    sql(
        migrated,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at) "
        "VALUES ('slack', %s, %s, now())",
        digest,
        BOB,
    )
    sql(
        migrated,
        "UPDATE auth.principal_identity SET deleted_at = statement_timestamp() "
        "WHERE identity_hash = %s AND deleted_at IS NULL",
        digest,
    )
    written = entries(migrated)[before:]
    unattributed = {"channel": "slack", "actor": "unattributed"}
    assert [(one.actor_id, one.subject, dict(one.details)) for one in written] == [
        ("unattributed", "principal:" + BOB, {"change": "bound", **unattributed}),
        ("unattributed", "principal:" + BOB, {"change": "unbound", **unattributed}),
    ]
    assert BindingCodeRow.__table__.schema == "auth"
