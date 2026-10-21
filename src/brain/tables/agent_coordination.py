"""`agent.agent_callee` and `agent.agent_fanout`: what a coordinating agent may call.

`0272` builds both. A coordinating agent hands a subtask to a specialist, and two facts about that
are an administrator's to set and nobody else's: **which agents it may hand a subtask to**, and
**whether it may run them at the same time**. Neither is read from anything a model wrote.

**Neither confers reach, and there is no column that could.** A callee row says an agent may be
asked; what the specialist then reaches is the asker's reach narrowed by both agents and by the
subtask's own ceiling (`brain.orchestration.delegation`), and `brain.agents.model.audience_scope`
and `entitlement_ceiling` read neither table. A callee row that widened anything would make linking
two agents a grant, and installing and linking an agent are configuration while granting is a
change to somebody's entitlements.

**A link is directional and the row stays.** `coordinator_id` may call `callee_id`; the reverse is
a different row. Withdrawing a link writes `removed_by` and `removed_at` once,
`agent.audience_extra`'s shape, so what a coordinator was allowed to call on the day a run happened
can be read back, and a partial unique index over the live rows makes a link one row at a time. An
agent may not be its own callee: a coordinator calling itself is a loop the depth cap would meet at
the third hop, and the cheaper refusal is that the row cannot exist.

**Fan-out is a grant in its own table and not a column on the agent.** The agent row is rewritten by
templates, upgrades and the builder, and a switch that lives there would be reset by whichever of
them wrote last. Here it is a dated row with a person on it: present and live is enabled, a
withdrawal is the same two columns, and an agent with no row runs its specialists one after another.

**Values, not keys.** The agents and the people are names with no foreign key, for
`agent.audience_extra`'s reason: retiring an agent must not rewrite the record of who allowed what.

Task ids: M18.5.1, M18.6.2
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS


class AgentCalleeRow(Base):
    """One agent another agent may hand a subtask to, and when and by whom that was withdrawn."""

    __tablename__ = "agent_callee"
    __table_args__ = (
        CheckConstraint("length(btrim(coordinator_id)) > 0", name="coordinator_present"),
        CheckConstraint("length(btrim(callee_id)) > 0", name="callee_present"),
        CheckConstraint("coordinator_id <> callee_id", name="an_agent_does_not_call_itself"),
        CheckConstraint("length(btrim(added_by)) > 0", name="added_by_present"),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        Index(
            "uq_agent_callee_one_live_row_per_link",
            "coordinator_id",
            "callee_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        {"schema": "agent"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    coordinator_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    callee_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    added_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    removed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentFanoutRow(Base):
    """One agent allowed to run its specialists at the same time, and when that was withdrawn."""

    __tablename__ = "agent_fanout"
    __table_args__ = (
        CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        CheckConstraint("length(btrim(enabled_by)) > 0", name="enabled_by_present"),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        Index(
            "uq_agent_fanout_one_live_row_per_agent",
            "agent_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        {"schema": "agent"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    enabled_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    enabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    removed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
