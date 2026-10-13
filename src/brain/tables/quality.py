"""Eight tables: what a lead flagged, the regression case it became, what the machines and the
people read of answers, how the golden questions scored by release, what a failed case proposed,
the outputs people approved unchanged, and who agreed to a change that needed more than one person.

The rows behind `brain.ops.feedback` (`Flag`, `CapturedCase`), `brain.ops.sampling`
(`AutomatedReading`, `HumanAnnotation`), `brain.ops.evaluation` (`CaseResult`) and the learning
tiers of `brain.memory.tiers`. `0219` builds them; `brain.ops.quality_store` is their one writer.

**Every one of them is a pointer and a word, and none holds what an answer said.** A flag names a
trace reference and a question id, a reading names a request id and a fault from the machine's
closed vocabulary, an annotation a fault from the human one, a golden score a question id, a
severity and a pass, a candidate a case reference and an agent. Not one has a free-text column, for
`brain.ops.feedback.A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED`: the store would be the
second copy of an answer under permissions belonging to nobody. The regression case is the one
document-shaped row and `CapturedCase` has no field a value could arrive in; its column is checked
to hold exactly the keys the dataclass has.

**Insert-only, and each insert is in the writer's own name.** A flag, a reading, an annotation, a
score, a candidate, an example and a decision are each a fact about a moment, so none is updated
and none is deleted, and what is true now (a candidate's state, an example's promotion) is read off
the newest `ops.tier_decision` row about it. Each table's insert policy admits only a row whose
writer column is the session's `app.principal_id`, so nobody records a judgement in another
person's name.

**The two-tier rule is held in the tables as in the code.** A reading says `passed` exactly when it
names no fault, an annotation says `sound` exactly when it names none, and the two fault columns
take different vocabularies with no word in common, so a row cannot be averaged across tiers by
sharing a column: `brain.ops.sampling.AUTOMATED_COVERAGE_IS_COMPLETE_AND_SHALLOW_ANNOTATION_IS_DEEP_
AND_PARTIAL`.

**A candidate never changes an agent.** Nothing here has a column naming a change to apply, and no
foreign key leads into an agent table: opening a candidate writes one row about an agent and
nothing to it.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M28.5.3, M16.6.7, M16.7.14
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Final

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS, DEPARTMENT_CHARS
from brain.db import Base
from brain.ops.canaries import Finding
from brain.ops.evaluation import Severity
from brain.ops.feedback import REFERENCE_MAX_LENGTH, FlagReason
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide a reference (a trace, a question, a request, a case) may be.
REFERENCE_CHARS: Final = REFERENCE_MAX_LENGTH
#: The widest fault, severity, source, state and kind word, with room.
WORD_CHARS: Final = 32
#: How wide a release is named: a tag or a commit, as `brain.release` writes one.
RELEASE_CHARS: Final = 64
#: How wide a stated reason code may be.
REASON_CHARS: Final = 64

#: One token and nothing else, so a sentence cannot be filed as a reference.
UNBROKEN: Final = r"^\S+$"


class CandidateSource(enum.StrEnum):
    """Where a failed case came from."""

    GOLDEN = "golden"
    CANARY = "canary"
    SAMPLED = "sampled"


class ItemKind(enum.StrEnum):
    """What a tier decision is about."""

    CANDIDATE = "candidate"
    EXAMPLE = "example"
    RULE = "rule"


class TierDecisionWord(enum.StrEnum):
    """What was decided. Promoting is tier two's word and the other two are tier three's."""

    PROMOTED = "promoted"
    APPROVED = "approved"
    DECLINED = "declined"


def _token(column: str) -> str:
    return f"{column} ~ '{UNBROKEN}'"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


class AnswerFlagRow(Base):
    """`ops.answer_flag`. One lead saying one answer was wrong, by reference and a closed reason."""

    __tablename__ = "answer_flag"
    __table_args__ = (
        CheckConstraint(_token("trace_ref"), name="trace_ref_is_one_token"),
        CheckConstraint(_token("question_id"), name="question_id_is_one_token"),
        CheckConstraint(_present("department"), name="department_present"),
        CheckConstraint(_present("flagged_by"), name="flagged_by_present"),
        CheckConstraint(one_of("reason", FlagReason), name="reason"),
        UniqueConstraint("trace_ref", "flagged_by", name="uq_answer_flag_one_per_lead_and_answer"),
        Index("ix_ops_answer_flag_flagged_at", "flagged_at"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    trace_ref: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    question_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    department: Mapped[str] = mapped_column(String(DEPARTMENT_CHARS), nullable=False)
    flagged_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    flagged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


#: The keys a captured case document holds, from `brain.ops.feedback.CapturedCase`'s fields.
CASE_KEYS: Final = (
    "answering_fields",
    "fault",
    "held",
    "locked_fields",
    "mocked_from",
    "origin_question_id",
    "origin_trace_ref",
    "question",
)


def case_has_exactly_the_keys() -> str:
    """The document's keys are `CASE_KEYS` and no others, in the one expression a CHECK can hold.

    `jsonb_typeof` object, then every key present, then nothing left after the keys are
    subtracted, which is `0045`'s allow-list shape and for its reason: a CHECK cannot hold a
    subquery, and a column that admits any key admits the one called `answer`.
    """
    keys = ", ".join(f"'{one}'" for one in CASE_KEYS)
    return (
        "jsonb_typeof(document) = 'object' AND jsonb_exists_all(document, "
        f"ARRAY[{keys}]) AND document - ARRAY[{keys}] = '{{}}'::jsonb"
    )


class RegressionCaseRow(Base):
    """`ops.regression_case`. A flag turned into a permanent case, carrying no value."""

    __tablename__ = "regression_case"
    __table_args__ = (
        CheckConstraint(case_has_exactly_the_keys(), name="a_case_has_exactly_the_captured_keys"),
        CheckConstraint(_present("captured_by"), name="captured_by_present"),
        UniqueConstraint("flag_id", name="uq_regression_case_one_per_flag"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    flag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ops.answer_flag.id", ondelete="RESTRICT"), nullable=False
    )
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    captured_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class QualityReadingRow(Base):
    """`ops.quality_reading`. What the mechanical checks saw on one request."""

    __tablename__ = "quality_reading"
    __table_args__ = (
        CheckConstraint(_token("request_id"), name="request_id_is_one_token"),
        CheckConstraint(
            "fault IS NULL OR " + one_of("fault", Finding), name="fault_is_a_mechanical_finding"
        ),
        CheckConstraint("passed = (fault IS NULL)", name="passed_exactly_when_no_fault"),
        CheckConstraint(_present("recorded_by"), name="recorded_by_present"),
        UniqueConstraint("request_id", name="uq_quality_reading_one_per_request"),
        Index("ix_ops_quality_reading_read_at", "read_at"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fault: Mapped[str | None] = mapped_column(String(WORD_CHARS), nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class QualityAnnotationRow(Base):
    """`ops.quality_annotation`. One person's judgement of one answer from a day's sample."""

    __tablename__ = "quality_annotation"
    __table_args__ = (
        CheckConstraint(_token("request_id"), name="request_id_is_one_token"),
        CheckConstraint(
            "fault IS NULL OR " + one_of("fault", FlagReason), name="fault_is_a_human_reason"
        ),
        CheckConstraint("sound = (fault IS NULL)", name="sound_exactly_when_no_fault"),
        CheckConstraint(_present("annotator"), name="annotator_present"),
        UniqueConstraint("request_id", name="uq_quality_annotation_one_per_request"),
        Index("ix_ops_quality_annotation_day", "day"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    request_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    annotator: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    sound: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fault: Mapped[str | None] = mapped_column(String(WORD_CHARS), nullable=True)
    annotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class GoldenScoreRow(Base):
    """`ops.golden_score`. One golden question's result on one release, as one persona asked it."""

    __tablename__ = "golden_score"
    __table_args__ = (
        CheckConstraint(_present("release"), name="release_present"),
        CheckConstraint(_token("question_id"), name="question_id_is_one_token"),
        CheckConstraint(_present("persona"), name="persona_present"),
        CheckConstraint(one_of("severity", Severity), name="severity"),
        CheckConstraint("passed = (reason = '')", name="a_failure_says_which_expectation_failed"),
        CheckConstraint("length(reason) <= 64", name="reason_is_a_code"),
        CheckConstraint(_present("ran_by"), name="ran_by_present"),
        UniqueConstraint(
            "release", "question_id", "persona", name="uq_golden_score_one_per_release_question"
        ),
        Index("ix_ops_golden_score_ran_at", "ran_at"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    release: Mapped[str] = mapped_column(String(RELEASE_CHARS), nullable=False)
    question_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    persona: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    severity: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False, server_default="")
    ran_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class EvaluationCandidateRow(Base):
    """`ops.evaluation_candidate`. A failed case opened against an agent for a person to decide."""

    __tablename__ = "evaluation_candidate"
    __table_args__ = (
        CheckConstraint(_present("agent_id"), name="agent_present"),
        CheckConstraint(one_of("source", CandidateSource), name="source"),
        CheckConstraint(_token("case_ref"), name="case_ref_is_one_token"),
        CheckConstraint(_present("opened_by"), name="opened_by_present"),
        UniqueConstraint(
            "agent_id", "source", "case_ref", name="uq_evaluation_candidate_one_per_failed_case"
        ),
        Index("ix_ops_evaluation_candidate_agent", "agent_id"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    source: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    case_ref: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    opened_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class PositiveExampleRow(Base):
    """`ops.positive_example`. An output a person approved without changes, for its agent."""

    __tablename__ = "positive_example"
    __table_args__ = (
        CheckConstraint(_present("agent_id"), name="agent_present"),
        CheckConstraint(_token("artefact_ref"), name="artefact_ref_is_one_token"),
        CheckConstraint("skill IS NULL OR " + _present("skill"), name="skill_present_when_named"),
        CheckConstraint(_present("approved_by"), name="approved_by_present"),
        UniqueConstraint("agent_id", "artefact_ref", name="uq_positive_example_one_per_output"),
        Index("ix_ops_positive_example_agent", "agent_id"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    skill: Mapped[str | None] = mapped_column(String(WORD_CHARS * 2), nullable=True)
    artefact_ref: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class TierDecisionRow(Base):
    """`ops.tier_decision`. Who agreed to a change that needed more than the system's say-so."""

    __tablename__ = "tier_decision"
    __table_args__ = (
        CheckConstraint(one_of("item_kind", ItemKind), name="item_kind"),
        CheckConstraint(_token("item_ref"), name="item_ref_is_one_token"),
        CheckConstraint("tier IN (2, 3)", name="only_tiers_two_and_three_are_decided_by_people"),
        CheckConstraint(one_of("decision", TierDecisionWord), name="decision"),
        CheckConstraint(
            "(tier = 2 AND decision <> 'approved') OR (tier = 3 AND decision <> 'promoted')",
            name="a_decision_word_belongs_to_its_tier",
        ),
        CheckConstraint(_present("decided_by"), name="decided_by_present"),
        CheckConstraint("cardinality(agreed_by) >= 1", name="somebody_agreed"),
        CheckConstraint(
            "decided_by = ANY(agreed_by)", name="the_decider_is_among_those_who_agreed"
        ),
        CheckConstraint(
            "effective_from >= decided_at", name="it_takes_effect_no_earlier_than_decided"
        ),
        Index("ix_ops_tier_decision_item", "item_kind", "item_ref", "decided_at"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    item_kind: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    item_ref: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    agreed_by: Mapped[list[str]] = mapped_column(ARRAY(String(PRINCIPAL_ID_CHARS)), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
