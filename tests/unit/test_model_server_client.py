"""The one client of the model server's document parts, which decides nothing.

Held here: a part that does not answer, is loading or is busy is an outcome and never an exception
and never a fact about the document; the server's own account of its memory reaches whoever keeps
it and never costs the answer it rode with; the breaker stops a queue from spending a request on a
server already known to be down; and the clock this side waits on is longer than the one the
server's supervisor holds, so a document the server gives up on is its refusal and not our timeout.

Task ids: M7.2.1, M7.2.3, M7.2.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.connectors.throttle import CallOutcome
from brain.models.routing import BREAKER_CONSECUTIVE_FAILURES
from brain.ops.inference_client import TransportError
from brain.ops.model_server import PATH_OF_PART, Part
from brain.ops.model_server_client import (
    DOCUMENT_TIMEOUT_SECONDS,
    SERVER_REQUEST_SECONDS,
    ModelServerClient,
    part_url,
)
from brain.ops.model_server_peaks import REPORT_KEY, PeakReport
from inference_server import supervisor

BASE = "http://inference:8080"
NOW = datetime(2999, 1, 1, tzinfo=UTC)
REPORT = {
    "model": "docling-layout-and-tableformer",
    "items": 4,
    "request_bytes": 9000,
    "duration_ms": 1200,
    "anon_peak_mib": 700,
    "cache_peak_mib": 20,
    "cgroup_limit_mib": 1344,
}


@dataclass
class _Response:
    status_code: int
    payload: object = None

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@dataclass
class _Transport:
    response: _Response | None = None
    raises: TransportError | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def post(self, url: str, *, json: object, timeout: float) -> _Response:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        assert self.response is not None
        return self.response


def _client(transport: _Transport, seen: list[PeakReport] | None = None) -> ModelServerClient:
    def keep(report: PeakReport) -> None:
        assert seen is not None
        seen.append(report)

    return ModelServerClient(
        transport=transport,
        base_url=BASE,
        clock=lambda: NOW,
        observer=keep if seen is not None else None,
    )


def test_a_part_is_posted_to_the_path_the_server_declares_for_it() -> None:
    """Every part has its own path, joined to the one address, whatever trailing slash it has.

    Delete this and a renamed path is a 404 the application reads as its own fault."""
    for part, path in PATH_OF_PART.items():
        assert part_url(BASE, part) == f"{BASE}{path}"
        assert part_url(f"{BASE}/", part) == f"{BASE}{path}"


@pytest.mark.parametrize("address", ["", "  ", "inference:8080", "ftp://inference", "http://u:p@h"])
def test_an_address_that_is_not_an_origin_is_refused_before_a_document_is_sent(
    address: str,
) -> None:
    """An empty address would build a relative URL; a credential in one would be logged. The same
    refusals the embedding leg makes, because it is the same address.

    Delete this and a document's bytes are posted wherever a bad setting points."""
    with pytest.raises(ValueError):
        part_url(address, Part.LAYOUT)


def test_a_good_answer_is_an_ok_outcome_with_its_body_and_the_request_is_json_the_part_reads() -> (
    None
):
    """The positive case: the body comes back, the request went to the part's path under the
    document timeout, and a read-only mapping was turned into plain JSON on the way out.

    Delete this and every refusal below is satisfied by a client that never succeeds."""
    transport = _Transport(response=_Response(200, {"blocks": []}))

    reply = _client(transport).ask(Part.LAYOUT, {"document": {"digest": "d"}})

    assert reply.outcome is CallOutcome.OK and dict(reply.payload) == {"blocks": []}
    [call] = transport.calls
    assert call["url"] == f"{BASE}{PATH_OF_PART[Part.LAYOUT]}"
    assert call["json"] == {"document": {"digest": "d"}}
    assert call["timeout"] == DOCUMENT_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (503, CallOutcome.UNAVAILABLE),
        (500, CallOutcome.UNAVAILABLE),
        (429, CallOutcome.QUOTA),
        (413, CallOutcome.REJECTED),
        (404, CallOutcome.REJECTED),
    ],
)
def test_a_status_is_an_outcome_and_never_an_exception(status: int, outcome: CallOutcome) -> None:
    """A part still loading, a host with no room and a busy server all answer 503, which is an
    outage; a request the server will not take is rejected. Neither raises.

    Delete this and a part that was starting ends a document as unreadable."""
    reply = _client(_Transport(response=_Response(status))).ask(Part.OCR, {})

    assert reply.outcome is outcome
    assert dict(reply.payload) == {}


@pytest.mark.parametrize("timed_out", [True, False])
def test_a_server_that_does_not_answer_is_an_outage_whether_it_was_slow_or_absent(
    timed_out: bool,
) -> None:
    """A timeout and a refused connection are one event here, because neither says anything about
    the document.

    Delete this and a slow server reads as a file that cannot be read."""
    transport = _Transport(raises=TransportError("ConnectError", timed_out=timed_out))

    reply = _client(transport).ask(Part.TIKA, {})

    assert reply.outcome is CallOutcome.UNAVAILABLE


@pytest.mark.parametrize("payload", ["text", ["a"], None, ValueError("not json")])
def test_an_answer_that_is_not_an_object_is_rejected_and_not_read_as_empty(payload: object) -> None:
    """A body that is not JSON, or not an object, is the contract failing and not a document with
    nothing in it.

    Delete this and a garbled answer is decoded as no blocks, which is read as a scan."""
    reply = _client(_Transport(response=_Response(200, payload))).ask(Part.LAYOUT, {})

    assert reply.outcome is CallOutcome.REJECTED


def test_a_breaker_that_has_opened_stops_the_request_leaving_the_process() -> None:
    """After the consecutive failures it allows the breaker opens and the next call is an outage
    without a request: the transport's call count is what shows it.

    Delete this and a queue of documents spends one request each on a server known to be down."""
    transport = _Transport(response=_Response(503))
    client = _client(transport)

    for _ in range(BREAKER_CONSECUTIVE_FAILURES):
        assert client.ask(Part.LAYOUT, {}).outcome is CallOutcome.UNAVAILABLE
    sent = len(transport.calls)
    refused = client.ask(Part.LAYOUT, {})

    assert sent == BREAKER_CONSECUTIVE_FAILURES
    assert refused.outcome is CallOutcome.UNAVAILABLE
    assert len(transport.calls) == sent


def test_a_quota_refusal_does_not_open_the_breaker() -> None:
    """A 429 is not ill health: any number of them leaves the breaker closed.

    Delete this and a busy server is treated as a broken one and documents stop being sent."""
    transport = _Transport(response=_Response(429))
    client = _client(transport)

    for _ in range(BREAKER_CONSECUTIVE_FAILURES + 2):
        client.ask(Part.LAYOUT, {})

    assert len(transport.calls) == BREAKER_CONSECUTIVE_FAILURES + 2


def test_the_servers_report_is_kept_against_the_part_asked_and_losing_it_loses_nothing() -> None:
    """The report rides in the answer, is attributed to the part the caller asked (not whatever
    the server claims), and an observer that raises does not cost the answer.

    Delete this and a database that refuses a row of figures takes a document's blocks with it."""
    seen: list[PeakReport] = []
    answer = {"blocks": [], REPORT_KEY: REPORT}

    kept = _client(_Transport(response=_Response(200, answer)), seen).ask(Part.LAYOUT, {})

    assert dict(kept.payload) == answer
    [report] = seen
    assert report.part is Part.LAYOUT and report.anon_peak_mib == 700

    def refuse(report: PeakReport) -> None:
        raise RuntimeError("the table refused a row")

    client = _client(_Transport(response=_Response(200, answer)))
    client.observer = refuse
    assert client.ask(Part.LAYOUT, {}).outcome is CallOutcome.OK


def test_this_side_waits_longer_than_the_servers_own_request_clock() -> None:
    """The document timeout is longer than the supervisor's per-request limit, and the figure
    spelled here is the supervisor's.

    Delete this and a document the server is still working on is abandoned by this side first, so
    its refusal is never heard and the document is sent again."""
    assert SERVER_REQUEST_SECONDS == supervisor.REQUEST_SECONDS
    assert DOCUMENT_TIMEOUT_SECONDS > SERVER_REQUEST_SECONDS


# ------------------------------------------------------------------ the readiness route
def _mock(handler: Any) -> Any:
    import httpx

    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return client


def test_readiness_gives_the_status_and_the_body_whatever_the_status_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server that is not ready says why in the body of a 503, and that body is returned with
    its status; the revision it states is read out of it.

    Delete this and a server that is not ready is a server that said nothing."""
    import asyncio

    import httpx

    from brain.ops.model_server_client import held_embedding_revision, server_readiness

    body = {"ready": False, "gaps": ["a"], "revisions": {"embedding": "abc123def456"}}
    monkeypatch.setattr(httpx, "AsyncClient", _mock(lambda request: httpx.Response(503, json=body)))

    answered = asyncio.run(server_readiness({"INSTALL_MODEL_ENDPOINT": BASE}))

    assert answered is not None and answered[0] == 503 and dict(answered[1]) == body
    assert held_embedding_revision(answered[1]) == "abc123def456"
    assert held_embedding_revision({"revisions": {"embedding": 12}}) is None
    assert held_embedding_revision({"revisions": ["embedding"]}) is None
    assert held_embedding_revision({}) is None


@pytest.mark.parametrize("kind", ["silent", "array", "not-json"])
def test_readiness_says_nothing_for_a_server_that_is_silent_or_answers_nonsense(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """None, and never an exception, for a refused connection, an answer that is not an object and
    one that is not JSON: the callers are a page that must still draw and a check with a sentence
    for each.

    Delete this and a server that is down makes the model server screen an error."""
    import asyncio

    import httpx

    from brain.ops.model_server_client import server_readiness

    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "silent":
            raise httpx.ConnectError("refused", request=request)
        if kind == "array":
            return httpx.Response(200, json=["not", "an", "object"])
        return httpx.Response(200, content=b"<html>")

    monkeypatch.setattr(httpx, "AsyncClient", _mock(handler))

    assert asyncio.run(server_readiness({"INSTALL_MODEL_ENDPOINT": BASE})) is None


def test_an_address_that_is_not_an_origin_is_no_answer_and_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A setting that names no origin gets None and no request at all.

    Delete this and a bad address is dialled, or the page that shows it is an error."""
    import asyncio

    import httpx

    from brain.ops.model_server_client import server_readiness

    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", _mock(handler))

    assert asyncio.run(server_readiness({"INSTALL_MODEL_ENDPOINT": "ftp://nowhere"})) is None
    assert sent == []
