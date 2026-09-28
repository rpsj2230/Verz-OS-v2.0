"""Signing in to a staff directory and walking it, against a stand-in for each vendor.

`brain.connectors.staff_directories` builds every request as a value and sends none, so what is
tested here is the whole of what it decides: the address a person is sent to, the exchange that
follows, the order and content of every page request, what is refused before anything is built,
and what a refusal repeats. The pages the stand-in answers with are
`tests/fixtures/roster_payloads.py`'s, which are reconstructed from vendor documentation and say
so; nothing here has called a vendor.

Task ids: M42.5.7, M1.6.5
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
    ENTRA_APPROVERS_MEMBERS,
    ENTRA_AUDITORS_MEMBERS,
    ENTRA_GROUPS_PAGE,
    ENTRA_USERS_PAGE_ONE,
    ENTRA_USERS_PAGE_TWO,
    GOOGLE_WORKSPACE_APPROVERS_MEMBERS,
    GOOGLE_WORKSPACE_AUDITORS_MEMBERS,
    GOOGLE_WORKSPACE_GROUPS_PAGE,
    GOOGLE_WORKSPACE_USERS_PAGE_ONE,
    GOOGLE_WORKSPACE_USERS_PAGE_TWO,
    LARK_GROUP_MEMBERS_PAGE,
    LARK_GROUPS_PAGE,
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
        # The whole account, never one of its domains: see `GOOGLE_OWN_ACCOUNT`.
        assert {query(one.url)["customer"] for one in stand.sent} == {"my_customer"}
        assert all("domain" not in query(one.url) for one in stand.sent)
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
        "/member/simplelist": LARK_GROUP_MEMBERS_PAGE,
        "group/simplelist": LARK_GROUPS_PAGE,
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


# ============================================================ groups, managers, fields
def google_directory() -> dict[str, Mapping[str, Any]]:
    """Two pages of people, then two groups and each one's members."""
    return {
        "pageToken=": GOOGLE_WORKSPACE_USERS_PAGE_TWO,
        "users?": GOOGLE_WORKSPACE_USERS_PAGE_ONE,
        "/03x8tuzt3gsvn3p/members": GOOGLE_WORKSPACE_APPROVERS_MEMBERS,
        "/01ksv4uv1x1a9z3/members": GOOGLE_WORKSPACE_AUDITORS_MEMBERS,
        "groups?": GOOGLE_WORKSPACE_GROUPS_PAGE,
    }


def graph_directory() -> dict[str, Mapping[str, Any]]:
    """Two pages of people, then three groups, two of them sharing a name."""
    return {
        "skiptoken": ENTRA_USERS_PAGE_TWO,
        "/v1.0/users?": ENTRA_USERS_PAGE_ONE,
        "0001/transitiveMembers": ENTRA_APPROVERS_MEMBERS,
        "0002/transitiveMembers": ENTRA_AUDITORS_MEMBERS,
        "0003/transitiveMembers": {"value": []},
        "/v1.0/groups?": ENTRA_GROUPS_PAGE,
    }


def test_workspace_groups_are_read_when_asked_as_the_addresses_of_their_people() -> None:
    """M1.6.5: the Directory API's groups, each group's members read through nested groups, and a
    member that is a group or the whole account left out, because only a `USER` is somebody.

    Delete this and the scheduled sync reads Workspace with no groups, so a group rule on the
    Roles screen has nothing to match, or reads a nested group's address as a person."""

    async def scenario() -> None:
        stand = Stand(pages_by_url(google_directory()))
        source = await pull(
            stand, GOOGLE_WORKSPACE, token=TOKEN, location="example.com", groups=True
        )
        reading = source.reading()  # type: ignore[attr-defined]

        members = [one for one in stand.sent if "/members?" in one.url]
        assert {query(one.url)["includeDerivedMembership"] for one in members} == {"true"}
        assert all(one.headers["Authorization"] == f"Bearer {TOKEN}" for one in stand.sent)
        assert source.group_members == {  # type: ignore[attr-defined]
            "approvers@example.com": ("ada@example.com",),
            "auditors@example.com": ("katherine@example.com",),
        }
        assert reading.groups_complete is True
        ada = next(one for one in reading.roster.people if one.work_address == "ada@example.com")
        assert ada.groups == ("approvers@example.com",)

    asyncio.run(scenario())


def test_graph_groups_are_read_by_id_and_a_name_two_groups_share_confers_from_neither() -> None:
    """Members are selected by id and turned into addresses against the people just read, with the
    advanced-query header Graph requires for a select on members. Two groups called Approvers keep
    an entry each, told apart by id, so a rule on the bare name matches neither: that is how a
    retired group would otherwise go on appointing people.

    Delete this and one retired group sharing a name with a live one confers the live one's role,
    or the members call is sent without the header and Graph refuses every night."""

    async def scenario() -> None:
        stand = Stand(pages_by_url(graph_directory()))
        source = await pull(
            stand, MICROSOFT_ENTRA, token=TOKEN, location="example.com", groups=True
        )

        members = [one for one in stand.sent if "transitiveMembers" in one.url]
        assert len(members) == 3
        assert all(one.headers["ConsistencyLevel"] == "eventual" for one in members)
        assert {query(one.url)["$select"] for one in members} == {"id"}
        assert all(one.url.startswith(MICROSOFT_GRAPH_URL) for one in stand.sent)
        assert source.group_members == {  # type: ignore[attr-defined]
            "Approvers (a1b2c3d4-0000-4000-8000-000000000001)": ("ada@example.com",),
            "Auditors": ("katherine@example.com",),
            "Approvers (a1b2c3d4-0000-4000-8000-000000000003)": (),
        }
        assert "Approvers" not in source.group_members  # type: ignore[attr-defined]

    asyncio.run(scenario())


def test_lark_groups_are_read_by_union_id_and_a_member_nobody_listed_is_left_out() -> None:
    """Lark's user groups, members asked for as union ids and turned into the addresses the people
    walk read. A union id the walk never listed is somebody this roster cannot name.

    Delete this and the owner's Lark install reads no groups, or a member's union id is read as
    an address."""

    async def scenario() -> None:
        stand = Stand(pages_by_url(lark_pages()))
        source = await pull(stand, LARK, token=TOKEN, location="larksuite.com", groups=True)

        asked = [query(one.url) for one in stand.sent if "/member/simplelist" in one.url]
        assert asked == [{"page_size": "100", "member_id_type": "union_id", "member_type": "user"}]
        assert source.group_members == {"approvers": ("ada@example.com",)}  # type: ignore[attr-defined]

    asyncio.run(scenario())


@pytest.mark.parametrize("source", [GOOGLE_WORKSPACE, MICROSOFT_ENTRA, LARK])
def test_a_walk_not_asked_for_groups_reads_none(source: str) -> None:
    """The first-run trial proposes who would be added and nothing else, so it reads no group.

    Delete this and the wizard's sign-in asks every directory for groups it has no scope to read,
    and the trial fails before anybody has been shown their staff list."""

    async def scenario() -> None:
        pages = {**google_directory(), **graph_directory(), **lark_pages()}
        stand = Stand(pages_by_url(pages))
        await pull(stand, source, token=TOKEN, location=LOCATIONS[source])

        assert not [one for one in stand.sent if "group" in one.url.split("?")[0]]

    asyncio.run(scenario())


def test_a_group_id_not_shaped_as_an_identifier_is_never_put_in_a_path() -> None:
    """A group's id is the one part of a group address a response chose, so it is checked against
    `GROUP_ID` before it becomes a path, and a group that fails is skipped and counted as not read.

    Delete this and a group id of `../users` walks the token to another resource of the API."""

    async def scenario() -> None:
        crooked = {
            "groups": [
                {"id": "../users", "email": "crooked@example.com"},
                {"id": "01ksv4uv1x1a9z3", "email": "auditors@example.com"},
            ]
        }
        stand = Stand(pages_by_url({**google_directory(), "groups?": crooked}))
        source = await pull(
            stand, GOOGLE_WORKSPACE, token=TOKEN, location="example.com", groups=True
        )

        paths = {urlsplit(one.url).path for one in stand.sent}
        assert paths == {
            "/admin/directory/v1/users",
            "/admin/directory/v1/groups",
            "/admin/directory/v1/groups/01ksv4uv1x1a9z3/members",
        }
        assert source.group_members == {  # type: ignore[attr-defined]
            "auditors@example.com": ("katherine@example.com",)
        }
        assert source.reading().groups_complete is False  # type: ignore[attr-defined]

    asyncio.run(scenario())


def test_a_group_walk_that_runs_out_marks_the_groups_incomplete_and_not_the_roster() -> None:
    """`A_GROUP_WALK_IS_ITS_OWN_BUDGET`. The people's pages decide whether anybody may be removed;
    the groups have pages of their own, and running out of them says so on the groups.

    Delete this and a company with many groups has its roster read as incomplete every night, so
    nobody who leaves is ever marked as having left, or a stopped group walk reads as complete."""

    async def scenario() -> None:
        stand = Stand(pages_by_url(google_directory()))
        source = await pull(
            stand, GOOGLE_WORKSPACE, token=TOKEN, location="example.com", pages=2, groups=True
        )
        reading = source.reading()  # type: ignore[attr-defined]

        assert reading.roster.complete is True
        assert reading.groups_complete is False
        assert len([one for one in stand.sent if "users?" in one.url]) == 2
        assert len([one for one in stand.sent if "users?" not in one.url]) == 2

    asyncio.run(scenario())


def test_a_group_page_linking_off_graph_is_refused_and_the_token_never_goes_there() -> None:
    """The groups' next links are followed only on Graph, as the people's are.

    Delete this and the second walk is the one place a response can send the token elsewhere."""

    async def scenario() -> None:
        elsewhere = {**ENTRA_GROUPS_PAGE, "@odata.nextLink": "https://graph.example.invalid/g"}
        stand = Stand(pages_by_url({**graph_directory(), "/v1.0/groups?": elsewhere}))

        with pytest.raises(DirectorySignInError):
            await pull(stand, MICROSOFT_ENTRA, token=TOKEN, location="example.com", groups=True)
        assert {urlsplit(one.url).netloc for one in stand.sent} == {"graph.microsoft.com"}

    asyncio.run(scenario())


def test_each_read_asks_only_for_the_fields_the_roster_needs() -> None:
    """The staff sync reads people, their department, manager, whether they are still here, and
    groups, and nothing else: Google's `fields` and Graph's `$select` say which, and each Lark
    people request asks for union ids so the manager is named by the id the roster keeps.

    The expected sets are written here rather than imported, so the test cannot pass by comparing
    a constant with itself. Delete this and a read can start carrying phone numbers, addresses
    and custom attributes into a system that keeps none of them."""

    async def scenario() -> None:
        google = Stand(pages_by_url(google_directory()))
        await pull(google, GOOGLE_WORKSPACE, token=TOKEN, location="example.com")
        graph = Stand(pages_by_url(graph_directory()))
        await pull(graph, MICROSOFT_ENTRA, token=TOKEN, location="example.com")
        lark = Stand(pages_by_url(lark_pages()))
        await pull(lark, LARK, token=TOKEN, location="larksuite.com")

        assert query(google.sent[0].url)["fields"] == (
            "nextPageToken,users(id,primaryEmail,name/fullName,suspended,archived,orgUnitPath,"
            "aliases,relations)"
        )
        first = query(graph.sent[0].url)
        assert set(first["$select"].split(",")) == {
            "id",
            "userPrincipalName",
            "displayName",
            "department",
            "accountEnabled",
            "proxyAddresses",
        }
        assert first["$expand"] == "manager($select=id,userPrincipalName)"
        people = [query(one.url) for one in lark.sent if "find_by_department" in one.url]
        assert people
        assert {one["user_id_type"] for one in people} == {"union_id"}

    asyncio.run(scenario())
