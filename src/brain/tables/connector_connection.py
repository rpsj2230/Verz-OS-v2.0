"""Which sources this install has connected from the console: one row per connection, never edited.

`brain.ops.connector_store` writes it and `migrations/versions/0057_connector_connection.py` holds
the argument for the table, the policies and the trigger; what is here is the model that mirrors
it. Until this table nothing anywhere recorded which connectors an install had connected, so
`brain.connector_routes` answered every install with a sentence saying nothing had looked.

**The settings are kept and the key is not, and that split is the table's design.** A connection
is the source's own identifiers that say what it reaches (an organisation id, a portal id), which
are what `brain.ops.connectable` builds the manifest from and what the trust screen shows
in words, and a key the source's vendor issued, which is written into the vault slot the source's
name makes and never reaches a table. No column here could hold the key, its length, a prefix or a
fingerprint, for the argument `brain.tables.credential` makes about its own columns.

**The digest pinned at connect is kept beside the settings.** `brain.connectors.manifest.
manifest_digest` of the manifest the administrator agreed to, so the screen can say when what a
source declares today is no longer what was agreed to: a release that changes a connector's tools
changes the manifest built from the same settings, and a row that only kept the settings would show
the new declaration as though it were the one agreed to.

**Disconnecting marks the row and never removes it.** `disconnected_at` and `disconnected_by` move
from nothing to a value once, which is the only update the application role may make, and a source
connected again is a new row. One live row per source is a partial unique index, so the history of
every connection stays and a second live connection of one source is refused by the table as well
as by the store's lock. No `deleted_at` and no `SoftDeleteMixin`: a disconnected row is not retired,
it is the record that a source was read and when that stopped.

**No foreign key to `auth.principal` on either actor column**, for the reason
`brain.tables.credential` gives about `written_by`: an actor is a value, and the record of who let
the system read a source outlives the person.

Task ids: M42.6.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.connectors.manifest import DIGEST_CHARS
from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: The widest source name `CONNECTOR_NAME_PATTERN` admits, and one more for nothing.
CONNECTOR_CHARS: Final = 64

#: The digest's shape: `manifest_digest` is a lower-case hex sha256.
DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"


class ConnectorConnectionRow(Base):
    """`ops.connector_connection`. One source connected once, by one person, and when it stopped."""

    __tablename__ = "connector_connection"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The source's short name, which is also its vault slot's last segment and the ledger subject.
    connector: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    #: The source's own identifiers the manifest is built from. Never a credential.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: `manifest_digest` of the manifest agreed to at connect.
    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: Who connected it. The ledger entry's actor, read off this column by the trigger.
    connected_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The database's clock, in the transaction the ledger entry is appended in.
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: Who disconnected it, or nothing while it is connected.
    disconnected_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        CheckConstraint("jsonb_typeof(settings) = 'object'", name="settings_are_an_object"),
        CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        CheckConstraint(f"connected_by ~ '{IDENTIFIER}'", name="connected_by_shape"),
        CheckConstraint(
            f"disconnected_by IS NULL OR disconnected_by ~ '{IDENTIFIER}'",
            name="disconnected_by_shape",
        ),
        CheckConstraint(
            "(disconnected_at IS NULL) = (disconnected_by IS NULL)",
            name="a_disconnection_names_who_and_when",
        ),
        # One live connection per source. See the module docstring.
        Index(
            "uq_connector_connection_connector_live",
            "connector",
            unique=True,
            postgresql_where=text("disconnected_at IS NULL"),
        ),
        {"schema": "ops"},
    )
