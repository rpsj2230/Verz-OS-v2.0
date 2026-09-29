"""A browser opened on a sealed envelope's run, and closed, each on the record (M24.3.4).

`brain.browsing.envelope_store` keeps what a run was permitted; nothing kept that a browser was
ever opened on it. M24.3.4 asks that an agent's browser session appear in the audit view with its
recording, and until this a session left no row and no entry anywhere. This is the row, and
`0150`'s trigger on it is the entry.

**The ledger entry is the database's, not this module's.** `start` inserts and `end` updates, and
`agent.browser_session`'s trigger appends a `browser_session` entry on each, naming the envelope's
asker as the actor, the run as the subject and the run's own trace. A caller therefore cannot
open a session without the entry, and an operator's statement at a prompt is recorded exactly as a
runner's is, which is the reason every recent member of `brain.audit.ledger.AuditAction` is
written by a trigger. Nothing here names an actor or a trace for the ledger: the actor is read off
the sealed envelope and the trace off the row, so neither can be supplied wrongly from here.

**A session starts only on a sealed envelope, and ends once.** The row's key points at
`agent.browser_envelope`, so a run nobody sealed has nothing to open; `end` moves a row whose
`ended_at` is empty and treats no row moved as a refusal, for the reason
`brain.browsing.envelope_store.record_decision` gives about its own guarded update.

**The recording is named by the digest of what `brain.browsing.recording.write` stores.**
`recording.transcript_digest` is over those exact bytes, so the entry and the object in the bucket
can be checked against each other, and a recording of another run is refused rather than named.

Not built, and said: the control-plane worker that drives a run and would call `start` when the
launcher answers and `end` when the runner reports its end. `brain.browsing.runner` has never run on
a host (see `brain.browsing`), so the install check is today the only caller.

Task ids: M24.3.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.browsing.recording import Recording, transcript_digest
from brain.tables.browsing import BrowserSessionRow

#: Why the entry is written by the database and not by this module.
A_SESSION_IS_ON_THE_RECORD_BECAUSE_ITS_ROW_EXISTS: Final = (
    "A session's ledger entry is appended by the trigger on its row, so there is no way to open "
    "or close a browser that leaves the row and not the entry, and no argument through which a "
    "caller could name a different actor or trace. The actor is the envelope's asker and the trace "
    "is the run's own, both read by the database."
)


class SessionStoreError(Exception):
    """A session that could not be started or ended as asked. Names no run's contents."""


async def start(session: AsyncSession, *, run_id: str, trace_id: str, at: datetime) -> None:
    """Record that a browser was opened on this run's sealed envelope. Does not commit.

    A run with no stored envelope is refused by the foreign key, and a second start by the key.
    """
    await session.execute(
        insert(BrowserSessionRow).values(run_id=run_id, trace_id=trace_id, started_at=at)
    )


async def end(
    session: AsyncSession, *, run_id: str, at: datetime, recording: Recording | None
) -> str | None:
    """Record that this run's browser was closed, naming its recording. Does not commit.

    Returns the digest the entry names, or None when no recording was kept. Raises when the run
    has no open session, which says nothing about whether it had none or had one that ended.
    """
    if recording is not None and recording.run_id != run_id:
        msg = f"the recording handed in is of another run than {run_id!r}"
        raise SessionStoreError(msg)
    digest = None if recording is None else transcript_digest(recording)
    # `CursorResult` rather than `Result`, which is what an UPDATE returns and the only one with
    # `rowcount`. Cast at a library boundary where proving the match buys nothing.
    changed = cast(
        "CursorResult[Any]",
        await session.execute(
            update(BrowserSessionRow)
            .where(BrowserSessionRow.run_id == run_id, BrowserSessionRow.ended_at.is_(None))
            .values(ended_at=at, recording_digest=digest)
        ),
    )
    if changed.rowcount != 1:
        msg = f"run {run_id!r} has no open browser session, so its end was not recorded"
        raise SessionStoreError(msg)
    return digest
