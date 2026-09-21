"""Which directory Keycloak brokers sign-in to, as the identity provider entry the realm carries.

`INSTALL_BROKERED_DIRECTORY` was declared, written by the setup wizard and read by one sentence
about the install's privacy posture, and nothing put a directory into the realm. A company that
chose Google Workspace signed in with passwords held in the realm, whatever the setting said.
This module turns the setting into the entry Keycloak imports, or into the sentence saying why
it cannot, and `brain.ops.realm_import` is the one reader that hands it the values.

**A brokered directory is always restricted to the company's own tenant, and refused without
one.** Keycloak's Google broker with no hosted domain accepts any Google account, and its
Microsoft broker with no tenant, or with `common`, `organizations` or `consumers`, accepts any
Microsoft account. Such a realm creates an account for a stranger on first sign-in. Entitlements
are additive, so that account starts with no reach, but a person the company never listed now
holds a session and an identity here. The restriction is `INSTALL_STAFF_SOURCE_LOCATION`, the
primary domain or tenant the wizard already asks for, and only when the staff source is the
same directory: a location that describes a different directory restricts nothing. See
`A_BROKER_WITH_NO_TENANT_SIGNS_IN_STRANGERS`.

**The secret is never a setting and never in the realm file.** The entry carries a Keycloak
vault reference, and the secret is a file in Keycloak's vault directory that an operator writes
on the server. Rejected: an `INSTALL_` value holding it, which would put a credential in the
environment file, on the Settings screen's list of names, and in every backup of that file.

**Lark and LDAP are refused with a reason rather than approximated.** Keycloak ships no Lark
broker and Lark's sign-in is not standard OpenID Connect, so a generic entry would be a sign-in
that fails at the token exchange. LDAP is a user federation needing a bind account and search
base this product has no settings for yet. Either way people sign in with accounts held in the
realm, and the Settings screen says so rather than letting the value look applied.

Scope: pure. Values in, a representation out; nothing here reads a setting or opens a socket.

Task ids: M41.1.5
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

#: Why a broker is never emitted without the company's own domain or tenant.
A_BROKER_WITH_NO_TENANT_SIGNS_IN_STRANGERS: Final = (
    "A Google broker with no hosted domain, or a Microsoft broker with no tenant or a "
    "multi-tenant one, lets anybody holding an account with that vendor complete a sign-in and "
    "be given an account in this realm. Refusing leaves people signing in with the realm's own "
    "accounts, which is where every install starts."
)

#: The value meaning sign-in is not brokered.
NOT_BROKERED: Final = "none"

#: What a setting nobody has answered holds, as `brain.install` declares it.
UNSET: Final = "unset"

#: Each directory this release brokers, and the staff source whose location restricts it. Held to
#: `brain.setup_wizard.STAFF_SOURCE_BROKERS` by a test, so the two cannot pair differently.
BROKERED_BY: Final[Mapping[str, str]] = MappingProxyType(
    {"google": "google_workspace", "microsoft": "microsoft_entra"}
)

#: Directories the setting may name that this release does not broker, and why, in words.
NOT_BROKERED_BY_THIS_RELEASE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "lark": (
            "Keycloak has no Lark broker and Lark's sign-in is not standard OpenID Connect, so "
            "this release cannot broker it."
        ),
        "ldap": (
            "LDAP needs a bind account and a search base this release has no settings for, so "
            "it is not federated."
        ),
    }
)

#: Microsoft's tenant names that admit accounts from any tenant. See
#: `A_BROKER_WITH_NO_TENANT_SIGNS_IN_STRANGERS`.
MULTI_TENANT_NAMES: Final[frozenset[str]] = frozenset({"common", "organizations", "consumers"})

#: The key the broker's secret is read under in Keycloak's vault.
VAULT_KEY: Final = "brokered-directory-client-secret"

#: What the entry's secret is: a reference Keycloak resolves from its vault, never the secret.
VAULT_REFERENCE: Final = "${vault." + VAULT_KEY + "}"

#: A domain or tenant: letters, digits, dots and hyphens, which is all either can contain.
_TENANT: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")

#: The settings this module is handed, named in the sentences it returns.
DIRECTORY_SETTING: Final = "INSTALL_BROKERED_DIRECTORY"
CLIENT_SETTING: Final = "INSTALL_BROKERED_CLIENT_ID"
LOCATION_SETTING: Final = "INSTALL_STAFF_SOURCE_LOCATION"
SOURCE_SETTING: Final = "INSTALL_STAFF_SOURCE"


@dataclass(frozen=True)
class Brokering:
    """The identity provider entry for the realm, or why there is none.

    Both empty means sign-in is deliberately not brokered. `problem` set means somebody chose a
    directory and the realm will not broker to it, which the Settings screen reports.
    """

    provider: dict[str, Any] = field(default_factory=dict)
    problem: str = ""


def vault_file(realm: str) -> str:
    """The file name Keycloak's file vault reads the secret from, for this realm.

    Keycloak's default key resolver joins realm and key with one underscore and doubles any
    underscore inside either, so an operator is told the exact name rather than the rule.
    """
    return f"{realm.replace('_', '__')}_{VAULT_KEY.replace('_', '__')}"


def brokering(*, directory: str, client_id: str, staff_source: str, location: str) -> Brokering:
    """The broker this configuration asks for, restricted to the company's tenant, or a reason."""
    chosen = directory.strip().lower()
    if chosen in ("", NOT_BROKERED):
        return Brokering()
    if chosen in NOT_BROKERED_BY_THIS_RELEASE:
        return Brokering(
            problem=(
                f"{DIRECTORY_SETTING} is {chosen!r}. {NOT_BROKERED_BY_THIS_RELEASE[chosen]} "
                "People sign in with accounts held in the realm."
            )
        )
    if chosen not in BROKERED_BY:
        known = sorted({NOT_BROKERED, *BROKERED_BY, *NOT_BROKERED_BY_THIS_RELEASE})
        return Brokering(
            problem=f"{DIRECTORY_SETTING} is {chosen!r}, which is not one of {', '.join(known)}."
        )
    client = client_id.strip()
    if client in ("", UNSET):
        return Brokering(
            problem=(
                f"{DIRECTORY_SETTING} is {chosen!r} and {CLIENT_SETTING} is not set, so sign-in "
                "is not brokered. Register an application with that directory and set its "
                "client id."
            )
        )
    tenant = location.strip()
    if staff_source.strip() != BROKERED_BY[chosen] or tenant in ("", UNSET):
        return Brokering(
            problem=(
                f"{DIRECTORY_SETTING} is {chosen!r} and no {chosen} domain or tenant is set to "
                f"restrict it to: {SOURCE_SETTING} must be {BROKERED_BY[chosen]!r} with "
                f"{LOCATION_SETTING} naming yours. {A_BROKER_WITH_NO_TENANT_SIGNS_IN_STRANGERS}"
            )
        )
    if not _TENANT.match(tenant) or tenant.lower() in MULTI_TENANT_NAMES:
        return Brokering(
            problem=(
                f"{LOCATION_SETTING} is {tenant!r}, which is not one company's domain or tenant. "
                f"{A_BROKER_WITH_NO_TENANT_SIGNS_IN_STRANGERS}"
            )
        )
    restriction = {"hostedDomain": tenant} if chosen == "google" else {"tenantId": tenant}
    return Brokering(
        provider={
            "alias": chosen,
            "providerId": chosen,
            "enabled": True,
            "trustEmail": False,
            "storeToken": False,
            "linkOnly": False,
            "firstBrokerLoginFlowAlias": "first broker login",
            "config": {
                "clientId": client,
                "clientSecret": VAULT_REFERENCE,
                "defaultScope": "openid profile email",
                "syncMode": "IMPORT",
                **restriction,
            },
        }
    )
