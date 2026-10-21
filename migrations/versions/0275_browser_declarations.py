"""A person can declare the systems a browser may be pointed at, and sign what lets it do more.

`brain.browsing.targets` says a target is a declaration by a person who has an account on that
system, and until now nothing stored one: the registry was a value a test or a check built. This
adds the two tables that make it a thing an install holds (M19.2.4), and the signed permissions
`brain.browsing.autonomy` and `brain.browsing.skill_gate` describe and said had nowhere to be kept
(M19.7.3, M19.9.7, M19.6.7).

**`agent.browser_target`, one row per change.** The declaration is the document
`brain.browsing.declared` reads: origins, surfaces with their declared verbs, fields and controls,
the API tools that do the same work without a browser, and credential bindings by vault reference.
**A binding is a path and an origin and never a value**, and the path is held to the one mount the
browser runner's vault policy reads (`browser/creds/<name>`). The newest row for a name is its
state and a row may retire it, so a map edited after a run has a history and nothing is updated or
deleted. Written in the session's own name, as `0261` writes a withdrawal.

**`agent.browser_grant`, a signed permission with an end.** An `exception` lets one surface's
writes run without the envelope waiting for a person (`autonomy.SurfaceException`) and an
`exemption` lets one skill drive a target that has an API (`skill_gate.Exemption`). Each names who
signed it, why (at least the twelve characters `brain.ops.halt.MINIMUM_REASON` asks of a halt) and
when it ends, and **the database refuses one that runs longer than ninety days**, the same quarter
the two value types refuse, so the limit does not depend on which writer reached the table. The one
thing updated is that a grant was revoked, and the grant to the application is on those two columns
alone (a column-level `UPDATE`), so a signed reason, a surface or an end cannot be edited after
the fact.

**Both are in the ledger as a leash change, by the database.** An insert into
`agent.browser_grant` appends a `leash_change` entry about `connector:browser.<target>` in the same
transaction, naming the surface (or the skill) and the rung it moves between, and a revocation
appends the reverse, each as the person who did it. The recorder has no method for it, because
`ACTION_BY_METHOD` pins one method per action and `leash_change` has one about an agent; a test
holds the entries to the details written out beside the rungs. Rejected: a Python call after the
insert, which is an entry a crashed request never writes.

**A skill's hyphens are written as underscores in the entry.** The ledger keeps names, and a name is
lowercase letters, digits and underscores (`brain.audit.ledger.FIELD_NAME`); an entry whose detail
broke that would be refused when the chain is read back, which is the worst moment to find out.

**No foreign key to a person or to a target.** A person is a value, so a grant outlives whoever
signed it, and a grant may name a target a later row retired, because the question it answers is who
allowed what and when. The downgrade drops the tables and the functions; the ledger entries stay,
because nothing may delete one (`0056`).

Task ids: M19.2.4, M19.7.3, M19.9.7, M19.6.7

Revision ID: 0275
Revises: 0274
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0275"
# Written over 0274, the head of main when this was last checked; if another migration lands first
# it is re-pointed at that one, as every migration landed in a train is.
down_revision = "0274"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.browser_target", "agent.browser_grant")

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.browsing` by `tests/unit/test_browser_declarations.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
SLUG = r"^[a-z][a-z0-9_]*$"
PRINCIPAL_ID_CHARS = 128
TARGET_CHARS = 64
SKILL_CHARS = 80
REASON_CHARS = 240
MINIMUM_REASON_CHARS = 12
KIND_CHARS = 16

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.browser_target ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY browser_target_readable ON agent.browser_target
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY browser_target_set_in_the_sessions_name ON agent.browser_target
        FOR INSERT TO brain_app
        WITH CHECK (set_by = {PRINCIPAL})
    """,
    "ALTER TABLE agent.browser_grant ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY browser_grant_readable ON agent.browser_grant
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY browser_grant_signed_in_the_sessions_name ON agent.browser_grant
        FOR INSERT TO brain_app
        WITH CHECK (signed_by = {PRINCIPAL} AND revoked_at IS NULL)
    """,
    f"""
    CREATE POLICY browser_grant_revoked_once_in_the_sessions_name ON agent.browser_grant
        FOR UPDATE TO brain_app
        USING (revoked_at IS NULL)
        WITH CHECK (revoked_by = {PRINCIPAL})
    """,
)

#: A target is SELECT and INSERT. A grant is SELECT and INSERT, and an UPDATE of two columns only.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.browser_target TO brain_app",
    "GRANT SELECT, INSERT ON agent.browser_grant TO brain_app",
    "GRANT UPDATE (revoked_at, revoked_by) ON agent.browser_grant TO brain_app",
)

#: The append every trigger here makes, copied from `0261`, which copied `0139`, `0121`, `0056`
#: and `0003`.
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


#: A grant signed, or revoked: a leash change about the target it concerns.
BROWSER_GRANT_TRIGGER_FUNCTION = (
    """
CREATE FUNCTION agent.record_browser_grant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_subject text := 'connector:browser.' || NEW.target;
    v_actor text;
    v_what text := 'browser.' || NEW.target || '.' || replace(COALESCE(NEW.surface, NEW.skill), '-', '_');
    v_from text;
    v_to text;
    v_details jsonb;"""
    + _DECLARE
    + """BEGIN
    IF TG_OP = 'INSERT' THEN
        v_actor := NEW.signed_by;
        v_from := CASE NEW.kind WHEN 'exception' THEN 'assisted' ELSE 'refused' END;
        v_to := CASE NEW.kind WHEN 'exception' THEN 'autonomous' ELSE 'exempted' END;
    ELSE
        v_actor := NEW.revoked_by;
        v_from := CASE NEW.kind WHEN 'exception' THEN 'autonomous' ELSE 'exempted' END;
        v_to := CASE NEW.kind WHEN 'exception' THEN 'assisted' ELSE 'refused' END;
    END IF;
    v_details := jsonb_build_object('target', v_what, 'from_rung', v_from, 'to_rung', v_to);"""
    + _APPEND.format(
        actor="v_actor", action="leash_change", subject="v_subject", details="v_details"
    )
    + """    RETURN NULL;
END;
$$
"""
)

TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER browser_grant_is_audited
        AFTER INSERT ON agent.browser_grant
        FOR EACH ROW EXECUTE FUNCTION agent.record_browser_grant()
    """,
    """
    CREATE TRIGGER browser_grant_revocation_is_audited
        AFTER UPDATE OF revoked_at ON agent.browser_grant
        FOR EACH ROW WHEN (OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL)
        EXECUTE FUNCTION agent.record_browser_grant()
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert sum("UPDATE" in statement for statement in GRANTS) == 1

    op.create_table(
        "browser_target",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("name", sa.String(TARGET_CHARS), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("set_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"name ~ '{SLUG}'", name="name_is_a_slug"),
        sa.CheckConstraint("jsonb_typeof(definition) = 'object'", name="definition_is_an_object"),
        sa.CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        schema="agent",
    )
    op.create_index(
        "ix_agent_browser_target_name", "browser_target", ["name", "seq"], schema="agent"
    )
    op.create_table(
        "browser_grant",
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True, nullable=False
        ),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("target", sa.String(TARGET_CHARS), nullable=False),
        sa.Column("surface", sa.String(TARGET_CHARS), nullable=True),
        sa.Column("skill", sa.String(SKILL_CHARS), nullable=True),
        sa.Column("signed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.CheckConstraint("kind IN ('exception', 'exemption')", name="kind"),
        sa.CheckConstraint(f"target ~ '{SLUG}'", name="target_is_a_slug"),
        sa.CheckConstraint(
            "(kind = 'exception') = (surface IS NOT NULL) "
            "AND (kind = 'exemption') = (skill IS NOT NULL)",
            name="an_exception_names_a_surface_and_an_exemption_a_skill",
        ),
        sa.CheckConstraint(f"signed_by ~ '{IDENTIFIER}'", name="signed_by_is_an_identifier"),
        sa.CheckConstraint(
            f"length(btrim(reason)) >= {MINIMUM_REASON_CHARS}", name="a_reason_is_a_sentence"
        ),
        sa.CheckConstraint("expires_at > created_at", name="a_grant_ends_after_it_begins"),
        sa.CheckConstraint(
            "expires_at <= created_at + interval '90 days'", name="a_grant_runs_at_most_a_quarter"
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name="a_revocation_is_a_person_and_a_date",
        ),
        schema="agent",
    )
    op.create_index(
        "ix_agent_browser_grant_target", "browser_grant", ["target", "seq"], schema="agent"
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    op.execute(BROWSER_GRANT_TRIGGER_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER browser_grant_revocation_is_audited ON agent.browser_grant")
    op.execute("DROP TRIGGER browser_grant_is_audited ON agent.browser_grant")
    op.execute("DROP FUNCTION agent.record_browser_grant()")
    # The policies, the grants and the indexes go with the tables.
    op.drop_table("browser_grant", schema="agent")
    op.drop_table("browser_target", schema="agent")
