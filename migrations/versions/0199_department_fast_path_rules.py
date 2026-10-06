"""A fast-lane rule may belong to a department, and a rule is written in its writer's name.

M6.5.1 asks that a department's administrator add, test and retire a fast-lane rule for their own
department from the console, and that it answer from the next request. `0019` built the rule
table for the whole install: one live rule per template, written by anybody holding the
application role, and read once at start. This migration is the table's half of the change;
`brain.gate.rule_store` reads the rules on every question now and `brain.rule_routes` is the
console's surface. `brain.tables.fast_lane` holds the argument for the column.

**`gate.fast_path_rule.department`**, nullable and held to the department slug grammar. Null is a
rule the whole install asks with, which is every rule an install already holds, so nothing that
answers today changes. A department's slug is a rule only that department's askers are matched
against. Nullable rather than defaulted, because no department is the honest description of a
rule nobody scoped, and a default department would hand an existing rule to whichever department
the default named.

**One live rule per template per department.** `0019`'s index admitted one live rule per
template, so a second department writing the words the first had written would be refused, and
the refusal would tell it the first department had written them. The index is replaced by one
over the template and the department with nulls not distinct, so each department holds its own
words and the rules the install asks with are still one per template.

**That index refuses nothing the previous release could write, and the reason is not the
compatibility gate's.** `brain.deployment.compatibility` passes a unique index naming a column
this body adds, on the argument that nulls are distinct and so the previous release's rows are
never compared. With nulls not distinct they are compared, so that argument does not hold here.
The one that does: the previous release writes no department, so every row it writes has a null
there, and among those rows this index is `0019`'s index exactly. Anything `0019`'s schema
accepted from the previous release, this one accepts. An expression over `coalesce(department,
'')` would say the same thing and is not what the gate can read, so it would be refused for a
narrowing it is not. Measured: `breaking_changes` of this file is empty, which
`tests/unit/test_rule_routes.py` holds.

**A rule is written in the name of the person writing it.** `0019`'s insert policy was
`WITH CHECK (true)`, so any session of the application role could insert a rule naming anybody
as its author, and `created_by` is the only accountability a rule answering with no model has.
The policy now requires `created_by` to be the `brain.actor_id` the transaction set, which is
`brain.tables.audit.attributed_to`'s setting every console write already runs first. Which
department a person may write is the grant's question and is decided by the routes at the
grant's scope, as `brain.classification_routes` decides it for an uploaded table; this table
holds the author to the truth, which is the part a route cannot vouch for about a row that
arrived some other way. The compatibility gate reads a policy replaced in one body as
unreadable rather than safe, so the reason it takes nothing from the previous release is
written here: that release writes a rule as the application role only from the install
acceptance checks, each of which runs `Harness.attributed()` and names the same actor in
`created_by`, and the seed and the demo write as the table's owner, whom no policy binds.

**A live rule's words are fixed, by a trigger rather than a grant.** `0045` left the update
policy retire-only for a row's `deleted_at`, and the application role still holds `UPDATE` on every
column, so a statement that kept a rule live could change its template, and "which rule answered
that question in March" would name a row that no longer said what it said in March. Narrowing the
grant to `deleted_at` was written here first and is refused by `brain.deployment.compatibility`,
rightly by its own rule: a `REVOKE` narrows what the previous release may do, and the gate admits
no per-file waiver. `gate.rule_words_are_fixed` refuses, before it happens, any update that keeps
a rule live and changes a column other than `deleted_at` and `updated_at`, whoever runs it. No
release writes a rule's words after adding it (`brain.gate.rule_store.StoredRules` adds and
retires, and every acceptance helper inserts), so the previous release loses nothing, which the
gate reads and passes. See `A_LIVE_RULES_WORDS_ARE_FIXED`.

**Every rule added and retired is on the ledger, under whoever did it.**
`gate.record_fast_path_rule` appends a `setting` entry under `setting:fast_path_rule.<id>` on an
addition and on a retirement, naming the change, the department and the answering source, entity
and fields, and the template only as a sha256 digest, because the ledger refuses anything that
is not a name or a digest. The actor is the transaction's `brain.actor_id`, and an addition with
none set (the seed and the demo, writing as the table's owner) is marked inferred from
`created_by`, as `0109` marks a group rule.
A retirement with no actor set is refused: the retirer is the one fact a retired row cannot
otherwise say, and inferring it from the author would name the wrong person. See
`A_RETIREMENT_NAMES_ITS_RETIRER`.

**The downgrade** drops both triggers and their functions, puts back `0019`'s index and insert
policy and drops the column. It is refused
while two live rules share a template, which only department rules can have made, so a
downgrade never builds an index the rows it finds would violate.

Task ids: M6.5.1

Revision ID: 0199
Revises: 0198
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0199"
# The head of this branch when it was written; re-pointed at whichever migration is the head
# when it lands, since nothing here depends on anything after 0045.
down_revision = "0198"
branch_labels = None
depends_on = None

#: No table is created: a column, an index, a policy and a grant change on `0019`'s table.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

#: `brain.knowledge.search.SLUG_SQL_PATTERN`, copied for the reason `0009` gives about reading
#: live code from a migration, and held equal to `brain.tables.fast_lane` by
#: `tests/unit/test_rule_routes.py`.
DEPARTMENT_IS_A_SLUG = "department IS NULL OR department ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'"

#: `brain.tables.fast_lane.NAME_CHARS`, copied.
NAME_CHARS = 60

#: The author, as the transaction's own setting names them.
ACTOR = "current_setting('brain.actor_id', true)"

UPGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY fast_path_rule_writable ON gate.fast_path_rule",
    f"""
    CREATE POLICY fast_path_rule_written_in_the_writers_name ON gate.fast_path_rule
        FOR INSERT TO brain_app
        WITH CHECK (created_by = {ACTOR})
    """,
)

#: `0019`'s, put back exactly.
DOWNGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY fast_path_rule_written_in_the_writers_name ON gate.fast_path_rule",
    """
    CREATE POLICY fast_path_rule_writable ON gate.fast_path_rule
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: Why a live rule's words are fixed by a trigger.
A_LIVE_RULES_WORDS_ARE_FIXED = (
    "A rule that answered a question is named by its id in that request's record, so a live "
    "rule's words cannot change under its id: change them by retiring it and adding another. "
    "A trigger refuses it rather than a narrowed grant, because a REVOKE narrows the previous "
    "release and the compatibility gate refuses that in one release."
)

#: Why a retirement with no actor set is refused.
A_RETIREMENT_NAMES_ITS_RETIRER = (
    "A retired rule's row says who wrote it and not who retired it, so the ledger entry is the "
    "only record of the retirer, and a retirement with no brain.actor_id set is refused rather "
    "than inferred from the author, who may be somebody else."
)

#: The columns a live rule may change: its retirement and the stamp that comes with it.
MAY_CHANGE: tuple[str, ...] = ("deleted_at", "updated_at")

#: Every other column of the table, which a live rule keeps as written.
FIXED: tuple[str, ...] = (
    "rule_id",
    "template",
    "slot",
    "source",
    "entity",
    "match_field",
    "answer_field",
    "created_by",
    "department",
    "created_at",
)

WORDS_ARE_FIXED_FUNCTION = (
    """
CREATE FUNCTION gate.rule_words_are_fixed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.deleted_at IS NULL AND ("""
    + ", ".join(f"NEW.{one}" for one in FIXED)
    + ") IS DISTINCT FROM ("
    + ", ".join(f"OLD.{one}" for one in FIXED)
    + """) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'a live rule''s words are fixed; retire it and add another',
            ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$
"""
)

WORDS_ARE_FIXED_TRIGGER = """
CREATE TRIGGER rule_words_are_fixed
    BEFORE UPDATE ON gate.fast_path_rule
    FOR EACH ROW EXECUTE FUNCTION gate.rule_words_are_fixed()
"""

#: `0120`'s block over one change, copied for `0046`'s reason: a migration describes the database
#: it built.
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

RULE_SUBJECT_PREFIX = "setting:fast_path_rule."
RULE_AUDIT_DETAILS: tuple[str, ...] = (
    "change",
    "source",
    "department",
    "answers_from",
    "entity",
    "match_field",
    "answer_field",
    "template_digest",
)

RULE_AUDIT_FUNCTION = """
CREATE FUNCTION gate.record_fast_path_rule() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, gate
AS $$
DECLARE
    v_action text := 'setting';
    v_actor text;
    v_supplied text;
    v_subject text := '__PREFIX__' || NEW.rule_id;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    IF TG_OP = 'INSERT' THEN
        IF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        END IF;
        v_details := jsonb_build_object('change', 'added');
        v_actor := COALESCE(v_supplied, NEW.created_by);
        IF v_supplied IS NULL THEN
            v_details := v_details || jsonb_build_object('actor', 'inferred');
        END IF;
    ELSE
        IF OLD.deleted_at IS NOT NULL OR NEW.deleted_at IS NULL THEN
            RETURN NULL;
        END IF;
        IF v_supplied IS NULL THEN
            RAISE EXCEPTION USING
                MESSAGE = 'a rule is retired in somebody''s name; set brain.actor_id first',
                ERRCODE = 'insufficient_privilege';
        END IF;
        v_details := jsonb_build_object('change', 'retired');
        v_actor := v_supplied;
    END IF;
    v_details := v_details || jsonb_build_object(
        'source', 'fast_path_rule',
        'department', COALESCE(NEW.department, 'install'),
        'answers_from', NEW.source,
        'entity', NEW.entity,
        'match_field', NEW.match_field,
        'answer_field', NEW.answer_field,
        'template_digest', encode(sha256(convert_to(NEW.template, 'UTF8')), 'hex')
    );
__APPEND__
    RETURN NULL;
END;
$$
""".replace("__APPEND__", _APPEND).replace("__PREFIX__", RULE_SUBJECT_PREFIX)

RULE_AUDIT_TRIGGER = """
CREATE TRIGGER fast_path_rule_is_audited
    AFTER INSERT OR UPDATE ON gate.fast_path_rule
    FOR EACH ROW EXECUTE FUNCTION gate.record_fast_path_rule()
"""

TRIGGERS: tuple[tuple[str, str, str], ...] = (
    ("rule_words_are_fixed", "gate.fast_path_rule", "gate.rule_words_are_fixed()"),
    ("fast_path_rule_is_audited", "gate.fast_path_rule", "gate.record_fast_path_rule()"),
)

#: The downgrade's refusal, for rows the one-per-template index would not admit.
REFUSE_TWO_LIVE_RULES_IN_ONE_TEMPLATE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT template FROM gate.fast_path_rule
         WHERE deleted_at IS NULL
         GROUP BY template
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'two live rules share a template; a downgrade would refuse its own index';
    END IF;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in UPGRADE_RLS[1:])
    assert all("brain_fastlane" not in statement for statement in UPGRADE_RLS)
    op.add_column(
        "fast_path_rule",
        sa.Column("department", sa.String(NAME_CHARS), nullable=True),
        schema="gate",
    )
    # A bare constraint name: alembic applies the metadata's naming convention.
    op.create_check_constraint(
        "department_is_a_slug", "fast_path_rule", DEPARTMENT_IS_A_SLUG, schema="gate"
    )
    op.drop_index("uq_fast_path_rule_template_live", table_name="fast_path_rule", schema="gate")
    op.create_index(
        "uq_fast_path_rule_template_department_live",
        "fast_path_rule",
        ["template", "department"],
        schema="gate",
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    for statement in UPGRADE_RLS:
        op.execute(statement)
    op.execute(WORDS_ARE_FIXED_FUNCTION)
    op.execute(WORDS_ARE_FIXED_TRIGGER)
    op.execute(RULE_AUDIT_FUNCTION)
    op.execute(RULE_AUDIT_TRIGGER)


def downgrade() -> None:
    op.execute(REFUSE_TWO_LIVE_RULES_IN_ONE_TEMPLATE)
    op.execute("DROP TRIGGER fast_path_rule_is_audited ON gate.fast_path_rule")
    op.execute("DROP FUNCTION gate.record_fast_path_rule()")
    op.execute("DROP TRIGGER rule_words_are_fixed ON gate.fast_path_rule")
    op.execute("DROP FUNCTION gate.rule_words_are_fixed()")
    for statement in DOWNGRADE_RLS:
        op.execute(statement)
    op.drop_index(
        "uq_fast_path_rule_template_department_live", table_name="fast_path_rule", schema="gate"
    )
    op.create_index(
        "uq_fast_path_rule_template_live",
        "fast_path_rule",
        ["template"],
        schema="gate",
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # The column's check goes with the column.
    op.drop_column("fast_path_rule", "department", schema="gate")
