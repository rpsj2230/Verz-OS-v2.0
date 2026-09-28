"""A pack is versioned and audited, a person's creation is audited, and a scope's label is a rename.

Three changes to what the ledger is told, each so a console write can be followed to its entry.

**`gate.capability_pack` gains `version`, an integer from one, and a trigger** (M27.15.24). A pack
is created, versioned, copied and retired from the console now, by `brain.govern_pack_routes`, and
until this nothing recorded any of it: `0003` audited a pack's *assignment* as a grant and nothing
about the pack itself, so a pack could change what every holder held with no entry anywhere. The
trigger appends one `pack` entry under `pack:<name>` for each change: `{"change": "created",
"version": "v1"}` on an insert, `{"change": "versioned", "version": "vN"}` when its capabilities or
its label move, and `{"change": "retired"}` when `deleted_at` is set. **The version is written
`v<n>` and never as a number**, because the ledger admits a detail value only when it is a name, and
`3` is a value that `brain.audit.ledger.AuditEntry` refuses to load;
`brain.audit.record.PACK_VERSION_PREFIX` is the same prefix and a test holds the two to one. A
version is the same row updated, so the holders move with it, which `0003`'s
`capability_pack_bumps_versions` already tells every holder's cached reach about;
`brain.govern_pack_routes.A_VERSION_IS_THE_SAME_PACK_MOVED_IN_PLACE` argues the choice. The column
is `NOT NULL DEFAULT 1` with a check that it is at least one, so every pack already written is
version one and the column arrives on a populated table without a data step.

**Every insert into `auth.principal` is recorded** (M27.15.19). A person added by hand from the
People screen had nothing to record them, and neither did the first administrator, the staff sync or
a statement at a prompt: `0095b` records a principal's disable and enable and nothing records that
the principal came to exist. The house rule is that every change is recorded, not only the
console's, so the trigger is on the table and the entry is `principal_state` with `{"change":
"created"}` under `principal:<id>`, which is where that person's disables and enables already sit.
**The actor is named when the application names it and `unattributed` when not, and never refused**,
as `0095b` and `0105` do: refusing to create somebody because a setting was not typed is a failed
sync at night. A principal id outside the ledger's identifier grammar is refused by the entry's
check, which is what every grant to such a principal has always met at `0003`'s trigger.

**A scope's label moving is `renamed`** (M27.11.1). `0086` recorded a department's and a team's
`name` moving as `renamed` and everything else as `changed`, and a scope had no name the console
moved. The Departments screen renames a scope now, through
`brain.identity.organisation_store.rename_scope`, so `gate.record_scope_change` is replaced by the
same function reading `label` where the other two read `name`: a label moving is `renamed`, and
`label` is no longer listed under `changed`. `brain.audit.record.AuditRecorder.organisation` accepts
a scope renamed for the same reason.

**The action list gains `pack` and the subject grammar gains `pack`**, superseding `0118`'s list and
`0136`'s grammar, which are the ones in the database. No grant: the application already holds
SELECT, INSERT and UPDATE on both tables (`0002`), and no role holds DELETE on either.

**The appends are `0003`'s block once more**, beside `0086`'s, `0095b`'s and `0105`'s, for the
reason `0047` gives against editing a function every grant in production goes through.

**The downgrade** drops the two new triggers and their functions, puts `0086`'s scope function back,
drops the column with its check, and puts `0118`'s action list and `0136`'s grammar back `NOT
VALID`, for `0026`'s reason: an entry already recorded stays.

Revises `0140`, in migration train 2 (carried from #169). The chain before it is `0136` halts,
`0137` agent lifecycle entries, `0118` chat bindings, `0138` and `0139` skills and `0140` provider
entries; only `0118` and `0136` left the lists this widens, so the action list is `0118`'s with
`pack` added and the subject grammar `0136`'s with `pack` added. Whoever lands it after another
migration re-points it at the newest head and widens that migration's lists instead.

Task ids: M27.11.1, M27.15.19, M27.15.24

Revision ID: 0141
Revises: 0140
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0141"
# The head of migration train 2 before this car, `0140`. See the docstring.
down_revision = "0140"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0118`'s, the last list
#: the chain before this leaves in the database (`0138`, `0139` and `0140` change neither list).
WIDENED_ACTIONS = (
    "action IN ('agent', 'agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'channel_binding', 'compose_change', 'connector', 'credential', 'deny', 'elevation', "
    "'entity_merge', 'erasure', 'grant', 'halt', 'instructions', 'leash_change', 'legal_hold', "
    "'memory', 'organisation', 'pack', 'principal_state', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', "
    "'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('agent', 'agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'channel_binding', 'compose_change', 'connector', 'credential', 'deny', 'elevation', "
    "'entity_merge', 'erasure', 'grant', 'halt', 'instructions', 'leash_change', 'legal_hold', "
    "'memory', 'organisation', 'principal_state', 'publish', 'record_read', 'retention', "
    "'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', 'vault_access', "
    "'webhook')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0136`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|breach|connector|credential|department|entity|erasure|grant"
    "|halt|leash|legal_hold|memory|pack|principal|retention|routing|scope|session|setting|skill"
    "|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|breach|connector|credential|department|entity|erasure|grant"
    "|halt|leash|legal_hold|memory|principal|retention|routing|scope|session|setting|skill"
    "|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0118`'s action list and `0136`'s subject grammar.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

#: The check the new column carries, as (name, predicate). The name is bare: alembic applies the
#: naming convention on top, as `0121` says of its own.
VERSION_CHECK: tuple[str, str] = ("version_at_least_one", "version >= 1")

#: `0002`'s CREATE TABLE of `gate.capability_pack` as it reads today, for the model comparison in
#: `tests/unit/test_tables.py`. Held to the ALTER the upgrade emits by
#: `tests/unit/test_govern_pack_routes.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "capabilities VARCHAR(200)[] NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT now() "
    "NOT NULL, updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, deleted_at TIMESTAMP "
    "WITH TIME ZONE, CONSTRAINT pk_capability_pack PRIMARY KEY (id),": (
        "capabilities VARCHAR(200)[] NOT NULL, version INTEGER DEFAULT 1 NOT NULL, created_at "
        "TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, updated_at TIMESTAMP WITH TIME ZONE "
        "DEFAULT now() NOT NULL, deleted_at TIMESTAMP WITH TIME ZONE, CONSTRAINT "
        "pk_capability_pack PRIMARY KEY (id),"
    ),
    "CONSTRAINT ck_capability_pack_not_empty CHECK (cardinality(capabilities) > 0) )": (
        "CONSTRAINT ck_capability_pack_not_empty CHECK (cardinality(capabilities) > 0), "
        f"CONSTRAINT ck_capability_pack_{VERSION_CHECK[0]} CHECK ({VERSION_CHECK[1]}) )"
    ),
}

#: The prefix a pack's version carries in an entry. `brain.audit.record.PACK_VERSION_PREFIX`,
#: restated for the reason `0009` gives about reading live code from a migration.
PACK_VERSION_PREFIX = "v"

#: The actor an entry names when the application named nobody, as `0095b` and `0105` write it.
UNATTRIBUTED = "unattributed"

#: The append every trigger here makes, as `0086` and `0121` copy it from `0003`. `{action}`,
#: `{subject}` and `{details}` are the three parts that differ.
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
            v_seq, v_at, v_actor, '{action}', {subject}, v_ent_hash,
            v_trace, {details}, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, '{action}', {subject},
                    v_ent_hash, v_trace, {details}, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
"""

_APPEND_DECLARE = """
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

# ------------------------------------------------------------------------------------ the pack

#: A pack created, versioned or retired, under its own name. A creation and a versioning name the
#: version the row was left at; a retirement names none. A row inserted already retired, which only
#: a statement typed by hand writes, records both, in order, as `0086` records a department.
PACK_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION gate.record_pack_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'pack:' || NEW.name;
    v_actor text := NULLIF(current_setting('brain.actor_id', true), '');
    v_unattributed boolean;
    v_changes text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _APPEND_DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'created'::text;
        IF NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    ELSE
        IF OLD.capabilities IS DISTINCT FROM NEW.capabilities
           OR OLD.description IS DISTINCT FROM NEW.description THEN
            v_changes := v_changes || 'versioned'::text;
        END IF;
        IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    END IF;
    v_unattributed := v_actor IS NULL;
    IF v_unattributed THEN
        v_actor := '"""
    + UNATTRIBUTED
    + """';
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);
        IF v_changes[i] <> 'retired' THEN
            v_details := v_details
                || jsonb_build_object('version', '"""
    + PACK_VERSION_PREFIX
    + """' || NEW.version::text);
        END IF;
        IF v_unattributed THEN
            v_details := v_details || jsonb_build_object('actor', '"""
    + UNATTRIBUTED
    + """');
        END IF;
        -- The append, as 0003, 0086 and 0105 write it. See the module docstring."""
    + _APPEND.format(action="pack", subject="v_subject", details="v_details")
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

PACK_TRIGGER = """
CREATE TRIGGER capability_pack_is_audited
    AFTER INSERT OR UPDATE ON gate.capability_pack
    FOR EACH ROW EXECUTE FUNCTION gate.record_pack_change()
"""

# ------------------------------------------------------------------------------- the principal

#: A principal inserted, under its own id, whoever inserted it.
PRINCIPAL_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION auth.record_principal_created() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text := NULLIF(current_setting('brain.actor_id', true), '');
    v_details jsonb := jsonb_build_object('change', 'created');"""
    + _APPEND_DECLARE
    + """BEGIN
    IF v_actor IS NULL THEN
        v_actor := '"""
    + UNATTRIBUTED
    + """';
        v_details := v_details || jsonb_build_object('actor', '"""
    + UNATTRIBUTED
    + """');
    END IF;
    -- The append, as 0003, 0095b and 0105 write it. See the module docstring."""
    + _APPEND.format(
        action="principal_state", subject="'principal:' || NEW.id", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

PRINCIPAL_TRIGGER = """
CREATE TRIGGER principal_creation_is_audited
    AFTER INSERT ON auth.principal
    FOR EACH ROW EXECUTE FUNCTION auth.record_principal_created()
"""

# ----------------------------------------------------------------------------------- the scope
# `0086`'s builder, copied rather than imported for the reason `0009` gives about reading live code
# from a migration, with the column whose movement is a rename made a parameter. Filled with
# `str.replace` so no SQL is built from a value, as `0086` fills it.

#: The word a trigger writes beside an actor nobody named, as `0003`, `0059` and `0086` write it.
INFERRED = "inferred"

#: `0086`'s columns whose movement is not a change anybody audits.
NOT_A_CHANGE: tuple[str, ...] = ("id", "created_at", "updated_at", "deleted_at")

_DECLARE = """
    v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor text;
    v_fields text;
    v_changes text[] := ARRAY[]::text[];
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

_CHANGES = """
    v_actor := COALESCE(v_supplied, session_user::text);
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'created'::text;
        IF NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    ELSE
        IF (to_jsonb(OLD) -> '__RENAMED__') IS DISTINCT FROM (to_jsonb(NEW) -> '__RENAMED__') THEN
            v_changes := v_changes || 'renamed'::text;
        END IF;
        SELECT string_agg(moved.key, ',' ORDER BY moved.key) INTO v_fields
          FROM jsonb_each(to_jsonb(NEW)) AS moved
         WHERE moved.key <> ALL (ARRAY[__IGNORED__])
           AND moved.value IS DISTINCT FROM (to_jsonb(OLD) -> moved.key);
        IF v_fields IS NOT NULL THEN
            v_changes := v_changes || 'changed'::text;
        END IF;
        IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    END IF;
"""

_DETAILS = (
    """
    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);
        IF v_changes[i] = 'changed' THEN
            v_details := v_details || jsonb_build_object('fields', v_fields);
        END IF;
        IF v_supplied IS NULL THEN
            v_details := v_details || jsonb_build_object('actor', '"""
    + INFERRED
    + """');
        END IF;"""
)


def _quoted(columns: tuple[str, ...]) -> str:
    return ", ".join(f"'{one}'" for one in columns)


def _scope_function(renamed: str, ignored: tuple[str, ...]) -> str:
    """`gate.record_scope_change`, with `renamed` as the column whose movement is a rename."""
    return (
        "\nCREATE OR REPLACE FUNCTION gate.record_scope_change() RETURNS trigger\n"
        "LANGUAGE plpgsql AS $$\nDECLARE"
        + "\n    v_subject text := 'scope:' || NEW.slug;"
        + _DECLARE
        + "BEGIN"
        + _CHANGES.replace("__RENAMED__", renamed).replace("__IGNORED__", _quoted(ignored))
        + _DETAILS
        + _APPEND.format(action="organisation", subject="v_subject", details="v_details")
        + "    END LOOP;\n    RETURN NULL;\nEND;\n$$\n"
    )


#: A scope created, renamed, changed by hand or retired. Its label moving is the rename.
SCOPE_TRIGGER_FUNCTION = _scope_function("label", (*NOT_A_CHANGE, "label"))

#: `0086`'s body, which the downgrade puts back: `name`, which a scope has no column for, so a scope
#: was never renamed and a label moving was `changed`.
PREVIOUS_SCOPE_TRIGGER_FUNCTION = _scope_function("name", NOT_A_CHANGE)


def upgrade() -> None:
    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")

    # The check travels with the column it reads, as `0121`'s do.
    op.add_column(
        "capability_pack",
        sa.Column(
            "version",
            sa.Integer(),
            sa.CheckConstraint(VERSION_CHECK[1], name=VERSION_CHECK[0]),
            server_default=sa.text("1"),
            nullable=False,
        ),
        schema="gate",
    )

    op.execute(PACK_TRIGGER_FUNCTION)
    op.execute(PACK_TRIGGER)
    op.execute(PRINCIPAL_TRIGGER_FUNCTION)
    op.execute(PRINCIPAL_TRIGGER)
    op.execute(SCOPE_TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(PREVIOUS_SCOPE_TRIGGER_FUNCTION)
    op.execute("DROP TRIGGER principal_creation_is_audited ON auth.principal")
    op.execute("DROP FUNCTION auth.record_principal_created()")
    op.execute("DROP TRIGGER capability_pack_is_audited ON gate.capability_pack")
    op.execute("DROP FUNCTION gate.record_pack_change()")
    # The check goes with the column that carries it.
    op.drop_column("capability_pack", "version", schema="gate")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs", postgresql_not_valid=True
    )
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
