"""Draining the outbox: claim what is due, send it, and write down what one attempt did.

`brain.ops.outbox` decides everything about a webhook that can be wrong without a network:
what an event may carry, how a request is signed, whether an address is one of ours, and what
one attempt's outcome does to a delivery. This is the half that talks to PostgreSQL, and it
re-decides none of it. Every refusal below is a call into that module, and every row written
is a value that module produced.

**The claim is `FOR UPDATE OF outbox_delivery SKIP LOCKED`, inside the transaction that sends.**
Two workers ticking together each take the rows the other has not locked and neither waits,
which is the whole of what makes a second worker add throughput rather than contention. `OF`
names the delivery table because the claim joins the event and the subscriber to build the
request, and locking those would have two workers delivering two different events to one
subscriber queue behind each other for no reason. See `TWO_WORKERS_NEVER_CLAIM_ONE_DELIVERY`.

**Rejected: a lease column with a visibility timeout**, which is how a queue without row locks
does this. It needs a figure for how long a claim may last before somebody else takes it, and
that figure is a guess wearing a number: too short and a slow subscriber is sent the same event
twice by two live workers, too long and a dead worker's claims sit unsent for the length of it.
A row lock lasts exactly as long as the worker's transaction and ends when the worker dies,
because the server rolls the transaction back. `brain.ops.schedule_store` makes the same
argument about an advisory lock and a replica that died mid-run.

**The price is a transaction held open across the requests**, and it is stated rather than
hidden. A claim of `limit` rows holds a connection for up to `limit` sends. That is why the
limit is a parameter the worker chooses and not a default chosen here: the right figure depends
on the sender's own timeout, which this module does not know.

**At least once, and the crash is where the second copy comes from.** A worker that dies after
a subscriber accepted a request and before its transaction committed has its delivery rolled
back to pending, so the next worker sends it again. That is `brain.ops.outbox.
DELIVERY_IS_AT_LEAST_ONCE` arriving through the one door it always arrives through, and the
subscriber drops it on the event id.

**A delivery refused on this side is parked, not attempted.** Two things stop a request before it
leaves: the subscriber was deactivated after the delivery was written, or its address resolves
somewhere only this network can reach. Neither is the subscriber failing, so neither counts an
attempt, and both exhaust at once with the reason on the row. See
`A_REFUSAL_ON_THIS_SIDE_IS_NOT_AN_ATTEMPT`.

**The secret is returned before the request leaves.** It is borrowed through
`brain.ops.secrets.borrow` for exactly as long as signing takes, and the lease is revoked by the
time the sender is called. A sender that hangs for its whole timeout is then holding a signed
request and no credential. See `THE_LEASE_ENDS_BEFORE_THE_REQUEST_STARTS`.

**A vault that cannot issue stops the batch.** Every delivery needs a secret, so a vault outage
is not one subscriber's problem and parking every delivery against it would exhaust a day of
events over an incident in somebody else's system. The exception propagates, the transaction
rolls back, and every claimed row is due again on the next tick.

Nothing here commits. The event and its deliveries are written in the caller's transaction,
which is `brain.ops.outbox.AN_OUTBOX_IS_A_ROW_IN_THE_SAME_TRANSACTION`, and the dispatcher's row
locks are the caller's transaction too.

Task ids: M17.5.1, M17.5.3
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Protocol, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.connectors.throttle import classify
from brain.ops.outbox import (
    Attempt,
    Delivery,
    DeliveryState,
    EventKind,
    OutboxError,
    OutboxEvent,
    SignedRequest,
    Subscriber,
    assert_deliverable,
    deliveries_for,
    plan_next,
    signed_request,
)
from brain.ops.secrets import SecretRef, Vault, VaultRole, borrow
from brain.tables.outbox import (
    REASON_CHARS,
    OutboxDeliveryRow,
    OutboxEventRow,
    WebhookSubscriberRow,
)
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why the claim skips locked rows rather than waiting on them.
TWO_WORKERS_NEVER_CLAIM_ONE_DELIVERY: Final = (
    "The claim locks the delivery rows it returns and skips any row another transaction has "
    "locked. Two workers ticking together therefore take disjoint rows and neither waits for "
    "the other, and a delivery is never in two workers' hands at once. Waiting instead would "
    "serialise every worker behind the slowest subscriber, and taking rows without a lock "
    "would send one event twice from two live workers, which is the one duplicate this side "
    "causes and the subscriber cannot tell from a retry."
)

#: Why a delivery refused before sending is exhausted without counting an attempt.
A_REFUSAL_ON_THIS_SIDE_IS_NOT_AN_ATTEMPT: Final = (
    "A subscriber deactivated after the delivery was written, and an address that resolves "
    "somewhere internal, are both stopped before a request leaves. Neither is the subscriber "
    "failing, so neither counts against the attempt cap: a console reading 'eight attempts' "
    "sends somebody to look at the subscriber's server when the refusal was ours. Both park "
    "at once, because repeating either reproduces it, and the reason goes on the row."
)

#: Why the credential is gone before the sender runs.
THE_LEASE_ENDS_BEFORE_THE_REQUEST_STARTS: Final = (
    "The shared secret is needed to compute a signature and for nothing after that. Holding the "
    "lease across the send would keep a live credential in this process for as long as a slow "
    "subscriber takes to answer, which is the longest and least predictable interval in the "
    "whole delivery. So the lease is revoked when signing ends and the sender is handed bytes "
    "and headers only."
)

#: Why a send result must say something.
A_RESULT_WITH_NO_STATUS_IS_NOT_A_SUCCESS: Final = (
    "brain.connectors.throttle.classify reads a call with no status and no failure flag as OK, "
    "which is right for a caller that always has one of the two and wrong for a sender that "
    "caught an exception and returned an empty result. That empty result would mark the "
    "delivery delivered and nobody would be told again. So a result names a status or says "
    "the request timed out or never connected, and a result that says neither is refused."
)


class OutboxStoreError(Exception):
    """A row was asked of the outbox tables in a way they cannot answer truthfully."""


# ------------------------------------------------------------------------ the sender
@dataclass(frozen=True)
class SendResult:
    """What one request did, in the terms `brain.connectors.throttle.classify` reads.

    `retry_after_seconds` is `float | None` for the reason `plan_next` gives: a subscriber that
    stated no wait is not a subscriber that said zero.
    """

    status: int | None = None
    timed_out: bool = False
    connection_failed: bool = False
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.status is None and not self.timed_out and not self.connection_failed:
            msg = (
                "a send result with no status and no failure. "
                f"{A_RESULT_WITH_NO_STATUS_IS_NOT_A_SUCCESS}"
            )
            raise OutboxStoreError(msg)


class Sender(Protocol):
    """Whatever puts a signed request on the wire. No implementation lives in this repository.

    A protocol, for the reason `brain.ops.limits` holds no socket: what is signed, what is
    claimed and what an outcome does to a row are the parts that are ever wrong, and none of
    them can be tested through something that connects. A real sender connects to
    `request.address` and sends `request.body` verbatim; `brain.ops.outbox.SignedRequest` says
    why both halves of that matter.
    """

    async def send(self, request: SignedRequest) -> SendResult: ...


# ------------------------------------------------------------- rows into domain values
def event_from(row: OutboxEventRow) -> OutboxEvent:
    """The event a row holds, through the domain type's own checks."""
    return OutboxEvent(
        event_id=row.event_id,
        kind=EventKind(row.kind),
        entity=row.entity,
        record_id=row.record_id,
        occurred_at=row.occurred_at,
        attributes=MappingProxyType(dict(row.attributes)),
    )


def subscriber_from(row: WebhookSubscriberRow) -> Subscriber:
    """The subscriber a row holds. Active exactly when it has no deactivation instant."""
    return Subscriber(
        subscriber_id=row.subscriber_id,
        endpoint=row.endpoint,
        secret_ref=SecretRef(path=row.secret_path, role=VaultRole(row.secret_role)),
        kinds=tuple(EventKind(one) for one in row.kinds),
        created_by=row.created_by,
        active=row.deactivated_at is None,
    )


def delivery_from(row: OutboxDeliveryRow) -> Delivery:
    return Delivery(
        event_id=row.event_id,
        subscriber_id=row.subscriber_id,
        attempts=row.attempts,
        state=DeliveryState(row.state),
    )


# ------------------------------------------------------------------ writing an event
async def record_event(
    session: AsyncSession, event: OutboxEvent, subscribers: Sequence[Subscriber]
) -> tuple[Delivery, ...]:
    """Write an event and one delivery per subscriber that takes it, in the caller's transaction.

    The fan-out is `brain.ops.outbox.deliveries_for`, whole. Does not commit: the caller is in
    the transaction that made the change this event describes, and committing here would open
    exactly the window an outbox exists to close.
    """
    session.add(
        OutboxEventRow(
            event_id=event.event_id,
            kind=event.kind.value,
            entity=event.entity,
            record_id=event.record_id,
            occurred_at=event.occurred_at,
            attributes=dict(event.attributes),
        )
    )
    # Flushed before the deliveries are added. The tables declare a foreign key and the models
    # declare no relationship, and the unit of work orders inserts by relationship: without
    # this flush it wrote the deliveries first and the key refused every one of them.
    await session.flush()
    deliveries = deliveries_for(event, subscribers)
    for delivery in deliveries:
        session.add(
            OutboxDeliveryRow(
                event_id=delivery.event_id,
                subscriber_id=delivery.subscriber_id,
                attempts=delivery.attempts,
                state=delivery.state.value,
            )
        )
    await session.flush()
    return deliveries


# ----------------------------------------------------------------------- the claim
@dataclass(frozen=True)
class Claimed:
    """One locked delivery, and the event and subscriber it needs to become a request."""

    delivery: Delivery
    event: OutboxEvent
    subscriber: Subscriber


async def claim_due(session: AsyncSession, *, now: datetime, limit: int) -> tuple[Claimed, ...]:
    """Lock and return up to `limit` pending deliveries that are due, oldest due first.

    See `TWO_WORKERS_NEVER_CLAIM_ONE_DELIVERY`. The locks last until the caller's transaction
    ends, which is why nothing here commits.

    Ordered by the instant a delivery fell due and then by its key, so that two runs over the
    same rows claim them in the same order and a subscriber's events leave in the order they
    became sendable. Delivery is still unordered on the far side, which is why an event carries
    `occurred_at`.
    """
    if limit < 1:
        msg = f"a claim of {limit} rows claims nothing and holds a transaction open to do it"
        raise OutboxStoreError(msg)
    if now.tzinfo is None:
        msg = "a naive instant compares wrongly against every due_at in the table"
        raise OutboxStoreError(msg)
    statement = (
        select(OutboxDeliveryRow, OutboxEventRow, WebhookSubscriberRow)
        .join(OutboxEventRow, OutboxEventRow.event_id == OutboxDeliveryRow.event_id)
        .join(
            WebhookSubscriberRow,
            WebhookSubscriberRow.subscriber_id == OutboxDeliveryRow.subscriber_id,
        )
        .where(
            OutboxDeliveryRow.state == DeliveryState.PENDING.value,
            OutboxDeliveryRow.due_at <= now,
        )
        .order_by(
            OutboxDeliveryRow.due_at,
            OutboxDeliveryRow.event_id,
            OutboxDeliveryRow.subscriber_id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True, of=OutboxDeliveryRow)
    )
    rows = (await session.execute(statement)).all()
    return tuple(
        Claimed(
            delivery=delivery_from(delivery),
            event=event_from(event),
            subscriber=subscriber_from(subscriber),
        )
        for delivery, event, subscriber in rows
    )


# ------------------------------------------------------------------- one attempt
def parked(delivery: Delivery, reason: str) -> Attempt:
    """A delivery stopped on this side: exhausted, with no attempt counted.

    See `A_REFUSAL_ON_THIS_SIDE_IS_NOT_AN_ATTEMPT`.
    """
    return Attempt(
        delivery=replace(delivery, state=DeliveryState.EXHAUSTED),
        delay_seconds=0.0,
        reason=reason,
    )


async def attempt_one(
    claimed: Claimed,
    *,
    now: datetime,
    sender: Sender,
    vault: Vault,
    resolver: Resolver,
    jitter: float = 0.0,
) -> Attempt:
    """Everything one claimed delivery goes through, ending in what to write on its row.

    The order is the rule. Whether the subscriber still takes this kind, then whether its
    address is one this server may connect to, then the signature with a borrowed secret, then
    the send, then `plan_next`. Every step that can refuse runs before the one that cannot be
    taken back.
    """
    if not claimed.subscriber.takes(claimed.event.kind):
        return parked(
            claimed.delivery,
            f"subscriber {claimed.subscriber.subscriber_id!r} no longer takes "
            f"{claimed.event.kind.value}; it was deactivated or changed after this delivery "
            "was written, so nothing was sent",
        )
    try:
        target = assert_deliverable(claimed.subscriber, resolver)
    except OutboxError as exc:
        return parked(claimed.delivery, f"not sent: {exc}")
    with borrow(vault, claimed.subscriber.secret_ref, now=now) as lease:
        request = signed_request(
            event=claimed.event,
            subscriber=claimed.subscriber,
            secret=lease.secret,
            sent_at=now,
            target=target,
        )
    result = await sender.send(request)
    outcome = classify(
        status=result.status,
        timed_out=result.timed_out,
        connection_failed=result.connection_failed,
    )
    return plan_next(
        claimed.delivery,
        outcome,
        retry_after_seconds=result.retry_after_seconds,
        jitter=jitter,
    )


async def record_attempt(
    session: AsyncSession, before: Delivery, attempt: Attempt, *, now: datetime
) -> None:
    """Write what one attempt did to the row it was claimed from.

    The WHERE clause names the state and the attempt count the row was claimed at, so a row
    somebody else moved in between is refused rather than overwritten. The lock makes that
    impossible for a well-behaved worker; the clause is what makes it loud for any other.

    `last_attempt_at` moves only when the count did. A parked delivery was never attempted,
    and writing an instant on it would make the console say when a request was sent that
    never was.
    """
    values: dict[str, Any] = {
        "attempts": attempt.delivery.attempts,
        "state": attempt.delivery.state.value,
        "due_at": now + timedelta(seconds=attempt.delay_seconds),
        "last_reason": attempt.reason[:REASON_CHARS],
    }
    if attempt.delivery.attempts > before.attempts:
        values["last_attempt_at"] = now
    # `CursorResult` rather than `Result`, which is what an UPDATE returns and is the only one
    # carrying `rowcount`. Cast at a library boundary where proving the match buys nothing.
    changed = cast(
        "CursorResult[Any]",
        await session.execute(
            update(OutboxDeliveryRow)
            .where(
                OutboxDeliveryRow.event_id == before.event_id,
                OutboxDeliveryRow.subscriber_id == before.subscriber_id,
                OutboxDeliveryRow.state == DeliveryState.PENDING.value,
                OutboxDeliveryRow.attempts == before.attempts,
            )
            .values(**values)
        ),
    )
    if changed.rowcount != 1:
        msg = (
            f"delivery of {before.event_id!r} to {before.subscriber_id!r} is no longer pending "
            f"at {before.attempts} attempts, so something moved it while this worker held it"
        )
        raise OutboxStoreError(msg)


async def dispatch_due(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
    sender: Sender,
    vault: Vault,
    resolver: Resolver,
    jitter: float = 0.0,
) -> tuple[Attempt, ...]:
    """Claim what is due, attempt each, and record each. One batch, in the caller's transaction."""
    settled: list[Attempt] = []
    for claimed in await claim_due(session, now=now, limit=limit):
        attempt = await attempt_one(
            claimed, now=now, sender=sender, vault=vault, resolver=resolver, jitter=jitter
        )
        await record_attempt(session, claimed.delivery, attempt, now=now)
        settled.append(attempt)
    return tuple(settled)


# ---------------------------------------------------------- subscribers (M17.5.3)
async def register_subscriber(session: AsyncSession, subscriber: Subscriber) -> None:
    """Write a new subscriber. Refuses one that arrives switched off.

    An inactive subscriber on registration is a row that reads in the console as a
    subscription and receives nothing, which `brain.ops.outbox.Subscriber` refuses in its
    other spelling, a subscriber with no kinds. The insert policy refuses it too.
    """
    if not subscriber.active:
        msg = (
            f"subscriber {subscriber.subscriber_id!r} is being registered switched off; register "
            "it when it should receive something"
        )
        raise OutboxStoreError(msg)
    session.add(
        WebhookSubscriberRow(
            subscriber_id=subscriber.subscriber_id,
            endpoint=subscriber.endpoint,
            secret_path=subscriber.secret_ref.path,
            secret_role=subscriber.secret_ref.role.value,
            kinds=[kind.value for kind in subscriber.kinds],
            created_by=subscriber.created_by,
        )
    )
    await session.flush()


async def deactivate_subscriber(session: AsyncSession, subscriber_id: str, *, at: datetime) -> None:
    """Switch a subscriber off, once. A second deactivation is refused rather than repeated.

    Refused because the instant is the record of when it stopped, and overwriting it would
    move that record to whoever clicked second.
    """
    changed = cast(
        "CursorResult[Any]",
        await session.execute(
            update(WebhookSubscriberRow)
            .where(
                WebhookSubscriberRow.subscriber_id == subscriber_id,
                WebhookSubscriberRow.deactivated_at.is_(None),
            )
            .values(deactivated_at=at)
        ),
    )
    if changed.rowcount != 1:
        msg = f"subscriber {subscriber_id!r} is not an active subscriber"
        raise OutboxStoreError(msg)


async def subscribers(session: AsyncSession) -> tuple[Subscriber, ...]:
    """Every subscriber, active or not, in id order."""
    rows = await session.execute(
        select(WebhookSubscriberRow).order_by(WebhookSubscriberRow.subscriber_id)
    )
    return tuple(subscriber_from(row) for row in rows.scalars().all())


async def last_delivered(session: AsyncSession) -> dict[str, datetime]:
    """When each subscriber last accepted a delivery, for the ones that ever have.

    Delivered only. An attempt that failed is not a delivery, and a console column reading
    "last delivered" over a failed attempt is the quiet integration looking healthy.
    """
    rows = await session.execute(
        select(
            OutboxDeliveryRow.subscriber_id,
            func.max(OutboxDeliveryRow.last_attempt_at),
        )
        .where(OutboxDeliveryRow.state == DeliveryState.DELIVERED.value)
        .group_by(OutboxDeliveryRow.subscriber_id)
    )
    return {subscriber: at for subscriber, at in rows.all() if at is not None}
