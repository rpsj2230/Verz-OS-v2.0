"""The one way this system calls a model: plan the chain, walk it, record every try, meter it.

`brain.models.routing` decides the tier and filters the chain, `brain.models.health` owns the
breaker, `brain.models.driver` and `brain.models.adapter` make one call, and nothing joined them:
`routing.plan` had no caller outside tests and `PoolDispatcher.dispatch` dispatched a request
somebody else had already chosen a rung for. `ModelCalls.complete` is the executor those modules
describe and never had, and it is deliberately the only thing holding the drivers, so there is no
way to reach a provider that skips the chain, the attempt row or the meter.

**Every call is metered by construction, because a call cannot be made without a meter.** The
meter is a required argument and belongs to the request that owns the call; see
`brain.models.metering` for why it is handed in rather than looked up. Each attempt is counted
before it is sent, an answer adds the provider's token count, and the executor marks a retry or a
fallback on the attempt that is one. See `A_MODEL_CALL_WITHOUT_A_METER_HAS_NO_DOOR`.

**Every attempt leaves a row before it is sent and is finished when it returns.** That is
`ops.model_attempt`'s own contract (`brain.tables.routing.ModelAttemptRow`: an attempt that never
finishes "has to be visible as an attempt that never finished"), and it is also the evidence the
breaker is replayed from on the next call, in this process and every other. See
`brain.models.evidence.HEALTH_IS_REPLAYED_FROM_THE_ATTEMPTS_SO_EVERY_PROCESS_AGREES`. The log is
told about an attempt and never about its request: no message, no text, no key.

**The ladder is read and assembled on every call.** See `brain.models.assembly` for why: a
provider switched off on the Models screen has to stop receiving questions at once, in every
process, and a chain frozen at start would keep sending them. One read of a few dozen rows is
nothing beside a model call.

**The walk is the policy's, and this module adds only the order of the steps.** For each rung the
chain selected, up to `attempts` tries while its breaker admits; a failure whose trigger is None
stops everything (`routing.trigger_for`); `CONTEXT_EXCEEDED` leaves the tier for the next one up
and never down (`routing.permits_tier_escalation`); any other trigger tries again or moves on.
Rate limiting and a content refusal are not a reason to open a breaker, and that decision is
`evidence.ONLY_THE_PROVIDERS_OWN_FAILURE_IS_ILL_HEALTH`, applied here to the breakers a single
walk carries so a rung that just opened is not tried again inside the same request.

**A call runs in a worker thread and waits for a slot on its rung.** `ModelDriver` is synchronous
on purpose, so `asyncio.to_thread` is the hop the driver's docstring budgets for, and
`RoutingRung.max_concurrency` becomes a semaphore per deployment in this process, which is what
the rung's ceiling says: "a slow provider becomes queueing rather than unbounded memory".

**Half-open admits one request per process, by claim and return.** A breaker replayed half-open
admits whoever asks `admits`, so every request arriving after a cooldown would be sent to the
provider that just failed. The walk therefore claims through `CircuitBreaker.try_admit` and then
through this executor's own claim on the deployment, which a finished attempt returns. What stays
unshared is the claim between processes, which `brain.models.evidence` states and costs.
See `HALF_OPEN_ADMITS_ONE_REQUEST_PER_PROCESS`.

**A lane's per-provider overrides apply to every try.** A provider's registry row
(`brain.models.registry`) carries `driver.ProviderClient`'s per-lane timeout and attempt
overrides, edited on the Models screen, and each try runs at `ProviderClient.policy_for` for the
request's lane rather than at the rung's own numbers (M5.1.3). A provider with no row runs at its
rung's numbers.

**A pin is tried first and the tier stands behind it.** An agent's pinned provider and model
(M5.7.3) is the answering rung that serves exactly that pair, in whichever tier holds it; it is
walked before the tier's chain and left out of it afterwards, so it is never tried twice. A pin
naming no answering rung is passed over, because a pin is a choice of model and never a way past
a switch, a missing key, a residency constraint or an open breaker. A failure that stops a chain
stops a pinned one too: a refusal from the pinned model is not tried on the tier's.

**Each try records what categories of data it sent** (M5.6.4), as the caller named them, on the
attempt row. See `brain.models.disclosure`.

**Not built, and said.** The probe loop `health.next_probes` describes has no scheduler, so an
idle provider's health is whatever its last real attempts say. The callers are the Models
screen's provider check, the matrix gate (`brain.ops.matrix_gate_run`) and
`brain.gate.model_lane`, the answer lane's step for a question no fast-path rule answers.

Task ids: M27.7.14, M27.8.8, M5.3.4, M5.4.6, M5.1.3, M5.7.3, M5.6.4, M5.7.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from brain.core.lane import Lane
from brain.models.assembly import Assembly, LadderRung, assemble
from brain.models.disclosure import DataCategory
from brain.models.driver import (
    CallPolicy,
    DriverFailure,
    DriverMessage,
    DriverRequest,
    DriverResponse,
    ModelDriver,
    ProviderUnavailable,
)
from brain.models.evidence import Attempt, outcome_of, replayed
from brain.models.health import ProviderHealth
from brain.models.metering import Meter
from brain.models.registry import ModelPin, ProviderRecord
from brain.models.routing import (
    BREAKER_PROBE_CLAIM_TTL_SECONDS,
    TIER_LADDER,
    UNCONSTRAINED,
    BreakerState,
    CircuitBreaker,
    FallbackTrigger,
    NoCompliantRoute,
    ResidencyRequirement,
    RoutingChain,
    RoutingRung,
    Tier,
    permits_tier_escalation,
)

# ------------------------------------------------------------------- written-down reasons

#: Why the executor takes the meter as a required argument.
A_MODEL_CALL_WITHOUT_A_METER_HAS_NO_DOOR: Final = (
    "The executor is the only holder of the drivers and it will not call one without a meter "
    "belonging to the request making the call. A call that could be made unmetered is a call "
    "whose tokens appear on no ledger row, and a usage screen reading that ledger would report "
    "less than the invoice for as long as nobody noticed."
)

#: Why a half-open deployment is claimed by one walk at a time.
HALF_OPEN_ADMITS_ONE_REQUEST_PER_PROCESS: Final = (
    "A breaker that has cooled down is half open, and half open means one request finds out "
    "whether the provider recovered. Every walk replays the same half-open breaker from the "
    "attempts, so without a claim every request in the process would be that one request. A "
    "walk claims the deployment before sending and the attempt's return releases it; a claim "
    "nobody returns expires after the breaker's own claim lifetime."
)

#: The breaker outcomes a walk treats as the provider failing. See `brain.models.evidence`.
_ILL: Final[frozenset[FallbackTrigger]] = frozenset(
    {FallbackTrigger.CONNECTION_ERROR, FallbackTrigger.TIMEOUT, FallbackTrigger.PROVIDER_ERROR}
)


# ------------------------------------------------------------------------------ the ports


@dataclass(frozen=True)
class LadderState:
    """What one call reads before it plans: the live rungs, the switches, and recent attempts."""

    rungs: tuple[LadderRung, ...]
    switched_off: frozenset[str]
    attempts: tuple[Attempt, ...]
    #: The provider registry's live rows: terms, lane overrides, and the providers an
    #: administrator added from the console.
    providers: tuple[ProviderRecord, ...] = ()


class AddedProviders(Protocol):
    """How the executor reaches providers added from the console, which exist only as rows."""

    def drivers(self, records: Sequence[ProviderRecord]) -> Mapping[str, ModelDriver]:
        """A driver for each added provider in `records`, keyed by its slug."""
        ...

    def held(self, records: Sequence[ProviderRecord]) -> frozenset[str]:
        """The added providers whose key this process holds. Names, never values."""
        ...


class NoAddedProviders:
    """A process that reaches no added provider: no drivers, no keys."""

    def drivers(self, records: Sequence[ProviderRecord]) -> Mapping[str, ModelDriver]:
        """Nothing to reach."""
        return {}

    def held(self, records: Sequence[ProviderRecord]) -> frozenset[str]:
        """Nothing held."""
        return frozenset()


class Ladder(Protocol):
    """Where the ladder, the provider switches and the recent attempts are read from."""

    async def current(self, now: datetime) -> LadderState:
        """Everything a call plans from, as it stands at `now`."""
        ...


class AttemptLog(Protocol):
    """Where each try is written. Never raises: a lost row must not lose the answer with it."""

    async def started(
        self,
        *,
        trace_id: str,
        rung_id: str,
        sequence: int,
        at: datetime,
        categories: tuple[str, ...] = (),
    ) -> str:
        """Write the row for an attempt about to be sent, and return what finishes it."""
        ...

    async def finished(self, token: str, *, at: datetime, outcome: str, status: int | None) -> None:
        """Finish the row `started` returned `token` for."""
        ...


# ---------------------------------------------------------------------------- the executor


@dataclass(frozen=True)
class Planned:
    """One call's view of the estate: the assembly and the replayed health, from one read."""

    assembly: Assembly
    health: Mapping[str, ProviderHealth]
    state: LadderState
    #: The install's model profile as this plan read it.
    profile: str
    #: The providers whose key this process held when this plan was made. Names, never values.
    held: frozenset[str]


class ModelCalls:
    """The executor. Holds the drivers, reads the ladder per call, and never calls unmetered."""

    def __init__(
        self,
        *,
        ladder: Ladder,
        attempts: AttemptLog,
        drivers: Mapping[str, ModelDriver],
        profile: Callable[[], str],
        held: Callable[[], frozenset[str]],
        clock: Callable[[], datetime],
        added: AddedProviders | None = None,
    ) -> None:
        self._ladder = ladder
        self._added: AddedProviders = NoAddedProviders() if added is None else added
        self._attempts = attempts
        self._drivers = drivers
        self._profile = profile
        self._held = held
        self._clock = clock
        self._slots: dict[str, asyncio.Semaphore] = {}
        #: Deployments a walk in this process has claimed while half open, and when.
        self._claims: dict[str, datetime] = {}

    def trying(
        self, change: Callable[[tuple[LadderRung, ...]], tuple[LadderRung, ...]]
    ) -> ModelCalls:
        """This executor planning from a changed copy of the ladder, for the matrix gate (M5.6.2).

        The drivers, the attempt log, the keys and the clock are this executor's own; only the
        rungs a plan reads differ, so a trial is the call a person's question would make after
        the change, and nothing about the live ladder moves.
        """
        return ModelCalls(
            ladder=_TrialLadder(self._ladder, change),
            attempts=self._attempts,
            drivers=self._drivers,
            profile=self._profile,
            held=self._held,
            clock=self._clock,
            added=self._added,
        )

    async def planned(self) -> Planned:
        """The ladder as it can be called now, and every deployment's health from its attempts.

        The same answer a call plans from, so a screen drawing this draws what the next call
        will do.
        """
        state = await self._ladder.current(self._clock())
        profile = self._profile()
        held = self._held() | self._added.held(state.providers)
        # The product's own drivers last, so an added provider can never replace one.
        drivers = {**self._added.drivers(state.providers), **self._drivers}
        assembly = assemble(
            state.rungs,
            profile=profile,
            switched_off=state.switched_off,
            held=held,
            drivers=drivers,
            registry={one.slug: one for one in state.providers},
        )
        return Planned(
            assembly=assembly,
            health=replayed(state.attempts),
            state=state,
            profile=profile,
            held=held,
        )

    async def complete(
        self,
        messages: Sequence[DriverMessage],
        *,
        tier: Tier,
        lane: Lane,
        meter: Meter,
        trace_id: str,
        agent_version: str | None = None,
        max_output_tokens: int | None = None,
        residency: ResidencyRequirement = UNCONSTRAINED,
        provider: str | None = None,
        pin: ModelPin | None = None,
        categories: Iterable[DataCategory] = (),
    ) -> DriverResponse:
        """One model call for one request, through the chain, or `Degraded` saying why not.

        `provider` narrows the chain to one provider's rungs, for a check an administrator asked
        for; nothing else sets it. `pin` is an agent's pinned provider and model, tried first.
        `categories` is what the messages carry, recorded on every attempt. Raises
        `NoCompliantRoute` when no rung can be tried and `ProviderUnavailable` carrying the last
        failure when every rung tried failed.
        """
        if lane is Lane.FAST:
            msg = "the fast lane takes no model, so a model call on it is a bug, not a route"
            raise ValueError(msg)
        plan = await self.planned()
        chain = plan.assembly.chain if provider is None else plan.assembly.for_provider(provider)
        walk = _Walk(
            assembly=plan.assembly,
            breakers={deployment: one.breaker for deployment, one in plan.health.items()},
            meter=meter,
            trace_id=trace_id,
            agent_version=agent_version,
            messages=tuple(messages),
            max_output_tokens=max_output_tokens,
            clock=self._clock,
            attempts=self._attempts,
            slot=self._slot,
            claims=self._claims,
            lane=lane,
            categories=tuple(sorted({one.value for one in categories})),
        )
        pinned = None if pin is None else self._pinned(chain, pin, residency, walk)
        if pinned is not None:
            answered = await walk.through(pinned.tier, (pinned,))
            if answered is not None:
                return answered
            # An overflow on the pinned model leaves the decision to the tier's own chain, which
            # starts at the agent's tier; the pinned rung is not tried again either way.
            walk.overflowed = False
        skip = frozenset() if pinned is None else frozenset({pinned.deployment.id})
        current: Tier | None = tier
        while current is not None:
            selection = chain.select(
                current, residency=residency, breakers=walk.breakers, now=self._clock()
            )
            rungs = tuple(one for one in selection.rungs if one.deployment.id not in skip)
            if not rungs and walk.last is not None:
                # An escalation, or a pin that failed, reached a tier with nothing left to try.
                # The honest failure is the last one, not a claim that nothing was configured.
                raise ProviderUnavailable(walk.last)
            if not rungs:
                selection.require()
            answered = await walk.through(current, rungs)
            if answered is not None:
                return answered
            current = walk.escalate_from(current)
        if walk.last is None:  # pragma: no cover - a selection that required rungs tried one
            msg = "a walk ended with no answer and no failure"
            raise NoCompliantRoute(msg)
        raise ProviderUnavailable(walk.last)

    def _pinned(
        self,
        chain: RoutingChain,
        pin: ModelPin,
        residency: ResidencyRequirement,
        walk: _Walk,
    ) -> RoutingRung | None:
        """The answering rung serving exactly the pinned pair that may be tried now, or None.

        Looked for in every tier in ladder order, through the tier's own selection, so the pin is
        subject to the residency constraint and the breakers exactly as its rung is anywhere else.
        """
        for tier in TIER_LADDER:
            selection = chain.select(
                tier, residency=residency, breakers=walk.breakers, now=self._clock()
            )
            for one in selection.rungs:
                if one.deployment.provider == pin.provider and one.model == pin.model:
                    return one
        return None

    def _slot(self, rung: RoutingRung) -> asyncio.Semaphore:
        """This process's concurrency slots for one deployment, made on first use."""
        found = self._slots.get(rung.deployment.id)
        if found is None:
            found = asyncio.Semaphore(rung.max_concurrency)
            self._slots[rung.deployment.id] = found
        return found


class _TrialLadder:
    """A ladder read as it stands with a proposed change applied. See `ModelCalls.trying`."""

    def __init__(
        self,
        base: Ladder,
        change: Callable[[tuple[LadderRung, ...]], tuple[LadderRung, ...]],
    ) -> None:
        self._base = base
        self._change = change

    async def current(self, now: datetime) -> LadderState:
        state = await self._base.current(now)
        return LadderState(
            rungs=self._change(state.rungs),
            switched_off=state.switched_off,
            attempts=state.attempts,
            providers=state.providers,
        )


class _Walk:
    """One request's progress down the chain: what it tried, what it learned, what it counts."""

    def __init__(
        self,
        *,
        assembly: Assembly,
        breakers: Mapping[str, CircuitBreaker],
        meter: Meter,
        trace_id: str,
        agent_version: str | None,
        messages: tuple[DriverMessage, ...],
        max_output_tokens: int | None,
        clock: Callable[[], datetime],
        attempts: AttemptLog,
        slot: Callable[[RoutingRung], asyncio.Semaphore],
        claims: dict[str, datetime] | None = None,
        lane: Lane = Lane.ANSWER,
        categories: tuple[str, ...] = (),
    ) -> None:
        self.assembly = assembly
        self.breakers: dict[str, CircuitBreaker] = dict(breakers)
        self.meter = meter
        self.trace_id = trace_id
        self.agent_version = agent_version
        self.messages = messages
        self.max_output_tokens = max_output_tokens
        self.clock = clock
        self.attempts = attempts
        self.slot = slot
        self.claims: dict[str, datetime] = {} if claims is None else claims
        self.lane = lane
        self.categories = categories
        self.sequence = 0
        self.last: DriverFailure | None = None
        self.last_deployment: str | None = None
        self.overflowed = False

    async def through(self, tier: Tier, rungs: tuple[RoutingRung, ...]) -> DriverResponse | None:
        """Try this tier's rungs in order. The answer, or None to go on, or a raise to stop."""
        for rung in rungs:
            for _ in range(self.policy(rung).attempts):
                claimed = self._admit(rung.deployment.id)
                if claimed is None:
                    # Open, or half open and claimed by another walk, or opened by a failure
                    # earlier in this same walk: the provider is not asked again here.
                    break
                try:
                    answered = await self._attempt(tier, rung)
                finally:
                    if claimed:
                        self.claims.pop(rung.deployment.id, None)
                if answered is not None:
                    return answered
                if self.overflowed:
                    return None
        return None

    def _admit(self, deployment_id: str) -> bool | None:
        """None when this deployment may not be tried now; else whether a claim was taken.

        Claim and return: `try_admit` is the breaker's claim, and a half-open admission is also
        claimed in this process's map, so two walks replaying the same half-open breaker do not
        both send. See `HALF_OPEN_ADMITS_ONE_REQUEST_PER_PROCESS`.
        """
        breaker = self.breakers.get(deployment_id)
        if breaker is None:
            return False
        now = self.clock()
        current, admitted = breaker.try_admit(now)
        if not admitted:
            return None
        if current.state is not BreakerState.HALF_OPEN:
            return False
        held = self.claims.get(deployment_id)
        if held is not None and (now - held).total_seconds() < BREAKER_PROBE_CLAIM_TTL_SECONDS:
            return None
        self.claims[deployment_id] = now
        self.breakers[deployment_id] = current
        return True

    def policy(self, rung: RoutingRung) -> CallPolicy:
        """The rung's numbers with its provider's override for this lane, or its own (M5.1.3)."""
        record = self.assembly.registry.get(rung.deployment.provider)
        if record is None:
            return CallPolicy(
                timeout_seconds=rung.timeout_seconds,
                attempts=rung.attempts,
                max_concurrency=rung.max_concurrency,
            )
        return record.client.policy_for(rung, self.lane)

    async def _attempt(self, tier: Tier, rung: RoutingRung) -> DriverResponse | None:
        """One try: counted, recorded, sent, recorded again, and learned from."""
        ladder_rung = self.assembly.rung(rung.deployment.id, tier)
        if self.last is not None:
            if self.last_deployment == rung.deployment.id:
                self.meter.retried()
            else:
                self.meter.fell_back()
        self.meter.attempted()
        token = await self.attempts.started(
            trace_id=self.trace_id,
            rung_id=ladder_rung.rung_id,
            sequence=self.sequence,
            at=self.clock(),
            categories=self.categories,
        )
        self.sequence += 1
        request = DriverRequest(
            deployment_id=rung.deployment.id,
            model=rung.model,
            messages=self.messages,
            timeout_seconds=self.policy(rung).timeout_seconds,
            max_output_tokens=self.max_output_tokens,
        )
        driver = self.assembly.drivers[rung.deployment.provider]
        try:
            async with self.slot(rung):
                response = await asyncio.to_thread(driver.complete, request)
        except ProviderUnavailable as failed:
            failure = failed.failure
            at = self.clock()
            await self.attempts.finished(
                token, at=at, outcome=outcome_of(failure), status=failure.status
            )
            self._learn(rung, at, failure)
            trigger = failure.trigger
            if trigger is None:
                raise
            if permits_tier_escalation(trigger):
                self.overflowed = True
            return None
        await self.attempts.finished(token, at=self.clock(), outcome=outcome_of(None), status=None)
        self.meter.answered(
            response, provider=rung.deployment.provider, agent_version=self.agent_version
        )
        return response

    def _learn(self, rung: RoutingRung, at: datetime, failure: DriverFailure) -> None:
        """Remember the failure, and move this walk's breaker when the failure is the provider's."""
        self.last = failure
        self.last_deployment = rung.deployment.id
        if failure.trigger in _ILL:
            known = self.breakers.get(rung.deployment.id)
            breaker = CircuitBreaker(deployment_id=rung.deployment.id) if known is None else known
            self.breakers[rung.deployment.id] = breaker.record_failure(at)

    def escalate_from(self, tier: Tier) -> Tier | None:
        """The next tier up after an overflow, or None. Never down, and only after an overflow."""
        if not self.overflowed:
            return None
        self.overflowed = False
        if tier not in TIER_LADDER:
            return None
        index = TIER_LADDER.index(tier)
        return TIER_LADDER[index + 1] if index + 1 < len(TIER_LADDER) else None


def chain_of(rungs: Sequence[LadderRung]) -> RoutingChain:
    """Every live rung as one chain, answering or not, for a screen that must show them all."""
    return RoutingChain(rungs=tuple(one.routing_rung() for one in rungs))
