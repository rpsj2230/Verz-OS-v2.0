"""Slack as a source: the channels this install's app was invited to, and a person's own messages.

A company's decisions are often made in a Slack channel and nowhere else, so a question on Ask
should be able to find them. The difficulty is that Slack's own rule for who may read a message is
channel membership, and the Brain has no copy of it and must not make one: a list of who is in
which channel is a resolved access list, which `brain.connectors.manifest` refuses to store.

**This connector keeps a minimal index and reads every value live.** What it keeps of a channel is
its id, its name and whether it is private; of a Slack member, their id and a digest of their
confirmed work email, the digest `brain.gate.ingress.identity_hash` keeps for an email binding.
No message, no member list and no address is stored. A message is read from Slack when a question
needs it, and is told only to an asker who is a member of its channel in Slack at that moment. See
`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`.

**Membership is asked of Slack on every question, for the asker and no one else.** The asker is
matched to their Slack account by the digest of their verified work email and nothing else: never
by a display name, which anybody can set to anybody's. Slack is then asked which of the app's
channels that member is in (`users.conversations`), and only those channels are read. See
`MEMBERSHIP_IS_ASKED_OF_SLACK_FOR_EVERY_QUESTION`.

**An asker with no Slack account, or in no channel that holds the answer, is told what an asker
is told when the channels hold nothing on the subject.** The reply has no row for a channel the
asker cannot see, not even a count, so the answer cannot say that a channel exists. That is the
repository's rule that a denial and an absence read alike, applied to Slack. See
`A_CHANNEL_THE_ASKER_IS_NOT_IN_IS_NOT_THERE_FOR_THEM`.

**Read-only, and only where the app was invited.** The bot token's scopes are the read scopes for
channels, their history and members; a channel the app was not invited to is not listed to it, so
it is neither indexed nor read. The connection names the workspace it reads and the department
whose people may be told what it holds.

**This is Slack read as a source, and not the Slack channel.** `brain.channels.slack` answers a
question asked in Slack; this module reads what was said there to answer a question asked
anywhere. They are separate apps with separate tokens and scopes, so the name is
`slack_messages`, as Lark's sources are `lark_base` and `lark_wiki` beside the `lark` channel.

Rejected: Slack's own search (`search.messages`). It needs a user token, which is one person's
whole account, and it searches as that person; a company-wide bot token has no search at all.
Rejected: indexing messages and filtering by membership at question time. It is a bulk sync of
bodies, which the owner's rule forbids, and a stored copy outlives a person leaving a channel.

Task ids: M11.7.5
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Self

from brain.connectors.contract import (
    AccessMode,
    ConnectorContractError,
    ConnectorScope,
    CredentialBinding,
    TransportKind,
    assert_holds_no_credential,
)
from brain.connectors.declaration import (
    CREDENTIAL_ASK,
    ConnectorDeclaration,
    ConsoleForm,
    KeyScheme,
    PageReply,
    Recorded,
    Setting,
    SettingRefusedError,
)
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
    ToolDeclaration,
)
from brain.connectors.projection import ProjectedRecord
from brain.connectors.rest import ID_TARGET, OperationSpec, ParameterSpec, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import FieldMapping, RestTransport
from brain.connectors.write_verification import ReadBack, Reading, unreadable
from brain.core.department import SLUG_RE
from brain.core.envelope import IdentityMode
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.ingress import identity_hash
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.secrets import SecretRef

# ------------------------------------------------------------------ written-down reasons

#: Why membership is asked of Slack for each question.
MEMBERSHIP_IS_ASKED_OF_SLACK_FOR_EVERY_QUESTION: Final = (
    "Slack decides who may read a channel, by membership, and the Brain keeps no copy of it. So "
    "on every question the asker is matched to their Slack account by the digest of their "
    "verified work email, never a display name, and Slack is asked which of the app's channels "
    "that account is in; only those channels are read, and only for that asker."
)

#: What an asker is told about a channel they are not in.
A_CHANNEL_THE_ASKER_IS_NOT_IN_IS_NOT_THERE_FOR_THEM: Final = (
    "A message in a channel the asker is not a member of is never read for them, however well it "
    "matches, and an asker with no Slack account is read nothing. Either way they are told what "
    "an asker is told when the channels hold nothing on the subject, with no row, count or hint "
    "that a channel they cannot see exists."
)

# ------------------------------------------------------------------------ the figures
CONNECTOR_NAME: Final = "slack_messages"
#: The entity kinds, named for Slack so their capabilities (`read:slack_message`) cannot be read as
#: another surface's: `read:member.*` is the whole member surface of the console.
CHANNEL: Final = "slack_channel"
MEMBER: Final = "slack_member"
MESSAGE: Final = "slack_message"
VERSION: Final = "1.0.0"
SPEC_REF: Final = "slack.web-api"

#: Slack's Web API, the one address this connector calls.
API: Final = "https://slack.com/api"

#: How often the index is read again: channels and members change within a day.
READING_INTERVAL: Final = timedelta(hours=1)

#: One page of a Slack list. Slack recommends no more than 200.
PAGE_LIMIT: Final = "200"

#: The channels read for one question, and the recent messages read from each.
MAX_CHANNELS: Final = 10
HISTORY_LIMIT: Final = "100"

#: The passages one question is shown, and the longest one.
MAX_PASSAGES: Final = 5
PASSAGE_CHARS: Final = 2000

WORKSPACE_SETTING: Final = "workspace"
DEPARTMENT_SETTING: Final = "department"

#: The scopes the bot token is created with, each read-only, as the slot row asks for them.
SCOPES: Final = (
    "channels:read",
    "groups:read",
    "channels:history",
    "groups:history",
    "users:read",
    "users:read.email",
)

_WORKSPACE_RE: Final = re.compile(r"^T[A-Z0-9]{6,20}$")
_SLACK_ID_RE: Final = re.compile(r"^[CGUW][A-Z0-9]{6,20}$")


class SlackError(ConnectorContractError):
    """A reply or a setting this connector will not read, in words that quote no value."""


# --------------------------------------------------------------------- the connection
@dataclass(frozen=True)
class SlackConnection:
    """One workspace and the department that may be told what it holds, decided at connect."""

    workspace: str
    department: str

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not _WORKSPACE_RE.fullmatch(self.workspace):
            msg = "the workspace is not a Slack workspace id"
            raise SettingRefusedError(msg, setting=WORKSPACE_SETTING)
        if not SLUG_RE.fullmatch(self.department):
            msg = "the department is not a department's short name"
            raise SettingRefusedError(msg, setting=DEPARTMENT_SETTING)
        self.scope()

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> Self:
        return cls(
            workspace=settings.get(WORKSPACE_SETTING, "").strip().upper(),
            department=settings.get(DEPARTMENT_SETTING, "").strip(),
        )

    def scope(self) -> ConnectorScope:
        return ConnectorScope(resource_kind="workspace", selectors=(self.workspace,))

    def visibility(self) -> Scope:
        return Scope.department(self.department)


# ---------------------------------------------------------------------- the operations
def _list(operation_id: str, path: str, records_at: str, *extra: str) -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        method="get",
        path=path,
        parameters=(
            ParameterSpec(name="limit", location="query"),
            ParameterSpec(name="cursor", location="query"),
            *(ParameterSpec(name=one, location="query") for one in extra),
        ),
        records_at=records_at,
    )


CHANNELS_OPERATION: Final = _list(
    "conversations_list", "/conversations.list", "channels", "types", "exclude_archived"
)
MEMBERS_OPERATION: Final = _list("users_list", "/users.list", "members")
MEMBERSHIP_OPERATION: Final = _list(
    "users_conversations", "/users.conversations", "channels", "user", "types", "exclude_archived"
)
HISTORY_OPERATION: Final = _list(
    "conversations_history", "/conversations.history", "messages", "channel"
)

CHANNEL_MAPPING: Final = (
    FieldMapping(target=ID_TARGET, source_path="id"),
    FieldMapping(target="name", source_path="name"),
    FieldMapping(target="is_private", source_path="is_private"),
    FieldMapping(target="is_member", source_path="is_member"),
)
MEMBER_MAPPING: Final = (
    FieldMapping(target=ID_TARGET, source_path="id"),
    FieldMapping(target="email", source_path="profile.email"),
    FieldMapping(target="confirmed", source_path="is_email_confirmed"),
    FieldMapping(target="deleted", source_path="deleted"),
    FieldMapping(target="is_bot", source_path="is_bot"),
)
MESSAGE_MAPPING: Final = (
    FieldMapping(target=ID_TARGET, source_path="ts"),
    FieldMapping(target="text", source_path="text"),
    FieldMapping(target="author", source_path="user"),
)

_BY_ENTITY: Final = {
    CHANNEL: (CHANNELS_OPERATION, CHANNEL_MAPPING),
    MEMBER: (MEMBERS_OPERATION, MEMBER_MAPPING),
}


def operation_for(entity: str) -> RestOperation:
    """The list one entity kind is indexed from."""
    spec, mapping = _BY_ENTITY[entity]
    return RestOperation(
        base_url=API,
        operation=spec,
        transport=RestTransport(
            spec_ref=SPEC_REF, operation=spec.operation_id, entity=entity, fields=mapping
        ),
    )


def membership_operation() -> RestOperation:
    """The channels one member is in, of those the app can see."""
    return RestOperation(
        base_url=API,
        operation=MEMBERSHIP_OPERATION,
        transport=RestTransport(
            spec_ref=SPEC_REF,
            operation=MEMBERSHIP_OPERATION.operation_id,
            entity=CHANNEL,
            fields=CHANNEL_MAPPING,
        ),
    )


def history_operation() -> RestOperation:
    """A channel's recent messages."""
    return RestOperation(
        base_url=API,
        operation=HISTORY_OPERATION,
        transport=RestTransport(
            spec_ref=SPEC_REF,
            operation=HISTORY_OPERATION.operation_id,
            entity=MESSAGE,
            fields=MESSAGE_MAPPING,
        ),
    )


def answered(body: Any) -> None:
    """Refuse a reply Slack marked as failed. Slack answers most refusals with HTTP 200."""
    if not isinstance(body, Mapping) or body.get("ok") is not True:
        msg = "Slack answered this call with ok false"
        raise SlackError(msg)


def next_cursor(body: Any) -> str:
    """The cursor of the page after this one, or empty when this was the last."""
    metadata = body.get("response_metadata") if isinstance(body, Mapping) else None
    cursor = metadata.get("next_cursor") if isinstance(metadata, Mapping) else None
    return cursor.strip() if isinstance(cursor, str) else ""


# ------------------------------------------------------------------------ the index
CHANNEL_FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(name="privacy", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)),
)
MEMBER_FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="identity_hash", shape=FieldShape.JOIN_KEY, uses=(HotUse.JOIN,)),
)


def member_digest(email: str) -> str:
    """The digest a member's work email is matched by: the one an email binding keeps."""
    return identity_hash(Channel.EMAIL, email)


class SlackReading:
    """The app's channels and the workspace's members, into the minimal index and no more."""

    def entities(self) -> tuple[str, ...]:
        return (CHANNEL, MEMBER)

    def refresh_interval(self) -> timedelta:
        return READING_INTERVAL

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Any
    ) -> RestOperation:
        del resolver
        SlackConnection.from_settings(settings)
        if entity not in _BY_ENTITY:
            msg = f"this reading keeps {sorted(_BY_ENTITY)} and was asked for {entity!r}"
            raise SlackError(msg)
        return operation_for(entity)

    def key_scheme(self) -> KeyScheme:
        return KeyScheme.BEARER

    def first_page(self, entity: str) -> Mapping[str, str]:
        if entity == CHANNEL:
            return {
                "limit": PAGE_LIMIT,
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
            }
        return {"limit": PAGE_LIMIT}

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        del entity, returned
        cursor = next_cursor(body)
        return {**asked, "cursor": cursor} if cursor else None

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        SlackConnection.from_settings(settings)
        return {}

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        call = classify(status=status)
        if call is not CallOutcome.OK:
            return PageReply(call=call, rows=None)
        try:
            answered(body)
        except SlackError:
            # Slack answers a revoked token or a missing scope with 200 and ok false: a refusal,
            # which the worker reads as one, and never a workspace with nothing in it.
            return PageReply(call=CallOutcome.REJECTED, rows=None)
        return PageReply(call=call, rows=operation.records(body, fetched_at=fetched_at))

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        stated = {key.lower(): value for key, value in headers.items()}.get("retry-after", "")
        return float(stated) if stated.strip().isdigit() else None

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        del headers
        return False

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """A channel the app is in, or a person with a confirmed work email; nothing else.

        The member's address is digested here and never kept: the row holds the digest alone.
        """
        raw = row.get("id")
        if not isinstance(raw, str) or not _SLACK_ID_RE.fullmatch(raw):
            return None
        if entity == CHANNEL:
            if row.get("is_member") is not True:
                return None
            fields: dict[str, Any] = {
                "name": str(row.get("name", ""))[:80],
                "privacy": "private" if row.get("is_private") is True else "public",
            }
        elif entity == MEMBER:
            email = row.get("email")
            if (
                row.get("deleted") is True
                or row.get("is_bot") is True
                or row.get("confirmed") is not True
                or not isinstance(email, str)
                or "@" not in email
            ):
                return None
            fields = {"identity_hash": member_digest(email)}
        else:
            return None
        return ProjectedRecord(
            source=CONNECTOR_NAME, entity=entity, source_id=raw, last_seen_at=seen_at, fields=fields
        )


# ------------------------------------------------------------------------ the manifest
def manifest(connection: SlackConnection, *, ref: SecretRef) -> ConnectorManifest:
    """Everything this connector declares for one workspace. Read-only, and service identity: the
    bot token is the app's, and the asker's own Slack membership narrows every read."""
    visibility = connection.visibility()
    return ConnectorManifest(
        name=CONNECTOR_NAME,
        version=VERSION,
        transport=TransportKind.REST,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=(
            ToolDeclaration(
                name="slack_messages.find_messages",
                description=(
                    "Find messages on a subject in the Slack channels the asker is a member of, "
                    "read live from Slack for this question."
                ),
                entity=MESSAGE,
                identity_mode=IdentityMode.SERVICE,
            ),
        ),
        projections=(
            ProjectedEntity(
                entity=CHANNEL,
                fields=CHANNEL_FIELDS,
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=visibility,
            ),
            ProjectedEntity(
                entity=MEMBER,
                fields=MEMBER_FIELDS,
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=visibility,
            ),
        ),
        ceiling=CONNECTOR_NAME,
    )


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    return manifest(SlackConnection.from_settings(settings), ref=ref)


@dataclass(frozen=True)
class Reply:
    """One Slack reply, for the read-back."""

    status: int
    body: Any


def read_back_reading(operation: RestOperation, reply: Reply) -> Reading:
    """One Slack list page as the reading reads it: ok false is a refusal, not an empty page."""
    call = classify(status=reply.status)
    if call is not CallOutcome.OK:
        return Reading(outcome=call, matched=0, complete=False)
    try:
        answered(reply.body)
        rows = operation.project(reply.body)
    except SlackError:
        return Reading(outcome=CallOutcome.REJECTED, matched=0, complete=False)
    except ConnectorContractError:
        return unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(rows), complete=not next_cursor(reply.body))


def message_time(ts: str) -> str:
    """A message's `ts` as the ISO time it was posted, or empty when it is not a Slack stamp."""
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def matching(texts: Sequence[tuple[str, str]], words: Sequence[str]) -> list[tuple[int, str, str]]:
    """Each (ts, text) holding any of the words, with how many it holds, best first."""
    found = []
    for ts, text in texts:
        folded = text.casefold()
        hits = sum(1 for word in words if word in folded)
        if hits:
            found.append((hits, ts, text))
    return sorted(found, key=lambda one: (-one[0], one[1]))


# ------------------------------------------------------------------------ the console
CONSOLE: Final = ConsoleForm(
    settings=(
        Setting(
            name=WORKSPACE_SETTING,
            label="Workspace id",
            hint=(
                "Your Slack workspace's id, which starts with T, as the app's Basic Information "
                "page or a workspace link shows it."
            ),
            refused="That is not a Slack workspace id. It starts with T, such as T0123ABCD.",
        ),
        Setting(
            name=DEPARTMENT_SETTING,
            label="Department that may be told it",
            hint=(
                "The short name of the department whose people may be granted what Slack holds, "
                "as the Departments page shows it. Each person is still read only the channels "
                "they are in."
            ),
            refused=(
                "That is not a department's short name. Use lower-case letters, digits and "
                "underscores, exactly as the Departments page shows it."
            ),
        ),
    ),
    credential_label="The app's Bot User OAuth Token",
    credential_hint=(
        "Copy the Bot User OAuth Token from the app's OAuth & Permissions page after installing "
        "it. Give the app these scopes and no others: "
        + ", ".join(SCOPES)
        + ". It is kept in the vault and never shown again."
    ),
    build=built_from_the_console,
)

APPS_URL: Final = "https://api.slack.com/apps"

#: Where Slack documents its Web API tiers, which `brain.ops.limits` records the ceiling from.
RATE_LIMITS_URL: Final = "https://docs.slack.dev/apis/web-api/rate-limits"

GUIDE: Final = keyed(
    (
        GuideStep(
            key="app",
            title="Create a Slack app for your workspace",
            text=(
                "At api.slack.com/apps click Create New App, choose From scratch, name it after "
                "this system and pick your workspace."
            ),
            sketch=Sketch(place="Slack API", heading="Your Apps", button="Create New App"),
            link=APPS_URL,
            link_label="Open Your Apps",
        ),
        GuideStep(
            key="scopes",
            title="Give it read scopes only",
            text=(
                "Open OAuth & Permissions and add these Bot Token Scopes: "
                + ", ".join(SCOPES)
                + ". Nothing that writes, and nothing else."
            ),
            sketch=Sketch(
                place="Slack API",
                heading="Bot Token Scopes",
                lines=tuple(SketchLine(LineKind.ITEM, one, mark=True) for one in SCOPES[:3]),
            ),
        ),
        GuideStep(
            key="install",
            title="Install it and invite it to channels",
            text=(
                "Click Install to Workspace and allow it. Then, in each channel this system may "
                "read, type /invite and the app's name. A channel it is not in is never read."
            ),
            sketch=Sketch(
                place="Slack",
                heading="#a-channel",
                lines=(SketchLine(LineKind.FIELD, "Message", "/invite @app", mark=True),),
            ),
        ),
        GuideStep(
            key="connect",
            title="Paste the workspace, the department and the token here",
            text=(
                "Type the workspace id and the department, paste the Bot User OAuth Token, and "
                "press Connect Slack."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Slack",
                lines=(
                    SketchLine(LineKind.FIELD, "Workspace id", "T0123ABCD", mark=True),
                    SketchLine(LineKind.FIELD, "Department", "operations", mark=True),
                    SketchLine(LineKind.FIELD, "Bot token", "********", mark=True),
                ),
                button="Connect Slack",
            ),
            asks=(WORKSPACE_SETTING, DEPARTMENT_SETTING, CREDENTIAL_ASK),
        ),
    )
)

CONNECTOR: Final = ConnectorDeclaration(
    name=CONNECTOR_NAME,
    label="Slack",
    guide=GUIDE,
    console=CONSOLE,
    read_back=ReadBack(
        reading=read_back_reading,
        recorded=(
            "SLACK-200-channels",
            "SLACK-200-members",
            "SLACK-200-membership",
            "SLACK-200-history",
            "SLACK-200-not-ok",
            "SLACK-429",
            "SLACK-503",
        ),
        findings=(),
    ),
    recorded=Recorded(tested=True),
    reading=SlackReading(),
)
