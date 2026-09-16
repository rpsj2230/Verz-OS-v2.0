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

Task ids: M39.5.1.1, M39.5.1.2
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
    Provenance,
    record,
)
from brain.core.entitlement import EntitlementSet
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.object_store import ObjectStore
from brain.ops.retention import DataClass
from brain.ops.storage import ObjectKind, StorageBackend, StorageError, bucket_for
from brain.tables.artifact import ArtifactRow

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

#: The bucket every artifact's bytes go in.
ARTIFACT_BUCKET: Final = bucket_for(ObjectKind.AGENT_ARTIFACT).name


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
    }


def artifact_of(row: ArtifactRow) -> Artifact | None:
    """The record a row holds, or None when it does not construct."""
    try:
        return Artifact(
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
        )
    except (ArtifactError, ValueError) as exc:
        log.warning("artifact row does not construct", artifact=row.artifact_id, error=str(exc))
        return None


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
                session.add(row)
        except Exception:
            await self._take_back(backend, key)
            raise
        return one

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
        return tuple(one for one in (artifact_of(row) for row in rows) if one is not None)


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
