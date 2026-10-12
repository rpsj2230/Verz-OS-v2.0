"""The install check for the Connectors area's "demonstrated on an install by a person" leaf.

M11.8.13 asks of the Connectors area of `docs/requirements/register.json` what four sibling leaves
ask of theirs: every requirement "is demonstrated on an install by a person, and each check is
recorded against the requirement it proves". The record is `ops.requirement_check`, which the
Requirement checks screen appends to, and this module reads it.

**A person's demonstration cannot be made by a check, and the check does not pretend to.** What a
check can read is the install's own record of what people saw: the newest check recorded against
each of the area's requirements. It passes only when every requirement of the area has a newest
check that is a pass, so the leaf closes when the owner's demonstrations are complete and not
before. Rejected: a check that stands up a source and replays each requirement itself, which is
what the connectors' own checks already do and which would close a leaf whose whole point is that
a person watched it work. Rejected too: counting a requirement as demonstrated because an
acceptance check names its proof leaf; that is the evidence column the screen already shows, and a
different claim from "a person saw it".

**Three outcomes, and the middle one is the honest default on a new install.** A requirement whose
newest check is a failure fails this check, because somebody saw it not work and has not since seen
it work. A requirement nobody has checked yet makes the check not run, in a sentence saying so,
because nothing has failed and nothing has been shown. A register this release does not carry also
makes it not run. Only a complete set of passes passes. The counts are the screen's and are not
repeated in a result (`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`).

**It reads the install's record and writes nothing.** The read goes through the screen's own store
over the check's session, so what is read is what the screen would show an administrator.

**Written beside its siblings and not on them.** The four other areas' checks are one module on a
branch that had not landed when this was written, and this one asks the same three questions of
one area. It restates the read in a few lines rather than waiting on a module that may land in a
different order; whichever lands second can fold the two onto one reader.

Task ids: M11.8.13
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.tables.requirement_check import CheckOutcome

#: Where this module's checks stand on the Install page, inside the range assigned to it. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1215

#: The area of the register, by the name the register and the Requirement checks screen give it.
AREA: Final = "Connectors"

# ------------------------------------------------------------------ written-down reasons
#: Said when the release carries no register, or none of this area's requirements. Held here and
#: not imported, because a reason is held to a literal in the file that raises it
#: (`tests/unit/test_acceptance.py`).
THIS_RELEASE_CARRIES_NO_REGISTER: Final = (
    "this release carries no requirements register, or none of this area's requirements, so "
    "there is no requirement to look for a recorded check against"
)

#: Said when a requirement has no recorded check.
SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK: Final = (
    "no person has yet recorded a passing check on the Requirement checks screen against every "
    "requirement of this area, which is what the leaf asks for and which only a person can do"
)


@dataclass(frozen=True)
class Standing:
    """Where the area's requirements stand in the install's record, with no ids and no counts."""

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


@check(
    leaves=("M11.8.13",),
    sentence=(
        "Every connectors requirement in the register has, on this install's Requirement checks, a "
        "newest check recorded by a person that passed: none is unchecked and none is failing."
    ),
)
async def every_connectors_requirement_is_shown_working_by_a_person(h: Harness) -> None:
    standing = await standing_of(h, AREA)
    if not standing.registered:
        raise CheckNotRunError(THIS_RELEASE_CARRIES_NO_REGISTER)
    if standing.failed:
        raise CheckFailedError(
            "a connectors requirement's newest recorded check is a failure and no person has "
            "passed it since"
        )
    if standing.unchecked:
        raise CheckNotRunError(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
