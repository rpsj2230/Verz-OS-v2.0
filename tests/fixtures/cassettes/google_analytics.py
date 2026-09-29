"""Google Analytics' recordings: the property, a report of four ranges, the token, and failures.

The property's industry carries the canary: the Admin API sends it and the index keeps nothing of
it. The report's figures are never kept by anything, so they need no marker; the install check
plants its own canary as a figure and looks for it in every table.

Task ids: M11.7.1
"""

from __future__ import annotations

import json
from typing import Final

from brain.connectors import google_analytics, google_token
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

SOURCE: Final = "google_analytics"

ADMIN_GET_DOC = (
    "https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1beta/properties/get"
)
RUN_REPORT_DOC = (
    "https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/"
    "runReport"
)
QUOTAS_DOC = "https://developers.google.com/analytics/devguides/reporting/data/v1/quotas"
ERRORS_DOC = "https://cloud.google.com/apis/design/errors"
TOKEN_DOC = "https://developers.google.com/identity/protocols/oauth2/service-account"

#: The made-up property every recording is of. The replay reads it as the connected one.
PROPERTY: Final = "123456789"


def _report_row(named: str, sessions: str, users: str, conversions: str) -> dict[str, object]:
    return {
        "dimensionValues": [{"value": named}],
        "metricValues": [{"value": sessions}, {"value": users}, {"value": conversions}],
    }


def _error(code: int, status: str, message: str) -> dict[str, object]:
    """Google's error envelope, as its API design guide documents it."""
    return {"error": {"code": code, "message": message, "status": status}}


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="GA-200-property",
        source=SOURCE,
        request=f"GET /v1beta/properties/{PROPERTY}",
        status=200,
        body={
            "name": f"properties/{PROPERTY}",
            "propertyType": "PROPERTY_TYPE_ORDINARY",
            "createTime": "2019-03-01T10:00:00.000Z",
            "updateTime": "2019-03-02T10:00:00.000Z",
            "parent": "accounts/100200300",
            "displayName": "Example Store",
            "industryCategory": "CANARY-INDUSTRY",
            "timeZone": "Etc/UTC",
            "currencyCode": "USD",
            "serviceLevel": "GOOGLE_ANALYTICS_STANDARD",
            "account": "accounts/100200300",
        },
        why="The one property a connection reads: its id, name and dates are kept, and the "
        "industry, time zone and currency arrive and nothing maps them.",
        kind=Kind.READ,
        tools=("google_analytics.read_property",),
        projects=google_analytics.ENTITY_PROPERTY,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=ADMIN_GET_DOC,
    ),
    Cassette(
        cid="GA-200-report",
        source=SOURCE,
        request=f"POST /v1beta/properties/{PROPERTY}:runReport",
        status=200,
        body={
            "dimensionHeaders": [{"name": "dateRange"}],
            "metricHeaders": [
                {"name": "sessions", "type": "TYPE_INTEGER"},
                {"name": "totalUsers", "type": "TYPE_INTEGER"},
                {"name": "keyEvents", "type": "TYPE_FLOAT"},
            ],
            "rows": [
                _report_row("yesterday", "41", "37", "2"),
                _report_row("last_7_days", "310", "254", "11"),
                _report_row("last_28_days", "1204", "951", "38"),
                _report_row("last_90_days", "3870", "2990", "117"),
            ],
            "rowCount": 4,
            "metadata": {"currencyCode": "USD", "timeZone": "Etc/UTC"},
            "kind": "analyticsData#runReport",
        },
        why="Four date ranges in one report: Google adds a dateRange dimension valued by each "
        "range's name, and the metrics come back as strings in the order they were asked for.",
        kind=Kind.READ,
        tools=("google_analytics.read_traffic",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=RUN_REPORT_DOC,
    ),
    Cassette(
        cid="GA-200-token",
        source=SOURCE,
        request="POST /token",
        status=200,
        body={"access_token": "ya29.recorded-shape", "expires_in": 3599, "token_type": "Bearer"},
        why="The token a signed assertion is exchanged for: a bearer token for an hour, used for "
        "one read and dropped.",
        kind=Kind.READ,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=TOKEN_DOC,
    ),
    Cassette(
        cid="GA-400-token",
        source=SOURCE,
        request="POST /token",
        status=400,
        body={"error": "invalid_grant", "error_description": "Invalid JWT Signature."},
        why="A key that was deleted or never belonged to the account: Google declines the "
        "assertion, which is a refusal of our key and never an empty property.",
        kind=Kind.ERROR,
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=TOKEN_DOC,
    ),
    Cassette(
        cid="GA-401",
        source=SOURCE,
        request=f"POST /v1beta/properties/{PROPERTY}:runReport",
        status=401,
        body=_error(
            401,
            "UNAUTHENTICATED",
            "Request had invalid authentication credentials. Expected OAuth 2 access token, "
            "login cookie or other valid authentication credential.",
        ),
        why="A token that expired or was revoked: a refusal, never a quiet property.",
        kind=Kind.ERROR,
        tools=("google_analytics.read_traffic",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
    Cassette(
        cid="GA-403-property",
        source=SOURCE,
        request=f"GET /v1beta/properties/{PROPERTY}",
        status=403,
        body=_error(
            403,
            "PERMISSION_DENIED",
            "User does not have sufficient permissions for this property.",
        ),
        why="The account was never added to the property, or was taken off it: Google refuses "
        "rather than answering empty, so this is the refusal and not an absence.",
        kind=Kind.ERROR,
        tools=("google_analytics.read_property",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
    Cassette(
        cid="GA-429-report",
        source=SOURCE,
        request=f"POST /v1beta/properties/{PROPERTY}:runReport",
        status=429,
        body=_error(
            429,
            "RESOURCE_EXHAUSTED",
            "Exhausted property tokens per hour for a project per property.",
        ),
        why="The property's hourly tokens are spent. Google states no wait, so the connector "
        "waits its own long end rather than anything the source said.",
        kind=Kind.RATE_LIMIT,
        tools=("google_analytics.read_traffic",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=QUOTAS_DOC,
    ),
    Cassette(
        cid="GA-500-report",
        source=SOURCE,
        request=f"POST /v1beta/properties/{PROPERTY}:runReport",
        status=500,
        body=_error(500, "INTERNAL", "Internal error encountered."),
        why="Google's own failure: unreachable, and the answer says so rather than guessing.",
        kind=Kind.ERROR,
        tools=("google_analytics.read_traffic",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    20,
    "minute",
    "14,000 tokens an hour per Cloud project per standard property and 200,000 a day, about ten "
    "a report; `brain.ops.limits` records the same figure. Raised by the property's own plan.",
    True,
)


def replay(recorded: Cassette) -> Replayed:
    """A recording through the connector's own reading, report or token exchange."""
    if recorded.request == "POST /token":
        try:
            google_token.token_from(
                status=recorded.status,
                body=json.dumps(recorded.body).encode("utf-8"),
            )
        except google_token.TokenNotIssuedError as refused:
            if refused.call is CallOutcome.REJECTED:
                return Replayed(Expect.REFUSED)
            return Replayed(unreachable_or_quota(refused.call))
        return Replayed(Expect.ANSWERED)
    settings = {"property": PROPERTY, "department": "marketing"}
    if recorded.request.endswith(":runReport"):
        reply = google_analytics.AnalyticsReport().interpret(
            google_analytics.ENTITY_PROPERTY,
            PROPERTY,
            status=recorded.status,
            body=recorded.body,
            fetched_at=FETCHED_AT,
        )
    else:
        reading = google_analytics.AnalyticsReading()
        operation = reading.operation(
            google_analytics.ENTITY_PROPERTY, settings=settings, resolver=_NoResolver()
        )
        reply = reading.interpret(
            operation, status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
        )
    if reply.call is CallOutcome.REJECTED:
        return Replayed(Expect.REFUSED)
    if reply.call is not CallOutcome.OK:
        return Replayed(unreachable_or_quota(reply.call))
    assert reply.rows is not None
    rows = [one.model_dump() for one in reply.rows.records]
    if not rows:
        return Replayed(Expect.ABSENT)
    if recorded.request.endswith(":runReport"):
        # A report's figures are read for a question and kept by nothing, so nothing is kept here.
        return Replayed(Expect.ANSWERED)
    kept = tuple(
        one
        for one in (
            google_analytics.AnalyticsReading().projected(
                google_analytics.ENTITY_PROPERTY, row, seen_at=SEEN_AT
            )
            for row in rows
        )
        if one is not None
    )
    return Replayed(Expect.ANSWERED, kept)


class _NoResolver:
    """The reading resolves nothing when it builds an operation; this is never asked."""

    def resolve(self, host: str) -> list[str]:
        raise AssertionError(f"the reading resolved {host} while building an operation")


def manifest() -> ConnectorManifest:
    from tests.unit import test_google_analytics

    built: ConnectorManifest = test_google_analytics.a_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
    not_recordable={
        Kind.PAGINATION: (
            "one property is one object and a report of four ranges with no other dimension is "
            "four rows, so neither ever pages"
        ),
    },
)
