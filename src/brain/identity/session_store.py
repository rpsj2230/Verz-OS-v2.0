"""`auth.session`: the sign-ins this installation has seen, and ending one of them.

`0003` built `auth.session`, its row-level security and the cascade that ends a disabled
principal's sessions, and nothing ever wrote a row. So the cascade ended nothing, the Sessions
screen the registry declares had nothing to list, and the one control M27.7.10 asks for, ending
somebody's sign-in because revoking a grant does not close it, had nothing to act on and nothing
that would have noticed it being pressed. This module is the store behind all three. It holds the
SQL and decides nothing: who may see a session and who may end one is
`brain.console.govern.open_sessions` and `may_end`, handed in as a callable where the decision has
to be taken under the row's lock.

**A session is recorded the first time a request arrives with it, not at sign-in.** Nothing on
the server is told when somebody signs in: the console runs the authorisation code flow against
the identity provider and the first thing this process sees is a token. So
`brain.identity.bearer.TokenAuthority.authenticate` asks `standing` on every request that carries
a `sid`, and a session never seen before is written then. A session opened before this version
was installed appears from its next request. See `A_SESSION_IS_SEEN_WHEN_IT_IS_FIRST_USED`.

**The ledger is the refusal as well as the listing, and that is the property the control rests
on.** Ending a session writes `ended_at` and nothing else, and a bearer token is valid because of
what is inside it, so ending a row changes nothing unless the next request asks the row. `standing`
is that asking. It reads one row by primary key, and writes one only the first time.

**It records the moment the session began as the token says it, and its hard end as the product's
ceiling.** `auth_time` where the token carries one and its issue time otherwise, which is
`bearer.started_at_of`; and `SESSION_ABSOLUTE_MAX` after that, which
`ops/keycloak/realm-export.json` sets the realm's own `ssoSessionMaxLifespan` to. The idle window
is the identity provider's to keep and is not recorded: a row updated on every request to slide
it would write to this table on every request anybody makes. See
`A_ROW_WRITTEN_ON_EVERY_REQUEST_IS_A_WRITE_NOBODY_ASKED_FOR`.

**Ending is one statement, stamped by the database and attributed in the same transaction.** The
update sets `ended_at` to `statement_timestamp()`, `end_reason` to `ended_from_console`, and only
on a row not already ended, so two administrators pressing the control at once end it once and the
second is told nothing was there. `brain.actor_id`, `brain.ent_hash` and `brain.trace_id` are set
first, and `0050`'s trigger reads them into the ledger entry it appends in the same transaction.

**The raw subject is not recorded.** `auth.session` has no column for it and none is added:
`brain.tables.identity` refuses to hold a channel identity anywhere, and the principal is what an
administrator needs to know whose session it is.

Task ids: M27.7.10
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import Select, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert, ReturningUpdate

from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.bearer import SessionStanding
from brain.identity.sessions import SESSION_ABSOLUTE_MAX
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.identity import PrincipalRow, SessionEndReason, SessionRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why a session is written when it is first used rather than when it opens.
A_SESSION_IS_SEEN_WHEN_IT_IS_FIRST_USED: Final = (
    "The identity provider opens a session and this process is not told: the console signs in "
    "against the realm and the first thing that arrives here is a token. So the row is written "
    "by the first request that carries the session's id, and a session nobody has used yet is "
    "not listed. The alternative, a hook at the identity provider calling in on every sign-in, "
    "needs a credential for this process at the realm, which nothing here holds and which would "
    "make every defect in this application a way to reach the identity provider."
)

#: Why the idle window is not kept on the row.
A_ROW_WRITTEN_ON_EVERY_REQUEST_IS_A_WRITE_NOBODY_ASKED_FOR: Final = (
    "Sliding an idle expiry here would update this row on every request anybody makes, which is "
    "a write on the busiest path in the system to keep a second copy of a clock the identity "
    "provider already enforces. The row keeps what cannot change, when the session began and "
    "the ceiling it cannot outlive, and a session that went idle at the realm stops arriving."
)

#: The channel a session with an id arrives on. `brain.api_routes.channel_for` gives a token
#: carrying a `sid` the console's ceiling, and a row on any other channel would disagree with it.
SESSION_CHANNEL: Final = Channel.CONSOLE

#: Why a session was ended when this store ends it.
ENDED_FROM_CONSOLE: Final = SessionEndReason.ENDED_FROM_CONSOLE


# --------------------------------------------------------------------- the shapes


@dataclass(frozen=True)
class StoredSession:
    """One sign-in that has not been ended, and the person it belongs to.

    `department` is the principal's primary department, carried so the console can place the
    row where a scope can be matched against it; `brain.console.govern.Placed` is the pairing.
    `second_factor` is what the first request made with the session proved, which is
    `bearer.assurance_from`'s answer when the row was written.
    """

    session_id: str
    principal_id: str
    display_name: str
    department: str | None
    channel: str
    second_factor: bool
    started_at: datetime
    expires_at: datetime

    def is_live(self, now: datetime) -> bool:
        """Begun, and not past its ceiling. An ended session is never loaded as one of these."""
        return self.started_at <= now < self.expires_at


@dataclass(frozen=True)
class EndedSession:
    """What ending one session wrote: whose it was, and the database's instant."""

    session_id: str
    principal_id: str
    ended_at: datetime


# ---------------------------------------------------------------- the decisions


def standing_of(
    recorded_principal: str, ended_at: datetime | None, principal_id: str
) -> SessionStanding:
    """What a recorded row says about a token from `principal_id` naming it.

    A row belonging to somebody else is refused before its ending is looked at, because a token
    naming another person's session is the failure worth naming in the log whichever way the row
    stands. Pure, so each outcome can be tested without a server.
    """
    if recorded_principal != principal_id:
        return SessionStanding.SOMEBODY_ELSES
    if ended_at is not None:
        return SessionStanding.ENDED
    return SessionStanding.OPEN


def stored_session(row: Mapping[str, Any]) -> StoredSession:
    """One joined row as the value the console decides over."""
    return StoredSession(
        session_id=row["id"],
        principal_id=row["principal_id"],
        display_name=row["display_name"],
        department=row["primary_department"],
        channel=row["channel"],
        second_factor=int(row["assurance"]) >= int(Assurance.STRONG),
        started_at=row["started_at"],
        expires_at=row["expires_at"],
    )


# ---------------------------------------------------------------- the statements


def one_session(session_id: str) -> Select[tuple[str, datetime | None]]:
    """Who a session was recorded against and whether it ended. By primary key."""
    return select(SessionRow.principal_id, SessionRow.ended_at).where(SessionRow.id == session_id)


def record_session(
    *,
    session_id: str,
    principal_id: str,
    assurance: Assurance,
    started_at: datetime,
) -> ReturningInsert[tuple[str]]:
    """A session seen for the first time, written once and never overwritten.

    `ON CONFLICT DO NOTHING` on the key, so two first requests racing each other write one row
    and the loser reads the winner's. Nothing a later request carries can move a row that exists,
    which is what keeps a replayed token from rewriting whose session a row is.
    """
    return (
        insert(SessionRow)
        .values(
            id=session_id,
            principal_id=principal_id,
            channel=SESSION_CHANNEL.value,
            assurance=int(assurance),
            started_at=started_at,
            expires_at=started_at + SESSION_ABSOLUTE_MAX,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(SessionRow.id)
    )


_LISTED: Final = (
    SessionRow.id,
    SessionRow.principal_id,
    PrincipalRow.display_name,
    PrincipalRow.primary_department,
    SessionRow.channel,
    SessionRow.assurance,
    SessionRow.started_at,
    SessionRow.expires_at,
)


def live_sessions(now: datetime, limit: int) -> Select[Any]:
    """Every session not ended and not past its ceiling, newest first, bounded.

    Joined to the principal for the name and the department the console places the row by.
    Ordered by when it began and then by id, so two readings of an unchanged table are one page.
    """
    return (
        select(*_LISTED)
        .join(PrincipalRow, PrincipalRow.id == SessionRow.principal_id)
        .where(SessionRow.ended_at.is_(None), SessionRow.expires_at > now)
        .order_by(SessionRow.started_at.desc(), SessionRow.id)
        .limit(limit)
    )


def one_live_session(session_id: str, now: datetime) -> Select[Any]:
    """One session that may still be ended, with its row locked until the transaction ends.

    Locked on the session and not the principal, so ending a session does not wait for somebody
    editing a person's record.
    """
    return (
        select(*_LISTED)
        .join(PrincipalRow, PrincipalRow.id == SessionRow.principal_id)
        .where(
            SessionRow.id == session_id,
            SessionRow.ended_at.is_(None),
            SessionRow.expires_at > now,
        )
        .with_for_update(of=SessionRow)
    )


def end_session(session_id: str) -> ReturningUpdate[tuple[datetime | None]]:
    """End one session that has not ended, stamped by the statement's own clock."""
    return (
        update(SessionRow)
        .where(SessionRow.id == session_id, SessionRow.ended_at.is_(None))
        .values(
            ended_at=func.statement_timestamp(),
            end_reason=ENDED_FROM_CONSOLE.value,
            updated_at=func.now(),
        )
        .returning(SessionRow.ended_at)
    )


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


# ------------------------------------------------------------------- the store


@dataclass(frozen=True)
class StoredSessions:
    """`auth.session`, read and written as the application role. Decides nothing."""

    sessions: async_sessionmaker[AsyncSession]

    async def standing(
        self,
        *,
        session_id: str,
        principal_id: str,
        assurance: Assurance,
        started_at: datetime,
        now: datetime,
    ) -> SessionStanding:
        """Record this session if it is new, and say whether a token from it may be used.

        Implements `brain.identity.bearer.SessionLedger`. `now` is accepted for that protocol
        and not read: whether a session has lapsed is the identity provider's to enforce, and the
        token has already been held to its own expiry.
        """
        del now
        async with self.sessions() as session, session.begin():
            found = (await session.execute(one_session(session_id))).one_or_none()
            if found is None:
                written = await session.execute(
                    record_session(
                        session_id=session_id,
                        principal_id=principal_id,
                        assurance=assurance,
                        started_at=started_at,
                    )
                )
                if written.first() is not None:
                    return SessionStanding.OPEN
                # Lost a race with another first request. Its row is the answer.
                found = (await session.execute(one_session(session_id))).one()
        recorded, ended_at = found
        return standing_of(recorded, ended_at, principal_id)

    async def open_sessions(
        self, *, now: datetime, limit: int
    ) -> tuple[tuple[StoredSession, ...], bool]:
        """Every live session, newest first, and whether the load came back full."""
        async with self.sessions() as session, session.begin():
            rows = (await session.execute(live_sessions(now, limit))).mappings().all()
        return tuple(stored_session(dict(row)) for row in rows), len(rows) >= limit

    async def end(
        self,
        session_id: str,
        *,
        may: Callable[[StoredSession], bool],
        ended_by: str,
        ent_hash: str,
        trace_id: str,
        now: datetime,
    ) -> EndedSession | None:
        """End one live session if `may` says so, or return None and write nothing.

        `may` is asked under the row's lock, so the session it judged is the session ended. None
        for a session that is not there, not live, not endable by the caller, or ended by
        somebody else first, and the four are one answer for the reason
        `brain.console.govern.A_CONTROL_THAT_REFUSES_DIFFERENTLY_SAYS_THE_SESSION_IS_THERE` gives.
        """
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(ACTOR_SETTING, ended_by))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            row = (
                (await session.execute(one_live_session(session_id, now))).mappings().one_or_none()
            )
            if row is None:
                return None
            record = stored_session(dict(row))
            if not may(record):
                return None
            stamped = (await session.execute(end_session(session_id))).scalar_one_or_none()
            if stamped is None:
                return None
        log.info("session.ended", principal=record.principal_id, ended_by=ended_by)
        return EndedSession(
            session_id=record.session_id, principal_id=record.principal_id, ended_at=stamped
        )
