"""`agent.audience_extra`: a department or a person named beside an agent's level (M13.8.19).

`0223` builds it. `brain.agents.model.AgentAudience` carries a level and the one department or
owner that level needs; this holds the others an agent's steward chose to offer it to.

**It is discovery and there is no column for reach.** A row says who may find the agent in a picker
and start it, and `brain.agents.model.audience_scope`, the only predicate a run is narrowed by,
does not read this table. See `AN_ADDED_AUDIENCE_GAINS_DISCOVERY_AND_NEVER_REACH`.

**Added by one person and withdrawn by one person, and the row stays.** A removal is two columns
written once (`removed_at`, `removed_by`), `group_install`'s shape, so what the audience was on a
day a question was answered can be read back. A department or a person is named once at a time,
by a partial unique index over the live rows.

**Values, not keys.** The agent, the department and the person are names with no foreign key, so
retiring a department or a person deletes nobody's record of having been offered an agent, and
naming a person who does not exist is not told apart from naming one who does, for the reason
`gate.role_nomination` gives.

Task ids: M13.8.19
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS, DEPARTMENT_CHARS
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: The widest kind word, `department`, with room.
KIND_CHARS: Final = 16


class ExtraKind(enum.StrEnum):
    """What a row names."""

    DEPARTMENT = "department"
    PERSON = "person"


class AudienceExtraRow(Base):
    """One department or person offered one agent, and when and by whom it was withdrawn."""

    __tablename__ = "audience_extra"
    __table_args__ = (
        CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        CheckConstraint(one_of("kind", ExtraKind), name="kind"),
        CheckConstraint("length(btrim(value)) > 0", name="value_present"),
        CheckConstraint("length(btrim(added_by)) > 0", name="added_by_present"),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        Index(
            "uq_audience_extra_one_live_row_per_name",
            "agent_id",
            "kind",
            "value",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        {"schema": "agent"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    #: A department's slug or a principal's id, by `kind`. The wider of the two widths.
    value: Mapped[str] = mapped_column(
        String(max(DEPARTMENT_CHARS, PRINCIPAL_ID_CHARS)), nullable=False
    )
    added_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    removed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
