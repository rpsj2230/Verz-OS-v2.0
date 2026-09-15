"""An automation's registration is kept once, read only as that automation or its owner, refused
when it does not construct, and adopted once, in the adopter's name, only when its owner has gone.

Builds `gate.automation_owner` through `0044` and drives it as the application role, through
`brain.ops.automation_owner_store.StoredAutomations` itself; it skips when there is no server, as
every file using `tests.fixtures.scratch_postgres` does. The first test proves the store's
connection is the application role, because a superuser connection bypasses every policy here.

Task ids: none
"""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.db import normalise_database_url
from brain.ops.automation_owner import Registration, RegistrationError, register
from brain.ops.automation_owner_store import StoredAutomations
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import (
    ROOT,
    drop,
    fresh,
    migrate,
    modelled,
    present,
    run,
    secured,
    shape,
    sql,
)

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
TABLES: tuple[str, ...] = ("gate.automation_owner",)
MIGRATION = ROOT / "migrations" / "versions" / "0044_automation_owner.py"


def person(pid: str, *, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {pid}",
        not_after=not_after,
    )


def registered(automation_id: str, owner: str = "u_owner") -> Registration:
    """A registration whose ceiling has a scope with a clause, so a round trip proves scopes."""
    web_only = Scope(clauses=(Clause(field="sku", op=Op.PREFIX, value="WEB-"),))
    return register(
        automation_id=automation_id,
        owner=person(owner),
        declared_tools=frozenset({"local.read_price_list", "local.search_documents"}),
        ceiling=EntitlementSet(
            principal_id=automation_id,
            grants=(Grant(capability=Capability(value="read:price_list"), scope=web_only),),
        ),
        now=NOW,
    ).registration


class Records:
    """A `PrincipalRecords` over the live principals given."""

    def __init__(self, *live: Principal) -> None:
        self.live = {one.id: one for one in live}

    async def live_principal(self, principal_id: str) -> Principal | None:
        return self.live.get(principal_id)


def predecessor() -> str:
    """The revision `0044` names as the one before it, read off the migration."""
    spec = importlib.util.spec_from_file_location("migration_0044_predecessor", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.down_revision)


@contextmanager
def automations(database: str) -> Iterator[str]:
    """A fresh database holding `gate.automation_owner`, built by `0044` itself."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", predecessor())
        migrate(database, "upgrade", "0044")
        yield scratch
    finally:
        drop(database)


def app_engine(url: str) -> AsyncEngine:
    """An engine whose every connection is the application role, so the policies apply."""
    return create_async_engine(
        normalise_database_url(url),
        poolclass=NullPool,
        connect_args={"options": "-c role=brain_app"},
    )


def with_store[T](url: str, work: Callable[[StoredAutomations], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredAutomations(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def as_app(url: str, *settings: tuple[str, str]) -> psycopg.Connection[Any]:
    """A connection as the application role with these settings, for a statement the store
    would never send."""
    conn = psycopg.connect(url, autocommit=True)
    conn.execute("SET ROLE brain_app")
    for name, value in settings:
        conn.execute("SELECT set_config(%s, %s, false)", (name, value))
    return conn


def test_the_store_connects_as_the_application_role() -> None:
    """Delete this and every policy test below can pass on a superuser connection that bypasses
    row-level security entirely."""
    with automations("brain_au_role") as url:

        async def work(store: StoredAutomations) -> tuple[Any, ...]:
            async with store.sessions() as session:
                return tuple((await session.execute(text("SELECT current_user"))).one())

        assert with_store(url, work) == ("brain_app",)


def test_a_registration_reads_back_as_the_registration_that_was_put() -> None:
    """Ceiling scopes and all. Delete this and a ceiling that loses its clause on the way through
    JSON widens every automation to the owner's whole reach."""
    with automations("brain_au_round_trip") as url:
        put = registered("nightly")

        async def work(store: StoredAutomations) -> Registration | None:
            await store.put(put)
            return await store.registration("nightly")

        assert with_store(url, work) == put


def test_a_transaction_told_one_automation_reads_that_one_and_no_other() -> None:
    """`THE_DATABASE_IS_TOLD_WHICH_AUTOMATION_IS_CALLING`. Delete this and a lookup that forgot
    its WHERE clause hands every automation's ceiling to a caller holding one credential."""
    with automations("brain_au_one_row") as url:

        async def work(store: StoredAutomations) -> None:
            await store.put(registered("mine", owner="u_a"))
            await store.put(registered("theirs", owner="u_b"))

        with_store(url, work)
        with as_app(url, ("app.automation_id", "mine")) as conn:
            told = conn.execute("SELECT automation_id FROM gate.automation_owner").fetchall()
        with as_app(url) as conn:
            untold = conn.execute("SELECT automation_id FROM gate.automation_owner").fetchall()
        with as_app(url, ("app.principal_id", "u_b")) as conn:
            owned = conn.execute("SELECT automation_id FROM gate.automation_owner").fetchall()

    assert told == [("mine",)]
    assert untold == []
    assert owned == [("theirs",)]


def test_an_automation_is_registered_only_in_the_sessions_own_name() -> None:
    """Delete this and a session can register an automation that runs as somebody else."""
    with automations("brain_au_insert") as url:
        values = registered("nightly", owner="u_victim")
        with (
            as_app(url, ("app.principal_id", "u_mallory")) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(
                "INSERT INTO gate.automation_owner "
                "(automation_id, owner_principal_id, credential_digest, declared_tools, ceiling) "
                "VALUES (%s, %s, %s, %s, '[]'::jsonb)",
                ("nightly", "u_victim", values.credential_digest, ["local.read_price_list"]),
            )


def test_a_row_that_does_not_construct_is_absent_rather_than_served() -> None:
    """A ceiling edited into something `Grant` refuses is refused on read. Delete this and the
    edited ceiling is served, or the route faults for one bad row."""
    with automations("brain_au_corrupt") as url:

        async def put(store: StoredAutomations) -> None:
            await store.put(registered("nightly"))

        with_store(url, put)
        sql(
            url,
            'UPDATE gate.automation_owner SET ceiling = \'[{"capability": "nonsense"}]\'::jsonb',
        )

        async def read(store: StoredAutomations) -> Registration | None:
            return await store.registration("nightly")

        assert with_store(url, read) is None


def test_an_automation_whose_owner_has_gone_is_adopted_in_the_adopters_name() -> None:
    """The positive case for both adoption refusals. Delete this and a store that refuses every
    adoption passes them."""
    with automations("brain_au_adopt") as url:

        async def work(store: StoredAutomations) -> tuple[Registration | None, Registration | None]:
            await store.put(registered("nightly", owner="u_left"))
            adopted = await store.adopt(
                "nightly", new_owner=person("u_heir"), principals=Records(), now=NOW
            )
            return adopted, await store.registration("nightly")

        adopted, stored = with_store(url, work)

    assert adopted is not None and adopted.owner_principal_id == "u_heir"
    assert stored == adopted


def test_an_automation_with_a_live_owner_is_not_adopted_and_nothing_is_written() -> None:
    """Delete this and the row lock is taken, the standing ignored and the owner replaced."""
    with automations("brain_au_not_adopted") as url:

        async def work(store: StoredAutomations) -> Registration | None:
            await store.put(registered("nightly", owner="u_owner"))
            with pytest.raises(RegistrationError, match="still has a live owner"):
                await store.adopt(
                    "nightly",
                    new_owner=person("u_heir"),
                    principals=Records(person("u_owner")),
                    now=NOW,
                )
            return await store.registration("nightly")

        stored = with_store(url, work)

    assert stored is not None and stored.owner_principal_id == "u_owner"


def test_adopting_an_automation_nobody_registered_is_nothing() -> None:
    """Delete this and adoption by id is an oracle for which automations exist."""
    with automations("brain_au_adopt_absent") as url:

        async def work(store: StoredAutomations) -> Registration | None:
            return await store.adopt(
                "nobody", new_owner=person("u_heir"), principals=Records(), now=NOW
            )

        assert with_store(url, work) is None


def test_the_policy_refuses_an_adoption_written_in_somebody_elses_name() -> None:
    """The store only ever writes the session's own principal; this is the policy holding that
    for a statement that does not. Delete this and a session can hand an automation to anybody."""
    with automations("brain_au_update_policy") as url:

        async def put(store: StoredAutomations) -> None:
            await store.put(registered("nightly", owner="u_left"))

        with_store(url, put)
        with (
            as_app(url, ("app.automation_id", "nightly"), ("app.principal_id", "u_heir")) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute("UPDATE gate.automation_owner SET owner_principal_id = 'u_mallory'")
        with as_app(url, ("app.automation_id", "nightly"), ("app.principal_id", "u_heir")) as conn:
            conn.execute("UPDATE gate.automation_owner SET owner_principal_id = 'u_heir'")
        with as_app(url, ("app.automation_id", "another"), ("app.principal_id", "u_heir")) as conn:
            elsewhere = conn.execute(
                "UPDATE gate.automation_owner SET owner_principal_id = 'u_heir'"
            ).rowcount
        owner = sql(url, "SELECT owner_principal_id FROM gate.automation_owner")

    assert elsewhere == 0, "a session naming another automation reached this one"
    assert owner == [("u_heir",)]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE gate.automation_owner SET credential_digest = repeat('0', 64)",
        "UPDATE gate.automation_owner SET ceiling = '[]'::jsonb",
        "UPDATE gate.automation_owner SET declared_tools = ARRAY['local.anything']",
        "DELETE FROM gate.automation_owner",
    ],
)
def test_the_app_role_cannot_edit_the_credential_the_ceiling_or_the_tools_or_delete(
    statement: str,
) -> None:
    """UPDATE is granted on the owner and the timestamp alone, and there is no DELETE. Delete this
    and a session that may adopt can also widen the ceiling it is adopting."""
    with automations("brain_au_grants") as url:

        async def put(store: StoredAutomations) -> None:
            await store.put(registered("nightly"))

        with_store(url, put)
        with (
            as_app(url, ("app.automation_id", "nightly"), ("app.principal_id", "u_owner")) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(statement)


def test_the_table_refuses_a_registration_that_declares_no_tool_or_carries_no_digest() -> None:
    """Delete this and a row written round the store declares nothing, which the projector would
    read as an automation with no tools, or carries a digest nothing can match."""
    with automations("brain_au_checks") as url:
        insert = (
            "INSERT INTO gate.automation_owner "
            "(automation_id, owner_principal_id, credential_digest, declared_tools, ceiling) "
            "VALUES (%s, 'u_owner', %s, %s, '[]'::jsonb)"
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "no_tools", "0" * 64, [])
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "no_digest", "not-a-digest", ["local.read_price_list"])
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "has.dot", "0" * 64, ["local.read_price_list"])
        sql(url, insert, "fine", "0" * 64, ["local.read_price_list"])
        assert present(url, TABLES) == set(TABLES)


def test_a_second_registration_under_one_id_is_refused() -> None:
    """Delete this and registering an id twice replaces who an automation runs as."""
    with automations("brain_au_twice") as url:

        async def work(store: StoredAutomations) -> None:
            await store.put(registered("nightly", owner="u_owner"))
            with pytest.raises(IntegrityError):
                await store.put(registered("nightly", owner="u_owner"))

        with_store(url, work)


def test_the_migration_builds_exactly_what_the_model_declares() -> None:
    """Delete this and the migration and the model can disagree about a constraint or the index."""
    with (
        automations("brain_au_shape") as url,
        modelled("brain_au_shape_modelled", TABLES) as from_models,
    ):
        assert shape(url, TABLES) == shape(from_models, TABLES)
        assert secured(url, TABLES) == dict.fromkeys(TABLES, True)


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Delete this and a downgrade that leaves the table behind is found at the next upgrade."""
    with automations("brain_au_down_up") as url:
        migrate("brain_au_down_up", "downgrade", predecessor())
        gone = present(url, TABLES)
        migrate("brain_au_down_up", "upgrade", "0044")
        back = present(url, TABLES)

    assert gone == set()
    assert back == set(TABLES)
