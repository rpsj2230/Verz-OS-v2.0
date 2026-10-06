"""`er.review_item`: a pair of records the cascade could not settle, waiting for a person.

`brain.resolution.guardrails.ReviewItem` was a type with nowhere to live, and
`guardrails.NOTHING_HERE_IS_PERSISTED` said so. This is where it lives.

**One row per pair, ever.** The pair is the two source records, ordered as `query.score_query`
orders them (left before right by their three key columns), and the six columns are unique
together. A pair a reviewer rejected is not raised again on the next run, and a pair already
waiting is not raised twice: both are what a queue nobody finishes looks like.

**Evidence is field names and weights, and nothing else.** `guardrails.Evidence` has no slot for a
value and the JSON here holds exactly its two fields, so a review item cannot carry what either
record says. The reason is the cascade's own sentence, which names stages and kinds and never a
value.

**No count and no score.** There is no total on the row for a screen to sort or threshold on,
for `guardrails.ReviewItem`'s reason.

**A decision is written once, in the deciding person's own name.** `state` moves from `open` to
`merged` or `rejected` and never back, and `decided_by` must be the session's principal. An
unmerge does not reopen the item: it is a new decision recorded where merges are, and the item
keeps saying what the reviewer decided at the time.

Task ids: M14.3.4, M14.6.4, M14.8.5
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.db import Base
from brain.resolution.canonical import EntityType
from brain.tables.identity import one_of
from brain.tables.resolution import (
    CREATED_BY_CHARS,
    ENTITY_CHARS,
    ENTITY_ID_CHARS,
    ENUM_CHARS,
    SOURCE_CHARS,
    SOURCE_ID_CHARS,
)

#: The table this module declares.
TABLES: tuple[str, ...] = ("er.review_item",)

#: How wide an item id is: a short prefix and a uuid's hex.
ITEM_ID_CHARS = 40

#: The cascade's reason, or the money or hold reason, in words.
REASON_CHARS = 400


class ReviewOrigin(enum.StrEnum):
    """Why a pair reached a person rather than being settled."""

    #: The cascade put it in the band between its thresholds, or could not measure the names.
    CASCADE = "cascade"
    #: The cascade matched it and one side carries financial records (M14.5.6).
    MONEY = "money"
    #: The cascade matched it and it was held: unattended merging is off, a cap would be
    #: breached, or a stronger identifier names another entity.
    HELD = "held"


class ReviewState(enum.StrEnum):
    OPEN = "open"
    MERGED = "merged"
    REJECTED = "rejected"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


class ReviewItemRow(Base):
    """`er.review_item`: two records, why they are here, the evidence, and what was decided."""

    __tablename__ = "review_item"

    item_id: Mapped[str] = mapped_column(String(ITEM_ID_CHARS), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(ENUM_CHARS), nullable=False)
    left_source: Mapped[str] = mapped_column(String(SOURCE_CHARS), nullable=False)
    left_entity: Mapped[str] = mapped_column(String(ENTITY_CHARS), nullable=False)
    left_source_id: Mapped[str] = mapped_column(String(SOURCE_ID_CHARS), nullable=False)
    right_source: Mapped[str] = mapped_column(String(SOURCE_CHARS), nullable=False)
    right_entity: Mapped[str] = mapped_column(String(ENTITY_CHARS), nullable=False)
    right_source_id: Mapped[str] = mapped_column(String(SOURCE_ID_CHARS), nullable=False)
    #: The two entities the records resolved to when the pair was raised.
    left_entity_id: Mapped[str] = mapped_column(String(ENTITY_ID_CHARS), nullable=False)
    right_entity_id: Mapped[str] = mapped_column(String(ENTITY_ID_CHARS), nullable=False)
    origin: Mapped[str] = mapped_column(String(ENUM_CHARS), nullable=False)
    #: The cascade stage that answered, one to four.
    stage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    #: `[{"field": ..., "weight": ...}]`, `guardrails.Evidence` and nothing more.
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(ENUM_CHARS), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    decided_by: Mapped[str | None] = mapped_column(String(CREATED_BY_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_present("item_id"), name="item_id_present"),
        CheckConstraint(one_of("entity_type", EntityType), name="entity_type_known"),
        CheckConstraint(one_of("origin", ReviewOrigin), name="origin_known"),
        CheckConstraint(one_of("state", ReviewState), name="state_known"),
        CheckConstraint(f"left_source ~ '{OBJECT_NAME_PATTERN}'", name="left_source_is_a_name"),
        CheckConstraint(f"right_source ~ '{OBJECT_NAME_PATTERN}'", name="right_source_is_a_name"),
        CheckConstraint(
            "(left_source, left_entity, left_source_id)"
            " < (right_source, right_entity, right_source_id)",
            name="pair_is_ordered",
        ),
        CheckConstraint("stage BETWEEN 1 AND 4", name="stage_is_a_stage"),
        CheckConstraint(_present("reason"), name="reason_present"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="evidence_is_a_list"),
        CheckConstraint(
            "(state = 'open') = (decided_by IS NULL AND decided_at IS NULL)",
            name="decided_once",
        ),
        Index(
            "uq_review_item_pair",
            "left_source",
            "left_entity",
            "left_source_id",
            "right_source",
            "right_entity",
            "right_source_id",
            unique=True,
        ),
        Index("ix_review_item_state", "state"),
        {"schema": "er"},
    )
