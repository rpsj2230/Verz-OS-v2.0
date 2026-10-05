"""Reading a source that is an MCP server: the protocol's messages, and what a tool's answer means.

`brain.connectors.transports.McpTransport` declared an MCP server and the exact set of its tools
this product exposes, and until this module nothing could talk to one. This is the half of the
client that decides: the JSON-RPC messages a session sends, how an answer is read whether the
server framed it as JSON or as an event stream, what a tool's definition is pinned by, and what a
`tools/call` result means for one entity. `brain.ops.mcp_session` is the half that talks, over the
same pinned connection and leased key every other source is read with, and it decides nothing.

**The protocol is written here, small, rather than taken from the MCP SDK.** The project depends
on no MCP library, and the SDK would bring an async HTTP client, an event-stream library and
its own transport for the one thing every other source here already has: a POST to an address
the address rule checked, on a connection pinned to the address it checked
(`brain.ops.connector_sync_run.HttpsSourceCaller`). Taking the SDK's transport would mean either
a second, unpinned HTTP path to a third-party server, which is the DNS-rebinding hole
`brain.tools.fetch.Fetchable` exists to close, or wrapping the SDK around our caller, which is
more code than the protocol. What a read-only client needs from the specification (revision
2025-06-18, Streamable HTTP) is four messages, one header pair and one framing, and they are
written below in a form a test drives with a recorded exchange and no server. Rejected: the SDK,
for the pinned connection; and the older HTTP-plus-SSE transport, which the specification has
deprecated and which needs a long-lived stream a worker attempt cannot hold.

**Only tools the declaration names are called, each for one entity, and each is pinned.** A
reading names, per entity, the remote tool that lists it and the one that reads one record, and
every one of them must be a tool the transport's mapping declares
(`transports.AN_UNDECLARED_REMOTE_TOOL_IS_NOT_EXPOSED`). The session lists the server's tools
before calling any, and a declared tool that is missing, whose definition no longer hashes to
the digest it was reviewed at, or whose own annotations say it writes, is refused before it is
called. See `A_TOOL_IS_CALLED_ONLY_AS_IT_WAS_REVIEWED`. A server that redefines a tool between
two runs therefore stops being read, rather than being read by a tool nobody looked at.

**A tool's answer is read by the declared field mapping and nothing else.** A `tools/call`
result is the tool's structured content where it gives one, otherwise the JSON its first text
item holds; the records are at the entity's declared path and each is mapped by the same walk a
REST mapping uses (`brain.connectors.rest.mapped_row`), so an unmapped field never arrives. A
result the server marks as an error is a refusal, never an empty page, because an empty page
reads as a source with nothing in it.

**A reading also reads one record live, by the same tool's answer read the same way**, so a
question and a scheduled read cannot come to disagree about what the server said. It declares
the service's credentials (`IdentityMode.SERVICE`): one connection, one key, and no person's own
key for this server is held.

Scope: domain logic. Nothing here opens a connection, reads a key or holds a session.
Connectors never bulk-sync, and a reading built here keeps a minimal index and reads every value
live: what it keeps is the entity's declared `index` fields and nothing else.

Task ids: M11.1.2
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import SCHEMES_SENT_AS_THEY_ARE, KeyScheme, PageReply
from brain.connectors.projection import ProjectedRecord, ProjectedValue
from brain.connectors.rest import ID_TARGET, mapped_row, rows_at
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import (
    FieldMapping,
    McpTransport,
    TransportError,
    is_source_path,
    normalise,
)
from brain.core.envelope import OBJECT_NAME_PATTERN, IdentityMode

# ------------------------------------------------------------------ written-down reasons
#: Why a tool is listed and checked before it is called.
A_TOOL_IS_CALLED_ONLY_AS_IT_WAS_REVIEWED: Final = (
    "An MCP server defines its own tools and can change one between two connections. So a "
    "session lists the server's tools before calling any, and a tool the reading calls is "
    "refused when it is missing, when its definition no longer hashes to the digest it was "
    "reviewed at, or when its own annotations say it changes something. The source then stops "
    "being read until somebody reviews the new definition, rather than being read by a tool "
    "nobody looked at."
)

_REVIEWED: Final = A_TOOL_IS_CALLED_ONLY_AS_IT_WAS_REVIEWED

#: Why the protocol is written here. See the module docstring.
THE_PROTOCOL_GOES_THROUGH_THE_PINNED_CONNECTION: Final = (
    "Every call to an MCP server is a POST to the address the address rule checked, on the "
    "connection pinned to that address, with the leased key in one header: the path every other "
    "source is read through. An MCP library brings its own HTTP client, which would be a second, "
    "unpinned path to a server somebody else runs."
)

# ------------------------------------------------------------------ the protocol's words
#: The revision of the specification this client speaks, and asks for at initialisation.
PROTOCOL_VERSION: Final = "2025-06-18"

#: Revisions whose Streamable HTTP transport and tool results this client reads. A server that
#: answers initialisation with another is refused, as the specification says a client should.
SUPPORTED_VERSIONS: Final = frozenset({PROTOCOL_VERSION, "2025-03-26"})

#: What a POST accepts. The specification requires both: a server may answer a request with one
#: JSON object or with an event stream carrying it.
ACCEPT: Final = "application/json, text/event-stream"

#: The header a server may assign a session in, and every later request must carry it back in.
SESSION_HEADER: Final = "Mcp-Session-Id"

#: The header every request after initialisation names the negotiated revision in (2025-06-18).
VERSION_HEADER: Final = "MCP-Protocol-Version"

#: How this client names itself at initialisation. The product and nothing about the install.
CLIENT_INFO: Final = MappingProxyType({"name": "company-brain-connectors", "version": "1"})

#: The fields of a tool's definition its pin covers: what a model or a reviewer reads, and the
#: shapes the arguments and the answer take. Not `annotations`, which are hints and are judged
#: on their own by `says_it_writes`, and not `title`, which is a display name.
PINNED_FIELDS: Final = ("name", "description", "inputSchema", "outputSchema")

#: The longest record id laid into a tool's arguments. An id longer than any source issues is
#: content rather than a reference.
MAX_ID_CHARS: Final = 200

_NAME_RE: Final = re.compile(OBJECT_NAME_PATTERN)


class McpProtocolError(TransportError):
    """An MCP server answered in a shape the protocol does not describe. Names no value it sent."""


class McpToolNotAsReviewedError(TransportError):
    """A tool this reading calls is missing, redefined, or says it writes. See
    `A_TOOL_IS_CALLED_ONLY_AS_IT_WAS_REVIEWED`."""


# ------------------------------------------------------------------ messages
def jsonrpc_request(request_id: int, method: str, params: Mapping[str, Any]) -> bytes:
    """One JSON-RPC request, compact and in a stable key order."""
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")


def notification_body(method: str) -> bytes:
    """One JSON-RPC notification, which has no id and is answered with no body."""
    message = {"jsonrpc": "2.0", "method": method}
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")


def initialize_params() -> dict[str, Any]:
    """What a session opens with: the revision, no client capabilities, and the client's name.

    No capability is offered because a reading needs none of them: it samples no model, exposes
    no roots and asks the person nothing.
    """
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": dict(CLIENT_INFO),
    }


def _messages(content_type: str, body: bytes) -> list[Any]:
    """Every JSON-RPC message in a body, framed as JSON or as a server-sent event stream."""
    kind = content_type.split(";", 1)[0].strip().lower()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        msg = "an MCP answer was not UTF-8"
        raise McpProtocolError(msg) from None
    if kind == "application/json":
        try:
            decoded = json.loads(text)
        except ValueError:
            msg = "an MCP answer framed as JSON did not hold JSON"
            raise McpProtocolError(msg) from None
        return decoded if isinstance(decoded, list) else [decoded]
    if kind == "text/event-stream":
        found: list[Any] = []
        for event in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
            data = [
                line[5:].removeprefix(" ") for line in event.split("\n") if line.startswith("data:")
            ]
            if not data:
                continue
            try:
                found.append(json.loads("\n".join(data)))
            except ValueError:
                msg = "an MCP event held data that is not JSON"
                raise McpProtocolError(msg) from None
        return found
    msg = "an MCP answer was framed as neither JSON nor an event stream"
    raise McpProtocolError(msg)


def reply_to(request_id: int, *, content_type: str, body: bytes) -> Mapping[str, Any]:
    """The result of the response to `request_id`, from a JSON body or an event stream.

    A stream may carry the server's own requests and notifications before the response, and
    they are passed over: a reading answers none of them. A JSON-RPC error is refused with its
    code and never its message, which is the server's text and may quote what was asked.
    """
    for message in _messages(content_type, body):
        if not isinstance(message, Mapping) or message.get("id") != request_id:
            continue
        if "error" in message:
            error = message["error"]
            code = error.get("code") if isinstance(error, Mapping) else None
            msg = f"the MCP server answered request {request_id} with error code {code!r}"
            raise McpProtocolError(msg)
        result = message.get("result")
        if not isinstance(result, Mapping):
            msg = f"the MCP server's response to request {request_id} holds no result object"
            raise McpProtocolError(msg)
        return result
    msg = f"the MCP server's answer holds no response to request {request_id}"
    raise McpProtocolError(msg)


def negotiated(result: Mapping[str, Any]) -> str:
    """The revision an initialisation result names, when it is one this client speaks."""
    version = result.get("protocolVersion")
    if not isinstance(version, str) or version not in SUPPORTED_VERSIONS:
        msg = (
            f"the MCP server speaks revision {version!r}, and this client speaks "
            f"{sorted(SUPPORTED_VERSIONS)}"
        )
        raise McpProtocolError(msg)
    return version


def listed_tools(result: Mapping[str, Any]) -> tuple[tuple[Mapping[str, Any], ...], str | None]:
    """One `tools/list` page: the tool definitions, and the cursor of the next page or None."""
    tools = result.get("tools")
    if not isinstance(tools, list) or not all(
        isinstance(one, Mapping) and isinstance(one.get("name"), str) for one in tools
    ):
        msg = "a tools/list result holds no list of named tools"
        raise McpProtocolError(msg)
    cursor = result.get("nextCursor")
    return tuple(tools), cursor if isinstance(cursor, str) and cursor else None


# ------------------------------------------------------------------ the pin
def tool_digest(definition: Mapping[str, Any]) -> str:
    """SHA-256 over the parts of a tool's definition a reviewer read. See `PINNED_FIELDS`.

    Canonical JSON (sorted keys, no spaces), so one definition has one digest however the server
    happened to order or space it.
    """
    pinned = {name: definition[name] for name in PINNED_FIELDS if name in definition}
    text = json.dumps(pinned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def says_it_writes(definition: Mapping[str, Any]) -> bool:
    """Whether a tool's own annotations say it is not read-only, or that it destroys something.

    Only an explicit word counts. The specification's defaults for an absent annotation are the
    pessimistic ones, and reading an absence as a claim would refuse every server that annotates
    nothing; what is refused here is a server telling us, in so many words, that a tool writes.
    """
    notes = definition.get("annotations")
    if not isinstance(notes, Mapping):
        return False
    return notes.get("readOnlyHint") is False or notes.get("destructiveHint") is True


def assert_as_reviewed(pinned: Mapping[str, str], listed: tuple[Mapping[str, Any], ...]) -> None:
    """Refuse when a tool this reading calls is not listed as it was reviewed.

    See `A_TOOL_IS_CALLED_ONLY_AS_IT_WAS_REVIEWED`. The message names the tool and which of the
    three it was, and nothing the server said about it.
    """
    by_name = {str(one["name"]): one for one in listed}
    for name in sorted(pinned):
        definition = by_name.get(name)
        if definition is None:
            msg = f"the MCP server no longer lists {name!r}. {_REVIEWED}"
            raise McpToolNotAsReviewedError(msg)
        if tool_digest(definition) != pinned[name]:
            msg = f"{name!r} is not defined as it was reviewed. {_REVIEWED}"
            raise McpToolNotAsReviewedError(msg)
        if says_it_writes(definition):
            msg = f"{name!r} says it writes. {_REVIEWED}"
            raise McpToolNotAsReviewedError(msg)


# ------------------------------------------------------------------ a tool's answer
def tool_records(result: Mapping[str, Any], path: str) -> tuple[Mapping[str, Any], ...] | None:
    """The records a `tools/call` result holds at `path`, or None for a result marked an error.

    The structured content where the tool gives one, which is what the specification added it
    for; otherwise the JSON the first text item carries, which is how a server written before
    structured content answers. Raises for a result that is neither, or holds no records there.
    """
    if result.get("isError") is True:
        return None
    structured = result.get("structuredContent")
    if isinstance(structured, Mapping):
        body: Any = structured
    else:
        content = result.get("content")
        texts = [
            one.get("text")
            for one in (content if isinstance(content, list) else ())
            if isinstance(one, Mapping) and one.get("type") == "text"
        ]
        if not texts or not isinstance(texts[0], str):
            msg = "a tools/call result holds neither structured content nor a text item"
            raise McpProtocolError(msg)
        try:
            body = json.loads(texts[0])
        except ValueError:
            msg = "a tools/call result's text item is not JSON"
            raise McpProtocolError(msg) from None
    found = rows_at(body, path)
    if found is None:
        msg = "a tools/call result holds no records where the reading declares them"
        raise McpProtocolError(msg)
    return found


# ------------------------------------------------------------------ the reading
@dataclass(frozen=True)
class McpEntity:
    """One entity a reading lists, the remote tools that read it, and how their answers map.

    `tool` lists the entity with `arguments`; `one_tool` reads one record, given its id under
    `id_argument`, and is `tool` itself narrowed by the id where it is empty. `index` names the
    mapped fields the minimal index keeps, which the manifest's projection must also declare,
    and `brain.ops.connector_sync.kept_fields` holds a run to that.
    """

    entity: str
    tool: str
    fields: tuple[FieldMapping, ...]
    index: tuple[str, ...]
    arguments: Mapping[str, str] = field(default_factory=dict)
    records_at: str = ""
    one_tool: str = ""
    id_argument: str = ID_TARGET

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.entity):
            msg = f"MCP reading entity {self.entity!r} is not a name"
            raise TransportError(msg)
        if not any(one.target == ID_TARGET for one in self.fields):
            msg = (
                f"the mapping for {self.entity!r} names no {ID_TARGET!r} target; a record with "
                "no id is dropped, so this reading would return nothing and read like an empty "
                "source"
            )
            raise TransportError(msg)
        if self.records_at and not is_source_path(self.records_at):
            msg = f"records path {self.records_at!r} for {self.entity!r} is not a plain dotted path"
            raise TransportError(msg)
        mapped = {one.target for one in self.fields}
        unmapped = sorted(set(self.index) - mapped)
        if unmapped:
            msg = f"{self.entity!r} keeps {unmapped} in its index, which its mapping never reads"
            raise TransportError(msg)
        if not self.id_argument.strip():
            msg = f"{self.entity!r} names no argument a record's id is passed in"
            raise TransportError(msg)


def _checked_id(source_id: str) -> str:
    if (
        not source_id.strip()
        or len(source_id) > MAX_ID_CHARS
        or any(character < " " or character == "\x7f" for character in source_id)
    ):
        msg = "a record id is not the shape a source issues"
        raise ConnectorContractError(msg)
    return source_id


@dataclass(frozen=True)
class McpReading:
    """A source that is an MCP server's tools, read on a schedule and live (M11.1.2).

    Satisfies `brain.connectors.declaration.ToolReading` for the worker and `LiveLookup` for a
    question, so a connector declares one of these as both its `reading` and its `live`. See the
    module docstring for what it refuses.
    """

    connector: str
    transport: McpTransport
    reads: tuple[McpEntity, ...]
    #: The digest of each remote tool's definition as it was reviewed (`tool_digest`).
    pins: Mapping[str, str]
    interval: timedelta
    scheme: KeyScheme = KeyScheme.BEARER
    #: The connection setting holding the server's address, or empty for `transport.endpoint`.
    endpoint_setting: str = ""

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.connector):
            msg = f"MCP reading connector {self.connector!r} is not a name"
            raise TransportError(msg)
        if not self.reads:
            msg = "an MCP reading reads no entity"
            raise TransportError(msg)
        names = [one.entity for one in self.reads]
        if len(names) != len(set(names)):
            msg = "an MCP reading reads one entity twice"
            raise TransportError(msg)
        called = {one.tool for one in self.reads} | {
            one.one_tool for one in self.reads if one.one_tool
        }
        undeclared = sorted(called - set(self.transport.tool_names))
        if undeclared:
            msg = (
                f"an MCP reading calls {undeclared}, which its transport does not declare. "
                "Only tools the declaration names are ever called"
            )
            raise TransportError(msg)
        if set(self.pins) != called:
            msg = (
                "an MCP reading must pin exactly the tools it calls, and pins "
                f"{sorted(self.pins)} for {sorted(called)}. {_REVIEWED}"
            )
            raise TransportError(msg)
        if self.scheme not in SCHEMES_SENT_AS_THEY_ARE:
            msg = (
                f"an MCP reading's key is sent as it is, and {self.scheme.value!r} is a key "
                "file exchanged for a token, which only a REST reading names a scope for"
            )
            raise TransportError(msg)
        if self.interval <= timedelta(0):
            msg = "an MCP reading's interval must be longer than nothing"
            raise TransportError(msg)

    def _entity(self, entity: str) -> McpEntity:
        for one in self.reads:
            if one.entity == entity:
                return one
        msg = f"this reading reads {[one.entity for one in self.reads]}, not {entity!r}"
        raise ConnectorContractError(msg)

    # ------------------------------------------------------------- `ToolReading`
    def entities(self) -> tuple[str, ...]:
        return tuple(one.entity for one in self.reads)

    def refresh_interval(self) -> timedelta:
        return self.interval

    def key_scheme(self) -> KeyScheme:
        return self.scheme

    def endpoint(self, settings: Mapping[str, str]) -> str:
        if not self.endpoint_setting:
            return self.transport.endpoint
        given = settings.get(self.endpoint_setting, "").strip()
        if not given:
            msg = "the connection names no MCP server address"
            raise ConnectorContractError(msg)
        return given

    def pinned(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.pins))

    def tool_call(self, entity: str, source_id: str | None) -> tuple[str, Mapping[str, Any]]:
        one = self._entity(entity)
        if source_id is None:
            return one.tool, MappingProxyType(dict(one.arguments))
        narrowed = {**one.arguments, one.id_argument: _checked_id(source_id)}
        return (one.one_tool or one.tool), MappingProxyType(narrowed)

    def interpret_tool(
        self, entity: str, result: Mapping[str, Any], *, fetched_at: str
    ) -> PageReply:
        one = self._entity(entity)
        found = tool_records(result, one.records_at)
        if found is None:
            # The tool said it failed. A refusal, never a page with no rows.
            return PageReply(call=CallOutcome.REJECTED, rows=None)
        rows = tuple(mapped_row(row, one.fields) for row in found)
        return PageReply(
            call=CallOutcome.OK,
            rows=normalise(entity, rows, source=self.connector, fetched_at=fetched_at),
        )

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        one = self._entity(entity)
        kept: dict[str, ProjectedValue] = {
            name: row[name]
            for name in one.index
            if isinstance(row.get(name), str | int | float | bool)
        }
        return ProjectedRecord(
            source=self.connector,
            entity=entity,
            source_id=str(row[ID_TARGET]),
            last_seen_at=seen_at,
            fields=kept,
        )

    # ------------------------------------------------------------- `LiveLookup`
    def identity_mode(self, entity: str) -> IdentityMode:
        del entity
        return IdentityMode.SERVICE

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        _, arguments = self.tool_call(entity, source_id)
        return {key: str(value) for key, value in arguments.items()}

    def operation(self, entity: str, *, settings: Mapping[str, str], resolver: Any) -> None:
        """None: a record is read by a tool, never by a REST operation."""
        del entity, settings, resolver
