"""The skill library gets its tables, and every import, decision and assignment reaches the ledger.

`brain.tools.skills` decided in M12.2 what an imported skill is, that a named person approves one,
and that only an approved skill whose bytes have not moved can be pinned to an agent. Nothing
stored one, so `brain.skill_routes` answered every reader that a skill could not be added,
approved or assigned from the console. This migration is the three tables that answer, the ledger
member and subject kind they are recorded under, and the three triggers that record them.
`brain.tables.skill` holds the argument for the columns and the keys.

**Three tables, SELECT and INSERT only.** A skill as it arrived, a decision about its bytes, and an
assignment of those bytes to an agent. None is edited or retired, for `0052`'s reason about a
decision: a row rewritten is a record whose author changed afterwards. A second import of the same
bytes, a second decision about them, is refused by a key and writes nothing, and PostgreSQL fires
no row trigger for a row it did not insert, so it appends nothing either.

**Read by the application whole, written only in the session's own name.** Who may see the library
is `brain.console.skill_library`'s decision over the Skills screen's grant, so each select policy
admits every row, which is `0052`'s shape for a table the console narrows. Each insert policy
admits a row whose actor column is the session's principal, the way `0055` admits an automation, so
a request cannot add a skill, decide about one or assign one in somebody else's name. A setting
that is unset admits nothing.

**Nobody decides about a skill they added, in the table's own definition.** `nobody_decides_their_
own_import` compares the decider with the importer the row carries, and the composite key holds
that copy to the skill row, so the importer cannot be misstated to get past the check. An
assignment names the decision `approved` through a key, so bytes nobody approved cannot be
assigned by a statement that never went through the console.

**`skill` is a new ledger member and a new subject kind**, argued in
`brain.audit.ledger.AuditAction`. The action list gains one member, replacing `0054`'s, and the
subject grammar gains one kind, replacing `0054`'s, which are the two in the database.

**An assignment is recorded as `compose_change` about the agent**, which is what that member is
for, with the part `skills`, the skill's folded name as the reference, and the reason code
`skill_assign`, exactly the details `brain.audit.record.AuditRecorder.compose_change` writes for
`brain.console.skill_library.ledger_reference`. The name is folded because the ledger admits a
field name and a hyphen is not one, which that module argues. An assignment that
replaces another version of the same skill records the detachment first, with `skill_replace`, so
"when did this agent stop running the old bytes" has an entry of its own.

**The append is `0003`'s, another copy of that block**, beside `0047`'s to `0055`'s, for the reason
`0047` gives against editing a function every grant in production goes through. The actor is read
off the row's own column; the reach's digest and the trace come from the settings the store sets
in the same transaction.

**The downgrade can fail, which is correct**, for the reason `0026` gives: narrowing the action list
and the subject grammar is refused once an entry carries the new values. The tables go with it, and
their ledger entries stay, because nothing may delete one.

Task ids: M42.6.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.skill", "agent.skill_review", "agent.skill_assignment")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.skill` and `brain.audit.ledger` by
#: `tests/unit/test_skill_store.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
DIGEST = r"^[0-9a-f]{64}$"
SKILL_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,79}$"
VERSION_PATTERN = r"^[0-9]+[.][0-9]+[.][0-9]+$"
PRINCIPAL_ID_CHARS = 128

#: The details the assignment trigger writes, as `AuditRecorder.compose_change` spells them.
#: Written out literally in the function below as well; a test holds the two equal.
PART = "skills"
ASSIGN_REASON = "skill_assign"
REPLACE_REASON = "skill_replace"

#: Alphabetical, matching how `tables.identity.one_of` sorts.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'credential', "
    "'deny', 'entity_merge', 'grant', 'leash_change', 'legal_hold', 'publish', 'record_read', "
    "'retention', 'revoke', 'session_end', 'sign_in', 'skill')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'credential', "
    "'deny', 'entity_merge', 'grant', 'leash_change', 'legal_hold', 'publish', 'record_read', "
    "'retention', 'revoke', 'session_end', 'sign_in')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0054`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|grant|leash|legal_hold|principal"
    "|retention|session|skill):[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|grant|leash|legal_hold|principal"
    "|retention|session):[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0054`'s action list and subject grammar.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.skill_review ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.skill_assignment ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_readable ON agent.skill
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_added_in_the_sessions_name ON agent.skill
        FOR INSERT TO brain_app
        WITH CHECK (submitted_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY skill_review_readable ON agent.skill_review
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_review_decided_in_the_sessions_name ON agent.skill_review
        FOR INSERT TO brain_app
        WITH CHECK (decided_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY skill_assignment_readable ON agent.skill_assignment
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_assignment_made_in_the_sessions_name ON agent.skill_assignment
        FOR INSERT TO brain_app
        WITH CHECK (assigned_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.skill TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_review TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_assignment TO brain_app",
)

#: The append every trigger below makes, as `0003` and `0054` write it. `{actor}`, `{action}`,
#: `{subject}` and `{details}` are the four expressions that differ.
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
            v_seq, v_at, {actor}, '{action}', {subject}, v_ent_hash,
            v_trace, {details}, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, {actor}, '{action}', {subject},
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
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

#: A skill added: the importer, the skill's name, and the bytes.
SKILL_IMPORT_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_skill_import() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'skill:' || NEW.name;
    v_details jsonb := jsonb_build_object('change', 'imported', 'digest', NEW.digest);"""
    + _DECLARE
    + """BEGIN"""
    + _APPEND.format(
        actor="NEW.submitted_by", action="skill", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

#: The name of the skill a decision's key names. The key into `agent.skill` guarantees the row.
_SKILL_NAME_OF_THE_DECISION = """
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;"""

#: A decision: the decider, the name of the skill the key names, the decision and the bytes.
SKILL_REVIEW_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_skill_review() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text;
    v_details jsonb := jsonb_build_object('change', NEW.decision, 'digest', NEW.digest);"""
    + _DECLARE
    + """BEGIN"""
    + _SKILL_NAME_OF_THE_DECISION
    + _APPEND.format(
        actor="NEW.decided_by", action="skill", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

#: An assignment: the replaced version detached first when there was one, then this one attached.
SKILL_ASSIGNMENT_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_skill_assignment() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.agent_id;
    v_directions text[] := ARRAY[]::text[];
    v_reasons text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF NEW.replaces_digest IS NOT NULL THEN
        v_directions := v_directions || 'detached'::text;
        v_reasons := v_reasons || 'skill_replace'::text;
    END IF;
    v_directions := v_directions || 'attached'::text;
    v_reasons := v_reasons || 'skill_assign'::text;

    FOR i IN 1 .. array_length(v_directions, 1) LOOP
        v_details := jsonb_build_object(
            'part', 'skills', 'reference', replace(NEW.skill_name, '-', '_'),
            'direction', v_directions[i], 'reason_code', v_reasons[i]
        );"""
    + _APPEND.format(
        actor="NEW.assigned_by", action="compose_change", subject="v_subject", details="v_details"
    )
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER skill_import_is_audited
        AFTER INSERT ON agent.skill
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_import()
    """,
    """
    CREATE TRIGGER skill_review_is_audited
        AFTER INSERT ON agent.skill_review
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_review()
    """,
    """
    CREATE TRIGGER skill_assignment_is_audited
        AFTER INSERT ON agent.skill_assignment
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_assignment()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "skill",
        sa.Column("digest", sa.String(64), primary_key=True, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.String(400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tools", postgresql.JSONB(), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_location", sa.String(400), nullable=False),
        sa.Column("source_content_digest", sa.String(64), nullable=False),
        sa.Column("submitted_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"digest ~ '{DIGEST}'", name="digest_shape"),
        sa.CheckConstraint(f"name ~ '{SKILL_NAME_PATTERN}'", name="name_shape"),
        sa.CheckConstraint(f"version ~ '{VERSION_PATTERN}'", name="version_shape"),
        sa.CheckConstraint("length(btrim(description)) > 0", name="description_present"),
        sa.CheckConstraint("jsonb_typeof(tools) = 'array'", name="tools_are_a_list"),
        sa.CheckConstraint("source_kind = 'upload'", name="source_is_an_upload"),
        sa.CheckConstraint("length(btrim(source_location)) > 0", name="source_location_present"),
        sa.CheckConstraint(f"source_content_digest ~ '{DIGEST}'", name="source_digest_shape"),
        sa.CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_is_an_identifier"),
        sa.UniqueConstraint("digest", "submitted_by", name="uq_skill_digest_submitted_by"),
        sa.UniqueConstraint("digest", "name", name="uq_skill_digest_name"),
        schema="agent",
    )
    op.create_table(
        "skill_review",
        sa.Column("digest", sa.String(64), primary_key=True, nullable=False),
        sa.Column("submitted_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')", name="decision_is_approved_or_rejected"
        ),
        sa.CheckConstraint(f"decided_by ~ '{IDENTIFIER}'", name="decided_by_is_an_identifier"),
        sa.CheckConstraint("decided_by <> submitted_by", name="nobody_decides_their_own_import"),
        sa.UniqueConstraint("digest", "decision", name="uq_skill_review_digest_decision"),
        sa.ForeignKeyConstraint(
            ["digest", "submitted_by"],
            ["agent.skill.digest", "agent.skill.submitted_by"],
        ),
        schema="agent",
    )
    op.create_table(
        "skill_assignment",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("skill_name", sa.String(80), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("approval", sa.String(16), server_default=sa.text("'approved'"), nullable=False),
        sa.Column("replaces_digest", sa.String(64), nullable=True),
        sa.Column("assigned_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint("approval = 'approved'", name="only_an_approved_skill_is_assigned"),
        sa.CheckConstraint(
            f"replaces_digest IS NULL OR (replaces_digest ~ '{DIGEST}' "
            "AND replaces_digest <> digest)",
            name="replaces_another_version",
        ),
        sa.CheckConstraint(f"assigned_by ~ '{IDENTIFIER}'", name="assigned_by_is_an_identifier"),
        sa.ForeignKeyConstraint(
            ["digest", "approval"],
            ["agent.skill_review.digest", "agent.skill_review.decision"],
        ),
        sa.ForeignKeyConstraint(
            ["digest", "skill_name"],
            ["agent.skill.digest", "agent.skill.name"],
        ),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")
    op.execute(SKILL_IMPORT_TRIGGER_FUNCTION)
    op.execute(SKILL_REVIEW_TRIGGER_FUNCTION)
    op.execute(SKILL_ASSIGNMENT_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER skill_assignment_is_audited ON agent.skill_assignment")
    op.execute("DROP TRIGGER skill_review_is_audited ON agent.skill_review")
    op.execute("DROP TRIGGER skill_import_is_audited ON agent.skill")
    op.execute("DROP FUNCTION agent.record_skill_assignment()")
    op.execute("DROP FUNCTION agent.record_skill_review()")
    op.execute("DROP FUNCTION agent.record_skill_import()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", NARROWER_ACTIONS, schema="obs")
    # The policies and the grants go with the tables, in the order their keys need.
    op.drop_table("skill_assignment", schema="agent")
    op.drop_table("skill_review", schema="agent")
    op.drop_table("skill", schema="agent")
