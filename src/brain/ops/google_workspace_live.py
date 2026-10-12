"""A connected Google Workspace on Ask: the asker's own mail, calendar and documents, read as them.

`brain.connectors.google_workspace` holds every rule about reading Workspace; this is the
application's half. For each question it renews the asker's own access from the refresh token their
own consent bought (`brain.ops.connector_sync_run.personal_access`, which leases their slot and no
other), reads the chosen services' matches with it, and hands what it found to the answer lane's
model step as passages told to the asker alone. See
`brain.connectors.google_workspace.A_PERSONS_WORKSPACE_IS_READ_AS_THEM_FOR_THEM`.

**Nothing is kept.** The messages, events and documents are passages for one question: not
written to a table, not embedded, not logged. The connection keeps no index of anybody's account.

**Two gates before Google is asked anything.** The asker must hold `read:google_workspace` in the
department the connection answers to, and must have connected their own account; either missing
is answered with no passage and no call to Google, which is what an asker is told when their
account holds nothing on the subject. A consent the vendor withdrew is the one thing said in
words, to that asker, as a passage of its own (`brain.connectors.oauth.YOUR_CONSENT_WITHDRAWN`):
their reads are down and nobody else's are.

**Only the chosen services are called.** A service the connection did not choose has no scope in
anybody's consent and is not asked here either. See
`brain.connectors.google_workspace.A_SERVICE_NOT_CHOSEN_IS_NEVER_CALLED`.

**A passage is personal to its asker.** Each is tagged with the asker as its owner at the
personal level, so the passage policy tells it to them and to nobody else, even if the answer is
shown again.

Task ids: M11.7.6
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import structlog

from brain.connectors import google_workspace as gws
from brain.connectors.contract import ConnectorContractError
from brain.connectors.google_token import TokenNotIssuedError
from brain.connectors.oauth import ConsentWithdrawnError
from brain.connectors.rest import MAX_RESPONSE_BYTES, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.core.entitlement import Capability
from brain.core.envelope import TypedResult
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage
from brain.knowledge.visibility import Visibility
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.connector_sync_run import (
    HttpsSourceCaller,
    WorkerConnectorKeys,
    personal_access,
    personal_words,
)
from brain.ops.lark_wiki_live import words_of
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.webhook_delivery import SystemResolver
from brain.tools.fetch import Resolver, UnsafeAddressError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from brain.core.entitlement import EntitlementSet
    from brain.ops.connector_sync_run import (
        ConnectorKeys,
        RunTokenVault,
        SourceCaller,
        SourcePoster,
    )

log = structlog.get_logger()

#: `personal_access` is named here so the install check's test can stand a broken one in for it.
__all__ = ["READ_WORKSPACE", "WorkspacePassages", "personal_access", "workspace_passages_for"]

#: The capability a person needs, in the connection's department, to be read anything.
READ_WORKSPACE: Final = Capability(value=gws.READER)

#: How long one call to Google may take while a person waits for an answer.
TIMEOUT_SECONDS: Final = 10.0

#: What a withdrawn consent's passage is titled.
WITHDRAWN_TITLE: Final = "Your Google Workspace account"


def _empty(now: datetime) -> TypedResult[KnowledgePassage]:
    return TypedResult[KnowledgePassage](
        records=(), source=gws.CONNECTOR_NAME, fetched_at=now.isoformat()
    )


class WorkspacePassages:
    """`brain.gate.model_lane.PassageSearch` over the connected Workspace, read per question as the
    asker, with their own consent."""

    def __init__(
        self,
        connected: Callable[[], Awaitable[Connection | None]],
        *,
        keys: ConnectorKeys,
        caller: SourceCaller,
        poster: SourcePoster,
        resolver: Resolver,
        clock: Callable[[], datetime],
    ) -> None:
        self._connected = connected
        self._keys = keys
        self._caller = caller
        self._poster = poster
        self._resolver = resolver
        self._clock = clock

    def __repr__(self) -> str:
        return "WorkspacePassages()"

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        words = words_of(question)
        connection = await self._connected()
        if not words or connection is None:
            return _empty(now)
        try:
            chosen = gws.WorkspaceConnection.from_settings(connection.settings)
        except ConnectorContractError:
            return _empty(now)
        scope = entitlement.scope_for(READ_WORKSPACE, now)
        if scope is None or not scope.matches({"department": chosen.department}):
            return _empty(now)
        me = entitlement.principal_id
        found = await asyncio.to_thread(self.read, connection, chosen, me, words)
        told = tuple(
            KnowledgePassage(
                entity=KNOWLEDGE_ENTITY,
                id=f"{one.entity}-{one.item_id}",
                document_id=f"{one.entity}-{one.item_id}",
                title=one.title,
                section=one.when,
                document=one.text[: gws.PASSAGE_CHARS],
                updated_at=one.when or now.isoformat(),
                visibility=Visibility.PERSONAL.value,
                owner_id=me,
            )
            for one in found
        )
        return TypedResult[KnowledgePassage](
            records=told, source=gws.CONNECTOR_NAME, fetched_at=now.isoformat()
        )

    def read(
        self,
        connection: Connection,
        chosen: gws.WorkspaceConnection,
        principal_id: str,
        words: Sequence[str],
    ) -> tuple[gws.Found, ...]:
        """What the asker's own account holds on the words, read with their own access.

        One renewal for the question. A person with no consent of their own is read nothing; a
        withdrawn one is said to them as the one passage; a call that fails ends that service's
        reading and the others still answer.
        """
        try:
            access = personal_access(
                gws.CONSENT,
                connector=gws.CONNECTOR_NAME,
                principal_id=principal_id,
                settings=connection.settings,
                keys=self._keys,
                poster=self._poster,
                resolver=self._resolver,
                now=self._clock(),
            )
        except ConsentWithdrawnError as withdrawn:
            said = personal_words(withdrawn)
            return (gws.Found(gws.MAIL, "consent", WITHDRAWN_TITLE, "", said),)
        except (
            TokenNotIssuedError,
            SecretsUnavailableError,
            UnsafeAddressError,
            ConnectorContractError,
        ) as refused:
            log.info("workspace.unread", why=type(refused).__name__)
            return ()
        headers = {"Authorization": f"Bearer {access.value}"}
        found: list[gws.Found] = []
        if gws.Service.MAIL in chosen.services:
            found.extend(self._mail(headers, words))
        if gws.Service.CALENDAR in chosen.services:
            found.extend(self._events(headers, words))
        if gws.Service.DOCUMENTS in chosen.services:
            found.extend(self._documents(headers, words))
        return tuple(found)

    # --------------------------------------------------------------- the three services
    def _mail(self, headers: Mapping[str, str], words: Sequence[str]) -> list[gws.Found]:
        listing = gws.messages_operation()
        body = self._json(listing, gws.mail_query(words), headers)
        if body is None:
            return []
        found = []
        reading = gws.message_operation()
        for ident in gws.message_ids(listing, body):
            one = self._json(reading, {"id": ident, "format": "metadata"}, headers)
            if one is None:
                break
            row = gws.message_row(reading, one)
            message = None if row is None else gws.message_found(row)
            if message is not None:
                found.append(message)
        return found

    def _events(self, headers: Mapping[str, str], words: Sequence[str]) -> list[gws.Found]:
        listing = gws.events_operation()
        body = self._json(listing, gws.event_query(words), headers)
        return [] if body is None else list(gws.events_found(listing, body))

    def _documents(self, headers: Mapping[str, str], words: Sequence[str]) -> list[gws.Found]:
        listing = gws.files_operation()
        body = self._json(listing, gws.document_query(words), headers)
        if body is None:
            return []
        found = []
        for ident, name, modified in gws.documents_listed(listing, body):
            text = self._text(
                gws.export_operation(), {"id": ident, "mimeType": "text/plain"}, headers
            )
            if text is None:
                break
            one = gws.document_found(ident, name, modified, text, words)
            if one is not None:
                found.append(one)
        return found

    # --------------------------------------------------------------- one call
    def _get(
        self,
        operation: RestOperation,
        arguments: Mapping[str, str],
        headers: Mapping[str, str],
        max_bytes: int,
    ) -> bytes | None:
        """One call's answered body, or None for any failure, which is logged by its kind."""
        try:
            checked = operation.prepare(arguments, resolver=self._resolver)
        except (ConnectorContractError, UnsafeAddressError):
            log.info("workspace.unread", why="address or shape")
            return None
        answer = self._caller.get(
            checked.url, address=checked.address, headers=headers, max_bytes=max_bytes
        )
        call = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed or answer.status is None,
        )
        if call is not CallOutcome.OK:
            log.info("workspace.unread", why=call.value)
            return None
        return answer.body

    def _json(
        self, operation: RestOperation, arguments: Mapping[str, str], headers: Mapping[str, str]
    ) -> Any:
        raw = self._get(operation, arguments, headers, MAX_RESPONSE_BYTES)
        if raw is None:
            return None
        try:
            return gws.answered(200, json.loads(raw))
        except (ValueError, ConnectorContractError):
            log.info("workspace.unread", why="not json")
            return None

    def _text(
        self, operation: RestOperation, arguments: Mapping[str, str], headers: Mapping[str, str]
    ) -> str | None:
        raw = self._get(operation, arguments, headers, gws.MAX_EXPORT_BYTES)
        return None if raw is None else raw.decode("utf-8", errors="replace")


def workspace_passages_for(
    sessions: async_sessionmaker[AsyncSession] | None, vault: RunTokenVault | None
) -> WorkspacePassages | None:
    """Workspace's passages for the answer lane's model step, or None with no database.

    The connection is read from the database on each question, so a Workspace connected or
    disconnected on the Connectors screen is read or not from the next one, and a process with no
    Workspace connection asks Google nothing. The vault is the application's own, which may mint
    the role a person's slot is read under and no process with nobody present may.
    """
    if sessions is None:
        return None
    stored = StoredConnections(sessions)

    async def connected() -> Connection | None:
        return next(
            (one for one in await stored.connected() if one.connector == gws.CONNECTOR_NAME), None
        )

    caller = HttpsSourceCaller(timeout_seconds=TIMEOUT_SECONDS)
    return WorkspacePassages(
        connected,
        keys=WorkerConnectorKeys(vault),
        caller=caller,
        poster=caller,
        resolver=SystemResolver(),
        clock=lambda: datetime.now(UTC),
    )
