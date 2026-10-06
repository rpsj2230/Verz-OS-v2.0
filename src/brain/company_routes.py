"""The Super Admin's view of the whole company over HTTP: everything in it, all its activity, and
what it spent.

`brain.console.global_surfaces` decided all three and said in its own docstring that nothing called
any of them: `estate` narrows the agents, skills, knowledge and connectors a reader may know exist
by department and by person, `company_activity` narrows the audit ledger by the same two filters,
and `company_consumption` totals the company's spend or withholds it. This module is the read they
sit behind, and it decides none of it. Each route loads, hands the rows and the caller's reach to
the function that owns the decision, and copies the answer onto a response. See
`THE_SURFACE_DECIDES_AND_THIS_ROUTE_COPIES`.

**Every load is a statement another screen already reads, reached for rather than written again.**
The agents are `brain.skill_routes.bounded_agents` through `brain.agent_routes.record_of`, the
skills are `brain.ops.skill_store.library_of`, the knowledge is `brain.estate_routes.
retrievable_items`, which reads past the corpus policy for the reason that module gives, the
connectors are `brain.ops.connector_store.every_live`, the people are `brain.directory_routes.
live_people` and the departments its `live_department_names`, and the ledger is read in chunks by
`brain.audit_routes.read_page`. The one statement written here is `spend_between`, because every
spend read before it was one agent's or one person's and the company figure is everybody's.

**Each screen opens on its own read and is refused with the one 404 when it does not.** Activity
is the Audit screen's read and consumption the Budget screen's, asked through `brain.console.
reads.permitted` before anything is loaded, so a caller with no grant is answered identically on
an install with a database and one without. The estate has no screen of its own: it is four
listings behind four screens' grants, which is `global_surfaces.
EACH_KIND_IS_ITS_OWN_DISCLOSURE_AND_ITS_OWN_SCREEN`, so it opens for a reader who may open any of
the four and refuses one who may open none. A kind they hold nothing for contributes no rows, and
that absence is the estate's own.

**A filter list offers nothing the reader has not already been shown.** The departments the estate
offers are the departments of the rows it would show unfiltered, passed through `brain.console.
govern_surfaces.departments_offered`, which is the console's rule for a department dropdown; the
people are the owners of those same rows. Activity offers the directory's departments through the
same function, as the Departments page does, and the actors on the rows it has just shown, as the
Audit screen does. See `A_FILTER_OFFERS_ONLY_WHAT_THE_ROWS_ALREADY_SAID`.

**A department lens over activity is that department's people, and only the ones this reader may
be named.** An audit entry carries no department, so `company_activity` takes the members and the
caller owes them. They are the directory's people whose department is the one named, as
`brain.console.organisation` places a member, narrowed by `organisation.nameable`, the People
screen's own read. Without that narrowing, asking for a department and getting one colleague's
entries back would say which department that colleague sits in to a reader the People screen
would not have told. A department the reader may name nobody in is therefore the empty page a
department with nobody in it gives. See `A_DEPARTMENT_IS_ITS_PEOPLE_AS_THIS_READER_MAY_NAME_THEM`.

**No count, no total of what was withheld, and no flag that is one.** The estate's loads are
bounded and say nothing about having come back full: over a load nobody narrowed, a full load is a
fact about rows the reader may not see. Consumption says its load was incomplete only when the
figure is shown, because a reader shown the company total has been shown every row the flag is
about, and a reader shown nothing must not learn that the company ran more than a load's worth of
requests. See `A_LOAD_BOUND_IS_SAID_ONLY_BESIDE_THE_FIGURE_IT_BOUNDS`.

**What is not here, and why.** The leaf names a company budget beside the consumption, and nothing
in the product writes a company ceiling: `brain.ops.budgets.company_budget` builds one,
`brain.ops.budget_store` would keep it, and no route, wizard step or job ever appends one, so a
read here would answer None on every install. The page shows what was spent and says no ceiling
is set rather than inventing where one would come from.

Task ids: M33.1.1.1, M33.1.1.2, M33.1.1.3
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import actual_of, record_of
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.audit.ledger import IDENTIFIER, AuditEntry
from brain.audit.view import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    AuditFilter,
    AuditPage,
    AuditRow,
    AuditView,
    position_of,
)
from brain.audit_routes import (
    AUDIT_SCREEN,
    AuditRowView,
    LedgerWindows,
    Order,
    actors_on,
    ledger_of,
    people_on,
    read_page,
    row_view,
    said_by,
)
from brain.console.global_surfaces import (
    ESTATE_SCREEN,
    EstateKind,
    EstateRow,
    activity_filter,
    company_activity,
    company_consumption,
    estate,
    visible_estate,
)
from brain.console.govern_surfaces import departments_offered
from brain.console.organisation import nameable
from brain.console.reads import permitted
from brain.console.screens import Lens, screen
from brain.console.workspace import SPEND_OF_OTHERS_SCREEN
from brain.core.department import SLUG_PATTERN
from brain.core.errors import Absent, Failed
from brain.directory_routes import (
    MAX_DEPARTMENTS,
    MAX_PEOPLE,
    live_department_names,
    live_people,
    member_of,
)
from brain.estate_routes import MAX_ITEMS_CONSIDERED, retrievable_items
from brain.listing import MAX_SEARCH_CHARS, says_every_word, search_words
from brain.ops.connector_store import every_live
from brain.ops.skill_store import MAX_LIBRARY, library_of
from brain.ops.spend import Actual
from brain.people_names import names_for
from brain.report_routes import money_and_clock
from brain.routing_routes import sessions_of
from brain.skill_routes import MAX_AGENTS_CONSIDERED, bounded_agents
from brain.tables.audit import AuditEntryRow
from brain.tables.spend import SpendActualRow

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why nothing on these responses is computed here.
THE_SURFACE_DECIDES_AND_THIS_ROUTE_COPIES: Final = (
    "brain.console.global_surfaces decides which rows of the estate a reader may know exist, "
    "which entries of the ledger a department or a person narrows to, and whether the company's "
    "spend may be shown at all. A route that filtered a row, dropped an entry or summed a figure "
    "itself would be a second answer to one of those questions, and the second answer is the one "
    "that drifts. So these routes load, hand the rows and the reach over, and copy what comes "
    "back."
)

#: Why a filter dropdown offers what it offers.
A_FILTER_OFFERS_ONLY_WHAT_THE_ROWS_ALREADY_SAID: Final = (
    "A dropdown is a listing. Departments read from the department table would name every "
    "department in the company to a reader whose rows were carefully narrowed, so the estate "
    "offers the departments of the rows it would show unfiltered and the owners of those rows, "
    "and activity offers the actors on the rows it has just shown. Each department list passes "
    "through departments_offered, the console's one rule about which department names a reader "
    "may be offered."
)

#: Why the members handed to company_activity are narrowed to the people this reader may name.
A_DEPARTMENT_IS_ITS_PEOPLE_AS_THIS_READER_MAY_NAME_THEM: Final = (
    "An audit entry carries no department, so a department lens over activity is the "
    "department's people, read off the directory. Handed every person in the department, a "
    "reader who may read a colleague's entries but not see where they sit would learn their "
    "department by asking for it and getting their entries back. So the members are narrowed "
    "by organisation.nameable, the People screen's own read, and a department the reader may "
    "name nobody in answers exactly as a department with nobody in it."
)

#: Why the consumption's load flag is withheld with the figure.
A_LOAD_BOUND_IS_SAID_ONLY_BESIDE_THE_FIGURE_IT_BOUNDS: Final = (
    "The company's spend is read up to a bound, and a total over a load that came back full is "
    "short, which the reader must be told. But the flag is a fact about everybody's runs: told "
    "to a reader whose figure is withheld, it says the company ran more than a load's worth of "
    "requests in the window, which is a measure of everybody else's activity arriving as a "
    "boolean. So it is false wherever the figure is withheld."
)

# ----------------------------------------------------------------------- the bounds

#: The most accounting rows one consumption request reads. A resource bound, said beside the
#: figure when it binds; see `A_LOAD_BOUND_IS_SAID_ONLY_BESIDE_THE_FIGURE_IT_BOUNDS`.
MAX_SPEND_ROWS: Final = 50_000

#: The longest window, in days, a consumption request may ask about.
MAX_CONSUMPTION_DAYS: Final = 366

#: The window the screen opens on: a month, the period a company budget is written over.
DEFAULT_CONSUMPTION_DAYS: Final = 30

#: The estate's two filters, as the query parameters spell them.
DEPARTMENT_PARAMETER: Final = "department"
PERSON_PARAMETER: Final = "person"

#: Where each read is served, relative to the API prefix.
ESTATE_PATH: Final = "/company/estate"
ACTIVITY_PATH: Final = "/company/activity"
CONSUMPTION_PATH: Final = "/company/consumption"


# ----------------------------------------------------------------------- the shapes


class EstateRowView(BaseModel):
    """One thing in the install: its kind, its identifier and the words a person knows it by.

    No department and no owner, for `brain.console.govern_estate.
    A_VISIBILITY_PREDICATE_NAMES_A_DEPARTMENT_AND_AN_OWNER`'s reason: the two together are a
    predicate with a name in front of it. A knowledge row's label is its reference and never its
    title, because the Library screen is the existence plane and a title is content.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EstateKind
    item_id: str
    label: str


class EstateView(BaseModel):
    """Everything this reader may know exists, narrowed as asked, and what the filters offer.

    `kinds` is the closed vocabulary, identical in every install, so offering all four says
    nothing about which ones this reader holds. There is no total and no field one could go in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[EstateRowView]
    kinds: list[EstateKind]
    #: Departments of the rows this reader may see, as `departments_offered` admits them.
    departments: list[str]
    #: The owners of the rows this reader may see, by principal id, sorted.
    people: list[str]
    #: Display names of the people above, by principal id.
    names: dict[str, str] = Field(default_factory=dict)


class CompanyActivityPage(BaseModel):
    """One page of all activity this reader may see, narrowed as asked, and where to continue.

    `brain.audit_routes.AuditLedgerPage`'s argument for having no total field applies here word
    for word, so there is none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AuditRowView]
    next_cursor: str | None
    order: Order
    #: The directory's departments, as `departments_offered` admits them to this reader.
    departments: list[str]
    #: The actors on the rows above, first appearance first, and no others.
    actors: list[str]
    #: Display names of the people on the rows above, by principal id.
    people: dict[str, str] = Field(default_factory=dict)


class DepartmentSpendView(BaseModel):
    """One department's share of the company's spend, in minor units of the install's currency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    spend_minor: int


class ConsumptionView(BaseModel):
    """What the company spent over one window, or that this reader is not shown it.

    `withheld` true carries no figure and no line, for `global_surfaces.
    A_COMPANY_TOTAL_ASSEMBLED_FROM_ONE_READERS_ROWS_IS_CONFIDENTLY_WRONG`. `incomplete` is false
    wherever the figure is withheld; see `A_LOAD_BOUND_IS_SAID_ONLY_BESIDE_THE_FIGURE_IT_BOUNDS`.
    `ceiling_set` is always false today, and the module docstring says why.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str
    since: datetime
    until: datetime
    withheld: bool
    spend_minor: int | None
    by_department: list[DepartmentSpendView]
    incomplete: bool
    ceiling_set: bool = False


# -------------------------------------------------------------------- the statements


def spend_between(since: datetime, until: datetime, limit: int) -> Select[tuple[SpendActualRow]]:
    """Every completed run's cost in the window, newest first, bounded.

    `brain.agent_routes.spend_for` and `brain.mine_routes.runs_by` are this statement narrowed to
    one agent and one person; the company's figure is everybody's, so it has neither clause.
    `company_consumption` applies the window again over what arrives, so this window decides how
    much is read and never what is counted. Newest first, so a load that hits its bound loses the
    oldest end of the window, which is the end a person reading this month's spend minds least.
    """
    return (
        select(SpendActualRow)
        .where(SpendActualRow.at >= since, SpendActualRow.at <= until)
        .order_by(SpendActualRow.at.desc())
        .limit(limit)
    )


# --------------------------------------------------------------------- rows to estate


def placed_at(department: str | None, owner_id: str) -> dict[str, str]:
    """The row an estate item sits in: its department when it has one, and its owner.

    No department field at all when there is none, rather than an empty one, because
    `brain.core.scope.Clause.matches` refuses a row that lacks a field a clause tests: a
    department-scoped grant then admits no unplaced item, and only a grant over everything does.
    """
    where = {"owner_id": owner_id}
    if department:
        where["department"] = department
    return where


async def estate_rows(session: AsyncSession) -> tuple[list[EstateRow], dict[tuple[str, str], str]]:
    """Every agent, skill, knowledge item and live connector, placed, with each one's label.

    Archived agents are left out, because an archived agent no longer runs and the estate is
    what the install holds today. Every version of a skill is a row, because each version is a
    separate thing an agent may pin. Rows that do not construct are absent for everybody, which
    is `record_of`'s rule.
    """
    rows: list[EstateRow] = []
    labels: dict[tuple[str, str], str] = {}

    def add(kind: EstateKind, item_id: str, label: str, where: dict[str, str]) -> None:
        rows.append(EstateRow(kind=kind, item_id=item_id, where=where))
        labels[(kind.value, item_id)] = label

    agents = (await session.execute(bounded_agents(MAX_AGENTS_CONSIDERED))).scalars().all()
    for agent_row in agents:
        record = record_of(agent_row)
        if record is None or record.archived_at is not None:
            continue
        audience = record.audience
        add(
            EstateKind.AGENT,
            record.agent_id,
            record.display_name,
            placed_at(audience.department, audience.owner_id),
        )
    for skill_row, _review in (await session.execute(library_of(MAX_LIBRARY))).all():
        add(
            EstateKind.SKILL,
            skill_row.digest,
            f"{skill_row.name} {skill_row.version}",
            placed_at(None, skill_row.submitted_by),
        )
    for item_id, owner_id, _level, department, _kind in (
        await session.execute(retrievable_items(MAX_ITEMS_CONSIDERED))
    ).all():
        add(EstateKind.KNOWLEDGE, item_id, item_id, placed_at(department, owner_id))
    for connector, _settings, _digest, connected_by, _at, _agreed in (
        await session.execute(every_live())
    ).all():
        add(EstateKind.CONNECTOR, connector, connector, placed_at(None, connected_by))
    return rows, labels


def offered_people(rows: Sequence[EstateRow]) -> list[str]:
    """The owners of these rows, sorted, each once."""
    return sorted({one.where["owner_id"] for one in rows if one.where.get("owner_id")})


def offered_departments(rows: Sequence[EstateRow]) -> list[str]:
    """The departments these rows sit in, sorted, each once. Handed to `departments_offered`."""
    return sorted({one.where["department"] for one in rows if one.where.get("department")})


# ------------------------------------------------------------------ the activity view


class CompanyActivityView:
    """`AuditView.page` asked through `company_activity`, for `brain.audit_routes.read_page`.

    `read_page` asks its view a page after every chunk it loads, and this is that view with the
    lens applied by the function that owns it, so the loop that reads the ledger is the Audit
    screen's and the narrowing is the company surface's. The direction and the search are handed
    through to `company_activity` unchanged.
    """

    def __init__(self, view: AuditView, lens: Lens, members: Sequence[str] | None) -> None:
        self._view = view
        self._lens = lens
        self._members = members

    def page(
        self,
        criteria: AuditFilter | None = None,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        newest_first: bool = False,
        shows: Callable[[AuditRow], bool] | None = None,
    ) -> AuditPage:
        return company_activity(
            self._view,
            lens=self._lens,
            members=self._members,
            criteria=criteria,
            limit=limit,
            cursor=cursor,
            newest_first=newest_first,
            shows=shows,
        )


class NothingLogged:
    """A ledger with no entries, for a lens that narrows to nobody.

    `company_activity` still asks the view its page question in that case, so a malformed limit
    or cursor is refused alike whichever department was named. Reading the real ledger to find
    nothing would be work whose only output is a latency.
    """

    async def window(
        self,
        criteria: AuditFilter,
        *,
        subject: str | None = None,
        position: tuple[datetime, str] | None,
        newest_first: bool,
        limit: int,
    ) -> Sequence[AuditEntryRow]:
        return ()


async def members_of(request: Request, asked: Asking, department: str) -> tuple[str, ...] | None:
    """The people in `department` this reader may be named, or None when no department is asked.

    See `A_DEPARTMENT_IS_ITS_PEOPLE_AS_THIS_READER_MAY_NAME_THEM`. The directory places a person
    by their principal row's department, which is `brain.console.organisation.placed`; a team
    membership in another department does not move them.
    """
    if not department:
        return None
    factory = _require_sessions(request)
    async with factory() as session:
        rows = (await session.execute(live_people(MAX_PEOPLE))).all()
    people = [member_of(row) for row in rows]
    in_department = [one for one in people if one.department == department]
    return tuple(one.principal_id for one in nameable(in_department, asked.reach, asked.now))


# -------------------------------------------------------------------------- refusals


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The session factory, or a process-level fault identical for every caller."""
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable(what: str) -> Absent:
    """The one refusal this router makes. Names the screen, never a row or the caller."""
    return Absent(f"the {what} screen is not answerable for this caller")


def _refused_input(field: str, message: str) -> RequestValidationError:
    """A cursor the view refuses, as the 422 every other malformed parameter gets."""
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", field), "msg": message, "input": None}]
    )


def may_open_estate(asked: Asking) -> bool:
    """Whether this reader may open any of the four screens the estate is made of."""
    return any(
        permitted(screen(ESTATE_SCREEN[kind]).read, asked.reach, asked.now) for kind in EstateKind
    )


# ---------------------------------------------------------------------------- routes

router = APIRouter(prefix=API_PREFIX, tags=["company"])

Department = Annotated[str, Query(max_length=60, pattern=SLUG_PATTERN)]
Person = Annotated[str, Query(max_length=128, pattern=IDENTIFIER)]


@router.get(ESTATE_PATH, response_model=EstateView, responses=COMMON_RESPONSES)
async def company_estate(
    request: Request,
    asked: Asked,
    department: Department | None = None,
    person: Person | None = None,
    kind: EstateKind | None = None,
) -> EstateView:
    """Every agent, skill, knowledge item and connector this reader may know exists (M33.1.1.1).

    Narrowed by department, by person and by kind, all inside `global_surfaces.estate` and after
    its visibility check, so asking for a department this reader cannot see answers exactly as a
    department that owns nothing.
    """
    if not may_open_estate(asked):
        log.info("estate not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("estate")
    factory = _require_sessions(request)
    async with factory() as session:
        rows, labels = await estate_rows(session)
    lens = Lens(department=department or "", person=person or "")
    shown = estate(
        rows, asked.reach, lens=lens, kinds=() if kind is None else (kind,), now=asked.now
    )
    seen = visible_estate(rows, asked.reach, asked.now)
    people = offered_people(seen)
    return EstateView(
        items=[
            EstateRowView(
                kind=one.kind, item_id=one.item_id, label=labels[(one.kind.value, one.item_id)]
            )
            for one in shown
        ],
        kinds=list(EstateKind),
        departments=list(departments_offered(offered_departments(seen), asked.reach, asked.now)),
        people=people,
        names=await names_for(request, people),
    )


@router.get(ACTIVITY_PATH, response_model=CompanyActivityPage, responses=COMMON_RESPONSES)
async def company_activity_page(
    request: Request,
    asked: Asked,
    department: Department | None = None,
    person: Person | None = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    order: Order = Order.NEWEST,
    q: Annotated[str, Query(max_length=MAX_SEARCH_CHARS)] = "",
) -> CompanyActivityPage:
    """All activity this reader may see, narrowed by department and person (M33.1.1.2).

    The Audit screen's question first, then the cursor, then the directory and the ledger. A
    department is its people as this reader may name them; see
    `A_DEPARTMENT_IS_ITS_PEOPLE_AS_THIS_READER_MAY_NAME_THEM`. Newest first unless asked
    otherwise, and `q` is the Audit screen's own search, asked of a visible row's own words.
    """
    if not permitted(screen(AUDIT_SCREEN).read, asked.reach, asked.now):
        log.info("company activity not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("activity")
    if cursor is not None:
        try:
            position_of(cursor)
        except ValueError:
            raise _refused_input("cursor", "malformed cursor") from None
    lens = Lens(department=department or "", person=person or "")
    members = await members_of(request, asked, lens.department)
    # Asked only so the statement loads less; `company_activity` decides again over what arrives.
    actors = activity_filter(lens, members=members)
    ledger: LedgerWindows = NothingLogged() if actors is None else ledger_of(request)

    def view_of(loaded: Sequence[AuditEntry]) -> CompanyActivityView:
        return CompanyActivityView(
            AuditView(loaded, reader=asked.reach, now=asked.now), lens, members
        )

    words = search_words(q)
    page = await read_page(
        ledger,
        view_of,
        AuditFilter(actors=actors or frozenset()),
        limit=limit,
        cursor=cursor,
        newest_first=order is Order.NEWEST,
        shows=(lambda row: says_every_word(said_by(row), words)) if words else None,
    )
    factory = _require_sessions(request)
    async with factory() as session:
        slugs = [
            row[0] for row in (await session.execute(live_department_names(MAX_DEPARTMENTS))).all()
        ]
    return CompanyActivityPage(
        items=[row_view(row) for row in page.rows],
        next_cursor=page.next_cursor,
        order=order,
        departments=list(departments_offered(slugs, asked.reach, asked.now)),
        actors=actors_on(page.rows),
        people=await names_for(request, people_on(page.rows)),
    )


@router.get(CONSUMPTION_PATH, response_model=ConsumptionView, responses=COMMON_RESPONSES)
async def company_consumption_view(
    request: Request,
    asked: Asked,
    days: Annotated[int, Query(ge=1, le=MAX_CONSUMPTION_DAYS)] = DEFAULT_CONSUMPTION_DAYS,
) -> ConsumptionView:
    """What the company spent over the last `days`, or that this reader is not shown it
    (M33.1.1.3).

    The Budget screen's question first. A reader who may open it with a grant over less than
    everybody is answered that the figure is withheld, which `company_consumption` decides
    through `brain.console.workspace.basis_for`.
    """
    if not permitted(screen(SPEND_OF_OTHERS_SCREEN).read, asked.reach, asked.now):
        log.info("company consumption not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("budget")
    until = asked.now
    since = until - timedelta(days=days)
    factory = _require_sessions(request)
    async with factory() as session:
        loaded = (
            (await session.execute(spend_between(since, until, MAX_SPEND_ROWS))).scalars().all()
        )
    actuals: list[Actual] = [one for one in (actual_of(row) for row in loaded) if one is not None]
    found = company_consumption(actuals, asked.reach, since=since, until=until, now=asked.now)
    code, _zone = money_and_clock()
    if found is None:
        return ConsumptionView(
            currency=code,
            since=since,
            until=until,
            withheld=True,
            spend_minor=None,
            by_department=[],
            incomplete=False,
        )
    return ConsumptionView(
        currency=code,
        since=since,
        until=until,
        withheld=False,
        spend_minor=found.spend_minor,
        by_department=[
            DepartmentSpendView(department=name, spend_minor=minor)
            for name, minor in found.by_department
        ],
        incomplete=len(loaded) >= MAX_SPEND_ROWS,
    )
