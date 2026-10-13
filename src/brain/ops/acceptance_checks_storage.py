"""Install acceptance checks for where files go: the four buckets, their lifecycles, the stores.

`brain.ops.storage` decides the bucket set, each bucket's retention and why, and which backends a
client may choose; `brain.ops.object_store` speaks S3 to the store and builds itself at start from
three installation settings and one vault slot. Their tests hold each rule alone. What nothing
showed on an install is the sentence a client reads: **the decided layout is what the running
product carries, and a store connected the way the application connects it answers.**

**Three checks, and what each one is worth.**

1. The declared buckets are the four decided, every kind of object lands in the one decided for
   it, no bucket is public and the lifecycle guard fires when a copy of the declaration is broken
   three ways. It reads the code the install is running and writes nothing, so it is proof of the
   declaration and not of the live store's own lifecycle rules, which no call this client makes can
   read.
2. **Either store a client may choose is built from its own vault slot and answers the same
   calls.** The application's own start function is run twice, once for SeaweedFS and once for
   Cloudflare R2, over a vault stand-in that remembers which slot it was asked for and a transport
   that keeps what it was sent and answers as S3 does. This is **made up** (the vault, the store and
   the keys), so the leaves it names are held in `docs/proof-sweep-holds.json` until an install
   runs on the other backend: the pass shows the install's own code behaves as the sentence says.
3. **The install's own store keeps and returns an object.** The store is built exactly as the
   application builds it, from this install's settings and its own vault, and an object is put in
   each bucket that keeps files, read back, deleted and shown gone; the backup bucket, which holds
   copies and is versioned, is only listed. An install that connects no store is recorded as not
   run: a store nobody connected is a Storage screen that says so, not a defect in the product.

**Rejected: putting the canary in the backup bucket.** It is versioned so that a job writing a
corrupt copy cannot destroy the good one, which also means a deleted object stays as a version, so
a test object written there could not be removed by name.

**Rejected: restating the retention figures here.** A check holding 30 and 90 and 35 days fails
when the owner changes a figure on purpose, which teaches people to change the check. The rule
that is decided is the structure (a bucket of copies is versioned, a bucket of screen captures and
exports expires, none is public, every one gives its reason), and that is what is asserted.

Task ids: M32.3.1.1, M32.3.1.2, M32.3.1.3, M32.3.1.4, M32.3.2.1, M32.3.2.2
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Any, Final

import httpx

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 710

# ------------------------------------------------------------------------ the figures
#: The four buckets the owner's layout names, restated as words rather than read off the module
#: that declares them, so a fifth or a rename fails here instead of moving with the product.
THE_DECIDED_BUCKETS: Final = frozenset({"assets", "recordings", "exports", "backups"})

#: Which bucket each kind of object is decided to live in, as words.
WHERE_EACH_KIND_LIVES: Final = {
    "console_asset": "assets",
    "agent_attachment": "assets",
    "knowledge_original": "assets",
    "agent_artifact": "assets",
    "browser_run_recording": "recordings",
    "compliance_export": "exports",
    "database_dump": "backups",
}

#: The buckets an object is put in and read back from. The backup bucket is only listed.
BUCKETS_THE_LIVE_CHECK_WRITES_IN: Final = ("assets", "recordings", "exports")

#: The reason a result is given when this install connects no store.
NO_STORE_IS_CONNECTED: Final = (
    "this install connects no object store (no vault, no key in its slot or no backend this "
    "release reaches), so there was nothing to put an object in"
)

# ------------------------------------------------------------------ written-down reasons
#: Why the stand-in vault is the one the check reads, and what it never holds.
THE_STAND_INS_HOLD_KEYS_ONLY_THE_CHECK_MADE: Final = (
    "The vault, the store and both key pairs of the stand-in check are made in memory for it. "
    "Nothing is sent to a socket and no key the install holds is read, so the pass shows the "
    "product's own start function and client behave as written and shows nothing about a store "
    "of the owner's."
)


# ------------------------------------------------------------------ 1. the layout
@check(
    leaves=("M32.3.1.2", "M32.3.1.3"),
    sentence=(
        "The product carries the four decided buckets (assets, recordings, exports, backups), "
        "every kind of object lands in the one decided for it, none is public, a bucket of "
        "copies is versioned, one of captures and exports expires and each gives its reason, and "
        "the lifecycle guard names each of three ways a copy of the declaration is broken."
    ),
)
async def the_decided_buckets_keep_their_lifecycles_and_none_is_public(h: Harness) -> None:
    from brain.ops.storage import BUCKETS, ObjectKind, bucket_for, lifecycle_gaps

    names = tuple(one.name for one in BUCKETS)
    if set(names) != THE_DECIDED_BUCKETS or len(set(names)) != len(names):
        raise CheckFailedError("the product's buckets are not the four the owner decided")
    if {one.value for one in ObjectKind} != set(WHERE_EACH_KIND_LIVES):
        raise CheckFailedError(
            "a kind of object has no decided bucket, or one was decided for none"
        )
    for kind in ObjectKind:
        if bucket_for(kind).name != WHERE_EACH_KIND_LIVES[kind.value]:
            raise CheckFailedError("a kind of object lands in a bucket other than its decided one")
    by_name = {one.name: one for one in BUCKETS}
    if any(one.public_read or not one.retention_reason.strip() for one in BUCKETS):
        raise CheckFailedError("a bucket is public or gives no reason for its retention")
    if not by_name["backups"].versioned or by_name["backups"].retention_days is None:
        raise CheckFailedError("the bucket of copies is not versioned, or keeps them for ever")
    if by_name["recordings"].retention_days is None or by_name["exports"].retention_days is None:
        raise CheckFailedError("a bucket of screen captures or exports keeps its files for ever")
    if lifecycle_gaps() != ():
        raise CheckFailedError("the product's own lifecycle guard finds a gap in its declaration")
    breaks = (
        replace(by_name["assets"], public_read=True),
        replace(by_name["backups"], versioned=False),
        replace(by_name["exports"], retention_days=None),
    )
    if any(len(lifecycle_gaps((one,))) != 1 for one in breaks):
        raise CheckFailedError(
            "the lifecycle guard misses a bucket made public, unversioned or kept"
        )


# --------------------------------------------------------------- 2. either store, made up
class _Vault:
    """`brain.ops.object_store.StaticKvReader` that remembers which slot it was asked for."""

    def __init__(self, fields: dict[str, Any]) -> None:
        self.fields = fields
        self.asked: list[str] = []

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.asked.append(path)
        return self.fields


def _handed(vault: _Vault, _address: str, _token: str) -> _Vault:
    """The vault the start function is told to build, whatever address and token it names."""
    return vault


@dataclass
class _Store:
    """An S3 stand-in: keeps what it was sent and answers a put, a get and a delete."""

    held: dict[str, bytes] = field(default_factory=dict)
    sent: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        where = request.url.path
        if request.method == "PUT":
            self.held[where] = request.content
            return httpx.Response(200)
        if request.method == "GET" and where in self.held:
            return httpx.Response(200, content=self.held[where])
        if request.method == "DELETE":
            self.held.pop(where, None)
            return httpx.Response(204)
        return httpx.Response(404, content=b"<Error><Code>NoSuchKey</Code></Error>")


def _carried(request: httpx.Request) -> bytes:
    """Everything a request carries that a secret could ride in: its address, headers and body."""
    headers = "".join(f"{key}:{value}" for key, value in request.headers.items())
    return f"{request.url}{headers}".encode() + request.content


@check(
    leaves=("M32.3.2.1", "M32.3.2.2"),
    sentence=(
        "With the store set to SeaweedFS and then to Cloudflare R2, the application's own start "
        "reads each backend's own vault slot and nothing else, signs for that backend's region, "
        "puts, reads and deletes an object through one client with the secret in no request, and "
        "refuses R2 with a real region, AWS S3 and an empty slot, each in words."
    ),
)
async def either_store_is_built_from_its_own_vault_slot(
    h: Harness,
) -> None:
    from brain.ops.object_store import (
        ACCESS_KEY_FIELD,
        BACKEND_SETTING,
        ENDPOINT_SETTING,
        PREFIX_SETTING,
        SECRET_KEY_FIELD,
        THE_STORE_SLOT_HOLDS_NO_KEY,
        object_store_at_start,
    )
    from brain.ops.openbao import STATIC_PREFIX
    from brain.ops.storage import Backend, StorageError, config_for

    def settings(backend: Backend, endpoint: str) -> dict[str, str]:
        return {
            BACKEND_SETTING: backend.value,
            ENDPOINT_SETTING: endpoint,
            PREFIX_SETTING: "acceptance",
        }

    # (backend, an address that never resolves, the region the signature must be scoped to, and
    # the vault slot the key is kept in, written here as words and not read back from the product)
    wanted = (
        (Backend.SEAWEEDFS, "http://objects.acceptance.invalid:8333", "us-east-1", "seaweedfs"),
        (
            Backend.CLOUDFLARE_R2,
            "https://acceptance.r2.acceptance.invalid",
            "auto",
            "cloudflare-r2",
        ),
    )
    for backend, endpoint, region, slot in wanted:
        access, secret = f"AK{secrets.token_hex(8).upper()}", secrets.token_hex(20)
        vault = _Vault({ACCESS_KEY_FIELD: access, SECRET_KEY_FIELD: secret})
        stand_in = _Store()
        built = await asyncio.to_thread(
            object_store_at_start,
            "http://vault.acceptance.invalid",
            "acceptance-token",
            env=settings(backend, endpoint),
            saved={},
            make_vault=partial(_handed, vault),
            transport=httpx.MockTransport(stand_in.handle),
        )
        if built.backend is None:
            raise CheckFailedError(
                "the application's start built no store from a slot holding a key"
            )
        if vault.asked != [f"{STATIC_PREFIX}{slot}"]:
            raise CheckFailedError(
                "the store's key was read from a slot other than its backend's own"
            )
        body = secrets.token_bytes(24)
        await asyncio.to_thread(
            built.backend.put_object, "assets", "acceptance/one", body, "text/plain"
        )
        if await asyncio.to_thread(built.backend.get_object, "assets", "acceptance/one") != body:
            raise CheckFailedError("an object put in the store was not read back as it was put")
        await asyncio.to_thread(built.backend.delete_object, "assets", "acceptance/one")
        if [one.method for one in stand_in.sent] != ["PUT", "GET", "DELETE"]:
            raise CheckFailedError("the client made calls other than the put, get and delete asked")
        for one in stand_in.sent:
            signed = one.headers.get("authorization", "")
            if not signed.startswith(f"AWS4-HMAC-SHA256 Credential={access}/"):
                raise CheckFailedError(
                    "a request was not signed with the key the vault handed over"
                )
            if f"/{region}/s3/aws4_request" not in signed:
                raise CheckFailedError("a request was signed for a region other than its backend's")
            if secret.encode() in _carried(one):
                raise CheckFailedError("the store's secret key travelled in a request")
            if not one.url.path.startswith("/assets/"):
                raise CheckFailedError("a bucket was not addressed by path on a path-style backend")
        if hashlib.sha256(body).hexdigest() != stand_in.sent[0].headers["x-amz-content-sha256"]:
            raise CheckFailedError("a request's payload hash is not the hash of what it carried")

    try:
        config_for(
            Backend.CLOUDFLARE_R2, endpoint_url="https://r2.acceptance.invalid", region="eu-west-1"
        )
    except StorageError:
        pass
    else:
        raise CheckFailedError("R2 was accepted with a region it does not have")
    try:
        config_for(Backend.AWS_S3, endpoint_url="https://s3.acceptance.invalid")
    except StorageError:
        pass
    else:
        raise CheckFailedError("AWS S3 was accepted with no region")
    leased = await asyncio.to_thread(
        object_store_at_start,
        "http://vault.acceptance.invalid",
        "acceptance-token",
        env=settings(Backend.AWS_S3, "https://s3.acceptance.invalid"),
        saved={},
        make_vault=lambda _a, _t: _Vault({}),
    )
    empty = await asyncio.to_thread(
        object_store_at_start,
        "http://vault.acceptance.invalid",
        "acceptance-token",
        env=settings(Backend.SEAWEEDFS, "http://objects.acceptance.invalid:8333"),
        saved={},
        make_vault=lambda _a, _t: _Vault({}),
    )
    if leased.backend is not None or not leased.unconnected:
        raise CheckFailedError("a store whose key is a lease nobody renews was connected")
    if empty.backend is not None or empty.unconnected != THE_STORE_SLOT_HOLDS_NO_KEY:
        raise CheckFailedError("a slot holding no key was connected, or was not said to hold none")


# ---------------------------------------------------------------- 3. the install's own store
@check(
    leaves=("M32.3.1.1", "M32.3.1.2", "M32.3.1.4"),
    sentence=(
        "The object store connected as the application connects it, from this install's settings "
        "and its own vault, keeps an object in each of assets, recordings and exports, returns it "
        "as it was put, deletes it so it is gone, and answers a listing of the backup bucket."
    ),
)
async def the_install_s_own_store_keeps_and_returns_an_object(h: Harness) -> None:
    from brain.ops.object_store import key_prefix, object_store_at_start
    from brain.ops.storage import StorageError, StoreUnansweredError

    store = await asyncio.to_thread(
        object_store_at_start, h.settings.vault_address, h.settings.vault_token
    )
    backend = store.backend
    if backend is None:
        raise CheckNotRunError(NO_STORE_IS_CONNECTED)
    word = h.word()
    for name in BUCKETS_THE_LIVE_CHECK_WRITES_IN:
        key = f"{key_prefix(name, store.prefix)}acceptance/{word}"
        body = f"acceptance {word}".encode()
        try:
            await asyncio.to_thread(backend.put_object, name, key, body, "text/plain")
            h.removes(partial(backend.delete_object, name, key))
            if await asyncio.to_thread(backend.get_object, name, key) != body:
                raise CheckFailedError("the store returned an object other than the one put in it")
            await asyncio.to_thread(backend.delete_object, name, key)
        except StoreUnansweredError as exc:
            raise CheckFailedError(
                "a bucket of the decided layout did not answer the connected store"
            ) from exc
        try:
            await asyncio.to_thread(backend.get_object, name, key)
        except StorageError:
            continue
        raise CheckFailedError("an object deleted from the store was still returned")
    try:
        await asyncio.to_thread(lambda: list(backend.list_objects("backups", "acceptance/")))
    except StorageError as exc:
        raise CheckFailedError("the backup bucket did not answer a listing") from exc
