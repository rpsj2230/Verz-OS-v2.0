"""The install acceptance checks for the chat and mail channels a vendor connects, one per channel.

Each check posts to the install's own events address, `POST /api/v1/channels/<name>/events`, on
an application whose stores are the check's rolled-back transaction, and reads back what the route
built to send. So what is proved is the route as the install runs it: the wire's verification, the
claim, the binding prompt and `deliver`. What is not proved, and cannot be from inside the install,
is the vendor's half: that the vendor signs what it sends the way its documentation says, and that
it accepts what the install sends it. Each check's sentence says which half it proves, and the
owner's own connection is the proof of the other.

**Email: the relay is the install's own, and the reply is kept rather than sent.** The receiving
script's signature is made here with a secret the check made, for `brain.ops.acceptance_checks`'
reason, and the reply goes through `brain.channels.relay.RelayingTransport` to the relay saved on
Notifications, read from `ops.setting` as a reply reads it, with the password the vault lends for
the send. The transport it is handed keeps the message, notes the host it was built for and
whether a password was lent, and drops the password; nothing is handed to the relay, so no mail
reaches anybody. See `NOTHING_THE_EMAIL_CHECK_SENDS_LEAVES_THE_PROCESS`.

**An install with no relay saved runs the inbound half and says the rest was not run.** A message
signed and marked as passed is still accepted, and a reply to it is still refused with nothing
sent, which is itself the rule `brain.channels.relay.A_RELAY_NOBODY_SET_UP_WAS_NEVER_ASKED`
states; but a relay's host and password were never asked, so the check is recorded not run with
`NO_RELAY_IS_SAVED` rather than passed on half of its sentence.

**Slack: a signing secret and a bot token made by the check, and nothing needed from the install
but its database.** The address check, a forged request and a signed direct message go to the
events route, and the binding prompt it answers with is kept by a transport that answers as Slack
documents a success. What only the owner's workspace proves is that Slack signs and delivers as
documented and accepts the post.

Task ids: M10.5.6, M10.5.1
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check

# The webhook check's in-memory secret, ledger and transport, imported rather than copied, and
# imported first so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks import _HeldLedger, _Kept, _Secret
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 240

#: Why nothing the email check sends reaches a relay, a vault slot or a person.
NOTHING_THE_EMAIL_CHECK_SENDS_LEAVES_THE_PROCESS: Final = (
    "The email channel the check sets up has a secret made in memory and a record in the check's "
    "transaction. Its reply is built for the relay saved on Notifications with the password the "
    "vault lends, and handed to a transport that keeps it and connects to nothing, so no mail "
    "leaves and no vault slot is written."
)

#: The reason the reply half is not run on an install with no relay saved.
NO_RELAY_IS_SAVED: Final = (
    "signed mail was accepted and forged mail refused, but no mail relay is saved on "
    "Notifications, so a reply had nowhere to leave from and its relay was not asked"
)

#: The address the check's messages come from and its record names. `.invalid` never resolves.
_DOMAIN: Final = "acceptance.invalid"


@dataclass
class _KeptMail:
    """`brain.ops.mail.MailTransport` that keeps each message and hands none to a relay."""

    sent: list[Any] = field(default_factory=list)

    def send(self, message: Any) -> Any:
        from brain.connectors.throttle import CallOutcome
        from brain.ops.mail import MailAnswer

        self.sent.append(message)
        return MailAnswer(CallOutcome.OK)


@dataclass
class _Relayed:
    """What the route built a relay for: the host, the port and whether a password was lent."""

    built: list[tuple[str, int, bool]] = field(default_factory=list)
    kept: _KeptMail = field(default_factory=_KeptMail)

    def build(self, settings: Any, password: str | None) -> _KeptMail:
        # The password is looked at for its presence and dropped here, as the relay would drop it.
        self.built.append((settings.host, settings.port, bool(password)))
        del password
        return self.kept


def _mail(sender: str, message_id: str, words: str) -> str:
    built = EmailMessage()
    built["From"] = sender
    built["To"] = f"ask@{_DOMAIN}"
    built["Subject"] = "Acceptance"
    built["Message-ID"] = message_id
    built.set_content(words)
    return built.as_string()


@check(
    leaves=("M10.5.6",),
    sentence=(
        "An email channel set up with a secret the check made accepts signed mail marked as "
        "passed, refuses mail signed with another secret before reading it and mail marked as "
        "failed, and answers the sender through the relay saved on Notifications, built for "
        "that relay's host with the password the vault lends, and kept rather than sent."
    ),
)
async def an_email_is_taken_signed_and_answered_by_the_install_s_relay(
    h: Harness,
) -> None:
    import httpx
    from fastapi import FastAPI

    from brain.channel_routes import router
    from brain.channels.email import ADDRESS, ENVELOPE_AUTHENTICATION, ENVELOPE_MESSAGE
    from brain.channels.webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
    from brain.gate.context import Channel
    from brain.ops.channel_store import StoredChannels
    from brain.ops.mail import settings_from_rows, settings_rows

    async with h.sessions() as session:
        saved = settings_from_rows(await settings_rows(session))
    written_to = f"acceptance-{h.run}-ask@{_DOMAIN}"
    await StoredChannels(h.sessions).save(
        Channel.EMAIL,
        enabled=True,
        tenant={ADDRESS: written_to},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    made, relayed, https = _Secret(secrets.token_hex(32)), _Relayed(), _Kept()
    app = FastAPI()
    app.include_router(router)
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.channel_secrets = made
    state.channel_transport = https
    state.operation_ledger = _HeldLedger()
    state.mail_transport = relayed.build
    sender = f"acceptance-{h.run}@{_DOMAIN}"

    async def post(verdict: str, n: int, signed_with: str) -> Any:
        message_id = f"<acceptance-{h.run}-{n}@{_DOMAIN}>"
        raw = json.dumps(
            {
                ENVELOPE_AUTHENTICATION: verdict,
                ENVELOPE_MESSAGE: _mail(sender, message_id, h.word()),
            }
        ).encode("utf-8")
        stamp = str(int(time.time()))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://acceptance.invalid"
        ) as c:
            return await c.post(
                f"/api/v1/channels/{Channel.EMAIL.value}/events",
                content=raw,
                headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(signed_with, stamp, raw)},
            )

    forged = await post("pass", 1, secrets.token_hex(32))
    if forged.status_code == 200 or relayed.built:
        raise CheckFailedError("mail signed with another secret was accepted")
    failed = await post("fail", 2, made.value)
    if failed.status_code == 200 or relayed.built:
        raise CheckFailedError("mail its receiver marked as failed was accepted")
    accepted = await post("pass", 3, made.value)
    if accepted.status_code != 200 or accepted.json().get("status") != "accepted":
        raise CheckFailedError("signed mail marked as passed was not accepted")
    if https.sent:
        raise CheckFailedError("a reply by mail was sent over HTTPS")
    reply = accepted.json().get("reply")
    if saved is None:
        if reply != "refused" or relayed.built:
            raise CheckFailedError("with no relay saved, a reply was not refused with nothing sent")
        raise CheckNotRunError(NO_RELAY_IS_SAVED)
    if reply != "sent" or len(relayed.built) != 1:
        if saved.username:
            raise CheckFailedError(
                "the relay saved on Notifications names a user and the vault lent no password "
                "for the reply"
            )
        raise CheckFailedError("the reply was not handed to the relay saved on Notifications")
    host, port, lent = relayed.built[0]
    if (host, port) != (saved.host, saved.port):
        raise CheckFailedError("the reply was built for a relay other than the one saved")
    if bool(saved.username) != lent:
        raise CheckFailedError("the reply was built without the password the relay's user needs")
    (kept,) = relayed.kept.sent
    if (kept.to, kept.in_reply_to, kept.reply_to) != (
        sender,
        f"<acceptance-{h.run}-3@{_DOMAIN}>",
        written_to,
    ):
        raise CheckFailedError(
            "the reply was not addressed to the sender alone, threaded under the question"
        )


# ------------------------------------------------------------------------------ slack
@dataclass
class _SlackKept(_Kept):
    """The webhook check's transport, answering each send as Slack documents a success."""

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        return VendorAnswer(status=200, body=b'{"ok":true}')


@check(
    leaves=("M10.5.1",),
    sentence=(
        "A Slack channel set up with a signing secret and a bot token the check made answers "
        "Slack's address check with its challenge, refuses a request signed with another secret "
        "before reading it, and answers a signed direct message from somebody bound to nobody "
        "with the binding prompt, built for Slack's own host on the bot's token and kept."
    ),
)
async def a_slack_message_is_taken_signed_and_answered_on_the_bot_token(h: Harness) -> None:
    import httpx
    from fastapi import FastAPI

    from brain.channel_routes import router
    from brain.channels.adapter import BOT_ID
    from brain.channels.slack import (
        BOT_TOKEN,
        SIGNATURE_HEADER,
        SIGNING_SECRET,
        SLACK_API_URL,
        TIMESTAMP_HEADER,
        sign,
    )
    from brain.gate.context import Channel
    from brain.gate.ingress import Unrecognised
    from brain.ops.channel_store import StoredChannels

    signing, token = secrets.token_hex(32), f"xoxb-{secrets.token_hex(16)}"
    await StoredChannels(h.sessions).save(
        Channel.SLACK,
        enabled=True,
        tenant={BOT_ID: f"U0BOT{h.run[:8].upper()}"},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    kept = _SlackKept()
    app = FastAPI()
    app.include_router(router)
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.channel_secrets = _Secret(json.dumps({SIGNING_SECRET: signing, BOT_TOKEN: token}))
    state.channel_transport = kept
    state.operation_ledger = _HeldLedger()
    sender = f"U0ACC{h.run[:8].upper()}"

    async def post(payload: dict[str, Any], signed_with: str) -> Any:
        raw = json.dumps(payload).encode("utf-8")
        stamp = str(int(time.time()))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://acceptance.invalid"
        ) as c:
            return await c.post(
                f"/api/v1/channels/{Channel.SLACK.value}/events",
                content=raw,
                headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(signed_with, stamp, raw)},
            )

    checked = await post({"type": "url_verification", "challenge": h.run}, signing)
    if checked.status_code != 200 or checked.json() != {"challenge": h.run}:
        raise CheckFailedError("Slack's address check was not answered with its own challenge")
    message = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "channel": f"D0ACC{h.run[:8].upper()}",
            "channel_type": "im",
            "user": sender,
            "text": h.word(),
            "ts": f"{int(time.time())}.000100",
        },
    }
    forged = await post(message, secrets.token_hex(32))
    if forged.status_code == 200 or kept.sent:
        raise CheckFailedError("a request signed with another secret was accepted")
    accepted = await post(message, signing)
    if accepted.status_code != 200 or accepted.json().get("status") != "accepted":
        raise CheckFailedError("a signed direct message was not accepted")
    if len(kept.sent) != 1:
        raise CheckFailedError(
            "a direct message from somebody bound to nobody was not answered once"
        )
    (built,) = kept.sent
    if built.url != f"{SLACK_API_URL}/chat.postMessage":
        raise CheckFailedError("the answer was not built for Slack's own host")
    if built.headers.get("Authorization") != f"Bearer {token}":
        raise CheckFailedError("the answer was not built on the bot's token")
    body = json.loads(built.body)
    if body != {"channel": sender, "text": Unrecognised(channel=Channel.SLACK).prompt}:
        raise CheckFailedError("the answer was not the binding prompt, to the sender alone")


# ------------------------------------------------------------------------ email, a mailbox
#: The reason the mailbox check's reply half is not run on an install with no relay saved.
NO_RELAY_IS_SAVED_FOR_THE_MAILBOX: Final = (
    "mail was read from the stand-in mailbox and marked, but no mail relay is saved on "
    "Notifications, so its answer had nowhere to leave from and its relay was not asked"
)


@dataclass
class _StandInMailbox:
    """`brain.channels.mailbox.MailboxReader` over messages the check made, in memory."""

    messages: list[tuple[str, bytes]]
    marked: list[str] = field(default_factory=list)
    closed: bool = False

    def unseen(self, most: int) -> list[tuple[str, bytes]]:
        return [one for one in self.messages if one[0] not in self.marked][:most]

    def mark_handled(self, ids: Any) -> None:
        self.marked.extend(ids)

    def close(self) -> None:
        self.closed = True


@check(
    leaves=("M10.5.6",),
    sentence=(
        "An email channel reading a mailbox, with a stand-in mailbox the check filled, reads "
        "its unread mail, answers a colleague its provider vouched for through the relay saved "
        "on Notifications with how to link their address, answers nobody else, and marks "
        "every message it read, deleting none."
    ),
)
async def mail_in_the_mailbox_is_read_answered_and_marked(h: Harness) -> None:
    from datetime import UTC, datetime

    from fastapi import FastAPI

    from brain.channel_routes import router
    from brain.channels.email import (
        ADDRESS,
        DOMAINS,
        IMAP_HOST,
        IMAP_PORT,
        IMAP_USER,
        RECEIVER,
    )
    from brain.gate.context import Channel
    from brain.gate.ingress import Unrecognised
    from brain.mailbox_read import read_mailbox_once
    from brain.ops.channel_store import StoredChannels
    from brain.ops.mail import settings_from_rows, settings_rows

    async with h.sessions() as session:
        saved = settings_from_rows(await settings_rows(session))
    box_user = f"ask-{h.run}@{_DOMAIN}"
    receiver = f"mx.{_DOMAIN}"
    await StoredChannels(h.sessions).save(
        Channel.EMAIL,
        enabled=True,
        tenant={
            ADDRESS: box_user,
            IMAP_HOST: f"imap.{_DOMAIN}",
            IMAP_PORT: "993",
            IMAP_USER: box_user,
            RECEIVER: receiver,
            DOMAINS: _DOMAIN,
        },
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    password = secrets.token_hex(16)
    colleague, stranger = f"acceptance-{h.run}@{_DOMAIN}", f"acceptance-{h.run}@elsewhere.invalid"

    def stamped(sender: str, n: int) -> bytes:
        message = EmailMessage()
        message["Authentication-Results"] = (
            f"{receiver}; dmarc=pass header.from={sender.rpartition('@')[2]}"
        )
        message["From"] = sender
        message["To"] = box_user
        message["Subject"] = "Acceptance"
        message["Message-ID"] = f"<acceptance-{h.run}-{n}@{_DOMAIN}>"
        message.set_content(h.word())
        return message.as_bytes()

    box = _StandInMailbox(messages=[("1", stamped(colleague, 1)), ("2", stamped(stranger, 2))])
    opened: list[tuple[str, str, bool]] = []

    def opener(settings: Any, given: str) -> _StandInMailbox:
        opened.append((settings.host, settings.user, given == password))
        return box

    relayed, https = _Relayed(), _Kept()
    app = FastAPI()
    app.include_router(router)
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.channel_secrets = _Secret(password)
    state.channel_transport = https
    state.operation_ledger = _HeldLedger()
    state.mail_transport = relayed.build

    ran = await read_mailbox_once(app, now=datetime.now(UTC), opener=opener)
    if opened != [(f"imap.{_DOMAIN}", box_user, True)]:
        raise CheckFailedError("the mailbox was not opened with the record's settings and secret")
    if ran.read != 2 or sorted(box.marked) != ["1", "2"] or not box.closed:
        raise CheckFailedError("the mailbox's unread mail was not read, marked and closed")
    if https.sent:
        raise CheckFailedError("an answer to mail was sent over HTTPS")
    if saved is None:
        if relayed.built:
            raise CheckFailedError("with no relay saved, an answer was handed to a relay")
        raise CheckNotRunError(NO_RELAY_IS_SAVED_FOR_THE_MAILBOX)
    if len(relayed.kept.sent) != 1:
        raise CheckFailedError("not exactly the colleague's message was answered")
    (kept,) = relayed.kept.sent
    if (kept.to, kept.body.rstrip()) != (colleague, Unrecognised(channel=Channel.EMAIL).prompt):
        raise CheckFailedError("the colleague was not told how to link their address")


# ------------------------------------------------------------------------------ teams
@dataclass
class _TeamsKept(_Kept):
    """The webhook check's transport, answering each send as the Bot Connector documents."""

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        return VendorAnswer(status=201, body=b'{"id":"1"}')


def _teams_token(private: Any, *, kid: str, app_id: str, service: str) -> str:
    """A compact RS256 token shaped as the Bot Framework mints one, signed by `private`."""
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    from brain.channels.teams import BOT_FRAMEWORK_ISSUER

    def b64(blob: bytes) -> str:
        return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")

    now = int(time.time())
    head = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    claims = {
        "iss": BOT_FRAMEWORK_ISSUER,
        "aud": app_id,
        "serviceurl": service,
        "nbf": now - 60,
        "exp": now + 1800,
    }
    signing = f"{b64(json.dumps(head).encode())}.{b64(json.dumps(claims).encode())}"
    signature = private.sign(signing.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing}.{b64(signature)}"


@check(
    leaves=("M10.5.2",),
    sentence=(
        "A Teams channel set up with ids and a key the check made accepts a personal message "
        "whose token that key signed for the bot and tenant, refuses one signed by another key "
        "and one from another tenant, and answers the sender in the chat through Microsoft's "
        "reply host on a token exchanged at the tenant's own login, kept rather than sent."
    ),
)
async def a_teams_message_is_taken_signed_and_answered_in_its_chat(h: Harness) -> None:
    import uuid
    from datetime import UTC, datetime

    import httpx
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI

    from brain.channel_routes import router
    from brain.channels.adapter import BOT_ID
    from brain.channels.teams import BOT_FRAMEWORK_ISSUER, MICROSOFT_LOGIN_URL, TENANT_ID
    from brain.gate.context import Channel
    from brain.gate.ingress import Unrecognised
    from brain.identity.oidc import KeySet, SigningKey
    from brain.ops.channel_store import StoredChannels

    app_id, tenant_id, other_tenant = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    service, chat, kid = "https://smba.trafficmanager.net/emea/", f"a:{h.run}", f"k-{h.run}"
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    await StoredChannels(h.sessions).save(
        Channel.TEAMS,
        enabled=True,
        tenant={BOT_ID: app_id, TENANT_ID: tenant_id},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    kept = _TeamsKept()
    app = FastAPI()
    app.include_router(router)
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.channel_secrets = _Secret(secrets.token_hex(24))
    state.channel_transport = kept
    state.operation_ledger = _HeldLedger()
    state.channel_keys = KeySet(
        issuer=BOT_FRAMEWORK_ISSUER,
        keys=(SigningKey(kid=kid, algorithm="RS256", material=pem, use="sig"),),
        fetched_at=datetime.now(UTC),
    )
    person = str(uuid.uuid4())

    async def post(n: int, signer: Any, tenant: str) -> Any:
        activity = {
            "type": "message",
            "id": f"{h.run}-{n}",
            "channelId": "msteams",
            "serviceUrl": service,
            "timestamp": datetime.now(UTC).isoformat(),
            "from": {"id": f"29:{h.run}", "aadObjectId": person},
            "conversation": {"id": chat, "conversationType": "personal"},
            "text": h.word(),
            "channelData": {"tenant": {"id": tenant}},
        }
        bearer = _teams_token(signer, kid=kid, app_id=app_id, service=service)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://acceptance.invalid"
        ) as c:
            return await c.post(
                f"/api/v1/channels/{Channel.TEAMS.value}/events",
                content=json.dumps(activity).encode("utf-8"),
                headers={"Authorization": f"Bearer {bearer}"},
            )

    forged = await post(1, stranger, tenant_id)
    if forged.status_code == 200 or kept.sent:
        raise CheckFailedError("a token no published key signed was accepted")
    elsewhere = await post(2, private, other_tenant)
    if elsewhere.status_code == 200 or kept.sent:
        raise CheckFailedError("an activity from another tenant was accepted")
    accepted = await post(3, private, tenant_id)
    if accepted.status_code != 200 or accepted.json().get("status") != "accepted":
        raise CheckFailedError("a personal message Microsoft signed for this bot was not accepted")
    if len(kept.sent) != 1:
        raise CheckFailedError("a message from somebody bound to nobody was not answered once")
    (built,) = kept.sent
    if not built.url.startswith(f"{service}v3/conversations/"):
        raise CheckFailedError("the answer was not built for Microsoft's reply host")
    exchange = built.exchange
    if exchange is None or exchange.url != f"{MICROSOFT_LOGIN_URL}/{tenant_id}/oauth2/v2.0/token":
        raise CheckFailedError("the answer was not authorised at the tenant's own login")
    if json.loads(built.body).get("text") != Unrecognised(channel=Channel.TEAMS).prompt:
        raise CheckFailedError("the answer was not the binding prompt")
