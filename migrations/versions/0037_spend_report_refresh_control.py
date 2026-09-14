"""The control-run name constraint admits the spend report refresh.

`brain.ops.controls` registers `spend_report_refresh`, the worker's schedule starts it, and the
check constraint on `ops.control_run.name` is generated from that registry. Without the widening
the model and the migration chain disagree, and the first run the schedule records for the
refresh is refused by the database, which is a control that is started on time and can never
say so.

The constraint is dropped by whichever name it holds and recreated, for the reason `0030` gives:
`0025` passed a name that was already prefixed, so a database built by it and one built from the
model name the same constraint differently.

**The downgrade narrows it again and fails if a refresh run was ever recorded**, which is the
correct restriction: a run record is history, and a downgrade that silently deleted the evidence
that a control ran would be the one migration here that edits the past.

Task ids: M36.1.3.2
"""

from __future__ import annotations

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

#: The control-run name constraint, widened for `spend_report_refresh`. Alphabetical, matching
#: how `brain.tables.identity.one_of` sorts, so the model and the migration compare equal as text.
WITH_SPEND_REPORT_REFRESH = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh')"
)
WITHOUT_SPEND_REPORT_REFRESH = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction')"
)

#: What this migration replaces: `0030`'s list, which is the one in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_SPEND_REPORT_REFRESH: WITH_SPEND_REPORT_REFRESH}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which this copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
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
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_SPEND_REPORT_REFRESH, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITHOUT_SPEND_REPORT_REFRESH, schema="ops"
    )
