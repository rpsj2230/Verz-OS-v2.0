"""A template draft that survives a restart, a schema version and an overview on a template, and an
agent offered to more than its level.

Three things in the agent schema, none of which changes what an existing row means.

**`agent.template_draft`, M13.8.15.** An agent saved as a template is a draft its author works
through item by item and publishes. `brain.agents.authoring` had the flow as values in a process;
this is the row that keeps it. Only the author's session may read, write or publish one, and
nothing installs from it: an installation reads `agent.template_version`, which a draft reaches
only when its author publishes. `brain.tables.template_draft` holds the argument.

**`agent.template_version.schema_version` and `overview_path`, M13.8.17.** Two columns. Every row
already there is `schema_version` 1, which is what it was signed under, and its digest and signature
are unchanged and go on verifying. A row signed under version 2 names the overview path it signed:
one of two manifest paths that are text for a person and are not what any prompt is built from. A
version-one row has none. See `brain.agents.template.THE_OVERVIEW_IS_FOR_PEOPLE_AND_NEVER_FOR_A_MODEL`.
The table is still SELECT and INSERT only: a published version is never amended.

**`agent.audience_extra`, M13.8.19.** A department or a person named beside an agent's level, who
may find and start it and gain no reach by it: `brain.agents.model.audience_scope` does not read
this table. Insert, plus an update of the two removal columns once, which `group_install`'s shape
keeps the history in. See `brain.tables.audience_extra`.

**Nothing here narrows what the previous release writes.** The new columns on `template_version`
default to version one and null, the two checks over them begin with the column being null, and
the two new tables are new.

The downgrade drops the tables and the columns. A draft is made again, a version-two row's
overview is lost and its signature then fails the older code's check, which is why a downgrade
below this revision is not offered once a version-two template is published.

Task ids: M13.8.15, M13.8.17, M13.8.19

Revision ID: 0223
Revises: 0222
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0223"
# The plan's number, after 0222. Re-pointed at whichever migration is the head when it lands.
down_revision = "0222"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. The column additions are not tables.
TABLES: tuple[str, ...] = ("agent.template_draft", "agent.audience_extra")

APP_ROLE = "brain_app"
PRINCIPAL = "current_setting('app.principal_id', true)"

OWNER_ID_CHARS = 128
AGENT_ID_CHARS = 60
STATE_CHARS = 16
KIND_CHARS = 16
VALUE_CHARS = 128

#: `brain.agents.template.MANIFEST_PATHS`, copied for `0016`'s reason.
MANIFEST_PATHS = (
    "'authority.allowed_tools', 'authority.capabilities', 'authority.required_tools', "
    "'authority.scope', 'connectors', 'golden_set', 'guardrails.leash', "
    "'guardrails.max_side_effect', 'identity.display_name', 'identity.published_by', "
    "'identity.summary', 'identity.template_id', 'identity.version', 'persona', "
    "'placeholders', 'skills', 'tier'"
)

#: `brain.agents.template.OVERVIEW_PATHS`, copied: the two manifest paths an overview may be.
OVERVIEW_PATHS = "'identity.display_name', 'identity.summary'"

STATES = "state IN ('draft', 'published')"
KINDS = "kind IN ('department', 'person')"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.template_draft ENABLE ROW LEVEL SECURITY",
    # Only the author sees a draft, administrators included: it is an agent's configuration
    # before anybody has looked for what is in it.
    f"""
    CREATE POLICY template_draft_visible_to_its_author ON agent.template_draft
        FOR SELECT TO brain_app
        USING (author = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY template_draft_started_by_its_author ON agent.template_draft
        FOR INSERT TO brain_app
        WITH CHECK (author = {PRINCIPAL} AND state = 'draft' AND decisions = '{{}}'::jsonb)
    """,
    f"""
    CREATE POLICY template_draft_worked_by_its_author ON agent.template_draft
        FOR UPDATE TO brain_app
        USING (author = {PRINCIPAL} AND state = 'draft')
        WITH CHECK (author = {PRINCIPAL})
    """,
    "ALTER TABLE agent.audience_extra ENABLE ROW LEVEL SECURITY",
    # Read by the roster for everybody it narrows, so who may be told is decided where it is shown.
    """
    CREATE POLICY audience_extra_readable ON agent.audience_extra
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY audience_extra_added_in_the_sessions_name ON agent.audience_extra
        FOR INSERT TO brain_app
        WITH CHECK (added_by = {PRINCIPAL} AND removed_at IS NULL)
    """,
    f"""
    CREATE POLICY audience_extra_withdrawn_in_the_sessions_name ON agent.audience_extra
        FOR UPDATE TO brain_app
        USING (removed_at IS NULL)
        WITH CHECK (removed_by = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON agent.template_draft TO brain_app",
    "GRANT UPDATE (decisions, state, published_version, published_at, updated_at) "
    "ON agent.template_draft TO brain_app",
    "GRANT SELECT, INSERT ON agent.audience_extra TO brain_app",
    "GRANT UPDATE (removed_by, removed_at) ON agent.audience_extra TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.add_column(
        "template_version",
        sa.Column("schema_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        schema="agent",
    )
    op.add_column(
        "template_version",
        sa.Column("overview_path", sa.String(40), nullable=True),
        schema="agent",
    )
    op.create_check_constraint(
        "only_version_two_names_an_overview",
        "template_version",
        "overview_path IS NULL OR schema_version >= 2",
        schema="agent",
    )
    op.create_check_constraint(
        "an_overview_is_never_prompt_text",
        "template_version",
        f"overview_path IS NULL OR overview_path = ANY(ARRAY[{OVERVIEW_PATHS}])",
        schema="agent",
    )
    op.create_table(
        "template_draft",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("author", sa.String(OWNER_ID_CHARS), nullable=False),
        sa.Column("source_agent_id", sa.String(AGENT_ID_CHARS), nullable=True),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("decisions", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "state", sa.String(STATE_CHARS), nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(author)) > 0", name="author_present"),
        sa.CheckConstraint(STATES, name="state"),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="document_shape"),
        sa.CheckConstraint(
            f"jsonb_exists_all(document, ARRAY[{MANIFEST_PATHS}])",
            name="document_holds_every_path",
        ),
        sa.CheckConstraint(
            f"document - ARRAY[{MANIFEST_PATHS}] = '{{}}'::jsonb",
            name="document_holds_no_other_path",
        ),
        sa.CheckConstraint("jsonb_typeof(decisions) = 'object'", name="decisions_shape"),
        sa.CheckConstraint(
            "(state = 'published') = (published_version IS NOT NULL)",
            name="a_published_draft_names_its_version",
        ),
        sa.CheckConstraint(
            "(published_version IS NULL) = (published_at IS NULL)",
            name="a_published_draft_names_its_instant",
        ),
        schema="agent",
    )
    op.create_index(
        "ix_agent_template_draft_author", "template_draft", ["author", "updated_at"], schema="agent"
    )
    op.create_table(
        "audience_extra",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("kind", sa.String(KIND_CHARS), nullable=False),
        sa.Column("value", sa.String(VALUE_CHARS), nullable=False),
        sa.Column("added_by", sa.String(OWNER_ID_CHARS), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column("removed_by", sa.String(OWNER_ID_CHARS), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint(KINDS, name="kind"),
        sa.CheckConstraint("length(btrim(value)) > 0", name="value_present"),
        sa.CheckConstraint("length(btrim(added_by)) > 0", name="added_by_present"),
        sa.CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        schema="agent",
    )
    op.create_index(
        "uq_audience_extra_one_live_row_per_name",
        "audience_extra",
        ["agent_id", "kind", "value"],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the tables.
    op.drop_table("audience_extra", schema="agent")
    op.drop_table("template_draft", schema="agent")
    op.drop_constraint(
        "an_overview_is_never_prompt_text",
        "template_version",
        schema="agent",
        type_="check",
    )
    op.drop_constraint(
        "only_version_two_names_an_overview", "template_version", schema="agent", type_="check"
    )
    op.drop_column("template_version", "overview_path", schema="agent")
    op.drop_column("template_version", "schema_version", schema="agent")
