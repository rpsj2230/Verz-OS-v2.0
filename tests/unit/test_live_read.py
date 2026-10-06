"""Question-time live reads, held to the owner's budget: parallel, cut off, named, never waited on.

The owner's rule (needs-rupash 99) is that answers stay fast: a question's live reads run in
parallel under a time budget, a slow source is cut off and named rather than making the person wait,
and the budget is a named constant with a reason and a test. The first test below is that test, run
at the real figures rather than scaled down, because a budget that is only ever exercised at a
tenth of its size is a budget nobody has watched hold.

Everything else runs against stand-in sources that answer, hang, refuse or raise on command, and
against the real bucket, breaker, plan check and single-flight, so what is proved is the executor's
composition of them and not a copy of it.

Task ids: M11.5.1, M11.5.2, M11.5.3, M11.5.4, M11.5.5, M11.2.5, M11.3.1, M11.3.2, M11.3.3
Task ids: M11.3.4, M11.3.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime

import pytest
import structlog

from brain.connectors import live_read
from brain.connectors.contract import FetchRequest
from brain.connectors.federation import (
    FANOUT_BUDGET_MS,
    CallBudget,
    FailureReason,
    FederationError,
)
from brain.connectors.live_read import (
    LIVE_READ_BUDGET_MS,
    LIVE_READ_TIMEOUT_MS,
    LiveCall,
    LiveFlights,
    LiveRead,
    LiveReply,
    LiveSource,
    LiveThrottle,
    read_live,
)
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import SourceRecord
from brain.core.envelope import IdentityMode, TypedResult
from brain.core.errors import Degraded
from brain.ops.reliability import ANSWER_P95_MS, FAST_P95_MS

#: A clock nothing will cross. The bucket and the breaker are judged against it, and neither is
#: about the present, so it is pinned far outside any plausible wall clock.
FAR = datetime(2999, 1, 1, tzinfo=UTC)


def clock() -> datetime:
    return FAR


def rows(connector: str, *ids: str) -> TypedResult[SourceRecord]:
    return TypedResult[SourceRecord](
        records=tuple(
            SourceRecord.model_validate({"entity": "invoice", "id": one, "amount_due": "12.50"})
            for one in ids
        ),
        source=connector,
        fetched_at="2999-01-01T00:00:00+00:00",
    )


class Source:
    """A `LiveSource` that answers on command and counts every call it was asked to make."""

    def __init__(
        self,
        connector: str,
        *,
        replies: tuple[LiveReply, ...] = (),
        hang: bool = False,
        before: Callable[[], Awaitable[None]] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.connector = connector
        self.replies = list(replies) or [LiveReply(CallOutcome.OK, rows=rows(connector, "r1"))]
        self.hang = hang
        self.before = before
        self.raises = raises
        self.calls: list[FetchRequest] = []

    async def __call__(self, request: FetchRequest) -> LiveReply:
        self.calls.append(request)
        if self.before is not None:
            await self.before()
        if self.hang:
            await asyncio.sleep(3600)
        if self.raises is not None:
            raise self.raises
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


class Sources:
    """`LiveSources` holding service sources by connector and delegated ones by asker."""

    def __init__(
        self,
        service: Mapping[str, Source],
        delegated: Mapping[tuple[str, str], Source] | None = None,
    ) -> None:
        self.service = dict(service)
        self.delegated = dict(delegated or {})

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        del entity
        return IdentityMode.SERVICE if connector in self.service else None

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> LiveSource | None:
        if mode is IdentityMode.SERVICE:
            return self.service.get(connector)
        return self.delegated.get((connector, asker))


def call(
    connector: str,
    call_id: str | None = None,
    *,
    record: str = "r1",
    mode: IdentityMode = IdentityMode.SERVICE,
    timeout_ms: int = LIVE_READ_TIMEOUT_MS,
) -> LiveCall:
    return LiveCall(
        call_id=call_id or connector,
        connector=connector,
        request=FetchRequest(entity="invoice", filters=(("id", record),), limit=1),
        identity_mode=mode,
        timeout_ms=timeout_ms,
    )


def read(
    *calls: LiveCall,
    sources: Sources,
    asker: str = "p_priya",
    throttle: LiveThrottle | None = None,
    flights: LiveFlights | None = None,
    **options: object,
) -> LiveRead:
    return asyncio.run(
        read_live(
            calls,
            sources=sources,
            asker=asker,
            throttle=throttle or LiveThrottle(),
            flights=flights or LiveFlights(),
            clock=clock,
            jitter=lambda: 0.0,
            **options,  # type: ignore[arg-type]
        )
    )


@pytest.fixture(scope="module", autouse=True)
def _the_first_read_has_paid_for_its_imports_before_any_budget_starts() -> None:
    """One throwaway read before the first test, so no test's budget pays for a cold process.

    Measured on 2026-10-07: the first live read in a fresh interpreter took 653 ms against 0 ms for
    the second, because it imports the connector registry (and with it a few hundred modules) while
    its budget is running. The budget is 1600 ms and a timeout 800, so on a loaded CI machine that
    first read spent the whole budget before a source was called (`(0, 0)` calls in the delegated
    read test) or overran a timeout by more than the stopwatch test allows, and which test failed
    depended on which one the shard ran first.

    Delete this and those two tests fail one run in a few, on whichever of them goes first."""
    read(call("xero"), sources=Sources({"xero": Source("xero")}))


# ------------------------------------------------------------------ the owner's budget


def test_the_live_read_budget_is_the_plan_checks_and_leaves_the_answer_lane_most_of_its_time() -> (
    None
):
    """The budget against the figures outside it, never against itself. It is the fan-out plan's
    own budget, so a plan the check admits is a plan the executor runs to the end; it is at most a
    fifth of the answer lane's objective, so a model call after it keeps the rest; it is above the
    fast lane's whole objective, which is why a request that read live is recorded under the answer
    lane; and it holds at least one full timeout, so the first wave is never cut short.

    Delete this and the budget can be raised past what an answer can afford, or below one source's
    timeout, and every question reading two sources then names one of them as unreachable."""
    assert LIVE_READ_BUDGET_MS == FANOUT_BUDGET_MS
    assert LIVE_READ_BUDGET_MS * 5 <= ANSWER_P95_MS
    assert LIVE_READ_BUDGET_MS > FAST_P95_MS
    assert LIVE_READ_BUDGET_MS >= 2 * LIVE_READ_TIMEOUT_MS
    assert LIVE_READ_TIMEOUT_MS < LIVE_READ_BUDGET_MS
    assert "cut off" in live_read.A_PERSON_IS_NEVER_KEPT_WAITING_FOR_A_SLOW_SOURCE


def test_a_source_that_never_answers_is_cut_off_at_its_timeout_and_named_and_the_rest_answer() -> (
    None
):
    """The owner's rule at the real figures. One source answers at once and one never does: the
    question comes back after one timeout, well inside the budget, with the first source's rows, and
    the second is carried out as a timeout. The notice names it to an asker whose reach already
    discloses it and says only that part of the answer is unavailable to anybody else.

    Delete this and nothing proves a person is not kept waiting for the slowest source, which is
    the whole of needs-rupash 99's second sentence."""
    quick = Source("xero")
    stuck = Source("freshdesk", hang=True)

    outcome = read(
        call("xero"), call("freshdesk"), sources=Sources({"xero": quick, "freshdesk": stuck})
    )

    assert set(outcome.rows) == {"xero"}
    assert [(f.connector, f.reason) for f in outcome.partial.failed] == [
        ("freshdesk", FailureReason.TIMEOUT)
    ]
    assert LIVE_READ_TIMEOUT_MS * 0.9 <= outcome.elapsed_ms < LIVE_READ_TIMEOUT_MS * 1.5
    assert outcome.elapsed_ms < LIVE_READ_BUDGET_MS
    assert "freshdesk" in outcome.partial.notice(disclosable=frozenset({"freshdesk"}))
    assert outcome.partial.notice(disclosable=frozenset({"xero"})) == Degraded.public_message


def test_independent_sources_are_read_at_once_so_the_wait_is_the_slowest_and_not_the_sum() -> None:
    """Three sources that each answer only once all three are in flight together. Read in
    parallel, all three answer; read one after another, the first waits for company that never
    comes and times out. Deterministic, because it asserts on overlap rather than on a stopwatch.

    Delete this and the executor can await its calls in turn, with every question reading three
    sources taking three timeouts, and every other test here still green."""
    started = 0
    together = asyncio.Event()

    async def wait_for_the_others() -> None:
        nonlocal started
        started += 1
        if started == 3:
            together.set()
        await together.wait()

    names = ("xero", "freshdesk", "lark_base")
    sources = Sources({name: Source(name, before=wait_for_the_others) for name in names})

    outcome = read(*(call(name) for name in names), sources=sources)

    assert set(outcome.rows) == set(names)
    assert outcome.partial.is_complete


def test_a_read_that_waits_on_another_is_built_from_its_answer_and_is_not_made_when_it_failed() -> (
    None
):
    """One critical path: the dependent call starts after its parent, with its request derived
    from what the parent returned, and a parent that did not answer means the child is not made.

    Delete this and a dependent read can start before the id it needs exists, or be made with a
    request built from nothing after its parent failed."""
    parent = Source("xero", replies=(LiveReply(CallOutcome.OK, rows=rows("xero", "c-9")),))
    child = Source("freshdesk")

    def from_parent(answered: Mapping[str, TypedResult[SourceRecord]]) -> FetchRequest:
        found = answered["xero"].records[0].id
        return FetchRequest(entity="ticket", filters=(("company", found),), limit=1)

    dependent = LiveCall(
        call_id="tickets",
        connector="freshdesk",
        request=FetchRequest(entity="ticket"),
        identity_mode=IdentityMode.SERVICE,
        depends_on=("xero",),
        derive=from_parent,
    )
    outcome = read(call("xero"), dependent, sources=Sources({"xero": parent, "freshdesk": child}))

    assert set(outcome.rows) == {"xero", "tickets"}
    assert child.calls == [FetchRequest(entity="ticket", filters=(("company", "c-9"),), limit=1)]

    failing = Source("xero", replies=(LiveReply(CallOutcome.REJECTED),))
    unmade = Source("freshdesk")
    outcome = read(call("xero"), dependent, sources=Sources({"xero": failing, "freshdesk": unmade}))

    assert unmade.calls == []
    assert {f.connector: f.reason for f in outcome.partial.failed}["freshdesk"] is (
        FailureReason.NOT_SERVING
    )


def test_a_plan_the_budget_cannot_afford_is_refused_before_any_source_is_called() -> None:
    """Too deep for the wall clock, or too many calls to one source: both refused before the first
    call, because a budget enforced call by call has already spent what it refuses to spend.

    Delete this and a question assembled three calls deep runs its first two against the client's
    allowance before discovering it cannot finish."""
    source = Source("xero")
    chain = (
        call("xero", "a"),
        LiveCall("b", "xero", FetchRequest(entity="invoice"), depends_on=("a",)),
        LiveCall("c", "xero", FetchRequest(entity="invoice"), depends_on=("b",)),
    )
    with pytest.raises(FederationError, match="critical path"):
        read(*chain, sources=Sources({"xero": source}))

    many = tuple(call("xero", f"r{index}", record=f"r{index}") for index in range(3))
    with pytest.raises(FederationError, match="cannot be afforded"):
        read(*many, sources=Sources({"xero": source}), budget=CallBudget(default_per_source=2))
    assert source.calls == []


# ------------------------------------------------------------------ one fetch for many


def test_two_questions_asking_the_same_service_read_at_once_make_one_call() -> None:
    """Thundering-herd protection on a miss: two questions arriving together for the same record
    share one fetch, and the second says it followed.

    Delete this and twenty people asking one thing at nine in the morning make twenty calls against
    a shared daily allowance."""
    gate = asyncio.Event()

    async def held() -> None:
        await gate.wait()

    source = Source("xero", before=held)
    sources = Sources({"xero": source})
    throttle, flights = LiveThrottle(), LiveFlights()

    async def both() -> tuple[LiveRead, LiveRead]:
        first = asyncio.ensure_future(
            read_live(
                [call("xero")],
                sources=sources,
                asker="a",
                throttle=throttle,
                flights=flights,
                clock=clock,
            )
        )
        await asyncio.sleep(0)
        second = asyncio.ensure_future(
            read_live(
                [call("xero")],
                sources=sources,
                asker="b",
                throttle=throttle,
                flights=flights,
                clock=clock,
            )
        )
        await asyncio.sleep(0)
        gate.set()
        return await first, await second

    first, second = asyncio.run(both())

    assert len(source.calls) == 1
    assert set(first.rows) == set(second.rows) == {"xero"}
    assert (first.coalesced, second.coalesced) == ((), ("xero",))
    assert flights.held() == ()


def test_a_delegated_read_is_kept_to_its_asker_and_never_shared() -> None:
    """A read under the asker's own credentials was narrowed by the source to that person, so two
    askers asking the same thing at once make two reads.

    Delete this and one person's view of a source, narrowed by the source's own permissions, is
    handed to whoever asked the same question a moment later."""
    gate = asyncio.Event()

    async def held() -> None:
        await gate.wait()

    mine = Source("xero", before=held)
    theirs = Source("xero", before=held)
    sources = Sources({}, delegated={("xero", "a"): mine, ("xero", "b"): theirs})
    throttle, flights = LiveThrottle(), LiveFlights()
    delegated = call("xero", mode=IdentityMode.DELEGATED)

    async def both() -> tuple[LiveRead, LiveRead]:
        first = asyncio.ensure_future(
            read_live(
                [delegated],
                sources=sources,
                asker="a",
                throttle=throttle,
                flights=flights,
                clock=clock,
            )
        )
        await asyncio.sleep(0)
        second = asyncio.ensure_future(
            read_live(
                [delegated],
                sources=sources,
                asker="b",
                throttle=throttle,
                flights=flights,
                clock=clock,
            )
        )
        await asyncio.sleep(0)
        gate.set()
        return await first, await second

    first, second = asyncio.run(both())

    assert (len(mine.calls), len(theirs.calls)) == (1, 1)
    assert first.coalesced == second.coalesced == ()


def test_a_delegated_read_with_no_credential_of_its_own_is_not_made_with_the_service_key() -> None:
    """The requester's credentials are the default and a service read is declared (M11.2.5). A
    source holding only the service's key answers a delegated read with nothing, and nothing is
    read; the same read declared as the service's is made.

    Delete this and a read meant to be narrowed by the source to the asker is made with the
    connection's key, and the source's own check is dropped without anybody deciding to."""
    service = Source("xero")
    sources = Sources({"xero": service})

    refused = read(call("xero", mode=IdentityMode.DELEGATED), sources=sources)
    assert service.calls == []
    assert [(f.connector, f.reason) for f in refused.partial.failed] == [
        ("xero", FailureReason.NOT_SERVING)
    ]

    made = read(call("xero", mode=IdentityMode.SERVICE), sources=sources)
    assert len(service.calls) == 1
    assert made.partial.is_complete
    assert LiveCall("x", "xero", FetchRequest(entity="invoice")).identity_mode is (
        IdentityMode.DELEGATED
    )


# ------------------------------------------------------------------ in front of a source


def test_an_open_breaker_refuses_at_once_and_a_closed_one_lets_the_call_through() -> None:
    """Three failed reads open the connector's breaker, and the next question is refused without
    waiting on the source at all; a healthy connector's breaker admits.

    Delete this and a source that has been down all morning costs every question a full timeout."""
    throttle = LiveThrottle()
    for _ in range(3):
        throttle.record("xero", CallOutcome.UNAVAILABLE, latency_ms=800.0, now=FAR)
    source = Source("xero")

    refused = read(call("xero"), sources=Sources({"xero": source}), throttle=throttle)
    assert source.calls == []
    assert refused.partial.failed[0].reason is FailureReason.CIRCUIT_OPEN

    healthy = read(call("xero"), sources=Sources({"xero": source}), throttle=LiveThrottle())
    assert healthy.partial.is_complete


def test_a_source_with_no_verified_ceiling_is_not_read_live_and_a_measured_one_is() -> None:
    """The bucket is derived from the verified ceiling and refuses to invent one, so a connector
    nobody has measured is not read at question time.

    Delete this and a source with no ceiling is driven at whatever rate questions arrive."""
    unmeasured = Source("nobody_measured")
    refused = read(call("nobody_measured"), sources=Sources({"nobody_measured": unmeasured}))
    assert unmeasured.calls == []
    assert refused.partial.failed[0].reason is FailureReason.NOT_SERVING

    measured = Source("lark_base")
    assert read(call("lark_base"), sources=Sources({"lark_base": measured})).partial.is_complete


def test_a_spent_bucket_is_a_quota_failure_at_once_rather_than_a_wait_past_the_budget() -> None:
    """A bucket asks for a wait; a wait that does not fit inside the budget is not waited.

    Delete this and a question arriving after a burst sleeps for the bucket's refill while the
    person watches, which is the wait the budget exists to forbid."""
    throttle = LiveThrottle()
    while throttle.admit("xero", now=FAR).refused is None and (
        throttle.buckets.tokens_in("xero") >= 1
    ):
        pass
    source = Source("xero")

    outcome = read(call("xero"), sources=Sources({"xero": source}), throttle=throttle)

    assert source.calls == []
    assert outcome.partial.failed[0].reason is FailureReason.QUOTA
    assert outcome.elapsed_ms < LIVE_READ_TIMEOUT_MS


def test_a_refusal_with_a_short_stated_wait_is_retried_once_inside_the_budget() -> None:
    """The retry policy's positive case: the source said wait a moment, the moment fits, and the
    second call answers.

    Delete this and the retry branch can be removed with every refusal test still green."""
    source = Source(
        "xero",
        replies=(
            LiveReply(CallOutcome.QUOTA, retry_after_seconds=0.01),
            LiveReply(CallOutcome.OK, rows=rows("xero", "r1")),
        ),
    )
    outcome = read(call("xero"), sources=Sources({"xero": source}))

    assert len(source.calls) == 2
    assert outcome.partial.is_complete


def test_a_refusal_that_states_no_wait_and_a_timeout_are_each_asked_once() -> None:
    """A refusal naming no wait is treated as the longest wait, which never fits; a source that
    used its whole timeout is slow now. Neither is asked again in the same question.

    Delete this and a question spends a second timeout on a source already known to be slow, or a
    hot retry against a source that said stop."""
    quota = Source("xero", replies=(LiveReply(CallOutcome.QUOTA),))
    outcome = read(call("xero"), sources=Sources({"xero": quota}))
    assert len(quota.calls) == 1
    assert outcome.partial.failed[0].reason is FailureReason.QUOTA

    slow = Source("xero", hang=True)
    outcome = read(call("xero", timeout_ms=50), sources=Sources({"xero": slow}), budget_ms=1600)
    assert len(slow.calls) == 1
    assert outcome.partial.failed[0].reason is FailureReason.TIMEOUT


def test_a_source_that_raises_is_a_transport_failure_named_by_kind_and_never_by_message() -> None:
    """A message can quote a header or a row, so only the exception's kind reaches the trace.

    Delete this and a source's error text, key and all, can land in the operator's log."""
    source = Source("xero", raises=RuntimeError("Bearer sk-live-SECRET for SNM Construction"))
    outcome = read(call("xero"), sources=Sources({"xero": source}))

    failure = outcome.partial.failed[0]
    assert (failure.reason, failure.detail) == (FailureReason.TRANSPORT, "RuntimeError")
    assert "SECRET" not in " ".join(outcome.partial.trace_lines())


def test_every_call_is_measured_for_its_connector_with_nothing_left_in_flight() -> None:
    """Requests, the error rate and the calls in flight, per connector, from the calls made.

    Delete this and the numbers a console reads about a connector's health are never written."""
    throttle = LiveThrottle()
    good = Source("xero")
    bad = Source("freshdesk", replies=(LiveReply(CallOutcome.UNAVAILABLE),))
    read(
        call("xero"),
        call("freshdesk"),
        sources=Sources({"xero": good, "freshdesk": bad}),
        throttle=throttle,
    )

    xero = throttle.metrics("xero", now=FAR)
    freshdesk = throttle.metrics("freshdesk", now=FAR)
    assert (xero.requests, xero.error_ratio, xero.concurrency) == (1, 0.0, 0)
    assert (freshdesk.requests, freshdesk.error_ratio) == (1, 1.0)


def test_what_could_not_be_read_goes_to_the_operators_log_in_full() -> None:
    """The asker is told as much as their reach discloses; the operator's log gets every source and
    reason under the request's trace.

    Delete this and a partial answer leaves no record of which source failed, so the person who
    was told to ask somebody has nobody who can find out."""
    stuck = Source("freshdesk", replies=(LiveReply(CallOutcome.REJECTED),))
    with structlog.testing.capture_logs() as logged:
        read(call("freshdesk"), sources=Sources({"freshdesk": stuck}), trace_id="t-live")

    partial = [one for one in logged if one["event"] == "live_read.partial"]
    assert len(partial) == 1
    assert partial[0]["trace_id"] == "t-live"
    assert partial[0]["unreached"] == ["freshdesk: transport (rejected)"]
