"""Cloudflare's recordings: the zones list and a full page of it, one zone, a zone's DNS records and
an empty zone, one record, a zone's security events, a GraphQL refusal inside a 200, a rate limit
and a refused token.

Every body is Cloudflare's documented envelope, `{"success", "errors", "messages", "result",
"result_info"}`, and every id is one of the documentation's own examples. A record's content carries
a canary: it is read live and never kept.

Task ids: M11.7.3, M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from typing import Any, Final

from brain.connectors import cloudflare
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import CallOutcome
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    FETCHED_AT,
    SEEN_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "cloudflare"

API_DOC: Final = "https://developers.cloudflare.com/api/resources/"

#: Ids from Cloudflare's own API reference examples.
ACCOUNT: Final = "01a7362d577a6c3019a474fd6f485823"
ZONE: Final = "023e105f4ecef8ad9ca31a8372d0c353"
OTHER_ZONE: Final = "9a7806061c88ada191ed06f989cc3dac"
RECORD: Final = "372e67954025e0ba6aaa6d586b9e0b59"


def envelope(result: Any, *, page: int = 1, per_page: int = 50, pages: int = 1) -> dict[str, Any]:
    """Cloudflare's documented envelope around a list, with the page it is."""
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": result,
        "result_info": {
            "page": page,
            "per_page": per_page,
            "count": len(result),
            "total_count": len(result) + (pages - page) * per_page,
            "total_pages": pages,
        },
    }


def a_zone(zone_id: str, name: str, *, account: str = ACCOUNT) -> dict[str, Any]:
    """A zone as `GET /zones` documents it, its name servers a value the index never keeps."""
    return {
        "id": zone_id,
        "name": name,
        "status": "active",
        "paused": False,
        "type": "full",
        "account": {"id": account, "name": "Example Account"},
        "name_servers": ["bob.ns.cloudflare.com", "lola.ns.cloudflare.com"],
        "created_on": "2014-01-01T05:20:00.12345Z",
        "modified_on": "2014-01-01T05:20:00.12345Z",
        "activated_on": "2014-01-02T00:01:00.12345Z",
    }


def a_record(record_id: str, name: str, record_type: str = "A") -> dict[str, Any]:
    """A DNS record as `GET /zones/{zone_id}/dns_records` documents it. The content is a canary."""
    return {
        "id": record_id,
        "name": name,
        "type": record_type,
        "content": "CANARY-DNS-CONTENT",
        "proxiable": True,
        "proxied": False,
        "ttl": 3600,
        "comment": "CANARY-DNS-COMMENT",
        "tags": [],
        "created_on": "2014-01-01T05:20:00.12345Z",
        "modified_on": "2014-01-01T05:20:00.12345Z",
        "meta": {},
    }


def _hex(number: int) -> str:
    return f"{number:032x}"


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="CF-200-zones",
        source=SOURCE,
        request="GET /client/v4/zones?page=1&per_page=50",
        status=200,
        body=envelope([a_zone(ZONE, "example.com"), a_zone(OTHER_ZONE, "example.net")]),
        why="The zones the token reaches, in the envelope every list shares: result, and "
        "result_info saying this is page 1 of 1, which is the only end signal the reading "
        "trusts besides a short page. Name servers arrive and are not kept.",
        kind=Kind.LIST,
        tools=("cloudflare.list_zones",),
        projects="zone",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=API_DOC + "zones/methods/list/",
    ),
    Cassette(
        cid="CF-200-zones-full-page",
        source=SOURCE,
        request="GET /client/v4/zones?page=1&per_page=50",
        status=200,
        body=envelope([a_zone(_hex(n + 1), f"zone{n}.example.org") for n in range(50)], pages=2),
        why="Fifty zones and a result_info saying page 1 of 2. A full page whose envelope says "
        "there is another is read on.",
        kind=Kind.PAGINATION,
        tools=("cloudflare.list_zones",),
        projects="zone",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=API_DOC + "zones/methods/list/",
    ),
    Cassette(
        cid="CF-200-zone",
        source=SOURCE,
        request=f"GET /client/v4/zones/{ZONE}",
        status=200,
        body={"success": True, "errors": [], "messages": [], "result": a_zone(ZONE, "example.com")},
        why="One zone by its id, read live: the object under result, with no result_info.",
        kind=Kind.READ,
        tools=("cloudflare.read_zone",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=API_DOC + "zones/methods/get/",
    ),
    Cassette(
        cid="CF-200-dns-records",
        source=SOURCE,
        request=f"GET /client/v4/zones/{ZONE}/dns_records?page=1&per_page=100",
        status=200,
        body=envelope(
            [a_record(RECORD, "www.example.com"), a_record(_hex(7), "example.com", "MX")],
            per_page=100,
        ),
        why="One zone's records, as the worker reads them under the zone. Every record's content "
        "arrives on the list and is a canary: the mapping the scheduled read uses names only the "
        "id, the name and the type. No record carries its zone's id, which is why the index names "
        "a record by its zone's id and its own.",
        kind=Kind.LIST,
        tools=("cloudflare.list_dns_records",),
        projects="dns_record",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=API_DOC + "dns/subresources/records/methods/list/",
    ),
    Cassette(
        cid="CF-200-dns-records-empty",
        source=SOURCE,
        request=f"GET /client/v4/zones/{ZONE}/dns_records?page=1&per_page=100",
        status=200,
        body=envelope([], per_page=100),
        why="A zone with no records: an answered, last page with nothing on it, which is an "
        "absence and never a failure.",
        kind=Kind.LIST,
        tools=("cloudflare.list_dns_records",),
        projects="dns_record",
        expect=Expect.ABSENT,
        origin=DOCUMENTED,
        reference=API_DOC + "dns/subresources/records/methods/list/",
    ),
    Cassette(
        cid="CF-200-dns-record",
        source=SOURCE,
        request=f"GET /client/v4/zones/{ZONE}/dns_records/{RECORD}",
        status=200,
        body={
            "success": True,
            "errors": [],
            "messages": [],
            "result": a_record(RECORD, "www.example.com"),
        },
        why="One record by its zone and its id, read live while somebody waits: its content, time "
        "to live and proxying are the values a question asks for and are never kept.",
        kind=Kind.READ,
        tools=("cloudflare.read_dns_record",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=API_DOC + "dns/subresources/records/methods/get/",
    ),
    Cassette(
        cid="CF-200-security-events",
        source=SOURCE,
        request="POST /client/v4/graphql",
        status=200,
        body={
            "data": {
                "viewer": {
                    "zones": [
                        {
                            "firewallEventsAdaptive": [
                                {
                                    "rayName": "5ed1e1d58f1c0f1a",
                                    "action": "block",
                                    "clientCountryName": "NL",
                                    "clientRequestHTTPHost": "www.example.com",
                                    "clientRequestPath": "/wp-login.php",
                                    "datetime": "2019-06-01T11:58:00Z",
                                    "ruleId": "100015",
                                    "source": "firewallManaged",
                                }
                            ]
                        }
                    ]
                }
            },
            "errors": None,
        },
        why="A zone's security events from the GraphQL Analytics API: GraphQL's own data and "
        "errors, not the REST envelope. Only the fields the query names arrive, and it names no "
        "visitor's address or user agent.",
        kind=Kind.READ,
        tools=("cloudflare.read_security_events",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference="https://developers.cloudflare.com/analytics/graphql-api/tutorials/"
        "querying-firewall-events/",
    ),
    Cassette(
        cid="CF-200-graphql-errors",
        source=SOURCE,
        request="POST /client/v4/graphql",
        status=200,
        body={
            "data": None,
            "errors": [
                {
                    "message": "cannot request data older than 2678400s",
                    "path": ["viewer", "zones", "0", "firewallEventsAdaptive"],
                    "extensions": {"code": "authz"},
                }
            ],
        },
        why="GraphQL refuses inside a 200. A window the zone's plan does not keep, or a token "
        "without Analytics Read, is a refusal and never an empty list of events.",
        kind=Kind.ERROR,
        tools=("cloudflare.read_security_events",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference="https://developers.cloudflare.com/analytics/graphql-api/errors/",
    ),
    Cassette(
        cid="CF-429",
        source=SOURCE,
        request="GET /client/v4/zones?page=1&per_page=50",
        status=429,
        headers={
            "Retry-After": "300",
            "Ratelimit": '"default";r=0;t=300',
            "Ratelimit-Policy": '"default";q=1200;w=300',
        },
        body={
            "success": False,
            "errors": [{"code": 10000, "message": "Rate limited. Please wait and consider"}],
            "messages": [],
            "result": None,
        },
        why="Past 1,200 calls in five minutes every call is refused for five minutes. The wait is "
        "in Retry-After, in seconds, and the Ratelimit header says nothing is left.",
        kind=Kind.RATE_LIMIT,
        tools=("cloudflare.list_zones",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference="https://developers.cloudflare.com/fundamentals/api/reference/limits/",
    ),
    Cassette(
        cid="CF-403",
        source=SOURCE,
        request=f"GET /client/v4/zones/{ZONE}/dns_records?page=1&per_page=100",
        status=403,
        body={
            "success": False,
            "errors": [{"code": 10000, "message": "Authentication error"}],
            "messages": [],
            "result": None,
        },
        why="A token without DNS Read, or revoked: refused, which is our credential rather than "
        "the zone having no records.",
        kind=Kind.ERROR,
        tools=("cloudflare.list_dns_records",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference="https://developers.cloudflare.com/fundamentals/api/troubleshooting/",
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    1_200,
    "requests per five minutes per user",
    "Across every token and the dashboard, so another integration the client runs spends the same "
    "allowance. Past it every call is refused for five minutes.",
    False,
)


def _operation(recorded: Cassette) -> Any:
    if "/dns_records/" in recorded.request:
        return cloudflare.dns_record_operation()
    if "/dns_records" in recorded.request:
        return cloudflare.dns_records_operation()
    if recorded.request.rstrip("/").endswith(ZONE):
        return cloudflare.zone_operation()
    return cloudflare.zones_operation()


def replay(recorded: Cassette) -> Replayed:
    """A recording through the connector's own reading: its interpretation, the index entry it keeps
    under the zone it was read under, and its paging; a GraphQL one through `security_events`."""
    if "/graphql" in recorded.request:
        events = cloudflare.security_events(recorded.status, recorded.body, fetched_at=FETCHED_AT)
        return _outcome(events.call, events.rows)
    operation = _operation(recorded)
    reading = cloudflare.CloudflareReading()
    reply = reading.interpret(
        operation, status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
    )
    outcome = _outcome(reply.call, reply.rows)
    if reply.rows is None or not recorded.projects:
        return outcome
    entity = recorded.projects
    under = reading.listed_under(entity)
    rows = reply.rows if under is None else under.named(reply.rows, ZONE)
    kept = tuple(
        one
        for one in (
            reading.projected(entity, row.model_dump(), seen_at=SEEN_AT) for row in rows.records
        )
        if one is not None
    )
    if outcome.outcome is not Expect.ANSWERED:
        return Replayed(outcome.outcome, kept)
    first = reading.first_page(entity)
    following = reading.next_page(entity, first, recorded.body, len(rows.records))
    return Replayed(Expect.MORE_TO_READ if following else Expect.ANSWERED, kept)


def _outcome(call: CallOutcome, rows: Any) -> Replayed:
    if call is CallOutcome.REJECTED:
        return Replayed(Expect.REFUSED)
    if call is not CallOutcome.OK:
        return Replayed(unreachable_or_quota(call))
    return Replayed(Expect.ANSWERED if rows.records else Expect.ABSENT)


def manifest() -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen builds, which is what ships."""
    from tests.unit import test_cloudflare

    built: ConnectorManifest = test_cloudflare.a_console_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
