"""Every credential written into the vault: which slot, by whom, when, and never what.

`brain.ops.credentials` writes a provider key into a vault slot, and
`migrations/versions/0054_credential_and_retention_audit.py` holds the argument for recording
it: a row here, and a trigger on the row that appends the ledger entry. What is here is the model
that mirrors it.

**No column could hold a value, and that is the table's whole design.** A slot, a principal id and
a time. Not the value, not its length, not a prefix and not a fingerprint: each is part of the
secret, a fingerprint of a key is a lookup for anybody holding a candidate, and this table is read
by the application role. `brain.tables.config` refuses a credential in `ops.setting` on the same
argument, and a table named for credentials is the second place somebody would reach for when a
screen wants to say which key was saved. The check constraints pin the two text columns to a path
and an identifier, so a hand-written statement cannot put a key in either.

**No `updated_at`, no `deleted_at`, no `SoftDeleteMixin`.** A write is a fact about a moment. The
application role is granted SELECT and INSERT only, a second write to one slot is a second row, and
a row retired would be a key replaced with nobody recorded as replacing it.

**No foreign key to `auth.principal` on `written_by`.** It is a value, for the reason
`brain.tables.review` gives about `decided_by`, and it cannot be a key anyway: the setup wizard
writes a key before any principal exists, as `brain.firstrun.GRANTED_BY`.

**The name was checked against every sweep that reads table names.** `brain.ops.sweeps` finds
grant-bearing tables by `%grant%` and `%pack%` and nothing reads a table name for words such as
credential, secret, key or token, so nothing was renamed to pass a sweep and no sweep was touched.

Task ids: M27.8.7
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.audit.record import CREDENTIAL_SLOT, CREDENTIAL_SLOT_CHARS
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS


class CredentialWriteRow(Base):
    """`ops.credential_write`. One credential written into one slot, by one actor, at one time."""

    __tablename__ = "credential_write"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The vault path written, `providers/anthropic`. The ledger's subject is derived from it.
    slot: Mapped[str] = mapped_column(String(CREDENTIAL_SLOT_CHARS), nullable=False)
    #: Who wrote it: a principal id, or `brain.firstrun.GRANTED_BY` from the setup wizard. The
    #: audit entry's actor, read off this column by the trigger.
    written_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The database's clock, in the same transaction as the ledger entry's `at`, so the two agree.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"slot ~ '{CREDENTIAL_SLOT}'", name="slot_shape"),
        CheckConstraint(f"written_by ~ '{IDENTIFIER}'", name="written_by_shape"),
        {"schema": "ops"},
    )
