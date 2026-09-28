"""Google Drive's recordings: a folder page, a file, two throttles, a refusal and a 404.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from brain.connectors import google_drive
from brain.connectors.manifest import ConnectorManifest
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

SOURCE: Final = "google_drive"

DRIVE_LIST_DOC = "https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list"
DRIVE_GET_DOC = "https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get"
DRIVE_ERRORS_DOC = "https://developers.google.com/workspace/drive/api/guides/handle-errors"

#: The folder a Drive recording's listing was asked for. The replay pins its connection here.
DRIVE_FOLDER = "fld0447AbC-_x"

#: Why the file projection's positive path cannot be replayed from a documented shape.
NO_SHARING_READER: Final = (
    "a file is kept only with a sharing state, which is reduced from the permissions Drive "
    "returns; the connector has no function reading them out of a response, and Google's "
    "documentation does not say whether a user grant carries the domain that reduction "
    "needs, so only a live capture can settle it"
)


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="DRIVE-200-files-page",
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
        source=SOURCE,
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
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    0,
    "not measured",
    "Google publishes per-project and per-user query quotas that a project owner sees "
    "and changes in the Cloud console, so there is no one figure to record here; "
    "`brain.connectors.google_drive.THERE_IS_NO_MEASURED_CEILING_HERE` says the same.",
    True,
)


def _drive_connection() -> google_drive.DriveConnection:
    from tests.unit.test_google_drive import a_connection

    return a_connection(folder_id=DRIVE_FOLDER)


@dataclass
class _DriveReader:
    reply: google_drive.Reply

    def read(self, request: google_drive.ListingRequest) -> google_drive.Reply:
        del request
        return self.reply


def replay(recorded: Cassette) -> Replayed:
    """A recording through `google_drive.read_page` or a file read, and the folder check."""
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
        return Replayed(unreachable_or_quota(failed.call_outcome))
    if not rows:
        return Replayed(Expect.ABSENT)
    # No function in the connector reads a permission array out of a response, so no sharing
    # state has a producer to replay; see `NO_SHARING_READER`. What is replayed is the refusal:
    # a row whose sharing nobody determined is not kept.
    for row in rows:
        with pytest.raises(google_drive.DriveError):
            google_drive.projected_fields(
                row,
                connection=connection,
                sharing=google_drive.classify_sharing(None, domain="verz.com"),
            )
    return Replayed(Expect.MORE_TO_READ if cursor else Expect.ANSWERED)


def manifest() -> ConnectorManifest:
    from tests.unit import test_google_drive

    built: ConnectorManifest = test_google_drive.a_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
    projection_not_replayable={"file": NO_SHARING_READER},
)
