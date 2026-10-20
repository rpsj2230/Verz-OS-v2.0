"""Browser recordings live under the install's object-store prefix, and a schedule removes them.

`brain.browsing.recording` decides what a recording is, where its key falls and which keys are past
their window. It says, in its own docstring, that nothing handed it a store and nothing asked it on
a schedule. This is that half, and it decides nothing the recording module decides.

**A recording goes where the install's other objects go: under its prefix.** The object store keeps
one prefix per install inside each bucket (`brain.ops.object_store.key_prefix`), and the Storage
screen counts a bucket under it. A recording written at the bucket's root would exist and be counted
by nobody, and a sweep listing under the prefix would never find it. `Under` wraps the backend so
`recording.write` and `recording.remove_expired` go on speaking in their own keys while every object
lands, and is listed, under the prefix. Rejected: a prefix parameter on both, which is two functions
that must be told the same string and a third that forgets.

**A hold on a run keeps its recording whatever its age.** A legal hold names audit subjects and
actors (`brain.audit.ledger.LegalHold`), and the ledger files a browser session under
`session:<run id>` as the person who asked for it. A run is held when an active hold names that
subject, names that person, or is company-wide. The sweep reads the holds from the table itself, in
the transaction it decides in, for the reason `brain.ops.schedule_runner.
THE_SWEEP_READS_ITS_OWN_HOLDS` gives about the retention sweep. A hold that is company-wide keeps
every recording and the sweep removes nothing, and says it held them.

**An object with no date in its key is counted and never removed.** That is `recording.removal`'s
rule, and this reports the count on every run, because an object the sweep cannot date is one a
person has to look at.

**Report-only decides and removes nothing.** The same decision is made over the same listing and
the report says what would have been removed.

**No object store connected is a sentence, not an error.** An install without a store has no
recordings to remove, and one that cannot reach its store has not swept; the report says which
reason it was given, and the retention sweep it is part of does not fail for it.

Task ids: M19.6.6, M19.9.11
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from brain.browsing.recording import KEY_RE, Removal, removal
from brain.ops.storage import ObjectKind, StorageBackend, bucket_for
from brain.tables.browsing import BrowserEnvelopeRow
from brain.tables.retention import LegalHoldRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True)
class Under:
    """A storage backend whose every key is under a prefix, seen from outside without it."""

    inner: StorageBackend
    #: Ends in a slash, or is empty.
    prefix: str

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.inner.put_object(bucket_name, f"{self.prefix}{key}", body, content_type)

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.inner.get_object(bucket_name, f"{self.prefix}{key}")

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.inner.delete_object(bucket_name, f"{self.prefix}{key}")

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]:
        for key in self.inner.list_objects(bucket_name, f"{self.prefix}{prefix}"):
            if key.startswith(self.prefix):
                yield key[len(self.prefix) :]


@dataclass(frozen=True)
class Holds:
    """What the active legal holds name. Subjects and actors as the ledger spells them."""

    everything: bool = False
    subjects: frozenset[str] = frozenset()
    actors: frozenset[str] = frozenset()


async def active_holds(session: AsyncSession, now: datetime) -> Holds:
    """The holds in force at `now`, read from the table in the caller's transaction."""
    rows = (
        await session.execute(
            select(LegalHoldRow).where(
                LegalHoldRow.placed_at <= now,
                (LegalHoldRow.released_at.is_(None)) | (LegalHoldRow.released_at > now),
            )
        )
    ).scalars()
    everything = False
    subjects: set[str] = set()
    actors: set[str] = set()
    for row in rows:
        everything = everything or row.all_subjects
        subjects.update(row.subjects)
        actors.update(row.actors)
    return Holds(everything=everything, subjects=frozenset(subjects), actors=frozenset(actors))


async def askers_of(session: AsyncSession, runs: frozenset[str]) -> Mapping[str, str]:
    """Who each run was asked for by, for the runs whose envelope this install still holds."""
    if not runs:
        return {}
    found = await session.execute(
        select(BrowserEnvelopeRow.run_id, BrowserEnvelopeRow.asked_by).where(
            BrowserEnvelopeRow.run_id.in_(sorted(runs))
        )
    )
    return {row[0]: row[1] for row in found.all()}


def runs_held(holds: Holds, askers: Mapping[str, str], runs: frozenset[str]) -> frozenset[str]:
    """The runs a hold keeps: named by subject, asked for by a held actor, or all of them."""
    if holds.everything:
        return runs
    return frozenset(
        run for run in runs if f"session:{run}" in holds.subjects or askers.get(run) in holds.actors
    )


def runs_in(keys: list[str]) -> frozenset[str]:
    """The run ids the dated recording keys name."""
    found = (KEY_RE.match(key) for key in keys)
    return frozenset(one.group(4) for one in found if one is not None)


@dataclass(frozen=True)
class Swept:
    """What one pass found: what was removable, what a hold kept, what could not be dated."""

    found: Removal
    removed: bool

    def sentence(self) -> str:
        verb = "removed" if self.removed else "would remove"
        return (
            f"recordings: {verb} {len(self.found.due)}, kept {self.found.held} under a hold, "
            f"{self.found.undated} with no date in their key"
        )


async def sweep(
    sessions: async_sessionmaker[AsyncSession],
    backend: StorageBackend,
    *,
    now: datetime,
    report_only: bool,
) -> Swept:
    """List the recordings, decide which are past their window and not held, and remove them.

    The holds and the askers are read in one transaction that is the decision's, and the removal
    happens after it with the keys that decision named.
    """
    bucket = bucket_for(ObjectKind.BROWSER_RUN_RECORDING).name
    keys = list(backend.list_objects(bucket, "browser-runs/"))
    runs = runs_in(keys)
    async with sessions() as session, session.begin():
        holds = await active_holds(session, now)
        askers = await askers_of(session, runs)
    held = runs_held(holds, askers, runs)
    found = removal(keys, today=now.astimezone(UTC).date(), held_runs=held)
    if not report_only:
        for key in found.due:
            backend.delete_object(bucket, key)
    return Swept(found=found, removed=not report_only)


def run_recording_sweep_now(
    database_url: str,
    *,
    now: datetime,
    report_only: bool,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`sweep` over this install's object store and database, as the retention schedule runs it.

    The store is built the way the application builds it, from the worker's vault. One that is not
    connected is a sentence in the report and not a failure of the retention sweep it belongs to.
    """
    from brain.ops.object_store import key_prefix, object_store_at_start
    from brain.session import make_app_engine, make_session_factory

    store = object_store_at_start(vault_address, vault_token)
    if store.backend is None:
        return f"recordings: not swept, no object store is connected ({store.unconnected})"
    bucket = bucket_for(ObjectKind.BROWSER_RUN_RECORDING).name
    backend = Under(store.backend, key_prefix(bucket, store.prefix))

    async def run() -> str:
        engine = make_app_engine(database_url)
        try:
            swept = await sweep(
                make_session_factory(engine), backend, now=now, report_only=report_only
            )
            return swept.sentence()
        finally:
            await engine.dispose()

    return asyncio.run(run(), loop_factory=loop_factory)
