"""Nominating a person for a role and a third person deciding it, held to `0208` and the domain.

The pure half holds `0208`'s copies to the model and the rules they copy, and the route's two
refusals to the words the domain gives them. The database half drives the application's own
routes over PostgreSQL as the application role, so `0208`'s policies, `0102`'s grant trigger and
the role grant the confirmation writes are the ones an install has.

Task ids: M33.1.2.3
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from typing import Any, Final

import httpx
import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain import govern_routes
from brain.console.global_surfaces import GOVERNANCE_CONTROL
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Clause, Op, Scope
from brain.db import metadata
from brain.identity.roles import SCOPE_REQUIRED, SEPARATION_OF_DUTIES_WARNING, Role
from brain.nomination_routes import (
    A_NOMINATION_IS_A_PROPOSAL_ANYBODY_ON_THE_ROLES_SCREEN_MAY_MAKE,
    A_NOMINATION_SAYS_NOTHING_ABOUT_WHETHER_ITS_NOMINEE_EXISTS,
    A_PERSON_IS_PROPOSED_BY_SOMEBODY_ELSE,
    DECISION_PATH,
    NOMINATIONS_PATH,
)
from brain.tables import role_grant, role_nomination
from brain.tables.identity import one_of
from brain.tables.role_nomination import NominationOutcome
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_review_store import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0208_role_nominations.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
API = "/api/v1"

WHOLE = Scope.unrestricted()
IN_WEB = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
ROLES_READ = (
    Grant(capability=Capability(value="read:role"), scope=WHOLE),
    Grant(capability=plane_capability(Plane.CONFIGURATION), scope=WHOLE),
)

#: The People screen's read, which is what being shown a person's name asks.
PEOPLE_READ = Grant(capability=screen("people").read.requires, scope=WHOLE)

#: `u_wide` nominates and holds the grant decision too, so its refusal is the two-person rule
#: and not a missing grant; it may name nobody. `u_admin` decides everywhere and may name anybody,
#: `u_elsewhere` decides only over the web department, `u_prefix` sees the screen and decides
#: nothing, `u_none` sees nothing.
GRANTS: Final[Mapping[str, tuple[Grant, ...]]] = {
    "u_wide": (*ROLES_READ, Grant(capability=GOVERNANCE_CONTROL, scope=WHOLE)),
    "u_admin": (*ROLES_READ, PEOPLE_READ, Grant(capability=GOVERNANCE_CONTROL, scope=WHOLE)),
    "u_elsewhere": (*ROLES_READ, Grant(capability=GOVERNANCE_CONTROL, scope=IN_WEB)),
    "u_prefix": ROLES_READ,
    "u_none": (),
}


def module() -> Any:
    return migration_module(MIGRATION)


# ------------------------------------------------------------------------ the migration
def test_the_migration_builds_the_nomination_table_exactly_as_the_model_declares_it() -> None:
    """Compared on rendered DDL. Delete this and the model can declare the third-person check or
    the scope rule while the database never has it."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["gate.role_nomination"]
    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_rules_the_migration_copies_are_the_rules_the_code_holds() -> None:
    """Each copied value against the one it copies, outside both. Delete this and a seventh role,
    a longer reason or a third outcome is refused by one side and admitted by the other."""
    m = module()
    assert one_of("role", Role) == m.ROLES
    assert one_of("role", SCOPE_REQUIRED) == m.SCOPED
    assert one_of("outcome", NominationOutcome) == m.OUTCOMES
    assert m.REASON_CHARS == govern_routes.REASON_CHARS == role_nomination.REASON_CHARS
    assert (m.SCOPE_SLUG_CHARS, m.OUTCOME_CHARS, m.ROLE_CHARS) == (
        role_nomination.SCOPE_SLUG_CHARS,
        role_nomination.OUTCOME_CHARS,
        role_grant.ROLE_CHARS,
    )


def test_the_application_may_decide_a_nomination_and_never_delete_or_rewrite_one() -> None:
    """Read off the emitted statements. Delete this and a nomination can be deleted with its
    decision, or its nominee and reason rewritten after a confirmer read them."""
    emitted = squash(rendered("upgrade", MIGRATION))
    assert "ALTER TABLE gate.role_nomination ENABLE ROW LEVEL SECURITY" in emitted
    grants = [one for one in emitted.split(";") if "GRANT" in one and "role_nomination" in one]
    assert grants and not any("DELETE" in one for one in grants)
    assert (
        "GRANT UPDATE (outcome, decided_by, decided_at, grant_id) ON gate.role_nomination TO "
        "brain_app" in emitted
    )


def test_the_two_refusals_say_what_the_domain_decides() -> None:
    """The nominating rule names the Roles screen's read and the self-nomination sentence names
    somebody else. Delete this and the constants can drift into saying a nomination needs the
    authority that appoints, which would make it pointless."""
    assert "Roles screen" in A_NOMINATION_IS_A_PROPOSAL_ANYBODY_ON_THE_ROLES_SCREEN_MAY_MAKE
    assert "somebody else" in A_PERSON_IS_PROPOSED_BY_SOMEBODY_ELSE
    assert GOVERNANCE_CONTROL.value == "approve:grant"


# ------------------------------------------------------------------------ on a server
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_nominations_{uuid.uuid4().hex[:8]}") as url:
        for pid, department in (
            ("u_wide", "sales"),
            ("u_admin", "sales"),
            ("u_elsewhere", "web"),
            ("u_prefix", "sales"),
            ("u_narrow", "sales"),
            ("u_web", "web"),
        ):
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name,"
                " primary_department) VALUES (%s, 'human', 'staff', %s, %s)"
                " ON CONFLICT (id) DO NOTHING",
                pid,
                f"Person {pid}",
                department,
            )
        yield url


def nominate(pid: str, principal: str, role: str, **extra: Any) -> tuple[str, str, dict[str, Any]]:
    return (
        pid,
        NOMINATIONS_PATH,
        {"principal_id": principal, "role": role, "reason": "cover", **extra},
    )


def decide(
    pid: str, nomination_id: str, decision: str, **extra: Any
) -> tuple[str, str, dict[str, Any]]:
    path = DECISION_PATH.format(nomination_id=nomination_id)
    return pid, path, {"decision": decision, **extra}


def press(database: str, *posts: tuple[str, str, dict[str, Any]]) -> list[httpx.Response]:
    from tests.fixtures.console_http import headers

    async def go(c: httpx.AsyncClient) -> list[httpx.Response]:
        return [
            await c.post(f"{API}{path}", json=body, headers=headers(pid))
            for pid, path, body in posts
        ]

    answers: list[httpx.Response] = pressed(database, GRANTS, go)
    return answers


def listing(database: str, pid: str) -> httpx.Response:
    from tests.fixtures.console_http import headers

    async def go(c: httpx.AsyncClient) -> httpx.Response:
        return await c.get(f"{API}{NOMINATIONS_PATH}", headers=headers(pid))

    answer: httpx.Response = pressed(database, GRANTS, go)
    return answer


def test_a_third_person_confirms_a_nomination_into_a_role_grant_on_the_ledger(
    database: str,
) -> None:
    """**M33.1.2.3 on PostgreSQL.** `u_wide` nominates `u_narrow` as an Auditor; the nominee is
    offered to `u_admin` to decide and not to `u_elsewhere`, whose grant decision is over another
    department, and the nominator sees it as theirs. The nominator cannot confirm it although
    they hold the grant decision; `u_admin` can, and the role grant is written with `u_admin` as
    `granted_by` and the nomination's reason, the nomination names it, and `0102`'s `grant` entry
    names `u_admin`. A second confirmation is the one refusal.

    Delete this and a nomination can be confirmed by the person who made it, decided by somebody
    whose authority does not reach the nominee, or confirmed without a grant being written."""
    [made] = press(database, nominate("u_wide", "u_narrow", "auditor"))
    assert made.status_code == 201, made.text
    nomination_id = made.json()["id"]

    as_admin = listing(database, "u_admin").json()
    as_nominator = listing(database, "u_wide").json()
    as_elsewhere = listing(database, "u_elsewhere").json()
    assert [one["id"] for one in as_admin["deciding"]] == [nomination_id]
    assert as_admin["deciding"][0]["display_name"] == "Person u_narrow"
    assert (as_nominator["deciding"], [one["id"] for one in as_nominator["mine"]]) == (
        [],
        [nomination_id],
    )
    assert as_elsewhere == {"deciding": [], "mine": []}

    by_nominator, by_elsewhere, by_admin, again = press(
        database,
        decide("u_wide", nomination_id, "confirm"),
        decide("u_elsewhere", nomination_id, "confirm"),
        decide("u_admin", nomination_id, "confirm"),
        decide("u_admin", nomination_id, "confirm"),
    )
    assert (by_nominator.status_code, by_elsewhere.status_code) == (404, 404)
    assert by_admin.status_code == 200, by_admin.text
    assert again.status_code == 404
    assert len({by_nominator.json()["message"], by_elsewhere.json()["message"]}) == 1

    [(outcome, decided_by, grant_id)] = sql(
        database, "SELECT outcome, decided_by, grant_id FROM gate.role_nomination"
    )
    [(granted_id, role, granted_by, reason)] = sql(
        database,
        "SELECT id, role, granted_by, reason FROM gate.role_grant WHERE principal_id = 'u_narrow'",
    )
    assert (outcome, decided_by, grant_id) == ("confirmed", "u_admin", granted_id)
    assert (role, granted_by, reason) == ("auditor", "u_admin", "cover")
    granted = [one for one in entries(database, "grant") if one.subject == "principal:u_narrow"]
    assert [(one.actor_id, one.details["role"]) for one in granted] == [("u_admin", "auditor")]
    # Decided, it is offered to nobody to decide again, and its nominator sees what became of it.
    assert listing(database, "u_admin").json()["deciding"] == []
    assert [one["outcome"] for one in listing(database, "u_wide").json()["mine"]] == ["confirmed"]


def test_a_nominee_who_exists_and_an_id_nobody_holds_are_indistinguishable_to_the_nominator(
    database: str,
) -> None:
    """`A_NOMINATION_SAYS_NOTHING_ABOUT_WHETHER_ITS_NOMINEE_EXISTS`: `u_wide`, who may name
    nobody, nominates a colleague and an id nobody holds, and the two answers and the two rows in
    their own list differ only in the id and the id they named; neither carries a name. `u_admin`,
    who may name people, is shown the colleague's name. Nothing reaches the ledger for either.

    Delete this and nominating an id becomes a way to ask whether a person exists, and what they
    are called, past the People screen's rule."""
    real, ghost = press(
        database,
        nominate("u_wide", "u_narrow", "auditor"),
        nominate("u_wide", "u_nobody_by_this_id", "auditor"),
    )
    assert (real.status_code, ghost.status_code) == (201, 201)
    assert sorted(real.json()) == sorted(ghost.json())
    assert real.json()["change"] == ghost.json()["change"] == "nominated"

    def without_ids(one: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in one.items()
            if key not in ("id", "principal_id", "created_at")
        }

    mine = listing(database, "u_wide").json()["mine"]
    assert [one["principal_id"] for one in mine] == ["u_nobody_by_this_id", "u_narrow"]
    assert without_ids(mine[0]) == without_ids(mine[1])
    assert {one["display_name"] for one in mine} == {None}
    named = {
        one["principal_id"]: one["display_name"]
        for one in listing(database, "u_admin").json()["deciding"]
    }
    assert named == {"u_narrow": "Person u_narrow", "u_nobody_by_this_id": None}
    assert entries(database, "grant") == []
    assert "People screen" in A_NOMINATION_SAYS_NOTHING_ABOUT_WHETHER_ITS_NOMINEE_EXISTS


def test_a_nominee_in_the_deciders_department_is_theirs_to_decide_and_a_decline_writes_no_grant(
    database: str,
) -> None:
    """The positive half of the scoped decider: `u_elsewhere` decides a nominee in their own
    department, and declines it, which writes the decision and no grant, where `u_prefix`, who sees
    the screen and holds no grant decision, is refused, and nobody confirms it afterwards. Delete
    this and the scope test above is satisfied by a decider nobody can ever be, anybody on the
    screen can decline, or a declined nomination is confirmed later."""
    [made] = press(database, nominate("u_wide", "u_web", "auditor"))
    nomination_id = made.json()["id"]
    assert [one["id"] for one in listing(database, "u_elsewhere").json()["deciding"]] == [
        nomination_id
    ]

    refused, declined, confirmed_after = press(
        database,
        decide("u_prefix", nomination_id, "decline"),
        decide("u_elsewhere", nomination_id, "decline"),
        decide("u_admin", nomination_id, "confirm"),
    )

    assert refused.status_code == 404
    assert declined.status_code == 200, declined.text
    # Declined is decided: nobody confirms it afterwards, and the refusal is the one 404.
    assert confirmed_after.status_code == 404
    assert sql(database, "SELECT outcome, decided_by, grant_id FROM gate.role_nomination") == [
        ("declined", "u_elsewhere", None)
    ]
    assert sql(database, "SELECT count(*) FROM gate.role_grant WHERE principal_id = 'u_web'") == [
        (0,)
    ]


def test_a_confirmation_crossing_the_separation_of_duties_needs_its_acknowledgement(
    database: str,
) -> None:
    """The appointment's sentence, said to a confirmer: `u_narrow` already holds Connector Admin,
    so confirming them as Super Admin is refused in the separation's words until the confirmer
    acknowledges it, and then written with the acknowledgement. Delete this and a nomination is a
    way around the separation the appointment route keeps."""
    sql(
        database,
        "INSERT INTO gate.role_grant (principal_id, role, granted_by, reason)"
        " VALUES ('u_narrow', 'connector_admin', 'u_admin', 'r')",
    )
    [made] = press(database, nominate("u_wide", "u_narrow", "super_admin"))
    nomination_id = made.json()["id"]

    bare, acknowledged = press(
        database,
        decide("u_admin", nomination_id, "confirm"),
        decide("u_admin", nomination_id, "confirm", acknowledgement="a company of two"),
    )

    assert bare.status_code == 404
    assert SEPARATION_OF_DUTIES_WARNING in bare.json()["message"]
    assert acknowledged.status_code == 200, acknowledged.text
    assert sql(
        database,
        "SELECT acknowledgement FROM gate.role_grant"
        " WHERE principal_id = 'u_narrow' AND role = 'super_admin'",
    ) == [("a company of two",)]


def test_nobody_nominates_themselves_and_nobody_off_the_roles_screen_nominates_at_all(
    database: str,
) -> None:
    """A person proposing themselves is told so and nothing is written; a person the Roles screen
    does not open for gets the one refusal, as does a person the screen opens for who may decide
    nothing and asks to. Delete this and a nomination is a way to propose oneself, or a queue
    anybody signed in can write into."""
    own, outside, missing = press(
        database,
        nominate("u_wide", "u_wide", "auditor"),
        nominate("u_none", "u_narrow", "auditor"),
        decide("u_prefix", str(uuid.uuid4()), "confirm"),
    )
    assert own.status_code == 404
    assert A_PERSON_IS_PROPOSED_BY_SOMEBODY_ELSE in own.json()["message"]
    assert (outside.status_code, missing.status_code) == (404, 404)
    assert listing(database, "u_none").status_code == 404
    assert sql(database, "SELECT count(*) FROM gate.role_nomination") == [(0,)]


def as_app(url: str, principal: str, statement: str, *params: object) -> None:
    with psycopg.connect(url, autocommit=False) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute("SELECT set_config('app.principal_id', %s, true)", (principal,))
        conn.execute(statement, params)
        conn.commit()


def test_the_table_holds_the_two_person_rule_against_a_row_written_by_hand(database: str) -> None:
    """For a row that arrives some other way than the route: a self-nomination, a nomination in
    another person's name, and a decision by the nominator are each refused by the database, and
    a decision by a third person is admitted. Delete this and a hand-written statement passes a
    gate one person passes alone."""
    insert = (
        "INSERT INTO gate.role_nomination (principal_id, role, nominated_by, reason)"
        " VALUES (%s, 'auditor', %s, 'r')"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        as_app(database, "u_wide", insert, "u_wide", "u_wide")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_app(database, "u_wide", insert, "u_narrow", "u_admin")
    as_app(database, "u_wide", insert, "u_narrow", "u_wide")
    decline = (
        "UPDATE gate.role_nomination SET outcome = 'declined', decided_by = %s,"
        " decided_at = statement_timestamp()"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        as_app(database, "u_wide", decline, "u_wide")
    as_app(database, "u_admin", decline, "u_admin")
    assert sql(database, "SELECT outcome, decided_by FROM gate.role_nomination") == [
        ("declined", "u_admin")
    ]
