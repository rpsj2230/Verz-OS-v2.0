"""The provider registry, the matrix gate's two tables, an agent's model pin, and a derived role.

Schema only. `brain.tables.model_registry` argues the three tables; this is what builds them and
the four changes beside them.

**Three tables.** `ops.model_provider` is every provider this install uses with the terms the
company agreed with it (M5.6.4), and an OpenAI-compatible provider added from the console with
its address and model names (M5.7.2); its key is in the vault slot and never here.
`ops.golden_question` is the install's own golden questions, and `ops.routing_change` a matrix
change with what the gate found when it was run against them and the permission canaries
(M5.6.2). SELECT, INSERT and UPDATE for `brain_app`, no DELETE: a provider and a question are
retired by `deleted_at`, and a change is history. **`USING` reads only live rows** on the two
retirable tables, as `0045` does for the ladder; the change table's rows are all readable.

**`ops.model_attempt.data_categories`.** Which categories of data an attempt sent (M5.6.4), as a
JSON array defaulting to empty, so the previous release, which never names it, writes a valid
row. **`refused` joins the attempt outcomes**, replacing `0003`'s list: a provider that declined
on content is recorded as that rather than as our request being wrong (M5.4.1).

**`agent.agent.model_pin_provider` and `model_pin_model`**, nullable, both or neither (M5.7.3).

**`ops.routing_rung_role()`**, a BEFORE INSERT OR UPDATE trigger that writes `role` from the
rung's position and provider against the lowest live position in its tier, which is
`brain.models.routing.RoutingChain.role_of` in SQL (M5.3.2). Whatever a writer sends as `role` is
overwritten. Existing rows are not rewritten here, which would be data in a schema migration;
each is derived on its next write.

**The downgrade** drops the trigger, the pin, the column and the three tables, and puts `0003`'s
outcome list back `NOT VALID`, for `0026`'s reason: an attempt already recorded as refused stays.

Task ids: M5.6.2, M5.6.4, M5.7.2, M5.7.3, M5.3.2, M5.4.1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0097"
# The newest migration on origin/main when this was written, 86a0016: 0093, 0096, 0095, 0095b.
# Nothing after 0003 touches the attempt outcomes, nothing after 0014 the agent's columns, and
# nothing after 0059 the ladder's triggers.
down_revision = "0095b"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.model_provider", "ops.golden_question", "ops.routing_change")

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.model_registry` by tests.
PROVIDER_SLUG_PATTERN = "^[a-z][a-z0-9_]{1,30}$"
HTTPS_ADDRESS_PATTERN = "^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$"
RESIDENCY_CLASSES = "residency_class IN ('global', 'on_prem', 'region_pinned')"
KINDS = "kind IN ('builtin', 'openai_compatible')"

#: The attempt outcomes before and after `refused`. The first is `0003`'s.
WITHOUT_REFUSED = (
    "outcome IN ('circuit_open', 'connection_error', 'context_exceeded', 'ok', "
    "'provider_error', 'rate_limited', 'stopped', 'timeout')"
)
WITH_REFUSED = (
    "outcome IN ('circuit_open', 'connection_error', 'context_exceeded', 'ok', "
    "'provider_error', 'rate_limited', 'refused', 'stopped', 'timeout')"
)

#: What this migration replaces: `0003`'s attempt outcomes.
SUPERSEDES: dict[str, str] = {WITHOUT_REFUSED: WITH_REFUSED}

MODEL_PIN_BOTH_OR_NEITHER = "(model_pin_provider IS NULL) = (model_pin_model IS NULL)"

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON ops.model_provider TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON ops.golden_question TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON ops.routing_change TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.model_provider ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY model_provider_live ON ops.model_provider
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY model_provider_insertable ON ops.model_provider
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY model_provider_updatable ON ops.model_provider
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "ALTER TABLE ops.golden_question ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY golden_question_live ON ops.golden_question
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY golden_question_insertable ON ops.golden_question
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY golden_question_updatable ON ops.golden_question
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    "ALTER TABLE ops.routing_change ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY routing_change_visible ON ops.routing_change
        FOR ALL TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
)

#: `RoutingChain.role_of`: the lowest live position in the tier is the primary, a rung sharing
#: its provider is a same-provider failover, and any other is a cross-provider one.
ROLE_FUNCTION = """
CREATE FUNCTION ops.routing_rung_role() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_position smallint;
    v_provider text;
BEGIN
    SELECT r.position, r.provider INTO v_position, v_provider
      FROM ops.routing_rung r
     WHERE r.tier = NEW.tier
       AND r.deleted_at IS NULL
       AND r.id <> NEW.id
     ORDER BY r.position
     LIMIT 1;
    IF v_position IS NULL OR NEW.position < v_position THEN
        NEW.role := 'primary';
    ELSIF v_provider = NEW.provider THEN
        NEW.role := 'same_provider_failover';
    ELSE
        NEW.role := 'cross_provider_failover';
    END IF;
    RETURN NEW;
END;
$$
"""

ROLE_TRIGGER = """
    CREATE TRIGGER routing_rung_role_is_derived
        BEFORE INSERT OR UPDATE ON ops.routing_rung
        FOR EACH ROW EXECUTE FUNCTION ops.routing_rung_role()
"""


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "model_provider",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(31), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("base_url", sa.String(300), nullable=True),
        sa.Column(
            "models",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("processing_region", sa.String(64), server_default="global", nullable=False),
        sa.Column("residency_class", sa.String(16), server_default="global", nullable=False),
        sa.Column("storage_location", sa.String(300), server_default="", nullable=False),
        sa.Column("retention_terms", sa.String(1000), server_default="", nullable=False),
        sa.Column("training_terms", sa.String(1000), server_default="", nullable=False),
        sa.Column("agreement_url", sa.String(300), nullable=True),
        sa.Column(
            "lane_overrides",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(128), nullable=False),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"slug ~ '{PROVIDER_SLUG_PATTERN}'", name="slug_shape"),
        sa.CheckConstraint(KINDS, name="kind"),
        sa.CheckConstraint("length(btrim(label)) > 0", name="label_present"),
        sa.CheckConstraint(
            "(kind = 'openai_compatible') = (base_url IS NOT NULL)", name="address_iff_added"
        ),
        sa.CheckConstraint(
            f"base_url IS NULL OR base_url ~ '{HTTPS_ADDRESS_PATTERN}'", name="address_shape"
        ),
        sa.CheckConstraint(
            f"agreement_url IS NULL OR agreement_url ~ '{HTTPS_ADDRESS_PATTERN}'",
            name="agreement_shape",
        ),
        sa.CheckConstraint("jsonb_typeof(models) = 'array'", name="models_array"),
        sa.CheckConstraint("jsonb_typeof(lane_overrides) = 'object'", name="lane_overrides_object"),
        sa.CheckConstraint(RESIDENCY_CLASSES, name="residency_class"),
        sa.CheckConstraint(
            "residency_class = 'global' OR processing_region <> 'global'",
            name="pinned_names_a_region",
        ),
        sa.CheckConstraint("length(btrim(updated_by)) > 0", name="updated_by_present"),
        schema="ops",
    )
    op.create_index("ix_model_provider_deleted_at", "model_provider", ["deleted_at"], schema="ops")
    op.create_index(
        "uq_model_provider_slug_live",
        "model_provider",
        ["slug"],
        unique=True,
        schema="ops",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "golden_question",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("question", sa.String(2000), nullable=False),
        sa.Column("asked_as", sa.String(128), nullable=False),
        sa.Column("expect", sa.String(8), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(btrim(question)) > 0", name="question_present"),
        sa.CheckConstraint("length(btrim(asked_as)) > 0", name="asked_as_present"),
        sa.CheckConstraint("expect IN ('answer', 'refuse')", name="expect"),
        sa.CheckConstraint("length(btrim(created_by)) > 0", name="created_by_present"),
        schema="ops",
    )
    op.create_index(
        "ix_golden_question_deleted_at", "golden_question", ["deleted_at"], schema="ops"
    )

    op.create_table(
        "routing_change",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column(
            "rung_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("ops.routing_rung.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("proposed", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column(
            "failing", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "reasons", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("quality_share", sa.Numeric(4, 3), nullable=True),
        sa.Column("proposed_by", sa.String(128), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('add', 'edit')", name="kind"),
        sa.CheckConstraint("status IN ('applied', 'held')", name="status"),
        sa.CheckConstraint("kind <> 'edit' OR rung_id IS NOT NULL", name="edit_names_a_rung"),
        sa.CheckConstraint("jsonb_typeof(proposed) = 'object'", name="proposed_object"),
        sa.CheckConstraint("jsonb_typeof(failing) = 'array'", name="failing_array"),
        sa.CheckConstraint("jsonb_typeof(reasons) = 'array'", name="reasons_array"),
        sa.CheckConstraint(
            "status <> 'applied' OR jsonb_array_length(failing) = 0",
            name="applied_has_no_failing_case",
        ),
        sa.CheckConstraint(
            "quality_share IS NULL OR quality_share BETWEEN 0 AND 1", name="quality_share_range"
        ),
        sa.CheckConstraint("length(btrim(proposed_by)) > 0", name="proposed_by_present"),
        schema="ops",
    )
    op.create_index("ix_routing_change_rung_id", "routing_change", ["rung_id"], schema="ops")
    op.create_index("ix_routing_change_decided_at", "routing_change", ["decided_at"], schema="ops")

    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)

    # The check travels with the column it reads, as `0093` adds `lease`.
    op.add_column(
        "model_attempt",
        sa.Column(
            "data_categories",
            postgresql.JSONB(),
            sa.CheckConstraint(
                "jsonb_typeof(data_categories) = 'array'", name="data_categories_array"
            ),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        schema="ops",
    )
    # The bare constraint name, for the reason 0026 gives.
    op.drop_constraint("outcome", "model_attempt", schema="ops", type_="check")
    op.create_check_constraint("outcome", "model_attempt", WITH_REFUSED, schema="ops")

    op.add_column(
        "agent", sa.Column("model_pin_provider", sa.String(60), nullable=True), schema="agent"
    )
    # The check travels with the second column, as `0093`'s does with `lease`: the previous
    # release names neither column, so every row it writes holds two nulls and satisfies it.
    op.add_column(
        "agent",
        sa.Column(
            "model_pin_model",
            sa.String(120),
            sa.CheckConstraint(MODEL_PIN_BOTH_OR_NEITHER, name="model_pin_both_or_neither"),
            nullable=True,
        ),
        schema="agent",
    )

    op.execute(ROLE_FUNCTION)
    op.execute(ROLE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER routing_rung_role_is_derived ON ops.routing_rung")
    op.execute("DROP FUNCTION ops.routing_rung_role()")
    # The check goes with the columns it reads.
    op.drop_constraint("model_pin_both_or_neither", "agent", schema="agent", type_="check")
    op.drop_column("agent", "model_pin_model", schema="agent")
    op.drop_column("agent", "model_pin_provider", schema="agent")
    op.drop_constraint("outcome", "model_attempt", schema="ops", type_="check")
    op.create_check_constraint(
        "outcome", "model_attempt", WITHOUT_REFUSED, schema="ops", postgresql_not_valid=True
    )
    op.drop_column("model_attempt", "data_categories", schema="ops")
    # The indexes, the policies and the grants go with the tables. The change points at the
    # ladder, so it goes first.
    op.drop_table("routing_change", schema="ops")
    op.drop_table("golden_question", schema="ops")
    op.drop_table("model_provider", schema="ops")
