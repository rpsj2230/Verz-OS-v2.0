"""`0200`'s `gate.grant_ids_of`: one person's grant ids, removed ones included, and nothing else.

The pure half holds the migration's statements to what `0177`'s function is held to. The server
half builds the schema at head, gives one person two capabilities and takes one away, gives another
person one, and reads them back through `brain.audit_routes.StoredPersonGrants` as the application
role, which cannot see the removed row in the table at all.

Task ids: M33.4.1.2
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from brain.audit_routes import MOST_GRANTS_READ, StoredPersonGrants
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_grant, a_principal, revoke

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0200_person_grant_ids.py"
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0200", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------ the migration
def test_the_function_is_a_pinned_definer_revoked_from_public_that_returns_ids_alone() -> None:
    """What `0177`'s function is held to, held here too, off the migration's own statements: a
    pinned search path, `STABLE`, EXECUTE for the application alone, one column and a bound the
    caller passes. Delete this and the search path can be left to the caller, PUBLIC keep
    EXECUTE, or the function grow a column that says what was granted past the ledger's view."""
    built = migration()
    body = " ".join(built.CREATE_FUNCTION.split())

    assert "SECURITY DEFINER" in body and "STABLE" in body
    assert "SET search_path = pg_catalog, gate" in body
    assert "RETURNS TABLE ( grant_id uuid )" in body
    assert "LIMIT greatest(p_limit, 0)" in body
    assert (
        f"REVOKE EXECUTE ON FUNCTION {built.FUNCTION} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {built.FUNCTION} TO brain_app",
    ) == built.GRANTS
    assert built.TABLES == ()


# ------------------------------------------------------------------------ on a server
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_person_grant_ids") as url:
        for pid in ("u_held", "u_other"):
            a_principal(url, pid)
        a_grant(url, "u_held", "read:client.name")
        a_grant(url, "u_held", "read:client.cost")
        revoke(url, "u_held", "read:client.cost")
        a_grant(url, "u_other", "read:client.margin")
        yield url


def _read(url: str, principal_id: str) -> tuple[tuple[str, ...], int, bool]:
    async def go() -> tuple[tuple[str, ...], int, bool]:
        from sqlalchemy import text

        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            source = StoredPersonGrants(sessions)
            ids = await source.grant_ids(principal_id)
            async with sessions() as session:
                visible = (
                    await session.execute(
                        text("SELECT count(*) FROM gate.capability_grant WHERE principal_id = :p"),
                        {"p": principal_id},
                    )
                ).scalar_one()
            person = await source.person(principal_id)
            return ids, int(visible), person is not None
        finally:
            await built.dispose()

    return run(go)


@pytest.mark.needs_db
def test_a_persons_grant_ids_include_the_removed_one_the_application_cannot_otherwise_see(
    install: str,
) -> None:
    """**The reason the function exists.** As the application role, the table shows the person's
    one live grant and the function returns both of theirs, the removed one included, and neither
    of somebody else's. Delete this and a person's History can only ever show grants that are
    still live, so no removal reaches it, or the function answers with another person's grants."""
    ids, visible, known = _read(install, "u_held")
    expected = {
        str(one)
        for (one,) in sql(
            install, "SELECT id FROM gate.capability_grant WHERE principal_id = 'u_held'"
        )
    }
    others = {
        str(one)
        for (one,) in sql(
            install, "SELECT id FROM gate.capability_grant WHERE principal_id = 'u_other'"
        )
    }

    assert visible == 1
    assert set(ids) == expected and len(ids) == 2
    assert not set(ids) & others
    assert known


@pytest.mark.needs_db
def test_the_function_runs_as_its_owner_for_the_application_alone(install: str) -> None:
    """Read off the catalogue. Delete this and a missing REVOKE leaves a read past the grant
    table's policy callable by any role with USAGE on the schema."""
    [(definer, config, acl)] = sql(
        install,
        "SELECT prosecdef, proconfig, proacl::text[] FROM pg_proc WHERE proname = 'grant_ids_of'",
    )
    assert definer is True
    assert config == ["search_path=pg_catalog, gate"]
    assert any(one.startswith("brain_app=X") for one in acl)
    assert not any(one.startswith("=X") for one in acl)


def test_the_bound_is_large_enough_for_a_person_and_never_unbounded() -> None:
    """A person rarely holds more than a few dozen grants in a lifetime; five hundred reads every
    one of them and still bounds a pathological row count. Delete this and the bound can drop to
    a figure that silently cuts a long-serving person's History short."""
    assert 100 <= MOST_GRANTS_READ <= 10_000
