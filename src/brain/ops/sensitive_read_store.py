"""Writing down every read of a sensitive record, from the one place a request finishes.

`brain.audit.reads` declares which reads are written down (personnel records, and any record whose
salary was shown) and refuses every other; `brain.audit.record.AuditRecorder.record_read` built
the entry; and no process called either, so no read had ever been written anywhere. This is the
caller, and it is a `brain.gate.finish.RequestRecorder` rather than a hook in a route for
`brain.gate.finish`'s reason: a record written from the answer route would be missing for every
read that arrives through an automation step, silently, because a short log looks exactly like a
quiet week.

**What decides a row is what the caller was shown.** Each record in the post-redaction payload
is asked of `brain.audit.reads.written_down_because` with the field names it still carries, so a
masked salary is not written down as a salary read and a record the redactor dropped is not a
read at all (`WHAT_WAS_SHOWN_IS_THE_READ_AND_WHAT_THE_RECORD_HOLDS_IS_NOT`,
`A_RECORD_NOBODY_WAS_SHOWN_WAS_NOT_READ`). No other read produces a row, because the function
returns nothing for one; there is no parameter here that could widen the set.

**One row per record, never one per request.** A question that returns three personnel records
is three reads of three people's records, and each of those people asks "who read mine" by their
own subject. One row naming the request would put two of them on the third person's page.

**The row carries the reach digest and the trace of the request itself.** `Finished` carries the
hash of the reach the request was answered at and the trace the gate vouched for, so the ledger
entry the row's trigger writes names the reader's real reach and the request, with no
dependence on session settings that a route might not have made (M24.3.1's placeholder).

**A read that cannot be written fails the request.** `brain.gate.finish` lets each recorder
decide what its own failure means, and says a record the request must not complete without should
raise. This is that kind: the answer is computed but its frames have not been written when the
recorders run, so raising here means a person is not shown a personnel record whose reading went
unrecorded. The measurements (`QuestionRecorder`, `TelemetryRecorder`) run first and catch their
own failures, so this one is last in `brain.app.request_recorders_for` and cannot take them with
it. See `A_SENSITIVE_READ_THAT_CANNOT_BE_WRITTEN_IS_NOT_SHOWN`.

**A cached answer is not a read, because the cache is not read.** `Answered.from_cache` serves a
stored answer and `brain.api_routes.answer` passes `cached=None`, so no cached answer is served
today. The day the cache is wired, a hit discloses the same records again and has to be written
down here as a read, and `disclosed_payload` is the one function that has to learn it.

Task ids: M24.3.2
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import structlog
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import IDENTIFIER
from brain.audit.reads import written_down_because
from brain.core.redaction import ENTITY_KEYS, ID_KEYS, RESERVED_KEYS, ChannelPayload
from brain.gate.answer import Answered
from brain.gate.finish import Finished, ToolCallOutcome
from brain.tables.sensitive_read import AGENT_PATTERN, RECORD_KIND_PATTERN, SensitiveReadRow

log = structlog.get_logger()

#: Why a failure to write a read fails the request.
A_SENSITIVE_READ_THAT_CANNOT_BE_WRITTEN_IS_NOT_SHOWN: Final = (
    "Needs Rupash item 45 promised a member they can see which agents read their HR record. A "
    "read shown and not written breaks that promise silently, and nothing afterwards can tell the "
    "member it happened. The recorders run before the frames are written, so raising here costs "
    "one person one answer and keeps the log true; catching the failure would keep the answer and "
    "make the log a record of the reads that happened to be written."
)

#: The field on a record that names the person it is about, when it names one.
SUBJECT_FIELDS: Final[tuple[str, ...]] = ("principal_id",)

_IDENTIFIER_RE: Final = re.compile(IDENTIFIER)
_KIND_RE: Final = re.compile(RECORD_KIND_PATTERN)
_AGENT_RE: Final = re.compile(AGENT_PATTERN)


class SensitiveReadError(Exception):
    """A sensitive read that cannot be written down, which fails the request that made it."""


@dataclass(frozen=True)
class SensitiveRead:
    """One row to write: who read which record, through which agent, at which reach."""

    reader_id: str
    agent_id: str | None
    record_kind: str
    subject_principal: str | None
    record_id: str | None
    ent_hash: str
    trace_id: str


def _first(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    return next((str(record[key]) for key in keys if record.get(key) not in (None, "")), "")


def disclosed_payload(request: Finished) -> ChannelPayload | None:
    """The records a finished request handed its caller, or None when it handed over none."""
    outcome = request.outcome
    if isinstance(outcome, Answered):
        return None if outcome.composed is None else outcome.composed.payload
    if isinstance(outcome, ToolCallOutcome):
        return outcome.disclosed
    return None


def reads_of(request: Finished) -> tuple[SensitiveRead, ...]:
    """Every read in the declared set this request made, one per record shown.

    A record outside the declared set is passed over whatever its shape, because it is not a read
    anybody writes down. A record inside it that names no id the ledger can file it under raises:
    the message names no record and no field, for the reason refusals here never do.
    """
    payload = disclosed_payload(request)
    if payload is None:
        return ()
    agent = request.agent_id if request.agent_id and _AGENT_RE.match(request.agent_id) else None
    found: list[SensitiveRead] = []
    for record in payload.records:
        kind = _first(record, ENTITY_KEYS)
        shown = [key for key in record if key not in RESERVED_KEYS]
        if not kind or not written_down_because(kind, shown):
            continue
        principal = _first(record, SUBJECT_FIELDS)
        record_id = _first(record, ID_KEYS)
        if not _KIND_RE.match(kind) or not (
            _IDENTIFIER_RE.match(principal) or _IDENTIFIER_RE.match(record_id)
        ):
            # Shown and impossible to file is a read that would go unrecorded, so it fails the
            # request for A_SENSITIVE_READ_THAT_CANNOT_BE_WRITTEN_IS_NOT_SHOWN's reason.
            raise SensitiveReadError(
                "a sensitive record was shown with no kind or id the ledger can file it under"
            )
        by_principal = bool(_IDENTIFIER_RE.match(principal))
        found.append(
            SensitiveRead(
                reader_id=request.origin.principal.id,
                agent_id=agent,
                record_kind=kind,
                subject_principal=principal if by_principal else None,
                record_id=None if by_principal else record_id,
                ent_hash=request.entitlement_hash,
                trace_id=request.origin.trace_id,
            )
        )
    return tuple(found)


def row_values(read: SensitiveRead) -> dict[str, object]:
    """The insert's values. The instant is the database's, which the ledger entry carries."""
    return {
        "reader_id": read.reader_id,
        "agent_id": read.agent_id,
        "record_kind": read.record_kind,
        "subject_principal": read.subject_principal,
        "record_id": read.record_id,
        "ent_hash": read.ent_hash,
        "trace_id": read.trace_id,
    }


class SensitiveReadRecorder:
    """The `RequestRecorder` that writes one `ops.sensitive_read` row per sensitive read."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def finished(self, request: Finished) -> None:
        """Write every read this request made, in one transaction, or raise.

        See `A_SENSITIVE_READ_THAT_CANNOT_BE_WRITTEN_IS_NOT_SHOWN` for why nothing is caught.
        """
        reads = reads_of(request)
        if not reads:
            return
        async with self.sessions() as session, session.begin():
            await session.execute(insert(SensitiveReadRow), [row_values(one) for one in reads])
        log.info("sensitive_read.recorded", trace_id=request.origin.trace_id, reads=len(reads))
