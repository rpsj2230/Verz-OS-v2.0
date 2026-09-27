"""A request to erase somebody's data gets a table, its ledger entries, and a place on the schedule.

The Retention and erasure screen said that a request to erase somebody's data "has to be handled and
recorded outside this system", because nothing stored one and nothing carried one out.
`brain.tables.erasure` holds the argument for the columns; what is here is the table, its policies,
the ledger member and subject kind it is recorded under, the trigger that records it, and the name
the worker's schedule records its runs under.

**SELECT and INSERT for the application, and nothing else.** An administrator files a request as
themselves: the insert policy admits a row whose `requested_by` is the session's principal and which
is not finished, so a request cannot be filed in somebody else's name or arrive already carried out.
**Finishing is the queue's**, and the queue runs in the worker on the database owner's connection,
which `brain.ops.erasure_store.A_CONNECTION_ROW_SECURITY_NARROWS_CANNOT_COUNT_WHAT_IT_ERASES` argues
it has to: the application role holds no UPDATE here, so a request cannot be marked erased by any
request the console serves. Read with `USING (true)`, for the reason `0053` gives: who may read the
queue is `brain.console.govern_surfaces.deletion_rows`, decided against the reader's live grants.

**`erasure` is a new ledger member and a new subject kind**, argued in
`brain.audit.ledger.AuditAction`. The action list gains one member and the subject grammar one
kind, each replacing `0059`'s, which are the two in the database. The trigger fires on the insert,
`requested` by the row's `requested_by`, and on the one update that finishes the row, the outcome
by the row's `finished_by`; any other update appends nothing. **The subject is the request and
never the person**, and the details are the change and nothing else.

**`erasure_queue` joins the control-run names**, replacing `0037`'s list, for the reason `0037`
gives about the spend report refresh: `brain.ops.controls` registers the control, the model's
constraint is generated from that registry, and without the widening the first run the schedule
records is refused by the database. The constraint is dropped by whichever name it holds, as
`0037` does.

**The append is `0003`'s, another copy of that block**, beside `0047`'s to `0059`'s, for the reason
`0047` gives against editing a function every grant in production goes through.

**The downgrade keeps the rows already written**, for the reason `0026` gives: the action list, the
subject grammar and the control names go back `NOT VALID`, so an entry or a run already carrying
the new values stays and no new one is accepted. The table goes with it, and its ledger entries
stay, because nothing may delete one.

Task ids: M27.7.24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.erasure_request",)

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.erasure` by `tests/unit/test_tables.py`'s model comparison.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_./#-]{0,63}$"
PRINCIPAL_ID_CHARS = 128
REFERENCE_CHARS = 64

#: `brain.tables.erasure.ErasureOutcome`, sorted as `one_of` sorts.
OUTCOME_IN = "outcome IN ('erased', 'held', 'incomplete')"

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0059`'s.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'publish', 'record_read', 'retention', 'revoke', 'routing', "
    "'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'grant', 'instructions', 'leash_change', 'legal_hold', "
    "'publish', 'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', "
    "'sign_in', 'skill', 'webhook')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0059`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|erasure|grant|leash|legal_hold"
    "|principal|retention|routing|session|setting|skill|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|entity|grant|leash|legal_hold|principal"
    "|retention|routing|session|setting|skill|webhook):[A-Za-z0-9_.@-]{1,128}$'"
)

#: The control-run names, with and without `erasure_queue`. The second is `0037`'s.
WITH_ERASURE_QUEUE = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'erasure_queue', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh')"
)
WITHOUT_ERASURE_QUEUE = (
    "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
    "'directory_sync', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh')"
)

#: What this migration replaces: `0059`'s action list, `0059`'s subject grammar and `0037`'s
#: control names, which are the three in the database.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
    WITHOUT_ERASURE_QUEUE: WITH_ERASURE_QUEUE,
}

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.erasure_request ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY erasure_request_readable ON ops.erasure_request
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY erasure_request_filed_in_the_sessions_name ON ops.erasure_request
        FOR INSERT TO brain_app
        WITH CHECK (requested_by = {PRINCIPAL} AND finished_at IS NULL)
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE. See the module docstring.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.erasure_request TO brain_app",)

#: The append the trigger makes, as `0003` and `0057` write it. `{actor}`, `{action}`, `{subject}`
#: and `{details}` are the four expressions that differ.
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

#: A request filed, then finished, each with the actor its own column names. A row inserted already
#: finished, which only an operator's statement can write, records both, in order.
ERASURE_REQUEST_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_erasure_request() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'erasure:' || NEW.request_id::text;
    v_changes text[] := ARRAY[]::text[];
    v_actors text[] := ARRAY[]::text[];
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'requested'::text;
        v_actors := v_actors || NEW.requested_by::text;
        IF NEW.finished_at IS NOT NULL THEN
            v_changes := v_changes || NEW.outcome::text;
            v_actors := v_actors || NEW.finished_by::text;
        END IF;
    ELSIF OLD.finished_at IS NULL AND NEW.finished_at IS NOT NULL THEN
        v_changes := v_changes || NEW.outcome::text;
        v_actors := v_actors || NEW.finished_by::text;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);"""
    + _APPEND.format(
        actor="v_actors[i]", action="erasure", subject="v_subject", details="v_details"
    )
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER erasure_request_is_audited
        AFTER INSERT OR UPDATE ON ops.erasure_request
        FOR EACH ROW EXECUTE FUNCTION ops.record_erasure_request()
    """,
)

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0037` copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'ops.control_run'::regclass
           AND c.contype = 'c'
           AND right(c.conname, 16) = 'control_run_name'
    LOOP
        EXECUTE 'ALTER TABLE ops.control_run DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "erasure_request",
        sa.Column(
            "request_id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subject_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason_reference", sa.String(REFERENCE_CHARS), nullable=False),
        sa.Column("requested_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("stores", postgresql.JSONB(), nullable=True),
        sa.Column("holds", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint(f"subject_id ~ '{IDENTIFIER}'", name="subject_is_an_identifier"),
        sa.CheckConstraint(f"requested_by ~ '{IDENTIFIER}'", name="requested_by_is_an_identifier"),
        sa.CheckConstraint(
            f"reason_reference ~ '{REFERENCE_PATTERN}'", name="reference_is_a_token"
        ),
        sa.CheckConstraint(
            f"finished_by IS NULL OR finished_by ~ '{IDENTIFIER}'",
            name="finished_by_is_an_identifier",
        ),
        sa.CheckConstraint(f"outcome IS NULL OR {OUTCOME_IN}", name="outcome"),
        sa.CheckConstraint(
            "(finished_at IS NULL) = (finished_by IS NULL) "
            "AND (finished_at IS NULL) = (outcome IS NULL) "
            "AND (finished_at IS NULL) = (stores IS NULL) "
            "AND (finished_at IS NULL) = (holds IS NULL)",
            name="finished_whole",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= requested_at",
            name="finished_after_it_was_requested",
        ),
        sa.CheckConstraint("stores IS NULL OR jsonb_typeof(stores) = 'array'", name="stores_list"),
        sa.CheckConstraint("holds IS NULL OR jsonb_typeof(holds) = 'array'", name="holds_list"),
        sa.CheckConstraint(
            "outcome IS NULL OR (outcome = 'held') = (jsonb_array_length(holds) > 0)",
            name="held_names_its_holds",
        ),
        schema="ops",
    )
    op.create_index(
        "uq_erasure_request_open",
        "erasure_request",
        ["subject_id"],
        unique=True,
        schema="ops",
        postgresql_where=sa.text("finished_at IS NULL"),
    )
    op.create_index(
        "ix_erasure_request_requested_at", "erasure_request", ["requested_at"], schema="ops"
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint names, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("subject_grammar", "audit_entry", WIDENED_SUBJECTS, schema="obs")
    op.execute(ERASURE_REQUEST_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)

    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint("control_run_name", "control_run", WITH_ERASURE_QUEUE, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_ERASURE_QUEUE,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.execute("DROP TRIGGER erasure_request_is_audited ON ops.erasure_request")
    op.execute("DROP FUNCTION ops.record_erasure_request()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs", postgresql_not_valid=True
    )
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
    # The policies, the grants and the indexes go with the table.
    op.drop_table("erasure_request", schema="ops")
