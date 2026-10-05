"""HubSpot's recordings: companies, contacts, deals, associations, an empty search and failures.

The deal's amount carries a canary; the contact's email and phone arrive and nothing maps them.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

import re
from typing import Final

from brain.connectors import hubspot
from brain.connectors.manifest import ConnectorManifest
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

SOURCE: Final = "hubspot"

HUBSPOT_OBJECTS_DOC = "https://developers.hubspot.com/docs/api/crm/companies"
HUBSPOT_ASSOCIATIONS_DOC = "https://developers.hubspot.com/docs/api/crm/associations"
HUBSPOT_LIMITS_DOC = (
    "https://developers.hubspot.com/docs/developer-tooling/platform/usage-guidelines"
)
HUBSPOT_ERRORS_DOC = "https://developers.hubspot.com/docs/api/error-handling"


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="HUBSPOT-200-empty",
        source=SOURCE,
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
    Cassette(
        cid="HUBSPOT-200-companies-page",
        source=SOURCE,
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
        projects=hubspot.ENTITY_CLIENT,
        expect=Expect.MORE_TO_READ,
        origin=DOCUMENTED,
        reference=HUBSPOT_OBJECTS_DOC,
    ),
    Cassette(
        cid="HUBSPOT-200-contacts",
        source=SOURCE,
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
        projects=hubspot.ENTITY_CONTACT,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference="https://developers.hubspot.com/docs/api/crm/contacts",
    ),
    Cassette(
        cid="HUBSPOT-200-deals",
        source=SOURCE,
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
        projects=hubspot.ENTITY_DEAL,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference="https://developers.hubspot.com/docs/api/crm/deals",
    ),
    Cassette(
        cid="HUBSPOT-200-deal",
        source=SOURCE,
        request=(
            "GET /crm/v3/objects/deals/4471?properties=amount,closedate,dealname,dealstage,"
            "hubspot_owner_id,pipeline"
        ),
        status=200,
        body={
            "id": "4471",
            "properties": {
                "dealname": "SNM website revamp",
                "amount": "CANARY-CONTRACT-LIVE-9RT2M",
                "dealstage": "contractsent",
                "pipeline": "default",
                "closedate": "2026-10-01T00:00:00.000Z",
                "hubspot_owner_id": "9911",
            },
            "createdAt": "2026-06-01T08:00:00.000Z",
            "updatedAt": "2026-09-05T10:00:00.000Z",
            "archived": False,
        },
        why="One deal by its id, the object itself with no results envelope: what a question "
        "reads live, so its amount is told while the asker waits and never kept. The list cannot "
        "be narrowed to one id, so this is the call that holds the record.",
        kind=Kind.READ,
        tools=("hubspot.read_deals",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference="https://developers.hubspot.com/docs/api/crm/deals",
    ),
    Cassette(
        cid="HUBSPOT-200-associations",
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    100,
    "calls per 10 seconds per private app, on the Free and Starter tiers",
    "250,000 a day per account on those tiers; Professional and Enterprise allow 190 per 10 "
    "seconds, and the API Limit Increase add-on raises both. Read from the usage guidelines on "
    "2026-09-30; the 10,000 a day this recorded before was not the documented figure.",
    True,
)


#: A request for one record by its id, as a question's live read makes it.
ONE_RECORD: Final = re.compile(r"/crm/v3/objects/(companies|contacts|deals)/[0-9]+(\?|$)")


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


def replay(recorded: Cassette) -> Replayed:
    """A recording through `hubspot.interpret`, `projected_record` and the reading's cursor."""
    from tests.unit.test_hubspot import Resolver

    entity = _hubspot_entity(recorded)
    one = ONE_RECORD.search(recorded.request)
    operation = (
        hubspot.one_record_operation(entity, resolver=Resolver())
        if one
        else hubspot.operation_for(entity, resolver=Resolver())
    )
    reply = hubspot.interpret(
        operation, status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
    )
    if reply.outcome is hubspot.HubSpotOutcome.REFUSED:
        return Replayed(Expect.REFUSED)
    if reply.outcome is hubspot.HubSpotOutcome.UNREACHABLE:
        return Replayed(unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [record.model_dump() for record in reply.rows.records]
    if not rows:
        return Replayed(Expect.ABSENT)
    if entity == hubspot.ENTITY_ASSOCIATION:
        edges = hubspot.association_edges(
            from_entity=hubspot.ENTITY_CLIENT,
            from_id="88",
            to_entity=hubspot.ENTITY_CONTACT,
            rows=tuple(rows),
        )
        return Replayed(Expect.ANSWERED if edges else Expect.ABSENT)
    kept = [hubspot.projected_record(entity, row, last_seen_at=SEEN_AT) for row in rows]
    projected = tuple(one for one in kept if one is not None)
    following = hubspot.HubSpotReading().next_page(entity, {}, recorded.body, len(rows))
    return Replayed(Expect.MORE_TO_READ if following else Expect.ANSWERED, projected)


def manifest() -> ConnectorManifest:
    from tests.unit import test_hubspot

    built: ConnectorManifest = test_hubspot.manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
