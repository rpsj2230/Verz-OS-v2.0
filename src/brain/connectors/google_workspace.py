"""Google Workspace as a source: each person's own mail, calendar and documents, read as them.

A company's commitments live in its people's mail and calendars as much as in any system of
record, and a question on Ask should be able to reach them. The difficulty is whose they are. A
mailbox is one person's, and Google's own rule for who may read a message, an event or a document
is that person's account: there is no company-wide key that reads a mailbox without impersonating
its owner, and domain-wide delegation, which would, is a key that reads every mailbox at once.

**Each person consents for their own account, and their account is read only for their own
questions.** The connection holds the application the company registered at Google (its client id
as a setting, its client secret as the key), and each person connects their own account from My
workspace, giving a consent that buys a refresh token kept in their own vault slot
(`brain.connectors.oauth.ConsentKind.PERSON`, `brain.ops.credentials.connector_person_oauth_slot`).
A question is read with the asker's token alone, so Google itself decides what they may read, and
what comes back is told to them alone. See `A_PERSONS_WORKSPACE_IS_READ_AS_THEM_FOR_THEM`.

**The services are chosen at connect, and one not chosen is never called and never asked for.**
`services` holds any of mail, calendar and documents, and each is one read-only Google scope:
`gmail.readonly`, `calendar.readonly` and `drive.readonly`. A person's consent asks Google for the
scopes of the chosen services and no others (`brain.connectors.oauth.asked_scopes`), with
`access_type=offline` so a refresh token is issued, and the read for a question calls only the
chosen services' endpoints. See `A_SERVICE_NOT_CHOSEN_IS_NEVER_CALLED`.

**Documents are read with the same personal consent, not through the Drive connector.** The Drive
connector reads one folder an administrator shared with a service account, for one department,
indexing its file names: the company's documents, answered by the company's rule. A person's own
documents are a different set, everything Google lets that person open, and the only key that
reads them as that person is their own consent. Reading them through the Drive connector would
either reach nothing of theirs or, with domain-wide delegation, reach everybody's. So documents
are a third service of this connection, read live with `drive.readonly` under the asker's token,
and a company folder for a department stays the Drive connector's. Rejected: answering documents
by the Drive connector and calling it a Workspace service, which would make "documents" a choice
whose reads are governed by a different person's rule than the mail beside it.

**This connector keeps a minimal index and reads every value live**, and the index here is empty:
nothing about a person's mail, calendar or documents is kept, not a subject, not an id, not a
count. Each question reads the asker's matching messages, events and documents from Google at that
moment and hands them to the answer lane as passages personal to the asker
(`brain.ops.google_workspace_live.WorkspacePassages`), never written, embedded or logged. See
`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`. There is no scheduled reading at all:
a read with nobody present has no person whose token it could use, and
`brain.ops.connector_lease.NOTHING_RUNNING_WITH_NOBODY_PRESENT_READS_A_PERSONS_CONSENT` is held by
the vault.

**A reader also needs the connection's read capability**, `read:google_workspace` in the
department the connection answers to, which the data steward grants. Without it a person is never
offered the button and is read nothing, consent or not, exactly as Slack's `read:slack_message`.

Rejected: domain-wide delegation of a service account. It is one key that reads every mailbox in
the company as whoever it names, which no person consented to and no vault policy can narrow.

Task ids: M11.7.6
"""

from __future__ import annotations

import enum
import html
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Self

from brain.connectors.ask import AskRows
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
    PERSONAL_DEPARTMENT_SETTING,
    ConnectExample,
    ConnectorDeclaration,
    ConsoleForm,
    KeyScopes,
    Recorded,
    Setting,
    SettingRefusedError,
)
from brain.connectors.google_token import GOOGLE_SCOPES_BASE_URL
from brain.connectors.manifest import ConnectorManifest, PermissionSync, ToolDeclaration
from brain.connectors.oauth import ConsentKind, OAuthConsent
from brain.connectors.rest import ID_TARGET, OperationSpec, ParameterSpec, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import FieldMapping, RestTransport
from brain.connectors.write_verification import ReadBack, Reading, unreadable
from brain.core.department import SLUG_RE
from brain.core.envelope import IdentityMode
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.limits import ConnectorLimit
from brain.ops.secrets import SecretRef

# ------------------------------------------------------------------ written-down reasons
#: Why a person's Workspace is read with their token and told to them alone.
A_PERSONS_WORKSPACE_IS_READ_AS_THEM_FOR_THEM: Final = (
    "A mailbox, a calendar and a person's documents are theirs, and Google decides who may read "
    "them by the account. So each is read with the asking person's own consent and nobody "
    "else's, Google answers only what that account may open, and every passage is told to the "
    "asker alone: another person's question never names their slot and is told nothing of theirs."
)

#: Why a service not chosen is never called.
A_SERVICE_NOT_CHOSEN_IS_NEVER_CALLED: Final = (
    "The services a connection reads are chosen when it is connected. A person's consent asks "
    "Google for the scopes of those services only, and a question reads only those services' "
    "endpoints, so a service nobody chose is neither granted nor called."
)

# ------------------------------------------------------------------------ the figures
CONNECTOR_NAME: Final = "google_workspace"
VERSION: Final = "1.0.0"
SPEC_REF: Final = "google_workspace.v1"

#: What a person's passages are read as, by the tool each chosen service declares.
MAIL: Final = "workspace_mail"
EVENT: Final = "workspace_event"
DOCUMENT: Final = "workspace_document"

#: The capability a person holds in the connection's department to be read anything, and so to
#: connect their own account at all. Declared in `brain.ops.starter.checked_elsewhere`.
READER: Final = "read:google_workspace"

CLIENT_ID_SETTING: Final = "client_id"
SERVICES_SETTING: Final = "services"
DEPARTMENT_SETTING: Final = PERSONAL_DEPARTMENT_SETTING

#: Google's consent page and token endpoint (https://developers.google.com/identity/protocols/
#: oauth2/web-server).
AUTHORIZE_URL: Final = "https://accounts.google.com/o/oauth2/v2/auth"
EXCHANGE_URL: Final = "https://oauth2.googleapis.com/token"

GMAIL_SCOPE: Final = f"{GOOGLE_SCOPES_BASE_URL}gmail.readonly"
CALENDAR_SCOPE: Final = f"{GOOGLE_SCOPES_BASE_URL}calendar.readonly"
DRIVE_SCOPE: Final = f"{GOOGLE_SCOPES_BASE_URL}drive.readonly"

GMAIL_URL: Final = "https://gmail.googleapis.com"
GOOGLE_API_URL: Final = "https://www.googleapis.com"

#: How many of each a question is read: messages, events and documents.
MAX_MESSAGES: Final = 5
MAX_EVENTS: Final = 5
MAX_DOCUMENTS: Final = 3

#: The longest passage one item is told as, and the most bytes one exported document is read.
PASSAGE_CHARS: Final = 2000
MAX_EXPORT_BYTES: Final = 200_000

#: A Google OAuth client id, as the Cloud console issues one.
_CLIENT_ID_RE: Final = re.compile(r"^[0-9]{6,20}-[a-z0-9]{8,64}\.apps\.googleusercontent\.com$")
#: A Gmail message id, a Calendar event id, a Drive file id.
_ITEM_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,512}$")
_GOOGLE_DOC: Final = "application/vnd.google-apps.document"


class WorkspaceError(ConnectorContractError):
    """A reply or a setting this connector will not read, in words that quote no value."""


class Service(enum.StrEnum):
    """What a connection may read for each person, chosen at connect."""

    MAIL = "mail"
    CALENDAR = "calendar"
    DOCUMENTS = "documents"


#: The one read-only scope each service asks Google for.
SCOPE_OF: Final[Mapping[Service, str]] = {
    Service.MAIL: GMAIL_SCOPE,
    Service.CALENDAR: CALENDAR_SCOPE,
    Service.DOCUMENTS: DRIVE_SCOPE,
}


# --------------------------------------------------------------------- the connection
@dataclass(frozen=True)
class WorkspaceConnection:
    """The application registered at Google, the services chosen, and the readers' department."""

    client_id: str
    services: tuple[Service, ...]
    department: str

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not _CLIENT_ID_RE.fullmatch(self.client_id):
            msg = "the client id is not a Google OAuth client id"
            raise SettingRefusedError(msg, setting=CLIENT_ID_SETTING)
        if not self.services:
            msg = "no service is chosen, so nothing would ever be read"
            raise SettingRefusedError(msg, setting=SERVICES_SETTING)
        if not SLUG_RE.fullmatch(self.department):
            msg = "the department is not a department's short name"
            raise SettingRefusedError(msg, setting=DEPARTMENT_SETTING)

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> Self:
        named = [
            one.strip().lower()
            for one in settings.get(SERVICES_SETTING, "").split(",")
            if one.strip()
        ]
        try:
            chosen = {Service(one) for one in named}
        except ValueError:
            msg = "a service named is not mail, calendar or documents"
            raise SettingRefusedError(msg, setting=SERVICES_SETTING) from None
        return cls(
            client_id=settings.get(CLIENT_ID_SETTING, "").strip(),
            services=tuple(one for one in Service if one in chosen),
            department=settings.get(DEPARTMENT_SETTING, "").strip(),
        )

    def scope(self) -> ConnectorScope:
        return ConnectorScope(resource_kind="oauth_client", selectors=(self.client_id,))


# ---------------------------------------------------------------------- the operations
def _operation(
    base: str,
    operation_id: str,
    path: str,
    entity: str,
    mapping: tuple[FieldMapping, ...],
    *,
    records_at: str,
    query: tuple[str, ...],
    path_parameter: str = "",
) -> RestOperation:
    parameters = tuple(ParameterSpec(name=one, location="query") for one in query)
    if path_parameter:
        parameters = (
            ParameterSpec(name=path_parameter, location="path", required=True),
            *parameters,
        )
    spec = OperationSpec(
        operation_id=operation_id,
        method="get",
        path=path,
        parameters=parameters,
        records_at=records_at,
    )
    return RestOperation(
        base_url=base,
        operation=spec,
        transport=RestTransport(
            spec_ref=SPEC_REF, operation=operation_id, entity=entity, fields=mapping
        ),
    )


def messages_operation() -> RestOperation:
    """The asker's messages matching a Gmail search: their ids, and nothing else."""
    return _operation(
        GMAIL_URL,
        "gmail_messages_list",
        "/gmail/v1/users/me/messages",
        MAIL,
        (FieldMapping(target=ID_TARGET, source_path="id"),),
        records_at="messages",
        query=("q", "maxResults"),
    )


def message_operation() -> RestOperation:
    """One of the asker's messages, as its headers and Gmail's snippet. Never its body."""
    return _operation(
        GMAIL_URL,
        "gmail_messages_get",
        "/gmail/v1/users/me/messages/{id}",
        MAIL,
        (
            FieldMapping(target=ID_TARGET, source_path="id"),
            FieldMapping(target="snippet", source_path="snippet"),
            FieldMapping(target="headers", source_path="payload.headers"),
            FieldMapping(target="internal_date", source_path="internalDate"),
        ),
        records_at="",
        query=("format",),
        path_parameter="id",
    )


def events_operation() -> RestOperation:
    """The asker's own calendar's events matching a search."""
    return _operation(
        GOOGLE_API_URL,
        "calendar_events_list",
        "/calendar/v3/calendars/primary/events",
        EVENT,
        (
            FieldMapping(target=ID_TARGET, source_path="id"),
            FieldMapping(target="summary", source_path="summary"),
            FieldMapping(target="description", source_path="description"),
            FieldMapping(target="location", source_path="location"),
            FieldMapping(target="start", source_path="start.dateTime"),
            FieldMapping(target="start_date", source_path="start.date"),
        ),
        records_at="items",
        query=("q", "maxResults", "singleEvents"),
    )


def files_operation() -> RestOperation:
    """The Google Docs the asker may open whose text matches a search."""
    return _operation(
        GOOGLE_API_URL,
        "drive_files_list",
        "/drive/v3/files",
        DOCUMENT,
        (
            FieldMapping(target=ID_TARGET, source_path="id"),
            FieldMapping(target="name", source_path="name"),
            FieldMapping(target="mime", source_path="mimeType"),
            FieldMapping(target="modified", source_path="modifiedTime"),
        ),
        records_at="files",
        query=("q", "pageSize", "fields"),
    )


def export_operation() -> RestOperation:
    """One Google Doc's text, exported as plain text. Its body is not JSON."""
    return _operation(
        GOOGLE_API_URL,
        "drive_files_export",
        "/drive/v3/files/{id}/export",
        DOCUMENT,
        (FieldMapping(target=ID_TARGET, source_path="id"),),
        records_at="",
        query=("mimeType",),
        path_parameter="id",
    )


# ------------------------------------------------------------------------ the questions
def _quoted(word: str) -> str:
    """A word as a search term, with anything that could end the term taken out."""
    return re.sub(r"[^\w-]", "", word)


def mail_query(words: Sequence[str]) -> dict[str, str]:
    """Gmail's search for any of the words, newest first. `{a b}` is Gmail's OR."""
    terms = " ".join(one for one in (_quoted(word) for word in words) if one)
    return {"q": f"{{{terms}}}", "maxResults": str(MAX_MESSAGES)}


def event_query(words: Sequence[str]) -> dict[str, str]:
    """Calendar's free-text search over the asker's own events."""
    terms = " ".join(one for one in (_quoted(word) for word in words) if one)
    return {"q": terms, "maxResults": str(MAX_EVENTS), "singleEvents": "true"}


def document_query(words: Sequence[str]) -> dict[str, str]:
    """Drive's search for Google Docs the asker may open whose text holds any of the words."""
    terms = " or ".join(
        f"fullText contains '{one}'" for one in (_quoted(word) for word in words) if one
    )
    return {
        "q": f"({terms}) and mimeType = '{_GOOGLE_DOC}' and trashed = false",
        "pageSize": str(MAX_DOCUMENTS),
        "fields": "files(id,name,mimeType,modifiedTime)",
    }


# ------------------------------------------------------------------------ the answers
@dataclass(frozen=True)
class Found:
    """One item read for one question: what it is, its title, when, and its words."""

    entity: str
    item_id: str
    title: str
    when: str
    text: str


def answered(status: int | None, body: Any) -> Mapping[str, Any]:
    """A reply Google answered as a JSON object, or a `WorkspaceError` naming no value."""
    if classify(status=status) is not CallOutcome.OK or not isinstance(body, Mapping):
        msg = "Google did not answer this call with a reply this connector reads"
        raise WorkspaceError(msg)
    return body


def message_ids(operation: RestOperation, body: Any) -> tuple[str, ...]:
    """The message ids a search answered, at most `MAX_MESSAGES`, each shaped as Gmail's are."""
    # Gmail leaves the array out entirely when nothing matches: an absence, not a shape change.
    if isinstance(body, Mapping) and "messages" not in body:
        return ()
    rows = operation.project(body)
    ids = (str(row.get(ID_TARGET, "")) for row in rows)
    return tuple(one for one in ids if _ITEM_ID_RE.fullmatch(one))[:MAX_MESSAGES]


def _header(headers: Any, name: str) -> str:
    for one in headers if isinstance(headers, list) else ():
        if isinstance(one, Mapping) and str(one.get("name", "")).lower() == name.lower():
            return str(one.get("value", ""))
    return ""


def message_row(operation: RestOperation, body: Any) -> Mapping[str, Any] | None:
    """The one message a read answered, through the mapping, which names no body field."""
    rows = operation.project([body])
    return rows[0] if rows else None


def message_found(row: Mapping[str, Any]) -> Found | None:
    """One message as its subject, sender, date and Gmail's snippet. Never the body."""
    ident = str(row.get(ID_TARGET, ""))
    if not _ITEM_ID_RE.fullmatch(ident):
        return None
    headers = row.get("headers")
    subject = _header(headers, "Subject") or "(no subject)"
    sender = _header(headers, "From")
    snippet = html.unescape(str(row.get("snippet", "")))
    text = f"From {sender}: {snippet}" if sender else snippet
    return Found(MAIL, ident, subject[:200], _header(headers, "Date"), text[:PASSAGE_CHARS])


def events_found(operation: RestOperation, body: Any) -> tuple[Found, ...]:
    """The asker's matching events, each as its title, its start and its words."""
    found = []
    for row in operation.project(body)[:MAX_EVENTS]:
        ident = str(row.get(ID_TARGET, ""))
        if not _ITEM_ID_RE.fullmatch(ident):
            continue
        when = str(row.get("start") or row.get("start_date") or "")
        place = str(row.get("location", ""))
        words = " ".join(
            one for one in (str(row.get("description", "")), f"At {place}." if place else "") if one
        )
        title = str(row.get("summary", "")) or "(no title)"
        found.append(Found(EVENT, ident, title[:200], when, words[:PASSAGE_CHARS] or title))
    return tuple(found)


def documents_listed(operation: RestOperation, body: Any) -> tuple[tuple[str, str, str], ...]:
    """The Google Docs a search answered, as (id, name, modified), at most `MAX_DOCUMENTS`."""
    listed = []
    for row in operation.project(body):
        ident = str(row.get(ID_TARGET, ""))
        if _ITEM_ID_RE.fullmatch(ident) and row.get("mime") == _GOOGLE_DOC:
            listed.append((ident, str(row.get("name", "")), str(row.get("modified", ""))))
    return tuple(listed[:MAX_DOCUMENTS])


def document_found(
    ident: str, name: str, modified: str, text: str, words: Sequence[str]
) -> Found | None:
    """A document's words around the first of the question's words it holds, or None."""
    folded = text.casefold()
    at = min((folded.find(one) for one in words if one in folded), default=-1)
    if at < 0:
        return None
    start = max(0, at - PASSAGE_CHARS // 4)
    return Found(
        DOCUMENT, ident, name[:200] or "(untitled)", modified, text[start : start + PASSAGE_CHARS]
    )


# ------------------------------------------------------------------------ the read-back
@dataclass(frozen=True)
class Reply:
    """One Google reply, for the read-back."""

    status: int
    body: Any


def read_back_reading(operation: RestOperation, reply: Reply) -> Reading:
    """One Workspace reply as a read reads it: a refusal is not an empty answer."""
    call = classify(status=reply.status)
    if call is not CallOutcome.OK:
        return Reading(outcome=call, matched=0, complete=False)
    try:
        body = answered(reply.status, reply.body)
        if operation.operation.operation_id == "gmail_messages_list" and "messages" not in body:
            # Gmail's answer to a search nothing matches: it looked, and there is none.
            return Reading(outcome=CallOutcome.OK, matched=0, complete=True)
        # A read of one item answers the item itself, which the mapping reads as one row.
        rows = operation.project([body] if not operation.operation.records_at else body)
    except ConnectorContractError:
        return unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(rows), complete=True)


# ------------------------------------------------------------------------ the manifest
_TOOLS: Final[Mapping[Service, ToolDeclaration]] = {
    Service.MAIL: ToolDeclaration(
        name="google_workspace.find_mail",
        description="Find the asker's own email on a subject, read live from Gmail as them.",
        entity=MAIL,
        identity_mode=IdentityMode.DELEGATED,
    ),
    Service.CALENDAR: ToolDeclaration(
        name="google_workspace.find_events",
        description="Find events on the asker's own calendar, read live from Google as them.",
        entity=EVENT,
        identity_mode=IdentityMode.DELEGATED,
    ),
    Service.DOCUMENTS: ToolDeclaration(
        name="google_workspace.find_documents",
        description="Find Google Docs the asker may open, read live from Drive as them.",
        entity=DOCUMENT,
        identity_mode=IdentityMode.DELEGATED,
    ),
}


def manifest(connection: WorkspaceConnection, *, ref: SecretRef) -> ConnectorManifest:
    """Everything this connector declares for one connection: a tool per chosen service, each read
    as the asking person, and no projection at all. Read-only, and delegated: Google enforces
    each person's own access on every call."""
    return ConnectorManifest(
        name=CONNECTOR_NAME,
        version=VERSION,
        transport=TransportKind.REST,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=tuple(_TOOLS[one] for one in connection.services),
        projections=(),
        ceiling=CONNECTOR_NAME,
        permission_sync=PermissionSync.DELEGATED,
    )


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    return manifest(WorkspaceConnection.from_settings(settings), ref=ref)


# ------------------------------------------------------------------------ the consent
CONSENT: Final = OAuthConsent(
    authorize_url=AUTHORIZE_URL,
    token_url=EXCHANGE_URL,
    scopes=(GMAIL_SCOPE, CALENDAR_SCOPE, DRIVE_SCOPE),
    # Offline access is what makes Google issue a refresh token at all, and consent prompts it
    # again when a person reconnects, so a second consent is issued one too.
    authorize_params=(("access_type", "offline"), ("prompt", "consent")),
    client_id_setting=CLIENT_ID_SETTING,
    kind=ConsentKind.PERSON,
    reader=READER,
    chosen_by=SERVICES_SETTING,
    scope_of_choice=tuple((one.value, SCOPE_OF[one]) for one in Service),
)


# ------------------------------------------------------------------------ the console
#: What the slot is defined as asking for, which the form's hint quotes word for word.
ASKED_FOR: Final = (
    "the client secret of a Web application OAuth client",
    "gmail.readonly, calendar.readonly, drive.readonly, only for the services chosen",
    "a consent given by each person at Google for their own account",
)

CONSOLE: Final = ConsoleForm(
    settings=(
        Setting(
            name=CLIENT_ID_SETTING,
            label="OAuth client id",
            hint=(
                "The client id of the OAuth client you created for this system in the Google "
                "Cloud console, ending in .apps.googleusercontent.com."
            ),
            refused="That is not a Google OAuth client id. It ends in .apps.googleusercontent.com.",
        ),
        Setting(
            name=SERVICES_SETTING,
            label="Services each person's account is read for",
            hint=(
                "Any of mail, calendar and documents, separated by commas. A service left out is "
                "never read and its permission is never asked of anybody."
            ),
            refused="Name one or more of mail, calendar and documents, separated by commas.",
        ),
        Setting(
            name=DEPARTMENT_SETTING,
            label="Department whose people may connect their account",
            hint=(
                "The short name of the department whose people may be granted this, as the "
                "Departments page shows it. Each person is read only their own account."
            ),
            refused=(
                "That is not a department's short name. Use lower-case letters, digits and "
                "underscores, exactly as the Departments page shows it."
            ),
        ),
    ),
    credential_label="The OAuth client's secret",
    credential_hint=(
        "Copy the client secret of the same OAuth client. This connection asks for "
        + "; ".join(ASKED_FOR)
        + ". It is kept in the vault and never shown again; each person's own consent is given "
        "at Google, never here."
    ),
    build=built_from_the_console,
    example=ConnectExample(
        settings={
            CLIENT_ID_SETTING: "123456789012-abcdefgh12345678.apps.googleusercontent.com",
            SERVICES_SETTING: "mail, calendar, documents",
            DEPARTMENT_SETTING: "operations",
        },
        fresh=lambda departments: {
            CLIENT_ID_SETTING: (
                f"{secrets.randbelow(10**12):012d}-{secrets.token_hex(8)}.apps.googleusercontent.com"
            ),
            SERVICES_SETTING: "mail, calendar, documents",
            DEPARTMENT_SETTING: departments[0],
        },
        edit=SERVICES_SETTING,
        edited=lambda: "mail",
    ),
)

CLOUD_CONSOLE_URL: Final = "https://console.cloud.google.com/apis/credentials"

#: Google's published quotas, which the ceiling is recorded from.
GMAIL_QUOTA_URL: Final = "https://developers.google.com/workspace/gmail/api/reference/quota"
CALENDAR_QUOTA_URL: Final = "https://developers.google.com/workspace/calendar/api/guides/quota"

GUIDE: Final = keyed(
    (
        GuideStep(
            key="project",
            title="Switch on the APIs for the services you will read",
            text=(
                "In the Google Cloud console, in a project of your organisation, enable the Gmail "
                "API for mail, the Google Calendar API for calendar and the Google Drive API for "
                "documents. Enable only those you will choose."
            ),
            sketch=Sketch(place="Google Cloud", heading="APIs and services", button="Enable"),
            link=CLOUD_CONSOLE_URL,
            link_label="Open the Cloud console",
        ),
        GuideStep(
            key="consent_screen",
            title="Set the consent screen to Internal",
            text=(
                "Under OAuth consent screen choose Internal, so only your organisation's accounts "
                "can consent, and add the read-only scopes of the services you will read."
            ),
            sketch=Sketch(
                place="Google Cloud",
                heading="OAuth consent screen",
                lines=(SketchLine(LineKind.ITEM, "Internal", mark=True),),
            ),
        ),
        GuideStep(
            key="client",
            title="Create an OAuth client for this system",
            text=(
                "Under Credentials create an OAuth client id of type Web application, and add this "
                "console's address followed by /connector-consent as its authorised redirect URI."
            ),
            sketch=Sketch(
                place="Google Cloud",
                heading="Create OAuth client id",
                lines=(
                    SketchLine(LineKind.FIELD, "Redirect URI", "/connector-consent", mark=True),
                ),
                button="Create",
            ),
        ),
        GuideStep(
            key="connect",
            title="Paste the client id, choose the services, and paste the secret",
            text=(
                "Type the client id, the services and the department, paste the client secret, "
                "and press Connect Google Workspace. Each person then connects their own account "
                "from My workspace."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Google Workspace",
                lines=(
                    SketchLine(
                        LineKind.FIELD, "Client id", "...apps.googleusercontent.com", mark=True
                    ),
                    SketchLine(LineKind.FIELD, "Services", "mail, calendar", mark=True),
                    SketchLine(LineKind.FIELD, "Department", "operations", mark=True),
                    SketchLine(LineKind.FIELD, "Client secret", "********", mark=True),
                ),
                button="Connect Google Workspace",
            ),
            asks=(CLIENT_ID_SETTING, SERVICES_SETTING, DEPARTMENT_SETTING, CREDENTIAL_ASK),
        ),
    )
)

#: This source's verified rate ceiling, which `brain.ops.limits.connector_ceiling` finds on this
#: declaration. See `brain.ops.limits.A_CEILING_LIVES_WITH_ITS_CONNECTOR`.
CEILING: Final = ConnectorLimit(
    name=CONNECTOR_NAME,
    per_minute=300,
    per_day=1_000_000,
    raisable=True,
    note=(
        "Google sets a quota per service. Gmail allows 6,000 quota units a minute for one user of "
        "a project and 1,200,000 for the project; a message search costs 5 units and reading a "
        f"message 20 ({GMAIL_QUOTA_URL}). Calendar allows 600 requests a minute for one user and "
        f"10,000 for the project, and 1,000,000 calls a day before billing ({CALENDAR_QUOTA_URL}). "
        "Drive allows 325,000 units a minute for one user and an export costs 200 "
        "(https://developers.google.com/workspace/drive/api/guides/limits). Read 2026-10-06. "
        "Recorded at the dearest call a question makes, 300 message reads a minute, and "
        "Calendar's daily figure. A project owner may raise each on the Cloud console's Quotas "
        "page."
    ),
)


CONNECTOR: Final = ConnectorDeclaration(
    ceiling=CEILING,
    name=CONNECTOR_NAME,
    label="Google Workspace",
    guide=GUIDE,
    console=CONSOLE,
    read_back=ReadBack(
        reading=read_back_reading,
        recorded=(
            "GWS-200-messages",
            "GWS-200-messages-none",
            "GWS-200-message",
            "GWS-200-events",
            "GWS-200-files",
            "GWS-200-export",
            "GWS-token-200",
            "GWS-token-400",
            "GWS-200-error",
            "GWS-401",
            "GWS-429",
            "GWS-503",
        ),
        findings=(),
    ),
    recorded=Recorded(tested=True),
    # Each person's mail, events and documents are read live as passages for the question's model
    # step (`brain.ops.google_workspace_live.WorkspacePassages`), never classified or indexed.
    ask=AskRows(by_passages=True),
    oauth=CONSENT,
    scopes=KeyScopes(
        request=ASKED_FOR,
        refuse=(
            "any scope that writes or sends",
            "domain-wide delegation of a service account",
        ),
    ),
)
