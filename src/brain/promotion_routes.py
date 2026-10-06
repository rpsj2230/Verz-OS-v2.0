"""The press that promotes a learned fast-lane rule, behind an agent's Memory tab (M39.4.2.3).

`brain.memory.promotion` argues every rule and `brain.memory.promotion_store` holds the session.
This is the address the console presses: `POST /learning/{memory_id}/promote`.

**Who may press is who may undo a learning where the rule would answer.** `admin:learning` at the
rule's department, or over everything for a rule the whole install asks with, asked through
`brain.console.govern._in_reach`, the narrowing every governance surface asks. A rule this person
may not press, and one that does not exist, are the same 404 in the same words, so the route is not
a way to ask which rules were learned in another department.

**Ready is counted, not claimed.** Whether enough separate conversations would have used the rule
is `tiers.may_promote` over the occurrences the database holds, at the agreement an administrator
saved on the Learning screen (`brain.ops.tuning.promotion_agreement`), worked out here on every
press. Nothing the console sends says the rule is ready.

**Whether it takes two people is worked out from the rule as it answers now.** The entity's
declared money (`brain.resolution.sources.resolved_entities`) and the answering column's
classification, read through the same wiring the answer route and the rule screen's trial use
(`brain.rule_routes.lane_wiring_of`). See
`brain.memory.promotion.A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE`.

Task ids: M39.4.2.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, RequestProblemView
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.audit.ledger import IDENTIFIER
from brain.console.govern import NOWHERE, _in_reach
from brain.console.govern_estate import UNDO_AUTHORITY
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.field_policy import Classification, FieldPolicy
from brain.memory.promotion import LearnedRule, PromotionRefusedError, needs_two
from brain.memory.promotion_store import StoredLearnedRules
from brain.memory.tiers import Change, may_promote, propose
from brain.ops.classification_store import Writer
from brain.tables.learning import MEMORY_ID_CHARS

log = structlog.get_logger(__name__)

router = APIRouter(prefix=API_PREFIX, tags=["learning"])

PROMOTE_PATH: Final = "/learning/{memory_id}/promote"

#: The one refusal for a learned rule this person may not press and one that does not exist.
NO_SUCH_RULE: Final = "There is no learned rule by that name that you may promote."

#: A memory id, in the ledger's identifier grammar and `mem.learning`'s width.
_ID = Path(min_length=1, max_length=MEMORY_ID_CHARS, pattern=IDENTIFIER)


class PromotionPressedView(BaseModel):
    """What one press came to: where the rule stands, whether it takes two people, and words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str
    state: str
    needs_two: bool
    said: str


def _store(request: Request) -> StoredLearnedRules:
    sessions = getattr(request.app.state, "db_sessions", None)
    if not isinstance(sessions, async_sessionmaker):
        raise Failed("no database on this process")
    return StoredLearnedRules(sessions)


def may_promote_where(reader: EntitlementSet, department: str | None, now: datetime) -> bool:
    """Whether this reader may press a learned rule that would answer at this place."""
    where = NOWHERE if department is None else {"department": department}
    return _in_reach(reader, UNDO_AUTHORITY, where, now)


def answering_classification(
    learned: LearnedRule,
    policies: dict[str, FieldPolicy],
    source_policies: dict[tuple[str, str], FieldPolicy],
) -> Classification | None:
    """How the column a rule answers with is classified, by its own source's policy first."""
    rule = learned.rule
    policy = source_policies.get((rule.source, rule.entity)) or policies.get(rule.entity)
    found = None if policy is None else policy.rule_for(rule.entity, rule.answer_field)
    return None if found is None else found.classification


def carries_money(learned: LearnedRule) -> bool:
    """Whether the rule's connector declares the entity it answers from as carrying money."""
    from brain.resolution.sources import resolved_entities

    declared = resolved_entities().get((learned.rule.source, learned.rule.entity))
    return bool(declared is not None and declared.carries_money)


async def takes_two(state: Any, learned: LearnedRule) -> bool:
    """`promotion.needs_two` for this rule as it answers now."""
    from brain.rule_routes import lane_wiring_of

    _, policies, source_policies = await lane_wiring_of(state)
    return needs_two(
        carries_money=carries_money(learned),
        answering=answering_classification(learned, policies, source_policies),
    )


def refused(message: str) -> JSONResponse:
    told = ErrorBody(
        message=message,
        problems=[RequestProblemView(field="memory_id", code="not_promoted", message=message)],
    )
    return JSONResponse(status_code=409, content=told.model_dump(mode="json"))


@router.post(
    PROMOTE_PATH,
    response_model=PromotionPressedView,
    responses={**COMMON_RESPONSES, 409: {"model": ErrorBody}},
)
async def promote_learned_rule(
    request: Request, asked: Asked, memory_id: Annotated[str, _ID]
) -> PromotionPressedView | JSONResponse:
    """Press to promote one learned rule: the first of two presses, or the one that applies it."""
    from brain.ops.tuning import promotion_agreement

    store = _store(request)
    learned = await store.learned(memory_id)
    if learned is None or not may_promote_where(asked.reach, learned.department, asked.now):
        raise Absent(NO_SUCH_RULE)
    seen = (await store.occurrences((memory_id,))).get(memory_id, ())
    ready = may_promote(
        propose(Change.FAST_PATH_RULE, subject=memory_id),
        list(seen),
        now=asked.now,
        agreement=promotion_agreement(),
    )
    two = await takes_two(request.app.state, learned)
    writer = Writer(
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request() or f"promotion.{memory_id}",
    )
    try:
        pressed = await store.promote(memory_id, writer=writer, ready=ready, two=two, now=asked.now)
    except PromotionRefusedError as exc:
        return refused(str(exc))
    log.info(
        "learning.rule_pressed",
        principal=writer.actor_id,
        memory=memory_id,
        state=pressed.state.value,
    )
    return PromotionPressedView(
        memory_id=memory_id,
        state=pressed.state.value,
        needs_two=pressed.needs_two,
        said=pressed.said,
    )
