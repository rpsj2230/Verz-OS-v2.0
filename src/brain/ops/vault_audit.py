"""Reading the vault's audit log, so "who read which credential" has an answer.

The application sees a lease. It cannot see a history, and it must not: a component that
could read its own access history could also decide what that history said. The vault
writes the log; this reads it, and `brain.ops.vault_audit_ship` carries what it reads into
the ledger from the worker, which never writes the log and holds no token that could.

**Every value in the log is already an HMAC, and this module must never undo that.**
OpenBao hashes tokens, accessors and every field of a request's and a response's data with a
key it holds, so the log answers "was this the same identity as that one" without answering
"what is the identity". Nothing in `VaultAccess` can hold a value, a token or a data field,
and the raw line is never retained after parsing, so a caller cannot reach past the type to
the text.

**What an entry is filed under is the slot, and never more of the path than the slot.**
Until 2026-09-17 this module kept a `path_hmac`, on the belief that OpenBao hashes a request's
path. It does not: the path is written in the clear and only its data is hashed, so the field
was empty for every real entry and the module shipped nothing anybody could read. The path
names which slot was read, `connector_keys/data/xero`, which is not a secret: the console lists
every slot by that name. What a path can carry beyond a slot is a lease id or a token accessor
in `sys/leases/revoke/<id>`, and those are cut off. So `slot_of` maps a path onto a closed
grammar, the credential slot grammar the ledger already files writes under, or refuses it, and
an unrecognised path is dropped rather than kept raw. See `A_PATH_IS_KEPT_ONLY_AS_FAR_AS_ITS_SLOT`.

**Responses, not requests.** OpenBao writes each call twice, the request and then the response,
and only the response carries whether it was refused. Keeping both would double every count and
file the refusal under one of the two. A request that never got a response is a vault that
crashed mid-call, which its own log and the container's say better than a ledger row could.

**A refused request is the interesting one.** A successful credential read is routine; a
refusal is either a misconfiguration or somebody asking for something they should not have.
Both are shipped, marked, and counted apart.

**The vault's own chatter is not a credential access.** A token looking itself up or renewing
itself, the seal status and health are asked constantly and name no slot, and a ledger that is
mostly the vault talking to itself hides the entries that are not.

Task ids: M31.3.2.6
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from brain.ops.openbao import STATIC_PREFIXES

# ------------------------------------------------------------------ written-down reasons

#: Why the slot and not the path.
A_PATH_IS_KEPT_ONLY_AS_FAR_AS_ITS_SLOT: Final = (
    "OpenBao writes a request's path in the clear and hashes only its data. A path names the slot "
    "that was read, which the console already lists, and past the slot it can name a lease id or "
    "a token accessor, which are handles on a live credential. So a path is mapped onto the "
    "credential slot grammar the ledger files writes under, and anything that does not map is "
    "dropped rather than kept raw."
)

#: What an OpenBao HMAC looks like in the log. Anything not matching is a value that was
#: written in the clear, which means `log_raw` was turned on somewhere.
HMAC_RE = re.compile(r"^hmac-sha256:([0-9a-f]{64})$")

#: The slot grammar, as `brain.audit.record.CREDENTIAL_SLOT` writes it. Copied rather than
#: imported, because the audit package sits above the vault client; a test holds them equal.
SLOT_GRAMMAR: Final = r"^[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)+$"
SLOT_CHARS: Final = 128
_SLOT_RE = re.compile(SLOT_GRAMMAR)

#: An operation as OpenBao names one: read, create, update, delete, list, patch.
_OPERATION_RE = re.compile(r"^[a-z]{1,16}$")

#: One path segment of a name the vault stores under, as the slot grammar can take it.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


class AuditLogError(Exception):
    """Raised when the log says something that should be impossible."""


class Part(enum.StrEnum):
    """What part of a slot a request touched. Closed, and a test holds the table's copy equal."""

    #: The value itself: a read hands a key over, a write replaces it.
    VALUE = "value"
    #: Versions, times and custom metadata, and no field of the secret.
    METADATA = "metadata"
    #: A run token minted against a token role, or a dynamic credential leased.
    LEASE = "lease"
    #: A token or a lease given back.
    REVOKE = "revoke"
    #: The vault's own configuration: a policy, an engine, an audit device, a token role.
    CONFIG = "config"


@dataclass(frozen=True)
class VaultAccess:
    """One call the vault answered, filed under the slot it touched.

    There is no field here that could hold a secret, a data field, a raw path or a usable token,
    and that is the mechanism rather than an oversight.
    """

    at: datetime
    operation: str
    part: Part
    #: The slot, in `SLOT_GRAMMAR`. See `A_PATH_IS_KEPT_ONLY_AS_FAR_AS_ITS_SLOT`.
    slot: str
    #: The 64 hex characters of the accessor's HMAC, or empty. Identifies *a* token consistently
    #: without being usable as one.
    identity: str = ""
    refused: bool = False


def _name(segment: str) -> str | None:
    """A stored name as one slot segment: `-` written as `_`, or None when it cannot be one."""
    if not _NAME_RE.fullmatch(segment):
        return None
    return segment.replace("-", "_")


def slot_of(path: str) -> tuple[str, Part] | None:
    """The slot a path names and the part of it touched, or None for a path nothing ships.

    See `A_PATH_IS_KEPT_ONLY_AS_FAR_AS_ITS_SLOT`. A lease id or accessor after `sys/leases/revoke`
    is never read, and a kv path deeper than one name is not a slot any policy here grants.
    """
    parts = path.strip("/").split("/")
    found: tuple[str, Part] | None = None
    engines = {prefix.rstrip("/") for prefix in STATIC_PREFIXES}
    match parts:
        case [engine, "data", name] if engine in engines:
            found = (f"{engine}/{name}", Part.VALUE)
        case [engine, "metadata", name] if engine in engines:
            found = (f"{engine}/{name}", Part.METADATA)
        case ["database", "creds", name]:
            found = (f"database/{name}", Part.LEASE)
        case ["auth", "token", "create", role]:
            found = (f"token_role/{role}", Part.LEASE)
        case ["auth", "token", "roles", role]:
            found = (f"token_role/{role}", Part.CONFIG)
        case ["auth", "token", "revoke-self"]:
            found = ("token/revoke_self", Part.REVOKE)
        case ["sys", "leases", "revoke", *_]:
            found = ("lease/revoke", Part.REVOKE)
        case ["sys", "policy", name] | ["sys", "policies", "acl", name]:
            found = (f"policy/{name}", Part.CONFIG)
        case ["sys", "audit", name]:
            found = (f"audit_device/{name}", Part.CONFIG)
        case ["sys", "mounts", name]:
            found = (f"engine/{name}", Part.CONFIG)
    if found is None:
        return None
    family, _, name = found[0].partition("/")
    spelled = _name(name)
    if spelled is None:
        return None
    slot = f"{family}/{spelled}"
    if len(slot) > SLOT_CHARS or not _SLOT_RE.fullmatch(slot):
        return None
    return slot, found[1]


def _identity(value: object) -> str:
    """The hex of an HMAC, or empty. Never the value itself.

    An accessor that arrives unhashed means `hmac_accessor=false` or `log_raw=true` was set.
    Returning empty rather than the raw text means a misconfigured vault produces entries with
    no identity, instead of copying working handles on tokens into the table kept longest.
    """
    found = HMAC_RE.match(str(value or ""))
    return found.group(1) if found else ""


def parse_line(line: str) -> VaultAccess | None:
    """One JSON line from the audit log, or None if it is not an entry worth shipping.

    None rather than an exception for an uninteresting line, because the log is mostly
    uninteresting. An exception is reserved for a line that is malformed, which is a different
    problem and should not be swallowed alongside the routine ones.
    """
    if not line.strip():
        return None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        msg = f"audit log line is not JSON: {line[:80]!r}"
        raise AuditLogError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"audit log line is not an object: {line[:80]!r}"
        raise AuditLogError(msg)
    if raw.get("type") != "response":
        return None

    request = raw.get("request") or {}
    if not isinstance(request, dict):
        return None
    mapped = slot_of(str(request.get("path", "")))
    if mapped is None:
        return None
    operation = str(request.get("operation", ""))
    if not _OPERATION_RE.fullmatch(operation):
        return None

    try:
        at = datetime.fromisoformat(str(raw.get("time", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        msg = f"audit entry has no usable time: {raw.get('time')!r}"
        raise AuditLogError(msg) from exc
    if at.tzinfo is None:
        msg = "audit entry timestamp has no timezone"
        raise AuditLogError(msg)

    auth = raw.get("auth") or {}
    slot, part = mapped
    return VaultAccess(
        at=at,
        operation=operation,
        part=part,
        slot=slot,
        identity=_identity(
            (auth.get("accessor") if isinstance(auth, dict) else "")
            or request.get("client_token_accessor")
        ),
        refused=bool(raw.get("error")),
    )


def read_log(path: Path) -> Iterator[VaultAccess]:
    """Every shippable access in the log, oldest first, streamed rather than read whole."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            entry = parse_line(line)
            if entry is not None:
                yield entry


@dataclass(frozen=True)
class AccessSummary:
    """What the log says, in counts. Never in names.

    Counts and distinct totals only. A summary listing which slots were read most would be a
    ranked list of the most valuable secrets in the system.
    """

    total: int = 0
    refused: int = 0
    distinct_identities: int = 0
    distinct_slots: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None

    @property
    def refusal_rate(self) -> float:
        return round(self.refused / self.total, 4) if self.total else 0.0


def summarise(entries: Iterator[VaultAccess] | list[VaultAccess]) -> AccessSummary:
    """Roll a log up into something a person can read in one line."""
    total = refused = 0
    identities: set[str] = set()
    slots: set[str] = set()
    first: datetime | None = None
    last: datetime | None = None
    for entry in entries:
        total += 1
        if entry.refused:
            refused += 1
        if entry.identity:
            identities.add(entry.identity)
        slots.add(entry.slot)
        first = entry.at if first is None or entry.at < first else first
        last = entry.at if last is None or entry.at > last else last
    return AccessSummary(
        total=total,
        refused=refused,
        distinct_identities=len(identities),
        distinct_slots=len(slots),
        first_at=first,
        last_at=last,
    )


def audit_is_enabled(devices: str) -> bool:
    """Whether `bao audit list` output shows a device.

    A string rather than a call, so the check can run against output captured over ssh from
    a machine that has no vault client. The devices are declared in `ops/openbao/compose.yml`,
    so a vault listing none is running a configuration other than the one shipped.
    """
    return any(
        line.strip() and not line.startswith("Path") and "/" in line.split()[0]
        for line in devices.splitlines()
    )
