"""A work email added on a person's page, and the join it makes with the staff list's person.

The decision is tested without a database; the route is driven over HTTP against a real PostgreSQL
at head as the application role, where the bindings, the disable, the retirement and the ledger
entries their triggers write can be read back. Without `DATABASE_URL` and pgvector those skip.

Task ids: M1.10.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import DEFAULT_TRUST, Roster, StaffRecord
from brain.identity.work_email import (
    TOLD,
    Holder,
    Joining,
    WorkEmailError,
    decide,
    work_address,
)
from brain.install import hold_saved
from brain.ops.staff_people_run import provide_people
from tests.fixtures.console_http import headers
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_directory_routes import GRANTS
from tests.unit.test_review_store import entries

NOW = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)
DIRECTORY = "/api/v1/govern/directory"
ADDRESS = "ada@example.test"


def holder(*, signs_in: bool = False, signed_in: bool = False, holds_own: bool = False) -> Holder:
    return Holder(
        principal_id="u_list", signs_in=signs_in, signed_in=signed_in, holds_own=holds_own
    )


# ------------------------------------------------------------------ the decision, no database


def test_an_address_nobody_holds_is_bound_and_one_the_list_made_nothing_for_is_joined() -> None:
    """The two outcomes that write. Delete this and adding a work email can stop binding, or stop
    joining the duplicate the owner asked to be rid of."""
    assert decide(has_email=False, holder=None, confirmed=False) is Joining.BOUND
    assert decide(has_email=False, holder=holder(), confirmed=False) is Joining.JOINED


@pytest.mark.parametrize(
    "found",
    [holder(signed_in=True), holder(holds_own=True), holder(signed_in=True, holds_own=True)],
)
def test_a_list_person_who_has_signed_in_or_holds_something_is_joined_only_once_confirmed(
    found: Holder,
) -> None:
    """Delete this and a join retires somebody an administrator granted something, or somebody who
    has used the Brain, without anybody being asked."""
    assert decide(has_email=False, holder=found, confirmed=False) is Joining.ASK
    assert decide(has_email=False, holder=found, confirmed=True) is Joining.JOINED


def test_a_list_person_who_signs_in_is_never_joined_and_a_person_with_an_email_gets_no_second() -> (
    None
):
    """Delete this and a join retires the one way in a person uses, or a person gets two work
    emails and the list two people to follow."""
    signs = holder(signs_in=True)
    assert decide(has_email=False, holder=signs, confirmed=True) is Joining.SIGNS_IN_ELSEWHERE
    assert decide(has_email=True, holder=None, confirmed=True) is Joining.ALREADY
    assert decide(has_email=True, holder=holder(), confirmed=True) is Joining.ALREADY


def test_an_address_is_trimmed_and_one_no_mailbox_could_have_is_refused() -> None:
    """Delete this and a typo binds a digest nothing on the list will ever match."""
    assert work_address("  ada@example.test ") == ADDRESS
    for typed in (
        "ada",
        "ada@",
        "@example.test",
        "ada@example",
        "a da@example.test",
        "x" * 250 + "@a.bc",
    ):
        with pytest.raises(WorkEmailError):
            work_address(typed)


# ------------------------------------------------------------------ over HTTP, on PostgreSQL


@pytest.fixture
def url() -> Iterator[str]:
    before = hold_saved(
        {"INSTALL_STAFF_SOURCE": "lark", "INSTALL_STAFF_SOURCE_LOCATION": "larksuite.com"}
    )
    try:
        with at_head("brain_test_work_email") as scratch:
            yield scratch
    finally:
        hold_saved(before)


def by_hand(url: str, pid: str = "u_first", department: str | None = None) -> str:
    """A person made by hand before the list, as the first administrator is: no email at all."""
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES (%s, 'human', 'staff', 'Ada Lovelace', %s)",
        pid,
        department,
    )
    return pid


def listed(url: str) -> str:
    """The staff list's own person for the address, made by the people step."""
    roster = Roster(
        source="lark",
        complete=True,
        asserts=DEFAULT_TRUST["lark"],
        people=(StaffRecord(ADDRESS, "Ada Lovelace"),),
    )

    async def make() -> None:
        from brain.session import make_app_engine, make_session_factory

        engine = make_app_engine(url)
        try:
            await provide_people(make_session_factory(engine), roster, now=NOW)
        finally:
            await engine.dispose()

    run(make)
    [(pid,)] = sql(
        url,
        "SELECT principal_id FROM auth.principal_identity WHERE channel = 'email'"
        " AND identity_hash = %s AND deleted_at IS NULL",
        digest_of(ADDRESS),
    )
    return str(pid)


def add(url: str, pid: str, reader: str = "u_admin", **body: Any) -> tuple[int, dict[str, Any]]:
    async def press(client: httpx.AsyncClient) -> tuple[int, dict[str, Any]]:
        answer = await client.post(
            f"{DIRECTORY}/{pid}/work-email",
            json={"address": ADDRESS, **body},
            headers=headers(reader),
        )
        return answer.status_code, answer.json()

    return pressed(url, GRANTS, press)


def email_holder(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT principal_id, assurance FROM auth.principal_identity WHERE channel = 'email'"
        " AND identity_hash = %s AND deleted_at IS NULL",
        digest_of(ADDRESS),
    )


def state(url: str, pid: str) -> tuple[bool, bool]:
    [(disabled, retired)] = sql(
        url,
        "SELECT disabled_at IS NOT NULL, deleted_at IS NOT NULL FROM auth.principal WHERE id = %s",
        pid,
    )
    return bool(disabled), bool(retired)


def test_an_address_nobody_holds_is_bound_to_the_person_and_the_ledger_names_who_did_it(
    url: str,
) -> None:
    """Delete this and the action can bind nothing, bind at an assurance that admits a verb, or
    leave no entry saying who bound whose address."""
    first = by_hand(url)
    before = len(entries(url, "channel_binding"))

    status, said = add(url, first)

    assert status == 200, said
    assert (said["outcome"], said["written"], said["told"]) == ("bound", True, TOLD[Joining.BOUND])
    assert email_holder(url) == [(first, int(Assurance.UNVERIFIED))]
    [entry] = entries(url, "channel_binding")[before:]
    assert (entry.actor_id, entry.subject, dict(entry.details)) == (
        "u_admin",
        f"principal:{first}",
        {"change": "bound", "channel": Channel.EMAIL.value},
    )


def test_the_list_person_who_holds_nothing_is_joined_retired_and_recorded(url: str) -> None:
    """The owner's duplicate. Delete this and typing his work email leaves two of him on People,
    or retires the list's person without the ledger saying so."""
    first, made = by_hand(url), listed(url)
    bindings, states = len(entries(url, "channel_binding")), len(entries(url, "principal_state"))

    status, said = add(url, first)

    assert status == 200, said
    assert (said["outcome"], said["written"]) == ("joined", True)
    assert email_holder(url) == [(first, int(Assurance.UNVERIFIED))]
    assert state(url, made) == (True, True)
    assert state(url, first) == (False, False)
    moved = [
        (one.actor_id, one.subject, one.details["change"])
        for one in entries(url, "channel_binding")[bindings:]
    ]
    assert moved == [
        ("u_admin", f"principal:{made}", "unbound"),
        ("u_admin", f"principal:{first}", "bound"),
    ]
    [disabled] = entries(url, "principal_state")[states:]
    assert (disabled.actor_id, disabled.subject, dict(disabled.details)) == (
        "u_admin",
        f"principal:{made}",
        {"change": "disabled"},
    )
    listed_ids = [
        row[0] for row in sql(url, "SELECT id FROM auth.principal WHERE deleted_at IS NULL")
    ]
    assert made not in listed_ids


def test_a_starter_pack_the_sync_gave_the_list_person_does_not_stop_the_join(url: str) -> None:
    """Grants the sync itself wrote count as nothing, because the sync writes them again for the
    joined person. Delete this and every list person with a Starter pack waits for a human."""
    first, made = by_hand(url), listed(url)
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason)"
        " VALUES (%s, 'read:ticket', '{}'::jsonb, 'roster.lark', 'starter pack')",
        made,
    )

    status, said = add(url, first)

    assert (status, said["outcome"]) == (200, "joined")


def test_a_list_person_somebody_granted_something_is_joined_only_after_the_page_asks(
    url: str,
) -> None:
    """Delete this and a join takes away a grant an administrator gave, with nobody asked."""
    first, made = by_hand(url), listed(url)
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason)"
        " VALUES (%s, 'read:ticket', '{}'::jsonb, 'u_admin', 'needed')",
        made,
    )

    asked_status, asked = add(url, first)
    unchanged = email_holder(url)
    confirmed_status, confirmed = add(url, first, confirm=True)

    assert (asked_status, asked["outcome"], asked["written"]) == (200, "ask", False)
    assert asked["told"] == TOLD[Joining.ASK]
    assert unchanged == [(made, int(Assurance.UNVERIFIED))]
    assert (confirmed_status, confirmed["outcome"]) == (200, "joined")
    assert email_holder(url) == [(first, int(Assurance.UNVERIFIED))]


def test_a_list_person_who_signs_in_is_not_joined_even_when_confirmed(url: str) -> None:
    """Delete this and a join retires the account somebody signs in with."""
    first, made = by_hand(url), listed(url)

    async def bind() -> None:
        from brain.identity.sign_in_binding import SignInBindings
        from brain.session import make_app_engine, make_session_factory

        engine = make_app_engine(url)
        try:
            await SignInBindings(
                make_session_factory(engine), "https://sign-in.example.test/realms/brain"
            ).bind("kc-ada", principal_id=made, bound_by="u_seed", now=NOW)
        finally:
            await engine.dispose()

    run(bind)

    status, said = add(url, first, confirm=True)

    assert (status, said["outcome"], said["written"]) == (200, "signs_in_elsewhere", False)
    assert email_holder(url) == [(made, int(Assurance.UNVERIFIED))]
    assert state(url, made) == (False, False)


def test_a_person_who_has_a_work_email_is_given_no_second(url: str) -> None:
    """Delete this and one person holds two addresses, so the list makes nobody for either."""
    made = listed(url)

    status, said = add(url, made)

    assert (status, said["outcome"], said["written"]) == (200, "already", False)


@pytest.mark.parametrize("reader", ["u_wide", "u_elsewhere", "u_none"])
def test_a_reader_without_the_granting_authority_over_both_people_changes_nothing(
    url: str, reader: str
) -> None:
    """`u_wide` reads People and grants nothing; `u_elsewhere` grants in maintenance only, while
    the hand-made person sits in maintenance and the list's person nowhere. Each is told what a
    missing person is told. Delete this and a reader who could not grant either person anything
    could retire one of them, or learn that an address is somebody's."""
    first = by_hand(url, department="maintenance")
    made = listed(url)

    status, _ = add(url, first, reader=reader)

    assert status == 404
    assert email_holder(url) == [(made, int(Assurance.UNVERIFIED))]
    assert state(url, made) == (False, False)


def test_an_address_no_mailbox_could_have_is_refused_before_anything(url: str) -> None:
    """Delete this and a typo binds a digest the list will never match."""
    first = by_hand(url)

    async def press(client: httpx.AsyncClient) -> int:
        answer = await client.post(
            f"{DIRECTORY}/{first}/work-email", json={"address": "ada"}, headers=headers("u_admin")
        )
        return answer.status_code

    assert pressed(url, GRANTS, press) == 422
    assert email_holder(url) == []


def test_the_page_offers_the_action_for_a_person_the_list_does_not_name_and_not_for_one_it_does(
    url: str,
) -> None:
    """Delete this and the owner has no button to press on his own page, or one on every page."""
    first, made = by_hand(url), listed(url)
    sql(
        url,
        "INSERT INTO auth.staff_member (source, address_hash, display_name, status,"
        " first_listed_at, last_listed_at) VALUES ('lark', %s, 'Ada Lovelace', 'active', %s, %s)",
        digest_of(ADDRESS),
        NOW,
        NOW,
    )

    async def read(client: httpx.AsyncClient) -> tuple[Any, Any]:
        mine = await client.get(f"{DIRECTORY}/{first}", headers=headers("u_admin"))
        theirs = await client.get(f"{DIRECTORY}/{made}", headers=headers("u_admin"))
        return mine.json(), theirs.json()

    mine, theirs = pressed(url, GRANTS, read)

    assert mine["may_add_work_email"] is True
    assert theirs["may_add_work_email"] is False
