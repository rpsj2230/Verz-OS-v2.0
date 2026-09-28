"""Every knowledge item records its kind, from a closed list, and the library can say which.

**`know.item.kind`** (M7.6.1): one word from `brain.knowledge.kinds.KnowledgeKind`, checked by a
constraint generated from that enum and held equal to it by `tests/unit/test_knowledge_kinds.py`.
Nullable, deliberately, for the reason `0010` gives about the embedding model: the items written
before this release were written by a path that chose no kind, there is no honest value to
backfill, and inventing one would be a classification nobody made. Every item the console adds
carries one, because the upload door refuses an upload naming none; a NULL means an item from
before this release or from the connector leg, and the library says so in words.

**No kind on `know.chunk`.** A search narrowed to some kinds asks `know.item` for them inside the
chunk statement, and `know.item`'s policy reads the same two session settings `know.chunk`'s does,
so the narrowing sees exactly the items the reach already admits. A copied column was rejected: it
would be a second place the kind lives, and a re-upload that changed the kind would have to move
it in two tables inside one transaction or leave them disagreeing.

**`know.library_items_with_kind` is the library read with the kind as its fifth column.** The
Knowledge library is read past the corpus policy through `0069`'s `know.library_items`, and the
kind is shown on its rows. A kind is a word a person chose from twelve and says nothing a
document's text says, so it sits on the existence plane beside the level, which is what that
screen may show. A second function rather than `0069`'s replaced, because PostgreSQL cannot
change the columns a function returns without dropping it, and a release still running during a
deploy reads the old one: `brain.deployment.compatibility` refuses a migration that removes what
the release before it reads. The old function is left for that release and is the next contract
migration's to drop. Its body is `0069`'s with one more column, and EXECUTE is granted as `0069`
granted it.

**The check travels with the column,** under the naming convention, as `0093` and `0100` add
theirs: a constraint added to a table that was already there is one the compatibility gate cannot
order, and one declared on a column that did not exist before narrows nothing the previous release
could write.

**Every write of `know.item` appends a ledger entry** (the owner's rule that every change is
audited). `know.record_item` is `0109`'s trigger shape over this table: `setting`, the action
`0109` records a group-role rule under, with the subject `setting:knowledge_item.<item id>` (a
digest of the id when the id is too long for the subject grammar), and details naming the change
(added or replaced), the source, the kind, the level, the department and the state. Never the
title and never a word of the text: a title is the part of a document `0040` says the wall exists
for, and the ledger is read by an auditor who may hold no read of the document. The writer is
`brain.actor_id` as `brain.attribution` sets it, and the owner, marked `inferred`, when nothing
set it, which is the connector leg writing at night. `jsonb_strip_nulls` leaves a company or
personal item's department and a connector item's kind out rather than recording a null, which
the ledger's details grammar refuses. A second action or subject kind for knowledge was rejected
here: it widens two closed vocabularies and the ledger's check constraints, and `0109` already
records a directory rule, which is not a setting either, under `setting`.

**The downgrade** drops the trigger and its function, the second library read, then the column
and its check with it. Dropping the
column loses every recorded kind, which is a real loss and the only reversal a column addition
has; no check is re-created, so nothing is narrowed on rows already written.

Task ids: M7.6.1, M7.6.3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0115"
# The newest migration on origin/main when this was written.
down_revision = "0108"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The column this adds to `know.item`, which `0040` built. Named for that table so the chunk
#: table's comparison in `tests/unit/test_search.py`, which reads `ADDS_COLUMNS`, is not told
#: about a column on a different table.
ITEM_COLUMNS_ADDED: tuple[str, ...] = ("kind",)

APP_ROLE = "brain_app"

SCHEMA = "know"
TABLE = "item"
COLUMN = "kind"

#: `brain.knowledge.kinds.KIND_CHARS`, copied for `0009`'s reason about reading live code from
#: a migration and held equal by a test.
KIND_CHARS = 32

#: `brain.knowledge.kinds.KnowledgeKind`, sorted, copied for the same reason and held equal.
KINDS: tuple[str, ...] = (
    "approved_solution",
    "best_practice",
    "brand_guidelines",
    "company_rule",
    "faq",
    "policy",
    "pricing_note",
    "service_information",
    "service_package",
    "sop",
    "template",
    "training_material",
)

#: The check, in the words `brain.tables.knowledge` renders for the model.
KIND_CHECK = "kind IS NULL OR kind IN ({})".format(", ".join(f"'{one}'" for one in KINDS))

LIBRARY_FUNCTION = "know.library_items_with_kind(integer)"

CREATE_LIBRARY = """
CREATE FUNCTION know.library_items_with_kind(p_limit integer)
RETURNS TABLE (
    item_id character varying,
    owner_id character varying,
    visibility character varying,
    department character varying,
    kind character varying
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $library$
    SELECT i.item_id, i.owner_id, i.visibility, i.department, i.kind
    FROM know.item AS i
    WHERE i.state IN ('draft', 'published')
    ORDER BY i.item_id
    LIMIT greatest(p_limit, 0)
$library$
"""

GRANTS: tuple[str, ...] = (f"GRANT EXECUTE ON FUNCTION {LIBRARY_FUNCTION} TO brain_app",)

#: The subject kind and prefix every item entry is recorded under. See the docstring.
AUDIT_ACTION = "setting"
AUDIT_SUBJECT_PREFIX = "setting:knowledge_item."

#: The longest item id recorded as itself: the subject grammar's 128 identifier characters less
#: the `knowledge_item.` prefix. A longer id is recorded as its sha256.
AUDIT_ID_CHARS = 128 - len("knowledge_item.")

#: The details an entry carries, in the order the trigger builds them. Held against the body
#: below by `tests/unit/test_knowledge_audit.py`, and never `title`.
AUDIT_DETAILS: tuple[str, ...] = ("change", "source", "kind", "level", "department", "state")

#: The append, `0003`'s block, over one change, as `0102` and `0109` copy it.
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

AUDIT_FUNCTION = "know.record_item()"

_AUDIT_TEMPLATE = """
CREATE FUNCTION know.record_item() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
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
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_details := jsonb_build_object('change', 'added');
    ELSE
        v_details := jsonb_build_object('change', 'replaced');
    END IF;
    v_action := '__ACTION__';
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
    IF v_supplied IS NULL THEN
        v_details := v_details || jsonb_build_object('actor', 'inferred');
    END IF;
__APPEND__
    RETURN NULL;
END;
$$
"""

CREATE_AUDIT_FUNCTION = (
    _AUDIT_TEMPLATE.replace("__APPEND__", _APPEND)
    .replace("__ACTION__", AUDIT_ACTION)
    .replace("__PREFIX__", AUDIT_SUBJECT_PREFIX)
    .replace("__ID_CHARS__", str(AUDIT_ID_CHARS))
)

AUDIT_TRIGGER = """
CREATE TRIGGER item_is_audited
    AFTER INSERT OR UPDATE ON know.item
    FOR EACH ROW EXECUTE FUNCTION know.record_item()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    # The check travels with the column, under the naming convention; see the docstring.
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            sa.String(KIND_CHARS),
            sa.CheckConstraint(KIND_CHECK, name=COLUMN),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.execute(CREATE_LIBRARY)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(CREATE_AUDIT_FUNCTION)
    op.execute(AUDIT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER item_is_audited ON know.item")
    op.execute(f"DROP FUNCTION {AUDIT_FUNCTION}")
    op.execute(f"DROP FUNCTION {LIBRARY_FUNCTION}")
    # The check goes with the column it constrains, so it is not dropped by name first.
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
