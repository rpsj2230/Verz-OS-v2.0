"""Reading connected sources while somebody waits: all at once, inside a budget, never for long.

`brain.connectors.federation` says what a question's live reads may be: a plan of independent calls
whose cost is its longest chain, a budget per question and per source, a claim that lets twenty
callers make one fetch, and a notice that names only what the asker could already see. It runs
nothing, by design. `brain.connectors.throttle` and `brain.ops.token_bucket` say what sits in front
of a source: the bucket, the breaker, the retry and the numbers. They run nothing either. **Until
this module no process ran any of it, so no question was ever answered from a live read, and the
owner's rule that connectors keep a minimal index and read every value live at question time
(needs-rupash 99) had a policy and no executor.** This is the executor, and it is the only place
those pieces meet a clock.

**The budget is a constant with a reason, and it is the owner's.** Every call of one question starts
together and is cut off at `LIVE_READ_TIMEOUT_MS`; the question's reads together end by
`LIVE_READ_BUDGET_MS` whatever any source is doing, and a source that has not answered by then is
left out and named rather than waited for. See `A_PERSON_IS_NEVER_KEPT_WAITING_FOR_A_SLOW_SOURCE`.
The budget is the length of the deepest chain `federation.FanOutPlan` accepts, so a plan the plan
check admits is a plan this can run, and `read_live` refuses one it cannot before any call is made.

**Parallel within a wave, in order between waves (M11.5.2).** `FanOutPlan.waves` groups the calls; a
wave's calls run concurrently and the wave costs its slowest member, so three independent sources
cost one timeout rather than three. A call that needs another call's answer waits for its wave and
is built from what came back (`LiveCall.derive`), and a call whose parent did not answer is not
made.

**Everything in front of a source is applied per call, and only the calls that reach it pay.** The
breaker is asked first and refuses without waiting (M11.3.2); the bucket then takes a token, and a
wait it asks for is waited only when it fits inside what is left of the budget (M11.3.1, M11.3.5); a
source with no verified ceiling is not read at all, for `throttle.UnmeasuredSourceError`'s reason. A
refusal is retried only when `throttle.retry_delay`, jitter included, fits inside the budget
(M11.3.3), which in practice means only a source that said how briefly to wait. **A source that
timed out is not asked again in the same question**: see
`A_SOURCE_THAT_TIMED_OUT_IS_NOT_ASKED_AGAIN_IN_THE_SAME_QUESTION`. Every call leaves a
`throttle.CallRecord`, and `LiveThrottle.metrics` is `throttle.measure` over them with the calls in
flight as the concurrency (M11.3.4).

**One fetch serves every question asking the same thing at the same moment (M11.5.4)**, for
`federation.COALESCING_IS_SAFE_BECAUSE_CONNECTORS_DO_NOT_DECIDE`'s reason: the rows are redacted
afterwards at each asker's own reach. **Except a read under the asker's own credentials**, which the
source itself narrowed to that asker, so it is shared with nobody and never replaced by a read under
the service's key (M11.2.5). See `A_DELEGATED_READ_IS_NEVER_SHARED_OR_UPGRADED`.

**What could not be read is carried out, never guessed round.** `LiveRead.partial` is
`federation.PartialAnswer`: its `notice` names a failed source only to an asker whose catalogue
already disclosed it and says part of the answer is unavailable to anybody else (M11.5.5), and its
`trace_lines` are written to the operator's log here with every source and reason.

Rejected: a thread pool per question with a join timeout. A thread cannot be cancelled, so the join
would return on time and leave the call running against the source's allowance; the calls here are
awaitables under `asyncio.wait_for`, and a source reached through a blocking client is given the
same timeout at its socket, which is `brain.ops.live_read_run`'s.

Rejected: holding the claims in Valkey now, as `federation.SingleFlight` anticipates. Two processes
asking one source at one moment would each fetch once, which is a doubling rather than a stampede,
and a network round trip in front of every live read would spend part of the budget this module
exists to keep.

Scope: nothing here opens a connection, reads a vault or knows a vendor. The sources, the clock, the
jitter and the sleep are handed in.

Task ids: M11.5.1, M11.5.2, M11.5.3, M11.5.4, M11.5.5, M11.9.2, M11.2.5, M11.3.1, M11.3.2, M11.3.3
Task ids: M11.3.4, M11.3.5
"""

from __future__ import annotations

import asyncio
import secrets
from collections import Counter, deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final, Protocol

import structlog

from brain.connectors.contract import FetchRequest, identity_mode_default
from brain.connectors.federation import (
    FEDERATION_TIMEOUT_MS,
    BudgetState,
    CallBudget,
    FailureReason,
    FanOutPlan,
    FederationError,
    FlightRole,
    PartialAnswer,
    SourceCall,
    SourceFailure,
    flight_key,
)
from brain.connectors.throttle import (
    DEFAULT_METRIC_WINDOW,
    CallOutcome,
    CallRecord,
    ConnectorMetrics,
    connector_breaker,
    is_retryable,
    measure,
    record_outcome,
    retry_delay,
)
from brain.connectors.transports import SourceRecord
from brain.core.envelope import IdentityMode, TypedResult
from brain.models.routing import CircuitBreaker
from brain.ops.token_bucket import BucketState, TokenBucketError

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons

#: The owner's rule for how long a person waits on a connected source (needs-rupash 99).
A_PERSON_IS_NEVER_KEPT_WAITING_FOR_A_SLOW_SOURCE: Final = (
    "Every live read a question needs starts at once, each is cut off at its own timeout, and the "
    "question's reads together end by the live read budget whatever any source is doing. A source "
    "that has not answered by then is left out of the answer and named to an asker who could "
    "already see it, and the operator's log gets the full list. Waiting for it instead would make "
    "the slowest system the company connects the speed of every answer, and the person who asked "
    "would learn which system that was from a spinner rather than from a sentence."
)

#: Why a timeout ends a source's part in one question.
A_SOURCE_THAT_TIMED_OUT_IS_NOT_ASKED_AGAIN_IN_THE_SAME_QUESTION: Final = (
    "A source that used its whole timeout is slow now, and asking again spends a second timeout "
    "of the person's wait on the same slowness, with the budget allowing exactly one more. A "
    "refusal that came back quickly with a short stated wait is different: it is the source "
    "saying when it will answer, and that retry is made when the wait fits inside the budget."
)

#: Why a read under the asker's own credentials is kept to that asker.
A_DELEGATED_READ_IS_NEVER_SHARED_OR_UPGRADED: Final = (
    "A read under the asker's own credentials was narrowed by the source to what that person may "
    "see there, which is a second check independent of ours. Sharing it with another asker would "
    "hand them the first asker's view of the source, and falling back to the connection's service "
    "key when the asker has no credential of their own would drop the source's check without "
    "anybody deciding to. So a delegated read is keyed to its asker and has no substitute."
)

# ------------------------------------------------------------------------ the budget

#: How long one call to one source may take while somebody waits, in milliseconds (M11.5.1).
#: `federation.FEDERATION_TIMEOUT_MS`, whose comment argues the figure from the answer lane's
#: targets; named again here because this is the module that enforces it.
LIVE_READ_TIMEOUT_MS: Final = FEDERATION_TIMEOUT_MS

#: How long one question's live reads may take in all, in milliseconds, retries and waits
#: included. See `A_PERSON_IS_NEVER_KEPT_WAITING_FOR_A_SLOW_SOURCE`.
#:
#: Two timeouts: one wave of independent calls, then one call that waits on another, which is the
#: deepest chain `federation.FanOutPlan.assert_within` admits. It is a fifth of the answer lane's
#: 95th percentile objective, so a model call after it keeps the rest, and it is above the fast
#: lane's whole objective, which is why a request that read live is recorded under the answer lane.
LIVE_READ_BUDGET_MS: Final = 2 * LIVE_READ_TIMEOUT_MS

#: How many times one call is made, the first included. Two, because the only retry that can fit
#: inside the budget is one the source asked for briefly; a third would be a loop.
MAX_ATTEMPTS_PER_CALL: Final = 2

#: The largest fraction a retry's wait is lengthened by. Only ever lengthens, as in
#: `brain.ops.limits.backoff_seconds`, so two askers refused at once do not return at once.
JITTER_FRACTION: Final = 0.1

#: How many completed calls `LiveThrottle` keeps for its metrics. Enough for several minutes of
#: the estate's traffic, and bounded, because a metrics buffer nothing trims is a slow leak.
METRIC_RECORDS_KEPT: Final = 5_000

#: The filter a live read of one record carries: the id its index row holds. A connector's
#: `declaration.LiveLookup` maps it onto the source's own query; nothing else is filtered on but
#: the range below.
RECORD_ID_FILTER: Final = "id"

#: The second filter a live read may carry, and only for a source declaring a report: the one range
#: a figure tool asked for, as `brain.connectors.date_range.DateWindow.text` writes it (M11.7.1).
RANGE_FILTER: Final = "range"

#: The detail a call carries when the question ran out of time before or while it waited.
BUDGET_SPENT: Final = "the question's live read budget was spent"

_RANDOM: Final = secrets.SystemRandom()


def jitter() -> float:
    """A fraction in `[0, JITTER_FRACTION)`, from the system's source of randomness."""
    return _RANDOM.uniform(0.0, JITTER_FRACTION)


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class LiveCall:
    """One live read of one source: what to ask for, whose credentials, and what it waits on.

    `identity_mode` defaults to the requester's own credentials (`contract.identity_mode_default`),
    and a service read is one somebody declared (M11.2.5). `derive` builds the request from the
    answers of the calls in `depends_on`, for a read that needs another's result as its argument;
    it is None for the ordinary independent call, whose `request` is used as it stands.
    """

    call_id: str
    connector: str
    request: FetchRequest
    identity_mode: IdentityMode = field(default_factory=identity_mode_default)
    depends_on: tuple[str, ...] = ()
    timeout_ms: int = LIVE_READ_TIMEOUT_MS
    derive: Callable[[Mapping[str, TypedResult[SourceRecord]]], FetchRequest] | None = field(
        default=None, compare=False
    )

    def planned(self) -> SourceCall:
        """This call as `federation.FanOutPlan` checks it."""
        return SourceCall(
            call_id=self.call_id,
            connector=self.connector,
            entity=self.request.entity,
            timeout_ms=self.timeout_ms,
            depends_on=self.depends_on,
        )


@dataclass(frozen=True)
class LiveReply:
    """What one call to a source came back with, as the connector's own reading classified it.

    `retry_after_seconds` is what the source said to wait, or None when it said nothing, which
    `throttle.retry_delay` treats as the longest wait rather than none.
    """

    outcome: CallOutcome
    rows: TypedResult[SourceRecord] | None = None
    retry_after_seconds: float | None = None


class LiveSource(Protocol):
    """One source, bound to one credential, read once per call. Never raises for the network."""

    def __call__(self, request: FetchRequest) -> Awaitable[LiveReply]: ...


class LiveSources(Protocol):
    """What is connected now, and how each connected source is read while somebody waits."""

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        """The credentials a live read of this pair runs under, or None when it is not read live."""
        ...

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> LiveSource | None:
        """The source under credentials of this mode for this asker, or None when there are none.

        None is final. See `A_DELEGATED_READ_IS_NEVER_SHARED_OR_UPGRADED`: a source holding only a
        service key answers None for a delegated read rather than reading it with that key.
        """
        ...


@dataclass(frozen=True)
class LiveRead:
    """What one question's live reads produced: the rows by call, what failed, and how long.

    `rows` holds a call only when it answered. `coalesced` names the calls that were served by a
    fetch another question was already making, which is the evidence M11.5.4 is working.
    """

    rows: Mapping[str, TypedResult[SourceRecord]]
    partial: PartialAnswer
    elapsed_ms: float
    coalesced: tuple[str, ...] = ()


# ------------------------------------------------------------------ in front of a source


@dataclass(frozen=True)
class Admission:
    """Whether one call may go now: refused with a reason, asked to wait, or admitted."""

    refused: FailureReason | None = None
    detail: str = ""
    wait_seconds: float = 0.0


@dataclass
class LiveThrottle:
    """Every connector's bucket, breaker and recent calls, for one process.

    One per process rather than one per question, because each of the three is about the source:
    a breaker opened by one question's timeouts is what spares the next question the wait, and a
    bucket per question would let every question spend a whole burst. Mutated only by synchronous
    methods, so on one event loop there is no interleaving to guard against.
    """

    buckets: BucketState = field(default_factory=BucketState)
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    records: deque[CallRecord] = field(default_factory=lambda: deque(maxlen=METRIC_RECORDS_KEPT))
    in_flight: Counter[str] = field(default_factory=Counter)

    def breaker(self, connector: str) -> CircuitBreaker:
        return self.breakers.get(connector) or connector_breaker(connector)

    def admit(self, connector: str, *, now: datetime) -> Admission:
        """Ask the breaker, then the bucket, and claim the breaker's admission last.

        The breaker is asked without claiming first, so a call the bucket then refuses has not
        taken the half-open probe from the call that could have used it. A connector with no
        verified ceiling is refused here: `brain.ops.token_bucket` will not invent one.
        """
        breaker = self.breaker(connector)
        if not breaker.admits(now):
            return Admission(refused=FailureReason.CIRCUIT_OPEN)
        try:
            decision, buckets = self.buckets.take(connector, now=now)
        except TokenBucketError:
            return Admission(refused=FailureReason.NOT_SERVING, detail="no verified ceiling")
        # Kept either way: a refused take refills without spending, and dropping it loses time.
        self.buckets = buckets
        if not decision.admitted:
            return Admission(wait_seconds=decision.retry_after_seconds)
        claimed, admitted = breaker.try_admit(now)
        self.breakers[connector] = claimed
        if not admitted:
            return Admission(refused=FailureReason.CIRCUIT_OPEN)
        return Admission()

    def record(
        self,
        connector: str,
        outcome: CallOutcome,
        *,
        latency_ms: float,
        now: datetime,
        jitter: float = 0.0,
    ) -> None:
        """One completed call: to the breaker, which ignores what is not ill health, and the log."""
        self.breakers[connector] = record_outcome(
            self.breaker(connector), outcome, now=now, jitter=jitter
        )
        self.records.append(
            CallRecord(at=now, connector=connector, outcome=outcome, latency_ms=latency_ms)
        )

    def metrics(
        self, connector: str, *, now: datetime, window: timedelta = DEFAULT_METRIC_WINDOW
    ) -> ConnectorMetrics:
        """`throttle.measure` over this process's calls, with the calls in flight now."""
        return measure(
            connector,
            tuple(self.records),
            now=now,
            window=window,
            concurrency=self.in_flight[connector],
        )


# ------------------------------------------------------------------ one fetch for many


@dataclass(frozen=True)
class Fetched:
    """One call's result: rows, or the failure that stands in for them."""

    rows: TypedResult[SourceRecord] | None = None
    failure: SourceFailure | None = None


class LiveFlights:
    """The fetches in progress in this process, so the same read asked twice is made once.

    A follower awaits the leader's task through `asyncio.shield`, so a follower that gives up
    cancels its own wait and never the fetch another question is relying on.
    """

    def __init__(self) -> None:
        self._held: dict[str, asyncio.Task[Fetched]] = {}

    def key(self, call: LiveCall, request: FetchRequest, *, asker: str) -> str:
        """What makes two reads the same read. The asker is part of it only for a delegated read.

        See `A_DELEGATED_READ_IS_NEVER_SHARED_OR_UPGRADED` and `federation.flight_key`, which
        leaves the asker out for the service read and argues why.
        """
        base = flight_key(call.connector, request.entity, request.filters)
        shaped = f"{base}|limit={request.limit}|cursor={request.cursor}|{call.identity_mode}"
        if call.identity_mode is IdentityMode.SERVICE:
            return shaped
        return f"{shaped}|asker={asker}"

    def held(self) -> tuple[str, ...]:
        return tuple(sorted(self._held))

    async def join(
        self, key: str, start: Callable[[], Awaitable[Fetched]], *, wait_seconds: float
    ) -> tuple[Fetched, FlightRole]:
        """Lead the fetch for this key, or follow the one already running. Raises on the wait."""
        task = self._held.get(key)
        role = FlightRole.FOLLOWER
        if task is None:
            role = FlightRole.LEADER
            task = asyncio.ensure_future(start())
            self._held[key] = task
            task.add_done_callback(lambda done: self._forget(key, done))
        fetched = await asyncio.wait_for(asyncio.shield(task), wait_seconds)
        return fetched, role

    def _forget(self, key: str, done: asyncio.Task[Fetched]) -> None:
        if self._held.get(key) is done:
            del self._held[key]
        if not done.cancelled():
            # Retrieved here so a fetch every waiter gave up on is not reported as unobserved.
            done.exception()


# ------------------------------------------------------------------------ the executor


@dataclass
class _Question:
    """One question's reads in progress. Private, and never kept past `read_live`."""

    calls: Sequence[LiveCall]
    sources: LiveSources
    asker: str
    throttle: LiveThrottle
    flights: LiveFlights
    clock: Callable[[], datetime]
    budget: CallBudget
    deadline: float
    jitter: Callable[[], float]
    sleep: Callable[[float], Awaitable[object]]
    spent: BudgetState = field(default_factory=BudgetState)

    def remaining(self) -> float:
        return self.deadline - asyncio.get_running_loop().time()

    async def one(self, call: LiveCall, request: FetchRequest) -> tuple[Fetched, FlightRole]:
        spent = _failed(call, FailureReason.TIMEOUT, BUDGET_SPENT)
        remaining = self.remaining()
        if remaining <= 0:
            return spent, FlightRole.LEADER
        key = self.flights.key(call, request, asker=self.asker)
        try:
            return await self.flights.join(
                key, lambda: self.fetch(call, request), wait_seconds=remaining
            )
        except TimeoutError:
            return spent, FlightRole.FOLLOWER

    async def fetch(self, call: LiveCall, request: FetchRequest) -> Fetched:
        """One call made as the leader: credentials, admission, the call, and at most one retry."""
        source = self.sources.source_for(call.connector, mode=call.identity_mode, asker=self.asker)
        if source is None:
            return _failed(call, FailureReason.NOT_SERVING, f"no {call.identity_mode} credential")
        loop = asyncio.get_running_loop()
        timeout = call.timeout_ms / 1000
        attempts = 0
        while True:
            admission = self.throttle.admit(call.connector, now=self.clock())
            if admission.refused is not None:
                return _failed(call, admission.refused, admission.detail)
            if admission.wait_seconds > 0:
                if admission.wait_seconds + timeout > self.remaining():
                    return _failed(call, FailureReason.QUOTA, "this process's share of its minute")
                await self.sleep(admission.wait_seconds)
                continue
            try:
                self.spent = self.spent.spend(call.connector, budget=self.budget)
            except FederationError:
                return _failed(call, FailureReason.QUOTA, "the question's call budget")
            attempts += 1
            allowed = min(timeout, self.remaining())
            if allowed <= 0:
                return _failed(call, FailureReason.TIMEOUT, BUDGET_SPENT)
            started = loop.time()
            self.throttle.in_flight[call.connector] += 1
            try:
                reply = await asyncio.wait_for(source(request), allowed)
            except TimeoutError:
                self._record(call, CallOutcome.UNAVAILABLE, started)
                # See A_SOURCE_THAT_TIMED_OUT_IS_NOT_ASKED_AGAIN_IN_THE_SAME_QUESTION.
                return _failed(call, FailureReason.TIMEOUT)
            except Exception as exc:
                # The kind and never the message, which can quote a header or a row.
                self._record(call, CallOutcome.UNAVAILABLE, started)
                return _failed(call, FailureReason.TRANSPORT, type(exc).__name__)
            finally:
                self.throttle.in_flight[call.connector] -= 1
            self._record(call, reply.outcome, started)
            if reply.outcome in (CallOutcome.OK, CallOutcome.TRUNCATED):
                return Fetched(rows=reply.rows)
            if attempts < MAX_ATTEMPTS_PER_CALL and is_retryable(reply.outcome):
                wait = retry_delay(
                    retry_after_seconds=reply.retry_after_seconds,
                    consecutive_refusals=attempts,
                    jitter=self.jitter(),
                )
                if wait + timeout <= self.remaining():
                    await self.sleep(wait)
                    continue
            return _failed(call, _reason(reply.outcome), reply.outcome.value)

    def _record(self, call: LiveCall, outcome: CallOutcome, started: float) -> None:
        latency_ms = (asyncio.get_running_loop().time() - started) * 1000
        self.throttle.record(
            call.connector, outcome, latency_ms=latency_ms, now=self.clock(), jitter=self.jitter()
        )


def _reason(outcome: CallOutcome) -> FailureReason:
    """A refusal as the reason the trace records. Only a quota refusal is the source's volume."""
    return FailureReason.QUOTA if outcome is CallOutcome.QUOTA else FailureReason.TRANSPORT


def _failed(call: LiveCall, reason: FailureReason, detail: str = "") -> Fetched:
    return Fetched(failure=SourceFailure(connector=call.connector, reason=reason, detail=detail))


async def read_live(
    calls: Sequence[LiveCall],
    *,
    sources: LiveSources,
    asker: str,
    throttle: LiveThrottle,
    flights: LiveFlights,
    clock: Callable[[], datetime],
    budget: CallBudget | None = None,
    budget_ms: int = LIVE_READ_BUDGET_MS,
    jitter: Callable[[], float] = jitter,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    trace_id: str = "",
) -> LiveRead:
    """Read every call, in parallel where they are independent, and stop at the budget (M11.5.1).

    The plan is checked before the first call, against the wall clock (`FanOutPlan.assert_within`)
    and against the question's call budget (`CallBudget.assert_affordable`), and a plan either
    refuses raises `federation.FederationError`: a question assembled wrongly is a bug in whoever
    assembled it, and it fails where it was built rather than as a slow answer. See
    `federation.THE_BUDGET_IS_CHECKED_BEFORE_THE_FIRST_CALL`.

    Returns when every call has answered or failed, and never later than `budget_ms` from the
    start. A failure is carried in `LiveRead.partial`, and the full list is written to the
    operator's log under `trace_id` (M11.5.5).
    """
    allowance = CallBudget() if budget is None else budget
    plan = FanOutPlan(tuple(call.planned() for call in calls))
    plan.assert_within(budget_ms)
    allowance.assert_affordable(plan)

    loop = asyncio.get_running_loop()
    began = loop.time()
    question = _Question(
        calls=calls,
        sources=sources,
        asker=asker,
        throttle=throttle,
        flights=flights,
        clock=clock,
        budget=allowance,
        deadline=began + budget_ms / 1000,
        jitter=jitter,
        sleep=sleep,
    )
    by_id = {call.call_id: call for call in calls}
    answered: dict[str, TypedResult[SourceRecord]] = {}
    failures: dict[str, SourceFailure] = {}
    coalesced: list[str] = []

    for wave in plan.waves():
        ready: list[tuple[LiveCall, FetchRequest]] = []
        for call_id in wave:
            call = by_id[call_id]
            if any(parent not in answered for parent in call.depends_on):
                failures[call_id] = SourceFailure(
                    call.connector, FailureReason.NOT_SERVING, "a read it waits on did not answer"
                )
                continue
            try:
                request = (
                    call.request
                    if call.derive is None
                    else call.derive(MappingProxyType(dict(answered)))
                )
            except Exception as exc:
                failures[call_id] = SourceFailure(
                    call.connector, FailureReason.NOT_SERVING, type(exc).__name__
                )
                continue
            ready.append((call, request))
        results = await asyncio.gather(*(question.one(call, request) for call, request in ready))
        for (call, _), (fetched, role) in zip(ready, results, strict=True):
            if role is FlightRole.FOLLOWER and fetched.failure is None:
                coalesced.append(call.call_id)
            if fetched.failure is not None:
                failures[call.call_id] = fetched.failure
            elif fetched.rows is not None:
                answered[call.call_id] = fetched.rows
                if fetched.rows.truncated:
                    failures[call.call_id] = SourceFailure(
                        call.connector, FailureReason.TRUNCATED, "the source's own ceiling"
                    )
            else:
                answered[call.call_id] = TypedResult[SourceRecord](source=call.connector)

    partial = PartialAnswer(
        fetched=tuple(sorted({by_id[call_id].connector for call_id in answered})),
        failed=tuple(failures[call_id] for call_id in sorted(failures)),
    )
    elapsed_ms = (loop.time() - began) * 1000
    if not partial.is_complete:
        log.warning(
            "live_read.partial",
            trace_id=trace_id,
            unreached=list(partial.trace_lines()),
            elapsed_ms=round(elapsed_ms, 1),
        )
    return LiveRead(
        rows=MappingProxyType(answered),
        partial=partial,
        elapsed_ms=elapsed_ms,
        coalesced=tuple(sorted(coalesced)),
    )
