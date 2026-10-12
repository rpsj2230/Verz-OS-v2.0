"""Install acceptance check for the handover the Settings screen describes before anyone runs it.

The handover of an install (export everything, remove every part, certify) is carried out by a
command on the server and never by a press in the console, because a console that could remove the
install that serves it would be removing its own floor. What the console owes is the **description
of that handover, read from the same steps the command takes**, so a person deciding whether to
leave is told what goes, in what order, and by whom, and a person without the authority is told
nothing of it. The check reads the Settings route as the administrator and holds the answer against
the stores the product removes in order and the parts an install leaves outside its database.

**Nothing is exported or removed here.** The route only describes; the check writes nothing.

Task ids: M27.13.7
"""

from __future__ import annotations

from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, refused
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1320

A, _ = RESERVED_DEPARTMENTS

#: The authority a Settings screen reader holds. Restated rather than imported, so a change to the
#: route's authority fails the check instead of moving with it.
CHANGES_SETTINGS: Final = "admin:install_setting"


@check(
    leaves=("M27.13.7",),
    sentence=(
        "An administrator is shown on Settings how this install is handed over: a step for every "
        "store removed in its order and every part left outside the database, who carries each "
        "out, the days a backup outlives removal and the commands; a person without the "
        "authority is refused the screen."
    ),
)
async def settings_describes_the_handover_before_anyone_runs_it(h: Harness) -> None:
    from brain.ops.handover import Residue, teardown_order
    from brain.ops.retention import BACKUP_RETENTION_DAYS
    from brain.settings_routes import settings

    await h.found_departments()
    admin, other = h.principal(A, "leaving"), h.principal(A, "staying")
    await h.person(admin, department=A, grants=((CHANGES_SETTINGS, Scope.unrestricted()),))
    await h.person(other, department=A)
    console = console_for(h)
    if not await refused(settings(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person without the authority was shown how the install is left")

    page = await settings(console.request(), await asking_as(h, admin, strong=True))
    leaving = page.leaving
    stores = [one.what for one in leaving.steps if one.kind == "store"]
    if stores != [one.value for one in teardown_order()]:
        raise CheckFailedError("the handover did not list every store, in the order they go")
    parts = {one.what for one in leaving.steps if one.kind == "part"}
    if parts != {one.value for one in Residue}:
        raise CheckFailedError("the handover did not name every part left outside the database")
    if any(one.by not in {"command", "operator"} or not one.how for one in leaving.steps):
        raise CheckFailedError("a handover step did not say who carries it out and how")
    if any(one.kind == "store" and not one.holds for one in leaving.steps):
        raise CheckFailedError("a store the handover removes was not said to hold anything")
    if leaving.backup_retention_days != BACKUP_RETENTION_DAYS or leaving.backup_retention_days < 1:
        raise CheckFailedError("the handover did not say how long a backup outlives removal")
    if not leaving.commands or not leaving.procedure or not leaving.told:
        raise CheckFailedError("the handover named no commands and no written procedure")
