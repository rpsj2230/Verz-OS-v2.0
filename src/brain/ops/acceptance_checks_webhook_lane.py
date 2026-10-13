"""The install acceptance checks for the outbox: a delivery is retried with a growing wait, signed
so a receiver can verify it and sent once however often it is asked for, and a subscriber is
managed through the console's own store.

**The wire and the secret are stand-ins, and the rest is the install's.** What the check cannot do
is connect to a stranger's address or read the vault, so the sender answers with a status the
check chooses, the signing key is a value the check made up for this run, and the resolver says a
documentation host resolves to a public address. Everything between them is the product's own, run
against the install's database as the worker runs it: the subscriber and the event are written
through `brain.ops.webhook_store` and `brain.ops.outbox_store`, a delivery is attempted through
`attempt_one` (the address rule, the signature, `issue_once` on the install's operation ledger),
and what it did to the row is written back and read from the row. **Because the wire and the
secret are made up, M17.5.1 and M17.5.2 stay in `docs/proof-sweep-holds.json`** until the install
shows a real subscriber receiving a real delivery. See `A_RESULT_ON_A_MADE_UP_WIRE_IS_HELD`.

**Nothing is sent and nothing is kept.** The sender is a list the check reads; the subscriber, the
event, the deliveries and the changes are rows in the check's transaction, which the run rolls
back.

Task ids: M17.5.1, M17.5.2, M17.5.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness
from brain.ops.outbox import SignedRequest
from brain.ops.outbox_store import SendResult
from brain.ops.secrets import SecretRef

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2020

# ------------------------------------------------------------------ written-down reasons
#: Why the two delivery leaves are held although their check passes.
A_RESULT_ON_A_MADE_UP_WIRE_IS_HELD: Final = (
    "The check answers for the subscriber's address with a status it chose and signs with a "
    "secret it made up, so a pass shows the product's retry, signing and one-send decisions on "
    "this install's database and does not show a receiver on the internet being reached."
)

#: The address the stand-in resolver gives the documentation host, in a public range.
PUBLIC_ADDRESS: Final = "93.184.216.34"

#: How many refused attempts the backoff is asked about.
REFUSALS_ASKED: Final = 5


class _Wire:
    """A sender that records each request and answers with the status it is told to."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        self.status = status
        self.retry_after = retry_after
        self.sent: list[SignedRequest] = []

    def send(self, request: SignedRequest) -> SendResult:
        self.sent.append(request)
        return SendResult(status=self.status, retry_after_seconds=self.retry_after)


class _Resolver:
    def resolve(self, host: str) -> Sequence[str]:
        return (PUBLIC_ADDRESS,)


class _Keys:
    """The signing secret, one value made for this run."""

    def __init__(self, secret: str) -> None:
        self.secret = secret

    def signing_secret(self, ref: SecretRef) -> str:
        return self.secret


async def _row(h: Harness, event_id: str, subscriber_id: str) -> tuple[str, int, datetime]:
    """A delivery's state, attempts and due time as the database holds them."""
    row = (
        await h.execute(
            text(
                "SELECT state, attempts, due_at FROM ops.outbox_delivery"
                " WHERE event_id = :event AND subscriber_id = :subscriber"
            ).bindparams(event=event_id, subscriber=subscriber_id)
        )
    ).one()
    return str(row[0]), int(row[1]), row[2]


@check(
    leaves=("M17.5.1", "M17.5.2", "M17.5.3"),
    sentence=(
        "A subscriber registered through the console's store is written one delivery per event; "
        "a refusing receiver is retried with a wait that does not shrink, a 404 is given up and "
        "can be replayed, an accepted delivery carries a signature its receiver verifies and is "
        "sent once however often it is asked for, and the subscriber is switched off and on."
    ),
)
async def a_delivery_is_retried_signed_sent_once_and_managed(h: Harness) -> None:
    import secrets

    from brain.ops.acceptance_checks_task_lane import _InstallLedger
    from brain.ops.outbox import (
        SIGNATURE_HEADER,
        TIMESTAMP_HEADER,
        Attempt,
        Delivery,
        DeliveryState,
        EventKind,
        OutboxEvent,
        Subscriber,
        serialise,
        signature_for,
        signature_matches,
    )
    from brain.ops.outbox_store import Claimed, attempt_one, record_attempt, record_event
    from brain.ops.webhook_admin import signing_secret_ref
    from brain.ops.webhook_store import StoredWebhooks
    from brain.tables.webhook_change import WebhookChange

    await h.found_departments()
    actor = h.principal(A, "owner")
    await h.person(actor, department=A)
    reach = await h.reach(actor)
    sub_id = f"acceptance-{h.run}-hook"
    subscriber = Subscriber(
        subscriber_id=sub_id,
        endpoint="https://hooks.acceptance.example/brain",
        secret_ref=signing_secret_ref(sub_id),
        kinds=(EventKind.AUTOMATION_RUN_FINISHED,),
        created_by=actor,
    )
    store = StoredWebhooks(h.sessions)
    await store.register(
        subscriber,
        actor=actor,
        at=h.now,
        trace_id=h.trace_id,
        ent_hash=reach.ent_hash(),
        keep_secret=lambda: None,
    )

    async def written(n: int) -> OutboxEvent:
        event = OutboxEvent(
            event_id=f"acceptance-{h.run}-event-{n}",
            kind=EventKind.AUTOMATION_RUN_FINISHED,
            entity="automation_run",
            record_id=f"acceptance-run-{n}",
            occurred_at=h.now,
        )
        async with h.sessions() as session, session.begin():
            made = await record_event(session, event, [subscriber])
        if [one.subscriber_id for one in made] != [sub_id]:
            raise CheckFailedError("an event was not written one delivery to its subscriber")
        return event

    loop = asyncio.get_running_loop()
    ledger = _InstallLedger(h, loop)
    secret = secrets.token_hex(16)
    keys, resolver = _Keys(secret), _Resolver()

    async def attempted(claimed: Claimed, wire: _Wire) -> Attempt:
        return await attempt_one(
            claimed,
            now=h.now,
            sender=wire,
            signing_keys=keys,
            resolver=resolver,
            ledger=ledger,
        )

    # 1. A refusing receiver is retried, and the wait does not shrink (M17.5.1).
    first = await written(1)
    delivery = Delivery(event_id=first.event_id, subscriber_id=sub_id)
    delays: list[float] = []
    refusing = _Wire(503, retry_after=5.0)
    for _ in range(REFUSALS_ASKED):
        attempt = await attempted(Claimed(delivery, first, subscriber), refusing)
        async with h.sessions() as session, session.begin():
            await record_attempt(session, delivery, attempt, now=h.now)
        delays.append(attempt.delay_seconds)
        delivery = attempt.delivery
    state, attempts, due = await _row(h, first.event_id, sub_id)
    if state != DeliveryState.PENDING.value or attempts != REFUSALS_ASKED or due <= h.now:
        raise CheckFailedError("a refused delivery was not left pending with a later due time")
    if delays[0] <= 0 or delays != sorted(delays) or delays[-1] <= delays[0]:
        raise CheckFailedError("the wait between refused deliveries did not grow")

    # 2. An accepted delivery is signed and sent once (M17.5.2).
    second = await written(2)
    claimed = Claimed(Delivery(event_id=second.event_id, subscriber_id=sub_id), second, subscriber)
    accepting = _Wire(200)
    done = await attempted(claimed, accepting)
    async with h.sessions() as session, session.begin():
        await record_attempt(session, claimed.delivery, done, now=h.now)
    if len(accepting.sent) != 1:
        raise CheckFailedError("one attempt did not send exactly one request")
    request = accepting.sent[0]
    sent_at = datetime.fromtimestamp(int(request.headers[TIMESTAMP_HEADER]), UTC)
    if request.body != serialise(second) or not signature_matches(
        signature_for(secret=secret, sent_at=sent_at, body=request.body),
        request.headers[SIGNATURE_HEADER],
    ):
        raise CheckFailedError("a delivery was not signed so that its receiver can verify it")
    if signature_matches(
        signature_for(secret=secret + "x", sent_at=sent_at, body=request.body),
        request.headers[SIGNATURE_HEADER],
    ):
        raise CheckFailedError("a delivery's signature verified under another secret")
    await attempted(claimed, accepting)
    if len(accepting.sent) != 1:
        raise CheckFailedError("asking again for an attempt already made sent it a second time")
    if (await _row(h, second.event_id, sub_id))[0] != DeliveryState.DELIVERED.value:
        raise CheckFailedError("an accepted delivery was not recorded delivered")

    # 3. The subscriber is managed through the console's store (M17.5.3).
    third = await written(3)
    gone = Claimed(Delivery(event_id=third.event_id, subscriber_id=sub_id), third, subscriber)
    given_up = await attempted(gone, _Wire(404))
    async with h.sessions() as session, session.begin():
        await record_attempt(session, gone.delivery, given_up, now=h.now)
    if (await _row(h, third.event_id, sub_id))[0] != DeliveryState.EXHAUSTED.value:
        raise CheckFailedError("a delivery a receiver refused for good was not given up")

    ours = [one for one in await store.registered() if one.subscriber.subscriber_id == sub_id]
    if len(ours) != 1 or not ours[0].subscriber.active:
        raise CheckFailedError("a registered subscriber was not listed as switched on")
    handles = [one.replay for one in ours[0].deliveries if one.replay]
    if len(handles) != 1:
        raise CheckFailedError("a delivery that was given up was not offered for replay")
    await store.switch_off(sub_id, actor=actor, at=h.now)
    off = [one for one in await store.registered() if one.subscriber.subscriber_id == sub_id]
    if off[0].deactivated_at is None:
        raise CheckFailedError("a subscriber switched off was not listed as off")
    await store.switch_on(sub_id, actor=actor, at=h.now)
    await store.replay(sub_id, handles[0], actor=actor, at=h.now)
    if (await _row(h, third.event_id, sub_id))[0] != DeliveryState.PENDING.value:
        raise CheckFailedError("a replayed delivery was not put back to be sent")
    later = next(x for x in await store.registered() if x.subscriber.subscriber_id == sub_id)
    changes = {one.change for one in later.changes}
    if (
        not {
            WebhookChange.REGISTERED,
            WebhookChange.SWITCHED_OFF,
            WebhookChange.SWITCHED_ON,
            WebhookChange.REPLAYED,
        }
        <= changes
    ):
        raise CheckFailedError("a change to a subscriber was not recorded")
