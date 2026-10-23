"""The install acceptance check for the job queue: a job put on the install's queue is fetched and
run by a worker, once, with the arguments it was given.

**The check puts a job of its own on the install's own queue and runs it with a worker of its
own.** The queue is the install's: its tables, its connection (the owner's, never the
application's, which the queue refuses), and the path every task of ours takes, `register_task`
and then `enqueue_job`. What the check does not borrow is the install's worker, which is not the
check's to start, stop or wait for. See `brain.ops.queue.run_probe_job` and
`brain.ops.queue.A_PROBE_JOB_WAITS_FOR_THE_CHECK_S_OWN_WORKER`, which say why the probe waits on the
one queue no worker drains by allocation and what removes it afterwards.

**What it shows**: the job lands in the driver's table waiting, on the queue its traffic class
derives; a worker started with the figures `driver_options` derives for a shard fetches it and
runs the task once, with the arguments it carried and nothing else; and the queue records the job
as succeeded. **What it does not show**: that the install's own worker is up and draining its
queues, which the worker's heartbeat and the Scheduled jobs screen say; the queue's behaviour
under load; and the recovery sweep, which `acceptance_checks_recovery` shows.

**Not run when the install's queue cannot be reached from this process**, in three sentences of
their own: no queue connection is named, the queue refuses the connection this process would open,
or the queue's tables are not there yet. A fourth, when something else on the install fetched
the probe before the check's worker did, which means an operator allocated slots to the queue the
probe uses.

**What it leaves**: nothing. The probe job and its events are removed by the probe prefix on its
queue when the check ends, whatever happened, and again at the start of the next, so a process
killed between the two leaves rows the next run removes by name.

Task ids: M17.1.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.ops.queue import ProbedJob

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2065

# ----------------------------------------------------------------------- not run
NO_QUEUE_CONNECTION_IS_NAMED: Final = (
    "the process running this check names no database for the queue, so no job could be put on it"
)
THE_QUEUE_REFUSES_THIS_PROCESS_S_CONNECTION: Final = (
    "the queue refuses the connection this process would open for it, which it will not share "
    "with the application's, so no job could be put on it from here"
)
NO_QUEUE_IS_INSTALLED_HERE: Final = (
    "the install's queue tables are not there yet, which the worker makes when it first starts, "
    "so no job could be put on it"
)
SOMETHING_ELSE_FETCHED_THE_PROBE: Final = (
    "another worker on this install fetched the check's job before the check's own worker did, "
    "so an operator has allocated slots to the queue the check uses and the check cannot see its "
    "own worker run it"
)

# ------------------------------------------------------------------------ failed
THE_QUEUE_DID_NOT_ANSWER: Final = "the install's queue did not answer on its own connection"
THE_QUEUE_REFUSED_THE_JOB: Final = (
    "the queue refused a job of a registered task on the queue its traffic class derives, or "
    "could not take it"
)
THE_WORKER_DID_NOT_FINISH: Final = (
    "the check's own worker did not empty the queue it was given within the time allowed"
)
THE_JOB_WAS_NOT_WAITING: Final = "an enqueued job was not waiting in the queue's table"
THE_JOB_WAS_ON_ANOTHER_QUEUE: Final = "the job was not put on the queue its traffic class derives"
THE_WORKER_DID_NOT_RUN_THE_JOB: Final = "a worker given a waiting job did not run it"
THE_JOB_RAN_WITH_OTHER_ARGUMENTS: Final = (
    "the task ran more than once or with arguments other than the ones the job carried"
)
THE_QUEUE_DID_NOT_RECORD_THE_RUN: Final = (
    "the job's task ran and the queue did not record the job as succeeded"
)
A_FAILED_JOB_WAS_NOT_RECORDED_FAILED: Final = (
    "the job's task raised and the queue did not record the job as failed"
)

#: The queue a probe job of the traffic class named is enqueued onto, stated here from the class'
#: own word and not from the function that derives it, so the check compares the two.
PROBE_QUEUE: Final = "human_interactive"


async def probe_a_job(h: Harness, *, fails: bool, reason: str = "") -> ProbedJob:
    """One probe job put on the install's queue, run by the check's own worker and checked.

    Raises a sentence for each step that did not hold. `fails` makes the probe task raise, which is
    what a job set aside needs, and `reason` then writes it into the dead-letter table through the
    call the recovery sweep makes. Whatever it made is removed when the check ends.
    """
    from datetime import UTC, datetime

    from brain.ops.queue import (
        PROBE_TASK_PREFIX,
        QueueError,
        forget_probe_jobs,
        probe_tables_are_there,
        queue_url_of,
        run_probe_job,
    )

    queue_url = queue_url_of(h.settings)
    if not queue_url:
        raise CheckNotRunError(NO_QUEUE_CONNECTION_IS_NAMED)
    try:
        there = await probe_tables_are_there(queue_url)
    except QueueError as exc:
        raise CheckNotRunError(THE_QUEUE_REFUSES_THIS_PROCESS_S_CONNECTION) from exc
    except Exception as exc:
        raise CheckFailedError(THE_QUEUE_DID_NOT_ANSWER) from exc
    if not there:
        raise CheckNotRunError(NO_QUEUE_IS_INSTALLED_HERE)
    h.removes(lambda: forget_probe_jobs(queue_url))
    try:
        await forget_probe_jobs(queue_url)
    except Exception as exc:
        raise CheckFailedError(THE_QUEUE_DID_NOT_ANSWER) from exc

    word = h.word()
    seen: list[str] = []

    async def probe(*, word: str) -> str:
        seen.append(word)
        if fails:
            msg = "the probe task was asked to fail"
            raise RuntimeError(msg)
        return "ran"

    try:
        probed = await run_probe_job(
            queue_url,
            task=f"{PROBE_TASK_PREFIX}{h.run}",
            run=probe,
            args={"word": word},
            at=datetime.now(UTC),
            set_aside_reason=reason,
        )
    except TimeoutError as exc:
        raise CheckFailedError(THE_WORKER_DID_NOT_FINISH) from exc
    except QueueError as exc:
        raise CheckFailedError(THE_QUEUE_REFUSED_THE_JOB) from exc
    except Exception as exc:
        raise CheckFailedError(THE_QUEUE_DID_NOT_ANSWER) from exc

    if probed.status_waiting != "todo":
        raise CheckFailedError(THE_JOB_WAS_NOT_WAITING)
    if probed.queue != PROBE_QUEUE:
        raise CheckFailedError(THE_JOB_WAS_ON_ANOTHER_QUEUE)
    if not seen:
        if probed.status_after == "todo":
            raise CheckFailedError(THE_WORKER_DID_NOT_RUN_THE_JOB)
        raise CheckNotRunError(SOMETHING_ELSE_FETCHED_THE_PROBE)
    if seen != [word]:
        raise CheckFailedError(THE_JOB_RAN_WITH_OTHER_ARGUMENTS)
    if not fails and probed.status_after != "succeeded":
        raise CheckFailedError(THE_QUEUE_DID_NOT_RECORD_THE_RUN)
    if fails and probed.status_after != "failed":
        raise CheckFailedError(A_FAILED_JOB_WAS_NOT_RECORDED_FAILED)
    return probed


@check(
    leaves=("M17.1.2",),
    sentence=(
        "A job of a registered task put on the install's own queue waits there on the queue its "
        "traffic class derives, is fetched by a worker started with the figures the queue derives "
        "for a shard, and is run once with the arguments it carried, and the queue records it as "
        "succeeded."
    ),
)
async def a_job_put_on_the_install_s_queue_is_fetched_and_run_by_a_worker(h: Harness) -> None:
    await probe_a_job(h, fails=False)
