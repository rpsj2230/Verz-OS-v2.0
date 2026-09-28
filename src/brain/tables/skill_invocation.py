"""`agent.skill_invocation`: one row for each skill a run used, by digest, when, and as which agent.

The skills screen and a skill's detail page were asked to say how many runs invoked a skill and
when it was last used, and nothing recorded either: `agent.skill_assignment` says which agents
hold a skill, which is a list of intentions, and counting it as use is the answer M27.15.9 says
must never be given. The run is where a skill is used, so the row is written when a run's request
finishes (`brain.ops.usage_store`), for each skill whose card that run offered to a model.

**The digest, never the body and never the name alone.** A name is a label an author can reuse
for different words; the digest is the exact procedure the run was shown, which is what
`brain.tools.skills.SkillPin` pins. The body is not here, and neither is anything the run said or
read: the row is who, which agent, which skill version and when.

**The person is on the row, so a count is taken at the reader's own basis.** A reader of an
agent's usage over their own runs only is told their own runs' figures (`brain.console.agent_tabs.
usage_basis`), and a skill count over everybody's runs would be the back door to the count that
basis withholds. `principal_id` is what the narrower read puts in its WHERE clause.

**One row per skill per finished request, by the database.** The unique key is the trace, the
instant the request finished and the digest. The trace alone was rejected: a caller may propose
its own trace id (`brain.app`'s trace middleware), so two requests can share one, and a key on the
trace alone would let the second request's use disappear. The instant is read once per request by
the lane, so the same request recorded twice collides and two requests do not.

**Insert-only.** The application holds SELECT and INSERT and no more: a use that happened is not
edited, and an erasure keeps these rows and reports them kept, as it does a cost.

Task ids: M27.15.9, M39.2.2.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS
from brain.tables.skill import AGENT_ID_CHARS, DIGEST_CHARS, NAME_CHARS

#: A trace id, at the width `brain.audit.ledger.TRACE_ID` admits.
TRACE_ID_CHARS: Final = 64

#: A digest as `brain.tools.skills.DIGEST_RE` writes one: sixty-four lower-case hex characters.
DIGEST_PATTERN: Final = "^[0-9a-f]{64}$"


class SkillInvocationRow(Base):
    """One skill one run used: the request, the person, the agent, the skill's digest, and when."""

    __tablename__ = "skill_invocation"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: When the run that used it finished, as the lane read it once.
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        CheckConstraint("length(btrim(agent_id)) >= 1", name="agent_present"),
        CheckConstraint("length(btrim(skill_name)) >= 1", name="skill_name_present"),
        UniqueConstraint("trace_id", "used_at", "digest"),
        Index("ix_skill_invocation_skill_used_at", "skill_name", "used_at"),
        Index("ix_skill_invocation_agent_used_at", "agent_id", "used_at"),
        {"schema": "agent"},
    )
