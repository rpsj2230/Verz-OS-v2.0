"""A source connected from the console gets a row, and connecting or disconnecting one is audited.

`brain.ops.connector_admin` connects a source from the Connectors screen and disconnects one, and
`brain.tables.connector_connection` argues the shape of the record. What is here is the table, its
policies, its grants, the ledger member it is recorded under and the trigger that records it.

**Read by the application, added to, and marked disconnected once.** SELECT and INSERT, and UPDATE
on the two disconnection columns alone, so the settings, the pinned digest and who connected a
source can never be edited after the fact. The insert policy admits only a row that is connected,
and the update policy only a connected row that becomes disconnected, which are
`0049`'s two policies for a release and a hold applied to one more object: a disconnection cannot
be undone by the application, and a source connected again is a new row. No DELETE. `USING (true)`
on the read is not an absence of a permission check, for the reason `0030` gives: who may be told
a source is connected is `brain.console.connector_trust`'s question, asked against the reader's own
grants, and the route asks it before anything is shown.

**One live connection per source**, as a partial unique index, beside the store's own lock. The lock
is what stops two administrators writing two keys into one slot; the index is what stops a
statement written by hand leaving two rows that both say a source is connected.

**The ledger gains a member, `connector`**, which `brain.audit.ledger.AuditAction` argues. The
action list is superseded again, replacing `0056`'s, which is the one in the database. The subject
kind `connector` has been in the grammar since `0002`, so the grammar is not touched.

**The trigger fires on the insert and on the one update that marks a row disconnected**, and on
nothing else, with the actor read off the row's own column for that change, as `0054`'s triggers
read theirs. A row inserted already disconnected, which only an operator's statement can write,
records both changes in order, for `0054`'s reason. The details are the change alone: never the
settings, which are the row's, and never anything of the key, which is recorded when it is written
under `credential` by `0054`'s trigger on `ops.credential_write`.

**The append is `0003`'s, and this is one more copy of that block**, beside `0047`'s, `0050`'s,
`0052`'s, `0053`'s, `0054`'s, `0055`'s and `0056`'s, for the reason `0047` gives against editing a function
every grant in production goes through. Same advisory lock, same sequence and parent read, same
`obs.audit_entry_hash`, same refusal of a discarded MERGE.

**The downgrade keeps what the ledger already holds**, for `0026`'s reason: the action list goes
back `NOT VALID`, so an entry already recording a connection stays and no new one is accepted. It
drops the table with it, and with the table the record of every source connected, which is the
state before this migration.

Task ids: M42.6.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.connector_connection",)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.connector_connection`, `brain.ops.credentials.
#: CONNECTOR_NAME_PATTERN`, `brain.connectors.manifest.DIGEST_CHARS`, `brain.audit.ledger.
#: IDENTIFIER` and `brain.tables.identity.PRINCIPAL_ID_CHARS` by
#: `tests/unit/test_connector_store.py`.
CONNECTOR_CHARS = 64
CONNECTOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
DIGEST_CHARS = 64
DIGEST_PATTERN = r"^[0-9a-f]{64}$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0056`'s.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'grant', 'leash_change', 'legal_hold', 'publish', "
    "'record_read', 'retention', 'revoke', 'session_end', 'sign_in', 'skill')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'credential', "
    "'deny', 'entity_merge', 'grant', 'leash_change', 'legal_hold', 'publish', 'record_read', "
    "'retention', 'revoke', 'session_end', 'sign_in', 'skill')"
)

#: What this migration replaces: `0056`'s action list, which is the one in the database.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.connector_connection ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY connector_connection_readable ON ops.connector_connection
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY connector_connection_connected ON ops.connector_connection
        FOR INSERT TO brain_app
        WITH CHECK (disconnected_at IS NULL AND disconnected_by IS NULL)
    """,
    """
    CREATE POLICY connector_connection_disconnected_once ON ops.connector_connection
        FOR UPDATE TO brain_app
        USING (disconnected_at IS NULL)
        WITH CHECK (disconnected_at IS NOT NULL)
    """,
)

#: SELECT and INSERT, UPDATE on the two disconnection columns, and never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.connector_connection TO brain_app",
    "GRANT UPDATE (disconnected_at, disconnected_by) ON ops.connector_connection TO brain_app",
)

#: A connection, then its disconnection, each with the actor its own column names.
CONNECTOR_CONNECTION_TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_connector_connection() RETURNS trigger
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

CONNECTOR_CONNECTION_TRIGGER = """
CREATE TRIGGER connector_connection_is_audited
    AFTER INSERT OR UPDATE ON ops.connector_connection
    FOR EACH ROW EXECUTE FUNCTION ops.record_connector_connection()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "connector_connection",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("connector", sa.String(CONNECTOR_CHARS), nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("connected_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("disconnected_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        sa.CheckConstraint("jsonb_typeof(settings) = 'object'", name="settings_are_an_object"),
        sa.CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint(f"connected_by ~ '{IDENTIFIER}'", name="connected_by_shape"),
        sa.CheckConstraint(
            f"disconnected_by IS NULL OR disconnected_by ~ '{IDENTIFIER}'",
            name="disconnected_by_shape",
        ),
        sa.CheckConstraint(
            "(disconnected_at IS NULL) = (disconnected_by IS NULL)",
            name="a_disconnection_names_who_and_when",
        ),
        schema="ops",
    )
    op.create_index(
        "uq_connector_connection_connector_live",
        "connector_connection",
        ["connector"],
        unique=True,
        schema="ops",
        postgresql_where=sa.text("disconnected_at IS NULL"),
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(CONNECTOR_CONNECTION_TRIGGER_FUNCTION)
    op.execute(CONNECTOR_CONNECTION_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER connector_connection_is_audited ON ops.connector_connection")
    op.execute("DROP FUNCTION ops.record_connector_connection()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
    # The policies and the grants go with the table.
    op.drop_index("uq_connector_connection_connector_live", "connector_connection", schema="ops")
    op.drop_table("connector_connection", schema="ops")
