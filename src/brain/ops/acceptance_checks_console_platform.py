"""Install acceptance checks for the platform screens an administrator changes things on.

Each check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`), over
the check's own transaction, so **nothing it writes is kept and nothing it does reaches a person**.

**A delivery is made up inside the transaction and never sent.** Replaying a delivery puts it
back to pending for the worker, which reads committed rows only. The check's rows are never
committed, so the worker cannot see the delivery it replays and nothing is sent to any address.
See `A_REPLAYED_DELIVERY_IS_THE_CHECKS_AND_THE_WORKER_NEVER_SEES_IT`.

Task ids: M27.15.44
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Final

from sqlalchemy import select, update

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, traced
from brain.ops.acceptance_operations_console_5 import (
    MANAGES_SUBSCRIBERS,
    WEBHOOK_ENDPOINT,
    KeptNowhere,
    subscriber_id_for,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 920

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why replaying a delivery the check made up sends nothing.
A_REPLAYED_DELIVERY_IS_THE_CHECKS_AND_THE_WORKER_NEVER_SEES_IT: Final = (
    "Replaying puts a given-up delivery back to pending, due now, for the worker to send. The "
    "delivery and the subscriber are rows of the check's own transaction, which is rolled back, "
    "and the worker reads committed rows only, so the replay is proved to reach the row and "
    "nothing is sent to the address the subscriber names."
)


# ------------------------------------------------------- 1. webhooks (M27.15.44)
@check(
    leaves=("M27.15.44",),
    sentence=(
        "A webhook subscriber switched off is switched back on from the console as a change on "
        "the record under the administrator's name, and a delivery that was given up is "
        "replayed from the console once: it goes back to pending, a second replay of it is "
        "refused, and a person who may not manage subscribers is refused both."
    ),
)
async def a_subscriber_is_switched_on_again_and_a_delivery_replayed_once(
    h: Harness,
) -> None:
    from brain.ops.outbox import MAX_DELIVERY_ATTEMPTS, DeliveryState, EventKind, OutboxEvent
    from brain.ops.outbox_store import record_event, subscribers
    from brain.ops.webhook_store import replay_handle
    from brain.tables.outbox import OutboxDeliveryRow
    from brain.tables.webhook_change import WebhookChangeRow
    from brain.webhook_routes import RegistrationAsked, register, replay, switch_off, switch_on

    await h.found_departments()
    admin, other = h.principal(A, "webhooks"), h.principal(A, "other")
    await h.person(admin, department=A, grants=((MANAGES_SUBSCRIBERS, Scope.unrestricted()),))
    await h.person(other, department=A)
    console = console_for(h)
    console.app.state.signing_secrets = KeptNowhere()
    subscriber, kind = subscriber_id_for(h), next(iter(EventKind))
    managing = await asking_as(h, admin, strong=True)

    async with traced(h, 1):
        registered = await register(
            console.request("POST"),
            RegistrationAsked(
                subscriber_id=subscriber,
                endpoint=WEBHOOK_ENDPOINT,
                kinds=[kind.value],
                secret=secrets.token_urlsafe(32),
            ),
            managing,
        )
    if registered.status_code != 200:
        raise CheckFailedError("a subscriber could not be registered from the console")

    if not await refused(switch_on(console.request("POST"), subscriber, managing)):
        raise CheckFailedError("a subscriber that was on was switched on again")
    async with traced(h, 2):
        await switch_off(console.request("POST"), subscriber, managing)
    stranger = await asking_as(h, other, strong=True)
    if not await refused(switch_on(console.request("POST"), subscriber, stranger)):
        raise CheckFailedError("a person who may not manage subscribers switched one on")
    async with traced(h, 3):
        back = await switch_on(console.request("POST"), subscriber, managing)
    if back.change.value != "switched_on":
        raise CheckFailedError("switching a subscriber back on did not say it was a switch on")
    changes = (
        await h.execute(
            select(WebhookChangeRow.change, WebhookChangeRow.changed_by)
            .where(WebhookChangeRow.subscriber_id == subscriber)
            .order_by(WebhookChangeRow.changed_at)
        )
    ).all()
    if [(one[0], one[1]) for one in changes][-2:] != [
        ("switched_off", admin),
        ("switched_on", admin),
    ]:
        raise CheckFailedError("the switch off and the switch on are not on the record under who")

    event = OutboxEvent(
        event_id=f"acceptance-{h.run}-event",
        kind=kind,
        entity="acceptance",
        record_id=f"acceptance-{h.run}",
        occurred_at=h.now - timedelta(minutes=1),
    )
    async with h.sessions() as session:
        mine = tuple(one for one in await subscribers(session) if one.subscriber_id == subscriber)
        made = await record_event(session, event, mine)
        await session.execute(
            update(OutboxDeliveryRow)
            .where(
                OutboxDeliveryRow.event_id == event.event_id,
                OutboxDeliveryRow.subscriber_id == subscriber,
            )
            .values(
                state=DeliveryState.EXHAUSTED.value,
                attempts=MAX_DELIVERY_ATTEMPTS,
                last_attempt_at=h.now - timedelta(seconds=30),
            )
        )
        await session.commit()
    if len(made) != 1:
        raise CheckFailedError("the subscriber, switched back on, was not given the event")
    handle = replay_handle(event.event_id, subscriber)

    if not await refused(replay(console.request("POST"), subscriber, handle, stranger)):
        raise CheckFailedError("a person who may not manage subscribers replayed a delivery")
    async with traced(h, 4):
        replayed = await replay(console.request("POST"), subscriber, handle, managing)
    if replayed.change.value != "replayed":
        raise CheckFailedError("replaying a delivery did not say it was a replay")
    state = (
        await h.execute(
            select(OutboxDeliveryRow.state).where(
                OutboxDeliveryRow.event_id == event.event_id,
                OutboxDeliveryRow.subscriber_id == subscriber,
            )
        )
    ).scalar_one()
    if state != DeliveryState.PENDING.value:
        raise CheckFailedError("a replayed delivery was not put back to pending")
    if not await refused(replay(console.request("POST"), subscriber, handle, managing)):
        raise CheckFailedError("a delivery that had been replayed was replayed again")
