"""Install check for the peak load runs listed beside the service levels they are judged against.

`brain.ops.load_run_store` keeps a row for each run of the peak test and, until
`GET /report/service-levels/load-runs`, no screen read it. This keeps one run of its own in the
check's rolled-back transaction and asks the route as the people it is for.

**What is held.** The run is listed, each lane's figures beside the objective the product declares
for it, held against the figures the owner stated (the fast lane's 500 milliseconds and the answer
lane's eight seconds) and not against the table's own output; a run smaller than the stated peak
says so; the listing names no person and no question; and a reader of one department's usage is
shown no runs, which is also what an install that has never been run shows.

**It does not assume an empty install.** The run is found among whatever runs the install has kept
by its own id, and nothing that was there is read as this check's.

Task ids: M36.2.4.3
"""

from __future__ import annotations

import uuid
from typing import Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2146

A, _B = RESERVED_DEPARTMENTS

#: Restated rather than imported, so a change to the route's authority fails the check.
READS_USAGE: Final = "read:usage"

#: The objectives the owner stated, in milliseconds: the fast lane's and the answer lane's 95th
#: percentile. Written here and not read from the table, which is what is being held to them.
FAST_OBJECTIVE_MS: Final = 500
ANSWER_OBJECTIVE_MS: Final = 8_000

THE_RUN_WAS_NOT_LISTED: Final = (
    "a peak run the install kept was not listed to a reader of the service levels"
)
A_LANE_HAD_THE_WRONG_OBJECTIVE: Final = (
    "a lane's figures were not shown beside the objective the owner stated for it"
)
A_SMALL_RUN_WAS_CALLED_THE_PEAK: Final = "a run smaller than the stated peak was listed as the peak"
THE_LISTING_NAMED_A_PERSON_OR_QUESTION: Final = "the listing carried a run's person or question"
A_DEPARTMENT_READER_WAS_SHOWN_RUNS: Final = (
    "a reader of one department's usage was shown the peak runs"
)


@check(
    leaves=("M36.2.4.3",),
    sentence=(
        "A peak run the install kept is listed to a reader of the service levels with each lane's "
        "figures beside the objective that lane is held to and, if it was smaller than the stated "
        "peak, saying so, naming no person and no question; a reader of one department's usage is "
        "shown no runs."
    ),
)
async def a_kept_peak_run_is_listed_beside_the_service_levels(h: Harness) -> None:
    from brain.load_run_routes import load_runs
    from brain.ops.load_run_store import LaneFigures, RunRecord, keep_run

    await h.found_departments()
    levels, department = h.principal(A, "levels"), h.principal(A, "department")
    await h.person(levels, department=A, grants=((READS_USAGE, Scope.unrestricted()),))
    await h.person(department, department=A, grants=((READS_USAGE, Scope.department(A)),))
    run_id = uuid.uuid4().hex
    record = RunRecord(
        run_id=run_id,
        commit="abc1234",
        profile="check",
        started_at=h.now,
        seconds_run=1.0,
        stated_arrivals_per_second=2.0,
        stated_in_flight=16.0,
        arrivals_per_second=40.0,
        planned=80,
        sent=80,
        not_sent=0,
        most_in_flight=9,
        people=1,
        at_stated_peak=False,
        held=True,
        interactive_shed=0,
        lanes=(
            LaneFigures("fast", 40, 12.0, 1.0, 0),
            LaneFigures("answer", 40, 3_200.0, 0.999, 0),
        ),
        findings=("the fast lane held", "the answer lane held"),
    )
    async with h.sessions() as session:
        await keep_run(session, record)
        await session.commit()
    console = console_for(h)
    shown = await load_runs(console.request(), await asking_as(h, levels))
    ours = next((one for one in shown.runs if one.run_id == run_id), None)
    if ours is None:
        raise CheckFailedError(THE_RUN_WAS_NOT_LISTED)
    objectives = {one.lane: one.objective_p95_ms for one in ours.lanes}
    if objectives != {"fast": FAST_OBJECTIVE_MS, "answer": ANSWER_OBJECTIVE_MS}:
        raise CheckFailedError(A_LANE_HAD_THE_WRONG_OBJECTIVE)
    if ours.at_stated_peak:
        raise CheckFailedError(A_SMALL_RUN_WAS_CALLED_THE_PEAK)
    if levels in ours.model_dump_json() or department in ours.model_dump_json():
        raise CheckFailedError(THE_LISTING_NAMED_A_PERSON_OR_QUESTION)
    narrow = await load_runs(console.request(), await asking_as(h, department))
    if narrow.runs:
        raise CheckFailedError(A_DEPARTMENT_READER_WAS_SHOWN_RUNS)
