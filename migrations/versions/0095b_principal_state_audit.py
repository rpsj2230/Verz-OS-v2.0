"""Disabling somebody and enabling them again each leave one entry in the audit ledger.

`brain.principal_state_routes` sets and clears `auth.principal.disabled_at`. A disable was on the
record only through the `session_end` entries `0050` appends for the sessions `0003`'s cascade
ends, so a person disabled with no session open left nothing, and an enable, which ends no session,
always left nothing: access restored and nobody recorded as having restored it. This migration adds
the `principal_state` action and a trigger that appends exactly one entry for each change of
`disabled_at` between set and unset, in the writing transaction, with `{"change": "disabled"}` or
`{"change": "enabled"}` under the principal's own subject.

**A trigger rather than the route, for `0050`'s reason.** An operator's statement at a prompt is
recorded as well as the console's control, and the entry commits with the row or not at all.

**The actor is named when the application names it and `unattributed` when not, and never
refused**, as `0050` records an ending: refusing a disable at midnight because a setting was not
typed leaves somebody signed in who should not be.

**A write that changes nothing is not recorded.** Setting `disabled_at` from one instant to another,
or clearing it when it is clear, is not a change of state, and the store writes neither anyway.

**The append is `0003`'s block once more**, beside `0050`'s and `0093`'s, for the reason `0047`
gives against editing a function every grant in production goes through.

**The downgrade** drops the trigger and its function and puts `0093`'s action list back `NOT VALID`,
for `0026`'s reason: an entry already recorded stays.

Task ids: M1.2.3

Revision ID: 0095b
Revises: 0095
"""

from __future__ import annotations

from alembic import op

revision = "0095b"
down_revision = "0095"
branch_labels = None
depends_on = None

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0093`'s.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'principal_state', 'publish', "
    "'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', "
    "'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', "
    "'vault_access', 'webhook')"
)

#: What this migration replaces: `0093`'s action list, the one in the database.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

TRIGGER_FUNCTION = """
CREATE FUNCTION auth.record_principal_state() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF (OLD.disabled_at IS NULL) = (NEW.disabled_at IS NULL) THEN
        RETURN NULL;
    END IF;

    v_details := jsonb_build_object(
        'change', CASE WHEN NEW.disabled_at IS NULL THEN 'enabled' ELSE 'disabled' END
    );
    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    IF v_actor IS NULL THEN
        v_actor := 'unattributed';
        v_details := v_details || jsonb_build_object('actor', 'unattributed');
    END IF;

    -- The append, as 0003, 0050 and 0093 write it. See the module docstring.
    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, v_actor, 'principal_state', 'principal:' || NEW.id, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'principal_state', 'principal:' || NEW.id,
                v_ent_hash, v_trace, v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
    RETURN NULL;
END;
$$
"""

TRIGGER = """
CREATE TRIGGER principal_state_is_audited
    AFTER UPDATE OF disabled_at ON auth.principal
    FOR EACH ROW EXECUTE FUNCTION auth.record_principal_state()
"""


def upgrade() -> None:
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER principal_state_is_audited ON auth.principal")
    op.execute("DROP FUNCTION auth.record_principal_state()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
