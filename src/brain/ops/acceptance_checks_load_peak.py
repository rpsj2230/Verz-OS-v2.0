"""The install's check for the peak load run's machinery: a short bounded run, judged and kept, in a
transaction that is rolled back.

The peak run itself (`python -m brain.ops.load_peak`) is two answers a second for ten minutes at the
install's real answer route, spends the model's calls, and is never started by the install. What
this check proves is the part of it that can be proved cheaply and on every install: that the
driver sends what a profile plans, concurrently and not one after another; that the judge reads
each lane off real answers against the service levels; that the install's answer route records
each request on the lane the run assumed it would take; that the result is kept as figures only; and
that the command's refusals are the ones it makes.

**It does not send a question to the model.** The answers come from the same function the answer
route calls (`brain.api_routes.answered_for`), as a reserved person in acceptance_a, with the model
behind it a stand-in that keeps its prompt and costs nothing (`brain.ops.acceptance_checks_memory`).
A question about a price list is answered by a rule and one about a document by the stand-in, which
is exactly the two lanes the run's mix is made of.

**Concurrent, over a transaction that cannot be used concurrently.** The run's arrivals are tasks
started at their offsets whatever the earlier ones are doing, and the check's database is one
transaction on one connection, so the sender takes a lock around the call. The arrivals still
overlap, and what the lock serialises is the database work the check cannot do twice at once, so
the figure `most_in_flight` is what the driver asked of the sender and the p95 is the sender's time
including the wait. Neither is a statement about the install's speed, which is what the real run
is for: the check asserts that they are measured, not that they are good.

**It does not assume an empty install.** The run's row is looked up by its own id among whatever
runs the install has kept, and nothing that was there is read as this check's.

**Nothing leaves the transaction.** The row the check keeps, the requests it makes and their ledger
entries exist for the length of the check. A real run's requests stay in the ledger, which is
append-only, attributed to the test people: see `brain.ops.load_peak.WHAT_A_RUN_LEAVES_BEHIND`.

Task ids: M22.3.3
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_memory import PAIRED_QUESTION, KeptPrompts, a_document
from brain.ops.acceptance_checks_speed import a_rule_on_a_list, asked_on, rules_app
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.load_peak import Shape

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 275

#: How many requests the short run plans, and the rate and length that plan them. Forty of each
#: lane is twice the fewest for which a 95th percentile is more than the maximum, so each lane is
#: measured, and the rate is high enough that arrivals overlap the way a peak's do.
SHORT_RUN_REQUESTS: Final = 80
SHORT_RUN_ARRIVALS_PER_SECOND: Final = 1600.0
SHORT_RUN_SECONDS: Final = 0.05

#: The mix the short run uses, so each lane gets at least the twenty requests a p95 needs.
SHORT_RUN_MIX: Final = 0.5


@check(
    leaves=("M22.3.3",),
    sentence=(
        "A short run through the peak test's own driver, as a reserved person asking the answer "
        "route with a stand-in for the model, sends every request it plans several at once, is "
        "read lane by lane against the service levels, is recorded as smaller than the stated "
        "peak and is kept and read back as figures naming no person and no question; the "
        "command refuses what it must. Nothing is left behind."
    ),
)
async def a_short_peak_run_is_driven_judged_and_kept_and_leaves_nothing(h: Harness) -> None:
    from brain.core.lane import Lane
    from brain.gate.context import Channel
    from brain.ops import load_peak
    from brain.ops.load_run_store import keep_run, read_runs
    from brain.ops.telemetry import RequestStatus

    made = await a_rule_on_a_list(h)
    words = await a_document(h)
    stand_in = KeptPrompts()
    app = await rules_app(h, stand_in)

    questions = {
        Lane.FAST: (made.question(),),
        Lane.ANSWER: (PAIRED_QUESTION.format(key=words.key),),
    }
    profile = load_peak.Profile(
        questions=questions,
        people=1,
        arrivals_per_second=SHORT_RUN_ARRIVALS_PER_SECOND,
        seconds=SHORT_RUN_SECONDS,
        max_requests=SHORT_RUN_REQUESTS,
        mix={Lane.ANSWER: SHORT_RUN_MIX, Lane.FAST: SHORT_RUN_MIX},
    )
    planned = load_peak.arrivals(profile)
    asked_fast = sum(1 for _, shape in planned if shape.lane is Lane.FAST)
    asked_answer = len(planned) - asked_fast

    lock = asyncio.Lock()
    counter = 0

    async def send(shape: Shape) -> load_peak.Sample:
        nonlocal counter
        begun = time.perf_counter()
        async with lock:
            counter += 1
            await asked_on(h, app, made.reader, shape.question, counter, Channel.CONSOLE)
        return load_peak.Sample(
            lane=shape.lane, status=RequestStatus.ANSWERED, seconds=time.perf_counter() - begun
        )

    measured = await load_peak.drive_measured(profile, send)
    if len(measured.samples) != len(planned) or measured.not_sent:
        raise CheckFailedError("the run did not send every request its profile planned")
    if measured.most_in_flight < 2:
        raise CheckFailedError("the run's requests were sent one after another, not together")

    report = load_peak.judge(measured.samples)
    for reading in report.readings:
        if reading.p95_ms is None or reading.success_rate != 1.0 or reading.shed:
            raise CheckFailedError("a lane's figures were not read off the answers it was sent")

    # The install recorded each request, on the lane the run assumed it would take.
    prefix = f"{h.trace_id}-"
    counted = (
        await h.execute(
            text(
                "SELECT lane, count(*) FROM obs.request_telemetry"
                " WHERE left(trace_id, :width) = :prefix GROUP BY lane"
            ).bindparams(width=len(prefix), prefix=prefix)
        )
    ).all()
    by_lane = {str(lane): int(count) for lane, count in counted}
    if by_lane != {"fast": asked_fast, "answer": asked_answer}:
        raise CheckFailedError("the install did not record each request on the lane it was sent to")
    if len(stand_in.sent) != asked_answer:
        raise CheckFailedError(
            "the model's stand-in was not asked once for each answer-lane request"
        )

    stated = load_peak.stated_peak(load_peak.DEFAULT_PROFILE)
    run_id = uuid.uuid4().hex
    record = load_peak.record_of(
        report,
        measured,
        profile,
        stated,
        started_at=h.now,
        commit=h.settings.resolved_commit(),
        run_id=run_id,
    )
    if record.at_stated_peak:
        raise CheckFailedError("a run of eighty requests was recorded as the stated peak")

    async with h.sessions() as session:
        await keep_run(session, record)
        kept = [one for one in await read_runs(session) if one.run_id == run_id]
    if kept != [record]:
        raise CheckFailedError("the run's row was not read back from the install as it was kept")
    stored = json.dumps(record.as_value())
    for given in (
        made.reader,
        words.key,
        words.value,
        *questions[Lane.FAST],
        *questions[Lane.ANSWER],
    ):
        if given in stored:
            raise CheckFailedError("the run's row named a person or a question")

    caller = load_peak.CallerFacts(made.reader, load_peak.LOAD_TEST_DEPARTMENT)

    def refusals(**changes: Any) -> tuple[str, ...]:
        fields: dict[str, Any] = {
            "switch_is_on": True,
            "callers": (caller,),
            "planned": len(planned),
            "confirmed": len(planned),
        }
        fields.update(changes)
        return load_peak.refusals_before_a_run(**fields)

    if refusals():
        raise CheckFailedError("the command refused a run that met every condition")
    for broken in (
        {"switch_is_on": False},
        {"callers": (load_peak.CallerFacts(made.reader, A),)},
        {"confirmed": len(planned) + 1},
    ):
        if not refusals(**broken):
            raise CheckFailedError("the command did not refuse a run that broke one of its rules")
