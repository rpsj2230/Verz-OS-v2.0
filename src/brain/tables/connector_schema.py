"""`ops.connector_schema_check`: what each night's schema check found about one kind of record.

`brain.ops.schema_drift` decides which fields a connected source no longer answers and
`brain.ops.schema_drift_run` reads the source for it. This is where the finding survives until the
next night, so a question asked at noon can be told its source's field is gone and the Connectors
screen can say which. The migration that creates it holds the policies and the grants.

**One row per night per kind of record, appended and never edited**, for the reason
`brain.tables.connector_sync` gives about attempts: a finding updated in place says a source was
checked last night whether or not it was read, and a check that has failed for a week would show
a fresh time. The newest row for a connection and an entity is the finding; the ones before it
are the history of when a field went and when it came back.

**It names the connection by value, not by a foreign key**, for `ops.connector_sync`'s reason and
under the rule `tests/unit/test_tables.py::test_no_grant_table_points_at_a_connector` holds: a
connection is never removed, and a source connected again is a new connection whose findings
start afresh, so a field gone under the old mapping is not held against the new one.

**Names and counts, never a value.** Both lists hold mapping targets, which are this release's
field names, and the check constraint refuses anything else in either, so nothing a record held can
be written here by any path. See `brain.ops.schema_drift.FIELD_NAME`.

Task ids: M11.8.7
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.connector_connection import CONNECTOR_CHARS

#: The longest field or entity name kept. A mapping target is at most this long.
NAME_CHARS: Final = 60

#: What a name in either list, and the entity, must look like. Held equal to
#: `brain.ops.schema_drift.FIELD_NAME` by a test.
NAME_PATTERN: Final = "[a-z][a-z0-9_]{0,59}"

#: Every element of a list is a name: the list read as comma-joined text is names and commas.
NAMES_ONLY: Final = f"^({NAME_PATTERN}(,{NAME_PATTERN})*)?$"


class ConnectorSchemaCheckRow(Base):
    """`ops.connector_schema_check`. One night's finding about one kind of record (M11.8.7)."""

    __tablename__ = "connector_schema_check"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The connection read. See the module docstring for why not a foreign key.
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: The source's name, carried so the screen's read needs no join.
    connector: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    #: The kind of record, as the connector's reading names it.
    entity: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Records read tonight across the calls for this kind. Nought when none was read.
    sampled: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The fields a record answered at the last night that read one.
    answered: Mapped[list[str]] = mapped_column(
        ARRAY(String(NAME_CHARS)), nullable=False, server_default=text("'{}'")
    )
    #: The fields answered on an earlier night that no record answers now.
    missing: Mapped[list[str]] = mapped_column(
        ARRAY(String(NAME_CHARS)), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        CheckConstraint(f"entity ~ '^{NAME_PATTERN}$'", name="entity_shape"),
        CheckConstraint("sampled >= 0", name="sampled_is_not_negative"),
        CheckConstraint(
            f"array_to_string(answered, ',') ~ '{NAMES_ONLY}' "
            f"AND array_to_string(missing, ',') ~ '{NAMES_ONLY}'",
            name="names_only",
        ),
        Index(
            "ix_connector_schema_check_connection_entity",
            "connection_id",
            "entity",
            "checked_at",
        ),
        {"schema": "ops"},
    )
