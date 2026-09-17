"""The routing ladder an install starts with, so its first question can reach a model.

`brain.models.calls.ModelCalls` walks `ops.routing_rung` on every call, and nothing wrote a rung:
there is no seed and no add-rung route, and the Routing screen edits four numbers of rows that
must already exist. So on a fresh install every call found no rung, the Models screen's check
answered "no rung names this provider", and the answer lane had a model step with nothing to
call. This module decides what the product writes there and when; `brain.ops.default_ladder_store`
writes it, into the same table the Routing screen edits, and `0059`'s trigger records each row
under the `routing` ledger action like any other rung.

**What the defaults are: one primary rung per tier the product routes to, for the one provider
setup chose.** `DEFAULT_TIERS` is `main`, which is where `classify_tier` puts every answer-lane
request, and `heavy`, which is where it puts the task lane and where an answer that overflows
`main` escalates. `small` is left empty for the reason `routing.seed_chain` gives: it earns a
rung when measurement shows traffic that keeps it cache-warm. Each rung's attempts, timeout and
concurrency are the primary rung of that tier in `seed_chain`, read from it rather than restated,
so the console's starting matrix and a fresh install's ladder are one set of numbers: `main` is
one attempt at twelve seconds, inside `ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS`, and `heavy` is two
at ninety, because nobody is watching a task. The install's own inference server answers one
request at a time, so its rungs carry a concurrency of one. See
`THE_DEFAULT_LADDER_IS_THE_SEEDS_PRIMARY_PER_TIER_FOR_THE_PROVIDER_SETUP_CHOSE`.

**Why no failover rung.** A second rung on the same provider is the same address and key tried
again, which `seed_chain` refuses on the answer lane as twelve more seconds for the same outcome;
a rung on a second provider is a provider nobody chose and whose key nobody kept, which
`seed_chain` calls a chain that fails at the moment it is reached. A failover is an
administrator's decision and belongs to them.

**The model names are the product's and they are stated, not discovered.** The Anthropic names
are `seed_chain`'s. The others are the providers' published names for the equivalent pair, and the
install's own server is asked for `LOCAL_COMPLETION_MODEL`, a name the product defines for the
completion task rather than a model it chose. **Two costs are stated rather than hidden.** A name
a provider retires stops its rung with a 4xx that the Models screen's check reports, and the
Routing screen cannot rename a rung (`brain.routing_routes` refuses the deployment fields until
M5.1's registry exists), so replacing one is a statement against the table. And
`brain.ops.inference.SERVED_MODELS` declares no completion task, so a local install's rung dials a
server that does not yet serve that name, and its check says so.

**When: only into a ladder nobody has held, and only once setup has chosen where text may go.**
Two refusals, and each has a failure behind it. A ladder with a live rung is an administrator's,
and a ladder whose rungs were all retired is one somebody emptied, which the ledger remembers and
the table's policy hides; refilling either at a start would undo a decision at the next restart,
which is `brain.identity.administration_reconciliation`'s argument about a revoked capability,
reached from the routing side. See `A_LADDER_SOMEBODY_HELD_IS_NEVER_REFILLED_BY_THE_PRODUCT`.
And before setup, an install's profile is the template's default rather than anybody's answer, so
a start that wrote a local ladder before the wizard ran would sit in front of the hosted provider
the wizard then chose, and every question would go to a server that does not answer. See
`NO_LADDER_IS_WRITTEN_BEFORE_SETUP_HAS_CHOSEN_WHERE_TEXT_MAY_GO`.

**Which provider.** From the wizard, the one it recorded, when the profile is `hosted` and its key
was kept, and the local server when the profile keeps text on the client's hardware. At a start,
the local server under a local profile, and under a hosted one the first provider in
`PROVIDER_SLOTS` order whose key this process holds, because a start has no wizard answer and a
held key is an administrator having chosen that provider.

Scope: pure. Nothing here opens a connection or reads a clock or the environment.

Task ids: M27.8.8, M5.3.1
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from brain.models.assembly import local_only
from brain.models.routing import (
    TIER_CONTEXT_WINDOW,
    Deployment,
    ResidencyClass,
    RoutingChain,
    RoutingRung,
    RungRole,
    Tier,
    seed_chain,
)
from brain.models.wire import LOCAL_PROVIDER
from brain.ops.provider_keys import PROVIDER_SLOTS

# ------------------------------------------------------------------- written-down reasons

#: What the product writes, and why those numbers and names.
THE_DEFAULT_LADDER_IS_THE_SEEDS_PRIMARY_PER_TIER_FOR_THE_PROVIDER_SETUP_CHOSE: Final = (
    "One primary rung in main, where every answer-lane request is routed, and one in heavy, "
    "where the task lane runs and an overflowing answer escalates, for the one provider setup "
    "chose. Attempts, timeout and concurrency are seed_chain's primary rung for that tier, so "
    "main fits the answer lane's wall-clock budget and heavy may retry because nobody is "
    "waiting; the local server answers one request at a time, so its rungs admit one. No "
    "failover: the same provider again is the same failure twice, and another provider is one "
    "nobody chose or kept a key for."
)

#: Why a ladder that ever held a rung is left alone.
A_LADDER_SOMEBODY_HELD_IS_NEVER_REFILLED_BY_THE_PRODUCT: Final = (
    "A live rung is an administrator's ladder, and a ladder whose rungs were all retired is one "
    "somebody emptied. The table's policy hides a retired rung from the application, and the "
    "ledger does not, so the product writes its defaults only when no rung is live and no "
    "routing entry was ever recorded. Refilling an emptied ladder at a start would put back, "
    "at every restart, a decision somebody took away."
)

#: Why a start writes nothing on an install nobody has set up.
NO_LADDER_IS_WRITTEN_BEFORE_SETUP_HAS_CHOSEN_WHERE_TEXT_MAY_GO: Final = (
    "Before the wizard, the model profile is the template's default rather than an answer, so a "
    "ladder written then is written for a provider nobody chose. Because a held ladder is never "
    "refilled, it would also stay in front of the provider the wizard then records, and every "
    "question would be sent to a server that does not answer. So a start writes defaults only "
    "on an install with an administrator, and the wizard writes them as it appoints one."
)

# ------------------------------------------------------------------------------ the figures

#: The tiers a default ladder fills, in the order they are written.
DEFAULT_TIERS: Final[tuple[Tier, ...]] = (Tier.MAIN, Tier.HEAVY)

#: The name the install's own inference server is asked for completion under. A task name the
#: product defines, not a model it chose: which weights answer is the install's, and a runtime
#: serving the chat completions shape is told which name to serve them as.
LOCAL_COMPLETION_MODEL: Final = "brain-completion"

#: How many requests the install's own server answers at once. `brain.ops.inference` derives the
#: same figure from its memory arithmetic, and a test holds the two equal; it is not imported,
#: because that module brings the embedding queue and the connectors with it.
LOCAL_CONCURRENCY: Final = 1


def _seed_models() -> Mapping[Tier, str]:
    chain = seed_chain()
    return {tier: chain.rungs_for(tier)[0].model for tier in DEFAULT_TIERS}


#: The model each provider's default rung names, per tier. Every key slot has an entry and so does
#: the install's own server, which a test holds, so the wizard cannot record a provider that has
#: no ladder to write.
DEFAULT_MODELS: Final[Mapping[str, Mapping[Tier, str]]] = MappingProxyType(
    {
        # `seed_chain`'s own names, read from it, so there is one copy.
        "anthropic": MappingProxyType(dict(_seed_models())),
        "openai": MappingProxyType({Tier.MAIN: "gpt-5-mini", Tier.HEAVY: "gpt-5"}),
        "moonshot": MappingProxyType(
            {Tier.MAIN: "kimi-k2-0905-preview", Tier.HEAVY: "kimi-k2-0905-preview"}
        ),
        LOCAL_PROVIDER: MappingProxyType(
            {Tier.MAIN: LOCAL_COMPLETION_MODEL, Tier.HEAVY: LOCAL_COMPLETION_MODEL}
        ),
    }
)


class LadderWritten(enum.StrEnum):
    """What asking for the defaults came to. Recorded in a log line, never shown to a person."""

    #: The defaults were written, one row per tier, each recorded by the routing trigger.
    WRITTEN = "written"
    #: A rung is live, so the ladder is somebody's.
    HELD = "held"
    #: No rung is live and the ledger records a routing change, so somebody emptied it.
    EMPTIED = "emptied"
    #: A start on an install with no administrator, so nobody has chosen a provider yet.
    NOT_SET_UP = "not_set_up"
    #: No provider could be named: a hosted profile with no key held, or none recorded.
    NO_PROVIDER = "no_provider"


@dataclass(frozen=True)
class DefaultRung:
    """One row the product writes into `ops.routing_rung`, with every column the table requires.

    `routing_rung` builds the policy layer's rung from it, so a default the chain would refuse is
    refused in a test rather than by the first call that plans from it.
    """

    tier: Tier
    deployment_id: str
    provider: str
    model: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int

    @property
    def position(self) -> int:
        """Every default is its tier's first rung: it is only ever written into an empty ladder."""
        return 0

    @property
    def role(self) -> RungRole:
        """What `RungRole` derives from a first position: the primary."""
        return RungRole.PRIMARY

    def routing_rung(self) -> RoutingRung:
        """The rung as the chain holds it, through `RoutingRung`'s own checks."""
        return RoutingRung(
            tier=self.tier,
            position=self.position,
            model=self.model,
            deployment=Deployment(
                id=self.deployment_id,
                provider=self.provider,
                model=self.model,
                region="global",
                residency_class=ResidencyClass.GLOBAL,
                context_window=TIER_CONTEXT_WINDOW[self.tier],
            ),
            attempts=self.attempts,
            timeout_seconds=self.timeout_seconds,
            max_concurrency=self.max_concurrency,
        )


def default_ladder(provider: str) -> tuple[DefaultRung, ...]:
    """The rungs the product writes for one provider. Refuses a provider it has no names for.

    Refusing rather than returning nothing, because an empty tuple written into an empty ladder is
    an install that answers nothing and says only that no rung names its provider.
    """
    models = DEFAULT_MODELS.get(provider)
    if models is None:
        msg = f"{provider!r} has no default ladder; these do: {list(DEFAULT_MODELS)}"
        raise ValueError(msg)
    seed = seed_chain()
    rungs: list[DefaultRung] = []
    for tier in DEFAULT_TIERS:
        primary = seed.rungs_for(tier)[0]
        rungs.append(
            DefaultRung(
                tier=tier,
                deployment_id=f"{provider}-{tier.value}",
                provider=provider,
                model=models[tier],
                attempts=primary.attempts,
                timeout_seconds=primary.timeout_seconds,
                max_concurrency=(
                    LOCAL_CONCURRENCY if provider == LOCAL_PROVIDER else primary.max_concurrency
                ),
            )
        )
    return tuple(rungs)


def default_chain(provider: str) -> RoutingChain:
    """The defaults as one chain, which is how the answer lane's budget is asked of them."""
    return RoutingChain(rungs=tuple(one.routing_rung() for one in default_ladder(provider)))


def provider_at_setup(profile: str, provider: str) -> str | None:
    """The provider the wizard's answers name: the local server, or the hosted provider recorded.

    Called after the key was kept, which is the only path on which the wizard appoints anybody
    with a hosted provider, so the key is not asked about here. A hosted profile naming a provider
    with no default ladder names none.
    """
    if local_only(profile):
        return LOCAL_PROVIDER
    return provider if provider in DEFAULT_MODELS else None


def provider_at_start(profile: str, held: Iterable[str]) -> str | None:
    """The provider a start writes defaults for: the local server, or the first held key's.

    First in `PROVIDER_SLOTS` order rather than in the order the keys were found, so two processes
    holding the same keys name the same provider.
    """
    if local_only(profile):
        return LOCAL_PROVIDER
    holding = frozenset(held)
    return next((one.slug for one in PROVIDER_SLOTS if one.slug in holding), None)


@runtime_checkable
class LadderWriter(Protocol):
    """Where the defaults for one provider are written, when the ladder has never been held."""

    async def write(self, provider: str, *, actor: str, trace_id: str) -> LadderWritten:
        """Write `default_ladder(provider)` into an unheld ladder, attributed to `actor`."""
        ...


async def reconcile(
    writer: LadderWriter,
    *,
    administrators: int,
    profile: str,
    held: Iterable[str],
    actor: str,
    trace_id: str,
) -> LadderWritten:
    """At a start: the defaults for this install's provider, once somebody has set it up.

    `administrators` is how many the install has, counted by the caller the way the wizard's door
    counts them, and none means nothing is written: see
    `NO_LADDER_IS_WRITTEN_BEFORE_SETUP_HAS_CHOSEN_WHERE_TEXT_MAY_GO`. `profile` and `held` are the
    install's model profile and the providers whose key this process holds, read by the caller,
    so this reads no environment. Whether the ladder was ever held is the writer's to find out,
    under its own lock.
    """
    if administrators < 1:
        return LadderWritten.NOT_SET_UP
    provider = provider_at_start(profile, held)
    if provider is None:
        return LadderWritten.NO_PROVIDER
    return await writer.write(provider, actor=actor, trace_id=trace_id)
