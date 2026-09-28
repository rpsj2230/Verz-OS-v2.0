"""A skill version can be retired and reinstated, and a skill detached from an agent, each as a row.

`0056` stored a skill, a decision and an assignment, and nothing that ends one. The Wave 2 skills
lifecycle (W2.8: M27.11.8, M27.15.55, M27.15.56) needs two things, and `brain.tables.skill` holds
the argument for each column; this is how they arrive.

**`agent.skill_retirement`, one row per change.** A row names a version by its digest and says
whether it is retired from that moment (`retired` true) or reinstated (`retired` false). The newest
row for a digest is its state, and a digest with no row was never retired, which is the shape
`0121` gave categories: the rows before the newest are what it was. Held to `agent.skill` by a key,
because a retirement of bytes nobody added would be a statement about nothing.

**`agent.skill_detachment`, one row per skill taken off an agent.** It names the agent, the skill,
the bytes it ran and, when the skill got there by an assignment, that assignment, held by a key and
unique, so one assignment is ended at most once. A skill a template pinned has no assignment to
name and is detached with the column empty. The current assignments are those no detachment names
and no later assignment of the same skill to the same agent replaced
(`brain.console.skill_library.current_assignments`), so nothing is ever updated to say one ended.

**SELECT and INSERT only, read whole and written in the session's own name**, `0056`'s shape and
reason: who may see the library is the console's decision, and an insert policy admitting a row
whose actor column is the session's principal means a request cannot retire or detach in somebody
else's name.

**Each insert appends to the ledger in the same transaction.** A retirement or a reinstatement is a
`skill` entry about the skill's name, with the change and the digest, as `0121`'s import and
decision entries are. A detachment is a `compose_change` about the agent with the details
`AuditRecorder.compose_change` writes for `brain.console.skill_library.ledger_reference`,
direction `detached` and reason `skill_detach`, beside `0056`'s `skill_assign` and
`skill_replace`, so "when did this agent stop running it" has an entry whichever way it stopped.

**The downgrade drops both tables and both functions**, and their ledger entries stay, because
nothing may delete one: `0056`'s reason.

Task ids: M27.11.8, M27.15.55, M27.15.56
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0139"
# Written over 0133, the newest on origin/main then; landed in one train behind 0136, 0137, 0118
# and 0138, so it follows the newest of them. Its triggers append `skill` and `compose_change`, both
# already in the action list every one of those leaves, and it re-states no constraint.
down_revision = "0138"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. The detachment
#: points at an assignment, so it follows it; both point at the skill.
TABLES: tuple[str, ...] = ("agent.skill_retirement", "agent.skill_detachment")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.skill` by `tests/unit/test_skill_lifecycle.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
DIGEST = r"^[0-9a-f]{64}$"
SKILL_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,79}$"
PRINCIPAL_ID_CHARS = 128
AGENT_ID_CHARS = 128
NAME_CHARS = 80
DIGEST_CHARS = 64

#: The details the detachment trigger writes, as `AuditRecorder.compose_change` spells them.
PART = "skills"
DETACH_REASON = "skill_detach"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_retirement ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.skill_detachment ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_retirement_readable ON agent.skill_retirement
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_retirement_set_in_the_sessions_name ON agent.skill_retirement
        FOR INSERT TO brain_app
        WITH CHECK (set_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY skill_detachment_readable ON agent.skill_detachment
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_detachment_made_in_the_sessions_name ON agent.skill_detachment
        FOR INSERT TO brain_app
        WITH CHECK (detached_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a change is a new row.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.skill_retirement TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_detachment TO brain_app",
)

#: The append every trigger below makes, copied from `0121`, which copied `0056` and `0003`.
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


def _function(name: str, head: str, body: str, *, actor: str, action: str) -> str:
    """One trigger function: its declarations, anything before the append, and the append."""
    return (
        f"""
CREATE FUNCTION {name}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE{head}"""
        + _DECLARE
        + """BEGIN"""
        + body
        + _APPEND.format(actor=actor, action=action, subject="v_subject", details="v_details")
        + """    RETURN NULL;
END;
$$
"""
    )


#: A retirement or a reinstatement, about the name of the skill the key names.
SKILL_RETIREMENT_TRIGGER_FUNCTION = _function(
    "agent.record_skill_retirement",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object(
        'change', CASE WHEN NEW.retired THEN 'retired' ELSE 'reinstated' END,
        'digest', NEW.digest
    );""",
    """
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;""",
    actor="NEW.set_by",
    action="skill",
)

#: A detachment, about the agent, under the folded name `0056`'s assignment trigger records.
SKILL_DETACHMENT_TRIGGER_FUNCTION = _function(
    "agent.record_skill_detachment",
    """
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object(
        'part', 'skills', 'reference', replace(NEW.skill_name, '-', '_'),
        'direction', 'detached', 'reason_code', 'skill_detach'
    );""",
    "",
    actor="NEW.detached_by",
    action="compose_change",
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER skill_retirement_is_audited
        AFTER INSERT ON agent.skill_retirement
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_retirement()
    """,
    """
    CREATE TRIGGER skill_detachment_is_audited
        AFTER INSERT ON agent.skill_detachment
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_detachment()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "skill_retirement",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("set_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        sa.ForeignKeyConstraint(["digest"], ["agent.skill.digest"]),
        schema="agent",
    )
    op.create_table(
        "skill_detachment",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("skill_name", sa.String(NAME_CHARS), nullable=False),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("detached_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(f"skill_name ~ '{SKILL_NAME_PATTERN}'", name="skill_name_shape"),
        sa.CheckConstraint(f"digest ~ '{DIGEST}'", name="digest_shape"),
        sa.CheckConstraint(f"detached_by ~ '{IDENTIFIER}'", name="detached_by_is_an_identifier"),
        sa.UniqueConstraint("assignment_id", name="uq_skill_detachment_assignment_id"),
        sa.ForeignKeyConstraint(["assignment_id"], ["agent.skill_assignment.id"]),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(SKILL_RETIREMENT_TRIGGER_FUNCTION)
    op.execute(SKILL_DETACHMENT_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER skill_detachment_is_audited ON agent.skill_detachment")
    op.execute("DROP TRIGGER skill_retirement_is_audited ON agent.skill_retirement")
    op.execute("DROP FUNCTION agent.record_skill_detachment()")
    op.execute("DROP FUNCTION agent.record_skill_retirement()")
    # The policies and the grants go with the tables; the detachment first, as it points at an
    # assignment and the retirement only at a skill.
    op.drop_table("skill_detachment", schema="agent")
    op.drop_table("skill_retirement", schema="agent")
