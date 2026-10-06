"""What an agent produced, kept: the bytes in the object store and the record in `agent.artifact`.

`brain.console.agent_output.record` is the one way an artifact record comes to exist and it had
no caller, no table and no bucket. This is where a run hands over what it made. It decides nothing
that module decides: the record, its retention class and its attribution are `record`'s, and who
may see the result is `may_see`'s. What is decided here is the order of the two writes, the key,
and what happens when the second write fails.

**The bytes first and the record second, and a failed record takes its bytes back.** A record
pointing at bytes that never arrived lists an artifact nobody can fetch; bytes with no record are
a copy of somebody's data in a bucket whose lifecycle keeps everything until it is deleted, with
nothing pointing at it and nothing that would ever delete it. The first is the loud failure and
the second the silent one, so the put happens first and a record that does not commit deletes the
object it would have described. A delete that also fails is logged as an error naming the key,
because that is the one object this system has lost track of. See
`BYTES_NOTHING_RECORDS_ARE_A_COPY_NOTHING_WILL_EVER_DELETE`.

**The key carries the retention class and a random identifier, never a title.** `object_key` is
`<prefix>/artifacts/<class>/<id>`. A key built from what the document is called is a sentence
about its content in every bucket listing, and the class is in the key so a lifecycle rule scoped
to that prefix can apply that class's window to the bytes. See
`AN_ARTIFACTS_KEY_SAYS_HOW_LONG_IT_IS_KEPT_AND_NOTHING_ABOUT_WHAT_IT_IS`.

**Written in the caller's name.** `0058`'s insert policy admits a row whose `caller_id` is the
session's principal, and the transaction sets that principal from the record, so the row a run
writes is the row for the person whose question produced it and no other.

**A row that no longer constructs is absent, not a fault**, for `brain.ops.skill_store`'s reason:
one row broken by hand would otherwise answer every reader of the Artifacts screen with a 500.

**What calls `keep` today: nothing in a run.** No agent in this release produces a document, deck,
report, export or image; a tool that renders one is where the call belongs, handing over the run's
own reach as `Produced.reach`. The write path is built and tested so that tool has one thing to
call, and the Artifacts screen reads what it writes.

Rejected: recording first as an intent and putting the bytes second. A put that then failed would
leave a record the screen lists and nobody can fetch, and the table is SELECT and INSERT only, so
nothing here could take the row back.

**A new version supersedes in the same transaction that records it** (`Produced.supersedes`), and
a person's supersession or archive is `change`: both are an `agent.artifact_change` row written in
the changer's name, and what an artifact is now is its row with its changes folded over it
(`artifact_of`). The row that was sent to somebody is never rewritten. `supersede` and `archive`
in `brain.console.agent_output` decide whether a change is allowed, and a producer may supersede
only an artifact of the same agent and kind that its own reach may see.

**The client is checked when it is written and resolved when it is read.** `keep` refuses a client
id that names no canonical entity, and `latest_for_client` reads the neighbourhood of the id it is
given from `er.canonical` and asks `brain.resolution.canonical.family_of` which ids now resolve to
the same client, so the forwarding rule is the resolver's and not a second copy written in SQL.
See `A_CLIENT_NOBODY_CAN_RESOLVE_IS_A_CLIENT_NOBODY_WILL_FIND`.

**Bytes are handed back only against the digest they were recorded with** (`bytes_of`). A file
that changed in the bucket is not the artifact the record describes, and handing it over would be
handing over something nobody produced.

Task ids: M39.5.1.1, M39.5.1.2, M39.5.1.5, M39.5.2.4, M39.8.5
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.console.agent_output import (
    NO_PROVENANCE,
    Artifact,
    ArtifactError,
    ArtifactInput,
    ArtifactKind,
    ArtifactState,
    Provenance,
    archive,
    latest_for_client,
    may_see,
    record,
    supersede,
)
from brain.core.entitlement import EntitlementSet, Grant
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.object_store import ObjectStore
from brain.ops.retention import DataClass
from brain.ops.storage import ObjectKind, StorageBackend, StorageError, bucket_for
from brain.resolution.canonical import (
    MAX_FORWARD_DEPTH,
    CanonicalEntity,
    EntityType,
    ResolutionError,
    SourceRef,
    family_of,
)
from brain.tables.artifact import ArtifactChangeRow, ArtifactRow
from brain.tables.resolution import CanonicalEntityRow

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the bytes go first and a failed record deletes them.
BYTES_NOTHING_RECORDS_ARE_A_COPY_NOTHING_WILL_EVER_DELETE: Final = (
    "An artifact's bytes sit in a bucket whose lifecycle keeps everything until something deletes "
    "it, and the record is the only thing that would. Bytes put and never recorded are a copy of "
    "somebody's data that nothing lists and nothing will ever remove. So the bytes are put first, "
    "and a record that does not commit deletes the object it would have described; a record "
    "pointing at bytes that never arrived is the louder failure and the one left possible."
)

#: Why the key names the class and a random identifier.
AN_ARTIFACTS_KEY_SAYS_HOW_LONG_IT_IS_KEPT_AND_NOTHING_ABOUT_WHAT_IT_IS: Final = (
    "A key is shown in every listing of its bucket, to whoever can list it. One built from a "
    "document's title or file name says what the document is about to somebody who may not read "
    "it. The key is the install's prefix, the artifacts segment, the retention class and a random "
    "identifier, so it says how long the bytes are kept and nothing about what they are."
)

#: What `keep` answers on a process with no object store.
NO_STORE_TO_KEEP_AN_ARTIFACT_IN: Final = (
    "This process is not connected to an object store, so an artifact cannot be kept: its record "
    "would point at bytes that are nowhere."
)

#: Why a client id is checked when an artifact is recorded.
A_CLIENT_NOBODY_CAN_RESOLVE_IS_A_CLIENT_NOBODY_WILL_FIND: Final = (
    "An artifact recorded against a client id that names no canonical entity is found by no "
    "question about any client, because the latest for a client is asked by the ids that client "
    "resolves to. So an id that resolves to nothing is refused when the artifact is recorded, "
    "which is the one moment the producer is still there to be told."
)

#: What `bytes_of` answers when the bucket's copy is not what was recorded.
THE_BYTES_ARE_NOT_WHAT_WAS_RECORDED: Final = (
    "The file in the object store is not the one this artifact recorded, so it is not handed "
    "over: it is not what was produced."
)

#: The bucket every artifact's bytes go in.
ARTIFACT_BUCKET: Final = bucket_for(ObjectKind.AGENT_ARTIFACT).name

#: The neighbourhood of one canonical id: its forwarding chain and every id forwarding into it,
#: each bounded by the resolver's own depth. `family_of` decides the family from these rows.
NEIGHBOURHOOD: Final = text(
    """
    WITH RECURSIVE forward(entity_id, depth) AS (
            SELECT c.entity_id, 0 FROM er.canonical c WHERE c.entity_id = :asked
        UNION
            SELECT c.merged_into, f.depth + 1
            FROM er.canonical c JOIN forward f ON c.entity_id = f.entity_id
            WHERE c.merged_into IS NOT NULL AND f.depth < :depth
    ),
    backward(entity_id, depth) AS (
            SELECT entity_id, 0 FROM forward
        UNION
            SELECT c.entity_id, b.depth + 1
            FROM er.canonical c JOIN backward b ON c.merged_into = b.entity_id
            WHERE b.depth < :depth
    )
    SELECT DISTINCT entity_id FROM backward
    """
)


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.skill_store` sets the same setting.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def _mint() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Produced:
    """What a run hands over when it has made something: the bytes, and what its record needs.

    `reach` is the run's own, `E_run(caller, agent)`, as `record` takes it: its hash goes on the
    record and nothing here computes one. `inputs` decide the retention class through
    `retention_class_for`, so a producer cannot choose a longer window for its own output.
    """

    agent_id: str
    kind: ArtifactKind
    run_id: str
    agent_version: str
    caller_id: str
    reach: EntitlementSet
    inputs: Sequence[ArtifactInput]
    body: bytes
    content_type: str
    provenance: Provenance = NO_PROVENANCE
    #: The canonical client it is for, or empty. Refused if it resolves to nothing.
    client_id: str = ""
    #: The grants `reach` held for what reached the file. See `brain.console.agent_output`.
    drew_on: tuple[Grant, ...] = ()
    #: The artifact this one is a new version of, superseded in the same transaction, or empty.
    supersedes: str = ""


@dataclass(frozen=True)
class Kept:
    """One recorded artifact with what only the store knows: its media type and its key."""

    artifact: Artifact
    content_type: str
    object_key: str
    content_digest: str


def object_key(prefix: str, one: Artifact) -> str:
    """Where one artifact's bytes are. See the reason constant on keys."""
    return f"{prefix}/artifacts/{one.data_class.value}/{one.artifact_id}"


def artifact_values(one: Artifact, *, key: str, content_type: str, digest: str) -> dict[str, Any]:
    """The row one artifact is recorded as, every column named."""
    return {
        "artifact_id": one.artifact_id,
        "agent_id": one.agent_id,
        "kind": one.kind.value,
        "run_id": one.run_id,
        "agent_version": one.agent_version,
        "caller_id": one.caller_id,
        "entitlement_hash": one.entitlement_hash,
        "produced_at": one.at,
        "data_class": one.data_class.value,
        "bytes_stored": one.bytes_stored,
        "content_type": content_type,
        "content_digest": digest,
        "object_key": key,
        "sources": list(one.provenance.sources),
        "knowledge_items": list(one.provenance.knowledge_items),
        "client_id": one.client_id or None,
        "drew_on": [grant.model_dump(mode="json") for grant in one.drew_on],
    }


def folded(one: Artifact, changes: Sequence[ArtifactChangeRow]) -> Artifact:
    """An artifact with its changes applied: superseded, then archived, as the domain allows.

    An archive after a supersession is allowed and leaves no successor named; a supersession after
    an archive is refused by `supersede`, so a pair of rows in that order does not construct and
    the artifact reads as archived, which is the later and narrower of the two.
    """
    by_state = {row.state: row for row in changes}
    superseded = by_state.get(ArtifactState.SUPERSEDED.value)
    if superseded is not None and superseded.superseded_by:
        one = supersede(one, by=superseded.superseded_by)
    if ArtifactState.ARCHIVED.value in by_state:
        one = archive(one)
    return one


def artifact_of(row: ArtifactRow, changes: Sequence[ArtifactChangeRow] = ()) -> Artifact | None:
    """The record a row holds with its changes folded over it, or None when it does not
    construct."""
    try:
        drew_on = tuple(Grant.model_validate(one) for one in row.drew_on or ())
        made = Artifact(
            artifact_id=row.artifact_id,
            agent_id=row.agent_id,
            kind=ArtifactKind(row.kind),
            run_id=row.run_id,
            agent_version=row.agent_version,
            caller_id=row.caller_id,
            entitlement_hash=row.entitlement_hash,
            at=row.produced_at,
            data_class=DataClass(row.data_class),
            bytes_stored=row.bytes_stored,
            provenance=Provenance(
                sources=tuple(row.sources), knowledge_items=tuple(row.knowledge_items)
            ),
            client_id=row.client_id or "",
            drew_on=drew_on,
        )
        return folded(made, changes)
    except (ArtifactError, ValueError) as exc:
        log.warning("artifact row does not construct", artifact=row.artifact_id, error=str(exc))
        return None


def entity_of(row: CanonicalEntityRow) -> CanonicalEntity:
    """A canonical row as the resolver's own record, so `family_of` decides the family."""
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


async def family_in(session: AsyncSession, client_id: str) -> frozenset[str]:
    """Every id `client_id` now shares a surviving entity with, or nothing for an unknown id.

    A broken or cycling chain is nothing too: `family_of` raises on it, and a listing answers a
    corrupt row by leaving it out, for `brain.resolution.canonical._survivor`'s reason.
    """
    ids = (
        (await session.execute(NEIGHBOURHOOD, {"asked": client_id, "depth": MAX_FORWARD_DEPTH}))
        .scalars()
        .all()
    )
    if not ids:
        return frozenset()
    rows = (
        (
            await session.execute(
                select(CanonicalEntityRow).where(CanonicalEntityRow.entity_id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
    try:
        entities = {row.entity_id: entity_of(row) for row in rows}
        return family_of(client_id, entities)
    except (ResolutionError, ValueError) as exc:
        log.warning("client does not resolve", error=type(exc).__name__)
        return frozenset()


class StoredArtifacts:
    """`agent.artifact` read and written, and the bucket the bytes go in.

    `backend` is None on a process with no object store, which can still list what was recorded
    and cannot keep anything new.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        backend: StorageBackend | None,
        prefix: str,
        *,
        mint: Callable[[], str] = _mint,
    ) -> None:
        self._sessions = sessions
        self._backend = backend
        self._prefix = prefix
        self._mint = mint

    async def keep(self, produced: Produced, *, at: datetime) -> Artifact:
        """Put the bytes, record the artifact, and take the bytes back if the record fails."""
        backend = self._backend
        if backend is None:
            raise StorageError(NO_STORE_TO_KEEP_AN_ARTIFACT_IN)
        if not produced.body:
            msg = "an artifact of no bytes is a production that failed, not a document"
            raise ArtifactError(msg)
        one = record(
            artifact_id=self._mint(),
            agent_id=produced.agent_id,
            kind=produced.kind,
            run_id=produced.run_id,
            agent_version=produced.agent_version,
            caller_id=produced.caller_id,
            reach=produced.reach,
            at=at,
            inputs=produced.inputs,
            bytes_stored=len(produced.body),
            provenance=produced.provenance,
            client_id=produced.client_id,
            drew_on=produced.drew_on,
        )
        key = object_key(self._prefix, one)
        await asyncio.to_thread(
            backend.put_object, ARTIFACT_BUCKET, key, produced.body, produced.content_type
        )
        row = ArtifactRow(
            **artifact_values(
                one,
                key=key,
                content_type=produced.content_type,
                digest=hashlib.sha256(produced.body).hexdigest(),
            )
        )
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(_set_config(PRINCIPAL_SETTING, one.caller_id))
                if one.client_id and not await family_in(session, one.client_id):
                    raise ArtifactError(A_CLIENT_NOBODY_CAN_RESOLVE_IS_A_CLIENT_NOBODY_WILL_FIND)
                session.add(row)
                if produced.supersedes:
                    await session.flush()
                    await self._supersede_in(session, produced, one)
        except Exception:
            await self._take_back(backend, key)
            raise
        return one

    async def _supersede_in(self, session: AsyncSession, produced: Produced, one: Artifact) -> None:
        """Mark the artifact `produced` replaces, in the transaction recording its successor.

        Refused unless the earlier one is this agent's, of this kind, current, and visible to the
        producing run's reach: a run cannot retire an artifact it could not have been shown.
        """
        found = await self._one_in(session, produced.supersedes)
        earlier = None if found is None else found.artifact
        if (
            earlier is None
            or earlier.agent_id != one.agent_id
            or earlier.kind is not one.kind
            or not may_see(earlier, produced.reach, one.at)
        ):
            msg = "the artifact a new version names is not one this run may supersede"
            raise ArtifactError(msg)
        supersede(earlier, by=one.artifact_id)
        session.add(
            ArtifactChangeRow(
                artifact_id=earlier.artifact_id,
                state=ArtifactState.SUPERSEDED.value,
                superseded_by=one.artifact_id,
                changed_by=one.caller_id,
                entitlement_hash=one.entitlement_hash,
                trace_id=produced.run_id,
            )
        )

    async def change(
        self,
        artifact_id: str,
        *,
        to: ArtifactState,
        by: str,
        superseded_by: str = "",
        ent_hash: str,
        trace_id: str,
    ) -> Artifact:
        """Supersede or archive one artifact in `by`'s name, as the domain allows, and return it.

        The domain's refusal is raised as `ArtifactError` before anything is written, and the
        change is one row: the artifact's own row is never touched.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, by))
            found = await self._one_in(session, artifact_id)
            if found is None:
                msg = "no artifact to change"
                raise ArtifactError(msg)
            match to:
                case ArtifactState.SUPERSEDED:
                    successor = await self._one_in(session, superseded_by)
                    if successor is None or successor.artifact.agent_id != (
                        found.artifact.agent_id
                    ):
                        msg = "a successor must be another artifact of the same agent"
                        raise ArtifactError(msg)
                    changed = supersede(found.artifact, by=superseded_by)
                case ArtifactState.ARCHIVED:
                    changed = archive(found.artifact)
                case ArtifactState.CURRENT:
                    msg = "an artifact is made current by nothing: a change is never undone"
                    raise ArtifactError(msg)
            session.add(
                ArtifactChangeRow(
                    artifact_id=artifact_id,
                    state=to.value,
                    superseded_by=changed.superseded_by or None,
                    changed_by=by,
                    entitlement_hash=ent_hash,
                    trace_id=trace_id,
                )
            )
        return changed

    async def _one_in(self, session: AsyncSession, artifact_id: str) -> Kept | None:
        row = (
            await session.execute(select(ArtifactRow).where(ArtifactRow.artifact_id == artifact_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        changes = (
            (
                await session.execute(
                    select(ArtifactChangeRow).where(ArtifactChangeRow.artifact_id == artifact_id)
                )
            )
            .scalars()
            .all()
        )
        made = artifact_of(row, changes)
        if made is None:
            return None
        return Kept(
            artifact=made,
            content_type=row.content_type,
            object_key=row.object_key,
            content_digest=row.content_digest,
        )

    async def one(self, artifact_id: str) -> Kept | None:
        """One recorded artifact with its changes, or None. Whoever asks decides who may see it."""
        async with self._sessions() as session:
            return await self._one_in(session, artifact_id)

    async def bytes_of(self, kept: Kept) -> bytes:
        """The recorded artifact's bytes, only when they are what was recorded."""
        backend = self._backend
        if backend is None:
            raise StorageError(NO_STORE_TO_KEEP_AN_ARTIFACT_IN)
        body = await asyncio.to_thread(backend.get_object, ARTIFACT_BUCKET, kept.object_key)
        if hashlib.sha256(body).hexdigest() != kept.content_digest:
            log.error("artifact bytes differ from their record", artifact=kept.artifact.artifact_id)
            raise StorageError(THE_BYTES_ARE_NOT_WHAT_WAS_RECORDED)
        return body

    async def latest_for(
        self, client_id: str, kind: ArtifactKind, requester: EntitlementSet, now: datetime
    ) -> Artifact | None:
        """The newest current artifact of `kind` for the client, among what `requester` may fetch.

        `requester` is whoever is asking as they are now: a run's own reach when an agent asks.
        See `brain.console.agent_output.latest_for_client`.
        """
        async with self._sessions() as session:
            family = await family_in(session, client_id)
            if not family:
                return None
            rows = (
                (
                    await session.execute(
                        select(ArtifactRow).where(
                            ArtifactRow.client_id.in_(family), ArtifactRow.kind == kind.value
                        )
                    )
                )
                .scalars()
                .all()
            )
            entries = await self._folded(session, rows)
        return latest_for_client(entries, family=family, kind=kind, requester=requester, now=now)

    async def _folded(
        self, session: AsyncSession, rows: Sequence[ArtifactRow]
    ) -> tuple[Artifact, ...]:
        ids = [row.artifact_id for row in rows]
        changes: dict[str, list[ArtifactChangeRow]] = {}
        if ids:
            for change in (
                (
                    await session.execute(
                        select(ArtifactChangeRow).where(ArtifactChangeRow.artifact_id.in_(ids))
                    )
                )
                .scalars()
                .all()
            ):
                changes.setdefault(change.artifact_id, []).append(change)
        return tuple(
            one
            for one in (artifact_of(row, changes.get(row.artifact_id, ())) for row in rows)
            if one is not None
        )

    async def of_agent(self, agent_id: str) -> tuple[Artifact, ...]:
        """Every recorded artifact of one agent, with its changes, newest first."""
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ArtifactRow)
                        .where(ArtifactRow.agent_id == agent_id)
                        .order_by(ArtifactRow.produced_at.desc(), ArtifactRow.artifact_id)
                    )
                )
                .scalars()
                .all()
            )
            return await self._folded(session, rows)

    async def _take_back(self, backend: StorageBackend, key: str) -> None:
        """Delete bytes whose record did not commit. See the reason constant on the order."""
        try:
            await asyncio.to_thread(backend.delete_object, ARTIFACT_BUCKET, key)
        except Exception as exc:
            log.error(
                "artifact bytes left with no record",
                bucket=ARTIFACT_BUCKET,
                key=key,
                error=type(exc).__name__,
            )

    async def every(self) -> tuple[Artifact, ...]:
        """Every recorded artifact that constructs, newest first. The screen narrows them."""
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ArtifactRow).order_by(
                            ArtifactRow.produced_at.desc(), ArtifactRow.artifact_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            return await self._folded(session, rows)


def artifacts_for(
    sessions: async_sessionmaker[AsyncSession] | None, store: ObjectStore | None
) -> StoredArtifacts | None:
    """The artifact store this process holds: over its database, keeping only where it has a store.

    None without a database, because the records are rows. A database and no object store still
    reads what was recorded, and refuses to keep anything new with
    `NO_STORE_TO_KEEP_AN_ARTIFACT_IN`.
    """
    if sessions is None:
        return None
    if store is None or store.backend is None:
        return StoredArtifacts(sessions, None, "")
    return StoredArtifacts(sessions, store.backend, store.prefix)
