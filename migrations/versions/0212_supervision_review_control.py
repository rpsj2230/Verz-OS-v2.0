"""The worker may record a run of the thirty-day supervision review.

M13.5.18 asks that a supervised agent's pin be reviewed at thirty days against measured
confidence. `brain.agents.supervision.review` decides that and the person-pressed Review asks it,
and until now nothing asked it on a schedule. `brain.ops.supervision_review` is the second caller,
registered as the control `supervision_review`, and the run it reports is recorded in
`ops.control_run`, whose name constraint admits only the controls that existed when it was last
widened. Without this migration the first run the schedule records is refused by the database.

**The control-run names gain `supervision_review`**, replacing `0209`'s. **No table, no column and
no policy.** The review writes `agent.supervision_pin` through `0195`'s own insert policy, which
admits a row whose `decided_by` is the session's principal, and the run sets that principal to the
system reviewer's name. Nothing about that table changes here, and in particular no ledger trigger
is added to it: a person-pressed review has none either, and whether a review should append to the
ledger is the owner's question (needs-rupash 174), not a side effect of admitting a control name.

**The downgrade** puts `0209`'s names back `NOT VALID`, for `0026`'s reason: a run already
recorded under the new name stays, and only a new one is refused.

Task ids: M13.5.18

Revision ID: 0212
Revises: 0211
"""

from __future__ import annotations

from alembic import op

revision = "0212"
down_revision = "0211"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The control-run names, with and without `supervision_review`. The second is `0209`'s.
WITH_SUPERVISION_REVIEW = (
    "name IN ('acceptance_run', 'approved_actions', 'audit_anchor', 'automation_run', "
    "'backup_exposure', 'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', "
    "'elevation_anchor', 'entity_resolution', 'erasure_queue', 'escalation_expiry', "
    "'evening_digest', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh', 'supervision_review', "
    "'vault_audit_ship', 'vault_token_renewal')"
)
WITHOUT_SUPERVISION_REVIEW = (
    "name IN ('acceptance_run', 'approved_actions', 'audit_anchor', 'automation_run', "
    "'backup_exposure', 'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', "
    "'elevation_anchor', 'entity_resolution', 'erasure_queue', 'escalation_expiry', "
    "'evening_digest', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh', 'vault_audit_ship', "
    "'vault_token_renewal')"
)

#: What this migration replaces: `0209`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_SUPERVISION_REVIEW: WITH_SUPERVISION_REVIEW}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0133` copies.
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
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_SUPERVISION_REVIEW, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_SUPERVISION_REVIEW,
        schema="ops",
        postgresql_not_valid=True,
    )
