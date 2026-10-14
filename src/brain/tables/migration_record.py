"""`ops.migration_record`: the documents a migration from another system is run on, kept (M37).

The row behind `brain.ops.migration_record_store`. `0241` builds it. A migration has three
documents that are written, argued over and re-written over weeks, and each had a module of
refusals (`brain.migration.inventory`, `parallel`, `decommission`) and nowhere to be kept: the
register of what the old system holds and what happens to each of it, the comparison period with
the criteria agreed before it began, and the cutover record. Until this table they ended with the
process.

**A document per version, appended and never edited.** Each save is a new row of one kind, the
newest is the current one, and the earlier ones stay. A migration register is the thing somebody
is asked, months later, to account for ("what did the criteria say when the period started"), and a
row overwritten in place answers with the last edit. This is the shape `ops.plugin_version` and
`ops.budget_version` have, for the same reason.

**The body is the domain's own JSON and is read back through the domain's own constructors.** The
route builds `Catalogue`, `Period` and `Decommission` from a body and refuses what they refuse, so
what is stored has passed them once; reading it back goes through them again, because a row is also
something that arrives by being loaded. No column here repeats a finding: the gaps are computed on
read, so they cannot be stale.

**Never an answer from the old system.** `brain.migration.parallel` records that two answers
differed and the question, and holds neither answer (`brain.migration.carry` has the argument), and
nothing here has a column that could.

Task ids: M37.1.1.1
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longest kind, with room.
KIND_CHARS: Final = 16


class RecordKind(enum.StrEnum):
    """The three documents. A fourth is a decision about what a migration is, not a value."""

    #: What the old system holds, what happens to each, and what its permissions become.
    REGISTER = "register"
    #: The comparison period, its criteria agreed before it began, and the questions asked.
    PARALLEL = "parallel"
    #: The cutover: read-only, archive, revocations, jobs, final backup and the acts done.
    CUTOVER = "cutover"


class MigrationRecordRow(Base):
    """One saved version of one migration document, and who saved it."""

    __tablename__ = "migration_record"
    __table_args__ = (
        CheckConstraint(one_of("kind", RecordKind), name="kind"),
        CheckConstraint("jsonb_typeof(body) = 'object'", name="body_object"),
        CheckConstraint("length(btrim(recorded_by)) > 0", name="a_person_recorded"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
