"""The read that finds a cited document's item, held to what it asks and what it builds.

A stand-in `RowSource` records every statement it is handed, so what the read asks is read off
the statement rather than assumed. Whether the policy then narrows it is
`tests/unit/test_badge_store_db.py`'s question, on PostgreSQL as the application role.

Task ids: M7.4.7
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.badge_store import (
    ITEM,
    NO_BODY_READ,
    StoredItems,
    item_lookup_of,
    item_of,
    items_query,
)
from brain.knowledge.item import KnowledgeState
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import KNOWLEDGE_READ, Reach, session_settings
from brain.knowledge.visibility import Visibility

#: `postgresql.dialect()` is untyped, so the dialect is taken from an engine, as
#: `tests/unit/test_document_tools.py` takes it.
POSTGRES = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far from any wall clock; nothing here is about the present.
NOW = datetime(2099, 6, 1, 9, 0, tzinfo=UTC)

READER = EntitlementSet(
    principal_id="p_reader",
    grants=(Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=Scope()),),
)
NOBODY = EntitlementSet(principal_id="p_nobody")


def a_row(**changed: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "item_id": "doc_handbook",
        "title": "Handbook",
        "owner_id": "p_owner",
        "visibility": "department",
        "department": "web",
        "state": "published",
        "verified_by": "p_steward",
        "verified_at": NOW - timedelta(days=30),
        "review_by": NOW + timedelta(days=300),
        "supersedes": None,
        "kind": None,
    }
    row.update(changed)
    return row


class Source:
    """A `RowSource` answering the departments query and then the items query, recording both."""

    def __init__(self, *items: Mapping[str, Any]) -> None:
        self.items = items
        self.asked: list[RowQuery] = []

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.asked.append(query)
        if query.columns == ("slug",):
            return [{"slug": "web"}, {"slug": "finance"}]
        return list(self.items)


def sql(query: RowQuery) -> str:
    return str(query.statement.compile(dialect=POSTGRES))


def test_the_items_are_read_under_the_readers_own_settings() -> None:
    """**The wall.** The statement carries the settings `know.item`'s policy reads for this reader,
    so the policy decides what comes back exactly as it decides which passages did.

    Delete this and the read runs with no settings, which the policy answers with company items
    only, and a department's verified documents lose their badges for the people in it."""
    reach = Reach(principal_id="p_reader", departments=("web",))
    query = items_query(["doc_handbook"], reach=reach)

    assert [str(one) for one in query.settings] == [str(one) for one in session_settings(reach)]
    assert f"FROM {ITEM.schema}.{ITEM.name}" in sql(query)
    assert "item_id IN" in sql(query)
    assert not query.certainly_empty


def test_the_read_asks_for_the_cited_documents_and_only_those() -> None:
    """The references travel as the statement's bound values, and nothing else is asked.

    Delete this and the read can widen to every item the reader reaches, which reads items for
    documents no answer cited."""
    source = Source(a_row())
    asyncio.run(StoredItems(source).items(["doc_handbook"], entitlement=READER, now=NOW))

    (_, asked) = source.asked
    bound = asked.statement.compile(dialect=POSTGRES).params
    assert sorted(value for value in bound.values() if isinstance(value, list | tuple)) == [
        ["doc_handbook"]
    ]


def test_no_cited_document_means_no_read_at_all() -> None:
    """An answer citing no document asks the database nothing.

    Delete this and every row answer costs a round trip to read no item."""
    source = Source()

    assert asyncio.run(StoredItems(source).items([], entitlement=READER, now=NOW)) == ()
    assert source.asked == []


def test_a_reader_with_no_read_of_the_knowledge_plane_reads_no_item() -> None:
    """No reach, no item: the departments are read to find the reach and nothing after it.

    Delete this and a reader with no knowledge grant can have items read on their behalf."""
    source = Source(a_row())

    assert (
        asyncio.run(StoredItems(source).items(["doc_handbook"], entitlement=NOBODY, now=NOW)) == ()
    )
    assert [one.columns for one in source.asked] == [("slug",)]


def test_a_row_becomes_the_record_a_badge_is_disclosed_from() -> None:
    """**The positive case.** The state, the verification and the place come off the row, and
    the body is the sentence saying it was not read.

    Delete this and a lookup that returns nothing passes every refusal above."""
    item = item_of(a_row())

    assert item is not None
    assert item.verified_by == "p_steward"
    assert item.visibility.level is Visibility.DEPARTMENT
    assert item.visibility.department == "web"
    assert item.state is KnowledgeState.PUBLISHED
    assert item.content == NO_BODY_READ


def test_a_row_the_record_refuses_has_no_badge_rather_than_failing_the_answer() -> None:
    """A company item published with nobody's verification is refused by `KnowledgeItem`, so it
    is left out and its citation is badged as nothing on file.

    Delete this and one malformed row fails every answer that cites its document."""
    unverified_company = a_row(
        visibility="company", department=None, verified_by=None, verified_at=None
    )
    unknown_state = a_row(state="shredded")

    assert item_of(unverified_company) is None
    assert item_of(unknown_state) is None


def test_a_company_items_department_is_not_carried_into_its_place() -> None:
    """Only a department item names a department in its place, so a stray column on a company
    row cannot make a departmental verifier grant admit it.

    Delete this and `verification._place` can be matched against a department the item is not
    stored under."""
    item = item_of(a_row(visibility="company", department="web"))

    assert item is not None
    assert item.visibility.department == ""


def test_a_process_with_no_database_hands_the_lane_no_lookup() -> None:
    """No sessions, no lookup, and the lane then badges nothing rather than everything unverified.

    Delete this and a process with no database builds a lookup that fails every answer."""
    assert item_lookup_of(SimpleNamespace()) is None
    assert item_lookup_of(SimpleNamespace(db_sessions=None)) is None
    assert isinstance(item_lookup_of(SimpleNamespace(db_sessions=object())), StoredItems)
