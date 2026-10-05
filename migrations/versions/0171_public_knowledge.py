"""Knowledge can be marked public, and a stranger's read runs as a role that reaches nothing else.

`brain.knowledge.public` argues who may mark an item and `brain.knowledge.search.PublicReach` what
a website visitor may read. What is here is what the database has to hold for both (M10.7.2).

**Two columns on `know.item`, `public_by` and `public_at`, both or neither.** Who marked the item
public and when, which is the record needs-rupash 26 asks for: marking is a one-way door in
practice, so it names the person as a grant does. The marking is on the item and not copied onto
its passages, so unmarking takes effect on the next question and no passage is rewritten. **A
personal item is never public**: the database refuses the pair on one, because a note its author
has shared with nobody cannot be shared with everybody.

**`brain_public`, a role with one read and nothing else.** Created NOLOGIN NOSUPERUSER NOBYPASSRLS
NOINHERIT as `0150` creates `brain_trace_reader`, and granted to `brain_app` `WITH INHERIT FALSE,
SET TRUE`: the application may `SET LOCAL ROLE brain_public` for a widget's question and inherits
nothing from it. It may use the `know` schema, select `know.chunk`, and select four columns of
`know.item`, the ones its own policy asks. **Its two policies are its only policies**, since every
earlier policy on both tables names `brain_app`: an item is read when it is published, not
personal and marked; a passage when it is live, published, not personal and its item is one of
those. So a statement that forgot `brain.knowledge.search.public_predicate` still returns nothing
else, which is needs-rupash 26's "the filter is not the only thing standing between a stranger and
everything else" held by the database.

**`know.record_item` says whether a replacement marked or unmarked the item.** `0120`'s function
names the columns a replacement changed, so a marking already appends an entry naming the actor
and `public_at,public_by`. That entry reads the same for a marking and an unmarking, so the one
addition is `public`, true or false, on an entry whose change moved `public_at`. A boolean
survives `brain.audit.ledger.redact_details`. Every other entry is unchanged.

**The downgrade** puts `0120`'s function back, drops the policies and the columns, and revokes the
role from the application. The role itself is left, for `0001`'s reason about roles on a cluster.

Revises `0177`, the head of main when this landed.

Task ids: M10.7.2

Revision ID: 0171
Revises: 0177
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0171"
down_revision = "0177"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The columns this adds to `know.item`, named for that table as `0115`'s are.
ITEM_COLUMNS_ADDED: tuple[str, ...] = ("public_by", "public_at")

#: `brain.tables.knowledge.KnowledgeItemRow`'s three checks, copied and held equal by a test. The
#: first two together are "both or neither", written as two halves that each begin with a column
#: this migration adds being null, which is the form `brain.deployment.compatibility` reads as
#: binding no row the previous release can write: it never names either column, so both are null
#: in every row it writes. `(public_by IS NULL) = (public_at IS NULL)` says the same and is a
#: predicate the gate cannot order, so it was reported as a narrowing of a table already there.
A_MARKING_NAMES_A_PERSON = "public_at IS NULL OR public_by IS NOT NULL"
A_MARKER_NAMES_A_TIME = "public_by IS NULL OR public_at IS NOT NULL"
A_PERSONAL_ITEM_IS_NEVER_PUBLIC = "public_at IS NULL OR visibility <> 'personal'"

#: `brain.knowledge.search.OWNER_ID_CHARS`, the width of every principal id on the table.
PRINCIPAL_CHARS = 128

APP_ROLE = "brain_app"
PUBLIC_ROLE = "brain_public"

#: The role, created once per cluster as `0001` and `0150` create theirs.
CREATE_PUBLIC_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_public') THEN
        CREATE ROLE brain_public NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
    END IF;
END
$$;
"""

#: The application may take the role for a transaction and inherits nothing from it.
MEMBERSHIP = "GRANT brain_public TO brain_app WITH INHERIT FALSE, SET TRUE"

#: What the role may read, and the policies that narrow it. `brain.knowledge.search.
#: public_predicate` states the same condition, and a test holds the two to one meaning.
PUBLIC_GRANTS: tuple[str, ...] = (
    "GRANT USAGE ON SCHEMA know TO brain_public",
    "GRANT SELECT ON know.chunk TO brain_public",
    "GRANT SELECT (item_id, state, visibility, public_at) ON know.item TO brain_public",
)

RLS: tuple[str, ...] = (
    """
    CREATE POLICY item_marked_public ON know.item
        FOR SELECT TO brain_public
        USING (
            public_at IS NOT NULL
            AND state = 'published'
            AND visibility <> 'personal'
        )
    """,
    """
    CREATE POLICY chunk_of_an_item_marked_public ON know.chunk
        FOR SELECT TO brain_public
        USING (
            deleted_at IS NULL
            AND state = 'published'
            AND visibility <> 'personal'
            AND EXISTS (
                SELECT 1 FROM know.item i
                 WHERE i.item_id = chunk.document_id
                   AND i.public_at IS NOT NULL
                   AND i.state = 'published'
                   AND i.visibility <> 'personal'
            )
        )
    """,
)

DOWNGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY chunk_of_an_item_marked_public ON know.chunk",
    "DROP POLICY item_marked_public ON know.item",
)

REVOKES: tuple[str, ...] = (
    "REVOKE SELECT (item_id, state, visibility, public_at) ON know.item FROM brain_public",
    "REVOKE SELECT ON know.chunk FROM brain_public",
    "REVOKE USAGE ON SCHEMA know FROM brain_public",
    "REVOKE brain_public FROM brain_app",
)

# ------------------------------------------------------------------ the item's audit function
#: `0120`'s subject prefix and the longest item id recorded as itself, restated.
ITEM_SUBJECT_PREFIX = "setting:knowledge_item."
ITEM_ID_CHARS = 128 - len("knowledge_item.")

#: `0120`'s template, copied for `0046`'s reason: a migration describes the database it built.
#: `__PUBLIC__` is where this migration's addition goes, and nothing goes there for `0120`'s body.
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

#: `0120`'s addition: the names of the columns a replacement changed.
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

#: This migration's addition: whether a replacement that moved the marking marked or unmarked.
_PUBLIC = """
    IF TG_OP = 'UPDATE' AND NEW.public_at IS DISTINCT FROM OLD.public_at THEN
        v_details := v_details || jsonb_build_object('public', NEW.public_at IS NOT NULL);
    END IF;
"""

#: `0003`'s block over one change, as `0115` and `0120` copy it.
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


def _item_audit(changed: str) -> str:
    return (
        _ITEM_AUDIT_TEMPLATE.replace("__CHANGED__", changed)
        .replace("__APPEND__", _APPEND)
        .replace("__PREFIX__", ITEM_SUBJECT_PREFIX)
        .replace("__ID_CHARS__", str(ITEM_ID_CHARS))
    )


#: The function after this migration, and `0120`'s exactly, which a test holds equal to that
#: migration's own.
ITEM_AUDIT_FUNCTION = _item_audit(_CHANGED + _PUBLIC)
ITEM_AUDIT_FUNCTION_AS_0120_SHIPPED = _item_audit(_CHANGED)


def upgrade() -> None:
    assert all(PUBLIC_ROLE in statement for statement in PUBLIC_GRANTS)
    assert all("brain_app" not in statement for statement in PUBLIC_GRANTS)
    assert all("TO brain_public" in statement for statement in RLS)
    assert all("FOR SELECT" in statement for statement in RLS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.add_column(
        "item", sa.Column("public_by", sa.String(PRINCIPAL_CHARS), nullable=True), schema="know"
    )
    op.add_column(
        "item", sa.Column("public_at", sa.DateTime(timezone=True), nullable=True), schema="know"
    )
    op.create_check_constraint(
        "a_public_marking_names_a_person", "item", A_MARKING_NAMES_A_PERSON, schema="know"
    )
    op.create_check_constraint(
        "a_public_marker_names_a_time", "item", A_MARKER_NAMES_A_TIME, schema="know"
    )
    op.create_check_constraint(
        "a_personal_item_is_never_public", "item", A_PERSONAL_ITEM_IS_NEVER_PUBLIC, schema="know"
    )
    op.execute(CREATE_PUBLIC_ROLE)
    op.execute(MEMBERSHIP)
    for statement in PUBLIC_GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)
    op.execute(ITEM_AUDIT_FUNCTION)


def downgrade() -> None:
    op.execute(ITEM_AUDIT_FUNCTION_AS_0120_SHIPPED)
    for statement in DOWNGRADE_RLS:
        op.execute(statement)
    for statement in REVOKES:
        op.execute(statement)
    op.drop_constraint("a_personal_item_is_never_public", "item", schema="know", type_="check")
    op.drop_constraint("a_public_marker_names_a_time", "item", schema="know", type_="check")
    op.drop_constraint("a_public_marking_names_a_person", "item", schema="know", type_="check")
    op.drop_column("item", "public_at", schema="know")
    op.drop_column("item", "public_by", schema="know")
