"""The S3 client, its signature, what builds it at start, and the reader of the backup bucket.

The signature is held against the four examples AWS publishes for S3, with their own example key
and expected signatures, so the canonical form is tested by something outside this repository.
Everything else runs against `tests.fixtures.fake_s3.FakeS3`, which verifies every signature it is
sent and refuses the ones that do not verify.

Task ids: M32.3.1.4, M32.3.2.1, M32.3.2.2
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from brain.ops import object_store
from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX
from brain.ops.object_store import (
    A_LEASE_NOBODY_RENEWS_IS_A_CREDENTIAL_THAT_STOPS_WORKING_ON_A_SCHEDULE,
    ACCESS_KEY_FIELD,
    BACKEND_SETTING,
    ENDPOINT_SETTING,
    LIST_PAGE,
    NO_VAULT_SO_NO_STORE_CREDENTIAL,
    PREFIX_SETTING,
    SECRET_KEY_FIELD,
    THE_BACKEND_SETTING_NAMES_NO_BACKEND,
    THE_STORE_SETTINGS_ARE_REFUSED,
    THE_STORE_SLOT_HOLDS_NO_KEY,
    THE_STORE_SLOT_IS_NOT_A_KEY_PAIR,
    THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY,
    USAGE_CEILING_OBJECTS,
    S3Backend,
    StoreCredential,
    authorization,
    backup_objects,
    object_store_at_start,
)
from brain.ops.openbao import VaultRefusedError, VaultUnreachableError
from brain.ops.storage import (
    Backend,
    ObjectKind,
    StorageError,
    StoreUnansweredError,
    bucket_for,
    config_for,
    credential_path,
)
from tests.fixtures.fake_s3 import FakeS3

#: AWS's documented example key pair for Signature Version 4. Not a credential of anybody's.
AWS_EXAMPLE = StoreCredential(
    access_key_id="AKIAIOSFODNN7EXAMPLE",
    secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
)
AWS_EXAMPLE_AT = datetime(2013, 5, 24, tzinfo=UTC)
AWS_HOST = "examplebucket.s3.amazonaws.com"
EMPTY = hashlib.sha256(b"").hexdigest()
WELCOME = hashlib.sha256(b"Welcome to Amazon S3.").hexdigest()

#: The key the fake store accepts, and one it does not.
KEY = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test-secret")
WRONG = StoreCredential(access_key_id="brain-test-access", secret_access_key="another-secret")
SLOT = {ACCESS_KEY_FIELD: KEY.access_key_id, SECRET_KEY_FIELD: KEY.secret_access_key}
ENDPOINT = "http://objects.example.test:8333"
SETTINGS = {ENDPOINT_SETTING: ENDPOINT, PREFIX_SETTING: "brain", BACKEND_SETTING: "seaweedfs"}


def backend_over(store: FakeS3, credential: StoreCredential = KEY) -> S3Backend:
    return S3Backend(
        config_for(Backend.SEAWEEDFS, endpoint_url=ENDPOINT),
        credential,
        transport=store.transport(),
    )


@pytest.mark.parametrize(
    ("method", "path", "query", "headers", "payload", "signature"),
    [
        (
            "GET",
            "/test.txt",
            [],
            {"Host": AWS_HOST, "Range": "bytes=0-9", "x-amz-content-sha256": EMPTY},
            EMPTY,
            "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41",
        ),
        (
            "PUT",
            "/test$file.text",
            [],
            {
                "Host": AWS_HOST,
                "Date": "Fri, 24 May 2013 00:00:00 GMT",
                "x-amz-storage-class": "REDUCED_REDUNDANCY",
                "x-amz-content-sha256": WELCOME,
            },
            WELCOME,
            "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd",
        ),
        (
            "GET",
            "/",
            [("lifecycle", "")],
            {"Host": AWS_HOST, "x-amz-content-sha256": EMPTY},
            EMPTY,
            "fea454ca298b7da1c68078a5d1bdbfbbe0d65c699e0f91ac7a200a0136783543",
        ),
        (
            "GET",
            "/",
            [("max-keys", "2"), ("prefix", "J")],
            {"Host": AWS_HOST, "x-amz-content-sha256": EMPTY},
            EMPTY,
            "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7",
        ),
    ],
)
def test_a_signature_matches_each_example_aws_publishes_for_s3(
    method: str,
    path: str,
    query: list[tuple[str, str]],
    headers: dict[str, str],
    payload: str,
    signature: str,
) -> None:
    """GET object, PUT object with a character that must be encoded, a bare sub-resource and a
    listing with a query, from AWS's Signature Version 4 examples for S3. Delete this and a wrong
    canonical form is verified only by a fake that shares it, and arrives at a real store as a 403
    that reads as a bad key."""
    signed = authorization(
        method=method,
        path=path,
        query=query,
        headers={**headers, "x-amz-date": "20130524T000000Z"},
        payload_sha256=payload,
        credential=AWS_EXAMPLE,
        region="us-east-1",
        at=AWS_EXAMPLE_AT,
    )
    assert signed.endswith(f"Signature={signature}")
    assert signed.startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/")


def test_a_request_is_not_signed_at_a_naive_instant() -> None:
    """Delete this and a host off UTC signs every request at the wrong hour, which a store refuses
    as a clock skew fifteen minutes later than anybody looks."""
    with pytest.raises(StorageError):
        authorization(
            method="GET",
            path="/",
            query=[],
            headers={"host": AWS_HOST},
            payload_sha256=EMPTY,
            credential=AWS_EXAMPLE,
            region="us-east-1",
            at=datetime(2013, 5, 24),
        )


def test_an_object_put_is_read_back_listed_and_deleted_through_a_store_that_checks_signatures() -> (
    None
):
    """The positive case for everything below. Delete this and a client refusing every request
    passes every refusal test."""
    store = FakeS3(credential=KEY).holding("assets", {})
    backend = backend_over(store)
    backend.put_object("assets", "brain/artifacts/payload/one", b"bytes", "text/plain")
    assert backend.get_object("assets", "brain/artifacts/payload/one") == b"bytes"
    assert list(backend.list_objects("assets", "brain/")) == ["brain/artifacts/payload/one"]
    backend.delete_object("assets", "brain/artifacts/payload/one")
    assert store.buckets["assets"] == {}


def test_a_request_signed_with_another_secret_is_refused_and_raised_with_the_code() -> None:
    """The store is the judge of the key, and its refusal reaches the caller as unanswered with the
    S3 code in it. Delete this and a signing that ignores the secret passes against a fake that
    accepts anything."""
    store = FakeS3(credential=KEY).holding("assets", {"brain/x": b"1"})
    with pytest.raises(StoreUnansweredError, match="403 \\(SignatureDoesNotMatch\\)"):
        backend_over(store, WRONG).get_object("assets", "brain/x")
    assert store.asked == []


def test_a_request_signed_for_another_region_is_refused() -> None:
    """Delete this and the region `config_for` resolves can be dropped from the signature, which is
    the R2 403 `brain.ops.storage` exists to prevent."""
    store = FakeS3(credential=KEY, region="auto").holding("assets", {"brain/x": b"1"})
    with pytest.raises(StoreUnansweredError, match="SignatureDoesNotMatch"):
        backend_over(store).get_object("assets", "brain/x")
    r2 = S3Backend(
        config_for(Backend.CLOUDFLARE_R2, endpoint_url=ENDPOINT), KEY, transport=store.transport()
    )
    assert r2.get_object("assets", "brain/x") == b"1"


def test_a_refusal_names_the_code_and_never_the_key_it_was_about() -> None:
    """A key can say what a file is about. Delete this and a message built from the store's body or
    the key lands in a log line or a screen."""
    store = FakeS3(credential=KEY).holding("assets", {})
    with pytest.raises(StoreUnansweredError) as raised:
        backend_over(store).get_object("assets", "brain/salary-review-2026")
    assert "NoSuchKey" in str(raised.value)
    assert "salary" not in str(raised.value)


def test_a_store_that_does_not_answer_is_raised_as_unanswered_and_not_as_a_transport_error() -> (
    None
):
    """Delete this and an `httpx` exception reaches a screen as a 500, because the routes catch the
    protocol's error and not a client library's."""
    store = FakeS3(credential=KEY, down=True)
    with pytest.raises(StoreUnansweredError, match="did not answer"):
        backend_over(store).get_object("assets", "brain/x")


def test_the_secret_is_rendered_by_neither_the_credential_nor_the_backend() -> None:
    """Delete this and an exception handler formatting either object writes the key to the log."""
    backend = backend_over(FakeS3(credential=KEY))
    for shown in (repr(KEY), str(KEY), repr(backend), str(backend)):
        assert KEY.secret_access_key not in shown
    assert KEY.access_key_id in repr(KEY)


def test_a_credential_with_whitespace_or_nothing_in_it_is_refused() -> None:
    """A key pasted with a line break signs every request wrong. Delete this and it is found as a
    403 rather than at start."""
    for access, secret in (("", "s"), ("a", ""), ("a b", "s"), ("a", "s\n")):
        with pytest.raises(StorageError):
            StoreCredential(access_key_id=access, secret_access_key=secret)


def test_an_address_carrying_a_user_and_password_sends_neither() -> None:
    """Delete this and credentials written into the endpoint setting travel in every Host header."""
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["host"] + str(request.url))
        return httpx.Response(200, content=b"x")

    backend = S3Backend(
        config_for(Backend.SEAWEEDFS, endpoint_url="http://user:hunter2@objects.example.test:8333"),
        KEY,
        transport=httpx.MockTransport(handle),
    )
    backend.get_object("assets", "brain/x")
    assert seen == ["objects.example.test:8333http://objects.example.test:8333/assets/brain/x"]


def test_usage_counts_every_page_under_the_prefix_and_carries_no_name() -> None:
    """Five objects over pages of two, one of them another install's. Delete this and a count of the
    first page, or of the whole bucket, is drawn as this install's usage."""
    store = FakeS3(credential=KEY, page=2).holding(
        "assets",
        {f"brain/{n}": b"x" * n for n in range(1, 6)} | {"other/1": b"y" * 100},
    )
    counted = backend_over(store).usage("assets", "brain/")
    assert (counted.objects, counted.bytes_stored, counted.complete) == (5, 15, True)
    assert set(vars(counted)) == {"objects", "bytes_stored", "complete"}
    assert sum(1 for method, _, _ in store.asked if method == "GET") == 3


def test_usage_stops_at_the_ceiling_and_says_the_figure_is_a_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and a bucket of millions is listed to the end on every opening of a screen, or a
    floor is drawn as a total."""
    monkeypatch.setattr(object_store, "USAGE_CEILING_OBJECTS", 4)
    store = FakeS3(credential=KEY, page=2).holding("assets", {f"brain/{n}": b"x" for n in range(9)})
    counted = backend_over(store).usage("assets", "brain/")
    assert (counted.objects, counted.complete) == (4, False)
    monkeypatch.setattr(object_store, "USAGE_CEILING_OBJECTS", 18)
    assert backend_over(store).usage("assets", "brain/").complete is True


def test_the_usage_ceiling_is_whole_pages_of_the_largest_page_s3_serves() -> None:
    """Held against S3's own page maximum rather than a restated number. Delete this and a ceiling
    below one page stops counting before the first page is read."""
    assert LIST_PAGE == 1000
    assert USAGE_CEILING_OBJECTS >= LIST_PAGE
    assert USAGE_CEILING_OBJECTS % LIST_PAGE == 0


# ------------------------------------------------------------------ built at start


class Vault:
    """A vault answering one slot or raising what it was told to, recording what it was asked."""

    def __init__(self, fields: dict[str, Any] | Exception) -> None:
        self.fields = fields
        self.asked: list[str] = []

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.asked.append(path)
        if isinstance(self.fields, Exception):
            raise self.fields
        return self.fields


def start(vault: Vault, settings: dict[str, str] = SETTINGS, **kw: Any) -> object_store.ObjectStore:
    return object_store_at_start(
        "http://vault.example.test:8200",
        "a-token",
        env=settings,
        saved={},
        make_vault=lambda _address, _token: vault,
        **kw,
    )


def test_a_store_is_built_from_the_settings_and_the_backends_own_vault_slot() -> None:
    """The positive case, reaching a store that checks the key. Delete this and every refusal below
    is satisfied by a function that never connects."""
    vault = Vault(SLOT)
    store = FakeS3(credential=KEY).holding("assets", {"brain/x": b"1"})
    built = start(vault, transport=store.transport())
    assert built.backend is not None
    assert (built.prefix, built.unconnected) == ("brain", "")
    assert built.backend.get_object("assets", "brain/x") == b"1"
    assert vault.asked == [credential_path(Backend.SEAWEEDFS)]
    r2 = Vault(SLOT)
    start(r2, {**SETTINGS, BACKEND_SETTING: "cloudflare_r2"})
    assert r2.asked == [credential_path(Backend.CLOUDFLARE_R2)]


def test_with_no_vault_nothing_is_built_and_the_reason_is_said() -> None:
    """Delete this and an install with no vault reads a key from somewhere else, or says nothing."""
    built = object_store_at_start("", "", env=SETTINGS, saved={})
    assert (built.backend, built.unconnected) == (None, NO_VAULT_SO_NO_STORE_CREDENTIAL)
    half = object_store_at_start("http://vault.example.test:8200", "", env=SETTINGS, saved={})
    assert half.unconnected == NO_VAULT_SO_NO_STORE_CREDENTIAL


def test_aws_s3_is_not_built_from_a_lease_and_the_vault_is_not_asked() -> None:
    """Delete this and a client built from a lease works until the lease expires and then refuses
    everything with a message about the key."""
    vault = Vault(SLOT)
    built = start(vault, {**SETTINGS, BACKEND_SETTING: "aws_s3"})
    assert (
        built.unconnected == A_LEASE_NOBODY_RENEWS_IS_A_CREDENTIAL_THAT_STOPS_WORKING_ON_A_SCHEDULE
    )
    assert vault.asked == []


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        (VaultRefusedError("no slot", status=404), THE_STORE_SLOT_HOLDS_NO_KEY),
        (VaultRefusedError("policy", status=403), THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY),
        (VaultUnreachableError("silent"), THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY),
        ({}, THE_STORE_SLOT_HOLDS_NO_KEY),
        ({ACCESS_KEY_FIELD: "a"}, THE_STORE_SLOT_IS_NOT_A_KEY_PAIR),
        ({ACCESS_KEY_FIELD: "a", SECRET_KEY_FIELD: 7}, THE_STORE_SLOT_IS_NOT_A_KEY_PAIR),
        ({ACCESS_KEY_FIELD: "a", SECRET_KEY_FIELD: "b c"}, THE_STORE_SLOT_IS_NOT_A_KEY_PAIR),
    ],
)
def test_every_way_the_vault_does_not_hand_over_a_key_is_a_sentence_and_not_a_raise(
    fields: dict[str, Any] | Exception, said: str
) -> None:
    """Delete this and a vault that refuses at start stops the process, which is every screen."""
    built = start(Vault(fields))
    assert (built.backend, built.unconnected) == (None, said)


@pytest.mark.parametrize(
    ("settings", "said"),
    [
        ({**SETTINGS, BACKEND_SETTING: "minio"}, THE_BACKEND_SETTING_NAMES_NO_BACKEND),
        ({**SETTINGS, PREFIX_SETTING: "../elsewhere"}, THE_STORE_SETTINGS_ARE_REFUSED),
        ({**SETTINGS, PREFIX_SETTING: "a/b"}, THE_STORE_SETTINGS_ARE_REFUSED),
        ({**SETTINGS, ENDPOINT_SETTING: "objects.example.test"}, THE_STORE_SETTINGS_ARE_REFUSED),
    ],
)
def test_settings_nothing_could_be_built_from_are_refused_before_the_vault_is_asked(
    settings: dict[str, str], said: str
) -> None:
    """A prefix with a slash or a climb lets a key leave the namespace two installs share. Delete
    this and the vault hands its key to a client that was never going to work."""
    vault = Vault(SLOT)
    assert start(vault, settings).unconnected == said
    assert vault.asked == []


def test_every_backend_connected_from_a_stored_key_has_its_slot_in_the_operators_guide() -> None:
    """The guide and the code name the same slot for every backend whose key is stored, and the one
    whose key is leased has none. Delete this and an operator fills a slot nothing reads, and the
    screen says the slot is empty."""
    from tests.unit.test_vault_policies import _slot_paths

    slots = _slot_paths()
    for backend in Backend:
        path = credential_path(backend)
        if path.startswith("providers/"):
            assert path in slots, backend
        else:
            assert path not in slots, backend


def test_the_default_install_is_seaweedfs_at_the_address_the_compose_file_names() -> None:
    """Delete this and the backend default drifts from the store the product ships."""
    vault = Vault(SLOT)
    built = start(vault, {})
    assert built.backend is not None
    assert vault.asked == [credential_path(Backend.SEAWEEDFS)]


# ------------------------------------------------------------------ the backup bucket


def test_the_backup_reader_fetches_descriptions_and_never_a_copy() -> None:
    """Delete this and opening the recovery screen pulls every nightly copy of the database into
    the web process."""
    bucket = bucket_for(ObjectKind.DATABASE_DUMP).name
    store = FakeS3(credential=KEY).holding(
        bucket,
        {
            "database-20260901T020000Z.dump": b"\x00" * 64,
            f"database-20260901T020000Z{MANIFEST_SUFFIX}": b'{"backup_id": "one"}',
            f"drill-20260902T030000Z{DRILL_SUFFIX}": b"\xff not utf-8",
        },
    )
    read = backup_objects(backend_over(store))()
    assert dict(read) == {
        f"database-20260901T020000Z{MANIFEST_SUFFIX}": '{"backup_id": "one"}',
        f"drill-20260902T030000Z{DRILL_SUFFIX}": "� not utf-8",
    }
    fetched = [path for method, path, query in store.asked if method == "GET" and not query]
    assert not any(path.endswith(".dump") for path in fetched)
    assert len(fetched) == 2
