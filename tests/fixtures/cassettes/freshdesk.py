"""Freshdesk's recordings: a search at its 300 ceiling, a full page, a ticket, a contact, failures.

A ticket's note carries a canary: the note is read live and never kept.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from typing import Any, Final

from brain.connectors import freshdesk
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.projection import ProjectedRecord
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    SEEN_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "freshdesk"

FRESHDESK_DOC = "https://developers.freshdesk.com/api/"


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


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="FRESH-200-search",
        source=SOURCE,
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
    Cassette(
        cid="FRESH-429",
        source=SOURCE,
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
        cid="FRESH-200-search-full-page",
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    300,
    "records per search, ever",
    "Not a page size. The search API will not return a 301st record however you "
    "page, so any connector that assumes it can enumerate is wrong.",
    False,
)


def _freshdesk_endpoint(recorded: Cassette) -> freshdesk.Endpoint:
    if "/search/" in recorded.request:
        return freshdesk.Endpoint.SEARCH_TICKETS
    if "/contacts/" in recorded.request:
        return freshdesk.Endpoint.GET_CONTACT
    if "/tickets/" in recorded.request:
        return freshdesk.Endpoint.GET_TICKET
    return freshdesk.Endpoint.LIST_TICKETS


def replay(recorded: Cassette) -> Replayed:
    """A recording through `freshdesk.assert_answered`, its operation and its paging."""
    from tests.unit.test_freshdesk import DOMAIN

    endpoint = _freshdesk_endpoint(recorded)
    reply = freshdesk.Reply(status=recorded.status, headers=recorded.headers, body=recorded.body)
    try:
        freshdesk.assert_answered(reply)
    except freshdesk.FreshdeskRefusedError:
        return Replayed(Expect.REFUSED)
    except freshdesk.FreshdeskUnreachableError as failed:
        return Replayed(unreachable_or_quota(failed.call_outcome))
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


def manifest() -> ConnectorManifest:
    from tests.unit import test_freshdesk

    built: ConnectorManifest = test_freshdesk.a_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
