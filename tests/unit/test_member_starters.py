"""An agent's starter prompts: the example tasks its skills carry that a run could carry out.

Real skills parsed from real text, a real registry and a real install, so what is asserted is what
the platform's own types do. **Every refusal has a sibling proving the permitted case is offered.**

Task ids: M40.7.8
"""

from __future__ import annotations

from brain.gate.model_lane import AgentRun
from brain.member_starters import MOST_STARTERS, starters_for, starters_from
from brain.tools.skills import SkillPin
from tests.unit.test_skill_library import (
    AGENT,
    NOW,
    a_registry,
    an_approved_skill,
    an_install,
    reach,
)


def skill_text(
    name: str = "hosting-expiry",
    *,
    tools: str = "[crm.read_client]",
    knowledge: str = "",
    examples: tuple[str, ...] = ("- When does this client's hosting expire? => crm.read_client",),
) -> str:
    lines = [
        "---",
        f"name: {name}",
        "description: Use when a client asks whether their domain is close to renewal",
        "version: 1.0.0",
        f"tools: {tools}",
        *([f"knowledge: {knowledge}"] if knowledge else []),
        "---",
        "Look up the domain, then open a ticket.",
        "",
        "## Examples",
        *examples,
    ]
    return "\n".join(lines) + "\n"


def a_run(*texts: str) -> AgentRun:
    skills = tuple(an_approved_skill(one) for one in texts)
    _, _, record = an_install()
    pins = tuple(SkillPin(agent_id=AGENT, skill_name=s.name, digest=s.digest) for s in skills)
    return AgentRun(record=record, pins=pins, library=skills, registry=a_registry())


def test_an_agent_offers_the_example_task_of_a_skill_the_person_can_run() -> None:
    """The positive case for every refusal below. Delete this and a function offering nothing
    passes them all."""
    run = a_run(skill_text())
    assert starters_for(run, caller=reach("read:client.name"), now=NOW) == (
        "When does this client's hosting expire?",
    )


def test_a_task_needing_a_tool_the_run_cannot_reach_is_not_offered_and_nothing_says_so() -> None:
    """A person without the tool's capability is offered nothing, the answer an agent with no
    examples gives. Delete this and a button is offered that the system knows will fail."""
    assert starters_for(a_run(skill_text()), caller=reach(), now=NOW) == ()


def test_a_skill_needing_a_department_the_run_does_not_cover_is_not_offered() -> None:
    """Knowledge is cut by department, so a starter that reads one the person cannot is out. Delete
    this and the starters could point a person at a department's documents."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope

    run = a_run(skill_text(knowledge="[finance]"))
    elsewhere = EntitlementSet(
        principal_id="u_member",
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
            Grant(capability=Capability(value="read:knowledge"), scope=Scope.department("sales")),
        ),
    )
    assert starters_for(run, caller=elsewhere, now=NOW) == ()


def test_an_unpinned_skill_contributes_nothing() -> None:
    """Only what the agent carries is offered. Delete this and every skill in the library
    suggests questions to every agent."""
    skill = an_approved_skill(skill_text())
    _, _, record = an_install()
    run = AgentRun(record=record, pins=(), library=(skill,), registry=a_registry())
    assert starters_for(run, caller=reach("read:client.name"), now=NOW) == ()


def test_at_most_three_are_offered_in_skill_name_order_and_each_task_once() -> None:
    """Three, in a stable order, without repeats. Delete this and a long list is a menu, or two
    readings of the same agent differ."""
    many = tuple(f"- Question {n} about renewals? => crm.read_client" for n in range(5))
    run = a_run(
        skill_text("zeta", examples=(many[0], many[1], many[4])),
        skill_text("alpha", examples=(many[0], many[3])),
    )
    found = starters_for(run, caller=reach("read:client.name"), now=NOW)
    assert MOST_STARTERS == 3
    assert found == (
        "Question 0 about renewals?",
        "Question 3 about renewals?",
        "Question 1 about renewals?",
    )


def test_a_stored_skill_with_examples_that_do_not_parse_offers_nothing_and_does_not_raise() -> None:
    """The library refuses such a skill, but a row edited by hand can still hold one. Delete this
    and one bad row takes an agent's starters away with an error."""
    from brain.tools.skills import ImportedSkill, SkillSource, SourceKind, skill_from_markdown

    broken = ImportedSkill(
        skill=skill_from_markdown(skill_text("broken", examples=("- no arrow here",))),
        source=SkillSource(kind=SourceKind.UPLOAD, location="SKILL.md", content_digest="0" * 64),
    )
    fine = an_approved_skill(skill_text("fine")).imported
    found = starters_from([broken, fine], reach=reach("read:client.name"), now=NOW)
    assert found == ("When does this client's hosting expire?",)


def test_the_pure_step_reads_nothing_of_the_person_but_the_reach_it_is_handed() -> None:
    """`starters_from` takes the skills a run offers and the run's reach and nothing else. Delete
    this and a hidden argument (a name, a department) could widen what is offered."""
    import inspect

    assert list(inspect.signature(starters_from).parameters) == ["offered", "reach", "now"]


def test_a_department_only_the_caller_reads_is_not_covered_when_the_agent_cannot_read_it() -> None:
    """The run's reach is the caller's narrowed by the agent, so knowledge the caller holds and the
    agent's ceiling lacks is not covered. Delete this and starters are decided at the caller's own
    reach, which offers a question the run cannot answer."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope

    run = a_run(skill_text(knowledge="[finance]"))
    caller = EntitlementSet(
        principal_id="u_member",
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
            Grant(capability=Capability(value="read:knowledge"), scope=Scope.department("finance")),
        ),
    )
    assert starters_for(run, caller=caller, now=NOW) == ()
