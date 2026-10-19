"""A template version can be withdrawn from new installs, and the withdrawal undone, each as a row.

`agent.template_version` is SELECT and INSERT only: a published manifest is never amended, and
every agent installed from one pins its digest. So hiding a version from the gallery cannot be a
column on it, and it cannot be a delete. This is the second table the architecture asked for, the
insert-only row (docs/admin-console-architecture.md, C2: "Arch M: withdraw a version (insert-only
row). Rest M: undo a withdrawal"), and it is `0139`'s `agent.skill_retirement` for a template.

**`agent.template_withdrawal`, one row per change.** A row names a version by its template id and
number and says whether it is withdrawn from that moment (`withdrawn` true) or the withdrawal is
undone (`withdrawn` false). The newest row for a version is its state, and a version with no row was
never withdrawn: the rows before the newest are what it was, so nothing is ever updated to say a
withdrawal ended. Held to `agent.template_version` by its composite key, because withdrawing a
version nobody published would be a statement about nothing. **The key is also why an installed
agent stays pinned**: nothing here touches `agent.template_instance`, and an instance reads its
version row whether or not a withdrawal names it.

**A withdrawal carries a reason and an undo may.** A withdrawal with no sentence is a hidden version
nobody can later explain, so the check constraint refuses one; the reason is for the people who
read the Templates page and is not put in the ledger, whose details admit field names and digests
and redact prose.

**SELECT and INSERT only, read whole and written in the session's own name**, `0139`'s shape and
reason: who may see a withdrawal is the console's decision, and an insert policy admitting a row
whose actor column is the session's principal means a request cannot withdraw in somebody else's
name.

**Each insert appends to the ledger in the same transaction.** A withdrawal or an undo is a
`publish` entry about the version (`artifact:<template>.v<n>`, the subject `0104` gave a version's
arrival) whose details say `withdrawn` or `withdrawal_undone`, as `AuditRecorder.template_version`
writes them, so "when did this version stop being offered, and who turned it back on" has an entry
beside the one for its publication.

**The downgrade drops the table and the function**, and the ledger entries stay, because nothing
may delete one: `0056`'s reason.

Task ids: M27.15.35

Revision ID: 0261
Revises: 0250
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0261"
# Written over 0250, the newest on origin/main when it was re-pointed. The coordinator re-points it
# when the migration train is built, as every migration landed in a train is.
down_revision = "0250"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.template_withdrawal",)

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.template_withdrawal` by `tests/unit/test_template_withdrawal.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
AGENT_ID_CHARS = 60
REASON_CHARS = 240

#: The words the trigger writes, as `AuditRecorder.template_version` spells them.
WITHDRAWN_WORD = "withdrawn"
UNDONE_WORD = "withdrawal_undone"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.template_withdrawal ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY template_withdrawal_readable ON agent.template_withdrawal
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY template_withdrawal_set_in_the_sessions_name ON agent.template_withdrawal
        FOR INSERT TO brain_app
        WITH CHECK (set_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a change is a new row.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.template_withdrawal TO brain_app",)

#: The append every trigger here makes, copied from `0139`, which copied `0121`, `0056` and `0003`.
_APPEND = """
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
            v_seq, v_at, {actor}, '{action}', {subject}, v_ent_hash,
            v_trace, {details}, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, {actor}, '{action}', {subject},
                    v_ent_hash, v_trace, {details}, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
"""

_DECLARE = """
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

#: A withdrawal or its undoing, about the version it names.
TEMPLATE_WITHDRAWAL_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_template_withdrawal() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'artifact:' || NEW.template_id || '.v' || NEW.version::text;
    v_details jsonb := jsonb_build_object(
        'change', CASE WHEN NEW.withdrawn THEN 'withdrawn' ELSE 'withdrawal_undone' END
    );"""
    + _DECLARE
    + """BEGIN"""
    + _APPEND.format(actor="NEW.set_by", action="publish", subject="v_subject", details="v_details")
    + """    RETURN NULL;
END;
$$
"""
)

TRIGGER = """
    CREATE TRIGGER template_withdrawal_is_audited
        AFTER INSERT ON agent.template_withdrawal
        FOR EACH ROW EXECUTE FUNCTION agent.record_template_withdrawal()
    """


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "template_withdrawal",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("template_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("withdrawn", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=True),
        sa.Column("set_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="version_is_positive"),
        sa.CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        sa.CheckConstraint(
            "reason IS NULL OR length(btrim(reason)) > 0", name="a_reason_is_a_sentence"
        ),
        sa.CheckConstraint("NOT withdrawn OR reason IS NOT NULL", name="a_withdrawal_says_why"),
        sa.ForeignKeyConstraint(
            ["template_id", "version"],
            ["agent.template_version.template_id", "agent.template_version.version"],
        ),
        schema="agent",
    )
    op.create_index(
        "ix_agent_template_withdrawal_version",
        "template_withdrawal",
        ["template_id", "version", "seq"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(TEMPLATE_WITHDRAWAL_TRIGGER_FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER template_withdrawal_is_audited ON agent.template_withdrawal")
    op.execute("DROP FUNCTION agent.record_template_withdrawal()")
    # The policies, the grants and the index go with the table.
    op.drop_table("template_withdrawal", schema="agent")
