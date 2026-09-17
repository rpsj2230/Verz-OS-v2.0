"""The registry the application builds, and the fact that anything builds one at all.

**This file exists because of an absence rather than a behaviour.** `brain.tools.registry`
carries every rule about what may be registered, and `ToolRegistry.freeze` says in its own
docstring that it is "called at startup". Nothing called it. Outside the tests, no code in
`src/` had ever constructed a `ToolRegistry`, so a careful set of rules had never refused
anything, and the first tool to break one would have broken it against a registry somebody
assembled the afternoon they needed one.

That is the same failure this repository has now found four times: a mechanism that is
correct, tested, and never invoked. The deploy that reported success and deployed nothing,
the RLS sweep that had never run, the traceability count that was stale, and this.

So the tests below are mostly about wiring: that there is one builder, that the application
calls it, that what comes back is frozen, and that a tool registered through it went through
every door on the way in.

**And which entities it registers depends on the source, since 2026-09-14.** The price list is
built in and registered on every install. The demo's clients, jobs and invoices are classified
by the demo, for the demo's source, and registered only by an install that reads it. The tests
at the end hold both halves, because a registration that leaked onto every install and one that
happened nowhere each pass a test that looks at one install.

Task ids: M12.1.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from brain import demo
from brain.api_routes import MAX_FILTERS, row_readers
from brain.app import Settings, create_app
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.envelope import IdentityMode
from brain.core.scope import Scope
from brain.identity.lifecycle import STARTER_PACK
from brain.knowledge.columns import PRICE_LIST
from brain.knowledge.document_tools import (
    KNOWLEDGE_ENTITY,
    READ_DOCUMENT,
    SEARCH_DOCUMENTS,
    knowledge_tools,
)
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import reach_for
from brain.tools.registry import ToolRegistrationError, ToolRegistry
from brain.tools.startup import (
    BUILT_IN_ROW_ENTITIES,
    ROW_TOOL_DESCRIPTIONS,
    SOURCE_ROW_ENTITIES,
    build_registry,
    classification_for,
    every_row_classification,
    row_entities_for,
)


class _Rows:
    """A `RowSource` that answers nothing. What it returns is not what these tests are about;
    that it can be supplied at all is."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        del query
        return ()


def _row_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    """The row tools alone: the definitions naming a source, which is what the answer lane reads
    as a reader of rows. The document tools name none, which a test below holds."""
    return tuple(d.name for d in registry.definitions() if d.source)


# --------------------------------------------------------------- there is a builder
def test_the_registry_the_application_builds_comes_back_frozen() -> None:
    """A caller handed an unfrozen registry can register into it after the whole-registry
    checks have run, which is the same as not running them.

    Delete this and `build_registry` can return before `freeze`, and the duplicate-description
    rule stops applying to anything registered afterwards."""
    registry = build_registry(source="local", records=_Rows())

    assert registry.is_frozen is True
    with pytest.raises(ToolRegistrationError):
        registry.register(
            next(iter(registry)),
            lambda: None,
        )


def test_a_row_tool_is_registered_for_every_entity_that_has_a_classification() -> None:
    """The positive case, and the one that proves the builder builds rather than returns an
    empty registry that passes every other assertion here.

    Named against `BUILT_IN_ROW_ENTITIES` rather than against the number one, so adding a
    second classification does not require editing this test to keep it honest."""
    registry = build_registry(source="xero", records=_Rows())
    rows = _row_tool_names(registry)

    assert len(rows) == len(BUILT_IN_ROW_ENTITIES)
    assert rows == ("xero.read_price_list",)
    assert PRICE_LIST in BUILT_IN_ROW_ENTITIES


def test_the_source_is_part_of_every_tools_name() -> None:
    """A row tool is pinned to one source as well as one entity, because `proj.record` is
    keyed that way and two systems' record ids collide by coincidence of integers. The name
    carries it, so a catalogue holding two sources' price lists describes two tools rather
    than one ambiguous one."""
    xero = _row_tool_names(build_registry(source="xero", records=_Rows()))
    freshdesk = _row_tool_names(build_registry(source="freshdesk", records=_Rows()))

    assert xero == ("xero.read_price_list",)
    assert freshdesk == ("freshdesk.read_price_list",)
    assert not set(xero) & set(freshdesk)


def test_a_registry_built_with_no_row_source_offers_no_row_tools() -> None:
    """**Not a degraded registry: an honest one.** A tool that is present and cannot answer
    is worse than one that is absent, because a missing tool is a gap somebody notices and an
    empty answer is a fact somebody believes. A model that picks `read_price_list` and is told
    nothing came back reports that the company has no price list.

    Delete this and the builder can be made to register tools bound to a source it invented,
    which is a second path to data with its own idea of what may be seen."""
    registry = build_registry(source="local")

    assert len(registry) == 0
    assert registry.is_frozen is True


def test_every_registered_entity_has_a_description_written_for_it() -> None:
    """`ToolRegistry.validate` refuses two tools sharing a description, folded and stripped of
    punctuation, and that is a property of a pair rather than of one tool. Keeping the
    descriptions in one mapping makes a collision visible while it is being written instead of
    at the freeze that follows.

    A source's own entities are held to the same rule by building the registry for that source,
    which is where a missing description raises and a colliding one is refused.

    Delete this and a new classification is added with no description, and the builder fails
    with a KeyError at startup rather than at the edit."""
    for classification in BUILT_IN_ROW_ENTITIES:
        assert classification.entity in ROW_TOOL_DESCRIPTIONS
        assert ROW_TOOL_DESCRIPTIONS[classification.entity].strip()

    for source, owned in SOURCE_ROW_ENTITIES.items():
        registry = build_registry(source=source, records=_Rows())
        for classification in owned:
            definition = registry.get(f"{source}.read_{classification.entity}").definition
            assert definition.description.strip()


def test_a_registered_row_tool_declares_service_identity_and_carries_its_pin() -> None:
    """The rule the registry checks and the reason the scope is passed rather than omitted. A
    projected row was fetched under somebody else's credentials long before the query runs, so
    the source is enforcing nothing now and ours are the only permissions there are.
    `assert_service_tool_is_scoped` refuses that combination unscoped, and passing the tool's
    own pin is what satisfies it honestly rather than with an unrestricted scope.

    Delete this and the tool can be registered with `IdentityMode.REQUESTER`, which claims the
    source is checking permissions it is not."""
    registry = build_registry(source="local", records=_Rows())
    definition = registry.get("local.read_price_list").definition

    assert definition.identity_mode is IdentityMode.SERVICE
    assert definition.source == "local"
    assert definition.required_capability == "read:price_list"


# --------------------------------------------------------------- the application calls it
def test_the_application_builds_the_registry_during_startup() -> None:
    """**The whole point of the module.** Every rule in `brain.tools.registry` runs at
    registration and `freeze` runs the rest, and none of it ran anywhere until a process
    built one.

    Asserted through the real lifespan rather than by calling the builder again, because
    calling the builder proves the builder works and proves nothing about whether anybody
    calls it. Delete this and the wiring can be removed with every other test here green."""
    from fastapi.testclient import TestClient

    app = create_app(Settings(env="development", run_migrations=False))

    with TestClient(app):
        registry = app.state.tools

        assert isinstance(registry, ToolRegistry)
        assert registry.is_frozen is True
        assert app.state.ready["tools"] is True


def test_the_source_the_application_uses_comes_from_configuration() -> None:
    """`RowTool` refuses an empty source, so this cannot be left unset and discovered at
    startup on a fresh install. It is a real setting with a real default rather than a
    placeholder that would fail the first time somebody deployed without it."""
    assert Settings().tool_source == "local"
    assert Settings(tool_source="xero").tool_source == "xero"


# --------------------------------------------------------------- what a source brings
def test_the_demos_source_registers_its_own_entities_beside_the_built_ins() -> None:
    """**The positive half of where the demo is registered.** An install configured to read
    the demo's source gets a row tool for every entity the demo stores records of, pinned to
    that source, and the price list as well.

    The entities are compared with the rows the demo writes rather than with its
    classifications, so a classification that forgot an entity is a missing tool here and not
    the same omission on both sides of an equality.

    Delete this and the demo's entities can stop being registered anywhere, and the console
    answers nobody's question about the seeded company, which is where it was on 2026-09-14."""
    registry = build_registry(source=demo.DEMO_SOURCE, records=_Rows())
    stored = {str(row["entity"]) for row in demo.record_rows()}
    built_in = {c.entity for c in BUILT_IN_ROW_ENTITIES}
    rows = [d for d in registry.definitions() if d.entity != KNOWLEDGE_ENTITY]

    assert {d.entity for d in registry.definitions()} == stored | built_in | {KNOWLEDGE_ENTITY}
    assert {d.source for d in rows} == {demo.DEMO_SOURCE}
    assert len(registry) == len(row_entities_for(demo.DEMO_SOURCE)) + len(knowledge_tools(_Rows()))


def test_no_install_reading_another_source_registers_anything_the_demo_brings() -> None:
    """**The half that keeps the demo out of the template.** The demo's entities are an invented
    company's columns, and an install reading its own system must not carry them: not as a
    classification governing its own `client`, and not as tools that read nothing. Asserted for
    the source an install reads by default, taken from the application's settings rather than
    written here, and for two others.

    The demo's source is asserted not to be that default too, because that is the one edit that
    would register the demo on every install while each comparison above moved with it.

    Delete this and `row_entities_for` can hand the demo's entities to every source, which is
    `BUILT_IN_ROW_ENTITIES` widened by another route."""
    built_in = {c.entity for c in BUILT_IN_ROW_ENTITIES} | {KNOWLEDGE_ENTITY}
    for source in (Settings().tool_source, "xero", "laravel"):
        registry = build_registry(source=source, records=_Rows())
        assert {d.entity for d in registry.definitions()} == built_in, source

    assert Settings().tool_source != demo.DEMO_SOURCE


# --------------------------------------------------------------- the document plane
def test_the_document_plane_is_registered_on_every_install_with_rows_whatever_it_reads() -> None:
    """**The half that lets a knowledge template start.** Ten catalogue templates name
    `knowledge.read` or `knowledge.search`, and until 2026-09-14 no install registered anything
    they could bind to, so every one of them was refused by the gate. The plane is the
    product's own, so it is asserted for the source an install reads by default, another
    system, and the demo: a document tool registered for one source is the demo's mistake made
    in the other direction.

    Delete this and the document tools can stop being registered, and every knowledge template
    badges itself incomplete on every install."""
    for source in (Settings().tool_source, "xero", demo.DEMO_SOURCE):
        names = build_registry(source=source, records=_Rows()).names()
        assert {SEARCH_DOCUMENTS, READ_DOCUMENT} <= set(names), source


def test_a_document_tool_asks_for_exactly_the_grant_that_opens_the_plane() -> None:
    """Asserted by what the requirement does rather than by how it is spelled: a caller holding
    only a document tool's required capability has a reach on the plane, and it is one a
    joiner's starter pack gives them. A tool asking for `read:knowledge.document` would be shown
    to people whose reach is None, and would retrieve nothing for all of them.

    Delete this and the requirement can drift to a field capability, and the tool appears in
    catalogues and answers nobody."""
    registry = build_registry(source="local", records=_Rows())

    for name in (SEARCH_DOCUMENTS, READ_DOCUMENT):
        needed = registry.get(name).capability
        holder = EntitlementSet(
            principal_id="u_reader", grants=(Grant(capability=needed, scope=Scope.unrestricted()),)
        )
        assert reach_for(holder, departments=()) is not None, name
        assert needed in STARTER_PACK.capabilities, name


def test_the_answer_lane_reads_no_document_tool_as_a_reader_of_rows() -> None:
    """`row_readers` hands the answer lane a reader per source and entity, and it reads a
    definition naming a source as a row tool. A document tool read that way would be handed a
    `RowRequest` and put `knowledge` into the sources an answer says it covered.

    Delete this and a document tool can be given a source, and the answer lane starts calling it
    as a table of rows."""
    registry = build_registry(source="local", records=_Rows())

    assert set(row_readers(registry)) == {("local", "price_list")}


def test_every_entity_is_classified_by_one_owner() -> None:
    """`classification_for` is keyed on the entity alone, and that has one answer only while no
    two owners classify one entity: the product's built-ins and every source's own. The day a
    second source classifies `client` this fails, and the lookup has to take the source, which
    is the change `fast_lane.entities_served` needed on 2026-09-14.

    Delete this and two sources' classifications of one entity make the records route redact one
    system's rows by the other's policy, chosen by the order two tuples were concatenated in."""
    entities = [one.entity for one in every_row_classification()]
    owned = {c.entity for classifications in SOURCE_ROW_ENTITIES.values() for c in classifications}

    assert len(entities) == len(set(entities)), entities
    assert set(entities) == {c.entity for c in BUILT_IN_ROW_ENTITIES} | owned


def test_an_entity_a_source_brings_is_answered_with_that_sources_classification() -> None:
    """The lookup the records route and the answer lane make. An entity the demo brings is
    classified by the demo's classification, a built-in by the built-in, and an entity nobody
    classifies by nothing, which the routes turn into the 404 an ungranted entity gets.

    Delete this and `classification_for` can go back to reading the built-ins alone, and the
    demo's tools are registered with no policy to redact them by, which the answer lane treats
    as a misconfigured install for every question."""
    for classification in demo.row_classifications():
        assert classification_for(classification.entity) == classification
    assert classification_for(PRICE_LIST.entity) == PRICE_LIST
    assert classification_for("no_such_entity") is None


def test_every_column_of_every_classified_entity_can_be_filtered_on() -> None:
    """`tests/unit/test_api_routes.py` holds the filter bound to the widest built-in entity, and
    a source's own entities are served by the same route, so the same bound has to reach every
    column of theirs. Measured against the route's own `MAX_FILTERS`.

    Delete this and a source can bring an entity with more columns than a caller may name in one
    filter, and a column somebody is entitled to read is unfilterable by everybody."""
    widest = max(len(c.columns()) for c in every_row_classification())

    assert widest <= MAX_FILTERS


def test_an_install_that_has_declared_no_embedding_weights_searches_its_documents_by_text() -> None:
    """**No revision, no embedder.** Every install until its owner declares which weights its
    inference server holds registers the search tool with an empty vector leg, and builds no
    client to a server that may not exist.

    Delete this and every process can build an embedding client at start whatever the install
    has said, and on the `lite` profile, which deploys no inference server, every knowledge
    search is a degraded answer."""
    from brain.knowledge.embed_policy import REVISION_SETTING
    from brain.tools.startup import question_embedder

    assert question_embedder({}) is None
    assert question_embedder({REVISION_SETTING: "unset"}) is None


def test_an_install_that_has_declared_its_weights_embeds_questions_with_them() -> None:
    """The positive sibling. The embedder carries the declared revision and a client pointed at
    the declared endpoint, and nothing is dialled by building it.

    Delete this and `question_embedder` can return None for everything, which is an install that
    declared its weights and whose knowledge search never runs its vector leg."""
    from brain.knowledge.embed_policy import ENDPOINT_SETTING, REVISION_SETTING
    from brain.ops.inference_client import InferenceEmbeddingClient, embed_url
    from brain.tools.startup import question_embedder

    endpoint = "http://192.0.2.9:8080"
    built = question_embedder({REVISION_SETTING: "v1.0.0", ENDPOINT_SETTING: endpoint})

    assert built is not None
    assert built.revision == "v1.0.0"
    assert isinstance(built.service, InferenceEmbeddingClient)
    assert built.service.url == embed_url(endpoint)
