"""Where the metadata ledger's rows are written, and where a service level reading is read from.

`brain.ops.telemetry` decides what a row is and `brain.ops.service_levels` decides what a
reading against the lane objectives says. This is the half that talks to PostgreSQL, and it
decides neither: a row written is a `RequestTelemetry` built through its own checks by
`request_telemetry_of`, and a window read comes back as `Observation`s for the read model to fold.

**The row is inserted by walking `ledger_row`, not by naming its columns again.** A field added to
the record reaches the insert without an edit here, and a column the table lacks is a refused
write the recorder logs. The alternative, an insert listing nineteen names, is the list that
falls behind the record silently: the table would carry a column the insert never fills.

**A request that cannot be recorded does not take its answer with it, and that is the question
recorder's rule rather than a second one.** `TelemetryRecorder` runs in the lane's `finally`,
after the answer exists, beside `brain.ops.question_store.QuestionRecorder`, and follows
`A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`, imported rather than
restated. Two kinds of failure, each with its own log event so a short figure can be explained:
a record the ledger refuses (`telemetry.unrecordable`, which is what a principal the trace grammar
masks produces) and a write the database refuses (`telemetry.unrecorded`).

**Neither log line carries the principal or the refusal's message.** A record is refused because
its principal is a value rather than a name, and the message says which value. Writing it to the
log would put the identifier the ledger refused to hold into a stream governed by who can read
logs, so the line carries the trace id, which `Origin` has already held to the audit grammar, and
the exception's class.

**The window is filtered in SQL and again in the read model, and the two agree by construction.**
`[start, end)` on `received_at`, the partition key, so a reading of one month touches one
partition. `against_target` applies the same window to what it is handed.

**A shape is read by trace id, and the read selects four columns (M21.3.4).** `shapes_for` is
handed the trace ids of recorded costs and reads the trace, the principal, the lane and the tool
count, which is what `brain.ops.telemetry.shapes_by_request` resolves a request's shape from. It
decides nothing about who may see a shape: the rows it returns carry no department, and
`brain.console.spend_view.shape_report` reads a shape only through a cost the reader's usage
grant already admits.

**Model usage is read by window, not by trace id (M27.7.14).** `metered_between` returns the rows
in `[start, end)` whose tokens were counted, on the partition key, because the usage screen's
window can be a year and a list of a year's trace ids in an `IN` clause is a statement nobody
should send. The join to the question a row belongs to is made in the read module on the trace
and the person, which is `A_TRACE_THAT_NAMES_TWO_SHAPES_NAMES_NONE`'s pairing, and a question
and its ledger row share the instant the gate judged the request at, so one window holds both.

Task ids: M30.5.2, M21.3.4, M27.7.14
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

import structlog
from sqlalchemy import Select, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.lane import Lane
from brain.gate.finish import Finished
from brain.ops.question_store import (
    A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT,
)
from brain.ops.reliability import LaneObjective
from brain.ops.service_levels import Observation, ServiceLevels, against_target
from brain.ops.telemetry import (
    MeteredRequest,
    QuestionShape,
    RequestStatus,
    RequestTelemetry,
    request_telemetry_of,
    shapes_by_request,
)
from brain.tables.telemetry import RequestTelemetryRow

log = structlog.get_logger(__name__)

__all__ = [
    "A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT",
    "TelemetryRecorder",
    "metered_between",
    "observed_between",
    "record",
    "service_levels_between",
    "shapes_for",
]


async def record(session: AsyncSession, telemetry: RequestTelemetry) -> None:
    """Append one request's row. Does not commit.

    The row goes to the driver as `ledger_row` produces it. Its closed vocabularies are all
    `StrEnum`s, which the driver writes as their text, so converting them here was a step with
    nothing to do: a mutation removing the conversion survived the database tests, and the
    conversion was removed rather than kept as a line nothing could observe. A test holds every
    enum on the row to being a `str`, which is the property this relies on.
    """
    await session.execute(insert(RequestTelemetryRow).values(**telemetry.ledger_row()))


async def observed_between(
    session: AsyncSession, *, start: datetime, end: datetime
) -> tuple[Observation, ...]:
    """Every request that arrived in `[start, end)`, oldest first, as the read model takes them.

    Selects four columns and not the row. The principal, the hash and the trace are never read,
    so a reading built from this cannot carry them by accident.
    """
    found = await session.execute(
        select(
            RequestTelemetryRow.lane,
            RequestTelemetryRow.status,
            RequestTelemetryRow.duration_ms,
            RequestTelemetryRow.received_at,
        )
        .where(RequestTelemetryRow.received_at >= start, RequestTelemetryRow.received_at < end)
        .order_by(RequestTelemetryRow.received_at)
    )
    return tuple(
        Observation(
            lane=Lane(lane),
            status=RequestStatus(status),
            duration_ms=duration_ms,
            received_at=received_at,
        )
        for lane, status, duration_ms, received_at in found.all()
    )


async def service_levels_between(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    objectives: Sequence[LaneObjective] | None = None,
) -> ServiceLevels:
    """Each lane's measured attainment over `[start, end)` against its objective (M30.5.3)."""
    observed = await observed_between(session, start=start, end=end)
    return against_target(observed, start=start, end=end, objectives=objectives)


async def shapes_for(
    session: AsyncSession, trace_ids: Collection[str]
) -> Mapping[tuple[str, str], QuestionShape | None]:
    """The shape of every request recorded under these trace ids, keyed by trace and principal.

    See the module docstring. Every row under a trace id is read, and the resolution of two
    rows naming different shapes is `shapes_by_request`'s rather than a query's.
    """
    found = await session.execute(
        select(
            RequestTelemetryRow.trace_id,
            RequestTelemetryRow.principal,
            RequestTelemetryRow.lane,
            RequestTelemetryRow.tool_count,
        ).where(RequestTelemetryRow.trace_id.in_(tuple(trace_ids)))
    )
    return shapes_by_request(
        (trace_id, principal, lane, tool_count)
        for trace_id, principal, lane, tool_count in found.all()
    )


def metered_rows(
    start: datetime, end: datetime
) -> Select[tuple[str, str, str | None, str | None, int | None, int | None]]:
    """Every row in `[start, end)` whose tokens were counted, oldest first.

    Six columns and not the row, so nothing about the request beyond who, which model, which
    agent and how many tokens can reach a figure built from it.
    """
    return (
        select(
            RequestTelemetryRow.trace_id,
            RequestTelemetryRow.principal,
            RequestTelemetryRow.model,
            RequestTelemetryRow.agent_version,
            RequestTelemetryRow.tokens_in,
            RequestTelemetryRow.tokens_out,
        )
        .where(RequestTelemetryRow.received_at >= start, RequestTelemetryRow.received_at < end)
        .where(RequestTelemetryRow.tokens_in.is_not(None))
        .where(RequestTelemetryRow.tokens_out.is_not(None))
        .order_by(RequestTelemetryRow.received_at)
    )


async def metered_between(
    session: AsyncSession, *, start: datetime, end: datetime
) -> tuple[MeteredRequest, ...]:
    """The model usage recorded in `[start, end)`, for the usage screen's join."""
    found = await session.execute(metered_rows(start, end))
    return tuple(
        MeteredRequest(
            trace_id=trace_id,
            principal=principal,
            model=model,
            agent_version=agent,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        for trace_id, principal, model, agent, tokens_in, tokens_out in found.all()
        # Both are tested in the statement; the columns are nullable, so the types are.
        if tokens_in is not None and tokens_out is not None
    )


class TelemetryRecorder:
    """The `brain.gate.finish.RequestRecorder` that writes the metadata ledger's row."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def finished(self, request: Finished) -> None:
        """Record how this request went, or log why it could not be, and never raise."""
        trace_id = request.origin.trace_id
        try:
            telemetry = request_telemetry_of(request)
        except Exception as exc:
            # Broad on purpose, and named in the constant imported above:
            # A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT.
            # The class and not the message, which names the value that was refused.
            log.warning("telemetry.unrecordable", trace_id=trace_id, error=type(exc).__name__)
            return
        try:
            async with self.sessions() as session:
                await record(session, telemetry)
                await session.commit()
        except Exception as exc:
            log.warning("telemetry.unrecorded", trace_id=trace_id, error=type(exc).__name__)
