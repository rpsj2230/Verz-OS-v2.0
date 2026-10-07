"""Google Workspace's recordings: one person's mail, calendar and documents read for one question,
the token exchange that renews their access, and the failures Google answers with.

Nothing here is kept by the connector, so nothing projects. A message's snippet, an event's
description and a document's text carry canaries, which `tests/unit/test_google_workspace.py`
and the install check search the tables for. Written to the shapes Google's API references
document; none is a capture of a real account.

Task ids: M11.7.6
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from brain.connectors import google_workspace as gws
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.rest import RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.idempotency import Verification
from tests.fixtures.cassettes._read_back import answered
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "google_workspace"

GMAIL_DOC: Final = "https://developers.google.com/workspace/gmail/api/reference/rest/v1/"
CALENDAR_DOC: Final = (
    "https://developers.google.com/workspace/calendar/api/v3/reference/events/list"
)
DRIVE_DOC: Final = "https://developers.google.com/workspace/drive/api/reference/rest/v3/files/"
OAUTH_DOC: Final = "https://developers.google.com/identity/protocols/oauth2/web-server"
ERRORS_DOC: Final = "https://developers.google.com/workspace/gmail/api/guides/handle-errors"

#: The ids the recordings name, shaped as Google's are and naming nobody.
MESSAGE: Final = "18c2f0a1b2c3d4e5"
EVENT: Final = "evt0123abcdefghij"
DOCUMENT: Final = "1aB2cD3eF4gH5iJ6kL7mN8oP9qRwsdoc"

#: What the recorded mail, event and document hold, each carrying a canary and the word "retainer"
#: a recorded question asks about.
MAIL_SNIPPET: Final = "CANARY-GWS-MAIL-SNIPPET the retainer renewal is agreed at the new rate"
EVENT_TEXT: Final = "CANARY-GWS-EVENT-TEXT retainer review with the client"
DOCUMENT_TEXT: Final = "Minutes.\nCANARY-GWS-DOCUMENT-TEXT The retainer is renewed for a year."

#: The words the recorded searches were made for.
WORDS: Final = ("retainer",)


def _google_error(code: int, reason: str, message: str) -> dict[str, Any]:
    return {
        "error": {
            "errors": [{"domain": "global", "reason": reason, "message": message}],
            "code": code,
            "message": message,
        }
    }


def _query(arguments: Mapping[str, str]) -> str:
    return "&".join(f"{key}={value}" for key, value in arguments.items())


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="GWS-200-messages",
        source=SOURCE,
        request=f"GET /gmail/v1/users/me/messages?{_query(gws.mail_query(WORDS))}",
        status=200,
        body={"messages": [{"id": MESSAGE, "threadId": MESSAGE}], "resultSizeEstimate": 1},
        why="The asker's messages matching the question's words, as ids alone: Gmail answers a "
        "search with nothing else, and each is then read for its headers and snippet.",
        kind=Kind.LIST,
        tools=("google_workspace.find_mail",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=GMAIL_DOC + "users.messages/list",
    ),
    Cassette(
        cid="GWS-200-messages-none",
        source=SOURCE,
        request=f"GET /gmail/v1/users/me/messages?{_query(gws.mail_query(WORDS))}",
        status=200,
        body={"resultSizeEstimate": 0},
        why="A search nothing in the mailbox matches: Gmail leaves the messages array out "
        "entirely, which is an absence and not a refusal.",
        kind=Kind.LIST,
        tools=("google_workspace.find_mail",),
        expect=Expect.ABSENT,
        origin=DOCUMENTED,
        reference=GMAIL_DOC + "users.messages/list",
    ),
    Cassette(
        cid="GWS-200-message",
        source=SOURCE,
        request=f"GET /gmail/v1/users/me/messages/{MESSAGE}?format=metadata",
        status=200,
        body={
            "id": MESSAGE,
            "threadId": MESSAGE,
            "snippet": MAIL_SNIPPET,
            "internalDate": "1600000000000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Retainer renewal"},
                    {"name": "From", "value": "Account Manager <manager@client.example>"},
                    {"name": "Date", "value": "Sun, 13 Sep 2020 12:26:40 +0000"},
                ]
            },
        },
        why="One message as metadata: its headers and Gmail's own snippet, never its body. The "
        "snippet is a canary: it is told to the asker and kept nowhere.",
        kind=Kind.READ,
        tools=("google_workspace.find_mail",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=GMAIL_DOC + "users.messages/get",
    ),
    Cassette(
        cid="GWS-200-events",
        source=SOURCE,
        request=f"GET /calendar/v3/calendars/primary/events?{_query(gws.event_query(WORDS))}",
        status=200,
        body={
            "kind": "calendar#events",
            "items": [
                {
                    "id": EVENT,
                    "summary": "Retainer review",
                    "description": EVENT_TEXT,
                    "location": "Meeting room 2",
                    "start": {"dateTime": "2020-09-14T10:00:00Z"},
                    "end": {"dateTime": "2020-09-14T11:00:00Z"},
                }
            ],
        },
        why="The asker's own calendar's events matching the words, singly, as Calendar answers "
        "a free-text search. The description is a canary.",
        kind=Kind.LIST,
        tools=("google_workspace.find_events",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=CALENDAR_DOC,
    ),
    Cassette(
        cid="GWS-200-files",
        source=SOURCE,
        request=f"GET /drive/v3/files?{_query(gws.document_query(WORDS))}",
        status=200,
        body={
            "files": [
                {
                    "id": DOCUMENT,
                    "name": "Retainer minutes",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2020-09-12T09:00:00.000Z",
                }
            ]
        },
        why="The Google Docs the asker may open whose text holds a word, as Drive's full-text "
        "search answers it for their own token.",
        kind=Kind.LIST,
        tools=("google_workspace.find_documents",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=DRIVE_DOC + "list",
    ),
    Cassette(
        cid="GWS-200-export",
        source=SOURCE,
        request=f"GET /drive/v3/files/{DOCUMENT}/export?mimeType=text/plain",
        status=200,
        body=DOCUMENT_TEXT,
        why="One Google Doc exported as plain text, whose body is the text and not JSON. The "
        "text is a canary.",
        kind=Kind.READ,
        tools=("google_workspace.find_documents",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=DRIVE_DOC + "export",
    ),
    Cassette(
        cid="GWS-token-200",
        source=SOURCE,
        request="POST /token grant_type=refresh_token",
        status=200,
        body={
            "access_token": "ya29.recorded-access",
            "token_type": "Bearer",
            "expires_in": 3599,
            "scope": f"{gws.GMAIL_SCOPE} {gws.CALENDAR_SCOPE}",
        },
        why="A person's access renewed from their refresh token. Google sends no new refresh "
        "token on a renewal, so nothing is written back.",
        kind=Kind.READ,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=OAUTH_DOC,
    ),
    Cassette(
        cid="GWS-token-400",
        source=SOURCE,
        request="POST /token grant_type=refresh_token",
        status=400,
        body={"error": "invalid_grant", "error_description": "Token has been expired or revoked."},
        why="The person revoked the app at Google, or the token lapsed: their consent is "
        "withdrawn, which is their reads down, said to them, and nobody else's.",
        kind=Kind.ERROR,
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=OAUTH_DOC,
    ),
    Cassette(
        cid="GWS-200-error",
        source=SOURCE,
        request=f"GET /gmail/v1/users/me/messages?{_query(gws.mail_query(WORDS))}",
        status=200,
        body="<html>not the API</html>",
        why="A 200 whose body is not the API's JSON, as a captive portal or a proxy answers: "
        "read as nothing usable, never as an empty mailbox.",
        kind=Kind.ERROR,
        tools=("google_workspace.find_mail",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
    Cassette(
        cid="GWS-401",
        source=SOURCE,
        request=f"GET /gmail/v1/users/me/messages?{_query(gws.mail_query(WORDS))}",
        status=401,
        body=_google_error(401, "authError", "Invalid Credentials"),
        why="An access token Google no longer accepts: a refusal, not an empty mailbox.",
        kind=Kind.ERROR,
        tools=("google_workspace.find_mail",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
    Cassette(
        cid="GWS-429",
        source=SOURCE,
        request=f"GET /calendar/v3/calendars/primary/events?{_query(gws.event_query(WORDS))}",
        status=429,
        body=_google_error(429, "rateLimitExceeded", "Rate Limit Exceeded"),
        why="Google documents exponential backoff and no Retry-After.",
        kind=Kind.RATE_LIMIT,
        tools=("google_workspace.find_events",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
    Cassette(
        cid="GWS-503",
        source=SOURCE,
        request=f"GET /drive/v3/files?{_query(gws.document_query(WORDS))}",
        status=503,
        body=_google_error(503, "backendError", "Backend Error"),
        why="Google is down or degraded: the question is answered without Workspace and "
        "nothing is concluded about what the account holds.",
        kind=Kind.ERROR,
        tools=("google_workspace.find_documents",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    300,
    "message reads a minute for one user, Gmail's dearest call",
    "Gmail allows 6,000 quota units a minute per user and a message read costs 20; Calendar "
    "allows 600 requests a minute per user; Drive 325,000 units a minute per user and an export "
    "costs 200. Each is raised on the project's Cloud console Quotas page.",
    True,
)


def operation_of(recorded: Cassette) -> RestOperation | None:
    """The operation a recording's request was made with, or None for the token endpoint."""
    if "/token" in recorded.request:
        return None
    if "/export" in recorded.request:
        return gws.export_operation()
    if "/messages/" in recorded.request:
        return gws.message_operation()
    if "/messages" in recorded.request:
        return gws.messages_operation()
    if "/calendar/" in recorded.request:
        return gws.events_operation()
    return gws.files_operation()


def replay(recorded: Cassette) -> Replayed:
    """A recording through the connector's own reading of it: the token endpoint through the
    consent's own reader, the API through each operation and the passage builders."""
    from brain.connectors.google_token import TokenNotIssuedError
    from brain.connectors.oauth import tokens_from

    operation = operation_of(recorded)
    if operation is None:
        try:
            tokens_from(status=recorded.status, body=json.dumps(recorded.body).encode())
        except TokenNotIssuedError as refused:
            if refused.call is CallOutcome.REJECTED:
                return Replayed(Expect.REFUSED)
            return Replayed(unreachable_or_quota(refused.call))
        return Replayed(Expect.ANSWERED)
    call = classify(status=recorded.status)
    if call is CallOutcome.REJECTED:
        return Replayed(Expect.REFUSED)
    if call is not CallOutcome.OK:
        return Replayed(unreachable_or_quota(call))
    if operation.operation.operation_id == "drive_files_export":
        text = recorded.body if isinstance(recorded.body, str) else ""
        found = gws.document_found(DOCUMENT, "", "", text, WORDS)
        return Replayed(Expect.ANSWERED if found is not None else Expect.ABSENT)
    try:
        body = gws.answered(recorded.status, recorded.body)
    except gws.WorkspaceError:
        return Replayed(Expect.UNREACHABLE)
    if operation.operation.operation_id == "gmail_messages_list":
        return Replayed(Expect.ANSWERED if gws.message_ids(operation, body) else Expect.ABSENT)
    if operation.operation.operation_id == "gmail_messages_get":
        row = gws.message_row(operation, body)
        found_one = None if row is None else gws.message_found(row)
        return Replayed(Expect.ANSWERED if found_one is not None else Expect.ABSENT)
    if operation.operation.operation_id == "calendar_events_list":
        return Replayed(Expect.ANSWERED if gws.events_found(operation, body) else Expect.ABSENT)
    return Replayed(Expect.ANSWERED if gws.documents_listed(operation, body) else Expect.ABSENT)


def manifest() -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen builds, which is what ships."""
    from brain.ops.connectable import key_reference

    example = gws.CONSOLE.example
    assert example is not None  # the connector declares one
    return gws.built_from_the_console(example.settings, key_reference(SOURCE))


def read_back_answer(recorded: Cassette) -> Verification:
    """One recording through Workspace's read-back reading, as the call it was made against."""
    # A token endpoint's answer is no read of the account, so it is read as a listing whose
    # records it does not hold, which settles nothing.
    operation = operation_of(recorded) or gws.files_operation()
    said = gws.Reply(status=recorded.status, body=recorded.body)
    return answered(SOURCE, operation, said)


#: How each recording this connector's read-back names is answered.
READ_BACK: Final[Mapping[str, Verification]] = MappingProxyType(
    {
        "GWS-200-messages": Verification.FOUND,
        "GWS-200-messages-none": Verification.ABSENT,
        "GWS-200-message": Verification.FOUND,
        "GWS-200-events": Verification.FOUND,
        "GWS-200-files": Verification.FOUND,
        # Plain text, not the API's JSON, and a token answer, neither a listing of anything.
        "GWS-200-export": Verification.INCONCLUSIVE,
        "GWS-token-200": Verification.INCONCLUSIVE,
        "GWS-token-400": Verification.INCONCLUSIVE,
        "GWS-200-error": Verification.INCONCLUSIVE,
        "GWS-401": Verification.INCONCLUSIVE,
        "GWS-429": Verification.INCONCLUSIVE,
        "GWS-503": Verification.INCONCLUSIVE,
    }
)


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    read_back=READ_BACK,
    read_back_answer=read_back_answer,
    wait_not_in_retry_after="none documented; Google asks for exponential backoff",
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
    not_recordable={
        Kind.PAGINATION: (
            "a question reads one page of each service, at most five items, and asks for no "
            "page after it, so nothing this connector reads ever pages"
        ),
    },
)
