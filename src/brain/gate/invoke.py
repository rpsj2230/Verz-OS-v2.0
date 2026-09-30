"""Running an agent: the one place the gate's parts are assembled into a call.

Everything before this module decides something. `resolve` works out what the caller holds,
`select` picks an agent, `catalogue.project` narrows the tools to the intersection of the
two, `leash` decides what may actually happen. This is where those become an invocation,
and it exists because the alternative is every call site assembling them itself - which
means every call site is a place one of them can be forgotten.

**The projected catalogue is the only tool list that ever reaches the model.** Not the
registry, not a filtered copy, not a list the caller passes in. `ProjectedCatalogue` cannot
be constructed outside `project`, so a function that takes one has proof the projection ran;
a function taking `tuple[ToolDefinition, ...]` has a promise. That difference is the whole
reason this signature is shaped the way it is.

**Nothing here decides a permission.** It calls the things that do, in an order that cannot
be got wrong, and refuses to proceed when one of them says no. A second opinion about who
may reach what would be a second answer, and the day the two disagree the permissive one
wins silently.

**In particular, the run reach is not computed here, and ten documents said it was.**
`E_run(caller, agent) = E(caller) intersect agent_ceiling` is computed in `brain.gate.leash`,
in `decide` and again in `resume`. This module has never contained that call. The claim was
in `CLAUDE.md`, in three other source modules, in a named constant, in two test docstrings
and in the invariant test guarding the rule, each copied from the last, and it was corrected
on 2026-09-08. The sentence is repeated here because this is where somebody following one of
those claims arrives, and arriving at a module that quietly does not do the thing is how the
claim survived. `tests/invariants/test_single_implementation.py` reads the call sites out of
the source and pins them, which is the only reason this stays true.

**An empty catalogue is a refusal, not an empty call.** A model handed no tools does not
stop: it answers from whatever it already has in context and from its own training, and
that answer looks exactly like a researched one. The abstention path exists for this and is
reached deliberately rather than by falling through.

**The configured leash becomes the leash a run is held to here, and nowhere else (M12.1.3).**
`ToolRegistry.tighten` holds every entry on a registered tool to that tool's leash ceiling, the
rung its side effect allows, so an entry somebody set to Autonomous on a tool that drafts,
writes or sends runs Assisted, and one on a tool that moves money runs in Shadow. It was built,
tested and shown on the Tools screen, and until 2026-09-30 nothing called it: every run was
held to the rung its leash said, whatever its tools did. The held leash is what `Invocation`
carries, so a step governed inside the run is governed by it and never by the configured one.
See `A_RUN_IS_HELD_TO_THE_RUNG_ITS_TOOLS_SIDE_EFFECTS_ALLOW`.

*Rejected: tightening in `brain.agent_routes.leash_of`*, which is what an agent's page reads.
The page would then show a rung nobody configured as though somebody had, and a person raising
a rung past its ceiling would see it not move and be told nothing. The page shows the
configured leash and a run may only be held lower, which is
`brain.console.agent_profile.THE_LEASH_SHOWN_IS_THE_CONFIGURED_ONE_AND_A_RUN_MAY_ONLY_BE_HELD_LOWER`.

*Rejected: tightening per action in `brain.gate.leash.effective_tier`.* The registry imports
that module, so it cannot import the registry, and computing the ceiling from the action's own
definition there would be a second copy of `leash_ceiling`. Two copies of a rule about how
far a tool may run unsupervised disagree eventually, and the one that disagrees permissively
is the one nobody notices.

*Rejected: tightening at each caller.* Three call sites assemble a run today (the builder's
rehearsal, the reach preview and an automation's piece call), and the fourth, an agent
runtime, is the one that would forget. Every one of them hands this function the registry
already, so the one place that can hold them all is the place they all pass through.

Task ids: M3.8.1, M12.1.3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from brain.core.entitlement import EntitlementSet
from brain.gate.catalogue import AgentCeiling, EmptyCatalogueError, ProjectedCatalogue, project
from brain.gate.injection import AutonomyTier, RiskAssessment, autonomy_ceiling
from brain.gate.leash import MISSING_ENTRY_RUNG, Leash
from brain.tools.registry import ToolRegistry

#: Why a run's rung is not always the rung its leash was configured at.
A_RUN_IS_HELD_TO_THE_RUNG_ITS_TOOLS_SIDE_EFFECTS_ALLOW: Final = (
    "A leash entry set to Autonomous on a tool that drafts, writes or sends runs Assisted, and "
    "one on a tool that moves money runs in Shadow, on every run, because the run is assembled "
    "in one place and that place holds the configured leash to each tool's leash ceiling with "
    "ToolRegistry.tighten. It only lowers a rung, a read keeps the rung it was given, and the "
    "configured leash, which is what a page shows, is never rewritten."
)


class InvocationRefusedError(Exception):
    """Raised when a run must not start. Distinct from a run that started and found nothing."""


@dataclass(frozen=True)
class Invocation:
    """Everything one agent run is allowed to do, decided before it starts.

    Frozen, and assembled in one place, because a run whose permissions could change
    part-way through is a run nobody can reconstruct afterwards. The audit entry written at
    the end has to describe the same reach the call actually had.
    """

    principal_id: str
    agent_id: str
    catalogue: ProjectedCatalogue
    #: The strictest rung any target in this catalogue is held to. Computed once, here,
    #: rather than per tool call: a run that could discover it was more trusted than it
    #: thought, half way through, is a run whose ceiling is advisory.
    ceiling_rung: AutonomyTier
    #: The leash this run is held to: the configured one with every entry on a registered
    #: tool held to that tool's leash ceiling. A step inside the run is governed by this one
    #: and never by the leash it was configured with. See
    #: `A_RUN_IS_HELD_TO_THE_RUNG_ITS_TOOLS_SIDE_EFFECTS_ALLOW`.
    leash: Leash
    ent_hash: str
    #: Names only. There is nowhere here to put a row, an argument or a record.
    reachable: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tool_count(self) -> int:
        return len(self.catalogue.tools)


def _strictest_rung(
    leash: Leash, agent_id: str, catalogue: ProjectedCatalogue, row: dict[str, str]
) -> AutonomyTier:
    """The lowest rung across every tool this run can reach.

    Strictest-wins across the catalogue, which is the same rule `leash.rung_for` applies
    across overlapping entries and is applied here for the same reason: a run that took the
    highest rung any of its tools allowed would let one loosely-leashed tool raise the
    trust of every other tool in the same run.

    An empty catalogue never gets here; `invoke` refuses first. If it did, `min` over
    nothing would raise, and the honest answer for "no tools" is not a rung at all.
    """
    rungs = [leash.rung_for(agent_id, tool.name, row) for tool in catalogue.tools]
    # `min` over the enum, because AutonomyTier orders from least to most autonomous and the
    # strictest is therefore the smallest. Written as min rather than as a sort so a member
    # added in the middle of the enum does not silently reorder the answer.
    return min(rungs) if rungs else MISSING_ENTRY_RUNG


def invoke(
    *,
    principal_id: str,
    agent_id: str,
    registry: ToolRegistry,
    entitlement: EntitlementSet,
    ceiling: AgentCeiling,
    leash: Leash,
    assessment: RiskAssessment,
    now: datetime,
    row: dict[str, str] | None = None,
    universal: frozenset[str] = frozenset(),
) -> Invocation:
    """Assemble one agent run, or refuse it.

    The order is the point and it is not rearrangeable: project first, so the tool list is
    the intersection and not the registry; then the leash held to what each tool's side
    effect allows, by the registry that declares the tools; then the rung, computed over the
    intersection from the held leash, so a tool the caller cannot reach cannot influence how
    much the run is trusted and a configured rung cannot outrun its tool; then the injection
    assessment, which may only tighten.

    Raises rather than returning an empty invocation. A caller that got an `Invocation` with
    no tools would have to remember to check, and the check that must be remembered is the
    check that gets skipped in the one path nobody tested.
    """
    try:
        catalogue = project(registry, entitlement, ceiling, now=now, universal=universal)
    except EmptyCatalogueError as exc:
        # Re-raised as a refusal rather than passed through, so a caller distinguishes
        # "this run may not start" from "the projector is broken".
        msg = f"{principal_id} reaches no tool through {agent_id}"
        raise InvocationRefusedError(msg) from exc

    if not catalogue.tools:
        msg = (
            f"{principal_id} reaches no tool through {agent_id}. A model handed no tools "
            "does not stop; it answers from context and training, and that answer looks "
            "exactly like a researched one."
        )
        raise InvocationRefusedError(msg)

    # The configured leash held to each tool's leash ceiling. `tighten` is `min` per entry, so
    # it only ever lowers a rung. See `A_RUN_IS_HELD_TO_THE_RUNG_ITS_TOOLS_SIDE_EFFECTS_ALLOW`.
    held = registry.tighten(leash)
    rung = _strictest_rung(held, agent_id, catalogue, row or {})

    # `autonomy_ceiling` takes the rung the leash allows and can only lower it: there is no
    # branch in it that returns something higher than what it was given. The `min` here is
    # belt as well as braces, so a future edit to that function cannot raise a rung by
    # accident without this line disagreeing.
    tightened = min(rung, autonomy_ceiling(rung, assessment))

    notes: list[str] = []
    if tightened is not rung:
        # Recorded, not silent. A run that quietly dropped a rung is a run whose refusals
        # afterwards look arbitrary.
        notes.append(f"autonomy tightened from {rung.name} to {tightened.name} by risk signals")

    return Invocation(
        principal_id=principal_id,
        agent_id=agent_id,
        catalogue=catalogue,
        ceiling_rung=tightened,
        leash=held,
        ent_hash=entitlement.ent_hash(),
        reachable=catalogue.names,
        notes=tuple(notes),
    )


def run(
    invocation: Invocation,
    body: Callable[[Invocation], object],
) -> object:
    """Execute the body with the invocation in hand.

    A thin seam on purpose. It exists so there is one place a future audit entry, a timing
    record and a trace span can attach without every caller of `invoke` growing its own
    copy of that bookkeeping - and so that the thing being wrapped is an already-decided
    `Invocation` rather than a set of arguments that still has to be checked.
    """
    return body(invocation)
