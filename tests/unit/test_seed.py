"""The seed command, and the guard that stops it running somewhere real.

Task ids: M0.4.4, M0.4.5, M38.1.4.4

M38.1.4.4 asks for seed data in staging and never production data. That is a property of
this command rather than of the staging compose file, because the compose file describes a
stack and this is the only thing that writes rows into one. The guard is therefore tested
through `looks_like_production` itself, against a connection that answers the way a real
database would, rather than through `seed` with the guard replaced.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import ProgrammingError

from brain import demo
from brain import seed as seed_mod


class _Recorder:
    """A connection that remembers the statements run against it and executes nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def execute(self, statement: object, parameters: Any = None, /) -> None:
        self.calls.append((str(statement), parameters))


def _engine(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Point `seed` at a recorder instead of a database, and hand the recorder back."""
    recorder = _Recorder()

    class _Engine:
        def begin(self) -> Any:
            return nullcontext(recorder)

        def dispose(self) -> None:
            return None

    monkeypatch.setattr(seed_mod, "create_engine", lambda *_a, **_k: _Engine())
    return recorder


def test_the_seed_reads_the_demo_company_and_never_the_test_fixture() -> None:
    """The install step must not read a Verz artefact (M41.2.3).

    It did until 2026-09-07: `_seed_rows` imported `tests.fixtures.company`, which is Verz's
    own org chart with a canary in every restricted field, and which is not in the deployed
    image at all. So `make seed` could not run on a client's install, and what it would have
    written if it could was a Verz value in their database on the first day.

    Deleting this test lets the import come back, and the symptom of its coming back is a
    client seeing `CANARY-CONTRACT-7Q4XZ` on their first screen.
    """
    principals, grants = seed_mod._seed_rows()
    ids = {p["id"] for p in principals}
    assert ids == {row["id"] for row in demo.demo_rows()["auth.principal"]}
    assert all(one.startswith(demo.DEMO_PREFIX) for one in ids), ids

    from tests.fixtures.company import build_company

    assert not (ids & set(build_company())), "the seed and the test fixture share a principal"
    assert len(grants) == len(demo.grant_rows())


def test_the_seeded_grants_carry_a_scope_a_granter_and_a_reason() -> None:
    """`granted_by` and `reason` are not nullable on `gate.capability_grant`, so a row
    missing either is an insert that fails halfway through the demo load rather than a demo
    that looks slightly thin. Deleting this leaves those two columns supplied by whichever
    call site happens to write the row next."""
    _, grants = seed_mod._seed_rows()
    assert grants
    assert all("clauses" in g["scope"] for g in grants)
    assert all(g["granted_by"] == demo.GRANTED_BY for g in grants)
    assert all(g["reason"].strip() for g in grants)


def test_the_owned_table_list_is_explicit() -> None:
    """What this command may disturb is written down rather than inferred, so widening it is
    a visible edit. It said "seeding truncates what it owns" until 2026-09-11, which had
    stopped being true: nothing here truncates anything, every insert carries ON CONFLICT DO
    NOTHING and every delete is bounded by a declared identifier. `OWNED` is now only the
    list `looks_like_production` treats as unsurprising, which is a smaller claim and the one
    the guard actually makes.

    Deleting this lets `proj.record` join the list, and `WRITING_IS_NOT_OWNING` says what
    that costs."""
    # Corrected 5 September: the table M1.4.1 actually creates is `capability_grant`.
    # `gate.grant` named nothing, and `looks_like_production` counts rows in tables it
    # does not own, so the first real grant row would have made the seeder refuse to run.
    assert seed_mod.OWNED == ("auth.principal", "gate.capability_grant")


def test_seed_refuses_when_the_database_holds_rows_it_does_not_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'I ran the seed against production' should be impossible, not discouraged.

    `already_loaded` is answered no here, which is what a client's database says: their rows
    are theirs and none of the demo's identifiers is among them. The case where it answers
    yes has its own test below, and the two together are what stop the short-circuit becoming
    a way past the guard.
    """
    monkeypatch.setattr(
        seed_mod, "looks_like_production", lambda _url: (True, "know.item (4,102 rows)")
    )
    monkeypatch.setattr(seed_mod, "already_loaded", lambda _url: False)
    assert seed_mod.seed("postgresql://x", force=False) == 1


def test_force_overrides_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_mod, "looks_like_production", lambda _url: (True, "whatever"))
    _engine(monkeypatch)
    assert seed_mod.seed("postgresql://x", force=True) == 0


def test_an_empty_database_seeds_without_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_mod, "looks_like_production", lambda _url: (False, ""))
    _engine(monkeypatch)
    assert seed_mod.seed("postgresql://x") == 0


def test_a_demo_that_fails_its_own_checks_is_refused_before_anything_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rows are about to become a client's rows, so the cheapest moment to refuse is
    before the first insert rather than after the load, with a report.

    Deleting this leaves `demo_gaps` a function nothing calls on the path where it matters,
    which is the path where a canary or an unrestricted grant would reach a client.
    """
    monkeypatch.setattr(seed_mod, "looks_like_production", lambda _url: (False, ""))
    monkeypatch.setattr(demo, "demo_gaps", lambda: ("an unrestricted grant",))
    recorder = _engine(monkeypatch)
    assert seed_mod.seed("postgresql://x") == 1
    assert not recorder.calls, "the demo was written despite failing its own checks"


# ------------------------------------------------------- writing, and writing reversibly
def test_every_table_the_demo_declares_is_written_in_the_order_it_declares_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grant carries a foreign key to a principal, so principals go first. The order is
    `brain.demo.TABLES`, read rather than restated, because a second ordering is a second
    thing to keep in step.

    Deleting this lets a table be dropped from the load with the demo still reporting a
    summary, which is an install that looks seeded and answers nothing.
    """
    monkeypatch.setattr(seed_mod, "looks_like_production", lambda _url: (False, ""))
    recorder = _engine(monkeypatch)
    assert seed_mod.seed("postgresql://x") == 0
    written = [statement for statement, _ in recorder.calls]
    assert len(written) == len(demo.TABLES)
    for statement, table in zip(written, demo.TABLES, strict=True):
        schema, _, name = table.partition(".")
        assert f'INSERT INTO "{schema}"."{name}"' in statement


def test_a_repeated_load_cannot_overwrite_a_row_somebody_edited() -> None:
    """`ON CONFLICT DO NOTHING`, never an upsert. A client who corrects a demo row and then
    re-runs the seed must keep their correction; an upsert would silently restore the
    invented value.

    Deleting this makes the conflict clause removable, and the failure it guards is
    invisible: the second load looks exactly like the first.
    """
    statement = seed_mod.insert_statement("auth.principal", ("id", "display_name"))
    assert "ON CONFLICT" in statement
    assert "DO NOTHING" in statement
    assert "DO UPDATE" not in statement


def test_the_conflict_clause_names_a_key_only_where_the_table_has_one() -> None:
    """Two forms, and which one is used is a decision `brain.ops.guards` cannot mutate because
    it is a conditional expression rather than an `if`. `auth.principal` has a natural key and
    names it; `gate.capability_grant` has none of this module's choosing, so the clause names
    no column and the table's own partial unique index decides. Measured on 2026-09-11 against
    a real PostgreSQL: a forced second load leaves thirty-one grants at thirty-one.

    Swapping the two produces `ON CONFLICT () DO NOTHING`, which is a syntax error PostgreSQL
    reports and no test here builds a database to hear.

    Deleting this leaves the choice untested in both directions, and the direction that fails
    fails on the client's server rather than here.
    """
    keyed = seed_mod.insert_statement("auth.principal", ("id", "display_name"))
    assert "ON CONFLICT (id) DO NOTHING" in keyed

    unkeyed = seed_mod.insert_statement("gate.capability_grant", ("principal_id", "capability"))
    assert "ON CONFLICT DO NOTHING" in unkeyed
    assert "ON CONFLICT (" not in unkeyed, unkeyed
    assert seed_mod.CONFLICT_KEYS["gate.capability_grant"] == ()


def test_a_mapping_column_is_serialised_before_it_reaches_the_driver() -> None:
    """`proj.record.fields` is a mapping and psycopg will not adapt a dict to `jsonb` on its
    own, so the demo's records fail to insert at all unless something serialises them. This is
    the second decision in this module the guard audit cannot reach, and it is the one that
    only breaks against a real database.

    Asserted both ways: the mapping becomes a string that parses back to the same mapping, and
    a value that was already a string is left alone rather than quoted twice.

    Deleting this lets the serialisation go, and the symptom is the demo load failing on the
    third table on somebody's install while every test here passes.
    """
    row = next(iter(demo.record_rows()))
    assert isinstance(row["fields"], dict), "the demo stopped carrying a mapping"

    bound = seed_mod._bindable(row)
    assert isinstance(bound["fields"], str)
    assert json.loads(bound["fields"]) == row["fields"]
    assert bound["source"] == row["source"]


def test_a_value_never_reaches_a_statement_as_text() -> None:
    """Every value is a bind parameter and only identifiers are interpolated. Deleting this
    lets a demo value be formatted into SQL, and the demo's values are the one part of this
    module somebody is expected to edit."""
    statement = seed_mod.insert_statement("proj.record", ("source", "entity", "source_id"))
    assert ":source" in statement and ":entity" in statement and ":source_id" in statement
    for row in demo.record_rows():
        assert str(row["source_id"]) not in statement


def test_a_column_name_that_is_not_an_identifier_never_reaches_a_statement() -> None:
    """The table and column names are interpolated, so anything that is not an ordinary
    lowercase identifier is refused rather than quoted and hoped for. Deleting this leaves
    the one interpolation in this module unguarded."""
    with pytest.raises(ValueError, match="ordinary identifier"):
        seed_mod.insert_statement("auth.principal", ('id"; drop table x --',))


def test_removal_is_bounded_by_the_identifiers_the_demo_declares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prefix match would also catch a real person a client happened to name that way, and
    the occasion that matters is somebody running this over data they meant to keep. So the
    delete carries the list, and the list is `brain.demo.demo_identifiers`.

    Deleting this lets the bound become `LIKE 'demo_%'`, which is one character from
    `LIKE '%'` and reads the same in review.
    """
    recorder = _Recorder()
    removed = seed_mod.remove(recorder)
    declared = set(demo.demo_identifiers())
    assert removed
    for statement, parameters in recorder.calls:
        assert "LIKE" not in statement.upper()
        assert set(parameters["targets"]) <= declared


def test_removal_runs_in_the_reverse_of_the_order_the_load_used() -> None:
    """The foreign key runs from a grant to a principal, so deleting principals first is
    refused while their grants still point at them. Deleting this test lets the two orders
    drift apart, and the symptom is a removal that half completes."""
    recorder = _Recorder()
    seed_mod.remove(recorder)
    order = [statement for statement, _ in recorder.calls]
    # The trigger-written tables are cleared first and are not the demo's own; see
    # `seed.TRIGGER_WRITTEN`. This test is about the order of the demo's tables among
    # themselves, so it starts after them.
    order = order[len(seed_mod.TRIGGER_WRITTEN) :]
    for statement, table in zip(order, tuple(reversed(demo.TABLES)), strict=True):
        schema, _, name = table.partition(".")
        # The target is built separately from the verb, so this assertion is not itself a
        # string that looks like an assembled statement.
        assert statement.startswith("DELETE FROM ")
        assert f'"{schema}"."{name}"' in statement


def test_owning_a_table_and_writing_into_one_stay_different_lists() -> None:
    """`OWNED` is what `looks_like_production` treats as disposable. Widening it to the
    demo's tables would tell the guard that rows in `proj.record` are safe to ignore, and
    that is where a real client's projected records live.

    Deleting this test removes the only thing standing between "the demo writes here" and
    "the guard may ignore this", which are one edit apart and read alike.
    """
    assert set(seed_mod.OWNED) < set(seed_mod.WRITES)
    assert "proj.record" in seed_mod.WRITES
    assert "proj.record" not in seed_mod.OWNED


def test_main_needs_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    assert seed_mod.main([]) == 2


# --------------------------------------------- the guard reads more than an estimate
def test_the_guard_does_not_rely_on_statistics_alone() -> None:
    """`n_live_tup` is an estimate maintained by the statistics collector, not a count. It
    is zero for a freshly restored database until autovacuum or ANALYZE has run, so a
    production dump restored ten minutes ago read as empty and this guard said it was safe
    to truncate.

    Asserted by reading the source, because the failure needs a real Postgres with cold
    statistics and a table full of rows, which no unit test can stand up. What a test can do
    is fail the moment somebody removes the exact probe and leaves the estimate.
    """
    source = (Path(__file__).resolve().parents[2] / "src" / "brain" / "seed.py").read_text(
        encoding="utf-8"
    )
    assert "LIMIT 1" in source, "the exact probe is gone; only the estimate remains"
    assert "n_live_tup" in source, "the estimate is gone; it covers a blind spot in the probe"


# ------------------------------- the guard, driven rather than described (M38.1.4.4)
class _Result:
    """What `Connection.execute` hands back, in the two shapes this module reads."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows

    def first(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _Connection:
    """A database that answers the three questions the guard asks.

    A fake rather than a real Postgres, because the case that matters most cannot be built
    against a real one in a unit test: a freshly restored snapshot whose statistics are still
    cold. Here that is two lines of setup and it is the exact shape the bug had.
    """

    def __init__(self, tables: list[tuple[str, str]], populated: set[str], stats: set[str]) -> None:
        self.tables = tables
        self.populated = populated
        self.stats = stats

    def execute(self, statement: object) -> _Result:
        sql = str(statement)
        if "information_schema.tables" in sql:
            return _Result(list(self.tables))
        if "pg_stat_user_tables" in sql:
            return _Result([(*name.split("."), 4102) for name in sorted(self.stats)])
        # A row probe. The guard builds it as `SELECT 1 FROM "schema"."table" LIMIT 1`.
        quoted = sql.split("FROM ")[1].split(" LIMIT")[0]
        name = quoted.replace('"', "")
        return _Result([(1,)] if name in self.populated else [])


def _database(
    monkeypatch: pytest.MonkeyPatch,
    tables: list[tuple[str, str]],
    *,
    populated: Collection[str] = (),
    stats: Collection[str] = (),
) -> None:
    connection = _Connection(tables, set(populated), set(stats))

    class _Engine:
        def connect(self) -> Any:
            return nullcontext(connection)

        def dispose(self) -> None:
            return None

    monkeypatch.setattr(seed_mod, "create_engine", lambda *_a, **_k: _Engine())


def test_a_database_holding_rows_the_seed_does_not_own_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The leaf itself: seeding is destructive, so "I ran the seed against production" has to
    be impossible rather than discouraged. Staging gets seed data because this refuses to run
    anywhere that already holds something.

    Driven through the real guard rather than through `seed` with the guard replaced. The
    replaced version tests that `seed` honours an answer; this tests that the answer is right,
    and the answer is the whole leaf. Deleting it leaves the refusal asserted only against a
    stub, which passes with the guard's body deleted.
    """
    _database(
        monkeypatch,
        [("auth", "principal"), ("know", "item")],
        populated={"know.item"},
    )
    risky, why = seed_mod.looks_like_production("postgresql://x")
    assert risky
    assert "know.item" in why


def test_a_database_holding_only_what_the_seed_owns_is_seedable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive half, and it is not decoration. A guard tested only by its refusals is
    satisfied by one that refuses everything, and a seeder that refuses every database is a
    seeder somebody runs with `--force` by habit - which disables the refusal that matters
    along with the one that does not.

    `auth.principal` is full here and the answer is still yes, because re-seeding a stack this
    command already owns is the normal case.
    """
    _database(
        monkeypatch,
        [("auth", "principal"), ("gate", "capability_grant")],
        populated={"auth.principal", "gate.capability_grant"},
    )
    assert seed_mod.looks_like_production("postgresql://x") == (False, "")


def test_a_snapshot_restored_minutes_ago_is_refused_even_though_its_statistics_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug that actually happened, as a behaviour rather than as a source-code check.

    `n_live_tup` is an estimate maintained by the statistics collector, so it is zero for a
    freshly restored database until autovacuum or ANALYZE has run. A production dump restored
    ten minutes ago therefore read as empty, and the guard said it was safe to truncate.

    Deleting this leaves that path covered only by a test asserting the string `LIMIT 1`
    appears in the file, which passes for a probe that is built and never executed.
    """
    _database(
        monkeypatch,
        [("obs", "audit_entry")],
        populated={"obs.audit_entry"},
        stats=set(),
    )
    risky, why = seed_mod.looks_like_production("postgresql://x")
    assert risky, "a restored snapshot with cold statistics read as an empty database"
    assert "holds rows" in why


def test_rows_the_connected_role_cannot_see_are_refused_on_the_statistics_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The blind spot the estimate is kept for, and until 2026-09-11 nothing reached it.**
    The exact probe runs as whoever is connected, and row-level security can hide every row
    in a table from that role while `pg_stat_user_tables` still counts them. So a client's
    database read as empty to the probe, and the estimate is the only signal that says
    otherwise. The docstring has argued that since the probe was added; the guard audit found
    on 2026-09-11 that switching the estimate arm off changed nothing any test could see.

    The mirror image of `test_a_snapshot_restored_minutes_ago...`, which is the probe covering
    the estimate's blind spot. Neither covers the other, which is why both run and either
    refuses, and why both now have a test that fails when the other one is deleted.

    Deleting this lets the estimate arm go, and what goes with it is the only thing that
    notices a table full of rows the seeding role is not allowed to see.
    """
    _database(monkeypatch, [("know", "item")], populated=set(), stats={"know.item"})
    risky, why = seed_mod.looks_like_production("postgresql://x")
    assert risky, "a table whose rows are hidden by policy read as an empty table"
    assert "know.item" in why
    assert "by statistics" in why, why


def test_a_table_whose_name_is_not_an_identifier_stops_the_seed_rather_than_being_queried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard interpolates a schema and table name into a probe, so a name that is not an
    ordinary identifier is reported instead of being run. Refusing to seed is the safe
    outcome, and a name that odd is worth a person looking at.

    Deleting this makes the validation removable without a test noticing, and what it guards
    is a string from the database reaching a query as though it were a literal.
    """
    _database(monkeypatch, [("know", 'item"; drop table x --')], populated=set())
    risky, why = seed_mod.looks_like_production("postgresql://x")
    assert risky
    assert "not an ordinary identifier" in why


#: The one file under `ops/` allowed to name `pg_dump`, and it is a path rather than a flag.
#:
#: A perishable exemption, in the shape `brain.ops.controls.NOT_A_SCHEDULE` takes: the test
#: below asserts the file exists, so an exemption that outlives the thing it exempts fails
#: rather than sitting there waiting to cover whatever takes the name next.
THE_ONLY_TAKER = "ops/backup/brain-backup"


def _ops_lines(repo: Path) -> list[tuple[str, int, str]]:
    """Every line of every non-Markdown file under `ops/`, with where it came from."""
    return [
        (path.relative_to(repo).as_posix(), number, line)
        for path in sorted((repo / "ops").rglob("*"))
        if path.is_file() and path.suffix != ".md"
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        )
    ]


def test_nothing_in_this_repository_loads_a_database_from_one_stack_into_another() -> None:
    """The other half of "never production data". The guard stops the seeder; this stops the
    shortcut that goes around it, which is a restore into staging to reproduce a bug.

    The moment that is possible somebody does it, and staging runs with weaker limits on the
    same network as a test harness.

    **This banned three commands until 2026-09-10 and now bans a direction, which is what it
    always meant.** `pg_restore` writes into a database and `pg_basebackup` reads a whole
    cluster off whatever host it is pointed at; both are a copy crossing a boundary and
    neither has an honest use in this repository. `pg_dump` reads, and reading this install's
    own database into this install's own bucket is the nightly copy Needs Rupash item 44 asked
    for. A blanket ban would have refused the backup this system needs in order to have one,
    which is a guard that eventually gets deleted rather than narrowed.

    Delete this and a convenience script that restores production into staging lands in `ops/`
    with nothing objecting."""
    repo = Path(__file__).resolve().parents[2]
    offenders = [
        f"{where}:{number}"
        for where, number, line in _ops_lines(repo)
        if "pg_restore" in line or "pg_basebackup" in line
    ]
    assert not offenders, f"something loads a database from elsewhere: {offenders}"

    taking = [
        f"{where}:{number}"
        for where, number, line in _ops_lines(repo)
        if "pg_dump" in line and where != THE_ONLY_TAKER
    ]
    assert not taking, (
        f"only {THE_ONLY_TAKER} may take a copy, and these also do: {taking}. A second taker "
        "is a second answer to what a backup is, and the one nobody reviewed is the one that "
        "writes somewhere else"
    )


def test_the_one_file_allowed_to_take_a_copy_exists_and_only_takes_one() -> None:
    """**An exemption naming a file that is gone is an exemption waiting to cover the next
    file that takes the name.** `brain.ops.controls.NOT_A_SCHEDULE` refuses its own stale
    entries for the same reason, and this is that rule for this one.

    The second half is what makes the exemption narrow rather than a hole: the taker may read,
    and it may not write into a database, load anything back, or reach a second host. A file
    exempted from the rule above that then did the thing the rule is about would be the whole
    guard undone by one line in one file.

    Delete this and the exemption becomes a name in a constant that nothing checks."""
    repo = Path(__file__).resolve().parents[2]
    taker = repo / THE_ONLY_TAKER

    assert taker.is_file(), (
        f"{THE_ONLY_TAKER} does not exist and is still exempted, so the exemption now covers "
        "whatever is written at that path next"
    )

    source = taker.read_text(encoding="utf-8")
    for forbidden in ("pg_restore", "pg_basebackup", "psql"):
        assert forbidden not in source, (
            f"{THE_ONLY_TAKER} names {forbidden}, so the one file allowed to read a database "
            "also writes to one, which is the guard above undone in the place it exempted"
        )
    assert "pg_dump" in source, (
        f"{THE_ONLY_TAKER} is exempted from the copy rule and takes no copy, so the exemption "
        "is covering a file that does not need it"
    )


def test_the_guard_looks_in_every_schema_that_exists() -> None:
    """It used to check seven while nine existed. `obs` was one of the two missing, and
    `obs` holds the audit ledger, which is the one thing here that re-running the seeder
    cannot undo."""
    from brain.db import SCHEMAS

    source = (Path(__file__).resolve().parents[2] / "src" / "brain" / "seed.py").read_text(
        encoding="utf-8"
    )
    assert "sorted(SCHEMAS)" in source, (
        "the schema list is hard-coded again; it drifts from brain.db.SCHEMAS the next time "
        "a schema is added, and the one that gets forgotten is the new one"
    )
    assert "obs" in SCHEMAS


# ------------------------------------------------------- one question, from the database
class _Rows:
    """What `Connection.execute` hands back when the caller asks for mappings."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Reader:
    """A database that answers the two questions `ask` puts to it, and no others."""

    def __init__(self, rules: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
        self.rules = rules
        self.records = records
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: Any = None, /) -> _Rows:
        sql = str(statement)
        self.statements.append(sql)
        if "fast_path_rule" in sql:
            return _Rows(self.rules)
        return _Rows(self.records)


def test_a_question_is_answered_from_the_rows_the_database_holds() -> None:
    """The install is provable rather than describable only if something answers, and the
    answer has to come from the database rather than from the module that declared the demo.
    Every install bug this repository has had lived in that gap: a Dockerfile that never
    copied the migrations, a volume path that only failed on start, a seed importing a
    directory the image does not contain.

    Deleting this leaves the read path exercised only by the CI job, which cannot say which
    half broke.
    """
    reader = _Reader(list(demo.rule_rows()), list(demo.record_rows()))
    assert seed_mod.ask(reader, "what is the status of Ashgrove Retail Group") == "active"
    assert any("fast_path_rule" in one for one in reader.statements)
    assert any("proj.record" in one for one in reader.statements)


def test_a_question_answered_from_an_empty_database_comes_back_as_nothing() -> None:
    """A migrated install with no rows in it must answer the same nothing as one asked about
    a record that does not exist. An install that said "no rules configured" would be telling
    its first user about its own state in a place answers belong.

    Deleting this lets the empty case raise or return a diagnostic, and the diagnostic is on
    the one screen a first user reads most carefully.
    """
    assert seed_mod.ask(_Reader([], []), "what is the status of Ashgrove Retail Group") is None


def test_the_read_names_its_columns_rather_than_selecting_everything() -> None:
    """A column added to `gate.fast_path_rule` must be inert until somebody puts it here, which
    is the rule `brain.gate.fast_lane.RULE_FIELDS` states about the same table: a new column
    reaching the matcher by accident is a rule field nobody reviewed.

    Deleting this lets the read become `SELECT *`, and the matcher then receives whatever the
    table grows next.
    """
    assert "SELECT *" not in seed_mod._READ_RULES
    assert "SELECT *" not in seed_mod._READ_RECORDS
    for column in (
        "rule_id",
        "template",
        "slot",
        "source",
        "entity",
        "match_field",
        "answer_field",
    ):
        assert column in seed_mod._READ_RULES


def test_the_smoke_check_compares_the_database_against_what_the_demo_declared() -> None:
    """`--smoke` is the whole of the CI install job's assertion, so it has to be a comparison
    between two different things: the left side comes out of the database through the fast
    lane's matcher, the right side is what `brain.demo` said it was going to write.

    Deleting this leaves the CI step asserting something no test explains, and the step would
    go on passing with the answer path removed.
    """
    reader = _Reader(list(demo.rule_rows()), list(demo.record_rows()))
    question, found, expected = seed_mod.smoke(reader)
    assert found == expected
    assert question.lower().startswith("what is the status of")


def test_the_smoke_check_fails_on_a_migrated_install_that_was_never_seeded() -> None:
    """The case it exists for. A database with the schema and no rows answers nothing, and an
    install that migrated and did not seed looks identical to one that worked until something
    asks it a question.

    Deleting this lets `smoke` pass over an empty database, which is the exact failure the CI
    job was added to catch.
    """
    question, found, expected = seed_mod.smoke(_Reader([], []))
    assert found is None
    assert expected
    assert question


def test_what_a_trigger_wrote_is_deleted_before_the_principals_it_points_at() -> None:
    """**CI found this and nothing here could have.** Inserting a capability grant fires
    `gate.bump_grants_version`, which writes a `gate.grants_version` row keyed on the
    principal. The demo never declares that row, so removal never deleted it, and the foreign
    key is RESTRICT: deleting the demo's principals came back
    `violates RESTRICT setting of foreign key constraint
    fk_grants_version_principal_id_principal`.

    A laptop with no PostgreSQL enforces no foreign key and fires no trigger, so every test in
    this file passed while the demo could not be removed at all. That is worse than the bug:
    `A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA` is the reason there is a demo, and it
    was false in the one place it is checked.

    Asserted on the order and on the bound rather than by running it, because there is still
    no PostgreSQL here. The end-to-end proof is the CI job, and this is what fails first and
    on the right machine when somebody reorders the deletes.

    Delete this and the demo becomes unremovable again, silently, everywhere except CI."""
    recorder = _Recorder()
    removed = seed_mod.remove(recorder)

    assert seed_mod.TRIGGER_WRITTEN, "nothing declared, so this test proves nothing"

    first = [statement for statement, _ in recorder.calls][: len(seed_mod.TRIGGER_WRITTEN)]
    for statement, table in zip(first, seed_mod.TRIGGER_WRITTEN, strict=True):
        schema, _, name = table.partition(".")
        assert statement.startswith("DELETE FROM ")
        assert f'"{schema}"."{name}"' in statement
        assert removed[table] > 0

    principals = {str(one["id"]) for one in demo.principal_rows()}
    for _, parameters in recorder.calls[: len(seed_mod.TRIGGER_WRITTEN)]:
        assert set(parameters["targets"]) == principals & set(demo.demo_identifiers())

    # And the principals themselves come after, which is the whole point of the ordering.
    tables_in_order = [statement for statement, _ in recorder.calls]
    grants_version = next(i for i, one in enumerate(tables_in_order) if "grants_version" in one)
    principal_delete = next(i for i, one in enumerate(tables_in_order) if '"principal"' in one)
    assert grants_version < principal_delete


# ------------------------------------------------- running it a second time (M0.4.4)
class _Present:
    """A database holding exactly the demo identifiers it was constructed with.

    Built to answer `not_yet_loaded` and nothing else: it reads the bound list out of the
    parameters and hands back the subset it holds, which is what a real `SELECT DISTINCT
    <key> ... WHERE <key> = ANY(:targets)` does.
    """

    def __init__(self, held: Collection[str]) -> None:
        self.held = set(held)
        self.statements: list[str] = []
        self.bounds: list[list[str]] = []

    def execute(self, statement: object, parameters: Any = None, /) -> _Result:
        self.statements.append(str(statement))
        targets = list(parameters["targets"]) if parameters else []
        self.bounds.append(targets)
        return _Result([(one,) for one in targets if one in self.held])


def _everything() -> set[str]:
    """Every identifier the demo would have written, across all four of its tables."""
    return {one for table in demo.TABLES for one in seed_mod.declared_in(table)}


def test_a_second_seed_over_a_database_holding_the_demo_writes_nothing_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The leaf's second-run question, and until 2026-09-11 the answer was a production
    refusal.** Measured against a real PostgreSQL: the first run wrote four tables and fired
    triggers into three more, and the second came back `database holds rows this command does
    not own: gate.fast_path_rule, gate.grants_version, gate.policy_epoch, obs.audit_entry,
    proj.record` - every one of them a table the seed itself had just filled. The only remedy
    the message offered was `--force`, which is the flag that turns the guard off.

    So a second run is a no-op that succeeds: nothing is written, the exit code is zero, and
    the state after two runs is the state after one. `insert_statement` has argued for that
    since it was written; what was missing was reaching the inserts at all.

    Delete this and the short-circuit can go, and what comes back is a command that refuses
    its own second run in the words of the production guard.
    """
    monkeypatch.setattr(seed_mod, "looks_like_production", lambda _url: (True, "proj.record"))
    monkeypatch.setattr(seed_mod, "already_loaded", lambda _url: True)
    recorder = _engine(monkeypatch)

    assert seed_mod.seed("postgresql://x") == 0
    assert not recorder.calls, "a second seed wrote rows into a database that already had them"


def test_a_demo_that_is_only_half_there_is_not_treated_as_already_loaded() -> None:
    """The negative half, and the one that stops the short-circuit becoming a hole. "Loaded"
    means every identifier the demo declares, not one of them: a database holding three demo
    people and none of the records has not been seeded, and answering yes would leave it that
    way for ever while reporting success.

    Delete this and `not_yet_loaded` can be weakened to "any row present", which reads the
    same in review and turns a half-loaded install into a permanent one.
    """
    everything = _everything()
    assert not seed_mod.not_yet_loaded(_Present(everything))

    half = sorted(everything)[: len(everything) // 2]
    absent = seed_mod.not_yet_loaded(_Present(half))
    assert absent
    assert all(":" in one for one in absent), absent
    assert not seed_mod.not_yet_loaded(_Present(everything))


def test_presence_is_decided_from_the_identifiers_the_removal_deletes() -> None:
    """One declared list, read by both. What a removal deletes and what presence is decided
    from have to be the same set, or the command can report a demo loaded that its own
    removal would not take out, and the leftover is a fictitious row nobody can name.

    Asserted through `declared_in`, which both call, rather than by comparing two
    comprehensions that happen to agree today.

    Delete this and the two can drift, and the drift is invisible until somebody removes the
    demo and the next seed says it is still there.
    """
    reader = _Present(_everything())
    seed_mod.not_yet_loaded(reader)

    recorder = _Recorder()
    seed_mod.remove(recorder)
    deleted = {
        table: set(parameters["targets"])
        for (statement, parameters), table in zip(
            recorder.calls[len(seed_mod.TRIGGER_WRITTEN) :],
            tuple(reversed(demo.TABLES)),
            strict=True,
        )
        if statement
    }

    for table, bound in zip(demo.TABLES, reader.bounds, strict=True):
        assert set(bound) == deleted[table], table
        assert bound, f"{table} is checked against an empty bound, so presence means nothing"


def test_presence_counts_a_demo_row_somebody_retired_as_still_there() -> None:
    """`proj.record` and `gate.fast_path_rule` carry `deleted_at`, and a retired demo row
    still occupies its identifier: re-inserting it would conflict and do nothing. Reporting
    it absent would promise a load that cannot happen, and the seed would then refuse for
    ever on a database it had already filled.

    Asserted on the statement rather than on a row, because the failure is a `WHERE
    deleted_at IS NULL` copied in from `_READ_RECORDS`, which answers a different question.

    Delete this and that clause comes back, and the symptom is a demo that can never be
    reported loaded once anybody retires one of its rows.
    """
    reader = _Present(_everything())
    seed_mod.not_yet_loaded(reader)

    assert reader.statements
    for statement in reader.statements:
        assert "deleted_at" not in statement, statement
        assert statement.startswith("SELECT DISTINCT ")


def test_a_refusal_names_something_to_do_before_it_names_force(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**A guard that refuses the ordinary case and offers one way past it teaches that way
    past it.** `test_a_database_holding_only_what_the_seed_owns_is_seedable` already says so
    about the guard; this says it about the message, which is the half somebody actually
    reads. The refusal used to end `Pass --force only if you are certain this database is
    disposable`, which names the flag that stops the check running and nothing else.

    Asserted on the order of the lines as well as on their presence, because a remedy printed
    after `--force` has been printed after the reader has stopped reading.

    Delete this and the message can go back to one line naming one flag.
    """
    monkeypatch.setattr(seed_mod, "looks_like_production", lambda _url: (True, "know.item"))
    monkeypatch.setattr(seed_mod, "already_loaded", lambda _url: False)

    assert seed_mod.seed("postgresql://x") == 1
    printed = capsys.readouterr().err

    assert "--remove" in printed
    assert "make reset" in printed
    assert printed.index("--remove") < printed.index("--force")
    assert seed_mod.REMEDIES[-1].startswith("--force"), seed_mod.REMEDIES


def test_a_presence_check_never_interpolates_a_name_that_is_not_an_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The presence read interpolates a schema, a table and a column exactly as the removal
    does, so it carries the same validation. A validator that is written and never run is
    this repository's most common defect, and this one guards the only interpolation in a
    statement that is built per table.

    Delete this and the check becomes removable, and what it guards is a column name reaching
    a query as though it were a literal.
    """
    monkeypatch.setattr(
        seed_mod,
        "REMOVAL_KEYS",
        dict(seed_mod.REMOVAL_KEYS) | {"proj.record": 'source_id"; drop table x --'},
    )
    with pytest.raises(ValueError, match="ordinary identifier"):
        seed_mod.not_yet_loaded(_Present(()))


# ------------------------------------------- guards that were written and never reached
def test_the_statistics_arm_ignores_the_tables_the_seed_owns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The estimate half has its own `OWNED` filter and nothing reached it. Without it, a
    database holding the seed's own principals is refused by the statistics even though the
    exact probe passed it, so re-seeding a stack this command already owns becomes
    impossible - which is the normal case, and the one somebody answers with `--force`.

    Found by `brain.ops.guards` on 2026-09-11: `seed.py:175` survived at depth one and at
    depth two, against every test file that imports this module.

    Delete this and the filter can go, and the failure presents as a seeder that refuses a
    database it filled itself.
    """
    _database(
        monkeypatch,
        [("auth", "principal"), ("gate", "capability_grant")],
        populated=set(),
        stats={"auth.principal", "gate.capability_grant"},
    )
    assert seed_mod.looks_like_production("postgresql://x") == (False, "")


def test_a_table_the_demo_declares_no_rows_for_is_skipped_rather_than_indexed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`install` reads the column names off `rows[0]`, so a declared table with no rows yet is
    an `IndexError` in the middle of a load rather than a table that writes nothing. The
    branch that skips it was written and reached by nothing, because every table the demo
    declares has rows today.

    A table declared before its rows exist is an ordinary state: `brain.demo.TABLES` is the
    insertion order, and somebody adding the next one writes the name first.

    Delete this and the skip can go, and the symptom is a half-written demo in a rolled-back
    transaction with a traceback about list indices.
    """
    thinned = {
        table: (() if table == "proj.record" else rows) for table, rows in demo.demo_rows().items()
    }
    monkeypatch.setattr(demo, "demo_rows", lambda: thinned)

    recorder = _Recorder()
    written = seed_mod.install(recorder)

    assert written["proj.record"] == 0
    assert not any("proj" in statement for statement, _ in recorder.calls)
    assert written["auth.principal"] == len(demo.principal_rows())


def test_a_trigger_written_table_named_oddly_stops_the_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`TRIGGER_WRITTEN` is interpolated into a DELETE the same way `REMOVAL_KEYS` is, and its
    validation was reached by nothing: both constants are written here and always valid, so
    every object any test builds is valid. That is the exact shape this repository's guard
    audit keeps finding.

    Delete this and the validation on the first statement `remove` runs becomes removable,
    and it is a DELETE.
    """
    monkeypatch.setattr(
        seed_mod, "TRIGGER_WRITTEN", {"gate.grants_version": 'principal_id" OR 1=1 --'}
    )
    with pytest.raises(ValueError, match="ordinary identifier"):
        seed_mod.remove(_Recorder())


def test_a_removal_column_that_is_not_an_identifier_stops_the_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same validation on the demo's own tables, and the same reason it was unreachable.
    A DELETE is the one statement in this module where an unchecked interpolation cannot be
    undone by re-running anything.

    Delete this and `remove` will build a DELETE round whatever `REMOVAL_KEYS` holds.
    """
    monkeypatch.setattr(
        seed_mod, "REMOVAL_KEYS", dict(seed_mod.REMOVAL_KEYS) | {"auth.principal": "id; drop"}
    )
    with pytest.raises(ValueError, match="ordinary identifier"):
        seed_mod.remove(_Recorder())


# ------------------------------------------------- the command line CI actually runs
class _Both:
    """An engine that hands one executor to `begin` and to `connect` alike."""

    def __init__(self, executor: object) -> None:
        self._executor = executor

    def begin(self) -> Any:
        return nullcontext(self._executor)

    def connect(self) -> Any:
        return nullcontext(self._executor)

    def dispose(self) -> None:
        return None


def _command(monkeypatch: pytest.MonkeyPatch, executor: object) -> None:
    """Point `main` at one executor, with a URL in the environment."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(seed_mod, "create_engine", lambda *_a, **_k: _Both(executor))


def test_the_removal_subcommand_is_reachable_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Every subcommand below is run by the CI install job and by no test until now.**
    `brain.ops.guards` reported `--remove`, `--smoke`, `--ask` and the answer comparison as
    survivors at depth one and depth two on 2026-09-11: the functions underneath were tested
    and the dispatch that reaches them was not, so a flag could be renamed or dropped and
    every test here would still pass while the job that proves an install works broke.

    Delete this and `--remove` can stop being wired up, and M41.2.6's smallest testable half
    goes with it.
    """
    recorder = _Recorder()
    _command(monkeypatch, recorder)

    assert seed_mod.main(["--remove"]) == 0
    assert recorder.calls
    assert all(statement.startswith("DELETE FROM ") for statement, _ in recorder.calls)


def test_the_smoke_subcommand_answers_zero_and_a_wrong_answer_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--smoke` is the whole of the CI install job's assertion, so the comparison has to be
    able to fail. It compares what came out of the database against what `brain.demo`
    declared, and a comparison nothing has ever seen fail is a comparison that might be
    between a constant and itself.

    Both directions here: a seeded database exits zero, and a migrated one that was never
    seeded exits one.

    Delete this and the exit code can be pinned at zero, and the CI step that exists to catch
    an install that never seeded passes on one.
    """
    _command(monkeypatch, _Reader(list(demo.rule_rows()), list(demo.record_rows())))
    assert seed_mod.main(["--smoke"]) == 0

    _command(monkeypatch, _Reader([], []))
    assert seed_mod.main(["--smoke"]) == 1


def test_the_ask_subcommand_answers_and_refuses_an_empty_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--ask` with nothing after it used to be a flag with no test at all, and the branch
    that refuses it is the difference between a usage message and asking the database the
    empty string, which matches no rule and prints the same `no answer` a real absence does.

    The CI job asks two questions through this flag and compares the answers, so a usage
    error printed as an answer would make that comparison pass for the wrong reason.

    Delete this and the dispatch and its refusal both go untested.
    """
    _command(monkeypatch, _Reader(list(demo.rule_rows()), list(demo.record_rows())))
    assert seed_mod.main(["--ask", "what is the status of Ashgrove Retail Group"]) == 0
    assert capsys.readouterr().out.strip() == "active"

    assert seed_mod.main(["--ask"]) == 2
    assert "needs a question" in capsys.readouterr().err


def test_already_loaded_asks_the_database_rather_than_assuming_either_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The thin half of the second-run answer, and the half a stub hides. Every test above
    that exercises the short-circuit replaces `already_loaded`, so the function itself - the
    engine it opens and the `not` in front of `not_yet_loaded` - is reached by nothing unless
    something drives it.

    Inverted, it would report every database as already holding the demo, and the command
    would report success on a fresh install having written nothing at all. That is the worst
    failure this module has available and it is one character.

    Delete this and the wrapper goes untested in both directions.
    """
    monkeypatch.setattr(seed_mod, "create_engine", lambda *_a, **_k: _Both(_Present(_everything())))
    assert seed_mod.already_loaded("postgresql://x") is True

    monkeypatch.setattr(seed_mod, "create_engine", lambda *_a, **_k: _Both(_Present(())))
    assert seed_mod.already_loaded("postgresql://x") is False


def test_a_presence_question_that_cannot_be_asked_is_answered_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The short-circuit runs only after the guard has refused, so it can turn a refusal into
    a success and nothing else. A database migrated halfway, or migrated by something else,
    makes the presence read raise, and letting that out would replace a refusal somebody can
    act on with a traceback on the first command of an install.

    Answering no leaves exactly the behaviour there was before the short-circuit existed,
    which is the only safe direction for a fallback on this path.

    Deleting this lets the fallback be widened to True, which would turn every database the
    read cannot be run against into one the seed reports as already holding the demo.
    """

    class _Broken:
        def execute(self, statement: object, parameters: Any = None, /) -> Any:
            raise ProgrammingError("select", {}, Exception("relation does not exist"))

    monkeypatch.setattr(seed_mod, "create_engine", lambda *_a, **_k: _Both(_Broken()))
    assert seed_mod.already_loaded("postgresql://x") is False

    monkeypatch.setattr(
        seed_mod, "looks_like_production", lambda _url: (True, "know.item (4,102 rows)")
    )
    assert seed_mod.seed("postgresql://x") == 1


def test_a_declared_table_that_contributes_no_identifier_stops_the_presence_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Found by a mutation that survived.** The code skipped such a table, and skipping it
    changed nothing a test could see: an empty bound matches nothing and extends nothing. What
    it changed was the answer above it. A table contributing no identifier is silently agreed
    to be present, so `already_loaded` reports the demo whole while a whole table of it is
    missing, and the seed then declines to write the rows that are not there.

    It takes two constants in two modules disagreeing: `brain.demo.demo_identifiers` and
    `brain.seed.REMOVAL_KEYS` have to name the same column for a table's presence to mean
    anything, and nothing else compares them.

    Deleting this leaves the refusal unreachable again, and the failure it prevents is an
    install that reports success having written a quarter of the demo.
    """
    monkeypatch.setattr(
        demo, "demo_identifiers", lambda: tuple(one["id"] for one in demo.principal_rows())
    )

    with pytest.raises(ValueError, match="contributes no identifier"):
        seed_mod.not_yet_loaded(_Present(()))
