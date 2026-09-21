"""The gate's front half after entitlement: screen, classify and select, cache, route, project.

Every piece already existed and nothing ran them in a row. `injection.assess` scored text,
`classify.classify_lane` and `select.select_agent` decided without a model, `answer_cache.lookup`
found an answer, `models.routing.classify_tier` chose a tier and `catalogue.project` built the
tools a model is shown. `/answer` called none of them: it identified, entitled, narrowed and asked
the model. This is the one function that runs them, in the order `GateStep` declares, and it
enters each step on the request's `Recorder` so running one out of order is an error rather than
a refactor.

**It starts only after entitlement, and it takes the narrowed reach.** It refuses a recorder that
has not reached ENTITLE, so the cache key and the catalogue cannot be computed at a reach nobody
resolved. Identification and entitlement stay in `brain.api_routes.asking`, which is the one
dependency every route takes; a second place that authenticates would be a second place to get
it wrong.

**Selection comes before the cache, because the key names the agent.** `CacheKeyParts` carries
the agent's configuration hash, so an answer cannot be looked up before the agent that would
give it is known. A hit stops the chain there: no model is called, so no tier is routed and no
catalogue is projected, and the recorder shows it stopped at CACHE.

**The route is decided on the agent's ceiling, not on the projected catalogue.** The owner's
order routes before projecting. `classify_tier` only ever raises a tier for a tool loop, and
projection only ever removes tools, so routing on the ceiling's size is at least as cautious as
routing on what survived. The fast lane takes no model, so it is routed to no tier and nothing is
projected for it.

**The screen never refuses.** `injection.assess` has nowhere to express a refusal (M3.4.3); the
score travels on `FrontHalf` to the leash, which may only tighten autonomy, and to the request
row through `FrontHalf.record`, which is where M3.4.2 and M3.6.3 are written as decided.

Rejected: putting this inside `brain.gate.answer.answer_lane`. That module is the lane's, and the
front half decides things about a request whatever lane it lands in; a task-lane run needs the
same five steps.

Task ids: M3.1.2, M3.4.1, M3.4.2, M3.6.3, M3.9.7
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import ToolDefinition
from brain.core.lane import Lane
from brain.gate.answer_cache import AnswerStore, lookup
from brain.gate.cache_key import CachedAnswer, NotCacheableError, key_for
from brain.gate.catalogue import AgentCeiling, ProjectedCatalogue, project
from brain.gate.classify import LaneDecision, classify_lane
from brain.gate.context import Channel, GateStep, Recorder, StepOutOfOrderError
from brain.gate.finish import FrontRecord
from brain.gate.injection import RiskAssessment, assess
from brain.gate.select import AgentBinding, AgentSelection, SelectionRule, select_agent
from brain.models.routing import RoutingRequest, Tier, TierDecision, classify_tier


@dataclass(frozen=True)
class AgentSetup:
    """What the chain needs about one agent it may select: its ceiling, its configuration hash
    for the cache key, and the tier its author pinned, if any."""

    ceiling: AgentCeiling
    config_hash: str
    tier: Tier | None = None

    def __post_init__(self) -> None:
        if not self.config_hash:
            raise ValueError(f"agent {self.ceiling.agent_id} has no configuration hash to key on")


@dataclass(frozen=True)
class Choosing:
    """Which agents this person may be answered by, and how the choice between them is made.

    `visible_agents` is the set `brain.agents.model` computes: visible and enabled. The chain
    narrows it further to agents it has a setup for, so selection cannot land on an agent the
    rest of the chain knows nothing about.
    """

    visible_agents: frozenset[str]
    default_agent: str
    bindings: tuple[AgentBinding, ...] = ()
    rules: tuple[SelectionRule, ...] = ()
    conversation_id: str | None = None
    #: The agent the person named, already resolved to an id. See `select_agent`.
    addressed: str | None = None


@dataclass(frozen=True)
class Caching:
    """What an answer-cache lookup needs beyond the question and the reach."""

    store: AnswerStore
    policy_epoch: int
    #: The epochs of the sources the selected agent's answers rest on.
    source_epochs: Mapping[str, int] = field(default_factory=dict)
    sources: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FrontHalf:
    """Every decision the front half made, and only the ones it reached.

    `tier` and `catalogue` are None on a cache hit, because nothing after a hit asks a model;
    `catalogue` is also None on the fast lane, which asks none either.
    """

    screened: RiskAssessment
    lane: LaneDecision
    selection: AgentSelection
    cached: CachedAnswer | None
    tier: TierDecision | None
    catalogue: ProjectedCatalogue | None

    @property
    def calls_a_model(self) -> bool:
        return self.cached is None and self.tier is not None and self.tier.tier is not Tier.NONE

    def record(self) -> FrontRecord:
        """What the request row holds of these decisions. See `FrontRecord`."""
        return FrontRecord(
            risk_score=self.screened.score,
            routed_lane=self.lane.lane,
            selection_stage=self.selection.stage,
            selected_agent=self.selection.agent_id,
        )


def run_front_half(
    question: str,
    *,
    recorder: Recorder,
    reach: EntitlementSet,
    channel: Channel,
    agents: Mapping[str, AgentSetup],
    choosing: Choosing,
    registry: Iterable[ToolDefinition],
    now: datetime,
    caching: Caching | None = None,
    requested_lane: Lane | None = None,
    universal: frozenset[str] = frozenset(),
) -> FrontHalf:
    """Screen, classify and select, look up, route and project, entering each step in order.

    `reach` is the narrowed entitlement `gate.admission.admit` returned, and nothing else: it is
    what the cache is keyed on and what the catalogue is projected from. `caching` is None on a
    process with no answer store, and the CACHE step is still entered, so the record says the
    step ran and found nothing rather than that it was skipped.
    """
    if not recorder.reached(GateStep.ENTITLE):
        raise StepOutOfOrderError(
            "the front half needs a resolved reach; ENTITLE has not run on this request"
        )
    if choosing.default_agent not in agents:
        raise ValueError("the default agent has no setup, so selection could land on nothing")

    recorder.enter(GateStep.SCREEN)
    screened = assess(question)

    recorder.enter(GateStep.CLASSIFY)
    lane = classify_lane(question, requested=requested_lane)

    recorder.enter(GateStep.SELECT)
    selection = select_agent(
        question,
        channel,
        visible_agents=choosing.visible_agents & frozenset(agents),
        default_agent=choosing.default_agent,
        bindings=choosing.bindings,
        rules=choosing.rules,
        conversation_id=choosing.conversation_id,
        addressed=choosing.addressed,
    )
    setup = agents[selection.agent_id]

    recorder.enter(GateStep.CACHE)
    cached = _cached(question, reach, setup, caching, now)
    if cached is not None:
        return FrontHalf(screened, lane, selection, cached, tier=None, catalogue=None)

    recorder.enter(GateStep.ROUTE)
    tier = classify_tier(
        RoutingRequest(
            lane=lane.lane,
            tool_count=len(setup.ceiling.allowed_tools),
            requested_tier=setup.tier,
        )
    )
    if tier.tier is Tier.NONE:
        return FrontHalf(screened, lane, selection, None, tier=tier, catalogue=None)

    recorder.enter(GateStep.PROJECT)
    catalogue = project(registry, reach, setup.ceiling, now=now, universal=universal)
    return FrontHalf(screened, lane, selection, None, tier=tier, catalogue=catalogue)


def _cached(
    question: str,
    reach: EntitlementSet,
    setup: AgentSetup,
    caching: Caching | None,
    now: datetime,
) -> CachedAnswer | None:
    """A servable cached answer, or None when there is no store, the question is volatile or
    nothing fresh is stored under this reach and agent."""
    if caching is None:
        return None
    try:
        key = key_for(
            question,
            reach.ent_hash(),
            setup.config_hash,
            caching.policy_epoch,
            caching.source_epochs,
            caching.sources,
        )
    except NotCacheableError:
        return None
    return lookup(key, caching.store, now)
