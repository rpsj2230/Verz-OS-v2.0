"""A connector for a new API as data: judged, compiled, and laid under the shipped ones.

`brain.ops.custom_connector` judges a definition and compiles it into the declaration a shipped
connector makes; `brain.ops.connector_catalogue` lays the approved ones beneath the shipped ones and
every list the product reads follows. These tests hold both halves without a database: the made-up
API of the install check, refused in each way it can be wrong and accepted when it is right, and the
lists, the worker's readings, the ceilings and the registry seeing it only while it is approved.

Task ids: M11.7.8
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.connectors.declaration import CredentialShape, KeyScheme, SettingRefusedError, shipped
from brain.connectors.rest import RestSpecError, load_spec
from brain.core.field_policy import Classification
from brain.knowledge.rows import RowQuery
from brain.ops import connector_catalogue
from brain.ops.acceptance_checks_custom_connector import made_up_definition, made_up_document
from brain.ops.connectable import CONNECTABLE, connectable, manifest_for
from brain.ops.connector_sync import READINGS
from brain.ops.custom_connector import (
    AN_UNMEASURED_SOURCE_IS_NOT_OFFERED,
    MAX_DOCUMENT_BYTES,
    CustomConnectorError,
    CustomDefinition,
    declaration_of,
    parse_document,
    problems,
)
from brain.ops.limits import connector_ceiling
from brain.ops.secrets import SecretRef, VaultRole
from brain.tools.startup import build_registry

NAME, ENTITY, DEPARTMENT = "widgets_api", "widgets_api_widget", "finance"
TOOL = f"{NAME}.read_{ENTITY}"

#: Fixed far from any wall clock, because nothing here is about the present.
SEEN = datetime(2019, 3, 1, tzinfo=UTC)


class _Resolver:
    """Every name answers a public address, so `assert_fetchable` admits the made-up server."""

    def resolve(self, host: str) -> list[str]:
        del host
        return ["93.184.216.34"]


class _Rows:
    """A `RowSource` that answers nothing; that one is supplied at all is what matters here."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        del query
        return ()


def definition(**changes: Any) -> CustomDefinition:
    """The install check's made-up API, as the routes turn its form into a definition."""
    from brain.custom_connector_routes import definition_of

    body = made_up_definition(NAME, ENTITY, DEPARTMENT)
    return replace(definition_of(body, json.loads(body.document)), **changes)


def codes(found: Sequence[Any]) -> list[str]:
    return [one.code for one in found]


@pytest.fixture(autouse=True)
def _nothing_installed() -> Iterator[None]:
    """Every test starts and ends with no reviewed connector served by the process."""
    connector_catalogue.install({})
    yield
    connector_catalogue.install({})


# ------------------------------------------------------------------------ the judgement
def test_the_made_up_api_is_judged_right_and_compiles_to_a_declaration_like_a_shipped_one() -> None:
    """The positive case every refusal below is a sibling of: a whole definition has no problem,
    and its declaration has a form, a reading, a live lookup, Ask rows and its ceiling. Delete this
    and a judgement that refuses everything passes every refusal test."""
    one = definition()
    assert problems(one, resolver=_Resolver()) == ()
    declared = declaration_of(one)
    assert declared.name == NAME
    assert declared.console is not None
    assert declared.reading is not None
    assert declared.reading.entities() == (ENTITY,)
    assert declared.live is not None
    assert declared.live.entities() == (ENTITY,)
    assert declared.ask is not None
    assert declared.ceiling is not None
    assert (declared.ceiling.name, declared.ceiling.per_minute) == (NAME, 60)


def test_a_definition_with_no_ceiling_is_refused_and_cannot_be_compiled() -> None:
    """`AN_UNMEASURED_SOURCE_IS_NOT_OFFERED`. Delete this and an API nobody measured is stored,
    offered and read against no limit at all."""
    bare = definition(ceiling=None)
    found = problems(bare, resolver=_Resolver())
    assert [(one.field, one.code, one.message) for one in found] == [
        ("ceiling", "missing", AN_UNMEASURED_SOURCE_IS_NOT_OFFERED)
    ]
    with pytest.raises(CustomConnectorError):
        declaration_of(bare)


def test_an_external_reference_is_refused_even_where_no_operation_reaches_it() -> None:
    """A `$ref` to another address anywhere in the document is refused at submit, before any
    schema walks to it. Delete this and a pasted document carries a fetch a reviewer approved
    without seeing, which `load_spec` would only refuse on the day a schema reached it."""
    document = made_up_document()
    document["components"]["schemas"]["Elsewhere"] = {"$ref": "https://evil.example/schema.json"}
    with pytest.raises(CustomConnectorError) as refused:
        parse_document(json.dumps(document))
    assert codes(refused.value.problems) == ["external_reference"]
    assert codes(problems(definition(document=document), resolver=_Resolver())) == [
        "external_reference"
    ]


def test_an_internal_reference_resolves_to_the_component_it_names() -> None:
    """The sibling: the made-up document's operations refer to a component and are read through
    it, the list at `data` and the one record as itself. Delete this and refusing every `$ref`
    would pass the test above."""
    document = parse_document(json.dumps(made_up_document()))
    spec = load_spec(document, resolver=_Resolver())
    assert (
        spec.operation("listWidgets").records_at,
        spec.operation("listWidgets").returns_list,
    ) == (
        "data",
        True,
    )
    assert spec.operation("getWidget").returns_list is False


def test_a_reference_that_resolves_nowhere_in_the_document_is_refused_when_read() -> None:
    """An internal pointer to nothing is refused by the loader rather than read as no schema.
    Delete this and a typo in a pointer reads as an operation with no records."""
    document = made_up_document()
    path = document["paths"]["/widgets/{widgetId}"]["get"]["responses"]["200"]["content"]
    path["application/json"]["schema"] = {"$ref": "#/components/schemas/Nowhere"}
    with pytest.raises(RestSpecError):
        load_spec(parse_document(json.dumps(document)), resolver=_Resolver())


def test_a_specification_over_the_size_cap_is_refused_before_it_is_parsed() -> None:
    """Delete this and a paste of any size is parsed into memory on the web process."""
    document = made_up_document()
    document["info"]["description"] = "x" * MAX_DOCUMENT_BYTES
    with pytest.raises(CustomConnectorError) as refused:
        parse_document(json.dumps(document))
    assert codes(refused.value.problems) == ["too_large"]
    document["info"]["description"] = "x" * 1000
    assert parse_document(json.dumps(document))["info"]["description"] == "x" * 1000


def test_an_operation_that_is_not_a_get_is_refused() -> None:
    """Read-only by construction. Delete this and a definition can name a write as its list."""
    document = made_up_document()
    document["paths"]["/widgets"]["post"] = document["paths"]["/widgets"].pop("get")
    found = problems(definition(document=document), resolver=_Resolver())
    assert codes(found) == ["list_not_a_list"]


def test_a_name_a_shipped_connector_has_is_refused_and_another_is_accepted() -> None:
    """`A_SHIPPED_NAME_ALWAYS_WINS`, at submit. Delete this and a definition named like a shipped
    connector is stored and silently shadowed, or worse."""
    taken = frozenset(shipped())
    assert codes(problems(definition(name="xero"), resolver=_Resolver(), taken_names=taken)) == [
        "taken"
    ]
    assert problems(definition(), resolver=_Resolver(), taken_names=taken) == ()


def test_an_entity_another_source_has_is_refused() -> None:
    """Two sources of one entity would share its capabilities. Delete this and a grant for one
    source's records reaches the other's."""
    found = problems(definition(), resolver=_Resolver(), taken_entities=frozenset({ENTITY}))
    assert codes(found) == ["entity_taken"]


def test_a_field_kept_nowhere_with_no_one_record_operation_is_refused() -> None:
    """`EVERY_FIELD_IS_DECIDED_BY_THE_PERSON_WHO_MAPPED_IT`. Delete this and the price is mapped,
    classified, approved and answerable by nothing."""
    one = definition()
    entity = replace(one.entities[0], one_operation=None)
    assert "read_nowhere" in codes(problems(replace(one, entities=(entity,)), resolver=_Resolver()))


def test_a_key_scheme_outside_the_three_a_definition_may_use_is_refused() -> None:
    """`A_DEFINITION_USES_A_KEY_SCHEME_THAT_EXISTS`. Delete this and a definition names the Google
    scheme with no token scope, and the worker's run is asked to mint a token for nothing."""
    found = problems(
        definition(
            key_scheme=KeyScheme.GOOGLE_SERVICE_ACCOUNT, credential_shape=CredentialShape.KEY
        ),
        resolver=_Resolver(),
    )
    assert codes(found) == ["not_a_scheme"]


# ------------------------------------------------------------------------ the compiled shape
def test_a_connection_naming_another_department_than_the_reviewed_one_is_refused() -> None:
    """`THE_DEPARTMENT_IS_THE_REVIEWED_ONE`, with the reviewed one accepted beside it. Delete this
    and a connection grants a department nobody reviewed."""
    declared = declaration_of(definition())
    assert declared.console is not None
    ref = SecretRef(path=f"connector_keys/{NAME}", role=VaultRole.WORKER)
    with pytest.raises(SettingRefusedError) as refused:
        declared.console.build({"department": "sales"}, ref)
    assert refused.value.setting == "department"
    manifest = declared.console.build({"department": DEPARTMENT}, ref)
    assert [one.name for one in manifest.tools] == [TOOL]


def test_the_reading_keeps_the_kept_fields_and_never_the_one_read_live() -> None:
    """The price is mapped and classified and is not in the index row. Delete this and the
    minimal index holds a value the definition said to read live."""
    declared = declaration_of(definition())
    assert declared.reading is not None
    row = {"id": "w1", "code": "A-1", "state": "active", "price": "99.00"}
    kept = declared.reading.projected(ENTITY, row, seen_at=SEEN)
    assert kept is not None
    assert (kept.source, kept.source_id, dict(kept.fields)) == (
        NAME,
        "w1",
        {"code": "A-1", "state": "active"},
    )


def test_each_field_is_behind_its_own_capability_at_the_classification_its_submitter_chose() -> (
    None
):
    """Ask's rows are built from the mapping's classifications. Delete this and the price could be
    reached by the row's own grant, or classified by nobody."""
    declared = declaration_of(definition())
    assert declared.ask is not None
    [entity] = declared.ask.entities
    assert {
        (rule.field, rule.required_capability.value, rule.classification) for rule in entity.fields
    } == {
        ("code", f"read:{ENTITY}.code", Classification.INTERNAL),
        ("state", f"read:{ENTITY}.state", Classification.INTERNAL),
        ("price", f"read:{ENTITY}.price", Classification.RESTRICTED),
    }
    assert (declared.ask.scoped_by, entity.named_by, entity.live_only) == (
        "department",
        "code",
        ("price",),
    )


def test_the_one_record_operation_is_named_by_its_path_parameter() -> None:
    """A record is read live by its own call with the id in the path. Delete this and a live read
    lays the id into a parameter the operation does not declare and is refused every time."""
    declared = declaration_of(definition())
    assert declared.live is not None
    assert dict(declared.live.arguments_for(ENTITY, "w1")) == {"widgetId": "w1"}
    with pytest.raises(Exception, match="refused rather than escaped"):
        declared.live.arguments_for(ENTITY, "../w1")


# ------------------------------------------------------------------------ the catalogue
def test_an_unreviewed_definition_is_in_no_list_and_has_no_tool() -> None:
    """With nothing approved, the definition's name is in no list the product reads. Delete this
    and a definition is offered, read or given a tool before anybody reviewed it."""
    assert NAME not in CONNECTABLE
    assert NAME not in READINGS
    assert connector_ceiling(NAME) is None
    tools = {one.name for one in build_registry(source="local", records=_Rows()).definitions()}
    assert TOOL not in tools


def test_an_approved_definition_is_offered_read_ceilinged_and_has_a_row_tool() -> None:
    """The sibling, through `install` as `refresh` calls it: every list follows. Delete this and an
    approval reaches the table and nothing a person or an agent uses."""
    connector_catalogue.install({NAME: declaration_of(definition())})
    assert connectable(NAME).label == "Acceptance check widgets"
    assert NAME in READINGS
    ceiling = connector_ceiling(NAME)
    assert ceiling is not None
    assert ceiling.per_day == 10_000
    assert manifest_for(NAME, {"department": DEPARTMENT}).name == NAME
    tools = {one.name for one in build_registry(source="local", records=_Rows()).definitions()}
    assert TOOL in tools
    assert connector_catalogue.install({}) is True
    assert NAME not in CONNECTABLE


def test_a_shipped_name_always_wins_over_a_reviewed_one() -> None:
    """`A_SHIPPED_NAME_ALWAYS_WINS`. Delete this and a definition stored under a shipped name
    replaces the shipped connector for every reader of the catalogue."""
    impostor = replace(declaration_of(definition()), name="xero", ceiling=None)
    assert connector_catalogue.install({"xero": impostor}) is False
    assert connector_catalogue.declarations()["xero"] is shipped()["xero"]


def test_an_overlay_is_seen_in_its_own_context_and_nowhere_after() -> None:
    """What a check lays over the catalogue is its own. Delete this and an acceptance check's
    rolled-back approval could be offered to a request served beside it."""
    with connector_catalogue.overlaid({NAME: declaration_of(definition())}):
        assert NAME in CONNECTABLE
        assert NAME in READINGS
    assert NAME not in CONNECTABLE
    assert NAME not in READINGS
