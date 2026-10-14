"""The application's object store key, handed over by the release and read back at start.

The producer is `keep_credential`, run inside the application by the object store overlay's hand
step, and the consumer is `object_store_at_start`, which reads the slot when a process starts. One
test for each is two tests for the consumer, so the round trip below writes with the first and
builds with the second against a store that checks the signature: the failure it exists to catch
is a slot written in a shape, or at a path, the reader does not read, which both halves' own
tests would pass.

Task ids: M32.3.1.4, M32.3.1.1
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.ops.object_store import (
    ACCESS_KEY_FIELD,
    BACKEND_SETTING,
    ENDPOINT_SETTING,
    PREFIX_SETTING,
    SECRET_KEY_FIELD,
    StoreCredential,
    credential_from,
    keep_credential,
    main,
    object_store_at_start,
)
from brain.ops.storage import Backend, StorageError, credential_path
from tests.fixtures.fake_s3 import FakeS3

ENDPOINT = "http://objects.example.test:8333"
SETTINGS = {ENDPOINT_SETTING: ENDPOINT, PREFIX_SETTING: "brain", BACKEND_SETTING: "seaweedfs"}
KEY = StoreCredential(access_key_id="handed-access-key", secret_access_key="handed-secret-key-1")
KEPT_AT = datetime(2019, 1, 1, tzinfo=UTC)


class Vault:
    """A vault that keeps what is written to it and answers reads from the same place."""

    def __init__(self) -> None:
        self.slots: dict[str, dict[str, str]] = {}

    def write_static_kv(self, path: str, fields: Any) -> datetime:
        self.slots[path] = dict(fields)
        return KEPT_AT

    def read_static_kv(self, path: str) -> dict[str, Any]:
        return dict(self.slots.get(path, {}))

    def static_kv_version(self, path: str) -> None:
        del path


def test_a_key_kept_by_the_release_is_the_key_the_application_builds_its_client_from() -> None:
    """The round trip through a store that verifies every signature: write with `keep_credential`,
    build with `object_store_at_start`, read an object. Delete this and the hand step can write a
    slot the application never reads, so the store runs, the key exists, and every upload reports
    that the slot holds no key."""
    vault = Vault()
    keep_credential(vault, KEY)
    store = FakeS3(credential=KEY).holding("assets", {"brain/x": b"1"})

    built = object_store_at_start(
        "http://vault.example.test:8200",
        "a-token",
        env=SETTINGS,
        saved={},
        make_vault=lambda _address, _token: vault,
        transport=store.transport(),
    )

    assert built.backend is not None, built.unconnected
    assert built.backend.get_object("assets", "brain/x") == b"1"


def test_the_key_is_kept_at_the_object_store_s_own_slot_and_no_other() -> None:
    """The slot is the backend's, named by the storage module and described in
    `ops/openbao/credential-slots.md` as `providers/seaweedfs`, and the two fields are the ones
    the reader names. Delete this and a rename of the slot in one place leaves the other writing
    where nothing reads. The slot is also written out here, since a constant compared with itself
    is true of every value it could hold."""
    vault = Vault()
    keep_credential(vault, KEY)

    assert list(vault.slots) == [credential_path(Backend.SEAWEEDFS)] == ["providers/seaweedfs"]
    assert vault.slots["providers/seaweedfs"] == {
        ACCESS_KEY_FIELD: KEY.access_key_id,
        SECRET_KEY_FIELD: KEY.secret_access_key,
    }
    assert ACCESS_KEY_FIELD == "access_key_id"
    assert SECRET_KEY_FIELD == "secret_access_key"


def test_the_pair_is_the_two_lines_the_hand_step_writes_and_nothing_else() -> None:
    """Exactly two non-empty lines, access key then secret. Delete this and a hand-over that lost
    a line is kept as a pair whose secret is the access key, and the store refuses every request."""
    assert credential_from(["handed-access-key\n", "handed-secret-key-1\n", "\n"]) == KEY
    for lines in ([], ["only-one-line"], ["a", "b", "c"], ["", ""]):
        with pytest.raises(StorageError):
            credential_from(lines)


def test_the_command_keeps_the_pair_from_standard_input_and_says_only_whether_it_did(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the hand step runs, with the vault replaced: the pair on standard input is kept, the
    journal line says so, and the secret is in neither output. Delete this and the command can
    print the key it was handed, or exit 0 without keeping it."""
    vault = Vault()
    monkeypatch.setattr("sys.stdin", io.StringIO("handed-access-key\nhanded-secret-key-1\n"))
    monkeypatch.setattr(
        "brain.ops.object_store.OpenBaoVault", lambda *_args, **_kw: vault, raising=True
    )
    monkeypatch.setenv("BRAIN_VAULT_ADDRESS", "http://vault.example.test:8200")
    monkeypatch.setenv("BRAIN_VAULT_TOKEN", "a-token-not-printed")

    assert main(["keep"]) == 0

    seen = capsys.readouterr()
    assert seen.out.strip() == "SAY the object store's key is kept in the vault"
    assert "handed-secret-key-1" not in seen.out + seen.err
    assert vault.slots["providers/seaweedfs"][SECRET_KEY_FIELD] == "handed-secret-key-1"


def test_the_command_says_why_it_kept_nothing_and_exits_non_zero_without_the_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No vault, or a malformed hand-over, is a sentence for the journal and a non-zero exit that
    makes the step say it will try again, never a traceback with the pair in it. Delete this and a
    server with no vault reads, in the deploy's journal, as an application that was handed a key."""
    monkeypatch.setattr("sys.stdin", io.StringIO("handed-access-key\nhanded-secret-key-1\n"))
    monkeypatch.delenv("BRAIN_VAULT_ADDRESS", raising=False)
    monkeypatch.delenv("BRAIN_VAULT_TOKEN", raising=False)

    assert main(["keep"]) == 1

    said = capsys.readouterr().out
    assert said.startswith("SAY the object store's key was not kept")
    assert "handed-secret-key-1" not in said
    assert main(["other"]) == 64
