"""The install acceptance check for Search Console: a site connected, indexed and asked, no socket.

A Search Console site is proved the way `brain.ops.acceptance_checks_google` proves a Google
Analytics property, and with the same steps, imported from there rather than copied: a site made up
for the run is connected inside the check's transaction through the store the Connectors screen's
routes call, the worker's own `brain.ops.connector_sync_run.attempt` reads it from the account's
site list with a token a generated key file bought, and it is asked about through the answer lane
and through its figure tool, both built by the application's own functions over a live reader over
the same connection.

**A module of its own, so the Install page places it.** Each check module declares where its
checks stand (`brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`), and this one
stands after Google Analytics'. Rejected: keeping the check beside Analytics' in one module, which
gives the two leaves one place on the page and makes the page order a fact about which function was
written first.

**What is Search Console's own.** The site list names the connected site and one more the account
can see, and only the connected one may be kept. The clicks on one day inside the last 28 are a
number minted for the run, and so are the clicks the figure tool is answered with for last month:
each is told to the reader granted it only after Google was asked, and afterwards the install's
index audit finds neither in any table. A reader without the site, and one holding the site's
capability in the other department, are told what a reader asking about no site is told.

**The check steps aside where the install has Search Console connected.** Connecting a source that
is connected already is refused, for `A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`'s reason.

Task ids: M11.7.2
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import _search
from brain.ops.acceptance_checks_google import (
    TOOL_PERIOD,
    A,
    _connect_and_read,
    _figure_tool,
    _KeyFiles,
    _no_subject,
    _prose,
    _reach,
    _route_asker,
    _three_readers,
    a_key_file,
)
from brain.ops.acceptance_checks_sources import _connection
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Mapping

    from brain.ops.connector_sync_run import SourceAnswer

# ------------------------------------------------------------------ written-down reasons
#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 340

#: What the check says where the install has Search Console connected already.
SEARCH_CONSOLE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Search Console connected already, so the check does not connect it again "
    "and does not ask about it"
)

# ------------------------------------------------------------------------ the figures
#: The range and figure the check asks for, as a question names them.
ASKED_SEARCH_FIGURE: Final = "clicks_last_28_days"


# ------------------------------------------------ a connected site answers its figures
@dataclass
class _SearchConsole:
    """Google's token endpoint and the Search Console API as recorded answers. No socket.

    The site list names the connected site and one more the account can see; a search is answered
    by its dimension, the day by day one carrying the check's clicks on one day inside the last 28;
    the sitemaps carry no problems. Every call a question makes is counted, and the worker's list
    read is not one of them.
    """

    site: str
    other_site: str
    clicks_on: str
    clicks: int
    range_clicks: int = 0
    report_calls: int = 0
    ranges: list[tuple[str, str]] = field(default_factory=list)
    tokens: list[bytes] = field(default_factory=list, repr=False)
    headers: list[dict[str, str]] = field(default_factory=list, repr=False)

    def calls_made(self) -> int:
        """How many report calls were made so far. A method so the count is read when asked."""
        return self.report_calls

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        self.headers.append(dict(headers))
        if url.endswith("/webmasters/v3/sites"):
            listed = {
                "siteEntry": [
                    {"siteUrl": self.site, "permissionLevel": "siteOwner"},
                    {"siteUrl": self.other_site, "permissionLevel": "siteOwner"},
                ]
            }
            return SourceAnswer(status=200, headers={}, body=json.dumps(listed).encode())
        if url.endswith("/sitemaps"):
            self.report_calls += 1
            return SourceAnswer(status=200, headers={}, body=b"{}")
        return SourceAnswer(status=404, headers={}, body=b"{}")

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        from brain.connectors.google_token import GOOGLE_TOKEN_URL
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        if url == GOOGLE_TOKEN_URL:
            self.tokens.append(body)
            issued = {"access_token": f"ya29.{secrets.token_hex(8)}", "token_type": "Bearer"}
            return SourceAnswer(status=200, headers={}, body=json.dumps(issued).encode())
        self.headers.append(dict(headers))
        if not url.endswith("/searchAnalytics/query"):
            return SourceAnswer(status=404, headers={}, body=b"{}")
        self.report_calls += 1
        asked = json.loads(body)
        dimension = (asked.get("dimensions") or [None])[0]
        rows: list[dict[str, Any]] = []
        if dimension == "date":
            rows = [{"keys": [self.clicks_on], "clicks": self.clicks, "impressions": self.clicks}]
        elif dimension is None:
            self.ranges.append((asked["startDate"], asked["endDate"]))
            rows = [{"clicks": self.range_clicks, "impressions": self.range_clicks}]
        answered = {"rows": rows} if rows else {}
        return SourceAnswer(status=200, headers={}, body=json.dumps(answered).encode())


@check(
    leaves=("M11.7.2",),
    sentence=(
        "A Search Console site made up for the check is connected and its name read by the worker "
        "from the account's site list with a token its key file bought. On Ask, and through its "
        "figure tool for last month, readers without the site get what a missing site gets, the "
        "granted reader gets clicks read when asked, and no figure is in any table."
    ),
)
async def a_search_console_site_answers_its_figures_live_and_keeps_none(h: Harness) -> None:
    from brain.connectors import search_console
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of
    from brain.ops.connector_store import live
    from brain.ops.connector_sync import SyncOutcome

    source, entity = search_console.SEARCH_CONSOLE, search_console.ENTITY_SITE
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(SEARCH_CONSOLE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()

    # The site, its name a word nothing else holds, and its clicks a number minted for the run.
    name = f"{h.word().lower()}.example"
    site = f"{search_console.DOMAIN_PROPERTY_PREFIX}{name}"
    canary = 10**14 + secrets.randbelow(9 * 10**14)
    ranged = 10**14 + secrets.randbelow(9 * 10**14)
    clicked = (h.now.date() - timedelta(days=2)).isoformat()
    other = f"{search_console.DOMAIN_PROPERTY_PREFIX}{h.word().lower()}.example"
    google = _SearchConsole(
        site=site, other_site=other, clicks_on=clicked, clicks=canary, range_clicks=ranged
    )
    keys = _KeyFiles(a_key_file())
    connection = _connection(
        h,
        source,
        {search_console.SITE_SETTING: site, search_console.DEPARTMENT_SETTING: A},
    )

    # Connected as the Connectors screen's route connects it, and read as the worker reads it.
    done = await _connect_and_read(h, connection, keys, google)
    if done.outcome is not SyncOutcome.SYNCED or done.records != 1:
        raise CheckFailedError("the worker did not keep the connected site alone from its list")
    if len(google.tokens) != 1 or not _no_subject(google.tokens[0]) or google.calls_made():
        raise CheckFailedError("the worker's read was not one token for the account and no call")
    if any("PRIVATE KEY" in json.dumps(one) for one in google.headers):
        raise CheckFailedError("a header carried the key file")

    ask = await _route_asker(h, connection, entity, keys, google)

    def asking(named: str) -> str:
        return QUESTION_SHAPES[0].format(label=label_of(ASKED_SEARCH_FIGURE), slot=named)

    granted, without, elsewhere = await _three_readers(
        h, entity, named_by=search_console.LABEL_FIELD, figure=ASKED_SEARCH_FIGURE
    )

    # Readers without the site are told what a site that is not there is told.
    for reader in (without, elsewhere):
        refused = await ask(reader, asking(name))
        nobody = await ask(reader, asking(f"{h.word().lower()}.example"))
        if refused.composed is not None or str(canary) in _prose(refused):
            raise CheckFailedError("a site's figure was told to a reader not granted it")
        if _prose(refused) != _prose(nobody):
            raise CheckFailedError("a site a reader may not see was told apart from none")

    # The clicks, read from Search Console when they were asked, for the reader granted them.
    told = await ask(granted, asking(name))
    if told.composed is None or str(canary) not in _prose(told):
        raise CheckFailedError("a connected site's clicks were not told to a reader granted them")
    if google.calls_made() != len(
        search_console.SearchConsoleReport().request_for(
            entity,
            search_console.site_id_of(site),
            settings=connection.settings,
            today=h.now.date(),
            window=None,
        )
    ):
        raise CheckFailedError("the site's figures were not read from Google when they were asked")

    # The figure tool, as a workflow's step calls it: last month, read live, at the caller's reach.
    from brain.connectors.date_range import RangeRequest, window_of
    from brain.knowledge.connector_figures import FIGURE_TOOL_NAMES

    tool = _figure_tool(h, connection, keys, google, FIGURE_TOOL_NAMES[source])
    for reader in (without, elsewhere):
        found = await tool(
            RangeRequest(period=TOOL_PERIOD), entitlement=await _reach(h, reader), now=h.now
        )
        if found.records:
            raise CheckFailedError("the figure tool read a site for a reader not granted it")
    found = await tool(
        RangeRequest(period=TOOL_PERIOD), entitlement=await _reach(h, granted), now=h.now
    )
    period = window_of(TOOL_PERIOD, today=h.now.date())
    if google.ranges != [(period.start.isoformat(), period.end.isoformat())]:
        raise CheckFailedError("the site's figure tool did not ask for the range it was given")
    if [one.model_dump().get("clicks") for one in found.records] != [str(ranged)]:
        raise CheckFailedError("the site's figure tool did not hand back the range's clicks")

    # Nothing either report returned was kept anywhere.
    if await _search(h, str(canary)) or await _search(h, str(ranged)):
        raise CheckFailedError("a search figure read live was found in a table")
