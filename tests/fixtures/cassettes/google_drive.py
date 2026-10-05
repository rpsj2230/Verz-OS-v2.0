"""Google Drive's recordings: a folder page, a file, two throttles, a refusal and a 404.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

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
                    "permissions": [
                        {"type": "user"},
                        {"type": "domain", "domain": "CANARY-DRIVE-GRANTEE-DOMAIN"},
                    ],
                }
            ],
        },
        why="A page with a cursor: Drive states continuation in nextPageToken. The "
        "permissions are sub-selected to type and domain and are reduced to a verdict where the "
        "page is read; a grantee's domain is never kept, which the canary proves.",
        kind=Kind.PAGINATION,
        tools=("google_drive.list_folder",),
        projects="drive_file",
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
    1625,
    "minute",
    "325,000 quota units a minute per user per project, and a download costs 200, so 1,625 of the "
    "dearest call a read makes; `brain.ops.limits` records the same figure. A project owner may "
    "ask for more on the Cloud console's Quotas page.",
    True,
)


#: When a replayed listing is read and seen. Far from any wall clock, deliberately.
AT: Final = "2999-01-01T00:00:00+00:00"
SEEN: Final = datetime(2999, 1, 1, tzinfo=UTC)

#: Every verdict a kept row may carry.
SHARING_STATES: Final = frozenset(state.value for state in google_drive.SharingState)


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
    outcome = Expect.MORE_TO_READ if cursor else Expect.ANSWERED
    if not listing:
        return Replayed(outcome)
    # Through the worker's own reading: the listing lays each file's verdict on its row, and the
    # reading keeps it, a verdict Drive did not show as "undetermined" (needs-rupash 135).
    reading = google_drive.DriveReading()
    listed = google_drive.folder_listing(connection).records(reply.body, fetched_at=AT)
    kept = tuple(
        one
        for record in listed.records
        if (one := reading.projected(google_drive.FILE, record.model_dump(), seen_at=SEEN))
        is not None
    )
    assert all(one.fields["sharing_state"] in SHARING_STATES for one in kept)
    return Replayed(outcome, kept=kept)


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
)
