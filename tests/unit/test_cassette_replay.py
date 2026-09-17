"""Every recording, replayed through the connector it belongs to, and every declaration covered.

`tests/fixtures/cassettes.py` says what each recording is an example of and what the
connector's own code must conclude from it. This file is where that is checked, and it is the
check that made "tested against recorded responses" a property rather than a word: until it
existed, the contract invariant asked only whether a connector's test file mentioned the
cassettes, and `test_google_drive.py` satisfied it by saying none existed.

**A replay calls the connector's own functions and nothing of this file's.** Each one hands a
recording to the reader, interpreter, walk or projection the connector ships, and reads the
outcome off what that code did: the reply it built, the exception it raised, the page it asked
for next, the record it kept. A replay that classified the recording itself would be a second
implementation of the connector, and it would agree with the recording by construction.

**The sweep is written from the manifests, not from the recordings.** Every tool a connector
declares must be answered by a recording of its own, every projection must be fed by one whose
rows the connector actually keeps, and every connector must have a page that says there is
more, a rate limit and an error. A connector that declares a tool nobody recorded fails
`test_every_declared_tool_is_answered_by_a_recording`, and the exemptions below are named with
the reason each cannot be recorded.

What this does not prove is that a vendor answers this way today. Every recording is a
documented shape, and `test_no_recording_claims_a_live_read_it_does_not_date` holds that.

Task ids: M0.6.5, M38.4.1.1
"""

from __future__ import annotations

import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

import brain.connectors
from brain.connectors import freshdesk, google_drive, hubspot, laravel, lark_base, lark_wiki, xero
from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.projection import ProjectedRecord
from brain.connectors.throttle import CallOutcome
from brain.ops.connector_recordings import RECORDINGS
from brain.ops.connector_sync import HubSpotReading, XeroReading
from tests.fixtures.cassettes import (
    CASSETTES,
    DRIVE_FOLDER,
    LARAVEL_RECORDED_CAP,
    WIKI_SPACE,
    Cassette,
    Expect,
    Kind,
    Origin,
    Protocol,
    Source,
)
from tests.invariants.test_cassettes import NOT_A_CONNECTOR

FETCHED_AT = "2026-09-06T09:00:00+00:00"
#: Pinned well away from any wall clock: nothing here is about the present.
SEEN_AT = datetime(2019, 6, 1, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Replayed:
    """What the connector's own code concluded, and how many rows it kept as projected records."""

    outcome: Expect
    kept: tuple[ProjectedRecord, ...] = ()

    @property
    def projected(self) -> int:
        return len(self.kept)


def _unreachable_or_quota(call_outcome: CallOutcome) -> Expect:
    return Expect.RATE_LIMITED if call_outcome is CallOutcome.QUOTA else Expect.UNREACHABLE


# ------------------------------------------------------------------------------ Xero
def _replay_xero(recorded: Cassette) -> Replayed:
    from tests.unit.test_xero import Resolver

    entity = recorded.projects or (
        xero.ENTITY_CONTACT if "Contacts" in recorded.request else xero.ENTITY_INVOICE
    )
    operation = xero.operation_for(entity, resolver=Resolver())
    reply = xero.interpret(
        operation, status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
    )
    if reply.outcome is xero.XeroOutcome.REFUSED:
        return Replayed(Expect.REFUSED)
    if reply.outcome is xero.XeroOutcome.UNREACHABLE:
        return Replayed(_unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [record.model_dump() for record in reply.rows.records]
    kept = [xero.projected_record(entity, row, last_seen_at=SEEN_AT) for row in rows]
    projected = tuple(one for one in kept if one is not None) if recorded.projects else ()
    if not rows:
        return Replayed(Expect.ABSENT)
    following = XeroReading().next_page(entity, {"page": "1"}, recorded.body, len(rows))
    return Replayed(Expect.MORE_TO_READ if following else Expect.ANSWERED, projected)


# --------------------------------------------------------------------------- HubSpot
def _hubspot_entity(recorded: Cassette) -> str:
    if "/associations/" in recorded.request:
        return hubspot.ENTITY_ASSOCIATION
    for fragment, entity in (
        ("/contacts", hubspot.ENTITY_CONTACT),
        ("/deals", hubspot.ENTITY_DEAL),
    ):
        if fragment in recorded.request:
            return entity
    return hubspot.ENTITY_CLIENT


def _replay_hubspot(recorded: Cassette) -> Replayed:
    from tests.unit.test_hubspot import Resolver

    entity = _hubspot_entity(recorded)
    operation = hubspot.operation_for(entity, resolver=Resolver())
    reply = hubspot.interpret(
        operation, status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
    )
    if reply.outcome is hubspot.HubSpotOutcome.REFUSED:
        return Replayed(Expect.REFUSED)
    if reply.outcome is hubspot.HubSpotOutcome.UNREACHABLE:
        return Replayed(_unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [record.model_dump() for record in reply.rows.records]
    if not rows:
        return Replayed(Expect.ABSENT)
    if entity == hubspot.ENTITY_ASSOCIATION:
        edges = hubspot.association_edges(
            from_entity=hubspot.ENTITY_CLIENT, from_id="88", to_entity="contact", rows=tuple(rows)
        )
        return Replayed(Expect.ANSWERED if edges else Expect.ABSENT)
    kept = [hubspot.projected_record(entity, row, last_seen_at=SEEN_AT) for row in rows]
    projected = tuple(one for one in kept if one is not None)
    following = HubSpotReading().next_page(entity, {}, recorded.body, len(rows))
    return Replayed(Expect.MORE_TO_READ if following else Expect.ANSWERED, projected)


# ------------------------------------------------------------------------- Freshdesk
def _freshdesk_endpoint(recorded: Cassette) -> freshdesk.Endpoint:
    if "/search/" in recorded.request:
        return freshdesk.Endpoint.SEARCH_TICKETS
    if "/contacts/" in recorded.request:
        return freshdesk.Endpoint.GET_CONTACT
    if "/tickets/" in recorded.request:
        return freshdesk.Endpoint.GET_TICKET
    return freshdesk.Endpoint.LIST_TICKETS


def _replay_freshdesk(recorded: Cassette) -> Replayed:
    from tests.unit.test_freshdesk import DOMAIN

    endpoint = _freshdesk_endpoint(recorded)
    reply = freshdesk.Reply(status=recorded.status, headers=recorded.headers, body=recorded.body)
    try:
        freshdesk.assert_answered(reply)
    except freshdesk.FreshdeskRefusedError:
        return Replayed(Expect.REFUSED)
    except freshdesk.FreshdeskUnreachableError as failed:
        return Replayed(_unreachable_or_quota(failed.call_outcome))
    rows = freshdesk.operation_for(endpoint, domain=DOMAIN).project(reply.body)
    if not rows:
        return Replayed(Expect.ABSENT)
    projected = tuple(
        ProjectedRecord(
            source=freshdesk.FRESHDESK,
            entity=freshdesk.TICKET,
            source_id=str(row["id"]),
            last_seen_at=SEEN_AT,
            fields=freshdesk.projected_fields(row),
        )
        for row in (rows if recorded.projects else ())
    )
    following = freshdesk.next_page(
        freshdesk.first_page(endpoint), rows_on_page=len(rows), rows_so_far=len(rows)
    )
    return Replayed(Expect.MORE_TO_READ if following else Expect.ANSWERED, projected)


# ------------------------------------------------------------------------- Lark Base
@dataclass
class _OneReply:
    reply: Any

    def read(self, cursor: object) -> Any:
        del cursor
        return self.reply


def _replay_lark_base(recorded: Cassette) -> Replayed:
    from tests.unit.test_lark_base import a_table, list_operation, single_operation

    table = a_table()
    reader = _OneReply(
        lark_base.LarkReply(status=recorded.status, headers=recorded.headers, body=recorded.body)
    )
    single = recorded.kind is Kind.READ
    try:
        if single:
            cursor = lark_base.PageCursor(
                endpoint=lark_base.Endpoint.GET_RECORD, record_id="recSNM0447"
            )
            row, _ = lark_base.read_record(
                single_operation(), reader, cursor, budget=lark_base.fair_share_budget()
            )
            rows: tuple[Mapping[str, Any], ...] = (row,)
            more = False
        else:
            rows, envelope = lark_base.read_page(list_operation(), reader, lark_base.first_cursor())
            more = envelope.has_more
    except lark_base.LarkBaseRefusedError:
        return Replayed(Expect.REFUSED)
    except lark_base.LarkBaseUnreachableError as failed:
        return Replayed(_unreachable_or_quota(failed.call_outcome))
    if not rows:
        return Replayed(Expect.ABSENT)
    projected = tuple(table.projected_record(row, last_seen_at=SEEN_AT) for row in rows)
    return Replayed(Expect.MORE_TO_READ if more else Expect.ANSWERED, projected)


# ------------------------------------------------------------------------- Lark Wiki
@dataclass
class _WikiReader:
    reply: lark_wiki.LarkReply

    def list_nodes(self, request: lark_wiki.NodeListRequest) -> lark_wiki.LarkReply:
        del request
        return self.reply

    def read_node(self, request: lark_wiki.NodeReadRequest) -> lark_wiki.LarkReply:
        del request
        return self.reply


def _replay_lark_wiki(recorded: Cassette) -> Replayed:
    reader = _WikiReader(lark_wiki.LarkReply(status=recorded.status, body=recorded.body))
    try:
        if "/nodes" in recorded.request:
            listing = lark_wiki.walk_nodes(reader, space_id=WIKI_SPACE, max_pages=1)
            if not listing.nodes:
                return Replayed(Expect.ABSENT)
            return Replayed(Expect.ANSWERED if listing.complete else Expect.MORE_TO_READ)
        fetch = lark_wiki.page_fetch(lark_wiki.operation_for(), reader, fetched_at=FETCHED_AT)
        result = fetch(
            FetchRequest(
                entity=lark_wiki.WIKI_PAGE, filters=(("token", "wikcnKQ1k3pcuo5uSK4t8Vabcef"),)
            )
        )
    except lark_wiki.LarkWikiRefusedError:
        return Replayed(Expect.REFUSED)
    except lark_wiki.LarkWikiUnreachableError as failed:
        return Replayed(_unreachable_or_quota(failed.call_outcome))
    return Replayed(Expect.ANSWERED if result.records else Expect.ABSENT)


# ---------------------------------------------------------------------- Google Drive
def _drive_connection() -> google_drive.DriveConnection:
    from tests.unit.test_google_drive import a_connection

    return a_connection(folder_id=DRIVE_FOLDER)


@dataclass
class _DriveReader:
    reply: google_drive.Reply

    def read(self, request: google_drive.ListingRequest) -> google_drive.Reply:
        del request
        return self.reply


def _replay_google_drive(recorded: Cassette) -> Replayed:
    connection = _drive_connection()
    reply = google_drive.Reply(status=recorded.status, headers=recorded.headers, body=recorded.body)
    listing = "/files?" in recorded.request or recorded.request.endswith("/files")
    try:
        if listing:
            rows, cursor = google_drive.read_page(
                google_drive.operation_for(google_drive.Endpoint.LIST_FILES),
                _DriveReader(reply),
                google_drive.first_page(connection),
            )
            for row in rows:
                google_drive.assert_row_is_in_the_folder(connection, row)
        else:
            google_drive.assert_answered(reply)
            rows = google_drive.operation_for(google_drive.Endpoint.GET_FILE).project(reply.body)
            cursor = ""
    except google_drive.DriveNotFoundError:
        return Replayed(Expect.NOT_FOUND)
    except google_drive.DriveRefusedError:
        return Replayed(Expect.REFUSED)
    except google_drive.DriveUnreachableError as failed:
        return Replayed(_unreachable_or_quota(failed.call_outcome))
    if not rows:
        return Replayed(Expect.ABSENT)
    # No function in the connector reads a permission array out of a response, so no sharing
    # state has a producer to replay; see `PROJECTION_NOT_REPLAYABLE`. What is replayed is the
    # refusal: a row whose sharing nobody determined is not kept.
    for row in rows:
        with pytest.raises(google_drive.DriveError):
            google_drive.projected_fields(
                row,
                connection=connection,
                sharing=google_drive.classify_sharing(None, domain="verz.com"),
            )
    return Replayed(Expect.MORE_TO_READ if cursor else Expect.ANSWERED)


# --------------------------------------------------------------------------- Laravel
def _replay_laravel(recorded: Cassette) -> Replayed:
    from tests.unit.test_laravel import connection

    entity = laravel.ENTITY_USER if "v_users" in recorded.request else laravel.ENTITY_CLIENT
    read = laravel.read_plan(connection(), entity)
    assert read.plan.limit == LARAVEL_RECORDED_CAP, "the recording's cap is not the replay's"
    body = recorded.body
    if recorded.protocol is Protocol.HTTP:
        view = laravel.ViewReply(app_status=recorded.status)
    elif "errno" in body:
        view = laravel.ViewReply(fault=laravel.fault_for_mysql_error(body["errno"]))
    else:
        view = laravel.ViewReply(rows=tuple(body["rows"]))
    reply = laravel.interpret(read, view, fetched_at=FETCHED_AT)
    if reply.outcome is laravel.LaravelOutcome.REFUSED:
        return Replayed(Expect.REFUSED)
    if reply.outcome is laravel.LaravelOutcome.UNREACHABLE:
        return Replayed(_unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [record.model_dump() for record in reply.rows.records]
    if not rows:
        return Replayed(Expect.ABSENT)
    kept = [laravel.projected_record(entity, row, last_seen_at=SEEN_AT) for row in rows]
    projected = tuple(one for one in kept if one is not None)
    more = reply.call is CallOutcome.TRUNCATED
    return Replayed(Expect.MORE_TO_READ if more else Expect.ANSWERED, projected)


#: One replay per connector module. `tests/invariants/test_cassettes.py` refuses a connector
#: that has none, so a new connector joins by existing and fails until it is replayed.
REPLAYS: Mapping[str, Callable[[Cassette], Replayed]] = {
    "xero": _replay_xero,
    "hubspot": _replay_hubspot,
    "freshdesk": _replay_freshdesk,
    "lark_base": _replay_lark_base,
    "lark_wiki": _replay_lark_wiki,
    "google_drive": _replay_google_drive,
    "laravel": _replay_laravel,
}


def _manifests() -> dict[str, ConnectorManifest]:
    """Every connector's manifest, built by its own test file's builder."""
    from tests.unit import (
        test_freshdesk,
        test_google_drive,
        test_hubspot,
        test_laravel,
        test_lark_base,
        test_lark_wiki,
        test_xero,
    )

    return {
        "xero": test_xero.manifest(),
        "hubspot": test_hubspot.manifest(),
        "freshdesk": test_freshdesk.a_manifest(),
        "lark_base": test_lark_base.a_manifest(),
        "lark_wiki": test_lark_wiki.a_manifest(),
        "google_drive": test_google_drive.a_manifest(),
        "laravel": test_laravel.manifest(),
    }


#: Connectors whose tools are named after a table a deployment chooses, so a recording names
#: the table as `{entity}`.
NAMED_AFTER_THE_TABLE = frozenset({"lark_base"})

#: Kinds a connector need not have, and why each cannot be recorded for it.
NOT_RECORDABLE: Mapping[tuple[str, Kind], str] = {
    ("laravel", Kind.RATE_LIMIT): (
        "a database read through views has no rate limiter; "
        "laravel.THERE_IS_NO_MEASURED_CEILING_HERE"
    ),
}

#: Projections whose positive path no documented shape can replay, and why.
PROJECTION_NOT_REPLAYABLE: Mapping[tuple[str, str], str] = {
    ("google_drive", "file"): (
        "a file is kept only with a sharing state, which is reduced from the permissions Drive "
        "returns; the connector has no function reading them out of a response, and Google's "
        "documentation does not say whether a user grant carries the domain that reduction "
        "needs, so only a live capture can settle it"
    ),
}


def _declared(name: str, manifest: ConnectorManifest) -> tuple[set[str], set[str]]:
    tools = {
        tool.name.replace(tool.entity, "{entity}") if name in NAMED_AFTER_THE_TABLE else tool.name
        for tool in manifest.tools
    }
    projections = {
        "{entity}" if name in NAMED_AFTER_THE_TABLE else one.entity for one in manifest.projections
    }
    return tools, projections


def _connector_names() -> set[str]:
    return {
        info.name
        for info in pkgutil.iter_modules(brain.connectors.__path__)
        if info.name not in NOT_A_CONNECTOR
    }


ANSWERING = frozenset({Kind.LIST, Kind.READ, Kind.PAGINATION})
ANSWERED = frozenset({Expect.ANSWERED, Expect.ABSENT, Expect.MORE_TO_READ})


@pytest.mark.parametrize("recorded", CASSETTES, ids=[c.cid for c in CASSETTES])
def test_every_recording_replays_to_what_it_says_through_its_own_connector(
    recorded: Cassette,
) -> None:
    """**The replay.** The connector's own code reads the recording and must conclude what the
    recording says, and a success that feeds a projection must leave kept records.

    Delete this and a recording can say a 429 is a rate limit while the connector reads it as
    an empty table, with every other test green."""
    replayed = REPLAYS[recorded.source.value](recorded)

    assert replayed.outcome is recorded.expect, (
        f"{recorded.cid}: the connector concluded {replayed.outcome}, the recording says "
        f"{recorded.expect}"
    )
    replayable = (recorded.source.value, recorded.projects) not in PROJECTION_NOT_REPLAYABLE
    if recorded.projects and recorded.expect in ANSWERED and replayable:
        assert replayed.projected > 0, f"{recorded.cid} feeds a projection and kept nothing"
    leaked = [
        (one.source_id, name)
        for one in replayed.kept
        for name, value in one.fields.items()
        if "CANARY" in str(value)
    ]
    assert not leaked, f"{recorded.cid} kept a value a canary guards: {leaked}"


def test_the_replay_tells_a_refusal_from_an_absence_and_an_outage() -> None:
    """The positive sibling of the replay: the four outcomes are all reached, so a replay that
    returned one answer for everything could not pass.

    Delete this and every replay can collapse to ANSWERED with the parametrised test failing
    only for the recordings somebody happens to read."""
    reached = {REPLAYS[c.source.value](c).outcome for c in CASSETTES}
    assert {
        Expect.ANSWERED,
        Expect.ABSENT,
        Expect.MORE_TO_READ,
        Expect.RATE_LIMITED,
        Expect.REFUSED,
        Expect.UNREACHABLE,
        Expect.NOT_FOUND,
    } <= reached


def test_every_connector_has_a_replay_and_a_manifest() -> None:
    """Discovered, so a connector added to the package fails here until it is replayed.

    Delete this and the sweeps below compare nothing for the connector nobody registered."""
    assert _connector_names() == set(REPLAYS) == set(_manifests())


@pytest.mark.parametrize("name", sorted(REPLAYS))
def test_every_declared_tool_is_answered_by_a_recording(name: str) -> None:
    """**The sweep.** A tool the manifest declares with no recording answering it is a tool
    nobody has run against the source's shape, and it fails here by name.

    Delete this and a fourth HubSpot tool ships described as tested."""
    tools, _ = _declared(name, _manifests()[name])
    recorded = [c for c in CASSETTES if c.source.value == name]
    answered = {
        tool for c in recorded if c.kind in ANSWERING and c.expect in ANSWERED for tool in c.tools
    }
    assert tools, f"{name} declares no tools, so this compared nothing"
    assert not tools - answered, f"{name} declares tools no recording answers: {tools - answered}"
    orphaned = {tool for c in recorded for tool in c.tools} - tools
    assert not orphaned, f"recordings for {name} name tools it does not declare: {orphaned}"


@pytest.mark.parametrize("name", sorted(REPLAYS))
def test_every_declared_projection_is_fed_by_a_recording(name: str) -> None:
    """A projection no recording feeds is a table of kept rows nobody has built from the source's
    shape. The exceptions are named with the reason.

    Delete this and a projection can be declared, digested and connected with no row ever
    having been kept from anything the vendor sends."""
    _, projections = _declared(name, _manifests()[name])
    fed = {
        c.projects
        for c in CASSETTES
        if c.source.value == name and c.projects and c.expect in ANSWERED
    }
    missing = projections - fed
    assert not missing, f"{name} projects {missing} and no recording feeds it"


@pytest.mark.parametrize("name", sorted(REPLAYS))
def test_every_connector_has_a_page_a_rate_limit_and_an_error(name: str) -> None:
    """Pagination, rate limit and error are what a mock leaves out. Each is required of every
    connector unless `NOT_RECORDABLE` says why it cannot happen.

    Delete this and a connector can be recorded answering and never failing."""
    kinds = {c.kind for c in CASSETTES if c.source.value == name}
    for required in (Kind.PAGINATION, Kind.RATE_LIMIT, Kind.ERROR):
        if (name, required) in NOT_RECORDABLE:
            assert required not in kinds, (
                f"{name} is exempt from {required} and has a recording of it; drop the exemption"
            )
            continue
        assert required in kinds, f"{name} has no {required} recording"


def test_the_exemptions_name_connectors_and_kinds_that_exist() -> None:
    """The guard on the lists above: an exemption naming a typo exempts nothing and reads as a
    considered decision.

    Delete this and `NOT_RECORDABLE` can quietly outlive the connector it described."""
    names = _connector_names()
    assert NOT_RECORDABLE and PROJECTION_NOT_REPLAYABLE
    assert {name for name, _ in NOT_RECORDABLE} <= names
    for (name, entity), _why in PROJECTION_NOT_REPLAYABLE.items():
        assert entity in _declared(name, _manifests()[name])[1]


def test_no_recording_claims_a_live_read_it_does_not_date() -> None:
    """A live capture is a claim that a real account answered, and it has to say when. Nothing
    in the corpus makes that claim today, and a documented shape must name its page.

    Delete this and a recording can be relabelled live with nothing behind it, and the console
    would say so."""
    for c in CASSETTES:
        assert c.reference.strip(), f"{c.cid} names no reference"
        if c.origin is Origin.LIVE_CAPTURE:
            datetime.fromisoformat(c.captured_at)
        else:
            assert not c.captured_at, f"{c.cid} is a documented shape with a capture time"
    assert all(c.origin is Origin.DOCUMENTED_SHAPE for c in CASSETTES)


def test_the_console_record_of_recordings_agrees_with_the_corpus() -> None:
    """**Two records of one fact.** `brain.ops.connector_recordings.RECORDINGS` is what the
    Connectors screen says about each connector, and the corpus and this file are what make it
    true. Tested and gaps are compared here, never believed.

    Delete this and the screen can say a connector is tested against recorded responses the day
    its recordings are deleted."""
    assert set(RECORDINGS) == set(REPLAYS)
    for name, said in RECORDINGS.items():
        recorded = [c for c in CASSETTES if c.source.value == name]
        assert said.tested is bool(recorded)
        assert said.live_capture is any(c.origin is Origin.LIVE_CAPTURE for c in recorded)
        gaps = tuple(
            sorted(why for (who, _), why in PROJECTION_NOT_REPLAYABLE.items() if who == name)
        )
        assert said.not_replayed == gaps
        assert ("live account" in said.sentence()) and (
            "not answers captured from a live account" in said.sentence()
        ) is not said.live_capture


# ------------------------------------------ what the documented shapes found about the code
def test_a_documented_wiki_node_carries_no_member_setting_and_is_withheld() -> None:
    """**A finding, pinned.** Lark's documented node listing has no `has_member_setting`, which
    is the key `lark_wiki.restriction_of` reads, so every documented page is UNDETERMINED and
    `admit_page` withholds it. That is the safe direction and it means the wiki reads nothing
    until a live capture shows the key, or the connector learns another way to tell.

    Delete this and the day somebody defaults the missing key to "inherits" nothing notices."""
    from tests.unit.test_lark_wiki import SPACES

    listing = next(c for c in CASSETTES if c.cid == "LARK-WIKI-200-nodes-page")
    item = listing.body["data"]["items"][0]
    node = lark_wiki.node_from(item, space_id=SPACES[0].space_id)

    assert lark_wiki.MEMBER_SETTING_KEY not in item
    assert node.restriction is lark_wiki.NodeRestriction.UNDETERMINED
    with pytest.raises(lark_wiki.PageWithheldError):
        lark_wiki.admit_page(node, spaces=lark_wiki.declarations_by_space(SPACES))
    assert "has_member_setting" in RECORDINGS["lark_wiki"].sentence()


def test_lark_documents_its_wait_in_a_header_the_connectors_do_not_read() -> None:
    """**A finding, pinned.** Lark states the wait in `x-ogw-ratelimit-reset`; `lark_base` reads
    only `Retry-After`, so on the documented 429 it waits its own sixty seconds. That is never
    shorter than the documented reset here, which is why it is recorded rather than fixed.

    Delete this and a documented reset longer than the fallback would go unnoticed."""
    recorded = next(c for c in CASSETTES if c.cid == "LARK-429")
    reply = lark_base.LarkReply(
        status=recorded.status, headers=recorded.headers, body=recorded.body
    )

    assert lark_base.wait_seconds(reply) == lark_base.WAIT_WHEN_UNSTATED
    assert lark_base.wait_seconds(reply) >= float(recorded.headers["x-ogw-ratelimit-reset"])


@pytest.mark.parametrize(
    ("errno", "fault"),
    [
        (1142, laravel.DatabaseFault.ACCESS_DENIED),
        (1143, laravel.DatabaseFault.ACCESS_DENIED),
        (1146, laravel.DatabaseFault.UNKNOWN_VIEW),
        (3024, laravel.DatabaseFault.TIMED_OUT),
        (2006, laravel.DatabaseFault.UNAVAILABLE),
        (1064, laravel.DatabaseFault.UNAVAILABLE),
    ],
)
def test_a_mysql_error_number_is_the_fault_mysql_documents_it_as(
    errno: int, fault: laravel.DatabaseFault
) -> None:
    """The table a live reader and a replay share. 1064 is a number nobody listed, and it is
    read as the database not answering rather than as an empty view or a withdrawn grant.

    Delete this and a dropped view can be classified as an outage, which pages the wrong person."""
    assert laravel.fault_for_mysql_error(errno) is fault


def test_a_withdrawn_view_is_never_an_empty_one_when_replayed() -> None:
    """The positive and negative halves of the table meeting the interpreter.

    Delete this and 1146 could map to a fault that `interpret` reads as zero rows."""
    from tests.unit.test_laravel import a_read

    gone = laravel.interpret(
        a_read(),
        laravel.ViewReply(fault=laravel.fault_for_mysql_error(1146)),
        fetched_at=FETCHED_AT,
    )
    assert gone.outcome is laravel.LaravelOutcome.REFUSED
    assert gone.rows is None


def test_a_recording_for_a_connector_that_is_not_one_is_refused() -> None:
    """Every recording's source is a connector module, so no recording sits unreplayed.

    Delete this and a `Source` member can outlive its connector."""
    assert {s.value for s in Source} == _connector_names()


def test_a_contract_error_in_a_replay_is_not_swallowed() -> None:
    """A body that does not say whether there is more is a failure, not an answer. The replay
    must let the connector's own refusal through rather than classify it.

    Delete this and a replay that caught everything would pass every recording."""
    broken = Cassette(
        cid="LARK-broken",
        source=Source.LARK_BASE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        status=200,
        body={"code": 0, "data": {"items": []}},
        kind=Kind.LIST,
        expect=Expect.ABSENT,
        origin=Origin.DOCUMENTED_SHAPE,
        reference="test",
    )
    with pytest.raises(ConnectorContractError):
        _replay_lark_base(broken)
