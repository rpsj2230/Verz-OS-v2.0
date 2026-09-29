"""A connection keeps the declaration it agreed to, and its ledger entries name the digest.

A shipped connector's declaration can change between releases, and a connection agreed under the
old one stops being read until a person with the installation authority accepts the new one
(`brain.connectors.registry`: upgrade is deliberate, reconnect never clears it). The Connectors
screen showed a "Declaration changed" pill and nothing about what had changed, because the row
kept only the digest, and a digest is a number nobody can read back. So the person accepted a
change they were never shown.

**`ops.connector_connection.agreed` keeps the declaration's canonical text**, exactly what
`brain.connectors.manifest.digest_input` returns and the digest is the SHA-256 of, written with
every new row. Kept as text rather than JSONB, so the check that it is the declaration the digest
names is the hash itself and nothing is reordered on the way in. Nullable: a row written before
this revision agreed to something nobody recorded, and the screen says so rather than guessing.
Bounded, as every text column here is, at far more than any declaration's size.

**Each ledger entry the connection's trigger appends now carries the row's digest**, beside the
change: accepting a changed declaration disconnects the old row and connects a new one in one
transaction, so the two entries name the digest agreed before and the one agreed now, under one
trace. The function is replaced, not the trigger.

**The downgrade** puts `0057`'s function back and drops the column. Entries already appended keep
their digest: the ledger is not rewritten.

Revises `0150`, the head of main when this was written; the number is provisional until the
integrator allocates it.

Task ids: M27.11.9, M33.5.1.1

Revision ID: 0157
Revises: 0150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0157"
down_revision = "0150"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. No new table.
TABLES: tuple[str, ...] = ()

#: The longest declaration text kept. A declaration is a few kilobytes; this is a sanity bound.
AGREED_MAX_CHARS = 262144

AGREED_CHECK = ("agreed_is_bounded", f"agreed IS NULL OR length(agreed) <= {AGREED_MAX_CHARS}")

#: `0057`'s function with the row's digest added to every entry's details.
CONNECTOR_CONNECTION_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION ops.record_connector_connection() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'connector:' || NEW.connector;
    v_changes text[] := ARRAY[]::text[];
    v_actors text[] := ARRAY[]::text[];
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'connected'::text;
        v_actors := v_actors || NEW.connected_by::text;
        IF NEW.disconnected_at IS NOT NULL THEN
            v_changes := v_changes || 'disconnected'::text;
            v_actors := v_actors || NEW.disconnected_by::text;
        END IF;
    ELSIF OLD.disconnected_at IS NULL AND NEW.disconnected_at IS NOT NULL THEN
        v_changes := v_changes || 'disconnected'::text;
        v_actors := v_actors || NEW.disconnected_by::text;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i], 'digest', NEW.digest);
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
            v_seq, v_at, v_actors[i], 'connector', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actors[i], 'connector', v_subject,
                    v_ent_hash, v_trace, v_details, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$
"""

#: `0057`'s function, which the downgrade puts back.
PREVIOUS_CONNECTOR_CONNECTION_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION ops.record_connector_connection() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'connector:' || NEW.connector;
    v_changes text[] := ARRAY[]::text[];
    v_actors text[] := ARRAY[]::text[];
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'connected'::text;
        v_actors := v_actors || NEW.connected_by::text;
        IF NEW.disconnected_at IS NOT NULL THEN
            v_changes := v_changes || 'disconnected'::text;
            v_actors := v_actors || NEW.disconnected_by::text;
        END IF;
    ELSIF OLD.disconnected_at IS NULL AND NEW.disconnected_at IS NOT NULL THEN
        v_changes := v_changes || 'disconnected'::text;
        v_actors := v_actors || NEW.disconnected_by::text;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);
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
            v_seq, v_at, v_actors[i], 'connector', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actors[i], 'connector', v_subject,
                    v_ent_hash, v_trace, v_details, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$
"""


def upgrade() -> None:
    # The check travels with the column it reads, as `0121`'s do.
    op.add_column(
        "connector_connection",
        sa.Column(
            "agreed",
            sa.Text(),
            sa.CheckConstraint(AGREED_CHECK[1], name=AGREED_CHECK[0]),
            nullable=True,
        ),
        schema="ops",
    )
    op.execute(CONNECTOR_CONNECTION_TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(PREVIOUS_CONNECTOR_CONNECTION_TRIGGER_FUNCTION)
    op.drop_column("connector_connection", "agreed", schema="ops")
