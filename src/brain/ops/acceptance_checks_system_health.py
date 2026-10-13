"""The install acceptance check that System health shows a guarantee as held only while the control
that keeps it is running (M27.13.2, M27.15.54).

**It writes run records as the worker writes them and asks the screen what they mean.** Two
scheduled controls the scheduler may run are given a run each, as the login the run connected as
and inside the check's rolled-back transaction: one that finished a minute ago and one that last
finished a hundred days ago. A third is given none. The route the page calls is then asked as three
readers. A person with no Incidents screen and one holding it over a single department are refused
in the same words, because the vault, the worker and the guarantees belong to the whole
installation. A reader of the whole installation is shown every control the register names, the
first as held, the second as not held because it is behind, the third as not held because it has
never run, the worker as last seen no earlier than the newest run, and the vault and object store
each named with what was measured.

**What it does not prove.** Readiness parts are the web process's own and the check's application
has no probes, so it asks only that the four headline parts are named, not that they are ready; the
breakers are the Models screen's and a reader without it is told so. The same sentence is said on
the page.

Task ids: M27.13.2, M27.15.54
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import insert

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    refused,
    screen_grants,
)
from brain.ops.acceptance_operations_console_2 import as_login
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1730

A, B = RESERVED_DEPARTMENTS

#: How long ago the stale control last finished, well past any control's cadence and its grace.
LONG_AGO: Final = timedelta(days=100)


def _controls_to_press() -> tuple[str, str, str]:
    """Three scheduled controls that delete nothing and that something calls, by the registry's
    order. A control nothing calls is `unreachable` whatever it last did, which is its own case."""
    from brain.ops.controls import Invocation
    from brain.ops.schedule import DESTRUCTIVE, schedulable

    names = [
        one.name
        for one in schedulable()
        if one.name not in DESTRUCTIVE and one.invoked_by is not Invocation.NOTHING
    ]
    if len(names) < 3:
        raise CheckFailedError("fewer than three controls can be run by the scheduler")
    return names[0], names[1], names[2]


@check(
    leaves=("M27.13.2", "M27.15.54"),
    sentence=(
        "System health is refused to a person with no Incidents screen and to one holding it over "
        "a department, and shown to a reader of the whole installation: every control the "
        "register names, one held that ran a minute ago, one not held that last ran a hundred days "
        "ago, one not held that never ran, the worker last seen, and the vault and object store."
    ),
)
async def system_health_shows_a_guarantee_held_only_while_its_control_runs(h: Harness) -> None:
    from brain.ops.controls import CONTROLS, Invocation
    from brain.system_health_routes import system_health
    from brain.tables.schedule import ControlRunRow

    await h.found_departments()
    whole, narrow, other = (h.principal(A, role) for role in ("whole", "narrow", "other"))
    in_a = Scope(clauses=(Clause(field="department", op=Op.EQ, value=A),))
    await h.person(whole, department=A, grants=screen_grants("incidents"))
    await h.person(narrow, department=A, grants=screen_grants("incidents", in_a))
    await h.person(other, department=A)

    running, stale, never = _controls_to_press()
    now = datetime.now(UTC)
    await as_login(
        h,
        insert(ControlRunRow).values(
            name=running,
            started_at=now - timedelta(minutes=2),
            finished_at=now - timedelta(minutes=1),
            outcome="ok",
        ),
        insert(ControlRunRow).values(
            name=stale,
            started_at=now - LONG_AGO - timedelta(minutes=1),
            finished_at=now - LONG_AGO,
            outcome="ok",
        ),
    )

    console = console_for(h)
    if await refused(system_health(console.request(), await asking_as(h, whole))):
        raise CheckFailedError("a reader of the whole installation was refused System health")
    if not await refused(system_health(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person with no Incidents screen was shown System health")
    if not await refused(system_health(console.request(), await asking_as(h, narrow))):
        raise CheckFailedError("a reader of one department was shown System health")

    page = await system_health(console.request(), await asking_as(h, whole))
    states = {one.control: one for one in page.guarantees}
    if set(states) != {one.name for one in CONTROLS}:
        raise CheckFailedError("System health did not list every control the register names")
    if not states[running].held or states[running].because:
        raise CheckFailedError("a control that ran a minute ago was not shown as held")
    if states[stale].held or states[stale].because != "behind":
        raise CheckFailedError("a control that last ran a hundred days ago was shown as held")
    if states[never].held or states[never].because != "never_run":
        raise CheckFailedError("a control that never ran was not shown as never run")
    uncalled = [one for one in CONTROLS if one.invoked_by is Invocation.NOTHING]
    if any(states[one.name].held or states[one.name].because != "unreachable" for one in uncalled):
        raise CheckFailedError("a control nothing calls was not shown as unreachable")
    if page.worker.last_seen is None or page.worker.last_seen < now - timedelta(minutes=2):
        raise CheckFailedError("the worker was not shown as seen when a run had just finished")
    if not {"database", "cache", "vault", "sign_in"} <= {one.name for one in page.parts}:
        raise CheckFailedError("System health did not name the four headline parts")
    if not page.vault.said or not page.object_store.said:
        raise CheckFailedError("the vault or the object store was drawn with nothing said of it")
    if page.breakers is not None or not page.breakers_said:
        raise CheckFailedError("breakers were shown to a reader who may not read the Models screen")
