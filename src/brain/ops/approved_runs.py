"""An approved action runs once, with nobody present, at its requester's reach as it is now.

M13.7.6 asks that an approved action run once without the requester returning, at the requester's
reach re-resolved at that moment, and that a rejected, amended or lapsed one never run. Everything
that decides whether it may run already exists: `brain.gate.leash.resume` re-checks the approval,
its window, the principal, the action's digest, the reach and the leash, and keys the run in the
operation ledger so it happens once. What was missing is a caller. An approval was recorded on the
Approvals screen and nothing sent it, for a DNS change or for anything else. This module is that
caller, and it is a worker control (`approved_actions`), so it runs whether or not anybody comes
back, every five minutes.

**One class of thing, whatever the action is.** An `Executor` names the tools it can run and runs
one approved suspension through `resume`. `ConnectorWrites` is the executor for every write a
connector declares (`brain.connectors.declaration.WriteGrant`), and runs it through
`brain.ops.connector_write_run.send_approved`, which sends with the grant's own key and reads the
change back before calling it done. A tool with no executor is never listed, so an approval of a
kind nothing can run stays approved until it lapses rather than being reported run. See
`AN_ACTION_NOTHING_CAN_RUN_IS_NEVER_LISTED`.

**The worker sees approved actions through one narrow door.** `gate.approved_to_run` (`0201`)
returns the id and the principal of each approved suspension inside its window, naming a tool an
executor runs, with no operation recorded against it, and nothing else. Each is then read **at its
principal's reach, resolved now** through the one resolver (`StoredEntitlements`), so `0042`'s
own-row clause is what admits it and a person removed or narrowed since the approval is the person
`resume` is handed. See `THE_REACH_IS_THE_REQUESTERS_AS_IT_IS_NOW`.

**The run is checked against what was approved, and the hash is the test.** `resume` compares the
reach the run would have, the requester's held reach intersected with the agent's ceiling, with the
hash the suspension recorded when it was raised, which `brain.gate.leash.decide` computed from the
same two sets through the one `intersect`. So a suspension this worker is to run is raised at the
requester's reach from the one resolver and the agent's stored ceiling, and any change to either
side since, a grant taken away or an agent narrowed, is a refusal and never a run at a reach nobody
approved.

**The agent is read now too.** Its ceiling and its bound leash come from the agent's stored record
and install (`StoredStandings`), so a leash lowered or an agent disabled since the approval bites,
which `resume`'s own rung check relies on. An agent that is gone or not enabled runs nothing.

**What a run came to is counted and logged by kind, never by content.** `ApprovedRun` says how many
ran, how many were refused and why in a word, and the log names the suspension and the outcome and
nothing an action carries.

Task ids: M13.7.6
"""

from __future__ import annotations

import asyncio
import enum
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.field_policy import FieldPolicy
from brain.gate.injection import RiskAssessment
from brain.gate.leash import Action, Leash, SuspendedAction
from brain.ops.idempotency import OperationLedger

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why a tool with no executor is filtered out rather than refused on every run.
AN_ACTION_NOTHING_CAN_RUN_IS_NEVER_LISTED: Final = (
    "The worker asks for approved actions naming the tools its executors run, and no others. An "
    "approval of a kind nothing can run stays approved and unrun until its window lapses, and is "
    "never reported as run, never retried every minute, and never crowds out one that can run."
)

#: Why the reach is resolved at the run and not remembered from the approval.
THE_REACH_IS_THE_REQUESTERS_AS_IT_IS_NOW: Final = (
    "An approval is a statement about a moment. The run is made at the requester's reach resolved "
    "when it runs, through the one resolver, so a grant taken away or a person removed since the "
    "approval is a refusal, and the action never runs at a reach that no longer exists."
)

# ------------------------------------------------------------------------ the figures
#: How often the worker looks. Five minutes, the worker's shortest cadence: an approved reply or
#: change is one a person is waiting to see happen, and each look is one read when nothing waits.
RUNS_EVERY: Final = timedelta(minutes=5)

#: The most approved actions one look takes. The rest are taken on the next.
PER_RUN: Final = 50


class Ran(enum.StrEnum):
    """What one approved action came to. Closed."""

    #: Run, and its effect confirmed.
    DONE = "done"
    #: Run, and its effect not confirmed or refused by the system it changes.
    FAILED = "failed"
    #: Not run: the install has not given what it needs, such as a write grant's key. Stays
    #: approved, so it runs once the install allows it, inside its window.
    NOT_ALLOWED = "not_allowed"
    #: Not run: the approval no longer runs as approved (lapsed, the reach, the agent or the leash
    #: moved). `resume` decided.
    REFUSED = "refused"
    #: Not run again: an earlier run already won its key.
    ALREADY_RAN = "already_ran"
    #: Not run: nothing the action needs exists any more (its agent, or its connection).
    GONE = "gone"


@dataclass(frozen=True)
class Listed:
    """One approved action the narrow door returned: an id and whose it is, and nothing else."""

    suspension_id: str
    principal_id: str


@dataclass(frozen=True)
class Standing:
    """An agent as it is now: what it may ever reach, and its bound leash."""

    ceiling: EntitlementSet
    leash: Leash


class Standings(Protocol):
    """Where an agent's standing is read at the moment of a run."""

    async def standing(self, agent_id: str, now: datetime) -> Standing | None: ...


class Reaches(Protocol):
    """The one resolver: a principal's reach at an instant."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet: ...


@dataclass(frozen=True)
class RunContext:
    """Everything `resume` is handed besides the suspension, resolved for this run."""

    reach: EntitlementSet
    agent_ceiling: EntitlementSet
    policy: FieldPolicy
    leash: Leash
    assessment: RiskAssessment
    trace_id: str
    now: datetime
    ledger: OperationLedger


class Executor(Protocol):
    """Runs approved actions of the tools it names, each through `brain.gate.leash.resume`."""

    def tools(self) -> frozenset[str]: ...

    async def run(self, suspension: SuspendedAction, context: RunContext) -> Ran: ...


@dataclass(frozen=True)
class ApprovedRun:
    """What one look came to, by outcome. Counts only."""

    listed: int
    outcomes: Mapping[Ran, int] = field(default_factory=dict)

    def summary(self) -> str:
        if self.listed == 0:
            return "no approved action was waiting to run"
        said = ", ".join(f"{count} {one.value}" for one, count in sorted(self.outcomes.items()))
        return f"{self.listed} approved action(s) looked at: {said}"


def assessment_of(action: Action) -> RiskAssessment:
    """The injection screen over what the action carries, as the automation step route takes it.

    `brain.gate.runtime_effects.action_assessment`, which is where an agent run raises an action,
    so the same function is read where the action is raised and where it is run.
    """
    from brain.gate.runtime_effects import action_assessment

    return action_assessment(action)


def policy_of(action: Action) -> FieldPolicy:
    """The field policy the action's target is decided under: its source's read classification,
    and the fields that source's write grants declare (`brain.tools.startup.field_policy_for`).

    `brain.gate.runtime_effects.action_policy`, for the reason `assessment_of` gives.
    """
    from brain.gate.runtime_effects import action_policy

    return action_policy(action)


async def approved_to_run(
    session: AsyncSession, *, now: datetime, tools: Sequence[str], limit: int = PER_RUN
) -> list[Listed]:
    """`gate.approved_to_run`: the approved, unrun, unlapsed actions of these tools. See `0201`."""
    if not tools:
        return []
    rows = await session.execute(
        text("SELECT suspension_id, principal_id FROM gate.approved_to_run(:now, :tools, :limit)"),
        {"now": now, "tools": sorted(tools), "limit": limit},
    )
    return [Listed(suspension_id=one, principal_id=whose) for one, whose in rows.all()]


async def run_approved(
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    executors: Sequence[Executor],
    standings: Standings,
    reaches: Reaches,
    ledger: OperationLedger,
    limit: int = PER_RUN,
) -> ApprovedRun:
    """Run every approved action waiting, each once, at its requester's reach as it is now.

    See the module docstring for each rule. A failure in one action is logged by its class and
    counted, and never stops the others.
    """
    from brain.gate.suspension_store import StoredSuspensions

    by_tool = {tool: one for one in executors for tool in one.tools()}
    async with sessions() as session, session.begin():
        listed = await approved_to_run(session, now=now, tools=list(by_tool), limit=limit)
    outcomes: dict[Ran, int] = {}
    store = StoredSuspensions(sessions)
    for one in listed:
        trace_id = f"approved_{uuid.uuid4().hex[:24]}"
        try:
            ran = await _run_one(store, one, by_tool, standings, reaches, ledger, now, trace_id)
        except Exception as exc:
            log.warning(
                "approved_action.not_run",
                suspension=one.suspension_id,
                error=type(exc).__name__,
            )
            ran = Ran.FAILED
        log.info("approved_action.ran", suspension=one.suspension_id, outcome=ran.value)
        outcomes[ran] = outcomes.get(ran, 0) + 1
    return ApprovedRun(listed=len(listed), outcomes=outcomes)


async def _run_one(
    store: Any,
    listed: Listed,
    by_tool: Mapping[str, Executor],
    standings: Standings,
    reaches: Reaches,
    ledger: OperationLedger,
    now: datetime,
    trace_id: str,
) -> Ran:
    reach = await reaches.load(listed.principal_id, now)
    suspension = await store.reading_as(reach, now).suspension(listed.suspension_id)
    if suspension is None:
        # Not readable at the requester's reach now: they are no longer who the row runs as.
        return Ran.GONE
    executor = by_tool.get(suspension.action.tool.name)
    standing = await standings.standing(suspension.action.agent_id, now)
    if executor is None or standing is None:
        return Ran.GONE
    context = RunContext(
        reach=reach,
        agent_ceiling=standing.ceiling,
        policy=policy_of(suspension.action),
        leash=standing.leash,
        assessment=assessment_of(suspension.action),
        trace_id=trace_id,
        now=now,
        ledger=ledger,
    )
    return await executor.run(suspension, context)


# ------------------------------------------------------------------ the agent, read now
@dataclass(frozen=True)
class StoredStandings:
    """An agent's ceiling and bound leash from its stored record and install, read at the run.

    The reads the automation worker makes for the agent it runs (`brain.ops.automation_run_store`),
    under the runner's own actor. An agent that is gone, does not construct, or is not enabled has
    no standing, and runs nothing.
    """

    sessions: async_sessionmaker[AsyncSession]
    registry: Any = None

    async def standing(self, agent_id: str, now: datetime) -> Standing | None:
        del now
        from brain.agent_routes import install_for, install_of, leash_of, one_agent, record_of
        from brain.agents.model import entitlement_ceiling
        from brain.ops.automation_owner_store import PRINCIPAL_SETTING
        from brain.ops.automation_run import RUNNER_ACTOR

        async with self.sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config(:name, :value, true)"),
                {"name": PRINCIPAL_SETTING, "value": RUNNER_ACTOR},
            )
            row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
            record = None if row is None else record_of(row)
            if record is None or not record.is_selectable:
                return None
            pair = (await session.execute(install_for(agent_id))).one_or_none()
        install = None if pair is None else install_of(pair[0], pair[1], record)
        return Standing(ceiling=entitlement_ceiling(record), leash=leash_of(install, self.registry))


# ------------------------------------------------------------------ an agent's own tools
class ToolExecutor:
    """The executor for actions whose effect is a handler this process holds, by tool name.

    Each run goes through `brain.gate.leash.resume` with the context resolved for it, so every
    check `resume` makes is made, and the run is keyed in the ledger before the handler is called.
    The handler is given the action and the reach the run is made at, which `resume` has checked
    against the approval, and nothing else.
    """

    def __init__(
        self, handlers: Mapping[str, Callable[[Action, EntitlementSet], TypedResult[Any]]]
    ) -> None:
        self._handlers = dict(handlers)

    def tools(self) -> frozenset[str]:
        return frozenset(self._handlers)

    async def run(self, suspension: SuspendedAction, context: RunContext) -> Ran:
        from brain.gate.leash import resume

        handler = self._handlers[suspension.action.tool.name]

        def execute(action: Action) -> TypedResult[Any]:
            return handler(action, context.reach)

        resumed = await asyncio.to_thread(
            resume,
            suspension,
            caller=context.reach,
            agent_ceiling=context.agent_ceiling,
            policy=context.policy,
            leash=context.leash,
            assessment=context.assessment,
            trace_id=context.trace_id,
            now=context.now,
            execute=execute,
            ledger=context.ledger,
        )
        if resumed.repeated is not None:
            return Ran.ALREADY_RAN
        if not resumed.resumed:
            return Ran.REFUSED
        return Ran.DONE


# ------------------------------------------------------------------ connector writes
class ConnectorWrites:
    """The executor for every write a connector declares: sent with the grant's own key, read back.

    `brain.ops.connector_write_run.send_approved` is the whole of what it does with one action;
    this finds the live connection of the connector whose grant sends the tool and hands it over,
    in a thread, because the send and the ledger are synchronous.
    """

    def __init__(
        self,
        *,
        connections: Callable[[], Awaitable[Sequence[Any]]],
        keys: Any,
        caller: Any,
        resolver: Any,
        clock: Callable[[], datetime],
        declarations: Mapping[str, Any] | None = None,
    ) -> None:
        from brain.connectors.declaration import shipped

        self._connections = connections
        self._keys = keys
        self._caller = caller
        self._resolver = resolver
        self._clock = clock
        self._declared = shipped() if declarations is None else declarations

    def tools(self) -> frozenset[str]:
        return frozenset(
            tool
            for declared in self._declared.values()
            for grant in declared.writes
            for tool in grant.tools
        )

    def _connector_of(self, tool: str) -> str | None:
        for name, declared in self._declared.items():
            if any(tool in grant.tools for grant in declared.writes):
                return str(name)
        return None

    async def run(self, suspension: SuspendedAction, context: RunContext) -> Ran:
        from brain.ops.connector_write_run import WriteOutcome, send_approved

        connector = self._connector_of(suspension.action.tool.name)
        connection = next(
            (one for one in await self._connections() if one.connector == connector), None
        )
        if connection is None:
            return Ran.GONE
        report = await asyncio.to_thread(
            send_approved,
            suspension,
            connection=connection,
            keys=self._keys,
            caller=self._caller,
            resolver=self._resolver,
            clock=self._clock,
            reach=context.reach,
            agent_ceiling=context.agent_ceiling,
            policy=context.policy,
            leash=context.leash,
            assessment=context.assessment,
            trace_id=context.trace_id,
            ledger=context.ledger,
            declarations=self._declared,
        )
        return {
            WriteOutcome.DONE: Ran.DONE,
            WriteOutcome.FAILED: Ran.FAILED,
            WriteOutcome.NOT_ALLOWED: Ran.NOT_ALLOWED,
            WriteOutcome.NOT_SENT: Ran.REFUSED,
            WriteOutcome.ALREADY_SENT: Ran.ALREADY_RAN,
        }[report.outcome]


# ------------------------------------------------------------------ the worker's run
def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_approved_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> ApprovedRun:
    """`run_approved`, from a thread with no event loop of its own, with the worker's real parts.

    The shape `brain.ops.connector_sync_run.run_connector_sync_now` takes: the worker's vault for
    the write keys, the pinned HTTPS caller, and the operation ledger on its own autocommit
    connection, which is the once.
    """
    import psycopg

    from brain.db import libpq_conninfo
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.ops.connector_store import StoredConnections
    from brain.ops.connector_sync_run import HttpsSourceCaller, worker_connector_keys
    from brain.ops.operation_store import PostgresOperationLedger
    from brain.ops.webhook_delivery import SystemResolver
    from brain.session import make_app_engine, make_session_factory

    async def go() -> ApprovedRun:
        engine = make_app_engine(database_url)
        sessions = make_session_factory(engine)
        try:
            with psycopg.connect(
                libpq_conninfo(database_url), autocommit=True, prepare_threshold=None
            ) as conn:
                writes = ConnectorWrites(
                    connections=StoredConnections(sessions).connected,
                    keys=worker_connector_keys(vault_address, vault_token),
                    caller=HttpsSourceCaller(),
                    resolver=SystemResolver(),
                    clock=_utc_now,
                )
                return await run_approved(
                    sessions,
                    now=now,
                    executors=(writes,),
                    standings=StoredStandings(sessions),
                    reaches=StoredEntitlements(sessions),
                    ledger=PostgresOperationLedger(conn),
                )
        finally:
            await engine.dispose()

    return asyncio.run(go(), loop_factory=loop_factory)
