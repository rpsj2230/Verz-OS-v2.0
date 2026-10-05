"""The application's half of giving the sign-in service the mail relay saved on Notifications.

Forgot password is Keycloak's own reset email, and Keycloak sends it through the realm's
`smtpServer`, which nothing on an install set: needs-rupash 131 asked the owner to type the relay's
host, port, sender, user name and password into Keycloak's console a second time. The relay the
Notifications screen keeps is exactly those values, so the release gives it to the realm instead,
and the owner types it once.

**The release does the writing, because only the release may.** `ops/keycloak/accounts-client.sh`
already runs after every deploy and from the installer, and it already signs in to the install's
own Keycloak as the administrator Keycloak was started with, inside Keycloak's container. That is
the only credential on an install that may change a realm's settings, and it is used where it is
kept. The application never holds it, and the accounts client the staff sync signs in as may
manage users and nothing else (`brain.connectors.sign_in_accounts.
THE_CLIENT_MAY_MANAGE_USERS_AND_NOTHING_ELSE`), so nothing in the application could read or write
a realm's mail settings, and this module does not change that. See
`THE_RELEASE_GIVES_THE_SIGN_IN_SERVICE_THE_RELAY`.

**The password goes from the vault into a pipe and nowhere else.** `--server` prints the realm's
mail settings, password included, to standard output, which the script pipes straight into kcadm's
standard input inside Keycloak's container: never an argument, never a file, never a line of the
deploy's output. `--decide` and `--read-back` read what Keycloak shows, where the password is
masked, and never print one. See `THE_RELAY_S_KEY_GOES_THROUGH_A_PIPE_ONLY`.

**A second run with the same relay changes nothing, and a changed one is picked up.** Keycloak
masks the password it holds, so what the realm shows cannot say whether it is the vault's. What
was last given is therefore remembered as `brain.ops.mail.configuration_version`, the digest of
the relay's settings and of when its password was last written, which names no host, address or
password, together with the host the realm reported back. The realm is written again when its
visible settings differ from the relay's or the relay has changed since; otherwise not at all. See
`THE_REALM_IS_WRITTEN_ONLY_WHEN_THE_RELAY_CHANGED`.

**No relay, nothing touched.** An install whose relay is not saved, or whose password is not held,
leaves the realm's mail settings exactly as they are, including any a person typed into Keycloak
by hand. The leaf's second half, hiding Forgot password while no relay is set, is not done here:
the coordinator's instruction for this step was to leave such a realm alone.

**What the install check can read is what the release read back.** After writing, the script reads
the realm's settings again with the same administrator and hands them to `--read-back`, which
records the host only if every visible setting is the relay's. The install check compares that
host with the relay's; it cannot ask Keycloak itself, for the reason above.

Rejected: granting the accounts client `manage-realm`, or even `view-realm`, so the application
could write or read the realm itself. It would put the sign-in service's configuration within
reach of a nightly job, the exact thing that client's three roles were chosen to keep out.

Rejected: a fingerprint kept inside the realm's `smtpServer` beside Keycloak's own keys. It works
only while Keycloak keeps keys it does not know, and it would be one more value in the sign-in
service that nothing there reads.

Task ids: M40.7.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.mail import (
    MailPassword,
    MailPasswordUnavailableError,
    MailSettings,
    Security,
    configuration_version,
    last_saved,
    settings_from_rows,
    settings_rows,
)
from brain.ops.setting_store import put, read_namespace, values_under
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons

#: Why the release, and not the application, writes the realm's mail settings.
THE_RELEASE_GIVES_THE_SIGN_IN_SERVICE_THE_RELAY: Final = (
    "Only Keycloak's own administrator may change a realm's mail settings, and that credential "
    "lives in Keycloak's container, where the release's step uses it. The application prints what "
    "the realm should hold and records what the realm read back, and holds no credential that "
    "could read or write a realm."
)

#: Why the password is printed at all, and where it goes.
THE_RELAY_S_KEY_GOES_THROUGH_A_PIPE_ONLY: Final = (
    "The relay's password leaves the vault once per change, on standard output, into a pipe whose "
    "other end is kcadm's standard input inside Keycloak's container. It is never an argument, a "
    "file or a line of output, and nothing that reads the realm back is shown it."
)

#: Why a second run with the same relay changes nothing.
THE_REALM_IS_WRITTEN_ONLY_WHEN_THE_RELAY_CHANGED: Final = (
    "Keycloak masks the password it holds, so the release remembers a digest of the relay it last "
    "gave, naming no host or password, and writes the realm again only when that digest or a "
    "setting the realm shows differs from the relay's."
)

# ------------------------------------------------------------------ the shapes

#: The `ops.setting` namespace holding what was last given, and who wrote it.
MIRROR_NAMESPACE: Final = "sign_in_mail"
MIRRORED_BY: Final = "release.sign-in-mail"

#: The three things `--decide` can answer, each a word on standard output.
UNSET: Final = "unset"
SAME: Final = "same"
WRITE: Final = "write"

#: The keys of the realm's `smtpServer` this sets and compares. The password is set and never
#: compared: Keycloak shows it masked.
VISIBLE_KEYS: Final = ("host", "port", "from", "auth", "user", "starttls", "ssl")
PASSWORD_KEY: Final = "password"  # noqa: S105  a key name, not a password

FLAGS: Final = ("--decide", "--server", "--read-back")


class SignInMailError(Exception):
    """What the script is told when a question cannot be answered. Never carries the password."""


@dataclass(frozen=True)
class Relay:
    """The relay as the realm should hold it, and the digest that names this version of it."""

    settings: MailSettings
    version: str


@dataclass(frozen=True)
class Mirrored:
    """What the release last gave the realm: the relay's digest and the host the realm reported."""

    version: str
    host: str


def visible(settings: MailSettings) -> dict[str, str]:
    """The realm's `smtpServer` for this relay, every key but the password, as strings."""
    return {
        "host": settings.host,
        "port": str(settings.port),
        "from": settings.sender,
        "auth": "true",
        "user": settings.username,
        "starttls": "true" if settings.security is Security.STARTTLS else "false",
        "ssl": "true" if settings.security is Security.TLS else "false",
    }


def realm_mail(document: str) -> dict[str, str]:
    """The `smtpServer` a realm's JSON holds, as kcadm prints it, or empty when it holds none."""
    try:
        parsed = json.loads(document)
    except ValueError as unread:
        msg = "the realm's mail settings did not arrive as JSON"
        raise SignInMailError(msg) from unread
    if not isinstance(parsed, Mapping):
        msg = "the realm's mail settings did not arrive as an object"
        raise SignInMailError(msg)
    found = parsed.get("smtpServer") or {}
    if not isinstance(found, Mapping):
        msg = "the realm's smtpServer is not an object"
        raise SignInMailError(msg)
    return {str(key): str(value) for key, value in found.items()}


def matches(relay: MailSettings, realm: Mapping[str, str]) -> bool:
    """Whether every setting the realm shows is the relay's. The password is not among them."""
    wanted = visible(relay)
    return all(realm.get(key, "") == wanted[key] for key in VISIBLE_KEYS)


def decide(relay: Relay | None, realm: Mapping[str, str], mirrored: Mirrored | None) -> str:
    """`unset`, `same` or `write`. See `THE_REALM_IS_WRITTEN_ONLY_WHEN_THE_RELAY_CHANGED`."""
    if relay is None:
        return UNSET
    if (
        mirrored is not None
        and mirrored.version == relay.version
        and matches(relay.settings, realm)
    ):
        return SAME
    return WRITE


def server(relay: Relay, password: str) -> dict[str, dict[str, str]]:
    """What the realm is updated with. Printed only into the pipe; see the module docstring."""
    return {"smtpServer": {**visible(relay.settings), PASSWORD_KEY: password}}


# ------------------------------------------------------------------ the install's facts


async def relay_of(session: AsyncSession, password: MailPassword) -> Relay | None:
    """The relay saved on Notifications and its digest, or None when either half is missing."""
    rows = await settings_rows(session)
    settings = settings_from_rows(rows)
    saved = last_saved(rows)
    if settings is None or saved is None:
        return None
    try:
        held = await asyncio.to_thread(password.held)
    except MailPasswordUnavailableError as unavailable:
        msg = f"the vault could not say whether the relay's password is held ({unavailable.state})"
        raise SignInMailError(msg) from unavailable
    if not held.held:
        return None
    version = configuration_version(
        settings, saved_at=saved.updated_at, password_written_at=held.written_at
    )
    return Relay(settings=settings, version=version)


async def mirrored_of(session: AsyncSession) -> Mirrored | None:
    """What the release last gave the realm, or None when it never has."""
    rows = values_under(await read_namespace(session, MIRROR_NAMESPACE), MIRROR_NAMESPACE)
    version, host = rows.get("version"), rows.get("host")
    if version is None or host is None:
        return None
    if not isinstance(version.value, str) or not isinstance(host.value, str):
        return None
    return Mirrored(version=version.value, host=host.value)


async def record(session: AsyncSession, relay: Relay, realm: Mapping[str, str]) -> None:
    """Remember what the realm read back, in the caller's transaction, when it is the relay."""
    if not matches(relay.settings, realm):
        msg = "the sign-in service did not keep the relay's settings, so nothing is recorded"
        raise SignInMailError(msg)
    for name, value, description in (
        ("version", relay.version, "The relay last given to the sign-in service, as a digest."),
        ("host", realm["host"], "The relay host the sign-in service reported it sends through."),
    ):
        await put(
            session,
            f"{MIRROR_NAMESPACE}.{name}",
            value_type=SettingType.STRING,
            value=value,
            description=description,
            updated_by=MIRRORED_BY,
        )


# ------------------------------------------------------------------ the command


def _process() -> tuple[MailPassword, Any, Any]:
    """This container's vault and database, as the console's own relay screen uses them."""
    from brain.ops.template_key import vault_for
    from brain.session import make_app_engine, make_session_factory
    from brain.settings import Settings

    settings = Settings()
    try:
        vault = vault_for(settings.vault_address, settings.vault_token)
    except ValueError:
        vault = None
    engine = make_app_engine(settings.database_url)
    return MailPassword(vault), engine, make_session_factory(engine)


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.sign_in_mail <flag>`, in the application container.

    `--decide` reads the realm's JSON on standard input and prints `unset`, `same` or `write`.
    `--server` prints the realm's mail settings, password included, for the pipe into kcadm.
    `--read-back` reads the realm's JSON on standard input and records what it holds when it is the
    relay. A refusal is one line on standard error and exit 1; no line ever holds the password.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in FLAGS:
        print(f"usage: python -m brain.ops.sign_in_mail {{{'|'.join(FLAGS)}}}", file=sys.stderr)
        return 2
    try:
        realm = realm_mail(sys.stdin.read()) if args[0] != "--server" else {}
        return asyncio.run(_answer(args[0], realm))
    except SignInMailError as refused:
        print(f"sign-in mail: {refused}", file=sys.stderr)
        return 1


async def _answer(flag: str, realm: Mapping[str, str]) -> int:
    password, engine, sessions = _process()
    try:
        async with sessions() as session:
            relay = await relay_of(session, password)
            if flag == "--decide":
                print(decide(relay, realm, await mirrored_of(session)))
                return 0
            if relay is None:
                msg = "no relay with a password is saved on Notifications"
                raise SignInMailError(msg)
            if flag == "--read-back":
                await record(session, relay, realm)
                await session.commit()
                print(f"sign-in mail: the sign-in service sends through {realm['host']}")
                return 0
            try:
                value = await asyncio.to_thread(password.read)
            except MailPasswordUnavailableError as unavailable:
                msg = f"the vault did not lend the relay's password ({unavailable.state})"
                raise SignInMailError(msg) from unavailable
            if value is None:
                msg = "the vault holds no relay password"
                raise SignInMailError(msg)
            sys.stdout.write(json.dumps(server(relay, value)))
            sys.stdout.flush()
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
