"""The application role is granted the run record it reads, and two item reads its policy withheld.

`brain.ops.application_privileges` compares every table the application's sessions read and write
against what the migrations grant `brain_app` and what row-level security admits, from source.
Run on 2026-09-17 it found three mismatches, and a staging install had already found the first.

**`ops.control_run` had three policies naming `brain_app` and no grant.** `0025` wrote a read, an
insert and a finish policy and no `GRANT`, and the worker writes the table as the database login,
so nothing failed until a console screen read it through the application's sessions. Live runs,
Scheduled jobs, Errors and Quality then answered every request with `permission denied for table
control_run` and a 500. SELECT is granted and nothing else: the reads are the routes', and the
insert and the finish stay the worker's, which writes them as the login in
`brain.ops.worker.run_control_job` and `brain.ops.schedule_runner`. Granting the two writes the
policies already describe would hand the application a way to record that a control ran when it
did not. `USING (true)` stays the read policy, for `0025`'s reason: which runs a reader may see is
`brain.jobs_routes.may_see_job`, decided against their live entitlements.

**The Knowledge library read `know.item` as `brain_app` with no session settings, so it saw
company items only.** `brain.estate_routes.library` lists "every retrievable item this reader may
know exists" and `brain.console.govern_estate.library_rows` narrows it by where each item sits,
deliberately not by the item's own visibility, so a company-wide reader is shown that a department
or personal item exists. `0040`'s policy is the corpus's reach and admits neither without a
principal and a department list, and the screen quietly listed fewer items than it says it lists.
`know.library_items` returns the four columns the screen places an item by, the id, the owner, the
visibility and the department, for retrievable items in reference order and bounded, and not the
title, which is the part of a document `0040` says the wall exists for.

**My workspace read the items a person stewards the same way, and saw only their company items.**
`brain.mine_routes.items_stewarded_by` asks for `owner_id` equal to the caller and never set
`app.principal_id`, so a personal item or a draft of their own was absent from the list of what
they keep. `know.items_stewarded_by_the_session` returns the same four columns for the
retrievable items whose owner is the principal the session names, and the route still asks
`is_own` of each row. Keyed to the setting and not to a parameter, so the application reads one
person's own stewardship by saying who is present, which is how every other own-row policy in
this schema is written, and never anybody's by naming them.

Rejected, for both reads: widening `item_within_reach`. A read policy on `know.item` is also what
retrieval stands behind, and an owner clause on it would let a person retrieve their own
department document after leaving the department, which
`brain.knowledge.chunk_store.A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF`
refuses. A session setting that switches the policy off is `0040`'s second rejected design, a
string any application code can write.

Both functions are `SECURITY DEFINER` with a pinned search path, every object named with its
schema, `STABLE` so a replica serves them, and granted EXECUTE as `0040` grants its own. `PUBLIC`
keeps EXECUTE for `0040`'s reason, and USAGE on `know` is `brain_app`'s alone.

The downgrade drops both functions and takes the grant back, after which those four screens fail
exactly as they did.

Task ids: M27.9.7

Revision ID: 0069
Revises: 0068
"""

from __future__ import annotations

from alembic import op

revision = "0069"
# The head of origin/main when this was written. Re-pointed at whichever migration is the head
# when it is integrated: nothing here depends on a table any later migration builds.
down_revision = "0068"
branch_labels = None
depends_on = None

APP_ROLE = "brain_app"

#: `brain.knowledge.item.RETRIEVABLE_STATES`, which a test holds this to.
RETRIEVABLE = ("draft", "published")

LIBRARY_FUNCTION = "know.library_items(integer)"
STEWARDED_FUNCTION = "know.items_stewarded_by_the_session(integer)"

CREATE_LIBRARY = """
CREATE FUNCTION know.library_items(p_limit integer)
RETURNS TABLE (
    item_id character varying,
    owner_id character varying,
    visibility character varying,
    department character varying
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $library$
    SELECT i.item_id, i.owner_id, i.visibility, i.department
    FROM know.item AS i
    WHERE i.state IN ('draft', 'published')
    ORDER BY i.item_id
    LIMIT greatest(p_limit, 0)
$library$
"""

CREATE_STEWARDED = """
CREATE FUNCTION know.items_stewarded_by_the_session(p_limit integer)
RETURNS TABLE (
    item_id character varying,
    owner_id character varying,
    visibility character varying,
    department character varying
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $stewarded$
    SELECT i.item_id, i.owner_id, i.visibility, i.department
    FROM know.item AS i
    WHERE i.owner_id = current_setting('app.principal_id', true)
      AND i.state IN ('draft', 'published')
    ORDER BY i.item_id
    LIMIT greatest(p_limit, 0)
$stewarded$
"""

GRANTS: tuple[str, ...] = (
    "GRANT SELECT ON ops.control_run TO brain_app",
    f"GRANT EXECUTE ON FUNCTION {LIBRARY_FUNCTION} TO brain_app",
    f"GRANT EXECUTE ON FUNCTION {STEWARDED_FUNCTION} TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    # The state list is written into both bodies rather than interpolated; this keeps it one list.
    assert all(
        f"i.state IN ({', '.join(repr(one) for one in RETRIEVABLE)})" in body
        for body in (CREATE_LIBRARY, CREATE_STEWARDED)
    )
    # The run record is read and never written by the application. See the docstring.
    assert not any(
        "control_run" in statement and verb in statement
        for statement in GRANTS
        for verb in ("INSERT", "UPDATE", "DELETE")
    )
    op.execute(CREATE_LIBRARY)
    op.execute(CREATE_STEWARDED)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {STEWARDED_FUNCTION}")
    op.execute(f"DROP FUNCTION {LIBRARY_FUNCTION}")
    op.execute("REVOKE SELECT ON ops.control_run FROM brain_app")
