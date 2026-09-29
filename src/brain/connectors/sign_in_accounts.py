"""The sign-in service's accounts, made, found, closed and opened, over its admin interface.

`brain.identity.staff_accounts` decides who has an account; this knows where Keycloak keeps them and
what to ask. It opens no socket: every request is an `Outbound` handed to a `Fetch` the caller owns,
`brain.connectors.staff_directories`' shape, so the calls are tested against a stand-in Keycloak.

**It asks as a service account that may manage users and nothing else.** The realm ships a
confidential client, `brain-accounts`, whose service account holds `realm-management`'s
`manage-users`, `view-users` and `query-users` and no other role: it cannot read the realm's
settings, change a client or grant anybody a role. Its secret is the vault's, written there by the
release and borrowed by the worker for one run. See `THE_CLIENT_MAY_MANAGE_USERS_AND_NOTHING_ELSE`.

**Nothing is ever sent from here.** The owner decided that nobody is sent a link. An account is made
with the work address, verified, no credential and `CONFIGURE_TOTP` required; the person presses
Forgot password on the sign-in page, which is Keycloak's own reset email sent because they asked,
and sets up the second factor when they first sign in. So no request this module builds may reach
`execute-actions-email`, `send-verify-email` or `reset-password-email`, and `SENDING_PATHS` is the
list a test holds every request to. See `NOTHING_HERE_SENDS_ANYTHING`.

**An account the sync made says so, in attributes.** `brain_staff_source`, `brain_staff_id` and
`brain_made_by_sync`, which is how a later run finds it by the source's identifier after an address
changes, and the only thing that lets the sync close an account without closing one a person made.

Rejected: keycloak's Python admin library. One more dependency with a release schedule, for six
requests, and a client that opens its own sockets cannot be tested the way this is.

Task ids: M1.6.16, M1.6.17
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote, urlencode

from brain.connectors.staff_directories import Answer, Fetch, Outbound
from brain.identity.staff_accounts import HeldAccount

# ------------------------------------------------------------------ written-down reasons
#: Why the client holds three roles.
THE_CLIENT_MAY_MANAGE_USERS_AND_NOTHING_ELSE: Final = (
    "The sync makes, finds, closes and opens accounts, which is manage-users, view-users and "
    "query-users of realm-management. A client that could also read the realm's settings or edit "
    "a client would put the sign-in service's configuration within reach of a nightly job."
)

#: Why no request here sends anything.
NOTHING_HERE_SENDS_ANYTHING: Final = (
    "The owner decided that nobody is sent a link: a person asks for their own with Forgot "
    "password. So no request this module builds reaches an admin endpoint that emails anybody."
)

#: The confidential client the sync signs in as. Declared in `ops/keycloak/realm-export.json`.
CLIENT_ID: Final = "brain-accounts"

#: The roles its service account holds, all of `realm-management`, and no others.
CLIENT_ROLES: Final[tuple[str, ...]] = ("manage-users", "query-users", "view-users")

#: The admin endpoints that send email, which no request from here may reach.
SENDING_PATHS: Final[tuple[str, ...]] = (
    "execute-actions-email",
    "send-verify-email",
    "reset-password-email",
)

#: What a new account must do at its first sign-in. The password is set before it, by the reset.
REQUIRED_ACTIONS: Final[tuple[str, ...]] = ("CONFIGURE_TOTP",)

#: The attributes an account the sync made or linked carries.
SOURCE_ATTRIBUTE: Final = "brain_staff_source"
STABLE_ID_ATTRIBUTE: Final = "brain_staff_id"
MADE_ATTRIBUTE: Final = "brain_made_by_sync"

#: Why the realm's user profile names the three attributes.
AN_UNDECLARED_ATTRIBUTE_IS_DROPPED_WITHOUT_A_WORD: Final = (
    "Keycloak 24 and later keep only the attributes a realm's user profile declares, and drop "
    "the rest from a create or an update without refusing it. The marks would vanish, every run "
    "would find the sync's accounts by address alone, and none would ever read as made by the "
    "sync, so no leaver's account would be closed. So the release declares them, editable by an "
    "administrator and invisible to the person."
)

#: The vault slot the accounts client's `<client id>:<secret>` is kept in, `connector_keys/<this>`.
KEY_SLOT: Final = "sign_in_accounts"

#: How many accounts one page of a listing asks for.
PAGE: Final = 100

#: How many pages a listing may read before it stops, which is a hundred thousand accounts.
MAX_PAGES: Final = 1000


class SignInServiceError(Exception):
    """The sign-in service refused or did not answer. The message is for the run's report."""


@dataclass(frozen=True)
class Realm:
    """Where the sign-in service is, as the worker reaches it, and which realm."""

    #: The base address, without `/realms/...`, e.g. `http://keycloak:8080`.
    base: str
    realm: str

    @property
    def admin(self) -> str:
        return f"{self.base.rstrip('/')}/admin/realms/{quote(self.realm, safe='')}"

    @property
    def token(self) -> str:
        return (
            f"{self.base.rstrip('/')}/realms/{quote(self.realm, safe='')}"
            "/protocol/openid-connect/token"
        )


def realm_of(issuer: str, internal: str = "") -> Realm:
    """The realm an issuer names, reached at `internal` where the worker has its own address.

    The issuer is `<base>/realms/<realm>`, which is how every Keycloak writes it; an issuer in any
    other shape names no realm this can manage.
    """
    head, marker, realm = issuer.rstrip("/").rpartition("/realms/")
    if not marker or not realm or "/" in realm:
        msg = "the sign-in issuer does not name a Keycloak realm, so no account can be managed"
        raise SignInServiceError(msg)
    return Realm(base=internal.rstrip("/") or head, realm=realm)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _refused(answer: Answer, what: str) -> SignInServiceError:
    said = answer.body.get("errorMessage") or answer.body.get("error_description") or ""
    words = " ".join(str(said).split())[:200]
    return SignInServiceError(
        f"The sign-in service refused {what} ({answer.status}){': ' + words if words else ''}."
    )


async def token(fetch: Fetch, realm: Realm, credential: str) -> str:
    """A token for the accounts client, from its identifier and secret kept as `<id>:<secret>`."""
    ident, separator, secret = credential.strip().partition(":")
    if not separator or not secret.strip():
        ident, secret = CLIENT_ID, credential.strip()
    if not secret:
        msg = "The kept credential for the sign-in service is empty."
        raise SignInServiceError(msg)
    answer = await fetch(
        Outbound(
            "POST",
            realm.token,
            form={
                "grant_type": "client_credentials",
                "client_id": ident.strip() or CLIENT_ID,
                "client_secret": secret.strip(),
            },
        )
    )
    found = answer.body.get("access_token")
    if answer.status != 200 or not isinstance(found, str) or not found:
        raise _refused(answer, "the accounts client's credential")
    return found


def _attribute(user: Mapping[str, Any], name: str) -> str:
    values = (user.get("attributes") or {}).get(name) or ()
    return str(values[0]) if isinstance(values, list) and values else ""


def held(user: Mapping[str, Any]) -> HeldAccount:
    """One Keycloak user representation as the plan reads an account."""
    return HeldAccount(
        account_id=str(user.get("id") or ""),
        email=str(user.get("email") or ""),
        enabled=bool(user.get("enabled", False)),
        source=_attribute(user, SOURCE_ATTRIBUTE),
        stable_id=_attribute(user, STABLE_ID_ATTRIBUTE),
        made_by_sync=_attribute(user, MADE_ATTRIBUTE) == "true",
    )


async def _users(fetch: Fetch, realm: Realm, bearer: str, query: Mapping[str, str]) -> list[Any]:
    found: list[Any] = []
    for page in range(MAX_PAGES):
        asked = {
            **query,
            "first": str(page * PAGE),
            "max": str(PAGE),
            "briefRepresentation": "false",
        }
        answer = await fetch(
            Outbound("GET", f"{realm.admin}/users?{urlencode(asked)}", _bearer(bearer))
        )
        if answer.status != 200:
            raise _refused(answer, "a listing of accounts")
        rows = answer.body.get("items")
        batch = rows if isinstance(rows, list) else []
        found.extend(batch)
        if len(batch) < PAGE:
            return found
    return found


async def accounts_of(
    fetch: Fetch, realm: Realm, bearer: str, *, source: str, emails: Sequence[str]
) -> tuple[HeldAccount, ...]:
    """Every account this source's sync made or linked, and every account these addresses have.

    One listing by the source's attribute, then one exact search per address the listing did not
    already hold, which finds an account somebody made by hand.
    """
    marked = await _users(fetch, realm, bearer, {"q": f"{SOURCE_ATTRIBUTE}:{source}"})
    found = {str(one.get("id")): held(one) for one in marked if isinstance(one, Mapping)}
    known = {one.email.casefold() for one in found.values()}
    for email in sorted({one.strip().casefold() for one in emails if one.strip()} - known):
        for one in await _users(fetch, realm, bearer, {"email": email, "exact": "true"}):
            if isinstance(one, Mapping) and str(one.get("email") or "").casefold() == email:
                found[str(one.get("id"))] = held(one)
    return tuple(found[key] for key in sorted(found))


def new_user(*, email: str, display_name: str, source: str, stable_id: str) -> Mapping[str, Any]:
    """The representation a new account is made from: no credential, the second factor required."""
    first, _, last = display_name.strip().partition(" ")
    return {
        "username": email.strip().casefold(),
        "email": email.strip().casefold(),
        # The address is the company directory's, so it is the person's by the company's word.
        "emailVerified": True,
        "enabled": True,
        "firstName": first or display_name.strip(),
        "lastName": last,
        "requiredActions": list(REQUIRED_ACTIONS),
        "attributes": {
            SOURCE_ATTRIBUTE: [source],
            STABLE_ID_ATTRIBUTE: [stable_id],
            MADE_ATTRIBUTE: ["true"],
        },
    }


async def make(
    fetch: Fetch, realm: Realm, bearer: str, representation: Mapping[str, Any]
) -> HeldAccount:
    """Make one account and read it back. An address taken since the listing is found instead."""
    answer = await fetch(
        Outbound("POST", f"{realm.admin}/users", _bearer(bearer), json_body=dict(representation))
    )
    if answer.status not in (201, 409):
        raise _refused(answer, "a new account")
    email = str(representation["email"])
    for one in await _users(fetch, realm, bearer, {"email": email, "exact": "true"}):
        if isinstance(one, Mapping) and str(one.get("email") or "").casefold() == email:
            return held(one)
    msg = "The sign-in service made an account and then did not list it."
    raise SignInServiceError(msg)


async def _update(
    fetch: Fetch, realm: Realm, bearer: str, account_id: str, changes: Mapping[str, Any], what: str
) -> None:
    url = f"{realm.admin}/users/{quote(account_id, safe='')}"
    current = await fetch(Outbound("GET", url, _bearer(bearer)))
    if current.status != 200:
        raise _refused(current, what)
    # Keycloak replaces what a PUT names, attributes included, so the account is read and sent back
    # whole with the change laid over it: a partial one would clear every attribute not named.
    body = {**current.body, **changes}
    answer = await fetch(Outbound("PUT", url, _bearer(bearer), json_body=body))
    if answer.status not in (200, 204):
        raise _refused(answer, what)


async def mark(
    fetch: Fetch, realm: Realm, bearer: str, account: HeldAccount, *, source: str, stable_id: str
) -> None:
    """Mark an account the sync linked with the source and identifier. Never as made by the sync."""
    url = f"{realm.admin}/users/{quote(account.account_id, safe='')}"
    current = await fetch(Outbound("GET", url, _bearer(bearer)))
    if current.status != 200:
        raise _refused(current, "an account to link")
    attributes = dict(current.body.get("attributes") or {})
    attributes[SOURCE_ATTRIBUTE] = [source]
    attributes[STABLE_ID_ATTRIBUTE] = [stable_id]
    answer = await fetch(
        Outbound("PUT", url, _bearer(bearer), json_body={**current.body, "attributes": attributes})
    )
    if answer.status not in (200, 204):
        raise _refused(answer, "an account to link")


async def close(fetch: Fetch, realm: Realm, bearer: str, account: HeldAccount) -> None:
    """Disable an account and end its sessions at the sign-in service."""
    await _update(
        fetch, realm, bearer, account.account_id, {"enabled": False}, "closing an account"
    )
    url = f"{realm.admin}/users/{quote(account.account_id, safe='')}/logout"
    answer = await fetch(Outbound("POST", url, _bearer(bearer)))
    if answer.status not in (200, 204):
        raise _refused(answer, "ending an account's sessions")


async def reopen(fetch: Fetch, realm: Realm, bearer: str, account: HeldAccount) -> None:
    """Enable an account the sync closed, for somebody the source lists as active again."""
    await _update(fetch, realm, bearer, account.account_id, {"enabled": True}, "opening an account")


#: The three marks as the realm's user profile declares them: an administrator may read and edit
#: them, and the person never sees them on their own account page.
PROFILE_ATTRIBUTES: Final[tuple[tuple[str, str], ...]] = (
    (SOURCE_ATTRIBUTE, "Staff source"),
    (STABLE_ID_ATTRIBUTE, "Staff source identifier"),
    (MADE_ATTRIBUTE, "Made by the staff sync"),
)


def declared_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """The realm's user profile with the three marks declared, and nothing else changed.

    Read from and written back to `users/profile` by `ops/keycloak/accounts-client.sh`. An attribute
    already declared is left exactly as an administrator may have set it; see
    `AN_UNDECLARED_ATTRIBUTE_IS_DROPPED_WITHOUT_A_WORD`.
    """
    attributes = [one for one in profile.get("attributes") or () if isinstance(one, Mapping)]
    names = {str(one.get("name")) for one in attributes}
    added = [
        {
            "name": name,
            "displayName": label,
            "permissions": {"view": ["admin"], "edit": ["admin"]},
            "multivalued": False,
        }
        for name, label in PROFILE_ATTRIBUTES
        if name not in names
    ]
    return {**profile, "attributes": [*(dict(one) for one in attributes), *added]}
