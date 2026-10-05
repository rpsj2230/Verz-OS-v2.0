"""The Teams channel, end to end: a token Microsoft signs in, answers out on a token the client
secret is exchanged for, and the Bot Framework's published keys fetched by the route.

Three halves. The wire, over activities and tokens built here with a real RSA key, so the check
that runs is the RS256 check an install runs; each refusal beside what it accepts. The keys,
read from documents shaped as Microsoft documents them and fetched through the channel
transport. And the events address, where a signed personal message from somebody bound to
nobody is answered in that chat, through Microsoft's reply host, and nothing else leaves.

Task ids: M10.5.2, M10.6.1
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, quote

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import channel_routes
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.channels.adapter import (
    BOT_ID,
    SECRET_ASK,
    Arrived,
    VendorAnswer,
    VendorRequest,
    channel_guides,
)
from brain.channels.teams import (
    BOT_FRAMEWORK_ISSUER,
    BOT_FRAMEWORK_METADATA_URL,
    GUIDE,
    TENANT_ID,
    WIRE,
    question_of,
)
from brain.channels.webhook import WebhookRefusedError
from brain.connectors.throttle import CallOutcome
from brain.gate.context import Channel
from brain.gate.ingress import Unrecognised, identity_hash
from brain.identity.oidc import KeySet, SigningKey
from brain.ops.channel_store import channel_secret_ref
from brain.tables.channel import RefusedBecause
from tests.fixtures.operation_ledger import MemoryLedger
from tests.unit.test_channel_pipeline import World, fresh_record

#: Pinned far from any wall clock, for `CLAUDE.md`'s reason: nothing below is about the present.
NOW = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
APP = "8f3c1e2a-1111-4000-8000-abcdef123456"
TENANT = "1b2c3d4e-3333-4000-8000-0123456789ab"
OTHER_TENANT = "9e8d7c6b-4444-4000-8000-ba9876543210"
SERVICE = "https://smba.trafficmanager.net/emea/"
PERSON = "3a1f0c22-5555-4000-8000-1a2b3c4d5e6f"
PERSONAL = "a:1qPvXoJm7YkQ0w"
ROOM = "19:9d4f2a1b6c3e@thread.tacv2"
SECRET = "teams-client-secret-sentinel-0123"
KID = "bf-test-key"
EVENTS = f"{API_PREFIX}/channels/teams/events"
TENANT_FIELDS = {BOT_ID: APP, TENANT_ID: TENANT}

_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(private: rsa.RSAPrivateKey) -> str:
    return (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


def keys(private: rsa.RSAPrivateKey = _PRIVATE, kid: str = KID) -> KeySet:
    key = SigningKey(kid=kid, algorithm="RS256", material=_pem(private), use="sig")
    return KeySet(issuer=BOT_FRAMEWORK_ISSUER, keys=(key,), fetched_at=NOW)


def _b64(blob: bytes) -> str:
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def token(
    *, signed_with: rsa.RSAPrivateKey = _PRIVATE, at: datetime = NOW, **claims: object
) -> str:
    """A compact RS256 JWS as the Bot Framework mints one for this bot."""
    head = {"alg": "RS256", "kid": KID, "typ": "JWT"}
    body: dict[str, object] = {
        "iss": BOT_FRAMEWORK_ISSUER,
        "aud": APP,
        "serviceurl": SERVICE,
        "nbf": int(at.timestamp()) - 60,
        "exp": int((at + timedelta(minutes=30)).timestamp()),
    }
    body.update(claims)
    signing = f"{_b64(json.dumps(head).encode())}.{_b64(json.dumps(body).encode())}"
    signature = signed_with.sign(signing.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing}.{_b64(signature)}"


def activity(
    *,
    text: str = "what is outstanding",
    conversation: str = PERSONAL,
    kind: str = "personal",
    tenant: str = TENANT,
    service: str = SERVICE,
    at: datetime = NOW,
    **extra: object,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "message",
        "id": "1757160000000",
        "channelId": "msteams",
        "serviceUrl": service,
        "timestamp": at.isoformat(),
        "from": {"id": "29:1kQvXoJm7Y", "name": "Priya Menon", "aadObjectId": PERSON},
        "conversation": {"id": conversation, "conversationType": kind},
        "recipient": {"id": f"28:{APP}", "name": "Brain"},
        "text": text,
        "channelData": {"tenant": {"id": tenant}},
    }
    body.update(extra)
    return body


def arrived(
    payload: Mapping[str, Any] | bytes,
    *,
    authorization: str | None = None,
    held: KeySet | None = None,
    tenant: Mapping[str, str] = TENANT_FIELDS,
) -> Arrived:
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return Arrived(
        headers={"authorization": authorization or f"Bearer {token()}"},
        body=raw,
        tenant=tenant,
        keys=held if held is not None else keys(),
    )


# ======================================================================== the wire, inbound


def test_a_personal_message_microsoft_signed_is_read_as_the_directory_s_person() -> None:
    """**The positive half of every refusal below**, verified with a real RS256 signature.

    Delete this and a wire refusing everything would pass every test here."""
    received = WIRE.read(WIRE.verify(arrived(activity()), SECRET, NOW))
    assert (received.event.channel, received.event.channel_identity) == (Channel.TEAMS, PERSON)
    assert received.event.text == "what is outstanding"
    assert received.reply_to == f"{SERVICE} {PERSONAL}"
    conversation = received.conversation
    assert conversation is not None
    assert (conversation.shared, conversation.sender_to) == (False, f"{SERVICE} {PERSONAL}")


def test_a_channel_message_naming_the_bot_is_shared_addressed_and_has_nowhere_private() -> None:
    """**A shared conversation is answered only when it named the bot, and has no private
    reply.** The `<at>` mention that opens it is not the question; the bot is addressed by its
    App ID; nobody in a channel has a conversation of their own to be told in.

    Delete this and the question would carry the mention, or a room could be answered unasked."""
    mention = {"type": "mention", "mentioned": {"id": f"28:{APP}", "name": "Brain"}}
    payload = activity(
        text="<at>Brain</at> what is outstanding",
        conversation=ROOM,
        kind="channel",
        entities=[mention],
    )
    received = WIRE.read(WIRE.verify(arrived(payload), SECRET, NOW))
    assert received.event.text == "what is outstanding"
    conversation = received.conversation
    assert conversation is not None
    assert (conversation.shared, conversation.sender_to, conversation.aside_to) == (True, "", "")
    assert conversation.addressed == {identity_hash(Channel.TEAMS, APP)}


@pytest.mark.parametrize(
    "tamper",
    [
        "no keys",
        "another key",
        "another bot",
        "another tenant",
        "another reply host",
        "expired",
        "no header",
        "not json",
        "record names no tenant",
    ],
)
def test_an_activity_microsoft_did_not_send_for_this_bot_and_tenant_is_refused(tamper: str) -> None:
    """**Every check Microsoft documents, and the tenant pin.** A token no published key signed,
    one minted for another bot, an activity from another tenant or naming a reply host the token
    did not, an expired token, no token, and a record that pins no tenant.

    Delete this and a stranger's bot, or ours installed elsewhere, would be answered."""
    body: Mapping[str, Any] | bytes = activity()
    authorization, held, tenant = None, None, TENANT_FIELDS
    match tamper:
        case "no keys":
            sent = Arrived(headers={"authorization": f"Bearer {token()}"}, body=b"{}", keys=None)
        case "another key":
            authorization = f"Bearer {token(signed_with=_OTHER)}"
        case "another bot":
            authorization = f"Bearer {token(aud='0d4b7c99-2222-4000-8000-fedcba654321')}"
        case "another tenant":
            body = activity(tenant=OTHER_TENANT)
        case "another reply host":
            body = activity(service="https://smba.trafficmanager.net/amer/")
        case "expired":
            authorization = f"Bearer {token(at=NOW - timedelta(hours=2))}"
        case "no header":
            authorization = "Basic x"
        case "not json":
            body = b"not json"
        case _:
            tenant = {BOT_ID: APP}
    if tamper != "no keys":
        sent = arrived(body, authorization=authorization, held=held, tenant=tenant)
    with pytest.raises(WebhookRefusedError):
        WIRE.verify(sent, SECRET, NOW)


def test_only_the_mentions_that_open_a_message_are_left_out() -> None:
    """Delete this and a question naming a colleague would lose who it is about."""
    assert question_of("<at>Brain</at>  <at>Ann</at> hello <at>Bo</at>") == "hello <at>Bo</at>"


# ======================================================================== the keys


def metadata(**changed: object) -> bytes:
    document: dict[str, object] = {
        "issuer": BOT_FRAMEWORK_ISSUER,
        "jwks_uri": "https://login.botframework.com/v1/.well-known/keys",
        "id_token_signing_alg_values_supported": ["RS256"],
    }
    document.update(changed)
    return json.dumps(document).encode()


def jwks(private: rsa.RSAPrivateKey = _PRIVATE) -> bytes:
    """A key set as the Bot Framework publishes one: RSA, for signing, and naming no `alg`."""
    numbers = private.public_key().public_numbers()

    def b64(value: int) -> str:
        return _b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    key = {"kty": "RSA", "use": "sig", "kid": KID, "n": b64(numbers.n), "e": b64(numbers.e)}
    return json.dumps({"keys": [key]}).encode()


def test_the_bot_framework_s_keys_are_read_as_the_algorithm_its_document_names() -> None:
    """**Microsoft's key set names no algorithm on its keys, and its document names RS256.**
    Read so, the published key verifies a real token.

    Delete this and every key would be dropped for naming no algorithm, and Teams would never
    verify on an install."""
    read = WIRE.key_set_of(metadata(), jwks(), NOW)
    assert [(one.kid, one.algorithm) for one in read.keys] == [(KID, "RS256")]
    received = WIRE.read(WIRE.verify(arrived(activity(), held=read), SECRET, NOW))
    assert received.event.channel_identity == PERSON


@pytest.mark.parametrize(
    ("document", "published"),
    [
        (metadata(issuer="https://example.test"), jwks()),
        (metadata(id_token_signing_alg_values_supported=["HS256"]), jwks()),
        (metadata(id_token_signing_alg_values_supported="RS256"), jwks()),
        (metadata(), json.dumps({"keys": []}).encode()),
        (metadata(), json.dumps({"keys": "x"}).encode()),
        (b"not json", jwks()),
    ],
)
def test_a_document_that_is_not_the_bot_framework_s_gives_no_keys(
    document: bytes, published: bytes
) -> None:
    """Delete this and a document from elsewhere, or one naming a symmetric algorithm, could
    choose what this install trusts."""
    with pytest.raises(ValueError):
        WIRE.key_set_of(document, published, NOW)


# ======================================================================== the wire, outbound


def test_a_reply_goes_to_the_signed_reply_host_on_a_token_the_secret_is_exchanged_for() -> None:
    """**The reply and the exchange that authorises it.** Posted into the conversation on the
    reply host, as plain text; the client secret goes only to Microsoft's login for this tenant.

    Delete this and a reply could leave with no token, or the secret go somewhere else."""
    request = WIRE.request_for(
        to=f"{SERVICE} {PERSONAL}",
        text="Two invoices.",
        secret=SECRET,
        tenant=TENANT_FIELDS,
        now=NOW,
    )
    assert request.url == f"{SERVICE}v3/conversations/{quote(PERSONAL, safe='')}/activities"
    assert json.loads(request.body) == {
        "type": "message",
        "text": "Two invoices.",
        "textFormat": "plain",
    }
    exchange = request.exchange
    assert exchange is not None
    assert exchange.url == f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    assert exchange.content_type == "application/x-www-form-urlencoded"
    assert parse_qs(exchange.body.decode()) == {
        "grant_type": ["client_credentials"],
        "client_id": [APP],
        "client_secret": [SECRET],
        "scope": ["https://api.botframework.com/.default"],
    }
    assert SECRET not in repr(request)


@pytest.mark.parametrize(
    "to",
    [
        PERSONAL,
        f"{SERVICE} ",
        f"http://smba.trafficmanager.net/emea/ {PERSONAL}",
        f"https://smba.trafficmanager.net.example.invalid/emea/ {PERSONAL}",
        f"https://example.test/ {PERSONAL}",
        f"{SERVICE} {PERSONAL} extra",
    ],
)
def test_a_reply_to_anywhere_but_microsoft_s_reply_hosts_is_refused(to: str) -> None:
    """**A reply carries a token that speaks as the bot**, so it is only ever posted to
    Microsoft. Delete this and a test message typed by hand could send the token anywhere."""
    with pytest.raises(ValueError):
        WIRE.request_for(to=to, text="x", secret=SECRET, tenant=TENANT_FIELDS, now=NOW)


@pytest.mark.parametrize(
    "tenant",
    [{BOT_ID: APP}, {BOT_ID: "not-a-guid", TENANT_ID: TENANT}, {BOT_ID: APP, TENANT_ID: "a/b"}],
)
def test_a_record_whose_ids_are_not_directory_ids_cannot_send(tenant: dict[str, str]) -> None:
    """Delete this and a tenant field could put a path into the login address."""
    with pytest.raises(ValueError, match="directory ids"):
        WIRE.request_for(
            to=f"{SERVICE} {PERSONAL}", text="x", secret=SECRET, tenant=tenant, now=NOW
        )


@pytest.mark.parametrize(
    ("answer", "judged"),
    [
        (VendorAnswer(status=201), CallOutcome.OK),
        (VendorAnswer(status=200), CallOutcome.OK),
        (VendorAnswer(status=299), CallOutcome.OK),
        (VendorAnswer(status=302), CallOutcome.REJECTED),
        (VendorAnswer(status=401), CallOutcome.REJECTED),
        (VendorAnswer(status=429), CallOutcome.QUOTA),
        (VendorAnswer(status=503), CallOutcome.UNAVAILABLE),
        (VendorAnswer(timed_out=True), CallOutcome.UNAVAILABLE),
        (VendorAnswer(unsafe_address=True), CallOutcome.REJECTED),
        (VendorAnswer(), CallOutcome.UNAVAILABLE),
    ],
)
def test_the_wire_judges_the_bot_connector_s_answer(
    answer: VendorAnswer, judged: CallOutcome
) -> None:
    """Delete this and a redirect would be taken for delivery, or silence for success."""
    assert WIRE.judge(answer) is judged


# ======================================================================== the steps


def test_teams_s_steps_hold_its_form_and_end_with_the_app_that_carries_the_bot() -> None:
    """Delete this and the steps could ask for the wrong ids, or stop before Teams can see it."""
    steps = channel_guides()[Channel.TEAMS]
    assert steps == GUIDE
    assert [one.key for one in steps if one.asks == (BOT_ID, TENANT_ID, SECRET_ASK)] == ["save"]
    assert steps[-1].key == "app"


# ======================================================================== the routes


@dataclass
class Microsoft:
    """`ChannelTransport` standing in for Microsoft: keeps each send, answers each read."""

    documents: dict[str, bytes] = field(default_factory=dict)
    sent: list[VendorRequest] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)

    def send(self, request: VendorRequest) -> VendorAnswer:
        self.sent.append(request)
        return VendorAnswer(status=201, body=b'{"id":"1"}')

    def read(self, request: VendorRequest) -> VendorAnswer:
        self.reads.append(request.url)
        found = self.documents.get(request.url)
        return VendorAnswer(status=200, body=found) if found else VendorAnswer(status=404)


@pytest.fixture
def world() -> World:
    here = World()
    here.secrets.slots[channel_secret_ref(Channel.TEAMS).path] = SECRET
    here.records.kept[Channel.TEAMS] = fresh_record(Channel.TEAMS, tenant=TENANT_FIELDS)
    return here


def client_for(world: World, microsoft: Microsoft, held: KeySet | None) -> TestClient:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(channel_routes.router)
    app.state.channel_records = world.records
    app.state.channel_deliveries = world.deliveries
    app.state.channel_claims = world.claims
    app.state.channel_secrets = world.secrets
    app.state.channel_transport = microsoft
    app.state.operation_ledger = MemoryLedger()
    if held is not None:
        app.state.channel_keys = held
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def microsoft() -> Microsoft:
    return Microsoft(
        documents={
            BOT_FRAMEWORK_METADATA_URL: metadata(),
            "https://login.botframework.com/v1/.well-known/keys": jwks(),
        }
    )


def post(
    c: TestClient, payload: Mapping[str, Any], *, signed_with: rsa.RSAPrivateKey = _PRIVATE
) -> Any:
    now = datetime.fromtimestamp(time.time(), tz=UTC)
    return c.post(
        EVENTS,
        content=json.dumps(activity(at=now) | dict(payload)).encode(),
        headers={"Authorization": f"Bearer {token(signed_with=signed_with, at=now)}"},
    )


def test_a_personal_message_from_somebody_bound_to_nobody_is_answered_through_microsoft(
    world: World, microsoft: Microsoft
) -> None:
    """**End to end, with the keys fetched as an install fetches them.** The route read the
    metadata and then the key set it named, the token verified against it, and the binding
    prompt was posted into the chat on the reply host, with the exchange beside it.

    Delete this and every other test here is a test of a piece nobody showed the route."""
    with client_for(world, microsoft, None) as c:
        answered = post(c, {})
    assert answered.status_code == 200, answered.text
    assert microsoft.reads == [
        BOT_FRAMEWORK_METADATA_URL,
        "https://login.botframework.com/v1/.well-known/keys",
    ]
    (sent,) = microsoft.sent
    assert sent.url == f"{SERVICE}v3/conversations/{quote(PERSONAL, safe='')}/activities"
    assert json.loads(sent.body)["text"] == Unrecognised(channel=Channel.TEAMS).prompt
    assert sent.exchange is not None and TENANT in sent.exchange.url


def test_keys_named_on_another_host_are_never_read_and_everything_is_refused(
    world: World, microsoft: Microsoft
) -> None:
    """**A metadata document cannot choose where trust comes from.** Its key set on another
    host is not fetched, so there are no keys, and the activity is refused unanswered.

    Delete this and a tampered document could hand the install an attacker's keys."""
    microsoft.documents[BOT_FRAMEWORK_METADATA_URL] = metadata(jwks_uri="https://example.test/keys")
    with client_for(world, microsoft, None) as c:
        answered = post(c, {})
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert microsoft.reads == [BOT_FRAMEWORK_METADATA_URL]
    assert microsoft.sent == []


def test_a_token_no_published_key_signed_is_refused_and_nothing_is_sent(
    world: World, microsoft: Microsoft
) -> None:
    """Delete this and a forged token could make the bot post on Microsoft's reply host."""
    with client_for(world, microsoft, keys()) as c:
        answered = post(c, {}, signed_with=_OTHER)
    assert answered.status_code == channel_routes._REFUSED_STATUS[RefusedBecause.BAD_SIGNATURE][0]
    assert microsoft.sent == []


def test_the_keys_are_fetched_once_and_served_from_the_cache_after(
    world: World, microsoft: Microsoft
) -> None:
    """Delete this and every activity would fetch Microsoft's documents again."""
    with client_for(world, microsoft, None) as c:
        post(c, {"id": "1"})
        post(c, {"id": "2"})
    assert len(microsoft.reads) == 2
    assert len(microsoft.sent) == 1  # the binding prompt goes once per sender
