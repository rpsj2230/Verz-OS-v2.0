"""The website widget's front door over HTTP: a stranger's browser asks for a session and is
handed one, or is told in one sentence why not.

`brain.channels.widget.WidgetSessions` decides everything here and had no caller: the allowlist
check before any window is touched, the two mint guards `brain.ops.limits.mint_widget_session`
owns, the short idle window and the hard bound, and the two registers of a refusal. This is the
one route that reaches it.

**No sign-in, and the origin is proved instead.** A website visitor has nothing to present, so
this is the second written exception to the rule that every route under the prefix
authenticates its caller (`MINTED_FOR_NOBODY`, held by `tests/unit/test_api_routes.py` beside
`brain.channel_routes.SIGNED_NOT_SIGNED_IN`). What it hands out is worth nothing on its own: the
session carries `gate.ingress.Unrecognised`, which holds no entitlement set, so a session is a
name for a browser and not a key to anything. What an anonymous visitor may read is M10.7.2's
question, and it is answered by a grant an administrator gives, never by this route.

**The allowlist is this install's `widget_origins`**, the same list CORS admits, read once per
process. A site that is not on it is answered 403 with the widget's own sentence and no window is
read or created; a site over one of the two guards is answered 429 with `Retry-After`. The
operator's sentence, which names the origin and the numbers, goes to the log and never to the
browser. See `brain.channels.widget.WidgetRefusal`.

**One store per process, and that is stated rather than solved here.** `WidgetSessions` keeps its
sessions and its mint windows in memory, so two replicas each count their own, and the ceiling
across a deployment is the replicas times the number. The module says so and names the seam that
closes it; this route does not pretend otherwise by holding a second copy in Valkey.

Rejected: minting on the first question instead of on a request of its own. A question arrives
with a body a person typed, and a refusal to mint would then be a refusal to read what they
asked, which is a worse thing to tell somebody than "this site is not set up".

Task ids: M10.5.5
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.channels.widget import (
    RefusedBecause,
    WidgetRefusal,
    WidgetSessions,
    allowed_origins,
)

log = structlog.get_logger(__name__)

#: Where a session is asked for.
WIDGET_SESSIONS_PATH: Final = "/widget/sessions"

#: The paths under the API prefix reached with no sign-in because the caller is nobody. Read by
#: `tests/unit/test_api_routes.py`, beside `brain.channel_routes.SIGNED_NOT_SIGNED_IN`.
MINTED_FOR_NOBODY: Final[frozenset[str]] = frozenset({API_PREFIX + WIDGET_SESSIONS_PATH})

#: The status each refusal is answered with.
REFUSAL_STATUS: Final = {RefusedBecause.ORIGIN_NOT_ALLOWED: 403, RefusedBecause.OVER_LIMIT: 429}

router = APIRouter(prefix=API_PREFIX, tags=["widget"])


class WidgetSessionView(BaseModel):
    """A session, as the embedding page holds it: the id to present, and when it ends."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: str
    expires_at: datetime
    absolute_expiry: datetime


def sessions_of(state: Any) -> WidgetSessions:
    """This process's widget sessions, made once from the install's allowlist.

    What a test or an install check installed, or one built from `settings.widget_origins` on
    first use and kept on the state, so the live count and the mint windows span requests.
    """
    found = getattr(state, "widget_sessions", None)
    if isinstance(found, WidgetSessions):
        return found
    settings = getattr(state, "settings", None)
    configured = tuple(getattr(settings, "widget_origins", ()) or ())
    made = WidgetSessions(allowed=allowed_origins(configured))
    state.widget_sessions = made
    return made


def refused(refusal: WidgetRefusal) -> JSONResponse:
    """The browser's answer to a refusal: the widget's public sentence, and a wait where one helps.

    The operator's `reason` is logged here and nowhere else. `Retry-After` only on the rate
    refusal: waiting changes nothing about an allowlist.
    """
    log.info("widget session refused", because=refusal.because.value, reason=refusal.reason)
    headers = {"Cache-Control": "no-store"}
    if refusal.because is RefusedBecause.OVER_LIMIT:
        headers["Retry-After"] = str(max(1, math.ceil(refusal.retry_after_seconds)))
    return JSONResponse(
        status_code=REFUSAL_STATUS[refusal.because],
        content=ErrorBody(message=refusal.public_message).model_dump(),
        headers=headers,
    )


@router.post(
    WIDGET_SESSIONS_PATH,
    status_code=201,
    response_model=WidgetSessionView,
    responses={
        **COMMON_RESPONSES,
        403: {"model": ErrorBody, "description": "This site is not on the install's widget list."},
        429: {"model": ErrorBody, "description": "Too many sessions from this site just now."},
    },
)
async def mint_session(
    request: Request, origin: Annotated[str, Header()] = ""
) -> WidgetSessionView | JSONResponse:
    """A session for the site the browser says it is on, or the widget's sentence for why not."""
    minted = sessions_of(request.app.state).mint(origin=origin, now=datetime.now(tz=UTC))
    if isinstance(minted, WidgetRefusal):
        return refused(minted)
    return WidgetSessionView(
        session=minted.session_id,
        expires_at=minted.expires_at,
        absolute_expiry=minted.absolute_expiry,
    )
