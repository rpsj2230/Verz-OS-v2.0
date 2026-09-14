"""Three tables for telling somebody else that something happened: who asked, what, and how far.

`brain.ops.outbox` is the shape and the policy, and said since it was written that "the table
itself is not in this repository yet". This is that table, split into the three things the
module already separates: a subscriber, an event, and one event's journey to one subscriber.

**Three tables and not one, because the three change at different rates and for different
people.** A subscriber is configuration somebody sets in the console and deactivates months
later. An event is a fact written once, in the transaction that made the change it describes,
and never touched again. A delivery is the only row that moves, once per attempt. Folding the
delivery into the event would mean one subscriber being down holds a row every other
subscriber's delivery also lives on, which is the argument `brain.ops.outbox.Delivery` makes
about itself.

**The event table is appended to and never updated.** SELECT and INSERT are granted and
nothing else, and there is no policy that would admit an UPDATE or a DELETE. An event is the
thing the subscriber deduplicates on, and an event whose kind or record id could be edited
after the first attempt is a deduplication key that means two different things on two
attempts. See `AN_EVENT_IS_WRITTEN_ONCE`.

**A delivery row may only be moved while it is pending.** The UPDATE policy reads the state
the row is in before the change, so a delivered or exhausted row cannot be moved by the
application at all. That is `brain.ops.outbox.plan_next`'s refusal to attempt a settled
delivery, held by the database as well, and the two are not a second implementation of one
rule: the domain refusal names the mistake and the policy is what holds when somebody writes
the UPDATE by hand.

**A subscriber is deactivated, never deleted, and deactivation is one way.** `deactivated_at`
is the only change a subscriber row takes, and the UPDATE policy admits it only on a row that
is still active. A delivery row names its subscriber by foreign key, so a deleted subscriber
would take with it the record of what was sent where, which is the one question asked after
a client's identifiers turn up somewhere unexpected. Reactivating is registering again, under
a new id, by somebody whose name goes on the new row.

**The secret is a reference, and rotating it is not a row change.** `secret_path` and
`secret_role` are a `brain.ops.secrets.SecretRef`, which is safe in a database and useless to
anybody who cannot already reach the vault. Rotating the shared secret replaces what the vault
holds at that path, so no column here changes and no route is needed for it.

**No foreign key from an event to anything outside this schema.** An event names an entity
and a record id as values. A key into the row plane would make the fact that something happened
depend on a cache having been filled, which is the refusal `0019` and `0020` make for the same
reason.

Task ids: M17.5.1, M17.5.3
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.outbox import (
    MAX_DELIVERY_ATTEMPTS,
    MAX_IDENTIFIER_CHARS,
    DeliveryState,
    EventKind,
)
from brain.ops.secrets import VaultRole
from brain.tables.identity import one_of

#: Why an event row takes no UPDATE.
AN_EVENT_IS_WRITTEN_ONCE: Final = (
    "The event id is what a subscriber deduplicates on, and it only works as a key if what it "
    "names is the same on every attempt. An event row that could be edited between the first "
    "attempt and the second would send two different facts under one id, and the subscriber "
    "would drop the second as a duplicate of something it was not."
)

#: How long an endpoint may be. A URL, not a document.
ENDPOINT_CHARS: Final = 2048

#: How long a vault path may be. The same bound `brain.ops.secrets.SecretRef` refuses above.
SECRET_PATH_CHARS: Final = 200

#: How long a reason on a delivery row may be. A sentence for an operator, never a payload.
REASON_CHARS: Final = 2000


def within(column: str, values: Iterable[str]) -> str:
    """An array column holding only members of a closed vocabulary, built from the vocabulary.

    The array twin of `brain.tables.identity.one_of`, for the reason that helper gives: a
    hand-written copy of an enum stops matching it the first time somebody adds a member. The
    literal is cast to `text[]` because `<@` compares arrays of one type and the column is one.
    """
    listed = ", ".join(f"'{value}'" for value in sorted(values))
    return f"{column} <@ ARRAY[{listed}]::text[]"


class WebhookSubscriberRow(Base):
    """`ops.webhook_subscriber`. One endpoint that asked to be told about some kinds (M17.5.3).

    Mirrors `brain.ops.outbox.Subscriber`, with `active` stored as the absence of a
    deactivation instant rather than as a boolean. A boolean says whether a subscriber is on
    now; the instant says when it stopped, which is what somebody reading a delivery history
    needs in order to tell a quiet integration from a switched-off one.
    """

    __tablename__ = "webhook_subscriber"

    subscriber_id: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_CHARS), primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    secret_path: Mapped[str] = mapped_column(String(SECRET_PATH_CHARS), nullable=False)
    secret_role: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Every kind this subscriber takes. At least one, and only kinds `EventKind` declares.
    kinds: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    #: Who set this up. See `brain.ops.outbox.Subscriber` on why it is required.
    created_by: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: When it was switched off. Null while it is active.
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(btrim(subscriber_id)) >= 1", name="subscriber_id_present"),
        CheckConstraint(
            f"length(btrim(endpoint)) BETWEEN 1 AND {ENDPOINT_CHARS}", name="endpoint_present"
        ),
        CheckConstraint(one_of("secret_role", VaultRole), name="secret_role"),
        CheckConstraint("cardinality(kinds) >= 1", name="takes_something"),
        CheckConstraint(within("kinds", EventKind), name="kinds_known"),
        CheckConstraint("length(btrim(created_by)) >= 1", name="created_by_present"),
        {"schema": "ops"},
    )


class OutboxEventRow(Base):
    """`ops.outbox_event`. One thing that happened, written with the change (M17.5.1).

    Mirrors `brain.ops.outbox.OutboxEvent`. `recorded_at` is the database's clock and is not
    `occurred_at`: the first is when the row landed and the second is when the thing happened,
    and a subscriber orders on the second.
    """

    __tablename__ = "outbox_event"

    event_id: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_CHARS), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_CHARS), nullable=False)
    record_id: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_CHARS), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Further identifiers. Values only, never a body: see
    #: `brain.ops.outbox.AN_EVENT_CARRIES_IDS_AND_NEVER_CONTENT`.
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("length(btrim(event_id)) >= 1", name="event_id_present"),
        CheckConstraint(one_of("kind", EventKind), name="kind"),
        CheckConstraint("length(btrim(record_id)) >= 1", name="record_id_present"),
        CheckConstraint("jsonb_typeof(attributes) = 'object'", name="attributes_object"),
        {"schema": "ops"},
    )


class OutboxDeliveryRow(Base):
    """`ops.outbox_delivery`. One event's journey to one subscriber, and the row a worker claims.

    Mirrors `brain.ops.outbox.Delivery`, plus the three columns a worker needs and the domain
    type deliberately does not carry: when it is next due, when it was last attempted, and the
    sentence `plan_next` gave for the last move.

    **`attempts` counts requests that left this process, and nothing else.** A delivery parked
    because its subscriber was deactivated, or because its address resolved somewhere internal,
    was never sent, so it is exhausted with its count unchanged. A count that also included
    refusals made on this side would read in the console as a subscriber that failed eight
    times, which sends somebody to look at the wrong system.
    """

    __tablename__ = "outbox_delivery"

    event_id: Mapped[str] = mapped_column(
        String(MAX_IDENTIFIER_CHARS),
        ForeignKey("ops.outbox_event.event_id"),
        primary_key=True,
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(MAX_IDENTIFIER_CHARS),
        ForeignKey("ops.webhook_subscriber.subscriber_id"),
        primary_key=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{DeliveryState.PENDING.value}'")
    )
    #: When a worker may next claim it. Meaningful only while pending.
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"attempts BETWEEN 0 AND {MAX_DELIVERY_ATTEMPTS}", name="attempts_within_the_cap"
        ),
        CheckConstraint(one_of("state", DeliveryState), name="state"),
        # A delivery that was attempted says when. The other direction is not required: a
        # delivery parked on this side was never attempted and has no instant to give.
        CheckConstraint(
            "attempts = 0 OR last_attempt_at IS NOT NULL", name="an_attempt_has_an_instant"
        ),
        CheckConstraint(
            f"last_reason IS NULL OR length(last_reason) <= {REASON_CHARS}",
            name="reason_is_a_sentence",
        ),
        # The claim query's index, and partial because a worker never asks about a settled row.
        # Without the predicate the index grows with every delivery ever made and the claim
        # scans past a history that only gets longer.
        Index(
            "ix_outbox_delivery_due",
            "due_at",
            postgresql_where=text(f"state = '{DeliveryState.PENDING.value}'"),
        ),
        {"schema": "ops"},
    )
