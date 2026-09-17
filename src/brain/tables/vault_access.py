"""Every call the secrets vault answered about a slot, shipped from its audit log into the ledger.

`brain.ops.vault_audit` reads the vault's audit log and `brain.ops.vault_audit_ship` carries it
here from the worker; `migrations/versions/0093_vault_leases_and_audit.py` holds the trigger that
appends a `vault_access` ledger entry for every row. What is here is the model that mirrors it.

**No column could hold a value.** A slot in the credential slot grammar, an operation word, a part
word, whether it was refused, and an identity that is the hex of an HMAC the vault computed. Check
constraints pin every text column, so a hand-written statement cannot put a token or a path past
the slot into any of them.

**Where in the log a row came from is kept, and is what makes shipping safe to repeat.** The log
file's identity, a digest of its first line, and the byte offset just past the entry's line are
unique together, so two workers shipping the same stretch of log write each entry once, and the
next run starts from the furthest offset shipped for the file that is there now.

**Append only.** SELECT and INSERT for the application role, for `0068`'s reason: a worker
configured with that role's login is not refused, and nothing edits what the vault said.

Task ids: M31.3.2.6
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.record import CREDENTIAL_SLOT, CREDENTIAL_SLOT_CHARS
from brain.db import Base
from brain.ops.vault_audit import Part
from brain.tables.identity import one_of

#: What part of a slot a call touched. See `brain.ops.vault_audit.Part`, held equal by a test.
PARTS: Final[tuple[str, ...]] = tuple(sorted(one.value for one in Part))

#: An OpenBao operation word.
OPERATION_PATTERN: Final = r"^[a-z]{1,16}$"

#: The hex of an HMAC, or of the first line's sha256.
HEX_DIGEST: Final = r"^[0-9a-f]{64}$"


#: The generated name of the one-row-per-log-position constraint, held equal to it by a test.
ONCE: Final[str] = "uq_vault_access_log_identity_log_offset"


class VaultAccessRow(Base):
    """`ops.vault_access`. One answered call about one slot, as the vault's audit log has it."""

    __tablename__ = "vault_access"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: When the vault answered, by the vault's clock.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    #: One of `PARTS`.
    part: Mapped[str] = mapped_column(String(16), nullable=False)
    slot: Mapped[str] = mapped_column(String(CREDENTIAL_SLOT_CHARS), nullable=False)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: The accessor's HMAC as hex, or null when the vault logged none this could read.
    identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: A digest of the log file's first line, which tells one file from its replacement.
    log_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The byte offset just past this entry's line.
    log_offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shipped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"operation ~ '{OPERATION_PATTERN}'", name="operation_shape"),
        CheckConstraint(one_of("part", PARTS), name="part"),
        CheckConstraint(f"slot ~ '{CREDENTIAL_SLOT}'", name="slot_shape"),
        CheckConstraint(f"identity IS NULL OR identity ~ '{HEX_DIGEST}'", name="identity_shape"),
        CheckConstraint(f"log_identity ~ '{HEX_DIGEST}'", name="log_identity_shape"),
        CheckConstraint("log_offset > 0", name="log_offset_positive"),
        # Unnamed: the naming convention generates `ONCE`, which the shipper names on conflict.
        UniqueConstraint("log_identity", "log_offset"),
        Index("ix_vault_access_shipped_at", "shipped_at"),
        {"schema": "ops"},
    )
