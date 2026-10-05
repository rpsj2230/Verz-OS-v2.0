"""The scheduled staff sync, against a stand-in directory, a stand-in vault and a recording session.

`brain.ops.staff_sync_run.sync_staff_on` chooses the source, leases the credential, reads, checks,
plans and applies. These tests hold each step with stand-ins so the order and the refusals are
visible without a database: the session records every statement it is handed, the store's readers
are replaced with the answers a table would give, and the directory answers from recorded shapes.
The same run against a real PostgreSQL is `tests/unit/test_staff_sync_store.py`, which CI runs.

Task ids: M1.6.1, M1.6.2, M1.6.5, M1.6.12, M1.8.6
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

import pytest

from brain.connectors import ldap_directory
from brain.connectors.staff_directories import Answer, Fetch, Outbound
from brain.identity.staff_roster import Application, RunOutcome, StoredMember, digest_of
from brain.identity.staff_source import STAFF_SOURCE_LOCATION_SETTING, STAFF_SOURCE_SETTING
from brain.identity.standing import StandingPlan
from brain.ops import staff_sync_run
from brain.ops.connectable import READING_ROLE
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_sync import NO_KEY
from brain.ops.connector_sync_run import ConnectorKeyAbsentError
from brain.ops.secrets import SecretRef, SecretsUnavailableError
from brain.ops.staff_accounts_run import NO_ISSUER
from brain.ops.staff_sync_run import (
    CREDENTIAL_REFUSED_PREFIX,
    NOBODY_CHANGED,
    NOT_READ_ON_A_SCHEDULE,
    STAFF_SOURCE_SLOT,
    sync_staff_on,
)
from brain.ops.staff_sync_store import RunRecord
from tests.unit.test_staff_directories import google_directory, graph_directory, lark_pages

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
NOW = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)
APP_ID = "cli_a1b2c3d4"
APP_SECRET = "sentinel-app-secret-0f9e8d"
TENANT_TOKEN = "t-sentinel-tenant-token"

LARK_ENV = {STAFF_SOURCE_SETTING: "lark", STAFF_SOURCE_LOCATION_SETTING: "larksuite.com"}


# ------------------------------------------------------------------ the stand-ins
@dataclass
class Session:
    executed: list[Any]

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> Session:
        return self

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)


@dataclass
class Sessions:
    executed: list[Any] = field(default_factory=list)

    def __call__(self) -> Session:
        return Session(self.executed)


@dataclass
class Lease:
    given: str | None
    failure: SecretsUnavailableError | None = None
    closed: list[datetime] = field(default_factory=list)

    def key(self) -> str:
        if self.failure is not None:
            raise self.failure
        assert self.given is not None
        return self.given

    def close(self, now: datetime) -> LeaseOutcome:
        self.closed.append(now)
        return LeaseOutcome.REVOKED


@dataclass
class Keys:
    lease_given: Lease
    asked: list[SecretRef] = field(default_factory=list)

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        self.asked.append(ref)
        return self.lease_given


@dataclass
class Directory:
    """Lark: the tenant token exchange, then the recorded department and people pages."""

    token_answer: Answer = field(
        default_factory=lambda: Answer(200, {"code": 0, "tenant_access_token": TENANT_TOKEN})
    )
    sent: list[Outbound] = field(default_factory=list)

    async def __call__(self, outbound: Outbound) -> Answer:
        self.sent.append(outbound)
        if outbound.url.endswith("/auth/v3/tenant_access_token/internal"):
            return self.token_answer
        for fragment, page in lark_pages().items():
            if fragment in outbound.url:
                return Answer(200, page)
        return Answer(404, {"msg": f"no stand-in for {outbound.url}"})


@dataclass
class Store:
    """What the two readers answer, and what the writer was handed."""

    members: tuple[StoredMember, ...] = ()
    last_applied: datetime | None = None
    written: list[tuple[Application, RunRecord]] = field(default_factory=list)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    held = Store()

    async def read_members(session: object, source: str) -> tuple[StoredMember, ...]:
        return held.members

    async def read_last_applied(session: object, source: str) -> datetime | None:
        return held.last_applied

    async def write_application(session: object, app: Application, record: RunRecord) -> None:
        held.written.append((app, record))

    monkeypatch.setattr(staff_sync_run, "read_members", read_members)
    monkeypatch.setattr(staff_sync_run, "read_last_applied", read_last_applied)
    monkeypatch.setattr(staff_sync_run, "write_application", write_application)
    monkeypatch.setattr(staff_sync_run, "run_row", lambda record: ("run", record))

    # The standing step reads principals and the ledger, which a recording session cannot answer;
    # `tests/unit/test_standing_run.py` runs it against a real database.
    async def plan_standing(*_: object, **__: object) -> StandingPlan:
        return StandingPlan()

    async def apply_standing(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(staff_sync_run, "plan_standing", plan_standing)
    monkeypatch.setattr(staff_sync_run, "apply_standing", apply_standing)
    return held


def run(
    *,
    env: Mapping[str, str],
    keys: Keys,
    fetch: Fetch | None = None,
    sessions: Sessions | None = None,
    saved: Mapping[str, str] | None = None,
    trial: bool = False,
) -> tuple[staff_sync_run.StaffSyncRun, Sessions]:
    recording = sessions or Sessions()
    clock = iter(NOW + timedelta(seconds=n) for n in range(1000))
    ran = asyncio.run(
        sync_staff_on(
            sessions=recording,  # type: ignore[arg-type]
            now=NOW,
            env=env,
            keys=keys,
            fetch=fetch or Directory(),
            clock=lambda: next(clock),
            saved=saved,
            trial=trial,
        )
    )
    return ran, recording


def records_of(sessions: Sessions) -> list[RunRecord]:
    return [one[1] for one in sessions.executed if isinstance(one, tuple) and one[0] == "run"]


# ------------------------------------------------------------------------ the runs
def test_a_scheduled_run_reads_lark_with_the_kept_credential_and_applies_the_plan(
    store: Store,
) -> None:
    """M1.6.1 and M1.6.12: read on a schedule, through the source interface, and applied.

    Delete this and the run could plan and never write, which is the state the audit found."""
    keys = Keys(Lease(f"{APP_ID}:{APP_SECRET}"))
    directory = Directory()

    ran, _ = run(env=LARK_ENV, keys=keys, fetch=directory)

    assert ran.outcome is RunOutcome.APPLIED
    assert keys.asked == [SecretRef(path=f"connector_keys/{STAFF_SOURCE_SLOT}", role=READING_ROLE)]
    exchange = directory.sent[0]
    assert exchange.json_body == {"app_id": APP_ID, "app_secret": APP_SECRET}
    assert all(
        one.headers.get("Authorization") == f"Bearer {TENANT_TOKEN}" for one in directory.sent[1:]
    )
    ((application, record),) = store.written
    assert record.outcome is RunOutcome.APPLIED
    assert sorted(application.added) == ["Ada Lovelace", "Katherine Johnson"]
    assert record.added == application.added
    assert keys.lease_given.closed == [NOW]


def test_a_credential_the_source_refuses_changes_nobody_and_says_so(store: Store) -> None:
    """M1.8.6: a refused credential appends one run with the vendor's words and writes no member.

    Delete this and a rotated secret could be read as a directory that answered with nobody, and
    a complete roster of nobody marks the whole company as having left."""
    keys = Keys(Lease(f"{APP_ID}:{APP_SECRET}"))
    refused = Directory(token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"}))
    store.members = (StoredMember(digest_of("ada@example.com"), "Ada Lovelace"),)
    store.last_applied = NOW - timedelta(days=1)

    ran, sessions = run(env=LARK_ENV, keys=keys, fetch=refused)

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert store.written == []
    (record,) = records_of(sessions)
    assert record.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert record.detail.startswith(CREDENTIAL_REFUSED_PREFIX)
    assert "app secret invalid" in record.detail
    assert NOBODY_CHANGED in record.detail
    assert (record.added, record.marked_left, record.renamed) == ((), (), ())
    assert APP_SECRET not in json.dumps([record.detail, *record.withheld])
    assert len(refused.sent) == 1
    assert keys.lease_given.closed == [NOW]


def test_a_refusal_code_inside_a_success_is_a_refused_credential_even_beside_a_token(
    store: Store,
) -> None:
    """Lark refuses inside an HTTP 200 with a business code, and a body can carry both.

    A mutation found the code check unwatched: every refusal here also lacked a token, so the
    missing token refused it first. Delete this and a code-carrying answer with a stale token in
    it is read with, and the directory's refusal becomes pages nobody may read."""
    refusing = Directory(
        token_answer=Answer(
            200, {"code": 99991663, "msg": "app not installed", "tenant_access_token": "stale"}
        )
    )

    ran, _ = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=refusing)

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert len(refusing.sent) == 1
    assert store.written == []


def test_no_credential_held_changes_nobody_and_contacts_nobody(store: Store) -> None:
    """The vault holding nothing at the slot is a run row and no request to the directory.

    Delete this and a missing credential could be sent as an empty one."""
    keys = Keys(Lease(None, failure=ConnectorKeyAbsentError(NO_KEY)))
    directory = Directory()

    ran, sessions = run(env=LARK_ENV, keys=keys, fetch=directory)

    assert ran.outcome is RunOutcome.NO_CREDENTIAL
    assert directory.sent == []
    assert store.written == []
    (record,) = records_of(sessions)
    assert NOBODY_CHANGED in record.detail


def test_a_credential_not_shaped_as_an_identifier_and_a_secret_is_refused_before_it_is_sent(
    store: Store,
) -> None:
    """A pasted secret with no identifier is told back in words, and nothing leaves the server.

    Delete this and half a credential is posted to Lark every night."""
    directory = Directory()

    ran, _ = run(env=LARK_ENV, keys=Keys(Lease(APP_SECRET)), fetch=directory)

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert directory.sent == []
    assert store.written == []


def test_a_source_with_no_scheduled_reader_changes_nobody_and_names_why(store: Store) -> None:
    """A hand-kept spreadsheet is read on upload; the run says so rather than reading nothing.

    Delete this and a spreadsheet install shows a nightly run that silently did nothing."""
    keys = Keys(Lease("unused"))

    ran, sessions = run(env={STAFF_SOURCE_SETTING: "spreadsheet"}, keys=keys)

    assert ran.outcome is RunOutcome.NOT_SCHEDULABLE
    assert keys.asked == []
    (record,) = records_of(sessions)
    assert record.detail == NOT_READ_ON_A_SCHEDULE["spreadsheet"]
    assert store.written == []


def test_an_install_that_reads_no_staff_list_records_no_run(store: Store) -> None:
    """`none` is the absence of a source, and a nightly row saying so would bury real runs.

    Delete this and every install without a directory fills the table with a row a night."""
    ran, sessions = run(env={STAFF_SOURCE_SETTING: "none"}, keys=Keys(Lease("unused")))

    assert ran.outcome is None
    assert sessions.executed == []


def test_a_location_that_is_not_a_lark_platform_is_misconfigured_and_contacts_nobody(
    store: Store,
) -> None:
    """The platform chooses which host the secret is sent to, so a wrong one is refused first.

    Delete this and a location somebody else chose receives the company's app secret."""
    directory = Directory()
    env = {STAFF_SOURCE_SETTING: "lark", STAFF_SOURCE_LOCATION_SETTING: "attacker.example"}

    ran, _ = run(env=env, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=directory)

    assert ran.outcome is RunOutcome.MISCONFIGURED
    assert directory.sent == []


def test_a_listed_person_is_added_to_the_roster_and_is_never_given_a_sign_in(store: Store) -> None:
    """M1.6.2: a roster source and a sign-in source are two axes. A run writes roster rows only.

    Every statement the run hands the session is a member write or a run record, and the writer
    it calls holds no principal and no binding: `brain.identity.sign_in_binding` is the only
    writer of a sign-in and it takes an administrator. The database half, that no principal and
    no binding exist after a run, is `test_staff_sync_store`'s. Delete this and a run could be
    extended to provision whoever a spreadsheet names."""
    run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))

    ((application, _),) = store.written
    assert {type(one).__name__ for one in application.writes} == {"MemberWrite"}


# ------------------------------------------------ chosen on the screen, and a leaver's agents
def test_a_source_saved_on_the_screen_is_the_source_the_worker_reads_with_no_server_edit(
    store: Store,
) -> None:
    """The worker holds no saved settings of its own, so each run lays `ops.setting` over its
    environment. Here the environment names no source at all and the saved values name Lark.

    Delete this and connecting a source from the console would change nothing at night until
    somebody edited the environment file on the server."""
    ran, _ = run(env={}, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), saved=LARK_ENV)

    assert ran.outcome is RunOutcome.APPLIED
    ((application, _),) = store.written
    assert application.source == "lark"


def test_a_saved_choice_outranks_the_one_the_environment_file_names(store: Store) -> None:
    """`brain.install.value_of`'s order, kept by the worker: saved, then the environment.

    Delete this and an install whose template named a spreadsheet would go on reading nothing
    after the owner connected Lark on the screen."""
    ran, _ = run(
        env={STAFF_SOURCE_SETTING: "spreadsheet"},
        keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")),
        saved=LARK_ENV,
    )

    assert ran.outcome is RunOutcome.APPLIED


def is_the_stop(statement: object) -> bool:
    return str(statement).startswith("UPDATE agent.agent SET disabled_at")


def test_the_run_that_applies_a_roster_stops_every_running_agent_a_leaver_owns(
    store: Store,
) -> None:
    """M1.8.9 as the owner decided it on 2026-09-21: stopped until a new owner accepts it.

    The statement is run in the applying transaction and says exactly the rule: set
    `disabled_at` on agents owned by a marked leaver, still running and never archived. Delete
    this and a leaver's agents keep running with nobody answering for them."""
    _, sessions = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))

    (stop,) = [one for one in sessions.executed if is_the_stop(one)]
    rendered = str(stop)
    leavers = "(SELECT DISTINCT auth.principal_identity.principal_id"
    assert f"WHERE agent.agent.owner_id IN {leavers}" in rendered
    assert "auth.staff_member.left_at IS NOT NULL" in rendered
    assert "agent.agent.disabled_at IS NULL AND agent.agent.archived_at IS NULL" in rendered
    assert stop.compile().params["disabled_at"] == NOW


def test_a_run_that_could_not_read_stops_nobody_s_agents(store: Store) -> None:
    """A refused credential says nothing about who left, so it stops no agent either.

    Delete this and a bad night at the directory could stop agents on the strength of silence."""
    refused = Directory(token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"}))

    _, sessions = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=refused)

    assert not [one for one in sessions.executed if is_the_stop(one)]


@dataclass
class ByPath:
    """Leases by the slot asked for: the staff source's own is empty, the Lark app's holds a key."""

    held: Mapping[str, str]
    asked: list[SecretRef] = field(default_factory=list)

    def lease(self, ref: SecretRef, *, now: datetime) -> Lease:
        self.asked.append(ref)
        if ref.path in self.held:
            return Lease(self.held[ref.path])
        return Lease(None, failure=ConnectorKeyAbsentError("no key at this slot"))


def test_a_lark_staff_source_with_no_key_of_its_own_reads_with_the_lark_app_s_key(
    store: Store,
) -> None:
    """The Connectors screen keeps one Lark app for several uses, and the staff list is one.

    The staff source's own slot is asked first and wins when it holds a key; only an absent key
    falls back. Delete this and connecting Lark once on the Connectors screen leaves the nightly
    staff sync with nothing to read with."""
    shared = f"connector_keys/{staff_sync_run.SHARED_APP_SLOTS['lark']}"
    keys = ByPath({shared: f"{APP_ID}:{APP_SECRET}"})

    ran, _ = run(env=LARK_ENV, keys=keys)  # type: ignore[arg-type]

    assert ran.outcome is RunOutcome.APPLIED
    assert [one.path for one in keys.asked] == [f"connector_keys/{STAFF_SOURCE_SLOT}", shared]
    own = ByPath({f"connector_keys/{STAFF_SOURCE_SLOT}": f"{APP_ID}:{APP_SECRET}", shared: "x:y"})
    run(env=LARK_ENV, keys=own)  # type: ignore[arg-type]
    assert [one.path for one in own.asked] == [f"connector_keys/{STAFF_SOURCE_SLOT}"]


def test_a_source_with_no_shared_app_does_not_fall_back_and_changes_nobody(store: Store) -> None:
    """Delete this and a Microsoft source could read with a Lark secret."""
    env = {STAFF_SOURCE_SETTING: "microsoft_entra", STAFF_SOURCE_LOCATION_SETTING: "example.com"}
    keys = ByPath({"connector_keys/lark": f"{APP_ID}:{APP_SECRET}"})

    ran, _ = run(env=env, keys=keys)  # type: ignore[arg-type]

    assert ran.outcome is RunOutcome.NO_CREDENTIAL
    assert [one.path for one in keys.asked] == [f"connector_keys/{STAFF_SOURCE_SLOT}"]


# ------------------------------------------------------------------------ LDAP, M1.6.6
LDAP_ENV = {
    STAFF_SOURCE_SETTING: "ldap",
    STAFF_SOURCE_LOCATION_SETTING: "ldaps://dc1.example.com/DC=example,DC=com",
}


def ldap_through(monkeypatch: pytest.MonkeyPatch, directory: Any) -> list[str]:
    """Route the LDAP reader through a stand-in directory, recording the credential it saw."""
    seen: list[str] = []
    real = ldap_directory.read_directory

    def reading(location: str, credential: str) -> Any:
        seen.append(credential)
        return real(location, credential, opener=directory)

    monkeypatch.setattr(staff_sync_run, "read_directory", reading)
    return seen


def test_an_ldap_directory_is_read_on_a_schedule_with_the_kept_service_account(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LDAP has a scheduled reader now, leasing the same slot as every staff source and binding
    with the credential held there. Delete this and choosing LDAP is a nightly NOT_SCHEDULABLE."""
    from tests.unit.test_ldap_directory import CREDENTIAL, STAFF, opened, paged

    directory = opened({ldap_directory.DEFAULT_USER_FILTER: paged(STAFF, 2)})
    seen = ldap_through(monkeypatch, directory)
    keys = Keys(Lease(CREDENTIAL))

    ran, _ = run(env=LDAP_ENV, keys=keys)

    assert ran.outcome is RunOutcome.APPLIED
    assert keys.asked == [SecretRef(path=f"connector_keys/{STAFF_SOURCE_SLOT}", role=READING_ROLE)]
    assert seen == [CREDENTIAL]
    assert directory.directory.closed
    ((application, _),) = store.written
    assert "Ada" in application.added
    assert keys.lease_given.closed == [NOW]


def test_a_refused_ldap_bind_is_a_refused_credential_that_names_no_password(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong password is filed as a refused credential, not an outage, and the row does not
    carry it. Delete this and a rotated service account password reads as the directory down."""
    from tests.unit.test_ldap_directory import PASSWORD

    def refusing(location: Any, account: Any) -> Any:
        raise ldap_directory.LdapBindRefusedError("dc1.example.com:636 refused the account")

    ldap_through(monkeypatch, refusing)

    ran, sessions = run(env=LDAP_ENV, keys=Keys(Lease(f"svc@example.com:{PASSWORD}")))

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    (record,) = records_of(sessions)
    assert record.detail.startswith(CREDENTIAL_REFUSED_PREFIX)
    assert PASSWORD not in record.detail
    assert store.written == []


# ------------------------------------------------------- Google Workspace and Entra, M1.6.5
WORKSPACE_ENV = {
    STAFF_SOURCE_SETTING: "google_workspace",
    STAFF_SOURCE_LOCATION_SETTING: "example.com",
}
TENANT = "8f1a0e5c-0000-4000-8000-00000000000a"
ENTRA_ENV = {STAFF_SOURCE_SETTING: "microsoft_entra", STAFF_SOURCE_LOCATION_SETTING: TENANT}
ACCESS_TOKEN = "ya29.sentinel-access-token"


@dataclass
class Vendor:
    """A vendor answering its token exchange at one address, then its pages by URL fragment."""

    exchange_at: str
    pages: Mapping[str, Mapping[str, Any]]
    token_answer: Answer = field(
        default_factory=lambda: Answer(200, {"access_token": ACCESS_TOKEN, "token_type": "Bearer"})
    )
    sent: list[Outbound] = field(default_factory=list)

    async def __call__(self, outbound: Outbound) -> Answer:
        self.sent.append(outbound)
        if outbound.method == "POST":
            return self.token_answer if outbound.url == self.exchange_at else Answer(404, {})
        for fragment, page in self.pages.items():
            if fragment in outbound.url:
                return Answer(200, page)
        return Answer(404, {"error": {"message": f"no stand-in for {outbound.url}"}})


@pytest.fixture(scope="module")
def workspace_credential() -> str:
    """What the Staff sources screen keeps for a service account key made in the test."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from brain.connectors.google_service_account import kept_value

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    pasted = json.dumps(
        {
            "type": "service_account",
            "private_key": private,
            "client_email": "sync@a-project.iam.gserviceaccount.com",
        }
    )
    return kept_value("reader@example.com", pasted)


def test_google_workspace_is_read_on_a_schedule_as_its_service_account_with_its_groups(
    store: Store, workspace_credential: str
) -> None:
    """M1.6.5: Workspace has a nightly reader. The kept key signs an assertion, the assertion is
    exchanged at Google's token endpoint, and the directory, its managers and its groups are read
    with the token and applied, with the archived user and the meeting room left out.

    Delete this and choosing Google Workspace on the Staff sources screen is a form that keeps a
    key nothing reads, which is what every run said before this reader existed."""
    vendor = Vendor("https://oauth2.googleapis.com/token", google_directory())
    keys = Keys(Lease(workspace_credential))

    ran, _ = run(env=WORKSPACE_ENV, keys=keys, fetch=vendor)

    assert ran.outcome is RunOutcome.APPLIED
    exchange, *reads = vendor.sent
    assert exchange.form is not None
    assert exchange.form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    assert all(one.method == "GET" for one in reads)
    assert all(one.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}" for one in reads)
    assert any("/members?" in one.url for one in reads)
    ((application, _),) = store.written
    assert sorted(application.added) == ["Ada Lovelace", "Katherine Johnson"]
    assert keys.lease_given.closed == [NOW]


def test_a_workspace_exchange_google_refuses_changes_nobody_and_repeats_no_key(
    store: Store, workspace_credential: str
) -> None:
    """A scope the Admin console never delegated is Google refusing the assertion, which is a
    refused credential in Google's words, with nothing read and no part of the key in the row.

    Delete this and a missing delegation reads as the directory being down, or as nobody."""
    refused = Answer(
        401,
        {
            "error": "unauthorized_client",
            "error_description": "Client is unauthorized to retrieve access tokens using this "
            "method, or client not authorized for any of the scopes requested.",
        },
    )
    vendor = Vendor("https://oauth2.googleapis.com/token", google_directory(), token_answer=refused)

    ran, sessions = run(env=WORKSPACE_ENV, keys=Keys(Lease(workspace_credential)), fetch=vendor)

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    (record,) = records_of(sessions)
    assert "not authorized for any of the scopes" in record.detail
    assert workspace_credential.split(":")[-1][:24] not in record.detail
    assert len(vendor.sent) == 1
    assert store.written == []


def test_a_credential_kept_for_another_source_is_refused_for_workspace_before_anything_is_sent(
    store: Store,
) -> None:
    """A Lark app's `<id>:<secret>` left in the slot after the choice changed is not a key, so the
    run refuses it in words that repeat none of it and signs nothing.

    Delete this and the reader tries to rebuild a key from somebody else's secret."""
    vendor = Vendor("https://oauth2.googleapis.com/token", google_directory())

    ran, sessions = run(env=WORKSPACE_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=vendor)

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    (record,) = records_of(sessions)
    assert APP_SECRET not in record.detail
    assert vendor.sent == []


def test_microsoft_entra_is_read_on_a_schedule_with_its_managers_and_groups(store: Store) -> None:
    """The application's identifier and secret exchanged for a Graph token, then the people with
    their managers expanded and the groups with their members, each on Graph. The disabled
    account and the guest are left out.

    Delete this and the nightly Entra read can drop its group walk, and a group mapped to a role
    on the Roles screen has nothing to match."""
    vendor = Vendor(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token", graph_directory()
    )
    keys = Keys(Lease(f"{APP_ID}:{APP_SECRET}"))

    ran, _ = run(env=ENTRA_ENV, keys=keys, fetch=vendor)

    assert ran.outcome is RunOutcome.APPLIED
    exchange, *reads = vendor.sent
    assert exchange.form is not None
    assert exchange.form["grant_type"] == "client_credentials"
    assert exchange.form["scope"] == "https://graph.microsoft.com/.default"
    assert all(one.url.startswith("https://graph.microsoft.com/") for one in reads)
    assert any("transitiveMembers" in one.url for one in reads)
    ((application, _),) = store.written
    assert sorted(application.added) == ["Ada Lovelace", "Katherine Johnson"]


# ------------------------------------------------------------ what a run says it read
class NamelessDepartments(Directory):
    """Lark answering an app without `contact:department.base:readonly`: the walk succeeds and
    every department arrives with no `name`, which is what the owner's install read."""

    async def __call__(self, outbound: Outbound) -> Answer:
        answer = await super().__call__(outbound)
        if "departments/0/children" not in outbound.url:
            return answer
        data = answer.body["data"]
        items = [{k: v for k, v in one.items() if k != "name"} for one in data["items"]]
        return Answer(answer.status, {**answer.body, "data": {**data, "items": items}})


def test_a_run_that_read_puts_what_it_read_on_its_row_and_in_the_job_history(
    store: Store,
) -> None:
    """The run row and the control's summary carry the reading's report: departments read and
    named, people read and placed. Delete this and a run that placed everybody and one that placed
    nobody are the same row on the Staff sources screen."""
    ran, _ = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))

    ((_, record),) = store.written
    assert record.report == (
        "Read 2 departments, 2 with a name, and 3 people; 3 placed in a department.",
        NO_ISSUER,
    )
    assert ran.report == record.report
    assert record.report[0] in ran.summary()


def test_a_lark_read_without_department_names_says_nobody_was_placed_and_which_scope_to_add(
    store: Store,
) -> None:
    """The owner's install on 2026-09-29, at the run: 123 people added, none placed, and a row
    that said only "applied". The row now says why and what to change.

    Delete this and the run can go back to applying a list that placed nobody in silence."""
    ran, _ = run(
        env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=NamelessDepartments()
    )

    ((application, record),) = store.written
    assert {one.department for one in application.writes} == {None}
    said = " ".join(record.report)
    assert "Read 2 departments, 0 with a name, and 3 people; 0 placed in a department." in said
    assert "Not placed: 3 in a department that came back with no name." in said
    assert "contact:department.base:readonly" in said
    for name in ("Ada Lovelace", "Katherine Johnson", "ada@example.com"):
        assert name not in said
    assert "contact:department.base:readonly" in ran.summary()


def test_a_trial_reads_as_the_run_would_and_writes_no_member_and_stops_nobody(
    store: Store,
) -> None:
    """A trial is the night's run with nothing applied: the same lease and read, one `tried` row
    with the counts a run would change and the report, no member written and no agent stopped.

    Delete this and Try a read can start applying the list it was pressed to preview."""
    keys = Keys(Lease(f"{APP_ID}:{APP_SECRET}"))
    ran, sessions = run(env=LARK_ENV, keys=keys, trial=True)

    assert store.written == []
    assert not [one for one in sessions.executed if is_the_stop(one)]
    (record,) = records_of(sessions)
    assert record.outcome is RunOutcome.TRIED
    assert ran.outcome is RunOutcome.TRIED
    assert record.detail == (
        # Two, because Grace has left and a first run adds only the people still here.
        "Trial read. Read lark. A run now would add 2, mark 0 as having left and move 0 to a new "
        f"address. {NOBODY_CHANGED}"
    )
    assert (record.added, record.marked_left, record.renamed) == ((), (), ())
    assert record.report[0].startswith("Read 2 departments, 2 with a name, and 3 people")
    assert keys.lease_given.closed == [NOW]


def test_a_trial_that_could_not_read_says_it_was_a_trial(store: Store) -> None:
    """A trial refused by the source is recorded as the refusal it is, opened so nobody reads it
    as a failed night. Delete this and a pressed button reads as the nightly sync breaking."""
    refused = Directory(token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"}))

    ran, sessions = run(
        env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=refused, trial=True
    )

    (record,) = records_of(sessions)
    assert record.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert record.detail.startswith(f"Trial read. {CREDENTIAL_REFUSED_PREFIX}")
    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert record.report == ()


def test_a_scheduled_run_is_not_opened_as_a_trial(store: Store) -> None:
    """The sibling: a night's refusal opens with the refusal, not with the trial's words. Delete
    this and every failed night would claim to have been a trial somebody pressed."""
    refused = Directory(token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"}))

    _, sessions = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), fetch=refused)

    (record,) = records_of(sessions)
    assert record.detail.startswith(CREDENTIAL_REFUSED_PREFIX)


def test_an_applied_run_places_its_people_in_the_organisation_and_a_trial_does_not(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every applied run hands its roster to `apply_organisation` with the last applied run it read
    before applying, so a first run ends no placement; a trial applies nothing and places nobody.
    Delete this and the organisation plan goes back to being applied by nothing on any install."""
    from brain.identity.organisation_sync import OrganisationPlan

    handed: list[tuple[str, datetime | None]] = []

    async def apply(sessions: object, roster: object, **kwargs: Any) -> OrganisationPlan:
        handed.append((getattr(roster, "source", ""), kwargs["last_applied"]))
        return OrganisationPlan(
            source="lark",
            to_join=(),
            to_leave=(),
            to_appoint=(),
            to_stand_down=(),
            unregistered=(),
            contested=(),
            withheld=(),
            refusals=(),
        )

    async def principals(sessions: object, roster: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr(staff_sync_run, "apply_organisation", apply)
    monkeypatch.setattr(staff_sync_run, "roster_principals", principals)
    store.last_applied = NOW - timedelta(days=1)

    run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")), trial=True)
    assert handed == []
    run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))
    assert handed == [("lark", NOW - timedelta(days=1))]
