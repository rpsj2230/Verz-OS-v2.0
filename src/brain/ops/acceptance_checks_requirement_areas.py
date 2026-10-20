"""The install acceptance checks for five areas' "demonstrated on an install by a person" leaves.

Five leaves ask the same sentence of five areas of `docs/requirements/register.json`: every
permissions (M1.8.8), departments (M2.3.2), models (M5.6.5), observability (M24.3.6) and console
(M27.15.12) requirement "is demonstrated on an install by a person, and each check is recorded
against the requirement it proves". The record is `ops.requirement_check`, which the Requirement
checks screen appends to, and this module reads it.

**A person's demonstration cannot be made by a check, and the check does not pretend to.** What a
check can read is the install's own record of what people saw: the newest check recorded against
each of the area's requirements. The check passes only when every requirement of the area has a
newest check that is a pass, so the leaf closes when the owner's demonstrations are complete and
not before. Rejected: a check that stands up reserved people and replays each requirement itself.
That is the same proof the area's own checks already give, run again, and it would close a leaf
whose whole point is that a person watched it work. Rejected too: counting a requirement as
demonstrated because an acceptance check names its proof leaf. That is the evidence column the
screen already shows beside each row, and it is a different claim from "a person saw it".

**Three outcomes, and the middle one is the honest default on a new install.** A requirement whose
newest check is a failure fails this check, because somebody saw it not work and has not since seen
it work. A requirement nobody has checked yet makes the check not run, in a sentence saying so,
because nothing has failed and nothing has been shown. A register this release does not carry also
makes it not run. Only a complete set of passes passes. The counts are the screen's and are not
repeated in a result (`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`).

**It reads the install's record and writes nothing.** The read goes through the screen's own store
over the check's session, so what is read is what the screen would show an administrator. Each
check is one area, because the four leaves close separately and one area's failure must not hold
another's closed.

**The console's area is the register's `Console` area and no other.** The register also holds
console requirements filed under the area they concern (a skills row from a console screenshot
is `Skills`), and those are demonstrated by their own area's leaf. Counting them here as well
would make this leaf wait on twenty areas' demonstrations to close on the console's own.

Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6, M27.15.12
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.tables.requirement_check import CheckOutcome

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 630

#: The areas of the register, by the name the register gives them and the leaf that asks for each.
AREAS: Final[dict[str, str]] = {
    "Permissions": "M1.8.8",
    "Departments": "M2.3.2",
    "Models": "M5.6.5",
    "Observability": "M24.3.6",
    "Console": "M27.15.12",
}

# ------------------------------------------------------------------ written-down reasons
#: Said when the release carries no register, or none of this area's requirements. Held here and
#: not imported, because a reason is held to a literal in the file that raises it
#: (`tests/unit/test_acceptance.py`).
THIS_RELEASE_CARRIES_NO_REGISTER: Final = (
    "this release carries no requirements register, or none of this area's requirements, so "
    "there is no requirement to look for a recorded check against"
)

#: Said when an area has a requirement with no recorded check. One sentence for the four areas,
#: written without naming one, so a reader of the Install page learns where to go.
SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK: Final = (
    "no person has yet recorded a passing check on the Requirement checks screen against every "
    "requirement of this area, which is what the leaf asks for and which only a person can do"
)


@dataclass(frozen=True)
class Standing:
    """Where one area's requirements stand in the install's record, with no ids and no counts."""

    registered: bool
    failed: bool
    unchecked: bool


async def standing_of(h: Harness, area: str) -> Standing:
    """What the install's record says about every requirement of one area of the register."""
    from brain.requirement_check_routes import DOCS, StoredRequirementChecks
    from brain.requirements import REGISTER_IN_DOCS, load_register

    path = DOCS / REGISTER_IN_DOCS
    if not path.exists():
        return Standing(registered=False, failed=False, unchecked=False)
    rows = [one for one in load_register(path).requirements if one.area == area]
    if not rows:
        return Standing(registered=False, failed=False, unchecked=False)
    latest = await StoredRequirementChecks(h.sessions).latest()
    outcomes = [latest[one.id].outcome if one.id in latest else None for one in rows]
    return Standing(
        registered=True,
        failed=any(one is CheckOutcome.FAILED for one in outcomes),
        unchecked=any(one is None for one in outcomes),
    )


# ------------------------------------------------------------------------ M1.8.8 permissions
@check(
    leaves=("M1.8.8",),
    sentence=(
        "Every permissions requirement in the register has, on this install's Requirement "
        "checks, a newest check recorded by a person that passed: none is unchecked and none is "
        "failing."
    ),
)
async def every_permissions_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Permissions")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a permissions requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M2.3.2 departments
@check(
    leaves=("M2.3.2",),
    sentence=(
        "Every departments requirement in the register has, on this install's Requirement "
        "checks, a newest check recorded by a person that passed: none is unchecked and none is "
        "failing."
    ),
)
async def every_departments_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Departments")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a departments requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M5.6.5 models
@check(
    leaves=("M5.6.5",),
    sentence=(
        "Every models requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_models_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Models")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a models requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M24.3.6 observability
@check(
    leaves=("M24.3.6",),
    sentence=(
        "Every observability requirement in the register has, on this install's Requirement "
        "checks, a newest check recorded by a person that passed: none is unchecked and none is "
        "failing."
    ),
)
async def every_observability_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Observability")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "an observability requirement's newest recorded check is a failure and no person "
            "has passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


# ------------------------------------------------------------------------ M27.15.12 the console
@check(
    leaves=("M27.15.12",),
    sentence=(
        "Every console requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_console_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, "Console")
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a console requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
