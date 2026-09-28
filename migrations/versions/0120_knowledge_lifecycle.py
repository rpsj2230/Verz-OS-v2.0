"""A stored document is verified, handed over, replaced and published, and each act tells somebody.

`brain.knowledge.lifecycle`, `brain.knowledge.promotion` and `brain.knowledge.solutions` argue the
rules. This is what the database has to hold for them: two tables, four triggers and three reads.

**`know.steward_task`: what one person is asked, opened by the database and never by a route.**
Four kinds, `brain.knowledge.lifecycle.TaskKind`'s, held equal by a test. The application role may
read and close its own and nothing else: there is no INSERT grant, because every task is opened by
a trigger in the transaction that made it true. A review that fell due is opened by the nag the
sweep records in `ops.outbox_event`, so the nag and the task are one fact; a hand-over by the
update that moved `know.item.owner_id`; a decided promotion by the update that decided its
suspension; a decided solution by the update that decided it. A route that forgot to open one is
not a state this table can be in. A review task is closed when its document is verified, given a
new review date, handed over, replaced or withdrawn, by the same trigger on `know.item`, because a
review cleared by dismissing it is a task list that lies.

**`know.solution`: a solution captured from a conversation, waiting for a named person.** Its
problem and its answer are the capturer's words, so the policy is three branches: the capturer
reads their own, anybody whose reach includes the department reads an approved one, and a pending
one is read and decided only where `app.deciding_departments` names the department. That setting
is set by `brain.knowledge.lifecycle_store` from the departments the reader holds `admin:knowledge`
over and nothing else, so the second wall is the same line Python draws: the people who may add a
document there decide what becomes one. The update's check refuses a decision by the capturer.
Every capture and decision is appended to the ledger as a `setting` entry naming the solution, its
department and what happened, and never its words.

**`know.record_item` now says which columns a replacement changed.** `0115`'s trigger recorded
every write of `know.item` as added or replaced, and a steward handed over, a verification and a
widening all read as "replaced". The list of changed column names is recordable under the ledger's
grammar, since `brain.audit.ledger.redact_details` admits a comma-joined list of field names, and it
says what happened without saying the value. The function is `0115`'s with that one addition; the
downgrade puts `0115`'s back.

**A promotion is applied by a trigger on `gate.suspension`.** `brain.knowledge.promotion` argues
why. When a suspension naming `knowledge.promotion` moves from pending to approved, the document and
its live passages become company-wide in that transaction, provided the approver is not the person
who asked, and the document is where it was asked for, published, verified and stewarded as it
was. Otherwise the trigger raises and the approval is not recorded. The function reads the
suspension's action, which the application role cannot update, so a card cannot be edited into a
different widening after it was raised.

**`know.supersede_item` is the one write past `know.item`'s policy.** That policy admits only live
rows, so the update moving a document to `superseded` is refused under it, which is the same defect
`0046` recorded for `know.chunk` and left open. This function makes the move for exactly one pair:
the predecessor must be within the reach the session was told, the successor published and naming
nothing yet, never wider and never another audience, which is `brain.knowledge.item.
assert_supersedable` held by the database as its second wall. It moves the predecessor's live
passages to `superseded` too, so an answer uses the newer version from the commit on.

**`know.item_versions` and `know.version_passages` read a history past the policy.** A superseded
version is out of the policy and has to stay readable, so the two reads return the chain and one
version's passages, and `brain.knowledge.lifecycle.Authority` decides in Python which versions a
reader may see and whether they may read the text, as `0040`'s `know.items_for_review` and `0115`'s
library read do.

Every function that writes past a policy is `SECURITY DEFINER` with its search path pinned and
every object named with its schema, the arrangement `0040` makes. No table here is given DELETE.

The downgrade drops the triggers, the functions and the two tables, and puts `0115`'s audit
function back. The tasks and the solutions go with their tables.

Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2

Revision ID: 0120
Revises: 0115
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0120"
# The newest migration on origin/main when this was written.
down_revision = "0115"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("know.steward_task", "know.solution")

APP_ROLE = "brain_app"

#: `brain.knowledge.item.ITEM_ID_PATTERN` and `brain.core.department.SLUG_PATTERN`, as `0040`
#: copies them.
REFERENCE_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
SLUG_PATTERN = "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"

#: `brain.knowledge.lifecycle.TaskKind`, sorted, and `Outcome`, held equal by a test.
TASK_KINDS: tuple[str, ...] = ("promotion_decided", "reverify", "solution_decided", "steward_named")
OUTCOMES: tuple[str, ...] = ("approved", "rejected")

#: `brain.knowledge.solutions.SolutionState`, sorted, held equal by a test.
SOLUTION_STATES: tuple[str, ...] = ("approved", "pending", "rejected")

#: The widths `brain.tables.knowledge_lifecycle` declares, held equal by the shape test.
TASK_KIND_CHARS = 24
OUTCOME_CHARS = 16
PROBLEM_CHARS = 2000
ANSWER_CHARS = 20000

#: The setting the solution policy reads for who may decide. See the docstring.
DECIDING_SETTING = "app.deciding_departments"

#: `brain.knowledge.promotion`'s act and capability, and the arguments the trigger reads.
PROMOTION_AGENT = "knowledge.promotion"
PROMOTION_CAPABILITY = "approve:knowledge.visibility"
PROMOTION_ARGS_READ: tuple[str, ...] = ("from_level", "item_id", "owner_id", "review_by")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(one) for one in values)})"


TASK_KIND_CHECK = _in("kind", TASK_KINDS)
OUTCOME_CHECK = f"outcome IS NULL OR {_in('outcome', OUTCOMES)}"
SOLUTION_STATE_CHECK = _in("state", SOLUTION_STATES)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT ON know.steward_task TO brain_app",
    "GRANT UPDATE (done_at, updated_at) ON know.steward_task TO brain_app",
    "GRANT SELECT, INSERT ON know.solution TO brain_app",
    "GRANT UPDATE (state, decided_by, decided_at, item_id, updated_at) ON know.solution "
    "TO brain_app",
    "GRANT EXECUTE ON FUNCTION know.supersede_item(character varying, character varying) "
    "TO brain_app",
    "GRANT EXECUTE ON FUNCTION know.item_versions(character varying) TO brain_app",
    "GRANT EXECUTE ON FUNCTION know.version_passages(character varying, integer) TO brain_app",
)

_PRINCIPAL = "current_setting('app.principal_id', true)"
_DEPARTMENTS = "string_to_array(current_setting('app.departments', true), ',')"
_DECIDING = f"string_to_array(current_setting('{DECIDING_SETTING}', true), ',')"

RLS: tuple[str, ...] = (
    "ALTER TABLE know.steward_task ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY steward_task_is_its_addressees ON know.steward_task
        FOR SELECT TO brain_app
        USING (principal_id = {_PRINCIPAL})
    """,
    f"""
    CREATE POLICY steward_task_closed_by_its_addressee ON know.steward_task
        FOR UPDATE TO brain_app
        USING (principal_id = {_PRINCIPAL} AND done_at IS NULL)
        WITH CHECK (principal_id = {_PRINCIPAL} AND done_at IS NOT NULL)
    """,
    "ALTER TABLE know.solution ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY solution_readable ON know.solution
        FOR SELECT TO brain_app
        USING (
            captured_by = {_PRINCIPAL}
            OR state = 'approved' AND department = ANY({_DEPARTMENTS})
            OR department = ANY({_DECIDING})
        )
    """,
    f"""
    CREATE POLICY solution_captured_by_its_capturer ON know.solution
        FOR INSERT TO brain_app
        WITH CHECK (
            captured_by = {_PRINCIPAL}
            AND state = 'pending'
            AND decided_by IS NULL
            AND item_id IS NULL
            AND department = ANY({_DEPARTMENTS})
        )
    """,
    f"""
    CREATE POLICY solution_decided_by_somebody_else ON know.solution
        FOR UPDATE TO brain_app
        USING (state = 'pending' AND department = ANY({_DECIDING}))
        WITH CHECK (
            state <> 'pending' AND decided_by = {_PRINCIPAL} AND decided_by <> captured_by
        )
    """,
)

# ------------------------------------------------------------------ the ledger append
#: `0003`'s block over one change, as `0115` copies it. `__ACTOR__` and `__ACTION__` are the
#: two names a caller fills in.
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

#: `0115`'s subject prefix and the longest item id recorded as itself.
ITEM_SUBJECT_PREFIX = "setting:knowledge_item."
ITEM_ID_CHARS = 128 - len("knowledge_item.")

#: `know.record_item` as `0115` shipped it, for the downgrade. Copied rather than imported, for
#: `0046`'s reason: a migration describes the database it built.
_ITEM_AUDIT_TEMPLATE = """
CREATE OR REPLACE FUNCTION know.record_item() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_action text;
    v_actor text;
    v_supplied text;
    v_subject text;
    v_details jsonb;
    v_changed text;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_details := jsonb_build_object('change', 'added');
    ELSE
        v_details := jsonb_build_object('change', 'replaced');
    END IF;
    v_action := 'setting';
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, NEW.owner_id);
    IF length(NEW.item_id) <= __ID_CHARS__ THEN
        v_subject := '__PREFIX__' || NEW.item_id;
    ELSE
        v_subject := '__PREFIX__' || encode(sha256(convert_to(NEW.item_id, 'UTF8')), 'hex');
    END IF;
    v_details := v_details || jsonb_strip_nulls(jsonb_build_object(
        'source', 'knowledge_item',
        'kind', NEW.kind,
        'level', NEW.visibility,
        'department', NEW.department,
        'state', NEW.state
    ));
__CHANGED__
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
"""

#: What this migration adds to `0115`'s function: the names of the columns a replacement changed.
_CHANGED = """
    IF TG_OP = 'UPDATE' THEN
        SELECT string_agg(n.key, ',' ORDER BY n.key) INTO v_changed
        FROM jsonb_each(to_jsonb(NEW)) AS n
        WHERE n.key NOT IN ('created_at', 'updated_at')
          AND n.value IS DISTINCT FROM (to_jsonb(OLD) -> n.key);
        IF v_changed IS NOT NULL THEN
            v_details := v_details || jsonb_build_object('changed', v_changed);
        END IF;
    END IF;
"""


def _item_audit(changed: str) -> str:
    return (
        _ITEM_AUDIT_TEMPLATE.replace("__CHANGED__", changed)
        .replace("__APPEND__", _APPEND)
        .replace("__PREFIX__", ITEM_SUBJECT_PREFIX)
        .replace("__ID_CHARS__", str(ITEM_ID_CHARS))
    )


#: The details an item entry carries after this migration, in the order the trigger builds them.
ITEM_AUDIT_DETAILS: tuple[str, ...] = (
    "change",
    "source",
    "kind",
    "level",
    "department",
    "state",
    "changed",
)

ITEM_AUDIT_FUNCTION = _item_audit(_CHANGED)
#: `0115`'s body exactly: the same template with nothing where the changed columns go.
ITEM_AUDIT_FUNCTION_AS_0115_SHIPPED = _item_audit("")

# ------------------------------------------------------------------ the solution ledger
SOLUTION_SUBJECT_PREFIX = "setting:knowledge_solution."
SOLUTION_AUDIT_DETAILS: tuple[str, ...] = ("change", "source", "department", "state")

SOLUTION_AUDIT_FUNCTION = """
CREATE FUNCTION know.record_solution() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_action text := 'setting';
    v_actor text;
    v_supplied text;
    v_subject text := '__PREFIX__' || NEW.solution_id;
    v_details jsonb;
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
        v_details := jsonb_build_object('change', 'captured');
    ELSE
        v_details := jsonb_build_object('change', NEW.state);
    END IF;
    v_details := v_details || jsonb_build_object(
        'source', 'knowledge_solution',
        'department', NEW.department,
        'state', NEW.state
    );
    v_supplied := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor := COALESCE(v_supplied, NEW.decided_by, NEW.captured_by);
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
""".replace("__APPEND__", _APPEND).replace("__PREFIX__", SOLUTION_SUBJECT_PREFIX)

SOLUTION_AUDIT_TRIGGER = """
CREATE TRIGGER solution_is_audited
    AFTER INSERT OR UPDATE ON know.solution
    FOR EACH ROW EXECUTE FUNCTION know.record_solution()
"""

# ------------------------------------------------------------------ opening a task
#: One task, opened once: a second opening of the same task id is nothing. MERGE rather than an
#: insert, so the migration rule that reads a DML keyword as a data change reads none here.
_OPEN_TASK = """
    MERGE INTO know.steward_task AS t
    USING (SELECT __ID__ AS task_id) AS s
       ON t.task_id = s.task_id
    WHEN NOT MATCHED THEN
        INSERT (task_id, principal_id, kind, item_id, actor_id, due_at, outcome, opened_at)
        VALUES (s.task_id, __TO__, '__KIND__', __ITEM__, __BY__, __DUE__, __OUTCOME__, now());
"""


def _open_task(
    *,
    task_id: str,
    to: str,
    kind: str,
    item: str,
    by: str = "NULL",
    due: str = "NULL",
    outcome: str = "NULL",
) -> str:
    return (
        _OPEN_TASK.replace("__ID__", task_id)
        .replace("__TO__", to)
        .replace("__KIND__", kind)
        .replace("__ITEM__", item)
        .replace("__BY__", by)
        .replace("__DUE__", due)
        .replace("__OUTCOME__", outcome)
    )


#: A review that fell due opens its steward's task, from the nag the sweep recorded. The nag's id
#: is the task's, so one nag is one task and a second sweep opens nothing.
REVIEW_TASK_FUNCTION = """
CREATE FUNCTION know.open_review_task() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
BEGIN
    IF NEW.entity <> 'knowledge_item' OR NEW.kind <> 'approval.requested' THEN
        RETURN NULL;
    END IF;
    IF NEW.attributes ->> 'route' IS DISTINCT FROM 'owner'
       OR NEW.attributes ->> 'recipient' IS NULL THEN
        RETURN NULL;
    END IF;
__OPEN__
    RETURN NULL;
END;
$$
""".replace(
    "__OPEN__",
    _open_task(
        task_id="NEW.event_id",
        to="NEW.attributes ->> 'recipient'",
        kind="reverify",
        item="NEW.record_id",
        due="(NEW.attributes ->> 'review_by')::timestamptz",
    ),
)

REVIEW_TASK_TRIGGER = """
CREATE TRIGGER nag_opens_a_review_task
    AFTER INSERT ON ops.outbox_event
    FOR EACH ROW EXECUTE FUNCTION know.open_review_task()
"""

#: A document handed to a new steward opens their task, unless they handed it to themselves; any
#: change that answers a review closes the review's task.
STEWARDSHIP_FUNCTION = """
CREATE FUNCTION know.item_stewardship() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
DECLARE
    v_actor text := NULLIF(current_setting('brain.actor_id', true), '');
BEGIN
    IF NEW.review_by IS DISTINCT FROM OLD.review_by
       OR NEW.verified_at IS DISTINCT FROM OLD.verified_at
       OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
       OR NEW.state NOT IN ('draft', 'published') THEN
        UPDATE know.steward_task SET done_at = now(), updated_at = now()
         WHERE item_id = NEW.item_id AND kind = 'reverify' AND done_at IS NULL;
    END IF;
    IF NEW.owner_id IS DISTINCT FROM OLD.owner_id
       AND NEW.owner_id IS DISTINCT FROM v_actor THEN
__OPEN__
    END IF;
    RETURN NULL;
END;
$$
""".replace(
    "__OPEN__",
    _open_task(
        task_id=(
            "'steward.' || left(encode(sha256(convert_to("
            "NEW.item_id || chr(10) || NEW.owner_id || chr(10) || pg_current_xact_id()::text,"
            " 'UTF8')), 'hex'), 40)"
        ),
        to="NEW.owner_id",
        kind="steward_named",
        item="NEW.item_id",
        by="v_actor",
    ),
)

STEWARDSHIP_TRIGGER = """
CREATE TRIGGER item_stewardship_is_told
    AFTER UPDATE ON know.item
    FOR EACH ROW EXECUTE FUNCTION know.item_stewardship()
"""

#: A decided solution tells the person who captured it.
SOLUTION_DECIDED_FUNCTION = """
CREATE FUNCTION know.solution_decided() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
BEGIN
    IF OLD.state <> 'pending' OR NEW.state = 'pending' THEN
        RETURN NULL;
    END IF;
__OPEN__
    RETURN NULL;
END;
$$
""".replace(
    "__OPEN__",
    _open_task(
        task_id="'decided.' || NEW.solution_id",
        to="NEW.captured_by",
        kind="solution_decided",
        item="NEW.solution_id",
        by="NEW.decided_by",
        outcome="NEW.state",
    ),
)

SOLUTION_DECIDED_TRIGGER = """
CREATE TRIGGER solution_decision_is_told
    AFTER UPDATE ON know.solution
    FOR EACH ROW EXECUTE FUNCTION know.solution_decided()
"""

# ------------------------------------------------------------------ the promotion
PROMOTION_FUNCTION = (
    """
CREATE FUNCTION know.apply_promotion() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
DECLARE
    v_args jsonb := NEW.action -> 'args';
    v_item text := NEW.action -> 'args' ->> 'item_id';
    v_owner text := NEW.action -> 'args' ->> 'owner_id';
    v_outcome text;
    v_changed integer;
BEGIN
    IF NEW.agent_id <> '__AGENT__' OR NEW.required_capability <> '__CAPABILITY__' THEN
        RETURN NULL;
    END IF;
    IF OLD.state <> 'pending' OR NEW.state = 'pending' THEN
        RETURN NULL;
    END IF;
    IF NEW.state = 'approved' THEN
        IF NEW.decided_by = NEW.principal_id THEN
            RAISE EXCEPTION USING
                MESSAGE = 'a promotion is approved by somebody other than the person who asked',
                ERRCODE = 'check_violation',
                HINT = 'a gate one person passes alone is not a gate';
        END IF;
        UPDATE know.item
           SET visibility = 'company',
               review_by = (v_args ->> 'review_by')::timestamptz,
               updated_at = now()
         WHERE item_id = v_item
           AND visibility = v_args ->> 'from_level'
           AND owner_id = v_owner
           AND state = 'published'
           AND verified_at IS NOT NULL
           AND verified_at < (v_args ->> 'review_by')::timestamptz;
        GET DIAGNOSTICS v_changed = ROW_COUNT;
        IF v_changed <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the document moved after its promotion was asked for',
                ERRCODE = 'check_violation',
                HINT = 'reject this one and ask again for the document as it is now';
        END IF;
        UPDATE know.chunk
           SET visibility = 'company'
         WHERE document_id = v_item
           AND deleted_at IS NULL
           AND state IN ('draft', 'published');
        v_outcome := 'approved';
    ELSE
        v_outcome := 'rejected';
    END IF;
__TELL_ASKER__
    IF v_owner IS DISTINCT FROM NEW.principal_id THEN
__TELL_STEWARD__
    END IF;
    RETURN NULL;
END;
$$
""".replace("__AGENT__", PROMOTION_AGENT)
    .replace("__CAPABILITY__", PROMOTION_CAPABILITY)
    .replace(
        "__TELL_ASKER__",
        _open_task(
            task_id="'decided.' || NEW.id",
            to="NEW.principal_id",
            kind="promotion_decided",
            item="v_item",
            by="NEW.decided_by",
            outcome="v_outcome",
        ),
    )
    .replace(
        "__TELL_STEWARD__",
        _open_task(
            task_id="'decided.steward.' || NEW.id",
            to="v_owner",
            kind="promotion_decided",
            item="v_item",
            by="NEW.decided_by",
            outcome="v_outcome",
        ),
    )
)

PROMOTION_TRIGGER = """
CREATE TRIGGER approved_promotion_is_applied
    AFTER UPDATE ON gate.suspension
    FOR EACH ROW EXECUTE FUNCTION know.apply_promotion()
"""

# ------------------------------------------------------------------ superseding
SUPERSEDE_FUNCTION = """
CREATE FUNCTION know.supersede_item(p_predecessor character varying, p_successor character varying)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
DECLARE
    v_before know.item%ROWTYPE;
    v_after know.item%ROWTYPE;
    v_principal text := current_setting('app.principal_id', true);
    v_departments text[] := string_to_array(current_setting('app.departments', true), ',');
BEGIN
    IF p_predecessor = p_successor THEN
        RAISE EXCEPTION USING MESSAGE = 'a document cannot supersede itself',
            ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO v_before FROM know.item WHERE item_id = p_predecessor FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING MESSAGE = 'there is no document to supersede',
            ERRCODE = 'no_data_found';
    END IF;
    SELECT * INTO v_after FROM know.item WHERE item_id = p_successor FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING MESSAGE = 'the new version has not been written',
            ERRCODE = 'no_data_found';
    END IF;
    -- The second wall: the reach this session was told admits the predecessor as it stands.
    IF NOT (
        v_before.state IN ('draft', 'published')
        AND (v_before.state <> 'draft' OR v_before.owner_id = v_principal)
        AND (
            v_before.visibility = 'company'
            OR v_before.visibility = 'department' AND v_before.department = ANY(v_departments)
            OR v_before.visibility = 'personal' AND v_before.owner_id = v_principal
        )
    ) THEN
        RAISE EXCEPTION USING MESSAGE = 'that document is not within reach',
            ERRCODE = 'insufficient_privilege';
    END IF;
    IF v_after.state <> 'published' OR v_after.supersedes IS NOT NULL THEN
        RAISE EXCEPTION USING MESSAGE = 'the new version is not a live document naming nothing',
            ERRCODE = 'check_violation';
    END IF;
    IF (CASE v_after.visibility WHEN 'personal' THEN 0 WHEN 'department' THEN 1 ELSE 2 END)
       > (CASE v_before.visibility WHEN 'personal' THEN 0 WHEN 'department' THEN 1 ELSE 2 END)
    THEN
        RAISE EXCEPTION USING MESSAGE = 'a new version is never wider than the one it replaces',
            ERRCODE = 'check_violation';
    END IF;
    IF v_after.visibility = v_before.visibility AND (
        v_after.visibility = 'department' AND v_after.department <> v_before.department
        OR v_after.visibility = 'personal' AND v_after.owner_id <> v_before.owner_id
    ) THEN
        RAISE EXCEPTION USING MESSAGE = 'a new version reaches nobody the old one did not',
            ERRCODE = 'check_violation';
    END IF;
    UPDATE know.item SET state = 'superseded', updated_at = now()
     WHERE item_id = p_predecessor;
    UPDATE know.item SET supersedes = p_predecessor, updated_at = now()
     WHERE item_id = p_successor;
    UPDATE know.chunk SET state = 'superseded'
     WHERE document_id = p_predecessor
       AND deleted_at IS NULL
       AND state IN ('draft', 'published');
END;
$$
"""

# ------------------------------------------------------------------ reading a history
#: The most versions a history walks in either direction. A resource bound, and far past any
#: document anybody replaces by hand.
MAX_VERSIONS = 50

VERSIONS_FUNCTION = """
CREATE FUNCTION know.item_versions(p_item character varying)
RETURNS TABLE (
    item_id character varying,
    title character varying,
    owner_id character varying,
    visibility character varying,
    department character varying,
    state character varying,
    kind character varying,
    verified_by character varying,
    verified_at timestamptz,
    review_by timestamptz,
    supersedes character varying,
    created_at timestamptz
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $versions$
    WITH RECURSIVE earlier(item_id, depth) AS (
        SELECT i.item_id, 0 FROM know.item AS i WHERE i.item_id = p_item
        UNION ALL
        SELECT i.supersedes, e.depth + 1
        FROM earlier AS e JOIN know.item AS i ON i.item_id = e.item_id
        WHERE i.supersedes IS NOT NULL AND e.depth < __MAX__
    ),
    later(item_id, depth) AS (
        SELECT i.item_id, 0 FROM know.item AS i WHERE i.item_id = p_item
        UNION ALL
        SELECT i.item_id, l.depth + 1
        FROM later AS l JOIN know.item AS i ON i.supersedes = l.item_id
        WHERE l.depth < __MAX__
    )
    SELECT i.item_id, i.title, i.owner_id, i.visibility, i.department, i.state, i.kind,
           i.verified_by, i.verified_at, i.review_by, i.supersedes, i.created_at
    FROM know.item AS i
    WHERE i.item_id IN (SELECT e.item_id FROM earlier AS e UNION SELECT l.item_id FROM later AS l)
    ORDER BY i.created_at, i.item_id
$versions$
""".replace("__MAX__", str(MAX_VERSIONS))

PASSAGES_FUNCTION = """
CREATE FUNCTION know.version_passages(p_item character varying, p_limit integer)
RETURNS TABLE (
    chunk_id character varying,
    ordinal integer,
    title character varying,
    section character varying,
    page integer,
    body text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $passages$
    SELECT c.chunk_id, c.ordinal, c.title, c.section, c.page, c.body
    FROM know.chunk AS c
    WHERE c.document_id = p_item AND c.deleted_at IS NULL
    ORDER BY c.ordinal
    LIMIT greatest(p_limit, 0)
$passages$
"""

FUNCTIONS: tuple[str, ...] = (
    "know.supersede_item(character varying, character varying)",
    "know.item_versions(character varying)",
    "know.version_passages(character varying, integer)",
)

TRIGGERS: tuple[tuple[str, str, str], ...] = (
    ("approved_promotion_is_applied", "gate.suspension", "know.apply_promotion()"),
    ("solution_decision_is_told", "know.solution", "know.solution_decided()"),
    ("solution_is_audited", "know.solution", "know.record_solution()"),
    ("item_stewardship_is_told", "know.item", "know.item_stewardship()"),
    ("nag_opens_a_review_task", "ops.outbox_event", "know.open_review_task()"),
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert all("INSERT" not in statement for statement in GRANTS if "steward_task" in statement)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "steward_task",
        sa.Column("task_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(TASK_KIND_CHARS), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(OUTCOME_CHARS), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"task_id ~ '{REFERENCE_PATTERN}'", name="task_id_is_a_reference"),
        sa.CheckConstraint(f"item_id ~ '{REFERENCE_PATTERN}'", name="item_id_is_a_reference"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="addressed"),
        sa.CheckConstraint(TASK_KIND_CHECK, name="kind"),
        sa.CheckConstraint(OUTCOME_CHECK, name="outcome"),
        sa.CheckConstraint(
            "kind <> 'reverify' OR due_at IS NOT NULL", name="a_review_names_its_date"
        ),
        sa.CheckConstraint(
            "(outcome IS NOT NULL) = (kind IN ('promotion_decided', 'solution_decided'))",
            name="a_decision_says_how_it_went",
        ),
        schema="know",
    )
    op.create_index(
        "ix_steward_task_open",
        "steward_task",
        ["principal_id"],
        schema="know",
        postgresql_where=sa.text("done_at IS NULL"),
    )
    op.create_index("ix_steward_task_item_id", "steward_task", ["item_id"], schema="know")
    op.create_table(
        "solution",
        sa.Column("solution_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("problem", sa.String(PROBLEM_CHARS), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("conversation_ref", sa.String(128), nullable=True),
        sa.Column("captured_by", sa.String(128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"solution_id ~ '{REFERENCE_PATTERN}'", name="solution_id_is_a_reference"
        ),
        sa.CheckConstraint(f"department ~ '{SLUG_PATTERN}'", name="department_is_a_slug"),
        sa.CheckConstraint("length(btrim(problem)) > 0", name="says_what_it_solved"),
        sa.CheckConstraint(
            f"length(btrim(answer)) > 0 AND length(answer) <= {ANSWER_CHARS}",
            name="says_how",
        ),
        sa.CheckConstraint(
            f"conversation_ref IS NULL OR conversation_ref ~ '{REFERENCE_PATTERN}'",
            name="conversation_ref_is_a_reference",
        ),
        sa.CheckConstraint("length(btrim(captured_by)) > 0", name="captured_by_somebody"),
        sa.CheckConstraint(SOLUTION_STATE_CHECK, name="state"),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        sa.CheckConstraint(
            "(decided_by IS NULL) = (state = 'pending')",
            name="only_a_decided_solution_names_its_decider",
        ),
        sa.CheckConstraint(
            "(item_id IS NOT NULL) = (state = 'approved')",
            name="an_approved_solution_is_a_document",
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> captured_by",
            name="decided_by_somebody_else",
        ),
        schema="know",
    )
    op.create_index(
        "ix_solution_department_state", "solution", ["department", "state"], schema="know"
    )
    for statement in RLS:
        op.execute(statement)
    op.execute(SUPERSEDE_FUNCTION)
    op.execute(VERSIONS_FUNCTION)
    op.execute(PASSAGES_FUNCTION)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(ITEM_AUDIT_FUNCTION)
    op.execute(SOLUTION_AUDIT_FUNCTION)
    op.execute(SOLUTION_AUDIT_TRIGGER)
    op.execute(REVIEW_TASK_FUNCTION)
    op.execute(REVIEW_TASK_TRIGGER)
    op.execute(STEWARDSHIP_FUNCTION)
    op.execute(STEWARDSHIP_TRIGGER)
    op.execute(SOLUTION_DECIDED_FUNCTION)
    op.execute(SOLUTION_DECIDED_TRIGGER)
    op.execute(PROMOTION_FUNCTION)
    op.execute(PROMOTION_TRIGGER)


def downgrade() -> None:
    for name, table, function in TRIGGERS:
        op.execute(f"DROP TRIGGER {name} ON {table}")
        op.execute(f"DROP FUNCTION {function}")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION {function}")
    op.execute(ITEM_AUDIT_FUNCTION_AS_0115_SHIPPED)
    # The indexes, the policies and the grants go with the tables.
    op.drop_table("solution", schema="know")
    op.drop_table("steward_task", schema="know")
