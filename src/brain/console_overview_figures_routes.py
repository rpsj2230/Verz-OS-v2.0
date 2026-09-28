"""The Overview's figure row over HTTP: how the last seven days' requests ended, and their cost.

`docs/screens.html` SCREEN 1 puts a row of figures across the top of the landing screen, and the
owner's brief for it names five: questions answered in the last seven days, refused or abstained,
active agents, connected sources, and cost where it is recorded. Two of those already have a
route that decides them for this reader. Agents are the roster's (`GET /agents`, the audience's
answer) and sources are the Connectors screen's (`GET /connectors`, `admitted_connections`), so
the page counts the rows those routes send it and this module computes neither: a second count
of either would be a second answer to who may be told an agent or a source exists, which is
`brain.operate_routes.A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE`. What no route served is how
the company's requests ended. The stats package counts that per agent, and `GET /report/usage`
counts the questions asked and not how they ended, so this is the one read that was missing.

**A figure is counted over rows the reader may read, and whose they are is said.** Requests belong
to the person who made them, so the basis is `brain.console.agent_tabs.usage_basis`, the Usage
screen's own read asked through `brain.console.agent_output.basis_over`: everybody's requests for
a reader who could open that screen and read them there, and only their own otherwise, with the
caller in the WHERE clause so nobody else's row is ever counted for them. `basis` is on the answer
because a reader shown their own figure with no label reads it as the company's. See
`A_FRONT_PAGE_FIGURE_IS_COUNTED_AT_THE_USAGE_SCREENS_BASIS`.

**Refused and abstained are one figure.** `brain.ops.telemetry.RequestStatus` records a refusal
and a request about nothing under one member, `nothing_returned`, because a status separating
them is a count of what people were refused. The figure is carried whole and nothing here could
split it.

**The count is made in the database, grouped by status, over one window.** The alternative, the
stats package's read of up to twenty thousand rows and a count in Python, is right for one agent
and wrong for the whole company: a busy week is more rows than that bound, and a figure read to a
bound would have to say `at_least` on the one number the landing screen exists to show. The window
is `brain.console.workspace.window`, the one every periodised figure asks, and the basis predicate
is in the statement, so the arithmetic in SQL has nothing left to decide. A zero is a measurement
here: `brain.ops.telemetry_store.TelemetryRecorder` writes a row for every request the lane
finishes, so a week with none answered really answered none.

**Cost is the sum of `ops.spend_actual` over the same week, made in the database, and it is
counted at the Budget screen's basis rather than the Usage screen's.** `brain.ops.usage_store`
writes what each request cost since 2026-09-28 (`brain.console.agent_profile.RUN_SPEND_IS_RECORDED`),
so the figure is served. Money spent is what the Budget and spend screen shows, and the Usage
screen shows questions and tokens, so a reader who may read everybody's usage and only their own
spend is summed their own: `brain.console.workspace.basis_for`, which is the basis the stats
package's `cost_basis` already takes for an agent's cost. The two bases are the same for every
administrator who holds both screens, and when they differ the answer says so in `cost_basis`
rather than letting `basis` describe a figure it was not applied to. The caller is in the WHERE
clause on the narrower basis, exactly as for the request counts. See
`A_FRONT_PAGE_COST_IS_SUMMED_AT_THE_BUDGET_SCREENS_BASIS`.

**Nought is served only where nought was measured.** The recorder writes a cost only for a request
every model of which has a price in the install's currency (`brain.models.pricing.cost_of`), so on
an install where no model has one nothing is ever written, and a sum over no rows would say a
company that has been asking questions all week spent nothing. So the figure is served only when
spend recording is on and at least one model has a price in the install's currency; otherwise
`cost_minor` and `currency` are null and `not_recorded` says why, in a sentence the page shows as
"Not recorded yet". Once a price exists a week with no cost rows is a measured nought. What the
sum cannot say is the cost of a request answered by a model nobody priced, which the recorder logs
and the Models screen lists; that is the Models screen's figure and not a caveat this row repeats.
See `A_COST_OVER_NO_PRICE_IS_NOT_RECORDED_AND_NEVER_NOUGHT`.

**The Overview screen's read first, and nothing is read for a reader without it**, in
`brain.console_overview_routes`' words and with its one refusal, so the two addresses of the one
landing screen refuse alike.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.agent_profile import RUN_SPEND_IS_RECORDED
from brain.console.agent_tabs import usage_basis
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import Basis, Range, basis_for, window
from brain.core.errors import Absent, Failed
from brain.locale import LocaleError
from brain.locale import currency as install_currency
from brain.models.pricing import Price
from brain.ops.price_store import read_prices
from brain.ops.telemetry import RequestStatus
from brain.routing_routes import sessions_of
from brain.tables.spend import SpendActualRow
from brain.tables.telemetry import RequestTelemetryRow

log = structlog.get_logger()

FIGURES_PATH: Final = "/console/overview/figures"

#: The registered screen whose read opens these figures. The landing screen's own.
OVERVIEW_SCREEN: Final = "overview"

#: The period the figures cover: the design's "Last 7 days".
FIGURES_RANGE: Final = Range.SEVEN_DAYS

# ------------------------------------------------------------------ written-down reasons
#: Why the figures are the reader's own unless the Usage screen is theirs to read.
A_FRONT_PAGE_FIGURE_IS_COUNTED_AT_THE_USAGE_SCREENS_BASIS: Final = (
    "A request belongs to the person who made it, and a count of everybody's requests moves when "
    "a colleague asks something. So the landing screen counts everybody's only for a reader who "
    "could open the Usage screen and read them there, and counts the reader's own otherwise, with "
    "the reader in the statement, and it says which it counted."
)

#: Why the cost is summed at the Budget screen's basis and says so apart from the counts'.
A_FRONT_PAGE_COST_IS_SUMMED_AT_THE_BUDGET_SCREENS_BASIS: Final = (
    "Money spent is the Budget and spend screen's figure, and the Usage screen shows questions and "
    "tokens. So the landing screen sums everybody's cost only for a reader who could open the "
    "Budget screen and read it there, sums the reader's own otherwise with the reader in the "
    "statement, and sends that basis as cost_basis beside the counts' basis."
)

#: Why an install with no price in its own currency is told cost is not recorded.
A_COST_OVER_NO_PRICE_IS_NOT_RECORDED_AND_NEVER_NOUGHT: Final = (
    "The recorder writes a request's cost only when every model it called has a price in the "
    "install's currency, so where no model has one nothing is ever written and a sum over no rows "
    "is nought for a company that has spent money. The figure is not recorded until a price "
    "exists, and from then on it is the sum, nought included."
)


class FigureNotRecordedView(BaseModel):
    """A figure the landing screen names that nothing on this install records, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    figure: str
    why: str


#: Why the cost figure is not served while nothing records one. A product fact that names nobody.
COST_IS_NOT_RECORDED: Final = FigureNotRecordedView(
    figure="cost",
    why=(
        "nothing on the request path writes what a request cost yet, so a figure here would be "
        "nought for every install rather than a measurement"
    ),
)

#: Why the cost figure is not served on an install where no model is priced in its currency.
COST_HAS_NO_PRICE: Final = FigureNotRecordedView(
    figure="cost",
    why=(
        "no model has a price in this install's currency yet, so no request's cost has been "
        "recorded; a model's price is set on the Models screen"
    ),
)


class OverviewFiguresView(BaseModel):
    """How this reader's share of the last seven days' requests ended, and what it cost.

    `basis` is `everyone` or `own`, and says whose requests `answered` and `nothing_returned` are
    over. `nothing_returned` is refused and abstained together and is never split. `cost_minor` is
    whole minor units of `currency`, the install's, summed over `cost_basis`; both are null while
    the cost is not recorded, and `not_recorded` then says why. No field is a total beside a
    narrowed figure, and none could be derived by subtraction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    since: datetime
    until: datetime
    basis: str
    answered: int
    nothing_returned: int
    cost_basis: str
    cost_minor: int | None
    currency: str | None
    not_recorded: list[FigureNotRecordedView]


def _not_answerable() -> Absent:
    """The one refusal, `brain.console_overview_routes`' sentence. Never a capability."""
    return Absent(f"the {OVERVIEW_SCREEN} screen is not answerable for this caller")


def request_outcomes(
    since: datetime, until: datetime, *, basis: Basis, caller_id: str
) -> Select[tuple[str, int]]:
    """How many requests ended each way inside the window, the caller's alone on `own`.

    Inclusive at both ends, which is `window`'s own rule. On the narrower basis the caller is in
    the WHERE clause, so a request somebody else made is never counted for this reader.
    """
    statement = select(RequestTelemetryRow.status, func.count()).where(
        RequestTelemetryRow.received_at >= since,
        RequestTelemetryRow.received_at <= until,
    )
    if basis is not Basis.EVERYONE:
        statement = statement.where(RequestTelemetryRow.principal == caller_id)
    return statement.group_by(RequestTelemetryRow.status)


def request_cost(
    since: datetime, until: datetime, *, basis: Basis, caller_id: str
) -> Select[tuple[int]]:
    """What the requests finished inside the window cost, the caller's alone on `own`.

    One row, nought over no rows, so the arithmetic is the database's and a busy week is never
    read into Python. The window and the basis are `request_outcomes`' own rule, on the instant a
    cost row names, which is the instant the lane finished the request.
    """
    statement = select(
        func.coalesce(func.sum(SpendActualRow.cost_minor), 0).label("cost_minor")
    ).where(SpendActualRow.at >= since, SpendActualRow.at <= until)
    if basis is not Basis.EVERYONE:
        statement = statement.where(SpendActualRow.principal_id == caller_id)
    return statement


def priced_in(prices: Mapping[tuple[str, str], Price], currency: str) -> bool:
    """Whether any model has a price a call could be costed at, which is one in `currency`.

    `brain.models.pricing.cost_of`'s rule read the other way: a price in another currency costs
    nothing, so it is no price here either.
    """
    return any(one.currency == currency for one in prices.values())


async def week_cost(
    session: AsyncSession, since: datetime, until: datetime, *, basis: Basis, caller_id: str
) -> tuple[int | None, str | None, FigureNotRecordedView | None]:
    """The window's cost and its currency, or no figure and the sentence saying why.

    Nothing is summed for an install whose cost could not have been written: see
    `A_COST_OVER_NO_PRICE_IS_NOT_RECORDED_AND_NEVER_NOUGHT`. A currency that does not resolve is
    one no price can be in, so it is that sentence too, and the log says which setting failed.
    """
    if not RUN_SPEND_IS_RECORDED:
        return None, None, COST_IS_NOT_RECORDED
    try:
        code = install_currency()
    except LocaleError as failed:
        log.warning("overview figures currency unresolved", error=str(failed))
        return None, None, COST_HAS_NO_PRICE
    if not priced_in(await read_prices(session), code):
        return None, None, COST_HAS_NO_PRICE
    ((summed,),) = (
        await session.execute(request_cost(since, until, basis=basis, caller_id=caller_id))
    ).all()
    return int(summed), code, None


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(FIGURES_PATH, response_model=OverviewFiguresView, responses=COMMON_RESPONSES)
async def overview_figures(request: Request, asked: Asked) -> OverviewFiguresView:
    """Answered, nothing returned and cost over the last seven days, each at the reader's basis."""
    if not permitted(screen(OVERVIEW_SCREEN).read, asked.reach, asked.now):
        log.info("overview figures not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    caller_id = asked.caller.principal.id
    basis = usage_basis(asked.reach, asked.now)
    cost_basis = basis_for(asked.reach, asked.now)
    since, until = window(FIGURES_RANGE, asked.now)
    async with factory() as session:
        rows = (
            await session.execute(request_outcomes(since, until, basis=basis, caller_id=caller_id))
        ).all()
        cost_minor, currency, unrecorded = await week_cost(
            session, since, until, basis=cost_basis, caller_id=caller_id
        )
    ended = {str(status): int(count) for status, count in rows}
    return OverviewFiguresView(
        range=FIGURES_RANGE.value,
        since=since,
        until=until,
        basis=basis.value,
        answered=ended.get(RequestStatus.ANSWERED.value, 0),
        nothing_returned=ended.get(RequestStatus.NOTHING_RETURNED.value, 0),
        cost_basis=cost_basis.value,
        cost_minor=cost_minor,
        currency=currency,
        not_recorded=[] if unrecorded is None else [unrecorded],
    )
