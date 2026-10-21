"""A coordinating agent hands subtasks to specialists, and each child runs at a narrowed reach.

These are the properties `brain.orchestration.coordinator` exists to hold, asserted over real
`EntitlementSet`s, real ceilings, the real gate and the real seeded budgets. The only stand-ins are
the two ports the engine is handed (a specialist and the global budget), because those are where a
model and a cache would be, and each is written to do what the real one does that the property
depends on: record the reach it was handed, wait for a sibling, raise, return an extra field.

**Every test of a refusal has a sibling that shows the thing working.** A guard tested only by its
refusals is satisfied by an engine that refuses every plan.

Dates are not used here beyond a moment the gate stamps on a record, so none of these can go off.

Task ids: M18.1.2, M18.1.4, M18.3.4, M18.3.5, M18.5.1, M18.5.2, M18.6.2, M18.7.1
"""

from __future__ import annotations

import ast
import asyncio
import functools
from collections.abc import Callable, Coroutine, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.agents.model import CEILING_PRINCIPAL_PREFIX
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.models.routing import Tier
from brain.ops.admission import AdmissionRequest
from brain.orchestration.contract import FieldKind, FieldSpec
from brain.orchestration.coordinator import (
    Callee,
    ChildStatus,
    ChildWork,
    Coordinated,
    Coordinator,
    Delivered,
    Mode,
    PlanStep,
    RoomAnswer,
    SpecialistRefusedError,
    Why,
    callee_refusals,
    contract_for,
    coordinate,
    not_allowed_sentence,
    plan_dispatch,
)
from brain.orchestration.delegation import (
    PARALLELISM_RESOURCE,
    Hop,
    LensKind,
    chain_reach,
    grant_verbs_in,
)
from brain.orchestration.fanout import Condition
from brain.orchestration.merge import GapCause


def _sync(test: Callable[[], Coroutine[Any, Any, None]]) -> Callable[[], None]:
    """Run an async test to the end. The suite drives coroutines with `asyncio.run`."""

    @functools.wraps(test)
    def runner() -> None:
        asyncio.run(test())

    return runner


AT = datetime(2999, 1, 1, tzinfo=UTC)
SRC = Path(__file__).resolve().parents[2] / "src" / "brain" / "orchestration"

A, B, C = "read:alpha.value", "read:beta.value", "read:gamma.value"


def _ceiling(agent_id: str, *capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id=f"{CEILING_PRINCIPAL_PREFIX}{agent_id}",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
        ),
    )


def _asker(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_asker",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
        ),
    )


def _callee(agent_id: str, *capabilities: str) -> Callee:
    return Callee(agent_id=agent_id, tier=Tier.MAIN, ceiling=_ceiling(agent_id, *capabilities))


def _coordinator(
    *allowed: str, fan_out: bool = True, ceiling: tuple[str, ...] = (A, B, C)
) -> Coordinator:
    return Coordinator(
        agent_id="lead",
        ceiling=_ceiling("lead", *ceiling),
        callable_ids=frozenset(allowed),
        may_fan_out=fan_out,
    )


def _step(
    callee: Callee, subtask_id: str, *after: str, kind: FieldKind = FieldKind.INTEGER
) -> PlanStep:
    return PlanStep(
        subtask_id=subtask_id,
        callee_id=callee.agent_id,
        contract=contract_for(
            callee,
            subtask_id=subtask_id,
            objective=f"Find the figure called {subtask_id} for this client",
            output=(FieldSpec(name="figure", kind=kind),),
        ),
        depends_on=after,
    )


class Recorder:
    """A specialist that returns an integer, and remembers what it was handed and when."""

    def __init__(self, *, fail: Mapping[str, Exception] | None = None) -> None:
        self.worked: list[ChildWork] = []
        self.running = 0
        self.most_at_once = 0
        self.fail = dict(fail or {})
        self.send: dict[str, Mapping[str, object]] = {}
        self.pause = 0.0

    async def run(self, work: ChildWork) -> Delivered:
        self.worked.append(work)
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        try:
            if self.pause:
                await asyncio.sleep(self.pause)
            if work.subtask_id in self.fail:
                raise self.fail[work.subtask_id]
            values = self.send.get(work.subtask_id, {"figure": len(self.worked)})
            return Delivered(values=values, minor=7, seconds=1.5)
        finally:
            self.running -= 1


class Room:
    """The global budget, answering as told and remembering what it was asked."""

    def __init__(self, answer: RoomAnswer | None = None) -> None:
        self.answer = answer or RoomAnswer(admitted=True, hold="slots")
        self.asked: list[AdmissionRequest] = []
        self.returned: list[RoomAnswer] = []

    async def take(self, request: AdmissionRequest) -> RoomAnswer:
        self.asked.append(request)
        return self.answer

    async def give_back(self, answer: RoomAnswer) -> None:
        self.returned.append(answer)


def _independent(count: int) -> tuple[dict[str, Callee], list[PlanStep]]:
    specialist = _callee("spec", A, B)
    return {"spec": specialist}, [_step(specialist, f"s{index}") for index in range(count)]


async def _run(
    steps: list[PlanStep],
    callees: Mapping[str, Callee],
    *,
    coordinator: Coordinator | None = None,
    specialist: Recorder | None = None,
    room: Room | None = None,
    caller: EntitlementSet | None = None,
    child_timeout: float = 5.0,
) -> Coordinated:
    lead = coordinator or _coordinator(*callees)
    return await coordinate(
        run_id="run-1",
        coordinator=lead,
        steps=steps,
        callees=callees,
        caller=caller or _asker(A, B, C),
        specialist=specialist or Recorder(),
        rooms=room or Room(),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        at=AT,
        child_timeout=child_timeout,
    )


# ------------------------------------------------------------------ who may be called (M18.5.1)
@_sync
async def test_a_subtask_handed_to_an_agent_the_coordinator_may_not_call_starts_nothing() -> None:
    """Delete this and a model's plan can reach any agent in the company by naming it.

    The sibling below shows the same plan running once the administrator has allowed the agent, so
    this is a refusal of the missing permission and not of every plan.
    """
    callees, steps = _independent(2)
    ran = Recorder()
    refused = await _run(steps, callees, coordinator=_coordinator("someone_else"), specialist=ran)
    assert refused.started is False
    assert refused.refusals == tuple(not_allowed_sentence(one.subtask_id) for one in steps)
    assert ran.worked == []

    allowed = await _run(steps, callees, coordinator=_coordinator("spec"), specialist=ran)
    assert allowed.started is True
    assert len(ran.worked) == 2


def test_an_agent_never_allowed_and_an_agent_that_is_not_there_are_one_refusal() -> None:
    """Delete this and a planner can tell agents apart by the words it is refused with.

    One step names an agent that exists and was not allowed, the other an agent that is not there at
    all, and the sentences differ only by the subtask the asker's own request produced.
    """
    present = _callee("exists", A)
    steps = [_step(present, "first"), _step(present, "second")]
    only_present = {"exists": present}
    never_allowed = callee_refusals(_coordinator("other"), steps[:1], only_present)
    not_there = callee_refusals(_coordinator("exists", "ghost"), [_ghost(present)], only_present)
    assert never_allowed == (not_allowed_sentence("first"),)
    assert not_there == (not_allowed_sentence("ghost_step"),)
    assert never_allowed[0].replace("first", "x") == not_there[0].replace("ghost_step", "x")
    assert "exists" not in never_allowed[0] + not_there[0]
    assert "ghost" not in not_there[0].replace("ghost_step", "")


def _ghost(present: Callee) -> PlanStep:
    step = _step(present, "ghost_step")
    return PlanStep(
        subtask_id=step.subtask_id,
        callee_id="ghost",
        contract=step.contract,
        depends_on=step.depends_on,
    )


@_sync
async def test_a_coordinator_cannot_hand_a_subtask_back_to_itself() -> None:
    """Delete this and a plan can loop through the coordinator until the depth cap meets it."""
    lead = _callee("lead", A)
    refused = await _run(
        [_step(lead, "again")], {"lead": lead}, coordinator=_coordinator("lead"), caller=_asker(A)
    )
    assert refused.started is False
    assert refused.refusals == (not_allowed_sentence("again"),)


# ------------------------------------------------------------------- the reach (M18.5.2)
@_sync
async def test_a_child_runs_at_the_askers_reach_narrowed_by_both_agents() -> None:
    """Delete this and a delegated run can hold what either agent's ceiling took away.

    The asker holds A, B and C, the coordinator may reach A and B, and the specialist B and C. The
    child holds B only, which is the intersection of all four, and the reach it is handed is the
    one `chain_reach` folds, not one the engine built.
    """
    specialist = _callee("spec", B, C)
    step = _step(specialist, "only")
    ran = Recorder()
    done = await _run(
        [step],
        {"spec": specialist},
        coordinator=_coordinator("spec", ceiling=(A, B)),
        specialist=ran,
        caller=_asker(A, B, C),
    )
    handed = ran.worked[0].reach
    assert handed.scope_for(Capability(value=B)) is not None
    assert handed.scope_for(Capability(value=A)) is None
    assert handed.scope_for(Capability(value=C)) is None
    assert handed.principal_id == "u_asker"
    hops = (
        _coordinator("spec", ceiling=(A, B)).hop,
        specialist.hop,
        Hop(lens_id="only", kind=LensKind.SUBTASK, ceiling=_subtask_ceiling(step)),
    )
    assert handed.ent_hash() == chain_reach(_asker(A, B, C), hops).ent_hash()
    assert done.children[0].reach_hash == handed.ent_hash()
    assert done.children[0].depth == 1


def _subtask_ceiling(step: PlanStep) -> EntitlementSet:
    from brain.orchestration.contract import subtask_ceiling

    return subtask_ceiling(step.contract)


@_sync
async def test_a_child_never_holds_what_the_asker_does_not() -> None:
    """Delete this and installing a wide specialist becomes a way to read what the asker cannot."""
    specialist = _callee("spec", A, B, C)
    ran = Recorder()
    await _run(
        [_step(specialist, "wide")],
        {"spec": specialist},
        specialist=ran,
        caller=_asker(A),
    )
    handed = ran.worked[0].reach
    assert handed.scope_for(Capability(value=A)) is not None
    assert handed.scope_for(Capability(value=B)) is None
    assert handed.scope_for(Capability(value=C)) is None


def test_a_subtask_gets_the_capabilities_of_the_specialist_and_a_model_has_no_word_for_more() -> (
    None
):
    """Delete this and the subtask lens could be something other than the specialist's own lens."""
    specialist = _callee("spec", A, B, A)
    contract = contract_for(
        specialist,
        subtask_id="x",
        objective="Find the figure called x for this client",
        output=(FieldSpec(name="figure", kind=FieldKind.INTEGER),),
    )
    assert [one.value for one in contract.capabilities] == [A, B]
    assert contract.scope == Scope()


@_sync
async def test_the_coordinator_receives_only_a_checked_result() -> None:
    """Delete this and a specialist's extra field or wrong type is merged as if it were promised."""
    specialist = _callee("spec", A)
    good, extra, wrong = (_step(specialist, one) for one in ("good", "extra", "wrong"))
    ran = Recorder()
    ran.send = {
        "good": {"figure": 3},
        "extra": {"figure": 4, "note": "a paragraph nobody declared"},
        "wrong": {"figure": "seven"},
    }
    done = await _run([good, extra, wrong], {"spec": specialist}, specialist=ran)
    assert done.merged is not None
    assert dict(done.merged.values) == {"good": {"figure": 3}}
    causes = {one.subtask_id: one.cause for one in done.merged.traces}
    assert causes == {"extra": GapCause.INVALID_RESULT, "wrong": GapCause.INVALID_RESULT}
    assert [one.status for one in done.children] == [
        ChildStatus.DELIVERED,
        ChildStatus.INVALID_RESULT,
        ChildStatus.INVALID_RESULT,
    ]
    assert done.merged.is_complete is False


@_sync
async def test_a_later_step_is_handed_the_earlier_checked_values_and_nothing_else_of_them() -> None:
    """Delete this and a step can read an earlier step's raw output, or one it did not depend on."""
    specialist = _callee("spec", A)
    first, second, third = (_step(specialist, one) for one in ("one", "two", "three"))
    third = _step(specialist, "three", "one")
    ran = Recorder()
    ran.send = {"one": {"figure": 11}, "two": {"figure": 22}, "three": {"figure": 33}}
    await _run([first, second, third], {"spec": specialist}, specialist=ran)
    handed = {one.subtask_id: dict(one.upstream) for one in ran.worked}
    assert handed["three"] == {"one": {"figure": 11}}
    assert handed["one"] == {}
    assert handed["two"] == {}


# ----------------------------------------------------------------------- partial failure
@_sync
async def test_a_specialist_that_fails_is_a_stated_gap_and_the_run_goes_on() -> None:
    """Delete this and one failed specialist costs the asker the whole answer, or hides a hole."""
    specialist = _callee("spec", A)
    steps = [_step(specialist, one) for one in ("fine", "refused", "broke", "slow")]
    ran = Recorder(
        fail={
            "refused": SpecialistRefusedError(),
            "broke": RuntimeError("secret row 42"),
        }
    )
    done = await _run(steps, {"spec": specialist}, specialist=ran)
    assert done.merged is not None
    assert set(done.merged.values) == {"fine", "slow"}
    causes = {one.subtask_id: one.cause for one in done.merged.traces}
    assert causes == {"refused": GapCause.REFUSED, "broke": GapCause.UNREACHABLE}
    assert "secret row 42" not in repr(done.merged)
    assert done.merged.notice(disclosable=frozenset(one.subtask_id for one in steps)) != ""


@_sync
async def test_a_specialist_that_takes_too_long_is_a_stated_gap() -> None:
    """Delete this and a stuck specialist holds the whole run for ever."""
    specialist = _callee("spec", A)
    ran = Recorder()
    ran.pause = 0.2
    done = await _run(
        [_step(specialist, "slow")], {"spec": specialist}, specialist=ran, child_timeout=0.01
    )
    assert done.merged is not None
    assert done.children[0].status is ChildStatus.TIMED_OUT
    assert [one.cause for one in done.merged.traces] == [GapCause.TIMED_OUT]


@_sync
async def test_a_step_whose_dependency_produced_nothing_is_not_run() -> None:
    """Delete this and a step runs on inputs that were never produced."""
    specialist = _callee("spec", A)
    first = _step(specialist, "first")
    second = _step(specialist, "second", "first")
    ran = Recorder(fail={"first": RuntimeError("down")})
    done = await _run([first, second], {"spec": specialist}, specialist=ran)
    assert [one.subtask_id for one in ran.worked] == ["first"]
    assert [one.status for one in done.children] == [
        ChildStatus.UNREACHABLE,
        ChildStatus.NOT_ADMITTED,
    ]
    assert done.merged is not None
    assert {one.subtask_id for one in done.merged.gaps} == {"first", "second"}


@_sync
async def test_every_child_that_ran_is_charged_and_the_total_is_the_sum_of_the_rows() -> None:
    """Delete this and the run's cost can be a figure that does not equal what each child cost."""
    callees, steps = _independent(3)
    done = await _run(steps, callees)
    assert done.merged is not None
    assert [one.minor for one in done.children] == [7, 7, 7]
    assert done.merged.total_minor == 21
    assert [one.seconds for one in done.merged.reports] == [1.5, 1.5, 1.5]


# ---------------------------------------------------------------- fan-out (M18.6.2, M18.7.1)
@_sync
async def test_with_fan_out_enabled_and_the_gate_agreeing_the_first_wave_starts_together() -> None:
    """Delete this and enabling fan-out changes nothing, because nothing runs in parallel.

    Two specialists wait for each other: run one after another the first would wait for ever, so
    the run only completes if both were started before either finished.
    """
    callees, steps = _independent(2)
    barrier = asyncio.Barrier(2)

    class Waiting(Recorder):
        async def run(self, work: ChildWork) -> Delivered:
            await asyncio.wait_for(barrier.wait(), timeout=2)
            return await super().run(work)

    room = Room()
    done = await _run(steps, callees, specialist=Waiting(), room=room)
    assert done.mode is Mode.PARALLEL
    assert done.why == ()
    assert done.merged is not None and done.merged.is_complete
    assert done.dispatch.gate is not None and done.dispatch.gate.parallel


@_sync
async def test_without_fan_out_enabled_the_specialists_run_in_turn_and_the_reason_is_kept() -> None:
    """Delete this and a run that was never allowed to fan out does, or says nothing about why not.

    Every specialist still runs, none at the same time as another, and the budget is not even asked.
    """
    callees, steps = _independent(3)
    ran = Recorder()
    ran.pause = 0.01
    room = Room()
    done = await _run(
        steps, callees, coordinator=_coordinator("spec", fan_out=False), specialist=ran, room=room
    )
    assert done.mode is Mode.SEQUENTIAL
    assert done.why == (Why.FAN_OUT_NOT_ENABLED,)
    assert ran.most_at_once == 1
    assert len(ran.worked) == 3
    assert room.asked == []
    assert done.merged is not None and done.merged.is_complete


@_sync
async def test_the_specialists_run_in_turn_never_replaced_by_the_coordinator() -> None:
    """Delete this and a refusal of parallelism becomes the coordinator answering in their place.

    The engine takes a subtask's values from the specialist port and from nowhere else: with
    fan-out refused, three subtasks produce three calls to the port and three results, each carrying
    the figure the specialist sent.
    """
    callees, steps = _independent(3)
    ran = Recorder()
    ran.send = {"s0": {"figure": 100}, "s1": {"figure": 200}, "s2": {"figure": 300}}
    done = await _run(
        steps, callees, coordinator=_coordinator("spec", fan_out=False), specialist=ran
    )
    assert done.merged is not None
    assert {k: dict(v) for k, v in done.merged.values.items()} == {
        "s0": {"figure": 100},
        "s1": {"figure": 200},
        "s2": {"figure": 300},
    }
    assert [one.callee_id for one in done.children] == ["spec", "spec", "spec"]


@_sync
async def test_a_chain_is_run_in_turn_because_the_gate_declines_and_names_the_condition() -> None:
    """Delete this and a plan with nothing to run together is fanned out, or the reason is lost."""
    specialist = _callee("spec", A)
    steps = [_step(specialist, "a"), _step(specialist, "b", "a"), _step(specialist, "c", "b")]
    room = Room()
    done = await _run(steps, {"spec": specialist}, room=room)
    assert done.mode is Mode.SEQUENTIAL
    assert Why.GATE_DECLINED in done.why
    assert done.dispatch.gate is not None
    assert Condition.ENOUGH_BRANCHES in done.dispatch.gate.failed
    assert room.asked == []
    assert done.merged is not None and done.merged.is_complete


@_sync
async def test_a_wave_wider_than_the_cap_runs_in_turn_and_says_so() -> None:
    """Delete this and nine children start at once against a cap of eight."""
    callees, steps = _independent(9)
    ran = Recorder()
    ran.pause = 0.001
    done = await _run(steps, callees, specialist=ran)
    assert done.mode is Mode.SEQUENTIAL
    assert Why.WAVE_OVER_THE_CAP in done.why
    assert ran.most_at_once == 1
    assert len(ran.worked) == 9


# ---------------------------------------------------------------------------- the budget (M18.3.5)
@_sync
async def test_the_global_budget_is_asked_once_for_the_widest_wave_before_any_child_starts() -> (
    None
):
    """Delete this and fan-out is admitted child by child, or never asked at all."""
    specialist = _callee("spec", A)
    steps = [
        *(_step(specialist, one) for one in ("a", "b", "c", "d")),
        _step(specialist, "e", "a", "b", "c", "d"),
    ]
    order: list[str] = []

    class Noting(Recorder):
        async def run(self, work: ChildWork) -> Delivered:
            order.append(f"run:{work.subtask_id}")
            return await super().run(work)

    class Noted(Room):
        async def take(self, request: AdmissionRequest) -> RoomAnswer:
            order.append("room")
            return await super().take(request)

    room = Noted()
    done = await _run(steps, {"spec": specialist}, specialist=Noting(), room=room)
    assert done.mode is Mode.PARALLEL
    assert len(room.asked) == 1
    assert room.asked[0].units == 4
    assert room.asked[0].resource is PARALLELISM_RESOURCE
    assert order[0] == "room"
    assert len(room.returned) == 1


@_sync
async def test_no_room_in_the_global_budget_runs_the_specialists_in_turn_and_says_so() -> None:
    """Delete this and a spent budget either stops the run or is exceeded by it."""
    callees, steps = _independent(3)
    ran = Recorder()
    ran.pause = 0.01
    room = Room(RoomAnswer(admitted=False, reason="the estate is busy"))
    done = await _run(steps, callees, specialist=ran, room=room)
    assert done.mode is Mode.SEQUENTIAL
    assert done.why == (Why.NO_ROOM,)
    assert ran.most_at_once == 1
    assert done.merged is not None and done.merged.is_complete
    assert len(room.returned) == 1


@_sync
async def test_a_halt_refuses_the_whole_run_in_the_halts_own_words() -> None:
    """Delete this and a stopped estate still starts children."""
    callees, steps = _independent(2)
    ran = Recorder()
    room = Room(RoomAnswer(admitted=False, halted=True, reason="Work is stopped for now."))
    done = await _run(steps, callees, specialist=ran, room=room)
    assert done.started is False
    assert done.refusals == ("Work is stopped for now.",)
    assert ran.worked == []


# ---------------------------------------------------------------------- the caps (M18.3.4)
@_sync
async def test_a_child_below_the_depth_cap_is_refused_before_it_starts() -> None:
    """Delete this and a coordinator two levels down can start a third level of agents."""
    deeper = Coordinator(
        agent_id="lead",
        ceiling=_ceiling("lead", A),
        callable_ids=frozenset({"spec"}),
        may_fan_out=True,
        parents=(_hop("p1", A), _hop("p2", A)),
    )
    specialist = _callee("spec", A)
    ran = Recorder()
    done = await _run(
        [_step(specialist, "toodeep")],
        {"spec": specialist},
        coordinator=deeper,
        specialist=ran,
        caller=_asker(A),
    )
    assert done.started is False
    assert deeper.depth == 2
    assert any("delegations deep" in one for one in done.refusals)
    assert ran.worked == []

    shallow = Coordinator(
        agent_id="lead",
        ceiling=_ceiling("lead", A),
        callable_ids=frozenset({"spec"}),
        may_fan_out=True,
        parents=(_hop("p1", A),),
    )
    allowed = await _run(
        [_step(specialist, "fine")],
        {"spec": specialist},
        coordinator=shallow,
        specialist=ran,
        caller=_asker(A),
    )
    assert allowed.started is True


def _hop(agent_id: str, *capabilities: str) -> Hop:
    return Hop(lens_id=agent_id, kind=LensKind.AGENT, ceiling=_ceiling(agent_id, *capabilities))


def test_a_plan_with_no_steps_or_too_many_starts_nothing() -> None:
    """Delete this and an empty or unbounded plan is weighed and dispatched."""
    callees, steps = _independent(13)
    dispatch = plan_dispatch(
        run_id="r",
        coordinator=_coordinator("spec"),
        steps=steps,
        callees=callees,
        caller=_asker(A),
        at=AT,
    )
    assert dispatch.refused
    empty = plan_dispatch(
        run_id="r",
        coordinator=_coordinator("spec"),
        steps=[],
        callees=callees,
        caller=_asker(A),
        at=AT,
    )
    assert empty.refused
    twelve = plan_dispatch(
        run_id="r",
        coordinator=_coordinator("spec"),
        steps=steps[:12],
        callees=callees,
        caller=_asker(A),
        at=AT,
    )
    assert not twelve.refused


def test_a_step_cannot_carry_another_subtasks_contract() -> None:
    """Delete this and a result is checked against a promise somebody else made."""
    from brain.orchestration.coordinator import CoordinationError

    specialist = _callee("spec", A)
    other = _step(specialist, "other")
    with pytest.raises(CoordinationError):
        PlanStep(subtask_id="mine", callee_id="spec", contract=other.contract)


# --------------------------------------------------------------------- the module's own shape
def test_the_coordinator_and_the_planner_intersect_nothing_and_grant_nothing() -> None:
    """Delete this and a second implementation of the central rule can arrive in the engine.

    Parsed, not searched: neither module may call `intersect`, and neither may produce an
    `EntitlementSet` out of anything that is not one.
    """
    for name in ("coordinator.py", "planner.py"):
        source = (SRC / name).read_text(encoding="utf-8")
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "intersect"
        ]
        assert calls == [], name
        assert grant_verbs_in(source) == (), name
