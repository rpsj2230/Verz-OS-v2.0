"""The Storage screen over HTTP: the buckets this product keeps, how long each keeps what, why, and
how much each holds now.

`brain.ops.storage` declares the object store's shape: four buckets, each with what it holds, a
retention and the reason for it, whether it is versioned, and a check that none is public.
`brain.ops.object_store` is the client the process builds at start, or the sentence saying why it
built none. This serves both, with the settings that say where the store is.

**Usage is measured when a store is connected, and each bucket says which it is.** A bucket row
carries either the objects and bytes this install holds there or the sentence saying why they were
not counted: no store on this process, or a store that did not answer for that bucket. A bucket
that failed is not drawn as empty beside three that counted, which is
`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE` one row at a time. The count stops at
`brain.ops.object_store.USAGE_CEILING_OBJECTS` and says the figure is a floor. See
`USAGE_IS_COUNTED_AND_NEVER_LISTED`.

**Counted under this install's own prefix, and the backup bucket at its root.** The application
writes its keys under `INSTALL_OBJECT_STORE_PREFIX` so two installs can share an endpoint, and the
nightly copy is written at the backup bucket's root by `ops/backup/brain-backup`. Each bucket is
counted where this install's objects are, which `brain.ops.object_store.key_prefix` decides.

**No object name is ever listed, and that is a rule rather than a gap.** A name can say what a file
is about, which is why `brain.knowledge.uploads` keys an original by its digest, and who may read
an object is decided where the object is used. A screen listing names would be a second answer to
that question for every reader who may open this one. The count is taken inside the client, and
`brain.ops.storage.BucketUsage`, which `BucketCounter.usage` answers, has no field a name could
arrive in. See `OBJECT_NAMES_ARE_NOT_LISTED_HERE`.

**Nothing on this screen changes anything, and the reason is the storage module's own.** The bucket
set is closed in the source and each retention is argued there and provisioned from there, so a
retention changed from a browser would be a policy nobody can explain, which `brain.ops.storage`
says is the policy that gets relaxed the first time somebody needs an old file. The settings are
the setup wizard's to write. See `RETENTION_IS_A_RELEASE_AND_NOT_A_SETTING`. So what this screen
measures is real and what it manages is nothing, which is the half of its leaf still open, and
`WHAT_THIS_SCREEN_DOES_NOT_MANAGE` says so on the screen.

**The capability is `admin:storage`, held over everything, and it is checked before the store is
asked.** The store serves the whole install, and a grant scoped to one department is a grant to
read how the whole company's files are kept. It is an `admin:` verb, so `brain.gate.admission`
already withholds it from a password-only session and from every channel but the console. A reader
without it is refused in one sentence before any setting is read or any request leaves, so a
refused reader cannot make the store be listed.

**The endpoint is shown as its scheme, host and port only.** A URL can carry a user name and a
password, and a screen that echoes the setting whole would display one. See
`AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL`.

Task ids: M27.8.15
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent
from brain.install import BY_NAME, InstallError, value_of
from brain.ops.object_store import (
    BACKEND_SETTING,
    ENDPOINT_SETTING,
    PREFIX_SETTING,
    ObjectStore,
    key_prefix,
)
from brain.ops.storage import (
    BUCKETS,
    BucketCounter,
    BucketUsage,
    ObjectKind,
    StoreUnansweredError,
    bucket_for,
    lifecycle_gaps,
)

log = structlog.get_logger()

__all__ = [
    "BACKEND_SETTING",
    "ENDPOINT_SETTING",
    "PREFIX_SETTING",
    "STORAGE_AUTHORITY",
    "STORAGE_PATH",
    "count_buckets",
    "object_store_of",
    "router",
    "shown_address",
    "storage_view",
]

# ------------------------------------------------------------ written-down reasons

USAGE_IS_COUNTED_AND_NEVER_LISTED: Final = (
    "How much each bucket holds is counted from the store each time this screen is opened, under "
    "this install's own prefix, and the backup bucket at its root where the nightly copy is "
    "written. The store has no call that says how much a bucket holds, so the count is a listing "
    "taken on the server and only the two figures reach this page. A bucket with more objects than "
    "the count reaches is shown as at least that many."
)

USAGE_IS_NOT_MEASURED: Final = (
    "How much each bucket holds is not measured, because nothing on this process connects to the "
    "object store. The sentence above says why."
)

NO_STORE_ON_THIS_PROCESS: Final = (
    "This process was started without an object store, so nothing on this screen was read from "
    "one. Restart the application once the store's settings and key are in place."
)

STORE_CONNECTED: Final = (
    "The application connects to the object store with the key kept in the vault. Backups are "
    "written to it by the backup script on the server, and the Backup and recovery screen reads "
    "their records from here."
)

NOT_COUNTED_WITHOUT_A_STORE: Final = "Not counted: nothing here connects to the store."

THE_STORE_DID_NOT_ANSWER_FOR_THIS_BUCKET: Final = (
    "Not counted: the store did not answer for this bucket when the page was opened."
)

OBJECT_NAMES_ARE_NOT_LISTED_HERE: Final = (
    "No object is listed by name. A name can say what a file is about, and who may read a file is "
    "decided where it is used, so this screen describes buckets and never their contents."
)

RETENTION_IS_A_RELEASE_AND_NOT_A_SETTING: Final = (
    "Each bucket's retention is part of the product, argued beside the bucket and applied by the "
    "store's own lifecycle rule when it is provisioned. It changes in a release, not from this "
    "screen: a retention nobody can explain is the one relaxed the first time somebody needs an "
    "old file."
)

WHAT_THIS_SCREEN_DOES_NOT_MANAGE: Final = (
    "Nothing here changes the store. A bucket's lifecycle is set when the store is provisioned "
    "and this screen does not read it back, so whether the store still applies the retention "
    "shown above is not checked from here."
)

AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL: Final = (
    "The store's address is shown as its scheme, host and port. A URL can carry a user name and a "
    "password, so the setting is never echoed whole."
)

# ----------------------------------------------------------------------- the figures

#: Reading this screen. An `admin:` verb, over everything.
STORAGE_AUTHORITY: Final = Capability(value="admin:storage")

#: Where the screen is read.
STORAGE_PATH: Final = "/storage"

# ------------------------------------------------------------------------ the shapes


class BucketUsageView(BaseModel):
    """What one bucket holds for this install, counted. A floor when `complete` is false."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    objects: int
    bytes_stored: int
    complete: bool


class BucketView(BaseModel):
    """One bucket: what it holds, for how long and why, which kinds go there, and how much now.

    Exactly one of `usage` and `usage_unread`, refused here, so a bucket that was not counted is
    never drawn as a bucket holding nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    holds: str
    retention_days: int | None
    retention_reason: str
    versioned: bool
    public_read: bool
    kinds: list[str]
    usage: BucketUsageView | None = None
    usage_unread: str = ""

    @model_validator(mode="after")
    def _counted_or_says_why_not(self) -> BucketView:
        if (self.usage is None) == (not self.usage_unread):
            msg = "a bucket is counted or says why it was not, never both and never neither"
            raise ValueError(msg)
        return self


class EndpointView(BaseModel):
    """Where the store is, as far as can be shown. `address` is None when it cannot be read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str | None
    prefix: str
    backend: str
    from_default: bool
    told: str


class StorageView(BaseModel):
    """The Storage screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    buckets: list[BucketView]
    findings: list[str]
    endpoint: EndpointView
    connection: str
    usage: str
    names: str
    retention: str
    manages: str
    read_at: datetime


# ------------------------------------------------------------------------ the decisions


def may_read(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `STORAGE_AUTHORITY` over everything, at this instant."""
    scope = reach.scope_for(STORAGE_AUTHORITY, now)
    return scope is not None and scope.is_unrestricted()


def shown_address(url: str) -> str | None:
    """A store's URL as scheme, host and port, or None when it is not one.

    Nothing after the host and nothing before it: a user name, a password, a path or a query is
    dropped. See `AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL`.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{parts.scheme}://{host}" + ("" if port is None else f":{port}")


def object_store_of(request: Request) -> ObjectStore | None:
    """The store this process was built with, or None for a process built without the lifespan."""
    found = getattr(request.app.state, "object_store", None)
    return found if isinstance(found, ObjectStore) else None


async def count_buckets(backend: BucketCounter, prefix: str) -> dict[str, BucketUsage | None]:
    """Every declared bucket counted, side by side, each in a worker thread.

    None for a bucket the store did not answer about, so one failing bucket is one row saying so
    and the other three are still counted. Each count is a blocking client call, so it leaves the
    event loop; together, so the screen waits for the slowest bucket rather than for all four.
    """

    def one(name: str) -> BucketUsage | None:
        try:
            return backend.usage(name, key_prefix(name, prefix))
        except StoreUnansweredError as exc:
            log.warning("bucket not counted", bucket=name, error=str(exc))
            return None

    names = [each.name for each in BUCKETS]
    counted = await asyncio.gather(*(asyncio.to_thread(one, name) for name in names))
    return dict(zip(names, counted, strict=True))


def storage_view(
    now: datetime,
    *,
    env: Mapping[str, str] | None = None,
    saved: Mapping[str, str] | None = None,
    store: ObjectStore | None = None,
    counted: Mapping[str, BucketUsage | None] | None = None,
) -> StorageView:
    """The screen, from the storage module, the settings, and the counts already taken.

    Asks the store nothing: `count_buckets` is the one call that does, made by the route after the
    capability check, and its answer is handed in. A bucket absent from `counted` is one nothing
    counted, which is `NOT_COUNTED_WITHOUT_A_STORE` when no store is connected and the store's
    silence otherwise.
    """
    kinds: dict[str, list[str]] = {}
    for kind in ObjectKind:
        kinds.setdefault(bucket_for(kind).name, []).append(kind.value)
    try:
        url = value_of(ENDPOINT_SETTING, env=env, saved=saved)
        prefix = value_of(PREFIX_SETTING, env=env, saved=saved)
        backend = value_of(BACKEND_SETTING, env=env, saved=saved)
    except InstallError:
        url, prefix, backend = "", "", ""
    connected = store is not None and store.backend is not None
    figures = counted or {}

    def usage_of(name: str) -> tuple[BucketUsageView | None, str]:
        if not connected:
            return None, NOT_COUNTED_WITHOUT_A_STORE
        found = figures.get(name)
        if found is None:
            return None, THE_STORE_DID_NOT_ANSWER_FOR_THIS_BUCKET
        view = BucketUsageView(
            objects=found.objects, bytes_stored=found.bytes_stored, complete=found.complete
        )
        return view, ""

    rows: list[BucketView] = []
    for one in BUCKETS:
        usage, unread = usage_of(one.name)
        rows.append(
            BucketView(
                name=one.name,
                holds=one.holds,
                retention_days=one.retention_days,
                retention_reason=one.retention_reason,
                versioned=one.versioned,
                public_read=one.public_read,
                kinds=sorted(kinds.get(one.name, [])),
                usage=usage,
                usage_unread=unread,
            )
        )
    if store is None:
        connection = NO_STORE_ON_THIS_PROCESS
    elif store.backend is None:
        connection = store.unconnected
    else:
        connection = STORE_CONNECTED
    return StorageView(
        buckets=rows,
        findings=list(lifecycle_gaps()),
        endpoint=EndpointView(
            address=shown_address(url),
            prefix=prefix,
            backend=backend,
            from_default=url == BY_NAME[ENDPOINT_SETTING].default,
            told=AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL,
        ),
        connection=connection,
        usage=USAGE_IS_COUNTED_AND_NEVER_LISTED if connected else USAGE_IS_NOT_MEASURED,
        names=OBJECT_NAMES_ARE_NOT_LISTED_HERE,
        retention=RETENTION_IS_A_RELEASE_AND_NOT_A_SETTING,
        manages=WHAT_THIS_SCREEN_DOES_NOT_MANAGE,
        read_at=now,
    )


# ------------------------------------------------------------------------- the route

router = APIRouter(prefix=API_PREFIX, tags=["storage"])


@router.get(STORAGE_PATH, response_model=StorageView, responses=COMMON_RESPONSES)
async def storage(request: Request, asked: Asked) -> StorageView:
    """The buckets, their retention and why, where the store is, and how much each holds now.

    The capability first, then the store, so a reader who may not open the screen cannot cause a
    listing. Never an object's name.
    """
    if not may_read(asked.reach, asked.now):
        log.info("storage not answerable", principal=asked.caller.principal.id)
        raise Absent("storage is not answerable for this caller")
    store = object_store_of(request)
    counted = None
    if store is not None and store.backend is not None:
        counted = await count_buckets(store.backend, store.prefix)
    return storage_view(asked.now, store=store, counted=counted)
