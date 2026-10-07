"""The install acceptance check for the one step every channel sends through: `deliver`.

`brain.ops.acceptance_checks_channels` and `brain.ops.acceptance_checks_chat` prove the half that
arrives, a message verified and answered on the install's own events route. What none of them
could show is the half that leaves for each vendor: that a planned message is built for that
vendor's API with a credential kept outside the channel's record, and that what the vendor said
is written down as what it was. Every route there ends at a transport that answers 200, so a
wire that read every answer as delivered would have passed them all.

**This check calls `deliver`, the one send step, once per wire and per kind of answer.** For each
of the seven channels `brain.channels.adapter.channel_wires` finds it saves an enabled record
through `brain.ops.channel_store.StoredChannels` as the Channels screen does, holds a secret the
check made in a vault stand-in that remembers which slot it was asked for, and delivers a planned
sentence through a transport that keeps the request and answers as the vendor documents:

- **Accepted** (a 2xx, Lark's `code` 0, Slack's and Telegram's `ok`, WhatsApp's `messages`, the
  mail relay's 250) is read back from `ops.channel_delivery` as `sent`, carrying the vendor's
  status.
- **Refused** (a 4xx, a redirect, a quota, an address this side refuses to connect to, and for
  Lark, Slack and Telegram a refusal written inside a 200) is read back as `refused` with its
  reason, and is **never** `sent`. This is the sentence's last clause, and the whole reason the
  vendors are told apart: Slack answers 200 and refuses in the body.
- **Unknown** (a timeout, a dropped connection, a 5xx, a 200 whose body names no message) is read
  back as `unknown`, never `sent` and never `refused`, because such a request may have been
  delivered. See `brain.channels.outbound`.

Each request is also held to the planned words it carries, to the secret reaching it where the
wire uses one (Slack's bearer token, Telegram's address, Lark's and Teams's token exchange,
WhatsApp's access token, the webhook's signature), and the secret is looked for in the record
read back and in the delivery rows and must be in neither. **The email wire is the one that never
puts its secret in what it sends**: its secret signs the receiving script's posts and the relay's
password is lent separately by the relay, so for it the check asserts the secret is absent from
the request, which is the property that holds, and does not pretend one that does not.

**What is made up, and so what the pass is worth.** The vendor does not exist: the transport is
the check's, and its answers are the shapes each vendor documents, written from the same
documentation the wires were. The secrets are made here. A pass shows the install's own wires,
store and delivery record behave as the sentence says; it does not show that Slack, Meta,
Microsoft, Telegram, Lark, a relay or a company's webhook accept what is sent. So the leaf is held
in `docs/proof-sweep-holds.json` until the install connects the owner's own account (needs-rupash
126), where the first real delivery is the other half.

**Rejected: a transport that answers 200 and a check that only builds the requests.** That proves
the request and nothing about the record, which is the half this leaf is for.

**Rejected: one check per channel.** The sentence is about every adapter. One check that walks
`channel_wires` fails the moment an eighth wire arrives with no fixture here
(`A_CHANNEL_WITH_NO_FIXTURE_IS_NOT_PROVED`), where seven separate checks would go on passing and
the new channel would be proved by nothing.

**Rejected: building a reason for a failure out of the wire's name.** A reason is served on a
public page and every one is a literal (`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`), so the
failure sentence names the property and the worker's log, on stderr, names the channel.

Task ids: M10.6.1
"""

from __future__ import annotations

import json
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import parse_qs

from sqlalchemy import text

from brain.channels.adapter import VendorAnswer, VendorRequest, channel_wires
from brain.channels.outbound import Outgoing, deliver
from brain.gate.context import Channel
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks import _HeldLedger, _Secret
from brain.ops.acceptance_run import LOG_PREFIX, Harness
from brain.ops.channel_store import (
    ChannelRecord,
    DeliveryEntry,
    DeliveryRecords,
    DeliveryView,
    StoredChannels,
    StoredDeliveries,
    channel_secret_ref,
)
from brain.ops.idempotency import Intent
from brain.tables.channel import DeliveryOutcome, RefusedBecause

#: Where this module's check stands on the Install page, after the channel checks it completes.
#: See `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 720

# ------------------------------------------------------------------ written-down reasons
#: Why a channel with no fixture here fails the check instead of being skipped.
A_CHANNEL_WITH_NO_FIXTURE_IS_NOT_PROVED: Final = (
    "a channel the product has a wire for has no fixture in this check, or this check has a "
    "fixture for a channel with no wire, so a channel could deliver with nothing proving it"
)

#: Why the check stops at the first wire that fails, and what the worker's log adds.
THE_LOG_NAMES_THE_CHANNEL_AND_THE_RESULT_NAMES_THE_PROPERTY: Final = (
    "A result is served on a public page and is a literal sentence, so it names the property "
    "that failed; the channel it failed for is on the worker's stderr beside the check's name."
)

THE_ENABLED_RECORD_WAS_NOT_KEPT: Final = (
    "a channel's enabled record, saved with a secret reference and no secret, was not read back "
    "as saved, or named another slot than its own channel's"
)
THE_TRANSPORT_WAS_NOT_ASKED_ONCE: Final = (
    "a planned message was not handed to the vendor's transport exactly once as one request"
)
THE_VAULT_WAS_ASKED_FOR_ANOTHER_SLOT: Final = (
    "a delivery asked the vault for something other than its own channel's slot, or did not ask"
)
THE_CREDENTIAL_DID_NOT_REACH_THE_REQUEST: Final = (
    "the secret held outside the channel's record did not reach the request built for the vendor"
)
THE_CREDENTIAL_REACHED_A_REQUEST_THAT_NEVER_CARRIES_IT: Final = (
    "a channel whose wire never sends its secret put the secret in the request built for the vendor"
)
THE_PLANNED_TEXT_WAS_NOT_IN_THE_REQUEST: Final = (
    "the words planned for the message were not in the request built for the vendor"
)
THE_DELIVERY_WAS_NOT_RECORDED_AS_IT_CAME_TO: Final = (
    "a delivery was not written to the delivery record, or what was read back differs from what "
    "the delivery came to"
)
AN_ACCEPTED_DELIVERY_WAS_NOT_RECORDED_SENT: Final = (
    "a delivery the vendor accepted as it documents was not recorded as sent with the vendor's "
    "status"
)
A_REFUSED_DELIVERY_WAS_NOT_RECORDED_REFUSED: Final = (
    "a delivery the vendor refused was not recorded as refused with its reason, or was recorded "
    "as sent"
)
AN_UNANSWERED_DELIVERY_WAS_NOT_RECORDED_UNKNOWN: Final = (
    "a delivery the vendor never answered, or answered with a fault, was recorded as sent or as "
    "refused instead of as not known"
)
THE_CREDENTIAL_WAS_KEPT_WITH_THE_RECORD: Final = (
    "a channel's secret was found in its stored record or in a delivery row, so it is not held "
    "outside configuration"
)

# ------------------------------------------------------------------------ the fixtures
#: Where the check's addresses point. `.invalid` never resolves, so nothing can be reached.
_DOMAIN: Final = "acceptance.invalid"

#: The sentence planned for every delivery, ahead of a word nothing on the install holds.
_PLANNED: Final = "Acceptance delivery for the channel check"

_NEVER_ANSWERED: Final = (VendorAnswer(timed_out=True), VendorAnswer(connection_failed=True))


def _json(body: Mapping[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _unreadable() -> VendorAnswer:
    """A 200 whose body is not the vendor's JSON: it may have been delivered, so it is unknown."""
    return VendorAnswer(status=200, body=b"<html>gateway</html>")


@dataclass(frozen=True)
class _Vendor:
    """One channel's fixture: its record, its secret, an address, and what its vendor says.

    `parts` are the made-up values the secret holds, each looked for in the database afterwards.
    `reached` says whether the request carries the secret the way this wire does, or is None for
    the one wire whose requests never do.
    """

    channel: Channel
    tenant: Mapping[str, str]
    secret: str = field(repr=False)
    parts: tuple[str, ...] = field(repr=False)
    to: str
    accepted: VendorAnswer
    refused: tuple[tuple[VendorAnswer, RefusedBecause], ...]
    unknown: tuple[VendorAnswer, ...]
    reached: Callable[[VendorRequest], bool] | None


def _made() -> str:
    return secrets.token_hex(16)


def _webhook() -> _Vendor:
    from brain.channels.webhook import REPLY_URL, SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

    secret = secrets.token_hex(32)

    def reached(request: VendorRequest) -> bool:
        stamp = request.headers.get(TIMESTAMP_HEADER, "")
        return request.headers.get(SIGNATURE_HEADER) == sign(secret, stamp, request.body)

    return _Vendor(
        channel=Channel.WEBHOOK,
        tenant={REPLY_URL: f"https://{_DOMAIN}/reply"},
        secret=secret,
        parts=(secret,),
        to="acceptance-conversation",
        accepted=VendorAnswer(status=204),
        refused=(
            (VendorAnswer(status=403), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=410), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=302), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(*_NEVER_ANSWERED, VendorAnswer(status=503)),
        reached=reached,
    )


def _lark() -> _Vendor:
    from brain.channels.adapter import BOT_ID
    from brain.channels.lark import APP_ID_FIELD, PLATFORM_FIELD, LarkSecret

    app_secret, encrypt_key, token = _made(), _made(), _made()
    kept = LarkSecret(app_secret=app_secret, encrypt_key=encrypt_key, verification_token=token)

    def reached(request: VendorRequest) -> bool:
        return request.exchange is not None and app_secret.encode() in request.exchange.body

    return _Vendor(
        channel=Channel.LARK,
        tenant={APP_ID_FIELD: "cli_acceptance", PLATFORM_FIELD: "larksuite.com", BOT_ID: "ou_bot"},
        secret=kept.kept(),
        parts=(app_secret, encrypt_key, token),
        to="chat:oc_acceptance",
        accepted=VendorAnswer(status=200, body=_json({"code": 0, "msg": "success", "data": {}})),
        refused=(
            (
                VendorAnswer(status=200, body=_json({"code": 230002, "msg": "bot not in chat"})),
                RefusedBecause.VENDOR_REFUSED,
            ),
            (
                VendorAnswer(status=200, body=_json({"code": 99991400, "msg": "rate limited"})),
                RefusedBecause.VENDOR_REFUSED,
            ),
            (VendorAnswer(status=400), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(*_NEVER_ANSWERED, VendorAnswer(status=500), _unreadable()),
        reached=reached,
    )


def _email() -> _Vendor:
    from brain.channels.email import ADDRESS

    secret = secrets.token_hex(32)
    return _Vendor(
        channel=Channel.EMAIL,
        tenant={ADDRESS: f"ask@{_DOMAIN}"},
        secret=secret,
        parts=(secret,),
        to=f"person@{_DOMAIN}",
        accepted=VendorAnswer(status=250),
        refused=(
            (VendorAnswer(status=550), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=554), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(*_NEVER_ANSWERED, VendorAnswer(status=450)),
        reached=None,
    )


def _slack() -> _Vendor:
    from brain.channels.adapter import BOT_ID
    from brain.channels.slack import BOT_TOKEN, SIGNING_SECRET

    signing, token = _made(), _made()
    return _Vendor(
        channel=Channel.SLACK,
        tenant={BOT_ID: "UACCEPTANCE"},
        secret=json.dumps({SIGNING_SECRET: signing, BOT_TOKEN: token}),
        parts=(signing, token),
        to="CACCEPTANCE",
        accepted=VendorAnswer(status=200, body=_json({"ok": True})),
        refused=(
            (
                VendorAnswer(status=200, body=_json({"ok": False, "error": "channel_not_found"})),
                RefusedBecause.VENDOR_REFUSED,
            ),
            (
                VendorAnswer(status=200, body=_json({"ok": False, "error": "ratelimited"})),
                RefusedBecause.VENDOR_REFUSED,
            ),
            (VendorAnswer(status=403), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(*_NEVER_ANSWERED, VendorAnswer(status=503), _unreadable()),
        reached=lambda request: request.headers.get("Authorization") == f"Bearer {token}",
    )


def _teams() -> _Vendor:
    from brain.channels.adapter import BOT_ID
    from brain.channels.teams import TENANT_ID

    secret = _made()

    def reached(request: VendorRequest) -> bool:
        if request.exchange is None:
            return False
        return parse_qs(request.exchange.body.decode("utf-8")).get("client_secret") == [secret]

    return _Vendor(
        channel=Channel.TEAMS,
        tenant={
            BOT_ID: "1b2c3d4e-1111-4000-8000-0123456789ab",
            TENANT_ID: "1b2c3d4e-3333-4000-8000-0123456789ab",
        },
        secret=secret,
        parts=(secret,),
        to="https://smba.trafficmanager.net/emea/ a:1acceptanceconversation",
        accepted=VendorAnswer(status=201),
        refused=(
            (VendorAnswer(status=403), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=400), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=302), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(*_NEVER_ANSWERED, VendorAnswer(status=502)),
        reached=reached,
    )


def _telegram() -> _Vendor:
    from brain.channels.adapter import BOT_ID

    # The shape BotFather issues: digits, a colon, and a body of at least twenty URL-safe letters.
    token = f"{100_000_000 + secrets.randbelow(900_000_000)}:{secrets.token_urlsafe(24)}"
    return _Vendor(
        channel=Channel.TELEGRAM,
        tenant={BOT_ID: "acceptance_bot"},
        secret=token,
        parts=(token,),
        to="999000111",
        accepted=VendorAnswer(status=200, body=_json({"ok": True, "result": {}})),
        refused=(
            (
                VendorAnswer(
                    status=200,
                    body=_json({"ok": False, "error_code": 403, "description": "bot was blocked"}),
                ),
                RefusedBecause.VENDOR_REFUSED,
            ),
            (VendorAnswer(status=403), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=429), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(*_NEVER_ANSWERED, VendorAnswer(status=502), _unreadable()),
        reached=lambda request: f"/bot{token}/sendMessage" in request.url,
    )


def _whatsapp() -> _Vendor:
    from brain.channels.whatsapp import ACCESS_TOKEN, APP_SECRET, PHONE_NUMBER_ID, VERIFY_TOKEN

    app, access, verify = _made(), _made(), _made()
    return _Vendor(
        channel=Channel.WHATSAPP,
        tenant={PHONE_NUMBER_ID: "999000111222"},
        secret=json.dumps({APP_SECRET: app, ACCESS_TOKEN: access, VERIFY_TOKEN: verify}),
        parts=(app, access, verify),
        to="999000222333",
        accepted=VendorAnswer(status=200, body=_json({"messages": [{"id": "wamid.ACCEPTANCE"}]})),
        refused=(
            (
                VendorAnswer(status=400, body=_json({"error": {"code": 131047, "message": "x"}})),
                RefusedBecause.VENDOR_REFUSED,
            ),
            (VendorAnswer(status=401), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(status=429), RefusedBecause.VENDOR_REFUSED),
            (VendorAnswer(unsafe_address=True), RefusedBecause.UNSAFE_ADDRESS),
        ),
        unknown=(
            *_NEVER_ANSWERED,
            VendorAnswer(status=500),
            VendorAnswer(status=200, body=_json({"messages": []})),
        ),
        reached=lambda request: request.headers.get("Authorization") == f"Bearer {access}",
    )


def vendors() -> tuple[_Vendor, ...]:
    """Every channel's fixture, with secrets made afresh. One per wire `channel_wires` finds."""
    return (
        _webhook(),
        _lark(),
        _email(),
        _slack(),
        _teams(),
        _telegram(),
        _whatsapp(),
    )


# ------------------------------------------------------------------------ the stand-ins
@dataclass
class _Vault(_Secret):
    """The check's secret store: it lends the made-up secret and remembers what was asked for."""

    asked: list[object] = field(default_factory=list)

    def read(self, ref: object) -> str | None:
        self.asked.append(ref)
        return self.value


@dataclass
class _Answering:
    """`brain.channels.adapter.ChannelTransport` that keeps each request and answers as told."""

    answer: VendorAnswer = field(default_factory=VendorAnswer)
    sent: list[VendorRequest] = field(default_factory=list)

    def send(self, request: VendorRequest) -> VendorAnswer:
        self.sent.append(request)
        return self.answer

    def read(self, request: VendorRequest) -> VendorAnswer:
        del request
        return VendorAnswer(connection_failed=True)


@dataclass
class _RecordedDeliveries:
    """`DeliveryRecords` over the install's own store, remembering what was handed to it."""

    inner: DeliveryRecords
    entries: list[DeliveryEntry] = field(default_factory=list)

    async def record(self, entry: DeliveryEntry) -> None:
        self.entries.append(entry)
        await self.inner.record(entry)

    async def recent(self, channel: Channel) -> tuple[DeliveryView, ...]:
        return await self.inner.recent(channel)


def _say(vendor: _Vendor, what: str) -> None:
    """The channel a failure was for, on the worker's stream. See the reason constant."""
    print(f"{LOG_PREFIX} channel delivery, {vendor.channel.value}: {what}", file=sys.stderr)


# ------------------------------------------------------------------------ the check
@check(
    leaves=("M10.6.1",),
    sentence=(
        "Each of the seven channels builds its planned message for its vendor with a secret held "
        "outside its record, and what the vendor answers is recorded as it was: accepted as sent, "
        "refused, including inside a 200, as refused, and silence or a fault as unknown, and "
        "never a refusal as sent."
    ),
)
async def each_channel_delivers_and_a_refusal_is_never_recorded_as_sent(
    h: Harness,
) -> None:
    from brain.gate.entitlement_store import StoredEntitlements

    made = vendors()
    if {one.channel for one in made} != set(channel_wires()) or len(made) != len(channel_wires()):
        raise CheckFailedError(A_CHANNEL_WITH_NO_FIXTURE_IS_NOT_PROVED)

    stored = StoredChannels(h.sessions)
    for number, vendor in enumerate(made):
        await stored.save(
            vendor.channel,
            enabled=True,
            tenant=vendor.tenant,
            actor=h.actor,
            ent_hash="0" * 32,
            trace_id=h.trace_id,
        )
        record = await stored.get(vendor.channel)
        if (
            record is None
            or not record.enabled
            or dict(record.tenant) != dict(vendor.tenant)
            or record.secret != channel_secret_ref(vendor.channel)
        ):
            _say(vendor, "the saved record was not read back as saved")
            raise CheckFailedError(THE_ENABLED_RECORD_WAS_NOT_KEPT)

        vault = _Vault(vendor.secret)
        kept = _RecordedDeliveries(StoredDeliveries(h.sessions))
        scenarios: list[tuple[VendorAnswer, DeliveryOutcome, RefusedBecause | None]] = [
            (vendor.accepted, DeliveryOutcome.SENT, None),
            *((one, DeliveryOutcome.REFUSED, why) for one, why in vendor.refused),
            *(
                (one, DeliveryOutcome.UNKNOWN, RefusedBecause.VENDOR_UNAVAILABLE)
                for one in vendor.unknown
            ),
        ]
        for step, (answer, outcome, why) in enumerate(scenarios):
            await _one_delivery(
                h,
                vendor,
                record,
                vault=vault,
                kept=kept,
                reach=StoredEntitlements(h.sessions),
                answer=answer,
                expected=(outcome, why),
                tag=f"{number}.{step}",
            )
        if await _secret_was_kept(h, vendor):
            _say(vendor, "a secret value was found in the record or a delivery row")
            raise CheckFailedError(THE_CREDENTIAL_WAS_KEPT_WITH_THE_RECORD)


async def _one_delivery(
    h: Harness,
    vendor: _Vendor,
    record: ChannelRecord,
    *,
    vault: _Vault,
    kept: _RecordedDeliveries,
    reach: Any,
    answer: VendorAnswer,
    expected: tuple[DeliveryOutcome, RefusedBecause | None],
    tag: str,
) -> None:
    """One planned message through `deliver`, answered as told, and everything read back."""
    outcome, why = expected
    transport, planned = _Answering(answer), f"{_PLANNED} {h.word()}"
    vault.asked.clear()
    kept.entries.clear()
    before = {one.recorded_at for one in await kept.recent(vendor.channel)}

    delivered = await deliver(
        Outgoing(
            channel=vendor.channel,
            to=vendor.to,
            intent=Intent(principal_id=h.actor, intent_ref=f"delivery.{h.run}.{tag}"),
            text=planned,
        ),
        record=record,
        secrets=vault,
        reach=reach,
        transport=transport,
        ledger=_in_memory(_HeldLedger()),
        deliveries=kept,
        now=h.now,
    )

    if len(transport.sent) != 1:
        _say(vendor, "the transport was not asked exactly once")
        raise CheckFailedError(THE_TRANSPORT_WAS_NOT_ASKED_ONCE)
    [request] = transport.sent
    if vault.asked != [record.secret]:
        _say(vendor, "the vault was asked for another slot or none")
        raise CheckFailedError(THE_VAULT_WAS_ASKED_FOR_ANOTHER_SLOT)
    if vendor.reached is not None and not vendor.reached(request):
        _say(vendor, "the secret did not reach the request")
        raise CheckFailedError(THE_CREDENTIAL_DID_NOT_REACH_THE_REQUEST)
    if vendor.reached is None and _holds_any(request, vendor.parts):
        _say(vendor, "the secret reached a request this wire never puts it in")
        raise CheckFailedError(THE_CREDENTIAL_REACHED_A_REQUEST_THAT_NEVER_CARRIES_IT)
    if planned.encode("utf-8") not in request.body:
        _say(vendor, "the planned words were not in the request")
        raise CheckFailedError(THE_PLANNED_TEXT_WAS_NOT_IN_THE_REQUEST)

    after = await kept.recent(vendor.channel)
    entry = kept.entries[0] if len(kept.entries) == 1 else None
    written = [one for one in after if one.recorded_at not in before and one.entry == entry]
    if entry is None or len(written) != 1 or delivered.outcome is not entry.outcome:
        _say(vendor, "the delivery row was not written as the delivery came to")
        raise CheckFailedError(THE_DELIVERY_WAS_NOT_RECORDED_AS_IT_CAME_TO)

    if outcome is DeliveryOutcome.SENT:
        if entry.outcome is not DeliveryOutcome.SENT or entry.vendor_status != answer.status:
            _say(vendor, "an accepted answer was not recorded sent with its status")
            raise CheckFailedError(AN_ACCEPTED_DELIVERY_WAS_NOT_RECORDED_SENT)
    elif outcome is DeliveryOutcome.REFUSED:
        if entry.outcome is not DeliveryOutcome.REFUSED or entry.reason is not why:
            _say(vendor, "a refused answer was not recorded refused with its reason")
            raise CheckFailedError(A_REFUSED_DELIVERY_WAS_NOT_RECORDED_REFUSED)
    elif entry.outcome is not DeliveryOutcome.UNKNOWN or entry.reason is not why:
        _say(vendor, "an unanswered request was not recorded as not known")
        raise CheckFailedError(AN_UNANSWERED_DELIVERY_WAS_NOT_RECORDED_UNKNOWN)


def _in_memory(ledger: _HeldLedger) -> Callable[[Callable[[Any], Any]], Any]:
    """The send step's ledger runner over a ledger held in memory, as a test of it is given."""

    def run(work: Callable[[Any], Any]) -> Any:
        return work(ledger)

    return run


def _holds_any(request: VendorRequest, values: tuple[str, ...]) -> bool:
    """Whether any value is in the request's address, headers or body, or its token exchange."""
    held = [request.url, *request.headers.values(), request.body.decode("utf-8", "replace")]
    if request.exchange is not None:
        held.append(request.exchange.body.decode("utf-8", "replace"))
    return any(value in one for value in values for one in held)


async def _secret_was_kept(h: Harness, vendor: _Vendor) -> bool:
    """Whether any made-up secret value is in the channel's record or its recent delivery rows."""
    async with h.sessions() as session:
        # Fixed statements: nothing here is built from a value but the bound channel and time.
        rows = (
            await session.execute(
                text("SELECT t::text FROM ops.channel t WHERE t.channel = :channel"),
                {"channel": vendor.channel.value},
            )
        ).scalars()
        deliveries = (
            await session.execute(
                text(
                    "SELECT t::text FROM ops.channel_delivery t"
                    " WHERE t.channel = :channel AND t.recorded_at >= :since"
                ),
                {"channel": vendor.channel.value, "since": h.now},
            )
        ).scalars()
        held = [*rows, *deliveries]
    return any(part in one for part in (vendor.secret, *vendor.parts) for one in held)
