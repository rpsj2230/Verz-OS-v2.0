"""`ops.oauth_consent`: a consent started at a vendor, held until the vendor answers it, once.

`migrations/versions/0180_oauth_consent.py` holds the argument for the table, its policies and its
grants; what is here is the model that mirrors it.

**One change is ever made to a row: `used_at` is set, once, by the person who started it.** The
application role may update that column alone, and the database's policies hold every read, insert
and update to the actor the transaction is attributed to. `brain.ops.connector_consent` is the one
writer.

**Never deleted by the application; removed when its person is erased**, by the erasure queue as
the database owner (`brain.ops.erasure_store.REMOVED`).

**Its kind says whose consent it is, and is never changed.** A source's own or a person's own
(`brain.connectors.oauth.ConsentKind`); the application may update `used_at` alone, so a consent
started as a person's cannot be answered as a source's.

**No foreign key to `auth.principal` or to a connection**, for the reason `brain.tables.credential`
gives: a principal and a source are values, and the record outlives both.

Task ids: M11.8.6
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.connectors.oauth import MAX_RETURN_ADDRESS_CHARS, ConsentKind
from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: A state's digest: SHA-256, in hex.
DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"

#: The widest consent kind, as `0180` makes the column.
KIND_CHARS: Final = 16

#: The check `0180` puts on the kind: one of `ConsentKind`'s values.
KIND_CHECK: Final = "kind IN (" + ", ".join(f"'{one.value}'" for one in ConsentKind) + ")"

#: The longest sealed verifier: a 12-byte nonce, a 128-character verifier and a 16-byte tag, in
#: unpadded-to-padded base64, with room.
SEALED_CHARS: Final = 256


class OAuthConsentRow(Base):
    """`ops.oauth_consent`. One consent started at a vendor, for one source, by one person."""

    __tablename__ = "oauth_consent"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The SHA-256 of the consent's state. The state itself is never kept.
    state_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The source consented to, the same as `ops.connector_connection.connector`.
    connector: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    #: A source's consent or a person's own (`ConsentKind`), fixed when the row is written.
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    #: Who started it, and the only person who may answer it.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: Where the vendor was told to send the person back, sent again with the code.
    return_address: Mapped[str] = mapped_column(String(MAX_RETURN_ADDRESS_CHARS), nullable=False)
    #: The PKCE verifier, sealed under a key derived from the state.
    sealed_verifier: Mapped[str] = mapped_column(String(SEALED_CHARS), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When the answer was taken. Empty until then, and set once.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"state_digest ~ '{DIGEST_PATTERN}'", name="state_digest_shape"),
        CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        CheckConstraint(KIND_CHECK, name="kind_known"),
        CheckConstraint(f"principal_id ~ '{IDENTIFIER}'", name="principal_id_shape"),
        CheckConstraint("return_address LIKE 'https://%'", name="return_address_is_https"),
        CheckConstraint("length(sealed_verifier) > 0", name="verifier_is_sealed"),
        CheckConstraint("expires_at > issued_at", name="expires_after_issue"),
        CheckConstraint("used_at IS NULL OR used_at >= issued_at", name="used_after_issue"),
        UniqueConstraint("state_digest"),
        {"schema": "ops"},
    )
