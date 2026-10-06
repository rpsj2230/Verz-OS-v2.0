"""A merge is recorded with who, when, its evidence and its pre-image, and an unmerge is audited.

`brain.resolution.merge` has decided a merge's shape since M14.5 was written, and nothing stored
one: no pre-image anywhere, no record of who merged or on what evidence, and an unmerge (the
pointer cleared again) wrote no ledger entry, because `0104`'s trigger fires only on a pointer
going from empty to set. `brain.tables.entity_merge` argues the two tables' shape; this builds
them, widens the ledger and replaces the trigger's function.

**`er.merge` and `er.unmerge`** are written by `brain.resolution.merge_store` inside the
transaction that moves the pointer, and read by nobody else yet. SELECT and INSERT for
`brain_app`, nothing for `brain_fastlane`, no UPDATE and no DELETE: they are audit rows. Row-level
security on both, readable `USING (true)` for `0020`'s reason (who may see which member of an
entity is decided per source record by `canonical.resolved_view`, not by these rows), and
insertable only in the name of the transaction's actor, so the row and the ledger entry cannot
name two different people.

**The unmerge's ledger entry is written by the trigger, not by the store**, and that is the
choice this file is mostly about. The store could append `entity_unmerge` itself through the
recorder, which reads as tidier; it would then be written only by the store, and a pointer
cleared any other way, a hand UPDATE during an incident included, would undo a merge with
nothing in the ledger, which is the gap this closes. The trigger sees every pointer change
whoever makes it, commits with it or not at all (`0050`'s argument for a trigger over a route),
and is where the merge entry is already written, so both halves of one story are written by one
function. So `er.record_entity_merge()` is replaced rather than joined by a second trigger:

- a pointer going from empty to set appends `entity_merge` per side, survivor first, as before;
- a pointer cleared appends `entity_unmerge` per side, the survivor it pointed at first;
- a pointer moved straight from one entity to another, which the product never does (`merge`
  refuses a stub), appends both, so a hand re-point reads as what it is.

Each entry names the merge, and the unmerge entry its unmerge too, by id in its details when the
store's row for it is there; an entry with no id in its details is a pointer moved by hand, and
reads as one. The ids are 32-hex, which the ledger's redaction keeps
(`brain.tables.entity_merge`). The append block is `0003`'s once more, copied as `0104` copies
it, for `0047`'s reason against editing a function every grant goes through.

**The action list gains `entity_unmerge`**, superseding `0150`'s, the last in the chain to widen
it. Fourteen characters, inside the column's sixteen. The subject kind `entity` exists since
`0002`.

**The downgrade** puts `0104`'s function back, drops the two tables, and puts `0150`'s action
list back `NOT VALID`, for `0026`'s reason: an entry already recorded stays.

Revises `0182`, the registry this merges the entities of.

Task ids: M14.5.1, M14.5.3, M14.5.4

Revision ID: 0183
Revises: 0182
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0183"
down_revision = "0182"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("er.merge", "er.unmerge")

APP_ROLE = "brain_app"

#: Copied for the reason `0009` gives about reading live code from a migration, and each held
#: equal to its source by `tests/unit/test_merge_store.py`.
RECORD_ID_PATTERN = "^[0-9a-f]{32}$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
CONFIDENCE_IS_A_SHARE = "confidence >= 0.0 AND confidence <= 1.0"
MONEY_LEFT_IN = (
    "money_left IN ('carries financial records', 'no financial records found', 'not checked')"
)
MONEY_RIGHT_IN = (
    "money_right IN ('carries financial records', 'no financial records found', 'not checked')"
)
PRE_IMAGE_KEYS_ARE_DIGESTS = (
    "jsonb_typeof(pre_image) = 'object' AND NOT jsonb_path_exists(pre_image, "
    "'$.identifiers[*].key_hash ? (!(@ like_regex \"^[0-9a-f]{64}$\"))')"
)
EVIDENCE_IS_NAMES_AND_WEIGHTS = (
    "jsonb_typeof(evidence) = 'array' "
    "AND NOT jsonb_path_exists(evidence, '$[*] ? (@.type() != \"object\")') "
    "AND NOT jsonb_path_exists(evidence, "
    '\'$[*].keyvalue() ? (@.key != "field" && @.key != "weight")\')'
)

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0150`'s.
WIDENED_ACTIONS = (
    "action IN ('agent', 'agent_owner', 'approval', 'breach', 'break_glass', 'browser_session', "
    "'certification', 'channel_binding', 'compose_change', 'connector', 'credential', 'deny', "
    "'elevation', 'entity_merge', 'entity_unmerge', 'erasure', 'grant', 'halt', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'pack', 'principal_state', "
    "'publish', 'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', "
    "'sign_in', 'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('agent', 'agent_owner', 'approval', 'breach', 'break_glass', 'browser_session', "
    "'certification', 'channel_binding', 'compose_change', 'connector', 'credential', 'deny', "
    "'elevation', 'entity_merge', 'erasure', 'grant', 'halt', 'instructions', 'leash_change', "
    "'legal_hold', 'memory', 'organisation', 'pack', 'principal_state', 'publish', "
    "'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', "
    "'skill', 'vault_access', 'webhook')"
)

#: What this migration replaces: `0150`'s action list.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

ACTOR = "current_setting('brain.actor_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE er.merge ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE er.unmerge ENABLE ROW LEVEL SECURITY",
    # `USING (true)` for `0020`'s reason: which members of an entity a reader may see is decided
    # per source record in `brain.resolution.canonical.resolved_view`, and these rows carry no
    # field of any record.
    """
    CREATE POLICY merge_readable ON er.merge
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY merge_recorded_in_the_actors_name ON er.merge
        FOR INSERT TO brain_app
        WITH CHECK (decided_by = {ACTOR})
    """,
    """
    CREATE POLICY unmerge_readable ON er.unmerge
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY unmerge_recorded_in_the_actors_name ON er.unmerge
        FOR INSERT TO brain_app
        WITH CHECK (performed_by = {ACTOR})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: these are audit rows. Nothing for the fast lane.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON er.merge TO brain_app",
    "GRANT SELECT, INSERT ON er.unmerge TO brain_app",
)

#: The append, as `0003`, `0060` and `0104` write it. `{actor}`, `{action}`, `{subject}` and
#: `{details}` are the four expressions that differ.
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

#: The actor the application named, or `unattributed` with the mark in the details. `0095b`'s rule.
_ACTOR = """
    v_actor := NULLIF(current_setting('brain.actor_id', true), '');
    IF v_actor IS NULL THEN
        v_actor := 'unattributed';
        v_marked := true;
    END IF;
"""

#: The pointer cleared or set, each side's entry naming the store's rows where there are any.
ENTITY_MERGE_TRIGGER_FUNCTION = (
    """
CREATE OR REPLACE FUNCTION er.record_entity_merge() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text;
    v_marked boolean := false;
    v_details jsonb;
    v_subjects text[];
    v_merge_id text;
    v_unmerge_id text;"""
    + _DECLARE
    + """BEGIN"""
    + _ACTOR
    + """
    IF OLD.merged_into IS NOT NULL AND OLD.merged_into IS DISTINCT FROM NEW.merged_into THEN
        v_details := '{}'::jsonb;
        v_merge_id := NULL;
        v_unmerge_id := NULL;
        SELECT u.unmerge_id, u.merge_id INTO v_unmerge_id, v_merge_id
          FROM er.unmerge u
          JOIN er.merge m ON m.merge_id = u.merge_id
         WHERE m.merged_id = NEW.entity_id
           AND m.survivor_id = OLD.merged_into
           AND m.decided_at = OLD.merged_at;
        IF v_unmerge_id IS NOT NULL THEN
            v_details := jsonb_build_object('merge_id', v_merge_id, 'unmerge_id', v_unmerge_id);
        END IF;
        IF v_marked THEN
            v_details := v_details || jsonb_build_object('actor', 'unattributed');
        END IF;
        v_subjects := ARRAY['entity:' || OLD.merged_into, 'entity:' || NEW.entity_id];
        FOR i IN 1 .. 2 LOOP"""
    + _APPEND.format(
        actor="v_actor", action="entity_unmerge", subject="v_subjects[i]", details="v_details"
    )
    + """        END LOOP;
    END IF;
    IF NEW.merged_into IS NOT NULL AND NEW.merged_into IS DISTINCT FROM OLD.merged_into THEN
        v_details := '{}'::jsonb;
        v_merge_id := NULL;
        SELECT m.merge_id INTO v_merge_id
          FROM er.merge m
         WHERE m.merged_id = NEW.entity_id
           AND m.survivor_id = NEW.merged_into
           AND m.decided_at = NEW.merged_at;
        IF v_merge_id IS NOT NULL THEN
            v_details := jsonb_build_object('merge_id', v_merge_id);
        END IF;
        IF v_marked THEN
            v_details := v_details || jsonb_build_object('actor', 'unattributed');
        END IF;
        v_subjects := ARRAY['entity:' || NEW.merged_into, 'entity:' || NEW.entity_id];
        FOR i IN 1 .. 2 LOOP"""
    + _APPEND.format(
        actor="v_actor", action="entity_merge", subject="v_subjects[i]", details="v_details"
    )
    + """        END LOOP;
    END IF;
    RETURN NULL;
END;
$$
"""
)

#: `0104`'s function, put back by the downgrade. Held equal to `0104`'s own text by a test.
PREVIOUS_ENTITY_MERGE_TRIGGER_FUNCTION = (
    """
CREATE OR REPLACE FUNCTION er.record_entity_merge() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text;
    v_marked boolean := false;
    v_details jsonb := '{}'::jsonb;
    v_subjects text[];"""
    + _DECLARE
    + """BEGIN
    IF OLD.merged_into IS NOT NULL OR NEW.merged_into IS NULL THEN
        RETURN NULL;
    END IF;"""
    + _ACTOR
    + """    IF v_marked THEN
        v_details := jsonb_build_object('actor', 'unattributed');
    END IF;
    v_subjects := ARRAY['entity:' || NEW.merged_into, 'entity:' || NEW.entity_id];
    FOR i IN 1 .. 2 LOOP"""
    + _APPEND.format(
        actor="v_actor", action="entity_merge", subject="v_subjects[i]", details="v_details"
    )
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")

    # Bare constraint names: alembic applies the naming convention on top. See `0030`. In the
    # order the models declare them, so the rendered DDL is the model's character for character.
    op.create_table(
        "merge",
        sa.Column("merge_id", sa.String(32), nullable=False),
        sa.Column("survivor_id", sa.String(128), nullable=False),
        sa.Column("merged_id", sa.String(128), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=False),
        sa.Column("automatic", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("review_ref", sa.String(128), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("money_left", sa.String(32), nullable=False),
        sa.Column("money_right", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("pre_image", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("merge_id"),
        sa.ForeignKeyConstraint(["survivor_id"], ["er.canonical.entity_id"]),
        sa.ForeignKeyConstraint(["merged_id"], ["er.canonical.entity_id"]),
        sa.UniqueConstraint("merge_id", "survivor_id", "merged_id"),
        sa.CheckConstraint(f"merge_id ~ '{RECORD_ID_PATTERN}'", name="merge_id_shape"),
        sa.CheckConstraint("survivor_id <> merged_id", name="not_merged_into_itself"),
        sa.CheckConstraint(f"decided_by ~ '{IDENTIFIER}'", name="decided_by_is_an_identifier"),
        sa.CheckConstraint(
            f"confidence IS NULL OR ({CONFIDENCE_IS_A_SHARE})", name="confidence_is_a_share"
        ),
        sa.CheckConstraint(
            "automatic = (confidence IS NOT NULL)", name="automatic_carries_a_confidence"
        ),
        sa.CheckConstraint("automatic = (review_ref IS NULL)", name="reviewed_carries_a_reference"),
        sa.CheckConstraint(
            "review_ref IS NULL OR length(btrim(review_ref)) > 0", name="review_ref_present"
        ),
        sa.CheckConstraint(EVIDENCE_IS_NAMES_AND_WEIGHTS, name="evidence_is_names_and_weights"),
        sa.CheckConstraint(MONEY_LEFT_IN, name="money_left_known"),
        sa.CheckConstraint(MONEY_RIGHT_IN, name="money_right_known"),
        sa.CheckConstraint(PRE_IMAGE_KEYS_ARE_DIGESTS, name="pre_image_keys_are_digests"),
        schema="er",
    )
    op.create_index("ix_merge_merged_id", "merge", ["merged_id"], schema="er")
    op.create_table(
        "unmerge",
        sa.Column("unmerge_id", sa.String(32), nullable=False),
        sa.Column("merge_id", sa.String(32), nullable=False),
        sa.Column("survivor_id", sa.String(128), nullable=False),
        sa.Column("restored_id", sa.String(128), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed_by", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("unmerge_id"),
        sa.ForeignKeyConstraint(
            ["merge_id", "survivor_id", "restored_id"],
            ["er.merge.merge_id", "er.merge.survivor_id", "er.merge.merged_id"],
        ),
        sa.UniqueConstraint("merge_id"),
        sa.CheckConstraint(f"unmerge_id ~ '{RECORD_ID_PATTERN}'", name="unmerge_id_shape"),
        sa.CheckConstraint(f"performed_by ~ '{IDENTIFIER}'", name="performed_by_is_an_identifier"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        schema="er",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The function is replaced; `0104`'s trigger, `AFTER UPDATE OF merged_into`, already fires
    # on both directions and is left as it is.
    op.execute(ENTITY_MERGE_TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(PREVIOUS_ENTITY_MERGE_TRIGGER_FUNCTION)
    # The policies and the grants go with the tables; their ledger entries stay.
    op.drop_table("unmerge", schema="er")
    op.drop_index("ix_merge_merged_id", table_name="merge", schema="er")
    op.drop_table("merge", schema="er")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
