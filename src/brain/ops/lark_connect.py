"""Connecting a company's own Lark app, from nothing: the steps, the scopes, the test, the switch.

The owner asked on 2026-09-21 for one thing: an administrator who has never created a Lark app
presses Connect Lark on the Connectors screen and is taken all the way to a working connection.
Four pieces of the product already speak to Lark (`brain.connectors.lark_wiki`,
`brain.connectors.lark_base`, `brain.channels.lark` and the staff list's Lark reader in
`brain.ops.staff_sync_run`) and none of them said how the app they all need comes to exist. This
module is that missing half: **what to click in Lark's developer console, which read-only scopes
each use needs, a test that tells a person exactly which scope is missing, and the settings a
chosen use is switched on with.** `brain.lark_connect_routes` serves it; this opens nothing.

**One app, one credential, several uses, and the scope list is the union of the uses chosen.** A
company creates one custom app and switches on what it wants: the staff list, knowledge from
Wiki, knowledge from Base, the chat channel. Each use names its scopes here once (`USES`), and
the steps a person is shown are built from the chosen uses, so a company that wants only the
staff list is never asked to grant the Wiki. See `A_SCOPE_IS_ASKED_FOR_ONLY_BY_A_USE_THAT_NEEDS_IT`.

**Every scope is read-only but one, and that one is named.** A chat bot that answers has to send
its own replies, so the chat channel asks for `im:message:send_as_bot` and the screen says it is
the one write. Nothing here asks for a scope that edits a document, a Base or a person.

**The test reads, and only reads.** It exchanges the app's identifier and secret for a tenant
token, which is Lark's one POST that changes nothing, and then makes one or two small GETs per
chosen use: a page size of one, and metadata rather than a document's body. It writes nothing
anywhere, here or in Lark, and it keeps nothing it read. See `THE_TEST_ONLY_READS`.

**A missing scope is named, because "permission denied" sends a person to guess.** Lark refuses a
call its token has no scope for with code 99991672 and lists the scopes that would have admitted
it; the test reports those, intersected with the use's own list, so the sentence says "add
contact:user.email:readonly" rather than "something is wrong". **Released and not released
cannot be told apart from outside**: a scope added in the console and not yet released answers
exactly like a scope never added. So a test where no chosen use got any scope reads as a version
not yet released and says both remedies in order, and a partial one names the scopes and reminds
that each addition needs a new version. See `A_SCOPE_NOT_RELEASED_LOOKS_LIKE_A_SCOPE_NOT_ADDED`.

**A scope Lark checks per field is tested by reading the field, because the call succeeds without
it.** The staff list's test read one person and called it working. On 2026-09-29 the owner's app
passed that and the night's sync then placed 123 people in no department: Lark admits the
department walk without `contact:department.base:readonly` and leaves each department's `name`
out. So the test reads one department as the sync does and names that scope when the name is
missing, and a refused department walk (the "no dept authority" the owner's first sync met) is
the data range, reported as such rather than hidden behind a person the root could list.

**Knowledge is switched on as configuration and never copied.** The owner's rule is that a
connector keeps a minimal index and reads content live at question time. Switching knowledge on
here writes which Base and which platform, as installation settings, and keeps the credential in
the vault; it registers no connection the sync worker would read and ingests nothing. The index
and the live reader are the Lark knowledge connector's to build over exactly these settings. See
`KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED`.

**The chat channel is received at the one events address, and switching it on writes the
channel's own record (M10.6.3).** Lark's events are verified with the app's Encrypt Key and
Verification Token (`brain.channels.lark.verify_event`), so those two are asked for beside the App
Secret, and the three are kept together at `providers/channel_lark`, the slot the application
reads when an event arrives, and never under `connector_keys/`, which it may not read. Saving
writes the channel's record with the App ID, the platform and the bot's own open id, the last read
from Lark's bot information, which is how a group message is known to be for the bot. The steps
put the save before Lark's Request URL, because Lark checks the address the moment it is entered
and this install answers that check only for a channel switched on with its keys held. See
`THE_CHANNEL_IS_SAVED_BEFORE_LARK_CHECKS_ITS_ADDRESS`.

Rejected: a scope list per use typed into the page. The test and the steps would then hold two
copies, and the one a person reads would drift from the one the test checks.

Rejected: testing with the credential already kept. The application may write a connector key
and never read one back (`brain.ops.credentials`), so the test takes the credential as it is
typed, before it is kept, and a re-test later asks for it again.

Task ids: M11.9.4, M11.9.1, M10.6.3, M10.4.3
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import quote, urlencode, urlsplit

from brain.connectors.staff_directories import (
    LARK_PLATFORMS,
    LARK_SCOPE_PURPOSE,
    LARK_SYNC_SCOPES,
    Answer,
    DirectorySignInError,
    Fetch,
    Outbound,
)
from brain.identity.staff_adapters import LARK_DEPARTMENT_NAME_SCOPE
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed

# ------------------------------------------------------------------ written-down reasons

#: Why the steps and the test are built from the uses chosen.
A_SCOPE_IS_ASKED_FOR_ONLY_BY_A_USE_THAT_NEEDS_IT: Final = (
    "Each use names the scopes it needs once, and the steps shown and the calls tested are built "
    "from the uses the person chose. A company that switches on only the staff list is never "
    "asked to grant its wiki, and a scope nobody chose is a scope nobody has to explain later."
)

#: What the test may send, and what it may not.
THE_TEST_ONLY_READS: Final = (
    "The test exchanges the app's identifier and secret for a tenant token, which changes nothing "
    "in Lark, and then makes small GET requests: a page size of one (the wiki's spaces are listed "
    "so they can be named), and a document's metadata rather than its body. It writes nothing "
    "in Lark and keeps nothing it read. Here it records only when it ran and each use's verdict "
    "in a word, so the card can say when Lark was last tested."
)

#: Why a test where nothing was granted reads as a version not released.
A_SCOPE_NOT_RELEASED_LOOKS_LIKE_A_SCOPE_NOT_ADDED: Final = (
    "Lark answers a scope that was added and not yet released exactly as it answers a scope never "
    "added, so the two cannot be told apart from outside. A test where no chosen use was granted "
    "anything is most often an app whose version was never released or approved, and it says so "
    "first; a partial one names the missing scopes and reminds that every addition needs a new "
    "version released."
)

#: What switching knowledge on writes, and what it never does.
KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED: Final = (
    "Switching on knowledge from Wiki or Base keeps the app's credential in the vault and records "
    "which platform and which Base, as installation settings. It registers no connection for the "
    "sync worker and copies no page, row or document into this system: the connector keeps a "
    "minimal index and reads content live from Lark when a question needs it."
)

#: Why the chat channel is saved here before its address is entered in Lark.
THE_CHANNEL_IS_SAVED_BEFORE_LARK_CHECKS_ITS_ADDRESS: Final = (
    "Lark checks the Request URL the moment it is saved there, by sending an encrypted challenge "
    "this install answers only for a chat channel that is switched on with its Encrypt Key and "
    "Verification Token held. So the chat channel is saved here first, with both keys, and the "
    "address below is entered in Lark after; entered before, Lark reports that it could not be "
    "verified."
)

#: What the chat channel does once it is on, in one sentence for the screen.
THE_CHANNEL_ANSWERS_AT_EACH_READERS_OWN_REACH: Final = (
    "A person who has linked their Lark account is answered in a direct message as Ask answers "
    "them on the web. In a group, the room is answered only with what everybody in it may see, and "
    "the person who asked reads their own answer in a card only they see, or a link to Ask. "
    "Somebody not linked yet is told once how to link, in their own chat with the bot."
)

#: The one event the chat channel subscribes to, in Lark's own name for it.
MESSAGE_EVENT: Final = "im.message.receive_v1"

# --------------------------------------------------------------------- the figures

#: Lark's code for a call whose token lacks a scope. The message lists the scopes that admit it.
MISSING_SCOPE_CODE: Final = 99991672

#: Codes Lark answers when the token itself is not accepted.
TOKEN_REFUSED_CODES: Final = frozenset({99991661, 99991663, 99991668})

#: Codes Lark answers when the app is not a member of the document or Base it asked about.
NOT_SHARED_CODES: Final = frozenset({91402, 91403, 131006, 1254302, 1254040, 1254003})

#: The separator between the app's identifier and its secret in the one kept value, which is the
#: shape the staff list's reader already splits (`staff_sync_run.CLIENT_CREDENTIAL_SEPARATOR`).
CREDENTIAL_SEPARATOR: Final = ":"

#: A Lark app's identifier, which the developer console always prints starting `cli_`.
APP_ID: Final = re.compile(r"^cli_[A-Za-z0-9]{4,60}$")

#: A Base token, as it appears in a Base's link after `/base/`.
BASE_TOKEN: Final = re.compile(r"^[A-Za-z0-9]{8,64}$")
_BASE_IN_LINK: Final = re.compile(r"/base/([A-Za-z0-9]{8,64})")

#: A scope name as Lark writes it inside a refusal: words joined by colons.
_SCOPE_IN_TEXT: Final = re.compile(r"[a-z]+(?::[a-z_.]+)+")

#: How many of the app's wiki spaces the test lists, for the step that declares each one. A
#: space beyond these is declared by pasting its link.
SPACES_LISTED: Final = 50

#: A chat id that names no chat, which the chat channel's test asks the members of. See `_channel`.
MEMBERS_CHECK_CHAT: Final = "oc_brain_connect_check"

#: The scope a group question reads who is present with.
MEMBERS_SCOPE: Final = "im:chat.members:read"

#: The scope a wiki page's permission settings are read with, which is how the Lark Wiki
#: connector knows whether a page was restricted (`brain.connectors.lark_wiki.restriction_of`).
WIKI_PERMISSION_SCOPE: Final = "docs:permission.setting:read"

#: The one path the chat channel's events arrive at, under the install's own address.
LARK_EVENTS_PATH: Final = "/api/v1/channels/lark/events"

#: The console's Ask page, which a chat's link names.
ASK_PATH: Final = "/ask"


class Use(enum.StrEnum):
    """What the company's Lark app can be switched on for."""

    STAFF_LIST = "staff_list"
    WIKI = "knowledge_wiki"
    BASE = "knowledge_base"
    CHANNEL = "chat_channel"


class Verdict(enum.StrEnum):
    """What testing one use came to."""

    WORKING = "working"
    MISSING_SCOPE = "missing_scope"
    NOT_RELEASED = "not_released"
    NOT_SHARED = "not_shared"
    NEEDS_SETTING = "needs_setting"
    CREDENTIAL_REFUSED = "credential_refused"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class Scope:
    """One Lark scope: its exact name, what it lets the app do, and whether it only reads."""

    name: str
    what: str
    read_only: bool = True


@dataclass(frozen=True)
class UseSpec:
    """One use: its words, its scopes, the vault slot its credential is kept in, its extra steps."""

    use: Use
    label: str
    what: str
    scopes: tuple[Scope, ...]
    #: The connector key slot the credential is kept in for this use, `connector_keys/<slot>`.
    slot: str
    #: What else has to be done in Lark for this use, in click order.
    extra: tuple[str, ...]


def _contact_scopes() -> tuple[Scope, ...]:
    # Read out of the staff sync's own constants, so the scopes this screen asks for are the ones
    # its reader was written against, and a scope added there is asked for here.
    return tuple(Scope(name, LARK_SCOPE_PURPOSE[name]) for name in LARK_SYNC_SCOPES.split())


#: Every use, with the scopes it needs. See `A_SCOPE_IS_ASKED_FOR_ONLY_BY_A_USE_THAT_NEEDS_IT`.
USES: Final[Mapping[Use, UseSpec]] = MappingProxyType(
    {
        Use.STAFF_LIST: UseSpec(
            use=Use.STAFF_LIST,
            label="Staff list",
            what=(
                "Read who works here, their work email, their departments, managers and user "
                "groups from Lark's directory, on a schedule, so people join and leave the Brain "
                "as they do in Lark."
            ),
            scopes=_contact_scopes(),
            slot="staff_source",
            extra=(
                "Still under Permissions & Scopes, find the data range for contacts (Lark may "
                "call it the contacts range or range of accessible data) and choose All members. "
                "Without it the app can read nobody, and the test says so.",
            ),
        ),
        Use.WIKI: UseSpec(
            use=Use.WIKI,
            label="Knowledge from Wiki",
            what=(
                "Answer questions from the wiki spaces you share with the app. The Brain keeps a "
                "small index (titles, where each page lives, who may see it) and reads a page "
                "live from Lark when a question needs it."
            ),
            scopes=(
                Scope("wiki:wiki:readonly", "list wiki spaces and pages"),
                Scope("docx:document:readonly", "read a page when a question needs it"),
                Scope(
                    WIKI_PERMISSION_SCOPE,
                    "read whether a page was restricted, so nobody is answered from a page "
                    "they cannot open",
                ),
            ),
            slot="lark_wiki",
            extra=(
                "After the version is released, share each wiki space with the app. Lark gives "
                "an app a space through a group: create or pick a group chat, add the app's bot "
                "to it, then in the wiki space open Settings, Member settings, Add members, and "
                "add that group with permission to view.",
            ),
        ),
        Use.BASE: UseSpec(
            use=Use.BASE,
            label="Knowledge from Base",
            what=(
                "Answer questions from one Lark Base you name. The Brain keeps a small index of "
                "its records and reads the values live from Lark when a question needs them."
            ),
            scopes=(
                Scope("bitable:app:readonly", "read the Base's tables and records"),
                Scope("base:record:read", "read a record when a question needs it"),
            ),
            slot="lark_base",
            extra=(
                "After the version is released, open the Base, click the three dots at the top "
                "right, choose More, then Add document app (Lark may call it Add Doc App), search "
                "for the app by its name and add it with permission to view.",
                "Copy the Base's link from the browser and paste it below: the Brain reads the "
                "token after /base/ and nothing else from it.",
            ),
        ),
        Use.CHANNEL: UseSpec(
            use=Use.CHANNEL,
            label="Chat channel",
            what=(
                "Let people ask the Brain in Lark chats: a direct message to the bot, or a "
                "mention of it in a group. A group is answered only with what everyone in it may "
                "see, and the asker reads the rest privately."
            ),
            scopes=(
                Scope("im:message.p2p_msg:readonly", "receive direct messages sent to the bot"),
                Scope(
                    "im:message.group_at_msg:readonly",
                    "receive group messages that mention the bot, and no others",
                ),
                Scope(
                    MEMBERS_SCOPE,
                    "read who is in a group, so what the room reads fits everyone in it",
                ),
                Scope(
                    "im:message:send_as_bot",
                    "send the bot's own replies and the cards only one person sees. The one "
                    "scope that writes: it posts as the bot and cannot read or change anybody "
                    "else's messages",
                    read_only=False,
                ),
            ),
            # The authority a chat channel is governed by, `admin:connector` over this name, which
            # `brain.channel_routes` asks too. Its secret is not kept here: see the module.
            slot="lark_channel",
            extra=(
                "In the left menu open Add Features (or Features), choose Bot, and turn it on. "
                "The chat scopes only work for an app that has a bot.",
                "In the left menu open Events & Callbacks, then the Encryption Strategy tab. If "
                "the Encrypt Key is empty, click Reset (or Generate) to make one. Copy the Encrypt "
                "Key and the Verification Token and paste both below with the App ID and App "
                "Secret. They are kept in the vault with the secret and never shown again.",
                "Press Save below now, before the next step. "
                + THE_CHANNEL_IS_SAVED_BEFORE_LARK_CHECKS_ITS_ADDRESS,
                "Back in Events & Callbacks, open the Event Configuration tab. Set the "
                "subscription mode to sending events to your server (Lark calls it Request URL, "
                "or Send events to developer server), paste this install's events address shown "
                "below, and click Save. Lark checks the address at once and shows it as verified.",
                f"Still on Event Configuration, click Add Events, search for {MESSAGE_EVENT} "
                "(Lark lists it as Message received, or Receive messages v2.0), tick it and click "
                "Add. It is the only event the Brain needs. If Lark asks to add the scopes the "
                "event requires, accept: they are the two receiving scopes above.",
                "After the version is approved, open Lark, search for the app by its name, open "
                "a chat with its bot and send hello. The bot answers once with how to link your "
                "account. Link it from your profile in the console with a one-time code sent to "
                "the bot, then ask a question. To use it in a group, open the group's settings, "
                "choose Bots, add the app's bot, and mention it in a question.",
            ),
        ),
    }
)


# ------------------------------------------------------------------------ the steps

#: Why the flow asks for the App ID third, before anything else is done in Lark.
THE_APP_ID_OPENS_EVERY_LATER_PAGE: Final = (
    "Lark's developer console gives each app its own pages under the App ID. Asked for as soon as "
    "the app exists, it turns every later step into a link that opens the exact page, so nobody "
    "has to find the app again in a list and then the menu entry inside it."
)

#: Why a permission needs a released version, said on the steps that add one.
A_PERMISSION_WORKS_ONLY_ONCE_ITS_VERSION_IS_APPROVED: Final = (
    "A permission added in Lark takes effect only once a new version of the app is released and "
    "approved, so every addition is followed by the release step, and a test that finds a "
    "permission missing sends you to both."
)


class StepKey(enum.StrEnum):
    """Every screen of Connect Lark, by the key a test's verdict sends a person back to."""

    CHOOSE = "choose"
    CREATE = "create"
    CREDENTIALS = "credentials"
    BOT = "bot"
    PERMISSIONS = "permissions"
    EVENTS_KEYS = "events_keys"
    EVENTS_ADDRESS = "events_address"
    RELEASE = "release"
    SHARE_WIKI = "share_wiki"
    SHARE_BASE = "share_base"
    TEST = "test"
    WIKI_SPACES = "wiki_spaces"
    BASE_ACCESS = "base_access"


#: The developer console's own page for each step, under an app's id, as its address bar shows
#: them in September 2026. Every step still names the menu entry in words, so a page Lark moves
#: is found by its name; the link only saves the search.
APP_PAGES: Final[Mapping[StepKey, str]] = MappingProxyType(
    {
        StepKey.CREDENTIALS: "baseinfo",
        StepKey.BOT: "bot",
        StepKey.PERMISSIONS: "auth",
        StepKey.EVENTS_KEYS: "event",
        StepKey.EVENTS_ADDRESS: "event",
        StepKey.RELEASE: "version",
    }
)

#: The left menu of an app in Lark's developer console, in the order it is drawn.
CONSOLE_MENU: Final = (
    "Credentials & Basic Info",
    "Add Features",
    "Permissions & Scopes",
    "Events & Callbacks",
    "Version Management & Release",
)

#: The two tabs of Events & Callbacks a step sends somebody to.
EVENT_TABS: Final = ("Event Configuration", "Encryption Strategy")

#: What each screen collects, by the field names the routes judge. See `brain.ops.connect_steps`.
ASKS: Final[Mapping[StepKey, tuple[str, ...]]] = MappingProxyType(
    {
        StepKey.CHOOSE: ("uses", "platform"),
        StepKey.CREDENTIALS: ("app_id", "app_secret"),
        StepKey.PERMISSIONS: ("scopes",),
        StepKey.EVENTS_KEYS: ("encrypt_key", "verification_token", "save_channel"),
        StepKey.EVENTS_ADDRESS: ("events_address",),
        StepKey.SHARE_BASE: ("base_link",),
        StepKey.TEST: ("test", "save"),
        StepKey.WIKI_SPACES: ("spaces",),
    }
)


def developer_console(platform: str) -> str:
    """The developer console's address on the chosen platform, or Lark's when none is chosen."""
    _, open_host = LARK_PLATFORMS.get(platform, LARK_PLATFORMS["larksuite.com"])
    return f"https://{open_host}/app"


def app_page(platform: str, app_id: str, step: StepKey) -> str:
    """The app's own page for a step, or the console's app list until a real App ID is known.

    An App ID that is not the shape Lark prints is never put into an address, so what somebody
    typed cannot become a link somewhere else. See `THE_APP_ID_OPENS_EVERY_LATER_PAGE`.
    """
    page = APP_PAGES.get(step)
    ident = app_id.strip()
    if page is None or not APP_ID.fullmatch(ident):
        return developer_console(platform)
    return f"{developer_console(platform)}/{ident}/{page}"


def scopes_for(uses: Iterable[Use]) -> tuple[Scope, ...]:
    """Every scope the chosen uses need, each once, in the order the uses name them."""
    seen: dict[str, Scope] = {}
    for use in Use:
        if use in set(uses):
            for one in USES[use].scopes:
                seen.setdefault(one.name, one)
    return tuple(seen.values())


#: The shape Lark's batch import of scopes reads, which is the shape its own export writes: the
#: app's scopes under `tenant`, and none under `user`, because the Brain asks for no user scope.
SCOPE_IMPORT_KEYS: Final = ("scopes", "tenant", "user")


def scope_import(uses: Iterable[Use]) -> str:
    """Every scope the chosen uses need, as the text Lark's batch import of scopes accepts.

    Pasted once instead of adding each scope by hand. The list is `scopes_for`, so it is exactly
    what the test checks and what the one-by-one list beside it shows.
    """
    scopes, tenant, user = SCOPE_IMPORT_KEYS
    names = [one.name for one in scopes_for(uses)]
    return json.dumps({scopes: {tenant: names, user: []}}, indent=2)


def _console_sketch(
    menu_mark: str,
    heading: str,
    *,
    lines: tuple[SketchLine, ...] = (),
    button: str = "",
    tabs: tuple[str, ...] = (),
    tab_mark: str = "",
) -> Sketch:
    return Sketch(
        place="Lark developer console",
        heading=heading,
        menu=CONSOLE_MENU,
        menu_mark=menu_mark,
        tabs=tabs,
        tab_mark=tab_mark,
        lines=lines,
        button=button,
    )


def _choose(chosen: Sequence[Use]) -> GuideStep:
    return GuideStep(
        key=StepKey.CHOOSE,
        title="Choose what the Lark app is for",
        text=(
            "Tick each thing the Lark app should do here. One app does all of them, and you can "
            "add another use later from the same card. Choose feishu.cn if your company's Lark "
            "is Feishu."
        ),
        sketch=Sketch(
            place="Company Brain",
            heading="What the Lark app is for",
            lines=tuple(
                SketchLine(LineKind.ITEM, USES[use].label, mark=use in chosen) for use in Use
            ),
        ),
        asks=ASKS[StepKey.CHOOSE],
    )


def _create(platform: str) -> GuideStep:
    return GuideStep(
        key=StepKey.CREATE,
        title="Create the app in Lark",
        text=(
            "Open Lark's developer console and sign in with an account that may create apps for "
            "your company, usually a Lark administrator. Click Create Custom App, give it the "
            "name your staff will see when it answers and a one-line description such as "
            "'Answers questions from our own documents', then click Create."
        ),
        sketch=Sketch(
            place="Lark developer console",
            heading="My apps",
            lines=(SketchLine(LineKind.TEXT, "Custom apps"),),
            button="Create Custom App",
        ),
        link=developer_console(platform),
        link_label="Open Lark's developer console",
    )


def _credentials(platform: str, app_id: str) -> GuideStep:
    return GuideStep(
        key=StepKey.CREDENTIALS,
        title="Paste the App ID and App Secret",
        text=(
            "In the app's left menu open Credentials & Basic Info. Copy the App ID (it starts with "
            "cli_) and the App Secret (click the eye or the copy icon) and paste both here. With "
            "the App ID, every later step opens its own page in Lark. The secret goes to the vault "
            "when you save and is never shown again, and it is not kept by this page if you close "
            "it."
        ),
        sketch=_console_sketch(
            "Credentials & Basic Info",
            "Credentials & Basic Info",
            lines=(
                SketchLine(LineKind.FIELD, "App ID", "cli_...", mark=True),
                SketchLine(LineKind.FIELD, "App Secret", "********", mark=True),
            ),
        ),
        link=app_page(platform, app_id, StepKey.CREDENTIALS),
        link_label="Open Credentials & Basic Info",
        asks=ASKS[StepKey.CREDENTIALS],
    )


def _bot(platform: str, app_id: str) -> GuideStep:
    return GuideStep(
        key=StepKey.BOT,
        title="Turn on the bot",
        text=USES[Use.CHANNEL].extra[0],
        sketch=_console_sketch(
            "Add Features",
            "Add Features",
            lines=(SketchLine(LineKind.ITEM, "Bot", mark=True),),
            button="Add",
        ),
        link=app_page(platform, app_id, StepKey.BOT),
        link_label="Open Add Features",
    )


def _permissions(chosen: Sequence[Use], platform: str, app_id: str) -> GuideStep:
    staff = Use.STAFF_LIST in chosen
    names = [one.name for one in scopes_for(chosen)]
    shown = tuple(SketchLine(LineKind.ITEM, name) for name in names[:3])
    more = (SketchLine(LineKind.TEXT, f"and {len(names) - 3} more"),) if len(names) > 3 else ()
    staff_range = (
        (SketchLine(LineKind.FIELD, "Contacts range", "All members", mark=True),) if staff else ()
    )
    return GuideStep(
        key=StepKey.PERMISSIONS,
        title="Add the permissions",
        text=(
            "In the app's left menu open Permissions & Scopes. Press Copy all permissions below, "
            "then in Lark click Batch import (Lark may call it Import scopes), paste, and confirm. "
            "If your Lark offers no batch import, add each permission in the list below: search "
            "its exact name and click Add. Every one only reads except im:message:send_as_bot, "
            "which sends the bot's own replies."
            + (" " + USES[Use.STAFF_LIST].extra[0] if staff else "")
            + " "
            + A_PERMISSION_WORKS_ONLY_ONCE_ITS_VERSION_IS_APPROVED
        ),
        sketch=_console_sketch(
            "Permissions & Scopes",
            "Permissions & Scopes",
            lines=shown + more + staff_range,
            button="Batch import",
        ),
        link=app_page(platform, app_id, StepKey.PERMISSIONS),
        link_label="Open Permissions & Scopes",
        asks=ASKS[StepKey.PERMISSIONS],
    )


def _events_keys(platform: str, app_id: str) -> GuideStep:
    return GuideStep(
        key=StepKey.EVENTS_KEYS,
        title="Copy the chat channel's two keys, then save it here",
        text=(
            "In the app's left menu open Events & Callbacks, then the Encryption Strategy tab. If "
            "the Encrypt Key is empty, click Reset to make one. Paste the Encrypt Key and the "
            "Verification Token here, then press Save the chat channel now. "
            + THE_CHANNEL_IS_SAVED_BEFORE_LARK_CHECKS_ITS_ADDRESS
        ),
        sketch=_console_sketch(
            "Events & Callbacks",
            "Events & Callbacks",
            tabs=EVENT_TABS,
            tab_mark="Encryption Strategy",
            lines=(
                SketchLine(LineKind.FIELD, "Encrypt Key", "********", mark=True),
                SketchLine(LineKind.FIELD, "Verification Token", "********", mark=True),
            ),
            button="Reset",
        ),
        link=app_page(platform, app_id, StepKey.EVENTS_KEYS),
        link_label="Open Events & Callbacks",
        asks=ASKS[StepKey.EVENTS_KEYS],
    )


def _events_address(platform: str, app_id: str) -> GuideStep:
    return GuideStep(
        key=StepKey.EVENTS_ADDRESS,
        title="Point Lark's events at this install",
        text=(
            "Still in Events & Callbacks, open the Event Configuration tab. Choose to send events "
            "to the developer server (Lark calls it Request URL), paste this install's events "
            "address shown below and click Save; Lark checks it at once and shows it as verified. "
            f"Then click Add Events, search for {MESSAGE_EVENT} (Lark lists it as Message "
            "received), tick it and click Add. It is the only event the Brain needs; if Lark asks "
            "to add the scopes it requires, accept."
        ),
        sketch=_console_sketch(
            "Events & Callbacks",
            "Events & Callbacks",
            tabs=EVENT_TABS,
            tab_mark="Event Configuration",
            lines=(
                SketchLine(LineKind.FIELD, "Request URL", "Your events address", mark=True),
                SketchLine(LineKind.ITEM, MESSAGE_EVENT),
            ),
            button="Add Events",
        ),
        link=app_page(platform, app_id, StepKey.EVENTS_ADDRESS),
        link_label="Open Events & Callbacks",
        asks=ASKS[StepKey.EVENTS_ADDRESS],
    )


def _release(platform: str, app_id: str) -> GuideStep:
    return GuideStep(
        key=StepKey.RELEASE,
        title="Release a version and have it approved",
        text=(
            "In the app's left menu open Version Management & Release and click Create a version. "
            "Enter a version number such as 1.0.0, set who may use the app to All members, write "
            "a short note such as 'Company Brain, read-only', then Save and Submit for release. "
            "Lark sends it to your workspace administrator, who approves it in the Lark Admin "
            "Console under app review; if you are the administrator, Lark may release it at once. "
            "Permissions take effect only after approval, and every later change to them needs a "
            "new version released the same way."
        ),
        sketch=_console_sketch(
            "Version Management & Release",
            "Version Management & Release",
            lines=(
                SketchLine(LineKind.FIELD, "Version", "1.0.0"),
                SketchLine(LineKind.FIELD, "Availability", "All members", mark=True),
            ),
            button="Create a version",
        ),
        link=app_page(platform, app_id, StepKey.RELEASE),
        link_label="Open Version Management & Release",
    )


def _share_wiki() -> GuideStep:
    return GuideStep(
        key=StepKey.SHARE_WIKI,
        title="Share your wiki spaces with the app",
        text=USES[Use.WIKI].extra[0],
        sketch=Sketch(
            place="Lark Wiki",
            heading="Space settings",
            tabs=("Basic settings", "Member settings"),
            tab_mark="Member settings",
            lines=(SketchLine(LineKind.ITEM, "Group with the app's bot", "Can view", mark=True),),
            button="Add members",
        ),
    )


def _share_base() -> GuideStep:
    scopes = " and ".join(one.name for one in USES[Use.BASE].scopes)
    return GuideStep(
        key=StepKey.SHARE_BASE,
        title="Share the Base with the app and paste its link",
        text=(
            f"The app reads a Base with {scopes}, which the permissions you added include, and "
            "only once a version with them is released. "
            f"{USES[Use.BASE].extra[0]} {USES[Use.BASE].extra[1]} Knowledge from Base must be "
            "ticked on the first step; the Base is switched on when you save on the test step."
        ),
        sketch=Sketch(
            place="Lark Base",
            heading="More",
            lines=(
                SketchLine(LineKind.ITEM, "Add document app", mark=True),
                SketchLine(LineKind.FIELD, "Link", ".../base/...", mark=True),
            ),
            button="Add",
        ),
        asks=ASKS[StepKey.SHARE_BASE],
    )


def _test(chosen: Sequence[Use]) -> GuideStep:
    chat = Use.CHANNEL in chosen
    return GuideStep(
        key=StepKey.TEST,
        title="Test, then save",
        text=(
            "Press Test connection. Each use you chose says it works, or which step to go back to "
            "and what to change there. When they work, press Save and switch on."
            + (
                " For the chat channel this save also records the bot's own id, which is how a "
                "group message is known to be for it. Then open Lark, search for the app by its "
                "name, open a chat with its bot and send hello: it answers once with how to link "
                "your account."
                if chat
                else ""
            )
        ),
        sketch=Sketch(
            place="Company Brain",
            heading="Test, then save",
            lines=tuple(
                SketchLine(LineKind.ITEM, USES[use].label, "Working", mark=True)
                for use in Use
                if use in chosen
            ),
            button="Test connection",
        ),
        asks=ASKS[StepKey.TEST],
    )


def _wiki_spaces() -> GuideStep:
    return GuideStep(
        key=StepKey.WIKI_SPACES,
        title="Say who may read each wiki space",
        text=(
            "For each wiki space shared with the app, choose who on this install may be told "
            "its pages: the whole company, or one department. A space nobody declares here is "
            "never read, and you are the steward of each space you declare. The test lists the "
            "spaces Lark shows the app; for one it does not show, paste the link of the space's "
            "settings page, which contains /wiki/space/ and a number."
        ),
        sketch=Sketch(
            place="Company Brain",
            heading="Wiki spaces",
            lines=(
                SketchLine(LineKind.FIELD, "A shared space", "The whole company", mark=True),
                SketchLine(LineKind.FIELD, "Another space", "One department", mark=True),
            ),
            button="Save the spaces",
        ),
        asks=ASKS[StepKey.WIKI_SPACES],
    )


#: Where a person is granted a Base's tables, and where each table is listed by its title.
PEOPLE_SCREEN: Final = "/people"
CAPABILITIES_SCREEN: Final = "/capabilities"


def _base_access() -> GuideStep:
    return GuideStep(
        key=StepKey.BASE_ACCESS,
        title="Grant each table to the people who may read it",
        text=(
            "Within about five minutes of saving, the worker indexes the Base: the ids, names "
            "and dates of its records, never their values. Nobody reads a table until they are "
            "granted it. On Capabilities each table is listed by its own title, as "
            "read:lark_<table> to find its records and read:lark_<table>.* to read their values; "
            "grant them to a person from their page on People."
        ),
        sketch=Sketch(
            place="Company Brain",
            heading="Capabilities",
            lines=(
                SketchLine(LineKind.ITEM, "read:lark_<table>", "Find records", mark=True),
                SketchLine(LineKind.ITEM, "read:lark_<table>.*", "Read values", mark=True),
            ),
            button="Grant",
        ),
    )


def steps_for(uses: Sequence[Use], *, platform: str, app_id: str = "") -> tuple[GuideStep, ...]:
    """The screens from nothing to a working connection, for the uses chosen, in order.

    Fewer than the list they replace, because a screen now holds everything done on one Lark page:
    creating the app and opening the console are one, copying the credentials is pasting them,
    the contacts range is on the permissions page, and releasing and approving are one version.
    Once `app_id` is a real App ID, every step on one of the app's pages links straight to it.
    """
    chosen = [use for use in Use if use in set(uses)]
    chat = Use.CHANNEL in chosen
    found = [_choose(chosen), _create(platform), _credentials(platform, app_id)]
    if chat:
        found.append(_bot(platform, app_id))
    found.append(_permissions(chosen, platform, app_id))
    if chat:
        found += [_events_keys(platform, app_id), _events_address(platform, app_id)]
    found.append(_release(platform, app_id))
    if Use.WIKI in chosen:
        found.append(_share_wiki())
    if Use.BASE in chosen:
        found.append(_share_base())
    found.append(_test(chosen))
    if Use.WIKI in chosen:
        found.append(_wiki_spaces())
    if Use.BASE in chosen:
        found.append(_base_access())
    return keyed(tuple(found))


def install_origin(redirect_uris: str) -> str:
    """This install's public origin, from the first redirect URI, or empty when it names none.

    Public because every address a vendor is told to post to is built on it: Lark's here, and
    every other channel's in `brain.channel_routes`.
    """
    first = next((one.strip() for one in redirect_uris.split(",") if one.strip()), "")
    parts = urlsplit(first)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def events_address(redirect_uris: str) -> str:
    """Where Lark sends the chat channel's events: the install's own origin and one path.

    Built from `INSTALL_OIDC_REDIRECT_URIS`, the one installation setting that already names this
    install's public address, so no second setting can disagree with it. Empty when it names none.
    """
    origin = install_origin(redirect_uris)
    return f"{origin}{LARK_EVENTS_PATH}" if origin else ""


def ask_address(redirect_uris: str) -> str:
    """The console's Ask page on this install, where a chat's link sends somebody to be answered.

    From the same setting as `events_address`, for its reason. The page carries no answer and no
    question, so following it runs the gate again for whoever follows it (M10.4.3).
    """
    origin = install_origin(redirect_uris)
    return f"{origin}{ASK_PATH}" if origin else ""


# ------------------------------------------------------------------------ judging input


@dataclass(frozen=True)
class Problem:
    """One thing wrong with what was sent: the field, a stable code, and what to do."""

    field: str
    code: str
    message: str


def base_token(link: str) -> str:
    """The Base token out of a Base's link or a bare token, or empty when neither is there."""
    given = link.strip()
    if BASE_TOKEN.fullmatch(given):
        return given
    found = _BASE_IN_LINK.search(given)
    return found.group(1) if found else ""


def uses_from(names: Iterable[str]) -> tuple[tuple[Use, ...], tuple[Problem, ...]]:
    """The uses named, in `Use` order, and a problem for a name that is not one."""
    known = {one.value: one for one in Use}
    unknown = sorted({name for name in names if name not in known})
    chosen = tuple(use for use in Use if use.value in set(names))
    problems = tuple(
        Problem("uses", "unknown", f"{name!r} is not something the Lark app can be used for.")
        for name in unknown
    )
    if not chosen and not unknown:
        problems = (Problem("uses", "blank", "Choose at least one use to switch on."),)
    return chosen, problems


def _one_piece(value: str) -> bool:
    return len(value) <= 200 and not any(one.isspace() or not one.isprintable() for one in value)


def _chat_key_problems(encrypt_key: str, verification_token: str) -> list[Problem]:
    """The chat channel's two event keys: present and each one piece. Never repeated back."""
    found: list[Problem] = []
    for name, value, where in (
        ("encrypt_key", encrypt_key.strip(), "Encrypt Key"),
        ("verification_token", verification_token.strip(), "Verification Token"),
    ):
        if not value:
            found.append(
                Problem(
                    name,
                    "blank",
                    f"Paste the {where} from Events & Callbacks, Encryption Strategy. Events are "
                    "refused without it.",
                )
            )
        elif not _one_piece(value):
            found.append(
                Problem(
                    name, "shape", f"That is not one {where}. Copy it again with the copy icon."
                )
            )
    return found


def input_problems(
    *,
    app_id: str,
    app_secret: str,
    uses: Sequence[Use],
    platform: str,
    base_link: str,
    encrypt_key: str = "",
    verification_token: str = "",
) -> tuple[Problem, ...]:
    """Everything wrong with what was sent, at once: identifier, secret, platform, Base link, and
    for the chat channel its Encrypt Key and Verification Token.

    The secrets are judged for shape only (present, one piece, not too long): whether Lark accepts
    them is the test's and the first event's to say. Nothing here repeats what was typed.
    """
    found: list[Problem] = []
    if Use.CHANNEL in uses:
        found += _chat_key_problems(encrypt_key, verification_token)
    ident = app_id.strip()
    if not ident:
        found.append(Problem("app_id", "blank", "Paste the App ID from Credentials & Basic Info."))
    elif not APP_ID.fullmatch(ident):
        found.append(
            Problem(
                "app_id",
                "shape",
                "That is not a Lark App ID. It starts with cli_ and has no spaces: copy it again "
                "from Credentials & Basic Info.",
            )
        )
    secret = app_secret.strip()
    if not secret:
        found.append(
            Problem("app_secret", "blank", "Paste the App Secret from Credentials & Basic Info.")
        )
    elif len(secret) > 200 or any(one.isspace() or not one.isprintable() for one in secret):
        found.append(
            Problem(
                "app_secret",
                "shape",
                "That is not one App Secret: it has a space or a line break inside, or is far "
                "too long. Copy it again with the copy icon.",
            )
        )
    if platform not in LARK_PLATFORMS:
        found.append(Problem("platform", "unknown", f"Choose one of: {', '.join(LARK_PLATFORMS)}."))
    if Use.BASE in uses and not base_token(base_link):
        found.append(
            Problem(
                "base_link",
                "blank" if not base_link.strip() else "shape",
                "Paste the link of the Base to read, copied from the browser while the Base is "
                "open. It contains /base/ followed by the Base's token.",
            )
        )
    return tuple(found)


def credential_value(app_id: str, app_secret: str) -> str:
    """The one value kept in the vault for every chosen use: `<app id>:<app secret>`."""
    return f"{app_id.strip()}{CREDENTIAL_SEPARATOR}{app_secret.strip()}"


# ------------------------------------------------------------------------ the test


@dataclass(frozen=True)
class UseResult:
    """What testing one use came to: the verdict, a sentence saying what to do, missing scopes."""

    use: Use
    verdict: Verdict
    told: str
    missing: tuple[str, ...] = ()
    #: True when every call was answered and a field was left out, which is a scope Lark checks
    #: per field. Lark granted something, so this is never read as a version not released.
    answered: bool = False
    #: The wiki spaces Lark showed the app, as (id, name), for the step that declares them.
    spaces: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ProbeResult:
    """The token exchange and every chosen use. `token_ok` False means no use was tried."""

    token_ok: bool
    told: str
    uses: tuple[UseResult, ...]


def _code(answer: Answer) -> int:
    code = answer.body.get("code", 0)
    return code if isinstance(code, int) else -1


def _data(answer: Answer) -> Mapping[str, Any]:
    data = answer.body.get("data")
    return data if isinstance(data, Mapping) else {}


def _items(answer: Answer) -> tuple[Mapping[str, Any], ...]:
    items = _data(answer).get("items") or ()
    return (
        tuple(one for one in items if isinstance(one, Mapping)) if isinstance(items, list) else ()
    )


def missing_scopes(answer: Answer, spec: UseSpec) -> tuple[str, ...]:
    """The scopes Lark's refusal names that this use asks for, or every scope it asks for.

    Only a use's own scopes are ever named, so a refusal quoting some other scope cannot send a
    person to grant it. When the refusal names none of them, every scope the use needs is named,
    because each is one the person may not have added.
    """
    said = str(answer.body.get("msg", ""))
    wanted = {one.name for one in spec.scopes}
    named = tuple(dict.fromkeys(one for one in _SCOPE_IN_TEXT.findall(said) if one in wanted))
    return named or tuple(one.name for one in spec.scopes)


def _missing(spec: UseSpec, scopes: Sequence[str]) -> UseResult:
    names = ", ".join(scopes)
    return UseResult(
        use=spec.use,
        verdict=Verdict.MISSING_SCOPE,
        told=(
            f"Missing scope: {names}. Add it under Permissions & Scopes, then create and release "
            "a new version under Version Management & Release: an added scope works only once "
            "that version is approved."
        ),
        missing=tuple(scopes),
    )


def _refused_or_other(spec: UseSpec, answer: Answer, *, not_shared: str) -> UseResult | None:
    """The verdict for a refusal, or None when the answer was a success."""
    code = _code(answer)
    if answer.status == 200 and code == 0:
        return None
    if code == MISSING_SCOPE_CODE:
        return _missing(spec, missing_scopes(answer, spec))
    if code in NOT_SHARED_CODES or answer.status == 403:
        return UseResult(spec.use, Verdict.NOT_SHARED, not_shared)
    if code in TOKEN_REFUSED_CODES:
        return UseResult(
            spec.use,
            Verdict.CREDENTIAL_REFUSED,
            "Lark did not accept the app's token for this call. Check the App ID and App Secret.",
        )
    if answer.status in (429, 500, 502, 503, 504):
        return UseResult(
            spec.use, Verdict.UNREACHABLE, "Lark did not answer this call properly. Try again."
        )
    return UseResult(
        spec.use,
        Verdict.NOT_SHARED if answer.status == 404 else Verdict.UNREACHABLE,
        not_shared if answer.status == 404 else f"Lark refused this call (code {code}).",
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


async def _get(fetch: Fetch, base: str, path: str, token: str, **query: str) -> Answer:
    url = f"{base}{path}" + (f"?{urlencode(query)}" if query else "")
    return await fetch(Outbound("GET", url, _bearer(token)))


async def _staff(fetch: Fetch, base: str, token: str) -> UseResult:
    spec = USES[Use.STAFF_LIST]
    range_sentence = (
        "The app can read nobody in the directory. Under Permissions & Scopes set the data range "
        "for contacts to All members, then release a new version."
    )
    people = await _get(
        fetch,
        base,
        "/open-apis/contact/v3/users/find_by_department",
        token,
        department_id="0",
        department_id_type="open_department_id",
        page_size="1",
    )
    refused = _refused_or_other(spec, people, not_shared=range_sentence)
    if refused is not None:
        return refused
    # The department walk is the sync's first call, so it is read even when a person was: the
    # root can list people while the walk is refused, and a department can come back unnamed.
    departments = await _get(
        fetch,
        base,
        "/open-apis/contact/v3/departments/0/children",
        token,
        department_id_type="open_department_id",
        page_size="1",
    )
    refused = _refused_or_other(spec, departments, not_shared=range_sentence)
    if refused is not None:
        return refused
    found = _items(departments)
    if found and not str(found[0].get("name") or "").strip():
        return replace(_missing(spec, (LARK_DEPARTMENT_NAME_SCOPE,)), answered=True)
    if found or _items(people):
        return UseResult(spec.use, Verdict.WORKING, "Working: the app can read the staff list.")
    return UseResult(spec.use, Verdict.NOT_SHARED, range_sentence)


async def _wiki(fetch: Fetch, base: str, token: str) -> UseResult:
    spec = USES[Use.WIKI]
    unshared = "The app is in no wiki space yet. " + spec.extra[0]
    spaces = await _get(
        fetch, base, "/open-apis/wiki/v2/spaces", token, page_size=str(SPACES_LISTED)
    )
    refused = _refused_or_other(spec, spaces, not_shared=unshared)
    if refused is not None:
        return refused
    seen = tuple(
        (str(one.get("space_id") or ""), str(one.get("name") or ""))
        for one in _items(spaces)
        if one.get("space_id")
    )
    space = seen[0][0] if seen else ""
    if not space:
        return UseResult(spec.use, Verdict.NOT_SHARED, unshared)
    nodes = await _get(
        fetch,
        base,
        f"/open-apis/wiki/v2/spaces/{quote(space, safe='')}/nodes",
        token,
        page_size="1",
    )
    refused = _refused_or_other(spec, nodes, not_shared=unshared)
    if refused is not None:
        return refused
    node = next(iter(_items(nodes)), None)
    if node is None:
        return UseResult(
            spec.use,
            Verdict.WORKING,
            "Working: the app can list a wiki space, which has no page yet to check further.",
            spaces=seen,
        )
    node_token = str(node.get("node_token") or "")
    # The call `brain.connectors.lark_wiki.read_live` makes before it answers from a page.
    permission = await _get(
        fetch,
        base,
        f"/open-apis/drive/v2/permissions/{quote(node_token, safe='')}/public",
        token,
        type="wiki",
    )
    refused = _refused_or_other(spec, permission, not_shared=unshared)
    if refused is not None:
        # Only the permission scope can be missing here; the listing already worked.
        if refused.verdict is Verdict.MISSING_SCOPE:
            return _missing(spec, (WIKI_PERMISSION_SCOPE,))
        return refused
    if str(node.get("obj_type") or "") == "docx" and node.get("obj_token"):
        document = await _get(
            fetch,
            base,
            f"/open-apis/docx/v1/documents/{quote(str(node['obj_token']), safe='')}",
            token,
        )
        refused = _refused_or_other(spec, document, not_shared=unshared)
        if refused is not None:
            if refused.verdict is Verdict.MISSING_SCOPE:
                return _missing(spec, ("docx:document:readonly",))
            return refused
    return UseResult(
        spec.use,
        Verdict.WORKING,
        "Working: the app can list the wiki, see whether a page was restricted, and read a "
        "page's details.",
        spaces=seen,
    )


async def _base(fetch: Fetch, base: str, token: str, table_token: str) -> UseResult:
    spec = USES[Use.BASE]
    if not table_token:
        return UseResult(spec.use, Verdict.NEEDS_SETTING, "Paste the link of the Base to read.")
    unshared = "The app cannot open that Base yet. " + spec.extra[0]
    tables = await _get(
        fetch,
        base,
        f"/open-apis/bitable/v1/apps/{quote(table_token, safe='')}/tables",
        token,
        page_size="1",
    )
    refused = _refused_or_other(spec, tables, not_shared=unshared)
    if refused is not None:
        return refused
    return UseResult(spec.use, Verdict.WORKING, "Working: the app can open the Base.")


async def _channel(fetch: Fetch, base: str, token: str) -> UseResult:
    """The bot, and the one scope a question in a group reads with, checked without a chat.

    The members read is asked of a chat that does not exist, so it reads nobody: Lark checks a
    token's scope before it looks for the chat, so a missing scope answers with its code and a
    granted one with the chat not being found. **If Lark ever looked for the chat first, this
    would say working with the scope missing, and the first group question would fall back to the
    asker's own private answer, never to a wider one.** The two receiving scopes cannot be asked
    about from outside at all; the first message is their test, and Events arriving says so.
    """
    spec = USES[Use.CHANNEL]
    bot = await _get(fetch, base, "/open-apis/bot/v3/info", token)
    no_bot = "The app has no bot yet. " + spec.extra[0]
    refused = _refused_or_other(spec, bot, not_shared=no_bot)
    if refused is not None:
        if refused.verdict is Verdict.MISSING_SCOPE:
            return UseResult(spec.use, Verdict.NOT_SHARED, no_bot)
        return refused
    if not isinstance(bot.body.get("bot"), Mapping):
        return UseResult(spec.use, Verdict.NOT_SHARED, no_bot)
    members = await _get(
        fetch, base, f"/open-apis/im/v1/chats/{MEMBERS_CHECK_CHAT}/members", token, page_size="1"
    )
    code = _code(members)
    if code == MISSING_SCOPE_CODE:
        return _missing(spec, (MEMBERS_SCOPE,))
    if code in TOKEN_REFUSED_CODES:
        return UseResult(
            spec.use,
            Verdict.CREDENTIAL_REFUSED,
            "Lark did not accept the app's token for this call. Check the App ID and App Secret.",
        )
    if members.status in (429, 500, 502, 503, 504):
        return UseResult(
            spec.use, Verdict.UNREACHABLE, "Lark did not answer this call properly. Try again."
        )
    return UseResult(
        spec.use,
        Verdict.WORKING,
        "Working: the bot is on and may read who is in a group. The two receiving scopes are "
        "checked by Lark when the first message arrives: send the bot a direct message and watch "
        "Events arriving on this card.",
    )


async def _tenant_token(fetch: Fetch, base: str, app_id: str, app_secret: str) -> str | None:
    """A tenant token for this app, or None when Lark did not give one. Changes nothing."""
    exchanged = await fetch(
        Outbound(
            "POST",
            f"{base}/open-apis/auth/v3/tenant_access_token/internal",
            {"Content-Type": "application/json"},
            json_body={"app_id": app_id.strip(), "app_secret": app_secret.strip()},
        )
    )
    token = exchanged.body.get("tenant_access_token")
    if exchanged.status != 200 or _code(exchanged) != 0 or not isinstance(token, str) or not token:
        return None
    return token


async def bot_open_id(
    fetch: Fetch, *, platform: str, app_id: str, app_secret: str, open_base: str | None = None
) -> str:
    """The app's bot's own open id, which the chat channel's record names it by, or empty.

    Read, never written, and empty rather than raising for anything Lark does not answer: an app
    whose version is not released yet has no bot to name, and the steps ask for a second save
    after release for exactly that.
    """
    _, host = LARK_PLATFORMS[platform]
    base = open_base if open_base is not None else f"https://{host}"
    try:
        token = await _tenant_token(fetch, base, app_id, app_secret)
        if token is None:
            return ""
        bot = await _get(fetch, base, "/open-apis/bot/v3/info", token)
    except DirectorySignInError:
        return ""
    found = bot.body.get("bot")
    open_id = found.get("open_id") if isinstance(found, Mapping) else None
    return open_id if bot.status == 200 and isinstance(open_id, str) else ""


def _released(results: Sequence[UseResult]) -> tuple[UseResult, ...]:
    """Every result, with an all-missing test read as a version not released. See the constant."""
    if not results or any(
        one.verdict is not Verdict.MISSING_SCOPE or one.answered for one in results
    ):
        return tuple(results)
    return tuple(
        UseResult(
            one.use,
            Verdict.NOT_RELEASED,
            "Lark has granted the app none of its scopes yet. Most often the version is not "
            "released or not approved: open Version Management & Release, create a version, "
            "submit it, and have the administrator approve it. If you have not added the scopes, "
            f"add {', '.join(one.missing)} first.",
            one.missing,
        )
        for one in results
    )


#: Where a use's verdict sends a person back to, when the verdict means the same for every use.
_REDO: Final[Mapping[Verdict, tuple[StepKey, ...]]] = MappingProxyType(
    {
        Verdict.CREDENTIAL_REFUSED: (StepKey.CREDENTIALS,),
        Verdict.MISSING_SCOPE: (StepKey.PERMISSIONS, StepKey.RELEASE),
        Verdict.NOT_RELEASED: (StepKey.RELEASE,),
    }
)

#: Where "not shared" sends a person back to, which depends on what the use needed shared.
_NOT_SHARED_REDO: Final[Mapping[Use, tuple[StepKey, ...]]] = MappingProxyType(
    {
        Use.STAFF_LIST: (StepKey.PERMISSIONS, StepKey.RELEASE),
        Use.WIKI: (StepKey.SHARE_WIKI,),
        Use.BASE: (StepKey.SHARE_BASE,),
        Use.CHANNEL: (StepKey.BOT, StepKey.RELEASE),
    }
)

#: Where a refused App ID and App Secret send a person back to: the credentials, then the platform.
REDO_WHEN_REFUSED: Final = (StepKey.CREDENTIALS, StepKey.CHOOSE)


def redo_for(result: UseResult) -> tuple[StepKey, ...]:
    """The steps to go back to for one use's verdict, in the order to do them. None when working.

    A missing scope sends a person to the permissions and then to the release, because Lark cannot
    say whether the scope was never added or added and not yet released (see
    `A_SCOPE_NOT_RELEASED_LOOKS_LIKE_A_SCOPE_NOT_ADDED`). The contacts range and the bot are the
    app's configuration too, so each is followed by a new release.
    """
    if result.verdict is Verdict.NOT_SHARED:
        return _NOT_SHARED_REDO[result.use]
    if result.verdict is Verdict.NEEDS_SETTING:
        # Only the Base asks for a setting of its own: its link, pasted on the sharing step.
        return (StepKey.SHARE_BASE,) if result.use is Use.BASE else ()
    return _REDO.get(result.verdict, ())


async def probe_connection(
    fetch: Fetch,
    *,
    platform: str,
    app_id: str,
    app_secret: str,
    uses: Sequence[Use],
    base_link: str = "",
    open_base: str | None = None,
) -> ProbeResult:
    """Exchange the credential for a tenant token and try each chosen use. Reads only.

    `open_base` replaces the platform's host, for a test that points this at a fake Lark; every
    install leaves it None. See `THE_TEST_ONLY_READS`.
    """
    _, host = LARK_PLATFORMS[platform]
    base = open_base if open_base is not None else f"https://{host}"
    try:
        token = await _tenant_token(fetch, base, app_id, app_secret)
    except DirectorySignInError:
        return ProbeResult(
            False, f"This server could not reach Lark at {base}. Nothing was tried.", ()
        )
    if token is None:
        return ProbeResult(
            False,
            "Lark did not accept this App ID and App Secret. Copy both again from Credentials & "
            "Basic Info, and check the platform: an app made on Feishu is not known to Lark.",
            (),
        )
    results: list[UseResult] = []
    for use in Use:
        if use not in set(uses):
            continue
        try:
            if use is Use.STAFF_LIST:
                results.append(await _staff(fetch, base, token))
            elif use is Use.WIKI:
                results.append(await _wiki(fetch, base, token))
            elif use is Use.BASE:
                results.append(await _base(fetch, base, token, base_token(base_link)))
            else:
                results.append(await _channel(fetch, base, token))
        except DirectorySignInError:
            results.append(UseResult(use, Verdict.UNREACHABLE, "Lark did not answer. Try again."))
    return ProbeResult(True, "Lark accepted the App ID and App Secret.", _released(results))


# ------------------------------------------------------------------------ saving


def settings_for(uses: Sequence[Use], *, platform: str, base_link: str) -> dict[str, str]:
    """The installation settings a save writes. Configuration only, never content.

    The staff list is handed to the staff source settings the Staff sources screen and the
    scheduled sync already read (`INSTALL_STAFF_SOURCE`, `INSTALL_STAFF_SOURCE_LOCATION`), so the
    staff list has one configuration and not two. See
    `KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED` for what the knowledge uses write.
    """
    values = {
        "INSTALL_LARK_USES": ",".join(use.value for use in Use if use in set(uses)) or "none",
        "INSTALL_LARK_PLATFORM": platform,
    }
    if Use.BASE in uses:
        values["INSTALL_LARK_BASE"] = base_token(base_link)
    if Use.STAFF_LIST in uses:
        values["INSTALL_STAFF_SOURCE"] = "lark"
        values["INSTALL_STAFF_SOURCE_LOCATION"] = platform
    return values


def uses_switched_on(saved: str) -> tuple[Use, ...]:
    """The uses a saved `INSTALL_LARK_USES` names, ignoring anything else in it."""
    names = {one.strip() for one in saved.split(",")}
    return tuple(use for use in Use if use.value in names)


# ------------------------------------------------------------------------ the last test

#: Why a test leaves a record at all, and why the record is so small.
A_TEST_LEAVES_ITS_VERDICTS_AND_NOTHING_IT_READ: Final = (
    "Once Lark is connected the card says when it was last tested and what each use came to, so "
    "an administrator sees a use that stopped working without testing again. What is kept is the "
    "instant, whether Lark accepted the credential, and one verdict word per use: never the "
    "secret, never a scope list Lark sent, never anything read from Lark."
)


@dataclass(frozen=True)
class LastTest:
    """When Lark was last tested from the console, and each use's verdict in a word."""

    at: datetime
    accepted: bool
    verdicts: tuple[tuple[Use, Verdict], ...]


def last_test_value(result: ProbeResult, *, at: datetime) -> dict[str, Any]:
    """The record a test leaves. See `A_TEST_LEAVES_ITS_VERDICTS_AND_NOTHING_IT_READ`."""
    if at.tzinfo is None:
        msg = "a test recorded at a naive instant is read back an offset early or late"
        raise ValueError(msg)
    return {
        "at": at.isoformat(),
        "accepted": result.token_ok,
        "uses": {one.use.value: one.verdict.value for one in result.uses},
    }


def last_test_from(value: object) -> LastTest | None:
    """A recorded test read back, or None for a record in any other shape."""
    if not isinstance(value, Mapping):
        return None
    at, accepted, uses = value.get("at"), value.get("accepted"), value.get("uses")
    if not isinstance(at, str) or not isinstance(accepted, bool) or not isinstance(uses, Mapping):
        return None
    try:
        when = datetime.fromisoformat(at)
    except ValueError:
        return None
    if when.tzinfo is None:
        return None
    known = {one.value: one for one in Use}
    verdicts = {one.value: one for one in Verdict}
    found = tuple(
        (known[name], verdicts[word])
        for name, word in uses.items()
        if name in known and isinstance(word, str) and word in verdicts
    )
    return LastTest(at=when, accepted=accepted, verdicts=found)


# ------------------------------------------------------------------------ switching off

#: What switching a use off does, said on its confirmation.
SWITCHING_A_USE_OFF: Final = (
    "Each use you chose is switched off here now and stops being read; the ledger records it. The "
    "app's credential stays in the vault, because this system may write a key and may not delete "
    "one, so remove the app or its permissions in Lark's developer console as well. Switching a "
    "use on again asks for the App Secret again."
)

#: What switching the staff list off does to the staff source.
SWITCHING_THE_STAFF_LIST_OFF: Final = (
    "Switching the staff list off leaves this install with no staff source: nobody joins or "
    "leaves from Lark until a source is chosen on Staff sources, and nobody already here is "
    "removed."
)


def settings_after_switching_off(
    off: Sequence[Use], *, saved_uses: str, staff_source: str
) -> dict[str, str]:
    """The installation settings switching `off` writes. The key is left where it is.

    The staff list hands the staff source back to nothing only when Lark is the source it names,
    so switching Lark's staff list off never unsets a source the Staff sources screen chose since.
    """
    still = [use for use in uses_switched_on(saved_uses) if use not in set(off)]
    values = {"INSTALL_LARK_USES": ",".join(use.value for use in still) or "none"}
    if Use.STAFF_LIST in off and staff_source == "lark":
        values["INSTALL_STAFF_SOURCE"] = "none"
    return values
