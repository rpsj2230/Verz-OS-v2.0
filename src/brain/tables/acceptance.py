"""`ops.acceptance_result`: what each install acceptance check came to, on which commit, and when.

`brain.ops.acceptance` holds the checks and `brain.ops.acceptance_run` runs them; this is where a
run leaves its verdict, so a task can be closed from a row the install wrote rather than from a
screenshot somebody took. `brain.acceptance_routes` serves it at `/api/acceptance.json`.

**One row per check per run, appended and never edited.** A check that passed on one commit and
fails on the next is two facts, and the first is what somebody reading a regression needs. SELECT
and INSERT for the application role, row-level security on with a policy for each and no other,
for `0093`'s reason; the worker writes as the database's owner.

**Keyed by the commit, and the commit is a value.** The release a run checked is a fact about that
day whether or not the commit is still deployed, so there is nothing for a key to point at.

**Nothing here can hold a company's data.** The check's name and leaves are the product's, the
outcome is one of three words, and the reason is a sentence the check's source wrote, bounded by
the column (`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`).

**`ops.acceptance_run`: the run's own record, so a run can outlive the process that began it.**
A run takes thirty-five minutes and more and the worker is restarted by every deploy, so rows
written only when the run ended were never written on a day of frequent merges. A run is now opened
here before its first check, each check's row is appended as it finishes, and the run is marked
`complete` only when the last one has. See `brain.ops.acceptance_resume`. **A result row with no
run row is a complete run**, because every run before this table existed was written whole.

Task ids: M38.5.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.identity import one_of

#: A commit as `brain.settings.Settings.resolved_commit` reports one: a sha, or a word such as
#: `unknown` or `wip` on a process with no manifest.
COMMIT_PATTERN: Final = r"^[0-9A-Za-z._-]{1,40}$"

#: `brain.ops.acceptance.CHECK_NAME`, restated for `0009`'s reason and held equal by a test.
CHECK_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]{2,63}$"

#: One or more WBS leaf ids, separated by single spaces.
LEAVES_PATTERN: Final = r"^M[0-9]+(\.[0-9]+){2,3}( M[0-9]+(\.[0-9]+){2,3})*$"

#: The three words, as `brain.ops.post_deploy` spells them.
OUTCOMES: Final = ("failed", "not run", "passed")

#: The two reasons a run happens, as `brain.ops.acceptance.Occasion` spells them.
OCCASIONS: Final = ("deploy", "request")

#: Where a run is: still going, finished with every check recorded, or left behind by a release
#: that replaced it before it was finished. Alphabetical, as `one_of` is read.
RUN_STATUSES: Final = ("abandoned", "complete", "running")

#: `brain.ops.acceptance.REASON_CHARS`, held equal by a test.
REASON_CHARS: Final = 240
LEAVES_CHARS: Final = 400


class AcceptanceResultRow(Base):
    """`ops.acceptance_result`. One check's outcome on one run of the suite."""

    __tablename__ = "acceptance_result"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: Every row one run wrote carries the same id, so a run reads back whole.
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    commit: Mapped[str] = mapped_column(String(40), nullable=False)
    occasion: Mapped[str] = mapped_column(String(8), nullable=False)
    check_name: Mapped[str] = mapped_column(String(64), nullable=False)
    leaves: Mapped[str] = mapped_column(String(LEAVES_CHARS), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(REASON_CHARS), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"commit ~ '{COMMIT_PATTERN}'", name="commit_shape"),
        CheckConstraint(one_of("occasion", OCCASIONS), name="occasion"),
        CheckConstraint(f"check_name ~ '{CHECK_NAME_PATTERN}'", name="check_name_shape"),
        CheckConstraint(f"leaves ~ '{LEAVES_PATTERN}'", name="leaves_shape"),
        CheckConstraint(one_of("outcome", OUTCOMES), name="outcome"),
        CheckConstraint("checked_at >= started_at", name="checked_after_it_started"),
        Index("ix_acceptance_result_commit", "commit", "started_at"),
        {"schema": "ops"},
    )


class AcceptanceRunRow(Base):
    """`ops.acceptance_run`. One run of the suite: which commit, why, and whether it finished.

    **Written by the worker, which may update a run that is still `running` and nothing else.**
    Once a run is `complete` or `abandoned` nothing edits it (the update policy reads only
    `running` rows), so a finished run stays the fact it was when it finished.
    """

    __tablename__ = "acceptance_run"

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    commit: Mapped[str] = mapped_column(String(40), nullable=False)
    occasion: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(9), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Moved on at the start of every check and when a worker takes the run over. A run whose
    #: heartbeat is old belongs to a process that is gone.
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"commit ~ '{COMMIT_PATTERN}'", name="commit_shape"),
        CheckConstraint(one_of("occasion", OCCASIONS), name="occasion"),
        CheckConstraint(one_of("status", RUN_STATUSES), name="status"),
        CheckConstraint("(status = 'running') = (ended_at IS NULL)", name="ended_once_finished"),
        {"schema": "ops"},
    )
