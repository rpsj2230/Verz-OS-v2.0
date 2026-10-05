"""The review queue, read and decided: the items waiting, whether a reader reaches both records of
one, and a reviewer's merge or rejection written in their own name.

`brain.resolution.review` turns items a reader may see into cards, and `guardrails.review_queue`
is the filter that decides which those are. Neither had anything to read from or anywhere to write
a decision, which `review.NO_SCREEN_IS_WIRED_TO_ANY_OF_THIS` said. This is both halves, and
`brain.resolution_routes` is the screen's API over it.

**Whether a reader reaches a record is the redactor's answer, asked of the record itself.**
`canonical.MemberReach` is handed one source record and nothing else, and the implementation here
asks `brain.knowledge.columns.project_row` whether the record, under its connector's own field
rules (`brain.knowledge.connector_rows.CONNECTOR_ROW_ENTITIES`), leaves this reader any column at
all. That is the question Ask asks before it answers from a row, so a reviewer is shown a pair
exactly when Ask would answer them about both halves. A record of an entity no connector
classifies, and a record that has gone, is reached by nobody: the fail-closed direction, for
`guardrails.BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE`'s reason. See
`A_REVIEWER_REACHES_A_RECORD_WHEN_ASK_WOULD_ANSWER_THEM_ABOUT_IT`.

**A decision is written once, by its reviewer, and a merge is a ReviewedMerge.** The item's row is
updated only while it is open and only to name the session's own principal (0184's policy), and a
merge goes through `merge_store.merge_entities` with the reviewer, the item as the review
reference and the evidence the reviewer was shown. The money answers are carried and not checked,
which is `merge.ReviewedMerge`'s whole difference from an automatic merge: a person may merge
across the boundary, and the audit names them.

**The merge commits before the item says so.** `merge_entities` owns its transaction, so the two
cannot be one. Merged and then marked, a failure between them leaves a merge whose item still
reads open, which the next decision finds already one entity and closes; marked and then merged,
it would leave an item saying merged over two entities nobody joined.

Task ids: M14.6.4, M14.8.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.resolves import ResolvesAs
from brain.core.entitlement import EntitlementSet
from brain.knowledge.columns import ColumnView, project_row
from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES, NAMED_BY
from brain.resolution.canonical import EntityType, SourceRef
from brain.resolution.guardrails import Evidence, ReviewItem
from brain.resolution.matching_store import (
    current_ids,
    families_of,
    linked_records,
    money_of,
    survivor_first,
)
from brain.resolution.merge import MoneyCheck, ReviewedMerge
from brain.resolution.merge_store import merge_entities
from brain.resolution.sources import resolved_entities
from brain.tables.audit import attributed_to
from brain.tables.projection import ProjectedRecordRow
from brain.tables.resolution_review import ReviewItemRow, ReviewOrigin, ReviewState

#: Why the review screen's reach is Ask's.
A_REVIEWER_REACHES_A_RECORD_WHEN_ASK_WOULD_ANSWER_THEM_ABOUT_IT: Final = (
    "A reviewer deciding whether two records are one thing has to see both, and showing them a "
    "record they could not ask about is the disclosure the whole product refuses. So a record is "
    "reached when the redactor, under its connector's own field rules, leaves this reader any "
    "column of it: the same question Ask asks before it answers from a row. A record of an entity "
    "nobody classified, or one that has gone, is reached by nobody."
)


@dataclass(frozen=True)
class StoredItem:
    """One review item as stored: the pair and its evidence, and what the row says about it."""

    item: ReviewItem
    entity_type: EntityType
    origin: ReviewOrigin
    stage: int
    reason: str
    state: ReviewState
    raised_at: datetime
    decided_by: str | None
    decided_at: datetime | None


def _stored(row: ReviewItemRow) -> StoredItem:
    return StoredItem(
        item=ReviewItem(
            item_id=row.item_id,
            left=SourceRef(row.left_source, row.left_entity, row.left_source_id),
            right=SourceRef(row.right_source, row.right_entity, row.right_source_id),
            evidence=tuple(
                Evidence(field=str(one["field"]), weight=float(one["weight"]))
                for one in row.evidence
            ),
        ),
        entity_type=EntityType(row.entity_type),
        origin=ReviewOrigin(row.origin),
        stage=int(row.stage),
        reason=row.reason,
        state=ReviewState(row.state),
        raised_at=row.raised_at,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
    )


def seen_by(
    reach: EntitlementSet, record: SourceRef, fields: Mapping[str, Any] | None, now: datetime
) -> ColumnView | None:
    """What this reader may see of one record, or None when they reach none of it.

    See `A_REVIEWER_REACHES_A_RECORD_WHEN_ASK_WOULD_ANSWER_THEM_ABOUT_IT`.
    """
    if fields is None:
        return None
    classified = {one.entity: one for one in CONNECTOR_ROW_ENTITIES.get(record.source, ())}
    classification = classified.get(record.entity)
    if classification is None:
        return None
    view = project_row(classification, fields, entitlement=reach, now=now)
    return view if view.values else None


def label_of(record: SourceRef, view: ColumnView) -> str:
    """How a card names a record: the field the connector names it by, when the reader sees it."""
    named_by = NAMED_BY.get((record.source, record.entity), "")
    shown = view.values.get(named_by) if named_by else None
    return str(shown) if shown not in (None, "") else record.source_id


class StoredReviews:
    """The review queue over this install's database, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def open_items(self) -> tuple[StoredItem, ...]:
        """Every item still waiting for a decision, in the order the queue sorts them."""
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(ReviewItemRow).where(ReviewItemRow.state == ReviewState.OPEN.value)
                )
            ).scalars()
            return tuple(_stored(row) for row in rows)

    async def one(self, item_id: str) -> StoredItem | None:
        async with self._sessions() as session:
            row = await session.get(ReviewItemRow, item_id)
            return None if row is None else _stored(row)

    async def records(self, refs: Sequence[SourceRef]) -> dict[SourceRef, Mapping[str, Any]]:
        """The live fields of each record, by its reference. A record that has gone is absent."""
        if not refs:
            return {}
        keys = [(one.source, one.entity, one.source_id) for one in refs]
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        ProjectedRecordRow.source,
                        ProjectedRecordRow.entity,
                        ProjectedRecordRow.source_id,
                        ProjectedRecordRow.fields,
                    ).where(
                        tuple_(
                            ProjectedRecordRow.source,
                            ProjectedRecordRow.entity,
                            ProjectedRecordRow.source_id,
                        ).in_(keys),
                        ProjectedRecordRow.deleted_at.is_(None),
                    )
                )
            ).all()
        return {SourceRef(a, b, c): dict(fields or {}) for a, b, c, fields in rows}

    async def decide(
        self,
        item_id: str,
        *,
        state: ReviewState,
        by: str,
        at: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        """Close one open item as merged or rejected, in `by`'s name. False when it was not open."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.principal_id', :by, true)").bindparams(by=by)
            )
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            done = await session.execute(
                update(ReviewItemRow)
                .where(
                    ReviewItemRow.item_id == item_id,
                    ReviewItemRow.state == ReviewState.OPEN.value,
                )
                .values(state=state.value, decided_by=by, decided_at=at)
                .returning(ReviewItemRow.item_id)
            )
            return done.first() is not None


async def merge_reviewed(
    sessions: async_sessionmaker[AsyncSession],
    stored: StoredItem,
    *,
    reviewer_id: str,
    at: datetime,
    ent_hash: str,
    trace_id: str,
    reason: str,
    declared: Mapping[tuple[str, str], ResolvesAs] | None = None,
) -> bool:
    """Merge the two records' current entities on a reviewer's word. False when already one.

    The entity minted first survives, as in the automatic path, and the money answers are what
    the connectors declare, carried on the merge and never checked: see the module docstring.
    """
    known = resolved_entities() if declared is None else declared
    item = stored.item
    async with sessions() as session:
        linked = await linked_records(session, {item.left, item.right})
        if item.left not in linked or item.right not in linked:
            return False
        current = await current_ids(session, [linked[item.left][0], linked[item.right][0]])
        left = current.get(linked[item.left][0])
        right = current.get(linked[item.right][0])
        if left is None or right is None or left == right:
            return False
        family = await families_of(session, (left, right))
        survivor, merged = await survivor_first(session, (left, right))
    money = MoneyCheck(
        left=money_of(family.get(left, {}).values(), known),
        right=money_of(family.get(right, {}).values(), known),
    )
    await merge_entities(
        sessions,
        survivor_id=survivor,
        merged_id=merged,
        authority=ReviewedMerge(
            reviewer_id=reviewer_id,
            review_ref=item.item_id,
            money=money,
            evidence=item.evidence,
        ),
        at=at,
        trace_id=trace_id,
        reason=reason,
        ent_hash=ent_hash,
    )
    return True
