"""One row per attempt to run a control, so "it has not run" is a fact rather than a silence.

`brain.ops.controls` is the registry of mechanisms that have to keep running.
`brain.ops.schedule` decides which of them are owed a run at an instant. Both are pure and
neither remembers anything, which is fine until the process restarts: a scheduler whose only
record of the last run is in memory starts every control again on every deploy, and on a
system that deploys on every push that is a retention sweep several times a day.

**An attempt table, not a last-run column, and the difference is the case that matters.** A
single mutable row per control answers "when did it last run" and destroys the answer to "when
did it stop working", which is the question somebody actually asks. It also cannot express the
state this whole area exists to catch: a control that starts every interval, fails every
interval, and looks from the outside exactly like one that is working. Rows are appended and
never updated. See `A_CONTROL_THAT_FAILS_EVERY_RUN_LOOKS_LIKE_ONE_THAT_RUNS`.

**Two clocks, and they are different columns rather than one column read twice.** When a
control may next be *tried* is measured from its last attempt, so a broken control is retried
on its own cadence rather than every tick. How *late* it is measured from its last success,
because a control that has been failing hourly for a week has not run for a week. Folding
them together gives a mechanism that is permanently on time and permanently broken, which is
the exact shape of the failure the registry was written about.

**`ops`, and it is the schema's own description.** `brain.db.SCHEMAS` calls `ops` "scheduled
jobs, budgets, deployment records". Note the same consequence `brain.tables.routing` records:
`brain.ops.sweeps.sweep_rls` does not check `ops`, so nothing in CI would notice row-level
security missing here. It is enabled in the migration and asserted in
`tests/unit/test_tables.py`, and the sweep's schema list is the thing that should change.

**No foreign key to a control.** The registry is a compiled constant in
`brain.ops.controls.CONTROLS` and not a table, deliberately: it is a fact about the product
rather than a client's data, for the same reason `brain.ops.starter.roles` is read off an
enum. A foreign key would need a table that mirrors the constant, and a mirror of a constant
is the second copy this repository refuses. What the column gets instead is a check that the
name is one the registry knows, generated from the registry itself so it cannot disagree.

Rejected: recording the control's cadence on the row so a reader could see what it was at the
time. It sounds like provenance and it is a second copy of a number that lives beside the
mechanism, which is exactly what `brain.ops.controls` refuses to hold. A cadence that changed
is visible in the file that changed it.

Task ids: M37.5.1.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.controls import CONTROLS
from brain.tables.identity import one_of

#: What an attempt ended as.
#:
#: `ok` and `failed` are the two a run produces. `refused` is the third and it is not a
#: failure: it is a control that was owed, was reached, and declined to act, which today is a
#: destructive control running in report-only mode. Folding it into `ok` would make a sweep
#: that deleted nothing indistinguishable from one that deleted, and folding it into `failed`
#: would alert on a system behaving exactly as configured.
OUTCOMES: Final[tuple[str, ...]] = ("ok", "failed", "refused")

#: Why the table is appended to rather than updated.
A_CONTROL_THAT_FAILS_EVERY_RUN_LOOKS_LIKE_ONE_THAT_RUNS: Final = (
    "A last-run column updated on every attempt says a control ran an hour ago whether it "
    "worked or not, so a mechanism that has been failing for a week reports as healthy and "
    "its console row is green. The outcome has to be on the row, and the row has to be kept, "
    "or the only durable record of a control is the claim that it was started."
)

#: `Control.name` is a short identifier. Bounded at the width the longest one takes with room,
#: so a mistyped column cannot hold a paragraph.
CONTROL_NAME_CHARS: Final = 64

#: What the detail column may hold. A sentence for a person, never a payload: this table is
#: read by an operator asking why a mechanism stopped, and a serialised object in it would be
#: a second place the system's own state lives.
DETAIL_CHARS: Final = 2000


class ControlRunRow(Base):
    """`ops.control_run`. One attempt to run one control, kept (M37.5.1.3).

    `started_at` and `finished_at` are both recorded, and the gap between them is the only
    way to see a control that is slower than its own cadence, which is a mechanism that
    overlaps itself and reports every run as fine. A row with a `started_at` and no
    `finished_at` is a run that did not return: the process died, or it is still going, and
    those two are told apart by whether anything holds its lock.

    `report_only` is on the row rather than inferred from the outcome, because the same
    control produces `refused` for two different reasons over its life and a reader six months
    later cannot reconstruct which mode it was in. See
    `brain.ops.schedule.A_SWEEP_RELEASED_BEFORE_ANYBODY_READ_ITS_REPORT_IS_A_DELETION_NOBODY_APPROVED`.

    There is no soft delete and no timestamp mixin. A run record that could be marked deleted
    is a run record somebody can make disappear, and the whole value of this table is that it
    outlives the opinion of whoever is looking at it.
    """

    __tablename__ = "control_run"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    #: The control's name in `brain.ops.controls.CONTROLS`.
    name: Mapped[str] = mapped_column(String(CONTROL_NAME_CHARS), nullable=False)

    #: When this process took the lock and began.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    #: When it returned. Null while it is running, and null for ever if the process died.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: One of `OUTCOMES`. Null while it is running.
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)

    #: True when the control was reached in report-only mode and was not allowed to act.
    report_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: A sentence for whoever is asking why. Never a payload.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Generated from the registry rather than typed, for the reason `one_of` exists: a
        # hand-written copy of a closed set stops matching it the first time somebody adds a
        # member, and the failure is a row the database refuses in production after passing
        # every test that only exercised the Python side.
        CheckConstraint(
            one_of("name", tuple(one.name for one in CONTROLS)), name="control_run_name"
        ),
        # `IS NULL OR` because the column is null while the run is going, and a plain `IN`
        # would pass a null anyway under three-valued logic. Written out so the constraint
        # says which of the two it means rather than relying on that.
        CheckConstraint(
            f"outcome IS NULL OR {one_of('outcome', OUTCOMES)}", name="control_run_outcome"
        ),
        # A run that has finished has an outcome and a run that has not has neither. The two
        # halves are one constraint because the states in between are the ones that would be
        # read wrong: a finished run with no outcome reads as still going for ever, and an
        # outcome with no finish reads as a run that ended without ending.
        CheckConstraint(
            "(finished_at IS NULL AND outcome IS NULL) OR "
            "(finished_at IS NOT NULL AND outcome IS NOT NULL)",
            name="control_run_finished_with_an_outcome",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="control_run_finished_after_it_started",
        ),
        CheckConstraint(
            f"detail IS NULL OR length(detail) <= {DETAIL_CHARS}",
            name="control_run_detail_is_a_sentence",
        ),
        # The scheduler's own question, asked every tick: the newest run of each control, and
        # the newest successful one. Descending because both answers are the first row.
        Index("ix_control_run_by_control", "name", "started_at", postgresql_using="btree"),
        {"schema": "ops"},
    )
