"""Reading an LDAP directory or Active Directory: bind read-only over TLS, page, hand over entries.

`brain.identity.staff_adapters.LdapSource` has parsed directory entries since M1.6.6 was first
opened, and said plainly that nothing fetched them: `brain.ops.staff_sync_run` answered every
LDAP run with "this product carries no directory client". This is that client's half. It knows
where the directory is, how to reach it safely, what to ask for and in what order, and it hands
the parser `(distinguished name, attributes)` pairs exactly as it has always taken them. It adds
no rule the parser or `staff_source.trust_for` already has; LDAP is trusted with existence,
department and role by `DEFAULT_TRUST`, as the other directories are.

**The directory is named by one value, an RFC 4516 LDAP URL, and nothing else.**
`staff_source.SELECTABLE` already argued it: an LDAP address carries the base a search starts
from, and two settings that can disagree about where a search starts is a roster silently about
a sub-tree. So `INSTALL_STAFF_SOURCE_LOCATION` is `ldaps://dc.example.com/DC=example,DC=com??sub?
(filter)?x-group-filter=...` and `location_for` builds it from the plain fields a setup screen
asks for, so nobody types percent-encoding by hand. See `ONE_URL_NAMES_THE_WHOLE_SEARCH`.

**TLS is required, and the plaintext escape is spelled so that nobody takes it by accident.**
`ldaps://` is TLS from the first byte and `ldap://` means StartTLS before the bind, and a
StartTLS the server declines is a refusal rather than a fallback. Plain LDAP sends the service
account's password across the network in the clear, so it is reachable only through the
extension `!x-plaintext-for-development-only` on an `ldap://` URL, and every read under it is
logged as a warning and says so on the trial. Certificates are validated always; a company whose
directory uses an internal certificate authority names its file with `x-ca-file`. See
`PLAIN_LDAP_EXPOSES_THE_BIND`.

**Read-only three times over, because a directory account is the keys to a company.** The
connection is opened with ldap3's `read_only`, which refuses an add, a modify or a delete
before anything is sent; the protocol this module hands the walk has one verb, a search page;
and the setup steps tell the administrator to create an account that can bind and search and
nothing more. See `A_DIRECTORY_ACCOUNT_THAT_CAN_WRITE_IS_NOT_ASKED_FOR`.

**An empty password is refused before it is sent.** An LDAP simple bind with a name and no
password is an "unauthenticated bind", which many servers, Active Directory among them, answer
with success and the rights of nobody. A sync that then reads nothing is a company everybody
left. See `A_BIND_WITH_NOTHING_TO_PROVE_IS_ANONYMOUS`.

**The credential is the vault's, and it is carried no further than the bind.** It is kept at
`connector_keys/staff_source` as `<bind name>:<password>` (the same one value the other
directories keep as `<id>:<secret>`), read by the worker through a run lease, handed to the
bind, and appears in no refusal, no log line, no representation and no row. A location naming
a user or a password in the URL is refused, because a location is a setting and settings are
stored in the database. See `A_CREDENTIAL_IN_THE_LOCATION_IS_A_CREDENTIAL_IN_THE_DATABASE`.

**Paging is the simple paged results control, and completeness is still the server's to say.**
Active Directory's `MaxPageSize` is a thousand; `PAGE_SIZE` is under it. The walk stops at
`staff_directories.MAX_PAGES` rather than following a server for ever, and when it stops early
the parser is told that a cookie was still outstanding, so the roster reads as incomplete from
what the server said exactly as a size limit or a referral does.

**The library is ldap3, a dependency by the owner's decision, imported when LDAP is read.**
It is the maintained pure-Python LDAP client, with a mock server the tests run against, and it
is LGPL-3.0-or-later. The allowlist admits the LGPL for psycopg's named reason rather than in
general, so the owner allowed ldap3 by name on 2026-09-22 (needs-rupash item 93), recorded in
`brain.ops.dependency_policy.OWNER_ALLOWED`. The permissive alternatives are not pure Python
(`bonsai`, `python-ldap` bind the C OpenLDAP library), are unmaintained (`ldaptor`, 2021) or
are penetration-testing toolkits (`msldap`, `badldap`). An image built before it was added,
choosing LDAP, gets a sentence saying the client library is not installed rather than an import
error. See `LDAP3_IS_LGPL_AND_ALLOWED_BY_NAME`.

Rejected: a second setting per part of the search (host, port, base, filter). Every one of them
would be read by `brain.install.value_of`, declared, shown on the Settings screen and able to
disagree with the others, for a value RFC 4516 already writes as one string.

Rejected: writing an LDAP client here. Bind, StartTLS and a paged search are a few hundred lines
of BER; an RFC 4515 filter parser, referrals and every server's quirks are the rest, and a
security-critical protocol written once for one product is the wrong place to save a dependency.

Task ids: M1.6.6
"""

from __future__ import annotations

import enum
import importlib
import ssl
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from urllib.parse import quote, unquote, urlsplit

import structlog

from brain.connectors.staff_directories import MAX_PAGES, DirectorySignInError
from brain.identity.staff_adapters import LDAP, LDAP_SUCCESS, LdapSource
from brain.identity.staff_source import StaffSourceError

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the whole search is one URL.
ONE_URL_NAMES_THE_WHOLE_SEARCH: Final = (
    "Where a directory search starts, what it matches and how it is protected are one decision, "
    "and RFC 4516 already writes it as one LDAP URL. Separate settings for each part would each "
    "be declared, stored and shown, and able to disagree with the others, which is a roster "
    "that is silently about a sub-tree nobody chose."
)

#: Why plain LDAP is refused unless named for development.
PLAIN_LDAP_EXPOSES_THE_BIND: Final = (
    "A simple bind sends the service account's name and password as they are. Over plain LDAP "
    "anybody on the network path reads a credential that can list every person in the company, "
    "so ldaps:// or StartTLS is required, a StartTLS the server declines refuses the read, and "
    "plain LDAP is reachable only through an extension whose name says it is for development."
)

#: Why the connection is read-only as well as the account.
A_DIRECTORY_ACCOUNT_THAT_CAN_WRITE_IS_NOT_ASKED_FOR: Final = (
    "A staff list is read and never written back. The account asked for can bind and search "
    "and nothing more, the connection refuses a write before sending it, and the one thing the "
    "walk can ask of a connection is a page of search results. Any one of the three would do; "
    "all three are there because the account is the one most often over-granted."
)

#: Why an empty password never reaches the server.
A_BIND_WITH_NOTHING_TO_PROVE_IS_ANONYMOUS: Final = (
    "A simple bind with a name and an empty password is an unauthenticated bind, and many "
    "servers answer it with success and the rights of nobody. The search then reads nothing, "
    "and nothing is what a company everybody left looks like, so an empty password is refused "
    "here rather than sent."
)

#: Why a user or password in the location is refused.
A_CREDENTIAL_IN_THE_LOCATION_IS_A_CREDENTIAL_IN_THE_DATABASE: Final = (
    "The location is an installation setting, stored in the database and shown on the Settings "
    "screen. A password written into it is a password in both, so a location carrying a user "
    "or a password is refused and the credential goes to the vault slot."
)

#: Why ldap3 is allowed by name, and why it is still imported late.
LDAP3_IS_LGPL_AND_ALLOWED_BY_NAME: Final = (
    "ldap3 is LGPL-3.0-or-later and the dependency policy admits the LGPL for psycopg's named "
    "reason, not in general, so the owner allowed it by name on 2026-09-22 (needs-rupash item "
    "93): used unmodified and pinned in uv.lock, so a client could replace it. It is imported "
    "only when an LDAP source is read, so an image built without it is told so in a sentence."
)

# ------------------------------------------------------------------------ the protocol
#: The two schemes, and the ports each defaults to.
LDAPS_SCHEME: Final = "ldaps"
LDAP_SCHEME: Final = "ldap"
DEFAULT_PORTS: Final[Mapping[str, int]] = {LDAPS_SCHEME: 636, LDAP_SCHEME: 389}

#: The extensions a location may carry. Any other is refused, not ignored: a mistyped group
#: filter that was ignored would read every group in the directory.
GROUP_FILTER_EXTENSION: Final = "x-group-filter"
CA_FILE_EXTENSION: Final = "x-ca-file"
PLAINTEXT_EXTENSION: Final = "x-plaintext-for-development-only"
KNOWN_EXTENSIONS: Final = frozenset(
    {GROUP_FILTER_EXTENSION, CA_FILE_EXTENSION, PLAINTEXT_EXTENSION}
)

#: People, and not the computers Active Directory also files under `person`. A computer object
#: is a subclass of `user`, which is a subclass of `person`, so `(objectClass=person)` alone
#: lists every workstation in the domain. Works unchanged against OpenLDAP.
DEFAULT_USER_FILTER: Final = "(&(objectClass=person)(!(objectClass=computer)))"

#: What is asked for about each person, and nothing else. `manager` is a distinguished name.
PERSON_ATTRIBUTES: Final[tuple[str, ...]] = (
    "objectGUID",
    "entryUUID",
    "mail",
    "userPrincipalName",
    "displayName",
    "cn",
    "department",
    "ou",
    "manager",
    "userAccountControl",
    "memberOf",
)

#: The attribute list that asks for no attributes at all (RFC 4511): a group search wants names.
NO_ATTRIBUTES: Final = "1.1"

#: One page of a staff read. Under Active Directory's default `MaxPageSize` of a thousand.
PAGE_SIZE: Final = 500

#: One page of a trial. Enough to see the mapping work, small enough to be quick.
TRIAL_PAGE_SIZE: Final = 25

#: How long reaching the server and waiting for one answer may take.
CONNECT_TIMEOUT_SECONDS: Final = 10
RECEIVE_TIMEOUT_SECONDS: Final = 30

#: The LDAP result code for a bind whose name or password the server refused.
INVALID_CREDENTIALS: Final = 49

#: The binary attribute that carries Active Directory's stable identifier, little-endian.
OBJECT_GUID: Final = "objectguid"

#: How the bind name and its password are kept as one value in the vault.
CREDENTIAL_SEPARATOR: Final = ":"

#: The simple paged results control (RFC 2696), whose cookie says whether more pages remain.
PAGED_RESULTS_CONTROL: Final = "1.2.840.113556.1.4.319"


class TlsMode(enum.Enum):
    """How the connection to the directory is protected."""

    LDAPS = "ldaps"
    STARTTLS = "starttls"
    #: No protection at all. Reachable only through `PLAINTEXT_EXTENSION`.
    PLAINTEXT_FOR_DEVELOPMENT = "plaintext-for-development-only"


class SearchScope(enum.Enum):
    """How far below the base a search reaches. `base` alone reads one entry and is refused."""

    SUBTREE = "sub"
    ONE_LEVEL = "one"


class LdapLocationError(StaffSourceError):
    """The location is not an LDAP URL this product will read. The message is for the person."""


class LdapBindRefusedError(Exception):
    """The directory refused the service account, or the kept credential is not shaped as one."""


class LdapUnreachableError(DirectorySignInError):
    """The directory could not be reached, or would not agree to protect the connection."""


class LdapLibraryMissingError(StaffSourceError):
    """This install has no LDAP client library. See `LDAP3_IS_LGPL_AND_ALLOWED_BY_NAME`."""


@dataclass(frozen=True)
class LdapLocation:
    """Where the directory is and what to search for, read out of one LDAP URL."""

    host: str
    port: int
    tls: TlsMode
    base_dn: str
    scope: SearchScope = SearchScope.SUBTREE
    user_filter: str = DEFAULT_USER_FILTER
    #: Empty for every group a person is in. Otherwise only groups this filter matches count.
    group_filter: str = ""
    #: A certificate authority file for a directory whose certificate an internal CA signed.
    ca_file: str = ""


@dataclass(frozen=True)
class BindAccount:
    """The read-only service account. The password is left out of every representation."""

    name: str
    password: str = field(repr=False)


def _balanced(query: str) -> bool:
    """Whether a filter is bracketed and its brackets balance. The library checks the rest."""
    if not (query.startswith("(") and query.endswith(")")):
        return False
    depth = 0
    for char in query:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


def parse_location(text: str) -> LdapLocation:
    """The location as an `LdapLocation`, or a refusal saying what to change.

    `ldap://host/base??scope?filter?extensions`, from RFC 4516, with the attribute list left
    empty because this module chooses what it reads. See `ONE_URL_NAMES_THE_WHOLE_SEARCH`.
    """
    given = text.strip()
    parts = urlsplit(given)
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        msg = (
            "The directory address has to begin with ldaps:// (port 636) or ldap:// (port 389, "
            "upgraded with StartTLS), for example ldaps://dc.example.com/DC=example,DC=com."
        )
        raise LdapLocationError(msg)
    if parts.username is not None or parts.password is not None:
        msg = (
            "The directory address carries a user or a password. Remove it: the service "
            "account's name and password are kept in the vault, never in a setting."
        )
        raise LdapLocationError(msg)
    host = (parts.hostname or "").strip()
    if not host:
        raise LdapLocationError("The directory address names no server.")
    try:
        port = parts.port or DEFAULT_PORTS[scheme]
    except ValueError as bad:
        raise LdapLocationError("The directory address has a port that is not a number.") from bad

    # urlsplit puts everything after the first `?` in the query; RFC 4516 separates four
    # fields there with further `?`, each percent-encoded on its own.
    split = parts.query.split("?")
    if len(split) > 4:
        raise LdapLocationError("The directory address has more than four `?` fields.")
    split += [""] * (4 - len(split))
    # Extensions are decoded one by one below, after splitting on the commas between them.
    attributes, scope_text, query = (unquote(one) for one in split[:3])
    extensions = split[3]

    base_dn = unquote(parts.path.removeprefix("/")).strip()
    if "=" not in base_dn:
        msg = (
            "The directory address needs the base the search starts from after the server, "
            "for example ldaps://dc.example.com/DC=example,DC=com."
        )
        raise LdapLocationError(msg)
    if attributes.strip():
        msg = (
            "Leave the attribute list in the directory address empty (two `?` in a row): what "
            "is read about each person is fixed, so nothing more than it is ever asked for."
        )
        raise LdapLocationError(msg)
    scopes = {one.value: one for one in SearchScope}
    chosen_scope = scopes.get(scope_text.strip().lower() or SearchScope.SUBTREE.value)
    if chosen_scope is None:
        msg = "The search scope has to be sub or one: base reads a single entry, not a staff list."
        raise LdapLocationError(msg)
    user_filter = query.strip() or DEFAULT_USER_FILTER
    if not _balanced(user_filter):
        raise LdapLocationError("The people filter has to be bracketed, like (objectClass=person).")

    options: dict[str, str] = {}
    for raw in (one for one in extensions.split(",") if one.strip()):
        name, _, value = unquote(raw).strip().partition("=")
        name = name.removeprefix("!").strip().lower()
        if name not in KNOWN_EXTENSIONS:
            msg = (
                f"The directory address carries the extension {name!r}, which this product "
                f"does not know. It knows {sorted(KNOWN_EXTENSIONS)}, and an unknown one is "
                "refused rather than ignored."
            )
            raise LdapLocationError(msg)
        options[name] = value.strip()

    group_filter = options.get(GROUP_FILTER_EXTENSION, "")
    if group_filter and not _balanced(group_filter):
        raise LdapLocationError("The group filter has to be bracketed, like (objectClass=group).")

    if PLAINTEXT_EXTENSION in options:
        if scheme != LDAP_SCHEME:
            msg = f"{PLAINTEXT_EXTENSION} means no TLS at all, and an ldaps:// address is TLS."
            raise LdapLocationError(msg)
        tls = TlsMode.PLAINTEXT_FOR_DEVELOPMENT
    else:
        tls = TlsMode.LDAPS if scheme == LDAPS_SCHEME else TlsMode.STARTTLS

    return LdapLocation(
        host=host,
        port=port,
        tls=tls,
        base_dn=base_dn,
        scope=chosen_scope,
        user_filter=user_filter,
        group_filter=group_filter,
        ca_file=options.get(CA_FILE_EXTENSION, ""),
    )


#: What `quote` may leave alone inside one RFC 4516 field: never `?`, `,`, `/` or `%`.
_FIELD_SAFE: Final = "=()&|!*:@-._~ "


def location_for(
    host: str,
    base_dn: str,
    *,
    port: int | None = None,
    tls: TlsMode = TlsMode.LDAPS,
    user_filter: str = "",
    group_filter: str = "",
    ca_file: str = "",
) -> str:
    """The one LDAP URL for the plain fields a setup screen asks for, checked by parsing it back.

    Built here so that nobody percent-encodes a distinguished name by hand, and parsed back
    before it is returned so that a value this module would refuse is refused while the
    person is still on the screen that asked for it.
    """
    scheme = LDAPS_SCHEME if tls is TlsMode.LDAPS else LDAP_SCHEME
    netloc = host.strip() if port is None else f"{host.strip()}:{port}"
    extensions = []
    if group_filter.strip():
        extensions.append(
            f"{GROUP_FILTER_EXTENSION}={quote(group_filter.strip(), safe=_FIELD_SAFE)}"
        )
    if ca_file.strip():
        extensions.append(f"{CA_FILE_EXTENSION}={quote(ca_file.strip(), safe=_FIELD_SAFE + '/')}")
    if tls is TlsMode.PLAINTEXT_FOR_DEVELOPMENT:
        extensions.append(f"!{PLAINTEXT_EXTENSION}")
    url = (
        f"{scheme}://{netloc}/{quote(base_dn.strip(), safe=_FIELD_SAFE)}"
        f"??{SearchScope.SUBTREE.value}?{quote(user_filter.strip(), safe=_FIELD_SAFE)}"
    )
    if extensions:
        url = f"{url}?{','.join(extensions)}"
    parse_location(url)
    return url


def bind_account(credential: str) -> BindAccount:
    """The service account out of the kept credential, refusing an anonymous or empty one.

    Split at the first colon, the way the other directories keep `<id>:<secret>`, so a colon
    in the password survives. See `A_BIND_WITH_NOTHING_TO_PROVE_IS_ANONYMOUS`.
    """
    name, separator, password = credential.partition(CREDENTIAL_SEPARATOR)
    if not separator or not name.strip():
        msg = (
            "The kept credential is not in the form an LDAP source needs: the service account's "
            "name (a distinguished name, or name@domain), a colon, then its password"
        )
        raise LdapBindRefusedError(msg)
    if not password:
        raise LdapBindRefusedError(
            "The kept credential has an empty password, which a directory reads as an "
            "unauthenticated bind with the rights of nobody. It was not sent"
        )
    return BindAccount(name=name.strip(), password=password)


# ------------------------------------------------------------------------ the transport
@dataclass(frozen=True)
class SearchPage:
    """One page of results as the server gave it: entries, the result code, and the cookie.

    An entry with no name is a continuation reference, which the parser reads as a search that
    did not cover everything. Values may be bytes or text; the walk decodes them.
    """

    entries: tuple[tuple[str | None, Mapping[str, Sequence[bytes | str]]], ...]
    result_code: int
    cookie: bytes = b""


class DirectoryConnection(Protocol):
    """A bound, protected connection with one verb. See the read-only reason."""

    def search_page(
        self,
        *,
        base: str,
        query: str,
        scope: SearchScope,
        attributes: Sequence[str],
        size: int,
        cookie: bytes,
    ) -> SearchPage: ...

    def close(self) -> None: ...


class Opener(Protocol):
    """Opens, protects and binds a connection, or raises one of this module's refusals."""

    def __call__(self, location: LdapLocation, account: BindAccount) -> DirectoryConnection: ...


def _ldap3() -> Any:
    """The ldap3 module, or a sentence saying it is not installed."""
    try:
        return importlib.import_module("ldap3")
    except ModuleNotFoundError as missing:
        msg = (
            "This install has no LDAP client library, so an LDAP directory cannot be read yet. "
            "The library (ldap3) is a dependency of this product, so this image predates it or "
            "was built without it; rebuild it, or choose another staff source. Nobody was "
            "changed."
        )
        raise LdapLibraryMissingError(msg) from missing


class _NeverRaisedError(Exception):
    """Stands in for the library's exceptions where the library is absent, so nothing matches."""


def _library_failure(name: str = "LDAPException") -> type[Exception]:
    """One of ldap3's exception classes, or one nothing raises when ldap3 is not installed.

    Looked up rather than imported so `Ldap3Directory.begin` runs over any connection object,
    which is how its StartTLS and bind refusals are tested where the library is not installed.
    """
    try:
        found: type[Exception] = getattr(
            importlib.import_module("ldap3.core.exceptions"), name, _NeverRaisedError
        )
    except ModuleNotFoundError:
        return _NeverRaisedError
    return found


def ldap3_connection(
    location: LdapLocation, account: BindAccount, *, client_strategy: str | None = None
) -> Any:
    """An unopened ldap3 connection: read-only, certificate-checked, referrals not followed.

    `client_strategy` exists for the library's own mock server, which is what the tests run
    against; production passes nothing and gets the synchronous socket strategy.
    """
    ldap3 = _ldap3()
    tls = None
    if location.tls is not TlsMode.PLAINTEXT_FOR_DEVELOPMENT:
        tls = ldap3.Tls(
            validate=ssl.CERT_REQUIRED,
            version=ssl.PROTOCOL_TLS_CLIENT,
            ca_certs_file=location.ca_file or None,
            ssl_options=[ssl.OP_NO_SSLv2, ssl.OP_NO_SSLv3, ssl.OP_NO_TLSv1, ssl.OP_NO_TLSv1_1],
        )
    server = ldap3.Server(
        location.host,
        port=location.port,
        use_ssl=location.tls is TlsMode.LDAPS,
        tls=tls,
        get_info=ldap3.NONE,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
    )
    return ldap3.Connection(
        server,
        user=account.name,
        password=account.password,
        authentication=ldap3.SIMPLE,
        client_strategy=client_strategy or ldap3.SYNC,
        read_only=True,
        raise_exceptions=False,
        auto_referrals=False,
        receive_timeout=RECEIVE_TIMEOUT_SECONDS,
    )


class Ldap3Directory:
    """`DirectoryConnection` over an ldap3 connection that `begin` has protected and bound."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @classmethod
    def begin(cls, connection: Any, location: LdapLocation) -> Ldap3Directory:
        """Open, upgrade with StartTLS when the location says so, and bind, in that order.

        Every failure is a sentence naming the server and never the account or its password.
        """
        where = f"{location.host}:{location.port}"
        failure = _library_failure()
        try:
            connection.open()
            if location.tls is TlsMode.STARTTLS and not connection.start_tls():
                msg = (
                    f"{where} would not start TLS (StartTLS), so the service account was not "
                    "sent. Use ldaps:// on port 636, or enable StartTLS on the directory."
                )
                raise LdapUnreachableError(msg)
            if not connection.bind():
                result = connection.result or {}
                if result.get("result") == INVALID_CREDENTIALS:
                    msg = f"{where} refused the service account's name or password"
                    raise LdapBindRefusedError(msg)
                said = " ".join(str(result.get("description") or "no reason").split())[:200]
                msg = f"{where} did not accept the bind: {said}."
                raise LdapUnreachableError(msg)
        except failure as failed:
            connection.unbind()
            msg = (
                f"This server could not reach {where} over a verified TLS connection "
                f"({type(failed).__name__}). Check the address, the port and the certificate."
            )
            raise LdapUnreachableError(msg) from None
        except (LdapUnreachableError, LdapBindRefusedError):
            connection.unbind()
            raise
        return cls(connection)

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
        ldap3 = _ldap3()
        try:
            self._connection.search(
                base,
                query,
                search_scope=ldap3.SUBTREE if scope is SearchScope.SUBTREE else ldap3.LEVEL,
                attributes=list(attributes),
                paged_size=size,
                paged_cookie=cookie or None,
            )
        except _library_failure("LDAPInvalidFilterError"):
            msg = f"The directory could not read the filter {query!r}. Check its brackets."
            raise LdapLocationError(msg) from None
        except _library_failure() as failed:
            msg = f"The directory stopped answering mid-search ({type(failed).__name__})."
            raise LdapUnreachableError(msg) from None
        result = self._connection.result or {}
        entries: list[tuple[str | None, Mapping[str, Sequence[bytes | str]]]] = []
        for one in self._connection.response or ():
            if one.get("type") == "searchResRef":
                entries.append((None, {"ref": list(one.get("uri") or ())}))
            elif one.get("type") == "searchResEntry":
                entries.append((str(one.get("dn") or ""), dict(one.get("raw_attributes") or {})))
        control = (result.get("controls") or {}).get(PAGED_RESULTS_CONTROL) or {}
        next_cookie = (control.get("value") or {}).get("cookie") or b""
        return SearchPage(
            entries=tuple(entries),
            result_code=int(result.get("result", -1)),
            cookie=bytes(next_cookie),
        )

    def close(self) -> None:
        self._connection.unbind()


def open_ldap3(location: LdapLocation, account: BindAccount) -> DirectoryConnection:
    """The real `Opener`: an ldap3 connection, protected and bound."""
    return Ldap3Directory.begin(ldap3_connection(location, account), location)


# ---------------------------------------------------------------------------- the walk
def _text(name: str, value: bytes | str) -> str | None:
    """One value as text: a GUID in Active Directory's braced form, anything else as UTF-8."""
    if isinstance(value, str):
        return value
    if name.casefold() == OBJECT_GUID and len(value) == 16:
        return "{" + str(uuid.UUID(bytes_le=value)) + "}"
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _as_text(attributes: Mapping[str, Sequence[bytes | str]]) -> dict[str, list[str]]:
    """Every attribute's values as text, dropping a value that is not text rather than guessing."""
    found: dict[str, list[str]] = {}
    for name, values in attributes.items():
        found[name] = [one for one in (_text(name, value) for value in values) if one is not None]
    return found


@dataclass(frozen=True)
class _Walked:
    entries: tuple[tuple[str | None, Mapping[str, Sequence[bytes | str]]], ...]
    result_code: int
    more_pages: bool


def _walk(
    connection: DirectoryConnection,
    location: LdapLocation,
    query: str,
    attributes: Sequence[str],
    *,
    page_size: int,
    max_pages: int,
) -> _Walked:
    """Every page of one search, stopping at a result that is not success or at `max_pages`."""
    entries: list[tuple[str | None, Mapping[str, Sequence[bytes | str]]]] = []
    cookie = b""
    code = LDAP_SUCCESS
    for _ in range(max_pages):
        page = connection.search_page(
            base=location.base_dn,
            query=query,
            scope=location.scope,
            attributes=attributes,
            size=page_size,
            cookie=cookie,
        )
        entries.extend(page.entries)
        code, cookie = page.result_code, page.cookie
        if code != LDAP_SUCCESS or not cookie:
            break
    return _Walked(tuple(entries), code, more_pages=bool(cookie) and code == LDAP_SUCCESS)


def read_directory(
    location_text: str,
    credential: str,
    *,
    opener: Opener | None = None,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
) -> LdapSource:
    """Bind, read the people (and the groups when a group filter is set), and hand over a source.

    Read-only, and the connection is closed whatever happens. A group read that did not finish
    marks the roster incomplete, because a membership dropped for want of its group is a role
    removed for want of a page.
    """
    location = parse_location(location_text)
    account = bind_account(credential)
    if location.tls is TlsMode.PLAINTEXT_FOR_DEVELOPMENT:
        log.warning(
            "ldap_plaintext_bind",
            server=f"{location.host}:{location.port}",
            reason=PLAIN_LDAP_EXPOSES_THE_BIND,
        )
    connection = (opener or open_ldap3)(location, account)
    try:
        allowed: frozenset[str] | None = None
        groups_unfinished = False
        if location.group_filter:
            groups = _walk(
                connection,
                location,
                location.group_filter,
                (NO_ATTRIBUTES,),
                page_size=page_size,
                max_pages=max_pages,
            )
            allowed = frozenset(name.casefold() for name, _ in groups.entries if name)
            groups_unfinished = groups.more_pages or groups.result_code != LDAP_SUCCESS
        people = _walk(
            connection,
            location,
            location.user_filter,
            PERSON_ATTRIBUTES,
            page_size=page_size,
            max_pages=max_pages,
        )
    finally:
        connection.close()

    entries: list[tuple[str | None, Mapping[str, Sequence[str]]]] = []
    for name, attributes in people.entries:
        text = _as_text(attributes)
        if allowed is not None:
            for held in [one for one in text if one.casefold() == "memberof"]:
                text[held] = [group for group in text[held] if group.casefold() in allowed]
        entries.append((name, text))
    return LdapSource(
        entries=tuple(entries),
        result_code=people.result_code,
        more_pages=people.more_pages or groups_unfinished,
    )


# ---------------------------------------------------------------------------- the trial
@dataclass(frozen=True)
class LdapTrial:
    """What one page read back: enough to see the settings work, and nothing written."""

    tls: TlsMode
    people: int
    active: int
    with_stable_identifier: int
    more_than_one_page: bool
    dropped: tuple[str, ...]
    warning: str = ""


def trial(location_text: str, credential: str, *, opener: Opener | None = None) -> LdapTrial:
    """Bind and read one page, read-only, and say what came back. Writes nothing anywhere."""
    location = parse_location(location_text)
    source = read_directory(
        location_text, credential, opener=opener, page_size=TRIAL_PAGE_SIZE, max_pages=1
    )
    reading = source.reading()
    people = reading.roster.people
    return LdapTrial(
        tls=location.tls,
        people=len(people),
        active=sum(1 for one in people if one.active),
        with_stable_identifier=len(reading.stable_ids),
        more_than_one_page=not reading.roster.complete,
        dropped=reading.dropped,
        warning=(
            PLAIN_LDAP_EXPOSES_THE_BIND if location.tls is TlsMode.PLAINTEXT_FOR_DEVELOPMENT else ""
        ),
    )


# --------------------------------------------------------------- what the connect flow shows
@dataclass(frozen=True)
class ConnectField:
    """One question the Staff sources connect flow asks for this source."""

    name: str
    label: str
    hint: str
    required: bool = True
    #: True for a value that goes to the vault and is never shown again.
    secret: bool = False
    default: str = ""


@dataclass(frozen=True)
class SourceSetup:
    """What a person needs to connect one kind of staff source, in the screen's own words."""

    source: str
    label: str
    fields: tuple[ConnectField, ...]
    steps: tuple[str, ...]
    #: Every attribute read about each person, so an administrator can review the request.
    reads: tuple[str, ...]


LDAP_SETUP: Final = SourceSetup(
    source=LDAP,
    label="LDAP or Active Directory",
    fields=(
        ConnectField(
            "host",
            "Directory server",
            "The domain controller's or directory server's name, for example dc1.example.com.",
        ),
        ConnectField(
            "tls",
            "Connection security",
            "ldaps (port 636, recommended) or starttls (port 389, upgraded before the bind).",
            default=TlsMode.LDAPS.value,
        ),
        ConnectField(
            "port",
            "Port",
            "Leave empty for 636 with ldaps or 389 with starttls.",
            required=False,
        ),
        ConnectField(
            "base_dn",
            "Base DN",
            "Where the search for people starts, for example DC=example,DC=com or "
            "OU=Staff,DC=example,DC=com.",
        ),
        ConnectField(
            "user_filter",
            "People filter",
            "Which entries are people. Leave empty for everything that is a person and not a "
            "computer; for Active Directory (&(objectCategory=person)(objectClass=user)) also "
            "works.",
            required=False,
            default=DEFAULT_USER_FILTER,
        ),
        ConnectField(
            "group_filter",
            "Group filter",
            "Optional: only groups this matches are read as memberships, for example "
            "(&(objectClass=group)(cn=Brain-*)). Empty reads every group a person is in.",
            required=False,
        ),
        ConnectField(
            "ca_file",
            "Certificate authority file",
            "Optional: the path on this server to your internal CA certificate, when the "
            "directory's certificate is not signed by a public one.",
            required=False,
        ),
        ConnectField(
            "bind_name",
            "Service account",
            "The read-only account's distinguished name, or name@domain.",
            secret=True,
        ),
        ConnectField(
            "password",
            "Service account password",
            "Kept in the secrets vault and never shown again.",
            secret=True,
        ),
    ),
    steps=(
        "In Active Directory Users and Computers, create a user to read the directory with, for "
        "example svc-brain-read. Make it an ordinary Domain User: no administrative group, and "
        "no delegated right to reset passwords or change groups.",
        "Set a long password that does not expire, or put a reminder in to change it here.",
        "Choose the base DN: the domain (DC=example,DC=com) or the organisational unit your "
        "staff are in. Everything below it that the people filter matches is read.",
        "Make sure the domain controller answers LDAPS on port 636 with a certificate this "
        "server trusts. If it is signed by your own certificate authority, copy that CA "
        "certificate onto this server and give its path.",
        "Allow this server to reach the domain controller on port 636 (or 389 for StartTLS) "
        "through any firewall between them.",
        "Enter the values here and press Test. One page is read, nothing is written, and the "
        "result says how many people and how many enabled accounts came back.",
    ),
    reads=PERSON_ATTRIBUTES,
)

#: The connect flow's metadata per staff source type. LDAP is the one with no sign-in flow.
SETUP_BY_SOURCE: Final[Mapping[str, SourceSetup]] = {LDAP: LDAP_SETUP}


def location_and_credential(answers: Mapping[str, str]) -> tuple[str, str]:
    """The setting value and the vault value for the connect flow's answers, checked.

    The location goes to `INSTALL_STAFF_SOURCE_LOCATION` and the credential to the vault slot;
    the two never mix, which is `A_CREDENTIAL_IN_THE_LOCATION_IS_A_CREDENTIAL_IN_THE_DATABASE`.
    """

    def given(name: str) -> str:
        return str(answers.get(name) or "").strip()

    modes = {TlsMode.LDAPS.value: TlsMode.LDAPS, TlsMode.STARTTLS.value: TlsMode.STARTTLS}
    tls = modes.get(given("tls").lower() or TlsMode.LDAPS.value)
    if tls is None:
        raise LdapLocationError("Connection security has to be ldaps or starttls.")
    port_text = given("port")
    if port_text and not port_text.isdigit():
        raise LdapLocationError("The port has to be a number, like 636.")
    if not given("host"):
        raise LdapLocationError("Enter the directory server's name.")
    location = location_for(
        given("host"),
        given("base_dn"),
        port=int(port_text) if port_text else None,
        tls=tls,
        user_filter=given("user_filter"),
        group_filter=given("group_filter"),
        ca_file=given("ca_file"),
    )
    password = str(answers.get("password") or "")
    credential = f"{given('bind_name')}{CREDENTIAL_SEPARATOR}{password}"
    bind_account(credential)
    return location, credential
