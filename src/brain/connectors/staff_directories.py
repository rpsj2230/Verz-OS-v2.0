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

**Groups are not read.** A first-run trial proposes who would be added and nothing else:
nobody exists yet to be removed, and `staff_source.CHOOSING_A_STAFF_LIST_IS_NOT_APPOINTING_ANYBODY`
keeps roles out of the choice. Each vendor's group walk is a second endpoint per group and is
the scheduled sync's work.

**What has never happened.** None of these addresses has been called from this repository. The
scopes, parameters and answer shapes are written from each vendor's documentation, the same
standing `tests/fixtures/roster_payloads.py` declares for the pages, and the tests prove the
order of the calls, what each carries, and the refusals, against a stand-in.

Task ids: M42.5.7
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from urllib.parse import urlencode, urlsplit

from brain.identity.staff_adapters import (
    GOOGLE_WORKSPACE,
    LARK,
    MICROSOFT_ENTRA,
    GoogleWorkspaceSource,
    LarkSource,
    MicrosoftEntraSource,
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

# --------------------------------------------------------------------- the vendors
#: Google's authorisation page, token endpoint and Directory API.
GOOGLE_AUTHORISE_URL: Final = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_EXCHANGE_URL: Final = "https://oauth2.googleapis.com/token"
GOOGLE_DIRECTORY_URL: Final = "https://admin.googleapis.com/admin/directory/v1/users"
GOOGLE_READ_USERS_URL: Final = "https://www.googleapis.com/auth/admin.directory.user.readonly"

#: Where the scheduled sync reads a Google Sheet's values, with an API key rather than a person.
#: Declared here with the other vendors' addresses; `brain.ops.staff_sync_run` is its reader.
GOOGLE_SHEETS_URL: Final = "https://sheets.googleapis.com/v4/spreadsheets"

#: Microsoft's sign-in host, whose path names the tenant, and Graph.
MICROSOFT_LOGIN_HOST: Final = "login.microsoftonline.com"
MICROSOFT_GRAPH_URL: Final = "https://graph.microsoft.com"
MICROSOFT_READ_USERS_URL: Final = "https://graph.microsoft.com/User.Read.All"

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

#: What a Lark sign-in asks to read: people, their work address, their departments, and the
#: department names. Written from the contact API's documentation and never granted anywhere.
LARK_SCOPES: Final = (
    "contact:user.base:readonly contact:user.email:readonly "
    "contact:user.department:readonly contact:department.base:readonly"
)

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
            "Add the contact permissions to read users, their email addresses, their "
            "departments and department names, set the app's contact range to everyone who "
            "should be listed, and publish the version."
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


async def _google(fetch: Fetch, token: str, domain: str) -> StaffSource:
    pages: list[Mapping[str, Any]] = []
    after = ""
    for _ in range(MAX_PAGES):
        query = {"domain": domain, "maxResults": "500", "projection": "basic"}
        if after:
            query["pageToken"] = after
        request = Outbound("GET", f"{GOOGLE_DIRECTORY_URL}?{urlencode(query)}", _bearer(token))
        page = _page(await fetch(request), "the Google Workspace directory")
        pages.append(page)
        after = str(page.get("nextPageToken") or "")
        if not after:
            break
    return GoogleWorkspaceSource(pages=pages)


async def _microsoft(fetch: Fetch, token: str) -> StaffSource:
    fields = "id,userPrincipalName,displayName,department,accountEnabled,proxyAddresses"
    link = f"{MICROSOFT_GRAPH_URL}/v1.0/users?{urlencode({'$select': fields, '$top': '999'})}"
    pages: list[Mapping[str, Any]] = []
    for _ in range(MAX_PAGES):
        page = _page(await fetch(Outbound("GET", link, _bearer(token))), "the Entra directory")
        pages.append(page)
        link = str(page.get("@odata.nextLink") or "")
        if not link:
            break
        if not on_graph(link):
            msg = (
                "The Entra directory pointed its next page somewhere other than Microsoft Graph, "
                "so it was not followed."
            )
            raise DirectorySignInError(msg)
    return MicrosoftEntraSource(pages=pages)


def _lark_page(answer: Answer, what: str) -> Mapping[str, Any]:
    """A Lark page, refusing the non-zero code Lark refuses with inside a success."""
    page = _page(answer, what)
    if page.get("code", 0) != 0:
        msg = f"Reading {what} was refused: {_vendor_words(page)}."
        raise DirectorySignInError(msg)
    data = page.get("data")
    return data if isinstance(data, Mapping) else {}


async def _lark(fetch: Fetch, token: str, platform: str) -> StaffSource:
    _, open_host = LARK_PLATFORMS[platform]
    base = f"https://{open_host}/open-apis/contact/v3"
    budget = MAX_PAGES
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
                # Stopped with this department's walk unfinished, so the last page handed over
                # still says there is more and the adapter reads the roster as incomplete.
                return LarkSource(pages=pages, department_names=names)
            budget -= 1
            query = {
                "department_id": department,
                "department_id_type": "open_department_id",
                "page_size": "50",
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
                key = str(one.get("union_id") or one.get("enterprise_email") or "").casefold()
                if key and key in seen:
                    continue
                seen.add(key)
                kept.append(one)
            pages.append({**answer.body, "data": {**data, "items": kept}})
            after = str(data.get("page_token") or "") if data.get("has_more") else ""
            if not after:
                break
    return LarkSource(pages=pages, department_names=names)


async def pull(fetch: Fetch, source: str, *, token: str, location: str) -> StaffSource:
    """Read the directory with the token, and hand back the adapter holding every page read."""
    where = location.strip().lower()
    problem = location_problem(source, where)
    if problem:
        raise DirectorySignInError(problem)
    if source == GOOGLE_WORKSPACE:
        return await _google(fetch, token, where)
    if source == MICROSOFT_ENTRA:
        return await _microsoft(fetch, token)
    return await _lark(fetch, token, where)


def signed_in_sources() -> Sequence[str]:
    """Every source a person signs in to, in the order the wizard offers them."""
    return tuple(REGISTRATION)
