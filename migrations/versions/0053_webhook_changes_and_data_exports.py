"""Two console writes get the record they need: who changed a webhook subscriber, and every export.

The Webhooks screen registers a subscriber, replaces its signing secret and switches it off, and
the Import and export screen takes an export of the audit trail. Neither had anywhere to record
that it happened. `brain.tables.webhook_change` and `brain.tables.data_export` hold the argument
for each shape; what is here is the DDL, the policies and the one trigger.

**Both tables take SELECT and INSERT and nothing else.** A change to a subscriber and an export
taken are facts about a moment, and a row that could be edited would be a record whose author or
whose window moved after the fact. PostgreSQL denies what no grant admits, so the absent UPDATE and
DELETE grants are the refusal. `USING (true)` on the policy is not an absence of a permission check,
for the reason `0030` gives about the subscriber table: who may read either is a console question
decided against the reader's live grants, by `brain.ops.outbox.may_manage` for the first and by
`brain.ops.data_transfer` for the second.

**An export reaches the audit ledger from the database, as a publish.** An export is an artefact
leaving the system and `publish` is the member that records one, so the action list is not widened.
The subject is `artifact:<export_id>`, the actor the row's own `requested_by`, and the details the
data set under `fields`, which is the shape `brain.audit.record.AuditRecorder.publish` writes. A
trigger for the reason `0047`, `0050` and `0052` give: an export inserted by an operator's statement
is recorded as well as one taken from the console. The digest of the reach and the request's trace
come from the settings the application sets in the same transaction.

**A webhook change does not reach the ledger, and that is stated rather than hidden.** No member
of `brain.audit.ledger.AuditAction` records a change to where the company's identifiers are sent,
and no subject kind fits a subscriber id. Adding both is the audit package's decision; when it is
made, a trigger on `ops.webhook_change` is the whole of the wiring.

**The append is `0003`'s, and this is a fifth copy of that block**, beside `0047`'s, `0050`'s and
`0052`'s, for the reason `0047` gives against editing a function every grant in production goes
through. Same advisory lock, same sequence and parent read, same `obs.audit_entry_hash`, same
refusal of a discarded MERGE.

**The downgrade drops both**, the trigger first. It discards the record of every export taken,
which is the state before this migration existed, and it is said here because a downgrade on a live
install is the moment somebody would want to know.

Task ids: none
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.webhook_change", "ops.data_export")

APP_ROLE = "brain_app"

#: Widths copied for the reason `0009` gives about reading live code from a migration.
#: `brain.ops.outbox.MAX_IDENTIFIER_CHARS` and `brain.tables.identity.PRINCIPAL_ID_CHARS`.
IDENTIFIER_CHARS = 128
PRINCIPAL_ID_CHARS = 128

#: `brain.tables.webhook_change.WebhookChange`, sorted as `one_of` sorts.
CHANGE_IN = "change IN ('registered', 'secret_replaced', 'switched_off')"

#: `brain.tables.data_export.ExportDataSet` and `brain.ops.export.ExportReason`, sorted.
DATA_SET_IN = "data_set IN ('audit_trail')"
REASON_IN = (
    "reason IN ('internal_investigation', 'legal_discovery', 'litigation_hold_collection', "
    "'regulatory_request', 'subject_access_request', 'system_migration')"
)

#: `brain.tables.data_export.REFERENCE_PATTERN` and `DIGEST_PATTERN`.
REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_./#-]{0,63}$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.webhook_change ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY webhook_change_visible ON ops.webhook_change
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.data_export ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY data_export_visible ON ops.data_export
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: SELECT and INSERT on both, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.webhook_change TO brain_app",
    "GRANT SELECT, INSERT ON ops.data_export TO brain_app",
)

DATA_EXPORT_TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_data_export() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_details jsonb := jsonb_build_object('fields', NEW.data_set);
    v_subject text := 'artifact:' || NEW.export_id::text;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    -- The append, as 0003's gate.record_entitlement_change, 0047's
    -- auth.record_sign_in_change, 0050's auth.record_session_end and 0052's
    -- gate.record_review_decision write it.
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
        v_seq, v_at, NEW.requested_by, 'publish', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.requested_by, 'publish', v_subject,
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

DATA_EXPORT_TRIGGER = """
CREATE TRIGGER data_export_is_audited
    AFTER INSERT ON ops.data_export
    FOR EACH ROW EXECUTE FUNCTION ops.record_data_export()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "webhook_change",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "subscriber_id",
            sa.String(IDENTIFIER_CHARS),
            sa.ForeignKey("ops.webhook_subscriber.subscriber_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("change", sa.String(16), nullable=False),
        sa.Column("changed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("secret_written_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(CHANGE_IN, name="change"),
        sa.CheckConstraint("length(btrim(changed_by)) > 0", name="changed_by_present"),
        sa.CheckConstraint(
            "change <> 'switched_off' OR secret_written_at IS NULL",
            name="a_switch_off_writes_no_secret",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_ops_webhook_change_subscriber",
        "webhook_change",
        ["subscriber_id", "changed_at"],
        schema="ops",
    )
    op.create_table(
        "data_export",
        sa.Column(
            "export_id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("data_set", sa.String(32), nullable=False),
        sa.Column("requested_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("reason_reference", sa.String(64), nullable=False),
        sa.Column(
            "produced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("first_seq", sa.BigInteger(), nullable=True),
        sa.Column("last_seq", sa.BigInteger(), nullable=True),
        sa.Column("entries", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("document_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(DATA_SET_IN, name="data_set"),
        sa.CheckConstraint(REASON_IN, name="reason"),
        sa.CheckConstraint("length(btrim(requested_by)) > 0", name="requested_by_present"),
        sa.CheckConstraint(
            f"reason_reference ~ '{REFERENCE_PATTERN}'", name="reference_is_a_token"
        ),
        sa.CheckConstraint(f"document_digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint("entries >= 0", name="entries_not_negative"),
        sa.CheckConstraint(
            "(first_seq IS NULL) = (last_seq IS NULL) AND (first_seq IS NULL) = (entries = 0)",
            name="a_window_names_both_ends_or_neither",
        ),
        sa.CheckConstraint(
            "first_seq IS NULL OR last_seq - first_seq + 1 = entries",
            name="the_window_is_contiguous",
        ),
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(DATA_EXPORT_TRIGGER_FUNCTION)
    op.execute(DATA_EXPORT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER data_export_is_audited ON ops.data_export")
    op.execute("DROP FUNCTION ops.record_data_export()")
    # The policies and the grants go with the tables.
    op.drop_table("data_export", schema="ops")
    op.drop_index("ix_ops_webhook_change_subscriber", "webhook_change", schema="ops")
    op.drop_table("webhook_change", schema="ops")
