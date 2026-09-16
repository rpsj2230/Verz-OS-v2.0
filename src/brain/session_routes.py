"""Sessions and sign-in links over HTTP: who is signed in, which account signs in as whom, and the
two controls that take one away.

`docs/screens.html` SCREEN 10 draws people with their grants and, beside them, what happened to a
leaver's sign-ins: "sessions killed, tokens rotated". The registry declares a Sessions screen, and
`brain.console.govern` holds the decisions behind it, `open_sessions` and `may_end`, written and
tested and reachable from nothing; the sign-in links an administrator makes had no screen at all.
This module serves both beside People in the Govern group (M27.7.10, M27.7.11).

**Nothing here decides who may see or end anything.** Whether the Sessions screen opens is
`brain.console.reads.permitted` over its registered read; which sessions it lists is
`govern.open_sessions` and which it offers the control on is `govern.may_end`. Whether the Sign-in
links screen opens is `brain.console.sign_in_links.may_see_links`, which is the authority to make a
link held over everything, and whether a link may be retired is
`brain.identity.sign_in_binding.decide_unlink`, taken under that store's lock. A route that filtered
a row itself would be a second answer to a question those modules answer, and the second answer is
the one nobody keeps in step.

**Ending a session is proved to reach the system, and the proof is three things.** The row:
`brain.identity.session_store.StoredSessions.end` sets `ended_at` and `ended_from_console` on a
session that was live, under its lock, only after `may_end` said yes about that very row. The ledger
entry: `0050`'s trigger appends `session_end` naming the administrator, their reach's digest and the
request, from the settings the store sets in the same transaction. And the refusal:
`brain.identity.bearer.TokenAuthority.authenticate` asks the ledger of sessions on every request
carrying a `sid`, so the next request made with the ended session is refused with the sentence every
refusal gets. See `ENDING_A_SESSION_IS_ONE_SITTING_AND_NOT_THE_PERSON`.

**Unlinking is the same three things over the other table.** `SignInBindings.unlink` retires the
link, `0047`'s trigger records `sign_in` retired with the administrator named, and the next request
from that account finds nobody in `brain.identity.principal_directory` and is refused. The last
administrator's link is refused with a sentence saying why, as a 409 carrying it, because it is
something the administrator has to act on and names nobody else.

**Every other refusal over a control is one refusal.** A caller who may not end a session, a session
out of their reach, one already ended, one past its ceiling and one that never existed are one 404,
which is `govern.A_CONTROL_THAT_REFUSES_DIFFERENTLY_SAYS_THE_SESSION_IS_THERE`. A caller who may not
unlink and a principal with no link are one 404 for the reason `brain.sign_in_routes` gives about a
principal who is not here.

**The authority is asked cheaply before any store is reached for, and properly under the lock.**
Straight from `brain.govern_routes`: a caller holding no authority is refused identically on a
process with a database and on one without, so nobody learns this deployment's state from the
difference between a 404 and a 500.

**No count of anything, anywhere.** Both listings are filtered per caller or answered whole, and
`truncated` says a load came back full, computed against what was loaded rather than what survived,
for the reason every listing in this application gives.

**The sentences are served, not written in the console.** What ending a session does, where the
account a person signs in with is kept, and why the last administrator's link stays are facts this
side knows, so they travel on the response, which is `brain.skill_routes`' arrangement: the day a
fact changes, the sentence changes in the same commit.

Task ids: M27.7.10, M27.7.11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated, Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.govern import SESSION_CONTROL, Placed, may_end, open_sessions
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.sign_in_links import (
    THE_ACCOUNT_IS_KEPT_AT_THE_IDENTITY_PROVIDER_AND_NOT_HERE,
    THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK,
    UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST,
    link_rows,
    may_see_links,
)
from brain.core.errors import Absent, Failed
from brain.identity.roles import SESSION_ID_PATTERN
from brain.identity.session_store import (
    EndedSession,
    StoredSession,
    StoredSessions,
)
from brain.identity.sign_in_binding import SignInLink, Unlinked
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: What ending a session does, and what it does not. Served on the listing.
ENDING_A_SESSION_IS_ONE_SITTING_AND_NOT_THE_PERSON: Final = (
    "Ending a session refuses every request made with that sign-in from the next one on. It "
    "removes no grant and does not stop the person signing in again, which starts a new session; "
    "to stop that, take away their grants or unlink their sign-in. The identity provider's own "
    "session is not ended from here, so they may have to sign out there before signing in again."
)

#: What the listing can and cannot show, served beside it.
A_SESSION_APPEARS_FROM_ITS_FIRST_REQUEST: Final = (
    "A session appears here from the first request it makes to this system, not from the moment "
    "somebody signs in, so a sign-in nobody has used yet is not listed."
)

# ----------------------------------------------------------------- the screens

#: The registered screen whose read decides whether the sessions listing opens.
SESSIONS_SCREEN: Final = "sessions"

#: The name the links screen is refused under. Not a registered screen: see
#: `brain.console.sign_in_links` for why its authority is the one that makes a link.
SIGN_IN_LINKS_SCREEN: Final = "sign-in links"

#: The most rows one listing loads. A resource bound and not a permission one.
MAX_ROWS: Final = 500
DEFAULT_ROWS: Final = 200


# ------------------------------------------------------------------- the shapes


class SessionView(BaseModel):
    """One live session, and whether this reader is offered the control over it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    principal_id: str
    display_name: str
    department: str | None
    second_factor: bool
    signed_in_at: datetime
    lapses_at: datetime
    #: The session this very request was made with.
    yours: bool
    #: `govern.may_end` said yes. Presentation only: the control is decided again when pressed.
    endable: bool


class SessionsPage(BaseModel):
    """Every live session this reader may see, and the two sentences the screen says."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[SessionView]
    #: The load came back full. Never how much more there is.
    truncated: bool
    ending: str = ENDING_A_SESSION_IS_ONE_SITTING_AND_NOT_THE_PERSON
    appears: str = A_SESSION_APPEARS_FROM_ITS_FIRST_REQUEST


class SessionEnding(BaseModel):
    """Which session to end. An id, and nothing that could say whose or why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1, max_length=120, pattern=SESSION_ID_PATTERN)


class SessionEnded(BaseModel):
    """What was ended, whose it was, and the database's instant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    principal_id: str
    ended_at: datetime


class SignInLinkView(BaseModel):
    """One person who can sign in, since when, and whether their link is the last way in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    department: str | None
    linked_at: datetime
    last_administrator: bool
    #: The reader's own link.
    yours: bool


class SignInLinksPage(BaseModel):
    """Every live sign-in link, and the sentences the screen says about what it cannot show."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[SignInLinkView]
    truncated: bool
    account: str = THE_ACCOUNT_IS_KEPT_AT_THE_IDENTITY_PROVIDER_AND_NOT_HERE
    unlinking: str = UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST
    last_administrator: str = THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK


class UnlinkAsked(BaseModel):
    """Whose sign-in link to retire."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)


class UnlinkView(BaseModel):
    """What came of it, in the store's word and in a sentence. Names nobody but the one asked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    outcome: Unlinked
    sentence: str


# ------------------------------------------------------------------- the stores


@runtime_checkable
class SessionStore(Protocol):
    """What these routes need of `auth.session`. `StoredSessions` implements it."""

    async def open_sessions(
        self, *, now: datetime, limit: int
    ) -> tuple[tuple[StoredSession, ...], bool]: ...

    async def end(
        self,
        session_id: str,
        *,
        may: Callable[[StoredSession], bool],
        ended_by: str,
        ent_hash: str,
        trace_id: str,
        now: datetime,
    ) -> EndedSession | None: ...


@runtime_checkable
class SignInLinkStore(Protocol):
    """What these routes need of `auth.principal_identity`. `SignInBindings` implements it."""

    async def links(self, *, limit: int) -> tuple[tuple[SignInLink, ...], bool]: ...

    async def administrators_linked(self, now: datetime) -> frozenset[str]: ...

    async def unlink(
        self,
        principal_id: str,
        *,
        unlinked_by: str,
        now: datetime,
        ent_hash: str = "",
        trace_id: str = "",
    ) -> Unlinked: ...


def session_store_of(request: Request) -> SessionStore:
    """The sessions this process reads, or one fault identical for every caller.

    `app.state.session_store` when something put one there, and the database otherwise, which is
    `brain.govern_routes._require_console_reads`' arrangement: nothing in `brain.app` sets it.
    """
    found = getattr(request.app.state, "session_store", None)
    if isinstance(found, SessionStore):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredSessions(factory)


def link_store_of(request: Request) -> SignInLinkStore:
    """`app.state.sign_in_bindings`, built beside the gate in `brain.app.lifespan`, or a fault."""
    found = getattr(request.app.state, "sign_in_bindings", None)
    if isinstance(found, SignInLinkStore):
        return found
    raise Failed("no sign-in bindings store on this process")


# ---------------------------------------------------------------- the projections


def placed_session(record: StoredSession) -> Placed[StoredSession]:
    """One session paired with the row its person sits in.

    The empty mapping when the principal carries no department, which fails closed for a reader
    whose grant is scoped: `brain.govern_routes.placed_grant` makes the same choice for a grant.
    """
    return Placed(
        record=record,
        where={} if record.department is None else {"department": record.department},
    )


def session_view(one: Placed[StoredSession], *, endable: bool, current: str | None) -> SessionView:
    record = one.record
    return SessionView(
        session_id=record.session_id,
        principal_id=record.principal_id,
        display_name=record.display_name,
        department=record.department,
        second_factor=record.second_factor,
        signed_in_at=record.started_at,
        lapses_at=record.expires_at,
        yours=current is not None and record.session_id == current,
        endable=endable,
    )


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.approval_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable(what: str) -> Absent:
    """The refusal a screen makes. Names the screen and never a row or the caller."""
    return Absent(f"the {what} screen is not answerable for this caller")


def _no_session_here() -> Absent:
    """The one refusal the control makes. See the module docstring."""
    return Absent("that session is not endable by this caller")


def _no_link_here() -> Absent:
    """The one refusal the unlink makes for a caller without authority and a principal unlinked."""
    return Absent("no sign-in link is removable here for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["sessions"])


# ------------------------------------------------------------------- sessions


@router.get("/govern/sessions", response_model=SessionsPage, responses=COMMON_RESPONSES)
async def sessions_page(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = DEFAULT_ROWS,
) -> SessionsPage:
    """Every live session this reader may see, newest first.

    The screen's question first and the database second. `truncated` is the load having come back
    full, computed against what was loaded rather than what `open_sessions` kept, because the second
    would be a count of what the decision withheld spelled as a boolean.
    """
    if not permitted(screen(SESSIONS_SCREEN).read, asked.reach, asked.now):
        log.info("sessions screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(SESSIONS_SCREEN)

    store = session_store_of(request)
    loaded, full = await store.open_sessions(now=asked.now, limit=limit)
    shown = open_sessions([placed_session(one) for one in loaded], asked.reach, asked.now)
    current = asked.caller.claims.session_id
    return SessionsPage(
        items=[
            session_view(one, endable=may_end(one, asked.reach, asked.now), current=current)
            for one in shown
        ],
        truncated=full,
    )


@router.post("/govern/sessions/end", response_model=SessionEnded, responses=COMMON_RESPONSES)
async def end_session(request: Request, body: SessionEnding, asked: Asked) -> SessionEnded:
    """End one session this reader may see and may end. A row, a ledger entry and a refusal.

    The control's capability is asked before a store is reached for; see the module docstring on
    the order. Then the store locks the row and asks `open_sessions` and `may_end` about that row,
    both, because a control is pressed by whatever was posted rather than by what was offered, and
    a session the reader may not see must not be endable by somebody who guessed its id.
    """
    if asked.reach.scope_for(SESSION_CONTROL, asked.now) is None:
        log.info("session not endable", principal=asked.caller.principal.id)
        raise _no_session_here()

    store = session_store_of(request)
    reach, now = asked.reach, asked.now

    def may(record: StoredSession) -> bool:
        placed = placed_session(record)
        return bool(open_sessions([placed], reach, now)) and may_end(placed, reach, now)

    ended = await store.end(
        body.session_id,
        may=may,
        ended_by=asked.caller.principal.id,
        ent_hash=reach.ent_hash(),
        trace_id=_trace_id(),
        now=now,
    )
    if ended is None:
        log.info("session end refused", principal=asked.caller.principal.id)
        raise _no_session_here()
    return SessionEnded(
        session_id=ended.session_id, principal_id=ended.principal_id, ended_at=ended.ended_at
    )


# ------------------------------------------------------------------- sign-in links


def link_views(
    links: Sequence[SignInLink], administrators: frozenset[str], reader: str
) -> list[SignInLinkView]:
    return [
        SignInLinkView(
            principal_id=row.principal_id,
            display_name=row.display_name,
            department=row.department,
            linked_at=row.linked_at,
            last_administrator=row.last_administrator,
            yours=row.principal_id == reader,
        )
        for row in link_rows(links, administrators=administrators)
    ]


@router.get("/govern/sign-ins", response_model=SignInLinksPage, responses=COMMON_RESPONSES)
async def sign_in_links_page(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = DEFAULT_ROWS,
) -> SignInLinksPage:
    """Every person who can sign in, since when, and which link is the last administrator's."""
    if not may_see_links(asked.reach, asked.now):
        log.info("sign-in links not answerable", principal=asked.caller.principal.id)
        raise _not_answerable(SIGN_IN_LINKS_SCREEN)

    store = link_store_of(request)
    links, full = await store.links(limit=limit)
    administrators = await store.administrators_linked(asked.now)
    return SignInLinksPage(
        items=link_views(links, administrators, asked.caller.principal.id),
        truncated=full,
    )


_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": UnlinkView, "description": "Not unlinked, and why, naming nobody else."},
}


@router.post("/govern/sign-ins/unlink", response_model=UnlinkView, responses=_TOLD)
async def unlink_sign_in(request: Request, body: UnlinkAsked, asked: Asked) -> JSONResponse:
    """Retire one person's sign-in link, unless it is the last administrator's."""
    if not may_see_links(asked.reach, asked.now):
        log.info("sign-in unlink refused", reason="not_an_administrator")
        raise _no_link_here()

    store = link_store_of(request)
    outcome = await store.unlink(
        body.principal_id,
        unlinked_by=asked.caller.principal.id,
        now=asked.now,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if outcome is Unlinked.NOT_LINKED:
        raise _no_link_here()
    if outcome is Unlinked.LAST_ADMINISTRATOR:
        view = UnlinkView(
            principal_id=body.principal_id,
            outcome=outcome,
            sentence=THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK,
        )
        return JSONResponse(status_code=409, content=view.model_dump(mode="json"))
    view = UnlinkView(
        principal_id=body.principal_id,
        outcome=outcome,
        sentence=UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST,
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
