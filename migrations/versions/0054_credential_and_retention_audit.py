"""Credential writes, retention releases and legal holds reach the ledger from the database.

Three writes that decide something nobody should be able to deny afterwards had no tamper-evident
record. `brain.ops.credentials.Credentials.keep` put a provider key into the vault from the console
and the setup wizard and left a log line. `brain.retention_routes` released the retention sweep to
delete, withdrew a release, placed a legal hold and lifted one, and left a row and nothing else.
This migration is the credential table, the three ledger members and three subject kinds they are
recorded under, and the three triggers that record them.

**Named for what it records rather than for its one table.** It was `0054_credential_write.py` for
an afternoon, until the retention writes were added to it rather than to a `0055`, and a reader
looking for where a legal hold reaches the ledger would not open a file named for credentials.

**Triggers rather than the application appending to `obs.audit_entry`.** Nothing in the application
appends to the ledger: every persisted entry is written by a trigger on a row the application
writes, `0003` for grants, `0047` for sign-in bindings, `0050` for session ends, `0052` for review
decisions and `0053` for exports, and `brain.app.suspension_store_for` says why no in-process writer
is built. So a row written by an operator's statement is recorded exactly as one the console
writes, and the chain still has one writer.

**A credential write: a table of its own, where no column could hold a value.** A slot, who wrote
it and when, never the value, its length, a prefix or a fingerprint, for the argument
`brain.tables.credential` makes; the two text columns are pinned by check constraints to a path and
an identifier. One row per write, never edited or retired: SELECT and INSERT only, for the reason
`0052` gives about a decision. The subject is the slot with its slashes written as dots,
`credential:providers.anthropic`, which `brain.audit.record.credential_subject_id` argues, and the
details are empty, because the value is the only other thing a write has.

**A release and a hold: the tables `0049` built, and a trigger on each.** Each fires on the insert
and on the one update that marks the row finished, a release's `withdrawn_at` or a hold's
`released_at` moving from nothing to an instant, and on nothing else; any other update appends
nothing. The actor is read off the row's own column for that change, `released_by`,
`withdrawn_by`, `placed_by` or the hold's `released_by`, so nothing is inferred and nothing is
marked unattributed. The subject is the object, `retention:<release id>` and `legal_hold:<hold id>`,
and the details are the change and nothing else: never the hold's subjects or actors, which are a
list of whose data is under hold. `brain.audit.ledger.AuditAction` argues the members and the kinds.

**A row inserted already finished records both of its changes, in order.** The application's
policies refuse one, `retention_release_made_live` and `legal_hold_placed_unlifted`, so only an
operator's statement can write it, and a ledger that recorded only the release of a release that
arrived withdrawn would say the sweep was free to delete when the table says it is not.

**What these triggers do not record, stated.** An update that moves a finished row back, a
withdrawal or a lift undone, is refused to the application role by `0049`'s update policies and
open to an operator; it appends nothing, because the row then names nobody for the change, and it
is the gap to close if an undone withdrawal is ever something an install needs to see. The entries
carry the request's trace and the writer's reach only where the application sets them in the
transaction, which `brain.retention_routes` does not today, so a retention entry's trace is the
transaction's own id and its reach the unsupplied sentinel.

**Two supersessions, and both are real.** The action list gains three members, replacing `0052`'s,
which is the one in the database. The subject grammar gains three kinds, replacing the one `0002`
wrote, which no migration had touched; `brain.tables.audit.SUBJECT_PATTERN` renders it from
`SUBJECT_KINDS`, so adding the kinds moved the model and this moves the database.

**The append is `0003`'s, and each trigger here is another copy of that block**, beside `0047`'s,
`0050`'s, `0052`'s and `0053`'s, for the reason `0047` gives against editing a function every grant
in production goes through. Same advisory lock, same sequence and parent read, same
`obs.audit_entry_hash`, same refusal of a discarded MERGE.

**The downgrade can fail, which is correct**, for the reason `0026` gives: narrowing the action list
and the subject grammar is refused once any entry carries the new values, and an audit entry cannot
be deleted to make room.

Task ids: none
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.credential_write",)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration.
#: `brain.tables.identity.PRINCIPAL_ID_CHARS`, `brain.audit.record.CREDENTIAL_SLOT_CHARS`,
#: `brain.audit.record.CREDENTIAL_SLOT` and `brain.audit.ledger.IDENTIFIER`.
PRINCIPAL_ID_CHARS = 128
SLOT_CHARS = 128
SLOT_GRAMMAR = r"^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)+$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"

#: Alphabetical, matching how `tables.identity.one_of` sorts.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'credential', "
    "'deny', 'entity_merge', 'grant', 'leash_change', 'legal_hold', 'publish', 'record_read', "
    "'retention', 'revoke', 'session_end', 'sign_in')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'deny', "
    "'entity_merge', 'grant', 'leash_change', 'publish', 'record_read', 'revoke', 'session_end', "
    "'sign_in')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0002`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|grant|leash|legal_hold|principal"
    "|retention|session):[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|entity|grant|leash|principal|session)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0052`'s action list and `0002`'s subject grammar, which are the
#: ones in the database.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.credential_write ENABLE ROW LEVEL SECURITY",
    # Every row, for the reason `0003` gives the tables with no `deleted_at`: a write is never
    # retired, so there is no live subset for a policy to narrow to. Nothing reads this table to
    # answer a person; the ledger entry is what the audit view shows, under its own capability.
    """
    CREATE POLICY credential_write_visible ON ops.credential_write
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.credential_write TO brain_app",)

#: The append every trigger below makes, as `0003`, `0047`, `0050`, `0052` and `0053` write it.
#: `{actor}`, `{action}`, `{subject}` and `{details}` are the four expressions that differ, so the
#: block is written once here and each function below is checked by a test against the recorder.
_APPEND = """
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
            v_seq, v_at, {actor}, '{action}', {subject}, v_ent_hash,
            v_trace, {details}, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, {actor}, '{action}', {subject},
                    v_ent_hash, v_trace, {details}, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
"""

_DECLARE = """
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

CREDENTIAL_WRITE_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_credential_write() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'credential:' || replace(NEW.slot, '/', '.');
    v_details jsonb := '{}'::jsonb;"""
    + _DECLARE
    + """BEGIN"""
    + _APPEND.format(
        actor="NEW.written_by", action="credential", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

#: A release, then its withdrawal, each with the actor its own column names. See the docstring for
#: why a row inserted already withdrawn records both.
RETENTION_RELEASE_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_retention_release() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'retention:' || NEW.id::text;
    v_changes text[] := ARRAY[]::text[];
    v_actors text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'released'::text;
        v_actors := v_actors || NEW.released_by::text;
        IF NEW.withdrawn_at IS NOT NULL THEN
            v_changes := v_changes || 'withdrawn'::text;
            v_actors := v_actors || NEW.withdrawn_by::text;
        END IF;
    ELSIF OLD.withdrawn_at IS NULL AND NEW.withdrawn_at IS NOT NULL THEN
        v_changes := v_changes || 'withdrawn'::text;
        v_actors := v_actors || NEW.withdrawn_by::text;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);"""
    + _APPEND.format(
        actor="v_actors[i]", action="retention", subject="v_subject", details="v_details"
    )
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

#: A hold placed, then lifted, each with the actor its own column names. Never its subjects or
#: actors lists.
LEGAL_HOLD_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION obs.record_legal_hold() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'legal_hold:' || NEW.id;
    v_changes text[] := ARRAY[]::text[];
    v_actors text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'placed'::text;
        v_actors := v_actors || NEW.placed_by::text;
        IF NEW.released_at IS NOT NULL THEN
            v_changes := v_changes || 'lifted'::text;
            v_actors := v_actors || NEW.released_by::text;
        END IF;
    ELSIF OLD.released_at IS NULL AND NEW.released_at IS NOT NULL THEN
        v_changes := v_changes || 'lifted'::text;
        v_actors := v_actors || NEW.released_by::text;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);"""
    + _APPEND.format(
        actor="v_actors[i]", action="legal_hold", subject="v_subject", details="v_details"
    )
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER credential_write_is_audited
        AFTER INSERT ON ops.credential_write
        FOR EACH ROW EXECUTE FUNCTION ops.record_credential_write()
    """,
    """
    CREATE TRIGGER retention_release_is_audited
        AFTER INSERT OR UPDATE ON ops.retention_release
        FOR EACH ROW EXECUTE FUNCTION ops.record_retention_release()
    """,
    """
    CREATE TRIGGER legal_hold_is_audited
        AFTER INSERT OR UPDATE ON obs.legal_hold
        FOR EACH ROW EXECUTE FUNCTION obs.record_legal_hold()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "credential_write",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slot", sa.String(SLOT_CHARS), nullable=False),
        sa.Column("written_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"slot ~ '{SLOT_GRAMMAR}'", name="slot_shape"),
        sa.CheckConstraint(f"written_by ~ '{IDENTIFIER}'", name="written_by_shape"),
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")
    op.execute(CREDENTIAL_WRITE_TRIGGER_FUNCTION)
    op.execute(RETENTION_RELEASE_TRIGGER_FUNCTION)
    op.execute(LEGAL_HOLD_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER legal_hold_is_audited ON obs.legal_hold")
    op.execute("DROP TRIGGER retention_release_is_audited ON ops.retention_release")
    op.execute("DROP TRIGGER credential_write_is_audited ON ops.credential_write")
    op.execute("DROP FUNCTION obs.record_legal_hold()")
    op.execute("DROP FUNCTION ops.record_retention_release()")
    op.execute("DROP FUNCTION ops.record_credential_write()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", NARROWER_ACTIONS, schema="obs")
    # The policies and the grants go with the table.
    op.drop_table("credential_write", schema="ops")
