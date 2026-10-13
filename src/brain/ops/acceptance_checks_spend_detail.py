"""Install checks for the Spend report's other readings: what an answer costs, the dearest question
shapes, and the budget stops in force.

`brain.console.spend_view` wrote `cost_per_answer`, `shape_report` and `budget_stops` for the
Spend screen and nothing called them. `brain.spend_detail_routes` serves them, and these checks
ask each as the reader it is for over rows the check writes through the stores the request path
writes with, in the check's rolled-back transaction.

**Readers are scoped to a reserved department, so the figures are exactly the check's.** An
install has real spend and the figures are the whole company's; a reader holding the usage
authority over acceptance_a alone is shown acceptance_a's rows only, and nothing else lives there,
so a count of a hundred answers is a hundred and not a hundred plus the company. A reader of
acceptance_b is shown none of them and is told so with no figure. See
`A_FIGURE_IS_ASSERTED_OVER_A_DEPARTMENT_NOTHING_ELSE_LIVES_IN`.

**A hundred answers, because that is how many the ninety-ninth needs.** `spend_view.
minimum_rows` is the figure; with a hundred rows costing one to a hundred the nearest-rank median,
ninetieth and ninety-ninth are fifty, ninety and ninety-nine, each an answer that cost exactly
that, and with five rows only the median is stated. Held against the nearest-rank definition, not
against the module's own output.

Task ids: M21.3.3, M21.3.4, M21.3.6
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import insert

from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import asking_as, console_for
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2140

A, B = RESERVED_DEPARTMENTS

#: Why a figure is asserted over a department nothing else lives in.
A_FIGURE_IS_ASSERTED_OVER_A_DEPARTMENT_NOTHING_ELSE_LIVES_IN: Final = (
    "The company's spend is the install's own, so a total over it would be a statement about the "
    "company. A reader holding the authority over a reserved department is shown that "
    "department's rows only, which are the check's."
)

#: Restated rather than imported, so a change to a route's authority fails its check instead of
#: moving with it.
READS_USAGE: Final = "read:usage"

#: How many answers the distribution check records, which is how many the ninety-ninth needs.
ANSWERS: Final = 100

#: What the machine's run cost, apart from every figure a person's answer can cost.
THE_MACHINES_RUN: Final = 100_000

#: What the two shapes and the unrecorded shape's cost.
THE_DEAR_SHAPE: Final = 9_000
THE_CHEAP_SHAPE: Final = 400
THE_UNKNOWN_SHAPE: Final = 5


async def _run(
    h: Harness,
    *,
    who: str,
    trace: str,
    cost: int,
    kind: PrincipalKind = PrincipalKind.HUMAN,
    traffic: TrafficClass = TrafficClass.HUMAN_INTERACTIVE,
    lane: Lane = Lane.ANSWER,
) -> None:
    from brain.tables.spend import SpendActualRow

    # Inserted as the other install checks insert a cost: the usage recorder is the ledger's one
    # writer, which a test over the source holds (`tests/unit/test_agent_profile.py`).
    async with h.sessions() as session:
        await session.execute(
            insert(SpendActualRow).values(
                principal_id=who,
                principal_kind=kind.value,
                traffic=traffic.value,
                department=A,
                agent_id=None,
                model=f"acc-model-{h.run}",
                lane=lane.value,
                cost_minor=cost,
                at=datetime.now(UTC) - timedelta(minutes=5),
                trace_id=trace,
            )
        )
        await session.commit()


# ----------------------------------------------------------- 1. what an answer costs (M21.3.3)
@check(
    leaves=("M21.3.3",),
    sentence=(
        "A hundred answers costing one to a hundred, recorded in acceptance_a, are shown to a "
        "reader of its spend as a count, a mean and the median, ninetieth and ninety-ninth the "
        "nearest-rank way, with the machine's run left out unless asked for; five answers state "
        "the median alone; and a reader of acceptance_b is told there are none and shown no "
        "figure."
    ),
)
async def what_one_answer_costs_is_a_distribution_not_a_mean(
    h: Harness,
) -> None:
    from brain.spend_detail_routes import cost_of_an_answer

    await h.found_departments()
    asker, sync = h.principal(A, "asker"), h.principal(A, "sync")
    here, there = h.principal(A, "cost"), h.principal(B, "cost")
    await h.person(asker, department=A)
    await h.person(here, department=A, grants=((READS_USAGE, Scope.department(A)),))
    await h.person(there, department=B, grants=((READS_USAGE, Scope.department(B)),))
    console = console_for(h)

    async def figure(who: str, *, machine: bool = False) -> Any:
        return await cost_of_an_answer(
            console.request(), await asking_as(h, who), include_machine=machine
        )

    for cost in range(1, ANSWERS + 1):
        await _run(h, who=asker, trace=f"{h.trace_id}-a{cost}", cost=cost)
    await _run(
        h,
        who=sync,
        trace=f"{h.trace_id}-m",
        cost=THE_MACHINES_RUN,
        kind=PrincipalKind.SERVICE,
        traffic=TrafficClass.AUTOMATION,
    )
    shown = await figure(here)
    stated = {one.quantile: one.cost_minor for one in shown.quantiles}
    if shown.answers != ANSWERS or shown.mean_minor != (ANSWERS + 1) / 2:
        raise CheckFailedError("the cost of an answer was not counted over the answers made")
    if stated != {0.5: 50, 0.9: 90, 0.99: 99}:
        raise CheckFailedError("the quantiles were not the nearest-rank ones of the answers")
    with_machine = await figure(here, machine=True)
    if with_machine.answers != ANSWERS + 1 or not with_machine.machine_included:
        raise CheckFailedError("the machine's run was not counted when it was asked for")
    if shown.machine_included:
        raise CheckFailedError("the report did not say it left machine traffic out")
    nothing = await figure(there)
    if nothing.answers != 0 or nothing.mean_minor is not None or nothing.quantiles:
        raise CheckFailedError("a reader of another department was shown a figure")


# ----------------------------------------------------- 2. the dearest question shapes (M21.3.4)
@check(
    leaves=("M21.3.4",),
    sentence=(
        "Runs of two shapes and one with no shape recorded, joined to their requests, are ranked "
        "dearest first by the Spend report's shapes route for a reader of acceptance_a with the "
        "unrecorded one named as such and never guessed, the total is the lines' sum, and a "
        "reader of acceptance_b is shown none of them."
    ),
)
async def dearest_question_shapes_are_ranked_from_their_own_requests(
    h: Harness,
) -> None:
    from brain.ops.telemetry import QuestionShape, RequestStatus
    from brain.spend_detail_routes import dearest_shapes
    from brain.tables.telemetry import RequestTelemetryRow

    await h.found_departments()
    asker = h.principal(A, "asker")
    here, there = h.principal(A, "shapes"), h.principal(B, "shapes")
    await h.person(asker, department=A)
    await h.person(here, department=A, grants=((READS_USAGE, Scope.department(A)),))
    await h.person(there, department=B, grants=((READS_USAGE, Scope.department(B)),))
    console = console_for(h)

    dear, cheap = QuestionShape(Lane.TASK, 3), QuestionShape(Lane.ANSWER, 0)
    at = datetime.now(UTC) - timedelta(minutes=5)
    for suffix, shape, cost in (("d", dear, THE_DEAR_SHAPE), ("c", cheap, THE_CHEAP_SHAPE)):
        trace = f"{h.trace_id}-{suffix}"
        await _run(h, who=asker, trace=trace, cost=cost, lane=shape.lane)
        await h.execute(
            insert(RequestTelemetryRow).values(
                received_at=at,
                trace_id=trace,
                traffic_class=TrafficClass.HUMAN_INTERACTIVE.value,
                principal=asker,
                entitlement_hash="0" * 32,
                lane=shape.lane.value,
                model=f"acc-model-{h.run}",
                agent_version="acceptance-agent",
                tokens_in=1,
                tokens_out=1,
                cache_hit=False,
                status=RequestStatus.ANSWERED.value,
                duration_ms=1.0,
                tool_count=shape.tool_count,
            )
        )
    await _run(h, who=asker, trace=f"{h.trace_id}-u", cost=THE_UNKNOWN_SHAPE)

    shown = await dearest_shapes(console.request(), await asking_as(h, here))
    ranked = [(one.shape, one.cost_minor) for one in shown.dearest]
    if [one[0] for one in ranked[:2]] != [dear.key, cheap.key]:
        raise CheckFailedError("the shapes were not ranked dearest first from their own requests")
    if dict(ranked)[dear.key] != THE_DEAR_SHAPE or dict(ranked)[cheap.key] != THE_CHEAP_SHAPE:
        raise CheckFailedError("a shape's cost was not what its requests paid")
    if (
        len(ranked) != 3
        or ranked[2][1] != THE_UNKNOWN_SHAPE
        or ranked[2][0] in (dear.key, cheap.key)
    ):
        raise CheckFailedError("a run with no recorded shape was guessed into one")
    if shown.total_minor != sum(cost for _, cost in ranked):
        raise CheckFailedError("the shapes' total was not the sum of their lines")
    hidden = await dearest_shapes(console.request(), await asking_as(h, there))
    if hidden.dearest or hidden.total_minor != 0:
        raise CheckFailedError("a reader of another department was shown the shapes")


# ----------------------------------------------------------- 3. every stop in force (M21.3.6)
@check(
    leaves=("M21.3.6",),
    sentence=(
        "A stop recorded against acceptance_a's budget, and one only said and not enforced, are "
        "listed by the stops route to a reader of acceptance_a's spend with whether each was "
        "enforced; a reader of acceptance_b is shown neither and no count, and a stop whose "
        "period has ended is not listed."
    ),
)
async def every_budget_stop_in_force_is_listed_to_those_who_may_be_told(h: Harness) -> None:
    from brain.ops.budget_stop import Addressing, Consequence, Notice, Stop
    from brain.ops.budget_stop_store import Asker, record
    from brain.ops.budgets import BudgetLevel, BudgetPeriod
    from brain.spend_detail_routes import stops_in_force

    await h.found_departments()
    here, there, asker = h.principal(A, "stops"), h.principal(B, "stops"), h.principal(A, "asker")
    await h.person(asker, department=A)
    await h.person(here, department=A, grants=((READS_USAGE, Scope.department(A)),))
    await h.person(there, department=B, grants=((READS_USAGE, Scope.department(B)),))
    console = console_for(h)
    now = datetime.now(UTC)

    def stop(period: BudgetPeriod, until: timedelta) -> Stop:
        return Stop(
            level=BudgetLevel.DEPARTMENT,
            subject=A,
            period=period,
            since=now - timedelta(hours=1),
            until=now + until,
        )

    async with h.sessions() as session:
        for one, enforced in (
            (stop(BudgetPeriod.DAY, timedelta(hours=5)), True),
            (stop(BudgetPeriod.MONTH, timedelta(days=5)), False),
        ):
            told = Notice(
                level=one.level,
                subject=one.subject,
                period=one.period,
                at=one.since,
                to=(),
                addressing=Addressing.UNADDRESSED,
            )
            await record(
                session,
                Consequence(notice=told, stop=one),
                enforced=enforced,
                asker=Asker(principal_id=asker, department=A),
                trace_id=h.trace_id,
            )
        await session.commit()
    shown = await stops_in_force(console.request(), await asking_as(h, here))
    mine = [one for one in shown.stops if one.subject == A]
    if sorted((one.period, one.enforced) for one in mine) != [("day", True), ("month", False)]:
        raise CheckFailedError("a stop and a would-have-stopped were not both listed as they were")
    if (await stops_in_force(console.request(), await asking_as(h, there))).stops:
        raise CheckFailedError("a reader of another department was shown a stop")
