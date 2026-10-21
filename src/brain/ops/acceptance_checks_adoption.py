"""Install acceptance check for what a department is told of its own coverage (M34.1.x).

A source is connected for one reserved department, read to the end, and three of its records are in
the index for that department. A department lead then reads the Adoption page's coverage statement,
the Ask page's questions built from that data, and the Connectors screen's suggestion, as the routes
the console calls do, signed in through the install's own gate. **What the check is for is the
things coverage must not do**: tell a reader about a department their usage grant does not admit,
name a source they may not be told of, or offer a question about a kind of record they cannot read.
Each is asked beside the act that works.

**The index rows are written by the check and rolled back with it.** Nothing here reaches a
source or a bucket; what is proved is the statement over the install's own tables, with the SQL the
count really runs.

Task ids: M34.1.1.1, M34.1.1.2, M34.1.1.3, M34.1.2.1, M34.1.2.2, M34.1.2.3
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_people_signed_in import administrator, console, everywhere, within
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2700

A, B = RESERVED_DEPARTMENTS

#: The source the check connects. A source that asks for a department and whose records can be read
#: live, so it is both attributable to a department and checkable in its own system.
SOURCE: Final = "freshdesk"

#: Why the check cannot run on an install that already reads this source.
CONNECTED_ALREADY: Final = (
    "The source this check connects is connected on this install already, and a source is "
    "connected once, so the check would have to disconnect it first."
)


async def _view(c: Any, who: str) -> Any:
    from brain.adoption_coverage_routes import coverage

    with c.as_route():
        return await coverage(c.request(), await c.asked(who, strong=False))


def _lines(view: Any, department: str) -> list[Any]:
    return [one for one in view.lines if one.department == department]


async def _no_key() -> None:
    """The key a source is connected with: none, because this check reads nothing from a source."""
    return None


@check(
    leaves=("M34.1.1.1", "M34.1.1.2", "M34.1.1.3", "M34.1.2.1", "M34.1.2.2", "M34.1.2.3"),
    sentence=(
        "A department with a source read to the end is shown its record count and last read, and "
        "one with nothing connected is shown as not connected and on the shopping list. A source "
        "the reader may not name is merged, and no other department reaches them. Connectors "
        "suggests a source never already connected; Ask offers questions on records they may read."
    ),
)
async def a_department_is_told_what_is_connected_for_it_alone(h: Harness) -> None:
    from sqlalchemy import insert

    from brain.adoption import Coverage, Need
    from brain.adoption_coverage_routes import SWITCHED_OFF, connector_start
    from brain.connectors.contract import HealthState
    from brain.connectors.manifest import manifest_digest
    from brain.console.adoption_coverage import UNNAMED_SOURCE
    from brain.console.connector_trust import THE_SCREEN
    from brain.console.screens import screen
    from brain.core.errors import Absent
    from brain.knowledge.rows import entity_capability
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync import Attempt, SyncOutcome
    from brain.ops.connector_sync_store import attempt_row, read_live
    from brain.ops.coverage_store import record_counts
    from brain.tables.projection import ProjectedRecordRow
    from brain.welcome_routes import welcome_from_data

    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(CONNECTED_ALREADY)

    await h.found_departments()
    c = await console(h)
    lead, unnamed, plain, admin, member, bystander = (
        h.principal(A, role)
        for role in ("lead", "unnamed", "plain", "admin", "member", "bystander")
    )
    ticket = entity_capability("ticket").value
    connectors = screen(THE_SCREEN).read.requires.value
    await h.person(lead, department=A, grants=(*within(A, "read:usage"), *everywhere(connectors)))
    await h.person(unnamed, department=A, grants=within(A, "read:usage"))
    await h.person(plain, department=A)
    await h.person(admin, department=A, grants=everywhere(*administrator()))
    await h.person(member, department=A, grants=within(A, ticket))
    await h.person(bystander, department=A, grants=within(B, ticket))

    settings = {"domain": "acceptance.freshdesk.com", "department": A}
    await StoredConnections(h.sessions).connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(manifest_for(SOURCE, settings)),
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_no_key,
    )
    async with h.sessions() as session, session.begin():
        [connected] = [
            one for one in await read_live(session) if one.connection.connector == SOURCE
        ]
    read_at = h.now - timedelta(minutes=5)
    await h.execute(
        attempt_row(
            connected.id,
            Attempt(
                connector=SOURCE,
                started_at=read_at,
                finished_at=read_at,
                outcome=SyncOutcome.SYNCED,
                health=HealthState.OK,
                records=3,
                consecutive_failures=0,
                next_attempt_at=h.now + timedelta(hours=1),
                detail="read",
            ),
        )
    )
    for index, place in enumerate((A, A, A, B, B)):
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=SOURCE,
                entity="ticket",
                source_id=f"acceptance-{h.run}-{uuid.uuid4().hex[:8]}-{index}",
                fields={"department": place},
                last_seen_at=h.now,
            ),
        )

    # The count is bounded to the departments it is asked for: the two rows of the other one are
    # in the index and never in the answer.
    async with h.sessions() as session:
        held = await record_counts(session, [A])
    if dict(held) != {(SOURCE, A, "ticket"): 3}:
        raise CheckFailedError("the count was not bounded to the department it was asked for")

    # Off by default: nothing is shown until an install turns the statement and the questions on.
    c.app.state.adoption_coverage_on = False
    c.app.state.starter_questions_from_data_on = False
    off = await _view(c, lead)
    if off.switched_on or off.lines or off.note != SWITCHED_OFF:
        raise CheckFailedError("the coverage statement was shown while its switch was off")
    with c.as_route():
        asked_off = await welcome_from_data(c.request(), await c.asked(member, strong=False))
    if asked_off.questions:
        raise CheckFailedError("questions built from data were offered while their switch was off")

    c.app.state.adoption_coverage_on = True
    c.app.state.starter_questions_from_data_on = True

    # A department lead reads their own department: connected, three records, read.
    told = await _view(c, lead)
    [mine] = [one for one in _lines(told, A) if one.source == SOURCE]
    if (mine.state, mine.records) != (Coverage.CONNECTED.value, 3) or mine.last_sync is None:
        raise CheckFailedError("a connected source was not shown with its records and last read")
    if _lines(told, B):
        raise CheckFailedError("a department the lead may not read usage for was shown to them")

    # Nothing connected is a statement of its own, and is on the shopping list.
    wide = await _view(c, admin)
    [theirs] = [one for one in _lines(wide, B) if one.source is not None]
    if (theirs.state, theirs.records, theirs.last_sync) != (
        Coverage.NOT_CONNECTED.value,
        None,
        None,
    ):
        raise CheckFailedError("a department with nothing connected was not shown as such")
    if theirs.source == SOURCE:
        raise CheckFailedError("a source connected already was suggested for another department")
    if not any(
        one.department == B and one.need == Need.AUTHORISE_THE_SOURCE.value for one in wide.shopping
    ):
        raise CheckFailedError("a department with nothing connected was not on the shopping list")

    # A source the reader may not be told of is merged, and the line is still true.
    [anonymous] = _lines(await _view(c, unnamed), A)
    if (anonymous.source, anonymous.state, anonymous.records) != (
        UNNAMED_SOURCE,
        Coverage.CONNECTED.value,
        3,
    ):
        raise CheckFailedError("a source the reader may not name was dropped or named")

    # No usage grant is an empty statement and not a refusal.
    nothing = await _view(c, plain)
    if nothing.lines or nothing.shopping:
        raise CheckFailedError("a reader with no usage grant was shown a coverage statement")

    # The Connectors screen suggests a source to connect first, and never the connected one.
    with c.as_route():
        start = await connector_start(c.request(), await c.asked(admin, strong=False))
    if start.source is None or start.source == SOURCE:
        raise CheckFailedError("the Connectors screen suggested nothing or a connected source")
    try:
        with c.as_route():
            await connector_start(c.request(), await c.asked(plain, strong=False))
    except Absent:
        pass
    else:
        raise CheckFailedError("a reader without the Connectors grant was given a suggestion")

    # Ask: a question about a kind of record the person may read, with where to check it.
    with c.as_route():
        offered = await welcome_from_data(c.request(), await c.asked(member, strong=False))
    if len(offered.questions) != 1 or "ticket" not in offered.questions[0].question:
        raise CheckFailedError("a person was not offered a question about the records they read")
    if not offered.questions[0].check_in:
        raise CheckFailedError("a question did not say where to check its answer")
    with c.as_route():
        refused = await welcome_from_data(c.request(), await c.asked(bystander, strong=False))
    if refused.questions:
        raise CheckFailedError("a person was offered a question about records they may not read")
