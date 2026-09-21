"""The provider registry, the golden questions a matrix change is asked, and the changes held.

Three tables `0097` adds, each the storage for one sentence the owner wrote.

**`ops.model_provider`: every provider this install uses, with what the company agreed with it.**
M5.6.4 asks that each registered provider carry its processing region, its retention and
training terms and a link to the signed agreement, and M5.7.2 that an OpenAI-compatible provider
be added from the console with its address, key and model names. One table serves both, because
both are the install's record of a provider: a built-in provider's row carries terms and no
address (the product owns where it is reached, `brain.models.wire`), an added provider's row
carries its address too. **The key is never here.** It is in the vault slot `providers/<slug>`,
written by `brain.ops.credentials.Credentials.keep`, and the row does not say whether one is held.

**The address of an added provider cannot be changed once written**, and the table says so by
having no route that updates it: `brain.provider_routes` updates terms and models, and a new
address is a new provider with a new key. An address somebody can edit is a key somebody can
redirect to a server they run, which is `wire.A_PROVIDER_IS_REACHED_AT_ITS_OWN_ADDRESS_AND_NEVER_
ONE_A_PERSON_TYPED`; binding the address to the key written with it keeps that argument true for
a provider a person did type.

**`ops.golden_question`: the install's own golden questions.** The repository's golden corpus is
the test suite's synthetic company and does not exist on an install (`brain.console.quality_view`
says so). M5.6.2 needs questions an install can ask as its own people, so an administrator
records them: the question, the principal it is asked as, and whether it must be answered or
refused. A question that must be refused is a permission case and scored at zero tolerance
(`brain.ops.evaluation`).

**`ops.routing_change`: a matrix change and what the gate found.** A rung edit or a new rung is
written here first, run against the golden questions and the permission canaries, and applied
only when nothing regressed. A held change keeps its failing cases, by question id and reason, so
the Routing screen shows why it did not take traffic.

Task ids: M5.6.2, M5.6.4, M5.7.2, M5.1.3, M5.5.3
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, SoftDeleteMixin, TimestampMixin
from brain.models.registry import HTTPS_ADDRESS_PATTERN, ProviderKind
from brain.models.registry import SLUG_PATTERN as PROVIDER_SLUG_PATTERN
from brain.models.routing import ResidencyClass
from brain.tables.identity import one_of

LABEL_CHARS = 80
ADDRESS_CHARS = 300
REGION_CHARS = 64
TERMS_CHARS = 1000
QUESTION_CHARS = 2000
PERSON_CHARS = 128


class GoldenExpectation(enum.StrEnum):
    """What a golden question must come back as."""

    ANSWER = "answer"
    REFUSE = "refuse"


class ChangeKind(enum.StrEnum):
    """What a routing change does to the ladder."""

    EDIT = "edit"
    ADD = "add"


class ChangeStatus(enum.StrEnum):
    """Where a routing change ended. There is no pending state: the gate runs in the request."""

    HELD = "held"
    APPLIED = "applied"


class ModelProviderRow(TimestampMixin, SoftDeleteMixin, Base):
    """`ops.model_provider`. One provider this install uses and what it agreed with it."""

    __tablename__ = "model_provider"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(String(31), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    label: Mapped[str] = mapped_column(String(LABEL_CHARS), nullable=False)
    #: Only an added provider has one, and it is never updated. See the module docstring.
    base_url: Mapped[str | None] = mapped_column(String(ADDRESS_CHARS), nullable=True)
    #: The model names an added provider serves, as a JSON array of strings.
    models: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    processing_region: Mapped[str] = mapped_column(
        String(REGION_CHARS), nullable=False, server_default="global"
    )
    residency_class: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=ResidencyClass.GLOBAL.value
    )
    #: Where the provider keeps what it is sent, in the words of the agreement.
    storage_location: Mapped[str] = mapped_column(
        String(ADDRESS_CHARS), nullable=False, server_default=""
    )
    retention_terms: Mapped[str] = mapped_column(
        String(TERMS_CHARS), nullable=False, server_default=""
    )
    training_terms: Mapped[str] = mapped_column(
        String(TERMS_CHARS), nullable=False, server_default=""
    )
    agreement_url: Mapped[str | None] = mapped_column(String(ADDRESS_CHARS), nullable=True)
    #: Per-lane timeout and attempt overrides (M5.1.3): `{"answer": {"timeout_seconds": 20}}`.
    lane_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_by: Mapped[str] = mapped_column(String(PERSON_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(f"slug ~ '{PROVIDER_SLUG_PATTERN}'", name="slug_shape"),
        CheckConstraint(one_of("kind", ProviderKind), name="kind"),
        CheckConstraint("length(btrim(label)) > 0", name="label_present"),
        # An added provider has an address and a built-in one never does.
        CheckConstraint(
            "(kind = 'openai_compatible') = (base_url IS NOT NULL)", name="address_iff_added"
        ),
        CheckConstraint(
            f"base_url IS NULL OR base_url ~ '{HTTPS_ADDRESS_PATTERN}'", name="address_shape"
        ),
        CheckConstraint(
            f"agreement_url IS NULL OR agreement_url ~ '{HTTPS_ADDRESS_PATTERN}'",
            name="agreement_shape",
        ),
        CheckConstraint("jsonb_typeof(models) = 'array'", name="models_array"),
        CheckConstraint("jsonb_typeof(lane_overrides) = 'object'", name="lane_overrides_object"),
        CheckConstraint(one_of("residency_class", ResidencyClass), name="residency_class"),
        # A pinned region names one, so a claim of residency always says where.
        CheckConstraint(
            "residency_class = 'global' OR processing_region <> 'global'",
            name="pinned_names_a_region",
        ),
        CheckConstraint("length(btrim(updated_by)) > 0", name="updated_by_present"),
        Index(
            "uq_model_provider_slug_live",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "ops"},
    )


class GoldenQuestionRow(TimestampMixin, SoftDeleteMixin, Base):
    """`ops.golden_question`. One question a matrix change must still answer, or refuse."""

    __tablename__ = "golden_question"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    question: Mapped[str] = mapped_column(String(QUESTION_CHARS), nullable=False)
    #: The principal the question is asked as, by id. Its reach is resolved at each run.
    asked_as: Mapped[str] = mapped_column(String(PERSON_CHARS), nullable=False)
    expect: Mapped[str] = mapped_column(String(8), nullable=False)
    created_by: Mapped[str] = mapped_column(String(PERSON_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(question)) > 0", name="question_present"),
        CheckConstraint("length(btrim(asked_as)) > 0", name="asked_as_present"),
        CheckConstraint(one_of("expect", GoldenExpectation), name="expect"),
        CheckConstraint("length(btrim(created_by)) > 0", name="created_by_present"),
        {"schema": "ops"},
    )


class RoutingChangeRow(TimestampMixin, Base):
    """`ops.routing_change`. One proposed matrix change and what the gate found (M5.6.2).

    No soft delete: a held change is history, and a change nobody can see was held is a change
    whose failing cases were lost.
    """

    __tablename__ = "routing_change"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    #: The rung an edit changes, or the rung an applied addition created.
    rung_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ops.routing_rung.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: The fields the change sets, as the route validated them.
    proposed: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    #: Each failing case as `{"case": id, "reason": sentence}`. Empty when it was applied.
    failing: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: Every reason the verdict gave, in the order `brain.ops.evaluation.score` gives them.
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: The quality share the golden questions scored, which the next change is compared with.
    quality_share: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(PERSON_CHARS), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("kind", ChangeKind), name="kind"),
        CheckConstraint(one_of("status", ChangeStatus), name="status"),
        CheckConstraint("kind <> 'edit' OR rung_id IS NOT NULL", name="edit_names_a_rung"),
        CheckConstraint("jsonb_typeof(proposed) = 'object'", name="proposed_object"),
        CheckConstraint("jsonb_typeof(failing) = 'array'", name="failing_array"),
        CheckConstraint("jsonb_typeof(reasons) = 'array'", name="reasons_array"),
        CheckConstraint(
            "status <> 'applied' OR jsonb_array_length(failing) = 0",
            name="applied_has_no_failing_case",
        ),
        CheckConstraint(
            "quality_share IS NULL OR quality_share BETWEEN 0 AND 1", name="quality_share_range"
        ),
        CheckConstraint("length(btrim(proposed_by)) > 0", name="proposed_by_present"),
        Index("ix_routing_change_decided_at", "decided_at"),
        {"schema": "ops"},
    )


#: The order `0097` creates them in: `routing_change` points at `ops.routing_rung` only.
MODEL_REGISTRY_TABLES: tuple[str, ...] = (
    "ops.model_provider",
    "ops.golden_question",
    "ops.routing_change",
)
