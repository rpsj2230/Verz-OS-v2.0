"""A decided suspension carries its verdict and reason, and the database writes its approval entry.

`gate.suspension` recorded who decided a suspension and when, and `brain.console.approvals.decide`
wrote the verdict and the reason to a ledger writer in the process. No writer for `obs.audit_entry`
existed, so `brain.app.suspension_store_for` built no store that could decide, and an approval on a
running install could be read and never decided. This migration is the two columns, their checks,
the grant and the trigger that make the decision and its entry one write.

**Two columns, `verdict` and `reason_code`, because the trigger can read only the row.** Until now
the row deliberately held no reason, for `brain.tables.suspension`'s argument that a reason beside
the ledger's is a second copy. With the entry written by the database there is no first copy to
duplicate: the row is the only place the verdict and the reason exist before the entry does, and
the entry is derived from it in the same transaction. `brain.tables.suspension` records the change
of mind.

**The checks keep the ledger's rules, because `redact_details` does not run in the database.**
`brain.audit.record.AuditRecorder.approval` refuses prose where a reason code belongs, a rejection
without a reason and an approval with one, and until now nothing reached the ledger without passing
it. The trigger copies the columns into the entry, so the table refuses what the recorder refuses: a
reason code in the recorder's grammar, a reason on every verdict except an approval, none on a
pending row, and a verdict that agrees with the state `resume` reads, `approved` for `approved` and
the others for `rejected`, as `brain.console.approvals.DOES_NOT_RUN` maps them.

**Three verdicts, not the recorder's four.** An amendment is recorded against the digest of the
action substituted for the original, and the row holds only the original's, so an amended entry
written from it would name the wrong action. The row refuses one until it holds the replacement's
digest; see `brain.tables.suspension`, which names the reason.

**UPDATE on the two columns, and no policy changes.** `0042`'s update policy already admits only a
pending row the session may approve and checks that the new state names the session's principal,
and the checks above make a decided row name its verdict. The insert policy admits only a pending
row, which the checks hold to no verdict and no reason.

**The trigger fires on the change from pending to decided, and on an insert already decided.** An
update of a pending row that leaves it pending appends nothing, and neither does an update of a row
already decided. The actor is the row's own `decided_by`, which the update policy pins to
`app.principal_id`; the subject is `leash:<id>`, which `AuditRecorder.approval` argues; the details
are the verdict, the row's `action_digest` and, when there is one, the reason code, which is that
method's shape. An insert already decided is refused to the application role and open to an
operator's statement, and records the decision for `0054`'s reason.

**What this does not record, stated.** An operator's statement that edits a decided row, changing
its verdict or moving it back to pending, appends nothing: the application role cannot write
either, and the row then no longer agrees with its entry, which is the gap to close if an undone
decision is ever something an install needs to see. The digest of the decider's reach and the
request's trace are the settings `brain.gate.suspension_store` sets in the transaction; a statement
that set neither gets the unsupplied sentinel and the transaction's own id.

**The append is `0003`'s, and this is another copy of that block**, beside `0059`'s and `0062`'s,
for the reason `0047` gives against editing a function every grant in production goes through. Same
advisory lock, same sequence and parent read, same `obs.audit_entry_hash`, same refusal of a
discarded MERGE. No action and no subject kind is added: `approval` has been a member since `0023`
and `leash` a kind since `0002`.

**The upgrade refuses a decided row with no verdict, which is correct.** Nothing in the product
inserts a suspension (`brain.gate.suspension_store.put_suspension` has no caller in `src`), so every
install's table is empty; a decided row there was written by hand, was never recorded, and has no
verdict anybody could supply without inventing one.

**The downgrade drops the trigger, the function, the checks and both columns.** The entries already
written stay in the ledger, which cannot be edited; the verdicts and reasons on the rows go.

Task ids: M27.9.3

Revision ID: 0083
Revises: 0082
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.suspension` and `brain.audit.record.REASON_CODE` by
#: `tests/unit/test_suspension_store.py`.
VERDICT_CHARS = 16
REASON_CODE_CHARS = 64
REASON_CODE_PATTERN = "^[a-z][a-z0-9_]{1,60}$"
#: `brain.tables.suspension.RECORDED_VERDICTS`, sorted as `one_of` sorts.
VERDICT_IN = "verdict IN ('approved', 'rejected', 'taken_over')"

#: The checks, by their bare names: alembic applies the naming convention on top. See `0030`.
CHECKS: tuple[tuple[str, str], ...] = (
    ("verdict", VERDICT_IN),
    ("a_decided_suspension_names_its_verdict", "(verdict IS NULL) = (state = 'pending')"),
    (
        "a_verdict_agrees_with_the_state_resume_reads",
        "verdict IS NULL OR (verdict = 'approved') = (state = 'approved')",
    ),
    ("reason_code_grammar", f"reason_code IS NULL OR reason_code ~ '{REASON_CODE_PATTERN}'"),
    (
        "every_verdict_but_an_approval_says_why",
        "(reason_code IS NULL) = (verdict IS NULL OR verdict = 'approved')",
    ),
)

GRANTS: tuple[str, ...] = ("GRANT UPDATE (verdict, reason_code) ON gate.suspension TO brain_app",)

#: The decision, recorded once, as `AuditRecorder.approval` writes it. The append block is `0059`'s.
TRIGGER_FUNCTION = """
CREATE FUNCTION gate.record_suspension_decision() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'leash:' || NEW.id;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF NEW.state = 'pending' THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.state <> 'pending' THEN
        RETURN NULL;
    END IF;

    v_details := jsonb_build_object('verdict', NEW.verdict, 'action_digest', NEW.action_digest);
    IF NEW.reason_code IS NOT NULL THEN
        v_details := v_details || jsonb_build_object('reason_code', NEW.reason_code);
    END IF;

    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(
        NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32)
    );
    v_trace := COALESCE(
        NULLIF(current_setting('brain.trace_id', true), ''),
        'tx.' || pg_current_xact_id()::text
    );
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, NEW.decided_by, 'approval', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.decided_by, 'approval', v_subject,
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

TRIGGER = """
CREATE TRIGGER suspension_decision_is_audited
    AFTER INSERT OR UPDATE ON gate.suspension
    FOR EACH ROW EXECUTE FUNCTION gate.record_suspension_decision()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    op.add_column(
        "suspension", sa.Column("verdict", sa.String(VERDICT_CHARS), nullable=True), schema="gate"
    )
    op.add_column(
        "suspension",
        sa.Column("reason_code", sa.String(REASON_CODE_CHARS), nullable=True),
        schema="gate",
    )
    for name, condition in CHECKS:
        op.create_check_constraint(name, "suspension", condition, schema="gate")
    for statement in GRANTS:
        op.execute(statement)
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER suspension_decision_is_audited ON gate.suspension")
    op.execute("DROP FUNCTION gate.record_suspension_decision()")
    # The column grant goes with the columns.
    for name, _ in reversed(CHECKS):
        op.drop_constraint(name, "suspension", schema="gate", type_="check")
    op.drop_column("suspension", "reason_code", schema="gate")
    op.drop_column("suspension", "verdict", schema="gate")
