"""A skill version's export and a rehearsal of its examples are each a row, with a ledger entry.

M12.3.1 asks that an administrator export an approved skill as a package another install can
import. `brain.console.skill_library.exported` builds the package; this records that it was built,
because a package is how a skill leaves the install and "who took which version, and when" has to
be answerable from the ledger.

**`agent.skill_export`, one row per export.** It names the version by its digest, held to
`agent.skill` by a key, and who exported it. The insert trigger appends a `skill` entry about the
skill's name with the change `exported` and the digest, `0139`'s shape for a retirement.

**`agent.skill_rehearsal`, one row per rehearsal of a version's examples (M12.3.4).** It names the
version, the kind of rehearsal, the agent it was rehearsed through, whether every example passed and
each example's outcome. Approval reads these rows for the exact digest it is asked about. `kind` is
held to a grammar rather than a list, so a rehearsal that runs a model is a new word in the same
table and needs no migration. The trigger appends a `skill` entry with the change `rehearsed`, the
digest, the kind and whether it passed, and never an example's task, which is the author's prose.

**SELECT and INSERT only, read whole and written in the session's own name**, `0056`'s shape and
reason: an insert policy admitting a row whose actor column is the session's principal means a
request cannot record an export in somebody else's name.

**The downgrade drops the table and its function**, and the ledger entries stay, because nothing
may delete one: `0056`'s reason.

Task ids: M12.3.1, M12.3.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0191"
# Written over 0178, the head of origin/main on the day; re-pointed at its turn in the train. Its
# trigger appends `skill`, already in the action list, and it re-states no constraint.
down_revision = "0178"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.skill_export", "agent.skill_rehearsal")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.skill` by `tests/unit/test_skill_export.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
DIGEST_CHARS = 64
AGENT_ID_CHARS = 128
REHEARSAL_KIND_PATTERN = r"^[a-z]{1,16}$"
REHEARSAL_KIND_CHARS = 16

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_export ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_export_readable ON agent.skill_export
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_export_made_in_the_sessions_name ON agent.skill_export
        FOR INSERT TO brain_app
        WITH CHECK (exported_by = {PRINCIPAL})
    """,
    "ALTER TABLE agent.skill_rehearsal ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_rehearsal_readable ON agent.skill_rehearsal
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_rehearsal_made_in_the_sessions_name ON agent.skill_rehearsal
        FOR INSERT TO brain_app
        WITH CHECK (rehearsed_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: an export is a new row.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.skill_export TO brain_app",
    "GRANT SELECT, INSERT ON agent.skill_rehearsal TO brain_app",
)

#: The append every trigger below makes, copied from `0139`, which copied `0121`, `0056` and `0003`.
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


#: An export, about the name of the skill the key names.
SKILL_EXPORT_TRIGGER_FUNCTION = _function(
    "agent.record_skill_export",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object('change', 'exported', 'digest', NEW.digest);""",
    """
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;""",
    actor="NEW.exported_by",
    action="skill",
)

#: A rehearsal, about the name of the skill the key names, with whether it passed.
SKILL_REHEARSAL_TRIGGER_FUNCTION = _function(
    "agent.record_skill_rehearsal",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object(
        'change', 'rehearsed', 'digest', NEW.digest, 'kind', NEW.kind, 'passed', NEW.passed
    );""",
    """
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;""",
    actor="NEW.rehearsed_by",
    action="skill",
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER skill_export_is_audited
        AFTER INSERT ON agent.skill_export
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_export()
    """,
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
        "skill_export",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("exported_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"exported_by ~ '{IDENTIFIER}'", name="exported_by_is_an_identifier"),
        sa.ForeignKeyConstraint(["digest"], ["agent.skill.digest"]),
        schema="agent",
    )
    op.create_table(
        "skill_rehearsal",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("kind", sa.String(REHEARSAL_KIND_CHARS), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("outcomes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rehearsed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"kind ~ '{REHEARSAL_KIND_PATTERN}'", name="kind_shape"),
        sa.CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        sa.CheckConstraint(f"rehearsed_by ~ '{IDENTIFIER}'", name="rehearsed_by_is_an_identifier"),
        sa.CheckConstraint("jsonb_typeof(outcomes) = 'array'", name="outcomes_are_a_list"),
        sa.ForeignKeyConstraint(["digest"], ["agent.skill.digest"]),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(SKILL_EXPORT_TRIGGER_FUNCTION)
    op.execute(SKILL_REHEARSAL_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER skill_rehearsal_is_audited ON agent.skill_rehearsal")
    op.execute("DROP TRIGGER skill_export_is_audited ON agent.skill_export")
    op.execute("DROP FUNCTION agent.record_skill_rehearsal()")
    op.execute("DROP FUNCTION agent.record_skill_export()")
    op.drop_table("skill_rehearsal", schema="agent")
    op.drop_table("skill_export", schema="agent")
