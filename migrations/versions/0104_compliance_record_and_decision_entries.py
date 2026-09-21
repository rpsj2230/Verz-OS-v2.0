"""Five decisions nothing recorded now write their ledger entries, and compliance gets two tables.

`brain.audit.record` has had a method for a deny, a leash change, a merge, a publish and a
break-glass since `0002`, and nothing called them: on the owner's install only grants, routing,
sign-ins and settings had ever been recorded (docs/tracker-audit-2026-09-17.md, M24.1.3). Each is
wired here where the decision lands in the database, so the entry commits with the decision or not
at all, which is `0050`'s argument for a trigger over a route:

- **break-glass**: an elevation request approved. `0062` records it as `elevation`, which answers
  "who asked for what"; this appends the `break_glass` entry for the session it opens, under
  `session:<request id>`, with the decider as actor and `AuditRecorder.break_glass`'s details.
- **entity merge**: `er.canonical.merged_into` going from empty to set, as the two entries
  `AuditRecorder.entity_merge` writes, one per side, so the id that disappeared is findable.
- **leash change**: `guardrails.leash` in `agent.template_instance.effective_document` moving,
  one entry per target whose rungs moved, with the highest rung before and after. The leash is a
  sealed path, so only an upgrade moves it; an install is the first leash and is not a change.
- **publish**: a template version arriving in `agent.template_version`, which is the published,
  signed body every install of that template pins; `0053` records the other publish, an export.
- **deny**: `gate.record_denial`, one narrow function the records route calls for a refusal it
  decided (`brain.ops.denial_store`). A deny writes no row of its own, so there is no table for a
  trigger to sit on, and a table kept only to fire one would be a second copy of the ledger.

Where the application names no actor (`brain.actor_id` unset), the entry says `unattributed` in
its actor and its details, never refused, for `0095b`'s reason.

**`breach` is a new ledger member and subject kind, and `ops.breach_case` is new** (M24.2.4). A
suspected breach is opened with its awareness, assessed, notified and closed on the Compliance
screen; the columns are `brain.audit.compliance.BreachCase`'s, references and enumerated values
only, never what happened. The trigger appends one `breach` entry per column that goes from empty
to set, and a re-assessment, by the row's `updated_by`, which the policies pin to the session.

**`ops.sensitive_referral` is new** (M24.2.2): who asked, when, the topic and the named person,
never the question. Read only by the person it is routed to, or, while nobody was named when it
arrived, by whoever is named for its topic now; the count a data protection officer sees comes
through `ops.sensitive_referral_tally`, which returns counts per topic and month and no row.

**The append is `0003`'s block once more**, for the reason `0047` gives against editing a function
every grant in production goes through.

**The downgrade** drops what this adds and puts `0095b`'s action list and `0086`'s subject grammar
back `NOT VALID`, for `0026`'s reason: an entry already recorded stays.

Task ids: M24.1.3, M24.2.2, M24.2.4

Revision ID: 0104
Revises: 0101
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0104"
down_revision = "0102"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.breach_case", "ops.sensitive_referral")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.compliance` by `tests/unit/test_tables.py`'s model comparison.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
PRINCIPAL_ID_CHARS = 128

#: `brain.audit.compliance`'s enums, sorted as `one_of` sorts.
BASIS_IN = "awareness_basis IN ('estimated', 'observed')"
SOURCE_IN = (
    "awareness_source IN ('data_intermediary_notice', 'internal_detection', 'regulator_notice', "
    "'staff_report', 'third_party_report')"
)
GROUND_IN = (
    "exception_ground IS NULL OR exception_ground IN ('commission_direction', 'remedial_action', "
    "'technological_protection')"
)
TOPIC_IN = (
    "topic IN ('grievance', 'harassment', 'hr_personal', 'legal', 'medical', 'salary', "
    "'whistleblowing')"
)

#: Alphabetical, matching how `tables.identity.one_of` sorts. The second is `0095b`'s.
WIDENED_ACTIONS = (
    "action IN ('approval', 'breach', 'break_glass', 'certification', 'compose_change', "
    "'connector', 'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', "
    "'instructions', 'leash_change', 'legal_hold', 'memory', 'organisation', 'principal_state', "
    "'publish', 'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', "
    "'sign_in', 'skill', 'vault_access', 'webhook')"
)
NARROWER_ACTIONS = (
    "action IN ('approval', 'break_glass', 'certification', 'compose_change', 'connector', "
    "'credential', 'deny', 'elevation', 'entity_merge', 'erasure', 'grant', 'instructions', "
    "'leash_change', 'legal_hold', 'memory', 'organisation', 'principal_state', 'publish', "
    "'record_read', 'retention', 'revoke', 'routing', 'session_end', 'setting', 'sign_in', "
    "'skill', 'vault_access', 'webhook')"
)

#: `brain.tables.audit.SUBJECT_PATTERN`, sorted, after and before. The second is `0086`'s.
WIDENED_SUBJECTS = (
    "subject ~ '^(agent|artifact|breach|connector|credential|department|entity|erasure|grant"
    "|leash|legal_hold|memory|principal|retention|routing|scope|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)
NARROWER_SUBJECTS = (
    "subject ~ '^(agent|artifact|connector|credential|department|entity|erasure|grant|leash"
    "|legal_hold|memory|principal|retention|routing|scope|session|setting|skill|webhook)"
    ":[A-Za-z0-9_.@-]{1,128}$'"
)

#: What this migration replaces: `0095b`'s action list and `0086`'s subject grammar.
SUPERSEDES: dict[str, str] = {
    NARROWER_ACTIONS: WIDENED_ACTIONS,
    NARROWER_SUBJECTS: WIDENED_SUBJECTS,
}

PRINCIPAL = "current_setting('app.principal_id', true)"

#: Whether a referral is readable by this session: routed to them, or routed to nobody and they are
#: named for its topic now. The named person is `ops.setting`'s `sensitive_route.<topic>`, a JSON
#: string, which is where `brain.ops.sensitive_referral_store` writes it.
VISIBLE_REFERRAL = """(
            routed_to = current_setting('app.principal_id', true)
            OR (
                routed_to IS NULL
                AND EXISTS (
                    SELECT 1 FROM ops.setting s
                     WHERE s.key = 'sensitive_route.' || topic
                       AND s.deleted_at IS NULL
                       AND s.value #>> '{}' = current_setting('app.principal_id', true)
                )
            )
        )"""

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.breach_case ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY breach_case_readable ON ops.breach_case
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY breach_case_opened_in_the_sessions_name ON ops.breach_case
        FOR INSERT TO brain_app
        WITH CHECK (recorded_by = {PRINCIPAL} AND updated_by = {PRINCIPAL} AND closed_at IS NULL)
    """,
    f"""
    CREATE POLICY breach_case_moved_while_open ON ops.breach_case
        FOR UPDATE TO brain_app
        USING (closed_at IS NULL)
        WITH CHECK (updated_by = {PRINCIPAL})
    """,
    "ALTER TABLE ops.sensitive_referral ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY sensitive_referral_read_by_its_person ON ops.sensitive_referral
        FOR SELECT TO brain_app
        USING {VISIBLE_REFERRAL}
    """,
    f"""
    CREATE POLICY sensitive_referral_filed_by_the_asker ON ops.sensitive_referral
        FOR INSERT TO brain_app
        WITH CHECK (asked_by = {PRINCIPAL} AND handled_at IS NULL)
    """,
    f"""
    CREATE POLICY sensitive_referral_handled_by_its_person ON ops.sensitive_referral
        FOR UPDATE TO brain_app
        USING {VISIBLE_REFERRAL}
        WITH CHECK (routed_to = {PRINCIPAL} AND handled_by = {PRINCIPAL})
    """,
)

#: SELECT, INSERT and UPDATE, and never DELETE: a case and a referral are records.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON ops.breach_case TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON ops.sensitive_referral TO brain_app",
)

#: The append, as `0003` and `0060` write it. `{actor}`, `{action}`, `{subject}` and `{details}`
#: are the four expressions that differ.
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

#: An elevation approved opens a break-glass session: its entry, by the decider.
BREAK_GLASS_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION gate.record_break_glass() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF NEW.decision IS DISTINCT FROM 'approved' THEN
        RETURN NULL;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.decision IS NOT DISTINCT FROM 'approved' THEN
        RETURN NULL;
    END IF;
    v_details := jsonb_build_object(
        'reason', NEW.reason, 'principal', NEW.principal_id, 'authorised_by', NEW.decided_by
    );"""
    + _APPEND.format(
        actor="NEW.decided_by",
        action="break_glass",
        subject="'session:' || NEW.id::text",
        details="v_details",
    )
    + """    RETURN NULL;
END;
$$
"""
)

BREAK_GLASS_TRIGGER = """
CREATE TRIGGER elevation_request_opens_break_glass
    AFTER INSERT OR UPDATE OF decision ON gate.elevation_request
    FOR EACH ROW EXECUTE FUNCTION gate.record_break_glass()
"""

#: A canonical entity merged into another: one entry for each side, kept first.
ENTITY_MERGE_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION er.record_entity_merge() RETURNS trigger
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

ENTITY_MERGE_TRIGGER = """
CREATE TRIGGER canonical_merge_is_audited
    AFTER UPDATE OF merged_into ON er.canonical
    FOR EACH ROW EXECUTE FUNCTION er.record_entity_merge()
"""

#: The rung names `AuditRecorder.leash_change` records, by `AutonomyTier` value. A target with no
#: entry is held at Shadow, which is `brain.gate.leash.MISSING_ENTRY_RUNG`.
LEASH_CHANGE_TRIGGER_FUNCTION = "".join(
    (
        """
CREATE FUNCTION agent.record_leash_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text;
    v_marked boolean := false;
    v_old jsonb := COALESCE(OLD.effective_document -> 'guardrails.leash', '[]'::jsonb);
    v_new jsonb := COALESCE(NEW.effective_document -> 'guardrails.leash', '[]'::jsonb);
    v_names text[] := ARRAY['shadow', 'assisted', 'autonomous'];
    v_target text;
    v_from integer;
    v_to integer;
    v_details jsonb;""",
        _DECLARE,
        """BEGIN
    IF v_old = v_new THEN
        RETURN NULL;
    END IF;""",
        _ACTOR,
        """    FOR v_target IN
        SELECT DISTINCT e ->> 'target' FROM (
            SELECT jsonb_array_elements(v_old) AS e
            UNION ALL
            SELECT jsonb_array_elements(v_new)
        ) AS both_sides
        ORDER BY 1
    LOOP
        IF (SELECT COALESCE(jsonb_agg(e ORDER BY e::text), '[]'::jsonb)
              FROM jsonb_array_elements(v_old) e WHERE e ->> 'target' = v_target)
           = (SELECT COALESCE(jsonb_agg(e ORDER BY e::text), '[]'::jsonb)
              FROM jsonb_array_elements(v_new) e WHERE e ->> 'target' = v_target) THEN
            CONTINUE;
        END IF;
        SELECT COALESCE(max((e ->> 'rung')::integer), 0) INTO v_from
          FROM jsonb_array_elements(v_old) e WHERE e ->> 'target' = v_target;
        SELECT COALESCE(max((e ->> 'rung')::integer), 0) INTO v_to
          FROM jsonb_array_elements(v_new) e WHERE e ->> 'target' = v_target;
        v_details := jsonb_build_object(
            'target', v_target, 'from_rung', v_names[v_from + 1], 'to_rung', v_names[v_to + 1]
        );
        IF v_marked THEN
            v_details := v_details || jsonb_build_object('actor', 'unattributed');
        END IF;""",
        _APPEND.format(
            actor="v_actor",
            action="leash_change",
            subject="'agent:' || NEW.id",
            details="v_details",
        ),
        """    END LOOP;
    RETURN NULL;
END;
$$
""",
    )
)

LEASH_CHANGE_TRIGGER = """
CREATE TRIGGER template_instance_leash_is_audited
    AFTER UPDATE OF effective_document ON agent.template_instance
    FOR EACH ROW EXECUTE FUNCTION agent.record_leash_change()
"""

#: A template version published into this install: `artifact:<template>.v<version>`.
PUBLISH_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_template_publish() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text;
    v_marked boolean := false;
    v_details jsonb := '{}'::jsonb;"""
    + _DECLARE
    + """BEGIN"""
    + _ACTOR
    + """    IF v_marked THEN
        v_actor := NEW.signed_by;
    END IF;"""
    + _APPEND.format(
        actor="v_actor",
        action="publish",
        subject="'artifact:' || NEW.template_id || '.v' || NEW.version::text",
        details="v_details",
    )
    + """    RETURN NULL;
END;
$$
"""
)

PUBLISH_TRIGGER = """
CREATE TRIGGER template_version_publish_is_audited
    AFTER INSERT ON agent.template_version
    FOR EACH ROW EXECUTE FUNCTION agent.record_template_publish()
"""

#: `brain.audit.record.DenyReason`, sorted.
DENY_REASONS = "('leash_refused', 'no_grant', 'out_of_scope', 'principal_expired', 'risk_ceiling')"

#: A refusal the application decided, appended in the caller's transaction. Narrow on purpose: the
#: action is fixed, the reason is `DenyReason`'s and the capability has the capability grammar, so
#: this is not the general `record(action, details)` `brain.audit.record` refuses to have.
DENIAL_FUNCTION = (
    """
CREATE FUNCTION gate.record_denial(
    p_subject text, p_capability text, p_reason text
) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_actor text;
    v_marked boolean := false;
    v_details jsonb;"""
    + _DECLARE
    + f"""BEGIN
    IF p_reason NOT IN {DENY_REASONS} THEN
        RAISE EXCEPTION 'a deny reason is one of DenyReason, not %', p_reason
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_capability !~ '^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*|\\.\\*)*$' THEN
        RAISE EXCEPTION 'a deny names a capability' USING ERRCODE = 'check_violation';
    END IF;"""
    + _ACTOR
    + """    v_details := jsonb_build_object('capability', p_capability, 'reason', p_reason);
    IF v_marked THEN
        v_details := v_details || jsonb_build_object('actor', 'unattributed');
    END IF;"""
    + _APPEND.format(actor="v_actor", action="deny", subject="p_subject", details="v_details")
    + """END;
$$
"""
)

#: One entry per column of a case that goes from empty to set, in the order a case moves, and one
#: for a re-assessment. The actor is the row's `updated_by`, or on an insert its `recorded_by`.
BREACH_CASE_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION ops.record_breach_case() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'breach:' || NEW.case_id::text;
    v_changes text[] := ARRAY[]::text[];
    v_actor text;
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changes := v_changes || 'opened'::text;
        v_actor := NEW.recorded_by;
        IF NEW.assessed_at IS NOT NULL THEN
            v_changes := v_changes || 'assessed'::text;
        END IF;
        IF NEW.commission_notified_at IS NOT NULL THEN
            v_changes := v_changes || 'commission_notified'::text;
        END IF;
        IF NEW.individuals_notified_at IS NOT NULL THEN
            v_changes := v_changes || 'individuals_notified'::text;
        END IF;
        IF NEW.exception_ground IS NOT NULL THEN
            v_changes := v_changes || 'individuals_excused'::text;
        END IF;
        IF NEW.closed_at IS NOT NULL THEN
            v_changes := v_changes || 'closed'::text;
        END IF;
    ELSE
        v_actor := NEW.updated_by;
        IF NEW.assessed_at IS NOT NULL
           AND (OLD.assessed_at IS DISTINCT FROM NEW.assessed_at
                OR OLD.significant_harm IS DISTINCT FROM NEW.significant_harm
                OR OLD.affected_count IS DISTINCT FROM NEW.affected_count) THEN
            v_changes := v_changes || 'assessed'::text;
        END IF;
        IF OLD.commission_notified_at IS NULL AND NEW.commission_notified_at IS NOT NULL THEN
            v_changes := v_changes || 'commission_notified'::text;
        END IF;
        IF OLD.individuals_notified_at IS NULL AND NEW.individuals_notified_at IS NOT NULL THEN
            v_changes := v_changes || 'individuals_notified'::text;
        END IF;
        IF OLD.exception_ground IS NULL AND NEW.exception_ground IS NOT NULL THEN
            v_changes := v_changes || 'individuals_excused'::text;
        END IF;
        IF OLD.closed_at IS NULL AND NEW.closed_at IS NOT NULL THEN
            v_changes := v_changes || 'closed'::text;
        END IF;
    END IF;

    FOR i IN 1 .. COALESCE(array_length(v_changes, 1), 0) LOOP
        v_details := jsonb_build_object('change', v_changes[i]);"""
    + _APPEND.format(actor="v_actor", action="breach", subject="v_subject", details="v_details")
    + """    END LOOP;
    RETURN NULL;
END;
$$
"""
)

BREACH_CASE_TRIGGER = """
CREATE TRIGGER breach_case_is_audited
    AFTER INSERT OR UPDATE ON ops.breach_case
    FOR EACH ROW EXECUTE FUNCTION ops.record_breach_case()
"""

#: Counts per topic in one calendar month, and no row. Security definer so it can count what the
#: caller may not read; `brain.audit.compliance.InterceptionTally.report` suppresses the result.
TALLY_FUNCTION = """
CREATE FUNCTION ops.sensitive_referral_tally(p_period text)
RETURNS TABLE (topic text, referrals bigint)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, ops
AS $$
    SELECT r.topic::text, count(*)
      FROM ops.sensitive_referral r
     WHERE to_char(r.asked_at AT TIME ZONE 'UTC', 'YYYY-MM') = p_period
     GROUP BY r.topic
$$
"""

#: Granted to the application by name. Not revoked from PUBLIC: `brain.deployment.compatibility`
#: reads a revocation as a statement that removes something, and what the function returns is
#: counts per topic and month, the aggregate the screen shows once suppressed.
FUNCTION_GRANTS: tuple[str, ...] = (
    "GRANT EXECUTE ON FUNCTION ops.sensitive_referral_tally(text) TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "breach_case",
        sa.Column(
            "case_id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("became_aware_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("awareness_basis", sa.String(16), nullable=False),
        sa.Column("awareness_source", sa.String(32), nullable=False),
        sa.Column("earliest_possible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("evidence_reference", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("significant_harm", sa.Boolean(), nullable=True),
        sa.Column("harm_decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("harm_rationale_reference", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("affected_count", sa.Integer(), nullable=True),
        sa.Column("commission_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("individuals_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exception_ground", sa.String(32), nullable=True),
        sa.Column("exception_decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("exception_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exception_rationale_reference", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("updated_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.CheckConstraint(BASIS_IN, name="awareness_basis"),
        sa.CheckConstraint(SOURCE_IN, name="awareness_source"),
        sa.CheckConstraint(GROUND_IN, name="exception_ground"),
        sa.CheckConstraint(f"recorded_by ~ '{IDENTIFIER}'", name="recorded_by_is_an_identifier"),
        sa.CheckConstraint(f"updated_by ~ '{IDENTIFIER}'", name="updated_by_is_an_identifier"),
        sa.CheckConstraint(f"evidence_reference ~ '{IDENTIFIER}'", name="evidence_is_a_reference"),
        sa.CheckConstraint(
            f"harm_decided_by IS NULL OR harm_decided_by ~ '{IDENTIFIER}'",
            name="harm_decided_by_is_an_identifier",
        ),
        sa.CheckConstraint(
            f"harm_rationale_reference IS NULL OR harm_rationale_reference ~ '{IDENTIFIER}'",
            name="harm_rationale_is_a_reference",
        ),
        sa.CheckConstraint(
            f"exception_decided_by IS NULL OR exception_decided_by ~ '{IDENTIFIER}'",
            name="exception_decided_by_is_an_identifier",
        ),
        sa.CheckConstraint(
            "exception_rationale_reference IS NULL OR exception_rationale_reference ~ "
            f"'{IDENTIFIER}'",
            name="exception_rationale_is_a_reference",
        ),
        sa.CheckConstraint(
            f"closed_by IS NULL OR closed_by ~ '{IDENTIFIER}'", name="closed_by_is_an_identifier"
        ),
        sa.CheckConstraint(
            "(awareness_basis = 'estimated') = (earliest_possible_at IS NOT NULL)",
            name="an_estimate_records_its_earliest",
        ),
        sa.CheckConstraint(
            "earliest_possible_at IS NULL OR earliest_possible_at <= became_aware_at",
            name="earliest_is_not_after_the_estimate",
        ),
        sa.CheckConstraint("recorded_at >= became_aware_at", name="recorded_after_it_was_known"),
        sa.CheckConstraint(
            "(assessed_at IS NULL) = (significant_harm IS NULL) "
            "AND (assessed_at IS NULL) = (harm_decided_by IS NULL) "
            "AND (assessed_at IS NULL) = (harm_rationale_reference IS NULL)",
            name="assessed_whole",
        ),
        sa.CheckConstraint(
            "affected_count IS NULL OR affected_count >= 0", name="affected_count_not_negative"
        ),
        sa.CheckConstraint(
            "(exception_ground IS NULL) = (exception_decided_by IS NULL) "
            "AND (exception_ground IS NULL) = (exception_decided_at IS NULL) "
            "AND (exception_ground IS NULL) = (exception_rationale_reference IS NULL)",
            name="excused_whole",
        ),
        sa.CheckConstraint("(closed_at IS NULL) = (closed_by IS NULL)", name="closed_whole"),
        sa.CheckConstraint(
            "closed_at IS NULL OR assessed_at IS NOT NULL", name="closed_only_once_assessed"
        ),
        schema="ops",
    )
    op.create_index(
        "ix_breach_case_became_aware_at", "breach_case", ["became_aware_at"], schema="ops"
    )
    op.create_table(
        "sensitive_referral",
        sa.Column("referral_id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("asked_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "asked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("routed_to", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.CheckConstraint(TOPIC_IN, name="topic"),
        sa.CheckConstraint(f"asked_by ~ '{IDENTIFIER}'", name="asked_by_is_an_identifier"),
        sa.CheckConstraint(
            f"routed_to IS NULL OR routed_to ~ '{IDENTIFIER}'", name="routed_to_is_an_identifier"
        ),
        sa.CheckConstraint(
            f"handled_by IS NULL OR handled_by ~ '{IDENTIFIER}'",
            name="handled_by_is_an_identifier",
        ),
        sa.CheckConstraint("(handled_at IS NULL) = (handled_by IS NULL)", name="handled_whole"),
        schema="ops",
    )
    op.create_index(
        "ix_sensitive_referral_routed_to", "sensitive_referral", ["routed_to"], schema="ops"
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

    for function, trigger in (
        (BREAK_GLASS_TRIGGER_FUNCTION, BREAK_GLASS_TRIGGER),
        (ENTITY_MERGE_TRIGGER_FUNCTION, ENTITY_MERGE_TRIGGER),
        (LEASH_CHANGE_TRIGGER_FUNCTION, LEASH_CHANGE_TRIGGER),
        (PUBLISH_TRIGGER_FUNCTION, PUBLISH_TRIGGER),
        (BREACH_CASE_TRIGGER_FUNCTION, BREACH_CASE_TRIGGER),
    ):
        op.execute(function)
        op.execute(trigger)
    op.execute(DENIAL_FUNCTION)
    op.execute(TALLY_FUNCTION)
    for statement in FUNCTION_GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP FUNCTION ops.sensitive_referral_tally(text)")
    op.execute("DROP FUNCTION gate.record_denial(text, text, text)")
    for trigger, table, function in (
        ("breach_case_is_audited", "ops.breach_case", "ops.record_breach_case"),
        (
            "template_version_publish_is_audited",
            "agent.template_version",
            "agent.record_template_publish",
        ),
        (
            "template_instance_leash_is_audited",
            "agent.template_instance",
            "agent.record_leash_change",
        ),
        ("canonical_merge_is_audited", "er.canonical", "er.record_entity_merge"),
        (
            "elevation_request_opens_break_glass",
            "gate.elevation_request",
            "gate.record_break_glass",
        ),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
        op.execute(f"DROP FUNCTION {function}()")
    op.drop_constraint("subject_grammar", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "subject_grammar", "audit_entry", NARROWER_SUBJECTS, schema="obs", postgresql_not_valid=True
    )
    op.drop_constraint("action", "audit_entry", schema="obs", type_="check")
    op.create_check_constraint(
        "action", "audit_entry", NARROWER_ACTIONS, schema="obs", postgresql_not_valid=True
    )
    # The policies, the grants and the indexes go with the tables; their ledger entries stay.
    op.drop_table("sensitive_referral", schema="ops")
    op.drop_table("breach_case", schema="ops")
