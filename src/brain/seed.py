"""Load the demo company into a database.

Refuses to run against a database that holds real rows. Seeding is destructive by nature -
it truncates what it owns - and "I ran the seed against production" is a mistake that
should be impossible rather than merely discouraged.

**This used to import `tests.fixtures.company` and that was an install step reading a Verz
artefact.** The comment beside the import said tests are not on the path in a deployed
image, which is true, and the consequence was never followed through: `make seed` is listed
in the Makefile, `make reset` calls it, and neither can run on a client's install because
the rows it wants live in a directory the image does not contain. What it would have written
if it could is worse than the failure. The fixture is Verz's own org chart, down to the
departments and the name of the person who owns the company, and every restricted field in
it holds a canary token that exists to make a permission test fail. Seeding a client with
that is a Verz value in their database on day one and a copy of the product's test
apparatus on their screen.

So the rows come from `brain.demo` now, which is product rather than test apparatus, and the
fixture goes back to being what it is for. The two artefacts are held apart by
`tests/unit/test_demo.py` rather than by anybody remembering.

**Additive, not destructive, for the tables the demo adds.** `OWNED` is unchanged and still
means "replaced", which is what the production guard is written against. The demo's rows are
inserted with `ON CONFLICT DO NOTHING` and are removable by identifier, so loading the demo
cannot overwrite a row somebody else wrote and removing it cannot reach one. See
`WRITING_IS_NOT_OWNING`.

Task ids: M0.4.4, M0.4.5, M41.2.3
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import structlog
from sqlalchemy import create_engine, text

from brain import demo
from brain.db import SCHEMAS, normalise_database_url

log = structlog.get_logger()

#: Tables this command owns and will replace. Anything else is left alone.
OWNED = ("auth.principal", "gate.capability_grant")

#: Tables the demo writes into. A superset of `OWNED`, and the difference is the point.
WRITES = demo.TABLES

#: Why writing into a table is not the same as owning it.
WRITING_IS_NOT_OWNING = (
    "OWNED is the list `looks_like_production` treats as disposable, so widening it to cover "
    "the demo's tables would tell the guard that rows in `proj.record` are safe to ignore, "
    "and `proj.record` is where a real client's projected records live. The demo therefore "
    "adds rather than replaces: every insert carries ON CONFLICT DO NOTHING and every row it "
    "writes carries the demo prefix, so it cannot overwrite something somebody else wrote and "
    "removing it cannot reach one either."
)

#: What an ordinary Postgres identifier looks like. A name that does not match is reported
#: rather than interpolated into a query.
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

#: The conflict targets, per table, so an insert can be repeated. Written out rather than
#: read from `information_schema`, because a key discovered at run time is a key that changes
#: what the statement does when somebody adds a constraint.
CONFLICT_KEYS: dict[str, tuple[str, ...]] = {
    "auth.principal": ("id",),
    # No natural key. A grant row is identified by its generated uuid, so a repeated load
    # would insert a second identical grant; the removal below is what makes that reversible,
    # and `install` refuses to run twice over a database that already holds the demo.
    "gate.capability_grant": (),
    "proj.record": ("source", "entity", "source_id"),
    "gate.fast_path_rule": ("rule_id",),
}

#: The column each table's demo rows are removed by. One column per table, and every value in
#: it carries `brain.demo.DEMO_PREFIX`, which is what makes removal a predicate rather than an
#: inventory. `gate.capability_grant` is removed by the principal it was granted to.
#: Tables a trigger writes on the demo's behalf, and the column naming the demo's row.
#:
#: **Found by CI on 2026-09-07, and it could not have been found here.** Inserting a
#: capability grant fires `gate.bump_grants_version`, which writes a `gate.grants_version` row
#: keyed on the principal. The demo never declares that row, so removal never deleted it, and
#: its foreign key to `auth.principal` is RESTRICT: deleting the demo's principals came back
#: `update or delete on table "principal" violates RESTRICT setting of foreign key constraint
#: "fk_grants_version_principal_id_principal"`.
#:
#: A laptop with no PostgreSQL enforces no foreign key and fires no trigger, so every test
#: here passed while the demo could not actually be removed. That matters more than the bug:
#: `brain.demo.A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA` is the argument for having a
#: demo at all, and it was false in the one place it is checked.
#:
#: Cleared before the ordinary walk rather than added to `demo.TABLES`, because these are not
#: rows the demo wrote and listing them there would make `demo_rows` disagree with itself.
TRIGGER_WRITTEN: dict[str, str] = {
    "gate.grants_version": "principal_id",
}

REMOVAL_KEYS: dict[str, str] = {
    "auth.principal": "id",
    "gate.capability_grant": "principal_id",
    "proj.record": "source_id",
    "gate.fast_path_rule": "rule_id",
}


def _seed_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The principals and grants the demo company holds.

    Kept as a pair for the two callers that read it that way. Everything the demo writes is
    in `brain.demo.demo_rows`; these two tables are the ones this command has owned since it
    was written, and they are the ones its production guard is phrased against.
    """
    rows = demo.demo_rows()
    return list(rows["auth.principal"]), list(rows["gate.capability_grant"])


def looks_like_production(url: str) -> tuple[bool, str]:
    """A crude but honest guard. Any row in a table we do not own means stop.

    Deliberately not a check on the hostname or the database name. Those are exactly the
    things that get copied into a staging config and then lie.

    **Two signals, and either one refuses.** This used to read `n_live_tup` alone, which is
    a statistics estimate rather than a count: it is zero for a freshly restored database
    until autovacuum or ANALYZE has run, so a production dump restored ten minutes ago read
    as empty and this function said the database was safe to truncate. The exact probe fixes
    that. The estimate is kept beside it rather than replaced, because the exact probe has
    its own blind spot: it runs as whoever is connected, and row-level security can hide
    rows from that role while the statistics still count them. Neither signal covers the
    other, so both run and either refuses.

    It also used to check seven schemas while nine exist. `ops` was missing, and so was
    `obs`, which holds the audit ledger. Truncating that is the one thing here that cannot
    be undone by re-running the seeder.
    """
    engine = create_engine(normalise_database_url(url), poolclass=None)
    # Interpolated below, and safe because it is built from a constant in this repository.
    schema_list = ", ".join(f"'{name}'" for name in sorted(SCHEMAS))
    found: dict[str, str] = {}
    list_tables = (
        "SELECT table_schema, table_name FROM information_schema.tables "  # noqa: S608
        f"WHERE table_schema IN ({schema_list}) AND table_type = 'BASE TABLE'"
    )
    count_estimates = (
        "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables "  # noqa: S608
        f"WHERE schemaname IN ({schema_list}) AND n_live_tup > 0"
    )
    try:
        with engine.connect() as conn:
            for schema, table in conn.execute(text(list_tables)).all():
                qualified = f"{schema}.{table}"
                if qualified in OWNED:
                    continue
                if not _IDENTIFIER_RE.match(schema) or not _IDENTIFIER_RE.match(table):
                    # A table name is not a literal just because the database supplied it.
                    # Anything that cannot be an ordinary lowercase identifier is reported
                    # rather than interpolated. Refusing to seed is the safe outcome, and a
                    # name that odd is worth a person looking at anyway.
                    found[qualified] = "name is not an ordinary identifier"
                    continue
                # Exact, and stops at the first row. `count(*)` would read the whole table
                # for an answer that only needs to be "any". The identifiers are validated
                # immediately above, which is what makes this interpolation safe.
                probe = f'SELECT 1 FROM "{schema}"."{table}" LIMIT 1'  # noqa: S608
                if conn.execute(text(probe)).first():
                    found[qualified] = "holds rows"

            for schema, table, estimate in conn.execute(text(count_estimates)).all():
                qualified = f"{schema}.{table}"
                if qualified not in OWNED:
                    found.setdefault(qualified, f"~{estimate} rows by statistics")
    finally:
        engine.dispose()

    if found:
        listed = ", ".join(f"{t} ({why})" for t, why in sorted(found.items())[:5])
        return True, f"database holds rows this command does not own: {listed}"
    return False, ""


class Executor(Protocol):
    """What the statements below are run against.

    A protocol rather than a `Connection`, for the reason `brain.ops.limits` holds no client:
    the interesting cases here are the statement that is built wrongly and the table that is
    written in the wrong order, and neither is testable through a module that opens a socket.
    """

    def execute(self, statement: Any, parameters: Any = None, /) -> Any:
        """Run one statement."""
        ...


def insert_statement(table: str, columns: Sequence[str]) -> str:
    """One parameterised INSERT, repeatable.

    The table name and the column names are interpolated and the values never are. Both come
    from `brain.demo`, which is a module in this repository rather than anything a caller
    supplies, and both are checked against `_IDENTIFIER_RE` before they get here.

    `ON CONFLICT DO NOTHING` rather than an upsert. An upsert would let a second load
    overwrite a row a client had edited, which is the one thing a demo must not be able to
    do; doing nothing means a repeated load is a no-op and an edited demo row stays edited.
    """
    schema, _, name = table.partition(".")
    for part in (schema, name, *columns):
        if not _IDENTIFIER_RE.match(part):
            msg = f"{part!r} is not an ordinary identifier and is not going into a statement"
            raise ValueError(msg)
    placeholders = ", ".join(f":{one}" for one in columns)
    keys = CONFLICT_KEYS[table]
    conflict = f" ON CONFLICT ({', '.join(keys)}) DO NOTHING" if keys else " ON CONFLICT DO NOTHING"
    return (
        f'INSERT INTO "{schema}"."{name}" ({", ".join(columns)}) '  # noqa: S608
        f"VALUES ({placeholders}){conflict}"
    )


def _bindable(row: Mapping[str, Any]) -> dict[str, Any]:
    """One row with its JSON columns serialised.

    `proj.record.fields` is a mapping and `gate.capability_grant.scope` is already a JSON
    string, and psycopg will not adapt a dict to `jsonb` on its own. Serialising here rather
    than in `brain.demo` keeps the data module free of any opinion about a driver.
    """
    return {
        key: json.dumps(value) if isinstance(value, dict) else value for key, value in row.items()
    }


def install(executor: Executor) -> dict[str, int]:
    """Write the demo company, table by table, in the order `brain.demo.TABLES` gives.

    The order is the demo's rather than this module's, because it is a fact about the rows:
    a grant carries a foreign key to a principal, so principals go first. Restating it here
    would be a second ordering to keep in step with the first.

    Returns what was attempted per table rather than what landed. A conflict clause means the
    database is entitled to write fewer rows than were offered, and reporting a count read
    back from the driver as though it were the demo's size would make a repeat load look like
    an empty demo.
    """
    written: dict[str, int] = {}
    for table, rows in demo.demo_rows().items():
        if not rows:
            written[table] = 0
            continue
        statement = insert_statement(table, tuple(rows[0]))
        executor.execute(text(statement), [_bindable(one) for one in rows])
        written[table] = len(rows)
    return written


def remove(executor: Executor) -> dict[str, int]:
    """Delete the demo company, and nothing else, in the reverse of the order it was written.

    Reverse order because the foreign key runs the other way: deleting principals first would
    be refused while their grants still point at them. Before any of it, the rows a trigger
    wrote on the demo's behalf, which the demo does not know it created; see
    `TRIGGER_WRITTEN`.

    Every statement is bounded by an explicit list of the identifiers `brain.demo` declares,
    not by a prefix match. A prefix match also catches a real person a client happened to give
    a matching identifier, and the one occasion that matters is the occasion somebody runs
    this against data they meant to keep. See
    `brain.demo.A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA`.
    """
    identifiers = set(demo.demo_identifiers())
    removed: dict[str, int] = {}

    # What a trigger wrote on the demo's behalf, first. See `TRIGGER_WRITTEN`.
    principals = sorted({str(one["id"]) for one in demo.principal_rows()} & identifiers)
    for table, column in TRIGGER_WRITTEN.items():
        schema, _, name = table.partition(".")
        for part in (schema, name, column):
            if not _IDENTIFIER_RE.match(part):
                msg = f"{part!r} is not an ordinary identifier"
                raise ValueError(msg)
        statement = f'DELETE FROM "{schema}"."{name}" WHERE {column} = ANY(:targets)'  # noqa: S608
        executor.execute(text(statement), {"targets": principals})
        removed[table] = len(principals)

    for table in reversed(demo.TABLES):
        schema, _, name = table.partition(".")
        column = REMOVAL_KEYS[table]
        for part in (schema, name, column):
            if not _IDENTIFIER_RE.match(part):
                msg = f"{part!r} is not an ordinary identifier"
                raise ValueError(msg)
        rows = demo.demo_rows()[table]
        targets = sorted({str(one[column]) for one in rows} & identifiers)
        statement = f'DELETE FROM "{schema}"."{name}" WHERE {column} = ANY(:targets)'  # noqa: S608
        executor.execute(text(statement), {"targets": targets})
        removed[table] = len(targets)
    return removed


#: What is read back to answer one question. Written out rather than `SELECT *`, so a column
#: added to either table is inert until somebody puts it here, which is the rule
#: `brain.gate.fast_lane.RULE_FIELDS` states about the same table.
_READ_RULES = (
    "SELECT rule_id, template, slot, source, entity, match_field, answer_field "
    "FROM gate.fast_path_rule WHERE deleted_at IS NULL"
)
_READ_RECORDS = (
    "SELECT entity, source_id, fields FROM proj.record "
    "WHERE source = :source AND deleted_at IS NULL"
)


def ask(executor: Executor, question: str) -> str | None:
    """Answer one question from what is actually in the database.

    This exists for the install to be provable rather than describable. An install that has
    migrated, seeded and reported success has still not been shown to answer anything, and
    the gap between those two is where every one of this repository's install bugs has lived:
    a Dockerfile that never copied the migrations, a volume path that only fails on start, a
    seed importing a directory the image does not contain.

    The rows come from here and the answer comes from `brain.demo.answer`, which has no
    connection and can therefore be tested against the case that matters. What this function
    adds is that the rows are the ones a fresh install really holds.
    """
    rules = [dict(one) for one in executor.execute(text(_READ_RULES)).mappings().all()]
    records = [
        dict(one)
        for one in executor.execute(text(_READ_RECORDS), {"source": demo.DEMO_SOURCE})
        .mappings()
        .all()
    ]
    return demo.answer(question, rules=rules, records=records)


def smoke(executor: Executor) -> tuple[str, str | None, str]:
    """Ask the demo its own first question and say what the answer should have been.

    Returns the question, what the database answered, and what `brain.demo` declared. The
    expected value is derived from the module rather than written into a CI step, because a
    literal in a workflow is a second copy of the demo that nothing keeps in step, and the
    direction it drifts is the workflow going on asserting a value the demo no longer holds.

    This is a comparison between two different things and not a constant against itself: the
    left side came out of the database through the fast lane's matcher, and the right side is
    what the seed said it was going to write. An install that migrated and did not seed
    answers nothing and fails here, which is the case this exists for.
    """
    client = next(one for one in demo.build_records() if one.entity == "client")
    rule = next(one for one in demo.build_rules() if one.entity == "client")
    question = rule.template.format(**{rule.slot: client.fields[rule.match_field]})
    return question, ask(executor, question), client.fields[rule.answer_field]


def seed(url: str, *, force: bool = False) -> int:
    risky, why = looks_like_production(url)
    if risky and not force:
        log.error("refusing to seed", reason=why)
        print(f"REFUSED: {why}", file=sys.stderr)
        print("Pass --force only if you are certain this database is disposable.", file=sys.stderr)
        return 1

    gaps = demo.demo_gaps()
    if gaps:
        # A demo that fails its own checks is not loaded and then reported on. The rows are
        # about to become a client's rows, and the cheapest moment to refuse is before that.
        log.error("refusing to seed", reason="the demo does not satisfy its own rules")
        for gap in gaps:
            print(f"REFUSED: {gap}", file=sys.stderr)
        return 1

    engine = create_engine(normalise_database_url(url), poolclass=None)
    try:
        with engine.begin() as conn:
            written = install(conn)
    finally:
        engine.dispose()

    log.info("seeded", **{table.replace(".", "_"): count for table, count in written.items()})
    print(demo.summary())
    return 0


def main(argv: list[str] | None = None) -> int:
    import os

    args = argv if argv is not None else sys.argv[1:]
    url = os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL", "")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    if "--remove" in args:
        engine = create_engine(normalise_database_url(url), poolclass=None)
        try:
            with engine.begin() as conn:
                removed = remove(conn)
        finally:
            engine.dispose()
        print(f"removed {sum(removed.values())} demo row(s)")
        return 0
    if "--smoke" in args:
        engine = create_engine(normalise_database_url(url), poolclass=None)
        try:
            with engine.connect() as conn:
                question, found, expected = smoke(conn)
        finally:
            engine.dispose()
        print(f"asked: {question}")
        print(f"answered: {found if found else demo.NO_ANSWER}")
        if found != expected:
            print(f"expected {expected!r}, got {found!r}", file=sys.stderr)
            return 1
        return 0
    if "--ask" in args:
        question = args[args.index("--ask") + 1] if len(args) > args.index("--ask") + 1 else ""
        if not question:
            print("--ask needs a question", file=sys.stderr)
            return 2
        engine = create_engine(normalise_database_url(url), poolclass=None)
        try:
            with engine.connect() as conn:
                found = ask(conn, question)
        finally:
            engine.dispose()
        # One line for every kind of nothing. See `brain.demo.NO_ANSWER`: a fresh install
        # distinguishing "no such record" from "no such rule" teaches its first user that an
        # absent answer is a fact about what exists.
        print(found if found else demo.NO_ANSWER)
        return 0
    return seed(url, force="--force" in args)


if __name__ == "__main__":
    raise SystemExit(main())
