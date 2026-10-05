"""The channel pipeline: the registry, the signed webhook's wire, receiving, sending, the routes.

Driven through the real application where a route exists, with the token machinery of
`tests/unit/test_api_routes.py`, over stores, a vault and a transport in memory; below the route
the two halves are called directly, because what they refuse before a byte is read is only
visible from there. The migration is held to the models without a server, and the stores run
against PostgreSQL at the foot, which **skip without a server**.

Every refusal has a permitted sibling. Signatures are made with the real clock, because the
check they meet is a five-minute window around it; no fixture date is compared with the present.

Task ids: M10.1.1, M10.1.5, M10.2.1, M10.3.3, M10.4.5, M10.6.1, M10.6.3, M3.2.2
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

import brain.channels
from brain import channel_routes
from brain.agent_routes import CHANNEL_ADAPTERS
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder, SettingChange
from brain.channels.adapter import (
    Arrived,
    ChannelRegistryError,
    Received,
    VendorAnswer,
    VendorRequest,
    channel_adapters,
    channel_wires,
)
from brain.channels.email import WIRE as EMAIL_WIRE
from brain.channels.inbound import (
    MAX_BODY_BYTES,
    Inbound,
    NoBindingsYet,
    ReceiptKind,
    receive,
)
from brain.channels.lark import WIRE as LARK_WIRE
from brain.channels.outbound import (
    A_MESSAGE_FOR_NOBODY_IN_PARTICULAR_CARRIES_NOTHING,
    Delivered,
    Outgoing,
    deliver,
)
from brain.channels.slack import WIRE as SLACK_WIRE
from brain.channels.teams import WIRE as TEAMS_WIRE
from brain.channels.telegram import WIRE as TELEGRAM_WIRE
from brain.channels.webhook import (
    REPLY_URL,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    WIRE,
    SignedWebhookWire,
    WebhookRefusedError,
    sign,
    verify,
)
from brain.channels.whatsapp import WIRE as WHATSAPP_WIRE
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.connectors.throttle import CallOutcome
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import OPAQUE_LABEL, ChannelPayload
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.gate.ingress import UNRECOGNISED_PROMPT, Binding, ChannelEvent, identity_hash
from brain.identity.bearer import TokenAuthority
from brain.ops import outbox
from brain.ops.channel_store import (
    A_CHANNEL_READS_ONLY_ITS_OWN_SLOT,
    ChannelRecord,
    ChannelSecretsUnavailableError,
    DeliveryEntry,
    DeliveryView,
    StoredChannels,
    StoredClaims,
    StoredDeliveries,
    VaultChannelSecrets,
    channel_secret_ref,
)
from brain.ops.connector_admin import SOURCE_FIELD
from brain.ops.credentials import KEY_FIELD, Credentials, VaultState
from brain.ops.idempotency import Intent
from brain.ops.openbao import StaticVersion, VaultRefusedError
from brain.ops.secrets import SecretRef, VaultRole
from brain.tables import channel as channel_table
from brain.tables.channel import (
    CHANNEL_SECRET_PREFIX,
    SECRET_PATH_CHARS,
    ChannelDeliveryRow,
    ChannelRow,
    DeliveryOutcome,
    Direction,
    RefusedBecause,
    outcome_fits_direction,
)
from brain.tables.identity import one_of
from tests.fixtures.operation_ledger import MemoryLedger
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import engine, modelled, run, sql
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credential_writes import entries
from tests.unit.test_tables import DIALECT, checks, migration_module, rendered, squash, table

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"
MIGRATION_0114 = MIGRATION / "0114_channel_record_and_delivery.py"

#: A test value for the channel's signing secret, and a second that is not it.
SECRET = "channel-test-secret-0123456789abcdef"
WRONG = "channel-test-secret-somebody-else-000"
REPLY_TO = "https://replies.example.test/brain"
#: Far outside any plausible wall clock, for records whose instant nothing compares to now.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
#: Text a refusal record must never contain. If it appears in a delivery row it leaked.
CANARY = "CANARY-MESSAGE-7QX2P"

EVENTS = f"{API_PREFIX}/channels/{{name}}/events"

#: A reach digest and a trace a store write is attributed to, in the ledger's own shapes.
REACH = "1f" * 16
TRACE = "trace-channel-1"
AS_ADMIN: dict[str, str] = {"actor": "u_admin", "ent_hash": REACH, "trace_id": TRACE}
AS_OTHER: dict[str, str] = {"actor": "u_other", "ent_hash": REACH, "trace_id": TRACE}


# ------------------------------------------------------------------------ the seams


def fresh_record(
    channel: Channel = Channel.WEBHOOK,
    *,
    enabled: bool = True,
    tenant: Mapping[str, str] | None = None,
    at: datetime = LONG_AGO,
) -> ChannelRecord:
    return ChannelRecord(
        channel=channel,
        enabled=enabled,
        tenant=MappingProxyType(dict({REPLY_URL: REPLY_TO} if tenant is None else tenant)),
        secret=channel_secret_ref(channel),
        updated_by="u_admin",
        updated_at=at,
    )


@dataclass
class Records:
    """`ChannelRecords` in a dictionary, one row per channel, as the table keys it."""

    kept: dict[Channel, ChannelRecord] = field(default_factory=dict)
    changes: int = 0
    #: Who, at what reach and in which request, for every write, in order.
    attributed: list[tuple[str, str, str]] = field(default_factory=list)

    async def get(self, channel: Channel) -> ChannelRecord | None:
        return self.kept.get(channel)

    async def every(self) -> tuple[ChannelRecord, ...]:
        return tuple(self.kept[one] for one in sorted(self.kept))

    async def save(
        self,
        channel: Channel,
        *,
        enabled: bool,
        tenant: Mapping[str, str],
        actor: str,
        ent_hash: str,
        trace_id: str,
    ) -> ChannelRecord:
        self.changes += 1
        self.attributed.append((actor, ent_hash, trace_id))
        kept = ChannelRecord(
            channel=channel,
            enabled=enabled,
            tenant=MappingProxyType(dict(tenant)),
            secret=channel_secret_ref(channel),
            updated_by=actor,
            updated_at=LONG_AGO + timedelta(seconds=self.changes),
        )
        self.kept[channel] = kept
        return kept

    async def switch(
        self, channel: Channel, *, enabled: bool, actor: str, ent_hash: str, trace_id: str
    ) -> ChannelRecord | None:
        found = self.kept.get(channel)
        if found is None:
            return None
        self.changes += 1
        self.attributed.append((actor, ent_hash, trace_id))
        self.kept[channel] = ChannelRecord(
            channel=channel,
            enabled=enabled,
            tenant=found.tenant,
            secret=found.secret,
            updated_by=actor,
            updated_at=LONG_AGO + timedelta(seconds=self.changes),
        )
        return self.kept[channel]


@dataclass
class Deliveries:
    """`DeliveryRecords` in a list, newest last."""

    entries: list[DeliveryEntry] = field(default_factory=list)

    async def record(self, entry: DeliveryEntry) -> None:
        self.entries.append(entry)

    async def recent(self, channel: Channel) -> tuple[DeliveryView, ...]:
        mine = [one for one in self.entries if one.channel is channel]
        return tuple(
            DeliveryView(entry=one, recorded_at=LONG_AGO + timedelta(seconds=n))
            for n, one in reversed(list(enumerate(mine)))
        )

    def seen(self) -> list[tuple[str, str, str | None]]:
        return [
            (one.direction.value, one.outcome.value, one.reason and one.reason.value)
            for one in self.entries
        ]


@dataclass
class Claims:
    """`EventClaims` over a set: a second delivery of one key is refused, as the key refuses it."""

    keys: set[tuple[str, str]] = field(default_factory=set)
    asked: int = 0

    async def first(self, event: ChannelEvent) -> bool:
        self.asked += 1
        if event.dedupe_key in self.keys:
            return False
        self.keys.add(event.dedupe_key)
        return True


@dataclass
class Secrets:
    """`ChannelSecrets` over a dictionary of slots, counting every read."""

    slots: dict[str, str] = field(default_factory=dict)
    reads: list[SecretRef] = field(default_factory=list)
    silent: bool = False

    def read(self, ref: SecretRef) -> str | None:
        self.reads.append(ref)
        if self.silent:
            raise ChannelSecretsUnavailableError(VaultState.UNREACHABLE)
        return self.slots.get(ref.path)

    def held(self, ref: SecretRef) -> bool:
        return ref.path in self.slots


@dataclass
class Transport:
    """`ChannelTransport` that keeps every request and answers with one fixed answer."""

    answer: VendorAnswer = field(default_factory=lambda: VendorAnswer(status=200))
    sent: list[VendorRequest] = field(default_factory=list)

    def send(self, request: VendorRequest) -> VendorAnswer:
        self.sent.append(request)
        return self.answer

    def read(self, request: VendorRequest) -> VendorAnswer:
        # The webhook channel reads nothing from its vendor; a read here is a wiring fault.
        raise AssertionError(f"nothing reads through the webhook's transport: {request.url}")

    def texts(self) -> list[str]:
        return [json.loads(one.body)["text"] for one in self.sent]


@dataclass
class Reach:
    """An `EntitlementStore` answering one set for everybody, which a test can change."""

    grants: tuple[Grant, ...] = ()

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=self.grants)


def signed(
    message: Mapping[str, Any] | bytes, *, secret: str = SECRET
) -> tuple[bytes, dict[str, str]]:
    """A message as the company's system sends it: bytes, a time, and a signature over both."""
    raw = message if isinstance(message, bytes) else json.dumps(dict(message)).encode("utf-8")
    stamp = str(int(time.time()))
    return raw, {
        TIMESTAMP_HEADER: stamp,
        SIGNATURE_HEADER: sign(secret, stamp, raw),
        "content-type": "application/json",
    }


def message(ident: str = "m-1", *, text: str = "what is left on the retainer?") -> dict[str, str]:
    return {"id": ident, "sender": "person-42", "text": text, "conversation": "conv-7"}


# ------------------------------------------------------------------------ the application


def grant(scope: Scope) -> Grant:
    return Grant(capability=INSTALL_AUTHORITY, scope=scope)


def over(name: str) -> Scope:
    return Scope(clauses=(Clause(field=SOURCE_FIELD, op=Op.EQ, value=name),))


#: `u_admin` holds the connector authority over everything; `u_narrow` over the widget channel
#: alone; `u_wide` holds every other capability and not this one; `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (grant(Scope.unrestricted()),),
    "u_narrow": (grant(over("widget_channel")),),
    "u_wide": (
        Grant(capability=Capability(value="admin:requirement_check"), scope=Scope.unrestricted()),
    ),
    "u_none": (),
}


class Directory:
    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return Principal(
                    id=pid, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=pid
                )
        return None


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


class KeptVault:
    """A vault holding written slots in a dictionary. Metadata says only that one is held."""

    def __init__(self) -> None:
        self.slots: dict[str, dict[str, str]] = {}

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        self.slots[path] = dict(fields)
        return LONG_AGO

    def static_kv_version(self, path: str) -> StaticVersion | None:
        return StaticVersion(written_at=LONG_AGO) if path in self.slots else None

    def read_static_kv(self, path: str) -> dict[str, Any]:
        if path not in self.slots:
            raise VaultRefusedError("nothing here", status=404)
        return dict(self.slots[path])


@dataclass
class World:
    records: Records = field(default_factory=Records)
    deliveries: Deliveries = field(default_factory=Deliveries)
    claims: Claims = field(default_factory=Claims)
    secrets: Secrets = field(
        default_factory=lambda: Secrets({channel_secret_ref(Channel.WEBHOOK).path: SECRET})
    )
    transport: Transport = field(default_factory=Transport)
    ledger: MemoryLedger = field(default_factory=MemoryLedger)
    vault: KeptVault = field(default_factory=KeptVault)


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
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
        app.state.channel_records = world.records
        app.state.channel_deliveries = world.deliveries
        app.state.channel_claims = world.claims
        app.state.channel_secrets = world.secrets
        app.state.channel_transport = world.transport
        app.state.operation_ledger = world.ledger
        app.state.credentials = Credentials(world.vault)
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


def post_event(c: TestClient, raw: bytes, sent: Mapping[str, str], name: str = "webhook") -> Any:
    return c.post(EVENTS.format(name=name), content=raw, headers=dict(sent))


def body_of(answer: Any) -> dict[str, Any]:
    found: dict[str, Any] = answer.json()
    found.pop("trace_id", None)
    return found


# ======================================================================== the registry (M10.1.1)


def test_every_adapter_in_the_package_is_registered_once_in_channel_order() -> None:
    """The registry is the package: seven surfaces, one each, in channel order, and the agent
    page's list is the registry itself rather than a second list beside it.

    Delete this and a discovery that found nothing, or found an adapter twice, would hand the
    agent page and the receiving route an empty or doubled set of surfaces."""
    declared = [factory().capabilities().channel for factory in channel_adapters()]
    assert declared == sorted(declared)
    assert len(declared) == len(set(declared))
    assert set(declared) >= {
        Channel.EMAIL,
        Channel.LARK,
        Channel.SLACK,
        Channel.TEAMS,
        Channel.TELEGRAM,
        Channel.WEBHOOK,
        Channel.WHATSAPP,
    }
    assert channel_adapters() == CHANNEL_ADAPTERS
    assert dict(channel_wires()) == {
        Channel.EMAIL: EMAIL_WIRE,
        Channel.LARK: LARK_WIRE,
        Channel.SLACK: SLACK_WIRE,
        Channel.TEAMS: TEAMS_WIRE,
        Channel.TELEGRAM: TELEGRAM_WIRE,
        Channel.WEBHOOK: WIRE,
        Channel.WHATSAPP: WHATSAPP_WIRE,
    }


PROBE_MODULE = """
from dataclasses import dataclass
from datetime import datetime

from brain.channels.adapter import ChannelCapabilities, Received
from brain.channels.webhook import SignedWebhookWire, normalise_message
from brain.core.redaction import ChannelPayload
from brain.gate.context import Channel
from brain.gate.ingress import ChannelEvent


class ProbeAdapter:
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(channel=Channel.WIDGET)

    def normalise(self, raw: object) -> ChannelEvent:
        event = normalise_message(raw)
        return ChannelEvent(
            channel=Channel.WIDGET,
            external_id=event.external_id,
            channel_identity=event.channel_identity,
            text=event.text,
            received_at=event.received_at,
        )

    def send(self, payload: ChannelPayload, *, to: str, body: str = "") -> None:
        del payload, to, body

    def healthy(self, now: datetime) -> bool:
        del now
        return True


@dataclass(frozen=True)
class ProbeWire(SignedWebhookWire):
    @property
    def channel(self) -> Channel:
        return Channel.WIDGET

    def read(self, arrived):
        read = super().read(arrived)
        event = ProbeAdapter().normalise(
            {
                "id": read.event.external_id,
                "sender": read.event.channel_identity,
                "text": read.event.text,
                "sent_at": int(read.event.received_at.timestamp()),
            }
        )
        return Received(event=event, reply_to=read.reply_to)


WIRE = ProbeWire()
"""


@pytest.fixture
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """A channel package added as one file and nothing else, for the length of one test."""
    (tmp_path / "zz_probe.py").write_text(PROBE_MODULE, encoding="utf-8")
    monkeypatch.setattr(brain.channels, "__path__", [*brain.channels.__path__, str(tmp_path)])
    channel_adapters.cache_clear()
    channel_wires.cache_clear()
    try:
        yield importlib.import_module("brain.channels.zz_probe")
    finally:
        sys.modules.pop("brain.channels.zz_probe", None)
        monkeypatch.undo()
        channel_adapters.cache_clear()
        channel_wires.cache_clear()


def test_a_channel_added_as_one_file_is_registered_with_no_list_edited(probe: ModuleType) -> None:
    """**M10.1.1's "later channel packages only add files".** A module dropped into the package
    joins the adapters and the wires, and nothing else in the tree was touched.

    Delete this and the registry can quietly become a list again, and the next channel package
    has to edit this one to be received."""
    declared = {factory().capabilities().channel for factory in channel_adapters()}
    assert Channel.WIDGET in declared
    assert channel_wires()[Channel.WIDGET] is probe.WIRE
    assert channel_routes.channel_named("widget") is Channel.WIDGET


def test_two_adapters_for_one_channel_are_refused_at_discovery(
    probe: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and two declarations of one surface's ceiling can both be registered, and
    whichever the caller happened to find is the one a send is checked against."""
    second = type("SecondProbe", (probe.ProbeAdapter,), {"__module__": probe.__name__})
    monkeypatch.setattr(probe, "SecondProbe", second, raising=False)
    channel_adapters.cache_clear()
    with pytest.raises(ChannelRegistryError, match="two adapters"):
        channel_adapters()


def test_a_wire_whose_channel_no_adapter_declares_is_refused(
    probe: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a wire can send on a surface with no declared ceiling or label rule."""
    monkeypatch.delattr(probe, "ProbeAdapter")
    channel_adapters.cache_clear()
    channel_wires.cache_clear()
    with pytest.raises(ChannelRegistryError, match="no adapter"):
        channel_wires()


# ======================================================================== the wire (M10.2.1)


def test_a_message_signed_over_its_exact_bytes_is_verified_and_read() -> None:
    """The positive case for every refusal below: verified, then read into the event the gate
    reads, at the instant the signature covers, with the conversation as the reply address.

    Delete this and every refusal below passes against a wire that accepts nothing."""
    raw, sent = signed(message())
    arrived = Arrived(headers=sent, body=raw)
    WIRE.verify(arrived, SECRET, datetime.now(UTC))
    received = WIRE.read(arrived)
    assert received.event.channel is Channel.WEBHOOK
    assert (received.event.external_id, received.event.channel_identity) == ("m-1", "person-42")
    assert received.event.received_at == datetime.fromtimestamp(int(sent[TIMESTAMP_HEADER]), tz=UTC)
    assert received.reply_to == "conv-7"
    without = {k: v for k, v in message().items() if k != "conversation"}
    raw, sent = signed(without)
    assert WIRE.read(Arrived(headers=sent, body=raw)).reply_to == "person-42"


@pytest.mark.parametrize(
    "tamper",
    ["altered body", "wrong secret", "stale", "no signature"],
)
def test_a_request_the_system_did_not_send_is_refused(tamper: str) -> None:
    """Delete this and a forged, altered or replayed-from-a-log request is read as a message."""
    raw, sent = signed(message(), secret=WRONG if tamper == "wrong secret" else SECRET)
    now = datetime.now(UTC)
    if tamper == "altered body":
        raw = raw.replace(b"retainer", b"contract")
    if tamper == "stale":
        now = now + timedelta(minutes=6)
    if tamper == "no signature":
        sent = {k: v for k, v in sent.items() if k != SIGNATURE_HEADER}
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(Arrived(headers=sent, body=raw), SECRET, now)


def test_the_headers_are_the_ones_this_install_signs_its_own_requests_with() -> None:
    """One construction in both directions. Delete this and a reply signed under one name is
    checked under another at the company's end, and reads there as a wrong secret."""
    assert outbox.TIMESTAMP_HEADER.lower() == TIMESTAMP_HEADER
    assert outbox.SIGNATURE_HEADER.lower() == SIGNATURE_HEADER


def test_a_reply_is_signed_with_the_channel_secret_and_posted_to_the_record_s_address() -> None:
    """The company's system checks a reply exactly as this install checks its message.

    Delete this and a reply can go out unsigned, or to an address no record named."""
    now = datetime.now(UTC)
    request = WIRE.request_for(
        to="conv-7", text="hello", secret=SECRET, tenant={REPLY_URL: REPLY_TO}, now=now
    )
    assert request.url == REPLY_TO
    verify(
        secret=SECRET,
        signature=request.headers[SIGNATURE_HEADER],
        timestamp=request.headers[TIMESTAMP_HEADER],
        body=request.body,
        now=now,
    )
    assert json.loads(request.body) == {"text": "hello", "to": "conv-7"}
    assert SECRET not in repr(request)
    for tenant in ({}, {REPLY_URL: "http://replies.example.test/brain"}):
        with pytest.raises(ValueError, match="https"):
            WIRE.request_for(to="c", text="t", secret=SECRET, tenant=tenant, now=now)


@pytest.mark.parametrize(
    ("answer", "judged"),
    [
        (VendorAnswer(status=200), CallOutcome.OK),
        (VendorAnswer(status=204), CallOutcome.OK),
        (VendorAnswer(status=302), CallOutcome.REJECTED),
        (VendorAnswer(status=403), CallOutcome.REJECTED),
        (VendorAnswer(status=429), CallOutcome.QUOTA),
        (VendorAnswer(status=503), CallOutcome.UNAVAILABLE),
        (VendorAnswer(timed_out=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
    ],
)
def test_the_wire_judges_the_system_s_answer(answer: VendorAnswer, judged: CallOutcome) -> None:
    """Delete this and a redirect or an unsafe address can be judged delivered."""
    assert WIRE.judge(answer) is judged


# ======================================================================== receiving


def run_receive(
    wire: Any,
    *,
    record: ChannelRecord | None,
    raw: bytes,
    sent: Mapping[str, str],
    world: World,
    body: Callable[[], Awaitable[bytes]] | None = None,
    declared: int | None = None,
) -> Any:
    async def read() -> bytes:
        return raw

    return run(
        lambda: receive(
            wire,
            record=record,
            headers=sent,
            declared_length=declared,
            body=body or read,
            secrets=world.secrets,
            claims=world.claims,
            deliveries=world.deliveries,
            now=datetime.now(UTC),
        )
    )


class Spy(SignedWebhookWire):
    """The webhook wire, counting how often it looked inside a body."""

    reads = 0

    def read(self, arrived: Arrived) -> Received:
        Spy.reads += 1
        return super().read(arrived)


def test_a_bad_signature_is_refused_before_the_wire_reads_the_body(world: World) -> None:
    """**M10.2.1's install check, below the route.** The wire's `read` is the first thing that
    looks inside a body, and a request that does not verify never reaches it, nor the claim.

    Delete this and a forged body could be parsed on the one path that exists to refuse it."""
    Spy.reads = 0
    raw, sent = signed(message(), secret=WRONG)
    receipt = run_receive(Spy(), record=fresh_record(), raw=raw, sent=sent, world=world)
    assert (receipt.kind, receipt.reason) == (ReceiptKind.REFUSED, RefusedBecause.BAD_SIGNATURE)
    assert Spy.reads == 0
    assert world.claims.asked == 0
    raw, sent = signed(message())
    assert (
        run_receive(Spy(), record=fresh_record(), raw=raw, sent=sent, world=world).kind
        is ReceiptKind.ACCEPTED
    )
    assert Spy.reads == 1


@pytest.mark.parametrize("enabled", [False, None])
def test_a_channel_switched_off_or_never_set_up_refuses_before_a_byte_is_read(
    world: World, enabled: bool | None
) -> None:
    """**M10.6.3's receiving half.** The body is not read and the secret is not borrowed.

    Delete this and a switched-off channel goes on reading, verifying and claiming."""

    async def never() -> bytes:
        raise AssertionError("the body was read")

    record = None if enabled is None else fresh_record(enabled=enabled)
    raw, sent = signed(message())
    receipt = run_receive(WIRE, record=record, raw=raw, sent=sent, world=world, body=never)
    reason = RefusedBecause.NOT_CONFIGURED if enabled is None else RefusedBecause.SWITCHED_OFF
    assert (receipt.kind, receipt.reason) == (ReceiptKind.REFUSED, reason)
    assert world.secrets.reads == []
    assert world.deliveries.seen() == [("inbound", "refused", reason.value)]


def test_a_request_larger_than_a_message_is_refused_before_it_is_read(world: World) -> None:
    """Delete this and a request of any size is read into memory, on an address anybody may post
    to."""

    async def never() -> bytes:
        raise AssertionError("the body was read")

    raw, sent = signed(message())
    receipt = run_receive(
        WIRE,
        record=fresh_record(),
        raw=raw,
        sent=sent,
        world=world,
        body=never,
        declared=MAX_BODY_BYTES + 1,
    )
    assert receipt.reason is RefusedBecause.TOO_LARGE
    oversized = b"{" + b" " * MAX_BODY_BYTES + b"}"
    receipt = run_receive(WIRE, record=fresh_record(), raw=oversized, sent=sent, world=world)
    assert receipt.reason is RefusedBecause.TOO_LARGE


# ================================================================ the route (M10.2.1, M3.2.2)


def test_an_unbound_sender_is_answered_once_with_the_binding_prompt(
    client: TestClient, world: World
) -> None:
    """**M10.3.3 through the route.** A verified message from a sender bound to nobody is claimed,
    recorded as accepted, and answered with the one prompt, signed and sent through the channel's
    own vendor, and recorded as sent. The prompt names no identity and carries no entitlement.

    Delete this and an unbound sender could be answered with anything, or not at all."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    raw, sent = signed(message(text=CANARY))
    answer = post_event(client, raw, sent)
    assert answer.status_code == 200
    assert answer.json() == {"status": "accepted", "reply": "sent"}
    assert world.transport.texts() == [UNRECOGNISED_PROMPT]
    request = world.transport.sent[0]
    assert request.url == REPLY_TO
    assert json.loads(request.body)["to"] == "conv-7"
    assert world.deliveries.seen() == [("inbound", "accepted", None), ("outbound", "sent", None)]
    assert world.secrets.reads == [channel_secret_ref(Channel.WEBHOOK)] * 2


def test_a_redelivered_event_is_claimed_once_and_answered_once(
    client: TestClient, world: World
) -> None:
    """**M3.2.2 and M10.2.1's install check.** The same message delivered twice, freshly signed
    the second time as a retrying vendor would, is claimed by the first and answered once.

    Delete this and every platform retry after a timeout is a second answer."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    raw, sent = signed(message("m-9"))
    first = post_event(client, raw, sent)
    raw, sent = signed(message("m-9"))
    second = post_event(client, raw, sent)
    assert first.json() == {"status": "accepted", "reply": "sent"}
    assert second.status_code == 200
    assert second.json() == {"status": "redelivered", "reply": None}
    assert len(world.transport.sent) == 1
    assert world.ledger.issued() == 1
    assert world.deliveries.seen() == [
        ("inbound", "accepted", None),
        ("outbound", "sent", None),
        ("inbound", "redelivered", None),
    ]


def test_a_bad_signature_is_refused_through_the_route_and_recorded_without_its_content(
    client: TestClient, world: World
) -> None:
    """Delete this and a forged request is answered, or its refusal leaves no trace, or leaves
    one holding the message it refused."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    raw, sent = signed(message(text=CANARY), secret=WRONG)
    answer = post_event(client, raw, sent)
    assert answer.status_code == 401
    assert CANARY not in answer.text
    assert world.claims.asked == 0
    assert world.transport.sent == []
    assert world.deliveries.seen() == [("inbound", "refused", "bad_signature")]
    assert CANARY not in repr(world.deliveries.entries)


def test_every_refusal_is_one_row_that_could_not_hold_a_message() -> None:
    """**The fourth install check, as a shape.** A delivery entry and a delivery row have exactly
    these fields, none of which could carry a body, a sender, a recipient or a message id.

    Delete this and a column added "to help debugging" stores what the gate refused to admit."""
    assert set(DeliveryEntry.__dataclass_fields__) == {
        "channel",
        "direction",
        "outcome",
        "reason",
        "vendor_status",
    }
    assert set(ChannelDeliveryRow.__table__.columns.keys()) == {
        "id",
        "channel",
        "direction",
        "outcome",
        "reason",
        "vendor_status",
        "recorded_at",
    }


@pytest.mark.parametrize(
    ("setup", "status", "reason"),
    [
        ("no record", 404, "not_configured"),
        ("switched off", 404, "switched_off"),
        ("no secret", 503, "no_secret"),
        ("vault silent", 503, "vault_unavailable"),
        ("unreadable", 400, "unreadable"),
    ],
)
def test_each_refusal_answers_its_status_and_is_recorded_with_its_reason(
    client: TestClient, world: World, setup: str, status: int, reason: str
) -> None:
    """Delete this and a refusal can be answered as success, or go unrecorded."""
    if setup != "no record":
        world.records.kept[Channel.WEBHOOK] = fresh_record(enabled=setup != "switched off")
    if setup == "no secret":
        world.secrets.slots.clear()
    if setup == "vault silent":
        world.secrets.silent = True
    raw, sent = signed(
        b"not json at all" if setup == "unreadable" else json.dumps(message()).encode()
    )
    answer = post_event(client, raw, sent)
    assert answer.status_code == status
    assert world.deliveries.seen() == [("inbound", "refused", reason)]
    assert world.transport.sent == []


def test_a_streamed_request_is_read_no_further_than_one_byte_past_a_message(
    client: TestClient, world: World
) -> None:
    """A request that declares no length is read up to the bound and refused, rather than held
    whole. Delete this and anybody can make the process hold whatever they choose to stream."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    _, sent = signed(message())

    def streamed() -> Iterator[bytes]:
        for _ in range(8):
            yield b" " * (MAX_BODY_BYTES // 4)

    answer = client.post(EVENTS.format(name="webhook"), content=streamed(), headers=sent)
    assert answer.status_code == 413
    assert world.deliveries.seen() == [("inbound", "refused", "too_large")]
    assert world.secrets.reads == []


def test_the_events_address_takes_no_sign_in_and_refuses_every_unsigned_request(
    client: TestClient, world: World
) -> None:
    """`A_PLATFORM_PROVES_A_SIGNATURE_AND_HAS_NO_SIGN_IN`, the one written exception to the rule
    that every route under the prefix authenticates its caller. Unsigned, the channel that is on
    refuses as unaccepted, every other name answers as nothing there, and nothing is answered;
    every other channel route asks for a sign-in.

    Delete this and the exception in `tests/unit/test_api_routes.py` excuses a route nothing
    shows refusing a stranger."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    assert {API_PREFIX + channel_routes.EVENTS_PATH} == channel_routes.SIGNED_NOT_SIGNED_IN
    for name in [*(one.value for one in Channel), "carrier-pigeon"]:
        answer = client.post(EVENTS.format(name=name), content=json.dumps(message()).encode())
        assert answer.status_code == (401 if name == "webhook" else 404), name
    assert world.transport.sent == [] and world.claims.asked == 0
    for method, path in (
        ("GET", "/channels"),
        ("PUT", "/channels/webhook"),
        ("POST", "/channels/webhook/switch"),
        ("GET", "/channels/webhook/deliveries"),
        ("POST", "/channels/webhook/test"),
    ):
        refused = client.request(method, API_PREFIX + path, json=None if method == "GET" else {})
        assert refused.status_code == 401, path


def test_a_name_that_is_no_channel_and_a_switched_off_channel_are_one_answer(
    client: TestClient, world: World
) -> None:
    """`AN_ADDRESS_A_VENDOR_POSTS_TO_SAYS_NOTHING_ABOUT_THE_INSTALL`. A channel nobody set up is the
    same answer again. Every channel receives since Telegram's wire, so each named channel is
    recorded, as switched off and as not configured, and the name that is no channel is not.

    Delete this and posting to each name in turn tells a stranger which channels an install runs."""
    world.records.kept[Channel.WEBHOOK] = fresh_record(enabled=False)
    raw, sent = signed(message())
    off = post_event(client, raw, sent)
    nothing = post_event(client, raw, sent, name="carrier-pigeon")
    unset = post_event(client, raw, sent, name="telegram")
    assert off.status_code == nothing.status_code == unset.status_code == 404
    assert body_of(off) == body_of(nothing) == body_of(unset)
    assert world.deliveries.seen() == [
        ("inbound", "refused", "switched_off"),
        ("inbound", "refused", "not_configured"),
    ]


def test_a_bound_sender_with_nothing_to_answer_them_is_refused_and_recorded(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bound sender is the answerer's; with none wired nothing is sent and the refusal is
    recorded. With one wired, what it made is what is sent.

    Delete this and a bound sender is answered with the unbound prompt, which tells them their
    binding does not exist."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    bound = Binding(
        channel=Channel.WEBHOOK,
        identity_hash=identity_hash(Channel.WEBHOOK, "person-42"),
        principal_id="u_admin",
        bound_at=LONG_AGO,
    )

    class Bound:
        async def binding_for(self, channel: Channel, digest: str) -> Binding | None:
            return bound if digest == bound.identity_hash else None

    client.app.state.channel_bindings = Bound()  # type: ignore[attr-defined]
    # A process with nothing able to answer: `answerer_of` answers None exactly there.
    monkeypatch.setattr(channel_routes, "answerer_of", lambda request: None)
    raw, sent = signed(message("m-2"))
    assert post_event(client, raw, sent).json() == {"status": "accepted", "reply": "refused"}
    assert world.deliveries.seen()[-1] == ("outbound", "refused", "not_answerable")
    assert world.transport.sent == []

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
            assert binding is bound
            assert record.channel is Channel.WEBHOOK
            return (
                Outgoing(
                    channel=Channel.WEBHOOK,
                    to=reply_to,
                    intent=Intent(principal_id=binding.principal_id, intent_ref="answer.1"),
                    text="an answer",
                ),
            )

    monkeypatch.undo()
    client.app.state.channel_answerer = Answerer()  # type: ignore[attr-defined]
    raw, sent = signed(message("m-3"))
    assert post_event(client, raw, sent).json() == {"status": "accepted", "reply": "sent"}
    assert world.transport.texts() == ["an answer"]


def test_until_a_binding_is_kept_nobody_is_bound() -> None:
    """`NOBODY_IS_BOUND_UNTIL_A_BINDING_IS_KEPT`. Delete this and a default that bound somebody
    would answer a stranger as a colleague."""
    assert run(lambda: NoBindingsYet().binding_for(Channel.WEBHOOK, "0" * 64)) is None


# ================================================================ sending (M10.6.1, M10.4.5)


def send(
    world: World,
    outgoing: Outgoing,
    *,
    record: ChannelRecord | None = None,
    reach: Reach | None = None,
    use_record: bool = True,
) -> Delivered:
    return run(
        lambda: deliver(
            outgoing,
            record=(record or fresh_record()) if use_record else None,
            secrets=world.secrets,
            reach=reach or Reach(),
            transport=world.transport,
            ledger=lambda work: work(world.ledger),
            deliveries=world.deliveries,
            now=datetime.now(UTC),
        )
    )


def note(text: str = "a product sentence", *, ref: str = "note.1", **kwargs: Any) -> Outgoing:
    return Outgoing(
        channel=Channel.WEBHOOK,
        to="conv-7",
        intent=Intent(principal_id="u_admin", intent_ref=ref),
        text=text,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("answer", "outcome", "reason", "status"),
    [
        (VendorAnswer(status=200), "sent", None, 200),
        (VendorAnswer(status=400), "refused", "vendor_refused", 400),
        (VendorAnswer(status=429), "refused", "vendor_refused", 429),
        (VendorAnswer(status=302), "refused", "vendor_refused", 302),
        (VendorAnswer(unsafe_address=True), "refused", "unsafe_address", None),
        (VendorAnswer(status=502), "unknown", "vendor_unavailable", 502),
        (VendorAnswer(timed_out=True), "unknown", "vendor_unavailable", None),
    ],
)
def test_a_delivery_the_vendor_refused_is_recorded_as_refused_and_never_as_sent(
    world: World, answer: VendorAnswer, outcome: str, reason: str | None, status: int | None
) -> None:
    """**M10.6.1.** What the vendor said is what is recorded, and a silence is unknown rather than
    either, because a request that timed out may have arrived.

    Delete this and a refused delivery can be counted as sent."""
    world.transport.answer = answer
    delivered = send(world, note())
    assert (delivered.outcome.value, delivered.reason and delivered.reason.value) == (
        outcome,
        reason,
    )
    assert world.deliveries.entries == [
        DeliveryEntry(
            channel=Channel.WEBHOOK,
            direction=Direction.OUTBOUND,
            outcome=DeliveryOutcome(outcome),
            reason=None if reason is None else RefusedBecause(reason),
            vendor_status=status,
        )
    ]


def test_the_credential_is_borrowed_by_its_reference_and_held_by_no_record(world: World) -> None:
    """**M10.6.1's "a credential held outside configuration".** The secret is read from the vault
    slot the record names, and signs the request; the record holds a reference and nothing else.

    Delete this and a record could come to hold the secret, or a send use one from elsewhere."""
    record = fresh_record()
    send(world, note(), record=record)
    assert world.secrets.reads == [record.secret]
    assert record.secret == SecretRef(
        path=f"{CHANNEL_SECRET_PREFIX}webhook", role=VaultRole.APPLICATION
    )
    assert SECRET not in repr(record)
    request = world.transport.sent[0]
    assert request.headers[SIGNATURE_HEADER] == sign(
        SECRET, request.headers[TIMESTAMP_HEADER], request.body
    )


def test_a_switched_off_channel_sends_nothing_and_borrows_nothing(world: World) -> None:
    """**M10.6.3's sending half.** Delete this and a channel switched off goes on sending."""
    assert (
        send(world, note(), record=fresh_record(enabled=False)).reason
        is RefusedBecause.SWITCHED_OFF
    )
    assert send(world, note(ref="note.2"), use_record=False).reason is RefusedBecause.NOT_CONFIGURED
    assert world.secrets.reads == []
    assert world.transport.sent == []
    assert world.deliveries.seen() == [
        ("outbound", "refused", "switched_off"),
        ("outbound", "refused", "not_configured"),
    ]


def test_an_answer_is_refused_when_its_recipient_s_reach_changed_before_it_left(
    world: World,
) -> None:
    """**M10.4.5.** The reach is loaded again at send time and a different hash refuses the send.
    The same reach sends.

    Delete this and a queued answer delivers what its recipient lost the right to see."""
    held = (Grant(capability=Capability(value="read:client"), scope=Scope.unrestricted()),)
    planned = EntitlementSet(principal_id="u_admin", grants=held).ent_hash()
    answer = note("an answer", recipient="u_admin", planned_hash=planned)
    revoked = send(world, answer, reach=Reach(grants=()))
    assert revoked.reason is RefusedBecause.REACH_CHANGED
    assert world.transport.sent == []
    kept = send(
        world,
        note("an answer", ref="note.2", recipient="u_admin", planned_hash=planned),
        reach=Reach(grants=held),
    )
    assert kept.outcome is DeliveryOutcome.SENT


def test_a_message_for_nobody_in_particular_carries_nothing_from_the_data() -> None:
    """`A_MESSAGE_FOR_NOBODY_IN_PARTICULAR_CARRIES_NOTHING`. Delete this and a payload with records
    could be sent with no reach ever checked against it."""
    with pytest.raises(ValueError, match="product sentence"):
        note(payload=ChannelPayload(records=({"client": "x"},)))
    with pytest.raises(ValueError, match="names them"):
        note(recipient="u_admin")
    assert "product sentence" in A_MESSAGE_FOR_NOBODY_IN_PARTICULAR_CARRIES_NOTHING


def test_a_label_the_text_dropped_or_a_class_above_the_ceiling_is_refused(world: World) -> None:
    """**M10.1.5 at the one send path.** A body that loses the opaque label, or a payload above
    the surface's ceiling, is refused before any request is built; the label kept is sent.

    Delete this and the escape hatch's warning can be dropped by a composed body."""
    labelled = ChannelPayload(label=OPAQUE_LABEL)
    dropped = Outgoing(
        channel=Channel.WEBHOOK,
        to="conv-7",
        intent=Intent(principal_id="u_admin", intent_ref="l.1"),
        text="no label here",
        payload=labelled,
        recipient="u_admin",
        planned_hash=EntitlementSet(principal_id="u_admin", grants=()).ent_hash(),
    )
    assert send(world, dropped).reason is RefusedBecause.CANNOT_CARRY
    above = note(ref="l.2", highest=Classification.CONFIDENTIAL)
    assert send(world, above).reason is RefusedBecause.CANNOT_CARRY
    assert world.transport.sent == []
    kept = Outgoing(
        channel=Channel.WEBHOOK,
        to="conv-7",
        intent=Intent(principal_id="u_admin", intent_ref="l.3"),
        payload=labelled,
        recipient="u_admin",
        planned_hash=EntitlementSet(principal_id="u_admin", grants=()).ent_hash(),
    )
    assert send(world, kept).outcome is DeliveryOutcome.SENT
    assert OPAQUE_LABEL in world.transport.texts()[0]


def test_one_intent_is_sent_once_and_recorded_once(world: World) -> None:
    """Delete this and a retried delivery posts twice, and is counted twice."""
    first = send(world, note())
    again = send(world, note())
    assert (first.issued, again.issued) == (True, False)
    assert again.outcome is DeliveryOutcome.SENT
    assert len(world.transport.sent) == 1
    assert len(world.deliveries.entries) == 1


def test_a_record_that_names_no_reply_address_is_refused_as_incomplete(world: World) -> None:
    """Delete this and a channel with no reply address fails as an exception inside a request."""
    assert send(world, note(), record=fresh_record(tenant={})).reason is RefusedBecause.INCOMPLETE


# ======================================================================== the secrets reader


def test_the_secrets_reader_reads_a_channel_slot_and_no_other() -> None:
    """`A_CHANNEL_READS_ONLY_ITS_OWN_SLOT`. Delete this and the channel reader is a second way to
    read a model provider's key, which shares its engine."""
    vault = KeptVault()
    vault.slots[f"{CHANNEL_SECRET_PREFIX}webhook"] = {KEY_FIELD: SECRET}
    vault.slots["providers/anthropic"] = {KEY_FIELD: "sk-not-a-channel"}
    reader = VaultChannelSecrets(vault)
    assert reader.read(channel_secret_ref(Channel.WEBHOOK)) == SECRET
    assert reader.held(channel_secret_ref(Channel.WEBHOOK)) is True
    assert reader.read(channel_secret_ref(Channel.LARK)) is None
    with pytest.raises(ValueError, match="not a channel's slot"):
        reader.read(SecretRef(path="providers/anthropic", role=VaultRole.APPLICATION))
    with pytest.raises(ValueError, match="not a channel's slot"):
        reader.read(SecretRef(path=f"{CHANNEL_SECRET_PREFIX}webhook", role=VaultRole.WORKER))
    with pytest.raises(ChannelSecretsUnavailableError):
        VaultChannelSecrets(None).read(channel_secret_ref(Channel.WEBHOOK))
    assert "not a channel's slot" not in A_CHANNEL_READS_ONLY_ITS_OWN_SLOT


# ================================================================ the record's routes (M10.6.3)


def test_a_channel_is_set_up_with_its_secret_kept_in_the_vault_and_never_sent_back(
    client: TestClient, world: World
) -> None:
    """The positive case for the refusals below. The secret goes to the channel's own slot, the
    record keeps the tenant and a reference, and nothing sent back holds the secret.

    Delete this and every refusal below passes against a route that sets nothing up."""
    answer = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={"enabled": True, "tenant": {REPLY_URL: REPLY_TO}, "secret": SECRET},
        headers=headers("u_admin"),
    )
    assert answer.status_code == 200, answer.text
    assert SECRET not in answer.text
    view = answer.json()
    assert (view["configured"], view["enabled"], view["tenant"]) == (
        True,
        True,
        {REPLY_URL: REPLY_TO},
    )
    assert view["events_path"] == f"{API_PREFIX}/channels/webhook/events"
    assert world.vault.slots == {f"{CHANNEL_SECRET_PREFIX}webhook": {KEY_FIELD: SECRET}}
    assert world.records.kept[Channel.WEBHOOK].updated_by == "u_admin"


def test_a_field_the_channel_does_not_take_is_refused_and_the_secret_is_not_echoed(
    client: TestClient, world: World
) -> None:
    """Delete this and a record can hold whatever was pasted into it, a key included."""
    answer = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={"enabled": True, "tenant": {"api_key": SECRET}, "secret": SECRET},
        headers=headers("u_admin"),
    )
    assert answer.status_code == 422
    assert SECRET not in answer.text
    assert world.records.kept == {}
    assert world.vault.slots == {}


def test_an_install_with_no_vault_keeps_no_secret_and_writes_no_record(
    client: TestClient, world: World
) -> None:
    """Delete this and a channel is switched on with nothing behind it."""
    client.app.state.credentials = Credentials(None)  # type: ignore[attr-defined]
    answer = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={"enabled": True, "tenant": {}, "secret": SECRET},
        headers=headers("u_admin"),
    )
    assert answer.status_code == 409
    assert world.records.kept == {}


@pytest.mark.parametrize("pid", ["u_none", "u_wide", "u_narrow"])
def test_a_reader_without_the_channel_authority_over_it_is_refused_as_on_nothing(
    client: TestClient, world: World, pid: str
) -> None:
    """`A_CHANNEL_IS_GOVERNED_BY_THE_AUTHORITY_CONNECT_LARK_ASKS`. `u_narrow` holds it over the
    widget channel and not this one. The refusal is the answer to a channel that does not exist.

    Delete this and anybody signed in can switch a channel on and point its replies elsewhere."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    put = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={"enabled": False, "tenant": {}},
        headers=headers(pid),
    )
    nowhere = client.put(
        f"{API_PREFIX}/channels/carrier-pigeon",
        json={"enabled": False, "tenant": {}},
        headers=headers(pid),
    )
    assert put.status_code == nowhere.status_code == 404
    assert body_of(put) == body_of(nowhere)
    for path, sent in (("/switch", {"enabled": False}), ("/test", {"to": "conv-7"})):
        refused = client.post(
            f"{API_PREFIX}/channels/webhook{path}", json=sent, headers=headers(pid)
        )
        assert refused.status_code == 404
    assert (
        client.get(f"{API_PREFIX}/channels/webhook/deliveries", headers=headers(pid)).status_code
        == 404
    )
    assert client.get(f"{API_PREFIX}/channels", headers=headers(pid)).json()["channels"] == []
    assert world.records.kept[Channel.WEBHOOK].enabled is True
    assert world.transport.sent == []


def test_switching_one_channel_off_stops_it_receiving_and_sending_and_leaves_another_alone(
    client: TestClient, world: World, probe: ModuleType
) -> None:
    """**M10.6.3's whole sentence, through the routes.** Two channels on; one switched off refuses
    what arrives and refuses a test message, and the other goes on receiving and sending.

    Delete this and a switch could reach another channel's record, or stop only one direction."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    world.records.kept[Channel.WIDGET] = fresh_record(Channel.WIDGET)
    world.secrets.slots[channel_secret_ref(Channel.WIDGET).path] = SECRET
    off = client.post(
        f"{API_PREFIX}/channels/webhook/switch", json={"enabled": False}, headers=headers("u_admin")
    )
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert world.records.kept[Channel.WIDGET].enabled is True

    raw, sent = signed(message("m-5"))
    assert post_event(client, raw, sent).status_code == 404
    assert post_event(client, raw, sent, name="widget").json() == {
        "status": "accepted",
        "reply": "sent",
    }
    test = client.post(
        f"{API_PREFIX}/channels/webhook/test", json={"to": "conv-7"}, headers=headers("u_admin")
    )
    assert test.json()["outcome"] == "refused" and test.json()["reason"] == "switched_off"
    other = client.post(
        f"{API_PREFIX}/channels/widget/test", json={"to": "conv-7"}, headers=headers("u_narrow")
    )
    assert other.json()["outcome"] == "sent"
    by_channel = {
        channel: [
            (one.direction.value, one.outcome.value, one.reason and one.reason.value)
            for one in world.deliveries.entries
            if one.channel is channel
        ]
        for channel in (Channel.WEBHOOK, Channel.WIDGET)
    }
    assert by_channel[Channel.WEBHOOK] == [
        ("inbound", "refused", "switched_off"),
        ("outbound", "refused", "switched_off"),
    ]
    assert by_channel[Channel.WIDGET] == [
        ("inbound", "accepted", None),
        ("outbound", "sent", None),
        ("outbound", "sent", None),
    ]


def test_a_test_message_is_sent_once_per_record_and_destination(
    client: TestClient, world: World
) -> None:
    """Delete this and every press of the button is another message at the other end."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    first = client.post(
        f"{API_PREFIX}/channels/webhook/test", json={"to": "conv-7"}, headers=headers("u_admin")
    )
    again = client.post(
        f"{API_PREFIX}/channels/webhook/test", json={"to": "conv-7"}, headers=headers("u_admin")
    )
    assert (first.json()["issued"], again.json()["issued"]) == (True, False)
    assert len(world.transport.sent) == 1
    assert world.transport.texts() == [channel_routes.TEST_MESSAGE]


def test_switching_a_channel_with_no_record_says_to_set_it_up(
    client: TestClient, world: World
) -> None:
    """Delete this and switching a channel nobody set up can look as though it worked."""
    answer = client.post(
        f"{API_PREFIX}/channels/webhook/switch", json={"enabled": True}, headers=headers("u_admin")
    )
    assert answer.status_code == 409
    assert world.records.kept == {}


def test_the_list_and_the_deliveries_show_the_manager_what_happened_and_nothing_said(
    client: TestClient, world: World
) -> None:
    """Delete this and the install has no way to show a person that a refusal was recorded."""
    world.records.kept[Channel.WEBHOOK] = fresh_record()
    raw, sent = signed(message(text=CANARY), secret=WRONG)
    post_event(client, raw, sent)
    listed = client.get(f"{API_PREFIX}/channels", headers=headers("u_admin")).json()["channels"]
    webhook = next(one for one in listed if one["channel"] == "webhook")
    assert (webhook["receives"], webhook["enabled"], webhook["secret_held"]) == (True, True, True)
    assert {one["channel"] for one in listed} == {
        factory().capabilities().channel.value for factory in channel_adapters()
    }
    rows = client.get(f"{API_PREFIX}/channels/webhook/deliveries", headers=headers("u_admin"))
    assert [(r["direction"], r["outcome"], r["reason"]) for r in rows.json()["deliveries"]] == [
        ("inbound", "refused", "bad_signature")
    ]
    assert CANARY not in rows.text
    narrow = client.get(f"{API_PREFIX}/channels", headers=headers("u_narrow")).json()["channels"]
    assert narrow == []


# ======================================================================== the audit ledger


@dataclass
class CredentialRecords:
    """`brain.ops.credentials.CredentialWrites`, keeping every record it was asked to make."""

    kept: list[dict[str, str]] = field(default_factory=list)

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        self.kept.append(
            {"slot": slot, "written_by": written_by, "trace_id": trace_id, "ent_hash": ent_hash}
        )


def test_a_set_up_and_a_switch_are_attributed_to_the_caller_s_reach_and_request(
    client: TestClient, world: World
) -> None:
    """**The owner's rule that every change is audited, through the routes.** Each write reaches
    the store with the caller, their live reach digest and the request's trace, which is what the
    trigger writes into the ledger entry instead of `0003`'s placeholders.

    Delete this and a route can write a channel with the placeholders, and the ledger cannot say
    at what reach, or in which request, a channel was switched on."""
    put = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={"enabled": True, "tenant": {REPLY_URL: REPLY_TO}},
        headers=headers("u_admin"),
    )
    off = client.post(
        f"{API_PREFIX}/channels/webhook/switch", json={"enabled": False}, headers=headers("u_admin")
    )
    assert put.status_code == off.status_code == 200
    assert [actor for actor, _, _ in world.records.attributed] == ["u_admin", "u_admin"]
    for _, reach, trace in world.records.attributed:
        assert re.fullmatch(r"[0-9a-f]{32}", reach) and reach != "0" * 32
        assert trace and not trace.startswith("tx.")
    assert world.records.attributed[0][2] != world.records.attributed[1][2]


def test_a_secret_replaced_is_recorded_by_its_slot_and_never_by_its_value(
    client: TestClient, world: World
) -> None:
    """The secret's replacement is `0054`'s `credential` entry, naming the channel's slot, the
    caller and the request, and the record handed to it has nowhere to put the value.

    Delete this and a secret can be replaced from the console with nothing in the ledger."""
    writes = CredentialRecords()
    client.app.state.credentials = Credentials(world.vault, writes=writes)  # type: ignore[attr-defined]
    answer = client.put(
        f"{API_PREFIX}/channels/webhook",
        json={"enabled": True, "tenant": {}, "secret": SECRET},
        headers=headers("u_admin"),
    )
    assert answer.status_code == 200
    assert len(writes.kept) == 1
    kept = writes.kept[0]
    assert (kept["slot"], kept["written_by"]) == (f"{CHANNEL_SECRET_PREFIX}webhook", "u_admin")
    assert kept["trace_id"] == world.records.attributed[0][2]
    assert SECRET not in repr(writes.kept)


class Executed:
    """An `AsyncSession` stand-in keeping the statements it was given, in order."""

    def __init__(self, returned: Any) -> None:
        self.statements: list[Any] = []
        self.returned = returned

    async def __aenter__(self) -> Executed:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def begin(self) -> Executed:
        return self

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        returned = self.returned

        class Result:
            def scalar_one(self) -> Any:
                return returned

            def scalar_one_or_none(self) -> Any:
                return returned

        return Result()


def test_the_store_sets_the_attribution_in_the_transaction_before_it_writes() -> None:
    """`A_CHANNEL_CHANGE_IS_ATTRIBUTED_IN_ITS_OWN_TRANSACTION`, read off the statements. The three
    settings first, then the write, in one session, for a save and for a switch.

    Delete this and the store can write first and attribute afterwards, when the trigger has
    already read nothing."""
    row = ChannelRow(
        channel="webhook",
        enabled=True,
        tenant={},
        secret_path=f"{CHANNEL_SECRET_PREFIX}webhook",
        secret_role="application",
        updated_by="u_admin",
        updated_at=LONG_AGO,
    )
    for write in ("save", "switch"):
        session = Executed(row)
        # A factory handing back the stand-in: the store only calls it and enters what it returns.
        stored = StoredChannels(cast(Any, lambda held=session: held))

        async def through(stored: StoredChannels = stored, write: str = write) -> object:
            if write == "save":
                return await stored.save(Channel.WEBHOOK, enabled=True, tenant={}, **AS_ADMIN)
            return await stored.switch(Channel.WEBHOOK, enabled=False, **AS_ADMIN)

        run(through)
        said = [str(one) for one in session.statements]
        settings = [one.compile().params for one in session.statements[:3]]
        assert all("set_config" in one for one in said[:3]), write
        assert [one["name"] for one in settings] == [
            "brain.actor_id",
            "brain.ent_hash",
            "brain.trace_id",
        ]
        assert [one["value"] for one in settings] == ["u_admin", REACH, TRACE]
        assert len(said) == 4 and "ops.channel" in said[3], write


def trigger() -> str:
    return " ".join(migration().CHANNEL_TRIGGER_FUNCTION.split())


def test_the_channel_trigger_writes_the_setting_words_its_writer_and_never_the_tenant() -> None:
    """Held to `AuditRecorder.setting`, which writes the same entry in code: the subject names the
    channel, the words are the setting's, the actor is the row's own `updated_by`, and the details
    are the change word alone.

    Delete this and the trigger can drift from the recorder, name no channel, or write a tenant
    value into the table that is kept longest."""
    body = trigger()
    written = re.findall(r"v_changes := v_changes \|\| '(\w+)'::text;", body)
    assert sorted(written) == ["set", "switched_off", "switched_on"]
    assert set(written) <= {one.value for one in SettingChange}
    assert "v_subject text := 'setting:channel.' || NEW.channel;" in body
    assert "v_details := jsonb_build_object('change', v_changes[i]);" in body
    assert "v_seq, v_at, NEW.updated_by, 'setting', v_subject, v_ent_hash," in body
    assert "OLD.tenant IS DISTINCT FROM NEW.tenant" in body
    assert "OLD.enabled IS DISTINCT FROM NEW.enabled" in body
    assert "NEW.tenant)" not in body and "secret" not in body
    entry = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash=REACH, trace_id=TRACE, clock=lambda: LONG_AGO
    ).setting(key="channel.webhook", change=SettingChange.SWITCHED_OFF)
    assert (entry.subject, dict(entry.details)) == (
        "setting:channel.webhook",
        {"change": "switched_off"},
    )
    up = squash(rendered("upgrade", MIGRATION_0114))
    assert "CREATE TRIGGER channel_is_audited AFTER INSERT OR UPDATE ON ops.channel" in up
    down = squash(rendered("downgrade", MIGRATION_0114))
    assert "DROP TRIGGER channel_is_audited ON ops.channel" in down
    assert "DROP FUNCTION ops.record_channel_change()" in down


@pytest.fixture(scope="module")
def migrated() -> Iterator[str]:
    """A database built through every migration that ships, which a server with pgvector builds."""
    with retirable("brain_test_channel_audit") as url:
        if not has_pgvector(url):
            pytest.skip("the migrations to 0114 need pgvector, which CI's server has")
        yield url


def test_each_set_up_and_switch_leaves_one_attributed_entry_and_the_chain_verifies(
    migrated: str,
) -> None:
    """**The owner's rule against a server, as the application role.** A set-up is `set` and
    `switched_on`; a switch off is `switched_off`; a save that changes nothing appends nothing; a
    new tenant is `set`. Every entry names the channel, the writer, their reach and the request,
    holds the change word and nothing else, and the chain verifies.

    Delete this and the trigger is only ever read, and the first time it runs is on an install."""
    sql(migrated, "TRUNCATE ops.channel")
    before = len(entries(migrated))

    async def through() -> None:
        db = app_engine(migrated)
        stored = StoredChannels(async_sessionmaker(db, expire_on_commit=False))
        await stored.save(Channel.WEBHOOK, enabled=True, tenant={REPLY_URL: REPLY_TO}, **AS_ADMIN)
        await stored.switch(Channel.WEBHOOK, enabled=False, **AS_OTHER)
        await stored.save(Channel.WEBHOOK, enabled=False, tenant={REPLY_URL: REPLY_TO}, **AS_OTHER)
        await stored.save(Channel.WEBHOOK, enabled=False, tenant={}, **AS_ADMIN)
        await db.dispose()

    run(through)
    chain = entries(migrated)
    mine = chain[before:]
    assert [(one.actor_id, one.subject, dict(one.details)) for one in mine] == [
        ("u_admin", "setting:channel.webhook", {"change": "set"}),
        ("u_admin", "setting:channel.webhook", {"change": "switched_on"}),
        ("u_other", "setting:channel.webhook", {"change": "switched_off"}),
        ("u_admin", "setting:channel.webhook", {"change": "set"}),
    ]
    assert {(one.action.value, one.ent_hash, one.trace_id) for one in mine} == {
        ("setting", REACH, TRACE)
    }
    assert REPLY_TO not in repr(mine)
    assert AuditChain(chain).verify() is None


# ======================================================================== the migration


def migration() -> ModuleType:
    return migration_module(MIGRATION_0114)


def test_0114_builds_both_tables_exactly_as_the_models_declare_them() -> None:
    """Delete this and the model and the migration can disagree about a column or a check, and
    a row the code writes is refused on an install."""
    up = squash(rendered("upgrade", MIGRATION_0114))
    for qualified in ("ops.channel", "ops.channel_delivery"):
        expected = squash(str(CreateTable(table(qualified)).compile(dialect=DIALECT)))
        assert expected in up, qualified
    index = next(iter(table("ops.channel_delivery").indexes))
    assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in up
    down = squash(rendered("downgrade", MIGRATION_0114))
    assert "DROP TABLE ops.channel_delivery" in down and "DROP TABLE ops.channel" in down


def test_0114_copies_every_check_and_width_it_shares_with_the_models() -> None:
    """Held against the vocabularies the models are built from, not against themselves.

    Delete this and a reason, an outcome or a channel reaches the code and not the database."""
    m = migration()
    assert one_of("channel", Channel) == m.CHANNELS
    assert f"reason IS NULL OR {one_of('reason', RefusedBecause)}" == m.REASONS
    assert outcome_fits_direction() == m.OUTCOME_FITS_DIRECTION
    assert one_of("direction", Direction) == m.DIRECTIONS
    assert f"secret_path = '{CHANNEL_SECRET_PREFIX}' || channel" == m.SLOT_IS_DERIVED
    widest = max(len(one.value) for one in Channel)
    assert m.CHANNEL_CHARS == channel_table.CHANNEL_CHARS >= widest
    assert m.SECRET_PATH_CHARS == SECRET_PATH_CHARS >= len(CHANNEL_SECRET_PREFIX) + widest
    assert (
        m.WORD_CHARS
        == channel_table.WORD_CHARS
        >= max(len(one.value) for one in (*Direction, *DeliveryOutcome, *RefusedBecause))
    )
    assert m.REASON_WHEN_NOT_DELIVERED == channel_table.REASON_WHEN_NOT_DELIVERED
    assert checks("ops.channel_delivery")["ck_channel_delivery_reason_known"] == m.REASONS
    assert checks("ops.channel")["ck_channel_secret_path_is_derived"] == m.SLOT_IS_DERIVED
    assert m.down_revision == "0113"


def test_0114_secures_both_tables_and_grants_no_delete_and_no_rewrite_of_a_delivery() -> None:
    """**Every new table enables row-level security.** A delivery row is appended and never
    changed, and a channel is switched off rather than removed.

    Delete this and a later edit can grant a rewrite of what the vendor said."""
    up = squash(rendered("upgrade", MIGRATION_0114))
    for qualified in ("ops.channel", "ops.channel_delivery"):
        assert f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY" in up
    m = migration()
    assert m.GRANTS == (
        "GRANT SELECT, INSERT, UPDATE ON ops.channel TO brain_app",
        "GRANT SELECT, INSERT ON ops.channel_delivery TO brain_app",
    )
    assert "FOR DELETE" not in up
    assert "ON ops.channel_delivery FOR UPDATE" not in up


# ======================================================================== against a server

TABLES = ("ops.channel", "ops.channel_delivery", "gate.channel_event")


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with modelled("brain_test_channel_pipeline", TABLES) as url:
        yield url


def test_the_stores_keep_one_row_per_channel_and_switch_only_the_one_named(database: str) -> None:
    """**M10.6.3 against a server.** Two records; one switched off; the other unchanged; the
    reference derived. Delete this and the upsert and the switch are only ever faked."""
    sql(database, "TRUNCATE ops.channel")
    db = engine(database)
    stored = StoredChannels(async_sessionmaker(db, expire_on_commit=False))

    async def through() -> tuple[
        ChannelRecord | None, ChannelRecord | None, tuple[ChannelRecord, ...]
    ]:
        await stored.save(Channel.WEBHOOK, enabled=True, tenant={REPLY_URL: REPLY_TO}, **AS_ADMIN)
        await stored.save(Channel.LARK, enabled=True, tenant={}, **AS_ADMIN)
        await stored.switch(Channel.WEBHOOK, enabled=False, **AS_OTHER)
        missing = await stored.switch(Channel.SLACK, enabled=False, **AS_OTHER)
        webhook = await stored.get(Channel.WEBHOOK)
        every = await stored.every()
        await db.dispose()
        return missing, webhook, every

    missing, webhook, every = run(through)
    assert missing is None
    assert webhook is not None and (webhook.enabled, webhook.updated_by) == (False, "u_other")
    assert webhook.secret == channel_secret_ref(Channel.WEBHOOK)
    assert dict(webhook.tenant) == {REPLY_URL: REPLY_TO}
    assert [(one.channel, one.enabled) for one in every] == [
        (Channel.LARK, True),
        (Channel.WEBHOOK, False),
    ]


def test_a_row_pointing_at_another_slot_or_pairing_a_wrong_outcome_is_refused(
    database: str,
) -> None:
    """The table's own checks. Delete this and a hand-written row can point a channel at a
    provider's key, or record an inbound delivery as sent."""
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO ops.channel "
            "(channel, enabled, tenant, secret_path, secret_role, updated_by) "
            "VALUES ('webhook', true, '{}', 'providers/anthropic', 'application', 'u_admin')",
        )
    for direction, outcome, reason in (("inbound", "sent", None), ("outbound", "refused", None)):
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(
                database,
                "INSERT INTO ops.channel_delivery (channel, direction, outcome, reason) "
                "VALUES ('webhook', %s, %s, %s)",
                direction,
                outcome,
                reason,
            )


def test_deliveries_are_appended_and_read_newest_first_and_a_claim_is_granted_once(
    database: str,
) -> None:
    """**M3.2.2 and M10.6.1 against a server.** Delete this and the claim and the record are only
    ever faked, and the first time either runs is on an install."""
    sql(database, "TRUNCATE ops.channel_delivery")
    sql(database, "TRUNCATE gate.channel_event")
    db = engine(database)
    sessions = async_sessionmaker(db, expire_on_commit=False)
    deliveries = StoredDeliveries(sessions)
    claims = StoredClaims(sessions)
    event = ChannelEvent(
        channel=Channel.WEBHOOK,
        external_id="m-1",
        channel_identity="person-42",
        text="",
        received_at=LONG_AGO,
    )

    async def through() -> tuple[bool, bool, tuple[DeliveryView, ...]]:
        await deliveries.record(
            DeliveryEntry(
                Channel.WEBHOOK,
                Direction.INBOUND,
                DeliveryOutcome.REFUSED,
                RefusedBecause.BAD_SIGNATURE,
            )
        )
        await deliveries.record(
            DeliveryEntry(
                Channel.WEBHOOK, Direction.OUTBOUND, DeliveryOutcome.SENT, vendor_status=200
            )
        )
        first = await claims.first(event)
        second = await claims.first(event)
        recent = await deliveries.recent(Channel.WEBHOOK)
        await db.dispose()
        return first, second, recent

    first, second, recent = run(through)
    assert (first, second) == (True, False)
    assert {one.entry.outcome for one in recent} == {DeliveryOutcome.REFUSED, DeliveryOutcome.SENT}
    assert recent[0].recorded_at >= recent[-1].recorded_at
