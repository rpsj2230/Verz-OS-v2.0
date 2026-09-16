"""Looking for a newer release: switched on by the install, asked by the server, never waited for.

`brain.console.version_view` compares what an install runs against the newest release it has
been told about and reaches nothing itself. This is the telling. Four decisions shape it and
each one has a cheaper version that is wrong.

**Off unless the install switches it on.** `BRAIN_RELEASE_CHECK` defaults to false in
`brain.settings.Settings`, and an install where it is off asks nobody and says so: the answer is
`Unasked.SWITCHED_OFF`, which the panel draws as the check being switched off rather than as up
to date. A request to a release list tells whoever serves it that this product runs at the
address the request left from, and when, and on a product a client installs and owns that is
theirs to agree to. `version_view.WHAT_A_RELEASE_CHECK_WOULD_SEND` is what they agree to. See
`A_CHECK_NOBODY_SWITCHED_ON_IS_A_DISCLOSURE_NOBODY_AGREED_TO`.

**The list is the product's own, named once, and an install can point at a copy instead.**
`PRODUCT_RELEASES_URL` is where `.github/workflows/release.yml` publishes every release, which is
the same for every install and belongs to the product rather than to any client, exactly as
`brain.deployment.installer.PRODUCT_IMAGE` does. It names the repository by its number rather
than by its owner and name: the repository was renamed once already, the address under its old
name has answered with a redirect ever since, and a number survives a rename where a name does
not. `BRAIN_RELEASE_FEED_URL` replaces it with a copy, which can sit inside the client's network
and removes every item on that list but the outbound allowance to their own mirror. Both are
read by `Settings` and handed to `feed_address`; see `CONFIGURATION_IS_READ_IN_ONE_PLACE`.

**The server asks, in the background, and no page waits for it.** Until 2026-09-16 the updates
route awaited the fetch, so a list that was slow put up to `FEED_TIMEOUT_SECONDS` in front of
the screen on every load, and a list that never answered did that every time. `ReleaseWatch`
holds this process's last look. The route reads it synchronously and gets whatever is there, and
when a look is due it starts one as a task and returns without it. The first load after a start
therefore says the check has not finished yet, which is true, and the load after says what the
list said. See `A_PAGE_NEVER_WAITS_FOR_THE_RELEASE_LIST`.

**A look is started by somebody opening the screen, and never by a timer.** A timer asks on a
server nobody is looking at, which is the disclosure with no reader to show the answer to: the
only place the answer is drawn is the screen, so a look nobody opens the screen for is a request
with no purpose. `LOOK_AGAIN_AFTER` bounds how often the screen can cause one. See
`A_LOOK_IS_STARTED_BY_A_READER_AND_NOT_BY_A_TIMER`.

**Every way of not getting an answer is an answer that is not a tick.** A list that is not an
https address, that cannot be reached, that answers with something other than JSON, that is
larger than a list of releases could be, or that names no release this install can order, is an
`Unanswered` with the reason. None of those produces a `Told`, so none of them can reach
`Standing.CURRENT`, and the panel refuses that standing without a `Told` besides. See
`AN_ANSWER_ANYBODY_ON_THE_PATH_COULD_REWRITE_IS_NOT_ONE_TO_CALL_UP_TO_DATE`.

**The list's shape is the one a release is actually published into**: the JSON a repository's
releases endpoint returns, an array of objects carrying `tag_name`, `draft`, `prerelease` and
`html_url`. A single such object is accepted too, which is what the latest-release endpoint
returns. Drafts and prereleases are not releases a client installs, and a tag outside the one
shape `version_view` orders is ignored rather than guessed at, so `latest` never becomes newest.

Rejected: one look per install rather than per process, held in the cache every process shares.
It saves a request per worker per look, which is at most a handful a day, and costs a module that
decides policy holding a client of the cache, which `brain.cache` and `brain.ops.limit_store`
exist to keep apart. Two workers disagreeing for the seconds after a start is one saying the
check has not finished and the other saying what the list said, and neither of those is a tick.

Rejected: comparing the release list's newest tag against `BRAIN_RELEASE_URL`. That variable is
the archive of the one release being installed, set for the length of an install or update and
not kept, so it names what somebody fetched once rather than what is newest now.

What is true on a real install today: no release has been published, so the product's list is an
empty array, which this reads as naming no release and draws as the check having failed with
that reason. No install has switched the check on against a published release, so the transport
has been pointed at the real list by hand and at nothing else.

Task ids: M42.3.9
"""

from __future__ import annotations

import asyncio
import http.client
import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import urlsplit

import structlog

from brain.console.version_view import (
    NOTES_ARE_READ_OVER,
    Told,
    Unanswered,
    Unasked,
    VersionError,
    ordinal,
)

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the check is off until an install switches it on.
A_CHECK_NOBODY_SWITCHED_ON_IS_A_DISCLOSURE_NOBODY_AGREED_TO: Final = (
    "A request to a release list tells whoever serves it that this product runs at the "
    "address the request left from, and when. On a product a client installs and owns, that is "
    "theirs to decide, so the default is to ask nobody and to say so, and the install switches "
    "the check on in its own configuration, where it can also point it at a copy inside its "
    "own network."
)

#: Why only https.
AN_ANSWER_ANYBODY_ON_THE_PATH_COULD_REWRITE_IS_NOT_ONE_TO_CALL_UP_TO_DATE: Final = (
    "The answer this list gives is the one a client reads before deciding not to update. Over "
    "plain http anybody between the server and the list can replace it with a list whose newest "
    "release is the one already running, and the panel would draw that as a tick. So a list "
    "that is not https is not asked, and the panel says why."
)

#: Why the route never awaits a look.
A_PAGE_NEVER_WAITS_FOR_THE_RELEASE_LIST: Final = (
    "A release list is somebody else's server, reached through the client's own network, and "
    "the slow answer is the one that arrives on the day the firewall changes. A route that "
    "waited for it put the fetch timeout in front of the screen on every load, so the page "
    "about whether to update was the page that hung. The look runs as a task beside the "
    "request, the request is answered from the last look that finished, and a first load says "
    "no look has finished yet, which is true and is not a tick."
)

#: Why a look is started by opening the screen.
A_LOOK_IS_STARTED_BY_A_READER_AND_NOT_BY_A_TIMER: Final = (
    "The answer is drawn in one place, the updates screen, so a look nobody opens that screen "
    "for is a request leaving the client's network with nobody to show the answer to, on a "
    "server that may not be administered at all that week. Started by somebody opening the "
    "screen, and no more often than the interval allows, every request that leaves has a reader "
    "waiting for what it learns."
)

# ------------------------------------------------------------------------ configuration
#: The variable that switches the check on. Read by `brain.settings.Settings.release_check`.
CHECK_VARIABLE: Final = "BRAIN_RELEASE_CHECK"

#: The variable naming a copy of the list to ask instead. Read by `Settings.release_feed_url`.
FEED_VARIABLE: Final = "BRAIN_RELEASE_FEED_URL"

#: Where this product's releases are listed, for every install. See the module docstring for
#: why it names the repository by number: `gh api repos/<owner>/<name> --jq .id` gives the
#: number, and `repositories/<number>` is the address the name-based one redirects to.
#: A hundred per page because the endpoint lists newest first and pages at thirty by default,
#: and the newest by number is what is wanted, which a hotfix to an older line can push down.
PRODUCT_RELEASES_URL: Final = "https://api.github.com/repositories/1357030077/releases?per_page=100"

#: How long a request may take before the list counts as unreachable. Nothing waits on this
#: except the background look itself, so it bounds how long a look holds a worker thread.
FEED_TIMEOUT_SECONDS: Final = 10

#: The largest answer read. A list of every release this product could publish in years is a
#: few hundred kilobytes; an answer past this is not a release list.
MAX_FEED_BYTES: Final = 2_000_000

#: How long an answer from the list is used before the next load of the screen looks again.
#:
#: **Chosen, and bounded from both sides rather than measured**, because there is no release
#: cadence to measure: nothing has been published. From above, it has to be far inside
#: `version_view.TELLING_GOES_OFF_AFTER_DAYS`, or an install whose screen is opened every day
#: would be drawn as stale with the check working. From below, every look is a request that
#: leaves the network and says somebody is administering the server, and the unauthenticated
#: releases endpoint allows sixty requests an hour from one address, which several installs
#: behind one company's egress share. Six hours puts a release published in the morning on the
#: screen the same working day and costs at most four looks a day per process.
LOOK_AGAIN_AFTER: Final = timedelta(hours=6)

#: How long after a look that got no answer the next load may try again. Shorter than a
#: successful look's interval so a firewall that has just been fixed is seen within the quarter
#: hour, and long enough that a list refusing every request is asked a few times an hour by
#: each process rather than once per load.
RETRY_A_FAILED_LOOK_AFTER: Final = timedelta(minutes=15)

#: What a fetch is: an address in, the body out, raising `OSError` or an HTTP error on failure.
Fetch = Callable[[str], bytes]


#: Why this module is handed its configuration rather than reading it.
CONFIGURATION_IS_READ_IN_ONE_PLACE: Final = (
    "Anything that differs between installs is configuration, and configuration is read in one "
    "place: brain.settings.Settings reads BRAIN_RELEASE_CHECK and BRAIN_RELEASE_FEED_URL, and "
    "whoever renders the panel hands both to feed_address. A module reading the environment for "
    "itself is a second reader of one value, and the place a fallback gets written where no "
    "client looks."
)


def feed_address(*, switched_on: bool, url: str) -> str:
    """The list this install asks, or an empty string when it asks nothing.

    Off means empty whatever `url` holds, so naming a copy of the list is not a second way to
    switch the check on: an install that set the copy's address and not the switch has agreed
    to nothing, and the panel's sentence names the switch.
    """
    if not switched_on:
        return ""
    return url.strip() or PRODUCT_RELEASES_URL


def newest_release(payload: object) -> str | None:
    """The newest published release a list names, or `None` when it names none this can order.

    Pure: the parsed JSON in, a tag out. Ordered with `version_view.ordinal`, the one ordering of
    two tags this repository has. No padding is needed for a maximum: a tuple that is a prefix of
    another sorts first, so `v1.4` sorts before `v1.4.0` and both before `v1.5`, and padding with
    zeros changes only which of two spellings of one release is returned.
    """
    found: list[tuple[tuple[int, ...], str]] = []
    for item in _entries(payload):
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


def notes_of(payload: object, tag: str) -> str:
    """Where the notes of the release tagged `tag` are read, or an empty string.

    Only an https address is returned, for the reason `Told` refuses anything else: the address
    becomes a link on the one screen somebody opens to decide whether to update, and a list
    somebody else serves chose it. Refused here as well as there so a hostile or broken copy of
    the list is a release with no link rather than a look that fails.
    """
    for item in _entries(payload):
        if str(item.get("tag_name", "")).strip() != tag:
            continue
        address = str(item.get("html_url", "")).strip()
        return address if address.startswith(NOTES_ARE_READ_OVER) else ""
    return ""


def _entries(payload: object) -> list[dict[str, object]]:
    """The objects in a list, or the one object a latest-release answer is."""
    items: list[object]
    if isinstance(payload, list):
        items = list(payload)
    elif isinstance(payload, dict):
        items = [payload]
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


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
            why=Unasked.SWITCHED_OFF,
            detail=(
                f"{CHECK_VARIABLE} is not switched on, so this install asks nothing outside its "
                "network about newer releases"
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
    return Told(tag=newest, at=now, by=_who_said(where), notes=notes_of(payload, newest))


def _who_said(where: str) -> str:
    """The source of a telling, in words a reader can weigh. The product's list by its name."""
    if where == PRODUCT_RELEASES_URL:
        return "the product's published list of releases, read by this install"
    return f"the release list at {where}, read by this install"


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


# ------------------------------------------------------------------ the background look
@dataclass(frozen=True)
class Look:
    """One finished look: which list was asked, and what it said."""

    address: str
    outcome: Told | Unanswered


def look_is_due(last: Look | None, now: datetime) -> bool:
    """Whether a load of the screen at `now` should start a look.

    A look that answered is used for `LOOK_AGAIN_AFTER` and one that did not for
    `RETRY_A_FAILED_LOOK_AFTER`. A look recorded later than `now` is not due, because from
    `now`'s point of view it has not happened yet and it is not stale.
    """
    if last is None:
        return True
    wait = LOOK_AGAIN_AFTER if isinstance(last.outcome, Told) else RETRY_A_FAILED_LOOK_AFTER
    return now - last.outcome.at >= wait


class ReleaseWatch:
    """This process's last look at the release list, and the one place another look starts.

    One per application object, which is one per worker process. `answer` does no I/O and never
    awaits: it returns what the last finished look said and, when one is due and none is
    running, starts one on the running event loop. See `A_PAGE_NEVER_WAITS_FOR_THE_RELEASE_LIST`.
    """

    def __init__(self, *, fetch: Fetch = https_fetch) -> None:
        self._fetch = fetch
        self._last: Look | None = None
        self._looking: asyncio.Task[None] | None = None

    @property
    def last(self) -> Look | None:
        """The last look that finished, or `None`."""
        return self._last

    @property
    def looking(self) -> bool:
        """Whether a look is running now."""
        return self._looking is not None and not self._looking.done()

    def answer(self, address: str, *, now: datetime) -> Told | Unanswered | None:
        """What the panel is handed at `now`, without waiting for anything.

        `address` is `feed_address`'s answer. Empty is the check switched off, answered at once
        and with nothing started. Otherwise `None` means no look at this address has finished
        by `now`, which the panel draws as not looked yet.

        Must be called on a running event loop when a look is due, which a route always is.
        """
        where = address.strip()
        if not where:
            return ask(where, fetch=self._fetch, now=now)
        if now.tzinfo is None:
            msg = "a naive now cannot be compared with the moment a look was made"
            raise VersionError(msg)
        last = self._last if self._last is not None and self._last.address == where else None
        if look_is_due(last, now) and not self.looking:
            self._looking = asyncio.get_running_loop().create_task(self._look(where, now))
        if last is None or last.outcome.at > now:
            return None
        return last.outcome

    async def _look(self, where: str, at: datetime) -> None:
        """Ask off the event loop and keep what came back, whatever came back.

        Every failure `ask` foresees is already an `Unanswered`. Anything else is caught here
        and kept as one too, because a task that raised would leave the last look as it was and
        the screen repeating an old answer with nothing to say the new look failed.
        """
        try:
            outcome = await asyncio.to_thread(ask, where, fetch=self._fetch, now=at)
        except Exception as error:
            log.warning("release list look failed", error=type(error).__name__)
            outcome = Unanswered(
                why=Unasked.UNREACHABLE,
                detail=f"asking {where} failed ({type(error).__name__})",
                at=at,
            )
        self._last = Look(address=where, outcome=outcome)
