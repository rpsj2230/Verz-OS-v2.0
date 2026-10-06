"""A learned fast-lane rule is held until people promote it, and every question it would have
answered is counted (M39.4.2.3).

`brain.memory.tiers` puts a learned fast-path rule at tier two: proposed, then promoted once enough
independent conversations agree, and `reach_view.tier_two_rows` works out whether one is ready.
Nothing stored the rule a learning proposes, nothing recorded an occurrence, so `may_promote` was
false on every install, and nothing applied a promoted rule. This migration is the tables' half;
`brain.memory.promotion` holds the rules and `brain.memory.promotion_store` the session.

**`mem.learned_rule`: the rule a tier-two learning proposes, held apart from the live rules.** One
row per learning, carrying the rule's words exactly as `gate.fast_path_rule` would and the
department it would answer. It is not a rule row: `gate.fast_path_rule` holds rules that answer
and rules that did, and an install check (M16.3.4) holds that a rule offered for review is in no
row of it. Promotion copies it there, in the promoter's name, with `learned_from` naming the
learning, so the lane that answers it is H's lane unchanged.

**Promoted by one person, or by two when the rule answers with money or a sensitive column,** and
never by whoever proposed it. `needs_two` is decided in Python at the first press
(`brain.memory.promotion.needs_two`) and kept, so the second press is judged by the rule the first
was. The update policy binds the presser to the transaction's `brain.actor_id`, and the checks
refuse a promotion by the proposer and a two-person promotion by one person, so the database holds
the rule even against a statement written elsewhere.

**`mem.rule_occurrence`: one row per learning, conversation and day a question would have used it.**
No principal, for `tiers.Occurrence`'s reason: agreement is about a pattern recurring, and a list
of whose conversations produced it is a note about who the system learns from. The insert policy
admits only an occurrence from the asker's own conversation, asked through `mem.conversation_is_
own`, so a session cannot manufacture agreement out of conversations it does not hold.

**On the ledger.** Each press appends a `setting` entry under `setting:learned_rule.<memory_id>`,
naming the change (`first` or `promoted`), whether two people are needed and the department, and a
press with no actor set is refused.

**`gate.fast_path_rule.learned_from`** joins the columns `0199`'s trigger keeps fixed on a live
rule, so the function is replaced with the longer list.

Task ids: M39.4.2.3

Revision ID: 0206
Revises: 0199
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0206"
# The head of this stack when it was written; re-pointed at whichever migration is the head when
# it lands, since nothing here depends on anything after 0199.
down_revision = "0199"
branch_labels = None
depends_on = None

TABLES: tuple[str, ...] = ("mem.learned_rule", "mem.rule_occurrence")

APP_ROLE = "brain_app"

#: `brain.core.envelope.OBJECT_NAME_PATTERN`, copied for `0009`'s reason.
NAME = "^[a-z][a-z0-9_]*$"
#: `brain.tables.fast_lane`'s widths, copied.
NAME_CHARS = 60
MAX_TEMPLATE_CHARS = 200
PRINCIPAL_CHARS = 128
#: `brain.tables.learning.MEMORY_ID_CHARS`, copied.
MEMORY_ID_CHARS = 26
#: The rule id a promotion writes: a department's slug, the separator and the name, as `0199`.
RULE_ID_CHARS = 128

#: `brain.knowledge.search.SLUG_SQL_PATTERN`, copied as `0199` copies it.
DEPARTMENT_IS_A_SLUG = "department IS NULL OR department ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'"

STATES: tuple[str, ...] = ("held", "awaiting_second", "promoted")

ACTOR = "NULLIF(current_setting('brain.actor_id', true), '')"


def _in(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in values)
    return f"{column} IN ({listed})"


#: Whether a conversation is this asker's own, read past `chat.conversation`'s policy.
CONVERSATION_IS_OWN_FUNCTION = """
CREATE FUNCTION mem.conversation_is_own(p_conversation uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, chat
AS $$
    SELECT EXISTS (
        SELECT 1 FROM chat.conversation c
         WHERE c.id = p_conversation
           AND c.principal_id = NULLIF(current_setting('app.principal_id', true), '')
    )
$$
"""

RLS: tuple[str, ...] = (
    "ALTER TABLE mem.learned_rule ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mem.rule_occurrence ENABLE ROW LEVEL SECURITY",
    # Read by the shadow match on every question and by the review, as `gate.fast_path_rule` is
    # read (`0019`): a rule's words are configuration, and who may promote is the route's grant.
    """
    CREATE POLICY learned_rule_readable ON mem.learned_rule
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY learned_rule_held_when_written ON mem.learned_rule
        FOR INSERT TO brain_app
        WITH CHECK (state = 'held' AND first_by IS NULL AND promoted_by IS NULL)
    """,
    f"""
    CREATE POLICY learned_rule_pressed_in_the_pressers_name ON mem.learned_rule
        FOR UPDATE TO brain_app
        USING (state <> 'promoted')
        WITH CHECK (
            (state = 'awaiting_second' AND first_by = {ACTOR})
            OR (state = 'promoted' AND promoted_by = {ACTOR})
        )
    """,
    "CREATE POLICY rule_occurrence_readable ON mem.rule_occurrence FOR SELECT TO brain_app"
    " USING (true)",
    """
    CREATE POLICY rule_occurrence_from_the_askers_own_conversation ON mem.rule_occurrence
        FOR INSERT TO brain_app
        WITH CHECK (mem.conversation_is_own(conversation_id))
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON mem.learned_rule TO brain_app",
    "GRANT UPDATE (state, needs_two, first_by, first_at, promoted_by, promoted_at, updated_at)"
    " ON mem.learned_rule TO brain_app",
    "GRANT SELECT, INSERT ON mem.rule_occurrence TO brain_app",
    "GRANT EXECUTE ON FUNCTION mem.conversation_is_own(uuid) TO brain_app",
)

#: `0120`'s block over one change, copied for `0046`'s reason.
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

LEARNED_RULE_SUBJECT_PREFIX = "setting:learned_rule."

PRESS_AUDIT_FUNCTION = """
CREATE FUNCTION mem.record_learned_rule() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, mem
AS $$
DECLARE
    v_action text := 'setting';
    v_actor text;
    v_subject text := '__PREFIX__' || NEW.memory_id;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF OLD.state = NEW.state THEN
        RETURN NULL;
    END IF;
    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    IF v_actor IS NULL THEN
        RAISE EXCEPTION USING
            MESSAGE = 'a learned rule is promoted in somebody''s name; set brain.actor_id first',
            ERRCODE = 'insufficient_privilege';
    END IF;
    v_details := jsonb_build_object(
        'change', CASE WHEN NEW.state = 'promoted' THEN 'promoted' ELSE 'first' END,
        'source', 'learned_rule',
        'needs_two', CASE WHEN NEW.needs_two THEN 'yes' ELSE 'no' END,
        'department', COALESCE(NEW.department, 'install'),
        'rule', NEW.rule_id
    );
__APPEND__
    RETURN NULL;
END;
$$
""".replace("__APPEND__", _APPEND).replace("__PREFIX__", LEARNED_RULE_SUBJECT_PREFIX)

PRESS_AUDIT_TRIGGER = """
CREATE TRIGGER learned_rule_press_is_audited
    AFTER UPDATE ON mem.learned_rule
    FOR EACH ROW EXECUTE FUNCTION mem.record_learned_rule()
"""

#: `0199`'s fixed columns, and the learning a promoted rule came from.
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
    "learned_from",
)
FIXED_BEFORE: tuple[str, ...] = FIXED[:-1]


def _words_are_fixed(columns: tuple[str, ...]) -> str:
    return (
        """
CREATE OR REPLACE FUNCTION gate.rule_words_are_fixed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.deleted_at IS NULL AND ("""
        + ", ".join(f"NEW.{one}" for one in columns)
        + ") IS DISTINCT FROM ("
        + ", ".join(f"OLD.{one}" for one in columns)
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


TRIGGERS: tuple[tuple[str, str, str], ...] = (
    ("learned_rule_press_is_audited", "mem.learned_rule", "mem.record_learned_rule()"),
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    op.add_column(
        "fast_path_rule",
        sa.Column("learned_from", sa.String(MEMORY_ID_CHARS), nullable=True),
        schema="gate",
    )
    op.execute(_words_are_fixed(FIXED))

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "learned_rule",
        sa.Column(
            "memory_id",
            sa.String(MEMORY_ID_CHARS),
            sa.ForeignKey("mem.learning.memory_id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("rule_id", sa.String(RULE_ID_CHARS), nullable=False),
        sa.Column("template", sa.String(MAX_TEMPLATE_CHARS), nullable=False),
        sa.Column("slot", sa.String(NAME_CHARS), nullable=False),
        sa.Column("source", sa.String(NAME_CHARS), nullable=False),
        sa.Column("entity", sa.String(NAME_CHARS), nullable=False),
        sa.Column("match_field", sa.String(NAME_CHARS), nullable=False),
        sa.Column("answer_field", sa.String(NAME_CHARS), nullable=False),
        sa.Column("department", sa.String(NAME_CHARS), nullable=True),
        sa.Column("proposed_by", sa.String(PRINCIPAL_CHARS), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("needs_two", sa.Boolean(), nullable=True),
        sa.Column("first_by", sa.String(PRINCIPAL_CHARS), nullable=True),
        sa.Column("first_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(PRINCIPAL_CHARS), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(_in("state", STATES), name="state"),
        sa.CheckConstraint(f"slot ~ '{NAME}'", name="slot_is_a_name"),
        sa.CheckConstraint(f"source ~ '{NAME}'", name="source_is_a_name"),
        sa.CheckConstraint(f"entity ~ '{NAME}'", name="entity_is_a_name"),
        sa.CheckConstraint(f"match_field ~ '{NAME}'", name="match_field_is_a_name"),
        sa.CheckConstraint(f"answer_field ~ '{NAME}'", name="answer_field_is_a_name"),
        sa.CheckConstraint(DEPARTMENT_IS_A_SLUG, name="department_is_a_slug"),
        sa.CheckConstraint(
            "(first_by IS NULL) = (first_at IS NULL) AND (promoted_by IS NULL) = "
            "(promoted_at IS NULL)",
            name="a_press_is_a_person_and_a_time",
        ),
        sa.CheckConstraint(
            "(state = 'held') = (first_by IS NULL AND needs_two IS NULL)",
            name="a_held_rule_is_unpressed",
        ),
        sa.CheckConstraint(
            "(state = 'promoted') = (promoted_by IS NOT NULL)",
            name="only_a_promoted_rule_names_its_promoter",
        ),
        sa.CheckConstraint(
            "state <> 'promoted' OR NOT needs_two OR first_by <> promoted_by",
            name="two_people_are_two_people",
        ),
        sa.CheckConstraint(
            "proposed_by IS NULL OR (first_by IS DISTINCT FROM proposed_by "
            "AND promoted_by IS DISTINCT FROM proposed_by)",
            name="never_promoted_by_its_proposer",
        ),
        schema="mem",
    )
    op.create_index("ix_learned_rule_department", "learned_rule", ["department"], schema="mem")
    op.create_table(
        "rule_occurrence",
        sa.Column(
            "memory_id",
            sa.String(MEMORY_ID_CHARS),
            sa.ForeignKey("mem.learned_rule.memory_id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("conversation_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("on_day", sa.Date(), primary_key=True, nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="mem",
    )
    op.execute(CONVERSATION_IS_OWN_FUNCTION)
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(PRESS_AUDIT_FUNCTION)
    op.execute(PRESS_AUDIT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER learned_rule_press_is_audited ON mem.learned_rule")
    op.execute("DROP FUNCTION mem.record_learned_rule()")
    op.drop_table("rule_occurrence", schema="mem")
    op.drop_index("ix_learned_rule_department", "learned_rule", schema="mem")
    op.drop_table("learned_rule", schema="mem")
    op.execute("DROP FUNCTION mem.conversation_is_own(uuid)")
    op.execute(_words_are_fixed(FIXED_BEFORE))
    op.drop_column("fast_path_rule", "learned_from", schema="gate")
