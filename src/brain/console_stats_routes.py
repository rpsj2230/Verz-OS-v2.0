"""One entity's figures over HTTP: an agent, a skill, a connector and a channel.

The owner asked for a detail page with stats for every entity, and each module's list screen
already exists with its own decision about who may be told what. This router adds one address
per module, `GET /console/{module}/{id}/stats`, and adds no rule of its own about who may see
the entity: each one asks the question its list screen asks, in the same words, and refuses in
that screen's one sentence. `brain.console.entity_stats` does the arithmetic.

**Who may be told the entity exists is the module's own answer, and an entity outside it is a
404 identical to a name that matches nothing.** An agent is `brain.agent_routes._visible_record`,
the audience the workspace admits by. A skill is the Skills screen's read and then a skill the
reader's agents run or the library lists to them. A connector is the Connectors screen's read
and then `brain.console.connector_trust.admitted_connections`. A channel is
`brain.channel_routes._managed_wire`, the authority Connect Lark asks. Each refusal is the
module's `Absent`, whose public sentence is the same for every cause, so a missing name, a
hidden one and a screen the reader may not open are one status and one body. See
`brain.console.entity_stats.AN_ENTITY_OUT_OF_REACH_ANSWERS_AS_ONE_THAT_DOES_NOT_EXIST`.

**How a figure aggregates only rows the reader may read, per module.**

- An agent's requests are `obs.request_telemetry` rows naming it as `selected_agent`, at
  `brain.console.agent_tabs.usage_basis`: everybody's for a reader holding the Usage screen's
  read over everything, their own otherwise, with `principal = caller` in the WHERE clause on
  the narrower basis. Its cost is `brain.agent_routes.spend_for` at `basis_for`, the headline's
  own statement and basis, so this page and the headline cannot disagree.
- A skill's figures are over the agents `visible_records` admits and the library only when
  `may_read_library` lists it, so an agent outside the audience pins nothing here. Its runs are
  `agent.skill_invocation` rows of those agents alone, at `usage_basis`, with the agent ids and,
  on the narrower basis, `principal_id = caller` in the WHERE clause, so a run by an agent the
  reader may not see, or by a colleague when they may not read usage, never reaches the process.
- A connector's attempts are its own live connection's, which a reader admitted to the
  connector already reads on the Connectors screen. Its live reads are `obs.request_telemetry`
  rows whose `connector` names it, at `usage_basis` with `principal = caller` in the WHERE clause
  on the narrower basis, exactly as an agent's requests are. Its index size is counted in the
  database entity by entity with the reader's own row scope for that entity compiled into the WHERE
  clause by `brain.core.scope_sql.compile_where`, which is how the row plane reads
  `proj.record`; an entity the reader holds no read of contributes nothing and is never named.
  Ids are counted and no field is read.
- A channel's deliveries are readable whole to its manager on the Deliveries screen and are
  counted whole for them. Its bound people are counted at the People screen's basis, with the
  caller in the WHERE clause on the narrower one.

**A bounded read says `at_least`, never `truncated`.** In this API `truncated` says a list came
back full, and the console measures every answer carrying it as a list to page, search and filter.
These are figures with no rows behind them on the page, so the flag says what a reader should
read into them: the figures are at least these.

**No field on any view is a total beside a narrowed count, and none is named like one.**
`tests/unit/test_console_stats_routes.py` reads every field name of every view against
`brain.ops.jobs.NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT`.

**A figure nothing records is served in `unrecorded` with its reason and never as nought**:
a run's cost while `brain.console.agent_profile.RUN_SPEND_IS_RECORDED` is false, when
`cost_minor` is null. A channel's answers are served as messages sent, and `unrecorded` says why.
A skill's runs and a source's live reads are recorded and counted, so neither is listed there.

Rejected: a stats route for knowledge documents in this commit. `know.item` admits a reader
through `brain.knowledge.search.reach_for` over each item's visibility, and a per-document
figure (retrievals, citations) has no table recording it, so the page would be a 404 rule and
nothing to show.

Task ids: M27.15.8, M27.15.9, M27.15.27, M27.15.33
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.agent_routes import (
    _require_session_factory,
    _visible_record,
    actual_of,
    record_of,
    spend_for,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.channel_routes import _managed_wire
from brain.connector_routes import _not_answerable as _no_connector_here
from brain.connector_routes import _permitted as _connector_screen_permitted
from brain.connector_routes import records_of, sync_records_of
from brain.connectors.contract import ConnectorContractError
from brain.console.agent_output import basis_over
from brain.console.agent_profile import RUN_SPEND_IS_RECORDED
from brain.console.agent_tabs import usage_basis
from brain.console.connector_trust import admitted_connections
from brain.console.entity_stats import (
    CHANNEL_ANSWERS_ARE_NOT_TOLD_APART,
    LONGEST,
    MAX_ACTIVITY_ROWS,
    RUN_COST_IS_NOT_RECORDED,
    Attempt,
    Delivery,
    LiveRead,
    Run,
    SkillRun,
    Unrecorded,
    attempt_figures,
    bound_people,
    counted,
    delivery_figures,
    last_active,
    newest,
    periods,
    run_figures,
    skill_figures,
    skill_runs,
    versions_added,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.skill_library import may_read_library
from brain.console.workspace import Basis, basis_for, headline, window
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Failed
from brain.core.scope_sql import compile_where
from brain.gate.context import Channel
from brain.knowledge.rows import NOTHING, RECORD, ROW_LAYOUT, SCOPE_PREFIX, row_scope_for
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import SyncOutcome
from brain.ops.skill_store import MAX_LIBRARY
from brain.ops.spend import Actual
from brain.ops.telemetry import RequestStatus
from brain.report_routes import money_and_clock
from brain.skill_routes import (
    MAX_AGENTS_CONSIDERED,
    SKILLS_SCREEN,
    bounded_agents,
    installs_of,
    library_of,
    pins_of,
    visible_records,
)
from brain.skill_routes import _not_answerable as _no_skill_here
from brain.tables.channel import ChannelDeliveryRow, DeliveryOutcome, Direction
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.connector_sync import ConnectorSyncRow
from brain.tables.identity import PrincipalIdentityRow
from brain.tables.skill_invocation import SkillInvocationRow
from brain.tables.telemetry import RequestTelemetryRow

log = structlog.get_logger()

#: The screen whose read decides whose bindings a channel's bound-people figure is over.
#:
#: A binding is a person, so the figure follows the screen where people are read, rather than
#: the channel authority, which governs a channel's record and says nothing about people.
PEOPLE_SCREEN: Final = "people"

AGENT_STATS_PATH: Final = "/console/agents/{agent_id}/stats"
SKILL_STATS_PATH: Final = "/console/skills/{skill_name}/stats"
CONNECTOR_STATS_PATH: Final = "/console/connectors/{connector}/stats"
CHANNEL_STATS_PATH: Final = "/console/channels/{name}/stats"

#: The widest name a path segment here accepts. Every entity key in this product is shorter.
MAX_NAME_CHARS: Final = 128

Named = Annotated[str, Path(min_length=1, max_length=MAX_NAME_CHARS)]


# ------------------------------------------------------------------------------ the views
class UnrecordedView(BaseModel):
    """A figure the page asks for that nothing on this install records, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    figure: str
    why: str


class AgentPeriodView(BaseModel):
    """One agent's figures over one period.

    `nothing_returned` is refused and abstained together, never split; see
    `brain.console.entity_stats.A_REFUSAL_AND_AN_ABSENCE_ARE_ONE_FIGURE`. `cost_minor` is in
    the install's minor units and null while nothing records a run's cost.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    since: datetime
    until: datetime
    runs: int
    answered: int
    nothing_returned: int
    p50_latency_ms: float | None
    cost_minor: int | None


class AgentStatsView(BaseModel):
    """One agent's figures, and whose they are.

    `basis` is the requests' and `cost_basis` the cost's, each `own` or `everyone`, carried so
    a reader shown their own figures does not read them as the agent's. `at_least` says the
    requests were read to their bound, so the figures are at least these.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    basis: str
    cost_basis: str
    currency: str
    last_active: datetime | None
    at_least: bool
    periods: list[AgentPeriodView]
    unrecorded: list[UnrecordedView]


class SkillPeriodView(BaseModel):
    """One skill's figures over one period: versions that arrived in the library, and runs.

    `runs` counts the requests that used the skill through an agent the reader may see, at
    `SkillStatsView.run_basis`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    since: datetime
    until: datetime
    versions_added: int | None
    runs: int


class SkillStatsView(BaseModel):
    """One skill across the reader's agents and the library.

    `versions` and each period's `versions_added` are null for a reader the library is not
    listed to, which is also what they are when the library holds no version of it. `run_basis`
    is whose runs are counted, `own` or `everyone`; `last_used` is the newest of them in the
    longest period, null when there is none; `at_least` says the runs were read to their bound.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_name: str
    agents_pinned: int
    pinned_versions: int
    versions: int | None
    run_basis: str
    last_used: datetime | None
    at_least: bool
    periods: list[SkillPeriodView]
    unrecorded: list[UnrecordedView]


class ConnectorPeriodView(BaseModel):
    """The worker's attempts on one source over one period, and the questions that read it live.

    `live_reads` is at `ConnectorStatsView.live_read_basis`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    since: datetime
    until: datetime
    attempts: int
    read_to_the_end: int
    failures: int
    quota_waits: int
    live_reads: int


class ConnectorStatsView(BaseModel):
    """One connected source: its health, when it was last read, its attempts and its index.

    `index_ids` counts the ids this install keeps of the source that the reader's own row scope
    admits, entity by entity; it is null when the source's manifest cannot be built today, so
    nothing says which entities it keeps. No field or value of a record is read to count it.
    `live_read_basis` is whose questions the live reads are, `own` or `everyone`, and
    `last_live_read` the newest of them in the longest period, null when there is none.
    `at_least` says the attempts or the live reads were read to their bound.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    health: str | None
    last_attempt: datetime | None
    last_read_to_the_end: datetime | None
    consecutive_failures: int | None
    index_ids: int | None
    live_read_basis: str
    last_live_read: datetime | None
    at_least: bool
    periods: list[ConnectorPeriodView]
    unrecorded: list[UnrecordedView]


class ChannelPeriodView(BaseModel):
    """What crossed one channel over one period. Never what was said or by whom."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    range: str
    since: datetime
    until: datetime
    received: int
    sent: int
    failed: int
    unknown: int
    refused_inbound: int


class ChannelStatsView(BaseModel):
    """One channel's traffic, its bound people and its last event.

    `bound_basis` is `everyone` for a reader of the People screen over everything and `own`
    otherwise, when `bound_people` says whether the reader is bound themselves.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    bound_people: int
    bound_basis: str
    last_event: datetime | None
    at_least: bool
    periods: list[ChannelPeriodView]
    unrecorded: list[UnrecordedView]


def _unrecorded(rows: Sequence[Unrecorded]) -> list[UnrecordedView]:
    return [UnrecordedView(figure=one.figure, why=one.why) for one in rows]


# ------------------------------------------------------------------------- the statements
def agent_requests(
    agent_id: str, since: datetime, *, basis: Basis, caller_id: str
) -> Select[tuple[str, datetime, str, float]]:
    """The requests that chose this agent since an instant, newest first and bounded.

    On the narrower basis the caller is in the WHERE clause, so nobody else's request reaches
    this process, and the bound is a bound on rows the reader may be counted over.
    """
    statement = select(
        RequestTelemetryRow.principal,
        RequestTelemetryRow.received_at,
        RequestTelemetryRow.status,
        RequestTelemetryRow.duration_ms,
    ).where(
        RequestTelemetryRow.selected_agent == agent_id,
        RequestTelemetryRow.received_at >= since,
    )
    if basis is not Basis.EVERYONE:
        statement = statement.where(RequestTelemetryRow.principal == caller_id)
    return statement.order_by(RequestTelemetryRow.received_at.desc()).limit(MAX_ACTIVITY_ROWS)


def skill_invocations(
    skill_name: str,
    agent_ids: Sequence[str],
    since: datetime,
    *,
    basis: Basis,
    caller_id: str,
) -> Select[tuple[str, str, datetime]]:
    """The runs that used this skill through these agents since an instant, newest first, bounded.

    The agents are the ones the reader may see, and on the narrower basis the caller is in the
    WHERE clause too, so a run by another agent or another person never reaches this process
    and the bound is a bound on rows the reader may be counted over.
    """
    statement = select(
        SkillInvocationRow.principal_id,
        SkillInvocationRow.agent_id,
        SkillInvocationRow.used_at,
    ).where(
        SkillInvocationRow.skill_name == skill_name,
        SkillInvocationRow.agent_id.in_(list(agent_ids)),
        SkillInvocationRow.used_at >= since,
    )
    if basis is not Basis.EVERYONE:
        statement = statement.where(SkillInvocationRow.principal_id == caller_id)
    return statement.order_by(SkillInvocationRow.used_at.desc()).limit(MAX_ACTIVITY_ROWS)


def connector_live_reads(
    connector: str, since: datetime, *, basis: Basis, caller_id: str
) -> Select[tuple[str, datetime]]:
    """The requests that read this source live since an instant, newest first and bounded.

    `agent_requests` with the source in place of the agent: on the narrower basis the caller is
    in the WHERE clause, so nobody else's question reaches this process.
    """
    statement = select(RequestTelemetryRow.principal, RequestTelemetryRow.received_at).where(
        RequestTelemetryRow.connector == connector,
        RequestTelemetryRow.received_at >= since,
    )
    if basis is not Basis.EVERYONE:
        statement = statement.where(RequestTelemetryRow.principal == caller_id)
    return statement.order_by(RequestTelemetryRow.received_at.desc()).limit(MAX_ACTIVITY_ROWS)


def connector_attempts(connector: str, since: datetime) -> Select[tuple[datetime, str]]:
    """The live connection's finished attempts since an instant, newest first and bounded.

    Joined on the live connection rather than read by name, because `ops.connector_sync` names
    the connection and a source connected again is a new one whose history starts afresh. A test
    a person asked for (`probed`, `0142`) is not an attempt to read the source and is left out, so
    it counts toward no attempt, failure or read, and never uses up the bound.
    """
    return (
        select(ConnectorSyncRow.finished_at, ConnectorSyncRow.outcome)
        .join(
            ConnectorConnectionRow,
            and_(
                ConnectorConnectionRow.id == ConnectorSyncRow.connection_id,
                ConnectorConnectionRow.disconnected_at.is_(None),
            ),
        )
        .where(ConnectorSyncRow.connector == connector, ConnectorSyncRow.finished_at >= since)
        .where(ConnectorSyncRow.outcome != SyncOutcome.PROBED.value)
        .order_by(ConnectorSyncRow.finished_at.desc())
        .limit(MAX_ACTIVITY_ROWS)
    )


def index_ids(source: str, entity: str, reach: EntitlementSet, now: datetime) -> Select[tuple[int]]:
    """How many kept ids of one entity of one source this reader's row scope admits.

    The scope is `brain.knowledge.rows.row_scope_for` and it is compiled by `compile_where`,
    the one renderer, into the statement, which is the row plane's rule that a row the caller
    may not see never leaves the database; here not even its count does. A reader holding no
    read of the entity compiles to `FALSE`, never to a missing clause.
    """
    scope = row_scope_for(entity, reach, now)
    predicate = NOTHING if scope is None else compile_where(scope, ROW_LAYOUT, SCOPE_PREFIX)
    return (
        select(func.count())
        .select_from(RECORD)
        .where(
            RECORD.c.source == source,
            RECORD.c.entity == entity,
            RECORD.c.deleted_at.is_(None),
            text(predicate.where).bindparams(**predicate.params),
        )
    )


def channel_deliveries(channel: Channel, since: datetime) -> Select[tuple[str, str, datetime]]:
    """One channel's deliveries since an instant, newest first and bounded. No content exists."""
    return (
        select(
            ChannelDeliveryRow.direction,
            ChannelDeliveryRow.outcome,
            ChannelDeliveryRow.recorded_at,
        )
        .where(
            ChannelDeliveryRow.channel == channel.value,
            ChannelDeliveryRow.recorded_at >= since,
        )
        .order_by(ChannelDeliveryRow.recorded_at.desc())
        .limit(MAX_ACTIVITY_ROWS)
    )


def channel_last_event(channel: Channel) -> Select[tuple[datetime]]:
    """When anything last crossed this channel, in either direction."""
    return select(func.max(ChannelDeliveryRow.recorded_at)).where(
        ChannelDeliveryRow.channel == channel.value
    )


def channel_bindings(channel: Channel, *, basis: Basis, caller_id: str) -> Select[tuple[str]]:
    """The people with a live binding on this channel, the caller alone on the narrower basis."""
    statement = select(PrincipalIdentityRow.principal_id).where(
        PrincipalIdentityRow.channel == channel.value,
        PrincipalIdentityRow.deleted_at.is_(None),
    )
    if basis is not Basis.EVERYONE:
        statement = statement.where(PrincipalIdentityRow.principal_id == caller_id)
    return statement.distinct()


# ---------------------------------------------------------------------------- the wiring
async def _agent_runs(
    session: AsyncSession, agent_id: str, since: datetime, *, basis: Basis, caller_id: str
) -> list[Run]:
    rows = (
        await session.execute(agent_requests(agent_id, since, basis=basis, caller_id=caller_id))
    ).all()
    runs: list[Run] = []
    for principal, at, status, duration in rows:
        try:
            runs.append(
                Run(
                    principal_id=principal,
                    at=at,
                    status=RequestStatus(status),
                    duration_ms=duration,
                )
            )
        except ValueError:
            # A status the table's check admits and this release does not know. Absent from
            # the figure for everybody alike rather than taking the page down.
            log.warning("request row does not construct", agent=agent_id)
    return runs


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(AGENT_STATS_PATH, response_model=AgentStatsView, responses=COMMON_RESPONSES)
async def agent_stats(request: Request, agent_id: Named, asked: Asked) -> AgentStatsView:
    """One agent's requests, answers, nothing returned, median time, cost and last activity.

    The audience admits the caller before anything else about the agent is read, so an agent
    they may not see answers exactly as one that does not exist and nothing is fetched for it.
    """
    factory = _require_session_factory(request)
    caller_id = asked.caller.principal.id
    basis = usage_basis(asked.reach, asked.now)
    cost_basis = basis_for(asked.reach, asked.now)
    since, _ = window(LONGEST, asked.now)
    async with factory() as session:
        await _visible_record(session, agent_id, asked)
        runs = await _agent_runs(session, agent_id, since, basis=basis, caller_id=caller_id)
        costs = (await session.execute(spend_for(agent_id, since))).scalars().all()
    spend: list[Actual] = [one for one in (actual_of(row) for row in costs) if one is not None]
    code, _ = money_and_clock()
    views: list[AgentPeriodView] = []
    for one, start, end in periods(asked.now):
        figures = run_figures(runs, caller_id=caller_id, basis=basis, since=start, until=end)
        cost = headline(
            agent_id, caller_id=caller_id, basis=cost_basis, actuals=spend, since=start, until=end
        )
        views.append(
            AgentPeriodView(
                range=one.value,
                since=start,
                until=end,
                runs=figures.runs,
                answered=figures.answered,
                nothing_returned=figures.nothing_returned,
                p50_latency_ms=figures.p50_latency_ms,
                cost_minor=cost.spend_minor if RUN_SPEND_IS_RECORDED else None,
            )
        )
    return AgentStatsView(
        agent_id=agent_id,
        basis=basis.value,
        cost_basis=cost_basis.value,
        currency=code,
        last_active=last_active(
            runs, caller_id=caller_id, basis=basis, since=since, until=asked.now
        ),
        at_least=len(runs) >= MAX_ACTIVITY_ROWS,
        periods=views,
        unrecorded=_unrecorded(() if RUN_SPEND_IS_RECORDED else (RUN_COST_IS_NOT_RECORDED,)),
    )


@router.get(SKILL_STATS_PATH, response_model=SkillStatsView, responses=COMMON_RESPONSES)
async def skill_stats(request: Request, skill_name: Named, asked: Asked) -> SkillStatsView:
    """How many of the reader's agents run one skill, at how many versions, and the library's.

    The Skills screen's read first, then the agents the reader's audience covers, then the
    library only when it is listed to them. A skill none of those name is refused exactly as
    a reader without the screen is.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now):
        log.info("skill stats not answerable", principal=asked.caller.principal.id)
        raise _no_skill_here()
    factory = _require_session_factory(request)
    async with factory() as session:
        rows = (await session.execute(bounded_agents(MAX_AGENTS_CONSIDERED))).scalars().all()
        records = [one for one in (record_of(row) for row in rows) if one is not None]
        mine = visible_records(records, asked)
        pairs = (await session.execute(installs_of([one.agent_id for one in mine]))).all()
    by_id = {one.agent_id: one for one in mine}
    pins = [
        (pin.agent_id, pin.skill_name, pin.digest)
        for instance_row, version_row in pairs
        if instance_row.id in by_id
        for pin in pins_of(instance_row, version_row, by_id[instance_row.id])
    ]
    readable = may_read_library(asked.reach, asked.now)
    library = await library_of(request).library(MAX_LIBRARY) if readable else ()
    named = [one for one in library if one.name == skill_name]
    if not named and not any(skill == skill_name for _, skill, _ in pins):
        log.info("skill stats not answerable", principal=asked.caller.principal.id)
        raise _no_skill_here()
    figures = skill_figures(
        skill_name, pins, [(one.name, one.digest) for one in named] if readable else None
    )
    submitted = [(one.name, one.submitted_at) for one in named]
    caller_id = asked.caller.principal.id
    basis = usage_basis(asked.reach, asked.now)
    agents = frozenset(by_id)
    since, _ = window(LONGEST, asked.now)
    async with factory() as session:
        used = (
            await session.execute(
                skill_invocations(
                    skill_name, sorted(agents), since, basis=basis, caller_id=caller_id
                )
            )
        ).all()
    runs = [SkillRun(agent_id=agent, principal_id=who, at=at) for who, agent, at in used]

    def runs_in(start: datetime, end: datetime) -> tuple[SkillRun, ...]:
        return skill_runs(
            runs, agents=agents, caller_id=caller_id, basis=basis, since=start, until=end
        )

    return SkillStatsView(
        skill_name=skill_name,
        agents_pinned=figures.agents_pinned,
        pinned_versions=figures.pinned_versions,
        versions=figures.versions,
        run_basis=basis.value,
        last_used=max((one.at for one in runs_in(since, asked.now)), default=None),
        at_least=len(used) >= MAX_ACTIVITY_ROWS,
        periods=[
            SkillPeriodView(
                range=one.value,
                since=start,
                until=end,
                versions_added=(
                    versions_added(skill_name, submitted, since=start, until=end)
                    if readable
                    else None
                ),
                runs=len(runs_in(start, end)),
            )
            for one, start, end in periods(asked.now)
        ],
        unrecorded=[],
    )


def _admitted(found: Sequence[Connection], name: str, asked: Asking) -> Connection:
    """The live connection of this name the reader may be told of, or the screen's refusal."""
    for one in admitted_connections(found, asked.reach, asked.now):
        if one.connector == name:
            return one
    raise _no_connector_here("connector stats")


def _entities(one: Connection) -> tuple[str, ...] | None:
    """The entities this connection's manifest keeps, or None when it cannot be built today."""
    try:
        manifest = manifest_for(one.connector, one.settings)
    except (NotConnectableError, ConnectorContractError):
        return None
    return tuple(sorted({projection.entity for projection in manifest.projections}))


@router.get(CONNECTOR_STATS_PATH, response_model=ConnectorStatsView, responses=COMMON_RESPONSES)
async def connector_stats(request: Request, connector: Named, asked: Asked) -> ConnectorStatsView:
    """One source's health, last full read, attempts per period and the ids it keeps.

    The screen's read before the database, then the connections the reader may be told of, and
    only then anything about the named one, so a source out of reach costs no query of its own.
    """
    _connector_screen_permitted(asked.reach, asked.now)
    caller_id = asked.caller.principal.id
    basis = usage_basis(asked.reach, asked.now)
    records = records_of(request)
    if records is None:
        raise Failed("no database on this process")
    one = _admitted(await records.connected(), connector, asked)
    sync = sync_records_of(request)
    state = None if sync is None else (await sync.states()).get(one.connector)
    since, _ = window(LONGEST, asked.now)
    entities = _entities(one)
    factory = _require_session_factory(request)
    async with factory() as session:
        rows = (await session.execute(connector_attempts(one.connector, since))).all()
        read_rows = (
            await session.execute(
                connector_live_reads(one.connector, since, basis=basis, caller_id=caller_id)
            )
        ).all()
        kept: int | None = None
        if entities is not None:
            kept = 0
            for entity in entities:
                found = (
                    await session.execute(index_ids(one.connector, entity, asked.reach, asked.now))
                ).scalar_one_or_none()
                kept += int(found or 0)
    attempts = [
        Attempt(at=at, outcome=SyncOutcome(outcome))
        for at, outcome in rows
        if outcome in {member.value for member in SyncOutcome}
    ]
    reads = [LiveRead(principal_id=who, at=at) for who, at in read_rows]
    return ConnectorStatsView(
        connector=one.connector,
        health=None if state is None else state.health.value,
        last_attempt=None if state is None else state.finished_at,
        last_read_to_the_end=None if state is None else state.last_synced_at,
        consecutive_failures=None if state is None else state.consecutive_failures,
        index_ids=kept,
        live_read_basis=basis.value,
        last_live_read=last_active(
            reads, caller_id=caller_id, basis=basis, since=since, until=asked.now
        ),
        at_least=len(rows) >= MAX_ACTIVITY_ROWS or len(read_rows) >= MAX_ACTIVITY_ROWS,
        periods=[
            ConnectorPeriodView(
                range=period.value,
                since=start,
                until=end,
                **asdict(attempt_figures(attempts, since=start, until=end)),
                live_reads=len(
                    counted(reads, caller_id=caller_id, basis=basis, since=start, until=end)
                ),
            )
            for period, start, end in periods(asked.now)
        ],
        unrecorded=[],
    )


@router.get(CHANNEL_STATS_PATH, response_model=ChannelStatsView, responses=COMMON_RESPONSES)
async def channel_stats(request: Request, name: Named, asked: Asked) -> ChannelStatsView:
    """One channel's messages received and sent, failures, bound people and last event.

    The channel authority first, which refuses a channel the reader may not manage exactly as a
    name that is no channel, and the database after it.
    """
    channel, _ = _managed_wire(name, asked)
    factory = _require_session_factory(request)
    caller_id = asked.caller.principal.id
    people_basis = basis_over(PEOPLE_SCREEN, asked.reach, asked.now)
    since, _ = window(LONGEST, asked.now)
    async with factory() as session:
        rows = (await session.execute(channel_deliveries(channel, since))).all()
        last = (await session.execute(channel_last_event(channel))).scalar_one_or_none()
        bound = (
            (
                await session.execute(
                    channel_bindings(channel, basis=people_basis, caller_id=caller_id)
                )
            )
            .scalars()
            .all()
        )
    deliveries = [
        Delivery(direction=Direction(direction), outcome=DeliveryOutcome(outcome), at=at)
        for direction, outcome, at in rows
    ]
    return ChannelStatsView(
        channel=channel.value,
        bound_people=bound_people(bound, caller_id=caller_id, basis=people_basis),
        bound_basis=people_basis.value,
        last_event=newest([last]),
        at_least=len(rows) >= MAX_ACTIVITY_ROWS,
        periods=[
            ChannelPeriodView(
                range=period.value,
                since=start,
                until=end,
                **asdict(delivery_figures(deliveries, since=start, until=end)),
            )
            for period, start, end in periods(asked.now)
        ],
        unrecorded=_unrecorded((CHANNEL_ANSWERS_ARE_NOT_TOLD_APART,)),
    )
