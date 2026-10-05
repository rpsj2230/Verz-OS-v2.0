"""The entity registry, written: every resolvable source record gets an entity, its names, its
hashed join keys, its link and its comparison row.

`brain.resolution.entities.observe` turns a projected record into an `Observation`,
`brain.resolution.canonical` defines the four graph rows, and migration 0020 built their tables.
Nothing wrote one: `proj.record.local_id` was empty on every install, because nothing set it.
This is the writer, and `run_registry_now` is what the worker's `entity_resolution` control
starts.

**Every record becomes its own entity first, and matching is a merge.** A record read for the
first time is minted a canonical entity of the type its connector declares, with one link at
confidence one, its observed name as an alias and each usable join key as a digest. Two records
of one client are two entities until the cascade decides otherwise, and what joins them is a merge
moving one pointer (`brain.resolution.merge`). Rejected: deciding the match here, at mint time,
and linking the second record straight to the first entity. That is a merge with no pre-image, no
audit and no unmerge, which is exactly what M14.5 exists to prevent, arrived at through the
writer instead of through the merge. See `EVERY_RECORD_IS_ITS_OWN_ENTITY_UNTIL_A_MERGE`.

**Which records are read is the connectors' own declaration.** `brain.resolution.sources` finds
`ConnectorDeclaration.resolves` on each connector: the entity type, and which projected field is
the name and which a join key. A record of an entity nobody declared is not read, which is the
fail-closed direction: a connector added tomorrow resolves nothing until it says what its
records are.

**The values never land here.** `observe` hashes a join key with the install's pepper inside
`cascade.usable_identifiers`, and what is written is a digest in a column that refuses anything
else (`er.identifier.key_hash`, the five `er.observation.*_hash` columns). The observed name is
written verbatim as an alias, because it is already a projected label in `proj.record` and it is
the evidence a reviewer is shown. See `entities.THERE_IS_NOWHERE_ON_AN_OBSERVATION_TO_PUT_A_
CONTACT_RECORD`.

**The install's blocked values are applied after hashing, by digest (M14.6.1).** The product's
own blocklist runs inside `usable_identifiers` on the raw value; an administrator's list is held
as digests in `er.blocked_value` and compared with the digest, so neither the table nor this
module ever holds the value an administrator blocked. See `A_BLOCKED_VALUE_IS_COMPARED_AS_A_DIGEST`.

**A record read again is observed again, and nothing it said before is unsaid.** Its comparison
row is replaced with what it says now, a new name form is a new alias and a new key a new
identifier, and the old ones stay: an alias and an identifier are observations, and an
observation made on 3 March was made. Its link and its entity do not change.

Scope: the store. The rules are `entities`, `cascade` and `canonical`; nothing here decides a
match.

Task ids: M14.1.1, M14.1.2, M14.1.3, M14.1.4, M14.1.6, M14.6.1, M14.7.3
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy import and_, func, or_, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.projection import ProjectedRecord, ProjectedValue
from brain.connectors.resolves import ResolvesAs
from brain.resolution.canonical import (
    Alias,
    CanonicalEntity,
    Identifier,
    IdentifierKind,
    Link,
    SourceRef,
    identifier_hash,
)
from brain.resolution.cascade import Feature, Observation, phonetic_codes
from brain.resolution.entities import observe, profile_for
from brain.resolution.sources import resolved_entities
from brain.tables.audit import attributed_to
from brain.tables.projection import ProjectedRecordRow
from brain.tables.resolution import (
    CanonicalEntityRow,
    EntityAliasRow,
    EntityIdentifierRow,
    EntityLinkRow,
)
from brain.tables.resolution_registry import BlockedValueRow, ObservationRow

# ------------------------------------------------------------------ written-down reasons
#: Why a record read for the first time is never linked to an existing entity here.
EVERY_RECORD_IS_ITS_OWN_ENTITY_UNTIL_A_MERGE: Final = (
    "Linking a newly read record straight to an entity another record already has is a merge, "
    "and doing it here would be a merge with no pre-image, no audit and no way back. So a record "
    "is minted its own entity, and two records become one only by a merge that moves a pointer "
    "and records why, which is the one way M14.5 allows."
)

#: Why a blocked value is held and compared as a digest.
A_BLOCKED_VALUE_IS_COMPARED_AS_A_DIGEST: Final = (
    "An administrator blocks a value because it is junk on this install, and the value may still "
    "be a contact detail: a shared mailbox, a switchboard number. Held as the same peppered digest "
    "a join key becomes, it is compared exactly where it would have joined, and neither the table "
    "nor the writer ever holds it."
)

#: The reach the registry's writes are attributed at: none, because a job reads for nobody. The
#: same all-zero hash `brain.ops.digest_run.NO_REACH` and the acceptance set-up write with.
JOB_REACH: Final = "0" * 32

#: Who the registry's writes are attributed to. A job, not a person, in the shape the ledger
#: and `er.canonical.created_by` both take.
REGISTRY_ACTOR: Final = "job.entity_resolution"

#: How often the worker runs the registry: twice as long as `brain.ops.connector_sync`'s five
#: minutes, so a record a sync wrote waits at most one sync and one run to get an entity.
EVERY: Final = timedelta(minutes=10)

#: How many records one run reads. A backfill of a large estate takes several runs, each of which
#: commits what it did, rather than one transaction holding every record of every source.
BATCH: Final = 500

#: The confidence of a record's link to the entity minted for it, which is certain.
MINTED_CONFIDENCE: Final = 1.0

#: The corroborating tokens the comparison row carries, by the column that holds each.
TOKEN_COLUMNS: Final[Mapping[Feature, str]] = {
    Feature.COUNTRY: "country_key",
    Feature.POSTCODE: "postcode_key",
}


class RegistryError(Exception):
    """A record the registry was asked to read cannot be read as anything it declares."""


@dataclass(frozen=True)
class Registered:
    """What one run did, in counts. Never a name, a value or a record id."""

    read: int = 0
    minted: int = 0
    reobserved: int = 0
    blocked: int = 0
    #: What comparing the records read with their candidates came to, in counts, once it ran.
    matching: str = ""

    def summary(self) -> str:
        if not self.read:
            return "no source record waited to be registered"
        said = (
            f"{self.read} source record(s) read: {self.minted} new entit(ies) minted, "
            f"{self.reobserved} observed again, {self.blocked} join key(s) refused as blocked"
        )
        return f"{said}; {self.matching}" if self.matching else said


def mint_entity_id() -> str:
    """A new canonical id. Opaque, so nothing about the record can be read off it."""
    return f"ent_{uuid.uuid4().hex}"


def observation_row(observation: Observation, entity_type: str) -> dict[str, object]:
    """The comparison row for one observation: digests, name keys and tokens, nothing else."""
    name = observation.name
    key = name.match_key
    row: dict[str, object] = {
        "source": observation.record.source,
        "entity": observation.record.entity,
        "source_id": observation.record.source_id,
        "entity_type": entity_type,
        "name_collapsed": name.collapsed or None,
        "name_key": key,
        "name_verdict": name.verdict.value,
        "name_fold": name.fold,
        "name_dm": sorted(phonetic_codes(key)) if key else [],
        "verified": sorted(one.value for one in observation.verified),
    }
    for kind in IdentifierKind:
        row[f"{kind.value}_hash"] = observation.identifiers.get(kind)
    for feature, column in TOKEN_COLUMNS.items():
        row[column] = observation.fields.get(feature)
    return row


def without_blocked(
    observation: Observation, blocked: frozenset[tuple[str, str]]
) -> tuple[Observation, int]:
    """The observation with every join key this install blocks removed, and how many were."""
    kept = {
        kind: digest
        for kind, digest in observation.identifiers.items()
        if (kind.value, digest) not in blocked
    }
    removed = len(observation.identifiers) - len(kept)
    if not removed:
        return observation, 0
    return (
        Observation(
            record=observation.record,
            name=observation.name,
            identifiers=kept,
            fields=observation.fields,
            verified=observation.verified & set(kept),
        ),
        removed,
    )


def observation_of(
    row: ProjectedRecordRow,
    declared: ResolvesAs,
    *,
    pepper: str,
    blocked: frozenset[tuple[str, str]],
) -> tuple[Observation, int]:
    """One stored record as the cascade compares it, without this install's blocked keys.

    The one place a record becomes an observation, used by the registry when it writes and by
    the matching when it compares, so the two never disagree about what a record says.
    """
    observed = observe(
        ProjectedRecord(
            source=row.source,
            entity=row.entity,
            source_id=row.source_id,
            last_seen_at=row.last_seen_at,
            fields=cast("Mapping[str, ProjectedValue]", declared.renamed(dict(row.fields or {}))),
        ),
        profile_for(declared.entity_type),
        pepper=pepper,
    )
    return without_blocked(observed.observation, blocked)


async def blocked_digests(session: AsyncSession) -> frozenset[tuple[str, str]]:
    """Every join key this install blocks, as (kind, digest)."""
    return frozenset(
        (kind, digest)
        for kind, digest in (
            await session.execute(select(BlockedValueRow.kind, BlockedValueRow.key_hash))
        ).all()
    )


class StoredRegistry:
    """The registry's writes, over this install's database as the application role."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        declared: Mapping[tuple[str, str], ResolvesAs] | None = None,
    ) -> None:
        self._sessions = sessions
        self._declared = resolved_entities() if declared is None else declared

    async def pending(self, *, limit: int = BATCH) -> tuple[SourceRef, ...]:
        """Live records of a declared entity never observed, or changed since they were."""
        if not self._declared:
            return ()
        record = ProjectedRecordRow
        seen = ObservationRow
        query = (
            select(record.source, record.entity, record.source_id)
            .outerjoin(
                seen,
                and_(
                    seen.source == record.source,
                    seen.entity == record.entity,
                    seen.source_id == record.source_id,
                ),
            )
            .where(
                record.deleted_at.is_(None),
                tuple_(record.source, record.entity).in_(list(self._declared)),
                or_(seen.source.is_(None), record.updated_at > seen.observed_at),
            )
            .order_by(record.source, record.entity, record.source_id)
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return tuple(SourceRef(source=a, entity=b, source_id=c) for a, b, c in rows)

    async def register(
        self,
        refs: Sequence[SourceRef],
        *,
        pepper: str,
        now: datetime,
        by: str = REGISTRY_ACTOR,
        trace_id: str = "entity-resolution",
    ) -> Registered:
        """Mint, link and observe each record, in one transaction. Refuses an undeclared one."""
        if not refs:
            return Registered()
        undeclared = sorted(
            f"{one.source}.{one.entity}"
            for one in refs
            if (one.source, one.entity) not in self._declared
        )
        if undeclared:
            msg = f"{undeclared} declare no record for resolution, so nothing says what they are"
            raise RegistryError(msg)
        keys = [(one.source, one.entity, one.source_id) for one in refs]
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=JOB_REACH, trace_id=trace_id):
                await session.execute(statement)
            records = {
                (row.source, row.entity, row.source_id): row
                for row in (
                    await session.execute(
                        select(ProjectedRecordRow).where(
                            tuple_(
                                ProjectedRecordRow.source,
                                ProjectedRecordRow.entity,
                                ProjectedRecordRow.source_id,
                            ).in_(keys),
                            ProjectedRecordRow.deleted_at.is_(None),
                        )
                    )
                ).scalars()
            }
            linked = {
                (row.source, row.entity, row.source_id): row.entity_id
                for row in (
                    await session.execute(
                        select(EntityLinkRow).where(
                            tuple_(
                                EntityLinkRow.source, EntityLinkRow.entity, EntityLinkRow.source_id
                            ).in_(keys)
                        )
                    )
                ).scalars()
            }
            blocked = await blocked_digests(session)
            minted = reobserved = refused = 0
            for key in keys:
                row = records.get(key)
                if row is None:
                    continue
                declared = self._declared[(key[0], key[1])]
                observation, removed = observation_of(row, declared, pepper=pepper, blocked=blocked)
                refused += removed
                entity_id = linked.get(key)
                if entity_id is None:
                    entity_id = await _mint(session, observation, declared, now=now, by=by)
                    minted += 1
                else:
                    reobserved += 1
                await _observe(session, observation, declared, entity_id=entity_id, now=now)
                await session.execute(
                    update(ProjectedRecordRow)
                    .where(
                        ProjectedRecordRow.source == row.source,
                        ProjectedRecordRow.entity == row.entity,
                        ProjectedRecordRow.source_id == row.source_id,
                        or_(
                            ProjectedRecordRow.local_id.is_(None),
                            ProjectedRecordRow.local_id != entity_id,
                        ),
                    )
                    .values(local_id=entity_id)
                )
        return Registered(
            read=minted + reobserved, minted=minted, reobserved=reobserved, blocked=refused
        )

    async def block(
        self,
        kind: IdentifierKind,
        value: str,
        *,
        pepper: str,
        reason: str,
        by: str,
        trace_id: str,
    ) -> str:
        """Refuse one join key on this install from the next registration on. Returns its digest.

        Hashed exactly as `cascade.usable_identifiers` hashes a join key, so it is compared where
        it would have joined. See `A_BLOCKED_VALUE_IS_COMPARED_AS_A_DIGEST`.
        """
        digest = identifier_hash(kind, value, pepper=pepper)
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.principal_id', :by, true)").bindparams(by=by)
            )
            for statement in attributed_to(actor_id=by, ent_hash=JOB_REACH, trace_id=trace_id):
                await session.execute(statement)
            await session.execute(
                insert(BlockedValueRow)
                .values(kind=kind.value, key_hash=digest, reason=reason, blocked_by=by)
                .on_conflict_do_nothing()
            )
        return digest


async def _mint(
    session: AsyncSession,
    observation: Observation,
    declared: ResolvesAs,
    *,
    now: datetime,
    by: str,
) -> str:
    """A new entity for one record, and the link that makes it that record's. See the module."""
    entity = CanonicalEntity(
        entity_id=mint_entity_id(),
        entity_type=declared.entity_type,
        created_at=now,
        created_by=by,
        created_from=observation.record,
    )
    link = Link(
        entity_id=entity.entity_id,
        source=observation.record,
        confidence=MINTED_CONFIDENCE,
        linked_at=now,
    )
    await session.execute(
        insert(CanonicalEntityRow).values(
            entity_id=entity.entity_id,
            entity_type=entity.entity_type.value,
            created_at=entity.created_at,
            created_by=entity.created_by,
            created_from_source=entity.created_from.source,
            created_from_entity=entity.created_from.entity,
            created_from_source_id=entity.created_from.source_id,
        )
    )
    await session.execute(
        insert(EntityLinkRow).values(
            source=link.source.source,
            entity=link.source.entity,
            source_id=link.source.source_id,
            entity_id=link.entity_id,
            confidence=link.confidence,
            linked_at=link.linked_at,
        )
    )
    return entity.entity_id


async def _observe(
    session: AsyncSession,
    observation: Observation,
    declared: ResolvesAs,
    *,
    entity_id: str,
    now: datetime,
) -> None:
    """The record's names, join keys and comparison row, added to what was observed before."""
    record = observation.record
    observed_name = observation.name.observed.strip()
    if observed_name:
        alias = Alias(entity_id=entity_id, name=observed_name, source=record, first_seen_at=now)
        await session.execute(
            insert(EntityAliasRow)
            .values(
                source=record.source,
                entity=record.entity,
                source_id=record.source_id,
                name=alias.name,
                entity_id=alias.entity_id,
                first_seen_at=alias.first_seen_at,
            )
            .on_conflict_do_nothing()
        )
    for kind, digest in sorted(observation.identifiers.items(), key=lambda one: one[0].value):
        identifier = Identifier(
            entity_id=entity_id, kind=kind, key_hash=digest, source=record, first_seen_at=now
        )
        await session.execute(
            insert(EntityIdentifierRow)
            .values(
                source=record.source,
                entity=record.entity,
                source_id=record.source_id,
                kind=identifier.kind.value,
                key_hash=identifier.key_hash,
                entity_id=identifier.entity_id,
                first_seen_at=identifier.first_seen_at,
            )
            .on_conflict_do_nothing()
        )
    row = observation_row(observation, declared.entity_type.value)
    statement = insert(ObservationRow).values(**row, observed_at=func.statement_timestamp())
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["source", "entity", "source_id"],
            set_={
                **{column: statement.excluded[column] for column in row if column not in KEY},
                "observed_at": func.statement_timestamp(),
            },
        )
    )


#: The three columns that name a record, which a re-observation never rewrites.
KEY: Final = frozenset({"source", "entity", "source_id"})


async def register_pending(
    sessions: async_sessionmaker[AsyncSession], *, pepper: str, now: datetime
) -> Registered:
    """One run: the records waiting, registered, then compared with their candidates.

    The comparison is `brain.resolution.matching_store`'s, over exactly the records this run read,
    so a record is compared once when it arrives and again whenever its source changes it.
    """
    from brain.resolution.matching_store import StoredMatching

    store = StoredRegistry(sessions)
    refs = await store.pending()
    done = await store.register(refs, pepper=pepper, now=now)
    matched = await StoredMatching(sessions).match(refs, pepper=pepper, now=now)
    return replace(done, matching=matched.summary()) if done.read else done


def run_registry_now(
    database_url: str,
    *,
    now: datetime,
    pepper: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> Registered:
    """`register_pending`, from a thread with no event loop of its own, committed.

    The shape `brain.ops.escalation_store.run_expiry_now` takes, for its reasons.
    """
    from brain.session import make_app_engine, make_session_factory

    async def once() -> Registered:
        engine = make_app_engine(database_url)
        try:
            return await register_pending(make_session_factory(engine), pepper=pepper, now=now)
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory)
