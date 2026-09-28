"""Install acceptance results get a table, and the acceptance run joins the control-run names.

**`ops.acceptance_result`: one row per check per run of `brain.ops.acceptance_run`.** The run's
id, the commit the process served, why it ran (a deploy nobody had checked, or a person asking),
the check's name and the leaves it proves, passed, failed or not run, a reason that is a sentence
the check's source wrote, and when the run started and the check ended. `brain.tables.acceptance`
argues the columns. `/api/acceptance.json` reads it, so a task can be closed from a row the
install wrote.

**SELECT and INSERT, and no UPDATE or DELETE**, for `0093`'s reason: a result is a fact about one
day and nothing edits it. The worker appends as the database's owner, and the application role
is granted the append so a worker configured with that role's login is not refused. **`USING
(true)` on the read**: the only reader is the public document, which carries nothing a policy
would narrow.

**One supersession.** The control-run names gain `acceptance_run`, replacing `0093`'s, which is
the newest in the database.

**The downgrade** drops the table, which discards every result, and puts the control-run names back
`NOT VALID`, for `0026`'s reason: a run already recorded stays.

Task ids: M38.5.1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0133"
# The newest migration on origin/main when this was written, 52b0a204. Nothing after 0093 touches
# the control-run names.
down_revision = "0117"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.acceptance_result",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.tables.acceptance` by
#: `tests/unit/test_acceptance.py`.
COMMIT_PATTERN = r"^[0-9A-Za-z._-]{1,40}$"
CHECK_NAME_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
LEAVES_PATTERN = r"^M[0-9]+(\.[0-9]+){2,3}( M[0-9]+(\.[0-9]+){2,3})*$"
OUTCOMES = "outcome IN ('failed', 'not run', 'passed')"
OCCASIONS = "occasion IN ('deploy', 'request')"
REASON_CHARS = 240
LEAVES_CHARS = 400

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.acceptance_result TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.acceptance_result ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY acceptance_result_readable ON ops.acceptance_result
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY acceptance_result_appendable ON ops.acceptance_result
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: The control-run names, with and without `acceptance_run`. The second is `0093`'s.
WITH_ACCEPTANCE_RUN = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)
WITHOUT_ACCEPTANCE_RUN = (
    "name IN ('audit_anchor', 'automation_run', 'backup_exposure', 'canary_run', "
    "'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)

#: What this migration replaces: `0093`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_ACCEPTANCE_RUN: WITH_ACCEPTANCE_RUN}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0093` copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname
          FROM pg_constraint c
         WHERE c.conrelid = 'ops.control_run'::regclass
           AND c.contype = 'c'
           AND right(c.conname, 16) = 'control_run_name'
    LOOP
        EXECUTE 'ALTER TABLE ops.control_run DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "acceptance_result",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("commit", sa.String(40), nullable=False),
        sa.Column("occasion", sa.String(8), nullable=False),
        sa.Column("check_name", sa.String(64), nullable=False),
        sa.Column("leaves", sa.String(LEAVES_CHARS), nullable=False),
        sa.Column("outcome", sa.String(8), nullable=False),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"commit ~ '{COMMIT_PATTERN}'", name="commit_shape"),
        sa.CheckConstraint(OCCASIONS, name="occasion"),
        sa.CheckConstraint(f"check_name ~ '{CHECK_NAME_PATTERN}'", name="check_name_shape"),
        sa.CheckConstraint(f"leaves ~ '{LEAVES_PATTERN}'", name="leaves_shape"),
        sa.CheckConstraint(OUTCOMES, name="outcome"),
        sa.CheckConstraint("checked_at >= started_at", name="checked_after_it_started"),
        schema="ops",
    )
    op.create_index(
        "ix_acceptance_result_commit",
        "acceptance_result",
        ["commit", "started_at"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)

    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint("control_run_name", "control_run", WITH_ACCEPTANCE_RUN, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_ACCEPTANCE_RUN,
        schema="ops",
        postgresql_not_valid=True,
    )
    # The index and the policies go with the table.
    op.drop_table("acceptance_result", schema="ops")
