"""Signing in to a staff directory and walking it, against a stand-in for each vendor.

`brain.connectors.staff_directories` builds every request as a value and sends none, so what is
tested here is the whole of what it decides: the address a person is sent to, the exchange that
follows, the order and content of every page request, what is refused before anything is built,
and what a refusal repeats. The pages the stand-in answers with are
`tests/fixtures/roster_payloads.py`'s, which are reconstructed from vendor documentation and say
so; nothing here has called a vendor.

Task ids: M42.5.7
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.connectors import staff_directories
from brain.connectors.staff_directories import (
    GOOGLE_AUTHORISE_URL,
    GOOGLE_DIRECTORY_URL,
    GOOGLE_EXCHANGE_URL,
    LARK_OPEN_HOST,
    MICROSOFT_GRAPH_URL,
    MICROSOFT_LOGIN_HOST,
    RETURN_PATH,
    Answer,
    DirectorySignInError,
    Outbound,
    authorisation_address,
    exchange,
    location_problem,
    pull,
    token_request,
)
from brain.identity.staff_adapters import GOOGLE_WORKSPACE, LARK, MICROSOFT_ENTRA
from tests.fixtures.roster_payloads import (
    ENTRA_USERS_PAGE_ONE,
    ENTRA_USERS_PAGE_TWO,
    GOOGLE_WORKSPACE_USERS_PAGE_ONE,
    GOOGLE_WORKSPACE_USERS_PAGE_TWO,
    LARK_USERS_PAGE_ONE,
    LARK_USERS_PAGE_TWO,
    LARK_USERS_REFUSED,
)

RETURN = f"https://brain.example.invalid{RETURN_PATH}"
STATE = "S" * 32
CHALLENGE = "C" * 43
VERIFIER = "v" * 64
CLIENT = "client-id-123"
#: A secret nothing else could contain, so finding it anywhere it should not be is a leak.
SECRET = "SECRET-SENTINEL-9f2c"
TOKEN = "TOKEN-SENTINEL-77ab"

LOCATIONS = {
    GOOGLE_WORKSPACE: "example.com",
    MICROSOFT_ENTRA: "8f1a0e5c-0000-4000-8000-00000000000a",
    LARK: "larksuite.com",
}


class Stand:
    """A vendor in memory: answers each request by a function of it, and keeps every request."""

    def __init__(self, answer: Callable[[Outbound], Answer]) -> None:
        self.sent: list[Outbound] = []
        self._answer = answer

    async def __call__(self, outbound: Outbound) -> Answer:
        self.sent.append(outbound)
        return self._answer(outbound)


def query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def address_for(source: str, **changed: str) -> str:
    given = {
        "location": LOCATIONS[source],
        "client_id": CLIENT,
        "redirect_uri": RETURN,
        "state": STATE,
        "challenge": CHALLENGE,
        **changed,
    }
    return authorisation_address(source, **given)


# ============================================================ where the person signs in
@pytest.mark.parametrize(
    ("source", "starts", "scope"),
    [
        (GOOGLE_WORKSPACE, GOOGLE_AUTHORISE_URL, "admin.directory.user.readonly"),
        (
            MICROSOFT_ENTRA,
            f"https://{MICROSOFT_LOGIN_HOST}/{LOCATIONS[MICROSOFT_ENTRA]}/oauth2/v2.0/authorize",
            "User.Read.All",
        ),
        (LARK, "https://accounts.larksuite.com/open-apis/authen/v1/authorize", "contact:user"),
    ],
)
def test_each_directory_sends_the_person_to_its_own_page_with_pkce_and_the_state(
    source: str, starts: str, scope: str
) -> None:
    """The positive half of every refusal below: the address is the vendor's, and it carries the
    client id, the return address, the state and an S256 challenge, which is what makes the code
    that comes back useless to anybody without the verifier the wizard tab holds.

    Delete this and the challenge can be dropped from the address, which every vendor still
    accepts, and a returned code becomes a bearer credential in a browser's history."""
    address = address_for(source)
    asked = query(address)

    assert address.split("?")[0] == starts
    assert asked["client_id"] == CLIENT
    assert asked["redirect_uri"] == RETURN
    assert asked["state"] == STATE
    assert (asked["code_challenge"], asked["code_challenge_method"]) == (CHALLENGE, "S256")
    assert asked["response_type"] == "code"
    assert scope in asked["scope"]


@pytest.mark.parametrize(
    ("source", "location"),
    [
        (MICROSOFT_ENTRA, "evil.example/oauth2"),
        (MICROSOFT_ENTRA, "tenant?x=1"),
        (MICROSOFT_ENTRA, ""),
        (GOOGLE_WORKSPACE, "example.com/path"),
        (GOOGLE_WORKSPACE, "localhost"),
        (LARK, "attacker.example"),
        (LARK, "open.larksuite.com"),
    ],
)
def test_a_location_that_is_not_a_domain_a_tenant_or_a_lark_platform_is_refused(
    source: str, location: str
) -> None:
    """A Microsoft tenant is part of a URL path and a Lark platform chooses the host the secret is
    sent to, so a location outside the three shapes is refused before any address exists. The
    accepted half is `test_each_directory_sends_the_person_to_its_own_page_with_pkce_and_the_state`.

    Delete this and a location can carry a path segment or a host of somebody else's choosing
    into the address the client secret is posted to."""
    assert location_problem(source, location)
    with pytest.raises(DirectorySignInError):
        address_for(source, location=location)


@pytest.mark.parametrize(
    "redirect",
    [
        "http://brain.example.invalid/first-run/staff-list",
        "https://brain.example.invalid/first-run/other",
        f"https://brain.example.invalid{RETURN_PATH}?next=x",
        "javascript:alert(1)",
    ],
)
def test_a_return_address_off_the_staff_list_page_or_off_https_is_refused(redirect: str) -> None:
    """The vendor sends the code to the return address. One that is not this install's staff list
    page over https is a code sent somewhere the wizard is not, and a locally served address is
    the only plain-http one allowed.

    Delete this and the screen can be pointed at any address the application happens to have
    registered."""
    with pytest.raises(DirectorySignInError):
        address_for(GOOGLE_WORKSPACE, redirect_uri=redirect)
    assert address_for(GOOGLE_WORKSPACE, redirect_uri=f"http://localhost:5173{RETURN_PATH}")


@pytest.mark.parametrize(("state", "challenge"), [("short", CHALLENGE), (STATE, "c" * 42)])
def test_a_state_or_challenge_not_shaped_as_the_standard_says_starts_nothing(
    state: str, challenge: str
) -> None:
    """Delete this and a blank challenge sends the person to sign in without PKCE."""
    with pytest.raises(DirectorySignInError):
        address_for(LARK, state=state, challenge=challenge)


# ============================================================ the exchange
@pytest.mark.parametrize(
    ("source", "url", "shape"),
    [
        (GOOGLE_WORKSPACE, GOOGLE_EXCHANGE_URL, "form"),
        (
            MICROSOFT_ENTRA,
            f"https://{MICROSOFT_LOGIN_HOST}/{LOCATIONS[MICROSOFT_ENTRA]}/oauth2/v2.0/token",
            "form",
        ),
        (LARK, f"https://{LARK_OPEN_HOST}/open-apis/authen/v2/oauth/token", "json"),
    ],
)
def test_the_code_is_exchanged_at_the_vendors_own_address_with_the_verifier_and_secret(
    source: str, url: str, shape: str
) -> None:
    """Delete this and the verifier can be left out of the exchange, which a vendor that did not
    enforce PKCE would accept, and the protection the challenge promised is gone."""
    request = token_request(
        source,
        location=LOCATIONS[source],
        client_id=CLIENT,
        client_secret=f"  {SECRET}\n",
        code="the-code",
        verifier=VERIFIER,
        redirect_uri=RETURN,
    )
    fields = request.form if shape == "form" else request.json_body

    assert (request.method, request.url) == ("POST", url)
    assert fields is not None
    assert fields["code_verifier"] == VERIFIER
    assert fields["client_secret"] == SECRET, "the pasted line break went to the vendor"
    assert fields["grant_type"] == "authorization_code"
    assert fields["redirect_uri"] == RETURN


def test_nothing_a_request_carries_is_in_its_representation() -> None:
    """`A_REFUSAL_REPEATS_THE_VENDOR_AND_NEVER_THE_REQUEST`. An exception holding a request renders
    it into a traceback, and a traceback reaches a log.

    Delete this and a field of `Outbound` can lose `repr=False`, and the secret is one uncaught
    error away from the log."""
    request = token_request(
        MICROSOFT_ENTRA,
        location=LOCATIONS[MICROSOFT_ENTRA],
        client_id=CLIENT,
        client_secret=SECRET,
        code="CODE-SENTINEL",
        verifier=VERIFIER,
        redirect_uri=RETURN,
    )
    shown = repr(request) + repr(Outbound("GET", GOOGLE_DIRECTORY_URL, {"Authorization": TOKEN}))

    assert SECRET not in shown
    assert "CODE-SENTINEL" not in shown
    assert VERIFIER not in shown
    assert TOKEN not in shown


def test_a_refused_exchange_says_the_vendors_words_and_nothing_that_was_sent() -> None:
    """The sentence a person acts on when their return address is not registered, and the
    sibling of the positive exchange below.

    Delete this and a refused exchange either says nothing useful or quotes the request."""

    async def scenario() -> None:
        refusing = Stand(
            lambda _: Answer(
                400, {"error": "invalid_grant", "error_description": "redirect mismatch"}
            )
        )
        with pytest.raises(DirectorySignInError) as told:
            await exchange(
                refusing,
                GOOGLE_WORKSPACE,
                location="example.com",
                client_id=CLIENT,
                client_secret=SECRET,
                code="CODE-SENTINEL",
                verifier=VERIFIER,
                redirect_uri=RETURN,
            )

        assert "redirect mismatch" in str(told.value)
        assert SECRET not in str(told.value)
        assert "CODE-SENTINEL" not in str(told.value)

    asyncio.run(scenario())


def test_lark_refusing_inside_a_success_is_a_refusal_and_not_a_token() -> None:
    """Lark answers HTTP 200 with a non-zero code. Delete this and that answer's missing token is
    the only thing refusing it, which a body carrying a stale `access_token` field walks past."""

    async def scenario() -> None:
        lark = Stand(lambda _: Answer(200, {"code": 20050, "access_token": "x", "error": "denied"}))
        with pytest.raises(DirectorySignInError):
            await exchange(
                lark,
                LARK,
                location="larksuite.com",
                client_id=CLIENT,
                client_secret=SECRET,
                code="c",
                verifier=VERIFIER,
                redirect_uri=RETURN,
            )

    asyncio.run(scenario())


# ============================================================ the walks
def pages_by_url(pages: Mapping[str, Mapping[str, Any]]) -> Callable[[Outbound], Answer]:
    """Answer by the first key the request's URL contains, and refuse anything unexpected."""

    def answer(outbound: Outbound) -> Answer:
        for fragment, page in pages.items():
            if fragment in outbound.url:
                return Answer(200, page)
        return Answer(404, {"error": {"message": f"no stand-in for {outbound.url}"}})

    return answer


def test_google_is_walked_page_by_page_with_the_token_until_no_page_is_left() -> None:
    """Delete this and the walk can stop after the first page, and a two-page company arrives as
    half a roster the adapter reads as whole."""

    async def scenario() -> None:
        stand = Stand(
            pages_by_url(
                {
                    "pageToken=": GOOGLE_WORKSPACE_USERS_PAGE_TWO,
                    "users?": GOOGLE_WORKSPACE_USERS_PAGE_ONE,
                }
            )
        )
        roster = (await pull(stand, GOOGLE_WORKSPACE, token=TOKEN, location="Example.COM")).roster()

        assert [query(one.url).get("pageToken") for one in stand.sent] == [
            None,
            GOOGLE_WORKSPACE_USERS_PAGE_ONE["nextPageToken"],
        ]
        assert {query(one.url)["domain"] for one in stand.sent} == {"example.com"}
        assert all(one.headers["Authorization"] == f"Bearer {TOKEN}" for one in stand.sent)
        assert roster.complete is True
        assert {one.work_address for one in roster.people} == {
            "ada@example.com",
            "grace@example.com",
            "katherine@example.com",
        }

    asyncio.run(scenario())


def test_graph_is_walked_by_its_own_next_links() -> None:
    """Delete this and the positive half of the refusal below goes, and a walk that never follows
    a next link passes it."""

    async def scenario() -> None:
        stand = Stand(
            pages_by_url({"skiptoken": ENTRA_USERS_PAGE_TWO, "/v1.0/users?": ENTRA_USERS_PAGE_ONE})
        )
        roster = (await pull(stand, MICROSOFT_ENTRA, token=TOKEN, location="example.com")).roster()

        assert [one.url for one in stand.sent][1] == ENTRA_USERS_PAGE_ONE["@odata.nextLink"]
        assert all(one.url.startswith(MICROSOFT_GRAPH_URL) for one in stand.sent)
        assert roster.complete is True
        assert {one.work_address for one in roster.people} >= {"ada@example.com"}

    asyncio.run(scenario())


def test_a_next_link_off_graph_is_refused_and_the_token_is_never_sent_there() -> None:
    """`A_NEXT_PAGE_ELSEWHERE_SENDS_THE_BEARER_ELSEWHERE`. The one address in any walk that a
    response chose.

    Delete this and a page answering with a next link on another host receives the access token
    on the next request."""

    async def scenario() -> None:
        elsewhere = {
            **ENTRA_USERS_PAGE_ONE,
            "@odata.nextLink": "https://graph.example.invalid/users",
        }
        stand = Stand(pages_by_url({"/v1.0/users?": elsewhere}))

        with pytest.raises(DirectorySignInError):
            await pull(stand, MICROSOFT_ENTRA, token=TOKEN, location="example.com")
        assert [urlsplit(one.url).netloc for one in stand.sent] == ["graph.microsoft.com"]

    asyncio.run(scenario())


def lark_pages() -> dict[str, Mapping[str, Any]]:
    """Two departments under the root, Ada listed in both, and the root holding Katherine."""
    departments = {
        "code": 0,
        "data": {
            "has_more": False,
            "items": [
                {"open_department_id": "od-engineering", "name": "engineering"},
                {"open_department_id": "od-finance", "name": "finance"},
            ],
        },
    }
    return {
        "departments/0/children": departments,
        "department_id=0&": LARK_USERS_PAGE_TWO,
        "department_id=od-engineering&": {
            **LARK_USERS_PAGE_ONE,
            "data": {**LARK_USERS_PAGE_ONE["data"], "has_more": False},
        },
        "department_id=od-finance&": LARK_USERS_PAGE_ONE_AGAIN,
    }


#: Ada again, from the finance department's page, which is a person in two departments.
LARK_USERS_PAGE_ONE_AGAIN: dict[str, Any] = {
    "code": 0,
    "data": {"has_more": False, "items": [LARK_USERS_PAGE_ONE["data"]["items"][0]]},
}


def test_lark_is_walked_by_department_and_a_person_in_two_is_listed_once() -> None:
    """Lark lists people by department, so the walk reads the tree and then each department. A
    person on two pages is kept once, by their stable id, and department names are read.

    Delete this and a person in two departments makes `Roster` refuse the whole company, or the
    root department alone is read and most of a company is missing."""

    async def scenario() -> None:
        stand = Stand(pages_by_url(lark_pages()))
        source = await pull(stand, LARK, token=TOKEN, location="larksuite.com")
        roster = source.roster()

        assert all(urlsplit(one.url).netloc == LARK_OPEN_HOST for one in stand.sent)
        assert "departments/0/children" in stand.sent[0].url
        assert sorted(one.work_address for one in roster.people) == [
            "ada@example.com",
            "grace@example.com",
            "katherine@example.com",
        ]
        assert {one.work_address: one.department for one in roster.people}["ada@example.com"] == (
            "engineering"
        )

    asyncio.run(scenario())


def test_lark_refusing_a_page_is_a_refusal_and_not_an_empty_company() -> None:
    """Delete this and a scope nobody granted reads as a company with nobody in it."""

    async def scenario() -> None:
        stand = Stand(
            pages_by_url(
                {
                    "departments/0/children": {"code": 0, "data": {"has_more": False, "items": []}},
                    "find_by_department": LARK_USERS_REFUSED,
                }
            )
        )
        with pytest.raises(DirectorySignInError):
            await pull(stand, LARK, token=TOKEN, location="larksuite.com")

    asyncio.run(scenario())


def test_a_walk_that_reaches_its_page_limit_hands_over_a_roster_read_as_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The walk stops rather than following a source for ever, and stops with the page that says
    there is more last, so the adapter reads the roster as incomplete from the payload.

    Delete this and a limit can be added that hands over a finished-looking last page, which is a
    roster trusted with completeness that is missing everybody after the limit."""

    async def scenario() -> None:
        monkeypatch.setattr(staff_directories, "MAX_PAGES", 2)
        endless = {**GOOGLE_WORKSPACE_USERS_PAGE_ONE, "users": []}
        stand = Stand(lambda _: Answer(200, endless))

        roster = (await pull(stand, GOOGLE_WORKSPACE, token=TOKEN, location="example.com")).roster()

        assert len(stand.sent) == 2
        assert roster.complete is False

    asyncio.run(scenario())


def test_a_page_refused_by_the_vendor_is_told_with_its_status_and_reason() -> None:
    """Delete this and a 403 from the Directory API is parsed as a page with no users on it."""

    async def scenario() -> None:
        stand = Stand(
            lambda _: Answer(403, {"error": {"message": "Not Authorized to access this"}})
        )
        with pytest.raises(DirectorySignInError) as told:
            await pull(stand, GOOGLE_WORKSPACE, token=TOKEN, location="example.com")
        assert "403" in str(told.value)
        assert "Not Authorized" in str(told.value)
        assert TOKEN not in str(told.value)

    asyncio.run(scenario())
