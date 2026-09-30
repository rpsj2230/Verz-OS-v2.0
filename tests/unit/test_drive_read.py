"""Google Drive's read half: the listing the worker keeps, and what may stop a file being read.

`brain.connectors.google_drive` listed nothing until 2026-09-30: it declared a manifest and a form
and no reading. These tests hold the reading the worker now runs (the folder's listing, each file's
sharing verdict reduced from the raw permissions, the index entry kept) and the live read's guards,
each built from Drive's raw payload rather than from the value the function under test produces,
so a producer and its consumer are tested apart.

Every date is far from any wall clock, and every domain is a reserved example.

Task ids: M11.6.7
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.connectors import google_drive
from brain.connectors.declaration import KeyScheme, ScopedReading
from brain.connectors.google_drive import (
    A_FILE_LOCKED_NARROWER_THAN_ITS_FOLDER_IS_NEVER_READ,
    DRIVE_SCOPE,
    FILE,
    GOOGLE_DOC_MIME,
    PASSAGE_CHARS,
    WHERE_DRIVE_SHOWS_NO_SHARING_THE_FOLDER_IS_THE_GRANT,
    DriveConnection,
    DriveError,
    DriveReading,
    Endpoint,
    SharingState,
    Withheld,
    folder_listing,
    operation_for,
    sharing_admits_a_read,
    sharing_of,
    text_url_for,
    withheld_from_a_read,
    words_of_a_body,
)
from brain.connectors.google_token import checked_scopes
from brain.connectors.manifest import RESOLVED_ACL_RE

#: The company's own domain in these tests, and another company's.
OWN: Final = "company.example"
FOREIGN: Final = "elsewhere.example"
FOLDER: Final = "fldR3adT3st0001"
SEEN: Final = datetime(2999, 1, 1, tzinfo=UTC)


def a_connection() -> DriveConnection:
    return DriveConnection(folder_id=FOLDER, domain=OWN, department="operations", steward_id="u_s")


def a_file(file_id: str = "fileAAA111", **overrides: Any) -> dict[str, Any]:
    """One file as Drive's API describes it, before anything here has read it."""
    raw: dict[str, Any] = {
        "id": file_id,
        "name": "Opening hours",
        "mimeType": GOOGLE_DOC_MIME,
        "modifiedTime": "2999-01-01T09:00:00.000Z",
        "headRevisionId": "rev1",
        "trashed": False,
        "parents": [FOLDER],
        "inheritedPermissionsDisabled": False,
    }
    raw.update(overrides)
    return raw


def metadata(raw: dict[str, Any]) -> tuple[Any, SharingState]:
    """What the live read has of a file: its mapped row and the verdict of its permissions."""
    (row,) = operation_for(Endpoint.GET_FILE).project(raw)
    return row, sharing_of(raw.get("permissions"), domain=OWN)


# ------------------------------------------------------------ the sharing verdict
@pytest.mark.parametrize(
    ("permissions", "verdict"),
    [
        (None, SharingState.UNDETERMINED),
        ([], SharingState.UNDETERMINED),
        ([{"type": "domain", "domain": OWN}, {"type": "user", "domain": OWN}], "restricted"),
        ([{"type": "domain", "domain": OWN}, {"type": "user"}], SharingState.UNDETERMINED),
        ([{"type": "user"}, {"type": "anyone"}], SharingState.LINK),
        ([{"type": "user"}, {"type": "user", "domain": FOREIGN}], SharingState.EXTERNAL),
        ([{"type": "rumour"}], SharingState.UNDETERMINED),
    ],
)
def test_a_file_s_permissions_reduce_to_one_verdict_and_the_wider_fact_wins(
    permissions: Any, verdict: str
) -> None:
    """`sharing_of`, from Drive's raw permissions: an absent list is undetermined, which is what a
    Viewer is shown; every grant inside the company is restricted, and one grant nobody could read
    makes that undetermined; a link or a foreign domain is reported whatever else was unreadable.

    Delete this and a file shared by link can read as restricted because one grant carried no
    domain, or a file inside the company can read as shared outside it."""
    assert sharing_of(permissions, domain=OWN) == verdict


def test_a_file_whose_sharing_drive_did_not_show_is_read_as_the_folder_s() -> None:
    """`WHERE_DRIVE_SHOWS_NO_SHARING_THE_FOLDER_IS_THE_GRANT`, needs-rupash 135 decided A: a file
    Drive showed nothing of is read, as one shown inside the company is; a file shown as shared by
    link or outside the company never is.

    Delete this and either every file is refused, which with the account a Viewer reads nothing,
    or a file shared outside the company is told to the department."""
    assert "needs-rupash 135" in WHERE_DRIVE_SHOWS_NO_SHARING_THE_FOLDER_IS_THE_GRANT
    assert {state for state in SharingState if sharing_admits_a_read(state)} == {
        SharingState.RESTRICTED,
        SharingState.UNDETERMINED,
    }


# ------------------------------------------------------------ the live read's guards
def test_a_doc_inside_the_folder_and_nothing_else_is_read() -> None:
    """The positive case every refusal below is a sibling of: a Google Doc listed in the folder,
    not binned, not locked, whose sharing Drive did not show. Delete this and a guard that refuses
    every file passes every test below."""
    assert withheld_from_a_read(a_connection(), *metadata(a_file())) is None


@pytest.mark.parametrize(
    ("changed", "why"),
    [
        ({"parents": ["fldSomewhereElse"]}, Withheld.OUTSIDE),
        ({"parents": []}, Withheld.OUTSIDE),
        ({"trashed": True}, Withheld.TRASHED),
        ({"inheritedPermissionsDisabled": True}, Withheld.LOCKED),
        ({"permissions": [{"type": "anyone"}]}, Withheld.SHARED_BEYOND),
        ({"permissions": [{"type": "domain", "domain": FOREIGN}]}, Withheld.SHARED_BEYOND),
        ({"mimeType": "application/pdf"}, Withheld.NOT_WORDS),
        ({"mimeType": "application/vnd.google-apps.spreadsheet"}, Withheld.NOT_WORDS),
    ],
)
def test_a_file_drive_now_says_is_elsewhere_binned_locked_shared_or_wordless_is_not_read(
    changed: dict[str, Any], why: Withheld
) -> None:
    """`withheld_from_a_read`, asked of what Drive says now: moved out of the folder, in the bin,
    locked narrower than its folder (`A_FILE_LOCKED_NARROWER_THAN_ITS_FOLDER_IS_NEVER_READ`),
    shown as shared by link or outside the company, or with no words to read. Delete this and a
    file the index listed an hour ago is read after somebody moved, binned, locked or published
    it."""
    assert withheld_from_a_read(a_connection(), *metadata(a_file(**changed))) is why
    assert "inherited permissions" in A_FILE_LOCKED_NARROWER_THAN_ITS_FOLDER_IS_NEVER_READ


def test_a_file_whose_bin_state_drive_did_not_say_is_not_read() -> None:
    """Drive says `trashed` when it is asked for, so a reply without it is not one that said the
    file is out of the bin. Delete this and a missing field reads as a file somebody kept."""
    raw = a_file()
    del raw["trashed"]
    assert withheld_from_a_read(a_connection(), *metadata(raw)) is Withheld.TRASHED


def test_a_doc_is_exported_as_plain_text_and_a_text_file_read_as_it_is() -> None:
    """`text_url_for`: a Google Doc through `files.export` as text/plain, a plain-text file
    through its content, and anything else not at all; an id outside the grammar is refused before
    it reaches an address. Delete this and a Doc can be asked for in a format a person does not
    read, or a binary file handed to the model as words."""
    exported = urlsplit(text_url_for("fileAAA111", GOOGLE_DOC_MIME) or "")
    media = urlsplit(text_url_for("fileAAA111", "text/markdown") or "")

    assert (exported.path, parse_qs(exported.query)) == (
        "/drive/v3/files/fileAAA111/export",
        {"mimeType": ["text/plain"]},
    )
    assert (media.path, parse_qs(media.query)["alt"]) == ("/drive/v3/files/fileAAA111", ["media"])
    assert text_url_for("fileAAA111", "application/pdf") is None
    with pytest.raises(DriveError):
        text_url_for("../other", GOOGLE_DOC_MIME)


def test_a_file_s_words_are_decoded_and_cut_to_one_passage() -> None:
    """A byte-order mark is dropped, bytes that are not UTF-8 are replaced rather than refused,
    and the words are cut to `PASSAGE_CHARS`. Delete this and one long file fills the model's
    prompt, or a file saved with a mark opens its passage with it."""
    assert words_of_a_body("﻿Hello".encode()) == "Hello"
    assert words_of_a_body(b"ok \xff") == "ok �"
    assert len(words_of_a_body(b"x" * (PASSAGE_CHARS + 50))) == PASSAGE_CHARS


# ------------------------------------------------------------ the worker's reading
def test_the_reading_lists_the_pin_by_its_cursor_alone() -> None:
    """The listing's query, fields and flags are the connection's own, so a page is asked for by
    its cursor and nothing a run hands it can change which folder is listed. Delete this and a
    page argument could widen the listing to a folder nobody connected."""
    listing = folder_listing(a_connection())
    first = parse_qs(urlsplit(listing.url_for({})).query)
    later = parse_qs(urlsplit(listing.url_for({"pageToken": "next1"})).query)

    assert first["q"] == [f"'{FOLDER}' in parents and trashed = false"]
    assert later["pageToken"] == ["next1"] and later["q"] == first["q"]
    with pytest.raises(DriveError):
        listing.url_for({"q": "trashed = false"})


def test_a_listed_row_carries_its_pin_and_its_verdict_and_never_its_permissions() -> None:
    """Each row the listing projects carries the pin it was reached through and the verdict
    `sharing_of` reduced its permissions to, and the permissions go no further. Delete this and the
    index can keep a file with no verdict, or keep the grantees themselves."""
    body = {
        "files": [
            a_file("fileAAA111"),
            a_file("fileBBB222", permissions=[{"type": "domain", "domain": FOREIGN}]),
        ]
    }
    rows = folder_listing(a_connection()).project(body)

    assert [(one["folder_id"], one["sharing_state"]) for one in rows] == [
        (FOLDER, "undetermined"),
        (FOLDER, "external"),
    ]
    assert not any("permissions" in one for one in rows)


def test_a_listed_row_outside_the_pin_refuses_the_page() -> None:
    """`assert_row_is_in_the_folder`, on the worker's path: a row that names another parent means
    the query is not the one sent, so the page is refused rather than filtered. Its sibling is the
    test above, where every row is the pin's. Delete this and a listing that went wrong keeps files
    from a folder nobody connected."""
    body = {"files": [a_file(), a_file("fileCCC333", parents=["fldSomewhereElse"])]}
    with pytest.raises(DriveError):
        folder_listing(a_connection()).project(body)


def test_the_reading_is_a_service_account_s_with_the_read_only_drive_scope() -> None:
    """The key is a key file exchanged for a token carrying `drive.readonly` alone, which the token
    module accepts as read-only. Delete this and the token could be minted for `drive`, which
    writes and deletes."""
    reading = DriveReading()
    assert reading.key_scheme() is KeyScheme.GOOGLE_SERVICE_ACCOUNT
    assert isinstance(reading, ScopedReading)
    assert reading.token_scopes() == (DRIVE_SCOPE,) == checked_scopes((DRIVE_SCOPE,))
    assert DRIVE_SCOPE.endswith("/drive.readonly")


def test_the_reading_follows_drive_s_cursor_and_stops_when_it_stops() -> None:
    """Drive states continuation in `nextPageToken`. Delete this and a folder of more than one
    page is indexed a page short, or read for ever."""
    reading = DriveReading()
    assert reading.next_page(FILE, {}, {"nextPageToken": "next1", "files": []}, 0) == {
        "pageToken": "next1"
    }
    assert reading.next_page(FILE, {}, {"files": []}, 0) is None


def test_a_file_is_kept_with_its_pin_and_verdict_and_a_folder_or_shortcut_is_not() -> None:
    """The index entry: a file's id, name, type, dates, revision and verdict, the pin, and nothing
    that names a person or a permission; a folder has no words and a shortcut points anywhere, so
    neither is kept. Delete this and the index can grow a folder nobody reads or a shortcut to a
    file outside the pin."""
    reading = DriveReading()
    body = {
        "files": [
            a_file("fileAAA111"),
            a_file("fldSub00001", mimeType="application/vnd.google-apps.folder"),
            a_file("shortcut001", mimeType="application/vnd.google-apps.shortcut"),
        ]
    }
    records = folder_listing(a_connection()).records(body, fetched_at=SEEN.isoformat())
    kept = [reading.projected(FILE, one.model_dump(), seen_at=SEEN) for one in records.records]

    assert [None if one is None else one.source_id for one in kept] == ["fileAAA111", None, None]
    fields = kept[0].fields if kept[0] is not None else {}
    assert fields["folder_id"] == FOLDER and fields["sharing_state"] == "undetermined"
    assert not any(RESOLVED_ACL_RE.search(name) for name in fields)
    assert "locked" not in fields and "parents" not in fields


def test_the_folder_s_rows_carry_the_department_a_grant_is_scoped_by() -> None:
    """The stored predicate is the folder and its department, so a `read:file` grant scoped to
    that department reaches the rows. Delete this and the rows carry no department, and a reader
    granted the folder's files in their department is refused every one."""
    clauses = {one.field: one.value for one in a_connection().visibility_predicate().clauses}
    assert clauses == {"folder_id": FOLDER, "department": "operations"}
    assert google_drive.CONNECTOR.reading is not None
