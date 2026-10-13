"""The install acceptance check that an incident is acknowledged once, by who and when, and that the
repeat notice stops (M27.15.45).

**It acknowledges an incident the check made.** A Xero tenant made up for the check is connected
through the Connectors store and tested against a transport answering from memory with a refusal,
which leaves the source failing on the worker's own record; nothing reaches the source. The
incident is then read, and acknowledged, through the routes the Incidents page calls. An install
that has Xero connected already is not run, because the check would be connecting over a real
connection (`brain.ops.acceptance_operations_console_2.A_SOURCE_IS_CONNECTED_HERE_ALREADY`).

**Three readers.** An administrator who holds the Incidents screen across the whole install is
offered the control and may press it. A reader who holds it over one department is shown no control
and is refused the press in the one answer every refusal gives, so the refusal does not say there
is a control. A person with neither is refused the screen.

**What the database must refuse as well.** The row is written in the session's own name and never
rewritten: a row naming somebody else is refused by its policy, and the grants carry neither UPDATE
nor DELETE. A check that only asked the route would pass with the policy deleted.

Task ids: M27.15.45
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, screen_grants
from brain.ops.acceptance_operations_console_2 import (
    CONNECTS_SOURCES,
    Answering,
    connected_here,
)
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1700

A, B = RESERVED_DEPARTMENTS


async def _failing_source(h: Harness, admin: str) -> str:
    """A made-up Xero tenant connected and tested with a transport that refuses, by its name."""
    from brain.connector_routes import ask_probe
    from brain.ops.acceptance_checks_connectors import SOURCE, _clock, _Keys, _Resolver
    from brain.ops.connector_probe_run import probe_on

    await connected_here(h, admin)
    console = console_for(h)
    await ask_probe(console.request("POST"), SOURCE, await asking_as(h, admin, strong=True))
    await probe_on(
        sessions=h.sessions,
        now=datetime.now(UTC),
        keys=_Keys(),
        caller=Answering(status=401),
        resolver=_Resolver(),
        clock=_clock,
    )
    return SOURCE


@check(
    leaves=("M27.15.45",),
    sentence=(
        "An incident is acknowledged by a reader holding the Incidents screen across the whole "
        "install, the row names who and when and a second press keeps the first, the repeat "
        "notice stops while the incident stays listed, a reader of one department is offered no "
        "control, and the database refuses a row in another's name and any rewrite."
    ),
)
async def an_incident_is_acknowledged_once_and_stops_its_repeat_notice(h: Harness) -> None:
    from brain.incident_routes import AcknowledgementAsked, acknowledge_incident, incidents_screen
    from brain.ops.alert_acknowledgement import notice_may_repeat

    await h.found_departments()
    whole, second, narrow, other = (
        h.principal(A, role) for role in ("whole", "second", "narrow", "other")
    )
    in_a = Scope(clauses=(Clause(field="department", op=Op.EQ, value=A),))

    # The screens share a plane, so each reader's grants are a set and not a concatenation.
    def held(*grants: tuple[str, Scope]) -> tuple[tuple[str, Scope], ...]:
        return tuple(dict.fromkeys(grants))

    sources = screen_grants("connectors")
    await h.person(
        whole,
        department=A,
        grants=held(
            *screen_grants("incidents"), *sources, (CONNECTS_SOURCES, Scope.unrestricted())
        ),
    )
    await h.person(second, department=A, grants=held(*screen_grants("incidents"), *sources))
    # The screen's read over one department, with the plane the sources screen holds whole.
    narrow_read = screen_grants("incidents", in_a)[0]
    await h.person(narrow, department=A, grants=held(narrow_read, *sources))
    await h.person(other, department=A)
    source = await _failing_source(h, whole)
    console = console_for(h)

    if not await refused(incidents_screen(console.request(), await asking_as(h, other))):
        raise CheckFailedError("a person who may not open Incidents was shown the screen")
    page = await incidents_screen(console.request(), await asking_as(h, whole))
    ours = [one for one in page.items if one.subject == source]
    if len(ours) != 1 or not page.may_acknowledge or ours[0].acknowledged_by:
        raise CheckFailedError("a failing source was not listed as an incident nobody had seen")
    asked = AcknowledgementAsked(subject=source, since=ours[0].since)

    narrow_page = await incidents_screen(console.request(), await asking_as(h, narrow))
    if narrow_page.may_acknowledge:
        raise CheckFailedError("a reader of one department was offered the acknowledge control")
    if not await refused(
        acknowledge_incident(console.request("POST"), await asking_as(h, narrow), asked)
    ):
        raise CheckFailedError("a reader of one department acknowledged an incident")

    done = await acknowledge_incident(console.request("POST"), await asking_as(h, whole), asked)
    if not done.acknowledged_by or done.acknowledged_at is None:
        raise CheckFailedError("an acknowledgement did not say who and when")
    again = await acknowledge_incident(console.request("POST"), await asking_as(h, second), asked)
    if (again.acknowledged_by, again.acknowledged_at) != (
        done.acknowledged_by,
        done.acknowledged_at,
    ):
        raise CheckFailedError("a second press rewrote who acknowledged the incident")

    after = await incidents_screen(console.request(), await asking_as(h, whole))
    kept = [one for one in after.items if one.subject == source]
    if len(kept) != 1 or kept[0].state != ours[0].state or not kept[0].acknowledged_by:
        raise CheckFailedError("an acknowledged incident was hidden or lost its state")
    now = datetime.now(UTC)
    every = timedelta(hours=1)
    if notice_may_repeat(acknowledged=True, last_said=now - every * 5, every=every, now=now):
        raise CheckFailedError("an acknowledged incident was said again")
    if not notice_may_repeat(acknowledged=False, last_said=now - every * 5, every=every, now=now):
        raise CheckFailedError("an unacknowledged incident was never said again")

    await _refused_by_the_database(h, whole, other, source, ours[0].since)


async def _refused_by_the_database(
    h: Harness, writer: str, somebody: str, subject: str, since: datetime
) -> None:
    """The policy and the grants, asked of the table itself."""

    async def attempt(statement: str, principal: str, **values: object) -> bool:
        """Whether the database accepted the statement, in a savepoint that is then undone."""
        try:
            async with h.sessions() as session:
                await session.execute(
                    text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
                )
                nested = await session.begin_nested()
                try:
                    await session.execute(text(statement), values)
                finally:
                    await nested.rollback()
        except DBAPIError:
            return False
        return True

    insert = (
        "INSERT INTO ops.alert_acknowledgement (kind, subject, since, acknowledged_by)"
        " VALUES ('incident', :subject, :since, :by)"
    )
    later = since + timedelta(seconds=1)
    if await attempt(insert, writer, subject=subject, since=later, by=somebody):
        raise CheckFailedError("the database accepted an acknowledgement in somebody else's name")
    if not await attempt(insert, writer, subject=subject, since=later, by=writer):
        raise CheckFailedError("the database refused an acknowledgement in the session's own name")
    if await attempt(
        "UPDATE ops.alert_acknowledgement SET acknowledged_by = :by WHERE subject = :subject",
        writer,
        subject=subject,
        by=somebody,
    ):
        raise CheckFailedError("the database allowed an acknowledgement to be rewritten")
    if await attempt(
        "DELETE FROM ops.alert_acknowledgement WHERE subject = :subject", writer, subject=subject
    ):
        raise CheckFailedError("the database allowed an acknowledgement to be deleted")
