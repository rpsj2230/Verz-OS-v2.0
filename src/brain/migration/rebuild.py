"""Rebuilding an agent that came from a platform with no ceiling and no leash.

A predecessor assistant platform describes an agent as a prompt, a list of tools and one
notion of who could use it. This system describes an agent as four separate things, and three
of them have no counterpart over there. Importing the configuration is therefore not a
conversion, it is a guess dressed as one, and the guess is made by whoever wrote the importer
rather than by anybody who will live with the result.

**So an agent is rebuilt from a template, and this module cannot represent an import.**
`Rebuild` has a template id and no field for the foreign prompt or the foreign tool list.
That is the enforcement: not a rule in a runbook that an importer could quietly stop
following, but a record that has nowhere to put the thing that must not be carried, in the
same shape as `brain.migration.carry.EntitySeed`, which has nowhere to put the old system's
access. See `A_CONFIGURATION_WITH_NO_CEILING_IN_IT_CONVERTS_TO_NOTHING`.

**Availability and authority are two answers and the platform being left behind had one.**
Who may see and start an agent, and what a run through it may reach, are `AgentAudience` and
`AgentAuthority` here, and the mistake worth designing against is deriving the second from
the first: an agent everybody can see becoming an agent that can reach everything. The
enforcement is again structural. `audience_for` is the only function here that takes a
foreign record, and `authority_for` has no parameter that could carry one, so the ceiling
cannot be derived from the old system's availability by any code path at all, and a test
asserts that of the signature rather than of the behaviour. See
`AVAILABILITY_IS_NOT_AUTHORITY_AND_ONE_FIELD_CANNOT_BE_TWO`.

**Every rebuilt agent starts at Shadow on writes, whatever it did before.** How an agent
behaved on a platform that narrowed nothing is not evidence about how it behaves under a
ceiling, because the two are not the same agent: the reach changed, the tools changed and the
prompt was rewritten. The tier is a required field with no default and only one accepted
value, so a rebuild that wants to start higher has to change this module and argue for it.
See `BEHAVIOUR_UNDER_NO_CEILING_IS_NOT_EVIDENCE_ABOUT_BEHAVIOUR_UNDER_ONE`.

**An explicit ceiling names at least one capability.** The old platform had no ceiling, and
the correction is not an empty one: an authority with no capabilities intersects to nothing,
so the agent reaches no data at all and is a placeholder somebody will widen later, in a
hurry, without the argument that belongs beside it. `authority_for` refuses it, which is the
one thing that function is for besides not being able to see the foreign record.

What was rejected. Mapping the foreign availability with a table in this module. Every
platform spells its levels differently and the mapping is a decision about one company's
agents, so it is a parameter, and an availability nobody mapped is a refusal rather than a
default to the narrowest level. Defaulting to the narrowest is the tempting version and it
is wrong in the way that matters: it is silent, it produces an agent nobody can see, and the
fix somebody applies at that point is to widen the audience without reading the mapping.

Task ids: M37.2.3.1, M37.2.3.2, M37.2.3.3, M37.2.3.4
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.agents.model import AgentAudience, AgentAuthority
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.knowledge.visibility import Visibility
from brain.migration.inventory import MigrationError


class RebuildError(MigrationError):
    """Raised when a rebuilt agent would carry something across that cannot be carried."""


# ------------------------------------------------------------------ written-down reasons
#: Why a foreign agent's configuration is not imported.
A_CONFIGURATION_WITH_NO_CEILING_IN_IT_CONVERTS_TO_NOTHING: Final = (
    "A predecessor platform describes an agent as a prompt, a tool list and one notion of "
    "who may use it. Three of the four things this system needs have no counterpart there, "
    "so an import is a guess made by whoever wrote the importer rather than by anybody who "
    "will live with the result. A rebuild carries a template id and the record has nowhere "
    "to put the foreign prompt or tool list, which is a rule that cannot be quietly stopped "
    "being followed."
)

#: Why the ceiling cannot be derived from who could use the agent.
AVAILABILITY_IS_NOT_AUTHORITY_AND_ONE_FIELD_CANNOT_BE_TWO: Final = (
    "Who may see and start an agent, and what a run through it may reach, are two answers, "
    "and the platform being left behind had one field for both. Derived one from the other, "
    "an agent everybody can see becomes an agent that can reach everything, which is the "
    "single worst outcome of a migration and the one nobody notices, because the agent "
    "works. audience_for is the only function here that sees a foreign record and "
    "authority_for has no parameter that could carry one."
)

#: Why every rebuilt agent starts at Shadow on writes.
BEHAVIOUR_UNDER_NO_CEILING_IS_NOT_EVIDENCE_ABOUT_BEHAVIOUR_UNDER_ONE: Final = (
    "An agent that behaved well on a platform that narrowed nothing tells you nothing about "
    "this one, because it is not the same agent: the reach changed, the tools changed and "
    "the prompt was rewritten from a template. The tier is required, has no default and "
    "accepts one value, so starting higher means changing this module and arguing for it."
)


@dataclass(frozen=True)
class ForeignAgent:
    """One agent as the platform being left behind describes it.

    Everything here is somebody else's vocabulary, kept as strings deliberately: coercing an
    availability or a tool name into this system's types at read time is exactly the
    assumption the module exists to prevent.
    """

    name: str
    availability: str
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a foreign agent has no name, so no rebuild can be matched to it"
            raise RebuildError(msg)
        if not self.availability.strip():
            msg = (
                f"{self.name!r} records no availability, and the level it maps onto is the "
                "one decision that cannot be guessed from the rest of the record"
            )
            raise RebuildError(msg)


def audience_for(
    foreign: ForeignAgent,
    *,
    mapping: Mapping[str, Visibility],
    owner_id: str,
    department: str = "",
) -> AgentAudience:
    """Who may see and start the rebuilt agent, from the old platform's availability.

    The mapping is a parameter because every platform spells its levels differently and the
    answer is a decision about one company's agents. An availability nobody mapped is a
    refusal: defaulting to the narrowest level is silent, produces an agent nobody can see,
    and the fix somebody reaches for at that point is to widen the audience rather than to
    read the mapping.

    This is the only function in this module that takes a foreign record, and that is the
    whole of `AVAILABILITY_IS_NOT_AUTHORITY_AND_ONE_FIELD_CANNOT_BE_TWO`.
    """
    level = mapping.get(foreign.availability)
    if level is None:
        msg = (
            f"{foreign.name!r} is available to {foreign.availability!r} over there and nothing "
            "says what that means here"
        )
        raise RebuildError(msg)
    return AgentAudience(level=level, owner_id=owner_id, department=department)


def authority_for(
    *,
    capabilities: Sequence[Capability],
    scope: Scope | None = None,
    allowed_tools: frozenset[str] = frozenset(),
    required_tools: frozenset[str] = frozenset(),
    max_side_effect: SideEffect = SideEffect.NONE,
) -> AgentAuthority:
    """What a run through the rebuilt agent may reach, at most.

    **There is no parameter here that could carry a `ForeignAgent`**, and there is not meant
    to be. The ceiling is a decision somebody takes with the agent's job in front of them,
    and the shape of this signature is what stops the old platform's availability reaching it.

    An empty capability set is refused. The old platform had no ceiling and an empty one is
    not the correction: it intersects to nothing, so the agent reaches no data, and what
    happens next is somebody widening it in a hurry without the argument that belongs beside
    it.
    """
    if not capabilities:
        msg = (
            "a ceiling with no capabilities reaches nothing, so the agent does nothing and "
            "somebody widens it later without the argument. Name what it may reach."
        )
        raise RebuildError(msg)
    missing = required_tools - allowed_tools
    if missing:
        msg = f"required tools that are not allowed: {sorted(missing)}"
        raise RebuildError(msg)
    return AgentAuthority(
        scope=Scope() if scope is None else scope,
        capabilities=tuple(capabilities),
        allowed_tools=allowed_tools,
        required_tools=required_tools,
        max_side_effect=max_side_effect,
    )


@dataclass(frozen=True)
class Rebuild:
    """One agent rebuilt here, and what it was called over there.

    `foreign_name` is provenance and nothing more: it is how `rebuild_gaps` matches a rebuild
    to the inventory, and there is deliberately no field holding the foreign prompt or tool
    list. See `A_CONFIGURATION_WITH_NO_CEILING_IN_IT_CONVERTS_TO_NOTHING`.
    """

    foreign_name: str
    template_id: str
    audience: AgentAudience
    authority: AgentAuthority
    write_tier: AutonomyTier
    because: str

    def __post_init__(self) -> None:
        if not self.foreign_name.strip():
            msg = "a rebuild names no agent it replaces"
            raise RebuildError(msg)
        if not self.template_id.strip():
            msg = (
                f"{self.foreign_name!r} was rebuilt from no template, which is an import "
                "wearing the word rebuild"
            )
            raise RebuildError(msg)
        if self.write_tier is not AutonomyTier.SHADOW:
            msg = (
                f"{self.foreign_name!r} starts at {self.write_tier.name} on writes. "
                f"{BEHAVIOUR_UNDER_NO_CEILING_IS_NOT_EVIDENCE_ABOUT_BEHAVIOUR_UNDER_ONE}"
            )
            raise RebuildError(msg)
        if not self.because.strip():
            msg = f"{self.foreign_name!r} was rebuilt with no record of what it is for"
            raise RebuildError(msg)


def rebuild_gaps(foreign: Sequence[ForeignAgent], rebuilds: Sequence[Rebuild]) -> tuple[str, ...]:
    """Agents on the old platform nobody has rebuilt, and rebuilds of agents nobody found.

    Both directions, in the order somebody works them. An agent with no rebuild is the work
    that is left. A rebuild naming an agent the inventory does not hold is the more
    interesting finding: it is an agent somebody built from memory, and what it was given is
    whatever they remembered.
    """
    rebuilt = {one.foreign_name for one in rebuilds}
    found = {one.name for one in foreign}
    findings = [one.name for one in foreign if one.name not in rebuilt]
    return tuple(
        [f"{name}: on the old platform and not rebuilt" for name in findings]
        + [
            f"{name}: rebuilt and not in the inventory, so it was built from memory"
            for name in sorted(rebuilt - found)
        ]
    )
