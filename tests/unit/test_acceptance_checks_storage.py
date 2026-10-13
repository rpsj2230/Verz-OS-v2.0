"""The storage install checks: registered, passing on a stand-in store and able to fail.

The three checks read the bucket declaration, build either backend through the application's own
start function, and put an object in the install's own store. None needs a database for its
body, so each runs here against a stub harness and, where it touches a store, against
`tests.fixtures.fake_s3.FakeS3`, which verifies every signature it is sent. One run as the worker
runs them proves the module is found and places itself.

Task ids: M32.3.1.1, M32.3.1.2, M32.3.1.3, M32.3.1.4, M32.3.2.1, M32.3.2.2
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops import acceptance_checks_storage as module
from brain.ops import object_store, storage
from brain.ops.acceptance import REASON_CHARS, CheckFailedError, CheckNotRunError, registered
from brain.ops.object_store import ObjectStore, S3Backend, StoreCredential
from brain.ops.storage import Backend, config_for
from tests.fixtures.fake_s3 import FakeS3
from tests.unit.test_acceptance import checks_in

MODULE = "brain.ops.acceptance_checks_storage"
LAYOUT = "the_decided_buckets_keep_their_lifecycles_and_none_is_public"
EITHER = "either_store_is_built_from_its_own_vault_slot"
LIVE = "the_install_s_own_store_keeps_and_returns_an_object"

LEAVES = {
    LAYOUT: ("M32.3.1.2", "M32.3.1.3"),
    EITHER: ("M32.3.2.1", "M32.3.2.2"),
    LIVE: ("M32.3.1.1", "M32.3.1.2", "M32.3.1.4"),
}
CREDENTIAL = StoreCredential(access_key_id="AKACCEPTANCE", secret_access_key="s" * 40)


class _Harness(SimpleNamespace):
    """What the three bodies ask of a harness: settings, a word and an undo list."""

    def __init__(self) -> None:
        super().__init__(
            settings=SimpleNamespace(vault_address="http://vault.invalid", vault_token="t"),
            undone=[],
        )

    def word(self) -> str:
        return "QZ0123456789ABCDEF"

    def removes(self, undo: Any) -> None:
        self.undone.append(undo)


def body(name: str) -> Any:
    return next(one for one in registered((MODULE,)) if one.name == name).run


def run(name: str, harness: Any = None) -> None:
    asyncio.run(body(name)(harness or _Harness()))


def a_store(fake: FakeS3) -> ObjectStore:
    config = config_for(Backend.SEAWEEDFS, endpoint_url="http://objects.invalid:8333")
    return ObjectStore(
        backend=S3Backend(config, CREDENTIAL, transport=fake.transport()), prefix="p"
    )


def connected(monkeypatch: pytest.MonkeyPatch, made: ObjectStore) -> None:
    monkeypatch.setattr(object_store, "object_store_at_start", lambda *_a, **_k: made)


def test_the_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Delete this and a check can close a leaf it does not exercise, or the stand-in check can
    be given the live leaf that only a connected store proves."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == LEAVES
    assert checks_in(MODULE) == list(LEAVES)
    assert 700 <= module.CHECK_ORDER <= 799


def test_every_reason_the_module_ends_a_check_with_fits_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(module.NO_STORE_IS_CONNECTED) <= REASON_CHARS


def test_the_layout_check_passes_on_the_declaration_the_product_carries() -> None:
    """The positive case. Delete this and a check that refuses everything passes the rest."""
    run(LAYOUT)


@pytest.mark.parametrize(
    "broken",
    [
        lambda one: replace(one, public_read=True) if one.name == "assets" else one,
        lambda one: replace(one, versioned=False) if one.name == "backups" else one,
        lambda one: replace(one, retention_days=None) if one.name == "exports" else one,
        lambda one: replace(one, name="archive") if one.name == "recordings" else one,
    ],
)
def test_the_layout_check_fails_where_the_declaration_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: Any
) -> None:
    """A bucket made public, copies left unversioned, exports kept for ever and a bucket renamed.
    Delete this and the leaves close on a declaration nothing could tell had been relaxed."""
    monkeypatch.setattr(storage, "BUCKETS", tuple(broken(one) for one in storage.BUCKETS))
    with pytest.raises(CheckFailedError):
        run(LAYOUT)


def test_the_layout_check_fails_where_a_kind_of_object_lands_in_the_wrong_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exports filed under assets. Delete this and a compliance export can share a console logo's
    lifecycle with the check green."""
    real = storage.bucket_for

    def misfiled(kind: storage.ObjectKind) -> storage.Bucket:
        return (
            storage.bucket("assets") if kind is storage.ObjectKind.COMPLIANCE_EXPORT else real(kind)
        )

    monkeypatch.setattr(storage, "bucket_for", misfiled)
    with pytest.raises(CheckFailedError, match="decided one"):
        run(LAYOUT)


def test_either_store_check_passes_for_both_backends() -> None:
    """The positive case, which builds SeaweedFS and R2 through the application's own start
    function. Delete this and the check can be satisfied by one that builds nothing."""
    run(EITHER)


def test_either_store_check_fails_where_the_key_is_read_from_the_wrong_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The R2 slot pointing at the SeaweedFS one. Delete this and a store can borrow another
    backend's key with the check green."""
    real = storage.credential_path
    monkeypatch.setattr(
        storage,
        "credential_path",
        lambda backend: real(Backend.SEAWEEDFS if backend is Backend.CLOUDFLARE_R2 else backend),
    )
    with pytest.raises(CheckFailedError, match="slot other than"):
        run(EITHER)


def test_either_store_check_fails_where_r2_is_given_a_real_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`config_for` accepting any region for R2. Delete this and the 403 that reads as a bad key
    is back with the leaf closed."""
    real = storage.config_for

    def lenient(backend: Backend, *, endpoint_url: str, region: str | None = None) -> Any:
        return real(
            Backend.SEAWEEDFS if backend is Backend.CLOUDFLARE_R2 and region else backend,
            endpoint_url=endpoint_url,
            region=region,
        )

    monkeypatch.setattr(module, "config_for", lenient, raising=False)
    monkeypatch.setattr(storage, "config_for", lenient)
    with pytest.raises(CheckFailedError, match="R2 was accepted"):
        run(EITHER)


def test_the_live_check_puts_reads_and_deletes_in_each_bucket_and_leaves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case over a store that verifies every signature. Delete this and the check
    can pass without an object ever reaching a store."""
    fake = FakeS3(CREDENTIAL)
    for name in ("assets", "recordings", "exports", "backups"):
        fake.holding(name, {})
    connected(monkeypatch, a_store(fake))
    run(LIVE)
    assert all(not objects for objects in fake.buckets.values())
    assert {method for method, _, _ in fake.asked} == {"PUT", "GET", "DELETE"}


def test_the_live_check_is_not_run_where_no_store_is_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store nobody connected is a state, not a fault. Delete this and an install with no store
    is recorded as failing a check that was never asked."""
    connected(monkeypatch, object_store.unconnected("no key"))
    with pytest.raises(CheckNotRunError, match="no object store"):
        run(LIVE)


def test_the_live_check_fails_where_a_bucket_of_the_layout_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store with no recordings bucket. Delete this and an install provisioned without one of
    the four passes its layout leaf."""
    fake = FakeS3(CREDENTIAL)
    for name in ("assets", "exports", "backups"):
        fake.holding(name, {})
    connected(monkeypatch, a_store(fake))
    with pytest.raises(CheckFailedError, match="did not answer"):
        run(LIVE)


def test_the_live_check_fails_where_the_store_keeps_an_object_it_was_told_to_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store ignoring deletes. Delete this and a store that never forgets passes."""

    class Keeps(FakeS3):
        def handle(self, request: Any) -> Any:
            import httpx

            if request.method == "DELETE":
                return httpx.Response(204)
            return super().handle(request)

    fake = Keeps(CREDENTIAL)
    for name in ("assets", "recordings", "exports", "backups"):
        fake.holding(name, {})
    connected(monkeypatch, a_store(fake))
    with pytest.raises(CheckFailedError, match="still returned"):
        run(LIVE)
