"""Who is in each team, who leads each department, and elevation requests, each audited.

`brain.tables.organisation` and `brain.tables.elevation` argue the shape of the three tables. What
is here is the tables, their policies, their grants, the two ledger members they are recorded
under and the three triggers that record them.

**Read by the application, added to, and ended or decided once.** For a membership and a lead:
SELECT and INSERT, and UPDATE on the two ending columns alone, so who was placed, where and by whom
can never be edited after the fact. The insert policy admits only a live row and the update policy
only a live row becoming ended, which are `0057`'s two policies for a connection applied to two more
objects. For a request: SELECT and INSERT, and UPDATE on the five decision columns alone, with the
insert policy admitting only a pending row and the update policy only a pending row becoming
decided, so a decision cannot be changed or undone by the application and a request asked again is
a new row. No DELETE on any of the three. `USING (true)` on the reads is not an absence of a
permission check, for the reason `0030` gives: who may be shown a placement or a request is
`brain.console.organisation`'s and `brain.console.elevation`'s question, asked against the reader's
own grants before anything is shown.

**No bump of `gate.grants_version` on a placement.** A membership and a lead confer nothing and no
resolver reads either, so moving every cached answer's epoch on a placement buys nothing; see
`brain.tables.organisation`. An approved elevation's reach is the grant row it writes, and that
row's own `0003` triggers bump and record it exactly as they do for every grant.

**The ledger gains two members, `organisation` and `elevation`**, which
`brain.audit.ledger.AuditAction` argues. The action list is superseded again, replacing the one in the
database before it. Both write under the subject kind `principal`, which has been in
the grammar since `0002`, so the grammar is not touched.

**Each trigger fires on the insert and on the one update that ends or decides the row**, with the
actor read off the row's own column for that change, as `0057`'s reads its. A row inserted already
ended or decided, which only an operator's statement can write, records both changes in order, for
`0054`'s reason. The details are the change and where: a team's path, `<department>.<team>`, read
through the team's own department; a department's slug; or a request's capability and reason code.
Never a request's explanation, which the ledger would keep as a marker.

**The append is `0003`'s, and this is three more copies of that block**, beside `0047`'s and
every one since, for the reason `0047` gives against editing a function every grant in production goes
through. Same advisory lock, same sequence and parent read, same `obs.audit_entry_hash`, same
refusal of a discarded MERGE.

**The downgrade can fail, which is correct**, for `0026`'s reason: narrowing the action list is
refused once any entry records a placement or a request, and an audit entry cannot be deleted to
make room. It drops the three tables with it, and with them every placement and request, which is
the state before this migration.

Task ids: M27.7.4, M27.7.8
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = (
    "gate.team_membership",
    "gate.department_lead",
    "gate.elevation_request",
)

APP_ROLE = "brain_app"

#: Widths and grammars copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.audit.ledger.IDENTIFIER`, `brain.tables.identity.PRINCIPAL_ID_CHARS`,
#: `brain.tables.gate` and `brain.tables.elevation` by `tests/unit/test_organisation_store.py` and
#: `tests/unit/test_elevation_store.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128
CAPABILITY_CHARS = 200
CAPABILITY_PATTERN = r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*|\.\*)*$"
CAPABILITY_VERBS = (
    "split_part(capability, ':', 1) IN ('admin', 'approve', 'invoke', 'read', 'write')"
)
SLUG_CHARS = 60
#: `brain.tables.gate.SLUG_SQL_PATTERN`: the colon escaped so it survives `text()`. See that module.
SLUG_SQL_PATTERN = "^[a-z][a-z0-9]*(?\\:_[a-z0-9]+)*$"
REASONS = "reason IN ('data_recovery', 'incident_response', 'install', 'lockout')"
REASON_CHARS = 32
EXPLANATION_CHARS = 500
LONGEST_HOURS = 4
DECISIONS = "decision IN ('approved', 'denied')"
DECISION_CHARS = 8

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is the list this
#: replaces, which is the one the migration before this leaves in the database.
WIDENED_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'publish', 'record_read', "
    "'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'publish', 'record_read', 'retention', 'revoke', "
    "'routing', 'session_end', 'setting', 'sign_in', 'skill', 'webhook')"
)

#: What this migration replaces: the action list the migration before it leaves.
SUPERSEDES: dict[str, str] = {NARROWER_ACTIONS: WIDENED_ACTIONS}


#: Written out for each table rather than built by a helper, because `brain.ops.migration_policy`
#: and `brain.ops.install_from_empty` read `ALTER TABLE <table> ENABLE ROW LEVEL SECURITY` off the
#: source text: a statement assembled at import is one they cannot see.
RLS: tuple[str, ...] = (
    "ALTER TABLE gate.team_membership ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY team_membership_readable ON gate.team_membership
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY team_membership_live ON gate.team_membership
        FOR INSERT TO brain_app
        WITH CHECK (ended_at IS NULL AND ended_by IS NULL)
    """,
    """
    CREATE POLICY team_membership_ended_once ON gate.team_membership
        FOR UPDATE TO brain_app
        USING (ended_at IS NULL)
        WITH CHECK (ended_at IS NOT NULL)
    """,
    "ALTER TABLE gate.department_lead ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY department_lead_readable ON gate.department_lead
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY department_lead_live ON gate.department_lead
        FOR INSERT TO brain_app
        WITH CHECK (ended_at IS NULL AND ended_by IS NULL)
    """,
    """
    CREATE POLICY department_lead_ended_once ON gate.department_lead
        FOR UPDATE TO brain_app
        USING (ended_at IS NULL)
        WITH CHECK (ended_at IS NOT NULL)
    """,
    "ALTER TABLE gate.elevation_request ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY elevation_request_readable ON gate.elevation_request
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY elevation_request_pending ON gate.elevation_request
        FOR INSERT TO brain_app
        WITH CHECK (decision IS NULL AND grant_id IS NULL)
    """,
    """
    CREATE POLICY elevation_request_decided_once ON gate.elevation_request
        FOR UPDATE TO brain_app
        USING (decision IS NULL)
        WITH CHECK (decision IS NOT NULL)
    """,
)

#: SELECT and INSERT, UPDATE on the ending or deciding columns alone, and never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON gate.team_membership TO brain_app",
    "GRANT UPDATE (ended_at, ended_by) ON gate.team_membership TO brain_app",
    "GRANT SELECT, INSERT ON gate.department_lead TO brain_app",
    "GRANT UPDATE (ended_at, ended_by) ON gate.department_lead TO brain_app",
    "GRANT SELECT, INSERT ON gate.elevation_request TO brain_app",
    (
        "GRANT UPDATE (decision, decided_by, decided_at, grant_id, lapses_at) "
        "ON gate.elevation_request TO brain_app"
    ),
)

#: The append, as `0003`'s `gate.record_entitlement_change` and every trigger since write it, over
#: one change at a time. `{action}` is the ledger member; the loop's arrays are the function's own.
_APPEND = """
    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := v_where || jsonb_build_object('change', v_changes[i]);
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
            v_seq, v_at, v_actors[i], '{action}', v_subject, v_ent_hash,
            v_trace, v_details, v_prev
        );

        MERGE INTO obs.audit_entry AS t
        USING (SELECT v_seq AS seq) AS s
           ON t.seq = s.seq
        WHEN NOT MATCHED THEN
            INSERT (seq, at, actor_id, action, subject, ent_hash, trace_id,
                    details, prev_hash, entry_hash)
            VALUES (v_seq, v_at, v_actors[i], '{action}', v_subject,
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
"""

#: One trigger function: the declarations, where the change was, which changes and by whom, and the
#: append. Filled by `_trigger_function` with `str.replace`, so no SQL is built by concatenation.
_TRIGGER_TEMPLATE = """
CREATE FUNCTION __NAME__() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'principal:' || NEW.principal_id;
    v_changes text[] := ARRAY[]::text[];
    v_actors text[] := ARRAY[]::text[];
    v_where jsonb;
    v_details jsonb;
    v_seq bigint;
    v_prev text;
    v_entry text;
    v_at timestamptz := now();
    v_ent_hash text;
    v_trace text;
    v_written integer;
BEGIN
    v_where := __WHERE__;
__CHANGES__
__APPEND__END;
$$
"""


def _trigger_function(name: str, where: str, changes: str, action: str) -> str:
    return (
        _TRIGGER_TEMPLATE.replace("__NAME__", name)
        .replace("__WHERE__", where)
        .replace("__CHANGES__", changes)
        .replace("__APPEND__", _APPEND.replace("{action}", action))
    )


#: A person placed in a team, then taken out, each with the actor its own column names.
TEAM_MEMBERSHIP_TRIGGER_FUNCTION = _trigger_function(
    "gate.record_team_membership",
    """jsonb_build_object(
        'team',
        COALESCE(
            (SELECT d.slug || '.' || t.slug FROM gate.team t
               JOIN gate.department d ON d.id = t.department_id
              WHERE t.id = NEW.team_id),
            'unknown'
        )
    )""",
    """    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'joined'::text;
        v_actors := v_actors || NEW.added_by::text;
        IF NEW.ended_at IS NOT NULL THEN
            v_changes := v_changes || 'left'::text;
            v_actors := v_actors || NEW.ended_by::text;
        END IF;
    ELSIF OLD.ended_at IS NULL AND NEW.ended_at IS NOT NULL THEN
        v_changes := v_changes || 'left'::text;
        v_actors := v_actors || NEW.ended_by::text;
    END IF;""",
    "organisation",
)

TEAM_MEMBERSHIP_TRIGGER = """
CREATE TRIGGER team_membership_is_audited
    AFTER INSERT OR UPDATE ON gate.team_membership
    FOR EACH ROW EXECUTE FUNCTION gate.record_team_membership()
"""

#: A lead appointed, then stood down, each with the actor its own column names.
DEPARTMENT_LEAD_TRIGGER_FUNCTION = _trigger_function(
    "gate.record_department_lead",
    """jsonb_build_object(
        'department',
        COALESCE(
            (SELECT d.slug FROM gate.department d WHERE d.id = NEW.department_id),
            'unknown'
        )
    )""",
    """    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'appointed'::text;
        v_actors := v_actors || NEW.appointed_by::text;
        IF NEW.ended_at IS NOT NULL THEN
            v_changes := v_changes || 'stood_down'::text;
            v_actors := v_actors || NEW.ended_by::text;
        END IF;
    ELSIF OLD.ended_at IS NULL AND NEW.ended_at IS NOT NULL THEN
        v_changes := v_changes || 'stood_down'::text;
        v_actors := v_actors || NEW.ended_by::text;
    END IF;""",
    "organisation",
)

DEPARTMENT_LEAD_TRIGGER = """
CREATE TRIGGER department_lead_is_audited
    AFTER INSERT OR UPDATE ON gate.department_lead
    FOR EACH ROW EXECUTE FUNCTION gate.record_department_lead()
"""

#: A request, then its decision: the requester's, then the decider's.
ELEVATION_REQUEST_TRIGGER_FUNCTION = _trigger_function(
    "gate.record_elevation_request",
    "jsonb_build_object('capability', NEW.capability, 'reason', NEW.reason)",
    """    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'requested'::text;
        v_actors := v_actors || NEW.principal_id::text;
        IF NEW.decision IS NOT NULL THEN
            v_changes := v_changes || NEW.decision::text;
            v_actors := v_actors || NEW.decided_by::text;
        END IF;
    ELSIF OLD.decision IS NULL AND NEW.decision IS NOT NULL THEN
        v_changes := v_changes || NEW.decision::text;
        v_actors := v_actors || NEW.decided_by::text;
    END IF;""",
    "elevation",
)

ELEVATION_REQUEST_TRIGGER = """
CREATE TRIGGER elevation_request_is_audited
    AFTER INSERT OR UPDATE ON gate.elevation_request
    FOR EACH ROW EXECUTE FUNCTION gate.record_elevation_request()
"""


def _placement_columns(where: str, target: str, actor: str) -> list[Any]:
    return [
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            where,
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(target, ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "principal_id",
            sa.String(PRINCIPAL_ID_CHARS),
            sa.ForeignKey("auth.principal.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(f"{actor}_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            f"{actor}_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"{actor}_by ~ '{IDENTIFIER}'", name=f"{actor}_by_shape"),
        sa.CheckConstraint(f"ended_by IS NULL OR ended_by ~ '{IDENTIFIER}'", name="ended_by_shape"),
        sa.CheckConstraint(
            "(ended_at IS NULL) = (ended_by IS NULL)", name="an_ending_names_who_and_when"
        ),
    ]


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "team_membership",
        *_placement_columns("team_id", "gate.team.id", "added"),
        schema="gate",
    )
    op.create_index(
        "ix_gate_team_membership_team_id", "team_membership", ["team_id"], schema="gate"
    )
    op.create_index(
        "ix_gate_team_membership_principal_id", "team_membership", ["principal_id"], schema="gate"
    )
    op.create_index(
        "uq_team_membership_team_id_principal_id_live",
        "team_membership",
        ["team_id", "principal_id"],
        unique=True,
        schema="gate",
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "department_lead",
        *_placement_columns("department_id", "gate.department.id", "appointed"),
        schema="gate",
    )
    op.create_index(
        "ix_gate_department_lead_department_id", "department_lead", ["department_id"], schema="gate"
    )
    op.create_index(
        "ix_gate_department_lead_principal_id", "department_lead", ["principal_id"], schema="gate"
    )
    op.create_index(
        "uq_department_lead_department_id_live",
        "department_lead",
        ["department_id"],
        unique=True,
        schema="gate",
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "elevation_request",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "principal_id",
            sa.String(PRINCIPAL_ID_CHARS),
            sa.ForeignKey("auth.principal.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("capability", sa.String(CAPABILITY_CHARS), nullable=False),
        sa.Column("scope_slug", sa.String(SLUG_CHARS), nullable=False),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("hours", sa.SmallInteger(), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decision", sa.String(DECISION_CHARS), nullable=True),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "grant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("gate.capability_grant.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("lapses_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"capability ~ '{CAPABILITY_PATTERN}'", name="capability_grammar"),
        sa.CheckConstraint(CAPABILITY_VERBS, name="capability_verb"),
        sa.CheckConstraint(f"scope_slug ~ '{SLUG_SQL_PATTERN}'", name="scope_slug_grammar"),
        sa.CheckConstraint(REASONS, name="reason"),
        sa.CheckConstraint(
            f"length(btrim(explanation)) > 0 AND length(explanation) <= {EXPLANATION_CHARS}",
            name="explained",
        ),
        sa.CheckConstraint(f"hours BETWEEN 1 AND {LONGEST_HOURS}", name="hours_within_the_bound"),
        sa.CheckConstraint(DECISIONS, name="decision"),
        sa.CheckConstraint(
            "(decision IS NULL) = (decided_by IS NULL) "
            "AND (decision IS NULL) = (decided_at IS NULL)",
            name="a_decision_names_who_and_when",
        ),
        sa.CheckConstraint(
            f"decided_by IS NULL OR decided_by ~ '{IDENTIFIER}'", name="decider_shape"
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> principal_id", name="not_decided_by_its_requester"
        ),
        sa.CheckConstraint(
            "(decision IS NOT DISTINCT FROM 'approved') = (grant_id IS NOT NULL)",
            name="an_approval_and_only_an_approval_names_its_grant",
        ),
        sa.CheckConstraint("(grant_id IS NULL) = (lapses_at IS NULL)", name="a_grant_lapses"),
        sa.CheckConstraint(
            "lapses_at IS NULL OR lapses_at <= decided_at + make_interval(hours => hours::int)",
            name="no_longer_than_asked",
        ),
        schema="gate",
    )
    op.create_index(
        "ix_gate_elevation_request_principal_id",
        "elevation_request",
        ["principal_id"],
        schema="gate",
    )

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", WIDENED_ACTIONS, schema="obs")
    op.execute(TEAM_MEMBERSHIP_TRIGGER_FUNCTION)
    op.execute(TEAM_MEMBERSHIP_TRIGGER)
    op.execute(DEPARTMENT_LEAD_TRIGGER_FUNCTION)
    op.execute(DEPARTMENT_LEAD_TRIGGER)
    op.execute(ELEVATION_REQUEST_TRIGGER_FUNCTION)
    op.execute(ELEVATION_REQUEST_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER elevation_request_is_audited ON gate.elevation_request")
    op.execute("DROP FUNCTION gate.record_elevation_request()")
    op.execute("DROP TRIGGER department_lead_is_audited ON gate.department_lead")
    op.execute("DROP FUNCTION gate.record_department_lead()")
    op.execute("DROP TRIGGER team_membership_is_audited ON gate.team_membership")
    op.execute("DROP FUNCTION gate.record_team_membership()")
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint("action", "audit_entry", NARROWER_ACTIONS, schema="obs")
    # The policies and the grants go with the tables.
    op.drop_index("ix_gate_elevation_request_principal_id", "elevation_request", schema="gate")
    op.drop_table("elevation_request", schema="gate")
    op.drop_index("uq_department_lead_department_id_live", "department_lead", schema="gate")
    op.drop_index("ix_gate_department_lead_principal_id", "department_lead", schema="gate")
    op.drop_index("ix_gate_department_lead_department_id", "department_lead", schema="gate")
    op.drop_table("department_lead", schema="gate")
    op.drop_index("uq_team_membership_team_id_principal_id_live", "team_membership", schema="gate")
    op.drop_index("ix_gate_team_membership_principal_id", "team_membership", schema="gate")
    op.drop_index("ix_gate_team_membership_team_id", "team_membership", schema="gate")
    op.drop_table("team_membership", schema="gate")
