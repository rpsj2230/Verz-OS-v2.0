"""Rehearsing a thing before it exists, and the gate it has to get through to start existing.

This is the load-bearing half of the builder, and the reason is one sentence: everywhere else
a person asks and the gate answers, and here a person builds the asker.

**Whose reach a rehearsal runs at, and why it is not the author's** (M20.3.3). Rehearsing
means running, and running means reaching data, so the question has an answer whether or not
anybody writes one down. `E_run(caller, agent) = E(caller) intersect agent_ceiling`, computed
by `EntitlementSet.intersect` in `brain.gate.leash.decide` and by `brain.ops.automation.
flow_reach`, so the reach of a run is a fact about who ran it. A rehearsal run at the author's
reach and then published to be run by somebody else has previewed a different run: the author
watched their own intersection and shipped somebody else's. So a rehearsal names the persona
it is run as, the reach handed to it must belong to that persona, and `reach_refusals` refuses
the pairing where it does not. That refusal is the whole of the leaf: without it the two are
indistinguishable at the type level, because both are an `EntitlementSet`.

**And a rehearsal is not a window onto another person's rows.** This is the half that reads
like a restriction and is the same rule pointing the other way. If the rehearsal runs at the
persona's reach and the author is shown everything it returned, the builder is a tool for
reading any colleague's data: pick a persona, rehearse, read the answer. That is exactly the
hazard a builder introduces, arriving through the preview rather than through the publish, and
it is worse than the publish version because it needs no approval at all. `RehearsalOutcome`
therefore carries no rows and `row_shaped_fields` refuses a field that could, and what the
author sees of the run itself follows a screen's own grant: naming the tools a persona reached
is a statement about that persona's grants, which is what `brain.console.screens`'s people
screen shows behind `read:grant`, so `detail_for` asks `brain.console.reads.permitted` about
that screen rather than inventing a capability for the builder. It is the same argument
`brain.console.workspace.basis_for` makes about a figure on an agent's front page.

**Rehearsal runs at SHADOW and that is not the cassette.** `brain.gate.leash.MISSING_ENTRY_RUNG`
is SHADOW and `run_shadow` returns the same shape a real run does, so pinning the rung is a
belt this layer can fasten by itself. M20.3.2 asks for cassette replay and is not claimed:
shadow stops an action being carried out, and a cassette stops the source being called at all.
The two fail differently and a source with a rate limit notices the difference.

**A builder is where a ceiling can outgrow its author's reach** (M20.4.3), and the reason the
publish gate matters more than the form does. Nothing an author publishes can widen their own
runs, because their own runs are intersected down to what they hold. What they can publish is
a ceiling wider than they hold, to be run by somebody who holds more, and from the author's
seat that widening is invisible: every rehearsal they run comes back narrowed by their own
grants, so the extra reach never appears. There is no seat from which it can be seen except
the diff, which is why a widening demotes to SHADOW and asks for a second pair of eyes rather
than warning the person who cannot see it. `widened_capabilities` compares the two ceilings
and computes no reach: a capability absent from the old ceiling is new, and a scope that lost
a clause is looser, because `Scope` is conjunction-only so clauses only ever narrow.

**A refusal at a publish gate is a refusal surface like any other** (M20.4.5). A router
collision is the case: two agents bound to one route, and the useful message names the other
agent. That message tells the author an agent exists that they may not be able to see, from a
screen whose whole job is to accept their own work, and it is worse than the usual leak
because it is one query per route. `binding_collisions` names the route the author supplied
and never the agent, and returns one refusal however many agents collide, because a refusal
per collision is a count of things the reader may not see. `brain.gate.answer` and
`brain.core.errors` make the same argument about DENIED and ABSENT.

**The publish record holds paths and never values** (M20.4.6). `brain.audit.ledger` already
argues this about itself: an entry records field names, never field values, because the ledger
is the longest-retained and most widely read table in the system. A publish diff is exactly
where somebody would put the before and after of `authority.capabilities`, which is a map of
what an agent may reach written into the place with the weakest reason to hold it. So
`record_publish` builds its paths with `brain.audit.ledger.changed_fields` and there is no
field on the record a value could arrive in. `AuditAction.PUBLISH` already exists, so nothing
here adds a member to a vocabulary that is closed on purpose.

**Rejected: deciding the demotion from the paths that changed.** It is the obvious reading of
M20.4.4 and it puts the decision in the wrong place. The gate reads the two ceilings, so
"instruction edits publish without demotion" is a consequence rather than a rule: an edit that
does not touch the authority section leaves the ceiling identical, `widened_capabilities`
returns nothing and the rung is kept. `REACH_PATHS` is carried anyway, because a manifest path
that is in neither classification is one nobody has decided about, and `publish_gaps` says so.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock; `now`
is a parameter, and it is required rather than defaulted because `EntitlementSet.scope_for`
reads the wall clock when it is not given one.

**This declares the gate and runs nothing through it.** M20.3.1 wants the rehearsal run
against the real gate, leash and redactor, and nothing in this repository assembles that run:
`brain.gate.answer` says the model lane does not exist. M20.3.2 wants a cassette player.
M20.3.4 wants a measured cost, which is a figure the run produces and there is no run. None of
the three is claimed.

Task ids: M20.3.3, M20.4.1, M20.4.2, M20.4.3, M20.4.4, M20.4.5, M20.4.6
"""

from __future__ import annotations

import enum
import inspect
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.agents.template import MANIFEST_PATHS
from brain.audit.ledger import changed_fields
from brain.builder.compose import BuilderError
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.gate.injection import AutonomyTier
from brain.gate.select import AgentBinding

# ------------------------------------------------------------------ written-down reasons
#: Why a rehearsal is run as the persona and never as the person watching.
A_REHEARSAL_AT_THE_AUTHORS_REACH_IS_A_PREVIEW_OF_A_DIFFERENT_RUN: Final = (
    "Rehearsing means running and running means reaching data, so the reach a rehearsal uses "
    "is a fact whether or not anybody chose it. Run at the author's reach and then published "
    "to be run by somebody else, the preview showed the author's own intersection and shipped "
    "another person's, which is the failure that looks most like success: the rehearsal "
    "passed. The persona is named on the rehearsal and the reach handed in must belong to it, "
    "because at the type level the author's reach and the persona's are the same object."
)

#: Why the author is not shown what the persona saw.
A_REHEARSAL_THAT_RETURNED_THE_ROWS_WOULD_READ_ANY_COLLEAGUES_DATA: Final = (
    "A rehearsal runs at the persona's reach, so a rehearsal that handed its answer back to "
    "the author would be a way of reading anybody's data by picking them as a persona. It "
    "needs no approval, leaves an audit row that says a rehearsal happened, and is reached "
    "from a surface whose whole purpose is to accept what the author is building. The outcome "
    "carries no rows, and which tools a persona reached follows the grant that shows a "
    "person's grants rather than a capability invented for the builder."
)

#: Why an author's own test can never be the test that stops a publish.
A_TEST_THE_AUTHOR_WROTE_IS_A_TEST_THE_AUTHOR_CAN_REWRITE: Final = (
    "A gate held shut by a test the person being gated also owns is a gate with a handle on "
    "the inside. Author-written tests are worth running and worth showing, and the moment one "
    "of them can block, the way past a failing publish is to edit the test. So blocking "
    "follows the origin of the check and nothing else: there is no field on a check that "
    "could raise an author's test to blocking, and no function here that promotes one."
)

#: Why a widening is the failure a builder introduces.
A_BUILDER_IS_WHERE_A_CEILING_CAN_OUTGROW_ITS_AUTHORS_REACH: Final = (
    "Nothing an author publishes widens their own runs, because their own runs are "
    "intersected down to what they hold. What they can publish is a ceiling wider than they "
    "hold, to be run by somebody who holds more, and the widening is invisible from the only "
    "seat the author occupies: every rehearsal comes back narrowed by their own grants. There "
    "is no seat from which it can be seen except the diff, so a widening demotes to shadow "
    "and asks for a second pair of eyes rather than warning the person who cannot see it."
)

#: Why the collision message names a route rather than an agent.
A_COLLISION_REFUSAL_THAT_NAMES_THE_OTHER_AGENT_HAS_DISCLOSED_IT: Final = (
    "The useful message says which agent is already on this route, and it says it to somebody "
    "who may not be entitled to know that agent exists. It is worse than the usual disclosure "
    "because it is repeatable: one publish attempt per route enumerates the router. The "
    "refusal names the route, which the author supplied, and there is one refusal however "
    "many agents collide, because a refusal per collision is a count of hidden things."
)

#: Why the publish record carries paths and not the diff itself.
A_PUBLISH_RECORD_THAT_CARRIES_VALUES_IS_A_MAP_OF_WHAT_AN_AGENT_REACHES: Final = (
    "The obvious record holds the before and after of what changed, and for a publish that is "
    "the before and after of authority.capabilities: a map of what an agent may reach, in the "
    "longest-retained and most widely read record in the system. brain.audit.ledger makes the "
    "same argument about its own entries and answers it the same way, with field names and "
    "never field values, so this builds its paths with that module's changed_fields."
)


# ------------------------------------------------------------------- rehearsal (M20.3.3)
#: The rung a rehearsal runs at, whatever the agent's leash says.
#:
#: Named rather than written into the check, and pinned to the same value `brain.gate.leash.
#: MISSING_ENTRY_RUNG` uses for an unconfigured target: an action nobody has thought about is
#: simulated and shown to somebody, and a run of an agent nobody has approved yet is exactly
#: that case.
REHEARSAL_RUNG: Final = AutonomyTier.SHADOW

#: Field names that would put another person's rows in front of the author.
#:
#: Names rather than a rule about values, because the failure arrives as a field somebody adds
#: to make the rehearsal useful. The same construction as
#: `brain.console.workspace.NAMES_THAT_WOULD_BE_AN_INLINE_COPY`.
NAMES_THAT_WOULD_CARRY_ANOTHER_PERSONS_ROWS: Final[frozenset[str]] = frozenset(
    {
        "answer",
        "content",
        "payload",
        "records",
        "result",
        "rows",
        "text",
        "values",
    }
)


class Detail(enum.StrEnum):
    """How much of a rehearsal the author is shown. Two, and the narrower one is the default.

    There is deliberately no third member meaning "the shapes, roughly". A middle level is
    the one that reads as a compromise and is a disclosure: which tools refused is which
    grants the persona is missing, whether it is spelled as a list or as a count.
    """

    #: Whether the agent got to an answer at all.
    OUTCOME = "outcome"
    #: Which tools the persona reached, for a reader who could read their grants anyway.
    PER_TOOL = "per_tool"


#: The screen whose grant decides whether a rehearsal may name the tools a persona reached.
#:
#: A screen key rather than a capability written out here, so the builder cannot drift from
#: the screen: `detail_for` asks `permitted` about that screen's own read, which is both the
#: tool's capability and the console plane, exactly as opening the screen would be.
PERSONA_DETAIL_SCREEN: Final = "people"


@dataclass(frozen=True)
class Rehearsal:
    """One rehearsal: which agent, run as whom, watched by whom.

    Three ids and a rung. The persona and the author are separate fields precisely because
    they are usually different people and are the same type, which is the confusion
    `A_REHEARSAL_AT_THE_AUTHORS_REACH_IS_A_PREVIEW_OF_A_DIFFERENT_RUN` describes.
    """

    agent_id: str
    #: The person this run is performed as. The reach belongs to them.
    persona_id: str
    #: The person watching. Holds no part of the run's reach.
    author_id: str
    rung: AutonomyTier = REHEARSAL_RUNG

    def __post_init__(self) -> None:
        if not self.agent_id.strip() or not self.persona_id.strip():
            msg = "a rehearsal of no agent, or as nobody, describes no run"
            raise BuilderError(msg)
        if not self.author_id.strip():
            msg = "a rehearsal nobody is watching is a run, and a run is not a rehearsal"
            raise BuilderError(msg)
        if self.rung is not REHEARSAL_RUNG:
            msg = (
                f"a rehearsal at {self.rung.name} could carry out the action it is "
                "rehearsing, and an action carried out in a preview is not a preview"
            )
            raise BuilderError(msg)


@dataclass(frozen=True)
class RehearsalOutcome:
    """What came back from a rehearsal, in the shape the author may be shown.

    **No field here holds a row.** No records, no answer, no payload. See
    `A_REHEARSAL_THAT_RETURNED_THE_ROWS_WOULD_READ_ANY_COLLEAGUES_DATA`, and
    `row_shaped_fields`, which asks the type rather than whoever edits it next.
    """

    agent_id: str
    persona_id: str
    #: Whether the run reached an answer rather than abstaining.
    answered: bool
    #: The tools the persona reached, shown only at `Detail.PER_TOOL`.
    tools_reached: tuple[str, ...] = ()


def reach_refusals(rehearsal: Rehearsal, reach: EntitlementSet) -> tuple[str, ...]:
    """Whether this reach may be used for this rehearsal (M20.3.3).

    One refusal, and it is the one thing a type cannot say: an `EntitlementSet` for the author
    and one for the persona are the same object, so nothing but the principal on it
    distinguishes the run being previewed from the run being shipped. See
    `A_REHEARSAL_AT_THE_AUTHORS_REACH_IS_A_PREVIEW_OF_A_DIFFERENT_RUN`.

    This does not narrow the reach and does not intersect it with the agent's ceiling. That
    is `brain.gate.leash.decide`'s work and it is the one implementation of the invariant;
    what happens here is a check that the reach handed to it belongs to the right person.
    """
    if reach.principal_id != rehearsal.persona_id:
        return (
            f"this rehearsal is run as {rehearsal.persona_id!r} and was handed a reach "
            f"belonging to {reach.principal_id!r}, so what it previews is a different run "
            f"from the one being published. "
            f"{A_REHEARSAL_AT_THE_AUTHORS_REACH_IS_A_PREVIEW_OF_A_DIFFERENT_RUN}",
        )
    return ()


def detail_for(entitlement: EntitlementSet, now: Any = None) -> Detail:
    """How much of a rehearsal this author may be shown (M20.3.3).

    Asked of `brain.console.reads.permitted` against the people screen's own read rather than
    of a capability invented here. Naming the tools a persona reached is a statement about
    that persona's grants, and the screen that shows a person's grants already has a grant in
    front of it; a builder with its own would be a second answer to a question the screen
    registry already answers, reviewed by nobody who reviews the first.
    """
    return (
        Detail.PER_TOOL
        if permitted(screen(PERSONA_DETAIL_SCREEN).read, entitlement, now)
        else Detail.OUTCOME
    )


def shown(outcome: RehearsalOutcome, detail: Detail) -> RehearsalOutcome:
    """The outcome as this author may see it (M20.3.3).

    At `Detail.OUTCOME` the tool list is emptied rather than counted. A count of tools the
    reader may not be told about is the disclosure by subtraction, and `answered` is not one:
    whether the agent being built reached an answer is a fact about the agent, which is the
    thing the author is holding.
    """
    if detail is Detail.PER_TOOL:
        return outcome
    return RehearsalOutcome(
        agent_id=outcome.agent_id,
        persona_id=outcome.persona_id,
        answered=outcome.answered,
    )


def row_shaped_fields(surface: Sequence[type]) -> tuple[str, ...]:
    """Fields on these types that could carry the rows a rehearsal read.

    Reported as `Type.field` so the finding names the edit, following
    `brain.ops.jobs.hidden_count_fields`.
    """
    findings: list[str] = []
    for one in surface:
        declared: Mapping[str, object] = getattr(one, "__dataclass_fields__", {})
        findings.extend(
            f"{one.__name__}.{name}"
            for name in declared
            if name in NAMES_THAT_WOULD_CARRY_ANOTHER_PERSONS_ROWS
        )
    return tuple(findings)


# ------------------------------------------------------- checks that block (M20.4.1, M20.4.2)
class CheckOrigin(enum.StrEnum):
    """Who wrote a check, which is the only thing that decides whether it can block.

    Two members and deliberately no third. An "approved by review" origin between them is the
    one somebody adds so a good author's tests can count, and it is the handle on the inside
    of the gate that `A_TEST_THE_AUTHOR_WROTE_IS_A_TEST_THE_AUTHOR_CAN_REWRITE` describes.
    """

    #: Written by this system. Permission canaries, and anything else shipped rather than typed.
    SYSTEM = "system"
    #: Written by whoever is building the agent.
    AUTHOR = "author"


#: Field names that would let an author's test be raised to blocking.
#:
#: The "forever" in M20.4.2 is a claim about every future edit, and a claim of that shape only
#: survives as a check. `Check.blocks` is a property computed from the origin, so there is
#: nothing to set; these are the names of the fields somebody would add to be able to.
NAMES_THAT_WOULD_PROMOTE_AN_AUTHORS_TEST: Final[frozenset[str]] = frozenset(
    {
        "advisory",
        "blocking",
        "blocks",
        "enforced",
        "fatal",
        "gating",
        "required",
        "severity",
        "weight",
    }
)


@dataclass(frozen=True)
class Check:
    """One check run against a candidate publish, and who wrote it.

    **`blocks` is a property and not a field**, which is M20.4.2 expressed as a shape rather
    than as a rule somebody keeps: there is no attribute to set, so promoting an author's
    test means editing this class in a diff somebody reviews.
    """

    name: str
    origin: CheckOrigin
    passed: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a check with no name cannot be reported, argued with or fixed"
            raise BuilderError(msg)

    @property
    def blocks(self) -> bool:
        """Whether this check stops the publish (M20.4.1, M20.4.2)."""
        return self.origin is CheckOrigin.SYSTEM and not self.passed


def blocking_failures(checks: Iterable[Check]) -> tuple[str, ...]:
    """The names of the checks that stop this publish, in the order they were run.

    Author-written failures are absent from this and present in the checks themselves, which
    is the difference between advisory and ignored: they are run, they are reported, and they
    are not consulted here.
    """
    return tuple(one.name for one in checks if one.blocks)


def promotion_shaped_fields(check_type: type) -> tuple[str, ...]:
    """Fields on the check type that would let an author's test become blocking."""
    declared: Mapping[str, object] = getattr(check_type, "__dataclass_fields__", {})
    return tuple(
        f"{check_type.__name__}.{name}"
        for name in declared
        if name in NAMES_THAT_WOULD_PROMOTE_AN_AUTHORS_TEST
    )


# ---------------------------------------------------- widening and demotion (M20.4.3, M20.4.4)
#: The manifest paths that decide what an agent may reach or how closely it is watched.
#:
#: Written as data rather than derived from a prefix, because two of the exclusions are
#: arguments rather than facts about a name. `connectors` and `skills` look like reach and are
#: not: reach is decided by capabilities alone, a connector nothing holds a capability for
#: grants nothing, and `brain.tools` opens with the rule that composing tools into a skill can
#: never widen what was decided about a tool. So an edit to either changes what an agent does
#: and not what it may see, and the ceiling comparison below is unmoved by it either way.
REACH_PATHS: Final[frozenset[str]] = frozenset(
    {
        "authority.allowed_tools",
        "authority.capabilities",
        "authority.required_tools",
        "authority.scope",
        "guardrails.leash",
        "guardrails.max_side_effect",
    }
)

#: Everything else, derived rather than listed, so nothing can be in both sets. A path in
#: neither is impossible by construction; a `REACH_PATHS` entry that is not a manifest path is
#: not, and `publish_gaps` is where that is caught.
INSTRUCTION_PATHS: Final[frozenset[str]] = frozenset(MANIFEST_PATHS) - REACH_PATHS

#: How many people have to approve a publish that widens what an agent may reach.
#:
#: Two rather than one, and the figure is only meaningful against the ordinary case: "a second
#: approver" means exactly one more than usual, which is the relation a test can hold rather
#: than a number it can only compare with itself.
APPROVERS_FOR_A_WIDENING: Final = 2

#: And for a publish that widens nothing.
APPROVERS_FOR_AN_ORDINARY_PUBLISH: Final = 1


def widened_capabilities(
    before: EntitlementSet, after: EntitlementSet, *, now: datetime
) -> tuple[str, ...]:
    """Everything the new ceiling admits that the old one did not (M20.4.3).

    This is the question a builder makes necessary and no other surface has to ask. See
    `A_BUILDER_IS_WHERE_A_CEILING_CAN_OUTGROW_ITS_AUTHORS_REACH`: the author cannot see the
    answer from any seat they occupy, so the diff is the only place it appears.

    Two ways a ceiling grows and both are here. A capability the old ceiling did not cover at
    all is new. A capability it did cover, in a scope that has since lost a clause, is looser:
    `Scope` is a conjunction with no NOT and no OR, so a clause can only narrow, and therefore
    the new scope is no wider than the old exactly when it keeps every clause the old one had.
    An unrestricted scope has no clauses, which makes it the widest, and the comparison gets
    that right without a special case.

    **Nothing here computes a reach.** This compares two declared ceilings and calls no
    intersection: `EntitlementSet.intersect` answers what one person gets through one agent,
    which is a different question and is answered where the run happens.

    `now` is required rather than defaulted because `scope_for` reads the wall clock when it
    is not given one, and a ceiling with an expiry would then be compared against whenever the
    check happened to run.
    """
    grown: list[str] = []
    for grant in after.grants:
        previous = before.scope_for(grant.capability, now)
        if previous is None:
            grown.append(grant.capability.value)
            continue
        if not set(previous.clauses) <= set(grant.scope.clauses):
            grown.append(grant.capability.value)
    return tuple(sorted(set(grown)))


def rung_after(current: AutonomyTier, widenings: Sequence[str]) -> AutonomyTier:
    """The rung this publish lands on (M20.4.3, M20.4.4).

    Demoted on a widening and kept otherwise, and the input is the widening rather than the
    paths that changed. That ordering is what makes M20.4.4 a consequence rather than a second
    rule: an instruction edit does not touch the authority section, so the ceilings are
    identical, so there is nothing to demote for. A gate that read the paths instead would be
    deciding supervision from a classification somebody maintains by hand.

    Shadow rather than a warning, because there is nobody useful to warn:
    `A_BUILDER_IS_WHERE_A_CEILING_CAN_OUTGROW_ITS_AUTHORS_REACH` is the argument, and the
    person who would read the warning is the one the reach is invisible to.
    """
    return AutonomyTier.SHADOW if widenings else current


def approvers_needed(widenings: Sequence[str]) -> int:
    """How many people must approve this publish (M20.4.3)."""
    return APPROVERS_FOR_A_WIDENING if widenings else APPROVERS_FOR_AN_ORDINARY_PUBLISH


def instruction_only(paths: Iterable[str]) -> bool:
    """Whether this diff touches nothing that decides reach or supervision (M20.4.4).

    Documentation of why an instruction edit never demotes, and never consulted by anything
    that decides one: see `rung_after`, and `publish_gaps`, which refuses a `decide` that
    grows a parameter this could arrive through. It is the arrangement
    `brain.console.screens.Screen.intended_for` uses for the same reason.

    A path that is in neither classification is treated as reach, because the safe reading of
    a path nobody has decided about is the one that asks for another pair of eyes.
    """
    return all(path in INSTRUCTION_PATHS for path in paths)


# ------------------------------------------------------------ the router collision (M20.4.5)
def route_key(binding: AgentBinding) -> str:
    """The address a binding occupies: its channel, and the conversation if it names one.

    A conversation-level binding and a channel-level one on the same channel are different
    addresses, because `brain.gate.select` resolves the more specific one first and both can
    exist. Collapsing them would refuse a publish that the router handles correctly.
    """
    return f"{binding.channel.value}:{binding.conversation_id or ''}"


def binding_collisions(
    candidate: AgentBinding, published: Iterable[AgentBinding]
) -> tuple[str, ...]:
    """Whether this binding is already taken, said without naming who by (M20.4.5).

    **One refusal, however many agents collide**, and it names the route rather than any of
    them. See `A_COLLISION_REFUSAL_THAT_NAMES_THE_OTHER_AGENT_HAS_DISCLOSED_IT`: a refusal per
    collision is a count of things the reader may not see, and the count is as much of a
    disclosure as the names would be.

    A binding the candidate agent already holds is not a collision, so republishing an agent
    onto its own route is not refused as a clash with itself.

    Selection rules are the router's second stage and are not covered. Two bindings collide
    when their addresses are equal, which is decidable by comparison; two rules collide when
    their patterns overlap, which is a different question with a different answer, and
    reporting equal patterns while missing overlapping ones would be a check that reads as
    complete and is not.
    """
    key = route_key(candidate)
    if any(route_key(one) == key and one.agent_id != candidate.agent_id for one in published):
        return (
            f"{key} already has an agent bound to it. Unbind it there, or publish this agent "
            "onto a route of its own. "
            f"{A_COLLISION_REFUSAL_THAT_NAMES_THE_OTHER_AGENT_HAS_DISCLOSED_IT}",
        )
    return ()


# ------------------------------------------------------------- the decision and the record
@dataclass(frozen=True)
class PublishDecision:
    """What this publish is allowed to become: a rung, a number of approvers, and refusals.

    `widenings` carries capability values and that is not a disclosure: every one of them is
    in the manifest the author is publishing, so the list is their own document read back to
    them. `refusals` is the half that is a disclosure surface, which is why the collision one
    is built where it is rather than formatted here.
    """

    agent_id: str
    rung: AutonomyTier
    approvers: int
    widenings: tuple[str, ...]
    refusals: tuple[str, ...]

    @property
    def may_publish(self) -> bool:
        """Whether anything stops this publish outright, before approval."""
        return not self.refusals


def decide(
    *,
    agent_id: str,
    current_rung: AutonomyTier,
    before_ceiling: EntitlementSet,
    after_ceiling: EntitlementSet,
    checks: Iterable[Check] = (),
    candidate_binding: AgentBinding | None = None,
    published_bindings: Iterable[AgentBinding] = (),
    now: datetime,
) -> PublishDecision:
    """The whole gate, in the order the questions have to be asked.

    Refusals first and demotion second, and they are different outcomes rather than degrees of
    the same one: a refusal means this publish does not happen, and a demotion means it
    happens under supervision. Collapsing them would make a widening refusable and a collision
    survivable, which is both of them the wrong way round.

    There is no parameter here that could skip a check or force a publish past one, and
    `publish_gaps` reads this signature to say so. A gate with an override is a gate whose
    real policy is whoever holds the override.
    """
    widenings = widened_capabilities(before_ceiling, after_ceiling, now=now)
    refusals = list(blocking_failures(checks))
    if candidate_binding is not None:
        refusals.extend(binding_collisions(candidate_binding, published_bindings))
    return PublishDecision(
        agent_id=agent_id,
        rung=rung_after(current_rung, widenings),
        approvers=approvers_needed(widenings),
        widenings=widenings,
        refusals=tuple(refusals),
    )


def approval_refusals(
    decision: PublishDecision, *, author_id: str, approvers: Iterable[str]
) -> tuple[str, ...]:
    """What is still missing before this decision can be acted on (M20.4.3).

    Two refusals. The author is not an approver of their own publish, which is the same rule
    `brain.console.reads.StewardNotice` keeps about a notice addressed to the actor: an
    approval given by the person who wants it tells nobody anything and passes every test that
    checks an approval was recorded. And distinct people are counted rather than approvals, so
    one person approving twice is one approver.
    """
    given = tuple(one.strip() for one in approvers if one.strip())
    refusals: list[str] = []
    if author_id in given:
        refusals.append(
            f"{author_id} both wrote and approved this publish, so nobody else has looked at "
            "it; a second approver means somebody other than the person asking"
        )
    distinct = {one for one in given if one != author_id}
    if len(distinct) < decision.approvers:
        refusals.append(
            f"this publish needs {decision.approvers} approver(s) and has {len(distinct)}"
        )
    return tuple(refusals)


#: Field names that would put a value into the publish record.
NAMES_THAT_WOULD_PUT_A_VALUE_IN_THE_RECORD: Final[frozenset[str]] = frozenset(
    {
        "after",
        "before",
        "detail",
        "diff",
        "document",
        "manifest",
        "overlay",
        "values",
    }
)


@dataclass(frozen=True)
class PublishRecord:
    """Who published what, when, and which paths moved. Never what they moved to.

    See `A_PUBLISH_RECORD_THAT_CARRIES_VALUES_IS_A_MAP_OF_WHAT_AN_AGENT_REACHES`. The rung and
    the approvers are here because they are the decision rather than the content: what a later
    reader needs is that this publish was supervised and by whom, and neither says what any
    field became.
    """

    agent_id: str
    actor_id: str
    at: datetime
    #: The manifest paths that changed, from `brain.audit.ledger.changed_fields`.
    paths: tuple[str, ...]
    rung: AutonomyTier
    approvers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            msg = "a publish record naming no actor records that somebody did something"
            raise BuilderError(msg)
        if self.at.tzinfo is None:
            msg = (
                "a publish recorded at a naive instant is wrong by the host's offset from "
                "UTC, and the record is what a later reader orders the history by"
            )
            raise BuilderError(msg)


def record_publish(
    *,
    agent_id: str,
    actor_id: str,
    at: datetime,
    before: Mapping[str, object],
    after: Mapping[str, object],
    decision: PublishDecision,
    approvers: Iterable[str] = (),
) -> PublishRecord:
    """The record of one publish (M20.4.6).

    The paths come from `brain.audit.ledger.changed_fields`, which is the function the ledger
    uses for the same purpose, so the record and the audit entry cannot disagree about what
    changed. Building the list here by comparing the two documents would be a second answer to
    that question, and the one that is wrong would be the one nobody reads until an incident.

    `AuditAction.PUBLISH` already exists, so writing this to the ledger adds no member to a
    vocabulary that is closed on purpose.
    """
    return PublishRecord(
        agent_id=agent_id,
        actor_id=actor_id,
        at=at,
        paths=changed_fields(before, after),
        rung=decision.rung,
        approvers=tuple(approvers),
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of this surface is handed. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`.
PUBLISH_SURFACE: Final[tuple[type, ...]] = (
    Rehearsal,
    RehearsalOutcome,
    Check,
    PublishDecision,
    PublishRecord,
)


def publish_gaps(
    *,
    surface: Sequence[type] = PUBLISH_SURFACE,
    check_type: type = Check,
    record_type: type = PublishRecord,
    reach_paths: Iterable[str] = REACH_PATHS,
    paths: Sequence[str] = MANIFEST_PATHS,
    source: str | None = None,
) -> tuple[str, ...]:
    """Everything about this gate that would let a publish through wider than anybody decided.

    Takes its inputs rather than reading this module's own constants, for the reason
    `brain.console.workspace.workspace_gaps` gives about its own: a diagnostic that can only
    run against the healthy tree has nothing to report today, so switching off any of its
    refusals changes nothing observable and every one of them survives a mutation.
    """
    from brain.console.workspace import intersections_in

    gaps: list[str] = []

    taken = set(inspect.signature(decide).parameters)
    for forbidden in ("force", "skip_checks", "override", "paths", "approved"):
        if forbidden in taken:
            gaps.append(
                f"decide takes {forbidden}, so a publish can be waved past a check it failed "
                "or have its supervision decided by a classification somebody hands in"
            )

    known = set(paths)
    for path in reach_paths:
        if path not in known:
            gaps.append(
                f"{path!r} is classified as reach and is not a manifest path, so the path it "
                "was renamed from is now classified as an instruction and an edit to it "
                "publishes without demotion"
            )

    gaps.extend(
        f"{found} would put another person's rows in front of the author. "
        f"{A_REHEARSAL_THAT_RETURNED_THE_ROWS_WOULD_READ_ANY_COLLEAGUES_DATA}"
        for found in row_shaped_fields(surface)
    )
    gaps.extend(
        f"{found} would let an author's own test stop a publish. "
        f"{A_TEST_THE_AUTHOR_WROTE_IS_A_TEST_THE_AUTHOR_CAN_REWRITE}"
        for found in promotion_shaped_fields(check_type)
    )
    declared: Mapping[str, object] = getattr(record_type, "__dataclass_fields__", {})
    gaps.extend(
        f"{record_type.__name__}.{name} would put a value into the publish record. "
        f"{A_PUBLISH_RECORD_THAT_CARRIES_VALUES_IS_A_MAP_OF_WHAT_AN_AGENT_REACHES}"
        for name in declared
        if name in NAMES_THAT_WOULD_PUT_A_VALUE_IN_THE_RECORD
    )

    text = inspect.getsource(sys.modules[__name__]) if source is None else source
    gaps.extend(
        f"line {line} intersects two entitlement sets, so the publish gate works out a reach "
        "rather than comparing two declared ceilings, which is a second copy of the central "
        "rule in the layer that decides what gets published"
        for line in intersections_in(text)
    )

    return tuple(gaps)
