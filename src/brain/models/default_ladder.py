"""The routing ladder an install starts with, so its first question can reach a model.

`brain.models.calls.ModelCalls` walks `ops.routing_rung` on every call, and nothing wrote a rung:
there is no seed and no add-rung route, and the Routing screen edits four numbers of rows that
must already exist. So on a fresh install every call found no rung, the Models screen's check
answered "no rung names this provider", and the answer lane had a model step with nothing to
call. This module decides what the product writes there and when; `brain.ops.default_ladder_store`
writes it, into the same table the Routing screen edits, and `0059`'s trigger records each row
under the `routing` ledger action like any other rung.

**When setup chose Anthropic, the default is the owner's failover matrix** (drawn on 2026-09-03,
restated on 2026-09-29, `OWNERS_MATRIX`): Simple, Medium and Complex each try three Anthropic
models and then one Moonshot model, twelve steps in all. It is the design of record for the Models
screen, and it overrules the argument this module made until 2026-09-29, that a failover is an
administrator's decision and the product should write none. That argument had two halves and
neither survives the code as it now stands. **"The same provider again is the same failure
twice"** was true of `seed_chain`'s failover, which is the same model in another region; the
owner's failovers are different models, which fail differently (one is overloaded while another
answers). **"Another provider is one nobody chose or kept a key for"** was true before
`brain.models.assembly`: a Moonshot step on an install holding no Moonshot key is now left out
before the chain is planned, marked "no key" on the Models screen, and never reached, so it costs
the person asking nothing and starts answering the moment the key is saved. See
`THE_DEFAULT_LADDER_IS_THE_OWNERS_FAILOVER_MATRIX`.

**Every other provider's default is still one primary step in Medium and one in Complex**, the
tiers `classify_tier` routes the answer lane and the task lane to. The owner drew a matrix for
Anthropic and Moonshot; a failover onto a provider an OpenAI, DeepSeek or local install never
chose is a decision nobody has made for them. See
`ANOTHER_PROVIDERS_DEFAULT_IS_ONE_PRIMARY_PER_TIER`.

**The numbers.** Each tier's first step is `seed_chain`'s primary for that tier, read from it
rather than restated: Medium one attempt at twelve seconds, Complex two at ninety because nobody
is watching a task. Simple has no seed row and a person waits on it as on Medium, so it takes
Medium's. A failover on Complex is `seed_chain`'s own Complex failover. **A failover on a tier a
person waits on is one attempt at four seconds**, because the answer lane's wall clock
(`ANSWER_LANE_WALL_CLOCK_BUDGET_SECONDS`, 25) bounds the whole walk and the call path enforces no
deadline of its own: twelve for the first step and four for each of the three after it is 24,
inside the budget, and `check_answer_lane_budget` holds it. Rejected: a deadline inside the walk,
which would let a failover reached after a fast failure use the whole remainder; it is the better
behaviour and a change to the executor every call goes through, and the four seconds need no
change there. See `A_WAITED_ON_WALK_FITS_THE_ANSWER_BUDGET`. The install's own inference server
answers one request at a time, so its steps carry a concurrency of one.

**The model names are the product's and they are stated, not discovered.** The Anthropic primaries
of Medium and Complex are `seed_chain`'s, and a test holds the owner's matrix to them. The rest
are the owner's names and the providers' published names for the equivalent pair, and the
install's own server is asked for `LOCAL_COMPLETION_MODEL`, a name the product defines for the
completion task rather than a model it chose. **Two costs are stated rather than hidden.** A name
a provider retires or refuses stops its step with a 4xx that the Models screen's Test reports,
and the Routing screen cannot rename a step, so replacing one is a retirement and an addition.
And `brain.ops.inference.SERVED_MODELS` declares no completion task, so a local install's step
dials a server that does not yet serve that name, and its check says so.

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

**One exception, and it is the product's own rows: an earlier default nobody touched is
completed.** An install set up before 2026-09-29 holds `earlier_default`, one primary in Medium
and one in Complex. When its live ladder is exactly those rows and no routing change was ever
applied, the ladder is still what the product wrote, so a start adds the steps the default has
since gained (`completion`). A held change changed nothing and does not count; an edited,
reordered, emptied or extended ladder is somebody's and is left alone. Rejected: a migration
inserting the rows, which is data in a schema change and cannot ask whether the install chose
Anthropic. See `AN_UNTOUCHED_EARLIER_DEFAULT_IS_COMPLETED_ONCE`.

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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
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

#: What the product writes when setup chose Anthropic, and why.
THE_DEFAULT_LADDER_IS_THE_OWNERS_FAILOVER_MATRIX: Final = (
    "When setup chose Anthropic, the default is the failover matrix the owner drew on 2026-09-03 "
    "and restated on 2026-09-29: Simple, Medium and Complex each try three Anthropic models and "
    "then one Moonshot model. The failovers are different models, which fail differently, and a "
    "Moonshot step on an install holding no Moonshot key is left out before the chain is planned "
    "and marked no key, so it costs the person asking nothing and answers once the key is saved."
)

#: Why every other provider's default is one primary step in each tier a lane routes to.
ANOTHER_PROVIDERS_DEFAULT_IS_ONE_PRIMARY_PER_TIER: Final = (
    "The owner drew a matrix for Anthropic and Moonshot. For any other provider setup chose, the "
    "default is one primary step in Medium, where every answer-lane request is routed, and one in "
    "Complex, where the task lane runs and an overflowing answer escalates. A failover onto a "
    "provider that install never chose is a decision nobody has made for it."
)

#: Why a failover on a tier somebody waits on is given four seconds.
A_WAITED_ON_WALK_FITS_THE_ANSWER_BUDGET: Final = (
    "A person waits on Simple and Medium, and the answer lane's wall-clock budget bounds the "
    "whole walk, not each step, because the call path has no deadline of its own. The first step "
    "keeps the seed's twelve seconds so a legitimately slow question is not cut off, and each of "
    "the three failovers gets one attempt at four seconds, which is 24 seconds in all. A failover "
    "is mostly reached after a fast failure, a refused connection or an overloaded provider."
)

#: Why a ladder that ever held a rung is left alone.
A_LADDER_SOMEBODY_HELD_IS_NEVER_REFILLED_BY_THE_PRODUCT: Final = (
    "A live rung is an administrator's ladder, and a ladder whose rungs were all retired is one "
    "somebody emptied. The table's policy hides a retired rung from the application, and the "
    "ledger does not, so the product writes its defaults only when no rung is live and no "
    "routing entry was ever recorded. Refilling an emptied ladder at a start would put back, "
    "at every restart, a decision somebody took away."
)

#: The one ladder with live rows the product still writes into, and why it is still the product's.
AN_UNTOUCHED_EARLIER_DEFAULT_IS_COMPLETED_ONCE: Final = (
    "A live ladder that is exactly the rows the product wrote before its default became the "
    "owner's matrix, on an install where no routing change was ever applied, is the product's "
    "own and nobody's decision, so a start adds the steps the default has since gained. A held "
    "change changed nothing and does not count. Anything else live is somebody's ladder and is "
    "left alone, and once completed the ladder is the default and the next start adds nothing."
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

#: The tiers every provider's default has a primary step in, in the order they are written.
DEFAULT_TIERS: Final[tuple[Tier, ...]] = (Tier.MAIN, Tier.HEAVY)

#: The provider whose default is the owner's matrix.
MATRIX_PROVIDER: Final = "anthropic"

#: The owner's failover matrix (2026-09-03, restated 2026-09-29): per level, each step's provider
#: and model in the order a question tries them. Written as he drew it; a test holds the Medium and
#: Complex primaries to `seed_chain`'s models, so the two cannot drift.
OWNERS_MATRIX: Final[Mapping[Tier, tuple[tuple[str, str], ...]]] = MappingProxyType(
    {
        Tier.SMALL: (
            ("anthropic", "claude-haiku-4-5"),
            ("anthropic", "claude-sonnet-5"),
            ("anthropic", "claude-opus-5"),
            ("moonshot", "kimi-k2.6"),
        ),
        Tier.MAIN: (
            ("anthropic", "claude-sonnet-5"),
            ("anthropic", "claude-opus-5"),
            ("anthropic", "claude-haiku-4-5"),
            ("moonshot", "kimi-k3"),
        ),
        Tier.HEAVY: (
            ("anthropic", "claude-opus-5"),
            ("anthropic", "claude-sonnet-5"),
            ("anthropic", "claude-haiku-4-5"),
            ("moonshot", "kimi-k3"),
        ),
    }
)

#: The tiers a person waits on: the answer lane's and the one below it. Their walks fit the budget.
WAITED_ON: Final[frozenset[Tier]] = frozenset({Tier.SMALL, Tier.MAIN})

#: One failover step's time on a tier a person waits on. See `A_WAITED_ON_WALK_FITS_THE_...`.
WAITED_ON_FAILOVER_TIMEOUT_SECONDS: Final = 4.0

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


#: The model each provider's primary step names, per tier every default fills. Every key slot has
#: an entry and so does the install's own server, which a test holds, so the wizard cannot record
#: a provider that has no ladder to write.
DEFAULT_MODELS: Final[Mapping[str, Mapping[Tier, str]]] = MappingProxyType(
    {
        # `seed_chain`'s own names, read from it, so there is one copy.
        "anthropic": MappingProxyType(dict(_seed_models())),
        "openai": MappingProxyType({Tier.MAIN: "gpt-5-mini", Tier.HEAVY: "gpt-5"}),
        "moonshot": MappingProxyType(
            {Tier.MAIN: "kimi-k2-0905-preview", Tier.HEAVY: "kimi-k2-0905-preview"}
        ),
        # DeepSeek's two OpenAI-compatible names: the chat model and the reasoning one (M5.7.1).
        "deepseek": MappingProxyType({Tier.MAIN: "deepseek-chat", Tier.HEAVY: "deepseek-reasoner"}),
        LOCAL_PROVIDER: MappingProxyType(
            {Tier.MAIN: LOCAL_COMPLETION_MODEL, Tier.HEAVY: LOCAL_COMPLETION_MODEL}
        ),
    }
)


def _levels(provider: str) -> Mapping[Tier, tuple[tuple[str, str], ...]]:
    """Each level's steps for one provider's default: the owner's matrix, or one primary each."""
    if provider == MATRIX_PROVIDER:
        return OWNERS_MATRIX
    models = DEFAULT_MODELS[provider]
    return {tier: ((provider, models[tier]),) for tier in DEFAULT_TIERS}


class LadderWritten(enum.StrEnum):
    """What asking for the defaults came to. Recorded in a log line, never shown to a person."""

    #: The defaults were written, one row per step, each recorded by the routing trigger.
    WRITTEN = "written"
    #: The live ladder was the product's earlier default, untouched, and the missing steps were
    #: added. See `AN_UNTOUCHED_EARLIER_DEFAULT_IS_COMPLETED_ONCE`.
    COMPLETED = "completed"
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
    refused in a test rather than by the first call that plans from it. `role` is what
    `RoutingChain.role_of` derives for the step in its default ladder, which is what `0097`'s
    trigger writes over whatever is sent.
    """

    tier: Tier
    deployment_id: str
    provider: str
    model: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int
    position: int = 0
    role: RungRole = RungRole.PRIMARY

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
    an install that answers nothing and says only that no rung names its provider. Each step's
    role is derived by `RoutingChain.role_of` over the whole default, the one derivation there is.
    """
    if provider not in DEFAULT_MODELS:
        msg = f"{provider!r} has no default ladder; these do: {list(DEFAULT_MODELS)}"
        raise ValueError(msg)
    steps = tuple(
        default_step(one, tier, position, model)
        for tier, level in _levels(provider).items()
        for position, (one, model) in enumerate(level)
    )
    chain = RoutingChain(rungs=tuple(step.routing_rung() for step in steps))
    return tuple(replace(step, role=chain.role_of(step.routing_rung())) for step in steps)


def default_step(provider: str, tier: Tier, position: int, model: str) -> DefaultRung:
    """One default row at `position` of `tier`, naming `provider` and `model`, with its numbers.

    The first step of a tier is `seed_chain`'s primary for it (Simple takes Medium's, having no
    seed row) and names its deployment by provider and tier, as the product always has. A later
    one is a failover: four seconds and one attempt on a tier a person waits on, `seed_chain`'s
    own failover numbers otherwise, and its deployment named by provider and model, which is how
    `brain.ops.matrix_gate.RungAddition` names a step added on the Routing screen.
    """
    seeded = seed_chain().rungs_for(tier if tier in DEFAULT_TIERS else Tier.MAIN)
    if position == 0:
        numbers = seeded[0]
        attempts, timeout, concurrency = (
            numbers.attempts,
            numbers.timeout_seconds,
            numbers.max_concurrency,
        )
        deployment = f"{provider}-{tier.value}"
    else:
        numbers = seeded[1]
        attempts, timeout, concurrency = (
            (1, WAITED_ON_FAILOVER_TIMEOUT_SECONDS, numbers.max_concurrency)
            if tier in WAITED_ON
            else (numbers.attempts, numbers.timeout_seconds, numbers.max_concurrency)
        )
        deployment = f"{provider}-{model}"[:120]
    return DefaultRung(
        tier=tier,
        deployment_id=deployment,
        provider=provider,
        model=model,
        attempts=attempts,
        timeout_seconds=timeout,
        max_concurrency=LOCAL_CONCURRENCY if provider == LOCAL_PROVIDER else concurrency,
        position=position,
    )


def default_rung(provider: str, tier: Tier, model: str) -> DefaultRung:
    """One primary default row: `seed_chain`'s primary numbers for `tier`, naming `provider` and
    `model`.

    Split out of `default_ladder` on 2026-09-28 so the Models screen's provider check can send
    through a provider no step names yet with exactly the numbers a default step would carry
    (`brain.provider_routes.unladdered_rung`), rather than a third set of numbers for one call.
    """
    return default_step(provider, tier, 0, model)


def earlier_default(provider: str) -> tuple[DefaultRung, ...]:
    """The ladder the product wrote until 2026-09-29: one primary in Medium and one in Complex.

    For every provider but Anthropic this is still the whole default. Kept so a start can tell an
    earlier default nobody touched from a ladder somebody chose. See
    `AN_UNTOUCHED_EARLIER_DEFAULT_IS_COMPLETED_ONCE`.
    """
    models = DEFAULT_MODELS.get(provider)
    if models is None:
        msg = f"{provider!r} has no default ladder; these do: {list(DEFAULT_MODELS)}"
        raise ValueError(msg)
    return tuple(default_rung(provider, tier, models[tier]) for tier in DEFAULT_TIERS)


@dataclass(frozen=True)
class WrittenStep:
    """One live row of `ops.routing_rung`, as the completion compares it with a default's.

    Every column the product writes except the role, which the trigger derives and which a move
    changes without anybody choosing it. `everywhere` is whether its scope narrows nothing, which
    is the scope the product writes.
    """

    tier: Tier
    position: int
    deployment_id: str
    provider: str
    model: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int
    enabled: bool
    everywhere: bool

    @classmethod
    def of(cls, step: DefaultRung) -> WrittenStep:
        """A default row as the product writes it: in use, and applying to every question."""
        return cls(
            tier=step.tier,
            position=step.position,
            deployment_id=step.deployment_id,
            provider=step.provider,
            model=step.model,
            attempts=step.attempts,
            timeout_seconds=float(step.timeout_seconds),
            max_concurrency=step.max_concurrency,
            enabled=True,
            everywhere=True,
        )


def completion(provider: str, live: Iterable[WrittenStep]) -> tuple[DefaultRung, ...]:
    """The steps that make an untouched earlier default today's default, or none.

    None unless the live rows are exactly `earlier_default(provider)`, every column the product
    wrote, and nothing else. Whether a change was ever applied is the caller's to ask, under its
    lock, because it is a read of the table rather than of these rows.
    """
    earlier = earlier_default(provider)
    if frozenset(live) != frozenset(WrittenStep.of(one) for one in earlier):
        return ()
    held = {(one.tier, one.position) for one in earlier}
    return tuple(one for one in default_ladder(provider) if (one.tier, one.position) not in held)


def default_model(provider: str, registered: Sequence[str] = ()) -> str | None:
    """The model a provider is checked with when no step names it, or None when there is none.

    The product's own name for its first default level where it has one (`DEFAULT_MODELS`), and
    otherwise the first model the provider's registry row lists, which is how a provider added
    from the console names its models. None for a provider with neither, because a check sent to
    a model nobody named would test a guess.
    """
    known = DEFAULT_MODELS.get(provider)
    if known is not None:
        return known[DEFAULT_TIERS[0]]
    return next((one for one in registered if one.strip()), None)


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
        """Write `default_ladder(provider)` into an unheld ladder, attributed to `actor`, or
        complete an untouched earlier default."""
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
    so this reads no environment. Whether the ladder was ever held, or is an earlier default
    nobody touched, is the writer's to find out, under its own lock.
    """
    if administrators < 1:
        return LadderWritten.NOT_SET_UP
    provider = provider_at_start(profile, held)
    if provider is None:
        return LadderWritten.NO_PROVIDER
    return await writer.write(provider, actor=actor, trace_id=trace_id)
