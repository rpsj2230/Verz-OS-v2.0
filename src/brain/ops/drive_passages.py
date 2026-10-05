"""A connected Google Drive folder on Ask: its files' words, read live for each question.

`brain.connectors.google_drive` holds every rule about the folder: the listing the worker keeps a
minimal index from, the verdict a file's sharing reduces to, and what may stop a file's words being
read. No process asked Drive for a word. This is the application's half, in the shape the Lark
Wiki's and Slack's passages take: for each question it finds the connected folder's files whose
names hold the question's words in the index, reads each one's metadata from Drive to check it
again, reads the words of those that pass, and hands them to the answer lane's model step as
passages.

**Two gates before Drive is asked anything.** The asker must hold `read:file` in the department
the folder was connected for, which is the grant the folder's index rows are judged by, and the
question must hold a word a file's name can be matched on, by the Lark Wiki's rule for its titles
(`brain.ops.lark_wiki_live.words_of`). Either missing is answered with no
passage and no call, which is exactly what a person asking about a file that is not there is told.
See `A_FILE_S_WORDS_ARE_TOLD_ONLY_TO_A_READER_OF_ITS_ROW`.

**Each file is checked again, live, before a word of it is read.** The index is up to an hour old,
so the file's metadata is read from Drive first and `google_drive.withheld_from_a_read` decides on
what Drive says now: a file moved out of the folder, put in the bin, locked narrower than its
folder, or shown as shared by link or outside the company is not read. Which of those it was is
logged for an operator by its kind, never by the file, and the asker is told what a missing file
tells them.

**A passage is personal to its asker.** It is tagged with the asker as its owner at the personal
level, as Slack's passages are, so the passage policy tells it to the person whose grant admitted
it and to nobody else if the answer is shown again. A department tag would admit whoever may read
that department's knowledge, which is a different grant from `read:file`.

**Nothing is kept.** The words are passages for one question: not written to a table, not
embedded, not logged. The index this reads holds names, types, dates and verdicts, never a word of
a file (`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`).

**One token per question.** The service account's key file is leased for the question and
exchanged for a token carrying `drive.readonly` alone (`brain.ops.connector_sync_run.presented`),
which lives as long as the read; the key file is never sent.

Rejected: matching the question against the files' words rather than their names. It needs every
file's words read first, which is the bulk read the owner's rule forbids, on every question.
Rejected: reading more than `MAX_FILES_READ` files. Each is two calls while the asker waits, and a
question naming a file by its name is answered from the few whose names hold its words.

Task ids: M11.6.7
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors import google_drive
from brain.connectors.contract import ConnectorContractError
from brain.connectors.google_drive import (
    GOOGLE_DRIVE,
    MAX_TEXT_BYTES,
    DriveConnection,
    DriveReading,
    Endpoint,
    SharingState,
    metadata_url_for,
    operation_for,
    sharing_admits_a_read,
    sharing_of,
    text_url_for,
    withheld_from_a_read,
    words_of_a_body,
)
from brain.connectors.google_token import TokenNotIssuedError
from brain.connectors.live_read import LIVE_READ_TIMEOUT_MS
from brain.connectors.manifest import manifest_digest
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.core.entitlement import Capability
from brain.core.envelope import TypedResult
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage
from brain.knowledge.visibility import Visibility
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.connector_sync_run import (
    HttpsSourceCaller,
    WorkerConnectorKeys,
    call_headers,
    presented,
)
from brain.ops.lark_wiki_live import words_of
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.webhook_delivery import SystemResolver
from brain.tables.projection import ProjectedRecordRow
from brain.tools.fetch import Resolver, UnsafeAddressError, assert_fetchable

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.ops.connector_sync_run import (
        ConnectorKeys,
        RunTokenVault,
        SourceCaller,
        SourcePoster,
    )

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a file's words reach only a reader of the folder's rows.
A_FILE_S_WORDS_ARE_TOLD_ONLY_TO_A_READER_OF_ITS_ROW: Final = (
    "A connected folder's files are indexed as rows of `file`, each carrying the department the "
    "folder was connected for, and a grant of read:file scoped to that department is what reaches "
    "them. A file's words are read for a question only when the asker holds that grant; anybody "
    "else is answered with no passage and no call to Drive, as though the folder held nothing on "
    "the subject."
)

# ------------------------------------------------------------------------ the figures
#: The capability a person needs to be told a connected folder's files.
READ_FILE: Final = Capability(value=f"read:{google_drive.FILE}")

#: The most files whose words are read for one question.
MAX_FILES_READ: Final = 3

#: The one reading whose token and headers a question's calls use.
READING: Final = DriveReading()

#: What an index read hands back: each file's id and the fields its row keeps.
type Indexed = Callable[[], Awaitable[tuple[tuple[str, Mapping[str, Any]], ...]]]


@dataclass(frozen=True)
class Candidate:
    """An indexed file whose name holds some of the question's words."""

    file_id: str
    name: str
    hits: int


def candidates(
    rows: Iterable[tuple[str, Mapping[str, Any]]],
    drive: DriveConnection,
    words: Sequence[str],
) -> tuple[Candidate, ...]:
    """The folder's indexed files worth reading for these words, best first, and few of them.

    A row of another folder, one whose verdict `sharing_admits_a_read` refuses and one whose type
    has no words to read are passed over here, before any call; each is checked again live.
    """
    found: list[Candidate] = []
    for file_id, fields in rows:
        if fields.get("folder_id") != drive.folder_id:
            continue
        try:
            sharing = SharingState(str(fields.get("sharing_state", "")))
            readable = text_url_for(file_id, str(fields.get("mime_type", ""))) is not None
        except (ValueError, ConnectorContractError):
            continue
        if not readable or not sharing_admits_a_read(sharing):
            continue
        name = str(fields.get("name", ""))
        folded = name.casefold()
        hits = sum(1 for word in words if word in folded)
        if hits:
            found.append(Candidate(file_id=file_id, name=name, hits=hits))
    found.sort(key=lambda one: (-one.hits, one.name, one.file_id))
    return tuple(found[:MAX_FILES_READ])


@dataclass(frozen=True)
class DriveText:
    """One file's words, read for one question and kept nowhere."""

    file_id: str
    name: str
    modified_at: str
    words: str = ""


def _empty(now: datetime) -> TypedResult[KnowledgePassage]:
    return TypedResult[KnowledgePassage](
        records=(), source=GOOGLE_DRIVE, fetched_at=now.isoformat()
    )


class DrivePassages:
    """`brain.gate.model_lane.PassageSearch` over the connected folder, read live per question."""

    def __init__(
        self,
        connected: Callable[[], Awaitable[Connection | None]],
        indexed: Indexed,
        *,
        keys: ConnectorKeys,
        caller: SourceCaller,
        poster: SourcePoster,
        resolver: Resolver,
        clock: Callable[[], datetime],
    ) -> None:
        self._connected = connected
        self._indexed = indexed
        self._keys = keys
        self._caller = caller
        self._poster = poster
        self._resolver = resolver
        self._clock = clock

    def __repr__(self) -> str:
        return "DrivePassages()"

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        words = words_of(question)
        connection = await self._connected()
        if not words or connection is None:
            return _empty(now)
        try:
            drive = DriveConnection.from_settings(connection.settings)
        except ConnectorContractError:
            return _empty(now)
        # See A_FILE_S_WORDS_ARE_TOLD_ONLY_TO_A_READER_OF_ITS_ROW.
        scope = entitlement.scope_for(READ_FILE, now)
        row = {"folder_id": drive.folder_id, "department": drive.department}
        if scope is None or not scope.matches(row):
            return _empty(now)
        found = candidates(await self._indexed(), drive, words)
        if not found:
            return _empty(now)
        read = await asyncio.to_thread(self.read, connection, drive, found)
        told = tuple(
            KnowledgePassage(
                entity=KNOWLEDGE_ENTITY,
                id=f"google-drive-{one.file_id}",
                document_id=f"google-drive-{one.file_id}",
                title=one.name,
                document=one.words,
                updated_at=one.modified_at or now.isoformat(),
                visibility=Visibility.PERSONAL.value,
                owner_id=entitlement.principal_id,
            )
            for one in read
            if one.words.strip()
        )
        return TypedResult[KnowledgePassage](
            records=told, source=GOOGLE_DRIVE, fetched_at=now.isoformat()
        )

    def read(
        self, connection: Connection, drive: DriveConnection, found: Sequence[Candidate]
    ) -> tuple[DriveText, ...]:
        """Each candidate checked live and its words read, under one token for the question.

        A connection whose declaration changed since it was agreed is not read, as a scheduled read
        of it is not (`brain.ops.connector_sync.plan_for`). A call that fails passes that file
        over and goes on; the failure is logged by its kind.
        """
        try:
            manifest = manifest_for(GOOGLE_DRIVE, connection.settings)
        except (NotConnectableError, ConnectorContractError):
            log.warning("google_drive.unread", why="settings")
            return ()
        if manifest_digest(manifest) != connection.digest:
            log.warning("google_drive.unread", why="declaration changed")
            return ()
        lease = self._keys.lease(manifest.credential.ref, now=self._clock())
        try:
            try:
                key = lease.key()
            except SecretsUnavailableError:
                log.warning("google_drive.unread", why="no key")
                return ()
            try:
                token = presented(
                    READING, key, poster=self._poster, resolver=self._resolver, now=self._clock()
                )
            except (TokenNotIssuedError, UnsafeAddressError):
                log.warning("google_drive.unread", why="no token")
                return ()
            headers = call_headers(READING, connection.settings, token)
            read: list[DriveText] = []
            for one in found:
                checked = self._metadata(drive, one.file_id, headers)
                if checked is None:
                    continue
                row, sharing = checked
                withheld = withheld_from_a_read(drive, row, sharing)
                if withheld is not None:
                    log.info("google_drive.withheld", reason=withheld.value)
                    continue
                body = self._words(one.file_id, str(row.get("mime_type", "")), headers)
                if body is None:
                    continue
                read.append(
                    DriveText(
                        file_id=one.file_id,
                        name=str(row.get("name", one.name)),
                        modified_at=str(row.get("modified_at", "")),
                        words=words_of_a_body(body),
                    )
                )
            return tuple(read)
        finally:
            lease.close(self._clock())

    def _metadata(
        self, drive: DriveConnection, file_id: str, headers: Mapping[str, str]
    ) -> tuple[Mapping[str, Any], SharingState] | None:
        """The file's metadata as Drive gives it now, and its sharing verdict, or None."""
        try:
            checked = assert_fetchable(metadata_url_for(file_id), self._resolver)
        except (UnsafeAddressError, ConnectorContractError):
            log.warning("google_drive.unread", why="address")
            return None
        answer = self._caller.get(
            checked.url, address=checked.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
        )
        if answer.status != 200:
            log.warning("google_drive.unread", why=f"metadata {answer.status or 'no answer'}")
            return None
        try:
            body = json.loads(answer.body)
            (row,) = operation_for(Endpoint.GET_FILE).project(body)
        except (ValueError, ConnectorContractError):
            log.warning("google_drive.unread", why="metadata shape")
            return None
        permissions = body.get("permissions") if isinstance(body, Mapping) else None
        return row, sharing_of(permissions, domain=drive.domain)

    def _words(self, file_id: str, mime_type: str, headers: Mapping[str, str]) -> bytes | None:
        """The file's words as Drive serves them, or None when there are none to read."""
        url = text_url_for(file_id, mime_type)
        if url is None:
            return None
        try:
            checked = assert_fetchable(url, self._resolver)
        except UnsafeAddressError:
            log.warning("google_drive.unread", why="address")
            return None
        asked = {"Authorization": headers["Authorization"], "Accept": "*/*"}
        answer = self._caller.get(
            checked.url, address=checked.address, headers=asked, max_bytes=MAX_TEXT_BYTES
        )
        if answer.status != 200 or not answer.body:
            log.warning("google_drive.unread", why=f"words {answer.status or 'no answer'}")
            return None
        return answer.body


class WithDrive:
    """`PassageSearch` over another search and the Drive folder: the other's passages first."""

    def __init__(self, first: Any, drive: DrivePassages) -> None:
        self._first = first
        self._drive = drive

    @property
    def library(self) -> Any:
        """The search Drive was put beside, which a question narrowed to kinds reads alone."""
        return self._first

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        own = await self._first.passages(question, entitlement=entitlement, now=now)
        more = await self._drive.passages(question, entitlement=entitlement, now=now)
        return TypedResult[KnowledgePassage](
            records=(*own.records, *more.records),
            source=own.source,
            fetched_at=own.fetched_at,
            truncated=own.truncated,
        )


# ------------------------------------------------------------------------ the wiring
async def indexed_files(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Every live index row of a Drive file, as (file id, fields)."""
    async with sessions() as session:
        rows = await session.execute(
            select(ProjectedRecordRow.source_id, ProjectedRecordRow.fields).where(
                ProjectedRecordRow.source == GOOGLE_DRIVE,
                ProjectedRecordRow.entity == google_drive.FILE,
                ProjectedRecordRow.deleted_at.is_(None),
            )
        )
        return tuple((str(one), dict(fields)) for one, fields in rows.all())


def _utc_now() -> datetime:
    return datetime.now(UTC)


def drive_passages_for(
    sessions: async_sessionmaker[AsyncSession] | None, vault: RunTokenVault | None
) -> DrivePassages | None:
    """Drive's passages for the answer lane's model step, or None with no database.

    The connection is read from the database on each question, so a folder connected or
    disconnected on the Connectors screen is read or not from the next one, and a process with no
    Drive connection asks Drive nothing.
    """
    if sessions is None:
        return None
    stored = StoredConnections(sessions)

    async def connected() -> Connection | None:
        return next(
            (one for one in await stored.connected() if one.connector == GOOGLE_DRIVE), None
        )

    async def indexed() -> tuple[tuple[str, Mapping[str, Any]], ...]:
        return await indexed_files(sessions)

    caller = HttpsSourceCaller(timeout_seconds=LIVE_READ_TIMEOUT_MS / 1000)
    return DrivePassages(
        connected,
        indexed,
        keys=WorkerConnectorKeys(vault),
        caller=caller,
        poster=caller,
        resolver=SystemResolver(),
        clock=_utc_now,
    )
