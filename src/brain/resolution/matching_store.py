"""The online cascade, run: every newly registered record compared with its candidates, and each
pair merged, queued for a person, or left alone.

`brain.resolution.cascade` decides a pair and `brain.resolution.merge_store` carries a merge out.
Nothing compared two records on an install until this module, and `cascade.WHAT_CALLS_THE_CASCADE`
now says so. The worker's `entity_resolution` control runs it after the registry, over the records
that run read.

**Candidates come from the database, scored in one statement (M14.3.6).** `query.score_query`
with `touching` restricts the self join to pairs with one of this run's records on a side and to
pairs `query.CANDIDATE_BLOCKING` admits: one type, and a join key, a name key or a close name in
common. The additive score is computed there, in SQL, with the weights bound; the decision is the
cascade's, in Python, over the two records observed again from what their sources keep, because
the cascade's stages read more than a sum. The score never decides anything here, which is
`cascade.cascade`'s rule.

**Every pair ends in exactly one of three places, and a match is the narrowest of them.**
- The cascade did not match it: nothing is written. A pair that is two things is not a question.
- The cascade put it in the band, or could not measure the names: a review item (M14.3.4).
- The cascade matched it: a merge, unless something holds it, and then a review item that says
  what held it. Five things hold a match: either side carries financial records (M14.5.6), the
  match was on names rather than on a hard identifier (item 155's recommendation, and the
  switch's own words), a merge would leave the survivor over an identifier cap (M14.6.2), a
  stronger identifier names another entity for the same record (M14.6.3), or unattended merging
  is switched off, which is how every install ships
  (`brain.ops.features.UNATTENDED_ENTITY_MERGE`, item 155). The switch is
  read by `merge_store.merge_entities` and nowhere else; a refusal from it lands here as a held
  item, so a match on an install that merges nothing unattended still reaches a person.

**A pair is raised once, ever.** `er.review_item` keeps one row per pair, and a pair that already
has one, open or decided, is not compared again: a rejected pair raised on every run is a queue
nobody finishes. A pair whose two records already resolve to one entity is not compared either.

**Money is read off the connectors' declarations.** A family carries financial records when any
of its records is of an entity its connector declares `carries_money`
(`brain.connectors.resolves`); otherwise every record in it was declared without money, so the
answer is "no financial records found" rather than "not checked".

Rejected: queueing every match while the switch is off without comparing at all. The comparison
is what puts the evidence on the card, and a reviewer shown two names with no reason is being
asked to do the cascade's job.

Task ids: M14.2.5, M14.3.2, M14.3.3, M14.3.4, M14.3.6, M14.3.7, M14.3.8, M14.5.6, M14.6.2
Task ids: M14.6.3
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.resolves import ResolvesAs
from brain.core.scope import Scope
from brain.resolution.canonical import EntityType, Identifier, IdentifierKind, SourceRef
from brain.resolution.cascade import CascadeResult, Decision, Observation, Stage
from brain.resolution.entities import profile_for, resolve_pair
from brain.resolution.guardrails import (
    Claim,
    ReviewItem,
    cap_breaches,
    priority_of,
    resolve_collision,
)
from brain.resolution.merge import (
    AutomaticMerge,
    MoneyBearing,
    MoneyCheck,
    money_review_item,
)
from brain.resolution.merge_store import (
    UNATTENDED_MERGING_WAITS_FOR_ITS_SWITCH,
    MergeRefusedError,
    merge_entities,
)
from brain.resolution.query import score_query
from brain.resolution.registry_store import (
    REGISTRY_ACTOR,
    blocked_digests,
    observation_of,
)
from brain.resolution.sources import resolved_entities
from brain.tables.projection import ProjectedRecordRow
from brain.tables.resolution import CanonicalEntityRow, EntityIdentifierRow
from brain.tables.resolution_review import ReviewItemRow, ReviewOrigin, ReviewState

# ------------------------------------------------------------------ written-down reasons
#: Why a match was held because unattended merging is off.
HELD_UNATTENDED: Final = (
    "the cascade matched these two, and this install does not merge with nobody looking yet, so a "
    "person decides"
)

#: Why a match was held at the money boundary (M14.5.6).
HELD_FOR_MONEY: Final = (
    "the cascade matched these two, and one of them carries financial records, which is never "
    "merged with nobody looking"
)

#: Why a match on anything but a hard identifier is held. Item 155 recommends unattended merging
#: on a hard identifier alone, and the switch says so in its own words.
HELD_ON_A_NAME: Final = (
    "the cascade matched these two on their names rather than on a registration number or a "
    "verified domain, and only a hard identifier is merged with nobody looking, so a person decides"
)

#: Why a match was held at an identifier cap.
HELD_AT_A_CAP: Final = (
    "the cascade matched these two, and merging them would give one entity more of one kind of "
    "identifier than a real one holds, so a person decides"
)

#: Why a match was held by a stronger identifier naming another entity.
HELD_BY_A_COLLISION: Final = (
    "the cascade matched this record with more than one entity, and the strongest identifier "
    "does not settle which, so a person decides"
)

#: The table the score runs over.
OBSERVATIONS: Final = "er.observation"

#: How a review item's id begins.
ITEM_PREFIX: Final = "rev_"

#: The trace a run's writes are attributed under.
MATCHING_TRACE: Final = "entity-resolution-matching"

#: The current entity of each of a set of entities, through the forwarding pointer. The same walk
#: `er.resolved_alias` makes, anchored on the entities asked about rather than on every survivor.
CURRENT_IDS: Final = """
WITH RECURSIVE walk(start_id, entity_id, merged_into, depth) AS (
        SELECT entity_id, entity_id, merged_into, 0
        FROM er.canonical WHERE entity_id = ANY(:ids)
    UNION ALL
        SELECT w.start_id, c.entity_id, c.merged_into, w.depth + 1
        FROM walk w JOIN er.canonical c ON c.entity_id = w.merged_into
        WHERE w.depth < 16
)
SELECT start_id, entity_id FROM walk WHERE merged_into IS NULL
"""

#: Every record, and every entity id, in the families of a set of current entities.
FAMILY_MEMBERS: Final = """
WITH RECURSIVE survivor(entity_id, current_id, depth) AS (
        SELECT entity_id, entity_id, 0 FROM er.canonical
        WHERE merged_into IS NULL AND entity_id = ANY(:ids)
    UNION ALL
        SELECT c.entity_id, s.current_id, s.depth + 1
        FROM er.canonical c JOIN survivor s ON c.merged_into = s.entity_id
        WHERE s.depth < 16
)
SELECT s.current_id, s.entity_id, l.source, l.entity, l.source_id
FROM survivor s LEFT JOIN er.link l ON l.entity_id = s.entity_id
"""


class Merges(Protocol):
    """Carries out one unattended merge: `merge_store.merge_entities` over the same sessions."""

    async def __call__(
        self,
        *,
        survivor_id: str,
        merged_id: str,
        authority: AutomaticMerge,
        at: datetime,
        trace_id: str,
        reason: str,
    ) -> object: ...


@dataclass(frozen=True)
class Matched:
    """What one matching run did, in counts. Never a name, a value or a record id."""

    compared: int = 0
    merged: int = 0
    queued: int = 0

    def summary(self) -> str:
        if not self.compared:
            return "no candidate pair to compare"
        return (
            f"{self.compared} candidate pair(s) compared: {self.merged} merged, "
            f"{self.queued} sent to a person"
        )


@dataclass
class _Raised:
    """A review item waiting to be written, with what the row needs beside the item."""

    item: ReviewItem
    entity_type: EntityType
    left_entity_id: str
    right_entity_id: str
    origin: ReviewOrigin
    stage: int
    reason: str


@dataclass
class _Match:
    result: CascadeResult
    entity_type: EntityType
    left_current: str
    right_current: str
    claims: list[Claim] = field(default_factory=list)


def new_item_id() -> str:
    return f"{ITEM_PREFIX}{uuid.uuid4().hex}"


def strongest_kind(result: CascadeResult) -> IdentifierKind | None:
    """The strongest identifier the two records agreed on, or None when they agreed on none."""
    kinds = [
        IdentifierKind(one.field)
        for one in result.evidence
        if one.weight > 0 and one.field in {kind.value for kind in IdentifierKind}
    ]
    return min(kinds, key=priority_of) if kinds else None


def money_of(
    members: Iterable[tuple[str, str]], declared: Mapping[tuple[str, str], ResolvesAs]
) -> MoneyBearing:
    """Whether a family carries financial records, read off its records' declarations."""
    found = list(members)
    if not found or any(one not in declared for one in found):
        return MoneyBearing.NOT_CHECKED
    if any(declared[one].carries_money for one in found):
        return MoneyBearing.CARRIES_FINANCIAL_RECORDS
    return MoneyBearing.NO_FINANCIAL_RECORDS_FOUND


class StoredMatching:
    """The online cascade over this install's registry, as the application role."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        declared: Mapping[tuple[str, str], ResolvesAs] | None = None,
        merges: Merges | None = None,
    ) -> None:
        self._sessions = sessions
        self._declared = resolved_entities() if declared is None else declared
        self._merges = merges

    async def _merge(
        self,
        *,
        survivor_id: str,
        merged_id: str,
        authority: AutomaticMerge,
        at: datetime,
        trace_id: str,
        reason: str,
    ) -> object:
        """The install's merge store, unless a caller handed another."""
        if self._merges is not None:
            return await self._merges(
                survivor_id=survivor_id,
                merged_id=merged_id,
                authority=authority,
                at=at,
                trace_id=trace_id,
                reason=reason,
            )
        return await merge_entities(
            self._sessions,
            survivor_id=survivor_id,
            merged_id=merged_id,
            authority=authority,
            at=at,
            trace_id=trace_id,
            reason=reason,
        )

    async def match(self, refs: Sequence[SourceRef], *, pepper: str, now: datetime) -> Matched:
        """Compare each of these records with its candidates and settle or queue each pair."""
        if not refs:
            return Matched()
        query = score_query(table=OBSERVATIONS, scope=Scope.unrestricted(), touching=refs)
        async with self._sessions() as session:
            pairs = [
                (
                    SourceRef(row.left_source, row.left_entity, row.left_source_id),
                    SourceRef(row.right_source, row.right_entity, row.right_source_id),
                )
                for row in (await session.execute(text(query.sql), dict(query.params))).all()
            ]
            if not pairs:
                return Matched()
            records = await linked_records(session, {one for pair in pairs for one in pair})
            current = await current_ids(session, [one[0] for one in records.values()])
            raised_before = await _raised_pairs(session, pairs)
            blocked = await blocked_digests(session)

        raised: list[_Raised] = []
        matches: list[_Match] = []
        compared = 0
        observed: dict[SourceRef, Observation] = {}
        for left, right in pairs:
            if left not in records or right not in records or (left, right) in raised_before:
                continue
            left_current = current.get(records[left][0])
            right_current = current.get(records[right][0])
            if left_current is None or right_current is None or left_current == right_current:
                continue
            declared = self._declared[(left.source, left.entity)]
            if declared.entity_type is not self._declared[(right.source, right.entity)].entity_type:
                continue
            for one in (left, right):
                if one not in observed:
                    observed[one], _ = observation_of(
                        records[one][1],
                        self._declared[(one.source, one.entity)],
                        pepper=pepper,
                        blocked=blocked,
                    )
            compared += 1
            result = resolve_pair(
                observed[left], observed[right], profile_for(declared.entity_type)
            )
            if result.decision is Decision.NOT_MATCHED:
                continue
            if result.decision is Decision.TO_REVIEW:
                raised.append(
                    _Raised(
                        item=result.review_item(new_item_id()),
                        entity_type=declared.entity_type,
                        left_entity_id=left_current,
                        right_entity_id=right_current,
                        origin=ReviewOrigin.CASCADE,
                        stage=int(result.stage),
                        reason=result.reason,
                    )
                )
                continue
            matches.append(_Match(result, declared.entity_type, left_current, right_current))

        merged = 0
        for match in self._settle_collisions(matches, raised):
            done = await self._merge_or_hold(match, now=now)
            if isinstance(done, _Raised):
                raised.append(done)
            else:
                merged += 1
        if raised:
            await self._raise(raised)
        return Matched(compared=compared, merged=merged, queued=len(raised))

    def _settle_collisions(self, matches: list[_Match], raised: list[_Raised]) -> list[_Match]:
        """The matches the priority order lets through, and the rest held for a person."""
        by_record: dict[SourceRef, list[_Match]] = defaultdict(list)
        for one in matches:
            by_record[one.result.left].append(one)
            by_record[one.result.right].append(one)
        held: set[int] = set()
        for record, found in by_record.items():
            targets = {
                one.right_current if one.result.left == record else one.left_current
                for one in found
            }
            if len(targets) < 2:
                continue
            claims = []
            for one in found:
                kind = strongest_kind(one.result)
                target = one.right_current if one.result.left == record else one.left_current
                if kind is not None:
                    claims.append(Claim(kind=kind, entity_id=target))
            winner = resolve_collision(claims).entity_id if len(claims) == len(found) else None
            for one in found:
                target = one.right_current if one.result.left == record else one.left_current
                if winner is None or target != winner:
                    held.add(id(one))
        kept = []
        for one in matches:
            if id(one) in held:
                raised.append(self._held(one, HELD_BY_A_COLLISION))
            else:
                kept.append(one)
        return kept

    def _held(self, one: _Match, reason: str, origin: ReviewOrigin = ReviewOrigin.HELD) -> _Raised:
        return _Raised(
            item=ReviewItem(
                item_id=new_item_id(),
                left=one.result.left,
                right=one.result.right,
                evidence=one.result.evidence,
            ),
            entity_type=one.entity_type,
            left_entity_id=one.left_current,
            right_entity_id=one.right_current,
            origin=origin,
            stage=int(one.result.stage),
            reason=reason,
        )

    async def _merge_or_hold(self, one: _Match, *, now: datetime) -> _Raised | None:
        """Merge one match, or say what held it. See the module docstring for the four holds."""
        async with self._sessions() as session:
            families = await families_of(session, (one.left_current, one.right_current))
            survivor, merged_id = await survivor_first(
                session, (one.left_current, one.right_current)
            )
            identifiers = await _identifiers(session, families)
        money = MoneyCheck(
            left=money_of(families.get(one.left_current, {}).values(), self._declared),
            right=money_of(families.get(one.right_current, {}).values(), self._declared),
        )
        if not money.permits_automatic:
            return _Raised(
                item=money_review_item(one.result, money, item_id=new_item_id()),
                entity_type=one.entity_type,
                left_entity_id=one.left_current,
                right_entity_id=one.right_current,
                origin=ReviewOrigin.MONEY,
                stage=int(one.result.stage),
                reason=HELD_FOR_MONEY,
            )
        if one.result.stage is not Stage.HARD_IDENTIFIER:
            return self._held(one, HELD_ON_A_NAME)
        relabelled = [
            Identifier(
                entity_id=survivor,
                kind=kind,
                key_hash=digest,
                source=source,
                first_seen_at=now,
            )
            for kind, digest, source in identifiers
        ]
        if cap_breaches(survivor, one.entity_type, relabelled):
            return self._held(one, HELD_AT_A_CAP)
        try:
            await self._merge(
                survivor_id=survivor,
                merged_id=merged_id,
                authority=AutomaticMerge(
                    decision=one.result, money=money, performed_by=REGISTRY_ACTOR
                ),
                at=now,
                trace_id=MATCHING_TRACE,
                reason=one.result.reason,
            )
        except MergeRefusedError as refused:
            if str(refused) != UNATTENDED_MERGING_WAITS_FOR_ITS_SWITCH:
                raise
            return self._held(one, HELD_UNATTENDED)
        return None

    async def _raise(self, raised: Sequence[_Raised]) -> None:
        """Write the review items, each pair once. A pair already raised is left as it is."""
        async with self._sessions() as session, session.begin():
            for one in raised:
                item = one.item
                await session.execute(
                    insert(ReviewItemRow)
                    .values(
                        item_id=item.item_id,
                        entity_type=one.entity_type.value,
                        left_source=item.left.source,
                        left_entity=item.left.entity,
                        left_source_id=item.left.source_id,
                        right_source=item.right.source,
                        right_entity=item.right.entity,
                        right_source_id=item.right.source_id,
                        left_entity_id=one.left_entity_id,
                        right_entity_id=one.right_entity_id,
                        origin=one.origin.value,
                        stage=one.stage,
                        reason=one.reason,
                        evidence=[
                            {"field": evidence.field, "weight": evidence.weight}
                            for evidence in item.evidence
                        ],
                        state=ReviewState.OPEN.value,
                    )
                    .on_conflict_do_nothing()
                )


# ------------------------------------------------------------------------- reading
async def linked_records(
    session: AsyncSession, refs: set[SourceRef]
) -> dict[SourceRef, tuple[str, ProjectedRecordRow]]:
    """Each live record with the entity it is linked to."""
    from brain.tables.resolution import EntityLinkRow

    keys = [(one.source, one.entity, one.source_id) for one in refs]
    rows = (
        await session.execute(
            select(EntityLinkRow.entity_id, ProjectedRecordRow)
            .join(
                EntityLinkRow,
                tuple_(EntityLinkRow.source, EntityLinkRow.entity, EntityLinkRow.source_id)
                == tuple_(
                    ProjectedRecordRow.source,
                    ProjectedRecordRow.entity,
                    ProjectedRecordRow.source_id,
                ),
            )
            .where(
                tuple_(
                    ProjectedRecordRow.source,
                    ProjectedRecordRow.entity,
                    ProjectedRecordRow.source_id,
                ).in_(keys),
                ProjectedRecordRow.deleted_at.is_(None),
            )
        )
    ).all()
    return {
        SourceRef(source=row.source, entity=row.entity, source_id=row.source_id): (entity_id, row)
        for entity_id, row in rows
    }


async def current_ids(session: AsyncSession, entity_ids: Sequence[str]) -> dict[str, str]:
    rows = (await session.execute(text(CURRENT_IDS), {"ids": list(set(entity_ids))})).all()
    return {str(start): str(current) for start, current in rows}


async def _raised_pairs(
    session: AsyncSession, pairs: Sequence[tuple[SourceRef, SourceRef]]
) -> set[tuple[SourceRef, SourceRef]]:
    """The pairs that already have a review item, open or decided."""
    row = ReviewItemRow
    keys = [(a.source, a.entity, a.source_id, b.source, b.entity, b.source_id) for a, b in pairs]
    found = (
        await session.execute(
            select(
                row.left_source,
                row.left_entity,
                row.left_source_id,
                row.right_source,
                row.right_entity,
                row.right_source_id,
            ).where(
                tuple_(
                    row.left_source,
                    row.left_entity,
                    row.left_source_id,
                    row.right_source,
                    row.right_entity,
                    row.right_source_id,
                ).in_(keys)
            )
        )
    ).all()
    return {(SourceRef(*one[0:3]), SourceRef(*one[3:6])) for one in found}


async def families_of(
    session: AsyncSession, current: Sequence[str]
) -> dict[str, dict[str, tuple[str, str]]]:
    """Each current entity's family: entity id to the (connector, entity) of its record."""
    found: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    for current_id, entity_id, source, entity, source_id in (
        await session.execute(text(FAMILY_MEMBERS), {"ids": list(current)})
    ).all():
        if source is not None:
            found[current_id][f"{entity_id}/{source}/{entity}/{source_id}"] = (source, entity)
    return found


async def survivor_first(session: AsyncSession, pair: Sequence[str]) -> tuple[str, str]:
    """The entity minted first survives, so an id issued earlier stays the one others resolve to."""
    rows = (
        await session.execute(
            select(CanonicalEntityRow.entity_id)
            .where(CanonicalEntityRow.entity_id.in_(list(pair)))
            .order_by(CanonicalEntityRow.created_at, CanonicalEntityRow.entity_id)
        )
    ).all()
    return rows[0][0], rows[1][0]


async def _identifiers(
    session: AsyncSession, families: Mapping[str, Mapping[str, tuple[str, str]]]
) -> list[tuple[IdentifierKind, str, SourceRef]]:
    """Every identifier of both families, as kind, digest and the record that asserted it."""
    entity_ids = sorted({key.split("/", 1)[0] for one in families.values() for key in one})
    rows = (
        await session.execute(
            select(EntityIdentifierRow).where(EntityIdentifierRow.entity_id.in_(entity_ids))
        )
    ).scalars()
    return [
        (
            IdentifierKind(row.kind),
            row.key_hash,
            SourceRef(source=row.source, entity=row.entity, source_id=row.source_id),
        )
        for row in rows
    ]
