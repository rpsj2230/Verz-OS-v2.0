"""Record every session ended before it lapsed in the audit ledger, from the database.

`auth.session` says when a sign-in stopped and why, and nothing says who stopped it. M27.7.10
puts a control on the Sessions screen that ends one, because revoking a grant does not close a
session, and an ending nobody is named for is the one an auditor is asked about afterwards. This
migration widens two constraints and adds the trigger that writes the entry.

**Two constraints, both widened and neither rewritten.** The ledger's action list gains
`session_end`, superseding `0047`'s list. `auth.session.end_reason` gains `ended_from_console`,
superseding `0003`'s, because an ending an administrator chose is neither a disable nor a
retirement and recording it as either would put a fact about the principal on a row where
nothing about the principal changed.

**A trigger rather than the route, for the reason `0003` and `0047` give.** `0003`'s own
cascade ends every session of a principal who is disabled or retired, from a trigger on
`auth.principal`, and a route that wrote the entry would leave every one of those unrecorded. An
operator ending a session with a statement at a prompt is recorded as well. The trigger fires for
every writer, the table owner included.

**An expiry is not recorded.** `expired` is a sweep tidying a row whose time had already run
out, which is nobody's act, and a sweep over a busy install would write one ledger entry per
sign-in per day into the table that is kept for ever. The other three reasons are acts.

**The actor is named when the application names it and recorded as `unattributed` when it does
not, and never refused.** Ending a session takes a way in away, which is `0047`'s retirement
case: refusing an ending at midnight because a setting was not typed leaves the session open,
which is the failure in the wrong direction. The console's route sets `brain.actor_id` in the
ending's own transaction, and so does anything that disables a principal through the
application.

**The subject is the principal, and the session id is not in the entry.** The person whose
sign-in was ended reads that it was, among the entries about them. A session id is not a field
name, so `brain.audit.ledger.redact_details` would store the marker, and the entry has to load
through `AuditEntry._names_only`, which refuses anything the redactor would have stripped.

**The append is `0003`'s, and it is a third copy of that block**, beside `0047`'s second. Same
advisory lock, same sequence and parent read, same `obs.audit_entry_hash`, same refusal of a
discarded MERGE, so an entry from here interleaves with a grant's and a sign-in's on one chain.
Rejected for the reason `0047` gives: rewriting `0003`'s trigger to call a shared append in this
migration edits a function every grant in production goes through in order to add a feature to a
different table. The three copies name each other.

**The downgrade can fail, which is correct**, for the reason `0026` gives: narrowing either
list is refused once any row carries the new value, and an audit row cannot be removed to make
room.

Task ids: none
"""

from __future__ import annotations

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

#: Alphabetical, matching how `tables.identity.one_of` sorts.
WITH_SESSION_END = (
    "action IN ('approval', 'break_glass', 'compose_change', 'deny', 'entity_merge', "
    "'grant', 'leash_change', 'publish', 'record_read', 'revoke', 'session_end', 'sign_in')"
)
WITHOUT_SESSION_END = (
    "action IN ('approval', 'break_glass', 'compose_change', 'deny', 'entity_merge', "
    "'grant', 'leash_change', 'publish', 'record_read', 'revoke', 'sign_in')"
)

WITH_CONSOLE_ENDING = (
    "end_reason IN ('ended_from_console', 'expired', 'principal_disabled', "
    "'principal_retired', 'signed_out')"
)
WITHOUT_CONSOLE_ENDING = (
    "end_reason IN ('expired', 'principal_disabled', 'principal_retired', 'signed_out')"
)

#: What this migration replaces: `0047`'s action list and `0003`'s end reasons, which are the
#: ones in the database.
SUPERSEDES: dict[str, str] = {
    WITHOUT_SESSION_END: WITH_SESSION_END,
    WITHOUT_CONSOLE_ENDING: WITH_CONSOLE_ENDING,
}

SESSION_END_TRIGGER_FUNCTION = """
CREATE FUNCTION auth.record_session_end() RETURNS trigger
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
    IF OLD.ended_at IS NOT NULL OR NEW.ended_at IS NULL THEN
        RETURN NULL;
    END IF;
    IF NEW.end_reason = 'expired' THEN
        RETURN NULL;
    END IF;

    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    v_details := jsonb_build_object('reason', NEW.end_reason);
    IF v_actor IS NULL THEN
        v_actor := 'unattributed';
        v_details := v_details || jsonb_build_object('actor', 'unattributed');
    END IF;

    -- The append, as 0003's gate.record_entitlement_change and 0047's
    -- auth.record_sign_in_change write it. See the module docstring.
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
        v_seq, v_at, v_actor, 'session_end', 'principal:' || NEW.principal_id, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'session_end', 'principal:' || NEW.principal_id,
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

SESSION_END_TRIGGER = """
CREATE TRIGGER session_records_its_end
    AFTER UPDATE ON auth.session
    FOR EACH ROW EXECUTE FUNCTION auth.record_session_end()
"""


def upgrade() -> None:
    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITH_SESSION_END, schema="obs")
    op.drop_constraint("end_reason", "session", schema="auth", type_="check")
    op.create_check_constraint("end_reason", "session", WITH_CONSOLE_ENDING, schema="auth")
    op.execute(SESSION_END_TRIGGER_FUNCTION)
    op.execute(SESSION_END_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER session_records_its_end ON auth.session")
    op.execute("DROP FUNCTION auth.record_session_end()")
    op.drop_constraint("end_reason", "session", schema="auth", type_="check")
    op.create_check_constraint("end_reason", "session", WITHOUT_CONSOLE_ENDING, schema="auth")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITHOUT_SESSION_END, schema="obs")
