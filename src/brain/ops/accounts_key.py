"""The application's half of setting up the staff sync's accounts client on an install.

`ops/keycloak/accounts-client.sh` runs on the server, after every release is ready and from the
installer, and it is the only thing that holds both halves: it signs in to the install's own
Keycloak as the administrator Keycloak was started with, inside Keycloak's container, and it
reaches the application's container. This is everything it asks the application: whether the
vault already holds the credential, which realm the install signs in with, the client and the
user profile as the reviewed realm declares them, and to keep the client's secret.

**The secret is kept by the application and read by nobody here.** It arrives on standard input,
never as an argument (an argument is readable in `ps` by every user on the server), is judged by
`brain.ops.credentials.problems_with` and written through `Credentials.keep`, which records the
write in `ops.credential_write` like a key typed into the console. The application's own policy
may write `connector_keys/` and never read it; the worker reads it for one run through the
`connector-run` token. See `NOBODY_COPIES_THE_ACCOUNTS_CLIENT_S_CREDENTIAL`.

**The client comes from the reviewed realm and nowhere else.** `--client` prints the one entry
of `ops/keycloak/realm-export.json` with its comments removed by `brain.ops.realm_import`, so a
realm imported fresh and a realm the script adds the client to afterwards hold the same client.

Rejected: a secret generated here and written into the realm file for `--import-realm`. The file
is written to a volume the Keycloak container reads, so the secret would sit on disk for the life
of the install, and `--import-realm` never touches a realm that already exists, so every install
made before this release would still need a person to do something.

Rejected: the application signing in to Keycloak as an administrator itself. That would put the
sign-in service's master credential into the process that answers questions.

Task ids: M1.6.16
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from brain.connectors.sign_in_accounts import (
    CLIENT_ID,
    KEY_SLOT,
    SignInServiceError,
    declared_profile,
    realm_of,
)
from brain.install import InstallError, value_of
from brain.ops.credentials import (
    ConnectorKeySlot,
    CredentialProblemError,
    Credentials,
    CredentialsUnavailableError,
    connector_key_slot,
)
from brain.ops.realm_import import strip_comments

#: Why the release, and not a person, keeps the secret.
NOBODY_COPIES_THE_ACCOUNTS_CLIENT_S_CREDENTIAL: Final = (
    "Keycloak makes the accounts client's secret; the release reads it inside Keycloak's own "
    "container and hands it to the application on standard input, which keeps it in the vault "
    "and records the write. It is never an argument, a file or a line of output, and no person "
    "has to copy it anywhere on any install."
)

#: The slot, `connector_keys/sign_in_accounts`.
SLOT: Final[ConnectorKeySlot] = connector_key_slot(KEY_SLOT)

#: Who the write is recorded as. A release's step, not a person.
KEPT_BY: Final = "release.accounts-client"

#: The reviewed realm, beside the source in a checkout and at `/app/ops` in the image.
REALM_FILE: Final = Path(__file__).resolve().parents[3] / "ops" / "keycloak" / "realm-export.json"

FLAGS: Final = ("--held", "--realm", "--client", "--profile", "--keep")


class AccountsKeyError(Exception):
    """What the script is told when a question cannot be answered. Never carries the secret."""


def client_representation(realm_file: Path = REALM_FILE) -> dict[str, Any]:
    """The accounts client exactly as the reviewed realm declares it, comments removed."""
    realm = json.loads(realm_file.read_text(encoding="utf-8"))
    for one in realm.get("clients") or ():
        if isinstance(one, dict) and one.get("clientId") == CLIENT_ID:
            found = strip_comments(one)
            assert isinstance(found, dict)
            return found
    msg = f"the reviewed realm declares no {CLIENT_ID} client"
    raise AccountsKeyError(msg)


def realm_name(env: Mapping[str, str] | None = None) -> str:
    """The realm the install's issuer names, which is the one the worker will manage."""
    try:
        return realm_of(value_of("INSTALL_OIDC_ISSUER", env)).realm
    except (InstallError, SignInServiceError) as unset:
        raise AccountsKeyError(str(unset)) from unset


def credential_for(secret: str) -> str:
    """What is kept: `<client id>:<secret>`, the shape `sign_in_accounts.token` reads."""
    return f"{CLIENT_ID}:{secret.strip()}"


def held(credentials: Credentials) -> bool:
    """Whether the slot holds a credential. Reads the vault's metadata and never the secret."""
    try:
        return credentials.held(SLOT).held
    except CredentialsUnavailableError as unavailable:
        raise AccountsKeyError(f"the vault could not be asked: {unavailable}") from unavailable


async def keep(credentials: Credentials, secret: str, *, trace_id: str) -> None:
    """Keep the secret. Refused, the reason names the problem and never the value."""
    if not secret.strip():
        msg = "no secret arrived on standard input, so nothing was kept"
        raise AccountsKeyError(msg)
    try:
        await credentials.keep(SLOT, credential_for(secret), actor=KEPT_BY, trace_id=trace_id)
    except CredentialProblemError as refused:
        codes = ", ".join(one.code for one in refused.problems)
        raise AccountsKeyError(f"the secret was refused ({codes}), so nothing was kept") from None
    except CredentialsUnavailableError as unavailable:
        raise AccountsKeyError(f"the vault could not keep it: {unavailable}") from unavailable


def _credentials() -> tuple[Credentials, Any]:
    """This container's vault and database, as the console's own write uses them."""
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.template_key import vault_for
    from brain.session import make_app_engine, make_session_factory
    from brain.settings import Settings

    settings = Settings()
    try:
        vault = vault_for(settings.vault_address, settings.vault_token)
    except ValueError:
        vault = None
    engine = make_app_engine(settings.database_url)
    writes = StoredCredentialWrites(make_session_factory(engine))
    return Credentials(vault, writes=writes), engine


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.accounts_key <flag>`, in the application container.

    `--held` exits 0 when the slot holds a credential and prints nothing. `--realm` prints the
    realm name. `--client` prints the client as JSON. `--profile` reads the realm's user profile on
    standard input and prints it with the marks declared. `--keep` reads the secret on standard
    input and keeps it. A refusal is one line on standard error and exit 1.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in FLAGS:
        print(f"usage: python -m brain.ops.accounts_key {{{'|'.join(FLAGS)}}}", file=sys.stderr)
        return 2
    try:
        return _answer(args[0])
    except AccountsKeyError as refused:
        print(f"accounts client: {refused}", file=sys.stderr)
        return 1


def _answer(flag: str) -> int:
    if flag == "--realm":
        print(realm_name())
        return 0
    if flag == "--client":
        print(json.dumps(client_representation()))
        return 0
    if flag == "--profile":
        try:
            profile = json.loads(sys.stdin.read())
        except ValueError as unread:
            msg = "the realm's user profile did not arrive as JSON"
            raise AccountsKeyError(msg) from unread
        if not isinstance(profile, dict):
            msg = "the realm's user profile did not arrive as an object"
            raise AccountsKeyError(msg)
        print(json.dumps(declared_profile(profile)))
        return 0
    credentials, engine = _credentials()

    async def go() -> int:
        try:
            if flag == "--held":
                return 0 if held(credentials) else 1
            await keep(credentials, sys.stdin.read(), trace_id="release-accounts-client")
            print("accounts client: its credential is kept in the vault")
            return 0
        finally:
            await engine.dispose()

    return asyncio.run(go())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
