"""A knowledge item gets a row, and the row holds everything about a document except its text.

`brain.knowledge.item.KnowledgeItem` has been the record of a document since M7.4.1, and nothing
stored one. The review date it carries was therefore a date nothing could read, which that
module calls documentation rather than a control. This is the row.

**The item is the document and a chunk is its copy, so the row is the source and `know.chunk`
is derived from it.** `brain.knowledge.chunking.permissions_of` reads a chunk's owner, scope
and visibility off the item, and `chunk_document` is the only source of a chunk. The owner,
department, visibility, state and title a chunk row carries are that copy, denormalised so the
reach predicate is one query over one table. Reading an item back out of its chunks would run
the arrow the wrong way, and it cannot be done anyway: no chunk carries who verified the
document, when, or when somebody must look again.

**No `content` column, and the absence is the reconciliation.** What an item says is the text
its chunks are cut from, and `know.chunk.body` holds it behind the corpus's policy. A second
copy here would be a second place the corpus lives, outside the reach predicate that is the
whole of what protects it. `brain.knowledge.item.UnderReview` is why the re-verification sweep
does not need it.

Rejected, and each for the reason it would break:

- **Review columns on `know.chunk`.** A review date belongs to a document and a chunk is a
  passage of one, so every chunk would carry a copy, the copies could disagree, and a sweep
  over chunks would open one task per passage. Re-chunking retires a document's chunks, which
  would retire its verification with them.
- **The whole `KnowledgeItem` here, text included.** See the paragraph above.
- **A foreign key from `know.chunk.document_id` to this table.** The corpus is written by
  ingestion and this row by whoever stewards the document, and neither writer exists yet; a
  key added now would decide an order between two writers nobody has built. `0040` adds none.

**The constraints are the ones the policy rests on, not a second copy of the model's.** The
department slug and "a department item names its department" are `0009`'s for the same reason
they are there: the policy splits `app.departments` on a comma, and a department item with no
department matches no branch and is invisible to its own team. The half-verification refusal
is `KnowledgeItem`'s own rule, held by the database because the sweep reads rows and not models.

Task ids: M34.2.1.3
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.knowledge.item import KnowledgeState
from brain.knowledge.search import (
    DEPARTMENT_CHARS,
    DOCUMENT_ID_CHARS,
    OWNER_ID_CHARS,
    REFERENCE_SQL_PATTERN,
    SLUG_SQL_PATTERN,
    TITLE_CHARS,
)
from brain.knowledge.visibility import Visibility
from brain.tables.identity import one_of


class KnowledgeItemRow(TimestampMixin, Base):
    """`know.item`. One document's stewardship: who answers for it, who vouched, when to look again.

    Keyed on the item id, which is the `document_id` every chunk of the document carries. No
    `deleted_at`: a withdrawn item is `archived` and a replaced one `superseded`, and both stay
    on file, which is `brain.knowledge.item`'s argument about explaining an old answer.
    """

    __tablename__ = "item"

    item_id: Mapped[str] = mapped_column(String(DOCUMENT_ID_CHARS), primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_CHARS), nullable=False, server_default="")
    #: The steward, as on `KnowledgeItem`. Never moves; see `brain.knowledge.item_store`.
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_CHARS), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    department: Mapped[str | None] = mapped_column(String(DEPARTMENT_CHARS), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(OWNER_ID_CHARS), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes: Mapped[str | None] = mapped_column(String(DOCUMENT_ID_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(f"item_id ~ '{REFERENCE_SQL_PATTERN}'", name="item_id_is_a_reference"),
        CheckConstraint("length(btrim(owner_id)) > 0", name="owned"),
        CheckConstraint(one_of("visibility", Visibility), name="visibility"),
        CheckConstraint(one_of("state", KnowledgeState), name="state"),
        CheckConstraint(
            f"department IS NULL OR department ~ '{SLUG_SQL_PATTERN}'", name="department_is_a_slug"
        ),
        CheckConstraint(
            "visibility <> 'department' OR department IS NOT NULL",
            name="a_department_item_names_its_department",
        ),
        CheckConstraint(
            "(verified_by IS NULL) = (verified_at IS NULL)",
            name="a_verification_is_a_person_and_a_date",
        ),
        # The sweep's access path: it asks for items whose date has arrived, and most items
        # have none.
        Index("ix_item_review_by", "review_by", postgresql_where=text("review_by IS NOT NULL")),
        {"schema": "know"},
    )
