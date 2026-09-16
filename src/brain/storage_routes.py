"""The Storage screen over HTTP: the buckets this product keeps, how long each keeps what, and why.

`brain.ops.storage` declares the object store's shape: four buckets, each with what it holds, a
retention and the reason for it, whether it is versioned, and a check that none is public. It is
read by the backup scripts' provisioning test and by nothing a browser could open. This serves it,
with the two installation settings that say where the store is, and says in words what cannot be
known from here.

**Usage cannot be read, and the screen says why rather than drawing an empty bar.** Nothing in
the application constructs a `StorageBackend`, so nothing on an install asks the store anything;
and the protocol's four operations carry no size, so an implementation could only add up sizes by
listing every object. See `USAGE_IS_NOT_MEASURED`.

**No object name is ever listed, and that is a rule rather than a gap.** A name can say what a file
is about, which is why `brain.knowledge.uploads` keys an original by its digest, and who may read
an object is decided where the object is used. A screen listing names would be a second answer to
that question for every reader who may open this one. See `OBJECT_NAMES_ARE_NOT_LISTED_HERE`.

**Nothing on this screen changes anything, and the reason is the storage module's own.** The bucket
set is closed in the source and each retention is argued there and provisioned from there, so a
retention changed from a browser would be a policy nobody can explain, which `brain.ops.storage`
says is the policy that gets relaxed the first time somebody needs an old file. The two settings
are the setup wizard's to write. See `RETENTION_IS_A_RELEASE_AND_NOT_A_SETTING`.

**The capability is `admin:storage`, held over everything.** The store serves the whole install,
and a grant scoped to one department is a grant to read how the whole company's files are kept.
It is an `admin:` verb, so `brain.gate.admission` already withholds it from a password-only session
and from every channel but the console. A reader without it is refused in one sentence, before any
setting is read.

**The endpoint is shown as its scheme, host and port only.** A URL can carry a user name and a
password, and a screen that echoes the setting whole would display one. See
`AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL`.

Task ids: M27.8.15
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent
from brain.install import BY_NAME, InstallError, value_of
from brain.ops.storage import BUCKETS, ObjectKind, bucket_for, lifecycle_gaps

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

USAGE_IS_NOT_MEASURED: Final = (
    "How much each bucket holds is not measured. Nothing on this install connects to the object "
    "store from the application yet, and the four things the application may ask a store include "
    "no size, so the only way to add one up would be to list every object in the bucket, which "
    "this screen never does."
)

NOTHING_CONNECTS_TO_THE_STORE_YET: Final = (
    "Nothing in the application reads or writes the object store yet, so whether it answers "
    "cannot be checked from here. Backups are the one thing written to it today, by the backup "
    "script on the server with its own settings, and the Backup and recovery screen reports them."
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

AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL: Final = (
    "The store's address is shown as its scheme, host and port. A URL can carry a user name and a "
    "password, so the setting is never echoed whole."
)

# ----------------------------------------------------------------------- the figures

#: Reading this screen. An `admin:` verb, over everything.
STORAGE_AUTHORITY: Final = Capability(value="admin:storage")

#: Where the screen is read.
STORAGE_PATH: Final = "/storage"

#: The two installation settings that say where the store is.
ENDPOINT_SETTING: Final = "INSTALL_OBJECT_STORE_URL"
PREFIX_SETTING: Final = "INSTALL_OBJECT_STORE_PREFIX"

# ------------------------------------------------------------------------ the shapes


class BucketView(BaseModel):
    """One bucket: what it holds, for how long and why, and which kinds of object go there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    holds: str
    retention_days: int | None
    retention_reason: str
    versioned: bool
    public_read: bool
    kinds: list[str]


class EndpointView(BaseModel):
    """Where the store is, as far as can be shown. `address` is None when it cannot be read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str | None
    prefix: str
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


def storage_view(
    now: datetime,
    *,
    env: Mapping[str, str] | None = None,
    saved: Mapping[str, str] | None = None,
) -> StorageView:
    """The screen, from the storage module and the two settings. Asks the store nothing."""
    kinds: dict[str, list[str]] = {}
    for kind in ObjectKind:
        kinds.setdefault(bucket_for(kind).name, []).append(kind.value)
    try:
        url = value_of(ENDPOINT_SETTING, env=env, saved=saved)
        prefix = value_of(PREFIX_SETTING, env=env, saved=saved)
    except InstallError:
        url, prefix = "", ""
    return StorageView(
        buckets=[
            BucketView(
                name=one.name,
                holds=one.holds,
                retention_days=one.retention_days,
                retention_reason=one.retention_reason,
                versioned=one.versioned,
                public_read=one.public_read,
                kinds=sorted(kinds.get(one.name, [])),
            )
            for one in BUCKETS
        ],
        findings=list(lifecycle_gaps()),
        endpoint=EndpointView(
            address=shown_address(url),
            prefix=prefix,
            from_default=url == BY_NAME[ENDPOINT_SETTING].default,
            told=AN_ENDPOINT_IS_SHOWN_WITHOUT_ANYTHING_THAT_COULD_BE_A_CREDENTIAL,
        ),
        connection=NOTHING_CONNECTS_TO_THE_STORE_YET,
        usage=USAGE_IS_NOT_MEASURED,
        names=OBJECT_NAMES_ARE_NOT_LISTED_HERE,
        retention=RETENTION_IS_A_RELEASE_AND_NOT_A_SETTING,
        read_at=now,
    )


# ------------------------------------------------------------------------- the route

router = APIRouter(prefix=API_PREFIX, tags=["storage"])


@router.get(STORAGE_PATH, response_model=StorageView, responses=COMMON_RESPONSES)
async def storage(asked: Asked) -> StorageView:
    """The buckets, their retention and why, and where the store is. Never an object's name."""
    if not may_read(asked.reach, asked.now):
        log.info("storage not answerable", principal=asked.caller.principal.id)
        raise Absent("storage is not answerable for this caller")
    return storage_view(asked.now)
