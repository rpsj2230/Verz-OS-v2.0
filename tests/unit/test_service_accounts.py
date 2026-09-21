"""Service accounts: authenticated as themselves, answered at their owner's live reach, no more.

The first half needs no server. It drives `TokenAuthority.authenticate` with an API key and with a
sessionless token over a directory holding accounts, asks `brain.api_routes.reach_of` what the
account then holds, and drives the routes that make an account and its keys over a store in memory.

The second half builds the database through `0095` and proves the three things M1.8.2 names on
real rows: the account acts at its owner's reach narrowed by its ceiling, it holds no grant of its
own, and it stops working when its owner loses the reach or is disabled. It also proves the partner
half of `0095` (M1.2.4) on the resolver every request goes through. It skips when there is no
server, and CI always has one.

Task ids: M1.1.7, M1.8.2, M1.2.4
"""

from __future__ import annotations

import ast
import base64
import inspect
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import service_account_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring, reach_of
from brain.app import Settings, create_app
from brain.channels.api_keys import ApiKeyRecord, IssuedKey, issue
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity import bearer
from brain.identity.bearer import (
    API_KEY_ISSUER,
    Caller,
    ServiceAccountDirectory,
    TokenAuthority,
)
from brain.identity.oidc import PrincipalDirectory, TokenRefusal, TokenRefusedError
from brain.identity.roles import BREAK_GLASS_MAX
from brain.identity.service_account_store import AccountListed, Registered
from brain.identity.sessions import ServiceAccount
from brain.tables import service_account as tables
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    KID,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    marker_for,
    token_for,
    verifier,
)
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION = VERSIONS / "0095_service_accounts_and_partner_reach.py"
LAPSE_MIGRATION = VERSIONS / "0048_grant_lapse.py"

#: The owner every account here belongs to, signed in through `test_api_routes`' subjects.
OWNER = "u_admin"
ACCOUNT = "svc_reporting"
#: A subject for the account's client-credentials user. Not any person's.
ACCOUNT_SUBJECT = "9c0ffee0-0000-4000-8000-0000000000aa"

READ_HOURS = Capability(value="read:client.hours")
READ_MARGIN = Capability(value="read:client.margin")
WRITE_NOTE = Capability(value="write:client.note")
CREDENTIAL = Capability(value="admin:credential")


def now() -> datetime:
    # The routes and the token check read the wall clock, so the fixtures are built around it.
    return datetime.now(UTC)


def an_account(*, ceiling: tuple[Capability, ...] = (READ_HOURS, READ_MARGIN)) -> ServiceAccount:
    return ServiceAccount(
        client_id=ACCOUNT,
        subject=ACCOUNT_SUBJECT,
        owner_principal_id=OWNER,
        ceiling=ceiling,
        not_after=now() + timedelta(days=30),
    )


def the_owner(*, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=OWNER,
        kind=PrincipalKind.HUMAN,
        employment=Employment.CONTRACTOR if not_after else Employment.STAFF,
        display_name="The Owner",
        primary_department="web",
        not_after=not_after,
    )


@dataclass
class Accounts:
    """A directory holding one person per `test_api_routes` subject, accounts and their keys."""

    accounts: dict[str, ServiceAccount] = field(default_factory=dict)
    keys: dict[str, tuple[ApiKeyRecord, ServiceAccount]] = field(default_factory=dict)
    owners: dict[str, Principal] = field(default_factory=lambda: {OWNER: the_owner()})
    asked_owner: list[str] = field(default_factory=list)

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return Principal(
                    id=pid,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name=pid,
                )
        return None

    async def service_account_for_subject(self, subject: str) -> ServiceAccount | None:
        return self.accounts.get(subject)

    async def service_account_for_key(
        self, handle: str
    ) -> tuple[ApiKeyRecord, ServiceAccount] | None:
        return self.keys.get(handle)

    async def live_owner(self, principal_id: str) -> Principal | None:
        self.asked_owner.append(principal_id)
        return self.owners.get(principal_id)


def keyed(directory: Accounts, account: ServiceAccount | None = None) -> IssuedKey:
    account = account or an_account()
    minted = issue(account, now=now() - timedelta(minutes=1), not_after=now() + timedelta(days=7))
    directory.keys[minted.record.handle] = (minted.record, account)
    return minted


def authority(directory: PrincipalDirectory) -> TokenAuthority:
    return TokenAuthority(
        issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=directory
    )


def authenticated(directory: PrincipalDirectory, header: str) -> Caller:
    import asyncio

    return asyncio.run(authority(directory).authenticate(header, now=now()))


def refused(directory: PrincipalDirectory, header: str) -> TokenRefusal:
    with pytest.raises(TokenRefusedError) as caught:
        authenticated(directory, header)
    return caught.value.reason


def account_token(**claims: object) -> str:
    """A sessionless token whose subject is the account's, as a client-credentials grant mints.

    Assembled from raw parts as `test_api_routes.token_for` is, without the `sid` that one always
    carries, because a missing `sid` is the whole difference being tested.
    """
    issued = now()
    header = {"alg": "RS256", "typ": "JWT", "kid": KID}
    payload: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": ACCOUNT_SUBJECT,
        "typ": "Bearer",
        "azp": ACCOUNT,
        "exp": int((issued + timedelta(minutes=5)).timestamp()),
        "iat": int(issued.timestamp()),
    }
    payload.update(claims)

    def seg(blob: bytes) -> str:
        return base64.urlsafe_b64encode(blob).decode().rstrip("=")

    return ".".join(
        (seg(json.dumps(header).encode()), seg(json.dumps(payload).encode()), seg(marker_for(KID)))
    )


# ------------------------------------------------------------------ the table and migration


def test_the_migration_restates_the_tables_patterns_and_the_break_glass_ceiling() -> None:
    """`0095` copies its patterns rather than importing live code, for `0009`'s reason. Delete this
    and the model and the database can accept different ids or keys, and the partner window can
    drift from `BREAK_GLASS_MAX`, which is the ceiling an elevation is approved under."""
    migration = migration_module(MIGRATION)
    assert migration.CLIENT_ID_PATTERN == tables.CLIENT_ID_PATTERN
    assert migration.HANDLE_PATTERN == tables.HANDLE_PATTERN
    assert migration.DIGEST_PATTERN == tables.DIGEST_PATTERN
    assert timedelta(hours=4) == BREAK_GLASS_MAX
    assert migration.BREAK_GLASS_WINDOW == "interval '4 hours'"
    assert migration.HELD_GRANTS_WITH_PARTNER_WINDOW.count(migration.BREAK_GLASS_WINDOW) == 2


def test_the_downgrade_puts_back_the_rows_0048_wrote_word_for_word() -> None:
    """Delete this and a downgrade can leave a resolver that is neither `0048`'s nor `0095`'s."""
    migration = migration_module(MIGRATION)
    lapse = migration_module(LAPSE_MIGRATION)
    assert (
        migration.HELD_GRANTS_AS_0048_WROTE_IT.replace(
            "CREATE OR REPLACE FUNCTION", "CREATE FUNCTION"
        )
        == lapse.HELD_GRANTS
    )


def test_a_partners_row_counts_only_as_a_window_and_everybody_elses_as_before() -> None:
    """M1.2.4 in the SQL: each half of the union keeps `0048`'s predicates and adds one clause
    about a partner. Delete this and the clause can be dropped from the pack half, which is a
    partner holding a pack standing."""
    migration = migration_module(MIGRATION)
    body = " ".join(migration.HELD_GRANTS_WITH_PARTNER_WINDOW.split())
    for alias in ("g", "a"):
        clause = (
            f"AND ( pr.employment <> 'partner' OR ({alias}.not_after IS NOT NULL AND "
            f"{alias}.not_after <= {alias}.created_at + interval '4 hours') )"
        )
        assert clause in body
    assert migration.TABLES == ("auth.service_account", "auth.api_key")


def test_an_account_is_not_a_principal_and_no_grant_can_name_one() -> None:
    """The structural half of "holds no grant of its own". Delete this and the account could be
    given a principal row, and then a grant, which is the union authority the type forbids."""
    from brain.tables import CapabilityGrantRow

    [grant_fk] = [
        fk for fk in CapabilityGrantRow.__table__.foreign_keys if fk.parent.name == "principal_id"
    ]
    assert grant_fk.column.table.fullname == "auth.principal"
    columns = set(tables.ServiceAccountRow.__table__.columns.keys())
    assert "ceiling" in columns
    assert not {"grants", "capability", "scope"} & columns


# ------------------------------------------------------------------- authenticating a key


def test_a_live_key_authenticates_as_its_account_with_its_owner_read_now() -> None:
    """The positive case for every refusal below. Delete this and a bearer that refuses every key
    satisfies them all; and the caller could come back as the owner, which records an
    integration's acts as a person's."""
    directory = Accounts()
    minted = keyed(directory)

    caller = authenticated(directory, f"Bearer {minted.secret}")

    assert caller.principal.id == ACCOUNT
    assert caller.principal.kind is PrincipalKind.SERVICE
    assert caller.service_account is not None and caller.service_account.client_id == ACCOUNT
    assert caller.owner is not None and caller.owner.id == OWNER
    assert caller.claims.issuer == API_KEY_ISSUER
    assert caller.claims.session_id is None
    assert caller.claims.key_id == minted.record.handle
    assert directory.asked_owner == [OWNER]


def test_a_wrong_secret_an_unknown_handle_and_a_malformed_key_are_refused() -> None:
    """Delete this and a key is accepted on its handle alone, which is the part that is logged."""
    directory = Accounts()
    minted = keyed(directory)
    prefix, handle, _secret = minted.secret.split(".")

    assert refused(directory, f"Bearer {prefix}.{handle}.{'A' * 43}") in {
        TokenRefusal.SERVICE_ACCOUNT_EXPIRED
    }
    assert refused(directory, f"Bearer {prefix}.nobodyshandle.{'A' * 43}") is (
        TokenRefusal.UNKNOWN_SERVICE_ACCOUNT
    )
    assert refused(directory, "Bearer brn.x") is TokenRefusal.MALFORMED


def test_a_key_whose_owner_is_disabled_or_past_their_end_date_is_refused() -> None:
    """M1.8.2's "stops working the moment its owner leaves". Delete this and an integration keeps
    working for a person who can no longer sign in, at the reach they had when they left."""
    gone = Accounts(owners={})
    minted = keyed(gone)
    assert refused(gone, f"Bearer {minted.secret}") is TokenRefusal.OWNER_INACTIVE

    lapsed = Accounts(owners={OWNER: the_owner(not_after=now() - timedelta(minutes=1))})
    minted = keyed(lapsed)
    assert refused(lapsed, f"Bearer {minted.secret}") is TokenRefusal.OWNER_INACTIVE


def test_a_directory_with_no_accounts_accepts_no_key() -> None:
    """Delete this and a process whose directory keeps no accounts could fall through to the token
    parser with a key, or worse to a caller built from nothing."""

    class People:
        async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
            return None

    assert not isinstance(People(), ServiceAccountDirectory)
    assert refused(People(), "Bearer brn.abcdefgh." + "A" * 43) is (
        TokenRefusal.UNKNOWN_SERVICE_ACCOUNT
    )


def test_the_bearer_checks_a_key_with_api_keys_verify_and_no_comparison_of_its_own() -> None:
    """One implementation of the key check. Delete this and a second comparison can appear in the
    bearer, with `==` on a digest, which is the timing leak `verify` exists to close."""
    source = inspect.getsource(bearer)
    tree = ast.parse(source)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "verify_key" in called
    assert "hashlib" not in source
    assert "compare_digest" not in source


# -------------------------------------------------------------- a client-credentials token


def test_a_sessionless_token_whose_subject_is_an_account_authenticates_as_the_account() -> None:
    """M1.1.7: a token from the identity provider with no `sid`. Delete this and such a token
    finds no principal and is refused, which is what the install did before this."""
    directory = Accounts(accounts={ACCOUNT_SUBJECT: an_account()})

    caller = authenticated(directory, f"Bearer {account_token()}")

    assert caller.principal.id == ACCOUNT
    assert caller.owner is not None and caller.owner.id == OWNER


def test_a_token_naming_another_client_or_carrying_a_session_is_not_the_account() -> None:
    """Delete this and a person's browser token for the same subject, or a token another client
    asked for, is accepted as the integration."""
    directory = Accounts(accounts={ACCOUNT_SUBJECT: an_account()})

    assert refused(directory, f"Bearer {account_token(azp='svc_other')}") is (
        TokenRefusal.NOT_A_SERVICE_ACCOUNT
    )
    # With a `sid` the account path is never taken, and the subject is nobody's here.
    assert refused(directory, f"Bearer {account_token(sid='sess-9')}") is TokenRefusal.NO_PRINCIPAL


# ---------------------------------------------------------------- what an account reaches


@dataclass
class OwnersGrants:
    """An `EntitlementStore` answering the owner's grants, which a test may change."""

    grants: dict[str, tuple[Grant, ...]]
    loaded: list[str] = field(default_factory=list)

    async def load(self, principal_id: str, at: datetime) -> EntitlementSet:
        self.loaded.append(principal_id)
        return EntitlementSet(principal_id=principal_id, grants=self.grants.get(principal_id, ()))


def a_grant(capability: Capability) -> Grant:
    return Grant(capability=capability, scope=Scope.unrestricted())


def wired(store: OwnersGrants, directory: PrincipalDirectory) -> GateWiring:
    return GateWiring(
        authority=authority(directory), versions=Versions(), store=store, cache=NoCache()
    )


def reach(caller: Caller, store: OwnersGrants) -> EntitlementSet:
    import asyncio

    return asyncio.run(reach_of(caller, wired(store, Accounts()), now()))


def test_an_account_reaches_what_its_owner_holds_and_its_ceiling_admits_and_nothing_else() -> None:
    """M1.8.2's first clause. The owner holds hours and a note; the ceiling admits hours and
    margin. Delete this and the account can reach the owner's note (a ceiling ignored) or the
    margin the owner never held (a ceiling that grants), which is union authority."""
    directory = Accounts()
    caller = authenticated(directory, f"Bearer {keyed(directory).secret}")
    store = OwnersGrants({OWNER: (a_grant(READ_HOURS), a_grant(WRITE_NOTE))})

    held = reach(caller, store)

    assert held.principal_id == ACCOUNT
    assert held.scope_for(READ_HOURS, now()) is not None
    assert held.scope_for(READ_MARGIN, now()) is None
    assert held.scope_for(WRITE_NOTE, now()) is None
    assert store.loaded == [OWNER]


def test_an_account_loses_a_capability_on_the_request_after_its_owner_does() -> None:
    """M1.8.2's last clause. Delete this and the reach can be computed once at authentication, or
    cached under the account, and a revoked grant keeps working through the integration."""
    directory = Accounts()
    caller = authenticated(directory, f"Bearer {keyed(directory).secret}")
    store = OwnersGrants({OWNER: (a_grant(READ_HOURS),)})
    assert reach(caller, store).scope_for(READ_HOURS, now()) is not None

    store.grants[OWNER] = ()

    assert reach(caller, store).scope_for(READ_HOURS, now()) is None


def test_a_person_is_still_resolved_as_themselves() -> None:
    """The sibling of the three above. Delete this and a change to `reach_of` can resolve a person
    through a path meant for an account, or not at all."""
    person = authenticated(Accounts(), f"Bearer {token_for('u_narrow')}")
    store = OwnersGrants({"u_narrow": (a_grant(READ_HOURS),)})

    held = reach(person, store)

    assert held.principal_id == "u_narrow"
    assert held.scope_for(READ_HOURS, now()) is not None
    assert store.loaded == ["u_narrow"]


def test_an_account_is_answered_on_the_api_channel_with_no_session() -> None:
    """Through the real application: `/me` says who asked and on which channel. Delete this and the
    account could be given the console's ceiling, where the approve and admin verbs live."""
    directory = Accounts()
    minted = keyed(directory)
    store = OwnersGrants({OWNER: (a_grant(READ_HOURS),)})
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wired(store, directory)
        answer = client.get(
            f"{API_PREFIX}/me", headers={"authorization": f"Bearer {minted.secret}"}
        )
        wrong = client.get(
            f"{API_PREFIX}/me", headers={"authorization": f"Bearer {minted.secret[:-2]}zz"}
        )

    assert answer.status_code == 200, answer.text
    assert answer.json()["principal_id"] == ACCOUNT
    assert answer.json()["channel"] == "api"
    assert wrong.status_code == 401


# ------------------------------------------------------------------------------ the routes


@dataclass
class Store:
    """A `service_account_routes.ServiceAccountStore` in memory, owner named on every call."""

    listed: dict[str, AccountListed] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def owned(self, owner: str, *, limit: int) -> tuple[tuple[AccountListed, ...], bool]:
        self.calls.append({"owned": owner})
        mine = tuple(v for v in self.listed.values() if v.account.owner_principal_id == owner)
        return mine, False

    async def register(
        self,
        account: ServiceAccount,
        *,
        subject: str | None,
        label: str,
        ent_hash: str,
        trace_id: str,
    ) -> Registered:
        self.calls.append({"register": account.client_id, "owner": account.owner_principal_id})
        if account.client_id in self.listed:
            return Registered.TAKEN
        self.listed[account.client_id] = AccountListed(
            account=account, label=label, created_at=now(), keys=()
        )
        return Registered.REGISTERED

    async def issue_key(
        self,
        client_id: str,
        *,
        owner: str,
        not_after: datetime,
        label: str,
        now: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> IssuedKey | None:
        self.calls.append({"issue": client_id, "owner": owner})
        found = self.listed.get(client_id)
        if found is None or found.account.owner_principal_id != owner:
            return None
        return issue(found.account, now=now, not_after=not_after, label=label)

    async def revoke_key(self, handle: str, *, owner: str) -> bool:
        self.calls.append({"revoke": handle, "owner": owner})
        return False

    async def retire(self, client_id: str, *, owner: str) -> bool:
        self.calls.append({"retire": client_id, "owner": owner})
        found = self.listed.get(client_id)
        return found is not None and found.account.owner_principal_id == owner


ROUTE_GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (a_grant(CREDENTIAL), a_grant(READ_HOURS)),
    "u_narrow": (a_grant(READ_HOURS),),
}


def an_app(store: Store) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    app.include_router(service_account_routes.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = wired(OwnersGrants(dict(ROUTE_GRANTS)), Accounts())
        app.state.service_accounts = store
        yield client


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def client(store: Store) -> Iterator[TestClient]:
    yield from an_app(store)


def auth(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


ACCOUNTS = f"{API_PREFIX}/govern/service-accounts"
KEYS = f"{API_PREFIX}/govern/service-accounts/keys"


def registration(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "client_id": ACCOUNT,
        "label": "Weekly report",
        "ceiling": [READ_HOURS.value, READ_MARGIN.value],
        "not_after": (now() + timedelta(days=30)).isoformat(),
    }
    body.update(over)
    return body


def test_an_administrator_registers_an_account_they_own_and_is_told_what_it_cannot_use(
    client: TestClient, store: Store
) -> None:
    """The positive case for the refusals below. Delete this and a route that refuses everything
    passes them; and the owner could be taken from the body, lending somebody else's reach."""
    answer = client.post(ACCOUNTS, json=registration(), headers=auth("u_admin"))

    assert answer.status_code == 201, answer.text
    assert answer.json()["not_held_now"] == [READ_MARGIN.value]
    assert store.calls == [{"register": ACCOUNT, "owner": "u_admin"}]


def test_a_caller_without_the_credential_authority_is_refused_before_any_store(
    client: TestClient, store: Store
) -> None:
    """Delete this and anybody signed in could mint a credential that acts as themselves from a
    script, which is a decision this install reserves to whoever holds `admin:credential`."""
    assert client.get(ACCOUNTS, headers=auth("u_narrow")).status_code == 404
    assert client.post(ACCOUNTS, json=registration(), headers=auth("u_narrow")).status_code == 404
    assert store.calls == []


def test_a_wildcard_or_a_repeated_capability_in_a_ceiling_is_refused(client: TestClient) -> None:
    """Delete this and an account's ceiling can be `read:client.*`, which is a claim about what it
    reaches rather than a list an auditor reads."""
    wild = client.post(
        ACCOUNTS, json=registration(ceiling=["read:client.*"]), headers=auth("u_admin")
    )
    twice = client.post(
        ACCOUNTS, json=registration(ceiling=[READ_HOURS.value] * 2), headers=auth("u_admin")
    )
    assert wild.status_code == 422
    assert twice.status_code == 422


def test_a_key_is_answered_whole_once_and_the_listing_never_carries_it(
    client: TestClient, store: Store
) -> None:
    """Delete this and the listing can carry the secret, which is a credential in every browser
    history and response log that ever saw the screen."""
    client.post(ACCOUNTS, json=registration(), headers=auth("u_admin"))
    lapse = (now() + timedelta(days=7)).isoformat()

    issued = client.post(
        KEYS, json={"client_id": ACCOUNT, "not_after": lapse}, headers=auth("u_admin")
    )
    listing = client.get(ACCOUNTS, headers=auth("u_admin"))

    assert issued.status_code == 201, issued.text
    key = issued.json()["key"]
    assert key.startswith("brn.")
    assert key not in listing.text
    assert key.split(".")[2] not in listing.text


def test_somebody_elses_account_is_not_found(client: TestClient, store: Store) -> None:
    """Delete this and an administrator can issue a key for an account another person owns, which
    acts at that person's reach."""
    store.listed[ACCOUNT] = AccountListed(
        account=ServiceAccount(
            client_id=ACCOUNT,
            subject=ACCOUNT,
            owner_principal_id="u_wide",
            ceiling=(READ_HOURS,),
            not_after=now() + timedelta(days=3),
        ),
        label="",
        created_at=now(),
        keys=(),
    )
    lapse = (now() + timedelta(days=1)).isoformat()

    key = client.post(
        KEYS, json={"client_id": ACCOUNT, "not_after": lapse}, headers=auth("u_admin")
    )
    gone = client.post(f"{ACCOUNTS}/retire", json={"client_id": ACCOUNT}, headers=auth("u_admin"))

    assert key.status_code == 404
    assert gone.status_code == 404


# ---------------------------------------------------------------------------- the database


def _database_tests_need() -> None:
    from tests.fixtures.scratch_postgres import admin_url

    admin_url()


@contextmanager
def through_0095(database: str) -> Iterator[str]:
    """The soft-deleted tables with `0047`, `0049`, `0050`, `0054` and `0095` applied.

    Where the server has pgvector, `retirable` is at head already. Where it has not, it stops at
    `0048`'s function, and the migrations these tests read are run for real with everything between
    stamped: the sign-in ledger, the retention tables `0054`'s trigger names, the session ending
    entry, the credential entry and this change.
    """
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import migrate

    run_for_real = (
        ("0046", "0047"),
        ("0048", "0049"),
        ("0049", "0050"),
        ("0053", "0054"),
        ("0096", "0095"),
        ("0095", "0095b"),
    )
    with retirable(database) as url:
        if not has_pgvector(url):
            for stamp, upgrade in run_for_real:
                migrate(database, "stamp", stamp)
                migrate(database, "upgrade", upgrade)
        yield url


def test_through_0095_a_key_acts_at_its_owners_live_reach_and_stops_with_the_owner() -> None:
    """M1.8.2 end to end on real rows, as the application role. An account is registered and keyed
    through the store; a real authority over the real directory authenticates the key; the real
    entitlement store resolves the owner; `reach_of` narrows by the ceiling. Then the owner's grant
    is revoked and the account loses it, and the owner is disabled and the key is refused. Delete
    this and any of the three can be true in memory and false in the database."""
    _database_tests_need()

    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.principal_directory import StoredDirectory
    from brain.identity.service_account_store import StoredServiceAccounts
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_entitlement_store import a_grant as grant_row
    from tests.unit.test_entitlement_store import a_principal, revoke

    with through_0095("brain_sa_reach") as url:
        a_principal(url, OWNER)
        grant_row(url, OWNER, READ_HOURS.value)
        grant_row(url, OWNER, WRITE_NOTE.value)

        async def go() -> tuple[Any, ...]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                accounts = StoredServiceAccounts(sessions)
                registered = await accounts.register(
                    an_account(), subject=None, label="report", ent_hash="", trace_id="t-1"
                )
                minted = await accounts.issue_key(
                    ACCOUNT,
                    owner=OWNER,
                    not_after=now() + timedelta(days=2),
                    label="",
                    now=now(),
                    ent_hash="",
                    trace_id="t-2",
                )
                assert minted is not None
                gate = GateWiring(
                    authority=authority(StoredDirectory(sessions)),
                    versions=Versions(),
                    store=StoredEntitlements(sessions),
                    cache=NoCache(),
                )
                header = f"Bearer {minted.secret}"
                caller = await gate.authority.authenticate(header, now=now())
                before = await reach_of(caller, gate, now())
                revoke(url, OWNER, READ_HOURS.value)
                after = await reach_of(caller, gate, now())
                sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", OWNER)
                try:
                    await gate.authority.authenticate(header, now=now())
                    disabled: TokenRefusal | None = None
                except TokenRefusedError as why:
                    disabled = why.reason
                return registered, before, after, disabled
            finally:
                await engine.dispose()

        registered, before, after, disabled = run(go)
        grants = sql(
            url, "SELECT count(*) FROM gate.capability_grant WHERE principal_id = %s", ACCOUNT
        )
        entries = sql(
            url,
            "SELECT actor_id, subject FROM obs.audit_entry WHERE action = 'credential'"
            " ORDER BY seq",
        )

    assert registered is Registered.REGISTERED
    assert before.principal_id == ACCOUNT
    assert before.scope_for(READ_HOURS, now()) is not None
    assert before.scope_for(WRITE_NOTE, now()) is None
    assert after.scope_for(READ_HOURS, now()) is None
    assert disabled is TokenRefusal.OWNER_INACTIVE
    assert grants == [(0,)]
    assert len(entries) == 2 and all(actor == OWNER for actor, _ in entries)


def test_through_0095_a_partner_holds_a_window_and_never_a_standing_grant() -> None:
    """M1.2.4 on the resolver every request goes through. A partner with a standing grant and a
    grant lapsing two hours after it was written resolves to the second only; a staff member's
    standing grant is untouched; and a downgrade to `0093` gives the partner's standing grant back,
    which is the proof the clause and not something else took it away. Delete this and a partner
    with rows in the grant table holds them, which `standing_entitlement` has always said they do
    not."""
    _database_tests_need()
    from tests.fixtures.scratch_postgres import migrate, sql
    from tests.unit.test_entitlement_store import a_grant as grant_row
    from tests.unit.test_entitlement_store import a_principal

    def held(url: str, principal_id: str) -> list[str]:
        rows = sql(
            url,
            "SELECT capability FROM gate.held_grants(%s, now()) ORDER BY capability",
            principal_id,
        )
        return [capability for (capability,) in rows]

    with through_0095("brain_sa_partner") as url:
        ends = now() + timedelta(days=90)
        a_principal(url, "p_partner", employment="partner", not_after=ends)
        a_principal(url, "u_staff")
        grant_row(url, "p_partner", READ_MARGIN.value)
        grant_row(url, "p_partner", READ_HOURS.value, not_after=now() + timedelta(hours=2))
        grant_row(url, "u_staff", READ_MARGIN.value)
        partner, staff = held(url, "p_partner"), held(url, "u_staff")
        migrate("brain_sa_partner", "downgrade", "0096")
        partner_before_0095 = held(url, "p_partner")

    assert partner == [READ_HOURS.value]
    assert staff == [READ_MARGIN.value]
    assert partner_before_0095 == [READ_HOURS.value, READ_MARGIN.value]


def test_a_retired_key_or_account_is_not_found_by_the_request_path() -> None:
    """Delete this and revocation could flag a row the lookup still returns."""
    _database_tests_need()

    from brain.identity.service_account_store import StoredServiceAccounts
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_entitlement_store import a_principal

    with through_0095("brain_sa_retire") as url:
        a_principal(url, OWNER)

        async def go() -> tuple[Any, ...]:
            engine = app_engine(url)
            try:
                accounts = StoredServiceAccounts(make_session_factory(engine))
                await accounts.register(
                    an_account(), subject=ACCOUNT_SUBJECT, label="", ent_hash="", trace_id=""
                )
                minted = await accounts.issue_key(
                    ACCOUNT,
                    owner=OWNER,
                    not_after=now() + timedelta(days=1),
                    label="",
                    now=now(),
                    ent_hash="",
                    trace_id="",
                )
                assert minted is not None
                handle = minted.record.handle
                found = await accounts.by_key(handle)
                by_subject = await accounts.by_subject(ACCOUNT_SUBJECT)
                not_mine = await accounts.revoke_key(handle, owner="u_other")
                revoked = await accounts.revoke_key(handle, owner=OWNER)
                after_revoke = await accounts.by_key(handle)
                retired = await accounts.retire(ACCOUNT, owner=OWNER)
                after_retire = await accounts.by_subject(ACCOUNT_SUBJECT)
                return found, by_subject, not_mine, revoked, after_revoke, retired, after_retire
            finally:
                await engine.dispose()

        found, by_subject, not_mine, revoked, after_revoke, retired, after_retire = run(go)

    assert found is not None and found[1].client_id == ACCOUNT
    assert by_subject is not None and by_subject.client_id == ACCOUNT
    assert not_mine is False
    assert revoked is True and after_revoke is None
    assert retired is True and after_retire is None


def test_the_test_file_names_the_migration_that_exists() -> None:
    """Delete this and a renamed migration turns the database half into skips nobody reads."""
    assert Path(MIGRATION).is_file()
