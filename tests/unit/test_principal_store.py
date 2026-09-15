"""A live principal is read from `auth.principal` as the application role; a disabled, deleted or
unreadable one is absent; and an ended engagement is returned for the caller to judge at its own
instant.

The first half reads rows into principals and needs no server. The second builds `0002` and
`0003` as `tests.unit.test_entitlement_store` does and drives
`brain.identity.principal_store.StoredPrincipals` as the application role, including through
`brain.ops.automation_owner.owner_of`, which is the reader it was written for. It skips when there
is no server.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from sqlalchemy import text
from structlog.testing import capture_logs

from brain.core.principal import Employment, Principal, PrincipalKind
from brain.identity.principal_store import (
    PRINCIPAL_SETTING,
    PrincipalStoreError,
    StoredPrincipals,
    principal_from,
)
from brain.ops.automation_owner import AutomationRefusal, AutomationRefusedError, owner_of
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine, registered
from tests.unit.test_entitlement_store import LONG_AGO, NOW, a_principal, resolver

#: When the contractor's engagement ends: after `LONG_AGO` and before `NOW`.
ENDS = datetime(2500, 1, 1, tzinfo=UTC)


def row(**changed: Any) -> dict[str, Any]:
    """A live contractor's row, as `StoredPrincipals` selects it."""
    return {
        "id": "u_owner",
        "kind": "human",
        "employment": "contractor",
        "display_name": "Person u_owner",
        "primary_department": "finance",
        "not_after": ENDS,
        "disabled_at": None,
        "deleted_at": None,
        **changed,
    }


# --------------------------------------------------------------------------- the row


def test_a_live_row_is_the_principal_it_records() -> None:
    """The positive case for every absence below. Delete it and a reader returning None for every
    row passes them, and no automation ever runs."""
    assert principal_from(row()) == Principal(
        id="u_owner",
        kind=PrincipalKind.HUMAN,
        employment=Employment.CONTRACTOR,
        display_name="Person u_owner",
        primary_department="finance",
        not_after=ENDS,
    )


def test_a_disabled_row_is_no_principal() -> None:
    """The policy on `auth.principal` hides a deleted row and not a disabled one. Delete this and a
    disabled owner's automation runs on, because a disabled principal comes back as a real one."""
    assert principal_from(row(disabled_at=LONG_AGO)) is None


def test_a_deleted_row_is_no_principal_whatever_the_connection_role() -> None:
    """Refused by the reader as well as hidden by the policy, because a connection that is not the
    application role bypasses the policy. Delete this and an offboarded owner is a live principal
    to any process wired with the wrong role."""
    assert principal_from(row(deleted_at=LONG_AGO)) is None


def test_an_ended_engagement_is_returned_for_the_caller_to_judge() -> None:
    """The store does not decide an expiry. Delete this and a filter on the date can creep in,
    judged at the database's clock rather than the call's, and an ended engagement becomes
    indistinguishable from a deletion."""
    found = principal_from(row(not_after=LONG_AGO))

    assert found is not None
    assert found.not_after == LONG_AGO
    assert not found.is_active(NOW)


@pytest.mark.parametrize(
    "changed",
    [{"kind": "robot"}, {"not_after": None}],
    ids=["unknown_kind", "unbounded_contractor"],
)
def test_a_row_that_does_not_construct_raises_rather_than_becoming_a_principal(
    changed: dict[str, Any],
) -> None:
    """A row arriving some other way than through `Principal` is refused as this store's error.
    Delete this and a contractor with no end date can be read back as a principal, which is the
    rot `Principal.model_post_init` exists to prevent."""
    with pytest.raises(PrincipalStoreError, match="u_owner"):
        principal_from(row(**changed))


# ---------------------------------------------------------------------- the database


def with_records[T](url: str, work: Callable[[StoredPrincipals], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredPrincipals(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def live(url: str, principal_id: str) -> Principal | None:
    return with_records(url, lambda records: records.live_principal(principal_id))


def test_the_store_connects_as_the_application_role() -> None:
    """Delete this and every test below can pass on a superuser connection that bypasses the
    policy on `auth.principal`."""
    with resolver("brain_ps_role") as url:

        async def work(records: StoredPrincipals) -> str:
            async with records.sessions() as session:
                return str((await session.execute(text("SELECT current_user"))).scalar_one())

        assert with_records(url, work) == "brain_app"


def test_a_live_principal_is_read_back_whole() -> None:
    """The positive case for the absences below, through the store. Delete it and a store that
    finds nobody passes every one of them."""
    with resolver("brain_ps_live") as url:
        a_principal(url, "u_owner", employment="contractor", not_after=ENDS)
        found = live(url, "u_owner")

    assert found == principal_from(row())


def test_a_disabled_a_deleted_and_an_unknown_principal_are_all_absent() -> None:
    """Three ways of not being here, one answer. Delete this and a disabled owner, whom the policy
    does not hide, can be read as live."""
    with resolver("brain_ps_absent") as url:
        a_principal(url, "u_disabled")
        a_principal(url, "u_deleted")
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", "u_disabled")
        sql(url, "UPDATE auth.principal SET deleted_at = now() WHERE id = %s", "u_deleted")
        found = [live(url, one) for one in ("u_disabled", "u_deleted", "u_stranger")]

    assert found == [None, None, None]


def test_a_row_that_does_not_construct_is_absent_and_logged_rather_than_raised() -> None:
    """One unreadable principal is an owner whose automation stops, and nothing else. Delete this
    and the refusal can raise out of the store, which turns one bad row into a fault on every call
    that reads it and says nothing in the log about which row."""
    with resolver("brain_ps_unreadable") as url:
        [(kind_check,)] = sql(
            url,
            "SELECT conname FROM pg_constraint WHERE conrelid = 'auth.principal'::regclass"
            " AND pg_get_constraintdef(oid) LIKE '%(kind)%'",
        )
        sql(url, f'ALTER TABLE auth.principal DROP CONSTRAINT "{kind_check}"')
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name)"
            " VALUES ('u_robot', 'robot', 'staff', 'Not a person')",
        )
        with capture_logs() as logs:
            found = live(url, "u_robot")

    assert found is None
    refused = [one.get("principal") for one in logs if one["event"] == "principal.record_refused"]
    assert refused == ["u_robot"]


#: `0002`'s principal policy, narrowed to the principal the transaction names.
NARROWED_TO_THE_PRINCIPAL: tuple[str, ...] = (
    "DROP POLICY principal_live ON auth.principal",
    "CREATE POLICY principal_live ON auth.principal FOR ALL TO brain_app"
    " USING (deleted_at IS NULL AND id = current_setting('app.principal_id', true))"
    " WITH CHECK (true)",
)


def test_the_store_still_reads_under_a_policy_that_narrows_to_the_principal_named() -> None:
    """The transaction is told whose record it is reading. Delete this and that setting can go with
    every other test green, and the first policy to read it stops every automation in the company.
    The second connection proves the replacement narrows at all."""
    with resolver("brain_ps_narrowed") as url:
        a_principal(url, "u_owner", employment="contractor", not_after=ENDS)
        for statement in NARROWED_TO_THE_PRINCIPAL:
            sql(url, statement)
        found = live(url, "u_owner")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config(%s, %s, false)", (PRINCIPAL_SETTING, "u_somebody"))
            seen = conn.execute("SELECT count(*) FROM auth.principal").fetchone()

    assert found == principal_from(row())
    assert seen == (0,)


def test_an_owner_disabled_in_the_database_stops_their_automation_on_the_next_call() -> None:
    """Item 56 through the real record: the automation stops at the moment its owner is disabled,
    because the owner is read on every call. Delete this and `owner_of` is only ever proved over a
    dictionary, and a store that cached or ignored `disabled_at` would pass."""
    registration = registered("nightly", owner="u_owner")
    with resolver("brain_ps_disabled_owner") as url:
        a_principal(url, "u_owner")

        async def call(records: StoredPrincipals) -> Principal:
            return await owner_of(registration, principals=records, now=NOW)

        running = with_records(url, call)
        sql(url, "UPDATE auth.principal SET disabled_at = now() WHERE id = %s", "u_owner")
        with pytest.raises(AutomationRefusedError) as refused:
            with_records(url, call)

    assert running.id == "u_owner"
    assert refused.value.reason is AutomationRefusal.OWNER_GONE


def test_an_owner_whose_engagement_ended_is_judged_at_the_calls_instant() -> None:
    """Expiry is the caller's, with the caller's now. Delete this and the store could drop an ended
    engagement at the database's clock, and a call judged at any other instant would be refused or
    admitted by a date nobody passed."""
    registration = registered("nightly", owner="u_owner")
    with resolver("brain_ps_ended_owner") as url:
        a_principal(url, "u_owner", employment="contractor", not_after=ENDS)

        def call_at(now: datetime) -> Callable[[StoredPrincipals], Awaitable[Principal]]:
            return lambda records: owner_of(registration, principals=records, now=now)

        before = with_records(url, call_at(LONG_AGO))
        with pytest.raises(AutomationRefusedError) as refused:
            with_records(url, call_at(NOW))

    assert before.id == "u_owner"
    assert refused.value.reason is AutomationRefusal.OWNER_GONE
