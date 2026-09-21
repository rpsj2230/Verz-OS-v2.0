"""`ops.sensitive_read`: one row per read of a record the declared sensitive set covers.

Needs Rupash item 45 chose to answer "which agents have read my HR record" for personnel records
and anything carrying a salary, and `brain.audit.reads` holds that set and the rules around it.
`brain.audit.record.AuditRecorder.record_read` built the entry in memory and nothing wrote one:
no process called it, and the tracker audit found no read entry on any install. This table is
where a finished request writes the read, and its insert trigger (`0098`) appends the
`record_read` ledger entry, **for `0054`'s reason: every persisted entry is written by a trigger on
a row**, so the chain keeps one writer and a statement typed at a prompt is recorded as a read
through the gate is.

**The row names the reader, the agent and the record, and never what the reader was shown.**
`record_kind` is the kind of record, which `brain.audit.reads.read_details` puts on the entry for
the reason `AN_ENTRY_NAMES_THE_RECORD_KIND_AND_NEVER_WHAT_ONE_READER_WAS_SHOWN` gives: two rows
that listed different fields would tell the subject what the other reader was refused. The
fields disclosed decide whether a row is written, in `brain.audit.sensitive_reads`, and are
dropped there.

**Exactly one of `subject_principal` and `record_id`.** A record about a person in the directory
is filed under that person, `principal:<id>`, which is the index `brain.audit.view` already
admits somebody to for their own entries, so "who read my record" is a question the member can
ask. A record that names no principal is filed under itself, `entity:<id>`, which names the record
the task sentence asks for; `record_read` refused a blank subject rather than file it anywhere,
and a read that is written nowhere is the failure M24.3.2 is about.

**`ent_hash` and `trace_id` are the row's, not session settings.** The recorder has both from the
finished request, so the entry carries the reader's real reach digest and the request's trace
without depending on `brain.tables.audit.attributed_to` having run in the same transaction,
which is the placeholder M24.3.1 exists to refuse.

**Append only.** SELECT and INSERT for the application role, row-level security with a policy for
each and no other, for `0093`'s reason: nothing edits what was read.

Task ids: M24.3.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import ENT_HASH, IDENTIFIER, TRACE_ID
from brain.db import Base

#: A record kind is an entity name, which is `brain.core.field_policy.NAME_PATTERN`.
RECORD_KIND_PATTERN: Final = r"^[a-z][a-z0-9_]*$"

#: An agent id, as `brain.core.department.SLUG_PATTERN` admits one, written without a
#: non-capturing group: SQLAlchemy has read `(?:` in a check constraint as a bind parameter.
AGENT_PATTERN: Final = r"^[a-z][a-z0-9_]*$"

RECORD_KIND_CHARS: Final = 64
AGENT_CHARS: Final = 64
#: `IDENTIFIER` is bounded at 128, and a subject id is one.
IDENTIFIER_CHARS: Final = 128
ENT_HASH_CHARS: Final = 32
TRACE_ID_CHARS: Final = 64


class SensitiveReadRow(Base):
    """`ops.sensitive_read`. One read of one record in the declared sensitive set."""

    __tablename__ = "sensitive_read"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: When the database wrote the row, which is the instant the ledger entry carries.
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The principal who was shown the record: the entry's actor.
    reader_id: Mapped[str] = mapped_column(String(IDENTIFIER_CHARS), nullable=False)
    #: The agent the read was made through, or null for a person asking directly.
    agent_id: Mapped[str | None] = mapped_column(String(AGENT_CHARS), nullable=True)
    record_kind: Mapped[str] = mapped_column(String(RECORD_KIND_CHARS), nullable=False)
    #: The person the record is about, when the record names one.
    subject_principal: Mapped[str | None] = mapped_column(String(IDENTIFIER_CHARS), nullable=True)
    #: The record's own id, when it names no principal.
    record_id: Mapped[str | None] = mapped_column(String(IDENTIFIER_CHARS), nullable=True)
    ent_hash: Mapped[str] = mapped_column(String(ENT_HASH_CHARS), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"reader_id ~ '{IDENTIFIER}'", name="reader_id_shape"),
        CheckConstraint(f"agent_id IS NULL OR agent_id ~ '{AGENT_PATTERN}'", name="agent_shape"),
        CheckConstraint(f"record_kind ~ '{RECORD_KIND_PATTERN}'", name="record_kind_shape"),
        CheckConstraint(
            f"subject_principal IS NULL OR subject_principal ~ '{IDENTIFIER}'",
            name="subject_principal_shape",
        ),
        CheckConstraint(f"record_id IS NULL OR record_id ~ '{IDENTIFIER}'", name="record_id_shape"),
        CheckConstraint("(subject_principal IS NULL) <> (record_id IS NULL)", name="one_subject"),
        CheckConstraint(f"ent_hash ~ '{ENT_HASH}'", name="ent_hash_shape"),
        CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        Index("ix_sensitive_read_at", "at"),
        Index("ix_sensitive_read_subject_principal", "subject_principal"),
        {"schema": "ops"},
    )
