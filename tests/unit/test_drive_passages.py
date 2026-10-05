"""A connected Drive folder on Ask: who is told a file's words, and what Drive is asked for them.

`brain.ops.drive_passages` over a recorded Google: a token endpoint, the metadata read and the two
ways a file's words are served. The index it reads is built by the worker's own reading from a raw
listing, so the rows are the ones a run would keep rather than rows written to suit the test.

Every date is far from any wall clock, and every domain is a reserved example.

Task ids: M11.6.7
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from brain.api_routes import A_NARROWED_QUESTION_READS_THE_LIBRARY_ALONE, model_lane_for
from brain.connectors.google_drive import (
    FILE,
    GOOGLE_DOC_MIME,
    GOOGLE_DRIVE,
    DriveReading,
    folder_listing,
)
from brain.connectors.google_token import GOOGLE_TOKEN_URL
from brain.connectors.manifest import manifest_digest
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.scope import Scope
from brain.gate.model_lane import DocumentSearchTool
from brain.knowledge.document_tools import KnowledgePassage
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.visibility import Visibility
from brain.ops.acceptance_checks_connectors import _Resolver
from brain.ops.acceptance_checks_google import _KeyFiles, a_key_file
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.drive_passages import (
    A_FILE_S_WORDS_ARE_TOLD_ONLY_TO_A_READER_OF_ITS_ROW,
    MAX_FILES_READ,
    READ_FILE,
    DrivePassages,
    WithDrive,
    candidates,
)
from brain.ops.model_service import ModelService

NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
FOLDER: Final = "fldPassages0001"
DEPARTMENT: Final = "operations"
SETTINGS: Final = {
    "folder": FOLDER,
    "domain": "company.example",
    "department": DEPARTMENT,
    "steward": "u_steward",
}


@dataclass
class RecordedDrive:
    """Google as recorded answers, noting every call by the file it named. No socket."""

    files: Mapping[str, Mapping[str, Any]]
    words: Mapping[str, str]
    tokens: int = 0
    metadata_read: list[str] = field(default_factory=list)
    words_read: list[str] = field(default_factory=list)

    def calls(self) -> int:
        return self.tokens + len(self.metadata_read) + len(self.words_read)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, headers, max_bytes
        parts = urlsplit(url)
        file_id = parts.path.removeprefix("/drive/v3/files/").removesuffix("/export")
        if parts.path.endswith("/export") or parse_qs(parts.query).get("alt") == ["media"]:
            self.words_read.append(file_id)
            return SourceAnswer(status=200, headers={}, body=self.words[file_id].encode())
        self.metadata_read.append(file_id)
        return SourceAnswer(status=200, headers={}, body=json.dumps(self.files[file_id]).encode())

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        del address, headers, body, max_bytes
        assert url == GOOGLE_TOKEN_URL
        self.tokens += 1
        issued = {"access_token": f"ya29.{secrets.token_hex(8)}", "token_type": "Bearer"}
        return SourceAnswer(status=200, headers={}, body=json.dumps(issued).encode())


def a_file(file_id: str, name: str, **overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": file_id,
        "name": name,
        "mimeType": GOOGLE_DOC_MIME,
        "modifiedTime": "2999-01-01T08:00:00.000Z",
        "headRevisionId": "rev1",
        "trashed": False,
        "parents": [FOLDER],
        "inheritedPermissionsDisabled": False,
    }
    raw.update(overrides)
    return raw


def index_of(*listed: dict[str, Any]) -> tuple[tuple[str, dict[str, Any]], ...]:
    """The index rows the worker's own reading keeps from this listing."""
    reading = DriveReading()
    listing = folder_listing(_drive())
    records = listing.records({"files": list(listed)}, fetched_at=NOW.isoformat())
    kept = [reading.projected(FILE, one.model_dump(), seen_at=NOW) for one in records.records]
    return tuple((one.source_id, dict(one.fields)) for one in kept if one is not None)


def _drive() -> Any:
    from brain.connectors.google_drive import DriveConnection

    return DriveConnection.from_settings(SETTINGS)


def a_connection(digest: str | None = None) -> Connection:
    agreed = manifest_digest(manifest_for(GOOGLE_DRIVE, SETTINGS))
    return Connection(
        connector=GOOGLE_DRIVE,
        settings=SETTINGS,
        digest=agreed if digest is None else digest,
        connected_by="u_admin",
        connected_at=NOW,
    )


def reader(department: str | None = DEPARTMENT) -> EntitlementSet:
    if department is None:
        return EntitlementSet(principal_id="u_reader")
    grant = Grant(capability=READ_FILE, scope=Scope.department(department))
    return EntitlementSet(principal_id="u_reader", grants=(grant,))


def passages_over(
    google: RecordedDrive,
    rows: Sequence[tuple[str, dict[str, Any]]],
    connection: Connection | None = None,
) -> DrivePassages:
    connected = a_connection() if connection is None else connection

    async def live() -> Connection | None:
        return connected

    async def indexed() -> Any:
        return tuple(rows)

    return DrivePassages(
        live,
        indexed,
        keys=_KeyFiles(a_key_file()),
        caller=google,
        poster=google,
        resolver=_Resolver(),
        clock=lambda: NOW,
    )


def ask(passages: DrivePassages, question: str, who: EntitlementSet) -> tuple[Any, ...]:
    found = asyncio.run(passages.passages(question, entitlement=who, now=NOW))
    return found.records


DOC = a_file("docQuarterly01", "Quarterly roster")
LOCKED = a_file("docLocked00001", "Salaries roster", inheritedPermissionsDisabled=True)
WORDS = {"docQuarterly01": "Mondays are staffed by two.", "docLocked00001": "Kept back."}


# ------------------------------------------------------------------ who is told
def test_a_reader_granted_the_folder_is_told_a_doc_s_words_read_when_asked() -> None:
    """The positive case: the asker holds `read:drive_file` in the folder's department, so the Doc
    whose name holds the question's word has its metadata read, then its words exported, under one
    token minted for the question; the passage is personal to the asker. Delete this and a guard
    that refuses everybody passes every test below."""
    google = RecordedDrive(files={"docQuarterly01": DOC}, words=WORDS)
    told = ask(passages_over(google, index_of(DOC)), "Who is on the quarterly?", reader())

    assert [(one.title, one.document) for one in told] == [
        ("Quarterly roster", "Mondays are staffed by two.")
    ]
    assert (told[0].owner_id, told[0].visibility) == ("u_reader", Visibility.PERSONAL.value)
    assert (google.tokens, google.metadata_read, google.words_read) == (
        1,
        ["docQuarterly01"],
        ["docQuarterly01"],
    )


@pytest.mark.parametrize("department", [None, "sales"])
def test_a_reader_without_the_folder_s_grant_is_told_what_nothing_tells_them(
    department: str | None,
) -> None:
    """`A_FILE_S_WORDS_ARE_TOLD_ONLY_TO_A_READER_OF_ITS_ROW`: a reader with no `read:drive_file`,
    and one holding it in another department, are handed exactly what a question about no file hands
    them, and Drive is asked nothing, not even for a token. Delete this and a file's words reach
    whoever asks for it by name."""
    google = RecordedDrive(files={"docQuarterly01": DOC}, words=WORDS)
    passages = passages_over(google, index_of(DOC))

    refused = ask(passages, "Who is on the quarterly?", reader(department))
    nothing = ask(passages, "Who is on the vanished?", reader(department))

    assert refused == nothing == ()
    assert google.calls() == 0
    assert "read:drive_file" in A_FILE_S_WORDS_ARE_TOLD_ONLY_TO_A_READER_OF_ITS_ROW


def test_a_file_locked_since_it_was_listed_is_looked_at_and_never_read() -> None:
    """A file listed when its inherited permissions were on and switched off since is matched in the
    index, its metadata read live, and its words never asked for; its sibling the Doc beside it is
    read. (A file locked when it is listed is not kept at all.) Delete this and a file somebody
    kept to fewer people than the folder reaches since the last pass is told to the department."""
    listed_open = {**LOCKED, "inheritedPermissionsDisabled": False}
    google = RecordedDrive(files={"docLocked00001": LOCKED, "docQuarterly01": DOC}, words=WORDS)
    told = ask(passages_over(google, index_of(DOC, listed_open)), "Show the roster", reader())

    assert [one.title for one in told] == ["Quarterly roster"]
    assert sorted(google.metadata_read) == ["docLocked00001", "docQuarterly01"]
    assert google.words_read == ["docQuarterly01"]


def test_a_file_in_a_subfolder_the_walk_found_is_read_and_one_in_a_locked_one_is_not() -> None:
    """A Doc whose parent is a subfolder the walk kept is read like one in the pin; a Doc whose
    parent is a folder the walk did not keep (it was locked narrower than its parent) is passed
    over after its metadata says so. Delete this and either nothing below the top level is read,
    or a file in a locked subfolder is."""
    sub = a_file("fldLevel00001", "Level", mimeType="application/vnd.google-apps.folder")
    nested = a_file("docNested0001", "Nested roster", parents=["fldLevel00001"])
    hidden = a_file("docHidden0001", "Hidden roster", parents=["fldLocked0001"])
    files = {"docNested0001": nested, "docHidden0001": hidden}
    words = {"docNested0001": "Nested words.", "docHidden0001": "Hidden words."}
    google = RecordedDrive(files=files, words=words)
    rows = (
        *index_of(sub, {**nested, "parents": [FOLDER]}),
        *index_of({**hidden, "parents": [FOLDER]}),
    )

    told = ask(passages_over(google, rows), "Show the roster", reader())

    assert [one.document for one in told] == ["Nested words."]
    assert google.words_read == ["docNested0001"]


def test_a_file_shown_as_shared_outside_is_never_read_listed_or_live() -> None:
    """A file the index lists as shared outside the company is passed over before any call, and
    one Drive shows as shared by link now, though the index had nothing, has its metadata read and
    not its words. Delete this and a file sent to a client is told to the department."""
    outside = a_file("docOutside0001", "Client roster", permissions=[{"type": "anyone"}])
    linked_now = a_file("docLinked00001", "Linked roster")
    shown_now = {**linked_now, "permissions": [{"type": "anyone"}]}
    google = RecordedDrive(files={"docLinked00001": shown_now}, words=WORDS)

    told = ask(passages_over(google, index_of(outside, linked_now)), "Show the roster", reader())

    assert told == ()
    assert google.metadata_read == ["docLinked00001"]
    assert google.words_read == []


def test_a_connection_whose_declaration_changed_is_not_read() -> None:
    """A folder connected under another declaration is read by nothing until it is agreed again,
    as the worker's schedule refuses it; its sibling is the first test, whose digest is today's.
    Delete this and a changed connector reads under terms nobody agreed to."""
    google = RecordedDrive(files={"docQuarterly01": DOC}, words=WORDS)
    changed = passages_over(google, index_of(DOC), a_connection(digest="0" * 64))

    assert ask(changed, "Who is on the quarterly?", reader()) == ()
    assert google.calls() == 0


def test_a_question_with_no_word_to_match_or_no_folder_asks_nothing() -> None:
    """Words of three letters or fewer match no name, and an install with no Drive connection has
    no folder to read; each is answered with nothing and no call. Delete this and a question of
    short words reads every file whose name holds "the"."""
    google = RecordedDrive(files={"docQuarterly01": DOC}, words=WORDS)
    assert ask(passages_over(google, index_of(DOC)), "Who is it?", reader()) == ()

    async def none() -> Connection | None:
        return None

    async def indexed() -> Any:
        return index_of(DOC)

    nowhere = DrivePassages(
        none,
        indexed,
        keys=_KeyFiles(a_key_file()),
        caller=google,
        poster=google,
        resolver=_Resolver(),
        clock=lambda: NOW,
    )
    assert ask(nowhere, "Who is on the quarterly?", reader()) == ()
    assert google.calls() == 0


# ------------------------------------------------------------------ what is matched
def test_a_name_is_matched_by_the_lark_wiki_s_rule_for_its_titles() -> None:
    """One rule for matching a question to a name, the Wiki's: words of four letters or more, and
    runs of two or more characters outside the Latin alphabet. Delete this and Drive can grow a
    second copy of it that drifts, and "is" matches every file named in English."""
    from brain.ops import drive_passages, lark_wiki_live

    assert vars(drive_passages)["words_of"] is lark_wiki_live.words_of
    asked = "Who is on the Quarterly roster, the ROSTER?"
    assert lark_wiki_live.words_of(asked) == ("quarterly", "roster")


def test_candidates_are_the_folder_s_readable_files_best_matched_first_and_few() -> None:
    """A row of another folder, a file with no words and a file shared outside are passed over,
    the rest ranked by how many words their names hold, and no more than `MAX_FILES_READ` kept.
    Delete this and one question reads the whole folder."""
    rows = index_of(
        a_file("docA000000001", "Roster week one"),
        a_file("docB000000002", "Roster week two quarterly"),
        a_file("docC000000003", "Roster pdf", mimeType="application/pdf"),
        a_file("docD000000004", "Roster outside", permissions=[{"type": "anyone"}]),
        *(a_file(f"docE00000000{n}", f"Roster {n}") for n in range(5, 9)),
    )
    other = ("docF000000009", {**rows[0][1], "folder_id": "fldAnother0001"})
    found = candidates((*rows, other), _drive(), ("roster", "quarterly"))

    assert found[0].file_id == "docB000000002"
    assert len(found) == MAX_FILES_READ
    assert {"docC000000003", "docD000000004", "docF000000009"}.isdisjoint(
        one.file_id for one in found
    )


# ------------------------------------------------------------------ beside the library
@dataclass
class Library:
    said: tuple[KnowledgePassage, ...] = ()

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        del question, entitlement
        return TypedResult[KnowledgePassage](
            records=self.said, source="knowledge", fetched_at=now.isoformat()
        )


def test_drive_s_passages_come_after_the_library_s_and_the_library_stays_reachable() -> None:
    """`WithDrive`: the library's passages first, then the folder's; `library` is the search it was
    put beside. Delete this and a Drive passage can crowd the company's own documents out of the
    prompt, or a narrowed question lose the library under the wrapper."""
    own = KnowledgePassage(entity="knowledge", id="k1", document_id="k1", document="Our policy.")
    library = Library(said=(own,))
    google = RecordedDrive(files={"docQuarterly01": DOC}, words=WORDS)
    both = WithDrive(library, passages_over(google, index_of(DOC)))

    found = asyncio.run(both.passages("Who is on the quarterly?", entitlement=reader(), now=NOW))

    assert [one.document for one in found.records] == ["Our policy.", "Mondays are staffed by two."]
    assert both.library is library


def test_a_narrowed_question_reads_the_library_alone() -> None:
    """`A_NARROWED_QUESTION_READS_THE_LIBRARY_ALONE`: with Drive beside the library, a question
    narrowed to kinds is handed the library narrowed and not Drive; unnarrowed, it is handed both.
    Delete this and a question narrowed to FAQs is shown a Drive file's words."""
    from tests.unit.test_model_calls import Ladder, executor

    calls, _ = executor(Ladder(()), {})
    owned = httpx.Client()
    try:

        async def handler(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError

        library = DocumentSearchTool(handler=handler)
        state = SimpleNamespace(
            models=ModelService(calls=calls, client=owned),
            passage_search=library,
            db_sessions=object(),
        )
        narrowed = model_lane_for(state, None, None, kinds=(KnowledgeKind.FAQ,))  # type: ignore[arg-type]
        whole = model_lane_for(state, None, None)  # type: ignore[arg-type]

        assert narrowed is not None and whole is not None
        assert narrowed.search == DocumentSearchTool(handler=handler, kinds=(KnowledgeKind.FAQ,))
        assert isinstance(whole.search, WithDrive) and whole.search.library is library
        assert "Google Drive" in A_NARROWED_QUESTION_READS_THE_LIBRARY_ALONE
    finally:
        owned.close()


def test_the_capability_is_the_one_the_folder_s_rows_are_granted_by() -> None:
    """`read:drive_file` is the row plane's capability for Drive's entity, so the grant a data
    steward writes for the folder's rows is the one that admits its words. Delete this and the two
    could drift apart, and a reader granted the rows be refused the words or the reverse."""
    from brain.knowledge.rows import entity_capability

    assert Capability(value=entity_capability(FILE).value) == READ_FILE


def test_a_narrowed_question_unwraps_the_wiki_and_drive_to_the_library() -> None:
    """`narrowed_to` with both live sources beside the library, as an install with the Wiki on and
    a folder connected has: the narrowed search is the library's, and a search that wraps no
    library is handed back. Delete this and, with the Wiki switched on, a question narrowed to FAQs
    is shown every kind, which main did until 2026-10-05 because `WithWiki` named no library."""
    from typing import cast

    from brain.api_routes import narrowed_to
    from brain.ops.lark_wiki_live import WikiPassages, WithWiki

    async def handler(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError

    library = DocumentSearchTool(handler=handler)
    google = RecordedDrive(files={}, words={})
    wrapped = WithDrive(WithWiki(library, cast(WikiPassages, object())), passages_over(google, ()))

    narrowed = narrowed_to(wrapped, (KnowledgeKind.FAQ,))
    assert narrowed == DocumentSearchTool(handler=handler, kinds=(KnowledgeKind.FAQ,))
    lone = Library()
    assert narrowed_to(lone, (KnowledgeKind.FAQ,)) is lone
