"""The delegation refusal, measured against a real PostgreSQL rather than described.

Two halves. The first needs no server and holds the SQL text against the things it reads: the
columns the migration builds and the document shape pydantic writes. The second runs the
statements the migration runs, in a database this file creates and drops, and asks the server
what it does with a row.

**The second half is the only half that is evidence.** A trigger nobody has executed is a
string, and this repository's commonest defect is a correct guard nothing reaches. Every test
below saying a row is refused inserts that row.

`0028` is applied through alembic rather than by re-issuing its DDL here, and the database is
stamped at `0027` first so the twenty-seven migrations before it, which need extensions a
laptop may not have, are not a condition of running this. What that buys is that the thing
under test is the migration that ships and not a copy of it written in a test.

Every insert carries a `run_id` taken from the name of the test that made it, rather than a
shared literal. The table holds one row per `(run_id, child_id)`, so a shared literal would
have one test's leftover row refusing another test's insert on the unique constraint, and a
test asserting that an insert is refused passes just as well for the wrong reason.

Task ids: M18.3.1, M18.3.2
"""

from __future__ import annotations

import itertools
import json
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.core.scope_sql import (
    DELEGATION_COLUMNS,
    DELEGATION_INSTALL,
    DELEGATION_REFUSED_SQLSTATE,
    DELEGATION_RELATION,
    DELEGATION_SCHEMA,
    DELEGATION_TABLE,
    DELEGATION_TRIGGER_FUNCTION_SQL,
    DELEGATION_UNINSTALL,
    trigger_columns,
)
from brain.orchestration.delegation import narrowing_refusals

#: Far outside any plausible wall clock, on purpose. `tests/unit/test_scope_and_capability.py`
#: records why: a fixture with a date near today is a clock, and it goes off. Nothing here is
#: about the present, so the instants are chosen so that no run ever crosses one.
AT = datetime(2500, 1, 1, tzinfo=UTC)
ALREADY_OVER = datetime(2400, 1, 1, tzinfo=UTC)
STILL_TO_COME = datetime(2600, 1, 1, tzinfo=UTC)
LATER_STILL = datetime(2700, 1, 1, tzinfo=UTC)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"
COLUMN_IN_MIGRATION = re.compile(r'sa\.Column\(\s*"([a-z][a-z0-9_]*)"')


def reach(
    principal: str, *grants: tuple[str, Scope], not_after: datetime | None = None
) -> EntitlementSet:
    """An entitlement set, written short enough that a test reads as its own claim."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=value), scope=scope) for value, scope in grants
        ),
        not_after=not_after,
    )


def where(**fields: str) -> Scope:
    return Scope(clauses=tuple(Clause(field=k, op=Op.EQ, value=v) for k, v in fields.items()))


def doc(one: EntitlementSet) -> str:
    """The jsonb a column holds: what pydantic writes, with nothing in between."""
    return json.dumps(one.model_dump(mode="json"))


# ------------------------------------------------------------------- what needs no server
def test_the_trigger_reads_only_columns_the_migration_builds() -> None:
    """The join between a migration's DDL and a string in another module, which nothing else
    type checks.

    A column renamed on one side and not the other produces a table whose every insert raises,
    which is fail-closed and is still a defect an operator finds rather than a gate. Asserted
    in both directions: the declared list is what the trigger really reads, and every name in
    it is a column the migration really builds.

    Delete this and the two can drift until the first insert on a fresh install.
    """
    source = (MIGRATION / "0028_delegation_narrowing.py").read_text(encoding="utf-8")
    built = set(COLUMN_IN_MIGRATION.findall(source))

    assert built, "no column was read out of the migration, so the comparison proves nothing"
    assert trigger_columns() == DELEGATION_COLUMNS
    assert set(DELEGATION_COLUMNS) <= built, sorted(set(DELEGATION_COLUMNS) - built)


def test_a_trigger_naming_a_column_the_table_lacks_is_reported() -> None:
    """The positive and negative halves of `trigger_columns`, on text it is handed.

    A reader of the test above cannot tell a scan that found the right columns from one that
    found nothing, and `DELEGATION_COLUMNS` matching an empty tuple would be a green test over
    a check that reads no columns at all. This hands it two bodies whose answers are known.

    Delete this and the column comparison above is satisfied by a regex that stopped matching.
    """
    assert trigger_columns("NEW.one and NEW.two and NEW.one again") == ("one", "two")
    assert trigger_columns("nothing here refers to a row") == ()


def test_the_document_the_sql_reads_is_the_one_pydantic_writes() -> None:
    """**The fail-open this whole arrangement is one rename away from.**

    The SQL reads `grants`, `principal_id`, `not_after`, `capability.value` and
    `scope.clauses` by name out of a jsonb column. Rename any of those in
    `brain.core.entitlement` or `brain.core.scope` and every lookup returns NULL, the computed
    reach comes back holding nothing, and a child claiming nothing is a subset of nothing: the
    trigger goes on admitting every row while checking none of them. Nothing else in the tree
    would notice, because the Python side would have been renamed consistently and would still
    pass.

    Asserted against a real serialisation rather than against a list written out here, for the
    reason CLAUDE.md gives about a constant compared with itself: a key list restated in a
    test moves when somebody updates the test.

    Delete this and the refusal becomes decorative on the day a field is renamed.
    """
    body = reach("p:one", ("read:client.name", where(department="web")), not_after=AT).model_dump(
        mode="json"
    )
    installed = DELEGATION_TRIGGER_FUNCTION_SQL + "".join(DELEGATION_INSTALL)

    assert set(body) == {"principal_id", "grants", "not_after"}
    assert set(body["grants"][0]) == {"capability", "scope"}
    assert set(body["grants"][0]["capability"]) == {"value"}
    assert set(body["grants"][0]["scope"]) == {"clauses"}
    assert set(body["grants"][0]["scope"]["clauses"][0]) == {"field", "op", "value"}
    for key in ("principal_id", "grants", "not_after", "capability", "value", "scope", "clauses"):
        assert f"'{key}'" in installed, key


def test_every_function_the_install_creates_the_uninstall_drops() -> None:
    """A downgrade that leaves a function behind is a downgrade that did not reverse.

    The two tuples are written by hand, in opposite orders, and the second is the one nobody
    looks at again. A function added to the install without its drop leaves `gate` holding a
    definition of the central rule on an install that has rolled back past it, which is worse
    than an untidy schema: the next upgrade's `CREATE OR REPLACE` would find it and a reader
    would have no way to tell which release it came from.

    Delete this and the downgrade rots silently, one function at a time.
    """
    created = {
        line.split("FUNCTION ", 1)[1].split("(", 1)[0].strip()
        for statement in DELEGATION_INSTALL
        for line in statement.splitlines()
        if "CREATE OR REPLACE FUNCTION" in line
    }
    dropped = {
        statement.split("EXISTS ", 1)[1].split("(", 1)[0].strip()
        for statement in DELEGATION_UNINSTALL
    }

    assert created, "nothing was read out of the install, so the comparison proves nothing"
    assert created == dropped


def test_the_table_is_named_once_and_qualified_from_its_parts() -> None:
    """Three constants naming one table is two chances to disagree, so they are derived.

    Delete this and a schema changed in one of them is a trigger hanging on a table the
    migration did not build.
    """
    assert DELEGATION_RELATION.split(".") == [DELEGATION_SCHEMA, DELEGATION_TABLE]
    assert DELEGATION_RELATION in DELEGATION_TRIGGER_FUNCTION_SQL


# ------------------------------------------------------- what only a server can answer
def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL") or None


#: A database of this file's own, created and dropped here. The unit-test job runs pytest
#: before it runs any migration, so `DATABASE_URL` points at an empty database and creating
#: `gate` in it would collide with `0001` later in the same job.
SCRATCH_DATABASE = "brain_delegation_check"


def _pointed_at(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


#: A second database of this file's own, for the one test that migrates down and back up. Kept
#: apart from `SCRATCH_DATABASE`, so a failure half way through that test cannot leave every
#: other test here reading a downgraded function.
ROUND_TRIP_DATABASE = "brain_delegation_round_trip"


def _fresh(admin: str, database: str) -> str:
    """Drop and create a scratch database holding what the migrations before `0028` would
    have left for it to need, the `gate` schema and the `brain_app` role, and return its url."""
    import psycopg

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{database}"')

    scratch = _pointed_at(admin, database)
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {DELEGATION_SCHEMA}")
        conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_app') "
            "THEN CREATE ROLE brain_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
        )
        conn.execute(f"GRANT USAGE ON SCHEMA {DELEGATION_SCHEMA} TO brain_app")
    return scratch


def _migrate(url: str, database: str, verb: str, revision: str) -> None:
    """One alembic command against one scratch database, through the migrations that ship.

    `DATABASE_URL` is what the migration environment reads, so it points at the scratch
    database for the length of the command and is put back afterwards.
    """
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    commands = {"stamp": command.stamp, "upgrade": command.upgrade, "downgrade": command.downgrade}
    before = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _pointed_at(url, database)
    try:
        commands[verb](config, revision)
    finally:
        if before is None:  # pragma: no cover - DATABASE_URL is set whenever this runs
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = before


@pytest.fixture(scope="module")
def server() -> Iterator[Any]:
    """A connection to a database holding exactly what `0028` and `0029` install.

    Stamped at `0027` so the migrations before it, and the extensions they need, are not a
    condition of running these tests, and then upgraded for real: what is under test is the
    migrations that ship rather than a copy of their DDL written out here. Upgraded to `0029`
    and no further, because `0029` is the last migration that touches `gate.delegation`, and a
    later one needing an extension this database lacks would make these tests depend on it.
    """
    import psycopg

    from brain.db import libpq_url

    url = _database_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")

    admin = libpq_url(url)
    scratch = _fresh(admin, SCRATCH_DATABASE)
    _migrate(url, SCRATCH_DATABASE, "stamp", "0027")
    _migrate(url, SCRATCH_DATABASE, "upgrade", "0029")

    with psycopg.connect(scratch, autocommit=True) as conn:
        yield conn

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}" WITH (FORCE)')


@pytest.fixture
def run_id(request: pytest.FixtureRequest) -> str:
    """A run id nothing else in this file writes. See the module docstring."""
    return str(request.node.name)


def sql_reach(
    conn: Any,
    parent: EntitlementSet,
    agent: EntitlementSet,
    subtask: EntitlementSet,
    at: datetime = AT,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT gate.delegated_reach(%s::jsonb, %s::jsonb, %s::jsonb, %s)",
        (doc(parent), doc(agent), doc(subtask), at),
    ).fetchone()
    assert row is not None
    return dict(row[0])


def shape(document: dict[str, Any]) -> tuple[Any, ...]:
    """A reach reduced to what it means, so two renderings of it can be compared.

    `not_after` is parsed rather than compared as text: pydantic writes UTC as `Z` and
    PostgreSQL writes it as an offset, and those are the same instant. Clauses are compared as
    a set because order and duplication carry no meaning in a conjunction.
    """
    bound = document.get("not_after")
    return (
        document["principal_id"],
        tuple(
            sorted(
                (
                    one["capability"]["value"],
                    tuple(sorted(json.dumps(c, sort_keys=True) for c in one["scope"]["clauses"])),
                )
                for one in document["grants"]
            )
        ),
        datetime.fromisoformat(bound) if bound else None,
    )


def insert(conn: Any, **row: Any) -> Any:
    columns = ", ".join(sorted(row))
    values = ", ".join(f"%({name})s" for name in sorted(row))
    returned = conn.execute(
        f"INSERT INTO {DELEGATION_RELATION} ({columns}) VALUES ({values}) RETURNING id",  # noqa: S608
        row,
    ).fetchone()
    return returned[0] if returned else None


# ------------------------------------------------------------------- the two are one answer
CHAINS: tuple[tuple[str, EntitlementSet, EntitlementSet, EntitlementSet], ...] = (
    (
        "a ceiling covering by wildcard keeps the concrete capability the parent held",
        reach("p:one", ("read:client.name", where(department="web"))),
        reach("ceiling:agent:a", ("read:client.*", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "each hop adds its clauses and the child ends up holding all three",
        reach("p:one", ("read:client.name", where(department="web"))),
        reach("ceiling:agent:a", ("read:client.name", where(region="apac"))),
        reach("subtask-ceiling:s", ("read:client.name", where(tier="gold"))),
    ),
    (
        "a capability no agent ceiling covers is gone from the child",
        reach("p:one", ("read:client.name", Scope()), ("read:invoice.total", Scope())),
        reach("ceiling:agent:a", ("read:client.name", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope()), ("read:invoice.*", Scope())),
    ),
    (
        "a capability no subtask ceiling covers is gone from the child",
        reach("p:one", ("read:client.name", Scope()), ("read:invoice.total", Scope())),
        reach("ceiling:agent:a", ("read:client.*", Scope()), ("read:invoice.*", Scope())),
        reach("subtask-ceiling:s", ("read:invoice.total", Scope())),
    ),
    (
        "an expired agent ceiling admits nothing, whatever it lists",
        reach("p:one", ("read:client.name", Scope())),
        reach("ceiling:agent:a", ("read:client.*", Scope()), not_after=ALREADY_OVER),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "an expired subtask ceiling admits nothing either",
        reach("p:one", ("read:client.name", Scope())),
        reach("ceiling:agent:a", ("read:client.*", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope()), not_after=ALREADY_OVER),
    ),
    (
        "the tightest of the three bounds is the one the child carries",
        reach("p:one", ("read:client.name", Scope()), not_after=LATER_STILL),
        reach("ceiling:agent:a", ("read:client.*", Scope()), not_after=STILL_TO_COME),
        reach("subtask-ceiling:s", ("read:client.*", Scope()), not_after=LATER_STILL),
    ),
    (
        "a ceiling holding one capability twice conjoins both of its scopes",
        reach("p:one", ("read:client.name", Scope())),
        reach(
            "ceiling:agent:a",
            ("read:client.*", where(region="apac")),
            ("read:client.name", where(tier="gold")),
        ),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "a parent holding nothing hands the child nothing",
        reach("p:one"),
        reach("ceiling:agent:a", ("read:client.*", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "a wildcard ceiling covers the fields under an entity and not the entity itself",
        reach("p:one", ("read:client", Scope()), ("read:client.name", Scope())),
        reach("ceiling:agent:a", ("read:client.*", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "a parent's wildcard is narrowed to the column an agent ceiling names",
        reach("p:one", ("read:client.*", where(department="web"))),
        reach("ceiling:agent:a", ("read:client.name", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "a parent's wildcard is narrowed to the column a subtask ceiling names",
        reach("p:one", ("read:client.*", where(department="web"))),
        reach("ceiling:agent:a", ("read:client.*", Scope())),
        reach("subtask-ceiling:s", ("read:client.hours_remaining", where(tier="gold"))),
    ),
    (
        "a parent holding a wildcard and a column under it keeps both scopes on the column",
        reach(
            "p:one",
            ("read:client.*", where(department="web")),
            ("read:client.name", where(tier="gold")),
        ),
        reach("ceiling:agent:a", ("read:client.name", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "a ceiling narrowing one column under its wildcard narrows a wildcard parent there too",
        reach("p:one", ("read:client.*", Scope())),
        reach(
            "ceiling:agent:a",
            ("read:client.*", where(department="web")),
            ("read:client.name", where(tier="gold")),
        ),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "wildcards at two depths narrow to the deeper one",
        reach("p:one", ("read:client.*", where(department="web"))),
        reach("ceiling:agent:a", ("read:client.billing.*", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
    (
        "a capability a ceiling names and the parent does not cover is not handed down",
        reach("p:one", ("read:client.name", Scope())),
        reach("ceiling:agent:a", ("read:client.name", Scope()), ("read:invoice.total", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope()), ("read:invoice.*", Scope())),
    ),
    (
        "an expired parent's wildcard is narrowed and carries its bound rather than being judged",
        reach("p:one", ("read:client.*", Scope()), not_after=ALREADY_OVER),
        reach("ceiling:agent:a", ("read:client.name", Scope())),
        reach("subtask-ceiling:s", ("read:client.*", Scope())),
    ),
)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("label", "parent", "agent", "subtask"), CHAINS, ids=[one[0] for one in CHAINS]
)
def test_the_reach_computed_in_sql_is_the_reach_python_computes(
    server: Any,
    label: str,
    parent: EntitlementSet,
    agent: EntitlementSet,
    subtask: EntitlementSet,
) -> None:
    """**The whole licence for a second implementation of the central rule.**

    CLAUDE.md forbids a second `intersect` because a copy drifts and the drifted copy is the
    one in production. The copy here is affordable only because it is measured against the
    original rather than trusted to agree with it, and this is that measurement: the same
    three sets folded by `EntitlementSet.intersect` twice over and by `gate.delegated_reach`
    once, compared by meaning.

    Seventeen cases, and each is a way the two could disagree without either looking wrong: a
    wildcard ceiling, a capability dropped at each hop, expiry on each side, the tighter of
    three bounds, one capability held twice by a ceiling, an empty parent, and an entity grant
    that must not confer the fields beneath it. The last seven were added on 2026-09-14 with
    the repair to `intersect`, and they are the wildcard held on the parent's side: narrowed to
    a column by either ceiling, kept with both scopes, narrowed by a ceiling's column grant under
    its wildcard, narrowed to a deeper wildcard, not handed a capability only a ceiling names,
    and carried rather than judged when the parent has lapsed.

    Delete this and the SQL is a second answer to who may see what, with nothing watching
    whether it is the same answer.
    """
    expected = parent.intersect(agent, AT).intersect(subtask, AT)
    computed = sql_reach(server, parent, agent, subtask)

    assert shape(computed) == shape(expected.model_dump(mode="json")), label
    # The order is not part of the meaning, and `shape` sorts it away. It is asserted anyway,
    # because `DELEGATED_REACH_SQL` claims to order grants as the Python fold does so a reader
    # diffing the two compares like with like, and a mutation reversing that order survived.
    assert [one["capability"]["value"] for one in computed["grants"]] == [
        one.capability.value for one in expected.grants
    ], label


@pytest.mark.needs_db
def test_a_parents_wildcard_reaches_the_column_a_ceiling_names_as_the_rule_says(
    server: Any,
) -> None:
    """**The comparison above could not have found the defect it shared, and did not.**

    Until 2026-09-14 `EntitlementSet.intersect` dropped a caller's wildcard whenever a ceiling
    named a column under it, and `gate.delegated_reach` was written as its mirror, so both
    computed nothing for this chain and the differential test compared two identical wrong
    answers. They also shared the permissive half: holding `read:client.*` in Web and
    `read:client.name` in gold, both handed the child the name column in gold clients of every
    department.

    So this one is compared against a reach written out here from the rule rather than computed
    by either implementation. The child holds the column, not the wildcard, under the parent's
    two scopes conjoined, which is what the parent reaches the column in by itself.

    Delete this and the SQL and the Python can drift together, which is the one kind of drift a
    differential test is blind to."""
    parent = reach(
        "p:one",
        ("read:client.*", where(department="web")),
        ("read:client.name", where(tier="gold")),
    )
    agent = reach("ceiling:agent:a", ("read:client.name", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    written_out = reach("p:one", ("read:client.name", where(department="web", tier="gold")))

    assert shape(sql_reach(server, parent, agent, subtask)) == shape(
        written_out.model_dump(mode="json")
    )


@pytest.mark.needs_db
def test_the_downgrade_writes_back_the_reach_0028_computed_and_the_upgrade_replaces_it() -> None:
    """**A downgrade nobody has run is a string**, and this one is a frozen copy of a function
    rather than a statement rendered from its owner, which is the shape that goes wrong quietly.

    One chain, asked after each step on a live database of its own: a parent holding
    `read:client.*` in Web, through an agent ceiling naming `read:client.name`. At `0029` the
    child reaches the column in Web. Downgraded to `0028` it reaches nothing, which is exactly
    what the function `0028` shipped computed and is what the code of `0028` expects the
    database to agree with. Upgraded again, the column is back. So the downgrade reverses the
    upgrade, the upgrade is not a no-op on a database that already ran `0028`, and neither
    direction is taken on trust.

    Delete this and `0029`'s downgrade can hold any function at all, including the corrected
    one, with every other test in this file green."""
    import psycopg

    from brain.db import libpq_url

    url = _database_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")

    admin = libpq_url(url)
    scratch = _fresh(admin, ROUND_TRIP_DATABASE)
    parent = reach("p:one", ("read:client.*", where(department="web")))
    agent = reach("ceiling:agent:a", ("read:client.name", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    written_out = reach("p:one", ("read:client.name", where(department="web")))
    narrowed = shape(written_out.model_dump(mode="json"))
    as_0028_computed = shape(reach("p:one").model_dump(mode="json"))

    seen: list[tuple[str, tuple[Any, ...]]] = []
    try:
        _migrate(url, ROUND_TRIP_DATABASE, "stamp", "0027")
        for verb, revision in (("upgrade", "0029"), ("downgrade", "0028"), ("upgrade", "0029")):
            _migrate(url, ROUND_TRIP_DATABASE, verb, revision)
            with psycopg.connect(scratch, autocommit=True) as conn:
                seen.append((revision, shape(sql_reach(conn, parent, agent, subtask))))
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{ROUND_TRIP_DATABASE}" WITH (FORCE)')

    assert narrowed != as_0028_computed, "the two states are the same, so this proves nothing"
    assert seen == [("0029", narrowed), ("0028", as_0028_computed), ("0029", narrowed)]


@pytest.mark.needs_db
def test_the_narrowing_migration_round_trips_the_refusals_on_a_live_database() -> None:
    """**`0033`'s downgrade is a frozen copy of a function, and a copy nobody ran is a string.**

    One question, asked after each step on a live database of its own: the child that kept a
    wildcard its parent only reached narrowly, against that parent. At `0033` it is refused.
    Downgraded to `0032` it is not, which is what the function that shipped before computed.
    Upgraded again it is refused. So the downgrade reverses the upgrade, and the upgrade is not a
    no-op on a database that ran the old body.

    The migrations between `0029` and `0032` are stamped rather than run. They build tables this
    function does not read, and what they need is not a condition of asking it anything.

    Delete this and the downgrade can hold any function at all, the corrected one included, with
    every other test in this file green."""
    import psycopg

    from brain.db import libpq_url

    url = _database_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")

    admin = libpq_url(url)
    scratch = _fresh(admin, ROUND_TRIP_DATABASE)
    parent = reach(
        "p:one",
        ("read:client.*", where(department="web")),
        ("read:client.name", where(tier="gold")),
    )
    child = reach("p:one", ("read:client.*", where(department="web")))

    seen: list[tuple[str, int]] = []
    try:
        _migrate(url, ROUND_TRIP_DATABASE, "stamp", "0027")
        _migrate(url, ROUND_TRIP_DATABASE, "upgrade", "0029")
        _migrate(url, ROUND_TRIP_DATABASE, "stamp", "0032")
        for verb, revision in (("upgrade", "0033"), ("downgrade", "0032"), ("upgrade", "0033")):
            _migrate(url, ROUND_TRIP_DATABASE, verb, revision)
            with psycopg.connect(scratch, autocommit=True) as conn:
                row = conn.execute(
                    "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)",
                    (doc(child), doc(parent)),
                ).fetchone()
                assert row is not None
                seen.append((revision, len(row[0])))
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{ROUND_TRIP_DATABASE}" WITH (FORCE)')

    assert seen == [("0033", 1), ("0032", 0), ("0033", 1)]


@pytest.mark.needs_db
def test_containment_in_the_intersection_is_containment_in_each_side_since_both_sides_are_asked(
    server: Any,
) -> None:
    """**A rejection this file used to demonstrate, and why it no longer holds.**

    Until 2026-09-15 `gate.narrowing_refusals` matched grants on the capability's own value, so a
    child holding `read:client.name` was refused against a ceiling holding only `read:client.*`,
    and this test showed that three direct containment tests could not stand in for the
    intersection. Containment is now asked of both sides through `gate.entitlement_scope_for`,
    which is exact, so the reading against the intersection and the reading against one side
    agree, as set containment says they must. `delegated_reach` is still what the trigger compares
    a row against, and nothing here argues for removing it.

    Delete this and the SQL can go back to matching strings without a test noticing, which
    refuses every legitimate delegation through a wildcard ceiling."""
    parent = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    child = parent.intersect(agent, AT).intersect(subtask, AT)

    against_the_intersection = server.execute(
        "SELECT gate.narrowing_refusals(%s::jsonb, gate.delegated_reach("
        "%s::jsonb, %s::jsonb, %s::jsonb, %s))",
        (doc(child), doc(parent), doc(agent), doc(subtask), AT),
    ).fetchone()
    against_the_agent = server.execute(
        "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)", (doc(child), doc(agent))
    ).fetchone()

    assert against_the_intersection[0] == []
    # The agent's ceiling is written under its own principal, so the principal finding stands;
    # what this asserts is that no finding about reach does.
    assert [one.split(" ", 4)[:4] for one in against_the_agent[0]] == [
        ["the", "child", "names", "principal"]
    ]


@pytest.mark.needs_db
def test_a_child_keeping_a_wildcard_its_parent_reaches_only_under_a_narrower_grant_is_refused(
    server: Any,
) -> None:
    """**The widening the string comparison let through, measured before it was fixed.**

    The parent holds `read:client.*` in Web and `read:client.name` in gold, so it reaches the name
    column only in Web's gold clients. A child holding `read:client.*` in Web alone matched a
    parent grant string for string and clause for clause, and reaches the name column in every
    tier of Web. Until 2026-09-15 the database returned no refusal for it. The Python original is
    asked the same question, so the two cannot disagree about this case.

    Delete this and the database check admits a delegation that reads rows its parent could not."""
    parent = reach(
        "p:one",
        ("read:client.*", where(department="web")),
        ("read:client.name", where(tier="gold")),
    )
    child = reach("p:one", ("read:client.*", where(department="web")))

    refused = server.execute(
        "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)", (doc(child), doc(parent))
    ).fetchone()

    assert refused[0] != []
    assert [one.split(" ", 1)[0] for one in refused[0]] == ["read:client.name"]
    assert narrowing_refusals(child, parent) != ()


@pytest.mark.needs_db
def test_a_child_narrowed_to_one_column_of_its_parents_wildcard_is_not_refused(
    server: Any,
) -> None:
    """The positive sibling. A parent holding `read:client.*` in Web and a child holding only
    `read:client.hours_remaining` in Web is a narrowing, and matching strings refused it, because
    no parent grant carries that capability's own value.

    Delete this and a check refusing every column narrowed from a wildcard passes the test
    above."""
    parent = reach("p:one", ("read:client.*", where(department="web")))
    child = reach("p:one", ("read:client.hours_remaining", where(department="web")))

    refused = server.execute(
        "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)", (doc(child), doc(parent))
    ).fetchone()

    assert refused[0] == []
    assert narrowing_refusals(child, parent) == ()


#: Grants whose capabilities cover one another and whose scopes overlap, so that every way two
#: sets of grants can relate occurs among the pairs of sets drawn from it.
POOL: tuple[tuple[str, Scope], ...] = tuple(
    (capability, scope)
    for capability in ("read:client.*", "read:client.name", "read:client.hours_remaining")
    for scope in (Scope(), where(department="web"), where(tier="gold"))
)


@pytest.mark.needs_db
def test_the_database_refuses_exactly_what_the_python_check_refuses(server: Any) -> None:
    """**The database copy and the Python original agree on every pair of sets from the pool.**

    Every set of at most two grants drawn from `POOL` is asked about as a child and as a parent,
    which is 46 sets and 2,116 pairs, and the number of refusals the database gives must equal the
    number the Python original gives. Counts rather than sentences, because the two phrase a
    missing capability differently, and a count is what the trigger's decision rests on. Expiry
    and principal are the same throughout, so every refusal here is about reach.

    Delete this and the two copies of the containment rule can drift apart, and the copy that
    drifts is the one the trigger runs."""
    sets = [
        reach("p:one", *combination)
        for size in range(3)
        for combination in itertools.combinations(POOL, size)
    ]
    disagreements: list[tuple[str, str, int, int]] = []
    for child, parent in itertools.product(sets, repeat=2):
        row = server.execute(
            "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)", (doc(child), doc(parent))
        ).fetchone()
        in_database = len(row[0])
        in_python = len(narrowing_refusals(child, parent))
        if in_database != in_python:
            disagreements.append((doc(child), doc(parent), in_database, in_python))

    assert len(sets) == 46
    assert disagreements == [], disagreements[:3]


@pytest.mark.needs_db
def test_a_child_that_dropped_a_clause_is_refused_whatever_its_own_expiry(server: Any) -> None:
    """**Expiry is set aside when containment is asked, on the child's side.**

    The child here expires before its parent, so the time-bound check has nothing to say, and it
    dropped the parent's department clause, so it reaches rows the parent could not. Asked with
    the child's expiry left in, `gate.entitlement_scope_for` finds the child reaching nothing at
    all, and a child that reaches nothing contains no widening. Expiry belongs to the fourth
    check, and the reach question has to be asked as though the child were live.

    Delete this and any expiring delegation can drop a clause unrefused, which is every
    delegation cut from a contractor or a break-glass grant."""
    parent = reach("p:one", ("read:client.name", where(department="web")), not_after=LATER_STILL)
    child = reach("p:one", ("read:client.name", Scope()), not_after=STILL_TO_COME)

    refused = server.execute(
        "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)", (doc(child), doc(parent))
    ).fetchone()

    assert [one.split(" ", 1)[0] for one in refused[0]] == ["read:client.name"]
    assert len(narrowing_refusals(child, parent)) == 1


@pytest.mark.needs_db
def test_a_child_narrowed_from_an_expiring_parent_is_not_refused(server: Any) -> None:
    """**Expiry is set aside when containment is asked, on the parent's side.** The positive
    sibling of the test above.

    The parent expires, the child expires no later and keeps every clause, and it holds one column
    of the parent's wildcard: a narrowing on every axis. Asked with the parent's expiry left in,
    the parent reaches nothing, and every capability the child holds is reported as held by no
    grant of the parent's.

    Delete this and every legitimate delegation from a grant with an end date is refused."""
    parent = reach("p:one", ("read:client.*", where(department="web")), not_after=LATER_STILL)
    child = reach("p:one", ("read:client.name", where(department="web")), not_after=STILL_TO_COME)

    refused = server.execute(
        "SELECT gate.narrowing_refusals(%s::jsonb, %s::jsonb)", (doc(child), doc(parent))
    ).fetchone()

    assert refused[0] == []
    assert narrowing_refusals(child, parent) == ()


# ------------------------------------------------------------------- what the trigger does
@pytest.mark.needs_db
def test_a_root_delegation_that_narrows_is_recorded(server: Any, run_id: str) -> None:
    """The positive case, without which every refusal below is satisfied by a trigger that
    refuses everything.

    Delete this and a trigger raising on all input passes the rest of this file.
    """
    parent = reach("p:one", ("read:client.name", where(department="web")))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))

    written = insert(
        server,
        run_id=run_id,
        child_id="child",
        parent_grants=doc(parent),
        agent_ceiling=doc(agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(parent.intersect(agent, AT).intersect(subtask, AT)),
        decided_at=AT,
    )

    assert written is not None


@pytest.mark.needs_db
def test_a_child_claiming_a_capability_the_fold_removed_is_refused(
    server: Any, run_id: str
) -> None:
    """The plainest widening there is: a capability no ceiling on the path admits.

    Delete this and the trigger's central refusal has no test, which is the state every other
    guard in this repository has been found in.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", Scope()), ("read:invoice.total", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_grants=doc(parent),
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(subtask),
            child_grants=doc(parent),
            decided_at=AT,
        )

    assert "read:invoice.total" in str(raised.value)
    assert raised.value.sqlstate == DELEGATION_REFUSED_SQLSTATE


@pytest.mark.needs_db
def test_a_child_that_dropped_a_scope_clause_is_refused(server: Any, run_id: str) -> None:
    """Widening by subtraction, which is the half a capability list never shows.

    A child holding the same capability as the fold produced, with one clause of the scope
    missing, sees every row the parent could plus the rows that clause excluded. Scopes
    compose by conjunction only, so fewer clauses is strictly wider.

    Delete this and a delegation can keep the capability and lose the department.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", where(department="web")))
    agent = reach("ceiling:agent:a", ("read:client.*", where(region="apac")))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    widened = reach("p:one", ("read:client.name", where(department="web")))

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_grants=doc(parent),
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(subtask),
            child_grants=doc(widened),
            decided_at=AT,
        )

    assert "without every clause" in str(raised.value)


@pytest.mark.needs_db
def test_a_child_outliving_the_reach_it_was_cut_from_is_refused(server: Any, run_id: str) -> None:
    """The third way a row widens, and the one a capability comparison cannot see.

    Delete this and a delegated run keeps its reach after the grant it came from has lapsed.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", Scope()), not_after=STILL_TO_COME)
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    outliving = reach("p:one", ("read:client.name", Scope()), not_after=LATER_STILL)

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_grants=doc(parent),
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(subtask),
            child_grants=doc(outliving),
            decided_at=AT,
        )

    assert "outliving the reach it came from" in str(raised.value)


@pytest.mark.needs_db
def test_a_child_naming_a_different_principal_is_refused(server: Any, run_id: str) -> None:
    """Narrowing keeps the caller's id, so a row naming somebody else was not produced by it.

    Two people with identical grants share an entitlement hash by design, which is what makes
    the cache key work, so the hash cannot answer this and the principal is compared directly.

    Delete this and a delegation can be recorded against a principal who never asked.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    somebody_else = reach("p:two", ("read:client.name", Scope()))

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_grants=doc(parent),
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(subtask),
            child_grants=doc(somebody_else),
            decided_at=AT,
        )

    assert "narrowing keeps the caller" in str(raised.value)


# --------------------------------------------- the row the application could not have caught
@pytest.mark.needs_db
def test_a_row_below_the_root_cannot_supply_its_own_parent_reach(server: Any, run_id: str) -> None:
    """**The constraint that makes this trigger worth more than the same check in Python.**

    A check written beside the insert reads the same supplied value as the insert does, so an
    inserter in control of its own row satisfies it by writing a wide `parent_grants`. Here
    `parent_id` and `parent_grants` are mutually exclusive, so a row below the root has no
    column in which to state its own left-hand side.

    Delete this and every refusal in this file becomes arithmetic the inserter could have done
    for itself.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    root = insert(
        server,
        run_id=run_id,
        child_id="root",
        parent_grants=doc(parent),
        agent_ceiling=doc(agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(parent.intersect(agent, AT).intersect(subtask, AT)),
        decided_at=AT,
    )

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_id=root,
            parent_grants=doc(parent),
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(subtask),
            child_grants=doc(parent),
            decided_at=AT,
        )

    assert "one_source_of_the_parent_reach" in str(raised.value)


@pytest.mark.needs_db
def test_a_grandchild_is_bounded_by_what_its_parent_recorded(server: Any, run_id: str) -> None:
    """**The refusal nothing in the application could make.**

    The root row narrows honestly and records a reach of one capability in one department. The
    child then claims a reach that is a perfectly good subset of the *root's* inputs and is not
    a subset of what the row above it recorded. Every column of the child row is the inserter's
    own, and it is still refused, because the left-hand side of its intersection is read out of
    the parent row rather than out of the insert.

    Delete this and the trigger degenerates into a restatement of `narrowing_refusals`, which
    the Python path has already run.
    """
    import psycopg

    asker = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", where(department="web")))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    recorded = asker.intersect(agent, AT).intersect(subtask, AT)
    root = insert(
        server,
        run_id=run_id,
        child_id="root",
        parent_grants=doc(asker),
        agent_ceiling=doc(agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(recorded),
        decided_at=AT,
    )

    # Narrower than the asker's own reach, and wider than the row above it: the department
    # clause the first hop added is gone.
    wider_than_the_parent = reach("p:one", ("read:client.name", Scope()))

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="grandchild",
            parent_id=root,
            agent_ceiling=doc(reach("ceiling:agent:b", ("read:client.*", Scope()))),
            subtask_ceiling=doc(subtask),
            child_grants=doc(wider_than_the_parent),
            decided_at=AT,
        )

    assert "without every clause" in str(raised.value)


@pytest.mark.needs_db
def test_a_grandchild_that_narrows_from_what_its_parent_recorded_is_kept(
    server: Any, run_id: str
) -> None:
    """The positive half of the chain check.

    A child that really is contained in the reach its parent recorded goes in. Without this,
    the test above passes on a trigger that refuses every row carrying a `parent_id`, which
    would be a chain check that had stopped allowing chains.

    Delete this and the chain rule is tested only by its refusals.
    """
    asker = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", where(department="web")))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    recorded = asker.intersect(agent, AT).intersect(subtask, AT)
    root = insert(
        server,
        run_id=run_id,
        child_id="root",
        parent_grants=doc(asker),
        agent_ceiling=doc(agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(recorded),
        decided_at=AT,
    )
    second_agent = reach("ceiling:agent:b", ("read:client.*", where(region="apac")))

    written = insert(
        server,
        run_id=run_id,
        child_id="grandchild",
        parent_id=root,
        agent_ceiling=doc(second_agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(recorded.intersect(second_agent, AT).intersect(subtask, AT)),
        decided_at=AT,
    )

    assert written is not None


@pytest.mark.needs_db
def test_a_delegation_row_cannot_be_edited_after_it_was_checked(server: Any, run_id: str) -> None:
    """Without this, widening is a two-statement job.

    Insert a narrow parent, insert the children that are measured against it, then widen the
    parent. Every individual statement passes a check that only looks at inserts. The trigger
    fires on UPDATE in order to have somewhere to refuse it.

    Delete this and the chain check above holds only until somebody edits the row it rests on.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    insert(
        server,
        run_id=run_id,
        child_id="root",
        parent_grants=doc(parent),
        agent_ceiling=doc(agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(parent.intersect(agent, AT).intersect(subtask, AT)),
        decided_at=AT,
    )

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        server.execute(
            f"UPDATE {DELEGATION_RELATION} SET child_grants = %s::jsonb "  # noqa: S608
            "WHERE run_id = %s",
            (doc(parent), run_id),
        )

    assert "is not edited afterwards" in str(raised.value)


@pytest.mark.needs_db
def test_a_child_decided_before_the_delegation_it_descends_from_is_refused(
    server: Any, run_id: str
) -> None:
    """A chain that runs backwards did not happen, and the timestamps are how an auditor
    reconstructs the order of one.

    `decided_at` is also the instant every ceiling's expiry is judged at, so a row free to
    claim any instant it likes is a row that can pick one where a lapsed ceiling was still
    live.

    Delete this and a chain can be assembled in any order after the fact.
    """
    import psycopg

    parent = reach("p:one", ("read:client.name", Scope()))
    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    subtask = reach("subtask-ceiling:s", ("read:client.*", Scope()))
    recorded = parent.intersect(agent, AT).intersect(subtask, AT)
    root = insert(
        server,
        run_id=run_id,
        child_id="root",
        parent_grants=doc(parent),
        agent_ceiling=doc(agent),
        subtask_ceiling=doc(subtask),
        child_grants=doc(recorded),
        decided_at=AT,
    )

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="grandchild",
            parent_id=root,
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(subtask),
            child_grants=doc(recorded),
            decided_at=ALREADY_OVER,
        )

    assert "decided before the delegation it descends from" in str(raised.value)


@pytest.mark.needs_db
def test_a_reach_the_check_cannot_read_is_refused_rather_than_admitted(
    server: Any, run_id: str
) -> None:
    """**The fail-open, closed.**

    The SQL reads its fields by name out of jsonb. A document that does not carry them reads
    as a reach holding nothing, and a child holding nothing is a subset of nothing, so the
    trigger would admit every row while checking none. Refusing a document it cannot read is
    what turns a renamed field into a refusal on the first insert instead of a silent
    disabling of the whole check.

    Delete this and the check survives a rename of `grants` with every test still green.
    """
    import psycopg

    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))
    renamed = json.dumps({"principal_id": "p:one", "entitlements": [], "not_after": None})

    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_grants=renamed,
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(agent),
            child_grants=renamed,
            decided_at=AT,
        )

    assert "carries no grants array" in str(raised.value)


@pytest.mark.needs_db
def test_a_delegation_naming_a_parent_that_is_not_there_is_refused(
    server: Any, run_id: str
) -> None:
    """A row whose bound does not exist is a row with no bound.

    The foreign key refuses an id no row carries and the trigger refuses it too, because the
    trigger reads the parent before the constraint is checked and a NULL reach read there
    would reach the fold rather than a refusal. Either refusal is correct and the test accepts
    both, since which one arrives first is PostgreSQL's business and not this module's.

    Delete this and a missing parent falls through to a reach nothing bounded.
    """
    import psycopg

    agent = reach("ceiling:agent:a", ("read:client.*", Scope()))

    with pytest.raises(psycopg.errors.Error) as raised:
        insert(
            server,
            run_id=run_id,
            child_id="child",
            parent_id="00000000-0000-0000-0000-000000000000",
            agent_ceiling=doc(agent),
            subtask_ceiling=doc(agent),
            child_grants=doc(reach("p:one")),
            decided_at=AT,
        )

    assert raised.value.sqlstate in {"23503", DELEGATION_REFUSED_SQLSTATE}


# ---------------------------------------------------------- what the catalogue is asked
@pytest.mark.needs_db
def test_the_trigger_is_attached_for_insert_and_for_update(server: Any) -> None:
    """Asked of the catalogue rather than of the migration having run without raising.

    A trigger declared `BEFORE INSERT` alone leaves the edit path open with the UPDATE refusal
    written and unreachable, which is this repository's commonest defect wearing a different
    hat, and the test above it would still pass because an UPDATE nothing watches raises
    nothing either.

    Delete this and the events the trigger fires on stop being a decision.
    """
    row = server.execute(
        "SELECT t.tgtype::int FROM pg_trigger t "
        "JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s AND t.tgname = %s",
        (DELEGATION_SCHEMA, DELEGATION_TABLE, "delegation_narrows"),
    ).fetchone()

    assert row is not None, "the migration created no trigger on the delegation table"
    kind = int(row[0])
    assert kind & 1, "the trigger is not a row-level trigger, so it sees no NEW"
    assert kind & 2, "the trigger does not fire BEFORE, so a refused row is written first"
    assert kind & 4, "the trigger does not fire on INSERT"
    assert kind & 16, "the trigger does not fire on UPDATE, so a row can be edited after it"


@pytest.mark.needs_db
def test_row_level_security_is_on_and_no_policy_hands_a_reader_a_reach(server: Any) -> None:
    """Every new table enables row-level security, and this one grants nothing back.

    A delegation row is a copy of somebody's permissions. Nothing in the application reads one,
    so there is a policy for INSERT and none for SELECT: a read policy of `USING (true)`
    written in advance of a screen that wants one would grant back exactly what enabling
    row-level security denied, which is what the queue driver's tables record about themselves.

    Delete this and the sweep still passes on a table whose read policy admits everything.
    """
    secured = server.execute(
        "SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s",
        (DELEGATION_SCHEMA, DELEGATION_TABLE),
    ).fetchone()
    policies = server.execute(
        "SELECT p.polname, p.polcmd FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s",
        (DELEGATION_SCHEMA, DELEGATION_TABLE),
    ).fetchall()
    privileges = server.execute(
        "SELECT privilege_type FROM information_schema.table_privileges "
        "WHERE table_schema = %s AND table_name = %s AND grantee = 'brain_app'",
        (DELEGATION_SCHEMA, DELEGATION_TABLE),
    ).fetchall()

    assert secured is not None and secured[0] is True
    assert [(name, command) for name, command in policies] == [("delegation_writable", "a")]
    assert {one[0] for one in privileges} == {"INSERT"}
