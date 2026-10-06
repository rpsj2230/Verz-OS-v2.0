"""A correction carrying the right answer is held as a candidate, and decided as a new version is.

`brain.knowledge.candidates` argues the rules. This is what the database holds for them: two tables,
three functions, two triggers and one widened task kind.

**`know.learning_candidate`: what a person said the right answer is, about one document.** The
words are the person's own, so nothing but the people whose corrections it holds and the people who
may decide it reads the row: the policy admits a reader whose correction it holds, the document's
steward, and whoever `app.deciding_departments` names the document's department for, which
`brain.knowledge.lifecycle_store` sets from `admin:knowledge` alone. A pending candidate is unique
per group key, which is the document and the words' key, so the same fix is one row.

**`know.candidate_evidence`: one row per correction that proposed or grew a candidate.** Keyed by
the corrected answer itself, its conversation and its instant, so one answer is evidence once and
ever, and a rejected candidate is not proposed again from it. The principal is on the row, because
the four-eyes rule reads it.

**Nothing is written into either table but by `know.propose_correction`.** The application role
holds no INSERT on them. The function takes the proposer from `app.principal_id`, refuses a
conversation that is not theirs and a document that is not live, adds the evidence once, and opens
a candidate or grows the pending one with the same key, which a reader whose policy cannot see
somebody else's pending candidate could not do through the table. A decision is an UPDATE of four
columns under a policy that admits the deciders and refuses anybody whose correction it holds,
asked through `know.candidate_proposed_by`, which reads the evidence past its policy so the refusal
cannot be avoided by not being able to see it.

**The steward is asked, by the database.** A new candidate opens a `correction_proposed` task for
the document's steward, unless the steward is the person who proposed it, and a decision closes
it. Each candidate raised and decided is appended to the ledger as a `setting` entry naming the
candidate, its document and what happened, never the words.

Every function that reads past a policy is `SECURITY DEFINER` with its search path pinned and every
object named with its schema, the arrangement `0040` and `0120` make. No table here is given DELETE.

Revision ID: 0198
Revises: 0197
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0198"
# The newest migration on origin/main when this was written; re-pointed when it is pushed.
down_revision = "0197"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("know.learning_candidate", "know.candidate_evidence")

APP_ROLE = "brain_app"

#: `brain.knowledge.item.ITEM_ID_PATTERN`, as `0120` copies it.
REFERENCE_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"

#: `brain.knowledge.candidates.CandidateState`, sorted, held equal by a test.
CANDIDATE_STATES: tuple[str, ...] = ("approved", "pending", "rejected")

#: `brain.knowledge.lifecycle.TaskKind`, sorted, held equal by a test: `0120`'s and this one's.
TASK_KINDS: tuple[str, ...] = (
    "correction_proposed",
    "promotion_decided",
    "reverify",
    "solution_decided",
    "steward_named",
)
#: `0120`'s list, which the downgrade narrows back to.
TASK_KINDS_BEFORE: tuple[str, ...] = (
    "promotion_decided",
    "reverify",
    "solution_decided",
    "steward_named",
)

#: The widths `brain.knowledge.candidates` declares, held equal by the shape test.
WORDS_CHARS = 2000
REASON_CHARS = 400
GROUP_KEY_CHARS = 64

DECIDING_SETTING = "app.deciding_departments"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(one) for one in values)})"


_PRINCIPAL = "current_setting('app.principal_id', true)"

# ------------------------------------------------------------------ the functions
#: Whether this person may decide a candidate about this document, as the database's second wall:
#: its steward, or a department this person decides in. `lifecycle.Authority.may_act` is the rule;
#: this is the line the table can hold without reading the person's grants.
DECIDES_FUNCTION = """
CREATE FUNCTION know.candidate_decides(p_item character varying, p_principal text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
    SELECT EXISTS (
        SELECT 1 FROM know.item i
         WHERE i.item_id = p_item
           AND i.state IN ('draft', 'published')
           AND (
               i.owner_id = p_principal
               OR i.department = ANY(
                   string_to_array(current_setting('app.deciding_departments', true), ',')
               )
           )
    )
$$
"""

#: Whether this person's correction is among a candidate's evidence, read past the policy.
PROPOSED_BY_FUNCTION = """
CREATE FUNCTION know.candidate_proposed_by(p_candidate character varying, p_principal text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
    SELECT EXISTS (
        SELECT 1 FROM know.candidate_evidence e
         WHERE e.candidate_id = p_candidate AND e.principal_id = p_principal
    )
$$
"""

#: The one write into both tables. Answers the candidate the evidence was added to, or NULL when
#: this answer is already evidence.
PROPOSE_FUNCTION = """
CREATE FUNCTION know.propose_correction(
    p_candidate character varying,
    p_item character varying,
    p_words character varying,
    p_key character varying,
    p_conversation uuid,
    p_answer_at timestamptz
) RETURNS character varying
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
DECLARE
    v_principal text := NULLIF(current_setting('app.principal_id', true), '');
    v_candidate character varying;
BEGIN
    IF v_principal IS NULL THEN
        RAISE EXCEPTION USING
            MESSAGE = 'a correction is proposed in somebody''s name',
            ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM chat.conversation c
         WHERE c.id = p_conversation AND c.principal_id = v_principal
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'a correction is proposed from the proposer''s own conversation',
            ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM know.item i WHERE i.item_id = p_item AND i.state IN ('draft', 'published')
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'a correction is proposed about a document that is still live',
            ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM know.candidate_evidence e
         WHERE e.conversation_id = p_conversation AND e.answer_at = p_answer_at
    ) THEN
        RETURN NULL;
    END IF;
    SELECT c.candidate_id INTO v_candidate
      FROM know.learning_candidate c
     WHERE c.group_key = p_key AND c.state = 'pending'
     FOR UPDATE;
    IF v_candidate IS NULL THEN
        MERGE INTO know.learning_candidate AS t
        USING (SELECT p_candidate AS candidate_id) AS s
           ON t.candidate_id = s.candidate_id
        WHEN NOT MATCHED THEN
            INSERT (candidate_id, item_id, words, group_key, raised_by, raised_at, state)
            VALUES (p_candidate, p_item, p_words, p_key, v_principal, now(), 'pending');
        v_candidate := p_candidate;
    END IF;
    MERGE INTO know.candidate_evidence AS t
    USING (SELECT p_conversation AS conversation_id, p_answer_at AS answer_at) AS s
       ON t.conversation_id = s.conversation_id AND t.answer_at = s.answer_at
    WHEN NOT MATCHED THEN
        INSERT (conversation_id, answer_at, candidate_id, principal_id, at)
        VALUES (p_conversation, p_answer_at, v_candidate, v_principal, now());
    RETURN v_candidate;
END;
$$
"""

FUNCTIONS: tuple[str, ...] = (
    "know.candidate_decides(character varying, text)",
    "know.candidate_proposed_by(character varying, text)",
    "know.propose_correction(character varying, character varying, character varying, "
    "character varying, uuid, timestamptz)",
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT ON know.learning_candidate TO brain_app",
    "GRANT UPDATE (state, decided_by, decided_at, reason, applied_item_id, updated_at) "
    "ON know.learning_candidate TO brain_app",
    "GRANT SELECT ON know.candidate_evidence TO brain_app",
    "GRANT EXECUTE ON FUNCTION know.candidate_decides(character varying, text) TO brain_app",
    "GRANT EXECUTE ON FUNCTION know.candidate_proposed_by(character varying, text) TO brain_app",
    "GRANT EXECUTE ON FUNCTION know.propose_correction(character varying, character varying, "
    "character varying, character varying, uuid, timestamptz) TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE know.learning_candidate ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY candidate_readable ON know.learning_candidate
        FOR SELECT TO brain_app
        USING (
            know.candidate_proposed_by(candidate_id, {_PRINCIPAL})
            OR know.candidate_decides(item_id, {_PRINCIPAL})
        )
    """,
    f"""
    CREATE POLICY candidate_decided_by_nobody_whose_correction_it_holds
        ON know.learning_candidate
        FOR UPDATE TO brain_app
        USING (state = 'pending' AND know.candidate_decides(item_id, {_PRINCIPAL}))
        WITH CHECK (
            state <> 'pending'
            AND decided_by = {_PRINCIPAL}
            AND NOT know.candidate_proposed_by(candidate_id, {_PRINCIPAL})
        )
    """,
    "ALTER TABLE know.candidate_evidence ENABLE ROW LEVEL SECURITY",
    # Written out rather than interpolated: a policy holding a subquery is the shape a linter
    # reads as built SQL, and this one is the product's own text with no value in it.
    """
    CREATE POLICY evidence_readable ON know.candidate_evidence
        FOR SELECT TO brain_app
        USING (
            principal_id = current_setting('app.principal_id', true)
            OR EXISTS (
                SELECT 1 FROM know.learning_candidate c
                 WHERE c.candidate_id = candidate_evidence.candidate_id
                   AND know.candidate_decides(
                       c.item_id, current_setting('app.principal_id', true)
                   )
            )
        )
    """,
)

# ------------------------------------------------------------------ the ledger append
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

CANDIDATE_SUBJECT_PREFIX = "setting:knowledge_candidate."
CANDIDATE_AUDIT_DETAILS: tuple[str, ...] = ("change", "source", "item", "state")

#: Each candidate raised and decided is on the ledger, naming its document and never its words; a
#: decision also opens nothing and closes the steward's task.
CANDIDATE_AUDIT_FUNCTION = """
CREATE FUNCTION know.record_candidate() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
DECLARE
    v_action text := 'setting';
    v_actor text;
    v_supplied text;
    v_subject text := '__PREFIX__' || NEW.candidate_id;
    v_details jsonb;
    v_owner text;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.state = NEW.state THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'INSERT' THEN
        v_details := jsonb_build_object('change', 'raised');
        SELECT i.owner_id INTO v_owner FROM know.item i WHERE i.item_id = NEW.item_id;
        IF v_owner IS NOT NULL AND v_owner <> NEW.raised_by THEN
            MERGE INTO know.steward_task AS t
            USING (SELECT 'correction.' || NEW.candidate_id AS task_id) AS s
               ON t.task_id = s.task_id
            WHEN NOT MATCHED THEN
                INSERT (task_id, principal_id, kind, item_id, actor_id, opened_at)
                VALUES (s.task_id, v_owner, 'correction_proposed', NEW.item_id, NULL, now());
        END IF;
    ELSE
        v_details := jsonb_build_object('change', NEW.state);
        UPDATE know.steward_task SET done_at = now(), updated_at = now()
         WHERE task_id = 'correction.' || NEW.candidate_id AND done_at IS NULL;
    END IF;
    v_details := v_details || jsonb_build_object(
        'source', 'knowledge_candidate',
        'item', NEW.item_id,
        'state', NEW.state
    );
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, NEW.decided_by, NEW.raised_by);
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
""".replace("__APPEND__", _APPEND).replace("__PREFIX__", CANDIDATE_SUBJECT_PREFIX)

CANDIDATE_AUDIT_TRIGGER = """
CREATE TRIGGER candidate_is_audited
    AFTER INSERT OR UPDATE ON know.learning_candidate
    FOR EACH ROW EXECUTE FUNCTION know.record_candidate()
"""

TRIGGERS: tuple[tuple[str, str, str], ...] = (
    ("candidate_is_audited", "know.learning_candidate", "know.record_candidate()"),
)

TASK_KIND_CHECK = _in("kind", TASK_KINDS)
TASK_KIND_CHECK_BEFORE = _in("kind", TASK_KINDS_BEFORE)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert all("INSERT" not in statement for statement in GRANTS)

    op.drop_constraint("kind", "steward_task", schema="know", type_="check")
    op.create_check_constraint("kind", "steward_task", TASK_KIND_CHECK, schema="know")

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "learning_candidate",
        sa.Column("candidate_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("words", sa.String(WORDS_CHARS), nullable=False),
        sa.Column("group_key", sa.String(GROUP_KEY_CHARS), nullable=False),
        sa.Column("raised_by", sa.String(128), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=True),
        sa.Column("applied_item_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"candidate_id ~ '{REFERENCE_PATTERN}'", name="candidate_id_is_a_reference"
        ),
        sa.CheckConstraint(f"item_id ~ '{REFERENCE_PATTERN}'", name="item_id_is_a_reference"),
        sa.CheckConstraint("length(btrim(words)) > 0", name="says_what_is_right"),
        sa.CheckConstraint(f"group_key ~ '^[0-9a-f]{{{GROUP_KEY_CHARS}}}$'", name="group_key"),
        sa.CheckConstraint("length(btrim(raised_by)) > 0", name="raised_by_somebody"),
        sa.CheckConstraint(_in("state", CANDIDATE_STATES), name="state"),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (state = 'pending')",
            name="only_a_decided_candidate_names_its_decider",
        ),
        sa.CheckConstraint(
            "(applied_item_id IS NOT NULL) = (state = 'approved')",
            name="an_approved_candidate_is_a_version",
        ),
        sa.CheckConstraint(
            "(reason IS NOT NULL) = (state = 'rejected') "
            "AND (reason IS NULL OR length(btrim(reason)) > 0)",
            name="a_rejection_keeps_its_reason",
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> raised_by", name="decided_by_somebody_else"
        ),
        sa.UniqueConstraint("applied_item_id", name="applied_once"),
        schema="know",
    )
    op.create_index(
        "ix_learning_candidate_one_pending_per_fix",
        "learning_candidate",
        ["group_key"],
        unique=True,
        schema="know",
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.create_index(
        "ix_learning_candidate_item_state",
        "learning_candidate",
        ["item_id", "state"],
        schema="know",
    )
    op.create_table(
        "candidate_evidence",
        sa.Column("conversation_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("answer_at", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(128),
            sa.ForeignKey("know.learning_candidate.candidate_id"),
            nullable=False,
        ),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="evidence_of_somebody"),
        schema="know",
    )
    op.create_index(
        "ix_candidate_evidence_candidate_id", "candidate_evidence", ["candidate_id"], schema="know"
    )
    op.execute(DECIDES_FUNCTION)
    op.execute(PROPOSED_BY_FUNCTION)
    op.execute(PROPOSE_FUNCTION)
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(CANDIDATE_AUDIT_FUNCTION)
    op.execute(CANDIDATE_AUDIT_TRIGGER)


def downgrade() -> None:
    for name, table, function in TRIGGERS:
        op.execute(f"DROP TRIGGER {name} ON {table}")
        op.execute(f"DROP FUNCTION {function}")
    # The policies read the functions, so they go with the tables first.
    op.drop_table("candidate_evidence", schema="know")
    op.drop_table("learning_candidate", schema="know")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION {function}")
    op.drop_constraint("kind", "steward_task", schema="know", type_="check")
    op.create_check_constraint(
        "kind", "steward_task", TASK_KIND_CHECK_BEFORE, schema="know", postgresql_not_valid=True
    )
