"""Install acceptance checks for the Incidents screen: what is degraded now and what it blocks.

The check connects a Xero tenant made up for it through the Connectors screen's store, has the
worker's own read of it refused by a transport answering from memory, and reads the Incidents
route as a reader of both screens. **Nothing leaves the process and nothing is kept**: the
connection, its attempt and its health are rows of the check's own transaction, and an install that
has Xero connected is left alone (`A_SOURCE_IS_CONNECTED_HERE_ALREADY`).

Task ids: M27.2.7
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, screen_grants
from brain.ops.acceptance_operations_console_2 import Answering, connected_here
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 950

A, B = RESERVED_DEPARTMENTS

#: The authority a source's administrator holds. Restated rather than imported, so a change to the
#: route's authority fails the check instead of moving with it.
CONNECTS_SOURCES: Final = "admin:connector"


# ------------------------------------------------------------- 1. incidents (M27.2.7)
@check(
    leaves=("M27.2.7",),
    sentence=(
        "A Xero tenant made up for the check whose scheduled read the source refuses is listed on "
        "Incidents as degraded or down, since when, with the tools that stop working because of "
        "it; a source nothing has read is not listed; a person without the screen is refused."
    ),
)
async def a_refused_source_is_an_incident_naming_what_it_blocks(h: Harness) -> None:
    from brain.incident_routes import incidents_screen
    from brain.ops.acceptance_checks_connectors import (
        SOURCE,
        _clock,
        _Keys,
        _no_wait,
        _Resolver,
    )
    from brain.ops.connector_sync import plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import attempt_row
    from brain.ops.connector_sync_store import read_live as live_rows

    await h.found_departments()
    admin, reader, other = (h.principal(A, role) for role in ("connects", "reader", "other"))
    await h.person(admin, department=A, grants=((CONNECTS_SOURCES, Scope.unrestricted()),))
    grants = dict.fromkeys((*screen_grants("incidents"), *screen_grants("connectors")))
    await h.person(reader, department=A, grants=tuple(grants))
    await h.person(other, department=A)
    await connected_here(h, admin)
    console = console_for(h)

    if not await refused(incidents_screen(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person without the screen was shown the incidents")
    quiet = await incidents_screen(console.request(), await asking_as(h, reader))
    if SOURCE in [one.subject for one in quiet.items]:
        raise CheckFailedError("a source nobody had read was listed as an incident")

    async with h.sessions() as session, session.begin():
        found = [one for one in await live_rows(session) if one.connection.connector == SOURCE]
    if len(found) != 1:
        raise CheckFailedError("the source the check connected was not read back as connected")
    plan = plan_for(found[0].connection, last=None, now=datetime.now(UTC))
    refusing = Answering(status=401)
    read = await attempt(
        found[0],
        plan,
        previous=None,
        sessions=h.sessions,
        keys=_Keys(),
        caller=refusing,
        resolver=_Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )
    await h.execute(attempt_row(found[0].id, read))
    if not refusing.asked:
        raise CheckFailedError("the worker's scheduled read never asked the source")

    listed = await incidents_screen(console.request(), await asking_as(h, reader))
    ours = [one for one in listed.items if one.subject == SOURCE]
    if len(ours) != 1 or ours[0].state not in {"degraded", "down"}:
        raise CheckFailedError("a source whose read was refused was not listed as an incident")
    if not ours[0].blocks and not ours[0].blocks_unknown:
        raise CheckFailedError("an incident did not say what it blocks, or that it cannot")
