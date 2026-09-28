"""A service account's key revoked, or the account retired, reaches the ledger.

`0095` made `auth.service_account` and `auth.api_key`, and `brain.identity.service_account_store`
records the two writes that give an integration a credential, registering the account and issuing
a key, through `ops.credential_write`, whose `0054` trigger appends a `credential` entry. The two
acts that take a credential away wrote nothing but `deleted_at`: "who revoked the key the payroll
export used, and when" had no answer outside a log line, and it is the first question asked after
an integration stops working.

**Triggers on the two tables rather than another `ops.credential_write` row from the store.** That
row is a write into a slot and its entry carries no details, because nothing is left of a write
once the value is taken out; a revocation filed there would read exactly as a key issued. And a
trigger records an operator's `UPDATE` at a prompt as it records a press in the console, which is
`0054`'s reason and `0137`'s, so the chain keeps one writer.

**Under the member and the subject a write already uses.** `credential`, with the subject
`credential:service_accounts.<client id>` that `0054` writes for the same account's registration
and keys, so one account's whole history is one subject an auditor filters on. The details are the
change, `key_revoked` or `account_retired` (`brain.audit.record.CredentialChange`), and never the
key's handle, its digest or the owner: a handle is not a field name, and the account is the
subject already.

**Only the retirement is recorded, and only once.** The update policy `0095` gave both tables
refuses any update to a retired row, and the trigger appends when `deleted_at` goes from empty to
set and at no other update, so a statement that relabels a key appends nothing. A retired account
retires its live keys first in the same transaction, so the ledger reads one `key_revoked` per key
that was live and then `account_retired`.

**The actor is `brain.actor_id` as the store sets it through `brain.tables.audit.attributed_to`**,
and a statement that set nothing is attributed to the database role and marked `actor: inferred`,
which is `0059`'s and `0137`'s arrangement. The rows carry `created_by` and no column for who
retired them, and adding one would be a second record of the same fact.

**No action list or subject grammar changes**: both exist since `0054`. **The downgrade drops the
two triggers and the function and keeps what the ledger holds.**

Task ids: M27.11.5
"""

from __future__ import annotations

from alembic import op

revision = "0148"
# The last car of migration train 2 before this one, which it was carried onto from #180.
down_revision = "0145"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

#: The slot family `brain.identity.service_account_store.SLOT_FAMILY` records an account under,
#: with its `/` written as `.`, as `brain.audit.record.credential_subject_id` rewrites it. Copied
#: for the reason `0009` gives about reading live code from a migration, and held equal by a test.
SUBJECT_PREFIX = "credential:service_accounts."

#: The two words, `brain.audit.record.CredentialChange`, held equal by a test.
KEY_REVOKED = "key_revoked"
ACCOUNT_RETIRED = "account_retired"

#: The word a trigger writes beside an actor nobody named, as `0059` and `0137` write it.
INFERRED = "inferred"

#: One key revoked or one account retired, by whoever the request named.
RETIREMENT_TRIGGER_FUNCTION = """
CREATE FUNCTION auth.record_service_account_retirement() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := '__SUBJECT_PREFIX__' || NEW.client_id;
    v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor text := COALESCE(v_supplied, session_user::text);
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF NOT (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL) THEN
        RETURN NULL;
    END IF;
    IF TG_TABLE_NAME = 'api_key' THEN
        v_details := jsonb_build_object('change', '__KEY_REVOKED__');
    ELSE
        v_details := jsonb_build_object('change', '__ACCOUNT_RETIRED__');
    END IF;
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', '__INFERRED__');
    END IF;

    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(
        NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32)
    );
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, v_actor, 'credential', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'credential', v_subject,
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
""".replace("__SUBJECT_PREFIX__", SUBJECT_PREFIX)
RETIREMENT_TRIGGER_FUNCTION = (
    RETIREMENT_TRIGGER_FUNCTION.replace("__KEY_REVOKED__", KEY_REVOKED)
    .replace("__ACCOUNT_RETIRED__", ACCOUNT_RETIRED)
    .replace("__INFERRED__", INFERRED)
)

#: The two triggers, one per table, over the one function.
TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER api_key_retirement_is_audited
        AFTER UPDATE ON auth.api_key
        FOR EACH ROW EXECUTE FUNCTION auth.record_service_account_retirement()
    """,
    """
    CREATE TRIGGER service_account_retirement_is_audited
        AFTER UPDATE ON auth.service_account
        FOR EACH ROW EXECUTE FUNCTION auth.record_service_account_retirement()
    """,
)


def upgrade() -> None:
    op.execute(RETIREMENT_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER service_account_retirement_is_audited ON auth.service_account")
    op.execute("DROP TRIGGER api_key_retirement_is_audited ON auth.api_key")
    op.execute("DROP FUNCTION auth.record_service_account_retirement()")
