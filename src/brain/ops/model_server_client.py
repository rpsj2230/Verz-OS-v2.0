"""The one client of the model server's document parts, which decides nothing.

`brain.ops.inference_client` is the embedding leg's client and this is the other one: a document
sent to the layout, scanned-page or general-reader part, and what came back, as an outcome the
parsers already know how to read. The split is the one that module states about itself and
for the same reason: the cases that matter on this leg are a server that does not answer, one that
is busy, one that is loading a part and one that answers with something nobody expected, and none
of them can be tested through a module that decides what a document is worth.

**A part that is not loaded is an outage and never a fact about the document.** The server loads a
part when work for it arrives, which takes seconds to minutes, and refuses with a 503 and a
retry hint when the host has no room for it or another part is serving. Every one of those arrives
here as `CallOutcome.UNAVAILABLE`, which the parsers turn into `PARSER_UNAVAILABLE`, which is
retryable, so the ingest job waits and nothing is lost. A client that read a 503 as "this file
cannot be read" would end a document because a part was starting.

**The same breaker as the embedding leg, because it is the same server.** A server known to be
down is down for both, and one that is failing one leg's requests should not be sent a document by
the other while it recovers. Each client holds its own state for it (`CircuitBreaker` is a value),
keyed by the same name.

**The server's own account of its memory is kept and never decides anything.** An answer carries a
`memory` block when the server could measure the request; it is handed to the observer, which
writes it down (`brain.ops.model_server_store.record_peak`), inside a guard, because a statistic is
never a reason to lose the answer it rode with.

**No address is logged and no exception text is kept.** The address is where a client's documents
go, and a transport's message carries it.

Task ids: M7.2.1, M7.2.3, M7.2.4
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

import structlog

from brain.connectors.throttle import CallOutcome, classify, connector_breaker, record_outcome
from brain.knowledge.embed_policy import EmbeddingUnavailable, embedding_endpoint, endpoint_refusals
from brain.models.routing import CircuitBreaker
from brain.ops.inference_client import (
    BREAKER_NAME,
    InferenceTransport,
    TransportError,
    http_transport,
    jsonable,
)
from brain.ops.model_server import PATH_OF_PART, Part
from brain.ops.model_server_peaks import PeakReport, read_report

log = structlog.get_logger()

#: How long one document may take, in seconds. A little over the server's own request clock
#: (`inference_server.supervisor.REQUEST_SECONDS`, 900), so the server gives up on a document
#: before this side does and the answer is the server's refusal and not a timeout. A test holds
#: the two in that order.
DOCUMENT_TIMEOUT_SECONDS: Final = 960.0

#: Spelled as the supervisor's, which this repository's other program holds in its own file.
SERVER_REQUEST_SECONDS: Final = 900.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Reply:
    """What a part said: how the call went, and the body only when it went well."""

    outcome: CallOutcome
    payload: Mapping[str, object] = field(default_factory=dict)


def part_url(base_url: str, part: Part) -> str:
    """Where a part is posted to, or a refusal naming every reason the address is not one.

    The same refusals as the embedding leg's (`endpoint_refusals`), because the address is the
    same one, and a joiner that trusted its input would build a relative URL out of an empty one.
    """
    address = base_url.strip()
    findings = endpoint_refusals(address)
    if findings:
        msg = "; ".join(findings)
        raise ValueError(msg)
    return f"{address.rstrip('/')}{PATH_OF_PART[part]}"


@dataclass
class ModelServerClient:
    """Sends a request body to one part and reads back an outcome. Mutable for its breaker."""

    transport: InferenceTransport
    base_url: str
    timeout_seconds: float = DOCUMENT_TIMEOUT_SECONDS
    breaker: CircuitBreaker = field(default_factory=lambda: connector_breaker(BREAKER_NAME))
    clock: Callable[[], datetime] = _utc_now
    #: Told what the server measured of itself for a request, when its answer carried one.
    observer: Callable[[PeakReport], None] | None = None

    def ask(self, part: Part, request: object) -> Reply:
        """One request, as an outcome. Never raises for the server being down or unwell.

        The breaker is claimed before the request and released by the outcome, as the embedding
        client does, so a half-open probe nothing released cannot leave it admitting one caller
        that never arrives.
        """
        self.breaker, admitted = self.breaker.try_admit(self.clock())
        if not admitted:
            return Reply(CallOutcome.UNAVAILABLE)
        try:
            response = self.transport.post(
                part_url(self.base_url, part),
                json=jsonable(request),
                timeout=self.timeout_seconds,
            )
        except TransportError as error:
            outcome = classify(timed_out=error.timed_out, connection_failed=not error.timed_out)
            self.breaker = record_outcome(self.breaker, outcome, now=self.clock())
            log.warning("model server unreachable", part=part.value, timed_out=error.timed_out)
            return Reply(outcome)
        outcome = classify(status=response.status_code)
        self.breaker = record_outcome(self.breaker, outcome, now=self.clock())
        if outcome is not CallOutcome.OK:
            return Reply(outcome)
        try:
            payload = response.json()
        except ValueError:
            return Reply(CallOutcome.REJECTED)
        if not isinstance(payload, Mapping):
            return Reply(CallOutcome.REJECTED)
        self._observed(part, payload)
        return Reply(CallOutcome.OK, payload)

    def _observed(self, part: Part, payload: Mapping[str, object]) -> None:
        """Hand the server's account of its memory to whoever keeps it, never failing the call."""
        if self.observer is None:
            return
        report = read_report(payload, part=part)
        if report is None:
            return
        try:
            self.observer(report)
        except Exception as error:
            log.warning("the model server's peak was not kept", error=type(error).__name__)


def make_model_server_client(
    env: Mapping[str, str] | None = None,
    observer: Callable[[PeakReport], None] | None = None,
) -> ModelServerClient:
    """A client pointed at this install's model server, at the one address it is given.

    There is no address parameter, for the reason `inference_client.make_client` has none: a second
    answer to where a client's documents go, beside the declared one, is the failure
    `INSTALL_MODEL_ENDPOINT` being read in one place exists to prevent.
    """
    return ModelServerClient(
        transport=http_transport(), base_url=embedding_endpoint(env), observer=observer
    )


#: How long the readiness route may take from here. It reads the disk and answers.
READY_TIMEOUT_SECONDS: Final = 5.0

#: The route the server answers readiness on. Spelled as `inference_server.gateway.READY_PATH`.
READY_PATH: Final = "/ready"


async def server_readiness(
    env: Mapping[str, str] | None = None, *, timeout_seconds: float = READY_TIMEOUT_SECONDS
) -> tuple[int, Mapping[str, object]] | None:
    """What the server's readiness route says, with its status, or None when it said nothing usable.

    The body is read whatever the status is, because a server that is not ready says why in it.
    None for an address that is not an origin, a server that did not answer, and an answer that is
    not an object: nothing here raises, because the callers are a screen that must still draw and a
    check that has its own sentence for each.
    """
    import httpx

    try:
        address = embedding_endpoint(env).rstrip("/")
    except Exception:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            answer = await client.get(f"{address}{READY_PATH}")
            body = answer.json()
            status = answer.status_code
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(body, Mapping):
        return None
    return status, body


def held_embedding_revision(body: Mapping[str, object]) -> str | None:
    """The revision of the embedding weights a readiness answer says the server holds, or None."""
    revisions = body.get("revisions")
    if not isinstance(revisions, Mapping):
        return None
    held = revisions.get("embedding")
    return held if isinstance(held, str) and held else None


def entity_endpoint(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> str | None:
    """Where the install's entity model answers, or None where it runs none.

    **Decided from two settings and no database**: the model server is one of the install's optional
    services and the entity part is one of its chosen parts. Both are things a person set on
    purpose (the default is neither), so an install that did nothing sends nothing here. This is
    read when the process starts, as the analyser's address is, because the detector is built once
    with the model driver; a change reaches it at the next start. A setting that cannot be read is
    no entity model, and the rules' scrub stands.
    """
    from brain.ops.inference import is_switched_on
    from brain.ops.model_server import ModelServerError, read_config

    if not is_switched_on(env, saved):
        return None
    try:
        if Part.ENTITIES not in read_config(env, saved).parts:
            return None
        return embedding_endpoint(env)
    except (ModelServerError, EmbeddingUnavailable):
        return None
