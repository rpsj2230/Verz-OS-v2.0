"""A connected Slack workspace on Ask: the asker's own channels, read live for each question.

`brain.connectors.slack_messages` holds every rule about reading Slack; this is the application's
half. For each question it finds the asker's Slack account from the index by the digest of their
verified work email, asks Slack which of the app's channels that account is in, reads those
channels' recent messages, and hands the messages that hold the question's words to the answer
lane's model step as passages, told to the asker alone. See
`brain.connectors.slack_messages.MEMBERSHIP_IS_ASKED_OF_SLACK_FOR_EVERY_QUESTION`.

**Nothing is kept.** The messages are passages for one question: not written to a table, not
embedded, not logged. The index it reads holds channel names and email digests, never a message.

**Two gates before Slack is asked anything.** The asker must hold `read:slack_message` in the
department the connection answers to, which the connection's data steward grants, and must have an
email binding whose digest matches a Slack member; either missing is answered with no passage and
no call, which is what an asker is told when Slack holds nothing on the subject. See
`brain.connectors.slack_messages.A_CHANNEL_THE_ASKER_IS_NOT_IN_IS_NOT_THERE_FOR_THEM`.

**A passage is personal to its asker.** It is tagged with the asker as its owner at the personal
level, so the passage policy tells it to the person whose membership admitted it and to nobody
else, even if the same answer is shown again.

Task ids: M11.7.5
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors import slack_messages as slack
from brain.connectors.rest import MAX_RESPONSE_BYTES, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.core.entitlement import Capability
from brain.core.envelope import TypedResult
from brain.gate.context import Channel
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, KnowledgePassage
from brain.knowledge.visibility import Visibility
from brain.ops.connectable import key_reference
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import call_headers
from brain.ops.lark_wiki_live import words_of
from brain.ops.secrets import SecretsUnavailableError
from brain.tables.identity import PrincipalIdentityRow
from brain.tables.projection import ProjectedRecordRow
from brain.tools.fetch import Resolver

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.ops.connector_sync_run import ConnectorKeys, SourceCaller

log = structlog.get_logger()

#: The capability a person needs to be told what Slack holds, in the connection's department.
READ_MESSAGE: Final = Capability(value=f"read:{slack.MESSAGE}")

#: The most pages of one member's channels read for one question.
MAX_MEMBERSHIP_PAGES: Final = 5


def _empty(now: datetime) -> TypedResult[KnowledgePassage]:
    return TypedResult[KnowledgePassage](
        records=(), source=slack.CONNECTOR_NAME, fetched_at=now.isoformat()
    )


async def asker_digests(
    sessions: async_sessionmaker[AsyncSession], principal_id: str
) -> tuple[str, ...]:
    """The digests of the asker's email bindings, which is how they are matched to Slack."""
    async with sessions() as session:
        rows = await session.execute(
            select(PrincipalIdentityRow.identity_hash).where(
                PrincipalIdentityRow.principal_id == principal_id,
                PrincipalIdentityRow.channel == Channel.EMAIL.value,
                PrincipalIdentityRow.deleted_at.is_(None),
            )
        )
        return tuple(str(one) for one in rows.scalars())


async def indexed(
    sessions: async_sessionmaker[AsyncSession], entity: str
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Every live index row of one Slack entity, as (source id, fields)."""
    async with sessions() as session:
        rows = await session.execute(
            select(ProjectedRecordRow.source_id, ProjectedRecordRow.fields).where(
                ProjectedRecordRow.source == slack.CONNECTOR_NAME,
                ProjectedRecordRow.entity == entity,
                ProjectedRecordRow.deleted_at.is_(None),
            )
        )
        return tuple((str(one), dict(fields)) for one, fields in rows.all())


class SlackPassages:
    """`brain.gate.model_lane.PassageSearch` over the connected workspace, read per question."""

    def __init__(
        self,
        connected: Callable[[], Awaitable[Connection | None]],
        *,
        sessions: async_sessionmaker[AsyncSession],
        keys: ConnectorKeys,
        caller: SourceCaller,
        resolver: Resolver,
        clock: Callable[[], datetime],
    ) -> None:
        self._clock = clock
        self._connected = connected
        self._sessions = sessions
        self._keys = keys
        self._caller = caller
        self._resolver = resolver

    def __repr__(self) -> str:
        return "SlackPassages()"

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        words = words_of(question)
        connection = await self._connected()
        if not words or connection is None:
            return _empty(now)
        department = slack.SlackConnection.from_settings(connection.settings).department
        scope = entitlement.scope_for(READ_MESSAGE, now)
        if scope is None or not scope.matches({"department": department}):
            return _empty(now)
        digests = set(await asker_digests(self._sessions, entitlement.principal_id))
        members = [
            one
            for one, fields in await indexed(self._sessions, slack.MEMBER)
            if fields.get("identity_hash") in digests
        ]
        if not members:
            return _empty(now)
        channels = {
            one: str(fields.get("name", ""))
            for one, fields in await indexed(self._sessions, slack.CHANNEL)
        }
        found = await asyncio.to_thread(self.read, connection, members[0], channels, words)
        told = tuple(
            KnowledgePassage(
                entity=KNOWLEDGE_ENTITY,
                id=f"slack-{channel}-{ts}",
                document_id=f"slack-{channel}-{ts}",
                title=f"#{channels[channel]}",
                section=slack.message_time(ts),
                document=text[: slack.PASSAGE_CHARS],
                updated_at=slack.message_time(ts) or now.isoformat(),
                visibility=Visibility.PERSONAL.value,
                owner_id=entitlement.principal_id,
            )
            for channel, ts, text in found
        )
        return TypedResult[KnowledgePassage](
            records=told, source=slack.CONNECTOR_NAME, fetched_at=now.isoformat()
        )

    def read(
        self,
        connection: Connection,
        member: str,
        channels: Mapping[str, str],
        words: Sequence[str],
    ) -> tuple[tuple[str, str, str], ...]:
        """The matching messages of the channels this member is in, as (channel, ts, text).

        One lease for the question. A call that fails ends the reading with what was read so far,
        and a channel the member is not in is never asked for.
        """
        reading = slack.SlackReading()
        lease = self._keys.lease(key_reference(slack.CONNECTOR_NAME), now=self._clock())
        try:
            try:
                headers = call_headers(reading, connection.settings, lease.key())
            except SecretsUnavailableError:
                log.warning("slack.unread", why="no key")
                return ()
            theirs = self._membership(member, headers)
            readable = [one for one in channels if one in theirs][: slack.MAX_CHANNELS]
            scored: list[tuple[int, str, str, str]] = []
            for channel in readable:
                body = self._get(
                    slack.history_operation(),
                    {"channel": channel, "limit": slack.HISTORY_LIMIT},
                    headers,
                )
                if body is None:
                    break
                texts = [
                    (str(row.get("id", "")), str(row.get("text", "")))
                    for row in slack.history_operation().project(body)
                ]
                scored.extend(
                    (hits, channel, ts, text) for hits, ts, text in slack.matching(texts, words)
                )
            best = sorted(scored, key=lambda one: (-one[0], one[1], one[2]))[: slack.MAX_PASSAGES]
            return tuple((channel, ts, text) for _, channel, ts, text in best)
        finally:
            lease.close(self._clock())

    def _membership(self, member: str, headers: Mapping[str, str]) -> frozenset[str]:
        """The channels this member is in, of those the app can see, asked of Slack now."""
        operation = slack.membership_operation()
        arguments: dict[str, str] = {
            "user": member,
            "types": "public_channel,private_channel",
            "exclude_archived": "true",
            "limit": slack.PAGE_LIMIT,
        }
        found: set[str] = set()
        for _ in range(MAX_MEMBERSHIP_PAGES):
            body = self._get(operation, arguments, headers)
            if body is None:
                break
            found |= {str(row.get("id", "")) for row in operation.project(body)}
            cursor = slack.next_cursor(body)
            if not cursor:
                break
            arguments = {**arguments, "cursor": cursor}
        return frozenset(found)

    def _get(
        self, operation: RestOperation, arguments: Mapping[str, str], headers: Mapping[str, str]
    ) -> Any:
        """One call's answered body, or None for any failure, which is logged by its kind."""
        try:
            checked = operation.prepare(arguments, resolver=self._resolver)
        except Exception:
            log.warning("slack.unread", why="address or shape")
            return None
        answer = self._caller.get(
            checked.url, address=checked.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
        )
        call = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed or answer.status is None,
        )
        if call is not CallOutcome.OK:
            log.warning("slack.unread", why=call.value)
            return None
        try:
            body = json.loads(answer.body)
            slack.answered(body)
        except (ValueError, slack.SlackError):
            log.warning("slack.unread", why="refused")
            return None
        return body


class PersonalPassages(Protocol):
    """A live reader of passages personal to the asker: Slack's, or Google Workspace's (M11.7.6)."""

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        """The asker's own passages on the question, read live."""
        ...


class Alongside:
    """`PassageSearch` over another search and a personal reader: the other's passages first."""

    def __init__(self, first: Any, second: PersonalPassages) -> None:
        self._first = first
        self._second = second

    @property
    def library(self) -> Any:
        """The search Slack was put beside, which a narrowed question reads alone."""
        return self._first

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        own = await self._first.passages(question, entitlement=entitlement, now=now)
        more = await self._second.passages(question, entitlement=entitlement, now=now)
        return TypedResult[KnowledgePassage](
            records=(*own.records, *more.records),
            source=own.source,
            fetched_at=own.fetched_at,
            truncated=own.truncated,
        )
