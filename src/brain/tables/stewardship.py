"""`ops.connector_steward` and `gate.self_grant`: who stewards a source, and every grant to oneself.

`migrations/versions/0167_stewards_and_self_grants.py` holds the argument for both tables, their
policies and their triggers; what is here is the models that mirror them.

**A steward is named by appending a row, never by editing one.** The source's steward is the row
named last for it, so the history of who answered for a source stays, and naming a steward is one
insert whose ledger entry the database appends in the same transaction.

**A self-grant row is written by the database and never by the application.** The two triggers on
`gate.capability_grant` and `gate.capability_pack_assignment` add it when a grant's principal is
the actor the transaction is attributed to, so no code path can grant somebody themselves and
leave no record a steward could be told of. The row keeps the capabilities and the scope as they
were granted and outlives the grant's retirement.

**No foreign key to `auth.principal`** on any person column, for the reason
`brain.tables.credential` gives: an actor is a value, and the record outlives the person.

Task ids: M7.7.2
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.gate import CAPABILITY_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: The widest pack name `gate.capability_pack.name` holds.
PACK_NAME_CHARS: Final = 80


class SelfGrantKind(enum.StrEnum):
    """The two ways a grant reaches a person, and so the two a self-grant can be made through."""

    CAPABILITY = "capability"
    PACK = "pack"


class ConnectorStewardRow(Base):
    """`ops.connector_steward`. One steward named for one source, by one person, and when."""

    __tablename__ = "connector_steward"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The source's short name, the same as `ops.connector_connection.connector`.
    connector: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    #: Who answers for the source from now on.
    steward_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: Who named them. The insert policy holds it to the transaction's attributed actor.
    named_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    named_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        CheckConstraint(f"steward_id ~ '{IDENTIFIER}'", name="steward_id_shape"),
        CheckConstraint(f"named_by ~ '{IDENTIFIER}'", name="named_by_shape"),
        Index("ix_connector_steward_connector", "connector", "named_at"),
        {"schema": "ops"},
    )


class SelfGrantRow(Base):
    """`gate.self_grant`. One grant a person made to themselves, as it was granted."""

    __tablename__ = "self_grant"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The `gate.capability_grant` or `gate.capability_pack_assignment` row it was recognised on.
    grant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: Who granted it and who received it, which is the same person.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The capability, or the pack's capabilities as they stood when it was assigned.
    capabilities: Mapped[list[str]] = mapped_column(
        ARRAY(String(CAPABILITY_CHARS)), nullable=False
    )
    #: The scope as granted, `brain.core.scope.Scope`'s own serialisation.
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: The pack's name for a pack, and nothing for a direct grant.
    pack: Mapped[str | None] = mapped_column(String(PACK_NAME_CHARS), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(one_of("kind", SelfGrantKind), name="kind"),
        CheckConstraint(f"principal_id ~ '{IDENTIFIER}'", name="principal_id_shape"),
        CheckConstraint("jsonb_typeof(scope) = 'object'", name="scope_is_an_object"),
        CheckConstraint("(kind = 'pack') = (pack IS NOT NULL)", name="a_pack_is_named"),
        UniqueConstraint("kind", "grant_id", name="one_row_per_grant"),
        Index("ix_self_grant_at", "at"),
        {"schema": "gate"},
    )
