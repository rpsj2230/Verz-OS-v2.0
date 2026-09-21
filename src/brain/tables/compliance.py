"""`ops.breach_case` and `ops.sensitive_referral`: two compliance records that are not the ledger.

**A breach case holds the clock and never the incident.** `brain.audit.compliance.BreachCase` is
the model this row stores, and every column is a timestamp, an enumerated value, a count or a
reference to where a person wrote the reasoning. There is no description column, and that is the
design rather than an omission: the case is read by the people running the clock, and a free-text
box on it is where the details of the breach, the names in it and the counterparty end up. The
evidence and the rationale are references (`IDENTIFIER`), exactly as the model's are.

**One column per step, each set once, and the ledger entry is the database's.** `0104`'s trigger
appends one `breach` entry for every column that goes from empty to set, by the row's `updated_by`,
which the update policy pins to the session. A re-assessment is recorded again, because an
undetermined assessment becoming a determined one is the event the Commission's clock runs from.

**A sensitive referral holds who asked, when, the topic and the named person, and never the
question.** It is the record M24.2.2 asks for ("recorded without its content"). Its readers are
decided in the database: the person it was routed to, or, when nobody was named for its topic at
the time, whoever is named now. A count reaches anybody else only through
`ops.sensitive_referral_tally`, which returns counts and no row, and `brain.audit.compliance`
suppresses those below a cohort.

Task ids: M24.2.2, M24.2.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.compliance import AwarenessBasis, AwarenessSource, ExceptionGround, SensitiveTopic
from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide an enumerated word may be. `technological_protection` is twenty-four.
WORD_CHARS: Final = 32
#: `observed` and `estimated`.
BASIS_CHARS: Final = 16


class BreachCaseRow(Base):
    """`ops.breach_case`. One suspected breach, from the moment there was reason to believe it."""

    __tablename__ = "breach_case"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    became_aware_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    awareness_basis: Mapped[str] = mapped_column(String(BASIS_CHARS), nullable=False)
    awareness_source: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    earliest_possible_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: Inert, as the model's is: recorded for the review and read by no deadline.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    significant_harm: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    harm_decided_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    harm_rationale_reference: Mapped[str | None] = mapped_column(
        String(PRINCIPAL_ID_CHARS), nullable=True
    )
    #: None means not yet established, never zero.
    affected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    individuals_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exception_ground: Mapped[str | None] = mapped_column(String(WORD_CHARS), nullable=True)
    exception_decided_by: Mapped[str | None] = mapped_column(
        String(PRINCIPAL_ID_CHARS), nullable=True
    )
    exception_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exception_rationale_reference: Mapped[str | None] = mapped_column(
        String(PRINCIPAL_ID_CHARS), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    #: Whoever made the latest change: the actor of the entry the trigger appends for it.
    updated_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("awareness_basis", AwarenessBasis), name="awareness_basis"),
        CheckConstraint(one_of("awareness_source", AwarenessSource), name="awareness_source"),
        CheckConstraint(
            f"exception_ground IS NULL OR {one_of('exception_ground', ExceptionGround)}",
            name="exception_ground",
        ),
        CheckConstraint(f"recorded_by ~ '{IDENTIFIER}'", name="recorded_by_is_an_identifier"),
        CheckConstraint(f"updated_by ~ '{IDENTIFIER}'", name="updated_by_is_an_identifier"),
        CheckConstraint(f"evidence_reference ~ '{IDENTIFIER}'", name="evidence_is_a_reference"),
        CheckConstraint(
            f"harm_decided_by IS NULL OR harm_decided_by ~ '{IDENTIFIER}'",
            name="harm_decided_by_is_an_identifier",
        ),
        CheckConstraint(
            f"harm_rationale_reference IS NULL OR harm_rationale_reference ~ '{IDENTIFIER}'",
            name="harm_rationale_is_a_reference",
        ),
        CheckConstraint(
            f"exception_decided_by IS NULL OR exception_decided_by ~ '{IDENTIFIER}'",
            name="exception_decided_by_is_an_identifier",
        ),
        CheckConstraint(
            "exception_rationale_reference IS NULL OR exception_rationale_reference ~ "
            f"'{IDENTIFIER}'",
            name="exception_rationale_is_a_reference",
        ),
        CheckConstraint(
            f"closed_by IS NULL OR closed_by ~ '{IDENTIFIER}'", name="closed_by_is_an_identifier"
        ),
        # An estimate carries its lower bound and an observation carries none: two candidate
        # start times, one unused, is how a later change picks the wrong one.
        CheckConstraint(
            "(awareness_basis = 'estimated') = (earliest_possible_at IS NOT NULL)",
            name="an_estimate_records_its_earliest",
        ),
        CheckConstraint(
            "earliest_possible_at IS NULL OR earliest_possible_at <= became_aware_at",
            name="earliest_is_not_after_the_estimate",
        ),
        CheckConstraint("recorded_at >= became_aware_at", name="recorded_after_it_was_known"),
        CheckConstraint(
            "(assessed_at IS NULL) = (significant_harm IS NULL) "
            "AND (assessed_at IS NULL) = (harm_decided_by IS NULL) "
            "AND (assessed_at IS NULL) = (harm_rationale_reference IS NULL)",
            name="assessed_whole",
        ),
        CheckConstraint(
            "affected_count IS NULL OR affected_count >= 0", name="affected_count_not_negative"
        ),
        CheckConstraint(
            "(exception_ground IS NULL) = (exception_decided_by IS NULL) "
            "AND (exception_ground IS NULL) = (exception_decided_at IS NULL) "
            "AND (exception_ground IS NULL) = (exception_rationale_reference IS NULL)",
            name="excused_whole",
        ),
        CheckConstraint("(closed_at IS NULL) = (closed_by IS NULL)", name="closed_whole"),
        # The module refuses to close an assessment nobody made; so does the table.
        CheckConstraint(
            "closed_at IS NULL OR assessed_at IS NOT NULL", name="closed_only_once_assessed"
        ),
        Index("ix_breach_case_became_aware_at", "became_aware_at"),
        {"schema": "ops"},
    )


class SensitiveReferralRow(Base):
    """`ops.sensitive_referral`. One intercepted question, routed, with nothing of what was said."""

    __tablename__ = "sensitive_referral"

    #: Minted by the application, because the asker's insert cannot read its own row back.
    referral_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    topic: Mapped[str] = mapped_column(String(WORD_CHARS), nullable=False)
    asked_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: The person named for the topic when it arrived, or None when nobody was.
    routed_to: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(one_of("topic", SensitiveTopic), name="topic"),
        CheckConstraint(f"asked_by ~ '{IDENTIFIER}'", name="asked_by_is_an_identifier"),
        CheckConstraint(
            f"routed_to IS NULL OR routed_to ~ '{IDENTIFIER}'", name="routed_to_is_an_identifier"
        ),
        CheckConstraint(
            f"handled_by IS NULL OR handled_by ~ '{IDENTIFIER}'",
            name="handled_by_is_an_identifier",
        ),
        CheckConstraint("(handled_at IS NULL) = (handled_by IS NULL)", name="handled_whole"),
        Index("ix_sensitive_referral_routed_to", "routed_to"),
        {"schema": "ops"},
    )
