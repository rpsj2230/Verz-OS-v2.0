"""The install acceptance check for the website widget's front door: a listed site is handed a
session that holds nothing, an unlisted site is refused without a window being made, and a busy
site is told to wait.

The route is `brain.widget_routes.mint_session`, mounted on an application of the check's own
with the store the route would build for itself, and called through an in-process transport as
a browser on a website would call it. The check's allowlist is one origin nobody publishes, named
after the run, so it never depends on which sites this install lists and never touches their
windows or their live sessions: the store is the check's and is dropped when the check ends.

**What the check proves, and what it does not.** It proves the deployed image mints through the
widget's own guards: the allowlist before any window, the minute's allowance, and a session
carrying no entitlement set. It does not prove that the install's own `widget_origins` names the
right sites, which is a setting its owner chooses, nor anything an anonymous visitor may read,
which is M10.7.2 and `brain.ops.acceptance_checks_public`'s.

Nothing is written to the database and nothing leaves the process.

Task ids: M10.5.5
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 260

#: The one host no install serves, under which the check's origin is named.
RESERVED_HOST_SUFFIX: Final = ".acceptance.invalid"


@check(
    leaves=("M10.5.5",),
    sentence=(
        "The widget's session route, mounted as the install mounts it over an allowlist of one "
        "origin the run names, hands that origin a session that holds no reach, refuses an "
        "unlisted origin without making a rate window, and answers the mint past the minute's "
        "allowance with 429 and a wait, naming no origin and no figure."
    ),
)
async def a_widget_session_is_minted_for_a_listed_site_within_its_rate(
    h: Harness,
) -> None:
    import httpx
    from fastapi import FastAPI

    from brain.api import API_PREFIX
    from brain.channels.widget import WidgetSessions, allowed_origins
    from brain.gate.ingress import Unrecognised
    from brain.ops.limits import WIDGET_MINTS_PER_MINUTE
    from brain.widget_routes import WIDGET_SESSIONS_PATH, router

    listed = f"https://{h.word().lower()}{RESERVED_HOST_SUFFIX}"
    unlisted = f"https://{h.word().lower()}{RESERVED_HOST_SUFFIX}"
    store = WidgetSessions(allowed=allowed_origins((listed,)))
    app = FastAPI()
    app.include_router(router)
    app.state.widget_sessions = store
    path = f"{API_PREFIX}{WIDGET_SESSIONS_PATH}"

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://acceptance.invalid") as c:
        refused = await c.post(path, headers={"Origin": unlisted})
        if refused.status_code != 403 or "retry-after" in refused.headers:
            raise CheckFailedError("an unlisted site was not refused as not set up")
        if store.windows != WidgetSessions(allowed=frozenset()).windows:
            raise CheckFailedError("refusing an unlisted site made a rate window for it")
        minted = [
            await c.post(path, headers={"Origin": listed}) for _ in range(WIDGET_MINTS_PER_MINUTE)
        ]
        over = await c.post(path, headers={"Origin": listed})

    if any(one.status_code != 201 for one in minted):
        raise CheckFailedError("a listed site within its allowance was not handed a session")
    session = store.get(str(minted[0].json().get("session", "")), datetime.now(tz=UTC))
    if session is None or not isinstance(session.reach, Unrecognised):
        raise CheckFailedError("a minted session was not held as one carrying no reach")
    if over.status_code != 429 or int(over.headers.get("retry-after", "0")) < 1:
        raise CheckFailedError("the mint past the minute's allowance was not told to wait")
    said = str(over.json().get("message", ""))
    if listed in over.text or str(WIDGET_MINTS_PER_MINUTE) in said:
        raise CheckFailedError("the refusal a browser reads named the site or the allowance")
