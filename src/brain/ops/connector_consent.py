"""Where a consent waits for its vendor's answer, and what a refused consent leaves on the source.

`brain.connectors.oauth` is the exchange as data and `brain.connector_routes` the two console
routes; this is the state between them and the one mark a refusal leaves, both written through the
application's own login.

**A consent is taken, never read.** `StoredConsents.take` is one `UPDATE ... RETURNING` that sets
`used_at` on the row whose state digest, principal and expiry admit it, and returns what the
exchange needs. There is no read that could hand a row back without using it, so there is no window
in which two answers carrying one state could both be exchanged: the second finds the row used.
A state nobody issued, one already used, one issued to somebody else and one past its ten minutes
are all the same answer, `None`, because the person answering is told the same sentence for each.
See `brain.connectors.oauth.A_CONSENT_ANSWER_IS_TRUSTED_ONLY_FOR_THE_REQUEST_THAT_ASKED` and
`0180`, whose policies hold the same rule a second time inside the database.

**A consent the vendor refuses at the code is the source down, in words, on its health.**
`refused_consent` is the one failed attempt the consent route appends to the source's connection
through `StoredConsentHealth`, with
`brain.connectors.oauth.CONSENT_WITHDRAWN` as its sentence and the call as a refusal, through
`brain.ops.connector_sync.after_attempt`, so the health word and the schedule are the same rule a
refused renewal on the worker meets. Rejected: a column or a setting of its own for "consent
refused", which would be a second health a screen has to reconcile with the first.

Task ids: M11.8.6
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import ConnectorContractError
from brain.connectors.oauth import (
    CONSENT_LIFETIME_SECONDS,
    CONSENT_WITHDRAWN,
    ConsentStart,
    opened_verifier,
    sealed_verifier,
    state_digest,
)
from brain.connectors.throttle import CallOutcome
from brain.ops.connector_sync import Attempt, SyncOutcome, SyncState, after_attempt
from brain.ops.connector_sync_store import attempt_row, read_live, read_states
from brain.tables.audit import attributed_to
from brain.tables.oauth_consent import OAuthConsentRow

#: How long a consent may wait for its vendor's answer.
CONSENT_LIFETIME: Final = timedelta(seconds=CONSENT_LIFETIME_SECONDS)


@dataclass(frozen=True)
class TakenConsent:
    """A consent this install issued, taken by the person who started it: what the code needs."""

    connector: str
    return_address: str
    start: ConsentStart


class ConsentStates(Protocol):
    """Where a consent waits for its answer. `StoredConsents` is the database's."""

    async def issue(
        self,
        *,
        connector: str,
        principal_id: str,
        start: ConsentStart,
        return_address: str,
        now: datetime,
    ) -> None:
        """Hold this consent for `CONSENT_LIFETIME`, for this person alone."""
        ...

    async def take(self, *, state: str, principal_id: str, now: datetime) -> TakenConsent | None:
        """The consent this state names, used now, or None for every reason it cannot be."""
        ...


class StoredConsents:
    """`ConsentStates` over `ops.oauth_consent`, each statement attributed to the person."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    def __repr__(self) -> str:
        return "StoredConsents()"

    async def issue(
        self,
        *,
        connector: str,
        principal_id: str,
        start: ConsentStart,
        return_address: str,
        now: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await _attribute(session, principal_id)
            await session.execute(
                insert(OAuthConsentRow).values(
                    state_digest=state_digest(start.state),
                    connector=connector,
                    principal_id=principal_id,
                    return_address=return_address,
                    sealed_verifier=sealed_verifier(start),
                    issued_at=now,
                    expires_at=now + CONSENT_LIFETIME,
                )
            )

    async def take(self, *, state: str, principal_id: str, now: datetime) -> TakenConsent | None:
        try:
            digest = state_digest(state)
        except UnicodeError:
            return None
        async with self._sessions() as session, session.begin():
            await _attribute(session, principal_id)
            found = (
                await session.execute(
                    update(OAuthConsentRow)
                    .where(
                        OAuthConsentRow.state_digest == digest,
                        OAuthConsentRow.principal_id == principal_id,
                        OAuthConsentRow.used_at.is_(None),
                        OAuthConsentRow.expires_at > now,
                    )
                    .values(used_at=now)
                    .returning(
                        OAuthConsentRow.connector,
                        OAuthConsentRow.return_address,
                        OAuthConsentRow.sealed_verifier,
                    )
                )
            ).one_or_none()
        if found is None:
            return None
        try:
            start = opened_verifier(state, found.sealed_verifier)
        except ConnectorContractError:
            return None
        return TakenConsent(
            connector=found.connector, return_address=found.return_address, start=start
        )


async def _attribute(session: AsyncSession, principal_id: str) -> None:
    """The actor `0180`'s policies hold every row to, for this transaction only."""
    for statement in attributed_to(actor_id=principal_id, ent_hash="", trace_id=""):
        await session.execute(statement)


# ------------------------------------------------------------------ a refused consent's mark
@dataclass(frozen=True)
class LatestAttempt:
    """A source's live connection, by the id its attempts point at, and its newest attempt."""

    connection_id: uuid.UUID
    previous: SyncState | None


class ConsentHealth(Protocol):
    """Where a consent the vendor refused is said, on the source's health.

    Two halves, read and append, so the attempt itself is made by the route's own
    `refused_consent` call and the rule it follows is `after_attempt`'s, not this store's.
    """

    async def latest(self, connector: str) -> LatestAttempt | None:
        """The source's live connection and its newest attempt, or None with no live connection."""
        ...

    async def record(self, connection_id: uuid.UUID, attempt: Attempt) -> None:
        """Append one attempt to the connection's record."""
        ...


class StoredConsentHealth:
    """`ConsentHealth` over `ops.connector_sync`, through `brain.ops.connector_sync_store`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    def __repr__(self) -> str:
        return "StoredConsentHealth()"

    async def latest(self, connector: str) -> LatestAttempt | None:
        async with self._sessions() as session, session.begin():
            live = await read_live(session)
            one = next((row for row in live if row.connection.connector == connector), None)
            if one is None:
                return None
            return LatestAttempt(one.id, (await read_states(session)).get(one.id))

    async def record(self, connection_id: uuid.UUID, attempt: Attempt) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(attempt_row(connection_id, attempt))


def refused_consent(
    connector: str, previous: SyncState | None, interval: timedelta, now: datetime
) -> Attempt:
    """The attempt a consent the vendor refused leaves: failed, refused, and said in words.

    `after_attempt`'s rule, so a refused authorisation is down at once and the next read waits on
    the backoff it would after any refused key. See `CONSENT_WITHDRAWN`.
    """
    return after_attempt(
        connector=connector,
        started_at=now,
        finished_at=now,
        outcome=SyncOutcome.FAILED,
        detail=CONSENT_WITHDRAWN,
        interval=interval,
        previous=previous,
        call=CallOutcome.REJECTED,
    )
