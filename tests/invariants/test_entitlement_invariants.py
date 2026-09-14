"""The rules that must never break. A failure here blocks deploy.

Each test carries the invariant id from the delivery document so a failure names the rule
it broke rather than the assertion that noticed.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent, Denied, to_public
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.core.scope_sql import compile_where

pytestmark = pytest.mark.invariant


def cap(v: str) -> Capability:
    return Capability(value=v)


def ent(pid: str, *pairs: tuple[str, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=tuple(Grant(capability=cap(c), scope=s) for c, s in pairs),
    )


# ------------------------------------------------------------------ INV-1
def test_inv1_agent_can_only_narrow() -> None:
    """INV-1: E_run(caller, agent) = E(caller) ∩ ceiling. An agent never widens."""
    caller = ent("u1", ("read:client.name", Scope.department("maintenance")))
    ceiling = ent(
        "agent",
        ("read:client.name", Scope.unrestricted()),
        ("read:client.contract_value", Scope.unrestricted()),
    )
    run = caller.intersect(ceiling)

    assert run.holds(cap("read:client.name"))
    # the ceiling offers it; the caller does not hold it, so the run must not have it
    assert not run.holds(cap("read:client.contract_value"))


def test_inv1_ceiling_narrows_a_wide_caller() -> None:
    caller = ent("u1", ("read:client.name", Scope.unrestricted()))
    ceiling = ent("agent", ("read:client.name", Scope.department("maintenance")))
    run = caller.intersect(ceiling)

    scope = run.scope_for(cap("read:client.name"))
    assert scope is not None
    assert scope.matches({"department": "maintenance"})
    assert not scope.matches({"department": "sales"})


def test_inv1_intersection_is_idempotent() -> None:
    caller = ent("u1", ("read:client.name", Scope.department("maintenance")))
    once = caller.intersect(caller)
    twice = once.intersect(caller)
    assert once.ent_hash() == twice.ent_hash()


#: The capability shapes `Capability.covers` tells apart: a record grant, a wildcard, a column
#: under it, and a wildcard under the wildcard. Each way two of them can be comparable is a way
#: the lens has been wrong.
PATTERNS = ("read:client", "read:client.*", "read:client.name", "read:client.billing.*")

#: What is asked of every result: each pattern, a column under each wildcard that no grant
#: names, and a noun sharing a prefix with `client` that nothing here may ever cover.
QUESTIONS = (
    *PATTERNS,
    "read:client.billing.total",
    "read:client.hours_remaining",
    "read:clients.name",
)

#: Unrestricted, and two scopes on different fields, so a conjunction shows up as two clauses.
SCOPES = (
    Scope.unrestricted(),
    Scope.department("maintenance"),
    Scope(clauses=(Clause(field="tier", op=Op.EQ, value="gold"),)),
)

#: An instant no bound in this universe comes near. Nothing about these two tests is the present.
FAR_FROM_ANY_BOUND = datetime(2500, 1, 1, tzinfo=UTC)


def _every_set_of_at_most_two_grants() -> list[EntitlementSet]:
    """Seventy-nine sets: no grant, each of twelve grants, and each of the sixty-six pairs."""
    grants = [Grant(capability=cap(p), scope=s) for p in PATTERNS for s in SCOPES]
    held: list[tuple[Grant, ...]] = [(), *((one,) for one in grants)]
    held.extend(itertools.combinations(grants, 2))
    return [EntitlementSet(principal_id="p", grants=one) for one in held]


def _written(one: EntitlementSet) -> str:
    return "; ".join(
        f"{g.capability.value} in {[(c.field, c.value) for c in g.scope.clauses]}"
        for g in one.grants
    )


def test_inv1_a_run_reaches_every_capability_exactly_where_both_sides_do() -> None:
    """INV-1 as the property itself, over every pair of sets in a universe, 43,687 answers.

    For every capability asked, the run's scope is the caller's and the ceiling's conjoined, and
    nothing when either side reaches nothing. Equality rather than containment, because both
    halves have been broken. *Never wider than either side* is the half that stops a leak.
    *Never narrower than both* is the half the wave-three milestone found broken, where a
    Department Admin's `read:client.*` reached nothing through a ceiling naming a column.
    Equality also makes the order of the two sides irrelevant, which is what lets
    `requirement(thing).intersect(reader)` and its reverse be the same question.

    **Measured on 2026-09-14 against the method as it stood: 2,088 of these answers were wrong,
    in both directions.** Some were empty where both sides reached the capability. Others were
    wider than one side, where a caller's or a ceiling's wildcard grant was dropped whole and
    took its scope clauses with it.

    The count of reached answers is asserted too, so the universe cannot be edited into one
    where every side reaches nothing and equality holds vacuously.

    Delete this and the invariant is held only by the cases somebody thought to write down,
    which is how both directions of the defect went unnoticed."""
    sets = _every_set_of_at_most_two_grants()
    questions = [cap(one) for one in QUESTIONS]
    at = FAR_FROM_ANY_BOUND
    wrong: list[str] = []
    reached = 0

    for caller in sets:
        for ceiling in sets:
            run = caller.intersect(ceiling, at)
            for question in questions:
                held = caller.scope_for(question, at)
                admitted = ceiling.scope_for(question, at)
                expected = None if held is None or admitted is None else held.intersect(admitted)
                got = run.scope_for(question, at)
                reached += got is not None
                if got != expected:
                    wrong.append(
                        f"caller [{_written(caller)}], ceiling [{_written(ceiling)}], "
                        f"{question.value}: got {got}, expected {expected}"
                    )

    assert not wrong, f"{len(wrong)} answers differ; the first is {wrong[0]}"
    assert reached > 0


def test_inv1_a_run_holds_no_capability_either_side_does_not_cover() -> None:
    """INV-1 grant by grant: every capability a run holds is one `covers` admits on both sides.

    The literal form of "an agent never widens", over the same universe as the test above. That
    test can only see a wrongly held capability through a question it happens to cover, and this
    asks the grants themselves. It matters now because a run's capabilities are read off the
    ceiling as well as the caller, which is what narrows a wildcard and is also the one route by
    which a wide ceiling could hand a narrow caller what it lists.

    The count of held grants is the positive sibling, so a run that held nothing passes neither.

    Delete this and a repair that took a capability from the ceiling without asking the caller
    is caught only if some question happens to fall under it."""
    at = FAR_FROM_ANY_BOUND
    held = 0

    for caller in _every_set_of_at_most_two_grants():
        for ceiling in _every_set_of_at_most_two_grants():
            for grant in caller.intersect(ceiling, at).grants:
                held += 1
                assert caller.holds(grant.capability, at), (grant, _written(caller))
                assert ceiling.holds(grant.capability, at), (grant, _written(ceiling))

    assert held > 0


# ------------------------------------------------------------------ INV-2
def test_inv2_scopes_compose_by_conjunction_only() -> None:
    """INV-2: composing scopes can only narrow. Two grants never combine into a wider one."""
    a = Scope.department("maintenance")
    b = Scope(clauses=(Clause(field="client_tier", op=Op.EQ, value="managed"),))
    both = a.intersect(b)

    assert both.matches({"department": "maintenance", "client_tier": "managed"})
    assert not both.matches({"department": "maintenance", "client_tier": "adhoc"})
    assert not both.matches({"department": "sales", "client_tier": "managed"})


def test_inv2_absent_field_never_satisfies_a_predicate() -> None:
    """A partially projected row must not widen access by omission."""
    s = Scope.department("maintenance")
    assert not s.matches({})
    assert not s.matches({"department": None})


def test_inv2_duplicate_grants_do_not_widen() -> None:
    e = ent(
        "u1",
        ("read:client.name", Scope.department("maintenance")),
        ("read:client.name", Scope(clauses=(Clause(field="tier", op=Op.EQ, value="a"),))),
    )
    scope = e.scope_for(cap("read:client.name"))
    assert scope is not None
    # holding it twice is the conjunction, not the union
    assert scope.matches({"department": "maintenance", "tier": "a"})
    assert not scope.matches({"department": "maintenance", "tier": "b"})


# ------------------------------------------------------------------ INV-3
def test_inv3_entitlements_are_additive_only() -> None:
    """INV-3: a field is hidden because no grant covers it, never because a rule removed it."""
    e = ent("u1", ("read:client.hours_remaining", Scope.department("maintenance")))
    assert e.holds(cap("read:client.hours_remaining"))
    assert not e.holds(cap("read:client.contract_value"))
    # there is no API to subtract; the type exposes no deny list at all
    assert not hasattr(e, "denials")
    assert not hasattr(e, "deny")


def test_inv3_entity_grant_does_not_confer_every_field() -> None:
    """`read:client` must not silently grant `read:client.contract_value`."""
    e = ent("u1", ("read:client", Scope.unrestricted()))
    assert not e.holds(cap("read:client.contract_value"))


def test_inv3_explicit_wildcard_does_confer_fields() -> None:
    e = ent("u1", ("read:client.*", Scope.unrestricted()))
    assert e.holds(cap("read:client.contract_value"))


# ------------------------------------------------------------------ INV-4
def test_inv4_ent_hash_is_order_independent() -> None:
    """INV-4: two identical entitlements built in different orders share a cache key."""
    a = ent(
        "u1",
        ("read:client.name", Scope.department("maintenance")),
        ("read:ticket.status", Scope.department("maintenance")),
    )
    b = ent(
        "u1",
        ("read:ticket.status", Scope.department("maintenance")),
        ("read:client.name", Scope.department("maintenance")),
    )
    assert a.ent_hash() == b.ent_hash()


def test_inv4_ent_hash_differs_on_any_difference() -> None:
    a = ent("u1", ("read:client.name", Scope.department("maintenance")))
    b = ent("u1", ("read:client.name", Scope.department("sales")))
    c = ent("u1", ("read:client.name", Scope.unrestricted()))
    assert len({a.ent_hash(), b.ent_hash(), c.ent_hash()}) == 3


def test_inv4_narrower_caller_never_shares_a_key_with_a_wider_one() -> None:
    wide = ent("u1", ("read:client.*", Scope.unrestricted()))
    narrow = ent("u2", ("read:client.name", Scope.department("maintenance")))
    assert wide.ent_hash() != narrow.ent_hash()


# ------------------------------------------------------------------ INV-5
def test_inv5_denied_is_indistinguishable_from_absent_in_public() -> None:
    """INV-5: an error message must never confirm that a hidden record exists."""
    assert to_public(Denied("client 4471 contract_value")) == to_public(Absent("no such client"))


def test_inv5_detail_is_retained_for_audit() -> None:
    d = Denied("client 4471 contract_value")
    assert "4471" in d.detail
    assert "4471" not in to_public(d)


# ------------------------------------------------------------------ INV-6
def test_inv6_expiry_is_enforced_at_entitlement_time() -> None:
    """INV-6: a session opened before expiry must not survive it."""
    now = datetime.now(UTC)
    p = Principal(
        id="c1",
        kind=PrincipalKind.HUMAN,
        employment=Employment.CONTRACTOR,
        display_name="Contractor",
        not_after=now - timedelta(seconds=1),
    )
    assert not p.is_active(now)


def test_inv6_bounded_engagements_must_carry_an_expiry() -> None:
    for employment in (Employment.CONTRACTOR, Employment.PARTNER):
        with pytest.raises(ValueError, match="not_after"):
            Principal(
                id="x",
                kind=PrincipalKind.HUMAN,
                employment=employment,
                display_name="No expiry",
            )


def test_inv6_naive_expiry_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Principal(
            id="x",
            kind=PrincipalKind.HUMAN,
            employment=Employment.CONTRACTOR,
            display_name="Naive",
            not_after=datetime(2027, 1, 1),
        )


# ------------------------------------------------------------------ INV-7
def test_inv7_scope_sql_never_interpolates_a_value() -> None:
    """INV-7: predicate rendering is parameterised. A client name cannot become SQL.

    Asserted against `compile_where` since 2026-09-09, when `Scope.to_sql` was deleted as a
    second renderer of this rule. The invariant belongs to whichever function renders the
    predicate, and there is now exactly one.

    Delete this and a department name typed into a console form can close a quote and
    become query text, in the function that decides which rows a person receives.
    """
    s = Scope(clauses=(Clause(field="department", op=Op.EQ, value="'; DROP TABLE grants--"),))

    compiled = compile_where(s)

    assert "DROP TABLE" not in compiled.where
    assert "DROP TABLE" in next(iter(compiled.params.values()))


def test_inv7_unrestricted_scope_renders_true() -> None:
    """An unrestricted scope compiles to a predicate that admits every row, and to no bound
    parameters at all.

    The failure this guards is the opposite of the usual one: a renderer that emitted an
    empty string for no clauses would produce a query with no WHERE clause, which reads the
    same and means the same, right up until it is composed with another fragment.

    Delete this and the company-wide grant is the case nothing checks.
    """
    compiled = compile_where(Scope.unrestricted())

    assert compiled.where == "TRUE"
    assert compiled.params == {}


# ------------------------------------------------------------------ regression
def test_scope_normalises_duplicate_clauses() -> None:
    """Regression, found by test_inv1_intersection_is_idempotent on 2026-09-04.

    `intersect` concatenates clause tuples, so intersecting a scope with itself produced
    `(department=maintenance, department=maintenance)`. Same meaning, different
    serialisation, therefore a different ent_hash - which is the cache key. The same
    caller would have missed their own cache entry and shown up in traces as a different
    principal. Scope now deduplicates and sorts on construction.
    """
    s = Scope.department("maintenance")
    assert len(s.intersect(s).clauses) == 1
    assert s.intersect(s) == s


def test_scope_clause_order_does_not_affect_identity() -> None:
    """Two scopes admitting the same rows must be the same object and must compile to the
    same SQL, because the serialisation is what `EntitlementSet.ent_hash` reads and the hash
    is the cache key.

    The compiled half matters separately from the object half: normalisation could be
    correct on the model and lost by a renderer that iterated the clauses as given, and then
    two identical scopes would produce two fragments and two bound-parameter maps.

    Delete this and the same caller can miss their own cache entry and appear in traces as a
    different principal.
    """
    a = Clause(field="department", op=Op.EQ, value="maintenance")
    b = Clause(field="tier", op=Op.EQ, value="managed")

    assert Scope(clauses=(a, b)) == Scope(clauses=(b, a))
    assert compile_where(Scope(clauses=(a, b))) == compile_where(Scope(clauses=(b, a)))
