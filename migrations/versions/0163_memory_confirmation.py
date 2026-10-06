"""An inference a person says again is confirmed on its own row, and the ledger says when.

M16.7.2 is that a memory which is used and confirmed again regains its confidence, and one that is
not falls below the retrieval floor on the configured schedule while its audit record stays. An
inferred memory decays from the moment it formed (`brain.memory.formation.confidence_now`), and
nothing could move that moment: `0018` gives `mem.adaptive` SELECT and INSERT and nothing else, so
a person saying the same preference a month later was skipped as already remembered and the
memory went on fading as if they never had.

**One column, stamped by the database, and one column's UPDATE.** `last_confirmed_at` is when the
person last said it again, and decay runs from it when it is set. The application may update that
column and no other (`GRANT UPDATE (last_confirmed_at)`), so a confirmation cannot rewrite what a
memory says, whom it is about or what it was formed with. The policy admits the update only in
the name of the person the memory is about, read from `app.principal_id` as `0154`'s marks are
written, and only stamped `statement_timestamp()`, so a confirmation cannot be back- or
forward-dated.

**The history is the ledger's, one entry per confirmation.** A trigger on the column appends a
`memory` entry under `memory:<id>` with `{"change": "confirmed"}`, the actor being the person the
row is about, in the transaction that confirmed it; `0061`'s correction entries are the same action
with the other two changes. So the row holds the latest confirmation and the ledger holds every one,
and neither is ever deleted: a memory that falls below the floor is still there, with its entries.

**A stated memory is not given the column.** It does not decay (`DECAYS_WITH_TIME`), so a
confirmation would change nothing it is read by, and a column that means nothing is a column
somebody eventually reads as meaning something.

Revises `0178`, the skill script digest migration (#357), in the order the migration queue
lands; `0154`, the marks and learning pause migration (#246), is earlier in the chain.

Task ids: M16.7.2

Revision ID: 0163
Revises: 0178
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0163"
down_revision = "0178"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"
SCHEMA = "mem"
TABLE = "adaptive"
COLUMN = "last_confirmed_at"

#: `0018`'s CREATE TABLE as it reads once this column is added, for the model comparison.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "formed_confidence FLOAT NOT NULL, CONSTRAINT pk_adaptive PRIMARY KEY (id),": (
        "formed_confidence FLOAT NOT NULL, last_confirmed_at TIMESTAMP WITH TIME ZONE, "
        "CONSTRAINT pk_adaptive PRIMARY KEY (id),"
    ),
}

#: The one column the application may update, and nothing else about the row.
GRANTS: tuple[str, ...] = ("GRANT UPDATE (last_confirmed_at) ON mem.adaptive TO brain_app",)

#: In the name of the person the memory is about, stamped by the statement that confirms it.
POLICIES: tuple[str, ...] = (
    """
    CREATE POLICY adaptive_confirmed_by_its_person ON mem.adaptive
        FOR UPDATE TO brain_app
        USING (principal_id = current_setting('app.principal_id', true))
        WITH CHECK (
            principal_id = current_setting('app.principal_id', true)
            AND last_confirmed_at = statement_timestamp()
        )
    """,
)

#: A confirmation, with the person the memory is about as the actor.
CONFIRMATION_TRIGGER_FUNCTION = """
CREATE FUNCTION mem.record_confirmation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'memory:' || NEW.id;
    v_details jsonb := jsonb_build_object('change', 'confirmed');
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    -- The append, as 0003's gate.record_entitlement_change and every trigger since write it.
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
        v_seq, v_at, NEW.principal_id, 'memory', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.principal_id, 'memory', v_subject,
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

CONFIRMATION_TRIGGER = """
CREATE TRIGGER confirmation_is_audited
    AFTER UPDATE OF last_confirmed_at ON mem.adaptive
    FOR EACH ROW
    WHEN (NEW.last_confirmed_at IS DISTINCT FROM OLD.last_confirmed_at)
    EXECUTE FUNCTION mem.record_confirmation()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in (*GRANTS, *POLICIES))
    assert all("DELETE" not in statement for statement in GRANTS)
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    for statement in (*GRANTS, *POLICIES):
        op.execute(statement)
    op.execute(CONFIRMATION_TRIGGER_FUNCTION)
    op.execute(CONFIRMATION_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER confirmation_is_audited ON mem.adaptive")
    op.execute("DROP FUNCTION mem.record_confirmation()")
    op.execute("DROP POLICY adaptive_confirmed_by_its_person ON mem.adaptive")
    op.execute("REVOKE UPDATE (last_confirmed_at) ON mem.adaptive FROM brain_app")
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
