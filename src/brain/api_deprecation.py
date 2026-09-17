"""How a route under `/api/v1` is retired: announced on every answer, and served until its date.

**A v1 route is never removed or changed incompatibly without notice, and the notice is on the
wire, not in a changelog.** Integrations written against this API belong to the company that
installed it (a Lark bot, a spreadsheet script, a partner's portal), and none of their authors
reads this repository. So a route being retired says so in every response it sends, in the two
headers a client library can act on: `Deprecation` (RFC 9745) with the date it was deprecated,
and `Sunset` (RFC 8594) with the date before which it will not go, plus a `Link` naming its
successor. OpenAPI marks the operation deprecated and carries the same two facts. See
`DEPRECATION_POLICY`.

**The notice has a floor, checked when the route is declared.** `MINIMUM_NOTICE` is ninety days,
so an install that updates at least once a quarter runs a release carrying the headers before
the route goes. A shorter notice is refused at import rather than argued about in review.

Rejected: a version header or `/api/v2` for every change. A new major version doubles every
route an integration has to move at once; retiring routes one at a time behind a dated notice
moves each integration when it touches the route that changed. An incompatible change to a
route's response that cannot be retired this way is what `/api/v2` is for.

Task ids: M31.1.4.1
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from typing import Any, Final

from fastapi import Depends, Response

#: The shortest time between deprecating a route and removing it.
MINIMUM_NOTICE: Final = timedelta(days=90)

#: Where a successor may live: this version or a later one, never outside the API.
API_ROOT: Final = "/api/v"

DEPRECATION_POLICY: Final = (
    "A route under /api/v1 that is going away is first declared deprecated with a date it was "
    "deprecated, a sunset date at least MINIMUM_NOTICE later and the path of its successor. From "
    "then until the sunset every answer carries Deprecation, Sunset and a successor Link, and "
    "OpenAPI marks it deprecated. It is not removed before the sunset, and a v1 response is "
    "never changed incompatibly in place: that is a new route, or /api/v2."
)


@dataclass(frozen=True)
class Deprecation:
    """One route's notice: when it was deprecated, the day it may go, and what replaces it."""

    since: date
    sunset: date
    successor: str

    def __post_init__(self) -> None:
        if self.sunset - self.since < MINIMUM_NOTICE:
            msg = (
                f"a sunset {(self.sunset - self.since).days} days after deprecation is shorter "
                f"than the {MINIMUM_NOTICE.days} days every integration is promised"
            )
            raise ValueError(msg)
        if not self.successor.startswith(API_ROOT):
            msg = f"successor {self.successor!r} is not a route under {API_ROOT}N"
            raise ValueError(msg)

    def headers(self) -> dict[str, str]:
        """The three headers, in the forms the two RFCs and RFC 8288 define."""
        since = datetime(self.since.year, self.since.month, self.since.day, tzinfo=UTC)
        sunset = datetime(self.sunset.year, self.sunset.month, self.sunset.day, tzinfo=UTC)
        return {
            "Deprecation": f"@{int(since.timestamp())}",
            "Sunset": format_datetime(sunset, usegmt=True),
            "Link": f'<{self.successor}>; rel="successor-version"',
        }


def deprecated(notice: Deprecation) -> dict[str, Any]:
    """Keyword arguments for a route decorator: `@router.get(path, **deprecated(notice))`."""

    async def announce(response: Response) -> None:
        response.headers.update(notice.headers())

    return {
        "deprecated": True,
        "dependencies": [Depends(announce)],
        "openapi_extra": {"x-sunset": notice.sunset.isoformat(), "x-successor": notice.successor},
    }


def undeclared_deprecations(document: Mapping[str, Any]) -> list[str]:
    """Every operation the document marks deprecated without a sunset and a served successor.

    A route marked `deprecated=True` by hand, rather than through `deprecated`, sends no headers,
    so no client is told; this is how the check finds one."""
    paths: Mapping[str, Any] = document.get("paths", {})
    found: list[str] = []
    for path, operations in paths.items():
        for method, operation in operations.items():
            if not isinstance(operation, dict) or not operation.get("deprecated"):
                continue
            if not operation.get("x-sunset") or operation.get("x-successor") not in paths:
                found.append(f"{method.upper()} {path}")
    return found
