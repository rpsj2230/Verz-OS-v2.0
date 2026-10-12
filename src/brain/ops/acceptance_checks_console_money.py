"""Install acceptance check for the console's money figures: the currency they carry, and the
cost nothing could have recorded, which is served as not recorded and never as nought.

**An install with no price in its own currency records no cost**, because the recorder prices a
call from the install's price list and writes nothing where there is none; a sum over that table
is the absence of rows. The check makes that state inside its own rolled-back transaction by
setting every price the install holds to another currency, reads the two routes that serve a cost
(the Overview's week and an agent's stats) and holds both to the sentence instead of a figure, then
prices one model in the install's currency and holds both to a figure that carries the code. It
reads the install's currency and says it was not run where there is none, rather than assuming
one.

Task ids: M27.15.33
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import insert

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1330

A, _ = RESERVED_DEPARTMENTS

#: The currency every existing price is set in while the check holds the install unpriced. Any
#: code but the install's own will do; the check picks the first of these that is not.
OTHER_CURRENCIES: Final = ("ZZA", "ZZB")

#: What a cost the check makes costs, in minor units.
SPENT: Final = 250


@check(
    leaves=("M27.15.33",),
    sentence=(
        "On an install where no model is priced in its currency, the Overview's week and an "
        "agent's stats serve their cost as not recorded with the reason and no currency, and "
        "never as nought; once a model is priced in it, both serve the cost with the install's "
        "currency code and the spend that was made."
    ),
)
async def an_unrecorded_cost_is_not_nought_and_a_cost_names_its_currency(
    h: Harness,
) -> None:
    from brain.console_overview_figures_routes import OverviewFiguresView, overview_figures
    from brain.console_stats_routes import AgentStatsView, agent_stats
    from brain.locale import NO_CURRENCY_CODE, LocaleError
    from brain.locale import currency as install_currency
    from brain.models.pricing import Price
    from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
    from brain.ops.acceptance_checks_company_views import _cost_is_recorded
    from brain.ops.acceptance_operations_console import screen_grants
    from brain.ops.acceptance_workspace import _spend, installed_agent
    from brain.ops.price_store import read_prices, set_price_statement
    from brain.tables.audit import attributed_to
    from brain.tables.spend import SpendActualRow

    try:
        code = install_currency()
    except LocaleError:
        raise CheckNotRunError(
            "this install's currency does not resolve, so no cost is recorded and none is shown"
        ) from None
    if code == NO_CURRENCY_CODE:
        raise CheckNotRunError(
            "this install has no currency set, so no cost is recorded and none is shown"
        )

    await h.found_departments()
    steward = h.principal(A, "spender")
    await h.person(
        steward,
        department=A,
        grants=tuple(
            dict.fromkeys(
                (*_readers("read:budget"), *screen_grants("overview", Scope.unrestricted()))
            )
        ),
    )
    agent_id = await installed_agent(h, steward)
    app = _console(h)

    # The install unpriced: every price it holds, repointed to another currency in this transaction.
    other = next(one for one in OTHER_CURRENCIES if one != code)
    async with h.sessions() as session:
        held = await read_prices(session)
    for (provider, model), price in held.items():
        await h.execute(
            *attributed_to(
                actor_id=steward, ent_hash=(await h.reach(steward)).ent_hash(), trace_id=h.trace_id
            ),
            set_price_statement(
                provider,
                model,
                Price(
                    input_minor=price.input_minor, output_minor=price.output_minor, currency=other
                ),
                by=steward,
            ),
        )

    async def served() -> tuple[OverviewFiguresView, AgentStatsView]:
        figures = await overview_figures(_request(app), await _asking(h, steward))
        stats = await agent_stats(_request(app), agent_id, await _asking(h, steward))
        return figures, stats

    figures, stats = await served()
    if figures.cost_minor is not None or figures.currency is not None or not figures.not_recorded:
        raise CheckFailedError("the Overview served a cost with nothing priced in the currency")
    if any(one.cost_minor is not None for one in stats.periods) or not stats.unrecorded:
        raise CheckFailedError("an agent's stats served a cost with nothing priced in the currency")
    if stats.projection is not None:
        raise CheckFailedError("an agent's stats projected a cost nothing recorded")

    # The same install with one model priced in its currency, and one cost made.
    await _cost_is_recorded(h, steward)
    async with h.sessions() as session:
        await session.execute(
            insert(SpendActualRow),
            [_spend(agent_id, steward, SPENT, h.now - timedelta(hours=1), f"{h.trace_id}-m0")],
        )
        await session.commit()
    figures, stats = await served()
    if figures.currency != code or figures.cost_minor is None or figures.not_recorded:
        raise CheckFailedError("the Overview did not serve a recorded cost with the currency")
    if figures.cost_minor < SPENT:
        raise CheckFailedError("the Overview's cost did not include the spend that was made")
    if stats.currency != code or stats.unrecorded:
        raise CheckFailedError("an agent's stats did not serve a recorded cost with the currency")
    if not any(one.cost_minor == SPENT for one in stats.periods):
        raise CheckFailedError("an agent's stats did not serve the spend that was made")
