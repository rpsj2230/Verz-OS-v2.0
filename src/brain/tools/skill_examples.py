"""A skill's example tasks, what each expects, and whether a rehearsal of one version cleared them.

M12.3.4: a skill carries example tasks with the behaviour expected of it, and a new version cannot
be approved until those examples have been rehearsed against it.

**The examples are in the `SKILL.md`, so they are in the digest.** A section headed `## Examples`
in the body, one line per example: the task in the words a person would ask it, then `=>`, then
the tools the run is expected to use, or `none`. Rejected: a frontmatter key. The frontmatter
grammar has two shapes, a scalar and an inline list (`brain.tools.skills._parse_scalar_or_list`
argues why), and an example is a sentence with a list beside it; nesting one would mean the third
shape that grammar exists to refuse. Rejected too: example files beside the `SKILL.md`, which
every way in other than a zip would have to refuse. In the body, the examples travel with every
version, an edit that changes them is a new version with a new digest, and an agent that reads the
skill reads them as the worked cases they are. See `EXAMPLES_ARE_PART_OF_THE_VERSION`.

**What a rehearsal judges today is reach, and it says so.** CON-59 says a skill is tested by
rehearsing an agent that holds it, and `brain.agents.install.rehearse` runs no model: it assembles
the run a person would get through the real gate and says what that run reaches. So a rehearsal of
a version, through one agent as the person rehearsing it, checks that every tool each example
expects is within the version's reach for them through that agent, and records an outcome per
example against the version's digest. It cannot judge the answer an example would get, and
`A_REACH_REHEARSAL_JUDGES_WHAT_IS_REACHABLE_AND_NOT_THE_ANSWER` is the limit in words, which the
screen shows beside every result. needs-rupash 161 holds the owner's question; a rehearsal that
runs the examples through the agent runtime is a second `RehearsalKind` in the same table.

**Approval asks for a passing rehearsal of the exact digest.** Any kind, so the day a model-run
kind exists it clears approval with no change here. A version that declares no examples is not
held: there is nothing to rehearse, and the review pane says it carries none. See
`A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_ONCE_A_REHEARSAL_OF_ITS_DIGEST_CLEARS_THEM`.

Task ids: M12.3.4
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.tools.registry import TOOL_NAME_RE
from brain.tools.skills import Skill, SkillError

#: The heading the examples sit under in a `SKILL.md`'s body.
EXAMPLES_HEADING: Final = "## Examples"

#: What separates an example's task from the tools it expects.
EXPECTS: Final = "=>"

#: What an example expecting no tool says after `EXPECTS`.
NO_TOOL: Final = "none"

#: The longest task an example may state, as a person would ask it.
MAX_TASK_CHARS: Final = 300

#: The most examples one version may carry: enough to cover a skill's cases, few enough to read.
MAX_EXAMPLES: Final = 20

#: Why the examples are part of the version.
EXAMPLES_ARE_PART_OF_THE_VERSION: Final = (
    "A skill's examples are written in its SKILL.md under the Examples heading, so they are inside "
    "the digest a reviewer approves. Changing an example is a new version, and a rehearsal or an "
    "approval of one version says nothing about the examples of another."
)

#: The limit of what a rehearsal judges today, said wherever a result is shown.
A_REACH_REHEARSAL_JUDGES_WHAT_IS_REACHABLE_AND_NOT_THE_ANSWER: Final = (
    "This rehearsal checked, for you and through the agent you chose, that every tool each example "
    "expects is within this version's reach. It ran no model, so it did not judge the answer any "
    "example would get; that waits for rehearsals that run the agent (needs-rupash 161)."
)

#: Why approval waits for a rehearsal.
A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_ONCE_A_REHEARSAL_OF_ITS_DIGEST_CLEARS_THEM: Final = (
    "A version that carries example tasks is approved only once a rehearsal recorded against its "
    "exact digest covered every example and every one passed. An approval is a statement about "
    "those bytes, and examples nobody rehearsed against them are a claim nobody checked."
)


class RehearsalKind(enum.StrEnum):
    """What a rehearsal ran. One today; the table holds the word, so another needs no new table."""

    #: The run's reach for the person rehearsing, through one agent, with no model.
    REACH = "reach"


@dataclass(frozen=True)
class SkillExample:
    """One example task and the tools a run of it is expected to use, in the order written."""

    task: str
    expects: tuple[str, ...]


@dataclass(frozen=True)
class ExampleOutcome:
    """What one rehearsal found for one example: passed, or the expected tools out of reach."""

    task: str
    passed: bool
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rehearsal:
    """One rehearsal of one version, as recorded: its kind and every example's outcome."""

    digest: str
    kind: RehearsalKind
    outcomes: tuple[ExampleOutcome, ...]
    #: Who rehearsed it, through which agent, and when. Empty for a rehearsal not yet recorded.
    rehearsed_by: str = ""
    agent_id: str = ""
    at: datetime | None = None

    @property
    def passed(self) -> bool:
        return bool(self.outcomes) and all(one.passed for one in self.outcomes)


def _section(body: str) -> list[str]:
    """The lines under the Examples heading, up to the next heading of the same depth or the end."""
    lines = body.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == EXAMPLES_HEADING]
    if not starts:
        return []
    if len(starts) > 1:
        msg = f"its body has {len(starts)} {EXAMPLES_HEADING!r} sections; keep the examples in one"
        raise SkillError(msg)
    found: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## ") or line.startswith("# "):
            break
        if line.strip():
            found.append(line.strip())
    return found


def examples_of(skill: Skill) -> tuple[SkillExample, ...]:
    """The examples a version carries, or a refusal saying which line to fix.

    Each line is `- <task> => <tool>, <tool>` or `- <task> => none`. An example may expect only
    tools the skill names, because a rehearsal checks the skill's reach and a tool outside its list
    is one it can never reach, which is a mistake in the file rather than a finding about a person.
    """
    examples: list[SkillExample] = []
    for line in _section(skill.body):
        if not line.startswith("- ") or EXPECTS not in line:
            msg = (
                f"the example line {line!r} is not '- <task> {EXPECTS} <tool>, <tool>' or "
                f"'- <task> {EXPECTS} {NO_TOOL}'"
            )
            raise SkillError(msg)
        task, _, tools = line[2:].rpartition(EXPECTS)
        task = task.strip()
        if not task or len(task) > MAX_TASK_CHARS:
            msg = f"an example's task is empty or over {MAX_TASK_CHARS} characters: {line!r}"
            raise SkillError(msg)
        named = tools.strip()
        expects = () if named == NO_TOOL else tuple(one.strip() for one in named.split(","))
        if not named or any(not TOOL_NAME_RE.match(one) for one in expects):
            msg = f"the example {task!r} names its tools as {named!r}, which is not a tool list"
            raise SkillError(msg)
        outside = sorted(set(expects) - set(skill.tools))
        if outside:
            msg = (
                f"the example {task!r} expects {outside}, which the skill does not list in its "
                "tools; a run of this skill can never use a tool it does not name"
            )
            raise SkillError(msg)
        examples.append(SkillExample(task=task, expects=expects))
    if len(examples) > MAX_EXAMPLES:
        msg = f"it carries {len(examples)} examples, over the {MAX_EXAMPLES} one version may carry"
        raise SkillError(msg)
    tasks = [one.task for one in examples]
    if len(set(tasks)) != len(tasks):
        msg = "two of its examples state the same task; a task is how an outcome is matched to it"
        raise SkillError(msg)
    return tuple(examples)


def rehearse_reach(
    examples: Sequence[SkillExample], reachable: Iterable[str]
) -> tuple[ExampleOutcome, ...]:
    """Each example's outcome when a run reaches exactly `reachable`: passed, or what it lacks."""
    held = frozenset(reachable)
    return tuple(
        ExampleOutcome(
            task=one.task,
            passed=set(one.expects) <= held,
            missing=tuple(sorted(set(one.expects) - held)),
        )
        for one in examples
    )


def rehearsal_clears(
    digest: str, examples: Sequence[SkillExample], rehearsals: Iterable[Rehearsal]
) -> bool:
    """Whether a rehearsal of this exact digest covered every example and every one passed.

    True for a version carrying no examples, which has nothing to rehearse. See
    `A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_ONCE_A_REHEARSAL_OF_ITS_DIGEST_CLEARS_THEM`.
    """
    if not examples:
        return True
    wanted = {one.task for one in examples}
    return any(
        one.digest == digest and one.passed and {outcome.task for outcome in one.outcomes} == wanted
        for one in rehearsals
    )
