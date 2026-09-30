"""The evening digest joins the control-run names, so the worker can record its scheduled run.

**One supersession and nothing else.** The control-run names gain `evening_digest`, replacing
`0168`'s, which is the newest list in the database. No table: where the digest goes and when are
install settings in `ops.setting`, and what the last digest saw is one row there too
(`brain.ops.digest_run`), so the database is otherwise unchanged.

**The downgrade** puts the names back `NOT VALID`, for `0026`'s reason: a run already recorded
stays.

Task ids: M38.3.3.1
"""

from __future__ import annotations

from alembic import op

revision = "0169"
# Lands straight after #252's 0162, behind 0168, whose control-run names (with
# `escalation_expiry`) this one supersedes.
down_revision = "0162"
branch_labels = None
depends_on = None

#: The control-run names, with and without `evening_digest`. The second is `0168`'s.
WITH_EVENING_DIGEST = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'escalation_expiry', 'evening_digest', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh', "
    "'vault_audit_ship', 'vault_token_renewal')"
)
WITHOUT_EVENING_DIGEST = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'escalation_expiry', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh', 'vault_audit_ship', "
    "'vault_token_renewal')"
)

#: What this migration replaces: `0168`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_EVENING_DIGEST: WITH_EVENING_DIGEST}

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
    op.create_check_constraint("control_run_name", "control_run", WITH_EVENING_DIGEST, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_EVENING_DIGEST,
        schema="ops",
        postgresql_not_valid=True,
    )
