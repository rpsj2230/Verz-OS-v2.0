"""The merge and the unmerge, carried out: one transaction each, one pointer, one audit row.

`brain.resolution.merge` decides what a merge is and refuses what it may not be, and it is pure:
until this module nothing called it, no pre-image was kept anywhere, and no merge could happen on
an install at all. This is the caller its `NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM` named.
Nothing here re-decides a rule `merge` holds; it loads what the rule needs, hands it over, and
writes what comes back.

**One merge is one transaction, and the pre-image is written in it** (M14.5.1). The two entities
are locked first, in id order, so two merges racing over a shared entity queue rather than
deadlock and the second sees the first's pointer. Then both families are loaded, whole, with every
link, alias and identifier naming any id in them, and `merge.merge` captures the pre-image from
exactly what was loaded. The `er.merge` row holding it is inserted before the pointer moves, so the
ledger entry `0183`'s trigger appends on the pointer can name the row, and the pointer, the row and
the entries commit together or not at all. See `ONE_MERGE_IS_ONE_TRANSACTION`.

**The write is one UPDATE of one row, and its WHERE clause is the last guard** (M14.5.2). The
outcome `merge` returns has nowhere to put a rewritten link, alias or identifier, and nothing here
writes one; the UPDATE moves `merged_into` and `merged_at` on the entity that stops being current,
only while it is still current, and anything other than one row is refused.

**An unmerge puts back the one thing the merge moved, and nothing that never moved** (M14.5.3).
A merge writes no child row, so the pre-image's links, aliases and identifiers are the rows as they
still stand, and writing them back would do nothing at best. At worst it would undo somebody else's
work: `er.link` takes an UPDATE, a record's membership corrected after the merge is a later
decision, and restoring the pre-image's copy over it would reverse that decision with this unmerge's
name on it. So the store clears the pointer to what the pre-image recorded and writes nothing else,
and the restoration it returns still carries the whole pre-image, for a caller to compare against.
See `AN_UNMERGE_PUTS_BACK_ONLY_WHAT_THE_MERGE_MOVED`. And only the merge in force is reversed: the
entity's `merged_at` has to be the merge's `decided_at`, so an old merge id, one already reversed
or one superseded by a later merge of the same pair, is refused rather than restoring a state two
merges ago. See `ONLY_THE_MERGE_IN_FORCE_IS_REVERSED`.

**Who is the authority's, and the database holds the row to it** (M14.5.4). The transaction is
attributed to `authority.decided_by` (or the unmerge's `performed_by`) through
`brain.tables.audit.attributed_to`, so the ledger entry names that actor, and `0183`'s INSERT
policies refuse a merge row naming anybody else. There is no parameter through which a caller
could name a different actor from the authority.

**Unattended merging is a switch that ships off** (needs-rupash 155). `AutomaticMerge` already
refuses money and anything the cascade did not match; whether this install merges at all with
nobody looking is the owner's call, so it is `brain.ops.features.UNATTENDED_ENTITY_MERGE`, read
here and nowhere else. A `ReviewedMerge` is never behind it. See
`UNATTENDED_MERGING_WAITS_FOR_ITS_SWITCH`.

**Invalidation is carried out after the commit, on every id of both families, surface by
surface, and today every surface holds nothing to drop** (M14.5.5). After rather than inside,
because an entry evicted before the commit can be filled again from the pre-merge rows by a reader
who has not seen it. Every id, because an id issued before a merge still resolves and is therefore
still a key (`merge.AN_ID_ISSUED_BEFORE_A_MERGE_IS_STILL_A_CACHE_KEY`). And each surface's
invalidator was written by asking what that surface holds about an entity id, measured on
2026-10-06: the answer cache's key carries no entity and the cache has no delete by design
(`THE_ANSWER_CACHE_HOLDS_NOTHING_KEYED_BY_AN_ENTITY`), no memory row names an entity
(`MEMORY_HOLDS_NOTHING_KEYED_BY_AN_ENTITY`), and the projection's `local_id` is the id a record was
resolved to, which is left as it is (`A_PROJECTED_ROW_KEEPS_THE_ID_IT_WAS_RESOLVED_TO`). Each is a
named function rather than an absent one, so the surface that first starts holding something keyed
by an entity id has a place to evict it, and `tests/unit/test_merge_store.py` fails the day a table
outside `er` grows such a column. Inventing an eviction for entries nobody writes would be a
function that reports success over nothing.

Rejected: a class holding the session factory, as most stores here are. The switch's reader is
named as `module:function` and checked against the source by `brain.ops.features.feature_gaps`, so
the function that asks has to be reachable at module level; two functions over a factory say the
same thing with one less indirection.

Task ids: M14.5.1, M14.5.2, M14.5.3, M14.5.4, M14.5.5
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, cast

from sqlalchemy import insert, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.features import UNATTENDED_ENTITY_MERGE, is_on
from brain.resolution.canonical import (
    MAX_FORWARD_DEPTH,
    Alias,
    CanonicalEntity,
    EntityType,
    Identifier,
    IdentifierKind,
    Link,
    ResolutionError,
    SourceRef,
)
from brain.resolution.merge import (
    AutomaticMerge,
    InvalidatedSurface,
    Invalidation,
    MergeAuthority,
    MergeOutcome,
    PreImage,
    Restoration,
    ReviewedMerge,
    merge,
    unmerge,
)
from brain.tables.audit import UNSUPPLIED_ENT_HASH, attributed_to
from brain.tables.entity_merge import EntityMergeRow, EntityUnmergeRow
from brain.tables.resolution import (
    CanonicalEntityRow,
    EntityAliasRow,
    EntityIdentifierRow,
    EntityLinkRow,
)

# ------------------------------------------------------------------ written-down reasons
#: Why the pointer, the audit row and the pre-image commit together.
ONE_MERGE_IS_ONE_TRANSACTION: Final = (
    "A pointer moved without its audit row is a merge nobody can explain, and a pre-image "
    "written after the move may describe a graph something else changed in between. So the two "
    "entities are locked, the families are read, the pre-image is captured from what was read, "
    "and the row holding it and the pointer are written in one transaction, row first so the "
    "ledger entry the pointer's trigger appends can name it. Either all of it commits or none."
)

#: Why an unmerge writes the pointer and nothing else.
AN_UNMERGE_PUTS_BACK_ONLY_WHAT_THE_MERGE_MOVED: Final = (
    "A merge moves one pointer and writes no link, alias or identifier, so those rows still "
    "stand as the pre-image recorded them and there is nothing of theirs to put back. Writing "
    "the pre-image's copies over them anyway would undo any correction made to a link since the "
    "merge, in this unmerge's name. The pointer is the one thing the merge moved and the one "
    "thing the unmerge restores; the pre-image travels with the restoration for comparison."
)

#: Why an unmerge is refused for anything but the merge currently in force.
ONLY_THE_MERGE_IN_FORCE_IS_REVERSED: Final = (
    "An entity merged, unmerged and merged again into the same survivor has two merge rows, and "
    "the older one's pre-image describes the state before the first merge. Reversing it would "
    "clear the newer merge's pointer under the older merge's name. So the entity's merged_at has "
    "to be the merge's decided_at, which is true of exactly one merge, and only while it stands."
)

#: Why an automatic merge consults the install's switch before anything else.
UNATTENDED_MERGING_WAITS_FOR_ITS_SWITCH: Final = (
    "A merge joins two permission surfaces. AutomaticMerge already refuses money and any pair the "
    "cascade did not match, and whether an install merges at all with nobody looking is still the "
    "owner's decision to make, so it is a feature that ships off. A merge a named reviewer decided "
    "is never behind the switch, and turning the switch off undoes nothing already merged."
)

#: Why the answer cache has nothing to drop on a merge.
THE_ANSWER_CACHE_HOLDS_NOTHING_KEYED_BY_AN_ENTITY: Final = (
    "brain.cache has no delete by design: an entry is orphaned when a version or an epoch in its "
    "key moves, and gate.cache_key's parts are the question, the reach, the agent, the policy "
    "and the uploaded tables' epochs, none of them an entity id. Nothing on the answer path reads "
    "er.* either, so no cached answer was assembled from a resolution a merge could make stale. "
    "When an answer is first built from a resolved entity, its key has to carry an epoch this "
    "invalidator moves; until then there is no entry to evict."
)

#: Why memory has nothing to drop on a merge.
MEMORY_HOLDS_NOTHING_KEYED_BY_AN_ENTITY: Final = (
    "mem.persistent, mem.adaptive, mem.learning, mem.correction and mem.mark key on a person, a "
    "scope and a statement, and no column in the mem schema names a canonical entity, so there "
    "is no row a merge could leave answering from before it."
)

#: Why the projection's local id is left as it is.
A_PROJECTED_ROW_KEEPS_THE_ID_IT_WAS_RESOLVED_TO: Final = (
    "proj.record.local_id is the id a record was resolved to, and after a merge that id still "
    "resolves, to the survivor, through the pointer. Rewriting it to the survivor's id is the "
    "rewritten child row merge rejects: it would make the merge a change to the projected source "
    "record (M14.5.2) and erase which entity the record was resolved to, which is what an "
    "unmerge gives back. A reader of the projection follows the pointer, as er.resolved_alias "
    "does; nothing reads local_id yet, and the row holds nothing else about an entity."
)

#: Why a retired row's copy of that id is left as well.
A_RETIRED_ROW_KEEPS_THE_ID_IT_WAS_RETIRED_WITH: Final = (
    "proj.record_retired.local_id is proj.record.local_id copied once, when the source stopped "
    "returning the record (0179), and the application's role may only insert that table, so no "
    "merge could rewrite it and none should: it says which entity the record was resolved to at "
    "the moment it was retired, and that id resolves to the survivor through the pointer as the "
    "live row's does."
)

# ------------------------------------------------------------------------ the figures
#: The columns that would mean a table holds something keyed by a canonical entity id, so a
#: merge has to reach it. Outside `er`, only `proj.record.local_id` and its retired copy may carry
#: one; the test of that is what keeps the three invalidators honest.
ENTITY_KEYED_COLUMNS: Final = frozenset(
    {"entity_id", "local_id", "merged_into", "survivor_id", "merged_id", "restored_id"}
)

#: Where each column of `ENTITY_KEYED_COLUMNS` may live outside the `er` schema, and why.
ENTITY_KEYS_OUTSIDE_RESOLUTION: Final[Mapping[str, str]] = MappingProxyType(
    {
        "proj.record.local_id": A_PROJECTED_ROW_KEEPS_THE_ID_IT_WAS_RESOLVED_TO,
        "proj.record_retired.local_id": A_RETIRED_ROW_KEEPS_THE_ID_IT_WAS_RETIRED_WITH,
    }
)


class MergeRefusedError(ResolutionError):
    """The store would not carry this merge or unmerge out. The reason is a constant above."""


class InvalidationIncompleteError(Exception):
    """The merge committed and at least one surface could not be told. Names the surfaces."""


#: One surface's eviction: handed every entity id a merge or an unmerge made stale on it.
type Invalidator = Callable[[frozenset[str]], Awaitable[None]]


async def nothing_cached_by_entity(entity_ids: frozenset[str]) -> None:
    """The answer cache's invalidator. See `THE_ANSWER_CACHE_HOLDS_NOTHING_KEYED_BY_AN_ENTITY`."""
    del entity_ids


async def nothing_remembered_by_entity(entity_ids: frozenset[str]) -> None:
    """Memory's invalidator. See `MEMORY_HOLDS_NOTHING_KEYED_BY_AN_ENTITY`."""
    del entity_ids


async def projection_keeps_its_resolved_id(entity_ids: frozenset[str]) -> None:
    """The projection's invalidator. See `A_PROJECTED_ROW_KEEPS_THE_ID_IT_WAS_RESOLVED_TO`."""
    del entity_ids


#: The invalidator for each surface `merge.InvalidatedSurface` names, and only those.
INVALIDATORS: Final[Mapping[InvalidatedSurface, Invalidator]] = MappingProxyType(
    {
        InvalidatedSurface.CACHE: nothing_cached_by_entity,
        InvalidatedSurface.MEMORY: nothing_remembered_by_entity,
        InvalidatedSurface.PROJECTION: projection_keeps_its_resolved_id,
    }
)


# ------------------------------------------------------------------- the pre-image as stored
def _ref(one: SourceRef) -> dict[str, str]:
    return {"source": one.source, "entity": one.entity, "source_id": one.source_id}


def _entity_document(one: CanonicalEntity) -> dict[str, Any]:
    return {
        "entity_id": one.entity_id,
        "entity_type": one.entity_type.value,
        "created_at": one.created_at.isoformat(),
        "created_by": one.created_by,
        "created_from": _ref(one.created_from),
        "merged_into": one.merged_into,
        "merged_at": None if one.merged_at is None else one.merged_at.isoformat(),
    }


def pre_image_document(pre: PreImage) -> dict[str, Any]:
    """`merge.PreImage` as `er.merge.pre_image` holds it: the rows, their keys, nothing else."""
    return {
        "survivor": _entity_document(pre.survivor),
        "merged": _entity_document(pre.merged),
        "links": [
            {
                "entity_id": one.entity_id,
                **_ref(one.source),
                "confidence": one.confidence,
                "linked_at": one.linked_at.isoformat(),
            }
            for one in pre.links
        ],
        "aliases": [
            {
                "entity_id": one.entity_id,
                "name": one.name,
                **_ref(one.source),
                "first_seen_at": one.first_seen_at.isoformat(),
            }
            for one in pre.aliases
        ],
        "identifiers": [
            {
                "entity_id": one.entity_id,
                "kind": one.kind.value,
                "key_hash": one.key_hash,
                **_ref(one.source),
                "first_seen_at": one.first_seen_at.isoformat(),
            }
            for one in pre.identifiers
        ],
    }


def _source_of(document: Mapping[str, Any]) -> SourceRef:
    return SourceRef(
        source=document["source"], entity=document["entity"], source_id=document["source_id"]
    )


def _entity_from(document: Mapping[str, Any]) -> CanonicalEntity:
    merged_at = document["merged_at"]
    return CanonicalEntity(
        entity_id=document["entity_id"],
        entity_type=EntityType(document["entity_type"]),
        created_at=datetime.fromisoformat(document["created_at"]),
        created_by=document["created_by"],
        created_from=_source_of(document["created_from"]),
        merged_into=document["merged_into"],
        merged_at=None if merged_at is None else datetime.fromisoformat(merged_at),
    )


def pre_image_from(document: Mapping[str, Any]) -> PreImage:
    """The stored pre-image read back through the domain's own constructors, which refuse a row
    that could not have been captured: a key that is not a digest, a naive instant."""
    return PreImage(
        survivor=_entity_from(document["survivor"]),
        merged=_entity_from(document["merged"]),
        links=tuple(
            Link(
                entity_id=one["entity_id"],
                source=_source_of(one),
                confidence=float(one["confidence"]),
                linked_at=datetime.fromisoformat(one["linked_at"]),
            )
            for one in document["links"]
        ),
        aliases=tuple(
            Alias(
                entity_id=one["entity_id"],
                name=one["name"],
                source=_source_of(one),
                first_seen_at=datetime.fromisoformat(one["first_seen_at"]),
            )
            for one in document["aliases"]
        ),
        identifiers=tuple(
            Identifier(
                entity_id=one["entity_id"],
                kind=IdentifierKind(one["kind"]),
                key_hash=one["key_hash"],
                source=_source_of(one),
                first_seen_at=datetime.fromisoformat(one["first_seen_at"]),
            )
            for one in document["identifiers"]
        ),
    )


# ------------------------------------------------------------------------- reading rows
def _entity_of(row: CanonicalEntityRow) -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=row.entity_id,
        entity_type=EntityType(row.entity_type),
        created_at=row.created_at,
        created_by=row.created_by,
        created_from=SourceRef(
            source=row.created_from_source,
            entity=row.created_from_entity,
            source_id=row.created_from_source_id,
        ),
        merged_into=row.merged_into or "",
        merged_at=row.merged_at,
    )


#: Every entity in the trees the two heads stand in: forwards to each head's survivor, then back
#: from every survivor reached to everything merged into it. Bounded at `MAX_FORWARD_DEPTH` both
#: ways, as `er.resolved_alias` is, so a corrupt cycle is a short walk and `merge` refuses it.
_TREES = text(
    """
    WITH RECURSIVE up(entity_id, merged_into, depth) AS (
            SELECT c.entity_id, c.merged_into, 0 FROM er.canonical c
             WHERE c.entity_id = ANY(:heads)
        UNION ALL
            SELECT c.entity_id, c.merged_into, u.depth + 1
              FROM er.canonical c JOIN up u ON c.entity_id = u.merged_into
             WHERE u.depth < :depth
    ), down(entity_id, depth) AS (
            SELECT u.entity_id, 0 FROM up u WHERE u.merged_into IS NULL
        UNION ALL
            SELECT c.entity_id, d.depth + 1
              FROM er.canonical c JOIN down d ON c.merged_into = d.entity_id
             WHERE d.depth < :depth
    )
    SELECT entity_id FROM up UNION SELECT entity_id FROM down
    """
)


async def _lock(session: AsyncSession, pair: Iterable[str]) -> None:
    """Both entities locked for the transaction, in id order. See `ONE_MERGE_IS_ONE_TRANSACTION`."""
    await session.execute(
        select(CanonicalEntityRow.entity_id)
        .where(CanonicalEntityRow.entity_id.in_(sorted(pair)))
        .order_by(CanonicalEntityRow.entity_id)
        .with_for_update()
    )


async def _graph(
    session: AsyncSession, heads: Sequence[str]
) -> tuple[dict[str, CanonicalEntity], tuple[Link, ...], tuple[Alias, ...], tuple[Identifier, ...]]:
    """The two heads' trees, and every link, alias and identifier naming any entity in them."""
    ids = list(
        (
            await session.execute(_TREES, {"heads": list(heads), "depth": MAX_FORWARD_DEPTH})
        ).scalars()
    )
    rows = (
        await session.execute(
            select(CanonicalEntityRow).where(CanonicalEntityRow.entity_id.in_(ids))
        )
    ).scalars()
    entities = {row.entity_id: _entity_of(row) for row in rows}
    links = tuple(
        Link(
            entity_id=row.entity_id,
            source=SourceRef(source=row.source, entity=row.entity, source_id=row.source_id),
            confidence=row.confidence,
            linked_at=row.linked_at,
        )
        for row in (
            await session.execute(select(EntityLinkRow).where(EntityLinkRow.entity_id.in_(ids)))
        ).scalars()
    )
    aliases = tuple(
        Alias(
            entity_id=row.entity_id,
            name=row.name,
            source=SourceRef(source=row.source, entity=row.entity, source_id=row.source_id),
            first_seen_at=row.first_seen_at,
        )
        for row in (
            await session.execute(select(EntityAliasRow).where(EntityAliasRow.entity_id.in_(ids)))
        ).scalars()
    )
    identifiers = tuple(
        Identifier(
            entity_id=row.entity_id,
            kind=IdentifierKind(row.kind),
            key_hash=row.key_hash,
            source=SourceRef(source=row.source, entity=row.entity, source_id=row.source_id),
            first_seen_at=row.first_seen_at,
        )
        for row in (
            await session.execute(
                select(EntityIdentifierRow).where(EntityIdentifierRow.entity_id.in_(ids))
            )
        ).scalars()
    )
    return entities, links, aliases, identifiers


async def _attribute(session: AsyncSession, actor: str, *, ent_hash: str, trace_id: str) -> None:
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)


# ------------------------------------------------------------------------- invalidating
def by_surface(invalidations: Iterable[Invalidation]) -> dict[InvalidatedSurface, frozenset[str]]:
    """Every entity id each surface was told about, gathered from `merge`'s instructions."""
    gathered: dict[InvalidatedSurface, set[str]] = {}
    for one in invalidations:
        gathered.setdefault(one.surface, set()).add(one.entity_id)
    return {surface: frozenset(ids) for surface, ids in gathered.items()}


async def invalidate(
    invalidations: Iterable[Invalidation],
    invalidators: Mapping[InvalidatedSurface, Invalidator] = INVALIDATORS,
) -> None:
    """Hand each surface every id it holds stale, after the commit (M14.5.5).

    Every surface is asked even when an earlier one failed, because a failure on the cache is no
    reason to leave memory answering from before the merge; the failures are raised together
    afterwards, naming the surfaces and nothing they held.
    """
    failed: list[str] = []
    for surface, ids in sorted(by_surface(invalidations).items()):
        try:
            await invalidators[surface](ids)
        except Exception:
            failed.append(surface.value)
    if failed:
        msg = f"the merge is committed and these surfaces could not be told of it: {failed}"
        raise InvalidationIncompleteError(msg)


# ----------------------------------------------------------------------------- merging
def new_record_id() -> str:
    """A merge's or an unmerge's id: 32 hex, which the ledger's redaction keeps as a digest."""
    return uuid.uuid4().hex


async def merge_entities(
    sessions: async_sessionmaker[AsyncSession],
    *,
    survivor_id: str,
    merged_id: str,
    authority: MergeAuthority,
    at: datetime,
    trace_id: str,
    reason: str = "",
    ent_hash: str = UNSUPPLIED_ENT_HASH,
    merge_id: str | None = None,
    invalidators: Mapping[InvalidatedSurface, Invalidator] = INVALIDATORS,
) -> MergeOutcome:
    """Merge `merged_id` into `survivor_id` on this install, and say what it produced.

    Refused, with nothing written, for an automatic merge while `UNATTENDED_ENTITY_MERGE` is off,
    and for everything `merge.merge` refuses. See the module docstring for the order of the rest.
    """
    async with sessions() as session, session.begin():
        if isinstance(authority, AutomaticMerge) and not await is_on(
            session, UNATTENDED_ENTITY_MERGE
        ):
            raise MergeRefusedError(UNATTENDED_MERGING_WAITS_FOR_ITS_SWITCH)
        await _attribute(session, authority.decided_by, ent_hash=ent_hash, trace_id=trace_id)
        await _lock(session, (survivor_id, merged_id))
        entities, links, aliases, identifiers = await _graph(session, (survivor_id, merged_id))
        outcome = merge(
            survivor_id=survivor_id,
            merged_id=merged_id,
            entities=entities,
            authority=authority,
            at=at,
            merge_id=merge_id or new_record_id(),
            links=links,
            aliases=aliases,
            identifiers=identifiers,
            reason=reason,
        )
        audit = outcome.audit
        await session.execute(
            insert(EntityMergeRow).values(
                merge_id=audit.merge_id,
                survivor_id=audit.survivor_id,
                merged_id=audit.merged_id,
                decided_at=audit.decided_at,
                decided_by=audit.decided_by,
                automatic=audit.automatic,
                confidence=audit.confidence,
                review_ref=authority.review_ref if isinstance(authority, ReviewedMerge) else None,
                evidence=[{"field": one.field, "weight": one.weight} for one in audit.evidence],
                money_left=authority.money.left.value,
                money_right=authority.money.right.value,
                reason=audit.reason,
                pre_image=pre_image_document(outcome.pre_image),
            )
        )
        # `CursorResult` rather than `Result`, which is what an UPDATE returns and the only one
        # with `rowcount`. Cast at a library boundary where proving the match buys nothing.
        moved = cast(
            "CursorResult[Any]",
            await session.execute(
                update(CanonicalEntityRow)
                .where(
                    CanonicalEntityRow.entity_id == outcome.merged.entity_id,
                    CanonicalEntityRow.merged_into.is_(None),
                )
                .values(merged_into=outcome.merged.merged_into, merged_at=outcome.merged.merged_at)
            ),
        )
        if moved.rowcount != 1:
            raise MergeRefusedError(ONE_MERGE_IS_ONE_TRANSACTION)
    await invalidate(outcome.invalidations, invalidators)
    return outcome


async def unmerge_entities(
    sessions: async_sessionmaker[AsyncSession],
    *,
    merge_id: str,
    performed_by: str,
    reason: str,
    at: datetime,
    trace_id: str,
    ent_hash: str = UNSUPPLIED_ENT_HASH,
    unmerge_id: str | None = None,
    invalidators: Mapping[InvalidatedSurface, Invalidator] = INVALIDATORS,
) -> Restoration:
    """Reverse the merge `merge_id` names, from its stored pre-image, if it is the one in force.

    See `AN_UNMERGE_PUTS_BACK_ONLY_WHAT_THE_MERGE_MOVED` and `ONLY_THE_MERGE_IN_FORCE_IS_REVERSED`.
    `merge.unmerge` makes its own refusals on top: a pointer that does not name the survivor the
    pre-image does, a naive instant, and a blank name or reason.
    """
    async with sessions() as session, session.begin():
        await _attribute(session, performed_by, ent_hash=ent_hash, trace_id=trace_id)
        row = await session.get(EntityMergeRow, merge_id)
        if row is None:
            raise MergeRefusedError(ONLY_THE_MERGE_IN_FORCE_IS_REVERSED)
        await _lock(session, (row.survivor_id, row.merged_id))
        entities, _, _, _ = await _graph(session, (row.survivor_id, row.merged_id))
        if entities[row.merged_id].merged_at != row.decided_at:
            raise MergeRefusedError(ONLY_THE_MERGE_IN_FORCE_IS_REVERSED)
        restoration = unmerge(
            pre_image_from(row.pre_image),
            entities=entities,
            merge_id=merge_id,
            unmerge_id=unmerge_id or new_record_id(),
            at=at,
            performed_by=performed_by,
            reason=reason,
        )
        audit = restoration.audit
        await session.execute(
            insert(EntityUnmergeRow).values(
                unmerge_id=audit.unmerge_id,
                merge_id=audit.merge_id,
                survivor_id=audit.survivor_id,
                restored_id=audit.restored_id,
                reversed_at=audit.reversed_at,
                performed_by=audit.performed_by,
                reason=audit.reason,
            )
        )
        before = next(one for one in restoration.entities if one.entity_id == audit.restored_id)
        moved = cast(
            "CursorResult[Any]",
            await session.execute(
                update(CanonicalEntityRow)
                .where(
                    CanonicalEntityRow.entity_id == audit.restored_id,
                    CanonicalEntityRow.merged_into == audit.survivor_id,
                )
                .values(merged_into=before.merged_into or None, merged_at=before.merged_at)
            ),
        )
        if moved.rowcount != 1:
            raise MergeRefusedError(ONLY_THE_MERGE_IN_FORCE_IS_REVERSED)
    await invalidate(restoration.invalidations, invalidators)
    return restoration
