"""A sealed browser envelope gets a row, and the row carries its approval's who and when.

`brain.browsing.envelope.Envelope` is the contract a browser run is compiled from and
`brain.browsing.approval` raises it for a person through the leash. Neither kept anything, so an
envelope sealed in one process and a container started in another had nothing between them but
a promise. This is the row between them (M19.2.3).

**What is stored is what the digest covers, and nothing a person wrote.** The steps, origins,
budget, rungs and unattended writes, in `sealed`, beside the digest over them. Not the goal:
the goal is somebody's own words and the run's record elsewhere, and a row the approval queue
reads is the wrong place for them. So a stored envelope cannot be rebuilt into an `Envelope`,
and does not need to be: `brain.browsing.envelope_store` re-derives the digest from `sealed`
through `brain.browsing.envelope.seal`, and a row edited after it was sealed no longer matches
its own digest and is refused on read.

**The approval record is the state, the window, who and when, and not why.** The verdict and
its reason code go to the ledger through `brain.console.approvals.decide`, which writes the
entry before the state moves. A reason column here would be the second copy
`brain.console.approvals` rejects for `SuspendedAction`, with this table's retention instead of
the ledger's. `approval_state` is null for an envelope with nothing to approve, and the checks
below hold the three halves of a decision together, so a row cannot say approved without saying
by whom and when, nor carry a decision while still pending.

**No `deleted_at`, and no foreign key.** A sealed envelope is the record of what a run was
permitted, and a finished run is still a run somebody may ask about. The asker and the agent
are values, for the reason `0014` gives: a key into `auth.principal` would make deleting a
person delete what was permitted in their name.

**A session is a row of its own, keyed by the run and pointing at its envelope** (M24.3.4). The
envelope is what a run was permitted; `agent.browser_session` is a browser actually opened on it,
under which trace, when it ended and the digest of the recording it kept. The key into the
envelope is the one foreign key here and it is the point: a session can start only on a sealed
envelope, so the agent and the person it ran for are read off that envelope rather than written a
second time, and `0150`'s trigger names them in the ledger entry each end of a session leaves.
`RESTRICT`, so the permission a session ran under cannot be deleted from under its record.

**A declared system and a signed permission are rows of their own** (M19.2.4, M19.9.7). `agent.
browser_target` is what a person declared about a system, one row per change with the newest row
for a name its state, so a map edited after a run is a map with a history and a retirement is a row
and not a deletion. `agent.browser_grant` is a signed exception for a surface's writes to run with
nobody looking, or an exemption for a skill to drive a website that has an API, each with a signer,
a reason and an end; the only thing updated on it is that it was revoked. Both are described at
length in `0275` and `brain.browsing.declared`.

Task ids: M19.2.3, M19.2.4, M19.7.3, M19.9.7, M24.3.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import TRACE_ID
from brain.browsing.targets import NAME_RE
from brain.db import Base, TimestampMixin
from brain.gate.leash import DIGEST, IDENTIFIER, ApprovalState
from brain.tables.identity import one_of

#: Widths, named once so the model, the migration and the store agree.
RUN_ID_CHARS = 128
TARGET_CHARS = 64
PRINCIPAL_CHARS = 128
DIGEST_CHARS = 64
STATE_CHARS = 16
TRACE_ID_CHARS = 64


class BrowserEnvelopeRow(TimestampMixin, Base):
    """`agent.browser_envelope`. One sealed envelope per run, and its approval if it needs one."""

    __tablename__ = "browser_envelope"

    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), primary_key=True)
    target: Mapped[str] = mapped_column(String(TARGET_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    #: Whose reach the run was compiled against. The goal's asker, as a value.
    asked_by: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    envelope_digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: The permitted parts the digest covers. See the module docstring.
    sealed: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approval_state: Mapped[str | None] = mapped_column(String(STATE_CHARS), nullable=True)
    raised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"run_id ~ '{IDENTIFIER}'", name="run_id_is_an_identifier"),
        CheckConstraint(f"target ~ '{NAME_RE.pattern}'", name="target_is_a_slug"),
        CheckConstraint("length(btrim(agent_id)) > 0", name="an_agent_runs_it"),
        CheckConstraint("length(btrim(asked_by)) > 0", name="somebody_asked"),
        CheckConstraint(f"envelope_digest ~ '{DIGEST}'", name="envelope_digest_shape"),
        CheckConstraint(one_of("approval_state", ApprovalState), name="approval_state"),
        CheckConstraint(
            "(approval_state IS NULL) = (raised_at IS NULL) "
            "AND (raised_at IS NULL) = (expires_at IS NULL)",
            name="an_approval_is_raised_with_a_window",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > raised_at", name="a_window_ends_after_it_opens"
        ),
        CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        CheckConstraint(
            "(decided_by IS NULL) = (approval_state IS NULL OR approval_state = 'pending')",
            name="only_a_decided_approval_names_its_decider",
        ),
        {"schema": "agent"},
    )


class BrowserSessionRow(Base):
    """`agent.browser_session`. One browser opened on a sealed envelope's run, and how it ended.

    Inserted when the session starts and updated once, when it ends. See the module docstring.
    """

    __tablename__ = "browser_session"

    run_id: Mapped[str] = mapped_column(
        String(RUN_ID_CHARS),
        ForeignKey("agent.browser_envelope.run_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    #: The run's trace, which its trace graph is keyed by and its ledger entries carry.
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The sha256 of the transcript `brain.browsing.recording.write` stored, when it kept one.
    recording_digest: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name="a_session_ends_after_it_starts"
        ),
        CheckConstraint(
            f"recording_digest IS NULL OR recording_digest ~ '{DIGEST}'",
            name="recording_digest_shape",
        ),
        CheckConstraint(
            "recording_digest IS NULL OR ended_at IS NOT NULL",
            name="a_recording_is_named_when_the_session_ends",
        ),
        {"schema": "agent"},
    )


#: The longest reason a grant may give: a sentence and not a document.
REASON_CHARS = 240
#: The shortest, which is `brain.ops.halt.MINIMUM_REASON`, restated for the check constraint.
MINIMUM_REASON_CHARS = 12
SKILL_CHARS = 80


class BrowserTargetRow(Base):
    """`agent.browser_target`. One change to what a person declared about a system.

    `definition` is the declaration as `brain.browsing.declared` reads it: origins, surfaces with
    their declared controls, the API tools that do the same work without a browser, and the
    credential bindings by vault reference and never by value. The newest row for a name is its
    state; `retired` says the system is no longer declared.
    """

    __tablename__ = "browser_target"

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(TARGET_CHARS), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    set_by: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"name ~ '{NAME_RE.pattern}'", name="name_is_a_slug"),
        CheckConstraint("jsonb_typeof(definition) = 'object'", name="definition_is_an_object"),
        CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        Index("ix_agent_browser_target_name", "name", "seq"),
        {"schema": "agent"},
    )


class BrowserGrantRow(Base):
    """`agent.browser_grant`. A signed exception for one surface, or an exemption for one skill.

    `kind` is `exception` (a surface's writes may run without the envelope waiting for a person,
    `brain.browsing.autonomy`) or `exemption` (a skill may drive a target that has an API,
    `brain.browsing.skill_gate`). Each names a person who signed it, why, and when it ends, and no
    grant runs longer than a quarter. Nothing is edited: a grant ends by its date or by being
    revoked, which is the one update the application may make.
    """

    __tablename__ = "browser_grant"

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(TARGET_CHARS), nullable=False)
    surface: Mapped[str | None] = mapped_column(String(TARGET_CHARS), nullable=True)
    skill: Mapped[str | None] = mapped_column(String(SKILL_CHARS), nullable=True)
    signed_by: Mapped[str] = mapped_column(String(PRINCIPAL_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint("kind IN ('exception', 'exemption')", name="kind"),
        CheckConstraint(f"target ~ '{NAME_RE.pattern}'", name="target_is_a_slug"),
        CheckConstraint(
            "(kind = 'exception') = (surface IS NOT NULL) "
            "AND (kind = 'exemption') = (skill IS NOT NULL)",
            name="an_exception_names_a_surface_and_an_exemption_a_skill",
        ),
        CheckConstraint(f"signed_by ~ '{IDENTIFIER}'", name="signed_by_is_an_identifier"),
        CheckConstraint(
            f"length(btrim(reason)) >= {MINIMUM_REASON_CHARS}", name="a_reason_is_a_sentence"
        ),
        CheckConstraint("expires_at > created_at", name="a_grant_ends_after_it_begins"),
        CheckConstraint(
            "expires_at <= created_at + interval '90 days'", name="a_grant_runs_at_most_a_quarter"
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name="a_revocation_is_a_person_and_a_date",
        ),
        Index("ix_agent_browser_grant_target", "target", "seq"),
        {"schema": "agent"},
    )
