"""A suspended action gets a row, so an approval can be read in one request and decided in the next.

`brain.gate.leash.SuspendedAction` holds an action a person must see: the action, the artefact
as it was shown, the digest binding the two, the reach it would run under and its window. Until
this table nothing kept one, so `brain.approval_routes` could list a card and nothing could
decide it: a decision with nowhere to be written is one that can be taken twice.

**The whole action is stored, as the model serialises it, and the digest beside it.** A resume
needs the action itself and not a description of it, and `SuspendedAction` stores its digest
rather than deriving it so that an action edited in place no longer matches the approval granted
for it. `brain.gate.suspension_store` re-derives the digest from `action` on every read and
refuses a row where the two disagree, which is the argument `brain.browsing.envelope_store` makes
about a sealed envelope.

**`required_capability` is a copy of `action.tool.required_capability`, kept as a column because
row-level security cannot read into the JSON cheaply and must not try.** It is the one fact the
read policy in `0042` narrows on, and the store refuses a row whose column and action disagree,
so the copy cannot quietly become the permission while the action says something else.

**The decision is the state, who and when, and since `0083` the verdict and its reason code.**
This paragraph used to say the verdict and the reason were the ledger's and never the row's, and
that a reason column would be the second copy `brain.console.approvals` refuses to put on
`SuspendedAction`. That was true while the entry was written by the process. It is written by the
row's trigger now, which can read nothing but the row, so the row is where the verdict and the
reason exist before the entry does, and the entry is derived from them in the same transaction:
one copy and its record, not two copies. `SuspendedAction` still carries neither, because nothing
that runs or resumes an action reads why it was decided; `state` is what `brain.gate.leash.resume`
reads, and a check holds the verdict to it. See `THE_ROW_CARRIES_THE_DECISION_ITS_TRIGGER_RECORDS`.

**Three verdicts and not the recorder's four.** See
`AN_AMENDMENT_IS_RECORDED_AGAINST_A_DIGEST_THE_ROW_DOES_NOT_HOLD`.

**No `deleted_at`, and no foreign key.** A decided suspension is the record of what a person was
shown before something ran in somebody's name. The principal and the agent are values, for the
reason `0014` gives: a key into `auth.principal` would make deleting a person delete what was
approved in their name.

Task ids: M35.3.1.1, M33.6.1.3, M27.9.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.record import REASON_CODE, ApprovalVerdict
from brain.db import Base, TimestampMixin
from brain.gate.leash import DIGEST, IDENTIFIER, MAX_APPROVAL_WINDOW, ApprovalState
from brain.tables.identity import one_of

#: Why the row holds the verdict and the reason at all.
THE_ROW_CARRIES_THE_DECISION_ITS_TRIGGER_RECORDS: Final = (
    "The approval entry is written by a trigger on this table, in the transaction that decides the "
    "row, so a decision and its entry cannot come apart. A trigger reads only the row, so the "
    "verdict and the reason code are columns, and the checks refuse what "
    "brain.audit.record.AuditRecorder.approval refuses, because redact_details does not run in the "
    "database."
)

#: Why an amendment cannot be decided on this row yet.
AN_AMENDMENT_IS_RECORDED_AGAINST_A_DIGEST_THE_ROW_DOES_NOT_HOLD: Final = (
    "AuditRecorder.approval records an amendment against the digest of the action substituted for "
    "the original, and this row holds only the original's. An amended entry written from the row "
    "would name the action that was not allowed, so the table refuses the verdict until it holds "
    "the replacement's digest, which is also when amending can be offered at all."
)

#: Widths, named once so the model, the migration and the store agree.
ID_CHARS: Final = 128
CAPABILITY_CHARS: Final = 200
HASH_CHARS: Final = 128
DIGEST_CHARS: Final = 64
STATE_CHARS: Final = 16
VERDICT_CHARS: Final = 16
#: `REASON_CODE` admits sixty-one characters.
REASON_CODE_CHARS: Final = 64
#: `SuspendedAction.artefact`'s own bound.
ARTEFACT_CHARS: Final = 8000

#: The verdicts this row can record faithfully. See the constant above for the one it cannot.
RECORDED_VERDICTS: Final[frozenset[ApprovalVerdict]] = frozenset(
    {ApprovalVerdict.APPROVED, ApprovalVerdict.REJECTED, ApprovalVerdict.TAKEN_OVER}
)

#: The longest window a row may carry, in whole hours, from the leash's own constant.
MAX_WINDOW_HOURS: Final = int(MAX_APPROVAL_WINDOW.total_seconds() // 3600)


class SuspensionRow(TimestampMixin, Base):
    """`gate.suspension`. One suspended action, and its decision once somebody takes one."""

    __tablename__ = "suspension"

    id: Mapped[str] = mapped_column(String(ID_CHARS), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(ID_CHARS), nullable=False)
    #: Whose reach the action would run under. The only principal who may raise it.
    principal_id: Mapped[str] = mapped_column(String(ID_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(ID_CHARS), nullable=False)
    #: `action.tool.required_capability`. See the module docstring.
    required_capability: Mapped[str] = mapped_column(String(CAPABILITY_CHARS), nullable=False)
    action: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ent_hash: Mapped[str] = mapped_column(String(HASH_CHARS), nullable=False)
    artefact: Mapped[str] = mapped_column(String(ARTEFACT_CHARS), nullable=False)
    action_digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(
        String(STATE_CHARS), nullable=False, server_default=ApprovalState.PENDING.value
    )
    decided_by: Mapped[str | None] = mapped_column(String(ID_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: What the person did, which the trigger records. See the module docstring.
    verdict: Mapped[str | None] = mapped_column(String(VERDICT_CHARS), nullable=True)
    #: Why, on every verdict but an approval. A code in `REASON_CODE`'s grammar, never prose.
    reason_code: Mapped[str | None] = mapped_column(String(REASON_CODE_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(f"id ~ '{IDENTIFIER}'", name="id_is_an_identifier"),
        CheckConstraint(f"trace_id ~ '{IDENTIFIER}'", name="trace_id_is_an_identifier"),
        CheckConstraint(f"principal_id ~ '{IDENTIFIER}'", name="principal_id_is_an_identifier"),
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(
            "length(btrim(required_capability)) > 0", name="an_action_requires_something"
        ),
        CheckConstraint("length(btrim(ent_hash)) > 0", name="a_reach_was_recorded"),
        CheckConstraint("length(artefact) > 0", name="something_was_shown"),
        CheckConstraint(f"action_digest ~ '{DIGEST}'", name="action_digest_shape"),
        CheckConstraint(one_of("state", ApprovalState), name="state"),
        CheckConstraint("expires_at > raised_at", name="a_window_ends_after_it_opens"),
        CheckConstraint(
            f"expires_at - raised_at <= interval '{MAX_WINDOW_HOURS} hours'",
            name="a_window_is_bounded",
        ),
        CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        CheckConstraint(
            "(decided_by IS NULL) = (state = 'pending')",
            name="only_a_decided_suspension_names_its_decider",
        ),
        CheckConstraint(one_of("verdict", RECORDED_VERDICTS), name="verdict"),
        CheckConstraint(
            "(verdict IS NULL) = (state = 'pending')",
            name="a_decided_suspension_names_its_verdict",
        ),
        CheckConstraint(
            "verdict IS NULL OR (verdict = 'approved') = (state = 'approved')",
            name="a_verdict_agrees_with_the_state_resume_reads",
        ),
        CheckConstraint(
            f"reason_code IS NULL OR reason_code ~ '{REASON_CODE}'", name="reason_code_grammar"
        ),
        CheckConstraint(
            "(reason_code IS NULL) = (verdict IS NULL OR verdict = 'approved')",
            name="every_verdict_but_an_approval_says_why",
        ),
        Index(
            "ix_suspension_pending_capability",
            "required_capability",
            postgresql_where=text("state = 'pending'"),
        ),
        {"schema": "gate"},
    )
