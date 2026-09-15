"""`brain.identity.keycloak_tokens`: real RS256 tokens, real keys, and no network.

Every key here is generated in the test and every token is signed with one, so a signature
check that passed would be a signature check that works. The identity provider is a fake
that serves a key-set document and counts requests, which is what the refetch rules are
about; the HTTP fetcher is tested separately over `httpx.MockTransport`.

Dates are fixed in 2031 and nothing reads the wall clock: `now` is handed to every call.

Task ids: M1.1.2
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from brain.core.principal import Employment, Principal, PrincipalKind
from brain.identity.bearer import Caller, TokenAuthority
from brain.identity.keycloak_tokens import (
    API_AUDIENCE,
    MAX_JWKS_BYTES,
    TOKEN_LEEWAY,
    VERIFIED_ALGORITHMS,
    KeycloakJwks,
    http_get,
    jwks_url_for,
    key_set_from_jwks,
    keycloak_authority,
    signing_key_from_jwk,
    verify_rs256,
)
from brain.identity.oidc import (
    ALLOWED_ALGORITHMS,
    JWKS_MIN_REFETCH,
    MAX_LEEWAY,
    SIGN_IN_PROMPT,
    SigningKey,
    TokenRefusal,
    TokenRefusedError,
)
from brain.identity.roles import IdentityError
from brain.install import InstallError

REPO = Path(__file__).resolve().parents[2]
REALM = REPO / "ops" / "keycloak" / "realm-export.json"

NOW = datetime(2031, 3, 4, 9, 0, tzinfo=UTC)
ISSUER = "https://id.example.com/realms/brain"
SUBJECT = "0b7c2f7e-0000-4000-8000-00000000000a"
KID = "realm-key-1"

SIGNING = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ATTACKER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ROTATED = rsa.generate_private_key(public_exponent=65537, key_size=2048)


# ------------------------------------------------------------------- fixtures
def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def pem_of(private: rsa.RSAPrivateKey) -> str:
    return (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )


def jwk_of(private: rsa.RSAPrivateKey, kid: str = KID, /, **over: object) -> dict[str, object]:
    """A JWK as Keycloak publishes one. An override of None removes the member, and `kid` is
    positional so an override can replace it too."""
    numbers = private.public_key().public_numbers()

    def integer(value: int) -> str:
        return b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    jwk: dict[str, object] = {
        "kid": kid,
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": integer(numbers.n),
        "e": integer(numbers.e),
    }
    jwk.update(over)
    return {name: value for name, value in jwk.items() if value is not None}


def rs256(private: rsa.RSAPrivateKey) -> Callable[[bytes], bytes]:
    return lambda data: private.sign(data, padding.PKCS1v15(), hashes.SHA256())


def token(
    *,
    sign: Callable[[bytes], bytes] | None = None,
    header: dict[str, object] | None = None,
    **claims: object,
) -> str:
    head: dict[str, object] = {"alg": "RS256", "kid": KID, "typ": "JWT"}
    head.update(header or {})
    payload: dict[str, object] = {
        "iss": ISSUER,
        "aud": API_AUDIENCE,
        "sub": SUBJECT,
        "typ": "Bearer",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(seconds=300)).timestamp()),
    }
    payload.update(claims)
    signing_input = f"{b64(json.dumps(head).encode())}.{b64(json.dumps(payload).encode())}"
    signature = (sign or rs256(SIGNING))(signing_input.encode("ascii"))
    return f"{signing_input}.{b64(signature)}"


class Idp:
    """Serves a key-set document and records every address it was asked for."""

    def __init__(self, *jwks: dict[str, object]) -> None:
        self.document: dict[str, object] = {"keys": list(jwks or (jwk_of(SIGNING),))}
        self.urls: list[str] = []

    def publish(self, *jwks: dict[str, object]) -> None:
        self.document = {"keys": list(jwks)}

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        return json.dumps(self.document).encode()


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class Directory:
    """One person, at the issuer this installation trusts."""

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        if issuer != ISSUER or subject != SUBJECT:
            return None
        return Principal(
            id="u_signed_in",
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name="Signed In",
            primary_department="web",
        )


class Realm:
    """An authority over a fake identity provider, with the clock kept in step with `now`."""

    def __init__(self, idp: Idp | None = None) -> None:
        self.idp = idp or Idp()
        self.clock = Clock()
        self.authority: TokenAuthority = keycloak_authority(
            directory=Directory(),
            get=self.idp.get,
            clock=self.clock,
            env={"INSTALL_OIDC_ISSUER": ISSUER},
        )

    def present(self, compact: str, *, at: datetime = NOW) -> Caller:
        self.clock.now = at
        return asyncio.run(self.authority.authenticate(f"Bearer {compact}", now=at))

    def refused(self, compact: str, *, at: datetime = NOW) -> TokenRefusedError:
        with pytest.raises(TokenRefusedError) as caught:
            self.present(compact, at=at)
        return caught.value


@pytest.fixture
def realm() -> Iterator[Realm]:
    yield Realm()


def realm_file() -> dict[str, object]:
    loaded = json.loads(REALM.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# ------------------------------------------------------------------ acceptance
def test_a_token_the_realm_signed_is_accepted_as_the_person_it_names(realm: Realm) -> None:
    """The positive case every refusal below is measured against. Deleting it leaves a suite
    that a verifier refusing everything passes, which is the state a deployed process was in
    before this module existed. It also pins where the keys were read from: the realm's own
    certs endpoint, spelled out here rather than rebuilt from the module's constant."""
    caller = realm.present(token())

    assert caller.principal.id == "u_signed_in"
    assert caller.claims.key_id == KID
    assert caller.claims.algorithm == "RS256"
    assert realm.idp.urls == ["https://id.example.com/realms/brain/protocol/openid-connect/certs"]


def test_a_token_expired_inside_the_leeway_is_still_accepted(realm: Realm) -> None:
    """The leeway is actually handed to validation. Deleting this lets `keycloak_authority`
    pass no tolerance at all, and every token from a server whose clock is a few seconds
    ahead is refused, with every refusal test still green because they are all far outside
    any leeway. (Dropping the argument entirely would not be noticed and does not matter:
    `oidc.DEFAULT_LEEWAY` is the same thirty seconds today.)"""
    just_expired = int((NOW - TOKEN_LEEWAY + timedelta(seconds=5)).timestamp())
    realm.present(token(exp=just_expired, iat=int((NOW - timedelta(minutes=5)).timestamp())))


# -------------------------------------------------------------------- refusals
def test_a_token_signed_by_another_key_under_the_published_kid_is_refused(realm: Realm) -> None:
    """A forger names the realm's real key id and signs with their own key. Deleting this
    means a verifier that answered True for any signature would pass the whole file except
    the tests that happen to check a reason."""
    assert realm.refused(token(sign=rs256(ATTACKER))).reason is TokenRefusal.BAD_SIGNATURE


def test_a_token_from_another_issuer_is_refused(realm: Realm) -> None:
    """Signed by the right key and naming another realm. Deleting this lets the authority be
    built with the issuer from somewhere other than the installation setting unnoticed."""
    compact = token(iss="https://id.example.com/realms/other")
    assert realm.refused(compact).reason is TokenRefusal.WRONG_ISSUER


def test_a_token_minted_for_another_audience_is_refused(realm: Realm) -> None:
    """A console token with no API audience is the confused deputy. Deleting this lets the
    authority's audience become anything, including the console's own client id."""
    assert realm.refused(token(aud="brain-console")).reason is TokenRefusal.WRONG_AUDIENCE


def test_an_expired_token_is_refused(realm: Realm) -> None:
    """Expired by more than the leeway. Deleting this leaves only the within-leeway
    acceptance, which an authority with an unbounded leeway also passes."""
    expired = int((NOW - TOKEN_LEEWAY - timedelta(seconds=1)).timestamp())
    compact = token(exp=expired, iat=int((NOW - timedelta(minutes=10)).timestamp()))
    assert realm.refused(compact).reason is TokenRefusal.EXPIRED


def test_a_token_not_yet_valid_is_refused(realm: Realm) -> None:
    """`nbf` five minutes ahead. Deleting this means a token minted for later, which is what
    a pre-issued credential looks like, is accepted now with nothing noticing."""
    compact = token(nbf=int((NOW + timedelta(minutes=5)).timestamp()))
    assert realm.refused(compact).reason is TokenRefusal.NOT_YET_VALID


def test_a_token_declaring_no_algorithm_is_refused(realm: Realm) -> None:
    """`alg: none` with an empty signature, the canonical forgery. Deleting this removes the
    only test in this file where the token carries no signature at all."""
    compact = token(header={"alg": "none"}, sign=lambda _data: b"")
    assert realm.refused(compact).reason is TokenRefusal.ALG_NONE


def test_hs256_signed_with_the_published_public_key_is_refused(realm: Realm) -> None:
    """The algorithm confusion attack, built for real: the realm's public key, which anybody
    can fetch, used as an HMAC secret, under the realm's real key id. Deleting this means
    nothing in the suite exercises a symmetric token against a real RSA key set."""
    secret = pem_of(SIGNING).encode("ascii")
    compact = token(
        header={"alg": "HS256"},
        sign=lambda data: hmac.new(secret, data, hashlib.sha256).digest(),
    )
    assert realm.refused(compact).reason is TokenRefusal.ALG_NOT_ALLOWED


def test_the_verifier_refuses_a_key_published_for_another_algorithm() -> None:
    """A genuine PKCS#1 v1.5 SHA-256 signature, handed to the verifier with a key that says
    PS256. `oidc` would allow PS256, so this is the verifier's own allow-list and nothing
    else. Deleting this lets `verify_rs256` check any key as RS256 whatever it was published
    for. The sibling line proves the same signature verifies under an RS256 key."""
    data = b"header.payload"
    signature = rs256(SIGNING)(data)
    material = pem_of(SIGNING)

    rs = SigningKey(kid=KID, algorithm="RS256", material=material)
    ps = SigningKey(kid=KID, algorithm="PS256", material=material)
    assert verify_rs256(signing_input=data, signature=signature, key=rs) is True
    assert verify_rs256(signing_input=data, signature=signature, key=ps) is False


def test_the_verifier_refuses_a_short_rsa_key_even_with_a_valid_signature() -> None:
    """See `A_SHORT_KEY_IS_REFUSED_WHEREVER_IT_CAME_FROM`. Deleting this lets a 1024-bit key
    from any key source verify, because the signature on it is perfectly genuine."""
    # Short on purpose: the key under test is the one the verifier must refuse.
    short = rsa.generate_private_key(public_exponent=65537, key_size=1024)  # noqa: S505
    data = b"header.payload"
    key = SigningKey(kid=KID, algorithm="RS256", material=pem_of(short))
    assert verify_rs256(signing_input=data, signature=rs256(short)(data), key=key) is False


def test_the_verifier_refuses_material_that_is_not_an_rsa_key() -> None:
    """An EC public key, and text that is no key at all. Deleting this lets a non-RSA key
    reach `verify` with RSA padding, which raises rather than refusing, and a raise inside
    `validate_token` is a fault rather than a refusal."""
    ec_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    for material in (ec_pem, "not a key"):
        key = SigningKey(kid=KID, algorithm="RS256", material=material)
        assert verify_rs256(signing_input=b"x", signature=b"y", key=key) is False


def test_an_unknown_kid_is_refused_after_one_refetch(realm: Realm) -> None:
    """Outside the refetch floor, a key id nobody publishes costs exactly one more fetch and
    is then refused. Deleting this loses the proof that the refetch happened and still did
    not accept the token, which is the half of rotation that must fail."""
    realm.present(token())
    later = NOW + JWKS_MIN_REFETCH + timedelta(seconds=1)

    refused = realm.refused(token(header={"kid": "never-published"}), at=later)

    assert refused.reason is TokenRefusal.UNKNOWN_KEY
    assert len(realm.idp.urls) == 2


def test_a_rotated_key_is_accepted_after_one_refetch(realm: Realm) -> None:
    """The positive sibling of the refusal above. Keycloak rotates, the new key id appears
    before the cache expires, and one refetch finds it. Deleting this means a refetch that
    never happened would pass the refusal test, because an unknown key is refused either way."""
    realm.present(token())
    realm.idp.publish(jwk_of(ROTATED, "realm-key-2"), jwk_of(SIGNING))
    later = NOW + JWKS_MIN_REFETCH + timedelta(seconds=1)

    caller = realm.present(token(header={"kid": "realm-key-2"}, sign=rs256(ROTATED)), at=later)

    assert caller.claims.key_id == "realm-key-2"
    assert len(realm.idp.urls) == 2


def test_a_storm_of_unknown_kids_costs_one_fetch_per_window(realm: Realm) -> None:
    """Fifty tokens with fifty invented key ids inside one window reach the identity
    provider once, and the next window lets exactly one more through. Deleting this lets the
    refetch floor go, and then anybody can make this process hammer the realm with its own
    credentials, one request per token."""
    realm.present(token())
    window = NOW + JWKS_MIN_REFETCH + timedelta(seconds=1)

    for number in range(50):
        refused = realm.refused(token(header={"kid": f"invented-{number}"}), at=window)
        assert refused.reason is TokenRefusal.UNKNOWN_KEY
    assert len(realm.idp.urls) == 2

    realm.refused(token(header={"kid": "invented-next"}), at=window + JWKS_MIN_REFETCH)
    assert len(realm.idp.urls) == 3


def test_every_refusal_tells_the_presenter_the_same_sentence(realm: Realm) -> None:
    """See `bearer.EVERY_REFUSAL_SAYS_THE_SAME_SENTENCE`. Seven different reasons, one public
    message, and no message carries its own reason. Deleting this lets a refusal from the new
    verifier path grow a helpful message that tells a forger which part to fix next."""
    expired = int((NOW - timedelta(hours=1)).timestamp())
    refusals = [
        realm.refused(token(sign=rs256(ATTACKER))),
        realm.refused(token(iss="https://id.example.com/realms/other")),
        realm.refused(token(aud="brain-console")),
        realm.refused(token(exp=expired, iat=expired - 300)),
        realm.refused(token(nbf=int((NOW + timedelta(minutes=5)).timestamp()))),
        realm.refused(token(header={"alg": "none"}, sign=lambda _data: b"")),
        realm.refused(token(header={"kid": "never-published"})),
    ]

    assert len({refusal.reason for refusal in refusals}) == 7
    assert {refusal.public_message for refusal in refusals} == {SIGN_IN_PROMPT}
    for refusal in refusals:
        assert str(refusal.reason) not in refusal.public_message


# ------------------------------------------------------------------ key sets
def test_keys_this_verifier_cannot_use_do_not_stop_the_signing_key_loading() -> None:
    """Keycloak's default realm publishes an RSA-OAEP encryption key beside the signing key,
    and a symmetric key could appear too. The signing key still verifies, and a token naming
    the encryption key's id is refused as unknown. Deleting this lets the reader refuse a
    whole document over one unusable entry, which on a default realm is every sign-in."""
    realm = Realm(
        Idp(
            jwk_of(SIGNING),
            jwk_of(SIGNING, "enc-key", alg="RSA-OAEP", use="enc"),
            {"kid": "hmac-key", "kty": "oct", "alg": "HS256", "use": "sig", "k": "c2VjcmV0"},
        )
    )

    realm.present(token())
    assert realm.refused(token(header={"kid": "enc-key"})).reason is TokenRefusal.UNKNOWN_KEY


@pytest.mark.parametrize(
    ("label", "over"),
    [
        ("no kid", {"kid": None}),
        ("empty kid", {"kid": ""}),
        ("not RSA", {"kty": "EC"}),
        ("published for encryption", {"use": "enc"}),
        ("no use", {"use": None}),
        ("another algorithm", {"alg": "RS384"}),
        ("no algorithm", {"alg": None}),
        ("no modulus", {"n": None}),
        ("no exponent", {"e": None}),
        ("an exponent that is not a key's", {"e": b64(b"\x01")}),
        ("a kid longer than a key id may be", {"kid": "k" * 201}),
    ],
)
def test_a_published_key_this_verifier_cannot_use_is_dropped(
    label: str, over: dict[str, object]
) -> None:
    """Each row is one reason to drop a key rather than guess, and the first assertion is the
    sibling proving an otherwise identical key is kept. Deleting this lets any of the eleven
    conditions go with the acceptance tests still green, because the realm's real key passes
    all of them."""
    assert signing_key_from_jwk(jwk_of(SIGNING)) is not None
    assert signing_key_from_jwk(jwk_of(SIGNING, **over)) is None, label


@pytest.mark.parametrize("modulus", ["A", "é"])
def test_a_modulus_the_decoder_refuses_is_dropped(modulus: str) -> None:
    """Separate from the table because it is the decoder raising, not a member missing: one
    character is a length no base64 can have, and a non-ASCII character is refused before
    decoding. Deleting this lets `_b64url_integer` let that raise escape, which arrives as a
    fault that `JwksCache` reports as no keys at all rather than as one dropped key. (A member
    of punctuation such as `@` does not reach the handler: the decoder discards it.)"""
    assert signing_key_from_jwk(jwk_of(SIGNING, n=modulus)) is None


@pytest.mark.parametrize(
    "document",
    [
        b"not json",
        b"[]",
        b'{"keys": {}}',
        json.dumps({"keys": [{"kty": "oct"}]}).encode(),
        json.dumps({"keys": ["not an object"]}).encode(),
    ],
)
def test_a_document_that_is_not_a_usable_key_set_is_refused(document: bytes) -> None:
    """Not JSON, not an object, keys not a list, a list with nothing usable, and a list whose
    entry is not an object at all, which must be skipped rather than read. Deleting this
    lets an empty set be cached, and an empty set refuses every token as an unknown key for an
    hour with no line saying the realm published nothing."""
    with pytest.raises(IdentityError):
        key_set_from_jwks(document, issuer=ISSUER, fetched_at=NOW)


def test_a_realm_publishing_nothing_usable_refuses_sign_in_as_no_keys() -> None:
    """Through the authority, the document fault above becomes a token refusal with its own
    reason. Deleting this loses the check that a bad document refuses rather than raising a
    fault out of the route."""
    realm = Realm(Idp(jwk_of(SIGNING, use="enc")))
    assert realm.refused(token()).reason is TokenRefusal.NO_KEYS_AVAILABLE


# ------------------------------------------------------------------ fetching
@pytest.mark.parametrize(
    "issuer",
    [
        "https://id.example.com/realms/brain",
        "http://localhost:8080/realms/brain",
        "http://127.0.0.1:8080/realms/brain",
    ],
)
def test_an_issuer_on_https_or_this_machine_has_its_keys_read(issuer: str) -> None:
    """The sibling of the refusals below. Deleting this lets the transport rule refuse a
    development Keycloak on loopback, which is the one plain-http realm that is safe."""
    assert jwks_url_for(issuer) == f"{issuer}/protocol/openid-connect/certs"


@pytest.mark.parametrize(
    "issuer",
    [
        "http://id.example.com/realms/brain",
        "http://10.0.0.5/realms/brain",
        "https://id.example.com/realms/brain/",
        "https:///realms/brain",
        "ftp://id.example.com/realms/brain",
    ],
)
def test_an_issuer_whose_keys_could_be_substituted_or_never_match_is_refused(
    issuer: str,
) -> None:
    """Plain http off this machine, a trailing slash, no host, another scheme. Deleting this
    lets keys be read over a transport anybody on the path can rewrite, which is every token
    that path's owner cares to sign."""
    with pytest.raises(IdentityError):
        jwks_url_for(issuer)


def test_the_key_source_fetches_for_its_own_issuer_and_no_other() -> None:
    """Deleting this lets the fetch serve whatever issuer it is asked about, and it would then
    read keys from wherever a wiring mistake pointed it. No request is made for the stranger."""
    idp = Idp()
    source = KeycloakJwks(ISSUER, get=idp.get, clock=Clock())

    with pytest.raises(IdentityError):
        source("https://id.example.com/realms/other")
    assert idp.urls == []
    assert source(ISSUER).by_kid(KID) is not None


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_http_fetch_returns_the_body_of_a_successful_answer() -> None:
    """The sibling of the three refusals below. Deleting this lets `http_get` refuse every
    answer, which the refusal tests alone would call correct."""
    body = json.dumps({"keys": [jwk_of(SIGNING)]}).encode()
    get = http_get(_client(lambda _request: httpx.Response(200, content=body)))
    assert get(jwks_url_for(ISSUER)) == body


def test_the_http_fetch_does_not_follow_a_redirect() -> None:
    """See `A_REDIRECTED_KEY_SET_IS_A_SUBSTITUTED_KEY_SET`. The redirect target is never
    requested. Deleting this lets `follow_redirects` flip and the keys come from wherever the
    first answer pointed."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://elsewhere.example.com/certs"})

    with pytest.raises(IdentityError):
        http_get(_client(handler))(jwks_url_for(ISSUER))
    assert asked == [jwks_url_for(ISSUER)]


def test_the_http_fetch_refuses_an_error_answer() -> None:
    """Deleting this lets a 500 page's body be handed to the key-set reader, which then
    reports a malformed document rather than an identity provider that is down."""
    with pytest.raises(IdentityError):
        http_get(_client(lambda _request: httpx.Response(500, content=b"{}")))(ISSUER)


def test_the_http_fetch_refuses_a_body_larger_than_a_key_set() -> None:
    """Deleting this lets whatever answers the key-set address decide how much memory the
    process reads into one request."""
    huge = b" " * (MAX_JWKS_BYTES + 1)
    with pytest.raises(IdentityError):
        http_get(_client(lambda _request: httpx.Response(200, content=huge)))(ISSUER)


# --------------------------------------------------------- held to the realm
def test_an_installation_with_no_issuer_refuses_to_build_an_authority() -> None:
    """The issuer comes from `INSTALL_OIDC_ISSUER` and nowhere else, and an unset one stops
    the build. Deleting this lets `keycloak_authority` grow a default issuer, which is a
    sign-in page trusting a realm this installation never named."""
    with pytest.raises(InstallError):
        keycloak_authority(directory=Directory(), get=Idp().get, clock=Clock(), env={})


def test_the_audience_is_the_one_the_realm_file_mints_for() -> None:
    """Held against the audience mapper in the realm file rather than against the constant
    itself. Deleting this lets `API_AUDIENCE` drift from the realm and every real token be
    refused as minted for another party."""
    audiences: set[object] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("protocolMapper") == "oidc-audience-mapper":
                config = node.get("config")
                assert isinstance(config, dict)
                audiences.add(config.get("included.client.audience"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(realm_file())
    assert audiences == {API_AUDIENCE}


def test_the_verified_algorithms_are_the_realms_and_inside_the_allow_list() -> None:
    """The realm signs with its default algorithm, and `oidc` must allow it before this
    verifier is ever asked. Deleting this lets the verifier's list widen past the realm, or
    name an algorithm `validate_token` refuses first, with nothing noticing either."""
    assert {realm_file()["defaultSignatureAlgorithm"]} == VERIFIED_ALGORITHMS
    assert VERIFIED_ALGORITHMS <= ALLOWED_ALGORITHMS
    assert "HS256" not in VERIFIED_ALGORITHMS


def test_the_leeway_is_a_tenth_of_a_token_life_at_most() -> None:
    """Held against the realm's access token lifespan and `oidc.MAX_LEEWAY`. Deleting this lets
    the leeway grow until an expired token is accepted for a large part of a second life."""
    lifespan = realm_file()["accessTokenLifespan"]
    assert isinstance(lifespan, int)
    assert timedelta(0) < TOKEN_LEEWAY <= timedelta(seconds=lifespan) / 10
    assert TOKEN_LEEWAY <= MAX_LEEWAY
