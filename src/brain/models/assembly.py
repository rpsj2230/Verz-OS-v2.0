"""Which rungs of the routing ladder can be called right now, and why each of the others cannot.

`ops.routing_rung` is the ladder an administrator edits on the Routing screen, and until this
module nothing turned it into anything that could be called: `brain.models.routing.seed_chain`
was the only `RoutingChain` any code built, and `driver.DriverRegistry` was constructed only in
tests. `assemble` is that step. It takes the live rungs, the install's model profile, which
providers an administrator has switched off, which keys this process holds and the drivers it
built at start, and returns the chain that can answer plus every rung that was left out, each
with a reason from a closed list.

**A rung that cannot be called is left out and says why, and it is never quietly kept.** A chain
listing a provider this process holds no key for is, in `seed_chain`'s own words, "a chain that
fails at the exact moment it is reached", and it fails as an authentication error on a person's
question. So a rung whose provider has no key, is switched off, is forbidden by a local profile,
or has no transport is removed before planning, and `Skipped` carries the reason in words an
administrator can act on. The Models and health screen draws the same `assemble` the executor
calls, so what the screen says will answer is what the next call tries. See
`A_RUNG_THAT_CANNOT_ANSWER_IS_LEFT_OUT_AND_SAYS_WHY`.

**The reasons are ordered, and the order is the order of consent.** The install's profile is the
decision to let text leave the client's hardware at all, so a hosted rung on a `local` install
is reported as that and nothing else. Then an administrator's switch. Then whether this product
can reach the provider, and last whether a key is held. A rung failing several of these is told
the first, because the later ones cannot be acted on until it is.

**Assembled on every call, from what is true at that moment, rather than once at start.** Three
of the five inputs change while a process runs: a rung's numbers are edited on the Routing
screen, a provider is switched off on the Models screen, and `brain.ops.credentials.Credentials.
put_to_use` hands a new key to this process. An assembly frozen at start would go on calling a
provider an administrator had just switched off, which is the one switch on this screen that
has to take effect immediately, because it is how an install stops sending text somewhere. The
drivers and their HTTP client are what is built at start, in `brain.ops.model_service`, and
assembling from them is a pure function over a few dozen rows.

**A rung promises the residency its provider's registry row documents, and no other.**
`ops.routing_rung` carries a deployment id, a provider and a model and no region. Since `0097`
the provider registry (`brain.models.registry`, M5.5.3) records where each provider processes, so
`assemble` gives a rung its provider's documented region and class. A provider with no row, or a
row that names no region, is `ResidencyClass.GLOBAL`, which `ResidencyRequirement.satisfied_by`
never accepts for a constrained scope. That is the direction that fails closed: a
residency-constrained request finds no compliant rung and is refused rather than sent somewhere
nobody documented. See `A_ROW_WITH_NO_REGION_PROMISES_NO_RESIDENCY`.

**The `local` profile is the default and anything unrecognised is read as it.** `brain.install`
declares `INSTALL_MODEL_PROFILE` with `local` as its default because "a client who has not chosen
to send text off their own hardware has not chosen it". A value that is neither of the two is
not a choice either, so it keeps text on the client's hardware.

Scope: pure. The rows, the switches, the keys and the drivers are parameters; nothing here opens
a connection, reads the environment or reads a clock.

Task ids: M27.8.8, M5.1.2, M5.5.3
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Final

from brain.models.driver import ModelDriver
from brain.models.registry import ProviderRecord
from brain.models.routing import (
    TIER_CONTEXT_WINDOW,
    Deployment,
    ResidencyClass,
    RoutingChain,
    RoutingRung,
    Tier,
)
from brain.models.wire import LOCAL_PROVIDER

# ------------------------------------------------------------------- written-down reasons

#: Why a rung that cannot be called is removed with a reason rather than kept.
A_RUNG_THAT_CANNOT_ANSWER_IS_LEFT_OUT_AND_SAYS_WHY: Final = (
    "A rung whose provider this process cannot call fails at the moment the chain reaches it, "
    "as an authentication error or a refused connection on somebody's question. So it is taken "
    "out before the chain is planned, and the reason it was taken out is carried beside it in "
    "words, so the screen that shows the ladder can say which rungs will answer and what to do "
    "about each one that will not."
)

#: Why a rung assembled from a row satisfies no residency constraint.
A_ROW_WITH_NO_REGION_PROMISES_NO_RESIDENCY: Final = (
    "ops.routing_rung records a deployment, a provider and a model, and no region. The region "
    "comes from the provider's row in the registry, and a provider nobody documented there is "
    "global, which no constrained scope accepts. A residency claim nobody wrote down is not one "
    "this system can make, so a regulated question is refused rather than routed to a location "
    "nobody documented."
)

#: What the install's model profile may be, as `brain.install` declares it.
LOCAL_PROFILE: Final = "local"
HOSTED_PROFILE: Final = "hosted"
MODEL_PROFILES: Final[tuple[str, ...]] = (LOCAL_PROFILE, HOSTED_PROFILE)

#: The region and class every assembled rung carries. See the reason constant above.
UNDOCUMENTED_REGION: Final = "global"


class RungSkip(enum.StrEnum):
    """Why a live rung is not in the chain that can answer. In the order they are judged."""

    #: A hosted provider on an install whose profile keeps text on its own hardware.
    LOCAL_PROFILE = "local_profile"
    #: An administrator switched this provider off on the Models screen.
    SWITCHED_OFF = "switched_off"
    #: This product has no transport for the provider the rung names.
    NO_TRANSPORT = "no_transport"
    #: The rung names the install's own inference server and no usable address is configured.
    NO_INFERENCE_SERVER = "no_inference_server"
    #: The provider needs a key and this process holds none.
    NO_KEY = "no_key"


#: What an administrator is told for each reason, in words that say what to do.
TOLD: Final[Mapping[RungSkip, str]] = MappingProxyType(
    {
        RungSkip.LOCAL_PROFILE: (
            "This install's model profile is local, so no question is sent to a hosted "
            "provider. Choose the hosted profile in the setup settings to allow it."
        ),
        RungSkip.SWITCHED_OFF: (
            "This provider is switched off on this screen, so nothing is sent to it. Switch it "
            "on to use this rung."
        ),
        RungSkip.NO_TRANSPORT: (
            "This product cannot call the provider this rung names. Point the rung at a "
            "provider listed on this screen."
        ),
        RungSkip.NO_INFERENCE_SERVER: (
            "This rung names the install's own inference server, and no usable address for it "
            "is configured. Set INSTALL_MODEL_ENDPOINT to the server's address."
        ),
        RungSkip.NO_KEY: (
            "No key for this provider is held by the server process that answered. Put one in "
            "on the credentials screen; other server processes pick it up within a minute."
        ),
    }
)


# ------------------------------------------------------------------------------ the rows


@dataclass(frozen=True)
class LadderRung:
    """One live row of `ops.routing_rung`, as assembly reads it.

    `rung_id` is carried so an attempt row can name the rung it tried, which is the join M5.3.4
    reconstructs a chain from.
    """

    rung_id: str
    tier: Tier
    position: int
    deployment_id: str
    provider: str
    model: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int
    enabled: bool
    #: Where the provider processes, from its registry row. Global when nobody documented it.
    region: str = UNDOCUMENTED_REGION
    residency_class: ResidencyClass = ResidencyClass.GLOBAL

    def routing_rung(self) -> RoutingRung:
        """The policy layer's rung, through its own checks. See `A_ROW_WITH_NO_REGION_...`."""
        return RoutingRung(
            tier=self.tier,
            position=self.position,
            model=self.model,
            deployment=Deployment(
                id=self.deployment_id,
                provider=self.provider,
                model=self.model,
                region=self.region,
                residency_class=self.residency_class,
                context_window=TIER_CONTEXT_WINDOW[self.tier],
                enabled=self.enabled,
            ),
            attempts=self.attempts,
            timeout_seconds=self.timeout_seconds,
            max_concurrency=self.max_concurrency,
        )


@dataclass(frozen=True)
class Skipped:
    """A live rung left out of the chain, and why."""

    rung: LadderRung
    reason: RungSkip

    @property
    def told(self) -> str:
        return TOLD[self.reason]


def is_hosted(provider: str) -> bool:
    """Whether a provider is outside the client's own hardware. Everything but the local server."""
    return provider != LOCAL_PROVIDER


def local_only(profile: str) -> bool:
    """Whether this profile keeps text on the client's hardware. Anything but `hosted` does."""
    return profile.strip() != HOSTED_PROFILE


def skip_reason(
    rung: LadderRung,
    *,
    profile: str,
    switched_off: frozenset[str],
    held: frozenset[str],
    drivers: Mapping[str, ModelDriver],
) -> RungSkip | None:
    """Why this rung cannot be called now, or None when it can. The first reason, in order.

    A disabled rung is not a skip here: `RoutingChain.select` already skips it as `DISABLED`,
    and it stays in the chain so the executed chain's positions are the edited ladder's.
    """
    hosted = is_hosted(rung.provider)
    if hosted and local_only(profile):
        return RungSkip.LOCAL_PROFILE
    if rung.provider in switched_off:
        return RungSkip.SWITCHED_OFF
    if rung.provider not in drivers:
        if hosted:
            return RungSkip.NO_TRANSPORT
        return RungSkip.NO_INFERENCE_SERVER
    if hosted and rung.provider not in held:
        return RungSkip.NO_KEY
    return None


@dataclass(frozen=True)
class Assembly:
    """The rungs that can be called, the drivers that call them, and every rung left out."""

    answering: tuple[LadderRung, ...]
    skipped: tuple[Skipped, ...]
    drivers: Mapping[str, ModelDriver]
    #: The provider rows this assembly read, by slug: their lane overrides and their terms.
    registry: Mapping[str, ProviderRecord] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def chain(self) -> RoutingChain:
        """The answering rungs as the policy layer's chain."""
        return RoutingChain(rungs=tuple(one.routing_rung() for one in self.answering))

    def for_provider(self, provider: str) -> RoutingChain:
        """The answering rungs of one provider only, for a check an administrator asked for."""
        return RoutingChain(
            rungs=tuple(one.routing_rung() for one in self.answering if one.provider == provider)
        )

    def rung(self, deployment_id: str, tier: Tier) -> LadderRung:
        """The ladder row behind a rung the chain selected. Never a row from another tier."""
        for one in self.answering:
            if one.deployment_id == deployment_id and one.tier is tier:
                return one
        msg = f"{deployment_id!r} is not an answering rung of tier {tier}"
        raise ValueError(msg)


def assemble(
    rungs: Iterable[LadderRung],
    *,
    profile: str,
    switched_off: frozenset[str],
    held: frozenset[str],
    drivers: Mapping[str, ModelDriver],
    registry: Mapping[str, ProviderRecord] | None = None,
) -> Assembly:
    """Split the live ladder into what can be called now and what cannot, in ladder order.

    `held` names providers, not environment variables, so nothing about where a key lives
    reaches this module. `drivers` is keyed by provider, as `DriverRegistry` is. `registry` is
    the provider rows by slug; a rung takes its provider's documented region from it.
    """
    documented = registry or {}
    answering: list[LadderRung] = []
    skipped: list[Skipped] = []
    for row in sorted(rungs, key=lambda r: (r.tier.value, r.position)):
        record = documented.get(row.provider)
        one = (
            row
            if record is None
            else replace(row, region=record.region, residency_class=record.residency_class)
        )
        reason = skip_reason(
            one, profile=profile, switched_off=switched_off, held=held, drivers=drivers
        )
        if reason is None:
            answering.append(one)
        else:
            skipped.append(Skipped(rung=one, reason=reason))
    return Assembly(
        answering=tuple(answering),
        skipped=tuple(skipped),
        drivers=MappingProxyType(dict(drivers)),
        registry=MappingProxyType(dict(documented)),
    )
