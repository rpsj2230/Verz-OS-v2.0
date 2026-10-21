"""Asking the server for a restore rehearsal: the request, and finding one that is waiting.

The product starts nothing on the server, so a person's press on the Recovery screen cannot start a
rehearsal. What it can do is leave a request where the drill service already looks, which is the
backup bucket, and read the service's answer from the record the service writes beside the copy
(`brain.ops.drill_service` has the whole argument, and says why a bucket and not a port). This
module is that request and nothing else: its body, finding one in a listing, and putting one.

**The request carries who and when and nothing the service acts on.** The service decides whether a
rehearsal runs, of which copy, from the listing and the clock. A request body that named a copy or
a target would be an instruction written by a web process to a process with root, and the one thing
that must not be possible from the console is choosing what a root process loads. The body exists
so the screen can say when the ask was made and by whom, and the service reads only that the object
is there.

**A request that cannot be read is still a request.** The screen says it is waiting rather than
saying nothing was asked, because the service answers the object and not its content, and a body
that is not what this module writes is a file somebody put there, not a reason to hide that the
service will act on it.

Rejected: a row in the database. The service must work when the database is the thing that is
being rehearsed, and a rehearsal that depends on the database it is rehearsing restoring is a
rehearsal that cannot run on the day it matters.

Task ids: M30.3.9
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.ops.drill_service import REQUEST_KEY
from brain.ops.storage import ObjectKind, StorageBackend, bucket_for

#: How the object is typed in the bucket.
CONTENT_TYPE: Final = "application/json"


@dataclass(frozen=True)
class Pending:
    """A request that is in the bucket now, with when it was made if its body says."""

    at: datetime | None
    by: str | None


def request_object(*, at: datetime, by: str) -> bytes:
    """The request as the bucket holds it. `at` must carry an offset or the time shown is wrong."""
    if at.tzinfo is None:
        msg = "a request with a naive time would be shown at this machine's offset"
        raise ValueError(msg)
    return json.dumps({"requested_at": at.isoformat(), "requested_by": by}).encode("utf-8")


def pending_in(listing: Iterable[tuple[str, str]]) -> Pending | None:
    """The waiting request among a bucket's objects, or None when there is none."""
    for name, content in listing:
        if name != REQUEST_KEY:
            continue
        try:
            document = json.loads(content)
            at = datetime.fromisoformat(document["requested_at"])
            by = document["requested_by"]
        except (ValueError, KeyError, TypeError):
            return Pending(at=None, by=None)
        if at.tzinfo is None or not isinstance(by, str):
            return Pending(at=None, by=None)
        return Pending(at=at, by=by)
    return None


def put_request(backend: StorageBackend, *, at: datetime, by: str) -> None:
    """Leave the request in the backup bucket for the service to find."""
    backend.put_object(
        bucket_for(ObjectKind.DATABASE_DUMP).name,
        REQUEST_KEY,
        request_object(at=at, by=by),
        CONTENT_TYPE,
    )
