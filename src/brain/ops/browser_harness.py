"""The browser harness's people: the product's own realm, two people, credentials minted per run.

The harness (`e2e/`, run by `.github/workflows/browser.yml`) signs in to a furnished install in a
real browser, as an administrator with a second factor and as a reader with a password alone. It
needs people the identity provider knows, and this module is where they come from.

**The realm is the one every install imports.** `brain.ops.realm_import.importable_realm` addresses
`ops/keycloak/realm-export.json` to the job's own origin exactly as it addresses it to a client's,
so the harness signs in through the browser flow, the conditional one-time-code step and the `amr`
mapper an install runs. Rejected: a realm written for the harness, which would prove that a realm
the product never ships signs people in.

**The people are a fixture; their credentials never are.** `e2e/fixtures/people.json` names two
people at `example.test`, a domain reserved for exactly this, with fixed ids so the job can bind
them to principals before the browser starts. It holds no password and no one-time-code secret,
and `tests/unit/test_browser_harness.py` fails the day it does. `realm_with_people` adds both from
the environment of the job that minted them a moment before, so a credential exists only for the
life of one run on one runner. See `A_CREDENTIAL_IN_A_FIXTURE_IS_A_CREDENTIAL_IN_A_REPOSITORY`.

**Never the owner's realm or anybody's account.** Nothing here reads an install's settings beyond
the address the job gives it, and nothing reaches a server outside the job.

Task ids: M27.10.6
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from brain.ops.realm_import import importable_realm

#: Why the fixture holds no credential.
A_CREDENTIAL_IN_A_FIXTURE_IS_A_CREDENTIAL_IN_A_REPOSITORY: Final = (
    "A password or a one-time-code secret written into a fixture is in the repository's history "
    "for ever, and this repository is public. So the fixture names the people and the job mints "
    "their credentials per run, in its own environment, and hands them to the realm and to the "
    "browser and to nothing else."
)

#: The domain every person in the fixture is addressed at: reserved for documentation and tests
#: by RFC 2606, so no address in it can be anybody's.
TEST_DOMAIN: Final = "example.test"

#: The fixture's own key naming which credentials a person is given, removed before import.
KIND_KEY: Final = "x-credentials"

#: The two kinds of sign-in a person in the fixture is given.
WITH_A_SECOND_FACTOR: Final = "password and one-time code"
WITHOUT_A_SECOND_FACTOR: Final = "password only"

#: Each person's environment variables, by username: the password, and the code's secret.
PASSWORD_ENV: Final[Mapping[str, str]] = {
    "e2e-admin": "E2E_ADMIN_PASSWORD",
    "e2e-reader": "E2E_READER_PASSWORD",
}
CODE_SECRET_ENV: Final[Mapping[str, str]] = {"e2e-admin": "E2E_ADMIN_CODE_SECRET"}

#: The realm's one-time-code policy, which the credential must state as the realm does.
CODE_POLICY: Final = {
    "subType": "totp",
    "digits": 6,
    "counter": 0,
    "period": 30,
    "algorithm": "HmacSHA1",
}

#: Keys whose presence in the fixture would be a credential, whatever their value.
CREDENTIAL_KEYS: Final = frozenset(
    {"credentials", "password", "value", "secret", "secretData", "hashedSaltedValue", "salt"}
)


class HarnessError(Exception):
    """The fixture or the job's environment cannot make the people the harness signs in as."""


def credentials_for(person: Mapping[str, Any], env: Mapping[str, str]) -> list[dict[str, Any]]:
    """The credentials one person is given, from the job's environment, or a refusal."""
    username = str(person.get("username", ""))
    kind = person.get(KIND_KEY)
    password = env.get(PASSWORD_ENV.get(username, ""), "")
    if not password:
        msg = f"the job minted no password for {username!r}"
        raise HarnessError(msg)
    given: list[dict[str, Any]] = [{"type": "password", "value": password, "temporary": False}]
    if kind == WITH_A_SECOND_FACTOR:
        secret = env.get(CODE_SECRET_ENV.get(username, ""), "")
        if not secret:
            msg = f"the job minted no one-time-code secret for {username!r}"
            raise HarnessError(msg)
        given.append(
            {
                "type": "otp",
                "userLabel": "browser harness",
                "secretData": json.dumps({"value": secret}),
                "credentialData": json.dumps(CODE_POLICY),
            }
        )
    elif kind != WITHOUT_A_SECOND_FACTOR:
        msg = f"{username!r} names no credential kind the harness knows"
        raise HarnessError(msg)
    return given


def fixture_problems(people: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Everything wrong with the fixture: a credential in it, or an address outside its domain."""
    found: list[str] = []

    def walk(value: object, where: str) -> None:
        if isinstance(value, Mapping):
            for key, inner in value.items():
                if key in CREDENTIAL_KEYS:
                    found.append(f"{where}.{key} is a credential, which the job mints per run")
                walk(inner, f"{where}.{key}")
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                walk(inner, f"{where}[{index}]")

    for index, person in enumerate(people):
        where = f"people[{index}]"
        walk(person, where)
        email = str(person.get("email", ""))
        if not email.endswith(f"@{TEST_DOMAIN}"):
            found.append(f"{where}.email is not at {TEST_DOMAIN}")
        if person.get(KIND_KEY) not in (WITH_A_SECOND_FACTOR, WITHOUT_A_SECOND_FACTOR):
            found.append(f"{where} names no credential kind")
    return tuple(found)


def realm_with_people(fixture: Path, env: Mapping[str, str], *, source: Path) -> str:
    """The product's realm addressed by `env`, with the fixture's people and minted credentials."""
    people = json.loads(fixture.read_text(encoding="utf-8"))
    problems = fixture_problems(people)
    if problems:
        raise HarnessError("; ".join(problems))
    realm = json.loads(importable_realm(source, env))
    for person in people:
        given = {key: value for key, value in person.items() if key != KIND_KEY}
        given["credentials"] = credentials_for(person, env)
        # Nothing asked of them at sign-in but what their credentials answer: the realm's default
        # action asks a new account to set up a one-time code, which is a person's first sign-in
        # and not what the harness tests.
        given["requiredActions"] = []
        realm.setdefault("users", []).append(given)
    return json.dumps(realm, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    """`realm FIXTURE SOURCE`: print the realm to import, from this process's environment."""
    from brain.settings import process_environment

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3 or args[0] != "realm":
        print("usage: python -m brain.ops.browser_harness realm FIXTURE SOURCE", file=sys.stderr)
        return 64
    try:
        print(realm_with_people(Path(args[1]), process_environment(), source=Path(args[2])))
    except HarnessError as error:
        print(f"browser harness: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
