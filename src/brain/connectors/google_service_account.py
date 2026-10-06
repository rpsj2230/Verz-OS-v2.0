"""Reading Google Workspace with nobody signed in: a service account, its key, and one signature.

`brain.ops.staff_sync_run` said Google Workspace "needs a service account with domain-wide
delegation, which this product cannot sign for", and `brain.console.staff_source_guide` held it
back for the same reason. Signing is one RS256 signature over a short JSON claim set, and the
`cryptography` package the product already verifies Keycloak's tokens with makes it; what was
missing was this module. It turns the key file a company downloads into what the vault keeps,
turns what the vault keeps back into a key, and builds the one request that exchanges a signed
assertion for an access token. It opens no socket: the request is an `Outbound`, as every other
directory request is.

**Domain-wide delegation, narrowed to two read-only scopes, acting as one administrator.** The
service account asks for `admin.directory.user.readonly` and `admin.directory.group.readonly` and
nothing else, as the administrator named on the connect form, because the Directory API answers
only an administrator. The company grants exactly those two scopes to the service account's
client ID in the Admin console, and Google refuses a token for any scope not granted there, so the
account cannot read mail or files whatever this module asked. See `DELEGATION_IS_NARROWED_BY_SCOPE`.
The Google Drive connector's steps (`docs/install/integrations.md`) refuse delegation, because no
scope narrows Drive to one folder; for the directory, the scopes are the narrowing.

**The vault keeps the key's two primes, not the file.** A key file is some 2,300 characters of
JSON with spaces in it, and the vault's ceiling on one credential is
`brain.ops.credentials.MAX_CREDENTIAL_CHARS`, one unbroken run of printable characters. The two
primes are the whole private key (the modulus and every exponent follow from them and Google's
fixed public exponent), and written in base64 beside the two addresses they came to 395
characters for a 2,048-bit key and 737 for a 4,096-bit one, measured on 2026-09-28. So the
connect form takes the file as it is pasted, this module keeps
`<administrator>:<service account>:<p>.<q>`, and the rest of the file is dropped. See
`THE_VAULT_KEEPS_THE_KEY_AND_NOTHING_ELSE_IN_THE_FILE`.

**Every address is this module's own.** The key file names a `token_uri` and it is never read: an
address a pasted file chose is an address a signed assertion would be sent to. See
`A_KEY_FILE_DOES_NOT_CHOOSE_WHERE_ITS_SIGNATURE_GOES`.

Rejected: raising the vault's ceiling for this one slot. `MAX_CREDENTIAL_CHARS` is held equal to
the setup wizard's ceiling on a pasted key by a test, and a second, larger ceiling for one source
is a second rule for what the vault may hold. Rejected: `google-auth`, which signs the same claim
set and adds a dependency, its transitive dependencies and a release schedule for about forty
lines. Rejected: a person's refresh token from the setup wizard's sign-in, which reads the
directory as that person and stops the night they leave or change their password.

Task ids: M1.6.5, M11.7.1
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from brain.connectors.staff_directories import (
    GOOGLE_EXCHANGE_URL,
    GOOGLE_READ_GROUPS_URL,
    GOOGLE_READ_USERS_URL,
    Outbound,
)

# ------------------------------------------------------------------ written-down reasons
#: Why domain-wide delegation is acceptable for the directory and not for Drive.
DELEGATION_IS_NARROWED_BY_SCOPE: Final = (
    "A service account with domain-wide delegation receives a token only for the scopes the "
    "company granted its client ID in the Admin console. Granted the two read-only directory "
    "scopes and nothing else, it can list people and groups and cannot read a message or a file, "
    "whatever it asks for. The scopes are the narrowing, which is why the steps name both."
)

#: Why the vault holds two primes rather than the key file.
THE_VAULT_KEEPS_THE_KEY_AND_NOTHING_ELSE_IN_THE_FILE: Final = (
    "The vault keeps one unbroken credential of at most MAX_CREDENTIAL_CHARS characters, and a "
    "key file is longer than that and has spaces in it. The two primes are the whole private "
    "key: the modulus and the exponents follow from them and Google's public exponent. So the "
    "file's key is kept as its primes beside the two addresses, and the project, the key id and "
    "the addresses the file suggests posting to are not kept at all."
)

#: Why the file's own token address is ignored.
A_KEY_FILE_DOES_NOT_CHOOSE_WHERE_ITS_SIGNATURE_GOES: Final = (
    "A key file carries a token_uri, and a pasted file is text somebody else may have written. "
    "An assertion signed with the company's key and sent to an address the file chose would be "
    "a credential handed to whoever wrote that address, so the exchange goes to Google's own "
    "token endpoint, a constant here, and the file's is never read."
)

# --------------------------------------------------------------------- the figures
#: What the two scopes are, in the order the claim set names them.
SCOPES: Final[tuple[str, ...]] = (GOOGLE_READ_USERS_URL, GOOGLE_READ_GROUPS_URL)

#: The grant type Google exchanges a signed assertion under.
JWT_BEARER: Final = "urn:ietf:params:oauth:grant-type:jwt-bearer"

#: How long a signed assertion may be exchanged for. Google allows an hour; it is exchanged at
#: once, so ten minutes leaves room for a clock a little behind Google's and no more.
ASSERTION_SECONDS: Final = 600

#: Google's own ceiling on an assertion's life, which `ASSERTION_SECONDS` must stay inside.
GOOGLE_MAXIMUM_ASSERTION_SECONDS: Final = 3600

#: Google's service account keys use this public exponent, and the kept primes rely on it.
PUBLIC_EXPONENT: Final = 65537

#: The smallest key accepted. Google issues 2,048-bit keys and refuses to sign with less.
MIN_KEY_BITS: Final = 2048

#: The longest key file the connect form takes. A 4,096-bit key's file is under half of it.
MAX_KEY_FILE_CHARS: Final = 8000

#: How a key file names itself, and the fields read from it. Nothing else in it is read.
KEY_FILE_TYPE: Final = "service_account"

#: Between the three parts of what the vault keeps, and between the two primes.
SEPARATOR: Final = ":"
PRIME_SEPARATOR: Final = "."

#: A work address, and a service account's address, which is always Google's own domain.
ADDRESS: Final = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
SERVICE_ACCOUNT: Final = re.compile(r"^[a-z0-9][a-z0-9._-]*@[a-z0-9.-]+\.gserviceaccount\.com$")
_PRIME_TEXT: Final = re.compile(r"^[A-Za-z0-9_-]{16,700}$")


class ServiceAccountKeyError(Exception):
    """The key file or the kept value is not a usable service account key. Words for a person."""


@dataclass(frozen=True)
class ServiceAccount:
    """Who signs, as whom, with what. The key is left out of the representation."""

    #: The Workspace administrator the service account acts as, which the Directory API needs.
    admin: str
    #: The service account's own address, which is the assertion's issuer.
    client_email: str
    key: rsa.RSAPrivateKey = field(repr=False)


def _encoded(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decoded(text: str) -> int:
    if not _PRIME_TEXT.match(text):
        raise ValueError("not a prime this module wrote")
    padded = text + "=" * (-len(text) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded), "big")


def _checked_admin(admin: str) -> str:
    given = admin.strip()
    if not ADDRESS.match(given):
        msg = "Enter the Workspace administrator's email address the service account acts as."
        raise ServiceAccountKeyError(msg)
    return given.casefold()


def key_of(key_file: str) -> tuple[str, rsa.RSAPrivateKey]:
    """The service account's address and private key out of a key file, or a refusal in words.

    Shared with `brain.connectors.google_token`, which reads a connected source's key file the same
    way and keeps nothing of it. The refusals never repeat the file, which holds the private key.
    """
    if len(key_file) > MAX_KEY_FILE_CHARS:
        msg = "That is longer than a service account key file. Paste the file's contents alone."
        raise ServiceAccountKeyError(msg)
    try:
        parsed: Any = json.loads(key_file)
    except ValueError:
        msg = "That is not a key file. Open the JSON file you downloaded and paste all of it."
        raise ServiceAccountKeyError(msg) from None
    if not isinstance(parsed, Mapping) or parsed.get("type") != KEY_FILE_TYPE:
        msg = "That is not a service account key file. Create a JSON key for the service account."
        raise ServiceAccountKeyError(msg)
    email = str(parsed.get("client_email") or "").strip().casefold()
    if not SERVICE_ACCOUNT.match(email):
        msg = "The key file names no service account address. Download a new JSON key."
        raise ServiceAccountKeyError(msg)
    try:
        key = serialization.load_pem_private_key(
            str(parsed.get("private_key") or "").encode("ascii"), password=None
        )
    except (ValueError, TypeError, UnicodeEncodeError):
        msg = "The key file's private key could not be read. Download a new JSON key."
        raise ServiceAccountKeyError(msg) from None
    if not isinstance(key, rsa.RSAPrivateKey):
        msg = "The key file's key is not an RSA key, which is what Google issues."
        raise ServiceAccountKeyError(msg)
    if key.private_numbers().public_numbers.e != PUBLIC_EXPONENT or key.key_size < MIN_KEY_BITS:
        msg = "The key file's key is not one Google issues. Download a new JSON key."
        raise ServiceAccountKeyError(msg)
    return email, key


def kept_value(admin: str, key_file: str) -> str:
    """What the vault keeps for this key file and administrator, or a refusal in words.

    See `THE_VAULT_KEEPS_THE_KEY_AND_NOTHING_ELSE_IN_THE_FILE`. The refusals never repeat the
    file, which holds the private key.
    """
    who = _checked_admin(admin)
    email, key = key_of(key_file)
    numbers = key.private_numbers()
    primes = PRIME_SEPARATOR.join((_encoded(numbers.p), _encoded(numbers.q)))
    return SEPARATOR.join((who, email, primes))


def service_account(kept: str) -> ServiceAccount:
    """The service account a kept value describes, or a refusal that repeats none of it."""
    parts = kept.strip().split(SEPARATOR)
    refused = ServiceAccountKeyError(
        "The kept Google Workspace credential is not in the form this version keeps. Connect "
        "Google Workspace again on the Staff sources screen."
    )
    if len(parts) != 3:
        raise refused
    admin, email, primes = parts
    if not ADDRESS.match(admin) or not SERVICE_ACCOUNT.match(email):
        raise refused
    halves = primes.split(PRIME_SEPARATOR)
    if len(halves) != 2:
        raise refused
    try:
        p, q = _decoded(halves[0]), _decoded(halves[1])
        if p < 3 or q < 3 or p == q:
            raise ValueError("not two distinct primes")
        d = pow(PUBLIC_EXPONENT, -1, (p - 1) * (q - 1))
        key = rsa.RSAPrivateNumbers(
            p=p,
            q=q,
            d=d,
            dmp1=rsa.rsa_crt_dmp1(d, p),
            dmq1=rsa.rsa_crt_dmq1(d, q),
            iqmp=rsa.rsa_crt_iqmp(p, q),
            public_numbers=rsa.RSAPublicNumbers(PUBLIC_EXPONENT, p * q),
        ).private_key()
    except (ValueError, binascii.Error):
        raise refused from None
    if key.key_size < MIN_KEY_BITS:
        raise refused
    return ServiceAccount(admin=admin, client_email=email, key=key)


def _segment(value: Mapping[str, Any] | bytes) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def signed_assertion(
    *,
    issuer: str,
    key: rsa.RSAPrivateKey,
    scopes: Sequence[str],
    now: int,
    subject: str | None,
) -> str:
    """One RS256-signed claim set for Google's token endpoint, as `subject` or as the issuer.

    `subject` is the person a delegated account acts as, which only the directory's reading
    names; a connected source's service account reads as itself and passes None, so the claim set
    carries no `sub` at all (`brain.connectors.google_token`). `now` is seconds since the epoch,
    handed in so a test is not a clock. The assertion lives `ASSERTION_SECONDS`.
    """
    header = {"alg": "RS256", "typ": "JWT"}
    claims: dict[str, str | int] = {
        "iss": issuer,
        "scope": " ".join(scopes),
        "aud": GOOGLE_EXCHANGE_URL,
        "iat": now,
        "exp": now + ASSERTION_SECONDS,
    }
    if subject is not None:
        claims["sub"] = subject
    signing_input = f"{_segment(header)}.{_segment(claims)}"
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_segment(signature)}"


def assertion(account: ServiceAccount, *, now: int, scopes: Sequence[str] = SCOPES) -> str:
    """The signed claim set Google exchanges for a token: RS256, as the administrator.

    `now` is seconds since the epoch, handed in so a test is not a clock. The assertion lives
    `ASSERTION_SECONDS`, well inside Google's hour.
    """
    return signed_assertion(
        issuer=account.client_email, key=account.key, scopes=scopes, now=now, subject=account.admin
    )


def token_request(account: ServiceAccount, *, now: int) -> Outbound:
    """The exchange of a signed assertion for an access token, to Google's own endpoint.

    See `A_KEY_FILE_DOES_NOT_CHOOSE_WHERE_ITS_SIGNATURE_GOES`: the address is a constant.
    """
    form = {"grant_type": JWT_BEARER, "assertion": assertion(account, now=now)}
    return Outbound("POST", GOOGLE_EXCHANGE_URL, form=form)
