"""Webhook subscribers in the console: what an administrator sees, and what they may change.

`brain.ops.outbox` named the capability and said what the screen would hold: "list
subscribers, show which kinds each takes and when it last delivered, and offer create,
deactivate and rotate-the-secret". This module is that screen's decisions, and like every
console module it writes nothing. `brain.ops.outbox_store` holds the rows.

**One capability decides the whole surface, and a reader without it is shown nothing.** Not a
greyed list and not a count: a subscriber is an endpoint outside the company that is told
whenever something happens here, and the list of them is a map of where the company's
identifiers go. A reader who may not manage subscribers gets an empty tuple from every read,
which is also what an install with no subscribers gets. See
`A_READER_WHO_MAY_NOT_MANAGE_IS_SHOWN_WHAT_AN_EMPTY_INSTALL_SHOWS`.

**The line carries no vault path.** A `SecretRef` is safe in a database row, and that is a
statement about who can use it rather than about who should read it: the paths are the shape of
the company's vault, and nothing an administrator does on this screen needs one. See
`A_SUBSCRIBER_LINE_CARRIES_NO_VAULT_PATH`.

**Who registered a subscriber is the reader, and it cannot be typed.** `registration` takes the
reader's entitlement and writes their principal id into `created_by`, so the question asked after
a client's identifiers turn up somewhere unexpected has an answer nobody chose.

**Rotating the secret is not here, and not because it was forgotten.** `brain.ops.outbox.
Subscriber` holds a reference, and rotation replaces what the vault holds at that path. No row
changes and there is nothing for this module to decide; the screen's rotate button is a vault
operation behind the same capability.

**Deactivation is one way.** Switching a subscriber back on is registering it again under a new
id, with the reader's name on it, because a subscription that was off for a month and is on
again is a new decision about where data goes.

Task ids: M17.5.3
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from brain.core.entitlement import EntitlementSet
from brain.ops.outbox import EventKind, Subscriber, may_manage, subscriber_gaps
from brain.ops.secrets import SecretRef

#: Why a reader without the capability sees nothing rather than a restricted list.
A_READER_WHO_MAY_NOT_MANAGE_IS_SHOWN_WHAT_AN_EMPTY_INSTALL_SHOWS: Final = (
    "A subscriber is an endpoint outside the company that is told whenever something happens "
    "here, so the list is a map of where the company's identifiers go. A reader who may not "
    "manage subscriptions is given the empty answer an install with none gives, and no count, "
    "because 'there are subscribers you may not see' is itself the fact being withheld."
)

#: Why a line on the screen omits the secret reference.
A_SUBSCRIBER_LINE_CARRIES_NO_VAULT_PATH: Final = (
    "A secret reference is safe in a row because it is useless without the vault. It is still "
    "the shape of the vault, and nothing an administrator does on this screen needs it: "
    "rotation happens at the path without anybody reading it off a page."
)

#: The one sentence a refused change gets. Nothing interpolated, so it cannot vary with what
#: was refused, following `brain.plugins.lifecycle.PLUGIN_NOT_AVAILABLE`.
NOT_AVAILABLE: Final = "subscriber management is not available here"


class SubscriberConsoleError(Exception):
    """A change was asked for that this reader may not make, or that means nothing."""


@dataclass(frozen=True)
class SubscriberLine:
    """One subscriber as the screen draws it. No secret reference: see the module docstring."""

    subscriber_id: str
    endpoint: str
    kinds: tuple[str, ...]
    active: bool
    created_by: str
    last_delivered_at: datetime | None


def subscriber_lines(
    reader: EntitlementSet,
    registered: Sequence[Subscriber],
    delivered: Mapping[str, datetime],
    *,
    now: datetime,
) -> tuple[SubscriberLine, ...]:
    """Every subscriber, in id order, or nothing for a reader who may not manage them.

    `delivered` is `brain.ops.outbox_store.last_delivered`, which holds only subscribers that
    have ever accepted a delivery, so a subscriber absent from it has never been delivered to
    and its line says so with None rather than with an old date.
    """
    if not may_manage(reader, now):
        return ()
    return tuple(
        SubscriberLine(
            subscriber_id=one.subscriber_id,
            endpoint=one.endpoint,
            kinds=tuple(sorted(kind.value for kind in one.kinds)),
            active=one.active,
            created_by=one.created_by,
            last_delivered_at=delivered.get(one.subscriber_id),
        )
        for one in sorted(registered, key=lambda one: one.subscriber_id)
    )


def findings(
    reader: EntitlementSet, registered: Sequence[Subscriber], *, now: datetime
) -> tuple[str, ...]:
    """What is wrong with the set of subscriptions, for a reader who may manage them.

    `brain.ops.outbox.subscriber_gaps`, whole. The findings name endpoints, so they are behind
    the same capability as the list.
    """
    if not may_manage(reader, now):
        return ()
    return subscriber_gaps(registered)


def registration(
    reader: EntitlementSet,
    *,
    subscriber_id: str,
    endpoint: str,
    secret_ref: SecretRef,
    kinds: Iterable[EventKind],
    now: datetime,
) -> Subscriber:
    """The subscriber a reader is registering, with their own id as its creator.

    The address is not checked here, and
    `brain.ops.outbox.A_SUBSCRIBER_URL_IS_CHECKED_AT_EVERY_DELIVERY` is why: a check at
    registration reads as "already checked", which is the hole the per delivery check exists
    to close.
    """
    if not may_manage(reader, now):
        raise SubscriberConsoleError(NOT_AVAILABLE)
    return Subscriber(
        subscriber_id=subscriber_id,
        endpoint=endpoint,
        secret_ref=secret_ref,
        kinds=tuple(kinds),
        created_by=reader.principal_id,
    )


def deactivation(reader: EntitlementSet, subscriber: Subscriber, *, now: datetime) -> Subscriber:
    """The subscriber, switched off. Refuses one that is already off.

    Refused rather than returned unchanged, because the store records the instant it stopped,
    and a second deactivation would move that instant to whoever clicked second.
    """
    if not may_manage(reader, now):
        raise SubscriberConsoleError(NOT_AVAILABLE)
    if not subscriber.active:
        msg = f"subscriber {subscriber.subscriber_id!r} is already switched off"
        raise SubscriberConsoleError(msg)
    return replace(subscriber, active=False)
