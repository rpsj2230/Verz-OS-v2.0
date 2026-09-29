"""The staff sync's accounts step against a real PostgreSQL at head and a stand-in Keycloak.

`brain.ops.staff_accounts_run.provide_accounts` makes each active person's account in the sign-in
service, a Brain person behind it bound the way the Sign-in links screen binds one, and closes a
leaver's. The plan is `tests/unit/test_staff_accounts.py` and the requests are
`tests/unit/test_sign_in_accounts.py`; this is the two put together with the tables they write, so
the binding, the member grant, the roster's email join and the disabling are the ones checked.
Nothing here has called a Keycloak; `tests/fixtures/stand_in_keycloak.py` says what it models.

CI sets `DATABASE_URL` and has pgvector; without either every test that needs the database skips.

Task ids: M1.6.16, M1.6.17
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.staff_directories import Answer, Outbound
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.principal_directory import SIGN_IN_CHANNEL, subject_digest
from brain.identity.staff_accounts import AccountRefusal
from brain.identity.staff_roster import RunOutcome, digest_of
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    EmploymentStatus,
    EmploymentType,
    Roster,
    StaffRecord,
)
from brain.ops.connectable import key_reference
from brain.ops.connector_sync_run import ConnectorKeyAbsentError
from brain.ops.secrets import SecretRef
from brain.ops.staff_accounts_run import (
    HOW_PEOPLE_GET_IN,
    NO_ISSUER,
    NO_KEY,
    AccountRun,
    provide_accounts,
)
from brain.ops.staff_sync_run import sync_staff_on
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.stand_in_keycloak import ISSUER, SECRET, StandInKeycloak, User
from tests.unit.test_acceptance import at_head
from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, LARK_ENV, Directory, Keys, Lease

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
NOW = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=1)

#: The install the worker is given: its issuer, which names the stand-in's realm.
ENV = {"INSTALL_OIDC_ISSUER": ISSUER}


#: Where the worker reaches the sign-in service: the issuer's own address, as the application
#: reaches it for its keys. The stand-in answers by path, so this is asserted rather than routed.
PUBLIC = ISSUER.rsplit("/realms/", 1)[0] + "/"


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with at_head("brain_test_staff_accounts_run") as scratch:
        yield scratch


def person(
    name: str,
    *,
    status: EmploymentStatus = EmploymentStatus.ACTIVE,
    kind: EmploymentType | None = EmploymentType.REGULAR,
) -> StaffRecord:
    return StaffRecord(
        f"{name}@example.test",
        f"{name.title()} Lovelace",
        active=status is EmploymentStatus.ACTIVE,
        status=status,
        employment_type=kind,
    )


def listed(*people: StaffRecord, complete: bool = True) -> Roster:
    return Roster(source="lark", people=people, complete=complete, asserts=DEFAULT_TRUST["lark"])


def stable(*names: str) -> dict[str, str]:
    return {f"{one}@example.test": f"on_{one}" for one in names}


def keys() -> Keys:
    return Keys(Lease(f"brain-accounts:{SECRET}"))


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def provide(
    url: str,
    keycloak: StandInKeycloak,
    roster: Roster,
    *,
    at: datetime = NOW,
    trial: bool = False,
    absent_is_gone: bool = False,
    given: Keys | None = None,
) -> AccountRun:
    return through(
        url,
        lambda sessions: provide_accounts(
            sessions=sessions,
            roster=roster,
            stable_ids=stable(*(one.work_address.split("@")[0] for one in roster.people)),
            keys=given or keys(),
            fetch=keycloak,
            env=ENV,
            now=at,
            absent_is_gone=absent_is_gone,
            trial=trial,
        ),
    )


def signed_in_as(url: str, account_id: str) -> list[tuple[Any, ...]]:
    """The principal this account signs in as, and whether that principal is disabled."""
    return sql(
        url,
        "SELECT p.id, p.disabled_at IS NOT NULL, p.employment FROM auth.principal_identity i "
        "JOIN auth.principal p ON p.id = i.principal_id "
        "WHERE i.channel = %s AND i.identity_hash = %s AND i.deleted_at IS NULL",
        SIGN_IN_CHANNEL.value,
        subject_digest(ISSUER, account_id),
    )


def mailbox_of(url: str, address: str) -> list[tuple[Any, ...]]:
    """The roster's join for this address: its email binding's principal and assurance."""
    return sql(
        url,
        "SELECT principal_id, assurance FROM auth.principal_identity "
        "WHERE channel = %s AND identity_hash = %s AND deleted_at IS NULL",
        Channel.EMAIL.value,
        digest_of(address),
    )


def account_of(keycloak: StandInKeycloak, address: str) -> Any:
    (found,) = [one for one in keycloak.users.values() if one.email == address]
    return found


def test_a_run_makes_an_account_and_a_bound_person_for_the_active_and_allowed_only(
    url: str,
) -> None:
    """The first run: an active regular person gets an account, a Brain person, a sign-in binding
    and the roster's email join at the assurance that admits nothing; a leaver and an outsourced
    person get none; nothing is sent to anybody. Delete this and the sync can make accounts that
    sign in as nobody, bind the roster's join at an assurance that admits mail, or make one for a
    leaver, with every stand-in test green."""
    keycloak = StandInKeycloak()
    ran = provide(
        url,
        keycloak,
        listed(
            person("ada"),
            person("bo", status=EmploymentStatus.LEFT),
            person("ed", kind=EmploymentType.OUTSOURCED),
        ),
    )

    assert [one.email for one in keycloak.users.values()] == ["ada@example.test"]
    assert keycloak.sent == []
    assert all(one.url.startswith(PUBLIC) for one in keycloak.requests)
    ada = account_of(keycloak, "ada@example.test")
    ((principal, disabled, employment),) = signed_in_as(url, ada.id)
    assert (disabled, employment) == (False, "staff")
    assert mailbox_of(url, "ada@example.test") == [(principal, int(Assurance.UNVERIFIED))]
    assert mailbox_of(url, "bo@example.test") == mailbox_of(url, "ed@example.test") == []
    grants = sql(
        url,
        "SELECT count(*) FROM gate.capability_grant WHERE principal_id = %s AND deleted_at IS NULL",
        principal,
    )
    assert grants == [(1,)]
    assert ran.plan is not None
    assert ran.plan.refused == {AccountRefusal.NOT_ACTIVE: 1, AccountRefusal.TYPE_NOT_ALLOWED: 1}
    assert ran.sentences == (
        "Sign-in accounts: 1 made, 0 opened again, 0 closed.",
        "No account for 1 suspended, gone or never activated, "
        "1 of an employment type that may not use the Brain.",
        HOW_PEOPLE_GET_IN,
    )


def test_a_second_run_finds_the_account_and_the_person_and_makes_neither_again(url: str) -> None:
    """Idempotent by the account's marks and the binding: two runs, one account, one person, one
    binding. Delete this and every night makes another account or another Brain person."""
    keycloak = StandInKeycloak()
    provide(url, keycloak, listed(person("cy")))
    ((first, _, _),) = signed_in_as(url, account_of(keycloak, "cy@example.test").id)
    again = provide(url, keycloak, listed(person("cy")), at=LATER)

    assert len(keycloak.users) == 1
    ((second, _, _),) = signed_in_as(url, account_of(keycloak, "cy@example.test").id)
    assert first == second
    assert mailbox_of(url, "cy@example.test") == [(first, int(Assurance.UNVERIFIED))]
    assert again.sentences[0] == "Sign-in accounts: 0 made, 0 opened again, 0 closed."


def test_a_leaver_s_account_is_closed_their_sessions_ended_and_their_person_disabled(
    url: str,
) -> None:
    """The next sync after somebody leaves: the account the sync made is disabled and signed out,
    and the Brain person behind it is disabled, which ends their Brain sessions. When the source
    lists them as active again both are opened. Delete this and a leaver keeps a way in, or stays
    locked out after they come back."""
    keycloak = StandInKeycloak()
    provide(url, keycloak, listed(person("di")))
    di = account_of(keycloak, "di@example.test")

    closed = provide(url, keycloak, listed(person("di", status=EmploymentStatus.LEFT)), at=LATER)
    assert (di.enabled, di.signed_out) == (False, 1)
    assert [row[1] for row in signed_in_as(url, di.id)] == [True]
    assert closed.sentences[0] == "Sign-in accounts: 0 made, 0 opened again, 1 closed."

    opened = provide(url, keycloak, listed(person("di")), at=LATER + timedelta(days=1))
    assert di.enabled is True
    assert [row[1] for row in signed_in_as(url, di.id)] == [False]
    assert opened.sentences[0] == "Sign-in accounts: 0 made, 1 opened again, 0 closed."
    assert keycloak.sent == []


def test_an_account_somebody_made_by_hand_is_linked_once_and_never_closed(url: str) -> None:
    """The first administrator's account, or one made before the sync: linked to a Brain person and
    marked with the source, not duplicated, and left open when the source says the person left.
    Delete this and the sync can lock a company out of its own install."""
    keycloak = StandInKeycloak()
    by_hand = User(id="by-hand", username="fe@example.test", email="fe@example.test")
    keycloak.users[by_hand.id] = by_hand
    provide(url, keycloak, listed(person("fe")))
    assert len(keycloak.users) == 1
    assert by_hand.attributes.get("brain_staff_id") == ["on_fe"]
    assert "brain_made_by_sync" not in by_hand.attributes
    assert len(signed_in_as(url, "by-hand")) == 1

    provide(url, keycloak, listed(person("fe", status=EmploymentStatus.LEFT)), at=LATER)
    assert by_hand.enabled is True
    assert [row[1] for row in signed_in_as(url, "by-hand")] == [False]


def test_a_trial_says_what_a_run_would_do_and_makes_nobody(url: str) -> None:
    """The Staff sources screen's Try a read: counts, and no account, person or binding. Delete this
    and pressing Try a read makes a company's accounts."""
    keycloak = StandInKeycloak()
    tried = provide(url, keycloak, listed(person("gil")), trial=True)

    assert keycloak.users == {}
    assert mailbox_of(url, "gil@example.test") == []
    assert tried.sentences == (
        "Sign-in accounts: 1 made, 0 opened again, 0 closed.",
        HOW_PEOPLE_GET_IN,
    )
    assert not [one for one in keycloak.requests if one.method in ("POST", "PUT")][1:]


def test_no_credential_in_the_vault_is_a_sentence_and_touches_nothing(url: str) -> None:
    """Before the release has kept the client's secret: one sentence, nothing asked of the sign-in
    service, and the lease handed back. Delete this and the step raises into the roster's run."""
    keycloak = StandInKeycloak()
    absent = Lease(None, failure=ConnectorKeyAbsentError(key_reference("sign_in_accounts")))
    given = Keys(absent)
    ran = provide(url, keycloak, listed(person("hal")), given=given)

    assert ran.sentences == (NO_KEY,)
    assert keycloak.requests == []
    assert given.asked == [key_reference("sign_in_accounts")]
    assert absent.closed == [NOW]


def test_a_refused_secret_stops_the_step_in_words_and_hands_the_lease_back(url: str) -> None:
    """Delete this and a rotated secret reads as a night with nobody to make, or leaks the secret
    into the run's report."""
    keycloak = StandInKeycloak(secret="another-secret")
    lease = Lease(f"brain-accounts:{SECRET}")
    ran = provide(url, keycloak, listed(person("ivy")), given=Keys(lease))

    assert ran.plan is None
    assert ran.sentences[0].startswith("Sign-in accounts: stopped. The sign-in service refused")
    assert SECRET not in " ".join(ran.sentences)
    assert lease.closed == [NOW]


def test_an_install_whose_worker_has_no_issuer_says_so_and_asks_nothing() -> None:
    """Delete this and a worker never given the issuer fails with a message about a setting's
    default rather than one an owner can act on."""
    keycloak = StandInKeycloak()
    lease = Lease(f"brain-accounts:{SECRET}")

    async def go() -> AccountRun:
        return await provide_accounts(
            sessions=None,  # type: ignore[arg-type]
            roster=listed(person("jo")),
            stable_ids={},
            keys=Keys(lease),
            fetch=keycloak,
            env={},
            now=NOW,
            absent_is_gone=False,
        )

    assert run(go).sentences == (NO_ISSUER,)
    assert keycloak.requests == []
    assert lease.closed == []


# ------------------------------------------------------------------ the whole run
@dataclass
class ByPath:
    """The vault, one lease per slot, so the staff list's key and the accounts client's differ."""

    leases: dict[str, Lease]
    asked: list[str] = field(default_factory=list)

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        self.asked.append(ref.path)
        return self.leases[ref.path]


class Both:
    """Lark at its own addresses and the sign-in service at the issuer's."""

    def __init__(self) -> None:
        self.directory = Directory()
        self.keycloak = StandInKeycloak()

    async def __call__(self, outbound: Outbound) -> Answer:
        if outbound.url.startswith(PUBLIC):
            return await self.keycloak(outbound)
        return await self.directory(outbound)


def test_a_scheduled_run_makes_the_accounts_before_the_roster_and_says_so_on_its_row(
    url: str,
) -> None:
    """`sync_staff_on` end to end: the Lark list's two active people get accounts and the resigned
    one none, the counts are on the run's own row beside what was read, the run leases the accounts
    client's key as well as the list's, and nothing is sent. Delete this and the step can be
    dropped from the run, or run after the row is written with its counts lost, with every other
    test here green."""
    fetch = Both()
    vault = ByPath(
        {
            key_reference("staff_source").path: Lease(f"{APP_ID}:{APP_SECRET}"),
            key_reference("sign_in_accounts").path: Lease(f"brain-accounts:{SECRET}"),
        }
    )
    ran = through(
        url,
        lambda sessions: sync_staff_on(
            sessions=sessions,
            now=NOW,
            env={**LARK_ENV, **ENV},
            keys=vault,
            fetch=fetch,
            clock=lambda: NOW + timedelta(seconds=5),
        ),
    )

    assert ran.outcome is RunOutcome.APPLIED
    assert sorted(one.email for one in fetch.keycloak.users.values()) == [
        "ada@example.com",
        "katherine@example.com",
    ]
    assert fetch.keycloak.sent == []
    assert vault.asked == [
        key_reference("staff_source").path,
        key_reference("sign_in_accounts").path,
    ]
    ((report,),) = sql(
        url,
        "SELECT report FROM auth.staff_sync_run WHERE started_at = %s AND outcome = 'applied'",
        NOW,
    )
    assert "Sign-in accounts: 2 made, 0 opened again, 0 closed." in report
    assert HOW_PEOPLE_GET_IN in report
    assert tuple(report) == ran.report
