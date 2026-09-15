"""Every soft-deleted table, on a real database as `brain_app`: a live row is read and retired, a
retired row is hidden from the next statement and every later one, it cannot be updated back, and
a retirement not stamped by its own statement is refused.

`tests/invariants/test_soft_delete_invariants.py` reads the same properties off the migrations,
which is what stops the next migration; this is what proves PostgreSQL agrees with that reading.
The argument for the policy shape is in `0045`. The database is built by
`tests.fixtures.retirable`, which runs every migration to head where the server has pgvector and
the soft-deleted tables' own migrations where it does not; `know.chunk` needs the extension, so
its rows are skipped by name on a server without it rather than silently absent.

**Every table has a recipe, and the recipe list is held to the models.** A new soft-deleted table
without one fails `test_every_soft_deleted_model_has_a_recipe`, so the table that most needs this
proof is not the one it quietly skips.

**Each refusal is asked twice, with a WHERE clause and without one, and the second is not
redundant.** An UPDATE whose WHERE names a column checks the old and the new row against the read
policy as well as the update policy, and the read policy carries the owner and the liveness test
too, so every refusal a WHERE clause meets is decided by the read policy and the update policy's
own USING and WITH CHECK are never the deciding check. An UPDATE with no WHERE clause needs no read
access and is judged by the update policy alone. Found by mutation: dropping the owner from
`chat.conversation`'s update policy survived every WHERE-clause test, and it let a stranger's
`UPDATE chat.conversation SET deleted_at = ...` reach every conversation in the table.

Rows are written as the superuser, which bypasses row-level security, and every assertion about
what the application can do is made through a connection whose role is `brain_app`. Each row is
retired as the superuser afterwards so the partial unique indexes, which admit one live row per
key, never see two. Every statement is a named template filled with a table name and a predicate
this file wrote, never with anything read from outside it.

Task ids: none
"""

from __future__ import annotations

import importlib.util
import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Final

import psycopg
import pytest

import brain.tables  # noqa: F401 - registers every table on the metadata
from brain.db import metadata
from tests.fixtures.retirable import RETIRABLE_MIGRATION, present_tables, retirable
from tests.fixtures.scratch_postgres import database_url, sql

_SERIAL = itertools.count(1)
PERSON = (
    "INSERT INTO auth.principal (id, kind, employment, display_name)"
    " VALUES ('u_rr_{n}', 'human', 'staff', 'Person {n}')"
)
OWNED_BY_THE_SESSION = (("app.principal_id", "u_rr_{n}"), ("app.departments", ""))

#: The retirement a store writes. See 0045 on why the stamp is the statement's.
RETIRE: Final = "UPDATE {table} SET deleted_at = statement_timestamp() WHERE {where} RETURNING 1"
COUNT: Final = "SELECT count(*) FROM {table} WHERE {where}"
UNRETIRE: Final = "UPDATE {table} SET deleted_at = NULL WHERE {where}"
BACKDATED: Final = (
    "UPDATE {table} SET deleted_at = statement_timestamp() - interval '1 day' WHERE {where}"
)
HANDED_ON: Final = (
    "UPDATE {table} SET deleted_at = statement_timestamp(), principal_id = 'u_rr_x' WHERE {where}"
)
#: The same three with no WHERE clause, so no read access is needed and the update policy alone
#: decides. See the module docstring.
UNRETIRE_EVERY: Final = "UPDATE {table} SET deleted_at = NULL"
BACKDATE_EVERY: Final = "UPDATE {table} SET deleted_at = statement_timestamp() - interval '1 day'"
RETIRE_EVERY: Final = "UPDATE {table} SET deleted_at = statement_timestamp()"
HAND_ON_EVERY: Final = (
    "UPDATE {table} SET deleted_at = statement_timestamp(), principal_id = 'u_rr_x'"
)
RETIRED: Final = "SELECT deleted_at IS NOT NULL FROM {table} WHERE {where}"
TIDY: Final = "UPDATE {table} SET deleted_at = now() WHERE {where} AND deleted_at IS NULL"
REFUSED_BY_THE_POLICY: Final = "row-level security"


@dataclass(frozen=True)
class Recipe:
    """One live row of one table, as superuser SQL, and the predicate that finds it again.

    Every string is formatted with `n`, so two rows of a table never collide on a unique key.
    """

    insert: str
    where: str
    parents: tuple[str, ...] = ()
    settings: tuple[tuple[str, str], ...] = ()


RECIPES: Final[dict[str, Recipe]] = {
    "auth.principal": Recipe(PERSON, "id = 'u_rr_{n}'"),
    "auth.principal_identity": Recipe(
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at)"
        " VALUES ('api', lpad(to_hex({n}), 64, '0'), 'u_rr_{n}', now())",
        "principal_id = 'u_rr_{n}'",
        parents=(PERSON,),
    ),
    "gate.capability_grant": Recipe(
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason)"
        " VALUES ('u_rr_{n}', 'read:price_list', '{{\"clauses\": []}}', 'u_admin', 'measured')",
        "principal_id = 'u_rr_{n}'",
        parents=(PERSON,),
    ),
    "gate.capability_pack": Recipe(
        "INSERT INTO gate.capability_pack (name, description, capabilities)"
        " VALUES ('rr_pack_{n}', 'described', ARRAY['read:price_list'])",
        "name = 'rr_pack_{n}'",
    ),
    "gate.capability_pack_assignment": Recipe(
        "INSERT INTO gate.capability_pack_assignment"
        " (principal_id, pack_id, scope, granted_by, reason)"
        " SELECT 'u_rr_{n}', id, '{{\"clauses\": []}}', 'u_admin', 'measured'"
        " FROM gate.capability_pack WHERE name = 'rr_parent_{n}'",
        "principal_id = 'u_rr_{n}'",
        parents=(
            PERSON,
            "INSERT INTO gate.capability_pack (name, description, capabilities)"
            " VALUES ('rr_parent_{n}', 'described', ARRAY['read:price_list'])",
        ),
    ),
    "gate.field_policy": Recipe(
        "INSERT INTO gate.field_policy (entity, field, required_capability, classification)"
        " VALUES ('client', 'field_{n}', 'read:client.name', 'internal')",
        "field = 'field_{n}'",
    ),
    "gate.scope": Recipe(
        "INSERT INTO gate.scope (slug, predicate) VALUES ('rrscope{n}', '{{}}')",
        "slug = 'rrscope{n}'",
    ),
    "gate.department": Recipe(
        "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
        " VALUES ('company', 'rrdept{n}', 'Department', 'rrdept{n}')",
        "slug = 'rrdept{n}'",
    ),
    "gate.team": Recipe(
        "INSERT INTO gate.team (department_id, slug, name)"
        " SELECT id, 'rrteam{n}', 'Team' FROM gate.department WHERE slug = 'rrparent{n}'",
        "slug = 'rrteam{n}'",
        parents=(
            "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
            " VALUES ('company', 'rrparent{n}', 'Department', 'rrparent{n}')",
        ),
    ),
    "ops.routing_tier": Recipe(
        "INSERT INTO ops.routing_tier (tier, context_window) VALUES ('small', {n})",
        "context_window = {n}",
    ),
    "ops.routing_rung": Recipe(
        "INSERT INTO ops.routing_rung (tier, scope, position, role, deployment_id, provider,"
        " model, attempts, timeout_seconds, max_concurrency) VALUES ('small',"
        " '{{\"clauses\": []}}', {n}, 'primary', 'deployment', 'provider', 'model', 1, 1, 1)",
        "position = {n}",
    ),
    "gate.capability_registry": Recipe(
        "INSERT INTO gate.capability_registry (capability, description)"
        " VALUES ('read:rr_{n}', 'described')",
        "capability = 'read:rr_{n}'",
    ),
    "ops.setting": Recipe(
        "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
        " VALUES ('ui.rr_{n}', 'string', '\"blue\"', 'described', 'u_admin')",
        "key = 'ui.rr_{n}'",
    ),
    "chat.conversation": Recipe(
        "INSERT INTO chat.conversation (principal_id) VALUES ('u_rr_{n}')",
        "principal_id = 'u_rr_{n}'",
        settings=OWNED_BY_THE_SESSION,
    ),
    "proj.record": Recipe(
        "INSERT INTO proj.record (source, entity, source_id, last_seen_at)"
        " VALUES ('crm', 'client', 'rr_{n}', now())",
        "source_id = 'rr_{n}'",
    ),
    "gate.fast_path_rule": Recipe(
        "INSERT INTO gate.fast_path_rule (rule_id, template, slot, source, entity, match_field,"
        " answer_field, created_by) VALUES ('rule_{n}', 'what is the price of item {n} {{sku}}',"
        " 'sku', 'crm', 'client', 'sku', 'price', 'u_admin')",
        "rule_id = 'rule_{n}'",
    ),
    "know.chunk": Recipe(
        "INSERT INTO know.chunk (chunk_id, document_id, ordinal, kind, span_start, span_end,"
        " body, owner_id, visibility, state) VALUES ('chunk_{n}', 'document_{n}', 0, 'prose',"
        " 0, 1, 'body', 'u_rr_{n}', 'personal', 'published')",
        "chunk_id = 'chunk_{n}'",
        settings=OWNED_BY_THE_SESSION,
    ),
}


def _stays_readable() -> frozenset[str]:
    spec = importlib.util.spec_from_file_location("migration_0045_readable", RETIRABLE_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return frozenset(module.RETIRED_ROWS_STAY_READABLE)


@dataclass(frozen=True)
class Row:
    """One live row written for one test, and how to reach it as the application."""

    table: str
    where: str
    settings: tuple[tuple[str, str], ...]

    def statement(self, template: str) -> str:
        return template.format(table=self.table, where=self.where)

    def retire(self) -> str:
        return RETIRE.format(table=self.table, where=f"{self.where} AND deleted_at IS NULL")


def as_app(url: str, row: Row, *statements: str) -> list[list[tuple[Any, ...]]]:
    """Statements in one transaction as `brain_app`, with the row's session settings, committed."""
    results: list[list[tuple[Any, ...]]] = []
    with psycopg.connect(url, options="-c role=brain_app") as conn:
        for name, value in row.settings:
            conn.execute("SELECT set_config(%s, %s, true)", (name, value))
        for statement in statements:
            cursor = conn.execute(statement)
            results.append(cursor.fetchall() if cursor.description else [(cursor.rowcount,)])
    return results


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    if database_url() is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    with retirable("brain_retirable_rows") as scratch:
        yield scratch


@pytest.fixture(params=sorted(RECIPES))
def row(request: pytest.FixtureRequest, url: str) -> Iterator[Row]:
    table: str = request.param
    if table not in present_tables(url):
        pytest.skip(f"{table} is not built on this server: it needs pgvector, which CI has")
    recipe = RECIPES[table]
    n = next(_SERIAL)
    for parent in recipe.parents:
        sql(url, parent.format(n=n))
    sql(url, recipe.insert.format(n=n))
    found = Row(
        table=table,
        where=recipe.where.format(n=n),
        settings=tuple((name, value.format(n=n)) for name, value in recipe.settings),
    )
    try:
        yield found
    finally:
        sql(url, found.statement(TIDY))


def is_retired(url: str, row: Row) -> bool:
    """As the superuser, which sees every row whatever the policy says."""
    return bool(sql(url, row.statement(RETIRED))[0][0])


# ------------------------------------------------------------------------ every table


def test_every_soft_deleted_model_has_a_recipe() -> None:
    """Delete this and a soft-deleted table added next year is simply not in the parametrisation,
    so the one table nobody proved is the one whose policy was copied from somewhere wrong."""
    soft = {key for key, table in metadata.tables.items() if "deleted_at" in table.c}
    assert soft == set(RECIPES)


def test_every_soft_deleted_table_the_database_holds_has_a_recipe(url: str) -> None:
    """Held against the catalogue as well as the models. Delete this and a table a migration built
    without a model, which `test_tables` would also miss, is never retired here."""
    assert present_tables(url) <= set(RECIPES)
    assert len(present_tables(url)) >= len(RECIPES) - 1


def test_the_application_role_reads_a_live_row(url: str, row: Row) -> None:
    """The positive case for every hiding below. Delete it and a policy that hides every row
    passes them all, and nothing the application reads is ever there."""
    assert as_app(url, row, row.statement(COUNT)) == [[(1,)]]


def test_a_live_row_is_retired_by_the_application_role(url: str, row: Row) -> None:
    """The defect 0045 repaired: this raised "new row violates row-level security policy" on every
    table here. Delete it and a grant can again be impossible to revoke through the application
    with every static reading of the policies green."""
    assert as_app(url, row, row.retire()) == [[(1,)]]
    assert is_retired(url, row)


def test_a_retired_row_is_hidden_from_the_next_statement_in_its_own_transaction(
    url: str, row: Row
) -> None:
    """The row is admitted to the retiring statement only. Delete this and a read policy written
    with `transaction_timestamp()` passes, which leaves a revoked grant visible to the rest of the
    request that revoked it."""
    expected = 1 if row.table in _stays_readable() else 0
    assert as_app(url, row, row.retire(), row.statement(COUNT)) == [[(1,)], [(expected,)]]


def test_a_retired_row_is_hidden_from_every_later_transaction(url: str, row: Row) -> None:
    """Delete this and a read policy of `USING (true)` passes, so every revoked grant is back in
    any read that forgot its WHERE clause. `gate.fast_path_rule` stays readable, for the reason
    0019 gives, and the invariant test holds that exception to that one table."""
    as_app(url, row, row.retire())
    expected = 1 if row.table in _stays_readable() else 0
    assert as_app(url, row, row.statement(COUNT)) == [[(expected,)]]


def test_a_retired_row_cannot_be_updated_back(url: str, row: Row) -> None:
    """Revocation is the deletion of a grant, and a deletion undone by an UPDATE was a suspension.
    Delete this and an update policy of `USING (true)` passes, which 0019 wrote. Asked again with
    no WHERE clause, because only that form is decided by the update policy's own reach."""
    as_app(url, row, row.retire())

    assert as_app(url, row, row.statement(UNRETIRE)) == [[(0,)]]
    as_app(url, row, row.statement(UNRETIRE_EVERY))
    assert is_retired(url, row)


def test_a_retirement_not_stamped_by_its_own_statement_is_refused(url: str, row: Row) -> None:
    """The update check is the stamp. Delete this and a WITH CHECK of `true` passes, and a grant
    can be recorded as revoked last March by whoever writes the UPDATE; only the form with no WHERE
    clause is decided by that check alone. The live row afterwards is the sibling: the refusals
    took nothing with it."""
    for template in (BACKDATED, BACKDATE_EVERY):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match=REFUSED_BY_THE_POLICY):
            as_app(url, row, row.statement(template))

    assert not is_retired(url, row)
    assert as_app(url, row, row.statement(COUNT)) == [[(1,)]]


# ---------------------------------------------------------- restrictions carried across


def a_conversation(url: str, *, session: str) -> Row:
    """A live conversation owned by a principal of its own, read by `session`."""
    n = next(_SERIAL)
    sql(url, RECIPES["chat.conversation"].insert.format(n=n))
    owner = f"u_rr_{n}" if session == "owner" else session
    return Row("chat.conversation", f"principal_id = 'u_rr_{n}'", (("app.principal_id", owner),))


def test_a_conversation_is_retired_only_by_its_owner(url: str) -> None:
    """0005's owner restriction is carried into the new update policy's reach. Delete this and the
    update policy can drop it, and a stranger's UPDATE with no WHERE clause retires every
    conversation in the table, which is the mutation that survived before this asked it."""
    stranger = a_conversation(url, session="u_rr_x")

    assert as_app(url, stranger, stranger.retire()) == [[]]
    assert as_app(url, stranger, stranger.statement(RETIRE_EVERY)) == [[(0,)]]
    assert not is_retired(url, stranger)


def test_a_conversation_is_not_handed_to_somebody_else_while_it_is_retired(url: str) -> None:
    """The owner restriction is on the update check as well as its reach. Delete this and the
    owner can retire a conversation into another principal's name, which a statement with no WHERE
    clause reaches with nothing but the update check in its way."""
    owner = a_conversation(url, session="owner")

    for template in (HANDED_ON, HAND_ON_EVERY):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match=REFUSED_BY_THE_POLICY):
            as_app(url, owner, owner.statement(template))

    assert not is_retired(url, owner)


def test_a_chunk_is_retired_only_within_the_sessions_reach(url: str) -> None:
    """0009's reach predicate is carried into the chunk's update policy. Delete this and an
    indexing worker running as one person can retire another person's personal chunks."""
    if "know.chunk" not in present_tables(url):
        pytest.skip("know.chunk is not built on this server: it needs pgvector, which CI has")
    n = next(_SERIAL)
    sql(url, RECIPES["know.chunk"].insert.format(n=n))
    stranger = Row(
        "know.chunk",
        f"chunk_id = 'chunk_{n}'",
        (("app.principal_id", "u_rr_x"), ("app.departments", "")),
    )

    assert as_app(url, stranger, stranger.retire()) == [[]]
    assert as_app(url, stranger, stranger.statement(RETIRE_EVERY)) == [[(0,)]]
    assert not is_retired(url, stranger)
