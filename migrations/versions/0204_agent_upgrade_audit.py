"""An agent moved to a newer template version, and a version somebody turned away, reach the ledger.

`brain.agents.upgrade` has held the review, accept and decline since M13.4.1 and
`brain.agent_upgrade_routes` now serves them. An acceptance moves the install's pin and with it
everything the agent is, its persona, its tools, its ceiling and the leash it is held to, and a
decline is the one record that somebody read a version and said no. Neither reached the ledger:
`0137`'s trigger on `agent.agent` records only a lifecycle or audience move, and says in its own
words that an edit to the configuration columns appends nothing, `0059`'s trigger on
`agent.template_instance` records only an overlay that moves the persona and nothing else, and
`agent.upgrade_decline` has no trigger at all. So "who changed what this agent is, and when" had
no answer for the move that changes the most.

**Two triggers, each its own function, and `0137`'s is not touched.** The change words are
`upgraded` and `upgrade_declined`, under the ledger's existing `agent` action, so no vocabulary
changes and `obs.audit_entry`'s check constraint is left alone. Naming the two moves as words on an
existing action, rather than as a new action, is the argument `0137` makes for its own seven.

**On an update of `agent.template_instance`, one entry when the pinned version moves.** The actor is
`brain.actor_id` as `brain.agent_upgrade_routes` sets it through `brain.tables.audit.attributed_to`
in the transaction that writes, and a statement that set nothing is attributed to the database role
and marked `actor: inferred`, which is `0059`'s and `0137`'s arrangement. An update that moves the
overlay, the hash or the document and not the version appends nothing here: an instruction edit is
`0059`'s, and every other writer of the install is a change this entry does not name.

**On an insert into `agent.upgrade_decline`, one entry, and the actor is the row's own
`declined_by`**, the way `0137` takes `created_by`: the decision is the person's and the row names
them. The entry does not say which version: **the details are the change and nothing else**, never
a version number, a digest or a steward, which is `0137`'s rule for the same reason, and the
version is on the decline row and the install row that the entry's subject names.

**The append is `0003`'s**, another copy of the block `0059` and `0137` carry, for the reason `0047`
gives against editing a function every grant in production goes through.

**Nothing is created or dropped but two functions and two triggers, and the downgrade keeps what
the ledger already holds**: an `agent` entry whose change is one of these words stays, and the
vocabulary of `change` is a detail and not a constraint, so there is nothing to put back.

Task ids: M13.4.4, M13.4.5
"""

from __future__ import annotations

from alembic import op

revision = "0204"
down_revision = "0207"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

#: The word a trigger writes beside an actor nobody named, as `0003`, `0059` and `0137` write it.
INFERRED = "inferred"

#: The two change words, held equal to `brain.audit.record.AgentUpgradeChange` by a test.
UPGRADED = "upgraded"
UPGRADE_DECLINED = "upgrade_declined"

#: The ledger append, `0137`'s block with its one change. `__CHANGE__` is the word and `__ACTOR__`
#: the expression naming who did it.
APPEND = """
    v_details := jsonb_build_object('change', '__CHANGE__');
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
"""

DECLARATIONS = """
DECLARE
    v_subject text := 'agent:' || __ID__;
    v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor text;
    v_inferred boolean := false;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
"""

#: One agent moved to another version of its template. The trigger's own `WHEN` is the whole of the
#: condition, so a statement that does not move the pin never reaches the function.
UPGRADED_FUNCTION = (
    """
CREATE FUNCTION agent.record_agent_upgrade() RETURNS trigger
LANGUAGE plpgsql AS $$"""
    + DECLARATIONS.replace("__ID__", "NEW.id")
    + """BEGIN
    v_actor := COALESCE(v_supplied, session_user::text);
    v_inferred := v_supplied IS NULL;
"""
    + APPEND.replace("__CHANGE__", UPGRADED).replace("__INFERRED__", INFERRED)
    + """    RETURN NULL;
END;
$$
"""
)

UPGRADED_TRIGGER = """
CREATE TRIGGER agent_upgrade_is_audited
    AFTER UPDATE ON agent.template_instance
    FOR EACH ROW
    WHEN (OLD.template_version IS DISTINCT FROM NEW.template_version)
    EXECUTE FUNCTION agent.record_agent_upgrade()
"""

#: One version turned away. The actor is the row's own `declined_by`, which is never null.
DECLINED_FUNCTION = (
    """
CREATE FUNCTION agent.record_agent_upgrade_decline() RETURNS trigger
LANGUAGE plpgsql AS $$"""
    + DECLARATIONS.replace("__ID__", "NEW.instance_id")
    + """BEGIN
    v_actor := NEW.declined_by;
"""
    + APPEND.replace("__CHANGE__", UPGRADE_DECLINED).replace("__INFERRED__", INFERRED)
    + """    RETURN NULL;
END;
$$
"""
)

DECLINED_TRIGGER = """
CREATE TRIGGER agent_upgrade_decline_is_audited
    AFTER INSERT ON agent.upgrade_decline
    FOR EACH ROW EXECUTE FUNCTION agent.record_agent_upgrade_decline()
"""


def upgrade() -> None:
    op.execute(UPGRADED_FUNCTION)
    op.execute(UPGRADED_TRIGGER)
    op.execute(DECLINED_FUNCTION)
    op.execute(DECLINED_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER agent_upgrade_decline_is_audited ON agent.upgrade_decline")
    op.execute("DROP FUNCTION agent.record_agent_upgrade_decline()")
    op.execute("DROP TRIGGER agent_upgrade_is_audited ON agent.template_instance")
    op.execute("DROP FUNCTION agent.record_agent_upgrade()")
