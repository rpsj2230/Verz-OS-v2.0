"""An access review's decisions get a table, and each decision reaches the ledger from the database.

`brain.console.govern` has decided who may keep or remove a grant in a review round since
2026-09-08, and nothing could record the answer. `brain.govern_routes` says so in
`ONLY_THE_HALF_OF_A_ROUND_THAT_HAS_A_ROW_TO_WRITE`: a removal retires a row and the grant trigger
records it, and a decision to keep a grant had "no certification table for it to be recorded in",
so a route accepting one would answer 200 to a person who believes the round is on the record when
nothing was written anywhere. M27.7.9 puts the round on a screen, and this migration is the table
behind it, the ledger member it is recorded under, and the trigger that records it.

**One row per decision, and a decision is never edited or retired.** `gate.review_decision` has no
`deleted_at` and the application role is granted SELECT and INSERT only. A round decided twice is
two rows, and the screen reads the newest; a row rewritten would be a decision whose author changed
after the fact, which is the one thing a review record exists to rule out.

**A decision names the row it was about, exactly one of two.** A grant is held either as a direct
row in `gate.capability_grant` or through a pack in `gate.capability_pack_assignment`, and a review
covers both, because a person holding twelve capabilities through a pack holds them exactly as much
as twelve direct grants. Two nullable foreign keys and a check that exactly one is set, rather than
one polymorphic id with a kind column, so the database refuses a decision about a row that does not
exist rather than trusting a string. `RESTRICT`, so a grant cannot be hard-deleted out from under
its review history; nothing here hard-deletes one anyway.

**Nobody decides their own grant, and the database says so as well as the type.**
`brain.console.govern.Certification` refuses it in its constructor; `not_decided_by_its_subject`
refuses the row a hand-written statement would otherwise leave. The rule is worth having twice for
the reason `auth.principal`'s `bounded_engagement_expires` gives about its own.

**The table is named for the review and not for grants, on purpose.** `brain.ops.sweeps.
sweep_grant_isolation` finds grant-bearing tables by name, `%grant%` or `%pack%`, and a table of
decisions confers nothing: calling it `grant_certification` would put it on that list and have the
sweep hold a record of decisions to the rules for a record of reach.

**`certification` is a new ledger member, and the existing ones were each tried and rejected.**
GRANT answers "what did this person gain", and a kept grant gains nothing. REVOKE is a grant taken
away, and a removal already writes one from the grant trigger; recording the decision under it too
would put two revokes in the ledger for one lost capability. APPROVAL is a suspended action decided,
and a grant under review is not suspended. So a member, which is `brain.audit.ledger.AuditAction`'s
own precedent from COMPOSE_CHANGE onwards. Thirteen characters, inside the column's sixteen.

**A trigger rather than the route, for the reason `0003`, `0047` and `0050` give.** A decision
inserted by an operator's statement is recorded as well as one made from the console. The actor is
the row's own `decided_by`, which the row requires: unlike a removal, where nothing on the retired
row names the remover, the decision row names its author, so there is nothing to infer and nothing
to mark as inferred. The digest of the reach and the request's trace come from the settings the
application sets in the same transaction, as every other trigger here reads them.

**The subject is the grant, `grant:<id>`, for a direct row and for a pack assignment alike**, which
is the subject `0003`'s trigger already writes for both tables, so "everything that happened to this
grant" is one subject whichever table held it. Details carry the decision and the capability or the
pack's name, which are the two values the grant trigger already records as recordable.

**The append is `0003`'s, and this is a fourth copy of that block**, beside `0047`'s and `0050`'s,
for the reason `0047` gives against editing a function every grant in production goes through. Same
advisory lock, same sequence and parent read, same `obs.audit_entry_hash`, same refusal of a
discarded MERGE.

**The downgrade keeps what the ledger already holds**, for the reason `0026` gives: the action list
goes back `NOT VALID`, so an entry already carrying the new value stays and no new one is accepted.

Task ids: none
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("gate.review_decision",)

APP_ROLE = "brain_app"

#: `brain.tables.identity.PRINCIPAL_ID_CHARS`, copied for the reason `0009` gives about reading
#: live code from a migration.
PRINCIPAL_ID_CHARS = 128

#: Alphabetical, matching how `tables.identity.one_of` sorts.
WITH_CERTIFICATION = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'deny', "
    "'entity_merge', 'grant', 'leash_change', 'publish', 'record_read', 'revoke', 'session_end', "
    "'sign_in')"
)
WITHOUT_CERTIFICATION = (
    "action IN ('approval', 'break_glass', 'compose_change', 'deny', 'entity_merge', "
    "'grant', 'leash_change', 'publish', 'record_read', 'revoke', 'session_end', 'sign_in')"
)

#: What this migration replaces: `0050`'s action list, which is the one in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_CERTIFICATION: WITH_CERTIFICATION}

RLS: tuple[str, ...] = (
    "ALTER TABLE gate.review_decision ENABLE ROW LEVEL SECURITY",
    # Every row, for the reason `0003` gives the tables with no `deleted_at`: a decision is never
    # retired, so there is no live subset for a policy to narrow to, and who may read which
    # decision is `brain.console.govern`'s to decide over the grant it is about.
    """
    CREATE POLICY review_decision_visible ON gate.review_decision
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON gate.review_decision TO brain_app",)

REVIEW_DECISION_TRIGGER_FUNCTION = """
CREATE FUNCTION gate.record_review_decision() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_details jsonb;
    v_row_id text;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF NEW.grant_id IS NOT NULL THEN
        v_row_id := NEW.grant_id::text;
        v_details := jsonb_build_object(
            'decision', NEW.decision,
            'capability',
            COALESCE(
                (SELECT g.capability FROM gate.capability_grant g WHERE g.id = NEW.grant_id),
                'unknown'
            )
        );
    ELSE
        v_row_id := NEW.assignment_id::text;
        v_details := jsonb_build_object(
            'decision', NEW.decision,
            'pack',
            COALESCE(
                (SELECT k.name FROM gate.capability_pack k
                   JOIN gate.capability_pack_assignment a ON a.pack_id = k.id
                  WHERE a.id = NEW.assignment_id),
                'unknown'
            )
        );
    END IF;

    -- The append, as 0003's gate.record_entitlement_change, 0047's
    -- auth.record_sign_in_change and 0050's auth.record_session_end write it.
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
        v_seq, v_at, NEW.decided_by, 'certification', 'grant:' || v_row_id, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.decided_by, 'certification', 'grant:' || v_row_id,
                v_ent_hash, v_trace, v_details, v_prev, v_entry);

    GET DIAGNOSTICS v_written = ROW_COUNT;
    IF v_written <> 1 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'the ledger already holds seq ' || v_seq
                      || '; the audit entry was not appended',
            ERRCODE = 'restrict_violation',
            HINT = 'an append that is discarded silently is the failure this refuses';
    END IF;
    RETURN NULL;
END;
$$
"""

REVIEW_DECISION_TRIGGER = """
CREATE TRIGGER review_decision_is_audited
    AFTER INSERT ON gate.review_decision
    FOR EACH ROW EXECUTE FUNCTION gate.record_review_decision()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "review_decision",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "grant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("gate.capability_grant.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "assignment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("gate.capability_pack_assignment.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("decision IN ('keep', 'remove')", name="decision"),
        sa.CheckConstraint(
            "(grant_id IS NULL) <> (assignment_id IS NULL)", name="one_row_is_decided"
        ),
        sa.CheckConstraint("length(btrim(decided_by)) > 0", name="decided_by_present"),
        sa.CheckConstraint("decided_by <> principal_id", name="not_decided_by_its_subject"),
        schema="gate",
    )
    op.create_index(
        "ix_gate_review_decision_grant_id", "review_decision", ["grant_id"], schema="gate"
    )
    op.create_index(
        "ix_gate_review_decision_assignment_id",
        "review_decision",
        ["assignment_id"],
        schema="gate",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WITH_CERTIFICATION, schema="obs")
    op.execute(REVIEW_DECISION_TRIGGER_FUNCTION)
    op.execute(REVIEW_DECISION_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER review_decision_is_audited ON gate.review_decision")
    op.execute("DROP FUNCTION gate.record_review_decision()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", WITHOUT_CERTIFICATION, schema="obs", postgresql_not_valid=True
    )
    # The policies and the grants go with the table.
    op.drop_table("review_decision", schema="gate")
