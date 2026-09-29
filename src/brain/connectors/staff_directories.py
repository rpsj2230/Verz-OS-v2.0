"""Signing in to a company's staff directory at first run, and reading who is in it once.

`brain.identity.staff_adapters` parses the pages Google Workspace, Microsoft Entra and Lark
answer with and says plainly that it owns no transport and that nothing fetches a page. The
setup wizard's staff source screen needs exactly that missing half, once: somebody chooses
where the company keeps its people, signs in there, and sees the list read back before any of
it is written. This module is the half that knows where each vendor is, what to ask it for and
in what order. It still opens no socket. Every request is a value, `Outbound`, handed to a
`Fetch` the caller owns, so the walk is tested against recorded page shapes and the one real
client lives in `brain.setup_staff_routes`.

**Signing in is OAuth 2.0 authorisation code with PKCE, and it needs an application the
company registers with its own directory.** That is not a gap this product can close for
them. A provider only sends a person back to an address registered on the application they
signed in to, and every install of this product has its own address, so there is no one
application a product owner could register for every company: the address each install
returns to would have to be on it in advance. So the company's own administrator registers an
application in their own Google Cloud project, Entra tenant or Lark developer console, grants it
read access to the directory, registers the one return address the screen shows them, and
pastes its client id and secret. `REGISTRATION` says what to do at each vendor in the words the
screen and `docs/install/authentication.md` use. See
`EVERY_INSTALL_RETURNS_TO_ITS_OWN_ADDRESS_SO_EVERY_COMPANY_REGISTERS_ITS_OWN_APPLICATION`.

Rejected: a device code grant, which needs no return address at all. Microsoft offers one and
it would have removed the registration for Entra; Google refuses the directory scopes to it and
Lark has none, so it would have made one of three sources simpler and the screen a different
shape for each. Rejected: a service account for Google and application credentials for
Microsoft and Lark, which read the directory without anybody signing in. They are the right
shape for the scheduled sync and the wrong one for this screen, whose leaf is a person signing
in, and each needs a standing secret with more reach than one person's session.

**Every address is built from constants and checked shapes, never from what came back.** The
authorisation address, the token address and the first page of each walk are made from the
vendor constants below and a location that was refused unless it is a domain, a tenant
identifier or one of Lark's two platforms. The one address a vendor hands back is Graph's next
page link, and it is followed only when it is on Graph itself: a next link pointing elsewhere
would be the access token sent to whoever wrote the page. See
`A_NEXT_PAGE_ELSEWHERE_SENDS_THE_BEARER_ELSEWHERE`.

**Completeness is still the adapter's to read, and the walk is shaped so it can.** The walk
stops at `MAX_PAGES` rather than following a source for ever, and when it stops early the last
page handed over is the one still saying there is more, so the adapter reads the roster as
incomplete from the payload exactly as it would from a vendor that stopped. Lark lists people
by department, so its walk reads the department tree first and then each department's
members; a person in two departments appears on two pages and is kept once, by the vendor's
stable identifier, because `Roster` refuses one person listed twice and that refusal is about a
source that disagrees with itself rather than about a walk that asked twice.

**What a vendor says in refusing is passed on, shortened, and nothing sent to it is.** A token
exchange that fails answers with the vendor's own `error_description`, which is what tells a
person their return address is not registered or their secret has expired; that sentence is
the one thing on the screen they can act on. What is never repeated is anything the request
carried: the secret, the code and the verifier are fields of `Outbound` and of nothing this
module returns, and `Outbound`'s representation leaves them out. See
`A_REFUSAL_REPEATS_THE_VENDOR_AND_NEVER_THE_REQUEST`.

**Groups are read only when the caller asks, and a first-run trial does not.** A trial proposes
who would be added and nothing else: nobody exists yet to be removed, and
`staff_source.CHOOSING_A_STAFF_LIST_IS_NOT_APPOINTING_ANYBODY` keeps roles out of the choice. The
scheduled sync asks (`pull(..., groups=True)`), because a directory group may be mapped to a role
and never to anything else (needs-rupash item 96). Each vendor's group walk is a list of groups
and a second endpoint per group, on a page budget of its own, and a walk that runs out hands the
adapter `groups_complete=False` rather than stopping the read: see `A_GROUP_WALK_IS_ITS_OWN_BUDGET`.
A group's identifier goes into a path, so it is checked against `GROUP_ID` first and a group
whose identifier is not that shape is skipped and counted as not read.

**The scopes are the ones each vendor's documentation names for exactly the fields read.** Lark
checks a scope per field and answers a field it may not show by leaving it out, which is the
quiet failure: without `contact:user.employee:readonly` every person arrives with no work
address and no status, and the call still succeeds. So `LARK_SCOPES` is written field by field
from the contact API's documentation (2026-09-28, corrected 2026-09-29):
`contact:department.organize:readonly` admits both endpoints and the department tree,
`contact:department.base:readonly` shows each department's name, `contact:user.base:readonly`
each person's name, `contact:user.employee:readonly` the Lark Mail address and the status,
`contact:user.department:readonly` a person's departments and manager, and
`contact:user.email:readonly` the account address used where there is no Lark Mail. See
`A_LARK_SCOPE_IS_CHECKED_PER_FIELD_AND_A_MISSING_ONE_IS_SILENT`.

**The department's name was the scope this list missed, and it placed a whole company nowhere.**
Until 2026-09-29 the list read "`contact:department.organize:readonly` for both endpoints and
department names", and Lark's field permission table for the department walk says otherwise: that
scope admits the call and shows the tree, and `name` is shown only to
`contact:department.base:readonly` (or a whole-directory scope this product does not ask for). On
the owner's install every department came back nameless, 123 people were added, and not one was
placed in a department. `staff_adapters.LARK_DEPARTMENT_NAME_SCOPE` is that scope, declared where
the name is read, and the reading now counts a nameless department and names the scope.

**What has never happened.** None of these addresses has been called from this repository. The
scopes, parameters and answer shapes are written from each vendor's documentation, the same
standing `tests/fixtures/roster_payloads.py` declares for the pages, and the tests prove the
order of the calls, what each carries, and the refusals, against a stand-in.

Task ids: M42.5.7, M1.6.5
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from urllib.parse import quote, urlencode, urlsplit

from brain.identity.staff_adapters import (
    GOOGLE_WORKSPACE,
    LARK,
    LARK_DEPARTMENT_NAME_SCOPE,
    LARK_PERSON_DEPARTMENT_SCOPE,
    MICROSOFT_ENTRA,
    GoogleWorkspaceSource,
    LarkSource,
    MicrosoftEntraSource,
    lark_work_address,
)
from brain.identity.staff_source import StaffSource

# ------------------------------------------------------------------ written-down reasons
#: Why the company registers the application and the product does not.
EVERY_INSTALL_RETURNS_TO_ITS_OWN_ADDRESS_SO_EVERY_COMPANY_REGISTERS_ITS_OWN_APPLICATION: Final = (
    "A directory sends a person back only to an address registered on the application they "
    "signed in to. Every install of this product answers at its own address, so no single "
    "application could list them all in advance, and the company's administrator registers one "
    "in their own directory, grants it read access, and registers the address the screen shows."
)

#: Why Graph's next link is checked before it is followed.
A_NEXT_PAGE_ELSEWHERE_SENDS_THE_BEARER_ELSEWHERE: Final = (
    "Every page request carries the access token. A next page link is the one address in this "
    "walk that a response chose rather than this module, so following one that is not on Graph "
    "itself would send the token to whoever wrote the page. It is refused instead."
)

#: Why a refusal carries the vendor's words and not the request's.
A_REFUSAL_REPEATS_THE_VENDOR_AND_NEVER_THE_REQUEST: Final = (
    "The vendor's own description of a failed sign-in is the sentence a person can act on, so "
    "it is passed on, shortened. What was sent is never repeated: the client secret, the code "
    "and the verifier leave in a request and appear in no refusal, no result and no log line."
)

#: Why the group walk has a budget of its own and never makes the roster incomplete.
A_GROUP_WALK_IS_ITS_OWN_BUDGET: Final = (
    "Who works here and which groups they are in are two walks, and only the first decides "
    "whether anybody may be removed. A company with more groups than the walk may read would "
    "otherwise spend the people's pages on groups and hand over a roster read as incomplete, "
    "which removes nobody for ever. So the groups get their own pages, and running out of them "
    "marks the groups as incomplete and leaves the roster's completeness to the people's walk."
)

#: Why Lark's scopes are listed field by field.
A_LARK_SCOPE_IS_CHECKED_PER_FIELD_AND_A_MISSING_ONE_IS_SILENT: Final = (
    "Lark admits a call on one scope and then shows each field only to the scope its "
    "documentation names for that field. A field the app may not see is left out and the call "
    "still succeeds, so an app without the employee scope reads every person with no work "
    "address and no status, and nothing refuses. Each scope here is the one named for a field "
    "the roster reads, and the steps ask for every one of them."
)

# --------------------------------------------------------------------- the vendors
#: Google's authorisation page, token endpoint and Directory API.
GOOGLE_AUTHORISE_URL: Final = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_EXCHANGE_URL: Final = "https://oauth2.googleapis.com/token"
GOOGLE_DIRECTORY_URL: Final = "https://admin.googleapis.com/admin/directory/v1/users"
GOOGLE_GROUPS_URL: Final = "https://admin.googleapis.com/admin/directory/v1/groups"
GOOGLE_READ_USERS_URL: Final = "https://www.googleapis.com/auth/admin.directory.user.readonly"
GOOGLE_READ_GROUPS_URL: Final = "https://www.googleapis.com/auth/admin.directory.group.readonly"

#: The one Workspace account the Directory API is asked about: the caller's own. A domain would
#: leave out everybody on the company's other domains from a list that says it is complete.
GOOGLE_OWN_ACCOUNT: Final = "my_customer"

#: The fields a Directory read asks for, as Google's `fields` parameter, and nothing more.
GOOGLE_USER_FIELDS: Final = (
    "nextPageToken,users(id,primaryEmail,name/fullName,suspended,archived,orgUnitPath,aliases,"
    "relations,organizations(description,primary))"
)
GOOGLE_GROUP_FIELDS: Final = "nextPageToken,groups(id,email)"
GOOGLE_MEMBER_FIELDS: Final = "nextPageToken,members(email,type)"

#: Where the scheduled sync reads a Google Sheet's values, with an API key rather than a person.
#: Declared here with the other vendors' addresses; `brain.ops.staff_sync_run` is its reader.
GOOGLE_SHEETS_URL: Final = "https://sheets.googleapis.com/v4/spreadsheets"

#: Microsoft's sign-in host, whose path names the tenant, and Graph.
MICROSOFT_LOGIN_HOST: Final = "login.microsoftonline.com"
MICROSOFT_GRAPH_URL: Final = "https://graph.microsoft.com"
MICROSOFT_READ_USERS_URL: Final = "https://graph.microsoft.com/User.Read.All"

#: The application permissions the scheduled read needs: people and their managers, then groups
#: and their members. Named for the steps, which ask for exactly these.
MICROSOFT_USERS_PERMISSION: Final = "User.Read.All"
MICROSOFT_GROUPS_PERMISSION: Final = "GroupMember.Read.All"

#: What a Graph read of people selects, and the manager it expands to. Nothing else is asked for.
MICROSOFT_USER_FIELDS: Final = (
    "id,userPrincipalName,displayName,department,accountEnabled,proxyAddresses,employeeType"
)
MICROSOFT_MANAGER_EXPAND: Final = "manager($select=id,userPrincipalName)"

#: Lark's two platforms: the international one and the one in mainland China. A tenant lives on
#: exactly one, and the location for a Lark source says which.
LARK_ACCOUNTS_HOST: Final = "accounts.larksuite.com"
LARK_OPEN_HOST: Final = "open.larksuite.com"
FEISHU_ACCOUNTS_HOST: Final = "accounts.feishu.cn"
FEISHU_OPEN_HOST: Final = "open.feishu.cn"

#: The words a person types for each Lark platform, and the two hosts each means.
LARK_PLATFORMS: Final[Mapping[str, tuple[str, str]]] = {
    "larksuite.com": (LARK_ACCOUNTS_HOST, LARK_OPEN_HOST),
    "feishu.cn": (FEISHU_ACCOUNTS_HOST, FEISHU_OPEN_HOST),
}

#: What reading Lark's people needs, field by field from the contact API's documentation: see
#: `A_LARK_SCOPE_IS_CHECKED_PER_FIELD_AND_A_MISSING_ONE_IS_SILENT`. Never granted anywhere here.
LARK_SCOPES: Final = (
    f"contact:department.organize:readonly {LARK_DEPARTMENT_NAME_SCOPE} "
    "contact:user.base:readonly contact:user.employee:readonly "
    f"{LARK_PERSON_DEPARTMENT_SCOPE} contact:user.email:readonly"
)

#: What reading Lark's user groups needs. The scheduled sync reads groups; a sign-in does not.
LARK_GROUP_SCOPE: Final = "contact:group:readonly"

#: Every scope the scheduled sync reads Lark with, which is what its steps ask for.
LARK_SYNC_SCOPES: Final = f"{LARK_SCOPES} {LARK_GROUP_SCOPE}"

#: What each of those scopes lets the sync read, in the words every screen that asks for them
#: uses. A test holds its keys equal to `LARK_SYNC_SCOPES`.
LARK_SCOPE_PURPOSE: Final[Mapping[str, str]] = {
    "contact:department.organize:readonly": "read your departments and how they are arranged",
    LARK_DEPARTMENT_NAME_SCOPE: "read each department's name",
    "contact:user.base:readonly": "read each person's name",
    "contact:user.employee:readonly": (
        "read each person's Lark Mail address and whether they are active, suspended or have left"
    ),
    LARK_PERSON_DEPARTMENT_SCOPE: "read which department each person is in and their manager",
    "contact:user.email:readonly": (
        "read the email on each person's account, used for anybody without a Lark Mail address"
    ),
    "contact:group:readonly": "read your user groups and who is in them",
}

#: How many pages one walk may read before it stops and hands over what it has as incomplete.
MAX_PAGES: Final = 200

#: The longest vendor refusal passed on. A sentence, not a document.
MAX_VENDOR_WORDS: Final = 300

#: The return address's path, which the company registers on its application. The console
#: draws its sign-in page here, and `brain.setup_staff_routes` refuses any other path.
RETURN_PATH: Final = "/first-run/staff-list"

#: What each source's location is, in the words the screen uses.
DOMAIN: Final = re.compile(
    r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
TENANT_ID: Final = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

#: The shapes the browser's half of PKCE and state may take, from RFC 7636. A value outside
#: them is refused before anything is built from it.
CHALLENGE: Final = re.compile(r"^[A-Za-z0-9_-]{43}$")
VERIFIER: Final = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
STATE: Final = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
CLIENT_ID: Final = re.compile(r"^[A-Za-z0-9._:@-]{1,200}$")

#: What a group's identifier from any of the three vendors may be before it goes into a path.
#: Google's and Lark's are letters and digits and Graph's is a GUID; nothing needs a slash.
GROUP_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class DirectorySignInError(Exception):
    """Signing in or reading the directory did not work. The message is for the person."""


@dataclass(frozen=True)
class Outbound:
    """One request, as a value. Nothing here is sent until a `Fetch` sends it.

    The body and the headers carry the secret, the code, the verifier and the token, so they
    are left out of the representation: an exception holding one of these renders it into a
    traceback, and a traceback is written to a log by whatever catches it.
    """

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    form: Mapping[str, str] | None = field(default=None, repr=False)
    json_body: Mapping[str, str] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Answer:
    """What came back: the status and the JSON body, or an empty mapping when it was not JSON."""

    status: int
    body: Mapping[str, Any]


class Fetch(Protocol):
    """Whatever sends an `Outbound`. `brain.setup_staff_routes.http_fetch` is the real one."""

    async def __call__(self, outbound: Outbound) -> Answer: ...


@dataclass(frozen=True)
class Registration:
    """What a company's administrator does at the vendor before anybody can sign in."""

    #: Where the application is registered, in the vendor's own names for the places.
    where: str
    #: What the application must be allowed to read.
    grant: str
    #: What the location question is asking for on this source.
    location: str


#: What each directory needs registered, in the words the screen shows and the guide repeats.
REGISTRATION: Final[Mapping[str, Registration]] = {
    GOOGLE_WORKSPACE: Registration(
        where=(
            "In Google Cloud console, in a project belonging to your company, create an OAuth "
            "client of the type Web application, and add the return address below as an "
            "authorised redirect URI. Enable the Admin SDK API in the same project."
        ),
        grant=(
            "Sign in with a Workspace administrator's account, which is what lets it read the "
            "user directory."
        ),
        location="Your company's primary Google Workspace domain, for example example.com.",
    ),
    MICROSOFT_ENTRA: Registration(
        where=(
            "In the Microsoft Entra admin centre, register an application in your tenant with "
            "a Web platform, add the return address below as a redirect URI, and create a "
            "client secret for it."
        ),
        grant=(
            "Give it the delegated Microsoft Graph permission User.Read.All and grant admin "
            "consent for your organisation."
        ),
        location="Your tenant ID, or your tenant's primary domain, from the Entra overview page.",
    ),
    LARK: Registration(
        where=(
            "In the Lark developer console, create a custom app, add the return address below "
            "as a redirect URL under Security settings, and copy its App ID and App Secret."
        ),
        grant=(
            f"Add these scopes under Permissions & Scopes: {', '.join(LARK_SCOPES.split())}. "
            "Set the app's contact range to everyone who should be listed, and publish the "
            "version."
        ),
        location="larksuite.com for Lark, or feishu.cn for Feishu.",
    ),
}


# ---------------------------------------------------------------------- the shapes
def location_problem(source: str, location: str) -> str:
    """Why this location cannot be used for this source, or the empty string.

    Refused here rather than escaped later, because Microsoft's tenant is part of a URL path and
    Lark's platform chooses which host the secret is sent to: a location that is not one of the
    shapes below is either a mistake or an address somebody else chose.
    """
    given = location.strip().lower()
    if source == GOOGLE_WORKSPACE and not DOMAIN.match(given):
        return "Enter your Google Workspace domain on its own, like example.com."
    if source == MICROSOFT_ENTRA and not (TENANT_ID.match(given) or DOMAIN.match(given)):
        return "Enter your tenant ID or your tenant's domain on its own."
    if source == LARK and given not in LARK_PLATFORMS:
        return f"Enter one of: {', '.join(LARK_PLATFORMS)}."
    if source not in REGISTRATION:
        return "This staff list is not one you sign in to."
    return ""


def _checked(source: str, location: str, client_id: str, redirect_uri: str) -> str:
    """The location, lower case, once every value an address is built from has been checked."""
    problem = location_problem(source, location)
    if problem:
        raise DirectorySignInError(problem)
    if not CLIENT_ID.match(client_id):
        msg = "That client ID has a character a client ID cannot have. Copy it again."
        raise DirectorySignInError(msg)
    parts = urlsplit(redirect_uri)
    local = parts.hostname in {"localhost", "127.0.0.1"}
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        msg = "The return address has to begin with https."
        raise DirectorySignInError(msg)
    if parts.path != RETURN_PATH or parts.query or parts.fragment:
        msg = f"The return address has to end in {RETURN_PATH} and nothing after it."
        raise DirectorySignInError(msg)
    return location.strip().lower()


def authorisation_address(
    source: str,
    *,
    location: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    challenge: str,
) -> str:
    """Where the person is sent to sign in: the vendor's own page, with PKCE and a state."""
    where = _checked(source, location, client_id, redirect_uri)
    if not STATE.match(state) or not CHALLENGE.match(challenge):
        msg = "The sign-in could not be started. Reload the page and try again."
        raise DirectorySignInError(msg)
    common = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if source == GOOGLE_WORKSPACE:
        extra = {"scope": GOOGLE_READ_USERS_URL, "hd": where, "prompt": "select_account"}
        return f"{GOOGLE_AUTHORISE_URL}?{urlencode({**common, **extra})}"
    if source == MICROSOFT_ENTRA:
        extra = {"scope": MICROSOFT_READ_USERS_URL, "response_mode": "query"}
        return (
            f"https://{MICROSOFT_LOGIN_HOST}/{where}/oauth2/v2.0/authorize?"
            f"{urlencode({**common, **extra})}"
        )
    accounts, _ = LARK_PLATFORMS[where]
    extra = {"scope": LARK_SCOPES}
    return f"https://{accounts}/open-apis/authen/v1/authorize?{urlencode({**common, **extra})}"


def token_request(
    source: str,
    *,
    location: str,
    client_id: str,
    client_secret: str,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> Outbound:
    """The exchange of the returned code for an access token, as a request not yet sent."""
    where = _checked(source, location, client_id, redirect_uri)
    if not VERIFIER.match(verifier) or not code.strip() or len(code) > 2000:
        msg = "The sign-in did not come back complete. Sign in again."
        raise DirectorySignInError(msg)
    fields = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret.strip(),
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if source == GOOGLE_WORKSPACE:
        return Outbound("POST", GOOGLE_EXCHANGE_URL, form=fields)
    if source == MICROSOFT_ENTRA:
        url = f"https://{MICROSOFT_LOGIN_HOST}/{where}/oauth2/v2.0/token"
        return Outbound("POST", url, form={**fields, "scope": MICROSOFT_READ_USERS_URL})
    _, open_host = LARK_PLATFORMS[where]
    url = f"https://{open_host}/open-apis/authen/v2/oauth/token"
    return Outbound("POST", url, json_body=fields)


def _vendor_words(body: Mapping[str, Any]) -> str:
    """The vendor's own description of a refusal, shortened, or a sentence saying there was none."""
    said = body.get("error_description") or body.get("msg") or body.get("error") or ""
    nested = body.get("error")
    if isinstance(nested, Mapping):
        said = nested.get("message") or said
    text = " ".join(str(said).split())[:MAX_VENDOR_WORDS]
    return text or "it gave no reason"


def token_from(answer: Answer) -> str:
    """The access token an exchange answered with, or a refusal in the vendor's words."""
    token = answer.body.get("access_token")
    refused = answer.status != 200 or answer.body.get("code", 0) not in (0, None)
    if refused or not isinstance(token, str) or not token:
        msg = f"Signing in was refused: {_vendor_words(answer.body)}."
        raise DirectorySignInError(msg)
    return token


async def exchange(
    fetch: Fetch,
    source: str,
    *,
    location: str,
    client_id: str,
    client_secret: str,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> str:
    """Exchange the code for an access token. The secret is sent once, in this request."""
    request = token_request(
        source,
        location=location,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        verifier=verifier,
        redirect_uri=redirect_uri,
    )
    return token_from(await fetch(request))


# ---------------------------------------------------------------------- the walks
def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _page(answer: Answer, what: str) -> Mapping[str, Any]:
    """One page, or a refusal naming what could not be read and the vendor's reason."""
    if answer.status != 200:
        msg = f"Reading {what} was refused ({answer.status}): {_vendor_words(answer.body)}."
        raise DirectorySignInError(msg)
    return answer.body


def on_graph(link: str) -> bool:
    """Whether a next page link is on Graph itself. See the named constant."""
    parts, graph = urlsplit(link), urlsplit(MICROSOFT_GRAPH_URL)
    return parts.scheme == graph.scheme and parts.netloc == graph.netloc


@dataclass
class _Budget:
    """How many more pages a walk may read. Spent one page at a time, refused at nought."""

    left: int

    def spend(self) -> bool:
        if self.left < 1:
            return False
        self.left -= 1
        return True


#: Group name to the addresses in it, and whether every group was read.
GroupRead = tuple[dict[str, tuple[str, ...]], bool]


def _unambiguous(found: Sequence[tuple[str, str, Sequence[str]]]) -> dict[str, tuple[str, ...]]:
    """Group name to members, a name two groups share being told apart by each group's id.

    A rule is written against a name, so a name that means two groups would confer a role from
    both, which is how a retired group goes on appointing people. Each keeps its own entry as
    `<name> (<id>)`, and a rule on the bare name matches neither.
    """
    counted: dict[str, int] = {}
    for _, name, _members in found:
        counted[name] = counted.get(name, 0) + 1
    return {
        (name if counted[name] == 1 else f"{name} ({ident})"): tuple(members)
        for ident, name, members in found
    }


def _addressable(listed: Sequence[tuple[str, str]]) -> tuple[list[tuple[str, str]], bool]:
    """The groups whose identifier may go into a path, and whether that was every one of them.

    A group's identifier is the one part of a group address a response chose, so one that is not
    `GROUP_ID`'s shape is never put in a path: it is skipped and the walk counts as incomplete.
    """
    usable = [(ident, name) for ident, name in listed if GROUP_ID.match(ident) and name]
    return usable, len(usable) == len(listed)


async def _google_groups(fetch: Fetch, token: str, budget: _Budget) -> GroupRead:
    """Every group in the account and its members, direct or through another group."""
    listed: list[tuple[str, str]] = []
    after = ""
    while True:
        if not budget.spend():
            return {}, False
        query = {
            "customer": GOOGLE_OWN_ACCOUNT,
            "maxResults": "200",
            "fields": GOOGLE_GROUP_FIELDS,
        }
        if after:
            query["pageToken"] = after
        url = f"{GOOGLE_GROUPS_URL}?{urlencode(query)}"
        page = _page(await fetch(Outbound("GET", url, _bearer(token))), "the Workspace groups")
        listed += [
            (str(one.get("id") or ""), str(one.get("email") or "").strip().casefold())
            for one in page.get("groups") or ()
            if isinstance(one, Mapping)
        ]
        after = str(page.get("nextPageToken") or "")
        if not after:
            break
    found: list[tuple[str, str, Sequence[str]]] = []
    usable, complete = _addressable(listed)
    for ident, name in usable:
        members: list[str] = []
        after = ""
        while True:
            if not budget.spend():
                return _unambiguous(found), False
            query = {
                "maxResults": "200",
                "includeDerivedMembership": "true",
                "fields": GOOGLE_MEMBER_FIELDS,
            }
            if after:
                query["pageToken"] = after
            url = f"{GOOGLE_GROUPS_URL}/{quote(ident, safe='')}/members?{urlencode(query)}"
            page = _page(await fetch(Outbound("GET", url, _bearer(token))), f"the group {name}")
            members += [
                str(one.get("email") or "")
                for one in page.get("members") or ()
                if isinstance(one, Mapping) and one.get("type") == "USER" and one.get("email")
            ]
            after = str(page.get("nextPageToken") or "")
            if not after:
                break
        found.append((ident, name, members))
    return _unambiguous(found), complete


async def _google(fetch: Fetch, token: str, budget: int, *, groups: bool) -> StaffSource:
    pages: list[Mapping[str, Any]] = []
    after = ""
    for _ in range(budget):
        query = {
            "customer": GOOGLE_OWN_ACCOUNT,
            "maxResults": "500",
            "projection": "basic",
            "fields": GOOGLE_USER_FIELDS,
        }
        if after:
            query["pageToken"] = after
        request = Outbound("GET", f"{GOOGLE_DIRECTORY_URL}?{urlencode(query)}", _bearer(token))
        page = _page(await fetch(request), "the Google Workspace directory")
        pages.append(page)
        after = str(page.get("nextPageToken") or "")
        if not after:
            break
    if not groups:
        return GoogleWorkspaceSource(pages=pages)
    members, complete = await _google_groups(fetch, token, _Budget(budget))
    return GoogleWorkspaceSource(pages=pages, group_members=members, groups_complete=complete)


def _next_on_graph(page: Mapping[str, Any], what: str) -> str:
    """The page's next link, or the empty string, refusing one that is not on Graph itself."""
    link = str(page.get("@odata.nextLink") or "")
    if link and not on_graph(link):
        msg = (
            f"The Entra directory pointed the next page of {what} somewhere other than "
            "Microsoft Graph, so it was not followed."
        )
        raise DirectorySignInError(msg)
    return link


async def _microsoft_groups(
    fetch: Fetch, token: str, budget: _Budget, address_of: Mapping[str, str]
) -> GroupRead:
    """Every group and its members, through nested groups, as addresses of people in this read.

    Members are selected by id alone and turned into addresses against the people just read, so
    the group walk reads nothing about a person the people walk did not. Selecting a member's
    fields is an advanced query in Graph, which needs `ConsistencyLevel: eventual` and `$count`.
    """
    listed: list[tuple[str, str]] = []
    query = urlencode({"$select": "id,displayName", "$top": "999"})
    link = f"{MICROSOFT_GRAPH_URL}/v1.0/groups?{query}"
    while link:
        if not budget.spend():
            return {}, False
        page = _page(await fetch(Outbound("GET", link, _bearer(token))), "the Entra groups")
        listed += [
            (str(one.get("id") or ""), str(one.get("displayName") or "").strip())
            for one in page.get("value") or ()
            if isinstance(one, Mapping)
        ]
        link = _next_on_graph(page, "groups")
    found: list[tuple[str, str, Sequence[str]]] = []
    usable, complete = _addressable(listed)
    advanced = {**_bearer(token), "ConsistencyLevel": "eventual"}
    for ident, name in usable:
        members: list[str] = []
        query = urlencode({"$count": "true", "$select": "id", "$top": "999"})
        link = (
            f"{MICROSOFT_GRAPH_URL}/v1.0/groups/{quote(ident, safe='')}/transitiveMembers?{query}"
        )
        while link:
            if not budget.spend():
                return _unambiguous(found), False
            answer = await fetch(Outbound("GET", link, advanced))
            page = _page(answer, f"the members of {name}")
            members += [
                address_of[str(one.get("id"))]
                for one in page.get("value") or ()
                if isinstance(one, Mapping) and str(one.get("id")) in address_of
            ]
            link = _next_on_graph(page, f"the members of {name}")
        found.append((ident, name, members))
    return _unambiguous(found), complete


async def _microsoft(fetch: Fetch, token: str, budget: int, *, groups: bool) -> StaffSource:
    query = {
        "$select": MICROSOFT_USER_FIELDS,
        "$expand": MICROSOFT_MANAGER_EXPAND,
        "$top": "999",
    }
    link = f"{MICROSOFT_GRAPH_URL}/v1.0/users?{urlencode(query)}"
    pages: list[Mapping[str, Any]] = []
    for _ in range(budget):
        page = _page(await fetch(Outbound("GET", link, _bearer(token))), "the Entra directory")
        pages.append(page)
        link = _next_on_graph(page, "people")
        if not link:
            break
    if not groups:
        return MicrosoftEntraSource(pages=pages)
    address_of = {
        str(one.get("id")): str(one.get("userPrincipalName") or "")
        for page in pages
        for one in page.get("value") or ()
        if isinstance(one, Mapping) and one.get("id") and one.get("userPrincipalName")
    }
    members, complete = await _microsoft_groups(fetch, token, _Budget(budget), address_of)
    return MicrosoftEntraSource(pages=pages, group_members=members, groups_complete=complete)


def _lark_page(answer: Answer, what: str) -> Mapping[str, Any]:
    """A Lark page, refusing the non-zero code Lark refuses with inside a success."""
    page = _page(answer, what)
    if page.get("code", 0) != 0:
        msg = f"Reading {what} was refused: {_vendor_words(page)}."
        raise DirectorySignInError(msg)
    data = page.get("data")
    return data if isinstance(data, Mapping) else {}


def _unfinished(pages: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The pages read, with the last one saying there is more. See `_lark`'s early stop."""
    if not pages:
        return pages
    last = pages[-1]
    data = last.get("data")
    held = data if isinstance(data, Mapping) else {}
    return [*pages[:-1], {**last, "data": {**held, "has_more": True}}]


async def _lark_groups(
    fetch: Fetch, token: str, base: str, budget: _Budget, address_of: Mapping[str, str]
) -> GroupRead:
    """Every ordinary user group and its user members, as addresses of people in this read.

    Members are asked for as union ids, the identifier the people walk keeps, and turned into
    addresses against it. A department placed in a group is not expanded: Lark lists it as a
    member of another type, and this reads users only.
    """
    listed: list[tuple[str, str]] = []
    after = ""
    while True:
        if not budget.spend():
            return {}, False
        query = {"page_size": "100", "type": "1"}
        if after:
            query["page_token"] = after
        url = f"{base}/group/simplelist?{urlencode(query)}"
        data = _lark_page(await fetch(Outbound("GET", url, _bearer(token))), "Lark's user groups")
        listed += [
            (str(one.get("id") or ""), str(one.get("name") or "").strip())
            for one in data.get("grouplist") or ()
            if isinstance(one, Mapping)
        ]
        after = str(data.get("page_token") or "") if data.get("has_more") else ""
        if not after:
            break
    found: list[tuple[str, str, Sequence[str]]] = []
    usable, complete = _addressable(listed)
    for ident, name in usable:
        members: list[str] = []
        after = ""
        while True:
            if not budget.spend():
                return _unambiguous(found), False
            query = {"page_size": "100", "member_id_type": "union_id", "member_type": "user"}
            if after:
                query["page_token"] = after
            url = f"{base}/group/{quote(ident, safe='')}/member/simplelist?{urlencode(query)}"
            answer = await fetch(Outbound("GET", url, _bearer(token)))
            data = _lark_page(answer, f"the members of {name}")
            members += [
                address_of[str(one.get("member_id"))]
                for one in data.get("memberlist") or ()
                if isinstance(one, Mapping) and str(one.get("member_id")) in address_of
            ]
            after = str(data.get("page_token") or "") if data.get("has_more") else ""
            if not after:
                break
        found.append((ident, name, members))
    return _unambiguous(found), complete


async def _lark(
    fetch: Fetch, token: str, platform: str, budget: int, *, groups: bool
) -> StaffSource:
    _, open_host = LARK_PLATFORMS[platform]
    base = f"https://{open_host}/open-apis/contact/v3"
    people = await _lark_people(fetch, token, base, budget)
    if not groups:
        return people
    address_of = {
        str(one.get("union_id")): lark_work_address(one)
        for page in people.pages
        for one in (page.get("data") or {}).get("items") or ()
        if isinstance(one, Mapping) and one.get("union_id") and lark_work_address(one)
    }
    members, complete = await _lark_groups(fetch, token, base, _Budget(budget), address_of)
    return LarkSource(
        pages=people.pages,
        department_names=people.department_names,
        group_members=members,
        groups_complete=complete,
    )


async def _lark_people(fetch: Fetch, token: str, base: str, budget: int) -> LarkSource:
    """The department tree, then each department's people, as union ids and open department ids."""
    names: dict[str, str] = {}
    after = ""
    while budget:
        budget -= 1
        query = {
            "fetch_child": "true",
            "page_size": "50",
            "department_id_type": "open_department_id",
        }
        if after:
            query["page_token"] = after
        url = f"{base}/departments/0/children?{urlencode(query)}"
        data = _lark_page(await fetch(Outbound("GET", url, _bearer(token))), "Lark's departments")
        for one in data.get("items") or ():
            if isinstance(one, Mapping) and one.get("open_department_id"):
                names[str(one["open_department_id"])] = str(one.get("name") or "")
        after = str(data.get("page_token") or "") if data.get("has_more") else ""
        if not after:
            break

    pages: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for department in ("0", *names):
        after = ""
        while True:
            if not budget:
                # Stopped before every department was walked. The last page handed over is
                # marked as having more, so the adapter reads the roster as incomplete: a walk
                # that stopped between two departments ends on a page that says it is the last.
                return LarkSource(pages=_unfinished(pages), department_names=names)
            budget -= 1
            # Union ids, so `leader_user_id` names the manager by the id the roster keeps.
            query = {
                "department_id": department,
                "department_id_type": "open_department_id",
                "page_size": "50",
                "user_id_type": "union_id",
            }
            if after:
                query["page_token"] = after
            url = f"{base}/users/find_by_department?{urlencode(query)}"
            answer = await fetch(Outbound("GET", url, _bearer(token)))
            data = _lark_page(answer, "Lark's people")
            kept = []
            for one in data.get("items") or ():
                if not isinstance(one, Mapping):
                    continue
                key = str(one.get("union_id") or lark_work_address(one)).casefold()
                if key and key in seen:
                    continue
                seen.add(key)
                kept.append(one)
            pages.append({**answer.body, "data": {**data, "items": kept}})
            after = str(data.get("page_token") or "") if data.get("has_more") else ""
            if not after:
                break
    return LarkSource(pages=pages, department_names=names)


async def pull(
    fetch: Fetch,
    source: str,
    *,
    token: str,
    location: str,
    pages: int | None = None,
    groups: bool = False,
) -> StaffSource:
    """Read the directory with the token, and hand back the adapter holding every page read.

    `pages` is how many pages the walk may read, `MAX_PAGES` when not given (read at the call, so
    the limit is one figure). A walk that runs out hands back what it read, and the adapter reads
    that as an incomplete roster, which nothing may remove anybody from: the console's connection
    test asks for a few pages and says how many people they held.

    `groups` walks the groups as well, on a budget of `pages` more. See
    `A_GROUP_WALK_IS_ITS_OWN_BUDGET`.
    """
    if pages is None:
        pages = MAX_PAGES
    if pages < 1:
        msg = "a walk of no pages reads nobody, which is not a test of anything"
        raise ValueError(msg)
    where = location.strip().lower()
    problem = location_problem(source, where)
    if problem:
        raise DirectorySignInError(problem)
    if source == GOOGLE_WORKSPACE:
        # The domain named the tenant signed in to; the read is of the whole account.
        return await _google(fetch, token, pages, groups=groups)
    if source == MICROSOFT_ENTRA:
        return await _microsoft(fetch, token, pages, groups=groups)
    return await _lark(fetch, token, where, pages, groups=groups)


def signed_in_sources() -> Sequence[str]:
    """Every source a person signs in to, in the order the wizard offers them."""
    return tuple(REGISTRATION)
