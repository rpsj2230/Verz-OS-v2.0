"""Departments, teams and scopes are audited: created, renamed, changed by hand and retired.

`brain.console.organisation` argues who may change the structure and `brain.identity.
organisation_store` writes it. What is here is the three triggers that record every change to
`gate.department`, `gate.team` and `gate.scope`, and the two subject kinds the entries are filed
under. No table is created, dropped or altered, and no row is written: this is schema only.

**Measured before this was written, on origin/main at f3252c7: nothing recorded any of the three.**
`0003` created the tables with no trigger, `0045` rewrote their policies and added none, and `0062`
audited the placements inside a department and nothing else, which
`docs/admin-console-architecture.md` records against B2 as a writer with audit triggers still to
build. Furnishing, the demo seed and every test fixture wrote those rows unrecorded.

**Every change is recorded, not only the console's**, for `0059`'s reason about `ops.setting`: a
trigger that recorded only the columns the console moves would leave a hand-typed change to a
scope's predicate unrecorded while reading as though the table were covered, and a predicate is
what every grant over the scope reaches. So an insert is `created`, a change to `name` is `renamed`,
a change to any other column except the three instants and the id is `changed` with the column names
and never their values, and `deleted_at` being set is `retired`. A row inserted already retired,
which only a statement typed by hand writes, records both, in order.

**The actor is the one the application named, or the database role marked inferred.** None of the
three tables has a column naming who changed it, so the actor is `brain.actor_id` as
`brain.identity.organisation_store` sets it, and a statement that set nothing is attributed to the
role it ran as with `actor: inferred`, which is `0059`'s arrangement for a routing rung.

**The subjects: `department:<slug>` for a department and each of its teams, and `scope:<slug>`**,
which `brain.audit.ledger.AuditAction.ORGANISATION` argues. A team's entry carries its path,
`<department>.<team>`, read through the department it belongs to, as `0062`'s membership trigger
reads it. The store retires a department's teams before the department, so the department is live
when each team's trigger reads it. A team whose department the reading role cannot see, which only a
statement typed by hand as the application role can produce, is filed under the department's id and
names the team by its own short name, so the entry is still written rather than refused.

**The action is `organisation`, which `0062` added**, so the action list is not touched. The subject
grammar gains `department` and `scope`, superseding `0061`'s, which is the one in the database.

**No grant, because the application already holds exactly what the store uses.** `0003` granted
`brain_app` SELECT, INSERT and UPDATE on all three tables and `0045` gave each a read, an insert and
an update policy. The store reads, inserts, renames and retires and never deletes, and no role holds
DELETE on any of them. The triggers append to the ledger as every trigger since `0003` does.

**The append is `0003`'s, three more copies of the block `0059` carries**, for the reason `0047`
gives against editing a function every grant in production goes through.

**The downgrade keeps what the ledger already holds**, for the reason `0026` gives: the subject
grammar goes back `NOT VALID`, so an entry already filed under `department:` or `scope:` stays and
no new one is accepted, and the triggers go, so nothing tries to write one.

Task ids: M27.11.1
"""

from __future__ import annotations

from alembic import op

revision = "0086"
# The newest migration on origin/main when this was rebased, a884c6c. Nothing after 0061 touches
# `gate.department`, `gate.team`, `gate.scope` or the ledger's subject grammar.
down_revision = "0083"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0061`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|department|entity|erasure|grant|leash"
    "|legal_hold|memory|principal|retention|routing|scope|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|erasure|grant|leash|legal_hold"
    "|memory|principal|retention|routing|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0061`'s subject grammar, which is the one in the database.
SUPERSEDES: dict[str, str] = {NARROWER_SUBJECTS: WIDENED_SUBJECTS}

#: The word a trigger writes beside an actor nobody named, as `0003` and `0059` write it.
INFERRED = "inferred"

#: The columns whose movement is not a change anybody audits: the identity, which is the subject,
#: and the three instants, of which retirement is recorded as a change of its own. `name` is left
#: out of a department's and a team's too, because moving it is recorded as `renamed`.
NOT_A_CHANGE: tuple[str, ...] = ("id", "created_at", "updated_at", "deleted_at")
RECORDED_AS_A_RENAME: tuple[str, ...] = ("name",)

#: The append every trigger below makes, as `0059` writes it. `{subject}` and `{details}` are the
#: two expressions that differ; the actor and the action are the same in all three.
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
            v_seq, v_at, v_actor, 'organisation', {subject}, v_ent_hash,
            v_trace, {details}, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, 'organisation', {subject},
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

#: Which changes one row's insert or update is, in order: created, renamed, changed, retired.
#: `__IGNORED__` is the columns whose movement is not `changed`. The name is read through `to_jsonb`
#: rather than as `NEW.name`, so one block serves a scope too: a scope has no `name` column, the two
#: sides are both null, and a scope is never renamed.
_CHANGES = """
    v_actor := COALESCE(v_supplied, session_user::text);
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'created'::text;
        IF NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    ELSE
        IF (to_jsonb(OLD) -> 'name') IS DISTINCT FROM (to_jsonb(NEW) -> 'name') THEN
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

#: One change's details, before the append: the change, the columns a hand-typed change moved, and
#: the mark for an actor nobody named. `__MORE__` is what one table adds.
_DETAILS = (
    """
    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i])__MORE__;
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


def _trigger_function(
    name: str, declare: str, prelude: str, ignored: tuple[str, ...], more: str
) -> str:
    """One trigger function, filled with `str.replace` so no SQL is built from a value."""
    return (
        f"\nCREATE FUNCTION {name}() RETURNS trigger\nLANGUAGE plpgsql AS $$\nDECLARE"
        + declare
        + _DECLARE
        + "BEGIN"
        + prelude
        + _CHANGES.replace("__IGNORED__", _quoted(ignored))
        + _DETAILS.replace("__MORE__", more)
        + _APPEND.format(subject="v_subject", details="v_details")
        + "    END LOOP;\n    RETURN NULL;\nEND;\n$$\n"
    )


#: A department created, renamed, changed by hand or retired, under its own slug.
DEPARTMENT_TRIGGER_FUNCTION = _trigger_function(
    "gate.record_department_change",
    "\n    v_subject text := 'department:' || NEW.slug;",
    "",
    NOT_A_CHANGE + RECORDED_AS_A_RENAME,
    "",
)

#: A team created, renamed, changed by hand or retired, under its department's slug with its path.
TEAM_TRIGGER_FUNCTION = _trigger_function(
    "gate.record_team_change",
    "\n    v_department text;\n    v_subject text;\n    v_team text;",
    """
    SELECT d.slug INTO v_department FROM gate.department d WHERE d.id = NEW.department_id;
    IF v_department IS NULL THEN
        v_subject := 'department:' || NEW.department_id::text;
        v_team := NEW.slug;
    ELSE
        v_subject := 'department:' || v_department;
        v_team := v_department || '.' || NEW.slug;
    END IF;""",
    NOT_A_CHANGE + RECORDED_AS_A_RENAME,
    " || jsonb_build_object('team', v_team)",
)

#: A scope created, changed by hand or retired, under its own slug. Never renamed.
SCOPE_TRIGGER_FUNCTION = _trigger_function(
    "gate.record_scope_change",
    "\n    v_subject text := 'scope:' || NEW.slug;",
    "",
    NOT_A_CHANGE,
    "",
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER department_is_audited
        AFTER INSERT OR UPDATE ON gate.department
        FOR EACH ROW EXECUTE FUNCTION gate.record_department_change()
    """,
    """
    CREATE TRIGGER team_is_audited
        AFTER INSERT OR UPDATE ON gate.team
        FOR EACH ROW EXECUTE FUNCTION gate.record_team_change()
    """,
    """
    CREATE TRIGGER scope_is_audited
        AFTER INSERT OR UPDATE ON gate.scope
        FOR EACH ROW EXECUTE FUNCTION gate.record_scope_change()
    """,
)


def upgrade() -> None:
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")
    op.execute(DEPARTMENT_TRIGGER_FUNCTION)
    op.execute(TEAM_TRIGGER_FUNCTION)
    op.execute(SCOPE_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER scope_is_audited ON gate.scope")
    op.execute("DROP TRIGGER team_is_audited ON gate.team")
    op.execute("DROP TRIGGER department_is_audited ON gate.department")
    op.execute("DROP FUNCTION gate.record_scope_change()")
    op.execute("DROP FUNCTION gate.record_team_change()")
    op.execute("DROP FUNCTION gate.record_department_change()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs", postgresql_not_valid=True
    )
