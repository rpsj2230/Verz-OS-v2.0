"""A Google service account's key, kept small enough for the vault, and the assertion it signs.

`brain.connectors.google_service_account` turns the key file a company downloads into what the
vault keeps, turns that back into a key, and signs the one assertion Google exchanges for a token.
The keys here are generated in the test, the key file is written in the shape Google documents,
and nothing is sent anywhere: the exchange is an `Outbound` value.

Task ids: M1.6.5
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from brain.connectors.google_service_account import (
    ServiceAccountKeyError,
    kept_value,
    service_account,
    token_request,
)
from brain.ops.credentials import MAX_CREDENTIAL_CHARS, problems_with

#: Far outside any plausible wall clock, so the assertion's times are a value and not a clock.
NOW = 32503680000  # 3000-01-01
ADMIN = "Directory-Reader@Example.com"
ACCOUNT = "staff-sync@a-project.iam.gserviceaccount.com"


def pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def key_file(key: rsa.RSAPrivateKey, **changed: Any) -> str:
    """A key file in the shape Google's console downloads, pretty-printed as it arrives."""
    fields = {
        "type": "service_account",
        "project_id": "PROJECT-ID-SENTINEL",
        "private_key_id": "PRIVATE-KEY-ID-SENTINEL",
        "private_key": pem(key),
        "client_email": ACCOUNT,
        "client_id": "123456789012345678901",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://tokens.example.invalid/steal",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/x",
        "universe_domain": "googleapis.com",
        **changed,
    }
    return json.dumps(fields, indent=2)


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def unpadded(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def test_a_key_file_is_kept_as_its_key_alone_and_that_key_signs_exactly_as_the_file_s(
    key: rsa.RSAPrivateKey,
) -> None:
    """`THE_VAULT_KEEPS_THE_KEY_AND_NOTHING_ELSE_IN_THE_FILE`. The kept value passes the vault's
    own check on a credential, carries nothing else from the file, and rebuilds a key whose
    signature over the same bytes is byte-for-byte the file key's, which is what proves the whole
    key survived: PKCS#1 v1.5 signing is deterministic.

    Delete this and a kept value could lose half the key and still parse, and the first sign is a
    refused token every night."""
    kept = kept_value(ADMIN, key_file(key))
    rebuilt = service_account(kept)
    message = b"the same bytes, signed twice"

    assert problems_with(kept) == ()
    assert len(kept) <= MAX_CREDENTIAL_CHARS
    for dropped in ("PRIVATE-KEY-ID-SENTINEL", "PROJECT-ID-SENTINEL", "tokens.example", "BEGIN"):
        assert dropped not in kept
    assert rebuilt.admin == ADMIN.casefold()
    assert rebuilt.client_email == ACCOUNT
    assert rebuilt.key.sign(message, padding.PKCS1v15(), hashes.SHA256()) == key.sign(
        message, padding.PKCS1v15(), hashes.SHA256()
    )


def test_the_assertion_is_signed_by_the_key_as_the_administrator_for_two_read_only_scopes(
    key: rsa.RSAPrivateKey,
) -> None:
    """`DELEGATION_IS_NARROWED_BY_SCOPE`. The claim set Google documents: issued by the service
    account, for the administrator it acts as, for the user and group read-only scopes and no
    other, addressed to Google's token endpoint, living inside Google's hour.

    The expected scopes and the hour are written here rather than imported. Delete this and the
    assertion can ask for a write scope, or live longer than Google accepts."""
    outbound = token_request(service_account(kept_value(ADMIN, key_file(key))), now=NOW)
    assert outbound.form is not None
    header, claims, signature = outbound.form["assertion"].split(".")

    key.public_key().verify(
        unpadded(signature),
        f"{header}.{claims}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    assert json.loads(unpadded(header)) == {"alg": "RS256", "typ": "JWT"}
    said = json.loads(unpadded(claims))
    assert said["iss"] == ACCOUNT
    assert said["sub"] == ADMIN.casefold()
    assert set(said["scope"].split()) == {
        "https://www.googleapis.com/auth/admin.directory.user.readonly",
        "https://www.googleapis.com/auth/admin.directory.group.readonly",
    }
    assert said["aud"] == "https://oauth2.googleapis.com/token"
    assert said["iat"] == NOW
    assert 0 < said["exp"] - said["iat"] <= 3600
    assert outbound.form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"


def test_the_signed_assertion_goes_to_google_and_never_to_the_address_the_file_names(
    key: rsa.RSAPrivateKey,
) -> None:
    """`A_KEY_FILE_DOES_NOT_CHOOSE_WHERE_ITS_SIGNATURE_GOES`. The fixture's key file names another
    token address, and the exchange ignores it.

    Delete this and a pasted file chooses where a signature made with the company's key is sent."""
    outbound = token_request(service_account(kept_value(ADMIN, key_file(key))), now=NOW)

    assert (outbound.method, outbound.url) == ("POST", "https://oauth2.googleapis.com/token")
    assert "PRIVATE KEY" not in repr(outbound)


def _refusal_for(text: str) -> str:
    with pytest.raises(ServiceAccountKeyError) as refused:
        kept_value(ADMIN, text)
    return str(refused.value)


def test_what_is_not_a_google_service_account_key_is_refused_in_words_that_repeat_none_of_it(
    key: rsa.RSAPrivateKey,
) -> None:
    """Text that is not JSON, a key file for something else, one with no service account address,
    a private key that does not load, a key too short and a key with another public exponent are
    each refused in a sentence, and no sentence repeats the file, which holds the private key.

    The sibling is the round trip above. Delete this and a pasted private key can come back in the
    refusal meant to explain it, or a key Google would refuse is kept and fails every night."""
    # A key too short is the case under test: it must be refused.
    small = rsa.generate_private_key(public_exponent=65537, key_size=1024)  # noqa: S505
    odd = rsa.generate_private_key(public_exponent=3, key_size=2048)
    pasted = [
        "not a key file at all SENTINEL-PASTE",
        key_file(key, type="authorized_user"),
        key_file(key, client_email="someone@example.com"),
        key_file(
            key, private_key="-----BEGIN PRIVATE KEY-----\nSENTINEL\n-----END PRIVATE KEY-----"
        ),
        key_file(small),
        key_file(odd),
        "x" * 9000,
    ]
    for text in pasted:
        told = _refusal_for(text)
        assert told
        assert "SENTINEL" not in told
        assert "PRIVATE KEY" not in told
        assert pem(key)[40:80] not in told
    with pytest.raises(ServiceAccountKeyError):
        kept_value("not-an-address", key_file(key))
    with pytest.raises(ServiceAccountKeyError):
        kept_value("a:b@example.com", key_file(key))


def test_a_kept_value_in_any_other_form_is_refused_and_never_repeated(
    key: rsa.RSAPrivateKey,
) -> None:
    """The vault's value is read back by the worker alone, and one in another form (a Lark or
    Microsoft credential left from a previous choice, a truncated copy, two numbers that are not
    primes) is refused in words that repeat none of it.

    Delete this and a leftover `<id>:<secret>` reaches the signer, or a refusal carries the secret
    into the run's row on the Staff sources screen."""
    kept = kept_value(ADMIN, key_file(key))
    admin, email, primes = kept.split(":")
    composite = base64.urlsafe_b64encode((2**1024 + 1).to_bytes(129, "big")).decode().rstrip("=")
    others = [
        "cli_a1b2c3:SENTINEL-secret",
        f"{admin}:{email}",
        f"{admin}:{email}:{primes.split('.')[0]}",
        f"{admin}:{email}:{composite}.{composite}",
        f"{admin}:someone@example.com:{primes}",
        f"not-an-address:{email}:{primes}",
    ]
    for value in others:
        with pytest.raises(ServiceAccountKeyError) as refused:
            service_account(value)
        assert "SENTINEL" not in str(refused.value)
        assert primes[:20] not in str(refused.value)
    assert service_account(kept).client_email == ACCOUNT


def test_a_service_account_s_representation_leaves_the_key_out(key: rsa.RSAPrivateKey) -> None:
    """An exception holding one renders it into a traceback, and a traceback is logged. Delete
    this and the key's representation can reach a log line."""
    account = service_account(kept_value(ADMIN, key_file(key)))

    assert "key" not in repr(account).replace("key=", "")
    assert "RSAPrivateKey" not in repr(account)
