"""Capabilities, and the set of them a principal holds.

A Capability is an atomic permission string. An EntitlementSet is every capability a
principal holds, each bound to the scope it applies in, reduced to a stable hash so a
cache key can encode "who was asking" without encoding who they were.

The one rule this module exists to enforce: entitlements are **additive only**. There is
no deny clause and no subtraction. A field is invisible because no grant covers it, never
because a rule removed it. Deny rules are what make permission systems unanswerable,
once you have them, "can X see Y" stops being a lookup and becomes an evaluation order
problem.

Task ids: M0.2.3, M0.2.4
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from brain.core.scope import Scope

#: verb:noun[.field], lowercase, dot-separated, no wildcards except a trailing `.*`
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*|\.\*)*$")

VERBS = frozenset({"read", "write", "invoke", "approve", "admin"})

#: Why the capabilities a run holds are read off both sides of the intersection.
A_WILDCARD_IS_NARROWED_BY_THE_LENS_AND_NEVER_DROPPED: Final = (
    "A run reaches each capability exactly where the caller and the ceiling both reach it, so "
    "the capabilities it holds are those either side names and both reach, each in both scopes "
    "conjoined. Reading them off the caller alone drops a caller's read:client.* whenever a "
    "ceiling names read:client.hours_remaining, because a column does not cover a wildcard, and "
    "every Department Admin holds wildcards. Taking the caller's scope from the one grant being "
    "walked, rather than from scope_for, is the permissive half: a wildcard grant the ceiling "
    "does not cover is dropped with its scope clauses, and the run reaches the column more "
    "widely than the caller does. Both sides are asked the same question about the same "
    "capabilities, and there is no second loop mirroring the first."
)


class Capability(BaseModel):
    """One atomic permission, e.g. `read:client.hours_remaining`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str = Field(min_length=3, max_length=200)

    @field_validator("value")
    @classmethod
    def _grammar(cls, v: str) -> str:
        if not CAPABILITY_RE.match(v):
            msg = f"capability {v!r} does not match verb:noun[.field] grammar"
            raise ValueError(msg)
        verb = v.split(":", 1)[0]
        if verb not in VERBS:
            msg = f"unknown verb {verb!r}; known verbs are {sorted(VERBS)}"
            raise ValueError(msg)
        return v

    @property
    def verb(self) -> str:
        return self.value.split(":", 1)[0]

    @property
    def noun(self) -> str:
        return self.value.split(":", 1)[1].split(".", 1)[0]

    def covers(self, other: Capability) -> bool:
        """True when holding self implies holding other.

        Only a trailing `.*` expands. `read:client.*` covers `read:client.name`;
        `read:client` does not, because an entity-level grant must not silently
        confer every field on it.
        """
        if self.value == other.value:
            return True
        if self.value.endswith(".*"):
            return other.value.startswith(self.value[:-1])
        return False


class Grant(BaseModel):
    """A capability bound to the scope it applies in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: Capability
    scope: Scope


class EntitlementSet(BaseModel):
    """Everything a principal holds. Additive only; there is no deny list by design.

    `not_after` is carried here rather than checked by whoever builds this, because a
    check that lives in a helper is a check someone can construct their way around. An
    expired principal's grants stay on file, revocation and expiry are different events,
    so the set has to know it is expired and refuse on that basis.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    grants: tuple[Grant, ...] = ()
    #: Copied from the principal at construction. None means no time bound.
    not_after: datetime | None = None
    #: The earliest instant after the load at which one of these grants lapses, as
    #: `gate.entitlements_with_lapse` reports it. None means no grant here is dated. It is not a
    #: bound on the principal and nothing here judges it: a lapsed grant is already absent from
    #: `grants`, so this says only when that list stops being the truth, and
    #: `brain.gate.resolve` reads it to decide how long a cached copy may live. Left out of
    #: `ent_hash` because the grants themselves change at the lapse, and out of `intersect`'s
    #: result because a run reach is derived per request and never cached by `resolve`. Omitted
    #: from the JSON when None, so a reach with no dated grant serialises exactly as it did
    #: before the field existed: `tests/unit/test_delegation_sql.py` pins that document's keys,
    #: because the delegation trigger reads it by name.
    next_grant_lapse: datetime | None = Field(default=None, exclude_if=lambda value: value is None)

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.not_after is None:
            return False
        return (now or datetime.now(UTC)) >= self.not_after

    def scope_for(self, capability: Capability, now: datetime | None = None) -> Scope | None:
        """The scope in which this principal holds `capability`, or None.

        Where several grants cover it, the scopes are intersected. That is deliberately
        the conservative reading: holding a capability twice must never be wider than
        holding it once.

        An expired principal holds nothing, whatever the grant table still says.
        """
        if self.is_expired(now):
            return None
        matched = [g.scope for g in self.grants if g.capability.covers(capability)]
        if not matched:
            return None
        result = matched[0]
        for s in matched[1:]:
            result = result.intersect(s)
        return result

    def holds(self, capability: Capability, now: datetime | None = None) -> bool:
        return self.scope_for(capability, now) is not None

    def intersect(self, ceiling: EntitlementSet, now: datetime | None = None) -> Self:
        """`E_run(caller, agent) = E(caller) ∩ agent_ceiling`.

        The core invariant of the whole platform. A run gets a capability only when the
        caller holds it *and* the agent's ceiling admits it, and the scope is the
        conjunction of both. An agent can therefore only ever narrow.

        **A run reaches every capability exactly where both sides reach it, and the
        capabilities it holds are read off both sides.** For each capability either side
        names, the run holds it in the caller's scope for it conjoined with the ceiling's, and
        not at all when either side reaches nothing. Where one grant covers the other, what
        survives is therefore the narrower capability under both scopes, whichever side held
        the wider one.

        **Until 2026-09-14 the capabilities were read off the caller alone, and that was wrong
        in both directions.** A caller holding `read:client.*` through a ceiling naming
        `read:client.hours_remaining` kept nothing, because a column does not cover a wildcard;
        the wave-three milestone found it, and it meant every Department Admin and the Super
        Admin reached nothing through an agent naming columns. The permissive half was quieter:
        the caller's scope was taken from the one grant being walked rather than from
        `scope_for`, so a wildcard grant the ceiling did not cover was dropped together with its
        clauses, and a caller holding the wildcard in Maintenance and the column in the gold tier
        came out reaching the column in gold clients of every department. The same happened
        from the ceiling's side. Measured over every pair of sets of at most two grants, 2,088 of
        43,687 answers were wrong; `tests/invariants/test_entitlement_invariants.py` asks all of
        them.

        **One path, asked of both sides, rather than a second loop.** The repair that suggests
        itself is a second pass over the ceiling's grants mirroring the first. That is a second
        implementation of the rule inside the method that exists to be the only one, and it
        would still read the caller's scope off a single grant, which is the permissive half.
        Instead both sides are asked the question the ceiling was always asked, `scope_for`,
        about the same capabilities, and the answers are conjoined once.

        **The caller is asked with its bound set aside, because its expiry is carried rather
        than judged here.** `scope_for` refuses an expired principal, so asking the caller
        through it at `now` would start deciding the left-hand side's expiry inside this method,
        and every call site passing an instant would change which side is judged when without
        anybody deciding it. The bound still reaches the result on `not_after`.

        **`now` is the instant the intersection is being reasoned about, and omitting it
        means the wall clock.** The right-hand side's expiry is evaluated here, because
        `scope_for` refuses an expired principal and a ceiling that has run out admits
        nothing; the left-hand side's is not evaluated here at all, it is carried out on
        `not_after` and asked later by whoever calls `scope_for` on the result. Until
        2026-09-08 this method had no way to be told the time, so that one evaluation used
        `datetime.now`.

        That asymmetry is not academic and it fails in the permissive direction. The four
        surfaces that ask "may this reader be told this" put the *reader* on the right, as
        `requirement(thing).intersect(reader)`, so the reader's expiry was the thing judged
        against the process clock rather than against the instant the caller was reasoning
        with. A recall being evaluated for an earlier instant, a replay, or an audit
        reconstruction would therefore admit a reader whose access had since lapsed. It was
        found by a test whose fixture expired at noon: green when it was written, red the
        next day, with nothing about the code having changed.

        Optional rather than required, because five call sites have no instant to give and
        inventing one for them would be worse than the wall clock. Which sites pass it is
        pinned in `tests/invariants/test_single_implementation.py` so the list stays a
        decision.
        """
        # See `A_WILDCARD_IS_NARROWED_BY_THE_LENS_AND_NEVER_DROPPED`. The caller's bound is set
        # aside for the question and carried out on `not_after` below, never judged here.
        unbounded = self.model_copy(update={"not_after": None})
        out: list[Grant] = []
        for capability in dict.fromkeys(g.capability for g in (*self.grants, *ceiling.grants)):
            held = unbounded.scope_for(capability)
            if held is None:
                continue
            admitted = ceiling.scope_for(capability, now)
            if admitted is None:
                continue
            out.append(Grant(capability=capability, scope=held.intersect(admitted)))
        # The tighter of the two bounds. An agent ceiling with its own expiry - a
        # time-boxed automation, say - must not outlive either side of the intersection.
        bounds = [d for d in (self.not_after, ceiling.not_after) if d is not None]
        return type(self)(
            principal_id=self.principal_id,
            grants=tuple(out),
            not_after=min(bounds) if bounds else None,
        )

    def ent_hash(self) -> str:
        """Stable, order-independent digest of this entitlement set.

        Used as part of a cache key so two callers with identical reach share a cached
        answer and two callers without it never can. Sorting before hashing is what makes
        it order-independent; without that, the same entitlement built in a different
        order would miss the cache and, worse, look like a different principal in traces.
        """
        parts = sorted(f"{g.capability.value}|{g.scope.model_dump_json()}" for g in self.grants)
        # The time bound is part of the identity. Without it, an answer cached before a
        # contractor's expiry would be served to that same contractor afterwards, because
        # the key would be identical on both sides of the boundary.
        parts.append(f"not_after|{self.not_after.isoformat() if self.not_after else ''}")
        digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
        return digest[:32]
