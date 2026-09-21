"""What the scheduled staff sync did, its credential, and a leaver's agents, over HTTP.

The four addresses `brain.staff_source_routes` gained on 2026-09-21, driven through the real
application with the token machinery `tests/unit/test_api_routes.py` provides. The runs and the
transfers read a database, which is a recording stand-in here: the statements are the store's and
are run against PostgreSQL in `tests/unit/test_staff_sync_store.py`. The credential is kept in the
in-memory vault `tests/unit/test_credentials.py` provides.

Task ids: M1.6.12, M1.8.6, M1.8.9
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain import staff_source_routes
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.staff_source_view import transfers_for
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.credential_routes import CREDENTIAL_AUTHORITY
from brain.identity.staff_roster import RunOutcome
from brain.identity.staff_source import STAFF_SOURCE_SETTING
from brain.install import hold_saved
from brain.knowledge.visibility import Visibility
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.ops.staff_sync_store import RunRecord
from brain.staff_source_routes import (
    CREDENTIAL_FORMS,
    CREDENTIAL_PATH,
    RUNS_PATH,
    STAFF_CREDENTIAL_SLOT,
    TRANSFERS_PATH,
)
from tests.fixtures.http_client import Response
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_credentials import Recorded, Vault

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

WHOLE = Scope.unrestricted()
IN_MAINTENANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value="maintenance"),))
CLIENT_NAMES = "read:client.name"
#: The row capability `entitlement_ceiling` adds beside a field capability.
CLIENT_ROWS = "read:client"
STAFF_SOURCE_CAPABILITY = "read:staff_source"

#: A credential nothing else in any output could contain.
SECRET = "cli_sentinel:staff-secret-SENTINEL-41c7"


def _grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    # The credential authority over one department, which is not a grant over this slot.
    "u_narrow": (
        Grant(capability=CREDENTIAL_AUTHORITY, scope=IN_MAINTENANCE),
        _grant(CLIENT_NAMES, IN_MAINTENANCE),
        _grant(CLIENT_ROWS, IN_MAINTENANCE),
    ),
    # May read the screen at the configuration plane, which is not the runs' plane.
    "u_wide": (
        _grant(STAFF_SOURCE_CAPABILITY),
        _grant(plane_capability(Plane.CONFIGURATION).value),
    ),
    "u_admin": (
        Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),
        _grant(STAFF_SOURCE_CAPABILITY),
        _grant(plane_capability(Plane.CONTENT).value),
        _grant(CLIENT_NAMES),
        _grant(CLIENT_ROWS),
    ),
    "u_prefix": (),
    "u_elsewhere": (),
}


class Grants:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=Grants(),
        cache=NoCache(),
    )


def an_agent(agent_id: str, owner: str, scope: Scope = WHOLE) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=f"Agent {agent_id}",
        persona="answers questions about clients",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id=owner, department=""),
        authority=AgentAuthority(scope=scope, capabilities=(Capability(value=CLIENT_NAMES),)),
        created_by=owner,
    )


# ------------------------------------------------------------------ the database stand-in
@dataclass
class Result:
    found: Any

    def scalar_one_or_none(self) -> Any:
        return self.found


@dataclass
class Session:
    agents: dict[str, AgentRecord]
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

    async def execute(self, statement: Any) -> Result:
        self.executed.append(statement)
        wanted = statement.compile().params
        agent_id = wanted.get("id_1")
        return Result(self.agents.get(agent_id) if isinstance(agent_id, str) else None)


@dataclass
class Database:
    runs: tuple[RunRecord, ...] = ()
    leavers: frozenset[str] = frozenset()
    agents: dict[str, AgentRecord] = field(default_factory=dict)
    executed: list[Any] = field(default_factory=list)
    opened: int = 0

    def __call__(self) -> Session:
        self.opened += 1
        return Session(self.agents, self.executed)


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Database:
    held = Database()

    async def read_runs(session: object, limit: int = 10) -> tuple[RunRecord, ...]:
        return held.runs

    async def read_leavers(session: object) -> frozenset[str]:
        return held.leavers

    async def leavers_agents(session: object) -> tuple[frozenset[str], list[AgentRecord]]:
        owned = [one for one in held.agents.values() if one.audience.owner_id in held.leavers]
        return held.leavers, sorted(owned, key=lambda one: one.agent_id)

    monkeypatch.setattr(staff_source_routes, "sessions_of", lambda request: held)
    monkeypatch.setattr(staff_source_routes, "read_runs", read_runs)
    monkeypatch.setattr(staff_source_routes, "read_leavers", read_leavers)
    monkeypatch.setattr(staff_source_routes, "_leavers_agents", leavers_agents)
    monkeypatch.setattr(staff_source_routes, "record_of", lambda row: row)
    return held


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    as_if_ci_had_a_database(monkeypatch)
    before = hold_saved({STAFF_SOURCE_SETTING: "lark"})
    built: FastAPI = create_app(Settings(env="development", database_url=""))
    yield built
    hold_saved(before)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.console_reads = None
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


def get(c: TestClient, path: str, pid: str) -> Response:
    answer: Response = c.get(f"{API_PREFIX}{path}", headers=headers(pid))
    return answer


# --------------------------------------------------------------------------- the runs
REFUSED_RUN = RunRecord(
    source="lark",
    started_at=LONG_AGO,
    finished_at=LONG_AGO + timedelta(seconds=3),
    outcome=RunOutcome.CREDENTIAL_REFUSED,
    detail="The staff source refused the kept credential: app secret invalid. Nobody was changed.",
)
APPLIED_RUN = RunRecord(
    source="lark",
    started_at=LONG_AGO - timedelta(days=1),
    finished_at=LONG_AGO - timedelta(days=1),
    outcome=RunOutcome.APPLIED,
    detail="Read 3 people from lark.",
    added=("Ada",),
    marked_left=("Cal",),
    withheld=(),
)


def test_the_screen_shows_a_refused_credential_changed_nobody(
    client: TestClient, database: Database
) -> None:
    """M1.8.6's last clause: a sync whose credential is refused says so on the Staff sources screen.

    Delete this and the run row could be written and never shown, which is a refusal nobody sees."""
    database.runs = (REFUSED_RUN, APPLIED_RUN)

    answer = get(client, RUNS_PATH, "u_admin")

    assert answer.status_code == 200, answer.text
    first, second = answer.json()["runs"]
    assert first["outcome"] == "credential_refused"
    assert first["changed_nobody"] is True
    assert "Nobody was changed" in first["detail"]
    assert first["added"] == first["marked_left"] == []
    assert second["changed_nobody"] is False
    assert (second["added"], second["marked_left"]) == (["Ada"], ["Cal"])


def test_a_reader_below_the_trials_plane_is_answered_no_runs_and_no_table_is_read(
    client: TestClient, database: Database
) -> None:
    """A run names people, so it is read at the content plane, and the refusal is an empty list.

    Delete this and a reader holding only the configuration grant reads who joined and who left."""
    database.runs = (APPLIED_RUN,)

    wide = get(client, RUNS_PATH, "u_wide")
    nobody = get(client, RUNS_PATH, "u_none")

    assert wide.json() == nobody.json() == {"runs": []}
    assert database.opened == 0


# --------------------------------------------------------------------- the credential
def test_the_credential_is_replaced_into_its_slot_recorded_and_never_sent_back(
    app: FastAPI, client: TestClient
) -> None:
    """M1.8.6: replaced from the console, kept in the vault, recorded in the ledger, not echoed.

    Delete this and the credential the nightly sync reads has no writer but a server shell."""
    vault = Vault()
    writes = Recorded()
    app.state.credentials = Credentials(vault, environ={}, writes=writes)

    with capture_logs() as logged:
        answer = client.put(
            f"{API_PREFIX}{CREDENTIAL_PATH}", json={"value": SECRET}, headers=headers("u_admin")
        )

    assert answer.status_code == 200, answer.text
    assert vault.written == [(STAFF_CREDENTIAL_SLOT.path, {KEY_FIELD: SECRET})]
    assert STAFF_CREDENTIAL_SLOT.path == "connector_keys/staff_source"
    assert [one["slot"] for one in writes.records] == [STAFF_CREDENTIAL_SLOT.path]
    assert answer.json()["held"] is True
    assert SECRET not in answer.text
    assert SECRET not in json.dumps(logged, default=str)


def test_a_credential_grant_over_one_department_neither_reads_nor_replaces_the_slot(
    app: FastAPI, client: TestClient
) -> None:
    """The secret reaches every person in the company, so a scoped grant is no grant here.

    Delete this and a department's credential administrator repoints the company's staff sync."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={})

    read = get(client, CREDENTIAL_PATH, "u_narrow")
    write = client.put(
        f"{API_PREFIX}{CREDENTIAL_PATH}", json={"value": SECRET}, headers=headers("u_narrow")
    )
    nobody = get(client, CREDENTIAL_PATH, "u_none")

    assert read.status_code == write.status_code == nobody.status_code == 404
    assert vault.written == []
    assert vault.asked == []


def test_the_credential_screen_says_whether_it_is_held_and_what_the_chosen_source_takes(
    app: FastAPI, client: TestClient
) -> None:
    """The positive read: metadata only, and the form for the source this install chose.

    Delete this and a person cannot tell whether the nightly sync has anything to read with."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={})

    answer = get(client, CREDENTIAL_PATH, "u_admin")

    assert answer.status_code == 200, answer.text
    assert answer.json()["held"] is False
    assert answer.json()["form"] == CREDENTIAL_FORMS["lark"]
    assert vault.asked == [STAFF_CREDENTIAL_SLOT.path]


# ---------------------------------------------------------------- a leaver's agents
def test_a_leavers_agent_is_listed_for_transfer_and_left_running() -> None:
    """M1.8.9: listed for a new owner, still enabled, and its ceiling untouched by the listing.

    Delete this and a leaver's agents could be stopped the night the sync marks them, which is
    the opposite of what the requirement asks, or never listed at all."""
    theirs = an_agent("a_theirs", "u_gone")
    mine = an_agent("a_mine", "u_admin")
    admin = EntitlementSet(principal_id="u_admin", grants=GRANTS["u_admin"])

    listed = transfers_for([theirs, mine], leavers=frozenset({"u_gone"}), reader=admin)

    assert listed == (theirs,)
    assert listed[0].disabled_at is None


def test_an_agent_reaching_further_than_the_reader_is_not_offered_to_them() -> None:
    """The new owner is a ceiling entering the world with their name on it, so it must fit them.

    Delete this and a department administrator takes on a company-wide agent by accepting it."""
    theirs = an_agent("a_theirs", "u_gone")
    narrow = EntitlementSet(principal_id="u_narrow", grants=GRANTS["u_narrow"])

    assert transfers_for([theirs], leavers=frozenset({"u_gone"}), reader=narrow) == ()


def test_taking_a_leavers_agent_moves_the_owner_and_never_the_reach(
    client: TestClient, database: Database
) -> None:
    """The steward moves and the ceiling does not, so the agent runs at no wider reach than before.

    Delete this and the transfer could write a different authority with the new owner's name."""
    theirs = an_agent("a_theirs", "u_gone")
    database.leavers = frozenset({"u_gone"})
    database.agents = {"a_theirs": theirs}

    listed = get(client, TRANSFERS_PATH, "u_admin")
    taken = client.post(f"{API_PREFIX}{TRANSFERS_PATH}/a_theirs", headers=headers("u_admin"))

    assert [one["agent_id"] for one in listed.json()["transfers"]] == ["a_theirs"]
    assert listed.json()["transfers"][0]["running"] is True
    assert taken.status_code == 200, taken.text
    assert taken.json() == {"agent_id": "a_theirs", "owner_id": "u_admin"}
    (update,) = [one for one in database.executed if one.is_dml]
    assert update.compile().params == {"owner_id": "u_admin", "id_1": "a_theirs"}


def test_an_agent_whose_owner_has_not_left_cannot_be_taken_and_nothing_is_written(
    client: TestClient, database: Database
) -> None:
    """The one refusal, for an owner still here, an agent out of reach, and one that is absent.

    Delete this and anybody who may adopt could take any agent by naming it."""
    database.leavers = frozenset({"u_gone"})
    database.agents = {"a_kept": an_agent("a_kept", "u_still_here")}

    kept = client.post(f"{API_PREFIX}{TRANSFERS_PATH}/a_kept", headers=headers("u_admin"))
    absent = client.post(f"{API_PREFIX}{TRANSFERS_PATH}/a_nobody", headers=headers("u_admin"))

    assert kept.status_code == absent.status_code == 404
    assert kept.json()["message"] == absent.json()["message"]
    assert [one for one in database.executed if one.is_dml] == []


def test_the_screens_writes_take_no_more_than_their_one_field(client: TestClient) -> None:
    """An extra field is refused, so nothing but the secret can be posted to the credential write.

    Delete this and a later field could be accepted and ignored on the one route taking a secret."""
    answer = client.put(
        f"{API_PREFIX}{CREDENTIAL_PATH}",
        json={"value": SECRET, "slot": "providers/anthropic"},
        headers=headers("u_admin"),
    )

    assert answer.status_code == 422
    assert SECRET not in answer.text
