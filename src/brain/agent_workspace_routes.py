"""An agent's own monthly budget, set from its page so its month-end projection has a ceiling.

`brain.console.workspace.projection` projects an agent's month against its own budget and has
done since M39.1.3.4 was written, and `brain.console_stats_routes` now sends that projection to a
reader of everybody's spend. Nothing on an install wrote an agent's budget: `brain.ops.budgets.
agent_ceilings` builds a per-run and a per-day row and no route called it, so every agent had no
ceiling and the projection could never be drawn. This is the one write that closes that, and it
adds no rule of its own about money.

**A month ceiling, appended as the next version.** `brain.ops.budget_store.append` is the only verb
the table has, and a change is `BudgetRow.superseded_by`, so every ceiling an agent ever had stays
readable and `0098`'s trigger ledgers the version with this request's actor, reach and trace.
Rejected: a per-day ceiling multiplied out to a month, which is a figure nobody set, and a
projection read against it would be a projection against a guess.

**Who may set it is the budget administrator over the agent's department.** `admin:budget` is the
authority `brain.ops.budget_stop` warns and escalates to, held with a scope, so it is asked with
`brain.console.scoped_authority.within_reach` over the department the agent's audience names, or
over everything for an agent no department owns. See `AN_AGENTS_BUDGET_IS_ITS_DEPARTMENT_S_TO_SET`.

**An agent the caller may not see is the 404 an agent that does not exist gets**, through
`brain.agent_routes._visible_record`, before anything about its money is read. A caller who may see
it and may not set its budget is told which role would let them, which names a role and never a
figure: `brain.ops.spend.A_REFUSAL_CARRIES_NO_FIGURE`.

Task ids: M39.1.3.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from brain.agent_routes import _require_session_factory, _visible_record
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.console.scoped_authority import within_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Scope
from brain.ops.budget_store import append, in_force
from brain.ops.budgets import BudgetError, BudgetLevel, BudgetPeriod, BudgetRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the department's budget administrator sets an agent's budget and nobody else does.
AN_AGENTS_BUDGET_IS_ITS_DEPARTMENT_S_TO_SET: Final = (
    "An agent's ceiling narrows everybody who runs it and is paid for out of its department's "
    "money, so it is set by whoever holds the budget authority over that department, or over "
    "everything for an agent no department owns. Holding it over another department, or holding "
    "only the budget screen's read, sets nothing."
)

#: The sentence a caller who may see the agent and may not set its budget is told.
SETTING_A_BUDGET_NEEDS_THE_BUDGET_ROLE: Final = (
    "Setting this agent's monthly budget needs the budget administrator's role over its department."
)

#: The sentence a second write in the same instant is answered with.
A_BUDGET_CHANGED_JUST_NOW: Final = "This budget changed a moment ago. Load the page again."

# ------------------------------------------------------------------------ the figures
#: The authority a budget is set with. `brain.ops.budget_stop.BUDGET_AUTHORITY`, restated as a
#: value so this module does not import the stop's machinery; a test holds the two equal.
BUDGET_AUTHORITY: Final[Capability] = Capability(value="admin:budget")

#: The largest monthly ceiling accepted, in minor units: a thousand million, which no agent's
#: month approaches and which keeps a typing slip from reading as a real ceiling.
MAX_CEILING_MINOR: Final = 1_000_000_000

BUDGET_PATH: Final = "/agents/{agent_id}/budget"


class BudgetAsked(BaseModel):
    """A new monthly ceiling for one agent, in the install's minor units, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ceiling_minor: Annotated[int, Field(ge=1, le=MAX_CEILING_MINOR)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class BudgetView(BaseModel):
    """The agent's monthly ceiling as it now stands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    ceiling_minor: int
    version: int
    effective_from: datetime


def place_of(record: AgentRecord) -> Scope:
    """Where an agent's money is decided: its department, or everything for none."""
    department = record.audience.department
    return Scope.department(department) if department else Scope.unrestricted()


def may_set_budget(reach: EntitlementSet, record: AgentRecord, now: datetime) -> bool:
    """Whether this reach may set this agent's monthly budget. See the reason above."""
    return within_reach(reach, BUDGET_AUTHORITY, place_of(record), now)


def next_version(
    current: BudgetRow | None,
    *,
    agent_id: str,
    ceiling_minor: int,
    author: str,
    reason: str,
    now: datetime,
) -> BudgetRow:
    """The agent's next monthly ceiling: version one, or the one in force superseded."""
    if current is None:
        return BudgetRow(
            level=BudgetLevel.AGENT,
            subject=agent_id,
            period=BudgetPeriod.MONTH,
            ceiling_minor=ceiling_minor,
            version=1,
            author=author,
            effective_from=now,
            reason=reason,
        )
    return current.superseded_by(
        ceiling_minor=ceiling_minor, author=author, effective_from=now, reason=reason
    )


async def write_budget(
    session: AsyncSession,
    *,
    agent_id: str,
    ceiling_minor: int,
    reason: str,
    author: str,
    ent_hash: str,
    trace_id: str,
    now: datetime,
) -> BudgetRow | None:
    """Append the agent's next monthly ceiling in this session's transaction, or None.

    None when the ceiling in force took effect no earlier than `now`, which is a second write in
    the same instant: `superseded_by` refuses it rather than leaving two versions that cannot be
    ordered. Does not commit, for `brain.ops.budget_store.append`'s reason.
    """
    current = await in_force(session, (BudgetLevel.AGENT, agent_id, BudgetPeriod.MONTH), now)
    try:
        row = next_version(
            current,
            agent_id=agent_id,
            ceiling_minor=ceiling_minor,
            author=author,
            reason=reason,
            now=now,
        )
    except BudgetError:
        return None
    await append(session, row, ent_hash=ent_hash, trace_id=trace_id)
    return row


def _refused(message: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"message": message})


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.put(BUDGET_PATH, response_model=BudgetView, responses=COMMON_RESPONSES)
async def set_agent_budget(
    request: Request, agent_id: str, body: BudgetAsked, asked: Asked
) -> JSONResponse | BudgetView:
    """Set the agent's monthly ceiling. See the module docstring."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_set_budget(asked.reach, record, asked.now):
            log.info("agent budget refused", principal=asked.caller.principal.id)
            return _refused(SETTING_A_BUDGET_NEEDS_THE_BUDGET_ROLE)
        row = await write_budget(
            session,
            agent_id=agent_id,
            ceiling_minor=body.ceiling_minor,
            reason=body.reason,
            author=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_of_request(),
            now=asked.now,
        )
        if row is None:
            await session.rollback()
            return JSONResponse(status_code=409, content={"message": A_BUDGET_CHANGED_JUST_NOW})
        await session.commit()
    log.info("agent budget set", agent=agent_id, principal=asked.caller.principal.id)
    return BudgetView(
        agent_id=agent_id,
        ceiling_minor=row.ceiling_minor,
        version=row.version,
        effective_from=row.effective_from,
    )
