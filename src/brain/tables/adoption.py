"""Who asked a question, as rows: one per trace, and nothing about what came back.

`brain.adoption.Asked` has been the record adoption is counted from since M37.3.2.4 was built,
and nothing held one. This is the table, and it mirrors `Asked` field for field.

**The trace id is the primary key, and that is the whole of how a hop is kept out.**
`brain.orchestration.delegation.fan_out_request` admits every child of a run under the root
run's trace id, so a question that fanned out finishes under one trace however many agents
worked on it. A key on the trace makes "one question, one row" a property of the database
rather than of every writer remembering it, and `brain.ops.question_store.record` writes with
`ON CONFLICT DO NOTHING`, so the first record of a trace is the one kept. See
`brain.ops.question_store.THE_FIRST_RECORD_OF_A_TRACE_IS_THE_QUESTION`.

**Nothing about the outcome, and the absence is load-bearing.** No status, no abstention
reason, no lane, no cache flag, no entity and no text. A column saying the question was
refused would be a count of refused questions per department, which is the hidden item count
`CLAUDE.md` forbids with a label on it, and a column naming what was asked about would be a
search history. A refused record and an absent one therefore produce rows that differ only in
their trace id and instant.

**Machine is not a column**, for the reason `brain.tables.spend` gives about the same field:
`Asked.machine` is derived from the principal's kind and the channel through
`brain.ops.limits.is_automated`, so the two inputs are stored and the answer is not.

**A channel rather than a traffic class.** The channel is where the request came from and the
class is `brain.gate.context.traffic_class_for`'s declaration about it; storing the class would
store a figure frozen at write time that the declaration could later disagree with.

Task ids: M37.3.2.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.principal import PrincipalKind
from brain.db import Base
from brain.gate.context import Channel
from brain.tables.identity import one_of
from brain.tables.spend import NAME_CHARS, PRINCIPAL_ID_CHARS

#: The longest trace id `brain.audit.ledger.TRACE_ID` admits.
TRACE_ID_CHARS: Final = 64


class QuestionAskedRow(Base):
    """`ops.question_asked`. One question somebody asked, and who and where from (M37.3.2.4).

    Appended when the answer lane finishes with a request. There is no update: who asked a
    question does not change afterwards, and a department that changes is a later question
    asked from a different department.
    """

    __tablename__ = "question_asked"

    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    principal_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    department: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: When the request was judged. The adoption window is taken from this.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("principal_kind", PrincipalKind), name="principal_kind"),
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        CheckConstraint("length(btrim(department)) >= 1", name="department_present"),
        Index("ix_question_asked_at", "at"),
        {"schema": "ops"},
    )
