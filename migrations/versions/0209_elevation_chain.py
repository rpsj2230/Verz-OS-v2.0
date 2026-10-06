"""An approved elevation is also an entry in a second chain of its own, anchored on its own.

`brain.console.elevation` decided what a separate chain is for, in
`A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER`: nothing about an entry is harder to
edit for sitting in its own run, and the one thing separation buys is a head that moves only when
somebody is elevated, so its own anchor shows a truncation of those few entries without depending
on the whole ledger being anchored often enough. It wrote `ELEVATION_CHAIN`,
`elevation_recorder` and `chain_findings`, and nothing on an install ever wrote to a second chain.

**`obs.elevation_entry` is `obs.audit_entry` again, with one action.** The same columns, the same
digest function (`0003`'s `obs.audit_entry_hash`), the same refusal of a fork or a repeated digest,
and the same statement triggers refusing UPDATE, DELETE and TRUNCATE. The action is `break_glass`
alone and the subject a session, so nothing but a break-glass session can be written into it.

**`0104`'s entry is written to both chains, in one transaction.** `0104`'s
`gate.record_break_glass` appends a `break_glass` entry for the session an approval opens to the
main ledger, which is what the Audit screen and the audit export read, and it is left exactly as it
is, so nothing an auditor could see before is gone. A second trigger on `gate.elevation_request`
appends the same entry, from the same expressions, to `obs.elevation_entry` under its own advisory
lock, so the second chain cannot fork between two approvals. "Separate" here means its own chain,
head and anchor; the main ledger still holds the same entry. The two copies are held to each other
by `brain.console.elevation.chain_findings`, which reports an entry in either chain without its
twin in the other, or a twin that says something different
(`A_BREAK_GLASS_ENTRY_IS_IN_BOTH_CHAINS_AND_EACH_HAS_ITS_TWIN`). Rejected: moving the entry out of
the main chain, which would take break-glass sessions off the Audit screen until that screen reads
two chains as one timeline, and a pointer entry in the main chain, which needs a ledger action the
vocabulary does not have.

**The downgrade drops the second trigger, its function and the table.** The main ledger still holds
every session entry, because `0104` wrote it there all along; an install downgraded past this
loses the separate head and anchor and nothing else.

Task ids: M33.7.1.3

Revision ID: 0209
Revises: 0208
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0209"
down_revision = "0208"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing.
TABLES: tuple[str, ...] = ("obs.elevation_entry",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.audit.ledger` and `brain.tables.audit` by
#: `tests/unit/test_elevation_chain.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
SUBJECT = r"^session:[A-Za-z0-9_.@-]{1,128}$"
ENT_HASH = r"^[0-9a-f]{32}$"
TRACE_ID = r"^[A-Za-z0-9_.-]{1,64}$"
DIGEST = r"^[0-9a-f]{64}$"
ACTIONS = "action IN ('break_glass')"
ACTION = "break_glass"
APPROVED = "approved"

#: The lock every append to this chain takes. Its own number, so an elevation never waits on the
#: main ledger's lock and the two chains cannot deadlock each other.
ELEVATION_LOCK = 8274419209

RLS: tuple[str, ...] = (
    "ALTER TABLE obs.elevation_entry ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY elevation_entry_readable ON obs.elevation_entry
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY elevation_entry_appendable ON obs.elevation_entry
        FOR INSERT TO brain_app
        WITH CHECK ({ACTIONS})
    """,
)

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON obs.elevation_entry TO brain_app",)

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION obs.elevation_entry_is_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'obs.elevation_entry is append-only; ' || tg_op || ' is refused',
        ERRCODE = 'restrict_violation',
        HINT = 'a wrong entry is corrected by appending another, never by editing it';
END;
$$
"""

APPEND_ONLY_TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER elevation_entry_refuses_amendment
        BEFORE UPDATE ON obs.elevation_entry
        FOR EACH STATEMENT EXECUTE FUNCTION obs.elevation_entry_is_append_only()
    """,
    """
    CREATE TRIGGER elevation_entry_refuses_removal
        BEFORE DELETE ON obs.elevation_entry
        FOR EACH STATEMENT EXECUTE FUNCTION obs.elevation_entry_is_append_only()
    """,
    """
    CREATE TRIGGER elevation_entry_refuses_truncation
        BEFORE TRUNCATE ON obs.elevation_entry
        FOR EACH STATEMENT EXECUTE FUNCTION obs.elevation_entry_is_append_only()
    """,
)

#: `0104`'s `gate.record_break_glass` entry again, appended to the elevation chain as well.
CHAIN_FUNCTION = f"""
CREATE FUNCTION gate.record_elevation_chain() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF NEW.decision IS DISTINCT FROM '{APPROVED}' THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.decision IS NOT DISTINCT FROM '{APPROVED}' THEN
        RETURN NULL;
    END IF;
    v_subject := 'session:' || NEW.id::text;
    v_details := jsonb_build_object(
        'reason', NEW.reason,
        'principal', NEW.principal_id,
        'authorised_by', NEW.decided_by
    );

    PERFORM pg_advisory_xact_lock({ELEVATION_LOCK});
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.elevation_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.elevation_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, NEW.decided_by, '{ACTION}', v_subject, v_ent_hash, v_trace, v_details, v_prev
    );

    INSERT INTO obs.elevation_entry (seq, at, actor_id, action, subject, ent_hash, trace_id,
                                     details, prev_hash, entry_hash)
    VALUES (v_seq, v_at, NEW.decided_by, '{ACTION}', v_subject, v_ent_hash, v_trace,
            v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the elevation chain was not appended at seq ' || v_seq,
            ERRCODE = 'restrict_violation',
            HINT = 'an approval whose elevation entry is discarded silently is refused';
    END IF;
    RETURN NULL;
END;
$$
"""


#: `0104`'s own trigger condition, `AFTER INSERT OR UPDATE OF decision`, so the two copies fire on
#: exactly the same statements.
CHAIN_TRIGGER = """
CREATE TRIGGER elevation_request_is_chained
    AFTER INSERT OR UPDATE OF decision ON gate.elevation_request
    FOR EACH ROW EXECUTE FUNCTION gate.record_elevation_chain()
"""

#: The control-run names, with and without `elevation_anchor`. The second is `0201`'s. The anchor
#: control is read by the anchor workflow on a route, and the run it reports is recorded here.
WITH_ELEVATION_ANCHOR = (
    "name IN ('acceptance_run', 'approved_actions', 'audit_anchor', 'automation_run', "
    "'backup_exposure', 'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', "
    "'elevation_anchor', 'entity_resolution', 'erasure_queue', 'escalation_expiry', "
    "'evening_digest', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh', 'vault_audit_ship', "
    "'vault_token_renewal')"
)
WITHOUT_ELEVATION_ANCHOR = (
    "name IN ('acceptance_run', 'approved_actions', 'audit_anchor', 'automation_run', "
    "'backup_exposure', 'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', "
    "'entity_resolution', 'erasure_queue', 'escalation_expiry', 'evening_digest', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)

#: What this migration replaces: `0201`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_ELEVATION_ANCHOR: WITH_ELEVATION_ANCHOR}

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
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "elevation_entry",
        sa.Column("seq", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("ent_hash", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("details", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.CheckConstraint("seq >= 0", name="seq_non_negative"),
        sa.CheckConstraint(f"actor_id ~ '{IDENTIFIER}'", name="actor_id_shape"),
        sa.CheckConstraint(ACTIONS, name="action"),
        sa.CheckConstraint(f"subject ~ '{SUBJECT}'", name="subject_grammar"),
        sa.CheckConstraint(f"ent_hash ~ '{ENT_HASH}'", name="ent_hash_shape"),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        sa.CheckConstraint(f"prev_hash ~ '{DIGEST}'", name="prev_hash_shape"),
        sa.CheckConstraint(f"entry_hash ~ '{DIGEST}'", name="entry_hash_shape"),
        sa.CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object"),
        sa.CheckConstraint("entry_hash <> prev_hash", name="not_its_own_parent"),
        schema="obs",
    )
    op.create_index(
        "uq_elevation_entry_entry_hash",
        "elevation_entry",
        ["entry_hash"],
        unique=True,
        schema="obs",
    )
    op.create_index(
        "uq_elevation_entry_prev_hash", "elevation_entry", ["prev_hash"], unique=True, schema="obs"
    )
    for statement in RLS + GRANTS:
        op.execute(statement)
    op.execute(APPEND_ONLY_FUNCTION)
    for statement in APPEND_ONLY_TRIGGERS:
        op.execute(statement)
    op.execute(CHAIN_FUNCTION)
    op.execute(CHAIN_TRIGGER)
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_ELEVATION_ANCHOR, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_ELEVATION_ANCHOR,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.execute("DROP TRIGGER IF EXISTS elevation_request_is_chained ON gate.elevation_request")
    op.execute("DROP FUNCTION IF EXISTS gate.record_elevation_chain()")
    op.execute("DROP TABLE IF EXISTS obs.elevation_entry")
    op.execute("DROP FUNCTION IF EXISTS obs.elevation_entry_is_append_only()")
