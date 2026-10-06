"""The worker finds approved actions that have not run, and nothing else about them.

M13.7.6 asks that an approved action run once without the requester returning, at the requester's
reach re-resolved at that moment, and that a rejected, amended or lapsed one never run. Until this
migration an approval was recorded and nothing sent it: `brain.gate.leash.resume` re-checks and runs
an approved suspension once, and nothing called it with nobody present.

**`gate.approved_to_run` is `SECURITY DEFINER`, for one read and one reason**, as `0172`'s
`gate.takeover_instants` is. `0042`'s policy admits a reader to a suspension only when it runs as
them, when they decided it, or when it is pending and they may approve it, so the worker has no
reach under which every approved action is visible, and must not be given one. The function returns
the id and the principal of each approved suspension that is still inside its window, names one of
the tools the caller can run, and has no operation recorded against it in `ops.operation`, and
nothing else: no action, no artefact, no reason, no decider. The worker then reads each one **at its
principal's reach, re-resolved now**, through `brain.gate.suspension_store`, so the policy's own-row
clause is what admits it and `resume` re-checks everything against the present.

**An action that has an operation recorded is not listed again.** `brain.gate.leash.resume` keys a
run in `ops.operation` by the approval's id, before the action is executed, so a run that won its
key is out of this list whether it happened, failed or is unknown; a retry is the recovery
control's business (`side_effect_resume`), and never this one's. The once is `resume`'s ledger, and
this filter only stops the worker asking about it every minute.

The window is a parameter and the body reads no clock, so the instant is the caller's, as it is in
`0172`. Its search path is pinned and every object is named with its schema. EXECUTE is revoked
from `PUBLIC` and granted to `brain_app`, the login the worker's controls use.

**The control-run names gain `approved_actions`**, replacing `0169`'s, so the worker can record its
scheduled run.

**The downgrade** drops the function and puts `0169`'s names back `NOT VALID`, for `0026`'s reason:
a run already recorded stays.

Revises `0154`, the head of main when this was written.

Task ids: M13.7.6

Revision ID: 0176
Revises: 0154
"""

from __future__ import annotations

from alembic import op

revision = "0176"
# The head of origin/main when this was written. Re-pointed at whichever migration is the head
# when it lands: nothing here depends on a table a later migration builds.
down_revision = "0154"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

#: `brain.gate.leash.ApprovalState.APPROVED`, copied for `0009`'s reason about reading live code
#: from a migration and held equal to it by a test.
APPROVED = "approved"

FUNCTION = "gate.approved_to_run(timestamptz, character varying[], integer)"

CREATE_FUNCTION = f"""
CREATE FUNCTION gate.approved_to_run(
    p_now timestamptz,
    p_tools character varying[],
    p_limit integer
)
RETURNS TABLE (suspension_id character varying, principal_id character varying)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT s.id, s.principal_id
      FROM gate.suspension s
     WHERE s.state = '{APPROVED}'
       AND s.expires_at > p_now
       AND (s.action -> 'tool' ->> 'name') = ANY (p_tools)
       AND NOT EXISTS (
           SELECT 1 FROM ops.operation o WHERE o.intent_ref = s.id
       )
     ORDER BY s.decided_at, s.id
     LIMIT p_limit
$$
"""  # noqa: S608 - the one interpolation is APPROVED, a constant of this module, never input

GRANTS: tuple[str, ...] = (
    f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {APP_ROLE}",
)

#: The control-run names, with and without `approved_actions`. The second is `0169`'s.
WITH_APPROVED_ACTIONS = (
    "name IN ('acceptance_run', 'approved_actions', 'audit_anchor', 'automation_run', "
    "'backup_exposure', 'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', "
    "'erasure_queue', 'escalation_expiry', 'evening_digest', 'knowledge_reverification', "
    "'model_health_probes', 'outbox_dispatch', 'queue_redrive', 'resolution_calibration', "
    "'restore_drill', 'retention_sweep', 'side_effect_resume', 'spend_correction', "
    "'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)
WITHOUT_APPROVED_ACTIONS = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'escalation_expiry', 'evening_digest', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh', "
    "'vault_audit_ship', 'vault_token_renewal')"
)

#: What this migration replaces: `0169`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_APPROVED_ACTIONS: WITH_APPROVED_ACTIONS}

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
    op.execute(CREATE_FUNCTION)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_APPROVED_ACTIONS, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_APPROVED_ACTIONS,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}")
