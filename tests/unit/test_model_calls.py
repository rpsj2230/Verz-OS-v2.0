"""The executor: the chain walked, every try recorded, every call metered, and nothing else.

Driven with a ladder, an attempt log and drivers held in memory, so the walk is inspected as the
policy layer describes it and nothing opens a socket or a connection.

Task ids: M27.7.14, M27.8.8, M5.3.4, M5.4.6, M5.5.4, M5.5.2, M5.1.3, M5.7.3, M5.6.4, M5.4.1,
M5.7.2, M5.2.2, M5.4.3, M5.4.7, M5.4.8, M5.5.1
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
from brain.core.scope import Scope
from brain.models.adapter import (
    Completion,
    ContentPolicyRefusedError,
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
from brain.models.disclosure import DataCategory
from brain.models.driver import (
    DriverMessage,
    DriverRequest,
    DriverResponse,
    LaneOverride,
    ModelDriver,
    ProviderUnavailable,
    Role,
)
from brain.models.evidence import Attempt, RingEntry, StoredRings
from brain.models.health import AlertLevel, DepthAlert
from brain.models.metering import Meter
from brain.models.registry import ModelPin, ProviderKind, ProviderRecord
from brain.models.residency import ScopedResidency
from brain.models.routing import (
    BREAKER_BASE_COOLDOWN_SECONDS,
    BREAKER_CONSECUTIVE_FAILURES,
    FallbackTrigger,
    NoCompliantRoute,
    ResidencyClass,
    ResidencyRequirement,
    RoutingRequest,
    Tier,
)
from brain.models.tier_rules import TierRule

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
    providers: tuple[ProviderRecord, ...] = ()
    tiers: tuple[TierRule, ...] = ()
    residency: tuple[ScopedResidency, ...] = ()
    rings: tuple[StoredRings, ...] = ()

    async def current(self, now: datetime) -> LadderState:
        return LadderState(
            rungs=self.rungs,
            switched_off=self.switched_off,
            attempts=self.attempts,
            providers=self.providers,
            tiers=self.tiers,
            residency=self.residency,
            rings=self.rings,
        )


@dataclass
class Rings:
    """Every live outcome the executor appended, as `(deployment, provider, ok)`."""

    seen: list[tuple[str, str, bool]] = field(default_factory=list)

    async def observed(self, *, deployment_id: str, provider: str, ok: bool, at: datetime) -> None:
        self.seen.append((deployment_id, provider, ok))


@dataclass
class Alerts:
    """Every depth alert the executor raised, with its trace."""

    raised: list[tuple[DepthAlert, str]] = field(default_factory=list)

    async def raised_(self, alert: DepthAlert, *, trace_id: str, at: datetime) -> None:
        self.raised.append((alert, trace_id))


class AlertSink:
    """`DepthAlerts` over an `Alerts` list."""

    def __init__(self, into: Alerts) -> None:
        self.into = into

    async def raised(self, alert: DepthAlert, *, trace_id: str, at: datetime) -> None:
        await self.into.raised_(alert, trace_id=trace_id, at=at)


@dataclass
class Log:
    """Every attempt row as the store would hold it: started, then finished by its token."""

    rows: dict[str, dict[str, object]] = field(default_factory=dict)

    async def started(
        self,
        *,
        trace_id: str,
        rung_id: str,
        sequence: int,
        at: datetime,
        categories: tuple[str, ...] = (),
    ) -> str:
        token = f"t{len(self.rows)}"
        self.rows[token] = {
            "trace_id": trace_id,
            "rung_id": rung_id,
            "sequence": sequence,
            "categories": categories,
        }
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
    rings: Rings | None = None,
    alerts: Alerts | None = None,
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
            health=rings,
            alerts=None if alerts is None else AlertSink(alerts),
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


def test_a_half_open_deployment_is_sent_one_request_at_a_time_by_claim_and_return() -> None:
    """M5.4.6. Replayed from the attempts, the breaker is half open for every walk at once.

    Delete this and every request arriving after a cooldown is sent to the provider that has
    just failed, which is the storm the single half-open admission exists to prevent."""
    opened = T0 - timedelta(seconds=BREAKER_BASE_COOLDOWN_SECONDS + 5)
    failures = tuple(
        Attempt(
            deployment_id="anthropic-main-0",
            finished_at=opened - timedelta(seconds=BREAKER_CONSECUTIVE_FAILURES - 1 - i),
            outcome=FallbackTrigger.TIMEOUT.value,
        )
        for i in range(BREAKER_CONSECUTIVE_FAILURES)
    )
    release = threading.Event()
    recovering: list[DriverRequest] = []

    def slow(request: DriverRequest) -> Completion:
        recovering.append(request)
        release.wait(timeout=5)
        return ok()

    backup = Scripted(ok())
    calls = ModelCalls(
        ladder=Ladder((rung("anthropic"), rung("moonshot", position=1)), attempts=failures),
        attempts=Log(),
        drivers={
            "anthropic": SdkDriver(provider="anthropic", transport=slow),
            "moonshot": SdkDriver(provider="moonshot", transport=backup),
        },
        profile=lambda: HOSTED_PROFILE,
        held=lambda: frozenset({"anthropic", "moonshot"}),
        clock=lambda: T0,
    )

    async def two() -> Sequence[DriverResponse]:
        first = asyncio.ensure_future(
            calls.complete(ASK, tier=Tier.MAIN, lane=Lane.ANSWER, meter=Meter(), trace_id=TRACE)
        )
        while not recovering:
            await asyncio.sleep(0.01)
        second = await calls.complete(
            ASK, tier=Tier.MAIN, lane=Lane.ANSWER, meter=Meter(), trace_id="c" * 32
        )
        release.set()
        return (await first, second)

    first, second = asyncio.run(two())

    assert first.deployment_id == "anthropic-main-0"
    assert second.deployment_id == "moonshot-main-1"
    assert len(recovering) == 1
    assert len(backup.sent) == 1


def test_a_returned_claim_lets_the_next_request_through_the_recovered_deployment() -> None:
    """The positive half of claim and return: once the probe comes back, the claim is released.

    Delete this and a claim that is never returned keeps a recovered provider out of rotation
    for this process until the claim lifetime runs out."""
    opened = T0 - timedelta(seconds=BREAKER_BASE_COOLDOWN_SECONDS + 5)
    failures = tuple(
        Attempt(
            deployment_id="anthropic-main-0",
            finished_at=opened - timedelta(seconds=BREAKER_CONSECUTIVE_FAILURES - 1 - i),
            outcome=FallbackTrigger.TIMEOUT.value,
        )
        for i in range(BREAKER_CONSECUTIVE_FAILURES)
    )
    recovered = Scripted(ok())
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1)), attempts=failures),
        {"anthropic": recovered, "moonshot": Scripted(ok())},
    )

    assert complete(calls, Meter()).deployment_id == "anthropic-main-0"
    assert complete(calls, Meter()).deployment_id == "anthropic-main-0"
    assert len(recovered.sent) == 2


def test_a_residency_constrained_call_with_no_compliant_rung_is_refused_and_calls_nothing() -> None:
    """M5.5.4 at the executor. Every rung assembled from a row promises no region, so a request
    pinned to one finds no compliant rung, and the refusal comes before any provider is called.

    Delete this and a regulated question can be sent to a provider in an undocumented location
    the moment the executor stops passing its residency through to the chain."""
    anywhere = Scripted(ok())
    calls, log = executor(Ladder((rung("anthropic"),)), {"anthropic": anywhere})

    with pytest.raises(NoCompliantRoute):
        complete(
            calls,
            Meter(),
            residency=ResidencyRequirement(allowed_regions=frozenset({"eu-west-1"})),
        )

    assert anywhere.sent == []
    assert log.rows == {}


# ------------------------------------------------------------------ the pin (M5.7.3)
def test_a_pinned_model_is_tried_first_even_from_another_tier() -> None:
    """M5.7.3: the pin is tried first, whichever tier holds its rung.

    Delete this and a pin is stored, shown on the Settings tab, and never used."""
    primary = Scripted(ok())
    pinned = Scripted(ok())
    calls, log = executor(
        Ladder((rung("anthropic"), rung("moonshot", tier=Tier.HEAVY, model="kimi-k2"))),
        {"anthropic": primary, "moonshot": pinned},
    )

    answered = complete(calls, Meter(), pin=ModelPin(provider="moonshot", model="kimi-k2"))

    assert answered.deployment_id == "moonshot-heavy-0"
    assert primary.sent == []
    assert [row["rung_id"] for row in log.rows.values()] == ["heavy-0"]


def test_a_pinned_model_that_fails_falls_back_to_the_agents_tier_and_is_not_tried_twice() -> None:
    """The tier stands behind the pin: a pin that fails on the closed set moves to the tier's
    chain, which leaves the pinned rung out.

    Delete this and a pinned provider's outage is an agent that answers nothing, or a pinned rung
    that sits in the tier too and is asked twice in one request."""
    pinned = Scripted(TransportConnectionError())
    backup = Scripted(ok())
    calls, log = executor(
        Ladder((rung("moonshot", model="kimi-k2"), rung("anthropic", position=1))),
        {"moonshot": pinned, "anthropic": backup},
    )

    answered = complete(calls, Meter(), pin=ModelPin(provider="moonshot", model="kimi-k2"))

    assert answered.deployment_id == "anthropic-main-1"
    assert len(pinned.sent) == 1
    assert [row["rung_id"] for row in log.rows.values()] == ["main-0", "main-1"]


def test_a_pin_naming_no_answering_rung_is_passed_over_for_the_tier() -> None:
    """A pin is a choice among the ladder's models, not a way round it.

    Delete this and a pin naming a switched-off or unkeyed provider stops the agent answering."""
    tier = Scripted(ok())
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": tier})

    answered = complete(calls, Meter(), pin=ModelPin(provider="moonshot", model="kimi-k2"))

    assert answered.deployment_id == "anthropic-main-0"


def test_a_refusal_from_the_pinned_model_is_not_tried_on_the_tier() -> None:
    """M5.4.1 holds through a pin: a content refusal stops the chain, pinned or not.

    Delete this and a pin becomes the way a declined question is shopped to a second model."""
    pinned = Scripted(ContentPolicyRefusedError(status=400))
    backup = Scripted(ok())
    calls, log = executor(
        Ladder((rung("moonshot", model="kimi-k2"), rung("anthropic", position=1))),
        {"moonshot": pinned, "anthropic": backup},
    )

    with pytest.raises(ProviderUnavailable) as refused:
        complete(calls, Meter(), pin=ModelPin(provider="moonshot", model="kimi-k2"))

    assert refused.value.failure.refused is True
    assert backup.sent == []
    assert log.outcomes() == [("main-0", 0, "refused")]


def test_a_content_refusal_is_recorded_as_refused_and_never_reaches_the_next_rung() -> None:
    """M5.4.1 at the executor: one attempt, recorded `refused`, and the second rung never called.

    Delete this and a declined question is tried on every model in the chain."""
    first = Scripted(ContentPolicyRefusedError(status=503))
    second = Scripted(ok())
    calls, log = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": first, "moonshot": second},
    )

    with pytest.raises(ProviderUnavailable):
        complete(calls, Meter())

    assert second.sent == []
    assert log.outcomes() == [("main-0", 0, "refused")]


# ------------------------------------------------------------- lane overrides (M5.1.3)
def record(
    slug: str,
    *,
    lanes: dict[Lane, LaneOverride] | None = None,
    region: str = "global",
    residency: ResidencyClass = ResidencyClass.GLOBAL,
) -> ProviderRecord:
    return ProviderRecord(
        slug=slug,
        kind=ProviderKind.BUILTIN,
        label=slug,
        processing_region=region,
        residency_class=residency,
        lane_overrides=lanes or {},
    )


def test_a_providers_lane_override_sets_the_timeout_and_attempts_each_try_runs_at() -> None:
    """M5.1.3: the answer lane's override for a provider is what the request is sent with.

    Delete this and the overrides edited on the Models screen are stored and never applied."""
    flaky = Scripted(TransportConnectionError(), ok())
    calls, log = executor(
        Ladder(
            (rung("anthropic"),),
            providers=(
                record(
                    "anthropic", lanes={Lane.ANSWER: LaneOverride(timeout_seconds=7.5, attempts=2)}
                ),
            ),
        ),
        {"anthropic": flaky},
    )

    assert complete(calls, Meter()).deployment_id == "anthropic-main-0"
    assert [one.timeout_seconds for one in flaky.sent] == [7.5, 7.5]
    assert len(log.rows) == 2


def test_an_override_for_another_lane_leaves_this_lane_at_the_rungs_numbers() -> None:
    """The sibling: overrides are per lane. Delete this and a task-lane timeout meant for
    overnight work is what a person waiting on the answer lane gets."""
    transport = Scripted(ok())
    calls, _ = executor(
        Ladder(
            (rung("anthropic"),),
            providers=(record("anthropic", lanes={Lane.TASK: LaneOverride(timeout_seconds=90.0)}),),
        ),
        {"anthropic": transport},
    )

    complete(calls, Meter())

    assert transport.sent[0].timeout_seconds == 12.0


# ------------------------------------------------------ residency from the registry (M5.5.2)
def test_a_constrained_call_skips_an_undocumented_rung_for_the_documented_one_behind_it() -> None:
    """M5.5.2 end to end: the registry documents one provider as pinned to a region, the rung
    ahead of it is undocumented and global, and a request pinned to that region skips the first
    for the second rather than degrading to it.

    Delete this and the registry's region is stored and never reaches routing."""
    anywhere = Scripted(ok())
    in_region = Scripted(ok())
    calls, _ = executor(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)),
            providers=(
                record("moonshot", region="eu-west-1", residency=ResidencyClass.REGION_PINNED),
            ),
        ),
        {"anthropic": anywhere, "moonshot": in_region},
    )

    answered = complete(
        calls,
        Meter(),
        residency=ResidencyRequirement(allowed_regions=frozenset({"eu-west-1"})),
    )

    assert answered.deployment_id == "moonshot-main-1"
    assert anywhere.sent == []


# ----------------------------------------------------------- what was sent (M5.6.4)
def test_every_attempt_records_the_categories_of_data_it_sent() -> None:
    """M5.6.4: the attempt row carries what the prompt carried, on every try.

    Delete this and the provider register counts nothing, however much was sent."""
    flaky = Scripted(TransportConnectionError(), ok())
    calls, log = executor(
        Ladder((rung("anthropic", attempts=2),)),
        {"anthropic": flaky},
    )

    complete(
        calls,
        Meter(),
        categories=(DataCategory.QUESTION, DataCategory.DOCUMENT_PASSAGES),
    )

    assert [row["categories"] for row in log.rows.values()] == [
        ("document_passages", "question"),
        ("document_passages", "question"),
    ]


# ------------------------------------------------------ an added provider (M5.7.2)
class Added:
    """An `AddedProviders` handing back one driver for each added record, and a key for each."""

    def __init__(self, transport: Scripted) -> None:
        self.transport = transport

    def drivers(self, records: Sequence[ProviderRecord]) -> dict[str, ModelDriver]:
        return {
            one.slug: SdkDriver(provider=one.slug, transport=self.transport)
            for one in records
            if one.kind is ProviderKind.OPENAI_COMPATIBLE
        }

    def held(self, records: Sequence[ProviderRecord]) -> frozenset[str]:
        return frozenset(one.slug for one in records if one.kind is ProviderKind.OPENAI_COMPATIBLE)


def test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release() -> None:
    """M5.7.2: a row and a key are all an added provider needs to answer a rung naming it.

    Delete this and an added provider sits on the Models screen with every rung naming it left
    out for want of a transport."""
    added = Scripted(ok())
    ladder = Ladder(
        (rung("acme_llm", model="acme-large"),),
        providers=(
            ProviderRecord(
                slug="acme_llm",
                kind=ProviderKind.OPENAI_COMPATIBLE,
                label="Acme",
                base_url="https://llm.example.test/v1",
                models=("acme-large",),
            ),
        ),
    )
    calls = ModelCalls(
        ladder=ladder,
        attempts=Log(),
        drivers={},
        profile=lambda: HOSTED_PROFILE,
        held=frozenset,
        clock=lambda: T0,
        added=Added(added),
    )

    assert complete(calls, Meter()).deployment_id == "acme_llm-main-0"
    assert len(added.sent) == 1


def test_an_added_provider_cannot_replace_a_built_in_providers_driver() -> None:
    """The product's own drivers win a name clash. Delete this and a row named like a built-in
    provider would carry that provider's questions to an address a person typed."""
    builtin = Scripted(ok())
    impostor = Scripted(ok())

    class Clashing(Added):
        def drivers(self, records: Sequence[ProviderRecord]) -> dict[str, ModelDriver]:
            return {"anthropic": SdkDriver(provider="anthropic", transport=self.transport)}

    calls = ModelCalls(
        ladder=Ladder((rung("anthropic"),)),
        attempts=Log(),
        drivers={"anthropic": SdkDriver(provider="anthropic", transport=builtin)},
        profile=lambda: HOSTED_PROFILE,
        held=lambda: frozenset({"anthropic"}),
        clock=lambda: T0,
        added=Clashing(impostor),
    )

    complete(calls, Meter())

    assert len(builtin.sent) == 1
    assert impostor.sent == []


def test_a_trial_plans_from_the_changed_ladder_and_leaves_the_live_one_alone() -> None:
    """M5.6.2's copy: `trying` changes what a plan reads and nothing else.

    Delete this and the matrix gate's trial can reach, or be, the live ladder."""
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": Scripted(ok())})
    trial = calls.trying(lambda rungs: ())

    assert asyncio.run(trial.planned()).state.rungs == ()
    assert len(asyncio.run(calls.planned()).state.rungs) == 1


# ------------------------------------------------------------ the tier table (M5.2.2)
def test_a_request_is_classified_against_the_tier_table_the_ladder_read() -> None:
    """**M5.2.2 on the live path.** The same request lands on main with no tier row and on heavy
    when `ops.routing_tier` says main holds fewer tokens than it carries, and the heavy rung is
    the one called.

    Delete this and the router goes back to the compiled windows, and a tier row saved on the
    Models screen changes nothing a person's question does."""
    asked = RoutingRequest(lane=Lane.ANSWER, estimated_context_tokens=60_000)
    rungs = (rung("anthropic"), rung("moonshot", tier=Tier.HEAVY))

    compiled, _ = executor(Ladder(rungs), {"anthropic": Scripted(ok()), "moonshot": Scripted(ok())})
    table, _ = executor(
        Ladder(rungs, tiers=(TierRule(Tier.MAIN, 50_000),)),
        {"anthropic": Scripted(ok()), "moonshot": Scripted(ok())},
    )

    assert complete(compiled, Meter(), tier=None, routing=asked).deployment_id == (
        "anthropic-main-0"
    )
    assert complete(table, Meter(), tier=None, routing=asked).deployment_id == "moonshot-heavy-0"


def test_a_call_naming_neither_a_tier_nor_a_request_is_refused_before_anything_is_read() -> None:
    """Delete this and a caller forgetting both would route somewhere by default."""
    calls, log = executor(Ladder((rung("anthropic"),)), {"anthropic": Scripted(ok())})

    with pytest.raises(ValueError, match="names its tier"):
        complete(calls, Meter(), tier=None)
    with pytest.raises(ValueError, match="cannot be sent"):
        complete(calls, Meter(), routing=RoutingRequest(lane=Lane.TASK))
    assert log.rows == {}


# ------------------------------------------------------ residency from a scope (M5.5.1)
FINANCE = Scope.department("finance")
EU = ScopedResidency(
    scope=FINANCE, requirement=ResidencyRequirement(allowed_regions=frozenset({"eu-west-1"}))
)


def test_a_reach_touching_a_constrained_scope_skips_the_rung_outside_its_regions() -> None:
    """**M5.5.1.** The constraint is attached to finance's scope, the request carries a reach over
    finance, and the executor skips the undocumented rung for the one in the allowed region.

    Delete this and a constraint written on the Models screen is stored and never reaches the
    chain, which is the state every call was in before the request carried it."""
    anywhere = Scripted(ok())
    in_region = Scripted(ok())
    calls, _ = executor(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)),
            providers=(
                record("moonshot", region="eu-west-1", residency=ResidencyClass.REGION_PINNED),
            ),
            residency=(EU,),
        ),
        {"anthropic": anywhere, "moonshot": in_region},
    )

    assert complete(calls, Meter(), reach=(FINANCE,)).deployment_id == "moonshot-main-1"
    assert anywhere.sent == []


def test_a_reach_with_nowhere_compliant_is_refused_and_one_elsewhere_is_answered() -> None:
    """The refusal and its sibling: the same ladder refuses a finance reader, because no rung is
    in the allowed region, and answers a sales reader, whose reach provably misses the scope.

    Delete this and a constrained request could degrade to a non-compliant rung, or every request
    could be held to a constraint on one department."""
    anywhere = Scripted(ok())
    calls, _ = executor(Ladder((rung("anthropic"),), residency=(EU,)), {"anthropic": anywhere})

    with pytest.raises(NoCompliantRoute):
        complete(calls, Meter(), reach=(FINANCE,))
    assert anywhere.sent == []

    assert complete(calls, Meter(), reach=(Scope.department("sales"),)).deployment_id == (
        "anthropic-main-0"
    )


# ------------------------------------------------------------- the stored rings (M5.4.3)
def test_every_answer_and_every_provider_failure_is_appended_to_its_live_ring() -> None:
    """**M5.4.3, fed by live calls.** A 503 on the primary and an answer from the second each reach
    the ring; a 429 does not, because a rate limit is the provider working.

    Delete this and the stored ring is a table nothing writes, and the console's live figures for
    a rung nothing has called in the window go blank."""
    rings = Rings()
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1), rung("deepseek", position=2))),
        {
            "anthropic": Scripted(TransportStatusError(503)),
            "moonshot": Scripted(TransportStatusError(429)),
            "deepseek": Scripted(ok()),
        },
        rings=rings,
    )

    complete(calls, Meter())

    assert rings.seen == [
        ("anthropic-main-0", "anthropic", False),
        ("deepseek-main-2", "deepseek", True),
    ]


def test_two_failed_probes_on_a_rung_with_no_live_traffic_take_it_out_of_the_next_plan() -> None:
    """**M5.4.7 reaching the live path.** The prober's ring holds two failures a minute apart and
    no attempt has touched the rung, so the replay opens its breaker and the call goes to the
    second rung without asking the first.

    Delete this and the prober writes a ring nothing reads, and the first person to need the
    rung is its probe after all."""
    dead = Scripted(ok())
    calls, _ = executor(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)),
            rings=(
                StoredRings(
                    deployment_id="anthropic-main-0",
                    provider="anthropic",
                    probe=(
                        RingEntry(ok=False, at=T0 - timedelta(seconds=70)),
                        # Ten seconds ago, so the breaker it opens is still inside its thirty-second
                        # cooldown at T0 rather than half open again.
                        RingEntry(ok=False, at=T0 - timedelta(seconds=10)),
                    ),
                ),
            ),
        ),
        {"anthropic": dead, "moonshot": Scripted(ok())},
    )

    assert complete(calls, Meter()).deployment_id == "moonshot-main-1"
    assert dead.sent == []


def test_one_failed_probe_leaves_the_rung_in_the_chain() -> None:
    """The sibling: one synthetic failure is as likely our network as the provider's. Delete this
    and a single DNS hiccup on the prober takes a provider out of rotation."""
    primary = Scripted(ok())
    calls, _ = executor(
        Ladder(
            (rung("anthropic"), rung("moonshot", position=1)),
            rings=(
                StoredRings(
                    deployment_id="anthropic-main-0",
                    provider="anthropic",
                    probe=(RingEntry(ok=False, at=T0 - timedelta(seconds=30)),),
                ),
            ),
        ),
        {"anthropic": primary, "moonshot": Scripted(ok())},
    )

    assert complete(calls, Meter()).deployment_id == "anthropic-main-0"


# ------------------------------------------------------------- depth alerting (M5.4.8)
def test_an_answer_from_the_second_rung_raises_a_warning_naming_the_tier_and_depth() -> None:
    """**M5.4.8, produced by the live path.** The primary failed, the second answered, the person
    got their answer, and the alert says the chain went to rung two.

    Delete this and `assess_chain_depth` stays a function no call ever asks, which is the state it
    was in: a dead primary reads as healthy for as long as the fallback holds."""
    alerts = Alerts()
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": Scripted(TransportStatusError(503)), "moonshot": Scripted(ok())},
        alerts=alerts,
    )

    complete(calls, Meter())

    ((alert, trace),) = alerts.raised
    assert (alert.level, alert.tier, alert.depth, alert.served_by) == (
        AlertLevel.WARNING,
        Tier.MAIN,
        2,
        "moonshot-main-1",
    )
    assert trace == TRACE


def test_a_chain_that_runs_out_raises_a_critical_alert_as_well_as_the_failure() -> None:
    """Delete this and an exhausted chain would raise to the caller and leave no alert, because
    the judging would be skipped by the exception."""
    alerts = Alerts()
    calls, _ = executor(
        Ladder((rung("anthropic"),)),
        {"anthropic": Scripted(TransportStatusError(503))},
        alerts=alerts,
    )

    with pytest.raises(ProviderUnavailable):
        complete(calls, Meter())

    ((alert, _),) = alerts.raised
    assert alert.level is AlertLevel.CRITICAL


def test_an_answer_from_the_primary_and_an_overflow_upward_raise_nothing() -> None:
    """The siblings: the chain working as designed is not an alert. Delete this and every
    question would page somebody, or a long question escalating to heavy would."""
    alerts = Alerts()
    healthy, _ = executor(
        Ladder((rung("anthropic"),)), {"anthropic": Scripted(ok())}, alerts=alerts
    )
    complete(healthy, Meter())

    overflowing, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", tier=Tier.HEAVY))),
        {
            "anthropic": Scripted(ContextWindowExceededError()),
            "moonshot": Scripted(ok()),
        },
        alerts=alerts,
    )
    assert complete(overflowing, Meter()).deployment_id == "moonshot-heavy-0"

    assert alerts.raised == []


def test_a_trial_on_the_matrix_gate_raises_no_alert() -> None:
    """Delete this and a proposed ladder the gate is still judging could page somebody about a
    chain that is not taking traffic."""
    alerts = Alerts()
    calls, _ = executor(
        Ladder((rung("anthropic"), rung("moonshot", position=1))),
        {"anthropic": Scripted(TransportStatusError(503)), "moonshot": Scripted(ok())},
        alerts=alerts,
    )

    asyncio.run(
        calls.trying(lambda rungs: rungs).complete(
            ASK, tier=Tier.MAIN, lane=Lane.ANSWER, meter=Meter(), trace_id=TRACE
        )
    )

    assert alerts.raised == []
