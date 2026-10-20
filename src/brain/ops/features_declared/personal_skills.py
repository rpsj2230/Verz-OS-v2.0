"""The switch on a person adding skills of their own and offering them to the department.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until an install decides its people may add a skill: adding one stores a procedure somebody
wrote, or fetched from an address or a repository the install's host list admits, and offering it
puts it in front of the people who review the library. Nothing a person adds runs, on their agents
or anyone's, until a named person has approved the exact bytes, so the switch is not what keeps a
skill from running. What it keeps is a member's reach to the install's fetcher and a new kind of
row in the review queue, which an install may want to open to its people only once its reviewers
are ready for them.

Task ids: M40.3.2.2, M40.3.2.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

PERSONAL_SKILLS: Final = Feature(
    name="personal_skills",
    title="Let a person add skills of their own and offer them to the department",
    what=(
        "A person can write a skill, paste one, or bring one from a repository at a commit or an "
        "address, from My workspace. It is theirs alone: no colleague, reviewer or administrator "
        "sees it until they offer it to the department's library, where a named person reads it "
        "and approves or rejects it like any other skill. Nothing runs a skill nobody has "
        "approved."
    ),
    while_off=(
        "Nobody can add a skill of their own or offer one. Skills a person already added stay "
        "theirs and stay listed on their page, and one already offered stays in the review "
        "queue."
    ),
    read_by=("brain.member_skill_routes:personal_skills_are_on",),
)
