"""Skills arriving from another platform: the description, the review, and what to leave behind.

A skill is authored work rather than a setting, so it is the part of a migration a client
notices immediately and the part most likely to be waved through, because it worked over there
yesterday. Four rules, and three of them exist to stop that sentence being the argument.

**A description written for a router is not a description of what a skill does.** The platforms
that route by description have their authors write "Use the invoicing skill to raise an
invoice", because the reader is a model choosing between skills. Here the reader is a person
looking at `brain.tools.skills.SkillCard`, and that sentence reads as an instruction to them:
the card tells somebody to use a thing they are looking at. The conversion is mechanical enough
to detect and not mechanical enough to finish, so `proposed_description` strips the preamble
and hands back a draft, and `router_descriptions` names every skill still in the old form. A
converter that silently produced final text would produce a card estate written in fragments.
See `A_DESCRIPTION_A_ROUTER_READS_IS_NOT_A_DESCRIPTION_A_PERSON_READS`.

**An imported skill starts unreviewed and there is nothing here that could say otherwise.**
`arriving` builds a `brain.tools.skills.ImportedSkill` in the imported state with no reviewer,
and it has no parameter that could carry the old platform's approval. That is the same
structural enforcement as `brain.migration.rebuild.authority_for` having no way to see a
foreign agent: the rule is not that an importer should not carry an approval across, it is
that there is nowhere to put one. It worked over there is a statement about a system with a
different tool catalogue, different data and no ceiling.

**Parsing is not behaviour, and "it parses" is what gets checked.** A skill whose file loads
and whose card renders can still do something different here, because the tools it names are
not the tools it had. So a skill is unproven until somebody has run a real task through it and
recorded whether the answer changed, and `unproven` names the ones nobody has. The check
records the task, because a comparison that does not say what was compared is a tick.

**Anything nobody has invoked in ninety days is retired rather than carried.** The number is
the leaf's and a test reads it from the leaf sentence rather than from a second copy here,
which is the only anchor available for a figure that is a judgement rather than an arithmetic
consequence. Retiring is not deleting: it is declining to spend a review on a skill nobody has
asked for, and the export still holds it.

What was rejected. Converting the description with a model. It is the obvious use for one and
it produces a plausible sentence for every skill, including the ones whose old description was
wrong, and nothing downstream can tell a converted description from an invented one. A
stripped preamble is visibly a draft.

Task ids: M37.2.2.2, M37.2.2.3, M37.2.2.4, M37.2.2.5
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from brain.migration.inventory import MigrationError
from brain.tools.skills import ImportedSkill, Skill, SkillSource


class SkillMigrationError(MigrationError):
    """Raised when a skill would arrive here carrying something from the old platform."""


# ------------------------------------------------------------------ written-down reasons
#: Why the description convention has to change rather than being carried.
A_DESCRIPTION_A_ROUTER_READS_IS_NOT_A_DESCRIPTION_A_PERSON_READS: Final = (
    "A platform that routes by description has its authors write 'Use the invoicing skill "
    "to raise an invoice', because the reader is a model choosing between skills. Here the "
    "reader is a person looking at a card, and that sentence tells them to use the thing "
    "they are looking at. The preamble is detectable and its removal leaves a fragment, so "
    "the conversion produces a draft rather than final text: a converter that returned final "
    "text would leave a card estate written in fragments and nothing would say so."
)

#: Why an approval on the old platform is not an approval here.
IT_WORKED_OVER_THERE_IS_A_STATEMENT_ABOUT_A_DIFFERENT_SYSTEM: Final = (
    "A skill that worked on the old platform worked with that platform's tool catalogue, its "
    "data and no ceiling. Here it names tools it may not hold, over rows it may not reach, "
    "under a leash that did not exist. So an imported skill starts unreviewed, and the "
    "enforcement is that there is no parameter anywhere here that could carry the old "
    "approval, in the same shape as authority_for having no way to see a foreign agent."
)

#: Why a skill that parses is still unproven.
A_FILE_THAT_LOADS_IS_NOT_A_SKILL_THAT_WORKS: Final = (
    "Parsing is the check that gets done, because it is the one that is free. A skill whose "
    "file loads and whose card renders can still answer differently here, because the tools "
    "it names are not the tools it had. It is unproven until somebody has run a real task "
    "through it and recorded whether the answer changed, and the record names the task, "
    "because a comparison that does not say what was compared is a tick."
)

#: Days without an invocation after which a skill is retired rather than carried across.
#:
#: Ninety, and the figure is M37.2.2.5's rather than this module's. A test reads it out of the
#: leaf sentence, which is the only anchor available for a number that is a judgement rather
#: than an arithmetic consequence of something else.
RETIRE_AFTER_DAYS: Final = 90

#: A description written as an instruction to a router.
#:
#: Deliberately narrow. It matches the preamble those platforms actually generate, "use the X
#: skill to", and nothing looser: a pattern that also caught "use this when" would rewrite
#: descriptions that are already about the skill, and a wrong conversion is worse than a
#: missed one, because the missed one is still in `router_descriptions`.
ROUTER_PREAMBLE: Final = re.compile(r"^\s*use\s+(?:the\s+)?(?P<name>.+?)\s+skill\s+to\s+", re.I)


@dataclass(frozen=True)
class ForeignSkill:
    """One skill as the platform being left behind holds it."""

    name: str
    description: str
    last_invoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a foreign skill has no name"
            raise SkillMigrationError(msg)
        if not self.description.strip():
            msg = f"{self.name!r} has no description, so there is nothing to convert or show"
            raise SkillMigrationError(msg)


# ------------------------------------------------------- the description convention (M37.2.2.2)
def proposed_description(foreign: ForeignSkill) -> str:
    """The old description with its router preamble removed, as a draft for a person.

    Returned unchanged when there is no preamble, which is the common case for a skill
    somebody wrote carefully. The result is deliberately not capitalised or repunctuated: a
    fragment that reads as a fragment is one somebody edits, and a tidy sentence is one
    somebody ships.
    """
    return ROUTER_PREAMBLE.sub("", foreign.description, count=1)


def router_descriptions(skills: Sequence[ForeignSkill]) -> tuple[str, ...]:
    """Skills whose description is still written at a router, in inventory order."""
    return tuple(
        f"{one.name}: the description tells a router what to do rather than saying what the "
        "skill does"
        for one in skills
        if ROUTER_PREAMBLE.match(one.description)
    )


# ------------------------------------------------------------- nothing arrives approved (M37.2.2.3)
def arriving(skill: Skill, source: SkillSource) -> ImportedSkill:
    """One imported skill, unreviewed, whatever it was on the old platform.

    **There is no parameter here that could carry an approval**, and there is not meant to be.
    See `IT_WORKED_OVER_THERE_IS_A_STATEMENT_ABOUT_A_DIFFERENT_SYSTEM`. The ordinary review
    path is `brain.tools.skills.ImportedSkill.approve`, which requires a named person and
    stores the digest they approved.
    """
    return ImportedSkill(skill=skill, source=source)


# -------------------------------------------------------- parsing is not behaviour (M37.2.2.4)
@dataclass(frozen=True)
class BehaviourCheck:
    """One real task run through a skill on both systems, and whether the answer changed."""

    skill_name: str
    task: str
    same_answer: bool
    checked_by: str

    def __post_init__(self) -> None:
        if not self.skill_name.strip():
            msg = "a behaviour check names no skill"
            raise SkillMigrationError(msg)
        if not self.task.strip():
            msg = (
                f"the check on {self.skill_name!r} names no task, and a comparison that does "
                "not say what was compared is a tick"
            )
            raise SkillMigrationError(msg)
        if not self.checked_by.strip():
            msg = f"the check on {self.skill_name!r} names nobody who ran it"
            raise SkillMigrationError(msg)


def unproven(skills: Sequence[ForeignSkill], checks: Sequence[BehaviourCheck]) -> tuple[str, ...]:
    """Skills nobody has run a real task through, and the ones where the answer changed.

    Two findings and they are different work. Nobody looked is a task to do. The answer
    changed is a skill to fix, and it is not a failure of the migration: it is the migration
    finding what it was run to find. Both are named because a list of only the first reads as
    a clean import once somebody works through it.
    """
    checked = {one.skill_name for one in checks}
    findings = [
        f"{one.name}: imported and no real task has been run through it"
        for one in skills
        if one.name not in checked
    ]
    findings.extend(
        f"{one.skill_name}: answered {one.task!r} differently after import"
        for one in checks
        if not one.same_answer
    )
    return tuple(findings)


# ------------------------------------------------------- what is left behind (M37.2.2.5)
def to_retire(
    skills: Sequence[ForeignSkill],
    *,
    now: datetime,
    after_days: int = RETIRE_AFTER_DAYS,
) -> tuple[str, ...]:
    """Skills nobody has invoked inside the window, and skills nobody has invoked at all.

    Two sentences rather than one, because they are different evidence. A skill last used four
    months ago was used; a skill with no recorded invocation may never have been used or may
    predate whatever started recording, and saying which is which is the difference between a
    decision and a guess.

    Retiring is not deleting. It is declining to spend a review on a skill nobody has asked
    for, and the export still holds it.
    """
    cutoff = now - timedelta(days=after_days)
    findings = [
        f"{one.name}: never invoked, or invoked before anything recorded it"
        for one in skills
        if one.last_invoked_at is None
    ]
    findings.extend(
        f"{one.name}: last invoked {one.last_invoked_at}, more than {after_days} days ago"
        for one in skills
        if one.last_invoked_at is not None and one.last_invoked_at < cutoff
    )
    return tuple(findings)
