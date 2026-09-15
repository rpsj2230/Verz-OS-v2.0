"""The plan, narrowed by what the caller holds and by how far the agent is trusted, then sealed.

M19.2.2 says "plan intersected with capabilities and skill ceiling", and the word intersected
is doing something specific that is worth being careful about. **Nothing here intersects two
entitlement sets.** `EntitlementSet.intersect` is the single implementation of the platform's
central rule, `tests/invariants/test_single_implementation.py` pins every call site of it by
name, and a browsing module computing a reach would be a new place that rule is applied by
somebody who was thinking about browsers at the time.

What happens instead is narrower and is the right operation for this layer. The run reach has
already been computed, by `brain.gate.leash.decide` or `brain.ops.automation.flow_reach`, and
arrives here as a value. Compilation asks that value a question per step, through
`EntitlementSet.holds`, and drops the steps it does not admit. So the intersection is with the
*plan*, not with another reach, and it is expressed as a filter because a filter can only ever
remove. `compilation_only_removes` states that as a property and a test asserts it rather than
trusting the reading.

**The skill ceiling narrows a second time, and only in the same direction.** It arrives as an
`AutonomyTier` and is composed with the side effect of each verb through
`brain.tools.registry.rung_ceiling`, which is `min` and cannot loosen anything. A write step
under a SHADOW ceiling does not survive.

**A SHADOW write is dropped rather than admitted as simulated, and that is a real decision.**
`brain.gate.leash` runs a shadow action by rendering the artefact and returning it marked
simulated, which is the right behaviour where there is something to simulate. There is no
browser in this repository and therefore no simulator, so admitting a step on the promise that
it would be simulated would be a claim nothing implements. It is dropped, the record says why,
and the day a runner exists this is the paragraph to come back to.

**The write budget is the plan's own count and not a configured number.** A run gets exactly as
many of each write verb as it planned, so a loop that clicks twice where the plan clicked once
is refused by arithmetic rather than by a heuristic about loops. A separate configured budget
would be a second number to keep in agreement with the plan, and the two would disagree the
first time somebody edited one.

**Naming a dropped step back to the caller discloses nothing.** DENIED and ABSENT must be
indistinguishable, and this looks at first like a place that breaks it. It is not: the caller
named these surfaces themselves in their own request, against a registry they can already
read, so being told that their own step did not survive their own reach adds no fact they did
not have. What is never said is which capability was missing, because that names a permission
the caller does not hold.

**A signed surface exception is compiled in and sealed, and nothing else about autonomy is.**
`unattended` holds the write steps a live `brain.browsing.autonomy.SurfaceException` lets run
without envelope approval, decided here once from the exceptions and the instant the caller
passes. It is in the digest, so an approval raised for an envelope that waited for a person does
not match one compiled after somebody signed an exception, and the reverse.

**The digest is a function beside the type rather than only a method on it.** A stored envelope
is re-read in `brain.browsing.envelope_store` without the plan it was compiled from, and it has
to re-derive the same fingerprint to notice a row edited after it was sealed. Two copies of the
digest would be two answers to what was sealed, so `seal` is the one and `Envelope.digest` calls
it.

Task ids: M19.2.2
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, assert_never

from brain.browsing.autonomy import SurfaceException, runs_unattended
from brain.browsing.planning import Plan, Step
from brain.browsing.targets import Target, Verb, is_write
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import SideEffect
from brain.gate.injection import AutonomyTier
from brain.tools.registry import rung_ceiling

#: What the digest is over. Versioned in the same shape `brain.gate.leash.DIGEST_SCHEMA` is,
#: so that a change to what is sealed invalidates every previous digest loudly rather than
#: producing the same string for a different meaning.
DIGEST_SCHEMA: Final = "brain.browsing.envelope.v2"

#: Why this module filters a plan rather than intersecting a reach.
COMPILATION_ONLY_REMOVES: Final = (
    "An envelope is the plan minus what the caller may not do and minus what the agent is "
    "not trusted to do. Written as a filter over steps, the narrowing is structural: there "
    "is no branch that could add one, so no reading of this function admits a step the plan "
    "did not contain. Written as an intersection of two reaches it would be a second call "
    "site of the platform's central rule, which is pinned by name in the invariant suite "
    "precisely so that a module thinking about browsers does not become one."
)

#: Why a shadow write is dropped rather than carried as simulated.
THERE_IS_NO_SIMULATOR_SO_THERE_IS_NO_SIMULATED_STEP: Final = (
    "brain.gate.leash simulates by rendering the artefact an action would have produced. A "
    "browser action's artefact is a page interaction and there is no browser here to render "
    "one. Admitting a step as simulated would put a state in the envelope that nothing can "
    "reach, which reads to every later author as a supported mode. Dropped, with the reason "
    "recorded, until something can actually simulate it."
)

#: Why the budget is counted from the plan.
A_SECOND_BUDGET_IS_A_SECOND_NUMBER_TO_KEEP_IN_AGREEMENT: Final = (
    "The number of writes a run may perform is already stated, once, by the plan somebody "
    "approved. Configuring it separately creates two figures that must match, no mechanism "
    "that makes them match, and a failure mode where the looser one wins because it is the "
    "one the enforcer happens to read."
)


class EnvelopeError(Exception):
    """A plan could not be compiled into a contract anything could enforce."""


def side_effect_of(verb: Verb) -> SideEffect:
    """What one verb does to the world, in the vocabulary the leash already speaks.

    Exhaustive by `match` and `assert_never`, in the shape `brain.ops.admission.kind_of`
    uses: a seventh verb cannot reach production without somebody deciding how far its
    mistake travels. A dictionary with a default would classify it as whatever the default
    was, and the only safe default is the strictest one, which nobody chooses.

    `UPLOAD` is SEND rather than WRITE because a document leaves the building. The two behave
    identically under `brain.tools.registry.default_rung`, so this changes nothing today; it
    is stated correctly because `max_side_effect` on an agent ceiling reads it.
    """
    match verb:
        case Verb.OPEN | Verb.READ:
            return SideEffect.NONE
        case Verb.CLICK | Verb.TYPE | Verb.SUBMIT:
            return SideEffect.WRITE
        case Verb.UPLOAD:
            return SideEffect.SEND
        case _:  # pragma: no cover - exhaustive, and the compiler proves it
            assert_never(verb)


def tier_for(verb: Verb, ceiling: AutonomyTier) -> AutonomyTier:
    """The rung this verb runs at under this ceiling. Never above either input.

    Delegates to `brain.tools.registry.rung_ceiling`, which is `min`. Written as a call
    rather than as `min(...)` here so there is one composition rule for autonomy in the
    repository and this module is a caller of it rather than a second author of it.
    """
    return rung_ceiling(ceiling, side_effect_of(verb))


@dataclass(frozen=True)
class Dropped:
    """One step that did not survive, and which of the two narrowings removed it.

    The reason names the narrowing and never the capability. A caller told "you lack
    `write:invoice.status`" has been handed the name of a permission somebody else holds,
    which is the disclosure `brain.ops.denial_alerts` exists to avoid making.
    """

    surface: str
    verb: Verb
    reason: str


@dataclass(frozen=True)
class Envelope:
    """The sealed contract for one run: what may be done, where, and how many times.

    Frozen, and every field is a value type. This is the object a policy is compiled from at
    container start, so anything mutable on it would be a way for the run to change the
    terms it is running under, which is the failure M19.3.1 names.
    """

    run_id: str
    plan: Plan
    #: The origins any action in this run may touch, taken from the target and not from the
    #: surfaces, so a surface cannot widen the allowlist by existing.
    origins: frozenset[str]
    steps: tuple[Step, ...]
    #: How many of each write verb this run may perform, counted from `steps`.
    budget: tuple[tuple[Verb, int], ...]
    #: The rung each admitted verb runs at, after the ceiling and the side effect compose.
    tiers: tuple[tuple[Verb, AutonomyTier], ...]
    dropped: tuple[Dropped, ...] = ()
    #: Write steps a signed surface exception lets run without envelope approval, as surface
    #: and verb pairs. Empty unless an exception was live at compilation. See
    #: `brain.browsing.autonomy`.
    unattended: tuple[tuple[str, Verb], ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            msg = "an envelope belonging to no run cannot be matched to a policy or a snapshot"
            raise EnvelopeError(msg)
        if not self.origins:
            msg = (
                f"envelope for run {self.run_id!r} allows no origin, so either every action "
                "is refused or an empty set is later read as no restriction"
            )
            raise EnvelopeError(msg)
        for verb, count in self.budget:
            if count < 1:
                msg = (
                    f"envelope for run {self.run_id!r} budgets {count} of {verb.value}; a "
                    "zero budget is the absence of the verb and must not be a row saying it "
                    "is allowed"
                )
                raise EnvelopeError(msg)
        for surface, verb in self.unattended:
            if not is_write(verb) or not self.admits(surface, verb):
                msg = (
                    f"envelope for run {self.run_id!r} lets {verb.value} on {surface!r} run "
                    "unattended, which is not a write step it admits; the set means writes "
                    "nobody approved and anything else in it would read as one"
                )
                raise EnvelopeError(msg)

    def allowance(self, verb: Verb) -> int:
        """How many times this verb may be used. Zero for anything not budgeted."""
        for budgeted, count in self.budget:
            if budgeted == verb:
                return count
        return 0

    def admits(self, surface: str, verb: Verb) -> bool:
        return any(step.surface == surface and step.verb == verb for step in self.steps)

    def awaits_approval(self) -> bool:
        """Whether any write in this envelope waits for a person before the run starts.

        A write compiled to run unattended does not; every other write does. An envelope with
        no write at all does not either, and raising an approval for one would put a card in
        front of a person asking them to approve reading.
        """
        return any(
            step.is_write() and (step.surface, step.verb) not in self.unattended
            for step in self.steps
        )

    def tier(self, verb: Verb) -> AutonomyTier:
        """The rung this verb runs at, or SHADOW for one that is not in the envelope.

        SHADOW rather than a raise, because this is asked on the enforcement path about a
        verb an untrusted container named, and the safe answer to a verb nobody compiled is
        the most supervised one rather than an exception the caller might catch.
        """
        for named, tier in self.tiers:
            if named == verb:
                return tier
        return AutonomyTier.SHADOW

    def digest(self) -> str:
        """A stable fingerprint of everything this envelope permits.

        Derived rather than stored, so it cannot be set to something the fields do not say.
        Covers the run, the origins, every admitted step and every budget line, because the
        thing being detected is a policy inside a container claiming to have been compiled
        from an envelope that permits more than the sealed one does.

        Deliberately does not cover `dropped`. What was refused is a record for a person and
        changing it changes nothing about what the run may do, so including it would void a
        policy for a reason that is not a difference in permissions.
        """
        return seal(
            run_id=self.run_id,
            origins=self.origins,
            steps=((step.surface, step.verb) for step in self.steps),
            budget=self.budget,
            tiers=self.tiers,
            unattended=self.unattended,
        )


def seal(
    *,
    run_id: str,
    origins: Iterable[str],
    steps: Iterable[tuple[str, Verb]],
    budget: Iterable[tuple[Verb, int]],
    tiers: Iterable[tuple[Verb, AutonomyTier]],
    unattended: Iterable[tuple[str, Verb]],
) -> str:
    """The fingerprint of what an envelope permits, from the permitted parts alone.

    The one statement of the digest. `Envelope.digest` calls it and so does a stored envelope
    re-reading its row, which has no plan to rebuild an `Envelope` from and must still arrive
    at the same string. Steps keep their order, because the order is part of what was
    approved; origins and the unattended set are sets and are sorted.
    """
    parts = [
        DIGEST_SCHEMA,
        run_id,
        "|".join(sorted(origins)),
        "|".join(f"{surface}:{verb.value}" for surface, verb in steps),
        "|".join(f"{verb.value}={count}" for verb, count in budget),
        "|".join(f"{verb.value}@{tier.value}" for verb, tier in tiers),
        "|".join(sorted(f"{surface}:{verb.value}" for surface, verb in unattended)),
    ]
    joined = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def compile_envelope(
    plan: Plan,
    target: Target,
    *,
    run_id: str,
    reach: EntitlementSet,
    ceiling: AutonomyTier,
    exceptions: Sequence[SurfaceException] = (),
    now: datetime | None = None,
) -> Envelope:
    """Narrow a plan to what this caller may do and this agent is trusted to do.

    Two filters, both removing, applied in an order that matters for the record rather than
    for the result. Capability first, because a step the caller cannot reach at all is not
    interestingly a question about how supervised the agent is, and reporting it as a rung
    problem would send whoever is reading the record to the wrong screen.

    `reach` is the run reach, already computed by the gate. This function does not compute
    one and must not: see `COMPILATION_ONLY_REMOVES`.

    **There is no check on `run_id` here and there used to be.** `Envelope.__post_init__`
    already refuses one that names no run, so the check in this function was a second
    statement of the same rule that could only ever raise at the same point in the same call,
    and mutating it away changed nothing any test could see. A second copy of a rule is a
    second place for it to be wrong, and the wrong copy is the one somebody edits, so it is
    the copy that is gone rather than the property.

    `exceptions` are signed surface exceptions and `now` is the instant they are judged at.
    Exceptions with no instant are refused rather than judged at the process clock, for the
    reason CLAUDE.md records about `intersect`: an expiry decided at the wrong moment fails
    permissive.
    """
    if exceptions and now is None:
        msg = (
            f"run {run_id!r} was compiled with surface exceptions and no instant to judge "
            "their expiry at"
        )
        raise EnvelopeError(msg)
    kept: list[Step] = []
    dropped: list[Dropped] = []
    for step in plan.steps:
        surface = target.surface(step.surface)
        if surface is None:
            dropped.append(
                Dropped(
                    surface=step.surface,
                    verb=step.verb,
                    reason="the target does not declare this surface",
                )
            )
            continue
        if not surface.admits(step.verb):
            dropped.append(
                Dropped(
                    surface=step.surface,
                    verb=step.verb,
                    reason="the surface does not declare this verb",
                )
            )
            continue
        if not reach.holds(surface.capability):
            dropped.append(
                Dropped(
                    surface=step.surface,
                    verb=step.verb,
                    reason="this run's reach does not admit this surface",
                )
            )
            continue
        if is_write(step.verb) and tier_for(step.verb, ceiling) < AutonomyTier.ASSISTED:
            dropped.append(
                Dropped(
                    surface=step.surface,
                    verb=step.verb,
                    reason=(
                        "the agent's ceiling leaves this write at shadow, and nothing "
                        "here simulates one"
                    ),
                )
            )
            continue
        kept.append(step)

    counts: dict[Verb, int] = {}
    for step in kept:
        if is_write(step.verb):
            counts[step.verb] = counts.get(step.verb, 0) + 1
    budget = tuple(sorted(counts.items(), key=lambda pair: pair[0].value))
    verbs = sorted({step.verb for step in kept}, key=lambda verb: verb.value)
    tiers = tuple((verb, tier_for(verb, ceiling)) for verb in verbs)
    unattended: tuple[tuple[str, Verb], ...] = ()
    if now is not None:
        unattended = tuple(
            dict.fromkeys(
                (step.surface, step.verb)
                for step in kept
                if runs_unattended(
                    target,
                    step.surface,
                    step.verb,
                    ceiling=ceiling,
                    exceptions=exceptions,
                    now=now,
                )
            )
        )
    return Envelope(
        run_id=run_id,
        plan=plan,
        origins=target.origins,
        steps=tuple(kept),
        budget=budget,
        tiers=tiers,
        dropped=tuple(dropped),
        unattended=unattended,
    )


def compilation_only_removes(plan: Plan, envelope: Envelope) -> bool:
    """Whether the envelope's steps are a subsequence of the plan's.

    A property rather than a comment, so that a later edit adding a step during compilation
    fails a test. Subsequence rather than subset, because order is what the digest covers and
    a reordering would change the fingerprint of an approved envelope without changing what
    it permits, which is the same class of surprise from the other direction.
    """
    remaining = list(plan.steps)
    for step in envelope.steps:
        while remaining and remaining[0] != step:
            remaining.pop(0)
        if not remaining:
            return False
        remaining.pop(0)
    return True
