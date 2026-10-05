"""Whether a reader reaches a record on the review screen, and what a card calls it.

Task ids: M14.6.4
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES
from brain.resolution.canonical import EntityType, SourceRef
from brain.resolution.review_store import label_of, seen_by

AT = datetime(2019, 3, 4, 12, tzinfo=UTC)
COMPANY = SourceRef("hubspot", "hubspot_company", "c1")
FIELDS = {"name": "Northwind Trading", "domain": "nw.example", "portal": "1"}


def reach_of(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reviewer",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def everything_on(source: str, entity: str) -> tuple[str, ...]:
    for one in CONNECTOR_ROW_ENTITIES[source]:
        if one.entity == entity:
            return tuple(sorted({rule.required_capability.value for rule in one.rules}))
    return ()


def test_a_reader_holding_the_records_rules_reaches_it_and_sees_its_name() -> None:
    """The positive half: the connector's own rules granted, the record is reached and its card
    names it by the field the connector names it by.

    Delete this and the screen could show no pair to anybody and still pass its refusals."""
    view = seen_by(reach_of(*everything_on("hubspot", "hubspot_company")), COMPANY, FIELDS, AT)

    assert view is not None
    assert label_of(COMPANY, view) == "Northwind Trading"


def test_a_reader_holding_nothing_of_a_record_and_a_record_gone_are_reached_by_nobody() -> None:
    """No grant, a record that has gone, and an entity no connector classifies are all unreached.

    Delete this and a reviewer is shown a record they could not ask about."""
    everything = reach_of(*everything_on("hubspot", "hubspot_company"))

    assert seen_by(reach_of(), COMPANY, FIELDS, AT) is None
    assert seen_by(everything, COMPANY, None, AT) is None
    assert seen_by(everything, SourceRef("hubspot", "nothing_classified", "1"), FIELDS, AT) is None


def test_a_record_whose_name_the_reader_may_not_see_is_called_by_its_id() -> None:
    """A reader who reaches the record and not its name field sees its source id instead.

    Delete this and a card names a record by a field the reader is not allowed to read."""
    without_name = tuple(
        one for one in everything_on("hubspot", "hubspot_company") if not one.endswith(".name")
    )
    view = seen_by(reach_of(*without_name), COMPANY, FIELDS, AT)

    assert view is not None
    assert label_of(COMPANY, view) == "c1"


def test_a_record_whose_name_is_blank_is_called_by_its_id() -> None:
    """A name field the reader sees and that says nothing is no name.

    Delete this and a card can name a record with an empty string."""
    view = seen_by(
        reach_of(*everything_on("hubspot", "hubspot_company")),
        COMPANY,
        {**FIELDS, "name": ""},
        AT,
    )

    assert view is not None
    assert label_of(COMPANY, view) == "c1"


@pytest.mark.needs_db
def test_a_reviewed_merge_of_two_records_already_one_entity_merges_nothing() -> None:
    """A pair whose two records already resolve to one entity is answered as merged with nothing
    merged, rather than as a merge of an entity into itself.

    Delete this and deciding a pair somebody already joined some other way fails the request."""
    import asyncio
    import json

    from brain.db import normalise_database_url
    from brain.resolution.guardrails import ReviewItem
    from brain.resolution.merge import MoneyBearing, MoneyCheck, ReviewedMerge
    from brain.resolution.merge_store import merge_entities
    from brain.resolution.registry_store import StoredRegistry
    from brain.resolution.review_store import StoredItem, merge_reviewed
    from brain.session import make_app_engine, make_session_factory
    from brain.tables.resolution_review import ReviewOrigin, ReviewState
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head

    one, two = COMPANY, SourceRef("hubspot", "hubspot_company", "c2")
    with at_head("brain_review_store") as url:
        for ref in (one, two):
            sql(
                url,
                "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at)"
                " VALUES (%s, %s, %s, %s::jsonb, %s)",
                ref.source,
                ref.entity,
                ref.source_id,
                json.dumps({"name": f"Northwind {ref.source_id}"}),
                AT,
            )

        async def go() -> bool:
            engine = make_app_engine(normalise_database_url(url))
            try:
                sessions = make_session_factory(engine)
                await StoredRegistry(sessions).register([one, two], pepper="ab" * 32, now=AT)
                [(a,), (b,)] = sql(url, "SELECT entity_id FROM er.link ORDER BY source_id")
                none = MoneyBearing.NO_FINANCIAL_RECORDS_FOUND
                await merge_entities(
                    sessions,
                    survivor_id=a,
                    merged_id=b,
                    authority=ReviewedMerge(
                        reviewer_id="u_first",
                        review_ref="elsewhere",
                        money=MoneyCheck(left=none, right=none),
                    ),
                    at=AT,
                    trace_id="t",
                    reason="joined elsewhere",
                )
                stored = StoredItem(
                    item=ReviewItem(item_id="rev_1", left=one, right=two),
                    entity_type=EntityType.COMPANY,
                    origin=ReviewOrigin.CASCADE,
                    stage=4,
                    reason="r",
                    state=ReviewState.OPEN,
                    raised_at=AT,
                    decided_by=None,
                    decided_at=None,
                )
                return await merge_reviewed(
                    sessions,
                    stored,
                    reviewer_id="u_second",
                    at=AT,
                    ent_hash="0" * 32,
                    trace_id="t",
                    reason="the same",
                )
            finally:
                await engine.dispose()

        merged = asyncio.run(go())
        assert merged is False
        assert sql(url, "SELECT count(*) FROM er.merge") == [(1,)]
