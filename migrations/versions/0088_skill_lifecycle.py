"""A skill version is retired and a skill detached from an agent, each a row the ledger records.

`0056` stored a skill, a decision about it and its assignments, and nothing could take one back:
`brain.console.agent_tabs.detach` ran only inside a version replacement, and a version nobody
wanted assigned again stayed on offer for ever. This migration is the two tables that answer, the
two triggers that record them, and one trigger that refuses an assignment of retired bytes.
`brain.tables.skill` holds the model.

**Two tables, SELECT and INSERT only, for `0056`'s reason.** A retirement and a detachment are
facts about a moment, and a row rewritten is a record whose author changed afterwards. Nothing on
`agent.skill` is updated to say a version is retired: the skill row has no status column and the
application role holds no UPDATE on it, and giving it one to write a flag would be the edit the
table was built never to take.

**A retirement is keyed by the digest**, so a version is retired once and a second press is
refused by the key and writes nothing, which is `0056`'s construction for a second decision.
Reinstating a version is not built here; when it is, it is a row of its own naming the retirement,
and this key is what it will have to argue with.

**A detachment is its own table and not an action column on `agent.skill_assignment`, measured
both ways.** The column would need a default on an existing table, a check that `replaces_digest`
is empty for a detach, a second body for `0056`'s assignment trigger and a copy of the first body
in the downgrade, and the assignment's key into `agent.skill_review` would refuse the detachment of
bytes a template pinned and nobody approved in this library. The decisive cost is the rollback:
dropping the column on the way down leaves every detachment an older release reads as an
assignment, which is history changing its meaning after it was written. A table of its own drops
with its rows and leaves `0056`'s untouched. It carries the agent, the name and the digest, held to
`agent.skill` by the digest-and-name key an assignment uses, and names no assignment row: the
agent's current skills are read from its install, as `brain.skill_routes.pins_of` reads them, and
the rows are the history beside that, not a second answer to it.

**A retired digest cannot be newly assigned, in the database as well as in the domain.**
`refuse_assigning_a_retired_skill` runs before an assignment row is written and refuses one whose
digest has a retirement, so a statement that never came through `brain.console.skill_library` is
refused too. It takes the ledger's own advisory lock before it looks, which is the lock every
audited insert here already takes in its append: a retirement holds it from its own trigger until
it commits, so an assignment that looks while a retirement is being written waits and then sees it,
and the ledger's order and the refusal's answer cannot disagree about which came first. A key
cannot say "no row exists in another table", which is why this one rule is a trigger.

**The ledger grammar is not widened, because nothing new is written to it.** A retirement is the
existing `skill` member about the existing `skill` subject kind, with `retired` as its change,
beside `0056`'s imported, approved and rejected. A detachment is `compose_change` about the agent,
with the part `skills`, the folded name and the direction `detached`, exactly the details
`brain.audit.record.AuditRecorder.compose_change` writes, with the reason code `skill_detach`. The
database constrains the member and the subject and not the details, so there is no list here to
supersede and no check for a downgrade to re-add `NOT VALID`.

**The append is `0003`'s, another copy of the block `0056` and `0059` carry**, for the reason `0047`
gives against editing a function every grant in production goes through.

**The downgrade keeps what the ledger already holds.** The triggers and the tables go; their ledger
entries stay, because nothing may delete one. An older release loads a `skill` entry saying
`retired` as it loads any other: `brain.audit.ledger.AuditEntry` admits a detail that is a field
name and keeps no list of a member's change words.

Task ids: M27.11.8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0088"
down_revision = "0083"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.skill_retirement", "agent.skill_detachment")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.skill` and `brain.audit.ledger` by
#: `tests/unit/test_skill_store.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128

#: The details the triggers write, as `AuditRecorder` spells them. Written out literally in the
#: functions below as well; a test holds the two equal.
PART = "skills"
DETACH_REASON = "skill_detach"
RETIRED = "retired"

#: The advisory lock `0003`'s append takes, which the refusal below takes before it looks.
LEDGER_LOCK = 8274419004

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
    CREATE POLICY skill_retirement_made_in_the_sessions_name ON agent.skill_retirement
        FOR INSERT TO brain_app
        WITH CHECK (retired_by = {PRINCIPAL})
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

#: SELECT and INSERT, and never UPDATE or DELETE. Exactly what `brain.ops.skill_store` sends: an
#: insert that returns its key, and the reads of the library and its history.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.skill_retirement TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_detachment TO brain_app",
)

#: The append every trigger below makes, as `0003`, `0054`, `0056` and `0059` write it. `{actor}`,
#: `{action}`, `{subject}` and `{details}` are the four expressions that differ.
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

#: The name of the skill a retirement's key names. The key into `agent.skill` guarantees the row.
_SKILL_NAME_OF_THE_RETIREMENT = """
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;"""

#: A retirement: the person, the name of the skill the key names, `retired` and the bytes.
SKILL_RETIREMENT_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_skill_retirement() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text;
    v_details jsonb := jsonb_build_object('change', 'retired', 'digest', NEW.digest);"""
    + _DECLARE
    + """BEGIN"""
    + _SKILL_NAME_OF_THE_RETIREMENT
    + _APPEND.format(
        actor="NEW.retired_by", action="skill", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

#: A detachment: the person, the agent, and the skill's folded name taken off it, and why.
SKILL_DETACHMENT_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_skill_detachment() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object(
        'part', 'skills', 'reference', replace(NEW.skill_name, '-', '_'),
        'direction', 'detached', 'reason_code', 'skill_detach'
    );"""
    + _DECLARE
    + """BEGIN"""
    + _APPEND.format(
        actor="NEW.detached_by", action="compose_change", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

#: The refusal of an assignment of retired bytes. See the module docstring for the lock.
REFUSE_RETIRED_ASSIGNMENT_FUNCTION = """
CREATE FUNCTION agent.refuse_assigning_a_retired_skill() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(8274419004);
    IF EXISTS (SELECT 1 FROM agent.skill_retirement r WHERE r.digest = NEW.digest) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'skill ' || NEW.digest || ' is retired and cannot be newly assigned',
            ERRCODE = 'restrict_violation',
            HINT = 'an agent already pinned to it keeps it until it is detached';
    END IF;
    RETURN NEW;
END;
$$
"""

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
    """
    CREATE TRIGGER a_retired_skill_is_not_assigned
        BEFORE INSERT ON agent.skill_assignment
        FOR EACH ROW EXECUTE FUNCTION agent.refuse_assigning_a_retired_skill()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "skill_retirement",
        sa.Column("digest", sa.String(64), primary_key=True, nullable=False),
        sa.Column("retired_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"retired_by ~ '{IDENTIFIER}'", name="retired_by_is_an_identifier"),
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
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("skill_name", sa.String(80), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("detached_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(f"detached_by ~ '{IDENTIFIER}'", name="detached_by_is_an_identifier"),
        sa.ForeignKeyConstraint(
            ["digest", "skill_name"],
            ["agent.skill.digest", "agent.skill.name"],
        ),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(SKILL_RETIREMENT_TRIGGER_FUNCTION)
    op.execute(SKILL_DETACHMENT_TRIGGER_FUNCTION)
    op.execute(REFUSE_RETIRED_ASSIGNMENT_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER a_retired_skill_is_not_assigned ON agent.skill_assignment")
    op.execute("DROP TRIGGER skill_detachment_is_audited ON agent.skill_detachment")
    op.execute("DROP TRIGGER skill_retirement_is_audited ON agent.skill_retirement")
    op.execute("DROP FUNCTION agent.refuse_assigning_a_retired_skill()")
    op.execute("DROP FUNCTION agent.record_skill_detachment()")
    op.execute("DROP FUNCTION agent.record_skill_retirement()")
    # The policies and the grants go with the tables.
    op.drop_table("skill_detachment", schema="agent")
    op.drop_table("skill_retirement", schema="agent")
