"""The grants version is read over the application's own async pool, as the application role,
naming its principal, and it moves when `0003`'s triggers say it does.

`tests/unit/test_cache.py` holds the statement order and the failure wrapping against a fake
session. This file builds `0002` and `0003` in a database of its own, stamped at `0001` for the
reason `tests/unit/test_entitlement_store.py` gives, and drives
`brain.cache.PostgresVersionSource` through the session factory lifespan will hand it. It skips
when there is no server, as every file using that fixture does.

Task ids: M1.4.5
"""

from __future__ import annotations

import psycopg

from brain.cache import PostgresVersionSource
from brain.gate.entitlement_store import PRINCIPAL_SETTING, StoredEntitlements
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_entitlement_store import (
    READ_NAMES,
    READ_PRICES,
    a_grant,
    a_principal,
    resolver,
    revoke,
    with_store,
)


def version_of(url: str, principal_id: str) -> int:
    """One read through the source, over the same factory the entitlement store is given."""

    async def work(store: StoredEntitlements) -> int:
        return await PostgresVersionSource(store.sessions).grants_version(principal_id)

    return with_store(url, work)


def test_a_principal_who_has_never_been_granted_anything_reads_as_zero_as_the_application() -> None:
    """No row is version zero, and reading it is a success. Delete this and a source that raised
    for a missing row, or that could only read as a superuser, passes every test that grants
    something first."""
    with resolver("brain_vs_zero") as url:
        a_principal(url, "u_new_starter")
        assert version_of(url, "u_new_starter") == 0


def test_a_grant_and_its_revocation_each_move_the_version_the_source_reads() -> None:
    """M1.4.5 end to end: the trigger bumps and this source sees the bump on its next read. Delete
    this and the source can read a column the triggers never touch, and every revocation would
    wait out the sixty-second TTL."""
    with resolver("brain_vs_moves") as url:
        a_principal(url, "u_reader")
        before = version_of(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES)
        a_grant(url, "u_reader", READ_NAMES)
        granted = version_of(url, "u_reader")
        revoke(url, "u_reader", READ_PRICES)
        revoked = version_of(url, "u_reader")
        [(stored,)] = sql(
            url, "SELECT version FROM gate.grants_version WHERE principal_id = %s", "u_reader"
        )

    assert before < granted < revoked
    assert revoked == stored


#: `0003`'s version policy, narrowed to the principal the transaction names.
NARROWED_TO_THE_READER: tuple[str, ...] = (
    "DROP POLICY grants_version_visible ON gate.grants_version",
    "CREATE POLICY grants_version_visible ON gate.grants_version FOR ALL TO brain_app"
    " USING (principal_id = current_setting('app.principal_id', true)) WITH CHECK (true)",
)


def test_the_version_is_still_read_under_a_policy_that_narrows_to_the_principal_named() -> None:
    """`A_VERSION_READ_NAMES_ITS_PRINCIPAL`. Under such a policy a read naming nobody sees no row,
    which is version zero, for ever: a cache key no revocation retires. Delete this and the
    setting can go with every other test green. The second connection proves the replacement
    policy narrows at all, without which the read proves nothing."""
    with resolver("brain_vs_narrowed") as url:
        a_principal(url, "u_reader")
        a_grant(url, "u_reader", READ_PRICES)
        for statement in NARROWED_TO_THE_READER:
            sql(url, statement)
        version = version_of(url, "u_reader")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config(%s, %s, false)", (PRINCIPAL_SETTING, "u_somebody"))
            seen = conn.execute("SELECT count(*) FROM gate.grants_version").fetchone()

    assert version > 0
    assert seen == (0,)
