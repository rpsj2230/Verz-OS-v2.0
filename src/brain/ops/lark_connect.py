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

**Knowledge is switched on as configuration and never copied.** The owner's rule is that a
connector keeps a minimal index and reads content live at question time. Switching knowledge on
here writes which Base and which platform, as installation settings, and keeps the credential in
the vault; it registers no connection the sync worker would read and ingests nothing. The index
and the live reader are the Lark knowledge connector's to build over exactly these settings. See
`KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED`.

**The chat channel is configured and does not yet receive Lark's events**, and the step says so
rather than handing out an address that Lark's verification would refuse: no channel in this
release receives a webhook (`brain.webhook_routes` says the same). The address is built from the
install's own redirect URI so the step can show where messages will arrive once the receiver
ships. See `THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET`.

Rejected: a scope list per use typed into the page. The test and the steps would then hold two
copies, and the one a person reads would drift from the one the test checks.

Rejected: testing with the credential already kept. The application may write a connector key
and never read one back (`brain.ops.credentials`), so the test takes the credential as it is
typed, before it is kept, and a re-test later asks for it again.

Task ids: M11.9.4, M11.9.1
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import quote, urlencode, urlsplit

from brain.connectors.staff_directories import (
    LARK_PLATFORMS,
    LARK_SCOPES,
    Answer,
    DirectorySignInError,
    Fetch,
    Outbound,
)

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
    "in Lark, and then makes small GET requests: a page size of one, and a document's metadata "
    "rather than its body. It writes nothing here or in Lark and keeps nothing it read."
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

#: What the chat channel can and cannot do in this release.
THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET: Final = (
    "The chat channel's credential, bot and scopes are set up and tested here, but this release "
    "does not yet receive Lark's events, so Lark would refuse the address if it were entered "
    "under Events & callbacks now. Leave that page for now. The address messages will arrive at "
    "is shown so it can be entered on the day the receiver ships."
)

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

#: The one path the chat channel's events will arrive at, under the install's own address.
LARK_EVENTS_PATH: Final = "/api/v1/channels/lark/events"


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
    # Read out of the staff list's own constant, so the scopes this screen asks for are the ones
    # its reader was written against, and a scope added there is asked for here.
    words = {
        "contact:user.base:readonly": "read each person's name and identifiers",
        "contact:user.email:readonly": "read each person's work email address",
        "contact:user.department:readonly": "read which departments each person is in",
        "contact:department.base:readonly": "read department names",
    }
    return tuple(
        Scope(name, words.get(name, "read the company directory")) for name in LARK_SCOPES.split()
    )


#: Every use, with the scopes it needs. See `A_SCOPE_IS_ASKED_FOR_ONLY_BY_A_USE_THAT_NEEDS_IT`.
USES: Final[Mapping[Use, UseSpec]] = MappingProxyType(
    {
        Use.STAFF_LIST: UseSpec(
            use=Use.STAFF_LIST,
            label="Staff list",
            what=(
                "Read who works here, their work email and their departments from Lark's "
                "directory, on a schedule, so people join and leave the Brain as they do in Lark."
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
                    "docs:permission.member:retrieve",
                    "read who may open a page, so nobody is answered from a page they cannot open",
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
                "mention of it in a group. Each answer is limited to what everyone in the chat "
                "may see."
            ),
            scopes=(
                Scope("im:message.p2p_msg:readonly", "receive direct messages sent to the bot"),
                Scope(
                    "im:message.group_at_msg:readonly",
                    "receive group messages that mention the bot, and no others",
                ),
                Scope(
                    "im:chat:readonly", "read who is in a chat, so an answer fits everyone in it"
                ),
                Scope(
                    "im:message:send_as_bot",
                    "send the bot's own replies. The one scope that writes: it can post as the "
                    "bot and cannot read or change anybody else's messages",
                    read_only=False,
                ),
            ),
            slot="lark_channel",
            extra=(
                "In the left menu open Add Features (or Features), choose Bot, and turn it on. "
                "The chat scopes only work for an app that has a bot.",
                THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET,
            ),
        ),
    }
)


# ------------------------------------------------------------------------ the steps


@dataclass(frozen=True)
class Step:
    """One thing to do in Lark: a short title and what to click, in Lark's own names."""

    title: str
    text: str


def developer_console(platform: str) -> str:
    """The developer console's address on the chosen platform, or Lark's when none is chosen."""
    _, open_host = LARK_PLATFORMS.get(platform, LARK_PLATFORMS["larksuite.com"])
    return f"https://{open_host}/app"


def scopes_for(uses: Iterable[Use]) -> tuple[Scope, ...]:
    """Every scope the chosen uses need, each once, in the order the uses name them."""
    seen: dict[str, Scope] = {}
    for use in Use:
        if use in set(uses):
            for one in USES[use].scopes:
                seen.setdefault(one.name, one)
    return tuple(seen.values())


def steps_for(uses: Sequence[Use], *, platform: str) -> tuple[Step, ...]:
    """The steps from nothing to a released app, for the uses chosen, in click order."""
    chosen = [use for use in Use if use in set(uses)]
    scope_names = ", ".join(one.name for one in scopes_for(chosen)) or "none yet: choose a use"
    found = [
        Step(
            "Open Lark's developer console",
            f"Go to {developer_console(platform)} and sign in with a Lark account that may "
            "create apps for your company, usually a Lark administrator.",
        ),
        Step(
            "Create the app",
            "Click Create Custom App. Give it the name your staff will see when it answers, a "
            "one-line description such as 'Answers questions from our own documents', and an "
            "icon if you have one. Click Create.",
        ),
        Step(
            "Copy its App ID and App Secret",
            "In the left menu open Credentials & Basic Info. Copy the App ID (it starts with "
            "cli_) and the App Secret (click the eye or the copy icon). Keep the page open: you "
            "paste both into this screen below, where the secret goes into the vault and is "
            "never shown again.",
        ),
    ]
    if Use.CHANNEL in chosen:
        found.append(Step("Turn on the bot", USES[Use.CHANNEL].extra[0]))
    found.append(
        Step(
            "Add the scopes",
            "In the left menu open Permissions & Scopes. For each scope below, search its exact "
            "name and click Add (or tick it and click Add Scopes). Each is read-only except "
            f"im:message:send_as_bot, which only sends the bot's own replies: {scope_names}.",
        )
    )
    if Use.STAFF_LIST in chosen:
        found.append(Step("Let it read everyone", USES[Use.STAFF_LIST].extra[0]))
    if Use.CHANNEL in chosen:
        found.append(Step("Events & callbacks: not yet", THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET))
    found += [
        Step(
            "Release a version",
            "In the left menu open Version Management & Release and click Create a version. "
            "Enter a version number such as 1.0.0, set who may use the app to All members, write "
            "a short note such as 'Company Brain, read-only', then Save and Submit for release. "
            "Every later change to the scopes needs a new version released the same way.",
        ),
        Step(
            "Have it approved",
            "Lark sends the release to your workspace administrator. They approve it in the Lark "
            "Admin Console, under the app review page. If you are the administrator, Lark may "
            "release it at once. Scopes take effect only after approval.",
        ),
    ]
    if Use.WIKI in chosen:
        found.append(Step("Share your wiki spaces with it", USES[Use.WIKI].extra[0]))
    if Use.BASE in chosen:
        found.append(Step("Share the Base with it", USES[Use.BASE].extra[0]))
        found.append(Step("Copy the Base's link", USES[Use.BASE].extra[1]))
    found.append(
        Step(
            "Test, then save",
            "Paste the App ID and App Secret below and press Test connection. Each use you chose "
            "says it works or exactly what to add. When they work, press Save to switch them on.",
        )
    )
    return tuple(found)


def events_address(redirect_uris: str) -> str:
    """Where Lark will send the chat channel's events: the install's own origin and one path.

    Built from `INSTALL_OIDC_REDIRECT_URIS`, the one installation setting that already names this
    install's public address, so no second setting can disagree with it. Empty when it names none.
    """
    first = next((one.strip() for one in redirect_uris.split(",") if one.strip()), "")
    parts = urlsplit(first)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}{LARK_EVENTS_PATH}"


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


def input_problems(
    *, app_id: str, app_secret: str, uses: Sequence[Use], platform: str, base_link: str
) -> tuple[Problem, ...]:
    """Everything wrong with the identifier, the secret, the platform and the Base link, at once.

    The secret is judged for shape only (present, one piece, not too long): whether Lark accepts
    it is the test's to say. Nothing here repeats what was typed.
    """
    found: list[Problem] = []
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
    if _items(people):
        return UseResult(spec.use, Verdict.WORKING, "Working: the app can read the staff list.")
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
    if _items(departments):
        return UseResult(spec.use, Verdict.WORKING, "Working: the app can read the staff list.")
    return UseResult(spec.use, Verdict.NOT_SHARED, range_sentence)


async def _wiki(fetch: Fetch, base: str, token: str) -> UseResult:
    spec = USES[Use.WIKI]
    unshared = "The app is in no wiki space yet. " + spec.extra[0]
    spaces = await _get(fetch, base, "/open-apis/wiki/v2/spaces", token, page_size="1")
    refused = _refused_or_other(spec, spaces, not_shared=unshared)
    if refused is not None:
        return refused
    space = next((str(one.get("space_id") or "") for one in _items(spaces)), "")
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
        )
    node_token = str(node.get("node_token") or "")
    permission = await _get(
        fetch,
        base,
        f"/open-apis/drive/v1/permissions/{quote(node_token, safe='')}/members",
        token,
        type="wiki",
        perm_type="single_page",
    )
    refused = _refused_or_other(spec, permission, not_shared=unshared)
    if refused is not None:
        # Only the permission scope can be missing here; the listing already worked.
        if refused.verdict is Verdict.MISSING_SCOPE:
            return _missing(spec, ("docs:permission.member:retrieve",))
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
        "Working: the app can list the wiki, see who may open a page, and read a page's details.",
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
    chats = await _get(fetch, base, "/open-apis/im/v1/chats", token, page_size="1")
    refused = _refused_or_other(spec, chats, not_shared=no_bot)
    if refused is not None:
        if refused.verdict is Verdict.MISSING_SCOPE:
            return _missing(spec, ("im:chat:readonly",))
        return refused
    return UseResult(
        spec.use,
        Verdict.WORKING,
        "Working: the bot is on and can see its chats. The message scopes are checked by Lark "
        "when the first message arrives. " + THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET,
    )


def _released(results: Sequence[UseResult]) -> tuple[UseResult, ...]:
    """Every result, with an all-missing test read as a version not released. See the constant."""
    if not results or any(one.verdict is not Verdict.MISSING_SCOPE for one in results):
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
        exchanged = await fetch(
            Outbound(
                "POST",
                f"{base}/open-apis/auth/v3/tenant_access_token/internal",
                {"Content-Type": "application/json"},
                json_body={"app_id": app_id.strip(), "app_secret": app_secret.strip()},
            )
        )
    except DirectorySignInError:
        return ProbeResult(
            False, f"This server could not reach Lark at {base}. Nothing was tried.", ()
        )
    token = exchanged.body.get("tenant_access_token")
    if exchanged.status != 200 or _code(exchanged) != 0 or not isinstance(token, str) or not token:
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
