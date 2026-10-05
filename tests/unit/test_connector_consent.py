"""A consent waits for its vendor's answer once, for the person who started it, and briefly.

`brain.ops.connector_consent` over `ops.oauth_consent` (`0180`), against PostgreSQL at head and as
the application's role (`brain.session.make_application_sessions`, which requests are served by),
so the table's policies are what is being asked as well as the store's statement. And the one
mark a refused consent leaves on the source's health, which is `after_attempt`'s rule. Every
refusal here has a sibling that takes the consent.

Task ids: M11.8.6
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import HealthState
from brain.connectors.oauth import (
    CONSENT_LIFETIME_SECONDS,
    CONSENT_WITHDRAWN,
    ConsentKind,
    ConsentStart,
    new_consent,
    state_digest,
)
from brain.ops.connector_consent import (
    CONSENT_LIFETIME,
    StoredConsentHealth,
    StoredConsents,
    TakenConsent,
    refused_consent,
)
from brain.ops.connector_sync import SyncOutcome
from brain.session import make_app_engine, make_application_sessions
from brain.tables.audit import attributed_to
from brain.tables.oauth_consent import (
    DIGEST_PATTERN,
    KIND_CHARS,
    SEALED_CHARS,
    OAuthConsentRow,
)
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_tables import MIGRATION_OAUTH_CONSENT, migration_module

#: A clock far from any wall clock, for CLAUDE.md's reason about dates in fixtures.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
ME: Final = "u_admin"
SOMEBODY_ELSE: Final = "u_other"
BACK: Final = "https://console.example/connector-consent"


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_application_sessions(engine))
        finally:
            await engine.dispose()

    return run(go)


def issue(
    url: str,
    start: ConsentStart,
    *,
    by: str = ME,
    at: datetime = NOW,
    kind: ConsentKind = ConsentKind.SOURCE,
) -> None:
    through(
        url,
        lambda sessions: StoredConsents(sessions).issue(
            connector="xero", principal_id=by, start=start, return_address=BACK, now=at, kind=kind
        ),
    )


def take(url: str, state: str, *, by: str = ME, at: datetime = NOW) -> object:
    return through(
        url,
        lambda sessions: StoredConsents(sessions).take(state=state, principal_id=by, now=at),
    )


# ------------------------------------------------------------------ the table and the model
def test_the_table_and_its_model_hold_one_shape() -> None:
    """The migration's widths and grammars, copied for `0009`'s reason, equal the model's. Delete
    this and a sealed verifier the model accepts can be refused by the table, or the reverse."""
    from brain.audit.ledger import IDENTIFIER
    from brain.connectors.oauth import MAX_RETURN_ADDRESS_CHARS
    from brain.ops.credentials import CONNECTOR_NAME_PATTERN
    from brain.tables.connector_connection import CONNECTOR_CHARS
    from brain.tables.identity import PRINCIPAL_ID_CHARS

    made = migration_module(MIGRATION_OAUTH_CONSENT)
    assert (made.DIGEST_PATTERN, made.SEALED_CHARS) == (DIGEST_PATTERN, SEALED_CHARS)
    assert made.RETURN_ADDRESS_CHARS == MAX_RETURN_ADDRESS_CHARS
    assert (made.CONNECTOR_CHARS, made.CONNECTOR_NAME_PATTERN) == (
        CONNECTOR_CHARS,
        CONNECTOR_NAME_PATTERN,
    )
    assert (made.IDENTIFIER, made.PRINCIPAL_ID_CHARS) == (IDENTIFIER, PRINCIPAL_ID_CHARS)
    assert not [one for one in made.GRANTS if "DELETE" in one]
    assert "GRANT UPDATE (used_at) ON ops.oauth_consent TO brain_app" in made.GRANTS
    assert tuple(one.value for one in ConsentKind) == made.KINDS
    assert made.KIND_CHARS == KIND_CHARS >= max(len(one.value) for one in ConsentKind)


def test_a_consent_waits_ten_minutes_and_no_longer() -> None:
    """The lifetime the table holds a consent for is the one `brain.connectors.oauth` states, and
    ten minutes: long enough to sign in at a vendor and short enough that a code intercepted on the
    way back is worthless by the time anybody could use it. Delete this and the lifetime can grow
    to a day in a debugging session."""
    assert CONSENT_LIFETIME == timedelta(seconds=CONSENT_LIFETIME_SECONDS) == timedelta(minutes=10)


def test_a_consent_the_vendor_refused_leaves_the_source_down_in_words() -> None:
    """The attempt a refused consent appends is a refusal, down at once, with
    `CONSENT_WITHDRAWN` as its sentence, by `after_attempt`'s rule. Delete this and a consent the
    vendor refused leaves the source looking healthy until the next scheduled read."""
    done = refused_consent("xero", None, timedelta(minutes=15), NOW)
    assert (done.outcome, done.health, done.detail) == (
        SyncOutcome.FAILED,
        HealthState.DOWN,
        CONSENT_WITHDRAWN,
    )
    assert done.consecutive_failures == 1 and done.next_attempt_at > NOW


# ------------------------------------------------------------------ against the database
@pytest.mark.needs_db
def test_a_consent_is_taken_once_by_its_own_person_before_it_expires() -> None:
    """**The single-use rule.** The person who started a consent takes it once, within its
    lifetime, and gets back the verifier its state sealed; a second take, a take by somebody else,
    a take past the lifetime and a take of a state never issued all come back as nothing, and the
    one by somebody else does not use the consent up. Delete this and a replayed or stolen answer
    can be exchanged."""
    with at_head("brain_oauth_consent_once") as url:
        start = new_consent()
        issue(url, start)
        assert take(url, start.state, by=SOMEBODY_ELSE) is None
        assert take(url, new_consent().state) is None
        found = take(url, start.state)
        assert isinstance(found, TakenConsent)
        assert (found.connector, found.return_address, found.start) == ("xero", BACK, start)
        assert take(url, start.state) is None

        late = new_consent()
        issue(url, late)
        assert take(url, late.state, at=NOW + CONSENT_LIFETIME) is None
        assert take(url, late.state, at=NOW + CONSENT_LIFETIME - timedelta(seconds=1)) is not None


@pytest.mark.needs_db
def test_a_consent_is_answered_as_the_kind_it_was_started_as_and_the_kind_never_changes() -> None:
    """A person's own consent is taken back as a person's own and a source's as a source's, read
    from the row rather than from anything the answer carries; and the application role cannot
    rewrite a row's kind, so a consent started for one person's account cannot be answered into the
    source's slot. Delete this and the callback can keep a person's token where every read uses it.
    """
    with at_head("brain_oauth_consent_kind") as url:
        own, theirs = new_consent(), new_consent()
        issue(url, own, kind=ConsentKind.PERSON)
        issue(url, theirs, kind=ConsentKind.SOURCE)
        taken_own, taken_theirs = take(url, own.state), take(url, theirs.state)
        assert isinstance(taken_own, TakenConsent) and isinstance(taken_theirs, TakenConsent)
        assert (taken_own.kind, taken_theirs.kind) == (ConsentKind.PERSON, ConsentKind.SOURCE)

        later = new_consent()
        issue(url, later, kind=ConsentKind.PERSON)

        async def rewrite(sessions: async_sessionmaker[AsyncSession]) -> None:
            async with sessions() as session, session.begin():
                for one in attributed_to(actor_id=ME, ent_hash="", trace_id=""):
                    await session.execute(one)
                await session.execute(
                    update(OAuthConsentRow)
                    .where(OAuthConsentRow.state_digest == state_digest(later.state))
                    .values(kind=ConsentKind.SOURCE.value)
                )

        with pytest.raises(Exception, match="permission denied"):
            through(url, rewrite)
        again = take(url, later.state)
        assert isinstance(again, TakenConsent) and again.kind is ConsentKind.PERSON


@pytest.mark.needs_db
def test_the_table_keeps_no_state_and_a_verifier_only_sealed() -> None:
    """The row is found by the state's digest and holds the verifier sealed, so neither the state
    nor the verifier is in it, and nothing in it opens without the state. Delete this and a copy of
    the table is enough to finish somebody else's consent."""
    with at_head("brain_oauth_consent_sealed") as url:
        start = new_consent()
        issue(url, start)
        rows = sql(url, "SELECT * FROM ops.oauth_consent")
        held = " ".join(str(value) for value in rows[0])
        assert start.state not in held and start.verifier not in held
        assert state_digest(start.state) in held


@pytest.mark.needs_db
def test_a_person_sees_and_starts_only_their_own_consents() -> None:
    """`0180`'s policies, asked as the application's role: a row started by one person is read by
    them and by nobody else, and a row cannot be inserted in somebody else's name. Delete this and
    the store's `WHERE` is the only thing standing between two people's consents."""
    with at_head("brain_oauth_consent_rls") as url:
        issue(url, new_consent())

        async def seen(sessions: async_sessionmaker[AsyncSession], who: str) -> int:
            async with sessions() as session, session.begin():
                for one in attributed_to(actor_id=who, ent_hash="", trace_id=""):
                    await session.execute(one)
                return len((await session.execute(select(OAuthConsentRow.id))).all())

        assert through(url, lambda sessions: seen(sessions, ME)) == 1
        assert through(url, lambda sessions: seen(sessions, SOMEBODY_ELSE)) == 0

        async def forged(sessions: async_sessionmaker[AsyncSession]) -> None:
            async with sessions() as session, session.begin():
                for one in attributed_to(actor_id=SOMEBODY_ELSE, ent_hash="", trace_id=""):
                    await session.execute(one)
                session.add(
                    OAuthConsentRow(
                        state_digest=state_digest(new_consent().state),
                        connector="xero",
                        kind=ConsentKind.SOURCE.value,
                        principal_id=ME,
                        return_address=BACK,
                        sealed_verifier="sealed",
                        issued_at=NOW,
                        expires_at=NOW + CONSENT_LIFETIME,
                    )
                )

        with pytest.raises(Exception, match="row-level security"):
            through(url, forged)


@pytest.mark.needs_db
def test_a_refused_consent_is_appended_to_a_live_connection_and_to_nothing_else() -> None:
    """`StoredConsentHealth` reads the source's live connection and its newest attempt, and
    appends the refused consent's attempt to it, down with `CONSENT_WITHDRAWN`; a source with no
    live connection has nothing to append to. Delete this and the Connectors screen keeps saying
    a refused source is read."""
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections

    with at_head("brain_oauth_consent_health") as url:
        assert through(url, lambda sessions: StoredConsentHealth(sessions).latest("xero")) is None
        settings = {"tenant_id": str(uuid.uuid4())}

        async def kept() -> datetime | None:
            return None

        through(
            url,
            lambda sessions: StoredConnections(sessions).connect(
                connector="xero",
                settings=settings,
                digest=manifest_digest(manifest_for("xero", settings)),
                actor=ME,
                trace_id="t",
                ent_hash="0" * 32,
                keep_key=kept,
            ),
        )

        async def mark(sessions: async_sessionmaker[AsyncSession]) -> None:
            health = StoredConsentHealth(sessions)
            latest = await health.latest("xero")
            assert latest is not None and latest.previous is None
            attempt = refused_consent("xero", latest.previous, timedelta(minutes=15), NOW)
            await health.record(latest.connection_id, attempt)

        through(url, mark)
        assert sql(url, "SELECT health, detail FROM ops.connector_sync") == [
            (HealthState.DOWN.value, CONSENT_WITHDRAWN)
        ]
        found = through(url, lambda sessions: StoredConsentHealth(sessions).latest("xero"))
        assert found is not None and found.previous is not None
        assert found.previous.detail == CONSENT_WITHDRAWN
