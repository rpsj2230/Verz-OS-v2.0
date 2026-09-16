"""Feature switches, job controls, instructions, rung saves and webhook changes reach the ledger.

`docs/console-audit.md` follows every write the console sends to the row it writes, the audit entry
it leaves and the behaviour it changes, and until this migration five kinds of write stopped at the
row. A feature switch and a job's pause, resume or run request were attributed by `ops.setting`'s
`updated_by` and overwritten by the next press; an instruction edit by the overlay's owner, which a
give-back removes; a rung save by nothing at all; a webhook change by `ops.webhook_change`, which
the ledger's chain did not cover. This migration is the four ledger members and three subject kinds
`brain.audit.ledger.AuditAction` argues, and the four triggers that record them.

**Triggers rather than the routes appending, for the reason `0054` gives**: nothing in the
application appends to `obs.audit_entry`, so a statement an operator types at a prompt is recorded
exactly as a press in the console is, and the chain keeps one writer.

**`ops.setting`, on every namespace and not only the two the console switches.** `0004` recorded
the missing trigger as a gap for the whole table, and a trigger that recorded `feature.*` and
`schedule.*` would leave an operator's hand edit of `install.model_endpoint` as unrecorded as
before, while reading as though the table were covered. The change is recorded when the row's key,
type or value moves, and when the row is retired; **an upsert that writes the value already held
appends nothing**, because nothing changed, and the row's `updated_at` moving on a second press is
not a change anybody audits. The actor is the row's `updated_by`, which every writer sets. The
details are `switched_on` or `switched_off` for a boolean and `set` for anything else, **never the
value**: a run request's instant, a company's name and an endpoint's address all stay on the row.

**`ops.routing_rung`, on the insert, on an update that moves a column, and on retirement.** The
details name the columns that moved, sorted and comma-joined, which `redact_details` admits as
field names, and never their values. The row has no column naming who changed it, so the actor is
`brain.actor_id` as `brain.routing_routes` sets it, and a statement that set nothing is attributed
to the database role it ran as and marked `actor: inferred`, which is `0003`'s word for the same
situation on a revocation.

**`agent.template_instance`, on an update that moves the overlay's `persona` and nothing else.** An
upgrade that moves the pin, or an edit to another overlaid path, is not an instruction edit. An
edit's actor is the overlay owner's `set_by`, the row's own record of who set it; a give-back
removes that owner, so its actor is `brain.actor_id` as `brain.prompt_routes` sets it, or the role
marked inferred. The details carry the effective configuration's digest, `effective_hash`, which
is what the answer cache keys on, and never the instructions.

**What these do not record, stated.** A statement that edits `agent.agent.persona` alone, without
the install, is not an instruction edit this trigger sees: the install is what `materialise` reads
and what the Prompts screen writes, and a copy edited behind it is a divergence the screen shows
rather than a change the ledger records. An install inserted with a persona already overlaid is an
install, which the template's own flow owns, and appends nothing here.

**`ops.webhook_change`, on the insert**, one entry per change row, with the actor its own
`changed_by` names. `brain.tables.webhook_change` said this trigger would be the whole of the
wiring, and it is.

**The subject ids fit the ledger's grammar without rewriting.** A setting key is dotted lowercase
names of at most 120 characters, a rung id is a uuid, an agent slug and a console subscriber id are
lowercase names, and `IDENTIFIER` admits all four. A row whose id does not fit is refused by the
ledger's check constraint and its write rolls back, which is `0003`'s refusal of an append
discarded silently, in the direction that keeps the chain whole.

**The append is `0003`'s, another copy of the block `0054` and `0056` carry**, for the reason `0047`
gives against editing a function every grant in production goes through.

**Two supersessions, and both are real**: `0057`'s action list and `0056`'s subject grammar, which
are the ones in the database. **The downgrade can fail, which is correct**, for the reason `0026` gives.

Task ids: M27.8.17
"""

from __future__ import annotations

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`, which concatenates
#: every migration's slice.
TABLES: tuple[str, ...] = ()

#: Alphabetical, matching how `tables.identity.one_of` sorts.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'grant', 'instructions', 'leash_change', 'legal_hold', "
    "'publish', 'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', "
    "'sign_in', 'skill', 'webhook')"
)
#: `0057`'s, which is the one in the database.
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'grant', 'leash_change', 'legal_hold', 'publish', "
    "'record_read', 'retention', 'revoke', 'session_end', 'sign_in', 'skill')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0056`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|grant|leash|legal_hold|principal"
    "|retention|routing|session|setting|skill|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|grant|leash|legal_hold|principal"
    "|retention|session|skill):[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0057`'s action list and `0056`'s subject grammar.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

#: The columns of a rung whose movement is not a change anybody audits: its identity, which is the
#: subject, and the three instants, of which retirement is recorded as a change of its own.
ROUTING_COLUMNS_NOT_RECORDED: tuple[str, ...] = ("id", "created_at", "updated_at", "deleted_at")

#: The word a trigger writes beside an actor nobody named, as `0003` writes it.
INFERRED = "inferred"

#: The append every trigger below makes, as `0003`, `0054` and `0056` write it. `{actor}`,
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

#: A setting switched, set or retired, with the actor its own `updated_by` names. See the docstring
#: for why an upsert of the value already held appends nothing.
SETTING_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_setting_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'setting:' || NEW.key;
    v_moved boolean;
    v_retired boolean;
    v_changes text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_moved := true;
        v_retired := NEW.deleted_at IS NOT NULL;
    ELSE
        v_moved := OLD.key IS DISTINCT FROM NEW.key
            OR OLD.value_type IS DISTINCT FROM NEW.value_type
            OR OLD.value IS DISTINCT FROM NEW.value;
        v_retired := OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL;
    END IF;

    IF v_moved THEN
        IF NEW.value_type <> 'boolean' THEN
            v_changes := v_changes || 'set'::text;
        ELSIF NEW.value = 'true'::jsonb THEN
            v_changes := v_changes || 'switched_on'::text;
        ELSE
            v_changes := v_changes || 'switched_off'::text;
        END IF;
    END IF;
    IF v_retired THEN
        v_changes := v_changes || 'retired'::text;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);"""
    + _APPEND.format(
        actor="NEW.updated_by", action="setting", subject="v_subject", details="v_details"
    )
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

#: A rung added, changed or retired, with the columns that moved and the actor the route supplied.
ROUTING_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_routing_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'routing:' || NEW.id::text;
    v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor text;
    v_fields text;
    v_changes text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    v_actor := COALESCE(v_supplied, session_user::text);
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'added'::text;
        IF NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    ELSE
        SELECT string_agg(moved.key, ',' ORDER BY moved.key) INTO v_fields
          FROM jsonb_each(to_jsonb(NEW)) AS moved
         WHERE moved.key <> ALL (ARRAY['"""
    + "', '".join(ROUTING_COLUMNS_NOT_RECORDED)
    + """'])
           AND moved.value IS DISTINCT FROM (to_jsonb(OLD) -> moved.key);
        IF v_fields IS NOT NULL THEN
            v_changes := v_changes || 'changed'::text;
        END IF;
        IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
            v_changes := v_changes || 'retired'::text;
        END IF;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);
        IF v_changes[i] = 'changed' THEN
            v_details := v_details || jsonb_build_object('fields', v_fields);
        END IF;
        IF v_supplied IS NULL THEN
            v_details := v_details || jsonb_build_object('actor', '"""
    + INFERRED
    + """');
        END IF;"""
    + _APPEND.format(actor="v_actor", action="routing", subject="v_subject", details="v_details")
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

#: An agent's instructions edited or given back, with the configuration put in force.
INSTRUCTIONS_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_instructions_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'agent:' || NEW.id;
    v_supplied text := NULLIF(current_setting('brain.actor_id', true), '');
    v_actor text;
    v_change text;
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF (OLD.overlay -> 'persona') IS NOT DISTINCT FROM (NEW.overlay -> 'persona') THEN
        RETURN NULL;
    END IF;
    IF NEW.overlay ? 'persona' THEN
        v_change := 'edited';
        v_actor := NEW.field_owners -> 'persona' ->> 'set_by';
    ELSE
        v_change := 'given_back';
    END IF;
    v_details := jsonb_build_object('change', v_change, 'config_hash', NEW.effective_hash);
    IF v_actor IS NULL THEN
        v_actor := COALESCE(v_supplied, session_user::text);
        IF v_supplied IS NULL THEN
            v_details := v_details || jsonb_build_object('actor', '"""
    + INFERRED
    + """');
        END IF;
    END IF;"""
    + _APPEND.format(
        actor="v_actor", action="instructions", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

#: One webhook change, with the actor its own `changed_by` names.
WEBHOOK_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_webhook_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'webhook:' || NEW.subscriber_id;
    v_details jsonb := jsonb_build_object('change', NEW.change);"""
    + _DECLARE
    + """BEGIN"""
    + _APPEND.format(
        actor="NEW.changed_by", action="webhook", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER setting_is_audited
        AFTER INSERT OR UPDATE ON ops.setting
        FOR EACH ROW EXECUTE FUNCTION ops.record_setting_change()
    """,
    """
    CREATE TRIGGER routing_rung_is_audited
        AFTER INSERT OR UPDATE ON ops.routing_rung
        FOR EACH ROW EXECUTE FUNCTION ops.record_routing_change()
    """,
    """
    CREATE TRIGGER instructions_are_audited
        AFTER UPDATE ON agent.template_instance
        FOR EACH ROW EXECUTE FUNCTION agent.record_instructions_change()
    """,
    """
    CREATE TRIGGER webhook_change_is_audited
        AFTER INSERT ON ops.webhook_change
        FOR EACH ROW EXECUTE FUNCTION ops.record_webhook_change()
    """,
)


def upgrade() -> None:
    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")
    op.execute(SETTING_TRIGGER_FUNCTION)
    op.execute(ROUTING_TRIGGER_FUNCTION)
    op.execute(INSTRUCTIONS_TRIGGER_FUNCTION)
    op.execute(WEBHOOK_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER webhook_change_is_audited ON ops.webhook_change")
    op.execute("DROP TRIGGER instructions_are_audited ON agent.template_instance")
    op.execute("DROP TRIGGER routing_rung_is_audited ON ops.routing_rung")
    op.execute("DROP TRIGGER setting_is_audited ON ops.setting")
    op.execute("DROP FUNCTION ops.record_webhook_change()")
    op.execute("DROP FUNCTION agent.record_instructions_change()")
    op.execute("DROP FUNCTION ops.record_routing_change()")
    op.execute("DROP FUNCTION ops.record_setting_change()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", NARROWER_ACTIONS, schema="obs")
