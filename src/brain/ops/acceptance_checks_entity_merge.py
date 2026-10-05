"""The install acceptance checks for merging and unmerging entities, one per property M14.5 asks.

Every check plants its own entities in the check's rolled-back transaction: a kept entity and one
to be merged into it, each observed on its own projected record with a link, an alias and a
hashed identifier, the two sharing one observed name, and each side already holding an entity
merged into it earlier, so a family is more than one id. Then it merges and unmerges through
`brain.resolution.merge_store`, the one module that writes either, as a named reviewer, and reads
back what the install's tables, its view and its ledger hold. Nothing a check plants is a real
company's, and none of it outlives the check.

**Reviewed merges only.** `UNATTENDED_ENTITY_MERGE` ships off and an install acceptance run must
not switch on a feature its owner has not, so every merge here is a `ReviewedMerge`, which the
switch never gates. The refusal of an automatic merge while it is off is proved by
`tests/unit/test_merge_store.py`, where turning the switch on touches nobody's install.

**The invalidation check reads what the install holds, not what a fake was told.** It wraps the
install's own invalidators, so the merge reaches the real ones, and then asks the catalogue
whether any table outside entity resolution holds a column keyed by an entity id other than the
projection's `local_id`: today none does, which is what makes each invalidator's eviction of
nothing the right answer, and a table that grows one fails this check on the install it is
deployed to. See `brain.resolution.merge_store.THE_ANSWER_CACHE_HOLDS_NOTHING_KEYED_BY_AN_ENTITY`.

Task ids: M14.5.1, M14.5.2, M14.5.3, M14.5.4, M14.5.5, M14.1.5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import insert, text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, after every smaller key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 432

#: The connector name every planted record is observed on. A name no real connector has.
SOURCE: Final = "acceptance"

#: The entity kind every planted record is, and the kind of entity they resolve to.
KIND: Final = "company"

#: The weights the reviewer was shown, as field names and weights, never what either record said.
EVIDENCE: Final = (("uen", 10.0), ("name", 3.5))

# ------------------------------------------------------------------ what a failure says
NOT_EVERY_ROW_BEFORE: Final = (
    "the merge's stored pre-image did not hold every link, alias and identifier of both families, "
    "and both entities, exactly as they stood before the merge"
)
A_ROW_MOVED: Final = (
    "the merge changed something other than the merged entity's pointer: a link, an alias, an "
    "identifier, the survivor, or a projected source record"
)
POINTER_NOT_MOVED: Final = "the merge did not point the merged entity at the one it was merged into"
NOT_RESTORED: Final = (
    "after the unmerge the entities, links, aliases and identifiers were not exactly what the "
    "merge's pre-image recorded"
)
OLD_ID_LOST: Final = (
    "an id issued before the merge did not resolve to the survivor during it, or to itself after "
    "the unmerge, or an entity merged earlier stopped resolving to its survivor"
)
MERGE_NOT_AUDITED: Final = (
    "the ledger did not hold one entity_merge entry per side naming the reviewer and the merge, "
    "or the merge row did not name who, when, the review and the evidence"
)
UNMERGE_NOT_AUDITED: Final = (
    "the ledger did not hold one entity_unmerge entry per side naming who reversed it, the merge "
    "and the unmerge, or the unmerge row did not name who, when and why"
)
NOT_EVERY_SURFACE_TOLD: Final = (
    "a merge or its unmerge did not hand the cache, memory and the projection every id of both "
    "families"
)
AN_ENTITY_KEY_NOBODY_EVICTS: Final = (
    "a table outside entity resolution holds a column keyed by an entity id, which no merge's "
    "invalidation reaches"
)
PROJECTION_REWRITTEN: Final = (
    "a merge rewrote a projected record's resolved id instead of leaving it to resolve through "
    "the pointer"
)


@dataclass(frozen=True)
class Planted:
    """The check's own entities: two sides, each with one merged into it already."""

    kept: str
    gone: str
    kept_stub: str
    gone_stub: str
    reviewer: str

    @property
    def everyone(self) -> tuple[str, ...]:
        return (self.kept, self.kept_stub, self.gone, self.gone_stub)


def _reviewed(h: Harness, reviewer: str, review: str) -> Any:
    from brain.resolution.guardrails import Evidence
    from brain.resolution.merge import MoneyBearing, MoneyCheck, ReviewedMerge

    return ReviewedMerge(
        reviewer_id=reviewer,
        review_ref=f"acceptance-{h.run}-{review}",
        money=MoneyCheck(left=MoneyBearing.NOT_CHECKED, right=MoneyBearing.NOT_CHECKED),
        evidence=tuple(Evidence(field=field, weight=weight) for field, weight in EVIDENCE),
    )


async def _plant(h: Harness) -> Planted:
    """Four entities on four projected records, then each stub merged into its side."""
    from brain.resolution.canonical import IdentifierKind, identifier_hash
    from brain.resolution.merge_store import merge_entities
    from brain.tables.projection import ProjectedRecordRow
    from brain.tables.resolution import (
        CanonicalEntityRow,
        EntityAliasRow,
        EntityIdentifierRow,
        EntityLinkRow,
    )

    planted = Planted(
        kept=f"acceptance_{h.run}_kept",
        gone=f"acceptance_{h.run}_gone",
        kept_stub=f"acceptance_{h.run}_kept_stub",
        gone_stub=f"acceptance_{h.run}_gone_stub",
        reviewer=h.principal(A, "reviewer"),
    )
    shared = f"Acceptance {h.word()} Pte Ltd"
    for entity_id in planted.everyone:
        record = {"source": SOURCE, "entity": KIND, "source_id": entity_id}
        name = shared if entity_id in (planted.kept, planted.gone) else f"Acceptance {h.word()}"
        await h.execute(
            *h.attributed(),
            insert(CanonicalEntityRow).values(
                entity_id=entity_id,
                entity_type=KIND,
                created_by=h.actor,
                created_from_source=SOURCE,
                created_from_entity=KIND,
                created_from_source_id=entity_id,
            ),
            insert(EntityLinkRow).values(
                **record, entity_id=entity_id, confidence=1.0, linked_at=h.now
            ),
            insert(EntityAliasRow).values(
                **record, name=name, entity_id=entity_id, first_seen_at=h.now
            ),
            insert(EntityIdentifierRow).values(
                **record,
                kind=IdentifierKind.UEN.value,
                key_hash=identifier_hash(IdentifierKind.UEN, h.word(), pepper=h.run),
                entity_id=entity_id,
                first_seen_at=h.now,
            ),
            insert(ProjectedRecordRow).values(
                **record, local_id=entity_id, fields={}, last_seen_at=h.now
            ),
        )
    for side, stub in ((planted.kept, planted.kept_stub), (planted.gone, planted.gone_stub)):
        await merge_entities(
            h.sessions,
            survivor_id=side,
            merged_id=stub,
            authority=_reviewed(h, planted.reviewer, stub),
            at=h.now,
            trace_id=h.trace_id,
            reason="An install acceptance check merging its own entities",
        )
    return planted


async def _rows(h: Harness, ids: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    """Every row a merge could touch for `ids`: the entities, their links, aliases, identifiers,
    and the projected records they were resolved from."""
    questions = {
        "canonical": "SELECT entity_id, entity_type, created_at, created_by, merged_into,"
        " merged_at FROM er.canonical WHERE entity_id = ANY(:ids)",
        "link": "SELECT entity_id, source, entity, source_id, confidence, linked_at FROM er.link"
        " WHERE entity_id = ANY(:ids)",
        "alias": "SELECT entity_id, name, source, entity, source_id, first_seen_at FROM er.alias"
        " WHERE entity_id = ANY(:ids)",
        "identifier": "SELECT entity_id, kind, key_hash, source, entity, source_id, first_seen_at"
        " FROM er.identifier WHERE entity_id = ANY(:ids)",
        "record": "SELECT source, entity, source_id, local_id, fields, last_seen_at, updated_at"
        " FROM proj.record WHERE source = :source AND source_id = ANY(:ids)",
    }
    held: dict[str, list[tuple[Any, ...]]] = {}
    for name, question in questions.items():
        found = await h.execute(
            text(question).bindparams(ids=list(ids), source=SOURCE)
            if ":source" in question
            else text(question).bindparams(ids=list(ids))
        )
        held[name] = sorted(tuple(row) for row in found.all())
    return held


def _as_rows(pre: Any) -> dict[str, list[tuple[Any, ...]]]:
    """A pre-image laid out as `_rows` lays the tables out, for an exact comparison."""
    return {
        "canonical": sorted(
            (
                one.entity_id,
                one.entity_type.value,
                one.created_at,
                one.created_by,
                one.merged_into or None,
                one.merged_at,
            )
            for one in (pre.survivor, pre.merged)
        ),
        "link": sorted(
            (
                one.entity_id,
                one.source.source,
                one.source.entity,
                one.source.source_id,
                one.confidence,
                one.linked_at,
            )
            for one in pre.links
        ),
        "alias": sorted(
            (
                one.entity_id,
                one.name,
                one.source.source,
                one.source.entity,
                one.source.source_id,
                one.first_seen_at,
            )
            for one in pre.aliases
        ),
        "identifier": sorted(
            (
                one.entity_id,
                one.kind.value,
                one.key_hash,
                one.source.source,
                one.source.entity,
                one.source.source_id,
                one.first_seen_at,
            )
            for one in pre.identifiers
        ),
    }


async def _merged(h: Harness, planted: Planted, **kwargs: Any) -> Any:
    from brain.resolution.merge_store import merge_entities

    return await merge_entities(
        h.sessions,
        survivor_id=planted.kept,
        merged_id=planted.gone,
        authority=_reviewed(h, planted.reviewer, "merge"),
        at=h.now,
        trace_id=h.trace_id,
        reason="An install acceptance check merging its own entities",
        **kwargs,
    )


async def _unmerged(h: Harness, merge_id: str, undoer: str, **kwargs: Any) -> Any:
    from brain.resolution.merge_store import unmerge_entities

    return await unmerge_entities(
        h.sessions,
        merge_id=merge_id,
        performed_by=undoer,
        reason="An install acceptance check reversing its own merge",
        at=h.now,
        trace_id=f"{h.trace_id}-unmerge",
        **kwargs,
    )


async def _resolves_to(h: Harness, observed: str) -> list[str]:
    found = await h.execute(
        text(
            "SELECT entity_id FROM er.resolved_alias WHERE observed_entity_id = :observed"
        ).bindparams(observed=observed)
    )
    return sorted(str(one) for one in found.scalars())


# ------------------------------------------------------------- M14.5.1 the pre-image
@check(
    leaves=("M14.5.1",),
    sentence=(
        "Two entities of the check's own, each with an entity merged into it earlier, are merged "
        "by a reviewer; the merge's stored pre-image holds both entities and every link, alias "
        "and identifier of both families exactly as the tables held them before the change."
    ),
)
async def a_merge_keeps_every_affected_row_as_it_stood_before_the_change(h: Harness) -> None:
    from brain.resolution.merge_store import pre_image_from

    planted = await _plant(h)
    before = await _rows(h, planted.everyone)
    outcome = await _merged(h, planted)
    stored = (
        await h.execute(
            text("SELECT pre_image FROM er.merge WHERE merge_id = :merge").bindparams(
                merge=outcome.audit.merge_id
            )
        )
    ).scalar_one()
    kept = _as_rows(pre_image_from(stored))
    wanted = {name: rows for name, rows in before.items() if name != "record"}
    wanted["canonical"] = [
        row for row in wanted["canonical"] if row[0] in (planted.kept, planted.gone)
    ]
    if kept != wanted:
        raise CheckFailedError(NOT_EVERY_ROW_BEFORE)


# ---------------------------------------------------------- M14.5.2 a pointer move
@check(
    leaves=("M14.5.2",),
    sentence=(
        "A reviewer merges two entities of the check's own: the merged entity's pointer and merge "
        "time are the only change, and every link, alias, identifier, the surviving entity and "
        "each projected source record read exactly as before."
    ),
)
async def a_merge_moves_one_pointer_and_changes_no_record_or_child_row(h: Harness) -> None:
    planted = await _plant(h)
    before = await _rows(h, planted.everyone)
    await _merged(h, planted)
    after = await _rows(h, planted.everyone)
    moved = [row for row in after["canonical"] if row[0] == planted.gone]
    if moved != [
        (*row[:4], planted.kept, h.now) for row in before["canonical"] if row[0] == planted.gone
    ]:
        raise CheckFailedError(POINTER_NOT_MOVED)
    unchanged = {name: rows for name, rows in after.items() if name != "canonical"}
    if unchanged != {name: rows for name, rows in before.items() if name != "canonical"} or [
        row for row in after["canonical"] if row[0] != planted.gone
    ] != [row for row in before["canonical"] if row[0] != planted.gone]:
        raise CheckFailedError(A_ROW_MOVED)


# -------------------------------------------------------------- M14.5.3 the unmerge
@check(
    leaves=("M14.5.3", "M14.1.5"),
    sentence=(
        "Two entities of the check's own are merged and the merge is reversed: every entity, "
        "link, alias and identifier is then exactly what the pre-image recorded, the merged "
        "entity's old id resolved to the survivor during the merge and to itself after, and an "
        "entity merged earlier still resolves."
    ),
)
async def an_unmerge_restores_the_pre_image_and_an_old_id_still_resolves(h: Harness) -> None:
    planted = await _plant(h)
    outcome = await _merged(h, planted)
    during = await _resolves_to(h, planted.gone)
    await _unmerged(h, outcome.audit.merge_id, h.principal(A, "undoer"))
    after = await _rows(h, planted.everyone)
    restored = {name: rows for name, rows in after.items() if name != "record"}
    restored["canonical"] = [
        row for row in restored["canonical"] if row[0] in (planted.kept, planted.gone)
    ]
    if restored != _as_rows(outcome.pre_image):
        raise CheckFailedError(NOT_RESTORED)
    if (
        during != [planted.kept]
        or await _resolves_to(h, planted.gone) != [planted.gone]
        or await _resolves_to(h, planted.gone_stub) != [planted.gone]
        or await _resolves_to(h, planted.kept_stub) != [planted.kept]
    ):
        raise CheckFailedError(OLD_ID_LOST)


# --------------------------------------------------------------- M14.5.4 the audit
@check(
    leaves=("M14.5.4",),
    sentence=(
        "A reviewer merges two entities of the check's own and a second person reverses it: the "
        "ledger holds one merge entry per side naming the reviewer and the merge, and one unmerge "
        "entry per side naming the second person, the merge and the unmerge, and the two rows "
        "name who, when, the review, the evidence and why."
    ),
)
async def the_audit_names_who_when_and_on_what_evidence_of_both_acts(
    h: Harness,
) -> None:
    planted = await _plant(h)
    undoer = h.principal(B, "undoer")
    outcome = await _merged(h, planted)
    merge_id = outcome.audit.merge_id
    restoration = await _unmerged(h, merge_id, undoer)
    unmerge_id = restoration.audit.unmerge_id

    async def entries(action: str) -> list[tuple[Any, ...]]:
        found = await h.execute(
            text(
                "SELECT actor_id, subject, details FROM obs.audit_entry"
                " WHERE action = :action AND subject = ANY(:subjects) ORDER BY seq"
            ).bindparams(
                action=action, subjects=[f"entity:{planted.kept}", f"entity:{planted.gone}"]
            )
        )
        return [tuple(row) for row in found.all()]

    merge_row = (
        await h.execute(
            text(
                "SELECT decided_by, decided_at, automatic, review_ref, evidence FROM er.merge"
                " WHERE merge_id = :merge"
            ).bindparams(merge=merge_id)
        )
    ).one()
    sides = (f"entity:{planted.kept}", f"entity:{planted.gone}")
    named = {"merge_id": merge_id}
    if [one for one in await entries("entity_merge") if one[2] == named] != [
        (planted.reviewer, side, named) for side in sides
    ] or tuple(merge_row) != (
        planted.reviewer,
        h.now,
        False,
        f"acceptance-{h.run}-merge",
        [{"field": field, "weight": weight} for field, weight in EVIDENCE],
    ):
        raise CheckFailedError(MERGE_NOT_AUDITED)
    unmerge_row = (
        await h.execute(
            text(
                "SELECT performed_by, reversed_at, merge_id, reason FROM er.unmerge"
                " WHERE unmerge_id = :unmerge"
            ).bindparams(unmerge=unmerge_id)
        )
    ).one_or_none()
    both = {"merge_id": merge_id, "unmerge_id": unmerge_id}
    if (
        await entries("entity_unmerge") != [(undoer, side, both) for side in sides]
        or unmerge_row is None
        or tuple(unmerge_row)[:3] != (undoer, h.now, merge_id)
        or not str(tuple(unmerge_row)[3]).strip()
    ):
        raise CheckFailedError(UNMERGE_NOT_AUDITED)


# ---------------------------------------------------------- M14.5.5 invalidation
#: Every column outside the `er` schema whose name says it holds an entity id. Read as the
#: application role, from the catalogue, which lists every table whatever the role may read.
ENTITY_KEYED = text(
    "SELECT n.nspname || '.' || c.relname || '.' || a.attname"
    " FROM pg_catalog.pg_attribute a"
    " JOIN pg_catalog.pg_class c ON c.oid = a.attrelid"
    " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
    " WHERE c.relkind IN ('r', 'p', 'v', 'm') AND a.attnum > 0 AND NOT a.attisdropped"
    " AND a.attname = ANY(:columns)"
    " AND n.nspname NOT IN ('er', 'pg_catalog', 'information_schema')"
)


@check(
    leaves=("M14.5.5",),
    sentence=(
        "Two entities of the check's own, each with one merged into it earlier, are merged and "
        "unmerged: each time the cache, memory and projection invalidators are handed all four "
        "ids, no table outside entity resolution is keyed by an entity id but the projection's, "
        "and that keeps its resolved ids."
    ),
)
async def a_merge_tells_every_surface_every_id_of_both_families(h: Harness) -> None:
    from brain.resolution.merge import InvalidatedSurface
    from brain.resolution.merge_store import (
        ENTITY_KEYED_COLUMNS,
        ENTITY_KEYS_OUTSIDE_RESOLUTION,
        INVALIDATORS,
        Invalidator,
    )

    told: list[tuple[str, frozenset[str]]] = []

    def through(surface: InvalidatedSurface) -> Invalidator:
        own = INVALIDATORS[surface]

        async def telling(ids: frozenset[str]) -> None:
            told.append((surface.value, ids))
            await own(ids)

        return telling

    invalidators = {surface: through(surface) for surface in InvalidatedSurface}
    planted = await _plant(h)
    before = await _rows(h, planted.everyone)
    outcome = await _merged(h, planted, invalidators=invalidators)
    during = await _rows(h, planted.everyone)
    await _unmerged(h, outcome.audit.merge_id, h.principal(A, "undoer"), invalidators=invalidators)
    every = frozenset(planted.everyone)
    if sorted(told) != sorted([(surface.value, every) for surface in InvalidatedSurface] * 2):
        raise CheckFailedError(NOT_EVERY_SURFACE_TOLD)
    keyed = await h.execute(ENTITY_KEYED.bindparams(columns=sorted(ENTITY_KEYED_COLUMNS)))
    if set(keyed.scalars()) != set(ENTITY_KEYS_OUTSIDE_RESOLUTION):
        raise CheckFailedError(AN_ENTITY_KEY_NOBODY_EVICTS)
    if during["record"] != before["record"]:
        raise CheckFailedError(PROJECTION_REWRITTEN)
