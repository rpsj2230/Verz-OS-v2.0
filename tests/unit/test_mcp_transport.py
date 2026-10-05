"""Reading a source that is an MCP server: the protocol's messages, the pin, the recorded exchange.

The pure half drives `brain.connectors.mcp` with no server: how an answer is read from either
framing, what a tool is pinned by, and what a tool's answer means. The other half replays the
recorded exchange (`tests/fixtures/cassettes/mcp_exchange.json`) through the product's own session,
worker attempt and live read, against the connector the acceptance check makes up
(`brain.ops.acceptance_checks_transports`), which is built for the test and never shipped.

Task ids: M11.1.2
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.declaration import KeyScheme
from brain.connectors.live_read import RECORD_ID_FILTER
from brain.connectors.manifest import manifest_digest
from brain.connectors.mcp import (
    PROTOCOL_VERSION,
    McpEntity,
    McpProtocolError,
    McpReading,
    McpToolNotAsReviewedError,
    assert_as_reviewed,
    negotiated,
    reply_to,
    request_body,
    tool_digest,
)
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import FieldMapping, McpTransport, TransportError
from brain.ops.acceptance_checks_transports import (
    DEPARTMENT_SETTING,
    MCP_DECLARATION,
    MCP_ENTITY,
    MCP_PINS,
    MCP_READING,
    MCP_SOURCE,
    TOOL_DEFINITIONS,
    KnownKey,
    mcp_manifest,
)
from brain.ops.connectable import key_reference
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import (
    NO_WAY_TO_POST,
    SOURCE_ALLOWANCE_REFUSED,
    TOOL_NOT_AS_REVIEWED,
    TOOL_SAID_IT_FAILED,
    SyncOutcome,
    plan_for,
)
from brain.ops.connector_sync_run import attempt
from brain.ops.connector_sync_store import LiveConnection
from brain.ops.live_read_run import ConnectedSources
from brain.ops.mcp_session import CallNotAdmittedError, open_session, read_entity
from brain.tools.fetch import UnsafeAddressError
from tests.fixtures.mcp_cassette import CassettePlayer, conversation, recorded

#: Far from any wall clock, because nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)
SETTINGS = {DEPARTMENT_SETTING: "acceptance_a"}
PUBLIC = "2000::1"


class _Resolver:
    def __init__(self, address: str = PUBLIC) -> None:
        self.address = address

    def resolve(self, host: str) -> list[str]:
        del host
        return [self.address]


def _event_stream(*messages: Any) -> bytes:
    return "".join(f"event: message\ndata: {json.dumps(one)}\n\n" for one in messages).encode()


# ------------------------------------------------------------------ the protocol's messages
def test_a_request_is_one_json_rpc_message_carrying_its_id() -> None:
    """Delete this and a request could go out with no id, which a server answers as a
    notification: with nothing at all."""
    assert json.loads(request_body(7, "tools/list", {})) == {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/list",
        "params": {},
    }


def test_an_answer_is_read_from_an_event_stream_past_the_server_s_own_notifications() -> None:
    """A stream may carry the server's notifications first. Delete this and a client could take
    the first event for the answer and read a log line as a result."""
    body = _event_stream(
        {"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info"}},
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
    )
    assert reply_to(2, content_type="text/event-stream; charset=utf-8", body=body) == {"tools": []}


def test_an_answer_is_read_from_a_json_body_too() -> None:
    """The specification lets a server answer with either framing. Delete this and a server
    that answers as plain JSON could be read as answering nothing."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode()
    assert reply_to(1, content_type="application/json", body=body) == {"ok": True}


@pytest.mark.parametrize(
    "body",
    [
        _event_stream({"jsonrpc": "2.0", "id": 9, "result": {}}),
        _event_stream({"jsonrpc": "2.0", "method": "notifications/message"}),
        b"event: message\ndata: {not json\n\n",
    ],
)
def test_an_answer_holding_no_response_to_the_request_is_refused(body: bytes) -> None:
    """A response to another request, a stream of notifications only, and an event that is not
    JSON. Delete this and a client could read another request's result as this one's."""
    with pytest.raises(McpProtocolError):
        reply_to(2, content_type="text/event-stream", body=body)


def test_a_json_rpc_error_is_refused_with_its_code_and_never_its_message() -> None:
    """The message is the server's text and may quote what was asked. Delete this and that text
    could reach a log line or a person."""
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 3, "error": {"code": -32602, "message": "SECRET-ECHO"}}
    ).encode()
    with pytest.raises(McpProtocolError) as refused:
        reply_to(3, content_type="application/json", body=body)
    assert "-32602" in str(refused.value)
    assert "SECRET-ECHO" not in str(refused.value)


def test_a_revision_this_client_does_not_speak_is_refused() -> None:
    """Delete this and a client could read a server whose transport or results moved on, as
    though they had not."""
    assert negotiated({"protocolVersion": PROTOCOL_VERSION}) == PROTOCOL_VERSION
    with pytest.raises(McpProtocolError):
        negotiated({"protocolVersion": "2024-11-05"})


# ------------------------------------------------------------------ the pin
def test_the_recorded_definitions_hash_to_the_pins_the_connector_was_reviewed_at() -> None:
    """The pins are written out in the connector, not computed. Delete this and the recording
    and the pins could drift apart, and every replay below would be testing a refusal."""
    listed = recorded()["conversations"]["scheduled"][2]["response"]["body"]
    tools = next(
        json.loads(line[5:])["result"]["tools"]
        for line in listed.splitlines()
        if line.startswith("data:") and '"result"' in line
    )
    by_name = {one["name"]: one for one in tools}
    assert {name: tool_digest(by_name[name]) for name in MCP_PINS} == dict(MCP_PINS)


def test_a_tool_s_digest_ignores_key_order_and_moves_with_its_description() -> None:
    """Canonical JSON, over what a reviewer read. Delete this and either a reordered answer is
    refused as a redefinition, or a rewritten description passes as the one reviewed."""
    original = dict(TOOL_DEFINITIONS[0])
    reordered = dict(reversed(list(original.items())))
    assert tool_digest(reordered) == tool_digest(original)
    assert tool_digest({**original, "description": "List every tenant."}) != tool_digest(original)
    assert tool_digest({**original, "annotations": {}}) == tool_digest(original)


@pytest.mark.parametrize(
    "listed",
    [
        TOOL_DEFINITIONS[1:],
        ({**TOOL_DEFINITIONS[0], "description": "List every client of every tenant."},),
        ({**TOOL_DEFINITIONS[0], "annotations": {"readOnlyHint": False}},),
        ({**TOOL_DEFINITIONS[0], "annotations": {"destructiveHint": True}},),
    ],
    ids=["missing", "redefined", "not_read_only", "destructive"],
)
def test_a_tool_missing_redefined_or_saying_it_writes_is_refused(listed: Any) -> None:
    """`A_TOOL_IS_CALLED_ONLY_AS_IT_WAS_REVIEWED`. Delete this and a server could swap what a
    declared tool does between two runs and still be called."""
    with pytest.raises(McpToolNotAsReviewedError):
        assert_as_reviewed({"list_clients": MCP_PINS["list_clients"]}, tuple(listed))


def test_a_tool_listed_as_it_was_reviewed_is_allowed_beside_an_undeclared_one() -> None:
    """The positive half: an undeclared tool that says it deletes is listed beside the declared
    ones and is no reason to refuse them. Delete this and a guard refusing everything passes."""
    assert_as_reviewed(MCP_PINS, TOOL_DEFINITIONS)


# ------------------------------------------------------------------ the reading
def _entity(**changes: Any) -> McpEntity:
    return replace(MCP_READING.reads[0], **changes)


def test_a_reading_calling_a_tool_the_transport_does_not_declare_is_refused() -> None:
    """`AN_UNDECLARED_REMOTE_TOOL_IS_NOT_EXPOSED`, applied to what is called. Delete this and a
    reading could call `delete_client`."""
    with pytest.raises(TransportError):
        replace(MCP_READING, reads=(_entity(one_tool="delete_client"),))


def test_a_reading_must_pin_exactly_the_tools_it_calls() -> None:
    """Delete this and a tool could be called with no digest to hold it to."""
    with pytest.raises(TransportError):
        replace(MCP_READING, pins={"list_clients": MCP_PINS["list_clients"]})


def test_a_reading_whose_key_is_a_key_file_is_refused() -> None:
    """Only a REST reading names the scope a key file's token carries. Delete this and an MCP
    reading naming the Google scheme would fail every read with a header it cannot build."""
    with pytest.raises(TransportError):
        replace(MCP_READING, scheme=KeyScheme.GOOGLE_SERVICE_ACCOUNT)


def test_an_entity_keeping_a_field_its_mapping_never_reads_is_refused() -> None:
    """Delete this and an index field would be declared that no record ever carries."""
    with pytest.raises(TransportError):
        _entity(index=("name", "owner_note"))


def test_a_record_is_read_live_by_the_declared_one_record_tool_with_its_id() -> None:
    """Delete this and a question could call the list tool and read whichever record came
    first."""
    assert MCP_READING.tool_call(MCP_ENTITY, None) == ("list_clients", {})
    assert MCP_READING.tool_call(MCP_ENTITY, "c-1001") == ("get_client", {"id": "c-1001"})
    with pytest.raises(ConnectorContractError):
        MCP_READING.tool_call(MCP_ENTITY, "c-1001\nmore")


def test_a_tool_marked_as_an_error_is_a_refusal_and_never_an_empty_page() -> None:
    """An empty page reads as a source with nothing in it. Delete this and a server in
    maintenance would read as a CRM with no clients."""
    reply = MCP_READING.interpret_tool(
        MCP_ENTITY, {"content": [{"type": "text", "text": "down"}], "isError": True}, fetched_at=""
    )
    assert (reply.call, reply.rows) == (CallOutcome.REJECTED, None)


def test_only_mapped_fields_arrive_and_a_row_with_no_id_is_dropped() -> None:
    """`WHAT_THE_MAPPING_DOES_NOT_NAME_DOES_NOT_ARRIVE`, for an MCP tool. Delete this and a field
    nobody classified could ride along on every record."""
    rows = [
        {"id": "c-1", "name": "One", "status": "active", "balance": "1", "owner_note": "x"},
        {"name": "No id"},
    ]
    reply = MCP_READING.interpret_tool(
        MCP_ENTITY, {"structuredContent": {"clients": rows}}, fetched_at="2019-03-01T09:00:00Z"
    )
    assert reply.rows is not None
    assert [one.model_dump() for one in reply.rows.records] == [
        {"entity": MCP_ENTITY, "id": "c-1", "name": "One", "status": "active", "balance": "1"}
    ]


def test_structured_content_is_read_before_the_text_item() -> None:
    """The specification added structured content for this. Delete this and a tool whose text
    item is a summary would be read instead of its records."""
    result = {
        "content": [{"type": "text", "text": json.dumps({"clients": []})}],
        "structuredContent": {"clients": [{"id": "c-9", "name": "Nine", "status": "active"}]},
    }
    reply = MCP_READING.interpret_tool(MCP_ENTITY, result, fetched_at="")
    assert reply.rows is not None and [one.id for one in reply.rows.records] == ["c-9"]


# ------------------------------------------------------------------ the recorded exchange
def _session(player: CassettePlayer, **kwargs: Any) -> Any:
    from brain.ops.connector_sync_run import bare_headers

    return open_session(
        MCP_READING,
        settings=SETTINGS,
        headers=bare_headers(KeyScheme.BEARER, player.key),
        poster=player,
        resolver=kwargs.get("resolver", _Resolver()),
        admit=kwargs.get("admit", lambda: True),
    )


def test_the_scheduled_conversation_is_sent_exactly_as_recorded() -> None:
    """**The whole scheduled read against the recording**: initialise, the notification, the
    tool list and one call of the declared tool, every body and header as recorded and the leased
    key in the one header. Delete this and the client can drift from the protocol with every
    unit test above still green."""
    player = CassettePlayer(conversation("scheduled"), key="k-" + uuid.uuid4().hex)
    session = _session(player)
    reply = read_entity(session, MCP_READING, MCP_ENTITY, None, fetched_at="2019-03-01T09:00:00Z")
    assert player.done(), player.mismatches
    assert reply.call is CallOutcome.OK and reply.rows is not None
    assert [(one.id, one.model_dump().get("name")) for one in reply.rows.records] == [
        ("c-1001", "Harbour Lane Bakery"),
        ("c-1002", "Westfield Joinery"),
    ]


def test_a_request_the_ceiling_does_not_admit_is_not_sent() -> None:
    """Delete this and a session could spend the source's allowance with the ceiling saying
    no."""
    player = CassettePlayer(conversation("scheduled"), key="k")
    admitted = iter((True, True))
    with pytest.raises(CallNotAdmittedError):
        _session(player, admit=lambda: next(admitted, False))
    assert player.at == 2


def test_an_address_inside_the_network_is_refused_before_anything_is_sent() -> None:
    """Delete this and an MCP server's name answering inside the network would be called."""
    player = CassettePlayer(conversation("scheduled"), key="k")
    with pytest.raises(UnsafeAddressError):
        _session(player, resolver=_Resolver("10.0.0.5"))
    assert player.at == 0


class _NoSessions:
    """Stands in for the session factory on reads that write nothing. Any use is a failure."""

    def __call__(self) -> Any:
        raise AssertionError("a read that kept nothing opened a database session")


def _attempt(poster: Any) -> Any:
    connection = Connection(
        connector=MCP_SOURCE,
        settings=SETTINGS,
        digest=manifest_digest(mcp_manifest(SETTINGS, key_reference(MCP_SOURCE))),
        connected_by="u_admin",
        connected_at=NOW,
    )
    plan = plan_for(
        connection,
        last=None,
        now=NOW,
        readings={MCP_SOURCE: MCP_READING},
        manifests=lambda name, settings: mcp_manifest(settings, key_reference(name)),
    )
    assert not plan.refused, plan.refused

    async def no_wait(seconds: float) -> None:
        del seconds

    return asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            sessions=cast(Any, _NoSessions()),
            keys=KnownKey(key="k-recorded"),
            caller=cast(Any, None),
            resolver=_Resolver(),
            clock=lambda: NOW,
            sleep=no_wait,
            poster=poster,
        )
    )


@pytest.mark.parametrize(
    ("name", "outcome", "detail"),
    [
        ("tool_error", SyncOutcome.FAILED, TOOL_SAID_IT_FAILED),
        ("allowance_spent", SyncOutcome.QUOTA, SOURCE_ALLOWANCE_REFUSED),
    ],
)
def test_a_recorded_failure_leaves_its_own_sentence_and_keeps_nothing(
    name: str, outcome: SyncOutcome, detail: str
) -> None:
    """A tool marked as an error and a 429, through the worker's own attempt. Delete this and a
    server in maintenance could read as empty, or a spent allowance as a failure that backs off
    as if the source were ill."""
    player = CassettePlayer(conversation(name), key="k-recorded")
    done = _attempt(player)
    assert player.done(), player.mismatches
    assert (done.outcome, done.detail, done.records) == (outcome, detail, 0)
    if name == "allowance_spent":
        assert done.next_attempt_at >= NOW.replace(second=30)


def test_a_redefined_tool_is_not_called_by_the_worker() -> None:
    """Delete this and the worker would read a server whose tool changed meaning since review."""
    exchanges = conversation("scheduled")
    listed = exchanges[2]["response"]
    listed["body"] = listed["body"].replace(
        "List the clients this server holds", "List every client of every tenant"
    )
    player = CassettePlayer(exchanges, key="k-recorded")
    done = _attempt(player)
    assert (done.outcome, done.detail) == (SyncOutcome.FAILED, TOOL_NOT_AS_REVIEWED)
    assert player.at == 3


def test_a_worker_given_no_way_to_post_does_not_read_an_mcp_source() -> None:
    """Delete this and the attempt would fail somewhere inside the session with a sentence that
    says nothing about why."""
    done = _attempt(None)
    assert (done.outcome, done.detail) == (SyncOutcome.FAILED, NO_WAY_TO_POST)


def test_a_question_reads_one_record_live_as_recorded() -> None:
    """**The live read against the recording**: a new session, the declared one-record tool
    called with the record's id, its text item read, and the value the index never holds
    returned. Delete this and a question could read an MCP source some other way than the
    worker does, or not at all."""
    player = CassettePlayer(conversation("live"), key="k-recorded")
    connection = Connection(
        connector=MCP_SOURCE,
        settings=SETTINGS,
        digest=manifest_digest(mcp_manifest(SETTINGS, key_reference(MCP_SOURCE))),
        connected_by="u_admin",
        connected_at=NOW,
    )
    sources = ConnectedSources(
        {MCP_SOURCE: connection},
        keys=KnownKey(key="k-recorded"),
        caller=cast(Any, None),
        resolver=_Resolver(),
        clock=lambda: NOW,
        declarations={MCP_SOURCE: MCP_DECLARATION},
        poster=player,
        manifests=lambda name, settings: mcp_manifest(settings, key_reference(name)),
    )
    reply = sources.read_one(
        connection,
        MCP_DECLARATION,
        FetchRequest(entity=MCP_ENTITY, filters=((RECORD_ID_FILTER, "c-1001"),)),
    )
    assert player.done(), player.mismatches
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    assert [one.model_dump().get("balance") for one in reply.rows.records] == ["1840.00"]


def test_an_entity_with_no_id_target_is_refused() -> None:
    """Delete this and a mapping with no id would return nothing and read like an empty
    source."""
    with pytest.raises(TransportError):
        McpEntity(
            entity="client",
            tool="list_clients",
            fields=(FieldMapping(target="name", source_path="name"),),
            index=("name",),
        )


def test_an_mcp_reading_is_built_only_from_declared_tools_and_a_transport() -> None:
    """The positive half of the refusals above: the connector the checks make up is accepted,
    reads one entity and pins two tools. Delete this and a reading refusing everything passes."""
    reading = McpReading(
        connector=MCP_SOURCE,
        transport=McpTransport(endpoint="https://mcp.example/mcp", tool_names={"a": "x.read_a"}),
        reads=(
            McpEntity(
                entity="thing",
                tool="a",
                fields=(FieldMapping(target="id", source_path="id"),),
                index=(),
            ),
        ),
        pins={"a": "0" * 64},
        interval=MCP_READING.interval,
    )
    assert reading.entities() == ("thing",)
    assert MCP_READING.entities() == (MCP_ENTITY,) and set(MCP_READING.pinned()) == set(MCP_PINS)
