"""When agent A calls agent B, whose reach does B run at.

The answer is the only one that keeps the platform's invariant true, and it is not the one
the question suggests. **B runs at the person's reach, narrowed by every lens on the path
from the person to B, in that order.** Not A's ceiling, not B's ceiling, and not the
person's raw reach.

The reason is that A is not a caller. `E_run(caller, agent) = E(caller) intersect
agent_ceiling` reads as though the caller of B were A, and A has no grants to be the
left-hand side of anything: `brain.agents.model.AN_AGENT_CEILING_IS_NOT_A_PRINCIPAL` says
so, and `EntitlementSet.intersect` proves it by keeping `self.principal_id`, so what comes
out of the first hop is still the asker's set. What calls B is therefore **the run**, whose
reach is `E(P) intersect ceiling(A)`, and B's reach is that intersected with `ceiling(B)`.
Written out for a chain:

    R0 = E(P)
    Rn = R(n-1) intersect ceiling(n)

which is a left fold, and `chain_reaches` is that fold and nothing else. See
`AN_AGENT_IS_NEVER_THE_CALLER`.

**Every hop can only reduce, and a hop that restored anything would make an agent a way to
launder a reach.** Intersection is decreasing, so R0 contains R1 contains R2 and so on for
as long as the chain runs. That is not a nicety. If a hop could restore, then giving agent
B a wide ceiling and having a narrow agent A call it would hand the run more than A had,
and installing an agent would have become a grant. Installing an agent is a configuration
change made by whoever can edit agents; granting is a change to somebody's entitlements
made by whoever can grant. Those are different acts with different approvals, and a
laundering path collapses them. `narrows` is the property stated as a predicate, and
`chain_refusals` refuses a chain that fails it.

**A chain of two has no interior, which is why the tests here run three.** This is the
specific trap and it is easy to walk into. An implementation that folds only the first and
the last ceiling and drops everything between them is *correct at two hops*, because with
two hops the first and the last are all of them. It is wrong from three, where the middle
lens is the one dropped, and wrong in the widening direction: the run comes out holding
what the middle agent's ceiling was there to take away. The same is true of an
implementation that narrows once and then carries the result forward. So the tests fold a
chain of three and compare against the two-hop prefix, and
`A_CHAIN_OF_TWO_HAS_NO_INTERIOR` records why a pair proves nothing.

**Nothing here intersects anything.** Every hop goes through
`brain.ops.automation.flow_reach`, which is the one wrapper over the one
`EntitlementSet.intersect`. It is named for a flow rather than for an agent, and it is
still the right function: what makes it the right one is that it is the single call site
this repository sanctions for a run reach, and giving orchestration a second wrapper called
`agent_reach` would be a second name for one rule and the beginning of a second
implementation. `tests/invariants/test_single_implementation.py` pins every `intersect`
call site in `src/brain` exactly, and this package appears in none of them.

**The orchestrator has no grant verb, and that is checked rather than promised.**
`grant_verbs_in` reads a module's source and reports every function that produces an
`EntitlementSet` from something that is not one, and every `Grant` constructed outside a
named ceiling producer. A ceiling producer is the exception and it is the one that has to
exist: a ceiling is the right-hand side of the intersection, it confers nothing, and its
principal id is prefixed so it cannot be read anywhere as a person. Everything else in this
package takes a reach and hands back a smaller one.

**Depth two and concurrency eight are not independent numbers, and one of them is not ours
at all.** `MAX_CHILDREN_PER_RUN` is eight, and `brain.ops.admission` gives
`Resource.LONG_RUNNING_TASKS` a limit of ten with `WorkloadClass.BACKGROUND` capped at
four fifths of it, which floors to exactly eight. So one run at full fan-out occupies the
whole background share of the global budget and a second run's first child is queued
behind it. That is the arithmetic architecture section 25 states in words: twenty users
each running eight subtasks is a hundred and sixty concurrent operations against a machine
sized for ten. The per-run cap is therefore pinned in the test suite against the global
budget rather than against itself, and `may_fan_out` asks `brain.ops.admission.decide`
rather than counting anything here. A second counter would be the failure that module
exists to prevent.

**Nothing here is a runtime.** `brain.gate.leash` says the same of itself and it is truer
here: there is no agent loop in this repository, and `brain.ops.checkpoints` says there is
no graph and no saver. The queue used to be third on that list and was struck off on
2026-09-11, when M32.4.1.1 installed a driver: there is now somewhere to run a child, and
still nothing that would be running. So no chain computed here has ever been the reach of
anything that
ran. What is here is the rule a runtime will have to obey and the checks that say whether
it does, which is the same standing `checkpoint_refusals` has and is worth saying plainly
rather than leaving to be discovered.

**This module refused M18.3.1 and M18.3.2 until 2026-09-11, and the refusal is now spent.**
It read the single-implementation rule as forbidding any second computation of the central
rule, and on those terms it was right to refuse: a second implementation of a reach a run
is *executed at* is a second place for the rule to be subtly wrong, and the wrong copy is
the one in production.

What `brain.core.scope_sql.delegated_reach` builds is not that, and the distinction is
worth stating precisely because it is the only thing keeping it legitimate. **Its sole
consumer is a refusal.** No run is executed at the reach it computes, no caller receives
it, and `EntitlementSet.intersect` remains the one implementation anything acts on. The
failure modes are asymmetric in the safe direction: narrower than Python refuses a row that
should have been recorded, which is loud; wider admits a row the Python path had already
checked, which is where the system stood before the trigger existed.

Silent drift between the two is the thing that would matter, so they are measured against
each other rather than argued about: seventeen differential cases fold the same three sets
through `intersect` twice and through the SQL once and compare by meaning, against a live
server, in `tests/unit/test_delegation_sql.py`. There were ten until 2026-09-14, when seven
chains holding a wildcard on the parent's side were added with the repair to `intersect`,
together with one test comparing the SQL against a reach written out by hand, because a
comparison of two copies cannot see a defect both of them share.

**Since 2026-09-14 the SQL containment check is no longer this module's check in SQL.**
`narrowing_refusals` below now asks both sides through `scope_for`, and
`gate.narrowing_refusals` in `brain.core.scope_sql` still matches grants on the capability
string. Measured on a live server that day, it admits a row holding `read:client.*` in Web
beneath a reach whose `read:client.name` is Web and gold, and that row reaches the name column
in every tier. It is recorded here and not repaired here, because that module is not this
change's.

The other half of the old refusal was real and has been answered rather than waived. There
was no row to hang a trigger on; migration `0028` creates `gate.delegation`, and the trigger
catches what this module cannot: a row below the root has no column in which to state its
own parent reach, so it is measured against what its parent row recorded, and every UPDATE
is refused because otherwise widening is two statements. What the database still cannot
confirm is the root row's own `parent_grants`, which is the asker's reach and is as true as
its writer; `scope_sql` says so in its own docstring rather than implying more.

Rejected: a `depth` field on the chain. It is derivable from the hops and a stored copy is
a second fact that can disagree with the first, which is
`brain.ops.jobs.SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE` read at a different scale.

Rejected: letting a hop carry `None` for a ceiling to mean it narrows nothing. There is no
entitlement set meaning everything, so `None` would have to mean "skip this intersection",
and a skipped intersection is exactly the hop that restores.

Task ids: M18.3.3, M18.3.4, M18.3.5
"""

from __future__ import annotations

import ast
import enum
import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.model import CEILING_PRINCIPAL_PREFIX
from brain.core.entitlement import EntitlementSet
from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.ops.admission import (
    AdmissionDecision,
    AdmissionRequest,
    Budget,
    CapacityState,
    Resource,
    WorkloadClass,
)
from brain.ops.admission import (
    decide as admission_decide,
)
from brain.ops.automation import flow_reach
from brain.ops.halt import NOTHING_HALTED, HaltState
from brain.orchestration.contract import SUBTASK_CEILING_PREFIX

# ------------------------------------------------------------------ written-down reasons
#: Whose reach a delegated run holds, and why the answer is not the caller agent's.
AN_AGENT_IS_NEVER_THE_CALLER: Final = (
    "E_run(caller, agent) = E(caller) intersect agent_ceiling reads as though the caller of "
    "agent B were agent A, and A has no grants to be the left-hand side of anything: an "
    "agent ceiling is not a principal's reach and confers nothing. What calls B is the run, "
    "and EntitlementSet.intersect keeps the caller's principal id, so the run is still the "
    "asker's. B therefore runs at the asker's reach narrowed by every lens between the "
    "asker and B, in order. Not A's ceiling, which belongs to nobody; not B's ceiling, for "
    "the same reason; and not the asker's raw reach, because then A would have narrowed "
    "nothing and delegation would be the way round every ceiling on the path."
)

#: Why the fold can only ever reduce, and what a restoring hop would buy an attacker.
EVERY_HOP_ONLY_NARROWS: Final = (
    "Intersection is decreasing, so the reach at each hop is contained in the reach at the "
    "one before it and the whole chain is a descending sequence. A hop that restored "
    "anything would make delegation a laundering route: give agent B a wide ceiling, have "
    "narrow agent A call it, and the run comes out holding what A's ceiling was there to "
    "remove. Installing an agent would then be a grant, and installing an agent is a "
    "configuration change while granting is a change to somebody's entitlements. The two "
    "have different approvers, and a restoring hop collapses them into one."
)

#: How containment is asked, and the two cheaper readings that are each wrong one way.
CONTAINMENT_IS_ASKED_OF_BOTH_SIDES: Final = (
    "A child is contained in its parent when, for every capability either of them names, the "
    "child reaches it only where the parent does, each side's reach read through scope_for. "
    "That is the reading intersect gives a set, so what a fold produces is never refused. "
    "Matching grants on the capability string refuses a wildcard caller's run the moment a "
    "ceiling names a column, because the run holds the column and the caller holds no grant "
    "equal to it. Walking only the child's grants admits a child that kept the parent's "
    "wildcard and left out the narrower column grant beneath it, and that child reaches the "
    "column wherever the wildcard does."
)

#: Why a pair of hops is not enough to test the fold.
A_CHAIN_OF_TWO_HAS_NO_INTERIOR: Final = (
    "An implementation that folds the first and the last ceiling and drops everything "
    "between them is correct at two hops, because at two hops the first and the last are "
    "all of them. It is wrong from three, and wrong in the widening direction: the dropped "
    "lens is the one whose ceiling was going to take something away. The same holds for an "
    "implementation that narrows once and carries the result forward. A pair therefore "
    "proves nothing about a fold, and every test of the chain here runs three hops, which "
    "is also the deepest chain the depth cap admits."
)

#: Why there is no verb here that hands a run more than it arrived with.
THE_ORCHESTRATOR_HAS_NO_GRANT_VERB: Final = (
    "Every function in this package that produces a reach takes a reach as its first "
    "argument and returns something contained in it. The exceptions are the ceiling "
    "producers, which build the right-hand side of the intersection: a ceiling confers "
    "nothing, is only ever the second argument, and carries a prefixed principal id so it "
    "cannot be read in a trace as a person. grant_verbs_in checks both halves against a "
    "module's own source, because a rule that lives in a docstring is defeated by one "
    "function somebody adds underneath it."
)

#: Why the per-run cap is eight and where the number comes from.
EIGHT_IS_THE_BACKGROUND_SHARE_OF_THE_GLOBAL_BUDGET: Final = (
    "brain.ops.admission gives Resource.LONG_RUNNING_TASKS a limit of ten, from section "
    "25's machine sized for ten, and caps WorkloadClass.BACKGROUND at four fifths of any "
    "budget, which floors to eight. So a per-run cap of eight is exactly the whole "
    "background share: one run at full fan-out fills it and the next run's first child is "
    "queued. The number is therefore pinned against the global budget rather than chosen "
    "beside it, and the admission decision is asked of brain.ops.admission.decide rather "
    "than counted here, because a second counter is the failure global budgets exist to "
    "prevent."
)


class DelegationError(Exception):
    """A chain, a hop or a delegation row that cannot mean what it says.

    Outside the `brain.core.errors` taxonomy, like `brain.agents.model.AgentError`: those
    five outcomes describe an answer given to a person, and this is a refusal to start a
    child. Nobody asking a question ever sees one.
    """


# --------------------------------------------------------------------------- the chain
class LensKind(enum.StrEnum):
    """What kind of narrowing one hop is.

    Two members and no third. An agent is a configured lens with an owner and a ceiling; a
    subtask is a per-run lens built from a contract. Both narrow and neither grants, and
    they are told apart because a trace that cannot say which of the two took a capability
    away sends whoever is reading it to the wrong screen.
    """

    AGENT = "agent"
    SUBTASK = "subtask"


#: The principal-id prefix a ceiling of each kind must carry, so that a set which is a
#: ceiling can never be read as a person. Both are imported from the module that produces
#: them rather than restated, because a prefix written twice is a prefix that drifts and
#: the drifted copy is the one that lets a ceiling into a trace looking like somebody.
CEILING_PREFIX: Final[dict[LensKind, str]] = {
    LensKind.AGENT: CEILING_PRINCIPAL_PREFIX,
    LensKind.SUBTASK: SUBTASK_CEILING_PREFIX,
}


@dataclass(frozen=True)
class Hop:
    """One lens on the path from the person to the work.

    Frozen, because the chain is folded once to decide what a child may reach and again to
    record what it ran at, and a hop that could change between the two would produce a run
    nobody can reconstruct.

    There is no `reach` field and nowhere to put one. A hop carries a ceiling, and the reach
    is what comes out of folding the ceilings over the caller's set. Storing the reach on
    the hop would be storing a permission decision beside the thing it was decided from,
    which is what `brain.ops.jobs.A_JOB_CARRIES_A_PRINCIPAL_AND_NEVER_A_REACH` refuses for a
    queue row and is refused here for the same reason.
    """

    lens_id: str
    kind: LensKind
    ceiling: EntitlementSet

    def __post_init__(self) -> None:
        if not self.lens_id.strip():
            msg = "a hop naming no lens cannot be recorded, audited or explained afterwards"
            raise DelegationError(msg)
        expected = CEILING_PREFIX[self.kind]
        if not self.ceiling.principal_id.startswith(expected):
            msg = (
                f"hop {self.lens_id!r} carries a {self.kind} ceiling whose principal id is "
                f"{self.ceiling.principal_id!r}, which does not start with {expected!r}; a "
                "ceiling that reaches a trace without its prefix reads there as a person"
            )
            raise DelegationError(msg)


#: How many delegation hops may sit below the run the person started. The root run is depth
#: zero, so a cap of two admits person to agent to child to grandchild and nothing further.
#: Architecture section 14 states it as "depth 2" and the cost of a third level is not
#: arithmetic: it is that nobody reading a trace can say which of four lenses removed the
#: capability the answer turned out to need.
MAX_DELEGATION_DEPTH: Final = 2

#: How many children one run may have in flight. See
#: `EIGHT_IS_THE_BACKGROUND_SHARE_OF_THE_GLOBAL_BUDGET`; the figure is pinned against
#: `brain.ops.admission` in the test suite rather than asserted here.
MAX_CHILDREN_PER_RUN: Final = 8

#: The global budget a fan-out spends. Named rather than passed, because a caller free to
#: choose which budget their children count against is a caller who can find an empty one.
PARALLELISM_RESOURCE: Final[Resource] = Resource.LONG_RUNNING_TASKS


def depth_of(hops: Sequence[Hop]) -> int:
    """How many delegations deep this chain is. The root run is zero.

    Counted from the agent hops, because a subtask ceiling narrows the same run rather than
    starting a new one: `parent intersect agent intersect subtask` is one delegation with
    two ceilings on it, not two delegations. Derived rather than stored, so there is one
    fact rather than two that can disagree.
    """
    return max(0, sum(1 for hop in hops if hop.kind is LensKind.AGENT) - 1)


def chain_reaches(caller: EntitlementSet, hops: Sequence[Hop]) -> tuple[EntitlementSet, ...]:
    """The reach at every point on the chain, starting with the caller's own.

    A left fold of `brain.ops.automation.flow_reach`, which is the one wrapper over the one
    `EntitlementSet.intersect`. The whole sequence is returned rather than only the last
    one, and that is deliberate twice over: an auditor asking which lens removed a
    capability needs the intermediate sets, and a test asserting that the chain descends
    needs every step of it rather than the endpoints.

    Length is `len(hops) + 1`. Index zero is the caller, index n is the reach after n hops.
    """
    reaches: list[EntitlementSet] = [caller]
    for hop in hops:
        reaches.append(flow_reach(reaches[-1], hop.ceiling))
    return tuple(reaches)


def chain_reach(caller: EntitlementSet, hops: Sequence[Hop]) -> EntitlementSet:
    """What the far end of this chain may reach. The last element of `chain_reaches`.

    An empty chain returns the caller's own set, which is right and is worth stating: a run
    with no lens on it is the person acting as themselves, and inventing a narrowing for
    that case would be this module deciding a policy nobody asked it for. What refuses an
    empty chain, if anything should, is `chain_refusals`, where the refusal is visible.
    """
    return chain_reaches(caller, hops)[-1]


def chain_digests(caller: EntitlementSet, hops: Sequence[Hop]) -> tuple[str, ...]:
    """The hash of the reach at every point on the chain, for an audit row.

    `EntitlementSet.ent_hash` rather than the sets themselves, for the reason
    `brain.gate.leash.Decision` carries a hash: a record of what a run could reach is a copy
    of somebody's permissions with its own retention, and the hash answers the only question
    an audit asks of it, which is whether it is the same reach as the one before.
    """
    return tuple(reach.ent_hash() for reach in chain_reaches(caller, hops))


# ------------------------------------------------------------- narrowing, as a predicate
def narrowing_refusals(child: EntitlementSet, parent: EntitlementSet) -> tuple[str, ...]:
    """Every way this child's reach is not contained in its parent's.

    Four checks, and each catches a different way a delegation row could widen.

    **The principal must not change.** `intersect` keeps the caller's principal id, so a
    child naming a different one was not produced by narrowing anybody's reach. Two people
    with identical grants share an `ent_hash` by design, which is what makes the cache key
    work, so the hash cannot answer this and it is asked separately; that is the same
    argument `brain.gate.leash.resume` makes about its own identity check.

    **Every capability the child reaches, the parent reaches.** Asked of both sides through
    `EntitlementSet.scope_for`, for every capability either set names, with both bounds set
    aside. That is the question `intersect` asks, so a child is judged by the same reading of
    a set that produced it. Asking only about the capabilities the child names is not enough:
    a child can keep a parent's `read:client.*` in Web and leave out the parent's
    `read:client.name` in gold, and it then reaches the name column in every tier. Asking
    about every capability either side names is enough, because the grants covering any
    capability are exactly the grants covering the most specific named capability above it.
    See `CONTAINMENT_IS_ASKED_OF_BOTH_SIDES`.

    **The scope must not have lost a clause.** Scopes compose by conjunction only, so more
    clauses is narrower, and a child whose clauses on a capability are a superset of the
    parent's clauses there has narrowed. This is a sufficient condition and not a necessary
    one: a child could be narrower in meaning with different clauses, and this would refuse
    it. That is the right direction for a refusal, and it is worth saying out loud rather
    than leaving somebody to discover it by having a legitimate row rejected.

    **Until 2026-09-14 this matched each child grant to the parent's grants on the
    capability's own value**, and argued against `scope_for`: a parent holding both
    `read:client.*` and `read:client.name` would be compared against a conjunction of scopes
    no single child grant was built from, and "grant for grant is exact for anything
    `flow_reach` produced". Both halves were true of the `intersect` of that day, which read a
    run's grants off the caller alone and took each scope from the one grant being walked.
    Neither is true of the repaired one. The run holds the column wherever a ceiling names it,
    so a parent's wildcard has no equal grant to be matched against, and its scope there is
    the parent's `scope_for` conjoined with the ceiling's, which carries every clause of that
    conjunction. Left as it was, the check reported a correct narrowing as a widening:
    `chain_refusals` refused `u_aaron`, `u_rupash`, `u_siti` and `u_expired` in
    `tests/fixtures/company.py` through the capacity analyst's installed ceiling. What survives
    of the old argument is the clause test and its direction, which are unchanged.

    Measured that day over every child and parent drawn from the sets of at most two grants
    `tests/invariants/test_entitlement_invariants.py` uses, 6,241 pairs, against a
    containment written out capability by capability, and over the narrowings `intersect`
    produces from the same sets, 6,241 at one hop and 409,968 at a second:
    - exact matching, as before: 1,449 and 35,991 of those narrowings refused, and against
      the written-out containment 64 widenings admitted and 670 containments refused;
    - `Capability.covers` with clause containment, per child grant: no narrowing refused,
      and 236 widenings admitted, because the clauses of one covering grant are not every
      clause the parent reaches a column under;
    - `scope_for`, per child grant: no narrowing refused, and 44 widenings admitted, which
      are the child leaving out a narrower grant;
    - `scope_for` asked of both sides, which is what this is: none refused and none admitted.
    Rejected, then, are the first three, and the fourth is the only one exact in both
    directions over that universe.

    **The time bound must not have moved out.** `intersect` takes the tighter of the two, so
    a child outliving its parent is a child that was not produced by one.
    """
    findings: list[str] = []
    if child.principal_id != parent.principal_id:
        findings.append(
            f"the child names principal {child.principal_id!r} and the parent names "
            f"{parent.principal_id!r}; narrowing keeps the caller's id, so this row was not "
            "produced by narrowing that caller's reach"
        )
    # See `CONTAINMENT_IS_ASKED_OF_BOTH_SIDES`. Both bounds are set aside for the question,
    # because expiry is the fourth check's to judge, and `scope_for` would otherwise judge it
    # against the wall clock and make a refusal depend on when somebody asked.
    reaching = child.model_copy(update={"not_after": None})
    reachable = parent.model_copy(update={"not_after": None})
    for capability in dict.fromkeys(g.capability for g in (*child.grants, *parent.grants)):
        held = reaching.scope_for(capability)
        if held is None:
            continue
        allowed = reachable.scope_for(capability)
        if allowed is None:
            findings.append(
                f"{capability.value} is held by the child and by no grant of the "
                f"parent's. {EVERY_HOP_ONLY_NARROWS}"
            )
            continue
        if not set(allowed.clauses) <= set(held.clauses):
            findings.append(
                f"{capability.value} is reached by the child without every clause the "
                "parent reaches it under, and scopes compose by conjunction only, so a "
                "dropped clause is rows the parent could not see"
            )
    if parent.not_after is not None and (
        child.not_after is None or child.not_after > parent.not_after
    ):
        findings.append(
            f"the child expires at {child.not_after} and the parent at {parent.not_after}; "
            "a delegated run outliving the reach it came from is a grant with a later "
            "expiry than the one it was cut from"
        )
    return tuple(findings)


def narrows(child: EntitlementSet, parent: EntitlementSet) -> bool:
    """Whether this child's reach is contained in its parent's. See `narrowing_refusals`."""
    return not narrowing_refusals(child, parent)


def chain_refusals(caller: EntitlementSet, hops: Sequence[Hop]) -> tuple[str, ...]:
    """Every reason this chain may not be run, in the order a reader wants them.

    Returns all of them rather than the first, matching `brain.ops.queue.queue_url_refusals`:
    a plan wrong in three ways should say so once.

    The structural checks come before the arithmetic one because they say what the chain is.
    A chain that does not start at an agent is not a run at all: a person's question is
    answered through an agent, and a subtask ceiling with nothing to run it is a narrowing
    of nobody. Two subtask hops in a row are the same defect one level down, a plan whose
    middle agent went missing between being proposed and being folded.

    The descent check is last and is the one that should never fire, because `chain_reaches`
    folds `flow_reach` and `flow_reach` cannot widen. It is asked anyway, of the sets rather
    than of the code that made them, because that is the difference between a property and a
    comment: an implementation swapped underneath this would be caught here rather than by
    somebody reading a diff.
    """
    findings: list[str] = []
    if hops and hops[0].kind is not LensKind.AGENT:
        findings.append(
            f"the chain starts at {hops[0].lens_id!r}, which is a {hops[0].kind}; a run is "
            "started through an agent, and a subtask ceiling with no agent to run it "
            "narrows nobody"
        )
    for earlier, later in itertools.pairwise(hops):
        if earlier.kind is LensKind.SUBTASK and later.kind is LensKind.SUBTASK:
            findings.append(
                f"{earlier.lens_id!r} and {later.lens_id!r} are both subtasks and adjacent, "
                "so a delegation between them has gone missing and the depth this chain "
                "reports is lower than the one it has"
            )
    depth = depth_of(hops)
    if depth > MAX_DELEGATION_DEPTH:
        findings.append(
            f"this chain is {depth} delegations deep and the cap is {MAX_DELEGATION_DEPTH}; "
            "past it nobody reading a trace can say which lens removed the capability the "
            "answer turned out to need"
        )
    reaches = chain_reaches(caller, hops)
    for index, (wider, narrower) in enumerate(itertools.pairwise(reaches)):
        findings.extend(
            f"hop {index} ({hops[index].lens_id!r}) did not narrow: {reason}"
            for reason in narrowing_refusals(narrower, wider)
        )
    return tuple(findings)


# --------------------------------------------------------- the child (M18.3.4, M18.3.5)
@dataclass(frozen=True)
class Delegation:
    """One child run: which chain it sits on, and what it may reach at the end of it.

    Carries the chain rather than a reach, and computes the reach on demand. A stored reach
    would be a permission decision written down and executed later, which is what
    `brain.ops.checkpoints.ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT` refuses for a checkpoint
    and `brain.ops.jobs` refuses for a queue row. Two attempts of one child can therefore
    reach different things, and both answers are right: narrowing is the guarantee, because
    revocation here is the deletion of a grant.
    """

    run_id: str
    child_id: str
    #: Every lens between the person and this child, root first.
    hops: tuple[Hop, ...]

    def __post_init__(self) -> None:
        for label, value in (("run_id", self.run_id), ("child_id", self.child_id)):
            if not value.strip():
                msg = f"a delegation with no {label} cannot be counted against a cap or audited"
                raise DelegationError(msg)
        if not self.hops:
            msg = (
                f"delegation {self.child_id!r} has no lens on it, so it would run at the "
                "asker's own reach and the agent it was delegated through would have "
                "narrowed nothing"
            )
            raise DelegationError(msg)

    @property
    def depth(self) -> int:
        return depth_of(self.hops)

    def reach(self, caller: EntitlementSet) -> EntitlementSet:
        """What this child may touch, folded from the caller's reach at this moment."""
        return chain_reach(caller, self.hops)


def child_hops(parent: Sequence[Hop], *, agent: Hop, subtask: Hop) -> tuple[Hop, ...]:
    """The chain a child sits on: the parent's, then the agent, then the subtask.

    The order is `parent intersect agent intersect subtask`, which is what architecture
    section 14 asks for and what the fold produces by applying them in that sequence.
    Intersection is associative, so the three-way narrowing needs no three-way function and
    no new call site: it is `flow_reach` twice, which is why nothing in this package appears
    in the pinned map of intersection call sites.

    Refuses a subtask hop dressed as an agent and the other way round, because the depth cap
    counts agents and a subtask counted as one would let a chain report a depth it does not
    have while `depth_of` agreed with it.
    """
    if agent.kind is not LensKind.AGENT:
        msg = f"the agent hop for this child is a {agent.kind}, so the depth cap would miscount"
        raise DelegationError(msg)
    if subtask.kind is not LensKind.SUBTASK:
        msg = (
            f"the subtask hop for this child is a {subtask.kind}, so it would be counted as "
            "a delegation and the chain would report a depth it does not have"
        )
        raise DelegationError(msg)
    return (*parent, agent, subtask)


def concurrency_refusals(children: Sequence[Delegation]) -> tuple[str, ...]:
    """Every reason this set of children may not start together, before any of them does.

    Per run rather than in total, because the cap is per run: `brain.ops.admission` holds
    the figure that applies across runs and `may_fan_out` asks it. Grouping here rather than
    requiring one run's children as the argument, so that a caller holding a mixed list
    cannot satisfy the cap by passing one run at a time.
    """
    findings: list[str] = []
    runs: dict[str, list[Delegation]] = {}
    for child in children:
        runs.setdefault(child.run_id, []).append(child)
    for run_id, group in sorted(runs.items()):
        if len(group) > MAX_CHILDREN_PER_RUN:
            findings.append(
                f"run {run_id!r} would start {len(group)} children at once and the cap is "
                f"{MAX_CHILDREN_PER_RUN}. {EIGHT_IS_THE_BACKGROUND_SHARE_OF_THE_GLOBAL_BUDGET}"
            )
        findings.extend(
            f"child {child.child_id!r} of run {run_id!r} sits {child.depth} delegations "
            f"deep and the cap is {MAX_DELEGATION_DEPTH}"
            for child in group
            if child.depth > MAX_DELEGATION_DEPTH
        )
    return tuple(findings)


def fan_out_request(run_id: str, *, children: int, traffic_class: TrafficClass) -> AdmissionRequest:
    """The admission request one fan-out makes, for all of its children at once.

    `units=children` rather than one request per child, and that is the whole point of
    building it here. Admitted one at a time, a fan-out of eight against two free slots
    starts two children and then discovers there is no room for the rest, which is a fan-out
    that half happened: the merge step has no way to distinguish a subtask that failed from
    one that was never admitted, and the answer goes out with a gap nobody chose.

    `Lane.TASK` unconditionally, whatever channel the question arrived on. A child is
    autonomous multi-step work with nobody watching the spinner, which is what that lane
    means, and `brain.ops.admission.workload_class_for` reads it to put the whole fan-out in
    the background pool rather than the interactive one.
    """
    if children < 1:
        msg = f"run {run_id!r} asked to fan out to {children} children, which is not a fan-out"
        raise DelegationError(msg)
    if children > MAX_CHILDREN_PER_RUN:
        msg = (
            f"run {run_id!r} asked for {children} children and the per-run cap is "
            f"{MAX_CHILDREN_PER_RUN}; admission is asked after the cap, never instead of it"
        )
        raise DelegationError(msg)
    return AdmissionRequest(
        trace_id=run_id,
        lane=Lane.TASK,
        traffic_class=traffic_class,
        resource=PARALLELISM_RESOURCE,
        units=children,
    )


def may_fan_out(
    request: AdmissionRequest,
    budgets: Sequence[Budget],
    state: CapacityState,
    *,
    now: datetime,
    halts: HaltState = NOTHING_HALTED,
) -> AdmissionDecision:
    """Whether there is room across every run for these children (M18.3.5).

    `brain.ops.admission.decide`, handed the request and nothing else. There is no
    arithmetic in this function and that is the point: the global budget is central, it is a
    configuration row rather than a constant, and a subsystem that counted its own
    concurrent children would be the exact failure section 25 describes, where each part of
    the system consumes until Postgres or memory gives out.

    A thin pass-through is still worth having, because what it pins is the choice of
    resource and lane. A caller free to name its own budget can name an empty one.
    """
    return admission_decide(request, budgets, state, now=now, halts=halts)


def global_ceiling(budgets: Sequence[Budget]) -> int:
    """The most children the whole estate may have in flight, from the configured budget.

    Read off the row rather than restated, so that raising the budget raises this and
    nothing has to be edited in two places. `WorkloadClass.BACKGROUND` because that is where
    `workload_class_for` puts task-lane work, and reading it at a different class would
    produce a number no fan-out is ever measured against.
    """
    rows = [one for one in budgets if one.budget_key == (PARALLELISM_RESOURCE, "")]
    if not rows:
        msg = (
            f"no budget row for {PARALLELISM_RESOURCE}; an unbudgeted resource is the "
            "failure global budgets exist to prevent, so nothing fans out against it"
        )
        raise DelegationError(msg)
    return rows[0].ceiling_for(WorkloadClass.BACKGROUND)


# ------------------------------------------------------- no grant verb (M18.3.3)
#: The functions permitted to build an `EntitlementSet` out of something that is not one.
#: Both are ceiling producers: what they return is the right-hand side of the intersection,
#: it confers nothing, and its principal id is prefixed so it cannot be read as a person.
#: Named as a constant with a parameter beside it so the check can be shown to fail, which
#: is the argument `brain.ops.queue.concurrency_gaps` records about its own default.
CEILING_PRODUCERS: Final[frozenset[str]] = frozenset({"subtask_ceiling", "entitlement_ceiling"})

#: The type whose construction is the unit of reach. A `Grant` is a capability bound to a
#: scope, which is precisely what somebody holds, so building one outside a ceiling producer
#: is the shape of conferring rather than narrowing.
GRANT_TYPE_NAME: Final = "Grant"

#: The type a reach is carried in. A function returning one from arguments that contain none
#: has produced reach from nothing.
REACH_TYPE_NAME: Final = "EntitlementSet"

#: Parameter names that are a receiver rather than an argument. A method that narrows the
#: reach it is handed takes it second, and counting `self` would report every one of them.
RECEIVER_NAMES: Final[frozenset[str]] = frozenset({"self", "cls"})


def grant_verbs_in(
    source: str, *, producers: frozenset[str] = CEILING_PRODUCERS
) -> tuple[str, ...]:
    """Every place in `source` that could hand a run more reach than it arrived with (M18.3.3).

    Two shapes, and neither is a search for the word "grant". Parsed rather than grepped for
    the reason `tests/invariants/test_single_implementation.py` gives about its own scan: a
    docstring saying a module grants nothing is exactly what this exists to disbelieve, and
    `ast` sees a call and a comment differently.

    **A function returning a reach whose first parameter is not one.** Narrowing takes a
    reach and returns a smaller one, so the signature is the check: a producer of reach from
    something else is either a ceiling producer, which is named, or a grant verb.

    **A `Grant` constructed outside a named ceiling producer**, including at module level. A
    grant at module level is a standing grant nobody can revoke, because revocation here is
    the deletion of a row and there is no row.

    Takes the source rather than reading this file, so the interesting case, a module that
    does confer, is one a test can hand it. That is the argument
    `brain.console.workspace.intersections_in` records having learned from a mutation.
    """
    tree = ast.parse(source)
    findings: list[str] = []
    inside: dict[int, str] = {}
    for holder in ast.walk(tree):
        if not isinstance(holder, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(holder):
            inside.setdefault(id(node), holder.name)
        if holder.name in producers:
            continue
        returns = holder.returns
        if returns is None or ast.unparse(returns) != REACH_TYPE_NAME:
            continue
        args = holder.args.posonlyargs + holder.args.args
        # The receiver is not an argument in this sense. A method narrowing the reach it is
        # handed still takes it as its first real parameter, and counting `self` would
        # report every such method as a grant verb and teach a reader to ignore the check.
        if args and args[0].arg in RECEIVER_NAMES:
            args = args[1:]
        first = args[0] if args else None
        if first is None or first.annotation is None:
            findings.append(
                f"{holder.name} returns a {REACH_TYPE_NAME} and takes no annotated first "
                f"argument, so it produces reach out of nothing. "
                f"{THE_ORCHESTRATOR_HAS_NO_GRANT_VERB}"
            )
            continue
        if ast.unparse(first.annotation) != REACH_TYPE_NAME:
            findings.append(
                f"{holder.name} returns a {REACH_TYPE_NAME} and its first argument is "
                f"{ast.unparse(first.annotation)}, so it is producing reach rather than "
                f"narrowing one. {THE_ORCHESTRATOR_HAS_NO_GRANT_VERB}"
            )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = called.id if isinstance(called, ast.Name) else None
        if name != GRANT_TYPE_NAME:
            continue
        holder_name = inside.get(id(node), "")
        if holder_name in producers:
            continue
        where = f"{holder_name}" if holder_name else "module level"
        findings.append(
            f"a {GRANT_TYPE_NAME} is constructed at {where}, which is the unit of reach "
            f"rather than a narrowing of one. {THE_ORCHESTRATOR_HAS_NO_GRANT_VERB}"
        )
    return tuple(findings)
