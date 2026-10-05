"""The website widget's front door over HTTP: a stranger's browser asks for a session and is
handed one, or is told in one sentence why not; and asks a question and is answered from what the
install marked public, or told it was not found.

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

**A question is answered from knowledge marked public, and from nothing else** (M10.7.2). The
session names the site it was minted for, and a question presenting it from another is answered
as a session that has ended, as an expired one is. The search is
`brain.knowledge.document_tools.public_searcher`: the one search a person's question runs, at the
public reach, in a transaction running as `brain_public`. **What was found is handed back as the
passages themselves**, each with its document's title and section; **nothing found is
`brain.gate.abstain.NOT_FOUND_TEXT`**, the one sentence the answer lane says for a question about
something withheld and one about something absent, so a question about an unmarked document and
one about nothing at all get the same body, the same status and the same headers. See
`A_QUESTION_ABOUT_ANYTHING_UNMARKED_IS_ANSWERED_AS_NOTHING_FOUND`.

**No model writes the answer yet, and that is stated rather than implied.** The answer lane's
model step meters every attempt against a person's budget and routes by a person's reach, and a
visitor is neither; giving a stranger a model's words means deciding who pays for them, which is
a decision for the owner and not this route's. Until then a visitor reads the published passages,
which is what the marking agreed to show.

Task ids: M10.5.5, M10.7.2
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Annotated, Any, Final, cast

import structlog
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.audit.ledger import IDENTIFIER
from brain.channels.widget import (
    RefusedBecause,
    WidgetRefusal,
    WidgetSessions,
    allowed_origins,
    normalise_origin,
)
from brain.core.errors import Failed
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.knowledge.document_tools import QUESTION_CHARS, KnowledgePassage

log = structlog.get_logger(__name__)

#: Where a session is asked for.
WIDGET_SESSIONS_PATH: Final = "/widget/sessions"

#: Where a question is asked, with the session it belongs to.
WIDGET_QUESTIONS_PATH: Final = "/widget/questions"

#: The paths under the API prefix reached with no sign-in because the caller is nobody. Read by
#: `tests/unit/test_api_routes.py`, beside `brain.channel_routes.SIGNED_NOT_SIGNED_IN`.
MINTED_FOR_NOBODY: Final[frozenset[str]] = frozenset(
    {API_PREFIX + WIDGET_SESSIONS_PATH, API_PREFIX + WIDGET_QUESTIONS_PATH}
)

#: Why a question about something unmarked and one about nothing are one answer.
A_QUESTION_ABOUT_ANYTHING_UNMARKED_IS_ANSWERED_AS_NOTHING_FOUND: Final = (
    "A question is a probe, and an answer that says it cannot find one product and answers for "
    "another has told a competitor which products exist. So nothing found is NOT_FOUND_TEXT with "
    "no passages, whether the document is unmarked, personal, a draft or was never written, and "
    "the search reaches only marked documents, so it cannot tell those apart to begin with."
)

#: What a visitor is told when the session they present has ended, or was minted for another site.
SESSION_ENDED: Final = "This chat has ended. Open it again to start a new one."

#: What a visitor is told above the passages a question found.
FROM_WHAT_THIS_SITE_PUBLISHES: Final = "Here is what this site publishes about that."

#: The status each refusal is answered with.
REFUSAL_STATUS: Final = {RefusedBecause.ORIGIN_NOT_ALLOWED: 403, RefusedBecause.OVER_LIMIT: 429}

router = APIRouter(prefix=API_PREFIX, tags=["widget"])


class WidgetSessionView(BaseModel):
    """A session, as the embedding page holds it: the id to present, and when it ends."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: str
    expires_at: datetime
    absolute_expiry: datetime


class WidgetQuestion(BaseModel):
    """A visitor's question and the session it is asked in. The question is bound, never spliced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: str = Field(pattern=IDENTIFIER)
    question: str = Field(min_length=1, max_length=QUESTION_CHARS)


class WidgetPassageView(BaseModel):
    """One published passage, as a visitor reads it: its words and where they come from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    title: str
    section: str
    text: str


class WidgetAnswerView(BaseModel):
    """What a visitor is told: a sentence, and the passages it introduces, which may be none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    passages: list[WidgetPassageView]


def answer_of(found: Sequence[KnowledgePassage]) -> WidgetAnswerView:
    """The visitor's answer: the passages found, or `NOT_FOUND_TEXT` and none (M10.7.2).

    See `A_QUESTION_ABOUT_ANYTHING_UNMARKED_IS_ANSWERED_AS_NOTHING_FOUND`.
    """
    if not found:
        return WidgetAnswerView(answer=NOT_FOUND_TEXT, passages=[])
    return WidgetAnswerView(
        answer=FROM_WHAT_THIS_SITE_PUBLISHES,
        passages=[
            WidgetPassageView(
                document_id=one.document_id,
                title=one.title,
                section=one.section,
                text=one.document,
            )
            for one in found
        ],
    )


#: The search a visitor's question runs, as `public_searcher` hands it back.
PublicSearch = Callable[[str], Awaitable[tuple[KnowledgePassage, ...]]]


def public_search_of(state: Any) -> PublicSearch | None:
    """This process's public search, made once over the application's sessions, or None.

    What a test or an install check installed, or `public_searcher` over the application's
    sessions and this install's question embedder, kept on the state. None with no database.
    """
    found = getattr(state, "widget_search", None)
    if found is not None:
        return cast("PublicSearch", found)
    sessions = getattr(state, "db_sessions", None)
    if sessions is None:
        return None
    from brain.knowledge.document_tools import public_searcher
    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import question_embedder

    made = public_searcher(SessionRowSource(sessions), question_embedder())
    state.widget_search = made
    return made


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


@router.post(
    WIDGET_QUESTIONS_PATH,
    response_model=WidgetAnswerView,
    responses={
        **COMMON_RESPONSES,
        401: {"model": ErrorBody, "description": "The session has ended or is another site's."},
    },
)
async def ask(
    request: Request, body: WidgetQuestion, origin: Annotated[str, Header()] = ""
) -> WidgetAnswerView | JSONResponse:
    """A visitor's question, answered from knowledge marked public, or `NOT_FOUND_TEXT`.

    The session is looked at before it is extended, so a session presented from a site it was not
    minted for is not kept alive by the attempt. See the module docstring.
    """
    now = datetime.now(tz=UTC)
    sessions = sessions_of(request.app.state)
    held = sessions.get(body.session, now)
    if held is None or held.origin != normalise_origin(origin):
        return JSONResponse(
            status_code=401,
            content=ErrorBody(message=SESSION_ENDED).model_dump(),
            headers={"Cache-Control": "no-store"},
        )
    sessions.touch(body.session, now)
    search = public_search_of(request.app.state)
    if search is None:
        raise Failed("no database on this process")
    return answer_of(await search(body.question))
