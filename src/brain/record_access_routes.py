"""Who can see a record, shown only to somebody who can already see it (M1.9.1).

The owner decided on 2026-09-18 to have a record access view, on one condition: it opens only
for someone who can already see the record. The console architecture had declined the view
because answering "who can see this invoice" confirms the invoice exists to anybody allowed to
ask; the condition closes exactly that, since a reader who sees the record already knows it
exists.

**Seeing the record is decided by reading it, never by a rule of this module.** The record is
asked for through the entity's own row tool at the caller's reach, the path `GET /records/{entity}`
takes, and a caller for whom it does not come back is answered with the sentence an unknown
entity gets. Each candidate is asked the same way: the same tool, the same filter, at that
person's resolved reach. So "can see" has one answer, the query compiler's, and there is no
second implementation of the row scope here to drift from it.

**The answer is a list of people, so it is also the People screen's disclosure.** A reader must
hold the People screen's read, and names are narrowed by `brain.console.govern.people_shown`
over where each person sits. Rejected: listing everybody who reaches the record to any reader of
it. That is a directory of other people's grants handed to whoever can open a row, which the
People screen's grant exists to govern. No count of anybody left out, and `truncated` says only
that the candidate load came back full.

Task ids: M1.9.1
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import FILTER_PARAM, MAX_FILTERS, Asked, FilterTerm, filter_scope, wiring_of
from brain.console.govern import Placed, people_shown
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.core.field_policy import FieldPolicy
from brain.core.redaction import require_typed_result, serialise_for_channel
from brain.core.scope import Scope
from brain.govern_routes import PEOPLE_SCREEN
from brain.knowledge.rows import RowRequest, row_scope_for
from brain.routing_routes import sessions_of
from brain.tables.identity import PrincipalRow
from brain.tools.registry import ToolRegistry
from brain.tools.startup import classification_for

log = structlog.get_logger()

#: How many people one view asks about. Each is one read through the row tool, so this bounds
#: the work one request can cause rather than what anybody may see.
MAX_CANDIDATES: Final = 200


class PersonWhoSees(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str


class RecordAudience(BaseModel):
    """The people who can see the one record the filter names, as this reader may be told."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    people: tuple[PersonWhoSees, ...]
    #: The candidate load came back full. Never how many more.
    truncated: bool = False


def live_people(limit: int) -> Select[tuple[str, str, str | None]]:
    """Every live, enabled principal: id, name, department."""
    return (
        select(PrincipalRow.id, PrincipalRow.display_name, PrincipalRow.primary_department)
        .where(PrincipalRow.deleted_at.is_(None), PrincipalRow.disabled_at.is_(None))
        .order_by(PrincipalRow.id)
        .limit(limit)
    )


def _not_answerable(entity: str) -> Absent:
    """The records route's sentence, so this view cannot tell an entity apart from a refusal."""
    return Absent(f"{entity!r} is not answerable for this caller")


async def _rows_seen(
    registry: ToolRegistry,
    tool: str,
    narrowing: Scope,
    reach: EntitlementSet,
    policy: FieldPolicy,
    now: datetime,
    limit: int,
) -> int:
    """How many rows this reach would be shown: the entity's own tool, then the redactor.

    Both enforcement points the records route uses, so a row the query let through and the
    redactor drops is not a row this person sees.
    """
    handler = registry.get(tool).handler
    answered = handler(RowRequest(filters=narrowing, limit=limit), entitlement=reach, now=now)
    raw = await answered if inspect.isawaitable(answered) else answered
    shown = serialise_for_channel(
        require_typed_result(raw), entitlement=reach, policy=policy, now=now
    )
    return len(shown.records)


router = APIRouter(prefix=API_PREFIX, tags=["gate"])


@router.get("/records/{entity}/access", response_model=RecordAudience, responses=COMMON_RESPONSES)
async def record_access(
    request: Request,
    entity: str,
    asked: Asked,
    filters: Annotated[
        tuple[FilterTerm, ...], Query(alias=FILTER_PARAM, min_length=1, max_length=MAX_FILTERS)
    ],
) -> RecordAudience:
    """Who can see the one record this filter names, if the caller can see it themselves.

    The People screen's read first, before anything is looked at. Then the record at the
    caller's own reach: it must come back, and exactly once, or the filter does not name one
    record and the answer is the records route's refusal. Then each candidate through the same
    tool at their own reach.
    """
    if not permitted(screen(PEOPLE_SCREEN).read, asked.reach, asked.now):
        raise _not_answerable(entity)
    narrowing = filter_scope(filters)
    registry = getattr(request.app.state, "tools", None)
    wiring = wiring_of(request)
    if not isinstance(registry, ToolRegistry) or wiring is None:
        raise Failed("no tool registry or gate wiring on this process")
    matching = [d for d in registry.definitions() if d.entity == entity]
    classification = classification_for(entity)
    reaches = row_scope_for(entity, asked.reach, asked.now) is not None
    if classification is None or len(matching) != 1 or not reaches:
        raise _not_answerable(entity)
    tool, policy = matching[0].name, classification.policy()

    try:
        if await _rows_seen(registry, tool, narrowing, asked.reach, policy, asked.now, 2) != 1:
            raise _not_answerable(entity)
        factory = sessions_of(request)
        if factory is None:
            raise Failed("no database on this process")
        async with factory() as session:
            candidates = (await session.execute(live_people(MAX_CANDIDATES + 1))).all()
        shown = people_shown(
            [
                Placed(record=(pid, name), where={} if dept is None else {"department": dept})
                for pid, name, dept in candidates[:MAX_CANDIDATES]
            ],
            asked.reach,
            asked.now,
        )
        seeing: list[PersonWhoSees] = []
        for one in shown:
            pid, name = one.record
            reach = await wiring.store.load(pid, asked.now)
            if row_scope_for(entity, reach, asked.now) is None:
                continue
            if await _rows_seen(registry, tool, narrowing, reach, policy, asked.now, 1):
                seeing.append(PersonWhoSees(principal_id=pid, display_name=name))
    except BrainError:
        raise
    except Exception as exc:
        # Whatever a driver raises becomes a refusal-shaped fault, as on the records route.
        raise Failed(f"reading who sees {entity}: {type(exc).__name__}") from exc
    return RecordAudience(people=tuple(seeing), truncated=len(candidates) > MAX_CANDIDATES)
