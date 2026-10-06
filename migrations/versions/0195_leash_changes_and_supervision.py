"""An agent's rungs move on the install, with their evidence, and its supervision is reviewed.

`brain.console.reach_view` decided how a rung may move once an agent is installed and
`brain.agents.supervision` decided the thirty-day review; nothing stored either, so every rung was
the install's for ever and no review had anywhere to be kept. `brain.tables.leash` holds the
argument for each column and `brain.ops.leash_store` is the one writer.

**`agent.leash_change`**: one row per move of one rung (lowered, proposed, raised, tripped), each
carrying exactly its own evidence, which the checks below hold. **`agent.supervised_action`**:
`brain.gate.leash.ActionRecord` stored, once per action and route. **`agent.action_verdict`**: one
person's verdict on one of those actions. **`agent.supervision_pin`**: a pin and each review of it.

**SELECT and INSERT only, written in the session's own name**, `0149`'s shape: a move, a verdict
and a review are new rows. A supervised action is written by whoever runs the agent, which is the
worker's login or the request's principal, so its insert policy names the principal the action ran
for. Nobody may edit a move, and the rung a key stands at is its newest move.

**Every lowered, raised and tripped move appends one `leash_change` entry about the agent**, in the
same transaction, with the target, both rungs and the kind: `0104`'s action and subject for the
install's own leash, so an agent's leash reads as one subject in the ledger whichever way it moved.
A proposal appends nothing, because nothing moved. Never the evidence's figures and never the
approvers beyond the entry's own actor: the table holds those beside the move.

**The downgrade drops the four tables, the function and the trigger**, and the ledger entries stay,
because nothing may delete one: `0056`'s reason.

Written as 0158 over 0153 in #254, and replayed as 0195 over 0194, the artifact replay it stacks
on; whoever lands it later re-points `down_revision` and nothing else.

Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0195"
down_revision = "0194"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = (
    "agent.leash_change",
    "agent.supervised_action",
    "agent.action_verdict",
    "agent.supervision_pin",
)

APP_ROLE = "brain_app"

#: Widths and vocabularies copied for the reason `0009` gives about reading live code from a
#: migration, and held equal to `brain.tables.leash` by `tests/unit/test_leash_store.py`.
AGENT_ID_CHARS = 128
TARGET_CHARS = 120
TOOL_CHARS = 80
WORD_CHARS = 16
TRACE_ID_CHARS = 128
REASON_CHARS = 64
METRIC_CHARS = 120
PRINCIPAL_ID_CHARS = 128
TOP_RUNG = 2
TARGET_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"
ENT_HASH_PATTERN = r"^[0-9a-f]{32}$"
REASON_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
KINDS = "kind IN ('lowered', 'proposed', 'raised', 'tripped')"
ROUTES = "route IN ('execute', 'simulate', 'suspend')"
VERDICTS = "verdict IN ('amended', 'approved', 'rejected', 'taken_over')"
OUTCOMES = "outcome IN ('eligible', 'extended', 'pinned')"
A_RAISE_NAMES_ITS_APPROVER_AND_ITS_EVIDENCE = (
    "kind NOT IN ('raised', 'proposed') OR (approver_id IS NOT NULL "
    "AND clean_runs IS NOT NULL AND agreement_rate IS NOT NULL AND became > was)"
)
A_FALL_CARRIES_NO_PROMOTION_EVIDENCE = (
    "kind NOT IN ('lowered', 'tripped') OR (became < was AND approver_id IS NULL "
    "AND second_approver_id IS NULL AND clean_runs IS NULL AND agreement_rate IS NULL)"
)
A_TRIP_NAMES_ITS_METRIC = (
    "(kind = 'tripped') = (metric IS NOT NULL AND measured IS NOT NULL AND threshold IS NOT NULL)"
)
TWO_APPROVERS_ARE_TWO_PEOPLE = (
    "second_approver_id IS NULL OR (kind = 'raised' AND second_approver_id <> approver_id)"
)
AN_IRREVERSIBLE_RISE_HAS_TWO_APPROVERS = (
    "kind <> 'raised' OR NOT irreversible OR second_approver_id IS NOT NULL"
)

A_REVIEW_CARRIES_ITS_COUNTS = (
    "(outcome = 'pinned') = (understood IS NULL AND reviewed IS NULL AND simulated IS NULL)"
)

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.leash_change ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.supervised_action ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.action_verdict ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE agent.supervision_pin ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY leash_change_readable ON agent.leash_change
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY leash_change_made_in_the_sessions_name ON agent.leash_change
        FOR INSERT TO brain_app
        WITH CHECK (changed_by = {PRINCIPAL})
    """,
    """
    CREATE POLICY supervised_action_readable ON agent.supervised_action
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY supervised_action_recorded_for_the_sessions_principal ON agent.supervised_action
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
    """
    CREATE POLICY action_verdict_readable ON agent.action_verdict
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY action_verdict_given_in_the_sessions_name ON agent.action_verdict
        FOR INSERT TO brain_app
        WITH CHECK (reviewer_id = {PRINCIPAL})
    """,
    """
    CREATE POLICY supervision_pin_readable ON agent.supervision_pin
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY supervision_pin_decided_in_the_sessions_name ON agent.supervision_pin
        FOR INSERT TO brain_app
        WITH CHECK (decided_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a move, a verdict and a review are new rows.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.leash_change TO brain_app",
    "GRANT SELECT, INSERT ON agent.supervised_action TO brain_app",
    "GRANT SELECT, INSERT ON agent.action_verdict TO brain_app",
    "GRANT SELECT, INSERT ON agent.supervision_pin TO brain_app",
)

#: The append the trigger makes, copied from `0149`, which copied `0139`, `0121`, `0056` and
#: `0003`.
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

#: One `leash_change` entry about the agent for every move that moved a rung. The rung names are
#: `0104`'s, by `AutonomyTier` value, and the kind is the move's own word.
LEASH_MOVE_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_leash_move() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_names text[] := ARRAY['shadow', 'assisted', 'autonomous'];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF NEW.kind = 'proposed' THEN
        RETURN NULL;
    END IF;
    v_details := jsonb_build_object(
        'target', NEW.target,
        'from_rung', v_names[NEW.was + 1],
        'to_rung', v_names[NEW.became + 1],
        'kind', NEW.kind
    );"""
    + _APPEND.format(
        actor="NEW.changed_by",
        action="leash_change",
        subject="'agent:' || NEW.agent_id",
        details="v_details",
    )
    + """    RETURN NULL;
END;
$$
"""
)

LEASH_MOVE_TRIGGER = """
    CREATE TRIGGER leash_change_is_audited
        AFTER INSERT ON agent.leash_change
        FOR EACH ROW EXECUTE FUNCTION agent.record_leash_move()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    op.create_table(
        "leash_change",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("target", sa.String(TARGET_CHARS), nullable=False),
        sa.Column("scope", JSONB(), nullable=False),
        sa.Column("was", sa.SmallInteger(), nullable=False),
        sa.Column("became", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.String(WORD_CHARS), nullable=False),
        sa.Column("irreversible", sa.Boolean(), nullable=False),
        sa.Column("approver_id", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("second_approver_id", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("clean_runs", sa.Integer(), nullable=True),
        sa.Column("agreement_rate", sa.Double(), nullable=True),
        sa.Column("metric", sa.String(METRIC_CHARS), nullable=True),
        sa.Column("measured", sa.Double(), nullable=True),
        sa.Column("threshold", sa.Double(), nullable=True),
        sa.Column("changed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason_code", sa.String(REASON_CHARS), nullable=False),
        sa.Column("entitlement_hash", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(KINDS, name="kind"),
        sa.CheckConstraint(f"target ~ '{TARGET_PATTERN}'", name="target_shape"),
        sa.CheckConstraint(f"was BETWEEN 0 AND {TOP_RUNG}", name="was_is_a_rung"),
        sa.CheckConstraint(f"became BETWEEN 0 AND {TOP_RUNG}", name="became_is_a_rung"),
        sa.CheckConstraint("jsonb_typeof(scope) = 'object'", name="scope_is_a_scope"),
        sa.CheckConstraint(
            A_RAISE_NAMES_ITS_APPROVER_AND_ITS_EVIDENCE, name="a_raise_has_evidence"
        ),
        sa.CheckConstraint(A_FALL_CARRIES_NO_PROMOTION_EVIDENCE, name="a_fall_has_none"),
        sa.CheckConstraint(A_TRIP_NAMES_ITS_METRIC, name="a_trip_names_its_metric"),
        sa.CheckConstraint(TWO_APPROVERS_ARE_TWO_PEOPLE, name="two_approvers_are_two_people"),
        sa.CheckConstraint(
            AN_IRREVERSIBLE_RISE_HAS_TWO_APPROVERS, name="an_irreversible_rise_has_two_approvers"
        ),
        sa.CheckConstraint(
            "agreement_rate IS NULL OR (agreement_rate >= 0 AND agreement_rate <= 1)",
            name="agreement_is_a_share",
        ),
        sa.CheckConstraint("clean_runs IS NULL OR clean_runs >= 0", name="clean_runs_counted"),
        sa.CheckConstraint(f"reason_code ~ '{REASON_PATTERN}'", name="reason_is_a_code"),
        sa.CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        schema="agent",
    )
    op.create_index(
        "ix_leash_change_agent_changed", "leash_change", ["agent_id", "changed_at"], schema="agent"
    )

    op.create_table(
        "supervised_action",
        sa.Column("action_digest", sa.String(64), nullable=False),
        sa.Column("route", sa.String(WORD_CHARS), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("tool_name", sa.String(TOOL_CHARS), nullable=False),
        sa.Column("target", sa.String(TARGET_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("ent_hash", sa.String(32), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("checks", ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("action_digest", "route"),
        sa.CheckConstraint(f"action_digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint(ROUTES, name="route_ran"),
        sa.CheckConstraint(f"tier BETWEEN 0 AND {TOP_RUNG}", name="tier_is_a_rung"),
        sa.CheckConstraint(f"ent_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint(
            "length(btrim(agent_id)) > 0 AND length(btrim(principal_id)) > 0",
            name="attributed",
        ),
        schema="agent",
    )
    op.create_index(
        "ix_supervised_action_agent_at", "supervised_action", ["agent_id", "at"], schema="agent"
    )

    op.create_table(
        "action_verdict",
        sa.Column("action_digest", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("verdict", sa.String(WORD_CHARS), nullable=False),
        sa.Column("reviewer_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("action_digest"),
        sa.CheckConstraint(f"action_digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint(VERDICTS, name="verdict"),
        sa.CheckConstraint("length(btrim(reviewer_id)) > 0", name="attributed"),
        schema="agent",
    )
    op.create_index(
        "ix_action_verdict_agent_at", "action_verdict", ["agent_id", "at"], schema="agent"
    )

    op.create_table(
        "supervision_pin",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("outcome", sa.String(WORD_CHARS), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("understood", sa.Integer(), nullable=True),
        sa.Column("reviewed", sa.Integer(), nullable=True),
        sa.Column("simulated", sa.Integer(), nullable=True),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("entitlement_hash", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(OUTCOMES, name="outcome"),
        sa.CheckConstraint("review_due_at > pinned_at", name="due_after_it_began"),
        sa.CheckConstraint(
            A_REVIEW_CARRIES_ITS_COUNTS,
            name="a_review_carries_its_counts",
        ),
        sa.CheckConstraint(
            "understood IS NULL OR (understood >= 0 AND understood <= reviewed "
            "AND reviewed <= simulated)",
            name="counts_are_a_measurement",
        ),
        sa.CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint("length(btrim(decided_by)) > 0", name="attributed"),
        schema="agent",
    )
    op.create_index(
        "ix_supervision_pin_agent_decided",
        "supervision_pin",
        ["agent_id", "decided_at"],
        schema="agent",
    )

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(LEASH_MOVE_TRIGGER_FUNCTION)
    op.execute(LEASH_MOVE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER leash_change_is_audited ON agent.leash_change")
    op.execute("DROP FUNCTION agent.record_leash_move()")
    op.drop_table("supervision_pin", schema="agent")
    op.drop_table("action_verdict", schema="agent")
    op.drop_table("supervised_action", schema="agent")
    op.drop_table("leash_change", schema="agent")
