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

What the request path does today is identify, entitle and narrow, then call the model. The
screen, the answer cache, routing and catalogue projection are not on `/answer` yet; the test
that holds all of them in order arrives with the chain that runs them, because the invariant
report refuses a skipped or expected-to-fail rule.

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
from brain.gate.catalogue import project
from brain.gate.classify import classify_lane
from brain.gate.context import Channel, GateStep, Recorder, StepOutOfOrderError, open_trace
from brain.gate.injection import assess
from brain.gate.resolve import resolve
from brain.gate.select import select_agent
from brain.identity.bearer import authenticate
from brain.models.calls import ModelCalls
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
    classify_lane.__code__: "route",
    select_agent.__code__: "route",
    project.__code__: "project",
    ModelCalls.complete.__code__: "model",
}

#: The front half the sentence names, in its order. `narrow` is entitlement's second half.
FRONT_HALF = ("identify", "entitle", "screen", "cache", "route", "project")

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


@pytest.mark.parametrize(
    "front",
    [GateStep.IDENTIFY, GateStep.ENTITLE, GateStep.CLASSIFY, GateStep.CACHE, GateStep.SELECT],
)
def test_the_declared_order_puts_every_front_step_before_the_model(front: GateStep) -> None:
    """INVOKE is where the model is called, and every front-half step is declared before it."""
    assert front < GateStep.INVOKE


@pytest.mark.parametrize(
    "front",
    [GateStep.IDENTIFY, GateStep.ENTITLE, GateStep.CLASSIFY, GateStep.CACHE, GateStep.SELECT],
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
    for step in (
        GateStep.INGEST,
        GateStep.IDENTIFY,
        GateStep.ENTITLE,
        GateStep.CLASSIFY,
        GateStep.CACHE,
        GateStep.SELECT,
        GateStep.INVOKE,
    ):
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
