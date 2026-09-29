"""A skill keeps its scripts' bytes and its example tasks, and a rehearsal of them is a row.

`0056` stored a skill as its `SKILL.md` and nothing else, so a skill declaring scripts was refused
at the door: the digest covered a script's name and not its bytes. The skill packages
(M12.4.11, M12.3.4, M12.3.1) need three things of the tables, and `brain.tables.skill` holds the
argument for each column; this is how they arrive.

**`agent.skill_script`, one row per declared script of a version, holding its bytes.** Keyed by the
skill's digest and the script's path, and held to `agent.skill` by the digest and the importer
together, the composite key `0056` gave a decision, so a script belongs to exactly those bytes and
was written by the person who added them. `content_sha256_is_of_its_content` holds the recorded
sha256 to the bytes, and the application may insert and read and never update, so a script cannot
be changed under the digest a reviewer approved, which covers that sha256.

**`agent.skill_example`, one row per example task, in the order a reviewer read them**, held to the
skill row the same way.

**`agent.skill_rehearsal`, one row per rehearsal of a version's examples.** A verdict per example
in `behaved` and `passed`, which `passed_when_no_example_failed` holds to the verdicts, so a row
cannot say it passed while recording an example that did not behave. The newest row for a digest
decides whether that version may be approved. A trigger appends every rehearsal to the ledger as a
`skill` entry about the skill's name, with the digest and `outcome` `passed` or `failed`, which
`AuditRecorder.skill` spells the same way.

**SELECT and INSERT only, read whole and written in the session's own name**, `0056`'s shape and
reason: who may see the library is the console's decision, and an insert policy admitting a row
whose actor column is the session's principal means a request cannot add a script or record a
rehearsal in somebody else's name.

**Three new tables and no change to one that exists**, so the release still running during a
deploy writes the skill rows it always wrote, and reads a skill with scripts or examples without
them: it digests that skill differently from its key and treats it as changed since approval,
refusing to run, assign or decide it, which is the safe direction.

**The downgrade drops the three tables and the trigger function**, losing the scripts, the examples
and the rehearsals, which is the only reversal a table addition has. Their skills stay, and read
under the previous release as changed since approval for the reason above. The ledger entries stay,
because nothing may delete one: `0056`'s reason.

Revises `0152`, the head of the branch this is written on (the change-signals package, which lands
first); `0153` to `0163` belong to other packages in flight.

Task ids: M12.4.11, M12.3.4, M12.3.1

Revision ID: 0164
Revises: 0152
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0164"
down_revision = "0152"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. All three point
#: at `agent.skill`.
TABLES: tuple[str, ...] = ("agent.skill_script", "agent.skill_example", "agent.skill_rehearsal")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.skill` by `tests/unit/test_skill_packages.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
DIGEST = r"^[0-9a-f]{64}$"
SCRIPT_PATH_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$"
PRINCIPAL_ID_CHARS = 128
DIGEST_CHARS = 64
SCRIPT_PATH_CHARS = 200
MAX_SCRIPT_BYTES = 256 * 1024
MAX_EXAMPLES = 20
EXAMPLE_CHARS = 500

#: The two rules the model names, copied for the same reason.
SCRIPT_SHA256_IS_OF_ITS_CONTENT = "content_sha256 = encode(sha256(content), 'hex')"
PASSED_WHEN_NO_EXAMPLE_FAILED = "passed = (NOT (behaved @> '[false]'::jsonb))"

#: The two words a rehearsal's entry says, as `brain.audit.record.RehearsalOutcome` spells them.
PASSED = "passed"
FAILED = "failed"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_script ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.skill_example ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.skill_rehearsal ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_script_readable ON agent.skill_script
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_script_added_in_the_sessions_name ON agent.skill_script
        FOR INSERT TO brain_app
        WITH CHECK (submitted_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY skill_example_readable ON agent.skill_example
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_example_added_in_the_sessions_name ON agent.skill_example
        FOR INSERT TO brain_app
        WITH CHECK (submitted_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY skill_rehearsal_readable ON agent.skill_rehearsal
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_rehearsal_recorded_in_the_sessions_name ON agent.skill_rehearsal
        FOR INSERT TO brain_app
        WITH CHECK (rehearsed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a script's bytes and a rehearsal are facts.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.skill_script TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_example TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_rehearsal TO brain_app",
)

#: A rehearsal, about the name of the skill the key names, copied from `0139`'s append, which
#: copied `0121`, `0056` and `0003`. `PASSED` and `FAILED` are written out rather than formatted in,
#: and a test holds the function to them.
SKILL_REHEARSAL_TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_skill_rehearsal() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text;
    v_details jsonb := jsonb_build_object(
        'change', 'rehearsed',
        'digest', NEW.digest,
        'outcome', CASE WHEN NEW.passed THEN 'passed' ELSE 'failed' END
    );
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;

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
        v_seq, v_at, NEW.rehearsed_by, 'skill', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, NEW.rehearsed_by, 'skill', v_subject,
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

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER skill_rehearsal_is_audited
        AFTER INSERT ON agent.skill_rehearsal
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_rehearsal()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "skill_script",
        sa.Column("skill_digest", sa.String(DIGEST_CHARS), primary_key=True, nullable=False),
        sa.Column("path", sa.String(SCRIPT_PATH_CHARS), primary_key=True, nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_sha256", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("submitted_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"skill_digest ~ '{DIGEST}'", name="skill_digest_shape"),
        sa.CheckConstraint(f"path ~ '{SCRIPT_PATH_PATTERN}'", name="path_shape"),
        sa.CheckConstraint(f"content_sha256 ~ '{DIGEST}'", name="content_sha256_shape"),
        sa.CheckConstraint(
            SCRIPT_SHA256_IS_OF_ITS_CONTENT, name="content_sha256_is_of_its_content"
        ),
        sa.CheckConstraint(
            f"octet_length(content) <= {MAX_SCRIPT_BYTES}", name="content_is_a_script"
        ),
        sa.CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_is_an_identifier"),
        sa.ForeignKeyConstraint(
            ["skill_digest", "submitted_by"], ["agent.skill.digest", "agent.skill.submitted_by"]
        ),
        schema="agent",
    )
    op.create_table(
        "skill_example",
        sa.Column("skill_digest", sa.String(DIGEST_CHARS), primary_key=True, nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True, nullable=False),
        sa.Column("task", sa.String(EXAMPLE_CHARS), nullable=False),
        sa.Column("expected", sa.String(EXAMPLE_CHARS), nullable=False),
        sa.Column("submitted_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"skill_digest ~ '{DIGEST}'", name="skill_digest_shape"),
        sa.CheckConstraint(
            f"ordinal BETWEEN 1 AND {MAX_EXAMPLES}", name="ordinal_is_one_of_the_examples"
        ),
        sa.CheckConstraint("length(btrim(task)) > 0", name="task_present"),
        sa.CheckConstraint("length(btrim(expected)) > 0", name="expected_present"),
        sa.CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_is_an_identifier"),
        sa.ForeignKeyConstraint(
            ["skill_digest", "submitted_by"], ["agent.skill.digest", "agent.skill.submitted_by"]
        ),
        schema="agent",
    )
    op.create_table(
        "skill_rehearsal",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("behaved", postgresql.JSONB(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("rehearsed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "CASE WHEN jsonb_typeof(behaved) = 'array' "
            f"THEN jsonb_array_length(behaved) BETWEEN 1 AND {MAX_EXAMPLES} ELSE false END",
            name="behaved_is_a_verdict_per_example",
        ),
        sa.CheckConstraint(PASSED_WHEN_NO_EXAMPLE_FAILED, name="passed_when_no_example_failed"),
        sa.CheckConstraint(f"rehearsed_by ~ '{IDENTIFIER}'", name="rehearsed_by_is_an_identifier"),
        sa.ForeignKeyConstraint(["digest"], ["agent.skill.digest"]),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(SKILL_REHEARSAL_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER skill_rehearsal_is_audited ON agent.skill_rehearsal")
    op.execute("DROP FUNCTION agent.record_skill_rehearsal()")
    # The policies and the grants go with the tables.
    op.drop_table("skill_rehearsal", schema="agent")
    op.drop_table("skill_example", schema="agent")
    op.drop_table("skill_script", schema="agent")
