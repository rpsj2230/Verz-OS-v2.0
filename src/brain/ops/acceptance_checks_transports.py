"""The install acceptance checks for two transports: an MCP server, and custom code in a sandbox.

`brain.connectors.mcp` and `brain.connectors.custom_code` let a connector read a source that is an
MCP server's tools or that only custom code can read. No connector this release ships uses either,
so each check makes one up, connects it inside the check's transaction through the store the
Connectors screen's routes call, plans it with the worker's own `plan_for`, reads it with the
worker's own `attempt`, and reads one record live with the question's own `ConnectedSources`. What
is proved is the path, on the install's own database and code: the index row the worker keeps, the
value read live that the index never holds, and the refusals the transports exist for.

**The MCP server is `McpReplay`, a stand-in that speaks the protocol and opens no socket.** It is
reached by the product's own session (`brain.ops.mcp_session`) through `SourcePoster`, the pinned
connection's interface, and it refuses a request with no key, with the wrong session or with no
revision header, as the specification says a server may, so a session that skipped any of them
reads nothing. It also lists a tool the connector does not declare and which says it deletes,
which must never be called.

**The sandbox is `StandInRunner`, and the sandbox itself is not proved here.** The runner contract
(`brain.tools.run_skill.ScriptRunner`) is what the seam uses, and the process, the filesystem and
the cgroup behind it are the deploy work's optional service (needs-rupash 154). The stand-in
answers the plan and the interpretation a connector's code would print, and records every spec it
was handed, so the check can say the key was in none of them. The check also proves the other half
of the seam: with no runner the source is not offered, not planned and not read.

**No check calls a source, reads the vault or holds a real key.** The key is minted by the check
and dropped with it (`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`),
and the made-up connectors read against Xero's measured ceiling, which `BORROWED_CEILING` says
plainly: a source made up for a check has no measured ceiling of its own, and the check is about
the transport, not the figure.

Task ids: M11.1.2, M11.1.5
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from brain.connectors.contract import (
    AccessMode,
    ConnectorScope,
    CredentialBinding,
    FetchRequest,
    TransportKind,
)
from brain.connectors.custom_code import CustomEntity, CustomReading
from brain.connectors.declaration import (
    ConnectorDeclaration,
    ConsoleForm,
    KeyScheme,
    Recorded,
    Setting,
)
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
    ToolDeclaration,
)
from brain.connectors.mcp import (
    SESSION_HEADER,
    VERSION_HEADER,
    McpEntity,
    McpReading,
)
from brain.connectors.transports import CustomTransport, FieldMapping, McpTransport
from brain.connectors.write_verification import NO_READ_BACK_PATH, NOTHING_IS_RECORDED, ReadBack
from brain.core.envelope import IdentityMode
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.tools.run_skill import RunOutcome, RunStatus, SandboxSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key.
CHECK_ORDER: Final = 312

A, _ = RESERVED_DEPARTMENTS

#: The ceiling the made-up connectors are read against, which is Xero's measured one.
BORROWED_CEILING: Final = "xero"

#: The setting both made-up connectors are connected with: the department their records belong to.
DEPARTMENT_SETTING: Final = "department"

# ------------------------------------------------------------------ the MCP connector
#: The connector the MCP check makes up. Not under `brain.connectors`, so never shipped.
MCP_SOURCE: Final = "mcp_acceptance"
MCP_ENTITY: Final = "client"
#: An address under `.example`, which RFC 2606 reserves, so no install's real server is named.
MCP_ENDPOINT: Final = "https://mcp.example/mcp"

#: The server's tools, as the specification shapes a `tools/list` entry. `delete_client` is not
#: declared and says it destroys, so it must never be called.
TOOL_DEFINITIONS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "name": "list_clients",
        "title": "List clients",
        "description": "List the clients this server holds, each with its name and status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Only clients in this status."}
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_client",
        "title": "Read a client",
        "description": "Read one client by its id, with its balance.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "delete_client",
        "description": "Delete one client.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
)

#: The digest of each called tool's definition as it was reviewed, written out rather than
#: computed, so a definition that moves is caught by the pin and not followed by it.
MCP_PINS: Final[Mapping[str, str]] = {
    "list_clients": "743a581247a96fe3f6a94ccf70663def3dae5ae8b26b5ca204dd64cce6ddf361",
    "get_client": "beb4d881863942e25634138a86a4f33624c8239638631cec68d4fc594198cf18",
}

MCP_READING: Final = McpReading(
    connector=MCP_SOURCE,
    transport=McpTransport(
        endpoint=MCP_ENDPOINT,
        tool_names={
            "list_clients": f"{MCP_SOURCE}.list_clients",
            "get_client": f"{MCP_SOURCE}.read_client",
        },
    ),
    reads=(
        McpEntity(
            entity=MCP_ENTITY,
            tool="list_clients",
            one_tool="get_client",
            records_at="clients",
            fields=(
                FieldMapping(target="id", source_path="id"),
                FieldMapping(target="name", source_path="name"),
                FieldMapping(target="status", source_path="status"),
                FieldMapping(target="balance", source_path="balance"),
            ),
            index=("name", "status"),
        ),
    ),
    pins=MCP_PINS,
    interval=timedelta(hours=1),
)


def _index_fields() -> tuple[ProjectedField, ...]:
    return (
        ProjectedField(name="name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
        ProjectedField(name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)),
    )


def mcp_manifest(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """What the made-up MCP connector declares for one connection."""
    department = settings[DEPARTMENT_SETTING]
    return ConnectorManifest(
        name=MCP_SOURCE,
        version="1",
        transport=TransportKind.MCP,
        scope=ConnectorScope(resource_kind="department", selectors=(department,)),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=(
            ToolDeclaration(
                name=f"{MCP_SOURCE}.read_client",
                description="Read one client from the server, live.",
                entity=MCP_ENTITY,
                identity_mode=IdentityMode.SERVICE,
            ),
        ),
        projections=(
            ProjectedEntity(
                entity=MCP_ENTITY,
                fields=_index_fields(),
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=Scope.department(department),
            ),
        ),
        ceiling=BORROWED_CEILING,
    )


def _form(build: Any) -> ConsoleForm:
    return ConsoleForm(
        settings=(
            Setting(
                name=DEPARTMENT_SETTING,
                label="Department",
                hint="The department whose records these are.",
                refused="Give a department's name.",
            ),
        ),
        credential_label="Read-only key",
        credential_hint="A key that can read and change nothing.",
        build=build,
    )


def _declaration(name: str, reading: Any, build: Any) -> ConnectorDeclaration:
    return ConnectorDeclaration(
        name=name,
        label=f"{name} (made up for the acceptance check)",
        read_back=ReadBack(
            reading=None, recorded=(), findings=(NO_READ_BACK_PATH, NOTHING_IS_RECORDED)
        ),
        recorded=Recorded(tested=False),
        console=_form(build),
        reading=reading,
        live=reading,
    )


MCP_DECLARATION: Final = _declaration(MCP_SOURCE, MCP_READING, mcp_manifest)


def _body(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


@dataclass
class McpReplay:
    """`SourcePoster` answering as one MCP server over Streamable HTTP. No socket.

    `tools` is what `tools/list` answers and `results` what each tool's call answers, by tool
    name. Initialisation is answered as JSON and everything after it as an event stream that
    carries one of the server's own notifications before the response, so a client that read
    only one framing, or took the first event for the answer, reads nothing.
    """

    tools: tuple[Mapping[str, Any], ...]
    results: Mapping[str, Mapping[str, Any]]
    session: str = field(default_factory=lambda: secrets.token_hex(8))
    #: Every request, as its method and parameters, and every `Authorization` header sent.
    asked: list[tuple[str, Mapping[str, Any]]] = field(default_factory=list)
    keys: list[str] = field(default_factory=list, repr=False)

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del url, address, max_bytes
        sent = {key.lower(): value for key, value in headers.items()}
        if not sent.get("authorization", "").startswith("Bearer "):
            return SourceAnswer(status=401, headers={}, body=b"")
        self.keys.append(sent["authorization"].removeprefix("Bearer "))
        accepts = sent.get("accept", "")
        if "application/json" not in accepts or "text/event-stream" not in accepts:
            return SourceAnswer(status=406, headers={}, body=b"")
        message = json.loads(body)
        method = str(message.get("method", ""))
        params = message.get("params") or {}
        self.asked.append((method, params))
        if method != "initialize" and (
            sent.get(SESSION_HEADER.lower()) != self.session
            or sent.get(VERSION_HEADER.lower()) != "2025-06-18"
        ):
            return SourceAnswer(status=400, headers={}, body=b"")
        if "id" not in message:
            return SourceAnswer(status=202, headers={}, body=b"")
        if method == "initialize":
            result: Mapping[str, Any] = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "stand-in", "version": "1"},
            }
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
            return SourceAnswer(
                status=200,
                headers={"content-type": "application/json", SESSION_HEADER.lower(): self.session},
                body=_body(reply),
            )
        if method == "tools/list":
            result = {"tools": list(self.tools)}
        elif method == "tools/call" and str(params.get("name")) in self.results:
            result = self.results[str(params["name"])]
        else:
            failed = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601}}
            return SourceAnswer(
                status=200, headers={"content-type": "application/json"}, body=_body(failed)
            )
        notice = {"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info"}}
        reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        stream = "".join(f"event: message\ndata: {json.dumps(one)}\n\n" for one in (notice, reply))
        return SourceAnswer(
            status=200, headers={"content-type": "text/event-stream"}, body=stream.encode("utf-8")
        )

    def called(self) -> tuple[str, ...]:
        """Every tool the session called, in order."""
        return tuple(
            str(params.get("name")) for method, params in self.asked if method == "tools/call"
        )


# ------------------------------------------------------------------ the custom-code connector
#: The connector the custom-code check makes up. Not under `brain.connectors`, so never shipped.
CODE_SOURCE: Final = "code_acceptance"
CODE_ENTITY: Final = "ticket"
#: The one host the code may have the host call, under `.example`, which RFC 2606 reserves.
CODE_HOST: Final = "api.example"

#: What the stand-in runner pretends is the reviewed module, so the reading names a real digest.
STAND_IN_CODE: Final = b"# the reviewed module the stand-in runner stands in for\n"

CODE_READING: Final = CustomReading(
    connector=CODE_SOURCE,
    transport=CustomTransport(
        module="connector.py", sandbox_profile="egress_allowlist", egress_allowlist=(CODE_HOST,)
    ),
    code_digest=hashlib.sha256(STAND_IN_CODE).hexdigest(),
    reads=(
        CustomEntity(
            entity=CODE_ENTITY,
            records_at="records",
            fields=(
                FieldMapping(target="id", source_path="id"),
                FieldMapping(target="subject", source_path="subject"),
                FieldMapping(target="status", source_path="state"),
                FieldMapping(target="body", source_path="body"),
            ),
            index=("subject", "status"),
        ),
    ),
    interval=timedelta(hours=1),
    scheme=KeyScheme.BEARER,
    interprets=True,
)


def code_manifest(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """What the made-up custom-code connector declares for one connection."""
    department = settings[DEPARTMENT_SETTING]
    return ConnectorManifest(
        name=CODE_SOURCE,
        version="1",
        transport=TransportKind.CUSTOM,
        scope=ConnectorScope(resource_kind="department", selectors=(department,)),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=(
            ToolDeclaration(
                name=f"{CODE_SOURCE}.read_ticket",
                description="Read one ticket from the source, live.",
                entity=CODE_ENTITY,
                identity_mode=IdentityMode.SERVICE,
            ),
        ),
        projections=(
            ProjectedEntity(
                entity=CODE_ENTITY,
                fields=(
                    ProjectedField(name="subject", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
                    ProjectedField(name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)),
                ),
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=Scope.department(department),
            ),
        ),
        ceiling=BORROWED_CEILING,
    )


CODE_DECLARATION: Final = _declaration(CODE_SOURCE, CODE_READING, code_manifest)


@dataclass
class StandInRunner:
    """`brain.tools.run_skill.ScriptRunner` printing what the connector's code would. Not a sandbox.

    A planning run prints one GET to the allowlisted host, for the list or for one ticket; an
    interpreting run decodes the answers it was handed and prints their tickets as records. Every
    spec it is handed is kept, so a check can search them for the key.
    """

    specs: list[SandboxSpec] = field(default_factory=list)

    def run(self, spec: SandboxSpec) -> RunOutcome:
        self.specs.append(spec)
        verb, *rest = spec.arguments
        if verb == "plan":
            _, source_id, *_settings = rest
            path = f"/v1/tickets/{source_id}" if source_id else "/v1/tickets"
            printed: Any = {"calls": [{"method": "GET", "url": f"https://{CODE_HOST}{path}"}]}
        else:
            answers = json.loads("".join(rest[1:]))
            records: list[Any] = []
            for answer in answers:
                decoded = json.loads(answer)
                records.extend(decoded.get("tickets", [decoded.get("ticket")]))
            printed = {"records": [one for one in records if one is not None]}
        return RunOutcome(
            run_id=uuid.uuid4().hex,
            status=RunStatus.COMPLETED,
            exit_code=0,
            output=json.dumps(printed),
            elapsed_seconds=0.01,
        )


@dataclass
class TicketSource:
    """`SourceCaller` answering the allowlisted host's ticket list and one-ticket read. No socket.

    A call without a bearer key is answered with 401, so a read that sent none reads nothing.
    """

    tickets: tuple[Mapping[str, Any], ...]
    asked: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list, repr=False)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.asked.append(url)
        sent = {key.lower(): value for key, value in headers.items()}
        if not sent.get("authorization", "").startswith("Bearer "):
            return SourceAnswer(status=401, headers={}, body=b"")
        self.keys.append(sent["authorization"].removeprefix("Bearer "))
        path = urlsplit(url).path
        if path == "/v1/tickets":
            return SourceAnswer(status=200, headers={}, body=_body({"tickets": list(self.tickets)}))
        for one in self.tickets:
            if path == f"/v1/tickets/{one['id']}":
                return SourceAnswer(status=200, headers={}, body=_body({"ticket": one}))
        return SourceAnswer(status=404, headers={}, body=b"{}")


# ------------------------------------------------------------------ shared parts
@dataclass
class KnownKey:
    """`ConnectorKeys` leasing one key the check minted and knows, so it can look for it."""

    key: str = field(default_factory=lambda: secrets.token_hex(16), repr=False)

    def lease(self, ref: SecretRef, *, now: datetime) -> Any:
        from brain.ops.acceptance_checks_connectors import _Lease

        del ref, now
        return _Lease(self.key)


def _connection(h: Harness, connector: str, build: Any) -> Any:
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import key_reference
    from brain.ops.connector_store import Connection

    settings = {DEPARTMENT_SETTING: A}
    return Connection(
        connector=connector,
        settings=settings,
        digest=manifest_digest(build(settings, key_reference(connector))),
        connected_by=h.actor,
        connected_at=h.now,
    )


def _manifests(build: Any) -> Any:
    from brain.ops.connectable import key_reference

    return lambda name, settings: build(settings, key_reference(name))


async def _connect(h: Harness, connection: Any) -> None:
    from brain.ops.acceptance_checks_connectors import _nothing_kept
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.connector_store import StoredConnections

    await StoredConnections(h.sessions).connect(
        connector=connection.connector,
        settings=connection.settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_nothing_kept,
    )


async def _read_by_the_worker(
    h: Harness,
    connection: Any,
    reading: Any,
    build: Any,
    *,
    keys: Any,
    caller: Any,
    poster: Any,
    runner: Any,
) -> Any:
    """The worker's plan and attempt for one made-up connection, or None when the plan refused."""
    from brain.ops.acceptance_checks_connectors import _no_wait, _Resolver
    from brain.ops.connector_sync import plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import LiveConnection

    plan = plan_for(
        connection,
        last=None,
        now=h.now,
        readings={connection.connector: reading},
        runner=runner,
        manifests=_manifests(build),
    )
    if plan.refused:
        return plan
    return await attempt(
        LiveConnection(id=uuid.uuid4(), connection=connection),
        plan,
        previous=None,
        sessions=h.sessions,
        keys=keys,
        caller=caller,
        resolver=_Resolver(),
        clock=lambda: h.now,
        sleep=_no_wait,
        poster=poster,
        runner=runner,
    )


def _live(
    h: Harness,
    connection: Any,
    declaration: ConnectorDeclaration,
    build: Any,
    *,
    keys: Any,
    caller: Any,
    poster: Any,
    runner: Any,
) -> Any:
    from brain.ops.acceptance_checks_connectors import _Resolver
    from brain.ops.live_read_run import ConnectedSources

    return ConnectedSources(
        {connection.connector: connection},
        keys=keys,
        caller=caller,
        resolver=_Resolver(),
        clock=lambda: h.now,
        declarations={connection.connector: declaration},
        poster=poster,
        runner=runner,
        manifests=_manifests(build),
    )


async def _kept(h: Harness, source: str) -> dict[str, dict[str, Any]]:
    from sqlalchemy import select

    from brain.tables.projection import ProjectedRecordRow

    rows = (
        await h.execute(
            select(ProjectedRecordRow.source_id, ProjectedRecordRow.fields).where(
                ProjectedRecordRow.source == source
            )
        )
    ).all()
    return {str(source_id): dict(fields) for source_id, fields in rows}


def _one(source_id: str, entity: str) -> FetchRequest:
    from brain.connectors.live_read import RECORD_ID_FILTER

    return FetchRequest(entity=entity, filters=((RECORD_ID_FILTER, source_id),))


# ------------------------------------------------ 1. an MCP server, read through the product
@check(
    leaves=("M11.1.2",),
    sentence=(
        "An MCP server made up for the check is connected and read through the product's own "
        "path: the worker calls only the declared tool and keeps each client's name and status "
        "and nothing else, a question reads one client's balance live by the declared one-record "
        "tool, and a server that redefines a tool is not called."
    ),
)
async def an_mcp_server_is_read_into_the_index_and_one_record_live(h: Harness) -> None:
    from brain.connectors.throttle import CallOutcome
    from brain.ops.acceptance_checks_connectors import _search
    from brain.ops.connector_sync import TOOL_NOT_AS_REVIEWED, SyncOutcome

    await h.found_departments()
    client_id, name, balance = (
        f"c-{secrets.token_hex(4)}",
        h.word(),
        f"MCPBAL{secrets.token_hex(6)}",
    )
    client = {"id": client_id, "name": name, "status": "active", "balance": balance}
    server = McpReplay(
        tools=TOOL_DEFINITIONS,
        results={
            "list_clients": {"content": [], "structuredContent": {"clients": [client]}},
            "get_client": {
                "content": [{"type": "text", "text": json.dumps({"clients": client})}],
            },
        },
    )
    connection = _connection(h, MCP_SOURCE, mcp_manifest)
    await _connect(h, connection)
    keys = KnownKey()
    done = await _read_by_the_worker(
        h, connection, MCP_READING, mcp_manifest, keys=keys, caller=None, poster=server, runner=None
    )
    if getattr(done, "outcome", None) is not SyncOutcome.SYNCED or done.records != 1:
        raise CheckFailedError("the worker did not read a connected MCP server's declared tool")
    if server.called() != ("list_clients",) or set(server.keys) != {keys.key}:
        raise CheckFailedError("the worker's session called other than the declared tool")
    kept = await _kept(h, MCP_SOURCE)
    if set(kept) != {client_id} or kept[client_id] != {
        "name": name,
        "status": "active",
        DEPARTMENT_SETTING: A,
    }:
        raise CheckFailedError("proj.record kept other than the MCP server's declared index")
    if await _search(h, balance):
        raise CheckFailedError("a value an MCP tool answered was kept in a table")

    sources = _live(
        h,
        connection,
        MCP_DECLARATION,
        mcp_manifest,
        keys=keys,
        caller=None,
        poster=server,
        runner=None,
    )
    reply = sources.read_one(connection, MCP_DECLARATION, _one(client_id, MCP_ENTITY))
    told = {} if reply.rows is None else {one.id: one.model_dump() for one in reply.rows.records}
    if reply.outcome is not CallOutcome.OK or told.get(client_id, {}).get("balance") != balance:
        raise CheckFailedError("a client's balance was not read live from the MCP server")
    if server.called()[-1:] != ("get_client",) or server.asked[-1][1].get("arguments") != {
        "id": client_id
    }:
        raise CheckFailedError("a live read did not call the declared one-record tool for the id")
    if await _search(h, balance):
        raise CheckFailedError("a value read live from the MCP server was kept in a table")

    moved = dict(TOOL_DEFINITIONS[0], description="List every client of every tenant.")
    redefined = McpReplay(tools=(moved, *TOOL_DEFINITIONS[1:]), results=server.results)
    refused = await _read_by_the_worker(
        h,
        connection,
        MCP_READING,
        mcp_manifest,
        keys=keys,
        caller=None,
        poster=redefined,
        runner=None,
    )
    if getattr(refused, "detail", "") != TOOL_NOT_AS_REVIEWED or redefined.called():
        raise CheckFailedError("a server that redefined a declared tool was still called")


# ------------------------------------- 2. custom code, read only through a sandbox runner
@check(
    leaves=("M11.1.5",),
    sentence=(
        "A custom-code connector made up for the check is not offered, planned or read with no "
        "sandbox runner; with a stand-in runner its code plans the call, the host makes it with "
        "the key, the index keeps a ticket's subject and status, its body is read live, and the "
        "key is in nothing the code was handed. The sandbox itself is the deploy work's optional "
        "service and is not proved here."
    ),
)
async def a_custom_code_source_is_read_only_through_a_sandbox_runner(h: Harness) -> None:
    from brain.connectors.throttle import CallOutcome
    from brain.ops.acceptance_checks_connectors import _search
    from brain.ops.connectable import offered, reads
    from brain.ops.connector_sync import NO_SANDBOX, SyncOutcome

    await h.found_departments()
    ticket_id, subject, body = str(10**6 + secrets.randbelow(9 * 10**6)), h.word(), h.word()
    ticket = {"id": ticket_id, "subject": subject, "state": "open", "body": f"CODEBODY{body}"}
    source = TicketSource(tickets=(ticket,))
    connection = _connection(h, CODE_SOURCE, code_manifest)
    await _connect(h, connection)
    keys = KnownKey()

    # Named as the source whose ceiling it borrows, so the runner is the only thing that differs
    # between offered and not: a made-up name has no measured ceiling and is never offered at all.
    named = dataclasses.replace(CODE_DECLARATION, name=BORROWED_CEILING)
    if reads(named) or BORROWED_CEILING in offered({BORROWED_CEILING: named})[0]:
        raise CheckFailedError("a custom-code source was offered on an install with no runner")
    plan = await _read_by_the_worker(
        h,
        connection,
        CODE_READING,
        code_manifest,
        keys=keys,
        caller=source,
        poster=None,
        runner=None,
    )
    if getattr(plan, "refused", "") != NO_SANDBOX or source.asked:
        raise CheckFailedError("the worker planned a custom-code source with no runner to run it")
    unrun = _live(
        h,
        connection,
        CODE_DECLARATION,
        code_manifest,
        keys=keys,
        caller=source,
        poster=None,
        runner=None,
    ).read_one(connection, CODE_DECLARATION, _one(ticket_id, CODE_ENTITY))
    if unrun.outcome is not CallOutcome.REJECTED or source.asked:
        raise CheckFailedError("a custom-code source was read live with no runner to run it")

    runner = StandInRunner()
    if (
        not reads(named, runner=runner)
        or BORROWED_CEILING not in offered({BORROWED_CEILING: named}, runner=runner)[0]
    ):
        raise CheckFailedError("a custom-code source was not offered with a runner given")
    done = await _read_by_the_worker(
        h,
        connection,
        CODE_READING,
        code_manifest,
        keys=keys,
        caller=source,
        poster=None,
        runner=runner,
    )
    if getattr(done, "outcome", None) is not SyncOutcome.SYNCED or done.records != 1:
        raise CheckFailedError("the worker did not read a custom-code source through its runner")
    kept = await _kept(h, CODE_SOURCE)
    if kept.get(ticket_id) != {"subject": subject, "status": "open", DEPARTMENT_SETTING: A}:
        raise CheckFailedError("proj.record kept other than the custom code's declared index")
    if await _search(h, ticket["body"]):
        raise CheckFailedError("a ticket's body read through custom code was kept in a table")

    reply = _live(
        h,
        connection,
        CODE_DECLARATION,
        code_manifest,
        keys=keys,
        caller=source,
        poster=None,
        runner=runner,
    ).read_one(connection, CODE_DECLARATION, _one(ticket_id, CODE_ENTITY))
    told = {} if reply.rows is None else {one.id: one.model_dump() for one in reply.rows.records}
    if reply.outcome is not CallOutcome.OK or told.get(ticket_id, {}).get("body") != ticket["body"]:
        raise CheckFailedError("a ticket's body was not read live through the custom code")
    if set(source.keys) != {keys.key}:
        raise CheckFailedError("the host's calls did not carry the leased key")
    handed = [" ".join((*one.arguments, *one.environment.values())) for one in runner.specs]
    if not handed or any(keys.key in one for one in handed):
        raise CheckFailedError("the key was in something the custom code was handed")
