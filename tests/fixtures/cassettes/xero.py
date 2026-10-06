"""Xero's recordings: invoices, contacts, a full page, the daily ceiling and an expired token.

Every one is a documented shape (`tests.fixtures.cassettes`), and the invoice's amount carries a
canary, because the amount is the value a question asks for and the one value never kept.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from brain.connectors import xero
from brain.connectors.manifest import ConnectorManifest
from brain.ops.idempotency import Verification
from tests.fixtures.cassettes._read_back import READ_AT, PublicResolver, answered
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

SOURCE: Final = "xero"

XERO_INVOICES_DOC = "https://developer.xero.com/documentation/api/accounting/invoices"
XERO_CONTACTS_DOC = "https://developer.xero.com/documentation/api/accounting/contacts"
XERO_LIMITS_DOC = "https://developer.xero.com/documentation/guides/oauth2/limits/"
XERO_ERRORS_DOC = "https://developer.xero.com/documentation/api/accounting/responsecodes"


def _xero_invoice(number: int) -> dict[str, Any]:
    return {
        "InvoiceID": f"b1f2-{number:04d}",
        "InvoiceNumber": f"INV-{2000 + number}",
        "Contact": {"ContactID": "c-0447", "Name": "SNM Construction Pte Ltd"},
        "AmountDue": "CANARY-INVOICE-Z9KRT",
        "DueDate": "/Date(1794700800000+0000)/",
        "Status": "AUTHORISED",
    }


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="XERO-200-invoices",
        source=SOURCE,
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
        cid="XERO-429",
        source=SOURCE,
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
        source=SOURCE,
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
        cid="XERO-200-contacts",
        source=SOURCE,
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
        source=SOURCE,
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
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    5_000,
    "day per tenant",
    "Also 60/minute. Resets 00:00 NZT. Not raisable, and this file said it was until "
    "2026-09-06: the ceiling sits on the client's tenant and is shared with every other "
    "integration they run, so no plan we can buy moves it and the only lever is asking "
    "for less. `brain.ops.limits.source_ceilings()` had the correct value and the argument "
    "for it the whole time; the two records simply disagreed, and the disagreement was "
    "found by a connector being written against both at once.",
    False,
)


def replay(recorded: Cassette) -> Replayed:
    """A recording through `xero.interpret`, `projected_record` and the reading's paging."""
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
        return Replayed(unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [record.model_dump() for record in reply.rows.records]
    kept = [xero.projected_record(entity, row, last_seen_at=SEEN_AT) for row in rows]
    projected = tuple(one for one in kept if one is not None) if recorded.projects else ()
    if not rows:
        return Replayed(Expect.ABSENT)
    following = xero.XeroReading().next_page(entity, {"page": "1"}, recorded.body, len(rows))
    return Replayed(Expect.MORE_TO_READ if following else Expect.ANSWERED, projected)


def manifest() -> ConnectorManifest:
    from tests.unit import test_xero

    built: ConnectorManifest = test_xero.manifest()
    return built


def read_back_answer(recorded: Cassette) -> Verification:
    """One recording through Xero's read-back reading, as the operation its request line names."""
    entity = xero.ENTITY_CONTACT if "/Contacts" in recorded.request else xero.ENTITY_INVOICE
    operation = xero.operation_for(entity, resolver=PublicResolver())
    reply = xero.interpret(
        operation, status=recorded.status, body=recorded.body, fetched_at=READ_AT
    )
    return answered(SOURCE, reply)


#: How each recording this connector's read-back names is answered. Written here rather than
#: read from the connector, so the expectation and the reading are two accounts that have to
#: agree (`tests/unit/test_write_verification.py`).
READ_BACK: Final[Mapping[str, Verification]] = MappingProxyType(
    {
        "XERO-200-invoices": Verification.FOUND,
        "XERO-429": Verification.INCONCLUSIVE,
        "XERO-401-expired": Verification.INCONCLUSIVE,
        "XERO-200-contacts": Verification.FOUND,
        "XERO-200-invoices-full-page": Verification.FOUND,
    }
)


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    read_back=READ_BACK,
    read_back_answer=read_back_answer,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
