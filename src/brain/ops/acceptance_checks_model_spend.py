"""Install acceptance check for what a model call costs: metered into spend, then stopped.

Two console leaves ask what no earlier check followed end to end. A model call is metered into
spend (M27.12.5): the provider's own counts and the price an administrator set become one cost
row under the request's trace. Budgets are versioned and their stops are visible (M27.7.15): a
department whose ceiling is used up has a stop recorded for the next request, listed to a reader
of its spend, and whether the install refuses on it is the `budget_enforcement` switch (off by
default). The budget versions and the stops list each have a check of their own; what none had
was a real question, answered by a model, followed into the ledger and then into the stop it
causes.

**The model is a stand-in the product's own transport reaches over a responder in the process**, as
the routing checks use one (`brain.ops.acceptance_routing`), so nothing leaves the server and no
provider's key is read. The price is one minor unit a token in the install's own currency, set
inside the check's rolled-back transaction, so the cost is exactly the tokens the request row
recorded and nothing in the assertion is a figure this check chose. Rejected: inserting the cost
row, which proves the stop machinery and not that a model call reaches the ledger.

**The stop is asserted in both states of the switch.** On an install where enforcement is off the
second question is answered and the stop is recorded as one that was not enforced; on an install
where it is on the second question is refused in the spending-limit sentence and the stop is
recorded as enforced. A check that assumed one state would fail on the other install for being
correct. The state is read from the install, not set, so the check never switches a feature.

Task ids: M27.12.5, M27.7.15
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2720

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.core.errors import Degraded
    from brain.gate.answer import Answered

A, _ = RESERVED_DEPARTMENTS

#: Restated, so a change to the Spend report's authority fails this check and does not move it.
READS_USAGE: Final = "read:usage"

#: One minor unit a token, written as a price per million tokens.
PER_TOKEN: Final = Decimal(1_000_000)

#: A daily ceiling of one minor unit, which any answered question has used up.
TINY_CEILING: Final = 1


@check(
    leaves=("M27.12.5", "M27.7.15"),
    sentence=(
        "A question answered by a priced model leaves one cost in its department equal to the "
        "tokens its request row recorded at the price set; once the department's daily ceiling is "
        "used up the next question leaves a stop, listed with whether the install enforced it to "
        "a reader of that department's spend and to nobody in another."
    ),
)
async def a_model_call_is_costed_and_a_used_up_budget_stops_the_next(h: Harness) -> None:
    from brain.locale import NO_CURRENCY_CODE, LocaleError
    from brain.locale import currency as install_currency
    from brain.models.pricing import Price
    from brain.ops.acceptance_models import STAND_IN, pinned, trace_of
    from brain.ops.acceptance_operations_console import asking_as, console_for
    from brain.ops.acceptance_routing import ANSWERS, answered, asking, standing_by, step
    from brain.ops.budget_store import append
    from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
    from brain.ops.features import BUDGET_ENFORCEMENT, is_on
    from brain.ops.price_store import set_price_statement
    from brain.spend_detail_routes import stops_in_force

    try:
        code = install_currency()
    except LocaleError:
        raise CheckNotRunError(
            "this install's currency does not resolve, so no cost is recorded to follow"
        ) from None
    if code == NO_CURRENCY_CODE:
        raise CheckNotRunError("this install has no currency set, so no cost is recorded to follow")

    s = await standing_by(h)
    budgeter, spend_reader = h.principal(A, "budgeter"), h.principal(A, "spend")
    elsewhere = h.principal(RESERVED_DEPARTMENTS[1], "spend")
    await h.person(budgeter, department=A)
    await h.person(spend_reader, department=A, grants=((READS_USAGE, Scope.department(A)),))
    await h.person(
        elsewhere,
        department=RESERVED_DEPARTMENTS[1],
        grants=((READS_USAGE, Scope.department(RESERVED_DEPARTMENTS[1])),),
    )
    await pinned(h, (step(ANSWERS),))
    await h.execute(
        *h.attributed(budgeter),
        set_price_statement(
            STAND_IN,
            ANSWERS,
            Price(input_minor=PER_TOKEN, output_minor=PER_TOKEN, currency=code),
            by=budgeter,
        ),
    )

    # 1. A question answered by the priced model leaves its cost, equal to the tokens it used.
    first = await asking(h, s.app, s.reader, s.paired.question, 1)
    if not answered(first):
        raise CheckFailedError("a question the stand-in model could answer was not answered")
    request = (
        await h.execute(
            text(
                "SELECT COALESCE(tokens_in, 0) + COALESCE(tokens_out, 0) FROM obs.request_telemetry"
                " WHERE trace_id = :trace"
            ).bindparams(trace=trace_of(h, 1))
        )
    ).all()
    costs = (
        await h.execute(
            text(
                "SELECT cost_minor, department, principal_id FROM ops.spend_actual"
                " WHERE trace_id = :trace"
            ).bindparams(trace=trace_of(h, 1))
        )
    ).all()
    if len(request) != 1 or request[0][0] <= 0:
        raise CheckFailedError("the answered question left no tokens on its request row")
    if len(costs) != 1 or (costs[0][1], costs[0][2]) != (A, s.reader):
        raise CheckFailedError("an answered question did not leave one cost under its department")
    if costs[0][0] != request[0][0]:
        raise CheckFailedError("the cost recorded was not the tokens used at the price set")

    # 2. A ceiling that cost has used up: the next question leaves a stop, enforced or not.
    reach = await h.reach(budgeter)
    async with h.sessions() as session:
        enforcing = await is_on(session, BUDGET_ENFORCEMENT)
        await append(
            session,
            BudgetRow(
                level=BudgetLevel.DEPARTMENT,
                subject=A,
                period=BudgetPeriod.DAY,
                ceiling_minor=TINY_CEILING,
                version=1,
                author=budgeter,
                effective_from=h.now,
                reason="An install check follows a used-up ceiling",
            ),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        )
        await session.commit()
    # Asked at the wall clock: the cost was recorded when the first question finished, after the
    # check began, and a budget is judged over what was spent up to the question's instant.
    second = await _asked_at_the_wall_clock(h, s.app, s.reader, s.paired.question, 2)
    if enforcing == answered(second):
        raise CheckFailedError(
            "the second question was answered with enforcement on, or refused with it off"
        )
    console = console_for(h)
    shown = await stops_in_force(console.request(), await asking_as(h, spend_reader))
    mine = [one for one in shown.stops if one.subject == A and one.period == "day"]
    if [one.enforced for one in mine] != [enforcing]:
        raise CheckFailedError(
            "the used-up ceiling's stop was not listed as the install enforces it"
        )
    if (await stops_in_force(console.request(), await asking_as(h, elsewhere))).stops:
        raise CheckFailedError("a reader of another department was shown a stop")


async def _asked_at_the_wall_clock(
    h: Harness, app: FastAPI, reader: str, question: str, n: int
) -> Answered | Degraded:
    """`acceptance_routing.asking`, at the instant now and not the check's start."""
    from brain.core.errors import Degraded
    from brain.ops.acceptance_models import asked

    try:
        return await asked(h, app, reader, question, n, at=datetime.now(UTC))
    except Degraded as refused:
        return refused
