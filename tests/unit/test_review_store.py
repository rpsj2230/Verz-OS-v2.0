"""Whether a reader reaches a record on the review screen, and what a card calls it.

Task ids: M14.6.4
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES
from brain.resolution.canonical import SourceRef
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
