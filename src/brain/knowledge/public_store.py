"""Where a public marking is read and written: two columns of `know.item`, under the caller's reach.

`brain.knowledge.public` decides who may mark a document; this holds a session and decides as little
as it can, in the shape `brain.knowledge.lifecycle_store` takes. Both functions run in a
transaction already told who is acting (`lifecycle_store.as_person`), so `know.item`'s policy
admits exactly the rows the Python judged, and the write is attributed by the caller so
`know.record_item` names them (`brain.knowledge.public.A_MARKING_NAMES_WHO_MADE_IT`).

**Separate from `lifecycle_store`'s item statements, and deliberately so.** Those read `know.item`
and `know.item_versions` in one column order the history function fixes, and adding two columns to
them would change a function `0120` owns for a fact only this screen shows. Rejected: carrying the
marking on `lifecycle.StoredItem`, for the same reason.

**The write says what it expected.** Marking moves an item that is published and unmarked, and
unmarking one that is marked, so two people pressing at once leave one entry and the second is told
it moved. A marking that changes nothing is not written, so the ledger records decisions and not
repeated presses.

Task ids: M10.7.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from brain.knowledge.public import PublicMarking

#: The marking of one item the policy admits at this transaction's reach.
MARKING_BY_ID: Final = "SELECT public_by, public_at FROM know.item WHERE item_id = :id"

#: Marks a published, unmarked item. The state and the marking are both conditions, so a moved
#: row is refused rather than overwritten.
MARK: Final = (
    "UPDATE know.item SET public_by = :by, public_at = :at, updated_at = now() "
    "WHERE item_id = :id AND state = 'published' AND public_at IS NULL"
)

#: Unmarks a marked item, whatever its state.
UNMARK: Final = (
    "UPDATE know.item SET public_by = NULL, public_at = NULL, updated_at = now() "
    "WHERE item_id = :id AND public_at IS NOT NULL"
)


class PublicMarkingMovedError(Exception):
    """The item's marking or state changed between the read and the write. Names no content."""


async def marking_of(session: AsyncSession, item_id: str) -> PublicMarking | None:
    """The item's marking, or None for an item this transaction's reach does not admit."""
    row = (await session.execute(text(MARKING_BY_ID), {"id": item_id})).mappings().one_or_none()
    if row is None:
        return None
    return PublicMarking(marked_by=row["public_by"] or "", marked_at=row["public_at"])


async def record_marking(
    session: AsyncSession, item_id: str, *, public: bool, by: str, at: datetime
) -> None:
    """Mark or unmark one item. Refuses with `PublicMarkingMovedError` when no row changed."""
    if public:
        result = await session.execute(text(MARK), {"id": item_id, "by": by, "at": at})
    else:
        result = await session.execute(text(UNMARK), {"id": item_id})
    # `CursorResult` rather than `Result`: an UPDATE's is the one carrying `rowcount`. Cast at a
    # library boundary where proving the match buys nothing.
    if cast("CursorResult[Any]", result).rowcount != 1:
        msg = f"{item_id!r} was not changed: its state or its marking moved first"
        raise PublicMarkingMovedError(msg)
