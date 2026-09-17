"""Recorded connector responses, so connectors can be built before credentials exist.

This is what makes the thirty-day plan possible. Every connector is written and tested
against these, and wired to real credentials at go-live - otherwise the whole build waits
on someone finding a Xero API key.

A cassette is not a convenience mock. It records three things a hand-written mock always
gets wrong, and each has caused a real outage somewhere:

**The failure responses, not just the happy one.** Xero returns 429 with a Retry-After
header, and the correct behaviour is to say "I could not reach Xero" rather than answer
from memory. A mock that only knows success produces a connector that has never once been
compiled against failure.

**The real limits, verified rather than assumed.** Freshdesk search returns at most 300
records *ever* - not per page, not per request, but as a hard ceiling on the result set.
A connector written against a mock that pages forever will silently under-report and look
correct doing it.

**The pagination shape.** Every one of these APIs pages differently, and the difference is
where "we only ever saw the first 100 clients" comes from.

**Not one of these was captured from a live account, and each says so.** `Origin` is a
required field rather than a comment: every cassette here is `DOCUMENTED_SHAPE`, written to
the response shape the vendor's own API reference publishes and naming that page in
`reference`. The values inside (a client name, an id, a canary) are invented; the envelope,
the field names, the status and the headers are the documentation's. A `LIVE_CAPTURE` is a
claim that a real account answered this, and it must name when; nothing here makes that
claim, and `tests/unit/test_cassette_replay.py` refuses one that names no capture time.

**Every cassette says what it covers and what replaying it must produce.** `kind`, `tools`,
`projects` and `expect` are what the replay test and the coverage sweep read: a connector
that declares a tool no cassette answers, or a projection no cassette feeds, fails there
rather than being described as tested.

Task ids: M0.6.5, M38.4.1.1
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Source(enum.StrEnum):
    XERO = "xero"
    LARK_BASE = "lark_base"
    FRESHDESK = "freshdesk"
    LARAVEL = "laravel"
    HUBSPOT = "hubspot"
    LARK_WIKI = "lark_wiki"
    GOOGLE_DRIVE = "google_drive"


class Origin(enum.StrEnum):
    """Where a recording's shape came from. Two, and the difference is what a console may say."""

    #: Written to the shape the vendor's published API reference documents. Not a live read.
    DOCUMENTED_SHAPE = "documented_shape"
    #: Captured from a real account's answer. Requires `captured_at`.
    LIVE_CAPTURE = "live_capture"


class Kind(enum.StrEnum):
    """What a recording is an example of, as the coverage sweep counts it."""

    LIST = "list"
    READ = "read"
    PAGINATION = "pagination"
    RATE_LIMIT = "rate_limit"
    ERROR = "error"


class Expect(enum.StrEnum):
    """What the connector's own code must conclude when this recording is replayed through it."""

    ANSWERED = "answered"
    ABSENT = "absent"
    #: Answered, and the source said there is more than this reply holds.
    MORE_TO_READ = "more_to_read"
    RATE_LIMITED = "rate_limited"
    REFUSED = "refused"
    UNREACHABLE = "unreachable"
    #: Drive's 404: absent, or present and not visible to this credential. The source does not say.
    NOT_FOUND = "not_found"


class Protocol(enum.StrEnum):
    """How the exchange travelled. Laravel is read through database views, not over HTTP."""

    HTTP = "http"
    #: `status` is 0, `request` is the statement's shape, and `body` holds `rows` or the
    #: server's documented `errno`, `sqlstate` and `message`.
    DATABASE = "database"


@dataclass(frozen=True)
class RateLimit:
    """Verified against the vendor's documentation, not guessed.

    These numbers are why the architecture federates instead of syncing: a realistic day
    touches 5-20 records per question, and syncing everything would need 15,000-60,000
    Xero calls against a ceiling of 5,000.
    """

    source: Source
    calls: int
    per: str
    note: str
    raisable: bool


RATE_LIMITS: tuple[RateLimit, ...] = (
    RateLimit(
        Source.XERO,
        5_000,
        "day per tenant",
        "Also 60/minute. Resets 00:00 NZT. Not raisable, and this file said it was until "
        "2026-09-06: the ceiling sits on the client's tenant and is shared with every other "
        "integration they run, so no plan we can buy moves it and the only lever is asking "
        "for less. `brain.ops.limits.SOURCE_CEILINGS` had the correct value and the argument "
        "for it the whole time; the two records simply disagreed, and the disagreement was "
        "found by a connector being written against both at once.",
        False,
    ),
    RateLimit(
        Source.LARK_BASE,
        100,
        "minute",
        "Permanently uncapped - Lark does not raise this on request, so it is a design "
        "constraint rather than a starting tier.",
        False,
    ),
    RateLimit(
        Source.FRESHDESK,
        300,
        "records per search, ever",
        "Not a page size. The search API will not return a 301st record however you "
        "page, so any connector that assumes it can enumerate is wrong.",
        False,
    ),
    RateLimit(Source.HUBSPOT, 10_000, "day", "Per app, per account.", True),
    RateLimit(Source.LARAVEL, 0, "no ceiling", "Our own system.", True),
    RateLimit(
        Source.LARK_WIKI,
        100,
        "minute",
        "The same tenant bucket as Lark Base: Lark publishes one frequency limit per tenant, "
        "and `brain.connectors.lark_wiki` runs against Lark Base's ceiling for that reason.",
        False,
    ),
    RateLimit(
        Source.GOOGLE_DRIVE,
        0,
        "not measured",
        "Google publishes per-project and per-user query quotas that a project owner sees "
        "and changes in the Cloud console, so there is no one figure to record here; "
        "`brain.connectors.google_drive.THERE_IS_NO_MEASURED_CEILING_HERE` says the same.",
        True,
    ),
)


@dataclass(frozen=True, kw_only=True)
class Cassette:
    """One recorded exchange, what it is an example of, and where its shape came from."""

    cid: str
    source: Source
    request: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    why: str = ""
    kind: Kind
    #: The declared tool names this exchange answers. Lark Base names its tools after the table,
    #: so its recordings write the table as `{entity}`.
    tools: tuple[str, ...] = ()
    #: The projected entity a successful reply's rows are kept as, or empty.
    projects: str = ""
    expect: Expect
    origin: Origin
    #: The vendor documentation page the shape was written to, or what a capture was taken from.
    reference: str
    #: When a live capture was taken, as ISO 8601. Empty for a documented shape.
    captured_at: str = ""
    protocol: Protocol = Protocol.HTTP


DOCUMENTED = Origin.DOCUMENTED_SHAPE

XERO_INVOICES_DOC = "https://developer.xero.com/documentation/api/accounting/invoices"
XERO_CONTACTS_DOC = "https://developer.xero.com/documentation/api/accounting/contacts"
XERO_LIMITS_DOC = "https://developer.xero.com/documentation/guides/oauth2/limits/"
XERO_ERRORS_DOC = "https://developer.xero.com/documentation/api/accounting/responsecodes"
LARK_BASE_LIST_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/bitable-v1/app-table-record/list"
)
LARK_BASE_GET_DOC = (
    "https://open.larksuite.com/document/server-docs/docs/bitable-v1/app-table-record/get"
)
LARK_RATE_DOC = "https://open.larksuite.com/document/ukTMukTMukTM/uUzN04SN3QjL1cDN"
LARK_WIKI_LIST_DOC = "https://open.larksuite.com/document/server-docs/docs/wiki-v2/space-node/list"
LARK_WIKI_GET_DOC = (
    "https://open.larksuite.com/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/wiki-v2/space/get_node"
)
FRESHDESK_DOC = "https://developers.freshdesk.com/api/"
HUBSPOT_OBJECTS_DOC = "https://developers.hubspot.com/docs/api/crm/companies"
HUBSPOT_ASSOCIATIONS_DOC = "https://developers.hubspot.com/docs/api/crm/associations"
HUBSPOT_LIMITS_DOC = "https://developers.hubspot.com/docs/api/usage-details"
HUBSPOT_ERRORS_DOC = "https://developers.hubspot.com/docs/api/error-handling"
DRIVE_LIST_DOC = "https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list"
DRIVE_GET_DOC = "https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get"
DRIVE_ERRORS_DOC = "https://developers.google.com/workspace/drive/api/guides/handle-errors"
MYSQL_ERRORS_DOC = "https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html"
MYSQL_CLIENT_ERRORS_DOC = (
    "https://dev.mysql.com/doc/mysql-errors/8.0/en/client-error-reference.html"
)
#: Laravel's rows are the view contract this connector declares rather than a vendor's API, so
#: the documented shape of a row is the connector's own column list.
LARAVEL_VIEW_CONTRACT = "brain.connectors.laravel.columns_for"

#: The folder a Drive recording's listing was asked for. The replay pins its connection here.
DRIVE_FOLDER = "fld0447AbC-_x"

#: The space a wiki recording's listing was asked for.
WIKI_SPACE = "6946843325487912356"


def _xero_invoice(number: int) -> dict[str, Any]:
    return {
        "InvoiceID": f"b1f2-{number:04d}",
        "InvoiceNumber": f"INV-{2000 + number}",
        "Contact": {"ContactID": "c-0447", "Name": "SNM Construction Pte Ltd"},
        "AmountDue": "CANARY-INVOICE-Z9KRT",
        "DueDate": "/Date(1794700800000+0000)/",
        "Status": "AUTHORISED",
    }


def _freshdesk_ticket(number: int) -> dict[str, Any]:
    return {
        "id": 88_000 + number,
        "subject": f"SSL renewal {number}",
        "status": 2,
        "priority": 1,
        "company_id": 447,
        "requester_id": 9_001,
        "group_id": 12,
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-05T10:00:00Z",
        "due_by": "2026-09-08T10:00:00Z",
        "custom_fields": {"internal_note": "CANARY-TICKET-B6YHF"},
    }


def _laravel_client(number: int) -> dict[str, Any]:
    return {
        "id": 4_400 + number,
        "name": f"Client {number}",
        "status": "active",
        "department": "maintenance",
        "manager_id": "u_weiling",
        "updated_at": "2026-09-01T10:00:00+00:00",
        "contract_value": "CANARY-CONTRACT-7Q4XZ",
    }


#: Laravel's row cap in the recording below, which is the bound the replay's connection declares.
LARAVEL_RECORDED_CAP = 200

CASSETTES: tuple[Cassette, ...] = (
    # ---- the happy paths ------------------------------------------------
    Cassette(
        cid="XERO-200-invoices",
        source=Source.XERO,
        request='GET /api.xro/2.0/Invoices?where=Contact.Name=="SNM Construction Pte Ltd"',
        status=200,
        headers={"X-DayLimit-Remaining": "4139", "X-MinLimit-Remaining": "58"},
        body={
            "Invoices": [
                {
                    "InvoiceID": "b1f2-0447",
                    "InvoiceNumber": "INV-2291",
                    "Contact": {"ContactID": "c-0447", "Name": "SNM Construction Pte Ltd"},
                    "AmountDue": "CANARY-INVOICE-Z9KRT",
                    "DueDate": "/Date(1794700800000+0000)/",
                    "Status": "AUTHORISED",
                }
            ]
        },
        why="Note the date format. Xero returns .NET epoch strings, not ISO, and a "
        "connector that assumes ISO parses garbage without erroring.",
        kind=Kind.LIST,
        tools=("xero.read_invoices",),
        projects="invoice",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=XERO_INVOICES_DOC,
    ),
    Cassette(
        cid="LARK-200-records",
        source=Source.LARK_BASE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records?page_size=100",
        status=200,
        body={
            "code": 0,
            "data": {
                "has_more": True,
                "page_token": "eyJvZmZzZXQiOjEwMH0",
                "total": 412,
                "items": [
                    {
                        "record_id": "recSNM0447",
                        "fields": {
                            "Client": "SNM Construction Pte Ltd",
                            "Hours Remaining": 12,
                            "Contract Value": "CANARY-CONTRACT-7Q4XZ",
                            "Renewal": 1794700800000,
                        },
                    }
                ],
            },
        },
        why="Lark returns code 0 inside a 200 for success and a non-zero code inside a "
        "200 for failure. A connector checking only the HTTP status treats every error "
        "as a successful empty result.",
        kind=Kind.PAGINATION,
        tools=("lark_base.list_{entity}",),
        projects="{entity}",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARK_BASE_LIST_DOC,
    ),
    Cassette(
        cid="FRESH-200-search",
        source=Source.FRESHDESK,
        request='GET /api/v2/search/tickets?query="company_id:447"',
        status=200,
        headers={
            "X-RateLimit-Total": "3000",
            "X-RateLimit-Remaining": "1841",
            "X-RateLimit-Used-CurrentRequest": "1",
        },
        body={
            "total": 300,
            "results": [
                {
                    "id": 88213,
                    "subject": "SSL renewal",
                    "status": 2,
                    "custom_fields": {"internal_note": "CANARY-TICKET-B6YHF"},
                }
            ],
        },
        why="total is 300 because 300 is the ceiling, not because there are 300. The "
        "true count is unknowable through this endpoint, and an answer that says '300 "
        "tickets' is wrong in a way nobody notices. The rate limit headers are the three "
        "Freshdesk documents on every response; an earlier version of this recording carried "
        "a search count header the documentation does not describe.",
        kind=Kind.LIST,
        tools=("freshdesk.search_tickets",),
        projects="ticket",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=FRESHDESK_DOC + "#filter_tickets",
    ),
    # ---- the failures, which are the point ------------------------------
    Cassette(
        cid="XERO-429",
        source=Source.XERO,
        request="GET /api.xro/2.0/Invoices",
        status=429,
        headers={
            "Retry-After": "1847",
            "X-Rate-Limit-Problem": "day",
            "X-DayLimit-Remaining": "0",
        },
        body={
            "Type": "https://developer.xero.com/documentation/api/errors",
            "Title": "Rate limit exceeded",
        },
        why="The daily ceiling, half an hour before reset. Correct behaviour is DEGRADED "
        "- say the source is unreachable - and never a cached figure presented as "
        "current. X-Rate-Limit-Problem names which limit was hit, as Xero documents.",
        kind=Kind.RATE_LIMIT,
        tools=("xero.read_invoices",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=XERO_LIMITS_DOC,
    ),
    Cassette(
        cid="XERO-401-expired",
        source=Source.XERO,
        request="GET /api.xro/2.0/Invoices",
        status=401,
        body={"Title": "Unauthorized", "Detail": "TokenExpired"},
        why="Distinct from 429 and must not be retried the same way. Retrying an expired "
        "token burns the rate limit and never succeeds.",
        kind=Kind.ERROR,
        tools=("xero.read_invoices",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=XERO_ERRORS_DOC,
    ),
    Cassette(
        cid="LARK-200-code-permission",
        source=Source.LARK_BASE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        status=200,
        body={"code": 91403, "msg": "Forbidden", "data": {}},
        why="HTTP 200 carrying a permission failure. The bot's own token is scoped to "
        "base:record:read; anything wider comes back like this, and a connector reading "
        "only the status code records an empty table as fact.",
        kind=Kind.ERROR,
        tools=("lark_base.list_{entity}",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=LARK_BASE_LIST_DOC,
    ),
    Cassette(
        cid="FRESH-429",
        source=Source.FRESHDESK,
        request="GET /api/v2/tickets",
        status=429,
        headers={"Retry-After": "60"},
        body={"description": "Rate limit exceeded"},
        why="Freshdesk gives Retry-After in seconds; Xero gives it in seconds too but "
        "against a daily window. Same header, very different waits.",
        kind=Kind.RATE_LIMIT,
        tools=("freshdesk.search_tickets",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=FRESHDESK_DOC + "#ratelimit",
    ),
    Cassette(
        cid="LARAVEL-500",
        source=Source.LARAVEL,
        request="GET /internal/clients/4471",
        status=500,
        body={"message": "Server Error"},
        why="Our own system failing. Still DEGRADED, still no substituted value - being "
        "in-house is not a reason to trust an error response. Laravel's default JSON error "
        "body; the connector reads views, and this is how the application's own failure was "
        "recorded rather than something the connector requests.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference="https://laravel.com/docs/errors",
    ),
    Cassette(
        cid="HUBSPOT-200-empty",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/companies/search",
        status=200,
        body={"total": 0, "results": []},
        why="Genuinely absent, as distinct from refused or unreachable. Three different "
        "outcomes that a naive connector collapses into one empty list.",
        kind=Kind.LIST,
        tools=("hubspot.read_companies",),
        expect=Expect.ABSENT,
        origin=DOCUMENTED,
        reference=HUBSPOT_OBJECTS_DOC,
    ),
    # ---- Xero, the rest of what it declares ------------------------------
    Cassette(
        cid="XERO-200-contacts",
        source=Source.XERO,
        request="GET /api.xro/2.0/Contacts?page=1",
        status=200,
        headers={"X-DayLimit-Remaining": "4138", "X-MinLimit-Remaining": "57"},
        body={
            "Contacts": [
                {
                    "ContactID": "c-0447",
                    "Name": "SNM Construction Pte Ltd",
                    "ContactStatus": "ACTIVE",
                    "UpdatedDateUTC": "/Date(1794700800000+0000)/",
                    "TaxNumber": "CANARY-TAX-M3PQ8",
                    "EmailAddress": "accounts@snm.example",
                }
            ]
        },
        why="The contact tool's answer. The email address arrives and is mapped by nothing, "
        "and the tax number arrives and is refused from the projection by name.",
        kind=Kind.LIST,
        tools=("xero.read_contacts",),
        projects="contact",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=XERO_CONTACTS_DOC,
    ),
    Cassette(
        cid="XERO-200-invoices-full-page",
        source=Source.XERO,
        request="GET /api.xro/2.0/Invoices?page=1",
        status=200,
        headers={"X-DayLimit-Remaining": "4137", "X-MinLimit-Remaining": "56"},
        body={"Invoices": [_xero_invoice(n) for n in range(100)]},
        why="Xero documents up to 100 invoices a page when the page parameter is used and "
        "states no total, so a full page is the only sign another exists.",
        kind=Kind.PAGINATION,
        tools=("xero.read_invoices",),
        projects="invoice",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=XERO_INVOICES_DOC,
    ),
    # ---- HubSpot ---------------------------------------------------------
    Cassette(
        cid="HUBSPOT-200-companies-page",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/companies?limit=100&properties=domain,hs_lastmodifieddate",
        status=200,
        body={
            "results": [
                {
                    "id": "88",
                    "properties": {
                        "name": "SNM Construction Pte Ltd",
                        "domain": "snm.example",
                        "lifecyclestage": "customer",
                        "hubspot_owner_id": "9911",
                        "hs_lastmodifieddate": "2026-09-05T10:00:00.000Z",
                        "hs_object_id": "88",
                    },
                    "createdAt": "2026-01-10T08:00:00.000Z",
                    "updatedAt": "2026-09-05T10:00:00.000Z",
                    "archived": False,
                }
            ],
            "paging": {
                "next": {
                    "after": "NTI1Cg%3D%3D",
                    "link": "?after=NTI1Cg%3D%3D",
                }
            },
        },
        why="HubSpot pages by an opaque cursor at paging.next.after and states no total. "
        "The absence of paging.next is the only end signal.",
        kind=Kind.PAGINATION,
        tools=("hubspot.read_companies",),
        projects="client",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=HUBSPOT_OBJECTS_DOC,
    ),
    Cassette(
        cid="HUBSPOT-200-contacts",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/contacts?limit=100",
        status=200,
        body={
            "results": [
                {
                    "id": "301",
                    "properties": {
                        "firstname": "Wei Ling",
                        "lastname": "Tan",
                        "jobtitle": "Operations Manager",
                        "email": "weiling@snm.example",
                        "phone": "+65 6555 0100",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "88",
                        "hubspot_owner_id": "9911",
                        "hs_lastmodifieddate": "2026-09-05T10:00:00.000Z",
                    },
                    "createdAt": "2026-01-10T08:00:00.000Z",
                    "updatedAt": "2026-09-05T10:00:00.000Z",
                    "archived": False,
                }
            ]
        },
        why="A last page: no paging object. The email and phone arrive and nothing maps them.",
        kind=Kind.LIST,
        tools=("hubspot.read_contacts",),
        projects="contact",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference="https://developers.hubspot.com/docs/api/crm/contacts",
    ),
    Cassette(
        cid="HUBSPOT-200-deals",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/deals?limit=100",
        status=200,
        body={
            "results": [
                {
                    "id": "4471",
                    "properties": {
                        "dealname": "SNM website revamp",
                        "amount": "CANARY-CONTRACT-7Q4XZ",
                        "dealstage": "contractsent",
                        "pipeline": "default",
                        "closedate": "2026-10-01T00:00:00.000Z",
                        "hubspot_owner_id": "9911",
                    },
                    "createdAt": "2026-06-01T08:00:00.000Z",
                    "updatedAt": "2026-09-05T10:00:00.000Z",
                    "archived": False,
                }
            ]
        },
        why="The amount is the answer people ask for and is fetched live; the projection "
        "must not carry it.",
        kind=Kind.LIST,
        tools=("hubspot.read_deals",),
        projects="deal",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference="https://developers.hubspot.com/docs/api/crm/deals",
    ),
    Cassette(
        cid="HUBSPOT-200-associations",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/companies/88/associations/contacts",
        status=200,
        body={"results": [{"id": "301", "type": "company_to_contact"}]},
        why="Edges only: the far record's id and the kind of link, and nothing of its content.",
        kind=Kind.READ,
        tools=("hubspot.read_associations",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=HUBSPOT_ASSOCIATIONS_DOC,
    ),
    Cassette(
        cid="HUBSPOT-429",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/companies",
        status=429,
        headers={
            "X-HubSpot-RateLimit-Daily": "10000",
            "X-HubSpot-RateLimit-Daily-Remaining": "0",
        },
        body={
            "status": "error",
            "message": "You have reached your daily limit.",
            "errorType": "RATE_LIMIT",
            "correlationId": "c033cdaa-2c40-4a64-ae48-b4cec88dad24",
            "policyName": "DAILY",
            "requestId": "3d3e35b7-0dae-4b9f-a6e3-9c230cbcf8dd",
        },
        why="HubSpot documents no Retry-After on a 429, so the wait is the connector's own "
        "long end rather than anything the source said.",
        kind=Kind.RATE_LIMIT,
        tools=("hubspot.read_companies",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=HUBSPOT_LIMITS_DOC,
    ),
    Cassette(
        cid="HUBSPOT-401",
        source=Source.HUBSPOT,
        request="GET /crm/v3/objects/deals",
        status=401,
        body={
            "status": "error",
            "message": "Authentication credentials not found.",
            "correlationId": "4f1b9f0e-7a61-4d0c-9d0b-3b8e1f2a6c55",
            "category": "INVALID_AUTHENTICATION",
        },
        why="A private app token revoked or never granted: a refusal, never an empty CRM.",
        kind=Kind.ERROR,
        tools=("hubspot.read_deals",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=HUBSPOT_ERRORS_DOC,
    ),
    # ---- Freshdesk -------------------------------------------------------
    Cassette(
        cid="FRESH-200-search-full-page",
        source=Source.FRESHDESK,
        request='GET /api/v2/search/tickets?query="group_id:12"&page=1',
        status=200,
        headers={"X-RateLimit-Total": "3000", "X-RateLimit-Remaining": "1840"},
        body={"total": 45, "results": [_freshdesk_ticket(n) for n in range(30)]},
        why="Search pages are thirty and fixed. A full page is the only sign of another, "
        "and total is never the end signal.",
        kind=Kind.PAGINATION,
        tools=("freshdesk.search_tickets",),
        projects="ticket",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=FRESHDESK_DOC + "#filter_tickets",
    ),
    Cassette(
        cid="FRESH-200-ticket",
        source=Source.FRESHDESK,
        request="GET /api/v2/tickets/88213",
        status=200,
        headers={"X-RateLimit-Total": "3000", "X-RateLimit-Remaining": "1839"},
        body={
            **_freshdesk_ticket(213),
            "requester_email": "someone@snm.example",
            "description": "<div>Certificate expires Friday.</div>",
            "description_text": "Certificate expires Friday.",
            "type": "Incident",
            "source": 2,
            "fr_escalated": False,
            "spam": False,
            "tags": [],
        },
        why="One ticket by id: the object itself, no envelope. The body and address arrive "
        "and are refused from the projection by different rules.",
        kind=Kind.READ,
        tools=("freshdesk.read_ticket",),
        projects="ticket",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=FRESHDESK_DOC + "#view_a_ticket",
    ),
    Cassette(
        cid="FRESH-200-contact",
        source=Source.FRESHDESK,
        request="GET /api/v2/contacts/9001",
        status=200,
        body={
            "id": 9001,
            "name": "Wei Ling Tan",
            "email": "weiling@snm.example",
            "phone": "+65 6555 0100",
            "company_id": 447,
            "active": True,
            "created_at": "2026-01-10T08:00:00Z",
            "updated_at": "2026-09-05T10:00:00Z",
        },
        why="Read live for the question that needs it and never stored.",
        kind=Kind.READ,
        tools=("freshdesk.read_contact",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=FRESHDESK_DOC + "#view_contact",
    ),
    Cassette(
        cid="FRESH-401",
        source=Source.FRESHDESK,
        request="GET /api/v2/tickets/88213",
        status=401,
        body={
            "code": "invalid_credentials",
            "message": "You have to be logged in to perform this action.",
        },
        why="A wrong or revoked key. Note the string code: a refusal, not a Lark envelope.",
        kind=Kind.ERROR,
        tools=("freshdesk.read_ticket",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=FRESHDESK_DOC + "#error",
    ),
    # ---- Lark Base -------------------------------------------------------
    Cassette(
        cid="LARK-200-record",
        source=Source.LARK_BASE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records/recSNM0447",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "record": {
                    "id": "recSNM0447",
                    "record_id": "recSNM0447",
                    "fields": {
                        "Client": "SNM Construction Pte Ltd",
                        "Title": "Maintenance 0447",
                        "Status": "Active",
                        "Hours Remaining": 12,
                        "Contract Value": "CANARY-CONTRACT-7Q4XZ",
                        "Renewal": 1794700800000,
                    },
                }
            },
        },
        why="One record under data.record with no has_more: a different envelope from a page.",
        kind=Kind.READ,
        tools=("lark_base.read_{entity}",),
        projects="{entity}",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_BASE_GET_DOC,
    ),
    Cassette(
        cid="LARK-429",
        source=Source.LARK_BASE,
        request="GET /open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        status=429,
        headers={"x-ogw-ratelimit-limit": "100", "x-ogw-ratelimit-reset": "37"},
        body={"code": 99991400, "msg": "request trigger frequency limit"},
        why="Lark documents the wait in x-ogw-ratelimit-reset and not in Retry-After, so a "
        "connector reading only Retry-After falls back to its own figure.",
        kind=Kind.RATE_LIMIT,
        tools=("lark_base.list_{entity}",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=LARK_RATE_DOC,
    ),
    # ---- Lark Wiki -------------------------------------------------------
    Cassette(
        cid="LARK-WIKI-200-node",
        source=Source.LARK_WIKI,
        request="GET /open-apis/wiki/v2/spaces/get_node?token=wikcnKQ1k3pcuo5uSK4t8Vabcef",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "node": {
                    "space_id": WIKI_SPACE,
                    "node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                    "obj_token": "doccnzAaODNqykc8g9hOWabcdef",
                    "obj_type": "docx",
                    "parent_node_token": "",
                    "node_type": "origin",
                    "origin_node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                    "origin_space_id": WIKI_SPACE,
                    "has_child": False,
                    "title": "Maintenance handbook",
                    "obj_create_time": "1642402428",
                    "obj_edit_time": "1642402428",
                    "node_create_time": "1642402428",
                    "creator": "ou_xxxxx",
                    "owner": "ou_xxxxx",
                }
            },
        },
        why="The page's metadata. No body travels on this path, and the creator and owner "
        "ids arrive and are mapped by nothing.",
        kind=Kind.READ,
        tools=("lark_wiki.read_page",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARK_WIKI_GET_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-nodes-page",
        source=Source.LARK_WIKI,
        request=f"GET /open-apis/wiki/v2/spaces/{WIKI_SPACE}/nodes?page_size=50",
        status=200,
        body={
            "code": 0,
            "msg": "success",
            "data": {
                "items": [
                    {
                        "space_id": WIKI_SPACE,
                        "node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                        "obj_token": "doccnzAaODNqykc8g9hOWabcdef",
                        "obj_type": "docx",
                        "parent_node_token": "",
                        "node_type": "origin",
                        "origin_node_token": "wikcnKQ1k3pcuo5uSK4t8Vabcef",
                        "origin_space_id": WIKI_SPACE,
                        "has_child": True,
                        "title": "Maintenance handbook",
                        "obj_create_time": "1642402428",
                        "obj_edit_time": "1642402428",
                        "node_create_time": "1642402428",
                        "creator": "ou_xxxxx",
                        "owner": "ou_xxxxx",
                    }
                ],
                "page_token": "6946843325487906839",
                "has_more": True,
            },
        },
        why="The documented listing, and what it does not carry matters: there is no "
        "has_member_setting on a documented node, so this connector reads every such page "
        "as having undetermined permissions and withholds it. A live capture decides whether "
        "a real tenant ever says otherwise.",
        kind=Kind.PAGINATION,
        tools=("lark_wiki.read_page",),
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARK_WIKI_LIST_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-200-code-permission",
        source=Source.LARK_WIKI,
        request="GET /open-apis/wiki/v2/spaces/get_node?token=wikcnKQ1k3pcuo5uSK4t8Vabcef",
        status=200,
        body={"code": 131006, "msg": "permission denied", "data": {}},
        why="The wiki's own permission code, which is not Lark Base's 91403. It is not in the "
        "connector's table of known codes, so it is read as the refusal an unknown code is.",
        kind=Kind.ERROR,
        tools=("lark_wiki.read_page",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=LARK_WIKI_LIST_DOC,
    ),
    Cassette(
        cid="LARK-WIKI-429",
        source=Source.LARK_WIKI,
        request="GET /open-apis/wiki/v2/spaces/get_node?token=wikcnKQ1k3pcuo5uSK4t8Vabcef",
        status=429,
        headers={"x-ogw-ratelimit-limit": "100", "x-ogw-ratelimit-reset": "12"},
        body={"code": 99991400, "msg": "request trigger frequency limit"},
        why="The tenant's minute, shared with Lark Base.",
        kind=Kind.RATE_LIMIT,
        tools=("lark_wiki.read_page",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=LARK_RATE_DOC,
    ),
    # ---- Google Drive ----------------------------------------------------
    Cassette(
        cid="DRIVE-200-files-page",
        source=Source.GOOGLE_DRIVE,
        request=f"GET /drive/v3/files?q='{DRIVE_FOLDER}' in parents and trashed = false",
        status=200,
        body={
            "nextPageToken": "~!!~AI9FV7Q0x",
            "files": [
                {
                    "id": "1aB2cD3eF4gH5iJ6kL7mN8oP9qR",
                    "name": "SNM proposal.pdf",
                    "mimeType": "application/pdf",
                    "modifiedTime": "2026-09-05T10:00:00.000Z",
                    "headRevisionId": "0B-rev1",
                    "trashed": False,
                    "parents": [DRIVE_FOLDER],
                    "permissions": [{"type": "user"}, {"type": "domain", "domain": "verz.com"}],
                }
            ],
        },
        why="A page with a cursor: Drive states continuation in nextPageToken. The "
        "permissions are sub-selected to type and domain, and the documentation does not say "
        "a user grant carries a domain, so no sharing state can be reduced from this shape.",
        kind=Kind.PAGINATION,
        tools=("google_drive.list_folder",),
        projects="file",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=DRIVE_LIST_DOC,
    ),
    Cassette(
        cid="DRIVE-200-file",
        source=Source.GOOGLE_DRIVE,
        request="GET /drive/v3/files/1aB2cD3eF4gH5iJ6kL7mN8oP9qR?supportsAllDrives=true",
        status=200,
        body={
            "id": "1aB2cD3eF4gH5iJ6kL7mN8oP9qR",
            "name": "SNM proposal.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2026-09-05T10:00:00.000Z",
            "headRevisionId": "0B-rev1",
            "trashed": False,
            "parents": [DRIVE_FOLDER],
        },
        why="One file's metadata. Content never travels on the tool path.",
        kind=Kind.READ,
        tools=("google_drive.read_file",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=DRIVE_GET_DOC,
    ),
    Cassette(
        cid="DRIVE-403-user-rate-limit",
        source=Source.GOOGLE_DRIVE,
        request="GET /drive/v3/files",
        status=403,
        body={
            "error": {
                "errors": [
                    {
                        "domain": "usageLimits",
                        "reason": "userRateLimitExceeded",
                        "message": "User Rate Limit Exceeded",
                    }
                ],
                "code": 403,
                "message": "User Rate Limit Exceeded",
            }
        },
        why="A throttle delivered as a 403. Read by status alone it is a permanent refusal.",
        kind=Kind.RATE_LIMIT,
        tools=("google_drive.list_folder",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=DRIVE_ERRORS_DOC,
    ),
    Cassette(
        cid="DRIVE-429",
        source=Source.GOOGLE_DRIVE,
        request="GET /drive/v3/files",
        status=429,
        body={
            "error": {
                "errors": [
                    {
                        "domain": "usageLimits",
                        "reason": "rateLimitExceeded",
                        "message": "Rate Limit Exceeded",
                    }
                ],
                "code": 429,
                "message": "Rate Limit Exceeded",
            }
        },
        why="Google documents exponential backoff and no Retry-After.",
        kind=Kind.RATE_LIMIT,
        tools=("google_drive.list_folder",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=DRIVE_ERRORS_DOC,
    ),
    Cassette(
        cid="DRIVE-401",
        source=Source.GOOGLE_DRIVE,
        request="GET /drive/v3/files/1aB2cD3eF4gH5iJ6kL7mN8oP9qR",
        status=401,
        body={
            "error": {
                "errors": [
                    {
                        "domain": "global",
                        "reason": "authError",
                        "message": "Invalid Credentials",
                        "locationType": "header",
                        "location": "Authorization",
                    }
                ],
                "code": 401,
                "message": "Invalid Credentials",
            }
        },
        why="The service account's key is wrong or revoked.",
        kind=Kind.ERROR,
        tools=("google_drive.read_file",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=DRIVE_ERRORS_DOC,
    ),
    Cassette(
        cid="DRIVE-404",
        source=Source.GOOGLE_DRIVE,
        request="GET /drive/v3/files/1zZ9yY8xX7wW6vV5uU4tT3sS2rR",
        status=404,
        body={
            "error": {
                "errors": [
                    {
                        "domain": "global",
                        "reason": "notFound",
                        "message": "File not found: 1zZ9yY8xX7wW6vV5uU4tT3sS2rR.",
                    }
                ],
                "code": 404,
                "message": "File not found: 1zZ9yY8xX7wW6vV5uU4tT3sS2rR.",
            }
        },
        why="Absent, or there and not shared with this account. Drive does not say which.",
        kind=Kind.ERROR,
        tools=("google_drive.read_file",),
        expect=Expect.NOT_FOUND,
        origin=DOCUMENTED,
        reference=DRIVE_ERRORS_DOC,
    ),
    # ---- Laravel, through database views ---------------------------------
    Cassette(
        cid="LARAVEL-rows-clients",
        source=Source.LARAVEL,
        request="SELECT id, contract_value, department, manager_id, name, status, updated_at "
        "FROM portal.v_clients LIMIT 200",
        status=0,
        body={"rows": [_laravel_client(71), {**_laravel_client(72), "api_token": "CANARY-TOK"}]},
        why="Two rows, one carrying a column the view contract does not name. It must not "
        "arrive, and the contract value must not be projected.",
        kind=Kind.LIST,
        tools=("laravel.read_clients",),
        projects="client",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARAVEL_VIEW_CONTRACT,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-rows-users",
        source=Source.LARAVEL,
        request="SELECT id, department, display_name, status, updated_at FROM portal.v_users "
        "LIMIT 200",
        status=0,
        body={
            "rows": [
                {
                    "id": 12,
                    "display_name": "Wei Ling",
                    "department": "maintenance",
                    "status": "active",
                    "updated_at": "2026-09-01T10:00:00+00:00",
                }
            ]
        },
        why="A staff record: a name and a department, and nothing that reaches a person.",
        kind=Kind.LIST,
        tools=("laravel.read_users",),
        projects="user",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=LARAVEL_VIEW_CONTRACT,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-rows-at-cap",
        source=Source.LARAVEL,
        # A recorded statement, compared as text and never executed.
        request=(
            "SELECT id, contract_value, department, manager_id, name, status, updated_at "  # noqa: S608
            f"FROM portal.v_clients LIMIT {LARAVEL_RECORDED_CAP}"
        ),
        status=0,
        body={"rows": [_laravel_client(n) for n in range(LARAVEL_RECORDED_CAP)]},
        why="A read that filled its row cap. A database does not page; the cap is ours, and "
        "reaching it is the only sign there were more.",
        kind=Kind.PAGINATION,
        tools=("laravel.read_clients",),
        projects="client",
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=LARAVEL_VIEW_CONTRACT,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-1142",
        source=Source.LARAVEL,
        request="SELECT id, display_name FROM portal.v_users LIMIT 200",
        status=0,
        body={
            "errno": 1142,
            "sqlstate": "42000",
            "message": "SELECT command denied to user 'brain_ro'@'10.0.0.8' for table 'v_users'",
        },
        why="The grant no longer covers the view. A withdrawn contract, never an empty view.",
        kind=Kind.ERROR,
        tools=("laravel.read_users",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=MYSQL_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-1146",
        source=Source.LARAVEL,
        request="SELECT id, name FROM portal.v_clients LIMIT 200",
        status=0,
        body={
            "errno": 1146,
            "sqlstate": "42S02",
            "message": "Table 'portal.v_clients' doesn't exist",
        },
        why="The view was dropped or renamed. Also a withdrawn contract.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=MYSQL_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-3024",
        source=Source.LARAVEL,
        request="SELECT id, name FROM portal.v_clients LIMIT 200",
        status=0,
        body={
            "errno": 3024,
            "sqlstate": "HY000",
            "message": "Query execution was interrupted, maximum statement execution time exceeded",
        },
        why="Our own time bound fired on somebody else's database.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=MYSQL_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
    Cassette(
        cid="LARAVEL-2006",
        source=Source.LARAVEL,
        request="SELECT id, name FROM portal.v_clients LIMIT 200",
        status=0,
        body={"errno": 2006, "sqlstate": "HY000", "message": "MySQL server has gone away"},
        why="The server went away mid-read. A client error number, from the client reference.",
        kind=Kind.ERROR,
        tools=("laravel.read_clients",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=MYSQL_CLIENT_ERRORS_DOC,
        protocol=Protocol.DATABASE,
    ),
)


def for_source(source: Source) -> tuple[Cassette, ...]:
    return tuple(c for c in CASSETTES if c.source is source)


def failures() -> tuple[Cassette, ...]:
    """Everything that is not a plain success, including the 200s that carry errors."""
    return tuple(
        c
        for c in CASSETTES
        if c.status >= 400
        or (isinstance(c.body, dict) and c.body.get("code", 0) not in (0, None))
        or (c.protocol is Protocol.DATABASE and isinstance(c.body, dict) and "errno" in c.body)
    )


def limit_for(source: Source) -> RateLimit:
    return next(r for r in RATE_LIMITS if r.source is source)
