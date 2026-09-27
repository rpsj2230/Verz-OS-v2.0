"""The vault token renewal joins the control-run names, so the worker's schedule can record it.

`brain.ops.vault_renewal` is the control, argued there: the installer now mints two periodic tokens
on an install's own vault, a periodic token lapses for good when nothing renews it inside its
period, and the worker's schedule renews the worker's own. `brain.ops.controls` registers it, the
model's constraint is generated from that registry, and without this widening the first run the
schedule records is refused by the database, for the reason `0037` gives about the spend report
refresh. The constraint is dropped by whichever name it holds, as `0060` does.

No table, no policy and no grant: the runs go into `ops.control_run`, which already has all three.

**The downgrade keeps the runs already recorded**, for the reason `0026` gives: the names go back
`NOT VALID`, so a run already carrying the new one stays and no new one is accepted.

Task ids: M42.6.2
"""

from __future__ import annotations

from alembic import op

revision = "0066"
# The head of origin/main when this was written, which was `0064`. Re-pointed at whichever
# migration is the head when it is integrated: this touches one constraint and depends on no
# table a later migration builds.
down_revision = "0064"
branch_labels = None
depends_on = None

#: The control-run names, with and without `vault_token_renewal`. The second is `0060`'s.
WIDENED_NAMES = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'erasure_queue', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh', "
    "'vault_token_renewal')"
)
NARROWER_NAMES = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'erasure_queue', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh')"
)

#: What this migration replaces: `0060`'s control names, which are the ones in the database.
SUPERSEDES: dict[str, str] = {NARROWER_NAMES: WIDENED_NAMES}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0060` copies.
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
    op.create_check_constraint("control_run_name", "control_run", WIDENED_NAMES, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", NARROWER_NAMES, schema="ops", postgresql_not_valid=True
    )
