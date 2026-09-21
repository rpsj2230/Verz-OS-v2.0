"""A residency constraint attached to a scope, and the requirement a request's reach carries.

Task ids: M5.5.1
"""

from __future__ import annotations

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.models.residency import (
    ResidencyError,
    ScopedResidency,
    may_overlap,
    reach_scopes,
    requirement_for,
    requirement_of,
)
from brain.models.routing import UNCONSTRAINED, ResidencyRequirement


def dept(name: str) -> Scope:
    return Scope.department(name)


def eu_only(scope: Scope) -> ScopedResidency:
    return ScopedResidency(
        scope=scope, requirement=ResidencyRequirement(allowed_regions=frozenset({"eu-west-1"}))
    )


def test_a_reach_inside_the_constrained_scope_carries_its_requirement() -> None:
    """The positive case. Delete this and a request reading finance could leave the constraint
    finance's scope carries behind."""
    found = requirement_for([eu_only(dept("finance"))], [dept("finance")])

    assert found.allowed_regions == frozenset({"eu-west-1"})


def test_a_reach_that_provably_misses_the_scope_carries_nothing() -> None:
    """Two scopes pinning `department` to different values share no row. Delete this and every
    constraint would bind every request, which is a residency rule for one department applied to
    the whole company."""
    assert requirement_for([eu_only(dept("finance"))], [dept("sales")]) == UNCONSTRAINED


@pytest.mark.parametrize(
    ("first", "second", "overlap"),
    [
        (Scope.unrestricted(), dept("finance"), True),
        (dept("finance"), Scope.unrestricted(), True),
        (dept("finance"), dept("finance"), True),
        (dept("finance"), dept("sales"), False),
        (
            Scope(clauses=(Clause(field="department", op=Op.IN, value=("finance", "legal")),)),
            dept("legal"),
            True,
        ),
        (
            Scope(clauses=(Clause(field="department", op=Op.IN, value=("finance", "legal")),)),
            dept("sales"),
            False,
        ),
        (Scope(clauses=(Clause(field="region", op=Op.PREFIX, value="eu-"),)), dept("sales"), True),
        (
            Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="fin"),)),
            dept("finance"),
            True,
        ),
        (
            Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="fin"),)),
            dept("sales"),
            False,
        ),
        (
            Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="fin"),)),
            Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="sal"),)),
            False,
        ),
        (
            Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="fin"),)),
            Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="finance"),)),
            True,
        ),
        (Scope(clauses=(Clause(field="department", op=Op.ANY),)), dept("sales"), True),
    ],
)
def test_two_scopes_are_disjoint_only_when_one_field_is_pinned_to_values_sharing_nothing(
    first: Scope, second: Scope, overlap: bool
) -> None:
    """`A_CONSTRAINT_APPLIES_UNLESS_THE_REACH_PROVABLY_MISSES_IT`, case by case. Delete this and
    a field only one side tests, or an `ANY`, could make two scopes read as disjoint, which drops
    a constraint the request needed."""
    assert may_overlap(first, second) is overlap


def test_two_constraints_a_request_touches_narrow_it_and_never_widen_it() -> None:
    """Delete this and a second constraint could replace the first rather than intersect with
    it, which is the one direction residency must never move."""
    both = requirement_for(
        [
            eu_only(dept("finance")),
            ScopedResidency(
                scope=Scope.unrestricted(),
                requirement=ResidencyRequirement(
                    allowed_regions=frozenset({"eu-west-1", "us-east-1"})
                ),
            ),
            ScopedResidency(
                scope=dept("finance"), requirement=ResidencyRequirement(on_prem_only=True)
            ),
        ],
        [dept("finance")],
    )

    assert both.allowed_regions == frozenset({"eu-west-1"})
    assert both.on_prem_only is True


def test_the_reach_is_every_scope_the_caller_holds_a_grant_over() -> None:
    """Delete this and a grant the caller holds could be left out of the reach, so a constraint on
    what it reads would not travel with the question."""
    held = EntitlementSet(
        principal_id="u_reader",
        grants=(
            Grant(capability=Capability(value="read:project"), scope=dept("finance")),
            Grant(capability=Capability(value="read:knowledge.document"), scope=dept("legal")),
        ),
    )

    assert reach_scopes(held) == (dept("finance"), dept("legal"))


@pytest.mark.parametrize(
    ("regions", "on_prem", "said"),
    [
        (None, False, "demands nothing"),
        ([], False, "allowing no region"),
        (["global"], False, "names no place"),
        ([""], False, "1 to"),
        (["r"] * 21, False, "at most"),
    ],
)
def test_a_constraint_that_would_mislead_is_refused(
    regions: list[str] | None, on_prem: bool, said: str
) -> None:
    """Delete this and a constraint that routes exactly as none, refuses every question, or
    promises a place no rung can be could be written and shown as a policy."""
    with pytest.raises(ResidencyError, match=said):
        requirement_of(regions, on_prem_only=on_prem)


def test_a_constraint_naming_regions_or_on_prem_is_kept_as_it_says() -> None:
    """The sibling of the refusals. Delete this and the refusals could be satisfied by a function
    that refuses everything."""
    assert requirement_of([" eu-west-1 "], on_prem_only=False) == ResidencyRequirement(
        allowed_regions=frozenset({"eu-west-1"})
    )
    assert requirement_of(None, on_prem_only=True) == ResidencyRequirement(on_prem_only=True)
