"""The providers this install may use, switched on and off from the console, with measured health.

M27.8.8 asks for "AI providers, models and the routing between them, managed from the console".
The routing between them was already editable (`brain.routing_routes`) and changed nothing,
because nothing called a model; the providers had no registry at all; and the Models and health
screen drew "Not recorded" beside every provider because `brain.console.model_matrix` would have
drawn a closed breaker nobody had tested. This module is the three routes that close those gaps
over `brain.models.calls.ModelCalls`, which the lifespan builds as `app.state.models`.

**One read, and it is the plan the next call makes.** `GET /models/providers` asks the executor
for `planned()`, the same assembly and replayed health `complete` walks, so what the screen says
will answer is what answers, each rung left out says why in `brain.models.assembly.TOLD`'s words,
and each rung's breaker is the one its attempts produced, marked measured or not. A screen that
recomputed any of that would be a second copy of the router's decision, and the copy a person
trusts would be the one that drifted. See `THE_SCREEN_DRAWS_THE_PLAN_THE_NEXT_CALL_MAKES`.

**A switch is a confirmed administrator write, held over everything.** `admin:routing_matrix`,
the routing matrix's own write capability, and only with an unrestricted scope, for the reason
`brain.credential_routes.A_KEY_EVERY_QUESTION_USES_IS_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION`
gives about a key: switching a provider changes where every department's questions go, so a grant
scoped to one department is not a grant here. The capability is asked before the provider's name
is looked at and before the database is, which is `brain.routing_routes`' order and its argument.
The console confirms the write before sending it; this module refuses it without the capability
whatever the console did.

**The switch takes effect on the next call in every process**, because every call reads the
switches (`brain.ops.model_service`), and the answer to the write is the plan read after it, so
the person who switched a provider off sees its rungs leave the chain in the same response.

**Whether a key is held is said two ways, and neither is a key.** `key_held` is whether this
server process's environment names the provider's variable, from
`brain.ops.provider_keys.names_in_environment`, which is what decides whether its rungs answer
here. `credential` is the vault's own answer from `brain.credential_routes.listing`, and it is
served only to a reader who may manage credentials, because that route serves it to nobody else.
A reader of this screen without that authority is told which rungs answer and why, including that
a rung has no key, which is the operational fact the screen exists to show; they are not told what
the vault holds. See `A_KEY_THAT_ANSWERS_HERE_AND_A_KEY_THE_VAULT_HOLDS_ARE_TWO_FACTS`.

**A check is a real call, metered like any other, and a request rather than a probe.** `POST
/models/providers/{provider}/check` sends one fixed sentence through that provider's first
answering rung, as the administrator who pressed it, on the answer lane's budget because a person
is waiting. Its attempts are rows the breaker is replayed from, and its tokens are on its ledger
row. It is not the prober `brain.models.health` keeps out of the live ring: a person pressing a
button once is live traffic through the whole path, and three failed presses opening a breaker is
the breaker being right. The reply is not returned, because nothing a model says about a fixed
sentence is a fact an administrator needs; that it answered, which deployment and model served it,
and what it cost, are. It is recorded on the metadata ledger and not as a question, because it is
not one. See `A_CHECK_IS_A_REQUEST_AND_NOT_A_PROBE`.

**Not written, and said.** A provider switch is an `ops.setting` row, so it keeps its last change
on the row and `0059`'s trigger appends a `setting` entry for it:
`brain.ops.setting_store.A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE`. Nothing
adds a rung or a provider: rungs are rows an installer writes, and a provider is a transport in
`brain.models.wire`, which is the product's to extend.

Task ids: M27.8.8, M27.2.3
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.model_matrix import exhausted_tiers, matrix
from brain.console.operate import figure_basis, panel
from brain.console.workspace import Basis
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.lane import Lane
from brain.credential_routes import SlotView, credentials_of, listing, may_manage
from brain.gate.finish import Finished, ModelCallOutcome, Origin, RequestRecorder, finish
from brain.models.assembly import HOSTED_PROFILE, LOCAL_PROFILE, TOLD, RungSkip, local_only
from brain.models.calls import ModelCalls, Planned, chain_of
from brain.models.driver import DriverMessage, ProviderUnavailable, Role
from brain.models.metering import Meter
from brain.models.routing import TIER_LADDER, BreakerState, FallbackTrigger, NoCompliantRoute, Tier
from brain.models.wire import LOCAL_PROVIDER
from brain.operate_routes import MODELS_SCREEN
from brain.ops.credentials import TOLD as VAULT_TOLD
from brain.ops.credentials import VaultState
from brain.ops.model_service import (
    KNOWN_PROVIDERS,
    ModelService,
    switch_provider,
    switch_states,
)
from brain.ops.provider_keys import PROVIDER_SLOTS
from brain.ops.telemetry_store import TelemetryRecorder
from brain.routing_routes import MATRIX_WRITE

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why this route serves the executor's own plan rather than computing a view of its own.
THE_SCREEN_DRAWS_THE_PLAN_THE_NEXT_CALL_MAKES: Final = (
    "The executor reads the ladder, the switches, the keys and the attempts on every call and "
    "decides which rungs can answer. This route asks it for exactly that, so the screen shows the "
    "chain the next question will walk. A view computed here would be a second copy of the "
    "router's decision, and the one a person reads during an incident would be the copy that "
    "drifted."
)

#: Why the vault's answer and this process's key are served separately.
A_KEY_THAT_ANSWERS_HERE_AND_A_KEY_THE_VAULT_HOLDS_ARE_TWO_FACTS: Final = (
    "A key in this process's environment is what lets its rungs answer, and a key in the vault is "
    "what every process loads at its next start. They differ after a rotation until a restart, "
    "and when the environment file sets the variable. The first decides what this screen draws "
    "as answering and is shown to its readers; the second is the credentials screen's to serve "
    "and is shown only to a reader who may manage credentials."
)

#: Why a check writes a ledger row and attempt rows and is not a probe.
A_CHECK_IS_A_REQUEST_AND_NOT_A_PROBE: Final = (
    "A probe is a synthetic request a scheduler sends on its own, and letting its outcomes move "
    "the live ring lets the prober vote on its own verdict. A check is a person asking, through "
    "the same chain, breaker admission, attempt rows and meter as any call, once per press. Its "
    "outcome is live evidence, its tokens are on the ledger under the person who pressed it, and "
    "it is not a question, so the question count never sees it."
)

# ----------------------------------------------------------------- the figures

#: What a check sends. Fixed, so nothing about the install or a person reaches the provider, and
#: short, so the call costs a handful of tokens.
CHECK_PROMPT: Final = "Reply with the single word: ready"

#: The output ceiling on a check. A one-word reply needs far fewer; the margin is for a model that
#: says a sentence anyway, and the ceiling is what stops it saying a page.
CHECK_MAX_OUTPUT_TOKENS: Final = 16

#: What an administrator is told about a check that did not answer, by the failure it ended on.
CHECK_TOLD: Final = {
    "answered": "The provider answered.",
    "no_rung": (
        "No rung on the routing ladder names this provider, so there is nothing to check. Add a "
        "rung for it, then check again."
    ),
    "out_of_rotation": (
        "Every rung naming this provider is out of rotation on the Routing screen, so nothing "
        "would send it a question. Put a rung back in rotation, then check again."
    ),
    "stopped": (
        "The provider refused the request. Check that its key is valid and that the model the "
        "rung names exists on the provider's account."
    ),
    FallbackTrigger.CONNECTION_ERROR.value: "The provider could not be reached from this server.",
    FallbackTrigger.TIMEOUT.value: "The provider did not answer inside the rung's timeout.",
    FallbackTrigger.RATE_LIMITED.value: (
        "The provider asked for fewer requests. Wait a minute and check again."
    ),
    FallbackTrigger.PROVIDER_ERROR.value: "The provider reported a fault on its side.",
    FallbackTrigger.CIRCUIT_OPEN.value: (
        "Recent calls to this provider failed, so its rungs are resting. Check again once the "
        "cooldown shown beside them has passed."
    ),
    FallbackTrigger.CONTEXT_EXCEEDED.value: "The check did not fit the model's window.",
}


# ------------------------------------------------------------------------ the shapes


class ProviderStateView(BaseModel):
    """One provider: what it is, whether it is switched on, and whether a key is held here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    description: str
    #: Outside the client's own hardware. Every provider but the local inference server.
    hosted: bool
    switched_on: bool
    #: Who last switched it and when, or null for a provider nobody has switched.
    switched_by: str | None
    switched_at: datetime | None
    #: Whether this server process holds a key for it, or null for a provider needing none.
    key_held: bool | None
    #: The vault's own answer for the provider's slot, only for a reader who may manage
    #: credentials. See `A_KEY_THAT_ANSWERS_HERE_AND_A_KEY_THE_VAULT_HOLDS_ARE_TWO_FACTS`.
    credential: SlotView | None


class RungStateView(BaseModel):
    """One live rung: where it sits, whether it answers now, and its measured health."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rung_id: str
    tier: str
    position: int
    role: str
    deployment_id: str
    provider: str
    model: str
    enabled: bool
    answers: bool
    skipped_because: RungSkip | None
    told: str | None
    state: BreakerState
    #: Whether any attempt stands behind `state`.
    measured: bool
    unhealthy_because: str | None
    live_seen: int
    live_failed: int


class ProvidersView(BaseModel):
    """The providers and the ladder as the next call will see them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: `local` or `hosted`, as the executor read it. Anything else is read as `local`.
    profile: str
    providers: list[ProviderStateView]
    rungs: list[RungStateView]
    #: Tiers with at least one rung and every rung open: a tier that cannot answer at all.
    exhausted_tiers: list[str]
    #: Whether this reader may switch a provider or check one. Presentation only.
    editable: bool
    #: The vault's state and sentence, only beside `credential`, for the same reader.
    vault: VaultState | None
    vault_told: str | None


class ProviderSwitchAsked(BaseModel):
    """The one field a switch carries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool


class CheckView(BaseModel):
    """How one check ended. Never the reply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    answered: bool
    #: `answered`, a `RungSkip`, a fallback trigger, `stopped`, `out_of_rotation` or `no_rung`.
    outcome: str
    told: str
    served_by: str | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    #: The provider's HTTP status on a failure that had one.
    status: int | None
    trace_id: str


# ------------------------------------------------------------------------ the decisions


def may_read(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reader's basis for the models screen is everybody's."""
    return figure_basis(panel(MODELS_SCREEN), reach, now) is Basis.EVERYONE


def may_switch(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reader holds the matrix's write capability over everything."""
    scope = reach.scope_for(MATRIX_WRITE, now)
    return scope is not None and scope.is_unrestricted()


def normalised_profile(profile: str) -> str:
    """The profile as the executor acts on it: `hosted`, or `local` for anything else."""
    return LOCAL_PROFILE if local_only(profile) else HOSTED_PROFILE


def providers_view(
    plan: Planned,
    *,
    switches: dict[str, tuple[bool, str, datetime]],
    reach: EntitlementSet,
    now: datetime,
    vault: tuple[VaultState, dict[str, SlotView]] | None,
) -> ProvidersView:
    """The plan and the switch rows, as one reader may be shown them.

    `vault` is None unless the reader may manage credentials; see the module docstring.
    """
    described = {one.slug: one.description for one in PROVIDER_SLOTS}
    providers = []
    for slug in KNOWN_PROVIDERS:
        switched = switches.get(slug)
        providers.append(
            ProviderStateView(
                provider=slug,
                description=described.get(slug, "This install's own inference server"),
                hosted=slug != LOCAL_PROVIDER,
                switched_on=True if switched is None else switched[0],
                switched_by=None if switched is None else switched[1],
                switched_at=None if switched is None else switched[2],
                key_held=None if slug == LOCAL_PROVIDER else slug in plan.held,
                credential=None if vault is None else vault[1].get(slug),
            )
        )
    skipped = {(one.rung.tier, one.rung.position): one for one in plan.assembly.skipped}
    ladder = {(one.tier, one.position): one for one in plan.state.rungs}
    rows = matrix(chain_of(plan.state.rungs), plan.health, reach, now=now)
    rungs = []
    for row in rows:
        rung = ladder[(row.tier, row.position)]
        left_out = skipped.get((row.tier, row.position))
        rungs.append(
            RungStateView(
                rung_id=rung.rung_id,
                tier=row.tier.value,
                position=row.position,
                role=row.role.value,
                deployment_id=row.deployment_id,
                provider=row.provider,
                model=row.model,
                enabled=rung.enabled,
                answers=left_out is None and rung.enabled,
                skipped_because=None if left_out is None else left_out.reason,
                told=None if left_out is None else left_out.told,
                state=row.state,
                measured=row.measured,
                unhealthy_because=(
                    None if row.unhealthy_because is None else row.unhealthy_because.value
                ),
                live_seen=row.live_seen,
                live_failed=row.live_failed,
            )
        )
    return ProvidersView(
        profile=normalised_profile(plan.profile),
        providers=providers,
        rungs=rungs,
        exhausted_tiers=[one.value for one in exhausted_tiers(rows)],
        editable=may_switch(reach, now),
        vault=None if vault is None else vault[0],
        vault_told=None if vault is None else VAULT_TOLD[vault[0]],
    )


def check_tier(plan: Planned, provider: str) -> Tier | None:
    """The cheapest tier holding an answering rung for this provider that is in rotation, or None.

    A rung taken out of rotation on the Routing screen stays in the answering chain so the chain
    skips it as disabled, and a check sent to a tier holding only such rungs would be refused by
    the chain and read as a resting breaker. So it is not a tier to check.
    """
    chain = plan.assembly.for_provider(provider)
    for tier in TIER_LADDER:
        if any(one.deployment.enabled for one in chain.rungs_for(tier)):
            return tier
    return None


# ------------------------------------------------------------------------- the wiring


def models_of(request: Request) -> ModelService:
    """The executor this process built, or a process-level fault identical for every caller."""
    found = getattr(request.app.state, "models", None)
    if not isinstance(found, ModelService):
        raise Failed("no model service on this process")
    return found


def _sessions(request: Request) -> async_sessionmaker[AsyncSession] | None:
    found = getattr(request.app.state, "db_sessions", None)
    return found if isinstance(found, async_sessionmaker) else None


async def _switches(request: Request) -> dict[str, tuple[bool, str, datetime]]:
    """Each switched provider's state, who switched it and when. Empty without a database."""
    factory = _sessions(request)
    if factory is None:
        return {}
    async with factory() as session:
        states = await switch_states(session)
    return {
        name: (state.value is True, state.updated_by, state.updated_at)
        for name, state in states.items()
        if isinstance(state.value, bool)
    }


async def _vault_for(
    request: Request, reach: EntitlementSet, now: datetime
) -> tuple[VaultState, dict[str, SlotView]] | None:
    """The vault's listing by provider, for a reader who may manage credentials, else None."""
    if not may_manage(reach, now):
        return None
    listed = await asyncio.to_thread(listing, credentials_of(request))
    by_provider = {slot.slot.rsplit("/", 1)[-1]: slot for slot in listed.slots}
    return listed.vault, by_provider


def _not_answerable() -> Absent:
    """The one refusal this router makes. Names the screen, never the caller or the grant."""
    return Absent(f"the {MODELS_SCREEN} screen's providers are not answerable for this caller")


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.credential_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _view(request: Request, asked: Asked, calls: ModelCalls) -> ProvidersView:
    plan = await calls.planned()
    return providers_view(
        plan,
        switches=await _switches(request),
        reach=asked.reach,
        now=asked.now,
        vault=await _vault_for(request, asked.reach, asked.now),
    )


router = APIRouter(prefix=API_PREFIX, tags=["models"])


@router.get("/models/providers", response_model=ProvidersView, responses=COMMON_RESPONSES)
async def providers(request: Request, asked: Asked) -> ProvidersView:
    """Every provider and every live rung, as the next call will see them."""
    if not may_read(asked.reach, asked.now):
        log.info("providers not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return await _view(request, asked, models_of(request).calls)


@router.put(
    "/models/providers/{provider}", response_model=ProvidersView, responses=COMMON_RESPONSES
)
async def switch(
    request: Request, provider: str, body: ProviderSwitchAsked, asked: Asked
) -> ProvidersView:
    """Switch one provider on or off, and answer with the plan the next call will make."""
    if not may_switch(asked.reach, asked.now):
        log.info("provider switch refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    if provider not in KNOWN_PROVIDERS:
        log.info("provider switch names no provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        await switch_provider(session, provider, on=body.on, by=asked.caller.principal.id)
        await session.commit()
    log.info(
        "provider switched", provider=provider, on=body.on, principal=asked.caller.principal.id
    )
    return await _view(request, asked, models_of(request).calls)


@router.post(
    "/models/providers/{provider}/check", response_model=CheckView, responses=COMMON_RESPONSES
)
async def check(request: Request, provider: str, asked: Asked) -> CheckView:
    """Send one fixed sentence through this provider's first answering rung, metered."""
    if not may_switch(asked.reach, asked.now):
        log.info("provider check refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    if provider not in KNOWN_PROVIDERS:
        log.info("provider check names no provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    calls = models_of(request).calls
    trace_id = _trace_id()
    origin = Origin(trace_id=trace_id, principal=asked.caller.principal, channel=asked.channel)
    meter = Meter()
    plan = await calls.planned()
    tier = check_tier(plan, provider)
    view = await _checked(calls, plan, provider, tier, meter=meter, trace_id=trace_id)
    recorders: tuple[RequestRecorder, ...] = tuple(
        one
        for one in getattr(request.app.state, "request_recorders", ())
        if isinstance(one, TelemetryRecorder)
    )
    await finish(
        recorders,
        Finished(
            origin=origin,
            at=asked.now,
            outcome=ModelCallOutcome(answered=view.answered),
            completed_at=datetime.now(UTC),
            entitlement_hash=asked.reach.ent_hash(),
            lane=Lane.ANSWER,
            tool_calls=0,
            model_usage=meter.usage(),
        ),
    )
    log.info(
        "provider checked",
        provider=provider,
        outcome=view.outcome,
        principal=asked.caller.principal.id,
    )
    return view


async def _checked(
    calls: ModelCalls,
    plan: Planned,
    provider: str,
    tier: Tier | None,
    *,
    meter: Meter,
    trace_id: str,
) -> CheckView:
    """The call and how it ended, in the check's vocabulary. Never raises a provider failure."""
    if tier is None:
        reasons = [one.reason for one in plan.assembly.skipped if one.rung.provider == provider]
        if reasons:
            return _unanswered(
                provider, reasons[0].value, TOLD[reasons[0]], status=None, trace_id=trace_id
            )
        named = any(one.provider == provider for one in plan.assembly.answering)
        outcome = "out_of_rotation" if named else "no_rung"
        return _unanswered(provider, outcome, CHECK_TOLD[outcome], status=None, trace_id=trace_id)
    try:
        response = await calls.complete(
            (DriverMessage(role=Role.USER, content=CHECK_PROMPT),),
            tier=tier,
            lane=Lane.ANSWER,
            meter=meter,
            trace_id=trace_id,
            max_output_tokens=CHECK_MAX_OUTPUT_TOKENS,
            provider=provider,
        )
    except ProviderUnavailable as failed:
        trigger = failed.failure.trigger
        outcome = "stopped" if trigger is None else trigger.value
        return _unanswered(
            provider, outcome, CHECK_TOLD[outcome], status=failed.failure.status, trace_id=trace_id
        )
    except NoCompliantRoute:
        # Every rung of this provider was resting behind an open breaker when the call planned.
        outcome = FallbackTrigger.CIRCUIT_OPEN.value
        return _unanswered(provider, outcome, CHECK_TOLD[outcome], status=None, trace_id=trace_id)
    return CheckView(
        provider=provider,
        answered=True,
        outcome="answered",
        told=CHECK_TOLD["answered"],
        served_by=response.deployment_id,
        model=response.model,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        status=None,
        trace_id=trace_id,
    )


def _unanswered(
    provider: str, outcome: str, told: str, *, status: int | None, trace_id: str
) -> CheckView:
    return CheckView(
        provider=provider,
        answered=False,
        outcome=outcome,
        told=told,
        served_by=None,
        model=None,
        tokens_in=None,
        tokens_out=None,
        status=status,
        trace_id=trace_id,
    )
