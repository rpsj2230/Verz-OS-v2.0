"""An agent's leash as it moves on the install, and the supervision that holds it down.

The leash an agent was installed with is `guardrails.leash` in its install's effective document,
sealed, and only an upgrade moves it. `brain.console.reach_view` decided how a rung may move after
that: lowered at once, raised only on evidence and a named approver and on two for a money or
irreversible boundary, tripped to the bottom by a breaker naming its metric, and every move kept
with its evidence. `brain.agents.supervision` decided the thirty-day review. Nothing stored any of
it, so every rung was the install's for ever. `0195` builds these four tables and
`brain.ops.leash_store` is their one writer.

**`agent.leash_change`: one row per move, never edited.** The rung a key stands at now is its
newest lowered, raised or tripped row; a proposed row moves nothing and waits for a second person.
Each kind carries exactly its own evidence, and the constraints below are that sentence: a raise
names its approver and its clean runs and agreement, a trip names its metric, a lowering names
neither, and a second approver is never the first. Rejected: an UPDATE of the install's leash,
which would put every rung move through the upgrade path and lose the evidence in the document.

**`agent.supervised_action` and `agent.action_verdict`: what an agent did under supervision, and
what a person said of it.** `brain.gate.leash.ActionRecord` field for field, which holds no value
from the action, and a verdict per action from the ledger's own vocabulary. They are what a
promotion's evidence, a breaker's measurement and a review's confidence are counted from, so none
of those three is a figure somebody typed.

**`agent.supervision_pin`: the thirty-day review, as rows.** A pin is written with its first due
date and an extension is a new row carrying the same start and a later due date, which is
`brain.agents.supervision.extended` stored. There is no column meaning supervision ended; the
agent's rung rises only through a raise in `agent.leash_change`.

Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.record import ApprovalVerdict
from brain.db import Base
from brain.gate.leash import DIGEST, TARGET, Route
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide an agent's identifier may be, matching `brain.tables.artifact.AGENT_ID_CHARS`.
AGENT_ID_CHARS: Final = 128
#: How wide a target may be: `brain.gate.leash.LeashEntry.target`'s own bound.
TARGET_CHARS: Final = 120
#: How wide a tool's name may be: `brain.gate.leash.ActionRecord.tool_name`'s bound.
TOOL_CHARS: Final = 80
#: How wide a kind, a route, an outcome and a verdict may be.
WORD_CHARS: Final = 16
#: How wide a trace id and a reason code may be.
TRACE_ID_CHARS: Final = 128
REASON_CHARS: Final = 64
#: How wide a breaker's metric may be, in words.
METRIC_CHARS: Final = 120
#: The highest rung, `brain.gate.injection.AutonomyTier.AUTONOMOUS`.
TOP_RUNG: Final = 2
#: An entitlement hash, as `EntitlementSet.ent_hash` returns it.
ENT_HASH_PATTERN: Final = r"^[0-9a-f]{32}$"
#: A reason code, as `brain.audit.record` admits one.
REASON_PATTERN: Final = r"^[a-z][a-z0-9_]{0,63}$"


class MoveKind(enum.StrEnum):
    """How one row moved a rung, or proposed to."""

    #: A person lowered it, at once, with no evidence asked for.
    LOWERED = "lowered"
    #: A person proposed a rise across a money or irreversible boundary; nothing moved yet.
    PROPOSED = "proposed"
    #: A person raised it on evidence, with a second person where the boundary asks for one.
    RAISED = "raised"
    #: A breaker put it on the bottom rung, naming the metric that tripped.
    TRIPPED = "tripped"


class PinOutcome(enum.StrEnum):
    """What one supervision row records. There is deliberately no member meaning it ended."""

    PINNED = "pinned"
    EXTENDED = "extended"
    ELIGIBLE = "eligible"


#: Each kind and the evidence it must carry, as the database checks it.
A_RAISE_NAMES_ITS_APPROVER_AND_ITS_EVIDENCE: Final = (
    "kind NOT IN ('raised', 'proposed') OR (approver_id IS NOT NULL "
    "AND clean_runs IS NOT NULL AND agreement_rate IS NOT NULL AND became > was)"
)
A_FALL_CARRIES_NO_PROMOTION_EVIDENCE: Final = (
    "kind NOT IN ('lowered', 'tripped') OR (became < was AND approver_id IS NULL "
    "AND second_approver_id IS NULL AND clean_runs IS NULL AND agreement_rate IS NULL)"
)
A_TRIP_NAMES_ITS_METRIC: Final = (
    "(kind = 'tripped') = (metric IS NOT NULL AND measured IS NOT NULL AND threshold IS NOT NULL)"
)
A_REVIEW_CARRIES_ITS_COUNTS: Final = (
    "(outcome = 'pinned') = (understood IS NULL AND reviewed IS NULL AND simulated IS NULL)"
)
TWO_APPROVERS_ARE_TWO_PEOPLE: Final = (
    "second_approver_id IS NULL OR (kind = 'raised' AND second_approver_id <> approver_id)"
)


class LeashChangeRow(Base):
    """`agent.leash_change`. One move of one rung of one agent, with its evidence."""

    __tablename__ = "leash_change"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    target: Mapped[str] = mapped_column(String(TARGET_CHARS), nullable=False)
    #: `brain.core.scope.Scope.model_dump(mode="json")`: where the entry applies.
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    was: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    became: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    #: Whether the target's effect is money or irreversible, as the writer read the tool.
    irreversible: Mapped[bool] = mapped_column(nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    second_approver_id: Mapped[str | None] = mapped_column(
        String(PRINCIPAL_ID_CHARS), nullable=True
    )
    clean_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agreement_rate: Mapped[float | None] = mapped_column(Double, nullable=True)
    metric: Mapped[str | None] = mapped_column(String(METRIC_CHARS), nullable=True)
    measured: Mapped[float | None] = mapped_column(Double, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Double, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    entitlement_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(one_of("kind", MoveKind), name="kind"),
        CheckConstraint(f"target ~ '{TARGET.replace('(?:', '(')}'", name="target_shape"),
        CheckConstraint(f"was BETWEEN 0 AND {TOP_RUNG}", name="was_is_a_rung"),
        CheckConstraint(f"became BETWEEN 0 AND {TOP_RUNG}", name="became_is_a_rung"),
        CheckConstraint("jsonb_typeof(scope) = 'object'", name="scope_is_a_scope"),
        CheckConstraint(A_RAISE_NAMES_ITS_APPROVER_AND_ITS_EVIDENCE, name="a_raise_has_evidence"),
        CheckConstraint(A_FALL_CARRIES_NO_PROMOTION_EVIDENCE, name="a_fall_has_none"),
        CheckConstraint(A_TRIP_NAMES_ITS_METRIC, name="a_trip_names_its_metric"),
        CheckConstraint(TWO_APPROVERS_ARE_TWO_PEOPLE, name="two_approvers_are_two_people"),
        CheckConstraint(
            "kind <> 'raised' OR NOT irreversible OR second_approver_id IS NOT NULL",
            name="an_irreversible_rise_has_two_approvers",
        ),
        CheckConstraint(
            "agreement_rate IS NULL OR (agreement_rate >= 0 AND agreement_rate <= 1)",
            name="agreement_is_a_share",
        ),
        CheckConstraint("clean_runs IS NULL OR clean_runs >= 0", name="clean_runs_counted"),
        CheckConstraint(f"reason_code ~ '{REASON_PATTERN}'", name="reason_is_a_code"),
        CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        Index("ix_leash_change_agent_changed", "agent_id", "changed_at"),
        {"schema": "agent"},
    )


class SupervisedActionRow(Base):
    """`agent.supervised_action`. `brain.gate.leash.ActionRecord`, stored, once per route."""

    __tablename__ = "supervised_action"

    action_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    route: Mapped[str] = mapped_column(String(WORD_CHARS), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(TOOL_CHARS), nullable=False)
    target: Mapped[str] = mapped_column(String(TARGET_CHARS), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    ent_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    checks: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"action_digest ~ '{DIGEST}'", name="digest_shape"),
        CheckConstraint(
            one_of("route", [one for one in Route if one is not Route.REFUSED]),
            name="route_ran",
        ),
        CheckConstraint(f"tier BETWEEN 0 AND {TOP_RUNG}", name="tier_is_a_rung"),
        CheckConstraint(f"ent_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        CheckConstraint(
            "length(btrim(agent_id)) > 0 AND length(btrim(principal_id)) > 0",
            name="attributed",
        ),
        Index("ix_supervised_action_agent_at", "agent_id", "at"),
        {"schema": "agent"},
    )


class ActionVerdictRow(Base):
    """`agent.action_verdict`. What one person said of one action an agent took or simulated."""

    __tablename__ = "action_verdict"

    action_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    verdict: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"action_digest ~ '{DIGEST}'", name="digest_shape"),
        CheckConstraint(one_of("verdict", ApprovalVerdict), name="verdict"),
        CheckConstraint("length(btrim(reviewer_id)) > 0", name="attributed"),
        Index("ix_action_verdict_agent_at", "agent_id", "at"),
        {"schema": "agent"},
    )


class SupervisionPinRow(Base):
    """`agent.supervision_pin`. One agent's pin, as written and as each review left it."""

    __tablename__ = "supervision_pin"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    outcome: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    pinned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The counts `brain.agents.supervision.measure` found, for a review; null for a new pin.
    understood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    simulated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    entitlement_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("outcome", PinOutcome), name="outcome"),
        CheckConstraint("review_due_at > pinned_at", name="due_after_it_began"),
        CheckConstraint(
            A_REVIEW_CARRIES_ITS_COUNTS,
            name="a_review_carries_its_counts",
        ),
        CheckConstraint(
            "understood IS NULL OR (understood >= 0 AND understood <= reviewed "
            "AND reviewed <= simulated)",
            name="counts_are_a_measurement",
        ),
        CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        CheckConstraint("length(btrim(decided_by)) > 0", name="attributed"),
        Index("ix_supervision_pin_agent_decided", "agent_id", "decided_at"),
        {"schema": "agent"},
    )
