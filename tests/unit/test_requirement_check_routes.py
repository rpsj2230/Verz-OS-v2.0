"""The Requirement checks screen: the register by area, a check recorded, and who may do either.

Driven through the real application with the token machinery of `tests/unit/test_api_routes.py`,
over a register of five rows and a store in memory. Every refusal has a permitted sibling. The
store's statements run against PostgreSQL at the foot, and **skip without a server**.

Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import requirement_check_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.identity.first_administrator import ADMINISTRATION
from brain.requirement_check_routes import (
    CHECKED_BY,
    DOCS,
    REQUIREMENT_CHECK_AUTHORITY,
    NewCheck,
    RequirementCheckView,
    register_of,
)
from brain.requirements import REGISTER_IN_DOCS, Register, Requirement, load_register
from brain.tables.requirement_check import CheckOutcome
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

CHECKS = f"{API_PREFIX}/requirements/checks"
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
COMMIT = "a" * 40


def row(ident: str, area: str) -> Requirement:
    return Requirement(
        id=ident,
        source="a source",
        area=area,
        requirement=f"requirement {ident}",
        leaves=("M1.1.1",),
        proof=("M1.8.8",),
        decision=None,
    )


REGISTER = Register(
    requirements=(
        row("ARC-A-001", "Permissions"),
        row("DEC-30", "Observability"),
        row("GAP2-03", "Departments"),
        row("FEAT-1.10", "Permissions"),
        row("LIVE2-03", "Models"),
    )
)


@dataclass
class Checks:
    """`RequirementChecks` in memory: the newest per id wins, as the statement picks."""

    kept: list[RequirementCheckView] = field(default_factory=list)

    async def latest(self) -> Mapping[str, RequirementCheckView]:
        newest: dict[str, RequirementCheckView] = {}
        for one in sorted(self.kept, key=lambda c: c.checked_at):
            newest[one.requirement_id] = one
        return newest

    async def record(self, check: NewCheck) -> RequirementCheckView:
        kept = RequirementCheckView(
            requirement_id=check.requirement_id,
            outcome=check.outcome,
            checked_by=check.checked_by,
            checked_at=LONG_AGO + timedelta(minutes=len(self.kept)),
            release_commit=check.release_commit,
            note=check.note,
        )
        self.kept.append(kept)
        return kept


def grant(value: Capability | str) -> Grant:
    capability = value if isinstance(value, Capability) else Capability(value=value)
    return Grant(capability=capability, scope=Scope.unrestricted())


#: `u_admin` holds the authority over everything; `u_narrow` holds it over one department;
#: `u_wide` holds every other administration capability and not this one.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (grant(REQUIREMENT_CHECK_AUTHORITY),),
    "u_narrow": (Grant(capability=REQUIREMENT_CHECK_AUTHORITY, scope=Scope.department("web")),),
    "u_wide": tuple(grant(one) for one in ADMINISTRATION if one != "admin:requirement_check"),
}


class Directory:
    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return Principal(
                    id=pid, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=pid
                )
        return None


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


@pytest.fixture
def checks() -> Checks:
    return Checks()


@pytest.fixture
def app(checks: Checks) -> Iterator[FastAPI]:
    built = create_app(Settings(env="development"))
    built.include_router(requirement_check_routes.router)
    yield built


@pytest.fixture
def client(app: FastAPI, checks: Checks) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.requirement_checks = checks
        app.state.requirement_register = REGISTER
        app.state.release_commit = COMMIT
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


def read(c: TestClient, pid: str, **params: str) -> Response:
    answer: Response = c.get(CHECKS, params=params, headers=headers(pid))
    return answer


def record(c: TestClient, pid: str, body: Mapping[str, object]) -> Response:
    answer: Response = c.post(CHECKS, json=dict(body), headers=headers(pid))
    return answer


# ------------------------------------------------------------------------ reading


def test_the_screen_lists_every_area_and_opens_on_the_first_one_a_leaf_asks_checks_of(
    client: TestClient,
) -> None:
    """The positive case for the refusals below. Every area in the register's order, each naming
    the leaf that asks for its checks, and Permissions' two rows in the owner's words, unchecked.
    Delete this and the refusals pass against a route that shows nothing to anybody."""
    body = read(client, "u_admin").json()
    assert [(a["area"], a["proves"], a["requirements"]) for a in body["areas"]] == [
        ("Permissions", "M1.8.8", 2),
        ("Observability", "M24.3.6", 1),
        ("Departments", "M2.3.2", 1),
        ("Models", "M5.6.5", 1),
    ]
    assert body["area"] == "Permissions"
    assert [(r["id"], r["requirement"], r["latest"]) for r in body["requirements"]] == [
        ("ARC-A-001", "requirement ARC-A-001", None),
        ("FEAT-1.10", "requirement FEAT-1.10", None),
    ]
    assert body["release_commit"] == COMMIT


def test_the_four_areas_the_leaves_name_are_the_register_s_own_words() -> None:
    """`CHECKED_BY` is keyed by area names, and a name the register does not use is an area whose
    checks can never be counted against its leaf. Held against the shipped register rather than
    against itself. Delete this and "Permission" or "Observability " passes every test above."""
    shipped = load_register(DOCS / REGISTER_IN_DOCS)
    areas = {one.area for one in shipped.requirements}
    assert set(CHECKED_BY) <= areas
    assert set(CHECKED_BY.values()) == {"M1.8.8", "M2.3.2", "M5.6.5", "M24.3.6"}


def test_the_shipped_register_is_what_a_process_with_no_override_reads() -> None:
    """Delete this and the screen can read a register path that exists in a checkout and not in
    the image, and every install shows "no register"."""

    class State:
        pass

    class App:
        state = State()

    class Asked:
        app = App()

    found = register_of(Asked())  # type: ignore[arg-type]
    assert found is not None
    assert found == load_register(Path(DOCS) / REGISTER_IN_DOCS)


def test_a_reader_without_the_authority_over_everything_is_refused_in_one_sentence(
    client: TestClient,
) -> None:
    """The authority over one department is not the authority, and every other administration
    capability is not it either. One sentence, naming the screen. Delete this and a department
    admin reads a map of where the install was seen to fail."""
    for pid in ("u_narrow", "u_wide", "u_none"):
        answer = read(client, pid)
        assert answer.status_code == 404, pid
        assert "ARC-A-001" not in answer.text


def test_the_administrators_are_granted_the_authority() -> None:
    """Delete this and the screen exists with nobody on any install able to open it, because the
    first administrator's grants and reconciliation both read `ADMINISTRATION`."""
    assert REQUIREMENT_CHECK_AUTHORITY.value in ADMINISTRATION


# ------------------------------------------------------------------------ recording


def test_a_check_is_recorded_as_the_person_asking_on_the_running_release_and_read_back(
    client: TestClient, checks: Checks
) -> None:
    """**The mechanism M1.8.8, M2.3.2, M5.6.5 and M24.3.6 share.** A check against one requirement,
    recorded as the caller and against the release this process runs, is the newest check that
    requirement shows, and the area's counts move. A second check supersedes it without editing
    it. Delete this and a check can be kept against nobody, or on no release, or read back as the
    first check ever made."""
    answer = record(
        client,
        "u_admin",
        {"requirement_id": "ARC-A-001", "outcome": "passed", "note": "Asked as Priya; refused."},
    )
    assert answer.status_code == 201, answer.text
    assert answer.json()["checked_by"] == "u_admin"
    assert answer.json()["release_commit"] == COMMIT

    record(
        client,
        "u_admin",
        {"requirement_id": "ARC-A-001", "outcome": "failed", "note": "Priya saw the salary."},
    )
    body = read(client, "u_admin").json()
    latest = body["requirements"][0]["latest"]
    assert (latest["outcome"], latest["note"]) == ("failed", "Priya saw the salary.")
    assert body["areas"][0] == {
        "area": "Permissions",
        "proves": "M1.8.8",
        "requirements": 2,
        "passed": 0,
        "failed": 1,
        "unchecked": 1,
    }
    assert [one.outcome for one in checks.kept] == [CheckOutcome.PASSED, CheckOutcome.FAILED]


def test_an_area_is_chosen_by_name_and_an_unknown_one_falls_back(client: TestClient) -> None:
    """Delete this and the Models tab shows Permissions' rows, or an unknown area empties the
    screen."""
    models = read(client, "u_admin", area="Models").json()
    assert (models["area"], [r["id"] for r in models["requirements"]]) == ("Models", ["LIVE2-03"])
    unknown = read(client, "u_admin", area="Nothing like this").json()
    assert unknown["area"] == "Permissions"


def test_a_check_against_an_id_the_register_does_not_carry_is_refused_before_anything_is_kept(
    client: TestClient, checks: Checks
) -> None:
    """A well-formed id nobody wrote, an empty note, a note of spaces and an outcome that is not
    one of the two are each a 422, and nothing is kept. Delete this and checks accumulate against
    requirements nobody can read back."""
    for body in (
        {"requirement_id": "ARC-Z-999", "outcome": "passed", "note": "did it"},
        {"requirement_id": "ARC-A-001", "outcome": "passed", "note": ""},
        {"requirement_id": "ARC-A-001", "outcome": "passed", "note": "   "},
        {"requirement_id": "ARC-A-001", "outcome": "maybe", "note": "did it"},
        {"requirement_id": "not an id", "outcome": "passed", "note": "did it"},
    ):
        assert record(client, "u_admin", body).status_code == 422, body
    assert checks.kept == []


def test_recording_needs_the_authority_over_everything_too(
    client: TestClient, checks: Checks
) -> None:
    """Delete this and somebody who may not read the checks may still write one."""
    for pid in ("u_narrow", "u_wide"):
        answer = record(
            client, pid, {"requirement_id": "ARC-A-001", "outcome": "passed", "note": "did it"}
        )
        assert answer.status_code == 404, pid
    assert checks.kept == []


# ------------------------------------------------------------------------ with a server


@pytest.mark.needs_db
def test_the_store_keeps_every_check_and_reads_back_the_newest_per_requirement() -> None:
    """The statements against `ops.requirement_check` as the application role: two checks of one
    requirement and one of another read back as the newest of each, the row not editable. **Skips
    without a server.**"""
    from brain.requirement_check_routes import StoredRequirementChecks
    from brain.session import make_session_factory
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine

    with retirable("brain_requirement_check") as url:
        if not has_pgvector(url):
            pytest.skip("0099 needs the whole chain, which needs pgvector")

        async def work() -> Mapping[str, RequirementCheckView]:
            engine = app_engine(url)
            try:
                store = StoredRequirementChecks(make_session_factory(engine))
                for ident, outcome in (
                    ("ARC-A-001", CheckOutcome.PASSED),
                    ("DEC-30", CheckOutcome.PASSED),
                    ("ARC-A-001", CheckOutcome.FAILED),
                ):
                    await store.record(
                        NewCheck(
                            requirement_id=ident,
                            outcome=outcome,
                            checked_by="u_admin",
                            release_commit=COMMIT,
                            note="checked",
                        )
                    )
                return await store.latest()
            finally:
                await engine.dispose()

        newest = run(work)
        [(may_update,)] = sql(
            url, "SELECT has_table_privilege('brain_app', 'ops.requirement_check', 'UPDATE')"
        )

    assert {k: v.outcome for k, v in newest.items()} == {
        "ARC-A-001": CheckOutcome.FAILED,
        "DEC-30": CheckOutcome.PASSED,
    }
    assert may_update is False


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL. Delete this and the model can drift from the table `0099` builds,
    and a check the route accepts is refused by the database, or the other way round."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from sqlalchemy.schema import CreateTable

    from brain.db import metadata
    from tests.unit.test_tables import VERSIONS, rendered, squash

    dialect = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
    migration = VERSIONS / "0099_requirement_check.py"
    expected = squash(
        str(CreateTable(metadata.tables["ops.requirement_check"]).compile(dialect=dialect))
    )
    upgrade = squash(rendered("upgrade", migration))
    assert expected in upgrade
    assert "UPDATE ON ops.requirement_check" not in upgrade
