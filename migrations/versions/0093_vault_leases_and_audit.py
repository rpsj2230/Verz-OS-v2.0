"""A connector run's lease is kept with its attempt, and the vault's audit log reaches the ledger.

Two changes to what the database keeps about the secrets vault, both schema only.

**`ops.connector_sync.lease`: how each attempt's vault lease ended.** Since this release the worker
reads a source's key through a run token minted for the attempt and revoked when it ends
(`brain.ops.connector_lease`). The attempt's row records one of four words, `none`, `revoked`,
`expired` or `not_revoked`, and the Secrets vault screen counts them per source. A column rather
than a table of its own, because a lease exists exactly as long as one attempt and the row that
describes the attempt is written when both have ended. Every row written before this migration held
no lease, so the default is `none` and the column is added with it, which rewrites nothing.

**`ops.vault_access`: every call the vault answered about a slot, and its ledger entry.** The worker
reads the vault's audit log (`brain.ops.vault_audit_ship`) and writes a row per response entry: the
vault's time, the operation, the part of the slot, the slot, whether it was refused, the HMAC of the
token's accessor as hex, and where in the log file the entry was. `brain.tables.vault_access` argues
the columns. The row's insert trigger appends a `vault_access` entry, filed under
`credential:<slot>` with the slashes written as dots, as `0054` files a credential write, so a
slot's writes and reads sit under one subject. Actor `secrets_vault`; details the operation, the
part, whether it was refused and the identity when there is one, as
`brain.audit.record.AuditRecorder.vault_access` writes them.

**SELECT and INSERT, and no UPDATE or DELETE**, for `0068`'s reason: nothing edits what the vault
said, the worker appends as the database's owner, and the application role is granted the append so
a worker configured with that role's login is not refused. **`USING (true)` on the read**: the only
reader is the Secrets vault screen, behind `admin:credential` over everything, which reads counts.

**Two supersessions.** The action list gains `vault_access`, replacing `0062`'s, which is the one in
the database. The control-run names gain `vault_audit_ship`, replacing `0068`'s.

**The append is `0003`'s, one more copy of the block `0054` carries**, for the reason `0047` gives
against editing a function every grant in production goes through.

**The downgrade** drops the trigger, its function and the table, which discards every shipped row
(the ledger keeps its entries), and drops the column. The action list and the control-run names go
back `NOT VALID`, for `0026`'s reason: an entry or a run already recorded stays.

Task ids: M31.3.2.4, M31.3.2.6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0093"
# The newest migration on origin/main when this was written, fa53822. Nothing after 0068 touches
# `ops.connector_sync` or the control-run names, and nothing after 0062 touches the action list.
down_revision = "0091"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.vault_access",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.connector_sync.LEASE_OUTCOMES`, `brain.tables.vault_access` and
#: `brain.audit.record.CREDENTIAL_SLOT` by tests.
LEASE_OUTCOMES = "lease IN ('expired', 'none', 'not_revoked', 'revoked')"
PARTS = "part IN ('config', 'lease', 'metadata', 'revoke', 'value')"
SLOT_CHARS = 128
SLOT_GRAMMAR = r"^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)+$"
OPERATION_PATTERN = r"^[a-z]{1,16}$"
HEX_DIGEST = r"^[0-9a-f]{64}$"

#: The actor every entry names: the vault, because the principal behind a token is not in its log.
VAULT_ACTOR = "secrets_vault"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.vault_access TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.vault_access ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY vault_access_readable ON ops.vault_access
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY vault_access_appendable ON ops.vault_access
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0062`'s.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', "
    "'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)

#: The control-run names, with and without `vault_audit_ship`. The second is `0068`'s.
WITH_VAULT_AUDIT_SHIP = (
    "name IN ('audit_anchor', 'automation_run', 'backup_exposure', 'canary_run', "
    "'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)
WITHOUT_VAULT_AUDIT_SHIP = (
    "name IN ('audit_anchor', 'automation_run', 'backup_exposure', 'canary_run', "
    "'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_token_renewal')"
)

#: What this migration replaces: `0062`'s action list and `0068`'s control-run names.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    WITHOUT_VAULT_AUDIT_SHIP: WITH_VAULT_AUDIT_SHIP,
}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0068` copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'ops.control_run'::regclass
           AND c.contype = 'c'
           AND right(c.conname, 16) = 'control_run_name'
    LOOP
        EXECUTE 'ALTER TABLE ops.control_run DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""

#: The append, as `0054` writes it, for one action and one actor.
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
            v_seq, v_at, v_actor, 'vault_access', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, 'vault_access', v_subject,
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

#: One ledger entry per shipped row. The details are the recorder's, key for key.
VAULT_ACCESS_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_vault_access() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'credential:' || replace(NEW.slot, '/', '.');
    v_actor text := '"""
    + VAULT_ACTOR
    + """';
    v_details jsonb := jsonb_build_object(
        'operation', NEW.operation,
        'part', NEW.part,
        'refused', CASE WHEN NEW.refused THEN 'true' ELSE 'false' END
    );
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF NEW.identity IS NOT NULL THEN
        v_details := v_details || jsonb_build_object('identity', NEW.identity);
    END IF;"""
    + _APPEND
    + """    RETURN NULL;
END;
$$
"""
)

TRIGGER = """
    CREATE TRIGGER vault_access_is_audited
        AFTER INSERT ON ops.vault_access
        FOR EACH ROW EXECUTE FUNCTION ops.record_vault_access()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # The check travels with the column it reads (alembic adds it right after, under the naming
    # convention): the previous release never names `lease`, so all it can write is the default.
    op.add_column(
        "connector_sync",
        sa.Column(
            "lease",
            sa.String(16),
            sa.CheckConstraint(LEASE_OUTCOMES, name="lease"),
            nullable=False,
            server_default="none",
        ),
        schema="ops",
    )

    op.create_table(
        "vault_access",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("part", sa.String(16), nullable=False),
        sa.Column("slot", sa.String(SLOT_CHARS), nullable=False),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.Column("identity", sa.String(64), nullable=True),
        sa.Column("log_identity", sa.String(64), nullable=False),
        sa.Column("log_offset", sa.BigInteger(), nullable=False),
        sa.Column(
            "shipped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"operation ~ '{OPERATION_PATTERN}'", name="operation_shape"),
        sa.CheckConstraint(PARTS, name="part"),
        sa.CheckConstraint(f"slot ~ '{SLOT_GRAMMAR}'", name="slot_shape"),
        sa.CheckConstraint(f"identity IS NULL OR identity ~ '{HEX_DIGEST}'", name="identity_shape"),
        sa.CheckConstraint(f"log_identity ~ '{HEX_DIGEST}'", name="log_identity_shape"),
        sa.CheckConstraint("log_offset > 0", name="log_offset_positive"),
        sa.UniqueConstraint("log_identity", "log_offset"),
        schema="ops",
    )
    op.create_index("ix_vault_access_shipped_at", "vault_access", ["shipped_at"], schema="ops")
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    op.execute(VAULT_ACCESS_TRIGGER_FUNCTION)
    op.execute(TRIGGER)

    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_VAULT_AUDIT_SHIP, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_VAULT_AUDIT_SHIP,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
    op.execute("DROP TRIGGER vault_access_is_audited ON ops.vault_access")
    op.execute("DROP FUNCTION ops.record_vault_access()")
    # The index, the policies and the grants go with the table.
    op.drop_table("vault_access", schema="ops")
    # The column's check goes with it.
    op.drop_column("connector_sync", "lease", schema="ops")
