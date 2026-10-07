"""Where departments come from, and a person moved on People is on the ledger.

The setting's reading and the roster the Starter pack step reads under the console, with no
database; then `0170`'s trigger against a real PostgreSQL at head, held to the shape the recorder
writes for the same change. CI sets `DATABASE_URL` and has pgvector; without either the database
half skips.

Task ids: M1.6.19, M1.6.20, M1.6.21
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder, OrganisationChange
from brain.console.configuration import setting_problem
from brain.identity.departments_from import (
    DEPARTMENTS_FROM_SETTING,
    DepartmentsFrom,
    as_the_console_places_them,
    departments_from,
    the_list_places_people,
)
from brain.identity.organisation_store import moving_people
from brain.identity.staff_source import DEFAULT_TRUST, Roster, StaffRecord
from brain.install import BY_NAME
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_entitlement_store import a_principal


@pytest.mark.parametrize(
    ("given", "read"),
    [
        ("console", DepartmentsFrom.CONSOLE),
        (" Console ", DepartmentsFrom.CONSOLE),
        ("staff_source", DepartmentsFrom.STAFF_SOURCE),
        ("", DepartmentsFrom.STAFF_SOURCE),
        ("consle", DepartmentsFrom.STAFF_SOURCE),
    ],
)
def test_the_setting_reads_its_two_words_and_anything_else_as_the_staff_list(
    given: str, read: DepartmentsFrom
) -> None:
    """Delete this and a slip in an environment file can switch a company to managing departments
    by hand, or `console` can stop meaning it."""
    assert departments_from({DEPARTMENTS_FROM_SETTING: given}, saved={}) is read


@pytest.mark.parametrize(
    ("given", "places"),
    [("console", False), ("staff_source", True), ("", True), ("consle", True)],
)
def test_the_sync_places_the_people_it_makes_only_where_departments_come_from_the_list(
    given: str, places: bool
) -> None:
    """The one question the people step and the accounts step both ask, and the one the install
    check asks of the product: false only for the console, true for the list and for any word
    that is neither. Delete this and the sync can place people on an install managing departments
    on People, or stop placing them on every other.

    Task ids: M1.6.19"""
    assert the_list_places_people({DEPARTMENTS_FROM_SETTING: given}, saved={}) is places


def test_the_setting_defaults_to_the_staff_list_and_settings_refuses_a_third_word() -> None:
    """Every install before this setting kept the list's departments; a word that is neither is
    refused on Settings before it is saved. Delete this and the default can change under every
    install on upgrade, or Settings can save a word the sync reads as the staff list."""
    assert BY_NAME[DEPARTMENTS_FROM_SETTING].default == "staff_source"
    assert setting_problem(DEPARTMENTS_FROM_SETTING, "console") == ""
    assert setting_problem(DEPARTMENTS_FROM_SETTING, "staff_source") == ""
    assert setting_problem(DEPARTMENTS_FROM_SETTING, "both") != ""


def test_under_the_console_the_roster_carries_the_department_people_set_and_no_team_or_lead() -> (
    None
):
    """What the Starter pack step reads: the department People put each person in, nobody in a team
    and nobody leading. Delete this and a pack follows the list's department, or the list's lead
    flag reaches a step that must not read it."""
    roster = Roster(
        source="lark",
        complete=True,
        asserts=DEFAULT_TRUST["lark"],
        people=(
            StaffRecord("Ada@example.test", "Ada", department="Web", teams=("design",), leads=True),
            StaffRecord("bo@example.test", "Bo", department="Sales"),
        ),
    )
    placed = as_the_console_places_them(roster, {"ada@example.test": "finance"})

    assert [(one.department, one.teams, one.leads) for one in placed.people] == [
        ("finance", (), False),
        ("", (), False),
    ]
    assert (placed.source, placed.complete, placed.asserts) == (
        roster.source,
        roster.complete,
        roster.asserts,
    )


# ------------------------------------------------------------------ the ledger, 0170
@pytest.fixture
def url() -> Iterator[str]:
    with at_head("brain_test_departments_from") as scratch:
        yield scratch


def moved_entries(url: str, pid: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (str(actor), dict(details))
        for actor, details in sql(
            url,
            "SELECT actor_id, details FROM obs.audit_entry WHERE action = 'organisation'"
            " AND subject = %s ORDER BY seq",
            f"principal:{pid}",
        )
    ]


def move(url: str, pid: str, department: str, *, actor: str | None) -> None:
    statement = moving_people([pid], department).compile(compile_kwargs={"literal_binds": True})
    prefix = "" if actor is None else f"SELECT set_config('brain.actor_id', '{actor}', true); "
    sql(url, f"BEGIN; {prefix}{statement}; COMMIT")


def test_a_person_moved_is_recorded_under_whoever_moved_them_in_the_recorder_s_own_shape(
    url: str,
) -> None:
    """0170's trigger writes `organisation` `moved` naming the new department's slug under the
    actor, a move to where somebody already is writes nothing, and an unattributed move says so.
    The details are exactly what `AuditRecorder.organisation` writes for `MOVED`. Delete this and
    moves can go unrecorded, or be recorded in a shape the readable export cannot read."""
    a_principal(url, "u_ada")
    move(url, "u_ada", "sales", actor="u_admin")
    move(url, "u_ada", "sales", actor="u_admin")
    move(url, "u_ada", "web", actor=None)

    recorded = AuditRecorder(
        AuditChain(),
        actor_id="u_admin",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: datetime(2999, 3, 1, tzinfo=UTC),
    ).organisation(change=OrganisationChange.MOVED, principal_id="u_ada", department="sales")
    assert moved_entries(url, "u_ada") == [
        ("u_admin", dict(recorded.details)),
        ("unattributed", {"change": "moved", "department": "web", "actor": "unattributed"}),
    ]
