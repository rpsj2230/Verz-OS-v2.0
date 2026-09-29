"""A person moved to another department is on the ledger, under whoever moved them.

The owner decided on 2026-09-29 (needs-rupash 115, item 2) that an install may manage departments on
People, several people moved at once (`brain.directory_routes.move_people`). Until then nothing but
a statement typed by hand ever changed `auth.principal.primary_department`: the staff source set it
when somebody was made, and no screen moved anybody. So nothing recorded a move, and a department
decides who governs a person, which is not a change to make unseen.

**A trigger rather than the route writing the entry**, as every other change to where somebody sits
is recorded (`0062`'s placements, `0086`'s structure): an entry the route wrote would miss a move
made any other way, and a trigger is in the writing transaction, so the move and its entry commit
together or neither does. The entry is `organisation` with `{"change": "moved", "department":
<the new slug>}` under the person's own subject, the shape
`brain.audit.record.AuditRecorder.organisation` writes for `OrganisationChange.MOVED`. A slug, never
a name: a department's name is whatever somebody typed.

**Only a move to a department is recorded.** A move to no department is not something any screen
makes, and an entry naming no department would be one the recorder refuses; a statement typed by
hand that clears the column is the one change left unrecorded, as it is for every column no screen
writes.

**The append is `0141`'s**, copied rather than imported for `0009`'s reason about reading live code
from a migration: under the ledger's advisory lock, chained to the previous entry, refusing loudly
if the sequence was taken. An update with nobody named as the actor is recorded as `unattributed`.

**The downgrade** drops the trigger and its function; moves already recorded stay recorded.

Task ids: M1.6.20

Revision ID: 0170
Revises: 0156
"""

from __future__ import annotations

from alembic import op

revision = "0170"
down_revision = "0156"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

UNATTRIBUTED = "unattributed"

_APPEND_DECLARE = """
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

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
            v_seq, v_at, v_actor, 'organisation', 'principal:' || NEW.id, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, 'organisation', 'principal:' || NEW.id,
                    v_ent_hash, v_trace, v_details, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
"""

MOVE_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION auth.record_principal_moved() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text := NULLIF(current_setting('brain.actor_id', true), '');
    v_details jsonb;"""
    + _APPEND_DECLARE
    + """BEGIN
    IF NEW.primary_department IS NULL
       OR OLD.primary_department IS NOT DISTINCT FROM NEW.primary_department THEN
        RETURN NULL;
    END IF;
    v_details := jsonb_build_object('change', 'moved', 'department', NEW.primary_department);
    IF v_actor IS NULL THEN
        v_actor := '"""
    + UNATTRIBUTED
    + """';
        v_details := v_details || jsonb_build_object('actor', '"""
    + UNATTRIBUTED
    + """');
    END IF;"""
    + _APPEND
    + """    RETURN NULL;
END;
$$
"""
)

MOVE_TRIGGER = """
CREATE TRIGGER principal_move_is_audited
    AFTER UPDATE OF primary_department ON auth.principal
    FOR EACH ROW EXECUTE FUNCTION auth.record_principal_moved()
"""


def upgrade() -> None:
    op.execute(MOVE_TRIGGER_FUNCTION)
    op.execute(MOVE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER principal_move_is_audited ON auth.principal")
    op.execute("DROP FUNCTION auth.record_principal_moved()")
