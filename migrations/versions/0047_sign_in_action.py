"""Record every sign-in binding and every retirement of one in the audit ledger, from the database.

`auth.principal_identity` holds which Keycloak subject signs in as which principal and has no
column saying who made that so. `brain.identity.sign_in_binding` writes it on an administrator's
act, and the first administrator's is written by the setup wizard's finishing screen, and
neither left a record anybody could come back to. This migration widens the action constraint
for `AuditAction.SIGN_IN` and adds the trigger that writes the entry.

**A trigger rather than the route, for the reason `0003` gives about grants.** A binding made by
an operator's statement at a psql prompt is as much a way in as one made in the console, and a
caller that has to remember to audit is the caller that forgets during an incident. The trigger
fires for every writer, the table owner included.

**Only the sign-in channel.** A chat channel's binding is a different act with its own writer,
and recording it as a sign-in would put Lark and Slack bindings into the answer to "who gave
this account a way in as her".

**The actor is named, and the two directions treat a missing name differently on purpose.** The
application sets `brain.actor_id` in the binding's own transaction, which
`brain.identity.sign_in_binding.SignInBindings` does on both writes.

- A binding with no actor named is refused. It is a new way into a principal, and one nobody is
  named for is the binding an audit exists to find; an operator making one by hand sets the
  setting first. See `A_WAY_IN_NAMES_WHO_MADE_IT` in that module.
- A retirement with no actor named is recorded as `unattributed` and never refused. It takes a
  way in away, and refusing an offboarding at midnight because a setting was not typed is the
  failure in the wrong direction. See `A_WAY_OUT_IS_NEVER_REFUSED_FOR_WANT_OF_A_NAME`.

**The append is `0003`'s, and it is a second copy of that block.** Same advisory lock, same
sequence and parent read, same `obs.audit_entry_hash`, same refusal of a discarded MERGE, so an
entry from here and one from a grant interleave on one chain. Rejected: rewriting `0003`'s
trigger to call a shared append function in the same migration, which edits a function every
grant in production goes through in order to add a feature to a different table. The two copies
are named in each other's neighbourhood so the next change to the chain's shape finds both.

**The downgrade keeps what the ledger already holds**, for the reason `0026` gives: the list goes
back `NOT VALID`, so a row already carrying `sign_in` stays and no new one is accepted.

Task ids: none
"""

from __future__ import annotations

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

#: Alphabetical, matching how `tables.identity.one_of` sorts.
WITH_SIGN_IN = (
    "action IN ('approval', 'break_glass', 'compose_change', 'deny', 'entity_merge', "
    "'grant', 'leash_change', 'publish', 'record_read', 'revoke', 'sign_in')"
)
WITHOUT_SIGN_IN = (
    "action IN ('approval', 'break_glass', 'compose_change', 'deny', 'entity_merge', "
    "'grant', 'leash_change', 'publish', 'record_read', 'revoke')"
)

#: What this migration replaces: `0026`'s list, which is the one in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_SIGN_IN: WITH_SIGN_IN}

#: The actor a retirement nobody was named for is recorded under, `unattributed`, is written
#: literally in the function below: an identifier by the ledger's grammar, and a word no
#: principal id in this system is spelled as.
SIGN_IN_TRIGGER_FUNCTION = """
CREATE FUNCTION auth.record_sign_in_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_change text;
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
    IF NEW.channel <> 'console' THEN
        RETURN NULL;
    END IF;
    IF tg_op = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_change := 'bound';
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        v_change := 'retired';
    END IF;

    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    v_details := jsonb_build_object('change', v_change);
    IF v_actor IS NULL THEN
        IF v_change = 'bound' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'a sign-in binding names who made it, and this one names nobody',
                ERRCODE = 'restrict_violation',
                HINT = 'set brain.actor_id in the same transaction before binding';
        END IF;
        v_actor := 'unattributed';
        v_details := v_details || jsonb_build_object('actor', 'unattributed');
    END IF;

    -- The append, as 0003's gate.record_entitlement_change writes it. See the module docstring.
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
        v_seq, v_at, v_actor, 'sign_in', 'principal:' || NEW.principal_id, v_ent_hash, v_trace,
        v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'sign_in', 'principal:' || NEW.principal_id, v_ent_hash,
                v_trace, v_details, v_prev, v_entry);

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

SIGN_IN_TRIGGER = """
CREATE TRIGGER principal_identity_records_sign_in
    AFTER INSERT OR UPDATE ON auth.principal_identity
    FOR EACH ROW EXECUTE FUNCTION auth.record_sign_in_change()
"""


def upgrade() -> None:
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITH_SIGN_IN, schema="obs")
    op.execute(SIGN_IN_TRIGGER_FUNCTION)
    op.execute(SIGN_IN_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER principal_identity_records_sign_in ON auth.principal_identity")
    op.execute("DROP FUNCTION auth.record_sign_in_change()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", WITHOUT_SIGN_IN, schema="obs", postgresql_not_valid=True
    )
