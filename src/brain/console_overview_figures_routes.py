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

**Cost is named as not recorded, never served as nought.** Nothing on the request path writes a
run's cost yet (`brain.console.agent_profile.RUN_SPEND_IS_RECORDED`), so a figure would be 0.00
for every install, and 0.00 is a claim the company spent nothing. The answer says so in
`not_recorded`, and a test fails the day that flag turns, which is the day to serve the figure.

**The Overview screen's read first, and nothing is read for a reader without it**, in
`brain.console_overview_routes`' words and with its one refusal, so the two addresses of the one
landing screen refuse alike.

Task ids: M27.2.1, M27.15.17
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.agent_profile import RUN_SPEND_IS_RECORDED
from brain.console.agent_tabs import usage_basis
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import Basis, Range, window
from brain.core.errors import Absent, Failed
from brain.ops.telemetry import RequestStatus
from brain.routing_routes import sessions_of
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


class FigureNotRecordedView(BaseModel):
    """A figure the landing screen names that nothing on this install records, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    figure: str
    why: str


#: Why the cost figure is not served. The sentence is a product fact and names nobody.
COST_IS_NOT_RECORDED: Final = FigureNotRecordedView(
    figure="cost",
    why=(
        "nothing on the request path writes what a request cost yet, so a figure here would be "
        "nought for every install rather than a measurement"
    ),
)

#: What this release cannot count, the same for every reader.
NOT_RECORDED_TODAY: Final[tuple[FigureNotRecordedView, ...]] = (
    () if RUN_SPEND_IS_RECORDED else (COST_IS_NOT_RECORDED,)
)


class OverviewFiguresView(BaseModel):
    """How this reader's share of the last seven days' requests ended.

    `basis` is `everyone` or `own`, and says whose requests `answered` and `nothing_returned` are
    over. `nothing_returned` is refused and abstained together and is never split. No field is a
    total beside a narrowed figure, and none could be derived by subtraction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    since: datetime
    until: datetime
    basis: str
    answered: int
    nothing_returned: int
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


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(FIGURES_PATH, response_model=OverviewFiguresView, responses=COMMON_RESPONSES)
async def overview_figures(request: Request, asked: Asked) -> OverviewFiguresView:
    """Answered and nothing returned over the last seven days, at the reader's basis."""
    if not permitted(screen(OVERVIEW_SCREEN).read, asked.reach, asked.now):
        log.info("overview figures not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    caller_id = asked.caller.principal.id
    basis = usage_basis(asked.reach, asked.now)
    since, until = window(FIGURES_RANGE, asked.now)
    async with factory() as session:
        rows = (
            await session.execute(request_outcomes(since, until, basis=basis, caller_id=caller_id))
        ).all()
    ended = {str(status): int(count) for status, count in rows}
    return OverviewFiguresView(
        range=FIGURES_RANGE.value,
        since=since,
        until=until,
        basis=basis.value,
        answered=ended.get(RequestStatus.ANSWERED.value, 0),
        nothing_returned=ended.get(RequestStatus.NOTHING_RETURNED.value, 0),
        not_recorded=list(NOT_RECORDED_TODAY),
    )
