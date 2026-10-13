"""The install acceptance check for the dead-letter list: a job the sweep set aside is shown to who
may see it and to nobody else.

**The sweep writes `ops.dead_letter` on the queue's own connection, which the role a check runs as
cannot do and must not**, so this check cannot make the install set a job aside. What it can do is
read what the install's own sweep has recorded there and ask the screen's own function who is shown
it. A reader holding the dead-letter capability over everything is shown the newest row; a reader
with no grant is shown nothing, and the list they get is the list they would get with no row at all,
so nothing says a row was withheld. **An install that has set no job aside says so and the check is
not run**, which is the healthy state and the one in which this check cannot show anything.

Task ids: M17.1.5
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2070

#: Said when the install has no job set aside to read.
NO_JOB_HAS_BEEN_SET_ASIDE: Final = (
    "no job has been set aside on this install, so the sweep has recorded no dead letter to "
    "read; the next acceptance run after one is set aside judges it"
)


@check(
    leaves=("M17.1.5",),
    sentence=(
        "A job the recovery sweep set aside for a person, read from the install's own record of "
        "them, is shown to a reader holding the dead-letter capability and not to a reader with no "
        "grant, whose list is the one they would get had it never been written."
    ),
)
async def a_job_set_aside_is_listed_to_those_who_may_see_it(h: Harness) -> None:
    from brain.core.scope import Scope
    from brain.gate.context import TrafficClass
    from brain.jobs_routes import dead_letters_shown
    from brain.ops.jobs import DEAD_LETTER_CAPABILITY, DeadLetter, DeadLetterReason
    from brain.tables.dead_letter import DeadLetterRow

    async with h.sessions() as session:
        rows = (
            (
                await session.execute(
                    select(DeadLetterRow).order_by(DeadLetterRow.set_aside_at.desc()).limit(50)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        raise CheckNotRunError(NO_JOB_HAS_BEEN_SET_ASIDE)
    entries = [
        DeadLetter(
            job_id=row.job_id,
            task=row.task,
            principal_id=row.principal_id,
            traffic_class=TrafficClass(row.traffic_class),
            reason=DeadLetterReason(row.reason),
            attempts=row.attempts,
            at=row.set_aside_at,
        )
        for row in rows
    ]

    await h.found_departments()
    holder, stranger = h.principal(A, "holder"), h.principal(A, "stranger")
    await h.person(
        holder, department=A, grants=[(DEAD_LETTER_CAPABILITY.value, Scope.unrestricted())]
    )
    await h.person(stranger, department=A)

    seen = dead_letters_shown(entries, await h.reach(holder), h.now)
    if [one.job_id for one in seen] != [one.job_id for one in entries]:
        raise CheckFailedError("a holder of the dead-letter capability was not shown every job")
    if dead_letters_shown(entries, await h.reach(stranger), h.now) != dead_letters_shown(
        [], await h.reach(stranger), h.now
    ):
        raise CheckFailedError("a reader with no grant was shown a job set aside for a person")
    if any(
        one.reason not in {reason.value for reason in DeadLetterReason}
        or not one.task
        or one.attempts < 0
        for one in seen
    ):
        raise CheckFailedError("a dead letter was shown without its task, reason or attempts")
