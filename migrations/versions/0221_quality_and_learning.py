"""What a lead flagged, what the machines and the people read of answers, how the golden questions
scored by release, what a failed case proposed, and who agreed to a change that needed more.

Eight tables in `ops`, every one insert-only and written in the session's own name. The argument for
each is in `brain.tables.quality`, and the shape of each is `brain.ops.feedback`'s `Flag` and
`CapturedCase`, `brain.ops.sampling`'s two readings, `brain.ops.evaluation`'s `CaseResult` and the
tiers of `brain.memory.tiers`. They are the stores those modules named and nothing wrote to:

- `ops.answer_flag` and `ops.regression_case`: a lead flags an answer by reference and a closed
  reason; one click turns the flag into a case that holds field names and no value.
- `ops.quality_reading` and `ops.quality_annotation`: the automated tier and the human tier, in two
  tables with no column in common, so no query can average them.
- `ops.golden_score`: one golden question on one release as one persona asked it.
- `ops.evaluation_candidate`: a failed case opened against an agent for a person to decide. It
  carries no change and no key into any agent table.
- `ops.positive_example`: an output a person approved unchanged, for its agent.
- `ops.tier_decision`: who agreed, and when it takes effect. A candidate's or an example's standing
  is its newest row here, which is why none of the others is ever updated.

**SELECT and INSERT only, and an insert names the session's principal** in the one column that says
who wrote it, as `0211` does. No UPDATE and no DELETE are granted on any of them: each row is a
fact about a moment. Who may be told of a row is decided where it is shown, so SELECT admits every
row, as `ops.budget_stop`'s does.

**Nothing here holds what an answer said.** Not one table has a free-text column, and the one
document (`ops.regression_case.document`) is checked to hold exactly the keys `CapturedCase` has.

The downgrade drops the tables, newest first. A flag, a reading or a score that was lost is made
again by the next run; a decision that was lost reopens the item it decided, which is the safe
direction.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M28.5.3, M16.6.7, M16.7.14

Revision ID: 0221
Revises: 0220
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0221"
# The plan's number, after 0220. Re-pointed at whichever migration is the head when it lands.
down_revision = "0220"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, in the order the tables are built.
TABLES: tuple[str, ...] = (
    "ops.answer_flag",
    "ops.regression_case",
    "ops.quality_reading",
    "ops.quality_annotation",
    "ops.golden_score",
    "ops.evaluation_candidate",
    "ops.positive_example",
    "ops.tier_decision",
)

APP_ROLE = "brain_app"
PRINCIPAL = "current_setting('app.principal_id', true)"

#: Each table and the column that names who wrote the row.
WRITERS: tuple[tuple[str, str], ...] = (
    ("ops.answer_flag", "flagged_by"),
    ("ops.regression_case", "captured_by"),
    ("ops.quality_reading", "recorded_by"),
    ("ops.quality_annotation", "annotator"),
    ("ops.golden_score", "ran_by"),
    ("ops.evaluation_candidate", "opened_by"),
    ("ops.positive_example", "approved_by"),
    ("ops.tier_decision", "decided_by"),
)

#: Written out, one per table, because `brain.ops.migration_policy` reads the migration's source for
#: the statement and not what a loop would produce.
ENABLED: tuple[str, ...] = (
    "ALTER TABLE ops.answer_flag ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.regression_case ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.quality_reading ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.quality_annotation ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.golden_score ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.evaluation_candidate ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.positive_example ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ops.tier_decision ENABLE ROW LEVEL SECURITY",
)

RLS: tuple[str, ...] = ENABLED + tuple(
    statement
    for table, writer in WRITERS
    for statement in (
        f"CREATE POLICY {table.split('.')[1]}_readable ON {table} FOR SELECT TO brain_app "
        "USING (true)",
        f"CREATE POLICY {table.split('.')[1]}_written_in_the_sessions_name ON {table} "
        f"FOR INSERT TO brain_app WITH CHECK ({writer} = {PRINCIPAL})",
    )
)

#: SELECT and INSERT, and never UPDATE or DELETE.
GRANTS: tuple[str, ...] = tuple(
    f"GRANT SELECT, INSERT ON {table} TO brain_app" for table, _ in WRITERS
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "answer_flag",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("trace_ref", sa.String(64), nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("flagged_by", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column(
            "flagged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("trace_ref ~ '^\\S+$'", name="trace_ref_is_one_token"),
        sa.CheckConstraint("question_id ~ '^\\S+$'", name="question_id_is_one_token"),
        sa.CheckConstraint("length(btrim(department)) > 0", name="department_present"),
        sa.CheckConstraint("length(btrim(flagged_by)) > 0", name="flagged_by_present"),
        sa.CheckConstraint(
            "reason IN ('incomplete', 'refused_wrongly', 'should_have_refused', 'stale', 'wrong_fact', 'wrong_sources')",
            name="reason",
        ),
        sa.UniqueConstraint(
            "trace_ref", "flagged_by", name="uq_answer_flag_one_per_lead_and_answer"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index("ix_ops_answer_flag_flagged_at", "answer_flag", ["flagged_at"], schema="ops")
    op.create_table(
        "regression_case",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("flag_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("captured_by", sa.String(128), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(document) = 'object' AND jsonb_exists_all(document, ARRAY['answering_fields', 'fault', 'held', 'locked_fields', 'mocked_from', 'origin_question_id', 'origin_trace_ref', 'question']) AND document - ARRAY['answering_fields', 'fault', 'held', 'locked_fields', 'mocked_from', 'origin_question_id', 'origin_trace_ref', 'question'] = '{}'::jsonb",
            name="a_case_has_exactly_the_captured_keys",
        ),
        sa.CheckConstraint("length(btrim(captured_by)) > 0", name="captured_by_present"),
        sa.UniqueConstraint("flag_id", name="uq_regression_case_one_per_flag"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["flag_id"], ["ops.answer_flag.id"], ondelete="RESTRICT"),
        schema="ops",
    )
    op.create_table(
        "quality_reading",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("fault", sa.String(32), nullable=True),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("request_id ~ '^\\S+$'", name="request_id_is_one_token"),
        sa.CheckConstraint(
            "fault IS NULL OR fault IN ('leaked', 'projection_too_narrow', 'projection_too_wide', 'refusal_distinguishable', 'unlocked')",
            name="fault_is_a_mechanical_finding",
        ),
        sa.CheckConstraint("passed = (fault IS NULL)", name="passed_exactly_when_no_fault"),
        sa.CheckConstraint("length(btrim(recorded_by)) > 0", name="recorded_by_present"),
        sa.UniqueConstraint("request_id", name="uq_quality_reading_one_per_request"),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index("ix_ops_quality_reading_read_at", "quality_reading", ["read_at"], schema="ops")
    op.create_table(
        "quality_annotation",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("annotator", sa.String(128), nullable=False),
        sa.Column("sound", sa.Boolean(), nullable=False),
        sa.Column("fault", sa.String(32), nullable=True),
        sa.Column(
            "annotated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("request_id ~ '^\\S+$'", name="request_id_is_one_token"),
        sa.CheckConstraint(
            "fault IS NULL OR fault IN ('incomplete', 'refused_wrongly', 'should_have_refused', 'stale', 'wrong_fact', 'wrong_sources')",
            name="fault_is_a_human_reason",
        ),
        sa.CheckConstraint("sound = (fault IS NULL)", name="sound_exactly_when_no_fault"),
        sa.CheckConstraint("length(btrim(annotator)) > 0", name="annotator_present"),
        sa.UniqueConstraint("request_id", name="uq_quality_annotation_one_per_request"),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index("ix_ops_quality_annotation_day", "quality_annotation", ["day"], schema="ops")
    op.create_table(
        "golden_score",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("release", sa.String(64), nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("persona", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("ran_by", sa.String(128), nullable=False),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("length(btrim(release)) > 0", name="release_present"),
        sa.CheckConstraint("question_id ~ '^\\S+$'", name="question_id_is_one_token"),
        sa.CheckConstraint("length(btrim(persona)) > 0", name="persona_present"),
        sa.CheckConstraint("severity IN ('permission', 'quality')", name="severity"),
        sa.CheckConstraint(
            "passed = (reason = '')", name="a_failure_says_which_expectation_failed"
        ),
        sa.CheckConstraint("length(reason) <= 64", name="reason_is_a_code"),
        sa.CheckConstraint("length(btrim(ran_by)) > 0", name="ran_by_present"),
        sa.UniqueConstraint(
            "release", "question_id", "persona", name="uq_golden_score_one_per_release_question"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index("ix_ops_golden_score_ran_at", "golden_score", ["ran_at"], schema="ops")
    op.create_table(
        "evaluation_candidate",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("agent_id", sa.String(60), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("case_ref", sa.String(64), nullable=False),
        sa.Column("opened_by", sa.String(128), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("source IN ('canary', 'golden', 'sampled')", name="source"),
        sa.CheckConstraint("case_ref ~ '^\\S+$'", name="case_ref_is_one_token"),
        sa.CheckConstraint("length(btrim(opened_by)) > 0", name="opened_by_present"),
        sa.UniqueConstraint(
            "agent_id", "source", "case_ref", name="uq_evaluation_candidate_one_per_failed_case"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_evaluation_candidate_agent", "evaluation_candidate", ["agent_id"], schema="ops"
    )
    op.create_table(
        "positive_example",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("agent_id", sa.String(60), nullable=False),
        sa.Column("skill", sa.String(64), nullable=True),
        sa.Column("artefact_ref", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("artefact_ref ~ '^\\S+$'", name="artefact_ref_is_one_token"),
        sa.CheckConstraint(
            "skill IS NULL OR length(btrim(skill)) > 0", name="skill_present_when_named"
        ),
        sa.CheckConstraint("length(btrim(approved_by)) > 0", name="approved_by_present"),
        sa.UniqueConstraint("agent_id", "artefact_ref", name="uq_positive_example_one_per_output"),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index("ix_ops_positive_example_agent", "positive_example", ["agent_id"], schema="ops")
    op.create_table(
        "tier_decision",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("item_kind", sa.String(32), nullable=False),
        sa.Column("item_ref", sa.String(64), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=False),
        sa.Column("agreed_by", sa.ARRAY(sa.String(128)), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint("item_kind IN ('candidate', 'example', 'rule')", name="item_kind"),
        sa.CheckConstraint("item_ref ~ '^\\S+$'", name="item_ref_is_one_token"),
        sa.CheckConstraint("tier IN (2, 3)", name="only_tiers_two_and_three_are_decided_by_people"),
        sa.CheckConstraint("decision IN ('approved', 'declined', 'promoted')", name="decision"),
        sa.CheckConstraint(
            "(tier = 2 AND decision <> 'approved') OR (tier = 3 AND decision <> 'promoted')",
            name="a_decision_word_belongs_to_its_tier",
        ),
        sa.CheckConstraint("length(btrim(decided_by)) > 0", name="decided_by_present"),
        sa.CheckConstraint("cardinality(agreed_by) >= 1", name="somebody_agreed"),
        sa.CheckConstraint(
            "decided_by = ANY(agreed_by)", name="the_decider_is_among_those_who_agreed"
        ),
        sa.CheckConstraint(
            "effective_from >= decided_at", name="it_takes_effect_no_earlier_than_decided"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_tier_decision_item",
        "tier_decision",
        ["item_kind", "item_ref", "decided_at"],
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grants go with the tables.
    for table, _ in reversed(WRITERS):
        op.drop_table(table.split(".")[1], schema="ops")
