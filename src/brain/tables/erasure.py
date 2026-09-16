"""Every request to erase somebody's data, and what carrying it out did.

`brain.ops.erasure` decides what a deletion reaches and in what order, and until this table nothing
recorded that anybody had asked for one: `brain.erasure_routes` told an administrator that a
request "has to be handled and recorded outside this system". This is where a request lands and
where the queue writes how it finished. `brain.ops.erasure_store` holds the transactions.

**One row per request, and the row is finished once.** A request is inserted by the administrator
who filed it, and the queue sets the five finishing columns together when it carries the request
out, which a check constraint holds whole: finished with an outcome, the stores and the holds, or
not finished at all. There is no retirement and no second finish, because "who asked, and what did
it do" is the record an erasure leaves once the data is gone, and a record that could be edited
afterwards proves nothing about either.

**The person is named here and nowhere downstream.** `subject_id` is whose data is to be erased,
and it has to be, because the queue needs it to carry the request out and the person needs to be
able to follow their own request up. The ledger entry `0060`'s trigger writes names the request
and never the person, and `stores` carries counts and sentences, never a value that was removed,
for the reason `brain.ops.erasure.A_CERTIFICATE_IS_NOT_A_COPY_OF_WHAT_IT_DELETED` gives. **This row
is kept when the erasure runs**, deliberately: it is the proof the erasure was asked for and what it
did, and `brain.ops.erasure_store.RETAINED` names it so the executor never reaches it.

**One open request per person**, by a partial unique index, because two open requests for one
person are two runs over the same rows and two ledger entries saying the same person was erased
twice. A finished request does not block a new one: a request held by a legal hold is made again
when the hold is lifted, which is `brain.ops.erasure.A_HELD_SUBJECT_IS_NOT_ERASED`.

**The reason is a reference token, never a sentence**, for
`brain.ops.export.A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES`' reason: a free-text field on
the record of an erasure is where the reason the person left ends up.

Task ids: M27.7.24
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.tables.data_export import REFERENCE_CHARS, REFERENCE_PATTERN
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide an outcome's word may be. `incomplete` is ten.
OUTCOME_CHARS: Final = 16


class ErasureOutcome(enum.StrEnum):
    """How the queue finished a request. `brain.audit.record.ErasureChange` less `requested`."""

    #: Every store a deletion reaches was reached and nothing about the person was kept.
    ERASED = "erased"
    #: An active legal hold reached the person, so nothing was touched.
    HELD = "held"
    #: A store could not be reached, or a table kept rows no path may remove.
    INCOMPLETE = "incomplete"


class ErasureRequestRow(Base):
    """`ops.erasure_request`. One request, filed by a person and finished once by the queue."""

    __tablename__ = "erasure_request"

    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: Whose data is to be erased.
    subject_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The matter or ticket the request arrived under.
    reason_reference: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Who finished it: the queue's own name, `brain.ops.erasure_store.ERASURE_QUEUE_ACTOR`.
    finished_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(OUTCOME_CHARS), nullable=True)
    #: `brain.ops.erasure_store.stores_document`: one entry per store, counts and sentences.
    stores: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    #: The ids of the holds that stopped a held request. Empty for every other outcome.
    holds: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(f"subject_id ~ '{IDENTIFIER}'", name="subject_is_an_identifier"),
        CheckConstraint(f"requested_by ~ '{IDENTIFIER}'", name="requested_by_is_an_identifier"),
        CheckConstraint(f"reason_reference ~ '{REFERENCE_PATTERN}'", name="reference_is_a_token"),
        CheckConstraint(
            f"finished_by IS NULL OR finished_by ~ '{IDENTIFIER}'",
            name="finished_by_is_an_identifier",
        ),
        CheckConstraint(f"outcome IS NULL OR {one_of('outcome', ErasureOutcome)}", name="outcome"),
        # Finished whole or not at all: an outcome nobody finished, or a finish with no stores,
        # is a request whose record says two things.
        CheckConstraint(
            "(finished_at IS NULL) = (finished_by IS NULL) "
            "AND (finished_at IS NULL) = (outcome IS NULL) "
            "AND (finished_at IS NULL) = (stores IS NULL) "
            "AND (finished_at IS NULL) = (holds IS NULL)",
            name="finished_whole",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= requested_at",
            name="finished_after_it_was_requested",
        ),
        CheckConstraint("stores IS NULL OR jsonb_typeof(stores) = 'array'", name="stores_list"),
        CheckConstraint("holds IS NULL OR jsonb_typeof(holds) = 'array'", name="holds_list"),
        # A held request names the holds that stopped it, and no other outcome names any.
        CheckConstraint(
            "outcome IS NULL OR (outcome = 'held') = (jsonb_array_length(holds) > 0)",
            name="held_names_its_holds",
        ),
        Index(
            "uq_erasure_request_open",
            "subject_id",
            unique=True,
            postgresql_where=text("finished_at IS NULL"),
        ),
        Index("ix_erasure_request_requested_at", "requested_at"),
        {"schema": "ops"},
    )
