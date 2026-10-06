"""`ops.retrieval_event`: one retrieval a person was answered from, as the learning signal reads it.

`brain.knowledge.quality.RetrievalEvent` is the record and this is its storage, column for field,
and nothing else. **Read the absences first, as that type asks.** No document or chunk reference,
no question, no principal, no reach, no trace, and no count taken before the reach predicate or of
anything withheld: the table has no column any of those could be written to, and a test holds the
column set to the record's fields. A log from which a person's movements could be reconstructed by
an operator who cannot read what they read is the thing `brain.ops.tracing` refuses to be, and so
is this.

**`used` is the one column that changes, and only by growing.** It is the positions in the
person's own list that they followed, one-based, sorted, each once, each inside `returned`; the
check constraints hold the length and the lower bound, `brain.ops.retrieval_store` holds the rest
in the statement that adds one, and `brain_app` may update that column and no other.

Task ids: M15.3.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: How wide the joined retriever names may be. `lexical.vector` is fourteen.
RETRIEVERS_CHARS: Final = 64

#: `brain.knowledge.quality.RETRIEVER_RE` for each name, joined on its separator.
RETRIEVERS_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"


class RetrievalEventRow(Base):
    """`ops.retrieval_event`. One retrieval, as much of it as may be written down."""

    __tablename__ = "retrieval_event"

    #: Minted by the application and handed to the page, which sends it back with a position.
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: The retrievers that ran, sorted and joined on `quality.RETRIEVER_SEPARATOR`.
    retrievers: Mapped[str] = mapped_column(String(RETRIEVERS_CHARS), nullable=False)
    returned: Mapped[int] = mapped_column(Integer, nullable=False)
    corroborated: Mapped[int] = mapped_column(Integer, nullable=False)
    used: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'")
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Served from the retrieval cache rather than ranked for this request. Written once, as
    #: every column but `used` is: `brain_app` may update `used` alone.
    from_cache: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint(f"retrievers ~ '{RETRIEVERS_PATTERN}'", name="retrievers_are_names"),
        CheckConstraint("returned >= 0", name="returned_is_a_count"),
        CheckConstraint(
            "corroborated >= 0 AND corroborated <= returned", name="corroborated_of_returned"
        ),
        CheckConstraint("cardinality(used) <= returned", name="used_within_returned"),
        CheckConstraint("1 <= ALL(used)", name="used_is_one_based"),
        CheckConstraint("latency_ms >= 0", name="latency_is_a_duration"),
        Index("ix_retrieval_event_at", "at"),
        {"schema": "ops"},
    )
