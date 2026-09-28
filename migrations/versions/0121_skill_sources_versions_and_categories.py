"""A skill comes from a commit or an address, an edit is a version, a self-approval says so, and
categories are kept.

`0056` built the skill library for one source, an upload, and for a second person deciding. The
Wave 2 skill package (M12.2.2, M12.2.3, M12.3.2, M12.4.6, M12.4.13) needs four things of the
tables, and `brain.tables.skill` holds the argument for each column; this is how they arrive.

**Three columns on `agent.skill`, each nullable and each carrying the checks that read it.** A
repository source's commit and folder, and the version an edit was edited from, held by a key to a
row that exists. Every check travels with the column it reads, as `0115`'s does, so it binds only
rows naming a column the previous release has never heard of: `brain.deployment.compatibility`'s
reason about a deploy that runs the new schema under the old code for as long as the swap takes.

**Two checks widened under the names `0056` gave them.** `source_is_an_upload` now admits the three
sources, and `nobody_decides_their_own_import` admits a decision by the importer when the row says
so in `self_decided`, a new column defaulting to false, with a check that only the importer's row
may say it. The names are kept because a check dropped and not recreated is a constraint no model
declares, which `tests/unit/test_tables.py` refuses for a reason worth keeping: a drop naming a
constraint that does not exist renders and drops nothing. So the names read as the rules they were,
with the exception each now admits written into the predicate. `SUPERSEDES` and
`AMENDS_CREATE_TABLE` bring `0056`'s CREATE TABLE up to what these leave behind, for the model
comparison.

**`agent.skill_category`, one row per change.** The newest row for a name is its categories.
SELECT and INSERT only, a select policy admitting every row because who may see the library is the
console's decision (`0056`'s shape), and an insert policy admitting a row set in the session's own
name. A trigger appends every change to the ledger.

**The two ledger triggers `0056` wrote are replaced, not added to.** An import records its source,
an edit records `edited` and the version it came from, and a decision by the importer records
`self_approved` or `self_rejected`, which is the word the audit screen's search finds (M12.4.6). A
second trigger beside each was rejected: two entries for one row is a ledger that disagrees with
itself about how many things happened.

**The downgrade** drops the category table and its trigger, puts `0056`'s two function bodies back,
narrows the two checks `NOT VALID` so rows already written stay, and drops the three columns and
`self_decided`, losing what they held, which is the only reversal a column addition has. A row
written from a repository or an address then fails to construct in the previous release and is
absent from its library, which `brain.ops.skill_store` already argues is the safe direction.

Task ids: M12.2.2, M12.2.3, M12.3.2, M12.4.6, M12.4.13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0121"
# The newest migration on origin/main when this was written.
down_revision = "0115"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.skill_category",)

APP_ROLE = "brain_app"

#: Grammars and widths copied for the reason `0009` gives about reading live code from a migration,
#: and held equal to `brain.tables.skill` by `tests/unit/test_skill_store.py`.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
DIGEST = r"^[0-9a-f]{64}$"
SKILL_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,79}$"
COMMIT_PATTERN = r"^[0-9a-f]{40}$"
PATH_PATTERN = r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$"
PRINCIPAL_ID_CHARS = 128
NAME_CHARS = 80
COMMIT_CHARS = 40
PATH_CHARS = 200
DIGEST_CHARS = 64
MAX_CATEGORIES = 8

#: `0056`'s source check, written as the list it always was, and the three it admits now.
SOURCE_BEFORE = "source_kind IN ('upload')"
SOURCE_AFTER = "source_kind IN ('github', 'upload', 'url')"

#: `0056`'s decider check, and the same rule with the importer's own row admitted when it says so.
DECIDER_BEFORE = "decided_by <> submitted_by"
DECIDER_AFTER = "self_decided OR submitted_by <> decided_by"

#: The checks each added column carries, as (name, predicate).
COMMIT_CHECKS: tuple[tuple[str, str], ...] = (
    ("source_commit_shape", f"source_commit IS NULL OR source_commit ~ '{COMMIT_PATTERN}'"),
    (
        "a_repository_source_names_its_commit",
        "(source_kind = 'github') = (source_commit IS NOT NULL)",
    ),
)
PATH_CHECK = (
    "source_path_on_a_repository_source",
    f"source_path IS NULL OR (source_kind = 'github' AND source_path ~ '{PATH_PATTERN}')",
)
EDITED_FROM_CHECK = (
    "edited_from_another_version",
    f"edited_from IS NULL OR (edited_from ~ '{DIGEST}' AND edited_from <> digest)",
)
SELF_DECIDED_CHECK = (
    "self_decided_only_by_the_importer",
    "NOT self_decided OR decided_by = submitted_by",
)
CATEGORY_LIST_CHECK = (
    "CASE WHEN jsonb_typeof(categories) = 'array' "
    f"THEN jsonb_array_length(categories) <= {MAX_CATEGORIES} ELSE false END"
)

#: `0056`'s two checks, rendered, and what this migration leaves in their place.
SUPERSEDES: dict[str, str] = {
    "CONSTRAINT ck_skill_source_is_an_upload CHECK (source_kind = 'upload')": (
        f"CONSTRAINT ck_skill_source_is_an_upload CHECK ({SOURCE_AFTER})"
    ),
    f"CONSTRAINT ck_skill_review_nobody_decides_their_own_import CHECK ({DECIDER_BEFORE})": (
        f"CONSTRAINT ck_skill_review_nobody_decides_their_own_import CHECK ({DECIDER_AFTER})"
    ),
}

#: `0056`'s two CREATE TABLEs as they would read today, for the comparison with the models. Held
#: to the ALTERs the upgrade emits by `tests/unit/test_skill_store.py`.
AMENDS_CREATE_TABLE: dict[str, str] = {
    "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, "
    "CONSTRAINT pk_skill PRIMARY KEY (digest),": (
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, "
        f"source_commit VARCHAR({COMMIT_CHARS}), source_path VARCHAR({PATH_CHARS}), "
        f"edited_from VARCHAR({DIGEST_CHARS}), CONSTRAINT pk_skill PRIMARY KEY (digest),"
    ),
    "CONSTRAINT uq_skill_digest_name UNIQUE (digest, name) )": (
        "CONSTRAINT uq_skill_digest_name UNIQUE (digest, name), "
        + "".join(f"CONSTRAINT ck_skill_{name} CHECK ({check}), " for name, check in COMMIT_CHECKS)
        + f"CONSTRAINT ck_skill_{PATH_CHECK[0]} CHECK ({PATH_CHECK[1]}), "
        f"CONSTRAINT ck_skill_{EDITED_FROM_CHECK[0]} CHECK ({EDITED_FROM_CHECK[1]}), "
        "CONSTRAINT fk_skill_edited_from_skill FOREIGN KEY(edited_from) "
        "REFERENCES agent.skill (digest) )"
    ),
    "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, "
    "CONSTRAINT pk_skill_review PRIMARY KEY (digest),": (
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, "
        "self_decided BOOLEAN DEFAULT false NOT NULL, "
        "CONSTRAINT pk_skill_review PRIMARY KEY (digest),"
    ),
    "REFERENCES agent.skill (digest, submitted_by) )": (
        "REFERENCES agent.skill (digest, submitted_by), "
        f"CONSTRAINT ck_skill_review_{SELF_DECIDED_CHECK[0]} CHECK ({SELF_DECIDED_CHECK[1]}) )"
    ),
}

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_category ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_category_readable ON agent.skill_category
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY skill_category_set_in_the_sessions_name ON agent.skill_category
        FOR INSERT TO brain_app
        WITH CHECK (set_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE: a change is a new row.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.skill_category TO brain_app",)

#: The append every trigger below makes, copied from `0056`, which copied `0003`.
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


def _function(name: str, head: str, body: str, *, actor: str, action: str) -> str:
    """One trigger function: its declarations, anything before the append, and the append."""
    return (
        f"""
CREATE OR REPLACE FUNCTION {name}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE{head}"""
        + _DECLARE
        + """BEGIN"""
        + body
        + _APPEND.format(actor=actor, action=action, subject="v_subject", details="v_details")
        + """    RETURN NULL;
END;
$$
"""
    )


#: An import records where it came from; an edit records the version it was edited from.
SKILL_IMPORT_TRIGGER_FUNCTION = _function(
    "agent.record_skill_import",
    """
    v_subject text := 'skill:' || NEW.name;
    v_details jsonb := CASE
        WHEN NEW.edited_from IS NOT NULL THEN jsonb_build_object(
            'change', 'edited', 'digest', NEW.digest, 'edited_from', NEW.edited_from
        )
        ELSE jsonb_build_object(
            'change', 'imported', 'digest', NEW.digest, 'source', NEW.source_kind
        )
    END;""",
    "",
    actor="NEW.submitted_by",
    action="skill",
)

#: The name of the skill a decision's key names. The key into `agent.skill` guarantees the row.
_SKILL_NAME_OF_THE_DECISION = """
    SELECT 'skill:' || s.name INTO v_subject FROM agent.skill s WHERE s.digest = NEW.digest;"""

#: A decision, and whether it was the importer's own.
SKILL_REVIEW_TRIGGER_FUNCTION = _function(
    "agent.record_skill_review",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object(
        'change', CASE WHEN NEW.self_decided THEN 'self_' || NEW.decision ELSE NEW.decision END,
        'digest', NEW.digest
    );""",
    _SKILL_NAME_OF_THE_DECISION,
    actor="NEW.decided_by",
    action="skill",
)

#: Categories set on a name. The categories themselves are words an administrator typed, so the
#: entry says that they changed and not what to: the ledger admits a value only when it is a field
#: name, and a label chosen by a person is a value.
SKILL_CATEGORY_TRIGGER_FUNCTION = _function(
    "agent.record_skill_category",
    """
    v_subject text := 'skill:' || NEW.skill_name;
    v_details jsonb := jsonb_build_object('change', 'categorised');""",
    "",
    actor="NEW.set_by",
    action="skill",
)

#: `0056`'s two function bodies, which the downgrade puts back.
PREVIOUS_IMPORT_FUNCTION = _function(
    "agent.record_skill_import",
    """
    v_subject text := 'skill:' || NEW.name;
    v_details jsonb := jsonb_build_object('change', 'imported', 'digest', NEW.digest);""",
    "",
    actor="NEW.submitted_by",
    action="skill",
)
PREVIOUS_REVIEW_FUNCTION = _function(
    "agent.record_skill_review",
    """
    v_subject text;
    v_details jsonb := jsonb_build_object('change', NEW.decision, 'digest', NEW.digest);""",
    _SKILL_NAME_OF_THE_DECISION,
    actor="NEW.decided_by",
    action="skill",
)

CATEGORY_TRIGGER = """
    CREATE TRIGGER skill_category_is_audited
        AFTER INSERT ON agent.skill_category
        FOR EACH ROW EXECUTE FUNCTION agent.record_skill_category()
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Each check travels with the column it reads, under the naming convention; see the docstring.
    op.add_column(
        "skill",
        sa.Column(
            "source_commit",
            sa.String(COMMIT_CHARS),
            *(sa.CheckConstraint(check, name=name) for name, check in COMMIT_CHECKS),
            nullable=True,
        ),
        schema="agent",
    )
    op.add_column(
        "skill",
        sa.Column(
            "source_path",
            sa.String(PATH_CHARS),
            sa.CheckConstraint(PATH_CHECK[1], name=PATH_CHECK[0]),
            nullable=True,
        ),
        schema="agent",
    )
    op.add_column(
        "skill",
        sa.Column(
            "edited_from",
            sa.String(DIGEST_CHARS),
            sa.ForeignKey("agent.skill.digest", name="fk_skill_edited_from_skill"),
            sa.CheckConstraint(EDITED_FROM_CHECK[1], name=EDITED_FROM_CHECK[0]),
            nullable=True,
        ),
        schema="agent",
    )
    op.add_column(
        "skill_review",
        sa.Column(
            "self_decided",
            sa.Boolean(),
            sa.CheckConstraint(SELF_DECIDED_CHECK[1], name=SELF_DECIDED_CHECK[0]),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="agent",
    )
    # The bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.drop_constraint("source_is_an_upload", "skill", schema="agent", type_="check")
    op.create_check_constraint("source_is_an_upload", "skill", SOURCE_AFTER, schema="agent")
    op.drop_constraint(
        "nobody_decides_their_own_import", "skill_review", schema="agent", type_="check"
    )
    op.create_check_constraint(
        "nobody_decides_their_own_import", "skill_review", DECIDER_AFTER, schema="agent"
    )

    op.create_table(
        "skill_category",
        sa.Column(
            "seq",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("skill_name", sa.String(NAME_CHARS), nullable=False),
        sa.Column("categories", postgresql.JSONB(), nullable=False),
        sa.Column("set_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"skill_name ~ '{SKILL_NAME_PATTERN}'", name="skill_name_shape"),
        sa.CheckConstraint(CATEGORY_LIST_CHECK, name="categories_are_a_short_list"),
        sa.CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)

    op.execute(SKILL_IMPORT_TRIGGER_FUNCTION)
    op.execute(SKILL_REVIEW_TRIGGER_FUNCTION)
    op.execute(SKILL_CATEGORY_TRIGGER_FUNCTION)
    op.execute(CATEGORY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER skill_category_is_audited ON agent.skill_category")
    op.execute("DROP FUNCTION agent.record_skill_category()")
    # The policies and the grant go with the table.
    op.drop_table("skill_category", schema="agent")
    # The functions first: `0056`'s bodies read no column this downgrade drops.
    op.execute(PREVIOUS_IMPORT_FUNCTION)
    op.execute(PREVIOUS_REVIEW_FUNCTION)
    op.drop_constraint(
        "nobody_decides_their_own_import", "skill_review", schema="agent", type_="check"
    )
    op.create_check_constraint(
        "nobody_decides_their_own_import",
        "skill_review",
        DECIDER_BEFORE,
        schema="agent",
        postgresql_not_valid=True,
    )
    op.drop_constraint("source_is_an_upload", "skill", schema="agent", type_="check")
    op.create_check_constraint(
        "source_is_an_upload", "skill", SOURCE_BEFORE, schema="agent", postgresql_not_valid=True
    )
    # Each check and the key go with the column that carries them.
    op.drop_column("skill_review", "self_decided", schema="agent")
    op.drop_column("skill", "edited_from", schema="agent")
    op.drop_column("skill", "source_path", schema="agent")
    op.drop_column("skill", "source_commit", schema="agent")
