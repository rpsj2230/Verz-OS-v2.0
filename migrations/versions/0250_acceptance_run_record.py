"""An acceptance run gets a record of its own, so it can be finished by a worker that did not begin it.

**Found on the owner's staging install, and not specific to it.** A run of the install acceptance
checks takes thirty-five minutes and more, every merge to main redeploys, and a redeploy restarts
the worker, which killed the run in progress. `ops.acceptance_result` was written when the run
ended, so on a day of frequent merges no run was ever recorded and no task could close however many
checks existed. A fresh install with a few hundred checks has the same fault the day it is deployed
twice in an hour.

**`ops.acceptance_run`: one row per run, `running` until the last check is recorded.** The run's id,
the commit it checks, why it ran, its status (`running`, `complete` or `abandoned`), when it
started, a heartbeat the worker moves on at every check, and when it ended. `brain.tables.acceptance`
argues the columns and `brain.ops.acceptance_resume` the rule built on them: results are appended to
`ops.acceptance_result` one check at a time under the run's id, a worker that finds a run of the
commit it serves whose heartbeat has stopped finishes it, and a run of any other commit that stopped
is marked `abandoned`. `brain.ops.proof_sweep` reads only `complete` runs.

**A result row with no run row is a complete run.** Every run before this migration was written
whole, in one transaction, so none of them is partial and none needs a row backfilled: the sweep
treats a run with no row here as complete. This is also why nothing is inserted by this migration:
it carries no install's data.

**Compatibility with the release before it.** The only change to a table that was already there is
none: the new table is created, and the previous release neither reads nor writes it, so it goes on
appending whole runs to `ops.acceptance_result`, which this release reads as complete.

**The application role may SELECT, INSERT and UPDATE the status columns, and only of a run still
`running`**: the update policy's `USING` clause reads `running`, so a run that is `complete` or
`abandoned` is a fact nothing edits, which is the rule `0133` holds for the results. No DELETE.
`USING (true)` on the read, for `0133`'s reason: the only reader is the sweep and the public
document, and neither carries anything a policy would narrow.

**The downgrade** drops the table. A run still `running` is then read, by the release before this
one, as the partial rows it wrote, and the next run of that commit starts afresh.

Task ids: M38.5.1

Revision ID: 0250
Revises: 0225
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0250"
# A branch migration: the newest on origin/main when it was written is 0225. The coordinator
# re-points it when the migrations land as one train.
down_revision = "0225"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`.
TABLES: tuple[str, ...] = ("ops.acceptance_run",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.tables.acceptance` by a test.
COMMIT_PATTERN = r"^[0-9A-Za-z._-]{1,40}$"
OCCASIONS = "occasion IN ('deploy', 'request')"
STATUSES = "status IN ('abandoned', 'complete', 'running')"

#: Column-level, so the worker can move a run on and finish it and can change nothing else.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE (status, heartbeat_at, ended_at) "
    "ON ops.acceptance_run TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.acceptance_run ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY acceptance_run_readable ON ops.acceptance_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY acceptance_run_opened ON ops.acceptance_run
        FOR INSERT TO brain_app
        WITH CHECK (status = 'running')
    """,
    """
    CREATE POLICY acceptance_run_moved_on_only_while_it_runs ON ops.acceptance_run
        FOR UPDATE TO brain_app
        USING (status = 'running')
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "acceptance_run",
        sa.Column("run_id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("commit", sa.String(40), nullable=False),
        sa.Column("occasion", sa.String(8), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"commit ~ '{COMMIT_PATTERN}'", name="commit_shape"),
        sa.CheckConstraint(OCCASIONS, name="occasion"),
        sa.CheckConstraint(STATUSES, name="status"),
        sa.CheckConstraint("(status = 'running') = (ended_at IS NULL)", name="ended_once_finished"),
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The policies go with the table.
    op.drop_table("acceptance_run", schema="ops")
