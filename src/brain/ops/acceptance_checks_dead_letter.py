"""The install acceptance check for the dead-letter list: a job set aside is shown to who may see
it and to nobody else.

**The check sets a job aside itself and reads it back through the route a person reads.** Until
2026-10-23 it read whatever the install's own recovery sweep had recorded, and an install that
had set no job aside, which is the healthy one, could never be shown anything: the check said it
was not run on every install that was working. The application's login may not write
`ops.dead_letter` (it is granted `SELECT` alone, `0228`), and must not, so the check does what the
sweep does on the queue's own connection: it puts a job of its own on the install's queue, runs it
with a worker of its own, lets its task raise, and writes the failed job into the table through
`DriverQueue.keep_aside`, the call the sweep makes. See `brain.ops.acceptance_checks_queue`, which
says what the probe is, why its queue is one no worker of the install drains, and what removes it.

**What it shows.** A reader holding the dead-letter capability over everything is listed the job,
with its task, the reason it was set aside and how many times it ran, through `GET /jobs/dead` as
the Jobs screen calls it. A reader with no grant is listed nothing: the list they get is the list
they would get had the job never been written, with no count and no placeholder, so nothing says a
row was withheld. **What it leaves**: nothing. The probe's job, its events and its dead-letter row
are removed by the probe's prefix when the check ends and again before the next, so a process
killed in between leaves rows the next run removes by name.

**Not run** exactly where the queue check is: no queue connection, one the queue refuses, or a
queue not yet installed.

Task ids: M17.1.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_queue import probe_a_job
from brain.ops.acceptance_operations_console import asking_as, console_for
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2070

NOT_SHOWN_TO_THE_HOLDER: Final = (
    "a holder of the dead-letter capability was not shown the job that was set aside"
)
SHOWN_WITHOUT_ITS_FACTS: Final = (
    "a dead letter was shown without its job, the reason it was set aside or its attempts"
)
SHOWN_TO_A_STRANGER: Final = "a reader with no grant was shown a job set aside for a person"


@check(
    leaves=("M17.1.5",),
    sentence=(
        "A job whose task raised on the install's own queue and was set aside is listed, with the "
        "reason and its attempts, to a reader holding the dead-letter capability and not to a "
        "reader with no grant, whose list is the one they would get had it never been written; "
        "nothing the check made is left behind."
    ),
)
async def a_job_set_aside_is_listed_to_those_who_may_see_it(h: Harness) -> None:
    from brain.core.scope import Scope
    from brain.jobs_routes import dead_letters
    from brain.ops.jobs import DEAD_LETTER_CAPABILITY, DeadLetterReason
    from brain.ops.queue import PROBE_TASK_PREFIX

    reason = DeadLetterReason.ATTEMPTS_EXHAUSTED
    probed = await probe_a_job(h, fails=True, reason=reason.value)

    await h.found_departments()
    holder, stranger = h.principal(A, "holder"), h.principal(A, "stranger")
    await h.person(
        holder, department=A, grants=[(DEAD_LETTER_CAPABILITY.value, Scope.unrestricted())]
    )
    await h.person(stranger, department=A)
    console = console_for(h)

    held = await dead_letters(console.request(), await asking_as(h, holder))
    mine = [one for one in held.items if one.task.startswith(PROBE_TASK_PREFIX)]
    if len(mine) != 1:
        raise CheckFailedError(NOT_SHOWN_TO_THE_HOLDER)
    [shown] = mine
    if shown.job_id != str(probed.job_id) or shown.reason != reason.value or shown.attempts < 1:
        raise CheckFailedError(SHOWN_WITHOUT_ITS_FACTS)

    refused = await dead_letters(console.request(), await asking_as(h, stranger))
    if refused.items:
        raise CheckFailedError(SHOWN_TO_A_STRANGER)
