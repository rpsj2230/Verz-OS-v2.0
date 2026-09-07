"""Telling somebody else that something happened here, without telling them what it was.

An outbound webhook is the one thing this platform sends that nobody re-checks. Everything
else, every answer, every citation, every tool result, is composed for a caller whose
entitlements were resolved for that request. A webhook payload is composed once and read for
ever by whoever holds the endpoint, and there is no second evaluation on the far side. So the
first rule is about the payload and the rest is delivery mechanics.

**An event carries identifiers and a kind, never content.** The same rule, for the same
reason, that `brain.gate.compose.Citation` follows when it carries a field name and never a
field value: a copy of business data that travels somewhere the redactor does not reach has
lost the permissions that governed it and cannot get them back. So a subscriber learns that a
thing happened and which record it happened to, and comes back through the gate as a named
principal to learn what the record says. `EventKind` is closed and every member is a fact
about our own machinery rather than about a client's data, which is what makes "ids and a
kind" enforceable rather than aspirational: there is no kind that could carry a body.

**This is at-least-once, and saying otherwise would be a lie.** An outbox with retry
guarantees delivery, not single delivery: a subscriber that received a request and answered
slowly gets the same event again, and no amount of care on this side can tell that apart from
a subscriber that never received it. So the subscriber deduplicates on the event id, and that
requirement is part of the contract rather than a footnote. See `DELIVERY_IS_AT_LEAST_ONCE`.
This is exactly why `brain.ops.idempotency` needs an `UNKNOWN` state and this module does
not: that one promises exactly-once and has to be honest about not knowing, and this one
promises at-least-once and pushes the duplicate on to somebody who can cheaply drop it.

**Why a table rather than an HTTP call at the point of change.** The event row is written in
the same transaction as the business change, so there is no window in which the change is
committed and the notification is not, and none in which the notification goes out and the
change rolls back. That is the whole of what "outbox" means, and it is the reason this is a
row rather than a call. **The table itself is not in this repository yet**: nothing here
names a column and `src/brain/tables/` holds no outbox model. This module is the shape and
the policy; the schema and its migration belong to whoever writes them, and they must enable
row-level security like every other table here.

**Signing is HMAC over a canonical serialisation with the timestamp inside it, and the
implementation is imported rather than rewritten.** `brain.channels.webhook.sign` already
holds it, for verifying inbound requests, and the construction is the same one in both
directions. Two copies of what-is-signed is the failure that produces a signature nobody can
verify after somebody fixes one of them. The timestamp is inside the signed material because
a signature over the body alone can be captured and replayed for ever with a fresh timestamp,
which is what makes the receiver's window check do nothing. See `RECEIVER_MUST_CHECK` for the
four things the far side has to do, in order.

**A subscriber's address is checked at every delivery and not at registration.**
`brain.tools.fetch.assert_fetchable` is the rule and it is not called from
`Subscriber.__post_init__` on purpose: a name that resolved to a public address when somebody
typed it into the console resolves to `169.254.169.254` on the day they change the record,
and an outbox retries the same endpoint for months. A check in the constructor reads as
"already checked", which is the hole `Fetchable` exists to close.

Rejected: writing the retry and the backoff here. `brain.connectors.throttle.retry_delay` is
the platform's rule, including the case that gets missed, which is a refusal that stated no
wait at all. A second backoff would give subscribers a different one from connectors for no
reason anybody could name later, and the copy that drifts is the one nobody is looking at.

Rejected: putting subscriber endpoints on `brain.ops.automation.EGRESS_ALLOWLIST`. That list
is five hosts a client's plumbing genuinely needs, matched exactly, and it is right for a
sandbox that reaches known systems. A subscriber endpoint is chosen by the client and is
arbitrary by design, so the question is not "is this host on the list" but "is this address
one of ours", which is a different rule and already written.

Scope: domain logic. Nothing here opens a socket, reads a clock or holds a credential: the
secret arrives as a parameter for the duration of one call, borrowed and revoked by
`brain.ops.secrets.borrow`, and there is no attribute anywhere in this module that holds one.

Task ids: M17.5.1, M17.5.2, M17.5.3
"""

from __future__ import annotations

import enum
import hmac
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.channels.webhook import DEFAULT_WINDOW, sign
from brain.connectors.throttle import CallOutcome, is_retryable, retry_delay
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.core.projection import is_forbidden
from brain.ops.limits import BACKOFF_AFTER_REFUSALS, MAX_BACKOFF_SECONDS
from brain.ops.queue import MAX_ARGUMENT_CHARS
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Fetchable, Resolver, UnsafeAddressError, assert_fetchable

# ------------------------------------------------------------------ written-down reasons
#: Why the event is a row written with the business change rather than a call made after it.
AN_OUTBOX_IS_A_ROW_IN_THE_SAME_TRANSACTION = (
    "The event is inserted in the transaction that made the change, so the two commit "
    "together or neither does. Calling the subscriber at the point of change instead leaves "
    "two failures with no way to tell them apart afterwards: the change committed and the "
    "call failed, so nobody was told; or the call succeeded and the transaction rolled back, "
    "so somebody was told about something that did not happen. A row removes both, and the "
    "price is that a separate worker has to drain it."
)

#: The guarantee, stated plainly because the alternative is a subscriber assuming the other.
DELIVERY_IS_AT_LEAST_ONCE = (
    "An outbox with retry delivers at least once and never exactly once. A subscriber that "
    "received a request and answered slowly, or answered and had the answer lost, is "
    "indistinguishable from one that never received it, so the honest response to both is to "
    "send it again. The duplicate is therefore the subscriber's to drop, and the event id is "
    "what they drop it on: it is minted once, with the row, and is the same on every "
    "attempt. Anybody claiming exactly-once for a webhook has moved the problem to the "
    "receiver without telling them."
)

#: Why the payload is identifiers and never values.
AN_EVENT_CARRIES_IDS_AND_NEVER_CONTENT = (
    "A webhook payload leaves the permission boundary completely. It is readable by whoever "
    "holds the endpoint, for as long as they keep it, with no re-check and no way to revoke "
    "what has already been sent. brain.gate.compose.Citation carries a field name and never "
    "a field value for exactly this reason one layer in, and the argument only gets stronger "
    "the further the data travels. So an event says that something happened and which record "
    "it happened to, and a subscriber that wants to know what the record says asks for it as "
    "a named principal whose entitlements are resolved at that moment."
)

#: Why the send time is part of what is signed.
THE_TIMESTAMP_IS_INSIDE_THE_SIGNATURE = (
    "A signature over the body alone is valid for that body for ever. Anybody who captures "
    "one, from a proxy log or a subscriber's own storage, can replay the request whenever "
    "they like and it verifies. Signing the timestamp with the body binds the signature to a "
    "moment, which is what gives the receiver's window check something to stand on: without "
    "it the window refuses stale requests and the signature accepts them, and the signature "
    "is the half that decides."
)

#: What a receiver has to do, in order. Four items, because three of them are commonly done
#: and the fourth is commonly not.
RECEIVER_MUST_CHECK = (
    "Recompute the signature over the raw bytes received, never over a re-serialisation: "
    "JSON has no canonical form, so a re-encoded body verifies something we never signed. "
    "Compare with a constant-time comparison, because == returns as soon as two bytes "
    "differ and the time it takes says how much of a guess was right. Refuse a timestamp "
    "outside the window in both directions, because a request from the future is as wrong as "
    "one from the past. And deduplicate on the event id in the verified body, because "
    "delivery is at least once and the id in an unsigned header is not the id we signed."
)

#: Why the address rule runs per delivery rather than once at registration.
A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY = (
    "A subscriber row lives for months and is delivered to thousands of times. A hostname "
    "checked when it was typed into the console can answer differently at any later lookup, "
    "which is DNS rebinding and is the standard way past exactly this defence. So the check "
    "belongs to the delivery and not to the record, and brain.tools.fetch.Fetchable carries "
    "the address it passed for, so the sender connects to what was checked rather than to "
    "the name it was checked under."
)

#: What is deliberately not built, said here so a reader does not go looking for it.
THE_CONSOLE_SCREEN_IS_NOT_BUILT = (
    "M17.5.3 asks for subscriber management in the console. What is here is the policy half: "
    "what a subscriber is, what may be subscribed to, who may manage one, and what the "
    "address rule is. There is no screen, no route and no table. The console surface would "
    "list subscribers, show which kinds each takes and when it last delivered, and offer "
    "create, deactivate and rotate-the-secret; every one of those is a write and every one "
    "of them needs MANAGE_SUBSCRIBERS, which is why the capability is named here rather than "
    "invented by whoever builds the screen."
)


class OutboxError(Exception):
    """An event, a subscriber or a delivery was described in a shape that cannot be sent.

    Outside `brain.core.errors` for the reason `brain.connectors.contract` gives about its
    own: this is a mistake by whoever configured the subscription, and it should stop a
    subscriber being registered rather than degrade somebody's answer at request time.
    """


# ------------------------------------------------------------ what may be subscribed to
class EventKind(enum.StrEnum):
    """Every kind of thing a subscriber may be told about. Closed, and closed on purpose.

    Each member is a fact about this platform's own machinery. None of them is a business
    record changing, and that absence is the design: an event about a client's invoice would
    have to name the invoice to be useful, and naming it usefully means carrying a value.
    See `AN_EVENT_CARRIES_IDS_AND_NEVER_CONTENT`.

    A kind added here is a decision about what leaves the boundary, which is why it is an
    enum in this file rather than a string in a subscription row.
    """

    #: An automation run reached a terminal state. The subscriber gets the run's id.
    AUTOMATION_RUN_FINISHED = "automation.run_finished"
    #: A side-effecting operation settled, succeeded or failed. See `brain.ops.idempotency`.
    OPERATION_SETTLED = "operation.settled"
    #: A connector's health probe changed state. An operator-facing fact about our plumbing.
    CONNECTOR_HEALTH_CHANGED = "connector.health_changed"
    #: Somebody has been asked to approve something and has not yet.
    APPROVAL_REQUESTED = "approval.requested"


#: Who may create, change or deactivate a subscriber. Named here so the console cannot pick a
#: different string: a screen that checked `admin:webhooks` while the grants said
#: `admin:webhook_subscriber` would refuse everybody, and the fix somebody reaches for under
#: pressure is to stop checking. Built as a `Capability` rather than kept as a bare string so
#: that `brain.core.entitlement`'s own grammar is what validates it.
MANAGE_SUBSCRIBERS: Final = Capability(value="admin:webhook_subscriber")


def may_manage(entitlement: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this principal may manage subscriptions.

    One line, and it earns its place by being the only line: the capability is named once, so
    the screen that does not exist yet cannot check a different one, and a test can pin it
    without importing a string literal from a template.
    """
    return entitlement.holds(MANAGE_SUBSCRIBERS, now)


# --------------------------------------------------------------------- the event
_ENTITY_RE: Final = re.compile(OBJECT_NAME_PATTERN)

#: How long an identifier may be before it is content rather than a reference. Imported from
#: `brain.ops.queue` rather than chosen again, because a queue row, a checkpoint and a
#: webhook payload are the same question asked three times, and the third asking is the
#: strictest: the other two stay inside a database we operate.
MAX_IDENTIFIER_CHARS: Final = MAX_ARGUMENT_CHARS


def assert_attribute_is_a_reference(name: str, value: object) -> None:
    """Refuse an event attribute that is content rather than a pointer at content.

    Three checks and each catches a different way a payload grows. A name on the permanent
    denylist in `brain.core.projection` is refused for a stronger version of the reason it is
    refused there: that list exists to stop a field being *stored*, and this sends it out of
    the building. A container is refused whatever its length, which is the rule
    `brain.ops.checkpoints` reached from the same direction, because a list under a declared
    name is where somebody puts records while meaning to put a summary. And a long string is
    content.

    **`value` is `object` rather than `str | int`, deliberately.** Written inline inside
    `OutboxEvent.__post_init__`, whose field is annotated `str | int`, mypy proves the type
    check dead and asks for it to be deleted, and it is very much alive: the call site that
    matters is the untyped one, where a row read out of a database is unpacked into this.
    `brain.channels.webhook.assert_raw_bytes` is the same shape for the same reason, and
    widening the parameter is what makes the check something the type checker can see the
    point of rather than something suppressed with a directive the next person removes.
    """
    if is_forbidden(name):
        msg = (
            f"attribute {name!r} is on the permanent denylist in brain.core.projection, "
            f"which exists to stop that field being stored. Sending it is worse. "
            f"{AN_EVENT_CARRIES_IDS_AND_NEVER_CONTENT}"
        )
        raise OutboxError(msg)
    if not isinstance(value, str | int):
        msg = (
            f"attribute {name!r} is a {type(value).__name__}; an event carries identifiers, "
            "and a container under a declared name is where a record ends up when somebody "
            "meant to put a reference"
        )
        raise OutboxError(msg)
    if isinstance(value, str) and len(value) > MAX_IDENTIFIER_CHARS:
        msg = (
            f"attribute {name!r} is {len(value)} characters; over {MAX_IDENTIFIER_CHARS} it "
            "is content rather than a reference, and this one leaves the permission boundary "
            "rather than merely being stored"
        )
        raise OutboxError(msg)


@dataclass(frozen=True)
class OutboxEvent:
    """One thing that happened, as a subscriber will read it.

    `event_id` is required and has no default. It is minted once, when the row is written
    with the business change, and it is the same on every delivery attempt: that is what
    makes it a deduplication key. A default that generated one here would mint a fresh id per
    send, which destroys deduplication in exactly the way a generated idempotency key
    destroys idempotency; `brain.ops.idempotency.A_KEY_IS_DERIVED_NEVER_GENERATED` is the
    same failure seen from the other side.

    `occurred_at` is when the thing happened and is not the signature's timestamp, which is
    when this attempt was sent. Both are needed and they answer different questions: delivery
    is at least once and unordered, so a subscriber orders on `occurred_at` and bounds replay
    on the signed one.
    """

    event_id: str
    kind: EventKind
    entity: str
    record_id: str
    occurred_at: datetime
    #: Further identifiers, if the record id alone does not locate the thing. Values only,
    #: never a body: see `AN_EVENT_CARRIES_IDS_AND_NEVER_CONTENT`.
    attributes: Mapping[str, str | int] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            msg = (
                "an event with no id cannot be deduplicated, and delivery is at least once, "
                f"so the subscriber has no way to drop the second copy. {DELIVERY_IS_AT_LEAST_ONCE}"
            )
            raise OutboxError(msg)
        if len(self.event_id) > MAX_IDENTIFIER_CHARS:
            msg = f"event id is {len(self.event_id)} characters; over {MAX_IDENTIFIER_CHARS} it "
            raise OutboxError(msg + "is not an identifier")
        if not _ENTITY_RE.match(self.entity):
            msg = (
                f"entity {self.entity!r} is not a name; a subscriber matches on it and a name "
                "nothing matches is an event nobody receives"
            )
            raise OutboxError(msg)
        if not self.record_id.strip() or len(self.record_id) > MAX_IDENTIFIER_CHARS:
            msg = (
                f"record id {self.record_id[:32]!r} is empty or longer than "
                f"{MAX_IDENTIFIER_CHARS} characters; an event points at a record and does not "
                "carry one"
            )
            raise OutboxError(msg)
        if self.occurred_at.tzinfo is None:
            # The same rule as every other timestamp in this package. A subscriber orders on
            # this, and two naive timestamps from two hosts produce an ordering that cannot
            # be compared, which is the only thing the field is for.
            msg = f"event {self.event_id!r} has no timezone on occurred_at"
            raise OutboxError(msg)
        for name, value in self.attributes.items():
            assert_attribute_is_a_reference(name, value)


def serialise(event: OutboxEvent) -> bytes:
    """The exact bytes that are signed and sent. Not a rendering; the thing itself.

    Sorted keys and no whitespace, the same canonicalisation
    `brain.connectors.manifest.digest_input` uses, so that reordering a mapping is not a
    different payload.

    **These bytes must be sent verbatim.** A sender that hands the event to an HTTP client
    and lets it serialise again has signed one thing and sent another, and the subscriber's
    verification fails in a way that looks like a wrong secret.
    `brain.channels.webhook.verify` refuses a parsed object on the receiving side for the
    same reason, and this is the sending half of that argument.
    """
    body = {
        "event_id": event.event_id,
        "kind": event.kind.value,
        "entity": event.entity,
        "record_id": event.record_id,
        "occurred_at": event.occurred_at.isoformat(),
        "attributes": dict(event.attributes),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


# ------------------------------------------------------------------ the subscriber
@dataclass(frozen=True)
class Subscriber:
    """One endpoint that has asked to be told about some kinds of event.

    `secret_ref` is a `SecretRef` and never a value, exactly as
    `brain.connectors.contract.CredentialBinding` holds one: the reference is safe in a
    configuration row and in a database, and is useless to anybody who cannot already reach
    the vault. Rotating the shared secret is then a vault operation and not a schema change.

    `created_by` is required for the reason a write grant names its granter: the question
    asked after a client's ids turned up somewhere unexpected is always who set this up, and
    a row with a URL in it cannot answer.

    There is deliberately no address check here. See
    `A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY`.
    """

    subscriber_id: str
    endpoint: str
    secret_ref: SecretRef
    kinds: tuple[EventKind, ...]
    created_by: str
    active: bool = True

    def __post_init__(self) -> None:
        if not self.subscriber_id.strip():
            msg = "a subscriber with no id cannot be deactivated by anybody"
            raise OutboxError(msg)
        if not self.endpoint.strip():
            msg = f"subscriber {self.subscriber_id!r} names no endpoint"
            raise OutboxError(msg)
        if not self.kinds:
            msg = (
                f"subscriber {self.subscriber_id!r} subscribes to nothing, which receives "
                "nothing and reads in a console as a working subscription. Deactivate it "
                "instead, which says the same thing where somebody can see it"
            )
            raise OutboxError(msg)
        duplicated = sorted({k for k in self.kinds if self.kinds.count(k) > 1})
        if duplicated:
            msg = (
                f"subscriber {self.subscriber_id!r} lists {duplicated} twice; delivery is "
                "per subscriber and per event, so a repeated kind is a row that means "
                "nothing and reads as though it might mean two deliveries"
            )
            raise OutboxError(msg)
        if not self.created_by.strip():
            msg = (
                f"subscriber {self.subscriber_id!r} names nobody who created it. The "
                "question afterwards is always who set this up, and a URL cannot answer it"
            )
            raise OutboxError(msg)

    def takes(self, kind: EventKind) -> bool:
        """Whether this subscriber receives that kind. Inactive subscribers take nothing."""
        return self.active and kind in self.kinds


def assert_deliverable(subscriber: Subscriber, resolver: Resolver) -> Fetchable:
    """Refuse a subscriber endpoint that would make this server connect somewhere internal.

    Delegated whole to `brain.tools.fetch.assert_fetchable`, which already holds the rule and
    was written against what "inside" means rather than against known-bad hosts: https only,
    no credentials in the URL, no unbracketed IPv6 authority, and no address in a range that
    only means "on this network", checked over every answer the resolver gives rather than
    the first. A second copy here would be the one that misses `[::ffff:169.254.169.254]`.

    Re-raised as an `OutboxError` rather than passed through, the way
    `brain.gate.invoke.invoke` re-raises an empty catalogue: the caller is registering or
    delivering a webhook and needs to distinguish "this subscription is wrong" from "the
    skill importer is broken". The original is chained, so the specific rule that refused it
    is still in the traceback.

    Called per delivery. See `A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY`.
    """
    try:
        return assert_fetchable(subscriber.endpoint, resolver)
    except UnsafeAddressError as exc:
        msg = (
            f"subscriber {subscriber.subscriber_id!r} may not be delivered to: {exc}. The "
            "wording is the skill importer's because the address rule is written once, in "
            "brain.tools.fetch, and this is the same rule rather than a second copy of it"
        )
        raise OutboxError(msg) from exc


# --------------------------------------------------------------- signing (M17.5.2)
#: The header carrying the send time, in whole seconds since the epoch. Inside the signed
#: material, so a modified one fails verification rather than merely disagreeing.
TIMESTAMP_HEADER: Final = "X-Brain-Timestamp"

#: The header carrying the signature. Hex, lower case, the whole of a SHA-256 HMAC.
SIGNATURE_HEADER: Final = "X-Brain-Signature"

#: What the receiver's window should be, if they ask. The same figure
#: `brain.channels.webhook` refuses inbound requests outside, because it is the same
#: construction in the other direction and two different windows would be two different
#: answers to "how long is a captured signature useful for".
SUGGESTED_RECEIVER_WINDOW: Final = DEFAULT_WINDOW


@dataclass(frozen=True)
class SignedRequest:
    """Everything needed to send one attempt, and nothing that could send it.

    No client, for the reason `brain.ops.limits` holds no Valkey connection: what is signed
    and what the receiver has to check are the parts that are ever wrong, and neither can be
    tested through a module that opens a socket.

    `address` is carried beside `url` because the two are not interchangeable. The address is
    what passed the check; connecting by name reopens the hole. `brain.tools.fetch.Fetchable`
    makes the same point at greater length and cannot enforce it either.
    """

    url: str
    address: str
    headers: Mapping[str, str]
    body: bytes


def signature_for(*, secret: str, sent_at: datetime, body: bytes) -> str:
    """The signature for these exact bytes at this exact moment.

    Delegated to `brain.channels.webhook.sign`, which is the one definition in this
    repository of what a signature covers. Inbound verification and outbound signing are the
    same construction, and two copies of it drift into a signature that verifies on one side
    only, discovered by a subscriber rather than by a test.
    """
    return sign(secret, _epoch_seconds(sent_at), bytes(body))


def signature_matches(expected: str, presented: str) -> bool:
    """Whether a presented signature is the one we would have produced. Constant time.

    `hmac.compare_digest` rather than `==`, and this exists as a function so that nobody
    writes the `==`. A normal comparison returns as soon as two bytes differ, so the time it
    takes says how much of a guess was right, and a few thousand requests turn that into the
    signature. `brain.channels.webhook.verify` makes the same call for inbound requests; this
    is for anything on this side that has to check one of ours, such as a round-trip test
    from the console against its own endpoint.
    """
    return hmac.compare_digest(expected, presented)


def _epoch_seconds(moment: datetime) -> str:
    """Whole seconds since the epoch, as text, which is what is signed.

    Whole seconds rather than a float: the value is inside the signed material and is
    reproduced by the receiver from the header, so any rendering that could differ by a
    trailing zero is a signature that fails for no reason anybody can see.
    """
    if moment.tzinfo is None:
        # A naive send time is a different instant on two hosts, and the receiver's window
        # check is a comparison against it.
        msg = "the signed timestamp has no timezone, so it names a different instant per host"
        raise OutboxError(msg)
    return str(int(moment.timestamp()))


def signed_request(
    *,
    event: OutboxEvent,
    subscriber: Subscriber,
    secret: str,
    sent_at: datetime,
    target: Fetchable,
) -> SignedRequest:
    """One attempt, signed and ready for something else to send.

    `target` is a `Fetchable` rather than a URL, so a request cannot be built without the
    address rule having run for this delivery. That is the structural half of
    `A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY`: there is no path to a `SignedRequest`
    that skips the check, because the check is what produces the only type this accepts.

    The target has to be the subscriber's own endpoint. A `Fetchable` for a different URL is a
    check made against something else, which is exactly as useful as no check.

    **There is no event-id header**, deliberately, although one would save the receiver a
    parse. An identifier in an unsigned header is a second copy of a signed value, and a
    subscriber that deduplicates on the unsigned copy is deduplicating on something the
    sender does not vouch for. The id is in the body, inside the signature, and the receiver
    reads it after verifying. See `RECEIVER_MUST_CHECK`.

    `secret` is a value and it is a parameter. It is borrowed for the duration of one call
    through `brain.ops.secrets.borrow`, which revokes in a `finally`; nothing in this module
    holds it, which is the property `brain.connectors.contract.assert_holds_no_credential`
    checks connectors for and the reason rotation needs no redeploy.
    """
    if target.url != subscriber.endpoint:
        msg = (
            f"the checked address is for {target.url!r} and subscriber "
            f"{subscriber.subscriber_id!r} is at {subscriber.endpoint!r}; an address rule "
            "that ran against another URL has not run against this one"
        )
        raise OutboxError(msg)
    if not subscriber.takes(event.kind):
        msg = (
            f"subscriber {subscriber.subscriber_id!r} does not take {event.kind}; it takes "
            f"{[k.value for k in subscriber.kinds]} and active is {subscriber.active}. "
            "Signing it anyway would send an event nobody subscribed to"
        )
        raise OutboxError(msg)
    body = serialise(event)
    return SignedRequest(
        url=subscriber.endpoint,
        address=target.address,
        headers=MappingProxyType(
            {
                TIMESTAMP_HEADER: _epoch_seconds(sent_at),
                # Through `signature_for` rather than calling `sign` again here. Two call
                # sites for what is signed is how the header and the signature come to be
                # computed over different renderings of one moment, which fails on the
                # receiver's side and reads there as a wrong shared secret.
                SIGNATURE_HEADER: signature_for(secret=secret, sent_at=sent_at, body=body),
            }
        ),
        body=body,
    )


# ------------------------------------------------------- retry and backoff (M17.5.1)
class DeliveryState(enum.StrEnum):
    """Where one event's delivery to one subscriber has got to.

    Three, and there is deliberately no `UNKNOWN` here although
    `brain.ops.idempotency.OperationState` has one. The difference is the guarantee. That
    machine promises exactly-once, so not knowing whether a side effect landed has to be a
    state nobody can leave except by asking. This one promises at-least-once, so not knowing
    whether the subscriber processed a request has an answer already: send it again, and the
    subscriber drops the duplicate on the event id.
    """

    #: Not yet accepted. Either never attempted or waiting for the next one.
    PENDING = "pending"
    #: The subscriber answered with a success status.
    DELIVERED = "delivered"
    #: Out of attempts, or refused in a way that repeating cannot change. A person decides.
    EXHAUSTED = "exhausted"


#: How many attempts one delivery gets. Two properties fix it rather than taste, and both are
#: anchored outside this module. It has to exceed
#: `brain.ops.limits.BACKOFF_AFTER_REFUSALS`, or the doubling never engages and the "backoff"
#: in "retry and backoff" is decorative. And the resulting window has to exceed
#: `MAX_BACKOFF_SECONDS`, or the cap expires inside a single wait and the last attempt is one
#: the worker never makes. Eight is the round number comfortably past both, and gives a
#: subscriber roughly half an hour of being down without losing an event.
MAX_DELIVERY_ATTEMPTS: Final = 8


def retry_window_seconds() -> float:
    """The longest a delivery can be retried over, in the worst case.

    Worst case because every wait is at the ceiling: a subscriber that returns nothing states
    no `Retry-After`, and `brain.connectors.throttle.RETRY_AFTER_WHEN_UNSTATED` deliberately
    substitutes the long end for it. Attempts minus one, because the first attempt is not
    preceded by a wait.
    """
    return (MAX_DELIVERY_ATTEMPTS - 1) * MAX_BACKOFF_SECONDS


@dataclass(frozen=True)
class Delivery:
    """One event's journey to one subscriber. The row a worker picks up.

    Separate from the event, so that one event to twelve subscribers is twelve rows that fail
    independently. Sharing a row would mean one subscriber being down holds up the other
    eleven, and would make "which of them got it" unanswerable.
    """

    event_id: str
    subscriber_id: str
    attempts: int = 0
    state: DeliveryState = DeliveryState.PENDING

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.subscriber_id.strip():
            msg = (
                "a delivery names one event and one subscriber; a row missing either is unroutable"
            )
            raise OutboxError(msg)
        if self.attempts < 0:
            msg = f"delivery of {self.event_id!r} reports {self.attempts} attempts"
            raise OutboxError(msg)


@dataclass(frozen=True)
class Attempt:
    """What one attempt's outcome did to the delivery, and when to come back.

    Carries the updated row rather than instructions for producing one. A function that
    returned "retry in 300 seconds" and left the caller to increment the attempt count is a
    function whose caller eventually forgets, and a delivery whose count never rises retries
    for ever.
    """

    delivery: Delivery
    delay_seconds: float
    reason: str

    @property
    def deliver_again(self) -> bool:
        return self.delivery.state is DeliveryState.PENDING


def plan_next(
    delivery: Delivery,
    outcome: CallOutcome,
    *,
    retry_after_seconds: float | None = None,
    jitter: float = 0.0,
) -> Attempt:
    """What happens to this delivery after one attempt came back with that outcome.

    The outcome classification is `brain.connectors.throttle.classify`'s, and whether it is
    worth another go is `is_retryable`'s. **What is deliberately not passed to `is_retryable`
    is a side effect**, and that is not an oversight worth hiding. That function refuses to
    retry a side-effecting call whose connector cannot read back, because a retry either
    repeats the action or loses it and nothing can tell which. A webhook delivery is a send,
    so it fails that rule on its face, and it is retried anyway because the read-back is
    replaced by something else: the subscriber's contractual duty to deduplicate on the event
    id. That is the substitution, stated rather than sneaked past. See
    `DELIVERY_IS_AT_LEAST_ONCE`.

    A `REJECTED` outcome exhausts immediately rather than counting an attempt against the
    cap. A 404 or a 410 from a subscriber will be a 404 or a 410 eight more times, at full
    cost, and a subscriber that has been deleted should reach a person today rather than in
    thirty-five minutes.

    The wait is `brain.connectors.throttle.retry_delay`, whole, including the case that gets
    missed: `retry_after_seconds` is `float | None` and a subscriber that stated nothing is
    not a subscriber that said zero.
    """
    if delivery.state is not DeliveryState.PENDING:
        msg = (
            f"delivery of {delivery.event_id!r} to {delivery.subscriber_id!r} is "
            f"{delivery.state} and was attempted again. A delivered event sent twice is a "
            "duplicate this side caused, which is the one kind the subscriber cannot be "
            "asked to absorb"
        )
        raise OutboxError(msg)

    attempted = replace(delivery, attempts=delivery.attempts + 1)
    if outcome is CallOutcome.OK:
        return Attempt(
            delivery=replace(attempted, state=DeliveryState.DELIVERED),
            delay_seconds=0.0,
            reason=f"accepted on attempt {attempted.attempts}",
        )
    if not is_retryable(outcome):
        return Attempt(
            delivery=replace(attempted, state=DeliveryState.EXHAUSTED),
            delay_seconds=0.0,
            reason=(
                f"the subscriber refused with {outcome}, which repeating reproduces exactly "
                "and at full cost; this needs somebody to look at the subscription"
            ),
        )
    if attempted.attempts >= MAX_DELIVERY_ATTEMPTS:
        return Attempt(
            delivery=replace(attempted, state=DeliveryState.EXHAUSTED),
            delay_seconds=0.0,
            reason=(
                f"{attempted.attempts} attempts over up to {retry_window_seconds():.0f}s and "
                "the subscriber has not accepted it. Parked rather than dropped: an event "
                "nobody was told about and nothing recorded is the failure an outbox exists "
                "to prevent"
            ),
        )
    delay = retry_delay(
        retry_after_seconds=retry_after_seconds,
        consecutive_refusals=attempted.attempts,
        jitter=jitter,
    )
    return Attempt(
        delivery=attempted,
        delay_seconds=delay,
        reason=(
            f"attempt {attempted.attempts} of {MAX_DELIVERY_ATTEMPTS} came back {outcome}; "
            f"next in {delay:.0f}s"
        ),
    )


def deliveries_for(event: OutboxEvent, subscribers: Iterable[Subscriber]) -> tuple[Delivery, ...]:
    """One row per subscriber that takes this kind, in subscriber order.

    Written with the event, in the same transaction, so that a worker crashing between the
    event row and the delivery rows cannot leave an event nobody is scheduled to receive.
    Ordered by subscriber id so two runs of the same fan-out produce the same rows and a diff
    of the plan is a diff of the decision, which is the argument
    `brain.ops.queue.worker_shards` makes about its own ordering.
    """
    return tuple(
        Delivery(event_id=event.event_id, subscriber_id=s.subscriber_id)
        for s in sorted(subscribers, key=lambda s: s.subscriber_id)
        if s.takes(event.kind)
    )


def backoff_is_engaged() -> bool:
    """Whether the attempt cap leaves room for the doubling to happen at all.

    A function rather than a comment, so the property `MAX_DELIVERY_ATTEMPTS` was chosen for
    can be asserted instead of believed. `brain.ops.limits.backoff_seconds` hands back the
    measured wait for the first `BACKOFF_AFTER_REFUSALS` refusals and only doubles after
    that, so a cap at or below that number is a retry policy with no backoff in it and a
    docstring that says there is.
    """
    return MAX_DELIVERY_ATTEMPTS > BACKOFF_AFTER_REFUSALS


def subscriber_gaps(subscribers: Sequence[Subscriber]) -> tuple[str, ...]:
    """Everything wrong with a set of subscriptions that no single row can see.

    A console screen would show this, and it is the half of M17.5.3 that can exist without
    one. Two findings, and both are invisible from inside a `Subscriber`: two rows pointing
    at the same endpoint, which delivers everything twice to somebody who will report it as
    our bug; and a kind nobody takes, which is not an error but is the thing an operator
    wants to know before they go looking for why an integration is quiet.

    Returns findings rather than raising, the way every other gap function in this package
    does: a configuration with two problems should show both, because fixing one leaves a
    setup that is still wrong and raises nothing.
    """
    findings: list[str] = []
    endpoints: dict[str, list[str]] = {}
    for subscriber in subscribers:
        if subscriber.active:
            endpoints.setdefault(subscriber.endpoint, []).append(subscriber.subscriber_id)
    for endpoint, owners in sorted(endpoints.items()):
        if len(owners) > 1:
            findings.append(
                f"{sorted(owners)} all deliver to {endpoint}, so it receives every matching "
                "event once per subscription. Deduplication is on the event id and these are "
                "the same event, so the receiver drops the copies and reports us as flapping"
            )
    taken = {kind for s in subscribers if s.active for kind in s.kinds}
    for kind in EventKind:
        if kind not in taken:
            findings.append(
                f"nothing takes {kind.value}; events of that kind are written and never "
                "delivered, which is a quiet integration rather than a failing one"
            )
    return tuple(findings)
