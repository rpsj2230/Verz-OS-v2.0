"""`ops.custom_connector`: a connector for a new API, as submitted, and who reviewed it.

`migrations/versions/0203_custom_connector.py` holds the argument for the table, its policies and
its trigger; what is here is the model that mirrors it, and `brain.ops.custom_connector` is what a
row means.

**One row per definition, edited in place, and every edit is a new revision waiting for review.**
The row holds the definition as its submitter last wrote it, so the catalogue reads the approved
rows and nothing else. A change sets the state back to unreviewed and the reviewer back to nobody in
the same statement, which the update policy holds: a row with a reviewer is a row its reviewer
wrote, and a reviewer is never the person who submitted the revision they reviewed.

**No foreign key to `auth.principal`**, for the reason `brain.tables.credential` gives: an actor is
a value, and the record outlives the person.

Task ids: M11.7.8
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: The states a definition is in. `brain.ops.custom_connector.ReviewState`'s values, copied for
#: the migration's reason and held equal by `tests/unit/test_custom_connector_store.py`.
STATES: Final = ("unreviewed", "approved", "rejected")

#: The key schemes and credential shapes a definition may name, as the domain allows them.
KEY_SCHEMES: Final = ("bearer", "basic_key_as_user", "none")
CREDENTIAL_SHAPES: Final = ("key", "none")

#: Widths. The label and the cited page are the domain's own caps.
LABEL_CHARS: Final = 80
CITED_CHARS: Final = 500
DEPARTMENT_CHARS: Final = 64
PARAMETER_CHARS: Final = 80

#: A department's short name, as a constraint can hold it without a non-capturing group, which
#: SQLAlchemy reads as a bind parameter (see CLAUDE.md on `knowledge/search.py`).
DEPARTMENT_PATTERN: Final = r"^[a-z][a-z0-9_]{0,63}$"

#: The largest stored document, in bytes of its text. Twice the paste cap, because JSONB's text
#: form spaces what a paste may not have.
DOCUMENT_BYTES: Final = 512 * 1024


class CustomConnectorRow(Base):
    """`ops.custom_connector`. One definition, its revision, and its review."""

    __tablename__ = "custom_connector"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    label: Mapped[str] = mapped_column(String(LABEL_CHARS), nullable=False)
    #: The OpenAPI document as submitted, parsed.
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: Each entity's operations and field mapping, with each field's classification.
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    key_scheme: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_shape: Mapped[str] = mapped_column(String(16), nullable=False)
    ceiling_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    ceiling_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ceiling_cited: Mapped[str] = mapped_column(String(CITED_CHARS), nullable=False)
    department: Mapped[str] = mapped_column(String(DEPARTMENT_CHARS), nullable=False)
    page_parameter: Mapped[str | None] = mapped_column(String(PARAMETER_CHARS), nullable=True)
    page_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint(f"name ~ '{CONNECTOR_NAME_PATTERN}'", name="name_shape"),
        CheckConstraint("length(btrim(label)) > 0", name="label_given"),
        CheckConstraint(
            f"octet_length(document::text) <= {DOCUMENT_BYTES}", name="document_bounded"
        ),
        CheckConstraint("jsonb_typeof(document) = 'object'", name="document_is_an_object"),
        CheckConstraint("jsonb_typeof(entities) = 'array'", name="entities_are_a_list"),
        CheckConstraint(
            "key_scheme IN (" + ", ".join(f"'{one}'" for one in KEY_SCHEMES) + ")",
            name="key_scheme",
        ),
        CheckConstraint(
            "credential_shape IN (" + ", ".join(f"'{one}'" for one in CREDENTIAL_SHAPES) + ")",
            name="credential_shape",
        ),
        CheckConstraint("ceiling_per_minute > 0", name="ceiling_per_minute_measured"),
        CheckConstraint(
            "ceiling_per_day IS NULL OR ceiling_per_day > 0", name="ceiling_per_day_measured"
        ),
        CheckConstraint("ceiling_cited ~ '^https://'", name="ceiling_cited"),
        CheckConstraint(f"department ~ '{DEPARTMENT_PATTERN}'", name="department_shape"),
        CheckConstraint(
            "(page_parameter IS NULL) = (page_size IS NULL)", name="paging_whole_or_none"
        ),
        CheckConstraint("page_size IS NULL OR page_size > 0", name="page_size_positive"),
        CheckConstraint("state IN (" + ", ".join(f"'{one}'" for one in STATES) + ")", name="state"),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_shape"),
        CheckConstraint(
            "(state = 'unreviewed') = (reviewed_by IS NULL AND reviewed_at IS NULL)",
            name="a_decision_names_its_reviewer",
        ),
        CheckConstraint(
            "reviewed_by IS NULL OR reviewed_by <> submitted_by",
            name="nobody_reviews_their_own",
        ),
        {"schema": "ops"},
    )
