"""Install check for the payload store's thirty-day expiry: a step goes at thirty days, no sooner.

`0226` gives the application role DELETE on `obs.trace_step` behind a row-level policy that admits a
step only once it is more than thirty days old, so the retention sweep, which asks the catalogue
whether the role may delete, removes what is past the window instead of queueing it for ever. This
asks the database, as the application role over the install's own table in the check's rolled-back
transaction, the three things the migration says.

**The delete is an unqualified one, and that is the point.** The statement names no age: the policy
decides which rows it may touch. A check that deleted `WHERE recorded_at < ...` would pass a policy
admitting everything, because the statement would have done the bounding. So the statement is the
one a compromised application would write, and what is read afterwards is which rows it left.

**Both rows are the check's own and the figures are read, never assumed.** The install may hold
steps past the window of its own, so the delete's count is held to at least the check's one and
whether the fresh step survived is read with the login role the check's connection steps back to,
inside a savepoint, as `brain.ops.acceptance_operations_console.applied_revisions` does.

Task ids: M25.1.3
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness
from brain.session import SET_APPLICATION_ROLE

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2160

#: How far either side of thirty days the check's two steps sit: a day past it and a day inside it.
A_DAY: Final = timedelta(days=1)

THE_APPLICATION_COULD_READ_A_STEP: Final = (
    "the application role read a stored trace step, which only the trace reader role may"
)
AN_EXPIRED_STEP_WAS_NOT_REMOVED: Final = (
    "the application role could not delete a trace step past thirty days"
)
A_FRESH_STEP_WAS_REMOVED: Final = "the application role deleted a trace step inside thirty days"


@check(
    leaves=("M25.1.3",),
    sentence=(
        "The application role deletes a trace step recorded more than thirty days ago with an "
        "unqualified delete and leaves one recorded a day ago, and still cannot read either."
    ),
)
async def a_trace_step_leaves_at_thirty_days_and_not_before(h: Harness) -> None:
    from brain.ops.retention import PAYLOAD_RETENTION_DAYS
    from brain.ops.tracing import MASKED_PAYLOADS

    old, fresh = f"{h.trace_id}-old", f"{h.trace_id}-new"
    for trace, age in ((old, PAYLOAD_RETENTION_DAYS * A_DAY + A_DAY), (fresh, A_DAY)):
        await h.execute(
            text(
                "INSERT INTO obs.trace_step (trace_id, step, parent, kind, name, attributes,"
                " payload_in, payload_out, recorded_at)"
                " VALUES (:trace, 0, NULL, 'request', 'answer', '{}'::jsonb, :masked, :masked,"
                " now() - :age)"
            ).bindparams(trace=trace, masked=MASKED_PAYLOADS[0], age=age)
        )

    try:
        async with h.connection.begin_nested():
            await h.connection.execute(text("SELECT trace_id FROM obs.trace_step"))
    except DBAPIError:
        pass
    else:
        raise CheckFailedError(THE_APPLICATION_COULD_READ_A_STEP)

    deleted = await h.execute(text("DELETE FROM obs.trace_step"))
    removed = int(getattr(deleted, "rowcount", 0))
    if removed < 1:
        raise CheckFailedError(AN_EXPIRED_STEP_WAS_NOT_REMOVED)

    async with h.connection.begin_nested():
        await h.connection.execute(text("RESET ROLE"))
        left = (
            (
                await h.connection.execute(
                    text(
                        "SELECT trace_id FROM obs.trace_step WHERE trace_id IN (:old, :fresh)"
                    ).bindparams(old=old, fresh=fresh)
                )
            )
            .scalars()
            .all()
        )
        await h.connection.exec_driver_sql(SET_APPLICATION_ROLE)
    if fresh not in left:
        raise CheckFailedError(A_FRESH_STEP_WAS_REMOVED)
    if old in left:
        raise CheckFailedError(AN_EXPIRED_STEP_WAS_NOT_REMOVED)
