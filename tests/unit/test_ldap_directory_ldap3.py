"""The LDAP reader over ldap3's own mock server: a real bind, real paging, a real read-only refusal.

`tests/unit/test_ldap_directory.py` holds the reader against stand-ins. This file runs the same
path through the library's `MOCK_SYNC` strategy, which parses the filter, checks the bind against
the entry's `userPassword` and pages with real cookies, so the ldap3 half is exercised rather than
assumed. ldap3 is a dependency since the owner allowed it on 2026-09-22 (needs-rupash item 93,
`ldap_directory.LDAP3_IS_LGPL_AND_ALLOWED_BY_NAME`), so this runs in CI; the skip is only for an
environment synced without it.

Task ids: M1.6.6
"""

from __future__ import annotations

import ssl
import uuid
from collections.abc import Sequence
from typing import Any

import pytest

from brain.connectors.ldap_directory import (
    DEFAULT_USER_FILTER,
    BindAccount,
    Ldap3Directory,
    LdapBindRefusedError,
    LdapLocation,
    LdapLocationError,
    TlsMode,
    ldap3_connection,
    location_for,
    parse_location,
    read_directory,
)

ldap3 = pytest.importorskip("ldap3")

BASE = "DC=example,DC=com"
LOCATION = f"ldaps://dc1.example.com/{BASE}"
BIND_NAME = f"CN=svc-brain-read,OU=Service,{BASE}"
PASSWORD = "sentinel-bind-password-7c1e"


def directory_entries() -> list[tuple[str, dict[str, Any]]]:
    """Seven people and the service account, as a domain controller would hold them."""
    found: list[tuple[str, dict[str, Any]]] = [
        (BIND_NAME, {"objectClass": ["person", "user"], "sn": "svc", "userPassword": PASSWORD}),
        (f"CN=Workstation,OU=Computers,{BASE}", {"objectClass": ["person", "user", "computer"]}),
        (f"CN=Approvers,OU=Groups,{BASE}", {"objectClass": ["group"], "cn": "Approvers"}),
        (f"CN=Legacy,OU=Groups,{BASE}", {"objectClass": ["group"], "cn": "Legacy"}),
    ]
    for at in range(7):
        found.append(
            (
                f"CN=Person {at},OU=Staff,{BASE}",
                {
                    "objectClass": ["top", "person", "organizationalPerson", "user"],
                    "sn": f"P{at}",
                    "mail": f"p{at}@example.com",
                    "displayName": f"Person {at}",
                    "department": "engineering",
                    "objectGUID": uuid.UUID(int=at + 1).bytes_le,
                    "userAccountControl": "514" if at == 3 else "512",
                    "memberOf": [f"CN=Approvers,OU=Groups,{BASE}", f"CN=Legacy,OU=Groups,{BASE}"],
                },
            )
        )
    return found


def mock_opener(entries: Sequence[tuple[str, dict[str, Any]]]) -> Any:
    """An `Opener` over the mock server, filled before the bind so the bind can be checked."""

    def opener(location: LdapLocation, account: BindAccount) -> Ldap3Directory:
        connection = ldap3_connection(location, account, client_strategy=ldap3.MOCK_SYNC)
        for name, attributes in entries:
            connection.strategy.add_entry(name, attributes)
        return Ldap3Directory.begin(connection, location)

    return opener


def test_the_connection_is_read_only_and_refuses_a_write_before_sending_it() -> None:
    """`A_DIRECTORY_ACCOUNT_THAT_CAN_WRITE_IS_NOT_ASKED_FOR`. ldap3's `read_only` refuses an add,
    a modify and a delete client-side. Delete this and an over-granted service account is one
    stray call from changing the company's directory."""
    account = BindAccount(BIND_NAME, PASSWORD)
    connection = ldap3_connection(
        parse_location(LOCATION), account, client_strategy=ldap3.MOCK_SYNC
    )
    for name, attributes in directory_entries():
        connection.strategy.add_entry(name, attributes)
    connection.bind()

    assert connection.read_only is True
    replace = {"sn": [(ldap3.MODIFY_REPLACE, ["changed"])]}
    with pytest.raises(ldap3.core.exceptions.LDAPConnectionIsReadOnlyError):
        connection.modify(f"CN=Person 1,OU=Staff,{BASE}", replace)
    with pytest.raises(ldap3.core.exceptions.LDAPConnectionIsReadOnlyError):
        connection.delete(f"CN=Person 1,OU=Staff,{BASE}")


def test_tls_checks_the_certificate_and_refuses_old_protocols() -> None:
    """Certificates are required and verified, TLS 1.0 and 1.1 are switched off, LDAPS wraps
    from the first byte, and a plaintext development location carries no TLS at all. Delete this
    and a directory impersonated on the network path is handed the service account."""
    account = BindAccount(BIND_NAME, PASSWORD)
    secure = ldap3_connection(parse_location(LOCATION), account).server
    upgraded = ldap3_connection(parse_location(f"ldap://dc1.example.com/{BASE}"), account).server
    plain_location = location_for("dc1.example.com", BASE, tls=TlsMode.PLAINTEXT_FOR_DEVELOPMENT)
    plain = ldap3_connection(parse_location(plain_location), account).server

    assert secure.ssl is True
    assert secure.tls.validate == ssl.CERT_REQUIRED
    assert {ssl.OP_NO_TLSv1, ssl.OP_NO_TLSv1_1} <= set(secure.tls.ssl_options)
    assert upgraded.ssl is False
    assert upgraded.tls.validate == ssl.CERT_REQUIRED
    assert plain.tls is None


def test_a_paged_read_over_the_mock_server_returns_every_person_and_no_computer() -> None:
    """Pages of three, followed by the library's own cookies, with the GUID read from bytes and
    the disabled account marked as left. Delete this and the ldap3 half of the reader is
    assumed rather than exercised."""
    source = read_directory(
        LOCATION,
        f"{BIND_NAME}:{PASSWORD}",
        opener=mock_opener(directory_entries()),
        page_size=3,
    )
    reading = source.reading()

    addresses = sorted(one.work_address for one in reading.roster.people)
    assert addresses == [f"p{at}@example.com" for at in range(7)]
    assert reading.roster.complete
    assert not next(
        one for one in reading.roster.people if one.work_address == "p3@example.com"
    ).active
    assert reading.stable_ids["p0@example.com"] == "{" + str(uuid.UUID(int=1)) + "}"
    assert not any("Workstation" in one for one in reading.dropped)


def test_a_group_filter_over_the_mock_server_narrows_memberships() -> None:
    """The group search runs as a second paged search and only its groups survive. Delete this
    and the group filter is tested only against a stand-in that never parsed it."""
    location = location_for("dc1.example.com", BASE, group_filter="(cn=Approvers)")

    reading = read_directory(
        location, f"{BIND_NAME}:{PASSWORD}", opener=mock_opener(directory_entries())
    ).reading()

    assert {one.groups for one in reading.roster.people} == {(f"CN=Approvers,OU=Groups,{BASE}",)}


def test_a_wrong_password_is_a_refused_bind_over_the_mock_server() -> None:
    """The library answers 49 for a wrong password and the reader calls it a refused credential.
    Delete this and the result code this reader keys on is an assumption about the library."""
    with pytest.raises(LdapBindRefusedError, match="refused the service account"):
        read_directory(LOCATION, f"{BIND_NAME}:wrong", opener=mock_opener(directory_entries()))


def test_a_filter_the_library_cannot_parse_is_a_misconfiguration() -> None:
    """A balanced but unreadable filter reaches the library, which refuses it, and the reader
    files that as the location's fault. Delete this and it is filed as an outage."""
    location = f"{LOCATION}???(&(objectClass=person)(mail))"

    with pytest.raises(LdapLocationError, match="could not read the filter"):
        read_directory(location, f"{BIND_NAME}:{PASSWORD}", opener=mock_opener(directory_entries()))
    assert DEFAULT_USER_FILTER.startswith("(")
