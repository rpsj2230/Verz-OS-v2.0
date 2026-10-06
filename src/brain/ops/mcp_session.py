"""The half of the MCP client that talks: one session with one server, over the pinned connection.

`brain.connectors.mcp` decides what every message is and what every answer means; this sends them.
One session is opened per worker attempt and per live read: initialise, say so, list the tools and
check every tool the reading calls is listed as it was reviewed, then one `tools/call` per entity.
The worker's run (`brain.ops.connector_sync_run`) and a question's read (`brain.ops.live_read_run`)
both open it through `open_session` and read through `read_entity`, so the two cannot come to send
different things to one server.

**Every request is a POST to the address the address rule checked, through `SourcePoster`**, the
same pinned connection a Google token exchange and an Analytics report go through, with the run's
timeout and the response bound every source is read with. The address is checked once per session,
before the first request, and every request goes to the address that check returned. See
`brain.connectors.mcp.THE_PROTOCOL_GOES_THROUGH_THE_PINNED_CONNECTION`.

**The key is in the headers the caller built and nowhere here.** The run builds the one
`Authorization` header with `connector_sync_run.authorization`, as it does for a REST source, and
hands this module headers; nothing here reads the key, logs a header or keeps an answer longer
than one request. A failure is raised as its kind (`CallNotAnsweredError.call`), never with the
server's text.

**Every request is admitted before it is sent.** `admit` is asked before each POST and a request
it refuses is not sent: the worker's run passes the source's verified ceiling, so a session takes
its share of the source's minute request by request, and a question's read passes one that admits
everything, because the live read's executor has already admitted the question's read. A request
the ceiling refuses ends the session as this install's share spent, and the next run reads the
source again; it is not waited for inside the session, because a session is one synchronous
conversation and waiting inside it would hold the worker's event loop.

**The session is not ended with a DELETE.** The specification lets a client end it and lets a
server expire it, and a reading opens one per attempt; a DELETE would be one more request admitted
against the source's ceiling to save the server a timeout. Not built, and said here so nobody
wonders whether it was forgotten.

Task ids: M11.1.2
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from brain.connectors.mcp import (
    ACCEPT,
    SESSION_HEADER,
    VERSION_HEADER,
    McpProtocolError,
    assert_as_reviewed,
    initialize_params,
    jsonrpc_request,
    listed_tools,
    negotiated,
    notification_body,
    reply_to,
)
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.tools.fetch import Resolver, assert_fetchable

if TYPE_CHECKING:
    from brain.connectors.declaration import PageReply, ToolReading
    from brain.ops.connector_sync_run import SourceAnswer, SourcePoster

#: How many `tools/list` pages a session reads before it gives up on finding the tools it calls.
#: A server listing more tools than four pages hold is listing far more than a reading needs, and
#: an unbounded list is a server that can keep a worker attempt open for as long as it likes.
MAX_TOOL_PAGES: Final = 4

#: How many requests opening a session takes before its first `tools/list` page: initialise, and
#: the notification that it is done.
OPENING_REQUESTS: Final = 2


class CallNotAnsweredError(Exception):
    """A call was not answered: refused, unavailable, timed out, or over the source's allowance.

    Carries the kind of failure and what the source asked to wait, and never the answer's text.
    Shared with `brain.ops.custom_code_run`, whose planned calls fail the same ways.
    """

    def __init__(
        self, call: CallOutcome, *, timed_out: bool = False, retry_after: float | None = None
    ) -> None:
        super().__init__(f"a call to a source came back {call.value}")
        self.call = call
        self.timed_out = timed_out
        self.retry_after = retry_after


class CallNotAdmittedError(Exception):
    """The source's ceiling did not admit the next call, so it was not sent."""


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if key.casefold() == "retry-after":
            try:
                return float(str(value).strip())
            except ValueError:
                return None
    return None


@dataclass
class McpSession:
    """One conversation with one MCP server. Private state; built only by `open_session`."""

    poster: SourcePoster
    url: str
    address: str
    headers: Mapping[str, str]
    admit: Callable[[], bool]
    session_id: str = ""
    version: str = ""
    sent: int = 0
    _next_id: int = 1

    def __repr__(self) -> str:
        return f"McpSession(sent={self.sent}, open={bool(self.version)})"

    def _post(self, body: bytes) -> SourceAnswer:
        if not self.admit():
            raise CallNotAdmittedError
        headers = {
            **self.headers,
            "Accept": ACCEPT,
            "Content-Type": "application/json",
            **({SESSION_HEADER: self.session_id} if self.session_id else {}),
            **({VERSION_HEADER: self.version} if self.version else {}),
        }
        answer = self.poster.post(
            self.url, address=self.address, headers=headers, body=body, max_bytes=MAX_RESPONSE_BYTES
        )
        self.sent += 1
        call = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed or answer.status is None,
        )
        if call is not CallOutcome.OK:
            said = answer.headers or {}
            wait = _retry_after(said) if call is CallOutcome.QUOTA else None
            raise CallNotAnsweredError(call, timed_out=answer.timed_out, retry_after=wait)
        return answer

    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """One request and the result of its response."""
        request_id, self._next_id = self._next_id, self._next_id + 1
        answer = self._post(jsonrpc_request(request_id, method, params))
        said = {key.lower(): value for key, value in (answer.headers or {}).items()}
        if method == "initialize":
            self.session_id = said.get(SESSION_HEADER.lower(), "")
        return reply_to(request_id, content_type=said.get("content-type", ""), body=answer.body)

    def notify(self, method: str) -> None:
        """One notification. Its answer has no body, and any status but a refusal is accepted."""
        self._post(notification_body(method))

    def tools(self) -> tuple[Mapping[str, Any], ...]:
        """Every tool the server lists, page by page, up to `MAX_TOOL_PAGES`."""
        found: list[Mapping[str, Any]] = []
        cursor: str | None = None
        for _ in range(MAX_TOOL_PAGES):
            page, cursor = listed_tools(
                self.request("tools/list", {} if cursor is None else {"cursor": cursor})
            )
            found.extend(page)
            if cursor is None:
                return tuple(found)
        msg = f"the MCP server listed its tools over more than {MAX_TOOL_PAGES} pages"
        raise McpProtocolError(msg)


def open_session(
    reading: ToolReading,
    *,
    settings: Mapping[str, str],
    headers: Mapping[str, str],
    poster: SourcePoster,
    resolver: Resolver,
    admit: Callable[[], bool],
) -> McpSession:
    """A session opened, its revision agreed, and every tool the reading calls listed as reviewed.

    Raises `UnsafeAddressError` for an address the rule refuses, before anything is sent;
    `CallNotAnsweredError` and `CallNotAdmittedError` for a request not answered or not sent;
    `McpProtocolError` for an answer the protocol does not describe; and
    `McpToolNotAsReviewedError` for a tool not listed as it was pinned.
    """
    checked = assert_fetchable(reading.endpoint(settings), resolver)
    session = McpSession(
        poster=poster, url=checked.url, address=checked.address, headers=headers, admit=admit
    )
    session.version = negotiated(session.request("initialize", initialize_params()))
    session.notify("notifications/initialized")
    assert_as_reviewed(reading.pinned(), session.tools())
    return session


def read_entity(
    session: McpSession,
    reading: ToolReading,
    entity: str,
    source_id: str | None,
    *,
    fetched_at: str,
) -> PageReply:
    """One entity listed, or one record read, by the declared tool, as the reading reads it."""
    tool, arguments = reading.tool_call(entity, source_id)
    result = session.request("tools/call", {"name": tool, "arguments": dict(arguments)})
    return reading.interpret_tool(entity, result, fetched_at=fetched_at)
