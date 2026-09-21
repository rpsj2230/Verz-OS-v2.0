"""The live answer path records what the redactor withheld, and states a department out of reach.

Driven through the real `/answer` route, with the model step and passage search of
`tests/unit/test_answer_route_model.py` and a trace sink that keeps what it was handed.

**M4.4.4.** The trace the sink receives is the redactor's own: the fields it withheld, by name, and
how many, and never a value. `CountingTraceSink`, the sink the application installs, writes the
names and the counts to its log line and nothing else.

**M2.2.4.** A department the question names outside the reader's scope is stated after the text,
in words that are the same for a department that exists and one that does not.

Task ids: M4.4.4, M2.2.4
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain.api import API_PREFIX
from brain.core.department import GAP_TEMPLATE, departments_named, gaps_for_question
from brain.core.entitlement import Capability, Grant
from brain.core.redaction import ChannelPayload, RedactionTrace
from brain.core.scope import Scope
from brain.ops.trace_sink import CountingTraceSink
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_answer_route_model import READER, READER_GRANTS
from tests.unit.test_answer_route_model import client as client
from tests.unit.test_answer_route_model import transport as transport
from tests.unit.test_model_lane import VISIBLE
from tests.unit.test_streaming import decode

QUESTION = "how much annual leave do we get"


class Kept:
    """A trace sink that keeps every trace it is handed."""

    def __init__(self) -> None:
        self.traces: list[RedactionTrace] = []

    def emit(self, reference: str, payload: ChannelPayload, trace: RedactionTrace) -> None:
        del reference, payload
        self.traces.append(trace)


def _without(capability: str) -> tuple[Grant, ...]:
    return tuple(one for one in READER_GRANTS[READER] if one.capability.value != capability)


def _text(client: TestClient, question: str) -> str:
    answered = client.post(
        f"{API_PREFIX}/answer", headers=headers(READER), json={"question": question}
    )
    assert answered.status_code == 200
    return next(one.data for one in decode(answered.text) if one.event == "text")


def test_the_sink_is_handed_the_redactors_trace_with_the_withheld_field_named(
    client: TestClient,
) -> None:
    """M4.4.4: a reader without the passage title is answered, and the trace handed to the sink
    names `knowledge.title` as withheld, once, and carries none of its value.

    Delete this and the lane can go back to an empty trace beside the payload, and the record says
    nothing was withheld on the requests where something was."""
    kept = Kept()
    client.app.state.trace_sink = kept  # type: ignore[attr-defined]
    client.app.state.gate = gate_wiring({READER: _without("read:knowledge.title")})  # type: ignore[attr-defined]
    _text(client, QUESTION)
    (trace,) = kept.traces
    assert trace.withheld_field_names() == (f"{VISIBLE.entity}.title",)
    assert trace.redaction_count == 1
    assert "LOCKEDTITLEVERMILION" not in trace.model_dump_json()


def test_the_applications_sink_logs_the_names_and_counts_and_never_a_value(
    client: TestClient,
) -> None:
    """What the installed sink writes: the withheld names and the counts, no value."""
    client.app.state.trace_sink = CountingTraceSink()  # type: ignore[attr-defined]
    client.app.state.gate = gate_wiring({READER: _without("read:knowledge.title")})  # type: ignore[attr-defined]
    with capture_logs() as logs:
        _text(client, QUESTION)
    (line,) = [one for one in logs if one.get("event") == "trace"]
    assert line["withheld"] == [f"{VISIBLE.entity}.title"]
    assert line["redactions"] == 1
    assert "LOCKEDTITLEVERMILION" not in str(line)


def _in_web_only(client: TestClient) -> None:
    grants: tuple[Grant, ...] = (
        *_without("read:knowledge"),
        Grant(capability=Capability(value="read:knowledge"), scope=Scope.department("web")),
    )
    client.app.state.gate = gate_wiring({READER: grants})  # type: ignore[attr-defined]


def test_a_department_out_of_reach_is_stated_in_the_answer_whether_or_not_it_exists(
    client: TestClient,
) -> None:
    """M2.2.4: a reader of the web department asks about finance and about a department nobody
    created; both answers state the gap in the same words, and asking about web states none.

    Delete this and an answer about another department reads as complete, or states the gap only
    for departments that exist, which is the org chart disclosed by asking."""
    _in_web_only(client)
    finance = _text(client, f"{QUESTION} in the finance department")
    zebra = _text(client, f"{QUESTION} in the zebra department")
    web = _text(client, f"{QUESTION} in the web department")
    assert GAP_TEMPLATE.format(department="finance") in finance
    assert GAP_TEMPLATE.format(department="zebra") in zebra
    assert finance.replace("finance", "X") == zebra.replace("zebra", "X")
    assert "outside the scopes you hold" not in web


def test_departments_are_read_from_the_wording_and_never_from_a_registry() -> None:
    """The extraction takes what the question calls a department, in order, once each."""
    named = departments_named("Compare the Finance department with the department of sales, dept")
    assert named == ("finance", "sales")
    assert departments_named("what does our department do") == ()
    # A reader holding no knowledge read at all: every named department is a gap.
    assert [gap.department for gap in gaps_for_question("the hr department", None)] == ["hr"]
    assert gaps_for_question("the hr department", Scope.unrestricted()) == ()
