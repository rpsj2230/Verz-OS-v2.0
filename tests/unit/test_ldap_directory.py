"""The LDAP and Active Directory reader, against a stand-in directory that pages like a real one.

`brain.connectors.ldap_directory` binds, protects and pages; `LdapSource` parses. These tests hold
the reader's half with a stand-in `DirectoryConnection` that answers pages with cookies and raw
bytes the way ldap3 hands them over, and a stand-in ldap3 connection for the bind order, so they
run where the library is not installed. The same walk over ldap3's own mock server is
`tests/unit/test_ldap_directory_ldap3.py`, which runs wherever ldap3 is importable.

Task ids: M1.6.6
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
import structlog

from brain.connectors import ldap_directory
from brain.connectors.ldap_directory import (
    CA_FILE_EXTENSION,
    DEFAULT_USER_FILTER,
    GROUP_FILTER_EXTENSION,
    LDAP_SETUP,
    NO_ATTRIBUTES,
    PAGE_SIZE,
    PERSON_ATTRIBUTES,
    PLAINTEXT_EXTENSION,
    SETUP_BY_SOURCE,
    TRIAL_PAGE_SIZE,
    BindAccount,
    Ldap3Directory,
    LdapBindRefusedError,
    LdapLibraryMissingError,
    LdapLocation,
    LdapLocationError,
    LdapUnreachableError,
    SearchPage,
    SearchScope,
    TlsMode,
    bind_account,
    location_and_credential,
    location_for,
    parse_location,
    read_directory,
    trial,
)
from brain.connectors.staff_directories import DirectorySignInError
from brain.identity.staff_adapters import (
    CHOOSABLE_SOURCES,
    LDAP,
    LDAP_SIZE_LIMIT_EXCEEDED,
    RosterUnavailableError,
)
from brain.identity.staff_source import StaffSourceError
from brain.ops.connector_slots import SLOT_SCOPES, STAFF_LIST
from brain.ops.staff_sync_run import STAFF_SOURCE_SLOT
from tests.fixtures import roster_payloads as recorded

BASE = "DC=example,DC=com"
LOCATION = f"ldaps://dc1.example.com/{BASE}"
PASSWORD = "sentinel-bind-password-7c1e"
BIND_NAME = "CN=svc-brain-read,OU=Service,DC=example,DC=com"
CREDENTIAL = f"{BIND_NAME}:{PASSWORD}"

Raw = Mapping[str, Sequence[bytes | str]]


def person(
    name: str,
    *,
    number: int,
    control: int = 512,
    groups: Sequence[str] = (),
    manager: str = "",
) -> tuple[str, Raw]:
    """One Active Directory entry as ldap3 hands it over: every value a list of bytes."""
    attributes: dict[str, list[bytes]] = {
        "objectGUID": [uuid.UUID(int=number).bytes_le],
        "mail": [f"{name}@example.com".encode()],
        "displayName": [name.title().encode()],
        "department": [b"engineering"],
        "userAccountControl": [str(control).encode()],
        "memberOf": [one.encode() for one in groups],
    }
    if manager:
        attributes["manager"] = [manager.encode()]
    return f"CN={name.title()},OU=Staff,{BASE}", attributes


def paged(entries: Sequence[tuple[str | None, Raw]], size: int, code: int = 0) -> list[SearchPage]:
    """Entries cut into pages whose cookie names the next page, as a server's cookie would."""
    chunks = [list(entries[at : at + size]) for at in range(0, len(entries), size)] or [[]]
    return [
        SearchPage(
            entries=tuple(chunk),
            result_code=code,
            cookie=str(at + 1).encode() if at + 1 < len(chunks) else b"",
        )
        for at, chunk in enumerate(chunks)
    ]


@dataclass
class Directory:
    """A bound connection that answers each filter from its own pages."""

    pages: Mapping[str, list[SearchPage]]
    asked: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def search_page(
        self,
        *,
        base: str,
        query: str,
        scope: SearchScope,
        attributes: Sequence[str],
        size: int,
        cookie: bytes,
    ) -> SearchPage:
        self.asked.append(
            {"base": base, "query": query, "scope": scope, "attributes": tuple(attributes)}
            | {"size": size, "cookie": cookie}
        )
        return self.pages[query][int(cookie.decode()) if cookie else 0]

    def close(self) -> None:
        self.closed = True


@dataclass
class Opened:
    """An `Opener` that records what it was handed and returns one directory."""

    directory: Directory
    handed: list[tuple[LdapLocation, BindAccount]] = field(default_factory=list)

    def __call__(self, location: LdapLocation, account: BindAccount) -> Directory:
        self.handed.append((location, account))
        return self.directory


STAFF = [
    person("ada", number=1, groups=[f"CN=Approvers,OU=Groups,{BASE}"]),
    person("grace", number=2, control=514, manager=f"CN=Ada,OU=Staff,{BASE}"),
    person("katherine", number=3, control=66048, manager=f"CN=Nobody,OU=Elsewhere,{BASE}"),
    person("dorothy", number=4, groups=[f"CN=Legacy,OU=Groups,{BASE}"]),
    (f"CN=svc-backup,OU=Service,{BASE}", {"displayName": [b"Backup"], "mail": []}),
]


def opened(pages: Mapping[str, list[SearchPage]]) -> Opened:
    return Opened(Directory(pages))


# ------------------------------------------------------------------------ the location
def test_ldaps_is_tls_from_the_first_byte_on_636_and_ldap_means_starttls_on_389() -> None:
    """The scheme decides the protection and the port it defaults to. Delete this and an
    `ldap://` address reads as whatever the parser falls into, which is the one place a
    plaintext bind could arrive without anybody having asked for it."""
    secure = parse_location(LOCATION)
    upgraded = parse_location(f"ldap://dc1.example.com/{BASE}")

    assert (secure.tls, secure.port, secure.base_dn) == (TlsMode.LDAPS, 636, BASE)
    assert (upgraded.tls, upgraded.port) == (TlsMode.STARTTLS, 389)
    assert secure.user_filter == DEFAULT_USER_FILTER
    assert secure.scope is SearchScope.SUBTREE


def test_plain_ldap_is_reachable_only_through_the_development_extension() -> None:
    """`PLAIN_LDAP_EXPOSES_THE_BIND`. Plain LDAP sends the service account's password as it is,
    so only an extension whose name says development reaches it, and it is refused beside
    `ldaps://`, which it would contradict. Delete this and a mistyped scheme is a password on the
    wire."""
    plain = parse_location(f"ldap://dc1.example.com/{BASE}????!{PLAINTEXT_EXTENSION}")

    assert plain.tls is TlsMode.PLAINTEXT_FOR_DEVELOPMENT
    with pytest.raises(LdapLocationError, match="ldaps:// address is TLS"):
        parse_location(f"{LOCATION}????!{PLAINTEXT_EXTENSION}")


def test_a_location_carrying_a_user_or_password_is_refused() -> None:
    """`A_CREDENTIAL_IN_THE_LOCATION_IS_A_CREDENTIAL_IN_THE_DATABASE`. The location is a setting
    and settings are stored in the database, so a password typed into it is refused, and the
    refusal does not repeat it. Delete this and the vault is bypassed by one paste."""
    with pytest.raises(LdapLocationError, match="vault") as refused:
        parse_location(f"ldaps://svc:{PASSWORD}@dc1.example.com/{BASE}")

    assert PASSWORD not in str(refused.value)
    assert parse_location(LOCATION).host == "dc1.example.com"


@pytest.mark.parametrize(
    ("location", "because"),
    [
        (f"https://dc1.example.com/{BASE}", "ldaps://"),
        ("ldaps://dc1.example.com/", "base the search starts"),
        (f"ldaps://dc1.example.com/{BASE}?mail", "attribute list"),
        (f"ldaps://dc1.example.com/{BASE}??base", "sub or one"),
        (f"ldaps://dc1.example.com/{BASE}???objectClass=person", "bracketed"),
        (f"ldaps://dc1.example.com/{BASE}????x-group-filtr=(cn=a)", "does not know"),
        (f"ldaps://dc1.example.com/{BASE}????{GROUP_FILTER_EXTENSION}=cn=a", "bracketed"),
        (f"ldaps:///{BASE}", "names no server"),
    ],
)
def test_a_location_this_reader_would_misread_is_refused_with_what_to_change(
    location: str, because: str
) -> None:
    """Each shape a person gets wrong, refused with a sentence rather than read. The unknown
    extension matters most: ignored, a mistyped group filter reads every group in the directory.
    Delete this and each of these reads a different search from the one somebody meant."""
    with pytest.raises(LdapLocationError, match=because):
        parse_location(location)


def test_a_location_built_from_fields_survives_commas_spaces_and_brackets() -> None:
    """A distinguished name has commas and a filter has brackets, both separators in an LDAP URL.
    `location_for` encodes them so that parsing gives back exactly what was typed. Delete this
    and a base DN with a space in an OU name becomes a search from somewhere else."""
    base = "OU=Head Office,DC=example,DC=com"
    groups = "(&(objectClass=group)(cn=Brain-*))"
    people = "(&(objectCategory=person)(objectClass=user))"

    url = location_for(
        "dc1.example.com",
        base,
        tls=TlsMode.STARTTLS,
        port=3389,
        user_filter=people,
        group_filter=groups,
        ca_file="/etc/brain/ca.pem",
    )
    back = parse_location(url)

    assert url.startswith("ldap://dc1.example.com:3389/")
    assert (back.base_dn, back.user_filter, back.group_filter) == (base, people, groups)
    assert (back.tls, back.port, back.ca_file) == (TlsMode.STARTTLS, 3389, "/etc/brain/ca.pem")
    assert f"{CA_FILE_EXTENSION}=" in url


# ------------------------------------------------------------------------ the credential
def test_an_empty_password_is_refused_before_anything_is_sent() -> None:
    """`A_BIND_WITH_NOTHING_TO_PROVE_IS_ANONYMOUS`. A simple bind with a name and no password is
    an unauthenticated bind that many servers answer with success and nobody's rights, and the
    search that follows reads nothing, which is a company everybody left. Delete this and a
    half-typed credential is a sync that proposes removing everyone."""
    directory = opened({DEFAULT_USER_FILTER: paged(STAFF, PAGE_SIZE)})

    with pytest.raises(LdapBindRefusedError, match="empty password"):
        read_directory(LOCATION, f"{BIND_NAME}:", opener=directory)
    assert directory.handed == []


def test_the_credential_splits_at_its_first_colon_so_a_colon_in_the_password_survives() -> None:
    """The positive side of the refusal above, and the shape refusal. Delete this and a
    password with a colon in it binds as something else."""
    account = bind_account(f"svc@example.com:{PASSWORD}:tail")

    assert (account.name, account.password) == ("svc@example.com", f"{PASSWORD}:tail")
    assert PASSWORD not in repr(account)
    with pytest.raises(LdapBindRefusedError, match="a colon"):
        bind_account(PASSWORD)


# ------------------------------------------------------------------------ the walk
def test_every_page_is_read_and_the_directory_is_parsed_into_people() -> None:
    """Three pages of two, followed by their cookies, into one roster with the stable
    identifier read out of the binary GUID. Delete this and a directory past one page is
    half a company."""
    directory = opened({DEFAULT_USER_FILTER: paged(STAFF, 2)})

    source = read_directory(LOCATION, CREDENTIAL, opener=directory, page_size=2)
    reading = source.reading()

    asked = directory.directory.asked
    assert [one["cookie"] for one in asked] == [b"", b"1", b"2"]
    assert {one["attributes"] for one in asked} == {PERSON_ATTRIBUTES}
    assert {one["base"] for one in asked} == {BASE}
    assert reading.roster.source == LDAP
    assert reading.roster.complete
    assert [one.work_address for one in reading.roster.people] == [
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
        "dorothy@example.com",
    ]
    assert reading.stable_ids["ada@example.com"] == "{" + str(uuid.UUID(int=1)) + "}"
    assert any("svc-backup" in one for one in reading.dropped)
    assert directory.directory.closed


def test_a_disabled_account_is_read_as_somebody_who_has_left() -> None:
    """514 has the disable bit and 66048 does not. A disabled account read as present keeps
    every role it held. Delete this and switching somebody off in the directory takes nothing
    away here."""
    reading = read_directory(
        LOCATION, CREDENTIAL, opener=opened({DEFAULT_USER_FILTER: paged(STAFF, 10)})
    ).reading()

    active = {one.work_address: one.active for one in reading.roster.people}
    assert active == {
        "ada@example.com": True,
        "grace@example.com": False,
        "katherine@example.com": True,
        "dorothy@example.com": True,
    }


def test_a_manager_is_resolved_only_against_people_in_the_same_read() -> None:
    """`manager` is a distinguished name. It resolves to an address when that person was read,
    and not otherwise. Delete this and a manager outside the base becomes a DN nobody can join."""
    reading = read_directory(
        LOCATION, CREDENTIAL, opener=opened({DEFAULT_USER_FILTER: paged(STAFF, 10)})
    ).reading()

    assert reading.managers == {"grace@example.com": "ada@example.com"}


def test_a_walk_that_stops_with_a_cookie_outstanding_is_not_complete() -> None:
    """The page cap stops the walk and the server had said there was more. Delete this and a
    directory bigger than the cap is a complete roster missing everyone past it."""
    source = read_directory(
        LOCATION,
        CREDENTIAL,
        opener=opened({DEFAULT_USER_FILTER: paged(STAFF, 2)}),
        page_size=2,
        max_pages=2,
    )

    assert source.more_pages
    assert len(source.roster().people) == 4
    assert not source.roster().complete


def test_a_size_limit_keeps_its_people_and_any_other_code_has_no_roster() -> None:
    """The server's verdict is passed to the parser unchanged: a truncation is an incomplete
    roster and a refusal raises. Delete this and a bind that lost its rights mid-walk is a
    company of nobody."""
    truncated = read_directory(
        LOCATION,
        CREDENTIAL,
        opener=opened({DEFAULT_USER_FILTER: paged(STAFF, 10, code=LDAP_SIZE_LIMIT_EXCEEDED)}),
    )
    assert truncated.roster().people
    assert not truncated.roster().complete

    refused = opened({DEFAULT_USER_FILTER: paged(STAFF, 10, code=50)})
    with pytest.raises(RosterUnavailableError, match="result code 50"):
        read_directory(LOCATION, CREDENTIAL, opener=refused).roster()
    assert refused.directory.closed


def test_a_referral_makes_the_read_incomplete() -> None:
    """A continuation reference is a forest domain this search did not cover. Delete this and
    the second domain is proposed for removal."""
    entries = [*STAFF[:1], (None, {"ref": [b"ldap://child.example.com/DC=child,DC=example"]})]

    source = read_directory(
        LOCATION, CREDENTIAL, opener=opened({DEFAULT_USER_FILTER: paged(entries, 10)})
    )

    assert not source.roster().complete


def test_a_group_filter_keeps_only_the_memberships_it_matches() -> None:
    """With a group filter only matching groups count, which is how a company keeps a legacy
    group from conferring a role. Groups are asked for by name alone. Delete this and every
    group in the directory is read as a membership."""
    groups = "(&(objectClass=group)(cn=Approvers))"
    location = location_for("dc1.example.com", BASE, group_filter=groups)
    matched: list[tuple[str | None, Raw]] = [(f"CN=Approvers,OU=Groups,{BASE}", {})]
    directory = opened({groups: paged(matched, 10), DEFAULT_USER_FILTER: paged(STAFF, 10)})

    reading = read_directory(location, CREDENTIAL, opener=directory).reading()

    held = {one.work_address: one.groups for one in reading.roster.people}
    assert held["ada@example.com"] == (f"CN=Approvers,OU=Groups,{BASE}",)
    assert held["dorothy@example.com"] == ()
    assert directory.directory.asked[0]["attributes"] == (NO_ATTRIBUTES,)
    assert reading.roster.complete


def test_an_unfinished_group_read_makes_the_roster_incomplete() -> None:
    """A membership dropped for want of its group page is a role removed for want of a page.
    Delete this and a capped group walk quietly takes roles away."""
    groups = "(objectClass=group)"
    location = location_for("dc1.example.com", BASE, group_filter=groups)
    many: list[tuple[str | None, Raw]] = [(f"CN=G{at},OU=Groups,{BASE}", {}) for at in range(4)]
    directory = opened({groups: paged(many, 2), DEFAULT_USER_FILTER: paged(STAFF, 10)})

    source = read_directory(location, CREDENTIAL, opener=directory, page_size=2, max_pages=1)

    assert not source.roster().complete


def test_the_connection_is_closed_when_the_read_fails() -> None:
    """A walk that raises still unbinds. Delete this and every failing run leaves a bound
    session open on the domain controller."""

    class Failing(Directory):
        def search_page(self, **_: Any) -> SearchPage:
            raise LdapUnreachableError("gone")

    directory = Opened(Failing({}))
    with pytest.raises(LdapUnreachableError):
        read_directory(LOCATION, CREDENTIAL, opener=directory)
    assert directory.directory.closed


def test_plaintext_is_logged_loudly_and_the_password_never_is() -> None:
    """Every plaintext read leaves a warning naming the server, and no log line, refusal or
    handed value carries the password beyond the bind. Delete this and the escape hatch is
    silent, or the credential reaches a log."""
    location = f"ldap://dc1.example.com/{BASE}????!{PLAINTEXT_EXTENSION}"
    directory = opened({DEFAULT_USER_FILTER: paged(STAFF, 10)})

    with structlog.testing.capture_logs() as logs:
        read_directory(location, CREDENTIAL, opener=directory)

    assert [one["event"] for one in logs] == ["ldap_plaintext_bind"]
    assert logs[0]["server"] == "dc1.example.com:389"
    assert PASSWORD not in repr(logs)
    assert directory.handed[0][1].password == PASSWORD

    with structlog.testing.capture_logs() as quiet:
        read_directory(LOCATION, CREDENTIAL, opener=opened({DEFAULT_USER_FILTER: paged(STAFF, 9)}))
    assert quiet == []


# ------------------------------------------------------------------------ the bind order
@dataclass
class Ldap3Stand:
    """The four calls `Ldap3Directory.begin` makes on an ldap3 connection, recorded."""

    starts_tls: bool = True
    binds: bool = True
    result: dict[str, Any] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def open(self) -> None:
        self.calls.append("open")

    def start_tls(self) -> bool:
        self.calls.append("start_tls")
        return self.starts_tls

    def bind(self) -> bool:
        self.calls.append("bind")
        return self.binds

    def unbind(self) -> None:
        self.calls.append("unbind")


def test_a_declined_starttls_refuses_before_the_account_is_sent() -> None:
    """`PLAIN_LDAP_EXPOSES_THE_BIND`. StartTLS the server declines is a refusal, never a
    fallback to binding in the clear. Delete this and a directory with StartTLS switched off is
    handed the service account's password as it is."""
    stand = Ldap3Stand(starts_tls=False)

    with pytest.raises(LdapUnreachableError, match="would not start TLS"):
        Ldap3Directory.begin(stand, parse_location(f"ldap://dc1.example.com/{BASE}"))

    assert stand.calls == ["open", "start_tls", "unbind"]


def test_starttls_comes_before_the_bind_and_ldaps_needs_no_upgrade() -> None:
    """The positive side: the upgrade happens first, then the bind. Delete this and a refusing
    StartTLS test is satisfied by a reader that never binds at all."""
    upgraded = Ldap3Stand()
    Ldap3Directory.begin(upgraded, parse_location(f"ldap://dc1.example.com/{BASE}"))
    secure = Ldap3Stand()
    Ldap3Directory.begin(secure, parse_location(LOCATION))

    assert upgraded.calls == ["open", "start_tls", "bind"]
    assert secure.calls == ["open", "bind"]


def test_a_refused_bind_is_the_credential_and_names_neither_account_nor_password() -> None:
    """Result 49 is the name or password refused, which the sync records as a refused credential
    rather than an unreachable directory. Delete this and a wrong password reads as an outage."""
    stand = Ldap3Stand(binds=False, result={"result": 49, "description": "invalidCredentials"})

    with pytest.raises(LdapBindRefusedError) as refused:
        Ldap3Directory.begin(stand, parse_location(LOCATION))

    assert "dc1.example.com:636" in str(refused.value)
    assert BIND_NAME not in str(refused.value)
    assert stand.calls[-1] == "unbind"
    other = Ldap3Stand(binds=False, result={"result": 8, "description": "strongerAuthRequired"})
    with pytest.raises(LdapUnreachableError, match="strongerAuthRequired"):
        Ldap3Directory.begin(other, parse_location(LOCATION))


def test_an_install_without_the_library_is_told_so_in_a_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LDAP3_IS_LGPL_AND_ALLOWED_BY_NAME`. An image built without the library, choosing LDAP,
    gets a misconfiguration saying why rather than an import error in a worker log. Delete this
    and the sync's MISCONFIGURED row says nothing."""
    real = importlib.import_module

    def without(name: str, package: str | None = None) -> Any:
        if name.startswith("ldap3"):
            raise ModuleNotFoundError(name)
        return real(name, package)

    monkeypatch.setattr(importlib, "import_module", without)
    with pytest.raises(LdapLibraryMissingError, match="no LDAP client library") as refused:
        read_directory(LOCATION, CREDENTIAL)
    assert isinstance(refused.value, StaffSourceError)


def test_the_refusals_land_where_the_sync_sorts_them() -> None:
    """A bad location and a missing library are misconfigurations, an unreachable directory is
    unreachable, a refused bind is neither. Delete this and `staff_sync_run` files a wrong
    password under an outage."""
    assert issubclass(LdapLocationError, StaffSourceError)
    assert issubclass(LdapLibraryMissingError, StaffSourceError)
    assert issubclass(LdapUnreachableError, DirectorySignInError)
    assert not issubclass(LdapBindRefusedError, (StaffSourceError, DirectorySignInError))


# ------------------------------------------------------------------------ trial and setup
def test_a_trial_reads_one_small_page_and_says_what_came_back() -> None:
    """The console's Test reads one page of `TRIAL_PAGE_SIZE`, never more, and reports it.
    Delete this and pressing Test walks the whole directory."""
    directory = opened({DEFAULT_USER_FILTER: paged(STAFF, TRIAL_PAGE_SIZE)})

    result = trial(LOCATION, CREDENTIAL, opener=directory)

    assert len(directory.directory.asked) == 1
    assert directory.directory.asked[0]["size"] == TRIAL_PAGE_SIZE
    assert (result.people, result.active, result.with_stable_identifier) == (4, 3, 4)
    assert result.tls is TlsMode.LDAPS
    assert result.warning == ""
    assert not result.more_than_one_page


def test_every_connect_field_is_used_and_the_password_goes_only_to_the_credential() -> None:
    """The connect flow's fields compose into the location and the credential, and the password
    is in the credential and never in the location. Delete this and a field on the screen is
    silently thrown away, or the password lands in a setting."""
    answers = {
        "host": "dc1.example.com",
        "tls": "starttls",
        "port": "389",
        "base_dn": BASE,
        "user_filter": "(objectClass=user)",
        "group_filter": "(objectClass=group)",
        "ca_file": "/etc/brain/ca.pem",
        "bind_name": BIND_NAME,
        "password": PASSWORD,
    }
    assert {one.name for one in LDAP_SETUP.fields} == set(answers)

    location, credential = location_and_credential(answers)
    parsed = parse_location(location)

    assert PASSWORD not in location
    assert credential == CREDENTIAL
    assert (parsed.host, parsed.tls, parsed.port) == ("dc1.example.com", TlsMode.STARTTLS, 389)
    assert (parsed.user_filter, parsed.group_filter) == (
        "(objectClass=user)",
        "(objectClass=group)",
    )
    assert parsed.ca_file == "/etc/brain/ca.pem"
    with pytest.raises(LdapBindRefusedError):
        location_and_credential(answers | {"password": ""})
    with pytest.raises(LdapLocationError, match="ldaps or starttls"):
        location_and_credential(answers | {"tls": "none"})


def test_the_setup_metadata_is_for_a_source_an_install_can_choose_and_names_what_is_read() -> None:
    """The metadata is keyed by a choosable source, marks the account and password secret, and
    lists every attribute read. Delete this and the screen offers a source nothing reads, or
    shows an administrator less than the reader asks for."""
    assert set(SETUP_BY_SOURCE) <= set(CHOOSABLE_SOURCES)
    assert SETUP_BY_SOURCE[LDAP] is LDAP_SETUP
    assert LDAP_SETUP.reads == PERSON_ATTRIBUTES
    assert {one.name for one in LDAP_SETUP.fields if one.secret} == {"bind_name", "password"}
    assert any("636" in step for step in LDAP_SETUP.steps)


def test_the_staff_list_slot_is_the_one_the_sync_reads() -> None:
    """The catalogue defines the slot the scheduled sync leases, held equal to the reader's own
    constant rather than to itself. Delete this and the installer defines a slot nothing reads."""
    assert STAFF_LIST == STAFF_SOURCE_SLOT
    assert SLOT_SCOPES[STAFF_LIST].path == f"connector_keys/{STAFF_SOURCE_SLOT}"
    assert any("bind and search" in one for one in SLOT_SCOPES[STAFF_LIST].request)


def test_the_recorded_directory_still_parses_through_the_reader() -> None:
    """The recorded Active Directory entries, handed over as text rather than bytes, parse to the
    same roster through the reader as through the adapter. Delete this and the reader's decoding
    is tested only against entries it built itself."""
    source = read_directory(
        LOCATION,
        CREDENTIAL,
        opener=opened({DEFAULT_USER_FILTER: paged(recorded.ACTIVE_DIRECTORY_ENTRIES, 2)}),
        page_size=2,
    )

    assert [one.work_address for one in source.roster().people] == [
        "ada@example.com",
        "grace@example.com",
        "katherine@example.com",
    ]


class StandInLdap3:
    """The four names `ldap3_connection` takes from ldap3, recording what each was built with."""

    NONE = "NONE"
    SIMPLE = "SIMPLE"
    SYNC = "SYNC"

    def __init__(self) -> None:
        self.built: dict[str, dict[str, Any]] = {}

    def _recorder(self, name: str) -> Any:
        def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.built[name] = {"args": args, **kwargs}
            return self.built[name]

        return build

    def __getattr__(self, name: str) -> Any:
        return self._recorder(name)


def built_with(monkeypatch: pytest.MonkeyPatch, location: str) -> dict[str, dict[str, Any]]:
    """What `ldap3_connection` hands ldap3 for this location, with no ldap3 installed."""
    stand = StandInLdap3()
    real = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, package=None: stand if name == "ldap3" else real(name, package),
    )
    ldap_directory.ldap3_connection(parse_location(location), BindAccount(BIND_NAME, PASSWORD))
    return stand.built


def test_the_connection_is_built_read_only_with_verified_modern_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`A_DIRECTORY_ACCOUNT_THAT_CAN_WRITE_IS_NOT_ASKED_FOR` and `PLAIN_LDAP_EXPOSES_THE_BIND`,
    as the arguments ldap3 is handed: read-only, referrals not followed, the certificate required
    and verified, TLS 1.0 and 1.1 off, LDAPS wrapped from the first byte. Held here as well as
    over the mock server because this file is the one that runs where ldap3 is not installed.
    Delete this and a writable connection or an unverified certificate ships unnoticed."""
    import ssl

    secure = built_with(monkeypatch, LOCATION)
    upgraded = built_with(monkeypatch, f"ldap://dc1.example.com/{BASE}")
    plain = built_with(monkeypatch, f"ldap://dc1.example.com/{BASE}????!{PLAINTEXT_EXTENSION}")

    assert secure["Connection"]["read_only"] is True
    assert secure["Connection"]["auto_referrals"] is False
    assert secure["Tls"]["validate"] == ssl.CERT_REQUIRED
    assert {ssl.OP_NO_TLSv1, ssl.OP_NO_TLSv1_1} <= set(secure["Tls"]["ssl_options"])
    assert (secure["Server"]["use_ssl"], secure["Server"]["port"]) == (True, 636)
    assert secure["Server"]["tls"] is secure["Tls"]
    assert upgraded["Server"]["use_ssl"] is False
    assert upgraded["Server"]["tls"] is upgraded["Tls"]
    assert "Tls" not in plain
    assert plain["Server"]["tls"] is None
