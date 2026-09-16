"""The executor: the chain walked, every try recorded, every call metered, and nothing else.

Driven with a ladder, an attempt log and drivers held in memory, so the walk is inspected as the
policy layer describes it and nothing opens a socket or a connection.

Task ids: M27.7.14, M27.8.8, M5.3.4
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.lane import Lane
from brain.models.adapter import (
    Completion,
    ContextWindowExceededError,
    SdkDriver,
    TransportConnectionError,
    TransportStatusError,
)
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, LadderRung
from brain.models.calls import (
    A_MODEL_CALL_WITHOUT_A_METER_HAS_NO_DOOR,
    LadderState,
    ModelCalls,
)
from brain.models.driver import (
    DriverMessage,
    DriverRequest,
    DriverResponse,
    ModelDriver,
    ProviderUnavailable,
    Role,
)
from brain.models.evidence import Attempt
from brain.models.metering import Meter
from brain.models.routing import (
    BREAKER_CONSECUTIVE_FAILURES,
    FallbackTrigger,
    NoCompliantRoute,
    Tier,
)

#: Far outside any plausible wall clock, because nothing here is about the present.
T0 = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)
TRACE = "b" * 32
ASK = (DriverMessage(role=Role.USER, content="how many hours are left"),)

Answer = Completion | BaseException


class Scripted:
    """A transport answering each call with the next item of a script, and keeping the requests."""

    def __init__(self, *script: Answer) -> None:
        self.script = list(script)
        self.sent: list[DriverRequest] = []

    def __call__(self, request: DriverRequest) -> Completion:
        self.sent.append(request)
        answer = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


def ok(tokens_in: int = 10, tokens_out: int = 2) -> Completion:
    return Completion(
        text="ready", finish_reason="stop", input_tokens=tokens_in, output_tokens=tokens_out
    )


@dataclass
class Ladder:
    rungs: tuple[LadderRung, ...]
    switched_off: frozenset[str] = frozenset()
    attempts: tuple[Attempt, ...] = ()

    async def current(self, now: datetime) -> LadderState:
        return LadderState(rungs=self.rungs, switched_off=self.switched_off, attempts=self.attempts)


@dataclass
class Log:
    """Every attempt row as the store would hold it: started, then finished by its token."""

    rows: dict[str, dict[str, object]] = field(default_factory=dict)

    async def started(self, *, trace_id: str, rung_id: str, sequence: int, at: datetime) -> str:
        token = f"t{len(self.rows)}"
        self.rows[token] = {"trace_id": trace_id, "rung_id": rung_id, "sequence": sequence}
        return token

    async def finished(self, token: str, *, at: datetime, outcome: str, status: int | None) -> None:
        self.rows[token].update(outcome=outcome, status=status)

    def outcomes(self) -> list[tuple[str, object, object]]:
        return [(str(r["rung_id"]), r["sequence"], r.get("outcome")) for r in self.rows.values()]


def rung(
    provider: str,
    *,
    tier: Tier = Tier.MAIN,
    position: int = 0,
    attempts: int = 1,
    model: str | None = None,
) -> LadderRung:
    return LadderRung(
        rung_id=f"{tier.value}-{position}",
        tier=tier,
        position=position,
        deployment_id=f"{provider}-{tier.value}-{position}",
        provider=provider,
        model=model or f"{provider}-model",
        attempts=attempts,
        timeout_seconds=12.0,
        max_concurrency=2,
        enabled=True,
    )


def executor(
    ladder: Ladder,
    transports: dict[str, Scripted],
    *,
    profile: str = HOSTED_PROFILE,
    held: frozenset[str] | None = None,
    log: Log | None = None,
    clock: Callable[[], datetime] = lambda: T0,
) -> tuple[ModelCalls, Log]:
    kept = log or Log()
    drivers: dict[str, ModelDriver] = {
        name: SdkDriver(provider=name, transport=one) for name, one in transports.items()
    }
    return (
        ModelCalls(
            ladder=ladder,
            attempts=kept,
            drivers=drivers,
            profile=lambda: profile,
            held=lambda: frozenset(transports) if held is None else held,
            clock=clock,
        ),
        kept,
    )


def complete(calls: ModelCalls, meter: Meter, **overrides: object) -> DriverResponse:
    arguments: dict[str, object] = {
        "tier": Tier.MAIN,
        "lane": Lane.ANSWER,
        "meter": meter,
        "trace_id": TRACE,
    }
    arguments.update(overrides)
    return asyncio.run(calls.complete(ASK, **arguments))  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- answers


def test_a_call_is_answered_by_the_primary_recorded_as_one_attempt_and_metered() -> None:
    """The positive case the rest of this file refuses around.

    Delete this and an executor that raises on every call passes every refusal below."""
    primary = Scripted(ok(40, 5))
    second = Scripted(ok())
    calls, log = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": primary, "moonshot": second},
    )
    meter = Meter()

    answered = complete(calls, meter, agent_version="finance-bot")

    assert answered.deployment_id == "anthropic-main-0"
    assert second.sent == []
    assert log.outcomes() == [("main-0", 0, "ok")]
    usage = meter.usage()
    assert usage is not None
    assert (usage.calls, usage.tokens_in, usage.tokens_out) == (1, 40, 5)
    assert (usage.model, usage.provider, usage.agent_version) == (
        "anthropic-model",
        "anthropic",
        "finance-bot",
    )
    assert (usage.fallback_count, usage.retry_count) == (0, 0)


def test_a_provider_error_moves_to_the_next_rung_and_counts_one_fallback() -> None:
    """Delete this and a chain that stops at its primary, or falls back without saying so on the
    ledger, passes the test above."""
    calls, log = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": Scripted(TransportStatusError(503)), "moonshot": Scripted(ok())},
    )
    meter = Meter()

    answered = complete(calls, meter)

    assert answered.deployment_id == "moonshot-main-1"
    assert log.outcomes() == [
        ("main-0", 0, FallbackTrigger.PROVIDER_ERROR.value),
        ("main-1", 1, "ok"),
    ]
    usage = meter.usage()
    assert usage is not None
    assert (usage.calls, usage.fallback_count, usage.retry_count) == (2, 1, 0)


def test_a_rung_with_two_attempts_is_tried_again_and_the_second_try_is_a_retry() -> None:
    """Delete this and `attempts` becomes a column nothing reads."""
    primary = Scripted(TransportConnectionError(), ok())
    calls, _ = executor(Ladder((rung("anthropic", attempts=2),)), {"anthropic": primary})
    meter = Meter()

    complete(calls, meter)

    assert len(primary.sent) == 2
    usage = meter.usage()
    assert usage is not None
    assert (usage.calls, usage.fallback_count, usage.retry_count) == (2, 0, 1)


def test_a_failure_with_no_trigger_stops_the_chain_and_never_reaches_the_next_rung() -> None:
    """A 400 is our request being wrong, and the next rung receives the same request.

    Delete this and every bad request costs the whole chain."""
    second = Scripted(ok())
    calls, log = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": Scripted(TransportStatusError(400)), "moonshot": second},
    )

    with pytest.raises(ProviderUnavailable) as raised:
        complete(calls, Meter())

    assert raised.value.failure.trigger is None
    assert second.sent == []
    assert log.outcomes() == [("main-0", 0, "stopped")]


def test_every_rung_failing_raises_the_last_failure() -> None:
    """Delete this and an exhausted chain can return nothing, or the first failure rather than the
    one an operator has to act on now."""
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {
            "anthropic": Scripted(TransportStatusError(503)),
            "moonshot": Scripted(TransportStatusError(429)),
        },
    )

    with pytest.raises(ProviderUnavailable) as raised:
        complete(calls, Meter())

    assert raised.value.failure.trigger is FallbackTrigger.RATE_LIMITED
    assert raised.value.failure.deployment_id == "moonshot-main-1"


def test_an_overflow_leaves_the_tier_for_the_next_one_up_and_never_down() -> None:
    """The one trigger permitted to change tier, and only upward.

    Delete this and an overflow on main either stops a request heavy would have answered, or is
    retried on a smaller model."""
    small = Scripted(ok())
    heavy = Scripted(ok(900, 9))
    calls, log = executor(
        Ladder(
            (
                rung("openai", tier=Tier.SMALL),
                rung("anthropic", tier=Tier.MAIN),
                rung("moonshot", tier=Tier.HEAVY),
            )
        ),
        {
            "openai": small,
            "anthropic": Scripted(ContextWindowExceededError()),
            "moonshot": heavy,
        },
    )
    meter = Meter()

    answered = complete(calls, meter)

    assert answered.deployment_id == "moonshot-heavy-0"
    assert small.sent == []
    assert [one[2] for one in log.outcomes()] == [FallbackTrigger.CONTEXT_EXCEEDED.value, "ok"]


def test_an_overflow_on_the_top_tier_raises_it_rather_than_answering_from_anywhere() -> None:
    """Delete this and the escalation loop can wrap round to the cheapest tier."""
    calls, _ = executor(
        Ladder((rung("anthropic", tier=Tier.HEAVY), rung("openai", tier=Tier.SMALL))),
        {"anthropic": Scripted(ContextWindowExceededError()), "openai": Scripted(ok())},
    )

    with pytest.raises(ProviderUnavailable) as raised:
        complete(calls, Meter(), tier=Tier.HEAVY)

    assert raised.value.failure.trigger is FallbackTrigger.CONTEXT_EXCEEDED


def test_an_overflow_into_a_tier_with_nothing_configured_raises_the_overflow() -> None:
    """Delete this and the request is refused as though nothing were configured at all, which sends
    an operator to configure a ladder that is there."""
    calls, _ = executor(
        Ladder((rung("anthropic", tier=Tier.MAIN),)),
        {"anthropic": Scripted(ContextWindowExceededError())},
    )

    with pytest.raises(ProviderUnavailable) as raised:
        complete(calls, Meter())

    assert raised.value.failure.trigger is FallbackTrigger.CONTEXT_EXCEEDED


# ---------------------------------------------------------------------------- refusals


def test_a_switched_off_provider_is_never_called_and_its_rung_is_passed_over() -> None:
    """Delete this and the switch on the Models screen reaches a row the executor does not read."""
    off = Scripted(ok())
    calls, _ = executor(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)), switched_off=frozenset({"anthropic"})
        ),
        {"anthropic": off, "moonshot": Scripted(ok())},
    )

    assert complete(calls, Meter()).deployment_id == "moonshot-main-1"
    assert off.sent == []


def test_a_local_profile_never_calls_a_hosted_provider() -> None:
    """Delete this and a local install sends its text off its own hardware to the first rung."""
    hosted = Scripted(ok())
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": hosted}, profile=LOCAL_PROFILE)
    meter = Meter()

    with pytest.raises(NoCompliantRoute):
        complete(calls, meter)

    assert hosted.sent == []
    assert meter.usage() is None


def test_a_ladder_with_nothing_on_it_is_refused_as_no_model_configured() -> None:
    """Delete this and an install with an empty ladder answers with a fault, not a sentence."""
    calls, _ = executor(Ladder(()), {})

    with pytest.raises(NoCompliantRoute) as raised:
        complete(calls, Meter())

    assert raised.value.public_message == "No model is configured to handle that."


def test_the_fast_lane_takes_no_model_call_at_all() -> None:
    """Delete this and a fast-lane request, whose every guarantee rests on no model seeing it, can
    be sent to one."""
    called = Scripted(ok())
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": called})

    with pytest.raises(ValueError, match="fast lane"):
        complete(calls, Meter(), lane=Lane.FAST)

    assert called.sent == []


def test_a_call_cannot_be_made_without_a_meter() -> None:
    """Read off the signature: the meter is keyword-only with no default.

    Delete this and a default `Meter()` can be added, after which a caller that forgot to hand
    one in makes calls whose tokens reach no ledger row."""
    parameter = inspect.signature(ModelCalls.complete).parameters["meter"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert "meter" in A_MODEL_CALL_WITHOUT_A_METER_HAS_NO_DOOR


def test_a_provider_narrowed_call_tries_only_that_providers_rungs() -> None:
    """Delete this and a check an administrator pressed for one provider is answered by another,
    and the screen says the first one works."""
    first = Scripted(ok())
    chosen = Scripted(ok())
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": first, "moonshot": chosen},
    )

    assert complete(calls, Meter(), provider="moonshot").deployment_id == "moonshot-main-1"
    assert first.sent == []


# ----------------------------------------------------------------------------- health


def test_a_rung_whose_attempts_opened_its_breaker_is_passed_over_without_a_call() -> None:
    """The breaker is replayed from the attempts every process wrote.

    Delete this and a provider three processes have watched fail keeps receiving questions from a
    fourth that did not."""
    dead = Scripted(ok())
    recent = tuple(
        Attempt(
            deployment_id="anthropic-main-0",
            finished_at=T0 - timedelta(seconds=5 - i),
            outcome=FallbackTrigger.TIMEOUT.value,
        )
        for i in range(BREAKER_CONSECUTIVE_FAILURES)
    )
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1)), attempts=recent),
        {"anthropic": dead, "moonshot": Scripted(ok())},
    )

    assert complete(calls, Meter()).deployment_id == "moonshot-main-1"
    assert dead.sent == []


def test_a_rung_that_opens_during_a_walk_is_not_tried_again_in_the_same_request() -> None:
    """Five attempts on a rung that fails every time stop at the breaker's own threshold.

    Delete this and one request spends every configured attempt on a provider it has just
    watched fail, which is the retry storm the breaker exists to stop."""
    failing = Scripted(TransportConnectionError())
    calls, _ = executor(
        Ladder((rung("anthropic", attempts=5), rung("moonshot", position=1))),
        {"anthropic": failing, "moonshot": Scripted(ok())},
    )
    meter = Meter()

    assert complete(calls, meter).deployment_id == "moonshot-main-1"
    assert len(failing.sent) == BREAKER_CONSECUTIVE_FAILURES
    usage = meter.usage()
    assert usage is not None
    assert (usage.retry_count, usage.fallback_count) == (BREAKER_CONSECUTIVE_FAILURES - 1, 1)


def test_a_rate_limited_rung_is_tried_again_because_a_rate_limit_is_not_ill_health() -> None:
    """Delete this and a burst of 429s opens a breaker on a working provider."""
    limited = Scripted(TransportStatusError(429))
    calls, _ = executor(
        Ladder((rung("anthropic", attempts=5), rung("moonshot", position=1))),
        {"anthropic": limited, "moonshot": Scripted(ok())},
    )

    complete(calls, Meter())

    assert len(limited.sent) == 5


def test_the_plan_is_the_one_a_call_walks_with_health_and_the_keys_it_read() -> None:
    """Delete this and the screen's view can come from a different assembly than the executor's."""
    calls, _ = executor(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)),
            attempts=(Attempt(deployment_id="anthropic-main-0", finished_at=T0, outcome="ok"),),
        ),
        {"anthropic": Scripted(ok()), "moonshot": Scripted(ok())},
        held=frozenset({"anthropic"}),
    )

    plan = asyncio.run(calls.planned())

    assert [one.provider for one in plan.assembly.answering] == ["anthropic"]
    assert [one.rung.provider for one in plan.assembly.skipped] == ["moonshot"]
    assert set(plan.health) == {"anthropic-main-0"}
    assert plan.held == frozenset({"anthropic"})
    assert plan.profile == HOSTED_PROFILE


def test_concurrent_calls_on_one_rung_never_exceed_its_ceiling() -> None:
    """`max_concurrency` is a semaphore per deployment in this process.

    Delete this and a slow provider becomes unbounded threads rather than queueing."""
    in_flight = 0
    most = 0
    lock = threading.Lock()

    def slow(request: DriverRequest) -> Completion:
        nonlocal in_flight, most
        with lock:
            in_flight += 1
            most = max(most, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return ok()

    calls = ModelCalls(
        ladder=Ladder((rung("anthropic"),)),
        attempts=Log(),
        drivers={"anthropic": SdkDriver(provider="anthropic", transport=slow)},
        profile=lambda: HOSTED_PROFILE,
        held=lambda: frozenset({"anthropic"}),
        clock=lambda: T0,
    )

    async def many() -> Sequence[DriverResponse]:
        return await asyncio.gather(
            *(
                calls.complete(ASK, tier=Tier.MAIN, lane=Lane.ANSWER, meter=Meter(), trace_id=TRACE)
                for _ in range(6)
            )
        )

    assert len(asyncio.run(many())) == 6
    assert most == 2
