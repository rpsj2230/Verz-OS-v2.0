"""Every export taken from the console: what data set, by whom, why, and what left.

`brain.ops.export` says an export is the widest permission act this platform performs and that its
record is "a required member of the returned object rather than something written on the side",
and it left `ExportAudit` for "whoever wires the two together". This table is where that record
lands, and `0053`'s trigger is what puts every row into the audit ledger.

**One row per export produced, written in the transaction that read what was exported.** The
document is handed back only after that transaction commits, so there is no path that returns an
export and leaves no row, and none that leaves a row for a document nobody received. See
`brain.ops.data_export_store.THE_ROW_AND_THE_DOCUMENT_COMMIT_TOGETHER`.

**What left is described by what a reader could check it against, never by its content.** The
window as sequence numbers, how many entries, whether the chain verified, and the sha256 of the
exact bytes handed over. A recipient holding the file can prove it is this export; a reader of this
table learns nothing the ledger itself would have refused to hold.

**Recorded in the ledger as a publish, by the database.** An export is an artefact leaving the
system, which is what `brain.audit.ledger.AuditAction.PUBLISH` records, so no member is added: the
subject is `artifact:<export_id>`, the actor is `requested_by`, and the details name the data set
under `fields`, which is the shape `brain.audit.record.AuditRecorder.publish` writes. A trigger
rather than the route, for the reason `0050` and `0052` give: an export inserted by a statement at
the server is recorded as well as one pressed in the console.

**The reason is a closed word and the reference is a token with no spaces**, for
`brain.ops.export.A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES`'s reason: a free-text field
on the record of an export is where the name of the person being investigated ends up.

**Never edited and never retired.** SELECT and INSERT only, no `deleted_at`.

Task ids: M27.8.16
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.export import ExportReason
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide a data set's name may be.
DATA_SET_CHARS: Final = 32

#: How wide a reason's word may be. `litigation_hold_collection` is twenty-six.
REASON_CHARS: Final = 32

#: How long a reference may be. A ticket or matter number, not a sentence.
REFERENCE_CHARS: Final = 64

#: What a reference may be: a token a ticket system or a matter register would issue, starting with
#: a letter or a digit and carrying no space. No colon either, because SQLAlchemy reads a colon
#: in a constraint's text as the start of a bind parameter. See the module note on free text.
REFERENCE_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9_./#-]{0,63}$"

#: A sha256 in lower-case hex.
DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"


class ExportDataSet(enum.StrEnum):
    """Every data set an export can be taken of from the console. Closed, like `ExportReason`.

    One member, because one data set can be exported end to end on an install today. Every other
    candidate and the reason it cannot be is `brain.ops.data_transfer.CATALOGUE`, and a member is
    added here on the day its export runs, with the migration that widens the constraint.
    """

    #: A contiguous window of the audit ledger, as `brain.audit.export` renders it.
    AUDIT_TRAIL = "audit_trail"


class DataExportRow(Base):
    """`ops.data_export`. One export produced, and what a recipient can check it against."""

    __tablename__ = "data_export"

    export_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    data_set: Mapped[str] = mapped_column(String(DATA_SET_CHARS), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    reason_reference: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    produced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The window, as the first and last sequence numbers exported. Both None for an empty one.
    first_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    entries: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Whether the window's chain verified when it was exported. The document carries the break.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: sha256 over the exact document handed over.
    document_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("data_set", ExportDataSet), name="data_set"),
        CheckConstraint(one_of("reason", ExportReason), name="reason"),
        CheckConstraint("length(btrim(requested_by)) > 0", name="requested_by_present"),
        CheckConstraint(f"reason_reference ~ '{REFERENCE_PATTERN}'", name="reference_is_a_token"),
        CheckConstraint(f"document_digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        CheckConstraint("entries >= 0", name="entries_not_negative"),
        CheckConstraint(
            "(first_seq IS NULL) = (last_seq IS NULL) AND (first_seq IS NULL) = (entries = 0)",
            name="a_window_names_both_ends_or_neither",
        ),
        CheckConstraint(
            "first_seq IS NULL OR last_seq - first_seq + 1 = entries",
            name="the_window_is_contiguous",
        ),
        {"schema": "ops"},
    )
