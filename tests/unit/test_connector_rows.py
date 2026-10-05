"""What a connected source's records answer on Ask: classifications, questions and the registry.

The classifications are held against the connectors' own declarations rather than against this
module: every field a source keeps or reads live is classified, by the capability the connector
itself names where it names one, and the column its visibility predicate tests is readable by
whoever reaches the row. The questions are held to the connected sources alone. The registry an
agent install reads is held to the connections: serving under this release's declaration and
quarantined under another.

Task ids: M11.6.5, M11.6.2, M11.4.9, M11.1.6
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain.connectors import freshdesk, xero
from brain.connectors.ask import AskEntity, AskRows, AskRowsError, each_behind_its_own
from brain.connectors.declaration import shipped
from brain.connectors.registry import ConnectorState
from brain.knowledge.connector_rows import (
    ANSWERED_BY_PASSAGES,
    CONNECTOR_ROW_DESCRIPTIONS,
    CONNECTOR_ROW_ENTITIES,
    NAMED_BY,
    SCOPED_BY,
    connected_questions,
)
from brain.tools.startup import SOURCE_ROW_ENTITIES, connector_row_sources

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def test_the_maps_are_read_off_every_connector_s_own_declaration() -> None:
    """`THE_ROWS_ARE_READ_OFF_THE_DECLARATIONS`. Every connector declaring classified Ask rows is in
    every map, with its own scope field, entities, descriptions and named fields, and every one
    declaring passages is a passage source, read here off the raw declarations rather than the
    maps. Xero's invoice, HubSpot's unnamed contact and Lark Wiki's passages are the anchors, so an
    assembly that found nothing or dropped one connector fails.

    Delete this and the assembly can drop a connector, or a field the connector names, and Ask
    tells a reader of it nothing was found, which is the answer for a record that does not exist."""
    declared = {name: one.ask for name, one in shipped().items() if one.ask is not None}
    classified = {name for name, rows in declared.items() if rows.entities}

    assert set(CONNECTOR_ROW_ENTITIES) == set(SCOPED_BY) == set(CONNECTOR_ROW_DESCRIPTIONS)
    assert set(CONNECTOR_ROW_ENTITIES) == classified
    assert {name for name, rows in declared.items() if rows.by_passages} == ANSWERED_BY_PASSAGES
    for name in classified:
        rows = declared[name]
        assert SCOPED_BY[name] == rows.scoped_by
        assert [one.entity for one in CONNECTOR_ROW_ENTITIES[name]] == [
            one.entity for one in rows.entities
        ]
        for entity in rows.entities:
            assert CONNECTOR_ROW_DESCRIPTIONS[name][entity.entity] == entity.description
            assert NAMED_BY.get((name, entity.entity), "") == entity.named_by
    assert {"xero", "freshdesk", "hubspot"} <= classified
    assert NAMED_BY[(xero.CONNECTOR_NAME, xero.ENTITY_INVOICE)] == "invoice_number"
    assert ("hubspot", "hubspot_contact") not in NAMED_BY
    assert "lark_wiki" in ANSWERED_BY_PASSAGES
    assert "lark_wiki" not in CONNECTOR_ROW_ENTITIES


def test_ask_rows_are_either_classified_or_passages_and_name_only_fields_they_classify() -> None:
    """Each refusal beside the declaration it narrows, which builds. Delete this and a connector can
    declare rows that are both classified and passages, or name a record by a field it never
    classifies, and the question shape built over it matches nothing."""
    fields = each_behind_its_own("widget", ("name", "status"))
    one = AskEntity(entity="widget", fields=fields, description="Look up widgets", named_by="name")

    assert AskRows(scoped_by="department", entities=(one,)).entities == (one,)
    assert AskRows(by_passages=True).by_passages
    with pytest.raises(AskRowsError):
        AskRows(scoped_by="department", entities=(one,), by_passages=True)
    with pytest.raises(AskRowsError):
        AskRows()
    with pytest.raises(AskRowsError):
        AskRows(entities=(one,))
    with pytest.raises(AskRowsError):
        AskEntity(entity="widget", fields=fields, description="Look up widgets", named_by="colour")
    with pytest.raises(AskRowsError):
        AskEntity(entity="gadget", fields=fields, description="Look up gadgets")
    with pytest.raises(AskRowsError):
        AskEntity(entity="widget", fields=fields, description="Look up", live_only=("colour",))


def test_every_field_xero_classifies_is_classified_by_the_capability_xero_names() -> None:
    """Held against `xero.XERO_FIELD_RULES`. Delete this and the Ask answer could require a
    different capability for an invoice's amount than the connector's own policy says, which is a
    second place deciding who may be told it."""
    for classification in CONNECTOR_ROW_ENTITIES[xero.CONNECTOR_NAME]:
        declared = {
            rule.field: (rule.required_capability, rule.classification)
            for rule in xero.XERO_FIELD_RULES
            if rule.entity == classification.entity
        }
        compiled = {
            rule.column: (rule.required_capability, rule.classification)
            for rule in classification.rules
            if rule.column != SCOPED_BY[xero.CONNECTOR_NAME]
        }
        assert compiled == declared


def test_every_field_freshdesk_keeps_or_reads_live_is_classified_behind_its_own_capability() -> (
    None
):
    """Held against the fields the Freshdesk index keeps and the body its live read returns. Delete
    this and a field can go unclassified, withheld from everybody with nothing saying why, or the
    ticket's body can be answered under the row's capability alone."""
    [ticket] = CONNECTOR_ROW_ENTITIES[freshdesk.FRESHDESK]
    kept = set(freshdesk.projected_field_names())
    columns = {rule.column: rule.required_capability.value for rule in ticket.rules}
    read = kept | {freshdesk.LIVE_BODY_FIELD}
    assert set(columns) == read | {SCOPED_BY[freshdesk.FRESHDESK]}
    for name in read:
        assert columns[name] == f"read:ticket.{name}"


def test_the_column_a_source_s_visibility_tests_is_read_by_whoever_reaches_the_row() -> None:
    """`THE_COLUMN_A_SCOPE_TESTS_IS_READ_BY_WHOEVER_REACHES_THE_ROW`, measured on a ticket: a
    reader granted tickets in one department was answered nothing, because the record had no
    department for the redactor to judge the grant against. Delete this and every department-scoped
    reader of a connected source is told nothing again."""
    for source, classifications in CONNECTOR_ROW_ENTITIES.items():
        for classification in classifications:
            rule = classification.rule_for(SCOPED_BY[source])
            assert rule is not None
            assert rule.required_capability.value == f"read:{classification.entity}"


def test_every_connected_source_s_entities_are_registered_where_the_application_builds_tools() -> (
    None
):
    """Delete this and a connector's classifications can be written and never filed, which is
    where the install stood before: nothing reached a connected source from Ask."""
    for source, classifications in CONNECTOR_ROW_ENTITIES.items():
        assert SOURCE_ROW_ENTITIES[source] == classifications
        assert source in connector_row_sources()


def test_only_a_connected_source_contributes_questions_and_each_is_keyed_on_its_named_field() -> (
    None
):
    """`A_SOURCE_NOBODY_CONNECTED_ASKS_NOTHING`, and the positive case beside it. Delete this and a
    source nobody connected answers "nothing found" to a question about it, which says the product
    knows the source exists, or a connected one contributes nothing."""
    assert connected_questions(()) == ()
    assert connected_questions(["lark_base"]) == ()
    xero_only = connected_questions([xero.CONNECTOR_NAME])
    assert {rule.source for rule in xero_only} == {xero.CONNECTOR_NAME}
    for rule in xero_only:
        assert rule.match_field == NAMED_BY[(rule.source, rule.entity)]
        assert rule.answer_field != rule.match_field
    both = connected_questions([xero.CONNECTOR_NAME, freshdesk.FRESHDESK])
    assert {rule.source for rule in both} == {xero.CONNECTOR_NAME, freshdesk.FRESHDESK}
    assert len({rule.rule_id for rule in both}) == len(both)


def test_the_answer_route_reads_its_connected_questions_from_the_connections_it_can_read() -> None:
    """A process with no database contributes no question, rather than failing the question.
    Delete this and a process started without a database raises on every Ask."""
    from brain.api_routes import connected_questions_of

    assert asyncio.run(connected_questions_of(SimpleNamespace())) == ()


class _Stored:
    """`StoredConnections.connected` over connections the test holds."""

    def __init__(self, connections: list[Any]) -> None:
        self.connections = connections

    async def connected(self) -> tuple[Any, ...]:
        return tuple(self.connections)


def test_an_agent_install_reads_a_connected_source_as_serving_and_a_changed_one_as_quarantined(
    monkeypatch: Any,
) -> None:
    """`CONNECTED_IS_WHAT_AN_AGENT_INSTALL_READS`. Until this, the registry an agent install read
    was always empty, so every agent needing a source was told it was not installed whatever the
    Connectors screen showed. Delete this and that can return, or an agent can be told a source
    serves under a declaration nobody agreed to."""
    import brain.agent_lifecycle_routes as lifecycle
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import Connection

    settings = {"tenant_id": "4f3f0a36-1e0c-4a5b-9d51-4c1f7c9b2a10"}
    current = manifest_digest(manifest_for(xero.CONNECTOR_NAME, settings))
    agreed = Connection(
        connector=xero.CONNECTOR_NAME,
        settings=settings,
        digest=current,
        connected_by="u_admin",
        connected_at=LONG_AGO,
    )
    changed = Connection(
        connector=freshdesk.FRESHDESK,
        settings={freshdesk.DOMAIN_SETTING: "a.freshdesk.com", freshdesk.DEPARTMENT_SETTING: "web"},
        digest="0" * 64,
        connected_by="u_admin",
        connected_at=LONG_AGO,
    )
    monkeypatch.setattr(lifecycle, "StoredConnections", lambda sessions: _Stored([agreed, changed]))
    monkeypatch.setattr(lifecycle, "sessions_of", lambda request: object())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    registry = asyncio.run(lifecycle.connectors_of(request))  # type: ignore[arg-type]

    assert registry.get(xero.CONNECTOR_NAME).state is ConnectorState.ENABLED
    assert registry.get(freshdesk.FRESHDESK).state is ConnectorState.QUARANTINED
    assert registry.serving() == (xero.CONNECTOR_NAME,)
    monkeypatch.setattr(lifecycle, "sessions_of", lambda request: None)
    assert len(asyncio.run(lifecycle.connectors_of(request))) == 0  # type: ignore[arg-type]


def test_hubspot_is_asked_by_a_company_or_deal_name_and_its_amount_is_confidential() -> None:
    """HubSpot on Ask since 2026-09-30: its companies and deals are asked about by the name a
    person knows them by, its contacts by no name at all (a contact is kept without one), and the
    deal's amount is CONFIDENTIAL behind `read:hubspot_deal.amount`, as HubSpot's own rules say.
    Delete this and HubSpot can fall back to being read and asked about by nothing, or a deal's
    amount can be told under an INTERNAL grant."""
    from brain.connectors import hubspot
    from brain.core.field_policy import Classification

    rules = connected_questions([hubspot.CONNECTOR_NAME])
    assert {rule.entity for rule in rules} == {hubspot.ENTITY_CLIENT, hubspot.ENTITY_DEAL}
    for rule in rules:
        assert rule.match_field == NAMED_BY[(rule.source, rule.entity)]
    [deal] = [one for one in CONNECTOR_ROW_ENTITIES["hubspot"] if one.entity == hubspot.ENTITY_DEAL]
    amount = deal.rule_for("amount")
    assert amount is not None
    assert (amount.required_capability.value, amount.classification) == (
        "read:hubspot_deal.amount",
        Classification.CONFIDENTIAL,
    )
    assert deal.rule_for("portal_id") is not None
