"""A Keycloak in memory: the admin interface the staff sync calls, and a person's sign-in page.

Built from Keycloak 26's admin REST documentation for the six requests
`brain.connectors.sign_in_accounts` makes, and from its documented behaviour for the person's side:
an enabled user with an email may ask for a password reset from the sign-in page ("Forgot
password", the realm's `resetPasswordAllowed`), which sends them a link; setting a password through
that link leaves the user's other required actions in place, so a user made with `CONFIGURE_TOTP`
is made to set up the second factor at the next sign-in. Every request is kept, and every email the
realm sends is kept with the reason it was sent, so a test can hold the sync to sending none.

And the user profile: Keycloak 24 and later keep only the attributes a realm's user profile
declares and drop the rest from a create or an update without refusing it. `declared` is that list;
a stand-in made with none drops the sync's marks exactly as an undeclared realm would.

Nothing here has called a Keycloak. It is a model of one, written down where a test can use it.

Task ids: none
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from brain.connectors.sign_in_accounts import PROFILE_ATTRIBUTES
from brain.connectors.staff_directories import Answer, Outbound

TOKEN = "stand-in-accounts-token"
BASE = "http://keycloak.test"
REALM = "brain"
ISSUER = f"https://sign-in.example.test/realms/{REALM}"
SECRET = "accounts-client-secret-sentinel"


@dataclass
class User:
    id: str
    username: str
    email: str
    enabled: bool = True
    email_verified: bool = False
    first_name: str = ""
    last_name: str = ""
    required_actions: list[str] = field(default_factory=list)
    attributes: dict[str, list[str]] = field(default_factory=dict)
    password: str | None = None
    signed_out: int = 0

    def representation(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "enabled": self.enabled,
            "emailVerified": self.email_verified,
            "firstName": self.first_name,
            "lastName": self.last_name,
            "requiredActions": list(self.required_actions),
            "attributes": {k: list(v) for k, v in self.attributes.items()},
        }


@dataclass
class Sent:
    """One email the realm sent: to whom, and why."""

    to: str
    reason: str


@dataclass
class StandInKeycloak:
    users: dict[str, User] = field(default_factory=dict)
    sent: list[Sent] = field(default_factory=list)
    requests: list[Outbound] = field(default_factory=list)
    secret: str = SECRET
    #: The realm's email settings; with none, a reset asked for sends nothing and says so.
    smtp: bool = True
    reset_password_allowed: bool = True
    #: The custom attributes the realm's user profile declares. By default the three marks, as the
    #: release leaves a realm; empty is a realm nobody declared them in.
    declared: frozenset[str] = frozenset(name for name, _ in PROFILE_ATTRIBUTES)

    def apply_profile(self, profile: Mapping[str, Any]) -> None:
        """`PUT users/profile`, as `ops/keycloak/accounts-client.sh` sends it through kcadm."""
        self.declared = frozenset(
            str(one.get("name")) for one in profile.get("attributes") or () if one.get("name")
        )

    def _kept(self, attributes: Mapping[str, Any]) -> dict[str, list[str]]:
        """What Keycloak keeps of the attributes it was sent: only the declared ones."""
        return {k: list(v) for k, v in dict(attributes).items() if k in self.declared}

    # ------------------------------------------------------------------ the admin interface
    async def __call__(self, outbound: Outbound) -> Answer:
        self.requests.append(outbound)
        parts = urlsplit(outbound.url)
        path = parts.path
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        if path == f"/realms/{REALM}/protocol/openid-connect/token":
            form = dict(outbound.form or {})
            if (
                form.get("grant_type") == "client_credentials"
                and form.get("client_id") == "brain-accounts"
                and form.get("client_secret") == self.secret
            ):
                return Answer(200, {"access_token": TOKEN, "token_type": "Bearer"})
            return Answer(401, {"error": "unauthorized_client", "error_description": "bad secret"})
        if outbound.headers.get("Authorization") != f"Bearer {TOKEN}":
            return Answer(401, {"error": "HTTP 401 Unauthorized"})
        admin = f"/admin/realms/{REALM}/users"
        if path == admin and outbound.method == "GET":
            return Answer(200, {"items": self._listing(query)})
        if path == admin and outbound.method == "POST":
            return self._create(dict(outbound.json_body or {}))
        if path.startswith(admin + "/"):
            rest = unquote(path[len(admin) + 1 :])
            user_id, _, action = rest.partition("/")
            user = self.users.get(user_id)
            if user is None:
                return Answer(404, {"error": "User not found"})
            if action == "" and outbound.method == "GET":
                return Answer(200, user.representation())
            if action == "" and outbound.method == "PUT":
                self._update(user, dict(outbound.json_body or {}))
                return Answer(204, {})
            if action == "logout" and outbound.method == "POST":
                user.signed_out += 1
                return Answer(204, {})
            if action in ("execute-actions-email", "send-verify-email", "reset-password-email"):
                # Sends mail on an administrator's say-so: the path the sync may never take.
                self.sent.append(Sent(to=user.email, reason=action))
                return Answer(204, {})
        return Answer(404, {"error": f"no stand-in for {outbound.method} {path}"})

    def _listing(self, query: Mapping[str, str]) -> list[dict[str, Any]]:
        found = sorted(self.users.values(), key=lambda one: one.username)
        if "q" in query:
            key, _, value = query["q"].partition(":")
            found = [one for one in found if value in one.attributes.get(key, [])]
        if "email" in query:
            wanted = query["email"].casefold()
            exact = query.get("exact") == "true"
            found = [
                one
                for one in found
                if (one.email.casefold() == wanted if exact else wanted in one.email.casefold())
            ]
        first, most = int(query.get("first", "0")), int(query.get("max", "100"))
        return [one.representation() for one in found[first : first + most]]

    def _create(self, body: Mapping[str, Any]) -> Answer:
        email = str(body.get("email") or "").casefold()
        if any(
            one.email.casefold() == email or one.username == body.get("username")
            for one in self.users.values()
        ):
            return Answer(409, {"errorMessage": "User exists with same username"})
        if "credentials" in body:
            msg = "the stand-in refuses a user made with a credential: the sync must set none"
            raise AssertionError(msg)
        user = User(
            id=str(uuid.uuid4()),
            username=str(body.get("username") or email),
            email=email,
            enabled=bool(body.get("enabled", True)),
            email_verified=bool(body.get("emailVerified", False)),
            first_name=str(body.get("firstName") or ""),
            last_name=str(body.get("lastName") or ""),
            required_actions=list(body.get("requiredActions") or []),
            attributes=self._kept(body.get("attributes") or {}),
        )
        self.users[user.id] = user
        return Answer(201, {})

    def _update(self, user: User, body: Mapping[str, Any]) -> None:
        if "enabled" in body:
            user.enabled = bool(body["enabled"])
        if "attributes" in body:
            # Keycloak replaces the attributes a PUT names, wholesale, keeping only declared ones.
            user.attributes = self._kept(body["attributes"] or {})
        if "requiredActions" in body:
            user.required_actions = list(body["requiredActions"] or [])

    # ------------------------------------------------------------------ the person's side
    def forgot_password(self, email: str) -> bool:
        """The sign-in page's Forgot password, pressed by the person. True when a link went out."""
        if not self.reset_password_allowed:
            return False
        user = next((one for one in self.users.values() if one.email == email.casefold()), None)
        if user is None or not user.enabled or not self.smtp:
            return False
        self.sent.append(Sent(to=user.email, reason="reset-credentials"))
        return True

    def set_password_from_link(self, email: str, password: str) -> None:
        """Following the reset link sets the password and leaves every other required action."""
        user = next(one for one in self.users.values() if one.email == email.casefold())
        assert any(one.to == user.email and one.reason == "reset-credentials" for one in self.sent)
        user.password = password
        user.required_actions = [one for one in user.required_actions if one != "UPDATE_PASSWORD"]

    def sign_in(self, email: str, password: str) -> str:
        """What signing in comes to: `refused`, the next required action, or `signed_in`."""
        user = next((one for one in self.users.values() if one.email == email.casefold()), None)
        if user is None or not user.enabled or user.password is None or user.password != password:
            return "refused"
        if user.required_actions:
            return user.required_actions[0]
        return "signed_in"
