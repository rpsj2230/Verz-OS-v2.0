"""A connected source names its steward, and every grant somebody makes to themselves is recorded.

M7.7.2 asks that every knowledge document, connected source and agent names a steward, set and
changed in the console, and that the steward is the person told when anybody grants themselves
access to that object. A document has had its steward since `0120` (`know.item.owner_id` and the
hand-over route) and an agent since `0014` (its owner and the transfer route). A connected source
had nobody, and nothing recorded a grant somebody made to themselves in a form a steward could be
told of. This migration is those two.

**`ops.connector_steward` is the history of who stewards each source, one row per naming, never
edited.** `ops.connector_connection` is built insert-only apart from its disconnection, and an edit
of a connection is a disconnection and a new row, so a steward held on the connection row would be
lost on every edit and would need an UPDATE the table was built without. Keyed by the source's name
instead: the steward named last is the steward, whatever edits the connection has had since, and a
source nobody has named a steward for is stewarded by whoever `brain.ops.stewardship_store` says
the default is. SELECT and INSERT, and the insert is admitted only when `named_by` is the actor the
transaction is attributed to, so a row cannot name somebody else as the person who named it. The
trigger appends a `connector` ledger entry, `change: steward`, under the source's own subject, in
the transaction that names the steward.

**`gate.self_grant` is one row per grant a person made to themselves, written by the database.**
`0003`'s ledger entry for a grant names the grant and the capability and not the person who
received it, and the application role cannot read a retired grant (`0045`), so a grant made,
used and removed within the hour left nothing a steward's list could be built from. Two triggers,
one on `gate.capability_grant` and one on `gate.capability_pack_assignment`, add a row whenever a
grant's principal is the actor the transaction is attributed to (or, with no attribution, the
row's own `granted_by`), carrying the capabilities and the scope as granted. The row is kept
after the grant is retired, because the misuse a steward is told of is exactly the grant that was
removed afterwards. Recognised by the database rather than declared by the writer, for
`brain.console.reads.THE_GRANT_THAT_MUST_NOT_BE_MISSED_IS_THE_ONE_NOBODY_DECLARES`: every path that
writes a grant, present or future, is covered without being edited. A team grant has no principal
and is not recorded; granting one's own team is a different act, and it is left out rather than
guessed at. The two triggers add their row with `MERGE ... WHEN NOT MATCHED THEN INSERT`, the
ledger append's own form, which keeps one row per grant without a conflict clause and keeps every
statement this migration runs a definition rather than a change to rows already there.

Which objects a self-grant reaches, and so which stewards are told, is decided in
`brain.identity.stewardship` rather than here: it needs `Capability.covers` and the scope rule,
and a second copy of those in SQL is the second implementation `0003` refuses.

**The downgrade** drops both triggers, their functions and both tables. The ledger entries the
steward trigger appended stay, for `0026`'s reason.

Revises `0171`, the head of main when it landed.

Task ids: M7.7.2

Revision ID: 0167
Revises: 0171
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0167"
# The head of origin/main when it landed.
down_revision = "0171"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.connector_steward", "gate.self_grant")

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.stewardship` by `tests/unit/test_stewardship_store.py`.
CONNECTOR_CHARS = 64
CONNECTOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
CAPABILITY_CHARS = 200
PACK_NAME_CHARS = 80

#: The two ways a grant reaches a person that a self-grant can be made through.
KINDS = "kind IN ('capability', 'pack')"

#: The actor a transaction is attributed to, empty when none was set.
ACTOR = "NULLIF(current_setting('brain.actor_id', true), '')"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.connector_steward ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY connector_steward_readable ON ops.connector_steward
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY connector_steward_named_by_the_actor ON ops.connector_steward
        FOR INSERT TO brain_app
        WITH CHECK (named_by = {ACTOR})
    """,
    "ALTER TABLE gate.self_grant ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY self_grant_readable ON gate.self_grant
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY self_grant_recorded ON gate.self_grant
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: SELECT and INSERT on both. Never UPDATE and never DELETE: both are records.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.connector_steward TO brain_app",
    "GRANT SELECT, INSERT ON gate.self_grant TO brain_app",
)

#: A steward named, appended to the ledger under the source's subject, actor the row's own.
STEWARD_TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_connector_steward() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'connector:' || NEW.connector;
    v_details jsonb := jsonb_build_object('change', 'steward', 'steward', NEW.steward_id);
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
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, NEW.named_by, 'connector', v_subject, v_ent_hash, v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.named_by, 'connector', v_subject,
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

STEWARD_TRIGGER = """
CREATE TRIGGER connector_steward_is_audited
    AFTER INSERT ON ops.connector_steward
    FOR EACH ROW EXECUTE FUNCTION ops.record_connector_steward()
"""

#: A direct grant whose principal is the person who made it.
GRANT_TRIGGER_FUNCTION = """
CREATE FUNCTION gate.record_self_grant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.principal_id IS NULL OR NEW.deleted_at IS NOT NULL THEN
        RETURN NULL;
    END IF;
    IF NEW.principal_id IS DISTINCT FROM COALESCE(
        NULLIF(current_setting('brain.actor_id', true), ''), NEW.granted_by
    ) THEN
        RETURN NULL;
    END IF;
    MERGE INTO gate.self_grant AS t
    USING (SELECT 'capability' AS kind, NEW.id AS grant_id) AS s
       ON t.kind = s.kind AND t.grant_id = s.grant_id
    WHEN NOT MATCHED THEN
        INSERT (kind, grant_id, principal_id, capabilities, scope, pack)
        VALUES ('capability', NEW.id, NEW.principal_id, ARRAY[NEW.capability], NEW.scope, NULL);
    RETURN NULL;
END;
$$
"""

GRANT_TRIGGER = """
CREATE TRIGGER capability_grant_self_grant_is_recorded
    AFTER INSERT ON gate.capability_grant
    FOR EACH ROW EXECUTE FUNCTION gate.record_self_grant()
"""

#: A pack assigned to the person who assigned it, with the pack's capabilities as they stand.
PACK_TRIGGER_FUNCTION = """
CREATE FUNCTION gate.record_self_pack() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_capabilities text[];
    v_pack text;
BEGIN
    IF NEW.deleted_at IS NOT NULL THEN
        RETURN NULL;
    END IF;
    IF NEW.principal_id IS DISTINCT FROM COALESCE(
        NULLIF(current_setting('brain.actor_id', true), ''), NEW.granted_by
    ) THEN
        RETURN NULL;
    END IF;
    SELECT k.capabilities, k.name INTO v_capabilities, v_pack
      FROM gate.capability_pack k WHERE k.id = NEW.pack_id;
    MERGE INTO gate.self_grant AS t
    USING (SELECT 'pack' AS kind, NEW.id AS grant_id) AS s
       ON t.kind = s.kind AND t.grant_id = s.grant_id
    WHEN NOT MATCHED THEN
        INSERT (kind, grant_id, principal_id, capabilities, scope, pack)
        VALUES ('pack', NEW.id, NEW.principal_id, COALESCE(v_capabilities, ARRAY[]::text[]),
                NEW.scope, COALESCE(v_pack, 'unknown'));
    RETURN NULL;
END;
$$
"""

PACK_TRIGGER = """
CREATE TRIGGER capability_pack_assignment_self_grant_is_recorded
    AFTER INSERT ON gate.capability_pack_assignment
    FOR EACH ROW EXECUTE FUNCTION gate.record_self_pack()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "connector_steward",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("connector", sa.String(CONNECTOR_CHARS), nullable=False),
        sa.Column("steward_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("named_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "named_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        sa.CheckConstraint(f"steward_id ~ '{IDENTIFIER}'", name="steward_id_shape"),
        sa.CheckConstraint(f"named_by ~ '{IDENTIFIER}'", name="named_by_shape"),
        schema="ops",
    )
    op.create_index(
        "ix_connector_steward_connector",
        "connector_steward",
        ["connector", "named_at"],
        schema="ops",
    )
    op.create_table(
        "self_grant",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("grant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("capabilities", postgresql.ARRAY(sa.String(CAPABILITY_CHARS)), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("pack", sa.String(PACK_NAME_CHARS), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(KINDS, name="kind"),
        sa.CheckConstraint(f"principal_id ~ '{IDENTIFIER}'", name="principal_id_shape"),
        sa.CheckConstraint("jsonb_typeof(scope) = 'object'", name="scope_is_an_object"),
        sa.CheckConstraint("(kind = 'pack') = (pack IS NOT NULL)", name="a_pack_is_named"),
        sa.UniqueConstraint("kind", "grant_id"),
        schema="gate",
    )
    op.create_index("ix_self_grant_at", "self_grant", ["at"], schema="gate")

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(STEWARD_TRIGGER_FUNCTION)
    op.execute(STEWARD_TRIGGER)
    op.execute(GRANT_TRIGGER_FUNCTION)
    op.execute(GRANT_TRIGGER)
    op.execute(PACK_TRIGGER_FUNCTION)
    op.execute(PACK_TRIGGER)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER capability_pack_assignment_self_grant_is_recorded "
        "ON gate.capability_pack_assignment"
    )
    op.execute("DROP FUNCTION gate.record_self_pack()")
    op.execute("DROP TRIGGER capability_grant_self_grant_is_recorded ON gate.capability_grant")
    op.execute("DROP FUNCTION gate.record_self_grant()")
    op.execute("DROP TRIGGER connector_steward_is_audited ON ops.connector_steward")
    op.execute("DROP FUNCTION ops.record_connector_steward()")
    # The policies and the grants go with the tables.
    op.drop_index("ix_self_grant_at", table_name="self_grant", schema="gate")
    op.drop_table("self_grant", schema="gate")
    op.drop_index("ix_connector_steward_connector", table_name="connector_steward", schema="ops")
    op.drop_table("connector_steward", schema="ops")
