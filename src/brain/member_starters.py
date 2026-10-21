"""Three things to ask an agent, drawn from what it can do for this person and nothing else.

Opening an agent on Ask used to show an empty box. The agent's skills already carry example tasks
their authors wrote (`brain.tools.skill_examples`), and those are the best thing to offer, so the
starters are those tasks. **The rule is that a starter is never one the person's run could not
carry out** (M40.7.8), and it is decided from the run and not from the skill alone: only skills
`brain.gate.model_lane.skills_offered` would offer (pinned, approved, unchanged and every tool
within `E_run(caller, agent)`) contribute, and of those only the ones whose knowledge needs the
run's reach covers, department by department.

**Nothing is said about what was left out.** A person whose reach covers nothing is offered no
starters, which is the answer a person is given when the agent has no examples, so the list cannot
be used to learn what the agent's skills or the company's departments are. There is no count, no
greyed prompt and no sentence about a skill the person cannot use.

**Read at the reach the run holds, with the instant told.** The caller's reach is narrowed by the
agent through `run_reach`, the one intersection, and every scope is asked with `now`.

Rejected: generating prompts with a model. A prompt a model wrote can name a department or a
figure the person may not see, and the check "could this run answer it" would have nothing to
check it against; an example task an author wrote and a reviewer read is bounded by its text.
Rejected: showing every example and refusing at the run, which offers the person a button the
system knows will fail.

Task ids: M40.7.8
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from brain.console.workspace_capabilities import run_reach
from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import EntitlementSet
from brain.gate.model_lane import AgentRun, skills_offered
from brain.knowledge.search import KNOWLEDGE_READ
from brain.tools.skill_examples import examples_of
from brain.tools.skills import ImportedSkill, SkillError

#: How many starters one agent offers. Three, because a list longer than that is a menu.
MOST_STARTERS: Final = 3


def _knowledge_covered(skill: ImportedSkill, reach: EntitlementSet, now: datetime) -> bool:
    """Whether the run's reach reads every department the skill says it needs."""
    needed = skill.skill.knowledge
    if not needed:
        return True
    scope = reach.scope_for(KNOWLEDGE_READ, now)
    return scope is not None and all(scope.matches({DEPARTMENT_FIELD: name}) for name in needed)


def starters_from(
    offered: Sequence[ImportedSkill], *, reach: EntitlementSet, now: datetime
) -> tuple[str, ...]:
    """Up to `MOST_STARTERS` example tasks of these skills, each skill's in the order written.

    Skills in name order so two readings of unchanged skills are the same list; a task a skill's
    examples repeat, or another skill repeats, is offered once. A skill whose examples do not
    parse offers nothing, since a skill that does not parse is one the library should show a
    reviewer and not a member.
    """
    found: list[str] = []
    for skill in sorted(offered, key=lambda one: one.skill.name):
        if not _knowledge_covered(skill, reach, now):
            continue
        try:
            examples = examples_of(skill.skill)
        except SkillError:
            continue
        for example in examples:
            if example.task not in found:
                found.append(example.task)
    return tuple(found[:MOST_STARTERS])


def starters_for(run: AgentRun, *, caller: EntitlementSet, now: datetime) -> tuple[str, ...]:
    """The starters for one agent as this caller would run it. What the route calls."""
    return starters_from(
        skills_offered(run, caller=caller, now=now), reach=run_reach(caller, run.record), now=now
    )
