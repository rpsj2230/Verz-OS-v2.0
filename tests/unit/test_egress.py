"""The egress scrub: what a third-party model is sent, what the reader gets back, no other way.

Three halves. The scrub itself: values replaced by numbered placeholders, the analyser only ever
adding to the rules, a scrub that fails sending nothing, and what was found logged by kind and
never obeyed. The transports: a hosted provider's body carries no value and its answer comes back
put back, while the install's own server is sent the text as it is. And the source: every
function in `src/brain` that builds a model transport goes through `third_party_call`, and nothing
else posts a provider's body, so a third way out is a failing test rather than a leak.

Task ids: M32.2.2.1, M32.2.2.3
"""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from brain.models.adapter import Completion, failure_from
from brain.models.driver import DriverMessage, DriverRequest, Role
from brain.ops import egress
from brain.ops.egress import (
    ANALYSER_BUDGET_SECONDS,
    AnalyserUnavailableError,
    EgressScrubFailedError,
    analyser,
    decode_analysis,
    scrub_for_egress,
    third_party_call,
)
from brain.ops.pii import PRESIDIO_BUILT_INS, PRESIDIO_KINDS, Detection, EntityKind, PiiError

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

#: Worked examples the pii suite already uses: a checksummed NRIC, an email and a number.
NRIC = "S1234567D"
OTHER_NRIC = "T0123456G"
EMAIL = "nur.aisyah@example.com"
PHONE = "9123 4567"
NAME = "Tan Wei Ling"

QUESTION = f"Is {NRIC} the same customer as {EMAIL}? Call {PHONE} if not."


def request(*texts: str) -> DriverRequest:
    return DriverRequest(
        deployment_id="anthropic.main",
        model="claude",
        messages=tuple(
            DriverMessage(role=Role.SYSTEM if i == 0 and len(texts) > 1 else Role.USER, content=t)
            for i, t in enumerate(texts)
        ),
        timeout_seconds=5.0,
    )


class Recorder:
    """A `send` that keeps what it was handed and answers with a fixed text."""

    def __init__(self, answer: str = "") -> None:
        self.sent: list[DriverRequest] = []
        self.answer = answer

    def __call__(self, outbound: DriverRequest) -> Completion:
        self.sent.append(outbound)
        return Completion(text=self.answer, finish_reason="stop")


def found_by(*spans: tuple[str, EntityKind]) -> Any:
    """A detector finding each named piece of text wherever it stands, as the analyser would."""

    def detect(text: str, *, timeout_seconds: float) -> Sequence[Detection]:
        del timeout_seconds
        out = []
        for piece, kind in spans:
            at = text.find(piece)
            if at >= 0:
                out.append(Detection(kind=kind, start=at, end=at + len(piece), confidence=0.9))
        return out

    return detect


# ------------------------------------------------------------------------ the scrub
def test_a_third_party_is_sent_placeholders_and_the_reader_gets_the_values_back() -> None:
    """`THE_ANSWER_IS_PUT_BACK_FOR_THE_READER`: the NRIC, the email and the number leave as
    placeholders, the model answers in them, and the reader reads the values. Delete this and a
    question's personal data can reach a provider with every other test green, or the reader can
    be handed an answer full of tokens."""
    send = Recorder(answer="[sg_nric_1] and [email_1] are one customer; [sg_phone_1] answers.")
    answered = third_party_call(request(QUESTION), send, provider="anthropic", detector=None)
    [outbound] = send.sent
    sent = outbound.messages[0].content
    assert sent == "Is [sg_nric_1] the same customer as [email_1]? Call [sg_phone_1] if not."
    assert answered.text == f"{NRIC} and {EMAIL} are one customer; {PHONE} answers."


def test_one_value_is_one_placeholder_everywhere_in_a_request() -> None:
    """The same NRIC in the system prompt and the question is one token, and a second NRIC is a
    second one, so the model can still tell one person from two. Delete this and two customers
    can arrive as one, or one as two."""
    scrubbed = scrub_for_egress(
        [f"Context: {NRIC} owes.", f"Does {NRIC} or {OTHER_NRIC} owe?"], detector=None
    )
    assert scrubbed.texts == ("Context: [sg_nric_1] owes.", "Does [sg_nric_1] or [sg_nric_2] owe?")
    assert dict(scrubbed.found) == {"sg_nric": 2}
    assert scrubbed.put_back("[sg_nric_2], not [sg_nric_1]") == f"{OTHER_NRIC}, not {NRIC}"


def test_a_placeholder_the_request_never_held_is_left_as_it_is() -> None:
    """A token the model invented stands for nothing, so it is left alone rather than given some
    other value. Delete this and a model guessing `[sg_nric_3]` could be handed a value."""
    scrubbed = scrub_for_egress([NRIC], detector=None)
    assert scrubbed.put_back("[sg_nric_3] [sg_nric_1]") == f"[sg_nric_3] {NRIC}"


def test_the_analyser_adds_what_the_rules_cannot_find() -> None:
    """`THE_ANALYSER_ONLY_EVER_ADDS`, its positive half: a name no pattern describes is scrubbed
    when the analyser finds it, beside everything the rules found. Delete this and the analyser
    can be wired in and never consulted."""
    scrubbed = scrub_for_egress(
        [f"{NAME} holds {NRIC}."], detector=found_by((NAME, EntityKind.UNPATTERNED_NAME))
    )
    assert scrubbed.texts == ("[person_name_1] holds [sg_nric_1].",)
    assert scrubbed.detector == "analyser"


@pytest.mark.parametrize("failure", [AnalyserUnavailableError(), PiiError("unreadable")])
def test_an_analyser_that_cannot_answer_leaves_the_rules_scrub_and_the_call_goes_ahead(
    failure: Exception,
) -> None:
    """`THE_ANALYSER_ONLY_EVER_ADDS`, its other half: an analyser that is down or answers
    something unreadable leaves the rules' scrub, the NRIC is still replaced, and the call is
    made. Delete this and text can be sent unscrubbed because the analyser was down, or no
    answer at all can be given for the same reason."""

    def down(text: str, *, timeout_seconds: float) -> Sequence[Detection]:
        raise failure

    send = Recorder(answer="[sg_nric_1]")
    answered = third_party_call(request(QUESTION), send, provider="anthropic", detector=down)
    assert NRIC not in send.sent[0].messages[0].content
    assert answered.text == NRIC


def test_the_analyser_is_not_asked_past_its_budget() -> None:
    """The analyser has one budget for the whole request. Once it is spent the rest of the
    request is scrubbed by the rules alone and the analyser is not asked again. Delete this and a
    slow analyser holds a person's answer for its timeout once per message."""
    asked: list[float] = []
    now = [0.0]

    def slow(text: str, *, timeout_seconds: float) -> Sequence[Detection]:
        asked.append(timeout_seconds)
        now[0] += ANALYSER_BUDGET_SECONDS
        return ()

    scrubbed = scrub_for_egress([QUESTION, QUESTION], detector=slow, clock=lambda: now[0])
    assert asked == [ANALYSER_BUDGET_SECONDS]
    assert scrubbed.detector == "rules"
    assert all(NRIC not in text for text in scrubbed.texts)


def test_a_scrub_that_fails_sends_nothing_and_stops_the_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scrub that raises sends nothing, and the failure carries no trigger, so the chain stops
    rather than trying the same unscrubbed text on the next rung. Delete this and a bug in the
    scrubber becomes the leak the scrubber exists to prevent."""

    def broken(text: str) -> tuple[Detection, ...]:
        raise RuntimeError(text)

    monkeypatch.setattr(egress, "detect", broken)
    send = Recorder()
    with pytest.raises(EgressScrubFailedError):
        third_party_call(request(QUESTION), send, provider="anthropic", detector=None)
    assert send.sent == []
    failure = failure_from(EgressScrubFailedError(), deployment_id="anthropic.main")
    assert failure.trigger is None


def test_what_was_found_is_logged_by_kind_and_never_by_value() -> None:
    """`DETECTIONS_ARE_COUNTED_AND_NEVER_OBEYED` (M32.2.2.3): every call writes one line naming
    the provider, the detector and the count of each kind, the call is made whatever was found,
    and no value is in the line. Delete this and what was found can stop being recorded, be
    recorded with the values themselves, or start refusing calls."""
    send = Recorder(answer="ok")
    with capture_logs() as logged:
        third_party_call(request(QUESTION), send, provider="anthropic", detector=None)
    [line] = [one for one in logged if one["event"] == "egress.scrubbed"]
    assert line["provider"] == "anthropic"
    assert line["detector"] == "rules"
    assert line["found"] == 3
    assert line["kinds"] == "email=1,sg_nric=1,sg_phone=1"
    assert len(send.sent) == 1
    rendered = json.dumps(logged, default=str)
    assert all(value not in rendered for value in (NRIC, EMAIL, PHONE))


# ------------------------------------------------------------------------ the analyser
def span(entity: str, start: int, end: int, score: float = 0.9) -> dict[str, object]:
    return {"entity_type": entity, "start": start, "end": end, "score": score}


def test_every_entity_the_install_asks_the_analyser_for_has_a_kind() -> None:
    """`pii.PRESIDIO_KINDS` covers every enabled built-in exactly, so no span the analyser is
    asked for is refused for want of a label. Delete this and enabling a built-in refuses every
    analysis that finds one."""
    assert set(PRESIDIO_KINDS) == {one.presidio_name for one in PRESIDIO_BUILT_INS}


def test_the_analysers_answer_is_read_as_detections_of_their_own_kind() -> None:
    """A PERSON and a URL above their thresholds become a name and a url, and a span under its
    threshold is dropped. Delete this and an analysis can be read with the wrong kinds or none."""
    text = f"{NAME} wrote https://example.com/x"
    found = decode_analysis(
        text,
        [span("PERSON", 0, 12), span("URL", 19, len(text)), span("PERSON", 19, 26, score=0.1)],
    )
    assert [(one.kind, one.start, one.end) for one in found] == [
        (EntityKind.UNPATTERNED_NAME, 0, 12),
        (EntityKind.URL, 19, len(text)),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"spans": []},
        ["not a span"],
        [span("NRP", 0, 3)],
        [span("PERSON", 0, 99)],
        [span("PERSON", 3, 3)],
        [{"entity_type": "PERSON", "start": 0, "end": 3}],
        [{"entity_type": "PERSON", "start": True, "end": 3, "score": 0.9}],
    ],
)
def test_an_answer_that_cannot_be_read_is_refused_rather_than_read_as_nothing(
    payload: object,
) -> None:
    """Not a list, not a span, an entity nobody asked for, a span outside the text or of no
    length, no score, a boolean offset: each is refused, so the caller keeps the rules' scrub and
    knows the analyser did not answer. Delete this and an unreadable answer reads as one that
    found nothing."""
    with pytest.raises(PiiError):
        decode_analysis("Tan Wei Ling", payload)


def test_the_analyser_is_asked_for_the_installs_entities_and_a_refusal_is_unavailable() -> None:
    """The request names the text, the language and every enabled built-in; a 200 is read and
    anything else is the analyser being unavailable. Delete this and the analyser can be asked
    the wrong question, or an error page read as an analysis."""
    seen: list[dict[str, Any]] = []
    status = [200]

    def answer(call: httpx.Request) -> httpx.Response:
        seen.append(json.loads(call.content))
        return httpx.Response(status[0], json=[span("PERSON", 0, 12)])

    detect = analyser(
        "http://analyser.test:3000/", httpx.Client(transport=httpx.MockTransport(answer))
    )
    found = detect(NAME, timeout_seconds=1.0)
    assert [one.kind for one in found] == [EntityKind.UNPATTERNED_NAME]
    assert seen[0]["text"] == NAME
    assert seen[0]["entities"] == [one.presidio_name for one in PRESIDIO_BUILT_INS]
    status[0] = 500
    with pytest.raises(AnalyserUnavailableError):
        detect(NAME, timeout_seconds=1.0)


# ------------------------------------------------------------------------ the transports
def provider_answering(text: str) -> tuple[httpx.Client, list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []

    def answer(call: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(call.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(answer)), bodies


def test_a_hosted_provider_is_posted_no_value_and_its_answer_is_put_back() -> None:
    """The one function that posts to a provider, end to end: the body that leaves holds the
    placeholders and none of the values, and the answer read back has them again. Delete this and
    `http_transport` can stop calling the scrub with every unit test of the scrub still green."""
    from brain.models.wire import PROVIDER_WIRES, http_transport

    client, bodies = provider_answering("[sg_nric_1] is known.")
    send = http_transport(PROVIDER_WIRES["moonshot"], client=client, key=lambda: "test-key")
    completion = send(request(QUESTION))
    assert NRIC not in json.dumps(bodies) and "[sg_nric_1]" in json.dumps(bodies)
    assert completion.text == f"{NRIC} is known."


def test_the_installs_own_server_is_sent_the_text_as_it_is() -> None:
    """The local server is inside the client's network, so it is not scrubbed for. Delete this
    and every answer on an install that chose a local model is degraded for no one's privacy."""
    from brain.models.wire import http_transport, local_wire

    client, bodies = provider_answering("fine")
    http_transport(local_wire("http://inference.test:8000"), client=client)(request(QUESTION))
    assert NRIC in json.dumps(bodies)


# ------------------------------------------------------------------------ no other way out
def _modules() -> list[tuple[Path, ast.Module]]:
    return [(one, ast.parse(one.read_text(encoding="utf-8"))) for one in SRC.rglob("*.py")]


def _calls_named(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        one
        for one in ast.walk(node)
        if isinstance(one, ast.Call)
        and (
            (isinstance(one.func, ast.Name) and one.func.id == name)
            or (isinstance(one.func, ast.Attribute) and one.func.attr == name)
        )
    ]


def test_every_model_transport_in_the_source_sends_through_the_egress_scrub() -> None:
    """**No other path.** Every function under `src/brain` that returns a model `Transport` calls
    `third_party_call`; the provider body is built and posted only inside `http_transport`; the
    SDK is called only inside `litellm_transport`; and every `SdkDriver` is handed a transport one
    of those built. Delete this and a third transport, or a driver handed a hand-written one, can
    send a question to a provider unscrubbed with every other test green."""
    producers: dict[str, bool] = {}
    builds_a_body: set[str] = set()
    calls_the_sdk: set[str] = set()
    drivers_given: set[str] = set()
    for path, module in _modules():
        for function in ast.walk(module):
            if not isinstance(function, ast.FunctionDef):
                continue
            returns = function.returns
            if isinstance(returns, ast.Name) and returns.id == "Transport":
                producers[function.name] = bool(_calls_named(function, "third_party_call"))
        if _calls_named(module, "request_body"):
            builds_a_body.add(path.name)
        for call in _calls_named(module, "completion"):
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                calls_the_sdk.add(f"{path.name}:{call.func.value.id}")
        for call in _calls_named(module, "SdkDriver"):
            for keyword in call.keywords:
                if keyword.arg == "transport" and isinstance(keyword.value, ast.Call):
                    func = keyword.value.func
                    drivers_given.add(func.id if isinstance(func, ast.Name) else ast.unparse(func))
    assert producers == {"http_transport": True, "litellm_transport": True}
    assert builds_a_body == {"wire.py"}
    assert calls_the_sdk == {"adapter.py:instance"}
    assert drivers_given <= {"http_transport", "make_transport", "self._make_transport"}
    assert drivers_given


def test_a_built_in_enabled_with_no_kind_is_a_configuration_finding() -> None:
    """`pii.configuration_gaps` reports a built-in with no kind to scrub it as, because every
    analysis that found one would be refused. Delete this and enabling a built-in quietly turns
    the analyser off for every text that holds one."""
    from brain.ops.pii import BuiltIn, configuration_gaps

    extra = BuiltIn("PHONE_NUMBER", 0.5, "an international number has many shapes")
    findings = configuration_gaps(built_ins=(*PRESIDIO_BUILT_INS, extra))
    assert findings == (
        "PHONE_NUMBER: enabled with no kind to scrub it as, so its spans would be refused",
    )
    assert configuration_gaps() == ()
