"""A chunk can be retired by the application role, and a retired chunk stays hidden and retired.

0045 argues the defect and the shape, and this applies the same shape to `know.chunk`. 0009 gave
the chunk one `FOR ALL` policy whose USING is the reach predicate with `deleted_at IS NULL` in
it, and repeated 0002's claim that `WITH CHECK (true)` lets a chunk be marked superseded. It does
not, for the reason `A_SEPARATE_READ_POLICY_STILL_CHECKS_THE_NEW_ROW` in 0045 gives: the new row
of an UPDATE with a WHERE clause is checked against the read policy's USING, and a retired chunk
fails it.

**The reach predicate is carried into the read and the update unchanged.** 0009's argument for
one policy rather than a read policy beside a maintenance policy was that permissive policies are
OR-ed within a command, so a second policy admitting live rows would widen the read. Per-command
policies are not OR-ed across commands: the read has exactly one policy, and the update's USING
is the same predicate, so an indexing worker still sees and retires a chunk only when it sets the
settings a request sets. The update's WITH CHECK is the retirement stamp alone, as 0009's was
`true`: a chunk's owner, visibility and department are the indexer's to rewrite, and narrowing
that is a different change.

**A superseded chunk is not a retired one, and this does not fix superseding.** The read still
admits only `draft` and `published`, so an UPDATE moving a live chunk to `superseded` is refused
by the rule 0045 describes, exactly as setting `deleted_at` was. Nothing under `src` does that
yet. It is recorded here rather than fixed because the right shape for a state column is not
this one: there is no statement stamp to match on.

**Separate from 0045 because this table needs pgvector to build**, so its test runs where the
extension exists.

**The downgrade puts back 0009's policy exactly.**

Task ids: none

Revision ID: 0046
Revises: 0045
"""

from __future__ import annotations

from typing import Final

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

#: 0045's constant of the same name, restated because a migration describes the database it
#: built rather than importing another file. The invariant test holds the two equal.
RETIRED_BY_THIS_STATEMENT: Final = "deleted_at = statement_timestamp()"

RLS: tuple[str, ...] = (
    "DROP POLICY chunk_within_reach ON know.chunk",
    """
    CREATE POLICY chunk_within_reach ON know.chunk
        FOR SELECT TO brain_app
        USING (
            (deleted_at IS NULL OR deleted_at = statement_timestamp())
            AND state IN ('draft', 'published')
            AND (state <> 'draft' OR owner_id = current_setting('app.principal_id', true))
            AND (
                visibility = 'personal'
                    AND owner_id = current_setting('app.principal_id', true)
                OR visibility = 'department'
                    AND department = ANY(
                        string_to_array(current_setting('app.departments', true), ',')
                    )
                OR visibility = 'company'
            )
        )
    """,
    """
    CREATE POLICY chunk_insertable ON know.chunk
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY chunk_updatable ON know.chunk
        FOR UPDATE TO brain_app
        USING (
            deleted_at IS NULL
            AND state IN ('draft', 'published')
            AND (state <> 'draft' OR owner_id = current_setting('app.principal_id', true))
            AND (
                visibility = 'personal'
                    AND owner_id = current_setting('app.principal_id', true)
                OR visibility = 'department'
                    AND department = ANY(
                        string_to_array(current_setting('app.departments', true), ',')
                    )
                OR visibility = 'company'
            )
        )
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)

#: 0009's policy, put back exactly, broken as it was.
DOWNGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY chunk_updatable ON know.chunk",
    "DROP POLICY chunk_insertable ON know.chunk",
    "DROP POLICY chunk_within_reach ON know.chunk",
    """
    CREATE POLICY chunk_within_reach ON know.chunk
        FOR ALL TO brain_app
        USING (
            deleted_at IS NULL
            AND state IN ('draft', 'published')
            AND (state <> 'draft' OR owner_id = current_setting('app.principal_id', true))
            AND (
                visibility = 'personal'
                    AND owner_id = current_setting('app.principal_id', true)
                OR visibility = 'department'
                    AND department = ANY(
                        string_to_array(current_setting('app.departments', true), ',')
                    )
                OR visibility = 'company'
            )
        )
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all("DELETE" not in statement for statement in RLS)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_RLS:
        op.execute(statement)
