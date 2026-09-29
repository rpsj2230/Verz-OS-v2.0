"""The payload store: a run's trace graph, masked before it is built, read only under its own role.

`brain.ops.tracing` designed the store and nothing built it: `mask` is the only way a span may
leave this process, `PAYLOAD_ROLE` is the separate role that may read one, and `read_payload`
writes the audit row before the read. `brain.ops.trace_sink.CountingTraceSink` dropped every
payload because there was nowhere whose permissions matched. This is that somewhere, and it is
the smallest one that makes M24.3.4's sentence true: the steps of a run, as a graph keyed by the
trace id, holding only masked content, readable only under the separate role.

**Written from the one place a request finishes.** `TraceRecorder` is a
`brain.gate.finish.RequestRecorder`, so a run is traced whichever channel it arrived through, for
the reason `brain.gate.finish` gives against a hook per route. The graph is what the lane already
decided and reports on `Finished`: the request itself, each tool call it started, the source those
calls read, and each model attempt the executor made under the trace, read back from
`ops.model_attempt`, which is where an attempt that never answered is kept. **Nothing is added to
the lane to feed it**, so the graph is exactly as detailed as `Finished` is, and a step it cannot
name is not invented: a tool call names no tool, because `Finished` carries none, for
`brain.gate.finish.A_REFUSED_TOOL_CALL_IS_RECORDED_WITHOUT_WHAT_WAS_REFUSED`'s reason.

**Every step is built as a `Span` and stored as `mask` leaves it**, and there is no other way to a
row: `rows_of` takes spans and returns `mask(span)`'s fields. What survives is `mask`'s allowlist
and nothing more, so a record's values, a person's id and the answer's text reach the store as
shapes. `obs.trace_step`'s check constraints admit only the four strings `mask` leaves in a payload
field, so the database refuses an unmasked payload too, which is the second lock on the same door.

**Read only under `brain_trace_reader`, with the row before the read.** `0150` grants the
application's role INSERT on the steps and no SELECT, and the reader role SELECT and nothing
else, with a membership `brain_app` cannot inherit through. `StoredTraces.read` asks the realm role
first (`tracing.may_read_payloads`, the design's separate role in the identity provider), writes
the `tracing.PayloadRead` row and commits it, and only then takes the reader role for one
transaction and reads. **That is `tracing.read_payload`'s order and not a second copy of its
rule**: that function's recorder is a plain call and a database write is awaited, so the order is
kept here in two transactions, the row committed before the read begins, which is what makes "a
recorder that fails means a payload that was never read" true of a database.

Rejected: widening `CountingTraceSink` into the store. `compose` calls it on the answer path
only, with a reference minted there rather than the trace id, so a sink-built store holds answers
and not refusals, abstentions or tool calls, and cannot be joined to the audit entries the same
run left. `telemetry.py` rejected the sink for its ledger for the same reason.

Rejected: letting the application's role read the steps and relying on the reader function. A
screen written next month that selects from the table as `brain_app` would read every payload with
no row written, and a grant is the one place that refusal cannot be forgotten.

Not built, and said: a route or screen that reads a trace. The Keycloak realm role reaches no
token claim the application reads today, so `realm_roles` is handed in by the caller, and the only
caller is the install check. A retention sweep over the thirty days `tracing.RETENTION` names is
M25.1.4's.

Task ids: M27.1.3, M24.3.4
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.finish import Finished
from brain.ops.sensitive_read_store import disclosed_payload
from brain.ops.telemetry import status_of_finished
from brain.ops.tracing import (
    VALUE_TOKEN_RE,
    PayloadRead,
    Span,
    StepKind,
    mask,
    may_read_payloads,
)
from brain.tables.routing import ModelAttemptRow
from brain.tables.telemetry import TraceReadRow, TraceStepRow

log = structlog.get_logger(__name__)

#: The database role that may read a stored trace, and the only one. `0150` creates it.
TRACE_READER_ROLE: Final = "brain_trace_reader"

#: Written out, so there is no interpolation near a statement. A test holds it to the role.
SET_TRACE_READER_ROLE: Final = "SET LOCAL ROLE brain_trace_reader"

#: The setting `obs.trace_read`'s insert policy compares the reader with.
PRINCIPAL_SETTING: Final = "app.principal_id"

#: A step name when the thing it would name is not system vocabulary.
UNNAMED: Final = "unnamed"

# ------------------------------------------------------------------ written-down reasons
#: Why a trace is stored masked and not as it was.
ONLY_WHAT_MASK_LEAVES_IS_STORED: Final = (
    "A trace outlives the answer it records and is read by an operator who may not be entitled "
    "to the records behind it, so it is the worst place to keep what the redactor let one person "
    "see. Every step is built as a span and stored as tracing.mask leaves it, and the table's own "
    "checks refuse a payload that is anything but a shape, so the store holds what the run did "
    "and never what it said."
)

#: Why the application's own role cannot read a trace.
A_TRACE_IS_READ_UNDER_ITS_OWN_ROLE_AND_AFTER_ITS_ROW: Final = (
    "The application's role may add a step and may not read one. Reading takes the realm role in "
    "the identity provider, a row saying who read which trace and why, committed first, and then "
    "the database role that alone holds SELECT. A screen that selected from the table as the "
    "application would be refused by the database rather than trusted to have asked."
)

#: Why a failed trace write does not fail the request.
A_TRACE_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT: Final = (
    "The trace is written after the answer exists and is read only during an investigation. "
    "Raising would turn an answered question into a fault the asker sees over a record only an "
    "operator reads, so a failure is a warning naming the trace, and the install check reads the "
    "trace back and fails when it is missing."
)


class TraceStoreError(Exception):
    """A trace read that the role or the reason does not admit. Names no trace and no content."""


@dataclass(frozen=True)
class Step:
    """One step of a run's graph before it is stored: where it hangs, what it is, its span."""

    step: int
    parent: int | None
    kind: StepKind
    span: Span


@dataclass(frozen=True)
class StoredStep:
    """One step as the store returns it: every field is what `mask` left."""

    step: int
    parent: int | None
    kind: StepKind
    name: str
    attributes: Mapping[str, Any]
    payload_in: str
    payload_out: str


def _name(value: str | None, fallback: str) -> str:
    """A step's name when it is system vocabulary, and the fallback when it is not or is absent.

    A name is stored as it is, so it is held to the grammar `mask` keeps a value under a safe key
    by, and anything else names nothing rather than being kept.
    """
    if value and VALUE_TOKEN_RE.match(value):
        return value
    return fallback


def _payload_text(request: Finished) -> str:
    """What the run handed its caller, as text, for `mask` to size. Empty when it handed nothing."""
    payload = disclosed_payload(request)
    if payload is None or not payload.records:
        return ""
    return json.dumps(list(payload.records), default=str, sort_keys=True)


def steps_of(
    request: Finished,
    attempts: Sequence[str | None],
    *,
    environment: str,
) -> tuple[Step, ...]:
    """The run's graph, unmasked: the request, its model attempts, its tool calls and their reads.

    `attempts` is each model attempt's outcome in the executor's order, None for one still in
    flight. Pure, so what a graph holds can be tested without a database; `rows_of` is where it is
    masked, and nothing reaches the table any other way.
    """
    usage = request.model_usage
    root: dict[str, object] = {
        "channel": request.origin.channel.value,
        "outcome": status_of_finished(request).value,
        "principal_kind": request.origin.principal.kind.value,
        "trace_id": request.origin.trace_id,
        # Masked, and kept to show it is: a trace reader is not entitled to know who asked.
        "principal": request.origin.principal.id,
    }
    if usage is not None:
        root["model"] = usage.model or UNNAMED
        root["token_count"] = usage.tokens_in + usage.tokens_out
    steps = [
        Step(
            step=0,
            parent=None,
            kind=StepKind.REQUEST,
            span=Span(
                name=_name(request.lane.value, StepKind.REQUEST.value),
                environment=environment,
                attributes=root,
                payload_out=_payload_text(request),
            ),
        )
    ]
    for outcome in attempts:
        steps.append(
            Step(
                step=len(steps),
                parent=0,
                kind=StepKind.MODEL_ATTEMPT,
                span=Span(
                    name=StepKind.MODEL_ATTEMPT.value,
                    environment=environment,
                    attributes={"outcome": outcome or "in_flight"},
                ),
            )
        )
    for _ in range(request.tool_calls):
        call = len(steps)
        steps.append(
            Step(
                step=call,
                parent=0,
                kind=StepKind.TOOL_CALL,
                span=Span(name=StepKind.TOOL_CALL.value, environment=environment),
            )
        )
        if request.connector is not None:
            steps.append(
                Step(
                    step=len(steps),
                    parent=call,
                    kind=StepKind.RETRIEVAL,
                    span=Span(
                        name=_name(request.connector, StepKind.RETRIEVAL.value),
                        environment=environment,
                    ),
                )
            )
    return tuple(steps)


def rows_of(trace_id: str, steps: Iterable[Step]) -> list[dict[str, object]]:
    """Each step as `obs.trace_step` holds it, every span through `mask`.

    See `ONLY_WHAT_MASK_LEAVES_IS_STORED`. The step's name is the one field `mask` copies, which
    is why `steps_of` builds it only from vocabulary.
    """
    rows: list[dict[str, object]] = []
    for one in steps:
        masked = mask(one.span)
        rows.append(
            {
                "trace_id": trace_id,
                "step": one.step,
                "parent": one.parent,
                "kind": one.kind.value,
                "name": masked.name,
                "attributes": dict(masked.attributes),
                "payload_in": masked.payload_in,
                "payload_out": masked.payload_out,
            }
        )
    return rows


class TraceRecorder:
    """The `brain.gate.finish.RequestRecorder` that writes a run's trace graph, masked."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], *, environment: str) -> None:
        self.sessions = sessions
        self.environment = environment

    async def finished(self, request: Finished) -> None:
        """Write this run's graph in one transaction, or log why not, and never raise.

        See `A_TRACE_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`. The class of a
        failure is logged and never its message, which may name the value that was refused.
        """
        trace_id = request.origin.trace_id
        try:
            async with self.sessions() as session, session.begin():
                attempts = (
                    await session.execute(
                        select(ModelAttemptRow.outcome)
                        .where(ModelAttemptRow.trace_id == trace_id)
                        .order_by(ModelAttemptRow.sequence)
                    )
                ).scalars()
                steps = steps_of(request, list(attempts), environment=self.environment)
                await session.execute(insert(TraceStepRow), rows_of(trace_id, steps))
        except Exception as exc:
            log.warning("trace.unrecorded", trace_id=trace_id, error=type(exc).__name__)


class StoredTraces:
    """Reading a stored trace: the realm role, the row, then the reader role. See the module."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def read(
        self,
        *,
        realm_roles: Iterable[str],
        at: datetime,
        actor: str,
        trace_id: str,
        reason: str,
    ) -> tuple[StoredStep, ...]:
        """Every step of one trace, in order, after the read is on record.

        See `A_TRACE_IS_READ_UNDER_ITS_OWN_ROLE_AND_AFTER_ITS_ROW`. A refusal writes nothing, for
        `brain.ops.telemetry.THE_ROLE_COMES_FIRST_AND_THE_ROW_COMES_BEFORE_THE_READ`'s reason: a
        row means somebody read, and a table mixing reads with refusals counts neither.
        """
        if not may_read_payloads(realm_roles):
            msg = "these roles do not admit reading a stored trace"
            raise TraceStoreError(msg)
        event = PayloadRead(at=at, actor=actor, trace_id=trace_id, reason=reason)
        async with self.sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config(:name, :value, true)").bindparams(
                    name=PRINCIPAL_SETTING, value=event.actor
                )
            )
            await session.execute(
                insert(TraceReadRow).values(
                    at=event.at, actor=event.actor, trace_id=event.trace_id, reason=event.reason
                )
            )
        async with self.sessions() as session, session.begin():
            await session.execute(text(SET_TRACE_READER_ROLE))
            found = await session.execute(
                select(
                    TraceStepRow.step,
                    TraceStepRow.parent,
                    TraceStepRow.kind,
                    TraceStepRow.name,
                    TraceStepRow.attributes,
                    TraceStepRow.payload_in,
                    TraceStepRow.payload_out,
                )
                .where(TraceStepRow.trace_id == event.trace_id)
                .order_by(TraceStepRow.step)
            )
            return tuple(
                StoredStep(
                    step=step,
                    parent=parent,
                    kind=StepKind(kind),
                    name=name,
                    attributes=attributes,
                    payload_in=payload_in,
                    payload_out=payload_out,
                )
                for step, parent, kind, name, attributes, payload_in, payload_out in found.all()
            )
