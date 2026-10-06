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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.connectors import google_drive
from brain.connectors.declaration import KeyScheme, ScopedReading
from brain.connectors.google_drive import (
    A_FILE_LOCKED_NARROWER_THAN_ITS_FOLDER_IS_NEVER_READ,
    DRIVE_SCOPE,
    FILE,
    FOLDER_MIME,
    GOOGLE_DOC_MIME,
    MAX_FOLDER_DEPTH,
    PASSAGE_CHARS,
    THE_WHOLE_TREE_UNDER_THE_PIN_IS_WALKED_AND_NOTHING_OUTSIDE_IT,
    WALK_FOLDER,
    WALK_LEFT_OUT,
    WALK_PATH,
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
FOLDER_ID: Final = "fldR3adT3st0001"
SEEN: Final = datetime(2999, 1, 1, tzinfo=UTC)


def a_connection() -> DriveConnection:
    return DriveConnection(
        folder_id=FOLDER_ID, domain=OWN, department="operations", steward_id="u_s"
    )


def a_file(file_id: str = "fileAAA111", **overrides: Any) -> dict[str, Any]:
    """One file as Drive's API describes it, before anything here has read it."""
    raw: dict[str, Any] = {
        "id": file_id,
        "name": "Opening hours",
        "mimeType": GOOGLE_DOC_MIME,
        "modifiedTime": "2999-01-01T09:00:00.000Z",
        "headRevisionId": "rev1",
        "trashed": False,
        "parents": [FOLDER_ID],
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

    assert first["q"] == [f"'{FOLDER_ID}' in parents and trashed = false"]
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
        (FOLDER_ID, "undetermined"),
        (FOLDER_ID, "external"),
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
    """Drive states continuation in `nextPageToken`, and a page holding no folder to walk with no
    cursor is the last. Delete this and a folder of more than one page is indexed a page short, or
    read for ever."""
    reading = DriveReading()
    following = reading.next_page(FILE, {}, {"nextPageToken": "next1", "files": []}, 0)
    assert following is not None and following["pageToken"] == "next1"
    assert following[WALK_FOLDER] == ""
    assert reading.next_page(FILE, {}, {"files": []}, 0) is None


def test_a_file_and_a_walked_folder_are_kept_and_a_shortcut_or_a_locked_one_is_not() -> None:
    """The index entry: a file's or a folder's id, name, type, dates, revision and verdict, the pin,
    and nothing that names a person or a permission. A folder is kept because the live read takes a
    file inside it as inside the tree; a shortcut points anywhere and is never kept; and nothing
    locked narrower than its parent is kept. Delete this and the index can keep a shortcut to a file
    outside the pin, or a locked folder whose files the live read would then read."""
    reading = DriveReading()
    body = {
        "files": [
            a_file("fileAAA111"),
            a_file("fldSub00001", mimeType=FOLDER_MIME),
            a_file("shortcut001", mimeType="application/vnd.google-apps.shortcut"),
            a_file("fldLocked01", mimeType=FOLDER_MIME, inheritedPermissionsDisabled=True),
            a_file("fileLocked1", inheritedPermissionsDisabled=True),
        ]
    }
    records = folder_listing(a_connection()).records(body, fetched_at=SEEN.isoformat())
    kept = [reading.projected(FILE, one.model_dump(), seen_at=SEEN) for one in records.records]

    assert [None if one is None else one.source_id for one in kept] == [
        "fileAAA111",
        "fldSub00001",
        None,
        None,
        None,
    ]
    fields = kept[0].fields if kept[0] is not None else {}
    assert fields["folder_id"] == FOLDER_ID and fields["sharing_state"] == "undetermined"
    assert not any(RESOLVED_ACL_RE.search(name) for name in fields)
    assert "locked" not in fields and "parents" not in fields


# ------------------------------------------------------------ the walk of the tree
def walk(tree: dict[str, list[dict[str, Any]]], *, pages: int = 50) -> tuple[list[str], list[str]]:
    """The reading over `tree` as the worker's page loop runs it: the folders listed, in order, and
    the ids kept in the index. Each folder answers its own rows; `pages` is the worker's bound."""
    reading = DriveReading()
    listing = folder_listing(a_connection())
    listed: list[str] = []
    kept: list[str] = []
    arguments: Any = reading.first_page(FILE)
    while arguments is not None and len(listed) < pages:
        asked = parse_qs(urlsplit(listing.url_for(arguments)).query)["q"][0]
        folder = asked.split("'")[1]
        listed.append(folder)
        body = {"files": tree.get(folder, [])}
        for one in listing.records(body, fetched_at=SEEN.isoformat()).records:
            entry = reading.projected(FILE, one.model_dump(), seen_at=SEEN)
            if entry is not None:
                kept.append(entry.source_id)
        arguments = reading.next_page(FILE, arguments, body, len(body["files"]))
    return listed, kept


def a_child(file_id: str, parent: str, **overrides: Any) -> dict[str, Any]:
    return a_file(file_id, parents=[parent], **overrides)


def test_a_file_at_every_level_under_the_pin_is_kept_under_the_pin() -> None:
    """`THE_WHOLE_TREE_UNDER_THE_PIN_IS_WALKED_AND_NOTHING_OUTSIDE_IT`: the pin, its subfolder and
    that one's subfolder are each listed once, and the file two levels down is kept under the pin
    it was reached through. Delete this and a folder's subfolders are never read, which narrows
    "the folders it was given" to their top level."""
    tree = {
        FOLDER_ID: [
            a_child("fileTop0001", FOLDER_ID),
            a_child("fldLevel001", FOLDER_ID, mimeType=FOLDER_MIME),
        ],
        "fldLevel001": [a_child("fldLevel002", "fldLevel001", mimeType=FOLDER_MIME)],
        "fldLevel002": [a_child("fileDeep001", "fldLevel002")],
    }
    listed, kept = walk(tree)

    assert listed == [FOLDER_ID, "fldLevel001", "fldLevel002"]
    assert kept == ["fileTop0001", "fldLevel001", "fldLevel002", "fileDeep001"]
    assert "walk" in THE_WHOLE_TREE_UNDER_THE_PIN_IS_WALKED_AND_NOTHING_OUTSIDE_IT


@pytest.mark.parametrize(
    "locked",
    [
        {"inheritedPermissionsDisabled": True},
        {"permissions": [{"type": "anyone"}]},
    ],
)
def test_a_locked_or_link_shared_subfolder_and_everything_in_it_are_left_out(
    locked: dict[str, Any],
) -> None:
    """A subfolder locked narrower than its parent, or shown as shared by link, is not walked, so
    none of its files are listed; its sibling, an ordinary subfolder beside it, is. Delete this and
    a folder somebody kept to fewer people is indexed for the whole department."""
    tree = {
        FOLDER_ID: [
            a_child("fldOpen0001", FOLDER_ID, mimeType=FOLDER_MIME),
            a_child("fldShut0001", FOLDER_ID, mimeType=FOLDER_MIME, **locked),
        ],
        "fldOpen0001": [a_child("fileOpen001", "fldOpen0001")],
        "fldShut0001": [a_child("fileShut001", "fldShut0001")],
    }
    listed, kept = walk(tree)

    assert listed == [FOLDER_ID, "fldOpen0001"]
    assert "fileOpen001" in kept and "fileShut001" not in kept and "fldShut0001" not in kept


def test_a_shortcut_to_a_folder_is_never_followed() -> None:
    """A shortcut, even one to a folder, is not walked, so a folder outside the tree is never
    listed through one; a real subfolder beside it is. Delete this and a shortcut in the pin reads
    another department's folder."""
    shortcut = a_child(
        "shortcut001",
        FOLDER_ID,
        mimeType="application/vnd.google-apps.shortcut",
        shortcutDetails={"targetId": "fldElsewhere"},
    )
    tree = {
        FOLDER_ID: [shortcut, a_child("fldReal0001", FOLDER_ID, mimeType=FOLDER_MIME)],
        "fldElsewhere": [a_child("fileAway001", "fldElsewhere")],
    }
    listed, kept = walk(tree)

    assert listed == [FOLDER_ID, "fldReal0001"]
    assert "fileAway001" not in kept and "shortcut001" not in kept


def test_a_loop_of_folders_is_walked_once_and_ends() -> None:
    """Two folders each naming the other as a child (a file with two parents) are each listed once,
    and the walk ends; the folder reached first is listed, the one reached again is not. Delete
    this and a loop lists the same two folders until the worker's page bound stops it."""
    tree = {
        FOLDER_ID: [a_child("fldLoopA001", FOLDER_ID, mimeType=FOLDER_MIME)],
        "fldLoopA001": [a_child("fldLoopB001", "fldLoopA001", mimeType=FOLDER_MIME)],
        "fldLoopB001": [a_child("fldLoopA001", "fldLoopB001", mimeType=FOLDER_MIME)],
    }
    listed, _ = walk(tree)

    assert listed == [FOLDER_ID, "fldLoopA001", "fldLoopB001"]


def a_chain(top: str, depth: int, *, name: str = "fldChain") -> dict[str, list[dict[str, Any]]]:
    """A chain of `depth` folders under `top`, each holding one file and the next folder down."""
    tree: dict[str, list[dict[str, Any]]] = {}
    parent = top
    for level in range(1, depth + 1):
        folder = f"{name}{level:04d}"
        tree.setdefault(parent, []).append(a_child(folder, parent, mimeType=FOLDER_MIME))
        tree[folder] = [a_child(f"file{name}{level:04d}", folder)]
        parent = folder
    return tree


def test_a_folder_deeper_than_the_bound_is_not_entered_and_every_page_after_says_so() -> None:
    """`MAX_FOLDER_DEPTH`, the `BoundedWalk` the worker asks: a chain three deeper than the bound is
    listed down to the bound and no further, its deeper files are not kept, the walk still ends,
    and `left_out` is true on the page that met the bound and on every page the walk asks after
    it, because the mark travels in the walk's own arguments. Its sibling below is a chain exactly
    as deep as the bound, read whole with nothing left out. Delete this and a tree deeper than the
    bound is read in part with nothing said, and the worker retires every file it did not reach."""
    from brain.connectors.declaration import BoundedWalk

    reading = DriveReading()
    assert isinstance(reading, BoundedWalk)
    tree = a_chain(FOLDER_ID, MAX_FOLDER_DEPTH + 3)
    listed, kept = walk(tree, pages=MAX_FOLDER_DEPTH * 2)

    assert listed == [FOLDER_ID, *(f"fldChain{n:04d}" for n in range(1, MAX_FOLDER_DEPTH + 1))]
    assert f"filefldChain{MAX_FOLDER_DEPTH:04d}" in kept
    assert f"filefldChain{MAX_FOLDER_DEPTH + 1:04d}" not in kept

    deepest = f"fldChain{MAX_FOLDER_DEPTH:04d}"
    arguments: Any = reading.first_page(FILE)
    while arguments.get(WALK_FOLDER) != deepest:
        arguments = reading.next_page(FILE, arguments, {"files": tree[_folder(arguments)]}, 1)
    assert not reading.left_out(FILE, arguments, {"files": []})
    met = {"files": tree[deepest]}
    assert reading.left_out(FILE, arguments, met)
    assert reading.next_page(FILE, arguments, met, 2) is None
    marked = dict(arguments, **{WALK_LEFT_OUT: "1"})
    assert reading.left_out(FILE, marked, {"files": []})


def test_a_tree_exactly_as_deep_as_the_bound_is_read_whole_and_nothing_is_left_out() -> None:
    """The positive sibling of the test above: a chain `MAX_FOLDER_DEPTH` deep is listed to its
    last folder, every file is kept, and no page says a folder was left out. And the figure is the
    one connector health states. Delete this and a bound that refuses one level too early, or a
    health sentence naming another depth, passes."""
    from brain.ops.connector_sync import READ_BUT_PART_LEFT_OUT

    reading = DriveReading()
    tree = a_chain(FOLDER_ID, MAX_FOLDER_DEPTH)
    listed, kept = walk(tree, pages=MAX_FOLDER_DEPTH * 2)

    assert len(listed) == MAX_FOLDER_DEPTH + 1
    assert f"filefldChain{MAX_FOLDER_DEPTH:04d}" in kept
    arguments: Any = reading.first_page(FILE)
    while arguments is not None:
        body = {"files": tree.get(_folder(arguments), [])}
        assert not reading.left_out(FILE, arguments, body)
        arguments = reading.next_page(FILE, arguments, body, 1)
    assert f"more than {MAX_FOLDER_DEPTH} levels" in READ_BUT_PART_LEFT_OUT


def _folder(arguments: Any) -> str:
    return str(arguments.get(WALK_FOLDER) or FOLDER_ID)


# ------------------------------------------------------- a tree read whole over passes
#: Drive's list endpoint as the recordings in `tests/fixtures/cassettes/google_drive.py` spell it.
LISTED: Final = "GET /drive/v3/files?q='{folder}' in parents and trashed = false"


def recorded_pages(
    tree: dict[str, list[list[dict[str, Any]]]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Recorded Drive list pages, one per folder page, keyed by the folder and the page token that
    asked for it, each body in the documented envelope with `nextPageToken` where more follows."""
    pages: dict[tuple[str, str], dict[str, Any]] = {}
    for folder, listed in tree.items():
        for index, rows in enumerate(listed):
            body: dict[str, Any] = {"files": rows}
            if index + 1 < len(listed):
                body["nextPageToken"] = f"~!!~{folder}.{index + 1}"
            pages[(folder, f"~!!~{folder}.{index}" if index else "")] = body
    return pages


def wide_and_deep() -> dict[str, list[list[dict[str, Any]]]]:
    """A tree wider and deeper than one pass: the pin answers two pages naming five subfolders
    between them; four of those are chains twelve deep whose every folder answers two pages, and
    the fifth is a chain sixty deep, more than one pass's fifty pages on its own."""
    folder = {"mimeType": FOLDER_MIME}
    pin_first = [a_child("filePin0001", FOLDER_ID)] + [
        a_child(f"fldWide{n}000", FOLDER_ID, **folder) for n in range(3)
    ]
    pin_second = [a_child("filePin0002", FOLDER_ID), a_child("fldWide3000", FOLDER_ID, **folder)]
    pin_second.append(a_child("fldDeep0000", FOLDER_ID, **folder))
    tree: dict[str, list[list[dict[str, Any]]]] = {FOLDER_ID: [pin_first, pin_second]}
    for n in range(4):
        for level in range(12):
            here = f"fldWide{n}{level:03d}"
            first = [a_child(f"fileWide{n}{level:03d}a", here)]
            if level < 11:
                first.append(a_child(f"fldWide{n}{level + 1:03d}", here, **folder))
            tree[here] = [first, [a_child(f"fileWide{n}{level:03d}b", here)]]
    for level in range(60):
        here = f"fldDeep{level:04d}"
        rows = [a_child(f"fileDeep{level:04d}", here)]
        if level < 59:
            rows.append(a_child(f"fldDeep{level + 1:04d}", here, **folder))
        tree[here] = [rows]
    return tree


@dataclass
class Pass:
    """One pass of the worker over recorded pages: the pages it asked, what it kept, the place it
    saved for the next pass (None when the walk ended), and whether it left a folder out."""

    asked: list[tuple[str, str]]
    kept: list[str]
    saved: str | None
    left_out: bool


def passes_over(
    pages: dict[tuple[str, str], dict[str, Any]], *, bound: int, most: int = 20
) -> list[Pass]:
    """The reading over recorded pages as the worker runs it, pass after pass: each pass asks at
    most `bound` pages from the place the last one saved, and saves the page it would ask next
    through the read state's own text (`page_cursor`, `page_of`), until a pass ends the walk."""
    from brain.ops.connector_sync import page_cursor, page_of

    reading = DriveReading()
    listing = folder_listing(a_connection())
    done: list[Pass] = []
    saved: str | None = ""
    while saved is not None and len(done) < most:
        arguments: Any = page_of(saved) if saved else reading.first_page(FILE)
        one = Pass(asked=[], kept=[], saved=None, left_out=False)
        while arguments is not None:
            if len(one.asked) >= bound:
                one.saved = page_cursor(arguments)
                break
            asked = parse_qs(urlsplit(listing.url_for(arguments)).query)
            folder = asked["q"][0].split("'")[1]
            assert LISTED.format(folder=folder).endswith(asked["q"][0])
            key = (folder, asked.get("pageToken", [""])[0])
            one.asked.append(key)
            body = pages[key]
            for row in listing.records(body, fetched_at=SEEN.isoformat()).records:
                entry = reading.projected(FILE, row.model_dump(), seen_at=SEEN)
                if entry is not None:
                    one.kept.append(entry.source_id)
            one.left_out = one.left_out or reading.left_out(FILE, arguments, body)
            arguments = reading.next_page(FILE, arguments, body, len(body["files"]))
        done.append(one)
        saved = one.saved
    return done


def test_a_tree_wider_and_deeper_than_a_pass_is_read_whole_over_several_passes() -> None:
    """**M11.9.15, depth first.** A recorded tree of a hundred and fifty-eight pages, five
    subfolders wide at the pin and sixty deep down one branch, is read over four passes of fifty:
    every recorded page is asked exactly once across them, every file and folder is kept exactly
    once, the walk's place is gone after the last, and each pass after the first starts at the
    page the one before saved, never at the pin. What a saved place holds is the path, no longer
    than the folder's depth. Delete this and a tree larger than one pass is read from the pin on
    every pass and never past its first fifty pages, or read twice over, or a place grows with
    the tree until it is the tree."""
    from brain.ops.connector_sync import page_of

    pages = recorded_pages(wide_and_deep())
    done = passes_over(pages, bound=50)

    asked = [key for one in done for key in one.asked]
    kept = [file_id for one in done for file_id in one.kept]
    recorded = [row["id"] for body in pages.values() for row in body["files"]]
    assert len(done) == 4 and done[-1].saved is None
    assert sorted(asked) == sorted(pages) and len(asked) == len(set(asked)) == 158
    assert sorted(kept) == sorted(recorded) and len(kept) == len(set(kept))
    for before, after in pairwise(done):
        assert before.saved is not None
        place = page_of(before.saved)
        assert after.asked[0] == (_folder(place), place.get("pageToken", ""))
        assert after.asked[0] != (FOLDER_ID, "")
        assert len(google_drive.walk_path(place)) <= 61
    assert not any(one.left_out for one in done)


def test_a_small_tree_is_read_whole_in_one_pass_and_leaves_no_place() -> None:
    """The positive case: a pin with two subfolders, one of them answering two pages, is read in one
    pass, every page once and every file kept, and the pass saves no place, so the next starts again
    at the pin. Delete this and a walk that never ends, or one that saves a place after its last
    page, passes the test above's passes as long as they stop."""
    folder = {"mimeType": FOLDER_MIME}
    tree = {
        FOLDER_ID: [
            [
                a_child("fileTop0001", FOLDER_ID),
                a_child("fldSmallA01", FOLDER_ID, **folder),
                a_child("fldSmallB01", FOLDER_ID, **folder),
            ]
        ],
        "fldSmallA01": [
            [a_child("fileSmallA1", "fldSmallA01")],
            [a_child("fileSmallA2", "fldSmallA01")],
        ],
        "fldSmallB01": [[a_child("fileSmallB1", "fldSmallB01")]],
    }
    pages = recorded_pages(tree)
    (only,) = passes_over(pages, bound=50)

    assert only.saved is None and not only.left_out
    assert only.asked == [
        (FOLDER_ID, ""),
        ("fldSmallA01", ""),
        ("fldSmallA01", "~!!~fldSmallA01.1"),
        ("fldSmallB01", ""),
    ]
    assert sorted(only.kept) == sorted(
        ["fileTop0001", "fldSmallA01", "fldSmallB01", "fileSmallA1", "fileSmallA2", "fileSmallB1"]
    )


def test_a_loop_met_in_a_later_pass_is_not_walked_again() -> None:
    """The cycle guard holds across passes: a chain sixty deep whose deepest folder names the
    tenth folder down and the pin as children meets both in the second pass, after the first has
    saved its place, and walks neither again; every folder is listed once and the walk ends.
    Delete this and a loop met after a pass boundary is walked until the page bound stops every
    pass, and the tree is never read to its end."""
    tree = a_chain(FOLDER_ID, 60, name="fldRing")
    deepest = "fldRing0060"
    tree[deepest] += [
        a_child("fldRing0010", deepest, mimeType=FOLDER_MIME),
        a_child(FOLDER_ID, deepest, mimeType=FOLDER_MIME),
    ]
    pages = recorded_pages({folder: [rows] for folder, rows in tree.items()})
    done = passes_over(pages, bound=50)

    asked = [key for one in done for key in one.asked]
    assert len(done) == 2 and done[-1].saved is None
    assert [folder for folder, _ in asked] == [
        FOLDER_ID,
        *(f"fldRing{n:04d}" for n in range(1, 61)),
    ]


def test_a_place_saved_by_the_breadth_first_walk_is_carried_on() -> None:
    """A place an earlier release saved names the folder it was listing and the folders it still had
    to list, and no path: the listing still accepts it, and the walk lists those folders and then
    ends, so a pass under way when this release arrived is finished rather than dropped. Delete
    this and the first run after the release fails on its saved place for ever, or ends the pass
    early and reports a tree read whole that was not."""
    reading = DriveReading()
    saved = {
        WALK_FOLDER: "fldOldA0001",
        google_drive.BREADTH_FIRST_PENDING: "fldOldB0001 fldOldC0001",
        google_drive.BREADTH_FIRST_SEEN: "fldOldA0001 fldOldB0001 fldOldC0001",
    }
    folder_listing(a_connection()).url_for(saved)
    listed: list[str] = []
    arguments: Any = saved
    while arguments is not None:
        listed.append(_folder(arguments))
        arguments = reading.next_page(FILE, arguments, {"files": []}, 0)
    assert listed == ["fldOldA0001", "fldOldB0001", "fldOldC0001"]


@pytest.mark.parametrize(
    "path",
    ["not json", '{"a": 1}', '[["fld", "", "x"]]', '[["../up", "", []]]', '[["fld", "", ["a b"]]]'],
)
def test_a_path_this_reading_did_not_write_is_refused(path: str) -> None:
    """`walk_path` reads back only the shape `next_page` writes, and refuses anything else rather
    than reading it as a shorter path. Its siblings are the passes above, whose saved paths are
    read back. Delete this and a damaged place reads as a walk near its end, which ends it and
    reports a tree read whole that was not."""
    with pytest.raises(DriveError):
        google_drive.walk_path({WALK_PATH: path})


def test_a_listing_names_the_folder_it_walked_to_and_its_rows_are_checked_against_it() -> None:
    """A page of a subfolder is checked against that subfolder: a row whose parent is the pin, on a
    page that listed a subfolder, means the query is not the one sent, and the page is refused.
    Its sibling is the walk above, where every row is its folder's. Delete this and a listing gone
    wrong keeps files from a folder the walk never reached."""
    listing = folder_listing(a_connection())
    asked = parse_qs(urlsplit(listing.url_for({WALK_FOLDER: "fldLevel001"})).query)
    assert asked["q"] == ["'fldLevel001' in parents and trashed = false"]
    with pytest.raises(DriveError):
        listing.project({"files": [a_child("fileTop0001", FOLDER_ID)]})
    with pytest.raises(DriveError):
        listing.url_for({WALK_FOLDER: "../other"})


def test_a_nested_file_is_read_live_only_when_its_folder_is_one_the_walk_found() -> None:
    """The live guard takes a file whose parent is a folder the walk kept as inside the tree, and
    one whose parent the walk did not keep as outside it. Delete this and either no file below the
    top level is ever read, or a file in a locked folder is."""
    nested = a_file(parents=["fldLevel001"])
    assert (
        withheld_from_a_read(a_connection(), *metadata(nested), frozenset({"fldLevel001"})) is None
    )
    assert withheld_from_a_read(a_connection(), *metadata(nested)) is Withheld.OUTSIDE


def test_the_folder_s_rows_carry_the_department_a_grant_is_scoped_by() -> None:
    """The stored predicate is the folder and its department, so a `read:drive_file` grant scoped to
    that department reaches the rows. Delete this and the rows carry no department, and a reader
    granted the folder's files in their department is refused every one."""
    clauses = {one.field: one.value for one in a_connection().visibility_predicate().clauses}
    assert clauses == {"folder_id": FOLDER_ID, "department": "operations"}
    assert google_drive.CONNECTOR.reading is not None


# ------------------------------------------------------------ a pass cut short
class EndlessTree:
    """Google as recorded answers over a tree with no bottom: every folder holds one file and one
    subfolder. The token endpoint answers; every listing is noted, with the folder it named."""

    def __init__(self) -> None:
        self.listings = 0
        self.folders: list[str] = []

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> Any:
        import json

        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        folder = parse_qs(urlsplit(url).query)["q"][0].split("'")[1]
        self.listings += 1
        self.folders.append(folder)
        body = {
            "files": [
                a_file(f"file{self.listings:07d}", parents=[folder]),
                a_file(f"fld{self.listings:08d}", parents=[folder], mimeType=FOLDER_MIME),
            ]
        }
        return SourceAnswer(status=200, headers={}, body=json.dumps(body).encode())

    def post(self, url: str, *, address: str, headers: Any, body: bytes, max_bytes: int) -> Any:
        import json

        from brain.ops.connector_sync_run import SourceAnswer

        del url, address, headers, body, max_bytes
        issued = {"access_token": "ya29.recorded", "token_type": "Bearer"}
        return SourceAnswer(status=200, headers={}, body=json.dumps(issued).encode())


@pytest.mark.needs_db
def test_a_pass_cut_short_by_its_bound_is_degraded_and_the_next_carries_on() -> None:
    """A tree deeper than one pass may walk is read to the worker's page bound and the attempt is
    recorded DEGRADED, read but cut short, rather than as a source read to the end; and the next
    pass starts at the folder the first did not reach, with the path the first saved, rather
    than at the pin (M11.9.15). Its sibling is the install check, whose tree is read to the end and
    is OK. Delete this and a folder too large for one pass reads as completely indexed, or is read
    from the pin on every pass and never past its first fifty folders."""
    from datetime import timedelta

    from brain.connectors.contract import HealthState
    from brain.connectors.manifest import manifest_digest
    from brain.ops.acceptance_checks_google import _KeyFiles, a_key_file
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections
    from brain.ops.connector_sync import MAX_PAGES_PER_ENTITY, READ_BUT_CUT_SHORT
    from brain.ops.connector_sync_run import sync_on
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_connector_sync_run import Resolver, a_database, no_sleep, through

    settings = {
        "folder": FOLDER_ID,
        "domain": OWN,
        "department": "operations",
        "steward": "u_steward",
    }
    digest = manifest_digest(manifest_for(google_drive.GOOGLE_DRIVE, settings))
    tree = EndlessTree()
    clock = iter(SEEN.replace(year=2026) + timedelta(seconds=n) for n in range(10_000))

    async def kept() -> datetime | None:
        return None

    with a_database("brain_drive_cut_short") as url:
        through(
            url,
            lambda sessions: StoredConnections(sessions).connect(
                connector=google_drive.GOOGLE_DRIVE,
                settings=settings,
                digest=digest,
                actor="u_admin",
                trace_id="t-connect",
                ent_hash="0" * 32,
                keep_key=kept,
            ),
        )
        at = SEEN.replace(year=2026)
        through(
            url,
            lambda sessions: sync_on(
                sessions=sessions,
                now=at,
                keys=_KeyFiles(a_key_file()),
                caller=tree,
                resolver=Resolver(),
                clock=lambda: next(clock),
                sleep=no_sleep,
                poster=tree,
            ),
        )
        ((health, detail),) = sql(url, "SELECT health, detail FROM ops.connector_sync")
        first = list(tree.folders)
        later = at + timedelta(days=1)
        through(
            url,
            lambda sessions: sync_on(
                sessions=sessions,
                now=later,
                keys=_KeyFiles(a_key_file()),
                caller=tree,
                resolver=Resolver(),
                clock=lambda: next(clock),
                sleep=no_sleep,
                poster=tree,
            ),
        )
        second = tree.folders[len(first) :]

    assert len(first) == MAX_PAGES_PER_ENTITY
    assert (health, detail) == (HealthState.DEGRADED.value, READ_BUT_CUT_SHORT)
    # Each listing names the next folder down, so the first the second pass lists is the one the
    # first pass queued last and never reached.
    assert first[0] == FOLDER_ID and second[0] == f"fld{MAX_PAGES_PER_ENTITY:08d}"
    assert len(second) == MAX_PAGES_PER_ENTITY and not set(first) & set(second)


class RecordedDrive(EndlessTree):
    """Google as recorded list pages (`recorded_pages`): each listing is answered by the page its
    folder and token name, and noted as that pair."""

    def __init__(self, pages: dict[tuple[str, str], dict[str, Any]]) -> None:
        super().__init__()
        self.pages = pages
        self.asked: list[tuple[str, str]] = []

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> Any:
        import json

        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        query = parse_qs(urlsplit(url).query)
        key = (query["q"][0].split("'")[1], query.get("pageToken", [""])[0])
        self.asked.append(key)
        return SourceAnswer(status=200, headers={}, body=json.dumps(self.pages[key]).encode())


@dataclass
class Synced:
    """What each pass of the worker left: its health and detail, its read state, and the index."""

    said: list[tuple[str, str]]
    walking: list[bool]
    held: dict[str, int]
    retired: int


def synced_over_passes(name: str, caller: RecordedDrive, *, passes: int) -> Synced:
    """Connect the pin and let the worker's own `sync_on` read it `passes` times, a day apart."""
    from datetime import timedelta

    from brain.connectors.manifest import manifest_digest
    from brain.ops.acceptance_checks_google import _KeyFiles, a_key_file
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections
    from brain.ops.connector_sync_run import sync_on
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_connector_sync_run import Resolver, a_database, no_sleep, through

    settings = {
        "folder": FOLDER_ID,
        "domain": OWN,
        "department": "operations",
        "steward": "u_steward",
    }
    digest = manifest_digest(manifest_for(google_drive.GOOGLE_DRIVE, settings))
    clock = iter(SEEN.replace(year=2026) + timedelta(seconds=n) for n in range(100_000))

    async def kept() -> datetime | None:
        return None

    said: list[tuple[str, str]] = []
    walking: list[bool] = []
    with a_database(name) as url:
        through(
            url,
            lambda sessions: StoredConnections(sessions).connect(
                connector=google_drive.GOOGLE_DRIVE,
                settings=settings,
                digest=digest,
                actor="u_admin",
                trace_id="t-connect",
                ent_hash="0" * 32,
                keep_key=kept,
            ),
        )

        def a_pass(at: datetime) -> Callable[[Any], Awaitable[Any]]:
            def run(sessions: Any) -> Awaitable[Any]:
                return sync_on(
                    sessions=sessions,
                    now=at,
                    keys=_KeyFiles(a_key_file()),
                    caller=caller,
                    resolver=Resolver(),
                    clock=lambda: next(clock),
                    sleep=no_sleep,
                    poster=caller,
                )

            return run

        for day in range(passes):
            through(url, a_pass(SEEN.replace(year=2026) + timedelta(days=day)))
            ((health, detail, state),) = sql(
                url,
                "SELECT health, detail, read_state FROM ops.connector_sync"
                " ORDER BY finished_at DESC LIMIT 1",
            )
            said.append((health, detail))
            walking.append(bool(state and state.get("walking")))
        held = dict(sql(url, "SELECT source_id, count(*) FROM proj.record GROUP BY source_id"))
        ((retired,),) = sql(url, "SELECT count(*) FROM proj.record_retired")
    return Synced(said=said, walking=walking, held=held, retired=retired)


@pytest.mark.needs_db
def test_the_worker_reads_a_tree_wider_than_a_pass_whole_and_then_forgets_its_place() -> None:
    """The recorded wide and deep tree through the worker and PostgreSQL: three passes are cut
    short and carried on, the fourth reads to the end and leaves no place, so the fifth starts again
    at the pin; every recorded page was asked once by the first four, and the index holds each file
    and folder once. Delete this and the place the walk saves can be dropped between the run and
    the store, which reads a large tree from the pin on every pass and never to its end."""
    from brain.connectors.contract import HealthState
    from brain.ops.connector_sync import READ_BUT_CUT_SHORT, READ_TO_THE_END

    pages = recorded_pages(wide_and_deep())
    drive = RecordedDrive(pages)
    done = synced_over_passes("brain_drive_depth_first", drive, passes=5)

    cut, whole = (
        (HealthState.DEGRADED.value, READ_BUT_CUT_SHORT),
        (
            HealthState.OK.value,
            READ_TO_THE_END,
        ),
    )
    assert done.said[:4] == [cut, cut, cut, whole]
    assert done.walking == [True, True, True, False, True]
    first_four = drive.asked[: len(pages)]
    assert sorted(first_four) == sorted(pages) and len(set(first_four)) == len(pages)
    assert drive.asked[len(pages)] == (FOLDER_ID, "")
    recorded = {row["id"] for body in pages.values() for row in body["files"]}
    assert set(done.held) == recorded and set(done.held.values()) == {1}


@pytest.mark.needs_db
def test_a_tree_deeper_than_the_bound_is_refused_in_words_on_connector_health() -> None:
    """A chain two deeper than `MAX_FOLDER_DEPTH` is read over three passes down to the bound; the
    pass that ends the walk says, on connector health, that part of the source was left out and
    why, rather than that it was read to the end, and nothing is retired. Delete this and a tree
    too deep to read reads as one read whole, and the files below the bound are retired from
    every answer."""
    from brain.connectors.contract import HealthState
    from brain.ops.connector_sync import READ_BUT_CUT_SHORT, READ_BUT_PART_LEFT_OUT

    tree = a_chain(FOLDER_ID, MAX_FOLDER_DEPTH + 2)
    drive = RecordedDrive(recorded_pages({folder: [rows] for folder, rows in tree.items()}))
    done = synced_over_passes("brain_drive_too_deep", drive, passes=3)

    cut = (HealthState.DEGRADED.value, READ_BUT_CUT_SHORT)
    assert done.said == [cut, cut, (HealthState.DEGRADED.value, READ_BUT_PART_LEFT_OUT)]
    assert done.walking == [True, True, False]
    assert len(drive.asked) == MAX_FOLDER_DEPTH + 1 and done.retired == 0
    assert f"filefldChain{MAX_FOLDER_DEPTH + 1:04d}" not in done.held
