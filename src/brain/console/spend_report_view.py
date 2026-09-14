"""The spend report read from a materialised view, at one reader's reach, with its age on it.

`brain.console.spend_view.spend_report` groups every accounting row a reader may see, and it is
the heaviest screen in the console: one row per completed run over the whole retained history,
asked for in five dimensions. `ops.spend_daily` (migration `0035`) does that grouping once per
refresh, and this module turns its rows into the same `Report` the unmaterialised screen
produces, through the same predicate.

**The view is keyed by the dimension the reader's scope is applied on, and that is the whole
security argument.** A materialised view carries no row-level security, so whatever it holds,
the application reads all of it. What makes that safe is that `may_read_spend` admits a row by
its department and by nothing else, and `department` is a group key of every row in the view.
Filtering summed rows by department therefore drops exactly the runs that filtering the runs
would have dropped, and the figures that survive are the ones `spend_report` would have printed.
See `THE_FILTER_COMMUTES_WITH_THE_SUM_ONLY_BECAUSE_ITS_INPUT_IS_A_GROUP_KEY`.

**The filter is `may_read_spend`, imported, and there is no SQL copy of it.** A predicate in the
view's query would be a second implementation of a scope match, and a scope is not a list of
departments: it can be unrestricted and it can expire at an instant. The view is read whole and
narrowed here. It is small enough to read whole because it holds one row per day, department,
principal kind, traffic class and key, which is the reason it exists.

**The view is only as narrow as its table, and that is checked rather than assumed.**
`ops.spend_actual` admits the application role to every row, so a view over it that the same
role reads is no wider. `view_gaps` takes the table's read policies as the server reports them
and names any that are narrower, because the day that policy narrows is the day this view
becomes a way round it. See
`A_VIEW_IS_NO_WIDER_THAN_ITS_TABLE_ONLY_WHILE_ITS_TABLE_ADMITS_EVERY_ROW`.

**The age of the figures is graded on `brain.gate.provenance`'s scale, because it is the same
question.** The refresh instant is the read time of every figure the view holds, exactly as a
citation's `fetched_at` is the read time of the value it cites, and what a reader needs is the
same answer in both places: how much weight a figure's age allows. So a report carries a
`StatedFreshness` computed by `state_freshness` against `REPORT_HORIZON`, and an answer and a
report say LIVE, AGEING, STALE or UNSTATED on one scale with one set of words. A never-refreshed
view, a naive instant and a refresh recorded after the reading instant are all UNSTATED, which is
provenance's decision about each rather than a second one taken here. See
`A_REPORTS_AGE_IS_GRADED_ON_THE_SCALE_AN_ANSWERS_IS`.

**Staleness is a field on the report, never a caption.** `MaterialisedReport` carries the instant
the figures are as of and the graded state, on the object a renderer is handed, for the reason
`spend_view.Report.machine_included` is on its object. A view nobody has refreshed has no report
at all rather than an empty one: an empty report says the company spent nothing, and an unbuilt
one says nothing about spend. See `A_REPORT_NOBODY_HAS_BUILT_IS_NOT_A_REPORT_OF_NOTHING`.

**The horizon is derived from the refresh schedule, and the schedule from the view's grain.** The
view sums by UTC day, and a day is also the finest budget period anything is paced against, so a
refresh per day is the most staleness a daily figure can carry and still describe the day before.
Figures younger than one refresh interval are LIVE. The STALE threshold is not a second number:
it is `brain.ops.controls.MISSED_RUN_GRACE` intervals, which is when every scheduled control's
lateness becomes worth saying, so a report goes STALE exactly when its refresh control would be
reported late. See `THE_REFRESH_IS_DAILY_BECAUSE_THE_VIEW_IS`.

What was rejected.

*A freshness type of this module's own*, holding the refresh instant with an overdue flag beside
it. It was written first, and it was a second scale for the one question: a report described as
overdue while an answer citing the same spend is described as ageing, and a reader cannot tell
whether the two words mean the same thing. `tests/invariants/test_single_implementation.py`
pins `Freshness` to `gate/provenance.py` for exactly that reason and caught it. Renaming the class
would have hidden it from that test without making the scales one.

*A view keyed without the department*, per model or per agent across the company. It is the
smaller view and it is the leak: every reader would be handed the company's figure for a key,
and the subtraction from what their own departments spent is the hidden spend.

*A view per reader, or per scope.* It is exact and it turns granting somebody a department into
a DDL change, and a view for a scope nobody currently holds is a view of figures nobody may read.

*A `security_invoker` plain view instead of a materialised one.* It applies the table's
policies to the reader, which is what `er.resolved_alias` does and is right there; it also
regroups every run on every read, which is the cost this leaf exists to remove.

*Filtering in SQL by the departments the reader's scope names.* `0009` does reduce a reach to
`app.departments` for the document plane, as a second wall behind a query that already carries
the reach. Here it would be the only wall, and it would disagree with `may_read_spend` about
every scope that is not a plain list.

Task ids: M36.1.3.1, M36.1.3.2
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from brain.console.spend_view import Report, may_read_spend, report_from_totals
from brain.core.entitlement import EntitlementSet
from brain.core.principal import PrincipalKind
from brain.gate.context import TrafficClass
from brain.gate.provenance import Freshness, StalenessHorizon, StatedFreshness, state_freshness
from brain.ops.controls import MISSED_RUN_GRACE
from brain.ops.limits import is_automated
from brain.ops.spend import Dimension


class SpendReportViewError(Exception):
    """Raised when a materialised report would state something its rows cannot support."""


# ------------------------------------------------------------------ written-down reasons
#: Why reading a materialised view whole and filtering it in Python leaks nothing.
THE_FILTER_COMMUTES_WITH_THE_SUM_ONLY_BECAUSE_ITS_INPUT_IS_A_GROUP_KEY: Final = (
    "may_read_spend admits an accounting row by its department and by nothing else, and the "
    "view groups by department before anything else. So dropping the summed rows of the "
    "departments a reader may not see removes exactly the runs that dropping those runs first "
    "would have removed, and every figure left is one spend_report would have printed. Take the "
    "department out of the grouping, or admit a row by anything the view does not group on, "
    "and the summed rows mix what the reader may see with what they may not, and no filter "
    "applied afterwards can separate them again."
)

#: Why the table's read policy is checked by this module.
A_VIEW_IS_NO_WIDER_THAN_ITS_TABLE_ONLY_WHILE_ITS_TABLE_ADMITS_EVERY_ROW: Final = (
    "PostgreSQL applies no row-level security when a materialised view is read, so the view "
    "shows its reader every row its owner could see when it was built. That is harmless while "
    "the reading role already sees every row of the table, which is what ops.spend_actual's "
    "USING (true) says. A narrower policy on the table would leave the view exactly as wide as "
    "before and turn it into the way round the new policy, with nothing on either object "
    "saying so."
)

#: Why a report's age uses the provenance scale rather than one of its own.
A_REPORTS_AGE_IS_GRADED_ON_THE_SCALE_AN_ANSWERS_IS: Final = (
    "The refresh instant is the read time of every figure a materialised report shows, which is "
    "what a citation's fetched_at is for the value it cites, and a reader asks the same thing of "
    "both: how much weight this figure's age allows. Two scales for that would describe the same "
    "spend as ageing in an answer and overdue on a screen, and nobody reading either could tell "
    "whether the words agree. So the report is graded by brain.gate.provenance.state_freshness "
    "against a horizon derived from its refresh schedule, and says what an answer would say."
)

#: Why the age of the figures rides on the report.
STALENESS_IS_A_FIGURE_ON_THE_REPORT_AND_NEVER_A_CAPTION: Final = (
    "A materialised report is right as of an instant and wrong in an unknown direction "
    "afterwards, and a reader deciding anything from it needs that instant beside the figure. "
    "A caption is the first thing a renderer drops when a screen is redesigned, so the instant "
    "and the graded freshness at the reader's own clock are fields on the object the renderer "
    "is handed."
)

#: Why a never-refreshed view produces no report rather than an empty one.
A_REPORT_NOBODY_HAS_BUILT_IS_NOT_A_REPORT_OF_NOTHING: Final = (
    "A view created WITH NO DATA and never refreshed holds nothing, and a report built over "
    "nothing says the company spent nothing, which is a figure and a false one. So until a "
    "refresh has been recorded there is no report at all, its freshness is unstated, and the "
    "renderer has to say the report has not been built yet rather than print a zero."
)

#: Why the refresh cadence is a day.
THE_REFRESH_IS_DAILY_BECAUSE_THE_VIEW_IS: Final = (
    "The view sums by UTC day and the finest budget period anything is paced against is a day, "
    "so one refresh per day is the most staleness a daily figure can carry while still describing "
    "the day before it. Refreshing more often recomputes the current partial day, which no screen "
    "reading this view needs: whether today's budget is running out is asked of live rows by the "
    "budget stop board. Refreshing less often leaves a day that has closed missing from a report "
    "of days."
)


# ---------------------------------------------------------------------------- the schedule
#: The view's grain. `0035` groups on `(at AT TIME ZONE 'UTC')::date`, which is one day.
VIEW_GRAIN: Final = timedelta(days=1)

#: How often the view is rebuilt. See `THE_REFRESH_IS_DAILY_BECAUSE_THE_VIEW_IS`.
REFRESH_EVERY: Final = VIEW_GRAIN

#: When the figures become STALE: the controls registry's own grace over the refresh interval.
STALE_AFTER: Final = REFRESH_EVERY * MISSED_RUN_GRACE

#: The report's horizon on the provenance scale. LIVE within one refresh, STALE past the grace.
REPORT_HORIZON: Final = StalenessHorizon(live_for=REFRESH_EVERY, stale_after=STALE_AFTER)


# ------------------------------------------------------------------------------ the rows
@dataclass(frozen=True)
class SpendDay:
    """One row of `ops.spend_daily`: what one key cost on one day in one department.

    `principal_kind` and `traffic` are carried rather than a machine flag, so whether the row is
    automated traffic is `brain.ops.limits.is_automated`'s answer and has no second copy.
    """

    day: date
    department: str
    principal_kind: PrincipalKind
    traffic: TrafficClass
    dimension: Dimension
    key: str
    cost_minor: int

    def __post_init__(self) -> None:
        if not self.department.strip() or not self.key.strip():
            msg = "a summed row with no department or no key cannot be shown to anybody at a reach"
            raise SpendReportViewError(msg)
        if self.cost_minor < 0:
            msg = "a day cannot have cost less than nothing"
            raise SpendReportViewError(msg)

    @property
    def machine(self) -> bool:
        """Whether nobody was asking. The lookup `Actual.machine` makes, over the same inputs."""
        return is_automated(self.principal_kind, self.traffic)


@dataclass(frozen=True)
class MaterialisedReport:
    """A spend report read from the view, the instant it is as of, and how fresh that is.

    `report` is None exactly when `as_of` is, and a report with no instant cannot be graded
    anything but unstated. The constructor holds all three together. See
    `A_REPORT_NOBODY_HAS_BUILT_IS_NOT_A_REPORT_OF_NOTHING` and
    `STALENESS_IS_A_FIGURE_ON_THE_REPORT_AND_NEVER_A_CAPTION`.
    """

    report: Report | None
    #: What the figures are as of. None when the view has never been built.
    as_of: datetime | None
    #: The provenance scale's verdict on `as_of`, at the reader's instant.
    freshness: StatedFreshness

    def __post_init__(self) -> None:
        if (self.report is None) != (self.as_of is None):
            msg = (
                "a report and the instant it is as of are present together or not at all. "
                f"{A_REPORT_NOBODY_HAS_BUILT_IS_NOT_A_REPORT_OF_NOTHING}"
            )
            raise SpendReportViewError(msg)
        if self.as_of is None and self.freshness.state is not Freshness.UNSTATED:
            msg = (
                f"a report never built is graded {self.freshness.state.value}; with no instant "
                "the only honest grade is unstated"
            )
            raise SpendReportViewError(msg)


def freshness_of(refreshed_at: datetime | None, now: datetime) -> StatedFreshness:
    """The provenance verdict on a refresh instant, at the reader's instant.

    `state_freshness` over the instant in ISO 8601 and `REPORT_HORIZON`, so every rule about an
    undatable, naive or future read time is provenance's. No instant is an empty read time,
    which that module turns into UNSTATED. See `A_REPORTS_AGE_IS_GRADED_ON_THE_SCALE_AN_ANSWERS_IS`.
    """
    fetched_at = "" if refreshed_at is None else refreshed_at.isoformat()
    return state_freshness(fetched_at, horizon=REPORT_HORIZON, now=now)


def spend_report_from_view(
    days: Sequence[SpendDay],
    refreshed_at: datetime | None,
    entitlement: EntitlementSet,
    dimension: Dimension,
    *,
    now: datetime,
    since: date | None = None,
    until: date | None = None,
    include_machine: bool = False,
) -> MaterialisedReport:
    """Spend in one dimension, from the materialised view, over what this reader may see.

    The same report `spend_view.spend_report` builds from runs, filtered by the same
    `may_read_spend` and ordered and totalled by the same `report_from_totals`. See
    `THE_FILTER_COMMUTES_WITH_THE_SUM_ONLY_BECAUSE_ITS_INPUT_IS_A_GROUP_KEY`.

    `since` is inclusive and `until` exclusive, both in UTC days, which is the view's grain. A
    window that ends before it starts is refused rather than answered with nothing, because an
    empty report reads as no spend.
    """
    if since is not None and until is not None and until <= since:
        msg = f"a window from {since} until {until} holds no day"
        raise SpendReportViewError(msg)
    freshness = freshness_of(refreshed_at, now)
    if refreshed_at is None:
        return MaterialisedReport(report=None, as_of=None, freshness=freshness)

    totals: dict[str, int] = {}
    for one in days:
        if one.dimension is not dimension:
            continue
        if since is not None and one.day < since:
            continue
        if until is not None and one.day >= until:
            continue
        if one.machine and not include_machine:
            continue
        if not may_read_spend(one.department, entitlement, now=now):
            continue
        totals[one.key] = totals.get(one.key, 0) + one.cost_minor
    return MaterialisedReport(
        report=report_from_totals(dimension, totals, include_machine=include_machine),
        as_of=refreshed_at,
        freshness=freshness,
    )


#: What the application role's read policy on the view's table has to be.
ADMITS_EVERY_ROW: Final = "true"


def view_gaps(read_policies: Sequence[str | None]) -> tuple[str, ...]:
    """Every way the view's table has stopped admitting the role that reads the view to every row.

    Takes the `qual` of each SELECT or ALL policy on `ops.spend_actual` for `brain_app`, as
    `pg_policies` reports it. Two findings: no read policy at all, which is a table the role
    cannot read beside a view it can, and a policy whose expression is anything but `true`. See
    `A_VIEW_IS_NO_WIDER_THAN_ITS_TABLE_ONLY_WHILE_ITS_TABLE_ADMITS_EVERY_ROW`.

    A parameter rather than a query, so the check can be shown a narrow policy without a server
    that has one, and so it is not the one module here that owns a connection.
    """
    if not read_policies:
        return (
            "ops.spend_actual has no read policy for brain_app while ops.spend_daily is granted "
            "to it, so the view shows figures from rows the role cannot read. "
            f"{A_VIEW_IS_NO_WIDER_THAN_ITS_TABLE_ONLY_WHILE_ITS_TABLE_ADMITS_EVERY_ROW}",
        )
    return tuple(
        f"ops.spend_actual is read under {qual!r}, which is narrower than every row, and "
        "ops.spend_daily is not. "
        f"{A_VIEW_IS_NO_WIDER_THAN_ITS_TABLE_ONLY_WHILE_ITS_TABLE_ADMITS_EVERY_ROW}"
        for qual in read_policies
        if qual != ADMITS_EVERY_ROW
    )
