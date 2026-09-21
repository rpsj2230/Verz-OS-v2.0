"""A residency constraint attached to a scope, and the requirement a request carries from it.

`brain.models.routing` has had `ResidencyRequirement` since the start, `RoutingChain.select` skips
a rung that cannot satisfy one, and `ChainSelection.require` refuses when nothing compliant is
left. What nothing did was produce a requirement: every call on the live path was `UNCONSTRAINED`,
so the skip and the refusal were correct code no request ever reached. This module is the missing
half. An administrator attaches a constraint to a scope (`ops.residency_constraint`, one row each,
written from the Models screen), and a request carries the requirement of every constraint its
reach touches, which the executor hands to the chain.

**A constraint lives beside a scope, not inside one.** `ResidencyRequirement`'s docstring gives the
reason and it is kept: `Scope` composes by conjunction only and a non-predicate field on it would
make `Scope.intersect` describe something the type does not do. So the row pairs a `Scope`, in the
same `model_dump()` shape the grant tables hold, with the regions it allows.

**A constraint applies unless the request's reach provably misses its scope.** The request carries
its caller's reach, which is the scope of every grant it holds, because that is everything the
answer could be drawn from. Deciding whether two scopes overlap exactly would need a solver over
the predicate grammar; what is decidable cheaply is that two scopes are disjoint, when both pin one
field to values that share nothing. So `may_overlap` answers False only then, and every other case,
including an unrestricted scope on either side, applies the constraint. The error this admits is a
request routed more narrowly than it needed to be, which is a refusal somebody can see and ask
about; the other error would be regulated data sent to a region its policy forbids, which nobody
sees until an audit. See `A_CONSTRAINT_APPLIES_UNLESS_THE_REACH_PROVABLY_MISSES_IT`.

**Requirements compose by `ResidencyRequirement.intersect` and nothing else**, so two constraints a
request touches can only narrow it, and two whose regions share nothing leave no region at all,
which `RoutingChain.select` turns into a refusal rather than into "route anywhere".

Scope: pure. The constraints and the reach are parameters.

Task ids: M5.5.1
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from brain.core.entitlement import EntitlementSet
from brain.core.scope import Clause, Op, Scope
from brain.models.routing import UNCONSTRAINED, ResidencyClass, ResidencyRequirement

#: Why a constraint is applied whenever overlap cannot be ruled out.
A_CONSTRAINT_APPLIES_UNLESS_THE_REACH_PROVABLY_MISSES_IT: Final = (
    "Whether a request's reach overlaps a constrained scope is decided conservatively: only two "
    "scopes that pin one field to values sharing nothing are disjoint, and anything else applies "
    "the constraint. Too narrow a route is a refusal a person can see and ask about; too wide a "
    "one sends regulated data across a border and is found in an audit months later."
)

#: The most regions one constraint may allow. A resource bound far above any real policy.
MAX_REGIONS: Final = 20

#: The longest region name a constraint may carry, matching a provider row's region column.
REGION_CHARS: Final = 60


class ResidencyError(ValueError):
    """Raised for a constraint that would not mean what it says."""


@dataclass(frozen=True)
class ScopedResidency:
    """One stored constraint: the scope it is attached to, and what it demands of a region."""

    scope: Scope
    requirement: ResidencyRequirement
    reason: str = ""


def requirement_of(
    allowed_regions: Sequence[str] | None, *, on_prem_only: bool
) -> ResidencyRequirement:
    """The requirement a row states, or a `ResidencyError` for one that would mislead.

    Refused: a constraint that demands nothing, which reads on the screen as a policy and routes
    exactly as no constraint does; an empty region list, which refuses every question and is a
    switch-off better made by switching providers off; and `global`, which names no place and which
    `ResidencyRequirement.satisfied_by` never accepts, so a constraint allowing it would promise a
    route it can never take.
    """
    if allowed_regions is None:
        if not on_prem_only:
            msg = (
                "a constraint that allows every region and does not demand on-prem demands nothing"
            )
            raise ResidencyError(msg)
        return ResidencyRequirement(on_prem_only=True)
    regions = [one.strip() for one in allowed_regions]
    if not regions:
        msg = "a constraint allowing no region refuses every question; switch providers off instead"
        raise ResidencyError(msg)
    if len(regions) > MAX_REGIONS:
        msg = f"a constraint may name at most {MAX_REGIONS} regions"
        raise ResidencyError(msg)
    for one in regions:
        if not one or len(one) > REGION_CHARS:
            msg = f"a region is named in 1 to {REGION_CHARS} characters"
            raise ResidencyError(msg)
        if one == ResidencyClass.GLOBAL.value:
            msg = "global names no place, so no constraint can allow it"
            raise ResidencyError(msg)
    return ResidencyRequirement(allowed_regions=frozenset(regions), on_prem_only=on_prem_only)


def _values(clause: Clause) -> frozenset[str] | None:
    """The exact values an EQ or IN clause admits, or None when the clause admits an open set."""
    if clause.op is Op.EQ:
        return frozenset() if clause.value is None else frozenset({str(clause.value)})
    if clause.op is Op.IN and isinstance(clause.value, tuple):
        return frozenset(clause.value)
    return None


def _disjoint(one: Clause, other: Clause) -> bool:
    """True only when no value can satisfy both clauses on the same field."""
    left, right = _values(one), _values(other)
    if left is not None and right is not None:
        return not (left & right)
    prefixes = [c.value for c in (one, other) if c.op is Op.PREFIX and isinstance(c.value, str)]
    if len(prefixes) == 2:
        first, second = prefixes
        return not (first.startswith(second) or second.startswith(first))
    if len(prefixes) == 1:
        exact = left if right is None else right
        if exact is not None:
            return not any(value.startswith(prefixes[0]) for value in exact)
    return False


def may_overlap(first: Scope, second: Scope) -> bool:
    """False only when some field is pinned by both scopes to values that share nothing.

    See `A_CONSTRAINT_APPLIES_UNLESS_THE_REACH_PROVABLY_MISSES_IT`. An `ANY` clause and a field
    only one scope tests say nothing, so they never make two scopes disjoint.
    """
    for one in first.clauses:
        for other in second.clauses:
            if one.field == other.field and _disjoint(one, other):
                return False
    return True


def reach_scopes(entitlement: EntitlementSet) -> tuple[Scope, ...]:
    """Every scope the caller holds a grant over: everything an answer could be drawn from."""
    return tuple(grant.scope for grant in entitlement.grants)


def requirement_for(
    constraints: Iterable[ScopedResidency], reach: Iterable[Scope]
) -> ResidencyRequirement:
    """The requirement a request with this reach carries: every touched constraint, intersected.

    A reach with no scope at all touches nothing and carries no constraint, which is right: a
    caller holding no grant is refused before any model is asked.
    """
    scopes = tuple(reach)
    found = UNCONSTRAINED
    for one in constraints:
        if any(may_overlap(one.scope, scope) for scope in scopes):
            found = found.intersect(one.requirement)
    return found
