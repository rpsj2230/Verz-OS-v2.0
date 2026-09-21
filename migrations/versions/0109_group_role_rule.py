"""Which directory group confers which role, the sync's ledger entries, and break-glass notices.

**`auth.group_role_rule`: the mapping an administrator keeps on the Roles screen (M1.1.5).** One
live row is one group, as the identity provider spells it, conferring one platform role, with a
scope exactly when the role needs one. It is `brain.identity.oidc.GroupRoleRule` stored, and it
has no capability column, because a group maps to a role and to nothing else
(`oidc.CLAIMS_NEVER_GRANT`). Retired with `deleted_at` and never deleted: SELECT, INSERT and UPDATE
of the two retiring columns, for `0002`'s reason. One live rule per group, so a group never means
two things at once.

**`auth.record_group_role_rule` audits the mapping** as a `setting` entry under
`setting:group_role_rule.<id>`, with the role, whether it was added or retired, and the group as a
sha256 digest: a group path is not a field name, and the ledger refuses anything that is not a
name or a digest (`brain.audit.ledger.redact_details`).

**`auth.record_directory_role_grant` audits the sync itself.** `0006` built the table the sync owns
and said the record that a directory once asserted a role belongs in `obs.audit_entry`, and until
now nothing wrote it. A `grant` entry on an insert and a `revoke` entry on a delete, under
`principal:<id>`, with `source` `directory`, so `brain.identity.administration_reconciliation`,
which counts `capability_grant` and `role_grant` entries, never mistakes a synced one for either.
The touch of `last_seen_at` is bookkeeping about the sync and is not audited.

**`gate.break_glass_notice`: a standing Super Admin told that a break-glass session opened
(M1.2.5).** One row per recipient per approved elevation, written in the approval's transaction by
`brain.gate.elevation_store`; the recipient reads their own on the Elevation screen. SELECT and
INSERT only: a record that somebody was told is never edited. `USING (true)`, for `0101`'s reason:
the one reader selects by the caller's own principal id.

**The downgrade** drops both triggers, both functions and both tables. The synced rows stay in
`0006`'s table, which is where they lived before this release, and the notices go with their table,
which is the state before it: nobody was told.

Task ids: M1.1.5, M1.2.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0109"
# The newest migration on origin/main when this was written.
down_revision = "0105"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("auth.group_role_rule", "gate.break_glass_notice")

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to the model by `tests/unit/test_group_sync.py`.
GROUP_CHARS = 300
PRINCIPAL_ID_CHARS = 128
ROLE_CHARS = 32
ROLES = (
    "role IN ('approver', 'auditor', 'connector_admin', 'department_admin', 'member', "
    "'super_admin')"
)
SCOPE_REQUIRED = "(role IN ('approver', 'department_admin')) = (scope IS NOT NULL)"
SCOPE_SHAPE = (
    "scope IS NULL OR (jsonb_typeof(scope) = 'object' "
    "AND jsonb_typeof(scope -> 'clauses') = 'array')"
)

#: Who the ledger names for a synced grant when the writer set nobody. An identifier, as the
#: ledger's actor column requires, and held equal to `brain.identity.group_sync`.
SYNC_ACTOR = "directory_sync"

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON auth.group_role_rule TO brain_app",
    "GRANT UPDATE (deleted_at, updated_at) ON auth.group_role_rule TO brain_app",
)

#: `brain.identity.roles.BreakGlassReason`, copied for `0004`'s reason.
BREAK_GLASS_REASONS = "reason IN ('data_recovery', 'incident_response', 'install', 'lockout')"

NOTICE_GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON gate.break_glass_notice TO brain_app",)

NOTICE_RLS: tuple[str, ...] = (
    "ALTER TABLE gate.break_glass_notice ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY break_glass_notice_readable ON gate.break_glass_notice
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY break_glass_notice_insertable ON gate.break_glass_notice
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

RLS: tuple[str, ...] = (
    "ALTER TABLE auth.group_role_rule ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY group_role_rule_live ON auth.group_role_rule
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY group_role_rule_insertable ON auth.group_role_rule
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY group_role_rule_updatable ON auth.group_role_rule
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)

#: The append, `0003`'s block, over one change, as `0102` copies it.
_APPEND = """
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
        v_seq, v_at, v_actor, v_action, v_subject, v_ent_hash, v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, v_action, v_subject, v_ent_hash, v_trace,
                v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
"""

_DECLARATIONS = """
    v_action text;
    v_actor text;
    v_supplied text;
    v_subject text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

_RULE_AUDIT_TEMPLATE = """
CREATE FUNCTION auth.record_group_role_rule() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE__DECLARATIONS__BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_details := jsonb_build_object('change', 'added');
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        v_details := jsonb_build_object('change', 'retired');
    END IF;
    v_action := 'setting';
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, NEW.created_by);
    v_subject := 'setting:group_role_rule.' || NEW.id::text;
    v_details := v_details || jsonb_build_object(
        'role', NEW.role,
        'source', 'group_role_rule',
        'group_digest', encode(sha256(convert_to(NEW.idp_group, 'UTF8')), 'hex')
    );
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
"""

_SYNC_AUDIT_TEMPLATE = """
CREATE FUNCTION auth.record_directory_role_grant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE__DECLARATIONS__    v_principal text;
    v_role text;
    v_group text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_action := 'grant';
        v_principal := NEW.principal_id;
        v_role := NEW.role;
        v_group := NEW.source_group;
    ELSE
        v_action := 'revoke';
        v_principal := OLD.principal_id;
        v_role := OLD.role;
        v_group := OLD.source_group;
    END IF;
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, '__SYNC_ACTOR__');
    v_subject := 'principal:' || v_principal;
    v_details := jsonb_build_object(
        'role', v_role,
        'source', 'directory',
        'group_digest', encode(sha256(convert_to(v_group, 'UTF8')), 'hex')
    );
__APPEND__
    RETURN NULL;
END;
$$
"""

RULE_AUDIT_FUNCTION = _RULE_AUDIT_TEMPLATE.replace("__DECLARATIONS__", _DECLARATIONS).replace(
    "__APPEND__", _APPEND
)
SYNC_AUDIT_FUNCTION = (
    _SYNC_AUDIT_TEMPLATE.replace("__DECLARATIONS__", _DECLARATIONS)
    .replace("__APPEND__", _APPEND)
    .replace("__SYNC_ACTOR__", SYNC_ACTOR)
)

RULE_AUDIT_TRIGGER = """
CREATE TRIGGER group_role_rule_is_audited
    AFTER INSERT OR UPDATE ON auth.group_role_rule
    FOR EACH ROW EXECUTE FUNCTION auth.record_group_role_rule()
"""

SYNC_AUDIT_TRIGGER = """
CREATE TRIGGER directory_role_grant_is_audited
    AFTER INSERT OR DELETE ON auth.directory_role_grant
    FOR EACH ROW EXECUTE FUNCTION auth.record_directory_role_grant()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in (*GRANTS, *NOTICE_GRANTS))
    assert all("DELETE" not in statement for statement in (*GRANTS, *NOTICE_GRANTS))

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "group_role_rule",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("idp_group", sa.String(GROUP_CHARS), nullable=False),
        sa.Column("role", sa.String(ROLE_CHARS), nullable=False),
        sa.Column("scope", JSONB(), nullable=True),
        sa.Column("created_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_group_role_rule"),
        sa.CheckConstraint(ROLES, name="role"),
        sa.CheckConstraint(SCOPE_REQUIRED, name="scope_exactly_when_required"),
        sa.CheckConstraint(SCOPE_SHAPE, name="scope_shape"),
        sa.CheckConstraint("length(btrim(idp_group)) > 0", name="group_present"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        schema="auth",
    )
    op.create_index(
        "ix_auth_group_role_rule_deleted_at", "group_role_rule", ["deleted_at"], schema="auth"
    )
    op.create_index(
        "uq_group_role_rule_idp_group_live",
        "group_role_rule",
        ["idp_group"],
        unique=True,
        schema="auth",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(RULE_AUDIT_FUNCTION)
    op.execute(RULE_AUDIT_TRIGGER)
    op.execute(SYNC_AUDIT_FUNCTION)
    op.execute(SYNC_AUDIT_TRIGGER)

    op.create_table(
        "break_glass_notice",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("authorised_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason", sa.String(ROLE_CHARS), nullable=False),
        sa.Column("lapses_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_break_glass_notice"),
        sa.CheckConstraint(BREAK_GLASS_REASONS, name="reason"),
        sa.CheckConstraint("recipient_id <> principal_id", name="never_told_to_the_person_acting"),
        sa.UniqueConstraint(
            "request_id", "recipient_id", name="uq_break_glass_notice_request_id_recipient_id"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["gate.elevation_request.id"],
            name="fk_break_glass_notice_request_id_elevation_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["auth.principal.id"],
            name="fk_break_glass_notice_recipient_id_principal",
            ondelete="RESTRICT",
        ),
        schema="gate",
    )
    op.create_index(
        "ix_gate_break_glass_notice_recipient_id",
        "break_glass_notice",
        ["recipient_id"],
        schema="gate",
    )
    for statement in NOTICE_RLS:
        op.execute(statement)
    for statement in NOTICE_GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_gate_break_glass_notice_recipient_id", "break_glass_notice", schema="gate")
    op.drop_table("break_glass_notice", schema="gate")
    op.execute("DROP TRIGGER directory_role_grant_is_audited ON auth.directory_role_grant")
    op.execute("DROP FUNCTION auth.record_directory_role_grant()")
    op.execute("DROP TRIGGER group_role_rule_is_audited ON auth.group_role_rule")
    op.execute("DROP FUNCTION auth.record_group_role_rule()")
    op.drop_index("uq_group_role_rule_idp_group_live", "group_role_rule", schema="auth")
    op.drop_index("ix_auth_group_role_rule_deleted_at", "group_role_rule", schema="auth")
    op.drop_table("group_role_rule", schema="auth")
