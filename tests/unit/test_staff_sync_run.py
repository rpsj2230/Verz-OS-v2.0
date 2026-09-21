"""The scheduled staff sync, against a stand-in directory, a stand-in vault and a recording session.

`brain.ops.staff_sync_run.sync_staff_on` chooses the source, leases the credential, reads, checks,
plans and applies. These tests hold each step with stand-ins so the order and the refusals are
visible without a database: the session records every statement it is handed, the store's readers
are replaced with the answers a table would give, and the directory answers from recorded shapes.
The same run against a real PostgreSQL is `tests/unit/test_staff_sync_store.py`, which CI runs.

Task ids: M1.6.1, M1.6.2, M1.6.12, M1.8.6
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

from brain.connectors.staff_directories import Answer, Outbound
from brain.identity.staff_roster import Application, RunOutcome, StoredMember, digest_of
from brain.identity.staff_source import STAFF_SOURCE_LOCATION_SETTING, STAFF_SOURCE_SETTING
from brain.ops import staff_sync_run
from brain.ops.connectable import READING_ROLE
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_sync import NO_KEY
from brain.ops.connector_sync_run import ConnectorKeyAbsentError
from brain.ops.secrets import SecretRef, SecretsUnavailableError
from brain.ops.staff_sync_run import (
    CREDENTIAL_REFUSED_PREFIX,
    NOBODY_CHANGED,
    NOT_READ_ON_A_SCHEDULE,
    STAFF_SOURCE_SLOT,
    sync_staff_on,
)
from brain.ops.staff_sync_store import RunRecord
from tests.unit.test_staff_directories import lark_pages

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
    return held


def run(
    *,
    env: Mapping[str, str],
    keys: Keys,
    fetch: Directory | None = None,
    sessions: Sessions | None = None,
    saved: Mapping[str, str] | None = None,
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
