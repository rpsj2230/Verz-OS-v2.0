"""An agent changing owner leaves one entry in the audit ledger.

The Staff sources screen lets a reader take on an agent whose owner the staff sync marked as having
left (M1.8.9), and `brain.identity.lifecycle.adopt` is M26.3.2's act that does it. The owner moved
on `agent.agent` and nothing recorded who moved it: `agent.agent` had no audit trigger, and the
console audit listed the route's ledger proof as a gap. This migration adds the `agent_owner` action
and a trigger that appends exactly one entry for each change of `owner_id`, in the writing
transaction, with `{"change": "owner_changed", "from_owner": ..., "to_owner": ...}` under the
agent's own subject.

**A trigger rather than the route, for `0050`'s reason.** An owner changed at a prompt is recorded
as well as one changed from the console, and the entry commits with the row or not at all.

**The actor is named when the application names it and `unattributed` when not, and never
refused**, as `0095b` records a disable: the route sets it with `brain.tables.audit.attributed_to`
before the update.

**A write that changes nothing is not recorded.** An update that sets the owner it already had is
not a change of owner.

**The append is `0003`'s block once more**, beside `0050`'s, `0093`'s and `0095b`'s, for the reason
`0047` gives against editing a function every grant in production goes through.

**The downgrade** drops the trigger and its function and puts `0104`'s action list back `NOT
VALID`, for `0026`'s reason: an entry already recorded stays.

Task ids: M1.8.9, M26.3.2

Revision ID: 0105
Revises: 0104
"""

from __future__ import annotations

from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0104`'s.
WIDENED_ACTIONS = (
    "action IN ('agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'compose_change', 'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', "
    "'grant', 'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', "
    "'principal_state', 'publish', 'record_read', 'retention', 'revoke', 'routing', "
    "'session_end', 'setting', 'sign_in', 'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'breach', 'break_glass', 'certification', 'compose_change', "
    "'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', "
    "'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', 'principal_state', "
    "'publish', 'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', "
    "'sign_in', 'skill', 'vault_access', 'webhook')"
)

#: What this migration replaces: `0104`'s action list, the one in the database.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_agent_owner() RETURNS trigger
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
    IF OLD.owner_id IS NOT DISTINCT FROM NEW.owner_id THEN
        RETURN NULL;
    END IF;

    v_details := jsonb_build_object(
        'change', 'owner_changed',
        'from_owner', OLD.owner_id,
        'to_owner', NEW.owner_id
    );
    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    IF v_actor IS NULL THEN
        v_actor := 'unattributed';
        v_details := v_details || jsonb_build_object('actor', 'unattributed');
    END IF;

    -- The append, as 0003, 0050, 0093 and 0095b write it. See the module docstring.
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
        v_seq, v_at, v_actor, 'agent_owner', 'agent:' || NEW.id, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'agent_owner', 'agent:' || NEW.id,
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
CREATE TRIGGER agent_owner_is_audited
    AFTER UPDATE OF owner_id ON agent.agent
    FOR EACH ROW EXECUTE FUNCTION agent.record_agent_owner()
"""


def upgrade() -> None:
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER agent_owner_is_audited ON agent.agent")
    op.execute("DROP FUNCTION agent.record_agent_owner()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
