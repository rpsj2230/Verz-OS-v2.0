"""Service levels, as one reader may be shown them: the whole install's reading, or nothing.

`brain.ops.service_levels` folds the metadata ledger into one reading per lane against
`brain.ops.reliability.LANE_OBJECTIVES`, and it deliberately decides nothing about who may read
the result, because until this module there was no screen to ask. The screen is
`brain.console.screens.screen("service_levels")` and this is where its reader decision lives.

**A reading is read under the grant usage is read under, and no capability is added for it.**
What a reading holds is how many requests each lane carried in a window and how they went.
That is the same activity `brain.console.adoption_view` counts as questions and
`brain.console.usage_view` counts as tokens, and `adoption_view` has already argued what a
second grant over one activity costs: a reader holding one and not the other reads across the
gap, and two scope checks drift. So the screen requires `read:usage`, `SERVICE_LEVEL_AUTHORITY`
is read off the registry rather than written here, and a test holds it to
`brain.console.spend_view.USAGE_AUTHORITY`. The rejected capability was `read:incident`, which
governs what is degraded now: it is the nearer name, and it would let a reader who may not see
any department's usage read the install's request volume off this screen. See
`SERVICE_LEVELS_ARE_READ_UNDER_THE_GRANT_USAGE_IS_READ_UNDER`.

**A reading has no department's version, so a department-scoped grant is shown nothing rather
than the install.** `brain.ops.telemetry_store.observed_between` selects the lane, the status,
the duration and the instant, and `obs.request_telemetry` carries no department at all, so a
reading is a sum over every department in the company. Narrowing it is not possible and showing
it whole to somebody whose usage grant names their own department is the leak by subtraction:
the install's request count less their own department's question count is every other
department's traffic, in one step, with every figure on both screens correct. So a reading
offers a grant's scope `READING_ROW`, which holds no field, and `brain.core.scope.Clause.matches`
refuses a field a row does not have: an unrestricted grant matches it and a department-scoped
one matches nothing. That is `brain.console.installation._limit_row`'s shape, and it is why the
screen sits beside Rate limits in `brain.console.screens.NOT_AT_DEPARTMENT_SCOPE`. See
`A_READING_IS_THE_WHOLE_INSTALLS_AND_HAS_NO_DEPARTMENTS_VERSION`.

**A refused reader is shown the reading of an install that promises nothing, and no count.**
The refused answer is a `ServiceLevels` over the same window with no lanes, which is exactly
what `against_target` returns for an install declaring no objectives over a quiet window. It
carries no request count, no lane and no sentence, so a refused reading of a busy install and
one of an idle install are equal objects, and nothing a renderer holds could separate DENIED
from ABSENT. The cheaper refusal, `None` or an exception naming the grant, tells the reader a
usage report exists and that they were measured against it. See
`A_REFUSED_READING_IS_THE_READING_OF_AN_INSTALL_THAT_PROMISES_NOTHING`.

**The reading is built before the decision, so a refused read does the same work.** The store
query runs and the window is checked whoever is asking, and the decision is the last step. A
refusal made first would return faster, and would stop refusing a malformed window or a database
that cannot answer, so a refused reader would be the one reader whose broken request succeeds.
See `A_REFUSED_READ_DOES_THE_SAME_WORK_AS_A_PERMITTED_ONE`.

What is not built. No console tool named `console.service_levels` is registered, so the screen
is declared and cannot be opened; `brain.console.screens.unregistered_tools` says so in figures
and `docs/console/runbooks/service_levels.md` says so in words. Nothing renders a reading. What
M30.5.3 is claimed on here is what earlier console leaves were claimed on: the read model, the
decision about who may be shown it, and a registered screen, each with tests.

Scope: domain logic plus one store read. Nothing here writes, renders or reads a clock; `now`
is a parameter, as in every sibling in this package.

Task ids: M30.5.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.reliability import LaneObjective
from brain.ops.service_levels import ServiceLevels
from brain.ops.telemetry_store import service_levels_between

# ------------------------------------------------------------------ written-down reasons
#: Why there is no service level capability.
SERVICE_LEVELS_ARE_READ_UNDER_THE_GRANT_USAGE_IS_READ_UNDER: Final = (
    "A reading is how many requests each lane carried and how they went, which is the same "
    "activity adoption counts as questions and usage counts as tokens. A grant of its own would "
    "let a reader hold the install's request volume without holding any department's usage and "
    "read across the gap, and a second scope check over one activity drifts. So the screen "
    "requires the usage screen's capability and nothing new."
)

#: Why a department-scoped grant is shown nothing rather than a narrowed or a whole reading.
A_READING_IS_THE_WHOLE_INSTALLS_AND_HAS_NO_DEPARTMENTS_VERSION: Final = (
    "The telemetry row carries no department, so a reading is a sum over every department and "
    "cannot be narrowed. Shown whole to a reader whose usage grant names one department, the "
    "install's request count less that department's own question count is every other "
    "department's traffic. So a reading offers a grant's scope no field at all: an unrestricted "
    "grant matches it and a department-scoped grant matches nothing."
)

#: Why the refused answer is an empty reading and not a refusal.
A_REFUSED_READING_IS_THE_READING_OF_AN_INSTALL_THAT_PROMISES_NOTHING: Final = (
    "A refused reader is handed the reading an install declaring no objectives produces over a "
    "quiet window: the same window, no lanes, no count and no sentence. A refused reading of a "
    "busy install and of an idle one are equal, and an exception naming the grant would tell "
    "the reader a usage report exists and that they were measured against it."
)

#: Why the reading is built before the decision.
A_REFUSED_READ_DOES_THE_SAME_WORK_AS_A_PERMITTED_ONE: Final = (
    "The store is read and the window is checked whoever asks, and the decision is the last "
    "step. Deciding first returns sooner for a refused reader and stops refusing a malformed "
    "window or a database that cannot answer, which makes the refused reader the one reader "
    "whose broken request succeeds."
)

#: The screen this module is the reader decision for.
SCREEN_KEY: Final = "service_levels"

#: The capability a reading is read under, read off the registry rather than written here.
SERVICE_LEVEL_AUTHORITY: Final[Capability] = screen(SCREEN_KEY).read.requires

#: The fields a reading offers a grant's scope: none. See
#: `A_READING_IS_THE_WHOLE_INSTALLS_AND_HAS_NO_DEPARTMENTS_VERSION`.
READING_ROW: Final[Mapping[str, str]] = MappingProxyType({})


def may_read_service_levels(entitlement: EntitlementSet, *, now: datetime) -> bool:
    """Whether this reader's usage grant admits the whole install, which is all a reading is.

    `EntitlementSet.scope_for` then `Scope.matches`, the pair `spend_view.may_read_spend` makes,
    against a row with no fields. The console plane is not asked here: that is the screen's
    `permitted`, and this is the row decision behind it, as `may_read_spend` is behind usage.
    """
    scope = entitlement.scope_for(SERVICE_LEVEL_AUTHORITY, now)
    if scope is None:
        return False
    return scope.matches(dict(READING_ROW))


def for_reader(
    levels: ServiceLevels, entitlement: EntitlementSet, *, now: datetime
) -> ServiceLevels:
    """The reading as this reader may be shown it: whole, or over the same window with no lanes.

    See `A_REFUSED_READING_IS_THE_READING_OF_AN_INSTALL_THAT_PROMISES_NOTHING`.
    """
    if may_read_service_levels(entitlement, now=now):
        return levels
    return ServiceLevels(start=levels.start, end=levels.end, lanes=())


async def service_levels_for_reader(
    session: AsyncSession,
    entitlement: EntitlementSet,
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    objectives: Sequence[LaneObjective] | None = None,
) -> ServiceLevels:
    """Each lane's attainment over `[start, end)` against its objective, for this reader.

    Reads through `telemetry_store.service_levels_between` and writes nothing. The reading is
    built first and narrowed last; see `A_REFUSED_READ_DOES_THE_SAME_WORK_AS_A_PERMITTED_ONE`.
    """
    levels = await service_levels_between(session, start=start, end=end, objectives=objectives)
    return for_reader(levels, entitlement, now=now)
