"""Adoption, as one reader may be shown it: the usage grant decides the departments.

`brain.adoption.adoption_by_department` takes the reach as a set of department names and
computes none of it, and says which grant that set should come from: the one
`brain.console.spend_view.may_read_spend` answers. This is where that sentence became a call.

**One function for "may this reader know how much this department did", shared with the usage
report.** Adoption and spend are both figures about a department's activity, and a reader who
could see one and not the other would learn from the difference. So there is no adoption
capability and no second scope check: the departments are narrowed through `may_read_spend`,
which is `EntitlementSet.scope_for` then `Scope.matches`, and a change to who may read usage is
a change to who may read adoption on the same afternoon. See
`ADOPTION_IS_READ_UNDER_THE_GRANT_USAGE_IS_READ_UNDER`.

**The departments come from the directory and never from the records.** `adoption_by_department`
gives every reachable department a line, zero included, so that whether a line appears says
nothing about what happened. That only holds if the list of departments does not itself come
from the rows: a list built from who asked would give a line to a department with nothing but
a schedule in it, and none to a department whose people asked nothing, which is exactly the
disclosure the zero lines exist to prevent. See
`THE_DEPARTMENTS_ARE_THE_DIRECTORYS_AND_NOT_WHATEVER_WAS_RECORDED`.

Task ids: M37.3.2.4
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final

from brain.adoption import Asked, DepartmentAdoption, adoption_by_department
from brain.console.spend_view import may_read_spend
from brain.core.entitlement import EntitlementSet

#: Why there is no adoption capability.
ADOPTION_IS_READ_UNDER_THE_GRANT_USAGE_IS_READ_UNDER: Final = (
    "How many questions a department asked and how much its questions cost are two figures "
    "about the same activity. Two grants would let a reader hold one and not the other and "
    "read across the gap, and two scope checks would drift. So the departments a reader is "
    "shown adoption for are exactly the departments may_read_spend admits."
)

#: Why the department list is a parameter the caller fills from the directory.
THE_DEPARTMENTS_ARE_THE_DIRECTORYS_AND_NOT_WHATEVER_WAS_RECORDED: Final = (
    "Every reachable department gets a line, zero included, so that a line's presence is a "
    "fact about the reader's reach. A department list derived from the records would give a "
    "line to a department whose only traffic was a machine's and none to one where nobody "
    "asked anything, and the reader would learn both."
)


def adoption_for_reader(
    asked: Sequence[Asked],
    departments: Iterable[str],
    entitlement: EntitlementSet,
    *,
    start: datetime,
    end: datetime,
    now: datetime,
) -> tuple[DepartmentAdoption, ...]:
    """The adoption lines this reader's usage grant admits, over `[start, end)`.

    `departments` is every department the directory holds. See
    `THE_DEPARTMENTS_ARE_THE_DIRECTORYS_AND_NOT_WHATEVER_WAS_RECORDED`. A reader holding no
    usage grant is shown no lines, as an empty answer rather than a refusal, for the reason
    `may_read_spend` gives.
    """
    reachable = frozenset(one for one in departments if may_read_spend(one, entitlement, now=now))
    return adoption_by_department(asked, reachable, start=start, end=end)
