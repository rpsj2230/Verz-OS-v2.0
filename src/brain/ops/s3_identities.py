"""The object store's access file, edited one identity at a time and never rewritten whole.

`/opt/brain/settings/seaweedfs/s3.json` says who may reach the store's S3 gateway and what each
may do there. Two things on a server want a line in it: the application, which keeps uploaded
documents and exports there (`brain.ops.object_store`), and the trace ledger, which keeps its own
event bucket in the same store (`ops/deploy/overlays/langfuse.prepare.sh`). Until this module the
ledger's preparation wrote the file from nothing on every deploy with one identity, its own, so
**the day an install switched the ledger on, the application lost its key to the store at the next
restart**, and the file's one writer had no way to know there was a second person's line in it.

**So a writer adds or replaces its own identity by name and touches no other.** `merge` reads the
file as it is, replaces the identity of the same name or appends it, and hands back the whole file.
Every other identity, and every other key in the file, comes back as it went in. Two overlays that
each merge can therefore run in either order, any number of times, and the file holds both.

**A file that cannot be understood is refused, never replaced.** Invalid JSON, a document that is
not an object, an `identities` entry that is not a list of objects: each raises `S3IdentityError`
and the caller keeps the file it has. The alternative, treating what cannot be read as empty, is how
the ledger's preparation destroyed the application's line, and an access file somebody hand-edited
into something unreadable is exactly the one a writer must not quietly start over.

**One kind of identity is dropped on the way through: a placeholder.** The repository's own
`ops/seaweedfs/s3.json` carries a `brain-application` identity whose key is the literal text
`REPLACE_AT_DEPLOY_FROM_OPENBAO`, which the installer copies into place when no file exists. A
placeholder key in a running store is a key anybody who has read this repository holds, so an
identity whose every credential is the placeholder is removed whenever anything merges, and the
file the ledger's preparation used to write never carried one for the same reason.

**It runs inside the application, and the secrets go on standard input.** The host the step runs on
is not promised a JSON tool, but it is promised the application's container, which the step already
runs the planner in. The identity's name, key, secret and actions are the first line of standard
input, the existing file is the rest, and the new file is standard output: nothing secret is an
argument another process on the server could list, and nothing is written until the whole of it
succeeded, so a refusal leaves the old file exactly where it was. Rejected: `jq` or a Python on the
host, which is a dependency the server may not have; and a file per identity assembled by the
shell, which drops whatever an administrator wrote into the file by hand.

Task ids: M32.3.1.1, M32.3.1.4, M32.1.1.1
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

#: The text the repository's placeholder credential carries, as a key or as a secret.
PLACEHOLDER_CREDENTIAL: Final = "REPLACE_AT_DEPLOY_FROM_OPENBAO"

#: Why a file that cannot be read is refused and not started over.
A_FILE_THAT_CANNOT_BE_READ_IS_NEVER_REPLACED: Final = (
    "An access file that is not valid, or is not the shape the store reads, may be the only record "
    "of who holds a key to the store. Writing a new one over it would take every other identity's "
    "access away, which is what the trace ledger's preparation did to the application's key, so "
    "the writer says what is wrong and leaves the file as it is."
)

#: What an identity's name may be: the characters the store's own documentation uses.
NAME_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

#: What a key or a secret may be: no whitespace and no quote, so it cannot end the JSON string it
#: is written into or be read as two values. The product mints hexadecimal ones.
CREDENTIAL_PATTERN: Final = re.compile(r"^[A-Za-z0-9._~+/=-]{8,256}$")


class S3IdentityError(Exception):
    """An identity that cannot be written, or an access file that cannot be merged into."""


@dataclass(frozen=True)
class Identity:
    """One identity of the store: a name, one key pair and the actions it may take.

    The secret is held in a field `repr` does not render, for the reason
    `brain.ops.object_store.StoreCredential` holds its own so.
    """

    name: str
    access_key: str
    secret_key: str = field(repr=False)
    actions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not NAME_PATTERN.match(self.name):
            msg = "an identity's name is one word of letters, digits, dots, dashes and underscores"
            raise S3IdentityError(msg)
        for what, value in (("access key", self.access_key), ("secret key", self.secret_key)):
            if not CREDENTIAL_PATTERN.match(value):
                msg = (
                    f"the identity's {what} is empty, short, or holds a character a key never does"
                )
                raise S3IdentityError(msg)
        if not self.actions or any(not one or one != one.strip() for one in self.actions):
            msg = "an identity with no actions may do nothing, so it is not written"
            raise S3IdentityError(msg)

    def entry(self) -> dict[str, Any]:
        """The identity as the file holds it."""
        return {
            "name": self.name,
            "credentials": [{"accessKey": self.access_key, "secretKey": self.secret_key}],
            "actions": list(self.actions),
        }


def _is_placeholder(entry: dict[str, Any]) -> bool:
    """Whether an identity's every credential is the repository's placeholder."""
    credentials = entry.get("credentials")
    if not isinstance(credentials, list) or not credentials:
        return False
    return all(
        isinstance(one, dict)
        and PLACEHOLDER_CREDENTIAL in (one.get("accessKey"), one.get("secretKey"))
        for one in credentials
    )


def _document(existing: str) -> dict[str, Any]:
    """The file as a document, or a refusal. Nothing, or only whitespace, is an empty file."""
    if not existing.strip():
        return {"identities": []}
    try:
        document = json.loads(existing)
    except ValueError as error:
        kind = error.__class__.__name__
        msg = f"the store's access file is not valid JSON ({kind}), so it is not changed"
        raise S3IdentityError(msg) from error
    if not isinstance(document, dict):
        msg = "the store's access file is not a JSON object, so it is not changed"
        raise S3IdentityError(msg)
    identities = document.get("identities", [])
    if not isinstance(identities, list) or not all(isinstance(one, dict) for one in identities):
        msg = (
            "the store's access file has an identities entry that is not a list of "
            "identities, so it is not changed"
        )
        raise S3IdentityError(msg)
    return document


def merge(existing: str, identity: Identity) -> str:
    """The access file with `identity` added, or replaced where its name is already there.

    Every other identity and every other key comes back as it went in, in the same order; a
    placeholder identity is the one thing removed (see the module docstring). The result ends in a
    newline and is the whole of the new file.
    """
    document = _document(existing)
    kept: list[dict[str, Any]] = []
    placed = False
    for one in document.get("identities", []):
        if one.get("name") == identity.name:
            if not placed:
                kept.append(identity.entry())
                placed = True
            continue
        if _is_placeholder(one):
            continue
        kept.append(one)
    if not placed:
        kept.append(identity.entry())
    document["identities"] = kept
    return json.dumps(document, indent=2) + "\n"


def read_request(text: str) -> tuple[Identity, str]:
    """The identity on the first line of standard input, and the existing file that follows it."""
    head, _, rest = text.partition("\n")
    try:
        asked = json.loads(head)
    except ValueError as error:
        msg = "the first line of the request is not the identity, as one line of JSON"
        raise S3IdentityError(msg) from error
    if not isinstance(asked, dict) or not isinstance(asked.get("actions"), list):
        msg = "the request's identity is not an object with a list of actions"
        raise S3IdentityError(msg)
    fields = ("name", "access_key", "secret_key")
    if not all(isinstance(asked.get(one), str) for one in fields):
        msg = "the request's identity names no name, access key and secret key"
        raise S3IdentityError(msg)
    return (
        Identity(
            name=asked["name"],
            access_key=asked["access_key"],
            secret_key=asked["secret_key"],
            actions=tuple(str(one) for one in asked["actions"]),
        ),
        rest,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`merge`: identity and existing file on standard input, the new file on standard output.

    Exits 1 and prints one sentence to standard error, with nothing on standard output, when the
    request or the file cannot be used. The sentence never carries the key or the secret.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["merge"]:
        print(
            "usage: python -m brain.ops.s3_identities merge < identity-line-then-file",
            file=sys.stderr,
        )
        return 64
    try:
        identity, existing = read_request(sys.stdin.read())
        written = merge(existing, identity)
    except S3IdentityError as error:
        print(f"the store's access file was not changed: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
