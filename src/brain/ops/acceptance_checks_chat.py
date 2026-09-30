"""The install acceptance checks for the Lark chat channel: a signed event in, what Lark was asked.

Each check posts events sealed and signed as Lark seals them to the install's own events route,
`POST /api/v1/channels/lark/events`, on an application whose every store is the check's rolled-back
transaction, and reads back what the route asked Lark to send. So what is proved is the route as
the install would run it: the wire's verification, the claim, `brain.channels.inbound.reply_for`'s
mention rule, `brain.chat_answer.ChatAnswerer`'s direct and group plans, and `deliver`.

**The application is the channel router over the check's transaction, and not `create_app`.** The
lifespan opens a pool of its own, a cache and a vault, and anything written through them would
outlive the check. So the check builds a bare application with `brain.channel_routes.router` and
sets on its state the same objects the lifespan would, each over `harness.sessions`: the gate
`brain.app.wirings_for` builds, with no entitlement cache, the registry from `build_registry`, the
install's own answer rules. The route's own wiring functions then choose every store, which is
how the check learns, for instance, whether this install reads chat bindings at all. Rejected:
calling `ChatAnswerer.answer` directly, which would skip the signature, the claim, the mention rule
and the send, and prove a function rather than an address.

**What stays in memory, and why, is the webhook check's list.** The channel secret is made by the
check and held in memory, because a check that wrote the vault would replace the install's own
Lark slot. Lark is a transport that keeps every request and sends nothing: a send is answered with
Lark's documented success and a members read with the room the check set, so no real chat, person
or tenant is ever reached. The operation ledger is held in memory for
`brain.ops.acceptance_checks`' reason. See `NOTHING_THE_CHECK_SENDS_LEAVES_THE_PROCESS`.

**The answer is a table the check uploads into acceptance_a, and no model is called.** An uploaded
table is answered by the fast lane, through the same `answered_for` every Ask runs, so each
person's answer is exact: one column open to the table's readers, one restricted to a grant of its
own. Rejected: a document, which only the model step answers, so every ask would cost a call per
person per room and two asks of one question could word the answer differently, which is the one
thing the web comparison below must not depend on. See `AN_UPLOADED_TABLE_ANSWERS_WITHOUT_A_MODEL`.
**So M2.3.1's chat half is shown over a department's rows and not over its document:** the
documents check shows a document found at department reach, and a model's words about one are the
one answer no check here asks for.

**A bound person is a row of `auth.principal_identity`, and binding is CH2's.** The check writes one
chat binding per person in its transaction, where CH2's store keeps them, and asks the route's own
`bindings_of` whether this install reads them. Until CH2 is deployed it reads none, and every
check that needs a bound person is recorded not run with `BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED`
rather than failed or passed on a binding the check invented.

**The web answer is the function the web route calls.** `/api/v1/answer` needs a sign-in, which the
run never makes, and its body is `brain.api_routes.answered_for`. So the check calls that function
for the same person at the reach the web admits a signed-in person, and compares its text with
what the chat was sent. See `A_DIRECT_REPLY_IS_THE_WEB_ANSWER_BECAUSE_BOTH_CALL_ONE_FUNCTION`.

Task ids: M10.2.2, M10.2.5, M10.2.6, M10.4.1, M10.4.2, M10.4.3, M10.4.4, M38.2.2.3, M2.3.1
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check

# The webhook check's in-memory secret and ledger, imported rather than copied, and imported first
# so the suite's own checks are registered ahead of these.
from brain.ops.acceptance_checks import _HeldLedger, _in, _Secret
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.core.scope import Scope

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 30

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why nothing the check posts or sends reaches Lark, a vault or a person.
NOTHING_THE_CHECK_SENDS_LEAVES_THE_PROCESS: Final = (
    "The Lark app the check sets up has a secret made in memory, a record in the check's "
    "transaction and a transport that keeps each request and answers it as Lark documents, so "
    "every event, members read and reply stays inside the worker. The vault slot the install's "
    "real Lark app uses is never written, its record changes only inside the check's "
    "transaction, and no real chat hears anything."
)

#: Why the check's answers come from an uploaded table.
AN_UPLOADED_TABLE_ANSWERS_WITHOUT_A_MODEL: Final = (
    "A table uploaded into acceptance_a in the check's transaction is answered by the fast lane "
    "at each person's reach, one column open to its readers and one held back for a grant of "
    "its own, so every answer is exact and repeatable and no provider is called."
)

#: Why a chat reply and the web's answer are compared, and how.
A_DIRECT_REPLY_IS_THE_WEB_ANSWER_BECAUSE_BOTH_CALL_ONE_FUNCTION: Final = (
    "The web's Ask runs brain.api_routes.answered_for for the signed-in person, and a bound "
    "person's direct message is answered by the same function at the reach their grants give "
    "them in chat. The check asks both for one person and one question and holds the words, the "
    "sources and the refusals equal, all but the instant each source was read at."
)

#: The reason a check needing a bound person is not run on an install without CH2.
BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED: Final = (
    "this install does not read chat bindings yet, so nobody can be asked as a bound person"
)

# ------------------------------------------------------------------------ the figures
#: The platform the check's app is recorded on. Only the host a send would go to depends on it,
#: and nothing is sent.
PLATFORM: Final = "larksuite.com"

#: What Lark answers a send it accepted, as `chyroc/lark`'s `api_message_send.go` records it.
SENT_ENVELOPE: Final = {"code": 0, "msg": "success", "data": {"message_id": "om_acceptance"}}

#: A source's read instant, which differs between two asks of one question by design: a sentence's
#: ", as of" tail, or the "read" or "updated" words `brain.gate.streaming.citation_text` puts
#: inside a citation's brackets beside how fresh it is.
_READ_AT: Final = re.compile(r", as of [^\n]+|, (?:read|updated) [^)\n]*(?=\))")


# --------------------------------------------------------------------- Lark in memory
@dataclass
class _Lark:
    """`ChannelTransport` answering as Lark: each request kept, nothing sent anywhere.

    A send is answered with `SENT_ENVELOPE`. A members read is answered from `rooms`, a list of
    member lists per chat read in turn, so a check can change the room between the read a floor
    is made from and the read that checks it before sending; a chat with no room fails to read.
    """

    rooms: dict[str, list[list[str]]] = field(default_factory=dict)
    sent: list[Any] = field(default_factory=list)
    reads: list[Any] = field(default_factory=list)

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        return VendorAnswer(status=200, body=json.dumps(SENT_ENVELOPE).encode())

    def read(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        chat = urlsplit(request.url).path.split("/")[-2]
        turns = self.rooms.get(chat, [])
        asked = sum(1 for one in self.reads if chat in one.url)
        self.reads.append(request)
        if not turns:
            return VendorAnswer(connection_failed=True)
        members = turns[min(asked, len(turns) - 1)]
        return VendorAnswer(status=200, body=json.dumps(_members_page(members)).encode())

    def messages(self) -> list[tuple[str, str, str]]:
        """Every message the route asked Lark to send, as (kind, where, text), in order."""
        found: list[tuple[str, str, str]] = []
        for request in self.sent:
            body = json.loads(request.body)
            if request.url.endswith("/ephemeral/v1/send"):
                text = body["card"]["elements"][0]["text"]["content"]
                found.append(("aside", f"{body['chat_id']}:{body['open_id']}", text))
            else:
                kind = parse_qs(urlsplit(request.url).query)["receive_id_type"][0]
                found.append((kind, body["receive_id"], json.loads(body["content"])["text"]))
        return found


def _members_page(members: Sequence[str]) -> dict[str, Any]:
    """One page of a chat's members, as `chyroc/lark`'s `api_chat_member_get_list.go` records
    `GET /open-apis/im/v1/chats/:chat_id/members` answering."""
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "items": [
                {"member_id_type": "open_id", "member_id": one, "name": "N", "tenant_key": "t"}
                for one in members
            ],
            "page_token": "",
            "has_more": False,
            "member_total": len(members),
        },
    }


# ---------------------------------------------------------------------- Lark's events
def open_id() -> str:
    """An open id no Lark tenant issued: Lark's `ou_` and thirty-two hex characters."""
    return f"ou_{secrets.token_hex(16)}"


def chat_id() -> str:
    """A chat id no Lark tenant issued: Lark's `oc_` and thirty-two hex characters."""
    return f"oc_{secrets.token_hex(16)}"


def lark_message(
    *,
    app_id: str,
    token: str,
    sender: str,
    text: str,
    chat: str,
    group: bool,
    mentions: Sequence[str] = (),
) -> dict[str, Any]:
    """An `im.message.receive_v1` event, schema 2.0, as Lark's server SDK
    (`larksuite/oapi-sdk-python`, `lark_oapi/event/dispatcher_handler.py`) parses it."""
    created = str(int(time.time()) * 1000)
    ident = f"om_{secrets.token_hex(12)}"
    return {
        "schema": "2.0",
        "header": {
            "event_id": f"ev_{ident}",
            "event_type": "im.message.receive_v1",
            "create_time": created,
            "token": token,
            "app_id": app_id,
            "tenant_key": "acceptance",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": sender, "union_id": "", "user_id": ""},
                "sender_type": "user",
                "tenant_key": "acceptance",
            },
            "message": {
                "message_id": ident,
                "root_id": "",
                "parent_id": "",
                "create_time": created,
                "chat_id": chat,
                "chat_type": "group" if group else "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}),
                "mentions": [
                    {
                        "key": f"@_user_{n}",
                        "id": {"open_id": one, "union_id": "", "user_id": ""},
                        "name": "Brain",
                    }
                    for n, one in enumerate(mentions, start=1)
                ],
            },
        },
    }


def sealed(event: Mapping[str, Any], encrypt_key: str) -> tuple[bytes, dict[str, str]]:
    """An event as Lark posts it: encrypted into `{"encrypt": ...}`, with its three headers.

    Written from Lark's algorithm (`lark_oapi/core/utils/decryptor.py` and `_verify_sign`) and
    not from `brain.channels.lark`, so a wire that opened or verified wrongly is refused here as
    it would be by Lark: AES-256-CBC under sha256 of the key, a random IV first, PKCS#7, base64,
    and sha256 over the time, the nonce, the key and the exact bytes.
    """
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    vector = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(json.dumps(event).encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(vector)).encryptor()
    ciphertext = vector + encryptor.update(padded) + encryptor.finalize()
    raw = json.dumps({"encrypt": base64.b64encode(ciphertext).decode()}).encode()
    stamp, nonce = str(int(time.time())), secrets.token_hex(8)
    material = (stamp + nonce + encrypt_key).encode("utf-8") + raw
    return raw, {
        "content-type": "application/json",
        "x-lark-request-timestamp": stamp,
        "x-lark-request-nonce": nonce,
        "x-lark-signature": hashlib.sha256(material).hexdigest(),
    }


# ------------------------------------------------------------------- the check's app
@dataclass
class _LarkApp:
    """One Lark app for the length of a check: its ids, its secret, Lark, and the address."""

    h: Harness
    app: FastAPI
    lark: _Lark
    app_id: str
    bot: str
    encrypt_key: str = field(repr=False)
    token: str = field(repr=False)

    async def post(self, sender: str, text: str, *, chat: str, group: bool, to_bot: bool) -> int:
        """One message through the events address; the status the route answered Lark with."""
        import httpx

        from brain.ops.lark_connect import LARK_EVENTS_PATH

        mentions = [self.bot] if to_bot else [open_id()]
        event = lark_message(
            app_id=self.app_id,
            token=self.token,
            sender=sender,
            text=f"@_user_1 {text}" if group else text,
            chat=chat,
            group=group,
            mentions=mentions if group else (),
        )
        raw, headers = sealed(event, self.encrypt_key)
        transport = httpx.ASGITransport(app=self.app)
        # The route answers Lark before it replies; the transport waits for the reply as well.
        # The address is the one Connect Lark tells the owner to paste into Lark.
        async with httpx.AsyncClient(
            transport=transport, base_url="https://acceptance.invalid"
        ) as c:
            answered = await c.post(LARK_EVENTS_PATH, content=raw, headers=headers)
        return answered.status_code

    def request(self) -> Request:
        """A request on this application, for the route's own wiring functions to be asked."""
        from starlette.requests import Request

        return Request({"type": "http", "app": self.app, "headers": [], "method": "POST"})


class _NoKeys:
    """The realm's keys, never fetched: the events route takes no caller and signs nobody in."""

    def __call__(self, url: str) -> bytes:
        del url
        raise CheckFailedError("the chat channel asked for the realm's keys, which it never needs")


async def lark_app(h: Harness) -> _LarkApp:
    """The events route over the check's transaction, with a Lark app set up in memory."""
    from fastapi import FastAPI

    from brain.api_routes import GateWiring
    from brain.cache import NoEntitlementCache, PostgresVersionSource
    from brain.channel_routes import router
    from brain.channels.adapter import BOT_ID
    from brain.channels.lark import APP_ID_FIELD, PLATFORM_FIELD, LarkSecret
    from brain.gate.context import Channel
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.rule_store import load_rules
    from brain.identity.keycloak_tokens import keycloak_authority
    from brain.identity.principal_directory import StoredDirectory
    from brain.identity.roles import IdentityError
    from brain.install import InstallError
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.channel_store import StoredChannels
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    # `brain.app.wirings_for`'s gate, built here because nothing under src imports the
    # application, and with no entitlement cache, which would outlive the transaction.
    try:
        authority = keycloak_authority(
            directory=StoredDirectory(h.sessions), get=_NoKeys(), clock=lambda: datetime.now(UTC)
        )
    except (InstallError, IdentityError) as exc:
        raise CheckNotRunError(
            "this install cannot check a sign-in, so it has no gate to answer"
        ) from exc
    gate = GateWiring(
        authority=authority,
        versions=PostgresVersionSource(h.sessions),
        store=StoredEntitlements(h.sessions),
        cache=NoEntitlementCache(),
    )
    kept = LarkSecret(
        app_secret=secrets.token_hex(16),
        encrypt_key=secrets.token_hex(16),
        verification_token=secrets.token_hex(16),
    )
    made = _LarkApp(
        h=h,
        app=FastAPI(),
        lark=_Lark(),
        app_id=f"cli_{secrets.token_hex(8)}",
        bot=open_id(),
        encrypt_key=kept.encrypt_key,
        token=kept.verification_token,
    )
    await StoredChannels(h.sessions).save(
        Channel.LARK,
        enabled=True,
        tenant={APP_ID_FIELD: made.app_id, PLATFORM_FIELD: PLATFORM, BOT_ID: made.bot},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    try:
        rules = await load_rules(h.sessions)
    except Exception:
        # The lifespan's choice for a rule table that cannot be read: an empty rule set.
        rules = ()
    state = made.app.state
    made.app.include_router(router)
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.gate = gate
    state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    state.fast_path_rules = rules
    state.trace_sink = CountingTraceSink()
    state.channel_secrets = _Secret(kept.kept())
    state.channel_transport = made.lark
    state.operation_ledger = _HeldLedger()
    return made


# ---------------------------------------------------------------------- the people
async def bound(chat: _LarkApp, people: Mapping[str, str]) -> None:
    """Each principal bound to their open id where CH2 keeps a binding, or the check not run.

    Asked of the route's own `bindings_of`, so the answer is this install's: a process that reads
    no binding answers `NoBindingsYet`, and one that reads them finds each row written here.
    """
    from brain.channel_routes import bindings_of
    from brain.channels.inbound import NoBindingsYet
    from brain.gate.context import Channel
    from brain.gate.ingress import identity_hash
    from brain.tables.identity import PrincipalIdentityRow

    reader = bindings_of(chat.request())
    if isinstance(reader, NoBindingsYet):
        raise CheckNotRunError(BINDING_A_CHAT_ACCOUNT_IS_NOT_DEPLOYED)
    h = chat.h
    for principal, identity in people.items():
        await h.execute(
            *h.attributed(),
            insert(PrincipalIdentityRow).values(
                channel=Channel.LARK.value,
                identity_hash=identity_hash(Channel.LARK, identity),
                principal_id=principal,
                bound_at=h.now,
            ),
        )
    for principal, identity in people.items():
        found = await reader.binding_for(Channel.LARK, identity_hash(Channel.LARK, identity))
        if found is None or found.principal_id != principal:
            raise CheckFailedError("a chat binding kept for a person was not read back as theirs")


@dataclass(frozen=True)
class _Table:
    """A table uploaded into acceptance_a for one check: one row, one open and one held column.

    The two columns are named for the run, so no rule the install holds asks about either, and
    the row's key and values are words nothing else holds.
    """

    entity: str
    key: str
    open_column: str
    held_column: str
    seen: str
    held: str

    def asking(self, column: str, key: str = "") -> str:
        """The question the table answers about one column of a row, in the first of
        `brain.knowledge.classified_rows.QUESTION_SHAPES`."""
        from brain.knowledge.classified_rows import label_of

        return f"what is the {label_of(column)} of {key or self.key}"

    def reads(self, department: str, *, held: bool) -> tuple[tuple[str, Scope], ...]:
        """The grants a reader of the table holds in `department`, the held column's or not."""
        own = (f"read:{self.entity}.{self.held_column}",) if held else ()
        return _in(department, f"read:{self.entity}", *own)


async def uploaded(h: Harness) -> _Table:
    """The table, uploaded through the Classification screen's own store in the transaction."""
    from brain.knowledge.classified_rows import StoredTable
    from brain.knowledge.columns import ColumnAccess, TableClassification, marked
    from brain.ops.classification_store import SqlClassifiedTables, Writer

    made = _Table(
        entity=f"acceptance_{h.run}",
        key=h.word(),
        open_column=f"shade{h.run}",
        held_column=f"band{h.run}",
        seen=h.word(),
        held=h.word(),
    )
    marks = (
        ("item", ColumnAccess.OPEN),
        ("department", ColumnAccess.OPEN),
        (made.open_column, ColumnAccess.OPEN),
        (made.held_column, ColumnAccess.RESTRICTED),
    )
    classification = TableClassification(
        entity=made.entity,
        rules=tuple(marked(made.entity, column, access) for column, access in marks),
    )
    table = StoredTable(
        classification=classification, title=made.entity, key_column="item", version=1
    )
    row = {
        "item": made.key,
        "department": A,
        made.open_column: made.seen,
        made.held_column: made.held,
    }
    writer = Writer(actor_id=h.actor, ent_hash="0" * 32, trace_id=h.trace_id)
    await SqlClassifiedTables(h.sessions).upload(table, [row], writer=writer)
    return made


def undated(text: str) -> str:
    """A reply without the instant each source was read at."""
    return _READ_AT.sub("", text)


@dataclass(frozen=True)
class _Heard:
    """What the web's Ask streamed a person: the prose, each source, or the failure alone."""

    prose: str
    sources: tuple[str, ...]
    failed: str

    def is_what(self, reply: str) -> bool:
        """Whether a chat reply says this: the failure, or the prose followed by exactly these
        sources, each source's read instant aside."""
        if self.failed:
            return reply == self.failed
        listed = sorted(line[2:] for line in reply.splitlines() if line.startswith("- "))
        return reply.startswith(self.prose) and listed == sorted(self.sources)


def heard(frames: Sequence[str]) -> _Heard:
    """The web's frames read by the event-stream format's own rules: a line per field, a value's
    lines joined by one newline. Read here rather than by `brain.chat_answer.chat_text`, so a chat
    that rendered the frames wrongly is not held equal to the same wrong rendering. A citation's
    fields become the one sentence a text channel shows for them, `citation_text`'s, which is a
    function of that frame alone."""
    from brain.gate.streaming import Event, citation_text

    prose: list[str] = []
    sources: list[str] = []
    failed = ""
    for frame in frames:
        fields: dict[str, list[str]] = {}
        for line in frame.splitlines():
            key, _, value = line.partition(":")
            fields.setdefault(key, []).append(value.removeprefix(" "))
        name, data = "".join(fields.get("event", [])), "\n".join(fields.get("data", []))
        if name == Event.TEXT.value:
            prose.append(data)
        elif name == Event.CITATION.value:
            sources.append(undated(citation_text(data)))
        elif name == Event.ERROR.value:
            failed = data
    return _Heard(prose="".join(prose).strip(), sources=tuple(sources), failed=failed)


async def web_answer(chat: _LarkApp, principal_id: str, question: str) -> _Heard:
    """What the web's Ask streams this person for this question. See
    `A_DIRECT_REPLY_IS_THE_WEB_ANSWER_BECAUSE_BOTH_CALL_ONE_FUNCTION`."""
    from brain.api_routes import Answering, Question, answered_for
    from brain.gate.admission import Assurance, admit
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace
    from brain.identity.principal_store import StoredPrincipals

    h = chat.h
    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    now = datetime.now(UTC)
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    outcome = await answered_for(
        chat.request(),
        open_trace(f"{h.trace_id}-web", now, Channel.CONSOLE),
        Answering(principal=person, reach=reach, channel=Channel.CONSOLE, now=now),
        Question(question=question),
    )
    if not isinstance(outcome, Answered):
        raise CheckFailedError("the web's answer was refused by a window the check never uses")
    return heard(outcome.frames)


# ------------------------------------------------------------------ 5. mentions
@check(
    leaves=("M10.2.2", "M10.2.6"),
    sentence=(
        "Signed Lark events posted to the install's events address: a group message naming "
        "somebody else, or typing the bot's name without mentioning it, is left alone, and one "
        "mentioning the bot is answered, to the sender's own chat; a direct message needs no "
        "mention; and a message sealed under another key is refused."
    ),
)
async def a_lark_group_message_is_answered_only_when_it_names_the_bot(h: Harness) -> None:
    from brain.gate.ingress import UNRECOGNISED_PROMPT

    chat = await lark_app(h)
    stranger, group = open_id(), chat_id()
    chat.lark.rooms[group] = [[stranger]]
    for text, to_bot in (("what is on today", False), ("@Brain what is on today", False)):
        if await chat.post(stranger, text, chat=group, group=True, to_bot=to_bot) != 200:
            raise CheckFailedError("a signed group message was not accepted by the events address")
    if chat.lark.sent or chat.lark.reads:
        raise CheckFailedError("a group message that did not mention the bot was answered")
    await chat.post(stranger, "what is on today", chat=group, group=True, to_bot=True)
    if chat.lark.messages() != [("open_id", stranger, UNRECOGNISED_PROMPT)]:
        raise CheckFailedError(
            "a group message mentioning the bot was not answered in the sender's own chat alone"
        )
    direct = chat_id()
    other = open_id()
    await chat.post(other, "what is on today", chat=direct, group=False, to_bot=False)
    if chat.lark.messages()[1:] != [("open_id", other, UNRECOGNISED_PROMPT)]:
        raise CheckFailedError("a direct message was not answered without mentioning the bot")
    forged = replace(chat, encrypt_key=secrets.token_hex(16))
    if await forged.post(other, "what is on today", chat=direct, group=False, to_bot=False) == 200:
        raise CheckFailedError("an event sealed under another key was accepted")
    if len(chat.lark.sent) != 2 or chat.lark.reads:
        raise CheckFailedError("answering a sender bound to nobody read or sent more than it said")


# ---------------------------------------------------------------- 6. direct messages
@check(
    leaves=("M38.2.2.3", "M2.3.1"),
    sentence=(
        "Bound in Lark to reserved people, a member of acceptance_a holding a restricted column "
        "and one who does not each ask about a row of a table uploaded into acceptance_a in a "
        "direct message, and each is sent exactly what the web's Ask answers them; the second, "
        "and a member of acceptance_b, are answered as if the row did not exist."
    ),
)
async def a_person_bound_in_lark_is_given_their_web_answer_directly(h: Harness) -> None:
    await h.found_departments()
    chat = await lark_app(h)
    table = await uploaded(h)
    wide, narrow = h.principal(A, "wide"), h.principal(A, "narrow")
    elsewhere = h.principal(B, "user")
    await h.person(wide, department=A, grants=table.reads(A, held=True))
    await h.person(narrow, department=A, grants=table.reads(A, held=False))
    await h.person(elsewhere, department=B, grants=table.reads(B, held=True))
    ids = {wide: open_id(), narrow: open_id(), elsewhere: open_id()}
    await bound(chat, ids)
    question = table.asking(table.held_column)
    replies: dict[str, str] = {}
    for principal, identity in ids.items():
        direct = chat_id()
        before = len(chat.lark.sent)
        await chat.post(identity, question, chat=direct, group=False, to_bot=False)
        sent = chat.lark.messages()[before:]
        if [(kind, where) for kind, where, _ in sent] != [("chat_id", direct)]:
            raise CheckFailedError("a bound person's direct message was not answered in its chat")
        replies[principal] = undated(sent[0][2])
        if not (await web_answer(chat, principal, question)).is_what(replies[principal]):
            raise CheckFailedError("a direct reply in Lark differed from the web's answer")
    if table.held not in replies[wide]:
        raise CheckFailedError("a member holding a column was not answered it in Lark")
    missing = table.asking(table.held_column, h.word())
    if not (await web_answer(chat, narrow, missing)).is_what(replies[narrow]):
        raise CheckFailedError("a column the asker may not read was answered unlike a missing row")
    if not (await web_answer(chat, elsewhere, missing)).is_what(replies[elsewhere]):
        raise CheckFailedError("a member of another department could tell the row exists")


# ------------------------------------------------------------------------ 7. rooms
@check(
    leaves=("M10.4.1", "M10.4.2", "M10.2.5", "M10.4.3", "M10.4.4"),
    sentence=(
        "In Lark groups of bound reserved people: the room is sent what everybody present may "
        "read and the asker their own answer in a card only they see; a room nobody in may be "
        "told anything is sent a link to Ask; and a room that changed while the answer was made "
        "is read again and not posted to."
    ),
)
async def a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone(h: Harness) -> None:
    from brain.chat_answer import LINK_TOLD, ask_link

    await h.found_departments()
    chat = await lark_app(h)
    link = ask_link()
    if not link:
        raise CheckNotRunError("this install names no address of its own, so there is no Ask")
    table = await uploaded(h)
    wide, narrow, none = (h.principal(A, role) for role in ("wide", "narrow", "none"))
    await h.person(wide, department=A, grants=table.reads(A, held=True))
    await h.person(narrow, department=A, grants=table.reads(A, held=False))
    await h.person(none, department=A)
    ids = {wide: open_id(), narrow: open_id(), none: open_id()}
    await bound(chat, ids)
    room, card = [ids[wide], ids[narrow]], ("aside", f"room:{ids[wide]}")

    async def asked(rooms: list[list[str]], asker: str, column: str) -> list[tuple[str, str, str]]:
        """What one question naming the bot in a new group sent, the group written `room`."""
        group = chat_id()
        chat.lark.rooms[group] = rooms
        before = len(chat.lark.sent)
        await chat.post(asker, table.asking(column), chat=group, group=True, to_bot=True)
        return [
            (kind, where.replace(group, "room"), text)
            for kind, where, text in chat.lark.messages()[before:]
        ]

    both = await asked([room], ids[wide], table.open_column)
    if [(kind, where) for kind, where, _ in both] != [("chat_id", "room"), card]:
        raise CheckFailedError("a group was not sent its floor beside the asker's own card")
    if table.seen not in both[0][2] or table.held_column in both[0][2]:
        raise CheckFailedError("the room was not sent exactly what everybody present may read")
    if table.seen not in both[1][2]:
        raise CheckFailedError("the asker's card did not carry their own answer")
    alone = await asked([room], ids[wide], table.held_column)
    if [(kind, where) for kind, where, _ in alone] != [card] or table.held not in alone[0][2]:
        raise CheckFailedError("a column somebody present may not read was not the asker's alone")
    together = await asked([[ids[wide]]], ids[wide], table.held_column)
    if [(kind, where) for kind, where, _ in together] != [("chat_id", "room")]:
        raise CheckFailedError("a room where everybody holds the answer was not answered once")
    linked = await asked([[ids[none], open_id()]], ids[none], table.open_column)
    if linked != [("chat_id", "room", f"{LINK_TOLD}{link}")]:
        raise CheckFailedError("a room where nothing may be said was not sent a link to Ask")
    reads = len(chat.lark.reads)
    changed = await asked([room, [*room, open_id()]], ids[wide], table.open_column)
    if [(kind, where) for kind, where, _ in changed] != [card]:
        raise CheckFailedError("a room that changed before sending was posted the old answer")
    if len(chat.lark.reads) - reads != 2:
        raise CheckFailedError("the room was not read again before its answer was sent")
