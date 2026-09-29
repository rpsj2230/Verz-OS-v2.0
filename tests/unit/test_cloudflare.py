"""The Cloudflare connector, driven by the recordings rather than by an account.

Five properties are pinned here, each a way this connector goes wrong with nothing failing.

**It is connected with a token that can only read, and says so everywhere a person is told.** The
form's hint, the guide's first step and the vault slot ask for Zone Read, DNS Read and Analytics
Read and refuse DNS Write, and the manifest's binding is read-only, so a write tool on it is
refused.

**It keeps a minimal index and reads every value live.** A zone keeps its name, status and account;
a record its zone, name and type. The content every recorded record carries is a canary, and it
never survives the reading.

**A DNS record is named by its zone and itself.** The worker reads a zone's records under the zone,
and the live read reaches the one-record call from the index id alone.

**A DNS change is only ever prepared for a person.** The change declares a write and the owner's DNS
effect, so it is registered only with that effect, capped below Autonomous, suspended by the gate
under an Autonomous leash, refused for somebody without the grant, and when approved it still sends
nothing: its execution waits for the owner.

**Security events are read for a named window, without the visitor.** The window is from a closed
list, and the query names no address and no user agent.

The database half, the worker's walk and the answer on Ask, is `tests/unit/test_cloudflare_sync.py`
and the install check `tests/unit/test_acceptance_cloudflare.py`.

Task ids: M11.7.3
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from brain.connectors import cloudflare
from brain.connectors.cloudflare import (
    A_DNS_CHANGE_WAITS_FOR_THE_OWNER_TO_ISSUE_A_WRITE_KEY,
    CLOUDFLARE,
    CONNECTOR,
    DNS_CHANGE_TOOL,
    DNS_RECORD,
    DNS_RECORD_LISTING,
    LIVE_DNS_FIELDS,
    SECURITY_EVENT_FIELDS,
    TOKEN_PERMISSIONS,
    WRITE_PERMISSION,
    ZONE,
    CloudflareConnection,
    CloudflareEnvelopeError,
    CloudflareLiveLookup,
    CloudflareReading,
    DnsChange,
    DnsChangeWaitsForTheOwnerError,
    SecurityWindow,
)
from brain.connectors.contract import AccessMode, ConnectorContractError, CredentialBinding
from brain.connectors.declaration import (
    ConnectorDeclaration,
    DeclarationError,
    KeyScheme,
    ListedUnder,
    SettingRefusedError,
)
from brain.connectors.manifest import ManifestError, ToolDeclaration
from brain.connectors.minimal_index import assert_minimal_index, fresh_canary, plant, sightings
from brain.connectors.throttle import CallOutcome, ceiling_for
from brain.connectors.transports import SourceRecord
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import IdentityMode, SideEffect, TypedResult
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import (
    SENSITIVE_EFFECT_RUNG,
    Leash,
    LeashEntry,
    ResumeRefusal,
    Route,
    govern,
    resume,
)
from brain.knowledge.rows import RowRecord
from brain.ops.acceptance_checks import _HeldLedger
from brain.ops.connectable import connectable, key_reference, manifest_for, settings_problems
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.connector_sync_run import authorization
from brain.ops.limits import CLOUDFLARE_CALLS_PER_FIVE_MINUTES, connector_ceiling
from brain.tools.registry import (
    SensitiveEffect,
    ToolRegistrationError,
    ToolRegistry,
    default_rung,
    leash_ceiling,
    sensitive_effects_named_by,
)
from tests.fixtures.cassettes import FETCHED_AT, SEEN_AT, Cassette, limit_for
from tests.fixtures.cassettes.cloudflare import (
    ACCOUNT,
    CASSETTES,
    OTHER_ZONE,
    RECORD,
)
from tests.fixtures.cassettes.cloudflare import (
    ZONE as ZONE_ID,
)

#: The department a connection made here names.
DEPARTMENT: Final = "operations"

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

#: The id the index keeps for the recorded record: its zone's and its own.
INDEXED: Final = f"{ZONE_ID}/{RECORD}"


class Public:
    """A resolver placing every name on a public address, as Cloudflare's is."""

    def resolve(self, host: str) -> list[str]:
        del host
        return ["104.16.132.229"]


PUBLIC: Final = Public()


def cassette(cid: str) -> Cassette:
    return next(one for one in CASSETTES if one.cid == cid)


def console_settings(**changed: str) -> dict[str, str]:
    """What an administrator types on the Connectors screen to connect an account."""
    return {"account_id": ACCOUNT, "department": DEPARTMENT, **changed}


def a_console_manifest() -> Any:
    """The manifest a console connection builds, with the key where the console keeps it."""
    return manifest_for(CLOUDFLARE, console_settings())


# ------------------------------------------------------------------ connected from the console
def test_an_account_is_connected_from_the_console_with_its_id_its_department_and_a_token() -> None:
    """**The positive case.** The Connectors screen lists Cloudflare with two settings, and what
    they build is pinned to that account, keeps its rows under the department and the account typed,
    runs against Cloudflare's own verified ceiling and reads the token from the slot the console
    wrote it to, read-only. Delete this and the form can build a manifest scoped to nothing or
    visible to nobody with every refusal below still green."""
    form = connectable(CLOUDFLARE)
    built = a_console_manifest()

    assert [one.name for one in form.settings] == ["account_id", "department"]
    assert CONNECTOR.console is not None and CONNECTOR.not_from_the_console == ""
    assert built.scope.selectors == (ACCOUNT,)
    assert {one.entity for one in built.projections} == {ZONE, DNS_RECORD}
    for projection in built.projections:
        assert projection.visibility.matches({"department": DEPARTMENT, "account_id": ACCOUNT})
        assert not projection.visibility.matches({"department": DEPARTMENT, "account_id": "x"})
        assert not projection.visibility.matches({"department": "finance", "account_id": ACCOUNT})
    assert built.ceiling == CLOUDFLARE == ceiling_for(built).name
    assert built.credential.ref == key_reference(CLOUDFLARE)
    assert built.credential.mode is AccessMode.READ_ONLY
    assert all(one.side_effect is SideEffect.NONE for one in built.tools)
    assert all(one.identity_mode is IdentityMode.SERVICE for one in built.tools)
    assert settings_problems(form, console_settings()) == ()


@pytest.mark.parametrize(
    "typed", ["", "*", "all", "0123", "0123456789abcdef0123456789abcdeg", ACCOUNT + "0", "a b"]
)
def test_an_account_id_that_is_not_one_is_refused_naming_that_setting(typed: str) -> None:
    """**A reach rule.** The account is the scope every row is held to, so anything but Cloudflare's
    32 hex digits is refused at connect, naming the account setting. Delete this and a connection
    scoped to `*` or a typo is accepted and reads whatever the token reaches."""
    with pytest.raises(SettingRefusedError) as refused:
        CloudflareConnection.from_settings(console_settings(account_id=typed))

    assert refused.value.setting == "account_id"


def test_an_account_id_is_matched_whatever_case_it_was_pasted_in() -> None:
    """The sibling of the refusal: hex is case-free, so a capitalised paste is the same account and
    is pinned in lower case. Delete this and a refusal that turned every id away would pass."""
    connection = CloudflareConnection.from_settings(console_settings(account_id=ACCOUNT.upper()))

    assert connection.account_id == ACCOUNT
    assert connection.scope().admits(ACCOUNT)


@pytest.mark.parametrize("typed", ["Operations", "ops team", "ops-team", "*", "_ops"])
def test_a_department_no_grant_could_name_is_refused(typed: str) -> None:
    """**A permission rule.** Every kept row carries the department, and a grant names only a
    department's short name. Delete this and an account connects, syncs and is unreadable."""
    with pytest.raises(SettingRefusedError) as refused:
        CloudflareConnection.from_settings(console_settings(department=typed))

    assert refused.value.setting == "department"


# ------------------------------------------------------------------ the token asked for
def test_every_place_a_person_is_told_asks_for_the_three_read_permissions_and_never_dns_write() -> (
    None
):
    """**The token can only read, and every screen says so in Cloudflare's own words.** The form's
    hint, the guide's first step and the vault slot name Zone Read, DNS Read and Analytics Read; the
    slot refuses DNS Write and the hint warns against it; and the guide's first step links to the
    dashboard's token page. Delete this and a hint drifts to "DNS Edit" and the token that can take
    a website off the internet is the one pasted."""
    form = CONNECTOR.console
    assert form is not None
    slot = SLOT_SCOPES[CLOUDFLARE]
    first = CONNECTOR.guide[0]

    assert slot.request == TOKEN_PERMISSIONS
    assert WRITE_PERMISSION in slot.refuse and WRITE_PERMISSION not in slot.request
    for permission in TOKEN_PERMISSIONS:
        assert permission in form.credential_hint
        assert permission in first.text
        assert any(line.label == permission for line in first.sketch.lines)
    assert f"Never a token with {WRITE_PERMISSION}" in form.credential_hint
    assert first.link == cloudflare.API_TOKENS_URL
    assert first.link.startswith("https://dash.cloudflare.com/")
    assert CONNECTOR.guide[-1].asks == ("account_id", "department", "credential")


def test_a_dns_change_is_refused_as_a_tool_on_the_read_manifest() -> None:
    """**Never with the read token.** A tool that writes, declared on the manifest a connection
    builds, is refused by the manifest itself, because its binding is read-only. The positive half:
    the manifest as shipped builds. Delete this and a write can be added to the read manifest and
    run with the token the guide told a person could only read."""
    built = a_console_manifest()
    writing = ToolDeclaration(
        name="cloudflare.update_dns_record",
        description="Change one DNS record.",
        entity=DNS_RECORD,
        side_effect=SideEffect.WRITE,
        identity_mode=IdentityMode.SERVICE,
        verifies_write=True,
    )

    with pytest.raises(ManifestError, match="read_only"):
        replace(built, tools=(*built.tools, writing))
    assert built.credential == CredentialBinding(ref=key_reference(CLOUDFLARE))


# ------------------------------------------------------------------ the ceiling
def test_the_ceiling_is_cloudflares_documented_five_minute_figure_recorded_per_minute() -> None:
    """Cloudflare documents 1,200 calls per five minutes per user, and the row records a fifth of it
    a minute, which a sliding minute can never exceed over five. Asserted against the cassette's
    own record of the vendor's figure rather than against itself, and the ceiling is unraisable on
    both. Delete this and the row can drift to a number no documentation states."""
    row = connector_ceiling(CLOUDFLARE)
    recorded = limit_for(CLOUDFLARE)

    assert row is not None
    assert recorded.calls == CLOUDFLARE_CALLS_PER_FIVE_MINUTES
    assert row.per_minute * 5 <= recorded.calls < (row.per_minute + 1) * 5
    assert "1,200 requests per five minutes" in row.note
    assert row.raisable is recorded.raisable is False
    assert cloudflare.CEILING_NAME == cloudflare.CONNECTOR_NAME


# ------------------------------------------------------------------ the worker's reading
def test_the_worker_reads_the_zones_first_and_each_zones_records_under_it() -> None:
    """The zones list at its largest page, then the DNS records listed under each zone by its id in
    the path, a hundred to a page, with the token as a bearer and no header of the reading's own.
    Delete this and the records are asked for with no zone, which Cloudflare cannot answer, or
    before the zones they are listed under."""
    reading = CloudflareReading()
    zones = reading.operation(ZONE, settings=console_settings(), resolver=PUBLIC)
    records = reading.operation(DNS_RECORD, settings=console_settings(), resolver=PUBLIC)
    first = {**reading.first_page(DNS_RECORD), "zone_id": ZONE_ID}

    assert reading.entities() == (ZONE, DNS_RECORD)
    assert reading.listed_under(ZONE) is None
    assert reading.listed_under(DNS_RECORD) == ListedUnder(parent=ZONE, parameter="zone_id")
    assert zones.url_for(reading.first_page(ZONE)) == (
        f"{cloudflare.API_BASE}/zones?page=1&per_page=50"
    )
    assert records.url_for(first) == (
        f"{cloudflare.API_BASE}/zones/{ZONE_ID}/dns_records?page=1&per_page=100"
    )
    assert reading.key_scheme() is KeyScheme.BEARER
    assert authorization(reading.key_scheme(), "sentinel") == "Bearer sentinel"
    assert dict(reading.call_headers(console_settings())) == {}


def test_a_page_is_followed_only_when_it_is_full_and_its_envelope_says_there_is_another() -> None:
    """From the recordings: a full page of zones saying page 1 of 2 is followed to page 2, and the
    page saying 1 of 1 ends the walk, as does a short page whatever its envelope says. Delete this
    and the first fifty zones are read as the account, or the walk asks past the last page."""
    reading = CloudflareReading()
    first = reading.first_page(ZONE)
    full = cassette("CF-200-zones-full-page").body
    only = cassette("CF-200-zones").body

    following = reading.next_page(ZONE, first, full, 50)
    assert following is not None and dict(following) == {**first, "page": "2"}
    assert reading.next_page(ZONE, first, only, 2) is None
    assert reading.next_page(ZONE, first, full, 49) is None
    assert reading.next_page(ZONE, first, {**full, "result_info": {}}, 50) is not None


def test_a_reply_whose_envelope_does_not_say_success_is_refused_and_an_empty_one_is_answered() -> (
    None
):
    """**`AN_ENVELOPE_THAT_SAYS_IT_FAILED_IS_NOT_AN_EMPTY_PAGE`.** A 200 whose envelope says success
    false, or holds no envelope at all, is refused rather than read as no zones; an answered empty
    page is an answer with no rows. Delete this and a refusal inside a 200 empties the index."""
    reading = CloudflareReading()
    operation = cloudflare.zones_operation()
    failed = {"success": False, "errors": [{"code": 1000}], "messages": [], "result": []}

    for body in (failed, [], {"result": []}):
        with pytest.raises(CloudflareEnvelopeError):
            reading.interpret(operation, status=200, body=body, fetched_at=FETCHED_AT)
    empty = reading.interpret(
        operation,
        status=200,
        body=cassette("CF-200-dns-records-empty").body,
        fetched_at=FETCHED_AT,
    )
    assert empty.call is CallOutcome.OK
    assert empty.rows is not None and empty.rows.records == () and not empty.rows.truncated


def test_a_refusal_and_a_rate_limit_carry_no_rows_and_the_wait_is_read_from_the_source() -> None:
    """From the recordings: a 403 is refused, a 429 is a quota with Retry-After's five minutes, and
    `Ratelimit` with nothing left says the allowance is spent while one with some left does not.
    Delete this and a refused token is written as an account with no zones."""
    reading = CloudflareReading()
    operation = cloudflare.dns_records_operation()
    limited = cassette("CF-429")

    refused = reading.interpret(
        operation, status=403, body=cassette("CF-403").body, fetched_at=FETCHED_AT
    )
    quota = reading.interpret(operation, status=429, body=limited.body, fetched_at=FETCHED_AT)
    assert (refused.call, refused.rows) == (CallOutcome.REJECTED, None)
    assert (quota.call, quota.rows) == (CallOutcome.QUOTA, None)
    assert reading.retry_after(limited.headers) == 300.0
    assert reading.retry_after({"retry-after": "12"}) == 12.0
    assert reading.retry_after({}) is None
    assert reading.allowance_spent(limited.headers) is True
    assert reading.allowance_spent({"ratelimit": '"default";r=50;t=30'}) is False
    assert reading.allowance_spent({}) is False


# ------------------------------------------------------------------ the minimal index
def test_a_record_keeps_its_zone_name_and_type_and_its_content_never_survives() -> None:
    """**The owner's rule, from the recording.** A canary minted for this run is planted in every
    record's content and comment, the page is read under its zone, and what is kept is inside the
    manifest's minimal index, named by the zone and the record, and holds the canary nowhere. The
    positive half: the record's name is kept. Delete this and the reading can start keeping a
    record's content with every test over one field green."""
    reading = CloudflareReading()
    canary = fresh_canary("CLOUDFLARE")
    body, count = plant(cassette("CF-200-dns-records").body, canary)
    reply = reading.interpret(
        cloudflare.dns_records_operation(), status=200, body=body, fetched_at=FETCHED_AT
    )
    assert reply.rows is not None and count >= 2
    named = DNS_RECORD_LISTING.named(reply.rows, ZONE_ID)

    kept = [
        reading.projected(DNS_RECORD, row.model_dump(), seen_at=SEEN_AT) for row in named.records
    ]

    assert all(one is not None for one in kept)
    kept_rows = [one for one in kept if one is not None]
    assert_minimal_index(a_console_manifest(), kept_rows)
    assert sightings(canary, kept_rows, reply.rows) == ()
    first = kept_rows[0]
    assert first.source_id == INDEXED
    assert first.fields == {"zone_id": ZONE_ID, "name": "www.example.com", "type": "A"}
    assert not set(LIVE_DNS_FIELDS) & {one.target for one in cloudflare.DNS_LIST_MAPPING}


def test_a_zone_keeps_its_name_status_and_account_and_never_its_name_servers() -> None:
    """A zone's index entry, from the recording, is its name, status and the account Cloudflare
    says it belongs to; its name servers arrive and are not kept. Delete this and the zone's
    account, which the visibility rule tests, can stop being carried."""
    reading = CloudflareReading()
    reply = reading.interpret(
        cloudflare.zones_operation(),
        status=200,
        body=cassette("CF-200-zones").body,
        fetched_at=FETCHED_AT,
    )
    assert reply.rows is not None
    kept = [
        reading.projected(ZONE, row.model_dump(), seen_at=SEEN_AT) for row in reply.rows.records
    ]

    assert [None if one is None else one.source_id for one in kept] == [ZONE_ID, OTHER_ZONE]
    assert kept[0] is not None
    assert kept[0].fields == {"name": "example.com", "status": "active", "account_id": ACCOUNT}


def test_a_record_the_walk_did_not_name_by_its_zone_is_refused_rather_than_kept() -> None:
    """A DNS record's index id must name its zone, because the live read reaches it from nothing
    else. A row arriving with the record's own id alone is refused. Delete this and a record is kept
    under an id no question can read it back by."""
    with pytest.raises(ConnectorContractError):
        CloudflareReading().projected(DNS_RECORD, {"id": RECORD, "name": "x"}, seen_at=SEEN_AT)


# ------------------------------------------------------------------ a record listed under another
def test_a_listed_record_is_named_by_its_parent_and_itself_and_taken_apart_the_same_way() -> None:
    """**The id both halves agree on.** Rows read under a zone are named zone/record and carry the
    zone, and the index id splits back into the two. Delete this and the worker and the live read
    can come to name one record two ways, which reads as the record having gone."""
    rows = TypedResult[SourceRecord](
        records=(SourceRecord(entity=DNS_RECORD, id=RECORD),), source="s", fetched_at=FETCHED_AT
    )
    named = DNS_RECORD_LISTING.named(rows, ZONE_ID)

    (one,) = named.records
    assert one.id == INDEXED
    assert one.model_dump()["zone_id"] == ZONE_ID
    assert DNS_RECORD_LISTING.split(INDEXED) == (ZONE_ID, RECORD)


@pytest.mark.parametrize("given", ["", RECORD, f"/{RECORD}", f"{ZONE_ID}/", f"a/b/{RECORD}"])
def test_an_id_that_does_not_name_a_parent_and_a_record_is_refused(given: str) -> None:
    """Delete this and an id with no zone, or with a separator inside a half, is split into a zone
    the record is not in, and the live read asks Cloudflare for somebody else's record."""
    with pytest.raises(ConnectorContractError):
        DNS_RECORD_LISTING.split(given)


def test_an_id_holding_the_separator_cannot_be_joined() -> None:
    """Delete this and a vendor id holding a slash is joined into an id that splits differently."""
    with pytest.raises(ConnectorContractError):
        DNS_RECORD_LISTING.source_id("a/b", RECORD)
    assert DNS_RECORD_LISTING.source_id(ZONE_ID, RECORD) == INDEXED


def test_an_entity_listed_under_one_its_reading_does_not_read_first_is_refused() -> None:
    """**A declaration the walk could not follow is refused at start-up.** A reading listing records
    under zones must read the zones first, or the walk has no parent to list them under and reads
    nothing while saying it read to the end. Delete this and that reading ships."""

    class Backwards(CloudflareReading):
        def entities(self) -> tuple[str, ...]:
            return (DNS_RECORD, ZONE)

    with pytest.raises(DeclarationError, match="does not read first"):
        replace(CONNECTOR, reading=Backwards())
    assert isinstance(replace(CONNECTOR, reading=CloudflareReading()), ConnectorDeclaration)


# ------------------------------------------------------------------ reading one record live
def test_a_record_is_read_live_by_its_own_call_under_its_zone() -> None:
    """The live lookup reads a DNS record by the one-record call, with the zone laid into the path
    by its listing, and its values in the mapping; a zone by its own call. Delete this and a live
    read lists a whole zone to answer about one record, or reads it without its content."""
    lookup = CloudflareLiveLookup()
    record = lookup.operation(DNS_RECORD, settings=console_settings(), resolver=PUBLIC)
    zone = lookup.operation(ZONE, settings=console_settings(), resolver=PUBLIC)
    assert record is not None and zone is not None

    arguments = {"zone_id": ZONE_ID, **lookup.arguments_for(DNS_RECORD, RECORD)}
    assert record.url_for(arguments) == (
        f"{cloudflare.API_BASE}/zones/{ZONE_ID}/dns_records/{RECORD}"
    )
    assert zone.url_for(lookup.arguments_for(ZONE, ZONE_ID)) == (
        f"{cloudflare.API_BASE}/zones/{ZONE_ID}"
    )
    assert set(LIVE_DNS_FIELDS) <= {one.target for one in record.transport.fields}
    assert lookup.identity_mode(DNS_RECORD) is IdentityMode.SERVICE


@pytest.mark.parametrize("given", ["../zones", RECORD.upper() + "?x=1", "1", "", "*"])
def test_an_id_that_could_change_the_address_is_refused_rather_than_escaped(given: str) -> None:
    """Delete this and an id laid into Cloudflare's path could name another endpoint."""
    with pytest.raises(ConnectorContractError):
        CloudflareLiveLookup().arguments_for(DNS_RECORD, given)


# ------------------------------------------------------------------ security events
def test_security_events_are_read_for_a_named_window_ending_at_the_question() -> None:
    """The query is Cloudflare's `firewallEventsAdaptive` for one zone between two instants computed
    from the window's name, POSTed to the GraphQL endpoint, newest first, a hundred at most. Delete
    this and the window a question names is not the window read."""
    asked = cloudflare.security_events_request(ZONE_ID, "past_24_hours", now=NOW)
    variables = asked.body["variables"]

    assert asked.url == f"{cloudflare.API_BASE}/graphql"
    assert variables["zoneTag"] == ZONE_ID
    assert variables["filter"] == {
        "datetime_geq": (NOW - timedelta(days=1)).isoformat(),
        "datetime_leq": NOW.isoformat(),
    }
    assert "firewallEventsAdaptive(" in asked.body["query"]
    assert "orderBy: [datetime_DESC]" in asked.body["query"]
    hour = cloudflare.security_events_request(ZONE_ID, SecurityWindow.PAST_HOUR, now=NOW)
    assert (
        hour.body["variables"]["filter"]["datetime_geq"] == (NOW - timedelta(hours=1)).isoformat()
    )


@pytest.mark.parametrize(
    ("zone", "window", "now"),
    [
        (ZONE_ID, "past_year", NOW),
        (ZONE_ID, "2019-01-01", NOW),
        ("example.com", "past_hour", NOW),
        (ZONE_ID, "past_hour", NOW.replace(tzinfo=None)),
    ],
)
def test_a_window_off_the_list_a_zone_that_is_not_an_id_and_a_clock_with_no_zone_are_refused(
    zone: str, window: str, now: datetime
) -> None:
    """**`A_WINDOW_IS_NAMED_FROM_A_CLOSED_LIST`.** Delete this and a typed date past the plan's
    retention is asked for, answered as an empty list, and read as a quiet week."""
    with pytest.raises(ConnectorContractError):
        cloudflare.security_events_request(zone, window, now=now)


def test_the_query_names_no_visitor_address_and_no_user_agent() -> None:
    """**`A_SECURITY_EVENT_IS_READ_WITHOUT_ITS_VISITOR`.** The fields the query selects are parsed
    out of the query itself and are exactly the declared ones, and neither the visitor's address nor
    their user agent is among them. Delete this and a question about a blocked request is answered
    with the address of the person who made it."""
    query = cloudflare.SECURITY_EVENTS_QUERY
    selected = query.rsplit("{", 1)[1].split("}", 1)[0].split()

    assert selected == [theirs for _, theirs in SECURITY_EVENT_FIELDS]
    assert not {"clientIP", "userAgent", "clientRequestQuery"} & set(selected)
    assert re.search(r"clientIP|userAgent", query) is None


def test_events_are_answered_and_a_refusal_inside_a_200_is_never_an_empty_list() -> None:
    """From the recordings: the events are read into our names, and GraphQL's errors in a 200, a
    reply naming no zone and a 429 are each not an answer. Delete this and a window the plan does
    not keep reads as a zone nobody attacked."""
    answered = cloudflare.security_events(
        200, cassette("CF-200-security-events").body, fetched_at=FETCHED_AT
    )
    refused = cloudflare.security_events(
        200, cassette("CF-200-graphql-errors").body, fetched_at=FETCHED_AT
    )
    unreached = cloudflare.security_events(
        200, {"data": {"viewer": {"zones": []}}, "errors": None}, fetched_at=FETCHED_AT
    )
    quota = cloudflare.security_events(429, {}, fetched_at=FETCHED_AT)

    assert answered.call is CallOutcome.OK and answered.rows is not None
    (event,) = answered.rows.records
    assert event.model_dump() == {
        "entity": cloudflare.SECURITY_EVENT,
        "id": "5ed1e1d58f1c0f1a",
        "action": "block",
        "country": "NL",
        "host": "www.example.com",
        "path": "/wp-login.php",
        "occurred_at": "2019-06-01T11:58:00Z",
        "rule_id": "100015",
        "detected_by": "firewallManaged",
    }
    assert (refused.call, refused.rows) == (CallOutcome.REJECTED, None)
    assert (unreached.call, unreached.rows) == (CallOutcome.REJECTED, None)
    assert (quota.call, quota.rows) == (CallOutcome.QUOTA, None)


# ------------------------------------------------------------------ a DNS change, prepared only
def a_change(**changed: str) -> DnsChange:
    values = {"record": INDEXED, "name": "www.example.com", "record_type": "A"}
    values["content"] = "192.0.2.10"
    values.update(changed)
    return DnsChange(**values)


def test_the_dns_change_declares_a_write_and_the_owners_dns_effect_so_it_is_never_autonomous() -> (
    None
):
    """**`A_DNS_CHANGE_IS_ONLY_EVER_PREPARED_FOR_A_PERSON`, at the registry.** The change is a
    write, so its default rung is Assisted; its name reads as a DNS change, so it registers only
    declaring that effect; and registered, its leash ceiling is at most the sensitive-effect rung.
    Delete this and the change can be declared a read, or registered Autonomous, and run by an agent
    unasked."""
    assert DNS_CHANGE_TOOL.side_effect is SideEffect.WRITE
    assert default_rung(DNS_CHANGE_TOOL.side_effect) is AutonomyTier.ASSISTED
    assert default_rung(DNS_CHANGE_TOOL.side_effect) < AutonomyTier.AUTONOMOUS
    assert DNS_CHANGE_TOOL.declares_sensitive_effect()
    assert sensitive_effects_named_by(DNS_CHANGE_TOOL.name) == {SensitiveEffect.DNS_OR_HOSTING}
    assert leash_ceiling(DNS_CHANGE_TOOL) <= SENSITIVE_EFFECT_RUNG < AutonomyTier.AUTONOMOUS

    async def handler(*, entitlement: EntitlementSet) -> TypedResult[RowRecord]:
        del entitlement
        raise AssertionError("never called")

    scope = Scope.department(DEPARTMENT)
    with pytest.raises(ToolRegistrationError):
        ToolRegistry().register(
            DNS_CHANGE_TOOL.model_copy(update={"sensitive": False}), handler, scope=scope
        )
    held = ToolRegistry().register(
        DNS_CHANGE_TOOL, handler, scope=scope, sensitive_effect=SensitiveEffect.DNS_OR_HOSTING
    )
    assert held.leash_ceiling <= SENSITIVE_EFFECT_RUNG


#: What the operator preparing a change and an approver hold, in the department the zones answer to.
WRITES: Final = ("write:dns_record", "read:dns_record.name", "read:dns_record.type")
READS_CONTENT: Final = "read:dns_record.content"
POLICY: Final = FieldPolicy(
    rules=tuple(
        FieldRule.of(DNS_RECORD, name, f"read:dns_record.{name}", Classification.INTERNAL)
        for name in ("name", "type", "content")
    )
)
AGENT: Final = "agent.dns"


def holding(principal: str, *capabilities: str) -> EntitlementSet:
    scope = Scope.department(DEPARTMENT)
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities),
    )


OPERATOR: Final = holding("u_operator", *WRITES, READS_CONTENT)
CEILING: Final = holding(AGENT, *WRITES, READS_CONTENT)
AUTONOMOUS: Final = Leash(
    entries=(
        LeashEntry(
            agent_id=AGENT,
            target=DNS_RECORD,
            scope=Scope.department(DEPARTMENT),
            rung=AutonomyTier.AUTONOMOUS,
        ),
    )
)
CALM: Final = RiskAssessment(score=0, matched=())


class Recorder:
    """What the gate is handed as the change's execution and its simulation, counting calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, action: Any) -> TypedResult[Any]:
        self.calls.append(action.tool.name)
        return TypedResult(records=(), source=CLOUDFLARE, fetched_at=FETCHED_AT)


def governed(caller: EntitlementSet, leash: Leash, executed: Recorder, simulated: Recorder) -> Any:
    return govern(
        cloudflare.prepare_dns_change(a_change(), agent_id=AGENT, department=DEPARTMENT),
        caller=caller,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=leash,
        assessment=CALM,
        trace_id="t-dns",
        now=NOW,
        simulate=simulated,
        execute=executed,
        ledger=_HeldLedger(),
    )


def test_a_dns_change_under_an_autonomous_leash_is_suspended_for_a_person_and_never_run() -> None:
    """**The prepared action.** An agent whose leash says Autonomous on DNS records prepares a
    change: the gate suspends it, the artefact an approver reads names the record and the content
    it would get, and nothing runs. Delete this and the one change the owner named as needing a
    person is made by an agent because somebody promoted its leash."""
    executed, simulated = Recorder(), Recorder()

    done = governed(OPERATOR, AUTONOMOUS, executed, simulated)

    assert done.route is Route.SUSPEND
    assert done.suspension is not None
    assert "cloudflare.change_dns_record on dns_record" in done.suspension.artefact
    assert "content: 192.0.2.10" in done.suspension.artefact
    assert "name: www.example.com" in done.suspension.artefact
    assert executed.calls == [] and simulated.calls == []
    assert done.suspension.action.row["department"] == DEPARTMENT


def test_a_dns_change_is_simulated_with_no_leash_and_refused_to_somebody_without_the_grant() -> (
    None
):
    """The two other doors, both shut: no leash entry is Shadow, which simulates and sends nothing,
    and a caller who does not hold `write:dns_record` in the department is refused before any rung
    is read. Delete this and an unconfigured agent or an ungranted person gets past the prepared
    action by a route the test above does not walk."""
    executed, simulated = Recorder(), Recorder()

    shadow = governed(OPERATOR, Leash(), executed, simulated)
    refused = governed(holding("u_reader", READS_CONTENT), AUTONOMOUS, executed, simulated)

    assert shadow.route is Route.SIMULATE and simulated.calls == [DNS_CHANGE_TOOL.name]
    assert refused.route is Route.REFUSED and refused.suspension is None
    assert executed.calls == []


def test_an_approved_dns_change_still_sends_nothing_and_says_it_waits_for_the_owner() -> None:
    """**`A_DNS_CHANGE_WAITS_FOR_THE_OWNER_TO_ISSUE_A_WRITE_KEY`.** A person approves the prepared
    change and it is resumed with the connector's own execution, which refuses with the owner's
    question and sends nothing; an unapproved one is not even tried. Delete this and an approved
    change can be sent with the read token, or with no read-back, before the owner decided."""
    done = governed(OPERATOR, AUTONOMOUS, Recorder(), Recorder())
    assert done.suspension is not None
    pending = resume(
        done.suspension,
        caller=OPERATOR,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=AUTONOMOUS,
        assessment=CALM,
        trace_id="t-resume",
        now=NOW,
        execute=cloudflare.execute_dns_change,
        ledger=_HeldLedger(),
    )
    approved = done.suspension.approved_by("u_approver", NOW)

    assert (pending.resumed, pending.refusal) == (False, ResumeRefusal.NOT_APPROVED)
    with pytest.raises(DnsChangeWaitsForTheOwnerError) as waits:
        resume(
            approved,
            caller=OPERATOR,
            agent_ceiling=CEILING,
            policy=POLICY,
            leash=AUTONOMOUS,
            assessment=CALM,
            trace_id="t-resume",
            now=NOW,
            execute=cloudflare.execute_dns_change,
            ledger=_HeldLedger(),
        )
    assert str(waits.value) == A_DNS_CHANGE_WAITS_FOR_THE_OWNER_TO_ISSUE_A_WRITE_KEY
    assert "should approved DNS changes be sent" in str(waits.value)


@pytest.mark.parametrize(
    ("changed", "why"),
    [
        ({"content": "300.1.1.1"}, "not an IPv4 address"),
        ({"record_type": "AAAA", "content": "192.0.2.10"}, "not an IPv6 address"),
        ({"record_type": "CNAME", "content": "not a host"}, "not a host name"),
        ({"record_type": "TXT", "content": "x" * 2049}, "longer than a TXT record takes"),
        ({"record_type": "MX", "content": "10 mail.example.com"}, "a type nothing checks"),
        ({"record": RECORD}, "no zone in the id"),
        ({"name": "www example com"}, "a name that is not a host"),
    ],
)
def test_a_change_whose_content_is_not_its_types_is_refused_before_anybody_is_asked(
    changed: dict[str, str], why: str
) -> None:
    """Delete this and a person is asked to approve an A record pointing at no address, and approves
    it because the card looked like every other."""
    with pytest.raises(ConnectorContractError):
        a_change(**changed)
    assert why


def test_a_change_of_each_type_whose_content_fits_is_prepared_and_would_patch_that_record() -> None:
    """The positive sibling: an A, an AAAA, a CNAME and a TXT change each fit, and what sending one
    would be is a PATCH of that record's content at its zone. Delete this and the checks above pass
    by refusing everything."""
    for record_type, content in (
        ("A", "192.0.2.10"),
        ("AAAA", "2001:db8::1"),
        ("CNAME", "target.example.net"),
        ("TXT", "v=spf1 -all"),
    ):
        change = a_change(record_type=record_type, content=content)
        method, url, body = cloudflare.dns_change_call(change)
        assert (method, dict(body)) == ("PATCH", {"content": content})
        assert url == f"{cloudflare.API_BASE}/zones/{ZONE_ID}/dns_records/{RECORD}"
    with pytest.raises(ConnectorContractError):
        cloudflare.prepare_dns_change(a_change(), agent_id=AGENT, department="Ops Team")
