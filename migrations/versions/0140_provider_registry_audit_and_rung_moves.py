"""A provider's registry row reaches the ledger, and a routing change may retire or move a step.

Two changes, both for the Models and routing module's rebuild (2026-09-28).

**`ops.model_provider` gets the audit trigger `0097` did not give it** (M5.6.4).
`brain.provider_registry_routes` said so in words: a terms edit was logged and not ledgered, and
"it is the next migration's to add". The trigger appends a `setting` entry on the insert
(`registered`), on an update that moves a column (`changed`, naming the columns, sorted and
comma-joined), and on retirement (`retired`), with `brain.audit.record.ProviderRegistryChange`'s
words. **The subject is `setting:provider.<slug>`, the subject the provider's switch is recorded
under by `0059`'s trigger on `ops.setting`**, so one provider's history is one subject. Never a
value: the terms are prose a company negotiated and stay on the row. The actor is
`brain.actor_id` when the route set it and the row's own `updated_by` when not, which every writer
of the table sets. A new ledger action was rejected: the actions are a closed list with one
recorder method each, and a provider's registry row is the install's configuration of that
provider exactly as its switch is.

**`ops.routing_change.kind` admits `retire` and `move`** (M5.3.3, M27.15.38). A step retired or
moved from the Routing screen goes through the matrix gate like an edit or an addition, and its
record says which it was.

**A retired rung keeps the role it had.** `0097`'s `ops.routing_rung_role()` derived the role on
every write, the retirement included, and a move retires several rungs of one level in one
statement: as each went, the next was derived against the ones left and became the primary, so
the ledger read "role changed" and then "retired" for rows whose role nobody changed. The function
now returns a retiring row untouched; a live row is derived exactly as before.

**The append is `0003`'s block once more**, beside `0059`'s and `0105`'s, for the reason `0047`
gives against editing a function every grant in production goes through.

**The downgrade** drops the trigger and its function, puts `0097`'s role function back, and puts
`0097`'s kinds back `NOT VALID`, for `0026`'s reason: a change already recorded as a retirement or a
move stays.

Task ids: M5.6.4, M5.3.3, M27.15.38

Revision ID: 0140
Revises: 0133
"""

from __future__ import annotations

from alembic import op

revision = "0140"
# The newest migration on origin/main when this was written: 0133, after 0120.
down_revision = "0133"
branch_labels = None
depends_on = None

#: No table is created or dropped here. Read by `tests/unit/test_tables.py`.
TABLES: tuple[str, ...] = ()

#: `brain.tables.model_registry.ChangeKind`, before and after, as `one_of` renders it.
NARROWER_KINDS = "kind IN ('add', 'edit')"
WIDENED_KINDS = "kind IN ('add', 'edit', 'move', 'retire')"

#: What this migration replaces: `0097`'s change kinds.
SUPERSEDES: dict[str, str] = {NARROWER_KINDS: WIDENED_KINDS}

#: The registry columns whose movement is not a change anybody audits: the row's identity, its
#: instants, of which retirement is recorded as a change of its own, and who wrote it last. Written
#: out in the trigger below as well, and a test holds the two together.
REGISTRY_COLUMNS_NOT_RECORDED: tuple[str, ...] = (
    "id",
    "created_at",
    "updated_at",
    "deleted_at",
    "updated_by",
)

TRIGGER_FUNCTION = """
CREATE FUNCTION ops.record_provider_registry_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'setting:provider.' || NEW.slug;
    v_actor text := COALESCE(NULLIF(current_setting('brain.actor_id', true), ''), NEW.updated_by);
    v_fields text;
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
        v_changes := v_changes || 'registered'::text;
    ELSE
        SELECT string_agg(moved.key, ',' ORDER BY moved.key) INTO v_fields
          FROM jsonb_each(to_jsonb(NEW)) AS moved
         WHERE moved.key <> ALL (
                   ARRAY['id', 'created_at', 'updated_at', 'deleted_at', 'updated_by']
               )
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

        -- The append, as 0003, 0059 and 0105 write it. See the module docstring.
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
            v_seq, v_at, v_actor, 'setting', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actor, 'setting', v_subject,
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
"""

#: `0097`'s derivation with one guard in front: a row being retired is returned untouched.
ROLE_FUNCTION = """
CREATE OR REPLACE FUNCTION ops.routing_rung_role() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_position smallint;
    v_provider text;
BEGIN
    IF NEW.deleted_at IS NOT NULL THEN
        RETURN NEW;
    END IF;
    SELECT r.position, r.provider INTO v_position, v_provider
      FROM ops.routing_rung r
     WHERE r.tier = NEW.tier
       AND r.deleted_at IS NULL
       AND r.id <> NEW.id
     ORDER BY r.position
     LIMIT 1;
    IF v_position IS NULL OR NEW.position < v_position THEN
        NEW.role := 'primary';
    ELSIF v_provider = NEW.provider THEN
        NEW.role := 'same_provider_failover';
    ELSE
        NEW.role := 'cross_provider_failover';
    END IF;
    RETURN NEW;
END;
$$
"""

#: `0097`'s function as it was, for the downgrade. Copied rather than imported, for `0009`'s reason
#: about reading other code from a migration; a test holds the two equal.
ROLE_FUNCTION_BEFORE = """
CREATE OR REPLACE FUNCTION ops.routing_rung_role() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_position smallint;
    v_provider text;
BEGIN
    SELECT r.position, r.provider INTO v_position, v_provider
      FROM ops.routing_rung r
     WHERE r.tier = NEW.tier
       AND r.deleted_at IS NULL
       AND r.id <> NEW.id
     ORDER BY r.position
     LIMIT 1;
    IF v_position IS NULL OR NEW.position < v_position THEN
        NEW.role := 'primary';
    ELSIF v_provider = NEW.provider THEN
        NEW.role := 'same_provider_failover';
    ELSE
        NEW.role := 'cross_provider_failover';
    END IF;
    RETURN NEW;
END;
$$
"""

TRIGGER = """
CREATE TRIGGER model_provider_is_audited
    AFTER INSERT OR UPDATE ON ops.model_provider
    FOR EACH ROW EXECUTE FUNCTION ops.record_provider_registry_change()
"""


def upgrade() -> None:
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("kind", "routing_change", schema="ops", type_="check")
    op.create_check_constraint("kind", "routing_change", WIDENED_KINDS, schema="ops")
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)
    op.execute(ROLE_FUNCTION)


def downgrade() -> None:
    op.execute(ROLE_FUNCTION_BEFORE)
    op.execute("DROP TRIGGER model_provider_is_audited ON ops.model_provider")
    op.execute("DROP FUNCTION ops.record_provider_registry_change()")
    op.drop_constraint("kind", "routing_change", schema="ops", type_="check")
    op.create_check_constraint(
        "kind", "routing_change", NARROWER_KINDS, schema="ops", postgresql_not_valid=True
    )
