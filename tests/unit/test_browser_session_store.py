"""A browser session opens on a sealed envelope and closes once, and each end is on the ledger.

The pure half holds the recording's digest to the bytes `write` stores and the recorder's entry to
its rules. The database half builds `0150` at head and drives `brain.browsing.session_store` as
`brain_app`, reading back what `0150`'s trigger appended; it skips when `DATABASE_URL` is unset.
The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M24.3.4
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import AuditRecorder, BrowserSessionChange
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.envelope_store import put_envelope
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.recording import Direction, Recording, record, transcript_digest, write
from brain.browsing.session_store import SessionStoreError, end, start
from brain.browsing.targets import TargetRegistry
from brain.browsing.wire import Kind, encode
from brain.gate.injection import AutonomyTier
from tests.unit.test_browsing_envelope_store import books, reach

if TYPE_CHECKING:
    from brain.tables.audit import AuditEntryRow

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
ASKER = "alex"


def sealed(run_id: str) -> Envelope:
    """A read-only envelope over the invoices surface, asked for by `ASKER`."""
    request = PlanRequest(
        goal=Goal(text="Read this month's invoices", asked_by=ASKER),
        target="books",
        surfaces=("invoices",),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id=run_id,
        reach=reach(),
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def a_recording(run_id: str) -> Recording:
    return record(
        run_id,
        NOW,
        (
            (Direction.TO_RUNNER, b'{"kind":"stop"}'),
            (Direction.FROM_RUNNER, encode(Kind.ENDED, reason="finished")),
        ),
        (),
        keep_pictures=frozenset(),
    )


class Bucket:
    """A storage backend that keeps what it is handed."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = body


# ------------------------------------------------------------------------------- pure
def test_the_digest_a_session_names_is_of_the_transcript_the_bucket_holds() -> None:
    """Computed here from the bytes `write` handed the backend, not from `transcript`. Delete this
    and the digest in the ledger can be of bytes nobody stored, so the entry names no recording."""
    recording = a_recording("run-7")
    bucket = Bucket()

    keys = write(bucket, recording)  # type: ignore[arg-type]

    stored = bucket.objects[keys[0]]
    assert keys[0].endswith("/run-7/transcript.jsonl")
    assert transcript_digest(recording) == hashlib.sha256(stored).hexdigest()


def test_the_recorder_names_a_recording_only_on_an_end_and_only_by_its_digest() -> None:
    """A start with a recording, and a recording that is not a digest, are refused; an end names
    its digest under the run. Delete this and an entry can say a session that has only started
    kept a recording, or name one by a key the ledger stores as the marker."""
    recorder = AuditRecorder(
        AuditChain(), actor_id=ASKER, ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )

    with pytest.raises(ValueError, match="only started"):
        recorder.browser_session(
            run_id="run-7", change=BrowserSessionChange.STARTED, recording="a" * 64
        )
    with pytest.raises(ValueError, match="sha256"):
        recorder.browser_session(
            run_id="run-7", change=BrowserSessionChange.ENDED, recording="browser-runs/x"
        )
    entry = recorder.browser_session(
        run_id="run-7", change=BrowserSessionChange.ENDED, recording="a" * 64
    )
    assert (entry.action, entry.subject) == (AuditAction.BROWSER_SESSION, "session:run-7")
    assert dict(entry.details) == {"change": "ended", "recording": "a" * 64}


# ------------------------------------------------------------------------ with a server
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_browser_session") as url:
        yield url


def _sessions(url: str) -> Any:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_application_sessions

    return make_application_sessions(make_app_engine(normalise_database_url(url)))


async def _open(url: str, run_id: str, trace_id: str, *, seal: bool = True) -> None:
    async with _sessions(url)() as session:
        await session.execute(text("SELECT set_config('app.principal_id', :p, true)"), {"p": ASKER})
        if seal:
            await put_envelope(session, sealed(run_id), agent_id="agent_books")
        await start(session, run_id=run_id, trace_id=trace_id, at=NOW)
        await session.commit()


async def _close(url: str, run_id: str, recording: Recording | None) -> str | None:
    async with _sessions(url)() as session:
        digest = await end(
            session, run_id=run_id, at=NOW + timedelta(minutes=1), recording=recording
        )
        await session.commit()
    return digest


def entries(url: str, run_id: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT action, actor_id, subject, trace_id, details, seq, at, ent_hash, prev_hash,"
        " entry_hash FROM obs.audit_entry WHERE subject = %s ORDER BY seq",
        f"session:{run_id}",
    )


@pytest.mark.needs_db
def test_each_end_of_a_session_is_an_entry_naming_the_asker_the_run_the_trace_and_the_recording(
    head: str,
) -> None:
    """**The trigger as the application reaches it.** Opening appends `started` and closing appends
    `ended` with the transcript's digest, each as the envelope's asker, under the run and the run's
    own trace, with the details the in-memory recorder writes, and each entry reads back as a link
    of the chain. Delete this and a session can open and close with the ledger saying nothing."""
    from brain.audit.chain_check import entry_of

    recording = a_recording("run-audited")
    asyncio.run(_open(head, "run-audited", "trace-browse-1"))
    digest = asyncio.run(_close(head, "run-audited", recording))

    found = entries(head, "run-audited")
    assert digest == transcript_digest(recording)
    assert [(one[0], one[1], one[2], one[3]) for one in found] == [
        ("browser_session", ASKER, "session:run-audited", "trace-browse-1"),
    ] * 2
    recorder = AuditRecorder(
        AuditChain(), actor_id=ASKER, ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    assert [one[4] for one in found] == [
        dict(recorder.browser_session(run_id="r", change=BrowserSessionChange.STARTED).details),
        dict(
            recorder.browser_session(
                run_id="r", change=BrowserSessionChange.ENDED, recording=digest
            ).details
        ),
    ]
    names = ("action", "actor_id", "subject", "trace_id", "details", "seq", "at", "ent_hash")
    for one in found:
        columns = (*names, "prev_hash", "entry_hash")
        # A namespace standing in for the row: `entry_of` reads attributes and nothing else.
        row = cast("AuditEntryRow", SimpleNamespace(**dict(zip(columns, one, strict=True))))
        entry = entry_of(row)
        assert entry is not None and entry.recompute_hash() == entry.entry_hash


@pytest.mark.needs_db
def test_a_session_closed_without_a_recording_names_none(head: str) -> None:
    """The positive half beside the recording: an end with nothing kept is `ended` alone. Delete
    this and a session with no recording can be recorded as one with an empty name."""
    asyncio.run(_open(head, "run-bare", "trace-browse-2"))

    assert asyncio.run(_close(head, "run-bare", None)) is None
    assert [one[4] for one in entries(head, "run-bare")][-1] == {"change": "ended"}


@pytest.mark.needs_db
def test_a_session_opens_only_on_a_sealed_run_and_closes_only_once_on_its_own_recording(
    head: str,
) -> None:
    """A run nobody sealed is refused by the key, a second end finds no open session, and a
    recording of another run is refused before anything is written. Delete this and a session can
    be opened on permissions nobody sealed, or its recording renamed after it ended."""
    with pytest.raises(IntegrityError):
        asyncio.run(_open(head, "run-unsealed", "trace-browse-3", seal=False))

    asyncio.run(_open(head, "run-once", "trace-browse-4"))
    with pytest.raises(SessionStoreError, match="another run"):
        asyncio.run(_close(head, "run-once", a_recording("run-other")))
    asyncio.run(_close(head, "run-once", None))
    with pytest.raises(SessionStoreError, match="no open browser session"):
        asyncio.run(_close(head, "run-once", a_recording("run-once")))

    assert entries(head, "run-unsealed") == []
    assert [one[4]["change"] for one in entries(head, "run-once")] == ["started", "ended"]
