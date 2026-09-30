"""The domains connector's recordings: a registry's RDAP record for one domain, and its failures.

Written to the shape RFC 9083 documents for a domain lookup and RFC 7480 for its errors. The
registrar's name is live-only, so the recorded one is a name nothing may keep.

Task ids: M11.7.4
"""

from __future__ import annotations

from typing import Final

from brain.connectors import domains
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import CallOutcome, classify
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

SOURCE: Final = "domains"

RDAP_RESPONSE_DOC = "https://www.rfc-editor.org/rfc/rfc9083"
RDAP_ERRORS_DOC = "https://www.rfc-editor.org/rfc/rfc7480#section-5"

#: The recorded domain and the registrar its record names. Reserved names, nobody's.
DOMAIN: Final = "example.com"
REGISTRAR: Final = "Recorded Registrar For Acceptance"

#: The registry record for `DOMAIN`, as a registry publishes it.
RECORD: Final = {
    "objectClassName": "domain",
    "ldhName": "EXAMPLE.COM",
    "status": ["client transfer prohibited"],
    "events": [
        {"eventAction": "registration", "eventDate": "2019-03-01T00:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2999-03-01T00:00:00Z"},
        {"eventAction": "last changed", "eventDate": "2019-03-02T00:00:00Z"},
    ],
    "entities": [
        {
            "objectClassName": "entity",
            "roles": ["registrar"],
            "vcardArray": [
                "vcard",
                [["version", {}, "text", "4.0"], ["fn", {}, "text", REGISTRAR]],
            ],
        },
        # The registrant: a person or a company, published by some registries and never read
        # here. A canary, so a kept row holding it would be caught.
        {
            "objectClassName": "entity",
            "roles": ["registrant"],
            "vcardArray": [
                "vcard",
                [["version", {}, "text", "4.0"], ["fn", {}, "text", "CANARY-DOMAINS-REGISTRANT"]],
            ],
        },
    ],
    "nameservers": [
        {"objectClassName": "nameserver", "ldhName": "NS1.EXAMPLE.NET"},
        {"objectClassName": "nameserver", "ldhName": "NS2.EXAMPLE.NET"},
    ],
}

CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="DOMAINS-200-domain",
        source=SOURCE,
        request="GET /domain/example.com",
        status=200,
        body=RECORD,
        why="One domain's registry record: its expiry as an event, its registrar as an entity "
        "with a vCard, its statuses and its name servers, none of them at a fixed position.",
        kind=Kind.READ,
        tools=("domains.read_domain",),
        projects="domain",
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=RDAP_RESPONSE_DOC,
    ),
    Cassette(
        cid="DOMAINS-404",
        source=SOURCE,
        request="GET /domain/example.com",
        status=404,
        body={"errorCode": 404, "title": "Not Found"},
        why="The registry holds no such domain. A refusal of this lookup, never an empty "
        "answer, so a deleted domain is not read as a domain with no expiry.",
        kind=Kind.ERROR,
        tools=("domains.read_domain",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=RDAP_ERRORS_DOC,
    ),
    Cassette(
        cid="DOMAINS-429",
        source=SOURCE,
        request="GET /domain/example.com",
        status=429,
        headers={"Retry-After": "10"},
        body={"errorCode": 429, "title": "Too Many Requests"},
        why="A registry limiting this install, as RFC 7480 lets each one do with its own figure.",
        kind=Kind.RATE_LIMIT,
        tools=("domains.read_domain",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=RDAP_ERRORS_DOC,
    ),
    Cassette(
        cid="DOMAINS-503",
        source=SOURCE,
        request="GET /domain/example.com",
        status=503,
        body=None,
        why="The registry's server did not answer, which is the source unwell and not an absence.",
        kind=Kind.ERROR,
        tools=("domains.read_domain",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=RDAP_ERRORS_DOC,
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    30,
    "minute",
    "No registry figure is shared: RFC 7480 lets each registry limit as it chooses. Thirty a "
    "minute is this product's own pace, recorded in brain.ops.limits beside it.",
    False,
)


def replay(recorded: Cassette) -> Replayed:
    """A recording through the reading's own interpretation and index entry."""
    call = classify(status=recorded.status)
    if call is CallOutcome.REJECTED:
        return Replayed(Expect.REFUSED)
    if call is not CallOutcome.OK:
        return Replayed(unreachable_or_quota(call))
    reading = domains.DomainsReading()
    reply = reading.interpret(
        domains.operation_at("https://rdap.example"),
        status=recorded.status,
        body=recorded.body,
        fetched_at=FETCHED_AT,
    )
    if reply.rows is None or not reply.rows.records:
        return Replayed(Expect.ABSENT)
    kept = tuple(
        one
        for one in (
            reading.projected(domains.DOMAIN, row.model_dump(), seen_at=SEEN_AT)
            for row in reply.rows.records
        )
        if one is not None
    )
    return Replayed(Expect.ANSWERED, kept=kept if recorded.projects else ())


def manifest() -> ConnectorManifest:
    """The manifest a connection of the recorded domain declares."""
    from brain.ops.connectable import key_reference

    return domains.manifest(
        domains.DomainsConnection(domains=(DOMAIN,), department="operations"),
        ref=key_reference(SOURCE),
    )


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
)
