"""A run's trace graph is stored masked behind a role of its own, and a browser session is audited.

M24.3.4 asks an install to show two things nothing built. `brain.tables.telemetry` argues the
trace store's shape and `brain.tables.browsing` the session's; what is here is the three tables,
the reader role, their policies and grants, the ledger's widened action list and the trigger.

**`obs.trace_step` is written by the application and read by nobody on its role.** `brain_app`
holds INSERT and no SELECT; `brain_trace_reader`, created here NOLOGIN NOSUPERUSER NOBYPASSRLS
NOINHERIT like `0001`'s fast-lane role, holds SELECT and nothing else. `brain_app` is granted the
role `WITH INHERIT FALSE, SET TRUE`, which PostgreSQL 16 and later accept and every compose file
ships (18): it may `SET LOCAL ROLE` to it, which is what `brain.ops.trace_store.StoredTraces.read`
does after writing its row, and it inherits none of its privileges whatever `brain_app`'s own
INHERIT attribute is, so a role created by hand before `0001` does not undo the separation.
**The payload columns admit only what `brain.ops.tracing.mask` leaves**, the four size classes,
copied here and held equal to `tracing.MASKED_PAYLOADS` by a test.

**`obs.trace_read` is the row before every read** (`tracing.PayloadRead`), inserted in the
reader's own name through `app.principal_id`, and read by the application, because who read a
trace is not itself a trace. SELECT and INSERT; never UPDATE or DELETE on either table.

**`agent.browser_session` keys on the run and points at its sealed envelope**, so a session opens
only on a run somebody sealed. Read with `USING (true)` for `0041`'s reason; inserted by the
application; updated only while open, and only in the two columns an end moves. The trigger
appends `browser_session` under `session:<run id>` on the insert (`started`) and on the update
that sets `ended_at` (`ended`, with the recording's digest when there is one). **The actor is the
envelope's asker and the trace is the row's own**, both read by the database rather than taken
from session settings, so the entry names whom the run acted for and the trace its graph is kept
under. The reach digest is the request's when one was set, and the sentinel otherwise.

**The action list gains `browser_session`**, superseding `0141`'s, the last in the database. The
subject kind `session` exists since `0002`, so the grammar does not change.

**The downgrade** drops the trigger, its function and the three tables, revokes the reader role
from the application and puts `0141`'s action list back `NOT VALID`, for `0026`'s reason: an entry
already recorded stays. The role itself is left, for `0001`'s reason about roles on a cluster.

Revises `0149`, the head of main when this was written.

Task ids: M24.3.4, M27.1.3

Revision ID: 0150
Revises: 0149
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.browser_session", "obs.trace_step", "obs.trace_read")

APP_ROLE = "brain_app"
READER_ROLE = "brain_trace_reader"

#: Copied for the reason `0009` gives about reading live code from a migration, and each held
#: equal to its source by `tests/unit/test_trace_store.py`: `brain.audit.ledger.TRACE_ID`,
#: `brain.gate.leash.DIGEST`, `brain.ops.tracing.VALUE_TOKEN_RE` and `tracing.MASKED_PAYLOADS`.
TRACE_ID_PATTERN = "^[A-Za-z0-9_.-]{1,64}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"
NAME_PATTERN = "^[a-z0-9][a-z0-9._:/-]*$"
MASKED_IN = (
    "('[masked:str/empty]', '[masked:str/large]', '[masked:str/medium]', '[masked:str/small]')"
)
KIND_IN = "kind IN ('model_attempt', 'request', 'retrieval', 'tool_call')"

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0141`'s.
WIDENED_ACTIONS = (
    "action IN ('agent', 'agent_owner', 'approval', 'breach', 'break_glass', 'browser_session', "
    "'certification', 'channel_binding', 'compose_change', 'connector', 'credential', 'deny', "
    "'elevation', 'entity_merge', 'erasure', 'grant', 'halt', 'instructions', 'leash_change', "
    "'legal_hold', 'memory', 'organisation', 'pack', 'principal_state', 'publish', "
    "'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', "
    "'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('agent', 'agent_owner', 'approval', 'breach', 'break_glass', 'certification', "
    "'channel_binding', 'compose_change', 'connector', 'credential', 'deny', 'elevation', "
    "'entity_merge', 'erasure', 'grant', 'halt', 'instructions', 'leash_change', 'legal_hold', "
    "'memory', 'organisation', 'pack', 'principal_state', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', "
    "'vault_access', 'webhook')"
)

#: What this migration replaces: `0141`'s action list.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}

#: The reader role, created once per cluster as `0001` creates its two.
CREATE_READER_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_trace_reader') THEN
        CREATE ROLE brain_trace_reader NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
    END IF;
END
$$;
"""

#: The application may take the reader role for a transaction and inherits nothing from it.
MEMBERSHIP = "GRANT brain_trace_reader TO brain_app WITH INHERIT FALSE, SET TRUE"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.browser_session ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY browser_session_readable ON agent.browser_session
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY browser_session_started ON agent.browser_session
        FOR INSERT TO brain_app
        WITH CHECK (ended_at IS NULL AND recording_digest IS NULL)
    """,
    """
    CREATE POLICY browser_session_ended_once ON agent.browser_session
        FOR UPDATE TO brain_app
        USING (ended_at IS NULL)
        WITH CHECK (ended_at IS NOT NULL)
    """,
    "ALTER TABLE obs.trace_step ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY trace_step_appendable ON obs.trace_step
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY trace_step_readable_by_its_reader ON obs.trace_step
        FOR SELECT TO brain_trace_reader
        USING (true)
    """,
    "ALTER TABLE obs.trace_read ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY trace_read_readable ON obs.trace_read
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY trace_read_in_the_readers_name ON obs.trace_read
        FOR INSERT TO brain_app
        WITH CHECK (actor = current_setting('app.principal_id', true))
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.browser_session TO brain_app",
    "GRANT UPDATE (ended_at, recording_digest) ON agent.browser_session TO brain_app",
    "GRANT INSERT ON obs.trace_step TO brain_app",
    "GRANT SELECT, INSERT ON obs.trace_read TO brain_app",
)

READER_GRANTS: tuple[str, ...] = (
    "GRANT USAGE ON SCHEMA obs TO brain_trace_reader",
    "GRANT SELECT ON obs.trace_step TO brain_trace_reader",
)

#: Each end of a session, under the run, as its envelope's asker and the run's own trace.
SESSION_TRIGGER_FUNCTION = """
CREATE FUNCTION agent.record_browser_session() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'session:' || NEW.run_id;
    v_actor text;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text := NEW.trace_id;
    v_written integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_details := jsonb_build_object('change', 'started');
    ELSIF OLD.ended_at IS NULL AND NEW.ended_at IS NOT NULL THEN
        v_details := jsonb_build_object('change', 'ended');
        IF NEW.recording_digest IS NOT NULL THEN
            v_details := v_details || jsonb_build_object('recording', NEW.recording_digest);
        END IF;
    ELSE
        RETURN NULL;
    END IF;
    SELECT e.asked_by INTO v_actor FROM agent.browser_envelope e WHERE e.run_id = NEW.run_id;

    PERFORM pg_advisory_xact_lock(8274419004);
    SELECT COALESCE(max(e.seq) + 1, 0) INTO v_seq FROM obs.audit_entry e;
    SELECT COALESCE(
        (SELECT e.entry_hash FROM obs.audit_entry e ORDER BY e.seq DESC LIMIT 1),
        repeat('0', 64)
    ) INTO v_prev;
    v_ent_hash := COALESCE(NULLIF(current_setting('brain.ent_hash', true), ''), repeat('0', 32));
    v_entry := obs.audit_entry_hash(
        v_seq, v_at, v_actor, 'browser_session', v_subject, v_ent_hash,
        v_trace, v_details, v_prev
    );

    MERGE INTO obs.audit_entry AS t
    USING (SELECT v_seq AS seq) AS s
       ON t.seq = s.seq
    WHEN NOT MATCHED THEN
        INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                details, prev_hash, entry_hash)
        VALUES (v_seq, v_at, v_actor, 'browser_session', v_subject,
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

SESSION_TRIGGER = """
CREATE TRIGGER browser_session_is_audited
    AFTER INSERT OR UPDATE ON agent.browser_session
    FOR EACH ROW EXECUTE FUNCTION agent.record_browser_session()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all(READER_ROLE in statement for statement in READER_GRANTS)
    assert all("DELETE" not in statement for statement in (*GRANTS, *READER_GRANTS))

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "browser_session",
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recording_digest", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID_PATTERN}'", name="trace_id_shape"),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name="a_session_ends_after_it_starts"
        ),
        sa.CheckConstraint(
            f"recording_digest IS NULL OR recording_digest ~ '{DIGEST_PATTERN}'",
            name="recording_digest_shape",
        ),
        sa.CheckConstraint(
            "recording_digest IS NULL OR ended_at IS NOT NULL",
            name="a_recording_is_named_when_the_session_ends",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent.browser_envelope.run_id"], ondelete="RESTRICT"),
        schema="agent",
    )
    op.create_table(
        "trace_step",
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("step", sa.SmallInteger(), nullable=False),
        sa.Column("parent", sa.SmallInteger(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("payload_in", sa.Text(), nullable=False),
        sa.Column("payload_out", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("trace_id", "step"),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID_PATTERN}'", name="trace_id_shape"),
        sa.CheckConstraint("step >= 0", name="step_not_negative"),
        sa.CheckConstraint(
            "(parent IS NULL) = (step = 0) AND (parent IS NULL OR parent < step)",
            name="a_step_hangs_from_an_earlier_one",
        ),
        sa.CheckConstraint(KIND_IN, name="kind"),
        sa.CheckConstraint("(kind = 'request') = (step = 0)", name="the_request_is_step_zero"),
        sa.CheckConstraint(f"name ~ '{NAME_PATTERN}'", name="name_is_vocabulary"),
        sa.CheckConstraint("jsonb_typeof(attributes) = 'object'", name="attributes_object"),
        sa.CheckConstraint(f"payload_in IN {MASKED_IN}", name="payload_in_masked"),
        sa.CheckConstraint(f"payload_out IN {MASKED_IN}", name="payload_out_masked"),
        schema="obs",
    )
    op.create_table(
        "trace_read",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(actor)) > 0", name="somebody_read_it"),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID_PATTERN}'", name="trace_id_shape"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="a_read_states_why"),
        schema="obs",
    )
    op.create_index("ix_trace_read_trace_id", "trace_read", ["trace_id"], schema="obs")

    op.execute(CREATE_READER_ROLE)
    op.execute(MEMBERSHIP)
    for statement in RLS:
        op.execute(statement)
    for statement in (*GRANTS, *READER_GRANTS):
        op.execute(statement)
    op.execute(SESSION_TRIGGER_FUNCTION)
    op.execute(SESSION_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER browser_session_is_audited ON agent.browser_session")
    op.execute("DROP FUNCTION agent.record_browser_session()")
    op.drop_index("ix_trace_read_trace_id", table_name="trace_read", schema="obs")
    # The policies and the grants go with the tables.
    op.drop_table("trace_read", schema="obs")
    op.drop_table("trace_step", schema="obs")
    op.drop_table("browser_session", schema="agent")
    op.execute("REVOKE USAGE ON SCHEMA obs FROM brain_trace_reader")
    op.execute("REVOKE brain_trace_reader FROM brain_app")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
