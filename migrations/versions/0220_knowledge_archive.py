"""A steward or the administrator of where a document sits can archive it from the console.

**`know.archive_item` is the one write that moves a document to `archived`.** `know.item`'s policy
admits only live rows, so the update that moves a row out of `draft` or `published` is refused under
it, which is the defect `0120` recorded for a supersession and answered with `know.supersede_item`.
This is the same answer for a withdrawal. The function is `SECURITY DEFINER` with its search path
pinned and every object named with its schema, the arrangement `0040` makes.

**The database is the second wall.** `brain.knowledge.lifecycle.Authority.may_act` decides in Python
who may archive, and this function repeats the one part of it the session can state: the document is
live and the reach the session was told admits it as it stands (company-wide, a department the
session holds, or the caller's own personal one; somebody else's draft is never within reach). It
does not decide who the steward is, because Python has already said so under the same transaction
and a second copy of that rule here would be a second place for it to be subtly wrong.

**The document's passages go with it.** A passage of an archived document stays in `know.chunk`,
state `archived`, which no retrieval path reads (`brain.knowledge.item.RETRIEVABLE_STATES` is the
list written out), so an answer stops using the document in the transaction that archives it, and
the document and its history stay on file. Nothing is deleted: no DELETE is granted by this
migration, and the function removes no row.

**The ledger entry is the one `0115`'s trigger already writes**, with `state` among the changed
columns and `state` itself `archived`, which is what `brain.knowledge.lifecycle.event_of` reads as
the history's archived step. This migration adds no ledger code of its own.

The downgrade drops the function. A document archived under it stays archived, because the state is
a member of the item's own check.

Task ids: M27.15.40

Revision ID: 0220
Revises: 0212
"""

from __future__ import annotations

from alembic import op

revision = "0220"
# The head of origin/main when this was written (e75f096). 0213 to 0219 are other builders' numbers
# in the same train, so the coordinator relinks this behind whichever of them lands last.
down_revision = "0212"
branch_labels = None
depends_on = None

APP_ROLE = "brain_app"

#: The function's signature, as `GRANT` and `DROP` name it.
FUNCTION = "know.archive_item(character varying)"

ARCHIVE_FUNCTION = """
CREATE FUNCTION know.archive_item(p_item character varying)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $$
DECLARE
    v_item know.item%ROWTYPE;
    v_principal text := current_setting('app.principal_id', true);
    v_departments text[] := string_to_array(current_setting('app.departments', true), ',');
BEGIN
    SELECT * INTO v_item FROM know.item WHERE item_id = p_item FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING MESSAGE = 'there is no document to archive',
            ERRCODE = 'no_data_found';
    END IF;
    -- The second wall: the reach this session was told admits the document as it stands.
    IF NOT (
        v_item.state IN ('draft', 'published')
        AND (v_item.state <> 'draft' OR v_item.owner_id = v_principal)
        AND (
            v_item.visibility = 'company'
            OR v_item.visibility = 'department' AND v_item.department = ANY(v_departments)
            OR v_item.visibility = 'personal' AND v_item.owner_id = v_principal
        )
    ) THEN
        RAISE EXCEPTION USING MESSAGE = 'that document is not within reach',
            ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE know.item SET state = 'archived', updated_at = now() WHERE item_id = p_item;
    UPDATE know.chunk SET state = 'archived'
     WHERE document_id = p_item
       AND deleted_at IS NULL
       AND state IN ('draft', 'published');
END;
$$
"""

GRANT = f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {APP_ROLE}"


def upgrade() -> None:
    assert APP_ROLE in GRANT
    assert "DELETE" not in GRANT
    op.execute(ARCHIVE_FUNCTION)
    op.execute(GRANT)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
