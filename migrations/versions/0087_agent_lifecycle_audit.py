"""An agent created, enabled, disabled, archived, handed on or published reaches the ledger.

`brain.agents.lifecycle` has held enable, disable, archive, transfer and publish since M13.1.4, and
`brain.agents.install_store` writes an installed agent, and until this migration every one of those
stopped at the row. `agent.agent` keeps two timestamps and a steward and never who moved them, so
"who switched this agent off" and "who is answering for it now, and since when" had a last answer
and no history. `brain.agent_lifecycle_routes` now serves the moves from the console, and this is
the ledger member `brain.audit.ledger.AuditAction.AGENT` argues and the one trigger that records it.

**A trigger rather than the route appending, for the reason `0054` gives**: nothing in the
application appends to `obs.audit_entry`, so a statement an operator types at a prompt is recorded
exactly as a press in the console is, and the chain keeps one writer. That matters more here than
for most rows, because archive is terminal in the domain and the only way an archived agent comes
back is a statement: `unarchived` is a word no route writes, and it is the change the ledger most
needs to see.

**On the insert, one entry: `created`, with the actor the row's own `created_by` names.** An install
writes the agent disabled, which `brain.agents.install_store.AN_INSTALLED_AGENT_IS_WRITTEN_DISABLED`
argues, so the state it starts in is part of its creation rather than a second decision, and a
`disabled` entry beside every `created` would be noise an auditor learns to skip.

**On an update, one entry per movement, in a fixed order**: `enabled` and `disabled` when
`disabled_at` is cleared or set, `archived` and `unarchived` when `archived_at` is set or cleared,
`transferred` when the steward moves, and `published` or `audience_changed` when the visibility
level or the department moves, `published` exactly when the new level is the company. An update
that moves none of those appends nothing, so an instruction edit writing `persona`, which `0059`
records on the install, is not recorded twice. The actor is `brain.actor_id` as
`brain.agent_lifecycle_routes` sets it through `brain.tables.audit.attributed_to`, and a statement
that set nothing is attributed to the database role and marked `actor: inferred`, which is `0059`'s
arrangement for a give-back.

**The details are the change and nothing else.** Never the steward: a principal id is not a field
name, so `AuditRecorder.agent` would keep the marker, and the row says who answers for the agent
now. Never a timestamp: the entry's own `at` is when.

**What this does not record, stated.** A statement that edits an agent's ceiling, tools or tier on
`agent.agent` directly moves none of the columns above and appends nothing. The install is what
`materialise` reads and the builder's publish gate is where a ceiling is meant to move, so a copy
edited behind it is a divergence rather than a change this member names; recording it needs its own
member and its own argument, and the leash is W3.8's.

**The append is `0003`'s**, another copy of the block `0059` and `0062` carry, for the reason `0047`
gives against editing a function every grant in production goes through.

**One supersession, the action list `0062` leaves in the database.** Numbered 0087 and revising
0083, the newest revision on origin/main when it was rebased (first written against 0068); others
in flight take the numbers between. **If one of them widens the action list first, this file's
`NARROWER_ACTIONS` and `down_revision` are re-pointed at it**, and `tests/unit/test_tables.py`'s
supersession check is what says so. **The downgrade keeps what the ledger already holds**, for the
reason `0026` gives: the list goes back `NOT VALID`, so an `agent` entry already written stays and
no new one is accepted.

Task ids: M27.11.6, M27.11.7
"""

from __future__ import annotations

from alembic import op

revision = "0087"
down_revision = "0083"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0062`'s, which is the
#: list the migration before this leaves in the database.
WIDENED_ACTIONS = (
    "action IN ('agent', 'approval', 'break_glass', 'certification', 'compose_change', "
    "'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', "
    "'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', "
    "'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', "
    "'skill', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)

#: What this migration replaces: the action list `0062` leaves.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

#: The level whose arrival is a publication. `brain.agents.lifecycle.PUBLICATION_LEVEL`, copied for
#: the reason `0009` gives about reading live code from a migration, and held equal by a test.
PUBLICATION_LEVEL = "company"

#: The word a trigger writes beside an actor nobody named, as `0003` and `0059` write it.
INFERRED = "inferred"

#: One agent created, or moved in its lifecycle, its steward or its audience.
AGENT_TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_agent_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.id;
    v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor text;
    v_inferred boolean := false;
    v_changes text[] := ARRAY[]::text[];
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'created'::text;
        v_actor := NEW.created_by;
    ELSE
        IF OLD.disabled_at IS NOT NULL AND NEW.disabled_at IS NULL THEN
            v_changes := v_changes || 'enabled'::text;
        END IF;
        IF OLD.disabled_at IS NULL AND NEW.disabled_at IS NOT NULL THEN
            v_changes := v_changes || 'disabled'::text;
        END IF;
        IF OLD.archived_at IS NULL AND NEW.archived_at IS NOT NULL THEN
            v_changes := v_changes || 'archived'::text;
        END IF;
        IF OLD.archived_at IS NOT NULL AND NEW.archived_at IS NULL THEN
            v_changes := v_changes || 'unarchived'::text;
        END IF;
        IF OLD.owner_id IS DISTINCT FROM NEW.owner_id THEN
            v_changes := v_changes || 'transferred'::text;
        END IF;
        IF OLD.visibility IS DISTINCT FROM NEW.visibility
           OR OLD.department IS DISTINCT FROM NEW.department THEN
            IF NEW.visibility = '__PUBLICATION_LEVEL__' THEN
                v_changes := v_changes || 'published'::text;
            ELSE
                v_changes := v_changes || 'audience_changed'::text;
            END IF;
        END IF;
        v_actor := COALESCE(v_supplied, session_user::text);
        v_inferred := v_supplied IS NULL;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);
        IF v_inferred THEN
            v_details := v_details || jsonb_build_object('actor', '__INFERRED__');
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
            v_seq, v_at, v_actor, 'agent', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, 'agent', v_subject,
                    v_ent_hash, v_trace, v_details, v_prev, v_entry);

        GET DIAGNOSTICS v_written = ROW_COUNT;
        IF v_written <> 1 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the ledger already holds seq ' || v_seq
                          || '; the audit entry was not appended',
                ERRCODE = 'restrict_violation',
                HINT = 'an append that is discarded silently is the failure this refuses';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$
""".replace("__PUBLICATION_LEVEL__", PUBLICATION_LEVEL).replace("__INFERRED__", INFERRED)

AGENT_TRIGGER = """
CREATE TRIGGER agent_is_audited
    AFTER INSERT OR UPDATE ON agent.agent
    FOR EACH ROW EXECUTE FUNCTION agent.record_agent_change()
"""


def upgrade() -> None:
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(AGENT_TRIGGER_FUNCTION)
    op.execute(AGENT_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER agent_is_audited ON agent.agent")
    op.execute("DROP FUNCTION agent.record_agent_change()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
