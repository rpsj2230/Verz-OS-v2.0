"""Every side-effecting operation gets a row, keyed by its idempotency key and unique on it.

`brain.ops.idempotency` holds the argument for the record and `brain.ops.operation_store` for how
it is written. What is here is the shape, and the shape has one job: to make "two workers both
found no record and both issued" impossible rather than unlikely.

**The key is the primary key.** `brain.ops.idempotency.WHAT_THE_CRASH_MODEL_DOES_NOT_COVER` has
said since the state machine was written that exactly-once rests on "a unique index on the key",
and that no such index existed. This is it. A second insert of the same intent conflicts, which
is what lets `claim` answer the record already there instead of writing a second one.

**The state is one of `OperationState`, generated from the enum.** A hand-written list is a list
that stops matching the machine the first time a state is added, and the failure is a row the
database refuses after every Python test passed. The transitions are enforced by a trigger in
`0051` as well as by `advance`, because a row edited by hand past `UNKNOWN` back to `PENDING` is
the second issue the whole machine exists to prevent, and the Python check never sees that edit.

**No `deleted_at` and nothing to delete with.** A record of an effect that could be retired is a
record whose effect can be issued again, because the next attempt finds no key.

**Nothing about what the effect carried.** The key is a digest of the arguments and the arguments
are not stored: a row naming the recipient and the amount would be a copy of business data with
none of the permissions that governed it, which is `A_KEY_IS_DERIVED_NEVER_GENERATED`'s reason
for hashing in the first place.

Task ids: M17.3.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.idempotency import KEY_CHARS, OperationState
from brain.tables.identity import one_of

#: Widths, named once so the model, the migration and the store agree.
CONNECTOR_CHARS: Final = 80
TOOL_CHARS: Final = 160
PRINCIPAL_CHARS: Final = 128
INTENT_CHARS: Final = 256


class OperationRow(Base):
    """`ops.operation`. One intent to issue a side effect, and how far it has got."""

    __tablename__ = "operation"

    key: Mapped[str] = mapped_column(String(KEY_CHARS), primary_key=True)
    connector: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    tool: Mapped[str] = mapped_column(String(TOOL_CHARS), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    intent_ref: Mapped[str] = mapped_column(String(INTENT_CHARS), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(f"key ~ '^[0-9a-f]{{{KEY_CHARS}}}$'", name="key_is_a_derived_key"),
        CheckConstraint(one_of("state", OperationState), name="state"),
        CheckConstraint("length(btrim(connector)) >= 1", name="connector_present"),
        CheckConstraint("length(btrim(tool)) >= 1", name="tool_present"),
        CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        CheckConstraint("length(btrim(intent_ref)) >= 1", name="intent_present"),
        Index("ix_operation_state", "state"),
        {"schema": "ops"},
    )
