"""When agent A calls agent B, B runs at the asker's reach narrowed by every lens between.

The question this file exists to answer is whose reach a delegated run holds, and the
answer is asserted rather than described: an agent is not a caller, so the left-hand side
of every hop is the running reach and never the previous agent's ceiling, and the whole
chain is a descending sequence.

**Every chain here is three hops long and that is deliberate.** A chain of two has no
interior, so an implementation that folds the first and the last ceiling and drops
everything between them is exactly right at two hops and wrong from three. There is a test
below that constructs that wrong implementation and shows both halves of it: agreeing with
the real fold at two hops, and handing back a capability the real fold removed at three.
Delete that test and a pair becomes a plausible way to check a fold.

Real `EntitlementSet`s, real `Scope`s, the real `AgentRecord` ceiling producer and the real
seeded budgets throughout. Nothing here stands in for the thing being tested: the point of
every assertion is what two real modules do when they meet, and a stub of an entitlement
set would be a stub of the rule.

Task ids: M18.3.3, M18.3.4, M18.3.5
"""

from __future__ import annotations

import ast
import itertools
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import (
    CEILING_PRINCIPAL_PREFIX,
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    entitlement_ceiling,
)
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import TrafficClass
from brain.knowledge.visibility import Visibility
from brain.ops.admission import (
    CapacityState,
    Resource,
    Verdict,
    WorkloadClass,
    seed_budgets,
)
from brain.ops.automation import flow_reach
from brain.orchestration.contract import (
    SUBTASK_CEILING_PREFIX,
    FieldKind,
    FieldSpec,
    SubtaskContract,
    subtask_ceiling,
)
from brain.orchestration.delegation import (
    MAX_CHILDREN_PER_RUN,
    MAX_DELEGATION_DEPTH,
    PARALLELISM_RESOURCE,
    Delegation,
    DelegationError,
    Hop,
    LensKind,
    chain_digests,
    chain_reach,
    chain_reaches,
    chain_refusals,
    child_hops,
    concurrency_refusals,
    depth_of,
    fan_out_request,
    global_ceiling,
    grant_verbs_in,
    may_fan_out,
    narrowing_refusals,
    narrows,
)

NOW = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "src" / "brain" / "orchestration"

NAME = "read:client.name"
HOURS = "read:client.hours_remaining"
TOTAL = "read:invoice.total"
TICKET = "write:ticket.status"


def _scope(**fields: str) -> Scope:
    return Scope(
        clauses=tuple(
            Clause(field=field, op=Op.EQ, value=value) for field, value in sorted(fields.items())
        )
    )


def _reach(principal_id: str, *capabilities: str, scope: Scope | None = None) -> EntitlementSet:
    """A person's own reach. Unrestricted scope unless one is given."""
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=scope or Scope()) for one in capabilities
        ),
    )


def _agent_hop(agent_id: str, *capabilities: str, scope: Scope | None = None) -> Hop:
    return Hop(
        lens_id=agent_id,
        kind=LensKind.AGENT,
        ceiling=EntitlementSet(
            principal_id=f"{CEILING_PRINCIPAL_PREFIX}{agent_id}",
            grants=tuple(
                Grant(capability=Capability(value=one), scope=scope or Scope())
                for one in capabilities
            ),
        ),
    )


def _contract(subtask_id: str, *capabilities: str, scope: Scope | None = None) -> SubtaskContract:
    return SubtaskContract(
        subtask_id=subtask_id,
        objective="Find every open invoice for this client",
        output=(FieldSpec(name="total", kind=FieldKind.DECIMAL),),
        scope=scope or Scope(),
        capabilities=tuple(Capability(value=one) for one in capabilities),
    )


def _subtask_hop(subtask_id: str, *capabilities: str, scope: Scope | None = None) -> Hop:
    return Hop(
        lens_id=subtask_id,
        kind=LensKind.SUBTASK,
        ceiling=subtask_ceiling(_contract(subtask_id, *capabilities, scope=scope)),
    )


def _held(reach: EntitlementSet) -> set[str]:
    return {grant.capability.value for grant in reach.grants}


def _clauses(reach: EntitlementSet, capability: str) -> set[tuple[str, str, object]]:
    scope = reach.scope_for(Capability(value=capability))
    assert scope is not None
    return {(clause.field, str(clause.op), clause.value) for clause in scope.clauses}


#: The chain every test about the fold uses. Each hop removes something the others do not,
#: and the middle one removes a capability the last one would have kept, which is the whole
#: reason the interior can be shown to matter.
def _three_hops() -> tuple[Hop, Hop, Hop]:
    return (
        _agent_hop("alpha", NAME, HOURS, TOTAL, scope=_scope(department="web")),
        _agent_hop("beta", NAME, HOURS, scope=_scope(region="apac")),
        _agent_hop("gamma", NAME, HOURS, TOTAL, scope=_scope(team="north")),
    )


def _asker() -> EntitlementSet:
    return _reach("p-ana", NAME, HOURS, TOTAL, TICKET)


# --------------------------------------------------------------- whose reach (the answer)
def test_a_delegated_run_holds_the_askers_reach_narrowed_by_every_lens_in_order():
    """The answer to the question this module exists for, asserted rather than described.

    Delete this and nothing says what a chain of agents produces, and the next reader has
    only the docstring, which is what four documents in this repository had before an agent
    read the source and found they all named a module that never contained the call."""
    hops = _three_hops()

    reach = chain_reach(_asker(), hops)

    # write:ticket.status is gone at the first hop, read:invoice.total at the second, and
    # nothing at the third restores either.
    assert _held(reach) == {NAME, HOURS}
    assert _clauses(reach, NAME) == {
        ("department", "eq", "web"),
        ("region", "eq", "apac"),
        ("team", "eq", "north"),
    }


def test_a_run_through_three_agents_is_still_the_askers_run():
    """`intersect` keeps the caller's principal id, which is what makes an agent a lens
    rather than a principal. Delete this and a chain could start attributing itself to the
    last agent on it, and every audit row for a depth-two subtask would name a thing that
    holds no grants."""
    hops = _three_hops()

    reaches = chain_reaches(_asker(), hops)

    assert [one.principal_id for one in reaches] == ["p-ana"] * 4


def test_the_chain_narrows_at_every_one_of_three_hops_and_never_restores():
    """The invariant stated over the whole sequence rather than at the ends.

    Delete this and an implementation that widened in the middle and narrowed again at the
    last hop would pass every other test here, because the endpoints would agree."""
    hops = _three_hops()

    reaches = chain_reaches(_asker(), hops)

    assert len(reaches) == len(hops) + 1
    for wider, narrower in itertools.pairwise(reaches):
        assert narrows(narrower, wider), narrowing_refusals(narrower, wider)
    # Strictly, at every hop: each of the three takes something away, so no two are equal.
    assert len({one.ent_hash() for one in reaches}) == len(reaches)


def test_a_chain_of_two_cannot_tell_the_real_fold_from_one_that_drops_the_interior():
    """**The reason every chain here is three hops.**

    A fold that keeps the first and the last ceiling and ignores everything between them is
    identical to the real one at two hops, because at two hops the first and the last are
    all of them. At three it hands back a capability the real fold removed, which is a
    widening, and it is the exact shape an implementation takes when somebody optimises the
    loop into "the caller's reach, narrowed by the agent being called".

    Delete this and a pair of hops looks like a sufficient test of a fold, which is how the
    interior stops being covered at all."""

    def dropping_the_interior(caller: EntitlementSet, hops: tuple[Hop, ...]) -> EntitlementSet:
        """The wrong implementation, written here so the test can show what it costs."""
        if not hops:
            return caller
        first = flow_reach(caller, hops[0].ceiling)
        if len(hops) == 1:
            return first
        return flow_reach(first, hops[-1].ceiling)

    asker = _asker()
    hops = _three_hops()

    pair = hops[:2]
    assert chain_reach(asker, pair).ent_hash() == dropping_the_interior(asker, pair).ent_hash()

    right = chain_reach(asker, hops)
    wrong = dropping_the_interior(asker, hops)
    assert right.ent_hash() != wrong.ent_hash()
    assert TOTAL in _held(wrong)
    assert TOTAL not in _held(right)
    assert ("region", "eq", "apac") not in _clauses(wrong, NAME)


def test_a_wide_ceiling_at_the_last_hop_restores_nothing_an_earlier_hop_removed():
    """An agent is not a way to launder a reach.

    The last agent's ceiling admits everything the asker ever held, including the capability
    the first hop removed, and the run still does not get it back. Delete this and the one
    property that makes installing an agent different from granting has no test: a wide
    ceiling deep in a chain would become a grant nobody wrote."""
    asker = _asker()
    hops = (
        _agent_hop("alpha", NAME),
        _agent_hop("beta", NAME, HOURS, TOTAL, TICKET),
        _agent_hop("gamma", NAME, HOURS, TOTAL, TICKET),
    )

    reach = chain_reach(asker, hops)

    assert _held(reach) == {NAME}


def test_a_subtask_hop_narrows_the_same_run_rather_than_starting_a_new_delegation():
    """`parent intersect agent intersect subtask` is one delegation with two ceilings, which
    is what makes the three-way narrowing need no three-way function and no new intersection
    call site.

    Delete this and the subtask ceiling could be counted as a hop of its own, which would
    halve the usable depth without anybody changing the cap."""
    asker = _asker()
    parent = (_agent_hop("alpha", NAME, HOURS, TOTAL, scope=_scope(department="web")),)
    hops = child_hops(
        parent,
        agent=_agent_hop("beta", NAME, HOURS),
        subtask=_subtask_hop("s-1", NAME, scope=_scope(client="c-9")),
    )

    reach = chain_reach(asker, hops)

    assert depth_of(hops) == 1
    assert _held(reach) == {NAME}
    assert _clauses(reach, NAME) == {("department", "eq", "web"), ("client", "eq", "c-9")}


def test_the_real_agent_ceiling_producer_makes_a_hop_this_module_accepts():
    """Driven through `brain.agents.model.entitlement_ceiling` rather than a set built here,
    because a producer and a consumer either side of one value need a test written from the
    producer's own output or there are two tests for the consumer.

    Delete this and the prefix rule could be satisfied by every hop in this file while the
    one function that actually builds an agent ceiling produced something the constructor
    refuses."""
    record = AgentRecord(
        agent_id="finance_helper",
        display_name="Finance helper",
        persona="Answers questions about invoices.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id="p-ana"),
        authority=AgentAuthority(
            scope=_scope(department="finance"),
            capabilities=(Capability(value=NAME),),
        ),
        created_by="p-ana",
    )

    hop = Hop(lens_id=record.agent_id, kind=LensKind.AGENT, ceiling=entitlement_ceiling(record))
    reach = chain_reach(_asker(), (hop,))

    assert hop.ceiling.principal_id == f"{CEILING_PRINCIPAL_PREFIX}finance_helper"
    assert _held(reach) == {NAME}
    assert _clauses(reach, NAME) == {("department", "eq", "finance")}


def test_the_reach_expires_at_the_tighter_of_the_askers_bound_and_a_ceilings():
    """A time-boxed lens must not outlive either side, and a chain must not extend it.

    Delete this and a contractor's expiry could be lost at the second hop, which is the one
    place in this system where a permission would outlive the decision that made it."""
    asker = EntitlementSet(
        principal_id="p-ana",
        grants=(Grant(capability=Capability(value=NAME), scope=Scope()),),
        not_after=NOW + timedelta(days=7),
    )
    tight = EntitlementSet(
        principal_id=f"{CEILING_PRINCIPAL_PREFIX}alpha",
        grants=(Grant(capability=Capability(value=NAME), scope=Scope()),),
        not_after=NOW + timedelta(days=1),
    )
    hops = (
        Hop(lens_id="alpha", kind=LensKind.AGENT, ceiling=tight),
        _agent_hop("beta", NAME),
    )

    reach = chain_reach(asker, hops)

    assert reach.not_after == NOW + timedelta(days=1)


def test_an_empty_chain_is_the_person_acting_as_themselves():
    """The positive case for the fold's base. A run with no lens on it is the asker, and
    inventing a narrowing for it would be this module deciding a policy nobody asked for.

    Delete this and a base case that returned an empty set would look correct, because every
    other test here has at least one hop and would go on passing."""
    asker = _asker()

    assert chain_reach(asker, ()).ent_hash() == asker.ent_hash()
    assert chain_reaches(asker, ()) == (asker,)


def test_the_audit_digests_are_one_per_point_on_the_chain():
    """An audit row records the hash of the reach at each hop rather than the reach itself,
    which is what lets somebody ask afterwards which lens removed a capability without the
    row being a copy of somebody's permissions.

    Delete this and the digests could silently become the endpoints only, and a trace would
    say a run narrowed without saying where."""
    asker = _asker()
    hops = _three_hops()

    digests = chain_digests(asker, hops)

    assert digests == tuple(one.ent_hash() for one in chain_reaches(asker, hops))
    assert len(digests) == 4
    assert len(set(digests)) == 4


# ------------------------------------------------------------------ narrowing as a predicate
def test_narrows_admits_what_the_fold_produces():
    """The positive half. A guard tested only by its refusals is satisfied by a predicate
    that refuses everything, and this one is asked at every hop of every chain.

    Delete this and `narrows` could return False unconditionally while every refusal test
    below went on passing."""
    asker = _asker()
    hops = _three_hops()
    reaches = chain_reaches(asker, hops)

    assert narrowing_refusals(reaches[-1], reaches[0]) == ()
    assert narrows(reaches[-1], reaches[0])


def test_a_child_holding_a_capability_its_parent_does_not_is_refused():
    """The plain widening. Delete this and a delegation row could add a capability, which is
    the one thing an agent must never be able to do.

    Asserted on the branch's own sentence rather than on the capability name, and a mutation
    is the reason: with the capability check switched off, the scope comparison below it
    reports the same grant with a message about clauses, so a test looking only for the
    capability value passes against a version that no longer has the check at all."""
    parent = _reach("p-ana", NAME)
    child = _reach("p-ana", NAME, TICKET)

    refusals = narrowing_refusals(child, parent)

    assert len(refusals) == 1
    assert refusals[0].startswith(f"{TICKET} is held by the child and by no grant of the parent's")


def test_a_child_that_dropped_a_scope_clause_is_refused():
    """Scopes compose by conjunction only, so a lost clause is rows the parent could not
    see. The capability is identical in both, which is what makes this a different failure
    from the one above and not a duplicate of it.

    Delete this and a chain could keep every capability and quietly widen the rows each one
    reaches, which no capability comparison would notice."""
    parent = _reach("p-ana", NAME, scope=_scope(department="web"))
    child = _reach("p-ana", NAME)

    refusals = narrowing_refusals(child, parent)

    assert len(refusals) == 1
    assert "conjunction" in refusals[0]


def test_a_child_naming_a_different_principal_is_refused():
    """Two principals with identical grants share an `ent_hash` by design, so the hash
    cannot answer this and it is asked separately.

    Delete this and a delegation row could move a run onto somebody else's name while every
    capability and scope check passed, because the grants would be identical."""
    parent = _reach("p-ana", NAME)
    child = _reach("p-bob", NAME)

    refusals = narrowing_refusals(child, parent)

    assert len(refusals) == 1
    assert "p-bob" in refusals[0]


def test_a_child_that_outlives_its_parent_is_refused():
    """`intersect` takes the tighter of the two bounds, so a later expiry means the row was
    not produced by narrowing.

    Delete this and a time-boxed reach could be extended by delegation, which is a grant
    with a later expiry than the one it was cut from."""
    parent = EntitlementSet(
        principal_id="p-ana",
        grants=(Grant(capability=Capability(value=NAME), scope=Scope()),),
        not_after=NOW + timedelta(days=1),
    )
    child = EntitlementSet(
        principal_id="p-ana",
        grants=(Grant(capability=Capability(value=NAME), scope=Scope()),),
        not_after=NOW + timedelta(days=30),
    )

    refusals = narrowing_refusals(child, parent)

    assert len(refusals) == 1
    assert "outliving" in refusals[0]


def test_a_child_with_no_expiry_under_a_parent_with_one_is_refused():
    """The same rule in the shape it actually arrives in: not a later date, but the absence
    of one, which reads in a row as "no time bound" and is the widest possible answer.

    Delete this and dropping the field entirely would pass the comparison above, because
    None is not greater than anything."""
    parent = EntitlementSet(
        principal_id="p-ana",
        grants=(Grant(capability=Capability(value=NAME), scope=Scope()),),
        not_after=NOW + timedelta(days=1),
    )
    child = _reach("p-ana", NAME)

    assert not narrows(child, parent)


# ------------------------------------------------------------------ the chain's own shape
def test_a_chain_at_the_depth_cap_is_admitted_and_one_deeper_is_refused():
    """Both halves in one test, because the cap is a boundary and a test of only the refusal
    is satisfied by a cap of zero.

    Delete this and the depth cap could drift to any value without a failure, and the
    deepest legal chain is also the only one that exercises the fold's interior."""
    asker = _asker()
    at_the_cap = _three_hops()
    deeper = (*at_the_cap, _agent_hop("delta", NAME))

    assert depth_of(at_the_cap) == MAX_DELEGATION_DEPTH
    assert chain_refusals(asker, at_the_cap) == ()

    refusals = chain_refusals(asker, deeper)
    assert len(refusals) == 1
    assert "3 delegations deep" in refusals[0]


def test_a_chain_that_starts_at_a_subtask_is_refused():
    """A subtask ceiling with no agent to run it narrows nobody, and a chain starting at one
    reports a depth of zero however long it is.

    Delete this and a plan whose root agent went missing would fold correctly and count
    wrongly, so the depth cap would stop applying to it."""
    refusals = chain_refusals(_asker(), (_subtask_hop("s-1", NAME),))

    assert len(refusals) == 1
    assert "started through an agent" in refusals[0]


def test_two_adjacent_subtask_hops_are_refused():
    """The same defect one level down: a delegation between two subtask ceilings has gone
    missing, so the chain reports a lower depth than it has.

    Delete this and a chain could reach any depth by alternating in a way `depth_of` does
    not count."""
    hops = (
        _agent_hop("alpha", NAME),
        _subtask_hop("s-1", NAME),
        _subtask_hop("s-2", NAME),
    )

    refusals = chain_refusals(_asker(), hops)

    assert len(refusals) == 1
    assert "both subtasks and adjacent" in refusals[0]


def test_a_ceiling_without_its_prefix_cannot_be_a_hop():
    """A set whose principal id is a bare slug reads in a trace exactly like a person's, and
    the prefixes are `brain.agents.model`'s and `brain.orchestration.contract`'s rather than
    strings written here.

    Delete this and a ceiling could reach a trace looking like somebody's reach, which is
    the failure `AN_AGENT_CEILING_IS_NOT_A_PRINCIPAL` exists to prevent."""
    bare = EntitlementSet(
        principal_id="alpha",
        grants=(Grant(capability=Capability(value=NAME), scope=Scope()),),
    )

    with pytest.raises(DelegationError, match=CEILING_PRINCIPAL_PREFIX):
        Hop(lens_id="alpha", kind=LensKind.AGENT, ceiling=bare)

    subtask = subtask_ceiling(_contract("s-1", NAME))
    assert subtask.principal_id.startswith(SUBTASK_CEILING_PREFIX)
    with pytest.raises(DelegationError, match=CEILING_PRINCIPAL_PREFIX):
        Hop(lens_id="s-1", kind=LensKind.AGENT, ceiling=subtask)


def test_child_hops_refuses_a_subtask_dressed_as_an_agent_and_the_other_way_round():
    """The depth cap counts agent hops, so a subtask passed as the agent would let a chain
    report a depth it does not have while `depth_of` agreed with it.

    Delete this and the cap could be walked past by passing the two hops in the wrong
    positions, and every other check in this file would still pass."""
    parent = (_agent_hop("alpha", NAME),)

    with pytest.raises(DelegationError, match="depth cap"):
        child_hops(parent, agent=_subtask_hop("s-1", NAME), subtask=_subtask_hop("s-2", NAME))
    with pytest.raises(DelegationError, match="counted as"):
        child_hops(parent, agent=_agent_hop("beta", NAME), subtask=_agent_hop("gamma", NAME))


def test_depth_counts_agents_and_not_subtask_ceilings():
    """Stated on its own so a failure says what went wrong rather than handing a reader a
    chain to count by eye.

    Delete this and `depth_of` could start counting every hop, which halves the usable depth
    with no constant having changed."""
    hops = (
        _agent_hop("alpha", NAME),
        _subtask_hop("s-1", NAME),
        _agent_hop("beta", NAME),
        _subtask_hop("s-2", NAME),
    )

    assert depth_of(hops) == 1
    assert depth_of(()) == 0


# ---------------------------------------------------------------- concurrency and budget
def _delegation(run_id: str, child_id: str, *, depth: int = 1) -> Delegation:
    hops = [_agent_hop("alpha", NAME)]
    for level in range(depth):
        hops.append(_agent_hop(f"child-{level}", NAME))
        hops.append(_subtask_hop(f"s-{child_id}-{level}", NAME))
    return Delegation(run_id=run_id, child_id=child_id, hops=tuple(hops))


def test_the_per_run_cap_is_exactly_the_background_share_of_the_global_budget():
    """**The per-run cap is pinned against something outside itself.**

    Eight is not a number chosen here: `brain.ops.admission` gives long-running tasks a
    limit of ten and caps the background class at four fifths of any budget, which floors to
    eight. So one run at full fan-out fills the whole background share.

    Delete this and `MAX_CHILDREN_PER_RUN` becomes a free constant, and moving it would
    change how many children a run may start without changing anything about the machine
    they run on. Every test that compares a count against the constant would move with
    it."""
    rows = [one for one in seed_budgets() if one.budget_key == (PARALLELISM_RESOURCE, "")]

    assert len(rows) == 1
    assert rows[0].resource is Resource.LONG_RUNNING_TASKS
    assert rows[0].ceiling_for(WorkloadClass.BACKGROUND) == MAX_CHILDREN_PER_RUN
    assert global_ceiling(seed_budgets()) == MAX_CHILDREN_PER_RUN


def test_a_run_may_start_the_cap_and_not_one_more():
    """Both halves, because a refusal test alone is satisfied by refusing everything.

    Delete this and the per-run cap could be off by one in either direction, and the
    direction nobody notices is the permissive one."""
    at_the_cap = [_delegation("r-1", f"c-{i}") for i in range(MAX_CHILDREN_PER_RUN)]
    over = [*at_the_cap, _delegation("r-1", "c-extra")]

    assert concurrency_refusals(at_the_cap) == ()

    refusals = concurrency_refusals(over)
    assert len(refusals) == 1
    assert "would start 9 children" in refusals[0]


def test_children_of_two_runs_are_counted_against_their_own_run():
    """The cap is per run, so sixteen children across two runs is two full fan-outs and not
    one refusal.

    Delete this and the check could start counting the whole list, which would refuse a
    legitimate second run, or start counting only the first run in it, which is how a caller
    holding a mixed list satisfies a per-run cap by passing everything at once."""
    mixed = [_delegation("r-1", f"a-{i}") for i in range(MAX_CHILDREN_PER_RUN)] + [
        _delegation("r-2", f"b-{i}") for i in range(MAX_CHILDREN_PER_RUN)
    ]

    assert concurrency_refusals(mixed) == ()

    mixed.append(_delegation("r-2", "b-extra"))
    refusals = concurrency_refusals(mixed)
    assert len(refusals) == 1
    assert "'r-2'" in refusals[0]


def test_a_child_deeper_than_the_cap_is_refused_by_the_concurrency_check_too():
    """The depth cap applies to every child in a fan-out and not only to the chain being
    folded, because the two are checked at different moments and a fan-out at the cap
    produces children past it.

    Delete this and a run could dispatch a legal number of illegal children."""
    deep = [_delegation("r-1", "c-1", depth=MAX_DELEGATION_DEPTH + 1)]

    refusals = concurrency_refusals(deep)

    assert len(refusals) == 1
    assert "delegations deep" in refusals[0]


def test_a_fan_out_asks_for_every_child_at_once():
    """Admitted one at a time, a fan-out of eight against two free slots starts two children
    and discovers there is no room for the rest, which the merge step cannot tell apart from
    six subtasks that failed.

    Delete this and the request could quietly become one unit, and a fan-out would half
    happen under load rather than being refused."""
    request = fan_out_request("r-1", children=5, traffic_class=TrafficClass.HUMAN_INTERACTIVE)

    assert request.units == 5
    assert request.resource is PARALLELISM_RESOURCE
    assert request.workload_class is WorkloadClass.BACKGROUND


def test_a_fan_out_past_the_per_run_cap_is_refused_before_admission_is_asked():
    """Admission is asked after the cap, never instead of it: a global budget with room
    would otherwise admit a run of twenty children.

    Delete this and the per-run cap would be enforced only by whoever remembered to call
    `concurrency_refusals` first."""
    with pytest.raises(DelegationError, match="per-run cap"):
        fan_out_request(
            "r-1",
            children=MAX_CHILDREN_PER_RUN + 1,
            traffic_class=TrafficClass.HUMAN_INTERACTIVE,
        )
    with pytest.raises(DelegationError, match="not a fan-out"):
        fan_out_request("r-1", children=0, traffic_class=TrafficClass.HUMAN_INTERACTIVE)


def test_a_second_run_is_queued_behind_the_first_at_full_fan_out():
    """The arithmetic section 25 states in words, asserted against the real budgets: one run
    at eight children fills the background share, so the next run's first child does not
    start.

    Nobody is waiting on a task-lane run, so it is queued rather than shed, which is the
    other half of the same rule. Delete this and the global budget could stop applying to
    fan-out without any counter changing."""
    budgets = seed_budgets()
    request = fan_out_request("r-2", children=1, traffic_class=TrafficClass.HUMAN_INTERACTIVE)
    full = CapacityState(used={(PARALLELISM_RESOURCE, ""): MAX_CHILDREN_PER_RUN})

    busy = may_fan_out(request, budgets, full, now=NOW)
    idle = may_fan_out(request, budgets, CapacityState(), now=NOW)

    assert busy.verdict is Verdict.QUEUED
    assert idle.verdict is Verdict.ADMITTED


# ----------------------------------------------------------- no grant verb, no intersection
@pytest.mark.parametrize("blank", ["", " "])
def test_a_hop_naming_no_lens_is_refused(blank):
    """A hop nobody can name cannot be recorded, audited or explained afterwards, and a
    chain of them is a narrowing whose steps have no story.

    Whitespace as well as the empty string, because a strip-free check admits a space and a
    lens called " " reads on a screen as a lens with a name.

    Delete this and a chain could fold correctly and be unexplainable, which is the state
    the digests exist to prevent."""
    with pytest.raises(DelegationError, match="naming no lens"):
        Hop(
            lens_id=blank,
            kind=LensKind.AGENT,
            ceiling=EntitlementSet(principal_id=f"{CEILING_PRINCIPAL_PREFIX}alpha"),
        )


@pytest.mark.parametrize("blank", ["", " "])
def test_a_delegation_naming_no_run_or_child_is_refused(blank):
    """A child with no run cannot be counted against the per-run cap, and one with no id
    cannot be attributed in a trace.

    Whitespace as well as the empty string, for the same reason as above.

    Delete this and `concurrency_refusals` would group every unnamed child under one empty
    run id, which either refuses a legitimate fan-out or admits an illegal one depending on
    how many there are."""
    with pytest.raises(DelegationError, match="cannot be counted against a cap"):
        Delegation(run_id=blank, child_id="c-1", hops=(_agent_hop("alpha", NAME),))
    with pytest.raises(DelegationError, match="cannot be counted against a cap"):
        Delegation(run_id="r-1", child_id=blank, hops=(_agent_hop("alpha", NAME),))


def test_a_delegation_with_no_lens_on_it_is_refused():
    """It would run at the asker's own reach, and the agent it was delegated through would
    have narrowed nothing, which is the widening this whole module exists to prevent
    arriving as an empty tuple rather than as a bad fold.

    Delete this and a child built with no hops would be indistinguishable from the asker
    acting directly, and `chain_reach` would agree with it."""
    with pytest.raises(DelegationError, match="no lens on it"):
        Delegation(run_id="r-1", child_id="c-1", hops=())


def test_a_fan_out_against_an_unbudgeted_resource_is_refused():
    """An unbudgeted resource is the failure global budgets exist to prevent, so a missing
    row is refused rather than read as an unlimited one.

    Delete this and an install whose budget table had not been seeded would fan out without
    limit, and the absence of a row would read as permission."""
    assert global_ceiling(seed_budgets()) == MAX_CHILDREN_PER_RUN

    with pytest.raises(DelegationError, match="unbudgeted resource"):
        global_ceiling(
            [one for one in seed_budgets() if one.resource is not Resource.LONG_RUNNING_TASKS]
        )


def test_a_producer_of_reach_with_no_arguments_at_all_is_reported():
    """The other half of the grant-verb check: a function returning an `EntitlementSet` and
    taking nothing is producing reach out of nothing, which is the widest possible grant
    verb and the one a signature check would miss if it only compared annotations.

    Delete this and a zero-argument reach factory would pass, because there would be no
    first argument to compare against."""
    findings = grant_verbs_in(
        "\n".join(
            (
                "from brain.core.entitlement import EntitlementSet",
                "",
                "def everything() -> EntitlementSet:",
                '    return EntitlementSet(principal_id="root")',
            )
        )
    )

    assert len(findings) == 1
    assert "takes no annotated first argument" in findings[0]


def test_no_module_in_this_package_produces_reach_from_something_that_is_not_reach():
    """M18.3.3 asserted over the package rather than promised in a docstring.

    Delete this and a function returning an `EntitlementSet` built from a contract, a
    string or nothing at all would read as reasonable in whichever file it appeared in, and
    the orchestrator would have a grant verb."""
    found = {
        path.name: grant_verbs_in(path.read_text(encoding="utf-8"))
        for path in sorted(PACKAGE.glob("*.py"))
    }

    assert len(found) >= 6
    assert all(not one for one in found.values()), found


def test_grant_verbs_in_reports_a_module_that_does_confer():
    """The positive half, and the reason the check takes source rather than reading the
    package: a diagnostic that can only be run against the healthy tree cannot be shown to
    fail, and every one of its refusals survives a mutation.

    Delete this and `grant_verbs_in` could return an empty tuple unconditionally while the
    test above went on passing."""
    conferring = (
        "from brain.core.entitlement import Capability, EntitlementSet, Grant\n"
        "\n"
        "def widen(subtask_id: str) -> EntitlementSet:\n"
        "    return EntitlementSet(\n"
        "        principal_id=subtask_id,\n"
        '        grants=(Grant(capability=Capability(value="admin:everything"), scope=None),),\n'
        "    )\n"
    )

    findings = grant_verbs_in(conferring)

    assert len(findings) == 2
    assert any("widen returns a EntitlementSet" in one for one in findings)
    assert any("Grant is constructed at widen" in one for one in findings)


def test_a_module_level_grant_is_reported_as_a_standing_one():
    """A `Grant` at module level is a standing grant nobody can revoke, because revocation
    here is the deletion of a row and there is no row.

    Delete this and a constant grant would be invisible to the check, which only walks
    functions for the first half of its work."""
    findings = grant_verbs_in(
        "from brain.core.entitlement import Capability, Grant\n"
        'ALWAYS = Grant(capability=Capability(value="admin:everything"), scope=None)\n'
    )

    assert len(findings) == 1
    assert "module level" in findings[0]


def test_the_exemption_for_a_ceiling_producer_is_named_and_can_be_removed():
    """The exemption is a parameter rather than a literal, so the finding it suppresses can
    be seen.

    Delete this and `CEILING_PRODUCERS` could grow to cover any function somebody wanted the
    check to stop reporting, and nothing would show what was being exempted."""
    source = (PACKAGE / "contract.py").read_text(encoding="utf-8")

    assert grant_verbs_in(source) == ()

    unexempted = grant_verbs_in(source, producers=frozenset())
    assert len(unexempted) == 2
    assert any("subtask_ceiling" in one for one in unexempted)


def test_no_module_in_this_package_intersects_anything_itself():
    """The rule `tests/invariants/test_single_implementation.py` pins across the whole
    source, asserted here as well because this package is the one most likely to grow a
    second implementation: everything in it is about composing reach.

    `brain.console.workspace.intersections_in` rather than a scan written here, for the same
    reason nothing in this package computes its own intersection.

    Delete this and the first failure would be in the invariant suite, which reports the new
    call site without saying why an orchestration module in particular must not have one."""
    for path in sorted(PACKAGE.glob("*.py")):
        assert intersections_in(path.read_text(encoding="utf-8")) == (), path.name


def test_every_module_in_this_package_ends_its_docstring_with_task_ids():
    """The house rule, asserted for the package rather than left to the traceability sweep,
    which reads commits and therefore says nothing until something is committed.

    Delete this and a module could ship claiming nothing, which the sweep reports as an
    untraceable file long after the commit that should have carried the ids."""
    for path in sorted(PACKAGE.glob("*.py")):
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
        assert docstring, path.name
        if path.name == "__init__.py":
            continue
        lines = [one for one in docstring.splitlines() if one.startswith("Task ids:")]
        assert lines, path.name
        for line in lines:
            assert len(line) < 100, (path.name, line)
            assert not line.rstrip().endswith(","), (path.name, line)
