"""The ledger of sign-in sessions: recorded on first use, ended once, and refusing afterwards.

The first half needs no server. It holds the three standings apart, reads each statement the store
sends as the SQL it compiles to, and drives `TokenAuthority.authenticate` over a directory that
keeps a ledger, which is how every request asks whether its session was ended.

The second half builds the database through `0050` and proves the control reaches the system, in
the three places the task names: the session row, the audit entry the trigger appends, and a
request made with that session refused afterwards through a real `keycloak_authority` and the real
directory. It skips when there is no server, and CI always has one.

Task ids: M27.7.10
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.app import wirings_for
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import AuditRecorder
from brain.cache import NoEntitlementCache
from brain.gate.admission import Assurance
from brain.identity.bearer import SessionLedger, SessionStanding, started_at_of
from brain.identity.keycloak_tokens import keycloak_authority
from brain.identity.oidc import TokenRefusal, TokenRefusedError, VerifiedClaims, parse_unverified
from brain.identity.principal_directory import StoredDirectory
from brain.identity.session_store import (
    SESSION_CHANNEL,
    EndedSession,
    StoredSession,
    StoredSessions,
    end_session,
    live_sessions,
    one_live_session,
    record_session,
    standing_of,
    stored_session,
)
from brain.identity.sessions import SESSION_ABSOLUTE_MAX
from brain.identity.sign_in_binding import sign_in_bindings
from brain.session import make_session_factory
from brain.tables.identity import SessionEndReason
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_principal
from tests.unit.test_keycloak_tokens import (
    ISSUER,
    NOW,
    SUBJECT,
    Clock,
    Idp,
    token,
)
from tests.unit.test_keycloak_tokens import Directory as OnePerson
from tests.unit.test_tables import VERSIONS, migration_module

#: A PostgreSQL dialect to compile statements against, from an engine that never connects.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

ENV: Mapping[str, str] = {"INSTALL_OIDC_ISSUER": ISSUER}


def compiled(statement: Any) -> tuple[str, dict[str, Any]]:
    rendered = statement.compile(dialect=DIALECT)
    return " ".join(str(rendered).split()), dict(rendered.params)


# ------------------------------------------------------------------- the standings


def test_a_recorded_session_is_open_ended_or_somebody_elses_and_somebody_elses_comes_first() -> (
    None
):
    """M27.7.10. Delete this and an ended row can be read as open, which is the control ending
    nothing; or a row recorded against one person can admit a token from another, which is a
    session borrowed across principals. Somebody else's is reported whichever way the row stands,
    so the log names the catastrophic case rather than the ordinary one."""
    ended = NOW

    assert standing_of("u_one", None, "u_one") is SessionStanding.OPEN
    assert standing_of("u_one", ended, "u_one") is SessionStanding.ENDED
    assert standing_of("u_one", None, "u_two") is SessionStanding.SOMEBODY_ELSES
    assert standing_of("u_one", ended, "u_two") is SessionStanding.SOMEBODY_ELSES


def test_a_session_is_live_from_its_start_to_just_before_its_ceiling() -> None:
    """Delete this and a lapsed session can be listed with a control beside it that ends nothing,
    or one that has just begun can be missing from the screen."""
    one = StoredSession(
        session_id="s",
        principal_id="u",
        display_name="U",
        department=None,
        channel="console",
        second_factor=False,
        started_at=NOW,
        expires_at=NOW + SESSION_ABSOLUTE_MAX,
    )

    assert one.is_live(NOW)
    assert not one.is_live(NOW - timedelta(seconds=1))
    assert not one.is_live(NOW + SESSION_ABSOLUTE_MAX)
    assert one.is_live(NOW + SESSION_ABSOLUTE_MAX - timedelta(seconds=1))


def test_a_row_says_a_second_factor_only_for_a_session_that_proved_one() -> None:
    """Delete this and every session reads as strongly authenticated, or none does, and the column
    an administrator reads to spot a password-only sign-in says the opposite of the truth."""
    row = {
        "id": "s",
        "principal_id": "u",
        "display_name": "U",
        "primary_department": "web",
        "channel": "console",
        "started_at": NOW,
        "expires_at": NOW + SESSION_ABSOLUTE_MAX,
    }

    assert stored_session(row | {"assurance": int(Assurance.STRONG)}).second_factor is True
    assert stored_session(row | {"assurance": int(Assurance.AUTHENTICATED)}).second_factor is False


# ------------------------------------------------------------------- the statements


def test_a_first_sighting_is_written_once_and_never_overwrites_a_row_that_exists() -> None:
    """Delete this and a replayed token can rewrite whose session a row is, or a racing second
    request raises on the key; and the ceiling can drift from the realm's ten hours."""
    sql_text, params = compiled(
        record_session(
            session_id="kc-1",
            principal_id="u_one",
            assurance=Assurance.STRONG,
            started_at=NOW,
        )
    )

    assert "ON CONFLICT (id) DO NOTHING" in sql_text
    assert sql_text.endswith("RETURNING auth.session.id")
    assert params["channel"] == SESSION_CHANNEL.value == "console"
    assert params["assurance"] == int(Assurance.STRONG)
    assert params["started_at"] == NOW
    assert params["expires_at"] == NOW + timedelta(hours=10)


def test_ending_is_one_statement_over_a_row_not_already_ended_stamped_by_the_database() -> None:
    """Delete this and a second press can re-stamp an ended row, moving the instant the ledger
    already recorded; or the application's clock stamps it; or the reason is not the console's."""
    sql_text, params = compiled(end_session("kc-1"))

    assert "ended_at=statement_timestamp()" in sql_text
    assert "WHERE auth.session.id = %(id_1)s::VARCHAR AND auth.session.ended_at IS NULL" in sql_text
    assert params["end_reason"] == SessionEndReason.ENDED_FROM_CONSOLE.value
    assert params["id_1"] == "kc-1"


def test_the_row_to_end_is_live_and_locked_and_the_listing_is_live_newest_first() -> None:
    """Delete this and two administrators can each judge a row the other is ending, or a lapsed
    session can be ended and listed. The lock is on the session and not the person."""
    lock_text, lock_params = compiled(one_live_session("kc-1", NOW))
    list_text, list_params = compiled(live_sessions(NOW, 50))

    assert lock_text.endswith("FOR UPDATE OF session")
    assert "auth.session.ended_at IS NULL AND auth.session.expires_at > " in lock_text
    assert lock_params["id_1"] == "kc-1"
    assert "auth.session.ended_at IS NULL AND auth.session.expires_at > " in list_text
    assert "ORDER BY auth.session.started_at DESC, auth.session.id" in list_text
    assert 50 in list_params.values()
    assert NOW in list_params.values()


def test_the_trigger_writes_the_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder` writes for
    a chain held anywhere else can come apart without a server to notice: one keyed `reason`, the
    other something else. The trigger's own function body is read off the migration module that
    executes it, and the recorder's details are produced by the recorder."""
    migration = migration_module(VERSIONS / "0050_session_end_action.py")
    details = recorded("u_one", SessionEndReason.ENDED_FROM_CONSOLE)

    assert list(details) == ["reason"]
    assert "jsonb_build_object('reason', NEW.end_reason)" in migration.SESSION_END_TRIGGER_FUNCTION
    assert "'session_end'" in migration.SESSION_END_TRIGGER_FUNCTION
    assert "IF NEW.end_reason = 'expired' THEN" in migration.SESSION_END_TRIGGER_FUNCTION


# ------------------------------------------------------------------- the store's orchestration


class StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None

    def one(self) -> Any:
        return self.rows[0]

    def first(self) -> Any:
        return self.rows[0] if self.rows else None

    def scalar_one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None

    def mappings(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return self.rows


class StubSession:
    """An `AsyncSession` in the shape the stores use, answering by the statement's SQL."""

    def __init__(self, answers: Callable[[str], list[Any]], sent: list[str]) -> None:
        self.answers = answers
        self.sent = sent

    async def __aenter__(self) -> StubSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> StubSession:
        return self

    async def execute(self, statement: Any, *_: Any, **__: Any) -> StubResult:
        text_of, params = compiled(statement)
        if text_of.startswith("SELECT set_config"):
            # The setting's name and value, which are what the trigger reads, not the SQL text.
            self.sent.append(f"{text_of} [{params['name']}={params['value']}]")
        else:
            self.sent.append(text_of)
        return StubResult(self.answers(text_of))


def stub_store(answers: Callable[[str], list[Any]]) -> tuple[StoredSessions, list[str]]:
    sent: list[str] = []
    return StoredSessions(lambda: StubSession(answers, sent)), sent  # type: ignore[arg-type]


LIVE_ROW: Mapping[str, Any] = {
    "id": "kc-1",
    "principal_id": "u_one",
    "display_name": "U",
    "primary_department": "web",
    "channel": "console",
    "assurance": int(Assurance.AUTHENTICATED),
    "started_at": NOW,
    "expires_at": NOW + SESSION_ABSOLUTE_MAX,
}


def test_a_session_never_seen_is_written_and_one_already_recorded_is_only_read() -> None:
    """M27.7.10, over a stub of the session. Delete this and the store can write on every request,
    or read nothing after writing and admit a session it never recorded, and only a server would
    notice."""

    def first_sighting(sql_text: str) -> list[Any]:
        return [("kc-1",)] if sql_text.startswith("INSERT") else []

    new_store, new_sent = stub_store(first_sighting)
    seen_store, seen_sent = stub_store(lambda sql_text: [("u_one", None)])

    async def go(store: StoredSessions) -> SessionStanding:
        return await store.standing(
            session_id="kc-1",
            principal_id="u_one",
            assurance=Assurance.AUTHENTICATED,
            started_at=NOW,
            now=NOW,
        )

    assert run(lambda: go(new_store)) is SessionStanding.OPEN
    assert [one.split(" ")[0] for one in new_sent] == ["SELECT", "INSERT"]
    assert run(lambda: go(seen_store)) is SessionStanding.OPEN
    assert [one.split(" ")[0] for one in seen_sent] == ["SELECT"]


def test_a_first_sighting_that_loses_a_race_reads_the_winners_row() -> None:
    """Delete this and a request that lost the race to write a session is admitted as open
    without looking at whose session the winner recorded, which is a borrowed session admitted on
    a coincidence of timing."""
    reads = iter([[], [("u_other", None)]])

    def raced(sql_text: str) -> list[Any]:
        return [] if sql_text.startswith("INSERT") else next(reads)

    store, sent = stub_store(raced)

    standing = run(
        lambda: store.standing(
            session_id="kc-1",
            principal_id="u_one",
            assurance=Assurance.AUTHENTICATED,
            started_at=NOW,
            now=NOW,
        )
    )

    assert standing is SessionStanding.SOMEBODY_ELSES
    assert [one.split(" ")[0] for one in sent] == ["SELECT", "INSERT", "SELECT"]


def test_ending_asks_the_decision_about_the_locked_row_before_it_writes() -> None:
    """M27.7.10, over a stub of the session. Delete this and `end` can write before it asks `may`,
    which ends whatever was posted; or skip naming the actor to the transaction, and the ledger
    entry the trigger writes says nobody did it."""
    asked: list[str] = []

    def answers(sql_text: str) -> list[Any]:
        if sql_text.startswith("SELECT set_config"):
            return []
        if sql_text.startswith("SELECT auth.session.id"):
            return [dict(LIVE_ROW)]
        return [NOW]

    def refuse(record: StoredSession) -> bool:
        asked.append(record.session_id)
        return False

    refusing, refused_sent = stub_store(answers)
    allowing, allowed_sent = stub_store(answers)

    def end(store: StoredSessions, may: Callable[[StoredSession], bool]) -> Any:
        return run(
            lambda: store.end(
                "kc-1", may=may, ended_by="u_admin", ent_hash="ab" * 16, trace_id="t", now=NOW
            )
        )

    assert end(refusing, refuse) is None
    assert asked == ["kc-1"]
    assert not [one for one in refused_sent if one.startswith("UPDATE")]
    ended = end(allowing, lambda _record: True)
    assert ended == EndedSession(session_id="kc-1", principal_id="u_one", ended_at=NOW)
    settings = [one.rsplit(" [", 1)[1] for one in allowed_sent[:3]]
    assert settings == [
        "brain.actor_id=u_admin]",
        f"brain.ent_hash={'ab' * 16}]",
        "brain.trace_id=t]",
    ]
    assert allowed_sent[-1].startswith("UPDATE auth.session")


# ------------------------------------------------------------------- the request path


def test_a_session_begins_when_the_token_says_and_never_after_the_token_itself() -> None:
    """Delete this and a session recorded from a token carrying a later `auth_time` than its own
    issue time begins after the request that recorded it, or a boolean is read as a second."""
    iat = int(NOW.timestamp())

    def claims(**extra: Any) -> VerifiedClaims:
        raw = parse_unverified(token(**extra))
        return VerifiedClaims(
            issuer=ISSUER,
            subject=SUBJECT,
            audience=(),
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            session_id="kc-1",
            key_id="k",
            algorithm="RS256",
            verified_at=NOW,
            claims=dict(raw.payload),
        )

    assert started_at_of(claims(auth_time=iat - 600)) == NOW - timedelta(minutes=10)
    assert started_at_of(claims()) == NOW
    assert started_at_of(claims(auth_time=iat + 600)) == NOW
    assert started_at_of(claims(auth_time=True)) == NOW


class LedgerDirectory(OnePerson):
    """The one person `test_keycloak_tokens` signs in, with a ledger of sessions beside them."""

    def __init__(self, standing: SessionStanding) -> None:
        self.answer = standing
        self.asked: list[dict[str, Any]] = []

    async def standing(
        self,
        *,
        session_id: str,
        principal_id: str,
        assurance: Assurance,
        started_at: datetime,
        now: datetime,
    ) -> SessionStanding:
        self.asked.append(
            {
                "session_id": session_id,
                "principal_id": principal_id,
                "assurance": assurance,
                "started_at": started_at,
            }
        )
        return self.answer


def authenticated(directory: Any, **claims: Any) -> Any:
    authority = keycloak_authority(directory=directory, get=Idp().get, clock=Clock(), env=ENV)

    async def go() -> Any:
        return await authority.authenticate(f"Bearer {token(**claims)}", now=NOW)

    return run(go)


def test_a_token_from_an_open_session_is_admitted_and_its_session_is_asked_about_as_it_is() -> None:
    """The positive case for the two refusals below. Delete this and a directory that refuses
    every session satisfies both, and the ledger can be asked about somebody other than the
    principal the token names, at the wrong assurance, from the wrong instant."""
    directory = LedgerDirectory(SessionStanding.OPEN)
    began = int((NOW - timedelta(minutes=20)).timestamp())

    caller = authenticated(directory, sid="kc-open", amr=["otp"], auth_time=began)

    assert caller.principal.id == "u_signed_in"
    assert directory.asked == [
        {
            "session_id": "kc-open",
            "principal_id": "u_signed_in",
            "assurance": Assurance.STRONG,
            "started_at": NOW - timedelta(minutes=20),
        }
    ]


def test_a_token_from_an_ended_session_or_from_somebody_elses_is_refused() -> None:
    """M27.7.10's refusal. Delete this and ending a session changes a row and nothing else: the
    token in the person's hand keeps working, which is the whole reason the control exists."""
    with pytest.raises(TokenRefusedError) as ended:
        authenticated(LedgerDirectory(SessionStanding.ENDED), sid="kc-ended")
    with pytest.raises(TokenRefusedError) as borrowed:
        authenticated(LedgerDirectory(SessionStanding.SOMEBODY_ELSES), sid="kc-borrowed")

    assert ended.value.reason is TokenRefusal.LOGGED_OUT
    assert borrowed.value.reason is TokenRefusal.SESSION_MISMATCH


def test_a_sessionless_token_and_a_directory_with_no_ledger_are_not_asked_about() -> None:
    """Delete this and a service account's token, which carries no `sid`, is written into the
    ledger of sign-in sessions under a session id of nothing; or the check can be made to require
    a ledger every test double would have to grow."""
    directory = LedgerDirectory(SessionStanding.ENDED)

    caller = authenticated(directory)
    plain = authenticated(OnePerson(), sid="kc-any")

    assert caller.principal.id == plain.principal.id == "u_signed_in"
    assert directory.asked == []


def test_the_directory_a_deployed_process_is_wired_with_keeps_the_ledger() -> None:
    """Delete this and the refusal above is real in a test and absent in production: `wirings_for`
    could build the authority over a directory that is not a `SessionLedger`, and `authenticate`
    would ask nothing. This is the one sentence standing between the control and a button that
    ends a row."""
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker()
    wired = wirings_for(sessions, get=Idp().get, cache=NoEntitlementCache(), clock=Clock(), env=ENV)

    assert wired is not None
    assert isinstance(StoredDirectory(sessions), SessionLedger)
    assert isinstance(wired[0].authority.directory, SessionLedger)


# ----------------------------------------------------------------------- the database


@contextmanager
def through_0050(database: str) -> Iterator[str]:
    """The soft-deleted tables with `0047` and `0050` applied. Where the server has no pgvector,
    `retirable` stops at `0048`'s function; `0046` and `0049` touch nothing these tests read, so
    they are stamped and `0047` and `0050` are run for real."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "stamp", "0046")
            migrate(database, "upgrade", "0047")
            migrate(database, "stamp", "0049")
            migrate(database, "upgrade", "0050")
        yield url


def with_sessions[T](url: str, work: Callable[[StoredSessions], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredSessions(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def session_entries(url: str) -> list[AuditEntry]:
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry WHERE action = 'session_end' ORDER BY seq",
    )
    names = ("seq", "at", "actor_id", "action", "subject", "ent_hash", "trace_id", "details")
    return [
        AuditEntry(**dict(zip((*names, "prev_hash", "entry_hash"), row, strict=True)))
        for row in rows
    ]


def recorded(principal_id: str, reason: SessionEndReason) -> Mapping[str, str]:
    """What `AuditRecorder.session_end` writes as details, in a chain held in memory."""
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    return recorder.session_end(principal_id=principal_id, reason=reason).details


def observe(url: str, session_id: str, principal_id: str) -> SessionStanding:
    return with_sessions(
        url,
        lambda store: store.standing(
            session_id=session_id,
            principal_id=principal_id,
            assurance=Assurance.AUTHENTICATED,
            started_at=NOW,
            now=NOW,
        ),
    )


def test_a_session_is_recorded_once_on_first_use_and_is_somebody_elses_to_anybody_else() -> None:
    """M27.7.10, through the database as the application role. Delete this and the listing has
    nothing to list, because nothing writes a row; or every request writes another; or a token
    naming somebody else's session id is admitted."""
    with through_0050("brain_ss_record") as url:
        a_principal(url, "u_one")
        a_principal(url, "u_two")
        first = observe(url, "kc-1", "u_one")
        again = observe(url, "kc-1", "u_one")
        borrowed = observe(url, "kc-1", "u_two")
        rows = sql(url, "SELECT id, principal_id, channel, ended_at FROM auth.session")

    assert (first, again, borrowed) == (
        SessionStanding.OPEN,
        SessionStanding.OPEN,
        SessionStanding.SOMEBODY_ELSES,
    )
    assert rows == [("kc-1", "u_one", "console", None)]


def test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request() -> None:
    """M27.7.10's proof that the control reaches the system, all three halves in one database.

    The row: ended at the database's instant, for the console's reason. The entry: `session_end`
    about the person, naming the administrator, their reach's digest and the request, with the
    recorder's details and a digest the chain verifies. The refusal: a real authority over the
    real directory admits a token from the session before, refuses it after, and still admits the
    same person's other session. Delete this and any one of the three can be missing while the
    screen reports success."""
    with through_0050("brain_ss_end") as url:
        a_principal(url, "u_joiner")

        async def go() -> tuple[str, Any, TokenRefusal, str]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                writer = sign_in_bindings(sessions, env=ENV)
                await writer.bind(SUBJECT, principal_id="u_joiner", bound_by="u_admin", now=NOW)
                authority = keycloak_authority(
                    directory=StoredDirectory(sessions), get=Idp().get, clock=Clock(), env=ENV
                )
                ended_token = f"Bearer {token(sid='kc-ended')}"
                other_token = f"Bearer {token(sid='kc-other')}"
                before = await authority.authenticate(ended_token, now=NOW)
                await authority.authenticate(other_token, now=NOW)
                ended = await StoredSessions(sessions).end(
                    "kc-ended",
                    may=lambda record: record.principal_id == "u_joiner",
                    ended_by="u_admin",
                    ent_hash="ab" * 16,
                    trace_id="trace-end-1",
                    now=NOW,
                )
                try:
                    await authority.authenticate(ended_token, now=NOW)
                except TokenRefusedError as refused:
                    after = refused.reason
                still = await authority.authenticate(other_token, now=NOW)
                return before.principal.id, ended, after, still.principal.id
            finally:
                await engine.dispose()

        before, ended, after, still = run(go)
        rows = sql(url, "SELECT id, end_reason, ended_at IS NOT NULL FROM auth.session ORDER BY id")
        entries = session_entries(url)

    assert before == still == "u_joiner"
    assert ended is not None and ended.principal_id == "u_joiner"
    assert rows == [("kc-ended", "ended_from_console", True), ("kc-other", None, False)]
    assert after is TokenRefusal.LOGGED_OUT
    [entry] = entries
    assert (entry.actor_id, entry.subject, entry.ent_hash, entry.trace_id) == (
        "u_admin",
        "principal:u_joiner",
        "ab" * 16,
        "trace-end-1",
    )
    assert entry.details == dict(recorded("u_joiner", SessionEndReason.ENDED_FROM_CONSOLE))
    assert entry.details == {"reason": "ended_from_console"}
    assert entry.recompute_hash() == entry.entry_hash


def test_a_session_the_decision_refuses_or_already_ended_writes_nothing() -> None:
    """Delete this and `end` can write before it asks `may`, which is a control that ends whatever
    was posted; or a second press re-ends a row and appends a second entry for one act."""
    with through_0050("brain_ss_refused") as url:
        a_principal(url, "u_one")
        observe(url, "kc-1", "u_one")

        def end(may: bool) -> Any:
            return with_sessions(
                url,
                lambda store: store.end(
                    "kc-1",
                    may=lambda _record: may,
                    ended_by="u_admin",
                    ent_hash="",
                    trace_id="",
                    now=NOW,
                ),
            )

        refused = end(False)
        untouched = sql(url, "SELECT ended_at FROM auth.session")
        first = end(True)
        second = end(True)
        entries = session_entries(url)

    assert refused is None
    assert untouched == [(None,)]
    assert first is not None
    assert second is None
    assert len(entries) == 1


def test_a_disable_ends_the_session_unattributed_and_an_expiry_is_not_recorded() -> None:
    """`0003`'s cascade finally has a row to end, and `0050` records it. Delete this and the
    trigger can refuse an ending with no actor named, which blocks a disable at midnight; or
    record a sweep's expiry, which is one ledger entry per sign-in per day kept for ever."""
    with through_0050("brain_ss_cascade") as url:
        a_principal(url, "u_leaver")
        a_principal(url, "u_other")
        observe(url, "kc-leaver", "u_leaver")
        observe(url, "kc-other", "u_other")
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = 'u_leaver'")
        sql(
            url,
            "UPDATE auth.session SET ended_at = now(), end_reason = 'expired'"
            " WHERE id = 'kc-other'",
        )
        rows = sql(url, "SELECT id, end_reason FROM auth.session ORDER BY id")
        entries = session_entries(url)

    assert rows == [("kc-leaver", "principal_disabled"), ("kc-other", "expired")]
    [entry] = entries
    assert (entry.actor_id, entry.subject) == ("unattributed", "principal:u_leaver")
    assert entry.details == {"reason": "principal_disabled", "actor": "unattributed"}
    assert entry.recompute_hash() == entry.entry_hash


def test_the_listing_is_the_live_sessions_with_their_people() -> None:
    """Delete this and the listing can include ended rows, whose control would end nothing, or
    lose the department the console places a row by."""
    with through_0050("brain_ss_list") as url:
        a_principal(url, "u_one")
        a_principal(url, "u_two")
        observe(url, "kc-1", "u_one")
        observe(url, "kc-2", "u_two")
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = 'u_two'")
        listed, full = with_sessions(url, lambda store: store.open_sessions(now=NOW, limit=10))

    assert [(one.session_id, one.principal_id, one.department) for one in listed] == [
        ("kc-1", "u_one", "finance")
    ]
    assert full is False
