"""`know.classified_table` and `know.classified_row`: a price list held as classified rows.

**A price list is rows, not a document (M7.7.3).** Indexed as text, the cost and the sell price
of one product sit in one passage, and a passage is answered whole or withheld whole, so the
company either shows everybody the cost or shows nobody the price. Held as rows under a
classification, each column is answered to the people its rule admits and absent for
everybody else, which is `brain.knowledge.columns` applied to data somebody uploaded.

**The classification lives on the table row, as one JSON array, and not in `gate.field_policy`.**
That table mirrors `FieldRule` and has been waiting for a writer since `0002`, and it was the
first place considered. It carries no derivation, and adding one means amending a `0002` table
whose shape the model test pins, for a store that would then hold one table's classification
across as many rows as it has columns and have to keep them consistent with the table they
describe. A table's classification is one decision about one set of columns, and
`brain.knowledge.columns.TableClassification` refuses one that does not construct as a whole,
so it is stored as a whole: an update replaces the array in one statement, and there is no
state in which half of a change has landed.

**Rows are versioned rather than replaced.** A second upload of the same price list writes
its rows under the next `version` and moves the table's `version` to it, so no row is ever
updated or deleted and the application holds no DELETE on either table. "What did we quote
in March" is answered by the rows of March's version, which is also what a wrong quote is
investigated with.

**A row's visibility is decided by the statement that reads it, not by a policy here.** The
row-level security on `know.classified_row` admits every row to the application role, because
which columns a person may see is a function of their grants, which a policy cannot read, and
the row plane already composes both the column list and the row scope into the statement
(`brain.knowledge.classified_rows.compile_table_query`). A policy that tried would be a second
answer to one question, in SQL, maintained by nobody who maintains the first.

Task ids: M7.5.1, M7.7.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.core.field_policy import NAME_PATTERN
from brain.db import Base, SoftDeleteMixin, TimestampMixin

#: `brain.core.envelope.Entity.entity` is 60 wide, and a table's entity is one.
ENTITY_CHARS = 60
#: A column name, as `brain.knowledge.columns.MAX_COLUMN_NAME_CHARS` bounds it.
COLUMN_CHARS = 60
#: The administrator's own name for the table.
TITLE_CHARS = 200
#: Every locally minted principal id in this system.
PRINCIPAL_ID_CHARS = 128


class ClassifiedTableRow(TimestampMixin, SoftDeleteMixin, Base):
    """`know.classified_table`. One uploaded table, its classification, and which rows are live.

    Keyed on the entity, because the entity is what every capability is written against:
    `read:<entity>` admits the table and `read:<entity>.<column>` a restricted column, so two
    live tables sharing one would be one set of grants governing two sets of rows.
    """

    __tablename__ = "classified_table"

    entity: Mapped[str] = mapped_column(String(ENTITY_CHARS), primary_key=True)
    title: Mapped[str] = mapped_column(String(TITLE_CHARS), nullable=False)
    #: The column a question names a row by, the product's name or its SKU.
    key_column: Mapped[str] = mapped_column(String(COLUMN_CHARS), nullable=False)
    #: `[{column, required_capability, classification, derived_from}]`, in the upload's order.
    columns: Mapped[Any] = mapped_column(JSONB, nullable=False)
    #: The upload whose rows are live. Rows of earlier versions stay, unread.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"entity ~ '{OBJECT_NAME_PATTERN}'", name="entity_is_a_name"),
        CheckConstraint(f"key_column ~ '{NAME_PATTERN}'", name="key_column_is_a_name"),
        CheckConstraint("length(btrim(title)) > 0", name="titled"),
        CheckConstraint("jsonb_typeof(columns) = 'array'", name="columns_is_an_array"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("length(btrim(created_by)) > 0", name="created_by_present"),
        CheckConstraint("length(btrim(updated_by)) > 0", name="updated_by_present"),
        {"schema": "know"},
    )


class ClassifiedRecordRow(Base):
    """`know.classified_row`. One row of one upload of one table, as text keyed by column name.

    No timestamps of its own beyond the insert and no `deleted_at`: a row is written once, under
    the version of the upload it came in, and is never changed. See the module docstring.
    """

    __tablename__ = "classified_row"

    entity: Mapped[str] = mapped_column(String(ENTITY_CHARS), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: The row's place in the file, from zero. Also its id in an answer.
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    fields: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("jsonb_typeof(fields) = 'object'", name="fields_is_an_object"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("version > 0", name="version_positive"),
        ForeignKeyConstraint(
            ["entity"],
            ["know.classified_table.entity"],
            name="fk_classified_row_entity_classified_table",
            ondelete="RESTRICT",
        ),
        {"schema": "know"},
    )
