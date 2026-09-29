"""The install acceptance checks for what the install is made of: its worker, its database's
connections, its trace store and the processor the scrub runs on.

Four checks over things a person cannot see on a screen and a deploy can still get wrong. The first
two read the worker the suite runs in: the allocation its container was started with, laid out per
traffic class by the worker's own `plan_for`, and the connection bound it declares, held against the
ceiling the install's database actually admits. The third writes a run's trace through the recorder
the application installs and reads it back as an operator would, under the separate role and after
its row. The fourth times the personal data scrub on the machine the install runs on, which is the
only machine a budget for it can be measured on.

**Two of them read the process they run in, and a process that is not a worker says so.** The
suite runs on the worker's schedule, so the worker's environment is the container's own, and
`brain.ops.worker` already has a function for every question asked of it: `preflight`,
`declared_slots`, `plan_for`, `declared_pool_max`, `pool_declaration_gaps`. The checks ask those
functions and restate none of their arithmetic. A process holding no `QUEUE_URL` is not a worker
(the application has none), and `NOT_IN_A_WORKER` is what it records rather than a pass about a
layout nobody started. The environment is read through `brain.settings.process_environment`, the one
reader, and no value from it reaches a result, a log line or an exception. See
`A_WORKER_CHECK_READS_THE_WORKER_IT_RUNS_IN`.

**Each refusal is shown firing on the install's own environment, not on a fixture.** A layout that
passes proves nothing about the guard behind it: the worker check removes one traffic class's
allocation from a copy of the environment and requires `preflight` to refuse it, and the connection
check removes the pool declaration and requires `pool_declaration_gaps` to refuse that. Both copies
are dictionaries in the check's frame; the process's own environment is not touched.

**The trace check is the audit check's trace half, on its own.** `brain.ops.acceptance_audit`
asserts the same store inside a check about the whole ledger, which records "not run" for reasons
that have nothing to do with a trace. So the trace is proved here by the same helper,
`_the_trace_is_masked_and_held_apart`, over a run of its own, and the two checks cannot disagree
about what masked means.

**The scrub is timed in a thread and its figure goes to the worker's log.** A result names no value
(`brain.ops.acceptance.A_RESULT_NAMES_NO_DATA`), so the check passes or fails against
`brain.ops.pii.BUDGET_MS_PER_KIB` and the measured rate is logged as `acceptance.scrub_measured`,
which an operator reads with the install's other logs. Timing in a thread keeps the worker's loop,
and the heartbeat it writes, turning while a second of arithmetic runs. See
`THE_SCRUB_IS_TIMED_WHERE_IT_WILL_RUN`.

Task ids: M32.4.1.4, M32.7.3, M32.1.2.1, M32.1.2.2, M32.1.2.5, M32.2.2.4
"""

from __future__ import annotations

import asyncio
import os
import platform
import time
from collections.abc import Callable, Mapping
from functools import partial
from typing import Final

import structlog
from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why two checks read the process they run in, and what they read.
A_WORKER_CHECK_READS_THE_WORKER_IT_RUNS_IN: Final = (
    "The suite runs on the worker's schedule, so the process running a check is a worker "
    "container started from its own environment. The layout and the connection bound are read "
    "from that environment through the worker's own functions, the ones that decided whether it "
    "could start, and a process with no queue address is not a worker and is not judged as one."
)

#: Why the scrub is timed on the install and nowhere else.
THE_SCRUB_IS_TIMED_WHERE_IT_WILL_RUN: Final = (
    "This system is single-tenant and client-hosted, so the processor a scrub's budget is about "
    "is the one each install runs on. The check times the real scrubber there on every run of the "
    "suite, logs the rate it measured, and fails when the rate is over the budget; a figure taken "
    "on a build machine is recorded beside the budget and is not this."
)

#: Said by the two worker checks in a process that is not a worker.
NOT_IN_A_WORKER: Final = (
    "the process running this check holds no queue address, so it is not one of the install's "
    "workers and there is no worker layout or worker connection bound to read; the worker's own "
    "run of the suite reads them"
)

# ------------------------------------------------------------------------ the figures
#: How much identifier-dense text one timing covers. Sixteen kibibytes: well above anything a
#: question sends, small enough that the whole run is about a second on a shared host.
SCRUB_SAMPLE_CHARS: Final = 16384

#: How many timings the ninety-fifth percentile is taken over. Three times the fewest
#: `brain.ops.pii.MINIMUM_TIMED_SAMPLES` allows, so one slow sample is not the figure.
SCRUB_SAMPLES: Final = 60

#: The clock a scrub's timings are read from. A name of its own so the suite can hand the check a
#: clock that ticks the same whatever else the machine running it is doing; on an install it is
#: the processor's own.
SCRUB_CLOCK: Callable[[], float] = time.perf_counter

#: Why a check reads a trace, as `brain.ops.tracing.PayloadRead` requires a reason.
TRACE_READ_REASON: Final = "An install acceptance check reading its own run's trace"


# ------------------------------------------------------------------------ the helpers
def _worker_environment() -> Mapping[str, str]:
    """The environment of the worker this check runs in, or `NOT_IN_A_WORKER`."""
    from brain.ops.worker import QUEUE_URL_ENV
    from brain.settings import process_environment

    env = process_environment()
    if not (env.get(QUEUE_URL_ENV) or "").strip():
        raise CheckNotRunError(NOT_IN_A_WORKER)
    return env


def _this_processor() -> str:
    """The processor a timing was taken on, as the process can see it. No value from any file."""
    machine = platform.machine() or "an unnamed architecture"
    return f"this install's own processor ({machine}, {os.cpu_count() or 0} logical CPUs)"


# ------------------------------------------------------------------- 1. the worker's layout
@check(
    leaves=("M32.4.1.4",),
    sentence=(
        "The worker running the suite was started from its container's declared allocation: "
        "its own start-up checks refuse nothing, it drains a queue per traffic class with that "
        "class's own number of slots, the slots fit the memory its container is limited to, and "
        "the same environment with one class's allocation taken away is refused."
    ),
)
async def the_worker_serves_each_traffic_class_from_its_own_slots(h: Harness) -> None:
    del h
    from brain.ops.queue import SlotClass
    from brain.ops.worker import (
        declared_component,
        declared_slot_class,
        declared_slots,
        plan_for,
        preflight,
        slot_env_name,
    )

    env = _worker_environment()
    if preflight(env):
        raise CheckFailedError(
            "the worker's own start-up checks would refuse the container the suite runs in"
        )
    allocation, unreadable = declared_slots(env)
    slot_class, _ = declared_slot_class(env)
    plan = plan_for(allocation, worker_component=declared_component(env), slot_class=slot_class)
    drained = {shard.traffic_class for shard in plan.shards}
    if (
        unreadable
        or len(drained) < 2
        or len({shard.queue for shard in plan.shards}) != len(drained)
    ):
        raise CheckFailedError(
            "the worker does not drain a queue of its own for each traffic class"
        )
    if any(shard.concurrency != allocation[shard.traffic_class] for shard in plan.shards):
        raise CheckFailedError(
            "a traffic class runs at a concurrency its container did not declare"
        )
    if slot_class is SlotClass.STANDARD and plan.slot_memory_mib > plan.memory_mib:
        raise CheckFailedError("the worker's slots need more memory than its container is given")

    busiest = max(drained, key=lambda one: allocation[one])
    without = {name: value for name, value in env.items() if name != slot_env_name(busiest)}
    if not preflight(without):
        raise CheckFailedError("a worker missing one traffic class's allocation would have started")


# ------------------------------------------------------- 2. the database's connection budget
@check(
    leaves=("M32.7.3",),
    sentence=(
        "The install's database admits exactly the connections its declared budget is computed "
        "against and holds back the administrators' reserve, the declared clients leave room "
        "inside that ceiling, the connections open on it now are within what those clients may "
        "hold, and the worker running the suite declares the bound the budget gives it, while "
        "the same worker with no declared bound is refused."
    ),
)
async def every_database_client_is_bounded_within_the_install_s_ceiling(h: Harness) -> None:
    from brain.ops.connections import database, demand_on, headroom_on
    from brain.ops.worker import (
        POOL_MAX_ENV,
        declared_component,
        declared_pool_max,
        pool_declaration_gaps,
    )

    env = _worker_environment()
    declared = database("db")
    admits, reserved, open_now = (
        await h.execute(
            text(
                "SELECT current_setting('max_connections')::int,"
                " current_setting('superuser_reserved_connections')::int,"
                # Every connection to a database on this server. `datname` is the column a role
                # that is not the server's administrator can read of another role's session;
                # `backend_type` reads as null there, so filtering on it would count nothing.
                " (SELECT count(*) FROM pg_stat_activity WHERE datname IS NOT NULL)"
            )
        )
    ).one()
    if int(admits) != declared.max_connections or int(reserved) != declared.reserved:
        raise CheckFailedError(
            "the install's database admits a different number of connections from the one its "
            "budget is computed against"
        )
    if headroom_on("db") <= 0:
        raise CheckFailedError("the declared clients of the install's database leave it no room")
    if int(open_now) > demand_on("db"):
        raise CheckFailedError(
            "more connections are open on the install's database than its declared clients may hold"
        )

    component = declared_component(env)
    bound, unreadable = declared_pool_max(env)
    if bound is None or unreadable or pool_declaration_gaps(env, worker_component=component):
        raise CheckFailedError("the worker running the suite does not declare its budgeted bound")
    without = {name: value for name, value in env.items() if name != POOL_MAX_ENV}
    if not pool_declaration_gaps(without, worker_component=component):
        raise CheckFailedError("a worker declaring no connection bound would have started")


# -------------------------------------------------------------------- 3. the trace store
@check(
    leaves=("M32.1.2.1", "M32.1.2.2", "M32.1.2.5"),
    sentence=(
        "A read of a reserved person's record by a member of acceptance_a is finished through the "
        "trace recorder the application installs, with a word nothing else holds in the record: "
        "the application's own role cannot read the stored trace, a read without the separate "
        "role is refused and leaves no row, a read with it leaves exactly one row, and every "
        "step read back is masked with the word in none of them."
    ),
)
async def a_run_s_trace_is_stored_masked_and_read_only_after_its_row(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.core.redaction import ChannelPayload
    from brain.gate.context import Channel
    from brain.gate.finish import Finished, Origin, ToolCallOutcome, finish
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_audit import _the_trace_is_masked_and_held_apart
    from brain.ops.trace_store import TraceRecorder

    await h.found_departments()
    asker, subject, operator = (h.principal(A, role) for role in ("asker", "subject", "operator"))
    for one in (asker, subject, operator):
        await h.person(one, department=A)
    person = await StoredPrincipals(h.sessions).live_principal(asker)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")

    trace_id = f"{h.trace_id}-trace"
    canary = h.word()
    record = {"@entity": "personnel", "principal_id": subject, "name": canary}
    await finish(
        (TraceRecorder(h.sessions, environment=h.settings.env),),
        Finished(
            Origin(trace_id=trace_id, principal=person, channel=Channel.CONSOLE),
            h.now,
            ToolCallOutcome(refused=False, disclosed=ChannelPayload(records=(record,))),
            completed_at=h.now,
            entitlement_hash=(await h.reach(asker)).ent_hash(),
            lane=Lane.TASK,
            tool_calls=1,
        ),
    )
    await _the_trace_is_masked_and_held_apart(h, operator, trace_id, canary)


# ------------------------------------------------------------ 4. the scrub on this processor
@check(
    leaves=("M32.2.2.4",),
    sentence=(
        "The personal data scrub is timed on the processor of the install the suite runs on, "
        "over identifier-dense text at the ninety-fifth percentile, and costs no more per "
        "kibibyte than the budget it is held to; the rate measured is in the worker's log."
    ),
)
async def the_scrub_meets_its_budget_on_this_install_s_processor(h: Harness) -> None:
    from brain.ops.pii import BUDGET_MS_PER_KIB, benchmark_text, budget_gaps, measure_scrub

    _worker_environment()
    cost = await asyncio.to_thread(
        partial(
            measure_scrub,
            benchmark_text(SCRUB_SAMPLE_CHARS),
            clock=SCRUB_CLOCK,
            hardware=_this_processor(),
            basis=(
                "measure_scrub over benchmark_text(16384) by the install's acceptance check, "
                "timed with time.perf_counter in a thread of the worker"
            ),
            excludes=(
                "every leg that is not this process: a model leg is a call to another container "
                "bounded by a timeout"
            ),
            taken_on=h.now.date(),
            samples=SCRUB_SAMPLES,
            on_the_client_cpu=True,
        )
    )
    log.info(
        "acceptance.scrub_measured",
        ms_per_kib=round(cost.ms_per_kib, 3),
        budget_ms_per_kib=BUDGET_MS_PER_KIB,
        chars=cost.chars,
        samples=cost.samples,
        cpus=os.cpu_count() or 0,
    )
    if budget_gaps(cost):
        raise CheckFailedError(
            "the scrub cost more per kibibyte on this install's processor than its budget allows"
        )
