"""One agent's leash on its page: every entry's rung, every move with its evidence, and supervision.

`brain.agents.leash_moves` decides how a rung moves and `brain.agents.supervision` how a review
answers; `brain.ops.leash_store` keeps what they decide. The Profile drew the install's leash and a
Change control marked as coming, because nothing could move a rung. This is the route behind that
control, and it decides nothing those modules had not.

**A rung is moved by whoever holds the leash authority over the agent's department**, or over
everything for an agent no department owns, which is how the budget is set
(`brain.agent_workspace_routes.place_of`). Lowering needs nothing else; raising needs the evidence
`leash_moves.raising` counts, and across a money or irreversible boundary a second holder's press.
Anybody else is told which role moves a rung, and never whether the move would have been allowed.
See `MOVING_A_RUNG_IS_THE_DEPARTMENT_S_LEASH_ROLE`.

**A verdict on an action is the agent's steward's or a leash holder's**, and recording one asks the
breaker at once: when the share of the target's actions accepted unchanged since its rung was set
falls below the bar, the rung falls to the bottom in the same request, naming the metric. So the
breaker needs no schedule to run on.

**A review is pressed, and its outcome stored.** Not due is a refusal; due and short extends the
pin from now; due and at the bar makes the agent eligible, after which a raise is possible and a
person still makes it. An agent held by its pin is held on every read until a stored review says
eligible, which is the direction `brain.agents.supervision` says a fail-safe errs in.

**What the page is shown is `E_run`-free configuration**, behind the Settings tab's read as the
Profile is. Approvers are named only to a reader of the People screen, which is
`brain.console.govern_estate.approver_of`'s rule, applied here to every name on a move.

Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final, Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_routes import (
    _no_agent_here,
    _require_session_factory,
    _tool_registry,
    _visible_record,
    install_for,
    install_of,
    leash_of,
    may_read_settings,
    takeover_standings,
)
from brain.agent_workspace_routes import place_of
from brain.agents.leash_moves import (
    TAKEN_OVER,
    LeashMove,
    LeashMoveError,
    TakeoverDemotion,
    breaker_for,
    effective_leash,
    held_by_takeovers,
    held_while_supervised,
    history,
    lowering,
    newest_by_key,
    raising,
    record_since,
    rung_of,
    takeover_demotions,
    tripping,
)
from brain.agents.model import AgentRecord
from brain.agents.supervision import (
    ShadowOutcome,
    ShadowReview,
    SupervisionError,
    pin,
    review,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.audit.record import ApprovalVerdict
from brain.console.agent_profile import scope_sentence
from brain.console.govern_estate import PROMOTION_APPROVER_SCREEN
from brain.console.reads import permitted
from brain.console.scoped_authority import within_reach
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.abstain import TAKEOVER_DEMOTION_THRESHOLD, AutonomyBreaker
from brain.gate.injection import AutonomyTier
from brain.gate.leash import DIGEST, ActionRecord, Leash
from brain.ops.leash_store import LeashState, StoredLeash, simulated_only, state_in
from brain.tables.leash import PinOutcome
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Who moves a rung, and why that one.
MOVING_A_RUNG_IS_THE_DEPARTMENT_S_LEASH_ROLE: Final = (
    "A rung decides how much a person sees before an agent acts in a department, so it is moved "
    "by whoever holds the leash authority over that department, or over everything for an agent "
    "no department owns. Anybody else is told which role would let them, and never whether the "
    "move they asked for would have been allowed."
)

#: The sentence a caller without the role is told.
MOVING_A_RUNG_NEEDS_THE_LEASH_ROLE: Final = (
    "Changing how much a person sees before this agent acts needs the leash role for its "
    "department."
)

#: The sentence a caller who may not judge the agent's actions is told.
JUDGING_AN_ACTION_NEEDS_THE_STEWARD_OR_THE_LEASH_ROLE: Final = (
    "Saying what you would have done with this agent's action needs its steward or the leash "
    "role for its department."
)

NOT_DUE_YET: Final = "Its review is not due yet, so nothing can be decided about it."
ALREADY_SUPERVISED: Final = "It is already under supervision."
NOT_SUPERVISED: Final = "It is not under supervision, so there is nothing to review."
ALREADY_JUDGED: Final = "Somebody has already said what they would have done with that action."

#: The leash authority, over the agent's department.
LEASH_AUTHORITY: Final = Capability(value="admin:leash")

#: The reason code a move from the page is recorded with.
FROM_THE_AGENT_PAGE: Final = "set_on_the_agent_page"
TRIPPED_BY_A_VERDICT: Final = "tripped_by_a_verdict"

LEASH_PATH: Final = "/agents/{agent_id}/leash"
MOVES_PATH: Final = "/agents/{agent_id}/leash/moves"
PIN_PATH: Final = "/agents/{agent_id}/supervision/pin"
REVIEW_PATH: Final = "/agents/{agent_id}/supervision/review"
VERDICT_PATH: Final = "/agents/{agent_id}/supervision/verdicts"

RungName = Literal["shadow", "assisted", "autonomous"]
RUNG_BY_NAME: Final[dict[str, AutonomyTier]] = {one.name.lower(): one for one in AutonomyTier}


# ------------------------------------------------------------------------------ the views
class LeashEntryView(BaseModel):
    """One entry of the leash as it now stands: a target, where it applies, and its rung."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    scope: Scope
    #: The scope in words, or empty for an entry that applies everywhere.
    where: str
    rung: str
    #: Whether a proposal to raise it waits for a second person.
    proposed: str | None = None
    #: The rung the autonomy breaker holds it to while people keep taking its work over, when
    #: lower than `rung`. The lower one binds, by `leash_moves`'
    #: `A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS`.
    lowered_to: str | None = None


class LeashMoveView(BaseModel):
    """One move of one rung, with its evidence (M39.3.2.5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    where: str
    kind: str
    was: str
    became: str
    at: datetime
    #: Named only to a reader of the People screen; empty otherwise and for a fall.
    approver: str
    second_approver: str
    clean_runs: int | None
    agreement_rate: float | None
    metric: str
    measured: float | None
    threshold: float | None
    #: For a takeover demotion: how many takeovers inside the week hold it down. `threshold` is
    #: then how many lower a rung.
    takeovers: int | None = None


class SupervisionView(BaseModel):
    """The pin as it stands and what its latest review found (M39.8.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pinned_at: datetime
    review_due_at: datetime
    outcome: str
    understood: int | None
    reviewed: int | None
    simulated: int | None
    #: Whether its rungs are held at the bottom now.
    held: bool
    due: bool


class AwaitingView(BaseModel):
    """One action nobody has said anything about yet. Names and digests, no values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_digest: str
    target: str
    route: str
    at: datetime


class AgentLeashView(BaseModel):
    """The leash block of the Profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    entries: list[LeashEntryView]
    history: list[LeashMoveView]
    supervision: SupervisionView | None
    awaiting: list[AwaitingView]
    may_move: bool
    may_judge: bool


class MoveAsked(BaseModel):
    """A rung asked for, on one target and where it applies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str = Field(
        min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"
    )
    scope: Scope = Field(default_factory=Scope.unrestricted)
    to: RungName


class MoveDoneView(BaseModel):
    """What a press did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    kind: str
    was: str
    became: str


class VerdictAsked(BaseModel):
    """What a person would have done with one action."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_digest: str = Field(pattern=DIGEST)
    verdict: ApprovalVerdict


class VerdictDoneView(BaseModel):
    """A verdict kept, and the rung it tripped, if it tripped one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_digest: str
    tripped: list[str]


class SupervisionDoneView(BaseModel):
    """A pin written or a review recorded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: str
    review_due_at: datetime


# ------------------------------------------------------------------------- the decisions
def may_move_leash(reach: EntitlementSet, record: AgentRecord, now: datetime) -> bool:
    """Whether this reach may move this agent's rungs. See the reason above."""
    return within_reach(reach, LEASH_AUTHORITY, place_of(record), now)


def may_judge(reach: EntitlementSet, record: AgentRecord, now: datetime) -> bool:
    """Whether this reach may say what they would have done with the agent's actions."""
    return reach.principal_id == record.audience.owner_id or may_move_leash(reach, record, now)


def effect_of(target: str, registry: ToolRegistry | None) -> SideEffect:
    """The side effect of the tool a target names, or money when nothing registered says."""
    if registry is not None:
        for one in registry.definitions():
            if one.name == target:
                return one.side_effect
    return SideEffect.MONEY


def leash_now(configured: Leash, state: LeashState, agent_id: str) -> Leash:
    """The leash a run of this agent is governed by: the moves, then the supervision hold."""
    return held_while_supervised(
        effective_leash(configured, state.moves),
        agent_id,
        None if state.pin is None else state.pin.outcome,
    )


def _rung(tier: AutonomyTier) -> str:
    return tier.name.lower()


def _where(scope: Scope) -> str:
    return "" if scope.is_unrestricted() else scope_sentence(scope)


def entry_views(
    leash: Leash,
    state: LeashState,
    agent_id: str,
    standings: Mapping[str, AutonomyBreaker],
    now: datetime,
) -> list[LeashEntryView]:
    newest = newest_by_key(state.moves)
    return [
        LeashEntryView(
            target=entry.target,
            scope=entry.scope,
            where=_where(entry.scope),
            rung=_rung(entry.rung),
            proposed=(
                _rung(move.became)
                if (move := newest.get((entry.agent_id, entry.target, entry.scope))) is not None
                and not move.moves_the_rung
                else None
            ),
            lowered_to=None and (
                _rung(held)
                if (held := held_by_takeovers(entry.rung, standings.get(entry.target), now))
                is not None
                else None
            ),
        )
        for entry in sorted(
            leash.entries, key=lambda one: (one.target, one.scope.model_dump_json())
        )
        if entry.agent_id == agent_id
    ]


def move_view(move: LeashMove, *, names: bool) -> LeashMoveView:
    promotion, trip = move.promotion, move.trip
    return LeashMoveView(
        target=move.target,
        where=_where(move.scope),
        kind=move.kind.value,
        was=_rung(move.was),
        became=_rung(move.became),
        at=move.at,
        approver="" if promotion is None or not names else promotion.approver_id,
        second_approver="" if promotion is None or not names else promotion.second_approver_id,
        clean_runs=None if promotion is None else promotion.clean_runs,
        agreement_rate=None if promotion is None else promotion.agreement_rate,
        metric="" if trip is None else trip.metric,
        measured=None if trip is None else trip.measured,
        threshold=None if trip is None else trip.threshold,
    )


def demotion_view(one: TakeoverDemotion) -> LeashMoveView:
    """A takeover demotion as a row of the history: when, how many, and nobody named."""
    return LeashMoveView(
        target=one.target,
        where="",
        kind=TAKEN_OVER,
        was=_rung(one.was),
        became=_rung(one.became),
        at=one.at,
        approver="",
        second_approver="",
        clean_runs=None,
        agreement_rate=None,
        metric="",
        measured=None,
        threshold=TAKEOVER_DEMOTION_THRESHOLD,
        takeovers=one.takeovers,
    )


def history_views(
    leash: Leash,
    state: LeashState,
    agent_id: str,
    standings: Mapping[str, AutonomyBreaker],
    now: datetime,
    *,
    names: bool,
) -> list[LeashMoveView]:
    """Every stored move and every takeover demotion standing now, oldest first.

    See `brain.agents.leash_moves`'
    `A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS`.
    """
    rows = [move_view(one, names=names) for one in history(state.moves)]
    rows += [demotion_view(one) for one in takeover_demotions(leash, agent_id, standings, now)]
    return sorted(rows, key=lambda one: (one.at, one.target, one.kind))


def supervision_view(state: LeashState, now: datetime) -> SupervisionView | None:
    if state.pin is None:
        return None
    one = state.pin
    return SupervisionView(
        pinned_at=one.pin.pinned_at,
        review_due_at=one.pin.review_due_at,
        outcome=one.outcome.value,
        understood=one.understood,
        reviewed=one.reviewed,
        simulated=one.simulated,
        held=one.outcome is not PinOutcome.ELIGIBLE,
        due=one.pin.is_due(now),
    )


def awaiting_views(state: LeashState) -> list[AwaitingView]:
    judged = {one.action_digest for one in state.verdicts}
    return [
        AwaitingView(
            action_digest=one.action_digest, target=one.target, route=one.route.value, at=one.at
        )
        for one in state.actions
        if one.action_digest not in judged
    ]


def reviewed_in_window(state: LeashState) -> tuple[list[ShadowReview], list[ActionRecord]]:
    """The simulated actions a review counts and the verdicts on them, as the domain takes them.

    A verdict on an action that was not simulated in the pin's window is left out rather than
    handed to `measure`, which refuses one: an action approved at Assisted is evidence for a
    raise, and not about a shadow period.
    """
    if state.pin is None:
        return [], []
    simulated = [one for one in simulated_only(state.actions) if one.at >= state.pin.pin.pinned_at]
    when = {one.action_digest: one.at for one in simulated}
    verdicts = [
        one
        for one in state.verdicts
        if one.action_digest in when and one.at >= when[one.action_digest]
    ]
    return verdicts, simulated


# --------------------------------------------------------------------------- the reads
async def _loaded(
    request: Request, agent_id: str, asked: Asking
) -> tuple[AgentRecord, Leash, LeashState, ToolRegistry | None]:
    factory = _require_session_factory(request)
    registry = _tool_registry(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_settings(asked):
            log.info("agent leash not answerable", principal=asked.caller.principal.id)
            raise _no_agent_here()
        pair = (await session.execute(install_for(agent_id))).one_or_none()
        state = await state_in(session, agent_id)
    install = install_of(pair[0], pair[1], record) if pair is not None else None
    return record, leash_of(install, registry), state, registry


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(LEASH_PATH, response_model=AgentLeashView, responses=COMMON_RESPONSES)
async def agent_leash(request: Request, agent_id: str, asked: Asked) -> AgentLeashView:
    """The leash as it stands, every move with its evidence, and supervision (M39.3.2)."""
    record, configured, state, _ = await _loaded(request, agent_id, asked)
    names = permitted(screen(PROMOTION_APPROVER_SCREEN).read, asked.reach, asked.now)
    judge = may_judge(asked.reach, record, asked.now)
    leash = leash_now(configured, state, agent_id)
    targets = sorted({one.target for one in leash.entries if one.agent_id == agent_id})
    standings = await takeover_standings(request, agent_id, targets, asked.now)
    return AgentLeashView(
        agent_id=agent_id,
        entries=entry_views(leash, state, agent_id, standings, asked.now),
        history=history_views(leash, state, agent_id, standings, asked.now, names=names),
        supervision=supervision_view(state, asked.now),
        awaiting=awaiting_views(state) if judge else [],
        may_move=may_move_leash(asked.reach, record, asked.now),
        may_judge=judge,
    )


def _refused(message: str, status: int = 409) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message})


@router.post(MOVES_PATH, response_model=MoveDoneView, responses=COMMON_RESPONSES)
async def move_agent_rung(
    request: Request, agent_id: str, body: MoveAsked, asked: Asked
) -> JSONResponse | MoveDoneView:
    """Lower a rung at once, or press to raise one on evidence (M39.3.2.2, M39.3.2.4)."""
    record, configured, state, registry = await _loaded(request, agent_id, asked)
    if not may_move_leash(asked.reach, record, asked.now):
        return _refused(MOVING_A_RUNG_NEEDS_THE_LEASH_ROLE, 403)
    leash = effective_leash(configured, state.moves)
    to = RUNG_BY_NAME[body.to]
    by = asked.caller.principal.id
    key = (agent_id, body.target, body.scope)
    newest = newest_by_key(state.moves).get(key)
    try:
        if to < rung_of(leash, agent_id, body.target, body.scope):
            move = lowering(
                leash,
                agent_id=agent_id,
                target=body.target,
                scope=body.scope,
                to=to,
                by=by,
                at=asked.now,
            )
        else:
            move = raising(
                leash,
                agent_id=agent_id,
                target=body.target,
                scope=body.scope,
                to=to,
                by=by,
                at=asked.now,
                effect=effect_of(body.target, registry),
                record=record_since(
                    agent_id,
                    body.target,
                    actions=state.actions,
                    verdicts=state.verdicts,
                    since=None if newest is None or not newest.moves_the_rung else newest.at,
                ),
                pending=newest,
                supervision=None if state.pin is None else state.pin.outcome,
            )
    except LeashMoveError as refused:
        return _refused(str(refused))
    await StoredLeash(_require_session_factory(request)).move(
        move,
        reason_code=FROM_THE_AGENT_PAGE,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    return MoveDoneView(
        target=move.target, kind=move.kind.value, was=_rung(move.was), became=_rung(move.became)
    )


@router.post(VERDICT_PATH, response_model=VerdictDoneView, responses=COMMON_RESPONSES)
async def judge_agent_action(
    request: Request, agent_id: str, body: VerdictAsked, asked: Asked
) -> JSONResponse | VerdictDoneView:
    """Say what you would have done with one action, and let the breaker look (M39.3.2.3)."""
    record, configured, state, _ = await _loaded(request, agent_id, asked)
    if not may_judge(asked.reach, record, asked.now):
        return _refused(JUDGING_AN_ACTION_NEEDS_THE_STEWARD_OR_THE_LEASH_ROLE, 403)
    action = next((one for one in state.actions if one.action_digest == body.action_digest), None)
    if action is None:
        raise _no_agent_here()
    by = asked.caller.principal.id
    store = StoredLeash(_require_session_factory(request))
    kept = await store.give_verdict(
        ShadowReview(
            agent_id=agent_id,
            action_digest=body.action_digest,
            verdict=body.verdict,
            reviewer_id=by,
            at=asked.now,
        )
    )
    if not kept:
        return _refused(ALREADY_JUDGED)
    after = await store.state(agent_id)
    leash = leash_now(configured, after, agent_id)
    newest = newest_by_key(after.moves)
    tripped: list[str] = []
    for entry in leash.entries:
        if entry.agent_id != agent_id or entry.target != action.target:
            continue
        last = newest.get((agent_id, entry.target, entry.scope))
        record_now = record_since(
            agent_id,
            entry.target,
            actions=after.actions,
            verdicts=after.verdicts,
            since=None if last is None or not last.moves_the_rung else last.at,
        )
        trip = breaker_for(entry.rung, record_now, at=asked.now)
        if trip is None:
            continue
        await store.move(
            tripping(
                leash,
                agent_id=agent_id,
                target=entry.target,
                scope=entry.scope,
                trip=trip,
                by=by,
            ),
            reason_code=TRIPPED_BY_A_VERDICT,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_of_request(),
        )
        tripped.append(entry.target)
    return VerdictDoneView(action_digest=body.action_digest, tripped=tripped)


@router.post(PIN_PATH, response_model=SupervisionDoneView, responses=COMMON_RESPONSES)
async def pin_agent(
    request: Request, agent_id: str, asked: Asked
) -> JSONResponse | SupervisionDoneView:
    """Put the agent under supervision from now, its first review thirty days out (M39.8.2)."""
    record, _, state, _ = await _loaded(request, agent_id, asked)
    if not may_move_leash(asked.reach, record, asked.now):
        return _refused(MOVING_A_RUNG_NEEDS_THE_LEASH_ROLE, 403)
    if state.pin is not None and state.pin.outcome is not PinOutcome.ELIGIBLE:
        return _refused(ALREADY_SUPERVISED)
    started = pin(agent_id, now=asked.now)
    await StoredLeash(_require_session_factory(request)).write_pin(
        started,
        PinOutcome.PINNED,
        by=asked.caller.principal.id,
        counts=None,
        at=asked.now,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    return SupervisionDoneView(outcome=PinOutcome.PINNED.value, review_due_at=started.review_due_at)


@router.post(REVIEW_PATH, response_model=SupervisionDoneView, responses=COMMON_RESPONSES)
async def review_agent(
    request: Request, agent_id: str, asked: Asked
) -> JSONResponse | SupervisionDoneView:
    """Ask the thirty-day question and keep the answer (M39.8.2)."""
    record, _, state, _ = await _loaded(request, agent_id, asked)
    if not may_move_leash(asked.reach, record, asked.now):
        return _refused(MOVING_A_RUNG_NEEDS_THE_LEASH_ROLE, 403)
    if state.pin is None or state.pin.outcome is PinOutcome.ELIGIBLE:
        return _refused(NOT_SUPERVISED)
    verdicts, simulated = reviewed_in_window(state)
    try:
        decision = review(
            state.pin.pin,
            simulated=simulated,
            reviews=verdicts,
            now=asked.now,
        )
    except SupervisionError:
        log.warning("supervision review refused its evidence", agent=agent_id)
        return _refused(NOT_DUE_YET)
    if decision.outcome is ShadowOutcome.NOT_YET_DUE:
        return _refused(NOT_DUE_YET)
    outcome = (
        PinOutcome.EXTENDED if decision.outcome is ShadowOutcome.EXTENDED else PinOutcome.ELIGIBLE
    )
    found = decision.confidence
    await StoredLeash(_require_session_factory(request)).write_pin(
        decision.pin,
        outcome,
        by=asked.caller.principal.id,
        counts=(found.understood, found.reviewed, found.simulated),
        at=asked.now,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    return SupervisionDoneView(outcome=outcome.value, review_due_at=decision.pin.review_due_at)
