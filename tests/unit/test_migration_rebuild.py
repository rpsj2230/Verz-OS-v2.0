"""Rebuilding an agent from a platform that had no ceiling and no leash."""

from __future__ import annotations

import inspect

import pytest

from brain.agents.model import AgentAudience, AgentAuthority
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect
from brain.core.scope import Clause, Op, Scope
from brain.gate.injection import AutonomyTier
from brain.knowledge.visibility import Visibility
from brain.migration.rebuild import (
    ForeignAgent,
    Rebuild,
    RebuildError,
    audience_for,
    authority_for,
    rebuild_gaps,
)

READS_CLIENTS = Capability(value="read:client.name")
MAPPING = {
    "everyone": Visibility.COMPANY,
    "my team": Visibility.DEPARTMENT,
    "just me": Visibility.PERSONAL,
}


def a_foreign(name: str = "Reporting bot", availability: str = "everyone") -> ForeignAgent:
    return ForeignAgent(name=name, availability=availability, tools=("search", "email"))


def an_authority() -> AgentAuthority:
    return authority_for(capabilities=(READS_CLIENTS,))


def a_rebuild(**kw: object) -> Rebuild:
    fields: dict[str, object] = {
        "foreign_name": "Reporting bot",
        "template_id": "reporting.v3",
        "audience": AgentAudience(level=Visibility.COMPANY, owner_id="u_priya"),
        "authority": an_authority(),
        "write_tier": AutonomyTier.SHADOW,
        "because": "it answers the weekly hours question and nothing else",
    }
    fields.update(kw)
    return Rebuild(**fields)  # type: ignore[arg-type]


# ------------------------------------------------- the configuration does not come across
def test_a_rebuild_has_nowhere_to_put_the_foreign_prompt_or_tool_list() -> None:
    """**M37.2.3.1 asks for a rebuild from a template rather than an import, and this is the
    enforcement.** A rule in a runbook is one an importer can quietly stop following; a record
    with nowhere to put the thing that must not be carried cannot be.

    Asserted on the field set rather than on an instance, because an instance with those
    fields left unset is what a default produces and would pass whether they existed or not.
    It is the same argument as `brain.migration.carry.EntitySeed` having nowhere to hold the
    old system's access.

    Delete this and an `instructions` field can be added with every other test still green,
    and the first importer to be written will fill it in."""
    assert set(Rebuild.__dataclass_fields__) == {
        "foreign_name",
        "template_id",
        "audience",
        "authority",
        "write_tier",
        "because",
    }


def test_a_rebuild_from_no_template_is_refused() -> None:
    """An import wearing the word rebuild. The template is what makes the prompt this
    system's rather than the old one's.

    Delete this and the blank branch is unreachable, and "rebuilt" becomes a label."""
    with pytest.raises(RebuildError, match="rebuilt from no template"):
        a_rebuild(template_id="  ")


def test_a_rebuild_naming_no_agent_is_refused() -> None:
    """The provenance is how `rebuild_gaps` matches a rebuild to the inventory, so a blank one
    is a rebuild that no inventory check can see.

    Delete this and an unmatched rebuild reports as covering an agent called nothing."""
    with pytest.raises(RebuildError, match="names no agent"):
        a_rebuild(foreign_name="")


def test_a_rebuild_with_no_record_of_what_it_is_for_is_refused() -> None:
    """The ceiling below is a decision, and the reason is what somebody re-reads before
    widening it.

    Delete this and the register holds ceilings with no arguments behind them, which is the
    state the old platform was in with extra fields."""
    with pytest.raises(RebuildError, match="no record of what it is for"):
        a_rebuild(because=" ")


# ------------------------------------------------------- Shadow on writes, whatever it did
def test_every_rebuilt_agent_starts_at_shadow_on_writes() -> None:
    """**M37.2.3.3, and the argument is that it is not the same agent.** How it behaved on a
    platform that narrowed nothing is not evidence about how it behaves under a ceiling: the
    reach changed, the tools changed and the prompt was rewritten from a template.

    Delete this and the tier becomes a field somebody sets from what the old platform's
    dashboard said, which is a measurement of a different system."""
    with pytest.raises(RebuildError, match="starts at AUTONOMOUS on writes"):
        a_rebuild(write_tier=AutonomyTier.AUTONOMOUS)


def test_starting_at_assisted_is_refused_too() -> None:
    """The middle rung, which is the one somebody argues for: it has a person in the loop, so
    it sounds cautious. It is still a real artefact rendered and sent for approval, by an
    agent whose reach nobody has watched yet.

    Delete this and the check can be written as "not autonomous", which admits the rung
    people actually ask for."""
    with pytest.raises(RebuildError, match="starts at ASSISTED on writes"):
        a_rebuild(write_tier=AutonomyTier.ASSISTED)


def test_a_rebuild_at_shadow_with_everything_stated_is_accepted() -> None:
    """The positive case for every refusal above.

    Delete this and `Rebuild` can be tightened until no agent is ever rebuilt."""
    rebuilt = a_rebuild()

    assert rebuilt.write_tier is AutonomyTier.SHADOW
    assert rebuilt.template_id == "reporting.v3"


# ------------------------------------------ availability and authority are two answers
def test_the_ceiling_cannot_be_derived_from_the_old_platform_s_availability() -> None:
    """**M37.2.3.4, asserted on the signature rather than on the behaviour.**

    Deriving authority from availability turns an agent everybody can see into an agent that
    can reach everything, which is the worst outcome of a migration and the one nobody
    notices, because the agent works. `authority_for` has no parameter that could carry a
    foreign record, so no code path can do it, and that is a stronger statement than any test
    of what it returns for a given input.

    Delete this and a `foreign` parameter can be added "for convenience", and the next person
    reads the availability off it because it is right there."""
    parameters = inspect.signature(authority_for).parameters

    assert "foreign" not in parameters
    assert all(one.annotation is not ForeignAgent for one in parameters.values())
    assert set(parameters) == {
        "capabilities",
        "scope",
        "allowed_tools",
        "required_tools",
        "max_side_effect",
    }


def test_an_availability_nobody_mapped_is_refused_rather_than_defaulted() -> None:
    """**Defaulting to the narrowest level is the tempting version and it is wrong in the way
    that matters.** It is silent, it produces an agent nobody can see, and the fix somebody
    applies then is to widen the audience rather than to read the mapping.

    Delete this and every unmapped availability becomes a personal agent, and the migration
    ends with a set of agents whose audiences were decided by an omission."""
    with pytest.raises(RebuildError, match="nothing says what that means here"):
        audience_for(
            a_foreign(availability="partners"),
            mapping=MAPPING,
            owner_id="u_priya",
        )


def test_a_mapped_availability_becomes_the_audience_it_maps_to() -> None:
    """The positive case, and it uses the mapping rather than the level's name, so a platform
    that calls its widest level "just me" maps where the mapping says.

    Delete this and `audience_for` can be written to read the string, which is right for one
    platform's vocabulary and wrong for the next."""
    audience = audience_for(a_foreign(), mapping=MAPPING, owner_id="u_priya")

    assert audience.level is Visibility.COMPANY
    assert audience.owner_id == "u_priya"


def test_a_department_audience_carries_its_department() -> None:
    """The one level that needs a second value, and `AgentAudience` refuses it without one, so
    this proves the parameter is passed through rather than dropped.

    Delete this and a departmental agent is built with no department, which `AgentAudience`
    refuses, and the failure appears at a call site rather than here."""
    audience = audience_for(
        a_foreign(availability="my team"),
        mapping=MAPPING,
        owner_id="u_priya",
        department="web",
    )

    assert audience.level is Visibility.DEPARTMENT
    assert audience.department == "web"


def test_a_foreign_agent_with_no_availability_is_refused() -> None:
    """The level it maps onto is the one decision that cannot be guessed from the rest of the
    record, so a blank one is a record that cannot be migrated rather than one that maps to a
    default.

    Delete this and a blank availability reaches the mapping, misses, and reports as an
    availability nobody mapped, which sends somebody to add a mapping for the empty string."""
    with pytest.raises(RebuildError, match="records no availability"):
        ForeignAgent(name="Reporting bot", availability="  ")


def test_a_foreign_agent_with_no_name_is_refused() -> None:
    """Delete this and the blank branch is unreachable."""
    with pytest.raises(RebuildError, match="has no name"):
        ForeignAgent(name=" ", availability="everyone")


# ------------------------------------------------------------- the ceiling is explicit
def test_a_ceiling_with_no_capabilities_is_refused() -> None:
    """**M37.2.3.2 asks for an explicit ceiling, and an empty one is not the correction for
    having had none.** It intersects to nothing, so the agent reaches no data, and what
    happens next is somebody widening it in a hurry without the argument that belongs beside
    it.

    Delete this and every rebuild passes with the default authority, which is the state the
    old platform was in with more fields."""
    with pytest.raises(RebuildError, match="reaches nothing"):
        authority_for(capabilities=())


def test_a_required_tool_that_is_not_allowed_is_refused() -> None:
    """`AgentCeiling` refuses this too, and refusing it here means the failure names the agent
    being rebuilt rather than appearing later against an id nobody recognises.

    Delete this and the contradiction survives until a run projects the catalogue."""
    with pytest.raises(RebuildError, match=r"required tools that are not allowed: \['send'\]"):
        authority_for(
            capabilities=(READS_CLIENTS,),
            allowed_tools=frozenset({"search"}),
            required_tools=frozenset({"send"}),
        )


def test_a_stated_ceiling_narrows_on_every_axis_it_was_given() -> None:
    """The positive case, and it checks all four axes travel, because a wrapper that dropped
    one would produce a ceiling wider than the one somebody agreed to.

    Delete this and `authority_for` can drop its scope, which widens every rebuilt agent from
    a department to the company with nothing going red."""
    scope = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))

    authority = authority_for(
        capabilities=(READS_CLIENTS,),
        scope=scope,
        allowed_tools=frozenset({"search", "send"}),
        required_tools=frozenset({"search"}),
        max_side_effect=SideEffect.DRAFT,
    )

    assert authority.scope == scope
    assert authority.capabilities == (READS_CLIENTS,)
    assert authority.allowed_tools == frozenset({"search", "send"})
    assert authority.required_tools == frozenset({"search"})
    assert authority.max_side_effect is SideEffect.DRAFT


# ------------------------------------------------------------------- the two directions
def test_an_agent_on_the_old_platform_with_no_rebuild_is_reported() -> None:
    """The work that is left, in inventory order so whoever is working the list works the
    export rather than an alphabetical rearrangement of it.

    Delete this and an agent is dropped from the migration by nobody deciding to drop it."""
    found = (a_foreign("Reporting bot"), a_foreign("Leave bot"))

    assert rebuild_gaps(found, (a_rebuild(),)) == (
        "Leave bot: on the old platform and not rebuilt",
    )


def test_a_rebuild_of_an_agent_the_inventory_never_saw_is_the_more_interesting_finding() -> None:
    """It is an agent somebody built from memory, and what it was given is whatever they
    remembered, including a ceiling nobody compared against anything.

    Delete this and the direction that finds invented agents is gone, and only the direction
    that finds missing ones remains."""
    found = (a_foreign("Reporting bot"),)
    rebuilds = (a_rebuild(), a_rebuild(foreign_name="Invoice bot"))

    assert rebuild_gaps(found, rebuilds) == (
        "Invoice bot: rebuilt and not in the inventory, so it was built from memory",
    )


def test_an_inventory_rebuilt_one_for_one_has_no_findings() -> None:
    """The positive case for both directions.

    Delete this and `rebuild_gaps` can be written to report every agent."""
    found = (a_foreign("Reporting bot"), a_foreign("Leave bot"))
    rebuilds = (a_rebuild(), a_rebuild(foreign_name="Leave bot"))

    assert rebuild_gaps(found, rebuilds) == ()
