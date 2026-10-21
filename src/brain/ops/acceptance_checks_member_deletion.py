"""Install acceptance check for a person asking for their data to be deleted (M40.4.2.3).

The routes My workspace and the Retention screen call (`brain.member_deletion_routes`), as reserved
people signed in through the console, over the install's own database. **What the check is for is
the one thing an ask must not be: a deletion.** The erasure queue is carried out by the worker with
nobody asked again, so the check reads that queue after an ask and refuses a run in which anything
was waiting in it for the asker. It then files the erasure as the administrator and shows that this,
and only this, closes the ask.

It also asks the database what the routes cannot show: that one person's session cannot record an
ask for somebody else, cannot delete a row, and cannot change a column the retention owner does not
set. Each is asked beside the act that works, because a guard tested only by its refusals is
satisfied by a table that refuses everything.

Task ids: M40.4.2.3
"""

from __future__ import annotations

from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import refused, screen_grants
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2790

A, B = RESERVED_DEPARTMENTS

#: The authority that files an erasure, restated so a change to the route fails this check.
FILES_ERASURES: Final = "admin:erasure"

#: The matter the check files under. A reference, never a description.
MATTER: Final = "ACCEPTANCE-ASK-1"


async def _database_refuses(h: Harness, as_person: str, statement: Any) -> bool:
    """Whether the database refuses a statement run as this person, in a savepoint of its own."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from brain.knowledge.search import PRINCIPAL_SETTING

    setting = text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=as_person
    )
    async with h.sessions() as session:
        try:
            await session.execute(setting)
            await session.execute(statement)
            await session.flush()
        except DBAPIError:
            await session.rollback()
            return True
        await session.rollback()
    return False


@check(
    leaves=("M40.4.2.3",),
    sentence=(
        "A member asks for their data to be deleted and is shown what a deletion reaches, what "
        "only time removes and what is kept; the ask waits for an administrator holding the "
        "erasure authority and files nothing in the erasure queue; a second ask is the first; the "
        "administrator's filing closes it; and with the switch off no new ask is taken."
    ),
)
async def a_member_asks_to_be_deleted_and_nothing_is_deleted_by_asking(h: Harness) -> None:
    from sqlalchemy import delete, insert, update

    from brain.erasure_routes import ErasureBody, erasure_queue, file_erasure
    from brain.member_deletion_routes import (
        YOUR_ASK_IS_WAITING,
        ask_for_my_data_to_be_deleted,
        my_deletion_request,
        waiting_asks,
    )
    from brain.tables.member_deletion import DeletionRequestRow

    await h.found_departments()
    admin, reader = h.principal(A, "erasure"), h.principal(A, "retention")
    ada, bea = h.principal(A, "ada"), h.principal(A, "bea")
    await h.person(
        admin,
        department=A,
        grants=((FILES_ERASURES, Scope.unrestricted()), *screen_grants("retention")),
    )
    await h.person(reader, department=A, grants=screen_grants("retention"))
    await h.person(ada, department=A)
    await h.person(bea, department=A)
    c = await console(h)
    request = c.request

    async def asking_as(who: str, *, strong: bool = False) -> Any:
        return await c.asked(who, strong=strong)

    async def mine(who: str) -> Any:
        with c.as_route():
            return await my_deletion_request(request(), await asking_as(who))

    async def asking(who: str) -> Any:
        with c.as_route():
            return await ask_for_my_data_to_be_deleted(request("POST"), await asking_as(who))

    # Off, which is how a new install ships: nothing offered and nothing taken.
    c.app.state.member_deletion_requests_on = False
    if (await mine(ada)).may_ask:
        raise CheckFailedError("the ask was offered with its switch off")
    if not await refused(asking(ada)):
        raise CheckFailedError("an ask was taken with its switch off")
    if (await mine(ada)).state != "none":
        raise CheckFailedError("a refused ask was recorded")

    # On: the lists first, then the ask, which is recorded and nothing more.
    c.app.state.member_deletion_requests_on = True
    before = await mine(ada)
    if not before.may_ask or not before.route.reaches or not before.route.rotates_out:
        raise CheckFailedError("a person was not shown what a deletion reaches and what it leaves")
    parts = [
        one.store
        for name in ("reaches", "rotates_out", "retained")
        for one in getattr(before.route, name)
    ]
    if sorted(parts) != sorted(one.store for one in before.route.order):
        raise CheckFailedError("the lists of what a deletion does do not add up to every store")
    first = await asking(ada)
    if first.state != "waiting" or first.told != YOUR_ASK_IS_WAITING or first.may_ask:
        raise CheckFailedError("an ask was not taken as waiting")
    again = await asking(ada)
    if again.asked_at != first.asked_at:
        raise CheckFailedError("a second ask was not the first")
    if (await mine(bea)).state != "none":
        raise CheckFailedError("one person's ask was shown as another's")

    # Nothing is deleted by asking: the erasure queue holds nothing for the asker.
    queue = await erasure_queue(request(), await asking_as(admin, strong=True))
    if [one for one in queue.requests if one.subject_id == ada]:
        raise CheckFailedError("an ask filed an erasure in the queue the worker carries out")

    # The retention owner sees who waits; nobody else does.
    seen = await waiting_asks(request(), await asking_as(admin, strong=True))
    if [one.subject_id for one in seen.requests] != [ada]:
        raise CheckFailedError("the retention owner was not shown exactly who had asked")
    for outsider in (ada, bea, reader):
        if not await refused(waiting_asks(request(), await asking_as(outsider, strong=True))):
            raise CheckFailedError("the waiting asks were shown to somebody without the authority")

    # The database: an ask is the asker's own and is never deleted or rewritten by them.
    if not await _database_refuses(h, ada, insert(DeletionRequestRow).values(subject_id=bea)):
        raise CheckFailedError("a person's session recorded an ask for somebody else")
    if not await _database_refuses(h, ada, delete(DeletionRequestRow)):
        raise CheckFailedError("the application may delete an ask")
    if not await _database_refuses(h, ada, update(DeletionRequestRow).values(subject_id=bea)):
        raise CheckFailedError("an ask could be given to somebody else")

    # Filing the erasure is what closes the ask, and only the filing.
    body = ErasureBody(subject_id=ada, reason_reference=MATTER)
    with c.as_route():
        filed = await file_erasure(request("POST"), body, await asking_as(admin, strong=True))
    if (await mine(ada)).state != "filed":
        raise CheckFailedError("filing the erasure did not close the person's ask")
    left = await waiting_asks(request(), await asking_as(admin, strong=True))
    if left.requests:
        raise CheckFailedError("a closed ask was still listed as waiting")
    queue = await erasure_queue(request(), await asking_as(admin, strong=True))
    if [one.request_id for one in queue.requests if one.subject_id == ada] != [filed.request_id]:
        raise CheckFailedError("the erasure the administrator filed was not the one queued")
