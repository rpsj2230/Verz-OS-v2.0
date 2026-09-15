"""Asking a release list which release is newest, only when an install has been told where it is.

`brain.console.version_view` compares what an install runs against what somebody has said is
newest, and argued for a day that nothing should ever do the saying automatically: a check that
runs by default is an outbound connection nobody agreed to, and it tells whoever answers that
this product is installed at that address. That argument is kept, and it is why this module
exists in the shape it does rather than as a fetch inside the panel.

**Switched off unless the install's own configuration names a list.** `BRAIN_RELEASE_FEED_URL`
has no default anywhere, and an install where it is unset asks nobody and says so: the answer is
`Unasked.NO_SOURCE`, which the panel draws as nobody having said. A client that wants the reminder
names the list, and the list can be a copy on their own network, which removes every item in
`version_view.WHAT_A_RELEASE_CHECK_WOULD_SEND` except the outbound allowance to their own mirror.
See `A_CHECK_NOBODY_SWITCHED_ON_IS_A_DISCLOSURE_NOBODY_AGREED_TO`. The variable is read by
`brain.settings.Settings` and handed in, never read here; see `CONFIGURATION_IS_READ_IN_ONE_PLACE`.

**Every way of not getting an answer is an answer that is not a tick.** A list that is not an
https address, that cannot be reached, that answers with something other than JSON, that is
larger than a list of releases could be, or that names no release this install can order, is an
`Unanswered` with the reason. None of those produces a `Told`, so none of them can reach
`Standing.CURRENT`, and the panel refuses that standing without a `Told` besides. See
`AN_ANSWER_ANYBODY_ON_THE_PATH_COULD_REWRITE_IS_NOT_ONE_TO_CALL_UP_TO_DATE`.

**The list's shape is the one a release is actually published into.** `.github/workflows/
release.yml` publishes each tag as a release with its archive attached, so the list is the JSON
a repository's releases endpoint returns: an array of objects carrying `tag_name`, `draft` and
`prerelease`. A single such object is accepted too, which is what the latest-release endpoint
returns. Drafts and prereleases are not releases a client installs, and a tag outside the one
shape `version_view` orders is ignored rather than guessed at, so `latest` never becomes newest.

**What is true on a real install today.** No release has been published, so there is no list
with anything on it, and the application container cannot read which release it is running
(`version_view.facts_the_container_cannot_read`), so the panel answers `UNKNOWN_RUNNING` before
it asks about anything newer. And nothing renders the panel: the screen is registered and its
tool is not. This module is the asking, built and tested against a transport handed in; the
transport that opens a socket has never been pointed at a published list.

Rejected: comparing the release list's newest tag against `BRAIN_RELEASE_URL`. That variable is
the archive of the one release being installed, set for the length of an install or update and
not kept, so it names what somebody fetched once rather than what is newest now.

Task ids: M42.3.9
"""

from __future__ import annotations

import http.client
import json
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

from brain.console.version_view import Told, Unanswered, Unasked, VersionError, ordinal

# ------------------------------------------------------------------ written-down reasons
#: Why the check is off until configured.
A_CHECK_NOBODY_SWITCHED_ON_IS_A_DISCLOSURE_NOBODY_AGREED_TO: Final = (
    "A request to a release list tells whoever serves it that this product runs at the "
    "address the request left from, and when. On a product a client installs and owns, that is "
    "theirs to decide, so the default is to ask nobody and to say so, and the list is named by "
    "the install's own configuration, which can point at a copy inside their network."
)

#: Why only https.
AN_ANSWER_ANYBODY_ON_THE_PATH_COULD_REWRITE_IS_NOT_ONE_TO_CALL_UP_TO_DATE: Final = (
    "The answer this list gives is the one a client reads before deciding not to update. Over "
    "plain http anybody between the server and the list can replace it with a list whose newest "
    "release is the one already running, and the panel would draw that as a tick. So a list "
    "that is not https is not asked, and the panel says why."
)

# ------------------------------------------------------------------------ configuration
#: The variable naming the release list. No default, deliberately.
FEED_VARIABLE: Final = "BRAIN_RELEASE_FEED_URL"

#: How long a request may take before the list counts as unreachable. A console panel waits on
#: this, so it is short, and a list that is slow is reported rather than waited for.
FEED_TIMEOUT_SECONDS: Final = 10

#: The largest answer read. A list of every release this product could publish in years is a
#: few hundred kilobytes; an answer past this is not a release list.
MAX_FEED_BYTES: Final = 2_000_000

#: What a fetch is: an address in, the body out, raising `OSError` or an HTTP error on failure.
Fetch = Callable[[str], bytes]


#: Why this module is handed the address rather than reading it.
CONFIGURATION_IS_READ_IN_ONE_PLACE: Final = (
    "Anything that differs between installs is configuration, and configuration is read in one "
    "place: brain.settings.Settings reads BRAIN_RELEASE_FEED_URL, and whoever renders the panel "
    "hands settings.release_feed_url to check. A module reading the environment for itself is a "
    "second "
    "reader of one value, and the place a fallback address gets written where no client looks."
)


def newest_release(payload: object) -> str | None:
    """The newest published release a list names, or `None` when it names none this can order.

    Pure: the parsed JSON in, a tag out. Ordered with `version_view.ordinal`, the one ordering of
    two tags this repository has. No padding is needed for a maximum: a tuple that is a prefix of
    another sorts first, so `v1.4` sorts before `v1.4.0` and both before `v1.5`, and padding with
    zeros changes only which of two spellings of one release is returned.
    """
    items: list[object]
    if isinstance(payload, list):
        items = list(payload)
    elif isinstance(payload, dict):
        items = [payload]
    else:
        return None
    found: list[tuple[tuple[int, ...], str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("draft") is not False or item.get("prerelease") is not False:
            continue
        tag = str(item.get("tag_name", "")).strip()
        numbers = ordinal(tag)
        if numbers is None:
            continue
        found.append((numbers, tag))
    if not found:
        return None
    return max(found)[1]


def ask(url: str, *, fetch: Fetch, now: datetime) -> Told | Unanswered:
    """Ask the release list at `url` which release is newest, failing closed at every step.

    `fetch` and `now` are parameters for the reason `version_view.standing_of` takes `now`: the
    interesting cases are a list that does not answer and an answer that is wrong, and neither
    can be tested through a function that opens a socket.
    """
    if now.tzinfo is None:
        msg = "a naive now cannot record when a release list was asked"
        raise VersionError(msg)
    where = url.strip()
    if not where:
        return Unanswered(
            why=Unasked.NO_SOURCE,
            detail=(
                f"{FEED_VARIABLE} is not set, so this install asks nothing outside its network "
                "about newer releases"
            ),
            at=now,
        )
    if urlsplit(where).scheme != "https":
        return Unanswered(
            why=Unasked.UNREADABLE,
            detail=(
                f"{FEED_VARIABLE} is not an https address, and an answer anybody on the path "
                "could rewrite is not one this install will call up to date"
            ),
            at=now,
        )
    try:
        body = fetch(where)
    except (OSError, http.client.HTTPException) as error:
        return Unanswered(
            why=Unasked.UNREACHABLE,
            detail=f"asking {where} failed ({type(error).__name__})",
            at=now,
        )
    if len(body) > MAX_FEED_BYTES:
        return Unanswered(
            why=Unasked.UNREADABLE,
            detail=f"{where} answered with more than a release list could hold",
            at=now,
        )
    try:
        payload: object = json.loads(body)
    except ValueError:
        return Unanswered(
            why=Unasked.UNREADABLE,
            detail=f"{where} did not answer with a list of releases",
            at=now,
        )
    newest = newest_release(payload)
    if newest is None:
        return Unanswered(
            why=Unasked.UNREADABLE,
            detail=f"{where} named no published release in a form this install can order",
            at=now,
        )
    return Told(tag=newest, at=now, by=f"the release list at {where}, read by this install")


def https_fetch(url: str, *, timeout: float = FEED_TIMEOUT_SECONDS) -> bytes:
    """The transport: one GET over https, reading no more than a release list could be.

    Refuses anything but https itself as well as `ask` doing so, because a caller handing this
    a URL directly would otherwise reach the one path the check above exists to close.
    """
    if urlsplit(url).scheme != "https":
        msg = f"{url!r} is not an https address"
        raise OSError(msg)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body: bytes = response.read(MAX_FEED_BYTES + 1)
    return body


def check(*, now: datetime, url: str, fetch: Fetch = https_fetch) -> Told | Unanswered:
    """What the panel is handed: the configured list asked, or the reason it was not.

    `url` is `brain.settings.Settings.release_feed_url`, handed in by whoever renders the panel. See
    `CONFIGURATION_IS_READ_IN_ONE_PLACE`.
    """
    return ask(url, fetch=fetch, now=now)
