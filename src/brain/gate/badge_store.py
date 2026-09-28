"""Reading the items behind the documents an answer cites, so each citation can carry its badge.

`brain.gate.provenance.Badging` takes a reader and the item records of the cited documents, and
`brain.knowledge.verification.disclose` decides what that reader may be told about who vouched for
each. Nothing on the request path read an item: `know.item` was read by the re-verification sweep
past its policy and by the library screen through `0069`'s own function, and neither is the
asker's reach. This is the read the answer needs, and it is the smallest one that could be right.

**It reads at the reader's own reach, through the policy `0040` put on `know.item`.** The statement
runs through the same `RowSource` the passage search does, with the settings
`brain.knowledge.search.session_settings` writes for this reader, so `item_within_reach` decides
which rows come back exactly as it decides which chunks do. Rejected: reading through the sweep's
`know.items_for_review`, which is `SECURITY DEFINER` and returns items the reader cannot reach. A
badge computed from one of those would still be withheld by nothing, because the citation beside
it was reached; but the read would have crossed a wall to get there, and the next caller of that
read would not have a citation beside it. See `A_BADGE_IS_READ_AT_THE_READERS_OWN_REACH`.

**It is asked for the cited documents and nothing else.** `brain.gate.model_lane.evidence_of`
passes the references of the passages it cites, so an item the answer did not draw on is never
read for it, and a badge exists only beside a citation, which is `provenance`'s own rule.

**`know.item` holds no body, and a `KnowledgeItem` requires one.** The item is constructed with
`NO_BODY_READ`, a fixed sentence saying so, because the badge reads its state, its dates, its
steward and its place and nothing else, and a record whose body is a sentence about not having
been read cannot be mistaken for the document. A row the record type refuses, such as a company
item published with nobody's verification, is left out rather than failing the answer: its
citation is then badged as nothing on file, which is `provenance.badge_for`'s "not verified by
anyone", and that is what the row says.

Scope: one read. It decides nothing about who may be told the verifier; that is
`brain.knowledge.verification.disclose`, called by `provenance`.

Task ids: M7.4.7, M34.2.1.2
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final, cast

import sqlalchemy as sa
from pydantic import ValidationError

from brain.core.entitlement import EntitlementSet
from brain.knowledge.document_tools import KNOWLEDGE_TOOL_PREFIX, reach_through
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.rows import RowQuery, RowSource
from brain.knowledge.search import Reach, session_settings
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.tables.knowledge import KnowledgeItemRow

#: Why the badge read runs under the reader's settings and not past the policy.
A_BADGE_IS_READ_AT_THE_READERS_OWN_REACH: Final = (
    "An item is read for a badge under the same row-level security that decided which passages "
    "the reader was shown, so the read returns only items this reader reaches. A read past the "
    "policy would return the same rows today, because every cited document was reached, and "
    "would be a read that crosses a wall for the next caller who has no citation beside it."
)

#: The body a badge's item is built with. `know.item` has no body column; see the docstring.
NO_BODY_READ: Final = "The body of this item is not read to compute its badge."

#: The table, and the columns a badge is computed from, labelled as the row names them. A cast at
#: SQLAlchemy's boundary: a declarative class's `__table__` is typed as the wider `FromClause`.
ITEM: Final = cast(sa.Table, KnowledgeItemRow.__table__)
BADGE_COLUMNS: Final[tuple[str, ...]] = (
    "item_id",
    "title",
    "owner_id",
    "visibility",
    "department",
    "state",
    "verified_by",
    "verified_at",
    "review_by",
    "supersedes",
    "kind",
)

#: What the statement is recorded as reading, for the row source's trace of what it ran.
ITEM_ENTITY: Final = "knowledge_item"


def items_query(document_ids: Sequence[str], *, reach: Reach) -> RowQuery:
    """The items among `document_ids`, under this reader's settings. Certainly empty on none."""
    statement = (
        sa.select(*(ITEM.c[name].label(name) for name in BADGE_COLUMNS))
        .where(ITEM.c.item_id.in_(list(document_ids)))
        .order_by(ITEM.c.item_id)
    )
    return RowQuery(
        entity=ITEM_ENTITY,
        source=KNOWLEDGE_TOOL_PREFIX,
        columns=BADGE_COLUMNS,
        statement=statement,
        certainly_empty=not document_ids,
        settings=session_settings(reach),
    )


def item_of(row: Mapping[str, Any]) -> KnowledgeItem | None:
    """One row as the record a badge is disclosed from, or None when the record refuses it."""
    try:
        level = Visibility(str(row["visibility"]))
        return KnowledgeItem(
            item_id=str(row["item_id"]),
            content=NO_BODY_READ,
            title=str(row["title"] or ""),
            visibility=KnowledgeVisibility(
                level=level,
                owner_id=str(row["owner_id"]),
                department=str(row["department"] or "") if level is Visibility.DEPARTMENT else "",
            ),
            owner_id=str(row["owner_id"]),
            state=KnowledgeState(str(row["state"])),
            verified_by=str(row["verified_by"] or ""),
            verified_at=row["verified_at"],
            review_by=row["review_by"],
            supersedes=str(row["supersedes"] or ""),
            kind=None if not row["kind"] else KnowledgeKind(str(row["kind"])),
        )
    except (ValidationError, ValueError):
        # See the module docstring: a row the record refuses has no badge of its own.
        return None


class StoredItems:
    """`brain.gate.model_lane.ItemLookup` over `know.item`, through a `RowSource`."""

    def __init__(self, records: RowSource) -> None:
        self._records = records

    async def items(
        self, document_ids: Sequence[str], *, entitlement: EntitlementSet, now: datetime
    ) -> tuple[KnowledgeItem, ...]:
        """The items this reach may read among the cited documents. None asked, none read."""
        if not document_ids:
            return ()
        reach = await reach_through(self._records, entitlement, now)
        if reach is None:
            return ()
        rows = await self._records.rows(items_query(document_ids, reach=reach))
        return tuple(item for item in (item_of(row) for row in rows) if item is not None)


def item_lookup_of(state: Any) -> StoredItems | None:
    """The lookup a process with a database hands the model lane, or None without one."""
    sessions = getattr(state, "db_sessions", None)
    return None if sessions is None else StoredItems(SessionRowSource(sessions))
