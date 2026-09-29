"""An agent's drafts, their revisions and what was done to each, every one of them on the ledger.

`brain.builder.drafts` named the tables a draft needs and left them unwritten, so a draft could not
outlive a restart and the console had no New agent and no Edit as a draft. These are those tables,
for a draft of one agent (`brain.builder.agent_drafts`), and `brain.tables.manifest_draft` holds the
argument for each column.

**`agent.manifest_draft`**: who started it, which agent it makes (its id minted then) or changes,
and for an edit the configuration digest it started from. **`agent.manifest_revision`**: one row per
save, the whole document, numbered from one. **`agent.manifest_act`**: one row per act on a
revision (checked, requested, approved, declined, published), at most once each. Where a draft
stands is read off its latest revision's acts and never stored.

**SELECT and INSERT only, written in the session's own name**, `0136`'s and `0139`'s shape: a save
is a new revision and an approval is a new row, so nothing is ever updated to say what happened,
and a row naming somebody other than `app.principal_id` as its owner, saver or actor is refused.
Who may open a draft is the console's decision (its owner, and a person who could approve it),
so the reads are whole.

**Each insert appends one `publish` entry about the agent, in the same transaction.** The subject is
`agent:<id>`, which is where the agent's own lifecycle entries (`0137`), its hand-overs (`0105`) and
its leash moves (`0104`) already are, so an agent's history reads as one subject from its first
draft to its archive. The change rides in the details, one word from
`brain.builder.agent_drafts.DraftChange` (`drafted`, `saved`, `checked`, `requested`, `approved`,
`declined`, `published`), and an act says whether the revision reached further than the agent did.
**Never the document**: not a path, a value or a digest of one, because the ledger is the
longest-kept record here and a manifest names what an agent may reach. `publish` is
`AuditAction.PUBLISH`, which `brain.builder.publish` already names as the builder's, so no member is
added and neither audit grammar changes.

**The downgrade drops the three tables and their functions**, and their ledger entries stay, because
nothing may delete one: `0056`'s reason.

Written over 0139 and re-pointed over 0148, the newest on origin/main when it landed. It restates
neither audit grammar: `publish` and the `agent` subject kind are in every list the chain leaves.

Task ids: M27.11.6, M27.15.29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. A revision
#: points at its draft and an act at its revision.
TABLES: tuple[str, ...] = (
    "agent.manifest_draft",
    "agent.manifest_revision",
    "agent.manifest_act",
)

APP_ROLE = "brain_app"

#: Widths and vocabularies copied for the reason `0009` gives about reading live code from a
#: migration, and held equal to `brain.tables.manifest_draft` by
#: `tests/unit/test_agent_draft_store.py`.
AGENT_ID_CHARS = 60
PRINCIPAL_ID_CHARS = 128
KIND_CHARS = 8
ACT_CHARS = 16
HASH_CHARS = 64
AGENT_ID_GRAMMAR = "agent_id ~ '^[a-z][a-z0-9]*(?\\:_[a-z0-9]+)*$'"
KINDS = "kind IN ('edit', 'new')"
ACTS = "act IN ('approved', 'checked', 'declined', 'published', 'requested')"
BASE_HASH_IFF_EDIT = "(kind = 'edit') = (base_hash IS NOT NULL)"

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.manifest_draft ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.manifest_revision ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.manifest_act ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY manifest_draft_readable ON agent.manifest_draft
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY manifest_draft_started_in_the_sessions_name ON agent.manifest_draft
        FOR INSERT TO brain_app
        WITH CHECK (owner_id = {PRINCIPAL})
    """,
    """
    CREATE POLICY manifest_revision_readable ON agent.manifest_revision
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY manifest_revision_saved_in_the_sessions_name ON agent.manifest_revision
        FOR INSERT TO brain_app
        WITH CHECK (saved_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY manifest_act_readable ON agent.manifest_act
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY manifest_act_taken_in_the_sessions_name ON agent.manifest_act
        FOR INSERT TO brain_app
        WITH CHECK (actor_id = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a save and an approval are new rows.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.manifest_draft TO brain_app",
    "GRANT SELECT, INSERT ON agent.manifest_revision TO brain_app",
    "GRANT SELECT, INSERT ON agent.manifest_act TO brain_app",
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


def _function(name: str, head: str, body: str, *, actor: str) -> str:
    """One trigger function appending one `publish` entry about the draft's agent."""
    return (
        f"""
CREATE FUNCTION {name}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE{head}"""
        + _DECLARE
        + """BEGIN"""
        + body
        + _APPEND.format(actor=actor, action="publish", subject="v_subject", details="v_details")
        + """    RETURN NULL;
END;
$$
"""
    )


#: A draft started, about the agent it makes or changes.
DRAFT_TRIGGER_FUNCTION = _function(
    "agent.record_manifest_draft",
    """
    v_subject text := 'agent:' || NEW.agent_id;
    v_details jsonb := jsonb_build_object('change', 'drafted');""",
    "",
    actor="NEW.owner_id",
)

#: A revision saved, about the agent its draft names.
REVISION_TRIGGER_FUNCTION = _function(
    "agent.record_manifest_revision",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object('change', 'saved');""",
    """
    SELECT 'agent:' || d.agent_id INTO v_subject
      FROM agent.manifest_draft d WHERE d.id = NEW.draft_id;""",
    actor="NEW.saved_by",
)

#: An act on a revision, the act's own word, and whether the revision reached further.
ACT_TRIGGER_FUNCTION = _function(
    "agent.record_manifest_act",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object(
        'change', NEW.act,
        'widened', CASE WHEN NEW.widened THEN 'true' ELSE 'false' END
    );""",
    """
    SELECT 'agent:' || d.agent_id INTO v_subject
      FROM agent.manifest_draft d WHERE d.id = NEW.draft_id;""",
    actor="NEW.actor_id",
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER manifest_draft_is_audited
        AFTER INSERT ON agent.manifest_draft
        FOR EACH ROW EXECUTE FUNCTION agent.record_manifest_draft()
    """,
    """
    CREATE TRIGGER manifest_revision_is_audited
        AFTER INSERT ON agent.manifest_revision
        FOR EACH ROW EXECUTE FUNCTION agent.record_manifest_revision()
    """,
    """
    CREATE TRIGGER manifest_act_is_audited
        AFTER INSERT ON agent.manifest_act
        FOR EACH ROW EXECUTE FUNCTION agent.record_manifest_act()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "manifest_draft",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("owner_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("base_hash", sa.String(HASH_CHARS), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(AGENT_ID_GRAMMAR, name="agent_id_grammar"),
        sa.CheckConstraint(KINDS, name="kind"),
        sa.CheckConstraint(BASE_HASH_IFF_EDIT, name="base_hash_iff_edit"),
        schema="agent",
    )
    op.create_index(
        "ix_agent_manifest_draft_owner_id", "manifest_draft", ["owner_id"], schema="agent"
    )
    op.create_index(
        "ix_agent_manifest_draft_agent_id", "manifest_draft", ["agent_id"], schema="agent"
    )
    op.create_table(
        "manifest_revision",
        sa.Column("draft_id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("number", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("body", JSONB(), nullable=False),
        sa.Column("saved_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("number >= 1", name="number_from_one"),
        sa.CheckConstraint("jsonb_typeof(body) = 'object'", name="body_is_an_object"),
        sa.ForeignKeyConstraint(["draft_id"], ["agent.manifest_draft.id"]),
        schema="agent",
    )
    op.create_table(
        "manifest_act",
        sa.Column("draft_id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("revision", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("act", sa.String(ACT_CHARS), primary_key=True, nullable=False),
        sa.Column("actor_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("widened", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("for_department", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["draft_id", "revision"],
            ["agent.manifest_revision.draft_id", "agent.manifest_revision.number"],
        ),
        sa.CheckConstraint(ACTS, name="act"),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(DRAFT_TRIGGER_FUNCTION)
    op.execute(REVISION_TRIGGER_FUNCTION)
    op.execute(ACT_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER manifest_act_is_audited ON agent.manifest_act")
    op.execute("DROP TRIGGER manifest_revision_is_audited ON agent.manifest_revision")
    op.execute("DROP TRIGGER manifest_draft_is_audited ON agent.manifest_draft")
    op.execute("DROP FUNCTION agent.record_manifest_act()")
    op.execute("DROP FUNCTION agent.record_manifest_revision()")
    op.execute("DROP FUNCTION agent.record_manifest_draft()")
    op.drop_table("manifest_act", schema="agent")
    op.drop_table("manifest_revision", schema="agent")
    op.drop_index("ix_agent_manifest_draft_agent_id", table_name="manifest_draft", schema="agent")
    op.drop_index("ix_agent_manifest_draft_owner_id", table_name="manifest_draft", schema="agent")
    op.drop_table("manifest_draft", schema="agent")
