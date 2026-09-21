"""Checking a Keycloak token's signature for real, and fetching the keys to check it with.

`brain.identity.oidc` decides everything about a token except whether its signature is
genuine, and `brain.identity.bearer.TokenAuthority` holds the pieces together, with the
signature check injected because no library that can verify RS256 was a dependency. So no
deployed process could accept any token at all, which was correct and was also the reason
`app.state.gate` is None. This module is the missing half: a `SignatureVerifier` backed by a
reviewed library, a `JwksFetch` that reads the realm's published keys, and one function that
assembles a `TokenAuthority` from the installation's own issuer.

**The dependency is `cryptography` alone, and not PyJWT or joserfc.** Both are good libraries
and both would be a second opinion here. `oidc.validate_token` already decides the algorithm
allow-list, the `kid` lookup, the issuer, the audience, `azp`, `typ`, expiry, not-before and
issue time, in one order, and `bearer` records why there is no second place to decide any of
them. PyJWT's `decode` and joserfc's claims registry each decide all of those again, with
their own defaults for leeway and audience, so importing either to use its signature step
alone leaves the whole second validator one import away for whoever next finds it more
convenient. It also buys nothing in capability: both call `cryptography` to verify RS256, so
the dependency closure is `cryptography` either way and the JWT library is surface on top.

**What is not written by hand is the cryptography.** The RSA operation, the PKCS#1 v1.5
padding check and the hash are one call into `cryptography`, which is OpenSSL underneath.
What is written here is the choice of that padding and hash for RS256, and turning a JWK's
`n` and `e` (two base64url integers) into a public key through `RSAPublicNumbers`, which
validates the exponent itself. Rejected: `rsa` (python-rsa), which is pure Python and would
avoid a compiled dependency, and whose project has stopped being maintained, which is the
exact failure `sweep_dependencies` was written after.

`cryptography` is Apache-2.0 OR BSD-3-Clause. Its own dependency `cffi` is MIT-0, which is
MIT without the attribution condition; see the entry for it beside `ALLOWED_LICENCES`.

**One algorithm, because the realm signs with one.** `ops/keycloak/realm-export.json` sets
`defaultSignatureAlgorithm` to RS256 and pins every client to it, and `oidc.ALLOWED_ALGORITHMS`
is wider (PS and ES too) because it is a statement about what is safe rather than about what
this realm mints. `VERIFIED_ALGORITHMS` is the narrower statement about what this verifier
can actually check, and it is applied twice: a published key for anything else is dropped
when the key set is read, and the verifier refuses a key whose algorithm is not on it
whatever the key set said. `HS256` is on neither list, so the confusion attack that presents
the published public key as an HMAC secret is refused by `oidc` before this module is asked,
and would be refused here if it were.

**The key set is fetched from the issuer and from nowhere else.** The URL is derived from
`INSTALL_OIDC_ISSUER`, which is the one reader of the issuer (`brain.install.value_of`), and
it is not a setting of its own. See `THE_KEYS_COME_FROM_THE_ISSUER_AND_NOWHERE_ELSE`. The
transport is https, or plain http to a loopback address for a Keycloak on a development
machine, a redirect is never followed, and the body is capped.

**A key this process cannot use is dropped rather than refusing the set.** Keycloak's default
realm publishes an RSA-OAEP encryption key in the same document as its signing key, so a
reader that refused a document over one unusable entry would refuse every sign-in on a
correctly configured realm. A dropped key cannot be named by a token: its `kid` is absent from
the set, so a token naming it is refused as an unknown key. A document with no usable key at
all is refused, because a set of nothing accepts nothing and says so only as a stream of
unknown-key refusals.

**Rotation and the refetch storm are `oidc.JwksCache`'s, unchanged.** An unrecognised `kid`
refetches once, and not again for `oidc.JWKS_MIN_REFETCH`, so a stream of tokens with random
key ids costs the identity provider one request per window rather than one per token. This
module supplies the fetch it calls and nothing about when it is called.

**Every refusal is `TokenRefusedError`, so the presenter hears one sentence.** The reason is
in the log and never in the response; see `bearer.EVERY_REFUSAL_SAYS_THE_SAME_SENTENCE`.
Faults inside this module (a document that is not a key set, a transport error) raise
`IdentityError`, which `JwksCache` turns into `NO_KEYS_AVAILABLE` or `UNKNOWN_KEY`.

**The fetch is synchronous and never runs on the event loop.** `JwksFetch` and `KeySource` are
synchronous, and `TokenAuthority.authenticate`, a coroutine since `brain.api_routes.asking`
became one, asks its key source through `asyncio.to_thread`
(`bearer.A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP`), so a fetch holds a worker thread and not
every request in the process. `oidc.JwksCache` holds a lock across the fetch, so the sign-ins
that reach a cold cache together cost the realm one request
(`oidc.SIMULTANEOUS_FIRST_REQUESTS_FETCH_ONCE`). A fetch happens at most once an hour plus
once per refetch window, and priming the cache at startup moves the first one out of a request.

Not built here: constructing this in the application's lifespan. The `PrincipalDirectory` it
is handed is `brain.identity.principal_directory.StoredDirectory`.

Task ids: M1.1.2
"""

from __future__ import annotations

import base64
import ipaddress
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Final
from urllib.parse import urlsplit

import httpx
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from brain.identity.bearer import MembershipObserver, TokenAuthority
from brain.identity.oidc import JwksCache, KeySet, PrincipalDirectory, SigningKey
from brain.identity.roles import IdentityError
from brain.install import value_of

# ------------------------------------------------------------ written-down reasons

#: Why the key set's address is derived from the issuer rather than configured beside it.
THE_KEYS_COME_FROM_THE_ISSUER_AND_NOWHERE_ELSE: Final = (
    "The issuer and the address its keys are read from have to name the same realm, and two "
    "settings that must agree are one setting and a place to disagree. A key-set address "
    "pointing anywhere else is a process that accepts any token signed by whoever holds that "
    "host's keys, provided the token names the right issuer, which is a string anybody can "
    "type. Deriving the address makes that configuration unrepresentable. Rejected: the OIDC "
    "discovery document, which is one more fetch of a document whose jwks_uri would then be "
    "trusted, to support identity providers other than the Keycloak this product ships with."
)

#: Why a redirect from the key-set address is refused rather than followed.
A_REDIRECTED_KEY_SET_IS_A_SUBSTITUTED_KEY_SET: Final = (
    "The address is derived from the issuer so that the keys come from the issuer. Following "
    "a redirect hands that decision to whatever answered, which is the substitution the "
    "derivation exists to prevent, and a realm that has really moved has a new issuer too."
)

#: Why the verifier refuses short RSA keys even when a key set published one.
A_SHORT_KEY_IS_REFUSED_WHEREVER_IT_CAME_FROM: Final = (
    "An RSA key under 2048 bits is factorable by a determined party, and a signature under one "
    "proves only that somebody did the work. The check is in the verifier rather than in the "
    "key-set reader so that it holds for every key the verifier is ever handed, including one "
    "from a key source nobody has written yet."
)

# --------------------------------------------------------------------- the figures

#: The algorithms this verifier checks. The realm's `defaultSignatureAlgorithm`, and a subset
#: of `oidc.ALLOWED_ALGORITHMS`; both relations are held by tests against the realm file.
VERIFIED_ALGORITHMS: Final[frozenset[str]] = frozenset({"RS256"})

#: See `A_SHORT_KEY_IS_REFUSED_WHEREVER_IT_CAME_FROM`. Keycloak generates 2048-bit keys.
MINIMUM_RSA_BITS: Final = 2048

#: The audience every token this system accepts is minted for. The realm file is part of the
#: product and names this client on every install, so it is not a setting; a test holds it
#: to the audience mapper in `ops/keycloak/realm-export.json`.
API_AUDIENCE: Final = "brain-api"

#: Clock skew tolerated on `exp`, `nbf` and `iat`. Keycloak's access tokens live 300 seconds
#: in this realm, so thirty is a tenth of a token's life: enough for a VPS whose clock has
#: drifted, and small enough that an expired token is not quietly given a second life. Held
#: to that tenth, and to `oidc.MAX_LEEWAY`, by tests.
TOKEN_LEEWAY: Final = timedelta(seconds=30)

#: Where Keycloak publishes a realm's keys, relative to the realm's issuer.
CERTS_PATH: Final = "/protocol/openid-connect/certs"

#: The most a key-set document may be. Keycloak's is around three kilobytes with two keys; a
#: body larger than this is not a key set, and reading it whole first would let whatever
#: answered decide how much memory this process spends.
MAX_JWKS_BYTES: Final = 64 * 1024

#: How long one fetch may take. A request waiting on a key set is a person waiting to sign in.
JWKS_FETCH_TIMEOUT: Final = httpx.Timeout(5.0)


# ------------------------------------------------------------------ the verifier


@lru_cache(maxsize=16)
def _rsa_public_key(material: str) -> rsa.RSAPublicKey | None:
    """The RSA public key a PEM names, or None for anything else. Cached, because a key set
    holds one or two keys and parsing a PEM on every request is work repeated for nothing."""
    try:
        loaded = serialization.load_pem_public_key(material.encode("ascii"))
    except (ValueError, UnsupportedAlgorithm, UnicodeEncodeError):
        return None
    return loaded if isinstance(loaded, rsa.RSAPublicKey) else None


def verify_rs256(*, signing_input: bytes, signature: bytes, key: SigningKey) -> bool:
    """Whether `signature` is this key's RS256 signature over `signing_input`.

    An `oidc.SignatureVerifier`. It answers a yes or a no and never raises for a bad
    signature, because `validate_token` turns the no into `BAD_SIGNATURE` and a raise would
    arrive as a fault instead of a refusal.
    """
    if key.algorithm not in VERIFIED_ALGORITHMS:
        return False
    public = _rsa_public_key(key.material)
    if public is None:
        return False
    if public.key_size < MINIMUM_RSA_BITS:
        return False
    try:
        public.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return False
    return True


# --------------------------------------------------------------- reading key sets


def _b64url_integer(value: object) -> int | None:
    """A JWK integer member, or None when it is absent or not base64url."""
    if not isinstance(value, str) or not value:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        # `binascii.Error` is a ValueError, and so is a string with a non-ASCII character in
        # it. Characters outside the alphabet are discarded rather than refused by the
        # decoder, so a member of pure punctuation arrives as zero, which the library then
        # refuses as a key.
        return None
    return int.from_bytes(raw, "big")


def signing_key_from_jwk(jwk: Mapping[str, object]) -> SigningKey | None:
    """One published key as a `SigningKey`, or None when this verifier cannot use it.

    Every condition is a reason to drop the key rather than to guess. A JWK with no `use` is
    dropped rather than read as a signing key, and one with no `alg` rather than having an
    algorithm inferred from its type, because inferring either is choosing how a token is
    checked from what a document left out.
    """
    kid = jwk.get("kid")
    if not isinstance(kid, str):
        # For the type only. An absent or empty kid is refused by `SigningKey` itself
        # (`min_length=1`), and that ValueError is caught below, so this line decides nothing
        # the type would not; mutating it away is an equivalent mutation and is recorded so.
        return None
    if jwk.get("kty") != "RSA":
        return None
    if jwk.get("use") != "sig":
        return None
    algorithm = jwk.get("alg")
    if not isinstance(algorithm, str) or algorithm not in VERIFIED_ALGORITHMS:
        return None
    modulus = _b64url_integer(jwk.get("n"))
    exponent = _b64url_integer(jwk.get("e"))
    if modulus is None or exponent is None:
        return None
    try:
        # Validates the exponent and modulus itself, and raises ValueError on a key that is
        # not one. A kid longer than `SigningKey` allows is a ValueError too.
        public = rsa.RSAPublicNumbers(exponent, modulus).public_key()
        pem = public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii")
        return SigningKey(kid=kid, algorithm=algorithm, material=pem, use="sig")
    except ValueError:
        return None


def key_set_from_jwks(document: bytes, *, issuer: str, fetched_at: datetime) -> KeySet:
    """A published key-set document as a `KeySet` of the keys this verifier can use.

    Raises `IdentityError` for a document that is not a key set or holds no usable key, and
    `KeySet` itself raises for a `kid` published twice. `JwksCache` catches both.
    """
    try:
        parsed = json.loads(document)
    except ValueError as exc:
        msg = f"the key set for {issuer} is not JSON"
        raise IdentityError(msg) from exc
    entries = parsed.get("keys") if isinstance(parsed, dict) else None
    if not isinstance(entries, list):
        msg = f"the key set for {issuer} has no list of keys"
        raise IdentityError(msg)
    usable = [signing_key_from_jwk(entry) for entry in entries if isinstance(entry, dict)]
    keys = tuple(key for key in usable if key is not None)
    if not keys:
        msg = f"the key set for {issuer} publishes no key this process can verify with"
        raise IdentityError(msg)
    return KeySet(issuer=issuer, keys=keys, fetched_at=fetched_at)


# ------------------------------------------------------------------- fetching


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def jwks_url_for(issuer: str) -> str:
    """Where this issuer's keys are published. See `THE_KEYS_COME_FROM_THE_ISSUER_AND_NOWHERE_ELSE`.

    Raises `IdentityError` for an issuer the keys must not be read from: anything but https,
    except plain http to this machine, and an issuer ending in a slash. The last is refused
    rather than trimmed because `validate_token` compares the issuer exactly, and Keycloak's
    issuer has no trailing slash, so a configured one would refuse every token as coming from
    the wrong issuer while the key set loaded perfectly.
    """
    parts = urlsplit(issuer)
    host = parts.hostname or ""
    if not host:
        msg = f"issuer {issuer!r} names no host"
        raise IdentityError(msg)
    if issuer.endswith("/"):
        msg = f"issuer {issuer!r} ends in a slash, which no token Keycloak mints will match"
        raise IdentityError(msg)
    if parts.scheme != "https" and not (parts.scheme == "http" and _is_loopback(host)):
        msg = f"issuer {issuer!r} would have its keys read over an insecure transport"
        raise IdentityError(msg)
    return f"{issuer}{CERTS_PATH}"


def http_get(client: httpx.Client) -> Callable[[str], bytes]:
    """A body fetcher over a real HTTP client, for `KeycloakJwks` in a deployed process.

    Streamed so the size cap is applied while reading rather than after. The client is the
    caller's, so its lifetime is the lifespan's and a test hands one a mock transport.
    """

    def get(url: str) -> bytes:
        with client.stream(
            "GET", url, follow_redirects=False, timeout=JWKS_FETCH_TIMEOUT
        ) as response:
            if response.status_code != httpx.codes.OK:
                # A redirect lands here too. See A_REDIRECTED_KEY_SET_IS_A_SUBSTITUTED_KEY_SET.
                msg = f"{url} answered {response.status_code}"
                raise IdentityError(msg)
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_JWKS_BYTES:
                    msg = f"{url} answered with more than {MAX_JWKS_BYTES} bytes"
                    raise IdentityError(msg)
            return bytes(body)

    return get


class KeycloakJwks:
    """An `oidc.JwksFetch` for exactly one issuer: the one this installation trusts.

    It refuses to fetch for any other issuer rather than deriving an address for it. The only
    caller today passes its own issuer, and that is the point of refusing: a key source that
    would fetch keys for whatever issuer it was asked about is one wiring mistake from reading
    them from a host an unverified token named.
    """

    def __init__(
        self, issuer: str, *, get: Callable[[str], bytes], clock: Callable[[], datetime]
    ) -> None:
        self._issuer = issuer
        self._url = jwks_url_for(issuer)
        self._get = get
        self._clock = clock

    @property
    def url(self) -> str:
        return self._url

    def __call__(self, issuer: str) -> KeySet:
        if issuer != self._issuer:
            msg = f"asked for the keys of {issuer!r}; this process trusts {self._issuer!r} only"
            raise IdentityError(msg)
        return key_set_from_jwks(self._get(self._url), issuer=issuer, fetched_at=self._clock())


# ------------------------------------------------------------------ assembling


def keycloak_authority(
    *,
    directory: PrincipalDirectory,
    get: Callable[[str], bytes],
    clock: Callable[[], datetime],
    env: Mapping[str, str] | None = None,
    memberships: MembershipObserver | None = None,
) -> TokenAuthority:
    """The token authority for this installation's realm.

    The issuer is `INSTALL_OIDC_ISSUER`, which has no default and refuses when unset (see
    `brain.install.A_GUESSED_IDENTITY_PROVIDER_IS_WORSE_THAN_A_STOPPED_ONE`), so a process
    without one fails where it is built rather than refusing every sign-in as a bad token.
    `env` is for tests; a deployed process passes nothing and the environment is read by
    `brain.install`, the one reader.
    """
    issuer = value_of("INSTALL_OIDC_ISSUER", env)
    return TokenAuthority(
        issuer=issuer,
        audience=API_AUDIENCE,
        keys=JwksCache(KeycloakJwks(issuer, get=get, clock=clock)),
        verify=verify_rs256,
        directory=directory,
        leeway=TOKEN_LEEWAY,
        memberships=memberships,
    )
