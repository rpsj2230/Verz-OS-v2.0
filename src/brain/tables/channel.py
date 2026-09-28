"""`ops.channel` and `ops.channel_delivery`: which channels an install runs, and what crossed them.

Until these two tables a channel existed only as code. Nothing on an install said which surfaces
were switched on, where each one's secret was kept, or whether a message that arrived or left was
accepted or refused, so "Lark is on" was a sentence somebody remembered and "the vendor refused
it" was a log line kept for a month. M10.6.3 asks for a record per channel and M10.6.1 for a
delivery the vendor refused to be recorded as refused; this is both.

**One row per channel, keyed by the channel.** `ops.channel` holds the on or off state, the
channel's tenant identifiers (the vendor's own ids and addresses that say which tenant this is,
never a credential) and where its secret is kept. Switching one channel off is an UPDATE of its
own row and cannot reach another's. See `A_CHANNEL_IS_SWITCHED_OFF_ON_ITS_OWN_ROW`.

**The secret is a vault reference, and the reference is derived.** `secret_path` is
`providers/channel_<channel>` and a check holds it to exactly that, so a row cannot point the
channel at another credential's slot, and a value pasted into the column is refused by its shape.
`brain.ops.channel_store.A_CHANNEL_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL` argues the engine.

**A delivery row carries no content.** A channel, a direction, an outcome, a reason from a closed
list, the vendor's status when it answered one, and an instant. No body, no sender, no recipient,
no external id: a refused request is somebody's message, and a table of refusals that kept them
would be the one place a message the gate never admitted is stored. See
`EVERY_REFUSAL_IS_RECORDED_WITHOUT_ITS_CONTENT`.

**Outbound has three outcomes and not two.** Sent, refused, and unknown: a vendor that timed out
may have delivered, and `brain.ops.idempotency.state_after_call` reads a silence as UNKNOWN for
that reason. Recording it as refused would invite a resend of a message that arrived, and as sent
would be the claim M10.6.1 forbids.

Task ids: M10.6.1, M10.6.3
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, SmallInteger, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.gate.context import Channel
from brain.ops.secrets import VaultRole
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Why switching a channel off is an update of its own row.
A_CHANNEL_IS_SWITCHED_OFF_ON_ITS_OWN_ROW: Final = (
    "Each channel is one row keyed by the channel, so switching one off is an update that names "
    "that channel and no other. A single setting holding every channel's state would make each "
    "switch a read, an edit and a write of every channel's state, and two administrators "
    "switching two channels at once would each put back the other's old value."
)

#: Why a delivery row has no column that could hold a message.
EVERY_REFUSAL_IS_RECORDED_WITHOUT_ITS_CONTENT: Final = (
    "A delivery row says which channel, which direction, what happened and why, in words from "
    "a closed list, and nothing about who or what. A refused request is still somebody's "
    "message, and a record of refusals that kept the message would store exactly what the "
    "gate refused to admit."
)

#: The prefix every channel's secret slot starts with. See the module docstring.
CHANNEL_SECRET_PREFIX: Final = "providers/channel_"  # noqa: S105

#: The widest channel name `brain.gate.context.Channel` has, and room to spare.
CHANNEL_CHARS: Final = 16

#: The widest slot: the prefix and the widest channel.
SECRET_PATH_CHARS: Final = len(CHANNEL_SECRET_PREFIX) + CHANNEL_CHARS

#: The widest word in any vocabulary below.
WORD_CHARS: Final = 24


class Direction(enum.StrEnum):
    """Which way a delivery was going."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DeliveryOutcome(enum.StrEnum):
    """What happened to one delivery. Which ones each direction may take is a check."""

    #: Inbound: verified, read and claimed as its first delivery.
    ACCEPTED = "accepted"
    #: Inbound: verified and read, and claimed before, so nothing answered it.
    REDELIVERED = "redelivered"
    #: Outbound: the vendor accepted it.
    SENT = "sent"
    #: Either way: refused, by this install or by the vendor. `reason` says which.
    REFUSED = "refused"
    #: Outbound: the vendor did not answer, so it may or may not have arrived.
    UNKNOWN = "unknown"


class RefusedBecause(enum.StrEnum):
    """Why a delivery was not made, in words that name a cause and never a message."""

    #: No record for this channel on the install.
    NOT_CONFIGURED = "not_configured"
    #: The channel's record is switched off.
    SWITCHED_OFF = "switched_off"
    #: The request was larger than a message is.
    TOO_LARGE = "too_large"
    #: The channel's secret slot holds nothing.
    NO_SECRET = "no_secret"  # noqa: S105
    #: The vault could not be asked, or refused.
    VAULT_UNAVAILABLE = "vault_unavailable"
    #: The signature did not verify, or the request was stale.
    BAD_SIGNATURE = "bad_signature"
    #: Verified, and not a message this channel can read.
    UNREADABLE = "unreadable"
    #: A bound sender, on an install where nothing answers on channels yet.
    NOT_ANSWERABLE = "not_answerable"
    #: The recipient's reach changed between the answer being made and being sent.
    REACH_CHANGED = "reach_changed"
    #: The surface cannot carry the payload's label or its classification.
    CANNOT_CARRY = "cannot_carry"
    #: The record lacks what the channel needs to send, such as its reply address.
    INCOMPLETE = "incomplete"
    #: The vendor's address resolves somewhere only this network can reach.
    UNSAFE_ADDRESS = "unsafe_address"
    #: The vendor answered and refused.
    VENDOR_REFUSED = "vendor_refused"
    #: The vendor did not answer, or answered that it could not. Only ever beside
    #: `DeliveryOutcome.UNKNOWN`, because such a request may still have been delivered.
    VENDOR_UNAVAILABLE = "vendor_unavailable"


#: Which outcomes each direction may record. Read by the check and by the store.
OUTCOMES_BY_DIRECTION: Final[dict[Direction, frozenset[DeliveryOutcome]]] = {
    Direction.INBOUND: frozenset(
        {DeliveryOutcome.ACCEPTED, DeliveryOutcome.REDELIVERED, DeliveryOutcome.REFUSED}
    ),
    Direction.OUTBOUND: frozenset(
        {DeliveryOutcome.SENT, DeliveryOutcome.REFUSED, DeliveryOutcome.UNKNOWN}
    ),
}


def outcome_fits_direction() -> str:
    """The check pairing each direction with its outcomes, built from `OUTCOMES_BY_DIRECTION`."""
    return " OR ".join(
        f"(direction = '{direction.value}' AND {one_of('outcome', outcomes)})"
        for direction, outcomes in sorted(OUTCOMES_BY_DIRECTION.items())
    )


#: A reason is given exactly when nothing was delivered, or it is not known whether it was.
REASON_WHEN_NOT_DELIVERED: Final = "(outcome IN ('refused', 'unknown')) = (reason IS NOT NULL)"


class ChannelRow(Base):
    """`ops.channel`. One channel on this install: on or off, its tenant, and its secret's slot."""

    __tablename__ = "channel"

    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: The vendor's identifiers and addresses for this tenant. Never a credential.
    tenant: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    secret_path: Mapped[str] = mapped_column(String(SECRET_PATH_CHARS), nullable=False)
    secret_role: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The database's clock at the last change.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint("jsonb_typeof(tenant) = 'object'", name="tenant_is_an_object"),
        CheckConstraint(
            f"secret_path = '{CHANNEL_SECRET_PREFIX}' || channel", name="secret_path_is_derived"
        ),
        # The application verifies and sends, so it is the role that borrows the secret.
        CheckConstraint(f"secret_role = '{VaultRole.APPLICATION.value}'", name="secret_role"),
        CheckConstraint(f"updated_by ~ '{IDENTIFIER}'", name="updated_by_shape"),
        {"schema": "ops"},
    )


class ChannelDeliveryRow(Base):
    """`ops.channel_delivery`. One message in or out, what happened, and never what it said."""

    __tablename__ = "channel_delivery"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)
    direction: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    outcome: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(WORD_CHARS), nullable=True)
    #: The status the vendor answered with, when it answered one.
    vendor_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint(one_of("direction", Direction), name="direction"),
        CheckConstraint(outcome_fits_direction(), name="outcome_fits_direction"),
        CheckConstraint(
            f"reason IS NULL OR {one_of('reason', RefusedBecause)}", name="reason_known"
        ),
        CheckConstraint(REASON_WHEN_NOT_DELIVERED, name="reason_when_not_delivered"),
        CheckConstraint(
            "vendor_status IS NULL OR vendor_status BETWEEN 100 AND 599", name="vendor_status"
        ),
        Index("ix_channel_delivery_channel_recorded_at", "channel", "recorded_at"),
        {"schema": "ops"},
    )
