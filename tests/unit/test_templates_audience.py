"""A template's schema version and overview, and an agent's added audience, on their own rules.

The pure half of M13.8.17 and M13.8.19: a manifest published as before is the first schema's digest
to the byte, the second schema signs an overview that only two paths may be, a signature never
crosses schemas, and an added department or person finds an agent without moving the predicate a
run is narrowed by. The install checks (`test_acceptance_checks_templates_audience.py`) run the
same over PostgreSQL.

Task ids: M13.8.15, M13.8.17, M13.8.19
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.agents.model import AgentAudience, AgentViewer, audience_scope, visible_to
from brain.agents.template import (
    MANIFEST_PATHS,
    MANIFEST_SCHEMA,
    OVERVIEW_PATHS,
    ManifestIdentity,
    SignedManifest,
    TemplateError,
    TemplateManifest,
    canonical,
    content_digest,
    publish,
    verify,
)
from brain.db import metadata
from brain.knowledge.visibility import Visibility
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0223_templates_and_audience.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
AT = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
KEY = "k" * 64


def manifest(name: str = "t1", summary: str = "A summary.") -> TemplateManifest:
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=name,
            version=1,
            published_by="u_author",
            display_name="A template",
            summary=summary,
        ),
        persona="Answers one thing.",
    )


def legacy_digest(one: TemplateManifest) -> str:
    """The digest as it was computed before the schema had a version, written out again here and
    nowhere else, so the two cannot drift together."""
    parts = (MANIFEST_SCHEMA, canonical(one.document()))
    return hashlib.sha256("".join(f"{len(part)}:{part}" for part in parts).encode()).hexdigest()


def test_a_manifest_published_without_an_overview_is_the_first_schemas_digest_to_the_byte() -> None:
    """Every template already published must go on verifying. Delete this and a change to the
    digest's domain, or a new part joined into it, stops every signature raised before."""
    signed = publish(manifest(), key=KEY, signed_by="u_author", at=AT)
    assert (signed.schema_version, signed.overview_path) == (1, "")
    assert signed.content_digest == legacy_digest(manifest()) == content_digest(manifest())
    verify(signed, key=KEY)


def test_a_manifest_that_names_an_overview_is_the_second_schema_and_signs_the_overview() -> None:
    """Both halves of the second schema. Delete this and the overview is unsigned, so anybody can
    repoint a published template's overview, or a template with none becomes the second schema."""
    one = manifest(summary="An overview.")
    signed = publish(one, key=KEY, signed_by="u_author", at=AT, overview_path="identity.summary")
    other = publish(
        one, key=KEY, signed_by="u_author", at=AT, overview_path="identity.display_name"
    )
    assert signed.schema_version == 2
    assert len({signed.content_digest, other.content_digest, legacy_digest(one)}) == 3
    verify(signed, key=KEY)
    verify(other, key=KEY)


@pytest.mark.parametrize(
    "path",
    ["persona", "golden_set", "skills", "guardrails.leash", "placeholders", "nowhere", "tier"],
)
def test_an_overview_that_is_not_the_display_name_or_the_summary_is_refused(path: str) -> None:
    """The paths a prompt is built from, and one that is not a path at all. Delete this and the
    overview becomes a second way to put prompt material in front of a model."""
    with pytest.raises(TemplateError, match="overview"):
        publish(manifest(), key=KEY, signed_by="u_author", at=AT, overview_path=path)


def test_a_signature_does_not_cross_schemas_and_a_record_cannot_claim_the_wrong_one() -> None:
    """The signature is domain-separated by schema, and so is the digest the record is checked
    against. Delete this and a second-schema record verifies under the first schema's signature,
    or claims version one while holding an overview."""
    one = manifest(summary="Overview.")
    first = publish(one, key=KEY, signed_by="u_author", at=AT)
    second = publish(one, key=KEY, signed_by="u_author", at=AT, overview_path="identity.summary")
    with pytest.raises(TemplateError):
        verify(second.model_copy(update={"signature": first.signature}), key=KEY)
    with pytest.raises((ValueError, TemplateError)):
        SignedManifest(
            manifest=one,
            content_digest=second.content_digest,
            signature=second.signature,
            signed_by="u_author",
            signed_at=AT,
            schema_version=1,
        )
    with pytest.raises((ValueError, TemplateError)):
        SignedManifest(
            manifest=one,
            content_digest=first.content_digest,
            signature=first.signature,
            signed_by="u_author",
            signed_at=AT,
            schema_version=1,
            overview_path="identity.summary",
        )
    with pytest.raises((ValueError, TemplateError)):
        SignedManifest(
            manifest=one,
            content_digest=first.content_digest,
            signature=first.signature,
            signed_by="u_author",
            signed_at=AT,
            schema_version=3,
        )


def test_the_overview_is_never_a_manifest_path_and_never_a_prompt_path() -> None:
    """The structural half of "no prompt includes the overview". Delete this and a path called
    overview, or the persona, is added to what may be an overview."""
    assert set(OVERVIEW_PATHS) <= set(MANIFEST_PATHS)
    assert "persona" not in OVERVIEW_PATHS
    assert not any("overview" in path for path in MANIFEST_PATHS)
    assert not any("overview" in name for name in TemplateManifest.model_fields)


# ----------------------------------------------------------------- the added audience
def viewer(person: str, *departments: str) -> AgentViewer:
    return AgentViewer(principal_id=person, departments=frozenset(departments))


def test_a_department_and_a_person_beside_the_level_find_the_agent_and_nobody_else_does() -> None:
    """Discovery widened by exactly the two lists. Delete this and the offer is found by nobody,
    or by everybody."""
    level = AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_steward", department="sales")
    offered = AgentAudience(
        level=Visibility.DEPARTMENT,
        owner_id="u_steward",
        department="sales",
        extra_departments=("web",),
        extra_people=("u_named",),
    )
    assert not visible_to(level, viewer("u_web", "web"))
    assert visible_to(offered, viewer("u_web", "web"))
    assert visible_to(offered, viewer("u_named", "finance"))
    assert not visible_to(offered, viewer("u_other", "finance"))
    assert visible_to(offered, viewer("u_sales", "sales"))


def test_an_added_audience_does_not_move_the_predicate_a_run_is_narrowed_by() -> None:
    """`audience_scope` of an audience with and without its additions, for every level that may
    carry them. Delete this and an offer widens reach, which `AUDIENCE_IS_NOT_AUTHORITY` forbids."""
    for level, department in (
        (Visibility.PERSONAL, ""),
        (Visibility.DEPARTMENT, "sales"),
    ):
        bare = AgentAudience(level=level, owner_id="u_steward", department=department)
        offered = AgentAudience(
            level=level,
            owner_id="u_steward",
            department=department,
            extra_departments=("web",),
            extra_people=("u_named",),
        )
        assert audience_scope(bare) == audience_scope(offered)


def test_a_company_audience_names_nobody_beside_it_and_an_empty_name_is_refused() -> None:
    """Both refusals. Delete this and a company agent carries a list that means nothing, or a blank
    entry offers the agent to nobody who exists and everybody who matches an empty string."""
    with pytest.raises(ValueError, match="everybody"):
        AgentAudience(level=Visibility.COMPANY, owner_id="u_steward", extra_people=("u_x",))
    with pytest.raises(ValueError, match="names somebody"):
        AgentAudience(
            level=Visibility.DEPARTMENT,
            owner_id="u_steward",
            department="sales",
            extra_departments=(" ",),
        )


# --------------------------------------------------------------------- the migration
def test_the_migration_builds_the_new_tables_exactly_as_the_models_declare_them() -> None:
    """Rendered DDL, table by table, with every index. Delete this and a model declares the
    one-live-offer index or the author-only draft's document check while the database never does."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for name in ("agent.template_draft", "agent.audience_extra"):
        table = metadata.tables[name]
        assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted, name
        for index in table.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted, index.name
    assert tuple(migration_module(MIGRATION).TABLES) == (
        "agent.template_draft",
        "agent.audience_extra",
    )


def test_the_two_columns_on_template_version_and_their_checks_are_what_the_model_declares() -> None:
    """The column additions are not a table, so the DDL comparison above cannot see them. Delete
    this and the model holds a check the database lacks."""
    emitted = squash(rendered("upgrade", MIGRATION))
    assert "ADD COLUMN schema_version SMALLINT DEFAULT 1 NOT NULL" in emitted
    assert "ADD COLUMN overview_path VARCHAR(40)" in emitted
    table = metadata.tables["agent.template_version"]
    names = {one.name for one in table.constraints}
    assert {
        "ck_template_version_only_version_two_names_an_overview",
        "ck_template_version_an_overview_is_never_prompt_text",
    } <= names
    assert "overview_path IS NULL OR schema_version >= 2" in emitted


def test_every_new_table_enables_row_security_and_grants_no_delete() -> None:
    """Read off the emitted statements. Delete this and a draft can be deleted by the application,
    or an offer's history can be."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for name in ("agent.template_draft", "agent.audience_extra"):
        assert f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY" in emitted
    grants = [one for one in emitted.split(";") if "GRANT" in one]
    assert grants and not any("DELETE" in one for one in grants)
