"""Install checks for a coordinating agent: who it may call, whether it may fan out, and a run.

Each check calls the functions the console's routes call, as the reader that page serves, over the
check's own transaction, and reads the answer back from the tables that keep it. **Every row written
is in the transaction the run rolls back, for reserved people of acceptance_a and acceptance_b, and
nothing reaches a person.**

**The first check proves the configuration against a real database.** An administrator of the
agent's department allows it to call a second agent and lets it fan out; its steward is told who it
may call and may change nothing; a colleague who answers for nothing is sent the same body before
and after, so a coordinator with specialists reads like one without; and an agent nobody can see,
itself and a personal agent are each refused in a sentence. The rows are read back with the person
who wrote them, and a withdrawn link stays with who withdrew it.

**The second check proves the engine against real agents.** Five agents are installed from signed
templates, so their ceilings are the ones the product compiles. The specialists are a script (a
model would be the install's own provider, and a person proves that); everything else is the
product's: the allow-list, the loading of each agent as the asker meets it, the plan read by
`read_plan`, the gate, the caps, the global budget, the merge and the kept rows. It shows that a
specialist is handed the intersection of the asker, the coordinator and itself and nothing wider;
that specialists run one after another until fan-out is granted and together after, with the
reason kept; that a specialist nobody allowed is refused with nothing started; that a result which
breaks its contract is stated as missing; and that what is kept names no request.

**Not claimed:** a model splitting a real request and real specialists answering it. That needs the
install's provider and a person watching, and it is the person-run leaf M18.6.1.

Task ids: M18.1.2, M18.1.4, M18.3.4, M18.3.5, M18.5.1, M18.5.2, M18.5.3, M18.6.2, M18.7.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_agent_console import (
    _asking,
    _console,
    _readers,
    _request,
    a_department_administrator,
)
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2680

A, B = RESERVED_DEPARTMENTS

#: The three columns of one made-up record the check's people and agents hold in different mixes.
TITLE: Final = "read:coordcheck.title"
BODY: Final = "read:coordcheck.body"
OWNER: Final = "read:coordcheck.owner"

NOT_TOLD_TO_THE_ADMINISTRATOR: Final = (
    "an administrator was not told which agents a coordinator may call"
)
NOT_ALLOWED: Final = "an administrator could not allow an agent to call two others"
A_COLLEAGUE_WAS_TOLD: Final = (
    "a colleague who answers for nothing was told who a coordinator may call"
)
A_COLLEAGUE_READ_IT_APART: Final = "a colleague read a coordinator with specialists differently"
A_STEWARD_WAS_NOT_TOLD: Final = "an agent's steward was not told who it may call"
A_STEWARD_CHANGED_IT: Final = "an agent's steward, who holds no authority, changed who it may call"
A_COLLEAGUE_CHANGED_IT: Final = "a colleague who holds no authority changed who an agent may call"
ITSELF_WAS_ALLOWED: Final = "an agent was allowed to call itself"
AN_UNSEEN_AGENT_WAS_ALLOWED: Final = "an agent the administrator cannot see was allowed as a callee"
A_PERSONAL_AGENT_WAS_ALLOWED: Final = "a personal agent was allowed as a callee"
THE_LINK_WAS_NOT_KEPT: Final = "an allowed link was not in the table with who allowed it"
FAN_OUT_WAS_NOT_GRANTED: Final = "an administrator could not let an agent fan out"
FAN_OUT_WAS_NOT_KEPT: Final = "a fan-out grant was not in the table with who granted it"
FAN_OUT_WAS_NOT_TAKEN_BACK: Final = "a fan-out grant was not taken back by the person who gave it"
A_WITHDRAWAL_LEFT_NO_ROW: Final = "a withdrawn link left no row saying who withdrew it"

A_CHILD_REACHED_TOO_MUCH: Final = (
    "a specialist was handed more than the asker, coordinator and itself share"
)
A_CHILD_REACHED_TOO_LITTLE: Final = "a specialist was handed less than the three of them share"
RAN_TOGETHER_WITHOUT_FAN_OUT: Final = "specialists ran at the same time with fan-out never granted"
THE_REASON_WAS_NOT_KEPT: Final = "the reason a run was in turn was not kept with it"
DID_NOT_RUN_TOGETHER: Final = "specialists did not run at the same time with fan-out granted"
A_GATE_DECISION_WAS_NOT_KEPT: Final = "the gate's decision for a coordinated run was not kept"
AN_UNALLOWED_AGENT_RAN: Final = "a specialist nobody allowed was started"
AN_INVALID_RESULT_WAS_MERGED: Final = "a result that broke its contract was merged"
A_GAP_WAS_NOT_STATED: Final = "an answer missing a subtask did not say it was missing something"
THE_RUN_NAMED_THE_REQUEST: Final = "a kept run held something other than numbers, words and hashes"
A_CHAIN_FANNED_OUT: Final = "a plan with nothing to run at once was fanned out"
A_PLAN_WITH_PROSE_WAS_READ: Final = "a plan asking a subtask for prose was read"
A_PLAN_PRICED_ITSELF: Final = "a plan that set its own cost was read"


async def _links_of(h: Harness, coordinator: str) -> list[tuple[str, str, str | None]]:
    """Every link the table holds for one coordinator: callee, who allowed it, who withdrew it."""
    async with h.sessions() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT callee_id, added_by, removed_by FROM agent.agent_callee "
                    "WHERE coordinator_id = :agent ORDER BY callee_id"
                ),
                {"agent": coordinator},
            )
        ).all()
    return [(str(a), str(b), None if c is None else str(c)) for a, b, c in rows]


async def _fan_rows(h: Harness, agent: str) -> list[tuple[str, str | None]]:
    async with h.sessions() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT enabled_by, removed_by FROM agent.agent_fanout "
                    "WHERE agent_id = :agent ORDER BY enabled_at"
                ),
                {"agent": agent},
            )
        ).all()
    return [(str(a), None if b is None else str(b)) for a, b in rows]


def _refused(reply: Any) -> bool:
    return int(getattr(reply, "status_code", 200)) == 409


# ------------------------------------- 1. who may call whom, and fan-out (M18.5.1, M18.6.2)
@check(
    leaves=("M18.5.1", "M18.6.2"),
    sentence=(
        "An administrator allows an agent to call two others and lets it fan out; its steward is "
        "told who and may change nothing; a colleague is sent the same body before and after; "
        "itself, an unseen agent and a personal agent are refused in a sentence; and each link "
        "and grant is kept with who made it, a withdrawn one with who withdrew it."
    ),
)
async def an_agent_is_told_who_it_may_call_and_whether_to_fan_out(
    h: Harness,
) -> None:
    from brain.agents.model import AgentAudience
    from brain.coordination_routes import (
        CoordinationCalleeAsked,
        CoordinationFanOutAsked,
        agent_coordination,
        allow_callee,
        set_fan_out,
        withdraw_callee,
    )
    from brain.core.errors import BrainError
    from brain.knowledge.visibility import Visibility

    await h.found_departments()
    steward, colleague = h.principal(A, "steward"), h.principal(A, "colleague")
    for one in (steward, colleague):
        await h.person(one, department=A, grants=_readers())
    admin = await a_department_administrator(h)
    lead = await installed_agent(h, steward, suffix="_lead")
    one = await installed_agent(h, steward, suffix="_one")
    two = await installed_agent(h, steward, suffix="_two")
    elsewhere = await installed_agent(
        h,
        steward,
        suffix="_away",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=steward, department=B),
    )
    private = await installed_agent(h, admin, suffix="_own", personal=True)
    app = _console(h)

    async def view(who: str, on: str = lead, *, strong: bool = False) -> Any:
        return await agent_coordination(_request(app), on, await _asking(h, who, strong=strong))

    async def allow(who: str, callee: str) -> Any:
        return await allow_callee(
            _request(app),
            lead,
            CoordinationCalleeAsked(callee_id=callee),
            await _asking(h, who, strong=True),
        )

    before = (await view(colleague)).model_dump()
    for callee in (one, two):
        done = await allow(admin, callee)
        if _refused(done):
            raise CheckFailedError(NOT_ALLOWED)
    told = await view(admin, strong=True)
    if told.names_shown is not True or [c.agent_id for c in told.callees] != sorted([one, two]):
        raise CheckFailedError(NOT_TOLD_TO_THE_ADMINISTRATOR)
    stewards = await view(steward)
    if [c.agent_id for c in stewards.callees] != sorted([one, two]):
        raise CheckFailedError(A_STEWARD_WAS_NOT_TOLD)
    if stewards.may_change:
        raise CheckFailedError(A_STEWARD_CHANGED_IT)
    after = (await view(colleague)).model_dump()
    if after["callees"] or after["names_shown"]:
        raise CheckFailedError(A_COLLEAGUE_WAS_TOLD)
    if after != before:
        raise CheckFailedError(A_COLLEAGUE_READ_IT_APART)
    try:
        await allow(steward, elsewhere)
    except BrainError:
        pass
    else:
        raise CheckFailedError(A_STEWARD_CHANGED_IT)
    try:
        await allow(colleague, elsewhere)
    except BrainError:
        pass
    else:
        raise CheckFailedError(A_COLLEAGUE_CHANGED_IT)

    if not _refused(await allow(admin, lead)):
        raise CheckFailedError(ITSELF_WAS_ALLOWED)
    if not _refused(await allow(admin, elsewhere)):
        raise CheckFailedError(AN_UNSEEN_AGENT_WAS_ALLOWED)
    if not _refused(await allow(admin, private)):
        raise CheckFailedError(A_PERSONAL_AGENT_WAS_ALLOWED)
    links = await _links_of(h, lead)
    if links != [(c, admin, None) for c in sorted([one, two])]:
        raise CheckFailedError(THE_LINK_WAS_NOT_KEPT)

    on = await set_fan_out(
        _request(app),
        lead,
        CoordinationFanOutAsked(enabled=True),
        await _asking(h, admin, strong=True),
    )
    if on.fan_out_enabled is not True:
        raise CheckFailedError(FAN_OUT_WAS_NOT_GRANTED)
    if await _fan_rows(h, lead) != [(admin, None)]:
        raise CheckFailedError(FAN_OUT_WAS_NOT_KEPT)
    off = await set_fan_out(
        _request(app),
        lead,
        CoordinationFanOutAsked(enabled=False),
        await _asking(h, admin, strong=True),
    )
    if off.fan_out_enabled is not False or await _fan_rows(h, lead) != [(admin, admin)]:
        raise CheckFailedError(FAN_OUT_WAS_NOT_TAKEN_BACK)

    gone = await withdraw_callee(
        _request(app),
        lead,
        CoordinationCalleeAsked(callee_id=two),
        await _asking(h, admin, strong=True),
    )
    if _refused(gone) or (two, admin, admin) not in await _links_of(h, lead):
        raise CheckFailedError(A_WITHDRAWAL_LEFT_NO_ROW)


# --------------------------------- 2. a plan is split, run at a narrowed reach and kept (M18.x)
class _Script:
    """A specialist that answers from a table, remembers the reach it was handed and overlaps."""

    def __init__(self, sends: Mapping[str, Mapping[str, object]]) -> None:
        self.sends = dict(sends)
        self.reaches: dict[str, Any] = {}
        self.running = 0
        self.most_at_once = 0
        self.started = 0

    async def run(self, work: Any) -> Any:
        from brain.orchestration.coordinator import Delivered

        self.started += 1
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        self.reaches[work.subtask_id] = work.reach
        try:
            await asyncio.sleep(0.02)
            return Delivered(values=self.sends.get(work.subtask_id, {"n": 1}), minor=3, seconds=0.5)
        finally:
            self.running -= 1


def _plan(callees: list[str], *, chain: bool = False, **more: Any) -> str:
    subtasks = []
    for index, callee in enumerate(callees):
        subtasks.append(
            {
                "subtask_id": f"s{index}",
                "callee": callee,
                "objective": f"Find the count called s{index} for this made-up client",
                "output": [{"name": "n", "kind": "integer"}],
                "depends_on": [f"s{index - 1}"] if chain and index else [],
                **more,
            }
        )
    return json.dumps({"subtasks": subtasks})


@check(
    leaves=("M18.1.2", "M18.1.4", "M18.3.4", "M18.3.5", "M18.5.2", "M18.5.3", "M18.7.1"),
    sentence=(
        "A model's plan is run over five installed agents: each specialist is handed only what "
        "the asker, coordinator and it share; they run in turn until fan-out is granted and "
        "together after, the reason kept; an unallowed specialist, prose and a self-priced plan "
        "start nothing; a broken result is stated as missing; no request is kept."
    ),
)
async def a_plan_runs_its_specialists_at_a_narrowed_reach(h: Harness) -> None:
    from brain.coordination_routes import (
        CoordinationCalleeAsked,
        CoordinationFanOutAsked,
        LedgerRooms,
        StoredRunKeeper,
        allow_callee,
        prepare,
        set_fan_out,
    )
    from brain.core.entitlement import Capability
    from brain.gate.context import TrafficClass
    from brain.ops.halt import NOTHING_HALTED
    from brain.orchestration.coordinator import Mode, Why, coordinate
    from brain.orchestration.planner import PlanRefusedError, read_plan

    await h.found_departments()
    steward, asker = h.principal(A, "steward"), h.principal(A, "asker")
    await h.person(steward, department=A, grants=_readers())
    # The asker holds the title and the body, the coordinator the title, the body and the owner, and
    # every specialist the body and the owner: the three share the body alone.
    await h.person(
        asker,
        department=A,
        grants=((TITLE, Scope.department(A)), (BODY, Scope.department(A))),
    )
    admin = await a_department_administrator(h)
    lead = await installed_agent(h, steward, suffix="_clead", capabilities=(TITLE, BODY, OWNER))
    names = [f"_cs{n}" for n in range(4)]
    specialists = [
        await installed_agent(h, steward, suffix=suffix, capabilities=(BODY, OWNER))
        for suffix in names
    ]
    stranger = await installed_agent(h, steward, suffix="_cstranger", capabilities=(BODY,))
    app = _console(h)
    for callee in specialists:
        await allow_callee(
            _request(app),
            lead,
            CoordinationCalleeAsked(callee_id=callee),
            await _asking(h, admin, strong=True),
        )
    asked = await _asking(h, asker)
    request = _request(app)

    async def run(reply: str, script: _Script, run_id: str) -> Any:
        prepared = await prepare(request, asked, lead)
        steps = read_plan(reply, prepared.callees)
        return await coordinate(
            run_id=run_id,
            coordinator=prepared.lead,
            steps=steps,
            callees=prepared.callees,
            caller=asked.reach,
            specialist=script,
            rooms=LedgerRooms(request, now=h.now, halts=NOTHING_HALTED),
            traffic=TrafficClass.HUMAN_ASYNC,
            at=h.now,
        )

    # Without fan-out four independent subtasks run one after another, at the shared reach only.
    script = _Script({})
    first = await run(_plan(specialists), script, f"check-{h.run}-turn")
    if first.mode is not Mode.SEQUENTIAL or first.why != (Why.FAN_OUT_NOT_ENABLED,):
        raise CheckFailedError(THE_REASON_WAS_NOT_KEPT)
    if script.most_at_once != 1 or script.started != 4:
        raise CheckFailedError(RAN_TOGETHER_WITHOUT_FAN_OUT)
    for reach in script.reaches.values():
        if reach.scope_for(Capability(value=BODY), h.now) is None:
            raise CheckFailedError(A_CHILD_REACHED_TOO_LITTLE)
        if any(reach.scope_for(Capability(value=one), h.now) for one in (TITLE, OWNER)):
            raise CheckFailedError(A_CHILD_REACHED_TOO_MUCH)
    await StoredRunKeeper(h.sessions).keep(first, coordinator_id=lead, at=h.now, by=asker)

    # With fan-out granted, and the gate agreeing, the first wave starts together.
    await set_fan_out(
        request, lead, CoordinationFanOutAsked(enabled=True), await _asking(h, admin, strong=True)
    )
    script = _Script({})
    second = await run(_plan(specialists), script, f"check-{h.run}-together")
    if second.mode is not Mode.PARALLEL or second.why or script.most_at_once < 2:
        raise CheckFailedError(DID_NOT_RUN_TOGETHER)
    await StoredRunKeeper(h.sessions).keep(second, coordinator_id=lead, at=h.now, by=asker)

    # A chain has nothing to run at once, so it is run in turn and the gate names why.
    chained = await run(_plan(specialists, chain=True), _Script({}), f"check-{h.run}-chain")
    if chained.mode is not Mode.SEQUENTIAL or Why.GATE_DECLINED not in chained.why:
        raise CheckFailedError(A_CHAIN_FANNED_OUT)

    # Nothing starts for a specialist nobody allowed, for prose, or for a plan that prices itself.
    nothing = _Script({})
    prepared = await prepare(request, asked, lead)
    try:
        read_plan(_plan([stranger]), prepared.callees)
    except PlanRefusedError:
        pass
    else:
        raise CheckFailedError(AN_UNALLOWED_AGENT_RAN)
    prosy = _plan(specialists[:1]).replace('"integer"', '"text"')
    try:
        read_plan(prosy, prepared.callees)
    except PlanRefusedError:
        pass
    else:
        raise CheckFailedError(A_PLAN_WITH_PROSE_WAS_READ)
    try:
        read_plan(_plan(specialists[:1], cost=1), prepared.callees)
    except PlanRefusedError:
        pass
    else:
        raise CheckFailedError(A_PLAN_PRICED_ITSELF)
    if nothing.started:
        raise CheckFailedError(AN_UNALLOWED_AGENT_RAN)

    # A result that breaks its contract is stated as missing and never merged.
    broken = await run(
        _plan(specialists[:2]),
        _Script({"s0": {"n": 1}, "s1": {"n": "one"}}),
        f"check-{h.run}-broken",
    )
    merged = broken.merged
    if merged is None or "s1" in merged.values:
        raise CheckFailedError(AN_INVALID_RESULT_WAS_MERGED)
    if merged.is_complete or not merged.notice(disclosable=frozenset({"s1"})):
        raise CheckFailedError(A_GAP_WAS_NOT_STATED)

    async with h.sessions() as session:
        kept = (
            await session.execute(
                text(
                    "SELECT run_id, mode, why, asked_by, jsonb_array_length(children) "
                    "FROM ops.coordinated_run WHERE coordinator_id = :agent ORDER BY started_at"
                ),
                {"agent": lead},
            )
        ).all()
        gates = (
            (
                await session.execute(
                    text("SELECT verdict FROM ops.fanout_gate WHERE run_id = ANY(:ids)"),
                    {"ids": [first.run_id, second.run_id]},
                )
            )
            .scalars()
            .all()
        )
        columns = (
            (
                await session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'ops' AND table_name = 'coordinated_run'"
                    )
                )
            )
            .scalars()
            .all()
        )
    if sorted((str(r[1]), list(r[2]), str(r[3]), int(r[4])) for r in kept) != sorted(
        [("sequential", ["fan_out_not_enabled"], asker, 4), ("parallel", [], asker, 4)]
    ):
        raise CheckFailedError(THE_REASON_WAS_NOT_KEPT)
    if sorted(str(one) for one in gates) != ["parallel", "parallel"]:
        raise CheckFailedError(A_GATE_DECISION_WAS_NOT_KEPT)
    if any(word in str(name) for name in columns for word in ("request", "objective", "question")):
        raise CheckFailedError(THE_RUN_NAMED_THE_REQUEST)
