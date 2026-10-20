"""`ops.coordinated_run`: how a coordinating agent's run went, kept without what it was about.

`0272` builds it. A run in which one agent handed subtasks to others is a value that ended with the
request, so "did it run them together, and if not why not" had no answer afterwards. This is the
row that keeps it: **how the specialists were run** (`mode`), **why they were not run together**
(`why`, from a closed vocabulary), each child's status, depth, reach hash and cost, and whether the
answer was complete.

**Numbers, words from a closed list and hashes, and nothing the asker said.** No request, no
objective, no result value, no specialist's text. A child is a subtask id the planner chose, the
specialist's agent id, its depth, the hash of the reach it ran at (`EntitlementSet.ent_hash`, which
answers the one question an audit asks, whether two runs reached the same, and is not a copy of
anybody's permissions), the word for what became of it and what it cost. That is the same boundary
`ops.fanout_gate` draws for the gate's decision, and for the same reason: this table has its own
retention and nobody should be able to read a question out of it.

**The vocabulary is closed in the database.** `mode` and every word of `why` are checked against the
enums the engine uses, and `children` is checked to be an array, so a row written by another route
cannot say something the engine never says. A child's own fields are held to their shape in
`brain.ops.coordinated_run_store`, which builds the row from the engine's record and nothing else.

**Written once, in the session's own name, never edited.** `0272`'s insert policy admits a row whose
`asked_by` is the session's principal, and no UPDATE or DELETE is granted. The asker is an actor and
not an owner: the row outlives the account, as the gate's decision does.

Task ids: M18.6.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.db import Base
from brain.orchestration.coordinator import Mode, Why
from brain.tables.fanout_gate import RUN_ID_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: The widest word of `Why`, with room.
WHY_CHARS: Final = 32


def _words_within(column: str, enum_type: type[Mode] | type[Why]) -> str:
    listed = ", ".join(f"'{one.value}'" for one in sorted(enum_type, key=lambda one: one.value))
    return f"{column} <@ ARRAY[{listed}]::character varying[]"


class CoordinatedRunRow(Base):
    """One run of a coordinating agent: how it ran, why not together, what each child came to."""

    __tablename__ = "coordinated_run"
    __table_args__ = (
        CheckConstraint(one_of("mode", Mode), name="mode"),
        CheckConstraint(_words_within("why", Why), name="why_is_a_known_reason"),
        CheckConstraint(
            "(mode = 'parallel') = (cardinality(why) = 0)",
            name="parallel_has_no_reason_not_to_be",
        ),
        CheckConstraint("length(btrim(run_id)) > 0", name="run_present"),
        CheckConstraint("length(btrim(coordinator_id)) > 0", name="coordinator_present"),
        CheckConstraint("length(btrim(asked_by)) > 0", name="an_actor_asked"),
        CheckConstraint("jsonb_typeof(children) = 'array'", name="children_are_a_list"),
        CheckConstraint("total_minor >= 0", name="cost_not_negative"),
        Index("ix_coordinated_run_by_start", "started_at"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), nullable=False)
    coordinator_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    asked_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: `parallel` or `sequential`, from `brain.orchestration.coordinator.Mode`.
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Why the specialists were not run together, from `Why`. Empty exactly when `mode` is parallel.
    why: Mapped[list[str]] = mapped_column(
        ARRAY(String(WHY_CHARS)), nullable=False, server_default=text("'{}'")
    )
    #: One object per child: subtask_id, callee_id, depth, reach_hash, status, minor, seconds.
    children: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
