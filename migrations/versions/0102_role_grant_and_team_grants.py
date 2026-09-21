"""Who holds a platform role, and a team as the subject of a capability grant.

**`gate.role_grant`: the role grants `brain.identity.roles.RoleGrant` describes (M1.3.2).**
`0006` built only what a directory asserts and refused to let that table stand in for this one.
One row is one person holding one role: a scope exactly when the role needs one, the principal a
deputy covers for (M1.3.3), who granted it and why, a lapse, and the separation-of-duties
acknowledgement an appointment may need (M1.8.7). Retired with `deleted_at` and never deleted:
SELECT, INSERT and UPDATE of the two retiring columns, and no DELETE, for `0002`'s reason.

**Two rules are the database's as well as the application's, because a row can arrive another
way.** `gate.guard_role_grant` refuses a deputy covering anybody who does not hold the same role
in their own right (depth one), and refuses retiring a standing Super Admin when fewer than two
others would stand (M1.3.4), under an advisory lock so two revocations cannot each count the
other. The thirty-day bound on a deputy and the scope rule are check constraints.

**Audited by `gate.record_role_grant`**: a `grant` entry on an insert and a `revoke` entry on the
retirement, under the subject `principal:<id>`, with the role, the covered principal and the
acknowledgement in the details, and `source` `role_grant`, so
`brain.identity.administration_reconciliation`, which reads `capability_grant` entries, never
mistakes one for a capability first run wrote.

**`gate.capability_grant.team_path`: a grant whose subject is a team (M1.5.3).** `principal_id`
becomes nullable and two checks hold exactly one of the two. `gate.held_grants` gains the team
branch, so a live member of a live team in a live department holds the team's grants, and the
bump reaches every member: a team grant fans out, a membership change bumps its person, and a
team retired bumps everybody in it. `gate.record_entitlement_change` names the team on a team
grant's entry rather than resolving a principal it does not have.

**The downgrade** drops the role table and the team column, puts `0003`'s and `0095`'s functions
back, and re-adds a principal on every grant as a check `NOT VALID`, for `0026`'s reason: a team
grant already written stays as history and no new one is accepted.

Task ids: M1.3.2, M1.3.3, M1.3.4, M1.5.3, M1.8.7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0102"
# The newest migration on origin/main when this was written.
down_revision = "0101"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.role_grant",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.tables.role_grant` and `brain.tables.gate`
#: by `tests/unit/test_role_grant.py`.
PRINCIPAL_ID_CHARS = 128
ROLE_CHARS = 32
TEAM_PATH_CHARS = 121
ROLES = (
    "role IN ('approver', 'auditor', 'connector_admin', 'department_admin', 'member', "
    "'super_admin')"
)
SCOPE_REQUIRED = "(role IN ('approver', 'department_admin')) = (scope IS NOT NULL)"
SCOPE_SHAPE = (
    "scope IS NULL OR (jsonb_typeof(scope) = 'object' "
    "AND jsonb_typeof(scope -> 'clauses') = 'array')"
)
DEPUTY_DAYS = 30
DEPUTY_BOUNDED = (
    "deputy_of IS NULL OR (not_after IS NOT NULL "
    f"AND not_after <= created_at + make_interval(days => {DEPUTY_DAYS}))"
)
#: Exactly one subject, as two checks the previous release's rows satisfy on their face: see
#: `brain.deployment.compatibility.A_RESTRICTION_ON_A_COLUMN_THE_PREVIOUS_RELEASE_NEVER_WRITES_...`.
NO_PRINCIPAL_ON_A_TEAM_GRANT = "team_path IS NULL OR principal_id IS NULL"
A_SUBJECT_IS_NAMED = "principal_id IS NOT NULL OR team_path IS NOT NULL"
TEAM_PATH_GRAMMAR = "team_path IS NULL OR team_path ~ '^[a-z][a-z0-9_]*[.][a-z][a-z0-9_]*$'"
SUPER_ADMIN_FLOOR = 2

#: The two checks on `gate.capability_grant`, as (name, predicate).
CAPABILITY_GRANT_CHECKS: tuple[tuple[str, str], ...] = (
    ("a_team_grant_names_no_principal", NO_PRINCIPAL_ON_A_TEAM_GRANT),
    ("a_grant_names_a_subject", A_SUBJECT_IS_NAMED),
    ("team_path_grammar", TEAM_PATH_GRAMMAR),
)

#: The advisory lock every retirement of a role grant takes. Its own number.
ROLE_LOCK = 8274419102

#: `gate.capability_grant` as `0002`'s CREATE TABLE would read today, for the comparison
#: `tests/unit/test_tables.py` makes between that table and its model.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "CREATE TABLE gate.capability_grant ( id UUID DEFAULT gen_random_uuid() NOT NULL, "
    "principal_id VARCHAR(128) NOT NULL,": (
        "CREATE TABLE gate.capability_grant ( id UUID DEFAULT gen_random_uuid() NOT NULL, "
        f"principal_id VARCHAR(128), team_path VARCHAR({TEAM_PATH_CHARS}),"
    ),
    "CONSTRAINT ck_capability_grant_reason_present CHECK (length(btrim(reason)) > 0),": (
        "CONSTRAINT ck_capability_grant_reason_present CHECK (length(btrim(reason)) > 0), "
        "CONSTRAINT ck_capability_grant_a_team_grant_names_no_principal "
        f"CHECK ({NO_PRINCIPAL_ON_A_TEAM_GRANT}), "
        f"CONSTRAINT ck_capability_grant_a_grant_names_a_subject CHECK ({A_SUBJECT_IS_NAMED}), "
        f"CONSTRAINT ck_capability_grant_team_path_grammar CHECK ({TEAM_PATH_GRAMMAR}),"
    ),
}

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON gate.role_grant TO brain_app",
    "GRANT UPDATE (deleted_at, updated_at) ON gate.role_grant TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.role_grant ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY role_grant_live ON gate.role_grant
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY role_grant_insertable ON gate.role_grant
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY role_grant_updatable ON gate.role_grant
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)

_GUARD_TEMPLATE = """
CREATE FUNCTION gate.guard_role_grant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_others integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.deputy_of IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM gate.role_grant s
             WHERE s.principal_id = NEW.deputy_of
               AND s.role = NEW.role
               AND s.deputy_of IS NULL
               AND s.deleted_at IS NULL
               AND (s.not_after IS NULL OR s.not_after > now())
        ) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'a deputy covers somebody holding the same role in their own right',
                ERRCODE = 'check_violation',
                HINT = 'deputies are depth one';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL
       AND OLD.role = 'super_admin' AND OLD.deputy_of IS NULL
       AND (OLD.not_after IS NULL OR OLD.not_after > now()) THEN
        PERFORM pg_advisory_xact_lock(__LOCK__);
        SELECT count(DISTINCT s.principal_id) INTO v_others
          FROM gate.role_grant s
         WHERE s.role = 'super_admin'
           AND s.deputy_of IS NULL
           AND s.deleted_at IS NULL
           AND s.id <> OLD.id
           AND s.principal_id <> OLD.principal_id
           AND (s.not_after IS NULL OR s.not_after > now());
        IF v_others < __FLOOR__ THEN
            RAISE EXCEPTION USING
                MESSAGE = 'retiring this grant would leave fewer than __FLOOR__ '
                          || 'standing Super Admins',
                ERRCODE = 'check_violation',
                HINT = 'appoint another Super Admin first';
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""

GUARD_FUNCTION = _GUARD_TEMPLATE.replace("__LOCK__", str(ROLE_LOCK)).replace(
    "__FLOOR__", str(SUPER_ADMIN_FLOOR)
)

GUARD_TRIGGER = """
CREATE TRIGGER role_grant_is_guarded
    BEFORE INSERT OR UPDATE ON gate.role_grant
    FOR EACH ROW EXECUTE FUNCTION gate.guard_role_grant()
"""

#: The append, `0003`'s block, over one change.
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
    v_row jsonb := to_jsonb(NEW);
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

_AUDIT_TEMPLATE = """
CREATE FUNCTION gate.record_role_grant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE__DECLARATIONS__BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_action := 'grant';
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        v_action := 'revoke';
    END IF;
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, NEW.granted_by);
    v_subject := 'principal:' || NEW.principal_id;
    v_details := jsonb_build_object('role', NEW.role, 'source', 'role_grant');
    IF NEW.deputy_of IS NOT NULL THEN
        v_details := v_details || jsonb_build_object('deputy_of', NEW.deputy_of);
    END IF;
    IF NEW.acknowledgement IS NOT NULL AND v_action = 'grant' THEN
        v_details := v_details || jsonb_build_object(
            'acknowledged', 'separation_of_duties', 'acknowledgement', NEW.acknowledgement
        );
    END IF;
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
"""

AUDIT_FUNCTION = _AUDIT_TEMPLATE.replace("__DECLARATIONS__", _DECLARATIONS).replace(
    "__APPEND__", _APPEND
)

AUDIT_TRIGGER = """
CREATE TRIGGER role_grant_is_audited
    AFTER INSERT OR UPDATE ON gate.role_grant
    FOR EACH ROW EXECUTE FUNCTION gate.record_role_grant()
"""

#: `0095`'s rows, and a team's grants for its live members, under the same partner window.
HELD_GRANTS_WITH_TEAMS = """
CREATE OR REPLACE FUNCTION gate.held_grants(p_principal_id text, p_now timestamptz)
RETURNS TABLE (capability text, scope jsonb, not_after timestamptz)
LANGUAGE sql
STABLE
AS $$
    SELECT g.capability::text, g.scope, g.not_after
    FROM gate.capability_grant g
    JOIN auth.principal pr ON pr.id = g.principal_id
    WHERE g.principal_id = p_principal_id
      AND g.deleted_at IS NULL
      AND (g.not_after IS NULL OR g.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (g.not_after IS NOT NULL AND g.not_after <= g.created_at + interval '4 hours')
      )
    UNION ALL
    SELECT member.capability::text, a.scope, a.not_after
    FROM gate.capability_pack_assignment a
    JOIN gate.capability_pack k
      ON k.id = a.pack_id
     AND k.deleted_at IS NULL
    JOIN auth.principal pr ON pr.id = a.principal_id
    CROSS JOIN LATERAL unnest(k.capabilities) AS member(capability)
    WHERE a.principal_id = p_principal_id
      AND a.deleted_at IS NULL
      AND (a.not_after IS NULL OR a.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (a.not_after IS NOT NULL AND a.not_after <= a.created_at + interval '4 hours')
      )
    UNION ALL
    SELECT g.capability::text, g.scope, g.not_after
    FROM gate.team_membership m
    JOIN gate.team t ON t.id = m.team_id AND t.deleted_at IS NULL
    JOIN gate.department d ON d.id = t.department_id AND d.deleted_at IS NULL
    JOIN gate.capability_grant g ON g.team_path = d.slug || '.' || t.slug
    JOIN auth.principal pr ON pr.id = m.principal_id
    WHERE m.principal_id = p_principal_id
      AND m.ended_at IS NULL
      AND g.deleted_at IS NULL
      AND (g.not_after IS NULL OR g.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (g.not_after IS NOT NULL AND g.not_after <= g.created_at + interval '4 hours')
      )
$$
"""

#: `0095`'s, restated for the downgrade.
HELD_GRANTS_AS_0095_WROTE_IT = """
CREATE OR REPLACE FUNCTION gate.held_grants(p_principal_id text, p_now timestamptz)
RETURNS TABLE (capability text, scope jsonb, not_after timestamptz)
LANGUAGE sql
STABLE
AS $$
    SELECT g.capability::text, g.scope, g.not_after
    FROM gate.capability_grant g
    JOIN auth.principal pr ON pr.id = g.principal_id
    WHERE g.principal_id = p_principal_id
      AND g.deleted_at IS NULL
      AND (g.not_after IS NULL OR g.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (g.not_after IS NOT NULL AND g.not_after <= g.created_at + interval '4 hours')
      )
    UNION ALL
    SELECT member.capability::text, a.scope, a.not_after
    FROM gate.capability_pack_assignment a
    JOIN gate.capability_pack k
      ON k.id = a.pack_id
     AND k.deleted_at IS NULL
    JOIN auth.principal pr ON pr.id = a.principal_id
    CROSS JOIN LATERAL unnest(k.capabilities) AS member(capability)
    WHERE a.principal_id = p_principal_id
      AND a.deleted_at IS NULL
      AND (a.not_after IS NULL OR a.not_after > p_now)
      AND pr.deleted_at IS NULL
      AND pr.disabled_at IS NULL
      AND (
          pr.employment <> 'partner'
          OR (a.not_after IS NOT NULL AND a.not_after <= a.created_at + interval '4 hours')
      )
$$
"""

_EPOCH = """
    MERGE INTO gate.policy_epoch AS pe
    USING (SELECT 1 AS id) AS s
       ON pe.id = s.id
    WHEN MATCHED THEN
        UPDATE SET epoch = pe.epoch + 1, updated_at = now()
    WHEN NOT MATCHED THEN
        INSERT (id, epoch) VALUES (1, 1);
"""

_BUMP_ONE = """
    MERGE INTO gate.grants_version AS gv
    USING (SELECT v_principal AS principal_id) AS s
       ON gv.principal_id = s.principal_id
    WHEN MATCHED THEN
        UPDATE SET version = gv.version + 1, updated_at = now()
    WHEN NOT MATCHED THEN
        INSERT (principal_id, version) VALUES (s.principal_id, 1);
"""

#: The members of a team named by path, or by id, as a MERGE source.
_BUMP_MEMBERS = """
    MERGE INTO gate.grants_version AS gv
    USING (
        SELECT DISTINCT m.principal_id
        FROM gate.team_membership m
        JOIN gate.team t ON t.id = m.team_id
        JOIN gate.department d ON d.id = t.department_id
        WHERE m.ended_at IS NULL AND __WHICH__
    ) AS s
       ON gv.principal_id = s.principal_id
    WHEN MATCHED THEN
        UPDATE SET version = gv.version + 1, updated_at = now()
    WHEN NOT MATCHED THEN
        INSERT (principal_id, version) VALUES (s.principal_id, 1);
"""

_BUMP_WITH_TEAMS_TEMPLATE = """
CREATE OR REPLACE FUNCTION gate.bump_grants_version() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_principal text := to_jsonb(NEW) ->> 'principal_id';
    v_team text := to_jsonb(NEW) ->> 'team_path';
BEGIN
    IF v_team IS NOT NULL THEN
__MEMBERS__
    ELSE
__ONE__
    END IF;
__EPOCH__
    RETURN NULL;
END;
$$
"""

BUMP_WITH_TEAMS = (
    _BUMP_WITH_TEAMS_TEMPLATE.replace(
        "__MEMBERS__", _BUMP_MEMBERS.replace("__WHICH__", "d.slug || '.' || t.slug = v_team")
    )
    .replace("__ONE__", _BUMP_ONE)
    .replace("__EPOCH__", _EPOCH)
)

_BUMP_0003_TEMPLATE = """
CREATE OR REPLACE FUNCTION gate.bump_grants_version() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_principal text := to_jsonb(NEW) ->> 'principal_id';
BEGIN
__ONE____EPOCH__
    RETURN NULL;
END;
$$
"""

BUMP_AS_0003_WROTE_IT = _BUMP_0003_TEMPLATE.replace("__ONE__", _BUMP_ONE).replace(
    "__EPOCH__", _EPOCH
)

_BUMP_FOR_TEAM_TEMPLATE = """
CREATE FUNCTION gate.bump_grants_version_for_team() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
__MEMBERS____EPOCH__
    RETURN NULL;
END;
$$
"""

BUMP_FOR_TEAM_FUNCTION = _BUMP_FOR_TEAM_TEMPLATE.replace(
    "__MEMBERS__", _BUMP_MEMBERS.replace("__WHICH__", "t.id = NEW.id")
).replace("__EPOCH__", _EPOCH)

#: A membership now confers, so its change moves its person's version; a team retired moves all.
BUMP_TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER team_membership_bumps_version
        AFTER INSERT OR UPDATE ON gate.team_membership
        FOR EACH ROW EXECUTE FUNCTION gate.bump_grants_version()
    """,
    """
    CREATE TRIGGER team_bumps_version
        AFTER UPDATE OF deleted_at ON gate.team
        FOR EACH ROW EXECUTE FUNCTION gate.bump_grants_version_for_team()
    """,
)

_ENTITLEMENT_CHANGE = """
CREATE OR REPLACE FUNCTION gate.record_entitlement_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE__DECLARATIONS__BEGIN
    IF tg_op = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_action := 'grant';
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        v_action := 'revoke';
    END IF;

    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, v_row ->> 'granted_by');
    v_subject := 'grant:' || (v_row ->> 'id');

    IF tg_table_name = 'capability_grant' THEN
        v_details := jsonb_build_object('capability', v_row ->> 'capability');
    ELSE
        v_details := jsonb_build_object(
            'pack',
            COALESCE(
                (SELECT k.name FROM gate.capability_pack k
                  WHERE k.id = (v_row ->> 'pack_id')::uuid),
                'unknown'
            )
        );
    END IF;
    v_details := v_details || jsonb_build_object('source', tg_table_name);

    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__HOLDS__
__APPEND__
    RETURN NULL;
END;
$$
""".replace("__DECLARATIONS__", _DECLARATIONS).replace("__APPEND__", _APPEND)

_HOLDS_0003 = """
    v_details := v_details || jsonb_build_object(
        'holds',
        CASE
            WHEN jsonb_array_length(
                gate.resolve_entitlements(v_row ->> 'principal_id', v_at) -> 'grants'
            ) = 0 THEN 'none'
            ELSE 'some'
        END
    );
"""

_HOLDS_WITH_TEAMS = """
    IF v_row ->> 'team_path' IS NOT NULL THEN
        v_details := v_details || jsonb_build_object('team', v_row ->> 'team_path');
    ELSE__HOLDS__    END IF;
""".replace("__HOLDS__", _HOLDS_0003)

ENTITLEMENT_CHANGE_WITH_TEAMS = _ENTITLEMENT_CHANGE.replace("__HOLDS__", _HOLDS_WITH_TEAMS)
ENTITLEMENT_CHANGE_AS_0003_WROTE_IT = _ENTITLEMENT_CHANGE.replace("__HOLDS__", _HOLDS_0003)


#: A downgrade leaves `principal_present` behind for the team grants it keeps; a later upgrade
#: removes it by whichever name it has, as `0093` drops a constraint that may be absent.
DROP_A_DOWNGRADES_PRINCIPAL_CHECK = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'gate.capability_grant'::regclass
           AND c.contype = 'c'
           AND c.conname = 'ck_capability_grant_principal_present'
    LOOP
        EXECUTE 'ALTER TABLE gate.capability_grant DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "role_grant",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("role", sa.String(ROLE_CHARS), nullable=False),
        sa.Column("scope", JSONB(), nullable=True),
        sa.Column("deputy_of", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("granted_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("acknowledgement", sa.Text(), nullable=True),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_role_grant"),
        sa.CheckConstraint(ROLES, name="role"),
        sa.CheckConstraint(SCOPE_REQUIRED, name="scope_exactly_when_required"),
        sa.CheckConstraint(SCOPE_SHAPE, name="scope_shape"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        sa.CheckConstraint(
            "acknowledgement IS NULL OR length(btrim(acknowledgement)) > 0",
            name="acknowledgement_present",
        ),
        sa.CheckConstraint(
            "deputy_of IS NULL OR deputy_of <> principal_id", name="not_its_own_deputy"
        ),
        sa.CheckConstraint(DEPUTY_BOUNDED, name="a_deputy_is_bounded"),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["auth.principal.id"],
            name="fk_role_grant_principal_id_principal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deputy_of"],
            ["auth.principal.id"],
            name="fk_role_grant_deputy_of_principal",
            ondelete="RESTRICT",
        ),
        schema="gate",
    )
    op.create_index(
        "ix_gate_role_grant_principal_id", "role_grant", ["principal_id"], schema="gate"
    )
    op.create_index("ix_gate_role_grant_deleted_at", "role_grant", ["deleted_at"], schema="gate")
    op.create_index(
        "uq_role_grant_principal_id_role_standing_live",
        "role_grant",
        ["principal_id", "role"],
        unique=True,
        schema="gate",
        postgresql_where=sa.text("deleted_at IS NULL AND deputy_of IS NULL AND scope IS NULL"),
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(GUARD_FUNCTION)
    op.execute(GUARD_TRIGGER)
    op.execute(AUDIT_FUNCTION)
    op.execute(AUDIT_TRIGGER)

    op.add_column(
        "capability_grant",
        sa.Column("team_path", sa.String(TEAM_PATH_CHARS), nullable=True),
        schema="gate",
    )
    op.alter_column("capability_grant", "principal_id", nullable=True, schema="gate")
    op.execute(DROP_A_DOWNGRADES_PRINCIPAL_CHECK)
    op.create_check_constraint(
        "a_team_grant_names_no_principal",
        "capability_grant",
        NO_PRINCIPAL_ON_A_TEAM_GRANT,
        schema="gate",
    )
    op.create_check_constraint(
        "a_grant_names_a_subject", "capability_grant", A_SUBJECT_IS_NAMED, schema="gate"
    )
    op.create_check_constraint(
        "team_path_grammar", "capability_grant", TEAM_PATH_GRAMMAR, schema="gate"
    )
    op.create_index(
        "ix_gate_capability_grant_team_path", "capability_grant", ["team_path"], schema="gate"
    )
    op.create_index(
        "uq_capability_grant_team_path_capability_live",
        "capability_grant",
        ["team_path", "capability"],
        unique=True,
        schema="gate",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(HELD_GRANTS_WITH_TEAMS)
    op.execute(BUMP_WITH_TEAMS)
    op.execute(BUMP_FOR_TEAM_FUNCTION)
    for statement in BUMP_TRIGGERS:
        op.execute(statement)
    op.execute(ENTITLEMENT_CHANGE_WITH_TEAMS)


def downgrade() -> None:
    op.execute(ENTITLEMENT_CHANGE_AS_0003_WROTE_IT)
    op.execute("DROP TRIGGER team_bumps_version ON gate.team")
    op.execute("DROP TRIGGER team_membership_bumps_version ON gate.team_membership")
    op.execute("DROP FUNCTION gate.bump_grants_version_for_team()")
    op.execute(BUMP_AS_0003_WROTE_IT)
    op.execute(HELD_GRANTS_AS_0095_WROTE_IT)
    op.drop_index(
        "uq_capability_grant_team_path_capability_live", "capability_grant", schema="gate"
    )
    op.drop_index("ix_gate_capability_grant_team_path", "capability_grant", schema="gate")
    for name, _ in reversed(CAPABILITY_GRANT_CHECKS):
        op.drop_constraint(name, "capability_grant", schema="gate", type_="check")
    op.drop_column("capability_grant", "team_path", schema="gate")
    op.create_check_constraint(
        "principal_present",
        "capability_grant",
        "principal_id IS NOT NULL",
        schema="gate",
        postgresql_not_valid=True,
    )
    op.execute("DROP TRIGGER role_grant_is_audited ON gate.role_grant")
    op.execute("DROP FUNCTION gate.record_role_grant()")
    op.execute("DROP TRIGGER role_grant_is_guarded ON gate.role_grant")
    op.execute("DROP FUNCTION gate.guard_role_grant()")
    op.drop_index("uq_role_grant_principal_id_role_standing_live", "role_grant", schema="gate")
    op.drop_index("ix_gate_role_grant_deleted_at", "role_grant", schema="gate")
    op.drop_index("ix_gate_role_grant_principal_id", "role_grant", schema="gate")
    op.drop_table("role_grant", schema="gate")
