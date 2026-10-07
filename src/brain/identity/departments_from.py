"""Where each person's department comes from: the staff list, or the console.

The owner decided on 2026-09-29 (needs-rupash 115, item 2) that an install chooses: **A, the staff
source**, where the department the list names is the person's department and the nightly sync
keeps it so, founding offered and people placed, moved, given their department's Starter pack and
their department's lead's audit reach; or **B, the console**, where departments are managed on
People, several people moved at once, and the sync places and moves nobody. A company whose
directory's departments are not the ones it works in, or whose directory has none, is the case B is
for.

**Under B the list still says who works here.** The sync still adds and marks leavers, makes
accounts and keeps out whom the staff list says (`brain.identity.standing`), because none of that is
where somebody sits. What stops is everything that reads the list's department: a new person's
department, the organisation plan (teams and leads), the heads' audit reach and the offer to found
the departments the list names. A Starter pack still follows item 105, "the Starter pack for their
own department", and under B their own department is the one People set, so the pack follows
that. See `UNDER_THE_CONSOLE_THE_SYNC_MOVES_NOBODY`.

**An unrecognised value reads as A**, which is what every install did before this setting existed.
The Settings screen refuses a word that is neither before it is saved, so only a hand edit of the
environment file can reach here with one, and the product behaving as it always has is the answer
that surprises nobody.

Task ids: M1.6.19, M1.6.20
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import replace
from typing import Final

from brain.identity.staff_source import Roster
from brain.install import InstallError, value_of

#: The installation setting naming where departments come from.
DEPARTMENTS_FROM_SETTING: Final = "INSTALL_DEPARTMENTS_FROM"

UNDER_THE_CONSOLE_THE_SYNC_MOVES_NOBODY: Final = (
    "When departments are managed on People, the staff sync gives nobody a department, moves "
    "nobody, places nobody in a team or as a lead, rewrites no head's audit reach and offers no "
    "department to found. It still adds people, marks leavers, makes accounts and keeps out "
    "whom the list says, and a Starter pack follows the department People set."
)

#: What a run under the console says on its row.
THE_CONSOLE_PLACES_PEOPLE: Final = (
    "Departments are managed on People on this install, so this run placed and moved nobody."
)

#: What a move is refused with when departments come from the staff list.
DEPARTMENTS_COME_FROM_THE_STAFF_LIST: Final = (
    "departments come from the staff list on this install, so a person's department is changed "
    "there; Settings, under Staff, says where departments come from"
)


class DepartmentsFrom(enum.StrEnum):
    """Where a person's department comes from. The setting's two words."""

    STAFF_SOURCE = "staff_source"
    CONSOLE = "console"


def departments_from(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> DepartmentsFrom:
    """This install's answer; the staff source for a value that is neither word. See the note."""
    try:
        word = value_of(DEPARTMENTS_FROM_SETTING, env, saved).strip().casefold()
    except InstallError:
        return DepartmentsFrom.STAFF_SOURCE
    known = {one.value: one for one in DepartmentsFrom}
    return known.get(word, DepartmentsFrom.STAFF_SOURCE)


def the_list_places_people(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> bool:
    """Whether a person the sync makes is placed in the department the list names.

    True when departments come from the staff source, and False when People manages them, where
    the sync places and moves nobody. The one question the people step and the accounts step both
    ask, so neither can answer it differently, and the one the install check asks of the product
    rather than of a copy of it (`brain.ops.acceptance_checks_people`).
    """
    return departments_from(env, saved) is DepartmentsFrom.STAFF_SOURCE


def as_the_console_places_them(roster: Roster, placed: Mapping[str, str | None]) -> Roster:
    """The roster with each person's department the one People set, and no team or lead.

    `placed` is a casefolded work address to the department slug their Brain person sits in; a
    person with no Brain person, or one People put nowhere, is in no department here. What the
    Starter pack step reads, so the pack follows the console's department rather than the list's.
    """
    return replace(
        roster,
        people=tuple(
            replace(
                one,
                department=placed.get(one.work_address.strip().casefold()) or "",
                teams=(),
                leads=False,
            )
            for one in roster.people
        ),
    )
