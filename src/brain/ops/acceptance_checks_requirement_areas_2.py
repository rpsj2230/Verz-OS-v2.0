"""The install checks for five more areas' "demonstrated on an install by a person" leaves.

`brain.ops.acceptance_checks_requirement_areas` reads the install's own record of what people saw
(`ops.requirement_check`, appended to by the Requirement checks screen) for four areas, and this
module is the same question asked of five more: agents (M13.8.12), the harness (M13.8.14), entity
resolution (M14.8.2), memory (M16.7.11) and learning (M16.7.9). It imports that module's
`standing_of` and writes no second reading of the record, so the two cannot disagree about what
"demonstrated" means.

**A person's demonstration cannot be made by a check, and the check does not pretend to.** It passes
only when every requirement of the area has a newest recorded check that passed, fails when the
newest is a failure, and says not run, in a sentence naming nothing, while a requirement has none.
Rejected: replaying each requirement from here, which repeats the proof the area's own checks
already give and would close a leaf whose point is that a person watched it work. Each area is its
own check because the five leaves close separately.

Task ids: M13.8.12, M13.8.14, M14.8.2, M16.7.11, M16.7.9
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_requirement_areas import standing_of
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 852

#: The areas of the register, by the name the register gives them and the leaf that asks for each.
AREAS: Final[dict[str, str]] = {
    "Agents": "M13.8.12",
    "Harness": "M13.8.14",
    "Entity resolution": "M14.8.2",
    "Memory": "M16.7.11",
    "Learning": "M16.7.9",
}

#: Said when the release carries no register, or none of this area's requirements. Held here as a
#: literal, as a reason is held to a literal in the file that raises it.
THIS_RELEASE_CARRIES_NO_REGISTER: Final = (
    "this release carries no requirements register, or none of this area's requirements, so "
    "there is no requirement to look for a recorded check against"
)

#: Said when an area has a requirement with no recorded check.
SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK: Final = (
    "no person has yet recorded a passing check on the Requirement checks screen against every "
    "requirement of this area, which is what the leaf asks for and which only a person can do"
)


# ------------------------------------------------------------------------ M13.8.12 agents
@check(
    leaves=("M13.8.12",),
    sentence=(
        "Every agents requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_agents_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Agents")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "an agents requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M13.8.14 harness
@check(
    leaves=("M13.8.14",),
    sentence=(
        "Every harness requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_harness_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Harness")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a harness requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M14.8.2 entity resolution
@check(
    leaves=("M14.8.2",),
    sentence=(
        "Every entity resolution requirement in the register has, on this install's Requirement "
        "checks, a newest check recorded by a person that passed: none is unchecked and none is "
        "failing."
    ),
)
async def every_entity_resolution_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Entity resolution")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "an entity resolution requirement's newest recorded check is a failure and no "
            "person has passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M16.7.11 memory
@check(
    leaves=("M16.7.11",),
    sentence=(
        "Every memory requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_memory_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Memory")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a memory requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M16.7.9 learning
@check(
    leaves=("M16.7.9",),
    sentence=(
        "Every learning requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_learning_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Learning")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a learning requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
