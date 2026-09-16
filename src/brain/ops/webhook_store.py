"""The rows behind the Webhooks screen: what is registered, what happened to each, and three writes.

`brain.ops.outbox_store` owns the subscriber, event and delivery tables and already writes a
registration and a deactivation. This is the console's half over the same tables and
`ops.webhook_change`, and it re-decides nothing: who may do any of this is
`brain.ops.outbox.may_manage`, asked by `brain.webhook_routes` before this is reached, and what a
registration must be is `brain.ops.webhook_admin`, judged before this is called.

**Each write is one transaction, and the vault is written inside it.** A registration inserts the
subscriber, then writes its secret, then records the change, and commits; a rotation locks the
active row, writes the secret, records the change and commits. A vault that refuses or does not
answer raises inside the transaction, so no subscriber is left registered with no secret and no
rotation is recorded that did not happen. See `THE_VAULT_IS_WRITTEN_WHILE_THE_ROW_IS_HELD`.

**Every change is recorded with who made it, and reaches the hash-chained ledger.** Each write
leaves an `ops.webhook_change` row in its own transaction, and the request's trace and the writer's
reach digest are set as transaction settings beside it, where `0059`'s trigger reads them into the
`webhook` entry it appends. See `A_CHANGE_IS_ATTRIBUTED_HERE_AND_CHAINED_BY_A_TRIGGER`.

**The price, stated.** The transaction is held open for as long as the vault takes to answer, which
`brain.ops.openbao.TIMEOUT_SECONDS` bounds at five seconds. And a commit that fails after the vault
accepted leaves a secret at a path no subscriber names; registering that id again replaces it,
because the path is the id.

**What the dispatcher last did is read beside them, from the schedule's own record.** The worker
writes a row in `ops.control_run` for every run of `outbox_dispatch`, and the newest is what the
screen says about delivery as a whole: when it last ran, how it ended, and whether a person has
paused it. No second record of a run is kept here, because two records of one run are two answers
to whether it happened.

**Recent outcomes are read per subscriber, newest first, a few each.** A window function numbers
each subscriber's deliveries, so one subscriber with a thousand parked deliveries does not crowd
every other subscriber off the screen. No event's record id is read: what a delivery was about is
an identifier of a company record, and the screen needs the kind and the outcome.

Task ids: M27.8.12
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.outbox import DeliveryState, EventKind, Subscriber
from brain.ops.outbox_store import (
    OutboxStoreError,
    deactivate_subscriber,
    last_delivered,
    register_subscriber,
    subscriber_from,
)
from brain.ops.schedule_control import paused_controls
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.outbox import OutboxDeliveryRow, OutboxEventRow, WebhookSubscriberRow
from brain.tables.schedule import ControlRunRow
from brain.tables.webhook_change import WebhookChange, WebhookChangeRow

# ------------------------------------------------------------ written-down reasons

#: Why the vault is written between the row and the commit.
THE_VAULT_IS_WRITTEN_WHILE_THE_ROW_IS_HELD: Final = (
    "Written before the row, a registration whose insert then failed would leave a secret at "
    "another subscriber's path, and two people registering one id at once would each overwrite "
    "the other's. Written after the commit, a vault that refused would leave a subscriber "
    "registered with no secret to sign with. Inside the transaction, after the row is inserted or "
    "locked, a second registration of the same id waits on the first and is refused, and a "
    "refusal from the vault rolls the row back."
)

#: Why a change is attributed in a table of its own and chained into the ledger from there.
A_CHANGE_IS_ATTRIBUTED_HERE_AND_CHAINED_BY_A_TRIGGER: Final = (
    "A registration, a replaced signing key and a switch-off are each an ops.webhook_change row "
    "naming who and when, written in the transaction that makes the change, and 0059's trigger "
    "on that table appends a webhook entry about the subscriber for each, so a change made by an "
    "operator's statement is chained exactly as one made here. A replaced key is not also "
    "recorded as a credential: the subscriber's change is the event an auditor of where "
    "identifiers are sent reads, and a second entry for it would be the same event twice."
)

#: How many recent deliveries and changes the screen reads for each subscriber.
RECENT_PER_SUBSCRIBER: Final = 5

#: The control whose runs are delivery, by the registry's name for it.
DISPATCH_CONTROL: Final = "outbox_dispatch"


class SubscriberTakenError(Exception):
    """A subscriber with this id is already registered, switched on or off."""


class NoActiveSubscriberError(Exception):
    """No subscriber with this id is switched on: it was never registered, or it is switched off."""


# ---------------------------------------------------------------------- the shapes


@dataclass(frozen=True)
class DeliveryLine:
    """One delivery as the screen draws it: what kind, where it got to, and why. No record id."""

    kind: EventKind
    state: str
    attempts: int
    occurred_at: datetime
    last_attempt_at: datetime | None
    reason: str | None
    #: When a pending delivery is next tried. None once it is delivered or set aside.
    next_attempt_at: datetime | None = None


@dataclass(frozen=True)
class DispatcherLine:
    """The newest run of the dispatch, as the schedule recorded it, and whether it is paused.

    Every field but `paused` is None when the dispatch has never been started on this install.
    `detail` is what the run recorded, which for a failed run begins with the exception's type.
    """

    started_at: datetime | None
    finished_at: datetime | None
    outcome: str | None
    detail: str | None
    paused: bool


@dataclass(frozen=True)
class ChangeLine:
    """One change to a subscriber: what, by whom, when, and when the vault stamped the secret."""

    change: WebhookChange
    changed_by: str
    changed_at: datetime
    secret_written_at: datetime | None


@dataclass(frozen=True)
class Registered:
    """One subscriber and everything the screen says about it beside the domain type."""

    subscriber: Subscriber
    created_at: datetime
    deactivated_at: datetime | None
    last_delivered_at: datetime | None
    deliveries: tuple[DeliveryLine, ...]
    changes: tuple[ChangeLine, ...]


@runtime_checkable
class WebhookRecords(Protocol):
    """What the Webhooks routes need from the database. `StoredWebhooks` is one."""

    async def registered(self) -> tuple[Registered, ...]:
        """Every subscriber in id order, with its recent deliveries and changes."""
        ...

    async def register(
        self,
        subscriber: Subscriber,
        *,
        actor: str,
        at: datetime,
        trace_id: str,
        ent_hash: str,
        keep_secret: Callable[[], datetime | None],
    ) -> datetime | None:
        """Write a subscriber, its secret and the change, or nothing. Returns the secret's time."""
        ...

    async def replace_secret(
        self,
        subscriber_id: str,
        *,
        actor: str,
        at: datetime,
        trace_id: str,
        ent_hash: str,
        keep_secret: Callable[[], datetime | None],
    ) -> datetime | None:
        """Write an active subscriber's new secret and the change, or nothing."""
        ...

    async def switch_off(self, subscriber_id: str, *, actor: str, at: datetime) -> None:
        """Switch an active subscriber off and record who did, or nothing."""
        ...

    async def dispatcher(self) -> DispatcherLine:
        """The newest run of the dispatch and whether a person has paused it."""
        ...


# ------------------------------------------------------------------- the statements


def _recent_deliveries(ids: Sequence[str], limit: int) -> Select[Any]:
    ranked = (
        select(
            OutboxDeliveryRow.subscriber_id,
            OutboxEventRow.kind,
            OutboxDeliveryRow.state,
            OutboxDeliveryRow.attempts,
            OutboxEventRow.occurred_at,
            OutboxDeliveryRow.last_attempt_at,
            OutboxDeliveryRow.last_reason,
            OutboxDeliveryRow.due_at,
            func.row_number()
            .over(
                partition_by=OutboxDeliveryRow.subscriber_id,
                order_by=(OutboxEventRow.occurred_at.desc(), OutboxDeliveryRow.event_id.desc()),
            )
            .label("place"),
        )
        .join(OutboxEventRow, OutboxEventRow.event_id == OutboxDeliveryRow.event_id)
        .where(OutboxDeliveryRow.subscriber_id.in_(sorted(ids)))
        .subquery()
    )
    return (
        select(ranked)
        .where(ranked.c.place <= limit)
        .order_by(ranked.c.subscriber_id, ranked.c.place)
    )


def _recent_changes(ids: Sequence[str], limit: int) -> Select[Any]:
    ranked = (
        select(
            WebhookChangeRow.subscriber_id,
            WebhookChangeRow.change,
            WebhookChangeRow.changed_by,
            WebhookChangeRow.changed_at,
            WebhookChangeRow.secret_written_at,
            func.row_number()
            .over(
                partition_by=WebhookChangeRow.subscriber_id,
                order_by=(WebhookChangeRow.changed_at.desc(), WebhookChangeRow.id.desc()),
            )
            .label("place"),
        )
        .where(WebhookChangeRow.subscriber_id.in_(sorted(ids)))
        .subquery()
    )
    return (
        select(ranked)
        .where(ranked.c.place <= limit)
        .order_by(ranked.c.subscriber_id, ranked.c.place)
    )


def _change(
    subscriber_id: str, change: WebhookChange, actor: str, at: datetime, written: datetime | None
) -> WebhookChangeRow:
    return WebhookChangeRow(
        subscriber_id=subscriber_id,
        change=change.value,
        changed_by=actor,
        changed_at=at,
        secret_written_at=written,
    )


async def _attribute(session: AsyncSession, *, trace_id: str, ent_hash: str) -> None:
    """The request's trace and the writer's reach digest, as this transaction's settings.

    Where every trigger in this schema reads them, so a trigger added to record a change in the
    ledger attributes it to the reach it was made under. See
    `A_CHANGE_IS_ATTRIBUTED_HERE_AND_CHAINED_BY_A_TRIGGER`.
    """
    await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
    await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.gate.review_store` sets the same settings for its trigger.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


# ---------------------------------------------------------------------- the store


class StoredWebhooks:
    """The subscriber, delivery, event and change tables, read and written as the console needs."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        recent: int = RECENT_PER_SUBSCRIBER,
    ) -> None:
        self._sessions = sessions
        self._recent = recent

    async def registered(self) -> tuple[Registered, ...]:
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(WebhookSubscriberRow).order_by(WebhookSubscriberRow.subscriber_id)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                return ()
            ids = [row.subscriber_id for row in rows]
            delivered = await last_delivered(session)
            deliveries: dict[str, list[DeliveryLine]] = {}
            for one in (await session.execute(_recent_deliveries(ids, self._recent))).mappings():
                deliveries.setdefault(one["subscriber_id"], []).append(
                    DeliveryLine(
                        kind=EventKind(one["kind"]),
                        state=one["state"],
                        attempts=one["attempts"],
                        occurred_at=one["occurred_at"],
                        last_attempt_at=one["last_attempt_at"],
                        reason=one["last_reason"],
                        next_attempt_at=(
                            one["due_at"] if one["state"] == DeliveryState.PENDING.value else None
                        ),
                    )
                )
            changes: dict[str, list[ChangeLine]] = {}
            for one in (await session.execute(_recent_changes(ids, self._recent))).mappings():
                changes.setdefault(one["subscriber_id"], []).append(
                    ChangeLine(
                        change=WebhookChange(one["change"]),
                        changed_by=one["changed_by"],
                        changed_at=one["changed_at"],
                        secret_written_at=one["secret_written_at"],
                    )
                )
        return tuple(
            Registered(
                subscriber=subscriber_from(row),
                created_at=row.created_at,
                deactivated_at=row.deactivated_at,
                last_delivered_at=delivered.get(row.subscriber_id),
                deliveries=tuple(deliveries.get(row.subscriber_id, ())),
                changes=tuple(changes.get(row.subscriber_id, ())),
            )
            for row in rows
        )

    async def register(
        self,
        subscriber: Subscriber,
        *,
        actor: str,
        at: datetime,
        trace_id: str,
        ent_hash: str,
        keep_secret: Callable[[], datetime | None],
    ) -> datetime | None:
        async with self._sessions() as session, session.begin():
            taken = await session.get(WebhookSubscriberRow, subscriber.subscriber_id)
            if taken is not None:
                raise SubscriberTakenError(subscriber.subscriber_id)
            try:
                await register_subscriber(session, subscriber)
            except IntegrityError as raced:
                raise SubscriberTakenError(subscriber.subscriber_id) from raced
            written = await asyncio.to_thread(keep_secret)
            await _attribute(session, trace_id=trace_id, ent_hash=ent_hash)
            session.add(
                _change(subscriber.subscriber_id, WebhookChange.REGISTERED, actor, at, written)
            )
            await session.flush()
        return written

    async def replace_secret(
        self,
        subscriber_id: str,
        *,
        actor: str,
        at: datetime,
        trace_id: str,
        ent_hash: str,
        keep_secret: Callable[[], datetime | None],
    ) -> datetime | None:
        async with self._sessions() as session, session.begin():
            held = (
                await session.execute(
                    select(WebhookSubscriberRow.subscriber_id)
                    .where(
                        WebhookSubscriberRow.subscriber_id == subscriber_id,
                        WebhookSubscriberRow.deactivated_at.is_(None),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if held is None:
                raise NoActiveSubscriberError(subscriber_id)
            written = await asyncio.to_thread(keep_secret)
            await _attribute(session, trace_id=trace_id, ent_hash=ent_hash)
            session.add(_change(subscriber_id, WebhookChange.SECRET_REPLACED, actor, at, written))
            await session.flush()
        return written

    async def switch_off(self, subscriber_id: str, *, actor: str, at: datetime) -> None:
        async with self._sessions() as session, session.begin():
            try:
                await deactivate_subscriber(session, subscriber_id, at=at)
            except OutboxStoreError as already:
                raise NoActiveSubscriberError(subscriber_id) from already
            session.add(_change(subscriber_id, WebhookChange.SWITCHED_OFF, actor, at, None))
            await session.flush()

    async def dispatcher(self) -> DispatcherLine:
        async with self._sessions() as session, session.begin():
            newest = (
                await session.execute(
                    select(
                        ControlRunRow.started_at,
                        ControlRunRow.finished_at,
                        ControlRunRow.outcome,
                        ControlRunRow.detail,
                    )
                    .where(ControlRunRow.name == DISPATCH_CONTROL)
                    .order_by(ControlRunRow.started_at.desc())
                    .limit(1)
                )
            ).first()
            paused = DISPATCH_CONTROL in await paused_controls(session)
        if newest is None:
            return DispatcherLine(None, None, None, None, paused=paused)
        started_at, finished_at, outcome, detail = newest
        return DispatcherLine(started_at, finished_at, outcome, detail, paused=paused)
