"""A request passes the gate's front half, in its declared order, before any model is called.

Two halves, because the order is declared in one place and followed in another.

**Declared.** `brain.gate.context.GateStep` is the order, and `Recorder.enter` refuses a step
that runs after a later one. So a model invocation entered before identification, entitlement,
the cache or selection is refused rather than recorded.

**Followed.** The real application from `create_app`, driven over HTTP with a model service in
place, and every step identified by the function that implements it rather than by a spy the
route could route around: a profiler records the first time each function's code runs, on
every thread, so a step is seen however it was imported and a step that did not run is absent.
The model is `brain.models.calls.ModelCalls.complete`, the one call every model request makes.

The request path identifies, entitles and narrows, then runs `brain.gate.front.run_front_half`
(screen, classify and select, cache, route, catalogue projection, the order decided on
2026-09-21), and only then calls the model. `tests/invariants/test_front_half.py` holds the chain
itself to that order; this holds `/answer` to it end to end.

Task ids: M3.9.7
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from types import CodeType, FrameType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.admission import admit
from brain.gate.answer import answer_lane
from brain.gate.answer_cache import lookup
from brain.gate.cache_key import CachedAnswer
from brain.gate.catalogue import project
from brain.gate.classify import classify_lane
from brain.gate.context import Channel, GateStep, Recorder, StepOutOfOrderError, open_trace
from brain.gate.finish import Finished
from brain.gate.front import _cached
from brain.gate.injection import assess
from brain.gate.resolve import resolve
from brain.gate.select import select_agent
from brain.identity.bearer import authenticate
from brain.models.calls import ModelCalls
from brain.models.routing import classify_tier
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_answer_route_model import READER, READER_GRANTS
from tests.unit.test_answer_route_model import client as client
from tests.unit.test_answer_route_model import transport as transport
from tests.unit.test_model_calls import Scripted

pytestmark = pytest.mark.invariant

#: The step each implementing function is, keyed on its code object so an alias is the same step.
STEP_OF: dict[CodeType, str] = {
    authenticate.__code__: "identify",
    resolve.__code__: "entitle",
    admit.__code__: "narrow",
    assess.__code__: "screen",
    lookup.__code__: "cache",
    classify_lane.__code__: "select",
    select_agent.__code__: "select",
    classify_tier.__code__: "route",
    project.__code__: "project",
    ModelCalls.complete.__code__: "model",
    # The CACHE step's own function, which runs with or without a store; `lookup` runs only
    # when there is one to look in.
    _cached.__code__: "cache step",
}

#: The whole front half, in the decided order, as the functions that do it are first seen.
FRONT_HALF = ("identify", "entitle", "narrow", "screen", "select", "cache", "route", "project")

#: A question the classifier puts on the fast lane, which no rule in the fixture answers.
FAST_LANE_QUESTION = "hours left on Acme"


class Store:
    """An answer store that finds nothing and remembers what it was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def get(self, key: str) -> CachedAnswer | None:
        self.asked.append(key)
        return None

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        del key, value, ttl_seconds


class Rows:
    """A request recorder that keeps what it was handed."""

    def __init__(self) -> None:
        self.kept: list[Finished] = []

    async def finished(self, request: Finished) -> None:
        self.kept.append(request)


NOW = datetime(2026, 9, 21, tzinfo=UTC)

#: A question no fast-path rule matches, so the route hands it to the model step.
UNANSWERED_BY_RULES = "how much annual leave do we get"


#: A verb the console admits only with a second factor, held by the caller in the narrowing test.
WITHHELD_WITHOUT_A_SECOND_FACTOR = Grant(capability=Capability(value="admin:roles"), scope=Scope())


class Observed(list[str]):
    """Steps in first-run order, plus the reach the answer lane was handed."""

    reach: EntitlementSet | None = None


def _first_seen(order: Observed) -> Callable[[FrameType, str, Any], None]:
    def profile(frame: FrameType, event: str, _arg: Any) -> None:
        if event == "call":
            if frame.f_code is answer_lane.__code__ and order.reach is None:
                order.reach = frame.f_locals.get("entitlement")
            step = STEP_OF.get(frame.f_code)
            if step is not None and step not in order:
                order.append(step)

    return profile


@pytest.fixture
def observed() -> Iterator[Observed]:
    """The steps in the order their code first ran, on every thread. TestClient runs the app on
    a portal thread, so a profiler on this thread alone would see nothing and pass vacuously."""
    order = Observed()
    profile = _first_seen(order)
    threading.setprofile_all_threads(profile)
    sys.setprofile(profile)
    try:
        yield order
    finally:
        sys.setprofile(None)
        threading.setprofile_all_threads(None)


def _ask(
    client: TestClient, question: str, token_for: str | None = READER, *, strong: bool = True
) -> int:
    sent = headers(token_for, strong=strong) if token_for is not None else {}
    return client.post(
        f"{API_PREFIX}/answer", headers=sent, json={"question": question}
    ).status_code


def _before_the_model(order: list[str], steps: tuple[str, ...]) -> None:
    assert "model" in order, f"no model call was seen; observed {order}"
    missing = [one for one in steps if one not in order]
    assert not missing, f"{missing} did not run before the model; observed {order}"
    ran = [one for one in order if one in (*steps, "model")]
    assert ran == [*steps, "model"], f"out of order: {order}"


# ------------------------------------------------------------------ declared

#: The front half as `GateStep` declares it, in order.
FRONT_STEPS = [
    GateStep.IDENTIFY,
    GateStep.ENTITLE,
    GateStep.SCREEN,
    GateStep.CLASSIFY,
    GateStep.SELECT,
    GateStep.CACHE,
    GateStep.ROUTE,
    GateStep.PROJECT,
]


@pytest.mark.parametrize(
    "front",
    FRONT_STEPS,
)
def test_the_declared_order_puts_every_front_step_before_the_model(front: GateStep) -> None:
    """INVOKE is where the model is called, and every front-half step is declared before it."""
    assert front < GateStep.INVOKE


@pytest.mark.parametrize(
    "front",
    FRONT_STEPS,
)
def test_a_front_step_after_the_model_call_is_refused(front: GateStep) -> None:
    """A model call entered first makes every front step after it an error, not a record."""
    recorder: Recorder = open_trace("t-order", NOW, Channel.CONSOLE)
    recorder.enter(GateStep.INVOKE)
    with pytest.raises(StepOutOfOrderError):
        recorder.enter(front)


def test_the_front_half_in_its_declared_order_reaches_the_model() -> None:
    """The positive sibling: the declared order, entered in order, is accepted end to end."""
    recorder = open_trace("t-order", NOW, Channel.CONSOLE)
    for step in (GateStep.INGEST, *FRONT_STEPS, GateStep.INVOKE):
        recorder.enter(step)
    assert recorder.steps[-1] is GateStep.INVOKE


# ------------------------------------------------------------------ followed


def test_the_request_is_identified_and_entitled_before_any_model_is_called(
    client: TestClient,
    transport: Scripted,
    observed: Observed,
) -> None:
    """Over HTTP, the caller is identified, their entitlements resolved and then narrowed to the
    channel and assurance, in that order, and only then is the model called, exactly once.

    Delete this and `/answer` can call the model at the nominal reach, or before anybody knows
    who asked, and every lane test still passes."""
    assert _ask(client, UNANSWERED_BY_RULES) == 200
    _before_the_model(observed, ("identify", "entitle", "narrow"))
    assert len(transport.sent) == 1


def test_the_model_step_is_handed_the_narrowed_reach_and_never_the_nominal_one(
    client: TestClient,
    transport: Scripted,
    observed: Observed,
) -> None:
    """The caller holds an admin grant and signed in without a second factor, so the console
    withholds it. The reach the answer lane, and so the model step, is handed has lost it.

    Delete this and the route can resolve and then answer at the nominal reach: `admit` still
    runs for the refusal wording, so seeing it run proves nothing about what was passed on."""
    client.app.state.gate = gate_wiring(  # type: ignore[attr-defined]
        {READER: (*READER_GRANTS[READER], WITHHELD_WITHOUT_A_SECOND_FACTOR)}
    )
    assert _ask(client, UNANSWERED_BY_RULES, strong=False) == 200
    assert len(transport.sent) == 1
    assert observed.reach is not None
    verbs = {grant.capability.verb for grant in observed.reach.grants}
    assert "read" in verbs
    assert "admin" not in verbs


def test_a_request_that_fails_identification_reaches_no_model(
    client: TestClient,
    transport: Scripted,
    observed: Observed,
) -> None:
    """Refused at the first step, so nothing after it runs: no entitlement read, no model."""
    assert _ask(client, UNANSWERED_BY_RULES, token_for=None) == 401
    assert "identify" in observed
    assert "entitle" not in observed
    assert "model" not in observed
    assert transport.sent == []


def test_the_whole_front_half_runs_in_order_on_answer_before_the_model(
    client: TestClient,
    transport: Scripted,
    observed: Observed,
) -> None:
    """M3.9.7 on the real route: identify, entitle, narrow, screen, classify and select, cache,
    route, project, and only then the model, with an answer store installed so the lookup runs.

    Delete this and `/answer` can call the model before the cache is consulted, or before the
    catalogue is projected from the narrowed reach, and the chain's own test still passes."""
    store = Store()
    client.app.state.answer_store = store  # type: ignore[attr-defined]
    assert _ask(client, UNANSWERED_BY_RULES) == 200
    _before_the_model(observed, FRONT_HALF)
    assert len(store.asked) == 1
    assert len(transport.sent) == 1


def test_with_no_answer_store_the_cache_step_still_runs_before_the_model(
    client: TestClient,
    transport: Scripted,
    observed: Observed,
) -> None:
    """No cache configured: the CACHE step is entered and misses, nothing is looked up, and the
    model is still reached only after route and projection."""
    assert _ask(client, UNANSWERED_BY_RULES) == 200
    assert "cache" not in observed
    _before_the_model(
        observed,
        ("identify", "entitle", "narrow", "screen", "select", "cache step", "route", "project"),
    )
    assert len(transport.sent) == 1


def test_a_fast_lane_question_reaches_no_model_even_when_no_rule_answers_it(
    client: TestClient,
    transport: Scripted,
    observed: Observed,
) -> None:
    """The front half routed it to no tier, so the lane is handed no model, and nothing is
    projected: a model is never called without ROUTE and PROJECT before it.

    Delete this and a question the classifier kept off the model lane reaches a model through
    the lane's own fallback, with no tier decided and no catalogue built."""
    assert _ask(client, FAST_LANE_QUESTION) == 200
    assert "route" in observed
    assert "project" not in observed
    assert transport.sent == []


def test_the_request_row_carries_what_the_front_half_decided(client: TestClient) -> None:
    """M3.4.2 and M3.6.3 through the route: the finished request holds the score, the routed
    lane, the stage and the agent the chain decided, which is what the row is written from."""
    rows = Rows()
    client.app.state.request_recorders = (rows,)  # type: ignore[attr-defined]
    assert _ask(client, UNANSWERED_BY_RULES) == 200
    (finished,) = rows.kept
    assert finished.front is not None
    assert finished.front.selected_agent == "brain"
    assert finished.front.routed_lane.value == "answer"


def test_the_agent_the_person_picked_reaches_selection_and_one_they_may_not_use_does_not(
    client: TestClient,
) -> None:
    """M3.9.8 through the route: the picker's id reaches `select_agent` as the addressed agent, and
    a name nobody may use falls to the default exactly as an absent one does.

    Delete this and `/answer` can drop the picker's value, and addressing an agent does nothing."""
    rows = Rows()
    client.app.state.request_recorders = (rows,)  # type: ignore[attr-defined]
    for agent in ("brain", "finance", None):
        body = {"question": UNANSWERED_BY_RULES, **({"agent": agent} if agent else {})}
        sent = client.post(f"{API_PREFIX}/answer", headers=headers(READER), json=body)
        assert sent.status_code == 200
    stages = [
        (one.front.selection_stage.value, one.front.selected_agent)
        for one in rows.kept
        if one.front
    ]
    assert stages == [("addressed", "brain"), ("default", "brain"), ("default", "brain")]
